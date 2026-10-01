"""A generated row says who made it, how, and what was not measured.

The stamp has two halves and this file holds both, because getting either one
wrong is silent.

**Half one - the tag wall 8 reads.** `app/dataquality.py::is_synthetic_row`
reads exactly `synthetic`, and `synthetic_census` counts what it returns. A row
stamped with `is_synthetic` or `generated: true` reads as REAL, the census
reports `clean: true`, and a generated file opens a gate. `docs/PHASES.md`
records that failure as DONE on 2026-08-27; the assertions here are what keeps
it done, and they check the tag by handing the stamped row to the product's own
reader rather than by comparing key names to a list this file also wrote.

**Half two - the account.** `origin` is `ASSERTED` and nothing may make it
anything else. `MEASURED` is what `Instrument.measured` mints; a generated row
is a model's assertion, and stamping it stronger is exactly the laundering
`app/tools/evidence.py` exists to refuse. The test does not hardcode the string:
it asserts the stamp agrees with `evidence.SUPPLIED_ORIGIN[actor]`, so the two
cannot drift apart.
"""

from __future__ import annotations

import unittest

import support

driver = support.import_file(
    "generate_the_preference_pairs",
    support.REPO_ROOT / "scripts" / "generate_the_preference_pairs.py",
)


def a_generator(**over):
    return {
        "model": "granite42-hermes:latest",
        "base_url": "http://127.0.0.1:11434",
        "options": {"temperature": 0.9, "seed": 4412},
        "degradation": "over_promises_beyond_the_source",
        "eval_count": 218,
        "seconds": 5.1,
        **over,
    }


def a_judge(**over):
    return {
        "model": "granite42-hermes:latest",
        "options": {"temperature": 0.0, "seed": 0},
        "verdict": "KEEP",
        "reasoning": (
            "The rejected answer promises unconditional returns, which the "
            "source answer limits to unmarked books within 30 days."
        ),
        "seconds": 3.4,
        **over,
    }


A_SOURCE = {
    "path": "runs/honest-path/train.jsonl",
    "sha256": "3a71" + "0" * 60,
    "row_index": 2,
    "answer_field": "response",
}

A_ROW = {
    "prompt": "Can I return a book?",
    "chosen": "Unmarked books can be returned within 30 days with a receipt.",
    "rejected": "Books can always be returned, no receipt needed.",
}


def stamp(row=None, **over):
    fields = dict(
        generator=a_generator(),
        validator={"module": "scripts/check_that_a_tool_call_could_run.py",
                   "checked": list(driver.WHAT_THE_VALIDATOR_CHECKED),
                   "faults": []},
        judge=a_judge(),
        source=dict(A_SOURCE),
        script="scripts/generate_the_preference_pairs.py",
        seed="granite42-2026-09-03-a",
        now="2026-09-03 06:14:02",
    )
    fields.update(over)
    return driver.stamp_the_provenance(dict(row or A_ROW), **fields)


class TheProductsOwnReaderSeesItAsSyntheticTest(unittest.TestCase):
    """The tag is checked by the code that will actually read it."""

    def test_the_census_reader_calls_a_stamped_row_synthetic(self):
        from app import dataquality

        self.assertTrue(dataquality.is_synthetic_row(stamp()))

    def test_an_unstamped_row_is_still_read_as_real(self):
        """The reader is not simply saying yes to everything."""
        from app import dataquality

        self.assertFalse(dataquality.is_synthetic_row(dict(A_ROW)))

    def test_the_two_companion_keys_are_spelled_the_way_datawork_spells_them(self):
        stamped = stamp()
        self.assertEqual(stamped["synthetic_source_index"], A_SOURCE["row_index"])
        self.assertEqual(stamped["synthetic_seed"], "granite42-2026-09-03-a")

    def test_the_source_index_is_the_source_row_not_the_output_row(self):
        """Sampling with replacement means output 7 can be source row 2. An
        index that counted outputs would point every reviewer at the wrong
        line of the seed file."""
        stamped = stamp(source={**A_SOURCE, "row_index": 41})
        self.assertEqual(stamped["synthetic_source_index"], 41)

    def test_a_stamper_that_dropped_a_tag_key_raises_rather_than_shipping(self):
        """Refusal 4, exercised by adding a key to `TAG_KEYS` that the stamper
        does not write - which is what a future edit that renames one looks
        like from the inside. A builder's own defect presenting as a slightly
        smaller output file is a defect nobody finds."""
        was = driver.TAG_KEYS
        driver.TAG_KEYS = was + ("synthetic_run_id",)
        try:
            with self.assertRaises(driver.TheStamperHasABug) as caught:
                stamp()
        finally:
            driver.TAG_KEYS = was
        self.assertIn("synthetic_run_id", str(caught.exception))
        self.assertIn("wall 8", str(caught.exception))

    def test_a_source_with_no_row_index_is_a_loud_failure_not_a_null_tag(self):
        """A `synthetic_source_index` of `None` would tag the row while
        pointing every reviewer at nothing."""
        with self.assertRaises(KeyError):
            driver.stamp_the_provenance(
                dict(A_ROW),
                generator=a_generator(), validator={}, judge=a_judge(),
                source={"path": "x"},
                script="s", seed="", now="n",
            )


