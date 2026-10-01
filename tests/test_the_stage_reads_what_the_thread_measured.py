"""The Stage is a reader. One GET, everything its panels draw, nothing written.

`docs/PHASES.md`, "The Stage", S1: the surface that shows a thread's runs side
by side must not file rows into the thread it is reading. So its data comes
through `GET /api/threads/{id}/stage` and `app/stage.py::build`, off the same
tables and functions the tools wrote through, and this file holds it to three
things: the rows are the rows, the paired verdict is `evals.compare`'s and not a
second implementation, and a read leaves the transcript exactly as long as it
found it.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from app import stage
from app.main import app
from app.tools import evals, sandbox
import support


class TheStageReadsTheThreadTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = int(support.conversations(1)[0]["id"])
        self.eval_path = self.root / "eval.jsonl"
        self.eval_path.write_text("", encoding="utf-8")
        #: twenty rows, every other one wrong: the baseline
        self.baseline = support.a_completed_eval_run(self.thread, self.eval_path, rows=20)
        #: a second complete run over the same rows, to be paired
        self.second = support.a_completed_eval_run(self.thread, self.eval_path, rows=20)

    def test_every_run_carries_its_rows_and_the_oldest_default_run_is_the_baseline(self):
        payload = stage.build(self.thread)
        self.assertEqual([r["run_id"] for r in payload["runs"]],
                         sorted(r["run_id"] for r in payload["runs"]), "oldest first")
        for run in payload["runs"]:
            self.assertEqual(len(run["rows"]), 20)
            self.assertEqual(sum(1 for r in run["rows"] if r["correct"]), run["correct"])
            self.assertEqual({"row_index", "correct", "failure_mode", "bucketed_by"},
                             set(run["rows"][0]))
        self.assertEqual(payload["baseline_run_id"], int(self.baseline["id"]))

    def test_the_paired_verdict_is_compare_s_and_not_a_second_opinion(self):
        payload = stage.build(self.thread)
        paired = payload["comparisons"][str(int(self.second["id"]))]
        theirs = evals.compare(int(self.second["id"]), int(self.baseline["id"]))
        for key in ("improved", "regressed", "p_value", "verdict", "paired_rows"):
            self.assertEqual(paired[key], theirs[key], key)
        self.assertNotIn(str(int(self.baseline["id"])), payload["comparisons"],
                         "the baseline is not paired against itself")

    def test_the_card_and_the_guard_are_read_and_may_be_absent(self):
        payload = stage.build(self.thread)
        # support.sandbox binds the card to "none"; the payload says so rather
        # than inventing a free card.
        self.assertIsNone(payload["gpu"]["occupancy"])
        self.assertIsNone(payload["gpu"]["guard"])
        crowded = {"used_gb": 4.9, "total_gb": 8.0,
                   "resident": [{"name": "granite4-hermes:latest", "size_gb": 4.9}]}
        with mock.patch.object(sandbox, "_gpu_occupancy", lambda: crowded):
            payload = stage.build(self.thread)
        self.assertEqual(payload["gpu"]["occupancy"]["used_gb"], 4.9)
        self.assertIn("granite4-hermes:latest", payload["gpu"]["guard"])

    def test_the_diagnosis_is_the_journey_report(self):
        payload = stage.build(self.thread)
        self.assertIsNotNone(payload["diagnosis"])
        self.assertIn("verdict", payload["diagnosis"])
        self.assertIn("gates", payload["diagnosis"]["verdict"])

    def test_a_missing_thread_is_a_key_error_and_a_404(self):
        with self.assertRaises(KeyError):
            stage.build(999_999)
        client = support.api_client(app)
        self.assertEqual(client.get("/api/threads/999999/stage").status_code, 404)

    def test_the_route_reads_without_writing_a_row(self):
        client = support.api_client(app)
        before = client.get(f"/api/threads/{self.thread}").json()["messages"]
        answered = client.get(f"/api/threads/{self.thread}/stage")
        self.assertEqual(answered.status_code, 200, answered.text)
        body = answered.json()
        self.assertEqual(body["thread_id"], self.thread)
        self.assertEqual(len(body["runs"]), 2)
        after = client.get(f"/api/threads/{self.thread}").json()["messages"]
        self.assertEqual(len(before), len(after), "the Stage filed a row while reading")
        # and it is JSON all the way down - nothing here that a browser cannot parse
        json.dumps(body)


class AnEmptyThreadIsEmptyAndNotZeroTest(unittest.TestCase):
    """A thread that has measured nothing yet.

    THE FAILURE THIS FORBIDS IS A PLACEHOLDER. `docs/DESIGN_DIRECTIVES.md` and
    every provenance wall in this product say the same thing in different
    words: a figure nobody measured is not a zero, it is an absence, and the
    interface must be able to tell them apart. A Stage that answered a fresh
    thread with `runs: [{score: 0}]`, or a comparison whose delta was 0.0
    because there was nothing to compare, would be inventing the most
    dangerous kind of number - one that looks measured.

    So the empty payload is exactly empty containers, `diagnosis: None`, and
    the `reads` block still fully present, because WHERE a number would have
    come from is true whether or not there is a number. The words a person
    sees on that screen are the frontend's own (`Stage.tsx:159`), which is
    where they belong; the engine ships no sentence here.
    """

    def setUp(self):
        support.sandbox(self)
        self.thread = int(support.conversations(1)[0]["id"])

    def test_nothing_measured_is_empty_containers_and_no_figure(self):
        payload = stage.build(self.thread)

        self.assertEqual(payload["runs"], [])
        self.assertEqual(payload["comparisons"], {})
        self.assertEqual(payload["sandboxes"], [])
        self.assertIsNone(payload["baseline_run_id"])

    def test_an_empty_diagnosis_is_a_skeleton_and_never_a_verdict(self):
        """MEASURED 2026-09-02, and not what was predicted.

        `diagnosis` is None only for a thread that does not exist, where
        `journey_report.build` raises KeyError (see
        `test_a_missing_thread_is_a_key_error_and_a_404`). For a thread that
        exists and has measured nothing, the report builds and comes back a
        SKELETON - and that is the more useful answer, because a reader can
        tell "this thread has a ledger and has answered nothing of it" from
        "there is no such thread".

        What makes the skeleton safe is that every field in it is an absence:
        no outcome, no sentence, no gate rows, no facts. This locks that. A
        skeleton that grew a `0` or a default verdict would be the invented
        number this product exists to refuse, and it would arrive on the
        emptiest screen a person can open - the worst place for it.
        """
        report = stage.build(self.thread)["diagnosis"]
        self.assertIsNotNone(report, "an existing thread's report should build")

        self.assertIsNone(report["verdict"]["outcome"])
        self.assertIsNone(report["verdict"]["say"])
        self.assertEqual(report["verdict"]["gates"], {})
        self.assertEqual(report["verdict"]["fact_origins"], {})
        self.assertEqual(report["facts"], [])
        self.assertEqual(report["storms"], [])
        # The ledger it WOULD diagnose against is named: that is provenance,
        # not a measurement, and it is true before anything is measured.
        self.assertTrue(str(report["ledger"]).endswith(".yaml"))

    def test_the_reads_block_survives_having_nothing_to_read(self):
        """Provenance is not conditional on there being a figure."""
        payload = stage.build(self.thread)
        self.assertEqual(
            sorted(payload["reads"]),
            ["comparisons", "diagnosis", "gpu", "runs", "sandboxes"],
            "the Stage dropped a provenance entry when the thread was empty",
        )
        for key, source in payload["reads"].items():
            self.assertTrue(
                str(source).strip(),
                f"reads[{key!r}] is empty - it must name what would be read",
            )

    def test_the_engine_ships_no_empty_state_sentence(self):
        """The words belong to the frontend; the engine sends data only.

        Checked as a property of the payload rather than by grepping the
        module: every string in it is a key, an identifier or a provenance
        note, and none of them is a sentence addressed to a person.
        """
        payload = stage.build(self.thread)
        flat = json.dumps(payload).lower()
        for sentence in ("nothing measured", "no runs yet", "get started", "n/a"):
            self.assertNotIn(
                sentence, flat,
                f"the engine put the words {sentence!r} in the Stage payload",
            )


if __name__ == "__main__":
    unittest.main()
