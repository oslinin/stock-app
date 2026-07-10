"""Provider layer: provenance envelope, capability routing, AV budget guard.

Pure logic — fake providers and a fake clock, no network.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.dataproviders.alphavantage import BudgetExceeded, CallBudget, InMemoryCallStore
from app.dataproviders.base import ProviderError, envelope
from app.dataproviders.registry import ProviderRegistry


class FakeProvider:
    def __init__(self, name, capabilities, latency="delayed"):
        self.name = name
        self.capabilities = frozenset(capabilities)
        self.latency = latency

    async def quote(self, symbol):
        return {"symbol": symbol, "price": 100.0}


# ---------------------------------------------------------------- envelope


def test_envelope_shape():
    provider = FakeProvider("yfinance", {"quote"}, latency="delayed")
    asof = datetime(2026, 7, 8, 15, 30, tzinfo=timezone.utc)
    out = envelope({"price": 1.0}, provider, asof=asof)
    assert set(out) == {"data", "provenance"}
    assert out["data"] == {"price": 1.0}
    prov = out["provenance"]
    assert prov["source"] == "yfinance"
    assert prov["latency"] == "delayed"
    assert prov["asof"] == asof.isoformat()


def test_envelope_defaults_asof_to_now():
    out = envelope([], FakeProvider("ibkr", {"quote"}, latency="live"))
    # parses back as an aware datetime close to now
    asof = datetime.fromisoformat(out["provenance"]["asof"])
    assert asof.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - asof).total_seconds()) < 5
    assert out["provenance"]["latency"] == "live"


# ---------------------------------------------------------------- registry


def make_registry():
    reg = ProviderRegistry()
    reg.register(FakeProvider("yfinance", {"quote", "bars", "chain"}))
    reg.register(FakeProvider("ibkr", {"quote", "chain"}, latency="live"))
    reg.register(FakeProvider("alphavantage", {"historical_options"}))
    return reg


def test_route_by_capability_prefers_registration_order():
    reg = make_registry()
    assert reg.route("quote").name == "yfinance"
    assert reg.route("historical_options").name == "alphavantage"


def test_route_by_explicit_source():
    reg = make_registry()
    assert reg.route("quote", source="ibkr").name == "ibkr"


def test_route_explicit_source_without_capability_fails():
    reg = make_registry()
    with pytest.raises(ProviderError, match="does not support"):
        reg.route("bars", source="ibkr")


def test_route_unknown_source_fails():
    reg = make_registry()
    with pytest.raises(ProviderError, match="unknown provider"):
        reg.route("quote", source="bloomberg")


def test_route_unsupported_capability_fails():
    reg = make_registry()
    with pytest.raises(ProviderError, match="no provider"):
        reg.route("teleportation")


def test_describe_lists_capabilities_and_latency():
    listed = ProviderRegistry()
    listed.register(FakeProvider("ibkr", {"quote"}, latency="live"))
    (entry,) = listed.describe()
    assert entry["name"] == "ibkr"
    assert entry["capabilities"] == ["quote"]
    assert entry["latency"] == "live"


# ---------------------------------------------------------- AV budget guard


class FakeClock:
    def __init__(self, start):
        self.current = start

    def now(self):
        return self.current

    def advance(self, **kwargs):
        self.current = self.current + timedelta(**kwargs)


def test_budget_guard_blocks_call_26():
    clock = FakeClock(datetime(2026, 7, 8, 9, 0, tzinfo=timezone.utc))
    budget = CallBudget(limit=25, now=clock.now, store=InMemoryCallStore())
    for _ in range(25):
        budget.spend()
    assert budget.remaining() == 0
    with pytest.raises(BudgetExceeded):
        budget.spend()


def test_budget_guard_resets_next_day():
    clock = FakeClock(datetime(2026, 7, 8, 23, 0, tzinfo=timezone.utc))
    budget = CallBudget(limit=2, now=clock.now, store=InMemoryCallStore())
    budget.spend()
    budget.spend()
    with pytest.raises(BudgetExceeded):
        budget.spend()
    clock.advance(hours=2)  # crosses midnight UTC
    budget.spend()  # fresh day, fresh budget
    assert budget.remaining() == 1


def test_budget_guard_same_day_calls_accumulate_in_store():
    clock = FakeClock(datetime(2026, 7, 8, 9, 0, tzinfo=timezone.utc))
    store = InMemoryCallStore()
    # two guards sharing one store (e.g. process restart) share the count
    CallBudget(limit=5, now=clock.now, store=store).spend()
    budget = CallBudget(limit=5, now=clock.now, store=store)
    assert budget.remaining() == 4
