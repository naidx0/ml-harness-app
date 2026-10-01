"""Stage 3: what the driver does with what a model says back.

THERE IS NO MODEL IN THIS FILE. The adapter is scripted, the way
`tests/test_a_turn_always_speaks.py` scripts a provider, so what is exercised is
the driver's reading of a reply and its four refusals - the parts that are wrong
or right on their own merits. That a real model can be reached at all is proven
by running the script, not by a test that would need one installed.

THE ONE THING TO KNOW ABOUT THESE ASSERTIONS. A dropped row is not a smaller
number; it is a row kept in `dropped.jsonl` with the sentences that say why. The
spec's line is *"Every dropped row, with why. Not a count"*, and it is the
difference between a generator that can be fixed and one that can only be
re-run.
"""

from __future__ import annotations

import json
import unittest

import support

driver = support.import_file(
    "generate_the_preference_pairs",
    support.REPO_ROOT / "scripts" / "generate_the_preference_pairs.py",
)

#: Two real rows from `runs/honest-path/train.jsonl`, copied. The whole point of
#: the pipeline is that the prompt and the chosen answer are somebody's real
#: ones, so the fixture is real ones.
A_SEED_FILE = "\n".join(
    json.dumps(row)
    for row in (
        {
            "instruction": "Where is my order? I ordered on the 3rd.",
            "response": (
                "Orders placed on the 3rd ship within two working days. If you "
                "give me your order number I can check the tracking for you."
            ),
            "split": "train",
        },
        {
            "instruction": "Can I return a book?",
            "response": (
                "Unmarked books can be returned within 30 days with a receipt."
            ),
            "split": "train",
        },
    )
)


#: A SECOND FIXTURE, FOR THE CONTROL ONLY, and it exists because of a real
#: behaviour change. `specifics_the_rewrite_adds` now drops any pair whose
#: rejected side names a number, price, weekday or name the real answer never
#: did - and two unrelated real answers almost always do. Measured over the
#: owner's own file: 28 of the 49 real-vs-real control pairs are now settled by
#: arithmetic before a judge call is spent on them. That is the check working,
#: and it means a control fixture built from rows carrying digits would be
#: testing the validator rather than the judge. These two answers name nothing
#: the other does not, so the pairs reach the judge.
A_SEED_FILE_THAT_NAMES_NOTHING = "\n".join(
    json.dumps(row)
    for row in (
        {
            "instruction": "Do you gift wrap?",
            "response": (
                "We do, but only for books bought here, and only if you ask at "
                "the counter before you pay."
            ),
        },
        {
            "instruction": "Can I reserve a book?",
            "response": (
                "Yes, if it is already on the shelf. Ask and we will put it "
                "under your name until the end of the week."
            ),
        },
    )
)

class ScriptedModel:
    """Replies in order, one per `stream` call. Raises when the script runs out.

    RAISES RATHER THAN REPEATING, so a test that expected four calls and got
    five fails loudly instead of grading a reply it never wrote.
    """

    def __init__(self, replies):
        self.replies = list(replies)
        self.asked = []

    def stream(self, messages, tools=None, *, secret=None):
        from app.providers import Delta

        self.asked.append(messages)
        if not self.replies:
            raise AssertionError(
                f"the driver made {len(self.asked)} model calls; the script had "
                f"{len(self.asked) - 1}"
            )
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            yield Delta(kind="error", detail=str(reply))
            return
        yield Delta(kind="text", text=reply)
        yield Delta(kind="end")


#: A rewrite for each seed row that ONLY REMOVES, verified against all three
#: gates. Needed once the added-fact rule shipped: a fixture written for row 0
#: and handed to row 1 introduces every content word of row 0, so the validator
#: refuses it and the row never reaches the judge the test is about. The old
#: fixtures failed that way and read as "the judge did not drop it".
A_REMOVAL_FOR = (
    "Orders ship within two working days.",
    "Unmarked books can be returned.",
    "We do, but only for books bought here.",
    "Yes, if it is already on the shelf.",
)


def a_removal_for(index: int) -> str:
    """The pure-removal rewrite for seed row `index`, cycling."""
    return A_REMOVAL_FOR[index % len(A_REMOVAL_FOR)]


#: A SECOND distinct rewrite of seed row 0, needed once the dedup gate shipped:
#: `a_good_rewrite(2)` returns the SAME rewrite twice, and two identical triples
#: are one training example, so the second is now refused as a row we already
#: have. A test that wanted two outputs from one source row wanted two DIFFERENT
#: outputs; it was passing because nothing counted.
ANOTHER_REMOVAL_FOR_ROW_0 = "Orders ship within two working days. I can check the tracking for you."


def a_good_rewrite(n=1):
    """One generator reply and one judge KEEP, `n` times over.

    CHANGED 2026-09-05 WHEN THE ADDED-FACT RULE SHIPPED, and the old fixture is
    worth recording. It was:

        "Orders always ship the same day, no order number needed."

    which adds `always`, `day` and `needed` - none of them in the source - and
    its scripted judge reply ended "and it adds nothing new". The fixture the
    whole suite called a GOOD rewrite was an added-fact row carrying a judge
    sentence asserting the opposite: precisely the failure measured on 8 of 20
    real rows that day. "always ship the same day" is also a STRONGER promise
    than "within two working days", so it was not only inventing, it was
    inventing something false.

    The replacement drops the qualifying clause and the whole second sentence
    and introduces nothing: every word of it is in the source.
    """
    out = []
    for _ in range(n):
        out.append("Orders ship within two working days.")
        out.append(
            "The rewrite drops the condition that the order was placed on the "
            "3rd and the offer to check the tracking, which is exactly the "
            "named degradation, and it adds nothing new." + chr(10) + "KEEP"
        )
    return out


