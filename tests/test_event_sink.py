from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd
import pytest

from app.persistence.event_sink import EventSink


@pytest.fixture
def sink_root(tmp_path: Path) -> Path:
    return tmp_path / "fraud"


@pytest.mark.asyncio
async def test_flush_writes_parquet_atomically(sink_root: Path):
    sink = EventSink(sink_root, batch_size=2, flush_secs=60, enabled=True)
    await sink.start()
    try:
        sink.enqueue({"customer_id": 1, "event_id": 1, "operaton_amt": 100}, "web")
        sink.enqueue({"customer_id": 1, "event_id": 2, "operaton_amt": 200}, "web")
        # batch_size=2 triggers flush; allow loop iteration
        for _ in range(50):
            files = list((sink_root / "events").rglob("*.parquet"))
            if files:
                break
            await asyncio.sleep(0.05)
        files = list((sink_root / "events").rglob("*.parquet"))
        assert files, "expected at least one parquet file"
        # No leftover .tmp
        assert not list((sink_root / "events").rglob("*.tmp"))
        df = pd.read_parquet(files[0])
        assert len(df) == 2
        assert set(df["event_id"]) == {1, 2}
    finally:
        await sink.stop()


@pytest.mark.asyncio
async def test_web_and_mobile_go_to_separate_dirs(sink_root: Path):
    sink = EventSink(sink_root, batch_size=1, flush_secs=60, enabled=True)
    await sink.start()
    try:
        sink.enqueue({"customer_id": 1, "event_id": 1}, "web")
        sink.enqueue({"customer_id": 1, "event_id": 2}, "mobile")
        for _ in range(50):
            web = list((sink_root / "events").rglob("*.parquet"))
            mob = list((sink_root / "events_mobile").rglob("*.parquet"))
            if web and mob:
                break
            await asyncio.sleep(0.05)
        assert list((sink_root / "events").rglob("*.parquet"))
        assert list((sink_root / "events_mobile").rglob("*.parquet"))
    finally:
        await sink.stop()


@pytest.mark.asyncio
async def test_flush_on_timeout(sink_root: Path):
    sink = EventSink(sink_root, batch_size=100, flush_secs=1, enabled=True)
    await sink.start()
    try:
        sink.enqueue({"customer_id": 1, "event_id": 1}, "web")
        # wait > flush_secs for periodic flush
        for _ in range(30):
            await asyncio.sleep(0.1)
            files = list((sink_root / "events").rglob("*.parquet"))
            if files:
                break
        assert list((sink_root / "events").rglob("*.parquet"))
    finally:
        await sink.stop()


@pytest.mark.asyncio
async def test_disabled_sink_is_noop(sink_root: Path):
    sink = EventSink(sink_root, batch_size=1, flush_secs=1, enabled=False)
    await sink.start()
    try:
        sink.enqueue({"customer_id": 1, "event_id": 1}, "web")
        await asyncio.sleep(0.2)
        assert not sink_root.exists() or not list(sink_root.rglob("*.parquet"))
    finally:
        await sink.stop()


@pytest.mark.asyncio
async def test_unwritable_fs_does_not_crash(sink_root: Path):
    # Use a path under a regular file (cannot mkdir below it) to force OSError
    blocker = sink_root.parent / "blocker"
    blocker.write_text("not a directory")
    bad_root = blocker / "fraud"
    sink = EventSink(bad_root, batch_size=1, flush_secs=60, enabled=True)
    await sink.start()
    try:
        sink.enqueue({"customer_id": 1, "event_id": 1}, "web")
        # Give loop one cycle — must not raise even though write fails
        await asyncio.sleep(0.2)
        # No parquet anywhere
        assert not list(blocker.parent.rglob("*.parquet"))
    finally:
        await sink.stop()


@pytest.mark.asyncio
async def test_stop_drains_remaining_buffer(sink_root: Path):
    sink = EventSink(sink_root, batch_size=100, flush_secs=60, enabled=True)
    await sink.start()
    sink.enqueue({"customer_id": 1, "event_id": 99}, "web")
    await sink.stop()
    files = list((sink_root / "events").rglob("*.parquet"))
    assert files, "stop() should drain leftover buffer"
    df = pd.read_parquet(files[0])
    assert df["event_id"].tolist() == [99]
