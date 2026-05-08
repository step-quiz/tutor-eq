"""
Client a l'API de Google Gemini. Implementa les 4 crides definides a la Fase 0:

1. judge_progress       — equació equivalent: avança o estanca?
2. classify_error       — equació no equivalent: quin error té?
3. interpret_input      — SymPy no parseja: què ha escrit l'alumne?
4. generate_hint        — l'alumne ha escrit '?': pista contextualitzada

També inclou:
- diagnose_dependency   — quina dependència del graf li falta

SDK: google-genai. Variable d'entorn requerida: GEMINI_API_KEY

Sobre thinking models:
- gemini-2.5-pro (DEFAULT): thinking obligatori, latència alta, qualitat alta.
- gemini-2.5-flash: thinking opcional (aquí desactivat). Més ràpid i barat.

Robustesa:
- Retry automàtic amb exponential backoff (3 intents) per a errors transitoris
  (503 UNAVAILABLE, 429 RATE_LIMIT, 500, timeouts).
- Tota crida queda registrada al log (api_logger.py).
"""

import json
import os
import re
import time
import uuid

from google import genai
from google.genai import types

import api_logger
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MAX_TOKENS = 400

IS_THINKING_MODEL = "pro" in MODEL.lower()
TOKEN_MULTIPLIER = 10 if IS_THINKING_MODEL else 1

# Retry config
MAX_ATTEMPTS = 3
BACKOFF_BASE_S = 1.5  # 1.5s → 3s → 6s

# Errors HTTP/API que considerem retriables
RETRIABLE_PATTERNS = (
    "503", "UNAVAILABLE",
    "429", "RATE_LIMIT", "RESOURCE_EXHAUSTED",
    "500", "INTERNAL",
    "DEADLINE_EXCEEDED",
    "timeout", "Timeout",
)

# Session id per al log (un per execució del procés)
_SESSION_ID = uuid.uuid4().hex[:8]

# Callback opcional perquè la UI pugui mostrar avisos durant els retries.
# Signatura: fn(message: str). El defineix `app.py`.
_progress_callback = None


def set_progress_callback(callback):
    """Permet a la UI rebre avisos quan estem reintentant."""
    global _progress_callback
    _progress_callback = callback


def _notify(msg: str):
    if _progress_callback is not None:
        try:
            _progress_callback(msg)
        except Exception:
            pass


def _is_retriable(err: Exception) -> bool:
    s = str(err)
    return any(p in s for p in RETRIABLE_PATTERNS)


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    return _client


def _build_config(system: str, max_tokens: int, json_mode: bool, temperature: float):
    cfg = {
        "system_instruction": system,
        "max_output_tokens": max_tokens * TOKEN_MULTIPLIER,
        "temperature": temperature,
    }
    if json_mode:
        cfg["response_mime_type"] = "application/json"
    if not IS_THINKING_MODEL:
        cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    return types.GenerateContentConfig(**cfg)


def _do_call(system: str, user: str, max_tokens: int,
             json_mode: bool, temperature: float) -> str:
    """Una crida única (sense retry). Pot llançar excepció."""
    client = _get_client()
    config = _build_config(system, max_tokens, json_mode, temperature)
    response = client.models.generate_content(
        model=MODEL, contents=user, config=config,
    )
    text = response.text or ""
    if not text.strip():
        finish = "?"
        if response.candidates:
            finish = getattr(response.candidates[0], "finish_reason", "?")
        raise RuntimeError(
            f"Resposta buida del model {MODEL} (finish_reason={finish})."
        )
    return text


