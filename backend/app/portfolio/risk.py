"""Forward-looking 1-day portfolio CVaR by historical simulation: reprice
every position under a set of underlying return scenarios and take the
tail mean of simulated P&L.

Options are repriced with full Black-Scholes (captures gamma, not just a
delta approximation); IV is held constant across scenarios (sticky-IV).
ponytail: a beta-scaled vol shock (IV moves with the underlying move) is
the natural upgrade — deferred, since sticky-IV is what the plan's own
"single short put, CVaR ~= tail repricing by hand" acceptance check
validates against. Stock/perp positions reprice linearly.
"""

from __future__ import annotations

from ..analytics.greeks import bs_price


def daily_returns(closes: list[float]) -> list[float]:
    return [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1]
    ]


def reprice_pnl(position: dict, ret: float, r: float) -> float:
    """P&L for one position under one scenario return `ret` (e.g. 0.02 = +2%),
    one trading day forward."""
    quantity = position["quantity"]
    multiplier = position.get("multiplier", 1)
    spot = position["spot"]

    if position["secType"] == "STK":
        return spot * ret * quantity * multiplier

    iv = position.get("iv")
    t_years = position.get("tYears")
    if iv is None or not t_years or t_years <= 0:
        raise ValueError("option position needs iv and tYears to reprice")
    strike = position["strike"]
    right = position["right"]
    current = bs_price(right, spot, strike, t_years, r, iv)
    new_spot = spot * (1 + ret)
    new_t = max(t_years - 1 / 365, 1e-6)
    repriced = bs_price(right, new_spot, strike, new_t, r, iv)
    return (repriced - current) * quantity * multiplier


def simulate_portfolio_pnl(positions: list[dict], scenarios: list[float], r: float) -> list[float]:
    return [sum(reprice_pnl(p, ret, r) for p in positions) for ret in scenarios]


def cvar(pnls: list[float], confidence: float = 0.95) -> float:
    """Expected shortfall: mean P&L in the worst (1-confidence) tail.
    Negative = expected loss. 0.0 for an empty series."""
    if not pnls:
        return 0.0
    ordered = sorted(pnls)  # ascending: worst (most negative) first
    tail_size = max(1, round(len(ordered) * (1 - confidence)))
    tail = ordered[:tail_size]
    return sum(tail) / len(tail)
