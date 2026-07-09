"""Beta-weighted delta — tastytrade's published formula:
stock: Position Delta x Beta x (Underlying Price / Benchmark Price)
option: Option Delta x Contracts x 100 x Beta x (Underlying Price / Benchmark Price)
(https://support.tastytrade.com/support/s/solutions/articles/43000522492)
Hand-worked numbers below, not a scraped worked example — the support
article 403s from this sandbox."""

import pytest

from app.portfolio.bwdelta import beta_weighted_delta


def test_option_position_hand_worked_example():
    # 0.30 delta x 2 contracts x 100 x 1.5 beta x (50/500) = 9.0
    bwd = beta_weighted_delta(
        delta=0.30, quantity=2, multiplier=100, beta=1.5,
        underlying_price=50, benchmark_price=500,
    )
    assert bwd == pytest.approx(9.0)


def test_stock_position_hand_worked_example():
    # 1.0 delta/share x 40 shares x 1 x 2.0 beta x (25/500) = 4.0
    bwd = beta_weighted_delta(
        delta=1.0, quantity=40, multiplier=1, beta=2.0,
        underlying_price=25, benchmark_price=500,
    )
    assert bwd == pytest.approx(4.0)


def test_short_stock_flips_sign():
    bwd = beta_weighted_delta(
        delta=1.0, quantity=-40, multiplier=1, beta=2.0,
        underlying_price=25, benchmark_price=500,
    )
    assert bwd == pytest.approx(-4.0)


def test_short_put_short_position_combine_to_positive_bwd():
    # short 1 put (quantity=-1), put delta -0.30 -> long-equivalent exposure
    bwd = beta_weighted_delta(
        delta=-0.30, quantity=-1, multiplier=100, beta=1.0,
        underlying_price=100, benchmark_price=500,
    )
    assert bwd == pytest.approx(6.0)  # -0.30 * -1 * 100 * 1.0 * (100/500)


def test_beta_weighting_against_self_is_price_ratio_one():
    # beta-weighting SPY to SPY: ratio is always 1
    bwd = beta_weighted_delta(
        delta=1.0, quantity=100, multiplier=1, beta=1.0,
        underlying_price=500, benchmark_price=500,
    )
    assert bwd == pytest.approx(100.0)
