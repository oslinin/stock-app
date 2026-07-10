"""Risk gate: every check runs before a bot's DraftOrder is placed; any
failure blocks the order (fires a risk_blocked event, at the call site).
Pure functions over plain inputs — no DB/broker access here.

ponytail: portfolio-level caps from the plan (max beta-weighted delta,
max net short vega, correlated-exposure cap using the beta cache) aren't
built this phase — they need live cross-bot portfolio state the tick
loop doesn't assemble yet. Ceiling: five bots each "within limits" can
still be one correlated short-vol position. Upgrade path: fold
portfolio/aggregate.py's summary into run_risk_gate's inputs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskCheckResult:
    passed: bool
    reason: str = ""


def check_daily_loss_halt(realized_pnl_today: float, halt_usd: float) -> RiskCheckResult:
    if halt_usd > 0 and realized_pnl_today <= -halt_usd:
        return RiskCheckResult(
            False, f"daily realized loss {realized_pnl_today:.0f} breached halt at -{halt_usd:.0f}"
        )
    return RiskCheckResult(True)


def check_concurrency(open_positions: int, bot_max_concurrent: int, global_max_concurrent: int) -> RiskCheckResult:
    limit = min(bot_max_concurrent, global_max_concurrent)
    if open_positions >= limit:
        return RiskCheckResult(False, f"{open_positions} open position(s) already at the {limit} limit")
    return RiskCheckResult(True)


def check_bp_pct(margin_required: float, net_liq: float, bp_pct: float, global_max_bp_pct: float) -> RiskCheckResult:
    if net_liq <= 0:
        return RiskCheckResult(False, "no NetLiq available")
    fraction = margin_required / net_liq
    limit = min(bp_pct, global_max_bp_pct)
    if fraction > limit:
        return RiskCheckResult(False, f"margin {fraction:.1%} of NetLiq exceeds the {limit:.1%} limit")
    return RiskCheckResult(True)


def run_risk_gate(
    *,
    margin_required: float,
    net_liq: float,
    bp_pct: float,
    global_max_bp_pct: float,
    open_positions: int,
    bot_max_concurrent: int,
    global_max_concurrent: int,
    realized_pnl_today: float,
    daily_loss_halt_usd: float,
) -> RiskCheckResult:
    for check in (
        check_daily_loss_halt(realized_pnl_today, daily_loss_halt_usd),
        check_concurrency(open_positions, bot_max_concurrent, global_max_concurrent),
        check_bp_pct(margin_required, net_liq, bp_pct, global_max_bp_pct),
    ):
        if not check.passed:
            return check
    return RiskCheckResult(True)
