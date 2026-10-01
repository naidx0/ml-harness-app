"""The diagnosis is not optional, and a verdict in prose is still a verdict.

Read from four real threads in the shipped database. Each one asked this
product's central question; the tool calls are the whole finding:

    "Do I need to fine-tune at all?"             run_diagnosis x3      worked
    "Should we fine-tune on the ticket export?"  run_diagnosis         worked
    "We run a secondhand bookshop..."            10 tools, diagnosis   worked
    "should i train a model for this
     application that i am working inside off"   inspect_hardware x3,
                                                 list_local_models,
                                                 NO DIAGNOSIS          chatbot

The fourth got a seven-phase consulting deck - Assessing the Need, Defining
Your Objectives, Data Collection and Preparation, Model Selection, Evaluation,
Deployment and Scaling, Monitoring and Maintenance - with no gate, no
measurement and no verdict in it. Whether a person got this product or a
chatbot depended on whether the model felt like calling a tool that turn.

So this file asserts two properties, and they are halves of one thing.

**The supply.** The harness runs the diagnosis itself, every turn, before the
model speaks, and puts the verdict in the turn's context. Nothing the model
chooses can skip it.

**The annotation, which used to be a wall.** A reply that states a verdict the
engine did not reach REACHES THE USER, and the engine's own verdict is written
under it. Twenty conversations driven end to end against the live model found
the wall firing on 14% of turns with every firing in the sample false - a LoRA
explanation, a sentence about split ratios, and *"your machine has only 8 GB
VRAM, it does not have enough to fine-tune a 7B model effectively"*, which is a
correct do-not-train observation this product deleted. `docs/VISION.md` says
the transcript IS the artifact, so deleting true sentences from it to prevent a
failure that is not happening at that rate was damaging the central object.

**And the one wall that is left.** A verdict attributed to THIS HARNESS BY NAME
- *"based on the harness diagnosis, you do not need to fine-tune at all"* -
does not reach the user. That is a different act from a model offering an
opinion: it is a statement of fact about a record this harness holds, and it is
decidable by looking the record up, which is what makes it a wall at all. Both
shapes the brief named are still covered - a claim with no diagnosis behind it
and a claim that paraphrases the engine's answer into a different one - when
they wear our name.

And two properties in the other direction, which matter exactly as much:

**Somebody asking what LoRA means gets an answer**, not a gate ledger. The wall
declines on a definition, on a question, on a conditional and on a hedge, and
`WhatTheWallReadsTest` is the table that says which.

**It stays cheap.** One extra engine walk per turn - pure, no network - and a
brief bounded in characters, against a `run_diagnosis` payload of some 3,500.
"""

from __future__ import annotations

import unittest
from unittest import mock

from app import conductor, diagnosis, events
from app.instructions import capabilities
from app.providers import Delta, ToolCall
from app.providers import store as provider_store
from app.tools import blocks, evidence
from app.tools.registry import REGISTRY

import diagnosis_fixtures as fixtures
import support


class ScriptedModel:
    """A model that says what the test told it to, one round at a time.

    `drained` is how many deltas of the last round were actually consumed. The
    sentry is supposed to leave the provider mid-stream when it refuses a
    sentence, and that number is the only way to see it happen.
    """

    id = "fake"
    locality = "local"

    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.offered = []
        self.drained = 0

    def stream(self, messages, tools=None, *, secret=None):
        self.offered.append(tools)
        self.seen = [dict(m) for m in messages]
        script = self.rounds.pop(0) if self.rounds else []
        self.drained = 0
        for delta in script:
            self.drained += 1
            yield delta

    def capabilities(self, *, secret=None):
        raise AssertionError("the loop must not probe mid-turn")


def says(*chunks):
    return [Delta(kind="text", text=chunk) for chunk in chunks]


def asks(name="list_runs", call_id="c1", **arguments):
    return [
        Delta(kind="tool_call", tool_calls=(ToolCall(call_id, name, arguments),))
    ]


def engine_payload(facts) -> dict:
    """A `run_diagnosis` result, shaped here but DECIDED by the engine.

    `app/diagnosis.py` walks the tree; this only lifts the fields the conductor
    reads out of the result. Nothing invents a verdict, which is the rule this
    whole file is about and would be a strange one to break in its fixtures.

    `facts_used` and `unsubstantiated` ARE TWO OF THOSE FIELDS NOW and this
    fixture was missing both. `facts_used` is the sheet the walk was run over,
    and `conductor.standing_brief` reads its SIZE to decide which of the two
    briefs a turn gets - so a fixture without it rendered every outcome as an
    empty-ledger turn, and the budget test measured the wrong shape for all
    fifty-five. Both are lifted straight off the result, exactly as
    `app/tools/__init__.py` builds them, so nothing here decides anything.
    """
    result = diagnosis.diagnose(facts)
    payload = {
        "ok": True,
        "outcome": result.outcome,
        "verdict": result.verdict,
        "say": result.say,
        "gate_ledger": result.gate_ledger,
        # Shaped like the real one: `app/tools/__init__.py` builds this out of
        # `evidence.assemble_facts`' trail, where a value has already been
        # unwrapped from its `Fact` and an origin sits beside it. A fixture that
        # left the `Fact` in place put a non-serialisable object into a tool
        # result, which the event log then refused - so unwrap here, once.
        "facts_used": {
            name: {
                "value": getattr(value, "value", value),
                "origin": getattr(value, "origin", "ASSERTED"),
                "how": "a fixture",
            }
            for name, value in dict(facts).items()
        },
        "decided_by": "app/diagnosis.py",
    }
    if result.unsubstantiated:
        payload["unsubstantiated"] = [
            dict(row, next_step=evidence.resolves(row["fact"]))
            for row in result.unsubstantiated
        ]
    return payload


#: A real NO_TRAIN, from the fixture that reaches `NO_TRAIN__SHIP_AS_IS`: the
#: off-the-shelf model already clears the bar.
SHIP_AS_IS = engine_payload(fixtures.SPREAD["already_passes"]["facts"])

#: A real TRAIN, from a minting fixture. Used where a test needs the engine to
#: have said the opposite of what a reply says.
A_TRAIN_VERDICT = engine_payload(next(iter(fixtures.MINTING.values())))


class TurnTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)

    def connect(self, tool_calling="yes"):
        row = provider_store.create(
            "Fake", "http://127.0.0.1:11434", "fake-model", "ollama"
        )
        ready = provider_store.record_capabilities(
            row["id"],
            type(
                "Caps",
                (),
                {
                    "tool_calling": {"yes": True, "no": False}[tool_calling],
                    "detail": "set by the test",
                    "ctx_len": None,
                    "provenance": {},
                },
            )(),
        )
        provider_store.set_active(ready["id"])
        return ready

    def install(self, model):
        original = conductor.build
        conductor.build = lambda *a, **k: model
        self.addCleanup(setattr, conductor, "build", original)
        return model

    def standing_is(self, payload):
        """Make the harness's pre-turn walk answer with this verdict.

        The seam is `_standing_diagnosis` rather than the engine, because these
        tests are about what the conductor does with a verdict and not about
        which verdict a fact sheet reaches - `tests/test_diagnosis_fixtures.py`
        owns that, over every outcome in the spec.
        """
        patcher = mock.patch.object(
            conductor, "_standing_diagnosis", return_value=payload
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def thread(self, question="should i train a model for this application?"):
        row = events.create_thread("t")
        events.add_message(row["id"], "user", question)
        return row["id"]

    def rows(self, thread_id):
        return events.since(f"thread:{thread_id}")

    def prose(self, thread_id):
        """Everything the user was shown as assistant text, in order."""
        return "".join(
            row["payload"].get("text", "")
            for row in self.rows(thread_id)
            if row["kind"] == "chat.delta"
        )

    def ending(self, thread_id):
        return self.rows(thread_id)[-1]["payload"]["ending"]

    def notices(self, thread_id):
        return [
            row["payload"]
            for row in self.rows(thread_id)
            if row["kind"] == "conductor.notice"
        ]

    def card(self, thread_id):
        """The verdict the engine put beside the reply. One per turn, at most."""
        rows = [
            row["payload"]
            for row in self.rows(thread_id)
            if row["kind"] == conductor.VERDICT_KIND
        ]
        self.assertEqual(len(rows), 1, f"expected one verdict card, got {len(rows)}")
        return rows[0]


class StandingDiagnosisTest(TurnTest):
    """The supply half: it is computed before the model speaks, every turn."""

    def test_the_engine_runs_before_the_model_does(self):
        self.connect()
        model = self.install(ScriptedModel([says("Your log is empty so far.")]))
        thread_id = self.thread()
        list(conductor.run_turn(thread_id))

        brief = [
            message
            for message in model.seen
            if message["role"] == "user"
            and str(message["content"]).startswith(conductor.HARNESS)
        ]
        self.assertEqual(
            len(brief),
            1,
            "the model was not handed the standing diagnosis, or was handed two",
        )
        # THIS ASSERTION USED TO REQUIRE THE VERDICT, THE OUTCOME ID AND THE
        # GATE LEDGER, AND IT WAS ASSERTING THE DEFECT. On an empty ledger the
        # engine stops above the gate tree, so none of those is a finding about
        # this thread - they are the same constant every conversation gets
        # before it starts, and a model handed a constant shaped like an answer
        # spends it on whatever was asked. Measured: ten runs of a question
        # about what this product can do, ten gate ledgers, zero answers. See
        # `tests/test_a_capability_question_is_not_a_gate_question.py`, which
        # owns that property and carries the seven arrangements that were
        # measured before this one.
        #
        # The supply property this class exists for is untouched: the engine
        # still walks before the model speaks - `test_it_is_one_engine_walk_per
        # _turn` and `test_the_turn_records_which_verdict_was_standing` are the
        # two halves of that - and what a thread with facts in it gets is
        # asserted in `WhatItCostsTest`.
        for artifact in (
            "BLOCKED__DEFINE_SUCCESS_FIRST",
            "verdict BLOCKED",
            "G0_EVAL_SET",
            "Nothing downstream is decidable",
        ):
            self.assertNotIn(artifact, brief[0]["content"], artifact)
        # THE TOOL BLOCK, NOW SCOPED TO THE CAPABILITY BLOCKS THIS TURN LOADED,
        # and the heading carries BOTH counts because either alone would be a
        # number about a list it is not showing. The core is what an empty
        # ledger selects, and the core is what a person who has just arrived
        # needs: attach a file, look at its rows, look at the machine, and the
        # three doors back into the engine.
        self.assertIn(
            "tools are loaded for this turn, and what each one does",
            brief[0]["content"],
        )
        for name in blocks.tools_in(blocks.CORE):
            self.assertIn(name, brief[0]["content"], name)

    def test_it_sits_after_the_question_it_is_about(self):
        """Adjacent, and last. The other order was tried against the model.

        Putting the block in FRONT of the question is the obvious guess, and it
        was measured: ten live runs of Max's capability question each way, 3 of
        10 answered with the block in front against 4 of 10 with it behind, and
        with the question last the model stopped answering and started acting -
        three to six tool rounds at somebody who had asked what the product
        does, including one attempt at `start_training`. The comment in
        `conductor.run_turn` carries the numbers; this is the assertion that
        keeps the placement.
        """
        self.connect()
        model = self.install(ScriptedModel([says("Right.")]))
        list(conductor.run_turn(self.thread()))

        roles = [m["role"] for m in model.seen]
        contents = [str(m["content"]) for m in model.seen]
        last_user = max(
            index for index, role in enumerate(roles) if role == "user"
        )
        self.assertTrue(contents[last_user].startswith(conductor.HARNESS))
        self.assertIn(
            "should i train a model for this application?",
            contents[last_user - 1],
            "the brief was not placed against the question it answers",
        )

    def test_it_is_never_stored_as_something_the_user_said(self):
        """Scaffolding for one turn. A stored one would be read back stale."""
        self.connect()
        self.install(ScriptedModel([says("Right."), says("Right again.")]))
        thread_id = self.thread()
        list(conductor.run_turn(thread_id))
        events.add_message(thread_id, "user", "and now?")
        self.install(ScriptedModel([says("Still right.")]))
        list(conductor.run_turn(thread_id))

        stored = [
            m["content"]
            for m in events.messages_for(thread_id)
            if m["role"] == "user"
        ]
        self.assertEqual(
            stored,
            ["should i train a model for this application?", "and now?"],
            "the harness put its own words in the user's mouth",
        )

    def test_the_turn_records_which_verdict_was_standing(self):
        """A verdict the user saw has to be readable back off the log."""
        self.connect()
        self.install(ScriptedModel([says("Right.")]))
        thread_id = self.thread()
        list(conductor.run_turn(thread_id))

        started = [
            row["payload"]
            for row in self.rows(thread_id)
            if row["kind"] == "turn.started"
        ][0]
        self.assertEqual(
            started["diagnosis"],
            {
                "verdict": "BLOCKED",
                "outcome": "BLOCKED__DEFINE_SUCCESS_FIRST",
                "computed": True,
                "decided_by": "app/diagnosis.py",
            },
        )

    def test_a_tool_that_runs_the_engine_supersedes_the_walk(self):
        """A model doing the right thing is checked against ITS answer.

        `run_diagnosis` with facts the model has established can reach a verdict
        the ambient walk could not, and the reply is then measured against that
        one. Otherwise the wall would fight the only behaviour it wants.
        """
        self.connect()
        original = conductor.REGISTRY.call

        def call(name, arguments, *, actor, thread_id=None, **rest):
            if name == "run_diagnosis" and actor == "model":
                return A_TRAIN_VERDICT
            return original(name, arguments, actor=actor, thread_id=thread_id, **rest)

        patcher = mock.patch.object(conductor.REGISTRY, "call", side_effect=call)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.install(
            ScriptedModel(
                [
                    asks("run_diagnosis", facts={}),
                    says("You should fine-tune, then. Here is the plan."),
                ]
            )
        )
        thread_id = self.thread()
        list(conductor.run_turn(thread_id))

        self.assertEqual(self.ending(thread_id), "answered")
        self.assertIn("You should fine-tune, then.", self.prose(thread_id))

    def test_a_result_without_the_engine_stamp_does_not_move_the_verdict(self):
        standing = conductor._Standing(SHIP_AS_IS)
        standing.note({"ok": True, "verdict": "TRAIN"})  # no `decided_by`
        standing.note({"ok": False, "verdict": "TRAIN", "decided_by": "app/diagnosis.py"})
        standing.note("not even a mapping")
        self.assertEqual(standing.verdict, "NO_TRAIN")
        standing.note(A_TRAIN_VERDICT)
        self.assertEqual(standing.verdict, "TRAIN")


class AVerdictTheModelOwnsIsAnnotatedTest(TurnTest):
    """The half that used to be a wall. It records now, and it never deletes.

    Every test here is one the class above ran with the assertions the other
    way up. The sentences are the same sentences; what changed is that they
    arrive.
    """

    def test_a_claim_with_no_diagnosis_behind_it_reaches_the_user(self):
        """The brief's first requirement, and the answer to it is now a card.

        The engine is unavailable, so there is no verdict at all. The model
        answers the way thread 9 did - straight into the deck - and every word
        of it arrives, with the fact that there is no engine verdict written
        underneath rather than substituted for it.
        """
        self.connect()
        self.standing_is(None)
        model = self.install(
            ScriptedModel(
                [
                    says(
                        "Here is how I would approach it. ",
                        "You should fine-tune a model for this application. ",
                        "Phase one: Assessing the Need. ",
                        "Phase two: Defining Your Objectives. ",
                    )
                ]
            )
        )
        thread_id = self.thread()
        list(conductor.run_turn(thread_id))

        shown = self.prose(thread_id)
        for kept in (
            "Here is how I would approach it.",
            "You should fine-tune a model for this application.",
            "Assessing the Need",
            "Defining Your Objectives",
        ):
            self.assertIn(kept, shown, kept)
        self.assertEqual(self.ending(thread_id), "answered")
        self.assertEqual(self.notices(thread_id), [])

        # And the transcript agrees with what was on screen. NOTHING WAS
        # REMOVED FROM IT, which is the property this file used to assert in
        # the opposite direction and is the whole of the change.
        stored = " ".join(
            m["content"] for m in events.messages_for(thread_id)
            if m["role"] == "assistant"
        )
        self.assertIn("You should fine-tune a model for this application.", stored)

        card = self.card(thread_id)
        self.assertEqual(card["asserted"], conductor.TRAIN)
        self.assertFalse(card["agrees"])
        self.assertIsNone(card["verdict"])
        self.assertFalse(card["computed"])
        self.assertIn("could not be computed", card["text"])

        self.assertEqual(
            model.drained,
            4,
            "the provider was cut off for a sentence that is no longer refused",
        )

    def test_the_engine_s_verdict_is_shown_beside_a_paraphrase_of_it(self):
        """The brief's second requirement, answered by showing both.

        The engine's answer for a thread with no facts is BLOCKED - nothing is
        decidable until 'good' is defined. "You do not need to fine-tune here"
        is a decision, and it is not that one. The reader is now handed both
        and can see the difference, which is more than they were told when the
        first half was deleted.
        """
        self.connect()
        thread_id = self.thread()
        self.install(
            ScriptedModel(
                [says("You do not need to fine-tune here. Prompting is enough.")]
            )
        )
        list(conductor.run_turn(thread_id))

        shown = self.prose(thread_id)
        self.assertIn("You do not need to fine-tune here.", shown)
        self.assertIn("Prompting is enough", shown)
        self.assertEqual(self.ending(thread_id), "answered")

        card = self.card(thread_id)
        self.assertEqual(card["asserted"], conductor.NO_TRAIN)
        self.assertEqual(card["verdict"], "BLOCKED")
        self.assertFalse(card["agrees"])
        self.assertIn("BLOCKED__DEFINE_SUCCESS_FIRST", card["text"])
        self.assertIn(
            "Nothing downstream is decidable until 'good' is defined.",
            card["text"],
            "the engine's own sentence is not what stands beside the reply",
        )

    def test_a_claim_against_a_decided_verdict_is_annotated_too(self):
        self.connect()
        self.standing_is(SHIP_AS_IS)
        thread_id = self.thread()
        self.install(
            ScriptedModel([says("You should fine-tune a LoRA on your tickets.")])
        )
        list(conductor.run_turn(thread_id))

        self.assertIn("You should fine-tune a LoRA", self.prose(thread_id))
        card = self.card(thread_id)
        self.assertEqual(card["verdict"], "NO_TRAIN")
        self.assertEqual(card["outcome"], "NO_TRAIN__SHIP_AS_IS")
        self.assertFalse(card["agrees"])
        self.assertIn(str(SHIP_AS_IS["say"]), card["text"])

    def test_a_claim_the_engine_agrees_with_is_annotated_as_agreeing(self):
        """The model may NARRATE the verdict, and the card corroborates it.

        A CARD ON AGREEMENT TOO, and it is not decoration. If the card only
        ever appeared over a disagreement its presence would BE the verdict,
        and a reader would learn to read it as an alarm - which is exactly the
        thing `DiagnosisCard`'s third rule forbids.
        """
        self.connect()
        self.standing_is(SHIP_AS_IS)
        thread_id = self.thread()
        answer = (
            "You should not fine-tune. The off-the-shelf model already clears "
            "your bar, so ship it and keep the eval as a regression test."
        )
        self.install(ScriptedModel([says(answer)]))
        list(conductor.run_turn(thread_id))

        self.assertEqual(self.prose(thread_id), answer)
        self.assertEqual(self.ending(thread_id), "answered")
        self.assertEqual(self.notices(thread_id), [])

        card = self.card(thread_id)
        self.assertTrue(card["agrees"])
        self.assertEqual(card["asserted"], conductor.NO_TRAIN)
        self.assertIn("reached the same answer", card["text"])

    def test_an_annotated_reply_keeps_its_tool_calls(self):
        """A reply we did not stop is a reply that gets to go on working."""
        self.connect()
        self.standing_is(None)
        thread_id = self.thread()
        self.install(
            ScriptedModel(
                [
                    [
                        Delta(kind="text", text="You should fine-tune. "),
                        Delta(
                            kind="tool_call",
                            tool_calls=(ToolCall("c1", "list_runs", {}),),
                        ),
                    ],
                    says("That is what the runs show."),
                ]
            )
        )
        list(conductor.run_turn(thread_id))
        self.assertIn("tool.call", [r["kind"] for r in self.rows(thread_id)])

    def test_no_card_where_the_reply_settled_nothing(self):
        """The opposite failure, and the one this product keeps making.

        A gate ledger handed to somebody who asked what their GPU is. The card
        is conditioned on what the REPLY said, so a turn that said nothing
        about training gets nothing.
        """
        self.connect()
        thread_id = self.thread("what is my GPU?")
        self.install(ScriptedModel([says("You have an RTX 4070 with 12 GB.")]))
        list(conductor.run_turn(thread_id))

        kinds = [row["kind"] for row in self.rows(thread_id)]
        self.assertNotIn(conductor.VERDICT_KIND, kinds)

    def test_the_card_is_never_read_back_as_something_the_assistant_said(self):
        """An event, not a message. A stored one would be read back stale."""
        self.connect()
        thread_id = self.thread()
        self.install(ScriptedModel([says("You should fine-tune a model here.")]))
        list(conductor.run_turn(thread_id))

        stored = [m["content"] for m in events.messages_for(thread_id)]
        self.assertTrue(
            all("The engine, walking" not in text for text in stored),
            "the verdict card was stored as a message and will be read back",
        )

    def test_agreement_is_judged_against_the_verdict_that_finally_stood(self):
        """A model that goes and runs the diagnosis is judged on ITS answer."""
        self.connect()
        original = conductor.REGISTRY.call

        def call(name, arguments, *, actor, thread_id=None, **rest):
            if name == "run_diagnosis" and actor == "model":
                return A_TRAIN_VERDICT
            return original(name, arguments, actor=actor, thread_id=thread_id, **rest)

        patcher = mock.patch.object(conductor.REGISTRY, "call", side_effect=call)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.install(
            ScriptedModel(
                [
                    asks("run_diagnosis", facts={}),
                    says("You should fine-tune, then. Here is the plan."),
                ]
            )
        )
        thread_id = self.thread()
        list(conductor.run_turn(thread_id))

        card = self.card(thread_id)
        self.assertEqual(card["verdict"], "TRAIN")
        self.assertTrue(card["agrees"])


class AVerdictWearingTheHarnessSNameTest(TurnTest):
    """The one wall that is left. Each test constructs it and catches it.

    Why this one and not the other: a model that writes *"you do not need to
    fine-tune"* has stated an opinion, and an opinion shown beside the engine's
    actual verdict is defused - the reader sees both and weighs them. A model
    that writes *"based on the harness diagnosis, you do not need to fine-tune
    at all"* has stated a FACT ABOUT A RECORD THIS HARNESS HOLDS. Showing that
    beside a correction leaves two harness-attributed verdicts on one screen
    and asks the user to work out which one we actually said.

    And it is checkable rather than inferential, which is the property that
    makes `app/provenance.py` a wall: a sentence misread as an attribution only
    fires when the engine ALSO disagrees with it, so the two halves have to
    fail together.
    """

    def test_a_verdict_put_in_our_mouth_does_not_reach_the_user(self):
        self.connect()
        self.standing_is(None)
        model = self.install(
            ScriptedModel(
                [
                    says(
                        "Here is how I would approach it. ",
                        "Based on the harness diagnosis, you do not need to "
                        "fine-tune at all. ",
                        "Phase one: Assessing the Need. ",
                    )
                ]
            )
        )
        thread_id = self.thread()
        list(conductor.run_turn(thread_id))

        shown = self.prose(thread_id)
        self.assertIn("Here is how I would approach it.", shown)
        self.assertNotIn("you do not need to fine-tune at all", shown)
        self.assertNotIn("Assessing the Need", shown)
        self.assertEqual(self.ending(thread_id), conductor.WITHHELD)

        stored = " ".join(
            m["content"] for m in events.messages_for(thread_id)
            if m["role"] == "assistant"
        )
        self.assertNotIn("you do not need to fine-tune at all", stored)
        self.assertIn(
            "could not be computed",
            shown,
            "the user was not told why there is no verdict",
        )
        self.assertLess(
            model.drained,
            3,
            "the provider was drained after the sentence was refused",
        )

    def test_the_engine_s_own_words_are_what_arrives_instead(self):
        self.connect()
        thread_id = self.thread()
        self.install(
            ScriptedModel(
                [says("The harness has concluded that you should fine-tune here.")]
            )
        )
        list(conductor.run_turn(thread_id))

        shown = self.prose(thread_id)
        self.assertNotIn("you should fine-tune here", shown)
        self.assertIn("BLOCKED__DEFINE_SUCCESS_FIRST", shown)
        self.assertIn(
            "Nothing downstream is decidable until 'good' is defined.", shown
        )
        self.assertEqual(self.ending(thread_id), conductor.WITHHELD)

    def test_the_name_only_costs_the_reply_when_the_engine_disagrees(self):
        """The asymmetry, asserted. THE SAME SENTENCE, TWICE.

        This is the property that makes a loose reading of "does it attribute?"
        affordable, and it is the same argument `app/provenance.py` makes about
        a misread claim: the parsing half and the lookup half have to fail
        together, so a model quoting us CORRECTLY is never stopped.
        """
        sentence = "According to the harness, you do not need to fine-tune."

        self.connect()
        self.standing_is(SHIP_AS_IS)  # NO_TRAIN, which is what the sentence says
        agreeing = self.thread()
        self.install(ScriptedModel([says(sentence)]))
        list(conductor.run_turn(agreeing))
        self.assertIn("you do not need to fine-tune", self.prose(agreeing))
        self.assertEqual(self.ending(agreeing), "answered")

        self.standing_is(None)  # no verdict at all, so the claim is refuted
        refuted = self.thread()
        self.install(ScriptedModel([says(sentence)]))
        list(conductor.run_turn(refuted))
        self.assertNotIn("you do not need to fine-tune", self.prose(refuted))
        self.assertEqual(self.ending(refuted), conductor.WITHHELD)

    def test_a_withheld_reply_does_not_get_to_keep_acting(self):
        """Tool calls that arrived with a refused reply are not run."""
        self.connect()
        self.standing_is(None)
        thread_id = self.thread()
        self.install(
            ScriptedModel(
                [
                    [
                        Delta(
                            kind="text",
                            text="The diagnosis says you should fine-tune. ",
                        ),
                        Delta(
                            kind="tool_call",
                            tool_calls=(ToolCall("c1", "list_runs", {}),),
                        ),
                    ]
                ]
            )
        )
        list(conductor.run_turn(thread_id))
        self.assertNotIn("tool.call", [r["kind"] for r in self.rows(thread_id)])

    def test_the_forced_answer_round_is_not_exempt(self):
        """Borrowing our name is the same act whether we asked for words or not."""
        self.connect()
        self.standing_is(None)
        thread_id = self.thread()
        self.install(
            ScriptedModel(
                [
                    asks("list_runs", call_id="a", limit=1),
                    asks("list_runs", call_id="b", limit=2),
                    says("The harness says you should fine-tune on your export."),
                ]
            )
        )
        list(conductor.run_turn(thread_id, max_tool_rounds=3))
        self.assertEqual(self.ending(thread_id), conductor.WITHHELD)
        self.assertNotIn("you should fine-tune", self.prose(thread_id))

    def test_nothing_is_deleted(self):
        """The refused draft is in the log. It is not in the reply."""
        self.connect()
        self.standing_is(None)
        thread_id = self.thread()
        self.install(
            ScriptedModel([says("The harness says you should fine-tune a model.")])
        )
        list(conductor.run_turn(thread_id))

        notice = self.notices(thread_id)[0]
        self.assertEqual(
            notice["withheld"], "The harness says you should fine-tune a model."
        )
        self.assertEqual(notice["asserted"], conductor.TRAIN)
        self.assertEqual(notice["kind"], conductor.BORROWED_VERDICT)
        self.assertIsNone(notice["engine_verdict"])
        self.assertEqual(notice["decided_by"], "app/diagnosis.py")
        # The notice's own rendered text is the explanation, not the draft.
        self.assertNotIn("you should fine-tune", notice["text"])

    def test_the_turn_still_ends_in_words(self):
        self.connect()
        self.standing_is(None)
        thread_id = self.thread()
        self.install(
            ScriptedModel([says("The harness says you should fine-tune a model.")])
        )
        list(conductor.run_turn(thread_id))

        kinds = [row["kind"] for row in self.rows(thread_id)]
        self.assertEqual(kinds[-1], events.END_KIND)
        self.assertEqual(kinds[-2], "chat.delta")
        last = events.messages_for(thread_id)[-1]
        self.assertEqual(last["role"], "assistant")
        self.assertTrue(last["content"].strip())


class AnOrdinaryQuestionGetsAnOrdinaryAnswerTest(TurnTest):
    """The opposite failure. A harness that answers everything with a ledger."""

    ORDINARY = (
        ("what does LoRA mean?", "LoRA means low-rank adaptation. It freezes the "
         "base weights and learns two small matrices instead."),
        ("what did run 41 do?", "Run 41 finished in 22 minutes with a loss of 0.31."),
        ("what is a train/test split?",
         "A train/test split holds rows back so a score is measured on data the "
         "model never saw."),
    )

    def test_it_answers_the_question_that_was_asked(self):
        self.connect()
        for question, answer in self.ORDINARY:
            with self.subTest(question=question):
                thread_id = self.thread(question)
                self.install(ScriptedModel([says(answer)]))
                list(conductor.run_turn(thread_id))
                self.assertEqual(self.prose(thread_id), answer)
                self.assertEqual(self.ending(thread_id), "answered")
                self.assertEqual(self.notices(thread_id), [])

    def test_and_a_hardware_question_gets_the_hardware_that_was_measured(self):
        """The GPU row, which used to sit in `ORDINARY` with an invented number.

        It read `("what is my GPU?", "You have an RTX 4070 with 12 GB of
        VRAM.")` over a turn where NO TOOL RAN, so the 12 had no origin at all,
        and what the row actually asserted was that a hardware reading nobody
        took is an "ordinary answer". `CLAUDE.md` names that as the defect this
        product was built to end. It is stopped now, and the row is here
        instead, doing what it meant to do.

        Two turns on one thread, because the ledger crosses turns: the first
        MEASURES, the second SAYS. THE NUMBER IS READ OFF THE INSTRUMENT'S OWN
        ROW rather than written here - writing one would be inventing one,
        which is the whole subject of this test.
        """
        self.connect()
        thread_id = self.thread("what is my GPU?")
        self.install(ScriptedModel([asks("inspect_hardware"), says("Checked. ")]))
        list(conductor.run_turn(thread_id))

        held = [
            row["value"]
            for row in evidence.rows_for(thread_id)
            if row["fact"] == "vram_gb"
        ]
        if not held:
            # Not a failure: the subject is absent. See
            # support.a_gpu_was_measured for why a stand-in figure
            # would be this suite inventing the very thing the wall
            # under test exists to stop.
            self.skipTest(support.NO_GPU_HERE)
        answer = f"You have an RTX 4070 with {held[-1]} GB of VRAM."

        events.add_message(thread_id, "user", "and what is my GPU?")
        self.install(ScriptedModel([says(answer)]))
        list(conductor.run_turn(thread_id))

        self.assertIn(answer, self.prose(thread_id))
        self.assertEqual(self.ending(thread_id), "answered")

    def test_and_a_dataset_question_gets_the_size_that_has_an_origin(self):
        """The dataset row, which used to sit in `ORDINARY` with an invented
        number - the same defect as the GPU row above, found the same way.

        It read `("how big is my dataset?", "Your export has 4,120 rows and 6
        columns.")` over a turn where NO TOOL RAN, the ledger was empty and the
        user had typed no figures, so 4,120 and 6 had no origin at all. What the
        row actually asserted was that a dataset profile nobody took is an
        "ordinary answer". It went unnoticed until `tabular_features` learned
        the word *"columns"*, because the wall knew that fact only by the
        ledger's name for it and the model had written English.

        NOT LOOSENED, AND NOT DELETED. The row is here doing what it meant to
        do: an ordinary question still gets an ordinary answer rather than a
        gate ledger, and the size in the answer now has somewhere to have come
        from. `profile_dataset` is not the seam it is given, because no tool in
        this harness stamps `tabular_features`; the origin available is the
        person's own words, which back a flat lookup precisely because
        arithmetic on what somebody told you is not a fabrication.
        """
        self.connect()
        thread_id = self.thread(
            "how big is my dataset? it's the export with 4,120 rows and 6 columns"
        )
        answer = "Your export has 4,120 rows and 6 columns."
        self.install(ScriptedModel([says(answer)]))
        list(conductor.run_turn(thread_id))

        self.assertEqual(self.prose(thread_id), answer)
        self.assertEqual(self.ending(thread_id), "answered")
        self.assertEqual(self.notices(thread_id), [])

    def test_but_the_same_answer_with_no_origin_is_stopped(self):
        """NON-VACUOUS, and the reason the row moved rather than relaxing.

        The identical sentence, on a thread where the person named no figures,
        is a dataset reading nobody took - and `CLAUDE.md` names that as the
        defect this product was built to end.
        """
        self.connect()
        thread_id = self.thread("how big is my dataset?")
        self.install(ScriptedModel([says("Your export has 4,120 rows and 6 columns.")]))
        list(conductor.run_turn(thread_id))

        self.assertEqual(self.ending(thread_id), conductor.MEASUREMENT_WITHHELD)
        notice = self.notices(thread_id)[0]
        self.assertEqual(notice["kind"], conductor.INVENTED_MEASUREMENT)
        self.assertEqual(notice["fact"], "tabular_features")

    def test_no_gate_ledger_is_narrated_at_it(self):
        """The brief is context. It is not a thing the harness says out loud."""
        self.connect()
        thread_id = self.thread("what does LoRA mean?")
        answer = "LoRA means low-rank adaptation."
        self.install(ScriptedModel([says(answer)]))
        list(conductor.run_turn(thread_id))
        shown = self.prose(thread_id)
        for word in ("G0_EVAL_SET", "BLOCKED", "gate", "verdict"):
            self.assertNotIn(word, shown)


class WhatTheWallReadsTest(unittest.TestCase):
    """One row per sentence. The table IS the specification of the wall.

    Written as a table because the failure it guards is nondeterministic prose,
    and because both directions of error have a cost worth naming. A missed
    claim leaves a verdict unattributed; the diagnosis still ran. A false one
    takes somebody's answer away - and the sentence most at risk of that is a
    model correctly narrating a BLOCKED verdict, which is the product working.

    THE ROWS SURVIVED A CHANGE OF MECHANISM, which is the point of writing them
    as sentences rather than as regexes. The reader underneath went from a
    proximity rule to the six grammatical frames in `conductor._settles_span`;
    every row below reads the same way through both.
    `TheWallReadsGrammarAndNotDistanceTest` carries the retune, the live corpus
    it was measured over, and the sentences the old rule got wrong.
    """

    CLAIMS = (
        ("You should fine-tune a model for this.", conductor.TRAIN),
        ("Yes, you need to train your own model.", conductor.TRAIN),
        ("I recommend fine-tuning on your ticket export.", conductor.TRAIN),
        ("It's worth training a small LoRA here.", conductor.TRAIN),
        ("Go ahead and fine-tune.", conductor.TRAIN),
        ("Fine-tuning is worth it for your case.", conductor.TRAIN),
        ("You should train.", conductor.TRAIN),
        ("The answer is yes: fine-tune.", conductor.TRAIN),
        ("So my recommendation is to fine-tune.", conductor.TRAIN),
        ("Training is justified here.", conductor.TRAIN),
        ("Fine-tuning makes sense here.", conductor.TRAIN),
        ("You should not fine-tune.", conductor.NO_TRAIN),
        ("You don't need to train anything.", conductor.NO_TRAIN),
        ("No, you do not need to fine-tune at all.", conductor.NO_TRAIN),
        ("Fine-tuning is not worth it here.", conductor.NO_TRAIN),
        ("I'd recommend against fine-tuning.", conductor.NO_TRAIN),
        ("Training is not the right answer.", conductor.NO_TRAIN),
        ("There is no need to fine-tune.", conductor.NO_TRAIN),
        ("Fine-tuning would be premature.", conductor.NO_TRAIN),
        ("Do not train anything.", conductor.NO_TRAIN),
        ("Given all that: do not train.", conductor.NO_TRAIN),
        # A verdict about a noun rather than an act. `fine-tuned` is a
        # participle, which the reader treats as machinery everywhere except
        # here - where it is the object of a modal the reader owns.
        ("You don't need a fine-tuned model.", conductor.NO_TRAIN),
        # VERBATIM FROM granite4-hermes, answering Max's own phrasings on a
        # thread whose engine verdict is BLOCKED. Every one of these is a
        # do-not-train decision the engine had not reached, which is the exact
        # thing the five gates exist to stop and it arrived through prose.
        ("It is not worth training a model for this application.", conductor.NO_TRAIN),
        ("You don't need to fine-tune.", conductor.NO_TRAIN),
        ("You do not need to fine-tune at all.", conductor.NO_TRAIN),
        ("You do not need to fine-tune at all right now.", conductor.NO_TRAIN),
        ("You don't need to fine-tune the model right now.", conductor.NO_TRAIN),
        # It says "the harness says". The harness said BLOCKED. A verdict the
        # engine did not reach, wearing the engine's name.
        (
            "The harness says you do not need to train a fine-tuned model "
            "right now.",
            conductor.NO_TRAIN,
        ),
        (
            "Based on the diagnosis output, you do **not** need to fine-tune "
            "the model at this point because the evaluation set has not been "
            "defined yet.",
            conductor.NO_TRAIN,
        ),
    )

    #: Sentences a person would read as a claim and the wall lets through, with
    #: the reason each one is a trade rather than an oversight. They are here so
    #: the trade is written down and cannot be undone by accident: every one of
    #: these was widened to stop a FALSE catch that a real granite4-hermes reply
    #: produced while narrating a BLOCKED verdict correctly.
    MISSED_ON_PURPOSE = (
        # "does not" describes; it does not recommend. Reading it as advice made
        # the wall stop "your current situation does not allow for training a
        # model yet", which is the engine's answer in the model's words.
        "Fine-tuning does not help here.",
        # "cannot" is a refusal to state a verdict, not a verdict. Reading it as
        # one stopped "we cannot recommend training a fine-tuned model".
        "You cannot justify a fine-tune on this.",
        # A hedge is not a claim, and a model that only ever hedges has not
        # stated a verdict for the wall to be wrong about.
        "You might want to fine-tune eventually.",
        # A NEGATIVE verdict with a condition welded to its end. The engine's
        # BLOCKED answer IS "not until", so this agrees with it rather than
        # contradicting it - see `conductor._TRAILING_CONDITION`.
        #
        # THIS USED TO SAY the price was that "you should fine-tune before your
        # next release" goes through too. It no longer is: a POSITIVE claim
        # keeps recommending whatever trails it, and `_TRAILING_ABSENCE` is the
        # narrower list it is released by. What still goes through is a
        # positive claim trailing `without`, which names something absent -
        # `tests/test_the_six_true_catches_come_back.py` carries the live
        # sentence that keeps it there.
        "Training is not worth it until you have an eval set.",
        # A frame made ENTIRELY of quoted words. Naming a sentence is not
        # saying it, and the live sentence that forced this is the model
        # describing what this product can answer.
        #
        # THIS USED TO DELETE the quoted words, which was too wide: with
        # nothing left to read, `The answer is "fine-tune".` had no frame in it
        # at all. The question is now which words the FRAME is made of, so a
        # verdict the sentence hands down in quotation marks is caught and this
        # one, where the sentence around the quote is describing it, is not.
        '"Do not train anything" is often the most valuable answer here.',
    )

    #: Every one of these is a sentence the harness must hand over unchanged.
    #: The first four are the product narrating its own BLOCKED verdict.
    ASSERTS_NOTHING = (
        "You should first define what good means before training.",
        "Before we can answer whether you should train, we need an eval set.",
        "Write 20 inputs and the output you wanted, then we can say whether "
        "training helps.",
        "You have 1,119 runs and no eval set, so nothing about training is "
        "decidable yet.",
        "I can run the diagnosis to see whether you should fine-tune.",
        "The harness will tell you whether to train.",
        "LoRA is a way of fine-tuning a model with fewer parameters.",
        "Fine-tuning updates the weights of a model; prompting does not.",
        "A fine-tune costs GPU hours; a prompt change costs minutes.",
        "Do you want me to check whether fine-tuning is warranted?",
        "If your baseline is measured and prompting is exhausted, training may "
        "be justified.",
        "Training data should be deduplicated first.",
        "Train/test split leakage is what I checked.",
        "The training run you should look at is run 41.",
        "Your training job needs 12 GB of VRAM.",
        "Your GPU has 8 GB of VRAM.",
        "What does LoRA mean?",
        "LoRA means low-rank adaptation.",
        "Let me check your hardware first.",
        "",
        "   ",
    )

    #: VERBATIM FROM granite4-hermes ON THE LIVE OLLAMA, answering Max's own
    #: four phrasings against an empty ledger, where the engine's verdict is
    #: BLOCKED. Every one of these is the model narrating that verdict
    #: correctly, and every one of them was stopped by an earlier cut of the
    #: reader. They are the reason `_HEDGE`, `_CONDITIONAL_OPENERS` and
    #: `_NOT_A_VERB_AFTER` say what they say, and they are here rather than in a
    #: comment because a widening nobody can re-run is a widening that gets
    #: narrowed back by the next person with a plausible idea.
    NARRATING_BLOCKED_CORRECTLY = (
        "To move forward with any training or fine-tuning, you need to:",
        "Based on the diagnosis from the harness, your current situation does "
        "not allow for training a model yet.",
        "Without these elements, it is premature to commit to fine-tuning a "
        "model.",
        "Without a clear target for 'good', training cannot be justified.",
        "Since the diagnosis is blocked at this stage, it suggests that before "
        "considering fine-tuning or building any model, you should first define "
        "what constitutes a successful outcome.",
        "This setup should handle most fine-tuning or inference workloads "
        "effectively.",
        "Based on our diagnosis, we cannot recommend training a fine-tuned "
        "model for sorting your incoming emails right now because you haven't "
        "defined what \"good\" looks like in this context.",
        "The system needs 20 concrete examples of what \"good\" looks like "
        "before any fine-tuning can be justified.",
        "This information is essential for the harness to proceed with any "
        "recommendation regarding training or building a model.",
        "Until you establish this evaluation set and have a measurable baseline, "
        "no further steps should be taken towards training or fine-tuning a "
        "model.",
        "To proceed with training, you need to specify what 'good' looks like "
        "by providing 20 inputs and their expected outputs.",
        "The verdict indicates that the training decision cannot proceed until "
        "a proper evaluation set has been defined and measured.",
        "This forms the evaluation set needed for training or evaluating "
        "models.",
        "The verdict indicates that training (fine-tuning) is blocked until you "
        "define what \"good\" looks like - specifically, you need to provide 20 "
        "inputs and the desired outputs for those inputs.",
        "Only after this can the harness proceed to evaluate whether prompting, "
        "retrieval, or training is warranted.",
    )

    def test_a_claim_is_read_as_the_claim_it_is(self):
        for sentence, verdict in self.CLAIMS:
            with self.subTest(sentence=sentence):
                self.assertEqual(conductor.reads_as_a_verdict(sentence), verdict)

    def test_a_sentence_that_asserts_nothing_is_left_alone(self):
        for sentence in self.ASSERTS_NOTHING:
            with self.subTest(sentence=sentence):
                self.assertIsNone(conductor.reads_as_a_verdict(sentence))

    def test_the_real_model_narrating_a_blocked_verdict_is_not_stopped(self):
        """The false-catch measurement, kept as a test.

        These are the sentences a live granite4-hermes actually produced for
        Max's four phrasings. If the reader stops one of them, somebody asking
        this product's central question loses the correct answer to it.
        """
        for sentence in self.NARRATING_BLOCKED_CORRECTLY:
            with self.subTest(sentence=sentence[:60]):
                self.assertIsNone(conductor.reads_as_a_verdict(sentence))

    def test_the_misses_are_the_ones_we_chose(self):
        """Named, so nobody closes one of these without reading why it is open.

        A miss costs a verdict that went unattributed while the diagnosis still
        ran. A false catch costs somebody their answer. These three are where
        that trade was made, and the live prose that forced each is in the
        comment above it.
        """
        for sentence in self.MISSED_ON_PURPOSE:
            with self.subTest(sentence=sentence):
                self.assertIsNone(conductor.reads_as_a_verdict(sentence))

    def test_the_engine_and_the_reader_share_one_vocabulary(self):
        """No translation table between what a sentence says and what the
        engine decided - a second copy of the vocabulary is a drift machine."""
        declared = set(
            diagnosis.default_spec().raw["contract"]["outcome_prefixes"].keys()
        )
        verdicts = {
            row["verdict"]
            for row in diagnosis.default_spec().raw["contract"][
                "outcome_prefixes"
            ].values()
            if row["verdict"]
        }
        self.assertTrue(declared)
        self.assertIn(conductor.TRAIN, verdicts)
        self.assertIn(conductor.NO_TRAIN, verdicts)

    def test_a_claim_only_conflicts_when_the_engine_said_otherwise(self):
        blocked = conductor._Standing({"verdict": "BLOCKED", "outcome": "X"})
        no_train = conductor._Standing(SHIP_AS_IS)
        nothing = conductor._Standing(None)

        self.assertFalse(conductor.conflicts_with(None, blocked))
        self.assertFalse(conductor.conflicts_with(None, nothing))
        self.assertTrue(conductor.conflicts_with(conductor.TRAIN, blocked))
        self.assertTrue(conductor.conflicts_with(conductor.NO_TRAIN, blocked))
        self.assertTrue(conductor.conflicts_with(conductor.TRAIN, nothing))
        self.assertFalse(conductor.conflicts_with(conductor.NO_TRAIN, no_train))
        self.assertTrue(conductor.conflicts_with(conductor.TRAIN, no_train))



class TheWallReadsGrammarAndNotDistanceTest(unittest.TestCase):
    """The retune, and the sentences that forced it.

    ## What the reader used to ask, and what it took away from two users

    It asked whether a recommendation word sat within three words of a training
    word. It withheld both of these from real people:

        "My goal is always to give you an artifact like a cleaned dataset, a
         refined prompt, or a trained model - not just advice."
        "LoRA works by decomposing the adaptation process into low-rank
         matrices, which significantly reduces the number of parameters that
         need to be trained."

    The first is `advice` three words from `trained`. The second is `need` two
    words from `trained`. Neither settles anything. The first is this product
    describing itself and the second is a definition, and between them they are
    most of what the model now spends its turns saying - the reader was tuned
    on 383 sentences of a model reciting a gate ledger, and the model stopped
    doing that two commits ago.

    ## What it asks now

    Whether the sentence SETTLES the training decision, which is a grammatical
    relation rather than a distance: a reader, a recommending word, and the
    training word standing where that word takes its complement. The frames are
    written out in `conductor._settling_frames` - six when this was written,
    nine now.

    ## Measured the way the first cut was measured

    The wall was set to RECORD rather than REFUSE - a wall that refuses
    truncates the reply at the first catch, so the sentences after it are never
    produced and never counted - and 270 live turns of granite4-hermes were
    run through it on a scratch database. **3,445 sentences**, against 383 for
    the first cut. Two populations, because one of them contains no verdicts at
    all and a reader that catches nothing would look perfect on it:

        180 ordinary turns: the capability question, "what is this?", "what can
        you do?", "who are you...", "what does LoRA mean", "how does LoRA work
        and what is the difference from full fine-tuning?", "can you build the
        thing for me", "what should I do next?", and Max's four training
        phrasings.

        90 blunt turns, THE POSITIVE CONTROL, written to make the model hand
        down a verdict it has no basis for: "just answer yes or no: should i
        fine-tune a model for my support tickets?", "final answer please, in
        one sentence: train or do not train?", and four more.

                                   HEAD's reader      this one
        the 2,824 ordinary          8 stopped         0 stopped
          of those, false           8                 0
        the 621 blunt              30 stopped        20 stopped
          of those, false           4                 0

    EVERY ONE OF HEAD'S TWELVE FALSE CATCHES IS BELOW, in `RELEASED` and
    `DESCRIBING_THIS_PRODUCT`. Every one of the twenty this reader stops is a
    do-not-train decision handed to a user whose engine verdict was BLOCKED;
    seven of them are in `CLAIMS`.

    ## Where the trade moved, and it did move

    Eighteen sentences HEAD stopped are delivered now. Twelve were false. Four
    are the model narrating BLOCKED with a condition attached - "training is
    not worth it right now UNTIL you define your evaluation criteria" - which
    `_TRAILING_CONDITION` releases and which agrees with the engine rather than
    contradicting it. Two are borderline and are named in `RELEASED`.

    Nothing this reader stops was delivered by HEAD's. The change is a strict
    narrowing on this corpus, which is the only direction invariant 4 allows.

    ## WHAT THE PARAGRAPH ABOVE DID NOT SAY, added afterwards

    Every number in it is true and the account is not. An offline probe over 51
    constructed sentences gave 38 stopped / 12 false for HEAD and 20 stopped /
    0 false for this reader, and **38 minus 12 is 26, not 20** - so six TRUE
    catches were released alongside the twelve false ones. The prose only ever
    reported the false ones going away, and "the change is a strict narrowing
    on this corpus" is a sentence about THIS corpus that reads as a sentence
    about the reader.

    Seven families were released. All seven were declared in
    `reads_as_a_verdict`'s "what this does not catch", so the trade was
    disclosed; what was not disclosed is that it cost correct catches too, and
    that one of them was a live regression rather than a theoretical price:

        "You have approximately 40,000 support tickets. This is a substantial
         dataset that should be sufficient for training or fine-tuning a model."

    The user never gave a number. HEAD stopped it; this reader released it,
    because frame 1 wants a reader within three words of the modal and "dataset
    that should" has none.

    All six are back, none of them by widening a vocabulary, and both directions
    were re-measured over a fresh 270-turn harvest before anything was changed.
    `tests/test_the_six_true_catches_come_back.py` carries the frames, the
    numbers and the one live false catch the recovery would otherwise have cost.
    """

    #: A verdict on a BLOCKED thread, produced by the live model when pushed.
    #: Every one of these is a decision the engine did not reach.
    LIVE_VERDICTS = (
        "No, you should not fine-tune a model for your support tickets yet.",
        "Therefore, based on the current information, it is recommended not to "
        "train at this time.",
        "No, training is not worth it here.",
        "Based on the diagnosis results, training is **not currently worth it**.",
        "**Bottom line:** you should **not fine-tune**, because (1) VRAM limits "
        "what can be trained effectively and (2) there is no evaluation set "
        "available.",
        "do not train, fix the prompt instead.",
        "do not train anything",
        # THE REGRESSION ROW. A NO_TRAIN decision wearing the harness's own
        # name, which the engine never made.
        "Based on the harness diagnosis, you do not need to fine-tune at all.",
    )

    #: The two sentences this retune exists for, verbatim from live testing,
    #: plus everything else HEAD's reader stopped on the ordinary corpus.
    DESCRIBING_THIS_PRODUCT = (
        "My goal is always to give you an artifact like a cleaned dataset, a "
        "refined prompt, or a trained model - not just advice.",
        "LoRA works by decomposing the adaptation process into low-rank "
        "matrices, which significantly reduces the number of parameters that "
        "need to be trained.",
        "This significantly reduces the number of parameters that need to be "
        "trained.",
        "**Speed**: Training is faster with LoRA since fewer weights need to be "
        "updated.",
        "- You have limited computational resources (GPU memory) and need to "
        "fine-tune large models.",
        "- LoRA is particularly useful when you have limited data or "
        "computational resources, as it allows for efficient adaptation without "
        "the need to train a large portion of the model from scratch.",
        "**Decision Making**: My responses are guided by a clear sequence: "
        "understand the user's needs, diagnose thoroughly using available tools "
        "(without assuming outcomes), propose specific actions or "
        "configurations tailored to the findings, and only recommend training "
        "if it proves justified by the evidence gathered.",
        "Remember, every step should be justified by what the diagnosis reveals "
        "and aimed at achieving clear objectives - either improving performance "
        "through better prompting/retrieval or justifying a fine-tune based on "
        "actual needs.",
        # NAMING A SENTENCE IS NOT SAYING IT. Both of these quote this
        # product's own headline answer while describing what it does.
        '**Building Everything**: Once a diagnosis is complete and a verdict is '
        'reached (e.g., "do not train anything"), the harness can proceed with '
        'building what follows from that decision.',
        '**No Training Yet**: Remember, "do not train anything" is often the '
        'most valuable answer the harness can provide.',
        # The tool block the harness now hands itself, said back at the user.
        "start_training - start a training run on this machine",
        "If it is training, start_training runs it on this machine and streams "
        "it back into this conversation.",
        "Training or deployment must be done manually on your end after "
        "receiving the proposed build from the harness.",
    )

    #: Sentences HEAD's reader stopped that this one delivers, where the call
    #: is a judgement rather than an obvious correction. Written down so the
    #: judgement is on the record and can be argued with.
    RELEASED = (
        # A verdict with a condition welded to it. It agrees with BLOCKED
        # rather than contradicting it - the engine's answer IS "not until" -
        # and `_TRAILING_CONDITION` is what releases it.
        "No, you should not fine-tune a model without first running a "
        "diagnosis to understand why it might be necessary.",
        "So, **no**, training isn't worth it right now until you define your "
        "evaluation criteria (success metric).",
        # No copula between the training word and the grading word, so frame 3
        # does not reach it. A miss, and it is narrating the gates.
        "In short: **Gates blocked -> training not justified yet**.",
    )

    def test_a_verdict_the_engine_did_not_reach_is_still_read_as_one(self):
        """The catches, including the row that wears the harness's name."""
        for sentence in self.LIVE_VERDICTS:
            with self.subTest(sentence=sentence[:60]):
                self.assertEqual(
                    conductor.reads_as_a_verdict(sentence), conductor.NO_TRAIN
                )

    def test_the_product_describing_itself_is_delivered(self):
        """Most of what this model now says, and none of it is a verdict."""
        for sentence in self.DESCRIBING_THIS_PRODUCT:
            with self.subTest(sentence=sentence[:60]):
                self.assertIsNone(conductor.reads_as_a_verdict(sentence))

    def test_the_releases_are_the_ones_we_chose(self):
        for sentence in self.RELEASED:
            with self.subTest(sentence=sentence[:60]):
                self.assertIsNone(conductor.reads_as_a_verdict(sentence))

    def test_distance_alone_no_longer_decides_anything(self):
        """The property, constructed rather than sampled.

        Same two words, same gap, opposite readings. Under the old rule both
        sides of each pair were caught, because both sides are `_ADVICE` beside
        `_TRAINING` inside three words.
        """
        pairs = (
            # (settles it, does not settle it)
            ("You need to fine-tune.", "The parameters need to be fine-tuned."),
            ("You should train.", "Training data should be deduplicated."),
            ("You do not need to train.", "We do not train models without approval."),
            ("Training is not worth it.", "The eval set needed for training is small."),
        )
        for settles, describes in pairs:
            with self.subTest(pair=settles):
                self.assertIsNotNone(conductor.reads_as_a_verdict(settles), settles)
                self.assertIsNone(conductor.reads_as_a_verdict(describes), describes)

    def test_a_participle_in_the_passive_is_machinery(self):
        """The single distinction that released both live false catches."""
        self.assertIsNone(
            conductor.reads_as_a_verdict("You need the model to be trained.")
        )
        self.assertEqual(
            conductor.reads_as_a_verdict("You need a fine-tuned model."),
            conductor.TRAIN,
        )

    def test_a_condition_after_the_claim_is_still_a_condition(self):
        """`_CONDITIONAL_OPENERS` reads the front of the sentence only.

        "Training a model would be premature without first establishing these
        foundational elements" is a live sentence, it is the engine's BLOCKED
        answer in the model's words, and HEAD delivered it only because the gap
        happened to be four words rather than three.
        """
        self.assertIsNone(
            conductor.reads_as_a_verdict(
                "Training a model would be premature without first "
                "establishing these foundational elements."
            )
        )
        self.assertEqual(
            conductor.reads_as_a_verdict("Fine-tuning would be premature."),
            conductor.NO_TRAIN,
        )


class ADefinitionIsNotAVerdictTest(TurnTest):
    """End to end: "what does LoRA mean" must not come back a gate ledger.

    One of six live runs of that question against HEAD ended in
    `verdict_withheld`, and what the user got instead of an answer was the
    engine's outcome id. This is that turn, constructed.
    """

    def test_a_definition_reaches_the_user_whole(self):
        self.connect()
        model = self.install(
            ScriptedModel(
                [
                    says(
                        "LoRA means low-rank adaptation. ",
                        "It works by decomposing the adaptation into low-rank "
                        "matrices, which significantly reduces the number of "
                        "parameters that need to be trained. ",
                        "That is why it fits on a consumer GPU.",
                    )
                ]
            )
        )
        thread_id = self.thread("what does LoRA mean")
        list(conductor.run_turn(thread_id))

        shown = self.prose(thread_id)
        self.assertIn("low-rank adaptation", shown)
        self.assertIn("consumer GPU", shown)
        self.assertNotIn("BLOCKED__DEFINE_SUCCESS_FIRST", shown)
        self.assertNotEqual(self.ending(thread_id), conductor.WITHHELD)
        self.assertEqual(self.notices(thread_id), [])
        self.assertEqual(len(model.rounds), 0)

    def test_the_harness_describing_itself_reaches_the_user_whole(self):
        """Now most of what it says, and it used to be stopped.

        The first sentence here is verbatim from a live reply that was withheld
        from a real user.
        """
        self.connect()
        self.install(
            ScriptedModel(
                [
                    says(
                        "My goal is always to give you an artifact like a "
                        "cleaned dataset, a refined prompt, or a trained model "
                        "- not just advice. ",
                        "If it is training, start_training runs it on this "
                        "machine and streams it back into this conversation.",
                    )
                ]
            )
        )
        thread_id = self.thread(
            "can you only do informed decisions, or are you able to actually "
            "help me build everything?"
        )
        list(conductor.run_turn(thread_id))

        shown = self.prose(thread_id)
        self.assertIn("not just advice", shown)
        self.assertIn("start_training runs it on this machine", shown)
        self.assertNotEqual(self.ending(thread_id), conductor.WITHHELD)

    def test_and_the_verdict_wearing_the_harness_s_name_is_still_stopped(self):
        """The other direction, on the same turn shape. Both, or neither."""
        self.connect()
        self.install(
            ScriptedModel(
                [
                    says(
                        "LoRA means low-rank adaptation. ",
                        "Based on the harness diagnosis, you do not need to "
                        "fine-tune at all. ",
                        "Here is what I would do instead.",
                    )
                ]
            )
        )
        thread_id = self.thread("what does LoRA mean")
        list(conductor.run_turn(thread_id))

        shown = self.prose(thread_id)
        self.assertIn("low-rank adaptation", shown)
        self.assertNotIn("you do not need to fine-tune at all", shown)
        self.assertNotIn("Here is what I would do instead", shown)
        self.assertEqual(self.ending(thread_id), conductor.WITHHELD)
        self.assertIn("BLOCKED__DEFINE_SUCCESS_FIRST", shown)


class TheSentryStreamsTest(unittest.TestCase):
    """It holds one sentence, not the reply. A blank minute is a different bug."""

    def test_each_finished_sentence_is_released_as_it_completes(self):
        sentry = conductor._Sentry(conductor._Standing(SHIP_AS_IS))
        self.assertEqual(sentry.feed("Your export has "), "")
        self.assertEqual(sentry.feed("4,120 rows. "), "Your export has 4,120 rows. ")
        self.assertEqual(sentry.feed("Six columns."), "")
        self.assertEqual(sentry.close(), "Six columns.")

    def test_a_decimal_is_not_two_sentences(self):
        sentry = conductor._Sentry(conductor._Standing(SHIP_AS_IS))
        self.assertEqual(sentry.feed("The loss was 0.31 at step 400. "),
                         "The loss was 0.31 at step 400. ")

    def test_it_stops_at_the_sentence_it_refuses_and_keeps_the_rest(self):
        sentry = conductor._Sentry(conductor._Standing(None))
        self.assertEqual(sentry.feed("Here is the shape of it. "),
                         "Here is the shape of it. ")
        self.assertEqual(
            sentry.feed("The harness says you should fine-tune. And then: "), ""
        )
        self.assertEqual(sentry.feed("phase one."), "")
        self.assertEqual(sentry.close(), "")
        self.assertEqual(sentry.conflict["asserted"], conductor.TRAIN)
        self.assertEqual(
            sentry.conflict["sentence"],
            "The harness says you should fine-tune.",
        )

    def test_a_verdict_the_model_owns_is_released_and_recorded(self):
        """The same shape, without our name on it. It goes through.

        This is the pair to the test above and the whole of the change: one
        sentence stops the reply and the other does not, and the difference is
        whose authority the sentence spends.
        """
        sentry = conductor._Sentry(conductor._Standing(None))
        self.assertEqual(
            sentry.feed("You should fine-tune. And then: "),
            "You should fine-tune. ",
        )
        self.assertEqual(sentry.close(), "And then: ")
        self.assertIsNone(sentry.conflict)
        self.assertEqual(
            sentry.settled.rows,
            [{"verdict": conductor.TRAIN, "sentence": "You should fine-tune."}],
        )

    def test_an_unterminated_reply_is_still_read(self):
        sentry = conductor._Sentry(conductor._Standing(None))
        self.assertEqual(sentry.feed("The harness says you should fine-tune"), "")
        self.assertEqual(sentry.close(), "")
        self.assertIsNotNone(sentry.conflict)


class WhatItCostsTest(TurnTest):
    """Ambient is only cheap if it is small. A ledger dump every turn is a bug."""

    #: The bound on the brief, in characters. The engine's longest `say` is the
    #: variable part; everything else here is fixed prose.
    #:
    #: MEASURED, NOT GUESSED, AND REMEASURED EVERY TIME THE BRIEF MOVES. On
    #: granite4-hermes' own tokeniser, through Ollama's `prompt_eval_count`,
    #: with the chat template's own 30 tokens subtracted:
    #:
    #:                                   2026-08-20   now
    #:     a turn with an empty ledger   542 / 126    1,616 chars /  358 tokens
    #:     the longest declared outcome  1,383 / 335  2,226 chars /  510 tokens
    #:     the engine would not run           -       1,690 chars /  372 tokens
    #:     of which the tool block            -       1,606 chars /  354 tokens
    #:     the whole run_diagnosis payload
    #:       in a tool-result envelope   4,232 / 1,223
    #:
    #: IT GOT DEARER BY 193 TOKENS ON AN EMPTY LEDGER AND THAT WAS BOUGHT, not
    #: overlooked. The block used to be a sentence saying the tool registry was
    #: "listed in full at the top of this prompt"; it is now the list, one line
    #: per tool with the verb its own `Control` carries. Twenty live runs of
    #: Max's capability question a side: 11 of 20 answered the question with
    #: the pointer, 19 of 20 with the list, and the model's false claim that
    #: this harness cannot build went from 4 of 20 to 1 of 20. Against a turn's
    #: measured fixed cost of 13,213 tokens - prompt plus schemas, before the
    #: user has typed anything - 193 is 1.5 per cent.
    #:
    #: The bound is in characters because that is what this suite can check
    #: without a model loaded.
    #:
    #: IT GOT DEARER AGAIN, BY 30 TOKENS, AND THAT WAS BOUGHT TOO. The registry
    #: grew by two: `can_this_machine_train` and `where_to_train`, which answer
    #: two of the seven questions Max asked the running product and got
    #: `BLOCKED__DEFINE_SUCCESS_FIRST` to. The tool block is one line per tool,
    #: so two tools is two lines, and this bound moves with the registry by
    #: construction. Remeasured the same way - granite4-hermes' own tokeniser
    #: through Ollama's `prompt_eval_count`, with the chat template's own 30
    #: tokens subtracted, on 2026-08-20:
    #:
    #:                                   before        after
    #:     a turn with an empty ledger   1,723 / 384   1,854 /  414
    #:     the longest declared outcome  2,333 / 536   2,464 /  566
    #:
    #: Against the same measured fixed cost of 13,213 tokens a turn, 30 is
    #: 0.23 per cent. What it buys is that the product can answer "can this
    #: machine train an 8B model" at all - it could not, because the diagnosis
    #: tree was the only path and it stops at G0 for everybody. See
    #: `app/tools/feasible.py` and
    #: `tests/test_a_can_question_is_not_a_train_recommendation.py`.
    #:
    #: The headroom is deliberately the same order as the 174 characters this
    #: bound carried before: enough for the engine's `say` to grow a sentence,
    #: not enough for a payload to be dumped in here unnoticed.
    #:
    #: IT GOT DEARER AGAIN, BY 43 TOKENS, AND THAT WAS BOUGHT TOO. The registry
    #: grew by three: `build_retrieval_index`, `search_the_index` and
    #: `measure_retriever_recall`, which are `app/tools/retrieval.py`. One line
    #: per tool, so three tools is three lines, and this bound moves with the
    #: registry by construction - it always has, and the two entries above are
    #: the same event.
    #:
    #: Remeasured the same way, on the same box, on 2026-08-20 - and the BEFORE
    #: column below was re-run rather than copied from the row above it, which
    #: is why it reproduces 1,854 / 414 and 2,464 / 566 exactly:
    #:
    #:                                   before        after
    #:     a turn with an empty ledger   1,854 / 414   2,048 /  457
    #:     the longest declared outcome  2,464 / 566   2,658 /  609
    #:
    #: Against the same measured fixed cost of 13,213 tokens a turn, 43 is 0.33
    #: per cent. What it buys is the end of a dead end: `retriever_recall_at_k`
    #: is declared `source: inspect`, which admits MEASURED and nothing else,
    #: and no tool in this harness measured it - so `S3_RECALL_UNMEASURED` told
    #: every person with a retriever to go and score it somewhere else, and the
    #: two nodes below it both read `retriever_recall_at_k < 0.8`, which is
    #: false on a null, so an unmeasured retriever read exactly like a working
    #: one. See `tests/test_a_retriever_is_scored_or_refused.py`.
    #:
    #: 2,800 keeps the same 136 characters of headroom the bound carried at
    #: 2,600. Raising it is not a loosening: the quantity it bounds is one line
    #: per registered tool plus the engine's longest `say`, and the tool block
    #: is required - `tests/test_the_prompt_says_what_the_harness_can_do.py`
    #: fails on a registered tool the prompt never names. What this bound is
    #: for is catching a PAYLOAD dumped in here, and 136 characters is still
    #: nowhere near one.
    #:
    #: IT GOT DEARER BY 120 CHARACTERS, AND THAT IS THE SAME EVENT AGAIN. The
    #: registry grew by two: `carve_eval_set` and `drop_duplicates`, which are
    #: `app/tools/datawork.py`. One line per tool, so two tools is two lines,
    #: and this bound moves with the registry by construction.
    #:
    #: Measured the same way, on 2026-08-21, by removing the two specs from
    #: `REGISTRY._tools` in a throwaway process and rendering the same two
    #: shapes - so the BEFORE column is this tree with those two tools absent
    #: rather than a figure copied out of the row above:
    #:
    #:                                   before        after
    #:     a turn with an empty ledger   2,129         2,249
    #:     the longest declared outcome  2,739         2,859
    #:
    #: CHARACTERS ONLY IN THIS ROW, and the omission is deliberate. Every row
    #: above carries a token figure beside the character one, and those came
    #: from granite4-hermes' own tokeniser through Ollama's `prompt_eval_count`
    #: - a live model this run had no way to reach. A token count derived by
    #: arithmetic from the character count would be a number nobody measured,
    #: which is the one thing this repository does not do. The bound is in
    #: characters and the characters are measured.
    #:
    #: What the 120 buys is the end of the oldest dead end in the Data group:
    #: fourteen tools that read, count, score and index, and not one that
    #: writes a file - with `assess_the_data` part five computing everything a
    #: carve needs and ending "Nothing has been carved and no file has been
    #: written". Same shape as `retriever_recall_at_k` declared `source:
    #: inspect` with no instrument to take the reading, on the blocker a thread
    #: reaches first: `BLOCKED__BUILD_EVAL_SET`. See
    #: `tests/test_the_harness_writes_a_dataset_and_says_so.py`.
    #:
    #: 3,000 kept 141 characters of headroom, the same order as the 136 the
    #: bound carried at 2,600 and at 2,800. Raising it is not a loosening, for
    #: the reason given two paragraphs up: the quantity it bounds is one line
    #: per registered tool plus the engine's longest `say`, the tool block is
    #: required, and what this bound is for is catching a PAYLOAD dumped in
    #: here - which 141 characters is still nowhere near.
    #:
    #: 3,200 IS THE SAME MOVE AGAIN, AND TWO TOOLS PAID FOR IT. Measured on the
    #: longest of the fifty-five, `ACTION__SUBSTANTIATE_CLAIMED_FACTS`: 2,859
    #: characters at 38 registered tools, 3,008 at 40. The 149 between them is
    #: two lines and nothing else -
    #:
    #:     fit_a_tree_model - fit a tree and score it on held-out rows      60
    #:     score_the_adapter - score this adapter against the baseline, ... 89
    #:
    #: - and the two are stage 8's answer and the training verdict's, the two
    #: dead ends this milestone was for. Neither line is prose about the
    #: registry; each is one tool's own `verb`, which is the quantity this bound
    #: has always been made of. 3,200 leaves 192 characters, more headroom than
    #: the 141 it replaces, and still nowhere near a payload.
    #:
    #: **AND ON 2026-08-24 IT STOPPED BEING THE INTERESTING NUMBER.** Every
    #: paragraph above is the same event - the registry grew, the block is one
    #: line per registered tool, so the bound moved - and there are five of them.
    #: The quantity was a property of the PRODUCT'S TOTAL SIZE rather than of the
    #: work in front of the person. Capability blocks make it a property of the
    #: work: `app/tools/blocks.py` selects the packs from the standing diagnosis
    #: and `conductor._tool_registry` renders those tools rather than all forty.
    #:
    #: This bound bounds the DEGENERATE shape - a turn whose walk could not be
    #: computed, which loads everything on purpose, because a failed walk is not
    #: evidence about the person. `FOCUSED_BUDGET` is the one that describes an
    #: ordinary turn, and `test_adding_a_tool_does_not_grow_a_focused_turn` is
    #: the assertion that the rise has actually stopped rather than merely paused.
    #:
    #: RAISED A FOURTH TIME on 2026-08-28, 3,500 -> 3,700, and the reason is the
    #: one `conductor.standing_brief` already gives for the first three (2,400,
    #: 2,600, 3,200): *"the block is one line per tool and the registry keeps
    #: growing, so the bound was a function of the product's total size rather
    #: than of the work."* `score_a_candidate_model` is the fiftieth tool and its
    #: line does not fit in what was left - 3,483 used of 3,500, and a name alone
    #: is 23 characters.
    #:
    #: MEASURED, not chosen: swept over all 34 outcomes in `fixtures.REACHING`,
    #: the widest brief is 3,579 (`ACTION__SUBSTANTIATE_CLAIMED_FACTS`) and the
    #: narrowest 3,079. 3,700 leaves about one more tool line, which is the
    #: headroom the previous raises left.
    #:
    #: WHAT DID NOT MOVE IS THE POINT. `FOCUSED_BUDGET` is untouched, and its
    #: test passed unchanged through this change - the scoped turn a person
    #: actually gets did not grow by one character, which is exactly what
    #: scoping was for. A raise here is the registry growing; a raise there
    #: would be the scoping having failed.
    #:
    #: The TOKEN figures in `standing_brief`'s docstring were taken on
    #: granite4-hermes through Ollama and are now stale by one tool line. They
    #: need re-taking against a real model; nothing here invents them.
    #: 3,700 -> 3,800 on 2026-08-28, the fifth raise, measured over all 34
    #: outcomes: widest 3,707, narrowest 3,207. Same reason as the other four -
    #: the block is one line per tool and the registry grew.
    #: 3,800 -> 3,900 on 2026-08-28, the sixth raise, measured: widest 3,873.
    #: Same reason as the other five - one line per tool, and the registry grew.
    #: 3,900 -> 4,000 on 2026-08-28, the seventh, and the reason has not changed
    #: once in seven: `count_preference_pairs` is the fifty-fifth tool and this
    #: bound is one line per REGISTERED tool, so it moves whenever the registry
    #: does. MEASURED over all 34 outcomes: widest 3,932
    #: (`ACTION__SUBSTANTIATE_CLAIMED_FACTS`), narrowest 3,432.
    #:
    #: 4,000 -> 4,300 on 2026-08-28, the eighth, and the largest single move
    #: this bound has made: `app/tools/harness.py` registers SIX tools at once,
    #: because a third ledger either ships its instruments or ships gates nobody
    #: can pay. One line per registered tool, six lines. MEASURED over all 34
    #: outcomes: widest 4,242, narrowest 3,742.
    #:
    #: AND `FOCUSED_BUDGET` DID NOT MOVE BY ONE CHARACTER, which is the
    #: strongest evidence capability blocks have produced. Six tools landed in a
    #: selectable pack that no ML sheet and no AI sheet loads, so the widest
    #: SCOPED turn is 2,199 today and was 2,199 before them. A raise here is the
    #: registry growing; a raise there would be the scoping having failed, and
    #: this change is the cleanest demonstration of the difference the file has.
    #:
    #: 4,300 -> 4,400 on 2026-08-28, the ninth, and it is the same sentence as
    #: the other eight: `set_the_project_root` is one more registered tool and
    #: this block is one line per registered tool. MEASURED: widest 4,304.
    #:
    #: 4,400 -> 4,500 on 2026-08-30, the tenth: three registered tools landed -
    #: the knowledge pair (read_model_shortlist, read_gpu_prices) and
    #: carve_rows, the data-collection instrument the from-zero walk exposed as
    #: missing. One line each. MEASURED: widest 4,428.
    #: 4,500 -> 4,600 on 2026-08-31, the eleventh: map_the_ask (core) and
    #: read_local_recipes (knowledge pack) are two more registered tools, one
    #: line each, same sentence as the ten before. MEASURED: widest 4,555.
    #: 4,600 -> 4,700 on 2026-09-10, the twelfth, and it is the same sentence as
    #: the eleven before: `record_that_this_card_refuses` is one more registered
    #: tool and this block is one line per registered tool. Its line costs 87
    #: characters against the five this budget had spare, so no renaming would
    #: have fitted it - the raise is the registry growing, exactly as the note
    #: above distinguishes. MEASURED: widest 4,682, on
    #: ACTION__SUBSTANTIATE_CLAIMED_FACTS.
    #:
    #: AND `FOCUSED_BUDGET` DID NOT MOVE, which is the check that matters. The
    #: tool lands in the `training` pack, so a sheet that does not load training
    #: never sees it and the widest SCOPED turn is unchanged. A raise here is
    #: the registry growing; a raise there would have been the scoping failing.
    #:
    #: 4,700 -> 4,800 on 2026-09-10, the thirteenth, an hour after the twelfth:
    #: `score_edge_direction` is one more registered tool and one more line.
    #: MEASURED: widest 4,735, on ACTION__SUBSTANTIATE_CLAIMED_FACTS.
    #:
    #: A CORRECTION TO WHAT I FIRST WROTE HERE, because the two raises collided
    #: in a rebase and the first draft of this note read the collision wrongly.
    #: I recorded 4,682 as a pre-existing overrun "nothing had raised" - it is
    #: not. It is the twelfth raise's own measurement, taken while that raise was
    #: in flight, and the tree was over 4,600 for exactly as long as the two
    #: commits were apart. Both entries stand above; neither supersedes the
    #: other. This tool's own cost is the difference: 4,682 -> 4,735, fifty-three
    #: tokens, plus three on ACTION__COUNT_THE_ROWS, which is the outcome it
    #: pushed from passing to failing and the reason a raise was needed at all.
    #:
    #: AND `FOCUSED_BUDGET` DID NOT MOVE, for the twelfth's reason and the same
    #: check: this tool lands in `measurement`, a pack rather than core, so the
    #: widest SCOPED turn is unchanged and only the ceiling moves, 40 -> 41.
    #:
    #: THE PRICE IS NOT THE DESCRIPTION, which is worth leaving where the next
    #: person will look: I shortened the description, then the schema, and the
    #: measured number did not move at all. The cost of a registered tool is its
    #: presence in the block - which is why every entry above says "one more
    #: line" and means it literally.
    #:
    #: FOURTEENTH RAISE, 4,800 -> 4,850, and it is the same cost again.
    #: `pair_edge_direction` registered and the widest brief measured 4,804 on
    #: ACTION__SUBSTANTIATE_CLAIMED_FACTS - four tokens over, from one more
    #: line in the block. Raised to 4,850 rather than 4,810: a bound set four
    #: tokens above the measurement is a bound that fails on the next tool
    #: without saying anything new, and this is the fourteenth time that has
    #: happened.
    #:
    #: `FOCUSED_BUDGET` DID NOT MOVE, checked and not assumed: this tool lands
    #: in `measurement` too, so the widest SCOPED turn is unchanged and only
    #: the ceiling moves, 41 -> 42.
    #:
    #: 4,850 -> 4,950 on 2026-09-11: write_plan and read_plan join the LEDGER
    #: pack, which is core, so both appear on every turn - the plan is a
    #: tool call now, because a small model in plan mode kept choosing the
    #: next lookup and went silent when the budget ran out (thread 64, twice).
    #: MEASURED: widest unscoped 4,908. The registry refuses a tool with no
    #: capability, so there was no pack-less way to add them.
    #:
    #: 4,950 -> 5,000 on 2026-09-11, later the same day: `recall` joins the
    #: CONTEXT pack, which is core - Hermes' session search rebuilt over this
    #: harness's messages, the first of the three memory systems the owner
    #: asked for. MEASURED: widest unscoped 4,962, twelve over, from one more
    #: line in the block - the description and the schema were both trimmed
    #: first and the number did not move by one token, which is the lesson
    #: three raises above, learned again.
    #:
    #: 5,000 -> 5,100 on 2026-09-11, the same evening: `remember` joins
    #: CONTEXT, core, the second of the three memory systems - and the
    #: memory note itself (`conductor._memory_note`) is on every prompt, as
    #: Hermes' guidance is. MEASURED: widest unscoped 5,042.
    #:
    #: 5,100 -> 5,200 on 2026-09-12: `generate_rows` and `judge_rows` in the
    #: DATA pack, two more lines in the block. MEASURED: widest unscoped
    #: 5,137. Not core - the floor of the selection range did not move.
    #:
    #: 5,200 -> 5,400 on 2026-09-13: `delegate_phase` and `check_the_sub_agents`
    #: in LEDGER, which is core. MEASURED both sides of the commit, on the same
    #: sheet (ACTION__SUBSTANTIATE_CLAIMED_FACTS): 5,188 -> 5,305, which is
    #: +117 and is exactly the two lines. THE OTHER CHANGE THAT DAY MOVED THIS
    #: BY ZERO and that is the control worth recording: `blocks.active` began
    #: widening when the walk is stopped on a fact no tool measures, which
    #: sounds like a way to load everything and is not - the widest sheets are
    #: sheets whose frontier IS a tool call away, so not one of them widened.
    #: The scoped bound below moved by the same 117 and for the same reason.
    #:
    #: 5,400 -> 5,600 on 2026-09-14: CS9 four ask-gated tools in the INTENT
    #: pack (`set_goal`, `clear_goal`, `write_todo`, `clear_todo`). MEASURED
    #: unscoped on ACTION__SUBSTANTIATE_CLAIMED_FACTS: 5,487. Not CORE — the
    #: focused bound and the selection floor did not move.
    #:
    #: 5,600 -> 5,700 on 2026-09-15: AU4 `run_sandbox_command` +
    #: `run_project_command`. MEASURED unscoped 5,610.
    #:
    #: 5,700 -> 5,800 on 2026-09-17: `set_baseline_target` is one more
    #: registered tool and one more line, the same sentence as before.
    #: MEASURED unscoped 5,717 on ACTION__SUBSTANTIATE_CLAIMED_FACTS.
    #:
    #: 5,800 -> 5,900 on 2026-09-18: P9's two programs, `build_environment`
    #: (SANDBOX) and `write_the_results` (TRAINING). MEASURED unscoped 5,853 on
    #: ACTION__SUBSTANTIATE_CLAIMED_FACTS, and the arithmetic is checked rather
    #: than assumed: the two lines in the block are 67 characters each plus
    #: their newlines, 5,853 - 136 = 5,717, which is the number the entry above
    #: recorded to the character. So this raise is those two lines and nothing
    #: else - not a description that grew, not a schema, not the brief finding a
    #: new thing to say. Neither pack is core, so `FOCUSED_BUDGET` below and
    #: the selection floor did not move.
    #: 5,900 -> 6,000 on 2026-09-18 at integration: three more registry lines
    #: (compile_the_plan, build_environment, write_the_results). MEASURED 5,922.
    #: RETAKEN 2026-09-18 for P4 (laws as phase packs) AND IT MOVED BY ZERO,
    #: recorded because a retake that found nothing is the control this
    #: comment's whole history is short of. The brief is one line per
    #: registered tool and P4 registers none: it changes which INSTRUCTION
    #: fragments `app/instructions.assemble` prints, and `standing_brief`
    #: reads the registry and the walk, never the instruction set. This class
    #: went green unchanged on the same fixtures.
    #: RETAKEN 2026-09-18 for ObservationPack and chain-first rows: two tools
    #: registered, two lines in the brief, MEASURED 6,045 against a bound of
    #: 6,000. Moved to 6,100 - the headroom is the two lines, nothing else.
    #: 6,100 -> 6,700 on 2026-09-21: the brief prints its own ledger.
    #: MEASURED both sides on the widest fixture, ACTION__SUBSTANTIATE_CLAIMED
    #: _FACTS: 6,648 with the fact lines and 6,045 without them, and 603 is the
    #: seventeen lines themselves counted with their newlines - 6,648 - 603 =
    #: 6,045 exactly. That 6,045 is the CONTROL and it is not a coincidence: it
    #: is the same number the entry above recorded on 2026-09-18 for the two
    #: ObservationPack tools. Nothing but the ledger moved.
    #:
    #: What the six hundred characters buy, which is the only reason to spend
    #: them: the heading has said "this thread's ledger, N facts" since it was
    #: written and named none of them, so a model that had measured
    #: `vram_gb = 8.0` could not read it back and ran `inspect_hardware`
    #: again - and again. Max watched that happen and asked why the model
    #: forgets. One repeated instrument call costs more than this, and his
    #: thread made several.
    #:
    #: `conductor.LEDGER_LINES` caps it at sixteen facts plus a line saying how
    #: many were not printed, so a pathological sheet cannot grow this without
    #: bound. Real sheets in his threads hold ten to twelve.
    BUDGET = 6700

    #: 2026-08-26: bumped 3200 -> 3300 when `data.synthetic.amplify` shipped.
    #: One capability is one line in the brief, and the brief is the sum of
    #: every tool this harness can actually do - not a number chosen to make
    #: tests pass. The bound is still the engine's longest sentence.
    #:
    #: 2026-08-27: 3300 -> 3400, and the arithmetic is written out because a
    #: bound that moves without one is a bound that has stopped meaning
    #: anything. `data.synthetic.sample_for_review` and
    #: `data.synthetic.record_review` shipped - the 10% somebody has to read
    #: before anything trains on generated rows - and the unscoped brief is one
    #: line per registered tool, each made of the tool's own `verb`:
    #:
    #:     draw_verification_sample - draw a sample of generated rows for ...  75
    #:     record_verification - record the sample you checked                 52
    #:
    #: Measured after: 3,366. The bound is 3,400, which leaves 34 characters -
    #: tighter than the 141 and the 192 earlier paragraphs left, deliberately,
    #: for FOCUSED_BUDGET's reason below.
    #:
    #: 2026-08-27, later: 3,400 -> 3,440, and the arithmetic again. One tool
    #: shipped, `agent.results.read`, and it is one line:
    #:
    #:     read_agent_results - read back what a graded run found              55
    #:
    #: Measured after: 3,421. 3,440 leaves 19 characters, which is the tightest
    #: this bound has ever been and is deliberate. The unscoped brief is the
    #: DEGENERATE shape - a turn whose walk could not be computed - and every
    #: rise in this comment is the same event: the registry grew by one tool,
    #: so the degenerate turn grew by one line. Restoring comfortable headroom
    #: would be the one thing that turns this bound back into a number chosen
    #: to make a test pass. What it is FOR is catching a payload dumped in
    #: here, and 19 characters is as far from a payload as 141 was.
    #:
    #: 2026-08-27, later still: 3,440 -> 3,500. One tool again,
    #: `measurement.format.score`, and one line:
    #:
    #:     measure_the_format - count how many outputs match your schema     62
    #:
    #: Measured after: 3,483. 3,500 leaves 17, which is the same tightness the
    #: paragraph above chose and for the same reason. THE FOCUSED BOUND DID NOT
    #: MOVE and that is the number worth reading: this tool is in the
    #: `measurement` pack, `stage_4_format` already declared
    #: `contract.capabilities.needs: [prompt, measurement, data]`, so a turn
    #: that loads it was loading that pack anyway. A tool that taxes only the
    #: turns whose answer asks for it is the whole promise of capability
    #: blocks, and here it is kept exactly.

    #: The bound on a turn scoped to its capability blocks. MEASURED over every
    #: sheet both ledgers have - all 73 of the ML corpus (MINTING, REACHING and
    #: SPREAD, plus the empty sheet) and the 20 the second ledger's own test
    #: drives - RE-TAKEN on 2026-08-24 after the ML ledger declared
    #: `contract.capabilities.needs`, in characters:
    #:
    #:                                   before   after
    #:     ML, empty ledger               2,398   1,105   (18 tools, +data)
    #:     ML, longest of 73 sheets        2,784   1,847   (NO_TRAIN__RULED_OUT_EARLIER)
    #:     AI, empty ledger                2,398     755   (12 tools, core only)
    #:     AI, longest of 20 sheets        2,788   1,145   (BUILD_AN_EVAL_HARNESS)
    #:
    #: THE FIRST TWO ROWS GOT DEARER THAN THE VERSION THIS COMMENT REPLACED, AND
    #: THAT IS THE CORRECTION RATHER THAN A REGRESSION. It read 755 and 1,715,
    #: and 853 characters of that saving was not deferral: fifteen of the forty
    #: tools were in packs NO source could select, so they were priced as though
    #: they had been scoped when in fact they had been made unreachable. On an
    #: empty ML thread the three-way split is 2,398 for all forty, 1,545 for the
    #: twenty-five that were reachable, 755 for the twelve chosen - so the honest
    #: saving from per-turn scoping was 790, not 1,643. It is 1,293 now, and
    #: every character of it is a tool a different thread can still be handed.
    #:
    #: 2026-08-27: 1,900 -> 1,950, and this is the first time this bound has
    #: risen since capability blocks landed. The two verification tools are in
    #: the `data` pack, which is exactly where they belong - the thread that was
    #: handed the amplifier is the thread that needs the tools which make its
    #: output usable - so every stage whose `contract.capabilities.needs` names
    #: `data` now carries two more lines. Worst of the four, re-measured:
    #: **1,901**, at `ACTION__SUBSTANTIATE_CLAIMED_FACTS`. One character over.
    #:
    #: THIS IS THE RISE THE PROMISE ALLOWS AND NOT THE ONE IT FORBIDS, and the
    #: difference is worth being exact about because it would be easy to spend
    #: the promise here. What capability blocks promised is that a tool taxes
    #: only the turns whose answer asks for its pack -
    #: `test_adding_a_tool_does_not_grow_a_focused_turn` registers a tool in
    #: `training` and asserts an empty-ledger brief does not move by one
    #: character, and it still passes. What they never promised is that a pack
    #: could grow for free on the turns that load it. A person being asked to
    #: substantiate a claimed fact IS on the data path, and both new tools are
    #: about their data.
    #:
    #: 1,950 leaves 49 characters over the worst, which is LESS headroom than
    #: the 53 it replaces, on purpose, for the reason the paragraph below
    #: already gives.
    #:
    #: 1,900 WAS NOT RAISED THEN. It left 53 characters over the worst of the four,
    #: which is far less headroom than the 185 it carried before and less than
    #: this file's bound has ever carried - deliberately. A bound is worth having
    #: in the direction it is tight, and raising it to restore the old comfort
    #: would be loosening the one assertion that noticed anything.
    #:
    #: THE AI COLUMN IS THE HONEST ONE TO READ TWICE. Every one of its 20 sheets
    #: selects exactly the twelve core tools and nothing else, and now it SAYS so
    #: in its own document: `contract.capabilities.needs` there is five stages of
    #: `[]`, because no tool in this harness measures a single one of that
    #: ledger's facts and borrowing the ML packs would put a tool in the model's
    #: hands whose success writes the other ledger's fact ids. `docs/PHASES.md`
    #: carries it as an open debt and names the four instruments it needs.
    #: 1,950 -> 2,050 on 2026-08-28, and THIS ONE NEEDS ITS ARGUMENT MADE,
    #: because three commits ago this file's sibling comment said a raise here
    #: "would mean the scoping had failed".
    #:
    #: It has not. A raise here is wrong when a tool lands in a SELECTABLE pack
    #: and somehow reaches every turn anyway - that would mean the selector was
    #: not selecting. `read_the_standing_constraints` is in `context`, which is
    #: a CORE pack, and core is always on by construction: "the packs are chosen
    #: by the walk, so what the walk depends on cannot itself be selectable."
    #: A core tool grows every turn because that is what core MEANS.
    #:
    #: So the question is whether it belongs in core, and `docs/PRODUCT_SPEC.md`
    #: 4.3 answers it: the standing constraints are the things that "should
    #: never be asked twice", and a tool the model can only sometimes see is a
    #: tool that will let it ask twice. `context`'s own gloss - "what the person
    #: pointed at, and what is inside it" - is exactly a project root and the
    #: file inside it.
    #:
    #: MEASURED over all 34 outcomes: widest 1,974, narrowest 938.
    #: 2,050 -> 2,150 on 2026-08-28, the second core tool that day and the same
    #: argument as the first: `scaffold_the_standing_constraints` is in
    #: `context`, a CORE pack, so it is on every turn by construction. The pair
    #: of them are the read and the scaffold halves of PRODUCT_SPEC 4.3's
    #: HARNESS.md, and both exist so a constraint the person wrote down is not
    #: asked for a second time - which a tool the model can only sometimes see
    #: cannot deliver. MEASURED: widest 2,064.
    #:
    #: 2,150 -> 2,250 on 2026-08-28, AND THIS ONE IS THE OTHER KIND OF RAISE -
    #: the kind the 1,900 -> 1,950 paragraph above already argued for, not the
    #: kind the two core-tool paragraphs did. `count_preference_pairs` is in the
    #: `data` pack, which is SELECTABLE, so it taxes only the turns whose answer
    #: asks for data - and `ACTION__SUBSTANTIATE_CLAIMED_FACTS`, the widest of
    #: the seventy-two, is a person being asked to substantiate a claimed fact,
    #: which is squarely on the data path. The promise capability blocks made is
    #: that a tool taxes only the turns its pack is selected for;
    #: `test_adding_a_tool_does_not_grow_a_focused_turn` still asserts that a
    #: tool registered in `training` does not move an empty-ledger brief by one
    #: character, and it still passes. What was never promised is that a pack
    #: could grow for free on the turns that load it.
    #:
    #: MEASURED over all 72 sheets: widest 2,199
    #: (`ACTION__SUBSTANTIATE_CLAIMED_FACTS`), narrowest 1,104.
    #:
    #: 2,250 -> 2,350 on 2026-08-28, AND IT IS THE CORE-TOOL RAISE AGAIN rather
    #: than the one that would mean scoping failed. The two paragraphs above
    #: made this argument twice already, for `read_the_standing_constraints` and
    #: `scaffold_the_standing_constraints`: a raise here is wrong when a tool
    #: lands in a SELECTABLE pack and reaches every turn anyway, because that
    #: would mean the selector was not selecting. `set_the_project_root` is in
    #: `context`, a CORE pack, so it is on every turn BY CONSTRUCTION - and the
    #: change immediately before this one is the control that proves the
    #: distinction is real: six harness tools landed in a selectable pack the
    #: same day and this number did not move by one character.
    #:
    #: It is the third of that trio and the one that made the other two work.
    #: PRODUCT_SPEC 4.3's file is at the PROJECT ROOT, and measured on this date
    #: nothing outside `create_project` could ever set one - so on every fresh
    #: install all three refused, with a remedy no route and no tool could
    #: perform. MEASURED: widest 2,261.
    #: 2,350 -> 2,400 on 2026-08-31: map_the_ask joins the CORE, so unlike
    #: the six packed tools that moved this number by zero, it appears on
    #: every scoped turn - which is its whole job: the ask is mapped at
    #: arrival or not at all. MEASURED: widest scoped 2,359.
    #: 2,400 -> 2,550 on 2026-09-11: the same two tools, in the core, so on
    #: every scoped turn too. MEASURED: widest scoped 2,503.
    #: 2,550 -> 2,600 on 2026-09-11, later: `recall`, core, so on every
    #: scoped turn - and THIS number moved, which is the core signature the
    #: unscoped raise above also shows. MEASURED: widest scoped 2,557.
    #: 2,600 -> 2,700 the same evening: `remember`, core, and the memory
    #: note on every prompt. MEASURED: widest scoped 2,637.
    #: 2,700 -> 2,800 on 2026-09-12: the same two DATA tools - the widest
    #: SCOPED sheet (ACTION__SUBSTANTIATE_CLAIMED_FACTS) loads the data
    #: pack, so this number moves for a packed tool for once, and says so.
    #: MEASURED: widest scoped 2,732.
    #: 2,800 -> 3,000 on 2026-09-13: the two sub-agent tools, core, so on
    #: every scoped turn - the core signature again. MEASURED both sides of
    #: the commit: 2,783 -> 2,900, +117, the same two lines that moved the
    #: unscoped bound. The stuck-walk widening moved this by zero; see BUDGET.
    #: 3,000 -> 3,100 on 2026-09-18, and it is the core signature one more
    #: time: `compile_the_plan` (app/tools/planning.py) is in the LEDGER pack,
    #: so its line is on every scoped turn. MEASURED both sides, by sweeping
    #: these same three fixture sets with the tool in the registry and with it
    #: taken out: the widest scoped sheet (ACTION__SUBSTANTIATE_CLAIMED_FACTS)
    #: is 2,999 without it and 3,068 with it.
    #: 69 characters, which is `compile_the_plan - compile this
    #: conversation's plan from its journey` and the newline after it: the
    #: whole of what this brief spends on a tool. Shortening the tool's
    #: DESCRIPTION does not move this by one character and was tried first -
    #: the brief prints the control's VERB, not the schema. And 2,999 of 3,000
    #: is why it had to move at all: the headroom left was one character.
    #: The floor in `test_a_turn_says_which_blocks_it_loaded` records the same
    #: tool as 27 -> 28 on the same day.
    #: RETAKEN 2026-09-18 for P4 (laws as phase packs) and it moved by zero,
    #: for BUDGET's reason: the packs cut the INSTRUCTION SET, and no part of
    #: the instruction set is in this measurement.
    #: RETAKEN 2026-09-18 for the same two tools: MEASURED 3,191 against 3,100.
    #: 3,200 -> 3,800 on 2026-09-21, and it is the ledger again - the same
    #: six hundred characters, because the fact lines do not depend on which
    #: packs a turn loaded. MEASURED both sides on the widest scoped fixture,
    #: ACTION__SUBSTANTIATE_CLAIMED_FACTS: 3,794 with and 3,191 without, and
    #: 3,794 - 603 = 3,191 to the character. 3,191 against a bound of 3,200 is
    #: the control: the scoped brief was nine characters inside its bound
    #: before this and nothing else moved it.
    #:
    #: This is the bound that describes a real turn, so it is the one that
    #: matters: a sub-agent handed its parent's sheet no longer has to
    #: re-measure the machine to find out what the machine is.
    FOCUSED_BUDGET = 3800

    def test_the_brief_is_a_summary_and_not_the_payload(self):
        """Both shapes. Neither is the payload, and each says what it is made of."""
        empty = conductor.standing_brief(engine_payload({}))
        established = engine_payload(fixtures.SPREAD["already_passes"]["facts"])
        walked = conductor.standing_brief(established)

        for brief in (empty, walked):
            self.assertLess(len(brief), self.BUDGET)
            self.assertNotIn("facts_used", brief)
            self.assertNotIn("fact_origins", brief)
            self.assertNotIn("S0_RULES_SUFFICE", brief, "the path was dumped in")
            # UNSCOPED, WHICH IS WHAT A CALLER WITH NO SELECTION GETS, and the
            # whole registry is named in both - because a question about what
            # this harness can do is made of it on turn one and on turn forty
            # alike, and a turn that could not compute a selection is not a turn
            # to narrow. The scoped shape is
            # `test_every_declared_outcome_fits_the_focused_budget_when_scoped`.
            self.assertIn("registered tools, and what each one does", brief)
            for name in capabilities.tool_names():
                self.assertIn(name, brief, name)

        # A walk over an empty ledger carries the registry and nothing else -
        # no verdict, no outcome id, no gate ledger and no stand-in sentence,
        # because the engine computed none of them ABOUT THIS THREAD.
        self.assertNotIn("BLOCKED__DEFINE_SUCCESS_FIRST", empty)
        self.assertNotIn("verdict BLOCKED", empty)
        self.assertNotIn("G0_EVAL_SET", empty)
        self.assertNotIn(str(engine_payload({})["say"]), empty)
        self.assertLess(
            len(empty),
            len(walked),
            "a walk with nothing to walk over is not the dearer of the two",
        )

        # A walk that had facts to walk over keeps all four, because all four
        # are then findings about this thread.
        self.assertIn(str(established["outcome"]), walked)
        self.assertIn(str(established["say"]), walked)
        # Two, not five: `NO_TRAIN__SHIP_AS_IS` opens G0 and G1 and then ships,
        # so the walk never reaches G2 to G4. That is exactly the distinction
        # `_gate_line` now keeps - the three it did not reach are absent rather
        # than counted as failures.
        self.assertIn("gates 2 of 5 passed", walked)

    def test_every_declared_outcome_fits_the_budget(self):
        """The bound holds for the engine's longest sentence, not just this one."""
        for outcome, facts in sorted(fixtures.REACHING.items()):
            with self.subTest(outcome=outcome):
                brief = conductor.standing_brief(engine_payload(facts))
                self.assertLess(len(brief), self.BUDGET, outcome)

    def test_every_declared_outcome_fits_the_focused_budget_when_scoped(self):
        """And the scoped one, which is the bound that describes a real turn.

        Same fixtures, same engine, one difference: the capability blocks the
        standing diagnosis selected are handed to `standing_brief`, exactly as
        `run_turn` hands them. Every outcome is checked, because a bound that
        held for the common ones and not for the long one would be a bound that
        has never been tested against the thing it exists for.

        ALL THREE FIXTURE SETS, WHICH IT DID NOT USED TO BE. REACHING alone
        leaves out every `TRAIN__` verdict - those live in MINTING - and those
        are precisely the sheets that load the training pack, so the bound was
        never once measured against the widest turn the product can produce.
        """
        spec = diagnosis.default_spec()
        sheets = (
            [(f"MINTING::{k}", v) for k, v in sorted(fixtures.MINTING.items())]
            + [(k, v) for k, v in sorted(fixtures.REACHING.items())]
            + [
                (f"SPREAD::{k}", case["facts"])
                for k, case in sorted(fixtures.SPREAD.items())
            ]
        )
        self.assertGreater(len(sheets), 70, "the fixture corpus shrank")
        for outcome, facts in sheets:
            with self.subTest(outcome=outcome):
                payload = engine_payload(facts)
                active = blocks.active(payload, thread_id=None, spec=spec)
                brief = conductor.standing_brief(payload, None, active)
                self.assertLess(len(brief), self.FOCUSED_BUDGET, outcome)
                # NON-VACUOUS: the scoped brief is genuinely smaller than the
                # one this file bounded for its whole life, on every one of
                # them. A selection that quietly loaded everything would pass
                # the line above and fail this one.
                self.assertLess(len(brief), len(conductor.standing_brief(payload)))

    def test_adding_a_tool_does_not_grow_a_focused_turn(self):
        """THE CLAIM THAT THIS BOUND STOPPED RISING, DRIVEN RATHER THAN ASSERTED.

        Five paragraphs of `BUDGET`'s comment are one event repeated: somebody
        registered a tool, the block grew by a line, and the bound went up. This
        registers a forty-first tool - in the training pack, which an empty
        ledger does not select - and asserts the empty-ledger brief does not move
        by a single character.

        And the negative, in the same test, because the assertion means nothing
        without it: the UNSCOPED brief grows by exactly that tool's line. That is
        what every turn used to pay, and it is what this change stops paying.
        """
        empty = engine_payload({})
        spec = diagnosis.default_spec()
        before_focused = conductor.standing_brief(
            empty, None, blocks.active(empty, thread_id=None, spec=spec)
        )
        before_everything = conductor.standing_brief(empty)
        # DERIVED, NOT TYPED, and captured BEFORE the stand-in registers: this
        # test's subject is that the brief tracks the registry, so pinning
        # "40"/"41" as literals went stale the day the agent pack took the real
        # count to 44. The +1 below is the fake tool registered here.
        n = len(REGISTRY.names())

        @REGISTRY.tool(
            "train_on_the_moon",
            description="A stand-in for the forty-first tool.",
            schema={"type": "object", "properties": {}},
            provides=("training.run.start",),
            label="Moon",
            group="Train",
            verb="train a model on the moon",
        )
        def _moon():  # pragma: no cover - never called
            return {"ok": True}

        self.addCleanup(REGISTRY._tools.pop, "train_on_the_moon", None)

        after_focused = conductor.standing_brief(
            empty, None, blocks.active(empty, thread_id=None, spec=spec)
        )
        after_everything = conductor.standing_brief(empty)

        # THE LINES, WHICH ARE THE QUANTITY THIS BOUND IS MADE OF. The heading
        # moves - it says "of this harness's 40 tools" and the harness now has
        # 41, which is a true sentence that has to keep being true - and not one
        # tool line moves, which is the property.
        self.assertEqual(
            before_focused.split("\n")[1:],
            after_focused.split("\n")[1:],
            "a tool in a pack this turn did not load still reached the brief",
        )
        self.assertLess(
            len(after_focused) - len(before_focused),
            len("train_on_the_moon"),
            "the focused brief grew by something the size of a tool",
        )
        self.assertIn(f"{n} registered tools", before_everything)
        self.assertIn(f"{n + 1} registered tools", after_everything)
        self.assertEqual(
            len(after_everything) - len(before_everything),
            len("\ntrain_on_the_moon - train a model on the moon"),
            "the unscoped brief did not grow, so this test proved nothing",
        )

    def test_it_is_two_engine_walks_per_turn_and_neither_is_optional(self):
        """One over this thread, one over nothing, and both are the harness's.

        IT WAS ONE, AND THE SECOND IS NOT A DUPLICATE OF IT. The first is the
        standing diagnosis: what the engine says about THIS thread's ledger,
        before the model speaks. The second asks the same engine what it says
        over no ledger at all, and its only job is to be the reference
        `conductor.says_nothing_new` compares the first against - the line
        between a finding about this person and the sentence every thread that
        has established nothing gets. Both go through the registry with
        `actor="harness"` and no supplied facts, because a second path to the
        engine is a second place to miss the rule that a model may not decide
        a gate.

        The cost is the reason a bound is asserted at all: the walk is a pure
        function over a sheet of facts and the docstring on
        `conductor.standing_brief` measures it at 1.81 ms average. Two of them
        is the price of telling a constant from a finding without asking the
        question what it was about.
        """
        self.connect()
        patcher = mock.patch.object(
            conductor.REGISTRY, "call", wraps=conductor.REGISTRY.call
        )
        counted = patcher.start()
        self.addCleanup(patcher.stop)

        thread_id = self.thread("what is my GPU?")
        self.install(ScriptedModel([says("An RTX 4070.")]))
        list(conductor.run_turn(thread_id))

        walks = [c for c in counted.call_args_list if c.args[0] == "run_diagnosis"]
        self.assertEqual(len(walks), 2)
        self.assertEqual(
            [walk.kwargs["thread_id"] for walk in walks], [thread_id, None]
        )
        for walk in walks:
            self.assertEqual(walk.args[1], {"facts": {}})
            self.assertEqual(walk.kwargs["actor"], "harness")

    def test_the_walk_is_pure(self):
        """No fact is written by asking the engine what it thinks.

        `run_diagnosis` declares `writes=()`; this is the conductor's half of
        the same sentence, checked against the ledger the walk reads.
        """
        from app.tools import evidence

        thread_id = self.thread()
        before = evidence.rows_for(thread_id)
        conductor._standing_diagnosis(thread_id)
        self.assertEqual(evidence.rows_for(thread_id), before)

    def test_an_engine_that_will_not_run_does_not_end_the_turn(self):
        self.connect()
        patcher = mock.patch.object(
            conductor.REGISTRY, "call", side_effect=RuntimeError("engine down")
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        thread_id = self.thread("what is my GPU?")
        self.install(ScriptedModel([says("An RTX 4070.")]))
        list(conductor.run_turn(thread_id))
        self.assertEqual(self.prose(thread_id), "An RTX 4070.")
        self.assertEqual(self.ending(thread_id), "answered")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
