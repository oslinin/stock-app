"""compute_metrics: win rate, expectancy, max drawdown, CAGR, Sharpe,
trade count — hand-verified fixtures."""

import pytest

from app.backtests.metrics import compute_metrics

TRADES = [
    {"entryDate": "2024-01-01", "exitDate": "2024-01-31", "pnl": 100.0},
    {"entryDate": "2024-02-01", "exitDate": "2024-02-28", "pnl": -50.0},
    {"entryDate": "2024-03-01", "exitDate": "2024-03-31", "pnl": 150.0},
]
EQUITY = [10_000.0, 10_100.0, 10_050.0, 10_200.0]


def test_win_rate_and_expectancy():
    result = compute_metrics(TRADES, EQUITY)
    assert result["winRate"] == pytest.approx(2 / 3)
    assert result["expectancy"] == pytest.approx((100 - 50 + 150) / 3)
    assert result["tradeCount"] == 3


def test_max_drawdown():
    # peak 10100 -> trough 10050 is the only drawdown: (10100-10050)/10100
    result = compute_metrics(TRADES, EQUITY)
    assert result["maxDd"] == pytest.approx((10_100 - 10_050) / 10_100)


def test_cagr_doubling_over_one_year():
    trades = [{"entryDate": "2023-01-01", "exitDate": "2024-01-01", "pnl": 10_000.0}]
    equity = [10_000.0, 20_000.0]
    result = compute_metrics(trades, equity)
    assert result["cagr"] == pytest.approx(1.0, rel=0.01)


def test_sharpe_none_with_a_single_trade():
    trades = [{"entryDate": "2024-01-01", "exitDate": "2024-01-31", "pnl": 100.0}]
    equity = [10_000.0, 10_100.0]
    result = compute_metrics(trades, equity)
    assert result["sharpe"] is None


def test_sharpe_positive_for_steadily_growing_equity():
    result = compute_metrics(TRADES, [10_000.0, 10_100.0, 10_200.0, 10_300.0])
    assert result["sharpe"] > 0


def test_empty_trades_returns_none_fields():
    result = compute_metrics([], [])
    assert result == {
        "cagr": None,
        "winRate": None,
        "expectancy": None,
        "maxDd": None,
        "sharpe": None,
        "tradeCount": 0,
    }
