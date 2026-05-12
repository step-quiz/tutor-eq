"""
Simulador de sessions del tutor: executa trajectòries scriptades end-to-end
sense fer cap crida real a la IA.

Per què existeix
================
`test_verifier.py` cobreix la capa determinista. `test_problems.py` i
`test_problems_properties.py` cobreixen la base de dades. Però la lògica
nuclear del tutor — la màquina d'estats de `tutor.process_turn`, amb tots
els escapaments, retrocessos, escalades, suspensions — no està testada
en cap suite. La única cosa que s'hi acosta és el "Test exhaustiu" del
mode debug, que fa crides reals a la IA, té cost, i prova el classificador,
no la lògica de control.

Aquest mòdul mocka `llm` amb respostes predeterministes i exerceix la
màquina d'estats amb seqüències d'inputs concretes, comprovant les
transicions clau. La cobertura ha de créixer cada vegada que s'afegeixi
una branca nova a `process_turn` o algun bug arquitectural surti al pilot.

Cada escenari valida tres coses:
  1. La seqüència de veredicts gravats a `history`
  2. El `verdict_final`
  3. Una o més propietats específiques de l'escenari

Tot passa per `process_turn`, així que els invariants estructurals
(invariants.py) també es validen automàticament.

Executar amb:
    python -m unittest test_session_simulator -v
"""

import unittest
from unittest.mock import patch

import invariants as INV
import tutor


# ============================================================
# Mock helpers
# ============================================================
class LLMScript:
    """
    Conjunt de respostes predeterministes per a les crides a llm. Cada
    test instancia un LLMScript amb el guió específic que vol exercitar.

    Camps:
      judge_progress     — dict fix o list (consum FIFO)
      classify_error     — dict fix o list (consum FIFO)
      interpret_input    — dict fix o list (consum FIFO)
      generate_hint      — str
      generate_worked_example — str
      generate_concrete_step  — str

    Si una crida esgota la llista, es repeteix l'última. Si una crida
    no esperada arriba, es retorna un default segur.
    """

    DEFAULT_PROGRESS = {"verdict": "progres", "reason": ""}
    DEFAULT_STAGNANT = {"verdict": "estancat", "reason": ""}
    DEFAULT_ERROR = {
        "error_label": "GEN_other",
        "is_conceptual": False,
        "dep_id": None,
        "short_msg": "Hi ha un error.",
    }
    DEFAULT_INTERPRET_NO_EQ = {
        "verdict": "no_eq",
        "reconstruction": None,
        "short_msg": "No entenc.",
    }

    def __init__(self, **kw):
        self._scripts = {}
        for name, val in kw.items():
            if isinstance(val, list):
                self._scripts[name] = list(val)
            else:
                self._scripts[name] = [val]
        self.calls = {name: 0 for name in self._scripts}

    def _next(self, name, default):
        if name not in self._scripts:
            return default
        self.calls[name] = self.calls.get(name, 0) + 1
        lst = self._scripts[name]
        if not lst:
            return default
        if len(lst) == 1:
            return lst[0]
        return lst.pop(0)

    def judge_progress(self, *args, **kw):
        return self._next("judge_progress", self.DEFAULT_PROGRESS)

    def classify_error(self, *args, **kw):
        return self._next("classify_error", self.DEFAULT_ERROR)

    def interpret_input(self, *args, **kw):
        return self._next("interpret_input", self.DEFAULT_INTERPRET_NO_EQ)

    def generate_hint(self, *args, **kw):
        return self._next("generate_hint", "Pista de mostra.")

    def generate_worked_example(self, *args, **kw):
        return self._next("generate_worked_example", "Exemple de mostra.")

    def generate_concrete_step(self, *args, **kw):
        return self._next("generate_concrete_step", "Pas concret de mostra.")


def _patch_llm(script: LLMScript):
    """Retorna una llista de patchers actius pels mètodes que mocker."""
    patchers = [
        patch("llm.judge_progress", side_effect=script.judge_progress),
        patch("llm.classify_error", side_effect=script.classify_error),
        patch("llm.interpret_input", side_effect=script.interpret_input),
        patch("llm.generate_hint", side_effect=script.generate_hint),
        patch("llm.generate_worked_example",
              side_effect=script.generate_worked_example),
        patch("llm.generate_concrete_step",
              side_effect=script.generate_concrete_step),
    ]
    return patchers


