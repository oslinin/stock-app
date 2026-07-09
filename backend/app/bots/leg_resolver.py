"""Resolves a spec's LegSpec structure into concrete chain strikes — the
minimum the bot runtime needs to build a DraftOrder. Pure arithmetic /
nearest-match over an already-fetched chain; no live lookups here.

Sign convention for PctOTM/AtmOffset/FixedWidthFromLeg: OTM is "away
from spot" — below spot for puts, above spot for calls. This isn't
stated in the schema itself, so it's a documented interpretation, not a
verbatim spec rule."""

from __future__ import annotations

from dataclasses import dataclass

from ..specs.schema import AtmOffset, DeltaTarget, FixedWidthFromLeg, LegSpec, PctOTM

SUPPORTED_STRIKE_RULES = frozenset({"delta_target", "pct_otm", "atm_offset", "fixed_width_from_leg"})


@dataclass
class ResolvedLeg:
    right: str
    strike: float
    action: str  # BUY | SELL
    ratio: int
    row: dict  # the matched chain row (bid/ask/iv/delta) for pricing


def _rows_for_right(chain: list[dict], right: str) -> list[dict]:
    return [r for r in chain if r["right"] == right]


def _nearest_by_strike(rows: list[dict], target_strike: float) -> dict | None:
    if not rows:
        return None
    return min(rows, key=lambda r: abs(r["strike"] - target_strike))


def _nearest_by_delta(rows: list[dict], target_delta: float) -> dict | None:
    candidates = [r for r in rows if r.get("delta") is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda r: abs(abs(r["delta"]) - abs(target_delta)))


def resolve_legs(structure: list[LegSpec], chain: list[dict], spot: float) -> list[ResolvedLeg]:
    resolved: list[ResolvedLeg] = []
    for leg in structure:
        rows = _rows_for_right(chain, leg.right)
        rule = leg.strike_rule
        away = -1 if leg.right == "P" else 1

        if isinstance(rule, DeltaTarget):
            row = _nearest_by_delta(rows, rule.delta)
        elif isinstance(rule, PctOTM):
            row = _nearest_by_strike(rows, spot * (1 + away * rule.pct))
        elif isinstance(rule, AtmOffset):
            row = _nearest_by_strike(rows, spot + away * rule.offset)
        elif isinstance(rule, FixedWidthFromLeg):
            if rule.from_leg >= len(resolved):
                raise ValueError(f"from_leg {rule.from_leg} not resolved yet — legs resolve in order")
            base = resolved[rule.from_leg]
            row = _nearest_by_strike(rows, base.strike + away * rule.width)
        else:
            raise ValueError(f"unsupported strike rule {rule!r}")

        if row is None:
            raise ValueError(f"no matching {leg.right} strike in chain for {rule!r}")
        action = "BUY" if leg.direction == "long" else "SELL"
        resolved.append(ResolvedLeg(right=leg.right, strike=row["strike"], action=action, ratio=leg.ratio, row=row))
    return resolved


def net_limit_price(legs: list[ResolvedLeg]) -> float:
    """Net debit (positive) or credit (negative) per share, from each
    leg's mid price: BUY legs cost, SELL legs pay."""
    total = 0.0
    for leg in legs:
        bid, ask = leg.row.get("bid"), leg.row.get("ask")
        mid = (bid + ask) / 2 if bid is not None and ask is not None else 0.0
        total += mid * leg.ratio if leg.action == "BUY" else -mid * leg.ratio
    return round(total, 2)
