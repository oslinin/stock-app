"""IV rank / IV percentile over an ATM-IV history (the iv_history table,
synced nightly from IBKR's IV index)."""

from __future__ import annotations


def iv_rank(history: list[float], current: float) -> float | None:
    """(current - min) / (max - min) * 100 over the lookback window.
    None when the window is empty or flat (rank undefined)."""
    if not history:
        return None
    lo, hi = min(history), max(history)
    if hi <= lo:
        return None
    return max(0.0, min(100.0, (current - lo) / (hi - lo) * 100.0))


def iv_percentile(history: list[float], current: float) -> float | None:
    """Share of observations strictly below the current IV, in percent."""
    if not history:
        return None
    below = sum(1 for v in history if v < current)
    return below / len(history) * 100.0
