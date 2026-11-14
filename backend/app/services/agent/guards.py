"""Pure business-rule checks taken from the KIT Student Handbook 2026 and circulars."""

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.core.principal import Programme
from app.services.agent.tools.base import RuleViolation

ACTIVE_STATUSES = {"pending", "approved", "proof_pending", "proof pending"}
REQUEST_TYPES = {"personal_leave", "medical_leave", "on_duty"}
THEORY_MIN = 75.0
LAB_MIN = 80.0


@dataclass(frozen=True)
class LeavePolicy:
    notice_hours: int
    hod_after_days: int
    on_duty_limit_days: int
    half_day_allowed: bool
    rule_prefix: str


POLICIES = {
    Programme.UG: LeavePolicy(
        notice_hours=24, hod_after_days=3, on_duty_limit_days=10, half_day_allowed=True, rule_prefix="6"
    ),
    Programme.PG: LeavePolicy(
        notice_hours=48, hod_after_days=2, on_duty_limit_days=6, half_day_allowed=False, rule_prefix="7"
    ),
}


def event_kind(event: dict[str, Any]) -> str:
    text = f"{event.get('type', '')} {event.get('title', '')}".lower()
    if "holiday" in text:
        return "holiday"
    if "exam" in text or "assessment" in text or str(event.get("type", "")).lower() in {"ia", "cat"}:
        return "exam"
    if "working" in text:
        return "working_day"
    return "other"


def _active(event: dict[str, Any]) -> bool:
    return str(event.get("status", "active")).lower() not in {"cancelled", "canceled", "postponed"}


def events_by_date(events: list[dict[str, Any]]) -> dict[date, list[dict[str, Any]]]:
    grouped: dict[date, list[dict[str, Any]]] = {}
    for event in events or []:
        if _active(event):
            grouped.setdefault(date.fromisoformat(event["date"]), []).append(event)
    return grouped


def schedule_weekday(day: date, calendar: dict[date, list[dict[str, Any]]]) -> int | None:
    """Timetable weekday that runs on `day` (1=Mon), or None when there are no classes."""
    events = calendar.get(day, [])
    if any(event_kind(e) == "holiday" for e in events):
        return None
    for event in events:
        if event_kind(event) == "working_day":
            return int(event.get("follows_weekday") or day.isoweekday())
    if day.isoweekday() == 7:
        return None
    return day.isoweekday()


