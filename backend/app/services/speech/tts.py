import asyncio
import logging
import os
from collections.abc import AsyncIterator, Callable

import edge_tts
import httpx

from app.core.config import Settings
from app.services.resilience import Attempt, FallbackResult, with_fallback

logger = logging.getLogger(__name__)
FIRST_CHUNK_TIMEOUT_SECONDS = 5.0


class TextToSpeech:
    """Edge neural voice first (free, no key), Deepgram Aura as fallback. MP3 output, streamed."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self._settings = settings
        self._http = http

    def _edge_chunks(self, text: str) -> AsyncIterator[bytes]:
        communicate = edge_tts.Communicate(
            text, self._settings.edge_tts_voice, rate="+5%", proxy=os.environ.get("HTTPS_PROXY")
        )

        async def generate() -> AsyncIterator[bytes]:
            async for item in communicate.stream():
                if item["type"] == "audio":
                    yield item["data"]

        return generate()

    def _deepgram_chunks(self, text: str) -> AsyncIterator[bytes]:
        async def generate() -> AsyncIterator[bytes]:
            async with self._http.stream(
                "POST",
                "https://api.deepgram.com/v1/speak",
                params={"model": self._settings.deepgram_tts_model, "encoding": "mp3"},
                headers={"Authorization": f"Token {self._settings.deepgram_api_key}"},
                json={"text": text},
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    yield chunk

        return generate()

    def _sources(self) -> list[tuple[str, Callable[[str], AsyncIterator[bytes]]]]:
        sources: list[tuple[str, Callable[[str], AsyncIterator[bytes]]]] = [("edge-tts", self._edge_chunks)]
        if self._settings.deepgram_api_key:
            sources.append(("deepgram-aura", self._deepgram_chunks))
        return sources

    async def synthesize(self, text: str) -> FallbackResult[bytes]:
        attempts = [Attempt(name, lambda open_=open_: _collect(open_(text))) for name, open_ in self._sources()]
        return await with_fallback(attempts, timeout=self._settings.tts_timeout_seconds, label="TTS")

    async def stream(self, text: str) -> tuple[str, AsyncIterator[bytes]]:
        """Starts playback on the first chunk. Each voice gets a few seconds to produce it, then the next one is tried."""
        for name, open_stream in self._sources():
            chunks = open_stream(text)
            try:
                first = await asyncio.wait_for(anext(chunks), FIRST_CHUNK_TIMEOUT_SECONDS)
            except Exception as exc:  # noqa: BLE001 - any failure, including timeout, moves to the next voice
                logger.warning("TTS stream '%s' failed before the first chunk: %s", name, type(exc).__name__)
                await chunks.aclose()
                continue
            return name, _prepend(first, chunks)
        result = await self.synthesize(text)
        return result.provider, _prepend(result.value, _empty())

    async def warm_up(self, phrases: dict[str, str]) -> dict[str, bytes]:
        """Pre-generates fixed phrases at startup; this also opens the voice connection early."""
        cache: dict[str, bytes] = {}
        for key, text in phrases.items():
            try:
                cache[key] = (await self.synthesize(text)).value
            except Exception as exc:  # noqa: BLE001 - warm-up is best effort
                logger.warning("TTS warm-up failed for '%s': %s", key, type(exc).__name__)
        return cache


async def _collect(chunks: AsyncIterator[bytes]) -> bytes:
    data = b"".join([chunk async for chunk in chunks])
    if not data:
        raise RuntimeError("TTS returned no audio")
    return data


async def _prepend(first: bytes, rest: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    yield first
    async for chunk in rest:
        yield chunk


async def _empty() -> AsyncIterator[bytes]:
    return
    yield b""
