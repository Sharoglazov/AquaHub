"""APScheduler-based automation: auto-feeding and light on/off scenarios.

Schedules live in the DB; :func:`sync_all` rebuilds the in-memory job set from
them, and the API calls it after any create/update/delete. Jobs publish MQTT
commands through the control service.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from ..db import SessionLocal  # noqa: F401  (kept for callers/tests)
from .. import db
from ..models import FeedingSchedule, LightScenario
from . import control

log = logging.getLogger("scheduler")

_scheduler: BackgroundScheduler | None = None


def start() -> None:
    global _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.start()
    sync_all()


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def _clear_owned_jobs() -> None:
    if _scheduler is None:
        return
    for job in _scheduler.get_jobs():
        if job.id.startswith(("feed-", "light-on-", "light-off-")):
            job.remove()


def sync_all() -> None:
    """Rebuild all automation jobs from the database."""
    if _scheduler is None:
        return
    _clear_owned_jobs()
    with db.SessionLocal() as session:
        for fs in session.execute(select(FeedingSchedule)).scalars():
            if fs.enabled:
                _add_feeding(fs)
        for ls in session.execute(select(LightScenario)).scalars():
            if ls.enabled:
                _add_light(ls)
    log.info("scheduler synced: %d jobs", len(_scheduler.get_jobs()))


def _add_feeding(fs: FeedingSchedule) -> None:
    _scheduler.add_job(
        control.feed, CronTrigger(hour=fs.hour, minute=fs.minute),
        args=[fs.device_id, fs.portions], id=f"feed-{fs.id}", replace_existing=True,
    )


def _add_light(ls: LightScenario) -> None:
    _scheduler.add_job(
        control.send_command, CronTrigger(hour=ls.on_hour, minute=ls.on_minute),
        args=[ls.device_id, "light", {"power": "on", "brightness": ls.brightness}],
        id=f"light-on-{ls.id}", replace_existing=True,
    )
    _scheduler.add_job(
        control.send_command, CronTrigger(hour=ls.off_hour, minute=ls.off_minute),
        args=[ls.device_id, "light", {"power": "off"}],
        id=f"light-off-{ls.id}", replace_existing=True,
    )
