from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..security import require_token

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("/strategies")
def list_strategies(request: Request) -> list[dict]:
    return [s.metadata() for s in request.app.state.registry.values()]


@router.get("/strategies/{strategy_id}")
def get_strategy(strategy_id: str, request: Request) -> dict:
    strategy = request.app.state.registry.get(strategy_id)
    if strategy is None:
        raise HTTPException(404, f"unknown strategy {strategy_id!r}")
    return strategy.metadata()
