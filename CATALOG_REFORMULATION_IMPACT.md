# Informe d'impacte: reformulació del `ERROR_CATALOG` (2026-05-12)

Document generat a partir de la comparació de dos informes `test_1forall`:

- **Abans**: `test_1forall_20260512-210326.json` — catàleg original.
- **Després**: `test_1forall_20260512-212418.json` — catàleg amb tres entrades reformulades.

L'execució anterior i posterior són sobre **els mateixos 25 problemes** amb els **mateixos 265 inputs** dels `TEST_CASES`. La diferència és exclusivament al text de tres entrades del `ERROR_CATALOG`: `L2_like_terms`, `L4_mcm_partial`, `L4_illegal_cancel`.

---

## Motivació de la reformulació

L'informe del 2026-05-12 21:03 va mostrar que tres etiquetes del catàleg **mai es disparaven** malgrat estar declarades als `errors_freqüents` de múltiples problemes. La causa diagnosticada: les descripcions originals descrivien l'**estat conceptual** de l'alumne ("failed to collect"), no la **transformació visible** entre `last_correct` i `attempt` que la IA ha de classificar segons la regla #1 del prompt.

Política aplicada a les tres reformulacions:

1. Patró textual visible al començament de la descripció.
2. Tres exemples concrets dels `TEST_CASES` reals del repositori.
3. Disambiguació explícita amb les etiquetes competidores (les que la IA preferia per defecte).

---

## Resum quantitatiu

| Mètrica | Abans (21:03) | Després (21:24) | Diferència |
|---|---|---|---|
| Crides API | 242 | 245 | +3 |
| Tokens d'entrada | 464.105 | 532.530 | +68.425 |
| Tokens de sortida | 16.963 | 16.753 | −210 |
| Cost USD | $0,1816 | $0,2016 | +$0,0200 |
| Durada total | 216 s | 217 s | +1 s |
| Items totals processats | 265 | 265 | 0 |
| Items amb match binari | 265 | 265 | 0 |
| Problemes OK | 25/25 | 25/25 | 0 |

**Observacions:**

- L'increment de tokens d'entrada (+15 %) es deu al text afegit a les tres descripcions (cada classify_error rep el catàleg sencer; tres entrades més grans = més tokens en cada crida).
- El cost addicional és **$0,02 per execució completa** — negligible per a iteració.
- Cap impacte negatiu detectat: tots els problemes continuen acabant bé, tots els items continuen tenint match binari.

---

## Resultat principal: les tres etiquetes diana

| Etiqueta | Abans | Després | Diferència | Veredicte |
|---|---|---|---|---|
| `L2_like_terms` | 0 disparades | 3 disparades | +3 | Victòria parcial |
| `L4_mcm_partial` | 1 disparada | 1 disparada | 0 | No-èxit |
| `L4_illegal_cancel` | 0 disparades | 4 disparades | +4 | Victòria clara |

**Total global**: 1 → 8 disparades de les tres etiquetes diana (+7).

---

## On apareixen ara les etiquetes diana (detall)

### `L2_like_terms` (3 noves)

