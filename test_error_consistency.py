"""
Tests del verificador post-IA de consistència d'etiquetes
(`error_consistency.py`).

Per a cada etiqueta verificada, dos blocs:
  - "Plausible" — l'etiqueta passa quan el context la suporta.
  - "Inconsistent" — l'etiqueta es descarta quan el context la
    contradiu (és el comportament que defensa contra el bug A3).

També incloem una bateria de robustesa Unicode i casos límit.
"""

import unittest

import error_consistency as EC


# =============================================================
# L3_distribution_partial — cal parèntesi amb factor
# =============================================================
class TestL3DistributionPartial(unittest.TestCase):

    LABEL = "L3_distribution_partial"

    def test_plausible_when_parenthesis_with_factor(self):
        self.assertTrue(EC.is_label_consistent(self.LABEL, "3(x − 4) = 9", "3x − 4 = 9"))
        self.assertTrue(EC.is_label_consistent(self.LABEL, "2(x + 1) = 8", "2x + 1 = 8"))

    def test_plausible_with_minus_factor(self):
        # `-2(x+1)` també és un factor a distribuir
        self.assertTrue(EC.is_label_consistent(self.LABEL, "−2(x + 1) = 4", "−2x + 1 = 4"))

    def test_inconsistent_no_parenthesis(self):
        # 3x − 12 = 9 → 3x = 8 (l'alumne ha fet GEN_arithmetic en realitat)
        self.assertFalse(EC.is_label_consistent(self.LABEL, "3x − 12 = 9", "3x = 8"))

    def test_inconsistent_empty_last_correct(self):
        self.assertFalse(EC.is_label_consistent(self.LABEL, "", "x = 5"))


# =============================================================
# L3_minus_paren — cal `-(...)` al last_correct
# =============================================================
class TestL3MinusParen(unittest.TestCase):

    LABEL = "L3_minus_paren"

    def test_plausible_when_minus_before_parenthesis(self):
        self.assertTrue(EC.is_label_consistent(self.LABEL, "7 − (x + 2) = 4", "7 − x + 2 = 4"))

    def test_plausible_with_unicode_minus(self):
        # `−` (U+2212) ha de comptar igual que `-`
        self.assertTrue(EC.is_label_consistent(self.LABEL, "5 − (x − 1) = 3", "5 − x − 1 = 3"))

    def test_inconsistent_parenthesis_with_plus(self):
        # `5 + (x + 2)` no és menys davant parèntesi
        self.assertFalse(EC.is_label_consistent(self.LABEL, "5 + (x + 2) = 9", "5 + x + 2 = 9"))

    def test_inconsistent_no_parenthesis(self):
        self.assertFalse(EC.is_label_consistent(self.LABEL, "3x + 5 = 14", "3x = 9"))


# =============================================================
# L3_combine_terms — cal x als dos costats
# =============================================================
class TestL3CombineTerms(unittest.TestCase):

    LABEL = "L3_combine_terms"

    def test_plausible_when_x_both_sides(self):
        self.assertTrue(EC.is_label_consistent(self.LABEL, "2x + 5 = x + 8", "x + 5 = 8"))
        self.assertTrue(EC.is_label_consistent(self.LABEL, "4x + 1 = 2x + 7", "4x = 2x + 6"))

    def test_inconsistent_x_only_on_one_side(self):
        self.assertFalse(EC.is_label_consistent(self.LABEL, "3x − 5 = 10", "3x = 15"))

    def test_inconsistent_no_equals_sign(self):
        self.assertFalse(EC.is_label_consistent(self.LABEL, "2x + 3", "x"))


# =============================================================
# L4_mcm_partial i L4_illegal_cancel — cal fracció
# =============================================================
class TestL4FractionRequired(unittest.TestCase):

    def test_plausible_with_fraction(self):
        self.assertTrue(EC.is_label_consistent("L4_mcm_partial",
                                                "(x+1)/3 = 4", "x+1 = 4"))
        self.assertTrue(EC.is_label_consistent("L4_illegal_cancel",
                                                "x/2 + 1 = 3/2", "x + 1 = 3"))

    def test_inconsistent_no_fraction_for_mcm(self):
        self.assertFalse(EC.is_label_consistent("L4_mcm_partial",
                                                 "3x − 5 = 10", "3x = 15"))

    def test_inconsistent_no_fraction_for_cancel(self):
        self.assertFalse(EC.is_label_consistent("L4_illegal_cancel",
                                                 "2x + 5 = 11", "2x = 6"))


# =============================================================
# L4_minus_fraction — menys davant fracció
# =============================================================
class TestL4MinusFraction(unittest.TestCase):

    LABEL = "L4_minus_fraction"

    def test_plausible_with_minus_before_fraction(self):
        self.assertTrue(EC.is_label_consistent(self.LABEL,
                                                "5 − (x + 1)/2 = 3",
                                                "5 − x + 1/2 = 3"))

    def test_plausible_with_unicode_minus(self):
        self.assertTrue(EC.is_label_consistent(self.LABEL,
                                                "−x/2 + 1 = 0",
                                                "−x + 1/2 = 0"))

    def test_inconsistent_no_fraction(self):
        self.assertFalse(EC.is_label_consistent(self.LABEL,
                                                 "3x − 5 = 10",
                                                 "3x = 15"))

    def test_inconsistent_fraction_without_minus(self):
        # `(x+1)/3 = 4` no té cap menys davant la fracció
        self.assertFalse(EC.is_label_consistent(self.LABEL,
                                                 "(x + 1)/3 = 4",
                                                 "x + 1 = 12"))


