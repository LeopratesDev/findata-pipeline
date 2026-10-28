"""Dashboard Streamlit do FinData Pipeline (consome a API da aplicacao).

Executar:  streamlit run src/findata_pipeline/dashboard/app.py
Config:    API_BASE_URL (default http://localhost:8000), API_WRITE_TOKEN (opcional).

Interface profissional: navegacao com icones (streamlit-option-menu), tema
sobrio (.streamlit/config.toml), CSS para cartoes/tipografia e um template
Plotly consistente. A logica de consulta (client.py) e de formatacao
(format.py) fica em funcoes puras e testadas; app.py apenas orquestra a UI.
Importar este modulo NAO executa a UI (guardado por __main__).
"""
from __future__ import annotations

import datetime as dt
import io
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_option_menu import option_menu

from findata_pipeline.dashboard import format as fmt
from findata_pipeline.dashboard.client import ApiClient, ApiError

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
# URL da API acessivel pelo NAVEGADOR do usuario (links de download). Em Docker,
# API_BASE_URL aponta para a rede interna (http://api:8000), que o navegador nao
# resolve; API_PUBLIC_URL e o endereco no host. Default = API_BASE_URL (local).
API_PUBLIC_URL = os.environ.get("API_PUBLIC_URL", API_BASE_URL)
API_WRITE_TOKEN = os.environ.get("API_WRITE_TOKEN") or None

PAGES = ["Visao geral", "Graficos", "Historico", "Execucoes", "Relatorios", "Execucao manual"]
PAGE_ICONS = ["speedometer2", "graph-up", "table", "clock-history", "file-earmark-bar-graph", "play-circle"]

# Paleta
NAVY = "#0f2740"
ACCENT = "#1e6feb"

_CSS = """
<style>
:root { --fd-accent: #1e6feb; --fd-navy: #0f2740; --fd-border: #e6ebf2; --fd-muted: #6b7280; }
.block-container { padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1180px; }
h1, h2, h3 { color: #13233a; font-weight: 700; letter-spacing: -0.01em; }
section[data-testid="stSidebar"] { background-color: var(--fd-navy); }
section[data-testid="stSidebar"] * { color: #e8eef6; }
[data-testid="stHeader"] { background: transparent; }

/* Cartoes de indicador */
.fd-cards { display: flex; gap: 16px; flex-wrap: wrap; margin: 6px 0 4px; }
.fd-card {
  flex: 1 1 200px; background: #fff; border: 1px solid var(--fd-border);
  border-left: 4px solid var(--fd-accent); border-radius: 12px; padding: 16px 18px;
  box-shadow: 0 1px 2px rgba(16,39,64,.05);
}
.fd-card-label { font-size: .82rem; color: var(--fd-muted); font-weight: 600; text-transform: uppercase; letter-spacing: .03em; }
.fd-card-unit { color: var(--fd-accent); font-weight: 700; }
.fd-card-value { font-size: 2rem; font-weight: 700; color: #13233a; line-height: 1.15; margin-top: 4px; }
.fd-card-sub { font-size: .8rem; color: var(--fd-muted); margin-top: 6px; }

/* st.metric como cartao */
[data-testid="stMetric"] {
  background: #fff; border: 1px solid var(--fd-border); border-radius: 12px;
  padding: 12px 16px; box-shadow: 0 1px 2px rgba(16,39,64,.05);
}
[data-testid="stMetricValue"] { color: #13233a; }

/* Badge */
.fd-badge { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .78rem; font-weight: 600; }
.fd-ok { background: #e7f6ee; color: #13834a; }
.fd-off { background: #fdeaea; color: #c0392b; }

/* Rodape da sidebar */
.fd-brand-title { font-size: 1.25rem; font-weight: 800; color: #fff; margin: 4px 0 0; }
.fd-brand-sub { font-size: .78rem; color: #9db7d8; margin-bottom: 8px; }
hr { border-color: rgba(255,255,255,.12); }
</style>
"""

