# STATUS — seguiment del Tutor d'equacions lineals

Document viu. S'actualitza a cada bloc de feina. Última actualització: 2026-05-09 (UI/UX Aran, validació IA Tier 3, bug post-prereq).

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
- **98/98 verds** (71 verifier + 8 api_logger + 19 problems d'integritat).
- **14 problemes** a `PROBLEMS`, distribuïts: 3 nivell 1, 4 nivell 2, 4 nivell 3, 3 nivell 4. Tots amb `TEST_CASES` validats per SymPy.
- Mai cap test fa crides reals a la IA — cost zero.

### Cobertura del catàleg d'errors (Fase 3 tancada)
- ✅ **Ben cobert (≥2 problemes):** L1_inverse_op (5), L1_sign_error (5), L2_order (2), L2_transpose_sign (7), L2_one_side_only (9), L3_distribution_partial (2), L3_minus_paren (3), L4_mcm_partial (3), L4_illegal_cancel (2), GEN_arithmetic (2).
- ⚠️ **Cobertura mínima (1 problema):** L3_combine_terms (únic problema amb x als dos costats: EQ3-C-001), L4_minus_fraction (únic amb menys davant fracció: EQ4-C-001). Cobertura mínima per disseny estructural — replicar-ne la cobertura demanaria duplicar el patró.
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
- **Document informatiu per a famílies + formulari de consentiment** (català, paper i digital).
- **Configurar Zero Data Retention** a la consola de Gemini.
- **Establir sostre de despesa** al projecte de Google Cloud / AI Studio.
- **Validació formal amb la direcció del centre.**

### Fase 3 — validació amb IA (FETA però no exhaustiva)
- ✅ Test exhaustiu manual a la web amb mode debug, contra els 7 problemes nous: tots 100% OK. Cap mismatch que requereixi ajustar prompt.
- ⚪ (Opcional) Re-validar EQ2-C-001, EQ2-D-001, EQ1-C-001 (els 3 del Tier 3) abans del pilot. Cost ~$0.05 total. Recomanat però no urgent.

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
