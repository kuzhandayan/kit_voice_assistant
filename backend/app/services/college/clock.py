import logging
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.errors import CollegeAPIError
from app.services.college.client import CollegeClient

logger = logging.getLogger(__name__)


class CollegeClock:
    """Single source of 'today'. The college system runs on its own date, not the server clock."""

    def __init__(self, client: CollegeClient, timezone: str = "Asia/Kolkata", ttl_seconds: int = 60):
        self._client = client
        self._tz = ZoneInfo(timezone)
        self._ttl = ttl_seconds
        self._cached: date | None = None
        self._fetched_at = 0.0

    async def today(self) -> date:
        if self._cached and time.monotonic() - self._fetched_at < self._ttl:
            return self._cached
        try:
            data = await self._client.today()
            self._cached = date.fromisoformat(data["date"])
            self._fetched_at = time.monotonic()
        except (CollegeAPIError, KeyError, ValueError) as exc:
            logger.warning("Could not read college date, using local date: %s", exc)
            return self._cached or datetime.now(self._tz).date()
        return self._cached
