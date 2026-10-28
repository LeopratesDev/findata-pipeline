# Jornadas (desenvolvimento guiado por provas)

Uma **jornada** é um fluxo do usuário ponta a ponta. Ela só está **provada**
quando passa na sua última execução, com um observador real. Abaixo, cada
jornada com os seus passos e a prova atual.

Legenda: ✅ provada · ⏳ pendente de prova.

---

## J1 — Ver o valor atual de um indicador ✅

**Passos:** abrir o dashboard → página *Visão geral* → ler o último valor de
CDI/Selic/IPCA com a unidade e a data de referência corretas.
**Observador:** testes + smoke ao vivo.
**Prova:** `test_api::test_latest_returns_string_value`,
`test_api::test_status_summary`; smoke com 628 observações reais (cartões
corretos). O `value` chega como **string** (precisão preservada).

## J2 — Consultar histórico filtrado e exportar ✅

**Passos:** página *Histórico* → escolher indicador, datas e paginação →
ver a tabela → exportar CSV com o filtro atual.
**Observador:** testes + funções puras.
**Prova:** `test_api::test_history_pagination`,
`test_api::test_history_invalid_date_422`, `test_dashboard` (formatação e
conversão); paginação servida pela API.

## J3 — Disparar uma coleta manual com controle de concorrência ✅

**Passos:** página *Execução manual* → confirmar → `POST /runs` (202 com
`run_id`) → acompanhar o status → uma segunda tentativa simultânea é recusada
(409).
**Observador:** testes da API e do runner.
**Prova:** `test_api::test_create_run_202_and_completes`,
`test_api::test_create_run_conflict_409`,
`test_api::test_create_run_requires_token_when_configured`.

## J4 — Baixar um relatório com segurança ✅

**Passos:** página *Relatórios* → listar → baixar (JSON/CSV) via API, sem
permitir caminhos arbitrários.
**Observador:** testes da API.
**Prova:** `test_api::test_reports_list_and_download`,
`test_api::test_report_download_bad_suffix_400`,
`test_api::test_resolve_report_path_blocks_traversal`.

## J5 — Subir a plataforma inteira com um comando ✅

**Passos:** `docker compose up --build` → API em `http://localhost:8000`
(Swagger em `/docs`) e dashboard em `http://localhost:8501`, falando pela rede
interna → dados persistem após `docker compose down` e novo `up`.
**Observador:** daemon do Docker.
**Prova:** `docker compose up --build` deixou `api` em `Healthy` e o
`dashboard` só iniciou após a saúde da api (`depends_on` por condição); smoke
pelos containers (`/health` ok, dashboard HTTP 200); coleta via API dentro do
container (**209 observações**); **persistência** confirmada — após
`docker compose down` + `up`, os dados permaneceram (209).

## J6 — Reproduzir o projeto a partir da documentação ✅*

**Passos:** seguindo o README, subir a plataforma e confirmar os dados.
**Observador:** execução dos comandos documentados (nesta sessão). A
reprodução por **outra pessoa** é o teste final no mundo real.
**Prova:** todos os comandos do README foram executados e funcionaram —
pipeline (CLI), API (Uvicorn), dashboard (Streamlit) e `docker compose up
--build`; a coleta via API gerou relatório; a persistência foi confirmada.
\*Asterisco: o observador "outra pessoa" não foi exercido; o conteúdo
documentado, sim.
