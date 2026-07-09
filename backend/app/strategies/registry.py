from __future__ import annotations

from ..config import Settings
from ..specs.spec_strategy import load_spec_strategies
from .base import Strategy
from .vix_hedge import VixHedgeStrategy


def build_registry(settings: Settings) -> dict[str, Strategy]:
    strategies: list[Strategy] = [VixHedgeStrategy(settings)]
    strategies += load_spec_strategies()
    return {s.id: s for s in strategies}
