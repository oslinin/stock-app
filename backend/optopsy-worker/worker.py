"""AGPL boundary: this process is the ONLY place `optopsy` is imported
in this repo (backend/README.md documents a CI grep forbidding
`import optopsy` outside this directory). It polls the main backend's
job queue over HTTP with its own WORKER_TOKEN — no shared imports, no
shared DB file, per the plan's AGPL-hygiene requirement.

ponytail: verified against a real (if empty-result) local optopsy run —
`op.short_puts(data, raw=True)` really does return the column names
_summarize() below expects (matches optopsy's own
single_strike_internal_cols / double_strike_internal_cols). Getting a
*non-empty* result needs synthetic data that lands inside optopsy's own
dte/otm bucketing, which needs real historical chain data to validate
properly — this sandbox has no such dataset. Verify against a real
DoltHub-backed run before trusting results in production.
"""

from __future__ import annotations

import os
import time
import traceback
from pathlib import Path

import httpx
import optopsy as op
import pandas as pd

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000/api/v1")
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")
POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "30"))
DATA_DIR = Path(os.environ.get("BACKTEST_CACHE_DIR", "./data/backtest_cache"))
STARTING_EQUITY = float(os.environ.get("STARTING_EQUITY", "10000"))

STRATEGY_FNS = {
    "short_puts": op.short_puts,
    "long_puts": op.long_puts,
    "short_calls": op.short_calls,
    "long_calls": op.long_calls,
    "short_put_spread": op.short_put_spread,
    "long_put_spread": op.long_put_spread,
    "short_call_spread": op.short_call_spread,
    "long_call_spread": op.long_call_spread,
}


def _headers() -> dict:
    return {"Authorization": f"Bearer {WORKER_TOKEN}"} if WORKER_TOKEN else {}


def claim() -> dict | None:
    r = httpx.post(
        f"{BACKEND_URL}/backtests/jobs/claim", params={"engine": "optopsy"}, headers=_headers(), timeout=30
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def post_result(run_id: int, metrics: dict, trades: list[dict], equity_curve: list[float], engine_raw: dict) -> None:
    httpx.post(
        f"{BACKEND_URL}/backtests/jobs/{run_id}/result",
        json={"metrics": metrics, "trades": trades, "equityCurve": equity_curve, "engineRaw": engine_raw},
        headers=_headers(),
        timeout=30,
    ).raise_for_status()


def post_failure(run_id: int, error: str) -> None:
    httpx.post(
        f"{BACKEND_URL}/backtests/jobs/{run_id}/fail",
        json={"error": error},
        headers=_headers(),
        timeout=30,
    ).raise_for_status()


def load_chain(symbol: str) -> pd.DataFrame:
    """Reads the parquet cache the main backend's backtests/data.py
    populates (a shared volume, not a shared DB — see
    deploy/docker-compose.yml)."""
    matches = sorted(DATA_DIR.glob(f"{symbol.upper()}_*.parquet"))
    if not matches:
        raise FileNotFoundError(f"no cached chain parquet for {symbol} in {DATA_DIR}")
    return pd.read_parquet(matches[-1])


def _row_pnl(row) -> float:
    """A single contract's/spread's $ P&L for one trade. Single-leg
    rows carry pct_change against `entry` (a $ premium); spreads carry
    total_entry_cost/total_exit_proceeds directly."""
    if "total_entry_cost" in row and pd.notna(row.get("total_entry_cost")):
        return float(row["total_exit_proceeds"] - row["total_entry_cost"]) * 100
    return float(row.get("pct_change", 0.0)) * float(row.get("entry", 0.0)) * 100


def _row_dates(row) -> tuple[str, str]:
    """optopsy reports dte_entry (days-to-expiration at entry) and
    expiration, not a literal entry date — back it out."""
    expiration = pd.Timestamp(row["expiration"])
    dte_entry = int(row.get("dte_entry", 0))
    entry_date = expiration - pd.Timedelta(days=dte_entry)
    return entry_date.date().isoformat(), expiration.date().isoformat()


def summarize(result_df: pd.DataFrame) -> tuple[list[dict], list[float]]:
    trades = []
    equity = [STARTING_EQUITY]
    for _, row in result_df.iterrows():
        entry_date, exit_date = _row_dates(row)
        pnl = _row_pnl(row)
        trades.append({"entryDate": entry_date, "exitDate": exit_date, "pnl": pnl})
        equity.append(equity[-1] + pnl)
    return trades, equity


def run_job(job: dict) -> None:
    params = job["params"]
    strategy_name = params.get("optopsyStrategy")
    fn = STRATEGY_FNS.get(strategy_name)
    if fn is None:
        post_failure(job["id"], f"unknown or unsupported optopsy strategy {strategy_name!r}")
        return

    try:
        chain = load_chain(params["underlyingSymbol"])
    except FileNotFoundError as exc:
        post_failure(job["id"], str(exc))
        return

    try:
        result_df = fn(chain, raw=True, **params.get("optopsyKwargs", {}))
        trades, equity_curve = summarize(result_df)
        wins = [t for t in trades if t["pnl"] > 0]
        metrics = {
            "tradeCount": len(trades),
            "winRate": (len(wins) / len(trades)) if trades else None,
            "expectancy": (sum(t["pnl"] for t in trades) / len(trades)) if trades else None,
        }
        post_result(job["id"], metrics, trades, equity_curve, engine_raw={"rowCount": len(result_df)})
    except Exception:  # noqa: BLE001 - a bad job must not kill the poll loop
        post_failure(job["id"], traceback.format_exc())


def main() -> None:
    print(f"optopsy-worker polling {BACKEND_URL} every {POLL_SECONDS}s")
    while True:
        job = claim()
        if job is None:
            time.sleep(POLL_SECONDS)
            continue
        print(f"claimed backtest job {job['id']}")
        run_job(job)


if __name__ == "__main__":
    main()
