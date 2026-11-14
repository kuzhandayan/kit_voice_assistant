from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    login_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class MeOut(BaseModel):
    role: str
    user_id: int | None = None
    login_id: str | None = None
    name: str | None = None
    profile: dict[str, Any] = {}


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = Field(default=None, max_length=32)


class TurnOut(BaseModel):
    conversation_id: str | None
    transcript: str
    reply: str
    reply_message_id: int | None
    audio_url: str | None
    provider: str | None = None
    tools: list[dict[str, Any]] = []
    stt_provider: str | None = None


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]
