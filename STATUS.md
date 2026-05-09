# STATUS — seguiment del Tutor d'equacions lineals

Document viu. S'actualitza a cada bloc de feina. Última actualització: 2026-05-09 (després del Tier 2).

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
- ✅ `test_problems.py` (NOU): 19 tests d'integritat (camps obligatoris, equacions parsegen, solucions concorden amb SymPy, errors de test_cases són no-equivalents).

### Estat dels tests automatitzats
- **98/98 verds** (71 verifier + 8 api_logger + 19 problems d'integritat).
- 11 problemes a `PROBLEMS`, tots amb `TEST_CASES` validats per SymPy.
- Mai cap test fa crides reals a la IA — cost zero.

### Cobertura del catàleg d'errors (post-Tier 2)
- ✅ **Ben cobert (≥2 problemes):** L1_inverse_op, L1_sign_error, L2_order, L2_transpose_sign, L2_one_side_only, L3_distribution_partial, L3_minus_paren, L4_mcm_partial, L4_illegal_cancel, GEN_arithmetic.
- ⚠️ **Cobertura mínima (1 problema):** L3_combine_terms (únic problema amb x als dos costats), L4_minus_fraction (únic amb menys davant fracció). Reforçar aquests requereix replicar els patrons estructurals — espera al Tier 3.
- ❌ **Sense cobertura:** GEN_other (per disseny, és el fallback intern).

### Bugs corregits posteriors
- ✅ **Cost del test exhaustiu**: el delta sortia 0 perquè `app.py` summarizava contra el session_id de l'alumne mentre que el test loggejava sota un session_id propi (per aïllament). Fixat: `run_exhaustive_test` accepta ara un paràmetre `session_id` que el caller li passa, i `app.py` summarizava directament contra aquest.
- ✅ **Validació en obres reals:** test exhaustiu de EQ3-C-001 (9/9), EQ3-D-001 (13/13) i EQ4-C-001 (12/12) tots OK amb el classificador. Cap mismatch detectat.

---

## 🟡 En cua (proper torn)

### Fase 3 — Tier 3 (variants estructurals, delegables al company de departament)
1. **EQ2-C-001** — `−3x + 5 = 14` → `x = −3`. Coeficient negatiu de la x.
2. **EQ1-C-001** — `x − 4 = 9` → `x = 13`. Un pas amb resta (variant simple).
3. **EQ2-D-001** — `12 = 2(x − 1)` → `x = 7`. Activa el camp `equacio_simetria` que ara està definit però no s'usa.

### Fase 3 — validació amb IA
- **Test exhaustiu en mode debug** dels nous problemes (EQ1-B, EQ2-B, EQ3-B, EQ3-C, EQ3-D, EQ4-A, EQ4-C) per validar que la classificació de Gemini concorda amb les etiquetes esperades. **Costa diners** (crides reals a l'API). Recomanat fer-ho un cop els del Tier 3 estiguin també autorats.

---

## ⚪ Pendent (sense ordre concret)

### Fase 4 — Preparació tècnica i legal del pilot
- ✅ Pseudonimització (fet, vegeu més amunt).
- ⚪ **Document informatiu per a famílies + formulari de consentiment** (català, paper i digital).
- ⚪ **Configurar Zero Data Retention** a la consola de Gemini.
- ⚪ **Establir sostre de despesa** al projecte de Google Cloud / AI Studio.
- ⚪ **Validació formal amb la direcció del centre.**

### Categoria B — Refinaments d'UI
- ⚪ Tipografia/mides per a l'Aran (revisar amb captures concretes).
- ⚪ Espai vertical: hi ha `<hr>` redundants? Revisar.
- ⚪ Comportament del botó "Vull sortir de la sessió": ara executa `!!` directament. **Demanar confirmació?**

### Categoria C — Refinaments d'UX
- ⚪ Verificar que la caixa verda persistent post-prereq es veu bé (no eclipsada per la cadena d'equacions).
- ⚪ Sidebar en mode no-debug: confirmar que queda neta.

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
