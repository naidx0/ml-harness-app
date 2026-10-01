"""Nothing trains on generated rows until a person has read a tenth of them.

`docs/diagnosis_engine.yaml` writes the rule into the recipe of
`BLOCKED__COLLECT_OR_SYNTHESIZE_DATA`, at all three sites that state it:

    "Synthesize from the real input distribution with a teacher model, then
     have a human verify a 10% sample before training on any of it."

Until 2026-08-27 that was a sentence in a data file and nothing in the product
enforced it. `docs/PHASES.md` Phase 2 lists it as owed, and the queue's step 5
says what "as a real step" means: something has to refuse.

**The gate wall and this one are different walls, and both are needed.**
`tests/test_a_generated_row_cannot_open_a_gate.py` stops a generated row
becoming a MEASUREMENT. This stops it becoming WEIGHTS. A file that never opens
a gate can still be handed to `start_training`, and the model that comes out is
the thing that ships.

**What this deliberately does not do is judge.** Nothing in this harness can
tell whether a generated answer is right - that is the entire reason a person is
in the loop - so `draw_verification_sample` chooses rows and writes them out,
and `record_verification` counts what came back. Neither one has an opinion.
"""

import json
import pathlib
import tempfile
import unittest

from app import diagnosis
from app.tools import datawork
from app.tools.registry import REGISTRY
import support


def _write(path, rows):
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return path


def _real(n):
    return [{"input": f"q{i}", "expected": "yes" if i % 2 else "no"} for i in range(n)]


class TheSampleIsDrawnAndNotJudgedTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.ledger = diagnosis.default_spec()

    def _amplify(self, rows=12, count=200, seed="phase-2"):
        source = _write(self.tmp / "source.jsonl", _real(rows))
        written = datawork.synthesize_rows(
            path=str(source),
            answer_column="expected",
            into=str(self.tmp / f"amplified-{seed}"),
            count=count,
            seed=seed,
            ledger=self.ledger,
        )
        self.assertTrue(written["ok"], written)
        return pathlib.Path(written["synthetic_path"])

    def test_it_draws_a_tenth_and_says_so(self):
        generated = self._amplify(count=200)
        drawn = datawork.draw_verification_sample(
            path=str(generated),
            into=str(self.tmp / "review"),
            seed="s",
            ledger=self.ledger,
        )
        self.assertTrue(drawn["ok"], drawn)
        self.assertEqual(20, drawn["rows_written"])
        self.assertEqual(200, drawn["rows_total"])
        rows = [
            json.loads(line)
            for line in pathlib.Path(drawn["sample_path"]).read_text().splitlines()
        ]
        self.assertEqual(20, len(rows))
        for row in rows:
            self.assertEqual("", row[datawork.VERDICT_FIELD])
            self.assertIn("source_row_index", row)

    def test_the_floor_bites_on_a_small_file(self):
        """Ten percent of twenty rows is two, and two says nothing. The floor is
        written down rather than left to arithmetic."""
        generated = self._amplify(count=20)
        drawn = datawork.draw_verification_sample(
            path=str(generated),
            into=str(self.tmp / "review-small"),
            ledger=self.ledger,
        )
        self.assertEqual(datawork.VERIFICATION_FLOOR, drawn["rows_written"])

    def test_the_same_seed_draws_the_same_rows(self):
        generated = self._amplify(count=100)
        first = datawork.draw_verification_sample(
            path=str(generated), into=str(self.tmp / "a"), seed="k", ledger=self.ledger
        )
        second = datawork.draw_verification_sample(
            path=str(generated), into=str(self.tmp / "b"), seed="k", ledger=self.ledger
        )

        def indexes(result):
            return [
                json.loads(line)["source_row_index"]
                for line in pathlib.Path(result["sample_path"]).read_text().splitlines()
            ]

        self.assertEqual(indexes(first), indexes(second))

    def test_it_refuses_a_file_with_nothing_generated_in_it(self):
        """This step is about rows this harness wrote. Drawing a 'verification
        sample' of somebody's real data would be asking them to check their own
        answers against nothing."""
        real = _write(self.tmp / "real.jsonl", _real(50))
        drawn = datawork.draw_verification_sample(
            path=str(real), into=str(self.tmp / "no"), ledger=self.ledger
        )
        self.assertFalse(drawn["ok"])
        self.assertEqual("nothing_generated", drawn["error"])


class WhatCameBackIsRecordedTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.ledger = diagnosis.default_spec()
        source = _write(self.tmp / "source.jsonl", _real(12))
        written = datawork.synthesize_rows(
            path=str(source),
            answer_column="expected",
            into=str(self.tmp / "amplified"),
            count=60,
            seed="s",
            ledger=self.ledger,
        )
        self.generated = pathlib.Path(written["synthetic_path"])
        self.drawn = datawork.draw_verification_sample(
            path=str(self.generated),
            into=str(self.tmp / "review"),
            seed="s",
            ledger=self.ledger,
        )
        self.sample = pathlib.Path(self.drawn["sample_path"])

    def _mark(self, verdicts):
        rows = [json.loads(line) for line in self.sample.read_text().splitlines()]
        for row, verdict in zip(rows, verdicts):
            row[datawork.VERDICT_FIELD] = verdict
        _write(self.sample, rows)
        return rows

    def test_a_fully_marked_sample_is_recorded_beside_the_data(self):
        rows = self._mark(["yes"] * 6)
        recorded = datawork.record_verification(
            sample_path=str(self.sample), ledger=self.ledger
        )
        self.assertTrue(recorded["ok"], recorded)
        self.assertEqual(len(rows), recorded["judged"])
        self.assertEqual(0, recorded["wrong"])
        beside = datawork.verification_path(self.generated)
        self.assertTrue(beside.is_file())
        record = json.loads(beside.read_text())
        self.assertEqual(str(self.generated), record["dataset"])

    def test_a_half_marked_sample_is_refused_rather_than_counted(self):
        """Reading a blank as wrong fails somebody for stopping halfway; reading
        it as right lets an unread file through. Both are this product deciding
        something only the person can."""
        self._mark(["yes", "", "yes", "", "yes", ""])
        recorded = datawork.record_verification(
            sample_path=str(self.sample), ledger=self.ledger
        )
        self.assertFalse(recorded["ok"])
        self.assertEqual("not_finished", recorded["error"])
        self.assertFalse(datawork.verification_path(self.generated).exists())

    def test_the_spellings_a_person_actually_writes_are_read(self):
        for right, wrong in (("yes", "no"), ("y", "n"), ("true", "false"), ("1", "0")):
            with self.subTest(right=right):
                self.assertIs(True, datawork.read_verdict(right))
                self.assertIs(False, datawork.read_verdict(wrong))
        self.assertIsNone(datawork.read_verdict(""))
        self.assertIsNone(datawork.read_verdict(None))
        self.assertIsNone(datawork.read_verdict("maybe"))

    def test_it_refuses_a_file_that_is_not_a_drawn_sample(self):
        loose = _write(self.tmp / "loose.jsonl", [{"verified": "yes"}])
        recorded = datawork.record_verification(
            sample_path=str(loose), ledger=self.ledger
        )
        self.assertFalse(recorded["ok"])
        self.assertEqual("no_manifest", recorded["error"])


class NothingTrainsOnUnreadRowsTest(unittest.TestCase):
    """The refusal that makes the whole step real, at the door that matters."""

    def setUp(self):
        support.sandbox(self)
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.ledger = diagnosis.default_spec()
        source = _write(self.tmp / "source.jsonl", _real(12))
        written = datawork.synthesize_rows(
            path=str(source),
            answer_column="expected",
            into=str(self.tmp / "amplified"),
            count=60,
            seed="s",
            ledger=self.ledger,
        )
        self.generated = pathlib.Path(written["synthetic_path"])

    def _verify(self, verdicts=None):
        drawn = datawork.draw_verification_sample(
            path=str(self.generated),
            into=str(self.tmp / f"review-{len(list(self.tmp.iterdir()))}"),
            seed="s",
            ledger=self.ledger,
        )
        sample = pathlib.Path(drawn["sample_path"])
        rows = [json.loads(line) for line in sample.read_text().splitlines()]
        marks = verdicts or ["yes"] * len(rows)
        for row, verdict in zip(rows, marks):
            row[datawork.VERDICT_FIELD] = verdict
        _write(sample, rows)
        return datawork.record_verification(sample_path=str(sample), ledger=self.ledger)

    def test_an_unread_generated_file_is_refused(self):
        verdict = datawork.may_be_trained_on(self.generated)
        self.assertFalse(verdict["ok"])
        self.assertEqual("not_verified", verdict["error"])
        self.assertIn("10% sample", verdict["why"])

    def test_a_real_file_needs_no_verification_at_all(self):
        """The negative beside the positive. This wall must not have made
        training on somebody's own data harder."""
        real = pathlib.Path(_write(self.tmp / "real.jsonl", _real(50)))
        self.assertTrue(datawork.may_be_trained_on(real)["ok"])

    def test_a_read_file_with_no_wrong_rows_may_be_trained_on(self):
        self.assertTrue(self._verify()["ok"])
        verdict = datawork.may_be_trained_on(self.generated)
        self.assertTrue(verdict["ok"], verdict)
        self.assertEqual(0, verdict["verified"]["wrong"])

    def test_a_sample_that_found_errors_stops_the_run(self):
        """Amplification copies answers verbatim, so a wrong generated row is a
        wrong source row - and the rest of the file came from the same source."""
        recorded = self._verify(["yes", "no", "yes", "yes", "yes", "yes"])
        self.assertTrue(recorded["ok"], recorded)
        self.assertEqual(1, recorded["wrong"])
        verdict = datawork.may_be_trained_on(self.generated)
        self.assertFalse(verdict["ok"])
        self.assertEqual("sample_found_errors", verdict["error"])

    def test_rewriting_the_data_after_verifying_it_invalidates_the_record(self):
        """The record is bound to the bytes somebody read. Re-generating with a
        different seed and keeping the filename is the obvious way to end up
        training on rows nobody has seen."""
        self.assertTrue(self._verify()["ok"])
        self.assertTrue(datawork.may_be_trained_on(self.generated)["ok"])

        rows = [json.loads(line) for line in self.generated.read_text().splitlines()]
        rows.append({**rows[0], "expected": "something else"})
        _write(self.generated, rows)

        verdict = datawork.may_be_trained_on(self.generated)
        self.assertFalse(verdict["ok"])
        self.assertEqual("verification_is_about_other_bytes", verdict["error"])

    def test_start_training_refuses_and_queues_nothing(self):
        answer = REGISTRY.call(
            "start_training",
            {
                "recipe": "hf-peft-lora",
                "base_model": "Qwen/Qwen3-0.6B",
                "dataset_path": str(self.generated),
            },
            actor="user",
            approved=True,
        )
        self.assertFalse(answer["ok"], answer)
        self.assertEqual("not_verified", answer["error"])
        self.assertIn("Nothing was queued", answer["help"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
