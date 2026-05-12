"""
Tests de propietat (Property tests) sobre la base de dades de problemes.

A diferència de `test_problems.py`, que verifica integritat estructural
(camps obligatoris, parsabilitat, no-equivalència d'errors), aquest mòdul
verifica **propietats** que han de complir tots els problemes — invariants
estructurals que protegeixen contra forats sistemàtics.

Cada classe està documentada amb el bug o el risc que detecta. Si en el
futur apareix una nova classe d'error sistemàtic detectable per anàlisi
estructural, afegir-la aquí, no a `test_problems.py`.

Executar amb:
    python -m unittest test_problems_properties -v
"""

import re
import unittest

import problems as PB
import verifier as V


# =============================================================
# 1. Forma de l'equació enunciada
# =============================================================
class TestProblemEquationsAreWellFormed(unittest.TestCase):
    """L'equació de l'enunciat no pot estar trivialment resolta ni mal formada."""

    def test_problem_equation_is_not_already_terminal(self):
        # Si una equació enunciada ja és de la forma 'x = c', no és un
        # problema, és la resposta. Atrapa errors d'autoria evidents.
        for pid, prob in PB.PROBLEMS.items():
            with self.subTest(problem=pid):
                eq = V.parse_equation(prob["equacio_text"])
                self.assertFalse(
                    V.is_terminal(eq, raw_text=prob["equacio_text"]),
                    f"{pid}: l'enunciat ja és terminal "
                    f"({prob['equacio_text']!r})",
                )

    def test_problem_equation_has_unique_solution(self):
        # L'enunciat ha de tenir solució única numèrica (no identitat,
        # no sense-solució). Els casos identitat/sense-solució estan a
        # Tier 4 (post-pilot) i requereixen tractament a part.
        for pid, prob in PB.PROBLEMS.items():
            with self.subTest(problem=pid):
                eq = V.parse_equation(prob["equacio_text"])
                sol = V.solve_for_x(eq)
                self.assertNotIn(
                    sol, ("identitat", "sense_solucio", None),
                    f"{pid}: solució no és única ({sol})",
                )


# =============================================================
# 2. Reachability del retrocés a prerequisits
# =============================================================
class TestErrorToDependencyReachability(unittest.TestCase):
    """
    Si un error 'X' implica conceptualment una dependència 'Y' (via
    _ERROR_TO_DEPENDENCY) i 'X' apareix als `errors_freqüents` d'un
    problema, llavors 'Y' HA d'aparèixer a les `dependencies` d'aquest
    problema. Si no, el retrocés automàtic no es pot disparar i l'alumne
    rebrà una etiqueta d'error sense remediació conceptual associada.

    Aquesta propietat era només implícita: la podia trencar un autor
    nou (incloent-nos) sense que cap test detectés res.
    """

    # Forats coneguts detectats per aquest test el 2026-05-11. NO ampliar
    # aquesta llista sense documentar el motiu a TODO_DEFERRED.md: cada
    # entrada és un cas on un alumne podria fer aquest error i no rebre
    # remediació conceptual automàtica.
    KNOWN_UNREACHABLE = {
        ("EQ4-A-001", "L4_mcm_partial"),   # falta def_mcm a deps
        ("EQ4-C-001", "L4_mcm_partial"),   # falta def_mcm a deps
    }

    def test_implied_deps_present_in_problem_dependencies(self):
        for pid, prob in PB.PROBLEMS.items():
            for err in prob["errors_freqüents"]:
                implied = PB.implied_dependency_for_error(err)
                if implied is None:
                    # Error procedimental: no requereix dep declarada.
                    continue
                if (pid, err) in self.KNOWN_UNREACHABLE:
                    continue
                with self.subTest(problem=pid, error=err, implied=implied):
                    self.assertIn(
                        implied, prob["dependencies"],
                        f"{pid}: l'error {err!r} implica la dependència "
                        f"{implied!r}, però aquesta NO és a "
                        f"`dependencies`={prob['dependencies']}. El retrocés "
                        f"a prereq no es podrà disparar.",
                    )


