"""
Tests unitaris per a verifier.py.

Cobertura: parsing, solucions, equivalència, classificació d'operació pendent,
detecció de terminal, validació de forma lineal, detecció de contingut
matemàtic, i comparació textual normalitzada. Tots els tests són deterministes
(no fan crides a IA) i ràpids.

Executar amb:
    python -m unittest test_verifier -v
"""

import unittest

from sympy import Rational, sqrt

import verifier as V


# ---------------------------------------------------------------
# parse_equation / parse_expression
# ---------------------------------------------------------------
class TestParseEquation(unittest.TestCase):
    def test_basic_equation_parses(self):
        self.assertIsNotNone(V.parse_equation("x + 7 = 12"))

    def test_implicit_multiplication(self):
        # 3x s'ha de parsejar com 3*x
        eq = V.parse_equation("3x = 21")
        self.assertIsNotNone(eq)
        self.assertEqual(V.solve_for_x(eq), 7)

    def test_unicode_minus(self):
        # − (Unicode minus) i en/em-dash han de funcionar
        self.assertIsNotNone(V.parse_equation("x − 5 = 7"))
        self.assertIsNotNone(V.parse_equation("x – 5 = 7"))
        self.assertIsNotNone(V.parse_equation("x — 5 = 7"))

    def test_unicode_multiplication(self):
        for op in ("·", "×", "*"):
            with self.subTest(op=op):
                eq = V.parse_equation(f"3{op}x = 21")
                self.assertIsNotNone(eq, f"falla operador {op!r}")
                self.assertEqual(V.solve_for_x(eq), 7)

    def test_unicode_division(self):
        eq = V.parse_equation("x ÷ 2 = 3")
        self.assertIsNotNone(eq)
        self.assertEqual(V.solve_for_x(eq), 6)

    def test_caret_as_power(self):
        # ^ s'ha de convertir a ** (transformació convert_xor)
        eq = V.parse_equation("x^2 = 4")
        self.assertIsNotNone(eq)
        # No comprovem solució aquí (no és lineal) — només que parseja

    def test_returns_none_when_no_equals(self):
        self.assertIsNone(V.parse_equation("3x + 5"))

    def test_returns_none_on_empty(self):
        self.assertIsNone(V.parse_equation(""))
        self.assertIsNone(V.parse_equation(None))

    def test_returns_none_with_two_equals(self):
        # "a = b = c" no és una equació vàlida en aquest context
        self.assertIsNone(V.parse_equation("x = 5 = 5"))

    def test_returns_none_on_garbage(self):
        self.assertIsNone(V.parse_equation("x = ??"))

    def test_european_decimal_comma(self):
        # _normalize converteix la coma en punt decimal.
        # Nota: SymPy parseja "2.5" com a Float, no com a Rational.
        # Comparem numèricament per documentar aquest comportament.
        eq = V.parse_equation("x = 2,5")
        self.assertIsNotNone(eq)
        self.assertAlmostEqual(float(V.solve_for_x(eq)), 2.5)


class TestParseExpression(unittest.TestCase):
    def test_basic(self):
        self.assertIsNotNone(V.parse_expression("3*x + 5"))

    def test_unicode(self):
        self.assertIsNotNone(V.parse_expression("3·x − 5"))

    def test_returns_none_on_garbage(self):
        self.assertIsNone(V.parse_expression("@@@"))

    def test_returns_none_on_empty(self):
        self.assertIsNone(V.parse_expression(""))
        self.assertIsNone(V.parse_expression(None))


