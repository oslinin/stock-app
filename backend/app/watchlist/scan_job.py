"""Nightly watchlist scan: for each watched symbol, sample the option
chain at the nearest listed expiry and write one symbol_metrics row per
symbol per day. Batches respect provider pacing; a provider error on one
symbol is logged and skipped, never crashes the job (same discipline as
scheduler/jobs.py:iv_snapshot)."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, datetime, timezone

from sqlmodel import select

from ..analytics.ivrank import iv_percentile, iv_rank
from ..dataproviders.base import ProviderError
from ..dataproviders.models import IVHistory
from ..db.session import session_scope
from .models import SymbolMetrics, WatchlistItem

log = logging.getLogger(__name__)

CHUNK_SIZE = 10
PACE_DELAY_SECONDS = 0.2


def batch_plan(symbols: list[str], chunk_size: int = CHUNK_SIZE) -> list[list[str]]:
    return [symbols[i : i + chunk_size] for i in range(0, len(symbols), chunk_size)]


def _nearest_row(rows: list[dict], underlying_px: float) -> dict:
    """The strike closest to spot stands in for "the" chain sample —
    one representative delta/IV/OI/spread per symbol per day."""
    return min(rows, key=lambda r: abs(r["strike"] - underlying_px))


async def _scan_symbol(provider, symbol: str, today: date) -> SymbolMetrics | None:
    underlying_px = (await provider.quote(symbol))["price"]

    expiries = await provider.expiries(symbol)
    if not expiries:
        return None
    expiry = expiries[0]
    dte = (date.fromisoformat(expiry) - today).days

    rows = await provider.chain(symbol, expiry)
    if not rows:
        return None
    sampled = _nearest_row(rows, underlying_px)

    mid = (sampled["bid"] + sampled["ask"]) / 2
    spread_pct = (sampled["ask"] - sampled["bid"]) / mid if mid else None
    premium_yield = mid / underlying_px / max(dte, 1)
    atm_iv = sampled.get("iv")
    expected_move = (
        underlying_px * atm_iv * math.sqrt(dte / 365)
        if atm_iv is not None and dte > 0
        else None
    )

    with session_scope() as session:
        history = [
            r.atm_iv
            for r in session.exec(
                select(IVHistory)
                .where(IVHistory.symbol == symbol)
                .order_by(IVHistory.date)
            ).all()
        ]

    return SymbolMetrics(
        symbol=symbol,
        date=today,
        underlying_px=underlying_px,
        atm_iv=atm_iv,
        iv_rank=iv_rank(history, atm_iv) if atm_iv is not None else None,
        iv_percentile=iv_percentile(history, atm_iv) if atm_iv is not None else None,
        expected_move=expected_move,
        premium_yield=premium_yield,
        open_interest=sampled.get("openInterest"),
        spread_pct=spread_pct,
        sampled_delta=sampled.get("delta"),
        sampled_dte=dte,
        source=getattr(provider, "name", ""),
    )


async def watchlist_scan(provider, settings) -> None:
    today = datetime.now(timezone.utc).date()
    with session_scope() as session:
        symbols = [w.symbol for w in session.exec(select(WatchlistItem)).all()]
        already = {
            m.symbol
            for m in session.exec(
                select(SymbolMetrics).where(SymbolMetrics.date == today)
            ).all()
        }
    pending = [s for s in symbols if s not in already]
    batches = batch_plan(pending)

    for batch_index, batch in enumerate(batches):
        for symbol in batch:
            try:
                metrics = await _scan_symbol(provider, symbol, today)
            except ProviderError as exc:
                log.warning("watchlist_scan skipped for %s: %s", symbol, exc)
                continue
            if metrics is None:
                continue
            with session_scope() as session:
                session.add(metrics)
        if batch_index < len(batches) - 1:
            await asyncio.sleep(PACE_DELAY_SECONDS)
