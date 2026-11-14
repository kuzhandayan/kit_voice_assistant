from datetime import date

import pytest

from app.core.principal import Programme
from app.services.agent import guards
from app.services.agent.tools.base import RuleViolation

TODAY = date(2026, 11, 21)  # Saturday, the college date seen in the sandbox
TIMETABLE = [{"weekday": d, "period": 1, "subject_code": "CS304", "subject_name": "DBMS"} for d in range(1, 6)]


def check(**overrides):
    params = dict(
        kind="personal_leave",
        start=date(2026, 11, 24),
        end=date(2026, 11, 24),
        reason="family function",
        event_name=None,
        half_day=False,
        today=TODAY,
        programme=Programme.UG,
        calendar={},
        timetable=TIMETABLE,
        existing=[],
    )
    params.update(overrides)
    return guards.check_request(**params)


def test_valid_leave_has_no_warnings():
    assert check() == []


def test_end_before_start_is_blocked():
    with pytest.raises(RuleViolation, match="end date"):
        check(start=date(2026, 11, 25), end=date(2026, 11, 24))


def test_retrospective_personal_leave_is_blocked():
    with pytest.raises(RuleViolation, match="6.1.2"):
        check(start=date(2026, 11, 20), end=date(2026, 11, 20))


def test_medical_leave_can_be_in_the_past():
    warnings = check(kind="medical_leave", start=date(2026, 11, 19), end=date(2026, 11, 20))
    assert any("medical certificate" in w for w in warnings)


def test_leave_on_internal_assessment_day_is_blocked():
    calendar = guards.events_by_date(
        [{"date": "2026-11-24", "type": "internal_exam", "title": "IA 2 DBMS", "status": "scheduled"}]
    )
    with pytest.raises(RuleViolation, match="6.1.4"):
        check(calendar=calendar)


def test_cancelled_exam_does_not_block():
    calendar = guards.events_by_date(
        [{"date": "2026-11-24", "type": "internal_exam", "title": "IA 2", "status": "cancelled"}]
    )
    assert check(calendar=calendar) == []


def test_on_duty_needs_event_name():
    with pytest.raises(RuleViolation, match="event"):
        check(kind="on_duty")


def test_on_duty_warns_about_proof_deadline_from_circular():
    warnings = check(kind="on_duty", event_name="Smart India Hackathon")
    assert any("Circular 12/2026" in w for w in warnings)


def test_overlapping_request_is_blocked():
    existing = [{"type": "personal_leave", "status": "pending", "from_date": "2026-11-23", "to_date": "2026-11-25"}]
    with pytest.raises(RuleViolation, match="overlaps"):
        check(existing=existing)


def test_rejected_request_does_not_count_as_overlap():
    existing = [{"type": "personal_leave", "status": "rejected", "from_date": "2026-11-24", "to_date": "2026-11-24"}]
    assert check(existing=existing) == []


def test_short_notice_warning():
    warnings = check(
        start=TODAY,
        end=TODAY,
        timetable=[*TIMETABLE, {"weekday": 6, "period": 1, "subject_code": "X", "subject_name": "X"}],
    )
    assert any("24 hours" in w for w in warnings)


def test_pg_students_cannot_take_half_day():
    with pytest.raises(RuleViolation, match="7.2.1"):
        check(programme=Programme.PG, half_day=True)


def test_holiday_only_range_needs_no_leave():
    calendar = guards.events_by_date([{"date": "2026-11-24", "type": "holiday", "title": "Festival"}])
    with pytest.raises(RuleViolation, match="no working days"):
        check(calendar=calendar)


def test_working_saturday_follows_another_weekday():
    calendar = guards.events_by_date(
        [{"date": "2026-11-28", "type": "working_day", "title": "Working Saturday", "follows_weekday": 3}]
    )
    assert guards.schedule_weekday(date(2026, 11, 28), calendar) == 3
    assert guards.schedule_weekday(date(2026, 11, 29), {}) is None


@pytest.mark.parametrize(("attended", "held", "needed"), [(30, 40, 0), (25, 40, 20), (0, 0, 0)])
def test_classes_needed(attended, held, needed):
    assert guards.classes_needed(attended, held, 75) == needed


def test_classes_can_miss():
    assert guards.classes_can_miss(36, 40, 75) == 8


def test_leave_impact_adds_periods_held():
    subjects = [
        {
            "subject_code": "CS304",
            "subject_name": "DBMS",
            "classes_held": 40,
            "classes_attended": 30,
            "classes_od": 0,
            "percentage": 75.0,
        }
    ]
    impact = guards.leave_impact(subjects, TIMETABLE, [date(2026, 11, 24)], {})
    assert impact == [{"subject": "DBMS", "periods_missed": 1, "now": 75.0, "after": 73.2, "below_minimum_after": True}]


DRIVE = {
    "id": 43,
    "company": "Zoho",
    "category": "non_dream",
    "min_cgpa": 7.0,
    "allow_standing_arrears": False,
    "allowed_departments": ["CSE", "ECE"],
    "eligible_years": [4],
    "deadline": "2026-11-26",
    "seats_left": 1,
}
PROFILE = {"department": "CSE", "year_of_study": 4}


def test_eligible_student_has_no_blockers():
    assert guards.placement_blockers(DRIVE, PROFILE, {"cgpa": 8.1, "standing_arrears": 0}, TODAY, []) == []


def test_placement_blockers_explain_every_reason():
    reasons = guards.placement_blockers(
        {**DRIVE, "deadline": "2026-11-20", "seats_left": 0},
        {"department": "MECH", "year_of_study": 3},
        {"cgpa": 6.5, "standing_arrears": 1, "placed_category": "dream"},
        TODAY,
        [{"drive_id": 43}],
    )
    assert len(reasons) == 8