class ScenarioCase(unittest.TestCase):
    """Helper base: arrenca i ferma patchers automàticament."""

    def run_scenario(self, problem_id, inputs, script=None):
        """
        Executa `inputs` sobre una nova sessió de `problem_id` amb el
        `script` de LLM mockejat. Retorna l'estat final.

        Els invariants s'apliquen a cada torn (via tutor.process_turn).
        """
        if script is None:
            script = LLMScript()
        patchers = _patch_llm(script)
        for p in patchers:
            p.start()
        try:
            state = tutor.new_session_state(problem_id, student_id="__sim__")
            for raw in inputs:
                tutor.process_turn(state, raw)
            return state
        finally:
            for p in patchers:
                p.stop()

    # Helpers d'assertion específics
    def assertVerdictSequence(self, state, expected):
        """Comprova la seqüència de veredicts a history (ometent 'inicial')."""
        actual = [h["verdict"] for h in state["history"]
                  if h["verdict"] != "inicial"]
        self.assertEqual(
            actual, expected,
            f"seqüència de veredicts: {actual}, esperada {expected}",
        )

    def assertFinalVerdict(self, state, expected):
        self.assertEqual(
            state["verdict_final"], expected,
            f"verdict_final={state['verdict_final']!r}, esperat {expected!r}",
        )

    def assertLastErrorLabel(self, state, expected):
        last_err = None
        for h in reversed(state["history"]):
            if h["verdict"] == "error":
                last_err = h.get("error_label")
                break
        self.assertEqual(
            last_err, expected,
            f"darrer error_label={last_err!r}, esperat {expected!r}",
        )


# ============================================================
# Escenaris
# ============================================================
class TestHappyPath(ScenarioCase):
    """L'alumne resol el problema en pocs passos correctes."""

    def test_one_step_resolution(self):
        # x + 7 = 12  → x = 5
        state = self.run_scenario("EQ1-A-001", ["x = 5"])
        self.assertVerdictSequence(state, ["correcte_progres"])
        self.assertFinalVerdict(state, "resolt")

    def test_two_step_resolution(self):
        # 3x − 5 = 10  → 3x = 15  → x = 5
        state = self.run_scenario("EQ2-A-001", ["3x = 15", "x = 5"])
        self.assertVerdictSequence(state, ["correcte_progres", "correcte_progres"])
        self.assertFinalVerdict(state, "resolt")


class TestEscapeSignals(ScenarioCase):
    """Senyals d'escapament: !!, !text, ?."""

    def test_exit_signal(self):
        state = self.run_scenario("EQ1-A-001", ["!!"])
        self.assertFinalVerdict(state, "abandonat")
        # !! NO genera entrada a history
        self.assertEqual(len(state["history"]), 1)  # només 'inicial'

    def test_discrepancy_signal_does_not_count_as_error(self):
        state = self.run_scenario(
            "EQ1-A-001",
            ["!això no ho entenc", "x = 5"],
        )
        self.assertEqual(len(state["discrepancies"]), 1)
        self.assertEqual(state["discrepancies"][0]["text_alumne"],
                         "això no ho entenc")
        self.assertFinalVerdict(state, "resolt")

    def test_help_signal_generates_hint(self):
        script = LLMScript(generate_hint="Pensa en quin nombre li hem de restar.")
        state = self.run_scenario("EQ1-A-001", ["?"], script=script)
        self.assertEqual(len(state["hints_requested"]), 1)
        self.assertEqual(state["hints_requested"][0]["context"], "principal")
        # ? NO genera entrada a history
        self.assertEqual(len(state["history"]), 1)


class TestInappropriateUseSuspension(ScenarioCase):
    """3 inputs no-matemàtics consecutius → suspensió."""

    def test_three_strikes_suspend(self):
        state = self.run_scenario(
            "EQ1-A-001",
            ["patata", "no ho sé", "buf"],
        )
        self.assertFinalVerdict(state, "suspes_us_inadequat")
        self.assertEqual(state["inappropriate_warnings"], 3)
        # Tots tres queden gravats com a no_math
        no_math_steps = [h for h in state["history"] if h["verdict"] == "no_math"]
        self.assertEqual(len(no_math_steps), 3)

    def test_math_input_resets_warning_counter(self):
        # patata, patata, x = 5 → es resol, no se suspèn
        state = self.run_scenario(
            "EQ1-A-001",
            ["patata", "no", "x = 5"],
        )
        self.assertEqual(state["inappropriate_warnings"], 0)
        self.assertFinalVerdict(state, "resolt")


