"""The runner's failure paths: timeout, refusal, output on stderr.

The only runner test that existed ran `python -c "print(1)"` and asserted it
worked. Everything a real job actually does when it goes wrong was untested:
it hangs, the binary does not exist, it writes to stderr instead of stdout,
it produces nothing at all.

This is the same gap as the rest of the suite - the happy path is the only
path a generated test builds, because the spec that produced it described
success.

**Rewritten for the structured job contract, and deliberately not loosened.**
Every case below is the case that was here before; only the way a job is
expressed has changed, because a job is a recipe now and not a shell string
(`app/jobspec.py`). One case could not survive as written: "a command that does
not exist" was reachable only because a caller could name the binary, and a
caller cannot. Its replacement is `test_a_recipe_whose_entrypoint_is_missing_is_refused`,
which is the same failure - argv[0] and argv[1] must both exist before anything
runs - arriving from the only direction still open.

The timing assertion is the one that matters and it is untouched: it measures
the clock, because the original bug produced a correct status and a correct
exit code while the bound did nothing.
"""
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

from app import db, jobspec, runner

import support


class RunnerFailurePathsTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)

    def test_timeout_is_recorded_not_raised(self):
        db.create_job("s", support.spec("sleeper"))
        done = runner.run_next_job(timeout=2)
        self.assertIsNotNone(done, "a timed-out job must still be finished")
        self.assertEqual(done["status"], "done")
        self.assertEqual(done["exit_code"], -1)
        self.assertIn("TIMEOUT", Path(done["log_path"]).read_text(encoding="utf-8"))

    def test_the_timeout_actually_bounds_the_job(self):
        """Every assertion above passed while the bound did nothing.

        subprocess.run(shell=True, capture_output=True, timeout=N) killed the
        shell and then waited on the grandchild's pipe, so a 2 second timeout
        on a 30 second sleep took 30.1 seconds and still returned exit -1.
        Correct status, correct exit code, no bound. Only the clock showed it.
        """
        db.create_job("s", support.spec("sleeper"))
        start = time.monotonic()
        runner.run_next_job(timeout=2)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 10,
                        f"a 2s timeout took {elapsed:.1f}s, so the job was "
                        f"never actually stopped")

    def test_the_timeout_bounds_the_buffered_path_too(self):
        """`_run_bounded` is still a supported path and still has to hold.

        It is the sibling of the streaming runner, kept because its docstring
        records the measurement that produced both. A bound that only holds on
        the path the product happens to call today is a bound waiting to be
        wrong.
        """
        db.create_job("s", support.spec("sleeper"))
        start = time.monotonic()
        done = runner.run_next_job(timeout=2, stream=False)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 10, f"buffered path took {elapsed:.1f}s")
        self.assertEqual(done["exit_code"], -1)

    def test_a_recipe_whose_entrypoint_is_missing_is_refused(self):
        """The replacement for "a command that does not exist".

        A caller can no longer name a binary, so the missing-executable case
        now arrives from the recipe side: `recipe.toml` declares an entrypoint
        that is not on disk. It must be refused with a reason, not reported as
        a success and not raised as a traceback.
        """
        db.create_job("s", support.spec("brokenentry"))
        done = runner.run_next_job()
        self.assertIsNotNone(done)
        self.assertNotEqual(done["exit_code"], 0,
                            "a missing entrypoint must not report success")
        self.assertEqual(done["status"], "done")
        self.assertIn("REJECTED",
                      Path(done["log_path"]).read_text(encoding="utf-8"))

    def test_an_unknown_recipe_is_refused_rather_than_run(self):
        db.create_job("s", support.spec("no-such-recipe"))
        done = runner.run_next_job()
        self.assertEqual(done["exit_code"], runner.REJECTED)
        self.assertEqual(done["status"], "done")

    def test_stderr_output_reaches_the_log(self):
        db.create_job("s", support.spec("noisy", kind="eval"))
        done = runner.run_next_job()
        self.assertIn("boom", Path(done["log_path"]).read_text(encoding="utf-8"))

    def test_a_command_with_no_output_still_finishes(self):
        db.create_job("s", support.spec("silent", kind="prepare"))
        done = runner.run_next_job()
        self.assertEqual(done["exit_code"], 0)
        self.assertEqual(done["status"], "done")
        self.assertTrue(Path(done["log_path"]).exists(),
                        "a silent job must still leave a log file")

    def test_only_one_job_is_taken_per_call(self):
        db.create_job("s", support.spec("printer", message="a"))
        db.create_job("s", support.spec("printer", message="b"))
        runner.run_next_job()
        remaining = [j for j in db.list_jobs() if j["status"] == "queued"]
        self.assertEqual(len(remaining), 1,
                         "the runner must take exactly one job at a time")

    def test_a_job_runs_confined_to_its_own_run_directory(self):
        """cwd is the run directory, not the engine's working directory.

        A job that resolves a relative path must land inside its own run, so
        that a recipe writing `checkpoint.pt` cannot write over the engine's.
        """
        job = db.create_job("s", support.spec("printer", message="x"))
        runner.run_next_job()
        run_dir = jobspec.run_dir_for(job["id"])
        self.assertTrue((run_dir / "job.json").is_file())
        self.assertTrue((run_dir / jobspec.LOG_NAME).is_file(),
                        "a job's log belongs inside its own run directory")
        self.assertIn(str(self.root), str(run_dir.resolve()))

    def test_a_job_is_handed_the_engines_token_not_a_fresh_one(self):
        """Regression. Found by running a job against a live engine, not here.

        The runner is invoked as its own process, so minting a token with
        `security.current_token()` produced one this process accepted and the
        engine had never heard of - and the job's first API call came back 401.
        Every in-process test passed, because in one process the two happen to
        be the same string. The token must come from `engine.json`, which is
        what every other local client reads.
        """
        import ast
        import inspect
        import textwrap
        from app import security

        # Parsed, not grepped - the comment above `client_token()` in the
        # runner explains the bug and therefore names `current_token()`, and a
        # substring check cannot tell the explanation from the defect. Same
        # lesson as the shell=True invariant in tests/test_security_boundary.py.
        tree = ast.parse(textwrap.dedent(inspect.getsource(runner.run_next_job)))
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertIn("client_token", called)
        self.assertNotIn("current_token", called,
                         "the runner must not mint its own token")

        with tempfile.TemporaryDirectory() as engine_dir:
            portfile = Path(engine_dir) / "engine.json"
            security.write_portfile(path=portfile)
            published = security.read_portfile(portfile)
            self.assertEqual(security.client_token(portfile), published["token"])

    def test_a_job_does_not_inherit_the_engine_environment(self):
        """A provider key exported into the engine's shell stays there."""
        import os
        os.environ["MLH_TEST_SECRET_KEY"] = "sk-should-not-leak"
        try:
            env = jobspec.job_env()
        finally:
            del os.environ["MLH_TEST_SECRET_KEY"]
        self.assertNotIn("MLH_TEST_SECRET_KEY", env)
        self.assertEqual(env["HF_HUB_DISABLE_TELEMETRY"], "1")
        self.assertEqual(env["DO_NOT_TRACK"], "1")


