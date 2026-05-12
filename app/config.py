from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mobile_model_path: Path = Field(default=Path("./models/mobile_best.pt"))
    web_model_path: Path = Field(default=Path("./models/web_best.pt"))
    customer_history_path: Path = Field(default=Path("./models/customer_features.parquet"))

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    ollama_timeout_ms: int = 800

    merchant_api_url: str = "http://localhost:9000"

    rule_threshold_behavior: float = 2.0
    rule_threshold_chat: float = 1.5
    rule_threshold_merchant: float = 1.0

    latency_budget_ms: int = 900
    log_level: str = "INFO"

    fraud_root: Path = Field(default=Path("~/fraud").expanduser())
    fraud_model_backend: Literal["local", "mlflow"] = "local"
    mlflow_tracking_uri: str = "file://" + str(Path("~/fraud/mlruns").expanduser())
    fraud_backend_reload_token: str = ""
    event_sink_batch_size: int = 1000
    event_sink_flush_secs: int = 60
    event_sink_enabled: bool = True


def get_settings() -> Settings:
    return Settings()
