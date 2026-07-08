"""Black-Scholes greeks/IV wrappers vs independently hand-computed values.

Reference case: S=100, K=100, T=0.5y, r=0.05, sigma=0.20. Constants below
were computed by hand from the closed-form BS formulas (scipy.stats.norm),
NOT copied from vollib output, so a silent library convention change
(per-year theta, per-unit vega, ...) breaks the suite.
"""

import math

import pytest

from app.analytics.greeks import bs_greeks, bs_price, enrich_chain, implied_vol

S, K, T, R, SIGMA = 100.0, 100.0, 0.5, 0.05, 0.20

CALL_PRICE = 6.888729
PUT_PRICE = 4.419720
CALL_DELTA = 0.597734
GAMMA = 0.027359
VEGA_PER_1PCT = 0.273587
CALL_THETA_PER_DAY = -0.022236


def test_call_and_put_price():
    assert bs_price("C", S, K, T, R, SIGMA) == pytest.approx(CALL_PRICE, abs=1e-4)
    assert bs_price("P", S, K, T, R, SIGMA) == pytest.approx(PUT_PRICE, abs=1e-4)


def test_put_call_parity():
    c = bs_price("C", S, K, T, R, SIGMA)
    p = bs_price("P", S, K, T, R, SIGMA)
    assert c - p == pytest.approx(S - K * math.exp(-R * T), abs=1e-9)


def test_greeks_conventions():
    g = bs_greeks("C", S, K, T, R, SIGMA)
    assert g["delta"] == pytest.approx(CALL_DELTA, abs=1e-4)
    assert g["gamma"] == pytest.approx(GAMMA, abs=1e-5)
    # vega must be per 1% vol move, theta per calendar day
    assert g["vega"] == pytest.approx(VEGA_PER_1PCT, abs=1e-4)
    assert g["theta"] == pytest.approx(CALL_THETA_PER_DAY, abs=1e-4)
    p = bs_greeks("P", S, K, T, R, SIGMA)
    assert p["delta"] == pytest.approx(CALL_DELTA - 1.0, abs=1e-4)
    assert p["gamma"] == pytest.approx(GAMMA, abs=1e-5)


def test_implied_vol_round_trip():
    price = bs_price("C", S, K, T, R, SIGMA)
    assert implied_vol(price, "C", S, K, T, R) == pytest.approx(SIGMA, abs=1e-6)
    price = bs_price("P", S, 110.0, T, R, 0.35)
    assert implied_vol(price, "P", S, 110.0, T, R) == pytest.approx(0.35, abs=1e-6)


def test_implied_vol_graceful_on_bad_price():
    # price below intrinsic value has no BS implied vol -> None, not a crash
    assert implied_vol(0.01, "C", 100.0, 50.0, T, R) is None
    assert implied_vol(-1.0, "C", S, K, T, R) is None
    assert implied_vol(5.0, "C", S, K, 0.0, R) is None  # expired


def test_enrich_chain_rows():
    fair = bs_price("C", S, K, T, R, SIGMA)
    rows = [
        # bid/ask straddling the fair price -> mid IV recovers ~sigma
        {"strike": K, "right": "C", "bid": fair - 0.05, "ask": fair + 0.05},
        # no quotes -> enrichment yields None fields, no exception
        {"strike": 120.0, "right": "C", "bid": None, "ask": None},
    ]
    out = enrich_chain(rows, spot=S, t_years=T, r=R)
    assert out[0]["iv"] == pytest.approx(SIGMA, abs=1e-3)
    assert out[0]["delta"] == pytest.approx(CALL_DELTA, abs=1e-2)
    assert out[0]["gamma"] is not None and out[0]["theta"] is not None
    assert out[1]["iv"] is None and out[1]["delta"] is None
