# TODO

Target: final submission by **14:00 IST** (bonus cutoff 14:15, close 14:45). Last update: 12:28.

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
- [x] Real speech test: generated speech → Whisper → agent → streamed Edge voice (public + student), audio owner check 404
- [x] TTS streams to the browser (playback starts on first chunk)
- [x] Browser + fake-microphone e2e: 23/23 pass (`e2e/run_e2e.py`)
- [x] Handled the live data changes (rescheduled exam, working Saturday, 3 surprise documents incl. new `notice` type)

## 4. Frontend — done
- [x] Home, Login, Assistant, History; VAD recorder; hands-free; text fallback; accessibility
- [x] Browser e2e: login → assistant → history, desktop + mobile, 0 page errors
- [x] Fixed: newer-Chrome `scrollIntoView` crash, page jump on load, UTC times in history, B.Tech label, mobile login button

## 5. Ship 1 (→ 13:15)
- [ ] Deploy, smoke test over https
- [ ] Submission 1

## 6. Harden (→ 13:50)
- [x] 52 backend tests + 5 frontend tests, ruff clean, tsc clean
- [x] README: deploy steps + known limitations
- [x] API-level tests: 25 HTTP tests with a fake college API, LLM, STT and TTS (78 backend tests total)
- [x] `./test.sh` runs everything; `docs/TESTING.md` maps requirements to tests
- [x] One turn at a time per person (backend lock + frontend busy guard); 82 backend tests; e2e 23/23
- [ ] Act on leaderboard feedback
- [ ] README live link
- [ ] Final submission (before 14:00)
