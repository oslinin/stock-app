"""optionlab glue: arbitrary legs -> PoP / expected profit / P&L bounds.

Deterministic (fixed dates, closed-form BS model inside optionlab); values
cross-checked by hand where closed-form: max profit of a credit spread is
the net credit, max loss is width - credit (x100 per contract).
"""

from datetime import date

import pytest

from app.analytics.optionlab_glue import structure_analytics

PUT_CREDIT_SPREAD = [
    {"right": "P", "action": "sell", "strike": 95.0, "premium": 2.0, "qty": 1},
    {"right": "P", "action": "buy", "strike": 90.0, "premium": 1.1, "qty": 1},
]


def run_pcs(**overrides):
    kwargs = dict(
        legs=PUT_CREDIT_SPREAD,
        spot=100.0,
        volatility=0.25,
        interest_rate=0.04,
        start_date=date(2026, 1, 5),
        target_date=date(2026, 2, 20),
    )
    kwargs.update(overrides)
    return structure_analytics(**kwargs)


def test_pcs_payoff_bounds_per_contract():
    out = run_pcs()
    # net credit 0.90 -> max profit $90/contract; width 5 - 0.9 -> max loss $410
    assert out["maxProfit"] == pytest.approx(90.0, abs=1e-6)
    assert out["maxLoss"] == pytest.approx(-410.0, abs=1e-6)


def test_pcs_pop_is_sane():
    out = run_pcs()
    # OTM credit spread: clearly better than a coin flip, never a lock
    assert 0.55 < out["pop"] < 0.95


def test_expected_profit_and_loss_signs():
    out = run_pcs()
    assert out["expectedProfitIfProfitable"] > 0
    assert out["expectedLossIfUnprofitable"] < 0
    assert out["profitRanges"], "profit ranges should be non-empty"


def test_higher_vol_lowers_pop_for_credit_spread():
    calm = run_pcs(volatility=0.15)["pop"]
    wild = run_pcs(volatility=0.60)["pop"]
    assert wild < calm


def test_quantity_scales_pl_not_pop():
    two_lots = [dict(leg, qty=2) for leg in PUT_CREDIT_SPREAD]
    out = run_pcs(legs=two_lots)
    assert out["maxProfit"] == pytest.approx(180.0, abs=1e-6)
    assert out["maxLoss"] == pytest.approx(-820.0, abs=1e-6)
    assert out["pop"] == pytest.approx(run_pcs()["pop"], abs=1e-9)


def test_rejects_bad_legs():
    with pytest.raises(ValueError):
        structure_analytics(
            legs=[{"right": "X", "action": "sell", "strike": 95.0, "premium": 2.0, "qty": 1}],
            spot=100.0,
            volatility=0.25,
            interest_rate=0.04,
            start_date=date(2026, 1, 5),
            target_date=date(2026, 2, 20),
        )
    with pytest.raises(ValueError):
        structure_analytics(
            legs=[],
            spot=100.0,
            volatility=0.25,
            interest_rate=0.04,
            start_date=date(2026, 1, 5),
            target_date=date(2026, 2, 20),
        )
