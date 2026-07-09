from __future__ import annotations

import logging
from datetime import date, time

from ..alerts.dispatcher import dispatch
from ..ibkr.opening_hours import et_today, now_et

log = logging.getLogger(__name__)


async def iv_snapshot(providers, settings) -> None:
    """Nightly IV-history sync into the iv_history table (idempotent per
    symbol/day).

    Reuse-first: a provider with the iv_history capability (IBKR's IV
    index) supplies the whole daily ATM-IV series in one request — first
    run backfills ~a year, later runs top up missing days. No provider
    (gateway down) means no rows tonight; the next successful sync
    backfills the gap.
    """
    from ..dataproviders.base import IV_HISTORY, ProviderError

    try:
        provider = providers.route(IV_HISTORY)
    except ProviderError:
        log.warning("iv_snapshot: no iv_history-capable provider registered, skipping")
        return
    for symbol in settings.iv_snapshot_symbol_list:
        try:
            added = await _sync_iv_history(provider, symbol)
            log.info("iv_snapshot: %s +%d days from %s", symbol, added, provider.name)
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


async def watchlist_scan_job(providers, settings) -> None:
    """Nightly symbol_metrics sweep over the watchlist. Reuse-first: any
    provider with a priced chain (yfinance by default) can sample it —
    same graceful-degradation discipline as iv_snapshot: a provider
    error skips the symbol, never crashes the job."""
    from ..dataproviders.base import CHAIN, ProviderError
    from ..watchlist.scan_job import watchlist_scan

    try:
        provider = providers.route(CHAIN)
    except ProviderError:
        log.warning("watchlist_scan: no chain-capable provider registered, skipping")
        return
    await watchlist_scan(provider, settings)


async def beta_refresh(providers, settings) -> None:
    """Weekly beta refresh: 1y daily OLS beta vs SPY for every watchlist
    symbol (same universe watchlist_scan already covers) — stored in
    beta_cache for /portfolio/beta and /portfolio/summary's beta-weighted
    delta. Same graceful-degradation discipline as the other jobs: a
    provider error skips a symbol, never crashes the run."""
    from sqlmodel import select

    from ..dataproviders.base import BARS, ProviderError
    from ..db.session import session_scope
    from ..portfolio.beta import compute_beta
    from ..portfolio.models import BetaCache, utcnow
    from ..portfolio.risk import daily_returns
    from ..watchlist.models import WatchlistItem

    try:
        provider = providers.route(BARS)
    except ProviderError:
        log.warning("beta_refresh: no bars-capable provider registered, skipping")
        return

    try:
        benchmark_bars = await provider.bars("SPY", period="1y", interval="1d")
    except ProviderError as exc:
        log.warning("beta_refresh: could not load SPY benchmark bars: %s", exc)
        return
    benchmark_returns = daily_returns([b["close"] for b in benchmark_bars])

    with session_scope() as session:
        symbols = [w.symbol for w in session.exec(select(WatchlistItem)).all()]

    for symbol in symbols:
        try:
            bars = await provider.bars(symbol, period="1y", interval="1d")
        except ProviderError as exc:
            log.warning("beta_refresh skipped for %s: %s", symbol, exc)
            continue
        returns = daily_returns([b["close"] for b in bars])
        n = min(len(returns), len(benchmark_returns))
        result = compute_beta(returns[-n:], benchmark_returns[-n:]) if n >= 2 else None
        if result is None:
            log.warning("beta_refresh: beta undefined for %s (insufficient/flat data)", symbol)
            continue
        beta, r2 = result
        with session_scope() as session:
            existing = session.exec(select(BetaCache).where(BetaCache.symbol == symbol)).first()
            if existing:
                existing.beta, existing.r2, existing.window_days = beta, r2, n
                existing.computed_at = utcnow()
                session.add(existing)
            else:
                session.add(BetaCache(symbol=symbol, beta=beta, r2=r2, window_days=n))


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
