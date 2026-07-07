"""Schema tests for OptionsStrategySpec (pure Pydantic, no I/O).

Pins the contract the rest of the platform builds on: JSON round-trip
stability, explicit Unspecified sentinels (never invented values),
needs_review derivation, and per-section status derivation.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.specs.schema import (
    UNSPECIFIED,
    AdjustmentRule,
    Condition,
    ExitRules,
    LegSpec,
    OptionsStrategySpec,
    Provenance,
    Sizing,
    is_unspecified,
)


def sample_spec(**overrides) -> OptionsStrategySpec:
    """The phase-1 hand-entered strategy: 45-DTE 0.30-delta put credit
    spread, 50% profit target, exit at 21 DTE."""
    base = dict(
        meta={
            "name": "45 DTE put credit spread",
            "category": "options",
            "origin": "manual",
            "source_ref": "",
        },
        universe={"underlyings": ["SPY"], "sec_type": "option"},
        structure=[
            LegSpec(
                right="P",
                direction="short",
                strike_rule={"kind": "delta_target", "delta": 0.30},
                dte_target=45,
            ),
            LegSpec(
                right="P",
                direction="long",
                strike_rule={"kind": "fixed_width_from_leg", "from_leg": 0, "width": 5.0},
                dte_target=45,
            ),
        ],
        entry=[
            Condition(
                kind="iv_rank_gte",
                params={"value": 30},
                provenance=Provenance(quote="I only sell when IV rank is over 30"),
            )
        ],
        exit=ExitRules(profit_target_pct_credit=50.0, time_exit_dte=21),
        adjustments=[],
        sizing=Sizing(bp_pct=5.0, max_concurrent=2),
        gates=[],
        unsupported_conditions=[],
    )
    base.update(overrides)
    return OptionsStrategySpec(**base)


def test_round_trip_json_stable():
    spec = sample_spec()
    dumped = spec.model_dump_json()
    reparsed = OptionsStrategySpec.model_validate_json(dumped)
    assert reparsed == spec
    # a second round trip must be byte-identical (no drift)
    assert reparsed.model_dump_json() == dumped


def test_exit_rules_default_to_unspecified():
    exits = ExitRules()
    assert is_unspecified(exits.profit_target_pct_credit)
    assert is_unspecified(exits.stop_loss_x_credit)
    assert is_unspecified(exits.time_exit_dte)
    # sentinel survives a JSON round trip
    reparsed = ExitRules.model_validate_json(exits.model_dump_json())
    assert is_unspecified(reparsed.stop_loss_x_credit)
    assert UNSPECIFIED == "unspecified"


def test_needs_review_when_exit_unspecified():
    # the sample spec never states a stop loss -> needs_review
    spec = sample_spec()
    assert is_unspecified(spec.exit.stop_loss_x_credit)
    assert spec.needs_review() is True

    fully_specified = sample_spec(
        exit=ExitRules(
            profit_target_pct_credit=50.0, stop_loss_x_credit=2.0, time_exit_dte=21
        )
    )
    assert fully_specified.needs_review() is False


def test_needs_review_when_unsupported_conditions_present():
    spec = sample_spec(
        exit=ExitRules(
            profit_target_pct_credit=50.0, stop_loss_x_credit=2.0, time_exit_dte=21
        ),
        unsupported_conditions=["only enter on down days that feel capitulatory"],
    )
    assert spec.needs_review() is True


def test_condition_kind_is_closed_enum():
    with pytest.raises(ValidationError):
        Condition(kind="vibes_are_good", params={})


def test_strike_rule_variants_round_trip():
    rules = [
        {"kind": "delta_target", "delta": 0.30},
        {"kind": "pct_otm", "pct": 5.0},
        {"kind": "atm_offset", "offset": -1.0},
        {"kind": "fixed_width_from_leg", "from_leg": 0, "width": 5.0},
    ]
    for rule in rules:
        leg = LegSpec(right="C", direction="long", strike_rule=rule)
        reparsed = LegSpec.model_validate_json(leg.model_dump_json())
        assert reparsed == leg
        assert reparsed.strike_rule.kind == rule["kind"]


def test_adjustment_rule_round_trip():
    adj = AdjustmentRule(
        trigger=Condition(kind="delta_between", params={"leg": 0, "min": 0.45, "max": 1.0}),
        action="roll_out_same_strike",
    )
    spec = sample_spec(adjustments=[adj])
    reparsed = OptionsStrategySpec.model_validate_json(spec.model_dump_json())
    assert reparsed.adjustments[0].action == "roll_out_same_strike"


def test_section_status_full_spec():
    spec = sample_spec()
    status = spec.section_status()
    assert status["entry"] == "defined"
    # profit target + time exit stated, stop loss unspecified -> partial
    assert status["exit"] == "partial"
    assert status["adjustments"] == "undefined"  # none stated
    assert status["sizing"] == "defined"


def test_section_status_degenerate_spec():
    spec = sample_spec(entry=[], exit=ExitRules(), sizing=Sizing())
    status = spec.section_status()
    assert status["entry"] == "undefined"
    assert status["exit"] == "undefined"
    assert status["sizing"] == "undefined"


def test_section_status_fully_defined_exit():
    spec = sample_spec(
        exit=ExitRules(
            profit_target_pct_credit=50.0, stop_loss_x_credit=2.0, time_exit_dte=21
        ),
        adjustments=[
            AdjustmentRule(
                trigger=Condition(kind="delta_between", params={"leg": 0, "min": 0.45}),
                action="roll_out_same_strike",
            )
        ],
    )
    status = spec.section_status()
    assert status["exit"] == "defined"
    assert status["adjustments"] == "defined"
