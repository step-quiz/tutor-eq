# TODO_DEFERRED — Tasques diferides i troballes pendents

Document creat el 2026-05-11 com a complement de la sessió d'enduriment del
tutor (afegida la suite de propietats, el simulador de sessions i el sistema
d'invariants en runtime). Recull dues coses:

1. **Findings**: bugs reals descoberts per les noves suites que no s'han
   arreglat automàticament i requereixen decisió humana (pedagògica o
   estructural).
2. **Recomanacions no implementades**: les propostes (a), (b), (c), (e) que
   van quedar fora d'aquest sprint i que tindrien sentit fer abans del pilot
   o just després.

---

## A. Findings concrets de les noves suites

Aquests són bugs reals que el sistema **no detectava** abans i que ara
queden marcats explícitament a `test_problems_properties.py` amb una
whitelist (`KNOWN_UNREACHABLE`, `KNOWN_SINGLETONS`). La suite passa, però
treure'ls de la whitelist els fa fallar, validant que es resolen quan toqui.

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
  realista en aquests problemes concrets). Argument a favor:
  `L4_mcm_partial` està pensat per a equacions amb DUES o més fraccions
  que requereixen mcm; en `(x+1)/3 = 4` el mcm és trivial.

Recomanat: (b) per `EQ4-A-001` (només una fracció) i `EQ4-C-001` (només
una fracció), si el professor confirma que no hi ha un error de "mcm
parcial" realista en aquests casos.

**Com es treu de la whitelist quan estigui fix**: editar
`test_problems_properties.py`, treure les dues entrades de
`KNOWN_UNREACHABLE`. La suite ha de continuar passant.

### F2. `L3_combine_terms` només té cobertura d'un problema (`EQ3-C-001`)

**Severitat**: baixa. **Localització**: `problems.py`, `PROBLEMS`.

La `STATUS.md` afirma "L3_combine_terms (5+ — el forat de Fase 3 ara
cobert per GAPs 3b/4/5)". A la base actual, només `EQ3-C-001` té aquesta
etiqueta. Els problemes `EQ2-H-001`, `EQ2-I-001`, `EQ3-E-001`,
`EQ3-F-001`, `EQ3-G-001` haurien d'haver-la rebut segons la documentació
i no la tenen.

**Cap d'aquests és necessàriament un bug**: la classificació d'errors
del professor pot ser correcta i la `STATUS.md` desactualitzada. Però la
discrepància entre doc i codi suggereix una decisió pendent.

**Fix proposat**: en una revisió dels `errors_freqüents` dels 5 problemes
mencionats, afegir `L3_combine_terms` als que correspongui (probablement
tots els que tenen x a ambdós costats: `EQ3-E`, `EQ3-F`, `EQ3-G`).

**Com es treu de la whitelist**: editar
`test_problems_properties.py:TestCoverageHealth.KNOWN_SINGLETONS`, treure
`"L3_combine_terms"`. Si la cobertura puja a 2+, la suite passa.

### F3. `L2_like_terms` està a la documentació però **no és a `ERROR_CATALOG`**

**Severitat**: mitjana-alta. **Localització**: `problems.py`, `ERROR_CATALOG`.

`SCHEMA.md` i `STATUS.md` llisten `L2_like_terms` com a etiqueta vigent
("Fet manualment per l'usuari... `L2_like_terms` afegit ara al
`ERROR_CATALOG`"). El codi real **no la conté**. Els problemes nous dels
GAPs 2-5 (`EQ2-E-001`, `EQ2-F-001`, etc.) no poden declarar aquesta
etiqueta sense fer fallar `test_problems.py`. La IA, en classificar, mai
no la veurà a la llista que se li passa, i per tant mai no la triarà.

**Fix proposat**: afegir l'entrada al catàleg amb la descripció que ja
apareix a `SCHEMA.md:264`:

```python
"L2_like_terms": (
    "failed to collect like terms before isolating: treated ax + bx as "
    "a single step without first simplifying the coefficient "
    "(e.g. 2x + 5x left as-is, or combined incorrectly as 10x)"
),
```

I, en una segona passada, revisar quins dels 11 problemes nous GAPs 1-5
haurien de declarar-la a `errors_freqüents`.

**Aquest finding no està a la whitelist** perquè cap test de propietats
el detecta directament (és una discrepància doc-vs-codi). Convindria
afegir un test que parsejés `SCHEMA.md` o, més senzill, llistar les
etiquetes oficialment vigents en una constant compartida i que tant
`SCHEMA.md` com `ERROR_CATALOG` derivin d'ella.

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

Es pot fer ara o post-pilot. Si es fa, comprovar que `test_session_simulator`
continua verd (un test podria dependre del comportament actual; en aquest
moment cap ho fa).

---

## B. Recomanacions no implementades

Vam acordar (d) + (f) + (g). Les següents van quedar fora però tenen
sentit. Estan ordenades per palanca / ratio benefici-cost.

### B1. Verificador post-IA per a `classify_error` (recomanació (c))

**Què és**: una funció determinista que, donada la classificació de la
IA (`error_label`) i el delta entre `last_correct_text` i `attempt_text`,
comprova si l'etiqueta és consistent amb la transformació real.
Si no, descarta l'etiqueta i cau a `GEN_arithmetic`.

**Per què importa**: és la xarxa de seguretat contra el bug A3 del
catàleg (la IA al·lucina causes plausibles però falses). Avui el
pre-check de coeficient (`x_coefficient`) cobreix només una part molt
concreta. Una funció més general — comparant nombre de termes, presència
de parèntesis, signes — atraparia més casos.

**Cost**: 1-2 sessions de feina per fer-ho amb cura. Cada error
classificat fa una comprovació O(1) extra.

**Quan fer-ho**: abans del pilot. És la palanca més gran que queda
sense activar.

### B2. Tipus explícits per als inputs (recomanació (a))

**Què és**: un `enum InputKind` amb els 7-8 valors reals (equació
correcta / incorrecta / amb errada tipogràfica / expressió sense `=` /
format malformat / no-matemàtic / escapament / abús), i una funció pura
`classify(raw_text) → InputKind` com a únic punt de decisió. La resta
del codi rep el tipus, no el text.

**Per què importa**: la classificació està avui escampada en `if`s al
llarg de `_evaluate_equation_step`. Els bugs B2 i B3 van existir
precisament per aquesta dispersió.

**Cost**: refactor mitjà. Requereix tocar `tutor.py` i `verifier.py` amb
cura.

**Quan fer-ho**: si es fa una refactor de `tutor.py` (per qualsevol
altre motiu), aprofitar el moment. No és urgent per al pilot.

### B3. Capa de validació pedagògica entre SymPy i el veredicte (recomanació (b))

**Què és**: una funció `pedagogically_acceptable(prev, new) → bool` que,
després de SymPy dir "equivalent", verifica invariants pedagògics
explícits abans de declarar un pas com a correcte. Inclou la
comprovació que ja existeix a `is_terminal(raw_text)` però generalitzada
(forma simplificada, no termes residuals, etc.).

**Per què importa**: B4 (cas `2x/2 = 8/2`) ja està parcialment cobert
amb la comprovació textual a `is_terminal`, però és un pegat puntual.
Una capa formal cobriria casos no anticipats (per exemple, formes
"vàlides però estranyes" com `x + 0 = 5`).

**Cost**: mig sprint. Requereix decidir quines són les "formes
acceptables" per a cada estat pedagògic (és en part decisió del
professor).

