"""A check that could not run must never report that it passed.

## The incident, 2026-09-20

Max ran ML Harness for a day and a half against an engine started on
2026-09-19 at 01:08 on commit `c0cccd4`, while `main` moved three commits past
it. Two entire cycles of fixes - every refusal, every UI change - were never
executed once. He found it himself, by reading the About panel: *"my build on
my about it says build nine C one nine six."*

Three things had to be true at once, and all three were:

1. **The shell does not start the engine.** `src-tauri/src/lib.rs` says so
   deliberately - starting processes is `scripts/launch.py`'s job. So the
   window attaches to whatever holds port 8078, however old.

2. **`probe_engine` reported the stale engine as current.** Staleness is
   decided by the ENGINE: the caller sends `?expect_build=`, `/health`
   compares and answers 409. `expect_build` defaulted to `None`, so nothing
   was sent, so `/health` answered 200, so the probe said `ours-current` and
   `decide()` said *"its build matches this working tree"*. It did not.

3. **The banner that exists for exactly this could not see it.**
   `liveness.ts` calls `checkAgainstCheckout`, which needs the revision the
   page came from. `engine_status` finds a checkout only when the exe sits in
   one, and an installed app does not, so the verdict was `unverifiable` and
   nothing drew. `__UI_REVISION__` (baked in by `vite.config.ts`) is the
   missing half; the TypeScript side is covered by
   `frontend/src/lib/engine/config.test.ts`.

This file pins (2), and pins the shape of it: the default is what makes the
check happen, and a caller that wants no comparison must say so.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402,F401
from app import identity, launcher  # noqa: E402


class WhatTheProbeSends(unittest.TestCase):
    def _sent(self, **kwargs) -> str:
        """The URL `probe_engine` would fetch, without fetching it."""
        seen: dict[str, str] = {}

        class _Answer:
            status = 200

            def read(self):
                return b'{"service": "ml-harness-engine"}'

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        def _urlopen(request, timeout=0):
            seen["url"] = request.full_url
            return _Answer()

        with mock.patch.object(launcher, "port_is_open", return_value=True), mock.patch(
            "urllib.request.urlopen", _urlopen
        ):
            launcher.probe_engine(8078, **kwargs)
        return seen.get("url", "")

    def test_it_asks_about_this_tree_when_nobody_said_which(self):
        """The default IS the fix. Without it the engine has nothing to compare."""
        expected = identity.code_fingerprint()[0]
        self.assertIn(f"expect_build={expected}", self._sent())

    def test_a_caller_that_names_a_build_still_wins(self):
        self.assertIn("expect_build=abc123", self._sent(expect_build="abc123"))

    def test_a_caller_can_still_ask_only_whether_anybody_is_there(self):
        """Empty string is the explicit opt-out; `None` is no longer one."""
        self.assertNotIn("expect_build", self._sent(expect_build=""))


class WhatTheProbeConcludes(unittest.TestCase):
    """409 is the engine disagreeing, and it must reach `decide` as stale."""

    def _probe(self, status: int, body: bytes):
        class _Error(Exception):
            code = status

            def read(self):
                return body

        import urllib.error

        error = urllib.error.HTTPError("u", status, "", None, None)
        error.read = lambda: body  # type: ignore[method-assign]

        def _urlopen(request, timeout=0):
            raise error

        with mock.patch.object(launcher, "port_is_open", return_value=True), mock.patch(
            "urllib.request.urlopen", _urlopen
        ):
            return launcher.probe_engine(8078)

    def test_a_disagreeing_engine_is_stale_and_gets_replaced(self):
        body = (
            b'{"service": "ml-harness-engine", "mismatch": '
            b'[{"field": "build", "expected": "new", "actual": "old"}]}'
        )
        probe = self._probe(409, body)
        self.assertEqual(probe.state, "ours-stale")
        decision = launcher.decide(probe)
        self.assertEqual(decision.action, "replace")
        self.assertIn("build", decision.reason)


class OneCopyOfEachFunction(unittest.TestCase):
    """`port_is_open`, `probe_engine` and `_unidentified` were each defined
    twice, verbatim, 110 lines apart. Identical today; a trap the first time
    somebody fixes one of them."""

    def test_the_launcher_defines_each_of_them_once(self):
        source = (REPO / "app" / "launcher.py").read_text("utf-8")
        for name in ("def port_is_open(", "def probe_engine(", "def _unidentified("):
            self.assertEqual(source.count(name), 1, name)


if __name__ == "__main__":
    unittest.main()