class TheOriginIsAssertedAndCannotBeAnythingElseTest(unittest.TestCase):
    def test_the_stamp_agrees_with_the_products_own_actor_table(self):
        from app.tools import evidence

        block = stamp()["provenance"]
        self.assertEqual(block["actor"], evidence.MODEL)
        self.assertEqual(block["origin"], evidence.SUPPLIED_ORIGIN[block["actor"]])

    def test_it_is_never_measured_whatever_the_caller_passes(self):
        """There is no parameter that reaches `origin`, and this asserts it by
        trying every field that touches the block."""
        for over in (
            {"generator": a_generator(origin="MEASURED")},
            {"validator": {"origin": "MEASURED"}},
            {"judge": a_judge(origin="MEASURED")},
            {"source": {**A_SOURCE, "origin": "MEASURED"}},
        ):
            with self.subTest(field=sorted(over)[0]):
                self.assertEqual(stamp(**over)["provenance"]["origin"], "ASSERTED")

    def test_a_row_field_named_origin_does_not_reach_the_block(self):
        stamped = stamp({**A_ROW, "origin": "MEASURED"})
        self.assertEqual(stamped["provenance"]["origin"], "ASSERTED")


class TheHowSentenceSaysWhatWasNotDoneTest(unittest.TestCase):
    def test_it_ends_by_saying_nothing_was_measured(self):
        """The one thing a reader of a generated file might assume is the one
        thing that is not true of any row in it."""
        self.assertTrue(
            stamp()["provenance"]["how"].endswith("Nothing here was measured."),
            stamp()["provenance"]["how"],
        )

    def test_it_names_the_model_the_row_and_the_file(self):
        how = stamp()["provenance"]["how"]
        self.assertIn("granite42-hermes:latest", how)
        self.assertIn("row 2", how)
        self.assertIn("runs/honest-path/train.jsonl", how)

    def test_it_names_the_degradation_the_generator_was_asked_for(self):
        self.assertIn("over_promises_beyond_the_source", stamp()["provenance"]["how"])

    def test_it_says_only_the_rejected_answer_was_written_by_a_model(self):
        self.assertIn(
            "Only the rejected answer was written by a model",
            stamp()["provenance"]["how"],
        )

    def test_a_run_with_no_named_degradation_still_reads_as_a_sentence(self):
        how = stamp(generator=a_generator(degradation=""))["provenance"]["how"]
        self.assertNotIn("''", how)
        self.assertTrue(how.endswith("Nothing here was measured."))


class SameWeightsIsComputedNotWrittenTest(unittest.TestCase):
    def test_the_same_model_on_both_sides_is_recorded_as_such(self):
        self.assertIs(
            stamp()["provenance"]["judge"]["same_weights_as_generator"], True
        )

    def test_two_different_models_are_recorded_as_such(self):
        stamped = stamp(judge=a_judge(model="qwen2.5:7b"))
        self.assertIs(
            stamped["provenance"]["judge"]["same_weights_as_generator"], False
        )

    def test_a_caller_cannot_write_it_by_hand(self):
        """It is computed, so a caller who claims independence they do not have
        is overruled rather than believed."""
        stamped = stamp(judge=a_judge(same_weights_as_generator=False))
        self.assertIs(
            stamped["provenance"]["judge"]["same_weights_as_generator"], True
        )


