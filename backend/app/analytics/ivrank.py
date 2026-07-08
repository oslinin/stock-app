"""IV rank / IV percentile over an ATM-IV history, plus ATM-IV extraction
from a chain snapshot (used by the nightly iv_snapshot job)."""

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


def atm_iv_from_chain(rows: list[dict], spot: float) -> float | None:
    """Average call/put IV at the strike nearest spot. Rows: {strike,
    right, iv}; rows without IV are ignored."""
    usable = [r for r in rows if r.get("iv") is not None and r.get("strike") is not None]
    if not usable:
        return None
    atm_strike = min((r["strike"] for r in usable), key=lambda k: abs(k - spot))
    ivs = [r["iv"] for r in usable if r["strike"] == atm_strike]
    return sum(ivs) / len(ivs) if ivs else None
