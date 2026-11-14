# CLAUDE.md — KIT Voice Assistant (Quirri Hiring Hackathon)

Read this first in every session. Keep it current.

## Deadlines (IST, Sat 14 Nov 2026)
| Time | Milestone |
|---|---|
| 10:45 | Problem released |
| 11:10 | Docs + plan done |
| 12:15 | Backend: college API client, agent, tools working via text |
| 12:45 | Voice loop (STT → agent → TTS) working locally |
| 13:15 | Frontend pages done; deploy; **submission 1** (get leaderboard feedback) |
| 13:45 | Fix review feedback, tests, edge cases; **submission 2** |
| **14:00** | **Our hard target: final submission** |
| 14:15 | +10 early-bonus cutoff (last submission must be before this) |
| 14:45 | Submissions close |

Max 3 submissions, latest counts. Never let a later submission be worse than an earlier one.

## Scoring (what we optimise for)
- Requirements delivered (must-haves count double): voice conversation, correct answers, leave + on-duty requests, saved history.
- Nice to have: placement registration, lesson doubts, admission enquiries + application on public page, AI-service failover.
- Also scored: security & reliability, architecture & design, code quality & tests.
- The app must run at the deployed https link. A broken app is disqualified.

## Hard rules from the problem
- Speech-to-text must use a speech service. **Browser Web Speech API recognition is NOT allowed.**
- Public mode can never see student data. Logged-in mode only ever acts for the logged-in person.
- We don't build the college system, dashboards, charts or uploads.
- Public GitHub repo, single branch, < 10 MB, README with what + how to run.
- "Things may change during the event" — keep endpoints, rules and knowledge files config-driven.

## Status (12:28)
Backend, voice, frontend done and verified live with student `arjun` / `Kit@2026`. Waiting on: teacher login, Supabase password, GitHub push, Render deploy. See `docs/TODO.md`.

## Hard-won lessons (don't regress)
- College date ≠ real date: always `CollegeClock`.
- Groq free tier ≈ 8K tokens/min per model → keep prompts small; cooldown handles 429.
- Gemini 3 rejects foreign tool-call history → `flatten_tool_history`.
- LLMs miscount weekdays → date table in the prompt.
- Never let the LLM confirm in the same turn it prepared; yes/no is handled in code.
- Chrome's `scrollIntoView` returns a Promise → never return it from `useEffect`; and it scrolls the whole page, so scroll the transcript box with `scrollTop` instead.
- SQLite drops timezones → API schemas force UTC (`UtcDatetime`).
- The college data changes live (exam rescheduled, surprise circulars/notices) → never hardcode dates or document types.
- Groq rejects `null` for optional tool args unless the schema allows it → `allow_null_optionals` for Groq only.
- Apple Silicon containers don't get `greenlet` with plain `sqlalchemy` → use `sqlalchemy[asyncio]`.

## Working rules
- Code quality first: small modules, typed, one responsibility each, shared components over copy-paste.
- Keep code comments minimal. Explain design in `docs/*.md`, not in code.
- Every new module or decision → update `docs/ARCHITECTURE.md`. Every finished task → tick `docs/TODO.md`.
- Security is enforced in code (role-scoped tool registry, server-side user id), never by the prompt alone.
- Every external call (college API, STT, LLM, TTS) goes through timeouts + retry + fallback.
- Secrets only in `.env`. Never commit `.env` or keys.
- Token economy: don't re-read large files, don't explore outside this folder, keep diffs focused.

## Stack
- Backend: Python 3.11, FastAPI, httpx, SQLAlchemy (SQLite locally, Postgres via `DATABASE_URL`), pydantic-settings, pytest.
- Agent: OpenAI-compatible tool calling. LLM chain (`LLM_CHAIN`): Groq gpt-oss-120b → Groq qwen3.8-27b → Gemini 3.5 Flash (verified 11:40, all tool-calling, 0.4–1.7 s).
- STT chain: Groq Whisper (`whisper-large-v3-turbo`) → Deepgram Nova-3.
- TTS chain: Edge TTS (free, no key) → Deepgram Aura-2 → text-only (client speaks with speechSynthesis as last resort).
- Knowledge: PDFs parsed at startup → chunked → BM25 search (no embedding API, no extra failure point).
- Frontend: React + Vite + TypeScript, plain CSS. MediaRecorder + silence detection.
- Storage: Postgres (compose container locally; Supabase session pooler in production).
- Dev: `docker compose up` = backend (uvicorn --reload) + frontend (Vite HMR) + Postgres, all with hot reload. Open :5173.
- Prod: one multi-stage `Dockerfile` (Node builds frontend, FastAPI serves it), used only by Render.
- Deploy: Render blueprint (`render.yaml`), one app, one URL; Supabase session pooler for `DATABASE_URL`; uptime ping on `/api/health`. Vercel split rejected (cross-site cookies, two deploys).

## Commands
```bash
cp .env.example .env
docker compose up --build                                   # http://localhost:5173, hot reload
./test.sh            # lint + all tests inside Docker; ./test.sh --e2e adds the browser + mic run
```

## Working copy / sync (Claude sessions)
Claude edits in its cloud sandbox and syncs to `~/personal-projects/kit-voice-assistant` with a tarball in `.sync/` (git-ignored). Never write `.env` from tools; the user owns it.

## Docs map
- `README.md` — for a developer: what, how to run, how it works.
- `docs/ARCHITECTURE.md` — components, flows, decisions.
- `docs/EDGE_CASES.md` — edge cases and how each is handled.
- `docs/TODO.md` — live task list.
- `docs/COLLEGE_API.md` — endpoints of the provided college API (from Swagger, verified live).
