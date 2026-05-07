"""
Lògica nuclear del tutor.

Aquest mòdul és l'únic que coneix la "màquina d'estats" de la sessió.
No depèn de Streamlit (es podria provar des d'un script o des d'un test).

Funció principal: process_turn(state, raw_input) → updated state.
"""

import json
import time
from datetime import datetime, timezone

import problems as PB
import verifier as V
import llm as L


# Profunditat màxima de retrocés a prerequisits (Fase 0, §3)
MAX_BACKTRACK_DEPTH = 2

# Avisos consecutius màxims abans de suspendre per ús inadequat (Fase 0, §11)
MAX_INAPPROPRIATE_WARNINGS = 3


# ------------------------------------------------------------
# Construcció d'un estat nou
# ------------------------------------------------------------
def new_session_state(problem_id: str, student_id: str = "professor_test") -> dict:
    """Crea l'estat inicial d'una sessió per a un problema."""
    problem = PB.get_problem(problem_id)
    return {
        "student_id": student_id,
        "problem_id": problem_id,
        "problem": problem,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "started_at_ts": time.time(),
        # Cadena d'equacions: cada element és un dict
        # {step, text, parsed, verdict, error_label, ts}
        "history": [
            {
                "step": 0,
                "text": problem["equacio_text"],
                "parsed_ok": True,
                "verdict": "inicial",
                "error_label": None,
                "ts": time.time(),
            }
        ],
        "hints_requested": [],          # llista d'índexs de torn on s'ha demanat ?
        "stagnation_consecutive": 0,
        "stagnation_max": 0,
        "stagnation_total": 0,
        "backtrack_count": 0,
        "backtrack_depth_max": 0,
        "discrepancies": [],            # entrades amb !text
        "inappropriate_warnings": 0,
        "active_prereq": None,          # PRE-XXX si estem en una sessió de prerequisit
        "active_prereq_depth": 0,
        "pending_proactive_offer": False,
        "verdict_final": None,          # "resolt" | "abandonat" | "suspes_us_inadequat"
        "messages": [],                 # missatges per mostrar a la UI (per torn)
        "last_input_was_question_mark": False,
    }


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _last_step(state: dict) -> dict:
    return state["history"][-1]


def _last_correct_step_text(state: dict) -> str:
    """
    Retorna el text del darrer pas correcte (correcte_progres o inicial).
    Si no n'hi ha cap, retorna l'enunciat. Usat per al judici de progrés
    quan el pas previ és un error: prenem com a referència el darrer estat
    "vàlid" de la resolució, no l'estat erroni.
    """
    for h in reversed(state["history"]):
        if h["verdict"] in ("correcte_progres", "inicial"):
            return h["text"]
    return state["problem"]["equacio_text"]


def _push_msg(state, kind: str, text: str):
    """
    kind: 'system' | 'feedback' | 'hint' | 'warning' | 'prereq' | 'discrepancy'
    """
    state["messages"].append({"kind": kind, "text": text, "ts": time.time()})


def _record_step(state, text, parsed_ok, verdict, error_label=None):
    step_no = len(state["history"])
    state["history"].append({
        "step": step_no,
        "text": text,
        "parsed_ok": parsed_ok,
        "verdict": verdict,
        "error_label": error_label,
        "ts": time.time(),
    })


def _history_text_for_prompt(state) -> str:
    """Cadena d'equacions per al prompt de generate_hint."""
    return "\n".join(
        f"  {i}. {h['text']}" for i, h in enumerate(state["history"])
    )


# ------------------------------------------------------------
# Detecció de senyals d'escapament (Fase 0, §5)
# ------------------------------------------------------------
def parse_escape_signal(raw: str) -> dict:
    """
    Retorna un dict {'kind': str, 'payload': str|None}
    kind ∈ {'normal', 'help', 'discrepancy', 'exit'}
    """
    s = (raw or "").strip()
    if s in ("!!", "exit", ":q"):
        return {"kind": "exit", "payload": None}
    if s == "?":
        return {"kind": "help", "payload": None}
    if s.startswith("!") and len(s) > 1:
        return {"kind": "discrepancy", "payload": s[1:].strip()}
    return {"kind": "normal", "payload": s}