# ---------------------------------------------------------------
# solve_for_x
# ---------------------------------------------------------------
class TestSolveForX(unittest.TestCase):
    def test_integer_solution(self):
        self.assertEqual(V.solve_for_x(V.parse_equation("x + 7 = 12")), 5)

    def test_negative_solution(self):
        self.assertEqual(V.solve_for_x(V.parse_equation("x + 10 = 3")), -7)

    def test_rational_solution(self):
        # 2x = 3 → x = 3/2
        sol = V.solve_for_x(V.parse_equation("2x = 3"))
        self.assertEqual(sol, Rational(3, 2))

    def test_identitat(self):
        # x = x : qualsevol x és solució
        self.assertEqual(V.solve_for_x(V.parse_equation("x = x")), "identitat")

    def test_sense_solucio(self):
        # 0 = 5 : cap solució
        self.assertEqual(V.solve_for_x(V.parse_equation("0 = 5")),
                         "sense_solucio")

    def test_none_on_none_input(self):
        self.assertIsNone(V.solve_for_x(None))


# ---------------------------------------------------------------
# equations_equivalent
# ---------------------------------------------------------------
class TestEquationsEquivalent(unittest.TestCase):
    def test_same_equation(self):
        eq1 = V.parse_equation("x + 7 = 12")
        eq2 = V.parse_equation("x + 7 = 12")
        self.assertTrue(V.equations_equivalent(eq1, eq2))

    def test_simplified_form(self):
        # x + 7 = 12  ⇔  x = 5
        eq1 = V.parse_equation("x + 7 = 12")
        eq2 = V.parse_equation("x = 5")
        self.assertTrue(V.equations_equivalent(eq1, eq2))

    def test_different_solutions_not_equivalent(self):
        eq1 = V.parse_equation("x + 7 = 12")
        eq2 = V.parse_equation("x = 4")
        self.assertFalse(V.equations_equivalent(eq1, eq2))

    def test_distributed_form_equivalent(self):
        # 3(x − 4) = 9  ⇔  3x − 12 = 9  ⇔  x = 7
        for form in ("3(x − 4) = 9", "3x − 12 = 9", "x = 7"):
            with self.subTest(form=form):
                eq = V.parse_equation(form)
                target = V.parse_equation("x = 7")
                self.assertTrue(V.equations_equivalent(eq, target))

    def test_swapped_sides(self):
        # 12 = x + 7  ⇔  x + 7 = 12
        eq1 = V.parse_equation("x + 7 = 12")
        eq2 = V.parse_equation("12 = x + 7")
        self.assertTrue(V.equations_equivalent(eq1, eq2))

    def test_none_handling(self):
        eq = V.parse_equation("x = 5")
        self.assertFalse(V.equations_equivalent(None, eq))
        self.assertFalse(V.equations_equivalent(eq, None))
        self.assertFalse(V.equations_equivalent(None, None))

    def test_fractional_form(self):
        # x/2 + x/3 = 5  →  x = 6
        eq1 = V.parse_equation("x/2 + x/3 = 5")
        eq2 = V.parse_equation("x = 6")
        self.assertTrue(V.equations_equivalent(eq1, eq2))


# ---------------------------------------------------------------
# next_operation_type
# ---------------------------------------------------------------
class TestNextOperationType(unittest.TestCase):
    def test_additive_with_constant(self):
        # 3x − 12 = 9 : el costat de la x té un terme constant a treure abans
        self.assertEqual(
            V.next_operation_type(V.parse_equation("3x − 12 = 9")),
            "additive",
        )

    def test_additive_simple_sum(self):
        # x + 5 = 12 : pendent restar 5
        self.assertEqual(
            V.next_operation_type(V.parse_equation("x + 5 = 12")),
            "additive",
        )

    def test_multiplicative(self):
        # 3x = 21 : només a*x al costat de la x, amb a≠±1
        self.assertEqual(
            V.next_operation_type(V.parse_equation("3x = 21")),
            "multiplicative",
        )

    def test_terminal_x_equals_const(self):
        # x = 5 : ja és terminal, no hi ha operació pendent
        self.assertEqual(
            V.next_operation_type(V.parse_equation("x = 5")),
            "none",
        )

    def test_terminal_negative_x(self):
        # −x = 5 : coeficient ±1, no és multiplicatiu
        self.assertEqual(
            V.next_operation_type(V.parse_equation("−x = 5")),
            "none",
        )

    def test_x_on_both_sides_returns_none(self):
        # 2x = x + 5 : la funció no està pensada per a aquest cas
        self.assertIsNone(
            V.next_operation_type(V.parse_equation("2x = x + 5"))
        )

    def test_none_on_none_input(self):
        self.assertIsNone(V.next_operation_type(None))


