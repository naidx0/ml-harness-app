"""The person's bucket reaches every reader, and the rule's is still there under it.

## What was unlocked, and what a neighbouring lane wanted to do about it

`eval_rebuckets` holds run 51's failures as 13 `wrong_format`, 5 `wrong_facts`
and 2 `wrong_reasoning`. `eval_results.failure_mode` for those same rows reads
`unclassified`. Read as raw SQL that looks like a write that never happened, and
it was routed here on 2026-09-09 as one: *the rebucketer's output was never
written back to the column whose name promises it*, with a corpus figure - 2,524
wrong rows, 366 carrying a named bucket - measured the same way.

**The corpus figure is not about rebuckets at all.** Measured here the same
afternoon: of those 2,524 wrong rows, 366 are named BY THE RULE in the raw
column, and **20 rows across exactly one run carry a rebucket**. The rule leaves
2,158 of them `unclassified`. So the 14.5% is a statement about the grader's
classification rate; honouring the overlay everywhere moves the corpus to 15.3%.
A reader deciding what to fix from that percentage would work on the wrong
thing, which is the second reason this file leads with where the number comes
from.

**The reader disagrees with the SQL.** `evals.results_for(51)` returns
`wrong_format` 13, `wrong_facts` 5, `wrong_reasoning` 2 and `unclassified` 27,
with `rule_failure_mode` reading `unclassified` on exactly the 20 that moved.
The classification is where readers read it. What the raw column shows is
migration 14 working as written:

    A person's reading of a failing row is kept, beside the rule's, not over it.

So the corpus statistic counts the rule's column and skips every overlay, and the
proposed repair - write the buckets into `eval_results.failure_mode` - is red by
a test that already exists: `test_the_eval_bench_keeps_its_rows` asserts the
string `UPDATE eval_` never appears in `app/tools/evals.py`.

## Why this file exists anyway

**Nothing asserted `rule_failure_mode` anywhere in `tests/`.** The overlay is the
only thing standing between a rebucketed run and 47 rows reading `unclassified`
to every consumer - `choose_exemplars`, `read_eval_results`, the failure pane -
and it was held up by one dict comprehension no test looked at. A regression
there is silent: the rows are all still present, all still wrong, and the
person's reading is simply gone.

The test that was requested - *a rebucket present and the column unclassified*
made impossible - would have locked the opposite of the design, and gone red the
first time anybody re-read a row. What is locked here is the invariant that is
actually true, including the raw column staying put, so the next reader of that
`unclassified` finds an assertion saying it is deliberate.
"""

from __future__ import annotations

import unittest

from app import db
from app.tools import REGISTRY, evals

import support


