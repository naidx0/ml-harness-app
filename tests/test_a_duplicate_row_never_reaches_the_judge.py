"""Planted case for the dedup gate, written before the gate.

    a triple already in the corpus is refused at generation, with zero calls
    and its own outcome column, so no count of tonight's kind is possible again

WHAT TONIGHT'S KIND WAS. Every count on this project counted duplicate rows as
separate rows: 164 kept rows were 127 distinct, 156 were 119, 95 were 60, and a
twenty-row run that reported adding 11 added 3. One triple appeared SEVEN times.
A model trained on that corpus would have seen one row seven times and called it
seven examples.

The generator draws from 49 source answers with one degradation instruction and
reproduces the same rewrite for the same source repeatedly. Nothing anywhere
deduplicated - not the generator, not the validator, not the judge, not the
report. **This gate is the thing that makes the count mean what it says.**

ITS OWN OUTCOME COLUMN, not folded into `validator`. A duplicate is not a bad
row: it is a row we already have, and a pipeline that reported it as a validator
fault would say the generator produced something wrong when it produced
something redundant. The report has to be able to say "12 duplicates" without
that reading as "12 defects".
"""

from __future__ import annotations

import unittest

import support

dedup = support.import_file(
    "a_row_we_already_have", support.REPO_ROOT / "scripts" / "a_row_we_already_have.py"
)

A_ROW = {
    "prompt": "Where is my order? I ordered on the 3rd.",
    "chosen": "Orders placed on the 3rd ship within two working days. If you "
              "give me your order number I can check the tracking for you.",
    "rejected": "Orders ship within two working days.",
}


def like(row, **changes):
    return {**row, **changes}


class ATripleAlreadyInTheCorpusIsRefusedTest(unittest.TestCase):
    """THE CASE. Zero calls: the check is three strings against a set."""

    def test_a_row_already_present_is_refused(self):
        seen = dedup.TheRowsWeAlreadyHave([A_ROW])
        said = dedup.why_this_row_is_one_we_already_have(A_ROW, seen)
        self.assertIsNotNone(said)
        self.assertIn("already", said)

    def test_a_row_not_present_is_admitted(self):
        """A gate that refused everything would pass the test above."""
        seen = dedup.TheRowsWeAlreadyHave([A_ROW])
        fresh = like(A_ROW, rejected="Orders ship. I can check the tracking.")
        self.assertIsNone(dedup.why_this_row_is_one_we_already_have(fresh, seen))

    def test_the_first_of_a_kind_is_admitted_and_then_remembered(self):
        """The corpus grows as the run goes, or a run would duplicate against
        itself - which is exactly how the 95 came to hold one row seven times."""
        seen = dedup.TheRowsWeAlreadyHave([])
        self.assertIsNone(dedup.why_this_row_is_one_we_already_have(A_ROW, seen))
        seen.remember(A_ROW)
        self.assertIsNotNone(dedup.why_this_row_is_one_we_already_have(A_ROW, seen))

    def test_all_three_parts_of_the_triple_matter(self):
        """A row differing in any one of prompt, chosen or rejected is a
        different training example."""
        seen = dedup.TheRowsWeAlreadyHave([A_ROW])
        for field in ("prompt", "chosen", "rejected"):
            with self.subTest(field=field):
                other = like(A_ROW, **{field: A_ROW[field] + " Extra."})
                self.assertIsNone(
                    dedup.why_this_row_is_one_we_already_have(other, seen),
                    f"a row differing in {field} was called a duplicate",
                )

    def test_whitespace_does_not_make_a_row_new(self):
        """Otherwise the gate is defeated by a trailing space, which is the
        difference between a check and a formality."""
        seen = dedup.TheRowsWeAlreadyHave([A_ROW])
        padded = like(A_ROW, rejected="  " + A_ROW["rejected"] + "  ")
        self.assertIsNotNone(dedup.why_this_row_is_one_we_already_have(padded, seen))

    def test_the_reason_names_what_it_matched(self):
        seen = dedup.TheRowsWeAlreadyHave([A_ROW])
        said = dedup.why_this_row_is_one_we_already_have(A_ROW, seen)
        self.assertIn(A_ROW["rejected"][:20], said)


class ItCostsNoCallsTest(unittest.TestCase):
    """Zero calls is the point: a duplicate must be refused BEFORE the judge,
    like the other three gates, not discovered after it has been paid for."""

    def test_the_check_is_pure_and_touches_no_runtime(self):
        source = (support.REPO_ROOT / "scripts" / "a_row_we_already_have.py").read_text(
            encoding="utf-8"
        )
        body = source.split('"""', 2)[-1]
        for forbidden in ("urllib", "requests", "http", "ask(", "adapter"):
            self.assertNotIn(forbidden, body, f"the dedup gate reaches for {forbidden}")

    def test_it_decides_from_three_strings(self):
        seen = dedup.TheRowsWeAlreadyHave([A_ROW])
        self.assertIsNotNone(
            dedup.why_this_row_is_one_we_already_have(dict(A_ROW), seen)
        )


class ItHasItsOwnOutcomeColumnTest(unittest.TestCase):
    """A duplicate is not a defect. The report must be able to say "12
    duplicates" without that reading as "12 bad rows"."""

    def test_the_stage_is_its_own(self):
        self.assertEqual(dedup.THE_STAGE, "duplicate")

    def test_it_is_not_the_validator(self):
        self.assertNotEqual(dedup.THE_STAGE, "validator")

    def test_the_reason_says_redundant_not_wrong(self):
        seen = dedup.TheRowsWeAlreadyHave([A_ROW])
        said = dedup.why_this_row_is_one_we_already_have(A_ROW, seen)
        self.assertNotIn("fault", said.lower())
        self.assertIn("not a defect", said.lower())


class TheCorpusItLoadsIsTheRealOneTest(unittest.TestCase):
    def test_it_reads_triples_from_rows(self):
        seen = dedup.TheRowsWeAlreadyHave(
            [A_ROW, like(A_ROW, rejected="Something else entirely.")]
        )
        self.assertEqual(len(seen), 2)

    def test_a_corpus_with_duplicates_collapses(self):
        """Loading tonight's corpus must give the DISTINCT count, which is the
        number this gate exists to protect."""
        seen = dedup.TheRowsWeAlreadyHave([A_ROW, dict(A_ROW), dict(A_ROW)])
        self.assertEqual(len(seen), 1)

    def test_rows_missing_a_field_do_not_crash_it(self):
        """A malformed row is not a duplicate and must not be treated as one."""
        seen = dedup.TheRowsWeAlreadyHave([{"prompt": "only"}])
        self.assertIsNone(dedup.why_this_row_is_one_we_already_have(A_ROW, seen))


if __name__ == "__main__":
    unittest.main()