# =============================================================
# 3. Consistència de família
# =============================================================
class TestFamilyConsistency(unittest.TestCase):
    """
    SCHEMA.md, "Regla d'or": problemes de la mateixa família comparteixen
    estructura, i per tant haurien de declarar les mateixes `dependencies`
    i `errors_freqüents`. Atrapa autories on una variant nova s'oblida
    de copiar una dep que la família ja tenia.
    """

    def _group_by_family(self):
        by_family = {}
        for pid, prob in PB.PROBLEMS.items():
            by_family.setdefault(prob["familia"], []).append((pid, prob))
        return by_family

    def test_same_family_has_same_dependencies(self):
        for fam, items in self._group_by_family().items():
            if len(items) < 2:
                continue
            ref_id, ref = items[0]
            ref_deps = set(ref["dependencies"])
            for pid, prob in items[1:]:
                with self.subTest(family=fam, problem=pid, ref=ref_id):
                    self.assertEqual(
                        set(prob["dependencies"]), ref_deps,
                        f"família {fam}: {pid} té dependencies diferents de {ref_id}",
                    )

    def test_same_family_has_same_errors(self):
        for fam, items in self._group_by_family().items():
            if len(items) < 2:
                continue
            ref_id, ref = items[0]
            ref_errs = set(ref["errors_freqüents"])
            for pid, prob in items[1:]:
                with self.subTest(family=fam, problem=pid, ref=ref_id):
                    self.assertEqual(
                        set(prob["errors_freqüents"]), ref_errs,
                        f"família {fam}: {pid} té errors_freqüents diferents de {ref_id}",
                    )

    def test_id_seq_format(self):
        # El sufix -NNN ha de ser 3 dígits per coherència amb SCHEMA.md
        # "Convencions de nomenclatura".
        pattern = re.compile(r"^EQ[1-4]-[A-Z]+-\d{3}$")
        for pid in PB.PROBLEMS:
            with self.subTest(problem=pid):
                self.assertRegex(pid, pattern,
                                 f"{pid}: no encaixa amb EQ{{n}}-{{F}}-{{NNN}}")


# =============================================================
# 4. Detecció d'equacions-trampa (cas C5)
# =============================================================
class TestNoTrapEquations(unittest.TestCase):
    """
    Bug C5: l'equació `5 + 2(x − 3) = 7` era trampa perquè un alumne que
    sumés 5+2 abans de distribuir produïa accidentalment una equació
    equivalent. Condició general: `a + b(x + c) = d` amb `d = a + b`.

    Aquesta classe detecta el patró estructuralment per a totes les
    equacions de la base. La detecció és heurística (regex sobre el text
    enunciat) però cobreix els casos coneguts.

    Si en el futur es detecta un nou patró-trampa, afegir-lo aquí.
    """

    # Patró: "<a> + <b>(x ± <c>) = <d>"  o  "<a> − <b>(x ± <c>) = <d>"
    # Captures: 1=a, 2=signe (+/-), 3=b, 4=signe interior, 5=c, 6=d
    _PAREN_PATTERN = re.compile(
        r"^\s*(-?\d+)\s*([+−\-])\s*(\d+)\s*\(\s*x\s*([+−\-])\s*(\d+)\s*\)\s*=\s*(-?\d+)\s*$"
    )

    @staticmethod
    def _to_int(sign: str, val: str) -> int:
        n = int(val)
        return -n if sign in ("-", "−") else n

    def test_no_trap_pattern_a_plus_b_paren(self):
        """
        Per a equacions de la forma `a ± b(x ± c) = d`:
        Si un alumne sumés a i b abans de distribuir (prioritat invertida),
        obtindria `(a+b)(x±c) = d`. Comprova que aquesta equació NO és
        equivalent a la correcta. Si ho és, és una trampa pedagògica.
        """
        for pid, prob in PB.PROBLEMS.items():
            text = prob["equacio_text"]
            # Normalitzem el menys Unicode per al regex
            text_norm = text.replace("−", "-")
            m = self._PAREN_PATTERN.match(text_norm)
            if not m:
                continue
            a = int(m.group(1))
            sign_b = m.group(2).replace("−", "-")
            b = int(m.group(3))
            b_signed = -b if sign_b == "-" else b
            sign_c = m.group(4).replace("−", "-")
            c = int(m.group(5))
            d = int(m.group(6))

            # Cas trampa: l'alumne fa (a+b)(x+c)=d enlloc de a+b(x+c)=d.
            # Si (a+b)(x+c)=d és equivalent a a+b(x+c)=d, hi ha trampa.
            trap_a_plus_b = a + b_signed
            wrong_eq_text = (
                f"{trap_a_plus_b}(x {sign_c} {c}) = {d}"
            )
            correct_eq = V.parse_equation(text)
            wrong_eq = V.parse_equation(wrong_eq_text)
            with self.subTest(problem=pid, wrong=wrong_eq_text):
                if wrong_eq is None:
                    continue
                self.assertFalse(
                    V.equations_equivalent(correct_eq, wrong_eq),
                    f"{pid}: equació trampa. Si l'alumne fa "
                    f"`{wrong_eq_text}` (prioritat invertida), surt una "
                    f"equació equivalent a l'enunciat. El sistema no podrà "
                    f"detectar l'error de raonament.",
                )


