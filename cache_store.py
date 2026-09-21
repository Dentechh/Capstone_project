"""
Simple in-memory cache to cut down on Firestore reads.

Why this instead of Redis/Memcached: it's free, needs zero extra
infrastructure, and lives entirely inside the running Python process.

Tradeoff to know about: because the data lives in this process's RAM,
it is NOT shared across multiple worker processes. If you ever deploy
this with something like `gunicorn -w 4` (4 worker processes), each
worker has its own separate cache, so writes from one worker won't
invalidate the cache in another worker until that entry's TTL expires
on its own. For a single-process deployment (Flask dev server, or
`gunicorn -w 1`), invalidation is always immediate and exact.

Usage pattern used throughout main.py:
    value = self.cache.get(key)
    if value is None:
        value = <expensive Firestore read>
        self.cache.set(key, value, ttl_seconds=300)
    return value

And after any write that changes that data:
    self.cache.invalidate(key)
"""

import threading
import time


class SimpleCache:
    def __init__(self):
        self._store = {}  # key -> (value, expires_at_or_None)
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at is not None and time.time() > expires_at:
                # Stale -- drop it and report a miss.
                del self._store[key]
                return None
            return value

    def set(self, key, value, ttl_seconds=None):
        expires_at = (time.time() + ttl_seconds) if ttl_seconds else None
        with self._lock:
            self._store[key] = (value, expires_at)

    def invalidate(self, key):
        with self._lock:
            self._store.pop(key, None)

    def invalidate_many(self, keys):
        with self._lock:
            for k in keys:
                self._store.pop(k, None)