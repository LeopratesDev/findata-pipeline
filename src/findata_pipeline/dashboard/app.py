"""Dashboard Streamlit do FinData Pipeline (consome a API da aplicacao).

Executar:  streamlit run src/findata_pipeline/dashboard/app.py
Config:    API_BASE_URL (default http://localhost:8000), API_WRITE_TOKEN (opcional).

A UI e fina: toda consulta passa por ApiClient (client.py) e toda formatacao
por funcoes puras (format.py), ambas testadas. Importar este modulo NAO
executa a UI (guardado por __main__), para permitir teste de importacao.
"""
from __future__ import annotations

import io
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from findata_pipeline.dashboard import format as fmt
from findata_pipeline.dashboard.client import ApiClient, ApiError

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
# URL da API acessivel pelo NAVEGADOR do usuario (links de download). Em Docker,
# API_BASE_URL aponta para a rede interna (http://api:8000), que o navegador nao
# resolve; API_PUBLIC_URL e o endereco no host. Default = API_BASE_URL (local).
API_PUBLIC_URL = os.environ.get("API_PUBLIC_URL", API_BASE_URL)
API_WRITE_TOKEN = os.environ.get("API_WRITE_TOKEN") or None

PAGES = ["Visao geral", "Graficos", "Historico", "Execucoes", "Relatorios", "Execucao manual"]

_CSS = """
<style>
.block-container { padding-top: 2rem; max-width: 1100px; }
h1, h2, h3 { color: #1f3b57; }
section[data-testid="stSidebar"] { background-color: #0f2a43; }
section[data-testid="stSidebar"] * { color: #e8eef4; }
</style>
"""


def _client() -> ApiClient:
    return ApiClient(API_BASE_URL, token=API_WRITE_TOKEN)


def _indicator_map(client: ApiClient) -> dict:
    return {i["series_id"]: i for i in client.get_indicators()}


# --------------------------------------------------------------- paginas
def page_overview(client: ApiClient) -> None:
    st.header("Visao geral")
    if not client.health_ok():
        st.error("API indisponivel. Verifique se o servico esta no ar.")
        return

    try:
        status = client.get_status()
        indicators = client.get_indicators()
    except ApiError as exc:
        st.error(f"Erro ao consultar a API: {exc.detail}")
        return

    st.caption(f"Fonte: BCB-SGS · Registros vigentes: {status['observations_count']}")

    cols = st.columns(len(indicators))
    for col, ind in zip(cols, indicators):
        with col:
            try:
                latest = client.get_latest(ind["series_id"])
            except ApiError:
                latest = {"has_data": False}
            if latest.get("has_data"):
                obs = latest["observation"]
                col.metric(
                    label=f"{ind['name']} ({fmt.unit_label(ind['unit'])})",
                    value=fmt.format_value(obs["value"]),
                )
                col.caption(f"Ref.: {fmt.format_date(obs['reference_date'])}")
            else:
                col.metric(label=f"{ind['name']}", value="sem dados")

    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Ultima coleta", fmt.format_datetime(status.get("last_successful_collection")) or "—")
    last_run = status.get("last_run")
    c2.metric("Ultima execucao", fmt.status_label(last_run["status"]) if last_run else "—")
    c3.metric("Registros armazenados", status["observations_count"])


def page_charts(client: ApiClient) -> None:
    st.header("Graficos")
    try:
        indicators = _indicator_map(client)
    except ApiError as exc:
        st.error(f"Erro ao consultar a API: {exc.detail}")
        return

    sid = st.selectbox(
        "Indicador", list(indicators), format_func=lambda s: indicators[s]["name"]
    )
    c1, c2 = st.columns(2)
    start = c1.date_input("Data inicial", value=None, format="DD/MM/YYYY")
    end = c2.date_input("Data final", value=None, format="DD/MM/YYYY")

    try:
        resp = client.get_history(
            sid,
            start=start.isoformat() if start else None,
            end=end.isoformat() if end else None,
            limit=1000,
        )
    except ApiError as exc:
        st.error(f"Erro ao consultar o historico: {exc.detail}")
        return

    chart = fmt.history_to_chart(resp["items"])
    if not chart["dates"]:
        st.info("Nenhum dado para o periodo selecionado.")
        return

    unit = indicators[sid]["unit"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=chart["dates"], y=chart["values"], mode="lines", name=indicators[sid]["name"]))
    fig.update_layout(
        title=f"{indicators[sid]['name']} — evolucao",
        xaxis_title="Data de referencia",
        yaxis_title=fmt.unit_label(unit),
        margin=dict(l=40, r=20, t=50, b=40),
        height=460,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Series exibidas separadamente, respeitando a unidade e a periodicidade de cada uma. "
        "Nao combinamos unidades diferentes no mesmo eixo."
    )


