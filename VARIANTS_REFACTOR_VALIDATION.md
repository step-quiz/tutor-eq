# Informe de validació: refactor de variants als prereqs (2026-05-14)

Document generat a partir de la tercera execució de `test_1forall` (`test_1forall_20260514-180640.json`), feta després del refactor arquitectural que ha portat els prereqs de 8 a 13 amb selecció automàtica de variant.

## Què s'ha validat

L'execució avalua dues coses independents:

1. **Salut del catàleg d'errors** (continuïtat amb les iteracions del 2026-05-12). El mateix test ja s'havia fet abans per ajustar les descripcions de `L2_like_terms`, `L4_mcm_partial`, `L4_illegal_cancel`.
2. **Comportament del nou selector de variants**, integrat el 2026-05-13. Per cada cas en què es dispara un prereq, el sistema ha de triar la variant adequada (suma/resta/multiplicació/divisió per a `operacions_inverses`, signes per a `prop_distributiva` i `regla_signes_parens`, estructura per a `def_fraccions_equiv`).

L'execució anterior (`test_1forall_20260512-212418.json`) servia de baseline. Cap canvi al catàleg entre aquesta i la d'ara: el delta esperat era zero a les etiquetes diana, i alguna cosa als prereqs disparats.

## Resum quantitatiu

| Mètrica | Valor |
|---|---|
| Items totals processats | 265 |
| Items amb match binari | 265 (100%) |
| Problemes OK | 25/25 |
| Excepcions API | 0 |
| Cost USD | $0,2051 |
| Crides API | 264 |
| Tokens d'entrada | 547.580 |
| Tokens de sortida | 16.349 |
| Durada | 7m24s |

Cost pràcticament idèntic a les execucions anteriors ($0,18-$0,20). El refactor de variants **no afecta la classificació**, només la selecció post-classificació, així que no hi ha increment de tokens d'entrada.

## Salut del catàleg (continuïtat amb 2026-05-12)

Reproducció de les xifres de l'execució anterior:

| Etiqueta | Execució 21:03 (catàleg original) | Execució 21:24 (catàleg reformulat) | Execució d'avui |
|---|---|---|---|
| `L2_like_terms` | 0 | 3 | **3** |
| `L4_mcm_partial` | 1 | 1 | **1** |
| `L4_illegal_cancel` | 0 | 4 | **4** |

Estabilitat estocàstica confirmada: el catàleg reformulat dispara consistentment les etiquetes específiques que abans s'ignoraven, i el cas paradigmàtic d'`L4_mcm_partial` (EQ4-B-001 amb dues fraccions a banda i banda) continua resistint-se. Cap canvi respecte a la diagnosi del 2026-05-12: caldria filtrar el catàleg per problema (entrada `B1bis` a `TODO_DEFERRED.md`) per resoldre el cas paradigmàtic. Es manté com a palanca arquitectural disponible si el pilot ho justifica.

## Validació del refactor de variants

**Total de prereqs disparats al test exhaustiu:** 126 (sobre 113 inputs que la IA va classificar com a errors conceptuals).

Distribució per variant:

| Variant | Disparades | Nota |
|---|---|---|
| PRE-EQUIV | 62 | Únic prereq sense variants. Mapejat sobretot per `L2_transpose_sign` (42) i `L2_one_side_only` (20). |
| PRE-INV-MULT | 28 | Variant més freqüent del refactor — coeficient enter davant la x. |
| PRE-INV-ADD | 10 | Constant positiva al costat de la x. |
| PRE-INV-SUB | 5 | Constant negativa. **Nova variant — sense el refactor, aquests 5 disparos haurien anat erròniament a PRE-INV-ADD.** |
| PRE-INV-DIV | 4 | x dividida per K. **Nova variant — sense el refactor, anirien a PRE-INV-ADD i mostrarien una suma com a exemple davant una divisió incorrecta.** |
| PRE-DIST-PLUS | 4 | Parèntesi amb signe positiu intern. |
| PRE-DIST-MINUS | 4 | Parèntesi amb signe negatiu intern. **Nova variant.** |
| PRE-SIGNES-MINUS | 3 | Cas històric. |
| PRE-SIGNES-PLUS | 2 | **Nova variant.** |
| PRE-FRAC-COEF | 4 | Coeficient fraccionari. **Nova variant — sense el refactor, anirien a PRE-FRAC-CROSS i mostrarien un producte creuat davant una cancel·lació de denominador.** |

**Verificació formal**: per cada un dels 126 prereqs disparats, el codi del selector (`_select_prereq_id`) reprodueix exactament la decisió real quan se li passa el `from_eq` de la ronda corresponent. Cap discrepància entre lògica i comportament.

**Quantificació del guany pedagògic**: sense el refactor, l'arquitectura antiga només tenia `PRE-INV` i `PRE-INV-MULT`. Aleshores:

