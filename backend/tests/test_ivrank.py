"""IV rank / IV percentile math and ATM-IV extraction from a chain snapshot."""

import pytest

from app.analytics.ivrank import atm_iv_from_chain, iv_percentile, iv_rank


def test_iv_rank_extremes():
    history = [0.10 + i * (0.20 / 251) for i in range(252)]  # 0.10 .. 0.30
    assert iv_rank(history, current=0.30) == pytest.approx(100.0)
    assert iv_rank(history, current=0.10) == pytest.approx(0.0)


def test_iv_rank_midpoint():
    history = [0.10, 0.20, 0.30]
    assert iv_rank(history, current=0.15) == pytest.approx(25.0)
    assert iv_rank(history, current=0.25) == pytest.approx(75.0)


def test_iv_percentile_counts_days_below():
    history = [0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.22, 0.24, 0.26, 0.28]
    # 8 of 10 observations (0.10 .. 0.24) are below 0.25
    assert iv_percentile(history, current=0.25) == pytest.approx(80.0)
    assert iv_percentile(history, current=0.05) == pytest.approx(0.0)
    assert iv_percentile(history, current=0.99) == pytest.approx(100.0)


def test_degenerate_series():
    assert iv_rank([], current=0.2) is None
    assert iv_rank([0.2, 0.2, 0.2], current=0.2) is None  # flat range: undefined
    assert iv_percentile([], current=0.2) is None


def test_atm_iv_from_chain_averages_call_and_put_at_nearest_strike():
    rows = [
        {"strike": 95.0, "right": "C", "iv": 0.30},
        {"strike": 95.0, "right": "P", "iv": 0.32},
        {"strike": 100.0, "right": "C", "iv": 0.22},
        {"strike": 100.0, "right": "P", "iv": 0.24},
        {"strike": 105.0, "right": "C", "iv": 0.28},
    ]
    assert atm_iv_from_chain(rows, spot=100.4) == pytest.approx(0.23)
    # spot nearest 105: only a call there -> use what exists
    assert atm_iv_from_chain(rows, spot=104.0) == pytest.approx(0.28)


def test_atm_iv_from_chain_skips_missing_iv():
    rows = [
        {"strike": 100.0, "right": "C", "iv": None},
        {"strike": 100.0, "right": "P", "iv": 0.24},
    ]
    assert atm_iv_from_chain(rows, spot=100.0) == pytest.approx(0.24)
    assert atm_iv_from_chain([], spot=100.0) is None
    assert (
        atm_iv_from_chain([{"strike": 100.0, "right": "C", "iv": None}], spot=100.0)
        is None
    )
