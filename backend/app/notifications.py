from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

SETTINGS_DIR = Path('/app/data/settings')
NOTIFICATIONS_FILE = SETTINGS_DIR / 'notifications.json'

_DEFAULT = {
    'enabled': False,
    'discord_webhook': '',
    'ntfy_url': '',
    'webhook_url': '',
    'events': ['stack_deployed', 'stack_deleted', 'health_fail'],
}


def load_notification_settings() -> dict:
    if not NOTIFICATIONS_FILE.exists():
        return dict(_DEFAULT)
    try:
        return {**_DEFAULT, **json.loads(NOTIFICATIONS_FILE.read_text())}
    except Exception:
        return dict(_DEFAULT)


def save_notification_settings(settings: dict) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    merged = {**_DEFAULT, **settings}
    NOTIFICATIONS_FILE.write_text(json.dumps(merged, indent=2))


def send_notification(event: str, title: str, message: str) -> None:
    """Fire-and-forget notification — runs in a background thread."""
    threading.Thread(
        target=_dispatch,
        args=(event, title, message),
        daemon=True,
    ).start()


def _dispatch(event: str, title: str, message: str) -> None:
    cfg = load_notification_settings()
    if not cfg.get('enabled'):
        return
    if event not in cfg.get('events', []):
        return

    if cfg.get('discord_webhook'):
        _post_json(cfg['discord_webhook'], {'content': f'**{title}**\n{message}'})

    if cfg.get('ntfy_url'):
        _post_raw(cfg['ntfy_url'], message.encode(), {'Title': title, 'Content-Type': 'text/plain'})

    if cfg.get('webhook_url'):
        _post_json(cfg['webhook_url'], {'event': event, 'title': title, 'message': message})


def _post_json(url: str, payload: dict) -> None:
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def _post_raw(url: str, data: bytes, headers: dict) -> None:
    try:
        req = urllib.request.Request(url, data=data, headers=headers)
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass
