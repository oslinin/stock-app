"""Condition evaluators: pure functions of (params, MarketContext).

MarketContext is a plain data snapshot — live ticks build it from
providers/analytics (see routes_specs.build_market_context), backtests
will build the same shape from historical data. No strategy logic lives
outside CONDITION_EVALUATORS: same rules, same evaluators, either clock.

Param key convention matches the phase-1 seeded spec (app/specs/seed.py):
single-threshold conditions use "value", ranges use "min"/"max". A
condition kind with no evaluator, or an evaluator with missing data,
fails closed (never a false ENTER on incomplete information).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable

from ..analytics.ivrank import iv_rank
from ..analytics.ta import sma
from .schema import Condition

WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@dataclass
class MarketContext:
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    vix: float | None = None
    price: float | None = None
    closes: list[float] = field(default_factory=list)
    current_iv: float | None = None
    iv_history: list[float] = field(default_factory=list)
    dte: int | None = None
    delta: float | None = None
    credit_pct_width: float | None = None


@dataclass
class CheckResult:
    passed: bool
    observed: float | str | None
    detail: str = ""


Evaluator = Callable[[dict, MarketContext], Awaitable[CheckResult]]


def _fail(detail: str) -> CheckResult:
    return CheckResult(passed=False, observed=None, detail=detail)


async def _iv_rank_gte(params: dict, ctx: MarketContext) -> CheckResult:
    if ctx.current_iv is None or not ctx.iv_history:
        return _fail("no IV history in context")
    rank = iv_rank(ctx.iv_history, ctx.current_iv)
    if rank is None:
        return _fail("IV rank undefined (flat history)")
    return CheckResult(rank >= params["value"], rank)


async def _iv_rank_lte(params: dict, ctx: MarketContext) -> CheckResult:
    if ctx.current_iv is None or not ctx.iv_history:
        return _fail("no IV history in context")
    rank = iv_rank(ctx.iv_history, ctx.current_iv)
    if rank is None:
        return _fail("IV rank undefined (flat history)")
    return CheckResult(rank <= params["value"], rank)


async def _dte_between(params: dict, ctx: MarketContext) -> CheckResult:
    if ctx.dte is None:
        return _fail("no candidate DTE in context")
    return CheckResult(params["min"] <= ctx.dte <= params["max"], ctx.dte)


async def _delta_between(params: dict, ctx: MarketContext) -> CheckResult:
    if ctx.delta is None:
        return _fail("no candidate delta in context")
    return CheckResult(params["min"] <= ctx.delta <= params["max"], ctx.delta)


async def _vix_below(params: dict, ctx: MarketContext) -> CheckResult:
    if ctx.vix is None:
        return _fail("no VIX quote in context")
    return CheckResult(ctx.vix < params["value"], ctx.vix)


async def _vix_above(params: dict, ctx: MarketContext) -> CheckResult:
    if ctx.vix is None:
        return _fail("no VIX quote in context")
    return CheckResult(ctx.vix > params["value"], ctx.vix)


async def _price_above_sma(params: dict, ctx: MarketContext) -> CheckResult:
    if ctx.price is None:
        return _fail("no price in context")
    avg = sma(ctx.closes, params["period"])[-1:] or [None]
    if avg[0] is None:
        return _fail(f"fewer than {params['period']} closes in context")
    return CheckResult(ctx.price > avg[0], avg[0])


async def _price_below_sma(params: dict, ctx: MarketContext) -> CheckResult:
    if ctx.price is None:
        return _fail("no price in context")
    avg = sma(ctx.closes, params["period"])[-1:] or [None]
    if avg[0] is None:
        return _fail(f"fewer than {params['period']} closes in context")
    return CheckResult(ctx.price < avg[0], avg[0])


async def _day_of_week_in(params: dict, ctx: MarketContext) -> CheckResult:
    today = WEEKDAY_NAMES[ctx.now.weekday()]
    wanted = [d.strip().lower()[:3] for d in params["days"]]
    return CheckResult(today in wanted, today)


async def _credit_min_pct_width(params: dict, ctx: MarketContext) -> CheckResult:
    if ctx.credit_pct_width is None:
        return _fail("no priced structure in context")
    return CheckResult(ctx.credit_pct_width >= params["value"], ctx.credit_pct_width)


CONDITION_EVALUATORS: dict[str, Evaluator] = {
    "iv_rank_gte": _iv_rank_gte,
    "iv_rank_lte": _iv_rank_lte,
    "dte_between": _dte_between,
    "delta_between": _delta_between,
    "vix_below": _vix_below,
    "vix_above": _vix_above,
    "price_above_sma": _price_above_sma,
    "price_below_sma": _price_below_sma,
    "day_of_week_in": _day_of_week_in,
    "credit_min_pct_width": _credit_min_pct_width,
}


async def evaluate_all(
    conditions: list[Condition], ctx: MarketContext
) -> tuple[bool, list[dict]]:
    """AND semantics: every condition must pass. A kind with no
    evaluator fails closed rather than being silently skipped."""
    checks: list[dict] = []
    all_passed = True
    for cond in conditions:
        evaluator = CONDITION_EVALUATORS.get(cond.kind)
        if evaluator is None:
            result = _fail(f"interpreter does not yet support '{cond.kind}'")
        else:
            result = await evaluator(cond.params, ctx)
        checks.append(
            {
                "kind": cond.kind,
                "pass": result.passed,
                "observed": result.observed,
                "detail": result.detail,
            }
        )
        all_passed = all_passed and result.passed
    return all_passed, checks
