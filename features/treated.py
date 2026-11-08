"""Read helpers for the treated layer (data/treated/*)."""

from __future__ import annotations

from pathlib import Path

import polars as pl

CARGO_TANKER = (70, 89)  # AIS ship types, inclusive


def vessel_table(data_dir: Path) -> pl.DataFrame:
    """One row per MMSI: most frequent declared ship type and length, last name."""
    sta = pl.read_parquet(data_dir / "treated" / "static" / "*.parquet")
    return sta.group_by("mmsi").agg(
        pl.col("ship_type").drop_nulls().mode().first().alias("ship_type"),
        pl.col("length_m").drop_nulls().mode().first().alias("length_m"),
        pl.col("name").drop_nulls().last().alias("name"),
    )


def load_positions(data_dir: Path, cargo_tanker_only: bool = False) -> pl.DataFrame:
    """All treated positions joined with the vessel table, sorted by mmsi and ts."""
    pos = pl.read_parquet(data_dir / "treated" / "positions" / "*.parquet")
    df = pos.join(vessel_table(data_dir), on="mmsi", how="left")
    if cargo_tanker_only:
        df = df.filter(pl.col("ship_type").is_between(*CARGO_TANKER))
    return df.sort(["mmsi", "ts"])


def in_bbox(df: pl.DataFrame, bbox: list[list[float]]) -> pl.DataFrame:
    """Filter to a [[lat_min, lon_min], [lat_max, lon_max]] box."""
    (la0, lo0), (la1, lo1) = bbox
    return df.filter(pl.col("lat").is_between(la0, la1) & pl.col("lon").is_between(lo0, lo1))
