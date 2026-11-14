import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import ProviderUnavailable
from app.services.agent.prompts import build_system_prompt
from app.services.agent.tools.base import ToolContext
from app.services.agent.tools.common import audience_for
from app.services.agent.tools.registry import CANCEL, CONFIRM, ToolRegistry
from app.services.llm.router import LLMRouter, tool_result_json

logger = logging.getLogger(__name__)

MAX_TOOL_RESULT_CHARS = 3500
FALLBACK_REPLY = "Sorry, I'm having trouble right now. Please try again in a moment."
_MARKDOWN = re.compile(r"[*_#`>|]+")
_BULLET = re.compile(r"^\s*[-•]\s+", re.MULTILINE)
_YES = re.compile(
    r"^(yes|yeah|yep|yup|sure|ok|okay|confirm|confirmed|go ahead|please do|do it|submit|submit it|haan|correct|yes please|yes go ahead|yes submit it|ok submit)$"
)
_NO = re.compile(r"^(no|nope|cancel|cancel it|don't|do not|stop|no thanks|leave it|never mind)$")


@dataclass
class ToolTrace:
    name: str
    arguments: dict[str, Any]
    status: str


@dataclass
class AgentResult:
    reply: str
    provider: str | None = None
    tools: list[ToolTrace] = field(default_factory=list)


def to_speech(text: str) -> str:
    text = _BULLET.sub("", text or "")
    text = _MARKDOWN.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_args(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _intent(text: str) -> str | None:
    """Clear yes/no answers to a pending action are handled in code, never guessed by the LLM."""
    cleaned = re.sub(r"[^a-z' ]", "", text.lower()).strip()
    if _YES.match(cleaned):
        return "yes"
    if _NO.match(cleaned):
        return "no"
    return None


def describe_outcome(output: dict[str, Any]) -> str:
    status = output.get("status")
    if status == "done":
        result = output.get("result") or {}
        ref = next((v for k, v in result.items() if k.endswith("_id") and v), None)
        state = result.get("status")
        parts = ["Done, that's submitted."]
        if ref:
            parts.append(f"Your reference number is {ref}.")
        if state and state not in {"submitted", "done"}:
            parts.append(f"Its status is {str(state).replace('_', ' ')}.")
        return " ".join(parts)
    if status == "cancelled":
        return "Okay, I've cancelled that. Nothing was submitted."
    if status == "already_done":
        return "That was already submitted, so I didn't send it again."
    if status == "nothing_to_confirm":
        return "There's nothing waiting to submit right now. What would you like to do?"
    return f"Sorry, that couldn't be completed: {output.get('reason', 'please try again')}."


class Agent:
    """Tool-calling loop: the LLM decides which tools to call and in which order."""

    def __init__(self, llm: LLMRouter, registry: ToolRegistry, max_steps: int = 6):
        self._llm = llm
        self._registry = registry
        self._max_steps = max_steps

    @staticmethod
    def _notices(ctx: ToolContext) -> list[str]:
        return ctx.knowledge.overriding_titles(audience_for(ctx))

    async def run(self, ctx: ToolContext, history: list[dict[str, str]], user_text: str) -> AgentResult:
        today = await ctx.today()
        pending = await self._registry.pending_summary(ctx.conversation_id)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": build_system_prompt(ctx.principal, today, pending, self._notices(ctx))},
            *history,
            {"role": "user", "content": user_text},
        ]
        tools = self._registry.specs_for(ctx.principal.role)
        result = AgentResult(reply=FALLBACK_REPLY)
        intent = _intent(user_text) if pending else None
        if intent:
            name = CONFIRM if intent == "yes" else CANCEL
            output = await self._registry.execute(ctx, name, {})
            result.tools.append(ToolTrace(name, {}, str(output.get("status"))))
            result.provider = "rules"
            result.reply = describe_outcome(output)
            return result
        try:
            for _ in range(self._max_steps):
                completion = await self._llm.complete(messages, tools)
                message = completion.value
                result.provider = completion.provider
                if not message.tool_calls:
                    result.reply = to_speech(message.content or "") or FALLBACK_REPLY
                    return result
                messages.append(
                    {
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [
                            {
                                "id": c.id,
                                "type": "function",
                                "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"},
                            }
                            for c in message.tool_calls
                        ],
                    }
                )
                for call in message.tool_calls:
                    args = _parse_args(call.function.arguments)
                    output = await self._registry.execute(ctx, call.function.name, args)
                    result.tools.append(ToolTrace(call.function.name, args, str(output.get("status"))))
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": tool_result_json(output, MAX_TOOL_RESULT_CHARS),
                        }
                    )
            result.reply = "Sorry, that took longer than expected. Could you ask again more simply?"
        except ProviderUnavailable as exc:
            logger.error("All LLM providers failed: %s", exc.failures)
        return result