class TheFourRefusalsTest(unittest.TestCase):
    def test_a_well_accounted_row_may_ship(self):
        self.assertEqual(driver.why_this_row_must_not_ship(stamp()), [])

    def test_an_unreadable_verdict_stops_the_row(self):
        faults = driver.why_this_row_must_not_ship(stamp(judge=a_judge(verdict=None)))
        self.assertTrue(any("unreadable" in f for f in faults), faults)

    def test_a_terse_account_no_longer_stops_the_row(self):
        """RETARGETED 2026-09-05 when the reasoning floor was retired.

        It asserted that two characters of account refused the row, on the
        theory that "a verdict with no account is a verdict nobody can check".
        The account can be FABRICATED - 19 of 19 KEEPs in the sentinel-N run
        named a clause the rewrite still contained - and across all 111 recorded
        replies the floor would have refused none. Length measures verbosity.

        THIS TEST IS ALSO WHY THE CHANGE'S OWN CLAIM WAS WRONG TWICE. The
        commit first said no test asserted the floor, then said one did. Two
        did, in two files, and both times the count came from grepping - first
        for the constant, then for a phrase in one file - instead of
        enumerating the callers of `why_this_row_must_not_ship`.
        """
        faults = driver.why_this_row_must_not_ship(stamp(judge=a_judge(reasoning="ok")))
        self.assertEqual([f for f in faults if "nobody can check" in f], [])

    def test_a_bare_verdict_with_no_account_at_all_still_stops_the_row(self):
        """What replaced the floor, and on format rather than length: the rubric
        asks for a line of reasoning THEN the word, so a reply that is only the
        word did not follow it."""
        faults = driver.why_this_row_must_not_ship(stamp(judge=a_judge(reasoning="KEEP")))
        self.assertTrue(any("bare verdict" in f for f in faults), faults)

    def test_a_row_with_no_provenance_at_all_is_refused_rather_than_crashing(self):
        self.assertNotEqual(driver.why_this_row_must_not_ship(dict(A_ROW)), [])


class TheDegradationListIsClosedTest(unittest.TestCase):
    def test_every_named_degradation_has_the_words_the_model_is_shown(self):
        self.assertEqual(
            set(driver.DEGRADATIONS), set(driver.WHAT_EACH_DEGRADATION_DOES),
            "a name on one list and not the other is either an unprompted run "
            "or an instruction nothing can ask for",
        )

    def test_it_is_a_tuple_so_it_cannot_be_appended_to_at_runtime(self):
        self.assertIsInstance(driver.DEGRADATIONS, tuple)

    def test_the_preference_checks_are_a_real_subset_of_the_validators(self):
        """A provenance block that listed a check nothing performs would say a
        question was asked of the row that was not."""
        self.assertTrue(driver.WHAT_A_PREFERENCE_PAIR_IS_CHECKED_FOR)
        self.assertTrue(
            set(driver.WHAT_A_PREFERENCE_PAIR_IS_CHECKED_FOR)
            <= set(driver.WHAT_THE_VALIDATOR_CHECKED)
        )
        self.assertNotIn(
            "types_match", driver.WHAT_A_PREFERENCE_PAIR_IS_CHECKED_FOR,
            "a preference pair is never checked against a tool schema",
        )

    #: Words that hand a generator a blank page. The spec calls an open-ended
    #: "make it worse" instruction *"the fabrication door"*, and these are what
    #: that door reads like in a prompt.
    OPEN_ENDED = (
        "any way", "anything", "as you like", "be creative", "invent",
        "make up", "come up with", "your own", "however you",
    )

    def test_no_degradation_hands_the_generator_a_blank_page(self):
        """The fabrication door. An instruction that says "make it worse" in
        any of its spellings is not a named degradation of a real answer, it is
        a request for a different answer - and a different answer is a new
        claim about the world, which is the one thing a corpus built out of
        real rows exists to avoid."""
        for name, words in driver.WHAT_EACH_DEGRADATION_DOES.items():
            with self.subTest(degradation=name):
                lowered = words.lower()
                for phrase in self.OPEN_ENDED:
                    self.assertNotIn(phrase, lowered)

    def test_every_degradation_states_a_prohibition_and_a_source_to_stay_inside(self):
        """Both halves are needed. "Drop a condition" alone tells the model
        what to change; only "add nothing that is not in the source answer"
        tells it what it may not reach for."""
        for name, words in driver.WHAT_EACH_DEGRADATION_DOES.items():
            with self.subTest(degradation=name):
                lowered = words.lower()
                self.assertTrue(
                    "do not" in lowered or "never" in lowered,
                    f"{name} names no prohibition: {words!r}",
                )
                self.assertIn("source answer", lowered)


