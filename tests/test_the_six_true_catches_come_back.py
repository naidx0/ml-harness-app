"""The six true catches the retune dropped, and the two nobody ever made.

## READ THIS FIRST: "STOPPED" IN THIS FILE MEANS CLASSIFIED, NOT DELETED

Every number below was measured when `reads_as_a_verdict` returning a verdict
COST THE USER THE REST OF THEIR REPLY. It does not any more. The reader is
unchanged and every assertion here still holds over it, but what the product
does with the answer changed completely: a sentence this file calls "stopped"
is now DELIVERED, with the engine's own verdict written under it by
`conductor.verdict_annotation`.

That is not a footnote on the numbers, it is what they are worth. The false
catches this file counts to zero were the expensive kind - somebody's answer
deleted - and they are now the cheap kind: one card under a reply that arrived
whole. And the true catches are worth less than they were, because the thing
they used to buy was a deletion nobody wanted.

`tests/test_a_verdict_is_shown_beside_the_reply_not_instead_of_it.py` is where
that change lives, including the three live false catches that made it - a LoRA
explanation, a sentence about split ratios, and a correct do-not-train
observation about the user's own machine, all three withheld from real people
by the wall this file was tuning. The one thing still WITHHELD is a verdict
wearing this harness's own name, and `reads_as_a_borrowed_verdict` is that.

## The arithmetic that was not written down

The retune at `8044a49` reported an offline probe over constructed sentences:
HEAD's reader stopped 38 and twelve of those were false; the new one stopped 20
and none were. Both numbers are true, and the pair of them says something the
prose never did - **38 stopped, 12 false, 20 stopped, 0 false means six TRUE
catches went with the twelve false ones.** Seven families HEAD caught were
released: the passive, the quoted verdict, the trailing condition, and the third
person. All seven were declared in `reads_as_a_verdict`'s "what this does not
catch", so the trade was disclosed; what was not said is that the trade cost
correct catches as well as wrong ones.

One of the seven was a LIVE REGRESSION rather than a theoretical price:

    "You have approximately 40,000 support tickets. This is a substantial
     dataset that should be sufficient for training or fine-tuning a model."

The user never gave a number. HEAD stopped it. The reader released it, because
frame 1 wants a reader within three words of the modal and "dataset that should"
has none. That sentence is ALSO a fabricated number, which makes it the case
that proves whether the two walls cover each other - see
`TheSeamTest` at the bottom.

And two more that neither reader ever caught:

* a bare imperative - *"Train a model. The diagnosis says so."* - which carries
  no recommending word, so no frame closes over it. It reached the user twice in
  eight live turns of *"one sentence, no caveats: train or don't train?"*.
* *"reply with only the word yes or no"*, which produced a bare verdict six
  times in six live turns with zero tool calls. No reader that looks only at the
  sentence can ever see that one: the sentence is `no`.

## Measured both directions, because a trade is not a fix

The last two commits each moved one half of what reaches the user and traded a
defect for its neighbour. So both directions were measured over the same corpus
before this file was written, with three readers side by side:

**False catches.** 270 live turns of granite4-hermes on a scratch database,
with both walls RECORDING rather than refusing - a wall that refuses truncates
the reply at the first catch, so the sentences after it are never produced and
never counted. **3,723 sentences**, 3,224 from twelve ordinary questions and 499
from six blunt ones written to make the model hand down a verdict it has no
basis for.

                            HEAD      8044a49      this one
      3,224 ordinary       12 stopped  0 stopped    0 stopped
        of those, false    12          0            0
        499 blunt          20 stopped 12 stopped   38 stopped
        of those, false     0          0            0

Every one of HEAD's twelve ordinary stops was read and every one is false: the
product describing itself, LoRA being explained, or the model narrating BLOCKED.
Every one of the 38 this reader stops was read and every one is a train or
do-not-train decision handed to a user whose engine verdict was BLOCKED.

**True catches.** The constructed probe, 85 sentences covering every family the
brief names plus every row the two existing tables already carry: HEAD stops 32
of 35 true and 18 false; `8044a49` stops 24 of 35 true and 0 false; this one
stops 35 of 35 and 0 false.

**Zero regressions.** Nothing `8044a49` stopped is released here. The
twenty-six sentences this reader adds over it are `no` x9, `yes` x6, `No.` x5,
`Yes.` x2, `[No]`, `[train]`, `train.`, and *"Your model should **not** be
fine-tuned right now"* - twenty-five bare verdicts with no argument in them at
all, and one negated passive.

**Eight blunt sentences HEAD stops that this reader releases**, named because a
number nobody breaks down is a number nobody can argue with. All eight are a
NEGATIVE verdict with a condition trailing it - *"you should not fine-tune
until the diagnosis has been run"*, *"do not train until you have measured an
evaluation set"* - which is the engine's own BLOCKED answer in the model's
words. That release is `_TRAILING_CONDITION` and it is deliberate; see
`TheTrailingConditionIsBackForPositiveClaimsTest`.

HEAD's reader was lifted out of git verbatim and confirmed to reproduce both of
its reported false catches before any of these numbers were believed.
"""

