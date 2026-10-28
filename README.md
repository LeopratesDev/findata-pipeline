# FinData Pipeline

![CI](https://github.com/LeopratesDev/findata-pipeline/actions/workflows/ci.yml/badge.svg)

Pipeline de coleta, validação, persistência e relatório de **indicadores
financeiros públicos** do Banco Central do Brasil (CDI, Selic e IPCA) —
os índices que embasam decisões de crédito estruturado e securitização
(CRI, CRA, FIDC).

> **Natureza do projeto.** Demonstração técnica para fins educacionais e de
> portfólio. **Não** acessa sistemas internos nem dados privados de nenhuma
> empresa, e **não** está em produção. Todos os números deste README foram
> gerados por execuções locais reais contra a API pública do BCB.

---

## Problema que resolve

Em crédito estruturado, operações são indexadas a taxas de mercado
(ex.: "CDI + spread", "IPCA + taxa"). Trabalhar com esses números exige
três garantias que este projeto demonstra:

- **Rastreabilidade** — saber de onde veio cada valor, a data do indicador
  e quando ele foi coletado.
- **Precisão decimal** — taxas não toleram o erro binário do `float`.
- **Idempotência** — reexecutar a rotina não pode duplicar nem corromper
  o histórico.

## Objetivos

- **Técnico:** um pipeline simples, testável e confiável, com separação
  clara de responsabilidades e cobertura de testes sem dependência de rede.
- **De negócio:** servir de base honesta para conversar sobre engenharia
  de dados financeiros numa entrevista, com decisões defensáveis.

## Tecnologias

- **Python 3.12**
- **requests** — requisições HTTP
- **pandas** — agregação das estatísticas e export CSV
- **SQLite** (`sqlite3`) — persistência
- **pytest** — testes automatizados
- **logging** — rastreabilidade de execução
- **beautifulsoup4** — usado pelo adaptador de fonte HTML (`html_source.py`),
  que parseia tabelas HTML. A fonte principal (API SGS) é JSON; o adaptador
  cobre fontes tabulares em HTML e é demonstrado com um fixture local (veja
  a nota de honestidade na seção *Fonte alternativa*).

## Fonte de dados

API do **SGS (Sistema Gerenciador de Séries Temporais)** do Banco Central:

```
https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json
```

Resposta: array JSON de `{"data": "dd/MM/yyyy", "valor": "<string>"}`.

| series_id   | Código SGS | Indicador           | Unidade           | Periodicidade |
|-------------|-----------:|---------------------|-------------------|---------------|
| BCB-SGS-12  |         12 | CDI                 | % ao dia          | dias úteis    |
| BCB-SGS-432 |        432 | Selic meta (Copom)  | % ao ano          | dias corridos |
| BCB-SGS-433 |        433 | IPCA                | % ao mês          | mensal        |

As três séries foram verificadas ao vivo contra a API. A API é de **dados
abertos**; o cliente usa timeout, retry com backoff e não contorna nenhum
controle de acesso.

> **Comportamento observado:** quando não há dado no intervalo pedido (ex.:
> uma série mensal numa janela curta), a API responde **HTTP 404**. O cliente
> trata isso como "sem dados" (retorna vazio e dispara o alerta `no_data`),
> em vez de considerar falha de coleta — distinguindo ausência de dado de
> uma indisponibilidade real (5xx/timeout).

## Arquitetura (diagrama textual)

```
          +-------------+     +--------------+     +-------------+
API SGS ->|  scraper.py | --> | validator.py | --> | database.py | --> SQLite
 (JSON)   |  (HTTP +    |     | (ISO 8601,   |     | (idempotente|
          |   parse)    |     |  Decimal,    |     |  + auditoria)|
          +-------------+     |  limites)    |     +-------------+
                              +--------------+            |
                                    |                     v
                                 válidos /           +-------------+
                                 rejeitados          | reporter.py |
                                                     | (pandas,    | --> reports/*.json|csv
                                                     |  CSV/JSON)  |     + resumo no terminal
                                                     +-------------+
                              main.py orquestra todo o fluxo e define o exit code.
```

- **config.py** — registro central das séries (código, unidade, limites).
- **scraper.py** — cliente HTTP; `parse_sgs_json` é função pura (testável).
- **validator.py** — normaliza e valida por série; separa válidos de rejeitados.
- **database.py** — SQLite versionado (índice parcial único por versão
  vigente) e transações.
- **reporter.py** — estatísticas, resumo e export.
- **alerts.py** — avaliação de alertas pós-execução.
- **html_source.py** — adaptador de fonte HTML (BeautifulSoup) para fontes
  que publicam tabelas; converte para o mesmo formato do scraper do SGS.
- **main.py** — orquestração, CLI (argparse) e código de saída.

## Estrutura de pastas

```
findata-pipeline/
├── src/findata_pipeline/
│   ├── config.py        # registro de séries e configuração
│   ├── scraper.py        # cliente HTTP do SGS
│   ├── validator.py      # validação/normalização
│   ├── database.py       # persistência SQLite
│   ├── reporter.py       # relatório e export
│   ├── alerts.py         # alertas pós-execução
│   ├── html_source.py    # adaptador de fonte HTML (BeautifulSoup)
│   └── main.py           # ponto de entrada
├── tests/
│   ├── fixtures/         # respostas de exemplo (JSON/HTML) para testes
│   ├── test_scraper.py
│   ├── test_validator.py
│   ├── test_database.py
│   ├── test_reporter.py
│   ├── test_alerts.py
│   ├── test_html_source.py
│   ├── test_main.py      # integração ponta-a-ponta (sem rede)
│   └── test_contract.py  # contrato contra a API real (só com --run-contract)
├── .github/workflows/    # CI (testes) e coleta agendada
├── conftest.py           # registra a flag --run-contract
├── data/                 # banco SQLite gerado (ignorado pelo git)
├── reports/              # relatórios gerados (ignorados pelo git)
├── logs/
├── requirements.txt
├── pyproject.toml        # configura o pytest (pythonpath=src)
├── .env.example
└── README.md
```

## Instalação

```bash
# Windows (PowerShell)
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# Linux/macOS
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Configuração opcional via variáveis de ambiente (ver `.env.example`):
`DB_PATH`, `LOG_LEVEL`, `REQUEST_TIMEOUT`, `DATA_SOURCE_BASE_URL`.

## Como executar

```bash
# Testes (não dependem de internet)
.\.venv\Scripts\python -m pytest -v

# Testes de contrato (acessam a API real do BCB; desligados por padrão)
.\.venv\Scripts\python -m pytest -m contract --run-contract -v

# Pipeline (coleta real; janela padrão de 180 dias, relatório em JSON)
# No Windows, exporte o PYTHONPATH para src antes de rodar o módulo:
$env:PYTHONPATH="src"; .\.venv\Scripts\python -m findata_pipeline.main

# Opções
.\.venv\Scripts\python -m findata_pipeline.main --days 120 --format csv --series BCB-SGS-12
```

O processo retorna **exit code 0** em sucesso e **1** se houve erro de
coleta em alguma série ou falha inesperada.

## Exemplo de saída no terminal

```
==================================================
FinData Pipeline - resumo da execucao
==================================================
Fonte           : BCB-SGS
Inicio          : 2026-10-28T14:54:37Z
Fim             : 2026-10-28T14:54:38Z
Extraidos       : 209
Validos         : 209
Rejeitados      : 0
Novos (insert)  : 209
Duplicados      : 0
Revisoes        : 0
Erros           : 0
==================================================
Alertas         : 0
```

Ao rodar **uma segunda vez** a mesma janela, a idempotência aparece:
`Novos (insert): 0` e `Duplicados: 209` — nenhum registro é duplicado.

## Agendamento e alertas

**Alertas** (módulo `alerts.py`): ao fim de cada execução o relatório é
avaliado e geram-se alertas acionáveis —

- `collection_failed` (error): falha de coleta em alguma série;
- `high_rejection_rate` (warning): taxa de rejeição acima do limite
  (`--max-rejection-rate`, padrão 20%);
- `no_data` (warning): série sem nenhum registro extraído.

O canal padrão é o **log**; quando algum alerta dispara, o processo encerra
com **exit code 1**, para que o agendador perceba a falha. Integrações
externas (webhook, e-mail) ficam como extensão e não são enviadas por padrão.

**Agendamento**: o workflow [`scheduled.yml`](.github/workflows/scheduled.yml)
roda a coleta diariamente (cron `0 9 * * *`, também disparável à mão) e
publica `reports/*.json` e `data/findata.db` como artefato — inclusive quando
um alerta dispara, para servir de evidência. Localmente, o mesmo papel cabe
ao Agendador de Tarefas (Windows) ou ao cron (Linux) chamando o comando do
pipeline.

## Fonte alternativa (adaptador HTML)

O módulo `html_source.py` usa **BeautifulSoup** para extrair uma tabela HTML
(colunas localizadas pelo cabeçalho) e devolve registros no mesmo formato do
scraper do SGS — então validator e database funcionam sem alteração.

> **Nota de honestidade:** a página real do Tesouro Nacional (Oracle APEX) é
> renderizada via JavaScript e **não** é extraível com `requests` +
> BeautifulSoup (exigiria um navegador headless). Por isso o adaptador é
> demonstrado contra um fixture HTML representativo, claramente marcado como
> dado de teste (`tests/fixtures/tesouro_sample.html`), e serve para qualquer
> fonte que publique uma tabela HTML estática.

## Exemplo de relatório (`reports/report_*.json`)

```json
{
  "source": "BCB-SGS",
  "started_at": "2026-10-28T14:54:37Z",
  "finished_at": "2026-10-28T14:54:38Z",
  "totals": {
    "extracted": 209, "valid": 209, "rejected": 0,
    "inserted": 209, "duplicates": 0, "revisions": 0
  },
  "by_series": [
    {"series_id": "BCB-SGS-12",  "extracted": 84,  "valid": 84,  "inserted": 84},
    {"series_id": "BCB-SGS-432", "extracted": 121, "valid": 121, "inserted": 121},
    {"series_id": "BCB-SGS-433", "extracted": 4,   "valid": 4,   "inserted": 4}
  ],
  "errors": []
}
```

## Estrutura do banco de dados

**observations** — dados válidos (idempotência via chave única)

| coluna          | tipo | observação                              |
|-----------------|------|-----------------------------------------|
| id              | INT  | PK                                      |
| series_id       | TEXT | ex. `BCB-SGS-12`                        |
| source          | TEXT | `BCB-SGS`                               |
| reference_date  | TEXT | data do indicador (ISO 8601)            |
| value           | TEXT | `Decimal` como texto canônico           |
| unit            | TEXT | ex. `percent_per_day`                   |
| collected_at    | TEXT | quando foi coletado (ISO 8601, UTC)     |
| version         | INT  | versão do valor para a (série, data)    |
| is_current      | INT  | 1 = versão vigente; 0 = histórica       |
| superseded_at   | TEXT | quando foi aposentada (se histórica)    |

Um **índice parcial único** `(series_id, reference_date) WHERE is_current = 1`
garante no nível do banco que existe no máximo uma versão vigente por
(série, data). Revisões geram uma nova versão vigente e preservam a anterior
no histórico (ver abaixo).

**rejections** — registros recusados (auditoria): `run_id`, `series_id`,
`raw_data`, `raw_value`, `reason`, `collected_at`.

**runs** — metadados de cada execução: `started_at`, `finished_at`,
`source`, `extracted`, `valid`, `rejected`, `inserted`, `duplicates`,
`revisions`, `status`.

## Limitações conhecidas

- Escopo de três séries (CDI, Selic, IPCA). "Spread de crédito" ficou de
  fora por exigir séries mais complexas — decisão consciente de escopo.
- `beautifulsoup4` não é exercitado no caminho de produção (fonte é JSON).
- Sem agendamento/orquestração externa (cron, Airflow) — fora do escopo.

### Revisões de valor (versionadas)

Quando um indicador é revisado (ex.: IPCA revisado pelo IBGE), o sistema
**não sobrescreve**: a versão vigente é aposentada (`is_current = 0`,
`superseded_at` preenchido) e a revisão entra como nova versão vigente. O
histórico completo fica consultável via `Database.get_history(series_id,
reference_date)`. Reexecutar com o mesmo valor vigente continua idempotente
(não cria versão nova).

## Melhorias futuras

1. **Canais de alerta externos** (webhook/e-mail) além do log, para que a
   falha chegue a quem opera sem depender de olhar o artefato.
2. **Ligar o adaptador HTML a uma fonte real** com tabela estática (ou um
   navegador headless para a página APEX do Tesouro) e integrá-lo ao `main`.
