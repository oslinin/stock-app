"""compile_bot: the strictest of the plan's three spec compilers
(doc/backtest/bot). A spec may describe rules the bot runtime can't
execute (adjustments/rolls aren't built this phase, an unsupported
condition kind, an unresolved Unspecified exit) — compile_bot refuses to
create/run a bot from such a spec rather than silently ignoring what it
can't do, and returns the exact blocker list so a human knows why."""

from __future__ import annotations

from ..specs.interpreter import CONDITION_EVALUATORS
from ..specs.schema import OptionsStrategySpec
from .leg_resolver import SUPPORTED_STRIKE_RULES


def compile_bot(spec: OptionsStrategySpec) -> list[str]:
    """[] = compilable; otherwise the list of reasons it isn't."""
    blockers: list[str] = []

    unspecified = spec.exit.unspecified_fields()
    if unspecified:
        blockers.append(f"exit rules unspecified: {', '.join(unspecified)}")

    if spec.unsupported_conditions:
        blockers.append(f"spec flags unsupported conditions: {', '.join(spec.unsupported_conditions)}")

    for cond in [*spec.entry, *spec.gates]:
        if cond.kind not in CONDITION_EVALUATORS:
            blockers.append(f"condition kind not runtime-supported: {cond.kind}")

    for leg in spec.structure:
        if leg.strike_rule.kind not in SUPPORTED_STRIKE_RULES:
            blockers.append(f"strike rule not runtime-supported: {leg.strike_rule.kind}")

    if spec.adjustments:
        blockers.append(
            f"{len(spec.adjustments)} adjustment rule(s) present — rolls/adjustments aren't "
            "built yet (this phase only runs entry through fill; exit/adjustment monitoring "
            "is a documented follow-up), so a bot can't safely manage this spec's exits"
        )

    if not spec.universe.underlyings:
        blockers.append("no underlying symbol in universe")

    if spec.sizing.bp_pct is None and spec.sizing.fixed_contracts is None:
        blockers.append("sizing unspecified (need bp_pct or fixed_contracts)")

    if not spec.structure:
        blockers.append("no legs in structure")

    return blockers
