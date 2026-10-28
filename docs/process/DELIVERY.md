# Entrega (Delivery)

Como o FinData Pipeline é entregue: em passos pequenos, verificáveis e guiados por provas.

## Fluxo: promessa → mudança escopada → prova

Toda etapa segue o mesmo caminho da esquerda para a direita:

1. **Promessa** — o que o usuário poderá fazer ao final (uma jornada).
2. **Mudança escopada** — a menor alteração adequada para cumprir a promessa,
   reaproveitando o que já existe (não reescrever o pipeline).
3. **Prova** — a jornada passa na sua última execução, com um observador real.

## O que conta como prova

- **Testes offline verdes** (`pytest`, sem rede): a lógica faz o que diz.
- **CI verde** no GitHub Actions: reproduzível em ambiente limpo.
- **Teste de contrato** contra a API real do BCB: a fonte ainda entrega o
  formato esperado (roda no agendado; `--run-contract` localmente).
- **Smoke ao vivo**: API e dashboard reais respondendo com dados reais.

Um "pronto" sem prova é uma **pendência**, não uma entrega.

## Cadência

- **Um commit por etapa**, com mensagem descritiva e o co-autor registrado.
- Mudanças de esquema do banco são **aditivas e idempotentes** (nunca recriam
  tabelas nem apagam dados).
- A precisão decimal é preservada: valores trafegam como **texto**, nunca
  convertidos para `float` na camada de negócio.

## Portões de qualidade (o "como")

- Type hints, exceções explícitas, separação rotas/serviços/persistência.
- Nenhuma regra de negócio reimplementada na API/dashboard — reuso do pipeline.
- Testes não dependem de internet nem disparam coleta real inadvertidamente.
- Segredos fora do repositório; operações de escrita protegíveis por token.

## Estado atual (resumo)

Ver [../product/ROADMAP_AND_ACCEPTANCE.md](../product/ROADMAP_AND_ACCEPTANCE.md)
para o estado e a prova de cada etapa, e [../journeys/JOURNEYS.md](../journeys/JOURNEYS.md)
para as jornadas.
