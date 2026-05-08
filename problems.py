"""
Base de dades de problemes per al Tutor d'equacions lineals (2n d'ESO).

Estructura:
- PROBLEMS: 4 problemes principals (un per nivell)
- DEPENDENCIES: graf de prerequisits (3 capes: aritmètica, algebraica, procedimental)
- PREREQUISITES: mini-problemes per al retrocés
- ERROR_CATALOG: errors típics per nivell

Ref: Document de disseny - Fase 0, seccions 2, 3, 4.
"""

# ---------- Catàleg d'errors típics (Fase 0, §4) ----------
# Cada entrada: id -> descripció breu (en anglès, per als prompts a la IA)
ERROR_CATALOG = {
    # Nivell 1
    "L1_inverse_op": (
        "confused inverse operation: applied an additive inverse where a "
        "multiplicative one was needed (or vice versa). E.g. from 3x = 21 "
        "writing x = 18 (subtracted 3 instead of dividing by 3), or from "
        "x + 5 = 12 writing x = 17 (added 5 instead of subtracting). The "
        "TYPE of operation chosen is wrong, not just its sign."
    ),
    "L1_sign_error": (
        "sign error in basic transposition or division: the right operation "
        "was chosen but the result has the wrong sign (e.g. 5x = 30 → x = -6)"
    ),
    # Nivell 2
    "L2_order": "wrong order: divided/multiplied before adding/subtracting the constant term",
    "L2_transpose_sign": "transposed a term to the other side keeping the same sign instead of inverting it",
    "L2_one_side_only": (
        "applied an operation to only ONE side of the equation, breaking equivalence. "
        "Example: from 3x = 21 writing 3x = 7 (divided RHS by 3 but kept LHS as 3x). "
        "The arithmetic on the modified side may be correct, but the equation is no "
        "longer equivalent because the same operation wasn't done on both sides."
    ),
    # Nivell 3
    "L3_distribution_partial": "incomplete distribution: a(x+b) = ax+b instead of ax+ab",
    "L3_minus_paren": "sign error after a minus sign in front of parenthesis: -(x-3) = -x-3 instead of -x+3",
    "L3_combine_terms": "incorrect combination of x-terms when they appear on both sides",
    # Nivell 4
    "L4_mcm_partial": "multiplied by the lcm only some terms of the equation, not all",
    "L4_minus_fraction": "sign error in front of a fraction: -(x+1)/2 treated as (-x+1)/2",
    "L4_illegal_cancel": "illegal cancellation of denominators that are not common factors",
    # Genèric
    "GEN_arithmetic": "arithmetic mistake (computation error in numbers)",
    "GEN_other": "other transformation error not listed in the catalog",
}


# Mapatge etiqueta d'error → dependència conceptual implicada.
# Algunes etiquetes són, per definició, indicatives d'un buit conceptual
# concret (no són lapsus procedimentals): si un alumne fa una distribució
# parcial, és perquè no domina la propietat distributiva — això no depèn
# del judici de la IA. Aquest mapatge s'usa com a fallback determinista a
# tutor.py per activar el retrocés a prerequisits sense dependre que el
# model marqui correctament `is_conceptual` a cada classificació.
#
# Les etiquetes que NO apareixen aquí (L1_sign_error, L2_*, L3_combine_terms,
# GEN_*) es consideren procedimentals per defecte: la IA encara pot pujar-les
# a conceptuals en casos clars, però no hi ha fallback automàtic.
_ERROR_TO_DEPENDENCY = {
    "L1_inverse_op":           "operacions_inverses",
    "L2_transpose_sign":       "principi_equiv",
    "L2_one_side_only":        "principi_equiv",
    "L3_distribution_partial": "prop_distributiva",
    "L3_minus_paren":          "regla_signes_parens",
    "L4_mcm_partial":          "def_mcm",
    "L4_minus_fraction":       "regla_signes_parens",
    "L4_illegal_cancel":       "def_fraccions_equiv",
}


def implied_dependency_for_error(error_label):
    """
    Retorna la dependència conceptual que una etiqueta d'error implica,
    o None si l'error es considera procedimental.
    """
    return _ERROR_TO_DEPENDENCY.get(error_label)


