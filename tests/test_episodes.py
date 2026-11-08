"""Episode extractor and geofences on SYNTHETIC tracks (no real AIS data).

Toy port "p": box lat/lon in [-1, 1]; anchorage square at [-0.5, -0.2];
berth square at [0.2, 0.5]. One point every 10 minutes unless stated.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
import yaml
from shapely.geometry import box

from features.episodes import EpisodeParams, extract_episodes
from features.geofences import (
    ANCHOR,
    BERTH,
    CandidateParams,
    classify_positions,
    draft_candidates,
    load_geofences,
    to_config,
)

T0 = datetime(2026, 11, 7, 0, 0, tzinfo=UTC)
STEP = timedelta(minutes=10)
BOXES = {"p": [[-1.0, -1.0], [1.0, 1.0]]}
ANCH = (-0.35, -0.35)
BERTH_PT = (0.35, 0.35)
SEA = (0.0, 0.0)  # inside the port box, outside any zone
OUTSIDE = (5.0, 5.0)  # outside the port box


@pytest.fixture
def fences(tmp_path: Path):
    cands = {
        "p": [
            {"kind": ANCHOR, "polygon": box(-0.5, -0.5, -0.2, -0.2), "n_mmsi": 3},
            {"kind": BERTH, "polygon": box(0.2, 0.2, 0.5, 0.5), "n_mmsi": 2},
        ]
    }
    path = tmp_path / "geofences.yaml"
    path.write_text(yaml.safe_dump(to_config(cands)))
    return load_geofences(path)


def track(mmsi: int, segments: list[tuple[tuple[float, float], float, int]], start=T0):
    """segments: ((lat, lon), sog, n_points); returns rows spaced by STEP."""
    rows, t = [], start
    for (lat, lon), sog, n in segments:
        for _ in range(n):
            rows.append({"mmsi": mmsi, "ts": t, "lat": lat, "lon": lon, "sog": sog})
            t += STEP
    return rows


def run(fences, rows, data_end=None):
    df = pl.DataFrame(
        rows,
        schema={
            "mmsi": pl.Int64,
            "ts": pl.Datetime("us", "UTC"),
            "lat": pl.Float64,
            "lon": pl.Float64,
            "sog": pl.Float64,
        },
    )
    return extract_episodes(classify_positions(df, fences), BOXES, data_end=data_end)


def test_completed_wait_is_anchor_start_to_berth_start(fences) -> None:
    rows = track(1, [(SEA, 10, 3), (ANCH, 0.1, 18), (SEA, 8, 2), (BERTH_PT, 0.0, 12)])
    ep = run(fences, rows)
    assert ep.height == 1
    e = ep.row(0, named=True)
    assert e["status"] == "completed"
    assert e["anchor_start"] == T0 + 3 * STEP
    assert e["anchor_confirm"] == T0 + 3 * STEP + timedelta(minutes=30)
    assert e["berth_start"] == T0 + 23 * STEP
    assert e["wait_h"] == pytest.approx(20 * 10 / 60)
    assert e["label_quality"] == "normal"
    assert e["anchor_zone_id"] == "p_A1" and e["berth_zone_id"] == "p_B1"


def test_short_stop_is_not_an_anchorage(fences) -> None:
    # 3 points = 20 min of dwell, below the 30 min rule.
    rows = track(2, [(SEA, 10, 3), (ANCH, 0.1, 3), (SEA, 8, 2), (BERTH_PT, 0.0, 12)])
    assert run(fences, rows).height == 0


def test_moving_inside_anchorage_does_not_count(fences) -> None:
    rows = track(3, [(SEA, 10, 3), (ANCH, 3.0, 18), (BERTH_PT, 0.0, 12)])
    assert run(fences, rows).height == 0


def test_left_without_berthing(fences) -> None:
    rows = track(4, [(SEA, 10, 3), (ANCH, 0.1, 12), (SEA, 10, 2), (OUTSIDE, 12, 3)])
    e = run(fences, rows).row(0, named=True)
    assert e["status"] == "left_without_berthing"
    assert e["berth_start"] is None


def test_censored_when_data_ends_at_anchor(fences) -> None:
    rows = track(5, [(SEA, 10, 3), (ANCH, 0.1, 12)])
    end = T0 + 20 * STEP
    e = run(fences, rows, data_end=end).row(0, named=True)
    assert e["status"] == "censored"
    assert e["end_ts"] == end
    assert e["wait_h"] == pytest.approx(17 * 10 / 60)  # lower bound


def test_long_gap_marks_low_quality(fences) -> None:
    before = track(6, [(SEA, 10, 3), (ANCH, 0.1, 6)])
    after = track(6, [(ANCH, 0.1, 3), (BERTH_PT, 0.0, 6)], start=T0 + timedelta(hours=10))
    e = run(fences, before + after).row(0, named=True)
    assert e["status"] == "completed"
    assert e["label_quality"] == "low"
    assert e["max_gap_h"] > 6


def test_arrival_must_be_observed(fences) -> None:
    # 7: already anchored in its first point (e.g. at data start): arrival not seen.
    first_heard_anchored = track(7, [(ANCH, 0.1, 12), (BERTH_PT, 0.0, 6)])
    # 8: seen moving right before anchoring: arrival observed.
    seen_arriving = track(8, [(SEA, 10, 3), (ANCH, 0.1, 12), (BERTH_PT, 0.0, 6)])
    # 9: last seen at sea 8 h before it shows up anchored (poor reception).
    silent = track(9, [(SEA, 10, 2)]) + track(
        9, [(ANCH, 0.1, 12), (BERTH_PT, 0.0, 6)], start=T0 + timedelta(hours=8)
    )
    ep = run(fences, first_heard_anchored + seen_arriving + silent)
    flags = dict(zip(ep["mmsi"].to_list(), ep["arrival_observed"].to_list(), strict=True))
    assert flags == {7: False, 8: True, 9: False}


def test_berthing_without_anchorage_is_not_an_episode(fences) -> None:
    rows = track(9, [(SEA, 10, 3), (BERTH_PT, 0.0, 12)])
    assert run(fences, rows).height == 0


def test_two_visits_give_two_episodes(fences) -> None:
    rows = track(
        10,
        [
            (SEA, 10, 3),
            (ANCH, 0.1, 6),
            (BERTH_PT, 0.0, 6),
            (OUTSIDE, 12, 3),
            (SEA, 10, 2),
            (ANCH, 0.1, 6),
            (BERTH_PT, 0.0, 6),
        ],
    )
    ep = run(fences, rows)
    assert ep["status"].to_list() == ["completed", "completed"]


def test_berth_wins_where_zones_overlap(tmp_path: Path) -> None:
    cands = {
        "p": [
            {"kind": ANCHOR, "polygon": box(0, 0, 2, 2), "n_mmsi": 3},
            {"kind": BERTH, "polygon": box(1, 1, 2, 2), "n_mmsi": 2},
        ]
    }
    path = tmp_path / "g.yaml"
    path.write_text(yaml.safe_dump(to_config(cands)))
    df = pl.DataFrame({"lat": [0.5, 1.5, 9.0], "lon": [0.5, 1.5, 9.0]})
    out = classify_positions(df, load_geofences(path))
    assert out["zone"].to_list() == [ANCHOR, BERTH, None]


def test_draft_candidates_finds_synthetic_anchorage_and_berth() -> None:
    def pt(mmsi: int, lat: float, lon: float, sog: float, nav: int) -> dict:
        return {"mmsi": mmsi, "lat": lat, "lon": lon, "sog": sog, "nav_status": nav}

    rows = [pt(m, -0.30 + k * 0.004, -0.30, 0.1, 1) for k, m in enumerate((101, 102, 103))]
    rows += [pt(m, 0.30, 0.30 + k * 0.002, 0.0, 5) for k, m in enumerate((201, 202))]
    cands = draft_candidates(pl.DataFrame(rows), CandidateParams())
    kinds = sorted(c["kind"] for c in cands)
    assert kinds == [ANCHOR, BERTH]
    assert {c["kind"]: c["n_mmsi"] for c in cands} == {ANCHOR: 3, BERTH: 2}


def test_episode_params_defaults_match_the_spec() -> None:
    p = EpisodeParams()
    assert p.max_sog == 0.5
    assert p.min_dwell == timedelta(minutes=30)
    assert p.max_gap == timedelta(hours=6)
