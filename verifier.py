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
from sympy import symbols, sympify, simplify, solve, Eq, Rational, S, Poly, total_degree
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
        "＝": "=",     # fullwidth equals (teclat asiàtic / copia-enganxa)
        "≠": "=",      # distint-de (alumne confós)
        "≠": "=", # ≠ com a codepoint
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


def next_operation_type(eq):
    """
    Inspecciona l'equació i retorna el tipus d'operació inversa que
    correspon aplicar al pròxim pas, mirant el costat on hi ha la x:
      - 'additive':       el costat amb x té un terme constant que cal
                          moure primer (ex: 3x − 12 = 9, x + 5 = 12).
      - 'multiplicative': el costat amb x és només a·x amb a ≠ ±1, i el
                          següent pas és dividir per a (ex: 3x = 21,
                          x/3 = 5).
      - 'none':           l'equació ja és terminal o quasi (x = c, −x = c).
      - None:             no es pot determinar (x als dos costats, no
                          parseja, etc.).

    S'usa per triar el prerequisit més adequat quan l'alumne confon
    l'operació inversa: si la pròxima operació hauria de ser multiplicativa,
    cal remediar amb la variant multiplicativa del prerequisit, no amb
    l'additiva.
    """
    if eq is None:
        return None
    lhs, rhs = eq
    lhs_has_x = X in lhs.free_symbols
    rhs_has_x = X in rhs.free_symbols
    if lhs_has_x and not rhs_has_x:
        x_side = lhs
    elif rhs_has_x and not lhs_has_x:
        x_side = rhs
    else:
        return None  # x als dos costats o a cap

    try:
        p = Poly(x_side, X)
    except Exception:
        return None
    coeffs = p.all_coeffs()  # ordre: grau més alt primer
    if not coeffs:
        return None

    # Per a una expressió lineal en x, coeffs té longitud 1 (a*x sense
    # constant) o 2 (a*x + b).
    if len(coeffs) == 1:
        a = coeffs[0]
        if a == 0:
            return None
        if a == 1 or a == -1:
            return "none"
        return "multiplicative"
    if len(coeffs) == 2:
        a, b = coeffs
        if a == 0:
            return None
        if b != 0:
            return "additive"
        if a == 1 or a == -1:
            return "none"
        return "multiplicative"
    # No lineal: cau fora; deixem que validate_equation_form ho atrapi.
    return None


def is_terminal(eq, raw_text: str = None) -> bool:
    """
    L'equació és de la forma 'x = c' o 'c = x' (amb c constant).
    Si es passa raw_text, s'afegeix una comprovació textual: el costat
    de la x al text cru ha de ser literalment 'x', per evitar que
    expressions com '2x/2=8/2' (que SymPy simplifica a x=4) es
    considerin terminals sense que l'alumne hagi aïllat realment la x.
    """
    if eq is None:
        return False
    lhs, rhs = eq
    # Comprovació algebraica (SymPy)
    algebraic_ok = (lhs == X and rhs.is_constant()) or                    (rhs == X and lhs.is_constant())
    if not algebraic_ok:
        return False
    # Comprovació textual: si tenim el text original, el costat de la x
    # ha de ser estrictament 'x' (sense operadors ni coeficients).
    if raw_text is not None:
        s = _normalize(raw_text)
        if "=" not in s:
            return False
        parts = s.split("=", 1)
        left_raw  = parts[0].strip()
        right_raw = parts[1].strip()
        x_side = left_raw if lhs == X else right_raw
        if x_side != "x":
            return False
    return True


def validate_equation_form(eq):
    """
    Comprova que l'equació parsejada és LINEAL en x i NO usa altres variables.
    Retorna un dict:
      {
        "ok": bool,
        "reason": "non_linear" | "foreign_variable" | "no_variable" | None,
        "details": str   # informació humana per al missatge de feedback
      }

    Política:
      - "ok": True si és lineal en x i no hi ha variables alienes.
      - "non_linear": apareix x^2, x^3, x*x, sqrt(x), etc.
      - "foreign_variable": apareix una variable diferent de x (y, z, t...).
      - "no_variable": l'equació no conté la x (ex: "5 = 5", "3 + 2 = 4").

    Aquestes comprovacions són deterministes (gratuïtes, instantànies)
    i s'han d'executar abans de tota crida a la IA.
    """
    if eq is None:
        return {"ok": False, "reason": "parse_error", "details": "no parseja"}
    lhs, rhs = eq
    expr = lhs - rhs

    # Recollim totes les variables lliures
    free_syms = expr.free_symbols
    foreign = [s for s in free_syms if s != X]
    if foreign:
        names = ", ".join(sorted(str(s) for s in foreign))
        return {
            "ok": False,
            "reason": "foreign_variable",
            "details": (
                f"Apareix la lletra «{names}». La incògnita d'aquest "
                f"problema és «x»."
            ),
        }

    # Si no hi ha cap variable, no és una equació útil per a aquest problema.
    if X not in free_syms:
        return {
            "ok": False,
            "reason": "no_variable",
            "details": "Aquesta equació no conté la incògnita x.",
        }

    # Comprovem grau lineal en x.
    try:
        poly = Poly(expr, X)
        deg = poly.degree()
    except Exception:
        # No és polinomial en x (sqrt, sin, exp, etc.)
        return {
            "ok": False,
            "reason": "non_linear",
            "details": "L'equació que tu has escrit no és lineal: revisa-ho.",
        }
    if deg > 1:
        return {
            "ok": False,
            "reason": "non_linear",
            "details": "L'equació que tu has escrit no és lineal: revisa-ho.",
        }
    # deg == 0 ja l'hem capturat com a "no_variable" abans
    return {"ok": True, "reason": None, "details": ""}


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
