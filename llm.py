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

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")
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
                   attempted_eq_text, error_catalog, problem_dependencies):
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
        "\n\n"
        "CRITICAL CLASSIFICATION RULES:"
        "\n 1. The relevant transformation is from 'Last correct step' to "
        "'Student's attempt'. THAT is what to classify. "
        "Do NOT look at the original equation to decide the error type — "
        "the original is just context."
        "\n    Example: if 'Last correct step' is 3x - 12 = 9 and the attempt "
        "is 3x = -21, the error is in transposing -12 (sign error in "
        "transposition), NOT in the distributive property — distribution was "
        "already done correctly to reach 'Last correct step'."
        "\n 2. Classify by the TYPE OF MISTAKE, not by the level of the equation."
        "\n 3. Distinguish carefully:"
        "\n    - GEN_arithmetic: pure number computation mistake where the OPERATION "
        "type is correct but the resulting number is wrong (e.g. 5*4=24, 9+12=20). "
        "The student did the right thing but computed the number incorrectly."
        "\n    - L1_inverse_op: the student used the WRONG TYPE of operation entirely. "
        "Key example: 3x=21 → x=18 (subtracted 3 instead of dividing by 3). "
        "Or: 3x=21 → x=63 (multiplied instead of dividing). "
        "Use this whenever the student confused +/-, or confused ×/÷."
        "\n    - L1_sign_error: the student used the correct operation type but got "
        "the WRONG SIGN on the result. "
        "Example: 3x=21 → x=−7 (divided by 3 correctly but negated the result). "
        "Example: x+5=10 → x=15 (subtracted correctly but kept wrong sign). "
        "The absolute value may be right, but the sign is flipped."
        "\n    - L2_transpose_sign: moving a term across = without flipping its "
        "sign. Common case: '3x - 12 = 9' → '3x = -21' (kept the -12 as -12 "
        "instead of flipping it to +12)."
        "\n    - L3_distribution_partial: a(b+c) computed as ab+c (forgetting "
        "one term of the distribution). ONLY use this if the wrong attempt "
        "involves a parenthesis being expanded."
        "\n    - L3_minus_paren: -(b+c) computed as -b+c (sign error after a minus)."
        "\n    - L4_mcm_partial: when clearing denominators, multiplied only some "
        "terms by the lcm. ONLY use this if the wrong attempt involves "
        "denominators being cleared."
        "\n 4. If 'Last correct step' has NO parenthesis or NO denominators, "
        "L3_distribution_partial and L4_mcm_partial are NOT applicable, even "
        "if the original equation had them."
        "\n 5. If you can't pinpoint the error, use GEN_other."
        "\n\n"
        "Error catalog (full list of valid labels):\n" + catalog_str +
        "\n\n"
        "Conceptual gap detection: if the error is conceptual (the student does "
        "not master a definition or rule) AND it matches one of the problem's "
        "dependencies, set is_conceptual=true and dep_id to that dependency id. "
        "Otherwise (procedural slip) set is_conceptual=false and dep_id=null. "
        "Problem dependencies for this exercise: " + deps_str + "."
        "\n\n"
        "CRITICAL — short_msg must match error_label exactly:"
        "\n  - GEN_arithmetic → describe a numerical calculation error only. "
        "NEVER mention distributive property, parentheses expansion, sign-change, "
        "or operation type."
        "\n  - L1_inverse_op → say the student used the wrong operation "
        "(e.g. 'Has restat en lloc de dividir')."
        "\n  - L1_sign_error → say the student got the sign wrong in the result "
        "(e.g. 'El resultat de la divisió té el signe incorrecte')."
        "\n  - L3_distribution_partial → mention the distributive property."
        "\n  - L2_transpose_sign → mention forgetting to change the sign when "
        "moving a term to the other side."
        "\n  Do NOT write a generic message that could fit multiple error types."
        "\n\n"
        "Write a short message (1-2 sentences) in Catalan that the student "
        "will see. DO NOT reveal the correct equation or the solution. "
        "Keep the tone sober (not gamified)."
        "\n\n"
        "Respond ONLY with JSON: {"
        "\"error_label\": \"<exact id from catalog>\", "
        "\"is_conceptual\": true|false, "
        "\"dep_id\": \"<dependency id or null>\", "
        "\"short_msg\": \"<short message in Catalan>\""
        "}"
    )
    user = (
        f"Original equation: {original_eq_text}\n"
        f"Last correct step: {last_correct_step_text}\n"
        f"Student's attempt: {attempted_eq_text}\n\n"
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
