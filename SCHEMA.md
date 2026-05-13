# Esquema de `problems.py`

Aquest document descriu l'estructura de dades de `problems.py` per a qui
hagi d'autorar problemes nous. Conté el contracte de cada camp i els
passos per afegir un problema sense trencar res.

## Visió general

`problems.py` és la base de dades del tutor. Conté **5 estructures**:

| Estructura | Què és | Cal tocar-la per afegir un problema? |
|---|---|---|
| `PROBLEMS` | Els problemes principals que l'alumne resol | **Sí** (sempre) |
| `TEST_CASES` | Casos de test associats a cada problema | **Sí** (sempre) |
| `DEPENDENCIES` | Graf de conceptes que un problema requereix | Només si introdueixes un concepte nou |
| `PREREQUISITES` | Mini-preguntes per al retrocés conceptual | Només si introdueixes una dependència nova |
| `ERROR_CATALOG` | Etiquetes d'errors típics que la IA pot assignar | Només si introdueixes un error que no encaixi en cap etiqueta existent |

Per a la majoria de problemes nous d'un tipus ja existent (un EQ2 més,
un EQ3 més, etc.), només cal tocar `PROBLEMS` i `TEST_CASES`.

---

## `PROBLEMS`

Cada entrada del dict `PROBLEMS` és un problema. Clau = `id`.

```python
"EQ2-B-001": {
    "id": "EQ2-B-001",
    "familia": "EQ2-B",
    "nivell": 2,
    "tema": "Equació amb dos passos i resultat negatiu",
    "equacio_text": "2x + 8 = 4",
    "equacio_simetria": "4 = 2x + 8",
    "solucio": -2,
    "dependencies": ["operacions_inverses", "principi_equiv", "def_aritm_negatius"],
    "errors_freqüents": ["L2_transpose_sign", "L1_sign_error", "L2_one_side_only"],
},
```

### Camps

