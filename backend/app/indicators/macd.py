"""MACD computed with plain Python (no pandas/numpy dependency).

All returned series are aligned with the input list; positions where the
indicator is not yet defined hold None.
"""

from __future__ import annotations


def ema(values: list[float], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    k = 2.0 / (period + 1)
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> dict[str, list[float | None]]:
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    line: list[float | None] = [
        f - s if f is not None and s is not None else None
        for f, s in zip(fast_ema, slow_ema)
    ]
    defined = [v for v in line if v is not None]
    signal_tail = ema(defined, signal)
    sig: list[float | None] = [None] * len(line)
    offset = len(line) - len(defined)
    for i, v in enumerate(signal_tail):
        if v is not None:
            sig[offset + i] = v
    hist: list[float | None] = [
        l - s if l is not None and s is not None else None for l, s in zip(line, sig)
    ]
    return {"line": line, "signal": sig, "hist": hist}


def last_defined(series: list[float | None], n: int) -> list[float] | None:
    """Last n non-None values of a series, or None if fewer exist."""
    defined = [v for v in series if v is not None]
    if len(defined) < n:
        return None
    return defined[-n:]
