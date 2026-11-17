"""Simple per-key rate limits, held in memory.

Enough for one API process (how Invest-pad runs today). With several processes each keeps
its own count, so the real limit is N times higher; move this to Postgres or Redis before
scaling out. Limits are deliberately generous: they stop scripts and runaway loops, not people.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException

_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()

# name: (max calls, window in seconds)
LIMITS = {
    "signup": (10, 3600),        # per client address
    "ask": (60, 3600),           # questions per user (app and extension together)
    "scan": (30, 3600),          # contradiction scans per user
    "export": (10, 3600),        # full exports per user
}


def check(name: str, key: str) -> None:
    most, window = LIMITS[name]
    now = time.monotonic()
    with _lock:
        hits = _hits[f"{name}:{key}"]
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= most:
            raise HTTPException(429, "Too many requests. Try again later.")
        hits.append(now)


def reset() -> None:
    with _lock:
        _hits.clear()
