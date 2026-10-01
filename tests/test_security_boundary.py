"""The attack, constructed, and then refused.

This file is not a unit test of a policy function. It builds the two requests
an attacker actually sends and asserts the product refuses them, because the
thing being defended is a *reachable* endpoint and the only honest proof is to
reach for it.

The hole, as it stood: `POST /jobs` accepted a free-text `cmd`, stored it, and
`app/runner.py` handed it to `subprocess.Popen(..., shell=True)`. No
authentication, no CORS policy, no `Origin` check. Two attackers could use it -
any process on the machine, and any web page open in the user's browser via a
cross-site form POST, which needs no preflight and so is sent before any CORS
rule is consulted. The product is about to hold a provider API key and the
user's data.

Every test below has a positive control nearby. A security test that passes by
rejecting everything is worse than no test, because it reports safety while
having proved only that the endpoint is broken - so each "this is refused" is
paired with a "and this identical-but-legitimate request is accepted."
"""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
import warnings
from pathlib import Path

from fastapi.testclient import TestClient

from app import db, jobspec, security

import support

warnings.filterwarnings("ignore")


REPO_ROOT = Path(__file__).resolve().parents[1]

#: What an attacker sends. The old contract's exact shape.
SHELL_PAYLOAD = {"intake_id": "x", "cmd": "calc.exe"}

#: A structurally valid job, so that a rejection is provably about the
#: boundary and not about the body being malformed.
VALID_PAYLOAD = {
    "intake_id": "s1",
    "recipe": "printer",
    "kind": "train",
    "config": {"message": "hello"},
}

EVIL_ORIGIN = "https://evil.example"


def basic(token: str, user: str = "opencode") -> dict[str, str]:
    """The header OpenCode's client builds (`authTokenFromCredentials`)."""
    raw = base64.b64encode(f"{user}:{token}".encode()).decode()
    return {"Authorization": f"Basic {raw}"}


class SecurityBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "test.db"
        db.init_db()
        self.recipes = support.recipe_fixtures(Path(self.temp.name))
        self.recipes.__enter__()
        from app.main import app
        # Deliberately unauthenticated. This client is the attacker.
        self.client = TestClient(app)
        self.headers = support.auth_headers()

    def tearDown(self):
        self.client.close()
        self.recipes.__exit__(None, None, None)
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def queued(self):
        return [j for j in db.list_jobs() if j["status"] == "queued"]

    # ---- attack 1: the unauthenticated POST ----------------------------

    def test_unauthenticated_post_to_jobs_is_rejected(self):
        """The whole hole, in four lines."""
        resp = self.client.post("/jobs", json=VALID_PAYLOAD)
        self.assertEqual(
            resp.status_code, 401,
            f"an unauthenticated POST /jobs returned {resp.status_code}; "
            f"anything that is not 401 is the hole still being open")
        self.assertEqual(self.queued(), [],
                         "a rejected request must not queue a job")

    def test_the_original_shell_payload_is_rejected_unauthenticated(self):
        resp = self.client.post("/jobs", json=SHELL_PAYLOAD)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(self.queued(), [])

    def test_an_authenticated_post_is_accepted(self):
        """The positive control for every rejection above.

        Without this, all of them would pass against an endpoint that had been
        deleted, or one that 401s unconditionally.
        """
        resp = self.client.post("/jobs", json=VALID_PAYLOAD, headers=self.headers)
        self.assertEqual(resp.status_code, 201, resp.text)
        self.assertEqual(len(self.queued()), 1)

    def test_a_wrong_token_is_rejected(self):
        resp = self.client.post(
            "/jobs", json=VALID_PAYLOAD,
            headers={"Authorization": "Bearer not-the-real-token"})
        self.assertEqual(resp.status_code, 401)

    def test_a_token_in_the_wrong_scheme_is_rejected(self):
        resp = self.client.post(
            "/jobs", json=VALID_PAYLOAD,
            headers={"Authorization": security.current_token()})
        self.assertEqual(resp.status_code, 401,
                         "a bare token with no Bearer scheme is not a "
                         "credential this API accepts")

    def test_the_api_surface_needs_a_token_for_reads_too(self):
        self.assertEqual(self.client.get("/api/runs").status_code, 401)
        self.assertEqual(
            self.client.get("/api/runs", headers=self.headers).status_code, 200)

    # ---- the OpenCode facade: same token, their spelling ---------------

    def test_the_facade_refuses_a_stranger_and_admits_their_credential(self):
        """`/oc` is the same surface as `/api`, so the same refusal, with the
        positive control beside it: OpenCode's client sends the engine's token
        as `Basic base64("opencode:<token>")`, and that is admitted."""
        self.assertEqual(self.client.get("/oc/api/info").status_code, 401)
        self.assertEqual(
            self.client.get("/oc/api/info", headers=basic(security.current_token())).status_code,
            200,
        )

    def test_the_facade_refuses_their_credential_for_another_user(self):
        response = self.client.get(
            "/oc/api/info", headers=basic(security.current_token(), user="admin")
        )
        self.assertEqual(response.status_code, 401)

    def test_a_basic_credential_opens_the_old_api_too_because_it_is_one_token(self):
        """Not a second secret: the Basic spelling of the token is the token."""
        self.assertEqual(
            self.client.get("/api/runs", headers=basic(security.current_token())).status_code, 200
        )
        self.assertEqual(self.client.get("/api/runs", headers=basic("guess")).status_code, 401)

    # ---- attack 2: the cross-site POST ---------------------------------

    def test_cross_origin_post_to_jobs_is_rejected(self):
        """A page on evil.example, with the port guessed correctly."""
        resp = self.client.post(
            "/jobs", json=VALID_PAYLOAD, headers={"Origin": EVIL_ORIGIN})
        self.assertEqual(
            resp.status_code, 403,
            f"a cross-origin POST /jobs returned {resp.status_code}; "
            f"a browser page can reach 127.0.0.1 and this must refuse it")
        self.assertEqual(self.queued(), [])

    def test_cross_origin_post_is_rejected_even_holding_the_token(self):
        """The CSRF case specifically.

        A cross-site request forgery is a request the *browser* makes on the
        page's behalf, so it can carry credentials the page cannot read. If the
        boundary only checked the token, this is the request that would get
        through - which is why the `Origin` check is a separate mechanism and
        not a nicety layered on top of the same one.
        """
        headers = dict(self.headers)
        headers["Origin"] = EVIL_ORIGIN
        resp = self.client.post("/jobs", json=VALID_PAYLOAD, headers=headers)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.queued(), [])

    def test_cross_site_form_post_is_rejected(self):
        """The form POST is the one that needs no preflight.

        `<form action="http://127.0.0.1:8078/jobs" method="post">` with a
        form-encoded body is a "simple request": the browser sends it without
        asking CORS for permission first, and the page never needs to read the
        response. CORS alone does not stop this. The `Origin` header does.
        """
        resp = self.client.post(
            "/jobs",
            data={"intake_id": "x", "cmd": "calc.exe"},
            headers={
                "Origin": EVIL_ORIGIN,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.queued(), [])

    def test_a_sandboxed_origin_is_rejected(self):
        """`Origin: null` is a sandboxed iframe or a file:// page. Never ours."""
        resp = self.client.post(
            "/jobs", json=VALID_PAYLOAD,
            headers={**self.headers, "Origin": "null"})
        self.assertEqual(resp.status_code, 403)

    def test_a_lookalike_origin_is_rejected(self):
        """Substring matching would let these through. Set membership does not."""
        for origin in (
            "http://127.0.0.1.evil.example",
            "http://localhost.evil.example",
            "https://127.0.0.1:8078",
            "http://127.0.0.1:9999",
            "http://evil.example#http://127.0.0.1:8078",
        ):
            with self.subTest(origin=origin):
                resp = self.client.post(
                    "/jobs", json=VALID_PAYLOAD,
                    headers={**self.headers, "Origin": origin})
                self.assertEqual(resp.status_code, 403, f"{origin} was allowed")

    def test_the_same_origin_post_still_works(self):
        """Positive control for the Origin check.

        The product's own page must keep working, or the check has been
        implemented by breaking the product.
        """
        allowed = sorted(security.allowed_origins())
        self.assertTrue(allowed)
        for origin in allowed:
            with self.subTest(origin=origin):
                resp = self.client.post(
                    "/jobs", json=VALID_PAYLOAD,
                    headers={**self.headers, "Origin": origin})
                self.assertEqual(resp.status_code, 201, resp.text)

    def test_cross_origin_read_is_rejected_too(self):
        """Not only writes. A page must not read the user's runs either."""
        resp = self.client.get(
            "/api/runs", headers={**self.headers, "Origin": EVIL_ORIGIN})
        self.assertEqual(resp.status_code, 403)

    # ---- the Stage is a read, and a read is behind the same door -------

    def test_the_stage_is_not_readable_without_the_token(self):
        """The Stage hands back a whole thread's measurements in one payload.

        A READ IS AN ATTACK SURFACE, which this file already argues at
        `test_cross_origin_read_is_rejected_too`: a page must not read the
        user's runs either. The Stage payload is strictly more than
        `/api/runs` - every eval run in the thread, every sandbox in the
        project, the GPU occupancy read off nvidia-smi, and the journey
        report - so it is the read most worth locking, and this is the first
        test that names it.

        The thread is created first, so that a 401 here cannot be a 404
        wearing a different number.
        """
        thread = support.conversations(1)[0]
        path = f"/api/threads/{thread['id']}/stage"

        self.assertEqual(self.client.get(path).status_code, 401)

        allowed = self.client.get(path, headers=self.headers)
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertEqual(allowed.json()["thread_id"], int(thread["id"]))

    def test_the_stage_refuses_a_cross_site_reader(self):
        """Token and all: a page on evil.example may not read the Stage."""
        thread = support.conversations(1)[0]
        resp = self.client.get(
            f"/api/threads/{thread['id']}/stage",
            headers={**self.headers, "Origin": EVIL_ORIGIN},
        )
        self.assertEqual(resp.status_code, 403)

    # ---- the command string is gone, not merely guarded ----------------

    def test_an_authenticated_cmd_payload_is_rejected_as_unknown(self):
        """Even with a valid token, there is nothing to send `cmd` to."""
        resp = self.client.post("/jobs", json=SHELL_PAYLOAD, headers=self.headers)
        self.assertEqual(resp.status_code, 422, resp.text)
        self.assertIn("cmd", resp.text,
                      "the rejection must name the offending field")
        self.assertEqual(self.queued(), [])

    def test_an_unknown_recipe_is_refused(self):
        resp = self.client.post(
            "/jobs",
            json={**VALID_PAYLOAD, "recipe": "definitely-not-a-recipe"},
            headers=self.headers)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(self.queued(), [])

    def test_a_recipe_name_cannot_traverse_the_recipes_directory(self):
        for name in ("../app", "..\\app", "printer/../../app", "/etc/passwd",
                     "PRINTER", "printer;calc.exe", "printer ", ""):
            with self.subTest(name=name):
                resp = self.client.post(
                    "/jobs", json={**VALID_PAYLOAD, "recipe": name},
                    headers=self.headers)
                self.assertGreaterEqual(resp.status_code, 400)
                self.assertLess(resp.status_code, 500)
        self.assertEqual(self.queued(), [])

    def test_a_kind_the_recipe_does_not_declare_is_refused(self):
        resp = self.client.post(
            "/jobs", json={**VALID_PAYLOAD, "kind": "sweep"},
            headers=self.headers)
        self.assertEqual(resp.status_code, 422)

    def test_shell_metacharacters_in_config_are_inert(self):
        """The remaining caller-controlled surface, attacked directly.

        `config` is the only thing a caller still chooses, and it goes into
        `job.json` rather than onto a command line. So the classic payloads are
        just text: they come back out of the job's stdout verbatim, which is
        the observable difference between "quoted correctly" and "never parsed
        by a shell at all".
        """
        from app import runner
        payload = '; calc.exe & echo pwned | whoami `id` $(id) %CD%'
        job = db.create_job("s1", support.spec("printer", message=payload))
        done = runner.run_next_job(timeout=30)
        log = Path(done["log_path"]).read_text(encoding="utf-8")
        self.assertEqual(done["exit_code"], 0, log)
        self.assertIn(payload, log,
                      "the payload must survive as text, not be interpreted")
        self.assertNotIn("pwned\n", log.replace(payload, ""))

    def test_no_shell_execution_remains_in_the_app(self):
        """The invariant, checked mechanically. `AGENTS.md` invariant 1.

        `docs/ROADMAP.md` proposed `grep -rn "shell=True" app/` for this. The
        check is done against the parsed syntax tree instead, for a reason
        worth writing down: `app/runner.py`'s docstring quotes the old
        `subprocess.run(shell=True, ...)` call, because that call is the
        measured failure the whole timeout design came from. A grep cannot tell
        a warning about a bug from the bug, so it would force the evidence to
        be deleted to make the check pass - and deleting the evidence is how
        this class of defect comes back.

        The AST check is also strictly stronger than the grep: it catches
        `shell = True`, `shell=1`, and a variable that is not literally
        `False`, none of which the grep pattern matches.
        """
        import ast

        offenders = []
        for path in sorted((REPO_ROOT / "app").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for keyword in node.keywords:
                    if keyword.arg != "shell":
                        continue
                    literal_false = (
                        isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is False
                    )
                    if not literal_false:
                        offenders.append(f"{path.name}:{keyword.value.lineno}")
        self.assertEqual(
            offenders, [],
            f"a shell-invoking call survives in app/: {offenders}")

    def test_the_runner_asks_for_no_shell_explicitly(self):
        """Not merely the absence of `shell=True`.

        `shell=False` is the default, so a subprocess call that omits the
        argument is already safe - and silently so. Every process launch in the
        runner states it, because the next person to edit that line should have
        to delete a word that says what it means rather than add one.
        """
        import ast

        source = (REPO_ROOT / "app" / "runner.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        launches = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "Popen"
        ]
        self.assertTrue(launches, "the runner launches no process at all?")
        for call in launches:
            declared = [k for k in call.keywords if k.arg == "shell"]
            self.assertEqual(
                len(declared), 1,
                f"Popen at line {call.lineno} does not say shell= at all")
            self.assertIs(
                declared[0].value.value, False,
                f"Popen at line {call.lineno} does not say shell=False")

        # And argv is a list, never a string: `Popen("a b c")` on Windows goes
        # through CreateProcess with the whole string, which is a different way
        # to reach the same class of bug.
        for call in launches:
            first = call.args[0] if call.args else None
            self.assertNotIsInstance(
                first, ast.Constant,
                f"Popen at line {call.lineno} is given a literal string")

    def test_a_legacy_command_row_is_refused_not_executed(self):
        """A job queued under the old contract must never run.

        The migration keeps old rows as history. This asserts the history is
        inert: the recipe name it carries is not a directory under `recipes/`,
        so the runner records a refusal instead of finding something to run.
        """
        from app import runner
        db.ensure_jobs_table()
        with db.session() as connection:
            connection.execute(
                "INSERT INTO jobs (intake_id, recipe, kind, config_json) "
                "VALUES (?, ?, ?, ?)",
                ("legacy", "legacy-command", "train",
                 json.dumps({"legacy_cmd": "calc.exe"})))
        done = runner.run_next_job()
        self.assertEqual(done["exit_code"], runner.REJECTED)
        self.assertIn("REJECTED",
                      Path(done["log_path"]).read_text(encoding="utf-8"))


class BoundaryPolicyTest(unittest.TestCase):
    """The policy functions, read directly.

    The HTTP tests above prove the boundary is wired in. These prove the rule
    it enforces is the rule that was written down, including the one exemption,
    which is the part most likely to be widened by accident later.
    """

    def test_every_state_changing_method_needs_a_token(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            for path in ("/jobs", "/hardware", "/intake", "/anything/new"):
                with self.subTest(method=method, path=path):
                    self.assertTrue(security.requires_token(method, path))

    def test_the_whole_api_surface_needs_a_token(self):
        for path in ("/api/runs", "/api/runs/1/metrics", "/api/recipes"):
            self.assertTrue(security.requires_token("GET", path))

    def test_there_is_no_exemption_left(self):
        """IT WAS EXACTLY ONE ROUTE AND NOW IT IS NONE.

        `/ui/intake` was the only server-rendered form that changed state, and a
        browser form cannot set an Authorization header - so that POST was let
        through the bearer-token boundary and defended by SameSite instead. A
        real defence, and a DIFFERENT one from every other route's, which is why
        it was named in a frozenset rather than assumed anywhere.

        `docs/THE_PLAN.md` V.3 A9 retired the form. So the strongest thing this
        boundary can now say is that EVERY state-changing path needs a token,
        with no special case to get wrong - and the path that used to be exempt
        is checked by name, because a route coming back without its exemption
        being reconsidered is the thing this test is for.
        """
        self.assertEqual(security.BROWSER_FORM_ROUTES, frozenset())
        for path in ("/ui/intake", "/ui/intakes", "/ui/intake/x", "/api/anything"):
            with self.subTest(path=path):
                self.assertTrue(security.requires_token("POST", path))

    def test_the_mechanism_survives_the_last_route_that_used_it(self):
        """The set is empty; the BRANCH is not deleted.

        A mechanism that has to be rebuilt before it can be used again is a
        mechanism somebody rebuilds in a hurry, differently, somewhere else. A
        future form is added to this frozenset on purpose, and `requires_token`
        already knows what to do with it.
        """
        original = security.BROWSER_FORM_ROUTES
        try:
            security.BROWSER_FORM_ROUTES = frozenset({"/ui/example"})
            self.assertFalse(security.requires_token("POST", "/ui/example"))
            self.assertTrue(security.requires_token("POST", "/ui/example/x"))
        finally:
            security.BROWSER_FORM_ROUTES = original

    def test_the_shell_origin_is_admitted_and_it_was_measured(self):
        """PHASE V A7, ANSWERED BY RUNNING A REAL WINDOW.

        THE_PLAN called this "the single highest-risk unknown" and refused to
        guess, because widening a security boundary on a blog post is the
        boundary loosened by an assumption. `scripts/origin_spike.py` served a
        page to a real Tauri v2 window on 2026-08-28, WebView2 151.0.4129.107:

            packaged (frontendDist)  Origin: http://tauri.localhost
                                     Sec-Fetch-Site: cross-site
            dev (devUrl)             Origin: http://localhost:5199
                                     Sec-Fetch-Site: same-origin

        Both were refused before this. Only the first is admitted.
        """
        self.assertIn(security.SHELL_ORIGIN, security.allowed_origins())
        self.assertTrue(security.origin_is_allowed(security.SHELL_ORIGIN))

    def test_the_dev_origin_is_still_refused_and_that_is_the_argument(self):
        """`http://tauri.localhost` is WebView2's internal custom-protocol host
        - no page a browser can navigate to has that origin, so admitting it
        widens nothing a website can reach. `http://localhost:5199` is an
        ORDINARY origin any page served on that port can have, and the dev path
        does not need it: Vite's proxy strips `Origin`, and a missing one
        already means "not a browser"."""
        self.assertFalse(security.origin_is_allowed("http://localhost:5199"))
        self.assertFalse(security.origin_is_allowed("http://tauri.localhost:5199"))
        self.assertFalse(security.origin_is_allowed("https://tauri.localhost"))
        self.assertFalse(security.origin_is_allowed("http://tauri.localhost.evil.com"))

    def test_it_is_admitted_on_every_port_because_it_names_no_port(self):
        """The loopback pair are per-port; the shell's origin has none, and a
        check that appended one would refuse the shell on any non-default port
        - which is every engine started with `--port`."""
        for port in (8078, 9000, 65535):
            with self.subTest(port=port):
                self.assertTrue(
                    security.origin_is_allowed(security.SHELL_ORIGIN, port)
                )

    def test_the_facade_needs_a_token_for_every_method(self):
        for method in ("GET", "POST", "PATCH", "DELETE"):
            for path in ("/oc", "/oc/", "/oc/api/info", "/oc/api/event", "/oc/api/session/x"):
                with self.subTest(method=method, path=path):
                    self.assertTrue(security.requires_token(method, path))

    def test_the_facade_prefix_is_a_whole_segment(self):
        """`/ocelot` is not under `/oc`; a prefix match on the string would say
        it was, and a route added there later would inherit a rule nobody
        wrote for it."""
        self.assertFalse(security.requires_token("GET", "/ocelot"))
        self.assertFalse(security.requires_token("GET", "/oc-notes"))

    def test_their_basic_spelling_of_the_token_is_accepted_and_nothing_else_is(self):
        token = security.current_token()
        self.assertTrue(security.token_matches(basic(token)["Authorization"]))
        self.assertTrue(security.token_matches(f"Bearer {token}"))
        self.assertTrue(security.token_matches(basic(token)["Authorization"].replace("Basic", "basic")))
        refused = {
            "wrong user": basic(token, user="admin")["Authorization"],
            "empty user": basic(token, user="")["Authorization"],
            "wrong password": basic("not-it")["Authorization"],
            "token as user": basic("", user=token)["Authorization"],
            "no colon": "Basic " + base64.b64encode(token.encode()).decode(),
            "not base64": "Basic !!!not-base64!!!",
            "empty": "Basic ",
            "bare token": token,
            "unknown scheme": f"Token {token}",
        }
        for case, header in refused.items():
            with self.subTest(case=case):
                self.assertFalse(security.token_matches(header))

    def test_a_missing_origin_is_allowed_and_a_foreign_one_is_not(self):
        self.assertTrue(security.origin_is_allowed(None))
        self.assertTrue(security.origin_is_allowed(""))
        self.assertFalse(security.origin_is_allowed(EVIL_ORIGIN))
        self.assertFalse(security.origin_is_allowed("null"))

    def test_the_token_is_not_a_constant(self):
        """Two engines must not share a token.

        A default or derived token would pass every test above while being
        guessable, which is the failure mode this assertion exists to catch.
        """
        import os
        saved_env = os.environ.pop("MLH_TOKEN", None)
        try:
            security.reset_token_for_tests()
            first = security.current_token()
            security.reset_token_for_tests()
            second = security.current_token()
            self.assertNotEqual(first, second)
            self.assertGreaterEqual(len(first), 32)
        finally:
            security.reset_token_for_tests()
            if saved_env is not None:
                os.environ["MLH_TOKEN"] = saved_env


class PortfileTest(unittest.TestCase):
    """The token reaches a local client without a keychain."""

    def test_the_portfile_carries_the_token_and_binds_loopback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "engine.json"
            security.write_portfile(path=path)
            published = security.read_portfile(path)
            self.assertEqual(published["token"], security.current_token())
            self.assertEqual(published["host"], "127.0.0.1")
            self.assertTrue(published["base_url"].startswith("http://127.0.0.1:"))
            self.assertEqual(
                security.auth_header(path),
                {"Authorization": f"Bearer {security.current_token()}"})

    def test_a_second_process_does_not_steal_a_live_engines_portfile(self):
        """Regression, found by running two processes against one repository.

        An engine was serving on 8078. A second process started the same app,
        and its startup rewrote `engine.json` with a token the listening engine
        had never heard of - so every local client, including a job already
        running, began authenticating against the wrong secret and got 401.
        Anything that imports and starts the app writes this file, the test
        suite included, so the last writer cannot be the owner.
        """
        import os

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "engine.json"
            # A live engine, which happens to be this process, publishes.
            security.write_portfile(path=path)
            live = security.read_portfile(path)
            self.assertEqual(live["pid"], os.getpid())

            # A different, still-running process owns it AND answers as the
            # engine the file names: leave it alone. Since 2026-09-23 a live
            # pid alone is not enough - Windows reuses pids, and a dead
            # engine's pid on a browser renderer once made the next engine
            # hide its token (test_a_live_pid_is_not_a_live_engine.py) - so
            # the incumbent here answers /health with the file's engine_id.
            import threading
            from http.server import BaseHTTPRequestHandler, HTTPServer

            engine_id = live["engine"]["engine_id"]

            class Health(BaseHTTPRequestHandler):
                def do_GET(self):  # noqa: N802 - the stdlib's spelling
                    body = json.dumps({"engine": {"engine_id": engine_id}}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *_):
                    pass

            incumbent = HTTPServer(("127.0.0.1", 0), Health)
            threading.Thread(target=incumbent.serve_forever, daemon=True).start()
            try:
                path.write_text(
                    json.dumps({**live, "pid": os.getppid(),
                                "base_url": f"http://127.0.0.1:{incumbent.server_address[1]}",
                                "token": "the-live-engines-token"}),
                    encoding="utf-8")
                security.write_portfile(path=path)
                self.assertEqual(
                    security.read_portfile(path)["token"], "the-live-engines-token",
                    "a second process overwrote a live engine's portfile")
            finally:
                incumbent.shutdown()

            # A dead owner leaves a stale file, which must be replaceable or a
            # crashed engine would lock the product out of its own portfile.
            path.write_text(
                json.dumps({**live, "pid": 0x7FFFFFFF, "token": "stale"}),
                encoding="utf-8")
            security.write_portfile(path=path)
            self.assertEqual(security.read_portfile(path)["pid"], os.getpid())

    def test_a_client_with_no_portfile_sends_no_token(self):
        """It must not invent one. A wrong token is a worse error message."""
        import os
        saved_env = os.environ.pop("MLH_TOKEN", None)
        try:
            with tempfile.TemporaryDirectory() as temp:
                missing = Path(temp) / "absent.json"
                self.assertIsNone(security.client_token(missing))
                self.assertEqual(security.auth_header(missing), {})
        finally:
            if saved_env is not None:
                os.environ["MLH_TOKEN"] = saved_env

    def test_the_engine_never_binds_anything_but_loopback(self):
        from app import config
        self.assertEqual(config.HOST, "127.0.0.1")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("0.0.0.0", readme,
                         "the README must not document a non-loopback bind")


if __name__ == "__main__":
    unittest.main()
