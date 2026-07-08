"""Provider protocol + the provenance envelope every response ships in.

Guiding rule (plan: "Provenance everywhere"): no market data leaves the
API without saying where it came from, when, and whether it was
live/delayed/end-of-day. Routes wrap provider results with `envelope()`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

# capabilities a provider may declare
QUOTE = "quote"
BARS = "bars"
CHAIN = "chain"
EXPIRIES = "expiries"
HISTORICAL_OPTIONS = "historical_options"
IV_HISTORY = "iv_history"  # daily ATM-IV series (e.g. IBKR's IV index)


class ProviderError(Exception):
    """Routing/validation error in the provider layer (400-class)."""


@runtime_checkable
class Provider(Protocol):
    """Minimal contract; providers implement only the methods for the
    capabilities they declare. All data methods are async (sync client
    libraries run under asyncio.to_thread inside the provider)."""

    name: str
    capabilities: frozenset[str]
    latency: str  # live|delayed|eod


def envelope(data, provider: Provider, asof: datetime | None = None, **extra) -> dict:
    """`{data, provenance}` — the shape of every /marketdata response."""
    stamp = asof or datetime.now(timezone.utc)
    provenance = {
        "source": provider.name,
        "asof": stamp.isoformat(),
        "latency": provider.latency,
    }
    provenance.update(extra)
    return {"data": data, "provenance": provenance}
