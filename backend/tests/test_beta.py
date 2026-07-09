"""OLS beta of a symbol's daily returns against a benchmark (SPY), plus
the R² low-confidence flag the plan calls for."""

import pytest

from app.portfolio.beta import LOW_R2_THRESHOLD, compute_beta, is_low_confidence

BENCHMARK = [0.010, -0.020, 0.030, 0.000, -0.010, 0.020, 0.015, -0.005, 0.025, -0.015]


def test_perfectly_correlated_series_recovers_exact_beta_and_r2_one():
    symbol = [1.5 * r for r in BENCHMARK]
    beta, r2 = compute_beta(symbol, BENCHMARK)
    assert beta == pytest.approx(1.5)
    assert r2 == pytest.approx(1.0)


def test_uncorrelated_series_gives_low_r2():
    symbol = [0.05, -0.05, 0.05, -0.05, 0.05, -0.05, 0.05, -0.05, 0.05, -0.05]
    _, r2 = compute_beta(symbol, BENCHMARK)
    assert is_low_confidence(r2)


def test_is_low_confidence_threshold():
    assert is_low_confidence(LOW_R2_THRESHOLD - 0.01)
    assert not is_low_confidence(LOW_R2_THRESHOLD + 0.01)


def test_mismatched_lengths_returns_none():
    assert compute_beta([0.01, 0.02], BENCHMARK) is None


def test_too_few_points_returns_none():
    assert compute_beta([0.01], [0.02]) is None


def test_flat_benchmark_returns_none():
    assert compute_beta([0.01, 0.02, 0.03], [0.0, 0.0, 0.0]) is None
