"""/analytics — option structure analytics (optionlab: PoP, expected
profit, P&L bounds) for arbitrary legs."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..analytics.optionlab_glue import structure_analytics
from ..security import require_token

router = APIRouter(prefix="/analytics", dependencies=[Depends(require_token)])


class LegIn(BaseModel):
    right: str  # C|P
    action: str  # buy|sell
    strike: float
    premium: float
    qty: int = 1


class StructureIn(BaseModel):
    legs: list[LegIn]
    spot: float
    volatility: float
    interestRate: float = 0.04
    daysToTarget: int | None = Field(default=None, description="calendar days to target")
    startDate: date | None = None
    targetDate: date | None = None


@router.post("/structure")
def structure(body: StructureIn) -> dict:
    start = body.startDate or date.today()
    if body.targetDate is not None:
        target = body.targetDate
    elif body.daysToTarget is not None:
        target = start + timedelta(days=body.daysToTarget)
    else:
        raise HTTPException(422, "provide targetDate or daysToTarget")
    try:
        result = structure_analytics(
            legs=[leg.model_dump() for leg in body.legs],
            spot=body.spot,
            volatility=body.volatility,
            interest_rate=body.interestRate,
            start_date=start,
            target_date=target,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    result["startDate"] = start.isoformat()
    result["targetDate"] = target.isoformat()
    return result
