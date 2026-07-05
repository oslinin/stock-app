from __future__ import annotations

from datetime import date, datetime, time

from ..indicators.opening_range import ET


def now_et() -> datetime:
    return datetime.now(ET)


def et_today() -> date:
    return now_et().date()


def session_open(now: datetime | None = None) -> bool:
    """Rough RTH gate for the VIX cash session (09:30-16:15 ET, weekdays)."""
    now = now or now_et()
    if now.weekday() >= 5:
        return False
    return time(9, 30) <= now.time() <= time(16, 15)
