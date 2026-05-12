"""
Tests de coherència entre la documentació tècnica (README.md, SCHEMA.md,
STATUS.md) i el codi real (problems.py, ERROR_CATALOG).

Per què existeix
================
El 2026-05-11 vam descobrir (finding F0 de TODO_DEFERRED.md) que
STATUS.md descrivia 25 problemes mentre el codi en tenia 14, i README.md
afirmava 4 problemes (xifra de la Fase 0). Cap test detectava la
discrepància. Conseqüència: durant la sessió d'enduriment, l'IA va
suggerir tasques basades en problemes que no existien (`EQ2-E-001`,
etc.) i el professor va haver de detectar-ho a mà.

Aquest mòdul afegeix una capa de comprovacions mecàniques. La filosofia
és la mateixa que la dels invariants: comprovacions barates (parsing de
regex sobre fitxers .md ja existents), executades en CI, que petarien
amb un missatge clar a la primera divergència.

Què compromet i què NO compromet
================================
**Sí compromet (fa fallar el test si divergeix):**
- El nombre total de problemes esmentat a README.md i STATUS.md ha de
  coincidir amb `len(problems.PROBLEMS)`.
- La taula d'etiquetes a SCHEMA.md ha de coincidir exactament amb les
  claus de `problems.ERROR_CATALOG`.
- Les famílies marcades "Existent" a SCHEMA.md han de tenir almenys un
  problema a `problems.PROBLEMS`, i a l'inrevés.

**No compromet (fora d'abast deliberadament):**
- "Tiers" de problemes, "GAPs coberts", cobertura per etiqueta amb
  números concrets — aquesta informació canvia massa sovint i fer-la
  testable la convertiria en soroll.
- Descripcions textuals dels conceptes. El test només mira identificadors.

Format dels missatges d'error: el test indica exactament quina línia de
la doc o quina constant del codi ha quedat desincronitzada, per fer
l'arranjament trivial.

Executar amb:
    python -m unittest test_docs_match_code -v
"""

import os
import re
import unittest

import problems as PB


REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def _read(name: str) -> str:
    with open(os.path.join(REPO_ROOT, name), encoding="utf-8") as f:
        return f.read()


# =============================================================
# 1. Nombre total de problemes
# =============================================================
class TestProblemCountMatchesDocs(unittest.TestCase):
    """README.md i STATUS.md no poden afirmar un nombre de problemes
    diferent del real. Atrapa F0 i futures repeticions.

    Mecànica: en lloc de mirar qualsevol xifra prop de "problemes" (que
    inclouria coses com "11 problemes nous" o "≥2 problemes" o "una
    sessió de 4 problemes"), busquem només **marcadors explícits** que
    el redactor de la doc ha de posar quan vol afirmar el total. Avui
    són dos:

        <!-- problem-count -->14<!-- /problem-count -->
        `len(PROBLEMS)` = 14

    Si vols afegir una afirmació numèrica sobre el total a la doc, usa
    una d'aquestes formes. Qualsevol altra menció ("els 11 problemes
    nous", "4 problemes per nivell", etc.) queda fora de l'abast del
    test, que és el correcte: aquestes són afirmacions sobre subconjunts
    o sobre estats històrics, no sobre el total actual.
    """

    REAL_COUNT = len(PB.PROBLEMS)

    _MARKER_HTML = re.compile(
        r"<!--\s*problem-count\s*-->\s*(\d+)\s*<!--\s*/problem-count\s*-->"
    )
    _MARKER_BACKTICK = re.compile(
        r"`len\(PROBLEMS\)`\s*=\s*(\d+)"
    )

    def _extract_marked_counts(self, text: str):
        out = []
        for i, line in enumerate(text.splitlines(), start=1):
            for pat in (self._MARKER_HTML, self._MARKER_BACKTICK):
                for m in pat.finditer(line):
                    out.append((int(m.group(1)), i, line.strip()))
        return out

    def test_readme_problem_count(self):
        text = _read("README.md")
        counts = self._extract_marked_counts(text)
        if not counts:
            self.skipTest(
                "README.md no usa el marcador <!-- problem-count -->N<!-- /problem-count -->. "
                "Si vols que README afirmi el total de problemes, afegir-hi el marcador."
            )
        for n, lineno, line in counts:
            with self.subTest(line=lineno):
                self.assertEqual(
                    n, self.REAL_COUNT,
                    f"README.md línia {lineno}: marcador problem-count "
                    f"afirma {n}, però problems.PROBLEMS en té "
                    f"{self.REAL_COUNT}. Línia: {line!r}",
                )

    def test_status_problem_count(self):
        text = _read("STATUS.md")
        counts = self._extract_marked_counts(text)
        if not counts:
            self.skipTest(
                "STATUS.md no usa el marcador <!-- problem-count -->N<!-- /problem-count -->. "
                "Si vols que STATUS afirmi el total, afegir-hi el marcador."
            )
        for n, lineno, line in counts:
            with self.subTest(line=lineno):
                self.assertEqual(
                    n, self.REAL_COUNT,
                    f"STATUS.md línia {lineno}: marcador problem-count "
                    f"afirma {n}, però problems.PROBLEMS en té "
                    f"{self.REAL_COUNT}. Línia: {line!r}",
                )


