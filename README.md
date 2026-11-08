# MLOps para congestionamento portuário (AIS)

TCC do MBA em Machine Learning in Production (UFSCar/ITI), de **Luiz Eduardo e Aliclei**. Entrega em 05/12/2026.

O sistema ingere dados AIS em tempo real, prevê o tempo de espera de navios nos portos de **Santos** e do **Rio de Janeiro**, detecta anomalias de fluxo e monitora drift com rótulos que chegam atrasados.

> **Status:** Fase 0 concluída. O coletor roda continuamente em um servidor AWS Lightsail desde 07/11/2026. Modelagem, serving e monitoramento estão nas próximas fases. Veja [docs/ESTADO.md](docs/ESTADO.md).

## Arquitetura atual

```
AISStream (WebSocket) ──► coletor (Docker) ──► camada bruta: JSONL gzip, data=/hour=, sha256
                                 │
                                 └──► eventos de conexão e heartbeat (healthcheck)
```

- **Coletor** ([`ingest/collector.py`](ingest/collector.py)): reconecta com backoff, registra lacunas, nunca sobrescreve um arquivo e grava o JSON bruto sem transformação.
- **Relatório de cobertura** ([`scripts/coverage_report.py`](scripts/coverage_report.py)): o gate G0 que escolheu os portos (decisão P-14).
- **Configuração** em [`config/collect.yaml`](config/collect.yaml).

## Como rodar

Pré-requisitos: [uv](https://docs.astral.sh/uv/) e Docker.

```bash
uv sync                       # dependências pelo lockfile
uv run pre-commit install     # hooks de qualidade e de segredos
uv run pytest                 # testes offline
cp .env.example .env          # depois preencha AISSTREAM_API_KEY
docker compose up -d --build  # inicia o coletor
```

```bash
docker compose run --rm --no-deps collector python scripts/coverage_report.py --since-hours 24
```

A chave do AISStream fica **apenas** no `.env`, que não é versionado.

## Documentação

| Arquivo | Conteúdo |
|---|---|
| [docs/ESTADO.md](docs/ESTADO.md) | estado atual, próximos passos, riscos |
| [docs/DECISOES.md](docs/DECISOES.md) | registro de decisões (ADR) |
| [docs/JORNADA.md](docs/JORNADA.md) | diário do projeto: decisões, dificuldades, material para a banca |
| [docs/LICENCAS.md](docs/LICENCAS.md) | licenças das dependências e termos das fontes |

## Licença

Código sob [MIT](LICENSE). Os dados AIS brutos não são publicados (ver [docs/LICENCAS.md](docs/LICENCAS.md)).
