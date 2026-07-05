from __future__ import annotations

from ..config import Settings
from .base import Strategy
from .vix_hedge import VixHedgeStrategy


def build_registry(settings: Settings) -> dict[str, Strategy]:
    strategies: list[Strategy] = [VixHedgeStrategy(settings)]
    return {s.id: s for s in strategies}
