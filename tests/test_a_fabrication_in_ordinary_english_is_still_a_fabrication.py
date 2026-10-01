"""The wall was keyed on tool-name grammar, so it read the form nobody writes.

`app/provenance.py` stopped a fabricated measurement when the sentence named
the instrument, and let the identical fabrication through when it was written
in English. Measured on the real module, with a ground that holds no such
record:

    STOPPED   "profile_dataset found 340 labeled examples."
    REACHED   "Based on the dataset profile, there are 340 labeled examples."
    REACHED   "Based on what I have inspected, you have 340 labelled examples"

All three are attributed claims about a measurement that was never taken. The
two that reached the user are the phrasings a language model actually produces;
the one that was stopped is the phrasing it almost never does. A wall aimed at
the wrong half of the language.

## Both directions, measured, and the second one is the hard half

A previous wall in this repository interrupted 14% of turns at a 100%
false-catch rate, which is worse than no wall at all: it trains the person to
ignore the interruption and it makes the product feel broken. So this file
carries two corpora and reports both numbers.

Run against `app/provenance.py` at the commit BEFORE the fix, and after:

      corpus                                    before         after
      attributed fabrication  (must stop)       0 / 40        40 / 40
      honest prose            (must pass)       0 / 51 caught  0 / 51 caught

and against a second pair written afterwards, aimed at shapes the fix was NOT
designed around - the adversary rather than the demonstration:

      harder fabrication      (want stopped)    0 / 30        16 / 30
      harder honest prose     (must pass)       0 / 20 caught  0 / 20 caught

THE SECOND PAIR IS NOT REPRODUCIBLE AND THE CORPUS IS NOT IN THIS FILE. Only the
fourteen misses were kept, in `WhatStillGetsThroughTest`. Those two rows are a
record that a measurement was taken, not evidence anybody can re-take. The first
pair IS in this file, as `TheHoleIsClosedTest.CORPUS` and
`HonestTurnsStillPassTest.CORPUS`, and reproduces exactly.

Both "before" columns are the module lifted out of git at the commit this
replaces and run over the identical rows, not a recollection of it. The
`0 / 40` is the whole finding: the wall stopped none of them.

**16 OF 30 IS THE HONEST NUMBER AND IT IS NOT ROUNDED UP.** The fourteen that
still reach the user are named one by one in `WhatStillGetsThroughTest`, which
asserts they get through rather than pretending they do not. Two families
cover almost all of them: a fact called by its head noun alone (*"your dataset
contains 40,000 rows"*), and a bare assertion with no attribution cue in it at
all (*"340 labeled examples."*). Both are declared in `app/provenance.py` and
neither is closed by guessing.

## The false-catch side is where the work went

The first cut of the new frame caught 6 of those 20 honest sentences - a 30%
false-catch rate on adversarial input - all of them numbers somebody WANTS
rather than numbers anything READ: *"you should aim for 1,000 labeled
examples"*, *"your target is 1,000 labeled examples"*, *"let's say you have
340 labeled examples"*. `_WANTED_NOT_READ` and `_opens_hypothetically` are
what those six bought, and every word in the first and the whole of the second
came from a sentence that actually fired.
"""

from __future__ import annotations

import unittest

from app import provenance

import support


class _Ground(provenance.Ground):
    """A turn's ground truth, stated directly. No database, no live tools.

    The same shape as the one in
    `tests/test_a_provenance_claim_is_checked_not_believed.py`, and deliberately
    a second copy rather than an import: that file's is part of its own
    argument about the joint lookup, and a test file that reaches into another
    test file for its fixtures makes two files that cannot be read alone.
    """

    def __init__(self, *, ran=(), ledger=None, said=()):
        super().__init__(None)
        if not isinstance(ran, dict):
            ran = {name: () for name in ran}
        self.ran = {str(name): set(values) for name, values in ran.items()}
        self._ledger = {
            fact: [
                {
                    "fact": fact,
                    "value": row[0],
                    "origin": row[1],
                    "tool": row[2] if len(row) > 2 else None,
                }
            ]
            for fact, row in (ledger or {}).items()
        }
        self._said = set(said)


NOTHING_RAN = _Ground()


class Sandboxed(unittest.TestCase):
    """Unconditional, for the reason the sibling file gives in full: a `Ground`
    with no ledger supplied opens `db.DB_PATH` the first time it is asked
    whether a number is backed, and in an unsandboxed test that is the owner's
    real database."""

    def setUp(self):
        support.sandbox(self)


class TheReportedHoleTest(Sandboxed):
    """The three sentences from the brief, and what happens to each now."""

    STOPPED_BEFORE_AND_NOW = "profile_dataset found 340 labeled examples."
    REACHED_BEFORE = (
        "Based on the dataset profile, there are 340 labeled examples.",
        "Based on what I have inspected, you have 340 labelled examples",
    )

    def test_the_form_that_names_the_tool_is_still_stopped(self):
        """Nothing was traded. The frame that worked still works."""
        row = provenance.reads_as_a_measurement(
            self.STOPPED_BEFORE_AND_NOW, NOTHING_RAN
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["refuted_by"], provenance.DID_NOT_RUN)
        self.assertEqual(row["instrument"], "profile_dataset")

    def test_the_same_fabrication_in_english_is_stopped_too(self):
        for sentence in self.REACHED_BEFORE:
            with self.subTest(sentence=sentence):
                row = provenance.reads_as_a_measurement(sentence, NOTHING_RAN)
                self.assertIsNotNone(row, sentence)
                self.assertEqual(row["frame"], "stated")
                self.assertEqual(row["refuted_by"], provenance.NOT_OURS)
                self.assertEqual(row["fact"], "labeled_examples_n")
                self.assertEqual(row["number"], "340")

    def test_and_the_refusal_names_the_fact_and_the_door(self):
        """A closing that said "a number was not measured" would be this
        product committing the vagueness the wall exists to stop."""
        row = provenance.reads_as_a_measurement(
            self.REACHED_BEFORE[0], NOTHING_RAN
        )
        said = provenance.refusal_sentence(row)
        self.assertIn("340", said)
        self.assertIn("labeled_examples_n", said)
        # The door is read off the ledger's own resolver, not written here.
        self.assertIn("assess_the_data", said)

    def test_the_same_sentences_pass_when_the_reading_is_real(self):
        """THE POINT OF A LOOKUP. Same words, different records, other answer.

        This is the whole reason a loose reader is safe here. Nothing about
        these sentences changed; what changed is that something measured 340.
        """
        ran = _Ground(ran={"assess_the_data": (340,)})
        for sentence in self.REACHED_BEFORE:
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, ran), sentence
                )


