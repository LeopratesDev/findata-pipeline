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
- **beautifulsoup4** — declarado por fazer parte do escopo do projeto, mas
  **não usado no caminho de produção**: a fonte escolhida (API SGS) é JSON,
  e forçar parsing de HTML seria complexidade desnecessária. Fica reservado
  para um eventual adaptador da fonte HTML do Tesouro Nacional.

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
- **database.py** — SQLite com `UNIQUE(series_id, reference_date)` e transações.
- **reporter.py** — estatísticas, resumo e export.
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
│   └── main.py           # ponto de entrada
├── tests/
│   ├── fixtures/         # respostas de exemplo (JSON/HTML) para testes
│   ├── test_scraper.py
│   ├── test_validator.py
│   ├── test_database.py
│   ├── test_reporter.py
│   └── test_main.py      # integração ponta-a-ponta (sem rede)
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
```

Ao rodar **uma segunda vez** a mesma janela, a idempotência aparece:
`Novos (insert): 0` e `Duplicados: 209` — nenhum registro é duplicado.

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

1. **Agendamento e alertas**: rodar a rotina periodicamente e alertar em
   falha de coleta ou em pico de rejeições.
2. **Teste de contrato** agendado contra o endpoint real do BCB, separado da
   suíte offline, para detectar mudança de estrutura antes que ela entre no banco.
3. **Mais séries e um adaptador HTML** (Tesouro Nacional) usando o
   `beautifulsoup4`, com fixtures locais — ampliando a cobertura de dados.