**Quan fer-ho**: post-pilot, si la recol·lecció de rastres mostra que
els alumnes troben formes pedagògicament estranyes que el sistema deixa
passar com a correctes.

### B4. Fuzz del parser (recomanació (e))

**Què és**: un script (Hypothesis o propi) que genera 1000+ strings rars
(Unicode mesclat, espais combinats, símbols barrejats) i comprova que
`verifier.parse_equation` mai peta i que `has_math_content` és consistent.

**Cost**: 1-2 hores.

**Quan fer-ho**: oportunista. Si surt un cas com B1 (fullwidth equals)
durant el pilot, val la pena dedicar-hi un matí.

---

## C. Tasques noves descobertes durant la implementació

### C1. Documentació-vs-codi: caldria un "single source of truth" per a `ERROR_CATALOG`

El finding F3 mostra el problema: `SCHEMA.md` i `ERROR_CATALOG` poden
divergir sense que cap test ho atrapi. Opció senzilla: que `SCHEMA.md`
generi la taula d'etiquetes a partir d'`ERROR_CATALOG` automàticament
(via un petit script `scripts/render_schema.py`), o a l'inrevés, que
`ERROR_CATALOG` es carregui d'un YAML que `SCHEMA.md` també referencia.

**Cost**: 1-2 hores. **Quan**: si tornem a tocar el catàleg.

### C2. Test "every session ends in a valid final verdict"

El simulador comprova `verdict_final` en cada test individual. Una bona
addició seria un test que, donat un fuzzer d'inputs aleatoris, garanteixi
que cap seqüència porta a un estat sense `verdict_final` o amb un
`verdict_final` invàlid. Els invariants ja ho cobreixen estructuralment;
això seria belt-and-suspenders.

**Cost**: 1 hora. **Quan**: opcional.

### C3. Mètrica: cobertura de codi de `tutor.py` pel simulador

Mesurada el 2026-05-11 amb `coverage.py`: el simulador cobreix **57% de
`tutor.py`** i **76% de `invariants.py`**. Les branques no cobertes són
majoritàriament codi de fallback d'errors d'API (`except Exception → push
warning`) i escenaris secundaris (`generate_hint` dins de prereq actiu,
verbatim `is_same_text` per a casos específics). Per pujar al 80%+
caldrien 5-8 escenaris més.

**Per reproduir**:

```bash
coverage run --source=tutor,invariants -m unittest test_session_simulator
coverage report
```

**Cost per arribar al 80%**: 2-3 hores. **Quan**: oportunista. Acceptable
per al pilot tal com està (les branques crítiques de la màquina d'estats
sí que estan cobertes).

---

## D. Notes sobre les noves suites

- `invariants.py` es pot desactivar amb `TUTOR_INVARIANTS=off`. **No
  recomanat en producció**: el cost dels invariants és microscòpic i
  detecten classes senceres de bugs.
- `test_problems_properties.py` actualment passa amb 3 forats whitelistats
  (vegeu F1 i F2 més amunt). Si afegim problemes nous, les propietats
  s'apliquen automàticament — no cal tocar res excepte si el problema nou
  expandeix un forat conegut, cas en què caldria justificar a la
  whitelist.
- `test_session_simulator.py` mocka la IA amb `unittest.mock.patch`. Cap
  test fa crides reals: cost zero, executable en CI. Si afegim una
  branca nova a `process_turn`, afegir un escenari corresponent al
  simulador.

---

**Resum quantitatiu de l'estat post-sprint:**

| Mòdul | Tests | Detecta |
|---|---|---|
| `test_verifier.py` | 71 | Bugs de parsing, equivalència, validació de forma |
| `test_problems.py` | 19 | Integritat d'esquema de la base |
| `test_problems_properties.py` | 13 | Forats estructurals (reachability, famílies, trampes) |
| `test_session_simulator.py` | 24 | Bugs a la màquina d'estats sense cost API |
| `test_api_logger.py` | 8 | Filtre per session/student |
| **Total** | **135** | **+3 findings reals documentats** |