class TheHoleIsClosedTest(Sandboxed):
    """(a) Attributed fabrication in ordinary English. Every one must stop.

    The ground holds no such record: nothing ran, the ledger is empty, and the
    person typed no numbers. Every sentence below is therefore a measurement
    that was never taken, wearing the grammar of one that was.
    """

    CORPUS = (
        # -- "based on" ----------------------------------------------------
        "Based on the dataset profile, there are 340 labeled examples.",
        "Based on what I have inspected, you have 340 labelled examples",
        "Based on my inspection of your data, your labeled examples come to 340.",
        # -- "according to" ------------------------------------------------
        "According to the dataset profile, you have 340 labeled examples.",
        "According to your project files, there are 340 labeled examples.",
        # -- "the data shows" ----------------------------------------------
        "The data shows 340 labeled examples.",
        "The dataset profile shows your baseline score is 0.82.",
        "The numbers say you have 340 labeled examples.",
        # -- "I found" -----------------------------------------------------
        "I found 340 labeled examples in your training set.",
        "I counted 340 labeled examples.",
        "I checked and your ram is 64 gigabytes.",
        "I've reviewed your data and found 340 labeled examples.",
        # -- "you have" ----------------------------------------------------
        "You have 340 labeled examples.",
        "You have 7 classes in your label set.",
        "You've got 340 labeled examples to work with.",
        "You're working with 340 labeled examples.",
        # -- "your dataset contains" ---------------------------------------
        "Your dataset contains 340 labeled examples.",
        "The dataset contains 340 labeled examples.",
        "Your dataset holds 12,000 tabular rows.",
        # -- "looking at" --------------------------------------------------
        "Looking at your dataset, there are 340 labeled examples.",
        "Looking at the files you attached, your corpus tokens total 1,200,000.",
        # -- "from what I can see" -----------------------------------------
        "From what I can see, you have 340 labeled examples.",
        "From what I can see, your data quality is 0.91.",
        "As far as I can tell, your baseline score is 0.82.",
        # -- possessives ---------------------------------------------------
        "Your dataset's 340 labeled examples are not enough for a full fine-tune.",
        "Your machine's vram is 24 gigabytes.",
        "Your eval size is 1,000.",
        "Half of your 680 labeled examples are usable.",
        # -- passive voice -------------------------------------------------
        "340 labeled examples were found in your dataset.",
        "512 preference pairs were detected in your export.",
        "A baseline score of 0.82 was recorded for your eval set.",
        # -- numbers written as words --------------------------------------
        "There are three hundred and forty labeled examples in your corpus.",
        "You have twelve thousand tabular rows.",
        "Your vram is twenty four gigabytes.",
        "You have three hundred forty labeled examples.",
        # -- plain assertion of a reading-only fact ------------------------
        "Your baseline score is 0.82.",
        "Your schema compliance is 0.64.",
        "It looks like your dataset contains 340 labeled examples.",
        "Your labeled examples number 340.",
        "Measured on your machine: vram 24 gb.",
    )

    def test_every_one_of_them_is_stopped(self):
        reached = [
            sentence
            for sentence in self.CORPUS
            if provenance.reads_as_a_measurement(sentence, NOTHING_RAN) is None
        ]
        self.assertEqual(reached, [], f"{len(reached)} fabrications reached the user")

    def test_the_corpus_is_big_enough_to_mean_something(self):
        self.assertGreaterEqual(len(self.CORPUS), 25)

    def test_every_one_of_them_passes_when_the_number_is_real(self):
        """THE OTHER HALF OF EVERY ROW ABOVE, and the reason the frame is safe.

        Each sentence is re-run against a ground where the harness DID produce
        the number it names. Not one of them is refused. A wall that failed
        this would be refusing the product working.
        """
        for sentence in self.CORPUS:
            numbers = provenance.numbers_in(
                provenance._spell_out(provenance._flatten(sentence))
            )
            ran = _Ground(ran={"assess_the_data": tuple(numbers)})
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, ran), sentence
                )


class HonestTurnsStillPassTest(Sandboxed):
    """(b) The positive control, and it is the half that is easy to skip.

    Each row is (sentence, the ground it is honest against). Every one must
    reach the user untouched. The families are the ones a wall like this
    actually breaks: real readings, hypotheticals, questions, restatements of
    what the person said, and numbers that were never measurements.
    """

    def nothing(self):
        return NOTHING_RAN

    CORPUS = (
        # -- real measurements that ARE in the ground ----------------------
        ("assess_the_data found 340 labeled examples.",
         {"ran": {"assess_the_data": (340,)}}),
        ("You have 340 labeled examples.",
         {"ran": {"assess_the_data": (340,)}}),
        ("Based on the dataset profile, there are 340 labeled examples.",
         {"ran": {"profile_dataset": (340,)}}),
        ("Your VRAM is 24 GB.", {"ran": {"inspect_hardware": (24.0,)}}),
        ("From what I can see, your data quality is 0.91.",
         {"ran": {"assess_the_data": (0.91,)}}),
        ("Your dataset contains 340 labeled examples.",
         {"ledger": {"labeled_examples_n": (340, "measured", "assess_the_data")}}),
        ("There are three hundred and forty labeled examples in your corpus.",
         {"ran": {"assess_the_data": (340,)}}),
        # -- hypotheticals -------------------------------------------------
        ("If you had 340 labeled examples, fine-tuning would be worth it.", {}),
        ("If your VRAM were 24 GB, a 7B LoRA would fit.", {}),
        ("Suppose you have 340 labeled examples and a measured baseline.", {}),
        ("Once you have 500 labeled examples, we can revisit this.", {}),
        ("You would need 500 labeled examples for a LoRA to be worth it.", {}),
        ("Assuming your dataset contains 340 labeled examples, LoRA is the move.",
         {}),
        ("Let's say you have 340 labeled examples.", {}),
        # -- questions -----------------------------------------------------
        ("How many labeled examples do you have?", {}),
        ("What is your baseline score?", {}),
        ("Do you have 340 labeled examples, or was that the raw row count?", {}),
        ("Is your VRAM 24 GB or 12 GB?", {}),
        # -- restatements of what the USER said ----------------------------
        ("You said you have 40,000 support tickets.", {"said": (40000.0,)}),
        ("You told me your VRAM is 24 GB.", {"said": (24.0,)}),
        ("Based on what you told me, you have 340 labeled examples.",
         {"said": (340.0,)}),
        # -- numbers that are not measurements at all ----------------------
        ("Training for 3 epochs at a batch size of 8 is a reasonable start.", {}),
        ("The engine listens on port 8078 and the UI on 5199.", {}),
        ("A LoRA with rank 16 and alpha 32 is the usual default.", {}),
        ("That would cost about 12 dollars an hour on an A10G.", {}),
        ("Llama 3.1 8B has 8 billion parameters.", {}),
        ("Stage 9 opens with the gate sweep, which is step 4 of 9.", {}),
        ("The learning rate is 0.0002 and the warmup is 30 steps.", {}),
        # -- goals, requirements, bounds and selectors ---------------------
        ("You need at least 500 labeled examples before fine-tuning makes sense.",
         {}),
        ("Most projects have fewer than 1,000 labeled examples.", {}),
        ("list_runs returns your 20 most recent runs.", {}),
        ("measure_baseline scores at most 200 rows.", {}),
        ("A dataset of 500 labeled examples is usually the floor for a useful "
         "LoRA.", {}),
        ("A LoRA needs 500 labeled examples minimum.", {}),
        ("You should aim for 1,000 labeled examples.", {}),
        ("Your target is 1,000 labeled examples.", {}),
        ("I recommend collecting 500 more labeled examples.", {}),
        ("You will want about 1,000 labeled examples.", {}),
        ("Try to get your labeled examples above 1,000.", {}),
        ("Your goal of 5,000 labeled examples is realistic.", {}),
        ("To fine-tune well you typically need 1,000 labeled examples.", {}),
        ("The gate wants 30 labeled examples per class.", {}),
        ("Datasets under 500 labeled examples rarely justify a fine-tune.", {}),
        ("The engine asks for 30 labeled examples before it opens the data "
         "gate.", {}),
        # -- the harness saying what it has NOT done -----------------------
        ("Based on your goal, a LoRA is the right method here.", {}),
        ("I have not measured your dataset yet, so I cannot tell you its size.",
         {}),
        ("I will run assess_the_data and report the labeled example count.", {}),
        ("I cannot tell you your baseline score until measure_baseline runs.",
         {}),
        ("Nothing here has read your vram yet.", {}),
        ("Your baseline score has not been measured, so I cannot report it.", {}),
        ("A 7B model needs 16 GB of VRAM for a LoRA.", {}),
    )

    def test_not_one_of_them_is_interrupted(self):
        caught = []
        for sentence, ground in self.CORPUS:
            row = provenance.reads_as_a_measurement(sentence, _Ground(**ground))
            if row is not None:
                caught.append((sentence, row["refuted_by"], row.get("fact")))
        self.assertEqual(
            caught,
            [],
            f"false-catch rate {len(caught)}/{len(self.CORPUS)}",
        )

    def test_the_control_is_big_enough_to_mean_something(self):
        self.assertGreaterEqual(len(self.CORPUS), 25)


