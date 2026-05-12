# STATUS — seguiment del Tutor d'equacions lineals

> Mètrica viva: `len(PROBLEMS)` = <!-- problem-count -->25<!-- /problem-count --> (verificat per `test_docs_match_code.py`).

Document viu. S'actualitza a cada bloc de feina. Última actualització: 2026-05-11 (F0 i F3 completament resolts: integració dels 11 problemes + TEST_CASES revisats pel professor. Base actual: 25 problemes, 58 rondes, 265 inputs).

---

## ✅ Completat

### Categoria A — Debug gating
- `?debug=1` URL flag implementat. Tota la infraestructura de debug (test exhaustiu, estat intern de la sessió, "senyals especials", model actiu) queda darrere d'aquest flag.

### Categoria D — Adaptació de llenguatge per a 13 anys
**Fet manualment per l'usuari** (full de càlcul → canvis directes als `.py`):
- Tots els missatges hardcoded a `tutor.py` i `app.py` revisats.
- Reformulats els 2 missatges desactualitzats que feien referència a senyals tipus `?` i `!!` en lloc dels botons.
- "Es recomana tutoria humana" → "demanar ajuda al professorat".
- "[Reconstruït]" → "Jo interpreto això".
- Etc.

### Grup 2 — Bugs i neteja del codi
- ✅ `PRE-EQUIV` duplicat eliminat de `problems.py`.
- ✅ `README.md` actualitzat a Gemini (abans deia Anthropic).
- ✅ `.gitignore` ampliat (`__pycache__/`, `.venv/`, `.DS_Store`, etc.).
- ✅ `tutor.py`: `interpret_input` que torna `error` ara grava `error_label="GEN_other"` (abans deixava el rastre buit).
- ✅ `api_logger.py`: timestamp de verificació de preus actualitzat a 2026-05.
- ✅ `test_verifier.py` (NOU): 71 tests unitaris del mòdul determinista.

### Pseudonimització (Fase 4 prep tècnica)
- ✅ `api_logger.log_call` accepta `student_id` opcional.
- ✅ `api_logger.summarize_session` filtra per `session_id` i/o `student_id`.
- ✅ `llm.py`: substituït `_SESSION_ID` per-procés per context **thread-local** (suporta multi-usuari concurrent a Streamlit).
- ✅ Funcions noves: `set_log_context()`, `get_log_context()`.
- ✅ `tutor.new_session_state`: genera `session_id` UUID per cada problema iniciat. Default de `student_id` canviat de `"professor_test"` → `"anon"`.
- ✅ `tutor.run_exhaustive_test`: aïlla el seu propi context (`__test_exhaustiu__`) per no contaminar les analítiques de l'alumne real.
- ✅ `tutor.build_trace`: inclou `session_id` al rastre JSON.
- ✅ `app.py`: input "Codi de l'alumne" al sidebar; `start_session` propaga el codi a `set_log_context`; `main()` re-aplica el context defensivament a cada rerun.
- ✅ `test_api_logger.py` (NOU): 8 tests del filtre per `student_id`.

### Fase 3 — GAPs 1-5 (11 problemes nous, IA-assistida)

Decisions preses:

- **a) `L2_like_terms` afegit ara al `ERROR_CATALOG`** (i documentat a `SCHEMA.md`). El company no ha de tocar el catàleg mentre autora — només `PROBLEMS` i `TEST_CASES`.
- **b) `SCHEMA.md` anotat amb les famílies reservades** després d'aquesta tanda. El company no pot usar EQ1-D, EQ2-E/F/H/I/X ni EQ3-E/F/G/H/I sense coordinació prèvia.

Problemes incorporats (generats per IA, revisats i acceptats sense modificació):

| ID | Equació | Nivell | GAP cobert |
|---|---|---|---|
| `EQ1-D-001` | `x/3 = 4` | 1 | 1 — coeficient fraccionari simple |
| `EQ2-X-001` | `2x/3 = 6` | 2 | 1 — coeficient fraccionari propi |
| `EQ2-E-001` | `2x + 5x = 21` | 2 | 2 — recollir termes semblants (un costat) |
| `EQ2-F-001` | `5 + 2x + 3 − x = 12` | 2 | 2 — termes semblants intercalats |
| `EQ2-H-001` | `5x − 2x + 3 − 1 = 2x + 4 + 2` | 2 | 3b — recollir ambdós costats + transposar |
| `EQ2-I-001` | `4x + x − 3 + 6 = 2x + 12 − 3` | 2 | 3b — variant amb 3 passos finals |
| `EQ3-E-001` | `4x + 1 = 2x + 7` | 3 | 4 — x als dos costats (coeficients positius) |
| `EQ3-F-001` | `7 − 2x = 3x + 2` | 3 | 4 — x als dos costats (coef. negatiu LHS) |
| `EQ3-G-001` | `−2x + 1 = x − 8` | 3 | 4 — x als dos costats (solució positiva) |
| `EQ3-H-001` | `2(x + 1) = 3(x − 2)` | 3 | 5 — parèntesis als dos costats |
| `EQ3-I-001` | `2(x + 3) − 3(x − 1) = 0` | 3 | 5 — dos parèntesis al LHS, menys davant del segon |

