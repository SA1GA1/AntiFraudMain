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
        app.state.llm = None
        app.state.merchant = None

        if load_models:
            from app.deps import build_runtime

            log.info("loading runtime", mobile_path=str(settings.mobile_model_path))
            runtime = build_runtime(settings)
            app.state.models = runtime.models
            app.state.history = runtime.history
            app.state.llm = runtime.llm
            app.state.merchant = runtime.merchant
            log.info("runtime ready")
        else:
            log.info("runtime skipped (load_models=False)")

        yield

        if app.state.llm is not None:
            await app.state.llm.aclose()
        if app.state.merchant is not None:
            await app.state.merchant.aclose()

    app = FastAPI(title="AntiFraud Backend", version=VERSION, lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": VERSION}

    from app.api import behavior, chat, merchant

    app.include_router(behavior.router)
    app.include_router(chat.router)
    app.include_router(merchant.router)

    return app


app = create_app()
