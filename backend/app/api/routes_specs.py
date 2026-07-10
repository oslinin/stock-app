from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError
from sqlmodel import select

from ..dataproviders.base import BARS, QUOTE, ProviderError
from ..dataproviders.models import IVHistory
from ..db.session import session_scope
from ..security import require_token
from ..specs import service
from ..specs.compile_doc import compile_doc
from ..specs.interpreter import MarketContext, evaluate_all
from ..specs.models import SpecVersion, StrategySpec
from ..specs.schema import OptionsStrategySpec
from ..strategies.registry import build_registry

VIX_SYMBOL = "^VIX"  # yfinance's symbol for the CBOE VIX index

router = APIRouter(prefix="/specs", dependencies=[Depends(require_token)])


def _refresh_registry(request: Request) -> None:
    """approve/edit can add or drop a spec strategy from the registry —
    it's built once at startup, so mutations that change a spec's
    approved-ness must refresh the live snapshot, not just the DB row.

    ponytail: only app.state.registry is refreshed here (read by
    /strategies and /screener lookups, and this module's own /verdict).
    engine.registry (a separate reference the scheduler's VIX-specific
    jobs iterate — see scheduler/jobs.py) deliberately stays frozen at
    boot: those jobs call VIX-only ScreenerEngine methods that assume
    VixHedgeStrategy's shape and would break on a SpecStrategy. Ceiling:
    spec strategies never get scheduled alert scans. Upgrade path: a
    dedicated spec-aware scan job, not a generic engine.registry refresh.
    """
    request.app.state.registry = build_registry(request.app.state.settings)


class SpecIn(BaseModel):
    spec: OptionsStrategySpec
    claimed_performance: dict | None = None


def _record_out(record: StrategySpec, version: SpecVersion | None = None) -> dict:
    out = {
        "id": record.id,
        "slug": record.slug,
        "name": record.name,
        "category": record.category,
        "origin": record.origin,
        "status": record.status,
        "lifecycle": record.lifecycle,
        "sections": record.section_status,
        "claimedPerformance": record.claimed_performance,
        "currentVersionId": record.current_version_id,
        "createdAt": record.created_at.isoformat(),
        "updatedAt": record.updated_at.isoformat(),
    }
    if version is not None:
        out["version"] = version.version
        out["spec"] = json.loads(version.spec_json)
        out["createdBy"] = version.created_by
        out["reviewedAt"] = (
            version.reviewed_at.isoformat() if version.reviewed_at else None
        )
    return out


@router.get("")
def list_specs(
    status: str | None = None,
    origin: str | None = None,
    category: str | None = None,
    lifecycle: str | None = None,
) -> list[dict]:
    return [
        _record_out(r)
        for r in service.list_specs(
            status=status, origin=origin, category=category, lifecycle=lifecycle
        )
    ]


@router.post("", status_code=201)
def create_spec(body: SpecIn) -> dict:
    record = service.create_spec(
        body.spec, claimed_performance=body.claimed_performance
    )
    found = service.get_spec(record.id)
    return _record_out(*found)


@router.get("/{spec_id}")
def get_spec(spec_id: int) -> dict:
    found = service.get_spec(spec_id)
    if found is None:
        raise HTTPException(404, "spec not found")
    return _record_out(*found)


@router.put("/{spec_id}")
def update_spec(spec_id: int, body: SpecIn, request: Request) -> dict:
    try:
        service.add_version(spec_id, body.spec)
    except KeyError:
        raise HTTPException(404, "spec not found")
    if body.claimed_performance is not None:
        with session_scope() as session:
            record = session.get(StrategySpec, spec_id)
            record.claimed_performance_json = json.dumps(body.claimed_performance)
            session.add(record)
    _refresh_registry(request)  # editing demotes status away from approved
    found = service.get_spec(spec_id)
    return _record_out(*found)


@router.post("/{spec_id}/approve")
def approve_spec(spec_id: int, request: Request) -> dict:
    try:
        service.approve_spec(spec_id)
    except KeyError:
        raise HTTPException(404, "spec not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    _refresh_registry(request)
    found = service.get_spec(spec_id)
    return _record_out(*found)


def _load(spec_id: int) -> tuple[StrategySpec, OptionsStrategySpec]:
    found = service.get_spec(spec_id)
    if found is None or found[1] is None:
        raise HTTPException(404, "spec not found")
    record, version = found
    try:
        return record, version.spec()
    except ValidationError as exc:  # stored JSON predates a schema change
        raise HTTPException(500, f"stored spec no longer parses: {exc}")


@router.get("/{spec_id}/doc")
def spec_doc(spec_id: int, reference_price: float = 100.0) -> dict:
    record, spec = _load(spec_id)
    return compile_doc(
        spec,
        reference_price=reference_price,
        claimed_performance=record.claimed_performance,
    )


@router.get("/{spec_id}/payoff")
def spec_payoff(spec_id: int, reference_price: float = 100.0) -> dict:
    _, spec = _load(spec_id)
    return compile_doc(spec, reference_price=reference_price)["payoff"]


async def build_market_context(providers, symbol: str) -> MarketContext:
    """Same layers /marketdata uses: dataproviders for quote/bars, the
    iv_history table for IV rank. Missing pieces (dte/delta/credit% —
    need a priced chain, not built yet) are left None; evaluators that
    need them fail closed rather than guess."""
    ctx = MarketContext()
    if symbol:
        try:
            ctx.price = (await providers.route(QUOTE).quote(symbol))["price"]
        except ProviderError:
            pass
        try:
            bars = await providers.route(BARS).bars(symbol, period="1y", interval="1d")
            ctx.closes = [b["close"] for b in bars]
        except ProviderError:
            pass
    try:
        ctx.vix = (await providers.route(QUOTE).quote(VIX_SYMBOL))["price"]
    except ProviderError:
        pass
    with session_scope() as session:
        rows = session.exec(
            select(IVHistory)
            .where(IVHistory.symbol == symbol.upper())
            .order_by(IVHistory.date)
        ).all()
        if rows:
            ctx.iv_history = [r.atm_iv for r in rows[:-1]]
            ctx.current_iv = rows[-1].atm_iv
    return ctx


@router.get("/{spec_id}/verdict")
async def spec_verdict(spec_id: int, request: Request) -> dict:
    """Entry-condition verdict for an approved spec — the Phase 3
    "screener": same AND-semantics interpreter a bot will run live."""
    record, spec = _load(spec_id)
    symbol = spec.universe.underlyings[0] if spec.universe.underlyings else ""
    ctx = await build_market_context(request.app.state.providers, symbol)
    passed, checks = await evaluate_all(spec.entry, ctx)
    return {
        "specId": spec_id,
        "underlying": symbol,
        "verdict": "ENTER" if passed and checks else "WAIT",
        "checks": checks,
        "asOf": datetime.now(timezone.utc).isoformat(),
    }
