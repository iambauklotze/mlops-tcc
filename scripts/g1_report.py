"""Gate G1 report: completed waits per port and the decision table (MODELO.md section 11).

Pipeline: treated positions (cargo/tanker) -> zones from the geofences file ->
episodes -> counts, linear projection to the cut-off date, decision.

Run: python -m scripts.g1_report [--geofences config/geofences.yaml] [--until 2026-11-28]

Writes the episodes table to data/derived/episodes.parquet for inspection.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import yaml

from features.episodes import extract_episodes
from features.geofences import classify_positions, load_geofences
from features.treated import load_positions

# Decision thresholds from MODELO.md section 11 (heuristic, approved in P-18).
SANTOS_HIGH, SANTOS_LOW, RIO_MIN = 150, 100, 50


def decide(projection: dict[str, float]) -> str:
    santos, rio = projection.get("santos", 0.0), projection.get("rio", 0.0)
    if santos >= SANTOS_HIGH and rio >= RIO_MIN:
        return "alvo principal nos 2 portos"
    if santos >= SANTOS_HIGH:
        return "previsão de espera só em Santos; Rio fica com anomalias e monitoramento"
    if santos >= SANTOS_LOW:
        return "zona cinzenta (100–150 em Santos): decisão do Luiz"
    return "Plano B: alvo = navios fundeados em t+12 h"


def usable(ep: pl.DataFrame) -> pl.Expr:
    return (
        (pl.col("status") == "completed")
        & (pl.col("label_quality") == "normal")
        & pl.col("arrival_observed")
    )


def build_report(ep: pl.DataFrame, span: tuple[datetime, datetime], until: datetime) -> str:
    start, end = span
    days = (end - start).total_seconds() / 86400
    horizon = (until - start).total_seconds() / 86400
    lines = [
        "# Gate G1",
        "",
        f"Dados: {start:%d/%m %H:%M} a {end:%d/%m %H:%M} UTC ({days:.1f} dias). "
        f"Projeção linear até {until:%d/%m} ({horizon:.0f} dias desde o início da coleta).",
        "",
        "| Porto | Episódios | Chegada vista | Completas úteis | Por dia | Projeção "
        "| Teto por chegadas | Censuradas | Saíram sem atracar | Qualidade baixa | Censura "
        "| Espera P50 (h) | P90 (h) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    projection: dict[str, float] = {}
    for port in sorted(ep["port"].unique().to_list()):
        e = ep.filter(pl.col("port") == port)
        ok = e.filter(usable(e))
        n_ok = ok.height
        per_day = n_ok / days if days > 0 else 0.0
        projection[port] = per_day * horizon
        n_cens = e.filter(pl.col("status") == "censored").height
        n_left = e.filter(pl.col("status") == "left_without_berthing").height
        n_low = e.filter(pl.col("label_quality") == "low").height
        n_seen = e.filter(pl.col("arrival_observed")).height
        # Upper bound: every observed arrival that did not leave becomes a usable label.
        seen_stay = e.filter(
            pl.col("arrival_observed") & (pl.col("status") != "left_without_berthing")
        ).height
        ceiling = seen_stay / days * horizon if days > 0 else 0.0
        decided = e.filter(pl.col("status") != "left_without_berthing").height
        cens_rate = n_cens / decided if decided else 0.0
        p50 = ok["wait_h"].quantile(0.5) if n_ok else None
        p90 = ok["wait_h"].quantile(0.9) if n_ok else None
        fmt = lambda v: "—" if v is None else f"{v:.1f}"  # noqa: E731
        lines.append(
            f"| {port} | {e.height} | {n_seen} | {n_ok} | {per_day:.1f} | {projection[port]:.0f} "
            f"| {ceiling:.0f} | {n_cens} | {n_left} | {n_low} | {cens_rate:.0%} "
            f"| {fmt(p50)} | {fmt(p90)} |"
        )
    lines += [
        "",
        f"**Decisão pela tabela da P-18:** {decide(projection)}.",
        "",
        "Notas: 'completas úteis' = atracação confirmada, sem lacuna de AIS > 6 h e com a "
        "chegada ao fundeio observada. 'Projeção' = completas úteis por dia, extrapoladas "
        "linearmente (é a base da decisão na P-18; fica enviesada para baixo enquanto a janela "
        "de dados for curta perto da espera típica, porque esperas longas ainda não terminaram). "
        "'Teto por chegadas' = chegadas vistas que não saíram, extrapoladas; supõe que todas "
        "virariam rótulo útil. A censura é calculada sobre episódios que não saíram sem atracar.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    ap.add_argument("--config", type=Path, default=Path("config/collect.yaml"))
    ap.add_argument("--geofences", type=Path, default=Path("config/geofences.yaml"))
    ap.add_argument("--until", default="2026-11-28")
    args = ap.parse_args(argv)

    ports = yaml.safe_load(args.config.read_text(encoding="utf-8"))["ports"]
    boxes = {k: v["bbox"] for k, v in ports.items()}
    pos = load_positions(args.data_dir, cargo_tanker_only=True)
    zoned = classify_positions(pos, load_geofences(args.geofences))
    ep = extract_episodes(zoned, boxes)

    out = args.data_dir / "derived" / "episodes.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    ep.write_parquet(out)

    # Data span = the whole collection (all vessel types), not only cargo positions.
    all_pos = load_positions(args.data_dir)
    span = (all_pos["ts"].min(), all_pos["ts"].max())
    until = datetime.fromisoformat(args.until).replace(tzinfo=UTC)
    print(f"geofences: {args.geofences}")
    print(build_report(ep, span, until))
    return 0


if __name__ == "__main__":
    sys.exit(main())