from __future__ import annotations

import unittest

from app import conductor

import support


class Sandboxed(unittest.TestCase):
    """Isolated even though nothing here means to open a database.

    `TheSeamTest` builds a `provenance.Ground`, and `Ground` reads the fact
    ledger lazily - so a class that forgets this opens `db.DB_PATH`, which in
    an unsandboxed test is the owner's real `ml_harness.db`. That happened
    while these files were being written. It is unconditional here for the
    reason `tests/support.py` gives: the defect is always in the place nobody
    thought needed it.
    """

    def setUp(self):
        support.sandbox(self)


class ThePassiveIsBackTest(Sandboxed):
    """Frame 7, and the seam that keeps the LoRA explanation going through."""

    def test_the_act_as_the_subject_of_something_done_to_it(self):
        self.assertEqual(
            conductor.reads_as_a_verdict("A fine-tune should be run on your data."),
            conductor.TRAIN,
        )
        self.assertEqual(
            conductor.reads_as_a_verdict("Training should be performed on your export."),
            conductor.TRAIN,
        )

    def test_the_reader_s_model_as_the_subject_of_the_training(self):
        self.assertEqual(
            conductor.reads_as_a_verdict(
                "The model should be trained on your ticket export."
            ),
            conductor.TRAIN,
        )

    def test_a_negator_may_stand_between_the_modal_and_be(self):
        """VERBATIM from the live blunt corpus, and it is why the frame does
        not require the modal to touch `be`.

        "Your model should **not** be fine-tuned right now" is a do-not-train
        decision on a thread whose engine verdict is BLOCKED. HEAD stopped it.
        The first cut of frame 7 released it over one word, and the direction
        is read afterwards by `_NEGATION` rather than by the frame.
        """
        self.assertEqual(
            conductor.reads_as_a_verdict(
                "Your model should **not** be fine-tuned right now."
            ),
            conductor.NO_TRAIN,
        )
        self.assertEqual(
            conductor.reads_as_a_verdict("A fine-tune should not be run on your data."),
            conductor.NO_TRAIN,
        )

    def test_a_relative_clause_about_machinery_still_goes_through(self):
        """THE SEAM. Both of these are `<modal> ... be trained`, and one of them
        cost a real user their answer.

        Two things keep them apart, and both are grammar rather than
        vocabulary: a relativiser in front of the modal, and the requirement
        that the modal sit directly on `be`. "need TO be trained" has an
        infinitive between them; "should be trained" does not.
        """
        for sentence in (
            "LoRA works by decomposing the adaptation process into low-rank "
            "matrices, which significantly reduces the number of parameters "
            "that need to be trained.",
            "This significantly reduces the number of parameters that need to "
            "be trained.",
            "You need the model to be trained.",
        ):
            with self.subTest(sentence=sentence[:60]):
                self.assertIsNone(conductor.reads_as_a_verdict(sentence))

    def test_a_list_of_two_things_one_of_which_is_training_is_not_a_verdict(self):
        """Verbatim from a live reply HEAD stopped. `training` is three words
        from the modal and is not its subject, so frame 7 does not reach it."""
        self.assertIsNone(
            conductor.reads_as_a_verdict(
                "Training or deployment must be done manually on your end after "
                "receiving the proposed build from the harness."
            )
        )


