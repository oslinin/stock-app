from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AlertRule(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    strategy_id: str = Field(index=True)
    channels: str = "email"  # comma-separated: email,push
    on_verdicts: str = "ARMED,ENTER"
    email: str = ""
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class AlertEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    rule_id: int = Field(index=True)
    strategy_id: str
    verdict: str
    trading_date: str = Field(index=True)  # YYYY-MM-DD ET; dedupe key component
    expiry: str = ""
    summary: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ArmedState(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    strategy_id: str = Field(index=True)
    armed_date: str  # YYYY-MM-DD ET of the confirming close
    confirming_close: float
    signal_detail: str = ""
    created_at: datetime = Field(default_factory=utcnow)