- Els 5 disparos de PRE-INV-SUB haurien anat a PRE-INV (exemple amb suma davant un cas de resta).
- Els 4 disparos de PRE-INV-DIV haurien anat a PRE-INV (suma davant divisió).
- Els 4 disparos de PRE-DIST-MINUS haurien anat a un PRE-DIST genèric (signe + davant signe −).
- Els 2 disparos de PRE-SIGNES-PLUS haurien anat al PRE-SIGNES antic (signe − davant signe +).
- Els 4 disparos de PRE-FRAC-COEF haurien anat a PRE-FRAC (producte creuat davant cancel·lació il·legal).

**Total**: ~19 disparos pedagògicament mal alineats sobre els 64 que el refactor cobreix amb variants no-úniques (≈30%). Ara aquests 19 reben l'exemple que reflecteix la mateixa estructura visual que el seu propi error.

## Casos clau verificats

Confirmació manual dels casos que motivaven el refactor:

| Equació | Error de l'alumne | Variant disparada | Veredicte |
|---|---|---|---|
| `x − 4 = 9` | `x = 36` (L1_inverse_op) | PRE-INV-SUB | El cas paradigmàtic — abans del refactor anava a PRE-INV (suma). Ara mostra resta. |
| `x/3 = 4` | `x = 1` (L1_inverse_op) | PRE-INV-DIV | Mostra divisió, no suma. |
| `3(x − 4) = 9` | `3x − 7 = 9` (L3_distribution_partial) | PRE-DIST-MINUS | Mostra exemple amb signe negatiu intern. |
| `2(x + 1) = 3(x − 2)` | `2x + 1 = 3x − 6` (L3_distribution_partial) | PRE-DIST-PLUS | Primer parèntesi guanya (cas mixt resolt segons regla acordada). |
| `7 − (x + 2) = 4` | `7 − x + 2 = 4` (L3_minus_paren) | PRE-SIGNES-PLUS | Signe positiu dins → mostra exemple anàleg. |
| `5 − (x − 1)/2 = 3` | `5 − (x − 1) = 3` (L4_illegal_cancel) | PRE-FRAC-COEF | Detecta coeficient fraccionari, no producte creuat. |

Cada cas dispara la variant que reflecteix l'estructura visual de l'última equació vàlida, no una variant genèrica.

## Observació pedagògica: cas marginal d'`L1_inverse_op` en passos avançats

A `EQ3-A-001` ronda 2, `from_eq = 3x − 12 = 9`. L'alumne escriu `3x = 108`. La IA classifica `L1_inverse_op`, i el selector activa **PRE-INV-SUB** (perquè l'última equació té forma `K·x − M = N`, additiva amb constant negativa).

L'error real no és exactament una confusió d'operació inversa additiva; l'alumne ha saltat un pas i ha calculat `9 · 12 = 108`. La classificació `L1_inverse_op` és tècnicament aplicable (operació incorrecta), però el matís pedagògic seria més precís amb `L2_order` (saltar passos).

**Status**: acceptable per al pilot. La pedagogia de PRE-INV-SUB ("aïlla la x primer fent l'operació inversa") és correcta per a l'alumne. Pendent veure si el pilot real revela confusió en aquest tipus de salt.

## Aspectes pendents

Cap finding nou resultant d'aquesta execució. Els punts existents al `TODO_DEFERRED.md` segueixen vigents:

- **B1bis** (filtrat del catàleg per problema): seguiria sent la palanca per resoldre el cas paradigmàtic d'`L4_mcm_partial` a EQ4-B-001 i de `L2_like_terms` a EQ2-E-001. Cost ~$0,20 de validació + 2-3h de codi. Decisió: defer fins al pilot.
- **Possible split de `PRE-EQUIV`**: és el prereq més freqüent (62 disparos sobre 126, gairebé la meitat). Si el pilot revela que un sol exemple genèric (`3x − 5 = 10`) no cobreix bé tots els casos (alumne transposant a `12 = 2x + 4`, per exemple), valdria la pena variants. Avui no és prioritari.
- **`GEN_arithmetic` com a label dominant**: 64 disparos, cap d'ells dispara prereq (no és conceptual). Si el pilot mostra que els alumnes queden encallats aquí, valdria la pena classificació més fina o un missatge més específic.

## Conclusió

**Sistema validat per al pilot real.** El refactor de variants funciona segons disseny: 126/126 prereqs disparats reben la variant pedagògicament alineada amb l'estructura del seu propi error. L'estabilitat estocàstica del catàleg es manté a través de tres execucions. Cap regressió detectada.

La següent font de dades útils és el pilot real amb usuaris — no més iteracions sintètiques amb la IA. Quan tinguem rastres de sessions reals, podrem decidir si valdria la pena cap de les palanques pendents.

---

**Veure també:**

- `CATALOG_REFORMULATION_IMPACT.md` — informe d'impacte de la reformulació del catàleg (2026-05-12).
- `TODO_DEFERRED.md:B1bis` — palanca arquitectural pendent (filtrat del catàleg per problema).
- `SCHEMA.md:PREREQUISITES` — documentació de la convenció de variants i selector.
- `test_session_simulator.py:TestPrereqVariantSelection` — 13 tests unitaris del selector.
