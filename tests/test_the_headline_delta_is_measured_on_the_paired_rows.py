"""The comparison card's big number, and the evidence printed underneath it.

THE DEFECT THIS FILE EXISTS FOR, CONSTRUCTED BEFORE IT WAS FIXED. `compare`
headlined the difference of two AGGREGATE scores - each run's own correct-count
over its own graded rows - while `improved`, `regressed` and `p_value` beneath
it were paired over the intersection. When the two runs graded different rows
those are two measurements of two different sets, and they can point in opposite
directions. Measured, on this file's own fixtures, against the shipped code:

    run_eval(sample=30)  -> 24 of 30 rows right, score 80.0%
    run_eval(sample=100) -> 30 of 100 rows right, score 30.0%
    compare()            -> delta -50.0%, resolved, "a real difference on this
                            eval set", above "6 improved, 0 regressed, p=0.0312"

The new run was the same or better on every row both runs graded. The card said
it was fifty points worse, in the flattering-to-nobody direction here but in the
FLATTERING direction on the path the bench recommends: a challenger holding ten
exemplar rows out - which `NO_TRAIN__FEW_SHOT` tells the user to do - reported
+12.0 points where the honest paired difference was +4.0. Threefold, upward,
arriving exactly when the user does the recommended thing.

`eval_fingerprint` could not catch it and was never the instrument for it: it
hashes every eligible row of the FILE, so it is identical for two runs at
different `sample` sizes, which is correct - they are the same eval set. Which
rows a run GRADED is on disk in `eval_results`, and that is what `compare` now
reads.

## WHAT EACH CLASS HERE IS FOR

`TheHeadlineCannotContradictTheEvidenceTest` is the defect itself, and its
central assertion is structural rather than numeric: `delta` must be identically
`(improved - regressed) / paired_rows`. A card whose headline disagrees with its
own strip is then not a bug to be noticed, it is arithmetic that cannot happen.

`TheFewShotPathIsHonestTest` is the same defect on the recommended path.

`TheOppositeFailureIsAsBadTest` is the control this repository's own methodology
demands: a bench that refuses everything measures nothing. Two runs over
genuinely the same rows must still compare, must give the number they always
gave, and a real difference must still come back resolved.

`TheRefusalsTest` keeps the two refusals honest - a genuinely different eval set
is still two facts and not a delta, and two runs with no row in common are now
refused instead of being reported as agreeing on zero rows.

MUTATION-CHECKED. Every assertion class here was run against `HEAD`'s
`app/tools/evals.py` before the fix; the failures are recorded in the summary of
the run that added this file. A test that passes against the broken code
certifies nothing.

Nothing here touches a network: `IndexedModel` answers from the row index, so
every number asserted is arithmetic over a file this module wrote.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from app.providers import Delta, store as provider_store
from app.tools import REGISTRY, evals
from app.tools.evidence import MODEL

import support


LABELS = ("yes", "no", "maybe", "never", "always")


def eval_file(root: Path, rows: int, name: str) -> Path:
    """`rows` questions with a five-label answer column, in equal proportion."""
    path = Path(root) / name
    path.write_text(
        "\n".join(
            json.dumps({"q": f"q{i}", "a": LABELS[i % len(LABELS)]})
            for i in range(rows)
        ),
        encoding="utf-8",
    )
    return path


class IndexedModel:
    """Right on exactly the row indexes it is handed, wrong on every other.

    Deliberately blunter than the bench's other fixture model: the point of
    every construction below is WHICH ROWS were right, so the model is a set of
    row indexes and nothing else. A wrong answer is a different member of the
    label set, so it buckets and never trips the refusal rules.
    """

    def __init__(self, right) -> None:
        self.right = set(right)
        self.asked: list[str] = []

    def stream(self, conversation, offered=None, *, secret=None):
        question = conversation[-1]["content"]
        self.asked.append(question)
        index = int(re.sub(r"\D", "", str(question)) or 0)
        if index in self.right:
            yield Delta(kind="text", text=LABELS[index % len(LABELS)])
        else:
            yield Delta(kind="text", text=LABELS[(index + 1) % len(LABELS)])


class PairedDeltaTest(unittest.TestCase):
    """Sandbox, one conversation, one scripted local connection."""

    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.thread = support.conversations(1)[0]["id"]
        row = provider_store.create(
            "Scripted", "http://127.0.0.1:11434", "scripted", "ollama"
        )
        provider_store.set_active(row["id"])

    def connect(self, right):
        model = IndexedModel(right)
        original = evals.build
        evals.build = lambda adapter, base_url, name: model
        self.addCleanup(lambda: setattr(evals, "build", original))
        return model

    def graded(self, path, right, **arguments):
        """One complete eval run over `path` by a model right on `right`."""
        self.connect(right)
        payload = {
            "eval_path": str(path),
            "input_field": "q",
            "expected_field": "a",
        }
        payload.update(arguments)
        report = REGISTRY.call(
            "run_eval", payload, actor=MODEL, thread_id=self.thread
        )
        self.assertTrue(report.get("ok"), report.get("detail") or report.get("summary"))
        self.assertTrue(report["complete"], report["summary"])
        return report

    def compare(self, after, before):
        return REGISTRY.call(
            "read_eval_results",
            {"run_id": after["run_id"], "against": before["run_id"]},
            actor=MODEL,
            thread_id=self.thread,
        )

    # -- the two constructions the module docstring quotes -------------------

    def two_sample_sizes(self):
        """The shipped card: sample=30 at 80%, then sample=100 at 30%.

        The second run is the same or better on every one of the thirty rows the
        first graded - six of them strictly better - and worse only on rows the
        first run never saw.
        """
        path = eval_file(self.root, 100, "hundred.jsonl")
        before = self.graded(path, range(0, 24), sample=30)
        after = self.graded(path, range(0, 30), sample=100, prompt="Try harder.")
        return before, after

    def fewshot(self):
        """The recommended path: ten exemplars held out of the challenger only.

        The champion grades rows 0-59 and fails rows 0-9, which is where
        `NO_TRAIN__FEW_SHOT` says exemplars come from. The challenger holds those
        ten out, so its aggregate is over a set the champion's ten worst rows are
        missing from - which is what inflates the aggregate difference.
        """
        path = eval_file(self.root, 60, "sixty.jsonl")
        champion = self.graded(path, range(10, 34), sample=60)
        challenger = self.graded(
            path,
            range(10, 36),
            sample=50,
            hold_out=list(range(10)),
            prompt="Here are examples.",
        )
        return champion, challenger


# ---------------------------------------------------------------------------


class TheHeadlineCannotContradictTheEvidenceTest(PairedDeltaTest):
    """A card reading -50% above "6 improved, 0 regressed" is the product lying
    with true components."""

    def test_the_card_that_shipped_is_the_wrong_way_round(self):
        """THE TEST THERE WAS NONE OF: two runs at different sample sizes.

        No test in this suite compared two runs whose sample sizes differed,
        which is why a sign-flipped headline shipped. Against the code before the
        fix this asserts `delta == +0.2` and receives `-0.5`.
        """
        before, after = self.two_sample_sizes()
        self.assertEqual(before["graded"], 30)
        self.assertEqual(after["graded"], 100)
        self.assertAlmostEqual(before["score"], 24 / 30)
        self.assertAlmostEqual(after["score"], 30 / 100)
        self.assertEqual(
            before["eval_fingerprint"],
            after["eval_fingerprint"],
            "one file, two sample sizes: this is one eval set",
        )

        verdict = self.compare(after, before)
        self.assertTrue(verdict["ok"], verdict.get("detail"))
        self.assertEqual(verdict["paired_rows"], 30)
        self.assertEqual(verdict["improved"], 6)
        self.assertEqual(verdict["regressed"], 0)
        self.assertAlmostEqual(verdict["delta"], 6 / 30)
        self.assertGreater(
            verdict["delta"], 0, "the new run was better on every row both graded"
        )
        self.assertTrue(verdict["resolved"])
        self.assertIn("+20.0%", verdict["says"])
        self.assertNotIn("-50.0% on", verdict["says"])

    def test_the_delta_is_identically_the_strip_over_its_own_width(self):
        """The structural guarantee, over four shapes of comparison.

        `delta * paired_rows == improved - regressed`, exactly. This is what
        makes the defect unreachable rather than merely fixed: any future change
        that computes the headline from anything other than the rows McNemar
        tested breaks this before it reaches a card.
        """
        path = eval_file(self.root, 60, "grid.jsonl")
        shapes = (
            # (before right, after right, before kwargs, after kwargs)
            (range(0, 20), range(0, 30), {"sample": 30}, {"sample": 60}),
            (range(0, 30), range(0, 20), {"sample": 60}, {"sample": 30}),
            (range(0, 25), range(0, 25), {"sample": 40}, {"sample": 40}),
            (
                range(10, 30),
                range(10, 40),
                {"sample": 60},
                {"sample": 50, "hold_out": list(range(10))},
            ),
        )
        for number, (old_right, new_right, old_kw, new_kw) in enumerate(shapes):
            with self.subTest(shape=number):
                before = self.graded(path, old_right, prompt=f"before {number}", **old_kw)
                after = self.graded(path, new_right, prompt=f"after {number}", **new_kw)
                verdict = self.compare(after, before)
                self.assertTrue(verdict["ok"], verdict.get("detail"))
                self.assertAlmostEqual(
                    verdict["delta"] * verdict["paired_rows"],
                    verdict["improved"] - verdict["regressed"],
                    places=9,
                )
                self.assertAlmostEqual(
                    verdict["score"] - verdict["score_against"],
                    verdict["delta"],
                    places=9,
                )

    def test_the_two_axis_markers_are_the_paired_scores(self):
        """`EvalCompareCard` plots `score_against` and `score` on ONE axis with
        the delta drawn between them. Two aggregates over two different row sets
        cannot go on one axis, and the gap between them would not be the delta."""
        before, after = self.two_sample_sizes()
        verdict = self.compare(after, before)
        self.assertAlmostEqual(verdict["score_against"], 24 / 30)
        self.assertAlmostEqual(verdict["score"], 30 / 30)
        self.assertAlmostEqual(
            verdict["score"] - verdict["score_against"], verdict["delta"]
        )
        self.assertEqual(verdict["correct"], 30)
        self.assertEqual(verdict["correct_against"], 24)

    def test_the_aggregate_difference_is_demoted_and_named_rather_than_deleted(self):
        """It is a real fact about two runs. What it is not is the difference
        between them, and it is labelled instead of headlined."""
        before, after = self.two_sample_sizes()
        verdict = self.compare(after, before)
        aggregate = verdict["aggregate"]
        self.assertAlmostEqual(aggregate["score"], 30 / 100)
        self.assertAlmostEqual(aggregate["score_against"], 24 / 30)
        self.assertAlmostEqual(aggregate["difference"], -0.5)
        self.assertEqual(aggregate["rows"], 100)
        self.assertEqual(aggregate["rows_against"], 30)
        self.assertEqual(aggregate["only_this_run_graded_count"], 70)
        self.assertEqual(aggregate["only_the_other_graded_count"], 0)
        self.assertIn("NOT the difference between them", aggregate["says"])
        self.assertFalse(verdict["same_rows"])
        self.assertIn("-50.0%", verdict["says"])
        self.assertIn("two different row sets", verdict["says"])

    def test_the_resolution_is_over_the_rows_the_delta_was_measured_on(self):
        """The card prints "+-x points at n=" beside the delta. An interval over
        a hundred rows next to a difference measured on thirty is the same defect
        one field along."""
        before, after = self.two_sample_sizes()
        verdict = self.compare(after, before)
        self.assertEqual(verdict["resolution"]["n"], verdict["paired_rows"])
        self.assertEqual(verdict["resolution"]["n"], 30)


class TheFewShotPathIsHonestTest(PairedDeltaTest):
    """Holding exemplar rows out is RECOMMENDED, so it must not flatter."""

    def test_holding_exemplars_out_no_longer_exaggerates_the_delta(self):
        """+12.0 reported where +4.0 was honest: threefold, upward, on the path
        `NO_TRAIN__FEW_SHOT` tells the user to take."""
        champion, challenger = self.fewshot()
        self.assertAlmostEqual(champion["score"], 24 / 60)
        self.assertAlmostEqual(challenger["score"], 26 / 50)

        verdict = self.compare(challenger, champion)
        self.assertTrue(verdict["ok"], verdict.get("detail"))
        self.assertEqual(verdict["paired_rows"], 50)
        self.assertAlmostEqual(verdict["delta"], 2 / 50)
        self.assertAlmostEqual(verdict["aggregate"]["difference"], 0.12)
        self.assertAlmostEqual(
            verdict["aggregate"]["difference"], 3 * verdict["delta"], places=9
        )
        self.assertIn("+4.0%", verdict["says"])
        self.assertIn("+12.0%", verdict["says"])
        self.assertIn("two different row sets", verdict["says"])

    def test_the_exemplar_rows_are_excluded_from_both_sides_and_counted(self):
        champion, challenger = self.fewshot()
        verdict = self.compare(challenger, champion)
        self.assertEqual(verdict["aggregate"]["only_the_other_graded_count"], 10)
        self.assertEqual(verdict["aggregate"]["only_this_run_graded_count"], 0)
        self.assertEqual(
            verdict["aggregate"]["only_the_other_graded"], list(range(10))
        )

    def test_two_unresolvable_rows_are_still_no_evidence(self):
        """The honest +4.0 is inside what fifty rows can see, and the refusal
        that is the point survives the correction: an honest number that cannot
        be resolved is still reported as no evidence, not as a small win."""
        champion, challenger = self.fewshot()
        verdict = self.compare(challenger, champion)
        self.assertEqual(verdict["verdict"], "no_evidence")
        self.assertFalse(verdict["resolved"])
        self.assertIn("NO EVIDENCE", verdict["says"])


class TheOppositeFailureIsAsBadTest(PairedDeltaTest):
    """A bench that can never conclude is as useless as one that always does."""

    def same_rows(self, old_right, new_right, rows=30):
        path = eval_file(self.root, rows, "same.jsonl")
        before = self.graded(path, old_right, sample=rows)
        after = self.graded(path, new_right, sample=rows, prompt="Try harder.")
        return before, after

    def test_two_runs_over_the_same_rows_report_exactly_what_they_always_did(self):
        """The ordinary case must not have moved. When the row sets are
        identical the paired delta IS the aggregate difference, bit for bit."""
        before, after = self.same_rows(range(0, 20), range(0, 28))
        verdict = self.compare(after, before)
        self.assertTrue(verdict["same_rows"])
        self.assertEqual(verdict["paired_rows"], 30)
        self.assertAlmostEqual(verdict["delta"], 8 / 30)
        self.assertAlmostEqual(
            verdict["delta"], after["score"] - before["score"], places=12
        )
        self.assertAlmostEqual(verdict["aggregate"]["difference"], verdict["delta"])
        self.assertAlmostEqual(verdict["score"], after["score"])
        self.assertAlmostEqual(verdict["score_against"], before["score"])
        self.assertNotIn("two different row sets", verdict["says"])

    def test_a_real_difference_is_still_reported_as_one(self):
        before, after = self.same_rows(range(0, 10), range(0, 28))
        verdict = self.compare(after, before)
        self.assertEqual(verdict["verdict"], "different")
        self.assertTrue(verdict["resolved"])
        self.assertLessEqual(verdict["p_value"], 0.05)
        self.assertIn("a real difference on this eval set", verdict["says"])

    def test_a_real_regression_still_comes_back_negative(self):
        """The sign has to survive in both directions or the fix has only moved
        the lie."""
        before, after = self.same_rows(range(0, 28), range(0, 10))
        verdict = self.compare(after, before)
        self.assertLess(verdict["delta"], 0)
        self.assertEqual(verdict["improved"], 0)
        self.assertEqual(verdict["regressed"], 18)
        self.assertTrue(verdict["resolved"])

    def test_a_different_sample_size_is_not_refused_as_a_different_eval_set(self):
        """Moving the fingerprint onto the graded rows would have made this a
        refusal, and it is a legitimate comparison: one file, one prompt change,
        two sizes."""
        before, after = self.two_sample_sizes()
        verdict = self.compare(after, before)
        self.assertTrue(verdict["ok"], verdict.get("detail"))
        self.assertNotEqual(verdict.get("error"), "different_eval_sets")
        self.assertEqual(verdict["verdict"], "different")

    def test_two_identical_runs_are_still_reported_as_identical(self):
        before, after = self.same_rows(range(0, 20), range(0, 20))
        verdict = self.compare(after, before)
        self.assertEqual(verdict["changed"], 0)
        self.assertEqual(verdict["delta"], 0.0)
        self.assertEqual(verdict["p_value"], 1.0)
        self.assertIn("no evidence of any difference", verdict["says"])


class TheRefusalsTest(PairedDeltaTest):
    """What the comparison still will not do, and one thing it now will not."""

    def test_two_runs_with_no_row_in_common_are_refused(self):
        """This returned "Not one of the 0 rows changed its verdict. These two
        are the same on this eval set", which reads as agreement and is a
        statement about nothing. Two runs on disjoint slices of one file have not
        been compared at all."""
        path = eval_file(self.root, 60, "disjoint.jsonl")
        first = self.graded(path, range(0, 30), sample=30)
        second = self.graded(
            path, range(0, 30), sample=30, hold_out=list(range(30))
        )
        verdict = self.compare(second, first)
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["error"], "no_shared_rows")
        self.assertEqual(verdict["paired_rows"], 0)
        self.assertIn("nothing to pair", verdict["detail"])
        self.assertNotIn("says", verdict)

    def test_two_different_eval_sets_are_still_two_facts(self):
        """The refusal that was already right, kept: a fingerprint mismatch is
        still a different eval set and still not a delta."""
        first = self.graded(
            eval_file(self.root, 40, "a.jsonl"), range(0, 20), sample=40
        )
        second = self.graded(
            eval_file(self.root, 30, "b.jsonl"), range(0, 20), sample=30
        )
        refused = self.compare(second, first)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "different_eval_sets")
        self.assertIn("two facts, not a delta", refused["detail"])

    def test_the_listing_no_longer_claims_a_fingerprint_means_the_same_rows(self):
        """`read_eval_results` told every caller that two runs sharing an
        `eval_fingerprint` "were measured on the same rows". That sentence is
        what the defect was made of."""
        path = eval_file(self.root, 40, "listed.jsonl")
        self.graded(path, range(0, 20), sample=20)
        self.graded(path, range(0, 20), sample=40, prompt="Try harder.")
        listing = REGISTRY.call(
            "read_eval_results", {}, actor=MODEL, thread_id=self.thread
        )
        self.assertTrue(listing["ok"])
        self.assertEqual(len(listing["runs"]), 2)
        self.assertEqual(
            listing["runs"][0]["eval_fingerprint"],
            listing["runs"][1]["eval_fingerprint"],
        )
        self.assertNotIn("measured on the same rows", listing["help"])
        self.assertIn("does NOT mean they graded the same rows", listing["help"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
