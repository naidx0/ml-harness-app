"""The portfile guard asks the incumbent engine, not the process table.

On 2026-09-23 a scratch engine died, Windows reused its pid for a browser
renderer, and the next engine read that pid as "still running": it deferred,
never published its token, and every client got 401. `write_portfile` now
defers only when the engine the file describes ANSWERS `/health` with the
file's own `engine_id`. Three cases, each producing only its own exit:

  - a live pid and nothing answering  -> publish (the reuse case)
  - a live pid and a DIFFERENT engine  -> publish (the file is stale)
  - a live pid and the SAME engine     -> defer (the incumbent is real)

The "live pid" is this test's own process, which is as alive as a pid gets,
so the old guard alone would defer every time. The incumbent is a tiny HTTP
server this test owns, on a port it picked.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import support  # noqa: F401  - puts the repo root on the path

from app import security


def _serve(engine_id: str) -> tuple[HTTPServer, str]:
    class Health(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - the stdlib's spelling
            body = json.dumps({"engine": {"engine_id": engine_id}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


class TheGuardAsksTheIncumbentTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.path = Path(self.scratch.name) / "engine.json"
        self.servers: list[HTTPServer] = []

    def tearDown(self):
        for server in self.servers:
            server.shutdown()
        self.scratch.cleanup()

    def _plant(self, base_url: str, engine_id: str) -> None:
        # A live pid: this very process. The old guard deferred on this alone.
        self.path.write_text(
            json.dumps(
                {
                    "pid": os.getpid() + 0,
                    "base_url": base_url,
                    "token": "somebody-elses-token",
                    "engine": {"engine_id": engine_id},
                }
            ),
            encoding="utf-8",
        )

    def _pid_that_is_alive_but_not_us(self) -> int:
        # os.getpid() is skipped by the guard as "ours"; the parent process
        # is alive on every platform this runs on and is never this engine.
        return os.getppid()

    def _plant_alive(self, base_url: str, engine_id: str) -> None:
        self._plant(base_url, engine_id)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["pid"] = self._pid_that_is_alive_but_not_us()
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_a_live_pid_with_nothing_answering_is_overwritten(self):
        server, base = _serve("whatever")
        server.shutdown()  # the port is now dead: the pid-reuse case
        self._plant_alive(base, "old-engine")
        security.write_portfile(port=8123, path=self.path)
        written = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(written["pid"], os.getpid())
        self.assertNotEqual(written["token"], "somebody-elses-token")

    def test_a_live_pid_with_a_different_engine_answering_is_overwritten(self):
        server, base = _serve("some-other-engine")
        self.servers.append(server)
        self._plant_alive(base, "old-engine")
        security.write_portfile(port=8123, path=self.path)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["pid"], os.getpid())

    def test_the_real_incumbent_keeps_its_file(self):
        server, base = _serve("old-engine")
        self.servers.append(server)
        self._plant_alive(base, "old-engine")
        security.write_portfile(port=8123, path=self.path)
        written = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(written["token"], "somebody-elses-token", "a live incumbent's file was stolen")


if __name__ == "__main__":
    unittest.main()
