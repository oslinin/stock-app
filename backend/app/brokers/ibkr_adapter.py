"""IBKR broker adapter — the ONLY place in this codebase that may ever
set transmit=True, and only for a bot's own paper account with
PAPER_AUTO_TRANSMIT explicitly on ("full autonomy is exactly what paper
is for" — plan). A live bot (mode="live") never auto-transmits in this
phase — live warm-up/per-order approval isn't built yet, so a live order
always stages with transmit=False for a human to review, exactly like
the existing /orders/ticket path.

Every other order-placing path in the app (routes_orders.py,
ibkr/orders.py, this module's own staged path) keeps transmit=False.
test_safety_invariants.py greps the whole app/ tree to keep this file
the single guarded exception.
"""

from __future__ import annotations

import asyncio

from ..config import Settings
from ..ibkr.client import IBClient
from ..ibkr.contracts import IB_TIMEOUT
from ..ibkr.ib_lib import ComboLeg, Contract, Option, Order, Stock
from .base import DraftOrder, Fill, WhatIf

# gateway-paper, TWS-paper — the only ports auto-transmit is allowed on,
# even when paper_auto_transmit=True, so a misconfigured port can't fire
# a live order.
PAPER_PORTS = frozenset({4002, 7497})


def round_to_tick(price: float, tick: float = 0.01) -> float:
    return round(round(price / tick) * tick, 2)


class IBKRAdapter:
    name = "ibkr"

    def __init__(self, client: IBClient, settings: Settings):
        self.client = client
        self.settings = settings

    @property
    def mode(self) -> str:
        return self.settings.ibkr_mode

    async def _qualify_leg(self, leg):
        ib = self.client.require()
        if leg.sec_type == "OPT":
            contract = Option(
                leg.symbol, leg.expiry.replace("-", ""), leg.strike, leg.right, "SMART", currency="USD"
            )
        else:
            contract = Stock(leg.symbol, "SMART", "USD")
        qualified = await asyncio.wait_for(ib.qualifyContractsAsync(contract), IB_TIMEOUT)
        if not qualified:
            raise ValueError(f"could not qualify contract for {leg}")
        return qualified[0]

    async def _build(self, draft: DraftOrder):
        qualified_legs = [await self._qualify_leg(leg) for leg in draft.legs]
        combo = Contract(
            symbol=draft.legs[0].symbol,
            secType="BAG",
            currency="USD",
            exchange="SMART",
        )
        combo.comboLegs = [
            ComboLeg(conId=q.conId, ratio=leg.ratio, action=leg.action, exchange="SMART")
            for q, leg in zip(qualified_legs, draft.legs)
        ]
        order = Order(
            action="BUY",
            orderType="LMT",
            totalQuantity=draft.quantity,
            lmtPrice=round_to_tick(draft.limit_price),
            tif="DAY",
            transmit=False,
        )
        return combo, order

    async def what_if(self, draft: DraftOrder) -> WhatIf:
        ib = self.client.require()
        combo, order = await self._build(draft)
        preview = Order(**{**order.__dict__})
        preview.whatIf = True
        state = await asyncio.wait_for(ib.whatIfOrderAsync(combo, preview), IB_TIMEOUT)
        if state is None:
            return WhatIf(available=False)

        def _f(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        return WhatIf(
            available=True,
            init_margin=_f(getattr(state, "initMarginChange", None)),
            maint_margin=_f(getattr(state, "maintMarginChange", None)),
            commission=_f(getattr(state, "commission", None)),
            warning_text=getattr(state, "warningText", "") or "",
        )

    def _may_auto_transmit(self) -> bool:
        """SAFETY: paper-only, explicitly opted in, and the gateway must
        actually be pointed at a recognized paper port — three
        independent conditions, not just the one flag, before this
        adapter will ever produce transmit=True."""
        return (
            self.settings.ibkr_mode == "paper"
            and self.settings.paper_auto_transmit
            and self.client.settings.ibkr_port in PAPER_PORTS
        )

    async def place(self, draft: DraftOrder) -> tuple[str, Fill | None]:
        ib = self.client.require()
        combo, order = await self._build(draft)
        if self._may_auto_transmit():
            order.transmit = True
        trade = ib.placeOrder(combo, order)
        return str(trade.order.orderId), None

    async def poll_fill(self, order_id: str) -> Fill | None:
        ib = self.client.require()
        for trade in ib.trades():
            if str(trade.order.orderId) == order_id and trade.orderStatus.status == "Filled":
                fills = trade.fills
                avg_price = fills[-1].execution.avgPrice if fills else trade.orderStatus.avgFillPrice
                return Fill(order_id=order_id, fill_price=float(avg_price), quantity=int(trade.order.totalQuantity))
        return None

    async def cancel(self, order_id: str) -> None:
        ib = self.client.require()
        for trade in ib.trades():
            if str(trade.order.orderId) == order_id:
                ib.cancelOrder(trade.order)
                return
