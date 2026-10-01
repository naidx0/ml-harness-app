"""A broken instance identity must refuse jobs, not jam the queue.

`app/runner.py` says, above its refusal handler: "Refusals are recorded, not
raised. A job the runner will not start is a finished job with a reason in its
log; leaving it queued would jam the single slot behind a row that can never
succeed."

Two lines sat outside that handler and broke the promise. Deriving the run
directory validates this database's instance identity - the value that names
the directory (`jobspec.runs_root_for`) - and refuses an identity that cannot
be a directory name. Because the derivation was above the `try`, that one
refusal escaped `run_next_job` as an exception. The row stayed `queued`, so
`db.next_queued_job()` handed the same unstartable job to the next invocation,
and the next, forever: the single slot jammed by exactly the mechanism the
comment describes, arriving through the only line that was not covered by it.

Nothing in the suite could see it. Every other test starts from a database
whose identity was minted seconds earlier by `db.get_instance()`, and a fresh
uuid always passes. The failure needs a database that has been damaged since -
a hand-edited row, a restored backup, a botched migration - so this file makes
one.
"""
import unittest
from pathlib import Path

from app import db, jobspec, runner

import support


def corrupt_the_instance_identity(value):
    """Damage this database's identity the way the real world would.

    Not by monkeypatching `jobspec.current_instance`: the point is a database
    on disk holding a value it should never hold, read back through the same
    call the runner makes. `db.get_instance()` self-heals a *missing* row with
    `INSERT OR IGNORE`, so a row that is present and wrong is the shape that
    survives, and it is the shape a damaged database actually has.
    """
    db.get_instance()                     # mint the row, then spoil it
    with db.session() as connection:
        connection.execute(
            "UPDATE harness_instance SET instance_id = ? WHERE id = 1",
            (value,),
        )


class CorruptInstanceIdentityTest(unittest.TestCase):
    #: A value that is both unusable as a directory name and actively hostile
    #: as one. If it ever reached the filesystem it would climb out of the
    #: artifact root, so the test below can check containment rather than
    #: taking "it was rejected" on trust.
    CORRUPT = "../../escape"

    def setUp(self):
        self.root = support.sandbox(self)

    def test_a_corrupt_identity_finishes_the_job_instead_of_raising(self):
        corrupt_the_instance_identity(self.CORRUPT)
        job = db.create_job("s", support.spec("printer", message="hi"))

        done = runner.run_next_job()

        self.assertIsNotNone(done, "the refused job was never finished")
        self.assertEqual(done["status"], "done")
        self.assertEqual(done["exit_code"], runner.REJECTED)
        self.assertEqual(done["id"], job["id"])

    def test_the_refusal_carries_a_reason(self):
        """A refusal nobody can read is barely better than no refusal."""
        corrupt_the_instance_identity(self.CORRUPT)
        db.create_job("s", support.spec("printer", message="hi"))

        done = runner.run_next_job()

        self.assertTrue(done["log_path"], "a refusal with no log has no reason")
        text = Path(done["log_path"]).read_text(encoding="utf-8")
        self.assertIn("REJECTED", text)
        self.assertIn("instance identity", text)
        self.assertIn(self.CORRUPT, text,
                      "the reason must name the value that was refused")

    def test_the_queue_is_not_jammed_behind_the_refused_row(self):
        """The failure this whole file is about.

        Before the fix the raise left the row `queued`, so every later
        invocation picked up the same job and died on it again. Two queued jobs
        make that visible: a jammed slot refuses to advance past the first one.
        """
        corrupt_the_instance_identity(self.CORRUPT)
        db.create_job("s", support.spec("printer", message="one"))
        second = db.create_job("s", support.spec("printer", message="two"))

        first_done = runner.run_next_job()
        second_done = runner.run_next_job()

        self.assertEqual(second_done["id"], second["id"],
                         "the runner never got past the first refused job")
        self.assertNotEqual(first_done["id"], second_done["id"])
        self.assertEqual(
            [j for j in db.list_jobs() if j["status"] == "queued"], [],
            "a refused job that stays queued is a jammed slot")
        self.assertIsNone(runner.run_next_job(),
                          "the slot must be free once the queue is drained")

    def test_the_corrupt_value_never_becomes_a_path(self):
        """The refusal is written somewhere safe, or it is not a refusal.

        `../../escape` names a real place - two levels above the artifact root.
        Recording the reason must not be the thing that lets the rejected value
        pick the directory.
        """
        corrupt_the_instance_identity(self.CORRUPT)
        db.create_job("s", support.spec("printer", message="hi"))

        done = runner.run_next_job()

        written = Path(done["log_path"]).resolve()
        artifact_root = Path(jobspec.RUNS_ROOT).resolve()
        self.assertTrue(
            str(written).startswith(str(artifact_root)),
            f"the refusal log escaped the artifact root: {written}")
        self.assertNotIn("escape", written.parts)
        self.assertIn(runner.UNIDENTIFIED, written.parts)

    def test_the_quarantine_name_cannot_collide_with_a_real_identity(self):
        """`db.get_instance()` mints `uuid4().hex`, and nothing else does.

        The quarantine directory sits beside real run directories, so the one
        thing it must never do is occupy a name a real database could later be
        given. Thirty-two lowercase hex characters is the whole minted space;
        this name is outside it, and this assertion is what keeps it outside if
        somebody ever shortens it.
        """
        import re
        self.assertIsNone(re.fullmatch(r"[0-9a-f]{32}", runner.UNIDENTIFIED))

    def test_an_empty_identity_is_refused_the_same_way(self):
        """The other shape a damaged row takes, and the cheaper one to hit."""
        corrupt_the_instance_identity("")
        db.create_job("s", support.spec("printer", message="hi"))

        done = runner.run_next_job()

        self.assertEqual(done["exit_code"], runner.REJECTED)
        self.assertEqual(done["status"], "done")
        self.assertIn("REJECTED",
                      Path(done["log_path"]).read_text(encoding="utf-8"))

    def test_a_log_that_cannot_be_written_still_frees_the_slot(self):
        """The row is the part that must always be written.

        Recording the reason is best effort by design: if the disk refuses the
        log too, letting that failure out of the refusal path would jam the
        single slot for the second time on the same code path. The job is
        finished either way, with `log_path` empty rather than pointing at a
        file that is not there - which `/jobs/{id}/log` already reads as "no
        output yet" instead of a 500.
        """
        from unittest import mock

        blocked = self.root / "not-a-directory"
        blocked.write_text("", encoding="utf-8")
        corrupt_the_instance_identity(self.CORRUPT)
        db.create_job("s", support.spec("printer", message="hi"))

        with mock.patch.object(runner, "_refusal_log_path",
                               return_value=blocked / "job_1" / "job.log"):
            done = runner.run_next_job()

        self.assertEqual(done["exit_code"], runner.REJECTED)
        self.assertEqual(done["status"], "done")
        self.assertIsNone(done["log_path"])
        self.assertIsNone(runner.run_next_job(), "the slot is still jammed")

    def test_a_healthy_identity_still_runs_the_job(self):
        """The guard must refuse damage, not traffic.

        A test that only proves refusals is satisfied by a runner that refuses
        everything, which is why this one is in the same file.
        """
        db.create_job("s", support.spec("printer", message="hi"))

        done = runner.run_next_job()

        self.assertEqual(done["exit_code"], 0)
        self.assertIn("hi",
                      Path(done["log_path"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
