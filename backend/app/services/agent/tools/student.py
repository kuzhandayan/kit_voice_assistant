import asyncio
from datetime import date, timedelta
from typing import Any

from app.services.agent import guards
from app.services.agent.tools.base import (
    STUDENT,
    ActionTool,
    Prepared,
    ReadTool,
    RuleViolation,
    ToolContext,
    arg_date,
    arg_int,
    arg_str,
    schema,
)

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
REQUEST_LABEL = {"personal_leave": "personal leave", "medical_leave": "medical leave", "on_duty": "on-duty"}


async def _calendar(ctx: ToolContext, start: date, end: date) -> dict[date, list[dict[str, Any]]]:
    return guards.events_by_date(await ctx.college.calendar(ctx.token, start, end))


async def get_my_attendance(ctx: ToolContext, _: dict[str, Any]) -> Any:
    data = await ctx.college.attendance(ctx.token)
    return {
        "as_of": data.get("as_of_date"),
        "overall_percentage": data.get("overall_percentage"),
        "note": "Eligibility is decided per subject (Rule 4.1.2): theory needs 75%, labs need 80%.",
        "subjects": [guards.attendance_status(s) for s in data.get("subjects", [])],
    }


async def get_attendance_sessions(ctx: ToolContext, args: dict[str, Any]) -> Any:
    rows = await ctx.college.attendance_sessions(
        ctx.token,
        arg_str(args, "subject", required=False),
        arg_date(args, "from_date", required=False),
        arg_date(args, "to_date", required=False),
    )
    return {"count": len(rows), "sessions": rows[-40:]}


async def get_my_timetable(ctx: ToolContext, args: dict[str, Any]) -> Any:
    slots = await ctx.college.timetable(ctx.token)
    day = arg_date(args, "date", required=False)
    if day is None:
        return {
            "weekly": [
                {
                    "day": WEEKDAYS[int(s["weekday"]) - 1],
                    "period": s["period"],
                    "time": f"{s['start_time']}-{s['end_time']}",
                    "subject": s["subject_name"],
                }
                for s in slots
            ]
        }
    calendar = await _calendar(ctx, day, day)
    weekday = guards.schedule_weekday(day, calendar)
    events = [e.get("title") for e in calendar.get(day, [])]
    if weekday is None:
        return {
            "date": day.isoformat(),
            "classes": [],
            "note": f"No classes on {WEEKDAYS[day.isoweekday() - 1]}.",
            "events": events,
        }
    note = None if weekday == day.isoweekday() else f"This day follows the {WEEKDAYS[weekday - 1]} timetable."
    classes = [
        {"period": s["period"], "time": f"{s['start_time']}-{s['end_time']}", "subject": s["subject_name"]}
        for s in slots
        if int(s["weekday"]) == weekday
    ]
    return {
        "date": day.isoformat(),
        "day": WEEKDAYS[day.isoweekday() - 1],
        "note": note,
        "events": events,
        "classes": sorted(classes, key=lambda c: c["period"]),
    }


async def get_my_academics(ctx: ToolContext, _: dict[str, Any]) -> Any:
    return await ctx.college.academics(ctx.token)


async def get_my_subjects(ctx: ToolContext, _: dict[str, Any]) -> Any:
    return await ctx.college.subjects(ctx.token)


async def list_my_requests(ctx: ToolContext, _: dict[str, Any]) -> Any:
    rows = await ctx.college.my_requests(ctx.token)
    return [
        {
            k: r.get(k)
            for k in (
                "id",
                "type",
                "from_date",
                "to_date",
                "half_day",
                "reason",
                "event_name",
                "status",
                "decision_note",
            )
        }
        for r in rows
    ]


async def list_placement_drives(ctx: ToolContext, _: dict[str, Any]) -> Any:
    today = await ctx.today()
    drives, academics, registrations = await asyncio.gather(
        ctx.college.placement_drives(), ctx.college.academics(ctx.token), ctx.college.my_placements(ctx.token)
    )
    return [
        {
            **d,
            "you_are_eligible": not (
                b := guards.placement_blockers(d, ctx.principal.profile, academics, today, registrations)
            ),
            "why_not": b,
        }
        for d in drives
    ]


async def list_my_placements(ctx: ToolContext, _: dict[str, Any]) -> Any:
    return await ctx.college.my_placements(ctx.token)


async def prepare_request(ctx: ToolContext, args: dict[str, Any]) -> Prepared:
    kind = arg_str(args, "type")
    start = arg_date(args, "from_date")
    end = arg_date(args, "to_date", required=False) or start
    reason = arg_str(args, "reason", required=False)
    event_name = arg_str(args, "event_name", required=False, max_len=120)
    half_day = bool(args.get("half_day"))
    today = await ctx.today()
    window_start = min(start, today) - timedelta(days=120)
    timetable, existing, calendar, attendance = await asyncio.gather(
        ctx.college.timetable(ctx.token),
        ctx.college.my_requests(ctx.token),
        _calendar(ctx, window_start, max(end, today) + timedelta(days=1)),
        ctx.college.attendance(ctx.token),
    )
    warnings = guards.check_request(
        kind=kind,
        start=start,
        end=end,
        reason=reason,
        event_name=event_name,
        half_day=half_day,
        today=today,
        programme=ctx.principal.programme,
        calendar=calendar,
        timetable=timetable,
        existing=existing,
    )
    if kind != "on_duty":
        days = guards.working_days(start, end, calendar, timetable)
        drops = [
            i
            for i in guards.leave_impact(attendance.get("subjects", []), timetable, days, calendar)
            if i["below_minimum_after"]
        ]
        if drops:
            names = ", ".join(f"{i['subject']} to {i['after']}%" for i in drops[:3])
            warnings.append(f"This leave would bring {names}, below the minimum (Rule 4.2.3).")
    payload = {
        "type": kind,
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "half_day": half_day,
        "reason": reason,
        "event_name": event_name,
    }
    span = start.strftime("%A %d %B") if start == end else f"{start.strftime('%d %B')} to {end.strftime('%d %B')}"
    label = REQUEST_LABEL[kind] + (" (half day)" if half_day else "")
    extra = f" for {event_name}" if event_name else ""
    return Prepared(f"{label.capitalize()}{extra} on {span}, reason: {reason}.", payload, warnings)


