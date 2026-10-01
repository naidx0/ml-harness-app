"""A rehearsal records the code it DROVE, not the code that was checked out.

## The measurement this exists because of

`docs/readiness-rehearsal-2026-09-11.md` recorded `engine build b17f320
(clean)` and meant the checkout's HEAD. The process on 8078 started
2026-09-10 02:43:02 with no `--reload`; `a443add`, which made
`assess_the_data`'s `path` optional, landed at 15:21 the same day. The report
then blamed the model for not calling a tool whose no-path form did not exist
in the process it was driving, and one of its four findings had to be withdrawn.

**A long-lived engine serves the build it started with.** The checkout's HEAD
is a fact about a directory; what the stranger meets is a fact about a process,
and nothing in that run asked the second question.

## What is held here

Not the number - the number changes every time anybody commits. What is held is
that an UNDECIDABLE gap renders as unknown rather than as zero, which is this
repository's provenance law applied to its own instruments: a figure nobody
could measure must not arrive looking like a measurement of nothing. "Level with
the remote" and "could not tell" are different sentences and only one of them
means somebody can trust the run.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import support

from app import db

driver = support.import_file(
    "drive_it_as_a_stranger",
    support.REPO_ROOT / "scripts" / "drive_it_as_a_stranger.py",
)


class WhatTheEngineIsRunningTest(unittest.TestCase):
    def _said(self, found: dict) -> str:
        page = io.StringIO()
        with redirect_stdout(page):
            driver.say_how_stale_the_engine_is(found)
        return page.getvalue()

    def test_a_gap_nobody_could_measure_is_unknown_and_not_level(self):
        """THE CASE. `None` means the question could not be asked - the process
        table would not answer, or git would not. Rendering that as "level"
        would tell a reader the run drove current code on the strength of a
        failure."""
        said = self._said({"behind": None}).lower()
        self.assertIn("unknown", said)
        self.assertNotIn("engine is level", said)

    def test_zero_is_level_and_says_so_plainly(self):
        """A measured zero is a real answer and must not be hedged into the
        same sentence as a failure."""
        said = self._said({"behind": 0}).lower()
        self.assertIn("engine is level", said)
        self.assertNotIn("unknown", said)

    def test_a_gap_names_the_commits_the_engine_is_not_running(self):
        """A count with no commits behind it is a number somebody has to go and
        reconstruct at the end of a run they have already paid for."""
        said = self._said(
            {
                "behind": 2,
                "behind_its_own_checkout": 1,
                "checkout": "/somewhere",
                "commits_since_the_engine_started": [
                    "aaaaaaa a change the engine is not running",
                    "bbbbbbb another",
                ],
            }
        )
        self.assertIn("a change the engine is not running", said)
        self.assertIn("2", said)

    def test_the_card_is_resolved_and_not_spelled_out(self):
        """`MLH_STRANGER_LOCK` is the seam the tests use, and its existence is
        why no home directory or vault name is in the shipped file. See
        `test_no_shipped_file_names_a_person`, which refuses the other way."""
        with tempfile.TemporaryDirectory() as where:
            named = Path(where) / "gpu.lock"
            os.environ["MLH_STRANGER_LOCK"] = str(named)
            try:
                self.assertEqual(named, driver._the_card())
            finally:
                del os.environ["MLH_STRANGER_LOCK"]

    def test_the_ledger_sits_beside_the_card(self):
        """The take and the release go to `gpu.lock.log` beside the lock, which
        is the amendment the first driver ignored entirely."""
        with tempfile.TemporaryDirectory() as where:
            named = Path(where) / "gpu.lock"
            self.assertEqual(
                named.parent / "gpu.lock.log", driver.card.the_log_beside(named)
            )

class TheEventsComeFromTheEnginesDatabaseTest(unittest.TestCase):
    """A run reads the database the ENGINE WRITES TO, or it refuses.

    ## Measured 2026-09-11 03:38, before it produced a false measurement

    Run from the intake worktree, this script resolved `app.db.DB_PATH` to that
    worktree's own `ml_harness.db` - a file that DOES NOT EXIST - so
    `events.since` would have returned nothing for every turn and the
    transcript would have carried four turns with empty event lists.

    Not a crash. A confident, silent nothing, in the file a report gets written
    from. The portfile had the same fault an hour earlier, and fixing that one
    without asking what else in here assumed this checkout was the engine's is
    how the second half survived.

    ## Why a refusal rather than a fallback

    An empty database opens and answers every query with no rows, which is
    indistinguishable from a quiet conversation. There is no reading of "no
    events" that is safe to report, so the only honest move is to refuse before
    the card is taken - the same rule the portfile check follows two functions
    above it.
    """

    def setUp(self):
        support.sandbox(self)
        self.where = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.where, True)
        #: `settle` assigns a module global that the whole suite shares.
        self.addCleanup(setattr, db, "DB_PATH", db.DB_PATH)
        self.addCleanup(setattr, driver, "ENGINE_CHECKOUT", driver.ENGINE_CHECKOUT)

    def test_a_checkout_with_no_database_refuses_before_taking_the_card(self):
        """THE CASE. The worktree this was run from had no `ml_harness.db` at
        all, and nothing said so."""
        driver.ENGINE_CHECKOUT = self.where
        with self.assertRaises(SystemExit) as refused:
            driver._the_engine_database()
        said = str(refused.exception)
        self.assertIn(str(self.where), said, "the refusal does not say where it looked")
        self.assertIn("before taking the card", said)

    def test_it_reads_the_database_beside_the_engine(self):
        beside = self.where / "ml_harness.db"
        beside.write_bytes(b"")
        driver.ENGINE_CHECKOUT = self.where
        self.assertEqual(beside, driver._the_engine_database())

    def test_the_apps_own_override_still_wins(self):
        """`ML_HARNESS_DB` is `app.db`'s seam and this does not get to outrank
        it. A person who has named a database has answered the question."""
        named = self.where / "somewhere-else.db"
        named.write_bytes(b"")
        os.environ["ML_HARNESS_DB"] = str(named)
        self.addCleanup(os.environ.pop, "ML_HARNESS_DB", None)
        driver.ENGINE_CHECKOUT = self.where
        (self.where / "ml_harness.db").write_bytes(b"")
        self.assertEqual(named, driver._the_engine_database())

    def test_settle_actually_points_the_reader_at_it(self):
        """THE WIRING, which is the half that was broken. Resolving the right
        path and not assigning it would read exactly as wrong as before.

        ASSIGNED RATHER THAN PUT IN THE ENVIRONMENT, because `app.security`
        imports `app.db`, so `DB_PATH` is already resolved by the time any of
        this runs and a value placed in `ML_HARNESS_DB` now would be read by
        nobody."""
        beside = self.where / "ml_harness.db"
        beside.write_bytes(b"")
        portfile = self.where / "engine.json"
        portfile.write_text(json.dumps({"port": 1, "token": "x"}), encoding="utf-8")
        os.environ["MLH_ENGINE_PORTFILE"] = str(portfile)
        os.environ["MLH_STRANGER_LOCK"] = str(self.where / "gpu.lock")
        self.addCleanup(os.environ.pop, "MLH_ENGINE_PORTFILE", None)
        self.addCleanup(os.environ.pop, "MLH_STRANGER_LOCK", None)

        driver.settle([str(self.where / "out.json"), "6", "a test"])

        self.assertEqual(beside, db.DB_PATH)

if __name__ == "__main__":
    unittest.main()
