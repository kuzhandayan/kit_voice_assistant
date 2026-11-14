import re
from typing import Any

from app.services.agent.tools.base import PUBLIC, ActionTool, Prepared, RuleViolation, ToolContext, arg_str, schema

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)


def normalise_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise RuleViolation("That phone number doesn't look right. Please say the 10-digit mobile number again.")
    return digits


_WORD = re.compile(r"[a-z]+")
_IGNORED = {"btech", "b", "tech", "and", "engineering", "of", "in", "the", "course", "degree", "bachelor"}


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower().replace(".", "").replace("-", " ")) if w not in _IGNORED}


def match_course(courses: list[dict[str, Any]], spoken: str) -> dict[str, Any]:
    """Matches a code ('BTECH-CSE'), department ('ECE') or spoken name ('computer science')."""
    wanted = _words(spoken)
    best, best_score = None, 0
    for course in courses:
        keys = _words(course["name"]) | _words(course["code"]) | {course["department"].lower()}
        score = len(wanted & keys)
        if score > best_score:
            best, best_score = course, score
    if best is None:
        options = ", ".join(c["name"] for c in courses)
        raise RuleViolation(f"I couldn't match that course. We offer {options}.")
    return best


async def prepare_admission(ctx: ToolContext, args: dict[str, Any]) -> Prepared:
    name = arg_str(args, "full_name", max_len=100)
    email = arg_str(args, "email", max_len=120).replace(" ", "").lower()
    if not _EMAIL.match(email):
        raise RuleViolation("That email address doesn't look right. Please spell it again.")
    phone = normalise_phone(arg_str(args, "phone", max_len=20))
    try:
        percent = float(args.get("twelfth_percent"))
    except (TypeError, ValueError) as exc:
        raise RuleViolation("Please tell me your 12th standard percentage.") from exc
    if not 0 < percent <= 100:
        raise RuleViolation("The 12th percentage must be between 0 and 100.")
    course = match_course(await ctx.college.courses(), arg_str(args, "course", max_len=80))
    if percent < float(course["min_12th_percent"]):
        raise RuleViolation(
            f"{course['name']} needs at least {course['min_12th_percent']:g}% in 12th, and you have {percent:g}%. "
            "You could consider another course that fits your marks."
        )
    payload = {
        "full_name": name,
        "phone": phone,
        "email": email,
        "course_code": course["code"],
        "twelfth_percent": percent,
    }
    summary = (
        f"Admission application for {name}, {course['name']}, 12th marks {percent:g}%, phone {phone}, email {email}."
    )
    return Prepared(summary, payload)


async def execute_admission(ctx: ToolContext, payload: dict[str, Any], key: str) -> Any:
    result = await ctx.college.submit_admission(payload, idempotency_key=key)
    return {
        "application_id": result.get("id"),
        "status": result.get("status"),
        "course_code": result.get("course_code"),
    }


PUBLIC_TOOLS = [
    ActionTool(
        "submit_admission_application",
        "Apply for admission. Collect full name, phone, email, course and 12th percentage first.",
        schema(
            {
                "full_name": {"type": "string"},
                "phone": {"type": "string"},
                "email": {"type": "string"},
                "course": {"type": "string", "description": "Course code or name, e.g. BTECH-CSE or computer science"},
                "twelfth_percent": {"type": "number"},
            },
            ["full_name", "phone", "email", "course", "twelfth_percent"],
        ),
        PUBLIC,
        prepare_admission,
        execute_admission,
    )
]
