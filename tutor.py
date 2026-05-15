"""
Lògica nuclear del tutor.

Aquest mòdul és l'únic que coneix la "màquina d'estats" de la sessió.
No depèn de Streamlit (es podria provar des d'un script o des d'un test).

Funció principal: process_turn(state, raw_input) → updated state.
"""

import copy
import json
import time
import uuid
from datetime import datetime, timezone

import problems as PB
import verifier as V
import llm as L
import invariants as INV
import error_consistency as EC


# Profunditat màxima de retrocés a prerequisits (Fase 0, §3)
MAX_BACKTRACK_DEPTH = 2

# Avisos consecutius màxims abans de suspendre per ús inadequat (Fase 0, §11)
MAX_INAPPROPRIATE_WARNINGS = 3


# ------------------------------------------------------------
# Construcció d'un estat nou
# ------------------------------------------------------------
def new_session_state(problem_id: str, student_id: str = "anon") -> dict:
    """
    Crea l'estat inicial d'una sessió per a un problema.

    `student_id`: pseudonim de l'alumne (es propaga al log via
    `L.set_log_context`). Defaultem a "anon" perquè qualsevol crida
    sense context explícit quedi clarament marcada com a anònima al log.

    Cada crida genera un `session_id` nou (12 hex). Una sessió =
    un intent d'un problema, no la vida del procés Python. Així es
    poden agregar mètriques per problema-iniciat al log.
    """
    problem = PB.get_problem(problem_id)
    return {
        "session_id": uuid.uuid4().hex[:12],
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
        # Comptador d'errors consecutius del mateix concepte dins el
        # problema (clau = dep_id, valor = comptador). Es reseteja amb un
        # pas correcte. S'usa per escalar l'ajuda quan un prereq no és
        # suficient: 1a errada → prereq, 2a → exemple resolt, 3+ → pas
        # concret directe.
        "concept_failure_streak": {},
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


def _recent_errors(state: dict, limit: int = 3) -> list:
    """
    Retorna els darrers `limit` intents amb veredicte 'error', en ordre
    cronològic (el més recent al final), cadascun com a dict
    {"text": ..., "error_label": ...}.

    Aquesta funció dóna a la IA visió del PATRÓ de la sessió: amb la
    classificació individual d'errors no es pot detectar que l'alumne
    està repetint el mateix tipus de fallada; passant els errors recents
    com a context, la IA pot pujar-li la confiança al diagnòstic
    conceptual i adaptar el missatge ("tornes a fer el mateix tipus
    d'error" en lloc de "has fallat").
    """
    out = []
    for h in reversed(state["history"]):
        if h.get("verdict") == "error":
            out.append({
                "text": h["text"],
                "error_label": h.get("error_label"),
            })
            if len(out) >= limit:
                break
    return list(reversed(out))


def _push_msg(state, kind: str, text: str, target: str = "main",
              persistent: bool = False, extra: dict = None):
    """
    kind:   'system' | 'feedback' | 'hint' | 'warning' | 'prereq' |
            'discrepancy' | 'worked_example' | 'concrete_step' |
            'prereq_resolved' | 'prereq_failed'
    target: 'main' (panell principal) | 'prereq' (panell dret quan hi ha
            sub-tasca activa).
    persistent: si True, el missatge sobreviu entre torns (no es neteja
            al començament de process_turn). Útil per a missatges que
            donen context sobre què s'acaba de tancar (per ex. el
            resultat del retrocés a un prereq), perquè l'alumne segueixi
            veient-los mentre intenta aplicar el que ha après.
    El render decideix on mostrar cada missatge segons el target.
    """
    state["messages"].append({"kind": kind, "text": text,
                              "target": target, "persistent": persistent,
                              "extra": extra or {},
                              "ts": time.time()})


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

    Wrapper sobre `_process_turn_impl` que afegeix una verificació
    d'invariants estructurals a la sortida (veure `invariants.py`). Si una
    excepció s'allibera des de la implementació, la deixem propagar sense
    verificar res — l'excepció ja és prou clara.
    """
    state = _process_turn_impl(state, raw_input)
    INV.check_state_invariants(state, label="process_turn")
    return state


def _process_turn_impl(state: dict, raw_input: str) -> dict:
    # Reset dels missatges de UI per al nou torn. Els missatges
    # marcats com a persistent (típicament prereq_resolved /
    # prereq_failed) es conserven perquè l'alumne segueixi veient
    # el resultat del retrocés mentre aplica el que ha après.
    state["messages"] = [m for m in state["messages"] if m.get("persistent")]

    # 1. Senyals d'escapament
    sig = parse_escape_signal(raw_input)

    if sig["kind"] == "exit":
        state["verdict_final"] = "abandonat"
        _push_msg(state, "system", "Sessió tancada per l'alumne. Rastre desat.")
        return state

    if sig["kind"] == "discrepancy":
        state["discrepancies"].append({
            "step_after": len(state["history"]) - 1,
            "text_alumne": sig["payload"],
            "ts": time.time(),
        })
        _push_msg(state, "discrepancy",
                  "D'acord, queda anotat. Continuem.")
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
            _push_msg(state, "warning", f"Hi ha un error de connexió amb la IA: {e}")
            return state

        if ia["verdict"] == "no_eq":
            # Distingim dos casos:
            # (a) L'input té "=" però SymPy no l'ha pogut parsear (caràcter
            #     Unicode, format inusual...) → no diem "falta el signe"
            #     perquè seria erroni; demanem que el reformuli.
            # (b) L'input ÉS matemàtic però no té "=" → falta el signe.
            # (c) L'input no és matemàtic → ús inadequat.
            has_eq_char = "=" in raw_text or "＝" in raw_text
            if has_eq_char:
                _push_msg(state, "feedback",
                          "He tingut dificultats per interpretar la teva equació. "
                          "Prova d'escriure-la de nou amb nombres i lletres estàndard, "
                          f"per exemple: {ia.get('reconstruction') or '...'}")
                return state
            if V.has_math_content(raw_text):
                _push_msg(state, "feedback",
                          "Sembla que falta el signe d'igualtat. "
                          "Escriu una equació completa amb «=», "
                          f"per exemple: {ia.get('reconstruction') or '...'}")
                return state
            return _handle_inappropriate(state, raw_text, ia_already_judged=True)

        reconstruction = ia.get("reconstruction")
        text_to_record = reconstruction or raw_text

        # Si la IA ha reconstruït una equació vàlida, la passem a SymPy
        # per al judici matemàtic real — la IA pot equivocar-se en jutjar
        # si el pas és correcte o no (ex: "3x 15" → "3x = 15" és correcte
        # però la IA pot dir "error" per la notació deficient de l'alumne).
        if reconstruction:
            reconstructed_eq = V.parse_equation(reconstruction)
            if reconstructed_eq is not None:
                _push_msg(state, "info", f"Jo interpreto: {reconstruction}")
                return _evaluate_equation_step(state, reconstruction)

        verdict_map = {
            "correcte_progres": "correcte_progres",
            "correcte_estancat": "correcte_estancat",
            "error": "error",
        }
        v = verdict_map.get(ia["verdict"], "error")
        # Si el camí d'interpretació conclou que el pas és erroni, etiquetem-lo
        # genèricament. interpret_input no fa classificació fina d'error (això
        # és feina de classify_error, que només es crida quan SymPy parseja);
        # sense aquesta etiqueta el rastre JSON queda buit per a aquests casos
        # i l'anàlisi posterior no pot agrupar-los.
        err_label = "GEN_other" if v == "error" else None
        _record_step(state, text_to_record, parsed_ok=False, verdict=v,
                     error_label=err_label)
        _push_msg(state, "feedback", f"Jo interpreto això {ia['short_msg']}")
        _post_verdict_bookkeeping(state, v, original_text)
        return state

    # Validació determinista de forma: lineal en x, sense variables alienes.
    # Tot això és gratis i ràpid; s'executa abans de qualsevol crida a la IA.
    form_check = V.validate_equation_form(new_eq)
    if not form_check["ok"]:
        # Mapatge de motiu → etiqueta d'error per al rastre
        reason_to_label = {
            "non_linear": "FORM_non_linear",
            "foreign_variable": "FORM_foreign_var",
            "no_variable": "FORM_no_variable",
        }
        label = reason_to_label.get(form_check["reason"], "FORM_other")
        _record_step(state, raw_text, parsed_ok=True,
                     verdict="error", error_label=label)
        _push_msg(state, "feedback", form_check["details"])
        _post_verdict_bookkeeping(state, "error", original_text)
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
                      "Has tornat a escriure la mateixa equació.")
            _post_verdict_bookkeeping(state, "correcte_estancat", original_text)
            return state

        # Comprovació determinista de terminal:
        # si x = c i c és la solució correcta, problema resolt sense IA.
        if V.is_terminal(new_eq, raw_text=raw_text):
            sol = V.solve_for_x(new_eq)
            if str(sol) == target_sol:
                _record_step(state, raw_text, parsed_ok=True,
                             verdict="correcte_progres")
                state["verdict_final"] = "resolt"
                _push_msg(state, "feedback",
                          f"Correcte. x = {sol}. Equació resolta, felicitats!")
                # F4 (2026-05-11): cridem bookkeeping per resetejar
                # comptadors d'estancament i streaks conceptuals al
                # moment de resoldre. No té efecte funcional ara mateix
                # (la sessió acaba aquí), però evita arrossegar valors
                # incorrectes si en el futur hi ha lògica post-resolt.
                _post_verdict_bookkeeping(state, "correcte_progres", original_text)
                return state

        # Per al judici de progrés sí que comparem amb la prèvia
        # (té sentit pedagògicament: estem avançant respecte d'on érem?).
        # Si la prèvia va ser un error, prenem com a referència de progrés
        # el darrer pas correcte (o l'enunciat).
        ref_text = _last_correct_step_text(state)
        try:
            jp = L.judge_progress(ref_text, raw_text, target_sol)
        except Exception as e:
            _push_msg(state, "warning", f"Hi ha un error de connexió amb la IA: {e}")
            return state

        v = "correcte_progres" if jp["verdict"] == "progres" else "correcte_estancat"
        _record_step(state, raw_text, parsed_ok=True, verdict=v)

        if v == "correcte_progres":
            _push_msg(state, "feedback", f"Correcte. {jp.get('reason','')}".strip())
        else:
            # No mostrem la raó del LLM a l'alumne: pot ser incorrecta
            # (el LLM pot al·lucinar "no equivalent" quan SymPy ja ha
            # confirmat l'equivalència). La raó queda al rastre JSON.
            _push_msg(state, "feedback",
                      "L'equació és correcta, però no t'acosta més a la solució.")

        _post_verdict_bookkeeping(state, v, original_text)
        return state

    # No equivalent a l'original: és un error.
    # Pre-check determinista: si el coeficient de x ha canviat entre
    # l'últim pas correcte i l'intent, és un error aritmètic en el
    # coeficient (independentment de si la resta de la transformació
    # era correcta). Detectar-ho aquí evita que la IA al·lucini una
    # causa que no correspon a la transformació real.
    last_correct = _last_correct_step_text(state)
    last_correct_eq = V.parse_equation(last_correct)
    attempt_eq = V.parse_equation(raw_text)
    coef_last   = V.x_coefficient(last_correct_eq)
    coef_attempt = V.x_coefficient(attempt_eq)
    # Només disparem si el coeficient canvia a un valor que NO és ±1.
    # Si c_attempt == ±1, l'alumne ha intentat aïllar x dividint pels
    # dos costats — pot ser un error de signe, però NO un error de
    # coeficient; deixem que la IA classifiqui correctament.
    if (coef_last is not None and coef_attempt is not None
            and coef_last != coef_attempt
            and coef_attempt not in (1, -1)):
        _record_step(state, raw_text, parsed_ok=True,
                     verdict="error", error_label="GEN_arithmetic")
        _push_msg(state, "feedback",
                  f"Has comès un error en el coeficient de x: "
                  f"era {coef_last} i has escrit {coef_attempt}. "
                  f"Comprova els càlculs i torna-ho a intentar.")
        _post_verdict_bookkeeping(state, "error", original_text)
        return state

    recent_err = _recent_errors(state, limit=3)
    try:
        ce = L.classify_error(
            original_text, last_correct, raw_text,
            PB.ERROR_CATALOG,
            state["problem"]["dependencies"],
            recent_errors=recent_err,
        )
    except Exception as e:
        _push_msg(state, "warning", f"Hi ha un error de connexió amb la IA: {e}")
        # IMPORTANT: encara que la IA falli, l'intent ÉS un error (sabem
        # per equivalència que no és correcte). Hem de gravar-lo a la
        # història amb una etiqueta genèrica, perquè si no, _last_correct
        # i el debug runner llegirien el pas previ com a últim — donant
        # falsament la sensació que aquest intent ha passat com a correcte.
        _record_step(state, raw_text, parsed_ok=True, verdict="error",
                     error_label="GEN_other")
        return state

    # Verificador post-IA: comprova que l'etiqueta retornada per la IA
    # és estructuralment consistent amb el context. Atrapa al·lucinacions
    # del tipus "L3_distribution_partial" quan no hi ha cap parèntesi a
    # last_correct, o "L4_mcm_partial" quan no hi ha cap fracció.
    # Veure error_consistency.py per a la llista de regles.
    revision_info = None
    if not EC.is_label_consistent(ce["error_label"], last_correct, raw_text):
        original_label = ce["error_label"]
        revision_info = {
            "original_label": original_label,
            "reason": EC.explain_inconsistency(original_label, last_correct)
                      or "inconsistència estructural",
        }
        # Sobreescrivim: el pas és un error genèric (sabem per SymPy
        # que no és equivalent), però el diagnòstic concret de la IA
        # no és fiable. Buidem també is_conceptual i dep_id perquè no
        # s'activi cap retrocés basat en una etiqueta descartada.
        ce["error_label"] = "GEN_arithmetic"
        ce["short_msg"] = (
            "Hi ha un error en aquest pas. Revisa els càlculs amb cura."
        )
        ce["is_conceptual"] = False
        ce["dep_id"] = None

    _record_step(state, raw_text, parsed_ok=True,
                 verdict="error", error_label=ce["error_label"])
    # Si la classificació de la IA s'ha revisat, anotem-ho al pas per
    # poder auditar el rastre JSON posteriorment. Camp opcional: només
    # apareix quan ha hagut revisió.
    if revision_info is not None:
        state["history"][-1]["error_label_revised"] = revision_info

    # Intent de contextualitzar el missatge d'error amb els números reals
    # de `last_correct` i de l'atemptp. Funció determinista: parseja amb
    # SymPy i només retorna text si està segura del patró. Si no pot,
    # retorna None i caiem al `short_msg` genèric de la IA. Veure
    # `_contextualize_error_message` més avall.
    _ctx_msg = _contextualize_error_message(
        ce["error_label"], last_correct, raw_text,
    )
    _push_msg(state, "feedback", _ctx_msg or ce["short_msg"])

    # Fallback determinista per al retrocés a prerequisits.
    # Si l'etiqueta d'error implica clarament un concepte (per exemple
    # L3_distribution_partial ⇒ prop_distributiva) i aquest concepte és
    # prerequisit d'aquest problema, tractem l'error com a conceptual
    # encara que la IA hagi posat is_conceptual=false. Així el retrocés
    # no depèn que el model ompli bé aquest camp en cada classificació.
    implied_dep = PB.implied_dependency_for_error(ce["error_label"])
    if implied_dep and implied_dep in state["problem"]["dependencies"]:
        if not ce["is_conceptual"] or not ce["dep_id"]:
            ce["is_conceptual"] = True
            ce["dep_id"] = implied_dep

    # Escalada d'ajuda segons la recurrència del mateix concepte:
    #   streak == 1  → retrocés a prereq (pregunta socràtica abstracta)
    #   streak == 2  → exemple resolt amb una equació anàloga
    #   streak >= 3  → instrucció directa del pas següent (mig revelat)
    # Cada nivell és més concret que l'anterior. Quan l'alumne fa un pas
    # de progrés, els streaks es reseteg(en a _post_verdict_bookkeeping.
    if ce["is_conceptual"] and ce["dep_id"]:
        dep = PB.get_dependency(ce["dep_id"])
        if dep:
            streaks = state["concept_failure_streak"]
            streaks[ce["dep_id"]] = streaks.get(ce["dep_id"], 0) + 1
            streak = streaks[ce["dep_id"]]

            concept_desc = dep.get("description", ce["dep_id"])

            if streak == 1:
                # 1a errada: retrocés a prereq, com fins ara
                if state["active_prereq_depth"] < MAX_BACKTRACK_DEPTH:
                    prereq_id = _select_prereq_id(
                        ce["error_label"], dep, last_correct
                    )
                    _start_prereq(state, prereq_id, ce["dep_id"])
            elif streak == 2:
                # 2a errada del mateix concepte: el prereq no ha
                # desbloquejat l'alumne; canvi de tàctica a exemple resolt.
                # Passem els intents equivocats recents (Move 2) com a
                # anti-exemples: la IA ha d'evitar triar un cas l'aspecte
                # del qual coincideixi amb el que l'alumne ha escrit
                # malament, perquè això reforçaria el patró erroni.
                recent_wrong = [e["text"]
                                for e in _recent_errors(state, limit=3)]
                try:
                    msg = L.generate_worked_example(
                        last_correct, original_text, concept_desc,
                        recent_wrong_attempts=recent_wrong,
                    )
                    _push_msg(state, "worked_example", msg)
                except Exception as e:
                    _push_msg(state, "warning",
                              f"Hi ha un error de connexió amb la IA: {e}")
            else:  # streak >= 3
                # 3a o més: ni el prereq ni l'exemple han funcionat;
                # diem explícitament què cal fer al pas següent.
                recent_wrong = [e["text"]
                                for e in _recent_errors(state, limit=3)]
                try:
                    msg = L.generate_concrete_step(
                        last_correct, original_text, concept_desc,
                        recent_wrong_attempts=recent_wrong,
                    )
                    _push_msg(state, "concrete_step", msg)
                except Exception as e:
                    _push_msg(state, "warning",
                              f"Hi ha un error de connexió amb la IA: {e}")

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
                      "Sembla que estàs donant voltes. Pots clicar el botó \"Pista\", a la columna de l'esquerra.")
    else:
        # Reset si surt de l'estancament
        state["stagnation_consecutive"] = 0
        state["pending_proactive_offer"] = False
        # Reset dels comptadors d'errors per concepte: l'alumne ha avançat
        # i tornem a començar el gradient d'ajuda des de zero. No resetegem
        # en cas de "error" — això és precisament quan els acumulem.
        if verdict == "correcte_progres":
            state["concept_failure_streak"] = {}


# ------------------------------------------------------------
# Subflux: '?' → pista contextualitzada
# ------------------------------------------------------------
def _handle_help(state):
    if state["active_prereq"] is not None:
        prereq = PB.get_prerequisite(state["active_prereq"])
        _push_msg(state, "hint", prereq.get("explanation",
                  "Llegeix bé el que t'estan demanant."),
                  target="prereq")
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
        _push_msg(state, "warning", f"Hi ha un error de connexió amb la IA: {e}")
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
# Contextualització de missatges d'error
# ------------------------------------------------------------
def _contextualize_error_message(error_label: str,
                                  last_correct_text: str,
                                  attempt_text: str) -> str | None:
    """
    Genera un missatge d'error contextualitzat amb els números reals del
    moment, en lloc del text genèric del catàleg.

    Estratègia DETERMINISTA: parsejem `last_correct_text` i `attempt_text`
    amb SymPy, identifiquem el patró específic de l'error, i construïm
    una frase. Cap crida a la IA — sense risc d'al·lucinació.

    Cobreix els 4 labels més pedagògicament rics:
        - L1_sign_error   ("dividit per K en lloc de per -K")
        - L1_inverse_op   ("restat K en lloc de dividir per K")
        - L2_transpose_sign ("mogut +b sense canviar el signe")
        - L4_illegal_cancel ("tret el denominador d sense multiplicar...")

    Per a la resta de labels, retorna None i el sistema usa el missatge
    genèric de la IA (a `ce["short_msg"]`).

    Si la detecció falla (equació no parseja, patró inesperat), retorna
    None — fallback al missatge genèric. Mai produeix un missatge incorrecte:
    només produeix res quan està segur del que diu.
    """
    from verifier import X, parse_equation
    from sympy import Poly, Rational

    last_eq = parse_equation(last_correct_text)
    att_eq = parse_equation(attempt_text)
    if last_eq is None or att_eq is None:
        return None
    last_lhs, last_rhs = last_eq
    att_lhs, att_rhs = att_eq

    try:
        # ─── L1_sign_error ─────────────────────────────────────────────
        # Patró: de Kx = M, l'alumne ha calculat un x amb el signe equivocat
        # (magnitud correcta). El cas paradigmàtic és:
        #   −3x = 9  → x = 3  (havia de ser −3; signe oposat al correcte)
        #   5x = −20 → x = 4  (havia de ser −4)
        #   2x = −10 → x = 5  (havia de ser −5)
        # La x pot estar a qualsevol costat.
        if error_label == "L1_sign_error":
            if X in last_lhs.free_symbols and X not in last_rhs.free_symbols:
                x_side, const_side = last_lhs, last_rhs
            elif X in last_rhs.free_symbols and X not in last_lhs.free_symbols:
                x_side, const_side = last_rhs, last_lhs
            else:
                x_side = None
            if x_side is not None:
                p_xside = Poly(x_side, X)
                coeffs = p_xside.all_coeffs()
                if len(coeffs) == 2 and coeffs[1] == 0:  # Kx (sense terme indep.)
                    K = coeffs[0]
                    M = const_side
                    if att_lhs == X and X not in att_rhs.free_symbols:
                        v = att_rhs
                        try:
                            correct = M / K
                            if v == -correct and v != correct:
                                K_str = str(K).replace('-', '−')
                                absK_str = str(abs(K))
                                if K_str == absK_str:
                                    return (
                                        f"El resultat té el signe equivocat. "
                                        f"Si {K_str}·x = {M}, x ha de ser "
                                        f"{correct} (no {v}). Revisa el signe."
                                    )
                                return (
                                    f"Crec que has dividit per {absK_str}, "
                                    f"però calia dividir per {K_str}. "
                                    f"Revisa el signe."
                                )
                        except (ZeroDivisionError, TypeError):
                            pass

        # ─── L1_inverse_op ─────────────────────────────────────────────
        # Patró 1: Kx = M → x = M ± K (additiu en lloc de divisió)
        # Patró 2: x + K = M → x = K + M (no inverteix l'additiu)
        # Patró 3: x/K = M → x = M/K (divideix en lloc de multiplicar)
        # La x pot estar a qualsevol costat de l'última correcta.
        if error_label == "L1_inverse_op":
            if X in last_lhs.free_symbols and X not in last_rhs.free_symbols:
                x_side, const_side = last_lhs, last_rhs
            elif X in last_rhs.free_symbols and X not in last_lhs.free_symbols:
                x_side, const_side = last_rhs, last_lhs
            else:
                x_side = None
            if x_side is not None and att_lhs == X and X not in att_rhs.free_symbols:
                p_xside = Poly(x_side, X)
                coeffs = p_xside.all_coeffs()  # [a, b] per a a*x + b
                v = att_rhs
                M = const_side
                if len(coeffs) == 2:
                    a, b = coeffs
                    # Cas 1: Kx (b == 0) amb K enter, alumne ha fet
                    # x = M - K, M + K o M * K. Excloem coeficients
                    # fraccionaris (1/3, etc.) — els tractem al Cas 3.
                    if b == 0 and a != 0 and a.is_integer:
                        K = a
                        if v == M - K:
                            return (
                                f"Crec que has restat {K} a {M}, "
                                f"però calia DIVIDIR per {K}. "
                                f"Revisa l'operació."
                            )
                        if v == M + K:
                            return (
                                f"Crec que has sumat {K} a {M}, "
                                f"però calia DIVIDIR per {K}. "
                                f"Revisa l'operació."
                            )
                        if v == M * K:
                            return (
                                f"Crec que has multiplicat {M} per {K}, "
                                f"però calia DIVIDIR per {K}. "
                                f"Revisa l'operació."
                            )
                    # Cas 2: x + b (a == 1), alumne ha sumat b en lloc de restar
                    if a == 1 and b != 0:
                        if v == M + b:
                            b_str = f"+{b}" if b > 0 else f"{b}"
                            return (
                                f"Has sumat {b_str.lstrip('+')} a {M} en lloc de "
                                f"restar-lo. Recorda que l'operació inversa de "
                                f"sumar és restar."
                            )
                        if v == M - b and b < 0:
                            return (
                                f"Has restat {abs(b)} en lloc de sumar-lo. "
                                f"Recorda que l'operació inversa de restar és sumar."
                            )
                # Cas 3: x/K = M (coef. fraccionari 1/K). SymPy normalitza
                # `x/3` com `Rational(1,3)*x`, per tant Poly.all_coeffs()
                # retorna [Rational(1,K), 0]. Si l'alumne ha posat v = M/K
                # (dividit en lloc de multiplicar) o v = M - K / v = M + K
                # (additiu en lloc de multiplicatiu), és error d'op. inversa.
                if len(coeffs) == 2 and coeffs[1] == 0:
                    a = coeffs[0]
                    from sympy import Rational
                    # Detecta `Rational(1, K)` amb K enter > 1
                    if isinstance(a, Rational) and a.p == 1 and a.q > 1:
                        K = a.q  # denominador
                        try:
                            if v == M / K:
                                return (
                                    f"Crec que has dividit {M} per {K}, "
                                    f"però calia MULTIPLICAR per {K}. "
                                    f"Revisa l'operació."
                                )
                            if v == M - K:
                                return (
                                    f"Crec que has restat {K} a {M}, "
                                    f"però calia MULTIPLICAR per {K}. "
                                    f"Revisa l'operació."
                                )
                            if v == M + K:
                                return (
                                    f"Crec que has sumat {K} a {M}, "
                                    f"però calia MULTIPLICAR per {K}. "
                                    f"Revisa l'operació."
                                )
                        except (ZeroDivisionError, TypeError):
                            pass

        # ─── L2_transpose_sign ─────────────────────────────────────────
        # Patró: ax + b = c → ax = c + b (mantingut el signe en lloc d'invertir-lo).
        # La x pot ser a qualsevol costat. Normalitzem perquè la x estigui
        # sempre a un dels costats; el terme constant a transposar és el
        # que apareix al costat amb x.
        if error_label == "L2_transpose_sign":
            # Identifiquem quin costat té x i quin no
            if X in last_lhs.free_symbols and X not in last_rhs.free_symbols:
                x_side, _const_side = last_lhs, last_rhs
            elif X in last_rhs.free_symbols and X not in last_lhs.free_symbols:
                x_side, _const_side = last_rhs, last_lhs
            else:
                x_side = None

            if x_side is not None:
                p_xside = Poly(x_side, X)
                coeffs = p_xside.all_coeffs()
                if len(coeffs) == 2:
                    a, b = coeffs
                    if b != 0:
                        # El terme transposat és b (amb el seu signe original
                        # a x_side). Si b > 0, l'alumne hauria de passar-ho
                        # com a "−b" a l'altre costat. Si b < 0, com a "+|b|".
                        if b > 0:
                            term_str = f"+{b}"
                            inverse_str = f"−{b}"
                        else:
                            term_str = f"−{abs(b)}"
                            inverse_str = f"+{abs(b)}"
                        return (
                            f"Has passat el {term_str} a l'altre costat, "
                            f"però havies de canviar-li el signe a {inverse_str}. "
                            f"Quan un terme canvia de costat, el signe s'inverteix."
                        )

        # ─── L4_illegal_cancel ─────────────────────────────────────────
        # Patró: a/d = c (last) → a = c (att, sense multiplicar el RHS per d).
        # Detecció: l'última té denominador, l'atemptp no, i el RHS és el mateix.
        if error_label == "L4_illegal_cancel":
            # Si l'última té x dividit per algo i l'atemptp no, és aquest patró.
            # Comprovem si `last_lhs * d == att_lhs` per algun enter `d`.
            # Heurística: si l'atemptp_rhs == last_rhs (sense canvi), és illegal cancel.
            if att_rhs == last_rhs:
                # Cerquem el denominador. Sympy simplifica `(x+1)/3` com
                # `(x+1)*Rational(1,3)`. Mirem la forma `last_lhs`.
                from sympy import together, fraction
                num, den = fraction(together(last_lhs))
                if den != 1 and num == att_lhs:
                    return (
                        f"Has eliminat el denominador {den} d'un costat, "
                        f"però havies de multiplicar l'altre costat per {den} "
                        f"perquè els dos costats segueixin sent iguals."
                    )
    except Exception:
        # Qualsevol fallada de SymPy o tipus → fallback al missatge genèric
        return None
    return None


# ------------------------------------------------------------
# Subflux: prerequisits (mini-sessions)
# ------------------------------------------------------------
def _select_prereq_id(error_label: str, dep: dict, last_correct_text: str) -> str:
    """
    Tria el prerequisit més adequat per a aquest error concret, segons la
    forma de l'última equació vàlida (`last_correct_text`). Cada concepte
    pedagògic (`dep["prerequisite"]`) pot tenir VARIANTS, i cal triar
    la que coincideix millor amb el cas que l'alumne té al davant.

    Mapatge de variants:

      operacions_inverses:
        x + K = M  (K > 0)  → PRE-INV-ADD  (cal restar)
        x − K = M  (K > 0)  → PRE-INV-SUB  (cal sumar)
        K·x = M             → PRE-INV-MULT (cal dividir)
        x/K = M             → PRE-INV-DIV  (cal multiplicar)

      prop_distributiva:
        a·(x + K)  → PRE-DIST-PLUS   (signe positiu dins)
        a·(x − K)  → PRE-DIST-MINUS  (signe negatiu dins)

      regla_signes_parens:
        −(x − K)  → PRE-SIGNES-MINUS (signe negatiu dins)
        −(x + K)  → PRE-SIGNES-PLUS  (signe positiu dins)

      def_fraccions_equiv:
        a/b = c/d         → PRE-FRAC-CROSS (producte creuat)
        ax/b = c          → PRE-FRAC-COEF  (coeficient fraccionari)

    Si la detecció falla (equació amb x als dos costats, parseja malament,
    casos ambigus), retorna el `dep["prerequisite"]` per defecte.

    NOTA IMPLEMENTATIVA: SymPy expandeix automàticament els parèntesis al
    parsejar (ex: '3(x − 4) = 9' es converteix en lhs=3*x − 12). Per tant,
    per a la detecció de prop_distributiva i regla_signes_parens cal
    inspeccionar el TEXT ORIGINAL via regex, no l'expressió parsejada.
    """
    default = dep["prerequisite"]
    concept = dep.get("description", "")
    text = (last_correct_text or "").strip()

    # Importacions locals (només necessàries en aquesta funció)
    from verifier import X
    from sympy import Poly
    import re

    # ─── operacions_inverses ──────────────────────────────────────────
    if default in ("PRE-INV-ADD", "PRE-INV", "PRE-INV-SUB",
                   "PRE-INV-MULT", "PRE-INV-DIV"):
        eq = V.parse_equation(text)
        if eq is None:
            return default
        lhs, rhs = eq
        # Quin costat té la x?
        if X in lhs.free_symbols and X not in rhs.free_symbols:
            x_side, const_side = lhs, rhs
        elif X in rhs.free_symbols and X not in lhs.free_symbols:
            x_side, const_side = rhs, lhs
        else:
            return default  # ambigu

        op_type = V.next_operation_type(eq)

        if op_type == "additive":
            # x + K = M (K > 0)  → PRE-INV-ADD
            # x − K = M (K > 0)  → PRE-INV-SUB
            # Per saber el signe de K, agafem el terme constant del
            # costat x i mirem si és positiu o negatiu.
            try:
                p = Poly(x_side, X)
                # all_coeffs() retorna [a, b] per a a*x + b
                coeffs = p.all_coeffs()
                if len(coeffs) == 2:
                    b = coeffs[1]
                    if b > 0:
                        return "PRE-INV-ADD"
                    if b < 0:
                        return "PRE-INV-SUB"
            except Exception:
                pass
            return "PRE-INV-ADD"  # fallback per a casos rars

        if op_type == "multiplicative":
            # K·x = M  → PRE-INV-MULT
            # x/K = M  → PRE-INV-DIV
            # SymPy normalitza `x/3` com `x/3` (Mul amb Rational), però
            # `3·x` com `3*x`. Distingim mirant si el text original conté
            # `x/` (cas divisió) o no (cas multiplicació). Comprovació
            # textual perquè SymPy a vegades ho amaga.
            if re.search(r'\bx\s*/\s*\d', text):
                return "PRE-INV-DIV"
            return "PRE-INV-MULT"

        return default

    # ─── prop_distributiva ────────────────────────────────────────────
    if default in ("PRE-DIST-PLUS", "PRE-DIST", "PRE-DIST-MINUS"):
        # Cerquem un parèntesi amb forma `(x ± K)` al text original.
        # Convencions de signe: SymPy usa `-` ASCII, l'editor pot usar
        # `−` Unicode (U+2212). Acceptem tots dos.
        # Patró: a·(x + K) o a·(x − K), o (x ± K)·a, o variants amb números.
        # Si trobem `(x +` clarament → PLUS; si `(x −` → MINUS.
        # Si hi ha múltiples parèntesis, prioritzem el primer.
        m_plus = re.search(r'\(\s*[\-−]?\s*\d*\s*x\s*\+\s*\d', text)
        m_minus = re.search(r'\(\s*[\-−]?\s*\d*\s*x\s*[\-−]\s*\d', text)
        if m_plus and m_minus:
            # Múltiples parèntesis amb signes diferents: triem el primer.
            return "PRE-DIST-PLUS" if m_plus.start() < m_minus.start() else "PRE-DIST-MINUS"
        if m_plus:
            return "PRE-DIST-PLUS"
        if m_minus:
            return "PRE-DIST-MINUS"
        return default

    # ─── regla_signes_parens ──────────────────────────────────────────
    if default in ("PRE-SIGNES-MINUS", "PRE-SIGNES", "PRE-SIGNES-PLUS"):
        # Cerquem un parèntesi precedit per menys: −(x ± K).
        # `[\-−]\s*\(\s*x\s*[\+]\s*\d`  → PRE-SIGNES-PLUS
        # `[\-−]\s*\(\s*x\s*[\-−]\s*\d` → PRE-SIGNES-MINUS
        m_plus = re.search(r'[\-−]\s*\(\s*x\s*\+\s*\d', text)
        m_minus = re.search(r'[\-−]\s*\(\s*x\s*[\-−]\s*\d', text)
        if m_plus and m_minus:
            return "PRE-SIGNES-PLUS" if m_plus.start() < m_minus.start() else "PRE-SIGNES-MINUS"
        if m_plus:
            return "PRE-SIGNES-PLUS"
        if m_minus:
            return "PRE-SIGNES-MINUS"
        return default

    # ─── def_fraccions_equiv ──────────────────────────────────────────
    if default in ("PRE-FRAC-CROSS", "PRE-FRAC", "PRE-FRAC-COEF"):
        eq = V.parse_equation(text)
        if eq is None:
            return default
        lhs, rhs = eq
        # PRE-FRAC-CROSS: dues fraccions a banda i banda d'=, sense x
        # multiplicador (a/b = c/d).
        # PRE-FRAC-COEF: una fracció amb coeficient (ax/b = c) i el
        # RHS és un nombre senzill.
        # Heurística: si almenys un costat és enter sencer (sense
        # fracció), és coef-fractionari. Si tots dos tenen forma
        # fraccionària, és producte creuat clàssic.
        rhs_is_int = rhs.is_number and rhs.is_integer
        lhs_is_int = lhs.is_number and lhs.is_integer
        if rhs_is_int or lhs_is_int:
            return "PRE-FRAC-COEF"
        return "PRE-FRAC-CROSS"

    return default


def _start_prereq(state, prereq_id, dep_id):
    state["active_prereq"] = prereq_id
    state["active_prereq_depth"] += 1
    state["backtrack_count"] += 1
    if state["active_prereq_depth"] > state["backtrack_depth_max"]:
        state["backtrack_depth_max"] = state["active_prereq_depth"]

    if state["active_prereq_depth"] > MAX_BACKTRACK_DEPTH:
        # No hauríem d'arribar mai aquí: el llindar es comprova abans
        _push_msg(state, "warning",
                  "Es recomana demanar ajuda al professorat.")
        state["active_prereq"] = None
        state["active_prereq_depth"] -= 1
        return

    prereq = PB.get_prerequisite(prereq_id)
    _push_msg(state, "prereq",
              "Cal practicar, abans, un exercici de reforç.",
              target="main")


def _process_prereq_turn(state, raw_text):
    prereq = PB.get_prerequisite(state["active_prereq"])
    correct = _check_prereq_answer(prereq, raw_text)
    explanation = prereq.get("explanation", "")
    prereq_id = prereq.get("id", state["active_prereq"])

    if isinstance(correct, tuple) and correct[0] == "typo":
        # Resposta correcta de fons però amb errada ortogràfica.
        # Màxim 3 avisos; al 4t intent acceptem per evitar bloqueig.
        typo_word = correct[1]
        typo_key = f"typo_attempts_{prereq_id}"
        state.setdefault(typo_key, 0)
        state[typo_key] += 1
        if state[typo_key] <= 3:
            _push_msg(state, "feedback",
                      f"Sembla correcte el que escrius, però has comès una errada "
                      f"ortogràfica. Repassa la paraula '{typo_word}' i torna a "
                      f"escriure la frase.",
                      target="prereq")
            return state
        # Al 4t intent: acceptem i continuem.
        correct = True

    if correct:
        # Feedback al panell del prereq abans que es tanqui (l'alumne
        # encara el veu un instant). El missatge auxiliar persistent va
        # al viewport principal.
        _push_msg(state, "feedback",
                  f"Correcte. {explanation}",
                  target="prereq")
        state["active_prereq"] = None
        state["active_prereq_depth"] = max(0, state["active_prereq_depth"] - 1)
        # Caixa auxiliar visible al viewport principal: l'alumne ha de
        # quedar amb constància que ha resolt el prereq, i — important —
        # ha de saber QUÈ HA DE FER ARA (continuar amb el problema
        # principal). Sense aquesta indicació, l'alumne es queda amb
        # l'input buit sense saber que ha de continuar resolent.
        # L'ID intern (PRE-EQUIV, PRE-INV...) no és significatiu per a l'alumne;
        # s'ometi del missatge. L'explicació va en paràgrafs separats per claredat.
        _extra = {}
        if prereq.get("initial_equation") and prereq.get("explanation_steps"):
            _extra = {
                "initial_equation": prereq["initial_equation"],
                "steps": prereq["explanation_steps"],
                "summary": prereq.get("explanation_summary", ""),
                "cta": "Continua amb la resolució de l'equació.",
            }
        _push_msg(state, "prereq_resolved",
                  "Correcte.",
                  target="main", persistent=True, extra=_extra)
    else:
        _push_msg(state, "feedback",
                  f"Encara no és correcte. {explanation}",
                  target="prereq")
        state["active_prereq"] = None
        state["active_prereq_depth"] = max(0, state["active_prereq_depth"] - 1)
        # Cas crític: si la resposta del prereq era incorrecta, NO podem
        # tancar-ho com si no hagués passat res — l'alumne ha de veure
        # explícitament que la seva resposta no era correcta, l'explicació
        # esperada, i la indicació de què fer ara.
        #
        # Si el prereq té els camps de visualització estructurada
        # (`initial_equation`, `explanation_steps`, `explanation_summary`),
        # passem-los també al missatge `prereq_failed` perquè l'UI els
        # renderitzi simètricament al cas de resolt: caixa amb passos
        # alineats, fraccions visuals, etc. La diferència és només el
        # color (groc enlloc de verd) i la frase de capçalera ("La
        # resposta no era correcta" enlloc de "Correcte").
        _failed_extra = {}
        if prereq.get("initial_equation") and prereq.get("explanation_steps"):
            _failed_extra = {
                "initial_equation": prereq["initial_equation"],
                "steps": prereq["explanation_steps"],
                "summary": prereq.get("explanation_summary", ""),
                "cta": "Continua amb la resolució de l'equació.",
            }
        _push_msg(state, "prereq_failed",
                  "La resposta no era correcta.",
                  target="main", persistent=True, extra=_failed_extra)
    return state


def _levenshtein(a: str, b: str) -> int:
    """Distància d'edició entre dues cadenes."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1,
                            prev[j] + (0 if ca == cb else 1)))
        prev = curr
    return prev[-1]