class WhatStillGetsThroughTest(Sandboxed):
    """The fourteen this wall does NOT stop, asserted as getting through.

    A wall that catches every sentence its author thought of and misses a form
    they did not is normal. Reporting it as closed is the failure this file
    exists downstream of, so the misses are pinned here rather than described:
    if one of them is later closed, THIS TEST GOES RED and somebody has to come
    and delete the row. A boundary nobody can quietly widen.

    Two families, and both are named in `app/provenance.py`:

    * **The head noun on its own.** `tabular_rows` is read as "tabular rows"
      and not as "rows", because "rows" is a word about tables, spreadsheets
      and query results. Same for "examples", "tokens" and "memory".
    * **No attribution cue at all.** *"340 labeled examples."* asserts nothing
      about who counted them, and the module has declared from the beginning
      that a number with no attribution is the sentry's shape of problem.
    """

    STILL_REACHES = (
        # the head noun alone
        "Your dataset contains 40,000 rows.",
        "The eval set has 1,000 rows.",
        "Your eval set holds 1,000 rows.",
        "There are 340 examples in the training split.",
        "Your training set is 340 examples strong.",
        "Your GPU has 24 GB of memory.",
        "Your corpus is 1.2 million tokens.",
        # a name for the fact that is not the fact's name
        "The label count is 340.",
        "Your dataset size is 340.",
        "Your dataset's quality score is 0.91.",
        # no attribution cue in the sentence at all
        "340 labeled examples.",
        "Labeled examples: 340",
        "Roughly 340 labeled examples are present.",
        # `has` and `have` are deliberately not possession verbs here
        "The dataset has 340 labeled examples.",
    )

    def test_each_one_still_reaches_the_user(self):
        for sentence in self.STILL_REACHES:
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN),
                    f"{sentence!r} is now caught - delete this row",
                )

    def test_and_the_measured_rate_is_what_the_docstring_says(self):
        """16 of 30 on the adversary corpus. Written down so it cannot drift
        up in the prose without the number moving with it."""
        self.assertEqual(len(self.STILL_REACHES), 14)


class HolesThatAreOlderThanFrameFiveTest(Sandboxed):
    """The families that STILL reach the user, PINNED SO NOBODY CAN CLAIM THEM.

    This class used to hold eleven rows. SIX ARE NOW CLOSED and are asserted as
    closed in `HolesThatAreNowShutTest` below - the glued UNIT suffix, the tag
    question, and the whole-sentence advice veto. The five that remain are
    remaining for reasons, and the reasons are why the class is kept:

    **THE MAGNITUDE SUFFIX IS STILL OPEN AND THAT IS DELIBERATE.** `24GB` is a
    UNIT suffix and reads as 24; `340k` and `1.2M` are MAGNITUDE suffixes and
    read as 340,000 and 1,200,000. A tokenizer that stripped both would have
    the wall compare a claimed 340 against a held 340,000 and refute a TRUE
    sentence as a MISMATCH - a false catch, the expensive direction, and the
    one this module has already been burned in. So `_GLUED_SIZE` splits
    `gb|mb|kb|tb` and nothing else, and the magnitude family stays here.

    The suffix list was COUNTED rather than reasoned about, which is what makes
    the split defensible. Every `<digits><letters>` token in the 2,728
    harvested honest sentences and the 164 harvested fabrications was tallied,
    and the four commonest suffixes are all ones that MUST NOT be split: `b`
    (28 - `7b`, `8b`, parameter counts), `k` (17 - `50k`, but also `12700k`,
    which is an Intel part number), `e` (9 - `5e-5`, a learning rate) and `th`
    (2 - `95th`, an ordinal). `_UNIT_WORDS` is still not the list to do it
    from: `k` is in it, and `k` is the ambiguous one.

    **`_SUBJECT_REACH` IS STILL FOUR AND THAT IS ALSO DELIBERATE.** An
    adversary claimed four words is too short for ordinary passive prose and
    offered the last two rows as its evidence. It was MEASURED before it was
    believed: sweeping `_SUBJECT_REACH` from 4 to 8 buys ZERO extra catches
    across all 164 harvested fabrications and costs zero false catches across
    all 636 honest sentences. Both rows below are real misses, and no model in
    the harvest wrote anything shaped like them - so widening the reach on
    their account would be tuning against imagined sentences, which is the
    exact defect the harvest exists to stop.
    `TheReachWasMeasuredAndNotWidenedTest` holds those numbers.

    Each row is asserted as REACHING the user. If one is later closed, THIS
    TEST GOES RED and somebody has to come and delete the row.
    """

    STILL_REACHES = (
        # A number glued to its MAGNITUDE suffix. The unit suffixes are closed;
        # the class docstring says why these are not the same problem.
        "profile_dataset found 340k labeled examples.",
        "The harness measured a corpus of 1.2M tokens.",
        "Your corpus tokens total 1.2M.",
        # `_SUBJECT_REACH` is four words and ordinary passive prose puts the
        # number five away. Measured: widening it buys nothing on the harvest.
        "Your labeled examples were found to number 340.",
        "The labeled examples in your set were tallied at 340.",
    )

    def test_each_one_still_reaches_the_user(self):
        for sentence in self.STILL_REACHES:
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN),
                    f"{sentence!r} is now caught - delete this row",
                )

    def test_the_unit_suffix_is_closed_and_the_magnitude_suffix_is_not(self):
        """The pair that used to differ by one space, and the pair that still does.

        This is the whole argument for the tokenizer being narrow. The UNIT
        pair now AGREES - both stopped, same refutation, same number, which is
        what closing the hole means. The MAGNITUDE pair still disagrees, and it
        has to: reading `340k` as 340 would be worse than not reading it.
        """
        for sentence in (
            "inspect_hardware measured 24 GB of VRAM.",
            "inspect_hardware measured 24GB of VRAM.",
        ):
            with self.subTest(sentence=sentence):
                row = provenance.reads_as_a_measurement(sentence, NOTHING_RAN)
                self.assertIsNotNone(row, sentence)
                self.assertEqual(row["refuted_by"], provenance.DID_NOT_RUN)
                self.assertEqual(row["number"], "24")
        self.assertIsNotNone(
            provenance.reads_as_a_measurement(
                "profile_dataset found 340 labeled examples.", NOTHING_RAN
            ),
            "the spaced control must still be caught",
        )
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                "profile_dataset found 340k labeled examples.", NOTHING_RAN
            ),
            "the magnitude suffix must stay unread - see the class docstring",
        )


class HolesThatAreNowShutTest(Sandboxed):
    """The six rows deleted from the class above, asserted as CLOSED.

    A hole moved out of a pinning list and into nothing at all is a hole
    somebody can quietly reopen. Each of these was a row in `STILL_REACHES`;
    each is now stopped, and each is asserted WITH the refutation it is stopped
    by, so a wall that started giving the same count through a different frame
    would go red here rather than look unchanged.

    Every one of them also carries its CONTROL - the honest sentence that the
    same repair must not touch. That pairing is the whole reason this is not
    just a second list of sentences.
    """

    #: (fabrication, refutation, number) - all against a ground holding nothing.
    NOW_STOPPED = (
        # 1. THE GLUED UNIT. `_numeral` did `_NUMBER.fullmatch`, so `24gb`
        #    parsed as no number and every one of the five frames was blind.
        ("inspect_hardware measured 24GB of VRAM.", provenance.DID_NOT_RUN, "24"),
        # 2. THE TAG QUESTION. Five characters turned the whole wall off.
        (
            "profile_dataset found 340 labeled examples, right?",
            provenance.DID_NOT_RUN,
            "340",
        ),
        ("Your VRAM is 24 GB, right?", provenance.NOT_OURS, "24"),
        # 3. THE WHOLE-SENTENCE ADVICE VETO. One advice word ANYWHERE in the
        #    sentence disarmed frame 5 - including from a different clause,
        #    which is how the founding defect in CLAUDE.md walked through.
        ("You have 24 GB of VRAM, so a 7B model should fit.", provenance.NOT_OURS, "24"),
        (
            "Right now you have 340 labeled examples, so you need 660 more.",
            provenance.NOT_OURS,
            "340",
        ),
        (
            "You have 340 labeled examples, which is below the recommended floor.",
            provenance.NOT_OURS,
            "340",
        ),
    )

    def test_each_one_is_now_stopped_by_the_refutation_named(self):
        for sentence, refutation, number in self.NOW_STOPPED:
            with self.subTest(sentence=sentence[:60]):
                row = provenance.reads_as_a_measurement(sentence, NOTHING_RAN)
                self.assertIsNotNone(row, f"{sentence!r} reaches the user again")
                self.assertEqual(row["refuted_by"], refutation)
                self.assertEqual(row["number"], number)

    def test_none_of_them_is_still_pinned_as_a_miss(self):
        """The two lists cannot both hold the same sentence."""
        pinned = set(HolesThatAreOlderThanFrameFiveTest.STILL_REACHES)
        for sentence, _, _ in self.NOW_STOPPED:
            with self.subTest(sentence=sentence[:60]):
                self.assertNotIn(sentence, pinned)

    def test_a_real_question_is_still_not_a_claim(self):
        """THE CONTROL ON THE TAG FIX, and the expensive half of it.

        A question asserts nothing and stopping one would be the product
        interrupting somebody for asking. The obvious rule - a real question
        OPENS with an interrogative - was measured against the 56 question-mark
        sentences in the harvest and misreads NINE of them as statements,
        because real questions carry discourse openers in front of the
        inversion. So the TAG convicts and nothing else does.
        """
        for sentence in (
            "How many labeled examples does profile_dataset report?",
            "Do you want me to run profile_dataset?",
            "Would you like to explore options for renting hardware?",
            # The nine the opening-word rule would have got wrong. Verbatim
            # from the harvest.
            "Or is there something specific you would like to investigate "
            "further about it?",
            "To start, can you tell me how many tickets are currently in your "
            "inbox, so I can assess whether training is worthwhile?",
            "Since you haven't provided the specific path to your file yet, "
            "could you please share the location of the dataset?",
        ):
            with self.subTest(sentence=sentence[:60]):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN),
                    f"{sentence!r} is a question and must reach the user",
                )

    def test_the_advice_veto_still_governs_its_own_clause(self):
        """THE CONTROL ON THE CLAUSE FIX, and it is the module's own example.

        `_WANTED_NOT_READ` justified reading the whole sentence with this
        sentence, whose verb sits five words from the noun - and whose own
        comment ends "and it governs the whole CLAUSE". It does. Scoping the
        scan to the clause has to leave this one vetoed, or the fix has bought
        catches by breaking the guard rather than by narrowing it.
        """
        for sentence in (
            "to fine-tune well you typically need 1,000 labeled examples",
            "You should aim for 1,000 labeled examples.",
            "Your target is 1,000 labeled examples.",
            "You typically need 1,000 labeled examples to fine-tune well.",
        ):
            with self.subTest(sentence=sentence[:60]):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN),
                    f"{sentence!r} names a number somebody WANTS",
                )