def _call_with_retry(function_name: str, system: str, user: str,
                     max_tokens: int, json_mode: bool,
                     temperature: float) -> str:
    """Crida amb retry exponential backoff. Loga cada intent."""
    last_error = None
    input_data = {
        "system_preview": system[:200],
        "user": user,
        "max_tokens": max_tokens,
        "json_mode": json_mode,
        "temperature": temperature,
    }

    for attempt in range(1, MAX_ATTEMPTS + 1):
        t0 = time.time()
        try:
            text = _do_call(system, user, max_tokens, json_mode, temperature)
            elapsed = time.time() - t0
            api_logger.log_call(
                session_id=_SESSION_ID, function=function_name,
                model=MODEL, attempt=attempt, ok=True,
                elapsed_s=elapsed, input_data=input_data,
                output_data={"text_preview": text[:500], "len": len(text)},
            )
            return text
        except Exception as e:
            elapsed = time.time() - t0
            err_str = str(e)
            api_logger.log_call(
                session_id=_SESSION_ID, function=function_name,
                model=MODEL, attempt=attempt, ok=False,
                elapsed_s=elapsed, input_data=input_data,
                error=err_str,
            )
            last_error = e

            if attempt < MAX_ATTEMPTS and _is_retriable(e):
                backoff = BACKOFF_BASE_S * (2 ** (attempt - 1))
                _notify(
                    f"L'API ha donat un error temporal (intent {attempt}/{MAX_ATTEMPTS}). "
                    f"Reintentant en {backoff:.0f}s..."
                )
                time.sleep(backoff)
                continue
            break

    raise RuntimeError(
        f"L'API ha fallat després de {MAX_ATTEMPTS} intents. Últim error: {last_error}"
    )


def _call_json(system: str, user: str, max_tokens: int = MAX_TOKENS,
               function_name: str = "unknown") -> str:
    return _call_with_retry(function_name, system, user, max_tokens,
                            json_mode=True, temperature=0.2)


def _call_text(system: str, user: str, max_tokens: int = MAX_TOKENS,
               function_name: str = "unknown") -> str:
    return _call_with_retry(function_name, system, user, max_tokens,
                            json_mode=False, temperature=0.4)


def _extract_json(text: str) -> dict:
    if text is None:
        return {}
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    if start == -1:
        return {}
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except Exception:
                    return {}
    return {}


# ============================================================
# Crida 1: jutjar progrés
# ============================================================
def judge_progress(prev_eq_text, new_eq_text, target_solution):
    system = (
        "You are a math tutor's classifier for linear equations at age-13 level. "
        "You receive two equivalent linear equations (proven equivalent by symbolic computation). "
        "Your only job is to decide whether the new one represents PROGRESS towards isolating x, "
        "or whether the student is just rearranging without advancing."
        "\n\nProgress means at least one of:"
        "\n - fewer x-terms (combined like terms)"
        "\n - fewer constant terms on each side"
        "\n - removed parentheses"
        "\n - cleared denominators"
        "\n - x appears on only one side now"
        "\n - the equation is closer to x = c form"
        "\n\nNon-progress means: cosmetic rearrangement, multiplied both sides by something "
        "without simplifying, expanded an already-expanded form, or restated the same equation."
        "\n\nRespond ONLY with JSON: {\"verdict\": \"progres\" | \"estancat\", \"reason\": \"<short reason in Catalan>\"}"
    )
    user = (
        f"Target solution (for context only): x = {target_solution}\n"
        f"Previous equation: {prev_eq_text}\n"
        f"New equation: {new_eq_text}\n\n"
        f"Decide: progres or estancat?"
    )
    raw = _call_json(system, user, max_tokens=200, function_name="judge_progress")
    data = _extract_json(raw)
    verdict = data.get("verdict", "progres")
    if verdict not in ("progres", "estancat"):
        verdict = "progres"
    return {"verdict": verdict, "reason": data.get("reason", "")}


