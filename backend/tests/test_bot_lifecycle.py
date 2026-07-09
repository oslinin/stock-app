"""compile_bot's gate matrix: a bot may only be created/run from a spec
the runtime can fully execute. Each test blocks on exactly one reason,
so a human reading a blocker list can trust it's complete and specific."""

from app.bots.compile_bot import compile_bot
from app.specs.schema import (
    AdjustmentRule,
    Condition,
    ExitRules,
    LegSpec,
    Sizing,
)
from tests.test_spec_schema import sample_spec


def approvable_spec(**overrides):
    overrides.setdefault(
        "exit", ExitRules(profit_target_pct_credit=50.0, stop_loss_x_credit=2.0, time_exit_dte=21)
    )
    return sample_spec(**overrides)


def test_fully_specified_spec_compiles_clean():
    assert compile_bot(approvable_spec()) == []


def test_unspecified_exit_blocks():
    blockers = compile_bot(sample_spec())  # default exit leaves stop_loss_x_credit unspecified
    assert any("exit rules unspecified" in b for b in blockers)


def test_unsupported_condition_kind_blocks():
    spec = approvable_spec(
        entry=[Condition(kind="gex_regime_is", params={"regime": "positive"})]
    )
    blockers = compile_bot(spec)
    assert any("gex_regime_is" in b for b in blockers)


def test_unsupported_condition_in_gates_also_blocks():
    spec = approvable_spec(gates=[Condition(kind="cot_zscore_gte", params={"value": 1})])
    blockers = compile_bot(spec)
    assert any("cot_zscore_gte" in b for b in blockers)


def test_flagged_unsupported_conditions_block():
    spec = approvable_spec(unsupported_conditions=["earnings within 3 days"])
    blockers = compile_bot(spec)
    assert any("unsupported conditions" in b for b in blockers)


def test_adjustment_rules_block():
    spec = approvable_spec(
        adjustments=[
            AdjustmentRule(trigger=Condition(kind="delta_between", params={"min": 0.4, "max": 0.6}), action="roll_out_same_strike")
        ]
    )
    blockers = compile_bot(spec)
    assert any("adjustment rule" in b for b in blockers)


def test_missing_underlying_blocks():
    spec = approvable_spec(universe={"underlyings": [], "sec_type": "option"})
    blockers = compile_bot(spec)
    assert any("no underlying" in b for b in blockers)


def test_missing_sizing_blocks():
    spec = approvable_spec(sizing=Sizing(bp_pct=None, fixed_contracts=None))
    blockers = compile_bot(spec)
    assert any("sizing unspecified" in b for b in blockers)


def test_empty_structure_blocks():
    spec = approvable_spec(structure=[])
    blockers = compile_bot(spec)
    assert any("no legs" in b for b in blockers)


def test_multiple_blockers_all_reported_at_once():
    spec = approvable_spec(structure=[], universe={"underlyings": [], "sec_type": "option"})
    blockers = compile_bot(spec)
    assert len(blockers) >= 2