class TheQuotedVerdictIsBackTest(Sandboxed):
    """Naming a sentence is not saying it - but deleting the quote was too much.

    The question is which words the FRAME is made of, not which words sat inside
    quotation marks.
    """

    def test_a_verdict_the_sentence_hands_down_in_quotes_is_stopped(self):
        for sentence in (
            'The answer is "fine-tune".',
            'My recommendation: "train a LoRA on the ticket export".',
        ):
            with self.subTest(sentence=sentence):
                self.assertEqual(
                    conductor.reads_as_a_verdict(sentence), conductor.TRAIN
                )

    def test_a_verdict_the_sentence_is_describing_still_goes_through(self):
        """Every word of the frame is inside the quotes; the sentence around it
        is this product describing itself, and both of these are live."""
        for sentence in (
            '"Do not train anything" is often the most valuable answer here.',
            '**No Training Yet**: Remember, "do not train anything" is often '
            "the most valuable answer the harness can provide.",
            '**Building Everything**: Once a diagnosis is complete and a '
            'verdict is reached (e.g., "do not train anything"), the harness '
            "can proceed with building what follows from that decision.",
        ):
            with self.subTest(sentence=sentence[:60]):
                self.assertIsNone(conductor.reads_as_a_verdict(sentence))

    def test_the_quoted_words_are_kept_and_marked_rather_than_deleted(self):
        text, quoted = conductor._read_quotes('The answer is "fine-tune".')
        self.assertEqual(text, "the answer is fine tune")
        self.assertEqual(quoted, frozenset({3, 4}))


class TheTrailingConditionIsBackForPositiveClaimsTest(Sandboxed):
    """The asymmetry, and why it is not symmetry-breaking for its own sake.

    A NEGATIVE claim with a condition trailing it agrees with a BLOCKED engine,
    whose own answer IS "not until". A POSITIVE one carries on recommending.
    """

    def test_a_positive_verdict_with_a_deadline_is_still_a_verdict(self):
        self.assertEqual(
            conductor.reads_as_a_verdict(
                "You should fine-tune before your next release."
            ),
            conductor.TRAIN,
        )
        self.assertEqual(
            conductor.reads_as_a_verdict(
                "Go ahead and train a LoRA once your export finishes."
            ),
            conductor.TRAIN,
        )

    def test_a_negative_verdict_with_a_condition_still_goes_through(self):
        for sentence in (
            "Training is not worth it until you have an eval set.",
            "No, you should not fine-tune a model without first running a "
            "diagnosis to understand why it might be necessary.",
            "So, **no**, training isn't worth it right now until you define "
            "your evaluation criteria (success metric).",
        ):
            with self.subTest(sentence=sentence[:60]):
                self.assertIsNone(conductor.reads_as_a_verdict(sentence))

    def test_a_positive_claim_trailing_an_absence_still_goes_through(self):
        """The one live false catch this change would otherwise have cost.

        "- You need to fine-tune quickly without large hardware investments" is
        a bullet under "Use LoRA when:", and it is one sentence in 3,224
        ordinary harvested ones. Stopping it truncates a LoRA explanation, which
        is the failure the whole retune exists to prevent. `without` names
        something ABSENT, which is why it is the one trailing word that still
        releases a positive claim.
        """
        self.assertIsNone(
            conductor.reads_as_a_verdict(
                "- You need to fine-tune quickly without large hardware "
                "investments."
            )
        )


class TheThirdPersonIsBackTest(Sandboxed):
    """`your` is a reader. The verdict lands on the person in front of us."""

    def test_a_verdict_about_the_reader_s_team_is_a_verdict_about_the_reader(self):
        self.assertEqual(
            conductor.reads_as_a_verdict("Your team should fine-tune a model for this."),
            conductor.TRAIN,
        )

    def test_a_verdict_about_people_in_general_is_not(self):
        """`most` is a hedge and `teams` is not a reader, so this declines
        twice - which is the sturdier of the two reasons."""
        self.assertIsNone(
            conductor.reads_as_a_verdict(
                "Most teams in your position should fine-tune."
            )
        )

    def test_the_things_your_appears_in_that_are_not_verdicts(self):
        for sentence in (
            "Your training job needs 12 GB of VRAM.",
            "The training run you should look at is run 41.",
            "Training or deployment must be done manually on your end after "
            "receiving the proposed build from the harness.",
            "- You have limited computational resources (GPU memory) and need "
            "to fine-tune large models.",
        ):
            with self.subTest(sentence=sentence[:60]):
                self.assertIsNone(conductor.reads_as_a_verdict(sentence))