# ============================================================
# Crida 2: classificar error
# ============================================================
def classify_error(original_eq_text, last_correct_step_text,
                   attempted_eq_text, error_catalog, problem_dependencies,
                   recent_errors=None):
    """
    `recent_errors` és una llista (opcional) de dicts {text, error_label}
    amb els errors anteriors d'aquesta sessió, en ordre cronològic. Permet
    a la IA detectar patrons (errors repetits del mateix tipus) i pujar la
    confiança del diagnòstic conceptual quan correspon.
    """
    catalog_str = "\n".join(f"  - {k}: {v}" for k, v in error_catalog.items())
    deps_str = ", ".join(problem_dependencies) if problem_dependencies else "(none)"

    system = (
        "You are an error classifier for a math tutor system. The student is "
        "solving a linear equation step by step. They have written an equation "
        "that is NOT equivalent to the original (the solution for x differs)."
        "\n\n"
        "YOUR TASK: classify the SPECIFIC TRANSFORMATION the student got wrong."
        "\n\n"
        "INPUTS YOU RECEIVE:"
        "\n - 'Original equation': the problem statement."
        "\n - 'Last correct step': the closest VALID equation (equivalent to "
        "the original) that the student had reached before this wrong attempt. "
        "If no valid step exists yet, this equals the original."
        "\n - 'Student's attempt': the wrong equation."
        "\n - 'Recent errors' (optional): earlier wrong attempts in this "
        "same problem with their assigned labels, in chronological order. "
        "Use them to detect PATTERNS — see rule 6 below."
        "\n\n"
        "CRITICAL CLASSIFICATION RULES:"
        "\n 1. The relevant transformation is from 'Last correct step' to "
        "'Student's attempt'. THAT is what to classify. "
        "Do NOT look at the original equation to decide the error type — "
        "the original is just context."
        "\n    Example: if 'Last correct step' is 3x - 12 = 9 and the attempt "
        "is 3x = -3, the error is in transposing -12 (kept its sign instead "
        "of flipping to +12, so the student computed 9 + (-12) = -3 instead "
        "of 9 - (-12) = 21). NOT a distributive error — distribution was "
        "already done correctly to reach 'Last correct step'."
        "\n 2. Classify by the TYPE OF MISTAKE, not by the level of the equation."
        "\n 3. Distinguish carefully:"
        "\n    - GEN_arithmetic: pure number computation mistake or typo "
        "(5*4=24, 30/5=-6, 9+12=20, copying 9 as 8 on the right-hand "
        "side, or arriving at the right MAGNITUDE with the wrong sign like "
        "writing -21 instead of 21). Use this when the STRUCTURE of the "
        "transformation is correct but a number is miscomputed or has a "
        "stray sign."
        "\n    - L1_inverse_op: confused inverse operation — applied an "
        "ADDITIVE inverse where a MULTIPLICATIVE one was needed (or vice "
        "versa). The TYPE of operation chosen is wrong."
        "\n      Canonical example: from '3x = 21' the student writes "
        "'x = 18' (subtracted 3 instead of dividing by 3 → 21-3=18). "
        "Another: from 'x + 5 = 12' writes 'x = 17' (added 5 instead of "
        "subtracting). NEVER label such cases as L1_sign_error: the sign "
        "isn't the problem, the operation is."
        "\n    - L1_sign_error: the CORRECT operation was chosen but the "
        "result has the wrong sign. Example: '5x = 30' → 'x = -6' (divided "
        "correctly in magnitude but flipped sign). Do NOT use this when the "
        "operation itself is wrong — that is L1_inverse_op."
        "\n    - L2_transpose_sign: moving a term across = without flipping "
        "its sign — student kept the original sign of the term being moved. "
        "Canonical example: '3x - 12 = 9' → '3x = -3' (kept the -12 as -12, "
        "so 9 + (-12) = -3 instead of the correct 9 + 12 = 21). The hallmark "
        "is the WRONG MAGNITUDE coming from using the wrong sign during "
        "addition. Do NOT confuse with a stray sign on the right magnitude "
        "(e.g. writing -21 when 21 is correct) — that is GEN_arithmetic."
        "\n    - L2_one_side_only: applied an operation to only ONE side of "
        "the equation, breaking equivalence. Canonical example: from "
        "'3x = 21' the student writes '3x = 7' (divided RHS by 3 correctly "
        "but kept LHS as 3x). The arithmetic on the modified side is right, "
        "but the operation wasn't done on both sides. Do NOT confuse with "
        "L1_inverse_op (where the operation TYPE is wrong) or with "
        "L2_transpose_sign (where a term moves across)."
        "\n    - L3_distribution_partial: a(b+c) computed as ab+c (forgetting "
        "one term of the distribution). ONLY use this if the wrong attempt "
        "involves a parenthesis being expanded in THIS step (i.e. 'Last "
        "correct step' still has the parenthesis and 'Student's attempt' "
        "expanded it). If the parenthesis was already gone in 'Last correct "
        "step', distribution is NOT the operation being done now."
        "\n    - L3_minus_paren: -(b+c) computed as -b+c (sign error after a minus)."
        "\n    - L4_mcm_partial: when clearing denominators, multiplied only some "
        "terms by the lcm. ONLY use this if the wrong attempt involves "
        "denominators being cleared."
        "\n 4. If 'Last correct step' has NO parenthesis or NO denominators, "
        "L3_distribution_partial and L4_mcm_partial are NOT applicable, even "
        "if the original equation had them."
        "\n 5. If you can't pinpoint the error, use GEN_other."
        "\n 6. PATTERN AWARENESS: when 'Recent errors' shows the same kind of "
        "mistake repeating (e.g. multiple L3_distribution_partial in a row, or "
        "a sequence of attempts that all fail the same operation type), this "
        "is strong evidence of a CONCEPTUAL GAP, not a slip. In such cases:"
        "\n    - Strongly prefer is_conceptual=true."
        "\n    - The new error is most likely the SAME kind as the recent ones "
        "unless the structure of the attempt clearly indicates otherwise — "
        "do not switch labels arbitrarily."
        "\n    - Phrase the message acknowledging the recurrence (e.g. 'Tornes "
        "a tenir el mateix tipus de dificultat amb…') instead of treating it "
        "as an isolated fall."
        "\n\n"
        "Error catalog (full list of valid labels):\n" + catalog_str +
        "\n\n"
        "Conceptual gap detection: if the error is conceptual (the student does "
        "not master a definition or rule) AND it matches one of the problem's "
        "dependencies, set is_conceptual=true and dep_id to that dependency id. "
        "Otherwise (procedural slip) set is_conceptual=false and dep_id=null."
        "\n\n"
        "The following labels almost ALWAYS indicate a conceptual gap. When "
        "you choose one of these AND the corresponding dependency is in the "
        "problem's dependency list, set is_conceptual=true and dep_id as listed:"
        "\n  - L3_distribution_partial → 'prop_distributiva'"
        "\n  - L3_minus_paren           → 'regla_signes_parens'"
        "\n  - L4_mcm_partial           → 'def_mcm'"
        "\n  - L4_illegal_cancel        → 'def_fraccions_equiv'"
        "\n  - L1_inverse_op            → 'operacions_inverses'"
        "\n  - L2_transpose_sign        → 'principi_equiv'"
        "\n  - L2_one_side_only         → 'principi_equiv'"
        "\nThese are NOT slips: an alumne who divides only one term of a "
        "distribution, who confuses ÷ with −, or who applies an operation "
        "to only one side of the equation, has not yet understood the "
        "underlying concept."
        "\n\n"
        "Problem dependencies for this exercise: " + deps_str + "."
        "\n\n"
        "Write a short message (1-2 sentences) in Catalan that the student "
        "will see. DO NOT reveal the correct equation or the solution. "
        "Keep the tone sober (not gamified)."
        "\n\n"
        "CONSISTENCY REQUIREMENT (very important): the short_msg MUST match "
        "the chosen error_label. The student sees the label and the message "
        "side by side, so a mismatch is confusing. Concretely:"
        "\n  - If error_label = GEN_arithmetic → talk about a computation/"
        "copy slip with a number (a stray sign, a wrong product, a typo). "
        "DO NOT mention distribution, transposition, inverse operations or "
        "any specific algebraic transformation."
        "\n  - If error_label = L1_inverse_op → mention that the inverse "
        "operation isn't the one chosen (e.g. when undoing a multiplication "
        "we divide, not subtract)."
        "\n  - If error_label = L1_sign_error → mention the sign of the result."
        "\n  - If error_label = L2_transpose_sign → mention changing sign "
        "when moving a term across the equals sign."
        "\n  - If error_label = L2_one_side_only → mention that an operation "
        "must be applied to BOTH sides, not only one."
        "\n  - If error_label = L3_distribution_partial / L3_minus_paren → "
        "mention the distributive property or the sign in front of the "
        "parenthesis."
        "\n  - If error_label = L4_* → mention denominators / lcm."
        "\nNever describe the error in terms of a transformation that did "
        "not happen in this step."
        "\n\n"
        "Respond ONLY with JSON: {"
        "\"error_label\": \"<exact id from catalog>\", "
        "\"is_conceptual\": true|false, "
        "\"dep_id\": \"<dependency id or null>\", "
        "\"short_msg\": \"<short message in Catalan>\""
        "}"
    )
    # Bloc opcional amb els errors anteriors d'aquesta sessió.
    if recent_errors:
        recent_lines = []
        for i, e in enumerate(recent_errors, start=1):
            label = e.get("error_label") or "?"
            recent_lines.append(f"  {i}. \"{e['text']}\" → labeled {label}")
        recent_block = (
            "\n\nRecent errors by this student on this problem (chronological, "
            "most recent last):\n" + "\n".join(recent_lines)
        )
    else:
        recent_block = ""

    user = (
        f"Original equation: {original_eq_text}\n"
        f"Last correct step: {last_correct_step_text}\n"
        f"Student's attempt: {attempted_eq_text}"
        f"{recent_block}\n\n"
        f"Classify the error in the transformation from 'Last correct step' "
        f"to 'Student's attempt'."
    )
    raw = _call_json(system, user, max_tokens=350, function_name="classify_error")
    data = _extract_json(raw)
    return {
        "error_label": data.get("error_label", "GEN_other"),
        "is_conceptual": bool(data.get("is_conceptual", False)),
        "dep_id": data.get("dep_id") or None,
        "short_msg": data.get("short_msg", "Hi ha un error en el pas que has escrit. Revisa-ho."),
    }


