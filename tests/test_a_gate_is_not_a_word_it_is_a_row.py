"""A gate is a row that was earned, not a sentence that says it was.

## The defect, measured on the owner's own database

Thread 34 recorded ZERO rows in `fact_evidence` and told him, in message 231:

    "An eval set exists, which is crucial for measuring performance."
    "A baseline score was measured, indicating some level of performance
     against a trivial or default model."
    "Prompting has been exhausted with at least three iterations and an
     automated optimiser run."

None of it had happened. Three messages later the SAME reply was stopped
mid-stream for showing `ram_gb = 32`, correctly, because no instrument had
produced that figure - so the number wall works and the gate wall did not
exist. `AGENTS.md` invariant 4 says the five-gate test may never be weakened; it was
enforced in `app/diagnosis.py`, where no fact means no gate, and unenforced in
the sentence the person actually reads.

## What is asserted here

Both halves, and the second matters more than the first:

* the three real fabricated sentences are caught;
* nine honest sentences about gates - planning, negating, asking, hedging -
  are RELEASED, including the two true ones from that same message ("retrieval
  has not yet been considered", "a cheaper or smaller model has not been
  considered"). A guard that stopped those would be worse than the hole,
  because this product's model must be able to say what is missing.

The vocabulary is derived from each gate's own id, so a ledger that adds a
gate tomorrow is covered that day; `test_a_gate_added_tomorrow_is_covered`
holds that by deriving from a gate id this file never mentions.
"""

from __future__ import annotations

import unittest

from app import conductor, provenance

GATES = [
    "G0_EVAL_SET",
    "G1_BASELINE_MEASURED",
    "G2_PROMPT_EXHAUSTED",
    "G3_RETRIEVAL_CONSIDERED",
    "G4_CHEAPER_MODEL_CONSIDERED",
]

#: Verbatim from thread 34, message 231, against a ledger holding no facts.
FABRICATED = {
    "An eval set exists, which is crucial for measuring performance.": "G0_EVAL_SET",
    (
        "A baseline score was measured, indicating some level of performance "
        "against a trivial or default model."
    ): "G1_BASELINE_MEASURED",
    (
        "Prompting has been exhausted with at least three iterations and an "
        "automated optimiser run."
    ): "G2_PROMPT_EXHAUSTED",
}

#: Sentences a working model must still be able to write. The first two are
#: from the same message as the fabrications above and were TRUE.
HONEST = [
    "Retrieval has not yet been considered but is flagged as a potential area.",
    "A cheaper or smaller model has not been considered yet.",
    "We need an eval set before anything can be measured.",
    "Once a baseline is measured we can compare the two.",
    "I could not find a baseline score in this conversation.",
    "Should I carve an eval set from your file?",
    "The next step is to measure a baseline.",
    "If prompting has been exhausted, training becomes the question.",
    "I will run the diagnosis and report what it says.",
]