class TestStagnationDetection(ScenarioCase):
    """Dos estancaments consecutius → oferta proactiva."""

    def test_two_stagnant_triggers_offer(self):
        # judge_progress retorna 'estancat' dues vegades → oferta proactiva
        script = LLMScript(
            judge_progress=LLMScript.DEFAULT_STAGNANT,
        )
        # Dos inputs equivalents a x + 7 = 12 que SymPy validarà però que
        # no avancen cap a x = 5.
        state = self.run_scenario(
            "EQ1-A-001",
            ["x + 7 − 0 = 12", "x + 0 + 7 = 12"],
            script=script,
        )
        self.assertEqual(state["stagnation_consecutive"], 2)
        self.assertTrue(state["pending_proactive_offer"])

    def test_progress_resets_stagnation(self):
        # Tres inputs:
        #  1) literalment l'enunciat → estancat via is_same_text (no crida LLM)
        #  2) reformulació equivalent → estancat via judge_progress mock
        #  3) progrés cap a la solució → reset
        # Si fos terminal el 3r, la branca correcte_terminal no crida
        # _post_verdict_bookkeeping (veure TODO_DEFERRED.md, finding F1).
        # Per això el 3r pas és intermedi (3x = 15, no x = 5).
        script = LLMScript(judge_progress=[
            LLMScript.DEFAULT_STAGNANT,
            LLMScript.DEFAULT_PROGRESS,
        ])
        state = self.run_scenario(
            "EQ2-A-001",
            ["3x − 5 = 10", "3x − 5 + 0 = 10", "3x = 15"],
            script=script,
        )
        self.assertEqual(state["stagnation_consecutive"], 0)
        self.assertFalse(state["pending_proactive_offer"])
        # Però stagnation_max conserva el pic
        self.assertEqual(state["stagnation_max"], 2)


class TestCoefficientPreCheck(ScenarioCase):
    """
    Pre-check determinista: si el coeficient de x canvia a un valor que
    no és ±1, és error aritmètic SENSE crida a la IA. Atrapa el bug A3:
    la IA al·lucinava causes per a errors purs de coeficient.
    """

    def test_coefficient_change_caught_without_llm(self):
        # 3x − 5 = 10 → l'alumne escriu 5x = 15 (canvia coef de 3 a 5)
        # Aquest pre-check ha de disparar; classify_error NO s'ha de cridar.
        script = LLMScript(
            classify_error={
                # Si això es cridés, marcaria el test com a fallit
                "error_label": "L2_transpose_sign",  # valor "intrús"
                "is_conceptual": False,
                "dep_id": None,
                "short_msg": "Aquesta IA no s'hauria d'haver cridat.",
            },
        )
        state = self.run_scenario(
            "EQ2-A-001",
            ["5x = 15"],
            script=script,
        )
        self.assertLastErrorLabel(state, "GEN_arithmetic")
        # La IA de classify NO s'ha cridat
        self.assertEqual(script.calls.get("classify_error", 0), 0)


class TestFormValidation(ScenarioCase):
    """Validació determinista de la forma de l'equació."""

    def test_non_linear_rejected_without_llm(self):
        script = LLMScript()
        state = self.run_scenario("EQ1-A-001", ["x^2 = 4"], script=script)
        self.assertLastErrorLabel(state, "FORM_non_linear")
        self.assertEqual(script.calls.get("classify_error", 0), 0)

    def test_foreign_variable_rejected_without_llm(self):
        script = LLMScript()
        state = self.run_scenario("EQ1-A-001", ["y + 7 = 12"], script=script)
        self.assertLastErrorLabel(state, "FORM_foreign_var")
        self.assertEqual(script.calls.get("classify_error", 0), 0)

    def test_no_variable_rejected_without_llm(self):
        script = LLMScript()
        state = self.run_scenario("EQ1-A-001", ["5 + 7 = 12"], script=script)
        self.assertLastErrorLabel(state, "FORM_no_variable")
        self.assertEqual(script.calls.get("classify_error", 0), 0)


class TestTerminalRawTextRegression(ScenarioCase):
    """
    Regressió del bug B4: l'alumne escriu `2x/2 = 8/2`. SymPy simplifica
    a x = 4 i podria declarar el problema resolt. La comprovació textual
    a is_terminal ha d'evitar-ho: l'equació és correcta però NO terminal.
    """

    def test_unsimplified_form_is_not_treated_as_terminal(self):
        # 3x − 5 = 10 → 3x = 15 (correcte progres), després "3x/3 = 15/3"
        # No s'ha aïllat la x literalment, no és terminal.
        # judge_progress simulat com a 'progres' (per simplicitat)
        script = LLMScript()
        state = self.run_scenario(
            "EQ2-A-001",
            ["3x = 15", "3x/3 = 15/3"],
            script=script,
        )
        # No s'ha de declarar resolt: el segon pas és correcte_progres
        # però verdict_final continua sent None (no terminal).
        self.assertFinalVerdict(state, None)


