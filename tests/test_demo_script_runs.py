"""The demo script must run, and must run somewhere disposable.

This file is where the user's real database got written to 1,036 times. The old
test ran `scripts/demo_train.py` as a subprocess and asserted one thing: that
the output did not contain `ModuleNotFoundError`. Two properties of that test
combined badly.

First, the script does not open a database - it POSTs to whatever engine
answers on `MLH_PORT`. The suite's usual isolation is `db.DB_PATH = <temp>` in
the *test* process, and the script's target never reads that global. On the
owner's machine the engine listening on the default port was the real one, so
every pass of the suite appended a run and thirty metric rows to real data.

Second, the assertion was satisfied by failure. A script that connected to
nothing, raised `URLError` and exited 1 produced output with no
`ModuleNotFoundError` in it, so the test was green on a machine with no engine
and quietly destructive on a machine with one - the two states are
indistinguishable to it. That is the worse half: the test could not tell
"worked" from "could not even start".

So this version stands up an engine of its own. A free port, a database in a
temporary directory via `ML_HARNESS_DB`, a pinned `MLH_TOKEN` and an
`MLH_ENGINE_FILE` in the same temporary directory so the real `engine.json` is
left alone. The script is then pointed at that engine with `MLH_PORT`, and the
test can assert what it always should have: that the script exits 0, that the
curve is in the temporary database, and that the real file is byte-identical
afterwards.

The original assertion is kept as its own method. It was checking something
real - the script inserts the repository root into `sys.path` so it can be run
from anywhere - and this file runs it from a temporary directory with the
repository stripped out of `PYTHONPATH` for exactly that reason.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import support


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "demo_train.py"

#: Pinned rather than read from a portfile, so the engine we start and the
#: script we start agree without either of them consulting the real
#: `engine.json`. `security.current_token()` honours `MLH_TOKEN` in both.
TOKEN = "demo-script-test-token"

#: How long to wait for uvicorn to answer `/health`. Generous, because a cold
#: import of fastapi on Windows is not fast and a flaky suite is worse than a
#: slow one.
STARTUP_TIMEOUT = 40.0


class DemoScriptRunsTest(unittest.TestCase):
    """One engine, one run of the script, four things asserted about it.

    Class-level setup rather than per-method: starting uvicorn four times to
    make four assertions about the same single run of the script would cost
    four process startups and, worse, would be asserting about four different
    runs.
    """

    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._remove, temp)
        cls.root = Path(temp.name)
        cls.database = cls.root / "demo.db"
        cls.port = support.free_port()

        cls.engine_env = os.environ.copy()
        cls.engine_env["ML_HARNESS_DB"] = str(cls.database)
        cls.engine_env["MLH_PORT"] = str(cls.port)
        cls.engine_env["MLH_TOKEN"] = TOKEN
        cls.engine_env["MLH_ENGINE_FILE"] = str(cls.root / "engine.json")

        cls._start_engine()

        # Recorded as late as possible before the script runs and read as soon
        # as possible after, so the window this test is answering for is the
        # script's own.
        before = {
            path: support.database_fingerprint(path)
            for path in support.PROTECTED_DATABASES
        }
        cls.result = cls._run_demo_script()
        cls.protected_before = before
        cls.protected_after = {
            path: support.database_fingerprint(path)
            for path in support.PROTECTED_DATABASES
        }

    # ---------------------------------------------------------------- engine

    @classmethod
    def _start_engine(cls):
        """Start an engine of our own and wait until it answers."""
        cls.engine_log = cls.root / "engine.log"
        handle = cls.engine_log.open("w", encoding="utf-8")
        # Registered before the stop, so it runs after it: cleanups are LIFO
        # and closing our end of the log while the engine is still writing to
        # it is a race worth not having.
        cls.addClassCleanup(handle.close)
        # Written to a file rather than a pipe: nothing reads the pipe until
        # cleanup, and a pipe nobody drains is a buffer that eventually blocks
        # the process filling it.
        cls.engine = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.port),
                "--log-level",
                "warning",
            ],
            cwd=str(REPO_ROOT),
            env=cls.engine_env,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        cls.addClassCleanup(cls._stop_engine)
        cls._wait_for_health()

    @classmethod
    def _wait_for_health(cls):
        deadline = time.monotonic() + STARTUP_TIMEOUT
        url = f"http://127.0.0.1:{cls.port}/health"
        while time.monotonic() < deadline:
            if cls.engine.poll() is not None:
                raise AssertionError(
                    f"engine exited {cls.engine.returncode} before answering:\n"
                    f"{cls._engine_output()}"
                )
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, OSError):
                time.sleep(0.1)
        raise AssertionError(
            f"engine did not answer {url} within {STARTUP_TIMEOUT}s:\n"
            f"{cls._engine_output()}"
        )

    @classmethod
    def _engine_output(cls) -> str:
        try:
            return cls.engine_log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "<no engine log>"

    @classmethod
    def _stop_engine(cls):
        if cls.engine.poll() is None:
            cls.engine.terminate()
            try:
                cls.engine.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.engine.kill()
                cls.engine.wait(timeout=10)

    @classmethod
    def _remove(cls, temp):
        try:
            temp.cleanup()
        except (PermissionError, OSError):
            # Same Windows handle problem `support.sandbox` documents: the
            # directory is the OS's problem at that point, not the test's.
            pass

    # ---------------------------------------------------------------- script

    @classmethod
    def _run_demo_script(cls) -> subprocess.CompletedProcess:
        """Run the script from outside the repository, against our engine."""
        env = dict(cls.engine_env)
        # The point of the original test: the script has to work when the
        # repository is neither the working directory nor on PYTHONPATH,
        # because it puts itself there.
        pythonpath_entries = env.get("PYTHONPATH", "").split(os.pathsep)
        env["PYTHONPATH"] = os.pathsep.join(
            entry
            for entry in pythonpath_entries
            if not entry or Path(entry).resolve() != REPO_ROOT
        )
        # Thirty rows are wanted; thirty pauses of 0.15s are not.
        env["MLH_DEMO_STEP_DELAY"] = "0"

        outside = cls.root / "outside-the-repo"
        outside.mkdir(exist_ok=True)
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=str(outside),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
            check=False,
        )

    # ----------------------------------------------------------- assertions

    def test_script_imports_app_from_outside_repo(self):
        self.assertNotIn("ModuleNotFoundError", self.result.stdout)

    def test_script_completes_against_the_engine_it_was_pointed_at(self):
        self.assertEqual(
            self.result.returncode,
            0,
            f"demo script exited {self.result.returncode}:\n{self.result.stdout}",
        )
        self.assertIn("completed demo run", self.result.stdout)
        self.assertIn(f"127.0.0.1:{self.port}", self.result.stdout)

    def test_the_curve_lands_in_the_database_the_engine_was_given(self):
        self.assertTrue(
            self.database.exists(),
            f"engine never created {self.database}:\n{self._engine_output()}",
        )
        connection = sqlite3.connect(self.database)
        try:
            connection.row_factory = sqlite3.Row
            runs = [
                dict(row)
                for row in connection.execute("SELECT * FROM runs").fetchall()
            ]
            self.assertEqual([run["name"] for run in runs], ["demo-loss-curve"])
            self.assertEqual(runs[0]["status"], "completed")
            self.assertEqual(json.loads(runs[0]["params_json"])["synthetic"], True)
            steps = connection.execute(
                "SELECT COUNT(*) FROM metrics WHERE run_id = ? AND name = 'loss'",
                (runs[0]["id"],),
            ).fetchone()[0]
            self.assertEqual(steps, 30)
        finally:
            connection.close()

    def test_running_the_demo_script_does_not_touch_the_real_database(self):
        """The defect this file exists to have fixed, asserted at the scene.

        `test_tests_do_not_touch_the_real_database` makes the same check for
        the suite as a whole. This one is here as well because a guard that
        only fires at the far end of the run tells you *that* something wrote;
        this one tells you it was this.
        """
        for path, baseline in self.protected_before.items():
            self.assertEqual(
                self.protected_after[path],
                baseline,
                f"{path} changed while the demo script ran",
            )


if __name__ == "__main__":
    unittest.main()
