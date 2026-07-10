"""/backtests — job queue for the optopsy worker (AGPL-isolated, polls
over HTTP with its own WORKER_TOKEN), the Option Omega manual-bridge
CSV import, and the robustness suite over a completed run's trades."""

from __future__ import annotations

import csv
import io
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlmodel import select

from ..backtests import service
from ..backtests.compile_backtest import compile_backtest
from ..backtests.metrics import compute_metrics
from ..backtests.models import BacktestResult, BacktestRun, RobustnessResult
from ..backtests.oo_import import parse_oo_trade_log
from ..backtests.robustness import bootstrap, permutation_test
from ..backtests.service import JobQueueError
from ..db.session import session_scope
from ..security import require_token, require_worker_token
from ..specs import service as spec_service

router = APIRouter(prefix="/backtests", dependencies=[Depends(require_token)])
worker_router = APIRouter(prefix="/backtests/jobs", dependencies=[Depends(require_worker_token)])


def _spec(spec_id: int):
    found = spec_service.get_spec(spec_id)
    if found is None:
        raise HTTPException(404, f"spec {spec_id} not found")
    _, version = found
    return version.spec()


def _run_out(run: BacktestRun, result: BacktestResult | None) -> dict:
    out = {
        "id": run.id,
        "specId": run.spec_id,
        "engine": run.engine,
        "status": run.status,
        "error": run.error,
        "createdAt": run.created_at.isoformat(),
    }
    if result is not None:
        out["metrics"] = json.loads(result.metrics_json)
    return out


@router.get("/compile-preview")
def compile_preview(spec_id: int) -> dict:
    """compile_backtest's output without creating a run — lets the UI
    show "supported: false, here's why" before the user queues a job."""
    return compile_backtest(_spec(spec_id))


@router.post("", status_code=201)
def create_run(body: dict, request: Request) -> dict:
    """The job's params carry compile_backtest's output (strategy name +
    optopsy kwargs), not just the caller's raw params — the worker has
    no shared imports with the backend (AGPL isolation), so everything
    it needs to run the backtest has to travel through the job payload."""
    spec_id = body["specId"]
    engine = body.get("engine", "optopsy")
    spec = _spec(spec_id)
    compiled = compile_backtest(spec)
    if engine == "optopsy" and not compiled["supported"]:
        raise HTTPException(422, {"unsupported": compiled["unsupported"]})
    params = {
        "underlyingSymbol": spec.universe.underlyings[0] if spec.universe.underlyings else "",
        "optopsyStrategy": compiled["optopsyStrategy"],
        "optopsyKwargs": compiled["optopsyKwargs"],
        **body.get("params", {}),
    }
    run_id = service.enqueue(spec_id, engine, params)
    with session_scope() as session:
        run = session.get(BacktestRun, run_id)
        return _run_out(run, None)


@router.get("/{run_id}")
def get_run(run_id: int) -> dict:
    with session_scope() as session:
        run = session.get(BacktestRun, run_id)
        if run is None:
            raise HTTPException(404, "backtest run not found")
        result = session.exec(select(BacktestResult).where(BacktestResult.run_id == run_id)).first()
        return _run_out(run, result)


@router.get("/{run_id}/equity")
def get_equity(run_id: int) -> dict:
    with session_scope() as session:
        result = session.exec(select(BacktestResult).where(BacktestResult.run_id == run_id)).first()
        if result is None:
            raise HTTPException(404, "no result yet for this run")
        return {"equityCurve": json.loads(result.equity_curve_json)}