# =============================================================
# L2_like_terms — dos termes en x al mateix costat
# =============================================================
class TestL2LikeTerms(unittest.TestCase):

    LABEL = "L2_like_terms"

    def test_plausible_with_two_x_terms_lhs(self):
        self.assertTrue(EC.is_label_consistent(self.LABEL,
                                                "2x + 5x = 21",
                                                "7x = 21"))

    def test_plausible_with_two_x_terms_rhs(self):
        self.assertTrue(EC.is_label_consistent(self.LABEL,
                                                "10 = 2x + 3x",
                                                "10 = 5x"))

    def test_inconsistent_only_one_x_per_side(self):
        self.assertFalse(EC.is_label_consistent(self.LABEL,
                                                 "3x + 5 = 14",
                                                 "3x = 9"))


# =============================================================
# Etiquetes sense regla — passen sempre
# =============================================================
class TestUnverifiedLabelsAlwaysPass(unittest.TestCase):

    def test_l1_inverse_op_passes_anywhere(self):
        self.assertTrue(EC.is_label_consistent("L1_inverse_op", "3x = 9", "x = 6"))
        self.assertTrue(EC.is_label_consistent("L1_inverse_op", "", ""))

    def test_l1_sign_error_passes(self):
        self.assertTrue(EC.is_label_consistent("L1_sign_error", "3x = -9", "x = 3"))

    def test_l2_transpose_sign_passes(self):
        self.assertTrue(EC.is_label_consistent("L2_transpose_sign", "x + 5 = 10", "x = 15"))

    def test_l2_one_side_only_passes(self):
        # Aquesta podria ser una de les pròximes a afegir; per ara passa.
        self.assertTrue(EC.is_label_consistent("L2_one_side_only", "3x = 21", "3x = 7"))

    def test_l2_order_passes(self):
        self.assertTrue(EC.is_label_consistent("L2_order", "3x − 5 = 10", "x − 5/3 = 10/3"))

    def test_gen_arithmetic_always_passes(self):
        self.assertTrue(EC.is_label_consistent("GEN_arithmetic", "anything", "anything"))

    def test_gen_other_always_passes(self):
        self.assertTrue(EC.is_label_consistent("GEN_other", "anything", "anything"))

    def test_unknown_label_passes(self):
        # Etiqueta no al diccionari: per defecte True (conservador)
        self.assertTrue(EC.is_label_consistent("L99_made_up", "x = 5", "x = 6"))


# =============================================================
# Robustesa
# =============================================================
class TestRobustness(unittest.TestCase):

    def test_check_does_not_raise_on_empty_strings(self):
        for label in ["L3_distribution_partial", "L3_minus_paren",
                      "L3_combine_terms", "L4_mcm_partial",
                      "L4_minus_fraction", "L4_illegal_cancel",
                      "L2_like_terms"]:
            with self.subTest(label=label):
                # No s'ha d'alliberar cap excepció
                result = EC.is_label_consistent(label, "", "")
                self.assertIsInstance(result, bool)

    def test_check_does_not_raise_on_garbage(self):
        for label in ["L3_distribution_partial", "L3_minus_paren"]:
            with self.subTest(label=label):
                result = EC.is_label_consistent(label, "$%^&*()", "qqqqqqq")
                self.assertIsInstance(result, bool)

    def test_explain_returns_none_for_unverified_label(self):
        self.assertIsNone(EC.explain_inconsistency("L1_inverse_op", "x = 5"))
        self.assertIsNone(EC.explain_inconsistency("GEN_arithmetic", "x = 5"))

    def test_explain_returns_string_for_verified_label(self):
        reason = EC.explain_inconsistency("L4_mcm_partial", "3x = 5")
        self.assertIsInstance(reason, str)
        self.assertGreater(len(reason), 5)


# =============================================================
# Regressions específiques dels bugs A3 i A4
# =============================================================
class TestA3RegressionScenarios(unittest.TestCase):
    """
    Casos reals del catàleg d'errors original (TODO_DEFERRED A3/A4).
    Aquests són els que la IA al·lucinava i que el verificador post-IA
    ha de descartar.
    """

    def test_a3_minus_3x_to_3x_no_paren_no_minus(self):
        # `-3x+5=14 → 3x=8`: la IA va dir "has mogut el terme -1 sense
        # canviar el signe" (L2_transpose_sign al·lucinat). Nota: aquest
        # cas concret no el descartem amb una regla d'L2 (no en tenim);
        # el pre-check de coeficient a tutor.py:399 sí el captura per
        # canvi de coef -3 → 3. Aquí només verifiquem que el verificador
        # no es CONTRADIU amb pre-checks existents — és a dir, que si
        # la IA DIU L3_distribution_partial sobre aquest mateix delta,
        # nosaltres ho descartem (no hi ha parèntesi enlloc).
        self.assertFalse(EC.is_label_consistent(
            "L3_distribution_partial", "−3x + 5 = 14", "3x = 8"))
        self.assertFalse(EC.is_label_consistent(
            "L3_minus_paren", "−3x + 5 = 14", "3x = 8"))
        self.assertFalse(EC.is_label_consistent(
            "L4_mcm_partial", "−3x + 5 = 14", "3x = 8"))

    def test_no_fraction_anywhere_kills_l4_family(self):
        # Una equació sense fraccions no pot generar errors de la
        # família L4. Si la IA en suggereix una, descartar-ho.
        for label in ("L4_mcm_partial", "L4_minus_fraction", "L4_illegal_cancel"):
            with self.subTest(label=label):
                self.assertFalse(EC.is_label_consistent(
                    label, "2x + 3 = 11", "2x = 9"))


if __name__ == "__main__":
    unittest.main()
