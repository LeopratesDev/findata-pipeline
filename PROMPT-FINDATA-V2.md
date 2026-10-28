# PROMPT — FinData Pipeline v2.0: API REST, Dashboard e Docker

> **Como usar este arquivo.** Cole o conteúdo abaixo (da seção "1. Papel e
> contexto" em diante) em uma conversa nova, com o repositório
> `findata-pipeline` disponível como diretório de trabalho. Este prompt já
> parte do estado real do projeto após a Etapa 1 (pipeline-base implementado
> e auditado) — não é um projeto do zero.

---

## 1. Papel e contexto

Atue como engenheiro de software sênior e especialista em engenharia de dados
financeiros, APIs REST, visualização de dados e containers.

Você vai **evoluir** um projeto Python existente e funcional chamado **FinData
Pipeline**, que coleta, valida, versiona e armazena indicadores financeiros
públicos do Banco Central do Brasil (CDI, Selic, IPCA) via API SGS, com
persistência em SQLite.

O objetivo da v2.0 é transformar o pipeline (hoje só CLI) em uma plataforma
integrada: **API REST (FastAPI)** que expõe os dados, **dashboard (Streamlit)**
que consome a API, e **Docker Compose** que sobe tudo com um comando.

Este é um projeto independente de portfólio, para uma entrevista de programador
na área financeira. **Não** use dados privados, credenciais ou sistemas
internos de nenhuma empresa, e **não** afirme vínculo oficial com ninguém.

**Restrição de escopo (decisão tomada, não reabrir):** manter **SQLite +
FastAPI + Streamlit + Docker Compose**. **Não** introduzir PostgreSQL, Redis,
Celery, Kafka, Kubernetes ou microserviços. O valor aqui é um sistema coerente,
confiável e *concluível* — não um stack inflado. Qualquer dependência nova
precisa de justificativa concreta.

---

## 2. Estado atual do repositório (já verificado — não re-auditar do zero)

O pipeline-base já está implementado, testado (**41 testes passando, 3 skipped**
de contrato) e com README honesto. **Antes de alterar qualquer coisa, rode os
testes para confirmar que continuam verdes no seu ambiente**, mas não refaça a
auditoria completa: o mapa abaixo é fiel ao código.

### Estrutura

```
findata-pipeline/
├── src/findata_pipeline/
│   ├── config.py        # registro de séries + configuração por env
│   ├── scraper.py       # SgsClient (HTTP) + parse_sgs_json (função pura)
│   ├── validator.py     # validate_records: normaliza/valida por série
│   ├── database.py      # Database: SQLite idempotente e versionado
│   ├── reporter.py      # ExecutionReport: estatísticas e export JSON/CSV
│   ├── alerts.py        # evaluate/emit: alertas pós-execução
│   ├── html_source.py   # adaptador de fonte HTML (BeautifulSoup)
│   └── main.py          # run_pipeline + CLI (argparse) + exit code
├── tests/               # pytest; fixtures locais; test_contract (marcado)
├── .github/workflows/   # ci.yml e scheduled.yml
├── conftest.py          # flag --run-contract
├── requirements.txt · pyproject.toml · .env.example · README.md
```

### Séries (`config.py`)

| series_id   | sgs_code | nome               | unit               | periodicity   | min..max |
|-------------|----------|--------------------|--------------------|---------------|----------|
| BCB-SGS-12  | 12       | CDI                | percent_per_day    | business_day  | 0..5     |
| BCB-SGS-432 | 432      | Selic meta (Copom) | percent_per_year   | calendar_day  | 0..100   |
| BCB-SGS-433 | 433      | IPCA               | percent_per_month  | monthly       | -10..50  |

Config por ambiente: `DB_PATH` (default `data/findata.db`), `LOG_LEVEL`,
`REQUEST_TIMEOUT` (default 15), `DATA_SOURCE_BASE_URL`. `SOURCE = "BCB-SGS"`.

### Esquema SQLite (`database.py`)

- **observations**(`id`, `series_id`, `source`, `reference_date` ISO, `value`
  TEXT, `unit`, `collected_at` ISO-UTC, `version`, `is_current`,
  `superseded_at`). Índice **parcial único** `(series_id, reference_date)
  WHERE is_current = 1` → garante uma única versão vigente por (série, data).
- **rejections**(`id`, `run_id`, `series_id`, `raw_data`, `raw_value`,
  `reason`, `collected_at`).
- **runs**(`id`, `started_at`, `finished_at`, `source`, `extracted`, `valid`,
  `rejected`, `inserted`, `duplicates`, `revisions`, `status`).

### Interfaces que a API DEVE reutilizar (não reimplementar)

- `main.run_pipeline(client, db, series_ids=None, start=None, end=None) -> ExecutionReport`
- `scraper.SgsClient(session=None, timeout=..., base_url=..., max_retries=2, backoff_seconds=1.0)`
- `Database(path)` → `.initialize()`, `.get_observations(series_id=None, include_history=False)`,
  `.get_history(series_id, reference_date)`, `.count_observations()`,
  `.start_run()`, `.finish_run(...)`, `.insert_observations(...)`,
  `.insert_rejections(...)`, `.close()`
- `validator.validate_records`, `reporter.ExecutionReport`, `alerts.evaluate/emit`

**Já aplicado nesta base:** a conexão SQLite usa **WAL + `timeout=30s`**
(`sqlite3.connect(path, timeout=30.0)` + `PRAGMA journal_mode = WAL`), para
leituras concorrentes enquanto o pipeline escreve. Preserve isso.

---

## 3. Regras invioláveis de integração

1. **Centralize a orquestração numa camada de serviços** (`services/`) que a API
   chama e que pode ser testada **sem HTTP**. As rotas FastAPI só traduzem
   HTTP ↔ serviço.
2. **Não duplique** lógica de coleta, validação ou persistência em arquivos da
   API. Importe e chame o pipeline existente.
3. **Precisão decimal:** os valores são guardados como **texto canônico** (ex.
   `"0.040168"`). A API deve devolvê-los **como string**, nunca convertidos para
   `float` na camada de negócio. Documente essa escolha no OpenAPI.
4. **Idempotência e histórico** do pipeline continuam íntegros; revisões não
   sobrescrevem (via `is_current`/`version`). O dashboard mostra só versões
   vigentes por padrão; histórico de revisões é opt-in.
5. **O dashboard nunca consulta o SQLite direto** nem chama a API pública do BCB
   a cada render. Ele fala só com a API da aplicação; a coleta só acontece pelo
   fluxo do pipeline.

---

## 4. API REST (FastAPI + Uvicorn + Pydantic)

Organize em `src/findata_pipeline/api/` com `routes/`, `schemas/`, `services/`,
`deps.py`, `app.py`. Documente tudo em OpenAPI/Swagger com exemplos reais
baseados no esquema acima.

### Conexão com o banco na API
Não compartilhe a conexão única de `Database` entre threads do servidor. Use
**uma conexão por requisição** (dependência FastAPI que abre/fecha o
`Database`) ou um pequeno pool. O WAL já permite leitura concorrente.

### Endpoints

**Saúde e diagnóstico**
- `GET /health` — processo responde (sempre 200 se vivo).
- `GET /ready` — dependências prontas (banco acessível, tabelas existem); 503 se não.
- `GET /api/v1/status` — resumo: nº de observações vigentes, última coleta
  bem-sucedida, estado da última execução.

**Indicadores**
- `GET /api/v1/indicators` — lista as séries do registro (`config.SERIES`), com
  unidade e periodicidade.
- `GET /api/v1/indicators/{series_id}/latest` — último valor vigente (404 se série
  desconhecida; 200 com corpo indicando "sem dados" se série existe mas vazia).
- `GET /api/v1/indicators/{series_id}/history?start=&end=&limit=&offset=&include_history=`
  — histórico paginado; valide os parâmetros (422 em data inválida / limit fora
  de faixa); `include_history=true` traz versões aposentadas sem misturar com as
  vigentes (marque `is_current`).

**Execuções**
- `GET /api/v1/runs?limit=&offset=` — lista execuções (tabela `runs`).
- `GET /api/v1/runs/{run_id}` — detalhe de uma execução + rejeições ligadas pelo `run_id`.
- `POST /api/v1/runs` — solicita nova coleta. Retorna **202** com `run_id` e
  `status`. Ver seção 4.1.
- `GET /api/v1/runs/{run_id}/status` — status atual da execução (não bloqueante).

**Relatórios**
- `GET /api/v1/reports` — lista relatórios gerados (arquivos em `reports/`).
- `GET /api/v1/reports/{report_id}/download` — baixa um relatório. **Bloqueie
  path traversal:** resolva o caminho e rejeite (400) qualquer coisa fora do
  diretório `reports/`; aceite só IDs/arquivos gerados pelo próprio sistema.

### Contratos e erros
Use Pydantic nas requisições e respostas. Padronize erros: **400** (requisição
inválida), **404** (recurso inexistente), **409** (conflito de execução), **422**
(validação de parâmetros), **503** (dependência indisponível), **500** (inesperado,
sem vazar stack trace, caminho interno ou segredo). Configure CORS só para a
origem do dashboard.

### 4.1. Execução assíncrona sem Celery/Redis
O pipeline é síncrono. Para executá-lo fora do ciclo da requisição, use
**`BackgroundTasks` do FastAPI** (ou um `ThreadPoolExecutor` de 1 worker):
1. `POST /api/v1/runs` grava uma linha em `runs` com `status="running"` (via
   `start_run`), dispara a tarefa em background e responde **202** com o `run_id`.
2. A tarefa roda `run_pipeline(...)` e no fim chama `finish_run(...)` com o status.
3. **Impeça execuções simultâneas:** antes de aceitar, cheque se já há `run`
   com `status="running"`; se houver, responda **409**. Use um lock simples
   (ex.: `threading.Lock` no processo, ou uma marca persistida) — documente a
   escolha e a limitação (vale para 1 processo; múltiplos workers exigiriam um
   lock no banco).
4. Em falha, persista `status="failed"` e um `error_detail` legível (ver 4.2).

### 4.2. Migração segura do esquema `runs`
A API precisa de mais campos em `runs`. **Não recrie a tabela** — faça migração
aditiva e idempotente: leia `PRAGMA table_info(runs)` e `ALTER TABLE runs ADD
COLUMN` apenas para o que faltar. Colunas a acrescentar:
- `window_start` TEXT, `window_end` TEXT — janela pedida na coleta.
- `requested_series` TEXT — séries pedidas (JSON ou CSV).
- `error_detail` TEXT — mensagem de erro quando `status="failed"`.
- `trigger` TEXT — `"cli"` | `"api"` | `"scheduled"`.

A duração da execução é derivada de `finished_at - started_at` (ambos ISO-UTC);
só exiba se `finished_at` existir.

---

## 5. Dashboard (Streamlit + Plotly)

Em `src/findata_pipeline/dashboard/`. **Extraia a lógica de consulta/formatação
para funções puras testáveis** (ex.: `client.py` com chamadas à API,
`format.py` com formatação de data/valor) — a UI só orquestra.

Em pt-BR, layout sóbrio e profissional (fundo neutro, azul, destaques
moderados), navegação lateral, responsivo. Sem emojis decorativos, sem valores
fictícios. Datas em formato brasileiro; cada valor com **sua unidade correta**
(não mostre CDI diário como anual, nem IPCA mensal como diário). Estados visuais
para carregando / sucesso / sem dados / erro. Identifique fonte e data de
referência.

**Páginas:**
1. **Visão geral** — cartões: último CDI, última Selic, último IPCA (cada um com
   data de referência e unidade), data/hora da última coleta, estado da API, nº
   de registros, estado da última execução. Tudo vindo da API.
2. **Gráficos (Plotly)** — evolução histórica de Selic, CDI e IPCA (séries
   separadas, respeitando periodicidade). Filtros: indicador, data inicial, data
   final. Eixos e unidades rotulados; períodos sem dado tratados sem
   interpolação enganosa; mensagem útil quando a consulta vier vazia. **Não**
   combine unidades diferentes no mesmo eixo sem justificativa explícita.
3. **Histórico** — tabela pesquisável (indicador, código, data de referência,
   valor, unidade, fonte, data de coleta, versão/situação). Paginação servida
   pela API. Exportar o resultado filtrado para CSV preservando os filtros.
   Consulta opcional das versões anteriores de um registro sem misturar com as
   vigentes.
4. **Execuções** — lista com data/hora, fonte, status, extraídos, válidos,
   rejeitados, inseridos, duplicados, revisões, duração; detalhe com motivos das
   rejeições. Estados visuais para sucesso / alerta / falha.
5. **Relatórios** — listar e baixar (JSON/CSV) via API.
6. **Execução manual** — botão que chama `POST /runs`: confirmação antes;
   avisa que pode demorar; mostra `run_id` e status; atualiza o status sem
   travar a UI; não declara conclusão antes da confirmação real; trata 409
   (execução em curso) e erros de forma compreensível.

---

## 6. Docker e Docker Compose

Subir tudo com **um comando**: `docker compose up --build`, sem passos manuais
para criar tabelas, instalar pacotes ou preparar diretórios (a API chama
`initialize()` na subida).

**Serviços:**
- `api` — FastAPI/Uvicorn.
- `dashboard` — Streamlit, consome a API pela rede interna.

Não crie um container de pipeline permanente: a coleta roda pela API em tarefa
controlada (seção 4.1). Documente essa decisão.

**Dockerfile(s):** imagem Python versionada (ex.: `python:3.12-slim`),
instalação reproduzível de `requirements.txt`, `WORKDIR` explícito, **usuário
não-root**, `.dockerignore` (exclua `.venv`, `.git`, `data`, `reports`, `logs`,
caches), logs em stdout/stderr, encerramento (SIGTERM) respeitado.

**Compose:** rede interna; **volume persistente para o SQLite** (caminho
consistente entre containers — nunca em diretório temporário do container);
volume para `reports/` compartilhado quando necessário; **health checks**
(`/health` na API); `depends_on` com condição de saúde; variáveis de ambiente;
portas documentadas; **sem expor o banco**. Só a API escreve no banco; o
dashboard chega aos dados pela API.

**Persistência:** após `docker compose down` e subir de novo, os dados
coletados permanecem (desde que o volume não seja removido). Documente a
diferença entre parar, recriar, remover volumes e fazer backup/restauração do
`.db`. A inicialização normal **nunca** apaga dados.

---

## 7. Configuração e segurança

- Tudo por variáveis de ambiente; forneça `.env.example` atualizado **sem
  segredos** (inclua `API_BASE_URL` do dashboard, `DB_PATH`, `REPORTS_DIR`,
  `LOG_LEVEL`, CORS, e uma chave opcional para operações de escrita).
- **Proteja `POST /runs`** quando a app for exposta: autenticação simples por
  token em header, com **comparação segura** (`secrets.compare_digest`). Em
  ambiente estritamente local, o dashboard pode funcionar sem login, mas a
  operação de disparo deve ser protegível por env.
- Nunca vaze stack trace, caminho interno ou segredo nas respostas.
- Não considere a aplicação pronta para exposição pública só porque roda local.

---

## 8. Testes (pytest) — ampliar a suíte existente

Sem rede nos testes comuns; nunca dispare coleta real inadvertidamente (use o
cliente SGS com transporte falso / fixtures já existentes em `tests/fixtures/`).

**API:** health/ready; listagem e `latest` de indicadores; histórico com
filtros e paginação; validação de parâmetros (422); série inexistente (404);
serialização de `value` como string decimal; listagem/detalhe de execuções;
`POST /runs` retornando 202; **conflito 409** em execução simultânea; download
autorizado de relatório; **bloqueio de path traversal** (400).

**Dashboard:** funções puras de consulta/formatação — resposta vazia, erro HTTP,
formatação de data/unidade, parâmetros enviados à API, conversão para os
gráficos, ausência de valores financeiros fixos como "atuais".

**Integração (sem rede):** banco de teste → fixtures/dados de demo claramente
marcados → consulta pela API → execução controlada do pipeline (cliente falso)
→ conferir status, integridade e persistência.

**Não declare testes aprovados sem executá-los.** Rode e cole a saída.

---

## 9. Qualidade

Type hints, validação de entrada, exceções explícitas, separação
rotas/serviços/persistência, config centralizada, deps reproduzíveis, logs
estruturados quando fizer sentido. Preserve `Decimal`/texto canônico — defina e
documente a representação de API dos valores (string). Migrações de esquema
sempre aditivas e idempotentes (seção 4.2).

---

## 10. README e documentação

Atualize o README para a versão integrada: objetivo, funcionalidades,
arquitetura + **diagrama de componentes** (pipeline + API + dashboard + Docker),
tecnologias, estrutura de pastas, pré-requisitos, execução local, execução com
`docker compose up --build`, endereços locais reais (dashboard e API) e portas
reais do Compose, link do Swagger, exemplos de requisição/resposta, exemplos de
teste, persistência/backup/restauração, segurança e limitações conhecidas,
melhorias futuras. Capturas de tela só se forem reais. **Não invente link de
demo hospedada nem afirme que está em produção.**

---

## 11. Fluxo de trabalho

A Etapa 1 (pipeline-base) está pronta. Trabalhe em **etapas pequenas e
verificáveis, um commit/PR por etapa** (o histórico do repo já segue esse
padrão):

- **Etapa 2 — Camada de serviços + API** (base de tudo): serviços reutilizando
  o pipeline, rotas, schemas, migração de `runs`, execução assíncrona, testes.
- **Etapa 3 — Dashboard** Streamlit consumindo a API; funções puras testáveis.
- **Etapa 4 — Docker** Dockerfiles, Compose, volumes, health checks, rede.
- **Etapa 5 — Integração final + README**: subir tudo, testar persistência,
  consulta e uma execução controlada; atualizar o README.

Ao fim de cada etapa, informe: **arquivos criados, arquivos modificados,
funcionalidades implementadas, testes executados e resultados, problemas
encontrados, pendências para a próxima etapa.**

Tome decisões técnicas razoáveis e documente-as; só me interrompa por falta de
acesso, decisão realmente bloqueadora ou risco de perda de dados. **Não gere
pseudocódigo:** implemente os arquivos no repositório, rode os testes possíveis
e documente honestamente o que foi verificado.

---

## 12. Critérios de aceitação

- O pipeline original continua funcionando e seus testes continuam passando.
- A API consulta os dados persistidos; Swagger acessível; valores como string decimal.
- O dashboard consome a API real; gráficos com dados reais respeitando unidades;
  filtros funcionam.
- Relatórios consultáveis e baixáveis com segurança (sem path traversal).
- Execução manual com controle de concorrência (409) e status rastreável (202).
- O SQLite mantém os dados após recriação dos containers.
- `docker compose up --build` sobe os serviços corretamente.
- Novos testes cobrem endpoints e fluxos principais.
- O README permite outra pessoa reproduzir tudo.
- **Nenhuma funcionalidade não implementada é apresentada como concluída.**

Comece pela **Etapa 2**. Rode os testes atuais primeiro para confirmar a base,
depois implemente a camada de serviços e a API.
