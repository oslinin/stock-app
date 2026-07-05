from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..indicators.opening_range import ET
from .jobs import eod_arming_scan, intraday_confirmation_poll


def build_scheduler(engine, settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=ET)
    scheduler.add_job(
        eod_arming_scan,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=20, timezone=ET),
        args=[engine, settings],
        id="eod_arming_scan",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        intraday_confirmation_poll,
        CronTrigger(day_of_week="mon-fri", hour="9-15", minute="*/5", timezone=ET),
        args=[engine, settings],
        id="intraday_confirmation_poll",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
