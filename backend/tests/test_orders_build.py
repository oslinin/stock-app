from app.ibkr.orders import (
    OrderLeg,
    build_combo_contract,
    build_limit_order,
    round_to_tick,
)

LEGS = [
    OrderLeg(101, "BUY", "14.5C"),
    OrderLeg(102, "SELL", "15.5C"),
    OrderLeg(103, "SELL", "21P"),
    OrderLeg(104, "BUY", "20P"),
]


def test_combo_contract_structure():
    combo = build_combo_contract(LEGS)
    assert combo.secType == "BAG"
    assert combo.symbol == "VIX"
    assert [l.conId for l in combo.comboLegs] == [101, 102, 103, 104]
    assert [l.action for l in combo.comboLegs] == ["BUY", "SELL", "SELL", "BUY"]
    assert all(l.ratio == 1 for l in combo.comboLegs)
    assert all(l.exchange == "CBOE" for l in combo.comboLegs)


def test_limit_order_never_transmits():
    order = build_limit_order(2, 0.07)
    assert order.transmit is False
    assert order.action == "BUY"
    assert order.orderType == "LMT"
    assert order.totalQuantity == 2
    assert order.lmtPrice == 0.05  # rounded to the VIX 0.05 tick


def test_net_credit_allows_negative_limit():
    order = build_limit_order(1, -0.12)
    assert order.lmtPrice == -0.10
    assert order.transmit is False


def test_round_to_tick():
    assert round_to_tick(0.07) == 0.05
    assert round_to_tick(0.08) == 0.10
    assert round_to_tick(-0.12) == -0.10
    assert round_to_tick(0.0) == 0.0
