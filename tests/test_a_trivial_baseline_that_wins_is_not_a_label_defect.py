"""S1_LABELS_ARE_NOISE draws a two-sided window, because its sentence says "within".

THIS WAS THE SECOND BROKEN RUNG OF THE FIRST REAL JOURNEY, and it is worth the
file because the defect was one character class wide and it walled off a whole
population.

The condition read:

    trivial_baseline_score >= baseline_score - 0.05 or data_quality < 0.6

which is ONE-SIDED. It is true when a majority-class guess beats the LLM by
three points, and it is equally true when it beats it by sixty-three. The `say:`
under it claimed "within 5 points" in both cases, so the product asserted a
measurement it had not made, which is the one thing this repository exists not
to do. `app/tools/propose.py` describes the same node twice as a line "where
being INSIDE it is a statement about your labels rather than about your model" -
the prose was right and the condition disagreed with it.

WHAT IT COST, MEASURED ON A REAL RUN. A closed-set text classifier over 229
commits of this repository: an eval set carved and counted, a baseline measured
at 0.00 against a majority-class trivial of 0.63 because the model answered in
the wrong format every time - which the product had ALREADY measured into
failure_histogram as {wrong_format: 30} in the same thread. The answer was
"the task or the labels are wrong, not the model", about labels read out of git,
and the only next step offered was measure_baseline, the tool that had just run.

AND IT SHADOWED THE NODE WRITTEN FOR THAT USER. S1_LABELS_ARE_NOISE sits
directly above S1_CLOSED_SET_CLASSIFICATION, the door to the small-encoder
answers, so the users most likely to be below a trivial baseline at a
fixed-taxonomy task were exactly the ones it stopped.

WHY FALLING THROUGH IS THE FIX AND A SECOND TERMINAL IS NOT, which is the part
that had to be argued rather than assumed. "The LLM is below a trivial baseline"
does not by itself decide anything: a model that gets the content right and the
style wrong on every row scores zero on exact match while a majority-class guess
scores well, and a style fine-tune is the correct answer to that. The fact that
DOES decide is the failure histogram, and the machinery for reading it is
already below this line - the closed-set door, then `S1_GAP_UNDIAGNOSED`, then
the failure-mode fork. Terminating here would only move the shadow down one row.

So the widening is real and it is stated rather than buried:
`test_the_widening_is_measured_and_every_gate_still_holds` walks the whole
score plane on every minting fixture and asserts that the runs that newly reach
a training verdict have passed all five gates - which is the guarantee, and it
is not the same claim as "nothing changed."

THE FLOOR COLLISION, 2026-09-16. trivial 0.05 against LLM 0.00 is also "within
5 points", and on a free-form set with forty distinct expected answers that
majority score is chance, not evidence the labels are noise. The within-window
arm now also requires `trivial_baseline_score >= 0.15`.
"""

from __future__ import annotations

import unittest

from app.diagnosis import diagnose, load_spec

import diagnosis_fixtures as fixtures


SPEC = load_spec()
REQUIRED = set(SPEC.required_gates)


def _scored(seed: dict, trivial: float, llm: float) -> dict:
    facts = dict(seed)
    facts.update(
        fixtures.attribute({"trivial_baseline_score": trivial, "baseline_score": llm})
    )
    return facts


