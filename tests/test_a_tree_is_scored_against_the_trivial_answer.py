"""A tree's accuracy is a number with an alibi, or it is not reported at all.

`app/tools/classical.py` is the first thing in this product that fits a model.
Everything that makes it worth having is a way of NOT producing the number a
naive version would produce, so this file is mostly about numbers that must not
come back.

The naive version of this tool is about fifteen lines - read a CSV, call
`fit`, call `score`, return it - and every one of the following would be true of
it, silently:

* it would report training accuracy, which on pure noise is near 100%;
* it would report "73%" on a set that is 70% one class as though it were a
  result;
* it would compare against a baseline computed from the rows being scored, which
  is a peek;
* it would score a dataset whose label is sitting in another column under a
  different name, come back at 99.8%, and nobody would ask;
* it would stamp `baseline_score` MEASURED, because that fact exists and is
  measurable, and it would thereby open the first gate of five on a tree fitted
  to a spreadsheet in a thread about fine-tuning a language model.

Eight properties, and each one is driven rather than described:

1. **THE HOLD-OUT IS REAL, PROVEN ON NOISE.** A label that is a coin flip
   independent of every feature. A tree scored on rows it was fitted on gets
   near all of them right; scored on held-out rows it cannot beat the trivial
   answer, and McNemar says so. This is the test that fails loudly if anybody
   ever scores the training matrix.
2. **THE SCORE IS NEVER ALONE.** Score, trivial baseline over the SAME rows, the
   paired McNemar over the rows they disagreed on, and the Wilson interval - all
   four present, all four consistent with each other, and all four in the
   sentence a person reads.
3. **THE BASELINE DOES NOT PEEK.** It is the commonest label among the rows the
   tree was FITTED on. Driven with a train file and a hold-out file whose
   majorities differ, so the honest baseline and the peeking one are different
   numbers and it can be checked which one was used.
4. **THE SPLIT IS REPRODUCIBLE AND CANNOT STRADDLE.** The same call twice gives
   the same split and the same score; a file that is one input repeated cannot
   put that input on both sides; a hold-out supplied by the caller is CHECKED and
   a leaking one is refused.
5. **THE LEAK REFUSALS FIRE, AND THE DOOR OUT OF THEM WORKS.** Both checks, each
   on the leak the other one misses, and dropping the named column produces a
   real fit.
6. **THE FIVE GATES ARE UNTOUCHED.** The one the brief asked to be proved. The
   gate ledger over a thread is byte-identical before and after this tool runs,
   the tool declares `measures=()` and `writes=()`, and the registry's own walls
   are checked to still be the reason.
7. **IT SAYS WHAT IT DID NOT TRY, AND READS IT RATHER THAN REMEMBERING IT.**
   Proved by MOVING the engine - a fourth library in the spec's `method.libs`
   and a different trial count on G2 - rather than by comparing "50" to "50".
8. **NO NEW DEPENDENCY.** Asserted against the module's own syntax tree: not one
   import of sklearn or numpy at module level, so `import app.tools` on a machine
   without them still works and neither becomes a dependency of this product by
   accident.
"""

from __future__ import annotations

import ast
import csv
import dataclasses
import json
import random
import unittest
from pathlib import Path
from unittest import mock

from app import dataquality, diagnosis
from app.tools import REGISTRY, classical, evals, evidence
from app.tools.evidence import Instrument
from app.tools.registry import RESERVED_ARGUMENTS, RESERVED_WRITES, Registry

import diagnosis_fixtures as fixtures
import support


TOOL = "fit_a_tree_model"

#: SKIPPED RATHER THAN FAILED WHERE THE LIBRARY IS NOT THERE, and the reason is
#: the property `NoNewDependencyTest` asserts: scikit-learn is not declared in
#: `pyproject.toml`, so a fresh checkout may legitimately not have it. A suite
#: that went red on such a machine would be arguing for the dependency this
#: whole lane exists not to add. Everything that does NOT need a fit - the
#: registration, the walls, the `measures=()` proof, the dependency check - runs
#: either way, so the tool's contract with the rest of the harness is still
#: checked on a machine that cannot fit anything.
NEEDS_A_FITTER = unittest.skipUnless(
    classical.available()["sklearn"] and classical.available()["numpy"],
    "scikit-learn or numpy is not installed, and neither is a declared "
    "dependency of this repository",
)


class TreeTestCase(unittest.TestCase):
    """A scratch database and a scratch directory each. Nothing here is shared."""

    def setUp(self):
        self.root = support.sandbox(self)

    # -- fixtures ----------------------------------------------------------

    def csv_file(self, name: str, header: list[str], rows: list[list]) -> str:
        path = self.root / name
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
        return str(path)

    def jsonl_file(self, name: str, records: list[dict]) -> str:
        path = self.root / name
        path.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n",
            encoding="utf-8",
        )
        return str(path)

    def signal_file(self, name: str = "churn.csv", rows: int = 800, seed: int = 7):
        """A table where the label really does follow from the features."""
        rng = random.Random(seed)
        out = []
        for _ in range(rows):
            tenure = rng.randint(1, 72)
            spend = round(rng.uniform(10, 200), 2)
            plan = rng.choice(["basic", "plus", "pro"])
            tickets = rng.randint(0, 9)
            risk = (
                (72 - tenure) / 72 * 1.4
                + tickets / 9 * 0.9
                + (0.4 if plan == "basic" else 0.0)
            )
            label = "yes" if risk + rng.gauss(0, 0.45) > 1.35 else "no"
            out.append([tenure, spend, plan, tickets, label])
        return self.csv_file(
            name,
            ["tenure_months", "monthly_spend", "plan", "support_tickets", "churned"],
            out,
        )

    def noise_file(self, name: str = "noise.csv", rows: int = 800, seed: int = 3):
        """The same shape with NO signal in it at all. The label is a coin flip.

        This is the fixture the hold-out property is proved on. A tree fitted on
        these rows can memorise every one of them - the features are continuous
        and unique, so it can - and will score near 100% on them. It can score
        no better than the coin on rows it has not seen.
        """
        rng = random.Random(seed)
        out = []
        for _ in range(rows):
            out.append(
                [
                    round(rng.uniform(0, 1000), 4),
                    round(rng.uniform(0, 1000), 4),
                    round(rng.uniform(0, 1000), 4),
                    rng.choice(["yes", "no"]),
                ]
            )
        return self.csv_file(name, ["a", "b", "c", "label"], out)

    def fit(self, **arguments):
        return REGISTRY.call(TOOL, arguments)


# ---------------------------------------------------------------------------
# 1. The hold-out is real, and noise is what proves it.