class TheSeedFileIsReadWithItsLineNumbersTest(unittest.TestCase):
    def rows(self, text):
        root = support.sandbox(self)
        path = root / "train.jsonl"
        path.write_text(text, encoding="utf-8")
        return driver.read_the_source_rows(
            path, question_field="instruction", answer_field="response"
        )

    def test_both_real_rows_come_back_with_their_question_and_answer(self):
        rows = self.rows(A_SEED_FILE)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["question"], "Can I return a book?")
        self.assertIn("30 days", rows[1]["answer"])

    def test_the_index_is_the_line_of_the_file_not_the_position_in_the_result(self):
        """A blank line and an unusable row still consume a line number,
        because `row_index` is what sends a reviewer to the right line."""
        text = "\n".join(
            [
                json.dumps({"instruction": "q0", "response": "a0 and more text"}),
                "",
                json.dumps({"instruction": "no answer here"}),
                json.dumps({"instruction": "q3", "response": "a3 and more text"}),
            ]
        )
        rows = self.rows(text)
        self.assertEqual([row["row_index"] for row in rows], [0, 3])

    def test_a_row_with_an_empty_answer_is_not_a_row(self):
        text = json.dumps({"instruction": "q", "response": "   "})
        self.assertEqual(self.rows(text), [])

    def test_a_line_that_is_not_json_is_skipped_rather_than_crashing_the_run(self):
        text = "{not json\n" + json.dumps(
            {"instruction": "q1", "response": "a1 and more text"}
        )
        rows = self.rows(text)
        self.assertEqual([row["row_index"] for row in rows], [1])


class TheVerdictIsReadFromTheConclusionTest(unittest.TestCase):
    def test_keep_and_drop(self):
        self.assertIs(driver.read_the_judges_verdict("reasons\nKEEP"), True)
        self.assertIs(driver.read_the_judges_verdict("reasons\nDROP"), False)

    def test_the_last_word_wins_because_the_reasoning_uses_both(self):
        """THE ONE THAT MATTERS. A judge asked for reasoning first writes "it
        does not DROP the condition, so KEEP". Reading the first verdict word
        would grade the argument instead of the conclusion, and it would grade
        it backwards."""
        self.assertIs(
            driver.read_the_judges_verdict(
                "It does not DROP the condition, so KEEP"
            ),
            True,
        )

    def test_a_reply_with_no_verdict_word_is_unreadable_not_a_drop(self):
        """`None` is not a third grade. Reading it as DROP would be a reading
        nobody made; reading it as KEEP would be that plus flattery."""
        self.assertIsNone(driver.read_the_judges_verdict("I am not sure."))
        self.assertIsNone(driver.read_the_judges_verdict(""))

    def test_the_word_must_stand_alone(self):
        self.assertIsNone(driver.read_the_judges_verdict("HOUSEKEEPING"))


class OnlyTheWrappingIsRemovedTest(unittest.TestCase):
    def test_a_label_a_fence_and_quotes_come_off(self):
        for wrapped in (
            'Rewritten answer: Orders always ship the same day.',
            '"Orders always ship the same day."',
            "```\nOrders always ship the same day.\n```",
        ):
            with self.subTest(wrapped=wrapped[:24]):
                self.assertEqual(
                    driver.strip_the_models_scaffolding(wrapped),
                    "Orders always ship the same day.",
                )

    def test_nothing_inside_is_edited(self):
        """A stripper that also tidied the text would make the row something
        neither the model nor the person wrote."""
        text = 'She said "within 30 days" and meant it.'
        self.assertEqual(driver.strip_the_models_scaffolding(text), text)


