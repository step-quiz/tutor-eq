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
    "L1_inverse_op": "confused inverse operation (subtracted instead of added or vice versa)",
    "L1_sign_error": "sign error in basic transposition",
    # Nivell 2
    "L2_order": "wrong order: divided/multiplied before adding/subtracting the constant term",
    "L2_transpose_sign": "transposed a term to the other side keeping the same sign instead of inverting it",
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
        "explanation": "El factor de fora multiplica cada terme de dins: 5·x + 5·2.",
    },
    "PRE-SIGNES": {
        "id": "PRE-SIGNES",
        "concept": "regla_signes_parens",
        "question": "Treu el parèntesi: −(x − 3)",
        "expected_equation_or_expr": "-x + 3",
        "explanation": "El menys davant canvia el signe de cada terme de dins: −x i +3.",
    },
    "PRE-INV": {
        "id": "PRE-INV",
        "concept": "operacions_inverses",
        "question": "Si tens 3 + x = 10, quina operació fas a tots dos costats per aïllar la x? Escriu només l'operació.",
        "keywords_required": ["restar", "resta", "−3", "-3", "menys 3", "treure"],
        "explanation": "Per desfer un +3, restem 3 als dos costats.",
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
