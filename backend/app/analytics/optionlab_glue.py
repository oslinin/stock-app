"""Map arbitrary option legs onto optionlab and normalize its outputs.

optionlab works per share; the API returns per-contract dollars (x100).
Everything here is deterministic given fixed dates (closed-form BS model).
"""

from __future__ import annotations

from datetime import date

VALID_RIGHTS = {"C": "call", "P": "put"}
VALID_ACTIONS = {"buy", "sell"}
SHARES_PER_CONTRACT = 100.0


def _to_optionlab_leg(leg: dict) -> dict:
    right = str(leg.get("right", "")).upper()
    if right not in VALID_RIGHTS:
        raise ValueError(f"leg right must be C or P, got {leg.get('right')!r}")
    action = str(leg.get("action", "")).lower()
    if action not in VALID_ACTIONS:
        raise ValueError(f"leg action must be buy or sell, got {leg.get('action')!r}")
    strike = float(leg["strike"])
    premium = float(leg["premium"])
    qty = int(leg.get("qty", 1))
    if strike <= 0 or premium < 0 or qty <= 0:
        raise ValueError(f"invalid leg numbers: strike={strike} premium={premium} qty={qty}")
    return {
        "type": VALID_RIGHTS[right],
        "strike": strike,
        "premium": premium,
        "action": action,
        "n": qty * int(SHARES_PER_CONTRACT),
    }


def structure_analytics(
    legs: list[dict],
    spot: float,
    volatility: float,
    interest_rate: float,
    start_date: date,
    target_date: date,
    min_stock: float | None = None,
    max_stock: float | None = None,
) -> dict:
    """PoP / expected profit / P&L bounds for a set of legs held to
    target_date. Legs: {right: C|P, action: buy|sell, strike, premium,
    qty} with premium per share (as quoted)."""
    if not legs:
        raise ValueError("at least one leg is required")
    if target_date <= start_date:
        raise ValueError("target_date must be after start_date")
    strategy = [_to_optionlab_leg(leg) for leg in legs]

    from optionlab import run_strategy  # deferred: pulls scipy/matplotlib

    out = run_strategy(
        {
            "stock_price": spot,
            "volatility": volatility,
            "interest_rate": interest_rate,
            "min_stock": min_stock if min_stock is not None else spot * 0.5,
            "max_stock": max_stock if max_stock is not None else spot * 1.5,
            "start_date": start_date,
            "target_date": target_date,
            "strategy": strategy,
        }
    )
    return {
        "pop": out.probability_of_profit,
        "maxProfit": out.maximum_return_in_the_domain,
        "maxLoss": out.minimum_return_in_the_domain,
        "expectedProfitIfProfitable": out.expected_profit_if_profitable,
        "expectedLossIfUnprofitable": out.expected_loss_if_unprofitable,
        "profitRanges": [list(r) for r in out.profit_ranges],
        "strategyCost": out.strategy_cost,
        "model": "black-scholes",
    }
