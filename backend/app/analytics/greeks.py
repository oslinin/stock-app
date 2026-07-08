"""Black-Scholes price, greeks, and implied vol via vollib.

Conventions (pinned by tests/test_greeks.py against hand-computed values):
- vega is per 1 percentage point of vol
- theta is per calendar day
- rights are "C"/"P" at this layer; vollib's "c"/"p" stays internal

Note: the plan named py_vollib; upstream renamed/restructured it into
`vollib` (same org, same numerics) — we depend on vollib directly.
"""

from __future__ import annotations

from vollib.black_scholes import black_scholes
from vollib.black_scholes.greeks.analytical import delta, gamma, theta, vega
from vollib.black_scholes.implied_volatility import implied_volatility

GREEK_FNS = {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}


def _flag(right: str) -> str:
    r = right.upper()
    if r not in ("C", "P"):
        raise ValueError(f"right must be 'C' or 'P', got {right!r}")
    return "c" if r == "C" else "p"


def bs_price(right: str, s: float, k: float, t_years: float, r: float, sigma: float) -> float:
    return black_scholes(_flag(right), s, k, t_years, r, sigma)


def bs_greeks(right: str, s: float, k: float, t_years: float, r: float, sigma: float) -> dict:
    f = _flag(right)
    return {name: fn(f, s, k, t_years, r, sigma) for name, fn in GREEK_FNS.items()}


def implied_vol(
    price: float, right: str, s: float, k: float, t_years: float, r: float
) -> float | None:
    """BS implied vol from an observed price; None when no vol explains the
    price (below intrinsic, expired, non-positive inputs) — bad quotes are
    data, not exceptions."""
    if price is None or price <= 0 or t_years <= 0 or s <= 0 or k <= 0:
        return None
    try:
        iv = implied_volatility(price, s, k, t_years, r, _flag(right))
    except Exception:  # noqa: BLE001 - vollib raises per-condition subclasses
        return None
    return iv if iv and iv > 0 else None


def enrich_chain(rows: list[dict], spot: float, t_years: float, r: float) -> list[dict]:
    """Add mid-price IV + greeks to chain rows in place (rows lacking a
    usable mid, or with provider IV already present, keep what they have)."""
    for row in rows:
        bid, ask = row.get("bid"), row.get("ask")
        mid = (bid + ask) / 2 if bid is not None and ask is not None else None
        iv = row.get("iv")
        if iv is None and mid is not None:
            iv = implied_vol(mid, row["right"], spot, row["strike"], t_years, r)
            row["iv"] = iv
        if iv is not None and row.get("delta") is None:
            row.update(bs_greeks(row["right"], spot, row["strike"], t_years, r, iv))
        else:
            for greek in ("delta", "gamma", "theta", "vega"):
                row.setdefault(greek, None)
        row.setdefault("iv", None)
    return rows
