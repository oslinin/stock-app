from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..ibkr import orders as ib_orders
from ..screener.schemas import OrderRequest
from ..security import require_token

router = APIRouter(dependencies=[Depends(require_token)])


async def _build(request: Request, body: OrderRequest):
    strategy = request.app.state.registry.get(body.strategyId)
    if strategy is None:
        raise HTTPException(404, f"unknown strategy {body.strategyId!r}")
    payload, order_ctx = await request.app.state.engine.spread(
        strategy, expiry=body.expiry, width=body.width, contracts_count=body.contracts
    )
    if order_ctx is None:
        raise HTTPException(
            409, f"no qualifying spread to order: {payload.get('reason', 'not found')}"
        )
    contract = ib_orders.build_combo_contract(order_ctx.legs)
    order = ib_orders.build_limit_order(order_ctx.contracts, order_ctx.net_per_share)
    manual_spec = {
        "expiry": payload["expiry"],
        "orderType": "LMT",
        "limitPrice": order.lmtPrice,
        "quantity": order_ctx.contracts,
        "tif": "DAY",
        "legs": [
            {"action": leg.action, "leg": leg.description, "ratio": 1}
            for leg in order_ctx.legs
        ],
    }
    return payload, contract, order, manual_spec


@router.post("/orders/preview")
async def preview(body: OrderRequest, request: Request) -> dict:
    payload, contract, order, manual_spec = await _build(request, body)
    what_if = await ib_orders.what_if(request.app.state.ib, contract, order)
    return {
        "status": "preview",
        "whatIf": what_if,
        "manualSpec": manual_spec,
        "spread": payload,
        "message": "whatIf preview only — nothing was placed or transmitted.",
    }


@router.post("/orders/ticket")
async def ticket(body: OrderRequest, request: Request) -> dict:
    settings = request.app.state.settings
    payload, contract, order, manual_spec = await _build(request, body)
    if not settings.allow_order_staging:
        return {
            "status": "manual",
            "manualSpec": manual_spec,
            "spread": payload,
            "message": (
                "Order staging is disabled (ALLOW_ORDER_STAGING=false). "
                "Enter this combo manually in IBKR, or enable staging to have it "
                "placed with transmit=false for your review in TWS."
            ),
        }
    order_id = ib_orders.stage(request.app.state.ib, contract, order)
    return {
        "status": "staged",
        "orderId": order_id,
        "transmit": False,
        "manualSpec": manual_spec,
        "spread": payload,
        "message": (
            "4-leg combo staged in TWS with transmit=false. Nothing auto-executes: "
            "review the order in IBKR and click Transmit yourself."
        ),
    }
