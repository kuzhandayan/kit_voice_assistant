"""The whole app over HTTP with a fake college system, LLM and speech services. No network, no keys."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.container import Services
from app.core.config import Settings
from app.core.errors import CollegeAPIError
from app.core.ratelimit import RateLimiter
from app.db.database import create_engine, create_session_factory, init_db
from app.db.repository import ConversationRepository, PendingActionRepository, SessionRepository
from app.services.agent.orchestrator import Agent
from app.services.agent.tools.registry import ToolRegistry
from app.services.college.clock import CollegeClock
from app.services.conversation import ConversationService
from app.services.knowledge.base import KnowledgeBase
from tests.fakes import FakeCollege, FakeLLM, FakeSTT, FakeTTS

AUDIO = ("speech.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 4000, "audio/webm")


def build_client(tmp_path, monkeypatch, **overrides) -> tuple[TestClient, FakeCollege, FakeLLM]:
    settings = Settings(database_url=f"sqlite:///{tmp_path}/test.db", **overrides)
    college, llm = FakeCollege(), FakeLLM()

    async def fake_services(_: Settings) -> Services:
        engine = create_engine(settings.database_url)
        await init_db(engine)
        factory = create_session_factory(engine)
        clock = CollegeClock(college)
        knowledge = KnowledgeBase(college, clock)
        conversations = ConversationRepository(factory)
        agent = Agent(llm, ToolRegistry(PendingActionRepository(factory)), settings.max_agent_steps)
        return Services(
            settings=settings,
            engine=engine,
            http=httpx.AsyncClient(),
            college=college,
            clock=clock,
            knowledge=knowledge,
            sessions=SessionRepository(factory),
            conversations=conversations,
            conversation_service=ConversationService(agent, conversations, college, clock, knowledge),
            stt=FakeSTT(),
            tts=FakeTTS(),
            llm=llm,
            rate_limiter=RateLimiter(settings.rate_limit_per_minute),
        )

    monkeypatch.setattr(main_module, "build_services", fake_services)
    return TestClient(main_module.create_app(settings)), college, llm


@pytest.fixture
def app(tmp_path, monkeypatch):
    client, college, llm = build_client(tmp_path, monkeypatch)
    with client:
        yield client, college, llm


def login(client: TestClient) -> None:
    assert client.post("/api/auth/login", json={"login_id": "arjun", "password": "Kit@2026"}).status_code == 200


def turn(client: TestClient, text: str, conversation_id: str | None = None) -> dict:
    response = client.post("/api/chat/turn", json={"text": text, "conversation_id": conversation_id})
    assert response.status_code == 200, response.text
    return response.json()


# Basics -------------------------------------------------------------------------------------------


def test_health_and_security_headers(app):
    client, _, _ = app
    response = client.get("/api/health")
    assert response.json()["status"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "microphone=(self)" in response.headers["permissions-policy"]


def test_public_home_has_college_and_courses(app):
    client, _, _ = app
    data = client.get("/api/public/home").json()
    assert data["college"]["code"] == "KIT" and len(data["courses"]) == 2


def test_visitor_gets_anonymous_cookie(app):
    client, _, _ = app
    response = client.get("/api/auth/me")
    assert response.json()["role"] == "public"
    assert "kit_visitor" in response.cookies


# Auth ---------------------------------------------------------------------------------------------


def test_wrong_password_is_rejected_without_detail(app):
    client, _, _ = app
    response = client.post("/api/auth/login", json={"login_id": "arjun", "password": "nope"})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid login ID or password."


def test_login_sets_httponly_session_and_never_returns_college_token(app):
    client, _, _ = app
    response = client.post("/api/auth/login", json={"login_id": "arjun", "password": "Kit@2026"})
    assert response.json()["role"] == "student" and response.json()["name"] == "Arjun K"
    assert "tok-arjun" not in response.text
    cookie = response.headers["set-cookie"].lower()
    assert "kit_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_logout_returns_to_public(app):
    client, _, _ = app
    login(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").json()["role"] == "public"


def test_empty_login_fields_fail_validation(app):
    client, _, _ = app
    response = client.post("/api/auth/login", json={"login_id": "", "password": ""})
    assert response.status_code == 422 and response.json()["error"]["code"] == "validation_error"


# Assistant: permissions -----------------------------------------------------------------------------


def test_public_visitor_cannot_reach_student_data_even_if_the_model_tries(app):
    client, _, llm = app
    data = turn(client, "what is my attendance")
    assert data["tools"][0]["status"] == "not_available"
    assert "77.5" not in data["reply"]
    offered = {spec["function"]["name"] for spec in llm.last_tools}
    assert "get_my_attendance" not in offered


def test_student_gets_their_own_attendance(app):
    client, _, _ = app
    login(client)
    data = turn(client, "what is my attendance")
    assert data["tools"][0] == {"name": "get_my_attendance", "arguments": {}, "status": "ok"}
    assert "77.5" in data["reply"]


def test_expired_college_token_returns_401(app):
    client, college, _ = app
    login(client)

    async def expired(token):
        raise CollegeAPIError("expired", upstream_status=401)

    college.attendance = expired
    response = client.post("/api/chat/turn", json={"text": "what is my attendance"})
    assert response.status_code == 401


# Assistant: confirm-before-write -------------------------------------------------------------------


def test_leave_on_exam_day_is_blocked(app):
    client, college, _ = app
    login(client)
    data = turn(client, "apply leave on 2026-11-25")
    assert data["tools"][0]["status"] == "not_allowed"
    assert "assessment" in data["reply"].lower() and college.requests == []


def test_leave_needs_yes_and_is_submitted_exactly_once(app):
    client, college, _ = app
    login(client)
    first = turn(client, "apply leave on 2026-11-26")
    assert first["tools"][0]["status"] == "awaiting_confirmation" and college.requests == []
    conversation = first["conversation_id"]

    done = turn(client, "Yes", conversation)
    assert done["provider"] == "rules" and "reference number is 500" in done["reply"]
    assert len(college.requests) == 1 and len(college.idempotency_keys[0]) == 32

    again = turn(client, "yes", conversation)
    assert len(college.requests) == 1
    assert again["provider"] != "rules"


def test_no_discards_the_pending_action(app):
    client, college, _ = app
    login(client)
    first = turn(client, "apply leave on 2026-11-26")
    cancelled = turn(client, "no", first["conversation_id"])
    assert "Nothing was submitted" in cancelled["reply"] and college.requests == []


def test_pending_action_is_per_conversation(app):
    client, college, _ = app
    login(client)
    turn(client, "apply leave on 2026-11-26")
    other = turn(client, "yes")  # new conversation, nothing pending there
    assert other["provider"] != "rules" and college.requests == []


def test_public_admission_flow(app):
    client, college, _ = app
    prepared = turn(client, "apply ece please")
    assert prepared["tools"][0]["status"] == "awaiting_confirmation"
    done = turn(client, "yes", prepared["conversation_id"])
    assert "reference number is 1" in done["reply"]
    assert college.admissions[0]["course_code"] == "BTECH-ECE" and college.admissions[0]["phone"] == "9876543210"


# Input validation ------------------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "x" * 1001])
def test_chat_text_limits(app, text):
    client, _, _ = app
    response = client.post("/api/chat/turn", json={"text": text})
    assert response.status_code == 422


# Voice ---------------------------------------------------------------------------------------------


def test_voice_turn_transcribes_and_answers(app):
    client, _, _ = app
    login(client)
    data = client.post("/api/voice/turn", files={"audio": AUDIO}).json()
    assert data["transcript"] == "What is my attendance?" and data["stt_provider"] == "fake-stt"
    assert data["audio_url"] == f"/api/voice/tts/{data['reply_message_id']}"


def test_voice_rejects_non_audio(app):
    client, _, _ = app
    response = client.post("/api/voice/turn", files={"audio": ("x.txt", b"hello" * 500, "text/plain")})
    assert response.status_code == 415


def test_tiny_audio_is_treated_as_not_heard_without_calling_the_llm(app):
    client, _, llm = app
    data = client.post("/api/voice/turn", files={"audio": ("s.webm", b"\x00" * 10, "audio/webm")}).json()
    assert data["reply"].startswith("Sorry, I didn't catch that") and llm.calls == []
    assert client.get(data["audio_url"]).status_code == 200


def test_voice_too_large(tmp_path, monkeypatch):
    client, _, _ = build_client(tmp_path, monkeypatch, max_audio_mb=1)
    with client:
        response = client.post(
            "/api/voice/turn", files={"audio": ("s.webm", b"\x00" * (1024 * 1024 + 10), "audio/webm")}
        )
        assert response.status_code == 413


def test_reply_audio_is_owner_only(app):
    client, _, _ = app
    data = turn(client, "hello")
    url = f"/api/voice/tts/{data['reply_message_id']}"
    owner = client.get(url)
    assert owner.status_code == 200 and owner.headers["content-type"] == "audio/mpeg"
    client.cookies.clear()
    assert client.get(url).status_code == 404


def test_unknown_system_phrase_is_404(app):
    client, _, _ = app
    assert client.get("/api/voice/tts/system/anything").status_code == 404


# History -------------------------------------------------------------------------------------------


def test_history_lists_and_reads_own_conversations_only(app):
    client, _, _ = app
    data = turn(client, "hello there")
    listed = client.get("/api/history").json()
    assert listed[0]["id"] == data["conversation_id"] and listed[0]["updated_at"].endswith("Z")
    detail = client.get(f"/api/history/{data['conversation_id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    client.cookies.clear()
    assert client.get(f"/api/history/{data['conversation_id']}").status_code == 404
    assert client.get("/api/history").json() == []


# Rate limiting -------------------------------------------------------------------------------------


def test_rate_limit(tmp_path, monkeypatch):
    client, _, _ = build_client(tmp_path, monkeypatch, rate_limit_per_minute=2)
    with client:
        client.get("/api/auth/me")
        codes = [client.post("/api/chat/turn", json={"text": "hi"}).status_code for _ in range(3)]
        assert codes == [200, 200, 429]


def test_model_asking_to_confirm_without_preparing_is_forced_to_call_the_tool(app):
    client, college, llm = app
    login(client)
    original = llm.complete

    async def lazy_then_correct(messages, tools):
        if messages[-1]["role"] == "user" and "apply leave on" in messages[-1]["content"].lower():
            from app.services.resilience import FallbackResult
            from tests.fakes import _message

            return FallbackResult("fake:llm", _message("Sure, I'll draft that. Shall I submit it?"), 1)
        if messages[-1]["role"] == "user" and "not called the action tool" in messages[-1]["content"]:
            from app.services.resilience import FallbackResult
            from tests.fakes import _call, _message

            args = {"type": "personal_leave", "from_date": "2026-11-25", "reason": "family"}
            return FallbackResult("fake:llm", _message(calls=[_call("create_leave_or_od_request", args)]), 1)
        return await original(messages, tools)

    llm.complete = lazy_then_correct
    data = turn(client, "apply leave on 2026-11-25")
    assert data["tools"][0]["status"] == "not_allowed"
    assert "assessment" in data["reply"].lower() and college.requests == []
