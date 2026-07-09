"""build_market_context: same fake-provider style as test_iv_snapshot.py
— no network, no FastAPI TestClient (no route tests exist yet in this
repo; this matches the established pure-function pattern instead)."""

import asyncio
from datetime import date, timedelta

import pytest

from app.api.routes_specs import VIX_SYMBOL, build_market_context
from app.config import Settings
from app.dataproviders.base import ProviderError
from app.dataproviders.models import IVHistory
from app.dataproviders.registry import ProviderRegistry
from app.db import session as db_session
from app.db.session import init_db, session_scope
from app.specs.interpreter import evaluate_all
from app.specs.schema import Condition


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    init_db(Settings(db_url=f"sqlite:///{tmp_path}/test.db"))
    yield
    db_session._engine = None


class FakeProvider:
    name = "fake"
    capabilities = frozenset({"quote", "bars"})
    latency = "delayed"

    def __init__(self, prices):
        self.prices = prices  # symbol -> price

    async def quote(self, symbol):
        if symbol not in self.prices:
            raise ProviderError(f"no quote for {symbol!r}")
        return {"symbol": symbol, "price": self.prices[symbol]}

    async def bars(self, symbol, period="1y", interval="1d"):
        return [{"close": float(100 + i)} for i in range(60)]


def seed_iv_history(symbol, values):
    today = date.today()
    with session_scope() as session:
        for i, v in enumerate(values):
            session.add(
                IVHistory(symbol=symbol, date=today - timedelta(days=len(values) - i), atm_iv=v)
            )


def test_builds_price_closes_vix_and_iv_history():
    seed_iv_history("SPY", [0.10, 0.20, 0.30])
    registry = ProviderRegistry()
    registry.register(FakeProvider({"SPY": 450.0, VIX_SYMBOL: 18.5}))

    ctx = asyncio.run(build_market_context(registry, "SPY"))
    assert ctx.price == 450.0
    assert ctx.vix == 18.5
    assert len(ctx.closes) == 60
    assert ctx.current_iv == 0.30
    assert ctx.iv_history == [0.10, 0.20]


def test_missing_provider_data_leaves_fields_none_not_crash():
    registry = ProviderRegistry()
    registry.register(FakeProvider({}))  # no symbols known -> quote() raises

    ctx = asyncio.run(build_market_context(registry, "SPY"))
    assert ctx.price is None
    assert ctx.vix is None
    assert ctx.iv_history == []


def test_end_to_end_verdict_flips_on_threshold():
    # current (last-seeded) IV sits mid-range, not at the series extreme,
    # so rank lands around 25% -- both a pass and a fail case are real
    seed_iv_history("SPY", [0.10, 0.20, 0.30, 0.15])
    registry = ProviderRegistry()
    registry.register(FakeProvider({"SPY": 450.0, VIX_SYMBOL: 18.0}))
    ctx = asyncio.run(build_market_context(registry, "SPY"))
    assert ctx.current_iv == pytest.approx(0.15)

    low_bar = [Condition(kind="iv_rank_gte", params={"value": 10})]
    passed, _ = asyncio.run(evaluate_all(low_bar, ctx))
    assert passed is True

    high_bar = [Condition(kind="iv_rank_gte", params={"value": 95})]
    passed, _ = asyncio.run(evaluate_all(high_bar, ctx))
    assert passed is False
