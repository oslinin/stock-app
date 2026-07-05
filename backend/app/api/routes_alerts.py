from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from ..alerts.models import AlertEvent, AlertRule
from ..db.session import session_scope
from ..screener.schemas import AlertRuleIn, AlertRulePatch
from ..security import require_token

router = APIRouter(dependencies=[Depends(require_token)])


def _rule_out(rule: AlertRule) -> dict:
    return {
        "id": rule.id,
        "strategyId": rule.strategy_id,
        "channels": [c for c in rule.channels.split(",") if c],
        "on": [v for v in rule.on_verdicts.split(",") if v],
        "email": rule.email,
        "active": rule.active,
        "createdAt": rule.created_at.isoformat(),
    }


@router.get("/alerts")
def list_rules() -> list[dict]:
    with session_scope() as session:
        rules = session.exec(select(AlertRule).order_by(AlertRule.id)).all()
        return [_rule_out(r) for r in rules]


@router.post("/alerts", status_code=201)
def create_rule(body: AlertRuleIn) -> dict:
    rule = AlertRule(
        strategy_id=body.strategyId,
        channels=",".join(body.channels),
        on_verdicts=",".join(v.upper() for v in body.on),
        email=body.email,
        active=body.active,
    )
    with session_scope() as session:
        session.add(rule)
        session.flush()
        return _rule_out(rule)


@router.patch("/alerts/{rule_id}")
def update_rule(rule_id: int, body: AlertRulePatch) -> dict:
    with session_scope() as session:
        rule = session.get(AlertRule, rule_id)
        if rule is None:
            raise HTTPException(404, "alert rule not found")
        if body.channels is not None:
            rule.channels = ",".join(body.channels)
        if body.on is not None:
            rule.on_verdicts = ",".join(v.upper() for v in body.on)
        if body.email is not None:
            rule.email = body.email
        if body.active is not None:
            rule.active = body.active
        session.add(rule)
        session.flush()
        return _rule_out(rule)


@router.delete("/alerts/{rule_id}", status_code=204)
def delete_rule(rule_id: int) -> None:
    with session_scope() as session:
        rule = session.get(AlertRule, rule_id)
        if rule is None:
            raise HTTPException(404, "alert rule not found")
        session.delete(rule)


@router.get("/alerts/events")
def list_events(limit: int = 50) -> list[dict]:
    with session_scope() as session:
        events = session.exec(
            select(AlertEvent).order_by(AlertEvent.id.desc()).limit(min(limit, 200))  # type: ignore[union-attr]
        ).all()
        return [
            {
                "id": e.id,
                "ruleId": e.rule_id,
                "strategyId": e.strategy_id,
                "verdict": e.verdict,
                "tradingDate": e.trading_date,
                "expiry": e.expiry,
                "summary": e.summary,
                "createdAt": e.created_at.isoformat(),
            }
            for e in events
        ]
