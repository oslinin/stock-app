from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request

from ..security import require_token

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@router.get("/ibkr/status", dependencies=[Depends(require_token)])
def ibkr_status(request: Request) -> dict:
    return request.app.state.ib.status()
