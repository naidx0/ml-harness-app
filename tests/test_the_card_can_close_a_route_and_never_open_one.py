"""The card may refuse a model. It may never recommend one.

## What this is for

The intake walk for a 1.5B and a 7B model, same task and same data, was
step-for-step identical - four decisions, one outcome - because nothing in it
read a model config, a parameter count or the card.
`can_this_machine_train` knew the whole time: YES needing 3.80 GiB with 4.20
spare for `Qwen2.5-Coder-1.5B-Instruct`, NO needing 7.94 with 0.06 for the 7B,
which fits at sequence 1472. It declared `measures=()` and so nothing it
computed could reach a node.

`measures=()` is a wall and it is right. `app/tools/feasible.py` argues that a
CAN question must never become a SHOULD - AGENTS.md invariant 4 - and
`tests/test_a_can_question_is_not_a_train_recommendation.py` holds it. **This
file does not weaken that. It adds the other half.**

## The rule

A **closure** may enter the ledger; a permission may not. `cannot_train_here` is
stamped only on a NO, carries the margin and the longest example that fits, and
is read by one node that can only refuse. There is no `can_train_here` fact and
there must not be.

## Why a second tool rather than a flag on the first

A tool whose `measures=` names a thread-scoped fact is REQUIRED to have a thread
(`evidence.thread_is_required_by`). `can_this_machine_train` answers on an empty
ledger with no conversation, and that is the defect its module was written to
close: Max asked seven questions and was refused six for want of a precondition.
Stamping from it would put the precondition back and break
`test_an_empty_ledger_still_gets_a_yes_or_a_no`. So the CAN tools keep
`measures=()` byte for byte, and `record_that_this_card_refuses` - which a walk
calls, and a walk always has a thread - carries the closure.
"""

from __future__ import annotations

import unittest

import support

import diagnosis_fixtures as fixtures

from app import events
from app import diagnosis as diagnosis_module
from app.diagnosis import default_spec, diagnose
from app.tools import REGISTRY, evidence

SPEC = default_spec()

SMALL = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
BIG = "Qwen/Qwen2.5-Coder-7B-Instruct"

THE_CLOSURE = ("cannot_train_here", "training_headroom_gb", "longest_fitting_seq")


class TheWallIsStillThereTest(unittest.TestCase):
    """The CAN tools were not touched, and this file's premise is that."""

    def test_the_can_tools_still_stamp_nothing(self):
        for name in ("can_this_machine_train", "where_to_train"):
            with self.subTest(tool=name):
                self.assertEqual((), REGISTRY.get(name).measures)

    def test_the_recorder_is_a_different_tool(self):
        self.assertIsNotNone(REGISTRY.get("record_that_this_card_refuses"))

    def test_there_is_no_permission_fact_in_the_ledger(self):
        """THE RULE, asserted where somebody would add the symmetric fact.
        `can_train_here` would be a permission, and a permission is what the
        wall exists to keep out of the ledger."""
        for forbidden in ("can_train_here", "training_is_permitted", "card_permits"):
            with self.subTest(fact=forbidden):
                self.assertNotIn(forbidden, SPEC.facts)

    def test_the_closure_facts_are_declared(self):
        for fact in THE_CLOSURE:
            with self.subTest(fact=fact):
                self.assertIn(fact, SPEC.facts)


