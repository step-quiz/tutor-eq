"""
Tutor d'equacions lineals — UI Streamlit.

Per executar:
    export GEMINI_API_KEY=...
    streamlit run app.py

L'estat de la sessió viu a st.session_state. La lògica viu a tutor.py.
"""

import os
import streamlit as st

import problems as PB
import tutor as T
import llm as L
import api_logger

st.set_page_config(
    page_title="Tutor IA — equacions lineals",
    layout="wide",
    initial_sidebar_state="collapsed",
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
      /* Limitar amplada del bloc central perquè no s'estiri massa
         en el layout wide quan no hi ha prerequisit actiu */
      .main-narrow { max-width: 720px; }

    </style>
    <script>
    /* Desactivar l'autocompletat del navegador als text_input de Streamlit.
       Streamlit no exposa l'atribut 'autocomplete' directament, per tant
       cal injectar-lo via JS amb un MutationObserver que vigili el DOM. */
    (function() {
        function applyNoAutocomplete() {
            document.querySelectorAll('input[type="text"]').forEach(function(el) {
                if (el.getAttribute('autocomplete') !== 'off') {
                    el.setAttribute('autocomplete', 'off');
                }
            });
        }
        var observer = new MutationObserver(applyNoAutocomplete);
        observer.observe(document.body, { childList: true, subtree: true });
        applyNoAutocomplete();
    })();
    </script>
    """,
    unsafe_allow_html=True,
)




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


def start_session(problem_id: str):
    st.session_state.session = T.new_session_state(problem_id)
    st.session_state.input_counter += 1


# Callback per a la UI: rep avisos de l'API durant els retries
def _on_api_retry(message: str):
    st.session_state.retry_messages.append(message)


L.set_progress_callback(_on_api_retry)


# ------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------
def render_sidebar():
    with st.sidebar:
        st.markdown("### Tutor IA — equacions lineals")
        st.caption("Pilot 2n d'ESO — mode professor")

        if not os.environ.get("GEMINI_API_KEY"):
            st.error("Falta GEMINI_API_KEY.")
            st.stop()

        # Info del model actiu (útil mentre depurem)
        st.caption(f"Model actiu: `{L.MODEL}`")

        st.markdown("---")
        st.markdown("**Selecciona problema**")

        for prob in PB.list_problems():
            label = f"N{prob['nivell']} · {prob['familia']} · {prob['equacio_text']}"
            if st.button(label, key=f"btn_{prob['id']}", use_container_width=True):
                start_session(prob["id"])
                st.rerun()

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
            st.markdown("**Estat de la sessió**")
            st.text(f"Torns:           {len(s['history']) - 1}")
            st.text(f"Pistes:          {len(s['hints_requested'])}")
            st.text(f"Estancaments:    {s['stagnation_total']}")
            st.text(f"Retrocessos:     {s['backtrack_count']}")
            st.text(f"Avisos no-math:  {s['inappropriate_warnings']}")
            if s["active_prereq"]:
                st.text(f"En prerequisit:  {s['active_prereq']}")

            # Botó Sortir (només si la sessió està activa)
            if s["verdict_final"] is None:
                if st.button("Sortir de la sessió (!!)",
                             key="exit_btn",
                             use_container_width=True):
                    T.process_turn(s, "!!")
                    st.rerun()

        st.markdown("---")
        st.caption(f"Log: `{api_logger.get_log_path()}`")


# ------------------------------------------------------------
# Pantalla central
# ------------------------------------------------------------
def render_main():
    s = st.session_state.session

    if s is None:
        st.title("Tutor d'equacions lineals")
        st.write("Tria un problema a la barra lateral per començar.")
        st.markdown("---")
        st.markdown(
            "**Què espera de tu el sistema?** En cada torn, escriu una equació "
            "intermèdia equivalent que avanci cap a aïllar `x`. No has de donar "
            "directament la solució: la cadena d'equacions és la teva traça de "
            "raonament. El sistema verificarà cada pas."
        )
        return

    # Decidim layout: si hi ha prerequisit actiu, partim en dues columnes.
    has_prereq = s["active_prereq"] is not None and s["verdict_final"] is None

    if has_prereq:
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


def _render_problem_main(s, input_disabled: bool):
    """Renderitza el problema principal: capçalera, cadena, missatges, input."""
    # Capçalera del problema
    st.markdown(f"### Problema {s['problem_id']}")
    st.caption(f"Nivell {s['problem']['nivell']} · {s['problem']['tema']}")

    st.markdown("<hr>", unsafe_allow_html=True)

    # Cadena d'equacions
    st.markdown("**Cadena de la sessió**")
    visible_history = _filter_superseded_errors(s["history"])
    for h in visible_history:
        if h["step"] == 0:
            st.markdown(f"`{h['text']}`  · *enunciat*")
        else:
            badge = _verdict_badge(h["verdict"])
            err_label = h.get("error_label")
            err = f"<span class='err-label'> · {err_label}</span>" if err_label else ""
            css_class = "eq-error" if h["verdict"] == "error" else ""
            st.markdown(
                f"<div class='{css_class}'>"
                f"<code>{h['text']}</code>  · {badge}{err}"
                f"</div>",
                unsafe_allow_html=True,
            )

    # Indicador discret si hi ha errors amagats
    n_hidden = len(s["history"]) - len(visible_history)
    if n_hidden > 0:
        plural = "s" if n_hidden > 1 else ""
        st.caption(
            f"({n_hidden} intent{plural} previ{plural} superat{plural} "
            f"· visible al rastre JSON)"
        )

    # Missatges del torn anterior dirigits al fil principal
    main_msgs = [m for m in s.get("messages", [])
                 if m.get("target", "main") == "main"]
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
        _render_trace(s)
        return

    if input_disabled:
        # Hi ha prerequisit actiu: l'input principal queda desactivat,
        # l'alumne ha de respondre primer al panell dret.
        st.markdown("<hr>", unsafe_allow_html=True)
        st.caption(
            "Respon primer la pregunta del prerequisit a la dreta. "
            "Després tornaràs a aquest problema."
        )
        return

    # Input principal
    st.markdown("<hr>", unsafe_allow_html=True)
    _render_input_form(s, key_prefix="main")


def _render_prereq_panel(s):
    """Panell dret per a la sub-tasca del prerequisit."""
    prereq = PB.get_prerequisite(s["active_prereq"])
    st.markdown("### ↻ Prerequisit")
    st.caption(prereq.get("concept", ""))

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown(f"**{prereq['question']}**")

    # Missatges propis del prerequisit
    prereq_msgs = [m for m in s.get("messages", [])
                   if m.get("target", "main") == "prereq"]
    for m in prereq_msgs:
        _render_message(m)

    st.markdown("<hr>", unsafe_allow_html=True)
    _render_input_form(s, key_prefix="prereq")


def _render_input_form(s, key_prefix: str):
    """Form d'input. Comú al fil principal i al prerequisit."""
    key_in = f"input_{key_prefix}_{st.session_state.input_counter}"
    key_form = f"form_{key_prefix}_{st.session_state.input_counter}"
    with st.form(key=key_form, clear_on_submit=True):
        # L'autocomplete es desactiva via el MutationObserver injectat a la capçalera.
        raw = st.text_input(
            "La teva resposta:",
            key=key_in,
        )
        submit = st.form_submit_button("Enviar", type="primary")

    if submit and raw:
        st.session_state.retry_messages = []
        spinner_text = (
            "Avaluant... (amb gemini-2.5-pro pot trigar uns segons; el model "
            "fa raonament intern abans de respondre)"
            if "pro" in L.MODEL.lower()
            else "Avaluant..."
        )
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
        "correcte_progres": "✓ progrés",
        "correcte_estancat": "≈ estancat",
        "error": "✗ error",
        "no_math": "— no math",
        "inicial": "—",
    }.get(v, v)


def _render_message(m: dict):
    kind = m["kind"]
    text = m["text"]
    if kind == "feedback":
        st.markdown(f"**Feedback:** {text}")
    elif kind == "hint":
        st.info(f"💡 **Pista:** {text}")
    elif kind == "warning":
        st.warning(text)
    elif kind == "system":
        st.caption(text)
    elif kind == "prereq":
        st.markdown(f"**↻ Retrocés a prerequisit:** {text}")
    elif kind == "discrepancy":
        st.success(f"📝 {text}")
    else:
        st.write(text)


def _render_trace(s):
    with st.expander("Veure rastre JSON de la sessió"):
        st.code(T.serialize_trace(s), language="json")


# ------------------------------------------------------------
# Punt d'entrada
# ------------------------------------------------------------
def main():
    init_state()
    render_sidebar()
    render_main()


if __name__ == "__main__":
    main()
