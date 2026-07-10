"""Capability routing over registered providers.

Registration order is priority order: `route(capability)` returns the
first provider that declares the capability; `?source=` on the API maps
to `route(capability, source=name)` for an explicit override.
"""

from __future__ import annotations

from .base import Provider, ProviderError


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> Provider:
        try:
            return self._providers[name]
        except KeyError:
            raise ProviderError(f"unknown provider '{name}'") from None

    def route(self, capability: str, source: str | None = None) -> Provider:
        if source is not None:
            provider = self.get(source)
            if capability not in provider.capabilities:
                raise ProviderError(
                    f"provider '{source}' does not support '{capability}'"
                )
            return provider
        for provider in self._providers.values():
            if capability in provider.capabilities:
                return provider
        raise ProviderError(f"no provider supports '{capability}'")

    def describe(self) -> list[dict]:
        """For GET /marketdata/providers."""
        return [
            {
                "name": p.name,
                "capabilities": sorted(p.capabilities),
                "latency": p.latency,
            }
            for p in self._providers.values()
        ]