class TheFabricationsAreCaughtTest(unittest.TestCase):
    def test_each_real_sentence_names_its_own_gate(self):
        for sentence, gate in FABRICATED.items():
            with self.subTest(gate=gate):
                self.assertEqual(provenance.gates_claimed_by(sentence, GATES), [gate])

    def test_a_walk_that_never_happened_is_named_as_such(self):
        for sentence in FABRICATED:
            with self.subTest(sentence=sentence[:40]):
                caught = provenance.reads_as_a_gate_claim(sentence, {})
                self.assertIsNotNone(caught)
                self.assertEqual(
                    caught["engine_status"], "never walked in this conversation"
                )

    def test_a_gate_the_walk_did_not_pass_is_caught(self):
        ledger = {gate: {"status": "NOT_MET"} for gate in GATES}
        caught = provenance.reads_as_a_gate_claim(
            "A baseline score was measured, indicating some level of performance.",
            ledger,
        )
        self.assertEqual(caught["gate"], "G1_BASELINE_MEASURED")
        self.assertEqual(caught["engine_status"], "NOT_MET")

    def test_a_gate_the_walk_did_pass_may_be_said_freely(self):
        """The wall is about UNEARNED claims. A gate the engine passed is a
        thing the model is supposed to be able to report."""
        ledger = {gate: {"status": "NOT_MET"} for gate in GATES}
        ledger["G1_BASELINE_MEASURED"] = {"status": "PASSED"}
        self.assertIsNone(
            provenance.reads_as_a_gate_claim(
                "A baseline score was measured on your rows.", ledger
            )
        )

    def test_soft_narration_over_earned_facts_is_not_a_gate_lie(self):
        """Max's measure_baseline loop, 2026-09-14: the tool stamped the
        facts, the walk still said NOT_REACHED, and soft narration of the
        measurement was withheld as if the model had invented a gate."""
        ledger = {gate: {"status": "NOT_REACHED"} for gate in GATES}
        origins = {
            "baseline_measured": "MEASURED",
            "baseline_score": "MEASURED",
            "trivial_baseline_score": "MEASURED",
        }
        self.assertIsNone(
            provenance.reads_as_a_gate_claim(
                "A baseline score was measured on your rows.",
                ledger,
                fact_origins=origins,
            )
        )

    def test_naming_the_gate_as_satisfied_still_needs_PASSED(self):
        ledger = {gate: {"status": "NOT_REACHED"} for gate in GATES}
        origins = {
            "baseline_measured": "MEASURED",
            "baseline_score": "MEASURED",
            "trivial_baseline_score": "MEASURED",
        }
        caught = provenance.reads_as_a_gate_claim(
            "G1_BASELINE_MEASURED is satisfied.",
            ledger,
            fact_origins=origins,
        )
        self.assertIsNotNone(caught)
        self.assertEqual(caught["gate"], "G1_BASELINE_MEASURED")
        self.assertEqual(caught["engine_status"], "NOT_REACHED")


class TheHonestSentencesSurviveTest(unittest.TestCase):
    def test_nothing_honest_is_stopped(self):
        for sentence in HONEST:
            with self.subTest(sentence=sentence[:44]):
                self.assertEqual(
                    provenance.gates_claimed_by(sentence, GATES), [],
                    "a sentence that plans, negates, asks or hedges is not a "
                    "claim, and stopping it would be worse than the hole this "
                    "wall closes",
                )
                self.assertIsNone(provenance.reads_as_a_gate_claim(sentence, {}))

    def test_a_sentence_with_no_verb_of_arrival_is_not_a_claim(self):
        self.assertEqual(
            provenance.gates_claimed_by("The eval set, the baseline, the prompt.", GATES),
            [],
        )


class TheVocabularyIsDerivedTest(unittest.TestCase):
    def test_a_gate_id_becomes_the_words_a_person_writes(self):
        self.assertEqual(
            provenance._gate_words("G1_BASELINE_MEASURED"), ("baseline", "measured")
        )

    def test_the_index_prefix_and_the_stop_words_come_off(self):
        self.assertEqual(
            provenance._gate_words("G5_THE_RUN_IS_BOUNDED_AND_RECORDED"),
            ("run", "bounded", "recorded"),
        )

    def test_a_gate_added_tomorrow_is_covered_the_day_it_lands(self):
        """Derived, not listed. This gate id appears in no other file."""
        invented = "G9_THE_TOKENISER_WAS_PINNED"
        self.assertEqual(
            provenance.gates_claimed_by("The tokeniser was pinned.", [invented]),
            [invented],
        )
        # And the same sentence with a planning word in it is released, which
        # is why "before the run" had to come out of this fixture: `before`
        # is one of the words that turns a claim back into a plan.
        self.assertEqual(
            provenance.gates_claimed_by(
                "The tokeniser was pinned before the run.", [invented]
            ),
            [],
        )

    def test_english_inflection_is_matched_in_one_direction_only(self):
        """`prompt` must match "prompting"; `set` must not be matched by "s"."""
        self.assertTrue(provenance._mentions("prompt", ["prompting"]))
        self.assertTrue(provenance._mentions("exhausted", ["exhausted"]))
        self.assertFalse(provenance._mentions("set", ["s"]))


