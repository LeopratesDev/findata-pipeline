# Roadmap e aceitação

Cada etapa é uma **promessa** com **critérios de aceitação** objetivos, um
**estado** e a **prova** correspondente. Nada é marcado como concluído sem
prova (ver [../process/DELIVERY.md](../process/DELIVERY.md)).

Legenda de estado: ✅ provada · 🔄 em andamento · ⏳ pendente de prova (observador
indisponível).

---

## v1 — Pipeline-base (CLI)

**Promessa:** coletar, validar, versionar e persistir CDI, Selic e IPCA do BCB,
de forma idempotente e auditável, via linha de comando.

**Aceitação:** coleta da API SGS; validação ciente da série com `Decimal`;
SQLite idempotente (índice parcial único por versão vigente); revisões
versionadas; relatórios e alertas; execução agendada; testes offline + teste
de contrato.

**Estado:** ✅ provada.
**Prova:** 41 testes offline + 3 de contrato; CI verde; execução real com 628
observações coletadas do BCB.

---

## v2 — Plataforma integrada (API + Dashboard + Docker)

Escopo fixo (decisão tomada): **SQLite + FastAPI + Streamlit + Docker Compose**.
Sem PostgreSQL, Redis, Celery, Kafka, Kubernetes ou microserviços.

### Etapa 2 — Camada de serviços + API REST

**Promessa:** expor os dados persistidos por uma API REST documentada, sem
reimplementar regra de negócio.

**Aceitação:** `/health`, `/ready`, `/status`; indicadores (lista/latest/history
paginado); execuções (lista/detalhe/POST 202/status); relatórios (download
seguro, anti path-traversal); execução assíncrona com controle de concorrência
(409); migração aditiva de `runs`; `value` como string decimal; Swagger.

**Estado:** ✅ provada.
**Prova:** 21 testes de API (62 no total) verdes; CI verde; smoke com Uvicorn
(`/openapi.json` lista os 11 paths; `/health`, `/ready`, `/indicators`
respondem). Commit `feat(api): Etapa 2`.

### Etapa 3 — Dashboard

**Promessa:** visualizar os indicadores e operar o pipeline por uma interface
em pt-BR que consome **apenas a API** da aplicação.

**Aceitação:** 6 páginas (visão geral, gráficos, histórico, execuções,
relatórios, execução manual); unidades e datas corretas; gráficos Plotly sem
misturar unidades; filtros e paginação; export CSV; estados de carregando/
sucesso/sem dados/erro; lógica de consulta e formatação em funções puras
testadas.

**Estado:** ✅ provada.
**Prova:** 14 testes de dashboard (76 no total) verdes; CI verde; smoke ao vivo
(API + dashboard) com 628 observações reais — cartões com unidade/data corretas
(CDI 0,050788 % a.d., Selic 13,75 % a.a., IPCA 0,82 % a.m.) e gráfico com eixo
em % a.d. Commit `feat(dashboard): Etapa 3`.

### Etapa 4 — Docker e Docker Compose

**Promessa:** subir a plataforma inteira com **um comando**
(`docker compose up --build`), com persistência do SQLite entre recriações.

**Aceitação:** Dockerfile(s) com imagem Python versionada, usuário não-root,
`.dockerignore`; Compose com api + dashboard, rede interna, volume persistente
para o SQLite (caminho consistente), health checks, `depends_on` por saúde,
variáveis de ambiente, portas documentadas, sem expor o banco; dados persistem
após `docker compose down` e novo `up`.

**Estado:** ✅ provada.
**Prova:** `docker compose up --build` sobe `api` (healthcheck → `Healthy`) e
`dashboard` (que só inicia após a api estar saudável). Smoke pelos containers:
`/health` ok, `/status` ok, dashboard HTTP 200. Coleta disparada pela API
dentro do container → **209 observações** do BCB. **Persistência:** após
`docker compose down` + `up` (sem remover volume), os dados permaneceram (209).
Ver jornada **J5** em [../jpd/JOURNEYS.md](../jpd/JOURNEYS.md).

### Etapa 5 — Integração final + README

**Promessa:** documentação que permite outra pessoa reproduzir tudo; integração
ponta a ponta verificada (persistência, consulta, execução controlada).

**Estado:** ✅ provada.
**Prova:** README v2 reescrito (arquitetura + diagrama de componentes, execução
local e Docker, exemplos de requisição/resposta **reais**, testes, persistência/
backup/restauração, segurança/limitações). Integração ponta a ponta verificada
na stack Docker: a coleta via API gera relatório listado em `/api/v1/reports`
(`report_20261028_162524.json`), a consulta por indicador/histórico retorna
dados reais, e a persistência resistiu a `down`+`up` (209 observações). Os
comandos do README foram executados nesta sessão.