def _fuzzy_keyword_match(keyword: str, text_words: list):
    """Retorna la paraula mal escrita si s'assembla prou a keyword (Levenshtein),
    o None si no hi ha coincidència.
    Paraules curtes (<=3 cars) exigeixen coincidència exacta.
    Llindar: max(1, len(keyword)//4) — 1 errada per cada 4 caràcters."""
    kw = keyword.lower()
    if len(kw) <= 3:
        return kw if kw in text_words else None
    threshold = max(1, len(kw) // 4)
    for w in text_words:
        if _levenshtein(kw, w) <= threshold:
            return w
    return None


def _check_prereq_answer(prereq, raw_text):
    """Avaluació determinista del prerequisit segons el camp present.
    Retorna True (correcte), False (incorrecte) o "typo" (correcte de
    fons però amb errada ortogràfica detectada per distància d'edició)."""
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
        words = s_low.split()
        has_exact = any(kw.lower() in s_low for kw in prereq["keywords_required"])
        typo_word = None
        if not has_exact:
            for kw in prereq["keywords_required"]:
                found = _fuzzy_keyword_match(kw, words)
                if found:
                    typo_word = found
                    break
        if not has_exact and typo_word is None:
            return False
        forbidden = prereq.get("forbidden_keywords", [])
        if any(kw.lower() in s_low for kw in forbidden):
            return False
        if typo_word:
            return ("typo", typo_word)  # tuple: correcte però amb errada
        return True

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
                  "S'ha detectat un ús inadequat del sistema. La sessió es tanca i el "
                  "rastre queda registrat.")
        return state

    _push_msg(state, "warning",
              f"Avís {n}/{MAX_INAPPROPRIATE_WARNINGS}: la resposta no conté contingut "
              "matemàtic. Recorda que pots activar el botó \"Pista\".")
    return state


