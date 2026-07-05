from __future__ import annotations

import logging
from datetime import date, datetime

from .client import IBClient
from .errors import DataUnavailable
from .ib_lib import Future, Index, Option

log = logging.getLogger(__name__)

VIX_TRADING_CLASS = "VIX"  # standard monthlies; weeklys use "VIXW"
IB_TIMEOUT = 25


async def vix_index(client: IBClient):
    ib = client.require()
    cached = getattr(client, "_vix_index", None)
    if cached is not None:
        return cached
    contract = Index("VIX", "CBOE", "USD")
    qualified = await ib.qualifyContractsAsync(contract)
    if not qualified:
        raise DataUnavailable("could not qualify the VIX index on CBOE")
    client._vix_index = qualified[0]
    return qualified[0]


async def vix_option_params(client: IBClient) -> tuple[list[str], list[float]]:
    """Monthly VIX option expirations (YYYYMMDD, sorted) and listed strikes."""
    ib = client.require()
    under = await vix_index(client)
    param_sets = await ib.reqSecDefOptParamsAsync(
        under.symbol, "", under.secType, under.conId
    )
    monthly = [p for p in param_sets if p.tradingClass == VIX_TRADING_CLASS]
    if not monthly:
        raise DataUnavailable("no VIX option parameters returned (tradingClass VIX)")
    expirations: set[str] = set()
    strikes: set[float] = set()
    for p in monthly:
        expirations.update(p.expirations)
        strikes.update(p.strikes)
    return sorted(expirations), sorted(strikes)


def pick_expiry(
    expirations: list[str], dte_min: int, dte_max: int, today: date | None = None
) -> tuple[str, int] | None:
    """Nearest monthly expiry whose DTE falls inside [dte_min, dte_max]."""
    today = today or date.today()
    for exp in expirations:
        exp_date = datetime.strptime(exp, "%Y%m%d").date()
        dte = (exp_date - today).days
        if dte_min <= dte <= dte_max:
            return exp, dte
    return None


def vix_option(expiry: str, strike: float, right: str) -> Option:
    return Option(
        "VIX",
        expiry,
        strike,
        right,
        "CBOE",
        multiplier="100",
        currency="USD",
        tradingClass=VIX_TRADING_CLASS,
    )


async def vix_future_for_expiry(client: IBClient, expiry: str):
    """The VIX future settling with this option expiry (same YYYYMM month).

    VIX options price off this future, not spot VIX — strike selection must
    center here. Returns None when the future can't be qualified (e.g. no
    CFE entitlement); callers fall back to spot with a warning.
    """
    ib = client.require()
    try:
        fut = Future("VIX", expiry[:6], "CFE", currency="USD")
        qualified = await ib.qualifyContractsAsync(fut)
        return qualified[0] if qualified else None
    except Exception as exc:  # noqa: BLE001
        log.warning("could not qualify VIX future for %s: %s", expiry, exc)
        return None
