from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.config import get_settings
from app.core.logging import configure_logging, get_logger

VERSION = "0.1.0"


def create_app(load_models: bool = True) -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.models = None
        app.state.history = None
        app.state.history_web = None
        app.state.history_mobile = None
        app.state.llm = None
        app.state.merchant = None
        app.state.event_sink = None

        if load_models:
            from app.deps import build_runtime

            log.info("loading runtime", mobile_path=str(settings.mobile_model_path))
            runtime = build_runtime(settings)
            app.state.models = runtime.models
            app.state.history = runtime.history
            app.state.history_web = runtime.history
            app.state.history_mobile = runtime.history
            app.state.llm = runtime.llm
            app.state.merchant = runtime.merchant
            log.info("runtime ready")
        else:
            log.info("runtime skipped (load_models=False)")

        from app.persistence.event_sink import EventSink

        sink = EventSink(
            root=settings.fraud_root,
            batch_size=settings.event_sink_batch_size,
            flush_secs=settings.event_sink_flush_secs,
            enabled=settings.event_sink_enabled,
        )
        await sink.start()
        app.state.event_sink = sink

        yield

        if app.state.event_sink is not None:
            await app.state.event_sink.stop()
        if app.state.llm is not None:
            await app.state.llm.aclose()
        if app.state.merchant is not None:
            await app.state.merchant.aclose()

    app = FastAPI(title="AntiFraud Backend", version=VERSION, lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": VERSION}

    from app.api import admin, behavior, chat, merchant

    app.include_router(behavior.router)
    app.include_router(chat.router)
    app.include_router(merchant.router)
    app.include_router(admin.router)

    return app


app = create_app()
