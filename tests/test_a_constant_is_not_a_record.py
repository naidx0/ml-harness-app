"""A walk that says nothing about you reaches the model as a record of itself.

## The defect, which is Max's original complaint and the oldest one open

He asked the product a question and got a seven-phase consulting deck; he asked
what it could do and was told to define success first. It has been fixed by
prose four times and structurally once, and it was still a third of turns.

The structural fix - `conductor._empty_ledger_brief` - stopped SUPPLYING the
engine's verdict on a turn where that verdict is a constant, and took the
capability question from 0 of 20 to 16 of 20. It did not stop the model going
and FETCHING the same constant. `run_diagnosis` is in the tool list on every
one of those turns, so the harness declined to say the thing and then offered a
button that says it, at seven times the tokens and with the raw five-gate
ledger attached.

## Measured before anything was changed

`scripts/did_it_answer_the_question.py`, kept in the tree, is the driver and
the bank: twenty questions across six kinds - definitional, risk, capability,
machine, data, and Max's four training phrasings verbatim - five live passes
each against granite4-hermes plus five more of the two kinds that pull the
engine, 140 turns, graded on one thing.

    non-training turns that ran the engine   28 of 120, answered 17  (61%)
    non-training turns that did not          92 of 120, answered 85  (92%)
                                                         p = 0.0002

That is the strongest association in the bank. Read rather than counted, the
misses are one shape:

    "Explain the difference between full fine-tuning and LoRA."
    -> "The diagnosis report indicates that the decision to train a model is
       blocked because several critical pieces of information are missing or
       not yet defined: 1. Definition of Success..."

    "What are the risks of fine-tuning on a small dataset?"
    -> "The diagnosis step has identified several critical factors that
       prevent proceeding with fine-tuning: 1. No Eval Set Defined
       (G0_EVAL_SET). 2. Baseline Not Measured (G1_BASELINE_MEASURED)..."

Those are the five gates enumerated as a checklist of things the person has
failed to provide, and **the engine evaluated none of them**. All five are
`NOT_REACHED` on that walk. `conductor._gate_line` is an essay about exactly
that distinction and it fixed the BRIEF; the tool payload still carried the raw
`gate_ledger`, and a model handed five gates with a status field renders them
as five requirements whatever it was asked about.

## The property under test, which is not the question and not the ledger's size

**Does the engine's answer for this thread differ from the answer it gives a
thread it knows nothing about?** When it does not, the model is handed the
verdict and the engine's own sentence, and not the record behind them.

Not the question, because matching on the question is the brittle road this
product has rejected three times and Max's four phrasings are the proof. Not
the ledger's size either, and that half is checkable rather than argued:
`inspect_hardware` puts four facts in the ledger and the walk over them reaches
the same outcome with the same five `NOT_REACHED` gates. A size test would call
that thread established while the engine is still saying one sentence to
everybody.

## The arm that was measured and rejected

Withdrawing `run_diagnosis` from the offer on those turns is the obvious lever
and it was the first thing tried. Twenty live turns, Max's four training
phrasings, five passes:

    the four training phrasings   answered   `run_diagnosis` called
      the tool offered            19 of 20        18 of 20
      the tool withdrawn           6 of 20         0 of 20

Thirteen of the twenty ended in `empty_reply` - no words, no tool calls, the
harness writing the closing sentence. Denied the engine, this model has no move
on the product's central question and says nothing at all. That is the silent
turn `app/conductor.py` opens with, reintroduced deliberately, and it is why
`TheToolIsStillOfferedTest` below is a regression row rather than a nicety.

## What that change bought, and how the number that said so was wrong

140 turns a side, same bank, same two-shard setup:

    kind             answered before   answered after   gate material
    definitional        46 of 50          47 of 50       1/50 -> 0/50
    risk                18 of 30          22 of 30       5/30 -> 2/30
    capability          18 of 20          17 of 20       1/20 -> 0/20
    THE FOUR TRAINING   19 of 20          20 of 20       -
    all                121 of 140        126 of 140     15/140 -> 6/140

Neither move was significant - p = 0.46 on the answered column and p = 0.067 on
the gate material - and the file was right not to claim they were. **What it
did not know is that the second column was measured with a ruler that could not
see the defect any more.** `gate material` was `GATE_WORDS`, a hand-written
list - `G0_EVAL_SET`, `NOT_REACHED`, `gates 0 of`, `define success` - written
against the wording that fix had just removed.

## The defect changed clothes, and the ruler was rebuilt before the fix

`constant_answer` stopped handing over the raw gate ledger and handed over
`verdict_sentence(payload)` instead, which on an empty ledger is a CONSTANT:

    BLOCKED - BLOCKED__DEFINE_SUCCESS_FIRST. Nothing downstream is decidable
    until 'good' is defined. Write 20 inputs and the output you wanted.

The model recited that. Max's first message of 2026 - *"What could go wrong if
I train on synthetic data generated by another model?"* - was answered 0 of 4,
three of them with *"we need to first define what constitutes 'good'... please
provide at least 20 example inputs"*.

Re-measured on 125 live non-training turns, with a detector that compares a
reply against the engine's OWN RECORDED SENTENCE rather than against a word
list - `scripts/did_it_answer_the_question.py::recites_the_engine`:

    a reader, going through every reply      15 of 125   (12%)
    the lookup                               13 of 125, 13 of them right
    `GATE_WORDS`                              7 of 125,  6 of them right

## What is here now, and what it bought

The model is handed a RECORD of the walk rather than the walk's answer:
`constant_record`. It ran; this thread established n of the facts it walks; the
outcome is the one a thread the engine has never seen gets. Nothing in it is
addressed to anybody, which is the property `WhatTheModelIsHandedTest` asserts,
and it is asserted as a property rather than as a list of strings so that it
does not go stale the way the ruler did. `standing_brief` took the same
predicate in the same change - see `TheBriefIsTheOtherDoorTest` for why it had
to.

145 turns a side, twenty-nine questions across nine kinds, five passes:

    column                            before     after        p
    recital, non-training           13 of 125   3 of 125    0.017
    answered, non-training          97 of 125  94 of 125    0.766
    THE FOUR TRAINING, answered      19 of 20   20 of 20    1.000
    empty replies, all               0 of 145   2 of 145    0.498
    gate_words, non-training          7 of 125   5 of 125    0.769

The last row is the old detector on the same two files, and it says the change
did nothing. That is the argument for fixing a ruler before the thing it
measures, in one line.

**NO TEST IN THIS FILE ASSERTS ANY OF THOSE NUMBERS.** They are a sample and
they are here so a re-run has something to disagree with. What is asserted is
the part that is not a sample: the engine's sentence, its outcome id and its
five gate ids cannot reach the model on such a turn through either door, the
whole payload is still in `tool.result`, the engine's exact words still reach
the PERSON through the verdict card, and `run_diagnosis` is still offered every
round. And what is declared open is `TheDoorThisStepDidNotCloseTest`.
"""

