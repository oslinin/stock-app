"""compile_backtest: spec -> optopsy strategy/kwargs + OO setup sheet +
signals CSV, with unsupported[] correctness (a rule the dataset/engine
can't express is reported, never silently dropped)."""

from app.backtests.compile_backtest import compile_backtest
from app.specs.schema import Condition, ExitRules, LegSpec, Sizing
from tests.test_spec_schema import sample_spec


def approvable_spec(**overrides):
    overrides.setdefault(
        "exit", ExitRules(profit_target_pct_credit=50.0, stop_loss_x_credit=2.0, time_exit_dte=21)
    )
    return sample_spec(**overrides)


def test_two_leg_put_credit_spread_maps_to_short_put_spread():
    result = compile_backtest(approvable_spec())
    assert result["supported"] is True
    assert result["optopsyStrategy"] == "short_put_spread"
    assert result["optopsyKwargs"]["delta_min"] == 0.25
    assert result["optopsyKwargs"]["delta_max"] == 0.35
    assert result["optopsyKwargs"]["exit_dte"] == 21


def test_two_leg_put_debit_spread_maps_to_long_put_spread():
    spec = approvable_spec(
        structure=[
            LegSpec(right="P", direction="long", strike_rule={"kind": "delta_target", "delta": 0.50}, dte_target=45),
            LegSpec(right="P", direction="long", strike_rule={"kind": "fixed_width_from_leg", "from_leg": 0, "width": 5.0}, dte_target=45),
        ]
    )
    result = compile_backtest(spec)
    assert result["optopsyStrategy"] == "long_put_spread"


def test_single_leg_short_put_maps_to_short_puts():
    spec = approvable_spec(
        structure=[LegSpec(right="P", direction="short", strike_rule={"kind": "delta_target", "delta": 0.20}, dte_target=30)]
    )
    result = compile_backtest(spec)
    assert result["optopsyStrategy"] == "short_puts"
    assert result["optopsyKwargs"]["delta_min"] == 0.15
    assert result["optopsyKwargs"]["delta_max"] == 0.25


def test_pct_otm_strike_rule_maps_to_max_otm_pct():
    spec = approvable_spec(
        structure=[LegSpec(right="C", direction="short", strike_rule={"kind": "pct_otm", "pct": 0.10}, dte_target=30)]
    )
    result = compile_backtest(spec)
    assert result["optopsyStrategy"] == "short_calls"
    assert result["optopsyKwargs"]["max_otm_pct"] == 0.10


def test_three_leg_structure_is_unsupported():
    spec = approvable_spec(
        structure=[
            LegSpec(right="P", direction="short", strike_rule={"kind": "delta_target", "delta": 0.20}, dte_target=30),
            LegSpec(right="P", direction="long", strike_rule={"kind": "fixed_width_from_leg", "from_leg": 0, "width": 5.0}, dte_target=30),
            LegSpec(right="C", direction="short", strike_rule={"kind": "delta_target", "delta": 0.20}, dte_target=30),
        ]
    )
    result = compile_backtest(spec)
    assert result["supported"] is False
    assert result["optopsyStrategy"] is None
    assert any("3-leg" in u for u in result["unsupported"])


def test_mixed_right_two_leg_structure_is_unsupported():
    spec = approvable_spec(
        structure=[
            LegSpec(right="P", direction="short", strike_rule={"kind": "delta_target", "delta": 0.20}, dte_target=30),
            LegSpec(right="C", direction="short", strike_rule={"kind": "delta_target", "delta": 0.20}, dte_target=30),
        ]
    )
    result = compile_backtest(spec)
    assert result["supported"] is False


def test_atm_offset_strike_rule_flagged_unsupported_for_optopsy():
    spec = approvable_spec(
        structure=[LegSpec(right="C", direction="short", strike_rule={"kind": "atm_offset", "offset": 3.0}, dte_target=30)]
    )
    result = compile_backtest(spec)
    assert result["supported"] is True  # single leg still maps to a strategy
    assert any("atm_offset" in u for u in result["unsupported"])


def test_pt_sl_exit_rules_always_flagged_unsupported_for_optopsy():
    # optopsy has no native P&L-triggered exit, only a calendar exit_dte
    result = compile_backtest(approvable_spec())
    assert any("profit_target_pct_credit" in u for u in result["unsupported"])


def test_oo_setup_sheet_carries_the_human_readable_fields():
    result = compile_backtest(approvable_spec())
    sheet = result["ooSetupSheet"]
    assert sheet["underlying"] == "SPY"
    assert sheet["strategyShape"] == "short_put_spread"
    assert sheet["profitTargetPctCredit"] == 50.0
    assert sheet["stopLossXCredit"] == 2.0


def test_signals_csv_has_a_header_even_with_no_gates():
    result = compile_backtest(approvable_spec())
    assert result["ooSignalsCsv"].startswith("date,signal")