def page_history(client: ApiClient) -> None:
    st.header("Historico")
    try:
        indicators = _indicator_map(client)
    except ApiError as exc:
        st.error(f"Erro ao consultar a API: {exc.detail}")
        return

    sid = st.selectbox("Indicador", list(indicators), format_func=lambda s: indicators[s]["name"])
    c1, c2, c3 = st.columns(3)
    start = c1.date_input("Data inicial", value=None, format="DD/MM/YYYY")
    end = c2.date_input("Data final", value=None, format="DD/MM/YYYY")
    include_history = c3.checkbox("Incluir versoes anteriores (revisoes)")

    limit = st.slider("Registros por pagina", 10, 500, 100, step=10)
    page = st.number_input("Pagina", min_value=1, value=1, step=1)
    offset = (int(page) - 1) * limit

    try:
        resp = client.get_history(
            sid,
            start=start.isoformat() if start else None,
            end=end.isoformat() if end else None,
            limit=limit,
            offset=offset,
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
            "Indicador": indicators[sid]["name"],
            "Codigo": indicators[sid]["sgs_code"],
            "Data de referencia": fmt.format_date(it["reference_date"]),
            "Valor": it["value"],
            "Unidade": fmt.unit_label(it["unit"]),
            "Fonte": it["source"],
            "Coletado em": fmt.format_datetime(it["collected_at"]),
            "Versao": it["version"],
            "Vigente": "sim" if it["is_current"] else "nao",
        }
        for it in items
    ]
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    st.download_button(
        "Exportar CSV (filtro atual)",
        data=buffer.getvalue(),
        file_name=f"historico_{sid}.csv",
        mime="text/csv",
    )


def page_runs(client: ApiClient) -> None:
    st.header("Execucoes do pipeline")
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
            "ID": r["id"],
            "Inicio": fmt.format_datetime(r["started_at"]),
            "Status": fmt.status_label(r["status"]),
            "Extraidos": r["extracted"],
            "Validos": r["valid"],
            "Rejeitados": r["rejected"],
            "Inseridos": r["inserted"],
            "Duplicados": r["duplicates"],
            "Revisoes": r["revisions"],
            "Duracao": fmt.format_duration(r["duration_seconds"]),
            "Origem": r["trigger"] or "—",
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
    st.header("Relatorios")
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
        # URL publica (host), nao a interna da rede Docker, pois o clique
        # acontece no navegador do usuario.
        c2.link_button("Baixar", f"{API_PUBLIC_URL}/api/v1/reports/{rep['report_id']}/download")


def page_manual_run(client: ApiClient) -> None:
    st.header("Execucao manual")
    st.info("A coleta roda em segundo plano e pode levar alguns segundos. O status fica rastreavel abaixo.")

    confirm = st.checkbox("Confirmo que desejo iniciar uma nova coleta")
    if st.button("Solicitar nova coleta", disabled=not confirm):
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
        if st.button("Atualizar status"):
            pass  # o rerun refaz a consulta abaixo
        try:
            status = client.get_run_status(int(run_id))
            st.write(f"Status atual: **{fmt.status_label(status['status'])}**")
            if status.get("error_detail"):
                st.error(status["error_detail"])
        except ApiError as exc:
            st.error(f"Erro ao consultar status: {exc.detail}")


def render() -> None:
    st.set_page_config(page_title="FinData Pipeline", page_icon=None, layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)

    with st.sidebar:
        st.title("FinData Pipeline")
        st.caption("Plataforma de Inteligencia de Indicadores Financeiros")
        page = st.radio("Navegacao", PAGES, label_visibility="collapsed")
        st.divider()
        st.caption(f"API: {API_BASE_URL}")

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
