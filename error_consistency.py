"""
Verificador determinista de consistència post-IA per a `classify_error`.

Per què existeix
================
Bug A3 del catàleg original: la IA, en classificar un error, optimitza
per coherència narrativa, no per veritat. Cas paradigmàtic: l'alumne
escriu `-3x+5=14 → 3x=8`. La IA va respondre "has mogut el terme -1 sense
canviar el signe" — una explicació plausible però **falsa** (el coeficient
ha canviat de -3 a 3, cosa que la IA no va detectar).

El pre-check de coeficient a `tutor.py:399` atrapa aquest cas concret,
però la classe d'errors és més àmplia: la IA pot dir "L3_distribution_partial"
quan `last_correct` ni tan sols conté un parèntesi a distribuir, o
"L4_mcm_partial" quan no hi ha cap fracció a l'equació. Cap mecanisme
detecta avui aquestes inconsistències estructurals.

Què fa aquest mòdul
===================
Per a cada etiqueta del `ERROR_CATALOG`, defineix una **condició
necessària** sobre el context (`last_correct_text` i `attempt_text`).
Si la condició no es compleix, l'etiqueta és inconsistent amb la
transformació real i s'ha de descartar.

Filosofia: **conservadora**. Millor un fals negatiu (deixar passar una
etiqueta dubtosa, l'alumne rep el missatge específic) que un fals
positiu (descartar una etiqueta correcta, l'alumne rep `GEN_arithmetic`
generic). Per això les condicions són **necessàries però no suficients**,
i les etiquetes sense regla explícita passen sempre.

Cobertura inicial (deliberadament parcial)
==========================================
Verifiquem les etiquetes amb prerequisits estructurals trivials al text:

- `L3_distribution_partial`: cal un patró `a(x±b)` al last_correct.
- `L3_minus_paren`: cal `-(...)` al last_correct.
- `L3_combine_terms`: cal x als dos costats al last_correct.
- `L4_mcm_partial`: cal almenys una fracció al last_correct.
- `L4_minus_fraction`: cal `-` davant d'una fracció al last_correct.
- `L4_illegal_cancel`: cal almenys una fracció al last_correct.
- `L2_like_terms`: cal almenys dos termes en x al mateix costat del
  last_correct.

Etiquetes amb condició True per defecte (no verificades):
  L1_inverse_op, L1_sign_error, L2_order, L2_transpose_sign,
  L2_one_side_only, GEN_arithmetic, GEN_other.

Quan vulguem ampliar la cobertura: afegir una entrada a `_CHECKS`. Cada
check té signatura `(last_correct: str, attempt: str) → bool`.

Integració
==========
`tutor.py` crida `is_label_consistent` immediatament després de
`classify_error`. Si retorna False, sobreescriu l'etiqueta a
`GEN_arithmetic`. La incidència es grava al pas (`error_label_revised=True`)
per permetre auditar el rastre posteriorment.
"""

from __future__ import annotations

import re
from typing import Callable, Optional


# ---------------------------------------------------------------
# Helpers de normalització
# ---------------------------------------------------------------
def _normalize_minus(text: str) -> str:
    """Normalitza variants Unicode del signe menys."""
    return (
        text
        .replace("−", "-")    # U+2212 MINUS SIGN
        .replace("–", "-")    # U+2013 EN DASH
        .replace("—", "-")    # U+2014 EM DASH
    )


def _strip_ws(text: str) -> str:
    return re.sub(r"\s+", "", text)


# ---------------------------------------------------------------
# Detectors estructurals primitius
# ---------------------------------------------------------------
def _has_parenthesized_factor(text: str) -> bool:
    """Detecta un patró `a(...)` o `(...)·a` amb a ≠ 1 (factor a
    distribuir). Conservador: detectem qualsevol dígit, x, o `)` just
    abans d'un `(` obert. La normalització de menys és necessària."""
    s = _normalize_minus(_strip_ws(text))
    # Cas: número o x just abans d'un parèntesi obert.
    # Atenció: el patró ha d'evitar capturar `=(...)` que no és un factor.
    return bool(re.search(r"[\dx)]\(", s))


def _has_minus_before_parenthesis(text: str) -> bool:
    """Detecta `-(...)` (parèntesi precedit per menys). Inclou casos
    com `5-(x+1)` però també `-(x+1)=...`. La presència és el que
    importa, no la posició."""
    s = _normalize_minus(_strip_ws(text))
    return "-(" in s


def _has_x_on_both_sides(text: str) -> bool:
    """Detecta x a ambdós costats del signe igual. Insensible a Unicode
    del menys i als espais."""
    s = _normalize_minus(text)
    if "=" not in s:
        return False
    lhs, _, rhs = s.partition("=")
    return ("x" in lhs.lower()) and ("x" in rhs.lower())


