"""Broker adapter protocol: the one seam bot runtime code depends on.
IBKRAdapter (real orders, paper-gated) and SimBroker (in-memory, tests)
both implement this, so bot logic never branches on which broker it's
talking to — a bot can run against SimBroker in pytest with zero IB
dependency, and the plan's later oleg_eval replay reuses the same seam."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class DraftLeg:
    symbol: str
    sec_type: str  # "OPT" | "STK"
    right: str | None  # "C" | "P" | None for stock
    strike: float | None
    expiry: str | None  # ISO date, options only
    action: str  # BUY | SELL
    ratio: int = 1


@dataclass(frozen=True)
class DraftOrder:
    legs: list[DraftLeg] = field(default_factory=list)
    quantity: int = 1
    limit_price: float = 0.0  # net price per combo share; negative = net credit


@dataclass(frozen=True)
class WhatIf:
    available: bool
    init_margin: float | None = None
    maint_margin: float | None = None
    commission: float | None = None
    warning_text: str = ""


@dataclass(frozen=True)
class Fill:
    order_id: str
    fill_price: float
    quantity: int


class BrokerAdapter(Protocol):
    name: str
    mode: str  # "paper" | "live"

    async def what_if(self, draft: DraftOrder) -> WhatIf: ...

    async def place(self, draft: DraftOrder) -> tuple[str, Fill | None]:
        """Returns (order_id, fill). fill is None when the order is
        pending rather than filled synchronously — the caller polls
        poll_fill() on later ticks."""
        ...

    async def poll_fill(self, order_id: str) -> Fill | None: ...

    async def cancel(self, order_id: str) -> None: ...
