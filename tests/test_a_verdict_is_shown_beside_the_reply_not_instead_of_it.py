"""The three sentences this product deleted, and the one it still stops.

## Why this file exists

Twenty conversations, driven end to end against granite4-hermes with both walls
LIVE, read the way a person reads a transcript. 22 turns, mean reply 1,267
characters.

    3 of 22 turns (14%) were interrupted.
    All three were the VERDICT SENTRY, not the provenance wall.
    All three were FALSE CATCHES. The true-catch rate was zero.

The three, verbatim, with what the user lost:

    "What is LoRA rank and what value should I use?"
      withheld: "Thus, a LoRA rank of 32 would result in smaller matrices ...
      which fits within the available VRAM while still providing sufficient
      flexibility for fine-tuning."
      A hyperparameter sentence read as asserting TRAIN. The user asked a
      definitional question and got a gate ledger about writing 20 examples.

    "I have 40000 rows across 4 classes. How many per class, and what does a
     10% holdout give me?"
      withheld: "This is a common split that balances enough data for robust
      evaluation while still leaving sufficient data to train on."
      A sentence about SPLIT RATIOS - and the arithmetic in the RELEASED half
      was wrong, 3,600 and 36,000 where 10% of 40,000 is 4,000. The harness let
      the false arithmetic through and withheld the true sentence after it.

    "What would it cost me to fine-tune a 7B model here?"
      withheld: "Given that your machine has only 8 GB VRAM, it does not have
      enough VRAM to fine-tune a 7B model effectively."
      True, useful, about the user's own machine - and A DO-NOT-TRAIN
      OBSERVATION, which `docs/VISION.md` calls the most valuable thing this
      product can say. The wall deleted it.

## The third row carries a number now, and that is a judgement, not a tidy-up

The row above was reconstructed from a live transcript by keeping the PROSE and
dropping the RECORDS, and the two are not separable here. On the reconstructed
turn nothing ran, the ledger was empty, and `standing_brief` carries the
registry rather than the hardware - so *"your machine has only 8 GB VRAM"* had
no origin whatsoever. `CLAUDE.md` names that exact shape as the defect this
product was built to end: *"a hardcoded 8.0 VRAM ... made the app confidently
wrong"*, down to the same number. Calling it true because it happened to match
the machine it was written on is the reasoning this repository exists to refuse.

So the question in the row now carries the person's own figure, which is what
gives the 8 an origin, and the withheld sentence is UNCHANGED. What the row
asserts is what it always meant to assert: A DO-NOT-TRAIN OBSERVATION ABOUT THE
USER'S OWN MACHINE REACHES THE USER WHOLE. What it no longer asserts is that a
hardware reading nobody took is fine to print.

Both directions are pinned. `test_the_do_not_train_observation_is_the_one_that
_matters_most` runs it over a record that holds the 8;
`test_but_the_same_sentence_over_nothing_is_the_founding_defect` runs the same
sentence, byte for byte, over a record that holds nothing, and requires it to be
stopped. A wall that could not tell those two apart would be worthless, and a
test that only ran the passing half would not know.

Those three sentences are the regression rows at the top of this file. They are
asserted end to end - through a real turn, with the real walls installed - and
not against the reader alone, because the reader was never the whole mechanism
and a unit assertion on it would pass while the product still ate the reply.

## And the opposite failure, which is measured here rather than assumed

The fabricated verdict from the same live run - *"Based on the harness
diagnosis, you do not need to fine-tune at all"*, a NO_TRAIN decision the
engine never reached, wearing the harness's own name - is still stopped, and
`TheConstructedRealCatchTest` is what the user now sees when it is.

## What was measured, before and after, on the same bank

Twenty conversations, five passes each - **105 turns a side** - against
granite4-hermes through Ollama on a scratch database, both walls live. The bank
carries the three regression questions verbatim, Max's four training phrasings,
the capability question, four definitional questions, two blunt ones and one
two-turn conversation. `scripts/harvest_the_walls.py` IS THAT DRIVER AND THAT
BANK, kept in the tree, because every number this project has argued from was
produced by a driver like it and then thrown away - and `app/provenance.py`
carries a paragraph apologising for exactly that.

                              BEFORE (7f87a5f)        AFTER
    turns                          105                 105
    interrupted                     10  (9.5%)           0  (0%)
      the verdict wall              10                    0
      the provenance wall            0                    0
    verdict cards                    -                   10  (9.5%)
    mean reply                   1,148 chars         1,163 chars
    endings              92 answered, 3 empty     105 answered

**Every interruption on both sides was read, not counted.** The ten before:

  * five are a bare `no` to *"reply with only the word yes or no: should i
    fine-tune?"*. TRUE catches by the reader's own standard - a verdict with
    zero tool calls behind it - and an indefensible thing to do to somebody:
    the user asked for one word and the harness deleted the word and returned
    468 characters about the gates. This is the case that shows annotating is
    better even where the reader is RIGHT.
  * four are false: *"Given that you have an 8 GB GPU ... I would recommend
    starting with a LoRA rank of 8"*, *"The value you should use for LoRA rank
    depends on several factors:"*, *"This split allows for a reasonable balance
    between having enough data for training and a substantial set for
    evaluating model performance"*, and *"However, if you prefer a faster, more
    resource-efficient approach ... LoRA is an excellent choice"*. Two of those
    truncated an answer to *"what is LoRA rank"* and one truncated an answer to
    *"explain the difference between full fine-tuning and LoRA"*.
  * one is *"**Verdict:** **Do NOT train a model yet.**"* - and what the
    harness RELEASED in front of it was *"The harness has diagnosed that there
    are no readable files ... it blocked the gate to training because the
    format of the dataset could not be determined. **Gate Blocked:**
    `format_unreadable`"*. There is no such gate. The wall let a fabricated
    gate ledger through and withheld the sentence closest to the engine's own
    answer. `speaks_for_the_engine` declares that gap; see it.

**And the ten cards after, all of them read.** Seven are true readings: five
`polarity` bare verdicts, one *"Therefore, do not train at this time."*, and
one *"Based on the tools available in this harness, it is indeed worth
considering training a model for your application"* - which is also A LIVE
NEGATIVE CONTROL FOR THE NARROW WALL, correctly declined, because `based on` is
an attribution phrase and `the tools available in this harness` is not the
harness deciding anything. Three are the same misread sentence in three passes:
*"The value you should use for LoRA rank depends on several factors:"*, where
`lora` is an action word and `should use` reaches it.

So the reader is still wrong three times in ten when it fires - four in nine on
an earlier run of the same bank, where it also read the markdown heading
`**Train**:` in a capability answer as a verdict. That cost was a deleted
answer and is now a line saying how the reply READS, under an answer that
arrived whole. It has NOT been tuned in this commit, and the reason is in
`conductor.reads_as_a_verdict`'s own history: it has been tuned four times, and
what made those tunings urgent was that the reader was a wall.

Zero engine-agreement cards appeared, and that is structural rather than
surprising: every conversation in the bank starts with an empty ledger, where
the walk reaches BLOCKED and any settled verdict disagrees with it by
construction. The agreeing arm is asserted over fixtures instead, in
`TheCardIsTheEnginesOwnAnswerTest` and in `test_a_claim_the_engine_agrees_with
_is_annotated_as_agreeing`.

**A SEPARATE RUN OF THE SAME BANK, ON AN INTERMEDIATE BUILD, INTERRUPTED TWICE
- BOTH TIMES THE PROVENANCE WALL**, on *"The dataset has 40000 rows, as
reported by `profile_dataset`"* over a 40,000 the USER typed. Those sentences
sit after the split-ratio sentence the verdict wall used to truncate, so they
were never produced and never read. Taking one wall down let the other see
turns it had never been shown, which is worth knowing before the next person
reads a zero in a harvest table.
"""

