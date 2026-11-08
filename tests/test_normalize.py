"""Offline tests for the treated layer (ingest/normalize.py). Frames are synthetic."""

from __future__ import annotations

import copy
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from ingest.normalize import (
    normalize_day,
    parse_time_utc,
    position_row,
    static_row,
    write_day,
)
from tests.test_parsing import POSITION_FRAME, STATIC_FRAME


def test_parse_time_utc_truncates_nanoseconds() -> None:
    ts = parse_time_utc("2026-11-07 00:01:12.602437867 +0000 UTC")
    assert ts == datetime(2026, 11, 7, 0, 1, 12, 602437, tzinfo=UTC)
    assert parse_time_utc("2026-11-07 00:01:12 +0000 UTC") == datetime(
        2026, 11, 7, 0, 1, 12, tzinfo=UTC
    )
    assert parse_time_utc("garbage") is None
    assert parse_time_utc(None) is None


def test_position_row_uses_real_field_names() -> None:
    row = position_row(POSITION_FRAME)
    assert row is not None
    assert row["mmsi"] == 710000001
    assert (row["lat"], row["lon"], row["sog"]) == (-24.0, -46.3, 0.1)
    assert row["nav_status"] == 1
    assert row["ts"].year == 2026


def test_position_row_rejects_bad_coordinates_and_flags_unavailable_sog() -> None:
    bad = copy.deepcopy(POSITION_FRAME)
    bad["Message"]["PositionReport"]["Latitude"] = 91.0  # AIS "not available"
    assert position_row(bad) is None

    no_sog = copy.deepcopy(POSITION_FRAME)
    no_sog["Message"]["PositionReport"]["Sog"] = 102.3
    row = position_row(no_sog)
    assert row is not None and row["sog"] is None


def test_static_row_extracts_type_length_and_trims_names() -> None:
    row = static_row(STATIC_FRAME)
    assert row is not None
    assert row["ship_type"] == 70
    assert row["length_m"] == 180  # Dimension A + B
    assert row["name"] == "TEST VESSEL"
    assert row["destination"] == "SANTOS"
    assert row["imo"] == 9000001
    assert static_row(POSITION_FRAME) is None


def _write_raw(day_dir: Path, frames: list[dict]) -> None:
    part = day_dir / "hour=00" / "part-test-00001.jsonl.gz"
    part.parent.mkdir(parents=True)
    with gzip.open(part, "wt", encoding="utf-8") as fh:
        for f in frames:
            fh.write(json.dumps({"recv_ts": "2026-11-07T00:01:13+00:00", "raw": json.dumps(f)}))
            fh.write("\n")


def test_normalize_day_dedups_and_writes_parquet(tmp_path: Path) -> None:
    day_dir = tmp_path / "raw" / "date=2026-11-07"
    _write_raw(day_dir, [POSITION_FRAME, POSITION_FRAME, STATIC_FRAME])

    pos, sta = normalize_day(day_dir)
    assert pos.height == 1  # exact duplicate dropped
    assert sta.height == 1

    write_day(tmp_path, "2026-11-07", pos, sta)
    back = pl.read_parquet(tmp_path / "treated" / "positions" / "date=2026-11-07.parquet")
    assert back.schema["ts"] == pl.Datetime("us", "UTC")
    assert back["mmsi"].to_list() == [710000001]