# ============================================================
# Crida 3: interpretar input
# ============================================================
def interpret_input(raw_text, prev_eq_text, original_eq_text):
    system = (
        "You are a math tutor's input interpreter for linear equations at age-13 level. "
        "The symbolic parser (SymPy) could not parse the student's input. "
        "Either: (a) the student wrote an equation with unusual notation, "
        "(b) the student wrote something that is not a mathematical equation, "
        "(c) the student wrote text describing what they would do (not an equation)."
        "\n\nIf you can reconstruct an equation, do so and judge whether it is "
        "a correct progressing step (correcte_progres), a correct but stagnant rewrite "
        "(correcte_estancat), or an error (error). "
        "If the input is not mathematical content, return verdict='no_eq'."
        "\n\nRespond ONLY with JSON: {"
        "\"verdict\": \"correcte_progres\"|\"correcte_estancat\"|\"error\"|\"no_eq\", "
        "\"reconstruction\": \"<the equation as best reconstructed, or null>\", "
        "\"short_msg\": \"<short message in Catalan; no solution reveal>\""
        "}"
    )
    user = (
        f"Original problem equation: {original_eq_text}\n"
        f"Previous step: {prev_eq_text}\n"
        f"Student raw input: {raw_text}"
    )
    raw = _call_json(system, user, max_tokens=300, function_name="interpret_input")
    data = _extract_json(raw)
    verdict = data.get("verdict", "no_eq")
    if verdict not in ("correcte_progres", "correcte_estancat", "error", "no_eq"):
        verdict = "no_eq"
    return {
        "verdict": verdict,
        "reconstruction": data.get("reconstruction"),
        "short_msg": data.get("short_msg", "No he pogut interpretar la teva resposta com a equació."),
    }