def _has_fraction(text: str) -> bool:
    """Detecta almenys una fracció. Usem `/` com a heurística simple,
    excloent casos manifestament no-fraccionals (poc probable en aquest
    domini, però sempre)."""
    s = _strip_ws(text)
    return "/" in s


def _has_minus_before_fraction(text: str) -> bool:
    """Detecta `-` immediatament davant d'una expressió fraccionària.
    Patró cobert: `-x/n`, `-(x+1)/n`, ` - 3/n` (espais ja eliminats).
    Aproximació: hi ha un `-` i una `/`, i el `-` apareix abans
    d'almenys un `/`."""
    s = _normalize_minus(_strip_ws(text))
    if "/" not in s or "-" not in s:
        return False
    # Volem `-` abans d'una `/`. Mínim: alguna `-` apareix abans
    # del primer `/` en posició textual.
    first_slash = s.index("/")
    return "-" in s[:first_slash]


def _has_two_x_terms_same_side(text: str) -> bool:
    """Detecta dos o més termes en x al mateix costat (LHS o RHS) del
    signe igual. Heurística textual: comptem ocurrències de 'x' a
    cada costat. Si un costat en té ≥ 2, és candidat a "termes
    semblants per recollir".

    Atenció: aquesta és la heurística més laxa del mòdul. Un terme com
    `2x + 3x` té dues `x`, però `(x+1)/x` també — en aquest cas el
    primer és el rellevant i el segon no apareixerà a equacions de
    2n d'ESO. Per al pilot acceptem la imprecisió."""
    s = _normalize_minus(text.lower())
    if "=" not in s:
        return False
    lhs, _, rhs = s.partition("=")
    return lhs.count("x") >= 2 or rhs.count("x") >= 2


# ---------------------------------------------------------------
# Regles per etiqueta
# ---------------------------------------------------------------
# Cada regla: signatura (last_correct: str, attempt: str) → bool.
# True = etiqueta plausible (no es descarta). False = inconsistent.
_CHECKS: dict[str, Callable[[str, str], bool]] = {
    "L3_distribution_partial":
        lambda lc, at: _has_parenthesized_factor(lc),
    "L3_minus_paren":
        lambda lc, at: _has_minus_before_parenthesis(lc),
    "L3_combine_terms":
        lambda lc, at: _has_x_on_both_sides(lc),
    "L4_mcm_partial":
        lambda lc, at: _has_fraction(lc),
    "L4_minus_fraction":
        lambda lc, at: _has_minus_before_fraction(lc),
    "L4_illegal_cancel":
        lambda lc, at: _has_fraction(lc),
    "L2_like_terms":
        lambda lc, at: _has_two_x_terms_same_side(lc),
}


# ---------------------------------------------------------------
# API pública
# ---------------------------------------------------------------
def is_label_consistent(
    error_label: str,
    last_correct_text: str,
    attempt_text: str,
) -> bool:
    """
    Comprova si `error_label` és estructuralment consistent amb la
    transformació de `last_correct_text` a `attempt_text`.

    Retorna:
      - True  si l'etiqueta NO es contradiu amb el context (cap regla
              específica falla; per defecte, deixem passar).
      - False si una regla específica detecta inconsistència estructural
              (ex: etiqueta L4_* sense fracció al last_correct).

    No examinem `attempt_text` per a la majoria de regles perquè la
    condició estructural està al **punt de partida** (què hi havia per
    fer malament), no al resultat. En futures versions, condicions sobre
    `attempt_text` poden afegir-se sense canviar la signatura.

    Cap excepció s'allibera: si la regla peta per qualsevol motiu, es
    considera "no decisible" i es deixa passar (True). El mòdul mai no
    ha de bloquejar `tutor.process_turn`.
    """
    check = _CHECKS.get(error_label)
    if check is None:
        return True
    try:
        return bool(check(last_correct_text, attempt_text))
    except Exception:
        return True


def explain_inconsistency(
    error_label: str,
    last_correct_text: str,
) -> Optional[str]:
    """
    Retorna una raó humana del descartament, per al rastre JSON. Útil
    per auditar a posteriori. None si no hi ha regla per a l'etiqueta.
    """
    reasons = {
        "L3_distribution_partial":
            "no hi ha parèntesi amb factor a distribuir al pas previ",
        "L3_minus_paren":
            "no hi ha cap parèntesi precedit per menys al pas previ",
        "L3_combine_terms":
            "x no apareix als dos costats del pas previ",
        "L4_mcm_partial":
            "no hi ha fraccions al pas previ",
        "L4_minus_fraction":
            "no hi ha menys davant de fracció al pas previ",
        "L4_illegal_cancel":
            "no hi ha fraccions al pas previ",
        "L2_like_terms":
            "no hi ha dos termes en x al mateix costat del pas previ",
    }
    return reasons.get(error_label)