# ------------------------------------------------------------
# Processament d'un torn complet
# ------------------------------------------------------------
def process_turn(state: dict, raw_input: str) -> dict:
    """
    Punt d'entrada únic. Modifica state in-place i retorna state.
    Tota la lògica de classificació, retrocés, estancaments, etc., passa aquí.
    """
    # Reset dels missatges de UI per al nou torn
    state["messages"] = []

    # 1. Senyals d'escapament
    sig = parse_escape_signal(raw_input)

    if sig["kind"] == "exit":
        state["verdict_final"] = "abandonat"
        _push_msg(state, "system", "Sessió tancada per l'alumne. Rastre guardat.")
        return state

    if sig["kind"] == "discrepancy":
        state["discrepancies"].append({
            "step_after": len(state["history"]) - 1,
            "text_alumne": sig["payload"],
            "ts": time.time(),
        })
        _push_msg(state, "discrepancy",
                  "Discrepància registrada per a revisió docent. La sessió continua.")
        return state

    if sig["kind"] == "help":
        return _handle_help(state)

    # 2. Si estem en una sessió de prerequisit, gestionar-ho a part
    if state["active_prereq"] is not None:
        return _process_prereq_turn(state, sig["payload"])

    # 3. Detecció determinista d'ús inadequat
    if not V.has_math_content(sig["payload"]):
        return _handle_inappropriate(state, sig["payload"])
    # Reset del comptador si l'input torna a ser matemàtic
    state["inappropriate_warnings"] = 0

    # 4. Avaluació amb SymPy → IA
    return _evaluate_equation_step(state, sig["payload"])


# ------------------------------------------------------------
# Subflux: avaluació d'una equació (camí principal)
# ------------------------------------------------------------
def _evaluate_equation_step(state: dict, raw_text: str) -> dict:
    last = _last_step(state)
    new_eq = V.parse_equation(raw_text)
    original_text = state["problem"]["equacio_text"]
    original_eq = V.parse_equation(original_text)
    target_sol = str(state["problem"]["solucio"])

    # Cas error_format: SymPy no parseja
    if new_eq is None:
        try:
            ia = L.interpret_input(raw_text, last["text"], original_text)
        except Exception as e:
            _push_msg(state, "warning", f"Error de connexió amb la IA: {e}")
            return state

        if ia["verdict"] == "no_eq":
            return _handle_inappropriate(state, raw_text, ia_already_judged=True)

        text_to_record = ia.get("reconstruction") or raw_text
        verdict_map = {
            "correcte_progres": "correcte_progres",
            "correcte_estancat": "correcte_estancat",
            "error": "error",
        }
        v = verdict_map.get(ia["verdict"], "error")
        _record_step(state, text_to_record, parsed_ok=False, verdict=v)
        _push_msg(state, "feedback", f"[Reconstruït] {ia['short_msg']}")
        _post_verdict_bookkeeping(state, v, original_text)
        return state

    # IMPORTANT: comparem amb l'equació ORIGINAL, no amb la prèvia.
    # Així, si un pas anterior va ser erroni, un pas correcte posterior
    # rescata l'alumne. L'equivalència és una propietat absoluta del
    # problema, no relativa al pas previ (que pot estar mal).
    equivalent = V.equations_equivalent(new_eq, original_eq)

    if equivalent:
        # Cas trivial: ha repetit literalment l'última
        if V.is_same_text(last["text"], raw_text):
            _record_step(state, raw_text, parsed_ok=True, verdict="correcte_estancat")
            _push_msg(state, "feedback",
                      "Has tornat a escriure la mateixa equació. No avances.")
            _post_verdict_bookkeeping(state, "correcte_estancat", original_text)
            return state

        # Comprovació determinista de terminal:
        # si x = c i c és la solució correcta, problema resolt sense IA.
        if V.is_terminal(new_eq):
            sol = V.solve_for_x(new_eq)
            if str(sol) == target_sol:
                _record_step(state, raw_text, parsed_ok=True,
                             verdict="correcte_progres")
                state["verdict_final"] = "resolt"
                _push_msg(state, "feedback",
                          f"Correcte. x = {sol}. Problema resolt.")
                return state

        # Per al judici de progrés sí que comparem amb la prèvia
        # (té sentit pedagògicament: estem avançant respecte d'on érem?).
        # Si la prèvia va ser un error, prenem com a referència de progrés
        # el darrer pas correcte (o l'enunciat).
        ref_text = _last_correct_step_text(state)
        try:
            jp = L.judge_progress(ref_text, raw_text, target_sol)
        except Exception as e:
            _push_msg(state, "warning", f"Error de connexió amb la IA: {e}")
            return state

        v = "correcte_progres" if jp["verdict"] == "progres" else "correcte_estancat"
        _record_step(state, raw_text, parsed_ok=True, verdict=v)

        if v == "correcte_progres":
            _push_msg(state, "feedback", f"Correcte. {jp.get('reason','')}".strip())
        else:
            _push_msg(state, "feedback",
                      "L'equació és correcta, però no t'acosta més a la solució. "
                      f"{jp.get('reason','')}".strip())

        _post_verdict_bookkeeping(state, v, original_text)
        return state

    # No equivalent a l'original: és un error
    try:
        ce = L.classify_error(
            original_text, raw_text,
            PB.ERROR_CATALOG,
            state["problem"]["dependencies"],
        )
    except Exception as e:
        _push_msg(state, "warning", f"Error de connexió amb la IA: {e}")
        return state

    _record_step(state, raw_text, parsed_ok=True,
                 verdict="error", error_label=ce["error_label"])
    _push_msg(state, "feedback", ce["short_msg"])

    # Si és conceptual i tenim prerequisit, fer retrocés
    if ce["is_conceptual"] and ce["dep_id"]:
        dep = PB.get_dependency(ce["dep_id"])
        if dep and state["active_prereq_depth"] < MAX_BACKTRACK_DEPTH:
            _start_prereq(state, dep["prerequisite"], ce["dep_id"])

    _post_verdict_bookkeeping(state, "error", original_text)
    return state


