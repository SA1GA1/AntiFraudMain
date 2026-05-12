"""Administrative endpoints used by the daily-retrain orchestrator.

- POST /admin/reload-model — swaps the active ModelBundle + customer history for
  a freshly promoted MLFlow Registry version (todo.md #2).
- POST /admin/labels-batch — accepts manual fraud-team labels and persists them
  as parquet under ~/fraud/labels{,_mobile}/ (todo.md #4d).

Both endpoints require a Bearer token (env `FRAUD_BACKEND_RELOAD_TOKEN`).
"""

from __future__ import annotations

import asyncio
import os
import secrets
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

import pandas as pd
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.core.logging import get_logger
from app.deps import get_loader, get_settings
from app.ml.customer_history import CustomerHistory
from app.ml.loader import Kind, ReloadResult
from app.schemas.common import (
    LabelRow,
    LabelsBatchResponse,
    ReloadModelRequest,
    ReloadModelResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"])
_LOGGER = get_logger("admin")

_NAME_TO_KIND: dict[str, Kind] = {
    "fraud_mlp_web": "web",
    "fraud_mlp_mobile": "mobile",
}


def require_admin_token(
    authorization: Annotated[Optional[str], Header()] = None,
    settings=Depends(get_settings),
) -> None:
    expected = settings.fraud_backend_reload_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FRAUD_BACKEND_RELOAD_TOKEN is not configured",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
        )
    presented = authorization[len("Bearer "):]
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid token")


@router.post(
    "/reload-model",
    response_model=ReloadModelResponse,
    dependencies=[Depends(require_admin_token)],
)
async def reload_model(req: ReloadModelRequest, request: Request) -> ReloadModelResponse:
    loader = get_loader(request)
    if loader is None:
        raise HTTPException(status_code=503, detail="ML loader not initialized")

    kind = _NAME_TO_KIND[req.model_name]
    try:
        result: ReloadResult = await asyncio.to_thread(loader.reload, kind, req.version)
    except RuntimeError as exc:
        _LOGGER.error("reload_failed", model_name=req.model_name, error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if result.history_df is not None:
        history = CustomerHistory.from_dataframe(result.history_df)
        if kind == "web":
            request.app.state.history_web = history
        else:
            request.app.state.history_mobile = history

    _LOGGER.info(
        "reload_completed",
        model_name=req.model_name,
        version=result.version,
        previous=result.previous_version,
        history_rows=(0 if result.history_df is None else len(result.history_df)),
    )
    return ReloadModelResponse(
        reloaded=True,
        model_name=req.model_name,
        version=result.version,
        previous_version=result.previous_version,
    )


@router.post(
    "/labels-batch",
    response_model=LabelsBatchResponse,
    dependencies=[Depends(require_admin_token)],
)
async def labels_batch(rows: list[LabelRow], request: Request) -> LabelsBatchResponse:
    if not rows:
        raise HTTPException(status_code=400, detail="empty batch")
    settings = get_settings(request)
    root = Path(settings.fraud_root).expanduser()
    today = date.today().isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()

    written_paths: list[str] = []
    for kind in ("web", "mobile"):
        subset = [r for r in rows if r.kind == kind]
        if not subset:
            continue
        df = pd.DataFrame(
            [
                {
                    "customer_id": r.customer_id,
                    "event_id": r.event_id,
                    "target": int(r.target),
                    "label_dttm": now_iso,
                    "source": "manual",
                }
                for r in subset
            ]
        )
        from contracts.labels_schema import LABELS_SCHEMA

        try:
            df = LABELS_SCHEMA.validate(df, lazy=True)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"labels schema violation: {exc}") from exc

        subdir = "labels" if kind == "web" else "labels_mobile"
        target_dir = root / subdir / f"dt={today}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"part-manual-{uuid.uuid4().hex}.parquet"
        tmp = target.with_suffix(".parquet.tmp")
        df.to_parquet(tmp, engine="pyarrow", index=False)
        os.replace(tmp, target)
        written_paths.append(str(target))
        _LOGGER.info("labels_written", kind=kind, rows=len(df), path=str(target))

    return LabelsBatchResponse(written=len(rows), paths=written_paths)
