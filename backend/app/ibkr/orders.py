"""Combo (BAG) order construction and staging.

SAFETY: nothing in this module — or anywhere in this codebase — ever sets
transmit=True. Orders are placed with transmit=False so they appear as
staged, untransmitted orders in TWS for a human to review and click Transmit.
The /orders/ticket endpoint is additionally gated by ALLOW_ORDER_STAGING
(default false), and whatIf previews never place anything.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .client import IBClient
from .contracts import IB_TIMEOUT
from .ib_lib import ComboLeg, Contract, Order

VIX_TICK = 0.05


@dataclass(frozen=True)
class OrderLeg:
    con_id: int
    action: str  # BUY / SELL
    description: str = ""


def round_to_tick(price: float, tick: float = VIX_TICK) -> float:
    return round(round(price / tick) * tick, 2)


def build_combo_contract(legs: list[OrderLeg]) -> Contract:
    combo = Contract(
        symbol="VIX",
        secType="BAG",
        currency="USD",
        exchange="CBOE",
    )
    combo.comboLegs = [
        ComboLeg(conId=leg.con_id, ratio=1, action=leg.action, exchange="CBOE")
        for leg in legs
    ]
    return combo


def build_limit_order(quantity: int, net_price_per_share: float) -> Order:
    """BUY combo at the net price. IB's combo convention allows a negative
    limit price when the package is a net credit."""
    return Order(
        action="BUY",
        orderType="LMT",
        totalQuantity=quantity,
        lmtPrice=round_to_tick(net_price_per_share),
        tif="DAY",
        transmit=False,
    )


async def what_if(client: IBClient, contract: Contract, order: Order) -> dict:
    ib = client.require()
    preview = Order(**{**order.__dict__})
    preview.whatIf = True
    state = await asyncio.wait_for(ib.whatIfOrderAsync(contract, preview), IB_TIMEOUT)
    if state is None:
        return {"available": False}

    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return {
        "available": True,
        "initMargin": _f(getattr(state, "initMarginChange", None)),
        "maintMargin": _f(getattr(state, "maintMarginChange", None)),
        "equityWithLoan": _f(getattr(state, "equityWithLoanChange", None)),
        "commission": _f(getattr(state, "commission", None)),
        "warningText": getattr(state, "warningText", "") or "",
    }


def stage(client: IBClient, contract: Contract, order: Order) -> int:
    """Place the combo with transmit=False (staged in TWS, never executed)."""
    ib = client.require()
    assert order.transmit is False, "staged orders must keep transmit=False"
    trade = ib.placeOrder(contract, order)
    return trade.order.orderId
