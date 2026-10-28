# Documentação — FinData Pipeline

Hub da documentação. O projeto segue uma disciplina inspirada no
[GraphHelm](https://github.com/stabem/GraphHelm) e no seu *Journey-Proven
Development*: **evidência acima de afirmação** — um merge, um build verde ou um
"pronto" não provam que um recurso funciona; ele só está provado quando a sua
**jornada passa na última execução**.

> Separação de responsabilidades (à la Keel): a **qualidade** governa *como* o
> código é escrito (testes offline, type hints, commits pequenos, CI); as
> **jornadas** governam *se funciona* (fluxos ponta a ponta com prova).

## Mapa

| Documento | Para quê |
|-----------|----------|
| [process/DELIVERY.md](process/DELIVERY.md) | Como entregamos: o que conta como prova, cadência, portões de qualidade. |
| [product/ROADMAP_AND_ACCEPTANCE.md](product/ROADMAP_AND_ACCEPTANCE.md) | Roadmap por etapas, critérios de aceitação, estado atual e a prova de cada uma. |
| [jpd/JOURNEYS.md](jpd/JOURNEYS.md) | As jornadas do usuário e a prova (atual) de cada uma. |
| [../README.md](../README.md) | Visão geral, instalação e execução. |

## Observadores

Cada prova depende de um **observador** — quem/o que confirma o resultado:

- Testes offline (`pytest`) e CI → observador sempre disponível.
- Teste de contrato (`--run-contract`) → observador externo (API do BCB).
- API/dashboard ao vivo → observador manual (smoke verificado).
- `docker compose up --build` → observador é o **daemon do Docker**.

Quando o observador está indisponível, a jornada permanece **não resolvida** —
nunca é declarada como provada.
