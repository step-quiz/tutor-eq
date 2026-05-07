"""
Client a l'API d'Anthropic. Implementa les 4 crides definides a la Fase 0:

1. judge_progress       — equació equivalent: avança o estanca?
2. classify_error       — equació no equivalent: quin error té?
3. interpret_input      — SymPy no parseja: què ha escrit l'alumne?
4. generate_hint        — l'alumne ha escrit '?': pista contextualitzada

També inclou:
- diagnose_dependency   — quina dependència del graf li falta
  (subcrida usada dins classify_error si l'error és conceptual)

Tots els prompts són en anglès (Fase 0, §1). El text que torna a l'alumne
es genera en català per als casos de pista.

Variable d'entorn requerida: ANTHROPIC_API_KEY
"""

import json
import os
import re
from anthropic import Anthropic

# Model per defecte. L'usuari pot canviar-lo si Anthropic actualitza els noms.
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")
MAX_TOKENS = 400

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Anthropic()  # llegeix ANTHROPIC_API_KEY de l'entorn
    return _client


def _call(system: str, user: str, max_tokens: int = MAX_TOKENS) -> str:
    """Crida a l'API i retorna el text de la resposta."""
    client = _get_client()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    # extracció determinista del primer bloc de text
    return msg.content[0].text


def _extract_json(text: str) -> dict:
    """
    Extreu el primer bloc JSON del text retornat pel model.
    Tolera embolcalls amb ```json ... ``` o text al voltant.
    """
    text = text.strip()
    # Treu ``` si hi és
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Busca el primer { i l'aparellat
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
# Crida 1: jutjar progrés (equació equivalent)
# ============================================================
def judge_progress(prev_eq_text: str,
                   new_eq_text: str,
                   target_solution: str) -> dict:
    """
    L'alumne ha escrit una equació equivalent a l'anterior. Avança o no?

    Retorn: {'verdict': 'progres'|'estancat', 'reason': str (curt)}
    """
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
    raw = _call(system, user, max_tokens=200)
    data = _extract_json(raw)
    verdict = data.get("verdict", "estancat")
    if verdict not in ("progres", "estancat"):
        verdict = "estancat"
    return {"verdict": verdict, "reason": data.get("reason", "")}


# ============================================================
# Crida 2: classificar error (equació no equivalent)
# ============================================================
def classify_error(prev_eq_text: str,
                   attempted_eq_text: str,
                   error_catalog: dict,
                   problem_dependencies: list) -> dict:
    """
    L'alumne ha escrit una equació NO equivalent. Identifica l'error.

    Retorn: {'error_label': str, 'is_conceptual': bool, 'dep_id': str|None,
             'short_msg': str (per mostrar a l'alumne, en català, sense revelar la solució)}
    """
    catalog_str = "\n".join(f"  - {k}: {v}" for k, v in error_catalog.items())
    deps_str = ", ".join(problem_dependencies) if problem_dependencies else "(none)"

    system = (
        "You are a math tutor's error classifier for linear equations at age-13 level. "
        "The student wrote an equation that is NOT equivalent to the previous one. "
        "Identify the most likely error from the catalog, and decide whether it is a "
        "PROCEDURAL slip (computation/transposition mistake the student knows how to fix) "
        "or a CONCEPTUAL gap (a definition or rule they don't really master)."
        "\n\nError catalog:\n" + catalog_str +
        "\n\nIf the error is conceptual and matches one of the problem's dependencies, "
        "set is_conceptual=true and dep_id to that dependency id. "
        "Problem dependencies for context: " + deps_str + "."
        "\n\nWrite a short message in Catalan that the student will see. "
        "DO NOT reveal the correct equation or the solution. "
        "Keep the tone sober (this is for a UPC pilot, not gamified)."
        "\n\nRespond ONLY with JSON: {"
        "\"error_label\": \"<id from catalog>\", "
        "\"is_conceptual\": true|false, "
        "\"dep_id\": \"<dependency id or null>\", "
        "\"short_msg\": \"<short message in Catalan>\""
        "}"
    )
    user = (
        f"Previous equation: {prev_eq_text}\n"
        f"Student's attempt: {attempted_eq_text}\n\n"
        f"Classify the error."
    )
    raw = _call(system, user, max_tokens=350)
    data = _extract_json(raw)
    return {
        "error_label": data.get("error_label", "GEN_other"),
        "is_conceptual": bool(data.get("is_conceptual", False)),
        "dep_id": data.get("dep_id") or None,
        "short_msg": data.get("short_msg", "Hi ha un error en el pas que has escrit. Revisa-ho."),
    }


# ============================================================
# Crida 3: interpretar input (SymPy no parseja)
# ============================================================
def interpret_input(raw_text: str,
                    prev_eq_text: str,
                    original_eq_text: str) -> dict:
    """
    SymPy no ha pogut parsejar l'input. Demana a la IA què interpreta.

    Retorn: {'verdict': 'correcte_progres'|'correcte_estancat'|'error'|'no_eq',
             'reconstruction': str|None,
             'short_msg': str}
    """
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
    raw = _call(system, user, max_tokens=300)
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
# Crida 4: generar pista contextualitzada
# ============================================================
def generate_hint(original_eq_text: str,
                  history_text: str,
                  target_solution: str) -> str:
    """
    L'alumne ha demanat ajuda amb '?'. Genera pista que NO reveli la solució.
    """
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
    raw = _call(system, user, max_tokens=150)
    return raw.strip()


# ============================================================
# (Opcional) Crida auxiliar: diagnosticar dependència
# ============================================================
def diagnose_dependency(prev_eq_text: str,
                        attempted_eq_text: str,
                        candidate_deps: list) -> str | None:
    """
    Subcrida (en cas que classify_error no hagi pogut decidir-ho).
    Retorna l'id d'una dependència del graf o None.
    """
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
    raw = _call(system, user, max_tokens=80)
    data = _extract_json(raw)
    dep = data.get("dep_id")
    return dep if dep in candidate_deps else None