# ------------------------------------------------------------
# Comptabilitat post-veredicte: estancaments, ofertes proactives
# ------------------------------------------------------------
def _post_verdict_bookkeeping(state, verdict, original_text):
    if verdict == "correcte_estancat":
        state["stagnation_consecutive"] += 1
        state["stagnation_total"] += 1
        if state["stagnation_consecutive"] > state["stagnation_max"]:
            state["stagnation_max"] = state["stagnation_consecutive"]
        # Oferta proactiva al 2n estancament consecutiu
        if state["stagnation_consecutive"] >= 2 and not state["pending_proactive_offer"]:
            state["pending_proactive_offer"] = True
            _push_msg(state, "system",
                      "Sembla que estàs donant voltes. Si vols una pista, escriu  ?  .")
    else:
        # Reset si surt de l'estancament
        state["stagnation_consecutive"] = 0
        state["pending_proactive_offer"] = False


# ------------------------------------------------------------
# Subflux: '?' → pista contextualitzada
# ------------------------------------------------------------
def _handle_help(state):
    if state["active_prereq"] is not None:
        # Pista al context del prerequisit (simple)
        prereq = PB.get_prerequisite(state["active_prereq"])
        _push_msg(state, "hint", prereq.get("explanation",
                  "Pensa en la definició del concepte."))
        state["hints_requested"].append({
            "step_after": len(state["history"]) - 1,
            "context": "prerequisit",
            "ts": time.time(),
        })
        return state

    # Pista normal contextualitzada via IA
    try:
        hint = L.generate_hint(
            state["problem"]["equacio_text"],
            _history_text_for_prompt(state),
            str(state["problem"]["solucio"]),
        )
    except Exception as e:
        _push_msg(state, "warning", f"Error de connexió amb la IA: {e}")
        return state

    _push_msg(state, "hint", hint)
    state["hints_requested"].append({
        "step_after": len(state["history"]) - 1,
        "context": "principal",
        "ts": time.time(),
    })
    state["pending_proactive_offer"] = False
    return state


# ------------------------------------------------------------
# Subflux: prerequisits (mini-sessions)
# ------------------------------------------------------------
def _start_prereq(state, prereq_id, dep_id):
    state["active_prereq"] = prereq_id
    state["active_prereq_depth"] += 1
    state["backtrack_count"] += 1
    if state["active_prereq_depth"] > state["backtrack_depth_max"]:
        state["backtrack_depth_max"] = state["active_prereq_depth"]

    if state["active_prereq_depth"] > MAX_BACKTRACK_DEPTH:
        # No hauríem d'arribar mai aquí: el llindar es comprova abans
        _push_msg(state, "warning",
                  "S'ha arribat a la profunditat màxima de retrocés. "
                  "Es recomana tutoria humana.")
        state["active_prereq"] = None
        state["active_prereq_depth"] -= 1
        return

    prereq = PB.get_prerequisite(prereq_id)
    _push_msg(state, "prereq",
              f"Treballem primer un prerequisit: {prereq['question']}")


