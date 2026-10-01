"""The harness has a tool that says what it still needs, and a model is offered it.

## The complaint, and the mechanism under it

The owner: *"right now it kind of throws tools in your face, but I kind of want
it a little more simplified. You literally attach a model to it, and we're
training it."*

MEASURED 2026-09-09, and the finding is not the one the task began with. The
intake was not missing. `app/asking.py` - 1,357 lines - already derives THE
question that would move a stopped diagnosis: which fact, what kind of answer it
takes, which node or gate it unblocks in the ledger's own words, and for a
`source: inspect` fact THE TOOL THAT MEASURES IT rather than a field to type in.
It has been served at `GET /api/next_step` since it was written.

**It was not a tool.** 67 registered, all 67 offered to a model, and not one of
them the asker. So a model ran `run_diagnosis`, got five gates reading
NOT_REACHED, and had sixty-seven doors and no way to learn which one. That is the
whole of "it throws tools in your face": the intake was built and unreachable
from the surface a model actually sees.

So this ships one registration, not new machinery - and these tests are about
REACHABILITY as much as behaviour, because reachability was the defect.
"""

from __future__ import annotations

import unittest

import support

from app import diagnosis
from app import tools


class TheAskerIsOfferedToAModelTest(unittest.TestCase):
    """THE CASE, and it is the one that was false before this change."""

    def test_it_is_registered(self):
        self.assertIn("what_is_missing", tools.REGISTRY.names())

    def test_a_model_is_offered_it(self):
        """REGISTERED IS NOT OFFERED, and the two are separate lists. A tool a
        model never sees is a route with extra steps - which is exactly what
        `GET /api/next_step` was."""
        #: OpenAI-style function schemas: {"type": "function", "function": {...}}.
        #: The first version read `.get("name")` off the outer dict and got a set
        #: containing only `None` - a check that would have passed for no tool at
        #: all if the assertion had been `assertNotIn`.
        offered = tools.REGISTRY.model_tools()
        names = {entry["function"]["name"] for entry in offered}
        self.assertIn("what_is_missing", names)
        self.assertGreater(len(names), 60, "the offered list collapsed")

    def test_it_is_offered_before_the_diagnosis(self):
        """A caller who runs the diagnosis first gets five NOT_REACHED gates and
        nothing to do about it. Order decides which one they meet."""
        #: `order` is a control field, not a `ToolSpec` attribute.
        asker = tools.REGISTRY.get("what_is_missing").as_control()
        diagnose = tools.REGISTRY.get("run_diagnosis").as_control()
        self.assertLess(asker["order"], diagnose["order"])


class ItAsksForOneThingAndSaysWhereTheAnswerGoesTest(unittest.TestCase):
    """A card, not a form and not a paragraph."""

    def setUp(self):
        #: `sandbox(self)` because this reads the thread's ledger rows, and a
        #: test that read the developer's real database would answer about their
        #: project. The house fixture, not one invented here - it takes the test
        #: and binds six globals, rather than being a context manager.
        support.sandbox(self)

    def call(self, thread_id=None):
        return tools.REGISTRY.call(
            "what_is_missing", {}, actor="user", thread_id=thread_id
        )

    def test_an_empty_thread_gets_exactly_one_question(self):
        out = self.call()
        self.assertTrue(out.get("ok"), out)
        question = out.get("question")
        self.assertIsInstance(question, dict, "no question was offered")
        self.assertIn("fact", question)

    def test_the_question_names_the_tool_that_would_settle_it(self):
        """For a `source: inspect` fact there is no field to type into - there
        is a tool and something to point it at. That distinction is the whole
        reason the prose round-trip lost provenance."""
        out = self.call()
        question = out["question"]
        if question["arrives_as"] == "MEASURED":
            self.assertTrue(
                (question.get("accepts") or {}).get("measured_by"),
                "a measured fact was offered with no tool to measure it",
            )
        self.assertIn("answer_through", out)
        self.assertTrue(out["answer_through"]["tool"])

    def test_it_takes_no_arguments_at_all(self):
        """STRUCTURAL, NOT TIDY. A caller who could pass facts here could move
        the frontier by asserting things and so choose which question the person
        is shown. Facts go in through `state_facts` and `run_diagnosis`, where
        the boundary decides what a caller's word is worth."""
        spec = tools.REGISTRY.get("what_is_missing")
        self.assertEqual(spec.schema.get("properties"), {})
        self.assertFalse(spec.schema.get("additionalProperties", True))

    def test_it_decides_nothing_and_stamps_nothing(self):
        spec = tools.REGISTRY.get("what_is_missing")
        self.assertEqual(tuple(spec.writes), ())
        self.assertEqual(tuple(spec.measures), ())