# ---------- Graf de dependències (Fase 0, §3) ----------
# Cada dependència: keywords per al test ràpid + prerequisit associat
DEPENDENCIES = {
    # Capa aritmètica
    "def_aritm_negatius": {
        "description": "operations with negative integers",
        "keywords": ["negatiu", "negatius", "menys", "signe", "oposat", "contrari"],
        "prerequisite": "PRE-NEG",
    },
    "def_fraccions_equiv": {
        "description": "fraction equivalence: a/b = c/d ⇔ ad = bc",
        "keywords": ["creuat", "creuada", "producte", "multiplicar", "creu"],
        "prerequisite": "PRE-FRAC",
    },
    "def_mcm": {
        "description": "least common multiple",
        "keywords": ["mcm", "múltiple", "multiple", "comú", "minim", "mínim"],
        "prerequisite": "PRE-MCM",
    },
    # Capa algebraica
    "principi_equiv": {
        "description": "applying the same operation to both sides preserves the solution",
        "keywords": ["dos costats", "ambdós", "ambdues", "tots dos", "mateixa", "tots", "alhora"],
        "prerequisite": "PRE-EQUIV",
    },
    "prop_distributiva": {
        "description": "distributive property: a(b+c) = ab + ac",
        "keywords": ["multiplica", "fora", "tots", "cada", "distribu", "obrir"],
        "prerequisite": "PRE-DIST",
    },
    "regla_signes_parens": {
        "description": "sign rule before a parenthesis: -(x-3) = -x+3",
        "keywords": ["canvi", "signe", "canvia", "oposat", "menys", "invers"],
        "prerequisite": "PRE-SIGNES",
    },
    # Capa procedimental
    "operacions_inverses": {
        "description": "inverse operations: + ↔ -, × ↔ ÷",
        "keywords": ["inversa", "contrari", "oposat", "restar", "sumar", "dividir", "multiplicar"],
        "prerequisite": "PRE-INV",
    },
}