class TestPrerequisiteBacktrack(ScenarioCase):
    """
    Error amb dependència implícita → s'activa prereq → resposta
    correcta del prereq → es tanca i continua amb l'equació original.
    """

    def test_prereq_activates_on_implied_dependency(self):
        # Provoquem un error L3_distribution_partial sobre un problema
        # que té prop_distributiva a deps. La IA marca is_conceptual=False
        # però el fallback determinista (implied_dependency_for_error)
        # ha d'activar igualment el prereq.
        script = LLMScript(
            classify_error={
                "error_label": "L3_distribution_partial",
                "is_conceptual": False,
                "dep_id": None,
                "short_msg": "Has distribuït parcialment.",
            },
        )
        # 3(x − 4) = 9, error: l'alumne escriu 3x − 4 = 9 (distribució
        # parcial). No equivalent a l'original ⇒ activa prereq.
        state = self.run_scenario(
            "EQ3-A-001",
            ["3x − 4 = 9"],
            script=script,
        )
        self.assertEqual(state["active_prereq"], "PRE-DIST")
        self.assertEqual(state["active_prereq_depth"], 1)
        self.assertEqual(state["backtrack_count"], 1)

    def test_prereq_resolves_and_returns_to_main(self):
        # Provoquem prereq i el resolem
        script = LLMScript(
            classify_error={
                "error_label": "L3_distribution_partial",
                "is_conceptual": False,
                "dep_id": None,
                "short_msg": "x",
            },
        )
        # PRE-DIST espera una resposta concreta — mirem què demana
        import problems as PB
        pq = PB.get_prerequisite("PRE-DIST")
        # PRE-DIST té expected_equation o expected_value: en busquem el camp
        if "expected_value" in pq:
            correct_answer = str(pq["expected_value"])
        elif "expected_equation" in pq:
            correct_answer = pq["expected_equation"]
        elif "expected_equation_or_expr" in pq:
            correct_answer = pq["expected_equation_or_expr"]
        else:
            self.skipTest("PRE-DIST té format inesperat")

        state = self.run_scenario(
            "EQ3-A-001",
            ["3x − 4 = 9", correct_answer],
            script=script,
        )
        # Prereq tancat
        self.assertIsNone(state["active_prereq"])
        self.assertEqual(state["active_prereq_depth"], 0)
        # Però backtrack_depth_max recorda el pic
        self.assertEqual(state["backtrack_depth_max"], 1)


class TestConceptFailureEscalation(ScenarioCase):
    """
    streak == 1 → prereq, streak == 2 → worked_example, streak ≥ 3 →
    concrete_step. Atrapa regressions a l'escalada d'ajuda.
    """

    def test_second_failure_triggers_worked_example(self):
        # Dos errors consecutius del mateix concepte conceptual.
        script = LLMScript(
            classify_error={
                "error_label": "L3_distribution_partial",
                "is_conceptual": True,
                "dep_id": "prop_distributiva",
                "short_msg": "x",
            },
            generate_worked_example="EXEMPLE_RESOLT",
        )
        # Després del primer error → prereq activat. Per provocar el segon
        # error, primer hem de tancar el prereq (responent malament,
        # cosa que continua però no torna a obrir prereq).
        import problems as PB
        pq = PB.get_prerequisite("PRE-DIST")
        wrong_for_prereq = "resposta_incorrecta_qualsevol"

        state = self.run_scenario(
            "EQ3-A-001",
            ["3x − 4 = 9", wrong_for_prereq, "3x − 4 = 9"],
            # ↑ error #1 (activa prereq) → resposta dolenta al prereq
            #   (tanca prereq amb prereq_failed) → error #2 del mateix
            #   concepte (streak=2 → worked_example)
            script=script,
        )
        # Streak final ha de ser 2
        self.assertEqual(
            state["concept_failure_streak"].get("prop_distributiva"), 2)
        # Worked example ha estat generat
        self.assertGreaterEqual(script.calls.get("generate_worked_example", 0), 1)

    def test_third_failure_triggers_concrete_step(self):
        script = LLMScript(
            classify_error={
                "error_label": "L3_distribution_partial",
                "is_conceptual": True,
                "dep_id": "prop_distributiva",
                "short_msg": "x",
            },
            generate_worked_example="EXEMPLE",
            generate_concrete_step="PAS_CONCRET",
        )
        state = self.run_scenario(
            "EQ3-A-001",
            ["3x − 4 = 9",      # error 1 → prereq
             "resp_dolenta",     # tanca prereq amb failed
             "3x − 4 = 9",       # error 2 → worked_example
             "3x − 4 = 9"],      # error 3 → concrete_step
            script=script,
        )
        self.assertEqual(
            state["concept_failure_streak"].get("prop_distributiva"), 3)
        self.assertGreaterEqual(script.calls.get("generate_concrete_step", 0), 1)


