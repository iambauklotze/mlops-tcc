"""Geofences: anchorage and berth polygons per port (Phase 2, MODELO.md section 2).

Two jobs:
1. Draft *candidate* polygons from where cargo/tanker vessels actually stop
   (data-driven, not from the nautical chart). A human validates them on a map
   before they are frozen in config/geofences.yaml.
2. Load the frozen polygons and classify positions (anchorage / berth / none).

Coordinates are [lat, lon] everywhere in config files (AISStream convention, same
as config/collect.yaml). Shapely works in (x=lon, y=lat), so conversion happens
only at the boundary of this module.

Candidate method (heuristic, parameters in CandidateParams):
- keep stationary points (SOG < max_sog) of cargo/tanker vessels inside the port box;
- label by the vessel's own NavigationalStatus: 1 = at anchor, 5 = moored
  (other statuses are ignored here; the status is filled by hand and is noisy, so
  it is used only to *draw* areas, never to detect events);
- grid the points, give each cell the majority label, join neighbouring cells of
  the same label into components and drop components with few distinct vessels;
- anchorage = convex hull of the component's points plus a margin (open water);
  berth = union of the component's cells plus a small margin (follows the quay);
- where an anchorage overlaps a berth, the berth wins.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl
import shapely
import yaml
from shapely.geometry import MultiPoint, Polygon, box
from shapely.ops import unary_union

ANCHOR, BERTH = "anchorage", "berth"
NAV_AT_ANCHOR, NAV_MOORED = 1, 5


@dataclass(frozen=True)
class CandidateParams:
    max_sog: float = 0.5  # knots; same threshold as the event definitions
    # Anchored ships sit far apart in open water, moored ones line up along quays,
    # so each kind is gridded at its own resolution.
    anchorage_cell_deg: float = 0.015  # ~1.5 km
    berth_cell_deg: float = 0.004  # ~400 m
    min_mmsi_anchorage: int = 3  # distinct vessels needed to keep a component
    min_mmsi_berth: int = 2
    anchorage_margin_deg: float = 0.005  # ~500 m around the convex hull
    berth_margin_deg: float = 0.0015  # ~150 m around the cells
    simplify_deg: float = 0.0005


# --------------------------------------------------------------------------- drafting


def _components(cells: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    """8-connected components of grid cells."""
    seen: set[tuple[int, int]] = set()
    comps: list[set[tuple[int, int]]] = []
    for start in cells:
        if start in seen:
            continue
        comp = {start}
        seen.add(start)
        queue = deque([start])
        while queue:
            i, j = queue.popleft()
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    nb = (i + di, j + dj)
                    if nb in cells and nb not in seen:
                        seen.add(nb)
                        comp.add(nb)
                        queue.append(nb)
        comps.append(comp)
    return comps


def label_cells(points: pl.DataFrame, max_sog: float, cell_deg: float) -> pl.DataFrame:
    """Grid cells with point/vessel counts per label and the majority label.

    `points` needs columns mmsi, lat, lon, sog, nav_status (already filtered to
    cargo/tanker vessels inside the port box).
    """
    c = cell_deg
    return (
        points.filter(
            (pl.col("sog") < max_sog) & pl.col("nav_status").is_in([NAV_AT_ANCHOR, NAV_MOORED])
        )
        .with_columns(
            (pl.col("lat") / c).floor().cast(pl.Int64).alias("ci"),
            (pl.col("lon") / c).floor().cast(pl.Int64).alias("cj"),
            pl.when(pl.col("nav_status") == NAV_AT_ANCHOR)
            .then(pl.lit(ANCHOR))
            .otherwise(pl.lit(BERTH))
            .alias("label"),
        )
        .group_by("ci", "cj")
        .agg(
            (pl.col("label") == ANCHOR).sum().alias("n_anchor"),
            (pl.col("label") == BERTH).sum().alias("n_berth"),
            pl.col("mmsi").filter(pl.col("label") == ANCHOR).unique().alias("mmsi_anchor"),
            pl.col("mmsi").filter(pl.col("label") == BERTH).unique().alias("mmsi_berth"),
        )
        .with_columns(
            pl.when(pl.col("n_anchor") > pl.col("n_berth"))
            .then(pl.lit(ANCHOR))
            .otherwise(pl.lit(BERTH))
            .alias("label")
        )
    )


def draft_candidates(points: pl.DataFrame, params: CandidateParams) -> list[dict[str, Any]]:
    """Candidate polygons [{kind, polygon (shapely, lon/lat), n_mmsi, n_points}]."""
    out: list[dict[str, Any]] = []
    for kind, min_mmsi, c in (
        (ANCHOR, params.min_mmsi_anchorage, params.anchorage_cell_deg),
        (BERTH, params.min_mmsi_berth, params.berth_cell_deg),
    ):
        sub = label_cells(points, params.max_sog, c).filter(pl.col("label") == kind)
        by_cell = {(r["ci"], r["cj"]): r for r in sub.iter_rows(named=True)}
        mmsi_col = "mmsi_anchor" if kind == ANCHOR else "mmsi_berth"
        n_col = "n_anchor" if kind == ANCHOR else "n_berth"
        for comp in _components(set(by_cell)):
            mmsis = set().union(*(set(by_cell[k][mmsi_col]) for k in comp))
            if len(mmsis) < min_mmsi:
                continue
            squares = [box(j * c, i * c, (j + 1) * c, (i + 1) * c) for i, j in comp]
            if kind == ANCHOR:
                # Hull of the real anchored positions (not of the coarse cells).
                coords = [
                    (lon, lat)
                    for lat, lon in points.filter(
                        (pl.col("sog") < params.max_sog) & (pl.col("nav_status") == NAV_AT_ANCHOR)
                    )
                    .select("lat", "lon")
                    .iter_rows()
                    if (int(lat // c), int(lon // c)) in comp
                ]
                hull = MultiPoint(coords).convex_hull
                poly = hull.buffer(params.anchorage_margin_deg)
            else:
                poly = unary_union(squares).buffer(params.berth_margin_deg)
            out.append(
                {
                    "kind": kind,
                    "polygon": poly.simplify(params.simplify_deg),
                    "n_mmsi": len(mmsis),
                    "n_points": int(sum(by_cell[k][n_col] for k in comp)),
                }
            )
    # Berths win over anchorages where they overlap.
    berth_union = unary_union([o["polygon"] for o in out if o["kind"] == BERTH])
    for o in out:
        if o["kind"] == ANCHOR and not berth_union.is_empty:
            o["polygon"] = o["polygon"].difference(berth_union)
    return [o for o in out if not o["polygon"].is_empty]


# --------------------------------------------------------------------------- (de)serialisation


def _rings(geom: Any) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def to_config(port_candidates: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Config dict with polygons as [[lat, lon], ...] exterior rings (holes dropped)."""
    ports: dict[str, Any] = {}
    for port, cands in port_candidates.items():
        entry: dict[str, list[dict[str, Any]]] = {ANCHOR: [], BERTH: []}
        counters = {ANCHOR: 0, BERTH: 0}
        for cand in sorted(cands, key=lambda o: -o["n_mmsi"]):
            for poly in _rings(cand["polygon"]):
                counters[cand["kind"]] += 1
                prefix = "A" if cand["kind"] == ANCHOR else "B"
                entry[cand["kind"]].append(
                    {
                        "id": f"{port}_{prefix}{counters[cand['kind']]}",
                        "n_mmsi": cand["n_mmsi"],
                        "polygon": [[round(y, 5), round(x, 5)] for x, y in poly.exterior.coords],
                    }
                )
        ports[port] = entry
    return {"ports": ports}


