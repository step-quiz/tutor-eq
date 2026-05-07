"""
Client a l'API de Google Gemini. Implementa les 4 crides definides a la Fase 0:

1. judge_progress       — equació equivalent: avança o estanca?
2. classify_error       — equació no equivalent: quin error té?
3. interpret_input      — SymPy no parseja: què ha escrit l'alumne?
4. generate_hint        — l'alumne ha escrit '?': pista contextualitzada

També inclou:
- diagnose_dependency   — quina dependència del graf li falta

SDK: google-genai (l'SDK unificat que reemplaça google-generativeai, deprecat).
Variable d'entorn requerida: GEMINI_API_KEY

Sobre thinking models (IMPORTANT):
- gemini-2.5-flash: thinking opcional. Aquí el desactivem (thinking_budget=0)
  per a màxima fiabilitat amb max_output_tokens petits.
- gemini-2.5-pro: thinking obligatori (no es pot desactivar). Si l'usuari
  el tria, augmentem max_output_tokens automàticament per donar marge.
"""

import json
import os
import re

from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MAX_TOKENS = 400

# Pro és thinking model obligatori → necessita molt més pressupost
IS_THINKING_MODEL = "pro" in MODEL.lower()
TOKEN_MULTIPLIER = 10 if IS_THINKING_MODEL else 1

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    return _client


def _build_config(system: str, max_tokens: int, json_mode: bool, temperature: float):
    """Construeix la configuració, gestionant thinking segons el model."""
    cfg = {
        "system_instruction": system,
        "max_output_tokens": max_tokens * TOKEN_MULTIPLIER,
        "temperature": temperature,
    }
    if json_mode:
        cfg["response_mime_type"] = "application/json"
    if not IS_THINKING_MODEL:
        # Flash: desactivem thinking per tenir respostes ràpides i fiables
        cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    # Pro: thinking és obligatori; el budget ja queda absorbit pel multiplicador
    return types.GenerateContentConfig(**cfg)


def _call_json(system: str, user: str, max_tokens: int = MAX_TOKENS) -> str:
    client = _get_client()
    config = _build_config(system, max_tokens, json_mode=True, temperature=0.2)
    response = client.models.generate_content(
        model=MODEL, contents=user, config=config,
    )
    text = response.text or ""
    if not text.strip():
        finish = getattr(response.candidates[0], "finish_reason", "?") if response.candidates else "?"
        raise RuntimeError(
            f"Resposta buida del model {MODEL} (finish_reason={finish}). "
            "Si fas servir gemini-2.5-pro, prova amb gemini-2.5-flash, "
            "que és més robust per a respostes curtes estructurades."
        )
    return text


def _call_text(system: str, user: str, max_tokens: int = MAX_TOKENS) -> str:
    client = _get_client()
    config = _build_config(system, max_tokens, json_mode=False, temperature=0.4)
    response = client.models.generate_content(
        model=MODEL, contents=user, config=config,
    )
    text = response.text or ""
    if not text.strip():
        finish = getattr(response.candidates[0], "finish_reason", "?") if response.candidates else "?"
        raise RuntimeError(
            f"Resposta buida del model {MODEL} (finish_reason={finish}). "
            "Si fas servir gemini-2.5-pro, prova amb gemini-2.5-flash."
        )
    return text


def _extract_json(text: str) -> dict:
    """Amb response_mime_type='application/json' Gemini retorna JSON net."""
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
    raw = _call_json(system, user, max_tokens=200)
    data = _extract_json(raw)
    verdict = data.get("verdict", "progres")  # default canviat: si JSON arriba mal, suposem progrés
    if verdict not in ("progres", "estancat"):
        verdict = "progres"
    return {"verdict": verdict, "reason": data.get("reason", "")}


# ============================================================
# Crida 2: classificar error
# ============================================================
def classify_error(prev_eq_text, attempted_eq_text, error_catalog, problem_dependencies):
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
    raw = _call_json(system, user, max_tokens=350)
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
    raw = _call_json(system, user, max_tokens=300)
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
    raw = _call_text(system, user, max_tokens=150)
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
    raw = _call_json(system, user, max_tokens=80)
    data = _extract_json(raw)
    dep = data.get("dep_id")
    return dep if dep in candidate_deps else None
