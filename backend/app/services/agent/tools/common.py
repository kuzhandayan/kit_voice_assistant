from datetime import timedelta
from typing import Any

from app.core.principal import Role
from app.services.agent.guards import event_kind
from app.services.agent.tools.base import EVERYONE, SIGNED_IN, ReadTool, ToolContext, arg_date, arg_str, schema
from app.services.knowledge.base import Audience

PUBLIC_DOC_TYPES = {"brochure"}


def audience_for(ctx: ToolContext) -> Audience:
    p = ctx.principal
    if p.role is Role.STUDENT:
        return Audience(
            programme=p.programme.value, department=p.profile.get("department"), year=p.profile.get("year_of_study")
        )
    return Audience()


async def search_documents(ctx: ToolContext, args: dict[str, Any]) -> Any:
    query = arg_str(args, "query", max_len=200)
    available = {d.type for d in ctx.knowledge.documents}
    allowed = PUBLIC_DOC_TYPES if ctx.principal.role is Role.PUBLIC else available or {"handbook"}
    wanted = args.get("source")
    doc_types = {wanted} if wanted in allowed else allowed
    chunks = await ctx.knowledge.search(query, doc_types=doc_types, audience=audience_for(ctx), limit=4)
    if not chunks:
        return {"found": False, "note": "Nothing relevant in the college documents. Say you don't know; do not guess."}
    return {
        "found": True,
        "passages": [{"source": c.doc.title, "type": c.doc.type, "text": c.text[:1200]} for c in chunks],
    }


async def get_college_info(ctx: ToolContext, _: dict[str, Any]) -> Any:
    return await ctx.college.college()


async def list_courses(ctx: ToolContext, _: dict[str, Any]) -> Any:
    return await ctx.college.courses()


async def get_calendar(ctx: ToolContext, args: dict[str, Any]) -> Any:
    today = await ctx.today()
    start = arg_date(args, "from_date", required=False) or today
    end = arg_date(args, "to_date", required=False) or start + timedelta(days=45)
    events = await ctx.college.calendar(ctx.token, start, end)
    wanted = args.get("kind")
    items = [
        {
            "date": e["date"],
            "kind": event_kind(e),
            "title": e.get("title"),
            "subject_code": e.get("subject_code"),
            "follows_weekday": e.get("follows_weekday"),
            "status": e.get("status"),
        }
        for e in events
        if not wanted or event_kind(e) == wanted
    ]
    return {"from": start.isoformat(), "to": end.isoformat(), "events": items}


async def get_my_profile(ctx: ToolContext, _: dict[str, Any]) -> Any:
    return await ctx.college.me(ctx.token)


SOURCES = ["handbook", "circular", "notice", "lesson_notes", "brochure"]

COMMON_TOOLS = [
    ReadTool(
        "search_documents",
        "Search official KIT documents (handbook, circulars, notices, admissions brochure, lesson notes). Use for any rule, policy, fee, date, eligibility or subject doubt. Circulars and notices override the handbook.",
        schema({"query": {"type": "string"}, "source": {"type": "string", "enum": SOURCES}}, ["query"]),
        EVERYONE,
        search_documents,
    ),
    ReadTool(
        "get_college_info", "KIT name, description and admissions office contact.", schema(), EVERYONE, get_college_info
    ),
    ReadTool(
        "list_courses",
        "Courses with code, minimum 12th %, annual fee, hostel fee and seats.",
        schema(),
        EVERYONE,
        list_courses,
    ),
    ReadTool(
        "get_calendar",
        "College calendar: holidays, internal assessments/exams and special working days. Dates YYYY-MM-DD.",
        schema(
            {
                "from_date": {"type": "string"},
                "to_date": {"type": "string"},
                "kind": {"type": "string", "enum": ["holiday", "exam", "working_day"]},
            }
        ),
        SIGNED_IN,
        get_calendar,
    ),
    ReadTool("get_my_profile", "Profile of the signed-in person.", schema(), SIGNED_IN, get_my_profile),
]
