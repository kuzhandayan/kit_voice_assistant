from dataclasses import asdict, dataclass
from typing import Any

from app.core.principal import Principal
from app.db.repository import ConversationRepository
from app.services.agent.orchestrator import Agent
from app.services.agent.tools.base import ToolContext
from app.services.college.client import CollegeClient
from app.services.college.clock import CollegeClock
from app.services.knowledge.base import KnowledgeBase

HISTORY_TURNS = 8


@dataclass(frozen=True)
class TurnResult:
    conversation_id: str
    user_text: str
    reply: str
    reply_message_id: int
    provider: str | None
    tools: list[dict[str, Any]]


class ConversationService:
    """One user turn: load history, run the agent, save both messages. Shared by text and voice."""

    def __init__(
        self,
        agent: Agent,
        repo: ConversationRepository,
        college: CollegeClient,
        clock: CollegeClock,
        knowledge: KnowledgeBase,
    ):
        self._agent = agent
        self._repo = repo
        self._college = college
        self._clock = clock
        self._knowledge = knowledge

    async def handle(
        self, principal: Principal, conversation_id: str | None, text: str, *, extra_meta: dict[str, Any] | None = None
    ) -> TurnResult:
        conversation = await self._repo.get_or_create(principal.owner_key, conversation_id, text)
        recent = await self._repo.recent_messages(conversation.id, HISTORY_TURNS)
        history = [{"role": m.role, "content": m.content} for m in recent if m.role in {"user", "assistant"}]
        ctx = ToolContext(principal, self._college, self._clock, self._knowledge, conversation.id)
        result = await self._agent.run(ctx, history, text)
        tools = [asdict(t) for t in result.tools]
        saved = await self._repo.add_messages(
            conversation.id,
            [
                ("user", text, extra_meta or {}),
                ("assistant", result.reply, {"provider": result.provider, "tools": tools}),
            ],
        )
        return TurnResult(conversation.id, text, result.reply, saved[-1].id, result.provider, tools)
