"""iv_snapshot job: syncs the daily IV series from an iv_history-capable
provider (IBKR IV index backfill), idempotently; skips cleanly when no
such provider is registered. Fake providers, real (in-memory) SQLite."""

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
    """Registered but lacking the iv_history capability (like yfinance)."""

    name = "yfinance"
    capabilities = frozenset({"quote", "chain", "expiries"})
    latency = "delayed"


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


def test_skips_cleanly_without_iv_history_provider():
    registry = ProviderRegistry()
    registry.register(ChainOnlyProvider())
    asyncio.run(iv_snapshot(registry, settings()))  # must not raise
    assert stored() == []
