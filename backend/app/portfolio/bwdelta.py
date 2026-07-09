"""Beta-weighted delta, tastytrade's published formula:
stock:  Position Delta x Beta x (Underlying Price / Benchmark Price)
option: Option Delta x Contracts x 100 x Beta x (Underlying Price / Benchmark Price)
One function covers both — for stock pass multiplier=1 and delta=+-1/share."""

from __future__ import annotations


def beta_weighted_delta(
    delta: float,
    quantity: float,
    multiplier: float,
    beta: float,
    underlying_price: float,
    benchmark_price: float,
) -> float:
    return delta * quantity * multiplier * beta * (underlying_price / benchmark_price)
