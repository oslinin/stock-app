from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from ..db.session import session_scope
from ..security import require_token
from ..watchlist.models import SymbolMetrics, WatchlistItem
from ..watchlist.screeners import SCREENER_REGISTRY, run_screener

router = APIRouter(prefix="/watchlist", dependencies=[Depends(require_token)])


class WatchlistItemIn(BaseModel):
    symbol: str
    tags: str = ""


def _item_out(item: WatchlistItem) -> dict:
    return {
        "id": item.id,
        "symbol": item.symbol,
        "tags": [t for t in item.tags.split(",") if t],
        "createdAt": item.created_at.isoformat(),
    }


@router.get("")
def list_watchlist() -> list[dict]:
    with session_scope() as session:
        items = session.exec(select(WatchlistItem).order_by(WatchlistItem.symbol)).all()
        return [_item_out(i) for i in items]


@router.post("", status_code=201)
def add_symbol(body: WatchlistItemIn) -> dict:
    symbol = body.symbol.strip().upper()
    if not symbol:
        raise HTTPException(422, "symbol is required")
    with session_scope() as session:
        existing = session.exec(
            select(WatchlistItem).where(WatchlistItem.symbol == symbol)
        ).first()
        if existing is not None:
            return _item_out(existing)
        item = WatchlistItem(symbol=symbol, tags=body.tags)
        session.add(item)
        session.flush()
        return _item_out(item)


@router.delete("/{symbol}", status_code=204)
def remove_symbol(symbol: str) -> None:
    with session_scope() as session:
        item = session.exec(
            select(WatchlistItem).where(WatchlistItem.symbol == symbol.upper())
        ).first()
        if item is None:
            raise HTTPException(404, "symbol not on watchlist")
        session.delete(item)


def _metrics_out(row: SymbolMetrics) -> dict:
    return {
        "symbol": row.symbol,
        "date": row.date.isoformat(),
        "underlying_px": row.underlying_px,
        "atm_iv": row.atm_iv,
        "iv_rank": row.iv_rank,
        "iv_percentile": row.iv_percentile,
        "expected_move": row.expected_move,
        "premium_yield": row.premium_yield,
        "open_interest": row.open_interest,
        "spread_pct": row.spread_pct,
        "sampled_delta": row.sampled_delta,
        "sampled_dte": row.sampled_dte,
        "source": row.source,
    }


def _latest_metrics_by_symbol() -> dict[str, dict]:
    """Screeners rank whatever the most recent scan wrote per symbol —
    not strictly "today" (weekends/holidays/a missed run shouldn't blank
    the screener out). Dicts are built while the session is still open;
    SymbolMetrics rows can't be read after session_scope() closes."""
    with session_scope() as session:
        rows = session.exec(select(SymbolMetrics).order_by(SymbolMetrics.date)).all()
        latest: dict[str, dict] = {}
        for row in rows:
            latest[row.symbol] = _metrics_out(row)
        return latest


@router.get("/screeners")
def list_screeners() -> list[dict]:
    return [
        {"id": s.id, "name": s.name, "description": s.description}
        for s in SCREENER_REGISTRY.values()
    ]


@router.post("/screeners/{screener_id}/run")
def run_screener_route(screener_id: str, params: dict | None = None) -> list[dict]:
    if screener_id not in SCREENER_REGISTRY:
        raise HTTPException(404, f"unknown screener {screener_id!r}")
    rows = list(_latest_metrics_by_symbol().values())
    return run_screener(screener_id, rows, params or {})