_DARK_CSS = """
<style>
.stApp, section[data-testid="stAppViewContainer"], .block-container { background-color: #0e1726; }
.stApp, .block-container p, .block-container span, .block-container label, .block-container li,
.stMarkdown, [data-testid="stWidgetLabel"] { color: #e6ebf4; }
h1, h2, h3 { color: #f1f5fb !important; }
.fd-card { background: #15213a; border-color: #24324d; }
.fd-card-value { color: #f1f5fb; }
.fd-card-label, .fd-card-sub { color: #9fb0c7; }
[data-testid="stMetric"] { background: #15213a; border-color: #24324d; }
[data-testid="stMetricValue"] { color: #f1f5fb; }
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * { color: #9fb0c7; }
[data-baseweb="select"] > div, [data-baseweb="input"] > div,
.stTextInput input, .stNumberInput input, .stDateInput input {
  background-color: #15213a !important; color: #e6ebf4 !important; border-color: #24324d !important;
}
[data-testid="stExpander"] { background: #15213a; border: 1px solid #24324d; border-radius: 12px; }
.fd-ok { background: #10371f; color: #8ff0b5; }
.fd-off { background: #3a1414; color: #ff9a9a; }
</style>
"""

PLOTLY_LAYOUT = dict(
    template="plotly_white",
    font=dict(family="sans-serif", color="#1f2a37", size=13),
    colorway=[ACCENT, "#16a34a", "#d97706"],
    margin=dict(l=48, r=24, t=56, b=44),
    hoverlabel=dict(bgcolor="white"),
    height=460,
)

# Barra de ferramentas do grafico (inclui o botao de baixar PNG).
PLOTLY_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
}

PERIOD_PRESETS = {"Ultimos 30 dias": 30, "Ultimos 90 dias": 90, "Ultimo ano": 365, "Tudo": None}

INDICATOR_HELP = {
    "BCB-SGS-12": "CDI — taxa diaria dos depositos interbancarios (% ao dia). Referencia de operacoes pos-fixadas (FIDC/CRA).",
    "BCB-SGS-432": "Selic meta — taxa basica de juros definida pelo Copom (% ao ano).",
    "BCB-SGS-433": "IPCA — variacao mensal da inflacao oficial (% no mes). Referencia de titulos indexados a inflacao (CRI/CRA).",
}


def _period_selector(key: str):
    """Seletor de periodo com presets + opcao personalizada. Retorna (start, end) em ISO ou None."""
    choice = st.radio("Periodo", list(PERIOD_PRESETS) + ["Personalizado"], horizontal=True, key=f"{key}_p")
    if choice == "Personalizado":
        c1, c2 = st.columns(2)
        start = c1.date_input("Data inicial", value=None, format="DD/MM/YYYY", key=f"{key}_s")
        end = c2.date_input("Data final", value=None, format="DD/MM/YYYY", key=f"{key}_e")
        return (start.isoformat() if start else None, end.isoformat() if end else None)
    days = PERIOD_PRESETS[choice]
    if days is None:
        return (None, None)
    return ((dt.date.today() - dt.timedelta(days=days)).isoformat(), None)


def _client() -> ApiClient:
    return ApiClient(API_BASE_URL, token=API_WRITE_TOKEN)


def _indicator_map(client: ApiClient) -> dict:
    return {i["series_id"]: i for i in client.get_indicators()}


def _page_header(title: str, caption: str = "") -> None:
    st.markdown(f"### {title}")
    if caption:
        st.caption(caption)


def _dark_enabled() -> bool:
    return bool(st.session_state.get("dark"))


def _style_chart(fig: go.Figure, title: str, y_title: str) -> go.Figure:
    layout = dict(PLOTLY_LAYOUT)
    if _dark_enabled():
        layout["template"] = "plotly_dark"
        layout["paper_bgcolor"] = "rgba(0,0,0,0)"
        layout["plot_bgcolor"] = "rgba(0,0,0,0)"
        layout["font"] = dict(family="sans-serif", color="#e6ebf4", size=13)
    fig.update_layout(title=title, xaxis_title="Data de referencia", yaxis_title=y_title, **layout)
    grid = "#24324d" if _dark_enabled() else "#eef2f7"
    fig.update_xaxes(gridcolor=grid)
    fig.update_yaxes(gridcolor=grid)
    return fig