class RunnerStreamsOutputTest(unittest.TestCase):
    """The log is live, not a lump delivered after the job is over.

    `communicate()` returns everything at once when the process has already
    exited, so a six-hour run showed nothing for six hours. That blocks every
    live pane the product needs, and it is indistinguishable from a job that is
    stuck.

    The proof is a job that prints, then blocks until this test creates a
    sentinel file, then prints again. If the runner buffered, the first line
    could not possibly be on disk while the job is still waiting - and the test
    would time out rather than pass by accident.
    """

    def setUp(self):
        self.root = support.sandbox(self)

    def test_output_is_readable_while_the_job_is_still_running(self):
        sentinel = self.root / "go.txt"
        db.create_job("s", support.spec("halting", sentinel=str(sentinel)))

        finished = []
        worker = threading.Thread(
            target=lambda: finished.append(runner.run_next_job(timeout=40)),
            daemon=True)
        worker.start()

        # Asked of `jobspec`, not spelled out here. The version of this line
        # that hardcoded `<repo>/logs/job_1.log` was reading a path shared by
        # the whole suite, so it could see - and did see - another test's job.
        log_path = jobspec.log_path_for(1)
        deadline = time.monotonic() + 15
        seen_first = False
        while time.monotonic() < deadline:
            if log_path.exists():
                text = log_path.read_text(encoding="utf-8", errors="replace")
                if "first" in text:
                    seen_first = True
                    # The job cannot have finished: it is blocked on the
                    # sentinel, which does not exist yet.
                    self.assertNotIn("second", text)
                    self.assertEqual(finished, [],
                                     "the job reported finished before it was")
                    break
            time.sleep(0.05)

        sentinel.write_text("go", encoding="utf-8")
        worker.join(timeout=40)

        self.assertTrue(seen_first,
                        "no output reached the log while the job was running, "
                        "so the runner is still buffering")
        self.assertTrue(finished, "the streaming job never finished")
        done = finished[0]
        self.assertEqual(done["exit_code"], 0)
        text = Path(done["log_path"]).read_text(encoding="utf-8")
        self.assertIn("first", text)
        self.assertIn("second", text)

    def test_partial_output_survives_a_timeout(self):
        """What the job printed before it was killed is the useful part.

        The buffered implementation replaced the whole log with the word
        TIMEOUT, throwing away the only evidence of where it got stuck.
        """
        never = self.root / "never.txt"
        db.create_job("s", support.spec("halting", sentinel=str(never)))
        done = runner.run_next_job(timeout=3)
        text = Path(done["log_path"]).read_text(encoding="utf-8")
        self.assertEqual(done["exit_code"], -1)
        self.assertIn("first", text)
        self.assertIn("TIMEOUT", text)
        self.assertNotIn("second", text)

    def test_the_streaming_primitive_returns_the_exit_code(self):
        """`_run_streaming` is a sibling of `_run_bounded`, held to the same bar."""
        run_dir = self.root / "direct"
        run_dir.mkdir()
        spec = support.spec("failing")
        jobspec.prepare_run_dir(spec, run_dir)
        log_path = run_dir / "out.log"
        code = runner._run_streaming(
            jobspec.resolve_argv(spec, run_dir), 30, log_path,
            cwd=run_dir, env=jobspec.job_env())
        self.assertEqual(code, 3)
        self.assertTrue(log_path.exists())

    def test_the_streaming_primitive_raises_on_timeout(self):
        spec = support.spec("sleeper")
        run_dir = self.root / "slow"
        run_dir.mkdir()
        jobspec.prepare_run_dir(spec, run_dir)
        start = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            runner._run_streaming(
                jobspec.resolve_argv(spec, run_dir), 2, run_dir / "out.log",
                cwd=run_dir, env=jobspec.job_env())
        self.assertLess(time.monotonic() - start, 10)


if __name__ == "__main__":
    unittest.main()