@dataclass(frozen=True)
class Geofence:
    id: str
    port: str
    kind: str
    polygon: Polygon  # shapely, x = lon, y = lat


def load_geofences(path: Path) -> list[Geofence]:
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    fences: list[Geofence] = []
    for port, kinds in doc["ports"].items():
        for kind in (ANCHOR, BERTH):
            for item in kinds.get(kind) or []:
                ring = [(lon, lat) for lat, lon in item["polygon"]]
                poly = Polygon(ring)
                if not poly.is_valid:
                    raise ValueError(f"invalid polygon {item['id']}")
                fences.append(Geofence(item["id"], port, kind, poly))
    return fences


def classify_positions(df: pl.DataFrame, fences: list[Geofence]) -> pl.DataFrame:
    """Add columns `zone` (anchorage/berth/null), `zone_id` and `zone_port`.

    Berths are checked before anchorages, so a point in both counts as berth.
    """
    lon = df["lon"].to_numpy()
    lat = df["lat"].to_numpy()
    n = df.height
    zone: list[str | None] = [None] * n
    zone_id: list[str | None] = [None] * n
    zone_port: list[str | None] = [None] * n
    ordered = sorted(fences, key=lambda f: 0 if f.kind == BERTH else 1)
    for fence in ordered:
        shapely.prepare(fence.polygon)
        inside = shapely.contains_xy(fence.polygon, lon, lat)
        for idx in inside.nonzero()[0]:
            if zone[idx] is None:
                zone[idx] = fence.kind
                zone_id[idx] = fence.id
                zone_port[idx] = fence.port
    return df.with_columns(
        pl.Series("zone", zone, dtype=pl.Utf8),
        pl.Series("zone_id", zone_id, dtype=pl.Utf8),
        pl.Series("zone_port", zone_port, dtype=pl.Utf8),
    )