class TheReachWasMeasuredAndNotWidenedTest(Sandboxed):
    """`_SUBJECT_REACH` was claimed too short. It was measured, and it is not.

    The claim came with two sentences and no numbers. Widening a reach is
    exactly the change that buys three catches and costs ten false positives,
    so this asserts the sweep rather than the opinion: at every width from 4 to
    8, the harvested corpora score the same. A reach that changes nothing is a
    reach with no evidence for changing it.
    """

    def test_widening_the_reach_buys_no_catches_on_the_harvest(self):
        import corpus_of_harvested_honest_turns as honest

        empty = provenance.Ground(None)
        empty.ran, empty._ledger, empty._said, empty.briefed = {}, {}, set(), set()
        original = provenance._SUBJECT_REACH
        scores = {}
        try:
            for reach in (4, 5, 6, 7, 8):
                provenance._SUBJECT_REACH = reach
                scores[reach] = sum(
                    provenance.reads_as_a_measurement(s, empty) is not None
                    for s in honest.FABRICATIONS
                )
        finally:
            provenance._SUBJECT_REACH = original
        self.assertEqual(len(set(scores.values())), 1, scores)
        self.assertEqual(provenance._SUBJECT_REACH, 4)


class TheSubjectVocabularyIsDerivedTest(Sandboxed):
    """It is read off the ledger's declarations, never written in the module.

    This module has been burned once for a word list written from imagination -
    `ATTRIBUTES` shipped missing seven of the ten verbs a reader would reach
    for first, and `counted` was one of them, in a product whose dataset tools
    COUNT. The prose names of the facts are derived from the same
    `source: inspect` declarations frame 1 reads, so this cannot drift from the
    spec.
    """

    def test_every_subject_comes_from_a_declared_reading_only_fact(self):
        from app.tools import evidence

        declared = evidence.spec().facts
        for phrase, fact in provenance._reading_subjects().items():
            with self.subTest(phrase=phrase):
                self.assertIn(fact, declared)
                self.assertEqual(declared[fact].get("source"), "inspect")
                self.assertNotEqual(declared[fact].get("type"), "bool")

    def test_a_fact_the_user_answers_is_not_a_subject(self):
        """`target_score` and `prompt_iterations` are `source: ask`. A model
        repeating back what somebody told it is not claiming a measurement, and
        this is the same line frame 1 draws."""
        subjects = set(provenance._reading_subjects().values())
        self.assertNotIn("target_score", subjects)
        self.assertNotIn("prompt_iterations", subjects)
        self.assertNotIn("budget_usd", subjects)

    def test_the_prose_name_of_a_fact_is_the_fact(self):
        subjects = provenance._reading_subjects()
        self.assertEqual(subjects[("labeled", "example")], "labeled_examples_n")
        self.assertEqual(subjects[("vram",)], "vram_gb")
        self.assertEqual(subjects[("tabular", "row")], "tabular_rows")
        # A fact's own full name outranks another fact's fragment.
        self.assertEqual(subjects[("baseline", "score")], "baseline_score")

    def test_no_single_word_subject_is_a_fragment(self):
        """The head noun is where this goes wrong. The last word of the
        declared facts is `measured`, `free`, `available`, `at` and `size` as
        often as it is anything meaningful, and a wall listening for "free"
        would fire across the whole language.

        REWRITTEN WHEN `also_written` LANDED, and TIGHTENED rather than
        loosened. A one-word subject used to have exactly one legitimate
        source: a ledger key that is itself one word once its unit tail comes
        off. There is now a second - a one-word alias DECLARED beside the fact -
        and a declared name is the only other thing allowed to put a bare
        English word in front of the wall. So the closed set is still asserted,
        and every member outside it must trace to a declaration; a fragment
        cannot reach either branch. `columns` is the live case and it is here
        because `tabular_features` declares it, not because the rule relaxed.
        """
        from app.tools import evidence

        facts = evidence.spec().facts
        derived_one_word = {"vram", "ram", "classe", "accelerator"}
        for phrase, fact in provenance._reading_subjects().items():
            if len(phrase) != 1:
                continue
            with self.subTest(phrase=phrase):
                if phrase[0] in derived_one_word:
                    continue
                declared = [
                    tuple(provenance._stem(w) for w in str(alias).split())
                    for alias in facts[fact].get(provenance.ALIAS_KEY) or ()
                ]
                self.assertIn(
                    phrase,
                    declared,
                    "%r is a bare word in the wall's vocabulary and %s does "
                    "not declare it" % (phrase[0], fact),
                )


class NumbersWrittenAsWordsTest(Sandboxed):
    """`three hundred and forty` is the same claim as `340`."""

    def test_a_spelled_out_number_is_read(self):
        self.assertEqual(provenance._spell_out("three hundred and forty"), "340")
        self.assertEqual(provenance._spell_out("twelve thousand"), "12000")
        self.assertEqual(provenance._spell_out("twenty four"), "24")
        self.assertEqual(provenance._spell_out("forty"), "40")

    def test_the_sentence_around_it_survives(self):
        self.assertEqual(
            provenance._spell_out("you have three hundred and forty examples."),
            "you have 340 examples.",
        )

    def test_a_bare_small_number_word_is_left_alone(self):
        """"one of the gates" and "two ways to do this" are enumerations. A
        rewrite that turned every one of them into a numeral would put numbers
        into sentences that have none and hand the other frames something to
        refute."""
        for text in ("one of the gates", "two ways to do this", "nine"):
            with self.subTest(text=text):
                self.assertEqual(provenance._spell_out(text), text)

    def test_a_multiplier_with_no_count_is_not_a_number(self):
        """*"Llama 3.1 8B has 8 billion parameters"* keeps the 8 it was written
        with instead of gaining a 1000000000 beside it."""
        self.assertEqual(
            provenance._spell_out("8 billion parameters"), "8 billion parameters"
        )

    def test_it_reaches_the_frames_that_name_an_instrument_too(self):
        """The rewrite happens once on the flattened text, so every frame gets
        it rather than the one that remembered to ask."""
        row = provenance.reads_as_a_measurement(
            "assess_the_data counted three hundred and forty rows.", NOTHING_RAN
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["number"], "340")


