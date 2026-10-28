# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [2.0.0] — Plataforma integrada
### Adicionado
- **API REST (FastAPI)** reutilizando o pipeline: indicadores (lista/latest/
  history paginado), execucoes (lista/detalhe/POST 202/status), relatorios
  (download seguro), saude (`/health`, `/ready`, `/status`) e Swagger.
- Execucao assincrona da coleta (ThreadPoolExecutor + lock) com conflito 409;
  migracao aditiva da tabela `runs`.
- **Dashboard (Streamlit + Plotly)** consumindo a API: visao geral, graficos,
  historico (filtros, paginacao, CSV), execucoes, relatorios e execucao manual.
- Interface profissional: `streamlit-option-menu`, tema sobrio, cartoes,
  estado vazio guiado, presets de periodo, tooltips, media movel e download PNG.
- **Docker Compose** (api + dashboard), volume persistente, health checks.
- Portoes de qualidade: `ruff`, `mypy` e cobertura no CI; `requirements-dev`.
- Documentacao: `docs/` (INDEX, process, product, journeys), LICENSE,
  CONTRIBUTING, CHANGELOG.

## [1.0.0] — Pipeline-base (CLI)
### Adicionado
- Coleta da API SGS do BCB (CDI, Selic, IPCA), validacao ciente da serie com
  `Decimal`, SQLite idempotente e versionado (revisoes preservam historico).
- Relatorios (JSON/CSV), alertas pos-execucao e coleta agendada (GitHub Actions).
- Adaptador de fonte HTML (BeautifulSoup) e teste de contrato contra a API real.
- Suite de testes offline + CI.
