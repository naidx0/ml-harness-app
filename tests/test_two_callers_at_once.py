"""Nothing in this suite called two things at the same time, and the product says so.

## The class

Ask what a test in this repository never does and one answer is: two things at
once. Every test is a single thread issuing one call, waiting for it, and
asserting on the result. `test_migrations_survive_concurrency` is the sole
exception in 1057 tests, and it concerns one table.

That is a shape a real machine does not have. The engine serves a request while
a supervisor thread drives a job; a storm runs four steps in a thread pool; a
person can press a control while a turn is in flight. Every read-then-write
sequence in the product is exercised only by callers that arrive one at a time,
so a race is untested by construction rather than by oversight.

## What that hid, in the product's own words

`app/tools/training.py` opened with this, next to a module-level lock:

    One job at a time in this process. `db.next_queued_job` selects the oldest
    queued row and does *not* claim it, so two supervisors running at once would
    both start the same job. THAT IS A DEFECT IN `app/db.py` rather than here;
    this lock keeps this module from being the thing that triggers it.

A named defect, with a stated mitigation, and **no test anywhere asserted
either half**: not that the read failed to claim, and not that the lock was
what stood in for a claim. The comment was the entire specification.

The mitigation was also narrower than it read. `_SLOT` is a `threading.Lock`,
so it is one process wide. Two engines on one database - the arrangement
`app/storm.py` explicitly plans for, which is why `_LIVE` is process-local and
documented as such - have two locks and one job queue, and both would have run
the same training job: the same subprocess tree twice, the same run directory
twice, two sets of metrics for one run.

`test_a_leftover_live_id_...` in
`tests/test_process_state_does_not_outlive_a_test.py` is the same lesson from
the other side. This file is the read-then-write half.

## CLOSED 2026-09-02

`db.next_queued_job` is now one statement - `UPDATE ... WHERE id = (SELECT id
... LIMIT 1) RETURNING *` - so the row is claimed by the same statement that
finds it and there is no window between the two for a second caller to arrive
in. `OPEN_RACES_NOW` went 1 -> 0 in that commit, which is this file's own rule:
a wrapper comes off only in the commit that fixes what it names.

The probes below are kept and are now ordinary tests. They are the regression
guard: the day somebody rewrites the claim as a select, the concurrency probe
goes red for the reason it was written for, and `test_taking_the_queue_claims_
what_it_hands_out` names the missing `UPDATE` directly.

## Why the probe here is not flaky

It was never about timing. When `next_queued_job` was a `SELECT` that mutated
nothing, a second caller got the same row whether it arrived a microsecond
later or a minute later - the answer was deterministic, and the concurrency is
here to show the shape a real caller has rather than to provoke a window. Now
that the statement claims, the same determinism runs the other way: exactly one
of the two callers can win the UPDATE, whenever they arrive.
`support.concurrently()` releases every thread from one barrier so the calls do
overlap, and it captures each exception rather than letting a worker thread
raise into nowhere.
"""

from __future__ import annotations

import unittest
from typing import Callable

from app import db

import support


#: Defect id -> what races, in one line. Filled by the decorator below.
OPEN_RACES: dict[str, str] = {}

#: How many races are open. ONE at the commit this file was written against;
#: ZERO since 2026-09-02, when `next_queued_job` became an atomic claim
#: (`app/db.py`) and `next_queued_job_does_not_claim` was closed rather than
#: carried. The file's own rule at the decorator below is that a wrapper comes
#: off only in the commit that fixes what it names, and that commit lowers this.
OPEN_RACES_NOW = 0


def open_race(race: str, mechanism: str) -> Callable[[Callable], Callable]:
    """Mark one probe as CURRENTLY RACING, by name and with a reason.

    Not a skip, for the reason `tests/test_laundering_routes.py` gives: a skip
    measures nothing and reads as green. An expected failure runs the probe,
    watches the race happen, and turns the build red on the day it is fixed.
    """

    def decorate(method: Callable) -> Callable:
        if race in OPEN_RACES:
            raise AssertionError(f"{race} is declared open twice")
        OPEN_RACES[race] = mechanism
        method.open_race = race  # type: ignore[attr-defined]
        return unittest.expectedFailure(method)

    return decorate