# ---------------------------------------------------------------
# is_terminal
# ---------------------------------------------------------------
class TestIsTerminal(unittest.TestCase):
    def test_x_equals_const(self):
        self.assertTrue(V.is_terminal(V.parse_equation("x = 5")))

    def test_const_equals_x(self):
        self.assertTrue(V.is_terminal(V.parse_equation("5 = x")))

    def test_x_equals_negative_const(self):
        self.assertTrue(V.is_terminal(V.parse_equation("x = -3")))

    def test_three_x_not_terminal(self):
        self.assertFalse(V.is_terminal(V.parse_equation("3x = 21")))

    def test_with_constant_not_terminal(self):
        self.assertFalse(V.is_terminal(V.parse_equation("x + 1 = 5")))

    def test_negative_x_not_terminal(self):
        # −x = 5 NO és terminal segons aquesta funció (cal aïllar +x)
        self.assertFalse(V.is_terminal(V.parse_equation("-x = 5")))

    def test_none_returns_false(self):
        self.assertFalse(V.is_terminal(None))


# ---------------------------------------------------------------
# validate_equation_form
# ---------------------------------------------------------------
class TestValidateEquationForm(unittest.TestCase):
    def test_linear_ok(self):
        res = V.validate_equation_form(V.parse_equation("3x − 12 = 9"))
        self.assertTrue(res["ok"])
        self.assertIsNone(res["reason"])

    def test_linear_with_fractions_ok(self):
        res = V.validate_equation_form(V.parse_equation("x/2 + x/3 = 5"))
        self.assertTrue(res["ok"])

    def test_quadratic_non_linear(self):
        res = V.validate_equation_form(V.parse_equation("x^2 = 4"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "non_linear")

    def test_x_times_x_non_linear(self):
        res = V.validate_equation_form(V.parse_equation("x*x = 9"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "non_linear")

    def test_foreign_variable(self):
        res = V.validate_equation_form(V.parse_equation("y + 3 = 5"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "foreign_variable")
        self.assertIn("y", res["details"])

    def test_multiple_foreign_variables(self):
        res = V.validate_equation_form(V.parse_equation("y + z = 5"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "foreign_variable")

    def test_no_variable(self):
        res = V.validate_equation_form(V.parse_equation("3 + 2 = 5"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "no_variable")

    def test_none_input(self):
        res = V.validate_equation_form(None)
        self.assertFalse(res["ok"])

    def test_x_with_foreign_var_flags_foreign_first(self):
        # Quan hi ha x I una variable aliena, el missatge ha de mencionar
        # la variable aliena (és l'error més pedagògicament rellevant).
        res = V.validate_equation_form(V.parse_equation("x + y = 5"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "foreign_variable")


# ---------------------------------------------------------------
# has_math_content
# ---------------------------------------------------------------
class TestHasMathContent(unittest.TestCase):
    def test_empty_is_false(self):
        self.assertFalse(V.has_math_content(""))
        self.assertFalse(V.has_math_content(None))

    def test_pure_text_is_false(self):
        self.assertFalse(V.has_math_content("hola que tal"))
        self.assertFalse(V.has_math_content("no ho sé"))

    def test_digit_is_true(self):
        self.assertTrue(V.has_math_content("la resposta és 5"))

    def test_x_is_true(self):
        self.assertTrue(V.has_math_content("x val cinc"))

    def test_operators_are_true(self):
        for op in ("a + b", "a - b", "a * b", "a / b", "a = b",
                   "(a)", "fa = això"):
            with self.subTest(op=op):
                self.assertTrue(V.has_math_content(op))

    def test_math_keywords_true(self):
        self.assertTrue(V.has_math_content("hauria de sumar tots dos costats"))
        self.assertTrue(V.has_math_content("la incògnita és cinc"))

    def test_unicode_minus(self):
        # _normalize tradueix − a -, que és un operador
        self.assertTrue(V.has_math_content("a − b"))


# ---------------------------------------------------------------
# is_same_text
# ---------------------------------------------------------------
class TestIsSameText(unittest.TestCase):
    def test_identical(self):
        self.assertTrue(V.is_same_text("3x = 21", "3x = 21"))

    def test_whitespace_differences(self):
        self.assertTrue(V.is_same_text("3x = 21", "3x=21"))
        self.assertTrue(V.is_same_text("3x = 21", "  3x  =  21  "))

    def test_unicode_minus_normalized(self):
        # Després de _normalize, − i - són equivalents
        self.assertTrue(V.is_same_text("3x − 5 = 10", "3x - 5 = 10"))

    def test_different_equations(self):
        self.assertFalse(V.is_same_text("3x = 21", "x = 7"))

    def test_empty_returns_false(self):
        self.assertFalse(V.is_same_text("", "3x = 21"))
        self.assertFalse(V.is_same_text("3x = 21", ""))
        self.assertFalse(V.is_same_text("", ""))


# ---------------------------------------------------------------
# Casos integrats: una mostra dels problemes reals
# ---------------------------------------------------------------
class TestRealProblems(unittest.TestCase):
    """
    Garanteix que els 4 problemes principals es comporten com s'espera,
    i que les transicions documentades a TEST_CASES funcionen amb les
    funcions deterministes (sense IA).
    """
    def test_eq1_solution(self):
        # x + 7 = 12 → x = 5
        eq = V.parse_equation("x + 7 = 12")
        self.assertEqual(V.solve_for_x(eq), 5)

    def test_eq2_solution(self):
        # 3x − 5 = 10 → x = 5
        eq = V.parse_equation("3x − 5 = 10")
        self.assertEqual(V.solve_for_x(eq), 5)

    def test_eq3_solution(self):
        # 3(x − 4) = 9 → x = 7
        eq = V.parse_equation("3(x − 4) = 9")
        self.assertEqual(V.solve_for_x(eq), 7)

    def test_eq4_solution(self):
        # x/2 + x/3 = 5 → x = 6
        eq = V.parse_equation("x/2 + x/3 = 5")
        self.assertEqual(V.solve_for_x(eq), 6)

    def test_partial_distribution_not_equivalent(self):
        # Error típic L3_distribution_partial:
        # 3(x − 4) = 9 → 3x − 4 = 9 (oblidat el 3 sobre el −4)
        original = V.parse_equation("3(x − 4) = 9")
        wrong = V.parse_equation("3x − 4 = 9")
        self.assertFalse(V.equations_equivalent(original, wrong))

    def test_transpose_sign_not_equivalent(self):
        # L2_transpose_sign:
        # 3x − 12 = 9 → 3x = -3 (mantingut −12 en lloc de +12)
        last_correct = V.parse_equation("3x − 12 = 9")
        wrong = V.parse_equation("3x = -3")
        self.assertFalse(V.equations_equivalent(last_correct, wrong))

    def test_inverse_op_confusion_not_equivalent(self):
        # L1_inverse_op: 3x = 21 → x = 18 (restat enlloc de dividir)
        original = V.parse_equation("3x = 21")
        wrong = V.parse_equation("x = 18")
        self.assertFalse(V.equations_equivalent(original, wrong))

    def test_one_side_only_not_equivalent(self):
        # L2_one_side_only: 3x = 21 → 3x = 7 (dividit només la dreta)
        original = V.parse_equation("3x = 21")
        wrong = V.parse_equation("3x = 7")
        self.assertFalse(V.equations_equivalent(original, wrong))


if __name__ == "__main__":
    unittest.main()