from __future__ import annotations

import unittest

from app import conductor, diagnosis, events
from app.providers import Delta, ToolCall
from app.providers import store as provider_store
from app.tools import REGISTRY, blocks, evidence

import support


class ScriptedModel:
    """A model that says what the test told it to, and keeps what it was sent."""

    id = "fake"
    locality = "local"

    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.sent = []

    def stream(self, messages, tools=None, *, secret=None):
        self.sent.append({"messages": [dict(m) for m in messages], "tools": tools})
        for delta in self.rounds.pop(0) if self.rounds else []:
            yield delta

    def capabilities(self, *, secret=None):
        raise AssertionError("the loop must not probe mid-turn")


class TurnTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.blank = conductor._standing_diagnosis(None)

    def connect(self):
        row = provider_store.create(
            "Fake", "http://127.0.0.1:11434", "fake-model", "ollama"
        )
        ready = provider_store.record_capabilities(
            row["id"],
            type(
                "Caps",
                (),
                {
                    "tool_calling": True,
                    "detail": "set by the test",
                    "ctx_len": None,
                    "provenance": {},
                },
            )(),
        )
        provider_store.set_active(ready["id"])

    def install(self, model):
        original = conductor.build
        conductor.build = lambda *a, **k: model
        self.addCleanup(setattr, conductor, "build", original)
        return model

    def thread(self, question):
        row = events.create_thread("t")
        events.add_message(row["id"], "user", question)
        return row["id"]

    def rows(self, thread_id):
        return events.since(f"thread:{thread_id}")

    def asks_the_engine(self, then_says="Here is the answer."):
        """Round one calls `run_diagnosis`; round two answers in words."""
        return ScriptedModel(
            [
                [
                    Delta(
                        kind="tool_call",
                        tool_calls=(ToolCall("c1", "run_diagnosis", {"facts": {}}),),
                    )
                ],
                [Delta(kind="text", text=then_says)],
            ]
        )

    def tool_message(self, model):
        """What the model was handed back for its call, on the next round."""
        rows = [
            message
            for message in model.sent[-1]["messages"]
            if message.get("role") == "tool"
        ]
        self.assertTrue(rows, "the model was never handed a tool result")
        return rows[-1]["content"]


