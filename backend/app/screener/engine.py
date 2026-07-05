from __future__ import annotations

import logging
import time as time_mod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlmodel import select

from ..alerts.models import ArmedState
from ..config import Settings
from ..db.session import session_scope
from ..ibkr import contracts, marketdata
from ..ibkr.client import IBClient
from ..ibkr.errors import DataUnavailable
from ..ibkr.opening_hours import et_today, session_open
from ..ibkr.orders import OrderLeg
from ..indicators.macd import last_defined, macd
from ..indicators.opening_range import OpeningRange, opening_range
from ..indicators.signals import bottom_signal, confirmation_checks, derive_verdict
from ..strategies.spread_math import breakevens, max_profile, payoff_points
from ..strategies.vix_hedge import (
    MULTIPLIER,
    VixHedgeParams,
    VixHedgeStrategy,
    select_spread,
)

log = logging.getLogger(__name__)

STATE_CACHE_SECONDS = 10


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MarketState:
    spot: float | None = None
    prior_close: float | None = None
    confirming_close: float | None = None
    opening: OpeningRange | None = None
    macd_line: float | None = None
    macd_signal: float | None = None
    hist: float | None = None
    hist_prev: float | None = None
    bottom_fired: bool = False
    bottom_detail: str = ""
    signal_date: str = ""
    armed: bool = False
    armed_date: str = ""
    session_open: bool = False
    closes: list[float] = field(default_factory=list)


@dataclass
class OrderContext:
    legs: list[OrderLeg]
    net_per_share: float
    contracts: int
    expiry: str


