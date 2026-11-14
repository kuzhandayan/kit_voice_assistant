import asyncio
from datetime import date
from typing import Any

from app.services.agent import guards
from app.services.agent.tools.base import (
    TEACHER,
    ActionTool,
    Prepared,
    ReadTool,
    RuleViolation,
    ToolContext,
    arg_int,
    arg_str,
    schema,
)


async def list_my_classes(ctx: ToolContext, _: dict[str, Any]) -> Any:
    return await ctx.college.teacher_classes(ctx.token)


async def list_class_requests(ctx: ToolContext, args: dict[str, Any]) -> Any:
    status = arg_str(args, "status", required=False) or "pending"
    rows = await ctx.college.teacher_requests(ctx.token, None if status == "all" else status)
    keys = (
        "id",
        "student_name",
        "class_code",
        "type",
        "from_date",
        "to_date",
        "half_day",
        "reason",
        "event_name",
        "status",
        "student_notes",
    )
    return [{k: r.get(k) for k in keys} for r in rows]


async def get_class_attendance(ctx: ToolContext, args: dict[str, Any]) -> Any:
    class_id = await _resolve_class(ctx, args)
    data = await ctx.college.class_attendance(ctx.token, class_id)
    students = sorted(data.get("students", []), key=lambda s: s.get("percentage", 0))
    only_low = bool(args.get("only_below_minimum"))
    if only_low:
        students = [s for s in students if float(s.get("percentage", 0)) < guards.THEORY_MIN]
    return {"class_code": data.get("class_code"), "as_of": data.get("as_of_date"), "students": students}


async def _resolve_class(ctx: ToolContext, args: dict[str, Any]) -> int:
    classes = await ctx.college.teacher_classes(ctx.token)
    wanted = str(args.get("class") or "").strip().lower().replace(" ", "")
    for c in classes:
        if wanted in {str(c["class_id"]), c["class_code"].lower().replace(" ", "")}:
            return int(c["class_id"])
    if len(classes) == 1 and not wanted:
        return int(classes[0]["class_id"])
    codes = ", ".join(c["class_code"] for c in classes) or "none"
    raise RuleViolation(f"Which class? You can act on: {codes}.")


async def _pending_request(ctx: ToolContext, request_id: int) -> dict[str, Any]:
    requests, classes = await asyncio.gather(
        ctx.college.teacher_requests(ctx.token, None), ctx.college.teacher_classes(ctx.token)
    )
    req = next((r for r in requests if int(r["id"]) == request_id), None)
    if req is None:
        raise RuleViolation("That request is not from a class you are allowed to approve today (Rule 6.5.2).")
    if str(req.get("status", "")).lower() != "pending":
        raise RuleViolation(
            f"That request is already {req.get('status')}. A request is decided only once (Rule 6.5.5)."
        )
    if req.get("class_code") and req["class_code"] not in {c["class_code"] for c in classes}:
        raise RuleViolation("Your authority for that class is not active today (Rule 6.5.3).")
    return req


def _describe(req: dict[str, Any]) -> str:
    kind = str(req.get("type", "request")).replace("_", " ")
    span = req["from_date"] if req["from_date"] == req["to_date"] else f"{req['from_date']} to {req['to_date']}"
    event = f" for {req['event_name']}" if req.get("event_name") else ""
    return f"{req.get('student_name')}'s {kind}{event} on {span} (reason: {req.get('reason')})"


async def _exam_warning(ctx: ToolContext, req: dict[str, Any]) -> list[str]:
    start, end = date.fromisoformat(req["from_date"]), date.fromisoformat(req["to_date"])
    calendar = guards.events_by_date(await ctx.college.calendar(ctx.token, start, end))
    exams = guards.exam_days(start, end, calendar)
    if exams and req.get("type") in {"personal_leave", "on_duty"}:
        return [
            f"Note: {exams[0][1]} is on {exams[0][0].strftime('%d %b')}; leave and on-duty are not allowed on assessment days."
        ]
    return []


async def prepare_approve(ctx: ToolContext, args: dict[str, Any]) -> Prepared:
    request_id = arg_int(args, "request_id")
    req = await _pending_request(ctx, request_id)
    comment = arg_str(args, "comment", required=False, max_len=200)
    return Prepared(
        f"Approve {_describe(req)}.", {"request_id": request_id, "comment": comment}, await _exam_warning(ctx, req)
    )


async def execute_approve(ctx: ToolContext, payload: dict[str, Any], _: str) -> Any:
    result = await ctx.college.approve_request(ctx.token, int(payload["request_id"]), payload.get("comment"))
    return {"request_id": result.get("id"), "status": result.get("status")}


async def prepare_reject(ctx: ToolContext, args: dict[str, Any]) -> Prepared:
    request_id = arg_int(args, "request_id")
    reason = arg_str(args, "reason", required=False, max_len=200)
    if not reason:
        raise RuleViolation("A reason is required to reject a request. What should I give as the reason?")
    req = await _pending_request(ctx, request_id)
    return Prepared(f"Reject {_describe(req)}, with reason: {reason}.", {"request_id": request_id, "reason": reason})


async def execute_reject(ctx: ToolContext, payload: dict[str, Any], _: str) -> Any:
    result = await ctx.college.reject_request(ctx.token, int(payload["request_id"]), payload["reason"])
    return {"request_id": result.get("id"), "status": result.get("status")}


TEACHER_TOOLS = [
    ReadTool("list_my_classes", "Classes I can advise or act on today.", schema(), TEACHER, list_my_classes),
    ReadTool(
        "list_class_requests",
        "Leave and on-duty requests from my classes. Default status pending; use 'all' for every status.",
        schema({"status": {"type": "string", "enum": ["pending", "approved", "rejected", "all"]}}),
        TEACHER,
        list_class_requests,
    ),
    ReadTool(
        "get_class_attendance",
        "Student-wise attendance for one of my classes (class code or id).",
        schema({"class": {"type": "string"}, "only_below_minimum": {"type": "boolean"}}),
        TEACHER,
        get_class_attendance,
    ),
    ActionTool(
        "approve_request",
        "Approve a pending student request by id.",
        schema({"request_id": {"type": "integer"}, "comment": {"type": "string"}}, ["request_id"]),
        TEACHER,
        prepare_approve,
        execute_approve,
    ),
    ActionTool(
        "reject_request",
        "Reject a pending student request by id. A reason is mandatory.",
        schema({"request_id": {"type": "integer"}, "reason": {"type": "string"}}, ["request_id", "reason"]),
        TEACHER,
        prepare_reject,
        execute_reject,
    ),
]