class WhatDecidesItTest(TurnTest):
    """`says_nothing_new` reads the payload. Nothing else is consulted."""

    def walk(self, thread_id):
        return REGISTRY.call(
            "run_diagnosis", {"facts": {}}, actor=evidence.MODEL, thread_id=thread_id
        )

    def test_a_thread_that_has_established_nothing_gets_the_constant(self):
        thread_id = self.thread("what is LoRA?")
        self.assertTrue(conductor.says_nothing_new(self.walk(thread_id), self.blank))

    def test_four_facts_that_do_not_move_the_outcome_are_still_the_constant(self):
        """THE HALF A LEDGER-SIZE TEST GETS WRONG, and it is not hypothetical.

        `inspect_hardware` measures four facts. The walk over them reaches the
        same outcome with all five gates `NOT_REACHED`, because the gate tree
        is above hardware. Three of the fifteen live turns in the table at the
        top of this file are exactly this sequence - inspect, then diagnose,
        then answer somebody's question about LoRA with the gate ledger.
        """
        if not support.a_gpu_was_measured():
            # inspect_hardware stamps four facts on a machine with a
            # readable card and two without it, so this count is a
            # statement about the machine as much as about the ledger.
            self.skipTest(support.NO_GPU_HERE)
        thread_id = self.thread("what are the risks of a small dataset?")
        REGISTRY.call("inspect_hardware", {}, thread_id=thread_id)
        walk = self.walk(thread_id)
        self.assertGreaterEqual(
            len(walk["facts_used"]), 4, "the ledger is no longer empty"
        )
        self.assertTrue(conductor.says_nothing_new(walk, self.blank))

    def test_a_fact_that_moves_the_outcome_ends_it_immediately(self):
        thread_id = self.thread("should i train?")
        REGISTRY.call(
            "state_facts", {"facts": {"target_score": 0.9}}, thread_id=thread_id
        )
        walk = self.walk(thread_id)
        self.assertNotEqual(walk["outcome"], self.blank["outcome"])
        self.assertFalse(conductor.says_nothing_new(walk, self.blank))

    def test_a_result_that_is_not_a_diagnosis_is_never_scoped(self):
        """The stamp, not the tool's name. A tool that runs the engine next
        year is covered the day it is written; one that does not, never is."""
        hardware = REGISTRY.call(
            "inspect_hardware", {}, thread_id=self.thread("what gpu?")
        )
        self.assertFalse(conductor.says_nothing_new(hardware, self.blank))
        self.assertFalse(conductor.says_nothing_new({"outcome": "x"}, self.blank))
        self.assertFalse(conductor.says_nothing_new("not a dict", self.blank))

    def test_it_fails_open_when_it_cannot_tell(self):
        """No reference, no scoping. The expensive direction is cutting a real
        finding down to two lines, so anything undecidable leaves the payload
        whole."""
        walk = self.walk(self.thread("should i train?"))
        self.assertFalse(conductor.says_nothing_new(walk, None))
        self.assertFalse(conductor.says_nothing_new(walk, {}))


