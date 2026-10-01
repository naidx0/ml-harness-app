"""The edge-direction pair refuses a model that matches nothing.

THE HOLE THIS CLOSES, MEASURED 2026-09-10. Direction is scored over MATCHED
edges, which is what stops a node named differently being charged twice - once as
a missing label and again as a broken edge. That denominator is right, and it is
gameable: a model that emits ONE CONSTANT GRAPH for every question matched 4 of
346 reference edges and reversed none of them. Its reversed share was 0.0% - the
best possible value of the metric - against the real model's 26.5%.

**Refusing to engage won.** A training run pointed at a bare reversed share would
have learned to emit labels the reference cannot match, and the score would have
improved all the way down.

So the metric is a pair, and this asserts the pair behaves: coverage travels with
the share, and a result below the floor is marked `is_a_score: false` rather than
reported as a good number.

WHY THE CONTROL IS A CONSTANT ANSWER AND NOT A BAD ONE. A merely wrong model
still matches labels and still gets charged for its reversals; it does not
exercise the hole. The hole needs an answer that is internally valid and shares
nothing with the reference, which is exactly what a majority-class baseline is -
and a majority baseline is the thing every eval is supposed to be checked
against.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.tools.edge_direction_metric import COVERAGE_FLOOR, score_edge_direction  # noqa: E402


def a_graph(*names: str) -> str:
    nodes = [{"id": n[:3], "label": n, "kind": "service"} for n in names]
    edges = [{"from": names[i][:3], "to": names[i + 1][:3]} for i in range(len(names) - 1)]
    return json.dumps({"nodes": nodes, "edges": edges}, separators=(",", ":"))


class AConstantAnswerIsNotAPerfectScoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.here = Path(self.tmp.name)

        #: Five systems, three edges each, sharing no label with the constant answer.
        self.reference = self.here / "reference.jsonl"
        rows = []
        for i in range(5):
            names = [f"Client {i}", f"Service {i}", f"Store {i}", f"Cache {i}"]
            rows.append({"row_id": i, "input": "x", "expected": a_graph(*names),
                         "node_labels": [n.lower() for n in names], "edge_count": 3})
        self.reference.write_text(
            chr(10).join(json.dumps(r) for r in rows) + chr(10), encoding="utf-8")

    def _predictions(self, name: str, answer_for) -> Path:
        path = self.here / name
        path.write_text(
            chr(10).join(json.dumps({"row_index": i, "answer": answer_for(i)})
                         for i in range(5)) + chr(10), encoding="utf-8")
        return path

    def test_a_constant_answer_is_refused_rather_than_scored(self):
        """THE WHOLE POINT. It reverses nothing because it matches nothing."""
        constant = a_graph("Widget", "Gadget", "Doodah")
        predictions = self._predictions("constant.jsonl", lambda _i: constant)

        found = score_edge_direction(str(predictions), [str(self.reference)])

        self.assertTrue(found["ok"])
        self.assertEqual(found["reversed_edges"], 0,
                         "the control must reverse nothing, or it is not this control")
        self.assertLess(found["coverage"], COVERAGE_FLOOR)
        self.assertFalse(found["is_a_score"],
                         "a constant answer was reported as a score")
        self.assertIn("NOT A SCORE", found["summary"])
        self.assertIn("matches nothing", found["summary"])

    def test_the_share_is_still_returned_so_the_refusal_can_be_read(self):
        """Hiding the number would leave a reader guessing at what was refused."""
        constant = a_graph("Widget", "Gadget", "Doodah")
        found = score_edge_direction(
            str(self._predictions("c2.jsonl", lambda _i: constant)), [str(self.reference)])
        self.assertEqual(found["reversed_share"], 0.0)
        self.assertIn("matched_edges", found)

    def test_a_perfect_answer_is_a_score_and_reverses_nothing(self):
        """The other end, so the refusal is not simply always-on."""
        reference = [json.loads(l) for l in self.reference.read_text(encoding="utf-8").splitlines() if l.strip()]
        found = score_edge_direction(
            str(self._predictions("perfect.jsonl", lambda i: reference[i]["expected"])),
            [str(self.reference)])
        self.assertTrue(found["is_a_score"])
        self.assertEqual(found["coverage"], 1.0)
        self.assertEqual(found["reversed_edges"], 0)
        self.assertEqual(found["reversed_share"], 0.0)

    def test_a_reversed_answer_is_a_score_and_is_charged_for_it(self):
        """Same labels, every arrow turned around: full coverage, all reversed.

        This is the case a bare share cannot tell apart from the constant answer
        - both report 0 reversed... no: this one reports ALL reversed at full
        coverage, and the constant reports none at 1.2%. The pair separates them
        and either number alone does not."""
        reference = [json.loads(l) for l in self.reference.read_text(encoding="utf-8").splitlines() if l.strip()]

        def flipped(i):
            graph = json.loads(reference[i]["expected"])
            graph["edges"] = [{"from": e["to"], "to": e["from"]} for e in graph["edges"]]
            return json.dumps(graph, separators=(",", ":"))

        found = score_edge_direction(
            str(self._predictions("flipped.jsonl", flipped)), [str(self.reference)])
        self.assertTrue(found["is_a_score"])
        self.assertEqual(found["coverage"], 1.0)
        self.assertEqual(found["reversed_share"], 1.0,
                         "every edge was turned around and the metric did not charge it")

    def test_the_rule_travels_with_the_number(self):
        """A share quoted without its denominator is what started all this."""
        reference = [json.loads(l) for l in self.reference.read_text(encoding="utf-8").splitlines() if l.strip()]
        found = score_edge_direction(
            str(self._predictions("p2.jsonl", lambda i: reference[i]["expected"])),
            [str(self.reference)])
        self.assertIn("matched edges only", found["rule"])
        self.assertIn("coverage", found["rule"])

    def test_a_positional_join_is_allowed_only_when_the_reference_is_positional(self):
        """THIS TEST ASSERTED THE OPPOSITE THIS MORNING AND WAS WRONG.

        It required a 0-based predictions file against a 100-based reference to
        join BY POSITION, on the reasoning that matching counts made file order
        unambiguous. ML BUILD then hit exactly that case for real: the recipe
        numbers predictions positionally, the extra held-out set numbers rows
        from 100 so an extra can never be mistaken for an original, and the two
        conventions together produced a table about the wrong graphs that looked
        entirely reasonable. Matching counts is evidence the files are the same
        LENGTH, not that they ask the same questions.

        So position is now allowed only where the two conventions cannot
        disagree - a reference whose own ids ARE the positions."""
        rows = [json.loads(l) for l in self.reference.read_text(encoding="utf-8").splitlines() if l.strip()]
        predictions = self._predictions("pos_ok.jsonl", lambda i: rows[i]["expected"])

        #: The reference here is numbered 0-4, so file order is unambiguous.
        found = score_edge_direction(str(predictions), [str(self.reference)])
        self.assertTrue(found["ok"], found.get("summary"))
        self.assertEqual(found["coverage"], 1.0)
        self.assertIn(found["join"], ("row_id", "position"))
    def test_it_refuses_when_no_join_is_possible(self):
        """Different ids AND different row counts is a guess, so it declines."""
        rows = [json.loads(l) for l in self.reference.read_text(encoding="utf-8").splitlines() if l.strip()][:3]
        for row in rows:
            row["row_id"] += 100
        short = self.here / "short.jsonl"
        short.write_text(chr(10).join(json.dumps(r) for r in rows) + chr(10), encoding="utf-8")
        found = score_edge_direction(
            str(self._predictions("p5.jsonl", lambda i: rows[0]["expected"])), [str(short)])
        self.assertFalse(found["ok"])
        self.assertIn("no join", found["summary"].lower())

    def test_a_zero_based_run_against_several_references_is_refused(self):
        """THE FAULT ML BUILD CAUGHT BY HAND, and it is AMBIGUITY rather than
        differing ids. The CLI globs every `held-out*.jsonl`, the recipe numbers
        predictions positionally from zero, and the extra set numbers rows from
        100 so an extra can never be mistaken for an original. Put those
        together and position 0 silently resolves to whichever file sorted
        first - a table about the wrong graphs that looks entirely reasonable.

        With more than one reference named there is no join that is not a
        guess, so it refuses. With ONE named reference the caller has said
        which file the run came from, and that is the next case."""
        rows = [json.loads(l) for l in self.reference.read_text(encoding="utf-8").splitlines() if l.strip()]
        hundreds_rows = [dict(r, row_id=r["row_id"] + 100) for r in rows]
        hundreds = self.here / "hundreds.jsonl"
        hundreds.write_text(chr(10).join(json.dumps(r) for r in hundreds_rows) + chr(10), encoding="utf-8")

        predictions = self._predictions("zero_based.jsonl", lambda i: hundreds_rows[i]["expected"])
        found = score_edge_direction(str(predictions), [str(self.reference), str(hundreds)])

        self.assertFalse(found["ok"], "it joined a 0-based run across two references")
        self.assertIn("wrong questions", found["summary"].lower())

    def test_one_named_reference_is_the_callers_claim_and_is_honoured(self):
        """The legitimate call, and refusing it was a notch too strict - it
        blocked the real baseline run on its first use. A run generated FROM one
        file and scored against that same file has no ambiguity to resolve."""
        rows = [json.loads(l) for l in self.reference.read_text(encoding="utf-8").splitlines() if l.strip()]
        hundreds_rows = [dict(r, row_id=r["row_id"] + 100) for r in rows]
        hundreds = self.here / "h_only.jsonl"
        hundreds.write_text(chr(10).join(json.dumps(r) for r in hundreds_rows) + chr(10), encoding="utf-8")

        predictions = self._predictions("zb2.jsonl", lambda i: hundreds_rows[i]["expected"])
        found = score_edge_direction(str(predictions), [str(hundreds)])
        self.assertTrue(found["ok"], found.get("summary"))
        self.assertEqual(found["join"], "position")
        self.assertEqual(found["coverage"], 1.0)
        self.assertIn("one reference was named", found["join_reason"])

    def test_a_declared_row_id_is_used_and_nothing_is_inferred(self):
        """The other half of the fix: when the predictions carry row_id, that
        IS the join and no guess is made."""
        rows = [json.loads(l) for l in self.reference.read_text(encoding="utf-8").splitlines() if l.strip()]
        for row in rows:
            row["row_id"] += 100
        hundreds = self.here / "h2.jsonl"
        hundreds.write_text(chr(10).join(json.dumps(r) for r in rows) + chr(10), encoding="utf-8")

        declared = self.here / "declared.jsonl"
        declared.write_text(chr(10).join(
            json.dumps({"row_index": i, "row_id": 100 + i, "answer": rows[i]["expected"]})
            for i in range(5)) + chr(10), encoding="utf-8")

        found = score_edge_direction(str(declared), [str(hundreds)])
        self.assertTrue(found["ok"], found.get("summary"))
        self.assertEqual(found["join"], "declared_row_id")
        self.assertEqual(found["coverage"], 1.0)

    def test_a_declared_row_id_that_is_not_in_the_reference_is_refused(self):
        """A file that says which rows it answers, against a set that does not
        hold them, was scored against something it was not generated from."""
        declared = self.here / "wrong.jsonl"
        rows = [json.loads(l) for l in self.reference.read_text(encoding="utf-8").splitlines() if l.strip()]
        declared.write_text(chr(10).join(
            json.dumps({"row_index": i, "row_id": 900 + i, "answer": rows[i]["expected"]})
            for i in range(5)) + chr(10), encoding="utf-8")
        found = score_edge_direction(str(declared), [str(self.reference)])
        self.assertFalse(found["ok"])
        self.assertIn("900", found["summary"])

    def test_a_missing_file_refuses_and_names_it(self):
        found = score_edge_direction(str(self.here / "nope.jsonl"), [str(self.reference)])
        self.assertFalse(found["ok"])
        self.assertIn("nope.jsonl", found["summary"])


class AnAnswerThatDoesNotParseIsWrongNotAbsentTest(unittest.TestCase):
    """THE DENOMINATOR MUST NOT SHRINK WHEN THE MODEL FAILS.

    A row whose answer is not JSON used to be skipped, taking its reference
    edges out of the total. That gives a model a SMALLER denominator for
    answering worse, which is coverage rewarding a miss - the same fault this
    file already refuses for a constant answer, by a different door.

    MEASURED 2026-09-10 on run 1's adapter over the forty: two answers did not
    parse, they carry two reference edges each, and coverage read 56/114 =
    49.1% where the honest denominator is 56/118 = 47.5%. ML BUILD's own page
    shipped the same fault on the same run and corrected it; this is the
    version that cannot ship it again.
    """

    def _reference(self, here):
        rows = [
            {"row_id": 0, "expected": {
                "nodes": [{"id": "a", "label": "Browser"},
                          {"id": "b", "label": "Api"}],
                "edges": [{"from": "a", "to": "b"}]}},
            {"row_id": 1, "expected": {
                "nodes": [{"id": "c", "label": "Worker"},
                          {"id": "d", "label": "Queue"}],
                "edges": [{"from": "c", "to": "d"}]}},
        ]
        path = here / "reference.jsonl"
        path.write_text(chr(10).join(json.dumps(r) for r in rows), encoding="utf-8")
        return path

    def test_an_unparseable_answer_stays_in_the_denominator(self):
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            reference = self._reference(here)
            #: Row 0 answered perfectly; row 1 answered with prose.
            runs = [
                {"row_index": 0, "row_id": 0, "answer": json.dumps({
                    "nodes": [{"id": "a", "label": "Browser"},
                              {"id": "b", "label": "Api"}],
                    "edges": [{"from": "a", "to": "b"}]})},
                {"row_index": 1, "row_id": 1, "answer": "```json"},
            ]
            run = here / "predictions.jsonl"
            run.write_text(chr(10).join(json.dumps(r) for r in runs), encoding="utf-8")

            found = score_edge_direction(str(run), [str(reference)])

            self.assertEqual(
                found["reference_edges"], 2,
                "the unanswered row's edge left the denominator, so failing to "
                "produce JSON improved the score.")
            self.assertEqual(found["matched_edges"], 1)
            self.assertAlmostEqual(found["coverage"], 0.5, places=4)
            self.assertEqual(
                found["unparsed_answers"], 1,
                "the count a reader needs to know how much of a coverage "
                "figure rests on answers that were not graphs at all.")

    def test_an_arm_that_parses_nothing_still_has_a_denominator(self):
        """THE CASE THAT PRODUCED THIS, and it produced nothing at all.

        Run 1's base arm answered every one of forty rows with the fence line
        alone. Under the old rule it scored `0 of 0` - a coverage with no
        denominator, which reads as 'nothing to say' rather than 'answered
        nothing'. The two are opposite readings of the same run.
        """
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            reference = self._reference(here)
            runs = [{"row_index": i, "row_id": i, "answer": "```json"}
                    for i in (0, 1)]
            run = here / "predictions.jsonl"
            run.write_text(chr(10).join(json.dumps(r) for r in runs), encoding="utf-8")

            found = score_edge_direction(str(run), [str(reference)])

            self.assertEqual(found["reference_edges"], 2,
                             "an arm that parsed nothing reported no "
                             "denominator, so it could not be told from an "
                             "arm that was never run.")
            self.assertEqual(found["matched_edges"], 0)
            self.assertEqual(found["coverage"], 0.0)
            self.assertFalse(found["is_a_score"])
            self.assertEqual(found["unparsed_answers"], 2)
if __name__ == "__main__":  # pragma: no cover
    unittest.main()