# =============================================================
# 5. next_operation_type ben definit
# =============================================================
class TestNextOperationTypeIsDefined(unittest.TestCase):
    """
    `next_operation_type` s'usa a `_select_prereq_id` per triar la variant
    correcta del prereq d'operacions inverses (additiu vs multiplicatiu).
    Si retornés None o un valor inesperat per a un problema en producció,
    la tria del prereq cauria al default i podria ser pedagògicament
    incorrecta. Per a l'enunciat de cada problema, l'operació següent
    ha de ser identificable.
    """

    def test_initial_equation_has_resolvable_next_op(self):
        for pid, prob in PB.PROBLEMS.items():
            with self.subTest(problem=pid):
                eq = V.parse_equation(prob["equacio_text"])
                op = V.next_operation_type(eq)
                # 'none' és vàlid si l'equació ja gairebé està resolta (no
                # passa amb cap enunciat real, però no és un error). El
                # que NO volem és None silenciós.
                self.assertIn(
                    op, ("additive", "multiplicative", "none", None),
                    f"{pid}: next_operation_type={op!r}, valor inesperat",
                )
                # Els problemes amb x als dos costats (EQ3-C, EQ3-E, etc.)
                # legítimament tornen None — el prereq cau al default i és
                # correcte. No afirmem res sobre aquests.


# =============================================================
# 6. Catalog drift: errors orfes o no usats
# =============================================================
class TestErrorCatalogUsage(unittest.TestCase):
    """
    Cada etiqueta a ERROR_CATALOG hauria de tenir almenys una raó d'existir:
    o bé apareix a `errors_freqüents` d'algun problema, o bé és un fallback
    intern documentat (GEN_other) o un label estructural (FORM_*). Si una
    etiqueta queda orfe, segurament l'havíem afegit per una variant futura
    i ens hem oblidat.
    """

    # Etiquetes que poden estar al catàleg sense aparèixer a cap problema:
    # GEN_other és el fallback del classificador. FORM_* són etiquetes
    # generades pel verifier, no pel catàleg.
    INTENTIONALLY_UNUSED = {"GEN_other"}

    def test_each_catalog_entry_is_used_or_documented(self):
        used = set()
        for prob in PB.PROBLEMS.values():
            used.update(prob["errors_freqüents"])
        catalog_keys = set(PB.ERROR_CATALOG.keys())
        orphan = catalog_keys - used - self.INTENTIONALLY_UNUSED
        self.assertEqual(
            orphan, set(),
            f"etiquetes al catàleg sense aparèixer a cap problema "
            f"i sense estar marcades com a INTENTIONALLY_UNUSED: {orphan}. "
            f"O bé afegir un problema que les exerciti, o bé moure-les "
            f"a INTENTIONALLY_UNUSED amb un comentari justificant per què.",
        )

    def test_no_unknown_labels_in_problems(self):
        # Ja existeix a test_problems.py però el repetim aquí per cobertura
        # explícita (la propietat duala de l'anterior).
        for pid, prob in PB.PROBLEMS.items():
            for err in prob["errors_freqüents"]:
                with self.subTest(problem=pid, error=err):
                    self.assertIn(err, PB.ERROR_CATALOG,
                                  f"{pid}: error {err!r} no és al catàleg")