⚠️ **Pendent de validació**: aquests 11 problemes NO han passat encara el test exhaustiu amb la IA. Veure cua delegada més avall.

### Model de privadesa — codi de sortida (no PII)

El camp `student_id` (sidebar «Codi de l'alumne») ha de contenir un **codi de sortida pseudònim** (p.ex. `"A01"`, `"EST03"`), no el nom real, correu ni cap dada identificativa. El codi el proporciona el professorat a l'inici de la sessió; l'alumne el copia al camp. Queda registrat als logs de l'API però no permet identificar la persona sense la llista de correspondències, que es guarda fora del sistema.

Implicació per a Fase 4: el document de consentiment ha de descriure aquest mecanisme i deixar clar que el sistema no registra el nom de l'alumne.

### Fase 3 — Esquema i autoria de problemes
- ✅ `SCHEMA.md` (NOU): documentació completa de l'esquema (PROBLEMS, TEST_CASES, DEPENDENCIES, PREREQUISITES, ERROR_CATALOG), procés d'autoria, convencions de nomenclatura.
- ✅ `EQ2-B-001` (NOU): `2x + 8 = 4` → `x = −2`. Dos passos amb solució negativa.
- ✅ `EQ3-B-001` (NOU): `5 + 2(x − 3) = 7` → `x = 4`. Parèntesi amb terme al davant.
- ✅ `EQ3-C-001` (NOU): `2x + 5 = x + 8` → `x = 3`. **Tier 1 — cobreix L3_combine_terms (forat total)**.
- ✅ `EQ3-D-001` (NOU): `7 − (x + 2) = 4` → `x = 1`. **Tier 1 — cobreix L3_minus_paren genuïnament**.
- ✅ `EQ4-C-001` (NOU): `5 − (x − 1)/2 = 3` → `x = 5`. **Tier 1 — cobreix L4_minus_fraction (forat total)**.
- ✅ `EQ1-B-001` (NOU): `5x = 20` → `x = 4`. **Tier 2 — reforça L1_inverse_op multiplicatiu**.
- ✅ `EQ4-A-001` (NOU): `(x + 1)/3 = 4` → `x = 11`. **Tier 2 — reforça errors L4 amb una sola fracció**.
- ✅ `EQ1-C-001` (NOU): `x − 4 = 9` → `x = 13`. **Tier 3 — un pas amb resta (varietat)**.
- ✅ `EQ2-C-001` (NOU): `−3x + 5 = 14` → `x = −3`. **Tier 3 — coeficient negatiu**.
- ✅ `EQ2-D-001` (NOU): `12 = 2x + 4` → `x = 4`. **Tier 3 — presentació invertida (incògnita a la dreta)**.
- ✅ `test_problems.py` (NOU): 19 tests d'integritat (camps obligatoris, equacions parsegen, solucions concorden amb SymPy, errors de test_cases són no-equivalents).

### Estat dels tests automatitzats
- **98/98 verds** (71 verifier + 8 api_logger + 19 problems d'integritat). ⚠️ Els 11 problemes nous (GAPs 1-5) no han passat `test_problems.py` encara — veure cua delegada.
- **25 problemes** a `PROBLEMS`, distribuïts: 4 nivell 1, 9 nivell 2, 9 nivell 3, 3 nivell 4. Els 14 originals amb `TEST_CASES` validats per SymPy; els 11 nous pendents de validació.
- Mai cap test fa crides reals a la IA — cost zero.

### Cobertura del catàleg d'errors (Fase 3 + GAPs 1-5)
- ✅ **Ben cobert (≥2 problemes):** L1_inverse_op (5+), L1_sign_error (5+), L2_order (2+), L2_transpose_sign (7+), L2_one_side_only (9+), L2_like_terms (4 — NOU, GAPs 2-5), L3_distribution_partial (2+), L3_minus_paren (3+), L3_combine_terms (5+ — el forat de Fase 3 ara cobert per GAPs 3b/4/5), L4_mcm_partial (3), L4_illegal_cancel (2+), GEN_arithmetic (2+).
- ⚠️ **Cobertura mínima (1 problema):** L4_minus_fraction (únic amb menys davant fracció: EQ4-C-001). Cobertura mínima per disseny estructural.
- ❌ **Sense cobertura:** GEN_other (per disseny, és el fallback intern del classificador).

### Bugs corregits posteriors
- ✅ **Cost del test exhaustiu**: el delta sortia 0 perquè `app.py` summarizava contra el session_id de l'alumne mentre que el test loggejava sota un session_id propi (per aïllament). Fixat: `run_exhaustive_test` accepta ara un paràmetre `session_id` que el caller li passa, i `app.py` summarizava directament contra aquest.

### Validació amb el classificador IA (test exhaustiu)
- ✅ **EQ3-C-001** (`2x + 5 = x + 8`): 9/9 OK
- ✅ **EQ3-D-001** (`7 − (x + 2) = 4`): 13/13 OK
- ✅ **EQ4-C-001** (`5 − (x − 1)/2 = 3`): 12/12 OK
- ✅ **EQ1-B-001** (`5x = 20`): 100% OK
- ✅ **EQ2-B-001** (`2x + 8 = 4`): 100% OK
- ✅ **EQ3-B-001** (`5 + 2(x − 3) = 7`): 100% OK
- ✅ **EQ4-A-001** (`(x + 1)/3 = 4`): 100% OK
- ✅ **EQ1-C-001** (`x − 4 = 9`): 100% OK
- ✅ **EQ2-C-001** (`−3x + 5 = 14`): 100% OK
- ✅ **EQ2-D-001** (`12 = 2x + 4`): 100% OK
- **Conclusió:** els 10 problemes nous (Tier 1+2+3) validats amb la IA, tots 100%. El classificador entén tots els errors del catàleg amb les etiquetes esperades. **Cap mismatch que requereixi ajustar el prompt de `classify_error` abans del pilot.**

### Categoria B / C — refinaments d'UI/UX (consolidats)
- ✅ Espai vertical: revisat, sense `<hr>` redundants.
- ✅ Sidebar en mode no-debug: net.
- ✅ Botó "Vull sortir de la sessió": ara demana confirmació (Acceptar / Cancel·lar) per evitar tancaments accidentals.
- ✅ Tipografia del panell principal augmentada un 20% per a millor lectura per a l'Aran (sidebar no afectat).
- ✅ Estil del botó Enviar: gris clar per defecte, gris fosc al hover amb border més marcat (substitueix el vermell primary que era visualment massa agressiu).
- ✅ **Bug fix: caixa verda post-prereq ara és persistent.** Abans, els missatges de tancament de prereq (`prereq_resolved`/`prereq_failed`) desapareixien al següent torn perquè `process_turn` netejava `state["messages"]` íntegrament. Solució: flag `persistent` a `_push_msg` que excepciona aquests missatges del reset.

---

## 🟡 En cua (proper torn)

### Fase 4 — bloqueigs externs (no codi)
- **Document informatiu per a famílies + formulari de consentiment** (català, paper i digital). Ha d'incloure la descripció del model de privadesa basat en codi de sortida.
- **Configurar Zero Data Retention** a la consola de Gemini.
- **Establir sostre de despesa** al projecte de Google Cloud / AI Studio.
- **Validació formal amb la direcció del centre.**

### Fase 3 — validació amb IA (FETA però no exhaustiva)
- ✅ Test exhaustiu manual a la web amb mode debug, contra els 7 problemes nous (Tier 1-3): tots 100% OK. Cap mismatch que requereixi ajustar prompt.
- ⚪ (Opcional) Re-validar EQ2-C-001, EQ2-D-001, EQ1-C-001 (els 3 del Tier 3) abans del pilot. Cost ~$0.05 total. Recomanat però no urgent.

### Cua delegada (tasques per al company)

El company pot fer les tasques següents de forma independent. **Restriccions prèvies ja resoltes** (no cal que les gestioni):
- `L2_like_terms` ja és al catàleg — no cal tocar `ERROR_CATALOG`.
- Les famílies reservades estan anotades a `SCHEMA.md` — no inventar IDs conflictius.

**Tasques:**

1. **Validar els 11 nous problemes amb el test exhaustiu** (mode `?debug=1` → botó «Test exhaustiu»). Un per un. Esperats: 100% OK per a tots. Si hi ha mismatch, anotar el problema i l'input fallit aquí.
2. **`test_problems.py`**: executar-lo i confirmar que els 11 nous passen (integritat de camps, SymPy concorda amb `solucio`, errors de `TEST_CASES` no-equivalents). Esperats: tots verds.
3. **(Opcional)** Afegir un segon enunciat (`-002`) a qualsevol de les famílies noves que es vulgui reforçar. Seguir el procés d'autoria de `SCHEMA.md`. No cal coordinació si la família ja existeix.
4. **(Opcional)** Re-validar EQ2-C-001, EQ2-D-001, EQ1-C-001 (Tier 3 antic). Cost ~$0.05.

---

## ⚪ Pendent (sense ordre concret)

### Fase 3 — Tier 4 (post-pilot, opcional)
- ⚪ Equació identitat (`2(x + 3) = 2x + 6`).
- ⚪ Equació sense solució (`x + 3 = x + 5`).
- ⚪ Solucions fraccionàries (`4x = 6` → `x = 3/2`).

### Fase 5 — Pilot
- ⚪ Sessions reals amb l'Aran.
- ⚪ Anàlisi del log per alumne (ara filtrable per `student_id`).
- ⚪ Iteració de prompts segons evidència.
- ⚪ Eventual ampliació a un grup.

---

## Convencions del projecte (recordatori)

- **SymPy és la font de veritat** per a la correcció matemàtica.
- **El català és la llengua de l'alumne**; els prompts a la IA són en anglès però produeixen sortida en català.
- **To sobri, no infantilitzat**, no gamificat.
- **Cap test cremant diners**: tots els tests automàtics són deterministes. La validació amb la IA es fa només via "Test exhaustiu" en mode debug, manualment, i només quan cal.
- **Cada nou problema ha de passar `test_problems.py`** abans de considerar-lo afegit.
