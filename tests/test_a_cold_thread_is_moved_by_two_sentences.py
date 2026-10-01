"""A cold thread stops asking for a definition once a person supplies one.

MEASURED 2026-09-09 against the running engine on 8078, thread 51, every call
through `POST /api/tools/{name}` and nothing stated by hand:

    fresh thread, nothing said     BLOCKED__DEFINE_SUCCESS_FIRST
    what_is_missing on it          asks `classes_n`, a pointer, settled by
                                   `assess_the_data`
    person states goal_text and
    target_score through that door BLOCKED__BUILD_EVAL_SET

That is the question `d1ccd10` left open. The reported failure was a thread
sitting at BLOCKED__DEFINE_SUCCESS_FIRST with five gates reading NOT_REACHED --
not failed, NEVER REACHED -- because `goal_text` and `target_score` are declared
`source: ask` and nothing in the tool surface asked for them. **Two sentences
now move it**, and the block that remains is a later and different one.

## WHY THE ORIGIN IS THE WHOLE TEST

`RC10_AN_ASSERTION_NEVER_MINTS`: a `source: ask` fact cannot be derived or
inspected into existence. A model's facts arrive ASSERTED and cannot open a
gate, so a walk driven by a model supplying these two would still block -- and
finding a way to make them count would be the bug rather than the workaround.

`POST /api/tools/{name}` hard-codes `actor=USER`, so the same two facts arrive
STATED, which is the origin the ledger admits for `ask`. The transition below is
therefore a property of WHO SAID IT, not of what was said, and these tests drive
both actors to show that the difference is real rather than incidental.

## NO ENGINE, AND THE SAME DOOR

The suite runs with the engine stopped, so these call `REGISTRY.call` with the
actor the route passes rather than over HTTP. That is the same object the route
reaches and the same `actor=` value it hard-codes; what is not exercised here is
FastAPI's routing, which `tests/` covers elsewhere. The measurement above was
taken over the wire; this locks the behaviour underneath it.
"""

from __future__ import annotations

import unittest

import support

from app import asking, diagnosis, events, tools


#: The two the ledger declares `source: ask` with no default, which is what
#: makes them a person's to give. Read from the ledger rather than typed here,
#: so a change to either declaration fails this rather than drifting past it.
THE_TWO = ("goal_text", "target_score")

#: What a person actually said, in the run above.
WHAT_THE_PERSON_SAID = {
    "goal_text": "a coding model that emits consistent architecture graphs as JSON",
    "target_score": 0.85,
}


class TheTwoFactsAreTheUsersToGiveTest(unittest.TestCase):
    """Read out of the ledger, so this is about the declaration and not a memory."""

    def setUp(self):
        self.spec = diagnosis.default_spec()

    def test_both_are_declared_source_ask(self):
        for fact in THE_TWO:
            with self.subTest(fact=fact):
                self.assertEqual(self.spec.facts[fact].get("source"), "ask")

    def test_neither_carries_a_default(self):
        """A `source: ask` fact WITH a default is already satisfied and blocks
        nothing. These two block because nobody has answered them."""
        for fact in THE_TWO:
            with self.subTest(fact=fact):
                self.assertNotIn("default", self.spec.facts[fact])

    def test_a_stated_origin_is_admitted_and_an_asserted_one_is_not(self):
        """The engine's own table, not a claim about it. This is why the actor
        the door passes decides whether the walk moves."""
        #: `admissible_for` takes a FACT, not a source - it reads the fact's
        #: own `source:` and answers for that. Asking it about the string
        #: "ask" raised `KeyError: 'ask'`, which is the right refusal.
        admitted = self.spec.admissible_for("goal_text")
        self.assertIn(diagnosis.STATED, admitted)
        self.assertNotIn(diagnosis.ASSERTED, admitted)


