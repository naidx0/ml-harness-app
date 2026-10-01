"""`./start.sh` decides four things, and getting any of them wrong costs a day.

The launcher looks at a port and answers: start, reuse, replace, or refuse. The
evening this comes from went wrong at "replace": a pid was read out of
`engine.json`, `taskkill` was pointed at it, it was not the server, and every
step after that was reasoning on top of a false premise.

So the rule these tests exist to hold:

    IT NEVER TERMINATES A PROCESS IT HAS NOT IDENTIFIED, AND THE ONLY
    IDENTIFICATION IT ACCEPTS CAME BACK OVER THE SOCKET IT IS ABOUT TO CLEAR.

Everything that decides lives in `scripts/launch.py` and not in `start.sh`,
which is why this file can exist at all: a bash script and its PowerShell twin
could not be tested, and would disagree with each other inside a week.

The probe tests stand up real HTTP servers on real loopback ports rather than
mocking `urlopen`. A mocked probe would agree with whatever the probe already
believes; the interesting cases here are all about a server behaving in a way
the launcher did not anticipate, and a mock cannot produce one.
"""

from __future__ import annotations

import importlib.util
import json
import re
import socket
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import support

from app import identity


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_launcher():
    """Import `scripts/launch.py` by path.

    By path rather than by adding `scripts/` to `sys.path`, because `launch` is
    a name a dozen packages use and putting that directory on the import path
    for the whole suite is a collision waiting to happen.

    Registered in `sys.modules` BEFORE it is executed, which is not optional:
    `@dataclass` resolves its annotations through `sys.modules[cls.__module__]`
    while the class body is being processed, and a module that is not there yet
    makes it raise `'NoneType' object has no attribute '__dict__'`.
    """
    spec = importlib.util.spec_from_file_location(
        "mlh_launcher", REPO_ROOT / "scripts" / "launch.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


launcher = _load_launcher()


# ---------------------------------------------------------------------------
# A stand-in for whatever is on the port.


class _Server:
    """One HTTP response, served on a real port, until stopped."""

    def __init__(self, status: int, body: bytes):
        self.port = support.free_port()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(outer.body)))
                self.end_headers()
                self.wfile.write(outer.body)

        self.status = status
        self.body = body
        self.httpd = HTTPServer(("127.0.0.1", self.port), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def _engine_body(**overrides) -> bytes:
    body = {
        "status": "ok",
        "service": "ml-harness-engine",
        "portfile_version": 2,
        "engine": {
            "engine_id": "a" * 32,
            "pid": 4242,
            "launch_nonce": None,
            "started_at": "2026-08-20T00:00:00+00:00",
            "uptime_seconds": 1.0,
        },
        "build": {"code_fingerprint": "b" * 64, "sha": "c" * 40, "dirty": False},
        "schema": {"build_knows": 9, "database_at": 9, "agrees": True},
        "database": {"path": "/tmp/x.db", "runs": 0},
        "checks": [{"name": "database_opens", "ok": True, "detail": "opened"}],
    }
    body.update(overrides)
    return json.dumps(body).encode()


class ItClassifiesWhatIsOnAPort(unittest.TestCase):
    """Five outcomes, and the boundary between two of them is a kill."""

    def _probe(self, server: _Server, **kwargs):
        self.addCleanup(server.stop)
        return launcher.probe_engine(server.port, timeout=3.0, **kwargs)

    def test_an_empty_port_is_free(self):
        self.assertEqual(launcher.probe_engine(support.free_port()).state, "free")

    def test_our_engine_answering_200_is_current(self):
        probe = self._probe(_Server(200, _engine_body()))
        self.assertEqual(probe.state, "ours-current")
        self.assertEqual(probe.pid, 4242)
        self.assertEqual(launcher.decide(probe).action, "reuse")

    def test_our_engine_answering_409_is_stale(self):
        """409 is the engine saying "I am fine and I am not what you meant"."""
        body = _engine_body(
            status="not_the_engine_you_meant",
            mismatch=[{"field": "build", "expected": "x", "actual": "y"}],
        )
        probe = self._probe(_Server(409, body), expect_build="deadbeef")
        self.assertEqual(probe.state, "ours-stale")
        decision = launcher.decide(probe)
        self.assertEqual(decision.action, "replace")
        self.assertIn("build", decision.reason)

    def test_our_engine_answering_503_is_unready(self):
        body = _engine_body(
            status="not_ready",
            checks=[
                {"name": "schema_agrees", "ok": False, "detail": "database is at 40"}
            ],
        )
        probe = self._probe(_Server(503, body))
        self.assertEqual(probe.state, "ours-unready")
        decision = launcher.decide(probe)
        self.assertEqual(decision.action, "replace")
        self.assertIn("schema_agrees", decision.reason)

    def test_somebody_elses_json_api_is_foreign(self):
        probe = self._probe(_Server(200, b'{"service":"somebody-elses-api"}'))
        self.assertEqual(probe.state, "foreign")
        self.assertEqual(launcher.decide(probe).action, "refuse")
        self.assertIn("somebody-elses-api", probe.evidence)

    def test_somebody_elses_web_page_is_foreign(self):
        probe = self._probe(_Server(200, b"<html>another project</html>"))
        self.assertEqual(probe.state, "foreign")
        self.assertIn("not JSON", probe.evidence)

    def test_a_socket_that_is_not_http_at_all_is_foreign(self):
        """Accepts a connection, says nothing. The launcher must not hang on it
        and must not conclude anything about it.
        """
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        self.addCleanup(sock.close)
        probe = launcher.probe_engine(port, timeout=2.0)
        self.assertEqual(probe.state, "foreign")
        self.assertEqual(launcher.decide(probe).action, "refuse")

    def test_an_ml_harness_engine_older_than_identity_is_named_as_such(self):
        """The case that will actually happen to somebody: an engine built
        before `app/identity.py` answers `/health` with exactly
        `{"status": "ok"}`. It IS ours and there is no way to know that, which
        is the hole this work closes. Refusing to kill it is still right; a
        launcher that killed anything answering `status: ok` would kill half
        the dev servers on the machine. But the message has to say what it
        probably is, or somebody goes hunting the wrong thing.
        """
        probe = self._probe(_Server(200, b'{"status": "ok"}'))
        self.assertEqual(probe.state, "foreign")
        self.assertIn("before app/identity.py", probe.evidence)


class ItNeverKillsWhatItCannotName(unittest.TestCase):
    """The rule the first failure broke."""

    def test_a_foreign_port_produces_a_refusal_and_no_action(self):
        probe = launcher.Probe("foreign", 8078, evidence="a stranger")
        decision = launcher.decide(probe)
        self.assertEqual(decision.action, "refuse")
        self.assertIn("a stranger", decision.reason)
        self.assertIn("will not be touched", decision.reason)

    def test_the_pid_it_would_terminate_comes_from_the_live_response(self):
        """Not from `engine.json`. That file said 24636 while 23220 held the
        port, and everything downstream of believing it was wrong.
        """
        killed: list[int] = []
        self.addCleanup(setattr, launcher, "_terminate", launcher._terminate)
        self.addCleanup(
            setattr, launcher, "_wait_for_port_to_close", launcher._wait_for_port_to_close
        )
        launcher._terminate = killed.append
        launcher._wait_for_port_to_close = lambda port, timeout=0: True

        probe = launcher.Probe(
            "ours-stale", 8078, payload=json.loads(_engine_body().decode())
        )
        launcher.replace_engine(probe, 8078)
        self.assertEqual(killed, [4242], "it killed something other than the live pid")

    def test_it_refuses_to_terminate_when_the_engine_reported_no_pid(self):
        probe = launcher.Probe("ours-stale", 8078, payload={"engine": {}})
        with self.assertRaises(launcher.LaunchError) as caught:
            launcher.replace_engine(probe, 8078)
        self.assertEqual(caught.exception.exit_code, 2)
        self.assertIn("nothing this launcher is willing to terminate", str(caught.exception))

    def test_a_port_that_stays_open_after_the_kill_is_a_loud_failure(self):
        """KILLING A PID PROVES A PID IS GONE. It does not prove the port is
        free, and the difference is the whole first failure. Under
        `uvicorn --reload` the socket belongs to a supervisor that starts
        another child, so the port never closes - and that has to be a sentence
        on the terminal, not a second engine that cannot bind.
        """
        self.addCleanup(setattr, launcher, "_terminate", launcher._terminate)
        self.addCleanup(
            setattr, launcher, "_wait_for_port_to_close", launcher._wait_for_port_to_close
        )
        self.addCleanup(setattr, launcher, "probe_engine", launcher.probe_engine)
        launcher._terminate = lambda pid: None
        launcher._wait_for_port_to_close = lambda port, timeout=0: False
        launcher.probe_engine = lambda port, **kwargs: launcher.Probe(
            "ours-current", port, payload=json.loads(_engine_body().decode())
        )

        probe = launcher.Probe(
            "ours-stale", 8078, payload=json.loads(_engine_body().decode())
        )
        with self.assertRaises(launcher.LaunchError) as caught:
            launcher.replace_engine(probe, 8078)
        message = str(caught.exception)
        self.assertIn("still occupied", message)
        self.assertIn("was not the process holding the socket", message)
        self.assertEqual(caught.exception.exit_code, 2)


class ItLooksAtEveryAddressAPortResolvesTo(unittest.TestCase):
    """Found within an hour of writing the single-address version.

    Vite binds `localhost`, Node resolves that to `::1` first, so the dev
    server was on IPv6 loopback with nothing at all on IPv4. A launcher that
    asked 127.0.0.1 called the port free, started a second Vite, and watched
    `--strictPort` refuse it - having just reported the first one as absent.
    """

    def test_an_ipv6_only_listener_is_found_through_localhost(self):
        try:
            sock = socket.socket(socket.AF_INET6)
            sock.bind(("::1", 0))
        except OSError:
            self.skipTest("no IPv6 loopback on this machine")
        sock.listen(16)
        port = sock.getsockname()[1]
        self.addCleanup(sock.close)
        self.assertTrue(
            launcher.port_is_open(port, host="localhost", timeout=2.0),
            "an IPv6-only listener was reported as a free port",
        )

    def test_an_ipv4_listener_is_still_found(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        # Backlog of 16, not 1. Nothing here ever calls `accept`, so each
        # probe leaves a connection sitting in the queue - and with a backlog
        # of one the SECOND probe in this method is dropped and times out,
        # which reads exactly like the bug being tested for. A real engine or
        # dev server accepts and closes, so this is a property of the stub.
        sock.listen(16)
        port = sock.getsockname()[1]
        self.addCleanup(sock.close)
        self.assertTrue(launcher.port_is_open(port, timeout=2.0))
        self.assertTrue(launcher.port_is_open(port, host="localhost", timeout=2.0))

    def test_a_free_port_is_free(self):
        self.assertFalse(launcher.port_is_open(support.free_port(), timeout=1.0))


class TwoServersCanHoldOnePortNumber(unittest.TestCase):
    """`strictPort` does not prevent this and nothing in the repo saw it coming.

    OBSERVED ON THIS MACHINE, not imagined: `netstat` showed
    `127.0.0.1:5199 LISTENING 19892` and `[::1]:5199 LISTENING 6404` at the
    same moment - two processes, one port number, different address families,
    serving different apps. `http://127.0.0.1:5199/__engine/session` returned
    our identity JSON; `http://localhost:5199/__engine/session` returned a
    different project's `index.html`. Neither Vite collided, so `strictPort`
    had nothing to refuse.

    That is exactly the failure `frontend/vite.config.ts` documents in its own
    comment - a screenshot taken against the wrong dev server and reported as
    evidence for this one - surviving the fix that was supposed to end it. So
    the launcher checks the address A BROWSER WILL USE, and when the two
    families disagree it refuses and says so rather than reusing whichever half
    it happened to ask.
    """

    def test_the_disagreement_is_named_rather_than_resolved_by_guessing(self):
        ours = _Server(200, _engine_body())
        self.addCleanup(ours.stop)
        # `localhost` answers with somebody else's SPA; `127.0.0.1` answers
        # with ours. The stub cannot really bind two families on one port, so
        # the two lookups are steered instead - the branch under test is what
        # the launcher DOES with a disagreement, not how it discovers one.
        def steer(host, port, timeout):
            if host == launcher.UI_HOST:
                return launcher.Probe(
                    "foreign", port, evidence="HTTP 200 but the body is not JSON"
                )
            return launcher.Probe("ours-current", port, payload={"base_url": "x"})

        self.addCleanup(setattr, launcher, "_probe_ui_at", launcher._probe_ui_at)
        launcher._probe_ui_at = steer

        probe = launcher.probe_ui(5199)
        self.assertEqual(probe.state, "foreign")
        self.assertIn("TWO SERVERS ON PORT 5199", probe.evidence)
        self.assertIn("IPv4 loopback and a different one holds IPv6", probe.evidence)
        self.assertIn("Stop them both", probe.evidence)

    def test_an_agreeing_pair_is_simply_ours(self):
        self.addCleanup(setattr, launcher, "_probe_ui_at", launcher._probe_ui_at)
        launcher._probe_ui_at = lambda host, port, timeout: launcher.Probe(
            "ours-current", port, payload={"base_url": "x"}
        )
        self.assertEqual(launcher.probe_ui(5199).state, "ours-current")

    def test_a_dev_server_that_serves_the_spa_instead_is_named_as_such(self):
        """A Vite whose config does not mount the identity route falls through
        to `index.html`. "the body is not JSON" is true and useless; naming the
        SPA fallback tells somebody it is a different checkout.
        """
        server = _Server(200, b"<!doctype html>\n<html><body>another</body></html>")
        self.addCleanup(server.stop)
        probe = launcher._probe_ui_at("127.0.0.1", server.port, 3.0)
        self.assertEqual(probe.state, "foreign")
        self.assertIn("index.html", probe.evidence)
        self.assertIn("different checkout", probe.evidence)


class ItKeepsThePortfileHonest(unittest.TestCase):
    """Uvicorn runs lifespan BEFORE it binds, so the engine cannot do this."""

    def setUp(self):
        support.sandbox(self)

    def test_a_portfile_describing_another_engine_is_repaired(self):
        from app import security

        health = json.loads(_engine_body().decode())
        security.ENGINE_FILE.write_text(
            json.dumps(
                {
                    "port": 8078,
                    "pid": 999,
                    "token": "a-token-nothing-accepts",
                    "engine": {"engine_id": "z" * 32},
                }
            ),
            encoding="utf-8",
        )
        note = launcher.reconcile_portfile(health, 8078, "the-pinned-token")
        self.assertIsNotNone(note)
        self.assertIn("not the one answering", note)
        written = json.loads(security.ENGINE_FILE.read_text(encoding="utf-8"))
        self.assertEqual(written["engine"]["engine_id"], "a" * 32)
        self.assertEqual(written["token"], "the-pinned-token")
        self.assertEqual(written["pid"], 4242)
        self.assertEqual(written["base_url"], "http://127.0.0.1:8078")

    def test_a_portfile_that_is_already_right_is_left_alone(self):
        from app import security

        health = json.loads(_engine_body().decode())
        launcher.reconcile_portfile(health, 8078, "t")
        self.assertIsNone(launcher.reconcile_portfile(health, 8078, "t"))

    def test_a_stale_portfile_is_removed_only_for_the_port_it_names(self):
        """It is deleted on the strength of "nothing is listening on this
        port", which is only evidence about THIS port. A portfile describing an
        engine on some other port is not ours to touch.
        """
        from app import security

        security.ENGINE_FILE.write_text(
            json.dumps({"port": 9999, "pid": 1}), encoding="utf-8"
        )
        self.assertIsNone(launcher.discard_stale_portfile(8078))
        self.assertTrue(security.ENGINE_FILE.exists())

        security.ENGINE_FILE.write_text(
            json.dumps({"port": 8078, "pid": 1}), encoding="utf-8"
        )
        self.assertIsNotNone(launcher.discard_stale_portfile(8078))
        self.assertFalse(security.ENGINE_FILE.exists())

    def test_the_token_is_carried_forward_from_the_published_file(self):
        """So a restart the launcher performed does not 401 a tab the user
        already had open. That happened to Max once and had no explanation
        anywhere.
        """
        from app import security

        security.ENGINE_FILE.write_text(
            json.dumps({"token": "the-tab-already-has-this"}), encoding="utf-8"
        )
        self.assertEqual(launcher.published_token(), "the-tab-already-has-this")

    def test_no_published_token_means_none_rather_than_an_invented_one(self):
        from app import security

        security.ENGINE_FILE.unlink(missing_ok=True)
        self.assertIsNone(launcher.published_token())


class TheLauncherIsNotReachableFromTheProduct(unittest.TestCase):
    """Invariant 1 says the product executes no shell. This file starts
    processes, so the boundary between it and `app/` has to be a fact rather
    than a habit.
    """

    def test_nothing_under_app_imports_the_launcher(self):
        offenders = []
        walked = sorted((REPO_ROOT / "app").rglob("*.py"))
        # A FLOOR ON WHAT WAS LOOKED AT. Audited 2026-09-06 by emptying every
        # discovered set: this passed, because a walk that finds no files
        # finds no offenders and reports the same green as a clean tree. The
        # same defect was found in the mirror's own scan the day before -
        # four of eleven rules running and calling the tree clean.
        self.assertGreater(len(walked), 20, "the walk over app/ found almost nothing")
        for path in walked:
            if "__pycache__" in path.parts:
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            for pattern in (r"\bimport\s+launch\b", r"\bfrom\s+scripts\b",
                            r"\bimport\s+scripts\b"):
                if re.search(pattern, source):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {pattern}")
        self.assertEqual(offenders, [], "product code can reach the launcher")

    def test_the_half_of_the_launcher_that_moved_starts_nothing(self):
        """THE HALF OF THIS INVARIANT THAT WAS NEVER GREPPABLE, now asserted.

        Phase V step A6 moved the launcher's DECISIONS into `app/launcher.py` -
        probing a port, asking `/health`, reading `engine.json`, and `decide()`
        itself, which is a pure function of a `Probe`. Everything that ACTS
        stayed in `scripts/launch.py`.

        The test above would not have noticed if the acting half had moved too:
        it greps for an import, and `from app import launcher` is not one. So
        this asserts the property the import rule is a proxy for.

        It is narrower than "the product starts no processes", which is not true
        and never was - `app/hwdetect.py` runs `nvidia-smi` and
        `app/tools/sandbox.py` runs recipes. What invariant 1 forbids is a SHELL
        and a free-text command; what this class is about is the launcher's
        process management not leaking into the package.
        """
        source = (REPO_ROOT / "app" / "launcher.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "os.kill", "Popen", "shell=True", "os.system"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_the_acting_half_stayed_where_it_was(self):
        """The control. Without it the assertion above passes for an empty file."""
        source = (REPO_ROOT / "scripts" / "launch.py").read_text(encoding="utf-8")
        for name in ("def start_engine", "def replace_engine", "def _terminate"):
            with self.subTest(name=name):
                self.assertIn(name, source)

    def test_the_launcher_starts_processes_with_a_fixed_argv_and_no_shell(self):
        source = (REPO_ROOT / "scripts" / "launch.py").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)
        # And it does not go through npm.cmd, which CreateProcess hands to the
        # command interpreter - measured to swallow all output when the child
        # is detached, which would make a UI failure invisible.
        self.assertNotIn('"npm"', source)


class TheEntryPointsAgreeWithWhatTheyLaunch(unittest.TestCase):
    """Two wrappers, one implementation. The duplication that remains is the
    port numbers, so it is checked rather than trusted.
    """

    def test_start_sh_exists_and_hands_over_to_the_launcher(self):
        script = (REPO_ROOT / "start.sh").read_text(encoding="utf-8")
        self.assertIn("scripts/launch.py", script)
        self.assertIn('exec "$PYTHON"', script)

    def test_start_ps1_exists_and_hands_over_to_the_same_launcher(self):
        script = (REPO_ROOT / "start.ps1").read_text(encoding="utf-8")
        self.assertIn("scripts\\launch.py", script)

    def test_the_engine_port_is_the_products_default(self):
        from app.config import DEFAULT_PORT

        self.assertEqual(launcher.parse_args([]).port, DEFAULT_PORT)

    def test_the_ui_port_matches_the_one_vite_is_pinned_to(self):
        """`frontend/vite.config.ts` sets `strictPort`, so if these two numbers
        drift the launcher probes one port and Vite refuses to start on the
        other - and the launcher would report a dev server that is not there.
        """
        config = (REPO_ROOT / "frontend" / "vite.config.ts").read_text(
            encoding="utf-8"
        )
        match = re.search(r"^\s*port:\s*(\d+)", config, re.MULTILINE)
        self.assertIsNotNone(match, "vite.config.ts no longer pins a port")
        self.assertEqual(int(match.group(1)), launcher.DEFAULT_UI_PORT)

    def test_the_ui_identity_route_is_one_only_our_dev_server_serves(self):
        config = (REPO_ROOT / "frontend" / "vite.config.ts").read_text(
            encoding="utf-8"
        )
        self.assertIn(launcher.UI_IDENTITY_PATH, config)

    def test_the_service_name_it_looks_for_is_the_one_the_engine_publishes(self):
        """BOTH HALVES OF THE LAUNCHER NOW, which is stronger than one.

        `probe_engine` moved to `app/launcher.py` in Phase V step A6, so the
        name it compares against moved with it. Reading both files asserts what
        this always meant - neither half hardcodes the string - rather than
        which file happens to hold the comparison today.
        """
        self.assertEqual(identity.SERVICE, "ml-harness-engine")
        for where in (
            REPO_ROOT / "scripts" / "launch.py",
            REPO_ROOT / "app" / "launcher.py",
        ):
            with self.subTest(file=where.name):
                self.assertNotIn(
                    '"ml-harness-engine"', where.read_text(encoding="utf-8")
                )
        self.assertIn(
            "identity.SERVICE",
            (REPO_ROOT / "app" / "launcher.py").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