class TheTurnStillSpeaksTest(unittest.TestCase):
    """Every ending this wall can reach has a sentence, and it names a move."""

    def test_the_new_ending_has_a_closing_sentence(self):
        self.assertIn(conductor.GATE_WITHHELD, conductor.SILENT_TURN)
        said = conductor.SILENT_TURN[conductor.GATE_WITHHELD]
        self.assertIn("{detail}", said)
        self.assertIn("ask again", said)

    def test_the_detail_names_the_gate_and_what_the_walk_holds(self):
        said = provenance.gate_refusal_sentence(
            {"gate": "G0_EVAL_SET", "engine_status": "NOT_MET"}
        )
        self.assertIn("G0_EVAL_SET", said)
        self.assertIn("NOT_MET", said)

    def test_the_detail_limit_covers_it(self):
        self.assertIn(conductor.GATE_WITHHELD, conductor.DETAIL_LIMIT)


class ACriterionIsAPlanTest(unittest.TestCase):
    """A live false catch, 2026-09-11, kept as the sentence it happened on.

    Plan mode, the owner's own question, his own model: a six-phase plan
    written in 28 seconds and withheld whole because one line named the
    measurement that would settle a phase. The reader saw `baseline` and
    `measured` and nothing in `_NOT_YET_A_CLAIM` said it was a plan.
    """

    SENTENCE = (
        "**Exit criterion**: baseline_score + trivial_baseline_score measured on "
        "same eval set; adapter score beats baseline by >=1 point."
    )

    def test_the_sentence_that_was_withheld_is_released(self):
        from app import provenance
        self.assertEqual(
            provenance.gates_claimed_by(self.SENTENCE, provenance._ledger_gate_ids()),
            [],
        )
        self.assertIsNone(provenance.reads_as_a_gate_claim(self.SENTENCE, {}))

    def test_the_same_gate_asserted_as_done_is_still_caught(self):
        """The other direction, so the release cannot become a hole."""
        from app import provenance
        done = "The baseline was measured on the eval set and that gate passed."
        self.assertTrue(provenance.gates_claimed_by(done, provenance._ledger_gate_ids()))


class TheGateReaderStandsDownWhilePlanningTest(unittest.TestCase):
    """The second live false catch of 2026-09-11, kept as the line it happened on.

    Thread 93, plan mode, the owner's model: `write_plan` had just saved a
    nine-phase plan, and the two-sentence summary the tool asks for was
    withheld at its fourth item - a phase describing its own measurement. Of
    five live plan turns that reached a reply that day, this reader stopped
    two. In plan mode nothing can train on a claimed gate, so the reader
    stands down there and only there; the same sentence in a build turn is
    still caught.
    """

    SENTENCE = (
        "**Evaluate and benchmark** — baseline measured, eval set counted, "
        "split leakage checked.\n"
    )

    def _fed(self, planning: bool):
        from app import conductor
        sentry = conductor._Sentry(conductor._Standing(None), None, planning=planning)
        sentry.feed(self.SENTENCE)
        return sentry.conflict

    def test_a_plan_turn_is_not_stopped_on_a_phase_naming_its_gate(self):
        self.assertIsNone(self._fed(planning=True))

    def test_a_build_turn_still_is(self):
        from app import conductor
        conflict = self._fed(planning=False)
        self.assertIsNotNone(conflict, "the build-turn reader let a gate claim through")
        self.assertEqual(conflict["kind"], conductor.INVENTED_GATE)


if __name__ == "__main__":
    unittest.main()
