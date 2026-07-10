"""Live IBKR positions + account summary, normalized to the same
position-dict shape fidelity_csv.py produces. Wraps the existing
IBClient (never modified) — same pattern as dataproviders/ibkr_provider.py.

ponytail: model greeks (delta/theta/vega) aren't populated here — IBKR
only supplies them via a live reqMktData greeks tick per contract (the
same enrichment ibkr_provider.py already does for chains), a second
network round trip this pass doesn't make. Positions show quantity/price
correctly; aggregate greek sums read as unavailable until that follow-up
lands. Ceiling: /portfolio/summary's totalDelta/totalTheta/totalVega stay
None for IBKR positions.
"""

from __future__ import annotations

from ..ibkr.client import IBClient
from ..ibkr.errors import IBKRUnavailable

ACCOUNT_SUMMARY_TAGS = {"NetLiquidation", "BuyingPower", "GrossPositionValue"}


def _iso_expiry(raw: str) -> str | None:
    if not raw or len(raw) < 8:
        return None
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def _normalize(item) -> dict:
    c = item.contract
    sec_type = "OPT" if c.secType in ("OPT", "FOP") else "STK"
    multiplier = float(c.multiplier) if getattr(c, "multiplier", "") else None
    return {
        "symbol": c.symbol,
        "secType": sec_type,
        "right": getattr(c, "right", None) or None,
        "strike": float(c.strike) if getattr(c, "strike", 0) else None,
        "expiry": _iso_expiry(getattr(c, "lastTradeDateOrContractMonth", ""))
        if sec_type == "OPT"
        else None,
        "quantity": float(item.position),
        "multiplier": multiplier or (100.0 if sec_type == "OPT" else 1.0),
        "lastPrice": float(item.marketPrice) if item.marketPrice else None,
        "avgCost": float(item.averageCost) if item.averageCost else None,
        "accountNumber": item.account,
        "description": "",
        "source": "ibkr_live",
    }


def fetch_positions(client: IBClient) -> list[dict]:
    """[] (not an error) when the gateway isn't connected — /positions
    still returns Fidelity-only results."""
    try:
        ib = client.require()
    except IBKRUnavailable:
        return []
    return [_normalize(item) for item in ib.portfolio()]


def fetch_account_summary(client: IBClient) -> dict:
    """{} when the gateway isn't connected. Values are provider-labeled
    strings from IB; the route layer casts what it needs."""
    try:
        ib = client.require()
    except IBKRUnavailable:
        return {}
    out: dict[str, dict] = {}
    for row in ib.accountSummary():
        if row.tag in ACCOUNT_SUMMARY_TAGS:
            out.setdefault(row.account, {})[row.tag] = row.value
    return out
