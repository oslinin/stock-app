"""Job queue mechanics over backtest_run — enqueue/claim/result/fail.
Pure DB-state-machine logic, separated from the route layer so it's
directly testable without a running worker."""

from __future__ import annotations

import json

from sqlmodel import select

from ..db.session import session_scope
from .models import BacktestResult, BacktestRun, RobustnessResult, utcnow


class JobQueueError(Exception):
    pass


def enqueue(spec_id: int, engine: str, params: dict) -> int:
    with session_scope() as session:
        run = BacktestRun(spec_id=spec_id, engine=engine, params_json=json.dumps(params))
        session.add(run)
        session.flush()
        return run.id


def claim(engine: str) -> dict | None:
    """The oldest queued job for `engine`, marked running. None when
    there's nothing to claim. Calling claim() again for the same job
    (nothing left queued, or it's already running) returns None —
    a job is claimed at most once."""
    with session_scope() as session:
        run = session.exec(
            select(BacktestRun)
            .where(BacktestRun.engine == engine, BacktestRun.status == "queued")
            .order_by(BacktestRun.created_at)
        ).first()
        if run is None:
            return None
        run.status = "running"
        run.claimed_at = utcnow()
        session.add(run)
        session.flush()
        return {"id": run.id, "specId": run.spec_id, "params": json.loads(run.params_json)}


def record_result(
    run_id: int, metrics: dict, trades: list[dict], equity_curve: list[float], engine_raw: dict
) -> None:
    """Raises if the run isn't currently `running` — a worker retry that
    already succeeded (or a run that was never claimed) must not
    silently overwrite or duplicate a result."""
    with session_scope() as session:
        run = session.get(BacktestRun, run_id)
        if run is None:
            raise JobQueueError(f"backtest run {run_id} not found")
        if run.status != "running":
            raise JobQueueError(f"backtest run {run_id} is {run.status!r}, not running — can't record a result")
        run.status = "done"
        session.add(run)
        session.add(
            BacktestResult(
                run_id=run_id,
                metrics_json=json.dumps(metrics),
                trades_json=json.dumps(trades),
                equity_curve_json=json.dumps(equity_curve),
                engine_raw_json=json.dumps(engine_raw),
            )
        )


def record_failure(run_id: int, error: str) -> None:
    """A completed run can't be failed after the fact; failing an
    already-failed run is idempotent (just updates the error text)."""
    with session_scope() as session:
        run = session.get(BacktestRun, run_id)
        if run is None:
            raise JobQueueError(f"backtest run {run_id} not found")
        if run.status == "done":
            raise JobQueueError(f"backtest run {run_id} already completed — can't fail it now")
        run.status = "failed"
        run.error = error
        session.add(run)


def record_robustness(run_id: int, kind: str, params: dict, results: dict) -> int:
    with session_scope() as session:
        row = RobustnessResult(
            run_id=run_id, kind=kind, params_json=json.dumps(params), results_json=json.dumps(results)
        )
        session.add(row)
        session.flush()
        return row.id
