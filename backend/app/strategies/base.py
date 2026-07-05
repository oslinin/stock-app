from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Strategy(ABC):
    """A screenable trade. The API envelope (verdict/checks/legs/net/payoff)
    is uniform across strategies so new trades plug in without new endpoints
    or new frontend components."""

    id: str
    name: str
    description: str
    underlying_symbol: str
    underlying_sec_type: str

    @abstractmethod
    def params_dict(self) -> dict[str, Any]:
        """Current effective parameters, for display/config in the UI."""

    def metadata(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "underlying": self.underlying_symbol,
            "secType": self.underlying_sec_type,
            "params": self.params_dict(),
        }