class AYesRecordsNothingAtAllTest(unittest.TestCase):
    """THE SEVENTH CASE. A fact stamped on a YES is a fact a planner reads as
    permission, and that is the whole of what the separation forbids."""

    def setUp(self):
        support.sandbox(self)
        self.thread = int(events.create_thread("can it", None)["id"])

    def ask(self, repo, seq_len=2048):
        return REGISTRY.call(
            "record_that_this_card_refuses",
            {"repo_id": repo, "method": "qlora", "seq_len": seq_len},
            actor=evidence.USER,
            thread_id=self.thread,
        )

    def test_a_yes_stamps_no_fact(self):
        out = self.ask(SMALL)
        self.assertEqual(out.get("answer"), "YES")
        self.assertEqual(out.get("recorded"), [])
        sheet, _ = evidence.assemble_facts(self.thread, {}, evidence.USER)
        for fact in THE_CLOSURE:
            with self.subTest(fact=fact):
                self.assertIsNone(sheet.get(fact))

    def test_a_yes_says_why_it_recorded_nothing(self):
        """Silence would read as a failure. It is a rule, so it is stated."""
        self.assertIn("only a refusal", self.ask(SMALL)["why_nothing_was_recorded"].lower())

    def test_a_no_stamps_the_closure_and_the_margin(self):
        """TWO FACTS SINCE 2026-09-10, NOT THREE, AND THE THIRD IS ABSENT FOR
        A REASON THE ANSWER STATES.

        The estimator's measured terms put `Coder-7B` beyond this card BEFORE
        any example is loaded, so the search for a longest fitting length
        returns nothing - there is no length to record. That is a STRONGER
        refusal than the one this test was written against, where the model
        missed by 0.52 GiB and fitted at 1,730 tokens.

        A missing field would read as a measurement that failed, so the answer
        carries `no_length_fits` saying which of the two it is.
        """
        out = self.ask(BIG)
        self.assertEqual(out.get("answer"), "NO")
        self.assertEqual(
            sorted(out["recorded"]),
            sorted(("cannot_train_here", "training_headroom_gb")),
        )
        self.assertIn("No sequence length fits", out["no_length_fits"])
        sheet, _ = evidence.assemble_facts(self.thread, {}, evidence.USER)
        self.assertIs(sheet["cannot_train_here"].value, True)
        self.assertIsNone(sheet.get("longest_fitting_seq"))

    def test_a_refusal_that_still_has_a_length_records_all_three(self):
        """THE CONTROL, and it is what keeps the case above from being a claim
        that the third fact is never stamped. A model that misses by a margin
        a shorter example would close still gets its length recorded."""
        thread = int(events.create_thread("shorter", None)["id"])
        out = REGISTRY.call(
            "record_that_this_card_refuses",
            {"repo_id": SMALL, "method": "qlora", "seq_len": 32768},
            actor=evidence.USER,
            thread_id=thread,
        )
        if out.get("answer") != "NO":
            self.skipTest("the small model fits even at 32k on this card")
        self.assertEqual(sorted(out["recorded"]), sorted(THE_CLOSURE))
        self.assertNotIn("no_length_fits", out)

    def test_the_margin_is_recorded_and_not_only_the_refusal(self):
        """NO by 0.06 and NO by 3.4 are different facts wearing one word. The
        first is a sequence length away from yes."""
        self.ask(BIG)
        sheet, _ = evidence.assemble_facts(self.thread, {}, evidence.USER)
        self.assertIsNotNone(sheet.get("training_headroom_gb"))

    def test_it_arrives_measured(self):
        self.ask(BIG)
        sheet, _ = evidence.assemble_facts(self.thread, {}, evidence.USER)
        from app import diagnosis

        self.assertEqual(sheet["cannot_train_here"].origin, diagnosis.MEASURED)


