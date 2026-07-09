"""Beta vs the benchmark comes from IB Gateway's fundamental-ratios feed
(generic tick 258) — never computed in this process. If the account
lacks the market-data entitlement that tick needs (Reuters Fundamentals,
a paid subscription on many exchanges), IB simply never populates the
ratio and the symbol is skipped; that's an acceptable gap, not something
to route around with an in-process regression."""

from __future__ import annotations

import asyncio
import math

from ..ibkr.client import IBClient
from ..ibkr.contracts import IB_TIMEOUT
from ..ibkr.errors import IBKRUnavailable
from ..ibkr.ib_lib import Stock

FUNDAMENTAL_RATIOS_TICK = "258"
POLL_INTERVAL_SECONDS = 0.25
MAX_WAIT_SECONDS = 5.0


def extract_beta(ratios) -> float | None:
    """Pull Beta out of an ib_async FundamentalRatios object. None if the
    tick never arrived, the tag is absent, or IB's own "no data" sentinel
    (-99999.99, which ib_async already turns into NaN) came back."""
    if ratios is None:
        return None
    value = getattr(ratios, "Beta", None)
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(value) else value


async def fetch_beta(client: IBClient, symbol: str) -> float | None:
    try:
        ib = client.require()
    except IBKRUnavailable:
        return None
    contract = Stock(symbol.upper(), "SMART", "USD")
    qualified = await asyncio.wait_for(ib.qualifyContractsAsync(contract), IB_TIMEOUT)
    if not qualified:
        return None
    ticker = ib.reqMktData(qualified[0], genericTickList=FUNDAMENTAL_RATIOS_TICK)
    try:
        waited = 0.0
        while ticker.fundamentalRatios is None and waited < MAX_WAIT_SECONDS:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            waited += POLL_INTERVAL_SECONDS
        return extract_beta(ticker.fundamentalRatios)
    finally:
        ib.cancelMktData(qualified[0])