| Camp | Tipus | Obligatori | Què és |
|---|---|---|---|
| `id` | str | Sí | Identificador únic. Format: `EQ{nivell}-{família}-{seq}`. Igual que la clau del dict. |
| `familia` | str | Sí | Prefix `EQ{nivell}-{família}`. Mateixa cosa que `id` sense el sufix `-{seq}`. |
| `nivell` | int (1-4) | Sí | Nivell de dificultat. Determina la mena d'errors típics i el to de les pistes. |
| `tema` | str | Sí | Frase curta en català que descriu el tipus d'equació. **Visible per a l'alumne** a la capçalera del problema. |
| `equacio_text` | str | Sí | L'equació tal com la veu l'alumne (i tal com el sistema la parseja). Veure §"Convencions per a l'equació" més avall. |
| `equacio_simetria` | str | Recomanat | La mateixa equació amb els dos costats invertits. **Camp reservat: actualment no s'usa al codi** (estava previst per a una variació aleatòria de presentació). Mantenir-lo per consistència. |
| `solucio` | int / Rational | Sí | Solució única de l'equació. Ha de coincidir amb el que SymPy retorna en `solve_for_x`. |
| `dependencies` | list[str] | Sí | Conceptes que aquest problema posa en joc. Cada element ha d'existir com a clau a `DEPENDENCIES`. Determina quins prereqs es poden activar. |
| `errors_freqüents` | list[str] | Sí | Errors típics esperats. Cada element ha d'existir com a clau a `ERROR_CATALOG`. **Pista per a la IA classificadora** — no és un filtre estricte, però acota els labels més probables. |
| `passos_esperats` | int | Opcional | Nombre de passos correctes esperats per resoldre el problema (sense comptar l'enunciat). Si està declarat i `≤ 6`, l'UI mostra un indicador de progrés visual amb punts (`●○○`) al panell de l'alumne; si és `> 6`, mostra només el text "Pas N de M"; si no està declarat, no es mostra cap indicador. **Sense conseqüència funcional** — només afecta la presentació. Si t'oblides de declarar-lo, l'alumne treballa igual però sense visual de progrés. |

### Convencions per a l'equació (`equacio_text`)

L'equació es passa al `verifier.parse_equation`, que normalitza alguns
caràcters abans de cridar a SymPy. Per tant pots usar (i és recomanable
que usis) la **notació humana**:

- `−` (signe menys Unicode) i `-` (guió ASCII) són equivalents. Recomanat: `−`.
- `·`, `×`, `*` són tots vàlids per a la multiplicació. Recomanat: deixar la juxtaposició com a `3x` (sense símbol explícit).
- `÷` i `/` són equivalents per a la divisió.
- Coma decimal: `2,5` es normalitza a `2.5`. Però **deixa `2.5`** si vols un Float, o `5/2` si vols un Rational. Per a problemes 2n d'ESO normalment no s'haurien d'usar decimals.
- Espais al voltant dels operadors: opcionals però fan l'equació més llegible per a l'alumne.

**Exemples vàlids:**
```
x + 7 = 12
3x − 5 = 10
3(x − 4) = 9
5 + 2(x − 3) = 7
x/2 + x/3 = 5
```

### Convencions de nomenclatura

L'id té tres parts: `EQ{nivell}-{família}-{seq}`.

- `nivell`: 1, 2, 3 o 4 (l'alçada del nivell pedagògic).
- `família`: A, B, C... — agrupa variants estructurals **dins d'un mateix nivell**. Exemples:
    - **EQ1-A**: equació d'un pas, suma (`x + b = c`).
    - **EQ2-A**: dos passos, resta (`ax − b = c`).
    - **EQ2-B**: dos passos, suma amb solució negativa (`ax + b = c`, `x < 0`).
    - **EQ3-A**: parèntesi pur (`a(x + b) = c`).
    - **EQ3-B**: parèntesi amb terme al davant (`d + a(x + b) = c`).
    - **EQ4-B**: fraccions (m.c.m. requerit).
- `seq`: número correlatiu dins de la família, amb 3 dígits (`001`, `002`, ...). Permet múltiples enunciats numèricament diferents que comparteixen estructura.

**Regla d'or:** problemes de la mateixa **família** comparteixen
estructura i errors típics. Per tant, dos problemes de la mateixa
família haurien de tenir les mateixes `dependencies` i `errors_freqüents`.

---

## `TEST_CASES`

Cada problema **ha de tenir** una entrada al dict `TEST_CASES`. La clau
és l'`id` del problema. El valor és una **llista de rondes**.

```python
"EQ2-B-001": [
    # Ronda 1: parteix de l'equació original "2x + 8 = 4"
    ["2x = -4", "2x = 12", "2x = 4", "2x + 8 = 12", "2x = -12"],
    # Ronda 2: parteix de l'estat al qual hagi avançat la ronda anterior, "2x = -4"
    ["x = -2", "x = 2", "x = -6", "x = -8", "2x = -2"],
],
```

### Format

- **Cada ronda és una llista d'inputs**. El **primer input** ha de ser una **resposta correcta** que avança cap a la solució. La resta són **errors versemblants**.
- El test runner usa el primer input per **avançar el baseline d'una ronda a la següent**. Per tant, el primer input de la ronda 2 ha de ser correcte des del resultat de la ronda 1.
- Els errors haurien de cobrir, com a mínim, els labels llistats a `errors_freqüents`. Fer-ne 3-5 per ronda és el balanç habitual.
- Total recomanat: **2-3 rondes per problema**, **4-6 inputs per ronda**.

### Comprovacions abans d'afegir un test cas

Per a **cada error candidat**, cal verificar dues coses amb un script ràpid:

1. **Parseja**: `verifier.parse_equation("...")` retorna una equació, no `None`.
2. **No és equivalent a l'estat actual** segons SymPy:
   `verifier.equations_equivalent(estat_actual, candidat)` retorna `False`.

Si SymPy considera que el candidat és equivalent (`True`), **no és un
error** — és una via algebraica vàlida i el sistema l'acceptaria com a
correcta. Cal descartar-lo o substituir-lo.

Exemple real (EQ2-B): `x + 4 = 2` SEMBLA un error (resultat de dividir
abans de restar) però SymPy detecta que és equivalent a `2x + 8 = 4`.
És un camí algebraicament vàlid, només pedagògicament menys directe. No
es pot usar com a "error" al test.

---

## `DEPENDENCIES`

Graf de **conceptes prerequisit** distribuïts en tres capes:

| Capa | Exemples |
|---|---|
| Aritmètica | `def_aritm_negatius`, `def_fraccions_equiv`, `def_mcm` |
| Algebraica | `principi_equiv`, `prop_distributiva`, `regla_signes_parens` |
| Procedimental | `operacions_inverses` |

Cada entrada:

```python
"def_aritm_negatius": {
    "description": "operations with negative integers",
    "keywords": ["negatiu", "negatius", "menys", "signe", "oposat", "contrari"],
    "prerequisite": "PRE-NEG",
},
```

| Camp | Tipus | Què és |
|---|---|---|
| `description` | str (anglès) | Descripció breu per als prompts a la IA. **En anglès** perquè el model està prompted en anglès. |
| `keywords` | list[str] | Pistes lèxiques per a l'identificació ràpida del concepte (no s'usen per a la classificació final, només com a indicador). |
| `prerequisite` | str | Id del prereq associat (clau a `PREREQUISITES`). |

**Quan cal afegir-ne una:** si introdueixes un problema que requereix
un concepte fonamentalment nou (per exemple, equacions amb decimals →
podria caldre `def_decimals`). En la majoria de casos els 7 conceptes
existents són suficients.

---

## `PREREQUISITES`

Cada `prerequisite` té un mini-problema associat per al retrocés.
N'hi ha **dos formats** segons com es valida la resposta:

### Format A: validació numèrica/simbòlica (SymPy)

```python
"PRE-NEG": {
    "id": "PRE-NEG",
    "concept": "def_aritm_negatius",
    "question": "Calcula el resultat de: −7 + 3",
    "expected_value": -4,
    "explanation": "Quan sumem un negatiu i un positiu, restem...",
},
```

| Camp | Tipus | Què és |
|---|---|---|
| `expected_value` | int / float / Rational | Resultat numèric esperat. Es compara amb `solve_for_x` o `parse_expression` segons el cas. |
| `expected_equation` | str | (alternativa a `expected_value`) Equació esperada. Es compara via `equations_equivalent`. |
| `expected_equation_or_expr` | str | (alternativa) Expressió o equació esperada. SymPy decideix la forma. |

### Format B: validació per paraules clau

```python
"PRE-INV": {
    "id": "PRE-INV",
    "concept": "operacions_inverses",
    "question": "Si tens 3 + x = 10, quina operació...",
    "keywords_required": ["restar", "resta", "−3", "-3", "menys 3", "treure"],
    "forbidden_keywords": ["multiplic", "divid"],
    "explanation": "...",
},
```

| Camp | Tipus | Què és |
|---|---|---|
| `keywords_required` | list[str] | **Almenys una** d'aquestes paraules ha d'aparèixer a la resposta. Comprova substring (sense word-boundary). |
| `forbidden_keywords` | list[str] | Si **qualsevol** d'aquestes apareix, la resposta es marca incorrecta encara que tingui keywords required. |

**Convencions per a `keywords_required`:**
- Inclou les conjugacions verbals comunes que un alumne escriuria: infinitiu, 1a persona present, 2a, 3a, 1a plural. Exemple per "sumar": `["sumar", "sumo", "sumes", "suma", "sumem"]`.
- Inclou sinònims naturals ("afegir" per "sumar", "treure" per "restar").
- Inclou notacions símbòliques rellevants (`+5`, `−3`, `:3`).
- Per a stems sense conjugació problemàtica, una sola arrel n'hi ha prou: `"multiplic"` cobreix multiplicar/multiplica/multiplico/etc.

**Atenció:** la comparació és per substring, sense word-boundary. `"resta"`
matchea `"presta"` i `"restaurant"`. Acceptable per a respostes curtes
però val la pena revisar les paraules clau quan la resposta esperada és
ambigua.

### Camps comuns a tots els formats

| Camp | Tipus | Què és |
|---|---|---|
| `id` | str | Mateix que la clau (`PRE-NEG`, etc.). |
| `concept` | str | Concepte de `DEPENDENCIES` que aquest prereq cobreix. |
| `question` | str | Pregunta visible per a l'alumne. **Adaptada al to de 13 anys.** Veure §"Patró de redacció" més avall. |
| `explanation` | str | Explicació mostrada quan es resol o falla el prereq. Format pedagògic: "<equació original> = <resultat>, perquè <raó operativa>". |

### Patró de redacció per a `question`

L'UI parseja el text de `question` amb un regex per renderitzar-lo en tres
línies separades visualment (equació en monospace, pregunta en bold, frase
"Explica-ho amb les teves paraules" en gris). Per que el regex funcioni,
la `question` ha de seguir **un dels dos patrons** següents:

```
Si tens <EQUACIÓ>, quina <pregunta>? Explica-ho amb les teves paraules.
Tens <EQUACIÓ> i vols <context>. Quina <pregunta>? Explica-ho amb les teves paraules.
```

Concretament, el regex busca:

- Text que comenci per `Si tens ` o `Tens ` seguit de l'equació, acabada per coma+minúscula o ` i ` o punt.
- Una pregunta que comenci per `Quina` o `quina` i acabi en `?`.

Si la `question` no segueix cap dels dos patrons, **no és un error**:
l'UI fa un fallback al format antic (la pregunta sencera en bold). El
resultat és lleig però funcional. Si vols el render bonic, ajusta't al
patró.

**Recomanació pràctica:** quan escriguis prereqs nous, comprova
visualment al `?debug=1` que la pregunta es renderitza en tres línies.
Si veus la pregunta sencera en una sola línia bold, el regex no l'ha
trobada i has caigut al fallback.

---

## `ERROR_CATALOG`

Catàleg d'etiquetes d'errors que la IA pot assignar quan classifica una
resposta errònia. Cada entrada: `id` → `descripció en anglès` (per al
prompt).

Convenció de noms:
- `L{nivell}_*`: error específic d'un nivell (per ex. `L3_distribution_partial`).
- `GEN_*`: error genèric (aritmètic, no classificable).

**Quan cal afegir-ne un:** si veus que el catàleg actual no descriu
adequadament un patró d'error que els alumnes fan repetidament al pilot.
És MILLOR afegir un nou label específic que abusar de `GEN_other`.

Si afegeixes un label que té una dependència conceptual implicada
(p.ex. afegeixes `L3_factor_drop` que correspon a un buit de
`prop_distributiva`), afegeix-lo també al dict `_ERROR_TO_DEPENDENCY` per
activar el retrocés automàtic.

### Labels actuals del catàleg

| Label | Descripció (anglès, per al prompt) | Afegit |
|---|---|---|
| `L1_inverse_op` | used the wrong inverse operation (e.g. subtracted instead of dividing) | Fase 3 |
| `L1_sign_error` | correct operation but wrong sign on the result | Fase 3 |
| `L2_order` | correct operations but applied in the wrong order | Fase 3 |
| `L2_transpose_sign` | transposed a term but forgot to change its sign | Fase 3 |
| `L2_one_side_only` | applied the operation to one side of the equation only | Fase 3 |
| `L2_like_terms` | failed to collect like terms before isolating: treated ax + bx as a single step without first simplifying the coefficient (e.g. 2x + 5x left as-is, or combined incorrectly as 10x) | GAPs 1-5 |
| `L3_distribution_partial` | distributed a factor to some terms inside parentheses but not all | Fase 3 |
| `L3_minus_paren` | dropped or reversed the sign when distributing a negative factor across parentheses | Fase 3 |
| `L3_combine_terms` | failed to combine variable terms from both sides before isolating | Fase 3 |
| `L4_mcm_partial` | cleared fractions by multiplying by an incomplete LCM | Fase 3 |
| `L4_illegal_cancel` | cancelled a term algebraically without multiplying both sides | Fase 3 |
| `L4_minus_fraction` | dropped the negative sign when operating on a term with a fraction preceded by minus | Fase 3 |
| `GEN_arithmetic` | arithmetic error in a computation step | Fase 3 |
| `GEN_other` | error not matching any specific category (classifier fallback) | Fase 3 |

---

## Famílies reservades (estat après GAPs 1-5)

Aquesta taula recull totes les famílies existents o reservades. **No creis
una família amb un id ja present aquí sense coordinació prèvia** — podries
xocar amb un problema que algú altre ja ha redactat o té previst.

Si vols afegir un segon enunciat a una família existent (p.ex. `EQ2-E-002`),
no cal coordinació — sempre que la clau `-002` no existeixi ja.

| Família | Estructura | Estat |
|---|---|---|
| `EQ1-A` | Un pas, suma (`x + b = c`) | Existent |
| `EQ1-B` | Un pas, multiplicació (`ax = c`) | Existent |
| `EQ1-C` | Un pas, resta (`x − b = c`) | Existent |
| `EQ1-D` | Un pas, divisió simple (`x/n = c`) | Existent (GAP 1) |
| `EQ2-A` | Dos passos, resta (`ax − b = c`) | Existent |
| `EQ2-B` | Dos passos, solució negativa (`ax + b = c`, `x < 0`) | Existent |
| `EQ2-C` | Dos passos, coeficient negatiu (`−ax + b = c`) | Existent |
| `EQ2-D` | Dos passos, incògnita a la dreta (`c = ax + b`) | Existent |
| `EQ2-E` | Termes semblants un costat (`ax + bx = c`) | Existent (GAP 2) |
| `EQ2-F` | Termes semblants intercalats LHS (`b + ax + d − x = c`) | Existent (GAP 2) |
| `EQ2-G` | *Lliure (pròxima variant EQ2 si cal)* | Disponible |
| `EQ2-H` | Recollir ambdós costats + transposar | Existent (GAP 3b) |
| `EQ2-I` | Recollir ambdós costats + transposar + dividir | Existent (GAP 3b) |
| `EQ2-X` | Coeficient fraccionari propi (`(a/b)x = c`) | Existent (GAP 1) |
| `EQ3-A` | Parèntesi pur (`a(x + b) = c`) | Existent |
| `EQ3-B` | Parèntesi amb terme al davant (`d + a(x + b) = c`) | Existent |
| `EQ3-C` | x als dos costats, un terme cada costat (`ax + b = x + c`) | Existent |
| `EQ3-D` | Menys davant parèntesi (`b − (x + d) = c`) | Existent |
| `EQ3-E` | x als dos costats, coeficients positius (`ax + b = bx + c`) | Existent (GAP 4) |
| `EQ3-F` | x als dos costats, coef. negatiu LHS (`b − ax = cx + d`) | Existent (GAP 4) |
| `EQ3-G` | x als dos costats, coef. negatiu, solució positiva | Existent (GAP 4) |
| `EQ3-H` | Parèntesis als dos costats (`a(x+b) = c(x+d)`) | Existent (GAP 5) |
| `EQ3-I` | Dos parèntesis LHS, menys davant segon (`a(x+b) − c(x+d) = 0`) | Existent (GAP 5) |
| `EQ4-A` | Una fracció, numerador binomi (`(x+b)/n = c`) | Existent |
| `EQ4-B` | Fraccions amb m.c.m. requerit | Existent |
| `EQ4-C` | Menys davant fracció (`b − (x+d)/n = c`) | Existent |

1. **Decidir nivell i família.** Si encaixa en una família existent (per
   ex. `EQ2-A` amb números diferents), reusa la família. Si és una
   variant estructural diferent, crea una família nova (`EQ2-B`,
   `EQ2-C`, ...).

2. **Verificar amb el verifier que l'equació parseja i que la solució
   és la que esperes:**

   ```bash
   python -c "
   import verifier as V
   eq = V.parse_equation('LA TEVA EQUACIÓ AQUÍ')
   print('parses?', eq is not None)
   print('forma vàlida?', V.validate_equation_form(eq))
   print('solució:', V.solve_for_x(eq))
   "
   ```

3. **Afegir l'entrada a `PROBLEMS`** seguint el format d'un problema
   existent del mateix nivell.

4. **Dissenyar les rondes de test.** Per cada ronda:
   - Triar un input correcte que avanci.
   - Triar 3-5 errors versemblants que cobreixin els `errors_freqüents`.
   - **Verificar tots els errors** (parsegen + no equivalents) com a §"Comprovacions abans d'afegir un test cas".

5. **Afegir l'entrada a `TEST_CASES`.**

6. **Validar al runner** (mode debug → "Test exhaustiu"). Tots els
   inputs correctes haurien de marcar `match=True`; tots els errors
   també (perquè no haurien de ser equivalents).

7. **Si has tocat `DEPENDENCIES`, `PREREQUISITES` o `ERROR_CATALOG`:**
   verifica que els tests existents segueixen passant
   (`python -m unittest test_verifier`).

---

## Resum visual: relacions entre estructures

```
              ┌─────────────────────────────────┐
              │         PROBLEMS                │
              │  (què resol l'alumne)           │
              └────┬────────────────┬───────────┘
                   │                │
   referencia      │                │ referencia
                   ▼                ▼
       ┌──────────────────┐    ┌──────────────────┐
       │   DEPENDENCIES   │    │  ERROR_CATALOG   │
       │  (conceptes)     │    │  (etiquetes IA)  │
       └────────┬─────────┘    └──────────────────┘
                │
                │ apunta a
                ▼
       ┌──────────────────┐
       │  PREREQUISITES   │
       │  (mini-preguntes │
       │   pel retrocés)  │
       └──────────────────┘

              ┌─────────────────────────────────┐
              │         TEST_CASES              │
              │   (mateixa clau que PROBLEMS)   │
              └─────────────────────────────────┘
```
