"""
Tests d'integritat de la base de dades de problemes (`problems.py`).

L'objectiu és atrapar errors d'autoria sense haver d'executar el "Test
exhaustiu" del runner (que requereix crides reals a la IA i té cost). Aquí
només verifiquem invariants deterministes del verifier.

Si algú afegeix un problema nou que viola una d'aquestes invariants
(per ex. un error que SymPy considera equivalent), el test falla
immediatament i en local.

Executar amb: python -m unittest test_problems -v
"""

import unittest

import problems as PB
import verifier as V


class TestProblemSchemaIntegrity(unittest.TestCase):
    """Cada problema té els camps obligatoris i les referències resolen."""

    REQUIRED_FIELDS = {
        "id", "familia", "nivell", "tema", "equacio_text", "solucio",
        "dependencies", "errors_freqüents",
    }

    def test_all_problems_have_required_fields(self):
        for pid, prob in PB.PROBLEMS.items():
            with self.subTest(problem=pid):
                missing = self.REQUIRED_FIELDS - set(prob.keys())
                self.assertEqual(missing, set(),
                                 f"{pid} té camps obligatoris a faltar: {missing}")

    def test_id_matches_dict_key(self):
        for pid, prob in PB.PROBLEMS.items():
            with self.subTest(problem=pid):
                self.assertEqual(prob["id"], pid)

    def test_familia_matches_id_prefix(self):
        # Convenció: id té format EQ{nivell}-{família}-{seq}
        for pid, prob in PB.PROBLEMS.items():
            with self.subTest(problem=pid):
                self.assertTrue(pid.startswith(prob["familia"] + "-"),
                                f"{pid}: familia={prob['familia']} no concorda amb l'id")

    def test_nivell_in_range(self):
        for pid, prob in PB.PROBLEMS.items():
            with self.subTest(problem=pid):
                self.assertIn(prob["nivell"], (1, 2, 3, 4))

    def test_dependencies_resolve(self):
        for pid, prob in PB.PROBLEMS.items():
            for dep in prob["dependencies"]:
                with self.subTest(problem=pid, dependency=dep):
                    self.assertIsNotNone(PB.get_dependency(dep),
                                         f"{pid}: dependència desconeguda {dep!r}")

    def test_errors_freqüents_resolve(self):
        for pid, prob in PB.PROBLEMS.items():
            for err in prob["errors_freqüents"]:
                with self.subTest(problem=pid, error=err):
                    self.assertIn(err, PB.ERROR_CATALOG,
                                  f"{pid}: error label desconegut {err!r}")

    def test_dependencies_point_to_existing_prereqs(self):
        for dep_id, dep in PB.DEPENDENCIES.items():
            prereq_id = dep["prerequisite"]
            with self.subTest(dependency=dep_id):
                self.assertIsNotNone(PB.get_prerequisite(prereq_id),
                                     f"{dep_id}: prereq {prereq_id!r} no existeix")


class TestProblemEquationsAreParseable(unittest.TestCase):
    """L'equació de cada problema parseja, és lineal en x i té la solució declarada."""

    def test_each_equation_parses(self):
        for pid, prob in PB.PROBLEMS.items():
            with self.subTest(problem=pid):
                eq = V.parse_equation(prob["equacio_text"])
                self.assertIsNotNone(eq, f"{pid}: {prob['equacio_text']!r} no parseja")

    def test_each_equation_is_linear(self):
        for pid, prob in PB.PROBLEMS.items():
            with self.subTest(problem=pid):
                eq = V.parse_equation(prob["equacio_text"])
                form = V.validate_equation_form(eq)
                self.assertTrue(form["ok"],
                                f"{pid}: forma no vàlida → {form}")

    def test_declared_solution_matches_sympy(self):
        for pid, prob in PB.PROBLEMS.items():
            with self.subTest(problem=pid):
                eq = V.parse_equation(prob["equacio_text"])
                sympy_sol = V.solve_for_x(eq)
                # Comparem numèricament per cobrir el cas Float vs Rational.
                self.assertEqual(float(sympy_sol), float(prob["solucio"]),
                                 f"{pid}: SymPy={sympy_sol}, declarat={prob['solucio']}")

    def test_equacio_simetria_is_equivalent(self):
        # equacio_simetria, si està present, ha de ser equivalent a equacio_text.
        for pid, prob in PB.PROBLEMS.items():
            sim = prob.get("equacio_simetria")
            if sim is None:
                continue
            with self.subTest(problem=pid):
                eq_orig = V.parse_equation(prob["equacio_text"])
                eq_sim = V.parse_equation(sim)
                self.assertIsNotNone(eq_sim, f"{pid}: equacio_simetria no parseja")
                self.assertTrue(V.equations_equivalent(eq_orig, eq_sim),
                                f"{pid}: equacio_simetria no és equivalent a equacio_text")