async def execute_request(ctx: ToolContext, payload: dict[str, Any], key: str) -> Any:
    body = {k: v for k, v in payload.items() if v is not None}
    result = await ctx.college.create_request(ctx.token, body, idempotency_key=key)
    return {"request_id": result.get("id"), "status": result.get("status"), "type": result.get("type")}


async def prepare_cancel(ctx: ToolContext, args: dict[str, Any]) -> Prepared:
    request_id = arg_int(args, "request_id")
    req = await ctx.college.my_request(ctx.token, request_id)
    if str(req.get("status", "")).lower() not in guards.ACTIVE_STATUSES:
        raise RuleViolation(f"That request is already {req.get('status')}, so it can't be cancelled.")
    if date.fromisoformat(req["from_date"]) <= await ctx.today():
        raise RuleViolation("A leave that has already started cannot be cancelled (Rule 6.6.1).")
    label = REQUEST_LABEL.get(req.get("type"), "request")
    return Prepared(f"Cancel your {label} from {req['from_date']} to {req['to_date']}.", {"request_id": request_id})


async def execute_cancel(ctx: ToolContext, payload: dict[str, Any], _: str) -> Any:
    result = await ctx.college.cancel_request(ctx.token, int(payload["request_id"]))
    return {"request_id": result.get("id"), "status": result.get("status")}


async def prepare_placement(ctx: ToolContext, args: dict[str, Any]) -> Prepared:
    drive_id = arg_int(args, "drive_id")
    today = await ctx.today()
    drives, academics, registrations = await asyncio.gather(
        ctx.college.placement_drives(), ctx.college.academics(ctx.token), ctx.college.my_placements(ctx.token)
    )
    drive = next((d for d in drives if int(d["id"]) == drive_id), None)
    if drive is None:
        raise RuleViolation("I couldn't find that placement drive.")
    blockers = guards.placement_blockers(drive, ctx.principal.profile, academics, today, registrations)
    if blockers:
        raise RuleViolation(f"You can't register for {drive['company']} because " + "; ".join(blockers) + ".")
    summary = f"Register for the {drive['company']} drive ({drive['category'].replace('_', '-')}), deadline {drive['deadline']}, {drive['seats_left']} seats left."
    return Prepared(summary, {"drive_id": drive_id}, ["Registering means you must attend every round (Rule 10.4.4)."])


async def execute_placement(ctx: ToolContext, payload: dict[str, Any], _: str) -> Any:
    result = await ctx.college.register_placement(ctx.token, int(payload["drive_id"]))
    return {"registration_id": result.get("id"), "company": result.get("company")}


DATE = {"type": "string", "description": "YYYY-MM-DD"}

STUDENT_TOOLS = [
    ReadTool(
        "get_my_attendance",
        "My attendance overall and per subject, with classes needed or still missable.",
        schema(),
        STUDENT,
        get_my_attendance,
    ),
    ReadTool(
        "get_attendance_sessions",
        "My class-by-class attendance history, optionally for one subject code or date range.",
        schema({"subject": {"type": "string"}, "from_date": DATE, "to_date": DATE}),
        STUDENT,
        get_attendance_sessions,
    ),
    ReadTool(
        "get_my_timetable",
        "My timetable. Give a date for one day's classes (handles holidays and special working days).",
        schema({"date": DATE}),
        STUDENT,
        get_my_timetable,
    ),
    ReadTool(
        "get_my_academics", "My CGPA, standing arrears and placement status.", schema(), STUDENT, get_my_academics
    ),
    ReadTool("get_my_subjects", "My registered subjects and codes.", schema(), STUDENT, get_my_subjects),
    ReadTool("list_my_requests", "My leave and on-duty requests with status.", schema(), STUDENT, list_my_requests),
    ReadTool(
        "list_placement_drives",
        "Placement drives with my eligibility for each.",
        schema(),
        STUDENT,
        list_placement_drives,
    ),
    ReadTool("list_my_placements", "Drives I have registered for.", schema(), STUDENT, list_my_placements),
    ActionTool(
        "create_leave_or_od_request",
        "Apply for personal leave, medical leave or on-duty, or check if a leave is allowed and how it affects attendance. Needs type, dates, reason; on-duty also needs event_name. Nothing is submitted until the user confirms.",
        schema(
            {
                "type": {"type": "string", "enum": ["personal_leave", "medical_leave", "on_duty"]},
                "from_date": DATE,
                "to_date": DATE,
                "reason": {"type": "string"},
                "event_name": {"type": "string"},
                "half_day": {"type": "boolean"},
            },
            ["type", "from_date", "reason"],
        ),
        STUDENT,
        prepare_request,
        execute_request,
    ),
    ActionTool(
        "cancel_my_request",
        "Cancel one of my pending or approved requests before it starts.",
        schema({"request_id": {"type": "integer"}}, ["request_id"]),
        STUDENT,
        prepare_cancel,
        execute_cancel,
    ),
    ActionTool(
        "register_for_placement",
        "Register me for a placement drive by drive id.",
        schema({"drive_id": {"type": "integer"}}, ["drive_id"]),
        STUDENT,
        prepare_placement,
        execute_placement,
    ),
]
