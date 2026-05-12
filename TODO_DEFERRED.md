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

### F1. ~~`EQ4-A-001` i `EQ4-C-001` declaren `L4_mcm_partial` sense `def_mcm` a `dependencies`~~ ✅ Resolt (2026-05-11)

Aplicada l'opció (b): `L4_mcm_partial` retirat dels `errors_freqüents`
d'`EQ4-A-001` i `EQ4-C-001`, perquè cap dels dos té dues o més fraccions
amb denominadors diferents (la condició necessària per al concepte de mcm
parcial). `EQ4-B-001`, que sí en té, manté l'etiqueta com a único portador.

La whitelist `KNOWN_UNREACHABLE` de `test_problems_properties.py` està
buidada. Conseqüència: `L4_mcm_partial` és ara singleton (un sol problema),
documentat explícitament a `KNOWN_SINGLETONS` amb justificació estructural.

### F4. ~~La branca "terminal correcte" no crida `_post_verdict_bookkeeping`~~ ✅ Resolt (2026-05-11)

Afegida la crida una línia abans del `return state` final de la branca
terminal correcte a `tutor.py:_evaluate_equation_step`. Els comptadors
d'estancament i streaks conceptuals ara es reseteg en arribar a `x = c`
solució correcta, com a la resta de branques. Comportament documentat
amb el test de regressió `TestStagnationDetection.test_terminal_resets_stagnation`.

---

## B. Discrepàncies entre documentació i codi

### F0. ~~*(Meta-troballa)* `STATUS.md` descriu un estat que no és el del codi~~ ✅ Resolt (2026-05-11)

Els 11 problemes pendents (`EQ1-D-001`, `EQ2-X-001`, `EQ2-E/F/H/I-001`,
`EQ3-E/F/G/H/I-001`) s'han integrat a `problems.py`. Marcadors `<!-- problem-count -->`
de `README.md` i `STATUS.md` actualitzats a 25. `KNOWN_PENDING_F0` a
`test_docs_match_code.py` buidat.

**TEST_CASES dels 11 nous problemes**: completats el mateix dia. Proposta
generada per Claude i revisada pel professor — 28 rondes addicionals i
125 inputs nous (total base: 58 rondes, 265 inputs). La whitelist
`KNOWN_PENDING_TEST_CASES` de `test_problems.py` també està buidada.

**Encara pendent (no bloquejant)**: validació pedagògica via test
exhaustiu (`?debug=1` a l'app). Confirmaria que les etiquetes d'error
proposades coincideixen amb les que la IA assigna realment. Si hi ha
discrepàncies, ajustar les descripcions del `ERROR_CATALOG` o els
inputs concrets dels TEST_CASES.

### F2. ~~`L3_combine_terms` només té cobertura d'un problema~~ ✅ Resolt (2026-05-11)

Amb la integració dels 11 problemes nous, `L3_combine_terms` ara apareix
a `EQ2-H-001`, `EQ2-I-001`, `EQ3-C-001`, `EQ3-E-001`, `EQ3-F-001`,
`EQ3-G-001`, `EQ3-H-001`, `EQ3-I-001` — 8 problemes. La whitelist
`KNOWN_SINGLETONS` de `test_problems_properties.py` ja no inclou aquesta
etiqueta.

### F3. ~~`L2_like_terms` està a la documentació però no és a `ERROR_CATALOG`~~ ✅ Resolt (2026-05-11)

Afegida l'entrada al `ERROR_CATALOG`. La utilitzen 4 problemes:
`EQ2-E-001`, `EQ2-F-001`, `EQ2-H-001`, `EQ2-I-001`. La whitelist
`known_pending_f3` de `test_docs_match_code.py` buidada.

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
| `test_session_simulator.py` | 31 | Bugs a la màquina d'estats sense cost API |
| `test_docs_match_code.py` | 7 | Discrepàncies entre doc i codi (F0/F3) |
| `test_error_consistency.py` | 35 | Al·lucinacions causals de la IA (bug A3) |
| `test_api_logger.py` | 8 | Filtre per session/student |
| **Total** | **184** | |

Notes operatives:

- `invariants.py` es pot desactivar amb `TUTOR_INVARIANTS=off`. **No
  recomanat en producció**: el cost és microscòpic i detecten classes
  senceres de bugs.
- `test_problems_properties.py` ja no té forats reals whitelistats.
  Conté només `KNOWN_SINGLETONS = {"L4_minus_fraction", "L4_mcm_partial"}`,
  ambdues amb justificació estructural (singletons per disseny).
- `test_problems.py` no té whitelists actives: tots els 25 problemes
  tenen `TEST_CASES` complets.
- `test_session_simulator.py` mocka la IA. Cap test fa crides reals.
- F0, F1, F2, F3, F4 i D1 (single source of truth) resolts. Cap finding
  obert en aquest document. Tots els tests verds (184/184) en ambdós
  modes (amb i sense invariants).