@NEEDS_A_FITTER
class TheScoreIsOnRowsItNeverSawTest(TreeTestCase):
    def training_accuracy(self, path: str) -> float:
        """What the naive fifteen-line version of this tool would have reported.

        The same estimator, fitted on every row of the file and scored on every
        row of the file. Computed HERE, from the file on disk, rather than taken
        from the tool - the whole point is to have a number the tool had no hand
        in, to hold its number against.
        """
        import numpy as np
        from sklearn.ensemble import HistGradientBoostingClassifier

        rows = list(dataquality.iter_records(path))
        matrix = np.array(
            [[float(row["a"]), float(row["b"]), float(row["c"])] for row in rows]
        )
        labels = np.array([1 if row["label"] == "yes" else 0 for row in rows])
        estimator = HistGradientBoostingClassifier(random_state=0, early_stopping=False)
        estimator.fit(matrix, labels)
        return float((estimator.predict(matrix) == labels).mean())

    def test_a_tree_cannot_beat_a_coin_on_a_coin(self):
        """The single most important assertion in this file.

        `HistGradientBoostingClassifier` on three continuous features and 800
        rows of coin flips memorises them: fitted on all of them and scored on
        all of them it is far above chance, and that is the number the naive
        version of this tool reports. What comes back here is what the tree
        knows about rows it has not seen, which on a coin flip is nothing.

        THREE SEEDS, because one is an anecdote and because a single McNemar at
        alpha 0.05 is wrong one time in twenty BY CONSTRUCTION - the first draft
        of this test asserted on it and drew that twentieth case. What is
        asserted instead is the gap, which is not a coin toss: memorising is
        tens of points, and generalising from noise is none.
        """
        for seed in (3, 29, 101):
            with self.subTest(seed=seed):
                path = self.noise_file(f"noise-{seed}.csv", seed=seed)
                result = self.fit(path=path, target_column="label")
                self.assertTrue(result["ok"], result.get("summary"))

                score = result["score"]
                trivial = result["trivial_baseline"]
                memorised = self.training_accuracy(path)

                self.assertEqual(
                    score["of"], trivial["of"], "two scores, different rows"
                )
                self.assertGreater(
                    memorised,
                    0.90,
                    "the fixture has no signal but this estimator did not "
                    "memorise it either, so the test below proves nothing",
                )
                self.assertLess(
                    score["accuracy"],
                    memorised - 0.20,
                    "the reported score is within twenty points of what the same "
                    "estimator scores on its own training rows, on data that is "
                    f"a coin flip: {result['summary']}",
                )
                self.assertLess(
                    score["accuracy"] - trivial["accuracy"],
                    0.15,
                    "a tree beat the trivial answer by more than fifteen points "
                    f"on pure noise: {result['summary']}",
                )

    def test_the_number_of_scored_rows_is_the_hold_out_and_nothing_else(self):
        result = self.fit(path=self.signal_file(), target_column="churned")
        split = result["split"]
        self.assertEqual(result["score"]["of"], split["holdout_rows"])
        self.assertEqual(
            split["train_rows"] + split["holdout_rows"], result["rows"]["used"]
        )
        self.assertEqual(split["inputs_on_both_sides"], 0)

    def test_a_tree_that_has_signal_does_beat_the_trivial_answer(self):
        """The other direction, so the test above is not passing on a dead tool."""
        result = self.fit(path=self.signal_file(), target_column="churned")
        self.assertGreater(
            result["score"]["correct"], result["trivial_baseline"]["correct"]
        )
        self.assertTrue(result["comparison"]["separated"], result["summary"])


# ---------------------------------------------------------------------------
# 2. The score is never alone.


@NEEDS_A_FITTER
class TheScoreTravelsWithItsBaselineAndItsIntervalTest(TreeTestCase):
    def setUp(self):
        super().setUp()
        self.result = self.fit(path=self.signal_file(), target_column="churned")
        self.assertTrue(self.result["ok"], self.result.get("summary"))

    def test_all_four_numbers_are_there(self):
        for key in (
            "score",
            "trivial_baseline",
            "best_constant_on_the_holdout",
            "comparison",
            "resolution",
        ):
            self.assertIsNotNone(self.result[key], key)

    def test_the_interval_is_the_one_the_eval_bench_computes(self):
        """`evals.resolution_for`, not a second Wilson written here.

        `resolution.n` IS `score.of` and that is the point of the identity: the
        interval below the score is the interval for that many ROWS. What used
        to be missing is the other half - that the rows are not independent
        units - and it is asserted beside it rather than instead of it.
        """
        score = self.result["score"]
        self.assertEqual(
            self.result["resolution"],
            evals.resolution_for(score["correct"], score["of"]),
        )
        self.assertEqual(self.result["resolution"]["n"], score["of"])
        # The unit the interval is over is stated, and the version over
        # independent inputs is beside it.
        over_inputs = self.result["resolution_over_distinct_inputs"]
        self.assertEqual(
            over_inputs["n"], self.result["split"]["holdout_distinct_inputs"]
        )
        self.assertEqual(
            over_inputs["mcnemar_p"],
            evals.mcnemar(over_inputs["improved"], over_inputs["regressed"]),
        )

    def test_the_comparison_is_the_paired_test_over_the_rows_that_disagreed(self):
        comparison = self.result["comparison"]
        n = self.result["score"]["of"]
        self.assertEqual(
            comparison["improved"] + comparison["regressed"], comparison["disagreed"]
        )
        self.assertEqual(comparison["disagreed"] + comparison["agreed"], n)
        self.assertEqual(
            comparison["mcnemar_p"],
            evals.mcnemar(comparison["improved"], comparison["regressed"]),
        )
        # The difference in points is the two counts, over the same rows.
        self.assertAlmostEqual(
            comparison["difference_points"],
            (self.result["score"]["correct"] - self.result["trivial_baseline"]["correct"])
            / n
            * 100.0,
            places=9,
        )

    def test_the_sentence_a_person_reads_carries_both_scores(self):
        summary = self.result["summary"]
        self.assertIn(f"{self.result['score']['correct']} of", summary)
        self.assertIn(str(self.result["trivial_baseline"]["correct"]), summary)
        self.assertIn("McNemar", summary)
        self.assertIn("95% confidence", summary)
        self.assertIn("no hyperparameter search was run", summary)

    def test_a_percentage_never_appears_without_its_counts(self):
        """Invariant 4: counts, never bare percentages.

        Every accuracy in the payload sits beside the `correct` and `of` it was
        divided from, so a reader can always recompute it.
        """
        for key in ("score", "trivial_baseline", "best_constant_on_the_holdout"):
            block = self.result[key]
            self.assertAlmostEqual(
                block["accuracy"], block["correct"] / block["of"], places=12, msg=key
            )


# ---------------------------------------------------------------------------
# 3. The baseline does not peek.


@NEEDS_A_FITTER
class TheTrivialAnswerComesFromTheRowsItWasFittedOnTest(TreeTestCase):
    """Two files whose majorities disagree, so the two baselines differ.

    Train is mostly `no`; the hold-out is mostly `yes`. The honest baseline -
    the training majority applied to the hold-out - therefore scores BADLY, and
    the peeking one scores well. A tool that computed its trivial baseline from
    the rows it was scoring would report the larger number, and this test says
    which one came back.
    """

    def setUp(self):
        super().setUp()
        rng = random.Random(5)
        train = [
            {"x": rng.random(), "y": rng.random(), "label": "no" if i % 5 else "yes"}
            for i in range(400)
        ]
        holdout = [
            {"x": rng.random(), "y": rng.random(), "label": "yes" if i % 5 else "no"}
            for i in range(200)
        ]
        self.train_path = self.jsonl_file("train.jsonl", train)
        self.holdout_path = self.jsonl_file("holdout.jsonl", holdout)
        self.result = self.fit(
            path=self.train_path,
            holdout_path=self.holdout_path,
            target_column="label",
        )
        self.assertTrue(self.result["ok"], self.result.get("summary"))

    def test_the_two_baselines_are_different_numbers_here(self):
        honest = self.result["trivial_baseline"]
        peeking = self.result["best_constant_on_the_holdout"]
        self.assertNotEqual(honest["answer"], peeking["answer"])
        self.assertLess(honest["correct"], peeking["correct"])

    def test_the_honest_one_is_the_training_majority(self):
        self.assertEqual(self.result["trivial_baseline"]["answer"], "no")
        self.assertEqual(self.result["best_constant_on_the_holdout"]["answer"], "yes")
        self.assertEqual(self.result["trivial_baseline"]["correct"], 40)
        self.assertEqual(self.result["best_constant_on_the_holdout"]["correct"], 160)

    def test_the_comparison_uses_the_honest_one(self):
        comparison = self.result["comparison"]
        self.assertAlmostEqual(
            comparison["difference_points"],
            (self.result["score"]["correct"] - self.result["trivial_baseline"]["correct"])
            / self.result["score"]["of"]
            * 100.0,
            places=9,
        )

    def test_the_peeking_one_is_labelled_as_peeking(self):
        peeking = self.result["best_constant_on_the_holdout"]
        self.assertIs(peeking["peeks"], True)
        self.assertIn("looking at them", peeking["is"])
        self.assertIn("fitted", self.result["trivial_baseline"]["how"])


# ---------------------------------------------------------------------------
# 4. The split.


