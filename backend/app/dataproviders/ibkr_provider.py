"""IBKR-backed provider: wraps the existing IBClient (never modifies it).

Latency is whatever the gateway session is configured for (delayed by
default, live with subscriptions) — reported honestly in provenance.
Chains reuse the chunked-ticker pattern from app.ibkr.marketdata.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime

from ..ibkr.client import IBClient
from ..ibkr.contracts import IB_TIMEOUT
from ..ibkr.ib_lib import Option, Stock
from ..ibkr.marketdata import price_of
from .base import BARS, CHAIN, EXPIRIES, IV_HISTORY, QUOTE, ProviderError

TICKER_CHUNK = 40
MAX_CHAIN_CONTRACTS = 160  # strikes around spot; respects pacing limits


def _clean(value, minimum=0.0) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or v <= minimum:
        return None
    return v


class IBKRProvider:
    name = "ibkr"
    capabilities = frozenset({QUOTE, BARS, CHAIN, EXPIRIES, IV_HISTORY})

    def __init__(self, client: IBClient):
        self.client = client

    @property
    def latency(self) -> str:
        return "delayed" if self.client.settings.ibkr_use_delayed else "live"

    async def _stock(self, symbol: str):
        ib = self.client.require()
        contract = Stock(symbol.upper(), "SMART", "USD")
        qualified = await asyncio.wait_for(
            ib.qualifyContractsAsync(contract), IB_TIMEOUT
        )
        if not qualified or not getattr(qualified[0], "conId", 0):
            raise ProviderError(f"IBKR could not qualify stock '{symbol}'")
        return qualified[0]

    # ------------------------------------------------------------- quote

    async def quote(self, symbol: str) -> dict:
        ib = self.client.require()
        contract = await self._stock(symbol)
        tickers = await asyncio.wait_for(ib.reqTickersAsync(contract), IB_TIMEOUT)
        price = price_of(tickers[0]) if tickers else None
        if price is None:
            raise ProviderError(f"IBKR returned no price for '{symbol}'")
        t = tickers[0]
        return {
            "symbol": symbol.upper(),
            "price": price,
            "bid": _clean(t.bid),
            "ask": _clean(t.ask),
            "previousClose": _clean(t.close),
            "currency": "USD",
        }

    # -------------------------------------------------------------- bars

    async def bars(self, symbol: str, period: str = "6mo", interval: str = "1d") -> list[dict]:
        ib = self.client.require()
        contract = await self._stock(symbol)
        duration = {"1mo": "1 M", "3mo": "3 M", "6mo": "6 M", "1y": "1 Y", "2y": "2 Y"}.get(
            period, "6 M"
        )
        bar_size = {"1d": "1 day", "1h": "1 hour", "5m": "5 mins"}.get(interval, "1 day")
        bars = await asyncio.wait_for(
            ib.reqHistoricalDataAsync(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow="TRADES",
                useRTH=True,
                formatDate=2,
            ),
            IB_TIMEOUT,
        )
        if not bars:
            raise ProviderError(f"IBKR returned no bars for '{symbol}'")
        return [
            {
                "time": b.date.isoformat(),
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(b.volume),
            }
            for b in bars
        ]

    # ------------------------------------------------------------- chain

    async def expiries(self, symbol: str) -> list[str]:
        ib = self.client.require()
        under = await self._stock(symbol)
        param_sets = await asyncio.wait_for(
            ib.reqSecDefOptParamsAsync(under.symbol, "", under.secType, under.conId),
            IB_TIMEOUT,
        )
        expirations: set[str] = set()
        for p in param_sets:
            if p.exchange == "SMART":
                expirations.update(p.expirations)
        if not expirations:
            raise ProviderError(f"IBKR lists no option expiries for '{symbol}'")
        # normalize YYYYMMDD -> YYYY-MM-DD to match the yfinance provider
        return sorted(
            datetime.strptime(e, "%Y%m%d").date().isoformat() for e in expirations
        )

    async def chain(self, symbol: str, expiry: str) -> list[dict]:
        ib = self.client.require()
        under = await self._stock(symbol)
        tickers = await asyncio.wait_for(ib.reqTickersAsync(under), IB_TIMEOUT)
        spot = price_of(tickers[0]) if tickers else None

        param_sets = await asyncio.wait_for(
            ib.reqSecDefOptParamsAsync(under.symbol, "", under.secType, under.conId),
            IB_TIMEOUT,
        )
        ib_expiry = expiry.replace("-", "")
        strikes: set[float] = set()
        for p in param_sets:
            if p.exchange == "SMART" and ib_expiry in p.expirations:
                strikes.update(p.strikes)
        if not strikes:
            raise ProviderError(f"IBKR has no strikes for '{symbol}' {expiry}")

        picked = sorted(strikes, key=lambda k: abs(k - spot) if spot else k)
        picked = sorted(picked[: MAX_CHAIN_CONTRACTS // 2])

        contracts = []
        for strike in picked:
            for right in ("C", "P"):
                contracts.append(
                    (right, strike, Option(under.symbol, ib_expiry, strike, right, "SMART"))
                )
        qualified = await asyncio.wait_for(
            ib.qualifyContractsAsync(*[c for _, _, c in contracts]), IB_TIMEOUT
        )
        live = [
            (r, k, c)
            for (r, k, c), _ in zip(contracts, qualified)
            if getattr(c, "conId", 0)
        ]
        if not live:
            raise ProviderError(f"no option contracts qualified for '{symbol}' {expiry}")

        rows: list[dict] = []
        for i in range(0, len(live), TICKER_CHUNK):
            chunk = live[i : i + TICKER_CHUNK]
            chunk_tickers = await asyncio.wait_for(
                ib.reqTickersAsync(*[c for _, _, c in chunk]), IB_TIMEOUT
            )
            for (right, strike, _), t in zip(chunk, chunk_tickers):
                greeks = t.modelGreeks
                rows.append(
                    {
                        "expiry": expiry,
                        "strike": float(strike),
                        "right": right,
                        "bid": _clean(t.bid, minimum=-1e-9),
                        "ask": _clean(t.ask),
                        "last": _clean(t.last),
                        "volume": _clean(t.volume, minimum=-1e-9),
                        "openInterest": None,  # not in snapshot tickers
                        "iv": _clean(getattr(greeks, "impliedVol", None)),
                        "delta": getattr(greeks, "delta", None) if greeks else None,
                        "gamma": getattr(greeks, "gamma", None) if greeks else None,
                        "theta": getattr(greeks, "theta", None) if greeks else None,
                        "vega": getattr(greeks, "vega", None) if greeks else None,
                    }
                )
        rows.sort(key=lambda r: (r["strike"], r["right"]))
        return rows

    async def iv_history(self, symbol: str, duration: str = "1 Y") -> list[dict]:
        """Daily ATM implied-volatility series from IBKR's own IV index
        (whatToShow=OPTION_IMPLIED_VOLATILITY: 30-day interpolated ATM IV).
        Reuse-first: ~a year of history in one request, so IV rank works
        immediately instead of accruing one snapshot per night."""
        ib = self.client.require()
        contract = await self._stock(symbol)
        bars = await asyncio.wait_for(
            ib.reqHistoricalDataAsync(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting="1 day",
                whatToShow="OPTION_IMPLIED_VOLATILITY",
                useRTH=True,
                formatDate=2,
            ),
            IB_TIMEOUT,
        )
        if not bars:
            raise ProviderError(f"IBKR returned no IV history for '{symbol}'")
        return [
            {"date": b.date.isoformat(), "iv": float(b.close)}
            for b in bars
            if b.close and not math.isnan(float(b.close)) and float(b.close) > 0
        ]

    async def spot(self, symbol: str) -> float | None:
        try:
            return (await self.quote(symbol))["price"]
        except Exception:  # noqa: BLE001
            return None
