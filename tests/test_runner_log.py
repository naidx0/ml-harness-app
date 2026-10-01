"""Regression tests for the job runner's log handling.

Hand-written, not generated. The generated acceptance test for 4.2b asserted
only `"1" in text`, which an appending writer passes just as happily as an
overwriting one - so it never noticed that a second job reusing id 1 left both
runs' output in the same file.

**Rewritten again, and this time the fix was not "truncate harder".** What this
file used to assert was that two databases both minting job id 1 write *the
same log path*, and that the second run's write wipes the first. That was a
faithful description of the behaviour, and the behaviour was the defect: a user
who resets their database gets job id 1 back, and its artifacts land on top of
the previous job 1's - two runs' history in one place, silently, with nothing
afterwards to say which output belonged to which. A monotonic counter that
restarts at 1 is not an identity, so paths are keyed on the database's own
identity now (`jobspec.current_instance()`), and the collision is not survivable-with-care
but unconstructible. `test_two_databases_both_minting_job_1_cannot_collide` is
the attempt to construct it.

The truncation tests stay, because the two halves are independent. Identity
stops two *databases* sharing a path. Ownership of the file stops one *call*
inheriting bytes it did not write - which is a separate way for a log to end up
holding a stranger's output, and the way that actually produced the observed
flake: the `TimeoutExpired` handler opened with `"a"`, so a job that timed out
having printed nothing yet came back with a complete run of someone else's
output followed by the word TIMEOUT.
"""
import unittest
from pathlib import Path

from app import db, jobspec, runner

import support


class RunnerLogTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)

    def test_two_databases_both_minting_job_1_cannot_collide(self):
        """The original collision, constructed on purpose.

        Two databases, each handing out job id 1, each running a job whose
        output says which one it was. Under the old layout both wrote
        `<repo>/logs/job_1.log` and both wrote `<repo>/runs/job_1/`, so the
        second run destroyed the first one's evidence and this test's first
        four assertions were all false at once.

        Note what is asserted last and why it matters more than the path
        comparison: the *first* job's log is re-read after the second job has
        been and gone. A fix that merely made the second job truncate more
        aggressively would pass an inequality check on the two paths and still
        fail here.
        """
        first_instance = jobspec.current_instance()
        db.create_job("s1", support.spec("printer", message="11111"))
        first = runner.run_next_job()

        # A fresh database restarts ids at 1. This is the user who deleted
        # ml_harness.db and started over, not a contrived scenario.
        db.DB_PATH = self.root / "second.db"
        db.init_db()
        second_instance = jobspec.current_instance()
        db.create_job("s2", support.spec("printer", message="22222"))
        second = runner.run_next_job()

        self.assertEqual(first["id"], 1)
        self.assertEqual(second["id"], 1, "both jobs must really be job 1")
        self.assertNotEqual(first_instance, second_instance,
                            "two databases must not share an identity")

        self.assertNotEqual(first["log_path"], second["log_path"])
        self.assertNotEqual(
            str(jobspec.run_dir_for(1, first_instance)),
            str(jobspec.run_dir_for(1, second_instance)),
            "two databases' job 1 must not share a run directory")

        # Neither run directory may contain the other, or "different path"
        # would still leave one job writing inside another job's artifacts.
        first_dir = jobspec.run_dir_for(1, first_instance).resolve()
        second_dir = jobspec.run_dir_for(1, second_instance).resolve()
        self.assertNotIn(first_dir, second_dir.parents)
        self.assertNotIn(second_dir, first_dir.parents)

        earlier = Path(first["log_path"]).read_text(encoding="utf-8")
        later = Path(second["log_path"]).read_text(encoding="utf-8")
        self.assertIn("11111", earlier)
        self.assertNotIn("22222", earlier)
        self.assertIn("22222", later)
        self.assertNotIn("11111", later)

    def test_a_jobs_log_lives_inside_that_jobs_run_directory(self):
        """One job is one directory: job.json going in, job.log coming out.

        The log used to live in a separate flat folder, which meant a job's
        artifacts were in two places and only one of them was ever isolated -
        so isolating a test's run directory did nothing about its log.
        """
        db.create_job("s1", support.spec("printer", message="inside"))
        done = runner.run_next_job()
        run_dir = jobspec.run_dir_for(1)
        self.assertEqual(Path(done["log_path"]).parent.resolve(),
                         run_dir.resolve())
        self.assertTrue((run_dir / "job.json").is_file())
        self.assertTrue((run_dir / jobspec.LOG_NAME).is_file())

    def test_a_stale_file_at_a_jobs_log_path_is_not_inherited(self):
        """The runner owns this file for the whole call, or it owns nothing.

        Identity makes a collision between two databases unconstructible; it
        says nothing about a file already sitting at the path this call is
        about to use - a re-run, a crash, a partially cleaned directory. The
        run that starts must not be able to report someone else's output as its
        own.
        """
        db.create_job("s1", support.spec("printer", message="mine"))
        planted = jobspec.log_path_for(1)
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text("OUTPUT-OF-SOME-EARLIER-RUN\n", encoding="utf-8")

        done = runner.run_next_job()
        text = Path(done["log_path"]).read_text(encoding="utf-8")
        self.assertIn("mine", text)
        self.assertNotIn("OUTPUT-OF-SOME-EARLIER-RUN", text)

    def test_a_timed_out_job_does_not_inherit_a_stale_log(self):
        """The `"a"` in the TimeoutExpired handler, held to the same rule.

        This is the exact shape of the observed failure: a log that reads
        `hello-4-3\\nkind=train\\n\\nTIMEOUT\\n` - a complete, successful run of
        a different recipe, then a timeout marker from this one. The append is
        still the right call, because what the job printed before it was killed
        is the most useful thing on disk; it is only honest because the file
        was emptied by this call first.
        """
        never = self.root / "never.txt"
        db.create_job("s1", support.spec("halting", sentinel=str(never)))
        planted = jobspec.log_path_for(1)
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text("OUTPUT-OF-SOME-EARLIER-RUN\n", encoding="utf-8")

        done = runner.run_next_job(timeout=3)
        text = Path(done["log_path"]).read_text(encoding="utf-8")
        self.assertEqual(done["exit_code"], -1)
        self.assertNotIn("OUTPUT-OF-SOME-EARLIER-RUN", text)
        self.assertIn("first", text, "the partial output must still survive")
        self.assertIn("TIMEOUT", text)

    def test_a_timed_out_buffered_job_does_not_inherit_a_stale_log(self):
        """The branch where nothing else was covering for the append.

        On the streaming path `_run_streaming` opens the log `"w"` before the
        clock runs out, so the append had something of its own to append to by
        accident. On the buffered path nothing in the call touches the file at
        all before `TimeoutExpired` is raised, so `"a"` wrote the marker
        directly onto whatever the previous holder of the path had left. That
        makes this the case that proves the truncation and not the sibling.
        """
        db.create_job("s1", support.spec("sleeper"))
        planted = jobspec.log_path_for(1)
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text("OUTPUT-OF-SOME-EARLIER-RUN\n", encoding="utf-8")

        done = runner.run_next_job(timeout=2, stream=False)
        text = Path(done["log_path"]).read_text(encoding="utf-8")
        self.assertEqual(done["exit_code"], -1)
        self.assertIn("TIMEOUT", text)
        self.assertNotIn("OUTPUT-OF-SOME-EARLIER-RUN", text)

    def test_a_refused_job_does_not_inherit_a_stale_log(self):
        """A refusal is a finished job with a reason, and only that reason."""
        db.create_job("s1", support.spec("no-such-recipe"))
        planted = jobspec.log_path_for(1)
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text("OUTPUT-OF-SOME-EARLIER-RUN\n", encoding="utf-8")

        done = runner.run_next_job()
        text = Path(done["log_path"]).read_text(encoding="utf-8")
        self.assertEqual(done["exit_code"], runner.REJECTED)
        self.assertIn("REJECTED", text)
        self.assertNotIn("OUTPUT-OF-SOME-EARLIER-RUN", text)

    def test_exit_code_of_a_failing_command_is_recorded(self):
        db.create_job("s3", support.spec("failing"))
        done = runner.run_next_job()
        self.assertEqual(done["exit_code"], 3)
        self.assertEqual(done["status"], "done")

    def test_config_reaches_the_job_without_touching_argv(self):
        """The round-trip that replaces the command string.

        Caller data goes into `run_dir/job.json` and the entrypoint reads it.
        Nothing the caller wrote appears on the command line, which is what
        makes quoting a non-problem rather than a solved problem.
        """
        job = db.create_job("s4", support.spec("printer", message="via-job-json"))
        done = runner.run_next_job()
        self.assertIn("via-job-json",
                      Path(done["log_path"]).read_text(encoding="utf-8"))
        argv = jobspec.resolve_argv(
            support.spec("printer", message="via-job-json"),
            jobspec.run_dir_for(job["id"]))
        self.assertNotIn("via-job-json", " ".join(argv))