class EveryRowIsKeptOrAccountedForTest(unittest.TestCase):
    def run_it(self, replies, *, how_many=1, seed_text=A_SEED_FILE,
               enforce_clause_one=True):
        root = support.sandbox(self)
        source = root / "train.jsonl"
        source.write_text(seed_text, encoding="utf-8")
        out = root / "out"
        model = ScriptedModel(replies)
        report = driver.generate(
            source=source, out_dir=out, how_many=how_many,
            model="scripted", base_url="http://127.0.0.1:0",
            seed="a-test", question_field="instruction",
            answer_field="response", degradation=driver.DEGRADATIONS[0],
            adapter=model, now=lambda: "2026-09-03 00:00:00",
            enforce_clause_one=enforce_clause_one,
        )
        return report, out, model

    def read(self, out, name):
        path = out / name
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_a_kept_row_carries_the_real_question_and_the_real_answer(self):
        report, out, _ = self.run_it(a_good_rewrite())
        rows = self.read(out, "train.synthetic.jsonl")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["prompt"], "Where is my order? I ordered on the 3rd.")
        self.assertIn("two working days", rows[0]["chosen"])
        self.assertEqual(report["kept"], 1)

    def test_a_kept_row_is_stamped_so_the_census_reads_it_as_synthetic(self):
        from app import dataquality

        _, out, _ = self.run_it(a_good_rewrite())
        row = self.read(out, "train.synthetic.jsonl")[0]
        self.assertTrue(dataquality.is_synthetic_row(row))
        self.assertEqual(row["provenance"]["origin"], "ASSERTED")

    def test_the_row_names_only_the_checks_that_actually_ran_on_it(self):
        """A preference pair is never checked against a tool schema. Naming
        the tool-call checks in its provenance would say four questions were
        asked of it that were not."""
        _, out, _ = self.run_it(a_good_rewrite())
        checked = self.read(out, "train.synthetic.jsonl")[0]["provenance"][
            "validator"
        ]["checked"]
        self.assertEqual(
            checked,
            ["chosen_is_the_source_answer", "rejected_adds_no_new_specifics"],
        )
        self.assertNotIn("registry_tools", self.read(
            out, "train.synthetic.jsonl")[0]["provenance"]["validator"])

    def test_a_judge_that_said_drop_puts_the_row_in_dropped_with_the_reason(self):
        _, out, _ = self.run_it(
            ["Orders ship within two working days.",
             "It invented a new policy." + chr(10) + "DROP"]
        )
        self.assertEqual(self.read(out, "train.synthetic.jsonl"), [])
        dropped = self.read(out, "dropped.jsonl")
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0]["dropped_by"], "judge")
        self.assertIn("the judge said DROP", dropped[0]["why"])
        self.assertIn("invented a new policy", dropped[0]["provenance"]["judge"]["reasoning"])

    def test_a_rewrite_identical_to_the_real_answer_never_reaches_the_judge(self):
        """The validator is stage 2 and it runs first, so a row with no
        preference in it costs no judge call."""
        real = json.loads(A_SEED_FILE.splitlines()[0])["response"]
        _, out, model = self.run_it([real])
        self.assertEqual(len(model.asked), 1, "the judge was asked about a non-pair")
        dropped = self.read(out, "dropped.jsonl")
        self.assertEqual(dropped[0]["dropped_by"], "validator")
        self.assertTrue(any("no preference here" in w for w in dropped[0]["why"]))

    def test_a_generator_that_failed_is_a_dropped_row_not_a_crash(self):
        report, out, _ = self.run_it([RuntimeError("connection refused")])
        dropped = self.read(out, "dropped.jsonl")
        self.assertEqual(dropped[0]["dropped_by"], "generator")
        self.assertTrue(any("connection refused" in w for w in dropped[0]["why"]))
        # And it is NOT a validator fault. An endpoint that went down reading as
        # a prompting problem would send a reader to fix the wrong thing.
        self.assertEqual(report["generator"]["failed"], 1)
        self.assertEqual(report["validator"]["by_fault"], {})
        self.assertEqual(report["validator"]["offered"], 0)

    def test_each_stage_keeps_its_own_tally(self):
        """THE ONE THAT MATTERS FOR READING THE REPORT. The two pass rates are
        the only thing that says which repair to make, and a judge drop counted
        among the validator's faults makes both of them wrong."""
        # ONE source row, so all three outputs are rewrites of the same answer
        # and the middle reply below really is a copy of it.
        only = A_SEED_FILE.splitlines()[0]
        real = json.loads(only)["response"]
        report, _, _ = self.run_it(
            a_good_rewrite()
            + [real]
            + [ANOTHER_REMOVAL_FOR_ROW_0,
               "it invented a policy." + chr(10) + "DROP"],
            how_many=3,
            seed_text=only,
        )
        stages = report["dropped_by_stage"]
        self.assertEqual(sum(stages["validator"].values()), 1)
        self.assertEqual(sum(stages["generator"].values()), 0)
        self.assertGreaterEqual(sum(stages["judge"].values()), 1)
        self.assertEqual(report["validator"]["dropped"], 1)
        self.assertEqual(report["judge"]["dropped"], 1)
        self.assertEqual(report["kept"], 1)

    def test_an_unreadable_verdict_drops_the_row_and_is_counted_apart(self):
        """Unreadable is not the same failure as DROP and the report keeps
        them in different columns, because they call for different repairs."""
        report, out, _ = self.run_it(
            ["Orders ship within two working days.",
             "I am not sure about this one."]
        )
        self.assertEqual(report["judge"]["unreadable"], 1)
        self.assertEqual(report["judge"]["dropped"], 0)
        self.assertEqual(self.read(out, "train.synthetic.jsonl"), [])

    def test_a_keep_with_no_reasoning_is_dropped(self):
        """STILL DROPPED, FOR A DIFFERENT REASON, and this test is why the
        reasoning floor's removal did not become a regression.

        The floor was retired on 2026-09-05 because it refused 0 of the 111
        recorded replies and because the account it protected can be fabricated.
        A first draft of that change said "nothing was tested against it" - this
        test is the counter-example, and it caught the case the measurement
        never saw: a reply of the single word KEEP.

        That is not a verbosity failure and no length decides it. The rubric
        asks for a line of reasoning THEN the word, so a reply that is only the
        word did not follow the rubric. The refusal now says that.
        """
        report, out, _ = self.run_it(["Orders ship within two working days.", "KEEP"])
        self.assertEqual(report["kept"], 0)
        self.assertTrue(
            any("bare verdict" in w for w in self.read(out, "dropped.jsonl")[0]["why"])
        )

    def test_the_report_is_written_even_when_nothing_was_kept(self):
        _, out, _ = self.run_it(["same", "no verdict word"])
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["kept"], 0)
        self.assertIsNone(report["control"])

    def test_the_dropped_file_holds_rows_and_the_report_holds_the_tally(self):
        report, out, _ = self.run_it(
            a_good_rewrite() + [a_removal_for(1),
                                "invented." + chr(10) + "DROP"],
            how_many=2,
        )
        self.assertEqual(report["kept"], 1)
        self.assertEqual(len(self.read(out, "dropped.jsonl")), 1)
        self.assertEqual(sum(report["validator"]["by_fault"].values()), 0)

    def test_two_outputs_from_one_source_row_both_name_that_source_row(self):
        # Two DISTINCT rewrites of one source row - see
        # ANOTHER_REMOVAL_FOR_ROW_0. Two identical ones are one example.
        replies = a_good_rewrite() + [
            ANOTHER_REMOVAL_FOR_ROW_0,
            "Also worse." + chr(10) + "KEEP",
        ]
        _, out, _ = self.run_it(replies, how_many=2, seed_text=A_SEED_FILE.splitlines()[0])
        rows = self.read(out, "train.synthetic.jsonl")
        self.assertEqual([row["synthetic_source_index"] for row in rows], [0, 0])