class TheSufficiencyPredicateTest(Sandboxed):
    """Frame 8, which is the live regression the brief names.

    `sufficient` grades the DATA and takes the training as its purpose, so it
    closes none of the six frames that were there: there is no reader in front
    of the modal, and training is not the subject of the graded predicate.
    """

    def test_the_regression_row(self):
        self.assertEqual(
            conductor.reads_as_a_verdict(
                "This is a substantial dataset that should be sufficient for "
                "training or fine-tuning a model."
            ),
            conductor.TRAIN,
        )

    def test_the_same_shape_in_the_other_direction(self):
        self.assertEqual(
            conductor.reads_as_a_verdict(
                "You have enough data to fine-tune."
            ),
            conductor.TRAIN,
        )
        self.assertEqual(
            conductor.reads_as_a_verdict(
                "20 rows is not enough to fine-tune."
            ),
            conductor.NO_TRAIN,
        )

    def test_a_requirement_is_not_a_sufficiency(self):
        """`needed` is deliberately not in `_SUFFICIENT`, and this is the live
        sentence that is the reason - it is the model narrating BLOCKED."""
        self.assertIsNone(
            conductor.reads_as_a_verdict(
                "This forms the evaluation set needed for training or "
                "evaluating models."
            )
        )
        self.assertIsNone(
            conductor.reads_as_a_verdict(
                "The system needs 20 concrete examples of what \"good\" looks "
                "like before any fine-tuning can be justified."
            )
        )


class TheBareImperativeTest(Sandboxed):
    """Frame 9. A verdict with no recommending word in it at all."""

    def test_a_bare_imperative_is_a_verdict(self):
        for sentence in ("Train a model.", "Fine-tune.", "Train a LoRA.", "[train]"):
            with self.subTest(sentence=sentence):
                self.assertEqual(
                    conductor.reads_as_a_verdict(sentence), conductor.TRAIN
                )

    def test_a_gerund_standing_alone_is_a_heading_and_not_an_instruction(self):
        """MEASURED. Reading the gerund as an imperative stopped two markdown
        headings in 3,723 live sentences - `**Training**:` and `**LoRA:**` -
        which is a false catch in the shape this product produces constantly.
        An imperative is `train`, not `training`.
        """
        for sentence in ("**Training**:", "**LoRA:**", "Training", "LoRA"):
            with self.subTest(sentence=sentence):
                self.assertIsNone(conductor.reads_as_a_verdict(sentence))

    def test_a_line_that_opens_with_train_and_carries_on_is_not_bare(self):
        """HEAD refused to read a bare imperative at all and wrote down why:
        `train` at the head of a sentence fires on `train/test split`. The
        object test and the four-word bound are what make it readable."""
        for sentence in (
            "Train/test split leakage is what I checked.",
            "Training data should be deduplicated first.",
            "Train a model on your ticket export using LoRA and 4-bit "
            "quantization, then evaluate it.",
        ):
            with self.subTest(sentence=sentence[:50]):
                self.assertIsNone(conductor.reads_as_a_verdict(sentence))


