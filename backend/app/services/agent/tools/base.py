from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.core.errors import NotAuthenticated
from app.core.principal import Principal, Role
from app.services.college.client import CollegeClient
from app.services.college.clock import CollegeClock
from app.services.knowledge.base import KnowledgeBase


class RuleViolation(Exception):
    """A college rule blocks the request. The message is spoken to the user."""


@dataclass
class ToolContext:
    principal: Principal
    college: CollegeClient
    clock: CollegeClock
    knowledge: KnowledgeBase
    conversation_id: str
    turn_started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def token(self) -> str:
        if not self.principal.college_token:
            raise NotAuthenticated("Please log in to use this.")
        return self.principal.college_token

    async def today(self) -> date:
        return await self.clock.today()


@dataclass(frozen=True)
class Prepared:
    summary: str
    payload: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


ReadHandler = Callable[[ToolContext, dict[str, Any]], Awaitable[Any]]
PrepareHandler = Callable[[ToolContext, dict[str, Any]], Awaitable[Prepared]]
ExecuteHandler = Callable[[ToolContext, dict[str, Any], str], Awaitable[Any]]


@dataclass(frozen=True)
class ReadTool:
    name: str
    description: str
    parameters: dict[str, Any]
    roles: frozenset[Role]
    run: ReadHandler


@dataclass(frozen=True)
class ActionTool:
    """A write action. prepare() validates and summarises; execute() runs only after spoken confirmation."""

    name: str
    description: str
    parameters: dict[str, Any]
    roles: frozenset[Role]
    prepare: PrepareHandler
    execute: ExecuteHandler


Tool = ReadTool | ActionTool


def schema(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties or {}, "required": required or []}


def to_spec(tool: Tool | ReadTool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {"name": tool.name, "description": tool.description, "parameters": tool.parameters},
    }


def arg_str(args: dict[str, Any], key: str, *, required: bool = True, max_len: int = 300) -> str | None:
    value = args.get(key)
    if value is None or str(value).strip() == "":
        if required:
            raise ValueError(f"{key} is required")
        return None
    return str(value).strip()[:max_len]


def arg_int(args: dict[str, Any], key: str) -> int:
    try:
        return int(args[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a number") from exc


def arg_date(args: dict[str, Any], key: str, *, required: bool = True) -> date | None:
    raw = arg_str(args, key, required=required)
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise ValueError(f"{key} must be a date in YYYY-MM-DD format") from exc


STUDENT = frozenset({Role.STUDENT})
TEACHER = frozenset({Role.TEACHER})
PUBLIC = frozenset({Role.PUBLIC})
SIGNED_IN = frozenset({Role.STUDENT, Role.TEACHER})
EVERYONE = frozenset(Role)