class TheDedupGateInThePipelineTest(unittest.TestCase):
    """The gate that makes `kept: N` mean N different things.

    Measured before it existed: 164 kept rows were 127 distinct, 156 were 119,
    95 were 60, and one triple appeared SEVEN times. A model trained on that
    corpus would have seen one row seven times and counted it as seven examples.
    """

    def run_it(self, replies, *, how_many=2, refuse_duplicates=True, seed=None):
        root = support.sandbox(self)
        source = root / "train.jsonl"
        source.write_text(A_SEED_FILE.splitlines()[0], encoding="utf-8")
        out = root / "out"
        model = ScriptedModel(replies)
        report = driver.generate(
            source=source, out_dir=out, how_many=how_many, model="scripted",
            base_url="x", seed="s", question_field="instruction",
            answer_field="response", degradation=driver.DEGRADATIONS[0],
            adapter=model, now=lambda: "2026-09-06 00:00:00",
            refuse_duplicates=refuse_duplicates,
            rows_already_kept=seed,
        )
        return report, out, model

    def read(self, out, name):
        text = (out / name).read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def test_the_same_rewrite_twice_keeps_one_row(self):
        report, out, _ = self.run_it(a_good_rewrite(2))
        self.assertEqual(report["kept"], 1, "a duplicate was kept as a second row")
        self.assertEqual(sum(report["dropped_by_stage"]["duplicate"].values()), 1)

    def test_the_duplicate_never_reaches_the_judge(self):
        """Zero calls. `a_good_rewrite(2)` scripts two judge replies; if the
        second row reached the judge the second would be consumed."""
        _, _, model = self.run_it(a_good_rewrite(2))
        self.assertEqual(len(model.asked), 3, "the judge was asked about a duplicate")

    def test_it_has_its_own_column_and_is_not_a_validator_fault(self):
        """A duplicate is redundant, not wrong. `12 duplicates` must not read
        as `12 defects`."""
        report, _, _ = self.run_it(a_good_rewrite(2))
        self.assertEqual(sum(report["dropped_by_stage"]["validator"].values()), 0)
        self.assertEqual(sum(report["dropped_by_stage"]["duplicate"].values()), 1)

    def test_two_distinct_rewrites_both_survive(self):
        """A gate that refused every second row would pass the tests above."""
        report, _, _ = self.run_it(
            a_good_rewrite() + [ANOTHER_REMOVAL_FOR_ROW_0,
                                "Also worse." + chr(10) + "KEEP"]
        )
        self.assertEqual(report["kept"], 2)
        self.assertEqual(sum(report["dropped_by_stage"]["duplicate"].values()), 0)

    def test_a_row_already_in_the_corpus_is_refused_before_any_call(self):
        """THE CASE THE RULING ASKED FOR: seeded from rows kept previously, not
        only from this run."""
        already = [{
            "prompt": "Where is my order? I ordered on the 3rd.",
            "chosen": json.loads(A_SEED_FILE.splitlines()[0])["response"],
            "rejected": "Orders ship within two working days.",
        }]
        report, _, model = self.run_it(a_good_rewrite(1), how_many=1, seed=already)
        self.assertEqual(report["kept"], 0)
        self.assertEqual(sum(report["dropped_by_stage"]["duplicate"].values()), 1)
        self.assertEqual(len(model.asked), 1, "the judge was asked anyway")

    def test_the_switch_restores_the_older_behaviour(self):
        """Kept so the corpus before the gate can be reproduced rather than
        re-argued."""
        report, _, _ = self.run_it(a_good_rewrite(2), refuse_duplicates=False)
        self.assertEqual(report["kept"], 2)


