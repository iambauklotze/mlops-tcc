"""AIS coverage report per target port, for go/no-go gate G0 (proposal P-02).

Reads the raw layer written by ingest/collector.py (including unfinished
*.inprogress parts, tolerating a truncated gzip tail) and reports, per port bbox:
- position reports and distinct MMSIs seen;
- distinct cargo/tanker MMSIs (AIS ship type 70-89, from ShipStaticData);
- median interval between consecutive position reports per vessel;
- pass/fail against the thresholds in config/collect.yaml.
Collection gaps come from data/ops/connection_events.jsonl.

The "anchorage -> berth transitions" criterion of P-02 needs validated geofences
(Phase 2) and is NOT evaluated here.

Run: python scripts/coverage_report.py --config config/collect.yaml [--since-hours 24]
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
import zlib
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

CARGO_TANKER_TYPES = range(70, 90)


@dataclass(frozen=True)
class Port:
    key: str
    name: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    @classmethod
    def from_config(cls, key: str, spec: dict[str, Any]) -> Port:
        (lat1, lon1), (lat2, lon2) = spec["bbox"]
        return cls(
            key, spec["name"], min(lat1, lat2), max(lat1, lat2), min(lon1, lon2), max(lon1, lon2)
        )

    def contains(self, lat: float, lon: float) -> bool:
        return self.lat_min <= lat <= self.lat_max and self.lon_min <= lon <= self.lon_max


@dataclass
class PortStats:
    reports: int = 0
    times_by_mmsi: dict[int, list[datetime]] = field(default_factory=lambda: defaultdict(list))


@dataclass(frozen=True)
class Position:
    mmsi: int
    lat: float
    lon: float


def iter_raw_lines(raw_root: Path) -> Iterator[dict[str, Any]]:
    """Yield envelope records from all raw parts, tolerating truncated gzip tails."""
    files = sorted(raw_root.glob("date=*/hour=*/*.jsonl.gz*"))
    for path in files:
        if path.name.endswith(".sha256"):
            continue
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue  # partial last line of an unfinished part
        except (EOFError, gzip.BadGzipFile, zlib.error):
            print(f"warning: truncated or unreadable part {path}", file=sys.stderr)


def parse_position(msg: dict[str, Any]) -> Position | None:
    """Extract a position from an AISStream PositionReport frame, or None."""
    if msg.get("MessageType") != "PositionReport":
        return None
    meta = msg.get("MetaData") or {}
    body = (msg.get("Message") or {}).get("PositionReport") or {}
    mmsi = meta.get("MMSI", body.get("UserID"))
    # Real frames use lowercase MetaData keys (the docs show capitalized ones).
    lat = body.get("Latitude", meta.get("latitude"))
    lon = body.get("Longitude", meta.get("longitude"))
    if (
        not isinstance(mmsi, int)
        or not isinstance(lat, int | float)
        or not isinstance(lon, int | float)
    ):
        return None
    if body.get("Valid") is False or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return Position(mmsi, float(lat), float(lon))


def parse_ship_type(msg: dict[str, Any]) -> tuple[int, int] | None:
    """Return (mmsi, AIS ship type) from a ShipStaticData frame, or None."""
    if msg.get("MessageType") != "ShipStaticData":
        return None
    body = (msg.get("Message") or {}).get("ShipStaticData") or {}
    mmsi = (msg.get("MetaData") or {}).get("MMSI", body.get("UserID"))
    ship_type = body.get("Type")
    if isinstance(mmsi, int) and isinstance(ship_type, int):
        return mmsi, ship_type
    return None


def median_interval_min(times_by_mmsi: dict[int, list[datetime]]) -> float | None:
    """Median over vessels of each vessel's median gap between consecutive reports."""
    per_vessel = []
    for times in times_by_mmsi.values():
        ts = sorted(times)
        gaps = [(b - a).total_seconds() / 60 for a, b in zip(ts, ts[1:], strict=False)]
        if gaps:
            per_vessel.append(statistics.median(gaps))
    return statistics.median(per_vessel) if per_vessel else None


