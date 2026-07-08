"""Idempotent seed of the phase-1 hand-entered strategy."""

from __future__ import annotations

from sqlmodel import select

from ..db.session import session_scope
from .schema import (
    Condition,
    ExitRules,
    LegSpec,
    Meta,
    OptionsStrategySpec,
    Sizing,
    Universe,
)
from .service import create_spec

SEED_SLUG = "put-credit-spread-45dte"


def seed_spec() -> OptionsStrategySpec:
    return OptionsStrategySpec(
        meta=Meta(
            name="45 DTE 0.30Δ put credit spread",
            category="options",
            origin="manual",
            description=(
                "Classic premium-selling baseline: sell a 0.30-delta put "
                "~45 DTE, buy a put 5 points further OTM, take profit at "
                "50% of credit, exit at 21 DTE regardless."
            ),
        ),
        universe=Universe(underlyings=["SPY"], sec_type="option"),
        structure=[
            LegSpec(
                right="P",
                direction="short",
                strike_rule={"kind": "delta_target", "delta": 0.30},
                dte_target=45,
                dte_window=(38, 52),
            ),
            LegSpec(
                right="P",
                direction="long",
                strike_rule={"kind": "fixed_width_from_leg", "from_leg": 0, "width": 5.0},
                dte_target=45,
            ),
        ],
        entry=[Condition(kind="iv_rank_gte", params={"value": 20})],
        exit=ExitRules(profit_target_pct_credit=50.0, time_exit_dte=21),
        sizing=Sizing(bp_pct=5.0, max_concurrent=2),
    )


def seed_default_specs() -> None:
    from .models import StrategySpec

    with session_scope() as session:
        exists = session.exec(
            select(StrategySpec).where(StrategySpec.slug == SEED_SLUG)
        ).first()
        if exists:
            return
    create_spec(seed_spec(), slug=SEED_SLUG, created_by="human")
