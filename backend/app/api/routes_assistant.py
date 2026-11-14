import re

from fastapi import APIRouter, File, Form, Response, UploadFile

from app.api.deps import LimitedPrincipalDep, PrincipalDep, ServicesDep
from app.api.schemas import ChatIn, TurnOut
from app.core.errors import AppError, NotFound
from app.services.speech.stt import Audio

router = APIRouter(prefix="/api", tags=["assistant"])

ALLOWED_AUDIO = ("audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav", "audio/aac")
NOT_HEARD = "Sorry, I didn't catch that. Could you say it again?"
_HAS_WORD = re.compile(r"[A-Za-z0-9]{2,}")
_WHISPER_NOISE = {"thank you.", "thanks for watching!", "you", "bye.", "."}


def _audio_url(message_id: int | None) -> str | None:
    return f"/api/voice/tts/{message_id}" if message_id else None


@router.post("/chat/turn", response_model=TurnOut)
async def chat_turn(body: ChatIn, principal: LimitedPrincipalDep, services: ServicesDep) -> TurnOut:
    result = await services.conversation_service.handle(principal, body.conversation_id, body.text.strip())
    return TurnOut(
        conversation_id=result.conversation_id,
        transcript=result.user_text,
        reply=result.reply,
        reply_message_id=result.reply_message_id,
        audio_url=_audio_url(result.reply_message_id),
        provider=result.provider,
        tools=result.tools,
    )


@router.post("/voice/turn", response_model=TurnOut)
async def voice_turn(
    principal: LimitedPrincipalDep,
    services: ServicesDep,
    audio: UploadFile = File(...),
    conversation_id: str | None = Form(default=None, max_length=32),
) -> TurnOut:
    content_type = (audio.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_AUDIO:
        raise AppError("Unsupported audio format.", status_code=415, code="unsupported_audio")
    data = await audio.read(services.settings.max_audio_mb * 1024 * 1024 + 1)
    if len(data) > services.settings.max_audio_mb * 1024 * 1024:
        raise AppError("Recording is too long.", status_code=413, code="audio_too_large")
    if len(data) < 1000:
        return TurnOut(
            conversation_id=conversation_id,
            transcript="",
            reply=NOT_HEARD,
            reply_message_id=None,
            audio_url="/api/voice/tts/system/not-heard",
        )
    extension = content_type.split("/")[-1].replace("x-", "").replace("mpeg", "mp3")
    stt = await services.stt.transcribe(Audio(data, f"speech.{extension}", content_type))
    transcript = stt.value.strip()
    if not _HAS_WORD.search(transcript) or transcript.lower() in _WHISPER_NOISE:
        return TurnOut(
            conversation_id=conversation_id,
            transcript=transcript,
            reply=NOT_HEARD,
            reply_message_id=None,
            audio_url="/api/voice/tts/system/not-heard",
            stt_provider=stt.provider,
        )
    result = await services.conversation_service.handle(
        principal, conversation_id, transcript[: services.settings.max_text_chars], extra_meta={"stt": stt.provider}
    )
    return TurnOut(
        conversation_id=result.conversation_id,
        transcript=transcript,
        reply=result.reply,
        reply_message_id=result.reply_message_id,
        audio_url=_audio_url(result.reply_message_id),
        provider=result.provider,
        tools=result.tools,
        stt_provider=stt.provider,
    )


SYSTEM_PHRASES = {"not-heard": NOT_HEARD, "greeting": "Hi! I'm the KIT assistant. How can I help you today?"}
_phrase_cache: dict[str, bytes] = {}


def _mp3(data: bytes, provider: str) -> Response:
    return Response(
        data, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600", "X-TTS-Provider": provider}
    )


@router.get("/voice/tts/system/{phrase}")
async def system_phrase(phrase: str, services: ServicesDep) -> Response:
    text = SYSTEM_PHRASES.get(phrase)
    if text is None:
        raise NotFound("Unknown phrase.")
    if phrase not in _phrase_cache:
        _phrase_cache[phrase] = (await services.tts.synthesize(text)).value
    return _mp3(_phrase_cache[phrase], "cache")


@router.get("/voice/tts/{message_id}")
async def message_audio(message_id: int, principal: PrincipalDep, services: ServicesDep) -> Response:
    message = await services.conversations.get_owned_message(principal.owner_key, message_id)
    if message is None or message.role != "assistant":
        raise NotFound("Message not found.")
    result = await services.tts.synthesize(message.content)
    return _mp3(result.value, result.provider)
