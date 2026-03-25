from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

SCHEDULES_FILE = Path('/app/data/schedules.json')

_scheduler = BackgroundScheduler(timezone='UTC')
_started = False


def _record_resources() -> None:
    try:
        from .docker_ops import get_container_resources
        from .resource_history import record_snapshot
        record_snapshot(get_container_resources())
    except Exception:
        pass


def start_scheduler() -> None:
    global _started
    if _started:
        return
    _scheduler.start()
    _started = True
    _load_persisted()
    _scheduler.add_job(
        _record_resources,
        'interval',
        seconds=30,
        id='resource_snapshot',
        replace_existing=True,
    )
    _record_resources()  # capture first snapshot immediately


def _load_persisted() -> None:
    for stack_name, cfg in _load_all().items():
        if cfg.get('enabled') and cfg.get('cron'):
            _add_job(stack_name, cfg['cron'])


def _add_job(stack_name: str, cron_expr: str) -> None:
    from .docker_ops import run_stack_action
    _scheduler.add_job(
        run_stack_action,
        CronTrigger.from_crontab(cron_expr, timezone='UTC'),
        id=f'restart_{stack_name}',
        args=[stack_name, 'restart'],
        replace_existing=True,
        misfire_grace_time=300,
    )


def set_schedule(stack_name: str, cron_expr: str, enabled: bool) -> dict:
    # Validate the cron expression by trying to build a trigger
    CronTrigger.from_crontab(cron_expr, timezone='UTC')

    schedules = _load_all()
    schedules[stack_name] = {'cron': cron_expr, 'enabled': enabled}
    _save_all(schedules)

    job_id = f'restart_{stack_name}'
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)
    if enabled:
        _add_job(stack_name, cron_expr)

    return schedules[stack_name]


def delete_schedule(stack_name: str) -> None:
    job_id = f'restart_{stack_name}'
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)
    schedules = _load_all()
    schedules.pop(stack_name, None)
    _save_all(schedules)


def get_schedule(stack_name: str) -> Optional[dict]:
    return _load_all().get(stack_name)


def list_schedules() -> dict:
    return _load_all()


def _load_all() -> dict:
    if not SCHEDULES_FILE.exists():
        return {}
    try:
        return json.loads(SCHEDULES_FILE.read_text())
    except Exception:
        return {}


def _save_all(schedules: dict) -> None:
    SCHEDULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULES_FILE.write_text(json.dumps(schedules, indent=2))