@NEEDS_A_FITTER
class TheSplitIsAHashAndNotAShuffleTest(TreeTestCase):
    def test_the_same_call_twice_gives_the_same_split_and_the_same_score(self):
        path = self.signal_file()
        first = self.fit(path=path, target_column="churned")
        second = self.fit(path=path, target_column="churned")
        self.assertEqual(first["split"]["holdout_rows"], second["split"]["holdout_rows"])
        self.assertEqual(first["score"], second["score"])
        self.assertEqual(first["trivial_baseline"]["correct"],
                         second["trivial_baseline"]["correct"])

    def test_the_seed_changes_the_draw_and_nothing_else(self):
        path = self.signal_file()
        plain = self.fit(path=path, target_column="churned")
        seeded = self.fit(path=path, target_column="churned", seed="other")
        self.assertEqual(plain["rows"]["used"], seeded["rows"]["used"])
        self.assertNotEqual(
            plain["score"]["correct"] * 1000 + plain["split"]["holdout_rows"],
            seeded["score"]["correct"] * 1000 + seeded["split"]["holdout_rows"],
            "changing the seed changed neither the split nor the score",
        )

    def test_two_identical_inputs_cannot_land_on_opposite_sides(self):
        """Every row duplicated. The duplicate must follow its twin."""
        rng = random.Random(13)
        rows = []
        for _ in range(300):
            row = [
                round(rng.uniform(0, 100), 3),
                rng.choice(["a", "b", "c"]),
                rng.choice(["yes", "no"]),
            ]
            rows.append(row)
            rows.append(list(row))
        path = self.csv_file("twins.csv", ["x", "k", "label"], rows)
        result = self.fit(path=path, target_column="label")
        self.assertTrue(result["ok"], result.get("summary"))
        self.assertEqual(result["split"]["inputs_on_both_sides"], 0)
        self.assertEqual(result["rows"]["used"], 600)
        self.assertEqual(result["split"]["distinct_inputs_in_the_file"], 300)

    def test_the_split_is_grouped_on_the_features_and_not_on_the_answer(self):
        """Same question, two different answers. Both go the same way.

        `dataquality.row_signature` would call these two DIFFERENT rows, because
        it hashes the answer too, and one of each pair could then be scored
        against a tree that had already been fitted on the other.
        """
        rng = random.Random(21)
        rows = []
        for _ in range(300):
            x = round(rng.uniform(0, 100), 3)
            k = rng.choice(["a", "b", "c"])
            rows.append([x, k, "yes"])
            rows.append([x, k, "no"])
        path = self.csv_file("ambiguous.csv", ["x", "k", "label"], rows)
        result = self.fit(path=path, target_column="label")
        self.assertTrue(result["ok"], result.get("summary"))
        self.assertEqual(result["split"]["inputs_on_both_sides"], 0)
        self.assertEqual(
            result["split"]["train_distinct_inputs"]
            + result["split"]["holdout_distinct_inputs"],
            300,
        )

    def test_a_hold_out_of_one_repeated_input_is_refused(self):
        """G0 counts real INPUTS. The same input three hundred times is one."""
        rows = [[1, "x", "yes" if i % 2 else "no"] for i in range(300)]
        path = self.csv_file("one_input.csv", ["a", "b", "label"], rows)
        result = self.fit(path=path, target_column="label")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "hold_out_too_small")
        self.assertIn("1 distinct input", result["summary"])
        self.assertTrue(result["nothing_was_fitted"])

    def test_a_supplied_split_is_checked_and_a_leaking_one_is_refused(self):
        path = self.signal_file()
        result = self.fit(path=path, holdout_path=path, target_column="churned")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "the_split_leaks")
        self.assertTrue(result["nothing_was_fitted"])
        self.assertIsNotNone(result["split_leakage"])
        self.assertEqual(result["split_leakage"]["leaked_rows"], 800)

    def test_a_clean_supplied_split_reports_that_it_was_checked(self):
        rng = random.Random(31)
        train = [
            {"x": rng.random(), "label": "yes" if rng.random() < 0.5 else "no"}
            for _ in range(400)
        ]
        holdout = [
            {"x": rng.random(), "label": "yes" if rng.random() < 0.5 else "no"}
            for _ in range(200)
        ]
        result = self.fit(
            path=self.jsonl_file("t.jsonl", train),
            holdout_path=self.jsonl_file("h.jsonl", holdout),
            target_column="label",
        )
        self.assertTrue(result["ok"], result.get("summary"))
        self.assertEqual(result["split"]["rule"], "supplied by the caller")
        self.assertEqual(result["split"]["train_rows"], 400)
        self.assertEqual(result["split"]["holdout_rows"], 200)
        self.assertEqual(result["split_leakage"]["leaked_rows"], 0)

    def test_the_hold_out_floor_is_the_gate_s_and_moving_the_gate_moves_it(self):
        """The floor is READ. Proved by moving it, not by comparing 30 to 30."""
        rng = random.Random(41)
        rows = [
            [round(rng.uniform(0, 100), 4), "yes" if i % 2 else "no"]
            for i in range(140)
        ]
        path = self.csv_file("small.csv", ["x", "label"], rows)

        # 140 rows, a quarter held out: 35, which clears a floor of 30.
        ok = self.fit(path=path, target_column="label")
        self.assertTrue(ok["ok"], ok.get("summary"))
        self.assertEqual(ok["split"]["holdout_floor"]["rows"], 30)

        with mock.patch(
            "app.tools.data.eval_set_floor",
            return_value={"rows": 500, "declared_in": "a moved gate"},
        ):
            moved = self.fit(path=path, target_column="label")
        self.assertFalse(moved["ok"])
        self.assertEqual(moved["error"], "hold_out_too_small")
        self.assertIn("500 is the floor", moved["summary"])
        self.assertIn("a moved gate", moved["summary"])


# ---------------------------------------------------------------------------
# 5. The leak refusals.


@NEEDS_A_FITTER
class AFeatureThatCarriesTheAnswerRefusesTheFitTest(TreeTestCase):
    def leaky_relabelling(self):
        """`is_churned` is `churned` with different spelling. Check A's case."""
        rng = random.Random(11)
        rows = []
        for _ in range(400):
            tenure = rng.randint(1, 72)
            tickets = rng.randint(0, 9)
            label = "yes" if (72 - tenure) / 72 + tickets / 9 > 1.0 else "no"
            rows.append([tenure, tickets, 1 if label == "yes" else 0, label])
        return self.csv_file(
            "leak_a.csv", ["tenure", "tickets", "is_churned", "churned"], rows
        )

    def leaky_oracle(self):
        """A six-valued band that determines the label. Check A cannot see it.

        Six distinct values against two classes, so "no more values than there
        are classes" is false and check A passes it. It still decides every
        held-out row, which is what check B is for.
        """
        rng = random.Random(17)
        rows = []
        for _ in range(400):
            tenure = rng.randint(1, 72)
            tickets = rng.randint(0, 9)
            label = "yes" if (72 - tenure) / 72 + tickets / 9 > 1.0 else "no"
            band = ("A" if label == "no" else "B") + str(rng.randint(0, 2))
            rows.append([tenure, tickets, band, label])
        return self.csv_file(
            "leak_b.csv", ["tenure", "tickets", "risk_band", "churned"], rows
        )

    def test_check_a_catches_the_relabelling(self):
        result = self.fit(path=self.leaky_relabelling(), target_column="churned")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "a_feature_leaks_the_target")
        self.assertTrue(result["nothing_was_fitted"])
        self.assertEqual(
            [row["column"] for row in result["leaking_columns"]], ["is_churned"]
        )
        self.assertIn("A - a feature whose values", result["check"])
        self.assertIn("drop_columns=['is_churned']", result["summary"])

    def test_check_b_catches_the_leak_check_a_cannot_see(self):
        path = self.leaky_oracle()
        result = self.fit(path=path, target_column="churned")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "a_feature_leaks_the_target")
        self.assertTrue(result["nothing_was_fitted"])
        self.assertEqual(
            [row["column"] for row in result["leaking_columns"]], ["risk_band"]
        )
        self.assertIn("B - one feature", result["check"])

        # And check A really is blind to it, so this is not two names for one
        # check: the six bands are more values than there are classes.
        rows = list(dataquality.iter_records(path))
        labels = [str(row["churned"]) for row in rows]
        self.assertEqual(
            classical._relabelling_leak(rows, ["risk_band"], labels, 2), []
        )

    def test_dropping_the_named_column_produces_a_real_fit(self):
        """The refusal names a door and the door opens."""
        path = self.leaky_relabelling()
        result = self.fit(
            path=path, target_column="churned", drop_columns=["is_churned"]
        )
        self.assertTrue(result["ok"], result.get("summary"))
        self.assertNotIn("is_churned", result["features"]["used"])
        self.assertGreater(
            result["score"]["correct"], result["trivial_baseline"]["correct"]
        )

    def test_there_is_no_argument_that_scores_anyway(self):
        """The door is dropping the column, and nothing else is offered.

        A `score_anyway` flag is exactly how a 99.8% that means nothing gets
        into a slide deck, so the schema must not grow one.
        """
        properties = REGISTRY.get(TOOL).schema["properties"]
        for forbidden in ("force", "ignore_leaks", "score_anyway", "skip_checks"):
            self.assertNotIn(forbidden, properties)
        self.assertIn("There is deliberately no flag that scores anyway",
                      REGISTRY.get(TOOL).schema["properties"]["drop_columns"]["description"])