class TheWindowIsTwoSidedTest(unittest.TestCase):
    SEED = fixtures.REACHING["BLOCKED__FIX_LABELS_OR_TASK"]

    def test_indistinguishable_is_still_a_label_defect(self):
        """The case the node was written for, and it must not move."""
        for trivial, llm in ((0.52, 0.55), (0.55, 0.55), (0.60, 0.55), (0.50, 0.55)):
            with self.subTest(trivial=trivial, llm=llm):
                result = diagnose(_scored(self.SEED, trivial, llm), SPEC)
                self.assertEqual(result.outcome, "BLOCKED__FIX_LABELS_OR_TASK")
                self.assertEqual(result.node, "S1_LABELS_ARE_NOISE")

    def test_a_trivial_baseline_that_wins_by_more_than_the_window_falls_through(self):
        """Sixty-three points apart is not "within 5 points" and must not say so."""
        for trivial, llm in ((0.65, 0.55), (0.63, 0.00), (0.90, 0.10), (1.00, 0.00)):
            with self.subTest(trivial=trivial, llm=llm):
                result = diagnose(_scored(self.SEED, trivial, llm), SPEC)
                self.assertNotEqual(result.node, "S1_LABELS_ARE_NOISE")
                self.assertEqual(result.outcome, "ACTION__CLASSIFY_FAILURES")

    def test_both_near_zero_is_not_a_label_defect(self):
        """Floor collision: chance majority vs zero LLM is not "labels are wrong".

        Measured on ml-principles-dataset under Full: trivial 0.05, LLM 0.00,
        forty distinct expected answers. The old within-window arm terminated
        at FIX_LABELS; the floor now lets the walk fall through to classify.
        """
        for trivial, llm in ((0.05, 0.00), (0.10, 0.05), (0.14, 0.10), (0.00, 0.00)):
            with self.subTest(trivial=trivial, llm=llm):
                result = diagnose(_scored(self.SEED, trivial, llm), SPEC)
                self.assertNotEqual(result.node, "S1_LABELS_ARE_NOISE")
                self.assertEqual(result.outcome, "ACTION__CLASSIFY_FAILURES")

    def test_the_boundary_is_where_the_sentence_puts_it(self):
        """Five points, inclusive, on BOTH sides. Not four and not six."""
        inside = diagnose(_scored(self.SEED, 0.60, 0.55), SPEC)
        outside = diagnose(_scored(self.SEED, 0.61, 0.55), SPEC)
        self.assertEqual(inside.node, "S1_LABELS_ARE_NOISE")
        self.assertNotEqual(outside.node, "S1_LABELS_ARE_NOISE")

    def test_the_majority_floor_is_where_the_condition_puts_it(self):
        """0.15 inclusive on the majority arm; below it, fall through."""
        at_floor = diagnose(_scored(self.SEED, 0.15, 0.12), SPEC)
        under_floor = diagnose(_scored(self.SEED, 0.149, 0.12), SPEC)
        self.assertEqual(at_floor.node, "S1_LABELS_ARE_NOISE")
        self.assertNotEqual(under_floor.node, "S1_LABELS_ARE_NOISE")

    def test_the_dirty_data_half_is_untouched(self):
        """`data_quality < 0.6` is an independent reason and still fires alone.

        Twenty points apart, so the window half is FALSE and the only thing that
        can be firing is the dirty-data half. The LLM is kept below
        `target_score` so S1_ALREADY_PASSES, which sits above, does not answer
        first - a fixture that reached this node for some other reason would
        prove nothing about this one.
        """
        facts = _scored(self.SEED, 0.20, 0.40)
        facts.update(fixtures.attribute({"data_quality": 0.3}))
        result = diagnose(facts, SPEC)
        self.assertEqual(result.outcome, "BLOCKED__FIX_LABELS_OR_TASK")
        self.assertEqual(result.node, "S1_LABELS_ARE_NOISE")
        clean = dict(facts)
        clean.update(fixtures.attribute({"data_quality": 0.9}))
        self.assertNotEqual(diagnose(clean, SPEC).node, "S1_LABELS_ARE_NOISE")

    def test_the_say_sentence_and_the_condition_agree(self):
        """The defect was that they did not, so this asserts the pair, not either half."""
        node = SPEC.node_index["S1_LABELS_ARE_NOISE"]
        condition = node["condition"]
        self.assertIn("<= baseline_score + 0.05", condition)
        self.assertIn(">= baseline_score - 0.05", condition)
        self.assertIn("trivial_baseline_score >= 0.15", condition)
        self.assertIn("within 5 points", node["say"])
        self.assertIn("beats chance", node["say"])


