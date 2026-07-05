from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.indicators.opening_range import opening_range
from app.indicators.signals import (
    bottom_signal,
    confirmation_checks,
    derive_verdict,
)

UTC = timezone.utc


def macd_out(line2, sig2, hist3):
    return {
        "line": [None] + line2,
        "signal": [None] + sig2,
        "hist": [None] + hist3,
    }


def test_bottom_signal_cross_up_low_vix():
    out = macd_out([-0.20, -0.10], [-0.15, -0.15], [0.0, -0.05, -0.02])
    closes = [20.0] * 100 + [15.0]
    sig = bottom_signal(out, closes)
    assert sig.cross_up and sig.low_vix and sig.fired


def test_bottom_signal_trough_turn():
    out = macd_out([-0.20, -0.22], [-0.15, -0.15], [-0.05, -0.08, -0.03])
    closes = [22.0] * 100 + [19.0]  # not in low quantile, but under abs floor 20
    sig = bottom_signal(out, closes)
    assert sig.trough_turn and not sig.cross_up and sig.low_vix and sig.fired


def test_bottom_signal_not_low_vix():
    out = macd_out([-0.20, -0.10], [-0.15, -0.15], [0.0, -0.05, -0.02])
    closes = [20.0] * 100 + [30.0]
    sig = bottom_signal(out, closes)
    assert sig.cross_up and not sig.low_vix and not sig.fired


def test_bottom_signal_insufficient_history():
    out = {"line": [None, -0.1], "signal": [None, None], "hist": [None, None]}
    assert not bottom_signal(out, [15.0]).fired


@dataclass
class Bar:
    date: datetime
    high: float
    low: float


def _bars_summer_morning():
    # 13:30 UTC == 09:30 ET during daylight saving time
    start = datetime(2026, 6, 18, 13, 30, tzinfo=UTC)
    highs = [14.40, 14.35, 14.20, 14.10, 14.05, 14.15, 14.50, 14.60]
    lows = [14.05, 14.10, 14.00, 13.95, 13.90, 14.00, 14.30, 14.40]
    return [
        Bar(start + timedelta(minutes=5 * i), h, l)
        for i, (h, l) in enumerate(zip(highs, lows))
    ]


def test_opening_range_uses_first_window_only():
    bars = _bars_summer_morning()
    now = datetime(2026, 6, 18, 15, 0, tzinfo=UTC)
    orr = opening_range(bars, 30, now=now)
    # window covers the first six 5-minute bars (09:30-09:59), not the 14.60 bar at 10:05
    assert orr.high == 14.40
    assert orr.low == 13.90
    assert orr.complete


def test_opening_range_incomplete_before_window_end():
    bars = _bars_summer_morning()[:3]
    now = datetime(2026, 6, 18, 13, 46, tzinfo=UTC)  # 09:46 ET
    orr = opening_range(bars, 30, now=now)
    assert not orr.complete
    assert orr.high == 14.40


def test_opening_range_no_bars():
    orr = opening_range([], 30)
    assert orr.high is None and not orr.complete


def test_confirmation_and_verdict_enter():
    checks = confirmation_checks(
        spot=14.55,
        prior_close=14.10,
        confirming_close=13.95,
        or_high=14.40,
        or_complete=True,
        armed=True,
        or_minutes=30,
    )
    assert all(c.passed for c in checks)
    assert derive_verdict(True, True, True, checks) == "ENTER"


def test_verdict_states():
    failing = confirmation_checks(14.0, 14.10, 13.95, 14.40, True, True, 30)
    assert derive_verdict(False, True, True, failing) == "NO_DATA"
    assert derive_verdict(True, True, False, failing) == "WAIT"
    assert derive_verdict(True, True, True, failing) == "ARMED"
    passing = confirmation_checks(14.55, 14.10, 13.95, 14.40, True, True, 30)
    assert derive_verdict(True, False, True, passing) == "ARMED"  # session closed