@NEEDS_A_FITTER
class TheReplyDoesNotOverstateWhatItDidTest(TreeTestCase):
    """Two smaller places where a key said one thing and meant another."""

    def test_the_fraction_asked_for_is_the_one_the_caller_asked_for(self):
        """It reported the CLAMPED value under the caller's name.

        `holdout_fraction=0.9` and `holdout_fraction=2.0` both came back as
        `fraction_asked_for: 0.5`, and `-1.0` came back as `0.05` - silently, in
        a field whose name is a claim about the caller. Nothing pinned that key,
        so nothing noticed.
        """
        for asked, used in ((0.9, 0.5), (2.0, 0.5), (-1.0, 0.05)):
            result = self.fit(
                path=self.signal_file(), target_column="churned",
                holdout_fraction=asked,
            )
            self.assertTrue(result["ok"], result.get("summary"))
            split = result["split"]
            self.assertEqual(split["fraction_asked_for"], asked)
            self.assertEqual(split["fraction_used"], used)
            self.assertTrue(split["fraction_was_clamped"])
            self.assertIn(str(asked), split["fraction_how"])

    def test_a_fraction_inside_the_bounds_is_not_reported_as_clamped(self):
        result = self.fit(
            path=self.signal_file(), target_column="churned", holdout_fraction=0.3
        )
        self.assertEqual(result["split"]["fraction_asked_for"], 0.3)
        self.assertEqual(result["split"]["fraction_used"], 0.3)
        self.assertFalse(result["split"]["fraction_was_clamped"])

    def test_rows_no_model_could_have_won_are_in_the_headline(self):
        """A class only in the hold-out was named in `classes.says` and nowhere
        the reader looks. A score short by rows nobody could win read as a
        score."""
        rng = random.Random(53)
        # THE SPLIT IS THE CALLER'S, so which side the rare class lands on is
        # decided here rather than by a hash - a hashed split makes this test
        # skip about half the time, which is a test that proves nothing. The
        # two files share no row and no near-duplicate: `find_leakage` matches
        # on similarity, so the marker column keeps every row far apart.
        train = [
            {"a": round(rng.uniform(0, 100), 3), "b": rng.choice(["p", "q", "r"]),
             "marker": f"train row number {i} of four hundred",
             "label": "yes" if rng.random() > 0.5 else "no"}
            for i in range(400)
        ]
        holdout = [
            {"a": round(200 + i * 0.7, 3), "b": rng.choice(["p", "q", "r"]),
             "marker": f"held out sample {i} kept back on purpose",
             "label": "yes" if i % 2 else "no"}
            for i in range(80)
        ] + [
            {"a": round(900 + i * 0.5, 3), "b": "p",
             "marker": f"held out sample {80 + i} kept back on purpose",
             "label": "unheard_of"}
            for i in range(15)
        ]
        result = self.fit(
            path=self.jsonl_file("train.jsonl", train),
            holdout_path=self.jsonl_file("holdout.jsonl", holdout),
            target_column="label",
        )
        self.assertTrue(result["ok"], result.get("summary"))
        classes = result["classes"]
        self.assertEqual(classes["in_holdout_but_never_in_training_n"], 1)
        self.assertEqual(classes["unwinnable_holdout_rows"], 15)
        self.assertIn(
            "could not have been got right", classes["says"]
        )
        self.assertIn("never appears in the training rows", result["summary"])
        self.assertIn(
            str(classes["unwinnable_holdout_rows"]), result["summary"]
        )

    def test_a_date_in_the_file_makes_the_random_split_the_headline(self):
        """B3: time-ordered data, split by hash, inverts the verdict.

        Measured on this exact fixture: the tool's hashed split scored the tree
        116 of 150 (77%) against a trivial 70 of 150 (47%), p = 9.84e-08,
        *separates them at the conventional 0.05.* The same estimator on the
        same file, fitted on the first 75% and scored on the LAST 25% by hand,
        got 70 of 150 (47%). Thirty points of the tool's score are the split.
        Neither "time-ordered" nor "chronological" appeared in the reply, and
        the `date` column - the single strongest evidence the split was wrong -
        was silently dropped as *closer to an identifier than to a category*.
        """
        from datetime import datetime, timedelta

        rng = random.Random(3)
        rows = []
        for t in range(600):
            a = round(rng.uniform(0, 1), 4)
            rows.append([
                (datetime(2023, 1, 1) + timedelta(days=t)).strftime("%Y-%m-%d"),
                a,
                "up" if a + t / 600.0 > 1.0 else "down",
            ])
        result = self.fit(
            path=self.csv_file("series.csv", ["date", "a", "trend"], rows),
            target_column="trend",
        )
        self.assertTrue(result["ok"], result.get("summary"))
        # The date column is still dropped as a feature - a booster cannot bin
        # 450 strings - and it is no longer dropped in silence.
        self.assertIn("date", [d["column"] for d in result["features"]["dropped"]])
        found = result["split"]["date_columns"]
        self.assertEqual([row["column"] for row in found], ["date"])
        self.assertEqual(found[0]["format"], "%Y-%m-%d")
        self.assertIn("THE SPLIT IS RANDOM AND THIS FILE HAS A DATE IN IT",
                      result["summary"])
        self.assertIn("holdout_path", result["split"]["and_this_split_is_not_by_time"])

    def test_a_file_with_no_dates_claims_nothing_either_way(self):
        result = self.fit(path=self.signal_file(), target_column="churned")
        self.assertEqual(result["split"]["date_columns"], [])
        self.assertNotIn("THE SPLIT IS RANDOM AND THIS FILE HAS A DATE",
                         result["summary"])
        # And it does not claim the rows are independent, which it cannot know.
        self.assertIn("not proof they are not",
                      result["split"]["and_this_split_is_not_by_time"])

    def test_a_clean_holdout_says_nothing_about_unwinnable_rows(self):
        result = self.fit(path=self.signal_file(), target_column="churned")
        self.assertEqual(result["classes"]["in_holdout_but_never_in_training_n"], 0)
        self.assertEqual(result["classes"]["unwinnable_holdout_rows"], 0)
        self.assertNotIn("never appears in the training rows", result["summary"])


