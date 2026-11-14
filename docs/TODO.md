# TODO

Target: final submission by **14:00 IST** (bonus cutoff 14:15, close 14:45). Last update: 12:00.

## 0. Inputs from Kuzhandayan
- [x] College API URL, Swagger, participant key (tested 11:15)
- [x] Groq, Gemini, Deepgram keys (verified 11:40)
- [x] Student test login (`arjun`, from the Swagger example)
- [ ] **Teacher test login** ("How to connect")
- [ ] **Supabase password** in `DATABASE_URL` (currently the literal word `PASSWORD`)
- [ ] GitHub repo pushed (public, `main` only)
- [ ] Render blueprint deployed + env values set
- [ ] Uptime ping on `/api/health`

## 1. Setup — done
- [x] Docs, `.env.example`, Dockerfile (prod), hot-reload `docker compose`, `render.yaml`
- [x] `docs/COLLEGE_API.md` from Swagger, verified live

## 2. Backend — done
- [x] Config, errors, logging, rate limit, security headers, server-side sessions
- [x] College client + college clock; knowledge base (BM25, auto refresh)
- [x] Role-scoped tools, handbook guards, confirm/cancel (in code, cross-turn, idempotent)
- [x] LLM chain with cooldown + Gemini history flattening + date table
- [x] Public flows verified live (courses, documents, admission)
- [x] Student flows verified live (attendance, timetable, calendar, placements, leave submit #110, cancel)
- [ ] Teacher flows verified live

## 3. Voice — done
- [x] STT chain, TTS chain, owner-scoped audio URLs, noise handling
- [ ] Real microphone test in a browser (local `docker compose up`)

## 4. Frontend — done
- [x] Home, Login, Assistant, History; VAD recorder; hands-free; text fallback; accessibility
- [x] Visual check (desktop + chat screenshot); fixed the newer-Chrome `scrollIntoView` crash

## 5. Ship 1 (→ 13:15)
- [ ] Deploy, smoke test over https
- [ ] Submission 1

## 6. Harden (→ 13:50)
- [x] 50 backend tests + 5 frontend tests, ruff clean, tsc clean
- [x] README: deploy steps + known limitations
- [ ] API-level tests (FastAPI TestClient with a fake college API)
- [ ] Act on leaderboard feedback
- [ ] README live link
- [ ] Final submission (before 14:00)
