from app.strategies.vix_hedge import (
    ChainRow,
    Quote,
    VixHedgeParams,
    select_spread,
)

CENTER = 19.48


def q(mid, spread=0.06):
    return Quote(con_id=1, bid=round(mid - spread / 2, 4), ask=round(mid + spread / 2, 4))


def build_chain():
    call_mids = {
        13.5: 6.05, 14.5: 5.10, 15.5: 4.17, 16.5: 3.30, 17.5: 2.55,
        18.5: 1.95, 19.5: 1.50, 20.0: 1.30, 20.5: 1.10, 21.0: 0.95,
        21.5: 0.80, 22.0: 0.70,
    }
    put_mids = {
        13.5: 0.15, 14.5: 0.25, 15.5: 0.40, 16.5: 0.60, 17.5: 0.85,
        18.5: 1.15, 19.5: 1.55, 20.0: 1.90, 20.5: 2.30, 21.0: 2.80,
        21.5: 3.35, 22.0: 3.95,
    }
    return [
        ChainRow(k, call=q(call_mids[k]), put=q(put_mids[k]))
        for k in sorted(call_mids)
    ]


def test_selects_equal_width_pair_with_net_closest_to_zero():
    result = select_spread(build_chain(), CENTER, VixHedgeParams())
    assert result.found
    best = result.best
    # cheapest balanced pair in this chain: 16.5/17.5 call debit 0.75
    # financed by 19.5/20.5 put credit 0.75 -> net exactly $0
    assert (best.call_long, best.call_short) == (16.5, 17.5)
    assert (best.put_long, best.put_short) == (19.5, 20.5)
    assert abs(best.net) < 1e-9
    assert best.net_usd < VixHedgeParams().net_debit_cap_usd


def test_structure_constraints_respected():
    result = select_spread(build_chain(), CENTER, VixHedgeParams())
    for combo in [result.best] + result.alternatives:
        assert combo.call_short <= CENTER          # call spread below the future
        assert combo.put_long >= CENTER - 1e-6     # put spread above the future
        assert abs(combo.call_short - combo.call_long - 1.0) < 1e-9  # equal widths
        assert abs(combo.put_short - combo.put_long - 1.0) < 1e-9
        assert combo.net_usd < 100


def test_debit_cap_rejects_and_reports_closest():
    # an impossible cap forces every combo over it (nets here bottom out ~-$45)
    params = VixHedgeParams(net_debit_cap_usd=-1000.0)
    result = select_spread(build_chain(), CENTER, params)
    assert not result.found
    assert result.best is not None  # closest candidate still surfaced
    assert "cap" in result.reason


def test_no_puts_means_no_financing():
    chain = build_chain()
    for row in chain:
        row.put = Quote()
    result = select_spread(chain, CENTER, VixHedgeParams())
    assert not result.found
    assert result.candidates_checked == 0
