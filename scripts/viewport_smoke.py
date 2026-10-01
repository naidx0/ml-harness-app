#!/usr/bin/env python3
"""Load the UI specimen at several viewport widths before a push.

    python scripts/viewport_smoke.py
    python scripts/viewport_smoke.py --check   # say what a push would run

WHY THIS EXISTS

A composer / goal-bar change that looks fine at 1600 can crush the chat at
1280 or spill horizontally at 820. Stage already learned that lesson
(docs/PHASES.md S6–S7): `document.scrollWidth > clientWidth` is the check a
screenshot alone does not replace. This script runs that check at the widths
we care about, against a static Basilica specimen that mirrors the composer
control surface — no engine, no token, no live database.

It is deliberately NOT the full React app. Wiring Vite + engine into a
pre-push hook would write into whatever DB the engine opened and take minutes.
The specimen is the surface we are redesigning; when the redesign lands in
React, the same runner can point at `vite preview` without changing the
assertion.

FAIL MODE

- Chrome/Edge missing → exit 0 with SKIP (fail-open, same spirit as
  install_hooks.py: a guard that cannot run must not block every push).
- Any width reports RED → exit 1.
- Browser dump lacks a verdict line → exit 1 (silent pass is forbidden).

Installed as a pre-push hook by `python scripts/install_hooks.py`.
"""

from __future__ import annotations

import argparse
import http.server
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DRAFTS = REPO / "docs" / "brand" / "drafts"
SPECIMEN = DRAFTS / "composer-three-paths.html"
RUNNER = DRAFTS / "viewport-runner.html"
MARKER = "ml-harness:viewport_smoke"

#: Widths Stage / Journey already walk in PHASES (plus the book's ~820 floor).
VIEWPORTS = (820, 1024, 1280, 1600)


def find_browser() -> Path | None:
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path.home() / r"AppData\Local\Microsoft\Edge\Application\msedge.exe",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def serve(directory: Path) -> tuple[socketserver.TCPServer, int]:
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, format, *args):  # noqa: A003
            return

    httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    httpd.allow_reuse_address = True
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, port


def dump_dom(browser: Path, url: str, width: int) -> str:
    """Headless Chromium at a fixed window size; dump DOM after virtual time."""
    with tempfile.TemporaryDirectory(prefix="mlh-viewport-") as tmp:
        cmd = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            f"--window-size={width},900",
            "--virtual-time-budget=2000",
            "--dump-dom",
            url,
        ]
        ran = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=tmp,
        )
        body = ran.stdout or ""
        if not body.strip():
            body = ran.stderr or ""
        return body


def verdict_from_dom(dom: str) -> tuple[str, str]:
    """Return (status, detail) where status is GREEN|RED|MISSING."""
    needle = 'id="viewport-smoke-verdict"'
    at = dom.find(needle)
    if at < 0:
        for alt in (
            "id='viewport-smoke-verdict'",
            'id=\\"viewport-smoke-verdict\\"',
        ):
            at = dom.find(alt)
            if at >= 0:
                break
    if at < 0:
        return "MISSING", "specimen never wrote #viewport-smoke-verdict"
    gt = dom.find(">", at)
    close = dom.find("</", gt)
    if gt < 0 or close < 0:
        return "MISSING", "verdict element had no text"
    text = dom[gt + 1 : close].strip()
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#39;", "'")
    )
    if text.startswith("GREEN"):
        return "GREEN", text
    if text.startswith("RED"):
        return "RED", text
    return "MISSING", f"unexpected verdict text: {text!r}"


def run_smoke() -> int:
    if not SPECIMEN.is_file():
        print(f"REFUSED: missing specimen at {SPECIMEN}", file=sys.stderr)
        return 1
    browser = find_browser()
    if browser is None:
        print(
            "SKIP: no Chrome/Edge found — viewport smoke not run "
            "(install a browser, or run with one on PATH).",
            file=sys.stderr,
        )
        return 0

    httpd, port = serve(DRAFTS)
    try:
        time.sleep(0.15)
        print(f"viewport_smoke: {browser.name}")
        print(f"viewport_smoke: widths {', '.join(str(w) for w in VIEWPORTS)}")
        failed: list[str] = []
        for width in VIEWPORTS:
            url = (
                f"http://127.0.0.1:{port}/composer-three-paths.html"
                f"?smoke=1&w={width}"
            )
            dom = dump_dom(browser, url, width)
            status, detail = verdict_from_dom(dom)
            print(f"  [{width}] {detail}")
            if status != "GREEN":
                failed.append(f"{width}px ({status})")
        if not failed:
            print("GREEN: no horizontal overflow at " + "/".join(str(w) for w in VIEWPORTS))
            return 0
        print("RED: failed at " + ", ".join(failed), file=sys.stderr)
        return 1
    finally:
        httpd.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="print what would run; do not launch a browser",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.check:
        browser = find_browser()
        print(f"specimen: {SPECIMEN} ({'present' if SPECIMEN.is_file() else 'MISSING'})")
        print(f"runner: {RUNNER} ({'present' if RUNNER.is_file() else 'MISSING'})")
        print(f"browser: {browser or 'none'}")
        print(f"widths: {', '.join(str(w) for w in VIEWPORTS)}")
        print(f"marker: {MARKER}")
        return 0 if SPECIMEN.is_file() else 1
    return run_smoke()


if __name__ == "__main__":
    raise SystemExit(main())
