"""Alpha Vantage HISTORICAL_OPTIONS provider with a hard daily call budget.

The free tier allows 25 requests/day; `CallBudget` refuses call 26
instead of letting Alpha Vantage silently return its rate-limit note.
Calls are logged to `provider_call_log` so the count survives restarts.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Callable, Protocol

import httpx
from sqlmodel import func, select

from .base import HISTORICAL_OPTIONS, ProviderError

AV_URL = "https://www.alphavantage.co/query"


class BudgetExceeded(ProviderError):
    """Daily upstream call budget exhausted."""


class CallStore(Protocol):
    def count(self, day: date) -> int: ...
    def add(self, day: date, endpoint: str = "", symbol: str = "") -> None: ...


class InMemoryCallStore:
    """Test/ephemeral store."""

    def __init__(self) -> None:
        self._counts: dict[date, int] = {}

    def count(self, day: date) -> int:
        return self._counts.get(day, 0)

    def add(self, day: date, endpoint: str = "", symbol: str = "") -> None:
        self._counts[day] = self._counts.get(day, 0) + 1


class DbCallStore:
    """Persists to provider_call_log (imported lazily so pure-logic tests
    never need a database)."""

    def __init__(self, provider: str) -> None:
        self.provider = provider

    def count(self, day: date) -> int:
        from ..db.session import session_scope
        from .models import ProviderCallLog

        with session_scope() as session:
            return session.exec(
                select(func.count())
                .select_from(ProviderCallLog)
                .where(ProviderCallLog.provider == self.provider)
                .where(ProviderCallLog.day == day)
            ).one()

    def add(self, day: date, endpoint: str = "", symbol: str = "") -> None:
        from ..db.session import session_scope
        from .models import ProviderCallLog

        with session_scope() as session:
            session.add(
                ProviderCallLog(
                    provider=self.provider, day=day, endpoint=endpoint, symbol=symbol
                )
            )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CallBudget:
    def __init__(
        self,
        limit: int,
        now: Callable[[], datetime] = _utcnow,
        store: CallStore | None = None,
    ) -> None:
        self.limit = limit
        self.now = now
        self.store = store if store is not None else InMemoryCallStore()

    def _today(self) -> date:
        return self.now().date()

    def remaining(self) -> int:
        return max(0, self.limit - self.store.count(self._today()))

    def spend(self, endpoint: str = "", symbol: str = "") -> None:
        day = self._today()
        if self.store.count(day) >= self.limit:
            raise BudgetExceeded(
                f"daily budget of {self.limit} upstream calls exhausted "
                f"(resets at 00:00 UTC)"
            )
        self.store.add(day, endpoint=endpoint, symbol=symbol)


class AlphaVantageProvider:
    name = "alphavantage"
    capabilities = frozenset({HISTORICAL_OPTIONS})
    latency = "eod"

    def __init__(self, api_key: str, budget: CallBudget | None = None) -> None:
        self.api_key = api_key
        self.budget = budget if budget is not None else CallBudget(
            limit=25, store=DbCallStore(self.name)
        )

    async def historical_options(self, symbol: str, on_date: str | None = None) -> list[dict]:
        """EOD option chain (with greeks/IV) for a symbol, optionally on a
        past date (YYYY-MM-DD). One metered call per request."""
        self.budget.spend(endpoint="HISTORICAL_OPTIONS", symbol=symbol)
        params = {
            "function": "HISTORICAL_OPTIONS",
            "symbol": symbol,
            "apikey": self.api_key,
        }
        if on_date:
            params["date"] = on_date
        payload = await asyncio.to_thread(self._get, params)
        if "data" not in payload:
            # AV signals errors/limits in-band with 200s
            note = payload.get("Note") or payload.get("Information") or str(payload)
            raise ProviderError(f"alphavantage error: {note[:300]}")
        return payload["data"]

    def _get(self, params: dict) -> dict:
        resp = httpx.get(AV_URL, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
