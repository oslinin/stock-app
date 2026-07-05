"""Opening-range computation, normalized to US/Eastern.

Timezone handling matters: IB historical bars arrive tz-aware, but an
off-by-one-hour bug here would silently corrupt the opening-range-breakout
check, so everything is converted to America/New_York explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)


def to_et(dt: datetime | date) -> datetime:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=ET)
        return dt.astimezone(ET)
    return datetime.combine(dt, time(0, 0), ET)


@dataclass
class OpeningRange:
    high: float | None
    low: float | None
    complete: bool
    window_min: int


def opening_range(bars, window_min: int, now: datetime | None = None) -> OpeningRange:
    """bars: iterable with .date (datetime), .high, .low — e.g. IB intraday bars."""
    bars = list(bars)
    if not bars:
        return OpeningRange(None, None, False, window_min)
    session_day = to_et(bars[-1].date).date()
    start = datetime.combine(session_day, SESSION_OPEN, ET)
    end = start + timedelta(minutes=window_min)
    in_window = [b for b in bars if start <= to_et(b.date) < end]
    now_et = to_et(now) if now is not None else datetime.now(ET)
    complete = bool(in_window) and now_et >= end
    if not in_window:
        return OpeningRange(None, None, False, window_min)
    return OpeningRange(
        max(b.high for b in in_window),
        min(b.low for b in in_window),
        complete,
        window_min,
    )