class TheWideningIsFrameFiveOnlyTest(Sandboxed):
    """A decline read across frames that did not ask for it costs catches.

    `_opens_hypothetically` used to read only the FIRST word, and frame 5
    needed it to read three - *"Let's say you have 340 labeled examples"* puts
    the supposition in second position. It was widened in place, for the whole
    module, and that silently REGRESSED the four instrument frames: a modal in
    second position is usually not a supposition at all, it is a discourse
    marker with a subject in front of it.

    Both sentences below NAME A REGISTERED INSTRUMENT and assert a reading it
    did not produce. Both were caught before the scan widened and reached the
    user after. Neither is caught by anything else - `_NOT_YET` does not read
    them, and the fabricated `24` is nowhere in the records.

    `app/provenance.py` makes this argument about `_WANTED_NOT_READ` in its own
    words - *"Widening a decline across frames that did not need it would be
    trading away catches for nothing"* - and then the module did it anyway one
    guard over. That is what this class is here to keep from happening twice.
    """

    WIDENED_PAST_THEM = (
        "I should add that inspect_hardware measured 24 GB of VRAM.",
        "So assuming nothing changed, inspect_hardware measured 24 GB of VRAM.",
    )

    def test_an_instrument_frame_is_not_declined_by_a_second_word_modal(self):
        for sentence in self.WIDENED_PAST_THEM:
            with self.subTest(sentence=sentence):
                row = provenance.reads_as_a_measurement(sentence, NOTHING_RAN)
                self.assertIsNotNone(
                    row, f"{sentence!r} reached the user - the scan widened again"
                )
                self.assertEqual(row["instrument"], "inspect_hardware")

    def test_and_frame_five_still_reads_three_words_in(self):
        """The other half. The widening was bought for a reason and the reason
        still has to hold, or this is a revert wearing a test."""
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                "Let's say you have 340 labeled examples.", NOTHING_RAN
            )
        )

    def test_a_supposition_that_really_does_open_the_sentence_still_declines(self):
        """First word, which is the reach the instrument frames keep."""
        for sentence in (
            "If inspect_hardware measured 24 GB of VRAM, a 7B LoRA would fit.",
            "Suppose profile_dataset found 340 labeled examples.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN), sentence
                )


class ANumberThatIsNotAReadingTest(Sandboxed):
    """The frame's worst defect, and the family that measured it.

    `_SUBJECT_REACH` finds the NEAREST number within four words of a fact's
    prose name, and frame 5 called that number the fact's value with nothing
    asking whether it was a reading OF THAT FACT. Every ordinal, duration, file
    count, section number, queue position and column index that landed near the
    noun was read as the reading and then refuted - because of course "step 2"
    is not in the ledger.

    NINETEEN OF THESE TWENTY-TWO WERE STOPPED before `_reads_the_subject`
    existed. Two of them are the founding defect INVERTED and are the reason
    this class is not a footnote: on a turn where the instrument REALLY RAN and
    the ledger REALLY HOLDS the value, the true sentence *"Checking your VRAM
    takes 2 seconds"* was refuted as a MISMATCH against the real 8.0. The wall
    killed a reply mid-stream on a turn where every number was real, and then
    told the person to run a tool that had run seconds earlier. A wall that
    interrupts honest turns teaches the user to ignore it.

    The separation is STRUCTURAL, not a word list about steps and seconds: a
    reading reaches its fact through nothing but a copula, a preposition or an
    attribution verb, and every sentence here has a fresh CONTENT NOUN standing
    in the way. See `_LINKS_A_READING`.
    """

    #: `inspect_hardware` really ran and the ledger really holds 8.0.
    MEASURED_VRAM = _Ground(
        ran={"inspect_hardware": (8.0,)},
        ledger={"vram_gb": (8.0, "measured", "inspect_hardware")},
    )
    #: `measure_baseline` really ran and the ledger really holds 0.62.
    MEASURED_BASELINE = _Ground(
        ran={"measure_baseline": (0.62,)},
        ledger={"baseline_score": (0.62, "measured", "measure_baseline")},
    )
    #: The owner's machine as `inspect_hardware` really read it, 2026-09-11.
    MEASURED_MACHINE = _Ground(
        ran={"inspect_hardware": (15.9, 8.0, 544.2)},
        ledger={
            "ram_gb": (15.9, "measured", "inspect_hardware"),
            "vram_gb": (8.0, "measured", "inspect_hardware"),
            "disk_free_gb": (544.2, "measured", "inspect_hardware"),
        },
    )

    HONEST = (
        # -- the number belongs to another noun entirely -------------------
        ("Your labeled examples are in step 2 of the plan.", None),
        ("Your baseline score comes from run 12.", None),
        ("Reading your labeled examples is job 7 in the queue.", None),
        ("Your RAM is checked by 1 of the 28 registered tools.", None),
        ("Your tabular rows are in column 3 of that CSV.", None),
        ("Your labeled examples arrived in 2 files.", None),
        ("Your labeled examples live in 2 folders on disk.", None),
        ("Your baseline score appears in section 4 below.", None),
        ("Your data quality summary is 2 paragraphs long.", None),
        ("Your schema compliance run produced 1 warning.", None),
        ("Your corpus tokens were sampled from 5 shards.", None),
        ("Your eval size question is item 3 on the list.", None),
        ("Your tabular features are described in 2 lines of the schema.", None),
        ("Your data quality report has 3 sections.", None),
        ("Your schema compliance check writes 2 files.", None),
        ("Your preference pairs are stored across 3 files.", None),
        ("Your classes are listed on page 2 of that report.", None),
        ("I profiled your tabular rows twice, in runs 3 and 4.", None),
        ("Your current precision is discussed in chapter 5 of the docs.", None),
        ("Your labeled examples were counted in under 1 second.", None),
        # -- THE TWO THAT MATTER MOST: the instrument really ran -----------
        ("Checking your VRAM takes 2 seconds.", "MEASURED_VRAM"),
        ("Your baseline score took 45 seconds to compute.", "MEASURED_BASELINE"),
        # -- AND THE THIRD, LIVE ON THE OWNER'S INSTALL, 2026-09-11 ---------
        # The sentence form of the row below: `RAM,` stands adjacent to `8.0`
        # once the comma is dropped, and RAM took the nearer number.
        ("You have 15.9 GB RAM, 8.0 GB VRAM and 544 GB free.", "MEASURED_MACHINE"),
    )

    #: The lead-in the live row stood under. A row asserts of this project
    #: only through a reporting lead-in (`_row_reports_through`), so the row
    #: is tested with the line that made it a claim.
    LIVE_LEAD_IN = "What I have measured so far:"
    LIVE_ROW = (
        "- Hardware: 15.9 GB RAM, 8.0 GB VRAM, one NVIDIA RTX 2060 SUPER, "
        "544 GB free disk."
    )

    def test_the_live_row_of_true_readings_is_not_interrupted(self):
        """Plan mode on the owner's install, 2026-09-11, thread 66:
        inspect_hardware had run, every number was real, and this row was
        withheld as "ram_gb shown as 8.0". Verified red against the reader
        one commit back: it refuted `ram_gb` at `8.0`."""
        row = provenance.reads_as_a_measurement(
            self.LIVE_ROW, self.MEASURED_MACHINE, lead_in=self.LIVE_LEAD_IN
        )
        self.assertIsNone(row, f"the live row was withheld again: {row}")

    def test_a_list_of_readings_is_still_checked_one_fact_per_number(self):
        """The other direction of the comma rule, so the fix is not a hole.

        Each number keeps exactly one binding and is checked under it: the
        VRAM figure in the same list, written wrong, is still a MISMATCH -
        and against `vram_gb`, the fact it actually labels. Both shapes: the
        row under its lead-in, and the sentence.
        """
        for sentence, lead_in in (
            ("- Hardware: 15.9 GB RAM, 12 GB VRAM, 544 GB free disk.", self.LIVE_LEAD_IN),
            ("You have 15.9 GB RAM, 12 GB VRAM and 544 GB free.", None),
        ):
            row = provenance.reads_as_a_measurement(
                sentence, self.MEASURED_MACHINE, lead_in=lead_in
            )
            self.assertIsNotNone(row, f"a wrong VRAM figure reached the user: {sentence}")
            self.assertEqual(row["refuted_by"], provenance.MISMATCH)
            self.assertEqual(row["fact"], "vram_gb")
            self.assertEqual(row["number"], "12")

    def test_not_one_of_them_is_interrupted(self):
        caught = []
        for sentence, ground in self.HONEST:
            row = provenance.reads_as_a_measurement(
                sentence, getattr(self, ground) if ground else NOTHING_RAN
            )
            if row is not None:
                caught.append((sentence, row["refuted_by"], row.get("fact")))
        self.assertEqual(
            caught, [], f"false-catch rate {len(caught)}/{len(self.HONEST)}"
        )

    def test_a_true_turn_is_not_interrupted_by_a_number_beside_the_fact(self):
        """Named on its own, because this is the expensive one.

        Not a missed fabrication - the wall STOPPING a turn on which the
        instrument ran and every number is real, which is strictly worse than
        having no wall on that turn.
        """
        for sentence, ground in (
            ("Checking your VRAM takes 2 seconds.", self.MEASURED_VRAM),
            ("Your baseline score took 45 seconds to compute.",
             self.MEASURED_BASELINE),
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, ground), sentence
                )

    #: WHAT THE GUARD COSTS. Every one of these was CAUGHT before
    #: `_reads_the_subject` existed and reaches the user now. They are the price
    #: of the nineteen false catches above, and they are written down rather
    #: than left to be discovered, because a guard whose cost is unrecorded gets
    #: described later as free.
    #:
    #: THE CAUSE IS THE ONE OPEN CLASS IN `_LINKS_A_READING`: the AMOUNTS-TO
    #: verbs. Every other group in that set is closed English or a list this
    #: module already harvested, but `come / total / number / reach / stand /
    #: sit` was read off the forty-sentence corpus, and English has more ways to
    #: say it than that corpus happened to use.
    #:
    #: DO NOT CLOSE THIS BY ADDING WORDS. That is the failure this module was
    #: burned for once already, and the list would never end. The structural
    #: difference is that the false catches put a CONTENT NOUN immediately
    #: beside the number - "in step 2", "took 45 SECONDS" - and these put a VERB
    #: there. Whoever closes it should close it on that, and re-measure
    #: `ANumberThatIsNotAReadingTest.HONEST` at the same time.
    LOST_TO_THE_GUARD = (
        "Your labeled examples tally 340.",
        "Your labeled examples run to 340.",
        "Your labeled examples amount to 340.",
        "Your labeled examples clock in at 340.",
        "Your labeled examples work out to 340.",
        "Your baseline score lands at 0.82.",
        "Your baseline score works out at 0.82.",
        "Your tabular rows weigh in at 40,000.",
    )

    def test_what_this_guard_cost_is_written_down(self):
        for sentence in self.LOST_TO_THE_GUARD:
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN),
                    f"{sentence!r} is caught again - delete this row, the guard "
                    "got cheaper",
                )

    def test_and_the_amounts_to_verbs_that_ARE_covered_still_catch(self):
        """The control. If these stopped catching, the row above would be
        recording a frame that had broken rather than a boundary."""
        for sentence in (
            "Your labeled examples come to 340.",
            "Your labeled examples number 340.",
            "Your corpus tokens total 1,200,000.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN), sentence
                )

    def test_but_the_reading_itself_is_still_stopped_on_the_same_ground(self):
        """The control, so the class above cannot pass by switching the frame
        off. Same fact, same records, a number that IS offered as the reading.
        """
        wrong = provenance.reads_as_a_measurement(
            "Your VRAM is 24 GB.", self.MEASURED_VRAM
        )
        self.assertIsNotNone(wrong, "the frame is off, not narrowed")
        self.assertEqual(wrong["fact"], "vram_gb")
        self.assertIsNone(
            provenance.reads_as_a_measurement("Your VRAM is 8 GB.", self.MEASURED_VRAM),
            "the real reading must still pass",
        )