def daterange(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def working_days(
    start: date, end: date, calendar: dict[date, list[dict[str, Any]]], timetable: list[dict[str, Any]]
) -> list[date]:
    weekdays_with_classes = {int(slot["weekday"]) for slot in timetable} or {1, 2, 3, 4, 5}
    return [d for d in daterange(start, end) if (wd := schedule_weekday(d, calendar)) and wd in weekdays_with_classes]


def exam_days(start: date, end: date, calendar: dict[date, list[dict[str, Any]]]) -> list[tuple[date, str]]:
    return [
        (d, e.get("title", "exam"))
        for d in daterange(start, end)
        for e in calendar.get(d, [])
        if event_kind(e) == "exam"
    ]


def overlapping(requests: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    clashes = []
    for req in requests or []:
        if str(req.get("status", "")).lower() not in ACTIVE_STATUSES:
            continue
        if date.fromisoformat(req["from_date"]) <= end and date.fromisoformat(req["to_date"]) >= start:
            clashes.append(req)
    return clashes


def check_request(
    *,
    kind: str,
    start: date,
    end: date,
    reason: str | None,
    event_name: str | None,
    half_day: bool,
    today: date,
    programme: Programme,
    calendar: dict[date, list[dict[str, Any]]],
    timetable: list[dict[str, Any]],
    existing: list[dict[str, Any]],
) -> list[str]:
    """Raises RuleViolation for hard rule breaks; returns warnings to read out before confirming."""
    policy = POLICIES[programme]
    p = policy.rule_prefix
    if kind not in REQUEST_TYPES:
        raise RuleViolation("The request type must be personal leave, medical leave or on-duty.")
    if end < start:
        raise RuleViolation("The end date is before the start date. Please give the dates again.")
    if not reason:
        raise RuleViolation("Please tell me the reason for the request.")
    if kind == "on_duty" and not event_name:
        raise RuleViolation("For on-duty I need the name of the event.")
    if half_day and (start != end or not policy.half_day_allowed):
        if not policy.half_day_allowed:
            raise RuleViolation("Half-day leave is not available for M.Tech students (Rule 7.2.1).")
        raise RuleViolation("Half-day leave can only be for a single day.")
    if kind == "personal_leave" and start < today:
        raise RuleViolation(
            f"Personal leave cannot be applied after the absence (Rule {p}.1.2). If you were unwell, you can apply for medical leave instead."
        )
    if kind == "on_duty" and start < today:
        raise RuleViolation("On-duty must be requested before the event (Rule 6.4.2).")
    if (end - start).days > 60:
        raise RuleViolation("That date range is too long. Please check the dates.")

    days = working_days(start, end, calendar, timetable)
    if not days:
        raise RuleViolation("There are no working days in that range, so no leave is needed.")

    exams = exam_days(start, end, calendar)
    if exams and kind in {"personal_leave", "on_duty"}:
        when = ", ".join(f"{title} on {d.strftime('%d %b')}" for d, title in exams[:2])
        rule = f"{p}.1.4" if kind == "personal_leave" else "6.4.7"
        raise RuleViolation(
            f"That range includes an internal assessment ({when}). Leave and on-duty, including half-day leave, "
            f"are not allowed on assessment days (Rule {rule}). Suggest a different date."
        )

    clashes = overlapping(existing, start, end)
    if clashes:
        c = clashes[0]
        raise RuleViolation(
            f"You already have a {c.get('type', 'request').replace('_', ' ')} ({c.get('status')}) from {c['from_date']} to {c['to_date']} that overlaps these dates (Rule 6.6.3)."
        )

    warnings: list[str] = []
    if kind == "personal_leave" and (start - today).days * 24 < policy.notice_hours:
        warnings.append(f"This is less than {policy.notice_hours} hours' notice, so it may be rejected (Rule {p}.1.1).")
    if kind == "personal_leave" and len(days) > policy.hod_after_days:
        warnings.append(
            f"More than {policy.hod_after_days} working days also needs Head of Department approval (Rule {p}.1.3)."
        )
    if kind == "medical_leave":
        warnings.append("You must submit the medical certificate to your advisor within 3 working days of returning.")
    if kind == "on_duty":
        used = sum(
            len(working_days(date.fromisoformat(r["from_date"]), date.fromisoformat(r["to_date"]), calendar, timetable))
            for r in existing or []
            if r.get("type") == "on_duty" and str(r.get("status", "")).lower() in ACTIVE_STATUSES
        )
        if used + len(days) > policy.on_duty_limit_days:
            warnings.append(
                f"This would take your on-duty to {used + len(days)} days; the semester limit is {policy.on_duty_limit_days}."
            )
        proof = "3 working days (Circular 12/2026)" if programme is Programme.UG else "5 working days (Rule 7.4.3)"
        warnings.append(f"Submit proof of participation within {proof} after the event.")
    return warnings


def is_lab(subject_name: str) -> bool:
    name = subject_name.lower()
    return "lab" in name or "laboratory" in name or "practical" in name


def classes_needed(attended: int, held: int, threshold: float) -> int:
    """Consecutive classes to attend to reach the threshold."""
    t = threshold / 100
    if held == 0 or attended / held >= t:
        return 0
    return math.ceil((t * held - attended) / (1 - t))


def classes_can_miss(attended: int, held: int, threshold: float) -> int:
    t = threshold / 100
    if held == 0 or attended / held < t:
        return 0
    return math.floor(attended / t - held)


def attendance_status(subject: dict[str, Any]) -> dict[str, Any]:
    held = int(subject.get("classes_held", 0))
    counted = int(subject.get("classes_attended", 0)) + int(subject.get("classes_od", 0) or 0)
    threshold = LAB_MIN if is_lab(subject.get("subject_name", "")) else THEORY_MIN
    return {
        "subject": f"{subject.get('subject_name')} ({subject.get('subject_code')})",
        "percentage": subject.get("percentage"),
        "minimum": threshold,
        "below_minimum": float(subject.get("percentage") or 0) < threshold,
        "classes_needed_to_reach_minimum": classes_needed(counted, held, threshold),
        "classes_you_can_still_miss": classes_can_miss(counted, held, threshold),
    }


def leave_impact(
    subjects: list[dict[str, Any]],
    timetable: list[dict[str, Any]],
    days: list[date],
    calendar: dict[date, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Rule 4.2.3: add the periods scheduled on leave days to periods held; attended stays the same."""
    missed: dict[str, int] = {}
    for day in days:
        weekday = schedule_weekday(day, calendar)
        for slot in timetable:
            if int(slot["weekday"]) == weekday:
                missed[slot["subject_code"]] = missed.get(slot["subject_code"], 0) + 1
    impact = []
    for s in subjects:
        lost = missed.get(s.get("subject_code"), 0)
        if not lost:
            continue
        held = int(s.get("classes_held", 0)) + lost
        counted = int(s.get("classes_attended", 0)) + int(s.get("classes_od", 0) or 0)
        after = round(counted / held * 100, 1) if held else 0.0
        threshold = LAB_MIN if is_lab(s.get("subject_name", "")) else THEORY_MIN
        impact.append(
            {
                "subject": s.get("subject_name"),
                "periods_missed": lost,
                "now": s.get("percentage"),
                "after": after,
                "below_minimum_after": after < threshold,
            }
        )
    return impact


def placement_blockers(
    drive: dict[str, Any],
    profile: dict[str, Any],
    academics: dict[str, Any],
    today: date,
    registrations: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if any(int(r.get("drive_id", -1)) == int(drive["id"]) for r in registrations or []):
        reasons.append("you are already registered for this drive (Rule 10.4.3)")
    if date.fromisoformat(drive["deadline"]) < today:
        reasons.append(f"the registration deadline {drive['deadline']} has passed (Rule 10.4.1)")
    if int(drive.get("seats_left", 0)) <= 0:
        reasons.append("no seats are left (Rule 10.4.2)")
    if float(academics.get("cgpa", 0)) < float(drive.get("min_cgpa", 0)):
        reasons.append(f"your CGPA {academics.get('cgpa')} is below the minimum {drive.get('min_cgpa')}")
    if int(academics.get("standing_arrears", 0)) > 0 and not drive.get("allow_standing_arrears"):
        reasons.append("this drive does not allow standing arrears (Rule 10.2.1)")
    dept = profile.get("department")
    if drive.get("allowed_departments") and dept not in drive["allowed_departments"]:
        reasons.append(f"it is open only to {', '.join(drive['allowed_departments'])}")
    year = profile.get("year_of_study")
    if drive.get("eligible_years") and year not in drive["eligible_years"]:
        reasons.append(f"it is open only to year {', '.join(map(str, drive['eligible_years']))} students")
    placed = (academics.get("placed_category") or "").lower()
    category = str(drive.get("category", "")).lower()
    if placed == "dream" and category != "dream":
        reasons.append("you already hold a dream offer, so you cannot register for non-dream drives (Rule 10.3.2)")
    if placed == "non_dream" and category != "dream":
        reasons.append("you already hold a non-dream offer, so you can register only for dream drives (Rule 10.3.3)")
    return reasons
