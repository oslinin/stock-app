"""In-memory BrokerAdapter for tests (and later, oleg_eval's simulated-
live replay). Deterministic fills: an order placed this tick fills on
the next poll_fill() call, always at its own limit price — no test
doubles of strategy logic, only the broker is simulated."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..brokers.base import DraftOrder, Fill, WhatIf


@dataclass
class SimBroker:
    name: str = "sim"
    mode: str = "paper"
    commission_per_leg: float = 1.0
    _next_order_id: int = 0
    _pending: dict[str, DraftOrder] = field(default_factory=dict)
    _cancelled: set = field(default_factory=set)

    async def what_if(self, draft: DraftOrder) -> WhatIf:
        margin = abs(draft.limit_price) * draft.quantity * 100
        return WhatIf(
            available=True,
            init_margin=margin,
            maint_margin=margin,
            commission=self.commission_per_leg * len(draft.legs),
        )

    async def place(self, draft: DraftOrder) -> tuple[str, Fill | None]:
        self._next_order_id += 1
        order_id = str(self._next_order_id)
        self._pending[order_id] = draft
        return order_id, None

    async def poll_fill(self, order_id: str) -> Fill | None:
        if order_id in self._cancelled:
            return None
        draft = self._pending.pop(order_id, None)
        if draft is None:
            return None
        return Fill(order_id=order_id, fill_price=draft.limit_price, quantity=draft.quantity)

    async def cancel(self, order_id: str) -> None:
        self._cancelled.add(order_id)
        self._pending.pop(order_id, None)
