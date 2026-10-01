"""The harness stops making a person learn an argument by failing.

Driving the intake end to end for the architecture-JSON task - a person
attaching `Qwen2.5-Coder-1.5B-Instruct` and saying what they want - the harness
demands **three** decisions before it stops asking:

    1. classes_n     settled by assess_the_data   point_at ['path']
    2. target_score  the person's own answer
    3. eval_size_n   settled by measure_eval_set  point_at ['path']

and then blocks on BLOCKED__BUILD_EVAL_SET. Two of the three are properties of
the same file; only `target_score` is genuinely the person's.

## The one this removes, and it is a decision made by failing

`point_at` is built from `slot.required`, which is a property of the SCHEMA.
`assess_the_data` requires only `path` - so a caller does exactly what it was
told, and **nothing is stamped**, because classes are counted only when
`label_column` names the column. The tool is not at fault: told nothing, it
reports a guess as a guess and its reply names the argument that would turn the
guess into a count. But the frontier asks the same question again, and from the
outside *"you have not pointed at anything"* and *"you pointed and it did not
count"* are the same sentence.

Measured: two calls to settle `classes_n`, the first spent learning what the
second needs. With the optional arguments named up front, one.

## What it is careful not to claim

They are NOT promoted into `point_at`. They are not required, and calling them
required would be a different lie - a caller whose data has no label column
would be told to supply one that does not exist. They are offered beside it,
under a name that says what they do, which is what the `slots` list already
carried and no consumer was reading.
"""

from __future__ import annotations

import shutil
import unittest

import support

from app import asking, events
from app.tools import REGISTRY, evidence


class ThePointerOffersWhatTheMeasurementNeedsTest(unittest.TestCase):
    """Read off the real ledger and the real registry."""

    def test_the_optional_arguments_are_named(self):
        offered = asking.question_for("classes_n").accepts
        self.assertIn("label_column", offered["and_these_change_the_answer"])

    def test_they_are_not_promoted_into_point_at(self):
        """`label_column` is optional in the schema and saying otherwise would
        tell somebody with no label column to invent one."""
        offered = asking.question_for("classes_n").accepts
        self.assertNotIn("label_column", offered["point_at"])

    def test_classes_n_no_longer_demands_a_path_up_front(self):
        """CHANGED BY A PERSON USING THE PRODUCT, 2026-09-10.

        This asserted `point_at == ["path"]` for `classes_n`, and that was the
        pointer faithfully reporting a demand the product should not have been
        making. Walking the intake with a model attached, Max reached this
        question and could not answer it: *"it says, how much of this data is
        usable? A tool has to run and asks for a path where the data is
        sitting. I have no idea ... ml_harness.db could be it, test scripts,
        I'm not really sure."*

        `assess_the_data` looks now - every `.jsonl` and `.csv` under `evals/`
        and `runs/`, with the rows it counted - so `path` is optional and the
        pointer stops naming it as something the caller must supply first. What
        `point_at` reports did not get worse; the demand behind it went away.

        `eval_size_n` still names its path, and that is the control below: this
        is one tool changing, not the pointer losing the ability to say what a
        measurement needs.
        """
        self.assertEqual([], asking.question_for("classes_n").accepts["point_at"])

    def test_the_required_argument_is_still_where_it_was(self):
        """The new key is additive. A consumer reading `point_at` alone reads
        exactly what it read before - for a tool that still requires one."""
        self.assertEqual(
            asking.question_for("eval_size_n").accepts["point_at"], ["path"]
        )

    def test_a_tool_with_no_optional_arguments_offers_an_empty_list(self):
        """Not a missing key - a consumer must not have to test for absence."""
        offered = asking.question_for("eval_size_n").accepts
        self.assertIsInstance(offered["and_these_change_the_answer"], list)

    def test_the_two_lists_never_overlap(self):
        """Required and optional are a partition of the slots, so a caller
        reading both sees every argument exactly once."""
        for fact in ("classes_n", "eval_size_n"):
            with self.subTest(fact=fact):
                accepts = asking.question_for(fact).accepts
                both = set(accepts["point_at"]) & set(
                    accepts["and_these_change_the_answer"]
                )
                self.assertEqual(both, set())