@NEEDS_A_FITTER
class ANumericIdentifierIsAnIdentifierTest(TreeTestCase):
    """Check C, and the asymmetry it exists to remove.

    The concept "this column is an identifier" was already in this module twice
    - a text column with more than `MAX_CATEGORIES` values is dropped as
    *closer to an identifier than to a category*, and a target with a different
    value in every row is refused as one - and a NUMERIC FEATURE got neither
    test.

    Measured before the fix, on the real tool: 400 rows, `customer_id` = 1..400,
    `churn` = (id <= 200). Scored 99 of 100 held-out rows, McNemar
    p = 2.4e-14, and the summary said it *separates them at the conventional
    0.05*. Check A cannot fire (400 distinct values, 2 classes); check B cannot
    (every held-out id is unseen, so it falls back); `leak_checks` reported both
    as run and found nothing. The identical column written as text - "C0001" -
    was dropped by the same tool in the same call.
    """

    def identifier_file(self, name: str = "ids.csv"):
        """`customer_id` decides `churn` and nothing else in the file does.

        The two noise columns are continuous so that dropping the identifier
        leaves a hold-out of distinct inputs to score on - what is being tested
        is that the score falls to nothing, not that the file becomes too thin.
        """
        rng = random.Random(29)
        return self.csv_file(
            name,
            ["customer_id", "region", "spend", "churn"],
            [
                [
                    i,
                    i % 7,
                    round(rng.uniform(0, 500), 3),
                    "yes" if i <= 200 else "no",
                ]
                for i in range(1, 401)
            ],
        )

    def test_a_numeric_counter_feature_is_refused_and_named(self):
        result = self.fit(path=self.identifier_file(), target_column="churn")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "a_feature_is_an_identifier")
        self.assertTrue(result["nothing_was_fitted"])
        self.assertIsNone(result["score"])
        self.assertEqual(
            [row["column"] for row in result["identifier_columns"]], ["customer_id"]
        )
        self.assertIn("a different whole number in every one", result["summary"])
        self.assertIn("drop_columns=['customer_id']", result["summary"])

    def test_the_door_opens_and_the_rest_of_the_file_is_worth_nothing(self):
        """The point of the refusal: what is left is the honest answer."""
        result = self.fit(
            path=self.identifier_file(),
            target_column="churn",
            drop_columns=["customer_id"],
        )
        self.assertTrue(result["ok"], result.get("summary"))
        self.assertNotIn("customer_id", result["features"]["used"])
        # Without the identifier there is no signal at all, which is what the
        # 99% was made of.
        self.assertFalse(result["comparison"]["separated"])

    def test_the_same_column_as_text_and_as_a_number_are_treated_alike(self):
        """The asymmetry, asserted from both sides in one test."""
        as_text = self.csv_file(
            "ids_text.csv",
            ["customer_id", "region", "churn"],
            [["C%04d" % i, i % 7, "yes" if i <= 200 else "no"] for i in range(1, 401)],
        )
        text_result = self.fit(path=as_text, target_column="churn")
        self.assertTrue(text_result["ok"], text_result.get("summary"))
        self.assertIn(
            "customer_id", [row["column"] for row in text_result["features"]["dropped"]]
        )
        number_result = self.fit(path=self.identifier_file(), target_column="churn")
        self.assertFalse(number_result["ok"])
        self.assertEqual(number_result["error"], "a_feature_is_an_identifier")

    def test_a_quantity_is_not_a_counter_even_when_every_value_differs(self):
        """`revenue`, all distinct, all fractional. The target check already
        drew this line and check C draws the same one."""
        rows = [
            [round(100 + i * 0.37, 2), i % 5, "yes" if i % 2 else "no"]
            for i in range(400)
        ]
        result = self.fit(
            path=self.csv_file("money.csv", ["revenue", "region", "label"], rows),
            target_column="label",
        )
        self.assertTrue(result["ok"], result.get("summary"))
        self.assertIn("revenue", result["features"]["used"])

    def test_a_whole_number_that_repeats_is_a_count_and_is_kept(self):
        rng = random.Random(31)
        rows = [
            [rng.randint(0, 50), round(rng.uniform(0, 9), 3), rng.choice(["yes", "no"])]
            for _ in range(400)
        ]
        result = self.fit(
            path=self.csv_file("counts.csv", ["clicks", "seconds", "label"], rows),
            target_column="label",
        )
        self.assertTrue(result["ok"], result.get("summary"))
        self.assertIn("clicks", result["features"]["used"])

    def test_the_check_is_declared_in_the_reply_of_a_run_that_passed_it(self):
        result = self.fit(path=self.signal_file(), target_column="churned")
        self.assertTrue(result["ok"], result.get("summary"))
        checks = {row["check"]: row for row in result["leak_checks"]}
        self.assertIn("C - the numeric identifier", checks)
        self.assertEqual(checks["C - the numeric identifier"]["found"], 0)
        self.assertGreater(
            checks["C - the numeric identifier"]["columns_checked"], 0
        )