# ============================================================
# Crida 4: generar pista
# ============================================================
def generate_hint(original_eq_text, history_text, target_solution):
    system = (
        "You are a math tutor for a 13-year-old student working on linear equations. "
        "The student typed '?' to request help. "
        "Generate a SHORT, DIRECTIONAL hint in Catalan that points to the next sensible "
        "transformation, but does NOT reveal the next equation or the final answer."
        "\n\nGuidelines:"
        "\n - One or two sentences max."
        "\n - Be Socratic: a question that nudges, not an instruction."
        "\n - Sober tone (UPC pilot style, not gamified)."
        "\n - Use the target solution to verify your hint points the right direction, "
        "   but never mention it explicitly."
        "\n - Use Catalan throughout."
        "\n\nOutput ONLY the hint text, no JSON, no preamble."
    )
    user = (
        f"Original equation: {original_eq_text}\n"
        f"Student's chain so far:\n{history_text}\n"
        f"Target solution (do NOT reveal): x = {target_solution}\n\n"
        f"Write the hint."
    )
    raw = _call_text(system, user, max_tokens=150, function_name="generate_hint")
    return raw.strip()


# ============================================================
# Crida 5: exemple resolt (escalada nivell 1 — streak == 2)
# ============================================================
def generate_worked_example(last_correct_eq_text, original_eq_text,
                            concept_description, recent_wrong_attempts=None):
    """
    L'alumne s'ha equivocat dues vegades amb el mateix concepte i el
    prerequisit no l'ha desbloquejat. Genera un exemple resolt curt amb
    una equació anàloga (números diferents) que demostri concretament
    l'operació. Acaba convidant l'alumne a aplicar-ho al seu cas.

    `recent_wrong_attempts`: llista opcional dels últims intents
    equivocats de l'alumne en aquest mateix problema. Es passen com a
    ANTI-EXEMPLES: la IA ha d'evitar triar un cas la forma del qual
    coincideixi visualment amb les respostes errònies, perquè això
    reforçaria el patró equivocat.
    """
    system = (
        "You are a math tutor for a 13-year-old student stuck on a linear "
        "equation step. They have made the same conceptual mistake twice. "
        "Abstract help (a Socratic prerequisite question) hasn't unblocked "
        "them. Now show a SHORT WORKED EXAMPLE: pick an analogous equation "
        "with DIFFERENT NUMBERS where the same kind of operation is needed, "
        "solve that step explicitly, and invite the student to apply the "
        "same idea to their own equation."
        "\n\nGuidelines:"
        "\n - Catalan throughout."
        "\n - Sober tone (UPC pilot style, not gamified)."
        "\n - 2-3 short sentences max."
        "\n - Show the operation EXPLICITLY with the example numbers "
        "(e.g. '5x : 5 = 20 : 5, així x = 4')."
        "\n - DO NOT reveal the answer or any intermediate equation of the "
        "actual problem. Use a clearly different example with different "
        "numbers."
        "\n - End with an invitation like 'Ara prova el mateix amb la teva "
        "equació'."
        "\n\nCRITICAL — STRUCTURAL MIRRORING:"
        "\nThe example MUST mirror the STRUCTURAL FORM of the original "
        "equation. This is not optional — using a structurally different "
        "example may reinforce the very mistake the student is making."
        "\n - If the original has a parenthesis with subtraction like "
        "a(x − k), the example MUST also use subtraction inside parens "
        "(e.g. 2(y − 5) = 14 → 2y − 10 = 14). NEVER pick an addition example "
        "(like 2(y+5)) when the original uses subtraction: the student may "
        "have just written wrongly something like 'ax + ak' and an addition "
        "example would visually confirm their mistake."
        "\n - If the original has a parenthesis with addition like "
        "a(x + k), the example MUST also use addition inside parens."
        "\n - If the original has a negative coefficient outside (e.g. "
        "-2(x+3)), the example must mirror that minus sign too."
        "\n - For inverse-operation concepts (forms like a·x = b), pick "
        "another a·x = b with different numbers (e.g. 5y = 20 → y = 4)."
        "\n - For transposition concepts, pick an analogous case with the "
        "same sign of the term being transposed."
        "\n - For 'apply to both sides' concepts (L2_one_side_only / "
        "principi_equiv), the example must show the operation applied to "
        "BOTH sides explicitly (e.g. 4y = 20 → 4y : 4 = 20 : 4 → y = 5)."
        "\n\nANTI-EXAMPLE GUARD:"
        "\nIf the user message contains a list of 'Recent wrong attempts', "
        "you MUST avoid choosing an example whose visual form looks like any "
        "of those wrong answers. The example must CONTRADICT the wrong "
        "pattern, not coincide with it. For instance, if the student wrote "
        "'3x + 12' as a wrong answer to a parenthesis-with-subtraction "
        "problem, never produce an example that ends with 'ax + b' — that "
        "would visually validate their mistake. Pick a form that visibly "
        "produces the OPPOSITE structure."
        "\n\nOutput ONLY the worked example text, no preamble, no JSON."
    )
    if recent_wrong_attempts:
        attempts_block = (
            "\nRecent wrong attempts by this student (treat as anti-examples "
            "— do NOT pick a worked example whose visual form matches any of "
            "these):\n"
            + "\n".join(f"  - {a}" for a in recent_wrong_attempts)
        )
    else:
        attempts_block = ""

    user = (
        f"Concept the student is missing: {concept_description}\n"
        f"Original problem (do NOT solve, do NOT reuse its numbers): "
        f"{original_eq_text}\n"
        f"Student's last correct step (which is where they got stuck): "
        f"{last_correct_eq_text}"
        f"{attempts_block}\n\n"
        f"Write the worked example."
    )
    raw = _call_text(system, user, max_tokens=220,
                     function_name="generate_worked_example")
    return raw.strip()


