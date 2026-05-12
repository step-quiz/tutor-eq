"""
Invariants de l'estat de sessió del tutor.

Aquest mòdul defineix una única funció (`check_state_invariants`) que, donat un
`state` retornat per `tutor.process_turn`, verifica que les propietats
estructurals que tot estat ha de complir siguin certes. Si alguna falla, llança
`InvariantViolation` amb un missatge concret que indica quin invariant ha fallat
i amb quin context (label).

Filosofia: aquests invariants són barats (només operacions O(n) trivials sobre
diccionaris ja existents), per tant es poden executar a tots els torns sense
cost rellevant. La idea és atrapar inconsistències que altrament només
es descobririen analitzant rastres setmanes després.

Es poden desactivar amb la variable d'entorn `TUTOR_INVARIANTS=off`. Recomanat
NO desactivar-los en producció: si un invariant falla, l'usuari té dret a
trobar-se amb un crash visible enlloc d'una conversa progressivament
inconsistent.
"""

from __future__ import annotations

import os


# Constants importades de tutor.py (les declarem aquí també per evitar import
# circular: tutor.py importa invariants.py, no a l'inrevés).
MAX_BACKTRACK_DEPTH = 2
MAX_INAPPROPRIATE_WARNINGS = 3

VALID_VERDICTS_FINAL = {None, "resolt", "abandonat", "suspes_us_inadequat"}
VALID_STEP_VERDICTS = {
    "inicial", "correcte_progres", "correcte_estancat",
    "error", "no_math",
}


class InvariantViolation(AssertionError):
    """Es llança quan un invariant de l'estat no es compleix."""


def _enabled() -> bool:
    return os.environ.get("TUTOR_INVARIANTS", "on").lower() != "off"


