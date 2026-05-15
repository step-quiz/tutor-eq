"""
Tutor d'equacions lineals — UI Streamlit.

Per executar:
    export GEMINI_API_KEY=...
    streamlit run app.py

L'estat de la sessió viu a st.session_state. La lògica viu a tutor.py.

Mode debug:
    Tot el material orientat al desenvolupador/professor (panel d'estat
    intern, botó "Test exhaustiu", panel de cost, rastre JSON, etc.) està
    amagat per defecte. Per veure-ho, afegeix `?debug=1` a la URL.
    Exemple: http://localhost:8501/?debug=1
"""

import os
import re
import html
import json
import uuid
import random
import string
from datetime import datetime
import streamlit as st

import problems as PB
import tutor as T
import llm as L
import api_logger


def _is_debug_mode() -> bool:
    """
    Mode debug actiu si la URL conté ?debug=1. Es persisteix a
    session_state perquè un cop activat sobreviu a futurs reruns sense
    haver de mantenir el query param.
    """
    if "debug_mode" not in st.session_state:
        try:
            qp = st.query_params.get("debug")
        except Exception:
            qp = None
        st.session_state.debug_mode = (qp == "1")
    return st.session_state.debug_mode


def _show_fractions() -> bool:
    """
    Mostra les equacions de nivell 4 (fraccions) si la URL conté ?fraction=1.
    Per defecte ocult: no volem saturar els alumnes a l'inici del pilot.
    Es persisteix a session_state igual que debug_mode.
    """
    if "show_fractions" not in st.session_state:
        try:
            qp = st.query_params.get("fraction")
        except Exception:
            qp = None
        st.session_state.show_fractions = (qp == "1")
    return st.session_state.show_fractions