# --------------------------------------------------------------- paginas
def page_overview(client: ApiClient) -> None:
    online = client.health_ok()
    badge = '<span class="fd-badge fd-ok">API online</span>' if online else '<span class="fd-badge fd-off">API offline</span>'
    st.markdown(f"### Visao geral &nbsp; {badge}", unsafe_allow_html=True)
    if not online:
        st.error("API indisponivel. Verifique se o servico esta no ar.")
        return

    try:
        with st.spinner("Consultando a API..."):
            status = client.get_status()
            indicators = client.get_indicators()
    except ApiError as exc:
        st.error(f"Erro ao consultar a API: {exc.detail}")
        return

    st.caption(f"Fonte: BCB-SGS · Registros vigentes: {status['observations_count']}")

    if status["observations_count"] == 0:
        st.info("Ainda nao ha dados coletados. Faca a primeira coleta para popular o "
                "dashboard (leva alguns segundos).")
        if st.button("Coletar agora", type="primary"):
            try:
                resp = client.create_run()
                st.success(f"Coleta iniciada (ID {resp['run_id']}). Aguarde alguns "
                           "segundos e recarregue a pagina.")
            except ApiError as exc:
                if exc.status_code == 409:
                    st.warning("Ja existe uma execucao em andamento.")
                elif exc.status_code == 401:
                    st.error("Operacao protegida por token (API_WRITE_TOKEN). Use a "
                             "pagina de execucao manual ou configure o token.")
                else:
                    st.error(f"Falha ao iniciar a coleta: {exc.detail}")
        return

    # Cartoes dos indicadores (HTML proprio para um visual coeso)
    cards = []
    for ind in indicators:
        try:
            latest = client.get_latest(ind["series_id"])
        except ApiError:
            latest = {"has_data": False}
        if latest.get("has_data"):
            obs = latest["observation"]
            value = fmt.format_value(obs["value"])
            sub = f"Ref.: {fmt.format_date(obs['reference_date'])}"
        else:
            value, sub = "—", "sem dados"
        cards.append(
            f'<div class="fd-card"><div class="fd-card-label">{ind["name"]} '
            f'<span class="fd-card-unit">{fmt.unit_label(ind["unit"])}</span></div>'
            f'<div class="fd-card-value">{value}</div>'
            f'<div class="fd-card-sub">{sub}</div></div>'
        )
    st.markdown(f'<div class="fd-cards">{"".join(cards)}</div>', unsafe_allow_html=True)

    with st.expander("O que significam os indicadores?"):
        for ind in indicators:
            st.markdown(f"- **{ind['name']}** — {INDICATOR_HELP.get(ind['series_id'], '')}")

    st.write("")
    c1, c2, c3 = st.columns(3)
    c1.metric("Ultima coleta", fmt.format_datetime(status.get("last_successful_collection")) or "—",
              help="Quando a ultima coleta bem-sucedida terminou.")
    last_run = status.get("last_run")
    c2.metric("Ultima execucao", fmt.status_label(last_run["status"]) if last_run else "—",
              help="Estado da execucao mais recente do pipeline.")
    c3.metric("Registros armazenados", status["observations_count"],
              help="Total de observacoes vigentes no banco.")


def page_charts(client: ApiClient) -> None:
    _page_header("Graficos", "Evolucao historica por indicador — cada serie com a sua unidade.")
    try:
        indicators = _indicator_map(client)
    except ApiError as exc:
        st.error(f"Erro ao consultar a API: {exc.detail}")
        return

    sid = st.selectbox("Indicador", list(indicators), format_func=lambda s: indicators[s]["name"])
    start, end = _period_selector("charts")
    show_ma = st.checkbox("Media movel (7 periodos)")

    try:
        with st.spinner("Consultando o historico..."):
            resp = client.get_history(sid, start=start, end=end, limit=5000)
    except ApiError as exc:
        st.error(f"Erro ao consultar o historico: {exc.detail}")
        return

    chart = fmt.history_to_chart(resp["items"])
    if not chart["dates"]:
        st.info("Nenhum dado para o periodo selecionado.")
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=chart["dates"], y=chart["values"], mode="lines", name=indicators[sid]["name"],
        line=dict(color=ACCENT, width=2), fill="tozeroy", fillcolor="rgba(30,111,235,.08)",
    ))
    if show_ma:
        fig.add_trace(go.Scatter(
            x=chart["dates"], y=fmt.moving_average(chart["values"], 7),
            mode="lines", name="Media movel (7)", line=dict(color="#d97706", width=2, dash="dot"),
        ))
    _style_chart(fig, f"{indicators[sid]['name']} — evolucao", fmt.unit_label(indicators[sid]["unit"]))
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
    st.caption("Dica: passe o mouse para ver os valores; use o icone da camera para baixar o grafico em PNG.")
    st.caption(
        "Series exibidas separadamente, respeitando a unidade e a periodicidade de cada uma. "
        "Nao combinamos unidades diferentes no mesmo eixo."
    )


