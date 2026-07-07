from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from ..db.session import session_scope
from ..security import require_token
from ..specs import service
from ..specs.compile_doc import compile_doc
from ..specs.models import SpecVersion, StrategySpec
from ..specs.schema import OptionsStrategySpec

router = APIRouter(prefix="/specs", dependencies=[Depends(require_token)])


class SpecIn(BaseModel):
    spec: OptionsStrategySpec
    claimed_performance: dict | None = None


def _record_out(record: StrategySpec, version: SpecVersion | None = None) -> dict:
    out = {
        "id": record.id,
        "slug": record.slug,
        "name": record.name,
        "category": record.category,
        "origin": record.origin,
        "status": record.status,
        "lifecycle": record.lifecycle,
        "sections": record.section_status,
        "claimedPerformance": record.claimed_performance,
        "currentVersionId": record.current_version_id,
        "createdAt": record.created_at.isoformat(),
        "updatedAt": record.updated_at.isoformat(),
    }
    if version is not None:
        out["version"] = version.version
        out["spec"] = json.loads(version.spec_json)
        out["createdBy"] = version.created_by
        out["reviewedAt"] = (
            version.reviewed_at.isoformat() if version.reviewed_at else None
        )
    return out


@router.get("")
def list_specs(
    status: str | None = None,
    origin: str | None = None,
    category: str | None = None,
    lifecycle: str | None = None,
) -> list[dict]:
    return [
        _record_out(r)
        for r in service.list_specs(
            status=status, origin=origin, category=category, lifecycle=lifecycle
        )
    ]


@router.post("", status_code=201)
def create_spec(body: SpecIn) -> dict:
    record = service.create_spec(
        body.spec, claimed_performance=body.claimed_performance
    )
    found = service.get_spec(record.id)
    return _record_out(*found)


@router.get("/{spec_id}")
def get_spec(spec_id: int) -> dict:
    found = service.get_spec(spec_id)
    if found is None:
        raise HTTPException(404, "spec not found")
    return _record_out(*found)


@router.put("/{spec_id}")
def update_spec(spec_id: int, body: SpecIn) -> dict:
    try:
        service.add_version(spec_id, body.spec)
    except KeyError:
        raise HTTPException(404, "spec not found")
    if body.claimed_performance is not None:
        with session_scope() as session:
            record = session.get(StrategySpec, spec_id)
            record.claimed_performance_json = json.dumps(body.claimed_performance)
            session.add(record)
    found = service.get_spec(spec_id)
    return _record_out(*found)


@router.post("/{spec_id}/approve")
def approve_spec(spec_id: int) -> dict:
    try:
        service.approve_spec(spec_id)
    except KeyError:
        raise HTTPException(404, "spec not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    found = service.get_spec(spec_id)
    return _record_out(*found)


def _load(spec_id: int) -> tuple[StrategySpec, OptionsStrategySpec]:
    found = service.get_spec(spec_id)
    if found is None or found[1] is None:
        raise HTTPException(404, "spec not found")
    record, version = found
    try:
        return record, version.spec()
    except ValidationError as exc:  # stored JSON predates a schema change
        raise HTTPException(500, f"stored spec no longer parses: {exc}")


@router.get("/{spec_id}/doc")
def spec_doc(spec_id: int, reference_price: float = 100.0) -> dict:
    record, spec = _load(spec_id)
    return compile_doc(
        spec,
        reference_price=reference_price,
        claimed_performance=record.claimed_performance,
    )


@router.get("/{spec_id}/payoff")
def spec_payoff(spec_id: int, reference_price: float = 100.0) -> dict:
    _, spec = _load(spec_id)
    return compile_doc(spec, reference_price=reference_price)["payoff"]
