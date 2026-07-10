"""Trade-list -> summary metrics (cagr/win_rate/expectancy/max_dd/
sharpe/trade_count). Engine-agnostic — optopsy, OO-imported, and manual
trade lists all normalize to the same shape before reaching this."""

from __future__ import annotations

import math
from datetime import date


def _years_between(start: date, end: date) -> float:
    return max((end - start).days / 365.25, 1 / 365.25)


def compute_metrics(trades: list[dict], equity_curve: list[float]) -> dict:
    """trades: [{"entryDate", "exitDate" (ISO), "pnl"}, ...].
    equity_curve: starting capital followed by cumulative equity after
    each trade closes (len == len(trades) + 1)."""
    trade_count = len(trades)
    if trade_count == 0 or len(equity_curve) < 2:
        return {
            "cagr": None,
            "winRate": None,
            "expectancy": None,
            "maxDd": None,
            "sharpe": None,
            "tradeCount": trade_count,
        }

    wins = [t for t in trades if t["pnl"] > 0]
    win_rate = len(wins) / trade_count
    expectancy = sum(t["pnl"] for t in trades) / trade_count

    start_equity, end_equity = equity_curve[0], equity_curve[-1]
    dates = sorted(date.fromisoformat(t["exitDate"]) for t in trades)
    entry_dates = sorted(date.fromisoformat(t["entryDate"]) for t in trades)
    years = _years_between(entry_dates[0], dates[-1])
    cagr = (end_equity / start_equity) ** (1 / years) - 1 if start_equity > 0 and years > 0 else None

    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak)

    period_returns = [
        (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
        for i in range(1, len(equity_curve))
        if equity_curve[i - 1]
    ]
    sharpe = None
    if len(period_returns) >= 2:
        mean = sum(period_returns) / len(period_returns)
        variance = sum((r - mean) ** 2 for r in period_returns) / (len(period_returns) - 1)
        stdev = math.sqrt(variance)
        if stdev > 0:
            sharpe = (mean / stdev) * math.sqrt(len(period_returns))

    return {
        "cagr": cagr,
        "winRate": win_rate,
        "expectancy": expectancy,
        "maxDd": max_dd,
        "sharpe": sharpe,
        "tradeCount": trade_count,
    }