class InstanceIdentityTest(unittest.TestCase):
    """The property the run directory is keyed on, tested on its own.

    Keyed on a value that is not stable, the layout would move under a running
    job; keyed on a value that is not unique, it would collide again. Both are
    checked here rather than only through the runner, because the runner takes
    a couple of seconds per job and this is the invariant every artifact path
    in the product rests on.
    """

    def setUp(self):
        self.root = support.sandbox(self)

    def test_the_identity_is_stable_across_calls_and_connections(self):
        first = jobspec.current_instance()
        second = jobspec.current_instance()
        self.assertEqual(first, second)
        db.init_db()          # re-running init must not re-mint
        self.assertEqual(jobspec.current_instance(), first)

    def test_every_database_gets_its_own_identity(self):
        seen = set()
        for index in range(5):
            db.DB_PATH = self.root / f"db{index}.db"
            db.init_db()
            seen.add(jobspec.current_instance())
        self.assertEqual(len(seen), 5)

    def test_a_database_written_before_identities_existed_gets_one(self):
        """No migration step for anyone to forget.

        A database from before this table existed is just a database without
        the row. Asking for the identity mints it, so an existing install keeps
        working the first time it runs a job rather than the first time
        somebody remembers to upgrade it.
        """
        db.DB_PATH = self.root / "legacy.db"
        db.init_db()
        with db.session() as connection:
            connection.execute("DROP TABLE harness_instance")

        recovered = jobspec.current_instance()
        self.assertTrue(recovered)
        self.assertEqual(jobspec.current_instance(), recovered)

    def test_an_identity_can_never_become_a_path(self):
        """It is a directory name, so it is held to the recipe-name rule.

        `db.get_instance()` mints a uuid hex and nothing else, so this is a
        guard against a future caller, not against today's one - which is the
        only time a guard is worth writing.
        """
        for hostile in ("..", "../..", "a/b", "a\\b", ".hidden", "", 7):
            with self.subTest(instance=hostile):
                with self.assertRaises(jobspec.JobRejected):
                    jobspec.run_dir_for(1, hostile)

        # `None` is not hostile, it is the documented default: "the database
        # currently bound". A caller who passes nothing still gets the
        # guarantee, which is the whole reason the parameter has a default.
        self.assertEqual(jobspec.run_dir_for(1),
                         jobspec.run_dir_for(1, jobspec.current_instance()))

    def test_a_database_holds_exactly_one_identity(self):
        """Repeated minting must not leave a second row to disagree with.

        `INSERT OR IGNORE` against a fixed primary key is what makes this true,
        and two processes racing to mint hit exactly the same path as calling
        it twice here: the loser's insert is dropped and it reads the winner's
        value. Asserted as row count rather than as SQL so the guarantee
        outlives the spelling.
        """
        minted = jobspec.current_instance()
        for _ in range(3):
            self.assertEqual(jobspec.current_instance(), minted)
        with db.session() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM harness_instance").fetchone()
        self.assertEqual(row["n"], 1)


if __name__ == "__main__":
    unittest.main()