def check_state_invariants(state: dict, label: str = "") -> None:
    """
    Verifica tots els invariants de l'estat de sessió. Llança InvariantViolation
    a la primera violació amb un missatge que identifica l'invariant i el
    context.

    `label`: cadena lliure que indica des d'on s'ha cridat (p.ex. "process_turn",
    "evaluate_step"). Apareix als missatges d'error.
    """
    if not _enabled():
        return

    def fail(name: str, detail: str) -> None:
        ctx = f"[{label}] " if label else ""
        raise InvariantViolation(
            f"{ctx}invariant {name!r} violat: {detail}"
        )

    # --- Estructura mínima ---
    if not isinstance(state, dict):
        fail("state_is_dict", f"state no és un dict (és {type(state).__name__})")

    required_keys = {
        "session_id", "student_id", "problem_id", "problem", "history",
        "hints_requested", "stagnation_consecutive", "stagnation_max",
        "stagnation_total", "backtrack_count", "backtrack_depth_max",
        "discrepancies", "inappropriate_warnings", "active_prereq",
        "active_prereq_depth", "concept_failure_streak",
        "pending_proactive_offer", "verdict_final", "messages",
    }
    missing = required_keys - set(state.keys())
    if missing:
        fail("state_keys", f"claus a faltar: {sorted(missing)}")

    # --- History ---
    hist = state["history"]
    if not isinstance(hist, list) or len(hist) == 0:
        fail("history_non_empty", f"history és buida o no és llista ({type(hist)})")

    # step numbers han de ser 0, 1, 2, ... contigus
    for expected_step, h in enumerate(hist):
        if h.get("step") != expected_step:
            fail("history_step_contiguous",
                 f"posició {expected_step}: step={h.get('step')} (esperat {expected_step})")

    # primer pas és sempre "inicial"
    if hist[0].get("verdict") != "inicial":
        fail("history_initial_verdict",
             f"primer pas té verdict={hist[0].get('verdict')!r} (esperat 'inicial')")

    # cada veredicte és vàlid
    for i, h in enumerate(hist):
        v = h.get("verdict")
        if v not in VALID_STEP_VERDICTS:
            fail("history_verdict_valid",
                 f"step {i} té verdict={v!r} desconegut")

    # error_label només és not-None si verdict és error o no_math
    for i, h in enumerate(hist):
        v = h.get("verdict")
        lbl = h.get("error_label")
        if lbl is not None and v not in ("error", "no_math"):
            fail("history_error_label_consistency",
                 f"step {i}: verdict={v!r} però error_label={lbl!r}")

    # --- Comptadors no-negatius ---
    for k in ("stagnation_consecutive", "stagnation_max", "stagnation_total",
              "backtrack_count", "backtrack_depth_max",
              "inappropriate_warnings", "active_prereq_depth"):
        v = state.get(k)
        if not isinstance(v, int) or v < 0:
            fail(f"counter_{k}_non_neg",
                 f"{k}={v!r} (s'esperava enter ≥ 0)")

    # --- Stagnation: invariants entre comptadors ---
    sc = state["stagnation_consecutive"]
    sm = state["stagnation_max"]
    st = state["stagnation_total"]
    if sm < sc:
        fail("stagnation_max_ge_consecutive",
             f"stagnation_max={sm} < stagnation_consecutive={sc}")
    if st < sm:
        fail("stagnation_total_ge_max",
             f"stagnation_total={st} < stagnation_max={sm}")

    # --- Prereq depth dins de límits i consistent amb active_prereq ---
    depth = state["active_prereq_depth"]
    active = state["active_prereq"]
    if depth > MAX_BACKTRACK_DEPTH:
        fail("prereq_depth_max",
             f"active_prereq_depth={depth} > MAX_BACKTRACK_DEPTH={MAX_BACKTRACK_DEPTH}")
    if active is None and depth != 0:
        fail("prereq_consistency_none",
             f"active_prereq=None però active_prereq_depth={depth}")
    if active is not None and depth == 0:
        fail("prereq_consistency_active",
             f"active_prereq={active!r} però active_prereq_depth=0")

    # backtrack_depth_max ha de ser ≥ depth actual (és el màxim històric)
    if state["backtrack_depth_max"] < depth:
        fail("backtrack_depth_max_monotone",
             f"backtrack_depth_max={state['backtrack_depth_max']} < depth actual={depth}")

    # backtrack_count ≥ backtrack_depth_max (cada profunditat ve d'un retrocés)
    if state["backtrack_count"] < state["backtrack_depth_max"]:
        fail("backtrack_count_ge_depth_max",
             f"backtrack_count={state['backtrack_count']} < "
             f"backtrack_depth_max={state['backtrack_depth_max']}")

    # --- verdict_final ---
    vf = state["verdict_final"]
    if vf not in VALID_VERDICTS_FINAL:
        fail("verdict_final_valid",
             f"verdict_final={vf!r} no és cap valor vàlid")

    # Implicació: si suspes, ha d'haver-hi prou avisos.
    if vf == "suspes_us_inadequat":
        if state["inappropriate_warnings"] < MAX_INAPPROPRIATE_WARNINGS:
            fail("suspes_requires_warnings",
                 f"verdict_final='suspes_us_inadequat' però "
                 f"inappropriate_warnings={state['inappropriate_warnings']} "
                 f"< {MAX_INAPPROPRIATE_WARNINGS}")

    # --- concept_failure_streak: dict de strings → enters no-negatius ---
    streaks = state["concept_failure_streak"]
    if not isinstance(streaks, dict):
        fail("streaks_dict",
             f"concept_failure_streak no és dict ({type(streaks).__name__})")
    for k, v in streaks.items():
        if not isinstance(k, str) or not isinstance(v, int) or v < 0:
            fail("streaks_entries",
                 f"entrada invàlida: {k!r}={v!r}")

    # --- hints_requested, discrepancies, messages: són llistes ---
    for k in ("hints_requested", "discrepancies", "messages"):
        if not isinstance(state[k], list):
            fail(f"{k}_is_list",
                 f"{k} no és llista ({type(state[k]).__name__})")
