"""Robustness suite: MCPT p-value sanity on coin-flip vs look-ahead-
biased fixtures (plan's own validation targets), bootstrap band
coverage, and walk-forward window math. Fixed seeds throughout — a
statistical test with an unseeded RNG is a flaky test."""

import numpy as np
from datetime import date

from app.backtests.robustness import (
    bootstrap,
    permutation_test,
    walk_forward_efficiency,
    walk_forward_windows,
)

UNDERLYING_SEED = 7
ENTRY_SEED = 123
N_DAYS = 500
HOLDING = 10
N_TRADES = 30


def _underlying():
    rng = np.random.default_rng(UNDERLYING_SEED)
    return rng.normal(0.0003, 0.01, N_DAYS).tolist()


def _random_entry_trades(underlying):
    rng = np.random.default_rng(ENTRY_SEED)
    u = np.array(underlying)
    starts = rng.integers(0, N_DAYS - HOLDING, N_TRADES)
    returns = [float(np.prod(1 + u[s : s + HOLDING]) - 1) for s in starts]
    return returns, [HOLDING] * N_TRADES


def _look_ahead_biased_trades(underlying):
    """Cherry-picks the best-performing windows in the whole series —
    the entry logic "knows the future," which is exactly what MCPT is
    supposed to catch."""
    u = np.array(underlying)
    windows = [(float(np.prod(1 + u[s : s + HOLDING]) - 1), s) for s in range(N_DAYS - HOLDING)]
    windows.sort(reverse=True)
    best = windows[:N_TRADES]
    return [r for r, _ in best], [HOLDING] * N_TRADES


def test_permutation_test_on_random_entries_yields_a_non_extreme_p_value():
    underlying = _underlying()
    returns, holding = _random_entry_trades(underlying)
    result = permutation_test(returns, holding, underlying, n=2000, seed=99)
    assert result["pValue"] > 0.3


def test_permutation_test_on_look_ahead_biased_entries_yields_a_tiny_p_value():
    underlying = _underlying()
    returns, holding = _look_ahead_biased_trades(underlying)
    result = permutation_test(returns, holding, underlying, n=2000, seed=99)
    assert result["pValue"] < 0.01


def test_permutation_test_mismatched_lengths_raises():
    try:
        permutation_test([0.1, 0.2], [5], [0.01] * 100)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_bootstrap_all_positive_pnls_has_zero_risk_of_ruin():
    result = bootstrap([100.0, 150.0, 80.0, 200.0], starting_equity=10_000, n=500, seed=1)
    assert result["riskOfRuin"] == 0.0


def test_bootstrap_all_negative_pnls_longest_streak_is_trade_count():
    pnls = [-50.0, -60.0, -70.0]
    result = bootstrap(pnls, starting_equity=10_000, n=200, seed=1)
    assert result["longestLosingStreakPercentiles"][50] == len(pnls)


def test_bootstrap_percentiles_are_monotonic():
    result = bootstrap([100.0, -80.0, 50.0, -30.0, 200.0, -100.0], starting_equity=10_000, n=2000, seed=2)
    p = result["terminalEquityPercentiles"]
    assert p[5] <= p[25] <= p[50] <= p[75] <= p[95]


def test_bootstrap_identical_pnls_has_zero_spread():
    # every resample is the same multiset -> every path has the same terminal equity
    result = bootstrap([10.0, 10.0, 10.0, 10.0], starting_equity=1_000, n=500, seed=3)
    p = result["terminalEquityPercentiles"]
    assert p[5] == p[95] == 1_040.0


def test_bootstrap_empty_trades_returns_none_risk_of_ruin():
    result = bootstrap([], starting_equity=10_000, n=100)
    assert result["riskOfRuin"] is None


def test_walk_forward_windows_anchored_rolling():
    windows = walk_forward_windows(
        date(2024, 1, 1), date(2025, 9, 1), is_months=12, oos_months=3, step_months=3
    )
    assert windows[0] == {
        "isStart": date(2024, 1, 1),
        "isEnd": date(2025, 1, 1),
        "oosStart": date(2025, 1, 1),
        "oosEnd": date(2025, 4, 1),
    }
    # every window must fit inside the requested range
    assert all(w["oosEnd"] <= date(2025, 9, 1) for w in windows)
    # anchored: isStart advances by step_months each time, isEnd/oosStart/oosEnd chain
    assert windows[1]["isStart"] == date(2024, 4, 1)


def test_walk_forward_windows_empty_when_range_too_short():
    assert walk_forward_windows(date(2024, 1, 1), date(2024, 6, 1)) == []


def test_walk_forward_efficiency_ratio():
    assert walk_forward_efficiency(0.20, 0.10) == 0.5


def test_walk_forward_efficiency_undefined_when_is_return_zero():
    assert walk_forward_efficiency(0.0, 0.10) is None
