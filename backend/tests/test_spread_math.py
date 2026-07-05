from app.strategies.spread_math import (
    PayLeg,
    breakevens,
    combo_intrinsic,
    max_profile,
    payoff_points,
)

# The reference structure from the strategy: long 14.5C / short 15.5C (debit)
# + short 21P / long 20P (credit), $100 multiplier.
LEGS = [
    PayLeg("C", 14.5, +1),
    PayLeg("C", 15.5, -1),
    PayLeg("P", 21.0, -1),
    PayLeg("P", 20.0, +1),
]


def test_combo_intrinsic_regions():
    assert combo_intrinsic(LEGS, 13.0) == -1.0  # both spreads at max pain
    assert combo_intrinsic(LEGS, 17.0) == 0.0   # call spread +1, put spread -1
    assert combo_intrinsic(LEGS, 25.0) == 1.0   # call spread +1, puts expire


def test_payoff_points_and_breakevens_nonzero_net():
    # debit 0.80, credit 0.70 -> net debit 0.10/share = $10/combo
    pts = payoff_points(LEGS, net_cost_per_share=0.10, pad=5.0)
    by_x = {p["x"]: p["y"] for p in pts}
    assert by_x[9.5] == -110.0
    assert by_x[14.5] == -110.0
    assert by_x[15.5] == -10.0
    assert by_x[20.0] == -10.0
    assert by_x[21.0] == 90.0
    assert by_x[26.0] == 90.0
    assert breakevens(pts) == [20.1]
    assert max_profile(pts) == (-110.0, 90.0)


def test_payoff_zero_net_plateau():
    pts = payoff_points(LEGS, net_cost_per_share=0.0)
    by_x = {p["x"]: p["y"] for p in pts}
    assert by_x[14.5] == -100.0
    assert by_x[15.5] == 0.0
    assert by_x[20.0] == 0.0
    assert by_x[21.0] == 100.0
    # zero plateau: both edges reported as breakeven boundaries
    assert breakevens(pts) == [15.5, 20.0]


def test_contracts_scale_linearly():
    pts = payoff_points(LEGS, net_cost_per_share=0.10, contracts=10)
    assert min(p["y"] for p in pts) == -1100.0
    assert max(p["y"] for p in pts) == 900.0