class ThePersonsReadingReachesTheReaderTest(unittest.TestCase):
    """One run, one re-reading, and every claim taken through `results_for`."""

    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = int(support.conversations(1)[0]["id"])
        self.eval_path = self.root / "eval.jsonl"
        self.eval_path.write_text("", encoding="utf-8")
        self.run = support.a_completed_eval_run(
            self.thread, self.eval_path, rows=20
        )
        #: DISCOVERED, NOT ASSUMED. Which row indices the fixture grades wrong is
        #: the fixture's business, and a test that hard-codes them fails for a
        #: reason that has nothing to do with the overlay.
        self.wrong = [
            int(row["row_index"])
            for row in evals.results_for(int(self.run["id"]))
            if not row["correct"]
        ]
        self.assertGreaterEqual(
            len(self.wrong), 2, "the fixture graded too few rows wrong to re-read"
        )
        #: A BUCKET THE RULE DID NOT ALREADY PICK, and the first draft of this
        #: file did not do it. The fixture grades its wrong rows `wrong_facts`,
        #: so re-reading a row AS `wrong_facts` changes nothing - and
        #: `test_the_persons_bucket_is_what_a_reader_gets` passed while asserting
        #: a value the overlay had no part in producing. Deleting the overlay
        #: entirely left it green. A test that cannot fail is not a test, so the
        #: bucket is now chosen to differ from whatever the rule said.
        self.rule_bucket = self.rows_by_index()[self.wrong[0]]["failure_mode"]
        self.reading = (
            "wrong_reasoning" if self.rule_bucket != "wrong_reasoning" else "wrong_format"
        )
        self.assertNotEqual(self.reading, self.rule_bucket)

    def rebucket(self, buckets):
        out = REGISTRY.call(
            "rebucket_failures",
            {"run_id": int(self.run["id"]), "buckets": buckets},
            actor="user",
            thread_id=self.thread,
        )
        self.assertTrue(out.get("ok"), out)
        return out

    def rows_by_index(self):
        return {
            int(row["row_index"]): row
            for row in evals.results_for(int(self.run["id"]))
        }

    def raw_failure_mode(self, row_index):
        """The column itself, with no overlay - what the neighbouring lane read."""
        with db.session() as connection:
            got = connection.execute(
                "SELECT failure_mode FROM eval_results "
                "WHERE run_id = ? AND row_index = ?",
                (int(self.run["id"]), int(row_index)),
            ).fetchone()
        return None if got is None else got["failure_mode"]

    def test_the_persons_bucket_is_what_a_reader_gets(self):
        """THE CASE. Without the overlay this row reads the rule's bucket."""
        target = self.wrong[0]
        self.rebucket({str(target): self.reading})
        self.assertEqual(self.rows_by_index()[target]["failure_mode"], self.reading)

    def test_the_rules_bucket_survives_underneath(self):
        """THE HALF NOTHING ASSERTED. `rule_failure_mode` is the provenance
        question - what the rule said and what the person said, both answerable
        after the correction."""
        target = self.wrong[0]
        before = self.rows_by_index()[target]["failure_mode"]
        self.rebucket({str(target): self.reading})
        after = self.rows_by_index()[target]
        self.assertEqual(after["rule_failure_mode"], before)
        self.assertNotEqual(after["failure_mode"], after["rule_failure_mode"])

    def test_the_stored_row_is_not_rewritten(self):
        """WHY THE WRITE-BACK WAS REFUSED, as an assertion rather than a note.
        `eval_results` is append-only; the correction lives in its own table."""
        target = self.wrong[0]
        before = self.raw_failure_mode(target)
        self.rebucket({str(target): self.reading})
        self.assertEqual(self.raw_failure_mode(target), before)

    def test_a_row_nobody_read_is_untouched(self):
        """The overlay lands on the row it was written for and no other."""
        read, unread = self.wrong[0], self.wrong[1]
        before = self.rows_by_index()[unread]["failure_mode"]
        self.rebucket({str(read): self.reading})
        after = self.rows_by_index()[unread]
        self.assertEqual(after["failure_mode"], before)
        self.assertNotIn("rule_failure_mode", after)

    def test_a_second_reading_of_one_row_wins(self):
        """Migration 14 keeps both readings and lets the latest win. Two rows in
        `eval_rebuckets`, one answer out."""
        target = self.wrong[0]
        second = "wrong_style" if self.reading != "wrong_style" else "wrong_format"
        self.rebucket({str(target): self.reading})
        self.rebucket({str(target): second})
        self.assertEqual(self.rows_by_index()[target]["failure_mode"], second)
        with db.session() as connection:
            kept = connection.execute(
                "SELECT COUNT(*) AS n FROM eval_rebuckets "
                "WHERE run_id = ? AND row_index = ?",
                (int(self.run["id"]), int(target)),
            ).fetchone()["n"]
        self.assertEqual(kept, 2, "a re-reading replaced the earlier one")

    def test_the_reader_says_whose_judgement_it_is(self):
        """A bucket that changed hands without saying so is the same defect one
        layer down."""
        target = self.wrong[0]
        self.rebucket({str(target): self.reading})
        self.assertEqual(
            self.rows_by_index()[target]["bucketed_by"],
            "the person who read the row",
        )


if __name__ == "__main__":
    unittest.main()
