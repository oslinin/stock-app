"""Indicator math for /marketdata/indicators (sma/rsi/bbands/atr dispatch)."""

import pytest

from app.analytics.ta import atr, bbands, compute_indicators, rsi, sma


def test_sma_alignment_and_values():
    out = sma([1, 2, 3, 4, 5], 3)
    assert out == [None, None, 2.0, 3.0, 4.0]


def test_rsi_monotone_up_is_100_and_bounded():
    up = list(range(1, 40))
    values = rsi([float(v) for v in up], period=14)
    assert values[13] is None  # undefined until period+1 samples
    assert values[-1] == pytest.approx(100.0)
    mixed = [100 + ((-1) ** i) * (i % 5) for i in range(60)]
    for v in rsi([float(x) for x in mixed]):
        if v is not None:
            assert 0.0 <= v <= 100.0


def test_bbands_symmetric_around_middle():
    closes = [float(90 + (i % 7)) for i in range(40)]
    bands = bbands(closes, period=20, num_std=2.0)
    i = len(closes) - 1
    mid, up, lo = bands["middle"][i], bands["upper"][i], bands["lower"][i]
    assert up > mid > lo
    assert up - mid == pytest.approx(mid - lo)


def test_atr_constant_range():
    n = 30
    highs = [102.0] * n
    lows = [98.0] * n
    closes = [100.0] * n
    out = atr(highs, lows, closes, period=14)
    assert out[-1] == pytest.approx(4.0)


def test_compute_indicators_dispatch():
    bars = [{"high": c + 1, "low": c - 1, "close": float(c)} for c in range(1, 61)]
    out = compute_indicators(bars, ["macd", "rsi", "bbands", "sma20", "atr"])
    assert set(out) == {"macd", "rsi", "bbands", "sma20", "atr"}
    assert set(out["macd"]) == {"line", "signal", "hist"}
    with pytest.raises(ValueError):
        compute_indicators(bars, ["vwap"])
