"""Forward-looking 1-day CVaR by historical simulation: full BS repricing
for options (captures gamma), linear for stock. IV held constant across
scenarios (sticky-IV) — a beta-scaled vol shock is a documented upgrade,
not built this phase. Acceptance (plan): "CVaR validates on a known
synthetic portfolio (e.g. single short put: simulated CVaR ~= tail
repricing by hand)."""

import pytest
from vollib.black_scholes import black_scholes

from app.portfolio.risk import cvar, reprice_pnl, simulate_portfolio_pnl

R = 0.04


def test_cvar_picks_the_mean_of_the_worst_tail():
    pnls = [-10.0, -5.0, -5.0, 0.0, 0.0, 0.0, 20.0, 20.0, 20.0, 50.0]
    # 90% confidence -> worst 10% = 1 of 10 -> just the single worst value
    assert cvar(pnls, confidence=0.90) == pytest.approx(-10.0)
    # 80% confidence -> worst 20% = 2 of 10 -> mean of the two worst
    assert cvar(pnls, confidence=0.80) == pytest.approx(-7.5)


def test_cvar_of_empty_series_is_zero():
    assert cvar([], confidence=0.95) == 0.0


def test_reprice_pnl_stock_is_linear():
    position = {"secType": "STK", "spot": 100.0, "quantity": 10, "multiplier": 1}
    pnl = reprice_pnl(position, ret=0.02, r=R)
    assert pnl == pytest.approx(100.0 * 0.02 * 10)


def test_short_put_worst_scenario_matches_hand_repricing():
    spot, strike, iv, t_years = 100.0, 95.0, 0.25, 30 / 365
    position = {
        "secType": "OPT", "right": "P", "spot": spot, "strike": strike,
        "iv": iv, "tYears": t_years, "quantity": -1, "multiplier": 100,
    }
    # a deterministic, evenly-spaced scenario set (no randomness) -
    # the worst case for a short put is the biggest down move
    scenarios = [round(-0.05 + 0.005 * i, 4) for i in range(21)]  # -5% .. +5%
    pnls = simulate_portfolio_pnl([position], scenarios, R)

    worst_ret = min(scenarios)
    current = black_scholes("p", spot, strike, t_years, R, iv)
    new_spot = spot * (1 + worst_ret)
    new_t = t_years - 1 / 365
    repriced = black_scholes("p", new_spot, strike, new_t, R, iv)
    hand_pnl = (repriced - current) * -1 * 100

    # tail_size = round(21 * 0.05) = 1 -> the single worst scenario
    assert cvar(pnls, confidence=0.95) == pytest.approx(hand_pnl, rel=1e-6)
    assert hand_pnl < 0  # short put loses when the underlying drops


def test_non_priceable_option_position_raises_valueerror():
    position = {"secType": "OPT", "right": "P", "spot": 100.0, "strike": 95.0,
                "iv": None, "tYears": 30 / 365, "quantity": -1, "multiplier": 100}
    with pytest.raises(ValueError):
        reprice_pnl(position, ret=0.0, r=R)