class WhatTheModelIsHandedTest(TurnTest):
    """A RECORD OF THE WALK, and nothing that is shaped like a reply.

    This class used to assert the opposite of what it asserts now, and the
    reason is the whole finding. It required `verdict_sentence(payload)` and
    `payload["say"]` to be present, on the argument that they are the engine
    verbatim and that paraphrasing the engine would be worse. That argument is
    correct and it was answered with the wrong thing: the engine's `say` on a
    constant walk is *"Nothing downstream is decidable until 'good' is defined.
    Write 20 inputs and the output you wanted"* - an instruction addressed to
    the reader, which is the one thing in the payload already shaped like a
    finished reply. A model holding a finished reply hands it over.

    So what is asserted here now is the SHAPE rather than the source: nothing
    the model is handed on such a turn is addressed to anybody.
    """

    def payload(self, thread_id):
        return REGISTRY.call(
            "run_diagnosis", {"facts": {}}, actor=evidence.MODEL, thread_id=thread_id
        )

    def test_the_engines_own_sentence_does_not_reach_the_model(self):
        payload = self.payload(self.thread("what is LoRA?"))
        handed = conductor.constant_record(payload)
        self.assertNotIn(payload["say"], handed)
        self.assertNotIn(payload["outcome"], handed)
        self.assertNotIn(conductor.verdict_sentence(payload), handed)

    def test_nothing_in_it_is_addressed_to_the_reader(self):
        """THE PROPERTY, STATED AS A PROPERTY AND NOT AS A LIST OF STRINGS.

        A test that named the current sentence would go stale the next time the
        engine's wording moves, which is exactly how the detector in
        `scripts/did_it_answer_the_question.py` came to be measuring the shape
        of a defect that had already changed clothes.
        """
        handed = conductor.constant_record(
            self.payload(self.thread("what is LoRA?"))
        ).lower()
        for word in (" you ", " your ", "write ", "provide ", "define ", "please"):
            self.assertNotIn(word, handed, f"{word!r} is addressed to somebody")

    def test_it_counts_the_facts_this_thread_established(self):
        """The count is the half that IS about this person, so it stays.

        `DEFAULTED` is the engine's own word for a fact nobody supplied, so
        this is read off `fact_origins` rather than judged.
        """
        if not support.a_gpu_was_measured():
            # inspect_hardware stamps four facts on a machine with a
            # readable card and two without it, so this count is a
            # statement about the machine as much as about the ledger.
            self.skipTest(support.NO_GPU_HERE)
        thread_id = self.thread("what are the risks of a small dataset?")
        REGISTRY.call("inspect_hardware", {}, thread_id=thread_id)
        payload = self.payload(thread_id)
        origins = payload["fact_origins"]
        established = sum(1 for row in origins.values() if row != "DEFAULTED")
        self.assertGreaterEqual(established, 4, "the fixture measured nothing")
        self.assertIn(
            f"{established} of {len(origins)} facts",
            conductor.constant_record(payload),
        )

    def test_it_carries_no_gate_at_all(self):
        """Not the ids, and not the word either. `_gate_line`'s honest line was
        the last thing in here that could be read as a checklist of five
        requirements, and on this branch the walk reached no gate anyway."""
        payload = self.payload(self.thread("what is LoRA?"))
        self.assertEqual(
            {row["status"] for row in payload["gate_ledger"].values()},
            {conductor.NOT_REACHED},
            "the fixture must be a walk that evaluated no gate",
        )
        handed = conductor.constant_record(payload)
        for gate in payload["gate_ledger"]:
            self.assertNotIn(gate, handed)
        self.assertNotIn("gate", handed.lower())


