"""A plan's identity must not move on its own, and must survive being recorded.

Two defects, one theme: `Build.fingerprint()` is what "approval is a contract"
compares, so anything it hashes that changes without the plan changing breaks
approval, and anything the plan carries that the record drops is a claim nobody
checked.

THE FIRST ONE WAS LIVE AND IT BROKE APPROVAL FOR EVERY HUMAN. `DataSnapshot.of`
set `how=f"{size.how}, read at {size.at}"`, and `Reading.at` is
`datetime.now(timezone.utc)` to the second. `POST /api/storms` re-proposes
server-side and refuses unless the digest matches what was approved - so the
approval failed whenever more than one second passed between the client
proposing and the server re-proposing, which for a person reading a plan is
always. It also made two storm tests intermittently red at roughly one run in
eight.

The line it turned on: a snapshot's size and modification time are properties OF
THE DATA and belong in the hash, because a plan costed against a different file
is a different plan. The moment somebody happened to look is a property of the
RUN and does not.

THE SECOND is `Step.operates_on` - what a step's cost was measured against. It
was held out of `Step.as_dict()` because `app/storm.py` refuses to rehydrate a
recorded key it cannot map onto a constructor argument, and emitting it before
the storm knew about it turned every approval into a 409. That guard is right.
The answer was to teach the storm, not to keep the field out of the record: a
plan whose subject is not recorded is a plan whose most important claim gets
re-derived on trust.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import support  # noqa: E402

from app import events  # noqa: E402
from app.build import Subject  # noqa: E402
from app.storm import _a_step_again  # noqa: E402
from app.tools import evidence  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402


class APlanIsTheSamePlanASecondLaterTest(unittest.TestCase):
    """The clock is not part of the plan."""

    def an_eval_file(self, rows: int, name: str = "eval.jsonl") -> Path:
        path = Path(tempfile.mkdtemp()) / name
        with path.open("w", encoding="utf-8") as handle:
            for index in range(rows):
                handle.write(
                    json.dumps({"input": f"ticket {index}",
                                "output": f"route {index % 4}"}) + "\n"
                )
        return path

    def setUp(self) -> None:
        support.sandbox(self)
        self.thread_id = support.a_conversation(1, title="keeping its identity")[0]["id"]
        self.path = self.an_eval_file(rows=140)
        REGISTRY.call(
            "state_facts",
            {"facts": {"goal_text": "route support tickets",
                       "modality": "text", "target_score": 0.9}},
            actor=evidence.USER,
            thread_id=self.thread_id,
        )

    def propose(self) -> dict:
        proposed = REGISTRY.call(
            "propose_build",
            {"facts": {}, "eval_path": str(self.path)},
            actor=evidence.USER,
            thread_id=self.thread_id,
        )
        self.assertTrue(proposed["ok"], proposed)
        return proposed

    def test_proposing_the_same_plan_across_a_second_gives_one_fingerprint(self):
        """The defect, reproduced as a test rather than as an anecdote.

        The sleep is the whole point and it is why this test is worth its
        1.4 seconds: the original probe that pronounced the fingerprint stable
        proposed ten times in a tight loop, every one inside the same second -
        the one condition under which this bug cannot appear.
        """
        first = self.propose()
        time.sleep(1.4)
        second = self.propose()

        self.assertEqual(
            first["approve"],
            second["approve"],
            "the same plan proposed twice across a second boundary produced two "
            "different fingerprints, so approval cannot survive a human reading "
            "the plan before pressing approve",
        )

    def test_the_snapshot_still_records_the_data_it_is_a_snapshot_of(self):
        """Dropping the timestamp must not drop the evidence.

        The fix removes when somebody looked. It must keep what they saw, or a
        plan costed against a different file would stop being a different plan.
        """
        build = self.propose()["build"]
        snapshots = build["environment"]["data"]
        self.assertTrue(snapshots, "the build snapshotted no data at all")
        for snapshot in snapshots:
            self.assertNotIn(
                "read at",
                snapshot["how"],
                "the snapshot still carries the moment it was read, which is the "
                "defect: that clause moves on its own and it is what the "
                "fingerprint hashes",
            )
            self.assertTrue(snapshot["modified_at"], "no modification time")
            self.assertGreater(snapshot["bytes"], 0, "no size")

    def test_a_plan_costed_against_a_different_file_is_a_different_plan(self):
        """The other direction, because a hash that never changes is not a hash.

        This is the opposite failure and it matters exactly as much: if removing
        the timestamp had made the fingerprint blind to the data, approval would
        accept a plan for a file nobody approved.
        """
        first = self.propose()["approve"]
        self.path = self.an_eval_file(rows=77, name="other.jsonl")
        second = self.propose()["approve"]
        self.assertNotEqual(
            first,
            second,
            "two plans over two different files produced the same fingerprint, "
            "so the digest is no longer looking at the data",
        )


class ARecordedStepKeepsItsSubjectTest(unittest.TestCase):
    """`operates_on` survives the round trip, and a record that lies is refused."""

    def a_recorded_step(self, **overrides) -> dict:
        recorded = {
            "id": "count",
            "tool": "measure_eval_set",
            "why": "count the eval set",
            "arguments": {"path": "C:/data/eval.jsonl"},
            "produces": [],
            "needs": [],
            "cost": None,
            "exit_criterion": {"stated": "counted", "source": "tool_result",
                               "subject": "eval_size_n",
                               "comparator": "at_least", "value": 30},
            "risks": [],
            "contract": "",
            # Built from a real `Subject` rather than hand-written, so this
            # fixture cannot drift away from the type it is standing in for.
            "operates_on": Subject(
                kind="path",
                key="C:/data/eval.jsonl",
                how="the file this step opens",
                witness="120 bytes, 2026-08-19T00:00:00+00:00",
                modified_at="2026-08-19T00:00:00+00:00",
            ).as_dict(),
        }
        recorded.update(overrides)
        return recorded

    def test_a_recorded_plan_round_trips_its_operates_on(self):
        step = _a_step_again(self.a_recorded_step())
        self.assertIsInstance(step.operates_on, Subject)
        self.assertEqual(step.operates_on.key, "C:/data/eval.jsonl")

    def test_the_witness_is_carried_verbatim_and_not_re_read(self):
        """A rebuild that re-stats the file measures a different moment.

        `_an_environment_again` made exactly this call for `DataSnapshot` and
        this follows it: the witness recorded at proposal time is the one the
        approval is about. Re-reading here would quietly absorb the very change
        the freshness check exists to catch.
        """
        step = _a_step_again(self.a_recorded_step())
        self.assertEqual(
            step.operates_on.witness, "120 bytes, 2026-08-19T00:00:00+00:00"
        )
        self.assertEqual(step.operates_on.modified_at, "2026-08-19T00:00:00+00:00")

    def test_a_step_with_no_subject_round_trips_as_none(self):
        step = _a_step_again(self.a_recorded_step(operates_on=None))
        self.assertIsNone(step.operates_on)

    def test_a_recorded_key_the_rebuild_cannot_map_is_still_refused(self):
        """The guard that held `operates_on` out is still doing its job.

        This is the control for the change: teaching the storm one new key must
        not have taught it to accept any key. A field the validation never sees
        is a field nobody checked.
        """
        with self.assertRaises(Exception) as caught:
            _a_step_again(self.a_recorded_step(invented_key="whatever"))
        self.assertIn("invented_key", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