class TheRunStopsRatherThanProducingRowsNobodyCanUseTest(unittest.TestCase):
    def test_a_seed_file_with_no_usable_row_stops_before_the_first_model_call(self):
        box = support.sandbox(self)
        if True:
            source = box / "empty.jsonl"
            source.write_text("\n", encoding="utf-8")
            model = ScriptedModel([])
            with self.assertRaises(driver.TheRunMustStop) as caught:
                driver.generate(
                    source=source, out_dir=box / "out", how_many=3,
                    model="scripted", base_url="x", seed="s",
                    question_field="instruction", answer_field="response",
                    degradation=driver.DEGRADATIONS[0], adapter=model,
                )
            self.assertEqual(model.asked, [])
            self.assertIn("no row carrying", str(caught.exception))

    def test_a_seed_file_that_changed_mid_run_stops_and_keeps_nothing(self):
        """Refusal 3. Every `synthetic_source_index` in the run now points
        somewhere else, and there is no repair for that afterwards."""

        class ChangesTheFileAfterTheFirstReply(ScriptedModel):
            def __init__(self, replies, source):
                super().__init__(replies)
                self.source = source

            def stream(self, messages, tools=None, *, secret=None):
                yield from super().stream(messages, tools, secret=secret)
                self.source.write_text("{}\n" + A_SEED_FILE, encoding="utf-8")

        box = support.sandbox(self)
        if True:
            source = box / "train.jsonl"
            source.write_text(A_SEED_FILE, encoding="utf-8")
            out = box / "out"
            model = ChangesTheFileAfterTheFirstReply(a_good_rewrite(), source)
            with self.assertRaises(driver.TheRunMustStop) as caught:
                driver.generate(
                    source=source, out_dir=out, how_many=1, model="scripted",
                    base_url="x", seed="s", question_field="instruction",
                    answer_field="response", degradation=driver.DEGRADATIONS[0],
                    adapter=model, now=lambda: "n",
                )
            self.assertIn("changed while the run was in progress", str(caught.exception))
            self.assertEqual(
                (out / "train.synthetic.jsonl").read_text(encoding="utf-8"), "",
                "a stopped run must not leave rows whose source index is wrong",
            )
            report = json.loads((out / "report.json").read_text(encoding="utf-8"))
            self.assertIn("changed while the run", report["stopped"])
            # Both digests, so the report of a stopped run cannot read as
            # though the file had been fine throughout.
            self.assertNotEqual(
                report["source"]["sha256_when_the_run_started"],
                report["source"]["sha256_when_it_finished"],
            )

    def test_too_many_unreadable_verdicts_stop_the_run(self):
        """Refusal 1's run-level half. Producing more rows nobody graded is not
        progress."""
        floor = driver.FEWEST_ROWS_BEFORE_A_SHARE_MEANS_ANYTHING
        replies = []
        for _ in range(floor + 4):
            replies.append(a_removal_for(0))
            replies.append("no verdict word here at all")
        box = support.sandbox(self)
        if True:
            source = box / "train.jsonl"
            # ONE source row, so one pure-removal rewrite fits every draw. With
            # the whole seed file the generator picks rows in its own order and
            # a rewrite written for one of them introduces every content word of
            # the others, so the validator refuses them and no verdict is ever
            # unreadable - the run would not stop, and the test would be
            # measuring the added-fact rule instead of the unreadable floor.
            source.write_text(A_SEED_FILE.splitlines()[0], encoding="utf-8")
            with self.assertRaises(driver.TheRunMustStop) as caught:
                driver.generate(
                    source=source, out_dir=box / "out",
                    how_many=floor + 4, model="scripted", base_url="x",
                    seed="s", question_field="instruction",
                    answer_field="response", degradation=driver.DEGRADATIONS[0],
                    adapter=ScriptedModel(replies), now=lambda: "n",
                )
            self.assertIn("unreadable", str(caught.exception))

    def test_a_few_unreadable_verdicts_in_a_short_run_do_not_stop_it(self):
        """Ten rows with one unreadable verdict is 10%, and stopping there
        would make the spec's own first run unrunnable."""
        box = support.sandbox(self)
        if True:
            source = box / "train.jsonl"
            source.write_text(A_SEED_FILE, encoding="utf-8")
            report = driver.generate(
                source=source, out_dir=box / "out", how_many=2,
                model="scripted", base_url="x", seed="s",
                question_field="instruction", answer_field="response",
                degradation=driver.DEGRADATIONS[0],
                adapter=ScriptedModel(
                    ["Orders ship within two working days.", "no verdict"]
                    + a_good_rewrite()
                ),
                now=lambda: "n",
            )
            self.assertIsNone(report["stopped"])
            self.assertEqual(report["judge"]["unreadable"], 1)


