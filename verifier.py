"""
Verificació simbòlica via SymPy.

Funcions principals:
- parse_equation(text): converteix una cadena en (lhs, rhs) sympificat
- equations_equivalent(eq1, eq2): comprova equivalència via solució
- is_terminal(eq, x): comprova si l'equació és de la forma 'x = c'
- solve_for_x(eq): retorna la solució numèrica

Política: tot el parsing tolera notació informal (·, ×, ÷, − unicode, etc.).
Si SymPy no parseja, retorna None i el flux passa la patata a la IA.
"""

import re
from sympy import symbols, sympify, simplify, solve, Eq, Rational, S
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)

X = symbols("x")
TRANSFORMATIONS = (
    standard_transformations
    + (implicit_multiplication_application, convert_xor)
)


def _normalize(text: str) -> str:
    """Normalitza la cadena de notació informal a sintaxi compatible amb SymPy."""
    s = text.strip()
    # Caràcters Unicode habituals
    replacements = {
        "−": "-",      # minus signe Unicode
        "–": "-",      # en-dash
        "—": "-",      # em-dash
        "·": "*",
        "×": "*",
        "÷": "/",
        ",": ".",      # decimals europeus (només si no està dins de funció)
        " ": " ",
    }
    for a, b in replacements.items():
        s = s.replace(a, b)
    # Eliminar espais redundants
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_equation(text: str):
    """
    Intenta convertir 'lhs = rhs' en una tupla (lhs_expr, rhs_expr).
    Retorna None si no parseja o no conté '='.
    """
    if text is None:
        return None
    s = _normalize(text)
    if "=" not in s:
        return None
    parts = s.split("=")
    if len(parts) != 2:
        return None
    try:
        lhs = parse_expr(parts[0], transformations=TRANSFORMATIONS, local_dict={"x": X})
        rhs = parse_expr(parts[1], transformations=TRANSFORMATIONS, local_dict={"x": X})
        return (lhs, rhs)
    except Exception:
        return None


def parse_expression(text: str):
    """Parseja una expressió (sense '='). Per als prerequisits."""
    if text is None:
        return None
    s = _normalize(text)
    try:
        return parse_expr(s, transformations=TRANSFORMATIONS, local_dict={"x": X})
    except Exception:
        return None


def solve_for_x(eq):
    """
    Resol l'equació (lhs, rhs) per a x.
    Retorna:
      - un valor (int / Rational) si solució única
      - 'identitat' si l'equació és sempre certa
      - 'sense_solucio' si no té solució
      - None en cas d'error inesperat
    """
    if eq is None:
        return None
    lhs, rhs = eq
    diff = simplify(lhs - rhs)
    # Equació trivial: 0 = 0
    if diff == 0:
        return "identitat"
    try:
        sols = solve(Eq(lhs, rhs), X)
    except Exception:
        return None
    if not sols:
        # Cap solució (ex.: 0 = 5)
        return "sense_solucio"
    if len(sols) == 1:
        return sols[0]
    return sols  # cas estrany per a equacions lineals; retornem llista


def equations_equivalent(eq1, eq2) -> bool:
    """
    Comprova si dues equacions tenen la mateixa solució.
    Per a equacions lineals, equivalència ⇔ mateixa solució per a x.
    """
    if eq1 is None or eq2 is None:
        return False
    s1 = solve_for_x(eq1)
    s2 = solve_for_x(eq2)
    if s1 is None or s2 is None:
        return False
    # Iguals si són del mateix tipus i valor
    if s1 == s2:
        return True
    # Comparació numèrica laxa (Rational vs Integer)
    try:
        if hasattr(s1, "evalf") and hasattr(s2, "evalf"):
            return abs(float(s1.evalf()) - float(s2.evalf())) < 1e-9
    except Exception:
        pass
    return False


def is_terminal(eq) -> bool:
    """
    L'equació és de la forma 'x = c' o 'c = x' (amb c constant).
    """
    if eq is None:
        return False
    lhs, rhs = eq
    # Cas x = c
    if lhs == X and rhs.is_constant():
        return True
    # Cas c = x
    if rhs == X and lhs.is_constant():
        return True
    return False


def has_math_content(text: str) -> bool:
    """
    Heurística determinista per detectar input matemàtic.
    Retorna True si la cadena conté algun signe inequívocament matemàtic.
    Usat per a la detecció d'ús inadequat (Fase 0, §11).
    """
    if not text:
        return False
    s = _normalize(text).lower()
    # Almenys un dígit, una x, o un operador típic
    if re.search(r"[0-9]", s):
        return True
    if re.search(r"\bx\b", s):
        return True
    if any(c in s for c in ["+", "-", "*", "/", "=", "(", ")"]):
        return True
    # Vocabulari matemàtic mínim
    keywords = ["sumar", "restar", "multiplicar", "dividir", "operació",
                "equació", "valor", "resoldre", "transposar", "simplificar",
                "mateix", "costat", "incògnita", "factor", "terme"]
    return any(kw in s for kw in keywords)


def is_same_text(text_a: str, text_b: str) -> bool:
    """Compara dos enunciats normalitzats (per detectar repeticions literals)."""
    if not text_a or not text_b:
        return False
    return _normalize(text_a).replace(" ", "") == _normalize(text_b).replace(" ", "")
