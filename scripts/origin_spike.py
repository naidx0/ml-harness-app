"""The Phase V A7 spike: what `Origin` does the shell's WebView actually send?

`docs/THE_PLAN.md` calls this **the single highest-risk unknown** of the
installer milestone, and it is the one step in Phase A that cannot be finished
by writing code. It is a MEASUREMENT of a running WebView, and the only way to
take it is to point one at this script.

## Why it cannot be guessed

`app/security.py::allowed_origins` permits exactly two strings - both spellings
of loopback on the engine's port - and every request carrying anything else is
refused. Vite sidesteps the question entirely by stripping `Origin` in its dev
proxy; under Tauri there is no proxy, so whatever the WebView sends arrives at
the engine unaltered.

Published answers for what Tauri v2 sends on Windows do exist and they disagree
with each other, with the version, and with whether the app uses the custom
protocol or a localhost server. **Widening a security boundary on the strength
of a blog post is the boundary loosened by an assumption**, which is the one
thing invariant 5 exists to stop - and it would be loosened in the place where
being wrong is most expensive.

So: measure it. This script is the measurement.

## What to do with it

1. Run this. It prints a URL and waits.
2. Point the Tauri shell's WebView at that URL - a `devUrl`, a `navigate`, or
   the address bar of the WebView2 window, whichever the scaffold makes easy.
3. It prints every header the WebView sent, with `Origin` and `Sec-Fetch-*`
   called out, and writes the whole thing to `origin-spike.json`.
4. Put the ANSWER into `docs/THE_PLAN.md` under A7, with the Tauri version and
   the WebView2 runtime version beside it, and only then decide what
   `allowed_origins` should say.

## Two things it also answers, for free

`Sec-Fetch-Site` and `Sec-Fetch-Mode` are worth having in the same reading:
together with `Origin` they are what distinguishes "a page this shell loaded"
from "a page somebody else's site loaded in a frame", and a boundary that reads
one without the other is answering half a question.

And it streams a chunked response at the end, because `frontend/src/lib/engine/events.ts`
uses `response.body.getReader()` - so any origin fix has to leave streaming
working, and a WebView that cannot stream is a second finding this trip should
not have to be made twice for.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


#: Not the engine's port. Running this on 8078 would collide with an engine
#: somebody has up, and the point of the spike is the WebView's behaviour rather
#: than the engine's.
DEFAULT_PORT = 8079

#: Where the reading is written, beside the repository so it is easy to paste
#: into THE_PLAN and easy to delete afterwards.
REPORT = Path(__file__).resolve().parents[1] / "origin-spike.json"

#: The headers that decide the question. Everything is recorded; these are the
#: ones printed large.
THE_ANSWER = ("origin", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest", "referer")

_PAGE = """<!doctype html>
<title>Origin spike</title>
<h1>Origin spike</h1>
<p>This page was served to the WebView. What it sent is in the terminal.</p>
<pre id="out">asking again with fetch()...</pre>
<script>
// A SECOND READING, AND IT IS THE ONE THAT MATTERS. The Origin on a top-level
// navigation is not always the Origin on a fetch() from the page that
// navigation loaded, and every request this product makes is the second kind.
fetch("/probe", {method: "POST", body: "{}"})
  .then(r => r.text())
  .then(t => { document.getElementById("out").textContent = t; })
  .catch(e => { document.getElementById("out").textContent = "fetch failed: " + e; });
</script>
"""


class Spike(BaseHTTPRequestHandler):
    seen: list[dict] = []

    def _record(self, kind: str) -> dict:
        headers = {key.lower(): value for key, value in self.headers.items()}
        row = {"kind": kind, "path": self.path, "headers": headers}
        Spike.seen.append(row)
        print(f"\n--- {kind} {self.path}")
        for name in THE_ANSWER:
            print(f"    {name:16} {headers.get(name, '(not sent)')}")
        other = sorted(set(headers) - set(THE_ANSWER))
        if other:
            print(f"    everything else: {', '.join(other)}")
        REPORT.write_text(json.dumps(Spike.seen, indent=2), encoding="utf-8")
        return row

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's interface
        if self.path.startswith("/stream"):
            self._record("GET (stream)")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            for index in range(3):
                self.wfile.write(f"data: chunk {index}\n\n".encode("utf-8"))
                self.wfile.flush()
                time.sleep(0.2)
            return
        self._record("GET (navigation)")
        body = _PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        row = self._record("POST (fetch)")
        body = json.dumps(
            {
                "origin": row["headers"].get("origin", "(not sent)"),
                "sec_fetch_site": row["headers"].get("sec-fetch-site", "(not sent)"),
                "note": (
                    "This is the reading that matters: every request this "
                    "product makes is a fetch from a loaded page, not a "
                    "top-level navigation."
                ),
            },
            indent=2,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:  # noqa: D102 - quieter than the default
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Spike)
    url = f"http://127.0.0.1:{args.port}/"
    print(__doc__.split("## What to do with it")[1].split("## Two things")[0].strip())
    print(f"\nlistening on {url}")
    print(f"the reading is written to {REPORT}")
    print("\nPoint the Tauri WebView here, then read what it sent. Ctrl-C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        if Spike.seen:
            print(f"{len(Spike.seen)} request(s) recorded in {REPORT}")
        else:
            print(
                "NOTHING WAS RECORDED, so nothing was measured. An empty run is "
                "not an answer - it means the WebView never reached this port."
            )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