class TheControlGradesTwoRealAnswersTest(unittest.TestCase):
    """The runnable half of the spec's control, and it reads the other way.

    Two unrelated real answers are not a degradation of one another, so the
    judge should DROP them. A HIGH drop rate is the judge working. Every test
    here is written against that inverted sign, because a control whose
    direction a reader has to reconstruct is one that gets read backwards.
    """

    def rows(self):
        return [
            {"row_index": 0, "question": "q0", "answer": "answer zero, at length"},
            {"row_index": 1, "question": "q1", "answer": "answer one, at length"},
            {"row_index": 2, "question": "q2", "answer": "answer two, at length"},
        ]

    def test_every_row_is_paired_with_the_next_and_the_last_wraps(self):
        pairs = driver.pairs_that_are_two_real_answers(self.rows())
        self.assertEqual([p["row_index"] for p in pairs], [0, 1, 2])
        self.assertEqual([p["rejected_from_row_index"] for p in pairs], [1, 2, 0])

    def test_the_chosen_side_is_still_the_rows_own_answer(self):
        """So the validator's verbatim check is exercised unchanged rather
        than bypassed for the control."""
        pairs = driver.pairs_that_are_two_real_answers(self.rows())
        self.assertEqual(pairs[0]["chosen"], "answer zero, at length")
        self.assertEqual(pairs[0]["rejected"], "answer one, at length")

    def test_nothing_in_a_control_pair_was_written_by_a_model(self):
        rows = self.rows()
        real = {row["answer"] for row in rows}
        for pair in driver.pairs_that_are_two_real_answers(rows):
            with self.subTest(row=pair["row_index"]):
                self.assertIn(pair["chosen"], real)
                self.assertIn(pair["rejected"], real)

    def test_one_row_makes_no_pair_rather_than_pairing_it_with_itself(self):
        """A row against itself has no preference in it and would be dropped
        by the validator, which would read as a judge result."""
        self.assertEqual(driver.pairs_that_are_two_real_answers(self.rows()[:1]), [])

    def test_the_reading_says_a_low_number_is_the_judge_working(self):
        reading = driver.the_control_reading(kept=2, graded=40)
        self.assertEqual(reading["false_keep_rate"], 0.05)
        self.assertIn("A LOW number is the judge working", reading["read_it_this_way"])
        self.assertIn("FALSE-KEEP half only", reading["read_it_this_way"])

    def test_nothing_graded_is_no_rate_rather_than_a_perfect_score(self):
        """Zero kept out of zero graded is not a 0% false-keep rate."""
        reading = driver.the_control_reading(kept=0, graded=0)
        self.assertIsNone(reading["false_keep_rate"])
        self.assertIn("no rate", reading["read_it_this_way"])

    def run_control(self, replies, seed_text=A_SEED_FILE_THAT_NAMES_NOTHING):
        root = support.sandbox(self)
        source = root / "train.jsonl"
        source.write_text(seed_text, encoding="utf-8")
        model = ScriptedModel(replies)
        return driver.run_the_control(
            source=source, model="scripted", base_url="x",
            question_field="instruction", answer_field="response",
            degradation=driver.DEGRADATIONS[0], adapter=model,
        ), model

    def test_a_judge_that_drops_both_pairs_scores_zero_false_keeps(self):
        reading, model = self.run_control(
            ["These are unrelated answers, not a degradation.\nDROP"] * 2
        )
        self.assertEqual(len(model.asked), 2, "one judge call per row, no generator")
        self.assertEqual(reading["graded"], 2)
        self.assertEqual(reading["judge_kept"], 0)
        self.assertEqual(reading["false_keep_rate"], 0.0)

    def test_a_waved_through_pair_is_kept_with_the_judges_own_sentence(self):
        """The interesting rows in a control are the KEPT ones, which is the
        opposite of a generation run - so they are stored, not counted."""
        reading, _ = self.run_control([
            "This looks worse to me, so I will keep it.\nKEEP",
            "Unrelated, not a degradation.\nDROP",
        ])
        self.assertEqual(reading["judge_kept"], 1)
        self.assertEqual(len(reading["waved_through"]), 1)
        waved = reading["waved_through"][0]
        self.assertIn("I will keep it", waved["judge_said"])
        self.assertEqual(waved["row_index"], 0)
        self.assertEqual(waved["rejected_from_row_index"], 1)

    def test_a_real_pair_naming_nothing_new_reaches_the_judge(self):
        """A validator drop HERE would mean the validator is broken, not that
        the judge said anything - these two answers name no number, price, day
        or name the other does not."""
        reading, _ = self.run_control(["not a degradation.\nDROP"] * 2)
        self.assertEqual(reading["validator_dropped"], 0)
        self.assertEqual(reading["pairs_offered"], 2)
        self.assertEqual(reading["graded"], 2)

    def test_a_real_pair_that_names_a_new_number_never_reaches_the_judge(self):
        """THE NEW CHECK, IN THE CONTROL PATH. Two unrelated real answers
        usually name different numbers, and arithmetic settles those without
        spending a judge call on them. Measured over the owner's own 49 rows:
        28 of the 49 control pairs, and it changes what the control costs."""
        model = ScriptedModel([])
        root = support.sandbox(self)
        source = root / "train.jsonl"
        source.write_text(A_SEED_FILE, encoding="utf-8")
        reading = driver.run_the_control(
            source=source, model="scripted", base_url="x",
            question_field="instruction", answer_field="response",
            degradation=driver.DEGRADATIONS[0], adapter=model,
        )
        self.assertEqual(reading["validator_dropped"], 2)
        self.assertEqual(model.asked, [], "arithmetic should have settled these")
        self.assertIsNone(reading["false_keep_rate"])

    def test_the_validator_really_runs_and_costs_the_judge_nothing(self):
        """The assertion above cannot tell a validator that passed from one
        that never ran, because real pairs always pass it. This one can: two
        rows with the SAME answer make a pair with no preference in it, which
        the validator must drop before any judge call is spent on it."""
        twinned = "\n".join([
            json.dumps({"instruction": "q0", "response": "the very same answer"}),
            json.dumps({"instruction": "q1", "response": "the very same answer"}),
        ])
        reading, model = self.run_control([], seed_text=twinned)
        self.assertEqual(reading["validator_dropped"], 2)
        self.assertEqual(reading["graded"], 0)
        self.assertEqual(model.asked, [], "a pair with no preference cost a judge call")
        self.assertIsNone(reading["false_keep_rate"])

    def test_an_unreadable_verdict_is_counted_apart_from_a_drop(self):
        reading, _ = self.run_control([
            "no verdict word", "not a degradation.\nDROP",
        ])
        self.assertEqual(reading["unreadable"], 1)
        self.assertEqual(reading["graded"], 1)
        self.assertEqual(reading["judge_dropped"], 1)

    def test_a_seed_file_with_one_usable_row_stops_rather_than_reporting(self):
        with self.assertRaises(driver.TheRunMustStop) as caught:
            self.run_control([], seed_text=A_SEED_FILE.splitlines()[0])
        self.assertIn("fewer than two usable rows", str(caught.exception))



