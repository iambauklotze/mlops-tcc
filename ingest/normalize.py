"""Treated layer: raw AIS frames -> daily Parquet tables (Phase 2, decision P-19).

Reads closed raw part files (data/raw/date=*/hour=*/*.jsonl.gz) and writes, per day:
  data/treated/positions/date=YYYY-MM-DD.parquet
  data/treated/static/date=YYYY-MM-DD.parquet

The treated layer is derived and fully regenerable from the raw layer, so a day's
file is rewritten on every run (the raw layer itself is never touched).

Field names follow the real AISStream frames, which differ from the docs:
MetaData uses lowercase `latitude`, `longitude`, `time_utc`; the message body uses
`Latitude`, `Longitude`, `Sog`, `Cog`, `NavigationalStatus`.

Run: python -m ingest.normalize [--data-dir data] [--date 2026-11-08]
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

log = logging.getLogger("normalize")

POSITION_TYPES = ("PositionReport", "StandardClassBPositionReport")

POSITION_SCHEMA = {
    "mmsi": pl.Int64,
    "ts": pl.Datetime("us", "UTC"),
    "lat": pl.Float64,
    "lon": pl.Float64,
    "sog": pl.Float64,
    "cog": pl.Float64,
    "nav_status": pl.Int16,
    "msg_type": pl.Utf8,
}
STATIC_SCHEMA = {
    "mmsi": pl.Int64,
    "ts": pl.Datetime("us", "UTC"),
    "ship_type": pl.Int16,
    "length_m": pl.Int32,
    "name": pl.Utf8,
    "destination": pl.Utf8,
    "imo": pl.Int64,
    "msg_type": pl.Utf8,
}


def parse_time_utc(value: str | None) -> datetime | None:
    """Parse AISStream `time_utc`, e.g. '2026-11-07 00:01:12.077504626 +0000 UTC'.

    Nanoseconds are truncated to microseconds.
    """
    if not value:
        return None
    parts = value.split(" ")
    if len(parts) < 2:
        return None
    date_s, time_s = parts[0], parts[1]
    if "." in time_s:
        hms, frac = time_s.split(".", 1)
        time_s = f"{hms}.{frac[:6].ljust(6, '0')}"
    else:
        time_s = f"{time_s}.000000"
    try:
        return datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=UTC)
    except ValueError:
        return None


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().strip("@").strip()
    return text or None


def _valid_latlon(lat: Any, lon: Any) -> bool:
    return (
        isinstance(lat, int | float)
        and isinstance(lon, int | float)
        and -90 <= lat <= 90
        and -180 <= lon <= 180
    )


def position_row(msg: dict[str, Any]) -> dict[str, Any] | None:
    """One row of the positions table, or None if the frame is not a usable position."""
    msg_type = msg.get("MessageType")
    if msg_type not in POSITION_TYPES:
        return None
    body = (msg.get("Message") or {}).get(msg_type) or {}
    meta = msg.get("MetaData") or {}
    lat = body.get("Latitude", meta.get("latitude"))
    lon = body.get("Longitude", meta.get("longitude"))
    ts = parse_time_utc(meta.get("time_utc"))
    mmsi = meta.get("MMSI", body.get("UserID"))
    if not _valid_latlon(lat, lon) or ts is None or not isinstance(mmsi, int):
        return None
    sog = body.get("Sog")
    cog = body.get("Cog")
    return {
        "mmsi": mmsi,
        "ts": ts,
        "lat": float(lat),
        "lon": float(lon),
        # 102.3 kn means "not available" in AIS; 360 deg likewise for COG.
        "sog": float(sog) if isinstance(sog, int | float) and sog < 102.3 else None,
        "cog": float(cog) if isinstance(cog, int | float) and cog < 360 else None,
        "nav_status": body.get("NavigationalStatus"),
        "msg_type": msg_type,
    }


def static_row(msg: dict[str, Any]) -> dict[str, Any] | None:
    """One row of the static table (ship type, length, name), or None."""
    msg_type = msg.get("MessageType")
    meta = msg.get("MetaData") or {}
    ts = parse_time_utc(meta.get("time_utc"))
    mmsi = meta.get("MMSI")
    if ts is None or not isinstance(mmsi, int):
        return None
    if msg_type == "ShipStaticData":
        body = (msg.get("Message") or {}).get("ShipStaticData") or {}
        dim = body.get("Dimension") or {}
        length = (dim.get("A") or 0) + (dim.get("B") or 0)
        imo = body.get("ImoNumber")
        return {
            "mmsi": mmsi,
            "ts": ts,
            "ship_type": body.get("Type"),
            "length_m": length or None,
            "name": _clean_text(body.get("Name")),
            "destination": _clean_text(body.get("Destination")),
            "imo": imo if isinstance(imo, int) and imo > 0 else None,
            "msg_type": msg_type,
        }
    if msg_type == "StaticDataReport":
        body = (msg.get("Message") or {}).get("StaticDataReport") or {}
        rep_a = body.get("ReportA") or {}
        rep_b = body.get("ReportB") or {}
        if rep_b.get("Valid"):
            dim = rep_b.get("Dimension") or {}
            length = (dim.get("A") or 0) + (dim.get("B") or 0)
            return {
                "mmsi": mmsi,
                "ts": ts,
                "ship_type": rep_b.get("ShipType"),
                "length_m": length or None,
                "name": None,
                "destination": None,
                "imo": None,
                "msg_type": msg_type,
            }
        if rep_a.get("Valid"):
            return {
                "mmsi": mmsi,
                "ts": ts,
                "ship_type": None,
                "length_m": None,
                "name": _clean_text(rep_a.get("Name")),
                "destination": None,
                "imo": None,
                "msg_type": msg_type,
            }
    return None


def iter_frames(day_dir: Path) -> Iterator[dict[str, Any]]:
    """Decoded frames from the closed part files of one raw day partition."""
    for part in sorted(day_dir.glob("hour=*/*.jsonl.gz")):
        with gzip.open(part, "rt", encoding="utf-8") as fh:
            for line in fh:
                try:
                    msg = json.loads(json.loads(line)["raw"])
                except (json.JSONDecodeError, KeyError, TypeError):
                    log.warning("undecodable line in %s", part.name)
                    continue
                if isinstance(msg, dict):
                    yield msg


def normalize_day(day_dir: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    positions: list[dict[str, Any]] = []
    statics: list[dict[str, Any]] = []
    for msg in iter_frames(day_dir):
        row = position_row(msg)
        if row is not None:
            positions.append(row)
            continue
        srow = static_row(msg)
        if srow is not None:
            statics.append(srow)
    pos = (
        pl.DataFrame(positions, schema=POSITION_SCHEMA)
        .unique(subset=["mmsi", "ts", "lat", "lon"], keep="first")
        .sort(["mmsi", "ts"])
    )
    sta = pl.DataFrame(statics, schema=STATIC_SCHEMA).sort(["mmsi", "ts"])
    return pos, sta


def write_day(data_dir: Path, day: str, pos: pl.DataFrame, sta: pl.DataFrame) -> None:
    for name, df in (("positions", pos), ("static", sta)):
        out = data_dir / "treated" / name / f"date={day}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".parquet.tmp")
        df.write_parquet(tmp)
        tmp.replace(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    ap.add_argument("--date", help="only this day (YYYY-MM-DD); default: all days")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    days = sorted((args.data_dir / "raw").glob("date=*"))
    if args.date:
        days = [d for d in days if d.name == f"date={args.date}"]
    if not days:
        log.error("no raw day partitions found under %s", args.data_dir / "raw")
        return 1
    for day_dir in days:
        day = day_dir.name.removeprefix("date=")
        pos, sta = normalize_day(day_dir)
        write_day(args.data_dir, day, pos, sta)
        log.info("%s: %d positions, %d static rows", day, pos.height, sta.height)
    return 0


if __name__ == "__main__":
    sys.exit(main())