class ScreenerEngine:
    def __init__(self, client: IBClient, registry: dict, settings: Settings):
        self.client = client
        self.registry = registry
        self.settings = settings
        self._cache: dict[str, tuple[float, MarketState]] = {}

    # ---------- market state ----------

    async def market_state(self, strategy: VixHedgeStrategy, force: bool = False) -> MarketState:
        cached = self._cache.get(strategy.id)
        if cached and not force and time_mod.monotonic() - cached[0] < STATE_CACHE_SECONDS:
            return cached[1]

        p = strategy.params
        under = await contracts.vix_index(self.client)
        daily = await marketdata.daily_closes(self.client, under)
        closes = [c for _, c in daily]
        macd_out = macd(closes, p.macd_fast, p.macd_slow, p.macd_signal)
        bottom = bottom_signal(
            macd_out, closes, p.low_quantile, p.low_lookback_days, p.abs_low
        )
        signal_date = str(daily[-1][0]) if daily else ""

        st = MarketState(
            prior_close=closes[-1] if closes else None,
            closes=closes,
            bottom_fired=bottom.fired,
            bottom_detail=bottom.detail,
            signal_date=signal_date,
            session_open=session_open(),
        )
        line2 = last_defined(macd_out["line"], 1)
        sig2 = last_defined(macd_out["signal"], 1)
        hist2 = last_defined(macd_out["hist"], 2)
        st.macd_line = line2[-1] if line2 else None
        st.macd_signal = sig2[-1] if sig2 else None
        if hist2:
            st.hist = hist2[-1]
            st.hist_prev = hist2[-2] if len(hist2) > 1 else None

        # persist / read arming state so the confirming-day close survives
        with session_scope() as session:
            row = session.exec(
                select(ArmedState)
                .where(ArmedState.strategy_id == strategy.id)
                .order_by(ArmedState.id.desc())  # type: ignore[union-attr]
            ).first()
            if bottom.fired and (row is None or row.armed_date != signal_date):
                row = ArmedState(
                    strategy_id=strategy.id,
                    armed_date=signal_date,
                    confirming_close=closes[-1],
                    signal_detail=bottom.detail,
                )
                session.add(row)
            if row is not None:
                age = (et_today() - date.fromisoformat(row.armed_date)).days
                if age <= p.armed_ttl_days:
                    st.armed = True
                    st.armed_date = row.armed_date
                    st.confirming_close = row.confirming_close

        st.spot = await marketdata.snapshot_price(self.client, under)
        bars = await marketdata.intraday_bars(self.client, under)
        st.opening = opening_range(bars, p.or_minutes)

        self._cache[strategy.id] = (time_mod.monotonic(), st)
        return st

    def state_payload(self, strategy: VixHedgeStrategy, st: MarketState) -> dict:
        opening = st.opening or OpeningRange(None, None, False, strategy.params.or_minutes)
        return {
            "strategyId": strategy.id,
            "underlying": strategy.underlying_symbol,
            "spot": st.spot,
            "priorClose": st.prior_close,
            "confirmingClose": st.confirming_close,
            "openingRange": {
                "windowMin": opening.window_min,
                "high": opening.high,
                "low": opening.low,
                "complete": opening.complete,
            },
            "macd": {
                "line": st.macd_line,
                "signal": st.macd_signal,
                "hist": st.hist,
                "histPrev": st.hist_prev,
                "bottomSignal": st.bottom_fired,
                "detail": st.bottom_detail,
                "asOfClose": st.signal_date,
            },
            "armed": st.armed,
            "armedAsOf": st.armed_date,
            "sessionOpen": st.session_open,
            "marketDataType": self.client.market_data_type,
            "asOf": _now_iso(),
        }

    # ---------- verdict ----------

    async def verdict(self, strategy: VixHedgeStrategy) -> dict:
        st = await self.market_state(strategy)
        p = strategy.params
        opening = st.opening or OpeningRange(None, None, False, p.or_minutes)
        checks = confirmation_checks(
            st.spot,
            st.prior_close,
            st.confirming_close,
            opening.high,
            opening.complete,
            st.armed,
            p.or_minutes,
        )
        has_data = st.spot is not None and bool(st.closes)
        verdict = derive_verdict(has_data, st.session_open, st.armed, checks)
        reasons = {
            "NO_DATA": "market data unavailable",
            "WAIT": "no MACD bottom signal on the daily VIX",
            "ARMED": "armed; awaiting intraday confirmation",
            "ENTER": "all entry conditions met",
        }
        return {
            "strategyId": strategy.id,
            "verdict": verdict,
            "armed": st.armed,
            "armedAsOf": st.armed_date,
            "checks": [
                {"key": c.key, "label": c.label, "pass": c.passed, "detail": c.detail}
                for c in checks
            ],
            "reason": reasons[verdict],
            "asOf": _now_iso(),
        }

    # ---------- spread construction ----------

    async def spread(
        self,
        strategy: VixHedgeStrategy,
        expiry: str | None = None,
        width: float | None = None,
        contracts_count: int = 1,
    ) -> tuple[dict, OrderContext | None]:
        p = strategy.params
        params = VixHedgeParams(**{**p.__dict__})
        if width:
            params.width = width

        expirations, all_strikes = await contracts.vix_option_params(self.client)
        warnings: list[str] = []
        dte = None
        if expiry:
            if expiry not in expirations:
                raise DataUnavailable(f"expiry {expiry} is not a listed monthly VIX expiration")
            exp_date = datetime.strptime(expiry, "%Y%m%d").date()
            dte = (exp_date - et_today()).days
        else:
            picked = contracts.pick_expiry(expirations, params.dte_min, params.dte_max, et_today())
            if picked is None:
                return (
                    {
                        "strategyId": strategy.id,
                        "found": False,
                        "reason": f"no monthly VIX expiry inside {params.dte_min}-{params.dte_max} DTE",
                        "asOf": _now_iso(),
                    },
                    None,
                )
            expiry, dte = picked

        under = await contracts.vix_index(self.client)
        spot = await marketdata.snapshot_price(self.client, under)

        center = None
        center_source = "future"
        fut = await contracts.vix_future_for_expiry(self.client, expiry)
        if fut is not None:
            center = await marketdata.snapshot_price(self.client, fut)
        if center is None:
            center = spot
            center_source = "spot"
            warnings.append(
                "VIX future price unavailable; centering strikes on spot VIX instead"
            )
        if center is None:
            raise DataUnavailable("no VIX price available to center the strike search")

        lo = center - params.strike_window_below
        hi = center + params.strike_window_above
        strikes = [k for k in all_strikes if lo <= k <= hi]
        if not strikes:
            raise DataUnavailable("no listed strikes inside the search window")

        rows = await marketdata.option_chain_quotes(self.client, expiry, strikes)
        sel = select_spread(rows, center, params)

        if self.settings.ibkr_use_delayed:
            warnings.append("quotes are delayed market data")

        expiry_iso = f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:]}"
        base = {
            "strategyId": strategy.id,
            "underlying": strategy.underlying_symbol,
            "expiry": expiry_iso,
            "expiryRaw": expiry,
            "dte": dte,
            "spot": spot,
            "center": round(center, 4),
            "centerSource": center_source,
            "contracts": contracts_count,
            "multiplier": MULTIPLIER,
            "width": params.width,
            "netDebitCapUsd": params.net_debit_cap_usd,
            "candidatesChecked": sel.candidates_checked,
            "asOf": _now_iso(),
        }

        if not sel.found:
            payload = {
                **base,
                "found": False,
                "reason": sel.reason,
                "warnings": warnings,
                "closest": self._combo_payload(sel.best, rows, params, contracts_count)
                if sel.best
                else None,
            }
            return payload, None

        best = sel.best
        combo = self._combo_payload(best, rows, params, contracts_count)
        payload = {
            **base,
            "found": True,
            "reason": "ok",
            **combo,
            "alternatives": [
                {
                    "callSpread": f"{alt.call_long:g}/{alt.call_short:g}",
                    "putSpread": f"{alt.put_long:g}/{alt.put_short:g}",
                    "netUsd": round(alt.net_usd, 2),
                }
                for alt in sel.alternatives
            ],
            "warnings": warnings + best.warnings,
        }

        by_strike = {r.strike: r for r in rows}
        order = OrderContext(
            legs=[
                OrderLeg(by_strike[best.call_long].call.con_id, "BUY", f"{best.call_long:g}C"),
                OrderLeg(by_strike[best.call_short].call.con_id, "SELL", f"{best.call_short:g}C"),
                OrderLeg(by_strike[best.put_short].put.con_id, "SELL", f"{best.put_short:g}P"),
                OrderLeg(by_strike[best.put_long].put.con_id, "BUY", f"{best.put_long:g}P"),
            ],
            net_per_share=best.net,
            contracts=contracts_count,
            expiry=expiry,
        )
        return payload, order

    def _combo_payload(self, combo, rows, params: VixHedgeParams, contracts_count: int) -> dict:
        by_strike = {r.strike: r for r in rows}

        def leg(leg_id: str, action: str, right: str, strike: float) -> dict:
            quote = by_strike[strike].call if right == "C" else by_strike[strike].put
            return {
                "id": leg_id,
                "action": action,
                "right": right,
                "strike": strike,
                "qty": contracts_count,
                "bid": quote.bid,
                "ask": quote.ask,
                "mid": quote.mid,
            }

        legs = [
            leg("long_call", "BUY", "C", combo.call_long),
            leg("short_call", "SELL", "C", combo.call_short),
            leg("short_put", "SELL", "P", combo.put_short),
            leg("long_put", "BUY", "P", combo.put_long),
        ]
        points = payoff_points(
            combo.legs(), combo.net, MULTIPLIER, contracts_count, pad=5.0
        )
        max_loss, max_gain = max_profile(points)
        w = params.width
        return {
            "legs": legs,
            "callSpread": {
                "width": w,
                "debit": combo.call_debit,
                "maxLossUsd": round(combo.call_debit * MULTIPLIER * contracts_count, 2),
                "maxGainUsd": round((w - combo.call_debit) * MULTIPLIER * contracts_count, 2),
            },
            "putSpread": {
                "width": w,
                "credit": combo.put_credit,
                "maxGainUsd": round(combo.put_credit * MULTIPLIER * contracts_count, 2),
                "maxLossUsd": round((w - combo.put_credit) * MULTIPLIER * contracts_count, 2),
            },
            "net": {
                "perSharePts": round(combo.net, 4),
                "perComboUsd": round(combo.net_usd, 2),
                "totalUsd": round(combo.net_usd * contracts_count, 2),
                "isDebit": combo.net > 0,
            },
            "maxLossUsd": max_loss,
            "maxGainUsd": max_gain,
            "breakevens": breakevens(points),
            "payoff": points,
        }
