from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..indicators.opening_range import ET
from .jobs import (
    beta_refresh,
    eod_arming_scan,
    intraday_confirmation_poll,
    iv_snapshot,
    watchlist_scan_job,
)


def build_scheduler(engine, settings, providers=None) -> AsyncIOScheduler:
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
    if providers is not None:
        scheduler.add_job(
            iv_snapshot,
            CronTrigger(day_of_week="mon-fri", hour=16, minute=45, timezone=ET),
            args=[providers, settings],
            id="iv_snapshot",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            watchlist_scan_job,
            CronTrigger(day_of_week="mon-fri", hour=17, minute=0, timezone=ET),
            args=[providers, settings],
            id="watchlist_scan",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            beta_refresh,
            CronTrigger(day_of_week="sat", hour=8, minute=0, timezone=ET),
            args=[providers, settings],
            id="beta_refresh",
            max_instances=1,
            coalesce=True,
        )
    return scheduler
