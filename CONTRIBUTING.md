# Como contribuir

Projeto de portfolio, mas organizado como um projeto real.

## Ambiente

```bash
py -3.12 -m venv .venv                       # Python 3.12
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
```

## Antes de abrir um PR

Rode os mesmos portoes do CI (devem passar):

```bash
ruff check .                                  # lint + ordem de imports
mypy                                          # tipos
pytest -v --cov=findata_pipeline              # testes + cobertura (offline)
```

O teste de contrato (acessa a API real do BCB) e opcional localmente:

```bash
pytest -m contract --run-contract
```

## Padroes

- **Evidencia acima de afirmacao:** um recurso so e "pronto" quando a sua
  jornada passa — ver [docs/journeys/JOURNEYS.md](docs/journeys/JOURNEYS.md).
- **Precisao decimal:** valores como texto/`Decimal`, nunca `float` na regra.
- **Migracoes de esquema** sempre aditivas e idempotentes (nunca recriar
  tabelas nem apagar dados).
- **Sem rede nos testes comuns**; use fixtures/transporte falso.
- Commits pequenos e descritivos; um por etapa/mudanca coesa.
- Nenhuma regra de negocio reimplementada na API/dashboard — reuso do pipeline.
