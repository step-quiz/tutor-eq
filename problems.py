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
        "question": "Si x/3 = 5/2, quina equació obtens fent el producte creuat?",
        "expected_equation": "2*x = 15",  # validació via SymPy
        "explanation": "Producte creuat: numerador × denominador de l'altre. 2·x = 3·5.",
    },
    "PRE-MCM": {
        "id": "PRE-MCM",
        "concept": "def_mcm",
        "question": "Quin és el mínim comú múltiple de 2 i 3?",
        "expected_value": 6,
        "explanation": "El mínim comú múltiple és el menor nombre divisible per tots dos.",
    },
    "PRE-DIST": {
        "id": "PRE-DIST",
        "concept": "prop_distributiva",
        "question": "Desenvolupa aplicant la propietat distributiva: 5 · (x + 2)",
        "expected_equation_or_expr": "5*x + 10",
        # Format de l'explicació: "<equació original> = <resultat>, perquè
        # <raó operativa>". L'alumne ha de veure el RESULTAT complet i el
        # PERQUÈ, no només la regla abstracta.
        "explanation": "5·(x + 2) = 5x + 10, perquè el factor 5 multiplica la x i també el 2.",
    },
    "PRE-SIGNES": {
        "id": "PRE-SIGNES",
        "concept": "regla_signes_parens",
        "question": "Desenvolupa i escriu sense haver de fer servir el parèntesi: −(x − 3)",
        "expected_equation_or_expr": "-x + 3",
        "explanation": "−(x − 3) = −x + 3, perquè el menys de davant canvia el signe de cada terme de dins: la x passa a −x i el −3 passa a +3.",
    },
    "PRE-INV": {
        "id": "PRE-INV",
        "concept": "operacions_inverses",
        "question": "Si tens 3 + x = 10, quina operació fas als dos membres de l'equació, per poder aïllar la x? Explica-ho en català.",
        "keywords_required": ["restar", "resta", "−3", "-3", "menys 3", "treure"],
        # Operacions equivocades per a aquest cas (additiu): rebutgem
        # respostes que parlin de multiplicar o dividir aquí.
        "forbidden_keywords": ["multiplic", "divid"],
        "explanation": "3 + x = 10 → x = 10 − 3 = 7. Per desfer el +3 restem 3 als dos costats.",
    },
    "PRE-INV-MULT": {
        "id": "PRE-INV-MULT",
        "concept": "operacions_inverses",
        "question": "Si tens 3·x = 12, quina operació fas als dos membres de l'equació, per poder aïllar la x? Explica-ho en català.",
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
        "tema": "Equació que es resol amb un pas",
        "equacio_text": "x + 7 = 12",
        "equacio_simetria": "12 = x + 7",   # forma invertida (20% prob)
        "solucio": 5,
        "dependencies": ["operacions_inverses", "principi_equiv"],
        "errors_freqüents": ["L1_inverse_op", "L1_sign_error"],
    },
    "EQ1-B-001": {
        "id": "EQ1-B-001",
        "familia": "EQ1-B",
        "nivell": 1,
        # Variant del nivell 1 amb operació MULTIPLICATIVA (no additiva).
        # Reforça L1_inverse_op en el cas dual a EQ1-A-001: l'única
        # operació inversa correcta és la divisió, i l'alumne pot
        # confondre-la per multiplicació, suma o resta.
        "tema": "Equació que es resol amb un pas (multiplicació)",
        "equacio_text": "5x = 20",
        "equacio_simetria": "20 = 5x",
        "solucio": 4,
        "dependencies": ["operacions_inverses", "principi_equiv"],
        "errors_freqüents": ["L1_inverse_op", "L2_one_side_only", "GEN_arithmetic"],
    },
    "EQ1-C-001": {
        "id": "EQ1-C-001",
        "familia": "EQ1-C",
        "nivell": 1,
        # Variant del nivell 1 amb resta. Estructuralment idèntic a
        # EQ1-A però amb signe contrari, útil per a varietat al pilot
        # i com a primer contacte amb números més grans (resultat 13).
        "tema": "Equació que es resol amb un pas (resta)",
        "equacio_text": "x − 4 = 9",
        "equacio_simetria": "9 = x − 4",
        "solucio": 13,
        "dependencies": ["operacions_inverses", "principi_equiv"],
        "errors_freqüents": ["L1_inverse_op", "L1_sign_error", "L2_one_side_only"],
    },
    "EQ2-A-001": {
        "id": "EQ2-A-001",
        "familia": "EQ2-A",
        "nivell": 2,
        "tema": "Equació que es resol amb dos passos",
        "equacio_text": "3x − 5 = 10",
        "equacio_simetria": "10 = 3x − 5",
        "solucio": 5,
        "dependencies": ["operacions_inverses", "principi_equiv", "def_aritm_negatius"],
        "errors_freqüents": ["L2_order", "L2_transpose_sign", "L1_sign_error"],
    },
    "EQ2-B-001": {
        "id": "EQ2-B-001",
        "familia": "EQ2-B",
        "nivell": 2,
        # Variant del nivell 2 amb suma (no resta) i solució negativa.
        # Posa més pes a def_aritm_negatius perquè el resultat final és < 0.
        "tema": "Equació amb dos passos i resultat negatiu",
        "equacio_text": "2x + 8 = 4",
        "equacio_simetria": "4 = 2x + 8",
        "solucio": -2,
        "dependencies": ["operacions_inverses", "principi_equiv", "def_aritm_negatius"],
        "errors_freqüents": ["L2_transpose_sign", "L1_sign_error", "L2_one_side_only"],
    },
    "EQ2-C-001": {
        "id": "EQ2-C-001",
        "familia": "EQ2-C",
        "nivell": 2,
        # Variant del nivell 2 amb COEFICIENT NEGATIU de la x.
        # Combinació pedagògicament difícil: signes a tots dos costats
        # de la igualtat (LHS i RHS), més una divisió per un nombre
        # negatiu al final que sovint confon l'alumne sobre el signe.
        "tema": "Equació amb dos passos i coeficient negatiu",
        "equacio_text": "−3x + 5 = 14",
        "equacio_simetria": "14 = −3x + 5",
        "solucio": -3,
        "dependencies": ["operacions_inverses", "principi_equiv", "def_aritm_negatius"],
        "errors_freqüents": ["L1_sign_error", "L2_transpose_sign", "L1_inverse_op"],
    },
    "EQ2-D-001": {
        "id": "EQ2-D-001",
        "familia": "EQ2-D",
        "nivell": 2,
        # Variant del nivell 2 PRESENTADA INVERTIDA: la incògnita
        # apareix a la dreta de la igualtat. Verifica que el sistema
        # i l'alumne gestionen bé la presentació no canònica. És el
        # primer problema actiu que té sentit pel camp equacio_simetria
        # (ja que la "forma normal" seria 2x + 4 = 12).
        "tema": "Equació amb dos passos amb la incògnita a la dreta",
        "equacio_text": "12 = 2x + 4",
        "equacio_simetria": "2x + 4 = 12",
        "solucio": 4,
        "dependencies": ["operacions_inverses", "principi_equiv"],
        "errors_freqüents": ["L2_transpose_sign", "L2_one_side_only", "L1_inverse_op"],
    },
    "EQ3-A-001": {
        "id": "EQ3-A-001",
        "familia": "EQ3-A",
        "nivell": 3,
        "tema": "Equació que conté parèntesis",
        "equacio_text": "3(x − 4) = 9",
        "equacio_simetria": "9 = 3(x − 4)",
        "solucio": 7,
        "dependencies": ["prop_distributiva", "regla_signes_parens", "operacions_inverses",
                         "principi_equiv"],
        "errors_freqüents": ["L3_distribution_partial", "L3_minus_paren", "L2_order"],
    },
    "EQ3-B-001": {
        "id": "EQ3-B-001",
        "familia": "EQ3-B",
        "nivell": 3,
        # Variant del nivell 3: parèntesi precedit per un terme constant.
        # Camí pedagògic preferit: aïllar el parèntesi primer (restar 5
        # als dos costats), després dividir per 2, després aïllar la x.
        # El sistema també accepta el camí alternatiu (distribuir primer)
        # perquè SymPy només comprova equivalència algebraica.
        "tema": "Equació amb parèntesis i un terme al davant",
        "equacio_text": "5 + 2(x − 3) = 7",
        "equacio_simetria": "7 = 5 + 2(x − 3)",
        "solucio": 4,
        "dependencies": ["prop_distributiva", "regla_signes_parens", "operacions_inverses",
                         "principi_equiv"],
        "errors_freqüents": ["L3_distribution_partial", "L2_transpose_sign", "L2_one_side_only"],
    },
    "EQ3-C-001": {
        "id": "EQ3-C-001",
        "familia": "EQ3-C",
        "nivell": 3,
        # Variant amb la x als DOS costats. Cobreix L3_combine_terms,
        # un error que cap altre problema actual exposa. El camí preferit
        # és restar la x petita als dos costats abans d'aïllar.
        "tema": "Equació amb la incògnita als dos costats",
        "equacio_text": "2x + 5 = x + 8",
        "equacio_simetria": "x + 8 = 2x + 5",
        "solucio": 3,
        "dependencies": ["operacions_inverses", "principi_equiv"],
        "errors_freqüents": ["L3_combine_terms", "L2_one_side_only", "L2_transpose_sign"],
    },
    "EQ3-D-001": {
        "id": "EQ3-D-001",
        "familia": "EQ3-D",
        "nivell": 3,
        # Variant amb un menys davant del parèntesi. Cobreix L3_minus_paren
        # genuïnament (l'EQ3-A-001 el declara però com que té 3(x-4) sense
        # cap menys davant del parèntesi, no es pot disparar de fet).
        "tema": "Equació amb un menys davant del parèntesi",
        "equacio_text": "7 − (x + 2) = 4",
        "equacio_simetria": "4 = 7 − (x + 2)",
        "solucio": 1,
        "dependencies": ["regla_signes_parens", "operacions_inverses", "principi_equiv",
                         "def_aritm_negatius"],
        "errors_freqüents": ["L3_minus_paren", "L2_one_side_only", "L2_transpose_sign"],
    },
    "EQ4-A-001": {
        "id": "EQ4-A-001",
        "familia": "EQ4-A",
        "nivell": 4,
        # Variant simple del nivell 4: una sola fracció amb numerador
        # entre parèntesis. Sense menys davant (això és EQ4-C-001).
        # L'error més probable és cancel·lar el denominador sense
        # multiplicar el costat dret (L4_illegal_cancel), o multiplicar
        # només una part del numerador (L4_mcm_partial).
        "tema": "Equació amb una fracció",
        "equacio_text": "(x + 1)/3 = 4",
        "equacio_simetria": "4 = (x + 1)/3",
        "solucio": 11,
        "dependencies": ["def_fraccions_equiv", "operacions_inverses", "principi_equiv"],
        "errors_freqüents": ["L4_illegal_cancel", "L4_mcm_partial", "L2_one_side_only"],
    },
    "EQ4-B-001": {
        "id": "EQ4-B-001",
        "familia": "EQ4-B",
        "nivell": 4,
        "tema": "Equació on hi ha fraccions",
        "equacio_text": "x/2 + x/3 = 5",
        "equacio_simetria": "5 = x/2 + x/3",
        "solucio": 6,
        "dependencies": ["def_mcm", "def_fraccions_equiv", "operacions_inverses",
                         "principi_equiv"],
        "errors_freqüents": ["L4_mcm_partial", "L4_illegal_cancel", "GEN_arithmetic"],
    },
    "EQ4-C-001": {
        "id": "EQ4-C-001",
        "familia": "EQ4-C",
        "nivell": 4,
        # Fracció amb un menys davant i numerador entre parèntesis.
        # Cobreix L4_minus_fraction (sign error en distribuir el menys
        # sobre el numerador), error del catàleg que no està exercitat
        # enlloc més. Camí preferit: multiplicar per 2, després
        # distribuir el menys, després combinar i aïllar.
        "tema": "Equació amb un menys davant d'una fracció",
        "equacio_text": "5 − (x − 1)/2 = 3",
        "equacio_simetria": "3 = 5 − (x − 1)/2",
        "solucio": 5,
        "dependencies": ["def_fraccions_equiv", "regla_signes_parens",
                         "operacions_inverses", "principi_equiv"],
        "errors_freqüents": ["L4_minus_fraction", "L3_minus_paren", "L4_mcm_partial",
                             "L2_one_side_only"],
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
    "EQ1-B-001": [
        # Des de 5x = 20. Camí preferit: dividir per 5 als dos costats → x = 4.
        # És l'únic problema actual on l'operació inversa és multiplicativa
        # (no additiva), per això reforça la cobertura de L1_inverse_op.
        # Errors:
        #   - "x = 100": va multiplicar per 5 enlloc de dividir (L1_inverse_op)
        #   - "x = 25": va sumar 5 + 20 (L1_inverse_op variant additiva)
        #   - "x = 15": va restar 20 - 5 (L1_inverse_op variant)
        #   - "x = -4": error de signe (GEN_arithmetic)
        #   - "5x = 4": va dividir només la dreta (L2_one_side_only)
        ["x = 4", "x = 100", "x = 25", "x = 15", "x = -4", "5x = 4"],
    ],
    "EQ1-C-001": [
        # Des de x − 4 = 9. Camí preferit: sumar 4 als dos costats → x = 13.
        # Errors:
        #   - "x = 5": va restar 4 enlloc de sumar (L1_inverse_op)
        #   - "x = -5": error de signe (va calcular 4 - 9)
        #   - "x = 36": va multiplicar 4 · 9 (L1_inverse_op extrem)
        #   - "x − 4 = 13": va sumar 4 només a la dreta (L2_one_side_only)
        #   - "x = 9": va ignorar el −4 i va copiar la dreta
        ["x = 13", "x = 5", "x = -5", "x = 36", "x − 4 = 13", "x = 9"],
    ],
    "EQ2-A-001": [
        # Des de 3x − 5 = 10
        ["3x = 15", "3x = 5", "3x = -15", "3x - 5 = 15"],
        # Des de 3x = 15
        ["x = 5", "x = -5", "x = 12", "x = 45", "3x = 5"],
    ],
    "EQ2-B-001": [
        # Des de 2x + 8 = 4. Camí preferit: restar 8 als dos costats → 2x = -4.
        # Errors:
        #   - "2x = 12": va passar el +8 a la dreta sense canviar-li el signe (L2_transpose_sign)
        #   - "2x = 4": va restar 8 només a l'esquerra (L2_one_side_only)
        #   - "2x + 8 = 12": va sumar 8 a la dreta i va deixar-lo també a l'esquerra
        #   - "2x + 8 = -4": només va canviar el signe de la dreta (no és cap operació vàlida)
        ["2x = -4", "2x = 12", "2x = 4", "2x + 8 = 12", "2x + 8 = -4"],
        # Des de 2x = -4. Camí preferit: dividir per 2 als dos costats → x = -2.
        # Errors:
        #   - "x = 2": va dividir bé però va perdre el signe negatiu (L1_sign_error)
        #   - "x = -6": va restar 2 enlloc de dividir (L1_inverse_op)
        #   - "x = -8": va multiplicar per 2 enlloc de dividir (L1_inverse_op)
        #   - "2x = -2": va dividir només la dreta (L2_one_side_only)
        ["x = -2", "x = 2", "x = -6", "x = -8", "2x = -2"],
    ],
    "EQ2-C-001": [
        # Des de −3x + 5 = 14. Camí preferit: restar 5 als dos costats → −3x = 9.
        # Errors:
        #   - "−3x = 19": va passar el +5 a la dreta sense canviar-li el signe (L2_transpose_sign)
        #   - "−3x + 5 = 9": va restar 5 només a la dreta (L2_one_side_only)
        #   - "3x + 5 = 14": va canviar el signe del coeficient sense raó (L1_sign_error)
        #   - "−3x = -9": va calcular bé l'esquerra però va canviar el signe a la dreta
        ["−3x = 9", "−3x = 19", "−3x + 5 = 9", "3x + 5 = 14", "−3x = -9"],
        # Des de −3x = 9. Camí preferit: dividir per −3 als dos costats → x = -3.
        # Atenció: dividir per un número negatiu canvia el signe del resultat.
        # Errors:
        #   - "x = 3": va dividir però va oblidar el signe (L1_sign_error)
        #   - "x = -27": va multiplicar per -3 enlloc de dividir (L1_inverse_op)
        #   - "x = 9": va dividir per 1 enlloc de -3 (va perdre la divisió completament)
        #   - "−3x = -3": va dividir només la dreta per 3 (L2_one_side_only)
        ["x = -3", "x = 3", "x = -27", "x = 9", "−3x = -3"],
    ],
    "EQ2-D-001": [
        # Des de 12 = 2x + 4 (presentació invertida). Camí preferit: restar 4
        # als dos costats → 8 = 2x. La incògnita roman a la dreta; això pot
        # confondre l'alumne acostumat a tenir-la a l'esquerra, però SymPy
        # accepta totes les formes equivalents.
        # Errors:
        #   - "16 = 2x": va passar el +4 a l'esquerra sense canviar-li el signe (L2_transpose_sign)
        #   - "12 = 2x": va restar 4 només de la dreta (L2_one_side_only)
        #   - "8 = 2x + 4": va restar 4 només de l'esquerra (L2_one_side_only)
        #   - "12 = 2x + 8": va sumar 4 a la dreta enlloc de restar
        ["8 = 2x", "16 = 2x", "12 = 2x", "8 = 2x + 4", "12 = 2x + 8"],
        # Des de 8 = 2x. Camí preferit: dividir per 2 → x = 4 (o 4 = x).
        # Errors:
        #   - "x = 16": va multiplicar per 2 enlloc de dividir (L1_inverse_op)
        #   - "x = 6": va restar 2
        #   - "x = 10": va sumar 2
        #   - "4 = 2x": va dividir només l'esquerra (L2_one_side_only)
        ["x = 4", "x = 16", "x = 6", "x = 10", "4 = 2x"],
    ],
    "EQ3-A-001": [
        # Des de 3(x − 4) = 9
        ["3x - 12 = 9", "3x - 7 = 9", "3x + 12 = 9", "3z - 12 = 9", "3x - 12 = 8"],
        # Des de 3x − 12 = 9
        ["3x = 21", "3x = -21", "-9x = 9", "3x = 108"],
        # Des de 3x = 21
        ["x = 7", "3x = -7", "x = 18", "3x = -18", "x = 21"],
    ],
    "EQ3-B-001": [
        # Des de 5 + 2(x − 3) = 7. Camí preferit: restar 5 als dos costats
        # → 2(x − 3) = 2 (mantenint el parèntesi sense distribuir).
        # Errors:
        #   - "2(x - 3) = 12": va passar el +5 a la dreta sumant-lo enlloc de restant-lo (L2_transpose_sign)
        #   - "5 + 2x - 3 = 7": distribució parcial (no va multiplicar 2·(-3)) (L3_distribution_partial)
        #   - "2(x - 3) = 7": va restar 5 només a l'esquerra (L2_one_side_only)
        #   - "5 + 2x + 6 = 7": distribució amb error de signe (2·(-3) = +6 en lloc de -6)
        ["2(x - 3) = 2", "2(x - 3) = 12", "5 + 2x - 3 = 7", "2(x - 3) = 7",
         "5 + 2x + 6 = 7"],
        # Des de 2(x − 3) = 2. Camí preferit: dividir per 2 → x − 3 = 1.
        # Errors:
        #   - "2x - 3 = 2": distribució parcial (L3_distribution_partial)
        #   - "2(x - 3) = 1": va dividir només la dreta (L2_one_side_only)
        #   - "2x + 6 = 2": error de signe en distribuir
        #   - "x - 3 = 4": va multiplicar per 2 enlloc de dividir (L1_inverse_op)
        ["x - 3 = 1", "2x - 3 = 2", "2(x - 3) = 1", "2x + 6 = 2", "x - 3 = 4"],
        # Des de x − 3 = 1. Camí preferit: sumar 3 als dos costats → x = 4.
        # Errors:
        #   - "x = -2": va passar el -3 sense canviar-li el signe (L2_transpose_sign)
        #   - "x = -4": error de signe sumant
        #   - "x = 1/3": va dividir per 3 enlloc de sumar (L1_inverse_op)
        ["x = 4", "x = -2", "x = -4", "x = 1/3", "x = 3"],
    ],
    "EQ3-C-001": [
        # Des de 2x + 5 = x + 8. Camí preferit: restar x als dos costats
        # → x + 5 = 8.
        # Errors:
        #   - "3x + 5 = 8": va sumar les x enlloc de restar-les (L3_combine_terms)
        #   - "3x = 13": va combinar errors (sumar x i sumar constants tot a un costat)
        #   - "x + 5 = 8 + x": va restar la x només d'un costat (L2_one_side_only)
        #   - "x = 13": camí abreujat amb errors compostos
        ["x + 5 = 8", "3x + 5 = 8", "3x = 13", "x + 5 = 8 + x", "x = 13"],
        # Des de x + 5 = 8. Camí preferit: restar 5 → x = 3.
        # Errors:
        #   - "x = 13": va sumar 5 enlloc de restar (L1_inverse_op)
        #   - "x = -3": va calcular 5 - 8 enlloc de 8 - 5 (error aritmètic)
        #   - "x + 5 = 3": va restar 5 només de la dreta (L2_one_side_only)
        ["x = 3", "x = 13", "x = -3", "x + 5 = 3"],
    ],
    "EQ3-D-001": [
        # Des de 7 − (x + 2) = 4. Camí preferit: distribuir el menys
        # → 7 − x − 2 = 4. Atenció: el menys ha de canviar el signe de
        # CADA terme dins del parèntesi (la x i el +2).
        # Errors:
        #   - "7 − x + 2 = 4": no va canviar el signe del +2 (L3_minus_paren, variant 1)
        #   - "7 + x − 2 = 4": no va canviar el signe de la x (L3_minus_paren, variant 2)
        #   - "−(x + 2) = 4": va restar 7 només de l'esquerra (L2_one_side_only)
        #   - "7 − x − 2 = -3": va restar 7 només de la dreta
        ["7 − x − 2 = 4", "7 − x + 2 = 4", "7 + x − 2 = 4", "−(x + 2) = 4",
         "7 − x − 2 = -3"],
        # Des de 7 − x − 2 = 4. Camí preferit: combinar 7 - 2 = 5
        # → 5 − x = 4.
        # Errors:
        #   - "9 − x = 4": va combinar 7 + 2 enlloc de 7 - 2 (error aritmètic)
        #   - "5 + x = 4": va perdre el signe negatiu de la x
        #   - "7 − x = 2": va passar el -2 a la dreta sense canviar-li el signe (L2_transpose_sign)
        ["5 − x = 4", "9 − x = 4", "5 + x = 4", "7 − x = 2"],
        # Des de 5 − x = 4. Camí preferit: aïllar la x (un sol pas mental:
        # x = 5 - 4 = 1; o bé en dos passos: −x = −1 → x = 1).
        # Errors:
        #   - "x = 9": va sumar 5 + 4 enlloc de restar (L1_inverse_op)
        #   - "x = -1": error de signe
        #   - "−x = 1": va restar 5 només de l'esquerra (o va perdre el signe de la dreta)
        ["x = 1", "x = 9", "x = -1", "−x = 1"],
    ],
    "EQ4-A-001": [
        # Des de (x + 1)/3 = 4. Camí preferit: multiplicar els dos costats
        # per 3 → x + 1 = 12.
        # Errors:
        #   - "x + 1 = 4": va cancel·lar el 3 sense multiplicar la dreta (L4_illegal_cancel)
        #   - "(x + 1)/3 = 12": va multiplicar només la dreta (L2_one_side_only)
        #   - "x + 3 = 12": va multiplicar 3 només per la x del numerador (L4_mcm_partial)
        #   - "x + 1 = 7": va tractar el /3 com si es transposés sumant 3 a la dreta
        ["x + 1 = 12", "x + 1 = 4", "(x + 1)/3 = 12", "x + 3 = 12", "x + 1 = 7"],
        # Des de x + 1 = 12. Camí preferit: restar 1 → x = 11.
        # Errors:
        #   - "x = 13": va sumar 1 enlloc de restar (L1_inverse_op)
        #   - "x = 12": no va fer res (va deixar el 12)
        #   - "x = -11": error de signe
        #   - "x + 1 = 11": va restar 1 només de la dreta (L2_one_side_only)
        ["x = 11", "x = 13", "x = 12", "x = -11", "x + 1 = 11"],
    ],
    "EQ4-B-001": [
        # Des de x/2 + x/3 = 5  (mcm = 6)
        ["3x + 2x = 30", "3x + 2x = 5", "x + x = 30", "5x = 5"],
        # Des de 3x + 2x = 30
        ["5x = 30", "5x = 5", "6x = 30", "x^2 = 30"],
        # Des de 5x = 30
        ["x = 6", "x = 25", "x = -6", "x = 35", "5x = 6"],
    ],
    "EQ4-C-001": [
        # Des de 5 − (x − 1)/2 = 3. Camí preferit: multiplicar tots els
        # termes per 2 → 10 − (x − 1) = 6 (manté el parèntesi).
        # Errors:
        #   - "10 − x − 1 = 6": va multiplicar I distribuir el menys, però
        #      sense canviar el signe del -1 (L4_minus_fraction)
        #   - "5 − (x − 1) = 3": va multiplicar només la fracció a l'esquerra,
        #      sense tocar el 5 ni el 3 (L2_one_side_only)
        #   - "10 − (x − 1)/2 = 6": va multiplicar el 5 i el 3 per 2 però
        #      no la fracció (L4_mcm_partial)
        ["10 − (x − 1) = 6", "10 − x − 1 = 6", "5 − (x − 1) = 3",
         "10 − (x − 1)/2 = 6"],
        # Des de 10 − (x − 1) = 6. Camí preferit: distribuir el menys
        # i combinar → 11 − x = 6.
        # Errors:
        #   - "9 − x = 6": va distribuir el menys malament (-1 → -1 enlloc de +1) i combinar (L3_minus_paren combinat)
        #   - "10 − x − 1 = 6": va distribuir el menys malament sense combinar
        #   - "11 + x = 6": va perdre el signe negatiu de la x
        ["11 − x = 6", "9 − x = 6", "10 − x − 1 = 6", "11 + x = 6"],
        # Des de 11 − x = 6. Camí preferit: aïllar la x → x = 5.
        # Errors:
        #   - "x = 17": va sumar 11 + 6 enlloc de restar (L1_inverse_op)
        #   - "x = -5": error de signe
        #   - "−x = 5": va restar 11 només de l'esquerra (o va perdre el signe de la dreta)
        ["x = 5", "x = 17", "x = -5", "−x = 5"],
    ],
}


def get_test_cases(problem_id):
    """Retorna la llista de rondes de test per a un problema, o None."""
    return TEST_CASES.get(problem_id)