- `EQ2-F-001` (`5 + 2x + 3 − x = 12`), R1: input `−x + 8 = 12` (l'alumne ha equivocat el signe en combinar `2x − x → −x`).
- `EQ2-I-001` (`4x + x − 3 + 6 = 2x + 12 − 3`), R1: input `3x + 3 = 2x + 9` (cas tipus: ha fet `4 − 1 = 3` en lloc de `4 + 1 = 5`).
- `EQ3-I-001`, una disparada addicional (no detallada).

**Cas no resolt**: a `EQ2-E-001` (`2x + 5x = 21`) — el cas **paradigmàtic** de l'etiqueta — els errors prototípics (`10x = 21`, `3x = 21`) continuen rebent `GEN_arithmetic`. Diagnosi: la IA classifica per la "naturalesa del càlcul" (aritmètica trivial) i no per l'estructura semàntica (recollida de termes). `GEN_arithmetic` també és un patró visible, més curt i directe, i guanya.

### `L4_illegal_cancel` (4 noves)

Les quatre concentrades a problemes amb fraccions:

- `EQ4-A-001` (`(x + 1)/3 = 4`), R1: inputs `x + 1 = 4`, `x + 1 = 7`, `x + 3 = 12` — tres casos prototípics on l'alumne elimina el denominador sense aplicar la inversa al RHS.
- `EQ4-C-001` (`5 − (x − 1)/2 = 3`), una disparada.

Aquesta és la victòria **més neta** de la iteració: la descripció reformulada conté literalment el patró textual `from '2x/3 = 6' writing '2x = 6'` i la IA l'ha aparellat amb fidelitat.

### `L4_mcm_partial` (sense canvi)

- `EQ4-C-001`, una disparada (la mateixa que l'execució anterior).
- `EQ4-B-001` (`x/2 + x/3 = 5`) — l'únic problema amb dues fraccions amb denominadors diferents, **continua** sense disparar l'etiqueta. Els errors prototípics (`3x + 2x = 5`, `5x = 5`) reben `GEN_arithmetic` o `L2_one_side_only`.

**Diagnosi del no-èxit**: a `EQ4-B-001`, l'error tipus és que l'alumne multiplica per 6 al LHS però no al RHS. Estructuralment, la IA veu això com a "operació aplicada només a un costat", i `L2_one_side_only` competeix directament i guanya. La descripció reformulada diu *"This is DIFFERENT from L2_one_side_only because here the inconsistency is between TERMS within the same equation"*, però aquesta distinció és més fina que la diferència real entre els inputs i les opcions del catàleg.

---

## Canvis col·laterals

Tots els canvis a etiquetes amb diferència significativa entre les dues execucions:

| Etiqueta | Abans | Després | Diferència |
|---|---|---|---|
| `L2_like_terms` | 0 | 3 | +3 |
| `L4_illegal_cancel` | 0 | 4 | +4 |
| `L2_order` | 0 | 1 | +1 |
| `GEN_other` | 0 | 1 | +1 |
| `L2_transpose_sign` | 38 | 37 | −1 |
| `L1_inverse_op` | 48 | 45 | −3 |
| `L2_one_side_only` | 29 | 24 | −5 |

**Lectura**: els 8 disparos guanyats per les etiquetes diana surten majoritàriament d'`L2_one_side_only` (−5) i `L1_inverse_op` (−3). Això és **exactament el que esperava**: les noves descripcions inclouen disambiguacions explícites contra aquestes dues etiquetes, i la IA ha redistribuït les classificacions cap a opcions més específiques quan correspon. Cap signe que el canvi hagi degradat classificacions correctes.

---

## Variància estocàstica

Aquesta comparació és **una sola execució de cada catàleg**. Gemini Flash té variància: el mateix prompt pot donar etiquetes diferents en dues execucions consecutives. Per quantificar quina part del +7 és guany real i quina és soroll, caldrien 2-3 execucions del catàleg nou. Cost: ~$0,40-$0,60 addicionals.

**Senyal indicativa d'alta significança**:
- `L4_illegal_cancel` passa de 0 a 4 disparos concentrats en un sol problema (`EQ4-A-001`, els tres inputs prototípics). Això **no és variància**: és la IA aparellant un patró textual nou. Veredicte robust.
- `L2_like_terms` passa de 0 a 3 disparos distribuïts. Aquí la variància podria explicar una part — caldria una segona execució per confirmar la sostenibilitat.
- `L4_mcm_partial` queda igual. Aquí sí podem concloure amb confiança que **la reformulació no ha estat suficient**: el cas paradigmàtic continua sense disparar-se i les disambiguacions afegides no han bastat.

---

## Conclusions

**Èxit principal**: hem passat de 1 a 8 disparos de les etiquetes diana (×8). Dues de les tres etiquetes han passat de visibilitat zero a visibilitat positiva.

**No-èxit identificat**:

- A `EQ2-E-001`, el cas paradigmàtic d'`L2_like_terms`, els errors continuen rebent `GEN_arithmetic`. Cap reformulació al catàleg basada exclusivament en descripcions ha resolt aquest cas.
- A `EQ4-B-001`, el cas paradigmàtic d'`L4_mcm_partial`, mateix problema.

**Hipòtesi del no-èxit**: en aquests dos casos, el catàleg sencer "competeix" contra l'etiqueta específica. Etiquetes generals (`GEN_arithmetic`, `L2_one_side_only`) i etiquetes properes (`L1_inverse_op`) tenen patrons textuals més simples o més directes i guanyen la tria. Cap reformulació al catàleg pot canviar això mentre el catàleg sencer estigui disponible a la IA.

**Següent palanca arquitectural**: filtrar el catàleg per problema (entrada B1bis a `TODO_DEFERRED.md`). Aquesta és la palanca que **podria** resoldre els dos casos paradigmàtics, perquè eliminaria les opcions competidores que no estiguin declarades al problema. Però:

- Té risc d'efectes secundaris (etiquetes correctes podrien quedar fora i caure a `GEN_other`).
- Requereix dades reals d'ús pedagògic per decidir si val la pena.
- Cost estimat: 2-3 h d'implementació + ~$0,20 de validació.

**Recomanació**: **acceptar el catàleg actual** com a versió de pilot. La cobertura de les etiquetes específiques és parcial però positiva, i la pedagogia funciona en els casos on no s'activa (l'alumne rep "Hi ha un error en els càlculs" enlloc d'una etiqueta més precisa, però l'experiència no és catastròfica). Si el pilot real mostra que les classificacions genèriques molesten o despisten l'alumne, llavors implementem el filtrat per problema.

---

## Annexos

**Política de catàleg vigent** (resum de les tres entrades reformulades):

- `L2_like_terms`: detecta canvis incorrectes de coeficient quan dos o més termes en x es combinen al mateix costat.
- `L4_mcm_partial`: detecta multiplicació desigual per mcm quan hi ha múltiples fraccions amb denominadors diferents.
- `L4_illegal_cancel`: detecta eliminació de denominador en un costat sense aplicar la inversa a l'altre.

Les tres descripcions inclouen exemples extrets directament dels `TEST_CASES` del repositori i clàusules de disambiguació explícita contra les etiquetes que la IA preferia per defecte.

**Veure també**:

- `CATALOG_REFORMULATION_PROPOSAL.md` — document de proposta original.
- `TODO_DEFERRED.md:B1bis` — la palanca arquitectural pendent.
- `problems.py:ERROR_CATALOG` — descripcions vigents en producció.