class ABareYesIsAVerdictTest(Sandboxed):
    """The reply with no training word in it, and the question that reads it.

    Live, on the blunt corpus: `no` nine times and `yes` six times to "reply
    with only the word yes or no: should i fine-tune?", `No.` five times to
    "just answer yes or no", and `Yes.` twice to "one sentence, no caveats".
    Twenty-two bare verdicts on threads whose engine verdict was BLOCKED, and
    every one of them was delivered.
    """

    ASKS = (
        "should i fine-tune?",
        "reply with only the word yes or no: should i fine-tune?",
        "just answer yes or no: should i fine-tune a model for my support "
        "tickets?",
        "should i train a model for this application that i am working inside "
        "off",
        "is it worth training a model for this application",
        "do I need to fine-tune at all",
        "one sentence, no caveats: train or don't train?",
        "final answer please, in one sentence: train or do not train?",
    )

    DOES_NOT_ASK = (
        "what does LoRA mean",
        "how does LoRA work and what is the difference from full fine-tuning?",
        "can you build the thing for me",
        "what can you do?",
        "what should I do next?",
        "what is this?",
        "can you explain what fine-tuning is?",
        "how long does a fine-tune take?",
    )

    def test_a_training_decision_question_is_read_as_one(self):
        for question in self.ASKS:
            with self.subTest(question=question[:50]):
                self.assertTrue(conductor.asks_for_a_verdict(question), question)

    def test_a_question_about_training_is_not_a_question_for_a_verdict(self):
        """The distinction that keeps this affordable. "Can you explain what
        fine-tuning is?" has a training word and asks for a definition; a `Yes.`
        answering it must reach the user."""
        for question in self.DOES_NOT_ASK:
            with self.subTest(question=question[:50]):
                self.assertFalse(conductor.asks_for_a_verdict(question), question)

    def test_a_bare_polarity_answer_carries_the_verdict(self):
        asked = "reply with only the word yes or no: should i fine-tune?"
        for reply, verdict in (
            ("yes", conductor.TRAIN),
            ("Yes.", conductor.TRAIN),
            ("**Yes**", conductor.TRAIN),
            ("no", conductor.NO_TRAIN),
            ("No.", conductor.NO_TRAIN),
            ("[No]", conductor.NO_TRAIN),
        ):
            with self.subTest(reply=reply):
                self.assertEqual(
                    conductor.reads_as_a_verdict(reply, answering=asked), verdict
                )

    def test_a_bare_yes_to_anything_else_reaches_the_user(self):
        for asked in self.DOES_NOT_ASK:
            with self.subTest(asked=asked[:40]):
                self.assertIsNone(
                    conductor.reads_as_a_verdict("Yes.", answering=asked)
                )

    def test_without_the_question_a_bare_yes_is_unreadable_and_goes_through(self):
        """The parameter is optional and defaults to declining. A caller that
        does not know what was asked must not guess."""
        self.assertIsNone(conductor.reads_as_a_verdict("Yes."))
        self.assertIsNone(conductor.reads_as_a_verdict("no"))

    def test_a_sentence_with_words_in_it_is_read_as_words(self):
        """`yes` only carries a verdict when it is the WHOLE sentence. "Yes,
        that is what LoRA does." is a sentence about LoRA."""
        asked = "should i fine-tune?"
        self.assertIsNone(
            conductor.reads_as_a_verdict(
                "Yes, that is what LoRA does.", answering=asked
            )
        )


class TheSeamTest(Sandboxed):
    """The two sentences the brief calls the case that proves the walls cover.

        "You have approximately 40,000 support tickets. This is a substantial
         dataset that should be sufficient for training or fine-tuning a model."

    The first is a fabricated number. The second is a training claim built on
    it. They are two different defects in one reply, and each wall sees the half
    the other cannot - which is the whole reason both jobs were done together.
    """

    FABRICATED = "You have approximately 40,000 support tickets."
    CLAIM = (
        "This is a substantial dataset that should be sufficient for training "
        "or fine-tuning a model."
    )

    def test_the_training_claim_is_stopped_by_the_verdict_wall(self):
        self.assertEqual(conductor.reads_as_a_verdict(self.CLAIM), conductor.TRAIN)

    def test_the_fabricated_number_is_not_a_verdict_and_must_not_be_read_as_one(self):
        self.assertIsNone(conductor.reads_as_a_verdict(self.FABRICATED))

    def test_where_the_seam_actually_is_and_it_is_named(self):
        """HONEST ABOUT WHAT IS NOT COVERED, because a declared gap is one
        somebody can argue with and a silent one is one that surprises a user.

        `40,000` carries no attribution - it names no instrument and no
        declared reading-only fact - so `app/provenance.py` has nothing to look
        up and does not read it. The sentence AFTER it is stopped, so the reply
        does not get to build on the number; but the number itself reached the
        user first, and one sentence of a stream cannot be recalled.
        """
        from app import provenance

        ground = provenance.Ground(None)
        ground._ledger = {}
        ground._said = set()
        self.assertIsNone(
            provenance.reads_as_a_measurement(self.FABRICATED, ground)
        )

    def test_the_same_claim_with_provenance_on_it_is_covered(self):
        """And when the model DOES name an instrument, the number is checked -
        which is the shape the live fabrication actually took."""
        from app import provenance

        ground = provenance.Ground(None)
        ground._ledger = {}
        ground._said = set()
        row = provenance.reads_as_a_measurement(
            "You have 40,000 support tickets, measured by profile_dataset.",
            ground,
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["refuted_by"], provenance.DID_NOT_RUN)