class TheRecordIsNotTouchedTest(TurnTest):
    """`tool.result` carries the whole payload. The conversation carries a
    record of the walk. Those are two different objects and this is the line
    between them."""

    def test_the_event_keeps_the_payload_the_model_does_not_get(self):
        self.connect()
        model = self.install(self.asks_the_engine())
        thread_id = self.thread("What is the difference between RAG and fine-tuning?")
        list(conductor.run_turn(thread_id))

        results = [
            row["payload"]
            for row in self.rows(thread_id)
            if row["kind"] == "tool.result"
        ]
        self.assertEqual(len(results), 1)
        recorded = results[0]["result"]
        self.assertEqual(len(recorded["gate_ledger"]), 5)
        self.assertIn("path", recorded)
        self.assertEqual(recorded["decided_by"], "app/diagnosis.py")
        self.assertTrue(recorded["say"])

        handed = self.tool_message(model)
        self.assertNotIn(recorded["say"], handed)
        self.assertNotIn(recorded["outcome"], handed)
        for gate in recorded["gate_ledger"]:
            self.assertNotIn(gate, handed)
        self.assertLess(len(handed), len(str(recorded)) // 10)

    def test_a_diagnosis_that_says_something_arrives_whole(self):
        """The scoping is not a diet. A walk that moved off the constant goes
        to the model as the full record, in its envelope, as it always did."""
        self.connect()
        model = self.install(self.asks_the_engine())
        thread_id = self.thread("should i train?")
        REGISTRY.call(
            "state_facts", {"facts": {"target_score": 0.9}}, thread_id=thread_id
        )
        list(conductor.run_turn(thread_id))

        handed = self.tool_message(model)
        self.assertIn("tool:run_diagnosis", handed, "it lost its data envelope")
        self.assertIn("gate_ledger", handed)


class TheBriefIsTheOtherDoorTest(TurnTest):
    """THE SAME CONSTANT, THROUGH A DIFFERENT DOOR, GATED ON A DIFFERENT THING.

    `says_nothing_new` decides the tool result on the OUTCOME, and the whole of
    its docstring is why the ledger's SIZE is the wrong property to decide it
    on. `standing_brief` decided itself on the ledger's size. So a thread where
    `inspect_hardware` had put four facts on the sheet was handed the engine's
    constant sentence in the brief, before the model had said anything, on
    every later turn of that thread - the exact thing the tool-result scoping
    exists to prevent, one layer up, reached by the exact argument that scoping
    rejects.

    Both doors now take the same predicate and the same reference.
    """

    def test_a_ledger_with_facts_whose_walk_says_nothing_loses_the_verdict(self):
        thread_id = self.thread("what is LoRA?")
        REGISTRY.call("inspect_hardware", {}, thread_id=thread_id)
        payload = conductor._standing_diagnosis(thread_id)
        self.assertTrue(payload["facts_used"], "the fixture needs a ledger")
        self.assertTrue(conductor.says_nothing_new(payload, self.blank))

        brief = conductor.standing_brief(payload, self.blank)
        self.assertNotIn(payload["say"], brief)
        self.assertNotIn(payload["outcome"], brief)
        self.assertIn(str(len(payload["facts_used"])), brief)
        self.assertIn("registered tools", brief)

    def test_a_ledger_whose_walk_says_something_still_gets_all_of_it(self):
        thread_id = self.thread("should i train?")
        REGISTRY.call(
            "state_facts", {"facts": {"target_score": 0.9}}, thread_id=thread_id
        )
        payload = conductor._standing_diagnosis(thread_id)
        self.assertFalse(conductor.says_nothing_new(payload, self.blank))

        brief = conductor.standing_brief(payload, self.blank)
        self.assertIn(payload["say"], brief)
        self.assertIn(payload["outcome"], brief)

    def test_the_turn_hands_the_reference_in(self):
        """The argument defaults to `None`, which restores the old behaviour
        exactly. So what is asserted is the CALL SITE and not the function: a
        live turn on a thread that has measured something must not put the
        constant in front of the model."""
        self.connect()
        model = self.install(self.asks_the_engine())
        thread_id = self.thread("what is LoRA?")
        REGISTRY.call("inspect_hardware", {}, thread_id=thread_id)
        list(conductor.run_turn(thread_id))

        sent = chr(10).join(
            message.get("content") or "" for message in model.sent[0]["messages"]
        )
        self.assertNotIn(self.blank["say"], sent)
        self.assertNotIn(self.blank["outcome"], sent)


class TheDoorThisStepDidNotCloseTest(TurnTest):
    """THE FOURTH LAYER, DECLARED OPEN RATHER THAN LEFT FOR SOMEBODY TO FIND.

    Three times now a fix has taken the engine's constant out of one place and
    the next place along has still been holding it: the brief carried a
    fabricated gate ledger, then the tool payload carried the raw ledger, then
    the tool payload carried the engine's sentence. Each fix was correct. Each
    left the layer under it untouched, and nobody knew until somebody measured.

    So this one was measured before it was written down. `propose_build`
    REFUSES on a thread the engine knows nothing about, and its refusal carries
    `outcome`, `verdict` and the engine's `say` - **without the
    `decided_by: app/diagnosis.py` stamp**, which is the only thing
    `says_nothing_new` keys on. So the scoping does not apply, the refusal
    arrives in its `data_envelope` whole, and *"Write 20 inputs and the output
    you wanted"* is in front of the model again.

    It is not hypothetical. One of the 125 non-training turns in the run that
    measured this step went through it:

        "How long would that take to train?"
        -> tools: inspect_hardware, run_diagnosis, propose_build
        -> "The verdict indicates that 'good' (i.e., what constitutes a
           successful outcome) hasn't been defined yet. You need to specify how
           you'll measure success..."

    It is NOT fixed here, and the reason is the discipline rather than the
    difficulty: closing it means either stamping a refusal as a diagnosis - a
    change in `app/tools/`, which this step does not own - or widening
    `says_nothing_new` past the stamp its own docstring argues for. Either is a
    step with its own acceptance and its own live measurement, and shipping it
    unmeasured on the back of this one is how the last three landed.

    `expectedFailure` and not `skip`: this runs the attack, watches it succeed,
    and is counted on the suite's last line. When somebody closes it, unittest
    reports an unexpected success and fails the build, so the marker cannot be
    left behind.
    """

    @unittest.expectedFailure
    def test_a_refused_build_does_not_hand_over_the_engines_sentence(self):
        thread_id = self.thread("What are the downsides of using RAG?")
        refusal = REGISTRY.call(
            "propose_build", {"facts": {}}, actor=evidence.MODEL, thread_id=thread_id
        )
        self.assertIs(refusal["ok"], False, "the fixture must be a refusal")
        self.assertEqual(refusal["outcome"], self.blank["outcome"])

        handed = (
            conductor.constant_record(refusal)
            if conductor.says_nothing_new(refusal, self.blank)
            else conductor.data_envelope("tool:propose_build", refusal)
        )
        self.assertNotIn(self.blank["say"], handed)


class TheUserStillGetsTheEngineTest(TurnTest):
    """IT STOPS REACHING THEM THROUGH THE MODEL'S MOUTH. IT DOES NOT STOP.

    Everything above is about what the MODEL is handed. The engine's exact
    sentence still reaches the person, in the harness's own voice, on a turn
    whose reply settled the training decision - either beside the reply on the
    verdict card or in place of a reply the sentry withheld. Both render
    through `verdict_sentence`, which is why there is one assertion here and
    not two, and it is the difference between the harness speaking beside the
    model and the model speaking for the harness.
    """

    def test_a_reply_that_settles_training_puts_the_engine_in_front_of_them(self):
        self.connect()
        self.install(
            ScriptedModel(
                [[Delta(kind="text", text="No - do not train a model for this.")]]
            )
        )
        thread_id = self.thread("should i train a model for this application")
        list(conductor.run_turn(thread_id))

        shown = chr(10).join(str(row["payload"]) for row in self.rows(thread_id))
        self.assertIn(self.blank["say"], shown)


class TheToolIsStillOfferedTest(TurnTest):
    """THE REGRESSION ROW, and the reason it is a test rather than a comment.

    Withdrawing `run_diagnosis` on these turns was measured: Max's four
    training phrasings went 19 of 20 answered to 6 of 20, thirteen of them
    ending with no words at all. The scoping above must never quietly become a
    withdrawal.

    **IT USED TO ASSERT THE WHOLE REGISTRY AND THAT WAS THE WRONG QUANTITY.**
    Capability blocks scope what a turn offers, so "all forty, every round" is
    no longer true and asserting it would be asserting the absence of a feature.
    What was ever load-bearing here is the DOOR BACK INTO THE ENGINE, which is
    the thing whose withdrawal was measured, and it is now a structural property
    rather than a habit: `run_diagnosis`, `propose_build` and `state_facts` are
    core, and the core is on every turn of every thread. That is what is
    asserted, on every round, plus the whole core beside it.

    **LAW SUBSTITUTED 2026-09-18, AND THE MEASURED HALF IS UNTOUCHED.** A turn
    now carries every active tool's NAME and only the named tools' full schema
    (`app/tools/blocks.py:on_the_wire`), so "offered" has become two things and
    this class asserts both. `run_diagnosis` and `state_facts` are in
    `blocks.ALWAYS_ON` and ride on every round with their parameters - that is
    the door whose withdrawal was the 19-of-20-to-6-of-20 measurement, and it is
    asserted below exactly as it was.

    `propose_build` MOVED, and it moved on a number. MEASURED the same day: its
    schema is 7,040 characters and 1,957 tokens - MORE THAN THE WHOLE NINE-TOOL
    CORE, which is 1,512 - and it is the move for exactly one shape of verdict,
    the one where every question the walk asks is answered. So it arrives when
    the engine says it is the move: `app/tools/__init__.py` writes *"the next
    move is propose_build"* into the payload's `next` on that branch, and
    `on_the_wire` reads that sentence. Driven below, on a payload that reaches
    it, rather than asserted away - and it is ACTIVE on every turn either way,
    so `_run_tool` runs it rather than refusing it.
    """

    def test_the_engine_is_offered_on_every_round_of_a_turn(self):
        self.connect()
        model = self.install(self.asks_the_engine())
        thread_id = self.thread("would training help here?")
        list(conductor.run_turn(thread_id))
        self.assertTrue(model.sent, "no round was sent, so this asserts nothing")
        # THE CORE PLUS WHAT THIS LEDGER DECLARES ITS ENTRY STAGE NEEDS, read
        # off the document rather than typed. A walk over no facts cannot leave
        # the stage it starts in, so that is the whole of the set - and it is
        # `core` alone only for a ledger that declares its first stage needs
        # nothing, which the ML ledger does not: `stage_0_admissibility: [data]`,
        # because everything that stage decides is answered by looking at the
        # person's data. An equality, not a superset: a selection that quietly
        # loaded all forty would still satisfy the four door lines below.
        # AND THE INSTRUMENTS THE GATES READ, from 2026-09-13, because the
        # entry stage's walk stops on `modality` and no tool measures it - so
        # nothing this turn could run would clear the stop, and withholding
        # the instruments cost the owner nine turns of a model announcing
        # `measure_baseline` and being unable to call it. Derived from the
        # ledger's own compiled gate index, same as the two lines above are
        # derived from its capability block.
        spec = diagnosis.default_spec()
        packs = set(blocks.CORE) | set(blocks.declared(spec).needs[spec.roles.entry_stage])
        for row in spec.gate_row_facts.values():
            for fact in row:
                for tool in blocks._measured_by(fact):
                    packs.update(blocks.pack_of_tool(tool))
        expected = set(blocks.tools_in(packs))
        # THE ACTIVE SET IS STILL EXACTLY THAT, which is where the equality
        # lives now - `turn.started` records it, and it is what `_run_tool`
        # permits. The schema set is the second record and is asserted beside
        # it, also as an equality: a subset would pass on a turn that carried
        # nothing, which is the withdrawal this class exists to refuse.
        started = events.latest("turn.started", thread_id)["payload"]
        active = set(started["blocks"]["tools"])
        self.assertEqual(active, expected)
        self.assertIn("propose_build", active, "the door is not active")
        # And the instrument the owner's model spent nine turns asking for. It
        # is ACTIVE, so a call to it runs rather than getting `not_loaded`.
        self.assertIn("measure_baseline", active)

        # PLUS THE ONE TOOL THE WALK NAMES, since 2026-09-22: a fresh walk
        # stops on a `derive` fact, the harness derives those from a counted
        # eval set on every permission, so the walk names `measure_eval_set`
        # and a named move carries its schema. Read off the walk, not typed.
        named = {
            str(((conductor._standing_diagnosis(thread_id) or {}).get("next_step") or {}).get("tool") or "")
        } & expected
        for sent in model.sent:
            offered = {tool["function"]["name"] for tool in sent["tools"]}
            self.assertEqual(offered, (set(blocks.ALWAYS_ON) & expected) | named)
            self.assertLess(len(offered), len(REGISTRY.names()))
            # THE MEASURED DOOR, ON EVERY ROUND, WITH ITS PARAMETERS. This is
            # the line the 19-of-20-to-6-of-20 arm was about and it has not
            # moved by a character.
            for door in ("run_diagnosis", "state_facts"):
                self.assertIn(door, offered, door)

    def test_the_proposal_door_opens_when_the_engine_says_it_is_the_move(self):
        """`propose_build`'s half of the law, driven rather than assumed.

        The class docstring says it arrives when the engine names it. A note
        saying so is worth nothing; this is the payload the engine writes on
        that branch, through the same selector the conductor calls.
        """
        answered = {
            "ok": True,
            "outcome": "READY",
            "verdict": "READY",
            "path": [],
            "alternatives": [],
            "unsubstantiated": [],
            "gate_ledger": {},
            "next_step": {"kind": "propose"},
            "next": "Every question the walk asks is answered; the next move is propose_build.",
        }
        active = blocks.active(answered, thread_id=None)
        wire = blocks.on_the_wire(active, thread_id=None, payload=answered)
        self.assertIn("propose_build", wire.tools)
        self.assertIn("next step", wire.because["propose_build"])
        # NON-VACUOUS: without that sentence the same sheet does not carry it,
        # which is the 1,957 tokens this whole substitution is about.
        blocked = dict(answered, next_step={"kind": "gap", "tool": "state_facts"}, next="")
        quiet = blocks.on_the_wire(
            blocks.active(blocked, thread_id=None), thread_id=None, payload=blocked
        )
        self.assertNotIn("propose_build", quiet.tools)

    def test_every_registered_tool_is_still_a_button(self):
        """The other half, and the one that makes a scoped turn recoverable.

        `docs/CAPABILITY_BLOCKS.md` §3: blocks scope what reaches the MODEL and
        `REGISTRY.controls()` stays complete. A pack that is not loaded is a tool
        the model will not reach for, never a tool the person cannot run - which
        is the whole difference between scoping and a tab bar.
        """
        self.assertEqual(
            {control["name"] for control in REGISTRY.controls()},
            set(REGISTRY.names()),
        )

    def test_the_engine_still_walks_before_the_model_speaks(self):
        """Nothing above changes what the harness computes, records or
        enforces. `turn.started` still carries the verdict that was standing."""
        self.connect()
        self.install(self.asks_the_engine())
        thread_id = self.thread("do I need to fine-tune at all?")
        list(conductor.run_turn(thread_id))
        started = [
            row["payload"]
            for row in self.rows(thread_id)
            if row["kind"] == "turn.started"
        ][0]
        self.assertEqual(started["diagnosis"]["verdict"], self.blank["verdict"])
        self.assertEqual(started["diagnosis"]["outcome"], self.blank["outcome"])
        self.assertEqual(started["diagnosis"]["decided_by"], "app/diagnosis.py")


if __name__ == "__main__":
    unittest.main()
