"""Bot tick state machine: FLAT -> ENTRY_SIGNALED -> ORDER_PENDING ->
IN_POSITION. One function drives a real IBKRAdapter or a SimBroker
(test/replay) identically, since both implement the same BrokerAdapter
protocol — no test doubles of strategy logic, only the broker and clock
are simulated (plan). Exit/adjustment monitoring (MANAGING) isn't built
this phase; compile_bot refuses specs with adjustment rules so a bot
never opens a position it can't safely manage the exit of."""

from __future__ import annotations

from dataclasses import dataclass

from ..brokers.base import DraftLeg, DraftOrder
from ..specs.interpreter import MarketContext, evaluate_all
from .leg_resolver import net_limit_price, resolve_legs
from .risk import run_risk_gate


@dataclass
class TickResult:
    position_state: str
    action: str
    detail: str = ""
    order_id: str | None = None
    whatif: dict | None = None


async def tick(
    *,
    bot,  # anything with: status, bp_pct, max_concurrent, fixed_contracts
    spec,  # OptionsStrategySpec
    position_state: str,
    order_id: str | None,
    ctx: MarketContext,
    chain: list[dict],
    broker,
    risk_inputs: dict,  # net_liq, open_positions, realized_pnl_today, global_max_bp_pct, global_max_concurrent, daily_loss_halt_usd
) -> TickResult:
    if bot.status != "running":
        return TickResult(position_state, "skipped", f"bot status is {bot.status!r}, not running")

    if position_state == "FLAT":
        entry_ok, _ = await evaluate_all(spec.entry, ctx)
        gates_ok, _ = await evaluate_all(spec.gates, ctx)
        if not (entry_ok and gates_ok):
            return TickResult("FLAT", "wait", "entry conditions or gates not met")
        return TickResult("ENTRY_SIGNALED", "entry_signaled", "entry conditions and gates met")

    if position_state == "ENTRY_SIGNALED":
        resolved = resolve_legs(spec.structure, chain, ctx.price)
        limit_price = net_limit_price(resolved)
        quantity = bot.fixed_contracts or 1
        symbol = spec.universe.underlyings[0]
        draft = DraftOrder(
            legs=[
                DraftLeg(symbol, "OPT", leg.right, leg.strike, leg.row.get("expiry"), leg.action, leg.ratio)
                for leg in resolved
            ],
            quantity=quantity,
            limit_price=limit_price,
        )
        what_if = await broker.what_if(draft)
        margin = what_if.init_margin if what_if.init_margin is not None else abs(limit_price) * quantity * 100
        gate = run_risk_gate(
            margin_required=margin,
            bp_pct=bot.bp_pct,
            bot_max_concurrent=bot.max_concurrent,
            **risk_inputs,
        )
        if not gate.passed:
            return TickResult("FLAT", "risk_blocked", gate.reason, whatif=what_if.__dict__)
        placed_id, fill = await broker.place(draft)
        if fill is not None:
            return TickResult(
                "IN_POSITION", "filled", f"filled at {fill.fill_price}", order_id=placed_id, whatif=what_if.__dict__
            )
        return TickResult("ORDER_PENDING", "order_placed", "", order_id=placed_id, whatif=what_if.__dict__)

    if position_state == "ORDER_PENDING":
        fill = await broker.poll_fill(order_id)
        if fill is None:
            return TickResult("ORDER_PENDING", "waiting_for_fill", "", order_id=order_id)
        return TickResult("IN_POSITION", "filled", f"filled at {fill.fill_price}", order_id=order_id)

    if position_state == "IN_POSITION":
        return TickResult("IN_POSITION", "hold", "exit/adjustment monitoring not built this phase", order_id=order_id)

    raise ValueError(f"unknown position_state {position_state!r}")
