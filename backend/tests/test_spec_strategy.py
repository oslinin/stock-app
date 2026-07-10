"""SpecStrategy: an approved spec wrapped to the existing thin Strategy
ABC contract (metadata()/params_dict()), and registry inclusion — this
is what makes an approved spec "just appear" in /strategies with no
new frontend or route plumbing."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.db import session as db_session
from app.specs import service
from app.specs.schema import ExitRules
from app.specs.spec_strategy import SpecStrategy, load_spec_strategies
from app.strategies.base import Strategy
from app.strategies.registry import build_registry
from tests.test_spec_schema import sample_spec


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    db_session.init_db(Settings(db_url=f"sqlite:///{tmp_path}/test.db"))
    yield
    db_session._engine = None


def approvable_spec(**overrides):
    overrides.setdefault(
        "exit",
        ExitRules(profit_target_pct_credit=50.0, stop_loss_x_credit=2.0, time_exit_dte=21),
    )
    return sample_spec(**overrides)


def test_spec_strategy_matches_abc_contract():
    record = service.create_spec(approvable_spec())
    service.approve_spec(record.id)
    _, version = service.get_spec(record.id)

    strategy = SpecStrategy(record, version.spec())
    assert isinstance(strategy, Strategy)
    meta = strategy.metadata()
    assert set(meta) == {"id", "name", "description", "underlying", "secType", "params"}
    assert meta["underlying"] == "SPY"
    assert meta["id"].startswith("spec:")


def test_load_spec_strategies_only_returns_approved():
    draft = service.create_spec(approvable_spec(meta={
        "name": "still draft", "category": "options", "origin": "manual", "source_ref": "",
    }))
    approved = service.create_spec(approvable_spec(meta={
        "name": "ready to trade", "category": "options", "origin": "manual", "source_ref": "",
    }))
    service.approve_spec(approved.id)

    strategies = load_spec_strategies()
    ids = {s.id for s in strategies}
    assert f"spec:{approved.slug}" in ids
    assert f"spec:{draft.slug}" not in ids


def test_build_registry_includes_approved_spec_strategies():
    approved = service.create_spec(approvable_spec(meta={
        "name": "shows up in strategies", "category": "options", "origin": "manual", "source_ref": "",
    }))
    service.approve_spec(approved.id)

    registry = build_registry(Settings(ibkr_enabled=False))
    assert "vix_hedge" in registry
    assert f"spec:{approved.slug}" in registry
    assert isinstance(registry[f"spec:{approved.slug}"], SpecStrategy)
