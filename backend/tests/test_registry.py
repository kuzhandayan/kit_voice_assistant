from datetime import date

import pytest

from app.core.principal import Principal, Role, public_principal
from app.db.database import create_engine, create_session_factory, init_db
from app.db.repository import ConversationRepository, PendingActionRepository
from app.services.agent.tools.base import ActionTool, Prepared, RuleViolation, ToolContext, schema
from app.services.agent.tools.registry import ToolRegistry


class FakeClock:
    async def today(self) -> date:
        return date(2026, 11, 21)


@pytest.fixture
async def repos():
    engine = create_engine("sqlite:///:memory:")
    await init_db(engine)
    factory = create_session_factory(engine)
    yield ConversationRepository(factory), PendingActionRepository(factory)
    await engine.dispose()


def make_context(principal: Principal, conversation_id: str) -> ToolContext:
    return ToolContext(principal, college=None, clock=FakeClock(), knowledge=None, conversation_id=conversation_id)  # type: ignore[arg-type]


def test_public_role_never_sees_student_or_teacher_tools(repos):
    registry = ToolRegistry(repos[1])
    public = registry.names_for(Role.PUBLIC)
    assert "get_my_attendance" not in public
    assert "approve_request" not in public
    assert "submit_admission_application" in public
    assert "create_leave_or_od_request" in registry.names_for(Role.STUDENT)
    assert "approve_request" not in registry.names_for(Role.STUDENT)


async def test_public_user_cannot_call_student_tool(repos):
    conversations, pending = repos
    conversation = await conversations.get_or_create("visitor:abc", None, "hi")
    result = await ToolRegistry(pending).execute(
        make_context(public_principal("abc"), conversation.id), "get_my_attendance", {}
    )
    assert result["status"] == "not_available"


async def test_action_needs_confirmation_and_runs_once(repos):
    conversations, pending = repos
    calls: list[str] = []

    async def prepare(ctx, args):
        if not args.get("ok"):
            raise RuleViolation("blocked by rule")
        return Prepared("Do the thing", {"value": 1})

    async def execute(ctx, payload, key):
        calls.append(key)
        return {"id": 99}

    tool = ActionTool("do_thing", "test", schema(), frozenset(Role), prepare, execute)
    registry = ToolRegistry(pending, [tool])
    conversation = await conversations.get_or_create("visitor:abc", None, "hi")
    ctx = make_context(public_principal("abc"), conversation.id)

    assert (await registry.execute(ctx, "do_thing", {}))["status"] == "not_allowed"
    assert (await registry.execute(ctx, "confirm_action", {}))["status"] == "nothing_to_confirm"

    prepared = await registry.execute(ctx, "do_thing", {"ok": True})
    assert prepared["status"] == "awaiting_confirmation"
    same_turn = await registry.execute(ctx, "confirm_action", {})
    assert same_turn["status"] == "needs_user_confirmation"
    assert calls == []

    ctx = make_context(public_principal("abc"), conversation.id)
    done = await registry.execute(ctx, "confirm_action", {})
    assert done["status"] == "done" and done["result"] == {"id": 99}
    assert (await registry.execute(ctx, "confirm_action", {}))["status"] == "nothing_to_confirm"
    assert len(calls) == 1


async def test_cancel_discards_pending_action(repos):
    conversations, pending = repos

    async def prepare(ctx, args):
        return Prepared("x", {})

    async def execute(ctx, payload, key):
        raise AssertionError("must not run")

    registry = ToolRegistry(pending, [ActionTool("do_thing", "t", schema(), frozenset(Role), prepare, execute)])
    conversation = await conversations.get_or_create("visitor:abc", None, "hi")
    ctx = make_context(public_principal("abc"), conversation.id)
    await registry.execute(ctx, "do_thing", {})
    ctx = make_context(public_principal("abc"), conversation.id)
    assert (await registry.execute(ctx, "cancel_action", {}))["status"] == "cancelled"
    assert (await registry.execute(ctx, "confirm_action", {}))["status"] == "nothing_to_confirm"


async def test_history_is_scoped_to_owner(repos):
    conversations, _ = repos
    mine = await conversations.get_or_create("user:1", None, "my question")
    await conversations.add_messages(mine.id, [("user", "q", {}), ("assistant", "a", {})])
    assert await conversations.get_owned("user:2", mine.id) is None
    other = await conversations.get_or_create("user:2", mine.id, "trying to reuse id")
    assert other.id != mine.id
    message_id = (await conversations.recent_messages(mine.id, 5))[-1].id
    assert await conversations.get_owned_message("user:2", message_id) is None


async def test_college_token_is_encrypted_at_rest(tmp_path):
    from sqlalchemy import select

    from app.db.models import UserSession
    from app.db.repository import SessionRepository

    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 's.db'}")
    await init_db(engine)
    factory = create_session_factory(engine)
    sessions = SessionRepository(factory, "secret-0123456789abcdef")
    await sessions.create("abc", {"role": "student", "college_token": "jwt-123"}, 60)

    async with factory() as db:
        stored = (await db.execute(select(UserSession))).scalar_one().principal
    assert stored["college_token"] != "jwt-123"
    assert (await sessions.get("abc"))["college_token"] == "jwt-123"
    assert await SessionRepository(factory, "another-secret-000000").get("abc") is None
    await engine.dispose()
