"""SpecStrategy: wraps an approved spec to the existing thin Strategy
ABC (app/strategies/base.py) so it appears in /strategies and the
registry with no new plumbing — see app/strategies/registry.py."""

from __future__ import annotations

from typing import Any

from ..strategies.base import Strategy
from . import service
from .models import StrategySpec
from .schema import OptionsStrategySpec


class SpecStrategy(Strategy):
    def __init__(self, record: StrategySpec, spec: OptionsStrategySpec):
        self.id = f"spec:{record.slug}"
        self.name = spec.meta.name
        self.description = spec.meta.description
        self.underlying_symbol = spec.universe.underlyings[0] if spec.universe.underlyings else ""
        self.underlying_sec_type = spec.universe.sec_type
        self.record = record
        self.spec = spec

    def params_dict(self) -> dict[str, Any]:
        return {
            "category": self.spec.meta.category,
            "origin": self.spec.meta.origin,
            "entryConditions": len(self.spec.entry),
            "gates": len(self.spec.gates),
        }


def load_spec_strategies() -> list[SpecStrategy]:
    """Every approved spec, wrapped — the registry appends these
    alongside the built-in strategies."""
    strategies = []
    for record in service.list_specs(status="approved"):
        found = service.get_spec(record.id)
        if found is None or found[1] is None:
            continue
        _, version = found
        try:
            spec = version.spec()
        except Exception:  # noqa: BLE001 - stored JSON predates a schema change
            continue
        strategies.append(SpecStrategy(record, spec))
    return strategies
