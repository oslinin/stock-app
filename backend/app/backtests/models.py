"""backtest_run doubles as the worker job queue (status
queued|running|done|failed); backtest_result stores metrics + the raw
trade list/equity curve as JSON (volatile per-engine shape — plan's own
SQLite architecture note: "schema churn lands in Pydantic, not DDL");
robustness_result stores one MCPT/bootstrap/walk-forward run each."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BacktestRun(SQLModel, table=True):
    __tablename__ = "backtest_run"

    id: int | None = Field(default=None, primary_key=True)
    spec_id: int = Field(foreign_key="strategy_spec.id")
    engine: str  # optopsy | oo_manual
    params_json: str = "{}"
    status: str = "queued"  # queued | running | done | failed
    error: str = ""
    claimed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class BacktestResult(SQLModel, table=True):
    __tablename__ = "backtest_result"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="backtest_run.id", index=True)
    metrics_json: str = "{}"
    trades_json: str = "[]"
    equity_curve_json: str = "[]"
    engine_raw_json: str = "{}"
    created_at: datetime = Field(default_factory=utcnow)


class RobustnessResult(SQLModel, table=True):
    __tablename__ = "robustness_result"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="backtest_run.id", index=True)
    kind: str  # permutation | bootstrap | walk_forward
    params_json: str = "{}"
    results_json: str = "{}"
    computed_at: datetime = Field(default_factory=utcnow)