class TheJobQueueTestCase(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)

    def queue(self, message: str) -> dict:
        return db.create_job("intake-1", support.spec("printer", message=message))


class TheHelperIsWhatMakesTheProbePossibleTest(TheJobQueueTestCase):
    """Before asserting about a race, assert the two callers really are two."""

    def test_both_callables_run_and_both_answers_come_back(self):
        results = support.concurrently(lambda: "left", lambda: "right")

        self.assertEqual([r.get("value") for r in results], ["left", "right"])

    def test_an_exception_in_one_caller_is_reported_and_not_lost(self):
        def boom():
            raise ValueError("from a worker thread")

        results = support.concurrently(boom, lambda: "fine")

        self.assertIsInstance(results[0]["error"], ValueError)
        self.assertEqual(results[1]["value"], "fine")


class TwoSupervisorsWouldStartTheSameJobTest(TheJobQueueTestCase):
    """The open race, and both halves of the product's own comment."""

    def test_only_one_job_is_queued(self):
        """The setup, asserted, so the probe below cannot pass on an empty queue."""
        job = self.queue("only one")

        self.assertEqual(job["status"], "queued")
        self.assertEqual(
            [row["id"] for row in db.list_jobs() if row["status"] == "queued"],
            [job["id"]],
        )

    def test_taking_the_queue_claims_what_it_hands_out(self):
        """The mechanism, stated directly: taking a job marks it taken.

        This test's own docstring used to say the opposite - "the read is a
        read" - and said why it was written that way: *"Pinning it here means
        the day somebody adds claiming, this test says so rather than the race
        probe silently going green."* This is that day, and this is the test
        saying so.
        """
        job = self.queue("claimed on the way out")

        handed = db.next_queued_job()

        self.assertEqual(handed["id"], job["id"])
        self.assertEqual(
            db.get_job(job["id"])["status"],
            "running",
            "next_queued_job handed the row out without marking it, so a "
            "second caller can still be handed the same job",
        )

    def test_a_claimed_job_is_not_handed_out_again(self):
        """The consequence that makes the claim worth having."""
        self.queue("the only job")

        first = db.next_queued_job()
        second = db.next_queued_job()

        self.assertIsNotNone(first)
        self.assertIsNone(
            second,
            "the queue handed out a job it had already claimed",
        )

    def test_two_callers_at_once_are_not_handed_the_same_job(self):
        self.queue("the only job")

        results = support.concurrently(db.next_queued_job, db.next_queued_job)

        self.assertEqual([r.get("error") for r in results], [None, None], results)
        first, second = (r["value"] for r in results)
        self.assertNotEqual(
            (first or {}).get("id"),
            (second or {}).get("id"),
            "next_queued_job_does_not_claim: two callers arriving together were "
            f"both handed job {(first or {}).get('id')}. One of them should have "
            "been told the queue is empty.",
        )


class TheOpenRaceRosterIsHonestTest(unittest.TestCase):
    def test_the_count_matches_the_decorations(self):
        self.assertEqual(len(OPEN_RACES), OPEN_RACES_NOW)


class EveryOpenRaceFailsForTheRightReasonTest(unittest.TestCase):
    """`expectedFailure` swallows a broken probe as happily as a real race."""

    def test_each_open_race_fails_on_its_own_assertion(self):
        case = TwoSupervisorsWouldStartTheSameJobTest
        methods = {
            name: function
            for name, function in vars(case).items()
            if getattr(function, "open_race", None)
        }
        self.assertEqual(
            sorted(getattr(f, "open_race") for f in methods.values()),
            sorted(OPEN_RACES),
            "an @open_race decoration did not land on a test method",
        )

        for name, function in sorted(methods.items()):
            race = getattr(function, "open_race")
            with self.subTest(race=race):
                result = unittest.TestResult()
                case(name).run(result)

                self.assertEqual(
                    len(result.expectedFailures),
                    1,
                    f"{race} did not race - it is closed, so delete its "
                    "@open_race line and lower OPEN_RACES_NOW",
                )
                _, trace = result.expectedFailures[0]
                self.assertIn("AssertionError", trace, trace)
                self.assertIn(
                    race,
                    trace,
                    f"{race} failed on an assertion that does not name it, so "
                    f"expectedFailure may be hiding a broken probe:\n{trace}",
                )


if __name__ == "__main__":
    unittest.main()
