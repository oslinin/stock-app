"""/bots — CRUD gated by compile_bot(), start/pause, kill switch (per-bot
+ global). Never auto-flattens an open position (plan) — kill only stops
new entries and cancels a pending (not-yet-filled) order."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from ..bots.compile_bot import compile_bot
from ..bots.models import Bot, BotRun
from ..brokers.ibkr_adapter import IBKRAdapter
from ..db.session import session_scope
from ..security import require_token
from ..specs import service

router = APIRouter(prefix="/bots", dependencies=[Depends(require_token)])


class BotIn(BaseModel):
    specId: int
    mode: str = "paper"
    bpPct: float = 0.05
    maxConcurrent: int = 1
    fixedContracts: int | None = None


def _approved_spec(spec_id: int):
    found = service.get_spec(spec_id)
    if found is None:
        raise HTTPException(404, f"spec {spec_id} not found")
    record, version = found
    if record.status != "approved":
        raise HTTPException(422, "spec must be approved before a bot can be created from it")
    return version.spec()


def _bot_out(bot: Bot) -> dict:
    return {
        "id": bot.id,
        "specId": bot.spec_id,
        "broker": bot.broker,
        "mode": bot.mode,
        "status": bot.status,
        "bpPct": bot.bp_pct,
        "maxConcurrent": bot.max_concurrent,
        "fixedContracts": bot.fixed_contracts,
        "positionState": bot.position_state,
        "pendingOrderId": bot.pending_order_id,
        "createdAt": bot.created_at.isoformat(),
    }


@router.get("")
def list_bots() -> list[dict]:
    with session_scope() as session:
        return [_bot_out(b) for b in session.exec(select(Bot).order_by(Bot.id)).all()]


@router.post("", status_code=201)
def create_bot(body: BotIn, request: Request) -> dict:
    if body.mode == "live" and not request.app.state.settings.allow_live_trading:
        raise HTTPException(422, "live bots are disabled (ALLOW_LIVE_TRADING=false)")
    spec = _approved_spec(body.specId)
    blockers = compile_bot(spec)
    if blockers:
        raise HTTPException(422, {"blockers": blockers})
    with session_scope() as session:
        bot = Bot(
            spec_id=body.specId,
            mode=body.mode,
            bp_pct=body.bpPct,
            max_concurrent=body.maxConcurrent,
            fixed_contracts=body.fixedContracts,
        )
        session.add(bot)
        session.flush()
        return _bot_out(bot)


@router.get("/{bot_id}")
def get_bot(bot_id: int) -> dict:
    with session_scope() as session:
        bot = session.get(Bot, bot_id)
        if bot is None:
            raise HTTPException(404, "bot not found")
        return _bot_out(bot)


@router.get("/{bot_id}/runs")
def list_runs(bot_id: int, limit: int = 50) -> list[dict]:
    with session_scope() as session:
        runs = session.exec(
            select(BotRun).where(BotRun.bot_id == bot_id).order_by(BotRun.id.desc()).limit(min(limit, 200))  # type: ignore[union-attr]
        ).all()
        return [
            {
                "tickAt": r.tick_at.isoformat(),
                "positionState": r.position_state,
                "action": r.action,
                "detail": r.detail,
            }
            for r in runs
        ]


@router.post("/{bot_id}/start")
def start_bot(bot_id: int, request: Request) -> dict:
    with session_scope() as session:
        bot = session.get(Bot, bot_id)
        if bot is None:
            raise HTTPException(404, "bot not found")
        if bot.status == "killed":
            raise HTTPException(422, "a killed bot cannot be restarted — create a new one")
        if bot.mode == "live" and not request.app.state.settings.allow_live_trading:
            raise HTTPException(422, "live bots are disabled (ALLOW_LIVE_TRADING=false)")
        spec = _approved_spec(bot.spec_id)
        blockers = compile_bot(spec)
        if blockers:
            raise HTTPException(422, {"blockers": blockers})
        bot.status = "running"
        session.add(bot)
        return _bot_out(bot)


@router.post("/{bot_id}/pause")
def pause_bot(bot_id: int) -> dict:
    with session_scope() as session:
        bot = session.get(Bot, bot_id)
        if bot is None:
            raise HTTPException(404, "bot not found")
        bot.status = "paused"
        session.add(bot)
        return _bot_out(bot)


async def _kill(session, bot: Bot, request: Request) -> None:
    bot.status = "killed"
    pending = bot.pending_order_id
    bot.pending_order_id = None
    session.add(bot)
    if pending:
        broker = IBKRAdapter(request.app.state.ib, request.app.state.settings)
        try:
            await broker.cancel(pending)
        except Exception:  # noqa: BLE001 - kill must always mark the bot killed
            pass


@router.post("/{bot_id}/kill")
async def kill_bot(bot_id: int, request: Request) -> dict:
    with session_scope() as session:
        bot = session.get(Bot, bot_id)
        if bot is None:
            raise HTTPException(404, "bot not found")
        await _kill(session, bot, request)
        return _bot_out(bot)


@router.post("/kill-all")
async def kill_all(request: Request) -> dict:
    with session_scope() as session:
        bots = session.exec(select(Bot).where(Bot.status.in_(["running", "paused"]))).all()  # type: ignore[union-attr]
        for bot in bots:
            await _kill(session, bot, request)
        return {"killed": len(bots)}
