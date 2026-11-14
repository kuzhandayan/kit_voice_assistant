# College API (provided — we only consume it)

- Base URL: `https://ht.knowvally.com` · Swagger: `/docs` · Spec: `/openapi.json` (OAS 3.1, v1.0.0)
- Every call: header `X-Participant-Key: <key>` (env `COLLEGE_PARTICIPANT_KEY`). Missing → `401`.
- User calls: also `Authorization: Bearer <access_token>` from `POST /v1/auth/login` (JWT, 8 h).
- Writes accept `Idempotency-Key` header (admissions, leave/OD requests) → we send the pending-action id.
- Error shape: `{"error": {"code": "...", "message": "...", "field": null}}`.
- Verified live 11:15 IST: health/today/college/courses/documents/drives = 200; no key = 401.

## Critical facts
- **College date ≠ real date.** `/v1/today` returned `2026-11-21` (Sat) while real date was 2026-11-14. All date logic ("today", "tomorrow", deadlines, exam-day checks) uses `/v1/today`, never the server clock.
- **Documents are dynamic.** `/v1/documents` lists handbooks, brochure, lesson notes, circulars, each with `effective_date`, `applies_to` and `is_surprise`. New ones can appear mid-event. Load from the API at startup + refresh on a TTL; pick the newest effective version per type that is not in the future.
- Two handbooks exist (2025.1, 2026.1) → use 2026.1 (effective 2026-07-01). Circulars override the handbook (e.g. Circular 12/2026: on-duty proof within 3 working days for B.Tech).
- Calendar events have `type` (holiday / exam / working_day …) and `follows_weekday` (a working day can follow another day's timetable).

## Endpoints

### Public (key only)
| Method | Path | Use |
|---|---|---|
| GET | `/v1/health` | health |
| GET | `/v1/today` | college date, weekday (1=Mon…7=Sun), timezone |
| GET | `/v1/college` | name, tagline, description, contact |
| GET | `/v1/courses` | code, name, department, min_12th_percent, annual_fee, hostel_fee, seats |
| POST | `/v1/admissions/applications` | body `{full_name, phone, email, course_code, twelfth_percent}` → `{id, status, created_at, …}` |
| GET | `/v1/documents` | list docs (`id, title, type, version, effective_date, applies_to, download_url, is_surprise`) |
| GET | `/v1/documents/{id}/file` | PDF |
| GET | `/v1/placements/drives` | `company, category, min_cgpa, allow_standing_arrears, allowed_departments, eligible_years, deadline, seats_total, seats_left` |

### Auth
| Method | Path | Use |
|---|---|---|
| POST | `/v1/auth/login` | `{login_id, password}` → `{access_token, token_type, expires_in, user}` |
| GET | `/v1/me` | `UserSummary {id, login_id, full_name, role, department, class_id, class_code, programme, year_of_study, notes}` |

### Student (key + bearer)
| Method | Path | Use |
|---|---|---|
| GET | `/v1/me/academics` | cgpa, standing_arrears, placed_company, placed_category |
| GET | `/v1/me/subjects` | subjects (id, code, name, class_id) |
| GET | `/v1/me/timetable` | slots (weekday 1–6, period, start/end, subject) |
| GET | `/v1/calendar?from&to` | holidays, exams, working days |
| GET | `/v1/me/attendance` | overall % + per subject (held, attended, od, absent, %) |
| GET | `/v1/me/attendance/sessions?subject&from&to` | per-session history |
| GET | `/v1/me/requests` | my leave/OD requests |
| POST | `/v1/me/requests` | `{type: personal_leave|medical_leave|on_duty, from_date, to_date, half_day?, reason, event_name? (required for on_duty)}` |
| GET | `/v1/me/requests/{id}` | detail |
| POST | `/v1/me/requests/{id}/cancel` | cancel pending/approved before start date |
| POST | `/v1/placements/drives/{id}/register` | register (atomic seat) |
| GET | `/v1/me/placements` | my registrations |

### Teacher (key + bearer)
| Method | Path | Use |
|---|---|---|
| GET | `/v1/teacher/classes` | classes the teacher may act on **today** (`role_type`, `valid_until`) |
| GET | `/v1/teacher/requests?status` | requests from authorised classes |
| GET | `/v1/teacher/classes/{class_id}/attendance` | student-wise attendance |
| POST | `/v1/teacher/requests/{id}/approve` | body `{comment?}` |
| POST | `/v1/teacher/requests/{id}/reject` | body `{reason}` (mandatory) |

## Sample data (sandbox QH-17F0AC)
- Courses: BTECH-CSE (min 75%, ₹1,25,000, 120 seats), BTECH-ECE (70%, ₹1,10,000, 60), BTECH-MECH (60%, ₹95,000, 60).
- Drives: Freshworks (dream, CGPA 8, CSE, no arrears, deadline 2026-11-28), TCS (non_dream, 6.0, all, arrears ok, 2026-12-01), Zoho (non_dream, 7.0, CSE/ECE, no arrears, 2026-11-26, 1 seat left).
- Test login (example in the Swagger spec): student `arjun` / `Kit@2026` → Arjun K, CSE-2A, UG (B.Tech), year 2, user id 172. Teacher login: from "How to connect" on the challenge page.
- Calendar event types seen: `holiday`, `internal_exam` (status `active`). Example: 2026-11-23 "DBMS Internal Assessment Exam".
- `programme` in `/v1/me` is `UG` / `PG` (not "B.Tech").