def page_history(client: ApiClient) -> None:
    _page_header("Historico", "Tabela pesquisavel dos registros, com exportacao em CSV.")
    try:
        indicators = _indicator_map(client)
    except ApiError as exc:
        st.error(f"Erro ao consultar a API: {exc.detail}")
        return

    sid = st.selectbox("Indicador", list(indicators), format_func=lambda s: indicators[s]["name"])
    start, end = _period_selector("hist")
    include_history = st.checkbox("Incluir versoes anteriores (revisoes)")

    limit = st.slider("Registros por pagina", 10, 500, 100, step=10)
    page = st.number_input("Pagina", min_value=1, value=1, step=1)
    offset = (int(page) - 1) * limit

    try:
        with st.spinner("Consultando o historico..."):
            resp = client.get_history(
                sid, start=start, end=end, limit=limit, offset=offset,
                include_history=include_history,
            )
    except ApiError as exc:
        st.error(f"Erro ao consultar o historico: {exc.detail}")
        return

    items = resp["items"]
    if not items:
        st.info("Nenhum registro para o filtro selecionado.")
        return

    st.caption(f"{resp['total']} registros no total · exibindo {resp['count']} (pagina {page}).")
    rows = [
        {
            "Indicador": indicators[sid]["name"], "Codigo": indicators[sid]["sgs_code"],
            "Data de referencia": fmt.format_date(it["reference_date"]), "Valor": it["value"],
            "Unidade": fmt.unit_label(it["unit"]), "Fonte": it["source"],
            "Coletado em": fmt.format_datetime(it["collected_at"]), "Versao": it["version"],
            "Vigente": "sim" if it["is_current"] else "nao",
        }
        for it in items
    ]
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    st.download_button("Exportar CSV (filtro atual)", data=buffer.getvalue(),
                       file_name=f"historico_{sid}.csv", mime="text/csv")


def page_runs(client: ApiClient) -> None:
    _page_header("Execucoes do pipeline", "Historico das coletas, com detalhe e motivos de rejeicao.")
    try:
        runs = client.list_runs(limit=50)["items"]
    except ApiError as exc:
        st.error(f"Erro ao consultar execucoes: {exc.detail}")
        return
    if not runs:
        st.info("Nenhuma execucao registrada ainda.")
        return

    table = [
        {
            "ID": r["id"], "Inicio": fmt.format_datetime(r["started_at"]),
            "Status": fmt.status_label(r["status"]), "Extraidos": r["extracted"],
            "Validos": r["valid"], "Rejeitados": r["rejected"], "Inseridos": r["inserted"],
            "Duplicados": r["duplicates"], "Revisoes": r["revisions"],
            "Duracao": fmt.format_duration(r["duration_seconds"]), "Origem": r["trigger"] or "—",
        }
        for r in runs
    ]
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)

    run_id = st.selectbox("Ver detalhe da execucao", [r["id"] for r in runs])
    detail = client.get_run(int(run_id))
    category = fmt.status_category(detail["status"])
    msg = f"Execucao {detail['id']} — {fmt.status_label(detail['status'])}"
    {"success": st.success, "warning": st.warning, "error": st.error, "info": st.info}[category](msg)
    if detail.get("error_detail"):
        st.error(f"Erro: {detail['error_detail']}")
    rejections = detail.get("rejections", [])
    if rejections:
        st.subheader("Rejeicoes")
        st.dataframe(pd.DataFrame(rejections), use_container_width=True, hide_index=True)
    else:
        st.caption("Sem rejeicoes nesta execucao.")