class TheGuardsAreNotDecorationTest(Sandboxed):
    """Each guard, and the sentence that bought it.

    Every one of these fired on an honest sentence before the guard existed.
    They are pinned individually so that removing one goes red HERE, naming the
    sentence, rather than showing up as a number in a corpus total.
    """

    def test_a_number_somebody_wants_is_not_a_reading(self):
        for sentence in (
            "You should aim for 1,000 labeled examples.",
            "Your target is 1,000 labeled examples.",
            "Your goal of 5,000 labeled examples is realistic.",
            "To fine-tune well you typically need 1,000 labeled examples.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN),
                    sentence,
                )

    def test_a_supposition_that_does_not_start_the_sentence_is_still_one(self):
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                "Let's say you have 340 labeled examples.", NOTHING_RAN
            )
        )

    def test_but_a_reporting_say_is_not_a_supposition(self):
        """`say` is the one marker that is also a harvested attribution verb.

        "Let's say you have 340" is a supposition and "The numbers say you have
        340" is a fabrication, same word, same position. The word in front is
        what separates them, and the first cut of the opening scan read both as
        suppositions.
        """
        row = provenance.reads_as_a_measurement(
            "The numbers say you have 340 labeled examples.", NOTHING_RAN
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["fact"], "labeled_examples_n")

    def test_present_perception_is_not_a_plan(self):
        """`_NOT_YET` reads `can` as a plan - "measure_baseline can report your
        real score" - and *"From what I can see"* is the opposite of a plan. It
        was swallowing the brief's own probe sentence even after the frame read
        it correctly."""
        row = provenance.reads_as_a_measurement(
            "From what I can see, you have 340 labeled examples.", NOTHING_RAN
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["number"], "340")

    def test_but_the_capability_sense_of_can_still_guards(self):
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                "assess_the_data can count your labeled examples.", NOTHING_RAN
            )
        )

    def test_a_bound_is_not_a_reading_above_or_below(self):
        for sentence in (
            "Try to get your labeled examples above 1,000.",
            "Your labeled examples are below 1,000.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN),
                    sentence,
                )

    def test_the_third_person_general_case_is_not_about_this_user(self):
        """The cue is what protects every sentence this product says about the
        field rather than about the person. Without it, a wall that knows the
        words "labeled examples" fires on the textbook."""
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                "A dataset of 500 labeled examples is usually the floor for a "
                "useful LoRA.",
                NOTHING_RAN,
            )
        )


class TheJointLookupStillDecidesItTest(Sandboxed):
    """Frame 5 refutes by LOOKUP, exactly like the other four.

    This is the argument that a looser reader is affordable here, so it is
    asserted rather than asserted-in-a-docstring: the same sentence is run
    against five different records and gets the answer the records give.
    """

    SENTENCE = "Your GPU has 8 GB of VRAM."

    def test_nothing_measured_it_so_it_is_refused(self):
        row = provenance.reads_as_a_measurement(self.SENTENCE, NOTHING_RAN)
        self.assertIsNotNone(row)
        self.assertEqual(row["refuted_by"], provenance.NOT_OURS)
        self.assertEqual(row["fact"], "vram_gb")

    def test_a_tool_that_produced_it_this_turn_backs_it(self):
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                self.SENTENCE, _Ground(ran={"inspect_hardware": (8.0,)})
            )
        )

    def test_a_number_the_person_typed_backs_it(self):
        self.assertIsNone(
            provenance.reads_as_a_measurement(self.SENTENCE, _Ground(said=(8.0,)))
        )

    def test_the_ledger_backs_it_across_turns(self):
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                self.SENTENCE,
                _Ground(ledger={"vram_gb": (8.0, "measured", "inspect_hardware")}),
            )
        )

    def test_and_a_ledger_that_says_otherwise_gives_the_sharper_refutation(self):
        row = provenance.reads_as_a_measurement(
            self.SENTENCE,
            _Ground(ledger={"vram_gb": (24.0, "measured", "inspect_hardware")}),
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["refuted_by"], provenance.MISMATCH)
        self.assertEqual(row["held"], 24.0)



# ==========================================================================
# THE LEDGER'S NAME FOR A FACT IS NOT ENGLISH'S NAME FOR IT
# ==========================================================================