def _process_prereq_turn(state, raw_text):
    prereq = PB.get_prerequisite(state["active_prereq"])
    correct = _check_prereq_answer(prereq, raw_text)

    if correct:
        _push_msg(state, "feedback",
                  f"Correcte. {prereq.get('explanation','')}")
        _push_msg(state, "system",
                  "Tornem al problema original.")
        state["active_prereq"] = None
        state["active_prereq_depth"] = max(0, state["active_prereq_depth"] - 1)
    else:
        _push_msg(state, "feedback",
                  f"Encara no. {prereq.get('explanation','')}")
        # En aquest MVP, no fem retrocés en cadena dins del prerequisit:
        # tanquem amb l'explicació mostrada i tornem al problema.
        _push_msg(state, "system", "Tornem al problema original.")
        state["active_prereq"] = None
        state["active_prereq_depth"] = max(0, state["active_prereq_depth"] - 1)
    return state


def _check_prereq_answer(prereq, raw_text) -> bool:
    """Avaluació determinista del prerequisit segons el camp present."""
    s = (raw_text or "").strip()

    if "expected_value" in prereq:
        expr = V.parse_expression(s)
        if expr is None:
            return False
        try:
            return float(expr) == float(prereq["expected_value"])
        except Exception:
            return False

    if "expected_equation" in prereq:
        eq_student = V.parse_equation(s)
        eq_target = V.parse_equation(prereq["expected_equation"])
        return V.equations_equivalent(eq_student, eq_target)

    if "expected_equation_or_expr" in prereq:
        # Pot ser equació o expressió
        target = prereq["expected_equation_or_expr"]
        if "=" in target:
            return V.equations_equivalent(V.parse_equation(s),
                                          V.parse_equation(target))
        else:
            from sympy import simplify
            e_stu = V.parse_expression(s)
            e_tgt = V.parse_expression(target)
            if e_stu is None or e_tgt is None:
                return False
            try:
                return simplify(e_stu - e_tgt) == 0
            except Exception:
                return False

    if "keywords_required" in prereq:
        s_low = s.lower()
        return any(kw.lower() in s_low for kw in prereq["keywords_required"])

    return False


# ------------------------------------------------------------
# Subflux: ús inadequat
# ------------------------------------------------------------
def _handle_inappropriate(state, raw_text, ia_already_judged=False):
    state["inappropriate_warnings"] += 1
    n = state["inappropriate_warnings"]

    # Registrar el text al rastre
    state["history"].append({
        "step": len(state["history"]),
        "text": raw_text,
        "parsed_ok": False,
        "verdict": "no_math",
        "error_label": None,
        "ts": time.time(),
    })

    if n >= MAX_INAPPROPRIATE_WARNINGS:
        state["verdict_final"] = "suspes_us_inadequat"
        _push_msg(state, "warning",
                  "S'ha detectat ús inadequat del sistema. La sessió es tanca i el "
                  "rastre queda registrat.")
        return state

    _push_msg(state, "warning",
              f"Avís {n}/{MAX_INAPPROPRIATE_WARNINGS}: la resposta no conté contingut "
              "matemàtic. Si necessites ajuda, escriu  ?  . Si vols sortir, escriu  !! .")
    return state


# ------------------------------------------------------------
# Generació del rastre JSON final
# ------------------------------------------------------------
def build_trace(state: dict) -> dict:
    duration = time.time() - state["started_at_ts"]
    return {
        "alumne": state["student_id"],
        "problema": {
            "id": state["problem_id"],
            "familia": state["problem"]["familia"],
            "nivell": state["problem"]["nivell"],
            "equacio": state["problem"]["equacio_text"],
            "solucio": state["problem"]["solucio"],
        },
        "started_at": state["started_at"],
        "durada_segons": round(duration, 1),
        "torns_totals": len(state["history"]) - 1,  # restem la inicial
        "equacions_intermèdies": [
            {
                "step": h["step"],
                "text": h["text"],
                "parsed_ok": h["parsed_ok"],
                "verdict": h["verdict"],
                "error_label": h.get("error_label"),
            }
            for h in state["history"]
        ],
        "pistes": {
            "total": len(state["hints_requested"]),
            "posicions": state["hints_requested"],
        },
        "estancaments": {
            "total": state["stagnation_total"],
            "consecutius_max": state["stagnation_max"],
        },
        "retrocessos": {
            "total": state["backtrack_count"],
            "profunditat_max": state["backtrack_depth_max"],
        },
        "discrepancies": state["discrepancies"],
        "avisos_us_inadequat": state["inappropriate_warnings"],
        "veredicte_final": state["verdict_final"] or "en_curs",
    }


def serialize_trace(state: dict) -> str:
    return json.dumps(build_trace(state), ensure_ascii=False, indent=2)