@router.get("/{run_id}/trades.csv")
def get_trades_csv(run_id: int) -> str:
    with session_scope() as session:
        result = session.exec(select(BacktestResult).where(BacktestResult.run_id == run_id)).first()
        if result is None:
            raise HTTPException(404, "no result yet for this run")
        trades = json.loads(result.trades_json)
    buf = io.StringIO()
    fieldnames = list(trades[0].keys()) if trades else ["entryDate", "exitDate", "pnl"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(trades)
    return buf.getvalue()


@router.get("/{run_id}/setup-sheet")
def get_setup_sheet(run_id: int) -> dict:
    with session_scope() as session:
        run = session.get(BacktestRun, run_id)
        if run is None:
            raise HTTPException(404, "backtest run not found")
        spec_id = run.spec_id
    spec = _spec(spec_id)
    compiled = compile_backtest(spec)
    return {
        "setupSheet": compiled["ooSetupSheet"],
        "signalsCsv": compiled["ooSignalsCsv"],
        "unsupported": compiled["unsupported"],
    }


@router.post("/import/oo", status_code=201)
async def import_oo(spec_id: int, file: UploadFile) -> dict:
    _spec(spec_id)  # 404s if the spec doesn't exist
    text = (await file.read()).decode("utf-8", errors="replace")
    try:
        trades = parse_oo_trade_log(text)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    starting_equity = 10_000.0
    equity_curve = [starting_equity]
    for t in trades:
        equity_curve.append(equity_curve[-1] + t["pnl"])
    metrics = compute_metrics(trades, equity_curve)

    run_id = service.enqueue(spec_id, "oo_manual", {})
    service.claim("oo_manual")
    service.record_result(run_id, metrics=metrics, trades=trades, equity_curve=equity_curve, engine_raw={})
    with session_scope() as session:
        run = session.get(BacktestRun, run_id)
        result = session.exec(select(BacktestResult).where(BacktestResult.run_id == run_id)).first()
        return _run_out(run, result)


@router.post("/{run_id}/robustness")
def run_robustness(run_id: int, body: dict) -> dict:
    kind = body["kind"]
    params = body.get("params", {})
    with session_scope() as session:
        result = session.exec(select(BacktestResult).where(BacktestResult.run_id == run_id)).first()
        if result is None:
            raise HTTPException(404, "no result yet for this run")
        trades = json.loads(result.trades_json)
        equity_curve = json.loads(result.equity_curve_json)

    if not trades:
        raise HTTPException(422, "no trades to run robustness against")

    if kind == "bootstrap":
        results = bootstrap(
            [t["pnl"] for t in trades], starting_equity=equity_curve[0], n=params.get("n", 10_000)
        )
    elif kind == "permutation":
        underlying_returns = params.get("underlyingDailyReturns")
        if not underlying_returns:
            raise HTTPException(422, "permutation test needs params.underlyingDailyReturns")
        trade_returns = [t["pnl"] / equity_curve[0] for t in trades]
        holding_days = [
            (date.fromisoformat(t["exitDate"]) - date.fromisoformat(t["entryDate"])).days for t in trades
        ]
        results = permutation_test(trade_returns, holding_days, underlying_returns, n=params.get("n", 1000))
    else:
        raise HTTPException(422, f"unknown robustness kind {kind!r} (walk_forward runs in the optopsy worker)")

    robustness_id = service.record_robustness(run_id, kind, params, results)
    return {"id": robustness_id, "kind": kind, "results": results}


@router.get("/{run_id}/robustness")
def list_robustness(run_id: int) -> list[dict]:
    with session_scope() as session:
        rows = session.exec(select(RobustnessResult).where(RobustnessResult.run_id == run_id)).all()
        return [
            {"id": r.id, "kind": r.kind, "results": json.loads(r.results_json), "computedAt": r.computed_at.isoformat()}
            for r in rows
        ]


# ------------------------------------------------------- worker endpoints


@worker_router.post("/claim")
def claim_job(engine: str) -> dict:
    job = service.claim(engine)
    if job is None:
        raise HTTPException(404, "no queued jobs")
    return job


@worker_router.post("/{run_id}/result")
def post_result(run_id: int, body: dict) -> dict:
    try:
        service.record_result(
            run_id,
            metrics=body["metrics"],
            trades=body["trades"],
            equity_curve=body["equityCurve"],
            engine_raw=body.get("engineRaw", {}),
        )
    except JobQueueError as exc:
        raise HTTPException(409, str(exc))
    return {"status": "recorded"}


@worker_router.post("/{run_id}/fail")
def post_failure(run_id: int, body: dict) -> dict:
    try:
        service.record_failure(run_id, body.get("error", ""))
    except JobQueueError as exc:
        raise HTTPException(409, str(exc))
    return {"status": "recorded"}