def page_reports(client: ApiClient) -> None:
    _page_header("Relatorios", "Relatorios gerados pelo pipeline (JSON).")
    try:
        reports = client.list_reports()
    except ApiError as exc:
        st.error(f"Erro ao consultar relatorios: {exc.detail}")
        return
    if not reports:
        st.info("Nenhum relatorio gerado ainda. Rode uma coleta para gerar um.")
        return
    for rep in reports:
        c1, c2 = st.columns([3, 1])
        c1.write(f"**{rep['report_id']}** · {rep['size_bytes']} bytes · {fmt.format_datetime(rep['modified_at'])}")
        # URL publica (host), nao a interna da rede Docker.
        c2.link_button("Baixar", f"{API_PUBLIC_URL}/api/v1/reports/{rep['report_id']}/download")


def page_manual_run(client: ApiClient) -> None:
    _page_header("Execucao manual", "Dispare uma nova coleta e acompanhe o status.")
    st.info("A coleta roda em segundo plano e pode levar alguns segundos. O status fica rastreavel abaixo.")

    confirm = st.checkbox("Confirmo que desejo iniciar uma nova coleta")
    if st.button("Solicitar nova coleta", type="primary", disabled=not confirm):
        try:
            resp = client.create_run()
            st.session_state["last_run_id"] = resp["run_id"]
            st.success(f"Execucao aceita. ID: {resp['run_id']} (status inicial: {resp['status']}).")
        except ApiError as exc:
            if exc.status_code == 409:
                st.warning("Ja existe uma execucao em andamento. Aguarde terminar.")
            elif exc.status_code == 401:
                st.error("Operacao protegida: token de escrita ausente ou invalido.")
            else:
                st.error(f"Falha ao solicitar execucao: {exc.detail}")

    run_id = st.session_state.get("last_run_id")
    if run_id:
        st.divider()
        st.write(f"Acompanhando execucao **{run_id}**")
        st.button("Atualizar status")  # o rerun refaz a consulta abaixo
        try:
            status = client.get_run_status(int(run_id))
            st.write(f"Status atual: **{fmt.status_label(status['status'])}**")
            if status.get("error_detail"):
                st.error(status["error_detail"])
        except ApiError as exc:
            st.error(f"Erro ao consultar status: {exc.detail}")


def render() -> None:
    st.set_page_config(page_title="FinData Pipeline", page_icon=":bar_chart:", layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown('<div class="fd-brand-title">FinData Pipeline</div>', unsafe_allow_html=True)
        st.markdown('<div class="fd-brand-sub">Inteligencia de Indicadores Financeiros</div>', unsafe_allow_html=True)
        page = option_menu(
            menu_title=None,
            options=PAGES,
            icons=PAGE_ICONS,
            default_index=0,
            styles={
                "container": {"background-color": NAVY, "padding": "4px 0"},
                "icon": {"color": "#9db7d8", "font-size": "1rem"},
                "nav-link": {
                    "color": "#d7e2f0", "font-size": "0.95rem", "text-align": "left",
                    "margin": "2px 6px", "border-radius": "8px", "--hover-color": "#16314f",
                },
                "nav-link-selected": {"background-color": ACCENT, "color": "white", "font-weight": "600"},
            },
        )
        st.markdown("<hr/>", unsafe_allow_html=True)
        st.toggle("Modo escuro", key="dark")
        st.caption(f"API: {API_BASE_URL}")

    if _dark_enabled():
        st.markdown(_DARK_CSS, unsafe_allow_html=True)

    client = _client()
    dispatch = {
        "Visao geral": page_overview,
        "Graficos": page_charts,
        "Historico": page_history,
        "Execucoes": page_runs,
        "Relatorios": page_reports,
        "Execucao manual": page_manual_run,
    }
    dispatch[page](client)


if __name__ == "__main__":
    render()