@NEEDS_A_FITTER
class TheOtherRefusalsAreRefusalsTest(TreeTestCase):
    """Every remaining way this tool declines, and they all leave the disk alone."""

    def refuse(self, **arguments) -> dict:
        result = self.fit(**arguments)
        self.assertFalse(result["ok"], result.get("summary"))
        self.assertTrue(result["nothing_was_fitted"])
        return result

    def test_a_target_of_one_value(self):
        rows = [[i, "no"] for i in range(300)]
        result = self.refuse(
            path=self.csv_file("one.csv", ["x", "label"], rows), target_column="label"
        )
        self.assertEqual(result["error"], "one_class")

    def test_a_target_that_is_an_identifier(self):
        rng = random.Random(3)
        rows = [[i, rng.randint(0, 9)] for i in range(300)]
        result = self.refuse(
            path=self.csv_file("ids.csv", ["customer_id", "x"], rows),
            target_column="customer_id",
        )
        self.assertEqual(result["error"], "target_is_an_identifier")

    def test_a_continuous_target_is_not_called_an_identifier(self):
        """The two look alike from the row count and are not the same defect.

        A price with a value per row is not an id, and a reply that called it
        one would be a wrong diagnosis inside a refusal to give a wrong number.
        """
        rng = random.Random(4)
        rows = [[round(rng.uniform(0, 1000), 3), rng.randint(0, 9)] for _ in range(300)]
        result = self.refuse(
            path=self.csv_file("rev.csv", ["revenue", "x"], rows),
            target_column="revenue",
        )
        self.assertEqual(result["error"], "target_is_continuous")
        self.assertIn("regression problem", result["summary"])
        self.assertIn("Wilson interval", result["summary"])

    def test_a_free_text_target_with_too_many_values(self):
        rng = random.Random(5)
        rows = [[f"note number {i}", rng.randint(0, 9)] for i in range(300)]
        result = self.refuse(
            path=self.csv_file("notes.csv", ["note", "x"], rows),
            target_column="note",
        )
        self.assertIn(result["error"], ("too_many_labels", "target_is_an_identifier"))

    def test_a_two_class_target_of_fractions_is_still_a_classification(self):
        """0.5 and 1.5 are two labels, not a continuum. The band is the count."""
        rng = random.Random(6)
        rows = [
            [round(rng.uniform(0, 100), 3), rng.choice([0.5, 1.5])] for _ in range(400)
        ]
        result = self.fit(
            path=self.csv_file("halves.csv", ["x", "label"], rows),
            target_column="label",
        )
        self.assertTrue(result["ok"], result.get("summary"))
        self.assertEqual(result["classes"]["n"], 2)

    def test_too_few_rows_to_fit_on(self):
        rng = random.Random(7)
        rows = [[rng.random(), rng.choice(["a", "b"])] for _ in range(60)]
        result = self.refuse(
            path=self.csv_file("tiny.csv", ["x", "label"], rows), target_column="label"
        )
        self.assertEqual(result["error"], "too_few_rows_to_fit_on")
        self.assertIn(str(dataquality.MIN_ROWS_FOR_TRAINING), result["summary"])

    def test_a_hold_out_that_came_out_all_one_class(self):
        """Supplied as a file, because that is how it actually happens.

        A hold-out with one label in it gives the trivial answer 100%, so
        nothing a model did could be told from always saying that word. The
        carved path cannot easily produce this - the hash draw is independent of
        the label - and a caller's own split absolutely can.
        """
        rng = random.Random(9)
        train = [
            {"x": rng.random(), "label": "yes" if i % 2 else "no"} for i in range(400)
        ]
        holdout = [{"x": rng.random(), "label": "yes"} for _ in range(200)]
        result = self.refuse(
            path=self.jsonl_file("t.jsonl", train),
            holdout_path=self.jsonl_file("h.jsonl", holdout),
            target_column="label",
        )
        self.assertEqual(result["error"], "hold_out_is_one_class")
        self.assertIn("scores 100%", result["summary"])

    def test_no_column_to_fit_on(self):
        rows = [["yes" if i % 2 else "no"] for i in range(300)]
        result = self.refuse(
            path=self.csv_file("only.csv", ["label"], rows), target_column="label"
        )
        self.assertEqual(result["error"], "no_features")

    def test_a_column_that_is_not_there(self):
        result = self.refuse(path=self.signal_file(), target_column="nope")
        self.assertEqual(result["error"], "no_such_column")
        self.assertIn("tenure_months", result["summary"])

    def test_a_file_that_is_not_a_table(self):
        path = self.root / "picture.csv"
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        result = self.refuse(path=str(path), target_column="label")
        self.assertEqual(result["error"], "unreadable")

    def test_more_rows_than_the_cap_refuses_rather_than_truncating(self):
        result = self.refuse(
            path=self.signal_file(), target_column="churned", max_rows=100
        )
        self.assertEqual(result["error"], "more_rows_than_the_cap")
        self.assertIn("not a sample", result["summary"])

    def test_a_matrix_too_large_to_build_refuses_rather_than_truncating(self):
        """Rows and columns are each bounded; their product was not.

        A refusal that names both doors beats an out-of-memory error that names
        neither, and truncating either side would be a different experiment
        reported as this one.
        """
        rng = random.Random(8)
        header = [f"c{i}" for i in range(20)] + ["label"]
        rows = [
            [round(rng.uniform(0, 1), 4) for _ in range(20)]
            + [rng.choice(["a", "b"])]
            for _ in range(400)
        ]
        path = self.csv_file("wide.csv", header, rows)
        with mock.patch.object(classical, "MAX_CELLS", 100):
            result = self.refuse(path=path, target_column="label")
        self.assertEqual(result["error"], "too_much_to_fit_at_once")
        self.assertIn("feature_columns", result["summary"])
        self.assertIn("max_rows", result["summary"])

        # And it is a real bound rather than a permanently closed door: the same
        # file fits when the budget is the shipped one.
        self.assertTrue(
            self.fit(path=path, target_column="label")["ok"],
            "the file only fitted because the budget was patched",
        )

    def test_a_training_slice_with_one_class_in_it(self):
        """Fitting a classifier on one class teaches it one answer.

        The whole file has two, so this is the split having put every minority
        row on the hold-out side - which a caller's own split can easily do and
        `sklearn` answers with a bare ValueError.
        """
        rng = random.Random(10)
        train = [{"x": rng.random(), "label": "no"} for _ in range(400)]
        holdout = [
            {"x": rng.random(), "label": "yes" if i % 2 else "no"} for i in range(200)
        ]
        result = self.refuse(
            path=self.jsonl_file("t.jsonl", train),
            holdout_path=self.jsonl_file("h.jsonl", holdout),
            target_column="label",
        )
        self.assertEqual(result["error"], "training_rows_are_one_class")
        self.assertIn("came from you", result["summary"])

    def test_without_sklearn_it_says_so_and_does_not_crash(self):
        with mock.patch.object(
            classical, "installed", side_effect=lambda name: name not in ("sklearn",)
        ):
            result = self.refuse(
                path=self.signal_file(), target_column="churned"
            )
        self.assertEqual(result["error"], "no_estimator")
        self.assertIn("scikit-learn", result["summary"])
        self.assertIn("pyproject.toml", result["summary"])

    def test_every_refusal_has_the_shape_of_a_success(self):
        """A caller that special-cases a refusal is one that can forget to."""
        rows = [[i, "no"] for i in range(300)]
        refusal = self.fit(
            path=self.csv_file("flat.csv", ["x", "label"], rows), target_column="label"
        )
        success = self.fit(path=self.signal_file(), target_column="churned")
        for key in (
            "ok",
            "error",
            "score",
            "trivial_baseline",
            "best_constant_on_the_holdout",
            "comparison",
            "resolution",
            "measured",
            "not_measured",
            "decides_nothing",
            "not_tried",
            "summary",
        ):
            self.assertIn(key, refusal, key)
            self.assertIn(key, success, key)
        for key in ("score", "trivial_baseline", "comparison"):
            self.assertIsNone(refusal[key], key)
        self.assertEqual(refusal["resolution"]["n"], 0)
        self.assertEqual(refusal["measured"], [])


# ---------------------------------------------------------------------------
# 6. The five gates are untouched. The one the brief asked to be proved.


class TheToolCannotStampAnythingTest(unittest.TestCase):
    """The declarations, which hold on every machine including one with no fitter."""

    def test_the_tool_declares_no_measurement_and_no_write(self):
        spec = REGISTRY.get(TOOL)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.measures, ())
        self.assertEqual(spec.bounds, ())
        self.assertEqual(spec.writes, ())
        self.assertFalse(spec.wants_instrument, "it cannot stamp and does not ask")

    def test_no_argument_of_this_tool_names_a_gate_or_a_provenance(self):
        """Wall 2 and wall 4, at this tool's own door."""
        properties = REGISTRY.get(TOOL).schema["properties"]
        for name in properties:
            self.assertNotIn(name.lower(), RESERVED_ARGUMENTS, name)
        for claimed in REGISTRY.get(TOOL).writes:
            self.assertNotIn(str(claimed).lower(), RESERVED_WRITES, claimed)