class TheReportSaysWhatTheJudgeDoesNotScreenForTest(unittest.TestCase):
    """A high judge pass rate does not mean the rows are faithful.

    `what_the_judge_is_shown` tells the judge, in as many words, that removing a
    condition or widening a limit IS the degradation and is never grounds to
    drop. So an over-promising row passes this filter BY DESIGN. A reader who
    takes `judge.pass_rate` for a faithfulness score is reading it wrong, and
    the report now says so in the same block as the number.

    Measured elsewhere on 2026-09-05: a separate faithfulness rubric went from
    4/9 to 9/9 on widened promises when one sentence about dropped limits was
    added. That clause must NOT come here - it would drop the pairs this corpus
    exists to produce.
    """

    def _report(self):
        return driver.the_kept_and_dropped_report(
            generated=10,
            validator_dropped={},
            judge_dropped=1,
            judge_unreadable=0,
            kept=9,
            distinct_sources=9,
            source_rows=49,
            control=None,
            generator_model="m",
            judge_model="j",
        )

    def test_the_judge_block_names_what_it_screens_for(self):
        judge = self._report()["judge"]
        self.assertIn("ADDED", judge["screens_for"])

    def test_the_judge_block_names_what_it_does_not_screen_for(self):
        judge = self._report()["judge"]
        self.assertIn("widened", judge["does_not_screen_for"])

    def test_the_note_is_stamped_stated_because_it_was_read_not_measured(self):
        self.assertTrue(self._report()["judge"]["provenance"].startswith("STATED"))

    def test_the_rubric_still_says_what_the_note_claims_it_says(self):
        """THE NOTE AND THE PROMPT MUST NOT DRIFT. If someone edits the rubric
        to drop widened promises, this note becomes a lie in a report that
        exists to be trusted - so the test reads the prompt, not a copy."""
        shown = driver.what_the_judge_is_shown(
            question="q", chosen="c", rejected="r",
            degradation=driver.DEGRADATIONS[0],
        )
        self.assertIn("NEVER ON WHAT WAS DROPPED", shown)



class TheDeterministicGatesRunBeforeTheJudgeTest(unittest.TestCase):
    """Wired 2026-09-05, after being measured on constructed rows.

    A reversed refusal and a rewrite that changed nothing of the named kind are
    both questions about two strings, and this judge has been measured
    answering both wrongly - keeping 3 of 6 inversions while narrating each as
    a deletion, and keeping 19 of 72 non-degradations while naming a clause the
    rewrite still contained. Neither gate is a rubric change.
    """

    #: A seed row of this suite's own, because the shared fixture's first row
    #: carries no refusal to invert and the test that needed one SKIPPED - a
    #: green suite with the case unrun, which is the shape of a test that is
    #: not there.
    A_ROW_WITH_A_REFUSAL = json.dumps({
        "instruction": "Can I return a book I have written in?",
        "response": "If it is unmarked and within 30 days, yes. Underlining "
                    "makes it unsellable, so those we cannot take back.",
    })

    def run_it(self, replies, *, enforce_clause_one=True, refuse_added_facts=True):
        root = support.sandbox(self)
        source = root / "train.jsonl"
        source.write_text(self.A_ROW_WITH_A_REFUSAL, encoding="utf-8")
        out = root / "out"
        model = ScriptedModel(replies)
        report = driver.generate(
            source=source, out_dir=out, how_many=1, model="scripted",
            base_url="http://127.0.0.1:0", seed="a-test",
            question_field="instruction", answer_field="response",
            degradation=driver.DEGRADATIONS[0], adapter=model,
            now=lambda: "2026-09-03 00:00:00",
            enforce_clause_one=enforce_clause_one,
            refuse_added_facts=refuse_added_facts,
        )
        return report, out, model

    def _the_real_answer(self):
        return json.loads(self.A_ROW_WITH_A_REFUSAL)["response"]

    def test_a_reversed_refusal_never_reaches_the_judge(self):
        """The generator returns the real answer with `cannot` flipped to
        `can`. One reply is scripted, so if the judge were asked the run would
        fail for want of a second."""
        flipped = self._the_real_answer().replace("cannot", "can")
        self.assertNotEqual(flipped, self._the_real_answer(), "no refusal to invert")
        report, out, model = self.run_it([flipped])
        self.assertEqual(report["kept"], 0)
        self.assertEqual(len(model.asked), 1, "the judge was asked anyway")
        self.assertTrue(
            any("reverses the refusal" in w
                for w in self.read(out, "dropped.jsonl")[0]["why"])
        )

    def test_a_rewrite_that_changed_nothing_of_the_named_kind_never_reaches_it(self):
        """A removed final full stop. 19 of 72 of these were KEPT by the judge
        with an invented deletion as the reason."""
        report, out, model = self.run_it([self._the_real_answer().rstrip(".")])
        self.assertEqual(report["kept"], 0)
        self.assertEqual(len(model.asked), 1)
        self.assertTrue(
            any("no judge is asked" in w
                for w in self.read(out, "dropped.jsonl")[0]["why"])
        )

    #: A rewrite of THIS test's source row that adds one content word - `always`
    #: - and nothing else. It drops the 30-day condition and then states the
    #: promise unconditionally, which is the named degradation carried past the
    #: line into an invention.
    #:
    #: IT HAD TO BE BUILT, NOT BORROWED, AND THAT IS THE POINT OF THIS COMMENT.
    #: The first version of this case pasted a bank-holiday rewrite - "including
    #: Christmas Day and Boxing Day" - onto a source row about returning books.
    #: That row IS refused, but by the OLDER specifics gate, which sees the
    #: names and numbers the rewrite invented: `Christmas`, `Boxing`, `Day`,
    #: `11`, `4`. So the case passed while proving nothing about the rule it was
    #: written for, AND WOULD HAVE GONE ON PASSING WITH THE ADDED-FACT RULE
    #: DELETED. A gate you cannot make fail is not a gate, and neither is a case
    #: that another gate answers first.
    #:
    #: Verified before use: refused by `a_rewrite_that_adds_a_fact`, and passed
    #: by `specifics_the_rewrite_adds`, the inverted-refusal check and the diff
    #: gate. The test below pins that by running the same row with the rule
    #: switched off and requiring it to reach the judge.
    A_REWRITE_THAT_ONLY_INVENTS = "If it is unmarked, yes. We can always take it back."

    def test_a_rewrite_that_invents_a_word_never_reaches_the_judge(self):
        """THE ROW THIS SHIPPED FOR, at zero judge calls.

        One reply is scripted, so if the judge were asked the run would fail for
        want of a second - which is how "zero calls" is asserted rather than
        assumed."""
        report, out, model = self.run_it([self.A_REWRITE_THAT_ONLY_INVENTS])
        self.assertEqual(report["kept"], 0)
        self.assertEqual(len(model.asked), 1, "the judge was asked anyway")
        why = self.read(out, "dropped.jsonl")[0]["why"]
        self.assertTrue(any("introduces content" in w for w in why), why)
        self.assertTrue(any("always" in w for w in why), why)

    def test_no_other_gate_would_have_caught_that_row(self):
        """THE CASE THAT MAKES THE CASE ABOVE MEAN SOMETHING. With the rule off,
        the same row reaches the judge - so the refusal above is the added-fact
        rule and not one of the gates that shipped before it.

        Without this, deleting the rule under test would leave the suite green.
        """
        _, _, model = self.run_it(
            [self.A_REWRITE_THAT_ONLY_INVENTS, "It is worse." + chr(10) + "KEEP"],
            refuse_added_facts=False,
        )
        self.assertEqual(
            len(model.asked), 2,
            "another gate refused this row, so the case above proves nothing "
            "about the added-fact rule",
        )

    def test_a_rewrite_that_only_removes_still_reaches_the_judge(self):
        """The rule must not refuse an ordinary deletion, which is the named
        degradation and the whole point of the corpus."""
        shorter = self._the_real_answer().replace(" and within 30 days", "")
        self.assertNotEqual(shorter, self._the_real_answer())
        _, _, model = self.run_it([shorter, "It is worse." + chr(10) + "KEEP"])
        self.assertEqual(len(model.asked), 2, "the judge was not asked")

    def test_the_added_fact_switch_restores_the_older_behaviour(self):
        """`refuse_added_facts=False` is the arm that measured the rule, kept
        so the trade can be re-measured rather than re-argued."""
        _, _, model = self.run_it(
            [self.A_REWRITE_THAT_ONLY_INVENTS, "It is worse." + chr(10) + "KEEP"],
            refuse_added_facts=False,
        )
        self.assertEqual(len(model.asked), 2)

    def test_the_switch_restores_the_shipped_behaviour_exactly(self):
        """The A arm of the preregistration needs the old path unchanged. With
        the gates off the same row reaches the judge, which is why a second
        reply is scripted here and not above."""
        _, _, model = self.run_it(
            [self._the_real_answer().rstrip("."), "It is worse." + chr(10) + "KEEP"],
            enforce_clause_one=False,
        )
        self.assertEqual(len(model.asked), 2, "the judge was not asked")

    def read(self, out, name):
        path = out / name
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


