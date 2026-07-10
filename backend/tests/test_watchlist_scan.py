"""watchlist_scan: a pure pacing-respecting batch plan, plus the async
job's idempotency (skip a symbol already scanned today) — same
fake-provider style as test_iv_snapshot.py, no network."""

import asyncio

import pytest
from sqlmodel import select

from app.config import Settings
from app.db import session as db_session
from app.db.session import init_db, session_scope
from app.watchlist.models import SymbolMetrics, WatchlistItem
from app.watchlist.scan_job import CHUNK_SIZE, batch_plan, watchlist_scan


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    init_db(Settings(db_url=f"sqlite:///{tmp_path}/test.db"))
    yield
    db_session._engine = None


# ------------------------------------------------------------ batch_plan


def test_batch_plan_respects_chunk_size():
    symbols = [f"SYM{i}" for i in range(25)]
    batches = batch_plan(symbols, chunk_size=10)
    assert [len(b) for b in batches] == [10, 10, 5]
    assert sum(batches, []) == symbols


def test_batch_plan_default_chunk_size_matches_module_constant():
    symbols = [f"SYM{i}" for i in range(3)]
    assert batch_plan(symbols) == batch_plan(symbols, chunk_size=CHUNK_SIZE)


def test_batch_plan_empty_input():
    assert batch_plan([]) == []


# --------------------------------------------------------- scan job (async)


class FakeChainProvider:
    name = "fake"
    capabilities = frozenset({"quote", "bars", "chain", "expiries"})
    latency = "delayed"

    def __init__(self):
        self.calls = []

    async def quote(self, symbol):
        self.calls.append(("quote", symbol))
        return {"symbol": symbol, "price": 100.0}

    async def bars(self, symbol, period="1y", interval="1d"):
        self.calls.append(("bars", symbol))
        return [{"close": float(100 + (i % 5))} for i in range(260)]

    async def expiries(self, symbol):
        self.calls.append(("expiries", symbol))
        return ["2026-08-21"]

    async def chain(self, symbol, expiry):
        self.calls.append(("chain", symbol))
        rows = []
        for strike, delta, iv, oi in [
            (95.0, -0.25, 0.28, 400),
            (100.0, -0.50, 0.30, 900),
            (105.0, -0.75, 0.32, 300),
        ]:
            rows.append(
                {
                    "expiry": expiry,
                    "strike": strike,
                    "right": "P",
                    "bid": 1.90,
                    "ask": 2.10,
                    "iv": iv,
                    "delta": delta,
                    "openInterest": oi,
                }
            )
        return rows


def seed_watchlist(symbols):
    with session_scope() as session:
        for s in symbols:
            session.add(WatchlistItem(symbol=s))


def stored_metrics():
    with session_scope() as session:
        rows = session.exec(select(SymbolMetrics)).all()
        return [
            {
                "symbol": r.symbol,
                "underlying_px": r.underlying_px,
                "sampled_dte": r.sampled_dte,
                "premium_yield": r.premium_yield,
            }
            for r in rows
        ]


def test_scan_writes_one_row_per_watchlist_symbol():
    seed_watchlist(["SPY", "QQQ"])
    provider = FakeChainProvider()
    asyncio.run(watchlist_scan(provider, Settings()))
    rows = stored_metrics()
    assert {r["symbol"] for r in rows} == {"SPY", "QQQ"}
    spy = next(r for r in rows if r["symbol"] == "SPY")
    assert spy["underlying_px"] == pytest.approx(100.0)
    assert spy["sampled_dte"] is not None
    assert spy["premium_yield"] > 0


def test_scan_is_idempotent_per_symbol_per_day():
    seed_watchlist(["SPY"])
    provider = FakeChainProvider()
    asyncio.run(watchlist_scan(provider, Settings()))
    asyncio.run(watchlist_scan(provider, Settings()))
    assert len(stored_metrics()) == 1


def test_scan_skips_a_symbol_whose_provider_call_fails():
    from app.dataproviders.base import ProviderError

    class FlakyProvider(FakeChainProvider):
        async def quote(self, symbol):
            if symbol == "BROKEN":
                raise ProviderError("no quote")
            return await super().quote(symbol)

    seed_watchlist(["SPY", "BROKEN"])
    asyncio.run(watchlist_scan(FlakyProvider(), Settings()))  # must not raise
    rows = stored_metrics()
    assert {r["symbol"] for r in rows} == {"SPY"}