class ATwoSentenceAnswerMovesTheWalkTest(unittest.TestCase):
    """THE CASE, and each exit has a case that produces only it."""

    def setUp(self):
        #: A REAL CONVERSATION, because the ledger refuses an id that names
        #: none - "a row filed against a conversation that does not exist YET
        #: is a row the next conversation INHERITS". Inventing 51 was the
        #: dangerous direction and it said so.
        support.sandbox(self)
        self.thread = events.create_thread("cold intake", None)["id"]

    def walk(self, facts=None, actor=None):
        out = tools.REGISTRY.call(
            "run_diagnosis",
            {"facts": dict(facts or {})},
            actor=actor or tools.evidence.USER,
            thread_id=self.thread,
        )
        return out.get("outcome")

    def state(self, facts, actor=None):
        return tools.REGISTRY.call(
            "state_facts",
            {"facts": dict(facts)},
            actor=actor or tools.evidence.USER,
            thread_id=self.thread,
        )

    def test_a_cold_thread_blocks_on_the_definition(self):
        """The reported failure, reproduced rather than remembered."""
        self.assertEqual(self.walk(), "BLOCKED__DEFINE_SUCCESS_FIRST")

    def test_the_two_sentences_move_it_off_that_block(self):
        """THE ANSWER TO THE OPEN QUESTION. Not "reaches a verdict" -- it reaches
        a DIFFERENT and later block, which is the whole claim."""
        self.state(WHAT_THE_PERSON_SAID)
        after = self.walk()
        self.assertNotEqual(after, "BLOCKED__DEFINE_SUCCESS_FIRST")
        self.assertEqual(after, "BLOCKED__BUILD_EVAL_SET")

    def test_the_block_that_remains_is_about_the_eval_set(self):
        """Named, so a later drift to some third block is a red test rather than
        a paragraph nobody re-reads."""
        self.state(WHAT_THE_PERSON_SAID)
        self.assertIn("EVAL_SET", self.walk())

    def test_one_sentence_is_not_enough(self):
        """`goal_text` alone leaves `target_score` null, and the node's condition
        is `target_score is null AND NOT user_can_produce(20, 'graded
        examples')` -- so the goal by itself does not satisfy it. Measured: the
        walk was unchanged."""
        self.state({"goal_text": WHAT_THE_PERSON_SAID["goal_text"]})
        self.assertEqual(self.walk(), "BLOCKED__DEFINE_SUCCESS_FIRST")


class WhereTheOriginActuallyDecidesTest(unittest.TestCase):
    """A node reads the VALUE. A gate reads the ORIGIN. I had this wrong.

    THE CLAIM I WROTE FIRST, AND IT WAS FALSE: that the same two sentences from
    a MODEL would leave the thread where it was, so the transition was "a
    property of who said it". Measured 2026-09-09, both actors on the same
    facts:

        USER  (STATED)    BLOCKED__BUILD_EVAL_SET
        MODEL (ASSERTED)  BLOCKED__BUILD_EVAL_SET

    Identical. `S0_NO_DEFINITION_OF_SUCCESS` is a NODE, and its condition
    `target_score is null and not user_can_produce(...)` reads whether the value
    is there, not who put it there. So the walk moves either way.

    `RC10_AN_ASSERTION_NEVER_MINTS` is about a fact being DERIVED OR INSPECTED
    into existence and about opening a GATE on it - not about a walk advancing
    past a node. Reading it as the stronger thing is easy, and I did: it is the
    difference between "a model cannot fabricate this fact" and "a model cannot
    influence the walk", and only the first is claimed.

    What follows locks the distinction, so nobody rebuilds on my misreading.
    """

    def setUp(self):
        support.sandbox(self)
        self.stated = events.create_thread("user speaks", None)["id"]
        self.asserted = events.create_thread("model speaks", None)["id"]

    def outcome_after(self, thread, actor):
        tools.REGISTRY.call(
            "state_facts", {"facts": dict(WHAT_THE_PERSON_SAID)},
            actor=actor, thread_id=thread,
        )
        return tools.REGISTRY.call(
            "run_diagnosis", {"facts": {}}, actor=actor, thread_id=thread
        ).get("outcome")

    def test_both_actors_move_the_walk_the_same_way(self):
        """The correction, asserted rather than described."""
        as_user = self.outcome_after(self.stated, tools.evidence.USER)
        as_model = self.outcome_after(self.asserted, tools.evidence.MODEL)
        self.assertEqual(as_user, as_model)
        self.assertEqual(as_user, "BLOCKED__BUILD_EVAL_SET")

    def test_but_the_origins_recorded_are_different(self):
        """The half that IS about the speaker, and it survives into the sheet
        even though this particular node does not consult it."""
        self.outcome_after(self.stated, tools.evidence.USER)
        self.outcome_after(self.asserted, tools.evidence.MODEL)
        for thread, actor, expected in (
            (self.stated, tools.evidence.USER, diagnosis.STATED),
            (self.asserted, tools.evidence.MODEL, diagnosis.ASSERTED),
        ):
            with self.subTest(expected=expected):
                sheet, _ = tools.evidence.assemble_facts(thread, {}, actor)
                self.assertEqual(sheet["target_score"].origin, expected)

    def test_a_gate_would_not_admit_the_model_s_word(self):
        """WHERE RC10 ACTUALLY BITES. The ledger's own table, for a `source:
        ask` fact: STATED opens a gate, ASSERTED does not. That is the promise -
        not that a model cannot advance a walk."""
        spec = diagnosis.default_spec()
        for fact in THE_TWO:
            with self.subTest(fact=fact):
                admitted = spec.admissible_for(fact)
                self.assertIn(diagnosis.STATED, admitted)
                self.assertNotIn(diagnosis.ASSERTED, admitted)


