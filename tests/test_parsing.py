"""Offline tests for the collector and coverage report (no network)."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ingest.collector import (
    RawWriter,
    build_subscription,
    frame_to_text,
    inspect_frame,
    load_config,
    validate_bbox,
)
from scripts.coverage_report import (
    Port,
    build_report,
    median_interval_min,
    parse_position,
    parse_ship_type,
)

# Shape of real AISStream frames as received in production (synthetic values):
# MetaData keys are lowercase (latitude, longitude, time_utc), unlike the docs.
POSITION_FRAME = {
    "MessageType": "PositionReport",
    "MetaData": {
        "MMSI": 710000001,
        "MMSI_String": 710000001,
        "ShipName": "TEST VESSEL         ",
        "latitude": -24.0,
        "longitude": -46.3,
        "time_utc": "2026-11-07 00:01:12.602437867 +0000 UTC",
    },
    "Message": {
        "PositionReport": {
            "UserID": 710000001,
            "Latitude": -24.0,
            "Longitude": -46.3,
            "Sog": 0.1,
            "NavigationalStatus": 1,
            "Valid": True,
        }
    },
}
STATIC_FRAME = {
    "MessageType": "ShipStaticData",
    "MetaData": {
        "MMSI": 710000001,
        "time_utc": "2026-11-07 00:01:12.077504626 +0000 UTC",
    },
    "Message": {
        "ShipStaticData": {
            "UserID": 710000001,
            "Type": 70,
            "Name": "TEST VESSEL         ",
            "Destination": "SANTOS              ",
            "Dimension": {"A": 150, "B": 30, "C": 15, "D": 15},
            "ImoNumber": 9000001,
        }
    },
}

REPO = Path(__file__).resolve().parents[1]


def test_config_loads_and_boxes_are_lat_lon() -> None:
    cfg = load_config(REPO / "config" / "collect.yaml")
    assert cfg.bounding_boxes, "at least one bounding box"
    for box in cfg.bounding_boxes:
        validate_bbox(box)


@pytest.mark.parametrize("bad", [[[-24.0, -46.0]], [[-200, 0], [0, 0]], [[0, 0], [0, 181]]])
def test_validate_bbox_rejects_invalid(bad: list) -> None:
    with pytest.raises(ValueError):
        validate_bbox(bad)


def test_subscription_message_shape() -> None:
    sub = json.loads(build_subscription("k", [[[-34.0, -54.0], [5.5, -28.0]]]))
    assert sub == {"APIKey": "k", "BoundingBoxes": [[[-34.0, -54.0], [5.5, -28.0]]]}


def test_frame_to_text_decodes_binary_utf8() -> None:
    assert frame_to_text('{"a": "ç"}'.encode()) == '{"a": "ç"}'
    assert frame_to_text("x") == "x"


def test_inspect_frame_detects_control_frames_only() -> None:
    assert inspect_frame('{"error": "Api Key Is Not Valid"}') == {"error": "Api Key Is Not Valid"}
    assert inspect_frame(json.dumps(POSITION_FRAME)) is None


def test_raw_writer_is_lossless_partitioned_and_checksummed(tmp_path: Path) -> None:
    w = RawWriter(tmp_path, "run1")
    t0 = datetime(2026, 11, 6, 13, 59, 59, tzinfo=UTC)
    raw_a = json.dumps(POSITION_FRAME)
    raw_b = "not json at all"  # raw layer keeps everything, even invalid frames
    w.write(t0, raw_a)
    w.write(t0 + timedelta(seconds=2), raw_b)  # crosses into hour 14 -> new part
    w.close()

    parts = sorted(tmp_path.glob("raw/date=2026-11-06/hour=*/*.jsonl.gz"))
    assert [p.parent.name for p in parts] == ["hour=13", "hour=14"]
    assert not list(tmp_path.rglob("*.inprogress"))

    lines = []
    for p in parts:
        sidecar = p.with_name(p.name + ".sha256").read_text().split()[0]
        assert sidecar == hashlib.sha256(p.read_bytes()).hexdigest()
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            lines += [json.loads(line) for line in fh]
    assert [rec["raw"] for rec in lines] == [raw_a, raw_b]


def test_raw_writer_never_overwrites(tmp_path: Path) -> None:
    t0 = datetime(2026, 11, 6, 10, tzinfo=UTC)
    w1 = RawWriter(tmp_path, "same")
    w1.write(t0, "a")
    w1.close()
    w2 = RawWriter(tmp_path, "same")
    w2.write(t0, "b")
    with pytest.raises(FileExistsError):
        w2.close()  # rename onto an existing finished part must not silently replace it


def test_parse_position_and_ship_type() -> None:
    pos = parse_position(POSITION_FRAME)
    assert pos is not None and (pos.mmsi, pos.lat, pos.lon) == (710000001, -24.0, -46.3)
    assert parse_ship_type(STATIC_FRAME) == (710000001, 70)
    assert parse_position(STATIC_FRAME) is None
    invalid = json.loads(json.dumps(POSITION_FRAME))
    invalid["Message"]["PositionReport"]["Valid"] = False
    assert parse_position(invalid) is None


def test_port_bbox_and_median_interval() -> None:
    spec = {"name": "Santos", "bbox": [[-24.35, -46.55], [-23.85, -46.05]]}
    port = Port.from_config("santos", spec)
    assert port.contains(-24.0, -46.3)
    assert not port.contains(-25.5, -48.5)
    t = datetime(2026, 11, 6, tzinfo=UTC)
    times = {1: [t, t + timedelta(minutes=2), t + timedelta(minutes=6)], 2: [t]}
    assert median_interval_min(times) == pytest.approx(3.0)


def test_build_report_end_to_end(tmp_path: Path) -> None:
    w = RawWriter(tmp_path, "r")
    t = datetime.now(UTC)
    w.write(t, json.dumps(STATIC_FRAME))
    for i in range(3):
        w.write(t + timedelta(minutes=5 * i), json.dumps(POSITION_FRAME))
    w.close()
    cfg = {
        "ports": {"santos": {"name": "Santos", "bbox": [[-24.35, -46.55], [-23.85, -46.05]]}},
        "coverage_criteria": {"min_cargo_tanker_mmsi": 1, "max_median_report_interval_min": 10},
    }
    report = build_report(cfg, tmp_path, since_hours=None)
    assert "| Santos | 3 | 1 | 1 | 5.0 | PASS | PASS |" in report