class TestTestCasesIntegrity(unittest.TestCase):
    """
    Per cada problema:
      - Hi ha test_cases
      - Per cada ronda, el primer input és equivalent a l'estat actual
        (i.e. és correcte)
      - La resta d'inputs NO són equivalents (i.e. són errors genuïns,
        no camins algebraics vàlids alternatius)
    """

    # Whitelist F0: els 11 problemes integrats el 2026-05-11 (vegeu
    # TODO_DEFERRED.md F0) encara no tenen `TEST_CASES` perquè aquests
    # requereixen disseny pedagògic explícit (errors típics que un alumne
    # de 2n d'ESO faria) i estem esperant al company/professor.
    #
    # Quan els TEST_CASES estiguin escrits per als 11, **treure aquesta
    # llista** (no és necessari treure cada problema un per un — la
    # condició és que la suite passi amb la whitelist buida).
    KNOWN_PENDING_TEST_CASES = {
        "EQ1-D-001",
        "EQ2-E-001", "EQ2-F-001", "EQ2-H-001", "EQ2-I-001", "EQ2-X-001",
        "EQ3-E-001", "EQ3-F-001", "EQ3-G-001", "EQ3-H-001", "EQ3-I-001",
    }

    def test_every_problem_has_test_cases(self):
        for pid in PB.PROBLEMS:
            if pid in self.KNOWN_PENDING_TEST_CASES:
                continue
            with self.subTest(problem=pid):
                rounds = PB.get_test_cases(pid)
                self.assertIsNotNone(rounds, f"{pid} no té test_cases")
                self.assertGreater(len(rounds), 0, f"{pid} té 0 rondes")

    def test_every_round_has_inputs(self):
        for pid, rounds in PB.TEST_CASES.items():
            for r_idx, ronda in enumerate(rounds, 1):
                with self.subTest(problem=pid, round=r_idx):
                    self.assertGreaterEqual(len(ronda), 2,
                                            "una ronda hauria de tenir 1 correcte + ≥1 errors")

    def test_first_input_of_each_round_is_correct(self):
        for pid, rounds in PB.TEST_CASES.items():
            initial_text = PB.get_problem(pid)["equacio_text"]
            state_eq = V.parse_equation(initial_text)

            for r_idx, ronda in enumerate(rounds, 1):
                first_input = ronda[0]
                with self.subTest(problem=pid, round=r_idx, input=first_input):
                    parsed = V.parse_equation(first_input)
                    self.assertIsNotNone(parsed, f"{first_input!r} no parseja")
                    self.assertTrue(
                        V.equations_equivalent(state_eq, parsed),
                        f"{pid} R{r_idx}: el primer input {first_input!r} hauria "
                        f"d'avançar correctament des de {state_eq}",
                    )
                # Avançar el baseline per a la propera ronda
                state_eq = V.parse_equation(first_input)

    def test_non_first_inputs_are_genuine_errors(self):
        # La invariant clau: cap input no-primer ha de ser equivalent
        # a l'estat actual. Si ho és, NO és un error: és una via vàlida
        # que el runner marcaria com a falsa-falla.
        for pid, rounds in PB.TEST_CASES.items():
            initial_text = PB.get_problem(pid)["equacio_text"]
            state_eq = V.parse_equation(initial_text)

            for r_idx, ronda in enumerate(rounds, 1):
                for i_idx, inp in enumerate(ronda[1:], start=1):
                    with self.subTest(problem=pid, round=r_idx, input=inp):
                        parsed = V.parse_equation(inp)
                        # L'error pot no parsejar (cas vàlid: l'alumne escriu
                        # alguna cosa molt malformada). Si parseja, però, NO
                        # ha de ser equivalent.
                        if parsed is not None:
                            self.assertFalse(
                                V.equations_equivalent(state_eq, parsed),
                                f"{pid} R{r_idx} input #{i_idx} {inp!r}: "
                                f"SymPy el considera equivalent a l'estat actual "
                                f"({state_eq}). Això vol dir que NO és un error real "
                                f"sinó un camí algebraic vàlid. Substitueix-lo per "
                                f"un error genuí.",
                            )
                # Avançar el baseline amb el primer input (correcte)
                state_eq = V.parse_equation(ronda[0])


class TestPrerequisiteSchema(unittest.TestCase):
    """Cada prereq té un format vàlid (numèric o per paraules clau)."""

    def test_prereq_id_matches_key(self):
        for pid, pq in PB.PREREQUISITES.items():
            with self.subTest(prereq=pid):
                self.assertEqual(pq["id"], pid)

    def test_prereq_concept_resolves(self):
        for pid, pq in PB.PREREQUISITES.items():
            with self.subTest(prereq=pid):
                self.assertIn(pq["concept"], PB.DEPENDENCIES,
                              f"{pid}: concept {pq['concept']!r} no és a DEPENDENCIES")

    def test_prereq_has_question_and_explanation(self):
        for pid, pq in PB.PREREQUISITES.items():
            with self.subTest(prereq=pid):
                self.assertTrue(pq.get("question"), f"{pid} sense pregunta")
                self.assertTrue(pq.get("explanation"), f"{pid} sense explicació")

    def test_prereq_has_validation_field(self):
        # Cada prereq ha de tenir UN d'aquests 4 camps de validació.
        validation_fields = {"expected_value", "expected_equation",
                             "expected_equation_or_expr", "keywords_required"}
        for pid, pq in PB.PREREQUISITES.items():
            with self.subTest(prereq=pid):
                present = validation_fields & set(pq.keys())
                self.assertEqual(len(present), 1,
                                 f"{pid}: ha de tenir exactament 1 camp de validació, "
                                 f"trobats {present}")


if __name__ == "__main__":
    unittest.main()
