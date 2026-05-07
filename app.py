"""
Tutor d'equacions lineals — UI Streamlit.

Per executar:
    export ANTHROPIC_API_KEY=sk-ant-...
    streamlit run app.py

L'estat de la sessió viu a st.session_state. La lògica viu a tutor.py.
"""

import os
import streamlit as st

import problems as PB
import tutor as T

st.set_page_config(
    page_title="Tutor IA — equacions lineals",
    layout="centered",
)


# ------------------------------------------------------------
# Inicialització
# ------------------------------------------------------------
def init_state():
    if "session" not in st.session_state:
        st.session_state.session = None
    if "input_counter" not in st.session_state:
        st.session_state.input_counter = 0


def start_session(problem_id: str):
    st.session_state.session = T.new_session_state(problem_id)
    st.session_state.input_counter += 1  # força reset del text_input


# ------------------------------------------------------------
# Sidebar: selecció de problema i estat
# ------------------------------------------------------------
def render_sidebar():
    with st.sidebar:
        st.markdown("### Tutor IA — equacions lineals")
        st.caption("Pilot 2n d'ESO — mode professor")

        if not os.environ.get("ANTHROPIC_API_KEY"):
            st.error("Falta ANTHROPIC_API_KEY.")
            st.stop()

        st.markdown("---")
        st.markdown("**Selecciona problema**")

        for prob in PB.list_problems():
            label = f"N{prob['nivell']} · {prob['familia']} · {prob['equacio_text']}"
            if st.button(label, key=f"btn_{prob['id']}", use_container_width=True):
                start_session(prob["id"])
                st.rerun()

        st.markdown("---")

        # Senyals d'escapament
        st.markdown("**Senyals especials**")
        st.markdown(
            "- `?` — demanar pista\n"
            "- `!text` — discrepància, continuar\n"
            "- `!!` — sortir de la sessió"
        )

        st.markdown("---")
        # Mostra de l'estat agregat
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


# ------------------------------------------------------------
# Pantalla central: enunciat + cadena d'equacions + input
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

    # Capçalera del problema
    st.markdown(f"### Problema {s['problem_id']}")
    st.markdown(f"**Nivell {s['problem']['nivell']} · {s['problem']['tema']}**")
    st.markdown(
        f"**Resol:** `{s['problem']['equacio_text']}`"
    )
    st.markdown("---")

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
        st.markdown("---")
        for m in s["messages"]:
            _render_message(m)

    # Si la sessió està tancada, no acceptem més input
    if s["verdict_final"] is not None:
        st.markdown("---")
        if s["verdict_final"] == "resolt":
            st.success("Sessió completada amb èxit.")
        elif s["verdict_final"] == "abandonat":
            st.info("Sessió tancada per l'alumne.")
        elif s["verdict_final"] == "suspes_us_inadequat":
            st.error("Sessió suspesa per ús inadequat.")
        _render_trace(s)
        return

    # Input
    st.markdown("---")
    if s["active_prereq"] is not None:
        prereq = PB.get_prerequisite(s["active_prereq"])
        st.markdown(f"**Pregunta del prerequisit:** {prereq['question']}")

    key = f"input_{st.session_state.input_counter}"
    raw = st.text_input("La teva resposta:", key=key, placeholder="ex: 3x = 15")

    cols = st.columns([1, 1, 4])
    with cols[0]:
        submit = st.button("Enviar", type="primary")
    with cols[1]:
        end = st.button("Sortir (!!)")

    if submit and raw:
        with st.spinner("Avaluant..."):
            T.process_turn(s, raw)
        st.session_state.input_counter += 1
        st.rerun()

    if end:
        T.process_turn(s, "!!")
        st.rerun()


# ------------------------------------------------------------
# Helpers de presentació
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