from __future__ import annotations

import re
import unittest
from unittest import mock

from app import conductor, diagnosis, events
from app.providers import Delta, ToolCall
from app.providers import store as provider_store
from app.tools import evidence

import diagnosis_fixtures as fixtures
import support


class ScriptedModel:
    id = "fake"
    locality = "local"

    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.drained = 0

    def stream(self, messages, tools=None, *, secret=None):
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


def engine_payload(facts) -> dict:
    """A `run_diagnosis` result, shaped here but DECIDED by the engine."""
    result = diagnosis.diagnose(facts)
    payload = {
        "ok": True,
        "outcome": result.outcome,
        "verdict": result.verdict,
        "say": result.say,
        "gate_ledger": result.gate_ledger,
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


SHIP_AS_IS = engine_payload(fixtures.SPREAD["already_passes"]["facts"])


class TurnTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)

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
        return ready

    def install(self, model):
        original = conductor.build
        conductor.build = lambda *a, **k: model
        self.addCleanup(setattr, conductor, "build", original)
        return model

    def standing_is(self, payload):
        patcher = mock.patch.object(
            conductor, "_standing_diagnosis", return_value=payload
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def thread(self, question):
        row = events.create_thread("t")
        events.add_message(row["id"], "user", question)
        return row["id"]

    def rows(self, thread_id):
        return events.since(f"thread:{thread_id}")

    def prose(self, thread_id):
        return "".join(
            row["payload"].get("text", "")
            for row in self.rows(thread_id)
            if row["kind"] == "chat.delta"
        )

    def ending(self, thread_id):
        return self.rows(thread_id)[-1]["payload"]["ending"]

    def cards(self, thread_id):
        return [
            row["payload"]
            for row in self.rows(thread_id)
            if row["kind"] == conductor.VERDICT_KIND
        ]


class TheThreeFalseCatchesTest(TurnTest):
    """The regression rows. Each one is a live turn, reconstructed.

    Each row is (the question the person asked, the sentence before the one
    that was deleted, THE SENTENCE THAT WAS DELETED, the sentence after it).
    All four have to arrive: the wall took the withheld sentence AND everything
    following it, so a test that only checked the deleted sentence would miss
    half of what the user lost.
    """

    ROWS = (
        (
            "What is LoRA rank and what value should I use?",
            "LoRA rank is the width of the two small matrices LoRA learns. ",
            "Thus, a LoRA rank of 32 would result in smaller matrices which "
            "fits within the available VRAM while still providing sufficient "
            "flexibility for fine-tuning. ",
            "Start at 16 and raise it if the loss plateaus.",
        ),
        (
            "I have 40000 rows across 4 classes. How many per class, and what "
            "does a 10% holdout give me?",
            "A 10% holdout leaves 90% of the rows to learn from. ",
            "This is a common split that balances enough data for robust "
            "evaluation while still leaving sufficient data to train on. ",
            "Stratify it, so each class keeps its share.",
        ),
        (
            # THE PERSON'S OWN FIGURE, and it is here because the
            # reconstruction dropped it. See `## The third row carries a
            # number now` above.
            "What would it cost me to fine-tune a 7B model here? My card "
            "has 8 GB of VRAM.",
            "The cost is your own electricity and your own time. ",
            "Given that your machine has only 8 GB VRAM, it does not have "
            "enough VRAM to fine-tune a 7B model effectively. ",
            "A 3B model with QLoRA is what fits.",
        ),
    )

    def test_every_word_of_all_three_reaches_the_user(self):
        self.connect()
        for question, before, deleted, after in self.ROWS:
            with self.subTest(question=question[:40]):
                thread_id = self.thread(question)
                self.install(ScriptedModel([says(before, deleted, after)]))
                list(conductor.run_turn(thread_id))

                shown = self.prose(thread_id)
                for part in (before, deleted, after):
                    self.assertIn(part.strip(), shown, part[:50])
                self.assertNotEqual(self.ending(thread_id), conductor.WITHHELD)

    def test_and_the_transcript_keeps_them_too(self):
        """The artifact, not just the screen.

        `docs/VISION.md`: the conversation IS the lab notebook, the thing you
        keep and hand to someone else. A sentence removed from `messages` is
        removed from the notebook, and the next turn reads a reply that never
        happened.
        """
        self.connect()
        for question, before, deleted, after in self.ROWS:
            with self.subTest(question=question[:40]):
                thread_id = self.thread(question)
                self.install(ScriptedModel([says(before, deleted, after)]))
                list(conductor.run_turn(thread_id))

                stored = " ".join(
                    message["content"]
                    for message in events.messages_for(thread_id)
                    if message["role"] == "assistant"
                )
                self.assertIn(deleted.strip(), stored)

    def test_the_do_not_train_observation_is_the_one_that_matters_most(self):
        """Named on its own, because deleting it was the product refusing to
        say the thing it exists to say.

        `docs/VISION.md`: *the most valuable thing this product can say is "do
        not train anything"*. The sentence below is that, about the user's own
        machine, and the harness ate it.
        """
        self.connect()
        sentence = (
            "Given that your machine has only 8 GB VRAM, it does not have "
            "enough VRAM to fine-tune a 7B model effectively."
        )
        thread_id = self.thread(
            "What would it cost me to fine-tune a 7B model here? My card "
            "has 8 GB of VRAM."
        )
        self.install(ScriptedModel([says(sentence)]))
        list(conductor.run_turn(thread_id))

        self.assertEqual(self.prose(thread_id), sentence)
        self.assertEqual(self.ending(thread_id), "answered")
        # It DID settle the training decision, so the engine's verdict stands
        # beside it. That is the point: the sentence is kept AND the harness's
        # own answer is on the page.
        self.assertEqual(self.cards(thread_id)[0]["asserted"], conductor.NO_TRAIN)

    def test_but_the_same_sentence_over_nothing_is_the_founding_defect(self):
        """The other direction, pinned, because the row above was edited.

        Strip the person's own figure out of the question and NOTHING in the
        conversation holds 8: no tool ran, the ledger is empty, the brief
        carries the registry and not the hardware. The sentence is then a
        hardware reading with no origin at all - *"a hardcoded 8.0 VRAM ...
        made the app confidently wrong"*, `CLAUDE.md`, down to the same number.

        It is STOPPED, and it has to be, or this file's edit above would be a
        wall tuned to a fixture. What decides is the record and not the words:
        the sentence is byte-identical to the one that reaches the user in the
        test above.
        """
        self.connect()
        sentence = (
            "Given that your machine has only 8 GB VRAM, it does not have "
            "enough VRAM to fine-tune a 7B model effectively."
        )
        thread_id = self.thread("What would it cost me to fine-tune a 7B model here?")
        self.install(ScriptedModel([says(sentence)]))
        list(conductor.run_turn(thread_id))

        self.assertNotIn("8 GB VRAM", self.prose(thread_id))
        self.assertEqual(
            self.ending(thread_id), conductor.MEASUREMENT_WITHHELD
        )


class TheConstructedRealCatchTest(TurnTest):
    """The fabrication from the same live run, and what the user now sees.

    *"Based on the harness diagnosis, you do not need to fine-tune at all"* is
    a NO_TRAIN decision the engine never reached, wearing the harness's own
    name. It is still stopped, and this class is the argument for why that one
    survived when the rest of the wall did not.
    """

    SENTENCE = (
        "Based on the harness diagnosis, you do not need to fine-tune at all."
    )

    def test_it_does_not_reach_the_user(self):
        self.connect()
        thread_id = self.thread("should i fine-tune?")
        self.install(
            ScriptedModel(
                [says("Let me summarise. ", self.SENTENCE + " ", "Here is why. ")]
            )
        )
        list(conductor.run_turn(thread_id))

        shown = self.prose(thread_id)
        self.assertIn("Let me summarise.", shown)
        self.assertNotIn("you do not need to fine-tune at all", shown)
        self.assertNotIn("Here is why.", shown)
        self.assertEqual(self.ending(thread_id), conductor.WITHHELD)

    def test_what_arrives_instead_is_the_engine_s_own_answer(self):
        self.connect()
        thread_id = self.thread("should i fine-tune?")
        self.install(ScriptedModel([says(self.SENTENCE)]))
        list(conductor.run_turn(thread_id))

        shown = self.prose(thread_id)
        self.assertIn("BLOCKED__DEFINE_SUCCESS_FIRST", shown)
        self.assertIn(
            "Nothing downstream is decidable until 'good' is defined.", shown
        )
        self.assertIn("quoting us", shown)

    def test_the_same_claim_without_our_name_on_it_arrives_whole(self):
        """The pair. ONE WORD OF DIFFERENCE, and it is the word that decides.

        "You do not need to fine-tune at all" is an opinion, and an opinion
        beside the engine's verdict is defused because the reader can see both.
        The sentence above is a statement of fact about a record we hold, and
        a record has only one true value.
        """
        self.connect()
        thread_id = self.thread("should i fine-tune?")
        self.install(
            ScriptedModel([says("You do not need to fine-tune at all. ", "Here is why. ")])
        )
        list(conductor.run_turn(thread_id))

        shown = self.prose(thread_id)
        self.assertIn("You do not need to fine-tune at all.", shown)
        self.assertIn("Here is why.", shown)
        self.assertEqual(self.ending(thread_id), "answered")
        card = self.cards(thread_id)[0]
        self.assertEqual(card["asserted"], conductor.NO_TRAIN)
        self.assertEqual(card["verdict"], "BLOCKED")
        self.assertFalse(card["agrees"])


class TheCardIsTheEnginesOwnAnswerTest(TurnTest):
    """What stands beside the reply is the engine's, verbatim, and no more."""

    def test_it_carries_the_verdict_the_sentence_and_the_gates(self):
        self.connect()
        self.standing_is(SHIP_AS_IS)
        thread_id = self.thread("should i fine-tune?")
        self.install(ScriptedModel([says("You should fine-tune a LoRA.")]))
        list(conductor.run_turn(thread_id))

        card = self.cards(thread_id)[0]
        self.assertEqual(card["verdict"], SHIP_AS_IS["verdict"])
        self.assertEqual(card["outcome"], SHIP_AS_IS["outcome"])
        self.assertEqual(card["say"], SHIP_AS_IS["say"])
        self.assertEqual(card["decided_by"], "app/diagnosis.py")
        self.assertEqual(
            card["gates"],
            conductor._gate_line(SHIP_AS_IS["gate_ledger"]),
            "the card drew its own gate line instead of the engine's",
        )
        self.assertTrue(card["computed"])

    def test_a_gate_the_walk_never_reached_is_not_reported_as_unmet(self):
        """`_gate_line`'s rule, asserted where the user actually reads it.

        On an empty ledger the walk stops above the gate tree and all five come
        back NOT_REACHED. Rendering that as "0 of 5 passed; first unmet G0" is
        a gate ledger the engine did not compute - the defect that cost Max his
        answer ten times out of ten - and it must not come back through the
        card.
        """
        self.connect()
        thread_id = self.thread("should i fine-tune?")
        self.install(ScriptedModel([says("You should fine-tune a LoRA.")]))
        list(conductor.run_turn(thread_id))

        card = self.cards(thread_id)[0]
        self.assertIn("no gate was reached", card["text"])
        self.assertNotIn("first unmet", card["text"])

    def test_no_number_in_the_card_was_invented(self):
        """Invariant 5, over every declared outcome rather than over one.

        Every numeral the card's text carries has to be traceable to the engine
        payload it was built from - the gate counts and whatever the engine's
        own sentence says. A card that could put a number on screen that the
        walk did not produce is invariant 3 broken on the surface that exists
        to enforce it.
        """
        settled = conductor._Settled()
        settled.note(conductor.TRAIN, "You should fine-tune.")
        for name, case in fixtures.SPREAD.items():
            with self.subTest(outcome=name):
                payload = engine_payload(case["facts"])
                card = conductor.verdict_annotation(payload, settled)
                source = " ".join(
                    [
                        str(payload.get("say") or ""),
                        str(payload.get("outcome") or ""),
                        str(conductor._gate_line(payload["gate_ledger"]) or ""),
                    ]
                )
                for numeral in re.findall(r"\d+", card["text"]):
                    self.assertIn(
                        numeral,
                        source,
                        f"{numeral} is in the card and in nothing the engine said",
                    )

    def test_the_one_inference_on_the_card_is_marked_as_one(self):
        """The card prints a record and a reading, and says which is which.

        WHAT THE ENGINE REACHED IS A RECORD. What the REPLY settled is
        `reads_as_a_verdict`'s inference, and that reader was wrong in three of
        three live catches. So the half that is a reading has to read as one.

        This is the residual cost of the change, stated where it can be seen:
        the reader still misreads, and a definitional answer about LoRA rank
        can still get a card. It now costs one line saying how the reply READS,
        under an answer that arrived whole, instead of the answer itself.
        """
        self.assertIn("reads as", conductor.VERDICT_DIFFERS)

        self.connect()
        thread_id = self.thread("What is LoRA rank and what value should I use?")
        self.install(
            ScriptedModel(
                [
                    says(
                        "Thus, a LoRA rank of 32 would result in smaller "
                        "matrices which fits within the available VRAM while "
                        "still providing sufficient flexibility for fine-tuning."
                    )
                ]
            )
        )
        list(conductor.run_turn(thread_id))
        card = self.cards(thread_id)[0]
        self.assertIn("This reply reads as settling on TRAIN", card["text"])
        self.assertNotIn("The reply settles on", card["text"])

    def test_the_harness_s_own_half_of_the_card_states_no_number(self):
        """The other half of the invariant, and the stronger one.

        The test above can only see numbers that reached the text; this one
        sees the templates themselves. Every numeral on the card has to have
        come from the engine, so the two sentences the harness writes around
        the engine's answer may not contain one at all.
        """
        for template in (conductor.VERDICT_AGREES, conductor.VERDICT_DIFFERS):
            with self.subTest(template=template[:40]):
                self.assertEqual(re.findall(r"\d", template), [])

    def test_a_turn_that_settled_nothing_gets_no_card(self):
        """The opposite failure, and the one this product keeps making."""
        self.connect()
        for question, answer in (
            ("what does LoRA mean?", "LoRA means low-rank adaptation."),
            ("what is my GPU?", "You have an RTX 4070 with 12 GB of VRAM."),
            ("what is this?", "One chat box for the whole of machine learning."),
        ):
            with self.subTest(question=question):
                thread_id = self.thread(question)
                self.install(ScriptedModel([says(answer)]))
                list(conductor.run_turn(thread_id))
                self.assertEqual(self.cards(thread_id), [])

    def test_one_card_per_turn_however_many_sentences_settled_it(self):
        self.connect()
        thread_id = self.thread("should i fine-tune?")
        self.install(
            ScriptedModel(
                [
                    says(
                        "You should fine-tune. ",
                        "Fine-tuning is worth it. ",
                        "You need to fine-tune here. ",
                    )
                ]
            )
        )
        list(conductor.run_turn(thread_id))

        cards = self.cards(thread_id)
        self.assertEqual(len(cards), 1)
        self.assertEqual(len(cards[0]["sentences"]), 3)

    def test_agreement_needs_every_sentence_and_not_just_the_last(self):
        """A reply that contradicts itself has disagreed, whatever it ends on.

        Otherwise the annotation would do quietly what the deletion used to do
        loudly: pick one half of the reply and report it as the whole.
        """
        settled = conductor._Settled()
        settled.note(conductor.TRAIN, "You should fine-tune.")
        settled.note(conductor.NO_TRAIN, "You should not fine-tune.")
        card = conductor.verdict_annotation(SHIP_AS_IS, settled)
        self.assertEqual(card["asserted"], conductor.NO_TRAIN)
        self.assertFalse(card["agrees"])


class TheReaderIsNoLongerAWallTest(unittest.TestCase):
    """The property, over the sentences the old wall stopped.

    Every one of these is read as a verdict by `reads_as_a_verdict` - that has
    not changed and is not the point. The point is that none of them costs the
    user a reply any more, because none of them speaks for the engine.
    """

    SETTLED_BUT_THE_MODEL_S_OWN = (
        "You should fine-tune a model for this application.",
        "You do not need to fine-tune here.",
        "I recommend fine-tuning on your export.",
        "Fine-tuning would be premature.",
        "Your model should not be fine-tuned right now.",
        "A fine-tune should be run on your data.",
        "Train a model.",
        "This is a substantial dataset that should be sufficient for training "
        "or fine-tuning a model.",
        "Your team should fine-tune a model for this.",
    )

    def test_none_of_them_is_a_borrowed_verdict(self):
        for sentence in self.SETTLED_BUT_THE_MODEL_S_OWN:
            with self.subTest(sentence=sentence[:50]):
                self.assertIsNotNone(
                    conductor.reads_as_a_verdict(sentence),
                    "the row no longer exercises the reader at all",
                )
                self.assertIsNone(
                    conductor.reads_as_a_borrowed_verdict(sentence),
                    "this sentence still costs the user their reply",
                )

    def test_the_same_sentences_with_our_name_on_them_all_are(self):
        """One prefix, nine sentences, and the whole of what still stops.

        ONE OF THE NINE IS EXPECTED TO FALL OUT and the count is asserted, so
        this cannot quietly become a test where every row is skipped. The one
        is the bare imperative - *"Train a model."* - which `_BARE_LIMIT` reads
        only at four words or fewer, and the prefix makes it five. The reader
        is a grammar and a prefix is part of the grammar.
        """
        moved_out_of_frame = 0
        for sentence in self.SETTLED_BUT_THE_MODEL_S_OWN:
            with self.subTest(sentence=sentence[:50]):
                claimed = f"The harness says {sentence[0].lower()}{sentence[1:]}"
                if conductor.reads_as_a_verdict(claimed) is None:
                    moved_out_of_frame += 1
                    continue
                self.assertIsNotNone(
                    conductor.reads_as_a_borrowed_verdict(claimed), claimed
                )
        self.assertEqual(moved_out_of_frame, 1)


class SpeakingForTheEngineIsAGrammarTest(unittest.TestCase):
    """The narrow reader on its own, both directions."""

    SPEAKS = (
        "Based on the harness diagnosis, you do not need to fine-tune at all.",
        "According to the harness, you should fine-tune.",
        "The harness says you should fine-tune.",
        "The diagnosis engine concluded that you should fine-tune.",
        "The harness's verdict is that you should not fine-tune.",
        "run_diagnosis determined that you do not need to fine-tune.",
        "You do not need to fine-tune, according to the harness.",
        "The harness has already decided you should fine-tune.",
        "Per the harness, you should fine-tune.",
        "It was determined by the harness that you should fine-tune.",
        # THE PREFIX TRAP. `the harness` is a prefix of `the harness's
        # diagnosis engine`, so a name list read shortest-first ends the name
        # two words early and leaves `diagnosis engine` standing between it and
        # the verb. `_ENGINE_NAMES` is sorted longest-first for this row.
        "The harness's diagnosis engine concluded that you should fine-tune.",
        "The harness's engine says you should fine-tune.",
    )

    #: Live sentences and near misses. None of these puts a verdict in our
    #: mouth, and the last two are this product describing itself - which is
    #: most of what it says.
    DOES_NOT = (
        "The harness has listed 28 tools that are registered on this machine.",
        "The harness will run a diagnosis before recommending anything.",
        "The engine is a decision layer above the trainer.",
        "You should fine-tune a model for this application.",
        "I recommend fine-tuning on your export.",
        'The harness will never tell you "you should fine-tune" without an '
        "eval set.",
        "Run run_diagnosis and it will tell you whether to fine-tune.",
        # THE TWO BARE PREPOSITIONS, which is where a reader like this goes
        # wrong. In both of these the engine's name modifies a NOUN and nobody
        # has claimed it decided anything. `_INTRODUCERS` carries the note.
        "Given 40,000 rows from the diagnosis run, you should fine-tune.",
        "A model trained by the harness is still your model, and you should "
        "fine-tune it.",
        # A COPULA WITH NO RESULT NOUN IN FRONT OF IT. This is the harness
        # being described, which is most of what this product says about
        # itself, and `_asserts_after` requires the noun for exactly this row.
        "The harness is a decision layer and you should fine-tune.",
        # LIVE, from the after run: an attribution phrase, this harness named,
        # and a training recommendation - and the harness is not what the
        # phrase attributes to. `based on THE TOOLS AVAILABLE IN this harness`
        # is the model reasoning from a registry, not quoting a verdict.
        "Based on the tools available in this harness, it is indeed worth "
        "considering training a model for your application.",
    )

    def test_it_reads_the_ones_that_do(self):
        for sentence in self.SPEAKS:
            with self.subTest(sentence=sentence[:50]):
                self.assertTrue(conductor.speaks_for_the_engine(sentence))

    def test_it_declines_the_ones_that_do_not(self):
        for sentence in self.DOES_NOT:
            with self.subTest(sentence=sentence[:50]):
                self.assertFalse(conductor.speaks_for_the_engine(sentence))

    def test_naming_a_verdict_in_quotation_marks_is_not_handing_one_down(self):
        """`_read_quotes`' rule, applied to the attribution as well as the frame.

        *The harness will never tell you "you should fine-tune"* is this
        product describing itself, and it is a live sentence.
        """
        self.assertFalse(
            conductor.speaks_for_the_engine(
                'It is wrong to say "the harness says you should fine-tune".'
            )
        )

    def test_the_vocabulary_is_provenance_s_and_not_a_second_copy(self):
        """One list of what this harness calls itself, in both walls.

        Two copies would be two vocabularies drifting apart in the two places
        that most need to agree about who "the harness" is.
        """
        for name in provenance_names():
            self.assertIn(name, conductor._ENGINE_NAMES)

    def test_every_attributing_verb_provenance_harvested_is_read_here(self):
        for verb in conductor.provenance.ATTRIBUTES:
            self.assertIn(verb, conductor._SPEAKS)


def provenance_names():
    return conductor.provenance.HARNESS_NAMES


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
