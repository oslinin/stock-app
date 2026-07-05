from __future__ import annotations

import asyncio
import logging
import math
from datetime import date

from ..strategies.vix_hedge import ChainRow, Quote
from .client import IBClient
from .contracts import IB_TIMEOUT, vix_option
from .errors import DataUnavailable
from .opening_hours import et_today

log = logging.getLogger(__name__)

TICKER_CHUNK = 40


def _num(value) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or v <= 0:
        return None
    return v


def price_of(ticker) -> float | None:
    """Best available price from a ticker: last, then midpoint, then close."""
    for candidate in (ticker.last, ticker.marketPrice(), ticker.close):
        v = _num(candidate)
        if v is not None:
            return v
    return None


async def snapshot_price(client: IBClient, contract) -> float | None:
    ib = client.require()
    tickers = await asyncio.wait_for(ib.reqTickersAsync(contract), IB_TIMEOUT)
    return price_of(tickers[0]) if tickers else None


async def daily_closes(client: IBClient, contract, duration: str = "6 M") -> list[tuple[date, float]]:
    """Completed daily closes (today's in-progress bar is dropped)."""
    ib = client.require()
    bars = await asyncio.wait_for(
        ib.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        ),
        IB_TIMEOUT,
    )
    if not bars:
        raise DataUnavailable("no daily VIX history returned")
    out = [(b.date, float(b.close)) for b in bars]
    if out and out[-1][0] >= et_today():
        out = out[:-1]
    return out


async def intraday_bars(client: IBClient, contract):
    ib = client.require()
    return await asyncio.wait_for(
        ib.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr="1 D",
            barSizeSetting="5 mins",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=2,
        ),
        IB_TIMEOUT,
    )


async def option_chain_quotes(
    client: IBClient, expiry: str, strikes: list[float]
) -> list[ChainRow]:
    """Qualify and quote calls+puts for the given strikes in one batch pass."""
    ib = client.require()
    contracts = []
    for strike in strikes:
        contracts.append(("C", strike, vix_option(expiry, strike, "C")))
        contracts.append(("P", strike, vix_option(expiry, strike, "P")))

    qualified = await asyncio.wait_for(
        ib.qualifyContractsAsync(*[c for _, _, c in contracts]), IB_TIMEOUT
    )
    live = [(r, k, c) for (r, k, c), q in zip(contracts, qualified) if getattr(c, "conId", 0)]
    if not live:
        raise DataUnavailable(f"no VIX option contracts qualified for {expiry}")

    rows: dict[float, ChainRow] = {}
    for i in range(0, len(live), TICKER_CHUNK):
        chunk = live[i : i + TICKER_CHUNK]
        tickers = await asyncio.wait_for(
            ib.reqTickersAsync(*[c for _, _, c in chunk]), IB_TIMEOUT
        )
        for (right, strike, contract), ticker in zip(chunk, tickers):
            row = rows.setdefault(strike, ChainRow(strike))
            bid = None if ticker.bid is None or math.isnan(ticker.bid) or ticker.bid < 0 else float(ticker.bid)
            ask = None if ticker.ask is None or math.isnan(ticker.ask) or ticker.ask <= 0 else float(ticker.ask)
            quote = Quote(con_id=contract.conId, bid=bid, ask=ask)
            if right == "C":
                row.call = quote
            else:
                row.put = quote
    return [rows[k] for k in sorted(rows)]
