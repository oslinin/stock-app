"""Indicator set for /marketdata/indicators.

Plain-Python like app.indicators.macd (which is reused verbatim): every
series is aligned with the input bars, None where undefined. TA-Lib is a
deferred upgrade; these cover the screener/chart needs (sma, ema, rsi,
bbands, atr, macd).
"""

from __future__ import annotations

import math

from ..indicators.macd import ema as _ema
from ..indicators.macd import macd as _macd


def sma(values: list[float], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    """Wilder's RSI (smoothed averages)."""
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain, avg_loss = gains / period, losses / period

    def to_rsi(g: float, l: float) -> float:
        if l == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + g / l)

    out[period] = to_rsi(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
        out[i] = to_rsi(avg_gain, avg_loss)
    return out


def bbands(
    values: list[float], period: int = 20, num_std: float = 2.0
) -> dict[str, list[float | None]]:
    mid = sma(values, period)
    upper: list[float | None] = [None] * len(values)
    lower: list[float | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        m = mid[i]
        var = sum((v - m) ** 2 for v in window) / period
        sd = math.sqrt(var)
        upper[i] = m + num_std * sd
        lower[i] = m - num_std * sd
    return {"middle": mid, "upper": upper, "lower": lower}


def atr(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> list[float | None]:
    """Wilder's ATR over aligned OHLC series."""
    n = len(closes)
    out: list[float | None] = [None] * n
    if n <= period:
        return out
    trs = [highs[0] - lows[0]]
    for i in range(1, n):
        trs.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
        )
    prev = sum(trs[1 : period + 1]) / period
    out[period] = prev
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + trs[i]) / period
        out[i] = prev
    return out


def compute_indicators(bars: list[dict], names: list[str]) -> dict:
    """Named indicator series over bar dicts ({high, low, close}), keyed
    by indicator name — the /marketdata/indicators payload."""
    closes = [b["close"] for b in bars]
    out: dict = {}
    for name in names:
        if name == "macd":
            out["macd"] = _macd(closes)
        elif name == "rsi":
            out["rsi"] = rsi(closes)
        elif name == "bbands":
            out["bbands"] = bbands(closes)
        elif name.startswith("sma"):
            period = int(name[3:] or 20)
            out[name] = sma(closes, period)
        elif name.startswith("ema"):
            period = int(name[3:] or 20)
            out[name] = _ema(closes, period)
        elif name == "atr":
            highs = [b.get("high", b["close"]) for b in bars]
            lows = [b.get("low", b["close"]) for b in bars]
            out["atr"] = atr(highs, lows, closes)
        else:
            raise ValueError(f"unknown indicator '{name}'")
    return out