# ============================================================
# Crida 6: pas concret directe (escalada nivell 2 — streak >= 3)
# ============================================================
def generate_concrete_step(last_correct_eq_text, original_eq_text,
                           concept_description, recent_wrong_attempts=None):
    """
    L'alumne ha fallat tres o més vegades el mateix concepte; ni el
    prereq ni l'exemple resolt han funcionat. Indica explícitament
    quina operació ha de fer al pas següent sobre la SEVA equació, però
    encara li deixem fer l'aritmètica perquè conservi sentit d'agència.

    `recent_wrong_attempts`: llista opcional dels intents equivocats
    recents. Es passen perquè la IA pugui fer una instrucció dirigida
    que contradigui explícitament el patró equivocat de l'alumne (per
    exemple: "no restis 3 com has provat abans, divideix per 3").
    """
    system = (
        "You are a math tutor for a 13-year-old student. They are stuck: "
        "they have failed the same concept three or more times in a row. "
        "First the feedback didn't help, then a Socratic prerequisite "
        "didn't help, then a worked example didn't help. Now we need to "
        "be very direct."
        "\n\nState EXPLICITLY the next operation they should perform on "
        "their actual equation, and ask them to compute it. Reveal the "
        "operation but make THEM do the arithmetic so they keep agency. "
        "DO NOT give the final solution to the original problem."
        "\n\nGuidelines:"
        "\n - Catalan throughout."
        "\n - Sober, encouraging (not patronising) tone."
        "\n - 1-2 sentences."
        "\n - Refer to the operation in concrete terms ('divideix els dos "
        "costats per 3', 'resta 5 als dos costats')."
        "\n - End by asking them to write the resulting equation."
        "\n - If the user message includes 'Recent wrong attempts', you may "
        "briefly contrast the correct operation with what they've been "
        "trying (e.g. 'no és restar com has provat, sinó dividir'). Be "
        "concise and not accusatory."
        "\n\nOutput ONLY the instruction text, no preamble, no JSON."
    )
    if recent_wrong_attempts:
        attempts_block = (
            "\nRecent wrong attempts by this student:\n"
            + "\n".join(f"  - {a}" for a in recent_wrong_attempts)
        )
    else:
        attempts_block = ""

    user = (
        f"Concept the student is missing: {concept_description}\n"
        f"Original problem: {original_eq_text}\n"
        f"Student's last correct equation: {last_correct_eq_text}"
        f"{attempts_block}\n\n"
        f"Write the directive instruction for the next step."
    )
    raw = _call_text(system, user, max_tokens=180,
                     function_name="generate_concrete_step")
    return raw.strip()


# ============================================================
# Auxiliar: diagnosticar dependència
# ============================================================
def diagnose_dependency(prev_eq_text, attempted_eq_text, candidate_deps):
    if not candidate_deps:
        return None
    deps_str = ", ".join(candidate_deps)
    system = (
        "You are a diagnostic classifier. Given a wrong transformation by a student "
        "and a list of candidate dependency concepts, identify which one is most likely "
        "missing. Respond ONLY with JSON: {\"dep_id\": \"<one of the listed ids or null>\"}"
        f"\n\nCandidate dependencies: {deps_str}"
    )
    user = (
        f"Previous: {prev_eq_text}\n"
        f"Student wrote: {attempted_eq_text}"
    )
    raw = _call_json(system, user, max_tokens=80, function_name="diagnose_dependency")
    data = _extract_json(raw)
    dep = data.get("dep_id")
    return dep if dep in candidate_deps else None