# ---------- Mini-problemes prerequisit ----------
# Format simple: una sola pregunta amb resposta validada per paraules clau
# o per igualtat numèrica/simbòlica. NO tenen passos intermitjos.
PREREQUISITES = {
    "PRE-NEG": {
        "id": "PRE-NEG",
        "concept": "def_aritm_negatius",
        "question": "Calcula el resultat de: −7 + 3",
        "expected_value": -4,            # validació numèrica
        "explanation": "Quan sumem un negatiu i un positiu, restem els valors absoluts i posem el signe del més gran en valor absolut.",
    },
    "PRE-FRAC": {
        "id": "PRE-FRAC",
        "concept": "def_fraccions_equiv",
        "question": "Si x/3 = 5/2, quina equació obtens fent producte creuat?",
        "expected_equation": "2*x = 15",  # validació via SymPy
        "explanation": "Producte creuat: numerador × denominador de l'altre. 2·x = 3·5.",
    },
    "PRE-MCM": {
        "id": "PRE-MCM",
        "concept": "def_mcm",
        "question": "Quin és el m.c.m. de 2 i 3?",
        "expected_value": 6,
        "explanation": "El mínim comú múltiple és el menor nombre divisible per tots dos.",
    },
    "PRE-EQUIV": {
        "id": "PRE-EQUIV",
        "concept": "principi_equiv",
        "question": "Si tens x + 5 = 12 i restes 5 a un sol costat, l'equació segueix sent equivalent? Respon SÍ o NO i digues per què.",
        "keywords_required": ["no"],
        "explanation": "S'ha d'operar als dos costats alhora. Si només es resta a un, ja no és la mateixa equació.",
    },
    "PRE-DIST": {
        "id": "PRE-DIST",
        "concept": "prop_distributiva",
        "question": "Desenvolupa: 5(x + 2)",
        "expected_equation_or_expr": "5*x + 10",
        # Format de l'explicació: "<equació original> = <resultat>, perquè
        # <raó operativa>". L'alumne ha de veure el RESULTAT complet i el
        # PERQUÈ, no només la regla abstracta.
        "explanation": "5·(x + 2) = 5x + 10, perquè el factor 5 multiplica la x i també el 2.",
    },
    "PRE-SIGNES": {
        "id": "PRE-SIGNES",
        "concept": "regla_signes_parens",
        "question": "Treu el parèntesi: −(x − 3)",
        "expected_equation_or_expr": "-x + 3",
        "explanation": "−(x − 3) = −x + 3, perquè el menys de davant canvia el signe de cada terme de dins: la x passa a −x i el −3 passa a +3.",
    },
    "PRE-INV": {
        "id": "PRE-INV",
        "concept": "operacions_inverses",
        "question": "Si tens 3 + x = 10, quina operació fas a tots dos costats per aïllar la x? Escriu només l'operació.",
        "keywords_required": ["restar", "resta", "−3", "-3", "menys 3", "treure"],
        # Operacions equivocades per a aquest cas (additiu): rebutgem
        # respostes que parlin de multiplicar o dividir aquí.
        "forbidden_keywords": ["multiplic", "divid"],
        "explanation": "3 + x = 10 → x = 10 − 3 = 7. Per desfer el +3 restem 3 als dos costats.",
    },
    "PRE-INV-MULT": {
        "id": "PRE-INV-MULT",
        "concept": "operacions_inverses",
        "question": "Si tens 3·x = 12, quina operació fas a tots dos costats per aïllar la x? Escriu només l'operació.",
        # "entre 3" és inequívocament divisió en català; "per 3" no
        # s'inclou perquè és ambigu (es fa servir tant per a multiplicar
        # com per a dividir).
        "keywords_required": ["dividir", "divideix", "divisió", "/3", ":3", "÷3", "entre 3"],
        # Operacions equivocades per al cas multiplicatiu: si l'alumne
        # contesta "multiplico", "sumar" o "restar", la resposta és falsa
        # encara que de retruc inclogui "/3" o similar.
        "forbidden_keywords": ["multiplic", "sumar", "restar"],
        "explanation": "3·x = 12 → x = 12 : 3 = 4. Per desfer una multiplicació per 3 dividim entre 3 als dos costats.",
    },
    "PRE-EQUIV": {
        "id": "PRE-EQUIV",
        "concept": "principi_equiv",
        # Aquest prereq cobreix dos errors germans:
        #   - L2_transpose_sign: moure un terme sense canviar-ne el signe
        #     (que és el snare de "fer la mateixa cosa als dos costats").
        #   - L2_one_side_only: aplicar una operació només a un costat.
        # La pregunta força explicitar l'operació I la simetria.
        "question": "Tens 3x − 5 = 10 i vols passar el −5 a l'altre costat. Quina operació fas, i a quants costats l'apliques?",
        # Conjugacions comunes del verb "sumar" en respostes d'alumne:
        # infinitiu, 1a persona present (la més freqüent), 2a, 3a, 1a plural,
        # més sinònim "afegir" en diverses formes, més notació "+5".
        "keywords_required": [
            "sumar", "sumo", "sumes", "suma", "sumem",
            "afegir", "afegeix", "afegim", "afegeixo",
            "+5", "+ 5",
        ],
        # Operacions equivocades: cal incloure conjugacions explícites de
        # "restar" perquè els altres stems ("multiplic", "divid") ja cobreixen
        # totes les seves variants.
        "forbidden_keywords": ["restar", "resto", "resta", "restem", "multiplic", "divid"],
        "explanation": "Per moure el −5, sumem 5 als DOS costats: 3x − 5 + 5 = 10 + 5, és a dir 3x = 15. La clau és aplicar la mateixa operació als dos costats.",
    },
}