@NEEDS_A_FITTER
class TheFiveGatesAreUntouchedTest(TreeTestCase):
    """The same claim, driven against the live engine over a real thread.

    THE SITUATION IS BUILT SO THAT G1 IS THE GATE IN QUESTION AND IS OPEN TO
    BEING MOVED. A thread where `eval_size_n` has been MEASURED, so G0 is PASSED
    and the walk reaches G1, and where G1 is FAILED because nobody has measured
    a baseline. That is the exact state a tree's accuracy would flatter, and
    `test_a_tool_that_did_stamp_would_move_it` shows the move really is
    available: a stand-in tool that declares
    `measures=("baseline_measured", "baseline_score", "trivial_baseline_score")`
    flips G1 to PASSED and changes the verdict. So the equality asserted in the
    test above it is a property of `fit_a_tree_model` and not of a ledger that
    could not have moved anyway.
    """

    def situation(self) -> tuple[int, dict]:
        """A thread with G0 open, G1 failed, and a sheet to walk over.

        The fixture's facts are unwrapped to plain values on the way in, because
        `evidence.assemble_facts` decides an origin from the ACTOR and would
        otherwise be handed one that already had an origin on it. Which is the
        point: what opens G0 here is `eval_size_n` arriving MEASURED through an
        instrument, exactly as it does when `measure_eval_set` runs.
        """
        thread_id = int(support.conversations(1)[0]["id"])
        self.stand_in("measure_the_eval_set", {"eval_size_n": 120}).call(
            "measure_the_eval_set", {}, actor="model", thread_id=thread_id
        )
        sheet = {
            name: (value.value if isinstance(value, diagnosis.Fact) else value)
            for name, value in fixtures.REACHING["NO_TRAIN__CACHE_AND_ROUTE"].items()
        }
        return thread_id, sheet

    def stand_in(
        self, name: str, facts: dict, provides: tuple = ("data.dataset.profile",)
    ):
        """A throwaway tool on a registry of its own that stamps `facts`.

        On its OWN `Registry` rather than the product's, so nothing here can
        leave a tool registered behind it - the real registry is a module-level
        singleton and `clear()` on it would take the other thirty-eight with it.

        `provides` is a parameter because wall 9 reads it. A fact names the
        capabilities that may measure it, so a stand-in for a BASELINE
        instrument cannot claim to profile a dataset - see the call below.
        """
        registry = Registry()

        @registry.tool(
            name,
            description="a stand-in for a tool that measures something",
            schema={"type": "object", "properties": {}},
            measures=tuple(facts),
            provides=provides,
            label="Stand in",
            group="Data",
            verb="stand in for a measurement",
        )
        def handler(*, instrument: Instrument):
            for fact, value in facts.items():
                instrument.measured(fact, value, how="a stand-in, in a test")
            return {"ok": True}

        return registry

    def walk(self, thread_id: int, sheet: dict):
        assembled, _ = evidence.assemble_facts(thread_id, sheet, "user")
        return diagnosis.diagnose(assembled)

    def test_the_situation_is_the_one_a_tree_score_would_flatter(self):
        """The setup itself, asserted, so the two tests below cannot be vacuous."""
        thread_id, sheet = self.situation()
        walked = self.walk(thread_id, sheet)
        self.assertEqual(walked.gate_ledger["G0_EVAL_SET"]["status"], "PASSED")
        self.assertEqual(walked.gate_ledger["G1_BASELINE_MEASURED"]["status"], "FAILED")

    def test_running_it_changes_no_gate_in_the_ledger(self):
        """The proof the brief asked for, driven rather than declared."""
        thread_id, sheet = self.situation()
        before = self.walk(thread_id, sheet)

        result = REGISTRY.call(
            TOOL,
            {"path": self.signal_file(), "target_column": "churned"},
            actor="model",
            thread_id=thread_id,
        )
        self.assertTrue(result["ok"], result.get("summary"))

        # THE LEDGER FIRST, so a failure here says which gate moved rather than
        # printing the whole reply at somebody.
        after = self.walk(thread_id, sheet)
        self.assertEqual(
            after.gate_ledger["G1_BASELINE_MEASURED"]["status"],
            "FAILED",
            "a tree fitted to a spreadsheet opened the baseline gate",
        )
        self.assertEqual(before.gate_ledger, after.gate_ledger)
        self.assertEqual(before.outcome, after.outcome)
        self.assertEqual(result["measured"], [])
        self.assertEqual(
            sorted(row["fact"] for row in result.get("measured_facts") or []),
            [],
            "the tool stamped a fact",
        )

    def test_a_tool_that_did_stamp_would_move_it(self):
        """The counterfactual, so the equality above means something.

        This is the defect `measures=()` is chosen against, made to happen once
        under laboratory conditions: the same thread, the same sheet, and the
        three facts a tree's accuracy is closest to. G1 opens and the verdict
        changes. That is what would be shipped if this tool declared them.
        """
        thread_id, sheet = self.situation()
        before = self.walk(thread_id, sheet)

        self.stand_in(
            "stamp_a_baseline",
            {
                "baseline_measured": True,
                "baseline_score": 0.62,
                "trivial_baseline_score": 0.54,
            },
            # All three facts declare `measured_by: [measurement.baseline.score,
            # measurement.eval.run]`, so this is the capability a real baseline
            # instrument would hold. The counterfactual is "a tool that MAY
            # stamp these did", and after wall 9 that has to be said out loud.
            provides=("measurement.baseline.score",),
        ).call("stamp_a_baseline", {}, actor="model", thread_id=thread_id)

        after = self.walk(thread_id, sheet)
        self.assertEqual(
            after.gate_ledger["G1_BASELINE_MEASURED"]["status"], "PASSED"
        )
        self.assertNotEqual(before.outcome, after.outcome)

    def test_it_records_nothing_in_the_thread_s_evidence(self):
        """Nothing reaches the ledger, so nothing can open a gate later either."""
        thread_id = int(support.conversations(1)[0]["id"])
        empty, _ = evidence.assemble_facts(thread_id, {}, "user")
        REGISTRY.call(
            TOOL,
            {"path": self.signal_file(), "target_column": "churned"},
            actor="model",
            thread_id=thread_id,
        )
        after, _ = evidence.assemble_facts(thread_id, {}, "user")
        self.assertEqual(sorted(empty), sorted(after))

    def test_the_reply_says_why_it_is_not_a_baseline(self):
        result = self.fit(path=self.signal_file(), target_column="churned")
        self.assertIn("baseline_score", result["not_measured"])
        self.assertIn("measure_baseline", result["not_measured"])
        self.assertIn("hparam_search_trials", result["decides_nothing"])
        self.assertIn(
            "tabular_rows",
            result["rows"]["is"],
            "a row count off a capped read must say it is not the fact",
        )


# ---------------------------------------------------------------------------
# 7. What it did not try, read off the engine.


