"""Waiting episodes: anchorage start -> berthing (MODELO.md section 2, decision P-18).

Input: cargo/tanker positions (all of them, not only inside the port, so a vessel
leaving the port box is seen), already classified by `classify_positions` into
zones. Output: one row per episode with its status:

- completed: confirmed berthing in the same port, without leaving the port box;
  wait_h = berth_start - anchor_start (this is the label).
- left_without_berthing: the vessel was seen outside the port box first.
- censored: the data ends (or the vessel goes silent) before either happens;
  wait_h holds the elapsed time so far, a lower bound.

An event is "confirmed" when the vessel stays in the zone with SOG < max_sog for at
least min_dwell (first to last qualifying point). Points with unknown SOG are
skipped. The vessel's NavigationalStatus is NOT used here (it is typed by hand).

Quality flags:
- label_quality = "low" when the largest AIS gap inside the episode exceeds max_gap;
- arrival_observed = we saw the vessel arrive: its previous point before the
  anchorage run is outside the anchorage (or moving) and at most max_gap earlier.
  Otherwise the vessel may have been anchored long before we first heard it (data
  start, or poor AIS reception at the anchorage), the true anchor_start is unknown
  and the wait is underestimated. Such episodes must not be used for training;
  they are counted separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import polars as pl

from features.geofences import ANCHOR, BERTH


@dataclass(frozen=True)
class EpisodeParams:
    max_sog: float = 0.5
    min_dwell: timedelta = timedelta(minutes=30)
    max_gap: timedelta = timedelta(hours=6)


EPISODE_SCHEMA = {
    "mmsi": pl.Int64,
    "port": pl.Utf8,
    "anchor_zone_id": pl.Utf8,
    "anchor_start": pl.Datetime("us", "UTC"),
    "anchor_confirm": pl.Datetime("us", "UTC"),
    "berth_zone_id": pl.Utf8,
    "berth_start": pl.Datetime("us", "UTC"),
    "end_ts": pl.Datetime("us", "UTC"),
    "wait_h": pl.Float64,
    "status": pl.Utf8,
    "label_quality": pl.Utf8,
    "max_gap_h": pl.Float64,
    "arrival_observed": pl.Boolean,
}


@dataclass
class _Run:
    kind: str
    zone_id: str
    start: datetime
    last: datetime

    def dwell(self) -> timedelta:
        return self.last - self.start


def _vessel_episodes(
    mmsi: int,
    port: str,
    rows: list[dict[str, Any]],
    data_end: datetime,
    p: EpisodeParams,
) -> list[dict[str, Any]]:
    """State machine over one vessel's time-ordered points for one port."""
    episodes: list[dict[str, Any]] = []
    run: _Run | None = None
    open_ep: dict[str, Any] | None = None
    times = [r["ts"] for r in rows]
    # Last point that was NOT part of the current stationary run (arrival evidence).
    last_outside_run: datetime | None = None

    def max_gap(start: datetime, end: datetime) -> timedelta:
        """Largest silence between start and end, counting the edges."""
        inside = [t for t in times if start <= t <= end]
        marks = [start, *inside, end]
        return max((b - a for a, b in zip(marks, marks[1:], strict=False)), default=timedelta(0))

    def close(ep: dict[str, Any], status: str, end: datetime) -> None:
        gap = max_gap(ep["anchor_start"], end)
        ep["status"] = status
        ep["end_ts"] = end
        ep["wait_h"] = (end - ep["anchor_start"]).total_seconds() / 3600
        ep["label_quality"] = "low" if gap > p.max_gap else "normal"
        ep["max_gap_h"] = gap.total_seconds() / 3600
        episodes.append(ep)

    for r in rows:
        ts = r["ts"]
        in_port = r["in_box"]
        if open_ep is not None and not in_port:
            close(open_ep, "left_without_berthing", ts)
            open_ep, run = None, None
            continue

        sog = r["sog"]
        if sog is None:
            continue
        zone = r["zone"] if r["zone_port"] == port else None
        stationary = zone is not None and sog < p.max_sog

        if stationary and run is not None and run.kind == zone and run.zone_id == r["zone_id"]:
            run.last = ts
        elif stationary:
            if run is not None:
                last_outside_run = run.last
            run = _Run(zone, r["zone_id"], ts, ts)
        else:
            run = None
            last_outside_run = ts
            continue

        if run.dwell() < p.min_dwell:
            continue

        if run.kind == ANCHOR and open_ep is None:
            open_ep = {
                "mmsi": mmsi,
                "port": port,
                "anchor_zone_id": run.zone_id,
                "anchor_start": run.start,
                "anchor_confirm": run.start + p.min_dwell,
                "berth_zone_id": None,
                "berth_start": None,
                "arrival_observed": (
                    last_outside_run is not None and run.start - last_outside_run <= p.max_gap
                ),
            }
        elif run.kind == BERTH and open_ep is not None:
            open_ep["berth_zone_id"] = run.zone_id
            open_ep["berth_start"] = run.start
            close(open_ep, "completed", run.start)
            open_ep = None
            # Stay in the berth run: a new episode needs a new anchorage run.

    if open_ep is not None:
        # Silence until the end of the data also counts towards the gap.
        close(open_ep, "censored", data_end)
    return episodes


def extract_episodes(
    positions: pl.DataFrame,
    port_boxes: dict[str, list[list[float]]],
    data_end: datetime | None = None,
    params: EpisodeParams | None = None,
) -> pl.DataFrame:
    """Episodes for every vessel and port.

    `positions` needs mmsi, ts, lat, lon, sog and the zone columns from
    `classify_positions` (zone, zone_id, zone_port).
    """
    p = params or EpisodeParams()
    if positions.is_empty():
        return pl.DataFrame(schema=EPISODE_SCHEMA)
    positions = positions.sort(["mmsi", "ts"])
    data_end = data_end or positions["ts"].max()
    out: list[dict[str, Any]] = []
    for port, ((la0, lo0), (la1, lo1)) in port_boxes.items():
        box_expr = pl.col("lat").is_between(la0, la1) & pl.col("lon").is_between(lo0, lo1)
        flagged = positions.with_columns(box_expr.alias("in_box"))
        # Only vessels that were ever inside this port's box matter.
        seen = flagged.filter(pl.col("in_box"))["mmsi"].unique()
        flagged = flagged.filter(pl.col("mmsi").is_in(seen.implode()))
        cols = ["mmsi", "ts", "sog", "zone", "zone_id", "zone_port", "in_box"]
        for (mmsi,), grp in flagged.select(cols).group_by(["mmsi"], maintain_order=True):
            rows = grp.to_dicts()
            out.extend(_vessel_episodes(int(mmsi), port, rows, data_end, p))
    return pl.DataFrame(out, schema=EPISODE_SCHEMA).sort(["port", "anchor_start"])
