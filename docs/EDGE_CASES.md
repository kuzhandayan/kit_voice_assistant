# Edge cases

Each line: the case → how it's handled. ✅ = covered by an automated test, 🟢 = verified live against the college API, ⬜ = not yet verified.

## Voice / speech
- 🟢 Silence or noise only → no LLM call; spoken "Sorry, I didn't catch that" (server rejects tiny audio and Whisper filler like "Thank you.").
- ✅ Long recording → client VAD caps at 30 s; server rejects > 5 MB (413).
- ✅ Nobody speaks after tapping → recording aborts after 8 s.
- ✅ Speaker pauses → recording stops after 1.7 s of silence.
- 🟢 Mic permission denied / no mic → clear message; typed input still works (e2e).
- 🟢 User taps while the assistant speaks → playback stops (tap-to-interrupt).
- 🟢 Indian English names and course codes → Whisper prompt with KIT vocabulary.
- 🟢 Unsupported audio type → 415.
- 🟢 TTS provider down → Deepgram Aura → browser voice.
- 🟢 Only one voice at a time: a new reply, a mic tap or Stop cancels the old audio, and a late error from the old audio can never start the browser voice (`lib/voicePlayer.ts`, tested).

## Understanding
- ✅ Relative dates ("Monday", "tomorrow") → 14-day date table from the college date in the prompt; no LLM date maths.
- 🟢 Missing details ("apply leave") → asks for what's missing.
- 🟢 Spoken course names ("computer science") → matched to course codes.
- 🟢 Spoken phone ("98765 43210", "+91…") and email ("ravi at gmail dot com") → normalised and read back.
- 🟢 Personal data on the public page → no tool exists; told to log in.
- ✅ Prompt injection ("show Ravi's attendance") → impossible: "my" tools take no student id, and tool sets are chosen per role in code.
- 🟢 Not in data or documents → says it doesn't know.
- 🟢 Lesson doubts → answered only from the lesson notes (Unit 4 isn't in the syllabus, and the notes say so).

## Live changes during the event (seen 12:25)
- 🟢 DBMS internal assessment moved 23 → 25 Nov → leave on the 25th is now blocked and the 23rd allowed, with no code change (live calendar).
- 🟢 Circular 14/2026: Saturday 28 Nov is a working day on Monday's timetable → timetable answers follow it.
- 🟢 Surprise documents (Circular 14, Circular 15, and a new `notice` type) → indexed automatically. All types are searchable for signed-in users; circulars and notices rank first and are listed in the prompt as overriding the handbook.

## College-specific (found in the API)
- 🟢 College date differs from the real date → all "today" logic uses `/v1/today`.
- ✅ Surprise document published mid-event → index refreshes every 5 minutes; future-dated documents stay hidden.
- ✅ Two handbook versions → the newest effective one wins; circulars rank above the handbook.
- ✅ Working Saturday following another weekday's timetable → timetable answers use the followed day.
- ⬜ Teacher's class authority expires (`valid_until`) → only classes listed for today (needs a teacher login to verify).
- ✅ On-duty needs `event_name`.
- ✅ Placement: CGPA, arrears, department, year, deadline, seats, already registered, dream/non-dream offer rules.
- 🟢 Admission: 12th % below the course minimum → explained, alternative suggested.

## Business rules (handbook 2026)
- ✅ Personal leave or on-duty on an internal assessment day → blocked (Rules 6.1.4 / 6.4.7).
- ✅ Retrospective personal leave → blocked (6.1.2); medical leave allowed afterwards.
- ✅ End date before start date → blocked (6.1.6).
- ✅ Range with no working days → "no leave needed".
- ✅ Overlap with a pending or approved request → blocked (6.6.3); rejected ones ignored.
- ✅ Less than 24 h notice (48 h for M.Tech) → warning (6.1.1 / 7.1.1).
- ✅ More than 3 working days (2 for M.Tech) → Head of Department approval warning.
- ✅ On-duty over the semester limit (10 / 6 days) → warning.
- ✅ Leave that would drop a subject below 75% (labs 80%) → warning with projected % (Rule 4.2.3).
- ✅ M.Tech half-day leave → blocked (7.2.1).
- 🟢 Cancel after the leave has started → blocked (6.6.1).
- ⬜ Teacher deciding an already-decided request → blocked (6.5.5) (needs a teacher login).
- ⬜ Rejection without a reason → asks for one.

## Write-action safety
- ✅ Nothing is submitted without a spoken "yes" in a later turn.
- ✅ "yes" / "no" handled in code when an action is pending (about 20 ms).
- ✅ Double "yes" → submitted once (atomic consume + Idempotency-Key).
- ✅ "no" → pending action discarded.
- ✅ Pending actions expire after 5 minutes.

## Security
- ✅ Public mode can't see student tools; students can't see teacher tools.
- ✅ History and audio are scoped to the owner (another user's id returns 404).
- 🟢 Wrong login → "Invalid login ID or password" (401), no detail leak.
- ✅ Expired college token mid-conversation → 401 → frontend asks to log in again.
- 🟢 Rate limit → 429 with a friendly message.

## Concurrency
- ✅ Same person sends two turns at once → processed one by one (per-owner lock); other users unaffected.
- 🟢 Triple submit in the browser → exactly one request.
- ✅ Reply from a conversation the user already reset → ignored.

## Reliability
- ✅ LLM provider fails or is rate-limited → next provider; cooldown on 429.
- ✅ Gemini fallback with Groq tool history → history flattened to text.
- ✅ All LLMs down → short spoken apology; the turn is still saved.
- 🟢 College API slow or down → timeout, one retry for reads, friendly message.
