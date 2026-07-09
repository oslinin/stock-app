from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BrokerAccount(SQLModel, table=True):
    __tablename__ = "broker_account"

    id: int | None = Field(default=None, primary_key=True)
    broker: str  # "ibkr" | "fidelity"
    label: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class PositionSnapshot(SQLModel, table=True):
    """One row per broker sync/upload: the full positions list as JSON —
    volatile per-broker shape, so it's a JSON blob (plan: "schema churn
    lands in Pydantic, not DDL"), not one row per position."""

    __tablename__ = "position_snapshot"

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="broker_account.id", index=True)
    asof: datetime = Field(default_factory=utcnow, index=True)
    source: str  # "ibkr_live" | "fidelity_csv"
    positions_json: str
    created_at: datetime = Field(default_factory=utcnow)


class FidelityImport(SQLModel, table=True):
    __tablename__ = "fidelity_import"

    id: int | None = Field(default=None, primary_key=True)
    filename: str = ""
    parsed_count: int = 0
    asof: datetime = Field(default_factory=utcnow)
    snapshot_id: int | None = Field(default=None, foreign_key="position_snapshot.id")


class BetaCache(SQLModel, table=True):
    __tablename__ = "beta_cache"

    id: int | None = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, unique=True)
    beta: float
    r2: float
    window_days: int
    computed_at: datetime = Field(default_factory=utcnow)
