# TODO_DEFERRED — Tasques diferides i troballes pendents

Document creat el 2026-05-11 com a complement de la sessió d'enduriment del
tutor (afegida la suite de propietats, el simulador de sessions i el sistema
d'invariants en runtime). Revisat el mateix dia després d'una troballa que
canvia l'arquitectura del document (veure F0 més avall).

Estructura:

- **A.** Troballes concretes: bugs reals al codi i a la base de dades.
- **B.** Discrepàncies entre documentació i codi.
- **C.** Recomanacions arquitecturals no implementades.
- **D.** Tasques de procés i qualitat descobertes durant la implementació.

---

## A. Troballes concretes — bugs reals

### F1. `EQ4-A-001` i `EQ4-C-001` declaren `L4_mcm_partial` sense `def_mcm` a `dependencies`

**Severitat**: mitjana. **Localització**: `problems.py`, `PROBLEMS`.

`L4_mcm_partial` està al mapatge `_ERROR_TO_DEPENDENCY` (→ `def_mcm`). Quan
la IA classifica un error d'un alumne com `L4_mcm_partial` en aquests dos
problemes, la lògica de fallback determinista a `tutor.py:434` mira si la
dep implicada (`def_mcm`) és a les `dependencies` del problema; com que no
hi és, **no es dispara el retrocés a `PRE-MCM`**. L'alumne rep un missatge
d'error genèric però no es desencadena cap remediació conceptual.

`EQ4-B-001`, en canvi, sí que té `def_mcm` declarada — per tant és
inconsistència entre problemes de la mateixa família Nivell 4.

**Fix proposat (decisió pedagògica)**: triar una de les opcions:

- (a) Afegir `def_mcm` a les `dependencies` d'`EQ4-A-001` i `EQ4-C-001`.
  Argument a favor: si la IA detecta `L4_mcm_partial`, vol dir que
  l'alumne ha intentat usar el mcm; per tant té sentit que el prereq
  estigui disponible.
- (b) Treure `L4_mcm_partial` dels `errors_freqüents` d'aquests dos
  problemes (només una sola fracció en cada cas — potser no és un error
  realista en aquests problemes concrets).

Recomanat: (b) per `EQ4-A-001` i `EQ4-C-001`, si el professor confirma
que no hi ha un error de "mcm parcial" realista en aquests casos.

**Status del test**: el bug està whitelistat a
`test_problems_properties.py:TestErrorToDependencyReachability.KNOWN_UNREACHABLE`.
Quan es fixi, treure les dues entrades; la suite ha de continuar passant.

### F4. La branca "terminal correcte" no crida `_post_verdict_bookkeeping`

**Severitat**: baixa. **Localització**: `tutor.py:342-350` (dins
`_evaluate_equation_step`).

Quan l'alumne arriba a `x = c` amb `c` igual a la solució, el codi grava
el pas, marca `verdict_final = "resolt"`, i retorna directament sense
passar per `_post_verdict_bookkeeping`. Conseqüència: els comptadors
`stagnation_consecutive`, `pending_proactive_offer` i el dict
`concept_failure_streak` **no es reseteg** al moment de resoldre.

Impacte funcional: cap mentre la sessió s'acaba aquí (és el final). Però
si en algun moment futur algú implementa una transició "post-resolt"
(seguir amb el problema següent, recompte agregat, etc.), aquests
comptadors arrossegaran valors de pre-solució i donaran mètriques falses.

**Fix proposat**: una sola línia abans del `return state` final de la
branca terminal:

```python
_post_verdict_bookkeeping(state, "correcte_progres", original_text)
```

**Status del test**: el comportament actual està documentat (no testat)
a `test_session_simulator.py:TestStagnationDetection.test_progress_resets_stagnation`.
Si es fa el fix, el comentari del test ja no aplica i es pot simplificar.

---

## B. Discrepàncies entre documentació i codi

### F0. *(Meta-troballa)* `STATUS.md` descriu un estat que no és el del codi

**Severitat**: alta com a font de confusió; nul·la com a bug d'execució.
**Localització**: `STATUS.md` vs. `problems.py`.

`STATUS.md` afirma:

> "**25 problemes** a `PROBLEMS`, distribuïts: 4 nivell 1, 9 nivell 2,
> 9 nivell 3, 3 nivell 4. Els 14 originals amb `TEST_CASES` validats per
> SymPy; els 11 nous pendents de validació."

`problems.py` real conté **14 problemes**: 3 de nivell 1 (A, B, C), 4 de
nivell 2 (A, B, C, D), 4 de nivell 3 (A, B, C, D), 3 de nivell 4 (A, B, C).
Els 11 problemes nous mencionats **no són enlloc del repositori**: ni a
`problems.py`, ni en una branca, ni en un fitxer separat.

**Implicacions:**

- La frase "11 nous pendents de validació" del `STATUS.md` no descriu
  una tasca de validació pendent: descriu una tasca d'**integració**
  pendent. Algú (probablement el company a qui es va delegar
  l'autoria) té els 11 nous en algun lloc fora del repo i encara no
  han entrat.
- `README.md` diu "4 problemes (un per nivell): EQ1-A, EQ2-A, EQ3-A,
  EQ4-B" — això reflecteix la Fase 0 original, abans dels GAPs 1-5
  que ompliren els 14 actuals. També està desactualitzat.
- Els findings F2 i F3 d'aquest document (vegeu més avall) són
  **conseqüències directes** d'aquesta discrepància, no problemes
  independents.

**Fix proposat**:

1. Reconciliar `STATUS.md` amb la realitat del codi: afirmar 14
   problemes integrats, descriure els 11 com a "pendents d'integració
   per part del company" amb un enllaç on són (Drive, branca local, etc.).
2. Actualitzar `README.md` amb el número real.
3. Establir un test mecànic que verifiqui que la xifra mencionada a
   `STATUS.md` i `README.md` coincideix amb `len(problems.PROBLEMS)`.
   Es pot fer amb una constant compartida o amb un test que parsegi els
   .md amb regex.

### F2. `L3_combine_terms` només té cobertura d'un problema (`EQ3-C-001`)

**Severitat**: baixa-mitjana (un cop F0 entès). **Localització**: `problems.py`.

`STATUS.md` afirma "L3_combine_terms (5+ — el forat de Fase 3 ara cobert
per GAPs 3b/4/5)". A la base actual només `EQ3-C-001` té aquesta etiqueta.

**Diagnosi revisada**: els 5+ esmentats són dins de la tongada
d'11 problemes no integrats (F0). Mentre aquesta tongada no entri al
codi, la cobertura real és d'un sol problema.

**Acció recomanada**: cap acció autònoma — quan la tongada s'integri
(F0), comprovar que els problemes corresponents declaren `L3_combine_terms`
i treure'l de `KNOWN_SINGLETONS` a `test_problems_properties.py`.

### F3. `L2_like_terms` està a la documentació però **no és a `ERROR_CATALOG`**

**Severitat**: baixa (un cop F0 entès). **Localització**: `problems.py`,
`SCHEMA.md`.

`SCHEMA.md` documenta `L2_like_terms` com a etiqueta. El catàleg real
no la conté.

**Diagnosi revisada**: aquesta etiqueta està documentada en previsió
de la tongada d'11 problemes (F0). Sense aquests problemes al codi,
cap alumne pot generar un error que la requereixi, i la IA no la veu
mai a la llista que se li passa per classificar — per tant tampoc no
hi ha cap classificació silenciosament desviada cap a altres
etiquetes.

**Acció recomanada**: quan la tongada s'integri (F0), afegir l'entrada
al `ERROR_CATALOG` amb la descripció que apareix a `SCHEMA.md:264`:

```python
"L2_like_terms": (
    "failed to collect like terms before isolating: treated ax + bx as "
    "a single step without first simplifying the coefficient "
    "(e.g. 2x + 5x left as-is, or combined incorrectly as 10x)"
),
```

I un cop al catàleg, comprovar via test exhaustiu que la IA la tria
correctament per als errors d'aquesta naturalesa als problemes nous.

---

## C. Recomanacions arquitecturals no implementades

Vam acordar (d) + (f) + (g) (propietats, simulador, invariants).
Les següents van quedar fora però tenen sentit. Ordenades per palanca.

### B1. ~~Verificador post-IA per a `classify_error`~~ ✅ Fet (2026-05-11)

**Implementat com a `error_consistency.py`** + integració a `tutor.py:436`.
Per a cada etiqueta del catàleg amb una condició estructural òbvia
(parèntesis, fraccions, x als dos costats, etc.), una regla determinista
comprova si l'etiqueta és consistent amb el delta `last_correct → attempt`.
Si no, l'etiqueta es descarta i es reemplaça per `GEN_arithmetic` amb un
missatge genèric. La revisió s'anota al pas com a `error_label_revised`
per a auditoria del rastre JSON.

**Cobertura inicial** (7 etiquetes amb regla):
`L3_distribution_partial`, `L3_minus_paren`, `L3_combine_terms`,
`L4_mcm_partial`, `L4_minus_fraction`, `L4_illegal_cancel`, `L2_like_terms`.

**Etiquetes sense regla** (passen sempre, conservadorisme deliberat):
`L1_inverse_op`, `L1_sign_error`, `L2_order`, `L2_transpose_sign`,
`L2_one_side_only`, `GEN_*`. Ampliable afegint entrades a `_CHECKS` —
cap canvi a la interfície necessari.

**Filosofia**: el verificador atrapa **fals positius** estructurals (la
IA al·lucina una etiqueta que el context contradiu). NO atrapa errors
de matís dins de tipologies plausibles: això requeriria una verificació
semàntica que SymPy no fa. Per al pilot, és la xarxa òptima cost/benefici.

**Tests**: 35 unitaris (`test_error_consistency.py`) + 6 end-to-end al
simulador (`TestPostIAConsistencyVerifier`).

### B2. Tipus explícits per als inputs

**Què és**: un `enum InputKind` amb els 7-8 valors reals d'input
(equació correcta / incorrecta / amb errada tipogràfica / expressió
sense `=` / format malformat / no-matemàtic / escapament / abús), i una
funció pura `classify(raw_text) → InputKind` com a únic punt de decisió.

**Per què importa**: la classificació està avui escampada en `if`s al
llarg de `_evaluate_equation_step`. Els bugs B2 i B3 del catàleg
original van existir per aquesta dispersió.

**Cost**: refactor mitjà de `tutor.py` i `verifier.py`.
**Quan**: oportunista, si es fa una refactor de `tutor.py` per qualsevol
altre motiu. No urgent per al pilot.

### B3. Capa de validació pedagògica entre SymPy i el veredicte

**Què és**: una funció `pedagogically_acceptable(prev, new) → bool` que,
després de SymPy dir "equivalent", verifica invariants pedagògics
explícits abans de declarar un pas com a correcte. Inclou la comprovació
que ja existeix a `is_terminal(raw_text)` però generalitzada (forma
simplificada, no termes residuals, etc.).

**Per què importa**: el bug B4 (cas `2x/2 = 8/2`) ja està parcialment
cobert amb la comprovació textual a `is_terminal`, però és un pegat
puntual. Una capa formal cobriria casos no anticipats (per exemple,
`x + 0 = 5` declarat resolt).

**Cost**: mig sprint. Decideix quines són les "formes acceptables" per
a cada estat pedagògic (és en part decisió del professor).
**Quan**: post-pilot, si els rastres mostren alumnes que produeixen
formes estranyes acceptades com a correctes.

### B4. Fuzz del parser

**Què és**: un script (Hypothesis o propi) que generi 1000+ strings rars
(Unicode mesclat, espais combinats, símbols barrejats) i comprovi que
`verifier.parse_equation` mai peta i que `has_math_content` és consistent.

**Cost**: 1-2 hores.
**Quan**: oportunista. Si surt un cas com el fullwidth equals durant
el pilot, val la pena dedicar-hi un matí.

---

## D. Procés i qualitat

### D1. ~~*Single source of truth* per a la documentació tècnica~~ ✅ Fet (2026-05-11)

**Implementat com a `test_docs_match_code.py`** (7 tests). Comprova:

- Famílies marcades "Existent" a SCHEMA.md vs. famílies reals a `PROBLEMS`.
- Etiquetes a la taula d'`ERROR_CATALOG` de SCHEMA.md vs. claus reals.
- Marcadors HTML `<!-- problem-count -->N<!-- /problem-count -->` a README/STATUS vs. `len(PROBLEMS)`.
- Marcadors `<!-- prereq-count -->N<!-- /prereq-count -->` vs. `len(PREREQUISITES)`.

**Whitelists explícites**:
- `TestErrorCatalogMatchesSchema.known_pending_f3`: tolera `L2_like_terms` mentre F0/F3 no es resolguin.
- `TestFamiliesMatchSchema.KNOWN_PENDING_F0`: tolera les 11 famílies pendents d'integració.

Quan F0 es resolgui (els 11 problemes nous entren al codi *o* es retiren
de SCHEMA.md), buidar ambdues whitelists i confirmar que la suite passa.

**Restant de l'acció ideal** (no implementat): derivar la taula de
SCHEMA.md automàticament a partir del codi. Es pot fer post-pilot si la
divergència torna a aparèixer. Per ara, el test detecta la deriva amb
prou claredat per al manteniment manual.

### D2. Fuzzer de seqüències per a `process_turn`

El simulador comprova escenaris específics. Una bona addició seria un
test que, donat un fuzzer d'inputs aleatoris, garanteixi que cap
seqüència porta a un estat sense `verdict_final` o amb invariants
trencats. Els invariants ja ho cobreixen estructuralment al runtime;
això seria belt-and-suspenders.

**Cost**: 1 hora. **Quan**: opcional.

### D3. Cobertura del simulador sobre `tutor.py`

Mesurada el 2026-05-11 amb `coverage.py`: el simulador cobreix **57%
de `tutor.py`** i **76% de `invariants.py`**. Les branques no cobertes
són majoritàriament codi de fallback d'errors d'API
(`except Exception → push warning`) i escenaris secundaris
(`generate_hint` dins de prereq actiu, casos específics de
`is_same_text`).

**Per reproduir**:

```bash
coverage run --source=tutor,invariants -m unittest test_session_simulator
coverage report
```

**Cost per arribar al 80%**: 2-3 hores afegint 5-8 escenaris.
**Quan**: oportunista. Acceptable per al pilot tal com està (les
branques crítiques de la màquina d'estats sí que estan cobertes).

---

## Estat final de les noves suites

| Mòdul | Tests | Detecta |
|---|---|---|
| `test_verifier.py` | 71 | Bugs de parsing, equivalència, validació de forma |
| `test_problems.py` | 19 | Integritat d'esquema de la base |
| `test_problems_properties.py` | 13 | Forats estructurals (reachability, famílies, trampes) |
| `test_session_simulator.py` | 30 | Bugs a la màquina d'estats sense cost API |
| `test_docs_match_code.py` | 7 | Discrepàncies entre doc i codi (F0/F3) |
| `test_error_consistency.py` | 35 | Al·lucinacions causals de la IA (bug A3) |
| `test_api_logger.py` | 8 | Filtre per session/student |
| **Total** | **183** | |

Notes operatives:

- `invariants.py` es pot desactivar amb `TUTOR_INVARIANTS=off`. **No
  recomanat en producció**: el cost és microscòpic i detecten classes
  senceres de bugs.
- `test_problems_properties.py` passa amb 2 forats whitelistats
  (els dos casos d'F1: `EQ4-A-001` i `EQ4-C-001`). F2 està
  whitelistat com a "singleton conegut" — quan F0 es resolgui i els
  11 problemes nous s'integrin, caldrà revisar si segueix
  whitelistat o ja no.
- `test_session_simulator.py` mocka la IA. Cap test fa crides reals.
