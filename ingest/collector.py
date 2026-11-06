"""Minimal raw AIS collector for AISStream (Phase 0).

Design rules (see docs/DECISOES.md):
- Every frame received is written unmodified to an append-only raw layer:
  data/raw/date=YYYY-MM-DD/hour=HH/part-<run>-<seq>.jsonl.gz
  Each line is {"recv_ts": <UTC ISO receive time>, "raw": <frame text as received>}.
- A part file is written as "*.inprogress" and renamed when closed, together with a
  ".sha256" checksum sidecar. Finished files are never reopened.
- Connection events (connect, disconnect, gap length, server errors) go to
  data/ops/connection_events.jsonl so collection gaps are measured, never hidden.
- data/ops/heartbeat is touched only when new frames were written (used by the
  container healthcheck).
- The API key is read from the environment and never logged.

Run: python -m ingest.collector --config config/collect.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import gzip
import hashlib
import json
import logging
import os
import random
import signal
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

import yaml
from dotenv import load_dotenv
from websockets.asyncio.client import ClientConnection, connect

AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"
API_KEY_ENV = "AISSTREAM_API_KEY"

log = logging.getLogger("collector")


# --------------------------------------------------------------------------- config


@dataclass(frozen=True)
class CollectorConfig:
    bounding_boxes: list[list[list[float]]]
    data_dir: Path
    flush_interval_s: float
    idle_timeout_s: float
    backoff_initial_s: float
    backoff_max_s: float
    stable_after_s: float


def load_config(path: Path) -> CollectorConfig:
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    c = doc["collection"]
    boxes = c["bounding_boxes"]
    for box in boxes:
        validate_bbox(box)
    return CollectorConfig(
        bounding_boxes=boxes,
        data_dir=Path(c["data_dir"]),
        flush_interval_s=float(c["flush_interval_s"]),
        idle_timeout_s=float(c["idle_timeout_s"]),
        backoff_initial_s=float(c["backoff_initial_s"]),
        backoff_max_s=float(c["backoff_max_s"]),
        stable_after_s=float(c["stable_after_s"]),
    )


def validate_bbox(box: Any) -> None:
    """A bbox is [[lat, lon], [lat, lon]] with valid ranges."""
    if not (isinstance(box, list) and len(box) == 2):
        raise ValueError(f"bbox must have two corners: {box!r}")
    for corner in box:
        if not (isinstance(corner, list) and len(corner) == 2):
            raise ValueError(f"corner must be [lat, lon]: {corner!r}")
        lat, lon = corner
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"corner out of range (expected [lat, lon]): {corner!r}")


def build_subscription(api_key: str, bounding_boxes: list[list[list[float]]]) -> str:
    """Subscription message as documented by AISStream (corners are [lat, lon])."""
    return json.dumps({"APIKey": api_key, "BoundingBoxes": bounding_boxes})


# --------------------------------------------------------------------------- storage


class RawWriter:
    """Append-only, hourly-partitioned gzip JSONL writer for raw frames."""

    def __init__(self, data_dir: Path, run_id: str) -> None:
        self.root = data_dir / "raw"
        self.run_id = run_id
        self._key: tuple[str, str] | None = None
        self._seq = 0
        self._fh: IO[bytes] | None = None
        self._path: Path | None = None
        self.lines_total = 0

    def write(self, recv_ts: datetime, raw: str) -> None:
        key = (recv_ts.strftime("%Y-%m-%d"), recv_ts.strftime("%H"))
        if key != self._key:
            self._rotate(key)
        assert self._fh is not None
        line = json.dumps({"recv_ts": recv_ts.isoformat(), "raw": raw}, ensure_ascii=False)
        self._fh.write(line.encode("utf-8") + b"\n")
        self.lines_total += 1

    def flush(self) -> None:
        if self._fh is not None:
            self._fh.flush()

    def close(self) -> None:
        """Finalize the current part: close, rename, write checksum sidecar."""
        if self._fh is None or self._path is None:
            return
        self._fh.close()
        final = self._path.with_name(self._path.name.removesuffix(".inprogress"))
        if final.exists():  # raw layer is immutable: never replace a finished part
            raise FileExistsError(f"refusing to overwrite raw part {final}")
        os.rename(self._path, final)
        digest = hashlib.sha256(final.read_bytes()).hexdigest()
        final.with_name(final.name + ".sha256").write_text(f"{digest}  {final.name}\n")
        log.info("raw part finalized", extra={"fields": {"file": str(final)}})
        self._fh = None
        self._path = None

    def _rotate(self, key: tuple[str, str]) -> None:
        self.close()
        self._key = key
        self._seq += 1
        part_dir = self.root / f"date={key[0]}" / f"hour={key[1]}"
        part_dir.mkdir(parents=True, exist_ok=True)
        self._path = part_dir / f"part-{self.run_id}-{self._seq:05d}.jsonl.gz.inprogress"
        # "xb": fail rather than ever overwrite an existing file.
        self._fh = gzip.open(self._path, "xb")


class EventLog:
    """Operational events (connections, gaps, errors) as JSON lines."""

    def __init__(self, data_dir: Path, run_id: str) -> None:
        self.ops_dir = data_dir / "ops"
        self.ops_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.ops_dir / "connection_events.jsonl"
        self.heartbeat = self.ops_dir / "heartbeat"
        self.run_id = run_id

    def emit(self, event: str, **fields: Any) -> None:
        rec = {"ts": datetime.now(UTC).isoformat(), "run_id": self.run_id, "event": event, **fields}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.info(event, extra={"fields": fields})

    def touch_heartbeat(self) -> None:
        self.heartbeat.touch()


# --------------------------------------------------------------------------- streaming


class IdleTimeoutError(Exception):
    """No frame received within the configured idle timeout."""


def frame_to_text(frame: str | bytes) -> str:
    # AISStream sends binary frames containing UTF-8 JSON.
    return frame.decode("utf-8") if isinstance(frame, bytes) else frame


def inspect_frame(raw: str) -> dict[str, Any] | None:
    """Return parsed JSON for control frames (errors / subscription confirmation), else None.

    Cheap prefix check so the hot path does not parse every position report.
    """
    head = raw[:64]
    if '"error"' in head or "SubscriptionConfirmation" in raw[:256]:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


async def consume(
    ws: ClientConnection, writer: RawWriter, events: EventLog, cfg: CollectorConfig
) -> None:
    last_flush = time.monotonic()
    written_since_flush = 0
    while True:
        try:
            frame = await asyncio.wait_for(ws.recv(), timeout=cfg.idle_timeout_s)
        except TimeoutError as exc:
            raise IdleTimeoutError(f"no frame for {cfg.idle_timeout_s:.0f}s") from exc
        raw = frame_to_text(frame)
        writer.write(datetime.now(UTC), raw)
        written_since_flush += 1

        control = inspect_frame(raw)
        if control is not None:
            if "error" in control:
                events.emit("server_error", error=str(control["error"]))
            elif control.get("MessageType") == "SubscriptionConfirmation":
                events.emit("subscription_confirmed", message=control.get("Message"))

        now = time.monotonic()
        if now - last_flush >= cfg.flush_interval_s:
            writer.flush()
            if written_since_flush:
                events.touch_heartbeat()
            log.info(
                "flush",
                extra={"fields": {"frames": written_since_flush, "total": writer.lines_total}},
            )
            written_since_flush = 0
            last_flush = now


async def run(cfg: CollectorConfig, api_key: str) -> None:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    writer = RawWriter(cfg.data_dir, run_id)
    events = EventLog(cfg.data_dir, run_id)
    events.emit("start", bounding_boxes=cfg.bounding_boxes)

    backoff = cfg.backoff_initial_s
    last_disconnect_wall: float | None = None
    try:
        while True:
            opened_at: float | None = None
            try:
                async with connect(
                    AISSTREAM_URL, compression="deflate", open_timeout=15, max_size=2**22
                ) as ws:
                    # Must be sent within 3 s of opening, as one complete frame.
                    await ws.send(build_subscription(api_key, cfg.bounding_boxes))
                    opened_at = time.monotonic()
                    gap = (
                        round(time.time() - last_disconnect_wall, 1)
                        if last_disconnect_wall is not None
                        else None
                    )
                    events.emit("connected", gap_since_last_disconnect_s=gap)
                    await consume(ws, writer, events, cfg)
                reason = "closed by server"
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - any failure leads to reconnect
                reason = f"{type(exc).__name__}: {exc}"

            writer.flush()
            last_disconnect_wall = time.time()
            lived = time.monotonic() - opened_at if opened_at is not None else 0.0
            if lived >= cfg.stable_after_s:
                backoff = cfg.backoff_initial_s
            sleep_s = min(backoff, cfg.backoff_max_s) * random.uniform(0.5, 1.0)
            events.emit(
                "disconnected",
                reason=reason,
                connection_lived_s=round(lived, 1),
                retry_in_s=round(sleep_s, 1),
            )
            await asyncio.sleep(sleep_s)
            backoff = min(backoff * 2, cfg.backoff_max_s)
    finally:
        writer.close()
        events.emit("shutdown", frames_written=writer.lines_total)


# --------------------------------------------------------------------------- entrypoint


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rec: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rec.update(getattr(record, "fields", {}) or {})
        return json.dumps(rec, ensure_ascii=False, default=str)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    # websockets logs frames at DEBUG; keep it quiet so the subscription (with key) is never logged.
    logging.getLogger("websockets").setLevel(logging.WARNING)


async def _main_async(cfg: CollectorConfig, api_key: str) -> None:
    task = asyncio.create_task(run(cfg, api_key))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, task.cancel)
    with contextlib.suppress(asyncio.CancelledError):
        await task


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Raw AIS collector (AISStream).")
    parser.add_argument("--config", type=Path, default=Path("config/collect.yaml"))
    args = parser.parse_args(argv)

    setup_logging()
    load_dotenv()
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        log.error(f"{API_KEY_ENV} is not set; copy .env.example to .env and fill it in")
        return 2

    cfg = load_config(args.config)
    asyncio.run(_main_async(cfg, api_key))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