class TheReportShowsTheFactorsNotJustTheProductTest(unittest.TestCase):
    def report(self, **over):
        fields = dict(
            generated=500,
            validator_dropped={"required parameter 'path' is missing": 118},
            judge_dropped=137, judge_unreadable=3, kept=242,
            distinct_sources=31, source_rows=49, control=None,
            generator_model="granite42-hermes:latest",
            judge_model="granite42-hermes:latest",
        )
        fields.update(over)
        return driver.the_kept_and_dropped_report(**fields)

    def test_both_pass_rates_are_there_beside_the_keep_rate(self):
        """A 40% that is 95%/42% is a prompting problem; 42%/95% is a format
        problem. The merged number hides which repair to make."""
        report = self.report()
        self.assertAlmostEqual(report["validator"]["pass_rate"], 0.764, places=3)
        self.assertAlmostEqual(report["judge"]["pass_rate"], 0.6335, places=3)
        self.assertAlmostEqual(report["keep_rate"], 0.484, places=3)

    def test_a_row_the_generator_never_produced_is_not_a_validator_fault(self):
        """An endpoint that went down must not read as a prompting problem.
        The validator was never offered those rows, so they are outside both of
        its rates rather than counted as failures of it."""
        report = self.report(generated=500, generator_failed=100)
        self.assertEqual(report["generator"]["failed"], 100)
        self.assertEqual(report["validator"]["offered"], 400)
        self.assertAlmostEqual(report["validator"]["pass_rate"], 0.705, places=3)
        self.assertAlmostEqual(report["judge"]["pass_rate"], 0.8582, places=3)

    def test_with_no_generator_failures_the_denominator_is_every_row(self):
        report = self.report()
        self.assertEqual(report["generator"]["failed"], 0)
        self.assertEqual(report["validator"]["offered"], report["generated"])

    def test_the_resolution_comes_from_the_products_own_wilson(self):
        from app.tools import evals

        self.assertEqual(
            self.report()["resolution"], evals.resolution_for(242, 500)
        )

    def test_a_run_that_generated_nothing_has_no_rate_rather_than_a_zero(self):
        report = self.report(generated=0, validator_dropped={}, kept=0)
        self.assertIsNone(report["keep_rate"])
        self.assertIsNone(report["validator"]["pass_rate"])
        self.assertIsNone(report["resolution"])

    def test_a_missing_control_is_named_as_missing(self):
        report = self.report()
        self.assertIsNone(report["control"])
        self.assertIn("cannot be read", report["control_note"])

    def test_a_control_that_was_run_replaces_the_note(self):
        report = self.report(control={"rows": 49, "keep_rate": 0.959})
        self.assertEqual(report["control"]["rows"], 49)
        self.assertNotIn("control_note", report)

    def test_one_judge_grading_its_own_output_is_said_out_loud(self):
        self.assertIn("not independent evidence", self.report()["who_judged"]["note"])

    def test_a_different_judge_gets_no_such_note(self):
        report = self.report(judge_model="qwen2.5:7b")
        self.assertFalse(report["who_judged"]["same_weights"])
        self.assertNotIn("note", report["who_judged"])

    def test_nobody_has_read_the_rows_until_somebody_has(self):
        self.assertEqual(self.report()["human"]["kept_rows_read"], 0)
        self.assertIsNone(self.report()["human"]["sample_drawn"])


if __name__ == "__main__":
    unittest.main()
