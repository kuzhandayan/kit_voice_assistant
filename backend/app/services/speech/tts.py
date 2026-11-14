import os

import edge_tts
import httpx

from app.core.config import Settings
from app.services.resilience import Attempt, FallbackResult, with_fallback


class TextToSpeech:
    """Edge neural voice first (free, no key), Deepgram Aura as fallback. Returns MP3 bytes."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self._settings = settings
        self._http = http

    async def _edge(self, text: str) -> bytes:
        chunks: list[bytes] = []
        communicate = edge_tts.Communicate(
            text, self._settings.edge_tts_voice, rate="+5%", proxy=os.environ.get("HTTPS_PROXY")
        )
        async for item in communicate.stream():
            if item["type"] == "audio":
                chunks.append(item["data"])
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