class TheAskerNamesAPointerNotAFormTest(unittest.TestCase):
    """What `what_is_missing` actually asks a cold thread, which was not what
    the task assumed.

    THE BRIEF EXPECTED `goal_text` FIRST. It asks `classes_n` -- a pointer,
    settled by `assess_the_data` -- and asks it again after the two sentences
    are stated. The frontier is the ledger's, not a list anybody wrote.
    """

    def setUp(self):
        support.sandbox(self)
        self.thread = events.create_thread("what it asks", None)["id"]

    def test_a_cold_thread_is_not_asked_for_anything_it_can_look_up(self):
        """THIS ASSERTED `pointer` AND THE ANSWER GOT BETTER, 2026-09-10.

        `answer` is POINTER when the settling tool has a required argument and
        MACHINE when it has none - "name something for me to read" against "I
        can go and run this". `assess_the_data` stopped requiring `path` that
        day, because a person walking the intake could not answer it: *"a tool
        has to run and asks for a path where the data is sitting. I have no
        idea."* It lists the datasets already in the checkout instead.

        So the first thing a cold thread meets is no longer a request for
        something the person may not have. The fact is the same; what the
        product wants from them is nothing.
        """
        out = tools.REGISTRY.call(
            "what_is_missing", {}, actor=tools.evidence.USER, thread_id=self.thread
        )
        question = out.get("question") or {}
        # AND IT GOT BETTER AGAIN, 2026-09-19. This asserted `classes_n`, which
        # a cold thread can indeed look up - but the walk was never going to
        # read it. `S0_RULES_SUFFICE` asks `task_family in {extraction,
        # classification} and ... classes_n <= 5`, the `and` answers False at
        # the first operand on a thread that has not said what kind of task it
        # is, and the class count is never looked at. The asker was building
        # its question from a PARSE of the condition rather than from what the
        # evaluation reached, so a person attaching a dataset was asked to
        # count label classes before anything had established there were
        # labels - and on Max's run that question cost forty minutes.
        #
        # What a cold thread meets now is the bar, which is the one thing here
        # nobody can look up: no path to name, no tool to run, no file to
        # find. The claim in this test's name holds more strongly than it did.
        self.assertEqual(question.get("fact"), "target_score")
        self.assertEqual(question.get("answer"), "number")
        self.assertNotEqual(
            question.get("answer"), "pointer",
            "a cold thread is still never opened with a request for a path",
        )

    def test_a_fact_that_really_needs_a_pointer_still_asks_for_one(self):
        """THE CONTROL, and it is what stops the case above reading as the
        asker losing the ability to ask. `eval_size_n`'s tool still requires a
        path, so it is still a POINTER."""
        self.assertEqual("pointer", asking.question_for("eval_size_n").answer)

    def test_the_card_names_the_door_that_settles_it(self):
        """Whatever the fact, the card carries the way to answer it. For a
        fact a tool measures that is `measured_by`; for one only the person
        can say, it is the tool and the actor on `settled_by`."""
        out = tools.REGISTRY.call(
            "what_is_missing", {}, actor=tools.evidence.USER, thread_id=self.thread
        )
        question = out.get("question") or {}
        settled = (question.get("declared") or {}).get("settled_by") or {}
        self.assertEqual(settled.get("tool"), "state_facts")
        self.assertEqual(settled.get("run_as"), "user")

    def test_a_fact_a_tool_measures_still_names_that_tool(self):
        """THE CONTROL for the case above: the pointer machinery is intact,
        and `classes_n` is still the card it always was when something asks
        for it."""
        card = asking.question_for("classes_n")
        self.assertEqual((card.accepts or {}).get("measured_by"), "assess_the_data")

    def test_it_is_not_goal_text(self):
        """Recorded because the task assumed otherwise, and an assumption that
        survives into a test is one nobody re-checks."""
        out = tools.REGISTRY.call(
            "what_is_missing", {}, actor=tools.evidence.USER, thread_id=self.thread
        )
        self.assertNotEqual((out.get("question") or {}).get("fact"), "goal_text")


if __name__ == "__main__":
    unittest.main()
