"""In-process token-bucket rate limiter (no I/O).

Built for high-volume, low-stakes public endpoints (the analytics beacon) where a
DB-backed counter would cost a write per request — the very load being limited.
Each uvicorn worker holds its own buckets, so with N workers the effective ceiling
is N x the configured figure; callers must size limits with that in mind (the API
runs 2 workers — plan §R-C). Two layers:

* a **global** bucket per worker that protects the database whoever is sending;
* a **per-key** bucket (LRU-bounded so memory cannot grow without limit).

A request is admitted only if BOTH buckets have a token; tokens are consumed only
on admission. Thread-safe.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float


class InProcessRateLimiter:
    def __init__(
        self,
        *,
        global_rate_per_sec: float,
        global_burst: int,
        key_rate_per_sec: float,
        key_burst: int,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if min(global_rate_per_sec, key_rate_per_sec) <= 0 or min(global_burst, key_burst) < 1:
            raise ValueError("rates must be > 0 and bursts >= 1")
        self._global_rate = global_rate_per_sec
        self._global_burst = float(global_burst)
        self._key_rate = key_rate_per_sec
        self._key_burst = float(key_burst)
        self._max_keys = max_keys
        self._clock = clock
        self._lock = threading.Lock()
        now = clock()
        self._global = _Bucket(tokens=self._global_burst, updated=now)
        self._keys: OrderedDict[str, _Bucket] = OrderedDict()

    @staticmethod
    def _refill(bucket: _Bucket, rate: float, burst: float, now: float) -> None:
        elapsed = max(0.0, now - bucket.updated)
        bucket.tokens = min(burst, bucket.tokens + elapsed * rate)
        bucket.updated = now

    def allow(self, key: str) -> bool:
        """Admit one request for ``key``; False when either bucket is empty."""
        with self._lock:
            now = self._clock()
            self._refill(self._global, self._global_rate, self._global_burst, now)
            bucket = self._keys.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self._key_burst, updated=now)
                self._keys[key] = bucket
                if len(self._keys) > self._max_keys:
                    self._keys.popitem(last=False)
            else:
                self._keys.move_to_end(key)
                self._refill(bucket, self._key_rate, self._key_burst, now)
            if self._global.tokens < 1.0 or bucket.tokens < 1.0:
                return False
            self._global.tokens -= 1.0
            bucket.tokens -= 1.0
            return True

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._keys)
