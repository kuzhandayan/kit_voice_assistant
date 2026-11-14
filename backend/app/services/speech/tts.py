import asyncio
import os
from collections.abc import AsyncIterator

import edge_tts
import httpx

from app.core.config import Settings
from app.services.resilience import Attempt, FallbackResult, with_fallback

FIRST_CHUNK_TIMEOUT_SECONDS = 4.0


class TextToSpeech:
    """Edge neural voice first (free, no key), Deepgram Aura as fallback. MP3 output."""

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

    async def _edge(self, text: str) -> bytes:
        chunks = [chunk async for chunk in self._edge_chunks(text)]
        if not chunks:
            raise RuntimeError("Edge TTS returned no audio")
        return b"".join(chunks)

    async def _deepgram(self, text: str) -> bytes:
        response = await self._http.post(
            "https://api.deepgram.com/v1/speak",
            params={"model": self._settings.deepgram_tts_model, "encoding": "mp3"},
            headers={"Authorization": f"Token {self._settings.deepgram_api_key}"},
            json={"text": text},
        )
        response.raise_for_status()
        return response.content

    async def synthesize(self, text: str) -> FallbackResult[bytes]:
        attempts: list[Attempt[bytes]] = [Attempt("edge-tts", lambda: self._edge(text))]
        if self._settings.deepgram_api_key:
            attempts.append(Attempt("deepgram-aura", lambda: self._deepgram(text)))
        return await with_fallback(attempts, timeout=self._settings.tts_timeout_seconds, label="TTS")

    async def stream(self, text: str) -> tuple[str, AsyncIterator[bytes]]:
        """Streams Edge audio as it is generated so playback starts on the first chunk.
        Falls back to a full synthesis (Deepgram) if Edge can't produce its first chunk in time."""
        chunks = self._edge_chunks(text)
        try:
            first = await asyncio.wait_for(anext(chunks), FIRST_CHUNK_TIMEOUT_SECONDS)
        except (TimeoutError, Exception):  # noqa: BLE001 - any Edge failure falls back
            await chunks.aclose()
            result = await self.synthesize_fallback(text)

            async def single() -> AsyncIterator[bytes]:
                yield result.value

            return result.provider, single()

        async def rest() -> AsyncIterator[bytes]:
            yield first
            async for chunk in chunks:
                yield chunk

        return "edge-tts", rest()

    async def synthesize_fallback(self, text: str) -> FallbackResult[bytes]:
        if not self._settings.deepgram_api_key:
            return await self.synthesize(text)
        return await with_fallback(
            [Attempt("deepgram-aura", lambda: self._deepgram(text))],
            timeout=self._settings.tts_timeout_seconds,
            label="TTS",
        )
