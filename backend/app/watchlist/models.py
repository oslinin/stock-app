from __future__ import annotations

import datetime as dt
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WatchlistItem(SQLModel, table=True):
    __tablename__ = "watchlist_item"

    id: int | None = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, unique=True)
    tags: str = ""  # comma-separated, matches AlertRule.channels convention
    created_at: datetime = Field(default_factory=utcnow)


class SymbolMetrics(SQLModel, table=True):
    """One row per symbol per day, written by the nightly watchlist_scan
    job. Screeners (app/watchlist/screeners.py) are pure queries over
    this table — never a live chain fetch at request time."""

    __tablename__ = "symbol_metrics"

    id: int | None = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    date: dt.date = Field(index=True)
    underlying_px: float
    atm_iv: float | None = None
    iv_rank: float | None = None
    iv_percentile: float | None = None
    expected_move: float | None = None  # underlying_px * atm_iv * sqrt(dte/365)
    # ATM straddle premium as a fraction of notional per day held — a
    # simple, labeled proxy for "credit/BP/day", not a real margin calc
    premium_yield: float | None = None
    open_interest: float | None = None  # at the strike sampled for delta/DTE
    spread_pct: float | None = None  # (ask-bid)/mid at that same strike
    sampled_delta: float | None = None
    sampled_dte: int | None = None
    source: str = ""
    created_at: datetime = Field(default_factory=utcnow)
