"""Async parquet writer for scored events.

todo.md #1 (blocker for daily_flow):
- batch buffer per kind (web / mobile)
- flush on batch_size or flush_secs (whichever first)
- atomic write: pd.DataFrame.to_parquet → tmp file → os.replace
- fire-and-forget: enqueue never raises, errors stay in logs

todo.md #6 (best-effort coverage):
- on each successful flush, log fraction of fields from the canonical schema
  that were present in the batch — gives us field-by-field drift visibility
  without enforcing pydantic.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date
from pathlib import Path
from typing import Literal, Optional

import pandas as pd

from app.core.logging import get_logger

Kind = Literal["web", "mobile"]


class EventSink:
    def __init__(
        self,
        root: Path,
        *,
        batch_size: int = 1000,
        flush_secs: int = 60,
        enabled: bool = True,
        logger=None,
    ) -> None:
        self.root = Path(root).expanduser()
        self.batch_size = max(1, int(batch_size))
        self.flush_secs = max(1, int(flush_secs))
        self.enabled = enabled
        self.logger = logger or get_logger("event_sink")

        self._buf_web: list[dict] = []
        self._buf_mobile: list[dict] = []
        self._flush_signal: Optional[asyncio.Event] = None
        self._stopped: Optional[asyncio.Event] = None
        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._flush_signal = asyncio.Event()
        self._stopped = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="event_sink_loop")
        self.logger.info("event_sink_started", root=str(self.root),
                         batch_size=self.batch_size, flush_secs=self.flush_secs)

    async def stop(self) -> None:
        if self._task is None:
            return
        assert self._stopped is not None
        self._stopped.set()
        if self._flush_signal is not None:
            self._flush_signal.set()
        try:
            await asyncio.wait_for(self._task, timeout=10.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._task.cancel()
        finally:
            await self._flush_all()  # drain
            self._task = None
            self.logger.info("event_sink_stopped")

    # -------------------------------------------------------------------- public
    def enqueue(self, payload: dict, kind: Kind) -> None:
        """Fire-and-forget. Never raises — endpoint must stay responsive."""
        if not self.enabled:
            return
        try:
            buf = self._buf_web if kind == "web" else self._buf_mobile
            buf.append(dict(payload))
            if len(buf) >= self.batch_size and self._flush_signal is not None:
                self._flush_signal.set()
        except Exception as exc:  # pragma: no cover — defensive
            self.logger.warning("event_sink_enqueue_failed", error=str(exc))

    # ------------------------------------------------------------------ internal
    async def _run(self) -> None:
        assert self._flush_signal is not None and self._stopped is not None
        while not self._stopped.is_set():
            try:
                await asyncio.wait_for(self._flush_signal.wait(), timeout=self.flush_secs)
            except asyncio.TimeoutError:
                pass
            self._flush_signal.clear()
            if self._stopped.is_set():
                break
            await self._flush_all()

    async def _flush_all(self) -> None:
        await self._flush_kind("web")
        await self._flush_kind("mobile")

    async def _flush_kind(self, kind: Kind) -> None:
        buf = self._buf_web if kind == "web" else self._buf_mobile
        if not buf:
            return
        batch, buf[:] = buf[:], []  # snapshot + atomic clear
        try:
            await asyncio.to_thread(self._write_parquet, batch, kind)
        except Exception as exc:
            self.logger.error("event_sink_flush_failed", kind=kind, rows=len(batch),
                              error=str(exc))

    def _write_parquet(self, batch: list[dict], kind: Kind) -> None:
        subdir = "events" if kind == "web" else "events_mobile"
        target_dir = self.root / subdir / f"dt={date.today().isoformat()}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"part-{uuid.uuid4().hex}.parquet"
        tmp = target.with_suffix(".parquet.tmp")
        df = pd.DataFrame(batch)
        df.to_parquet(tmp, engine="pyarrow", index=False)
        os.replace(tmp, target)
        self.logger.info(
            "event_sink_flush",
            kind=kind,
            rows=len(batch),
            path=str(target),
            coverage=_coverage(batch, kind),
        )


def _coverage(batch: list[dict], kind: Kind) -> dict[str, float]:
    """Per-field presence rate in batch (todo.md #6 best-effort)."""
    from contracts import EVENT_FIELDS_WEB, EVENT_FIELDS_MOBILE

    fields = EVENT_FIELDS_WEB if kind == "web" else EVENT_FIELDS_MOBILE
    n = len(batch)
    if n == 0:
        return {}
    return {
        f: round(sum(1 for p in batch if p.get(f) is not None) / n, 3)
        for f in fields
    }