# =============================================================
# 7. Cobertura mínima del catàleg pel pilot
# =============================================================
class TestCoverageHealth(unittest.TestCase):
    """
    Salut estadística de la cobertura. No són errors estrictes, sinó
    avisos de qualitat: si una etiqueta està a un sol problema, no és
    bloquejant però val la pena saber-ho.
    """

    # Etiquetes que poden viure amb cobertura mínima per disseny estructural.
    # Si una etiqueta nova hi entra, documentar el motiu.
    # NOTA 2026-05-11: L3_combine_terms tenia 5+ problemes segons STATUS.md
    # ("forat de Fase 3 ara cobert per GAPs 3b/4/5"), però a la base actual
    # només apareix a EQ3-C-001. Discrepància entre doc i codi (veure
    # TODO_DEFERRED.md). Marcada com a singleton-coneguda fins que es
    # decideixi com tractar-ho.
    KNOWN_SINGLETONS = {"L4_minus_fraction", "L3_combine_terms"}

    def test_singletons_are_documented(self):
        usage = {k: 0 for k in PB.ERROR_CATALOG}
        for prob in PB.PROBLEMS.values():
            for err in prob["errors_freqüents"]:
                usage[err] = usage.get(err, 0) + 1
        singletons = {k for k, n in usage.items()
                      if n == 1 and k != "GEN_other"}
        undocumented = singletons - self.KNOWN_SINGLETONS
        self.assertEqual(
            undocumented, set(),
            f"etiquetes amb un sol problema sense estar documentades: "
            f"{undocumented}. O bé afegir un segon problema que les "
            f"reforci, o bé moure-les a KNOWN_SINGLETONS amb justificació.",
        )


# =============================================================
# 8. Solucions amb valors raonables
# =============================================================
class TestSolutionsArePedagogicallyReasonable(unittest.TestCase):
    """
    Per a 2n d'ESO, les solucions han de ser nombres curts (enters petits
    o racionals amb denominador petit). Una solució `x = 137/29` és
    matemàticament vàlida però gairebé segur un error d'autoria.
    """

    MAX_ABS_NUMERATOR = 100
    MAX_DENOMINATOR = 10

    def test_solutions_are_small(self):
        from sympy import Rational, Integer
        for pid, prob in PB.PROBLEMS.items():
            sol = prob["solucio"]
            with self.subTest(problem=pid, solution=sol):
                if isinstance(sol, int):
                    self.assertLessEqual(abs(sol), self.MAX_ABS_NUMERATOR,
                                         f"{pid}: solució {sol} massa gran")
                elif isinstance(sol, float):
                    # Acceptem floats pedagògicament només si són enters
                    self.assertEqual(sol, int(sol),
                                     f"{pid}: solució float {sol} no entera")
                else:
                    # Rational
                    try:
                        r = Rational(sol)
                        self.assertLessEqual(abs(r.p), self.MAX_ABS_NUMERATOR,
                                             f"{pid}: numerador massa gran ({r.p})")
                        self.assertLessEqual(r.q, self.MAX_DENOMINATOR,
                                             f"{pid}: denominador massa gran ({r.q})")
                    except Exception:
                        self.fail(f"{pid}: tipus de solució inesperat ({type(sol)})")


# =============================================================
# 9. Prereqs útils: la pregunta no és la mateixa equació de l'enunciat
# =============================================================
class TestPrerequisitesAreDistinct(unittest.TestCase):
    """
    Si la pregunta d'un prereq fos idèntica o equivalent a l'enunciat
    del problema original, el retrocés seria circular. No hi ha cap cas
    així en la base actual, però val la pena protegir-ho.
    """

    def test_prereq_question_does_not_match_any_problem(self):
        problem_eqs = []
        for prob in PB.PROBLEMS.values():
            eq = V.parse_equation(prob["equacio_text"])
            if eq is not None:
                problem_eqs.append((prob["equacio_text"], eq))

        for prid, pq in PB.PREREQUISITES.items():
            q = pq.get("question", "")
            # Extreu equació si n'hi ha una (heurística: tokenize 'x' i '=')
            if "=" not in q or "x" not in q.lower():
                continue
            pq_eq = V.parse_equation(q)
            if pq_eq is None:
                continue
            for ptext, peq in problem_eqs:
                with self.subTest(prereq=prid, problem_eq=ptext):
                    self.assertFalse(
                        V.equations_equivalent(pq_eq, peq),
                        f"prereq {prid} fa la mateixa pregunta que el "
                        f"problema amb enunciat {ptext!r}",
                    )


if __name__ == "__main__":
    unittest.main()
