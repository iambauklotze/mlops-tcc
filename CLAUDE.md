# CLAUDE.md

Guidance for Claude Code in this repository. Project context: TCC (MBA ML in Production, UFSCar/ITI) by Luiz Eduardo and Aliclei, due 2026-12-05. Real-time AIS ingestion → waiting-time forecast at Santos and Rio de Janeiro → anomaly detection → drift monitoring with delayed labels.

## Governance (non-negotiable)

**Golden rule: nothing changes without Luiz's validation.**

- **Needs approval:**
  - creating, editing, moving or deleting files;
  - installing dependencies;
  - any external network call (AISStream, ANTAQ, the server, GitHub);
  - commits, branches, PRs and pushes;
  - any cloud spend;
  - any change of scope, tool, architecture or metric.
- **Free:** reading, analysis, planning, reading docs, running existing tests read-only, answering questions.
- **Proposal format:** `P-nn · tipo · título` with Por quê / Impacto / Alternativa descartada / Como reverter. Execution plans are `PE-n`. Answers are `APROVO` / `REJEITO` / `AJUSTE`. Silence is never approval, and an approval covers only what it names.
- Record every decision in `docs/DECISOES.md` (short ADR). Keep `docs/ESTADO.md` and `docs/JORNADA.md` updated at the end of each session (P-13). The journal uses the `[BANCA]` tag for presentation material.
- **Git:**
  - small commits with Conventional Commits;
  - one branch per phase;
  - nothing goes to `main` unless Luiz asks;
  - never `push --force`;
  - commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Destructive actions** (deleting data, force push, stopping the collector) need a separate explicit confirmation.

## Honesty

- Never invent metrics or results; say "não verifiquei" when something was not checked.
- Claim something works only after running it.
- Always label synthetic or simulated data as such.

## Security

- The AISStream key lives only in `.env`, which is git-ignored. `.env.example` has no values.
- A leaked key is an incident: rotate it and report it.
- Containers run as non-root with no secrets in the image.
- Pre-commit runs gitleaks; never bypass hooks (`--no-verify`).
- Raw AIS data (`data/`) is never committed or published (see `docs/LICENCAS.md`).

## Language

- Conversation and docs in Portuguese (Brazil).
- Code, identifiers and commit messages in English.
- Default mode is Mentor-Parceiro: up to 2 Socratic questions, then a recommendation. "modo direto" skips the questions but never the approval rule.

## Commands

```bash
uv sync                                   # install from uv.lock
uv run pytest -q                          # offline tests
uv run pre-commit run --all-files         # ruff, gitleaks, hygiene
docker compose up -d --build              # run the collector locally
```

```bash
ssh mlops-tcc 'cd ~/mlops-tcc && docker compose ps && docker compose logs --tail 5'
```

The server (Lightsail, us-east-2, 1 GB RAM) receives code via rsync, excluding `.env`, `data`, `.venv` and `.git`. Its `.env` was created by Luiz.

## Layout

- `ingest/collector.py`: WebSocket collector and raw writer (gzip JSONL, `date=/hour=`, sha256, no overwrite).
- `scripts/coverage_report.py`: G0 coverage report per port.
- `config/collect.yaml`: bounding boxes, port boxes, coverage criteria.
- `tests/`: offline pytest suite.
- `docs/`: ESTADO, DECISOES, JORNADA, LICENCAS.

## Known facts about the data

Real AISStream messages differ from the docs:

- MetaData keys are lowercase (`latitude`, `longitude`, `time_utc`, `MMSI`, `ShipName`).
- The PositionReport body uses `Latitude`, `Longitude`, `Sog`, `Cog` and `NavigationalStatus`.
- The test fixture still uses the documented format; fixing it is planned for Phase 1.
