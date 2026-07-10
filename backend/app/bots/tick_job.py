"""bot_tick: drives every running bot's tick() once, RTH cadence (1 min).
Reuses build_market_context (Phase 3) for entry conditions and the
CHAIN provider (Phase 2) for leg resolution — same layers every other
job in this codebase builds on. A bot-level exception is caught, logged,
and skipped, same discipline as iv_snapshot/watchlist_scan/beta_refresh:
one bot's failure never stops the rest from ticking."""

from __future__ import annotations

import logging

from sqlmodel import select

from ..api.routes_specs import build_market_context
from ..brokers.ibkr_adapter import IBKRAdapter
from ..dataproviders.base import CHAIN, ProviderError
from ..db.session import session_scope
from ..specs import service
from .models import Bot, BotRun
from .runtime import tick

log = logging.getLogger(__name__)


async def bot_tick(providers, client, settings) -> None:
    with session_scope() as session:
        bots = session.exec(select(Bot).where(Bot.status == "running")).all()
        snapshots = [
            {
                "id": b.id,
                "spec_id": b.spec_id,
                "mode": b.mode,
                "status": b.status,
                "bp_pct": b.bp_pct,
                "max_concurrent": b.max_concurrent,
                "fixed_contracts": b.fixed_contracts,
                "position_state": b.position_state,
                "pending_order_id": b.pending_order_id,
            }
            for b in bots
        ]
        open_positions_global = len(
            session.exec(
                select(Bot).where(Bot.status == "running", Bot.position_state == "IN_POSITION")
            ).all()
        )

    if not snapshots:
        return

    broker = IBKRAdapter(client, settings)
    for snap in snapshots:
        try:
            await _tick_one(providers, broker, snap, open_positions_global, settings)
        except Exception as exc:  # noqa: BLE001 - one bot's failure must not stop the rest
            log.warning("bot_tick skipped for bot %s: %s", snap["id"], exc)


async def _tick_one(providers, broker, snap: dict, open_positions_global: int, settings) -> None:
    found = service.get_spec(snap["spec_id"])
    if found is None or found[0].status != "approved":
        log.warning("bot_tick: bot %s spec not approved, skipping", snap["id"])
        return
    _, version = found
    spec = version.spec()
    symbol = spec.universe.underlyings[0] if spec.universe.underlyings else ""
    ctx = await build_market_context(providers, symbol)

    chain: list[dict] = []
    if snap["position_state"] == "ENTRY_SIGNALED":
        try:
            provider = providers.route(CHAIN)
            expiries = await provider.expiries(symbol)
            if not expiries:
                log.warning("bot_tick: no listed expiries for %s, skipping", symbol)
                return
            chain = await provider.chain(symbol, expiries[0])
        except ProviderError as exc:
            log.warning("bot_tick: no chain for %s: %s", symbol, exc)
            return

    class BotView:
        status = snap["status"]
        bp_pct = snap["bp_pct"]
        max_concurrent = snap["max_concurrent"]
        fixed_contracts = snap["fixed_contracts"]

    result = await tick(
        bot=BotView(),
        spec=spec,
        position_state=snap["position_state"],
        order_id=snap["pending_order_id"],
        ctx=ctx,
        chain=chain,
        broker=broker,
        risk_inputs=dict(
            net_liq=100_000.0,  # ponytail: real NetLiq needs portfolio/ibkr_positions.py's
            # accountSummary() wired in here — placeholder until that follow-up lands;
            # the risk gate still runs, just against an assumed account size.
            open_positions=open_positions_global,
            realized_pnl_today=0.0,  # needs journal/execution history (not built yet)
            global_max_bp_pct=settings.bot_max_bp_pct,
            global_max_concurrent=settings.bot_max_concurrent_global,
            daily_loss_halt_usd=settings.bot_daily_loss_halt_usd,
        ),
    )

    with session_scope() as session:
        bot = session.get(Bot, snap["id"])
        if bot is None:
            return
        bot.position_state = result.position_state
        bot.pending_order_id = result.order_id
        session.add(bot)
        session.add(
            BotRun(
                bot_id=snap["id"],
                position_state=result.position_state,
                action=result.action,
                detail=result.detail,
            )
        )
