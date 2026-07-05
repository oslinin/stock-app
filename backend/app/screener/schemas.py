from __future__ import annotations

from pydantic import BaseModel, Field


class OrderRequest(BaseModel):
    strategyId: str = "vix_hedge"
    expiry: str | None = None  # YYYYMMDD; default = nearest in DTE window
    width: float | None = None
    contracts: int = Field(default=1, ge=1, le=100)


class AlertRuleIn(BaseModel):
    strategyId: str = "vix_hedge"
    channels: list[str] = ["email"]
    on: list[str] = ["ARMED", "ENTER"]
    email: str = ""
    active: bool = True


class AlertRulePatch(BaseModel):
    channels: list[str] | None = None
    on: list[str] | None = None
    email: str | None = None
    active: bool | None = None
