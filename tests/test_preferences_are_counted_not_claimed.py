"""The one number standing between a person and DPO can now be taken.

## The gap, in the product's own words

`evidence.resolves("preference_pairs_n")` answered, in the sentence the frontier
puts in front of a person:

    No tool in this harness measures this yet. 'preference_pairs_n' IS a
    declared fact of docs/diagnosis_engine.yaml - the ledger this conversation
    is running - and no registered instrument produces it, so that is a gap in
    the product rather than something you can answer.

One node reads that fact - `S5_PREFERENCES_NOT_DEMONSTRATIONS`, whose condition
is `preference_pairs_n >= 1000 and user_can_rank_but_not_write` - and it is the
only route to `TRAIN__DPO`. So the whole preference branch hung off a number
nothing could take. `count_preference_pairs` is that instrument.

## Why it is a separate tool from `profile_dataset`

`profile_dataset` already opens the file and already stamps two counts, so the
cheap move was to stamp a third. It cannot answer this question exactly. Its
`schema[column]["non_null"]` counts each column on its own, so the smallest of
the three is an UPPER BOUND on complete triples: a row with a prompt and a
chosen and no rejected, and another with a rejected and no prompt, are two
unusable rows that a per-column minimum reports as one usable pair. A gate
opened on an upper bound is a gate opened on an estimate, which is
`measure_eval_set`'s rule about lower bounds pointing the other way. Measured
below, on a file built to have exactly that shape.

## And a demonstrations file is NAMED rather than scored zero

Pointed at what `hf-peft-lora` trains on, an honest count is 0 - and 0 reads as
*your data is no good* when what is true is *your data is for the other
backend*. That distinction is the same one `_why_carving_is_not_honest_here` had
to learn: "there is nothing here" and "the thing you have goes somewhere else"
send a person to two different afternoons.
"""

import json
import unittest

from app import dataquality, diagnosis
from app.tools import REGISTRY, evidence, measure
import support


class CountingPreferencePairsTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = int(support.conversations(1)[0]["id"])

    def _write(self, name: str, rows: list[dict]) -> str:
        path = self.root / name
        path.write_text(
            "\n".join(json.dumps(row) for row in rows), encoding="utf-8"
        )
        return str(path)

    def _pairs(self, count: int, name: str = "pairs.jsonl") -> str:
        return self._write(
            name,
            [
                {"prompt": f"p{i}", "chosen": "the better answer", "rejected": "worse"}
                for i in range(count)
            ],
        )

    def _count(self, path: str, thread=None, **over):
        return REGISTRY.call(
            "count_preference_pairs",
            {"path": path, **over},
            actor="user",
            thread_id=self.thread if thread is None else thread,
        )

    # -- the gap, closed --------------------------------------------------

    def test_the_fact_now_resolves_to_an_instrument_at_all(self):
        """Rung one, and the reason this file exists. Before this tool, the
        product told a person that the only number on the route to preference
        optimisation was one nothing here could take."""
        resolved = evidence.resolves("preference_pairs_n", diagnosis.load_spec())
        self.assertEqual(resolved["tool"], "count_preference_pairs")
        self.assertEqual(resolved["run_as"], "harness")

    def test_the_ledger_binds_the_fact_to_this_capability(self):
        """Wall 9. `measured_by:` is what stops a tool that happens to carry the
        right name from stamping a fact it has no business measuring, and the
        binding is declared in the ledger rather than assumed by the tool."""
        self.assertEqual(
            evidence.measured_by("preference_pairs_n", diagnosis.load_spec()),
            ("data.preferences.count",),
        )
        self.assertIn(
            "data.preferences.count", REGISTRY.get("count_preference_pairs").provides
        )

    def test_a_count_is_recorded_as_MEASURED(self):
        result = self._count(self._pairs(1200))
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result["preference_pairs"], 1200)

        sheet, _ = evidence.assemble_facts(self.thread, {}, "user")
        recorded = sheet.get("preference_pairs_n")
        self.assertIsNotNone(recorded, "nothing reached the ledger")
        self.assertEqual(recorded.value, 1200)
        self.assertEqual(recorded.origin, diagnosis.MEASURED)

    def test_the_count_opens_the_route_it_exists_to_open(self):
        """End to end through the tree rather than asserted about a number.

        The condition is `preference_pairs_n >= 1000 and
        user_can_rank_but_not_write`, and the second half is the person's to
        say. This proves the first half is now takeable and that taking it moves
        the engine - which is the only sense in which closing the gap mattered.
        """
        import diagnosis_fixtures

        sheet = dict(diagnosis_fixtures.MINTING["TRAIN__DPO"])
        self.assertEqual(diagnosis.diagnose(sheet).outcome, "TRAIN__DPO")

        sheet["preference_pairs_n"] = diagnosis.measured(40)
        self.assertNotEqual(diagnosis.diagnose(sheet).outcome, "TRAIN__DPO")

    # -- the exactness that made it its own tool --------------------------

    def test_a_row_missing_one_of_the_three_fields_is_not_half_a_pair(self):
        path = self._write(
            "mixed.jsonl",
            [{"prompt": "p", "chosen": "c", "rejected": "r"} for _ in range(10)]
            + [{"prompt": "p", "chosen": "c"} for _ in range(4)]
            + [{"rejected": "r"} for _ in range(3)],
        )
        result = self._count(path)
        self.assertEqual(result["preference_pairs"], 10)
        self.assertEqual(result["incomplete_rows"], 7)
        self.assertIn("not all three", result["summary"])

    def test_the_per_column_minimum_would_have_been_wrong_here(self):
        """THE MEASUREMENT THAT DECIDED THIS WAS ITS OWN TOOL.

        Ten rows carrying prompt+chosen and ten carrying prompt+rejected. Every
        one of the three columns has non-null values in it and NOT ONE ROW is a
        preference pair. `profile_dataset`'s per-column counts - the cheap place
        to have stamped this - give a minimum of ten, so the shortcut would have
        handed the ledger a count of 10 for a file holding 0, and every number
        downstream would be about pairs that do not exist.
        """
        path = self._write(
            "never_complete.jsonl",
            [{"prompt": f"p{i}", "chosen": "c"} for i in range(10)]
            + [{"prompt": f"q{i}", "rejected": "r"} for i in range(10)],
        )

        profile = dataquality.profile(path)
        per_column = {
            field: (profile["schema"].get(field) or {}).get("non_null")
            for field in measure.PREFERENCE_FIELDS
        }
        self.assertEqual(
            min(value for value in per_column.values() if value is not None),
            10,
            f"the shortcut's answer changed shape: {per_column}",
        )

        self.assertEqual(self._count(path)["preference_pairs"], 0)

    def test_the_derivation_says_which_file_and_a_proposer_can_read_it(self):
        """THE SENTENCE IS A CONTRACT WITH `propose._A_RECORDED_COUNT`.

        That regular expression is the ledger's only record of WHICH FILE a
        count counted, and it reads `counted <n> rows in <path>` off the END of
        the derivation. A count whose subject cannot be recovered is refused by
        the preference build - correctly - and the refusal would read "nothing
        recorded which file it counted" about a count taken a minute earlier. So
        the qualification goes in front of the phrase the parser reads, and both
        halves are asserted here rather than hoped for.
        """
        from app.tools.propose import Subject, subject_of_a_recorded_measurement

        path = self._pairs(1000)
        self._count(path)
        _, trail = evidence.assemble_facts(self.thread, {}, "user")
        how = next(
            str(row.get("how") or "")
            for row in trail
            if row.get("fact") == "preference_pairs_n"
        )

        self.assertIn("rows carrying all of", how)
        recovered = subject_of_a_recorded_measurement(how)
        self.assertIsNotNone(recovered, f"no subject recoverable from {how!r}")
        self.assertTrue(Subject.of_path(path).matches(recovered)[0])

    # -- the refusals -----------------------------------------------------

    def test_a_demonstrations_file_is_named_rather_than_scored_zero(self):
        path = self._write(
            "demos.jsonl", [{"text": f"an example, number {i}"} for i in range(50)]
        )
        result = self._count(path)
        self.assertEqual(result["preference_pairs"], 0)
        self.assertEqual(result["demonstration_rows"], 50)
        self.assertIn("hf-peft-lora", result["summary"])
        self.assertIn("different objective", result["summary"])

        sheet, _ = evidence.assemble_facts(self.thread, {}, "user")
        self.assertIsNone(
            sheet.get("preference_pairs_n"),
            "a zero was stamped for a file that is simply the other recipe's",
        )

    def test_the_same_sentence_the_recipe_refuses_with(self):
        """One product, one answer. The recipe's own refusal and this tool's
        reply have to send a person to the same place, because they are two
        halves of one product looking at one file."""
        # `support.import_file` and not `exec_module` directly: importing a
        # recipe entrypoint from inside the repository writes a `.pyc` beside
        # it, which is a write into the working tree that
        # `test_the_sandbox_isolates_everything_the_product_writes` watches -
        # and has failed on in every CI run this repository has had.
        module = support.import_file(
            "dpo_entrypoint",
            support.REPO_ROOT / "recipes" / "hf-peft-dpo" / "entrypoint.py",
        )

        path = self._write("demos.jsonl", [{"text": "x"} for _ in range(60)])
        with self.assertRaises(SystemExit) as refused:
            module.load_pairs(support.Path(path))

        for phrase in ("hf-peft-lora", "different objective"):
            self.assertIn(phrase, str(refused.exception))
            self.assertIn(phrase, self._count(path)["summary"])

    def test_a_scan_that_stopped_early_records_nothing(self):
        """A lower bound is not a count - `measure_eval_set`'s rule, and here it
        matters more: the threshold this feeds is a `>=`, so a partial count is
        the one kind of wrong answer that fails toward "not enough" rather than
        toward "plenty". Driven by shrinking the budget rather than by writing a
        file big enough to take thirty seconds."""
        path = self._pairs(400)
        original = dataquality.COUNT_TIME_BUDGET_SECONDS
        dataquality.COUNT_TIME_BUDGET_SECONDS = 0.0
        try:
            result = self._count(path)
        finally:
            dataquality.COUNT_TIME_BUDGET_SECONDS = original

        self.assertFalse(result["exact"])
        self.assertIn("finish_the_count", result["stopped_because"])
        self.assertIn("a lower bound is not a count", result["summary"])

        sheet, _ = evidence.assemble_facts(self.thread, {}, "user")
        self.assertIsNone(sheet.get("preference_pairs_n"))

    def test_the_lever_lifts_the_bound_on_the_wait_and_not_on_the_answer(self):
        path = self._pairs(400)
        original = dataquality.COUNT_TIME_BUDGET_SECONDS
        dataquality.COUNT_TIME_BUDGET_SECONDS = 0.0
        try:
            result = self._count(path, finish_the_count=True)
        finally:
            dataquality.COUNT_TIME_BUDGET_SECONDS = original

        self.assertTrue(result["exact"])
        self.assertEqual(result["preference_pairs"], 400)

    def test_a_file_that_is_not_there_counts_nothing_and_says_so(self):
        result = self._count(str(self.root / "absent.jsonl"))
        self.assertFalse(result.get("ok"))
        self.assertFalse(result["exact"])
        self.assertIn("there is nothing at", result["summary"])

        sheet, _ = evidence.assemble_facts(self.thread, {}, "user")
        self.assertIsNone(
            sheet.get("preference_pairs_n"),
            "a mistyped filename was recorded as a file holding no pairs",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