class TheClosedSetDoorIsNoLongerShadowedTest(unittest.TestCase):
    """The population the one-sided window shut out, restated as its own run."""

    def _classifier(self, trivial: float, llm: float, **extra) -> dict:
        facts = _scored(fixtures.REACHING["BLOCKED__FIX_LABELS_OR_TASK"], trivial, llm)
        facts.update(
            fixtures.attribute(
                {
                    "modality": "text",
                    "task_family": "classification",
                    "labels_are_closed_set": True,
                    "requires_multistep_reasoning": False,
                    "classes_n": 6,
                    "labeled_examples_n": 132,
                    "failure_histogram": {"wrong_format": 30},
                    **extra,
                }
            )
        )
        return facts

    def test_a_classifier_below_a_trivial_baseline_reaches_the_small_encoder_answer(self):
        result = diagnose(self._classifier(0.63, 0.00), SPEC)
        self.assertEqual(result.verdict, "NO_TRAIN")
        self.assertEqual(result.outcome, "NO_LLM__SETFIT")
        self.assertIn("S1_CLOSED_SET_CLASSIFICATION", [e.id for e in result.path])

    def test_the_same_run_under_the_one_sided_window_stopped_at_the_wall(self):
        """The control, and it is the whole point: only the two scores differ.

        Inside the window the same closed-set classifier still gets the label
        answer, because inside the window that answer is true.
        """
        result = diagnose(self._classifier(0.58, 0.55), SPEC)
        self.assertEqual(result.outcome, "BLOCKED__FIX_LABELS_OR_TASK")


class TheWideningIsMeasuredAndEveryGateStillHoldsTest(unittest.TestCase):
    """The honest half. Runs that were walled off can now reach a verdict.

    This does NOT assert that nothing changed - something did, and pretending
    otherwise would be the failure mode this whole repository is built against.
    It asserts the thing that is actually guaranteed: every run that reaches the
    gated prefix has passed all five gates under its own proposal's class.
    """

    def test_every_training_verdict_on_the_whole_score_plane_paid_all_five_gates(self):
        checked = 0
        training = 0
        for name, seed in fixtures.MINTING.items():
            for trivial in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
                for llm in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
                    result = diagnose(_scored(seed, trivial, llm), SPEC)
                    checked += 1
                    if not result.outcome.startswith(SPEC.gated_prefix):
                        continue
                    training += 1
                    passed = {
                        gate
                        for gate, entry in result.gate_ledger.items()
                        if entry["status"] == "PASSED"
                    }
                    self.assertEqual(
                        REQUIRED - passed,
                        set(),
                        f"{name} at trivial={trivial} llm={llm} reached "
                        f"{result.outcome} without {sorted(REQUIRED - passed)}",
                    )
        self.assertEqual(checked, len(fixtures.MINTING) * 36)
        self.assertGreater(training, 0, "a plane with no training verdict proves nothing")

    def test_a_run_below_the_trivial_baseline_is_not_waved_through_the_gates(self):
        """The specific worry, asked directly: does losing to a guess buy anything?

        It buys nothing. The gate ledger of a run at trivial=0.9, llm=0.1 is the
        same five questions as any other, and the fixture that reaches a verdict
        does so because it answered them.
        """
        seed = fixtures.MINTING["TRAIN__LORA_SFT"]
        below = diagnose(_scored(seed, 0.90, 0.10), SPEC)
        even = diagnose(_scored(seed, 0.50, 0.52), SPEC)
        self.assertEqual(even.outcome, "BLOCKED__FIX_LABELS_OR_TASK")
        self.assertTrue(below.outcome.startswith(SPEC.gated_prefix))
        self.assertEqual(
            {g for g, e in below.gate_ledger.items() if e["status"] == "PASSED"},
            REQUIRED,
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
