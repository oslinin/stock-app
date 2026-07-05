from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..security import require_token

router = APIRouter(dependencies=[Depends(require_token)])


def _strategy(request: Request, strategy_id: str):
    strategy = request.app.state.registry.get(strategy_id)
    if strategy is None:
        raise HTTPException(404, f"unknown strategy {strategy_id!r}")
    return strategy


@router.get("/screener/{strategy_id}/state")
async def state(strategy_id: str, request: Request) -> dict:
    strategy = _strategy(request, strategy_id)
    engine = request.app.state.engine
    st = await engine.market_state(strategy)
    return engine.state_payload(strategy, st)


@router.get("/screener/{strategy_id}/verdict")
async def verdict(strategy_id: str, request: Request) -> dict:
    strategy = _strategy(request, strategy_id)
    return await request.app.state.engine.verdict(strategy)


@router.get("/screener/{strategy_id}/spread")
async def spread(
    strategy_id: str,
    request: Request,
    expiry: str | None = Query(default=None, pattern=r"^\d{8}$"),
    width: float | None = Query(default=None, gt=0, le=5),
    contracts: int = Query(default=1, ge=1, le=100),
) -> dict:
    strategy = _strategy(request, strategy_id)
    payload, _ = await request.app.state.engine.spread(
        strategy, expiry=expiry, width=width, contracts_count=contracts
    )
    return payload
