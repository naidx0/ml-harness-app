"""Train/eval leakage: the check the user cannot run for themselves.

Every fixture here is a real pair of files written to disk, and the leaky ones
are leaky on purpose. Two files that each look perfectly reasonable on their own
can share rows, and nothing about either one in isolation reveals it - which is
the whole reason this check exists and the reason a WARN would not be enough.

What is asserted, over and over, in different shapes:

1. Overlap is a **BLOCK**, and the message says the eval numbers are invalid
   rather than merely suspect. A leaked row does not degrade a measurement, it
   removes its meaning, and gate G1 wants a *measured baseline*.
2. **Near-identical counts.** A paraphrase leaks exactly as thoroughly as a
   copy, and a split produced by a script that shuffled after deduplicating is
   the normal way it happens.
3. **A check that did not run is not a pass.** An unreadable eval file produces
   "this was not checked", never "no leakage found".
4. **Clean is scoped.** "No overlap" is worded as covering the two files given,
   because a benchmark the harness has never seen cannot be checked at all.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app import dataquality


ORIGINAL = (
    "How do I reset my password on the customer portal? Click the forgot "
    "password link on the login screen and follow the emailed instructions."
)
PARAPHRASE = ORIGINAL.replace("login screen", "sign-in screen")
UNRELATED = (
    "What is the refund window for an order placed with express delivery in "
    "the winter sale?"
)


class LeakageTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)

    def tearDown(self):
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def csv(self, name: str, header: str, rows: list[str]) -> Path:
        path = self.dir / name
        path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
        return path

    def jsonl(self, name: str, records: list[dict]) -> Path:
        path = self.dir / name
        path.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n",
            encoding="utf-8",
        )
        return path


class ALeakySplitTest(LeakageTestCase):
    def build(self):
        """Forty train rows, ten eval rows, four of which are train rows."""
        train_rows = [f"train question number {i} about billing,billing" for i in range(40)]
        eval_rows = [f"eval question number {i} about billing,billing" for i in range(6)]
        eval_rows += train_rows[:4]
        train = self.csv("train.csv", "text,label", train_rows)
        evaluation = self.csv("eval.csv", "text,label", eval_rows)
        return train, evaluation

    def test_the_overlapping_rows_are_counted(self):
        train, evaluation = self.build()

        leakage = dataquality.find_leakage(train, evaluation)

        self.assertTrue(leakage["ran"])
        self.assertEqual(leakage["train_rows"], 40)
        self.assertEqual(leakage["eval_rows"], 10)
        self.assertEqual(leakage["leaked_rows"], 4)
        self.assertEqual(leakage["exact_matches"], 4)
        self.assertEqual(leakage["leak_rate"], 0.4)

    def test_it_is_a_block_and_says_the_numbers_are_invalid(self):
        train, evaluation = self.build()

        finding = dataquality.leakage_finding(dataquality.find_leakage(train, evaluation))

        self.assertEqual(finding.level, dataquality.BLOCK)
        self.assertEqual(finding.code, "split_leakage")
        self.assertIn("invalid", finding.message)
        self.assertIn("baseline", finding.message)

    def test_the_offending_rows_are_named_so_the_user_can_go_and_look(self):
        train, evaluation = self.build()

        leakage = dataquality.find_leakage(train, evaluation)

        self.assertTrue(leakage["examples"])
        example = leakage["examples"][0]
        for key in (
            "eval_row", "train_row", "eval_excerpt", "train_excerpt",
            "similarity", "similarity_basis", "similarity_provenance",
        ):
            self.assertIn(key, example)
        self.assertIn("train question number", example["train_excerpt"])
        self.assertEqual(example["similarity_provenance"], dataquality.MEASURED)

    def test_every_number_in_the_result_carries_provenance(self):
        train, evaluation = self.build()

        leakage = dataquality.find_leakage(train, evaluation)

        for key, value in leakage["provenance"].items():
            with self.subTest(field=key):
                self.assertIn(value, dataquality.PROVENANCE)

    def test_the_plain_language_summary_says_it_in_the_brief_s_own_words(self):
        train, evaluation = self.build()

        leakage = dataquality.find_leakage(train, evaluation)
        profile = dataquality.profile(train, split="train")
        text = dataquality.describe(
            profile, dataquality.quality_report(profile, leakage), leakage
        )

        self.assertIn("appear in both your train and eval splits", text)


class NearDuplicateLeakageTest(LeakageTestCase):
    """A paraphrase leaks as thoroughly as a copy, and is far harder to see."""

    def test_a_reworded_row_is_caught(self):
        train = self.csv(
            "train.csv", "text", [f'"{ORIGINAL}"'] + [f'"{UNRELATED} {i}"' for i in range(20)]
        )
        evaluation = self.csv("eval.csv", "text", [f'"{PARAPHRASE}"'])

        leakage = dataquality.find_leakage(train, evaluation)

        self.assertEqual(leakage["leaked_rows"], 1)
        self.assertEqual(leakage["exact_matches"], 0)
        self.assertEqual(leakage["near_matches"], 1)
        self.assertGreaterEqual(
            leakage["examples"][0]["similarity"], dataquality.JACCARD_THRESHOLD
        )

    def test_an_unrelated_eval_row_is_not_reported_as_a_leak(self):
        train = self.csv("train.csv", "text", [f'"{ORIGINAL}"'])
        evaluation = self.csv("eval.csv", "text", [f'"{UNRELATED}"'])

        self.assertEqual(dataquality.find_leakage(train, evaluation)["leaked_rows"], 0)

    def test_only_whitespace_and_case_differ_still_counts_as_exact(self):
        train = self.csv("train.csv", "text", [f'"{ORIGINAL}"'])
        evaluation = self.csv(
            "eval.csv", "text", [f'"  {ORIGINAL.upper()}   "']
        )

        leakage = dataquality.find_leakage(train, evaluation)

        self.assertEqual(leakage["leaked_rows"], 1)
        self.assertEqual(leakage["exact_matches"], 1)

    def test_a_row_renamed_into_a_different_column_is_still_the_same_row(self):
        """Column names are dropped before comparing, on purpose.

        A user who exported their eval set from a different tool has the same
        rows under different headers. If the check keyed on column names it
        would report a clean split, which is the worst possible answer.
        """
        train = self.jsonl(
            "train.jsonl",
            [{"question": ORIGINAL, "answer": "Use the reset link."}]
            + [{"question": f"{UNRELATED} {i}", "answer": "Fourteen days."} for i in range(10)],
        )
        evaluation = self.jsonl(
            "eval.jsonl", [{"prompt": ORIGINAL, "completion": "Use the reset link."}]
        )

        leakage = dataquality.find_leakage(train, evaluation)

        self.assertEqual(leakage["leaked_rows"], 1)
        self.assertEqual(leakage["exact_matches"], 1)


class ACleanSplitTest(LeakageTestCase):
    def test_no_overlap_is_reported_as_information_and_scoped_to_these_two_files(self):
        train = self.csv("train.csv", "text", [f"train row {i}" for i in range(50)])
        evaluation = self.csv("eval.csv", "text", [f"eval row {i}" for i in range(20)])

        leakage = dataquality.find_leakage(train, evaluation)
        finding = dataquality.leakage_finding(leakage)

        self.assertEqual(leakage["leaked_rows"], 0)
        self.assertEqual(finding.level, dataquality.INFO)
        self.assertIn("two files given", finding.remediation)
        self.assertIn("has never seen", finding.remediation)

    def test_a_clean_result_never_claims_more_than_it_measured(self):
        train = self.csv("train.csv", "text", ["a", "b"])
        evaluation = self.csv("eval.csv", "text", ["c", "d"])

        finding = dataquality.leakage_finding(
            dataquality.find_leakage(train, evaluation)
        )

        self.assertNotIn("guarantee", finding.message.lower())
        self.assertNotIn("no leakage exists", finding.message.lower())


class ACheckThatDidNotRunIsNotAPassTest(LeakageTestCase):
    def test_an_unreadable_eval_file_produces_not_checked_rather_than_clean(self):
        train = self.csv("train.csv", "text", ["a", "b"])
        evaluation = self.dir / "eval.parquet"
        evaluation.write_bytes(b"PAR1" + b"\x00" * 64)

        leakage = dataquality.find_leakage(train, evaluation)
        finding = dataquality.leakage_finding(leakage)

        self.assertFalse(leakage["ran"])
        self.assertTrue(leakage["checks_not_run"])
        self.assertEqual(finding.code, "split_leakage_not_checked")
        self.assertIn("nothing here says", finding.message)
        self.assertNotEqual(finding.level, dataquality.INFO)

    def test_a_missing_train_file_says_which_side_was_missing(self):
        evaluation = self.csv("eval.csv", "text", ["a"])

        leakage = dataquality.find_leakage(self.dir / "nope.csv", evaluation)

        self.assertFalse(leakage["ran"])
        self.assertIn("train", leakage["checks_not_run"][0]["why"])

    def test_zero_leaked_rows_and_a_check_that_did_not_run_are_different_states(self):
        clean_train = self.csv("t.csv", "text", ["a"])
        clean_eval = self.csv("e.csv", "text", ["b"])
        broken = self.dir / "broken.parquet"
        broken.write_bytes(b"PAR1")

        clean = dataquality.find_leakage(clean_train, clean_eval)
        unknown = dataquality.find_leakage(clean_train, broken)

        self.assertEqual((clean["ran"], clean["leaked_rows"]), (True, 0))
        self.assertEqual((unknown["ran"], unknown["leaked_rows"]), (False, 0))
        self.assertNotEqual(
            dataquality.leakage_finding(clean).code,
            dataquality.leakage_finding(unknown).code,
        )


class TheThresholdIsOursTest(LeakageTestCase):
    def test_the_threshold_is_reported_and_labelled_as_policy(self):
        train = self.csv("train.csv", "text", ["a"])
        evaluation = self.csv("eval.csv", "text", ["b"])

        leakage = dataquality.find_leakage(train, evaluation)

        self.assertEqual(leakage["threshold"], dataquality.JACCARD_THRESHOLD)
        self.assertIn("policy", leakage["threshold_is"])
        self.assertIn("shingles", leakage["method"])


if __name__ == "__main__":
    unittest.main()
