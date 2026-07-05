"""Bottom-signal detection and verdict derivation for the VIX hedge entry.

Entry logic (AJ Brown):
- ARMING (end of day): a MACD "bottom signal" on the daily VIX — the MACD line
  crossing above its signal line and/or the histogram turning up from a trough,
  while VIX is relatively low (cheap volatility).
- CONFIRMATION (next session, intraday) — all must hold to fire ENTER:
    1. VIX above the previous day's close
    2. VIX above the confirming-day close (stored when the signal armed)
    3. VIX above the opening-range high (first N minutes of the session)
"""

from __future__ import annotations

from dataclasses import dataclass

from .macd import last_defined


@dataclass
class BottomSignal:
    fired: bool
    cross_up: bool
    trough_turn: bool
    low_vix: bool
    detail: str


@dataclass
class Check:
    key: str
    label: str
    passed: bool
    detail: str = ""


def quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("empty series")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def bottom_signal(
    macd_out: dict[str, list[float | None]],
    closes: list[float],
    low_quantile: float = 0.4,
    lookback: int = 120,
    abs_low: float = 20.0,
) -> BottomSignal:
    line2 = last_defined(macd_out["line"], 2)
    sig2 = last_defined(macd_out["signal"], 2)
    hist3 = last_defined(macd_out["hist"], 3)
    if line2 is None or sig2 is None or hist3 is None or not closes:
        return BottomSignal(False, False, False, False, "insufficient history for MACD")

    cross_up = line2[0] <= sig2[0] and line2[1] > sig2[1]
    trough_turn = hist3[1] < hist3[0] and hist3[2] > hist3[1] and hist3[1] < 0

    window = closes[-lookback:]
    q = quantile(sorted(window), low_quantile)
    low_vix = closes[-1] <= q or closes[-1] <= abs_low

    fired = (cross_up or trough_turn) and low_vix
    parts = []
    if cross_up:
        parts.append("MACD crossed above signal")
    if trough_turn:
        parts.append("histogram turned up from a trough")
    if not parts:
        parts.append("no MACD bottom pattern")
    parts.append(
        f"VIX {closes[-1]:.2f} vs {low_quantile:.0%} quantile {q:.2f} (abs floor {abs_low:.1f})"
        + (" -> low" if low_vix else " -> not low")
    )
    return BottomSignal(fired, cross_up, trough_turn, low_vix, "; ".join(parts))


def confirmation_checks(
    spot: float | None,
    prior_close: float | None,
    confirming_close: float | None,
    or_high: float | None,
    or_complete: bool,
    armed: bool,
    or_minutes: int,
) -> list[Check]:
    checks = [
        Check(
            "macd_bottom",
            "MACD bottom signal (armed)",
            armed,
            "armed" if armed else "no bottom signal detected",
        )
    ]

    def cmp_check(key: str, label: str, ref: float | None, ref_name: str) -> Check:
        if spot is None or ref is None:
            return Check(key, label, False, "no data")
        return Check(
            key,
            label,
            spot > ref,
            f"VIX {spot:.2f} vs {ref_name} {ref:.2f}",
        )

    checks.append(cmp_check("above_prior_close", "VIX > prior close", prior_close, "prior close"))
    checks.append(
        cmp_check(
            "above_confirming_close",
            "VIX > confirming-day close",
            confirming_close,
            "confirming close",
        )
    )
    if spot is None or or_high is None or not or_complete:
        checks.append(
            Check(
                "or_breakout",
                f"VIX > {or_minutes}m opening-range high",
                False,
                "opening range incomplete" if not or_complete else "no data",
            )
        )
    else:
        checks.append(
            Check(
                "or_breakout",
                f"VIX > {or_minutes}m opening-range high",
                spot > or_high,
                f"VIX {spot:.2f} vs OR high {or_high:.2f}",
            )
        )
    return checks


def derive_verdict(has_data: bool, session_open: bool, armed: bool, checks: list[Check]) -> str:
    if not has_data:
        return "NO_DATA"
    if not armed:
        return "WAIT"
    if session_open and all(c.passed for c in checks):
        return "ENTER"
    return "ARMED"
