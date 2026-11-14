"""End-to-end check of the running app in a real Chromium, including the microphone.

Chromium's fake microphone plays a WAV file, so the real path is exercised:
mic permission -> MediaRecorder -> silence detection -> upload -> STT -> agent -> streamed TTS.

Usage:  python e2e/run_e2e.py --base http://localhost:5173 --audio-dir e2e/audio
Needs:  pip install playwright && playwright install chromium
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

REPLY = ".bubble--assistant:not(.bubble--thinking)"
STUDENT = ("arjun", "Kit@2026")


@dataclass
class Report:
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        (self.passed if ok else self.failed).append(name)
        print(
            f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""),
            flush=True,
        )


def launch(pw: Playwright, wav: Path | None = None, grant_mic: bool = True) -> Browser:
    args = [
        "--use-fake-device-for-media-stream",
        "--autoplay-policy=no-user-gesture-required",
    ]
    if wav:
        args.append(f"--use-file-for-fake-audio-capture={wav}")
    if grant_mic:
        args.append("--use-fake-ui-for-media-stream")
    return pw.chromium.launch(args=args)


def new_page(browser: Browser, base: str, grant_mic: bool = True) -> Page:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    if grant_mic:
        context.grant_permissions(["microphone"], origin=base)
    page = context.new_page()
    page.errors = []  # type: ignore[attr-defined]
    page.on("pageerror", lambda e: page.errors.append(str(e)))  # type: ignore[attr-defined]
    return page


def replies(page: Page) -> list[str]:
    return page.locator(REPLY).all_inner_texts()


def ask(page: Page, text: str, timeout: float = 45) -> str:
    before = len(replies(page))
    page.fill("input[aria-label='Type your question']", text)
    page.click("button:has-text('Send')")
    page.wait_for_function(
        f"document.querySelectorAll('{REPLY}').length > {before}",
        timeout=timeout * 1000,
    )
    return replies(page)[-1]


def speak(page: Page, timeout: float = 60) -> tuple[str, str, int]:
    """Clicks the mic; the fake mic plays the WAV. Returns (transcript, reply, tts_status)."""
    toggle = page.locator(".toggle input")
    if toggle.is_checked():
        toggle.uncheck()
    before = len(replies(page))
    statuses: list[int] = []
    page.on(
        "response",
        lambda r: statuses.append(r.status) if "/api/voice/tts/" in r.url else None,
    )
    page.click(".orb")
    page.wait_for_function(
        f"document.querySelectorAll('{REPLY}').length > {before}",
        timeout=timeout * 1000,
    )
    deadline = time.time() + 20
    while not statuses and time.time() < deadline:
        page.wait_for_timeout(250)
    user = page.locator(".bubble--user").all_inner_texts()
    return (
        (user[-1] if user else ""),
        replies(page)[-1],
        (statuses[-1] if statuses else 0),
    )


def has(text: str, *patterns: str) -> bool:
    return all(re.search(p, text, re.IGNORECASE) for p in patterns)


def login(page: Page, base: str) -> None:
    page.goto(f"{base}/login", wait_until="networkidle")
    page.fill("input[autocomplete=username]", STUDENT[0])
    page.fill("input[type=password]", STUDENT[1])
    page.click("button[type=submit]")
    page.wait_for_url("**/assistant", timeout=15000)


def run(base: str, audio: Path) -> Report:
    r = Report()
    with sync_playwright() as pw:
        # 1. Public page: voice
        browser = launch(pw, audio / "pub_hostel.wav")
        page = new_page(browser, base)
        page.goto(base, wait_until="networkidle")
        r.check(
            "home page shows courses table", page.locator("table tbody tr").count() >= 3
        )
        t0 = time.time()
        heard, reply, tts = speak(page)
        r.check(
            "public voice: mic -> transcript",
            has(heard, r"hostel", r"E\s?C\s?E|electronics"),
            heard,
        )
        r.check(
            "public voice: correct spoken answer",
            has(reply, r"60,?000|sixty thousand"),
            f"{reply} ({time.time() - t0:.1f}s)",
        )
        r.check("public voice: reply audio streamed", tts == 200, f"tts status {tts}")

        # 2. Public page: typed questions and admission flow
        reply = ask(page, "What courses do you offer?")
        r.check(
            "public: lists all courses",
            has(reply, r"computer", r"electronics", r"mechanical"),
            reply,
        )
        reply = ask(page, "What is my attendance?")
        r.check(
            "public: refuses personal data, asks to log in",
            has(reply, r"log\s?in"),
            reply,
        )
        reply = ask(
            page,
            "Apply for CSE admission. Name Priya Raman, phone 98765 43210, email priya.r@example.com, 12th marks 70 percent",
        )
        r.check("admission: below CSE minimum is refused", has(reply, r"75"), reply)
        reply = ask(page, "Okay, apply for ECE instead")
        r.check(
            "admission: read back before submitting",
            has(reply, r"electronics|ECE", r"submit|confirm|shall"),
            reply,
        )
        reply = ask(page, "yes")
        r.check(
            "admission: submitted after yes",
            has(reply, r"submitted|reference|done"),
            reply,
        )
        r.check(
            "public page: no browser errors", not page.errors, "; ".join(page.errors)
        )  # type: ignore[attr-defined]
        browser.close()

        # 3. Student: voice + rules
        browser = launch(pw, audio / "stu_att.wav")
        page = new_page(browser, base)
        login(page, base)
        r.check("student: login works", "Arjun" in page.inner_text("h1"))
        heard, reply, tts = speak(page)
        r.check("student voice: transcript", has(heard, r"attendance"), heard)
        r.check(
            "student voice: real attendance from college system",
            has(reply, r"\d+(\.\d+)?\s?(%|percent)"),
            reply,
        )
        r.check("student voice: reply audio streamed", tts == 200, f"tts status {tts}")
        reply = ask(page, "Apply personal leave on 25 November for a family function")
        r.check(
            "rule: no leave on (rescheduled) internal assessment day",
            has(reply, r"assessment|exam"),
            reply,
        )
        reply = ask(page, "How many working days do I get to submit on-duty proof?")
        r.check(
            "documents: circular overrides handbook (3 days)",
            has(reply, r"\bthree\b|\b3 working")
            and not has(reply, r"\bfive\b|\b5 working"),
            reply,
        )
        reply = ask(page, "Do I have classes on Saturday 28 November?")
        r.check(
            "calendar: working Saturday follows Monday timetable",
            has(reply, r"monday"),
            reply,
        )
        reply = ask(page, "Explain normalisation from the DBMS notes in one line")
        r.check(
            "lesson notes: subject doubt answered",
            has(reply, r"normal|redundan|depend"),
            reply,
        )
        reply = ask(page, "Show me Ravi's attendance")
        r.check(
            "security: can't see another student's data",
            not has(reply, r"Ravi('s)? attendance is \d"),
            reply,
        )
        page.goto(f"{base}/history", wait_until="networkidle")
        r.check(
            "history: conversations listed", page.locator(".history li").count() >= 1
        )
        with page.expect_response(lambda resp: "/api/auth/logout" in resp.url):
            page.click("button:has-text('Log out')")
        page.goto(f"{base}/assistant", wait_until="networkidle")
        r.check("logout: assistant page needs login again", "/login" in page.url)
        r.check(
            "student pages: no browser errors", not page.errors, "; ".join(page.errors)
        )  # type: ignore[attr-defined]
        browser.close()

        # 4. Mic permission denied
        browser = launch(pw, grant_mic=False)
        page = new_page(browser, base, grant_mic=False)
        page.goto(base, wait_until="networkidle")
        page.click(".orb")
        page.wait_for_selector(".notice--error", timeout=10000)
        r.check(
            "mic denied: clear message, typing still works",
            has(page.inner_text(".notice--error"), r"microphone|type"),
        )
        browser.close()
    return r


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:5173")
    parser.add_argument("--audio-dir", default=str(Path(__file__).parent / "audio"))
    opts = parser.parse_args()
    report = run(opts.base.rstrip("/"), Path(opts.audio_dir))
    print(f"\n{len(report.passed)} passed, {len(report.failed)} failed")
    sys.exit(1 if report.failed else 0)