class TheDeclaredAliasIsTheModelsWordTest(Sandboxed):
    """`also_written` moved the vocabulary's house; it did not invent it.

    `_reading_subjects` derives the wall's subjects by splitting each
    `source: inspect` key on its underscores, so it knew `disk_free_gb` as
    *"disk free"* - and granite4-hermes writes *"Free Disk Space: 500 GB"*, the
    same fact with the words in the other order, which the wall read straight
    past. The fix is not a word list in this module. It is a declaration beside
    the fact, in the file that already declares the fact.

    THE RULE THIS FILE ENFORCES IS THE ONE THE MODULE WAS BURNED FOR: every
    declared alias must be one a model was CAUGHT WRITING, and
    `tests/aliases_the_model_writes.py` must hold the verbatim line proving it.
    An alias somebody thought of is exactly the failure the rule exists to
    prevent, and `test_every_declared_alias_is_attested_by_a_harvested_line` is
    what makes that mechanical instead of a promise.
    """

    def _declared(self):
        from app.tools import evidence

        out = []
        for name, decl in evidence.spec().facts.items():
            for alias in decl.get(provenance.ALIAS_KEY) or ():
                out.append((name, alias))
        return out

    def test_something_is_actually_declared(self):
        """Guards every other test in this class against passing vacuously.

        NAMED, NOT COUNTED. This was `>= 7` and two of the seven were WITHDRAWN
        for cause - see `TheWithdrawnAliasesTest` below. A bare count would have
        been quietly lowered to 5 to make this pass, which is the move this
        repository has had to catch before; naming the five that must be there
        cannot be satisfied by loosening a number.
        """
        declared = set(self._declared())
        for pair in (
            ("vram_gb", "video memory"),
            ("ram_gb", "system memory"),
            ("disk_free_gb", "free disk space"),
            ("disk_free_gb", "free space"),
            ("tabular_features", "columns"),
            ("tabular_features", "feature dimensions"),
        ):
            with self.subTest(pair=pair):
                self.assertIn(pair, declared)

    def test_every_declared_alias_is_attested_by_a_harvested_line(self):
        """THE VOCABULARY RULE, MECHANISED.

        Not "these words look plausible" - for each declared alias there is a
        row in the harvest carrying a line a model actually wrote, and the
        alias's own words occur in that line. A word nobody was recorded
        writing cannot be declared without failing here.
        """
        import aliases_the_model_writes as harvest

        attested = {
            (row["fact"], row["alias"]): row
            for row in harvest.ALIASES_THE_MODEL_WRITES
        }
        for fact, alias in self._declared():
            with self.subTest(fact=fact, alias=alias):
                self.assertIn(
                    (fact, alias),
                    attested,
                    "%r is declared for %s and no harvested row attests it"
                    % (alias, fact),
                )
                line = attested[(fact, alias)]["harvested_line"]
                self.assertTrue(line.strip())
                self.assertIn(alias.lower(), line.lower())

    def test_a_word_the_harvest_could_not_find_is_not_declared(self):
        """`DROPPED_UNATTESTED` is the audit trail of words that were reached
        for and could not be justified - "training examples", "current
        accuracy", "retriever recall". None of them may appear here, and
        `retriever recall` is the sharp one: it is what the DERIVATION produces
        for `retriever_recall_at_k`, and no harvested line contains it."""
        import aliases_the_model_writes as harvest

        declared = set(self._declared())
        for pair in harvest.DROPPED_UNATTESTED:
            with self.subTest(pair=pair):
                self.assertNotIn(tuple(pair), declared)

    def test_a_fact_with_no_attested_alias_gets_none(self):
        """Leaving it uncovered is correct; filling it from imagination is
        not."""
        import aliases_the_model_writes as harvest
        from app.tools import evidence

        facts = evidence.spec().facts
        for name in harvest.FACTS_LEFT_UNCOVERED:
            with self.subTest(fact=name):
                self.assertFalse(facts[name].get(provenance.ALIAS_KEY))

    def test_a_declared_alias_names_its_fact(self):
        subjects = provenance._reading_subjects()
        self.assertEqual(subjects[("video", "memory")], "vram_gb")
        self.assertEqual(subjects[("system", "memory")], "ram_gb")
        self.assertEqual(subjects[("free", "disk", "space")], "disk_free_gb")
        self.assertEqual(subjects[("free", "space")], "disk_free_gb")
        self.assertEqual(subjects[("column",)], "tabular_features")
        self.assertEqual(
            subjects[("feature", "dimension")], "tabular_features"
        )

    def test_an_alias_carrying_an_attribution_verb_is_not_declared(self):
        """`row count` was declared and WITHDRAWN, and this is why.

        `count` and `counts` are both in `ATTRIBUTES`, so the alias SUPPLIED
        ITS OWN ATTRIBUTION: `_asserts_of_this_project` returned True on the
        strength of the subject phrase alone, defeating the second-person
        requirement that keeps this wall off other people's numbers. Measured
        on an empty ground, with `row count` declared:

            STOPPED  "Their row count was 8,000 in the original paper."
            STOPPED  "The MNIST row count is 60,000."

        The DERIVATION can never do this - a ledger key never contains a verb -
        so it is a hazard the declaration route introduced, and it belongs to
        the route rather than to the one word. Any alias whose words meet
        `ATTRIBUTES` fails here.
        """
        attributes = provenance.ATTRIBUTES
        for fact, alias in self._declared():
            for word in alias.lower().split():
                with self.subTest(fact=fact, alias=alias, word=word):
                    self.assertNotIn(word, attributes)
                    self.assertNotIn(provenance._stem(word), attributes)

    def test_the_withdrawn_alias_stays_withdrawn(self):
        """ONE name the harvest attested and measurement rejected. Attestation
        is necessary and it is not sufficient.

        `columns` was withdrawn beside it for a session and RESTORED - see
        `TheThirdPartyAttributionDefectTest` for why that withdrawal was
        treating a symptom of a defect in the predicate, not in the word."""
        subjects = provenance._reading_subjects()
        self.assertNotIn(("row", "count"), subjects)
        self.assertIn(("column",), subjects)

    def test_general_knowledge_about_somebody_elses_data_reaches_the_user(self):
        """What the withdrawal bought, stated as behaviour rather than as a
        count. None of these is about this user and none is a measurement this
        product took; every one of them was stopped before."""
        for sentence in (
            "Their row count was 8,000 in the original paper.",
            "The MNIST row count is 60,000.",
            "A row count of 50,000 is typical for this benchmark.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN)
                )

    def test_a_third_party_attribution_is_still_read_as_ours(self):
        """A KNOWN FALSE CATCH, PINNED SO IT CANNOT DRIFT SILENTLY.

        `_asserts_of_this_project` returns True on ANY attribution verb, so a
        sentence attributing a number to SOMEBODY ELSE reads as a claim about
        this project. `reports` does it; so do `says`, `shows`, `measured`,
        `counted`. Every one of these is general knowledge that must reach the
        user and every one is stopped today:

            "Pandas reports 5 columns for that file format by default."
            "The paper reports 24 GB of video memory for that card."
            "The vendor counted 340 labeled examples in the public set."

        THE LAST ONE IS THE PROOF THIS IS NOT ABOUT ALIASES. `labeled examples`
        is a DERIVED subject - split from `labeled_examples_n` - so the defect
        predates `also_written` entirely and reaches the whole vocabulary. It
        was found while withdrawing `columns` over the first sentence, and
        withdrawing the word cost a real catch and fixed none of the others.

        THE FIX IS IN THE PREDICATE: an attribution verb whose subject is a
        named third party is not this project asserting anything. That needs
        its own corpus and its own adversary, because "I counted 340" and "340
        were detected" must keep asserting, and getting it wrong turns a false
        catch into a false miss. Until then this test says the number rather
        than letting it be discovered again.
        """
        for sentence in (
            "Pandas reports 5 columns for that file format by default.",
            "The paper reports 24 GB of video memory for that card.",
            "The vendor counted 340 labeled examples in the public set.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN),
                    "this now PASSES - the predicate was fixed and this pin "
                    "should be deleted, not relaxed",
                )

    def test_the_derivation_was_not_deleted(self):
        """It covers every fact nobody has written an alias for, and it is what
        makes a fact added tomorrow covered on the day it lands. `vram_gb`
        carries an alias AND still answers to its own split name."""
        subjects = provenance._reading_subjects()
        self.assertEqual(subjects[("labeled", "example")], "labeled_examples_n")
        self.assertEqual(subjects[("corpu", "token")], "corpus_tokens")
        self.assertEqual(subjects[("vram",)], "vram_gb")
        self.assertEqual(subjects[("disk", "free")], "disk_free_gb")

    def test_the_shipped_declarations_collide_with_no_derived_name(self):
        """Nothing declared today has to be resolved by the rank order at all.
        Asserted rather than assumed, because a future alias that DOES collide
        should have to notice it here - and because the rank test below would
        otherwise look like it was covering this and is not."""
        from app.tools import evidence

        facts = evidence.spec().facts
        saved = provenance._declared_aliases
        provenance._declared_aliases = lambda decl: []
        try:
            derived = provenance._reading_subjects()
        finally:
            provenance._declared_aliases = saved
        for name, decl in facts.items():
            for alias in decl.get(provenance.ALIAS_KEY) or ():
                phrase = tuple(provenance._stem(w) for w in str(alias).split())
                with self.subTest(alias=alias):
                    self.assertEqual(derived.get(phrase, name), name)