st.set_page_config(
    page_title="Tutor IA — equacions lineals",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS per reduir espai entre l'enunciat i la cadena de la sessió,
# ajustar marges, i marcar errors en vermell burdeus.
st.markdown(
    """
    <style>
      hr { margin: 0.6rem 0 !important; }
      .block-container h3 { margin-top: 0.3rem !important; }
      .block-container { padding-top: 2rem !important; }

      /* Equacions amb error: text en vermell burdeus i fons subtil */
      .eq-error code {
          background-color: #fbe9eb !important;
          color: #8a1c2b !important;
          border: 1px solid #e6b8be;
          font-weight: 500;
      }
      .eq-error .err-label {
          color: #8a1c2b;
          font-weight: 500;
      }
      /* Equacions estancades (correcte però sense progrés): gris neutre */
      .eq-stagnant code {
          background-color: #f0f0f0 !important;
          color: #666666 !important;
          border: 1px solid #d0d0d0;
      }
      /* Tamany de font de les equacions de la cadena (+20%) */
      .eq-chain-step code, .eq-chain-original code {
          font-size: 1.2em !important;
      }
      .eq-frac {
          display: inline-flex;
          flex-direction: column;
          align-items: center;
          vertical-align: middle;
          font-size: 0.82em;
          line-height: 1.15;
          margin: 0 1px;
      }
      .eq-frac-num {
          border-bottom: 1.5px solid currentColor;
          padding: 0 3px 1px;
          text-align: center;
      }
      .eq-frac-den {
          padding: 1px 3px 0;
          text-align: center;
      }
      /* Fraccions al capçalera (forma canònica) */
      .eq-forma {
          font-family: monospace;
          font-size: 0.9em;
          color: #2e7d32;
          display: inline-block;
          vertical-align: middle;
      }
      .eq-forma .eq-frac-num { border-bottom-color: #2e7d32; }
      /* Fraccions al sidebar (millor equació fins ara) */
      .eq-sidebar-best .eq-frac { font-size: 0.82em; }
      /* Equació vàlida al sidebar: +20% i contorn negre */
      .eq-sidebar-best {
          font-size: 1.2em !important;
          font-weight: 700 !important;
          border: 2px solid #000000 !important;
          border-radius: 4px !important;
          padding: 6px 10px !important;
          display: inline-block;
          font-family: monospace;
      }
      /* Limitar amplada del bloc central perquè no s'estiri massa
         en el layout wide quan no hi ha prerequisit actiu */
      .main-narrow { max-width: 720px; }

      /* Amaga el petit ajut "Press Enter to submit form" que Streamlit
         posa sota els text_input dins de forms. Aran no necessita
         aquesta indicació tècnica — el botó Enviar i el comportament
         d'Enter ja són evidents. */
      [data-testid="InputInstructions"] { display: none !important; }
      /* Botons amb intent pedagògic explícit per a Aran. Els targetem
         per la classe st-key-{key} que Streamlit afegeix automàticament
         al div wrapper del botó. Així evitem servir type="primary"
         (que afectaria també el botó Enviar i altres). */
      .st-key-hint_btn button {
          background-color: #f59e0b !important;   /* taronja càlid */
          color: #ffffff !important;
          border: 1px solid #d97706 !important;
      }
      .st-key-hint_btn button:hover {
          background-color: #d97706 !important;
          border-color: #b45309 !important;
      }
      .st-key-exit_btn button {
          background-color: #4a4a4a !important;   /* gris fosc neutre */
          color: #ffffff !important;
          border: 1px solid #2d2d2d !important;
      }
      .st-key-exit_btn button:hover {
          background-color: #2d2d2d !important;
          border-color: #1a1a1a !important;
      }

      /* Augment del 20% del text al panell principal per millor
         lectura per a l'Aran. El sidebar (que usa altres contenidors)
         no es veu afectat. */
      .block-container {
          font-size: 1.2rem;
      }

      /* Botó Enviar (form_submit_button): manté mida normal i estrena
         look gris clar, amb hover a gris fosc i border més marcat. */
      .block-container [data-testid="stFormSubmitButton"] button {
          background-color: #f0f0f0 !important;
          color: #333333 !important;
          border: 2px solid #c0c0c0 !important;
          font-size: 1rem !important;
      }
      .block-container [data-testid="stFormSubmitButton"] button:hover {
          background-color: #555555 !important;
          color: #ffffff !important;
          border: 2px solid #1a1a1a !important;
      }

      /* ─────────────────────────────────────────────────────────────
       * Sidebar sempre obert (decisió pilot 2n d'ESO, 2026-05-14).
       *
       * Amaguem les fletxes natives `<<` del header del sidebar, així
       * l'alumne no pot col·lapsar-lo i evitem el bug recurrent que el
       * control de "tornar a obrir" no apareix sempre al DOM de
       * Streamlit. El sidebar conté info útil per a la sessió (selector
       * d'equació, equació vàlida fins ara) que val la pena tenir
       * sempre visible. El panell principal viu amb max-width:720px
       * (.main-narrow), per tant l'amplada del sidebar no és un coll
       * d'ampolla per al contingut central.
       * ───────────────────────────────────────────────────────────── */
      [data-testid="stSidebarCollapseButton"],
      [data-testid="stSidebarCollapsedControl"],
      [data-testid="collapsedControl"] {
          display: none !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# Amaga elements de chrome de Streamlit (menú de tres punts amb tema /
# print / record screen / "Made with Streamlit") quan no estem en
# mode debug. L'alumne no els necessita i només són distraccions.
if not _is_debug_mode():
    st.markdown(
        """
        <style>
          [data-testid="stMainMenu"] { display: none !important; }
          [data-testid="stToolbar"]  { display: none !important; }
          [data-testid="stHeader"]   { display: none !important; }
          footer                     { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# Injecció de JS per desactivar les suggerències del navegador i del teclat
# del mòbil als camps de text. Els atributs `autocorrect`, `autocapitalize`
# i `spellcheck` no es poden passar a `st.text_input`, per això els fixem
# directament al DOM amb un MutationObserver. A més, randomitzem el `name`
# de cada input perquè els navegadors no associïn entrades antigues amb
# el camp actual (és el principal motiu pel qual s'arribaven a veure
# valors com "x=5", "3x-12=9", etc. al teclat del mòbil).
import streamlit.components.v1 as _components

_components.html(
    """
    <script>
    (function() {
        const targetDoc = window.parent.document;
        function suppressSuggestions() {
            const inputs = targetDoc.querySelectorAll(
                'input[type="text"], textarea'
            );
            inputs.forEach((input) => {
                if (input.dataset.noSuggest === '1') return;
                input.setAttribute('autocomplete', 'off');
                input.setAttribute('autocorrect', 'off');
                input.setAttribute('autocapitalize', 'off');
                input.setAttribute('spellcheck', 'false');
                // Nom aleatori: derrota la coincidència per historial.
                input.setAttribute(
                    'name',
                    'in_' + Math.random().toString(36).slice(2)
                );
                input.dataset.noSuggest = '1';
            });
        }
        suppressSuggestions();
        const obs = new MutationObserver(suppressSuggestions);
        obs.observe(targetDoc.body, { childList: true, subtree: true });
    })();
    </script>
    """,
    height=0,
)




# ------------------------------------------------------------
# CODI DE SESSIÓ v1 — format: Lsss-DDMM-HHMM-TQ-FC-NNN-RTPV
# ------------------------------------------------------------
#
#  L     1   Lletra de control antifrau (algorisme DNI, taula TRWAGMYFPDXBNJZSQVHLCKE)
#  sss   3   Salt aleatori (3 lletres minúscules)
#  DDMM  4   Data (dia i mes)
#  HHMM  4   Hora i minuts
#  TQ    2   Codi d'exercici fix: Tutor d'eQuacions
#  FC    2   Família del problema: nivell (1-4) + lletra (A-D), ex. "2C"
#  NNN   3   Nota × 10 arrodonida (000–100)
#  R     1   Resultat: R=resolt, A=abandonat, S=suspès
#  T     1   Torns (passos donats): 0-9, A-F (10-15), G (≥16)
#  P     1   Pistes demanades (0–9, màx 9)
#  V     1   Estancaments totals (0–9, màx 9)
#
#  CHECKSUM:
#    suma   = NNN_int + DD + MM + HH + mm + ASCII(salt[0])
#    lletra = "TRWAGMYFPDXBNJZSQVHLCKE"[ suma % 23 ]
#
#  NOTA (0–100):
#    Resolt sense pistes, ≤5 torns → 100
#    Resolt                        → max(40, 100 - pistes×12 - max(0, torns-5)×3)
#    Abandonat                     → 20
#    Suspès per ús inadequat       → 5
# ------------------------------------------------------------

_CTRL_LETTERS = 'TRWAGMYFPDXBNJZSQVHLCKE'
_HEX_TURNS    = '0123456789ABCDEFG'  # G = 16+ torns


def _calcula_nota_sessio(s: dict) -> int:
    """Retorna la nota com a enter 0-100 (NNN en el codi)."""
    verdict = s.get("verdict_final")
    torns   = max(0, len(s.get("history", [])) - 1)   # passos donats (ex. l'inicial)
    pistes  = len(s.get("hints_requested", []))
    if verdict == "resolt":
        nota = 100 - pistes * 12 - max(0, torns - 5) * 3
        return max(40, min(100, nota))
    elif verdict == "abandonat":
        return 20
    else:  # suspes_us_inadequat o desconegut
        return 5


def _generate_codi_sessio(s: dict) -> str:
    """
    Genera el codi de sessió de 30 caràcters per al tutor d'equacions.
    Retorna la cadena o '' si les dades de la sessió no són suficients.
    """
    if not s or s.get("verdict_final") is None:
        return ""

    # Salt aleatori
    salt = ''.join(random.choices(string.ascii_lowercase, k=3))

    # Data i hora actuals (moment de generació del codi)
    ara    = datetime.now()
    dia    = ara.strftime("%d")
    mes    = ara.strftime("%m")
    hora   = ara.strftime("%H")
    minuts = ara.strftime("%M")

    # Família del problema → FC (2 chars). Ex: "EQ2-C-001" → familia "EQ2-C" → "2C"
    familia = s.get("problem", {}).get("familia", "??")   # p. ex. "EQ2-C"
    if familia and len(familia) >= 4 and familia[2].isdigit():
        fc = familia[2] + familia[4]   # "EQ2-C" → '2' + 'C' = "2C"
    else:
        fc = "??"

    # Nota
    nota_int = _calcula_nota_sessio(s)
    nota_str = str(nota_int).zfill(3)

    # Resultat
    v = s.get("verdict_final", "")
    r_char = {"resolt": "R", "abandonat": "A", "suspes_us_inadequat": "S"}.get(v, "?")

    # Torns (en hex ampliat fins a G)
    torns = max(0, len(s.get("history", [])) - 1)
    t_char = _HEX_TURNS[min(torns, 16)]

    # Pistes (màx 9)
    pistes = min(len(s.get("hints_requested", [])), 9)

    # Estancaments (màx 9)
    stagnation = min(s.get("stagnation_total", 0), 9)

    # Checksum (idèntic a game-core.js)
    ascii_salt  = ord(salt[0])
    suma_ctrl   = nota_int + int(dia) + int(mes) + int(hora) + int(minuts) + ascii_salt
    lletra      = _CTRL_LETTERS[suma_ctrl % 23]

    codi = (
        f"{lletra}{salt}-{dia}{mes}-{hora}{minuts}"
        f"-TQ-{fc}-{nota_str}"
        f"-{r_char}{t_char}{pistes}{stagnation}"
    )
    return codi


def _render_codi_sessio(s: dict):
    """
    Mostra el codi de sessió amb botó de còpia.
    S'ha de cridar quan verdict_final no és None.
    """
    codi = _generate_codi_sessio(s)
    if not codi:
        return

    st.markdown("**Codi de la sessió**")
    st.caption(
        "Copia aquest codi i enganxa'l al formulari que rebràs a la classe."
    )

    # Mostrem el codi en monospace i afegim un botó de còpia via JS.
    # Usem un component HTML perquè Streamlit no té botó de còpia natiu.
    import streamlit.components.v1 as _cv1
    _cv1.html(
        f"""
        <div style="display:flex;align-items:center;gap:12px;
                    font-family:monospace;font-size:1.05rem;
                    background:#f1f5f9;border:1.5px solid #cbd5e1;
                    border-radius:8px;padding:12px 16px;
                    max-width:560px;">
          <span id="codi-text" style="flex:1;letter-spacing:0.5px;
                color:#1e293b;user-select:all;-webkit-user-select:all;">
            {codi}
          </span>
          <button id="btn-copia"
            onclick="(function(){{
              navigator.clipboard.writeText('{codi}').then(function(){{
                var b=document.getElementById('btn-copia');
                b.innerText='Copiat ✅';
                b.style.backgroundColor='#22c55e';
                setTimeout(function(){{b.innerText='📋 Copia';b.style.backgroundColor='#334155';}},3000);
              }});
            }})()"
            style="background:#334155;color:white;border:none;
                   border-radius:6px;padding:6px 14px;cursor:pointer;
                   font-size:0.9rem;white-space:nowrap;">
            📋 Copia
          </button>
        </div>
        """,
        height=70,
    )

    if _is_debug_mode():
        st.caption(f"Codi brut: `{codi}` ({len(codi)} chars)")


# ------------------------------------------------------------
# Inicialització
# ------------------------------------------------------------
def init_state():
    if "session" not in st.session_state:
        st.session_state.session = None
    if "input_counter" not in st.session_state:
        st.session_state.input_counter = 0
    if "retry_messages" not in st.session_state:
        st.session_state.retry_messages = []
    if "test_results" not in st.session_state:
        st.session_state.test_results = None
    if "test_problem_id" not in st.session_state:
        st.session_state.test_problem_id = None
    if "confirm_exit" not in st.session_state:
        st.session_state.confirm_exit = False
    if "equation_changes" not in st.session_state:
        st.session_state.equation_changes = 0   # canvis d'equació amb sessió activa
    if "confirm_change_eq" not in st.session_state:
        st.session_state.confirm_change_eq = None  # id del problema pendent de confirmar
    if "prereq_resolved_history_len" not in st.session_state:
        st.session_state.prereq_resolved_history_len = None


def start_session(problem_id: str):
    st.session_state.session = T.new_session_state(problem_id)
    # Propagar el context al thread perquè totes les crides a la IA
    # d'aquest problema quedin etiquetades amb la sessió.
    L.set_log_context(
        session_id=st.session_state.session["session_id"],
    )
    st.session_state.input_counter += 1
    # Si l'alumne havia clicat "Vull sortir" sense confirmar a la sessió
    # anterior i ara comença un problema nou, neteja la flag perquè
    # el botó torni al seu estat inicial.
    st.session_state.confirm_exit = False
    # Reseteja el marcador del prereq resolt per a la nova sessió.
    st.session_state.prereq_resolved_history_len = None
    # Si canviem de problema, els resultats del test anterior ja no
    # corresponen — els netegem.
    if st.session_state.test_problem_id != problem_id:
        st.session_state.test_results = None
        st.session_state.test_problem_id = None


# Callback per a la UI: rep avisos de l'API durant els retries
def _on_api_retry(message: str):
    st.session_state.retry_messages.append(message)


L.set_progress_callback(_on_api_retry)


# ------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------
def _frac_html(text: str) -> str:
    """Converteix expressions a/b del text d'equació a HTML de fracció visual.

    Exemples:
        "x/2 + x/3 = 5"      → HTML amb x sobre 2 i x sobre 3
        "(x + 1)/3 = 4"      → HTML amb (x + 1) sobre 3
        "5 − (x − 1)/2 = 3"  → HTML amb (x − 1) sobre 2

    Aplicat tant a l'enunciat (forma canònica del problema) com als passos
    de l'alumne a l'historial. Inputs sense fraccions són retornats com a
    HTML amb caràcters especials (`<`, `>`, `&`) escapats — `verifier`
    rebutja inputs amb aquests caràcters, però `_frac_html` és la barrera
    visual i no pot assumir que ho són sempre.

    Defensa en profunditat: tot text que arribi aquí passa per `html.escape`
    abans de ser inserit a la cadena HTML, perquè un futur canvi al
    pipeline (per exemple, mostrar inputs malformats abans de validar)
    podria saltar-se les validacions de `verifier`.
    """
    # Captura: (expr_parèntesi | terme_simple) / denominador
    # − Unicode (U+2212) i - ASCII tots dos com a signe de numerador
    _FRAC_RE = re.compile(
        r'(\([^)]+\)|[−\-]?(?:[0-9]*[a-zA-Z]+|[0-9]+))\s*/\s*([a-zA-Z0-9]+)'
    )

    # Escapem primer els caràcters HTML especials del text complet. Això
    # converteix per exemple `<` en `&lt;`. El regex segueix funcionant
    # perquè només cerca `/`, dígits, lletres, parèntesis i signes menys.
    safe_text = html.escape(text)

    def _replace(m: re.Match) -> str:
        num = m.group(1)
        den = m.group(2)
        # Treu parèntesis exteriors del numerador si n'hi ha
        if num.startswith('(') and num.endswith(')'):
            num = num[1:-1]
        return (
            f"<span class='eq-frac'>"
            f"<span class='eq-frac-num'>{num}</span>"
            f"<span class='eq-frac-den'>{den}</span>"
            f"</span>"
        )

    return _FRAC_RE.sub(_replace, safe_text)


def _render_fraction_safe(text: str) -> str:
    """Renderitza fraccions textuals dins de text que pot contenir HTML
    legítim (com spans de color escrits pel mateix autor del prereq).

    Diferència amb `_frac_html`:
      - `_frac_html` escapa tot el text amb `html.escape` (per protegir
        contra HTML hostil dels alumnes). Bona política per a inputs no
        controlats.
      - `_render_fraction_safe` NO escapa res. S'usa només amb text
        produït pels autors del catàleg (a `problems.py:PREREQUISITES`),
        que és contingut confiable. Permet barrejar fraccions
        autorenderitzades (`x/3` → barra horitzontal) amb spans HTML
        explícits (`<span style="color:#1a6fc4;font-weight:700">+5</span>`).

    Si el contingut del prereq evolucionés mai cap a inputs no
    controlats, caldria filtrar amb una whitelist d'etiquetes
    permeses, no canviar aquest helper.
    """
    # Captura: (expr_parèntesi | terme_simple) / denominador
    # Atenció: cal evitar que el regex matchi dins d'un atribut HTML
    # (per exemple `style="font-family:'Courier New'"`). Una heurística
    # senzilla: el numerador no pot contenir cometes ni signe `<`.
    # El regex actual ja exclou aquests caràcters per construcció (només
    # accepta `[0-9a-zA-Z]` o `(...)` sense `<` ni `"`), per tant no cal
    # més protecció.
    _FRAC_RE = re.compile(
        r'(\([^)]+\)|[−\-]?(?:[0-9]*[a-zA-Z]+|[0-9]+))\s*/\s*([a-zA-Z0-9]+)'
    )

    def _replace(m: re.Match) -> str:
        num = m.group(1)
        den = m.group(2)
        if num.startswith('(') and num.endswith(')'):
            num = num[1:-1]
        return (
            f"<span class='eq-frac'>"
            f"<span class='eq-frac-num'>{num}</span>"
            f"<span class='eq-frac-den'>{den}</span>"
            f"</span>"
        )

    return _FRAC_RE.sub(_replace, text)


# ───── Caixes visuals per als prereqs (resolved / failed) ─────
# Paletes de color: verd (resolt) per a `kind="resolved"`, groc/taronja
# (warning) per a `kind="failed"`. La paleta groga és compatible amb
# l'estil de `st.warning` però amb una mica més d'intensitat als marges
# perquè la caixa "interna" (passos monospace) es distingeixi del fons.
_PREREQ_BOX_PALETTES = {
    "resolved": {
        "bg": "#d1e7dd", "border": "#a3cfbb", "fg": "#0a3622",
    },
    "failed": {
        "bg": "#fff3cd", "border": "#ffe69c", "fg": "#664d03",
    },
}


def _render_prereq_visual_box(extra: dict, kind: str, header: str) -> str:
    """Construeix l'HTML d'una caixa visual estructurada per a prereqs.

    Usada tant per al cas "prereq resolt" (verd) com per al cas
    "prereq fallat" (groc). El contingut és simètric: ambdós casos
    mostren `initial_equation`, `explanation_steps` (amb alineació
    `=` central via grid quan els elements són `[lhs, rhs]`),
    `explanation_summary`, i un CTA. La diferència és la capçalera
    i el color.

    Mostrar la solució correcta també en cas de fracàs és intencionat:
    l'alumne ha de poder veure el procediment correcte per aprendre de
    l'error, encara que ara hagi de tornar a intentar el problema
    original.

    Arguments:
        extra: dict amb claus `initial_equation`, `steps`, `summary`,
               `cta`. Vegeu SCHEMA.md per al format.
        kind: "resolved" o "failed". Determina la paleta de colors.
        header: text de capçalera (per exemple "✓ Correcte." o
                "✗ La resposta no era correcta.").
    """
    initial_eq = extra["initial_equation"]
    steps = extra["steps"]
    summary = extra.get("summary", "")
    cta = extra.get("cta", "Ara, torna a resoldre l'equació original.")

    # `_render_fraction_safe` converteix fraccions textuals (`x/3`) en
    # HTML visual sense escapar spans HTML legítims que l'autor del
    # prereq ja ha escrit.
    initial_eq_html = _render_fraction_safe(initial_eq)

    # Cada element de `steps` pot ser:
    #   - str: línia lliure (cas PRE-MCM, PRE-NEG, primera línia).
    #   - [lhs, rhs]: equació amb `=` central; les dues bandes
    #     s'alineen automàticament a una columna fixa via CSS grid
    #     (equivalent al `&=` de LaTeX).
    #
    # Per garantir que els `=` quedin a la mateixa columna entre línies,
    # totes les línies en format [lhs, rhs] CONTÍGUES comparteixen un
    # MATEIX contenidor grid. Si una línia lliure trenca la seqüència,
    # el grid es tanca i se'n comença un de nou per a les pairs següents.
    html_parts = []
    current_pairs = []  # buffer de (lhs_html, rhs_html)

    def _flush_pairs():
        if not current_pairs:
            return ""
        cells = []
        for lhs_html, rhs_html in current_pairs:
            cells.append(f'<div style="white-space:pre">{lhs_html}</div>')
            cells.append('<div>=</div>')
            cells.append(f'<div style="white-space:pre">{rhs_html}</div>')
        out = (
            '<div style="display:grid;'
            'grid-template-columns:max-content max-content 1fr;'
            'column-gap:0.4rem;row-gap:0;line-height:1.7;'
            'font-family:\'Courier New\',Courier,monospace;">'
            + "".join(cells)
            + '</div>'
        )
        current_pairs.clear()
        return out

    for s in steps:
        if isinstance(s, (list, tuple)) and len(s) == 2:
            lhs = _render_fraction_safe(s[0])
            rhs = _render_fraction_safe(s[1])
            current_pairs.append((lhs, rhs))
        else:
            html_parts.append(_flush_pairs())
            txt = _render_fraction_safe(s)
            html_parts.append(
                '<div style="white-space:pre;'
                'font-family:\'Courier New\',Courier,monospace;'
                f'line-height:1.7">{txt}</div>'
            )
    html_parts.append(_flush_pairs())
    steps_lines = "".join(html_parts)

    palette = _PREREQ_BOX_PALETTES[kind]
    return f"""
<div style="background-color:{palette['bg']};border:1px solid {palette['border']};
            border-radius:0.375rem;padding:0.85rem 1.1rem;color:{palette['fg']};
            margin-top:0.25rem;">
  <div style="font-weight:600;margin-bottom:0.55rem;">{header}</div>
  <div style="font-family:'Courier New',Courier,monospace;
              background:rgba(0,0,0,0.06);border-radius:0.25rem;
              padding:0.45rem 0.7rem;margin-bottom:0.55rem;">
    <div style="white-space:pre;line-height:1.7">{initial_eq_html}</div>
{steps_lines}
  </div>
  <div style="margin-bottom:0.55rem;">{summary}</div>
  <div style="font-weight:700;">{cta}</div>
</div>"""


def render_sidebar():
    debug = _is_debug_mode()
    with st.sidebar:
        # Títol i model actiu (im1) — només per al desenvolupador.
        if debug:
            st.markdown("### Tutor IA — equacions lineals")
            st.caption("Pilot 2n d'ESO — mode professor")

        if not os.environ.get("GEMINI_API_KEY"):
            st.error("Falta GEMINI_API_KEY.")
            st.stop()

        # Info del model actiu (im1) — debug-only.
        if debug:
            st.caption(f"Model actiu: `{L.MODEL}`")

        st.markdown("---")

        # Equació vàlida fins ara — persistent al sidebar, no desapareix amb el scroll.
        s = st.session_state.session
        if s is not None and s.get("verdict_final") is None:
            best = state_so_far(s["history"])
            if best and best != s["problem"].get("equacio_text", ""):
                st.markdown("**📌 Equació vàlida:**")
                st.markdown(
                    f"<div class='eq-sidebar-best'>{_frac_html(best)}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown("---")

                # Scroll automàtic del sidebar cap amunt perquè l'alumne
                # vegi l'equació vàlida sense haver de fer scroll manual.
                import streamlit.components.v1 as _cv1_scroll
                _cv1_scroll.html(
                    """
                    <script>
                    (function() {
                        var sidebar = window.parent.document.querySelector(
                            '[data-testid="stSidebar"] > div'
                        );
                        if (sidebar) sidebar.scrollTop = 0;
                    })();
                    </script>
                    """,
                    height=0,
                )

        st.markdown("**Selecciona l'equació**")

        # CSS dinàmic: ressalta en blau el botó del problema actiu.
        # Streamlit afegeix automàticament la classe st-key-btn_{id} al div
        # wrapper de cada botó, cosa que ens permet targetar-lo sense JS.
        active_id = (st.session_state.session or {}).get("problem_id") or                     (st.session_state.session or {}).get("problem", {}).get("id")
        if active_id:
            safe_id = active_id.replace("-", "\\-")
            st.markdown(
                f"""<style>
                .st-key-btn_{safe_id} button {{
                    background-color: #1a56db !important;
                    color: #ffffff !important;
                    border: 1px solid #1242b0 !important;
                    font-weight: 600 !important;
                }}
                .st-key-btn_{safe_id} button:hover {{
                    background-color: #1242b0 !important;
                }}
                </style>""",
                unsafe_allow_html=True,
            )

        _MAX_EQ_CHANGES = 3  # més canvis → ús inadequat

        # Diàleg de confirmació de canvi d'equació
        pending_id = st.session_state.get("confirm_change_eq")
        if pending_id:
            # Scroll automàtic del sidebar cap amunt perquè l'alumne
            # vegi el diàleg de confirmació sense haver de fer scroll manual.
            import streamlit.components.v1 as _cv1_scroll_confirm
            _cv1_scroll_confirm.html(
                """
                <script>
                (function() {
                    var sidebar = window.parent.document.querySelector(
                        '[data-testid="stSidebar"] > div'
                    );
                    if (sidebar) sidebar.scrollTop = 0;
                })();
                </script>
                """,
                height=0,
            )
            prob_pend = PB.PROBLEMS.get(pending_id, {})
            st.warning(
                f"Vols canviar a **{prob_pend.get('equacio_text', pending_id)}**? "
                "Perdràs tota la feina feta."
            )
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Sí, canvia", key="confirm_change_yes",
                             use_container_width=True):
                    st.session_state.equation_changes += 1
                    st.session_state.confirm_change_eq = None
                    start_session(pending_id)
                    st.rerun()
            with col2:
                if st.button("Cancel·la", key="confirm_change_no",
                             use_container_width=True):
                    st.session_state.confirm_change_eq = None
                    st.rerun()
            st.markdown("---")

        # Millora 1: agrupar per nivell amb capçaleres descriptives
        _NIVELL_LABELS = {
            1: "Nivell 1 · Un sol pas",
            2: "Nivell 2 · Dos passos",
            3: "Nivell 3 · Parèntesis i termes semblants",
            4: "Nivell 4 · Fraccions",
        }
        from collections import defaultdict
        probs_by_nivell: dict = defaultdict(list)
        for prob in PB.list_problems():
            if prob["nivell"] == 4 and not _show_fractions():
                continue
            probs_by_nivell[prob["nivell"]].append(prob)

        first_group = True
        for nivell in sorted(probs_by_nivell.keys()):
            sep_style = (
                "" if first_group
                else "border-top: 1px solid #e2e8f0; margin-top: 0.5rem; padding-top: 0.5rem;"
            )
            first_group = False
            label_text = _NIVELL_LABELS.get(nivell, f"Nivell {nivell}")
            st.markdown(
                f"<div style='{sep_style} background-color:#f1f5f9; "
                f"font-size:0.78em; font-weight:600; text-transform:uppercase; "
                f"letter-spacing:0.06em; color:#475569; "
                f"padding:4px 6px; border-radius:4px; margin-bottom:0.3rem;'>"
                f"{label_text}</div>",
                unsafe_allow_html=True,
            )
            for prob in probs_by_nivell[nivell]:
                if debug:
                    label = f"N{prob['nivell']} · {prob['familia']} · {prob['equacio_text']}"
                else:
                    label = prob['equacio_text']
                if st.button(label, key=f"btn_{prob['id']}", use_container_width=True):
                    s = st.session_state.session
                    active = (s is not None
                              and s.get("verdict_final") is None
                              and s.get("problem", {}).get("id") != prob["id"])
                    if active:
                        changes = st.session_state.equation_changes
                        if changes >= _MAX_EQ_CHANGES:
                            # Tractem com a ús inadequat: suspensió
                            T.process_turn(s, "!!")
                            _push_warning = True
                            st.rerun()
                        else:
                            st.session_state.confirm_change_eq = prob["id"]
                            st.rerun()
                    else:
                        st.session_state.confirm_change_eq = None
                        start_session(prob["id"])
                        st.rerun()

# "Senyals especials" (codi tècnic ?, !text, !!) només té sentit
        # per al desenvolupador. Per a Aran (13 anys) ho substituïm per
        # botons explícits: "Vull una pista" i "Vull sortir de la sessió".
        if debug:
            st.markdown("---")
            st.markdown("**Senyals especials**")
            st.markdown(
                "- `?` — demanar pista\n"
                "- `!text` — discrepància, continuar\n"
                "- `!!` — sortir de la sessió"
            )

        st.markdown("---")
        s = st.session_state.session
        if s is not None:
            # Estat intern de la sessió (im2): comptadors de torns, pistes, etc.
            # Info meta orientada al desenvolupador.
            if debug:
                st.markdown("**Estat de la sessió**")
                st.text(f"Torns:           {len(s['history']) - 1}")
                st.text(f"Pistes:          {len(s['hints_requested'])}")
                st.text(f"Estancaments:    {s['stagnation_total']}")
                st.text(f"Retrocessos:     {s['backtrack_count']}")
                st.text(f"Avisos no-math:  {s['inappropriate_warnings']}")
                if s["active_prereq"]:
                    st.text(f"En prerequisit:  {s['active_prereq']}")
                st.markdown("")  # petit espai abans dels botons d'acció

            # Accions de l'alumne durant la sessió. Visibles tant en
            # mode normal com en debug — són la substitució accessible
            # dels senyals tècnics ?, !!. El color (CSS .st-key-...)
            # els distingeix visualment: taronja per la pista (acció
            # constructiva), gris fosc per sortir (acció definitiva).
            if s["verdict_final"] is None:
                if st.button("Vull una pista",
                             key="hint_btn",
                             use_container_width=True):
                    T.process_turn(s, "?")
                    st.rerun()

                # Sortir té confirmació en dos passos: el primer clic
                # activa la flag, el rerun mostra Acceptar / Cancel·lar.
                # Així evitem tancaments accidentals.
                if not st.session_state.get("confirm_exit"):
                    if st.button("Vull sortir de la sessió",
                                 key="exit_btn",
                                 use_container_width=True):
                        st.session_state.confirm_exit = True
                        st.rerun()
                else:
                    st.warning("Vols confirmar que surts de la sessió?")
                    col_ok, col_cancel = st.columns(2)
                    with col_ok:
                        if st.button("Acceptar",
                                     key="exit_confirm_btn",
                                     use_container_width=True):
                            st.session_state.confirm_exit = False
                            T.process_turn(s, "!!")
                            st.rerun()
                    with col_cancel:
                        if st.button("Cancel·lar",
                                     key="exit_cancel_btn",
                                     use_container_width=True):
                            st.session_state.confirm_exit = False
                            st.rerun()
                    
            # Mode debug: test exhaustiu (im2 part 2).
            if debug:
                st.markdown("---")
                st.markdown("**Mode debug**")
                n_rounds = len(PB.get_test_cases(s["problem_id"]) or [])
                if n_rounds == 0:
                    st.caption("No hi ha casos de test definits per a aquest problema.")
                else:
                    st.caption(
                        f"Executa {n_rounds} ronda(es) amb inputs sintètics. "
                        "Fa moltes crides a la IA — pot trigar i té cost."
                    )
                    if st.button("🧪 Test exhaustiu",
                                 key="test_btn",
                                 use_container_width=True):
                        _run_test_and_store(s["problem_id"])
                        st.rerun()
                    if st.session_state.get("test_results"):
                        if st.button("Tanca resultats del test",
                                     key="clear_test_btn",
                                     use_container_width=True):
                            st.session_state.test_results = None
                            st.rerun()

        # Resum de cost + log path (im2 part 3) — info estrictament per
        # al desenvolupador / professor que audita l'ús de l'API.
        if debug:
            st.markdown("---")
            try:
                cost_summary = api_logger.summarize_session(L.get_session_id())
                if cost_summary["calls_total"] > 0:
                    st.caption(
                        f"Sessió · {cost_summary['calls_total']} crides · "
                        f"{cost_summary['tokens_input']:,}↓ "
                        f"+ {cost_summary['tokens_output']:,}↑ tokens · "
                        f"~${cost_summary['cost_usd']:.4f}"
                    )
                else:
                    st.caption("Sessió · cap crida encara")
            except Exception:
                pass
            st.caption(f"Log: `{api_logger.get_log_path()}`")

            # ----- Test 1-for-all -----
            # Aquest botó és independent del problema actiu: itera sobre
            # TOTS els problemes amb TEST_CASES i genera un únic JSON
            # consolidat. Pensat per al professor / desenvolupador per
            # validar pedagògicament la base sencera en una sola passada.
            # Usa un patró de doble confirmació via session_state per
            # protegir-se de clics accidentals (cost API).
            st.markdown("---")
            st.markdown("**Test 1-for-all**")
            n_total = len(PB.TEST_CASES)
            st.caption(
                f"Executa el test exhaustiu sobre els {n_total} "
                "problemes seqüencialment. Genera un únic informe JSON. "
                "**Cost API alt** — només per a validació puntual."
            )

            awaiting = st.session_state.get("awaiting_1forall_confirm", False)

            if not awaiting:
                if st.button(
                    "🧪 Test 1-for-all",
                    key="test_1forall_btn",
                    use_container_width=True,
                ):
                    st.session_state.awaiting_1forall_confirm = True
                    st.rerun()
            else:
                st.warning(
                    "Confirmes que vols fer aquest test? "
                    "Pot tenir un cost elevat!"
                )
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button(
                        "✅ Acceptar",
                        key="test_1forall_accept",
                        use_container_width=True,
                    ):
                        st.session_state.awaiting_1forall_confirm = False
                        _run_1forall_test_and_store()
                        st.rerun()
                with col_b:
                    if st.button(
                        "❌ Cancel·lar",
                        key="test_1forall_cancel",
                        use_container_width=True,
                    ):
                        st.session_state.awaiting_1forall_confirm = False
                        st.rerun()

            # Si hi ha informe disponible, mostrar download + opció de
            # netejar. El JSON es construeix on-the-fly per evitar
            # mantenir-lo en memòria si l'usuari no el baixa.
            if st.session_state.get("test_1forall_report"):
                report = st.session_state.test_1forall_report
                summary = report.get("summary", {})
                st.success(
                    f"Test acabat: {summary.get('n_problems_ok', 0)}/"
                    f"{summary.get('n_problems_total', 0)} problemes OK · "
                    f"{summary.get('n_items_match', 0)}/"
                    f"{summary.get('n_items_total', 0)} inputs match · "
                    f"~${summary.get('cost', {}).get('cost_usd', 0):.4f}"
                )
                json_bytes = json.dumps(
                    report, ensure_ascii=False, indent=2
                ).encode("utf-8")
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                st.download_button(
                    label="⬇️ Descarregar informe JSON",
                    data=json_bytes,
                    file_name=f"test_1forall_{ts}.json",
                    mime="application/json",
                    key="test_1forall_download",
                    use_container_width=True,
                )
                if st.button(
                    "Tanca informe",
                    key="test_1forall_clear",
                    use_container_width=True,
                ):
                    st.session_state.test_1forall_report = None
                    st.rerun()


def _run_test_and_store(problem_id: str):
    """Executa el test exhaustiu i guarda els resultats a session_state."""
    progress_box = st.empty()

    def on_progress(r_idx, n_rounds, i_idx, n_inputs):
        progress_box.info(
            f"Test exhaustiu: ronda {r_idx}/{n_rounds}, "
            f"input {i_idx}/{n_inputs}..."
        )

    # Generem un session_id propi per a aquest test. El test l'usarà
    # internament per al logging (sota student_id='__test_exhaustiu__')
    # i nosaltres podrem fer-ne un summarize directament: com que la
    # sessió és nova, el sumari és el cost total del test sense cap
    # subtracció.
    test_sid = uuid.uuid4().hex[:12]
    with st.spinner("Executant test exhaustiu (pot trigar uns minuts)..."):
        results = T.run_exhaustive_test(
            problem_id, on_progress=on_progress, session_id=test_sid,
        )
    progress_box.empty()

    summary = api_logger.summarize_session(test_sid)
    st.session_state.test_results = results
    st.session_state.test_problem_id = problem_id
    st.session_state.test_cost_delta = {
        "calls": summary["calls_total"],
        "tokens_in": summary["tokens_input"],
        "tokens_out": summary["tokens_output"],
        "cost_usd": summary["cost_usd"],
    }


def _run_1forall_test_and_store():
    """Executa el test exhaustiu seqüencialment sobre TOTS els problemes
    de la base que tinguin TEST_CASES, i genera un únic informe JSON
    consolidat per analitzar offline (per exemple, perquè un LLM
    auxiliar el revisi i suggereixi millores al catàleg).

    Política d'errors: si un problema concret falla amb una excepció
    catastròfica (no en una crida individual — això ja ho gestiona
    `run_exhaustive_test` internament al camp `exception` de cada
    item), el problema es marca amb `error_api=True` i el cicle
    continua amb el següent. NO interrompem el lot per un error
    aïllat: el valor del lliurable és veure quants problemes han
    passat i quins han fallat.

    L'informe és estrictament un volcat estructurat (opció (b) acordada
    amb el professor el 2026-05-11): no genera resum llegible humà,
    només dades que un LLM pot processar.
    """
    progress_box = st.empty()

    problem_ids = sorted(PB.TEST_CASES.keys())
    n_problems = len(problem_ids)

    # Session id propi per al lot sencer. Cada problema individual
    # rep un sub-session-id derivat per poder fer agregacions de cost
    # per-problema si calgués més endavant, però el cost total del
    # lot es calcula sobre `batch_sid`.
    batch_sid = uuid.uuid4().hex[:12]

    report = {
        "schema_version": 1,
        "kind": "test_1forall",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "model": getattr(L, "MODEL_NAME", "unknown"),
        "n_problems_total": n_problems,
        "batch_session_id": batch_sid,
        "problems": [],
        "summary": {},  # omplit al final
    }

    n_done = 0
    n_with_error = 0

    with st.spinner(
        f"Test 1-for-all en marxa ({n_problems} problemes). "
        "No tanquis la pestanya. Pot trigar uns minuts..."
    ):
        for pid in problem_ids:
            n_done += 1
            progress_box.info(
                f"Test 1-for-all: problema {n_done}/{n_problems} ({pid})..."
            )

            problem_entry = {
                "problem_id": pid,
                "equacio_text": PB.PROBLEMS[pid].get("equacio_text"),
                "solucio": str(PB.PROBLEMS[pid].get("solucio")),
                "errors_freqüents_declarats": list(
                    PB.PROBLEMS[pid].get("errors_freqüents", [])
                ),
                "n_rounds": len(PB.TEST_CASES.get(pid, [])),
                "results": None,
                "error_api": False,
                "error_message": None,
                "sub_session_id": None,
            }

            sub_sid = f"{batch_sid}_{pid}"
            try:
                results = T.run_exhaustive_test(
                    pid, on_progress=None, session_id=sub_sid,
                )
                problem_entry["results"] = results
                problem_entry["sub_session_id"] = sub_sid
            except Exception as e:
                # Error catastròfic: el problema sencer s'ha romput.
                # No interrompem el lot — marquem i continuem.
                problem_entry["error_api"] = True
                problem_entry["error_message"] = f"{type(e).__name__}: {e}"
                n_with_error += 1

            report["problems"].append(problem_entry)

    progress_box.empty()

    # Resum agregat: comptem matches/mismatches i excepcions per input
    # per facilitar el primer cop d'ull a l'LLM analitzador.
    n_items_total = 0
    n_items_match = 0
    n_items_exception = 0
    mismatches_by_problem = {}

    for pe in report["problems"]:
        if pe["error_api"] or pe["results"] is None:
            continue
        for round_data in pe["results"]:
            for item in round_data.get("items", []):
                n_items_total += 1
                if item.get("exception"):
                    n_items_exception += 1
                if item.get("match"):
                    n_items_match += 1
                else:
                    mismatches_by_problem.setdefault(pe["problem_id"], []).append({
                        "round": round_data["round"],
                        "input": item["input"],
                        "expected": item["expected"],
                        "got_verdict": item.get("verdict"),
                        "got_error_label": item.get("error_label"),
                        "exception": item.get("exception"),
                    })

    # Cost total del lot: el sumari per `batch_sid` no inclou les
    # crides perquè cada sub-test usa un sub_sid diferent. Cal sumar
    # els sub_sids manualment.
    total_calls = 0
    total_tokens_in = 0
    total_tokens_out = 0
    total_cost = 0.0
    for pe in report["problems"]:
        sid = pe.get("sub_session_id")
        if not sid:
            continue
        try:
            s = api_logger.summarize_session(sid)
            total_calls += s.get("calls_total", 0)
            total_tokens_in += s.get("tokens_input", 0)
            total_tokens_out += s.get("tokens_output", 0)
            total_cost += s.get("cost_usd", 0.0)
        except Exception:
            pass

    report["summary"] = {
        "n_problems_total": n_problems,
        "n_problems_ok": n_problems - n_with_error,
        "n_problems_error_api": n_with_error,
        "n_items_total": n_items_total,
        "n_items_match": n_items_match,
        "n_items_mismatch": n_items_total - n_items_match,
        "n_items_exception": n_items_exception,
        "mismatches_by_problem": mismatches_by_problem,
        "cost": {
            "calls_total": total_calls,
            "tokens_input": total_tokens_in,
            "tokens_output": total_tokens_out,
            "cost_usd": round(total_cost, 6),
        },
    }
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")

    st.session_state.test_1forall_report = report


# ------------------------------------------------------------
# Pantalla central
# ------------------------------------------------------------
def state_so_far(history: list) -> str | None:
    """
    Retorna el text de l'últim pas `correcte_progres` de la cadena.
    És la millor equació equivalent acceptada fins al moment — la que
    l'alumne ha d'usar com a punt de partida per al proper pas.
    Retorna None si l'alumne encara no ha avançat cap pas vàlid.
    """
    best = None
    for h in history:
        if h.get("verdict") == "correcte_progres":
            best = h["text"]
    return best


def render_main():
    s = st.session_state.session

    if s is None:
        st.title("Aprendre a resoldre equacions")
        st.write("Escull una equació a la barra lateral.")
        return

    # Decidim layout: si hi ha prerequisit actiu, partim en dues columnes.
    has_prereq = s["active_prereq"] is not None and s["verdict_final"] is None

    if has_prereq:
        # Scroll automàtic de la pàgina principal cap amunt perquè l'alumne
        # vegi la capçalera del panell de reforç sense haver de fer scroll.
        # Provem els dos selectors més habituals del contenidor scrollable
        # de Streamlit (pot variar entre versions).
        import streamlit.components.v1 as _cv1_scroll_main
        _cv1_scroll_main.html(
            """
            <script>
            (function() {
                var doc = window.parent.document;
                var main = doc.querySelector('[data-testid="stMain"]')
                        || doc.querySelector('section.main');
                if (main) main.scrollTop = 0;
            })();
            </script>
            """,
            height=0,
        )
        col_main, col_prereq = st.columns([3, 2], gap="large")
        with col_main:
            _render_problem_main(s, input_disabled=True)
        with col_prereq:
            _render_prereq_panel(s)
    else:
        # Una sola columna centrada (no full-width amb layout=wide)
        _, col_center, _ = st.columns([1, 3, 1])
        with col_center:
            _render_problem_main(s, input_disabled=False)

    # Si hi ha resultats d'un test exhaustiu per a aquest problema, els
    # mostrem sota la columna principal (només en mode debug; el botó
    # per llençar-los també està amagat fora de debug, però per coherència
    # el panell també).
    if (_is_debug_mode()
            and st.session_state.get("test_results")
            and st.session_state.get("test_problem_id") == s["problem_id"]):
        _render_test_results(st.session_state.test_results)


def _render_problem_main(s, input_disabled: bool):
    """Renderitza el problema principal: capçalera, cadena, missatges, input."""
    debug = _is_debug_mode()
    # Capçalera del problema
    # En mode debug mostrem l'ID intern; a l'alumne li mostrem la forma canònica.
    _FAMILIA_FORMA = {
        "EQ1-A": "x + b = c",   "EQ1-B": "ax = b",       "EQ1-C": "x − b = c",
        "EQ2-A": "ax + b = c",  "EQ2-B": "ax − b = c",   "EQ2-C": "−ax + b = c",
        "EQ2-D": "c = ax + b",  "EQ3-A": "a(x + b) = c", "EQ3-B": "a + b(x + c) = d",
        "EQ3-C": "ax + b = cx + d", "EQ3-D": "a − (x + b) = c",
        "EQ4-A": "x/a + b = c", "EQ4-B": "a/b · x + c = d", "EQ4-C": "−(x + b)/a = c",
    }
    familia = s["problem"].get("familia", "")
    forma = _FAMILIA_FORMA.get(familia, familia)
    if debug:
        st.markdown(f"### Equació {s['problem_id']}  `{forma}`")
        st.caption(f"Nivell {s['problem']['nivell']} · {s['problem']['tema']}")
    else:
        st.markdown(
            f"<h3 style='font-size:1.28em;margin-bottom:0.2rem'>"
            f"Equació de la forma&nbsp;&nbsp;"
            f"<span class='eq-forma'>{_frac_html(forma)}</span></h3>",
            unsafe_allow_html=True,
        )

    # Instrucció inicial: només visible abans de la primera interacció.
    # Un cop l'alumne ha fet almenys un pas (la cadena té >1 element),
    # la instrucció desapareix per no fer soroll.
    n_steps = len([h for h in s["history"] if h["step"] > 0])
    if n_steps == 0:
        st.markdown(
            "Has de simplificar l'equació per poder estar més a prop d'aïllar la "
            "incògnita `x`. Atenció, no has de donar directament la solució, sinó "
            "avançar pas a pas."
        )

    st.markdown("<hr>", unsafe_allow_html=True)

    # Cadena d'equacions
    st.markdown("**Cadena d'equacions**")
    visible_history = _filter_superseded_errors(s["history"])

    # Millora 4: indicador de progrés (punts + text)
    steps_done = len([h for h in visible_history
                      if h["step"] > 0 and h.get("verdict") != "error"])
    steps_expected = s["problem"].get("passos_esperats", None)
    if steps_expected is not None:
        if steps_expected <= 6:
            dots_html = "".join(
                f"<span style='color:#1e40af;font-size:1em;'>●</span>"
                if i < steps_done else
                f"<span style='color:#cbd5e1;font-size:1em;'>○</span>"
                for i in range(steps_expected)
            )
            progress_html = (
                f"<div style='margin:0.3rem 0 0.5rem 0; display:flex; "
                f"align-items:center; gap:6px;'>"
                f"{dots_html}"
                f"<span style='color:#64748b; font-size:0.82em; margin-left:4px;'>"
                f"Pas {steps_done} de {steps_expected}</span></div>"
            )
        else:
            progress_html = (
                f"<div style='margin:0.3rem 0 0.5rem 0; color:#64748b; "
                f"font-size:0.82em;'>Pas {steps_done} de {steps_expected}</div>"
            )
        st.markdown(progress_html, unsafe_allow_html=True)

    # Millora 3: injectar CSS per a l'espaiat i el grid de numeració
    st.markdown(
        """
        <style>
        .eq-chain-step, .eq-chain-original {
            margin-bottom: 0.55rem;
        }
        .eq-chain-numbered {
            display: grid;
            grid-template-columns: 2.5rem 1fr;
            align-items: start;
            margin-bottom: 0.55rem;
        }
        .eq-chain-step-num {
            color: #94a3b8;
            font-size: 0.85em;
            font-family: monospace;
            padding-top: 2px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    step_display_counter = 0
    for h in visible_history:
        if h["step"] == 0:
            st.markdown(
                f"<div class='eq-chain-original' style='margin-bottom:0.55rem;'>"
                f"<code>{_frac_html(h['text'])}</code>"
                f"&nbsp; · <em>equació original</em></div>",
                unsafe_allow_html=True,
            )
        else:
            step_display_counter += 1
            badge = _verdict_badge(h["verdict"])
            err_label = h.get("error_label") if _is_debug_mode() else None
            err = f"<span class='err-label'> · {err_label}</span>" if err_label else ""
            if h["verdict"] == "error":
                css_class = "eq-error"
            elif h["verdict"] == "correcte_estancat":
                css_class = "eq-stagnant"
            else:
                css_class = ""
            st.markdown(
                f"<div class='eq-chain-numbered'>"
                f"<span class='eq-chain-step-num'>{step_display_counter}.</span>"
                f"<div class='eq-chain-step {css_class}'>"
                f"<code>{_frac_html(h['text'])}</code>  · {badge}{err}"
                f"</div></div>",
                unsafe_allow_html=True,
            )

    # Indicador discret si hi ha errors amagats. Aquesta línia menciona
    # el "rastre JSON" i és fonamentalment una nota per al desenvolupador
    # que audita la sessió. L'alumne no necessita saber-ho.
    n_hidden = len(s["history"]) - len(visible_history)
    if n_hidden > 0 and _is_debug_mode():
        plural = "s" if n_hidden > 1 else ""
        st.caption(
            f"({n_hidden} intent{plural} previ{plural} superat{plural} "
            f"· visible al rastre JSON)"
        )

    # Missatges del torn anterior dirigits al fil principal.
    #
    # Regla pedagògica: el requadre verd "prereq_resolved" viu des que
    # es resol el prereq fins al primer pas nou de l'alumne al fil
    # principal. Després, MAI MÉS.
    #
    # Implementació: marquem la longitud de l'historial en el moment en
    # què veiem el missatge verd per primera vegada. Quan l'historial
    # creix (l'alumne ha fet un pas nou), eliminem físicament tots els
    # missatges `prereq_resolved` de `s["messages"]`. NO només els
    # filtrem al render: si un prereq nou s'activa més tard (per culpa
    # d'un altre error), no volem que el missatge antic ressusciti.
    # (Bug observat 2026-05-13: l'eliminació era només filtre i el
    # reset del marcador quan s'activava un nou prereq feia reaparèixer
    # el verd antic.)
    has_prereq_resolved_msg = any(
        m.get("kind") == "prereq_resolved"
        for m in s.get("messages", [])
        if m.get("target", "main") == "main"
    )
    prl_key = "prereq_resolved_history_len"
    if has_prereq_resolved_msg and st.session_state.get(prl_key) is None:
        # Primera vegada que veiem un missatge verd: marquem la longitud
        # actual de l'historial.
        st.session_state[prl_key] = len(s["history"])
    elif (
        st.session_state.get(prl_key) is not None
        and len(s["history"]) > st.session_state[prl_key]
    ):
        # L'alumne ha fet un pas nou des que es va resoldre el prereq.
        # Eliminem físicament el missatge verd perquè no torni a sortir
        # mai més, encara que un nou prereq s'activi pel mig.
        s["messages"] = [
            m for m in s.get("messages", [])
            if not (m.get("kind") == "prereq_resolved"
                    and m.get("target", "main") == "main")
        ]
        st.session_state[prl_key] = None

    main_msgs = [
        m for m in s.get("messages", [])
        if m.get("target", "main") == "main"
    ]
    if main_msgs:
        st.markdown("<hr>", unsafe_allow_html=True)
        for m in main_msgs:
            _render_message(m)

    # Sessió tancada
    if s["verdict_final"] is not None:
        st.markdown("<hr>", unsafe_allow_html=True)
        if s["verdict_final"] == "resolt":
            st.success("Sessió completada amb èxit.")
        elif s["verdict_final"] == "abandonat":
            st.info("Sessió tancada per l'alumne.")
        elif s["verdict_final"] == "suspes_us_inadequat":
            st.error("Sessió suspesa per ús inadequat.")
        # Codi de sessió — visible sempre (no és informació sensible).
        st.markdown("<br>", unsafe_allow_html=True)
        _render_codi_sessio(s)
        # Rastre JSON: només en mode debug. Per a l'alumne és sorollós i
        # exposa l'estructura interna que no necessita.
        if _is_debug_mode():
            _render_trace(s)
        return

    if input_disabled:
        # Hi ha prerequisit actiu: l'input principal queda desactivat,
        # l'alumne ha de respondre primer al panell dret.
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown(
            "<p style='color:#92400e; font-size:1em; margin:0;'>"
            "→ Primer, respon l'exercici de la dreta.</p>",
            unsafe_allow_html=True,
        )
        return

    # Input principal
    st.markdown("<hr>", unsafe_allow_html=True)
    _render_input_form(s, key_prefix="main")


def _render_prereq_panel(s):
    """Panell dret per a la sub-tasca del prerequisit."""
    prereq = PB.get_prerequisite(s["active_prereq"])

    # Millora 2: injectar CSS per al contenidor del panell de reforç.
    # Streamlit no permet passar estils directament a st.container(),
    # però podem injectar un bloc CSS que seleccioni el div pel data-testid
    # que Streamlit afegeix automàticament a cada contenidor amb key.
    st.markdown(
        """
        <style>
        [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"]:has(
            [data-testid="stMarkdownContainer"] > p > strong
        ) {}
        /* Classe per al contenidor del prereq via key CSS */
        .prereq-panel-wrapper {
            background-color: #fffbeb;
            border-left: 4px solid #f59e0b;
            border-radius: 6px;
            padding: 1rem 1.2rem;
            margin-top: 0.4rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div class='prereq-panel-wrapper'>",
        unsafe_allow_html=True,
    )

    # Avís d'obligatorietat
    st.markdown(
        "<div style='background:#fef3c7; border:1px solid #f59e0b; "
        "border-radius:4px; padding:0.5rem 0.8rem; margin-bottom:0.6rem; "
        "color:#92400e; font-size:0.95em;'>"
        "Respon aquest exercici abans de continuar.</div>",
        unsafe_allow_html=True,
    )

    st.markdown("**Exercici de reforç**")
    st.caption(prereq.get("concept", ""))

    st.markdown("<hr>", unsafe_allow_html=True)

    # Reformatem la pregunta del prereq en tres línies:
    #   [equació]
    #   [Quina...?]
    #   Explica-ho amb les teves paraules.
    #
    # Funciona per als dos patrons observats al catàleg:
    #   - "Si tens [EQ], quina operació...? Explica-ho..."
    #   - "Tens [EQ] i vols [context]. Quina operació...? Explica-ho..."
    _q_raw = prereq.get("question", "")

    # 1. Extreu l'equació: text entre "Si tens"/"Tens" i
    #    la primera coma seguida de minúscula, " i " o punt.
    _eq_m = re.search(
        r'(?:Si tens|Tens)\s+(.+?)(?=,\s+[a-zàèéíïòóúü]|\s+i\s+[a-zàèéíïòóúü]|\.)',
        _q_raw,
    )
    # 2. Extreu la pregunta "Quina...?" (majúscula o minúscula)
    _qm = re.search(r'[Qq]uina[^?]+\?', _q_raw)

    if _eq_m and _qm:
        _eq_part = html.escape(_eq_m.group(1).strip())
        _qtext   = _qm.group(0).strip()
        _qtext   = _qtext[0].upper() + _qtext[1:]   # primera lletra en majúscula
        _q_part  = html.escape(_qtext)
        question_html = (
            f"<p style='margin:0; line-height:1.7;'>"
            f"<span style='font-family:monospace; font-size:1.1em; "
            f"font-weight:600;'>{_eq_part}</span><br>"
            f"<span style='font-weight:600;'>{_q_part}</span><br>"
            f"<span style='color:#78716c;'>Explica-ho amb les teves paraules.</span>"
            f"</p>"
        )
    else:
        # Fallback: mostrem el text original sense transformar
        question_html = (
            f"<p style='margin:0; font-weight:600;'>{html.escape(_q_raw)}</p>"
        )
    st.markdown(question_html, unsafe_allow_html=True)

    # Missatges propis del prerequisit
    prereq_msgs = [m for m in s.get("messages", [])
                   if m.get("target", "main") == "prereq"]
    for m in prereq_msgs:
        _render_message(m)

    st.markdown("<hr>", unsafe_allow_html=True)
    _render_input_form(s, key_prefix="prereq")

    st.markdown("</div>", unsafe_allow_html=True)


def _render_input_form(s, key_prefix: str):
    """Form d'input. Comú al fil principal i al prerequisit."""
    key_in = f"input_{key_prefix}_{st.session_state.input_counter}"
    key_form = f"form_{key_prefix}_{st.session_state.input_counter}"

    # Millora 5: contenidor visual prominent per a la zona d'input.
    # Injectem un selector CSS basat en el key del form per donar-li
    # un fons subtil i un contorn que el distingeixi de la resta de la pàgina.
    safe_key = key_form.replace("-", "\\-")
    st.markdown(
        f"""
        <style>
        [data-testid="stForm"][id="{key_form}"] {{
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 1rem 1.2rem;
            margin-top: 0.8rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Nombre de passos correctes fets fins ara (per al helper inicial)
    n_steps_done = len([h for h in s["history"] if h["step"] > 0
                        and h.get("verdict") != "error"])

    # IMPORTANT: clear_on_submit=False. Si el posem a True, el text que
    # l'alumne ha escrit desapareix immediatament en clicar Enter, abans
    # que el sistema acabi d'avaluar-lo (typically ~0.5-2s amb el thinking
    # model). Això crea una sensació desorientadora ("on ha anat el meu
    # text?"). Amb False, el text roman al camp durant tota l'avaluació
    # i només es buida quan el rerun final renderitza un nou camp (gràcies
    # a `input_counter` que canvia el key del widget).
    with st.form(key=key_form, clear_on_submit=False):
        # Etiqueta amb més pes visual (Millora 5)
        st.markdown(
            "<p style='font-weight:600; font-size:1em; color:#1e293b; margin-bottom:0.3rem;'>"
            "Escriu el pas següent:</p>",
            unsafe_allow_html=True,
        )
        # `autocomplete="off"` ja s'aplica també des del JS injectat al cap
        # de l'app (juntament amb autocorrect / autocapitalize / spellcheck
        # i un name aleatori). El passem aquí com a defensa redundant per
        # si el script no s'arriba a executar.
        raw = st.text_input(
            "Escriu el pas següent:",
            label_visibility="collapsed",
            key=key_in,
            autocomplete="off",
        )
        submit = st.form_submit_button("Enviar", type="primary")

    # Helper inicial: desapareix després del primer pas correcte (Millora 5)
    if n_steps_done == 0 and key_prefix == "main":
        st.caption(
            "Escriu l'equació equivalent al primer pas de la resolució."
        )

    if submit and raw:
        st.session_state.retry_messages = []
        # Inclou el text de l'alumne dins del missatge del spinner perquè
        # vegi clarament què s'està avaluant en cada moment.
        suffix = (" (pot trigar uns segons mentre el sistema raona)"
                  if "pro" in L.MODEL.lower() else "")
        spinner_text = f"Estic avaluant «{raw}»...{suffix}"
        with st.spinner(spinner_text):
            placeholder = st.empty()
            T.process_turn(s, raw)
            for msg in st.session_state.retry_messages:
                placeholder.warning(msg)
        st.session_state.input_counter += 1
        st.rerun()


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _filter_superseded_errors(history: list) -> list:
    """
    Amaga els errors que han estat superats per un pas correcte posterior.
    Estratègia: recorrem la història; quan trobem un pas correcte, eliminem
    de la llista visible tots els errors immediatament anteriors fins al
    darrer pas correcte (o l'enunciat). Els passos de tipus 'no_math'
    (avisos d'ús inadequat) també queden amagats si han estat superats.

    El JSON sencer es manté al rastre per al professorat.
    """
    visible = []
    for h in history:
        v = h["verdict"]
        if v in ("correcte_progres", "correcte_estancat"):
            # Aquest pas correcte supera els errors previs encara visibles.
            # Eliminem els errors fins al darrer pas correcte/inicial.
            while visible and visible[-1]["verdict"] in ("error", "no_math"):
                visible.pop()
            visible.append(h)
        else:
            visible.append(h)
    return visible


def _verdict_badge(v: str) -> str:
    return {
        "correcte_progres": "Correcte ✓",
        "correcte_estancat": "No has simplificat prou",
        "error": "Errada ✗",
        "no_math": "No detecto matemàtiques (!)",
        "inicial": "—",
    }.get(v, v)


def _render_message(m: dict):
    kind = m["kind"]
    text = m["text"]
    if kind == "feedback":
        st.markdown(f"**Missatge:** {text}")
    elif kind == "hint":
        st.info(f"💡 **Pista:** {text}")
    elif kind == "worked_example":
        # Escalada nivell 1: l'alumne ha tornat a fallar el mateix concepte
        # després del prereq. Mostrem un exemple resolt anàleg.
        st.info(f"📌 **Exemple resolt:** {text}")
    elif kind == "concrete_step":
        # Escalada nivell 2: ni el prereq ni l'exemple no han desencallat
        # l'alumne. Donem el pas concret de manera molt directa.
        st.info(f"🎯 **Pas concret:** {text}")
    elif kind == "prereq_resolved":
        # Caixa auxiliar de "encert al prereq". Petita, verda, clarament
        # diferent dels passos del problema principal. L'alumne sap que
        # ha resolt una tasca paral·lera, no un pas de l'equació original.
        extra = m.get("extra", {})
        if extra and extra.get("initial_equation") and extra.get("steps"):
            html = _render_prereq_visual_box(
                extra,
                kind="resolved",
                header="✓ Correcte.",
            )
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.success(f"✓ {text}")
    elif kind == "prereq_failed":
        # Caixa auxiliar de "fracàs al prereq". Persistent al viewport
        # (a diferència del missatge dins del panell del prereq, que es
        # tanca). Amb l'explicació de la resposta correcta.
        # Mateix render visual que `prereq_resolved` però en color groc/
        # taronja (warning) i capçalera diferent. L'alumne veu la solució
        # correcta encara que ell hagi fallat, perquè pugui aprendre de
        # l'error.
        extra = m.get("extra", {})
        if extra and extra.get("initial_equation") and extra.get("steps"):
            html = _render_prereq_visual_box(
                extra,
                kind="failed",
                header="✗ La resposta no era correcta.",
            )
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.warning(f"✗ {text}")
    elif kind == "warning":
        st.warning(text)
    elif kind == "system":
        st.caption(text)
    elif kind == "prereq":
        st.markdown(f"**↻** {text}")
    elif kind == "discrepancy":
        st.success(f"📝 {text}")
    else:
        st.write(text)


def _render_trace(s):
    with st.expander("Veure rastre JSON de la sessió"):
        st.code(T.serialize_trace(s), language="json")


def _render_test_results(rounds: list):
    """
    Mostra els resultats del test exhaustiu sota la columna principal.
    Cada ronda és una secció: una capçalera amb l'equació de partida i
    una taula de fila per input amb veredicte i comparació esperat/got.
    """
    st.markdown("---")
    n_total = sum(len(r["items"]) for r in rounds)
    n_match = sum(1 for r in rounds for it in r["items"] if it["match"])
    title_emoji = "✅" if n_match == n_total else "⚠️"
    st.markdown(f"### {title_emoji} Test exhaustiu — {n_match}/{n_total} OK")
    st.caption(
        "Cada ronda parteix d'un estat fresc del problema (no afecta la "
        "sessió actual). El primer input és la resposta correcta esperada; "
        "els altres són errors versemblants. ✅ = veredicte coherent amb "
        "l'esperat; ❌ = mismatch que cal investigar."
    )
    # Cost del test: si el runner ha guardat el delta, mostrem-lo perquè
    # l'autor del problema vegi quant li costa cada execució del test.
    delta = st.session_state.get("test_cost_delta")
    if delta:
        st.caption(
            f"Cost d'aquesta execució: ~${delta['cost_usd']:.4f} "
            f"({delta['calls']} crides · "
            f"{delta['tokens_in']:,}↓ + {delta['tokens_out']:,}↑ tokens)"
        )

    for r in rounds:
        st.markdown(
            f"**Ronda {r['round']}** — des de `{r['from_eq']}`"
        )
        for it in r["items"]:
            mark = "✅" if it["match"] else "❌"
            verdict = it.get("verdict") or "?"
            label = it.get("error_label")
            label_str = f" · `{label}`" if label else ""
            expected = it["expected"]
            exp_short = "correcte" if expected == "correct" else "error"

            line = (
                f"{mark} `{it['input']}`  →  **{verdict}**{label_str}  "
                f"_(esperat: {exp_short})_"
            )
            st.markdown(line)
            if it.get("feedback"):
                st.markdown(
                    f"<div style='margin-left:1.6rem;color:#555;"
                    f"font-size:0.9em'>↳ {it['feedback']}</div>",
                    unsafe_allow_html=True,
                )
            if it.get("prereq_triggered"):
                st.markdown(
                    f"<div style='margin-left:1.6rem;color:#555;"
                    f"font-size:0.9em'>↻ Prereq <b>{it['prereq_triggered']}</b>: "
                    f"{it.get('prereq_question','')}</div>",
                    unsafe_allow_html=True,
                )
            if it.get("exception"):
                st.error(f"Excepció: {it['exception']}")
        st.markdown("")


# ------------------------------------------------------------
# Punt d'entrada
# ------------------------------------------------------------
def main():
    init_state()
    # Defensiu: si hi ha sessió activa, re-establim el context de logging
    # a cada rerun. Streamlit normalment reutilitza el mateix thread per
    # a una sessió d'usuari, però aquesta crida garanteix que un canvi
    # de thread (p. ex. recàrrega de codi) no faci que les crides quedin
    # etiquetades com a "anon" silenciosament.
    s = st.session_state.get("session")
    if s is not None:
        L.set_log_context(
            session_id=s.get("session_id"),
        )
    render_sidebar()
    render_main()


if __name__ == "__main__":
    main()