class TheLoopActuallyAdvancesTest(unittest.TestCase):
    """An asker that asks the same thing forever is worse than none - it looks
    like progress. This drives the loop the way a model would."""

    ANSWERS = {
        "classes_n": 12,
        "goal_text": "a support chatbot that answers from our docs",
        "target_score": 0.8,
        "eval_size_n": 60,
        "baseline_score": 0.42,
        "baseline_measured": True,
        "labeled_examples_n": 800,
    }

    def walk(self, limit: int = 10):
        from app import asking

        facts: dict = {}
        asked: list[str] = []
        for _ in range(limit):
            step = asking.next_step(facts).as_dict()
            question = step.get("question")
            if not question:
                return asked, step.get("outcome")
            fact = question["fact"]
            asked.append(fact)
            if fact not in self.ANSWERS:
                return asked, step.get("outcome")
            facts[fact] = self.ANSWERS[fact]
        self.fail(f"the intake did not terminate in {limit} questions: {asked}")

    def test_it_never_asks_the_same_fact_twice(self):
        asked, _ = self.walk()
        self.assertEqual(len(asked), len(set(asked)), f"repeated a question: {asked}")

    def test_it_reaches_an_outcome_that_is_not_the_starting_block(self):
        """THE VERIFICATION THAT MATTERS. Before this, a thread sat at
        BLOCKED__DEFINE_SUCCESS_FIRST with nothing offering a way out."""
        _, outcome = self.walk()
        self.assertIsNotNone(outcome)
        self.assertNotEqual(outcome, "BLOCKED__DEFINE_SUCCESS_FIRST")

    def test_it_takes_a_handful_of_questions_and_not_a_form(self):
        """The complaint was that the harness throws everything at you. Fifteen
        facts are declared `source: ask` without a default; an intake that asked
        for all of them would be the same failure with better manners."""
        asked, _ = self.walk()
        self.assertLessEqual(len(asked), 6, f"that is a form, not a conversation: {asked}")


class ItRefusesAThreadRunningAnotherLedgerTest(unittest.TestCase):
    """`asking.py` is written for one ledger and says so.

    `GET /api/next_step` already refuses this, because before 2026-08-27 it
    ANSWERED one: an AI-engineering thread got an outcome from the ML tree, a
    fact its ledger has never heard of, and a card naming a tool that could not
    measure anything in it. A tool is a wider door than a route, so it refuses
    on the same terms rather than a looser set.
    """

    def test_the_refusal_exists_in_the_tool_and_not_only_in_the_route(self):
        source = (support.REPO_ROOT / "app" / "tools" / "__init__.py").read_text(
            encoding="utf-8"
        )
        body = source[source.index("def what_is_missing"):]
        body = body[: body.index("@tool(")] if "@tool(" in body else body
        self.assertIn("wrong_ledger", body)
        self.assertIn("default_spec()", body)

    def test_it_names_what_to_run_instead(self):
        """A refusal that names nothing costs a round and teaches nothing."""
        source = (support.REPO_ROOT / "app" / "tools" / "__init__.py").read_text(
            encoding="utf-8"
        )
        body = source[source.index("def what_is_missing"):]
        self.assertIn("run_diagnosis", body[: body.index("try:")])


class TheCapabilityIsDeclaredTest(unittest.TestCase):
    """The registry refuses a capability the engine does not publish, and it is
    right to - a misspelling that became a new capability would be a pack nobody
    can ask for."""

    def test_the_capability_is_published(self):
        from app.tools import blocks

        self.assertIn("ledger.asking.next_step", blocks.CAPABILITIES)

    def test_it_carries_a_gloss(self):
        from app.tools import blocks

        self.assertGreater(len(blocks.CAPABILITIES["ledger.asking.next_step"]), 20)


if __name__ == "__main__":
    unittest.main()