@NEEDS_A_FITTER
class ItNamesWhatItDidNotDoAndReadsItRatherThanRememberingItTest(TreeTestCase):
    def test_the_libraries_come_from_the_spec(self):
        named = classical.libraries_the_engine_names()
        node = diagnosis.default_spec().node_index["S8_TABULAR_STANDARD"]
        self.assertEqual(named, [str(lib) for lib in node["method"]["libs"]])
        self.assertTrue(named, "the spec named no libraries at all")

    def spec_with(self, **replacements):
        """The real spec with one field swapped, handed back by `default_spec`.

        `Spec` is a dataclass instance and not a namespace, so the honest way to
        move the engine is to build a different one and let the reader come and
        get it - which is exactly the call path the product uses.
        """
        return mock.patch(
            "app.diagnosis.default_spec",
            return_value=dataclasses.replace(diagnosis.default_spec(), **replacements),
        )

    def test_a_fourth_library_in_the_spec_appears_in_the_reply(self):
        """MOVE THE ENGINE, not the assertion. This is what proves it is read."""
        real = diagnosis.default_spec()
        node = dict(real.node_index["S8_TABULAR_STANDARD"])
        node["method"] = dict(node["method"])
        node["method"]["libs"] = list(node["method"]["libs"]) + ["Notaboost"]
        index = dict(real.node_index)
        index["S8_TABULAR_STANDARD"] = node
        with self.spec_with(node_index=index):
            result = self.fit(path=self.signal_file(), target_column="churned")
        machine = result["not_tried"]["machine"]
        self.assertIn("Notaboost", machine["engine_named"])
        self.assertIn("Notaboost", machine["missing"])
        self.assertIn("Notaboost", result["summary"])

    def test_the_absence_is_measured_and_not_remembered(self):
        """`find_spec` decides, so a machine that HAS one stops being told it does not."""
        result = self.fit(path=self.signal_file(), target_column="churned")
        self.assertIn("find_spec", result["not_tried"]["machine"]["how"])
        with mock.patch.object(classical, "installed", return_value=True):
            everything = classical.available()
        self.assertEqual(everything["missing"], [])

    def test_the_trial_count_comes_from_the_gate(self):
        self.assertEqual(classical.trials_the_gate_asks_for(), 50)
        gate = diagnosis.default_spec().gates["G2_PROMPT_EXHAUSTED"]
        rows = [
            row for row in gate["passes_when"]
            if row["method_class"] == "classical_deep"
        ]
        self.assertEqual(len(rows), 1)
        self.assertIn(
            f"hparam_search_trials >= {classical.trials_the_gate_asks_for()}",
            rows[0]["requires"],
        )

    def test_moving_the_gate_moves_the_sentence(self):
        real = diagnosis.default_spec()
        gates = dict(real.gates)
        gate = dict(gates["G2_PROMPT_EXHAUSTED"])
        gate["passes_when"] = [
            dict(row, requires="hparam_search_trials >= 900")
            if row.get("method_class") == "classical_deep"
            else row
            for row in gate["passes_when"]
        ]
        gates["G2_PROMPT_EXHAUSTED"] = gate
        with self.spec_with(gates=gates):
            block = classical.not_tried_block()
        text = json.dumps(block)
        self.assertIn("hparam_search_trials >= 900", text)
        self.assertIn("899 more", text)

    def test_every_reply_names_the_levers_including_the_refusals(self):
        rows = [[i, "no"] for i in range(300)]
        refusal = self.fit(
            path=self.csv_file("flat.csv", ["x", "label"], rows), target_column="label"
        )
        for payload in (
            refusal,
            self.fit(path=self.signal_file(), target_column="churned"),
        ):
            text = json.dumps(payload["not_tried"])
            self.assertIn("hyperparameter search", text)
            self.assertIn("feature engineering", text)
            self.assertIn("cross-validation", text)
            self.assertIn("temporal leak", text)

    def test_it_says_the_leak_checks_cannot_see_everything(self):
        """And the list must be the WHOLE list, which it was not.

        It named a temporal leak and a two-column leak. The largest one - a leak
        carried by ONE column with more distinct values than the checks can
        tabulate - was not in it, and is the regime real tabular leaks live in.
        Measured by sweeping only the leaking column's width with the classes
        fixed at two: refused at 2 distinct values, and at 50, 51, 100 and 200 a
        column that fully determines the target was fitted and scored EVERY
        held-out row right, p between 2.7e-23 and 6.9e-18, with both checks
        reporting nothing found. The check stops working exactly where the leak
        stops being obvious to a person, and the sentence that lists the blind
        spots did not say so.
        """
        result = self.fit(path=self.signal_file(), target_column="churned")
        unseen = result["not_tried"]["and_the_leak_nothing_here_can_see"]
        self.assertIn("temporal leak", unseen)
        self.assertIn("two columns", unseen)
        self.assertIn("more distinct values than the checks can tabulate", unseen)
        self.assertIn("100%", unseen)

    def test_the_high_cardinality_single_column_leak_really_does_get_through(self):
        """The blind spot, driven - so the sentence above is a reading.

        `band` is `risk_score >= 200` and `risk_score` has 400 distinct values.
        Check A cannot fire: 400 distinct values against 2 classes. Check B
        cannot: every held-out `risk_score` is unseen in training, so it falls
        back. Check C cannot: `band` repeats, and `risk_score` is the target's
        source rather than a feature here.
        """
        rng = random.Random(41)
        rows = [
            [round(i + rng.random(), 4), rng.choice(["p", "q"]), "high" if i >= 200 else "low"]
            for i in range(400)
        ]
        result = self.fit(
            path=self.csv_file("band.csv", ["risk_score", "noise", "band"], rows),
            target_column="band",
        )
        self.assertTrue(result["ok"], result.get("summary"))
        self.assertGreaterEqual(result["score"]["accuracy"], 0.95)
        self.assertTrue(result["comparison"]["separated"])
        # No check caught it, and the reply says this is the case it cannot see.
        self.assertEqual(
            sum(check["found"] for check in result["leak_checks"]), 0
        )
        self.assertIn(
            "more distinct values than the checks can tabulate",
            result["not_tried"]["and_the_leak_nothing_here_can_see"],
        )

    def test_a_holdout_of_repeated_inputs_says_what_the_inputs_resolve(self):
        """B4: the interval over rows overstates what repeated rows support.

        Measured: 160 inputs each repeated ten times gave a hold-out of 400 rows
        holding 40 distinct inputs. Over rows the paired test gave p = 7.3e-08
        and `separated: True`; over the 40 independent inputs it gave p = 0.134
        and `separated: False`, with an interval 3.04 times as wide. Both
        numbers were computable from the payload and only one was reported.
        """
        rng = random.Random(5)
        rows = []
        for _ in range(160):
            a = round(rng.uniform(0, 100), 3)
            b = round(rng.uniform(0, 100), 3)
            c = rng.choice(["x", "y", "z"])
            label = "yes" if (a + b > 100) != (rng.random() < 0.25) else "no"
            rows.extend([[a, b, c, label]] * 10)
        result = self.fit(
            path=self.csv_file("repeats.csv", ["a", "b", "c", "label"], rows),
            target_column="label",
        )
        self.assertTrue(result["ok"], result.get("summary"))
        over_rows = result["resolution"]
        over_inputs = result["resolution_over_distinct_inputs"]
        self.assertTrue(over_inputs["rows_repeat"])
        self.assertLess(over_inputs["n"], over_rows["n"])
        self.assertGreater(
            over_inputs["half_width_points"], over_rows["half_width_points"]
        )
        # The two verdicts really do differ here, which is the finding.
        self.assertTrue(result["comparison"]["separated"])
        self.assertFalse(over_inputs["separated"])
        # And the sentence a person reads carries both.
        self.assertIn("distinct inputs", result["summary"])
        self.assertIn("over more units than there are independent", result["summary"])

    def test_a_holdout_with_no_repeats_says_so_and_claims_nothing(self):
        result = self.fit(path=self.signal_file(), target_column="churned")
        over_inputs = result["resolution_over_distinct_inputs"]
        self.assertFalse(over_inputs["rows_repeat"])
        self.assertEqual(over_inputs["n"], result["score"]["of"])
        self.assertIn("nothing here is overstated", over_inputs["says"])
        self.assertNotIn("over more units", result["summary"])


# ---------------------------------------------------------------------------
# 8. No new dependency, asserted against the file's own syntax tree.


class NoNewDependencyTest(unittest.TestCase):
    MODULE = Path(__file__).resolve().parents[1] / "app" / "tools" / "classical.py"

    def test_sklearn_and_numpy_are_never_imported_at_module_level(self):
        """A module-level import here makes sklearn a dependency of the product.

        `pyproject.toml` declares four packages and sklearn is not one of them,
        so `import app.tools` on a fresh install would raise - taking every
        other tool with it - if this import moved out of the handler.
        """
        tree = ast.parse(self.MODULE.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0], ("sklearn", "numpy"))
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn(
                    (node.module or "").split(".")[0], ("sklearn", "numpy")
                )

    def test_the_declared_dependencies_did_not_change(self):
        text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
        block = text.split("dependencies = [", 1)[1].split("]", 1)[0]
        declared = sorted(
            line.strip().strip('",').split(">=")[0].split("==")[0]
            for line in block.splitlines()
            if line.strip().startswith('"')
        )
        # EXACT, NOT "sklearn IS NOT IN IT", because the subject of this case is
        # that fitting a tree added nothing - and a list that only ever gets
        # checked for two names would not notice a third arriving.
        #
        # 2026-08-27: python-multipart joined it, and it was not a new
        # dependency in the sense this case is about. It was already imported at
        # import time by `POST /ui/intake`'s Form(...) fields and simply never
        # declared, so `import app.main` raised on any clean interpreter.
        #
        # 2026-08-28: AND IT LEFT AGAIN, which is the same case working in the
        # other direction. `docs/THE_PLAN.md` V.3 A9 retired that form - the
        # last route in the product that took form fields - so the only reason
        # the line existed was gone. `tests/test_what_this_package_imports_it_
        # declares.py` is the general property and now checks BOTH directions:
        # the dependency is undeclared AND nothing under `app/` has grown a
        # `Form(`, `File(` or `UploadFile` behind its back.
        self.assertEqual(declared, ["fastapi", "markdown", "pyyaml", "uvicorn"])
        for absent in ("scikit-learn", "sklearn", "numpy"):
            self.assertNotIn(absent, declared)

    def test_the_tool_registers_even_where_the_libraries_are_missing(self):
        """Registration must not depend on what is installed."""
        with mock.patch.object(classical, "installed", return_value=False):
            self.assertIn(TOOL, REGISTRY)
            self.assertFalse(classical.available()["sklearn"])


# ---------------------------------------------------------------------------
# The control face, which is the other half of every tool in this harness.


class ItIsAControlAsWellAsAToolTest(unittest.TestCase):
    def test_it_is_in_the_data_group_with_a_verb_a_person_can_read(self):
        control = next(row for row in REGISTRY.controls() if row["name"] == TOOL)
        self.assertEqual(control["group"], "Data")
        self.assertFalse(control["needs_approval"], "it writes nothing")
        self.assertEqual(control["measures"], [])
        self.assertEqual(control["writes"], [])

    def test_the_verb_states_no_rule_the_instruction_set_already_states(self):
        verb = REGISTRY.get(TOOL).control.verb.lower()
        self.assertNotIn("gate", verb)
        self.assertNotIn("recommend", verb)

    def test_the_required_arguments_are_the_two_nothing_can_guess(self):
        schema = REGISTRY.get(TOOL).schema
        self.assertEqual(sorted(schema["required"]), ["path", "target_column"])
        self.assertIn("nothing here guesses a target",
                      schema["properties"]["target_column"]["description"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
