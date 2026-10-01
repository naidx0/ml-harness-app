"""`GET /api/next_step` answered an AI thread with a machine-learning card.

## The measurement, taken through the route

A conversation running `docs/ledgers/ai_engineering.yaml`, no facts recorded,
asking the product what it wants to know next. What came back, before
2026-08-27:

    outcome   BLOCKED__DEFINE_SUCCESS_FIRST
    verdict   BLOCKED
    question  classes_n - "say how much of this data is usable"
    because   S0_RULES_SUFFICE, stage_0_admissibility
    settled   assess_the_data, run as harness

Four wrong things and all of them confident. `BLOCKED__DEFINE_SUCCESS_FIRST`
is an outcome of the OTHER ledger's tree. `classes_n` is a fact this thread's
ledger has never heard of - the two shipped ledgers share not one fact name,
which `tests/test_a_tool_reads_the_ledger_its_thread_is_running.py` asserts
independently. `S0_RULES_SUFFICE` is a node in a document this conversation is
not running. And `assess_the_data` could not stamp anything on this thread if
the person did point it at a folder: migration v011's wall would refuse the
row, because a fact this ledger does not declare cannot be filed against it.

## It is Phase 0's own prediction, arriving on a route a person can open

`docs/PHASES.md` quotes the finding that started the whole ledger-per-thread
pass:

> "26 `default_spec()` call sites across 11 modules resolve to SPEC_PATH - the
>  ML ledger - unconditionally... **A second ledger will diagnose correctly and
>  then hand its verdict to a tool layer still reading the first ledger's
>  file.**"

`app/asking.py` is thirteen of those sites, and until this change its own
`_spec` docstring gave the reason: *"the product has one ledger"*. That
sentence was true when it was written and stopped being true at migration
`v011`. **A stale argument in a docstring is how a fixed defect stays fixed
only in the places somebody remembered.**

## Why it REFUSES rather than answering correctly

Answering correctly means threading a ledger through this module: eleven
functions and two dataclasses, one of which builds cards in `__post_init__`.
That is the real fix and it is written down as a bounded debt.

What may not wait for it is a confident wrong answer. So the boundary asks
which ledger the conversation is running, and where that is not the one
`asking.py` is written for it returns 409 with a sentence naming both files and
the route that does work - which is the shape `evidence.resolves` and
`propose.propose` already use for this exact situation: *the two states are told
apart and said out loud.*

## The control

`TheMachineLearningPathIsUntouchedTest` asks the same route on a thread running
the ML ledger, and on no thread at all, and requires a real card back. A
boundary that refused both would be a fix that broke the product.
"""

from __future__ import annotations

import unittest

from fastapi import HTTPException

from app import diagnosis, events, main
from app.tools import evidence

AI_LEDGER = "docs/ledgers/ai_engineering.yaml"
ML_LEDGER = "docs/diagnosis_engine.yaml"


class TheWrongDomainIsRefusedTest(unittest.TestCase):
    def setUp(self):
        import support

        support.sandbox(self)
        self.ai = int(events.create_thread("an agent that fails", ledger=AI_LEDGER)["id"])

    def test_the_premise_this_test_rests_on(self):
        """The thread really is running the other ledger, and the module this
        route uses really does read only the first one. A test that asserted a
        refusal without establishing both would pass against a route that
        refuses everything."""
        self.assertEqual(AI_LEDGER, evidence.ledger_for_thread(self.ai).as_written)
        self.assertEqual(ML_LEDGER, diagnosis.default_spec().as_written)

    def test_it_refuses_instead_of_answering(self):
        with self.assertRaises(HTTPException) as caught:
            main.next_step_ep(thread_id=self.ai)
        self.assertEqual(409, caught.exception.status_code)

    def test_the_refusal_names_both_ledgers_and_a_route_that_works(self):
        """A wall with no door is a person told 'no' and left there."""
        with self.assertRaises(HTTPException) as caught:
            main.next_step_ep(thread_id=self.ai)
        said = str(caught.exception.detail)
        self.assertIn(AI_LEDGER, said)
        self.assertIn(ML_LEDGER, said)
        self.assertIn("run_diagnosis", said)

    def test_nothing_is_recorded_by_the_refusal(self):
        with self.assertRaises(HTTPException):
            main.next_step_ep(thread_id=self.ai)
        self.assertEqual([], evidence.rows_for(self.ai))

    def test_the_card_it_would_have_served_is_the_one_named_in_the_docstring(self):
        """THE DEFECT ITSELF, RUN, so this file cannot go green because the
        attack became impossible. The old route was `diagnose(sheet)` with no
        spec followed by `asking.next_step`; both are still callable, so the
        wrong answer is still constructible - and constructing it is what shows
        the refusal above is refusing something real."""
        from app import asking

        sheet, _trail = evidence.assemble_facts(self.ai, {}, evidence.USER)
        would_have = asking.next_step(result=diagnosis.diagnose(sheet)).as_dict()

        self.assertEqual("BLOCKED__DEFINE_SUCCESS_FIRST", would_have["outcome"])
        question = would_have.get("question") or {}
        # It was `classes_n` until 2026-09-19, when the asker stopped reading
        # facts the condition merely MENTIONS and started reading the ones it
        # reached. The wrong-domain card the old route builds is `target_score`
        # now; what this test is about is that the card is built out of the ML
        # ledger for a thread running the AI one, whatever the fact is called.
        self.assertEqual("target_score", question.get("fact"))

        # And every one of those names is foreign to the thread it was for.
        ai = diagnosis.spec_at(AI_LEDGER)
        self.assertNotIn(question.get("fact"), ai.facts)
        self.assertNotIn("classes_n", ai.facts)
        self.assertNotIn("BLOCKED__DEFINE_SUCCESS_FIRST", set(ai.declared_outcomes()))

    def test_the_tool_that_card_named_could_not_have_helped_either(self):
        """The second half of the wrongness, and the one that would have cost
        the person their afternoon: they point at a folder, the tool runs, and
        migration v011's wall refuses the row - because a fact this ledger does
        not declare cannot be filed against it."""
        instrument = evidence.instrument_for(
            tool="assess_the_data",
            measures=("classes_n",),
            provides=("data.dataset.assess",),
            thread_id=self.ai,
            ledger=evidence.ledger_for_thread(self.ai),
        )
        with self.assertRaises(evidence.MeasurementError) as caught:
            instrument.measured("classes_n", 4, how="counted the label column")
        self.assertIn("declares no such fact", str(caught.exception))


class TheMachineLearningPathIsUntouchedTest(unittest.TestCase):
    """The control. A boundary that refused everything would be worse than the
    defect, because the defect at least served the ML threads correctly."""

    def setUp(self):
        import support

        support.sandbox(self)

    def test_a_thread_on_the_first_ledger_still_gets_a_card(self):
        thread = int(events.create_thread("an ordinary conversation")["id"])
        got = main.next_step_ep(thread_id=thread)
        self.assertEqual(thread, got["thread_id"])
        self.assertEqual("question", got["step"]["kind"])
        self.assertTrue(got["step"]["question"]["fact"])

    def test_no_thread_at_all_still_gets_the_first_question(self):
        """`thread_id` is optional on this route on purpose - "what would you
        ask me first" is an honest question with no conversation open - and the
        check must not have taken that away."""
        got = main.next_step_ep()
        self.assertIsNone(got["thread_id"])
        self.assertEqual("question", got["step"]["kind"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
