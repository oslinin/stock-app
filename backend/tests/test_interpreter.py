"""Condition interpreter: each evaluator is a pure function of
(params, MarketContext); AND semantics across a condition list; an
unsupported kind fails closed instead of crashing or silently passing."""

import asyncio
from datetime import datetime, timezone

import pytest

from app.specs.interpreter import CONDITION_EVALUATORS, MarketContext, evaluate_all
from app.specs.schema import Condition

SUPPORTED_KINDS = {
    "iv_rank_gte",
    "iv_rank_lte",
    "dte_between",
    "delta_between",
    "vix_below",
    "vix_above",
    "price_above_sma",
    "price_below_sma",
    "day_of_week_in",
    "credit_min_pct_width",
}


def run(kind, params, context):
    evaluator = CONDITION_EVALUATORS[kind]
    return asyncio.run(evaluator(params, context))


def test_all_ten_first_conditions_registered():
    assert SUPPORTED_KINDS == set(CONDITION_EVALUATORS)


def test_iv_rank_gte_and_lte():
    ctx = MarketContext(current_iv=0.30, iv_history=[0.10, 0.20, 0.30, 0.40])
    passed = run("iv_rank_gte", {"value": 50}, ctx)
    assert passed.passed and passed.observed == pytest.approx(66.667, abs=0.01)
    assert not run("iv_rank_gte", {"value": 90}, ctx).passed
    assert run("iv_rank_lte", {"value": 90}, ctx).passed
    assert not run("iv_rank_lte", {"value": 50}, ctx).passed


def test_iv_rank_missing_data_fails_closed():
    ctx = MarketContext()
    result = run("iv_rank_gte", {"value": 50}, ctx)
    assert not result.passed
    assert result.observed is None


def test_dte_between():
    ctx = MarketContext(dte=30)
    assert run("dte_between", {"min": 21, "max": 45}, ctx).passed
    assert not run("dte_between", {"min": 45, "max": 60}, ctx).passed
    assert not run("dte_between", {"min": 21, "max": 45}, MarketContext()).passed


def test_delta_between():
    ctx = MarketContext(delta=0.28)
    assert run("delta_between", {"min": 0.16, "max": 0.30}, ctx).passed
    assert not run("delta_between", {"min": 0.30, "max": 0.45}, ctx).passed


def test_vix_below_and_above():
    ctx = MarketContext(vix=18.5)
    assert run("vix_below", {"value": 20}, ctx).passed
    assert not run("vix_above", {"value": 20}, ctx).passed
    assert run("vix_above", {"value": 15}, ctx).passed


def test_price_above_and_below_sma():
    closes = [float(100 + i) for i in range(60)]  # steadily rising -> price > SMA
    ctx = MarketContext(price=closes[-1], closes=closes)
    above = run("price_above_sma", {"period": 20}, ctx)
    assert above.passed
    assert above.observed is not None
    assert not run("price_below_sma", {"period": 20}, ctx).passed


def test_price_vs_sma_insufficient_history_fails_closed():
    ctx = MarketContext(price=100.0, closes=[100.0, 101.0])
    result = run("price_above_sma", {"period": 20}, ctx)
    assert not result.passed
    assert result.observed is None


def test_day_of_week_in():
    monday = datetime(2026, 7, 6, tzinfo=timezone.utc)  # a Monday
    ctx = MarketContext(now=monday)
    assert run("day_of_week_in", {"days": ["mon", "wed", "fri"]}, ctx).passed
    assert not run("day_of_week_in", {"days": ["tue", "thu"]}, ctx).passed


def test_credit_min_pct_width():
    ctx = MarketContext(credit_pct_width=0.35)
    assert run("credit_min_pct_width", {"value": 0.33}, ctx).passed
    assert not run("credit_min_pct_width", {"value": 0.40}, ctx).passed


# ---------------------------------------------------------- AND semantics


def test_evaluate_all_and_semantics():
    ctx = MarketContext(vix=18.0, current_iv=0.30, iv_history=[0.1, 0.2, 0.3, 0.4])
    conditions = [
        Condition(kind="vix_below", params={"value": 20}),
        Condition(kind="iv_rank_gte", params={"value": 50}),
    ]
    passed, checks = asyncio.run(evaluate_all(conditions, ctx))
    assert passed is True
    assert len(checks) == 2
    assert all(c["pass"] for c in checks)


def test_evaluate_all_fails_if_any_condition_fails():
    ctx = MarketContext(vix=25.0, current_iv=0.30, iv_history=[0.1, 0.2, 0.3, 0.4])
    conditions = [
        Condition(kind="vix_below", params={"value": 20}),  # fails: vix=25
        Condition(kind="iv_rank_gte", params={"value": 50}),  # passes
    ]
    passed, checks = asyncio.run(evaluate_all(conditions, ctx))
    assert passed is False
    assert checks[0]["pass"] is False
    assert checks[1]["pass"] is True


def test_evaluate_all_empty_conditions_passes_vacuously():
    passed, checks = asyncio.run(evaluate_all([], MarketContext()))
    assert passed is True
    assert checks == []


# ------------------------------------------------------- unsupported kind


def test_unsupported_kind_fails_closed_not_crash():
    conditions = [Condition(kind="gex_regime_is", params={"regime": "positive"})]
    passed, checks = asyncio.run(evaluate_all(conditions, MarketContext()))
    assert passed is False
    assert checks[0]["pass"] is False
    assert "not" in checks[0]["detail"].lower()