class TestBacktrackDepthLimit(ScenarioCase):
    """
    El retrocés no pot anar més enllà de MAX_BACKTRACK_DEPTH=2 nivells.
    Si l'alumne acumula errors profunds, no s'obren més prereqs niats.
    """

    def test_depth_never_exceeds_max(self):
        # Provoquem repetidament errors conceptuals. La invariant
        # estructural d'invariants.py ja garanteix que active_prereq_depth
        # <= MAX_BACKTRACK_DEPTH; aquí ho verifiquem amb una seqüència
        # plausible.
        script = LLMScript(
            classify_error={
                "error_label": "L3_distribution_partial",
                "is_conceptual": True,
                "dep_id": "prop_distributiva",
                "short_msg": "x",
            },
        )
        # Forcem múltiples cicles d'error → prereq → tanca → error
        state = self.run_scenario(
            "EQ3-A-001",
            ["3x − 4 = 9", "wrong", "3x − 4 = 9", "wrong", "3x − 4 = 9"],
            script=script,
        )
        # En cap moment active_prereq_depth ha pogut superar 2 (l'invariant
        # ho hauria detectat); ho verifiquem també directament.
        self.assertLessEqual(state["active_prereq_depth"],
                             tutor.MAX_BACKTRACK_DEPTH)
        self.assertLessEqual(state["backtrack_depth_max"],
                             tutor.MAX_BACKTRACK_DEPTH)


class TestEquivalentInputWithoutProgress(ScenarioCase):
    """
    Si l'alumne escriu literalment la mateixa equació, no fa falta cridar
    judge_progress: la lògica detecta 'is_same_text' i marca estancat
    directament. Atrapa una possible regressió que cridi LLM sense
    necessitat (cost).
    """

    def test_identical_repetition_does_not_call_llm(self):
        script = LLMScript()
        state = self.run_scenario(
            "EQ1-A-001",
            ["x + 7 = 12"],  # exactament l'enunciat
            script=script,
        )
        # No s'ha de cridar judge_progress
        self.assertEqual(script.calls.get("judge_progress", 0), 0)
        # Però sí s'ha gravat com a correcte_estancat
        self.assertVerdictSequence(state, ["correcte_estancat"])


class TestUnicodeEqualsRegression(ScenarioCase):
    """
    Regressió del bug B1: `＝` (fullwidth equals, teclat mòbil asiàtic)
    s'ha de normalitzar a `=` i parsejar correctament.
    """

    def test_fullwidth_equals_is_accepted(self):
        # x ＝ 5 (amb fullwidth) → ha de parsejar i resoldre
        state = self.run_scenario("EQ1-A-001", ["x ＝ 5"])
        self.assertVerdictSequence(state, ["correcte_progres"])
        self.assertFinalVerdict(state, "resolt")


@unittest.skipIf(
    __import__("os").environ.get("TUTOR_INVARIANTS", "on").lower() == "off",
    "Tests d'invariants es salten quan TUTOR_INVARIANTS=off",
)
class TestInvariantsTriggerOnBrokenState(unittest.TestCase):
    """Sanity: si manipulem l'estat directament i el trenquem, els
    invariants detecten la inconsistència. No és un test de la lògica
    del tutor sinó d'invariants.py."""

    def test_negative_counter_detected(self):
        state = tutor.new_session_state("EQ1-A-001")
        state["inappropriate_warnings"] = -5
        with self.assertRaises(INV.InvariantViolation):
            INV.check_state_invariants(state)

    def test_inconsistent_prereq_detected(self):
        state = tutor.new_session_state("EQ1-A-001")
        state["active_prereq"] = "PRE-NEG"
        # depth no actualitzat ⇒ inconsistència
        with self.assertRaises(INV.InvariantViolation):
            INV.check_state_invariants(state)

    def test_suspes_without_warnings_detected(self):
        state = tutor.new_session_state("EQ1-A-001")
        state["verdict_final"] = "suspes_us_inadequat"
        # No hi ha avisos acumulats ⇒ no quadra
        with self.assertRaises(INV.InvariantViolation):
            INV.check_state_invariants(state)


if __name__ == "__main__":
    unittest.main()