class TheCardsNoComesBeforeTheQuestionsThatAssumeAYesTest(unittest.TestCase):
    """A refusal must not require doing the impossible first.

    `S9_THE_CARD_CANNOT` sits after the gates, and for a model the card can hold
    that is right. For a model it has REFUSED it is unreachable: the baseline
    those gates demand would have to be measured on the very model that will not
    load. So a recorded closure is consulted at stage 0, before any of it.
    """

    def setUp(self):
        support.sandbox(self)

    def thread_for(self, repo):
        thread = int(events.create_thread(repo, None)["id"])
        REGISTRY.call(
            "record_that_this_card_refuses",
            {"repo_id": repo, "method": "qlora", "seq_len": 2048},
            actor=evidence.USER,
            thread_id=thread,
        )
        return thread

    def walk(self, thread):
        return REGISTRY.call(
            "run_diagnosis", {"facts": {}}, actor=evidence.USER, thread_id=thread
        ).get("outcome")

    def test_a_refused_model_reaches_the_refusal_with_no_baseline(self):
        """THE CASE. Nothing has been measured on this thread but the card's
        answer, and that is the point."""
        self.assertEqual(
            self.walk(self.thread_for(BIG)), "NO_TRAIN__WONT_FIT_THIS_MACHINE"
        )

    def test_a_model_that_fits_still_has_to_define_success_first(self):
        """THE CONTROL, and it is what stops this being a bypass. A YES stamps
        nothing, so a thread about a model that fits has no closure to match and
        walks into the gates exactly as it did before."""
        self.assertEqual(
            self.walk(self.thread_for(SMALL)), "BLOCKED__DEFINE_SUCCESS_FIRST"
        )

    def test_a_caller_who_asserts_the_closure_is_not_routed(self):
        """RC10_AN_ASSERTION_NEVER_MINTS, at the one node that reads an origin.

        `state_facts` RECORDS `cannot_train_here` at a caller's origin - it says
        "cannot, at this origin" and keeps the row, because a sheet that drops
        what somebody said cannot explain itself. So the value reaches the sheet
        with no tool having run, and a condition reading the bare value would
        let a thread assert its own refusal and skip every gate. Harmless in
        outcome, since a closure only closes - and still a walk deciding on
        somebody's say-so.
        """
        thread = int(events.create_thread("asserted", None)["id"])
        said = REGISTRY.call(
            "state_facts",
            {"facts": {"cannot_train_here": True}},
            actor=evidence.USER,
            thread_id=thread,
        )
        self.assertTrue(said.get("ok"), "the row is kept, not refused")
        sheet, _ = evidence.assemble_facts(thread, {}, evidence.USER)
        self.assertIs(sheet["cannot_train_here"].value, True)
        self.assertNotEqual(sheet["cannot_train_here"].origin, diagnosis_module.MEASURED)
        #: On the sheet, and NOT routed.
        self.assertEqual(self.walk(thread), "BLOCKED__DEFINE_SUCCESS_FIRST")

    def test_the_node_asks_for_the_origin_and_not_only_the_value(self):
        """Read off the ledger, so removing `measured()` from the condition is a
        red test rather than a silent widening."""
        import ast as _ast

        condition = SPEC.conditions["S0_THE_CARD_ALREADY_SAID_NO"]
        calls = {
            node.func.id
            for node in _ast.walk(condition)
            if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name)
        }
        self.assertIn("measured", calls)


class TheTwoWalksDivergeTest(unittest.TestCase):
    """One node, and it is the only place they differ."""

    def walk(self, **extra):
        facts = dict(fixtures.MINTING["TRAIN__LORA_SFT"])
        if extra:
            facts.update(fixtures.attribute(extra))
        return diagnose(facts, SPEC)

    def test_a_thread_the_card_refused_stops_recommending(self):
        refused = self.walk(cannot_train_here=True)
        #: ONE NODE, NOT TWO. This asserted `S9_THE_CARD_CANNOT` until the
        #: closure moved ahead of the gates - for a refused model the stage-9
        #: node was unreachable, because the baseline the gates before it demand
        #: would have to be measured on the model that will not load. Two nodes
        #: for one outcome with the earlier always winning is dead code, so the
        #: stage-9 one was removed rather than left to look like a second route.
        self.assertEqual(refused.node, "S0_THE_CARD_ALREADY_SAID_NO")
        self.assertEqual(refused.outcome, "NO_TRAIN__WONT_FIT_THIS_MACHINE")

    def test_a_thread_that_never_asked_walks_exactly_as_before(self):
        """THE CONTROL. If this changed, the node would be refusing threads on
        the absence of a fact rather than on a recorded closure."""
        self.assertEqual(self.walk().outcome, "TRAIN__LORA_SFT")

    def test_a_false_closure_is_not_a_refusal_either(self):
        """Nothing stamps False today, and if something ever does it must not
        read as a refusal."""
        self.assertEqual(self.walk(cannot_train_here=False).outcome, "TRAIN__LORA_SFT")

    def test_the_refusal_names_the_margin_as_the_thing_to_read(self):
        said = self.walk(cannot_train_here=True).say or ""
        self.assertIn("longest example", said)
        self.assertIn("margin", said)

    def test_it_removes_an_option_and_proposes_nothing(self):
        """A closure closes. It must not arrive carrying a different method to
        try, which would be the CAN answer recommending after all."""
        refused = self.walk(cannot_train_here=True)
        self.assertTrue(refused.outcome.startswith("NO_TRAIN__"))


if __name__ == "__main__":
    unittest.main()