# ------------------------------------------------------------
# Generació del rastre JSON final
# ------------------------------------------------------------
def build_trace(state: dict) -> dict:
    duration = time.time() - state["started_at_ts"]
    return {
        "alumne": state["student_id"],
        "session_id": state["session_id"],
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


# ------------------------------------------------------------
# Mode debug: test exhaustiu del flux end-to-end
# ------------------------------------------------------------
def run_exhaustive_test(problem_id: str, on_progress=None,
                        session_id: str = None) -> list:
    """
    Executa una bateria de rondes de prova contra el tutor per a un
    problema. Per a cada ronda:
      - Es prova cada input contra una còpia profunda del baseline.
      - El primer input de cada ronda ha de ser una resposta correcta.
      - Després dels tests, el baseline avança usant aquesta resposta
        correcta i passem a la ronda següent.

    No modifica cap estat compartit: tot es fa sobre còpies. El baseline
    parteix sempre de l'enunciat (no de l'estat actual de la sessió),
    perquè els tests siguin reproduïbles.

    Aïllament de logging: aquesta funció reescriu el context del thread
    a (student_id='__test_exhaustiu__', session_id=<id efímer>) per no
    contaminar les analítiques de l'alumne real. El context anterior es
    restaura al final via try/finally.

    `on_progress(round_idx, n_rounds, input_idx, n_inputs)`: callback
    opcional que la UI pot usar per mostrar progrés (cada input pot
    trigar segons depenent del model).

    `session_id`: id de sessió a fer servir per al logging d'aquesta
    execució. Si no s'especifica, se'n genera un nou. Útil quan el
    caller vol agregar després el cost via `summarize_session(sid)`.

    Retorna una llista de dicts (un per ronda) amb la forma:
        {
          "round": int,
          "from_eq": str,        # equació de partida d'aquesta ronda
          "items": [
              {
                "input": str,
                "expected": "correct" | "error",
                "verdict": str,
                "error_label": str | None,
                "feedback": str,
                "prereq_triggered": str | None,
                "prereq_question": str | None,
                "match": bool,    # esperat coincideix amb obtingut?
                "exception": str | None,
              },
              ...
          ]
        }
    """
    rounds = PB.get_test_cases(problem_id)
    if not rounds:
        return []

    test_sid = session_id or uuid.uuid4().hex[:12]
    _prev_student, _prev_session = L.get_log_context()
    L.set_log_context(
        student_id="__test_exhaustiu__",
        session_id=test_sid,
    )
    try:
        return _run_exhaustive_test_inner(rounds, problem_id, on_progress)
    finally:
        L.set_log_context(student_id=_prev_student, session_id=_prev_session)


def _run_exhaustive_test_inner(rounds, problem_id, on_progress):
    baseline = new_session_state(problem_id, student_id="__test_exhaustiu__")
    all_results = []

    for round_idx, round_inputs in enumerate(rounds, start=1):
        from_eq = baseline["history"][-1]["text"]
        round_data = {"round": round_idx, "from_eq": from_eq, "items": []}

        for input_idx, raw_input in enumerate(round_inputs):
            if on_progress is not None:
                try:
                    on_progress(round_idx, len(rounds),
                                input_idx + 1, len(round_inputs))
                except Exception:
                    pass

            expected = "correct" if input_idx == 0 else "error"
            test_state = copy.deepcopy(baseline)
            item = {
                "input": raw_input,
                "expected": expected,
                "verdict": None,
                "error_label": None,
                "feedback": "",
                "prereq_triggered": None,
                "prereq_question": None,
                "match": False,
                "exception": None,
            }
            try:
                process_turn(test_state, raw_input)
            except Exception as e:
                item["exception"] = str(e)
                round_data["items"].append(item)
                continue

            last = test_state["history"][-1] if test_state["history"] else {}
            verdict = last.get("verdict", "?")
            item["verdict"] = verdict
            item["error_label"] = last.get("error_label")

            feedbacks = [m["text"] for m in test_state.get("messages", [])
                         if m.get("kind") == "feedback"]
            item["feedback"] = feedbacks[0] if feedbacks else ""

            prereq_id = test_state.get("active_prereq")
            item["prereq_triggered"] = prereq_id
            if prereq_id:
                pq = PB.get_prerequisite(prereq_id)
                if pq:
                    item["prereq_question"] = pq.get("question")

            # Coincidència esperat vs obtingut: simplifiquem a "correcte"
            # vs "error". Distingim una excepció, que sempre és un mismatch.
            is_correct = verdict in ("correcte_progres", "correcte_estancat")
            is_error = verdict in ("error", "no_math")
            if expected == "correct":
                item["match"] = is_correct
            else:
                item["match"] = is_error

            round_data["items"].append(item)

        all_results.append(round_data)

        # Avançar el baseline amb la resposta correcta cap a la ronda
        # següent. Si falla, no té sentit continuar.
        try:
            process_turn(baseline, round_inputs[0])
        except Exception:
            break

    return all_results
