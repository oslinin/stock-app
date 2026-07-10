from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Bot(SQLModel, table=True):
    """Current state lives on the row (position_state, pending_order_id)
    so the next tick reads it directly; bot_run is the immutable audit
    trail of how it got there."""

    __tablename__ = "bot"

    id: int | None = Field(default=None, primary_key=True)
    spec_id: int = Field(foreign_key="strategy_spec.id")
    broker: str = "ibkr"
    mode: str = "paper"  # paper | live
    status: str = "draft"  # draft | running | paused | killed
    bp_pct: float = 0.05  # fraction of NetLiq per position
    max_concurrent: int = 1
    fixed_contracts: int | None = None
    position_state: str = "FLAT"  # FLAT | ENTRY_SIGNALED | ORDER_PENDING | IN_POSITION
    pending_order_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class BotRun(SQLModel, table=True):
    """One row per tick (plan: bot_run: tick_at, position_state, action,
    detail) — the audit trail the state machine leaves behind."""

    __tablename__ = "bot_run"

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="bot.id", index=True)
    tick_at: datetime = Field(default_factory=utcnow, index=True)
    position_state: str
    action: str = ""
    detail: str = ""


class BotEvent(SQLModel, table=True):
    __tablename__ = "bot_event"

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="bot.id", index=True)
    type: str  # order_placed | filled | kill | risk_blocked
    payload: str = ""  # JSON
    created_at: datetime = Field(default_factory=utcnow)


class OrderRecord(SQLModel, table=True):
    __tablename__ = "order_record"

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int | None = Field(default=None, foreign_key="bot.id")
    broker: str
    broker_order_id: str = ""
    draft_json: str = ""
    whatif_json: str = ""
    status: str = "draft"  # draft | staged | transmitted | filled | cancelled | rejected
    created_at: datetime = Field(default_factory=utcnow)
