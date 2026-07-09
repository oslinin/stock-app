"""Pure grouping/summing over the normalized position-dict shape shared
by fidelity_csv.py and ibkr_positions.py."""

from __future__ import annotations

from .bwdelta import beta_weighted_delta

GROUP_KEYS = {
    "account": lambda p: p.get("accountNumber") or "unknown",
    "underlying": lambda p: p["symbol"],
}


def enrich_position(
    position: dict,
    beta_by_symbol: dict[str, float],
    underlying_prices: dict[str, float],
    benchmark_price: float | None,
) -> dict:
    """Adds betaWeightedDelta to a copy of the position — None when any
    required input (a model delta, an IB-reported cached beta, a live
    underlying price, the benchmark price) is missing, never a guessed
    zero. beta is whatever IB Gateway last reported (portfolio/beta.py) —
    never computed here."""
    out = dict(position)
    beta = beta_by_symbol.get(position["symbol"])
    underlying_price = underlying_prices.get(position["symbol"])
    delta = position.get("delta")
    if beta is not None and underlying_price and benchmark_price and delta is not None:
        out["beta"] = beta
        out["betaWeightedDelta"] = beta_weighted_delta(
            delta, position["quantity"], position.get("multiplier", 1),
            beta, underlying_price, benchmark_price,
        )
    else:
        out["betaWeightedDelta"] = None
    return out


def group_positions(positions: list[dict], group_by: str) -> dict[str, list[dict]]:
    """group_by: 'account' | 'underlying'. 'campaign'/'strategy' from the
    plan need journal linkage / manual tags — not built this phase (no
    journal exists yet)."""
    key_fn = GROUP_KEYS.get(group_by)
    if key_fn is None:
        raise ValueError(f"unsupported group_by {group_by!r}")
    groups: dict[str, list[dict]] = {}
    for p in positions:
        groups.setdefault(key_fn(p), []).append(p)
    return groups


def _sum_present(positions: list[dict], key: str) -> float | None:
    values = [p[key] for p in positions if p.get(key) is not None]
    return sum(values) if values else None


def summarize(positions: list[dict]) -> dict:
    """Sums skip positions missing a given greek rather than treating a
    missing value as zero (a partial sum silently understates exposure)."""
    return {
        "count": len(positions),
        "totalDelta": _sum_present(positions, "delta"),
        "totalBetaWeightedDelta": _sum_present(positions, "betaWeightedDelta"),
        "totalTheta": _sum_present(positions, "theta"),
        "totalVega": _sum_present(positions, "vega"),
    }
