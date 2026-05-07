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
    layout="centered",
)

# CSS per reduir espai entre l'enunciat i la cadena de la sessió,
# i ajustar marges generals.
st.markdown(
    """
    <style>
      hr { margin: 0.6rem 0 !important; }
      .block-container h3 { margin-top: 0.3rem !important; }
      .block-container { padding-top: 2rem !important; }
    </style>
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

    # Capçalera del problema (compactada)
    st.markdown(f"### Problema {s['problem_id']}")
    st.markdown(
        f"**Nivell {s['problem']['nivell']} · {s['problem']['tema']}**  \n"
        f"**Resol:** `{s['problem']['equacio_text']}`"
    )

    # Separador suau
    st.markdown("<hr>", unsafe_allow_html=True)

    # Cadena d'equacions
    st.markdown("**Cadena de la sessió**")
    for h in s["history"]:
        if h["step"] == 0:
            st.markdown(f"`{h['text']}`  · *enunciat*")
        else:
            badge = _verdict_badge(h["verdict"])
            err = f" · {h['error_label']}" if h.get("error_label") else ""
            st.markdown(f"`{h['text']}`  · {badge}{err}")

    # Missatges del torn anterior
    if s.get("messages"):
        st.markdown("<hr>", unsafe_allow_html=True)
        for m in s["messages"]:
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

    # Input
    st.markdown("<hr>", unsafe_allow_html=True)
    if s["active_prereq"] is not None:
        prereq = PB.get_prerequisite(s["active_prereq"])
        st.markdown(f"**Pregunta del prerequisit:** {prereq['question']}")

    # Form: tecla Enter equival a clicar Enviar (millora 4)
    key_in = f"input_{st.session_state.input_counter}"
    key_form = f"form_{st.session_state.input_counter}"
    with st.form(key=key_form, clear_on_submit=False):
        raw = st.text_input("La teva resposta:", key=key_in)
        cols = st.columns([1, 1, 4])
        with cols[0]:
            submit = st.form_submit_button("Enviar", type="primary")
        with cols[1]:
            end = st.form_submit_button("Sortir (!!)")

    if submit and raw:
        # Reset retry messages abans de cada torn
        st.session_state.retry_messages = []
        spinner_text = (
            "Avaluant... (amb gemini-2.5-pro pot trigar uns segons; el model "
            "fa raonament intern abans de respondre)"
            if "pro" in L.MODEL.lower()
            else "Avaluant..."
        )
        with st.spinner(spinner_text):
            # Si hi ha retries, els mostrem visualment fent un placeholder
            placeholder = st.empty()
            T.process_turn(s, raw)
            # Si han arribat avisos durant la crida, els registrem com a missatges
            for msg in st.session_state.retry_messages:
                placeholder.warning(msg)
        st.session_state.input_counter += 1
        st.rerun()

    if end:
        T.process_turn(s, "!!")
        st.rerun()


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
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
