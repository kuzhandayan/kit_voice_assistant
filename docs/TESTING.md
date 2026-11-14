# Testing

```bash
docker compose up -d --build
./test.sh          # lint + 85 backend tests + frontend tests, about 10 s, no keys needed
./test.sh --e2e    # adds the 23-check browser + microphone run against the live AI
```

## Layers

| Layer | Where | Network / keys | What it proves |
|---|---|---|---|
| Unit | `backend/tests/test_guards.py`, `test_services.py`, `test_registry.py` | none | Handbook rules, attendance maths, placement eligibility, document selection and search, provider fallback and cooldown, yes/no handling, confirm-once, owner scoping |
| API | `backend/tests/test_api.py` (fakes in `tests/fakes.py`) | none | The whole app over HTTP with a fake college system, LLM, STT and TTS |
| Frontend | `frontend/src/lib/vad.test.ts` | none | Voice activity detection: start, silence stop, no-speech abort, max length |
| End-to-end | `e2e/run_e2e.py` | live app + keys | Real Chromium; a fake microphone plays recorded speech through the full voice path |

## Requirement → test

| Requirement | Proved by |
|---|---|
| Voice conversation | e2e: mic → transcript → spoken answer, public and student; API: `test_voice_turn_transcribes_and_answers` |
| Correct answers | e2e: fees, courses, attendance, circular over handbook, working Saturday, lesson notes |
| Leave and on-duty requests | API: `test_leave_needs_yes_and_is_submitted_exactly_once`, `test_leave_on_exam_day_is_blocked`; unit: 20 rule tests |
| Saved history | API: `test_history_lists_and_reads_own_conversations_only`; e2e: history page |
| Admission on public page | API: `test_public_admission_flow`; e2e: refused below minimum, read back, submitted |
| Works if one AI service fails | unit: `test_fallback_*`, `test_flatten_tool_history_for_gemini`, `test_tts_stream_falls_back_when_edge_fails` |
| Public sees no student data | API: `test_public_visitor_cannot_reach_student_data_even_if_the_model_tries`; unit: role scoping |
| Security | API: httpOnly session, no token leak, wrong password, expired token → 401, owner-only audio and history, rate limit, input limits, 415/413 on audio |
| Microphone denied | e2e: clear message, typing still works |