class ItSavesTheCallThatOnlyTeachesTest(unittest.TestCase):
    """THE MEASUREMENT, through the registry, on the real eval set."""

    def setUp(self):
        self.root = support.sandbox(self)
        self.data = self.root / "held-out.jsonl"
        shutil.copy(
            support.REPO_ROOT / "evals" / "architecture-json" / "held-out.jsonl",
            self.data,
        )

    def calls_to_settle(self, *, read_the_new_field: bool) -> int:
        thread = int(events.create_thread("intake", None)["id"])
        offered = asking.question_for("classes_n").accepts
        arguments = {"path": str(self.data)}
        if read_the_new_field and "label_column" in offered["and_these_change_the_answer"]:
            arguments["label_column"] = "expected"
        for attempt in range(1, 4):
            out = REGISTRY.call(
                "assess_the_data", arguments, actor=evidence.USER, thread_id=thread
            )
            if [row["fact"] for row in (out.get("measured_facts") or [])]:
                return attempt
            #: What the tool's own reply teaches a caller who did not know.
            arguments["label_column"] = "expected"
        return 99

    def test_a_caller_reading_only_point_at_spends_a_call_learning(self):
        self.assertEqual(self.calls_to_settle(read_the_new_field=False), 2)

    def test_a_caller_reading_the_new_field_settles_it_first_time(self):
        self.assertEqual(self.calls_to_settle(read_the_new_field=True), 1)

    def test_and_the_fact_that_lands_is_the_same_either_way(self):
        """One call or two, the answer is identical - this removes a round trip
        and not a check."""
        thread = int(events.create_thread("intake", None)["id"])
        REGISTRY.call(
            "assess_the_data",
            {"path": str(self.data), "label_column": "expected"},
            actor=evidence.USER,
            thread_id=thread,
        )
        sheet, _ = evidence.assemble_facts(thread, {}, evidence.USER)
        self.assertIsNotNone(sheet.get("classes_n"))
        self.assertGreater(sheet["classes_n"].value, 0)


class TheIntakeDemandsTwoDecisionsTest(unittest.TestCase):
    """Recorded so a third is a red test rather than a slow afternoon.

    IT WAS THREE, AND THE THIRD WAS A QUESTION THE WALK NEVER ASKED. The
    intake opened with `classes_n` on a thread that had not said what kind of
    task it was. `S0_RULES_SUFFICE` reads `task_family in {extraction,
    classification} and ... classes_n <= 5`; with the family unknown the `and`
    answers False at the first operand and the class count is never looked at.
    The asker built its question from a PARSE of that condition, which names
    every operand, so a person attaching a dataset was asked to count label
    classes before anything had established there were labels.

    Max, 2026-09-19, after that question ate forty minutes of a real run:
    *"Stop just saying not-work."* Two now, and the one that is his own is
    still exactly one.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        self.data = self.root / "held-out.jsonl"
        shutil.copy(
            support.REPO_ROOT / "evals" / "architecture-json" / "held-out.jsonl",
            self.data,
        )
        self.thread = int(events.create_thread("attach and go", None)["id"])

    def test_three_and_only_one_of_them_is_the_persons_own(self):
        from app import conductor

        stated = {
            "goal_text": "a coding model that emits architecture graphs as JSON",
            "target_score": 0.85,
        }
        asked = []
        for _ in range(12):
            out = REGISTRY.call(
                "what_is_missing", {}, actor=evidence.USER, thread_id=self.thread
            )
            question = out.get("question") or {}
            fact = question.get("fact")
            if not fact:
                break
            asked.append(fact)
            tool = (question.get("accepts") or {}).get("measured_by")
            if fact in stated:
                REGISTRY.call(
                    "state_facts",
                    {"facts": {fact: stated[fact]}},
                    actor=evidence.USER,
                    thread_id=self.thread,
                )
                continue
            arguments = {"path": str(self.data)}
            if tool == "assess_the_data":
                arguments["label_column"] = "expected"
            REGISTRY.call(tool, arguments, actor=evidence.USER, thread_id=self.thread)

        self.assertEqual(asked, ["target_score", "eval_size_n"])
        self.assertNotIn(
            "classes_n", asked,
            "the class count is a question about a branch this thread never took",
        )
        outcome = (conductor._standing_diagnosis(self.thread) or {}).get("outcome")
        self.assertEqual(outcome, "BLOCKED__BUILD_EVAL_SET")


if __name__ == "__main__":
    unittest.main()
