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


def _push_msg(state, kind: str, text: str, target: str = "main"):
    """
    kind:   'system' | 'feedback' | 'hint' | 'warning' | 'prereq' |
            'discrepancy' | 'worked_example' | 'concrete_step' |
            'prereq_resolved' | 'prereq_failed'
    target: 'main' (panell principal) | 'prereq' (panell dret quan hi ha
            sub-tasca activa).
    El render decideix on mostrar cada missatge segons el target.
    """
    state["messages"].append({"kind": kind, "text": text,
                              "target": target, "ts": time.time()})


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
            return _handle_inappropriate(state, raw_text, ia_already_judged=True)

        text_to_record = ia.get("reconstruction") or raw_text
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
        if V.is_terminal(new_eq):
            sol = V.solve_for_x(new_eq)
            if str(sol) == target_sol:
                _record_step(state, raw_text, parsed_ok=True,
                             verdict="correcte_progres")
                state["verdict_final"] = "resolt"
                _push_msg(state, "feedback",
                          f"Correcte. x = {sol}. Equació resolta, felicitats!")
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
            _push_msg(state, "feedback",
                      "L'equació és correcta, però no t'acosta més a la solució. "
                      f"{jp.get('reason','')}".strip())

        _post_verdict_bookkeeping(state, v, original_text)
        return state

    # No equivalent a l'original: és un error.
    # Passem a la IA també el darrer pas correcte, perquè la classificació
    # es centri en la transformació local (last_correct → attempt) i no
    # confongui errors aritmètics simples amb errors de distribució a
    # només perquè l'enunciat tingui parèntesis.
    # També li passem els errors recents (Move 1): així pot detectar
    # patrons (p. ex. tres distribucions parcials seguides) i ajustar
    # tant la classificació com el to del missatge.
    last_correct = _last_correct_step_text(state)
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

    _record_step(state, raw_text, parsed_ok=True,
                 verdict="error", error_label=ce["error_label"])
    _push_msg(state, "feedback", ce["short_msg"])

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
                      "Sembla que estàs donant voltes. Pots clicar al botó de la columna esquerra \"Vull una pista\".")
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
# Subflux: prerequisits (mini-sessions)
# ------------------------------------------------------------
def _select_prereq_id(error_label: str, dep: dict, last_correct_text: str) -> str:
    """
    Tria el prerequisit més adequat per a aquest error concret. Per
    defecte, la dependència té un sol prerequisit (`dep["prerequisite"]`),
    però algunes dependències com `operacions_inverses` cobreixen dos
    casos diferents (additiu i multiplicatiu) i necessiten triar variant
    segons la forma de l'última equació vàlida:

      Última equació: 3x = 21  → operació pendent: dividir → PRE-INV-MULT
      Última equació: x + 5 = 12 → operació pendent: restar → PRE-INV

    Així evitem el mismatch pedagògic en què l'alumne confon dividir amb
    restar però el sistema li pregunta com aïllar la x d'una suma.
    """
    default = dep["prerequisite"]

    if error_label == "L1_inverse_op":
        eq = V.parse_equation(last_correct_text)
        op_type = V.next_operation_type(eq)
        if op_type == "multiplicative" and PB.get_prerequisite("PRE-INV-MULT"):
            return "PRE-INV-MULT"
        # Additiu o indeterminat: ens quedem amb el prerequisit per defecte.

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
              "Cal treballar abans un exercici de reforç.",
              target="main")


def _process_prereq_turn(state, raw_text):
    prereq = PB.get_prerequisite(state["active_prereq"])
    correct = _check_prereq_answer(prereq, raw_text)
    explanation = prereq.get("explanation", "")
    prereq_id = prereq.get("id", state["active_prereq"])

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
        _push_msg(state, "prereq_resolved",
                  f"Exercici {prereq_id}: superat correctament. {explanation}\n\n"
                  f"**Ara, aplica el que has après a la teva equació original.**",
                  target="main")
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
        _push_msg(state, "prereq_failed",
                  f"Exercici {prereq_id}: la teva resposta no és correcta. "
                  f"La solució és aquesta: {explanation}\n\n"
                  f"**Ara ja pots intentar resoldre l'equació original.**",
                  target="main")
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
        # Comprovació positiva: ha d'aparèixer alguna keyword esperada.
        has_required = any(kw.lower() in s_low for kw in prereq["keywords_required"])
        if not has_required:
            return False
        # Comprovació negativa: certs prereqs declaren keywords que
        # invaliden la resposta encara que també hi hagi una de positiva
        # (ex: si el prereq demana dividir, "multiplico per 3" no val
        # encara que contingués "/3" per qualsevol motiu).
        forbidden = prereq.get("forbidden_keywords", [])
        if any(kw.lower() in s_low for kw in forbidden):
            return False
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
              "matemàtic. Recorda que pots activar el botó per demanar ajuda, o bé sortir.")
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
def run_exhaustive_test(problem_id: str, on_progress=None) -> list:
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

    `on_progress(round_idx, n_rounds, input_idx, n_inputs)`: callback
    opcional que la UI pot usar per mostrar progrés (cada input pot
    trigar segons depenent del model).

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

    # Aïllem el context de logging del test perquè les crides a l'API
    # no quedin etiquetades amb l'alumne real (si app.py n'havia fixat
    # un). Capturem el context actual per restaurar-lo al final.
    _prev_student, _prev_session = L.get_log_context()
    L.set_log_context(
        student_id="__test_exhaustiu__",
        session_id=uuid.uuid4().hex[:12],
    )
    try:
        return _run_exhaustive_test_inner(rounds, problem_id, on_progress)
    finally:
        # Restaurem el context anterior (o el deixem buit si no n'hi havia).
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
