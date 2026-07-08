"""iv_snapshot job: provider-sync first (IBKR IV index backfill), chain
snapshot only as fallback; idempotent either way. Fake providers, real
(in-memory) SQLite."""

import asyncio
from datetime import date, timedelta

import pytest
from sqlmodel import select

from app.config import Settings
from app.dataproviders.models import IVHistory
from app.dataproviders.registry import ProviderRegistry
from app.db import session as db_session
from app.db.session import init_db, session_scope
from app.scheduler.jobs import iv_snapshot


@pytest.fixture(autouse=True)
def memory_db():
    init_db(Settings(iv_snapshot_symbols="SPY", db_url="sqlite://"))
    yield
    db_session._engine = None


def settings():
    return Settings(iv_snapshot_symbols="SPY", db_url="sqlite://")


class IVIndexProvider:
    """A provider exposing a ready-made daily IV series (like IBKR)."""

    name = "ibkr"
    capabilities = frozenset({"iv_history", "quote", "chain", "expiries"})
    latency = "delayed"
    calls = 0

    async def iv_history(self, symbol):
        type(self).calls += 1
        start = date(2026, 7, 1)
        return [
            {"date": (start + timedelta(days=i)).isoformat(), "iv": 0.15 + i * 0.01}
            for i in range(5)
        ]


class ChainOnlyProvider:
    name = "yfinance"
    capabilities = frozenset({"quote", "chain", "expiries"})
    latency = "delayed"

    async def quote(self, symbol):
        return {"symbol": symbol, "price": 100.0}

    async def expiries(self, symbol):
        return [(date.today() + timedelta(days=30)).isoformat()]

    async def chain(self, symbol, expiry):
        return [
            {"strike": 100.0, "right": "C", "iv": 0.22},
            {"strike": 100.0, "right": "P", "iv": 0.24},
        ]


def stored():
    with session_scope() as session:
        rows = session.exec(select(IVHistory).order_by(IVHistory.date)).all()
        return [
            {
                "date": r.date,
                "atm_iv": r.atm_iv,
                "source": r.source,
                "underlying_px": r.underlying_px,
            }
            for r in rows
        ]


def test_sync_backfills_full_series_from_iv_history_provider():
    registry = ProviderRegistry()
    registry.register(ChainOnlyProvider())
    registry.register(IVIndexProvider())
    asyncio.run(iv_snapshot(registry, settings()))
    rows = stored()
    assert len(rows) == 5
    assert rows[0]["atm_iv"] == pytest.approx(0.15)
    assert rows[0]["source"] == "ibkr_iv_index"

    # second run: series unchanged -> no duplicates
    asyncio.run(iv_snapshot(registry, settings()))
    assert len(stored()) == 5


def test_falls_back_to_chain_snapshot_without_iv_history_provider():
    registry = ProviderRegistry()
    registry.register(ChainOnlyProvider())
    asyncio.run(iv_snapshot(registry, settings()))
    rows = stored()
    assert len(rows) == 1
    assert rows[0]["atm_iv"] == pytest.approx(0.23)  # mean of call/put ATM IV
    assert rows[0]["source"] == "yfinance"
    assert rows[0]["underlying_px"] == pytest.approx(100.0)

    # idempotent per day
    asyncio.run(iv_snapshot(registry, settings()))
    assert len(stored()) == 1
