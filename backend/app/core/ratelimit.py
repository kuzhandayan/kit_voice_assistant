import time
from collections import defaultdict, deque

from app.core.errors import RateLimited


class RateLimiter:
    """Sliding one-minute window per key. In-memory: fine for a single instance."""

    def __init__(self, per_minute: int):
        self._limit = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= self._limit:
            raise RateLimited("You're sending requests too quickly. Please wait a moment.")
        hits.append(now)
