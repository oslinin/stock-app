from __future__ import annotations

import logging
from datetime import time

from ..alerts.dispatcher import dispatch
from ..ibkr.opening_hours import et_today, now_et

log = logging.getLogger(__name__)


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