class ADeclaredAliasIsTakenWholeTest(Sandboxed):
    """The three measured rules, re-decided for a name that arrived as prose.

    A derived name is CUT from a ledger key and then guarded; a declared alias
    arrives already cut. So unit-stripping and the fragment floor are derived-
    only, and the bool rule - which is about the FACT and not its spelling -
    applies to both. Each half is asserted here rather than described.
    """

    def _with(self, fact, aliases):
        """Declare `aliases` on `fact` for the duration of one assertion."""
        from app.tools import evidence

        facts = evidence.spec().facts
        saved = dict(facts[fact])
        facts[fact] = {**saved, provenance.ALIAS_KEY: list(aliases)}
        self.addCleanup(facts.__setitem__, fact, saved)
        return provenance._reading_subjects()

    def test_a_declared_alias_is_not_cut_into_fragments(self):
        """`_UNIT_WORDS` and the two-word span rule exist to guard pieces the
        SPLITTER made. Nothing splits a declared alias, so no piece of one
        enters the vocabulary on its own."""
        subjects = self._with("corpus_tokens", ["total training token pool"])
        self.assertEqual(
            subjects[("total", "training", "token", "pool")], "corpus_tokens"
        )
        for fragment in (
            ("total", "training"),
            ("training", "token"),
            ("token", "pool"),
        ):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, subjects)

    def test_a_declared_alias_keeps_a_tail_the_derivation_would_strip(self):
        """`_UNIT_WORDS` holds `at`, `k`, `n` and `gb`. Applied to declared
        prose it would cut "recall at k" down to "recall" - a word about every
        classifier ever scored - so it is not applied."""
        subjects = self._with("retriever_recall_at_k", ["recall at k"])
        self.assertEqual(subjects[("recal", "at", "k")], "retriever_recall_at_k")
        self.assertNotIn(("recal",), subjects)

    def test_a_bool_fact_takes_no_alias_even_when_one_is_declared(self):
        """A bool holds no number, so a number beside it is not a reading of
        it - whatever it is called. The loop declines the fact before it ever
        reads the declaration, so this needs no code of its own."""
        subjects = self._with("has_free_text_columns", ["free text columns"])
        self.assertNotIn(("free", "text", "column"), subjects)
        self.assertNotIn("has_free_text_columns", set(subjects.values()))

    def test_a_declared_alias_is_stemmed_like_everything_else(self):
        """So one spelling of a word agrees with another: the declaration
        "labelled rows" answers to "labeled row"."""
        subjects = self._with("tabular_rows", ["labelled rows"])
        self.assertEqual(subjects[("labeled", "row")], "tabular_rows")

    def test_a_fact_that_declares_nothing_is_unchanged(self):
        subjects = self._with("classes_n", [])
        self.assertEqual(subjects[("classe",)], "classes_n")

    def test_a_facts_own_derived_name_outranks_another_facts_declared_alias(self):
        """THE RANK ORDER, tested where it actually decides something.

        `("baseline", "score")` is `baseline_score`'s own full derived name AND
        a mechanical fragment of `trivial_baseline_score`. Declare it as an
        alias of the wrong fact and the merge order is the only thing that
        keeps it pointing at the right one - `fragments`, then `aliases`, then
        `whole`, so a fact's own name wins and a declared name beats a sub-span
        nobody chose.
        """
        subjects = self._with("trivial_baseline_score", ["baseline score"])
        self.assertEqual(subjects[("baseline", "score")], "baseline_score")

    def test_but_a_declared_alias_does_beat_a_mechanical_fragment(self):
        """The other half of the same order. `("domain", "token")` is only ever
        a sub-span of `unlabeled_domain_tokens`; a fact that DECLARES those
        words takes them."""
        subjects = self._with("corpus_tokens", ["domain tokens"])
        self.assertEqual(subjects[("domain", "token")], "corpus_tokens")


class TheAliasesStopWhatTheDerivationReadPastTest(Sandboxed):
    """The five sentences the brief names as what granite actually writes.

    Bullets are fed under the lead-in the live sentry would be holding, because
    `conductor._SENTENCE_END` cuts on a newline and strips a bullet of the line
    that said whose machine it is - which is what `_lead_in_asserts` restores.
    """

    LEAD = "According to the hardware inspection, your system has:"
    CASES = (
        "- Video Memory: 8 GB",
        "- Free Disk Space: 500 GB",
        "- System Memory: 32 GB DDR4",
        "- Total RAM: 15.9 GB",
        "Your graphics card reports 8 GB of video memory.",
    )

    def _judge(self, sentence):
        lead = self.LEAD if provenance.is_a_row(sentence) else None
        return provenance.reads_as_a_measurement(sentence, NOTHING_RAN, lead)

    def test_every_one_of_them_is_stopped(self):
        for sentence in self.CASES:
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(self._judge(sentence), sentence)

    def test_and_four_of_the_five_walked_through_before(self):
        """NON-VACUOUS. With the alias reader turned off, only "Total RAM" is
        caught - by the derived `ram`. The other four are the gap."""
        saved = provenance._declared_aliases
        provenance._declared_aliases = lambda decl: []
        try:
            stopped = [s for s in self.CASES if self._judge(s) is not None]
        finally:
            provenance._declared_aliases = saved
        self.assertEqual(stopped, ["- Total RAM: 15.9 GB"])

    def test_a_backed_number_still_passes_in_the_new_words(self):
        """The aliases widen what is READ, not what is REFUSED. The same
        sentence against a ground that holds the reading is not a conflict."""
        ground = _Ground(ran={"inspect_hardware": (8.0,)})
        self.assertIsNone(
            provenance.reads_as_a_measurement("- Video Memory: 8 GB", ground, self.LEAD)
        )


class TheHonestSentenceInTheseWordsStillGetsThroughTest(Sandboxed):
    """"Free disk space", "system memory" and "video memory" are ordinary
    English, and the danger is not theoretical. Each shape the brief names is
    pinned here, in the exact words the aliases now listen for.

    THIS IS THE HALF THAT GETS FORGOTTEN. A wall in this repository once
    interrupted 14% of turns at a 100% false-catch rate, which is worse than no
    wall, because it teaches the person to ignore the product.
    """

    MUST_REACH_THE_USER = (
        # a person asking
        "How much video memory do I need?",
        "Do you know how much free disk space is required for a 7B model?",
        # a hypothetical
        "If your GPU had 24 GB of video memory, then a 13B model would fit.",
        "Suppose you had 64 GB of system memory and 2 TB of free disk space.",
        # a recommendation
        "You want at least 16 GB of system memory for this.",
        "You should aim for 500 GB of free disk space before starting.",
        # general knowledge that is NOT about this user
        "An RTX 4090 has 24 GB of video memory.",
        "Most consumer graphics cards ship with 8 GB of video memory.",
        # the harness describing its own tools
        "`inspect_hardware` reports video memory, system memory and free disk space.",
        # a bound is not a reading
        "Training needs at most 40 GB of free disk space.",
    )

    def test_not_one_of_them_is_stopped(self):
        for sentence in self.MUST_REACH_THE_USER:
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN), sentence
                )

    def test_but_the_reporting_form_of_the_same_words_is_stopped(self):
        """NON-VACUOUS, and the point of the whole class: these are not passing
        because the wall cannot see the words. Strip the question, the
        supposition and the wanting verb, and the same nouns are refused."""
        for sentence in (
            "You have 24 GB of video memory.",
            "Your system memory is 64 GB.",
            "You have 500 GB of free disk space.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN), sentence
                )


if __name__ == "__main__":
    unittest.main()
