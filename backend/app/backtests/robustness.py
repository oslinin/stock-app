"""Backtest robustness: engine-agnostic pure numpy over a trade list /
bar series — works on optopsy, OO-imported, or manual results alike.

- permutation_test: "is this edge distinguishable from luck?" The plan's
  cheaper MCPT variant — for each realized trade, draw a random entry
  point (and equal holding length) from the SAME underlying daily-return
  series and compound a synthetic return; sum across trades per
  permutation gives one null-distribution total. p_value = P(null total
  >= actual total). Full bar-shuffle-and-rerun-the-engine MCPT is the
  fuller (and pricier) version the plan also names; this is its
  documented cheaper substitute.
- bootstrap: "how bad could the same edge feel?" resample realized trade
  P&L with replacement -> distribution of equity curves.
- walk_forward_windows / walk_forward_efficiency: the rolling
  anchored-window structure ("does it survive out-of-sample?"); the
  actual per-window re-optimization runs in the optopsy worker (it owns
  the data) — these are the pure window-math + OOS/IS ratio helpers.
"""

from __future__ import annotations

from datetime import date

import numpy as np


def permutation_test(
    trade_returns: list[float],
    holding_days: list[int],
    underlying_daily_returns: list[float],
    n: int = 1000,
    seed: int | None = None,
) -> dict:
    if len(trade_returns) != len(holding_days):
        raise ValueError("trade_returns and holding_days must be the same length")
    rng = np.random.default_rng(seed)
    returns = np.asarray(underlying_daily_returns, dtype=float)
    n_days = len(returns)
    actual_total = float(sum(trade_returns))

    null_totals = np.empty(n)
    for i in range(n):
        total = 0.0
        for h in holding_days:
            if h <= 0 or h > n_days:
                continue
            start = rng.integers(0, n_days - h + 1)
            window = returns[start : start + h]
            total += float(np.prod(1 + window) - 1)
        null_totals[i] = total

    p_value = float(np.mean(null_totals >= actual_total))
    return {"pValue": p_value, "actualTotal": actual_total, "permutations": n}


def bootstrap(trade_pnls: list[float], starting_equity: float, n: int = 10_000, seed: int | None = None) -> dict:
    rng = np.random.default_rng(seed)
    pnls = np.asarray(trade_pnls, dtype=float)
    n_trades = len(pnls)
    if n_trades == 0:
        return {
            "terminalEquityPercentiles": {},
            "maxDrawdownPercentiles": {},
            "riskOfRuin": None,
            "longestLosingStreakPercentiles": {},
            "paths": n,
        }

    resampled = rng.choice(pnls, size=(n, n_trades), replace=True)
    equity_paths = starting_equity + np.cumsum(resampled, axis=1)
    terminal = equity_paths[:, -1]
    terminal_pct = {p: float(np.percentile(terminal, p)) for p in (5, 25, 50, 75, 95)}

    with_start = np.hstack([np.full((n, 1), starting_equity), equity_paths])
    running_peak = np.maximum.accumulate(with_start, axis=1)[:, 1:]
    drawdown = np.divide(
        running_peak - equity_paths, running_peak, out=np.zeros_like(equity_paths), where=running_peak > 0
    )
    max_dd_per_path = drawdown.max(axis=1)
    dd_pct = {p: float(np.percentile(max_dd_per_path, p)) for p in (50, 95)}

    risk_of_ruin = float(np.mean(equity_paths.min(axis=1) <= 0))

    is_loss = resampled < 0
    streaks = np.zeros(n, dtype=int)
    current = np.zeros(n, dtype=int)
    for col in range(n_trades):
        current = np.where(is_loss[:, col], current + 1, 0)
        streaks = np.maximum(streaks, current)
    streak_pct = {p: float(np.percentile(streaks, p)) for p in (50, 95)}

    return {
        "terminalEquityPercentiles": terminal_pct,
        "maxDrawdownPercentiles": dd_pct,
        "riskOfRuin": risk_of_ruin,
        "longestLosingStreakPercentiles": streak_pct,
        "paths": n,
    }


def walk_forward_windows(
    start: date, end: date, is_months: int = 12, oos_months: int = 3, step_months: int = 3
) -> list[dict]:
    """Rolling anchored windows: [is_start, is_end) optimize, [oos_start,
    oos_end) test, stepping forward step_months at a time until the OOS
    window would run past `end`."""

    def add_months(d: date, months: int) -> date:
        month_index = d.month - 1 + months
        year = d.year + month_index // 12
        month = month_index % 12 + 1
        return date(year, month, min(d.day, 28))

    windows = []
    is_start = start
    while True:
        is_end = add_months(is_start, is_months)
        oos_end = add_months(is_end, oos_months)
        if oos_end > end:
            break
        windows.append({"isStart": is_start, "isEnd": is_end, "oosStart": is_end, "oosEnd": oos_end})
        is_start = add_months(is_start, step_months)
    return windows


def walk_forward_efficiency(is_return: float, oos_return: float) -> float | None:
    """OOS/IS return ratio — None when IS return is zero (undefined)."""
    if is_return == 0:
        return None
    return oos_return / is_return
