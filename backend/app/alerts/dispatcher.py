from __future__ import annotations

import asyncio
import logging

from sqlmodel import select

from ..config import Settings
from ..db.session import session_scope
from .models import AlertEvent, AlertRule
from .push import send_push
from .smtp import send_email

log = logging.getLogger(__name__)


async def dispatch(
    settings: Settings,
    strategy_id: str,
    verdict: str,
    trading_date: str,
    expiry: str,
    summary: str,
) -> int:
    """Fire matching alert rules at most once per (rule, verdict, trading day).

    Returns the number of events actually fired (post-dedupe).
    """
    fired = 0
    with session_scope() as session:
        rules = session.exec(
            select(AlertRule).where(
                AlertRule.active == True,  # noqa: E712
                AlertRule.strategy_id == strategy_id,
            )
        ).all()
        for rule in rules:
            wanted = [v.strip().upper() for v in rule.on_verdicts.split(",") if v.strip()]
            if verdict not in wanted:
                continue
            duplicate = session.exec(
                select(AlertEvent).where(
                    AlertEvent.rule_id == rule.id,
                    AlertEvent.verdict == verdict,
                    AlertEvent.trading_date == trading_date,
                    AlertEvent.expiry == expiry,
                )
            ).first()
            if duplicate:
                continue
            session.add(
                AlertEvent(
                    rule_id=rule.id,
                    strategy_id=strategy_id,
                    verdict=verdict,
                    trading_date=trading_date,
                    expiry=expiry,
                    summary=summary[:2000],
                )
            )
            fired += 1
            subject = f"[VIX Screener] {verdict} — {strategy_id} ({trading_date})"
            channels = [c.strip() for c in rule.channels.split(",") if c.strip()]
            if "email" in channels:
                to = rule.email or settings.default_alert_email
                await asyncio.to_thread(send_email, settings, to, subject, summary)
            if "push" in channels:
                await asyncio.to_thread(send_push, settings, subject, summary)
    if fired:
        log.info("dispatched %d alert(s): %s %s", fired, strategy_id, verdict)
    return fired
