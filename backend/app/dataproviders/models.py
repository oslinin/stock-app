from __future__ import annotations

import datetime as dt
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IVHistory(SQLModel, table=True):
    """One ATM-IV observation per symbol per day, written by the nightly
    iv_snapshot job. IV rank/percentile are computed over this table."""

    __tablename__ = "iv_history"

    id: int | None = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    date: dt.date = Field(index=True)
    atm_iv: float
    underlying_px: float | None = None
    source: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ProviderCallLog(SQLModel, table=True):
    """One row per metered upstream call (Alpha Vantage budget guard)."""

    __tablename__ = "provider_call_log"

    id: int | None = Field(default=None, primary_key=True)
    provider: str = Field(index=True)
    day: dt.date = Field(index=True)
    endpoint: str = ""
    symbol: str = ""
    called_at: datetime = Field(default_factory=utcnow)
