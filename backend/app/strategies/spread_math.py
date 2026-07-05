"""Pure payoff math for option combos (no IB dependency, unit-tested).

Sign convention: qty is +1 for a long leg and -1 for a short leg. Payoff is
piecewise-linear in the underlying, so evaluating at the strikes plus padded
endpoints fully defines the curve; the tails are flat because each right has
an equal number of long and short legs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PayLeg:
    right: str  # "C" or "P"
    strike: float
    qty: int  # signed: +1 long, -1 short


def combo_intrinsic(legs: list[PayLeg], s: float) -> float:
    total = 0.0
    for leg in legs:
        if leg.right == "C":
            intrinsic = max(s - leg.strike, 0.0)
        else:
            intrinsic = max(leg.strike - s, 0.0)
        total += leg.qty * intrinsic
    return total


def payoff_points(
    legs: list[PayLeg],
    net_cost_per_share: float,
    multiplier: int = 100,
    contracts: int = 1,
    pad: float = 5.0,
) -> list[dict[str, float]]:
    """P&L at expiration, evaluated at every kink plus padded flat endpoints."""
    strikes = sorted({leg.strike for leg in legs})
    xs = [max(strikes[0] - pad, 0.0)] + strikes + [strikes[-1] + pad]
    return [
        {
            "x": round(x, 4),
            "y": round(
                (combo_intrinsic(legs, x) - net_cost_per_share) * multiplier * contracts, 2
            ),
        }
        for x in xs
    ]


def breakevens(points: list[dict[str, float]]) -> list[float]:
    """Zero crossings of the piecewise-linear P&L curve (linear interpolation)."""
    found: list[float] = []
    for a, b in zip(points, points[1:]):
        ya, yb = a["y"], b["y"]
        if ya == 0.0 and (not found or abs(found[-1] - a["x"]) > 1e-9):
            found.append(a["x"])
        if (ya < 0 < yb) or (ya > 0 > yb):
            x = a["x"] + (b["x"] - a["x"]) * (0 - ya) / (yb - ya)
            if not found or abs(found[-1] - x) > 1e-9:
                found.append(round(x, 4))
    if points and points[-1]["y"] == 0.0:
        x = points[-1]["x"]
        if not found or abs(found[-1] - x) > 1e-9:
            found.append(x)
    return found


def max_profile(points: list[dict[str, float]]) -> tuple[float, float]:
    """(max_loss, max_gain) in dollars over the evaluated curve."""
    ys = [p["y"] for p in points]
    return (min(ys), max(ys))
