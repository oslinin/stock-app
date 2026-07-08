from __future__ import annotations

import logging
from datetime import date, datetime, time

from ..alerts.dispatcher import dispatch
from ..ibkr.opening_hours import et_today, now_et

log = logging.getLogger(__name__)

IV_SNAPSHOT_TARGET_DTE = 30


def _pick_expiry(expiries: list[str], target_dte: int = IV_SNAPSHOT_TARGET_DTE) -> str:
    """Expiry (YYYY-MM-DD) closest to the target DTE — ATM IV is sampled at
    a consistent tenor so the iv_history series is comparable day to day."""
    today = date.today()

    def dte(expiry: str) -> int:
        return (datetime.strptime(expiry, "%Y-%m-%d").date() - today).days

    future = [e for e in expiries if dte(e) >= 0]
    if not future:
        raise ValueError("no future expiries")
    return min(future, key=lambda e: abs(dte(e) - target_dte))


async def iv_snapshot(providers, settings) -> None:
    """Nightly IV-history sync into the iv_history table (idempotent per
    symbol/day).

    Reuse-first: a provider with the iv_history capability (IBKR's IV
    index) supplies the whole daily ATM-IV series in one request — first
    run backfills ~a year, later runs top up missing days. Only when no
    such provider is available (gateway down, yfinance-only setup) does
    the job fall back to measuring today's ATM IV from a chain snapshot.
    """
    from ..dataproviders.base import IV_HISTORY, ProviderError

    for symbol in settings.iv_snapshot_symbol_list:
        try:
            try:
                provider = providers.route(IV_HISTORY)
            except ProviderError:
                provider = None
            if provider is not None:
                try:
                    added = await _sync_iv_history(provider, symbol)
                    log.info("iv_snapshot: %s +%d days from %s", symbol, added, provider.name)
                    continue
                except Exception as exc:  # noqa: BLE001 - fall back below
                    log.warning(
                        "iv_snapshot: %s via %s failed (%s), falling back to chain",
                        symbol,
                        provider.name,
                        exc,
                    )
            await _snapshot_from_chain(providers, symbol)
        except Exception as exc:  # noqa: BLE001 - jobs must never crash the loop
            log.warning("iv_snapshot skipped for %s: %s", symbol, exc)


async def _sync_iv_history(provider, symbol: str) -> int:
    """Upsert a provider's daily IV series; returns how many days were new."""
    from sqlmodel import select

    from ..dataproviders.models import IVHistory
    from ..db.session import session_scope

    series = await provider.iv_history(symbol)
    with session_scope() as session:
        have = set(
            session.exec(
                select(IVHistory.date).where(IVHistory.symbol == symbol)
            ).all()
        )
        added = 0
        for point in series:
            day = date.fromisoformat(point["date"])
            if day in have:
                continue
            session.add(
                IVHistory(
                    symbol=symbol,
                    date=day,
                    atm_iv=point["iv"],
                    underlying_px=point.get("underlying_px"),
                    source=f"{provider.name}_iv_index",
                )
            )
            added += 1
    return added


async def _snapshot_from_chain(providers, symbol: str) -> None:
    """Fallback: measure today's ATM IV from a current chain snapshot."""
    from sqlmodel import select

    from ..analytics.ivrank import atm_iv_from_chain
    from ..dataproviders.base import CHAIN, QUOTE
    from ..dataproviders.models import IVHistory
    from ..db.session import session_scope

    today = et_today()
    with session_scope() as session:
        exists = session.exec(
            select(IVHistory)
            .where(IVHistory.symbol == symbol)
            .where(IVHistory.date == today)
        ).first()
    if exists:
        return
    chain_provider = providers.route(CHAIN)
    spot = (await providers.route(QUOTE).quote(symbol))["price"]
    expiry = _pick_expiry(await chain_provider.expiries(symbol))
    rows = await chain_provider.chain(symbol, expiry)
    atm_iv = atm_iv_from_chain(rows, spot=spot)
    if atm_iv is None:
        log.warning("iv_snapshot: no usable ATM IV for %s (%s)", symbol, expiry)
        return
    with session_scope() as session:
        session.add(
            IVHistory(
                symbol=symbol,
                date=today,
                atm_iv=atm_iv,
                underlying_px=spot,
                source=chain_provider.name,
            )
        )
    log.info("iv_snapshot: %s atm_iv=%.4f (%s, spot %.2f)", symbol, atm_iv, expiry, spot)


async def eod_arming_scan(engine, settings) -> None:
    """After the close: refresh state; if a bottom signal armed today, alert."""
    for strategy in engine.registry.values():
        try:
            st = await engine.market_state(strategy, force=True)
        except Exception as exc:  # noqa: BLE001 - jobs must never crash the loop
            log.warning("eod scan skipped for %s: %s", strategy.id, exc)
            continue
        if st.armed and st.armed_date == st.signal_date == str(et_today()):
            summary = (
                f"{strategy.name}: MACD bottom signal detected at today's close.\n"
                f"{st.bottom_detail}\n"
                f"Confirming close: {st.confirming_close}\n"
                "The trade is ARMED for the next session; entry fires only if VIX "
                "trades above the prior close, the confirming close, and the "
                "opening-range high."
            )
            await dispatch(settings, strategy.id, "ARMED", str(et_today()), "", summary)


async def intraday_confirmation_poll(engine, settings) -> None:
    """During RTH while armed: poll for the ENTER transition and alert once."""
    if now_et().time() < time(9, 35):
        return
    for strategy in engine.registry.values():
        try:
            st = await engine.market_state(strategy, force=True)
            if not st.armed:
                continue
            verdict = await engine.verdict(strategy)
            if verdict["verdict"] != "ENTER":
                continue
            spread, _ = await engine.spread(strategy)
            if spread.get("found"):
                legs = ", ".join(
                    f"{leg['action']} {leg['strike']:g}{leg['right']}"
                    for leg in spread["legs"]
                )
                trade = (
                    f"Best combo ({spread['expiry']}, {spread['dte']} DTE): {legs}. "
                    f"Net {spread['net']['perComboUsd']:+.0f} USD per combo, "
                    f"max loss {spread['maxLossUsd']:.0f}, max gain {spread['maxGainUsd']:.0f}."
                )
                expiry = spread.get("expiryRaw", "")
            else:
                trade = f"No qualifying spread under the cap right now: {spread.get('reason')}"
                expiry = ""
            summary = (
                f"{strategy.name}: ENTER — all confirmation conditions met.\n"
                f"VIX {st.spot}, prior close {st.prior_close}, "
                f"confirming close {st.confirming_close}, "
                f"OR high {st.opening.high if st.opening else None}.\n{trade}"
            )
            await dispatch(settings, strategy.id, "ENTER", str(et_today()), expiry, summary)
        except Exception as exc:  # noqa: BLE001
            log.warning("intraday poll skipped for %s: %s", strategy.id, exc)
