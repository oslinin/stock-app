from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel

from .schema import OptionsStrategySpec


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StrategySpec(SQLModel, table=True):
    __tablename__ = "strategy_spec"

    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    name: str
    category: str = "options"  # options|stock|crypto
    origin: str = "manual"  # youtube|corpus|manual
    status: str = "draft"  # draft|needs_review|approved|archived
    lifecycle: str = "defined"  # undefined|defined|backtested|paper|live
    current_version_id: int | None = None
    section_status_json: str = "{}"
    claimed_performance_json: str = "null"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def section_status(self) -> dict:
        return json.loads(self.section_status_json)

    @property
    def claimed_performance(self) -> dict | None:
        return json.loads(self.claimed_performance_json)


class SpecVersion(SQLModel, table=True):
    __tablename__ = "spec_version"

    id: int | None = Field(default=None, primary_key=True)
    spec_id: int = Field(index=True)
    version: int = 1
    spec_json: str
    unsupported_json: str = "[]"
    created_by: str = "human"  # llm|human
    reviewed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)

    def spec(self) -> OptionsStrategySpec:
        return OptionsStrategySpec.model_validate_json(self.spec_json)
