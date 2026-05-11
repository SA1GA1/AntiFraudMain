"""DI: построение runtime-объектов при старте FastAPI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Request

from app.config import Settings
from app.ml.customer_history import maybe_load
from app.ml.loader import LocalFileLoader, ModelLoader


@dataclass
class Runtime:
    models: ModelLoader
    history: object  # CustomerHistory | None
    llm: object  # OllamaClient | None
    merchant: object  # MerchantClient | None


def build_runtime(settings: Settings) -> Runtime:
    loader = LocalFileLoader(
        mobile_path=settings.mobile_model_path,
        web_path=settings.web_model_path,
    )
    history = maybe_load(settings.customer_history_path)

    from app.llm.client import OllamaClient
    from app.pipelines.merchant.enrich import MerchantClient

    llm = OllamaClient(
        base_url=settings.ollama_url,
        model=settings.ollama_model,
        timeout_ms=settings.ollama_timeout_ms,
    )
    merchant = MerchantClient(base_url=settings.merchant_api_url)

    return Runtime(models=loader, history=history, llm=llm, merchant=merchant)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_loader(request: Request) -> Optional[ModelLoader]:
    return request.app.state.models


def get_history(request: Request):
    return request.app.state.history


def get_llm(request: Request):
    return request.app.state.llm


def get_merchant(request: Request):
    return request.app.state.merchant
