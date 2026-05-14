# Tutor IA — Equacions lineals (Fase 1, prototip)

> Mètriques vives (verificades per `test_docs_match_code.py`):
> `len(PROBLEMS)` = <!-- problem-count -->25<!-- /problem-count --> · 
> `len(PREREQUISITES)` = <!-- prereq-count -->13<!-- /prereq-count -->

Prototip mínim viable del tutor Socràtic determinista descrit a la Fase 0.
Aplicat a 2n d'ESO, interfície Streamlit.

## Requisits

- Python 3.10+
- Una clau d'API de Google Gemini (https://aistudio.google.com/apikey)

## Instal·lació

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=...
streamlit run app.py
```

(Opcional) per canviar el model. Per defecte: `gemini-2.5-flash`.
```bash
export GEMINI_MODEL=gemini-2.5-pro    # més qualitat, més lent, més car
# o bé
export GEMINI_MODEL=gemini-2.5-flash-lite   # més barat
```

## Estructura

| Fitxer | Responsabilitat |
|---|---|
| `problems.py` | Base de dades: 4 problemes, 7 prerequisits, graf, catàleg d'errors |
| `verifier.py` | SymPy: parsing, equivalència, terminal, detecció de contingut matemàtic |
| `llm.py` | 4 crides a la IA + 1 auxiliar; prompts en anglès |
| `tutor.py` | Lògica nuclear: torn, escapaments, estancaments, retrocessos, rastre JSON |
| `app.py` | UI Streamlit |

## Què està implementat

Tot l'abast definit a la Fase 0:

- ✓ 4 problemes (un per nivell): EQ1-A, EQ2-A, EQ3-A, EQ4-B
- ✓ Verificació SymPy → IA en cascada (4 veredictes possibles)
- ✓ Senyals d'escapament: `?`, `!text`, `!!`
- ✓ Detecció d'estancament + oferta proactiva al 2n estancament consecutiu
- ✓ Retrocés a prerequisits amb límit de profunditat (2 nivells)
- ✓ Detecció determinista d'ús inadequat (3 avisos → suspensió)
- ✓ Rastre JSON complet amb tots els camps definits

## Què cal saber abans d'executar

- **Cost**: cada torn fa 1-2 crides a la IA. Una sessió típica de 4 problemes
  pot costar uns pocs cèntims de dòlar amb `gemini-2.5-flash`. Per a `pro`,
  multiplicar per ~4. Veure `api_logger.py` per al desglòs de preus.
- **Model**: per defecte `gemini-2.5-flash`. Si Google actualitza el nom o els
  preus, ajustar `GEMINI_MODEL` o `MODEL_PRICING_USD_PER_M` a `api_logger.py`.
- **Problemes coneguts**: el judici de progrés és l'única dimensió que depèn
  fortament de la IA. Si veus comportament estrany, mira el JSON i informa-ho
  per ajustar el prompt.

## Símbols admesos a l'input

L'alumne pot escriure de manera informal:

| Vol escriure | Pot escriure |
|---|---|
| `−` (menys) | `-` o `−` |
| `·` (multiplicació) | `*`, `·`, `×`, o concatenació (`3x`) |
| `÷` | `/` |
| `^` (potència) | `^` o `**` |

SymPy és força tolerant; quan no parseja, una crida a la IA fa el rescat.

## Mode professor

Aquesta versió és per provar el sistema un mateix. No fa pseudonimització
real, no demana consentiment, i guarda el rastre només a memòria de Streamlit
(es perd quan tanques la finestra). Per a desplegament real cal completar
les tasques recollides a la secció 11 del document de Fase 0.
