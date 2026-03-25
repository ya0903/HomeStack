from __future__ import annotations

import time
from collections import deque
from typing import Dict, List

# 60 snapshots × 30 s = 30 minutes of history
_history: deque = deque(maxlen=60)


def record_snapshot(resources: List[Dict]) -> None:
    _history.append({'ts': int(time.time()), 'data': resources})


def get_history() -> List[Dict]:
    return list(_history)
