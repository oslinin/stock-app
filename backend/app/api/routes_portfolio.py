"""/portfolio — IBKR live positions + Fidelity CSV snapshots, merged;
aggregate greeks + beta-weighted delta; forward-looking CVaR.

IBKR positions are fetched live every call and also persisted as a
position_snapshot row (broker_account keyed by IB account number) for a
provenance trail; Fidelity positions are snapshotted only on upload (no
live feed) — the plan's "IBKR live ... Fidelity via versioned CSV
upload" distinction, reflected in how each source reaches this table.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from sqlmodel import select

from ..dataproviders.base import BARS, CHAIN, QUOTE, ProviderError
from ..db.session import session_scope
from ..portfolio import aggregate, ibkr_positions, risk
from ..portfolio.fidelity_csv import parse_fidelity_csv
from ..portfolio.models import BetaCache, BrokerAccount, FidelityImport, PositionSnapshot
from ..security import require_token

router = APIRouter(prefix="/portfolio", dependencies=[Depends(require_token)])


def _get_or_create_account(session, broker: str, label: str) -> BrokerAccount:
    existing = session.exec(
        select(BrokerAccount).where(BrokerAccount.broker == broker, BrokerAccount.label == label)
    ).first()
    if existing:
        return existing
    account = BrokerAccount(broker=broker, label=label)
    session.add(account)
    session.flush()
    return account


def _snapshot(session, account: BrokerAccount, source: str, positions: list[dict]) -> PositionSnapshot:
    snap = PositionSnapshot(account_id=account.id, source=source, positions_json=json.dumps(positions))
    session.add(snap)
    session.flush()
    return snap


def _live_ibkr_positions(request: Request) -> list[dict]:
    positions = ibkr_positions.fetch_positions(request.app.state.ib)
    if not positions:
        return positions
    by_account: dict[str, list[dict]] = {}
    for p in positions:
        by_account.setdefault(p["accountNumber"] or "default", []).append(p)
    with session_scope() as session:
        for label, rows in by_account.items():
            account = _get_or_create_account(session, "ibkr", label)
            _snapshot(session, account, "ibkr_live", rows)
    return positions


def _latest_fidelity_positions() -> list[dict]:
    with session_scope() as session:
        accounts = session.exec(select(BrokerAccount).where(BrokerAccount.broker == "fidelity")).all()
        out: list[dict] = []
        for account in accounts:
            snap = session.exec(
                select(PositionSnapshot)
                .where(PositionSnapshot.account_id == account.id)
                .order_by(PositionSnapshot.asof.desc())
            ).first()
            if snap:
                out.extend(json.loads(snap.positions_json))
        return out


def _all_positions(request: Request) -> list[dict]:
    return _live_ibkr_positions(request) + _latest_fidelity_positions()


async def _quotes_concurrently(providers, symbols: set[str]) -> dict[str, float]:
    """One quote per unique symbol, fetched concurrently — sequential
    awaits here would add each provider's full round trip per symbol."""

    async def one(symbol: str) -> tuple[str, float | None]:
        try:
            return symbol, (await providers.route(QUOTE).quote(symbol))["price"]
        except ProviderError:
            return symbol, None

    results = await asyncio.gather(*(one(s) for s in symbols))
    return {symbol: price for symbol, price in results if price is not None}


@router.get("/positions")
def list_positions(request: Request, group_by: str | None = None) -> dict:
    all_positions = _all_positions(request)
    if group_by:
        try:
            return {"groups": aggregate.group_positions(all_positions, group_by)}
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    return {"positions": all_positions}


@router.get("/summary")
async def portfolio_summary(request: Request) -> dict:
    providers = request.app.state.providers
    all_positions = _all_positions(request)

    with session_scope() as session:
        betas = {b.symbol: b.beta for b in session.exec(select(BetaCache)).all()}

    symbols = {p["symbol"] for p in all_positions} | {"SPY"}
    underlying_prices = await _quotes_concurrently(providers, symbols)
    benchmark_price = underlying_prices.get("SPY")

    enriched = [
        aggregate.enrich_position(p, betas, underlying_prices, benchmark_price)
        for p in all_positions
    ]

    with session_scope() as session:
        ibkr_labels = [
            a.label for a in session.exec(select(BrokerAccount).where(BrokerAccount.broker == "ibkr")).all()
        ]
        fidelity_labels = [
            a.label
            for a in session.exec(select(BrokerAccount).where(BrokerAccount.broker == "fidelity")).all()
        ]

    account_summary = ibkr_positions.fetch_account_summary(request.app.state.ib)
    accounts = [
        {
            "broker": "ibkr",
            "label": label,
            "netLiquidation": account_summary.get(label, {}).get("NetLiquidation"),
            "buyingPower": account_summary.get(label, {}).get("BuyingPower"),
        }
        for label in ibkr_labels
    ] + [
        {"broker": "fidelity", "label": label, "netLiquidation": None, "buyingPower": "unavailable from source"}
        for label in fidelity_labels
    ]

    return {"summary": aggregate.summarize(enriched), "accounts": accounts, "positions": enriched}


async def _enrich_for_risk(request: Request, positions: list[dict]) -> tuple[list[dict], list[dict]]:
    """Attach spot/iv/tYears needed to reprice each position. A position
    that can't be priced (no quote, no matching chain row) is excluded
    and listed with a reason — plan: "non-priceable positions excluded
    and listed" — rather than silently dropped."""
    providers = request.app.state.providers
    ready: list[dict] = []
    excluded: list[dict] = []

    quote_cache = await _quotes_concurrently(providers, {p["symbol"] for p in positions})

    async def chain_for(symbol: str, expiry: str) -> list[dict]:
        try:
            return await providers.route(CHAIN).chain(symbol, expiry)
        except ProviderError:
            return []

    chain_keys = {
        (p["symbol"], p["expiry"])
        for p in positions
        if p["secType"] != "STK" and p.get("expiry") and p.get("strike") and p.get("right")
    }
    chain_results = await asyncio.gather(*(chain_for(s, e) for s, e in chain_keys))
    chain_cache = dict(zip(chain_keys, chain_results))

    for p in positions:
        spot = quote_cache.get(p["symbol"])
        if spot is None:
            excluded.append({**p, "reason": f"no quote available for {p['symbol']}"})
            continue
        if p["secType"] == "STK":
            ready.append({**p, "spot": spot})
            continue
        if not p.get("expiry") or not p.get("strike") or not p.get("right"):
            excluded.append({**p, "reason": "incomplete option contract"})
            continue
        key = (p["symbol"], p["expiry"])
        row = next(
            (r for r in chain_cache[key] if r["strike"] == p["strike"] and r["right"] == p["right"]),
            None,
        )
        if row is None or row.get("iv") is None:
            excluded.append({**p, "reason": "no chain quote for this contract"})
            continue
        t_years = max((date.fromisoformat(p["expiry"]) - date.today()).days, 1) / 365.0
        ready.append({**p, "spot": spot, "iv": row["iv"], "tYears": t_years})
    return ready, excluded


@router.get("/risk")
async def portfolio_risk(request: Request, lookback_days: int = 500) -> dict:
    """Forward-looking 1-day CVaR (95%/99%) via historical simulation —
    the realized equity-curve half arrives with journal analytics (not
    built yet), per the plan."""
    providers = request.app.state.providers
    r = request.app.state.settings.analytics_risk_free_rate
    all_positions = _all_positions(request)
    ready, excluded = await _enrich_for_risk(request, all_positions)

    async def scenarios_for(symbol: str) -> tuple[str, list[float]]:
        try:
            bars = await providers.route(BARS).bars(symbol, period="2y", interval="1d")
            return symbol, risk.daily_returns([b["close"] for b in bars])
        except ProviderError:
            return symbol, []

    unique_symbols = {p["symbol"] for p in ready}
    scenario_results = await asyncio.gather(*(scenarios_for(s) for s in unique_symbols))
    scenarios_by_symbol = dict(scenario_results)

    priceable_idx = {i for i, p in enumerate(ready) if len(scenarios_by_symbol.get(p["symbol"], [])) >= 2}
    priceable = [ready[i] for i in priceable_idx]
    excluded += [
        {**p, "reason": "insufficient price history for scenarios"}
        for i, p in enumerate(ready)
        if i not in priceable_idx
    ]

    if not priceable:
        return {"cvar95": None, "cvar99": None, "scenarios": 0, "priced": 0, "excluded": excluded}

    n = min(min(len(scenarios_by_symbol[p["symbol"]]) for p in priceable), lookback_days)
    pnls = [0.0] * n
    for p in priceable:
        aligned = scenarios_by_symbol[p["symbol"]][-n:]
        for i, ret in enumerate(aligned):
            pnls[i] += risk.reprice_pnl(p, ret, r)

    return {
        "cvar95": risk.cvar(pnls, confidence=0.95),
        "cvar99": risk.cvar(pnls, confidence=0.99),
        "scenarios": n,
        "priced": len(priceable),
        "excluded": excluded,
    }


@router.post("/fidelity/upload", status_code=201)
async def upload_fidelity_csv(file: UploadFile, account_label: str = Form("default")) -> dict:
    text = (await file.read()).decode("utf-8", errors="replace")
    positions = parse_fidelity_csv(text)
    with session_scope() as session:
        account = _get_or_create_account(session, "fidelity", account_label)
        snap = _snapshot(session, account, "fidelity_csv", positions)
        session.add(
            FidelityImport(filename=file.filename or "", parsed_count=len(positions), snapshot_id=snap.id)
        )
    return {"parsedCount": len(positions), "accountLabel": account_label}


@router.get("/beta")
def get_beta(symbol: str) -> dict:
    symbol = symbol.upper()
    with session_scope() as session:
        row = session.exec(select(BetaCache).where(BetaCache.symbol == symbol)).first()
    if row is None:
        raise HTTPException(
            404,
            f"no cached beta for '{symbol}' yet — the weekly beta_refresh job pulls "
            "it from IB Gateway's fundamental-ratios feed for watchlist symbols "
            "(needs the gateway up and a Reuters Fundamentals entitlement)",
        )
    return {
        "symbol": row.symbol,
        "beta": row.beta,
        "source": row.source,
        "computedAt": row.computed_at.isoformat(),
    }
