"""In-memory stand-ins for the college API, the LLM and the speech services, used by the API tests."""

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from app.core.errors import CollegeAPIError
from app.services.resilience import FallbackResult

STUDENT = {
    "id": 172,
    "login_id": "arjun",
    "full_name": "Arjun K",
    "role": "student",
    "department": "CSE",
    "class_id": 71,
    "class_code": "CSE-2A",
    "programme": "UG",
    "year_of_study": 2,
}
COURSES = [
    {
        "id": 1,
        "code": "BTECH-CSE",
        "name": "B.Tech Computer Science and Engineering",
        "department": "CSE",
        "min_12th_percent": 75.0,
        "annual_fee": 125000.0,
        "hostel_fee": 60000.0,
        "seats": 120,
    },
    {
        "id": 2,
        "code": "BTECH-ECE",
        "name": "B.Tech Electronics and Communication Engineering",
        "department": "ECE",
        "min_12th_percent": 70.0,
        "annual_fee": 110000.0,
        "hostel_fee": 60000.0,
        "seats": 60,
    },
]
TIMETABLE = [
    {
        "id": i,
        "weekday": d,
        "period": 1,
        "start_time": "09:00",
        "end_time": "09:50",
        "subject_code": "CS304",
        "subject_name": "Database Management Systems",
    }
    for i, d in enumerate(range(1, 6), 1)
]
CALENDAR = [
    {
        "id": 1,
        "date": "2026-11-22",
        "type": "holiday",
        "title": "Sunday Holiday",
        "subject_code": None,
        "follows_weekday": None,
        "status": "active",
    },
    {
        "id": 2,
        "date": "2026-11-25",
        "type": "internal_exam",
        "title": "DBMS Internal Assessment Exam",
        "subject_code": "CS304",
        "follows_weekday": None,
        "status": "active",
    },
]


class FakeCollege:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.idempotency_keys: list[str] = []
        self.admissions: list[dict[str, Any]] = []

    async def aclose(self) -> None: ...

    def _auth(self, token: str) -> None:
        if token != "tok-arjun":
            raise CollegeAPIError("Token expired", upstream_status=401, upstream_code="unauthorized")

    async def today(self):
        return {"date": "2026-11-21", "weekday": 6, "weekday_name": "Saturday", "timezone": "Asia/Kolkata"}

    async def college(self):
        return {
            "name": "Knotopian Institute of Technology",
            "code": "KIT",
            "tagline": "t",
            "description": "d",
            "contact": {"phone": "1", "email": "a@kit.ac.in", "website": "w", "address": "x"},
        }

    async def courses(self):
        return COURSES

    async def documents(self):
        return []

    async def login(self, login_id: str, password: str):
        if (login_id, password) != ("arjun", "Kit@2026"):
            raise CollegeAPIError("Invalid credentials", upstream_status=401)
        return {"access_token": "tok-arjun", "token_type": "bearer", "expires_in": 28800, "user": STUDENT}

    async def me(self, token):
        self._auth(token)
        return STUDENT

    async def attendance(self, token):
        self._auth(token)
        subject = {
            "subject_id": 1,
            "subject_code": "CS304",
            "subject_name": "Database Management Systems",
            "classes_held": 40,
            "classes_attended": 31,
            "classes_od": 0,
            "classes_absent": 9,
            "percentage": 77.5,
        }
        return {
            "as_of_date": "2026-11-21",
            "overall_percentage": 77.5,
            "total_classes_held": 40,
            "total_classes_attended": 31,
            "subjects": [subject],
        }

    async def timetable(self, token):
        self._auth(token)
        return TIMETABLE

    async def calendar(self, token, start=None, end=None):
        self._auth(token)
        return [
            e
            for e in CALENDAR
            if (not start or e["date"] >= start.isoformat()) and (not end or e["date"] <= end.isoformat())
        ]

    async def my_requests(self, token):
        self._auth(token)
        return self.requests

    async def create_request(self, token, payload, idempotency_key):
        self._auth(token)
        self.idempotency_keys.append(idempotency_key)
        created = {"id": 500 + len(self.requests), "student_id": 172, "status": "pending", **payload}
        self.requests.append(created)
        return created

    async def submit_admission(self, payload, idempotency_key):
        self.admissions.append(payload)
        return {"id": len(self.admissions), "status": "received", **payload}


def _call(name: str, args: dict[str, Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"call_{name}", type="function", function=SimpleNamespace(name=name, arguments=json.dumps(args or {}))
    )


def _message(content: str | None = None, calls: list[SimpleNamespace] | None = None) -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=calls or None)


@dataclass
class FakeLLM:
    """Deterministic 'model': maps the user's words to a tool call, then repeats the tool result."""

    calls: list[list[dict[str, Any]]] = field(default_factory=list)
    last_tools: list[dict[str, Any]] = field(default_factory=list)
    provider_names: list[str] = field(default_factory=lambda: ["fake:llm"])

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> FallbackResult:
        self.calls.append(messages)
        self.last_tools = tools
        last = messages[-1]
        if last["role"] == "tool":
            return FallbackResult("fake:llm", _message(f"RESULT {last['content']}"), 1)
        text = last["content"].lower()
        if "attendance" in text:
            return FallbackResult("fake:llm", _message(calls=[_call("get_my_attendance")]), 1)
        if match := re.search(r"leave on (\d{4}-\d{2}-\d{2})", text):
            args = {"type": "personal_leave", "from_date": match.group(1), "reason": "family function"}
            return FallbackResult("fake:llm", _message(calls=[_call("create_leave_or_od_request", args)]), 1)
        if "apply ece" in text:
            args = {
                "full_name": "Priya R",
                "phone": "98765 43210",
                "email": "priya@example.com",
                "course": "ECE",
                "twelfth_percent": 72,
            }
            return FallbackResult("fake:llm", _message(calls=[_call("submit_admission_application", args)]), 1)
        return FallbackResult("fake:llm", _message("Hello from KIT."), 1)


class FakeSTT:
    def __init__(self, transcript: str = "What is my attendance?") -> None:
        self.transcript = transcript

    async def transcribe(self, audio) -> FallbackResult:
        return FallbackResult("fake-stt", self.transcript, 1)


class FakeTTS:
    async def synthesize(self, text: str) -> FallbackResult:
        return FallbackResult("fake-tts", b"ID3fake", 1)

    async def stream(self, text: str) -> tuple[str, AsyncIterator[bytes]]:
        async def chunks() -> AsyncIterator[bytes]:
            yield b"ID3"
            yield b"fake"

        return "fake-tts", chunks()
