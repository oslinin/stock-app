"""1-variable OLS beta of a symbol's daily returns against a benchmark
(SPY), with the R2 low-confidence flag the plan calls for."""

from __future__ import annotations

import numpy as np

LOW_R2_THRESHOLD = 0.3


def compute_beta(symbol_returns: list[float], benchmark_returns: list[float]) -> tuple[float, float] | None:
    """(beta, r2); None when there aren't enough points or the benchmark
    has no variance (beta undefined)."""
    if len(symbol_returns) != len(benchmark_returns) or len(symbol_returns) < 2:
        return None
    y = np.array(symbol_returns, dtype=float)
    x = np.array(benchmark_returns, dtype=float)
    if np.isclose(x.std(), 0.0):
        return None
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    ss_res = float(np.sum((y - predicted) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return float(slope), r2


def is_low_confidence(r2: float) -> bool:
    return r2 < LOW_R2_THRESHOLD
