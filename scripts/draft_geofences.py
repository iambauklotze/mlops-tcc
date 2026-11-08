"""Draft candidate anchorage and berth polygons from real AIS data (Phase 2).

Writes data/derived/geofences_candidate.yaml in the same format as the frozen
config/geofences.yaml. The candidate is NOT used by the pipeline until a human
validates it on a map and it is copied to config/ (decision recorded in DECISOES).

Run: python -m scripts.draft_geofences [--data-dir data]
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from features.geofences import CandidateParams, draft_candidates, to_config
from features.treated import in_bbox, load_positions


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    ap.add_argument("--config", type=Path, default=Path("config/collect.yaml"))
    args = ap.parse_args(argv)

    ports = yaml.safe_load(args.config.read_text(encoding="utf-8"))["ports"]
    df = load_positions(args.data_dir, cargo_tanker_only=True)
    params = CandidateParams()

    cands = {}
    for key, spec in ports.items():
        cands[key] = draft_candidates(in_bbox(df, spec["bbox"]), params)
        for c in cands[key]:
            print(f"{key:7s} {c['kind']:9s} vessels={c['n_mmsi']:3d} points={c['n_points']:5d}")

    doc = to_config(cands)
    doc = {
        "status": "candidate (not validated)",
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_span_utc": [str(df["ts"].min()), str(df["ts"].max())],
        "params": params.__dict__,
        **doc,
    }
    out = args.data_dir / "derived" / "geofences_candidate.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
