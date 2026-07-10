"""yfinance-backed provider: free delayed quotes, bars, and option chains.

yfinance is synchronous, so every call runs under asyncio.to_thread.
Yahoo's option chain reports its own impliedVolatility per contract; rows
are normalized to plain dicts and (optionally) re-enriched with our own
vollib IV/greeks at the API layer.
"""

from __future__ import annotations

import asyncio
import math

from .base import BARS, CHAIN, EXPIRIES, QUOTE, ProviderError


def _f(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def _pos(value) -> float | None:
    v = _f(value)
    return v if v is not None and v > 0 else None


class YFinanceProvider:
    name = "yfinance"
    capabilities = frozenset({QUOTE, BARS, CHAIN, EXPIRIES})
    latency = "delayed"

    def _ticker(self, symbol: str):
        import yfinance as yf  # deferred: import cost + easier test fakes

        return yf.Ticker(symbol)

    async def _run(self, fn, *args):
        """Every sync yfinance call goes through here so network/library
        failures (proxy blocks, HTTP errors, yfinance's own exceptions)
        normalize to ProviderError once, instead of every caller of this
        provider needing to catch yfinance-specific exception types."""
        try:
            return await asyncio.to_thread(fn, *args)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize any failure
            raise ProviderError(f"yfinance request failed: {exc}") from exc

    # ------------------------------------------------------------- quote

    async def quote(self, symbol: str) -> dict:
        return await self._run(self._quote, symbol)

    def _quote(self, symbol: str) -> dict:
        info = self._ticker(symbol).fast_info
        def g(key):
            try:
                return _f(info[key])
            except (KeyError, TypeError):
                return None

        price = g("last_price")
        if price is None:
            raise ProviderError(f"yfinance returned no price for '{symbol}'")
        return {
            "symbol": symbol.upper(),
            "price": price,
            "previousClose": g("previous_close"),
            "dayHigh": g("day_high"),
            "dayLow": g("day_low"),
            "currency": getattr(info, "currency", None) or None,
        }

    # -------------------------------------------------------------- bars

    async def bars(self, symbol: str, period: str = "6mo", interval: str = "1d") -> list[dict]:
        return await self._run(self._bars, symbol, period, interval)

    def _bars(self, symbol: str, period: str, interval: str) -> list[dict]:
        df = self._ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
        if df is None or df.empty:
            raise ProviderError(f"yfinance returned no bars for '{symbol}'")
        out = []
        for ts, row in df.iterrows():
            close = _f(row.get("Close"))
            if close is None:
                continue
            out.append(
                {
                    "time": ts.isoformat(),
                    "open": _f(row.get("Open")),
                    "high": _f(row.get("High")),
                    "low": _f(row.get("Low")),
                    "close": close,
                    "volume": _f(row.get("Volume")),
                }
            )
        return out

    # ------------------------------------------------------------- chain

    async def expiries(self, symbol: str) -> list[str]:
        return await self._run(self._expiries, symbol)

    def _expiries(self, symbol: str) -> list[str]:
        expiries = list(self._ticker(symbol).options or ())
        if not expiries:
            raise ProviderError(f"yfinance lists no option expiries for '{symbol}'")
        return expiries

    async def chain(self, symbol: str, expiry: str) -> list[dict]:
        return await self._run(self._chain, symbol, expiry)

    def _chain(self, symbol: str, expiry: str) -> list[dict]:
        oc = self._ticker(symbol).option_chain(expiry)
        rows: list[dict] = []
        for right, df in (("C", oc.calls), ("P", oc.puts)):
            for _, r in df.iterrows():
                rows.append(
                    {
                        "expiry": expiry,
                        "strike": _f(r.get("strike")),
                        "right": right,
                        "bid": _pos(r.get("bid")),
                        "ask": _pos(r.get("ask")),
                        "last": _pos(r.get("lastPrice")),
                        "volume": _f(r.get("volume")),
                        "openInterest": _f(r.get("openInterest")),
                        "iv": _pos(r.get("impliedVolatility")),
                    }
                )
        rows = [r for r in rows if r["strike"] is not None]
        if not rows:
            raise ProviderError(f"empty option chain for '{symbol}' {expiry}")
        rows.sort(key=lambda r: (r["strike"], r["right"]))
        return rows
