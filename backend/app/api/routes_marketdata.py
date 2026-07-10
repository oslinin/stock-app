"""/marketdata — provider-labeled quotes, bars, chains, indicators, IV rank.

Every data response is a provenance envelope: {data, provenance:{source,
asof, latency}}. `?source=` overrides capability routing (400 on a bad
source, 502 when the upstream provider fails).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import select

from ..analytics.greeks import enrich_chain
from ..analytics.ivrank import iv_percentile, iv_rank
from ..analytics.ta import compute_indicators
from ..dataproviders.alphavantage import BudgetExceeded
from ..dataproviders.base import BARS, CHAIN, EXPIRIES, QUOTE, ProviderError, envelope
from ..dataproviders.models import IVHistory
from ..dataproviders.registry import ProviderRegistry
from ..db.session import session_scope
from ..security import require_token

router = APIRouter(prefix="/marketdata", dependencies=[Depends(require_token)])


def _registry(request: Request) -> ProviderRegistry:
    return request.app.state.providers


def _route(request: Request, capability: str, source: str | None):
    try:
        return _registry(request).route(capability, source=source)
    except ProviderError as exc:  # bad ?source= / unsupported capability
        raise HTTPException(400, str(exc))


async def _call(coro):
    try:
        return await coro
    except BudgetExceeded as exc:
        raise HTTPException(429, str(exc))
    except ProviderError as exc:
        raise HTTPException(502, str(exc))


@router.get("/providers")
def providers(request: Request) -> list[dict]:
    return _registry(request).describe()


@router.get("/quote")
async def quote(request: Request, symbol: str, source: str | None = None) -> dict:
    provider = _route(request, QUOTE, source)
    return envelope(await _call(provider.quote(symbol)), provider)


@router.get("/bars")
async def bars(
    request: Request,
    symbol: str,
    period: str = "6mo",
    interval: str = "1d",
    source: str | None = None,
) -> dict:
    provider = _route(request, BARS, source)
    data = await _call(provider.bars(symbol, period=period, interval=interval))
    return envelope(data, provider)


@router.get("/expiries")
async def expiries(request: Request, symbol: str, source: str | None = None) -> dict:
    provider = _route(request, EXPIRIES, source)
    return envelope(await _call(provider.expiries(symbol)), provider)


@router.get("/chain")
async def chain(
    request: Request,
    symbol: str,
    expiry: str | None = None,
    source: str | None = None,
    greeks: bool = True,
) -> dict:
    provider = _route(request, CHAIN, source)
    if expiry is None:
        listed = await _call(provider.expiries(symbol))
        expiry = listed[0]
    rows = await _call(provider.chain(symbol, expiry))

    spot = None
    if QUOTE in provider.capabilities:
        try:
            spot = (await provider.quote(symbol))["price"]
        except ProviderError:
            pass
    if greeks and spot is not None:
        try:
            exp_date = date.fromisoformat(expiry)
            t_years = max((exp_date - date.today()).days, 0) / 365.0
            if t_years > 0:
                settings = request.app.state.settings
                enrich_chain(rows, spot=spot, t_years=t_years, r=settings.analytics_risk_free_rate)
        except ValueError:
            pass  # provider-specific expiry format: skip enrichment
    return envelope(
        {"symbol": symbol.upper(), "expiry": expiry, "spot": spot, "rows": rows},
        provider,
    )


@router.get("/indicators")
async def indicators(
    request: Request,
    symbol: str,
    set: str = "macd,rsi,bbands",
    period: str = "6mo",
    interval: str = "1d",
    source: str | None = None,
) -> dict:
    provider = _route(request, BARS, source)
    bar_data = await _call(provider.bars(symbol, period=period, interval=interval))
    names = [n.strip() for n in set.split(",") if n.strip()]
    try:
        series = compute_indicators(bar_data, names)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return envelope(
        {"times": [b["time"] for b in bar_data], "indicators": series}, provider
    )


@router.get("/ivrank")
def ivrank(request: Request, symbol: str, lookback_days: int = 252) -> dict:
    """IV rank/percentile over the iv_history table (written nightly by the
    iv_snapshot job — needs at least two snapshots to be defined)."""
    symbol = symbol.upper()
    with session_scope() as session:
        rows = session.exec(
            select(IVHistory)
            .where(IVHistory.symbol == symbol)
            .order_by(IVHistory.date.desc())
            .limit(lookback_days)
        ).all()
    if not rows:
        raise HTTPException(
            404,
            f"no IV history for '{symbol}' yet — the nightly iv_snapshot job "
            "syncs it from IBKR's IV index (backfills ~1y on first run; "
            "requires the gateway)",
        )
    rows = list(reversed(rows))
    history = [r.atm_iv for r in rows]
    current = history[-1]
    return {
        "data": {
            "symbol": symbol,
            "atmIv": current,
            "ivRank": iv_rank(history[:-1], current) if len(history) > 1 else None,
            "ivPercentile": iv_percentile(history[:-1], current) if len(history) > 1 else None,
            "observations": len(history),
            "series": [{"date": r.date.isoformat(), "atmIv": r.atm_iv} for r in rows],
        },
        "provenance": {
            "source": f"iv_history({rows[-1].source})",
            "asof": datetime.now(timezone.utc).isoformat(),
            "latency": "eod",
        },
    }
