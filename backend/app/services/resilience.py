import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from app.core.errors import ProviderUnavailable

logger = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(frozen=True)
class Attempt(Generic[T]):
    name: str
    call: Callable[[], Awaitable[T]]


@dataclass(frozen=True)
class FallbackResult(Generic[T]):
    provider: str
    value: T
    latency_ms: int


async def with_fallback(attempts: Sequence[Attempt[T]], *, timeout: float, label: str) -> FallbackResult[T]:
    if not attempts:
        raise ProviderUnavailable(f"No {label} provider is configured")
    failures: list[str] = []
    for attempt in attempts:
        started = time.perf_counter()
        try:
            value = await asyncio.wait_for(attempt.call(), timeout)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - any provider failure moves to the next provider
            logger.warning("%s provider '%s' failed: %s: %s", label, attempt.name, type(exc).__name__, exc)
            failures.append(f"{attempt.name}: {type(exc).__name__}")
            continue
        latency = int((time.perf_counter() - started) * 1000)
        logger.info("%s served by '%s' in %d ms", label, attempt.name, latency)
        return FallbackResult(attempt.name, value, latency)
    raise ProviderUnavailable(f"All {label} providers failed", failures=failures)
