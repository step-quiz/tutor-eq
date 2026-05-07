# Tutor IA — Equacions lineals (Fase 1, prototip)

Prototip mínim viable del tutor Socràtic determinista descrit a la Fase 0.
Aplicat a 2n d'ESO, 4 problemes (un per nivell), 7 prerequisits, interfície
Streamlit.

## Requisits

- Python 3.10+
- Una clau d'API d'Anthropic (https://console.anthropic.com)

## Instal·lació

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
streamlit run app.py
```

(Opcional) per canviar el model:
```bash
export CLAUDE_MODEL=claude-sonnet-4-5
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
  pot costar 5-15 cèntims de dòlar amb Sonnet.
- **Model**: per defecte `claude-sonnet-4-5`. Si Anthropic actualitza el nom,
  cal ajustar l'env var `CLAUDE_MODEL` o editar `llm.py`.
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
