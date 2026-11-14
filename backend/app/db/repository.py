from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Message, PendingAction, UserSession, utcnow


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class SessionRepository:
    def __init__(self, factory: async_sessionmaker[AsyncSession]):
        self._factory = factory

    async def create(self, session_id: str, principal: dict[str, Any], ttl_seconds: int) -> None:
        async with self._factory() as db:
            db.add(
                UserSession(id=session_id, principal=principal, expires_at=utcnow() + timedelta(seconds=ttl_seconds))
            )
            await db.commit()

    async def get(self, session_id: str) -> dict[str, Any] | None:
        async with self._factory() as db:
            row = await db.get(UserSession, session_id)
            if row is None or _aware(row.expires_at) <= utcnow():
                return None
            return row.principal

    async def delete(self, session_id: str) -> None:
        async with self._factory() as db:
            await db.execute(delete(UserSession).where(UserSession.id == session_id))
            await db.commit()


class ConversationRepository:
    def __init__(self, factory: async_sessionmaker[AsyncSession]):
        self._factory = factory

    async def get_or_create(self, owner_key: str, conversation_id: str | None, first_text: str) -> Conversation:
        async with self._factory() as db:
            if conversation_id:
                found = await db.get(Conversation, conversation_id)
                if found and found.owner_key == owner_key:
                    return found
            conversation = Conversation(owner_key=owner_key, title=first_text.strip()[:80] or "New conversation")
            db.add(conversation)
            await db.commit()
            return conversation

    async def recent_messages(self, conversation_id: str, limit: int) -> list[Message]:
        async with self._factory() as db:
            rows = await db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.id.desc())
                .limit(limit)
            )
            return list(reversed(rows.all()))

    async def add_messages(self, conversation_id: str, items: list[tuple[str, str, dict[str, Any]]]) -> list[Message]:
        async with self._factory() as db:
            messages = [Message(conversation_id=conversation_id, role=r, content=c, meta=m) for r, c, m in items]
            db.add_all(messages)
            await db.execute(update(Conversation).where(Conversation.id == conversation_id).values(updated_at=utcnow()))
            await db.commit()
            return messages

    async def list_for_owner(self, owner_key: str, limit: int = 50) -> list[Conversation]:
        async with self._factory() as db:
            rows = await db.scalars(
                select(Conversation)
                .where(Conversation.owner_key == owner_key)
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
            )
            return list(rows.all())

    async def get_owned(self, owner_key: str, conversation_id: str) -> tuple[Conversation, list[Message]] | None:
        async with self._factory() as db:
            conversation = await db.get(Conversation, conversation_id)
            if conversation is None or conversation.owner_key != owner_key:
                return None
            rows = await db.scalars(
                select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
            )
            return conversation, list(rows.all())

    async def get_owned_message(self, owner_key: str, message_id: int) -> Message | None:
        async with self._factory() as db:
            message = await db.get(Message, message_id)
            if message is None:
                return None
            conversation = await db.get(Conversation, message.conversation_id)
            return message if conversation and conversation.owner_key == owner_key else None


class PendingActionRepository:
    def __init__(self, factory: async_sessionmaker[AsyncSession], ttl_seconds: int = 300):
        self._factory = factory
        self._ttl = ttl_seconds

    async def replace(self, conversation_id: str, tool: str, payload: dict[str, Any], summary: str) -> PendingAction:
        async with self._factory() as db:
            await db.execute(
                delete(PendingAction).where(
                    PendingAction.conversation_id == conversation_id, PendingAction.consumed_at.is_(None)
                )
            )
            action = PendingAction(
                conversation_id=conversation_id,
                tool=tool,
                payload=payload,
                summary=summary,
                expires_at=utcnow() + timedelta(seconds=self._ttl),
            )
            db.add(action)
            await db.commit()
            return action

    async def current(self, conversation_id: str) -> PendingAction | None:
        async with self._factory() as db:
            row = await db.scalar(
                select(PendingAction)
                .where(PendingAction.conversation_id == conversation_id, PendingAction.consumed_at.is_(None))
                .order_by(PendingAction.created_at.desc())
                .limit(1)
            )
            if row is None or _aware(row.expires_at) <= utcnow():
                return None
            return row

    async def consume(self, action_id: str) -> bool:
        """Atomically marks the action used. False if it was already consumed (double 'yes')."""
        async with self._factory() as db:
            result = await db.execute(
                update(PendingAction)
                .where(PendingAction.id == action_id, PendingAction.consumed_at.is_(None))
                .values(consumed_at=utcnow())
            )
            await db.commit()
            return result.rowcount == 1

    async def discard(self, conversation_id: str) -> None:
        async with self._factory() as db:
            await db.execute(
                delete(PendingAction).where(
                    PendingAction.conversation_id == conversation_id, PendingAction.consumed_at.is_(None)
                )
            )
            await db.commit()
