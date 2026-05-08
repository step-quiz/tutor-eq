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

      /* Amaga el petit ajut "Press Enter to submit form" que Streamlit
         posa sota els text_input dins de forms. Aran no necessita
         aquesta indicació tècnica — el botó Enviar i el comportament
         d'Enter ja són evidents. */
      [data-testid="InputInstructions"] { display: none !important; }
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


def start_session(problem_id: str):
    st.session_state.session = T.new_session_state(problem_id)
    st.session_state.input_counter += 1
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
            # Estat intern de la sessió (im2): comptadors de torns,
            # pistes, retrocessos, etc. És informació meta orientada al
            # desenvolupador. Per a l'Aran no aporta res i la distreu.
            if debug:
                st.markdown("**Estat de la sessió**")
                st.text(f"Torns:           {len(s['history']) - 1}")
                st.text(f"Pistes:          {len(s['hints_requested'])}")
                st.text(f"Estancaments:    {s['stagnation_total']}")
                st.text(f"Retrocessos:     {s['backtrack_count']}")
                st.text(f"Avisos no-math:  {s['inappropriate_warnings']}")
                if s["active_prereq"]:
                    st.text(f"En prerequisit:  {s['active_prereq']}")

            # Botó Sortir (visible sempre que hi hagi sessió activa).
            if s["verdict_final"] is None:
                if st.button("Sortir de la sessió (!!)",
                             key="exit_btn",
                             use_container_width=True):
                    T.process_turn(s, "!!")
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


def _run_test_and_store(problem_id: str):
    """Executa el test exhaustiu i guarda els resultats a session_state."""
    progress_box = st.empty()

    def on_progress(r_idx, n_rounds, i_idx, n_inputs):
        progress_box.info(
            f"Test exhaustiu: ronda {r_idx}/{n_rounds}, "
            f"input {i_idx}/{n_inputs}..."
        )

    # Mesurem el delta de cost del test: agafem el sumari abans i després
    # i la diferència ens dóna el que ha consumit aquesta execució.
    summary_before = api_logger.summarize_session(L.get_session_id())
    with st.spinner("Executant test exhaustiu (pot trigar uns minuts)..."):
        results = T.run_exhaustive_test(problem_id, on_progress=on_progress)
    summary_after = api_logger.summarize_session(L.get_session_id())
    progress_box.empty()
    st.session_state.test_results = results
    st.session_state.test_problem_id = problem_id
    st.session_state.test_cost_delta = {
        "calls": summary_after["calls_total"] - summary_before["calls_total"],
        "tokens_in": summary_after["tokens_input"] - summary_before["tokens_input"],
        "tokens_out": summary_after["tokens_output"] - summary_before["tokens_output"],
        "cost_usd": round(
            summary_after["cost_usd"] - summary_before["cost_usd"], 6
        ),
    }


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
        # Rastre JSON: només en mode debug. Per a l'alumne és sorollós i
        # exposa l'estructura interna que no necessita.
        if _is_debug_mode():
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
    # IMPORTANT: clear_on_submit=False. Si el posem a True, el text que
    # l'alumne ha escrit desapareix immediatament en clicar Enter, abans
    # que el sistema acabi d'avaluar-lo (typically ~0.5-2s amb el thinking
    # model). Això crea una sensació desorientadora ("on ha anat el meu
    # text?"). Amb False, el text roman al camp durant tota l'avaluació
    # i només es buida quan el rerun final renderitza un nou camp (gràcies
    # a `input_counter` que canvia el key del widget).
    with st.form(key=key_form, clear_on_submit=False):
        # `autocomplete="off"` ja s'aplica també des del JS injectat al cap
        # de l'app (juntament amb autocorrect / autocapitalize / spellcheck
        # i un name aleatori). El passem aquí com a defensa redundant per
        # si el script no s'arriba a executar.
        raw = st.text_input(
            "La teva resposta:",
            key=key_in,
            autocomplete="off",
        )
        submit = st.form_submit_button("Enviar", type="primary")

    if submit and raw:
        st.session_state.retry_messages = []
        # Inclou el text de l'alumne dins del missatge del spinner perquè
        # vegi clarament què s'està avaluant en cada moment.
        suffix = (" (pot trigar uns segons mentre el sistema raona)"
                  if "pro" in L.MODEL.lower() else "")
        spinner_text = f"Avaluant «{raw}»...{suffix}"
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
        # ha resolt una tasca paral·lela, no un pas de l'equació original.
        st.success(f"✓ {text}")
    elif kind == "prereq_failed":
        # Caixa auxiliar de "fracàs al prereq". Persistent al viewport
        # (a diferència del missatge dins del panell del prereq, que es
        # tanca). Amb l'explicació de la resposta correcta.
        st.warning(f"✗ {text}")
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
    render_sidebar()
    render_main()


if __name__ == "__main__":
    main()
