from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI

from app.core.config import Settings
from app.services.resilience import Attempt, FallbackResult, with_fallback

VOCABULARY_HINT = (
    "KIT, Knotopian Institute of Technology, B.Tech Computer Science and Engineering, Electronics and Communication "
    "Engineering, Mechanical Engineering, attendance, on-duty, OD, personal leave, medical leave, "
    "internal assessment, B.Tech, M.Tech, CSE, ECE, MECH, CGPA, arrears, placement, Zoho, TCS, Freshworks, DBMS, normalisation."
)


@dataclass(frozen=True)
class Audio:
    data: bytes
    filename: str
    content_type: str


class SpeechToText:
    """Groq Whisper first, Deepgram as fallback. Browser speech recognition is never used."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self._settings = settings
        self._http = http
        self._groq = (
            AsyncOpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1", max_retries=0)
            if settings.groq_api_key
            else None
        )

    async def _groq_transcribe(self, audio: Audio) -> str:
        assert self._groq
        result = await self._groq.audio.transcriptions.create(
            model=self._settings.groq_stt_model,
            file=(audio.filename, audio.data, audio.content_type),
            language="en",
            prompt=VOCABULARY_HINT,
            temperature=0,
        )
        return result.text

    async def _deepgram_transcribe(self, audio: Audio) -> str:
        response = await self._http.post(
            "https://api.deepgram.com/v1/listen",
            params={"model": self._settings.deepgram_stt_model, "language": "en", "smart_format": "true"},
            headers={"Authorization": f"Token {self._settings.deepgram_api_key}", "Content-Type": audio.content_type},
            content=audio.data,
        )
        response.raise_for_status()
        return response.json()["results"]["channels"][0]["alternatives"][0]["transcript"]

    async def transcribe(self, audio: Audio) -> FallbackResult[str]:
        attempts: list[Attempt[str]] = []
        if self._groq:
            attempts.append(Attempt("groq-whisper", lambda: self._groq_transcribe(audio)))
        if self._settings.deepgram_api_key:
            attempts.append(Attempt("deepgram", lambda: self._deepgram_transcribe(audio)))
        return await with_fallback(attempts, timeout=self._settings.stt_timeout_seconds, label="STT")
