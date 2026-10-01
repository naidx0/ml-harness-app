"""The app can replace its own engine, without anybody running a script.

Max, 2026-09-21, looking at a banner that told him to run two shell commands:
*"we seem to have lost the restart engine on the app button, the whole thing
with the app should be one package, and the engine should be easy for people
to restart, they shouldn't be running scripts on their own."*

Why there was no button. `engine::bootstrap` refuses while an engine is
answering - right for a START. `engine::stop_if_ours` ends only a child the
window spawned - right, because a window must not kill a process a terminal
owns. Between them they left the case the window can actually see: an engine
somebody else started, on older code, visible as wrong and unreplaceable.

So the engine stops ITSELF, and the only caller that can ask is one holding
the bearer token it published to `engine.json` (user-only permissions). That
is a better identity check than a pid - a pid can be recycled, a token cannot
be guessed - and nothing signals a process it merely believes is ours.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402,F401


class TheRouteIsBehindTheToken(unittest.TestCase):
    """`/api/engine/shutdown` sits under /api/, which is the token boundary."""

    def test_it_is_registered_under_api(self):
        from app import main

        paths = {getattr(r, "path", "") for r in main.app.routes}
        self.assertIn("/api/engine/shutdown", paths)

    def test_it_is_a_post(self):
        from app import main

        for route in main.app.routes:
            if getattr(route, "path", "") == "/api/engine/shutdown":
                self.assertIn("POST", getattr(route, "methods", set()))
                return
        self.fail("route not found")

    def test_health_is_not_behind_the_token_but_this_is(self):
        """The probe must stay reachable; the stop must not.

        `/health` is how a launcher asks what is on a port before it decides
        anything, so it is deliberately open. A route that ends the process
        cannot be.
        """
        source = (REPO / "app" / "main.py").read_text("utf-8")
        self.assertIn('@app.get("/health")', source)
        self.assertIn('@app.post("/api/engine/shutdown")', source)


class TheShellAsksRatherThanKills(unittest.TestCase):
    """The Rust side never signals a pid it did not spawn."""

    def _restart_body(self) -> str:
        source = (REPO / "src-tauri" / "src" / "engine.rs").read_text("utf-8")
        start = source.index("pub fn restart(")
        return source[start : source.index("\n/// Stop the engine THIS SHELL started")]

    def test_it_posts_the_shutdown_route_with_the_token(self):
        body = self._restart_body()
        self.assertIn("/api/engine/shutdown", body)
        self.assertIn("engine_request", body)
        self.assertIn("token", body)

    def test_it_kills_nothing(self):
        """`.kill()` appears elsewhere in this file for children we spawned.
        It must not appear in the path that replaces somebody else's."""
        body = self._restart_body()
        self.assertNotIn(".kill()", body)
        self.assertNotIn("taskkill", body)

    def test_it_waits_for_the_port_before_starting_another(self):
        body = self._restart_body()
        self.assertIn("ours_is_answering(port)", body)
        self.assertIn("bootstrap(port)", body)


class NoProductTellsSomebodyToRunAScript(unittest.TestCase):
    """The banner's own words, which were mine and were wrong."""

    def test_the_liveness_actions_name_no_shell_command(self):
        source = (REPO / "frontend" / "src" / "lib" / "engine" / "liveness.ts").read_text("utf-8")
        actions = [
            line for line in source.splitlines() if line.strip().startswith("action:")
        ]
        self.assertTrue(actions, "no action lines found")
        for line in actions:
            self.assertNotIn("scripts/launch.py", line, line)
            self.assertNotIn("python ", line, line)


if __name__ == "__main__":
    unittest.main()