# ---------- Problemes principals (1 per nivell) ----------
PROBLEMS = {
    "EQ1-A-001": {
        "id": "EQ1-A-001",
        "familia": "EQ1-A",
        "nivell": 1,
        "tema": "Equació d'un pas, suma",
        "equacio_text": "x + 7 = 12",
        "equacio_simetria": "12 = x + 7",   # forma invertida (20% prob)
        "solucio": 5,
        "dependencies": ["operacions_inverses", "principi_equiv"],
        "errors_freqüents": ["L1_inverse_op", "L1_sign_error"],
    },
    "EQ2-A-001": {
        "id": "EQ2-A-001",
        "familia": "EQ2-A",
        "nivell": 2,
        "tema": "Equació de dos passos",
        "equacio_text": "3x − 5 = 10",
        "equacio_simetria": "10 = 3x − 5",
        "solucio": 5,
        "dependencies": ["operacions_inverses", "principi_equiv", "def_aritm_negatius"],
        "errors_freqüents": ["L2_order", "L2_transpose_sign", "L1_sign_error"],
    },
    "EQ3-A-001": {
        "id": "EQ3-A-001",
        "familia": "EQ3-A",
        "nivell": 3,
        "tema": "Equació amb parèntesi",
        "equacio_text": "3(x − 4) = 9",
        "equacio_simetria": "9 = 3(x − 4)",
        "solucio": 7,
        "dependencies": ["prop_distributiva", "regla_signes_parens", "operacions_inverses",
                         "principi_equiv"],
        "errors_freqüents": ["L3_distribution_partial", "L3_minus_paren", "L2_order"],
    },
    "EQ4-B-001": {
        "id": "EQ4-B-001",
        "familia": "EQ4-B",
        "nivell": 4,
        "tema": "Equació amb denominadors",
        "equacio_text": "x/2 + x/3 = 5",
        "equacio_simetria": "5 = x/2 + x/3",
        "solucio": 6,
        "dependencies": ["def_mcm", "def_fraccions_equiv", "operacions_inverses",
                         "principi_equiv"],
        "errors_freqüents": ["L4_mcm_partial", "L4_illegal_cancel", "GEN_arithmetic"],
    },
}


def get_problem(problem_id):
    return PROBLEMS[problem_id]


def list_problems():
    """Retorna llista ordenada per nivell."""
    return sorted(PROBLEMS.values(), key=lambda p: p["nivell"])


def get_prerequisite(prereq_id):
    return PREREQUISITES.get(prereq_id)


def get_dependency(dep_id):
    return DEPENDENCIES.get(dep_id)


# ---------- Casos de test per al mode debug ("Test exhaustiu") ----------
# Cada problema té una llista de rondes. Cada ronda és una llista d'inputs:
# el PRIMER ha de ser una resposta correcta que avança cap a la solució;
# els altres són errors versemblants. El test runner usa el primer per
# avançar el baseline d'una ronda a la següent.
#
# Aquests casos es trien per cobrir els errors típics del catàleg:
# distribució parcial, transposició sense canvi de signe, confusió
# d'operació inversa, errors aritmètics/tipogràfics, variable aliena, etc.
TEST_CASES = {
    "EQ1-A-001": [
        # Des de x + 7 = 12  (solució: x = 5)
        ["x = 5", "x = 19", "x = -5", "x + 7 = 5", "y = 5"],
    ],
    "EQ2-A-001": [
        # Des de 3x − 5 = 10
        ["3x = 15", "3x = 5", "3x = -15", "3x - 5 = 15"],
        # Des de 3x = 15
        ["x = 5", "x = -5", "x = 12", "x = 45", "3x = 5"],
    ],
    "EQ3-A-001": [
        # Des de 3(x − 4) = 9
        ["3x - 12 = 9", "3x - 7 = 9", "3x + 12 = 9", "3z - 12 = 9", "3x - 12 = 8"],
        # Des de 3x − 12 = 9
        ["3x = 21", "3x = -21", "-9x = 9", "3x = 108"],
        # Des de 3x = 21
        ["x = 7", "3x = -7", "x = 18", "3x = -18", "x = 21"],
    ],
    "EQ4-B-001": [
        # Des de x/2 + x/3 = 5  (mcm = 6)
        ["3x + 2x = 30", "3x + 2x = 5", "x + x = 30", "5x = 5"],
        # Des de 3x + 2x = 30
        ["5x = 30", "5x = 5", "6x = 30", "x^2 = 30"],
        # Des de 5x = 30
        ["x = 6", "x = 25", "x = -6", "x = 35", "5x = 6"],
    ],
}


def get_test_cases(problem_id):
    """Retorna la llista de rondes de test per a un problema, o None."""
    return TEST_CASES.get(problem_id)