def _a_row_judged(judge: dict) -> dict:
    """A stamped row carrying one judge verdict. `why_this_row_must_not_ship`
    reads `provenance.judge`, not keyword arguments - the first version of
    these tests invented a signature and three of them errored."""
    return {"chosen": "a", "rejected": "b", "prompt": "q",
            "provenance": {"judge": judge}}


class TheReasoningFloorIsGoneAndStaysGoneTest(unittest.TestCase):
    """Removed 2026-09-05, measured rather than argued.

    It refused a row whose judge reasoning ran under forty characters, because
    "a verdict with no account is a verdict nobody can check". The account can
    be FABRICATED - 19 of 19 KEEPs in the sentinel-N run named a clause the
    rewrite still contained, none of them short - and across all 111 recorded
    `JUDGE_SYSTEM` replies the floor would have refused ZERO. Shortest reply 54
    characters; the 23 wrong verdicts ran 99 or more.

    This change stated its own test coverage wrong TWICE: first that no test
    asserted the floor, then that one did. TWO did, in two files, and the gate
    found the second. Both wrong counts came from grepping rather than
    enumerating the callers of `why_this_row_must_not_ship`.
    It caught the one case the 111 replies never contained, a reply of the
    single word KEEP, and it is retargeted rather than deleted: that row is
    still dropped, now for failing the rubric's format instead of a length.
    """

    def test_a_terse_verdict_is_no_longer_refused_for_being_terse(self):
        """Six characters of account, well under the old forty."""
        faults = driver.why_this_row_must_not_ship(
            _a_row_judged({"verdict": "DROP", "reasoning": "Worse."})
        )
        self.assertEqual(
            [f for f in faults if "reasoning" in f or "characters" in f], []
        )

    def test_an_unreadable_verdict_is_still_refused(self):
        """The other refusal in that function is untouched: a row nobody graded
        is still not a row that passed."""
        faults = driver.why_this_row_must_not_ship(
            _a_row_judged({"verdict": None, "reasoning": "a long and careful account"})
        )
        self.assertTrue(any("unreadable" in f for f in faults))

    def test_a_long_fabrication_was_never_caught_by_length(self):
        """The row the removal rests on: a real reply from the run, 137
        characters, naming a clause the rewrite still contains, verdict KEEP."""
        fabrication = (
            'The rewrite drops the "over 25.00" condition, making the '
            "recommendation unconditional, which is more permissive while "
            "retaining all original facts and numbers."
        )
        self.assertGreater(len(fabrication), 40)
        faults = driver.why_this_row_must_not_ship(
            _a_row_judged({"verdict": "KEEP", "reasoning": fabrication})
        )
        self.assertEqual([f for f in faults if "characters" in f], [])


if __name__ == "__main__":
    unittest.main()