# =============================================================
# 2. Etiquetes del catàleg
# =============================================================
class TestErrorCatalogMatchesSchema(unittest.TestCase):
    """La taula d'etiquetes de SCHEMA.md ha de reflectir exactament
    `problems.ERROR_CATALOG`. Atrapa F3 (L2_like_terms documentat però
    no al codi) i casos simètrics."""

    # Patró conservador: una fila Markdown amb una clau d'etiqueta a la
    # primera columna. Format: | `LABEL` | ... | ... |
    _ROW_PATTERN = re.compile(
        r"^\|\s*`(L\d_[a-z_]+|GEN_[a-z_]+)`\s*\|",
        re.MULTILINE,
    )

    def setUp(self):
        text = _read("SCHEMA.md")
        self.schema_labels = set(self._ROW_PATTERN.findall(text))
        self.code_labels = set(PB.ERROR_CATALOG.keys())

    def test_no_labels_in_schema_missing_from_code(self):
        missing = self.schema_labels - self.code_labels
        # F3 resolt el 2026-05-11: `L2_like_terms` es va afegir al
        # ERROR_CATALOG quan es van integrar els 11 problemes nous.
        # Si torna a haver-hi etiquetes documentades sense codi,
        # afegir-les aquí amb una nota de la motivació.
        known_pending_f3 = set()
        unexpected = missing - known_pending_f3
        self.assertEqual(
            unexpected, set(),
            f"Etiquetes documentades a SCHEMA.md però absents d'"
            f"`ERROR_CATALOG`: {sorted(unexpected)}. "
            f"Cal afegir-les al codi o eliminar-les de la doc.",
        )

    def test_no_labels_in_code_missing_from_schema(self):
        missing = self.code_labels - self.schema_labels
        self.assertEqual(
            missing, set(),
            f"Etiquetes a `ERROR_CATALOG` però no documentades a "
            f"SCHEMA.md: {sorted(missing)}. Afegir-les a la taula 'Labels "
            f"actuals del catàleg' de SCHEMA.md.",
        )


# =============================================================
# 3. Famílies de problemes
# =============================================================
class TestFamiliesMatchSchema(unittest.TestCase):
    """Les famílies marcades 'Existent' a la taula de famílies de SCHEMA.md
    han de tenir representació a problems.PROBLEMS, i a l'inrevés. Atrapa
    F0 directament: SCHEMA.md llista famílies "Existent (GAP X)" que en
    realitat no estan integrades al codi."""

    # Patró: | `EQX-Y` | <descripció> | Existent[...] |
    _FAMILY_PATTERN = re.compile(
        r"\|\s*`(EQ\d-[A-Z]+)`\s*\|[^|]+\|\s*Existent[^|]*\|",
    )

    def setUp(self):
        text = _read("SCHEMA.md")
        self.schema_families = set(self._FAMILY_PATTERN.findall(text))
        self.code_families = {prob["familia"] for prob in PB.PROBLEMS.values()}

    # Whitelist F0: buidada el 2026-05-11 quan els 11 problemes nous
    # (GAPs 1-5) es van integrar a `problems.py`. Si torna a haver-hi
    # famílies a SCHEMA però no al codi, afegir-les aquí amb una nota
    # de la motivació.
    KNOWN_PENDING_F0 = set()

    def test_no_existent_families_missing_from_code(self):
        missing = self.schema_families - self.code_families
        unexpected = missing - self.KNOWN_PENDING_F0
        self.assertEqual(
            unexpected, set(),
            f"Famílies marcades 'Existent' a SCHEMA.md sense cap problema "
            f"a problems.PROBLEMS, FORA de la whitelist F0: "
            f"{sorted(unexpected)}.\n"
            f"Possibles solucions:\n"
            f"  (a) Si els problemes existeixen en algun lloc fora del "
            f"repo (Drive, branca local), integrar-los a problems.py.\n"
            f"  (b) Si encara no existeixen, canviar l'estat a "
            f"'Reservada' o 'Disponible' a la taula de famílies de "
            f"SCHEMA.md.",
        )

    def test_no_code_families_missing_from_schema(self):
        missing = self.code_families - self.schema_families
        self.assertEqual(
            missing, set(),
            f"Famílies presents a problems.PROBLEMS però no a SCHEMA.md "
            f"(o marcades diferent d''Existent'): {sorted(missing)}. "
            f"Afegir-les a la taula 'Famílies reservades' de SCHEMA.md.",
        )


# =============================================================
# 4. Llista de prerequisits
# =============================================================
class TestPrerequisiteCount(unittest.TestCase):
    """Mateix mecanisme que TestProblemCountMatchesDocs però per a
    `PREREQUISITES`. Usa el marcador:

        <!-- prereq-count -->7<!-- /prereq-count -->
    """

    REAL_COUNT = len(PB.PREREQUISITES)
    _MARKER = re.compile(
        r"<!--\s*prereq-count\s*-->\s*(\d+)\s*<!--\s*/prereq-count\s*-->"
    )

    def _extract(self, text):
        out = []
        for i, line in enumerate(text.splitlines(), start=1):
            for m in self._MARKER.finditer(line):
                out.append((int(m.group(1)), i, line.strip()))
        return out

    def test_readme_prereq_count(self):
        text = _read("README.md")
        counts = self._extract(text)
        if not counts:
            self.skipTest("README.md no usa el marcador prereq-count.")
        for n, lineno, line in counts:
            with self.subTest(line=lineno):
                self.assertEqual(
                    n, self.REAL_COUNT,
                    f"README.md línia {lineno}: marcador afirma {n} "
                    f"prerequisits, però PREREQUISITES en té "
                    f"{self.REAL_COUNT}.",
                )


if __name__ == "__main__":
    unittest.main()
