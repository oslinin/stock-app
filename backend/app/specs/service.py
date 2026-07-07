"""Spec persistence: create/version/approve, always deriving
section_status and review state from the schema (never trusting the
caller's copy)."""

from __future__ import annotations

import json
import re

from sqlmodel import select

from ..db.session import session_scope
from .models import SpecVersion, StrategySpec, utcnow
from .schema import OptionsStrategySpec


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "strategy"


def _unique_slug(session, base: str) -> str:
    slug, n = base, 2
    while session.exec(select(StrategySpec).where(StrategySpec.slug == slug)).first():
        slug = f"{base}-{n}"
        n += 1
    return slug


def create_spec(
    spec: OptionsStrategySpec,
    slug: str | None = None,
    created_by: str = "human",
    claimed_performance: dict | None = None,
) -> StrategySpec:
    with session_scope() as session:
        record = StrategySpec(
            slug=_unique_slug(session, slug or slugify(spec.meta.name)),
            name=spec.meta.name,
            category=spec.meta.category,
            origin=spec.meta.origin,
            status="needs_review" if spec.needs_review() else "draft",
            section_status_json=json.dumps(spec.section_status()),
            claimed_performance_json=json.dumps(claimed_performance),
        )
        session.add(record)
        session.flush()
        version = SpecVersion(
            spec_id=record.id,
            version=1,
            spec_json=spec.model_dump_json(),
            unsupported_json=json.dumps(spec.unsupported_conditions),
            created_by=created_by,
        )
        session.add(version)
        session.flush()
        record.current_version_id = version.id
        session.add(record)
        session.flush()
        session.refresh(record)
        session.expunge(record)
        return record


def add_version(
    spec_id: int, spec: OptionsStrategySpec, created_by: str = "human"
) -> SpecVersion:
    with session_scope() as session:
        record = session.get(StrategySpec, spec_id)
        if record is None:
            raise KeyError(spec_id)
        latest = session.exec(
            select(SpecVersion)
            .where(SpecVersion.spec_id == spec_id)
            .order_by(SpecVersion.version.desc())  # type: ignore[union-attr]
        ).first()
        version = SpecVersion(
            spec_id=spec_id,
            version=(latest.version + 1) if latest else 1,
            spec_json=spec.model_dump_json(),
            unsupported_json=json.dumps(spec.unsupported_conditions),
            created_by=created_by,
        )
        session.add(version)
        session.flush()
        record.current_version_id = version.id
        record.name = spec.meta.name
        record.category = spec.meta.category
        record.section_status_json = json.dumps(spec.section_status())
        # editing reopens review; approval is always an explicit human act
        record.status = "needs_review" if spec.needs_review() else "draft"
        record.updated_at = utcnow()
        session.add(record)
        session.flush()
        session.refresh(version)
        session.expunge(version)
        return version


def approve_spec(spec_id: int) -> StrategySpec:
    with session_scope() as session:
        record = session.get(StrategySpec, spec_id)
        if record is None:
            raise KeyError(spec_id)
        version = session.get(SpecVersion, record.current_version_id)
        spec = version.spec()
        if spec.needs_review() and spec.exit.unspecified_fields():
            # approving with unspecified exits is allowed only after the
            # human explicitly resolves them by editing — block here
            raise ValueError(
                "cannot approve: unspecified exit rules "
                f"{spec.exit.unspecified_fields()} — edit the spec to state them"
            )
        record.status = "approved"
        version.reviewed_at = utcnow()
        record.updated_at = utcnow()
        session.add(record)
        session.add(version)
        session.flush()
        session.refresh(record)
        session.expunge(record)
        return record


def get_spec(spec_id: int) -> tuple[StrategySpec, SpecVersion] | None:
    with session_scope() as session:
        record = session.get(StrategySpec, spec_id)
        if record is None:
            return None
        version = session.get(SpecVersion, record.current_version_id)
        session.expunge(record)
        if version is not None:
            session.expunge(version)
        return record, version


def list_specs(
    status: str | None = None,
    origin: str | None = None,
    category: str | None = None,
    lifecycle: str | None = None,
) -> list[StrategySpec]:
    with session_scope() as session:
        query = select(StrategySpec).order_by(StrategySpec.id)
        if status:
            query = query.where(StrategySpec.status == status)
        if origin:
            query = query.where(StrategySpec.origin == origin)
        if category:
            query = query.where(StrategySpec.category == category)
        if lifecycle:
            query = query.where(StrategySpec.lifecycle == lifecycle)
        records = session.exec(query).all()
        for r in records:
            session.expunge(r)
        return records
