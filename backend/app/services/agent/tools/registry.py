import logging
from datetime import UTC
from typing import Any

from app.core.errors import CollegeAPIError, NotAuthenticated
from app.core.principal import Role
from app.db.repository import PendingActionRepository
from app.services.agent.tools.base import ActionTool, RuleViolation, Tool, ToolContext, schema, to_spec
from app.services.agent.tools.common import COMMON_TOOLS
from app.services.agent.tools.public import PUBLIC_TOOLS
from app.services.agent.tools.student import STUDENT_TOOLS
from app.services.agent.tools.teacher import TEACHER_TOOLS

logger = logging.getLogger(__name__)

CONFIRM = "confirm_action"
CANCEL = "cancel_action"
_CONFIRM_SPECS = [
    {
        "type": "function",
        "function": {
            "name": CONFIRM,
            "description": "Submit the pending action. Call ONLY after the user clearly says yes to the summary you read out.",
            "parameters": schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": CANCEL,
            "description": "Discard the pending action when the user says no or changes their mind.",
            "parameters": schema(),
        },
    },
]

ALL_TOOLS: list[Tool] = [*COMMON_TOOLS, *PUBLIC_TOOLS, *STUDENT_TOOLS, *TEACHER_TOOLS]


class ToolRegistry:
    """Role-scoped tools. A role never sees, and can never call, tools outside its set."""

    def __init__(self, pending: PendingActionRepository, tools: list[Tool] | None = None):
        self._pending = pending
        self._by_role: dict[Role, dict[str, Tool]] = {role: {} for role in Role}
        for tool in tools or ALL_TOOLS:
            for role in tool.roles:
                self._by_role[role][tool.name] = tool

    def specs_for(self, role: Role) -> list[dict[str, Any]]:
        tools = self._by_role[role].values()
        specs = [to_spec(t) for t in tools]
        if any(isinstance(t, ActionTool) for t in tools):
            specs.extend(_CONFIRM_SPECS)
        return specs

    def names_for(self, role: Role) -> set[str]:
        return set(self._by_role[role])

    async def execute(self, ctx: ToolContext, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == CONFIRM:
                return await self._confirm(ctx)
            if name == CANCEL:
                await self._pending.discard(ctx.conversation_id)
                return {"status": "cancelled"}
            tool = self._by_role[ctx.principal.role].get(name)
            if tool is None:
                return {
                    "status": "not_available",
                    "reason": "That is not available here. Signed-in features need login.",
                }
            if isinstance(tool, ActionTool):
                prepared = await tool.prepare(ctx, args)
                await self._pending.replace(ctx.conversation_id, tool.name, prepared.payload, prepared.summary)
                return {
                    "status": "awaiting_confirmation",
                    "summary": prepared.summary,
                    "warnings": prepared.warnings,
                    "next_step": "Read the summary and any warnings to the user, then ask them to say yes to confirm.",
                }
            return {"status": "ok", "data": await tool.run(ctx, args)}
        except RuleViolation as exc:
            return {"status": "not_allowed", "reason": str(exc)}
        except NotAuthenticated:
            raise
        except CollegeAPIError as exc:
            if exc.upstream_status == 401 and ctx.principal.is_authenticated:
                raise NotAuthenticated("Your session has expired. Please log in again.") from exc
            return {"status": "failed", "reason": exc.message}
        except ValueError as exc:
            return {"status": "invalid_input", "reason": str(exc)}

    async def _confirm(self, ctx: ToolContext) -> dict[str, Any]:
        action = await self._pending.current(ctx.conversation_id)
        if action is None:
            return {
                "status": "nothing_to_confirm",
                "reason": "There is no pending action, or it expired. Ask the user to repeat the request.",
            }
        created = action.created_at if action.created_at.tzinfo else action.created_at.replace(tzinfo=UTC)
        if created >= ctx.turn_started_at:
            return {
                "status": "needs_user_confirmation",
                "reason": "The user has not confirmed yet. Read the summary and ask them to say yes.",
                "summary": action.summary,
            }
        tool = self._by_role[ctx.principal.role].get(action.tool)
        if not isinstance(tool, ActionTool):
            return {"status": "not_available"}
        if not await self._pending.consume(action.id):
            return {"status": "already_done", "reason": "This action was already submitted."}
        result = await tool.execute(ctx, action.payload, action.id)
        logger.info("Action %s executed for %s", tool.name, ctx.principal.owner_key)
        return {"status": "done", "action": action.summary, "result": result}

    async def pending_summary(self, conversation_id: str) -> str | None:
        action = await self._pending.current(conversation_id)
        return action.summary if action else None