def collection_gaps(events_path: Path, since: datetime | None) -> list[dict[str, Any]]:
    if not events_path.exists():
        return []
    out = []
    with events_path.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            if since and datetime.fromisoformat(rec["ts"]) < since:
                continue
            if rec["event"] == "connected" and rec.get("gap_since_last_disconnect_s"):
                out.append(rec)
    return out


def build_report(cfg: dict[str, Any], data_dir: Path, since_hours: float | None) -> str:
    ports = [Port.from_config(k, v) for k, v in cfg["ports"].items()]
    crit = cfg["coverage_criteria"]
    since = datetime.now(UTC) - timedelta(hours=since_hours) if since_hours else None

    stats = {p.key: PortStats() for p in ports}
    ship_types: dict[int, int] = {}
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    frames = 0

    for env in iter_raw_lines(data_dir / "raw"):
        ts = datetime.fromisoformat(env["recv_ts"])
        if since and ts < since:
            continue
        frames += 1
        first_ts = ts if first_ts is None or ts < first_ts else first_ts
        last_ts = ts if last_ts is None or ts > last_ts else last_ts
        try:
            msg = json.loads(env["raw"])
        except (json.JSONDecodeError, TypeError):
            continue
        st = parse_ship_type(msg)
        if st:
            ship_types[st[0]] = st[1]
            continue
        pos = parse_position(msg)
        if pos is None:
            continue
        for p in ports:
            if p.contains(pos.lat, pos.lon):
                stats[p.key].reports += 1
                stats[p.key].times_by_mmsi[pos.mmsi].append(ts)

    lines = ["# AIS coverage report (gate G0)", ""]
    if first_ts is None or last_ts is None:
        lines.append("No raw data found.")
        return "\n".join(lines)
    hours = (last_ts - first_ts).total_seconds() / 3600
    lines += [
        f"Window: {first_ts.isoformat()} -> {last_ts.isoformat()} ({hours:.1f} h), "
        f"{frames} frames, {len(ship_types)} vessels with known ship type.",
        "",
        "| Port | Position reports | Distinct MMSI | Cargo/tanker MMSI | "
        "Median report interval (min) | MMSI criterion | Interval criterion |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in ports:
        s = stats[p.key]
        mmsis = set(s.times_by_mmsi)
        cargo = {m for m in mmsis if ship_types.get(m) in CARGO_TANKER_TYPES}
        med = median_interval_min(s.times_by_mmsi)
        ok_mmsi = len(cargo) >= crit["min_cargo_tanker_mmsi"]
        ok_int = med is not None and med <= crit["max_median_report_interval_min"]
        med_txt = f"{med:.1f}" if med is not None else "n/a"
        lines.append(
            f"| {p.name} | {s.reports} | {len(mmsis)} | {len(cargo)} | {med_txt} | "
            f"{'PASS' if ok_mmsi else 'FAIL'} | {'PASS' if ok_int else 'FAIL'} |"
        )

    gaps = collection_gaps(data_dir / "ops" / "connection_events.jsonl", since)
    total_gap = sum(g["gap_since_last_disconnect_s"] for g in gaps)
    lines += [
        "",
        f"Collection gaps (reconnections): {len(gaps)}, total {total_gap / 60:.1f} min.",
        "Not evaluated: anchorage->berth transitions (needs validated geofences, Phase 2).",
        "Note: cargo/tanker counts only include vessels whose ShipStaticData was seen.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("config/collect.yaml"))
    parser.add_argument("--since-hours", type=float, default=None)
    args = parser.parse_args(argv)
    with args.config.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    data_dir = Path(cfg["collection"]["data_dir"])
    print(build_report(cfg, data_dir, args.since_hours))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
