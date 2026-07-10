"""Screener registry: pure functions over symbol_metrics-shaped rows
(plain dicts). No chain fetch, no DB access here — the route layer
loads today's rows and hands them in. Every screener respects the same
optional liquidity params (min_open_interest, max_spread_pct)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Screener:
    id: str
    name: str
    description: str
    run: Callable[[list[dict], dict], list[dict]]


def _liquid(rows: list[dict], params: dict) -> list[dict]:
    min_oi = params.get("min_open_interest")
    max_spread = params.get("max_spread_pct")
    out = rows
    if min_oi is not None:
        out = [r for r in out if (r.get("open_interest") or 0) >= min_oi]
    if max_spread is not None:
        out = [r for r in out if (r.get("spread_pct") or 0) <= max_spread]
    return out


def _expensive_premium(rows: list[dict], params: dict) -> list[dict]:
    candidates = [r for r in _liquid(rows, params) if r.get("premium_yield") is not None]
    return sorted(candidates, key=lambda r: r["premium_yield"], reverse=True)


def _high_ivr(rows: list[dict], params: dict) -> list[dict]:
    min_ivr = params.get("min_iv_rank", 50)
    candidates = [
        r for r in _liquid(rows, params) if r.get("iv_rank") is not None and r["iv_rank"] >= min_ivr
    ]
    return sorted(candidates, key=lambda r: r["iv_rank"], reverse=True)


def _delta_dte_candidates(rows: list[dict], params: dict) -> list[dict]:
    dmin = params.get("delta_min", 0.16)
    dmax = params.get("delta_max", 0.30)
    dte_min = params.get("dte_min", 21)
    dte_max = params.get("dte_max", 45)
    return [
        r
        for r in _liquid(rows, params)
        if r.get("sampled_delta") is not None
        and dmin <= abs(r["sampled_delta"]) <= dmax
        and r.get("sampled_dte") is not None
        and dte_min <= r["sampled_dte"] <= dte_max
    ]


SCREENER_REGISTRY: dict[str, Screener] = {
    "expensive_premium": Screener(
        id="expensive_premium",
        name="Expensive premium to sell",
        description="Highest ATM straddle premium per day of notional (a simple credit/BP/day proxy).",
        run=_expensive_premium,
    ),
    "high_ivr": Screener(
        id="high_ivr",
        name="High IV rank",
        description="IV rank at or above a threshold (default 50), ranked descending.",
        run=_high_ivr,
    ),
    "delta_dte_candidates": Screener(
        id="delta_dte_candidates",
        name="0.16–30Δ, 21–45 DTE candidates",
        description="Symbols whose sampled short strike sits in the classic premium-selling band.",
        run=_delta_dte_candidates,
    ),
}


def run_screener(screener_id: str, rows: list[dict], params: dict) -> list[dict]:
    return SCREENER_REGISTRY[screener_id].run(rows, params)
