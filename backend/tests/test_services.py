from datetime import date

import pytest

from app.core.errors import ProviderUnavailable
from app.services.agent.orchestrator import to_speech
from app.services.agent.tools.base import RuleViolation
from app.services.agent.tools.public import match_course, normalise_phone
from app.services.knowledge.base import DocumentMeta, select_active, tokenize
from app.services.knowledge.chunking import chunk_text
from app.services.llm.router import parse_chain
from app.services.resilience import Attempt, with_fallback


async def _ok(value):
    return value


async def _boom():
    raise RuntimeError("down")


async def test_fallback_uses_next_provider():
    result = await with_fallback([Attempt("a", _boom), Attempt("b", lambda: _ok("hi"))], timeout=1, label="t")
    assert (result.provider, result.value) == ("b", "hi")


async def test_fallback_raises_when_all_fail():
    with pytest.raises(ProviderUnavailable) as exc:
        await with_fallback([Attempt("a", _boom), Attempt("b", _boom)], timeout=1, label="t")
    assert exc.value.failures == ["a: RuntimeError", "b: RuntimeError"]


def test_llm_chain_skips_vendors_without_keys():
    entries = parse_chain("groq:openai/gpt-oss-120b@low,gemini:gemini-3.5-flash,bad:model", {"groq": "k", "gemini": ""})
    assert [(e.vendor, e.model, e.reasoning_effort) for e in entries] == [("groq", "openai/gpt-oss-120b", "low")]


COURSES = [
    {"code": "BTECH-CSE", "name": "B.Tech Computer Science and Engineering", "department": "CSE"},
    {"code": "BTECH-ECE", "name": "B.Tech Electronics and Communication Engineering", "department": "ECE"},
    {"code": "BTECH-MECH", "name": "B.Tech Mechanical Engineering", "department": "MECH"},
]


@pytest.mark.parametrize(
    ("spoken", "code"),
    [("computer science", "BTECH-CSE"), ("ECE", "BTECH-ECE"), ("mechanical", "BTECH-MECH"), ("BTECH-CSE", "BTECH-CSE")],
)
def test_match_course(spoken, code):
    assert match_course(COURSES, spoken)["code"] == code


def test_unknown_course_lists_options():
    with pytest.raises(RuleViolation, match="We offer"):
        match_course(COURSES, "medicine")


@pytest.mark.parametrize("raw", ["98765 43210", "+91 98765-43210", "09876543210"])
def test_phone_normalisation(raw):
    assert normalise_phone(raw) == "9876543210"


def test_invalid_phone_is_rejected():
    with pytest.raises(RuleViolation):
        normalise_phone("12345")


def doc(id_, type_, effective):
    return DocumentMeta(id_, f"doc {id_}", type_, "v", date.fromisoformat(effective), {})


def test_newest_effective_handbook_wins_and_future_docs_are_hidden():
    docs = [
        doc(1, "handbook", "2025-07-01"),
        doc(2, "handbook", "2026-07-01"),
        doc(5, "circular", "2026-11-01"),
        doc(9, "circular", "2027-01-01"),
    ]
    active = {d.id for d in select_active(docs, date(2026, 11, 21))}
    assert active == {2, 5}


def test_rule_chunking_and_spelling_normalisation():
    text = " ".join(f"6.1.{i} Rule number {i} says something important about leave." for i in range(1, 9))
    chunks = chunk_text(text)
    assert len(chunks) > 1 and chunks[0].startswith("6.1.1")
    assert tokenize("Normalization rules") == tokenize("normalisation rule")


def test_to_speech_strips_markdown():
    assert to_speech("**Done!** Your id is `12`.\n- item") == "Done! Your id is 12. item"


def test_flatten_tool_history_for_gemini():
    from app.services.llm.router import flatten_tool_history

    messages = [
        {"role": "user", "content": "attendance?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "get_my_attendance", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": '{"overall": 76}'},
    ]
    flat = flatten_tool_history(messages)
    assert all("tool_calls" not in m and m["role"] != "tool" for m in flat)
    assert flat[-1]["content"] == '[Result of get_my_attendance]: {"overall": 76}'


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("Yes", "yes"),
        ("yes please!", "yes"),
        ("Okay.", "yes"),
        ("no", "no"),
        ("Cancel it", "no"),
        ("yes but make it Wednesday", None),
        ("what about tuesday", None),
    ],
)
def test_yes_no_intent(text, intent):
    from app.services.agent.orchestrator import _intent

    assert _intent(text) == intent


def test_describe_outcome_reads_reference():
    from app.services.agent.orchestrator import describe_outcome

    text = describe_outcome({"status": "done", "result": {"request_id": 81, "status": "pending"}})
    assert text == "Done, that's submitted. Your reference number is 81. Its status is pending."
