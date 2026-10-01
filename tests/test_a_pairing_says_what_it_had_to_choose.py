"""A paired table has to say what its numbers rest on, or it is a guess.

## The two faults this file is about, both from one night

**One: the model columns committed EMPTY.** The kill-13 table was hand-assembled
in a shell string, the backticks around each model name were read as command
substitution, and every identity cell came out blank under a commit message
asserting "one model in both arms". A table that says nothing looks exactly like
a table that says something, so the table is built by code now.

**Two: the lenient parse picked a fragment and reported a percentage off it.**
`strip_fence` keeps the first balanced object out of a fenced reply. On
`run_15`'s base arm only 1 of 40 replies ever closed its fence, 17 of 40 carried
more than one balanced object, and in 24 of 40 the first one ended before HALF
the text. A base coverage of "2.5%" was published from that. The number was
about a fragment the parser chose, and nothing in the output said so.

So `objects_seen` and the rule that chose are recorded per answer, and these
tests are what keeps them there.
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

from app.tools.pair_edge_direction import (  # noqa: E402
    STATES,
    balanced_objects,
    pair_edge_direction,
    parse_answer,
)

NL = chr(10)
TAB = chr(9)
FENCE = chr(96) * 3


def graph(*pairs):
    labels = sorted({name for pair in pairs for name in pair})
    nodes = [{"id": n[:4], "label": n, "kind": "service"} for n in labels]
    edges = [{"from": a[:4], "to": b[:4]} for a, b in pairs]
    return {"nodes": nodes, "edges": edges}


def write(path: Path, rows) -> Path:
    path.write_text(NL.join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


class TheAmbiguityIsRecordedNotResolvedTest(unittest.TestCase):
    """THE FAULT THAT PUBLISHED A NUMBER ABOUT A FRAGMENT."""

    def test_several_objects_are_counted_and_the_rule_is_named(self):
        reply = FENCE + "json" + NL + json.dumps(graph(("a", "b"))) + NL + FENCE \
            + NL + "Another attempt:" + NL + json.dumps(graph(("c", "d")))
        self.assertEqual(len(balanced_objects(reply)), 2,
                         "two whole answers in one reply must read as two.")
        found, ok, objects, rule = parse_answer(reply, True)
        self.assertTrue(ok)
        self.assertEqual(objects, 2)
        self.assertEqual(rule, "first_balanced_object",
                         "the rule that chose must be named, because it chose.")

    def test_a_clean_answer_says_it_had_nothing_to_choose(self):
        """`verbatim` is the only rule that CANNOT have picked wrong."""
        found, ok, objects, rule = parse_answer(json.dumps(graph(("a", "b"))), True)
        self.assertTrue(ok)
        self.assertEqual(rule, "verbatim")

    def test_a_truncated_reply_is_not_silently_parsed(self):
        """The base arm's actual shape: opened, never closed."""
        truncated = FENCE + "json" + NL + '{' + NL + '  "nodes": [' + NL + '    {' \
            + NL + '      "id": "a"'
        self.assertEqual(balanced_objects(truncated), [])
        found, ok, objects, rule = parse_answer(truncated, True)
        self.assertFalse(ok)
        self.assertEqual(rule, "none")
        self.assertEqual(found, {"nodes": [], "edges": []})

    def test_braces_inside_strings_do_not_close_an_object(self):
        """A label containing a brace is not the end of the graph."""
        text = json.dumps({"nodes": [{"id": "a", "label": "the {weird} one"}],
                           "edges": []})
        self.assertEqual(len(balanced_objects(text)), 1)


class TheTableSaysWhoAnsweredTest(unittest.TestCase):
    """Refusal 6, enforced rather than asserted."""

    def _pair(self, here, left_rows, right_rows, **kw):
        reference = write(here / "reference.jsonl", [
            {"row_id": 0, "expected": graph(("a", "b"))},
            {"row_id": 1, "expected": graph(("c", "d"))},
        ])
        left = write(here / "left.jsonl", left_rows)
        right = write(here / "right.jsonl", right_rows)
        return pair_edge_direction(
            arms=[{"name": "base", "predictions_path": str(left)},
                  {"name": "adapter", "predictions_path": str(right)}],
            reference_paths=[str(reference)],
            out_path=str(here / "table.tsv"), **kw)

    def test_an_arm_with_no_model_anywhere_is_refused(self):
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            rows = [{"row_id": 0, "answer": json.dumps(graph(("a", "b")))}]
            found = self._pair(here, rows, rows)
            self.assertFalse(found["ok"])
            self.assertEqual(found["error"], "model_not_recorded")
            self.assertIn("moves two things at once", found["summary"])

    def test_the_model_travels_into_every_row_of_the_table(self):
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            left = [{"row_id": 0, "answer": json.dumps(graph(("a", "b"))),
                     "model": "base-model"},
                    {"row_id": 1, "answer": json.dumps(graph(("c", "d"))),
                     "model": "base-model"}]
            right = [{"row_id": 0, "answer": json.dumps(graph(("a", "b"))),
                      "model": "base-model"},
                     {"row_id": 1, "answer": json.dumps(graph(("d", "c"))),
                      "model": "base-model"}]
            found = self._pair(here, left, right)
            self.assertTrue(found["ok"], found.get("summary"))
            self.assertTrue(found["same_base_model"])
            rows = Path(found["table_path"]).read_text(encoding="utf-8").splitlines()
            header = rows[0].split(TAB)
            self.assertIn("model_base", header)
            self.assertIn("model_adapter", header)
            for line in rows[1:]:
                cells = line.split(TAB)
                self.assertEqual(cells[header.index("model_base")], "base-model",
                                 "a model cell came out empty, which is the "
                                 "shell-substitution fault this tool replaced.")

    def test_two_different_models_are_said_out_loud(self):
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            left = [{"row_id": 0, "answer": json.dumps(graph(("a", "b"))),
                     "model": "one-model"}]
            right = [{"row_id": 0, "answer": json.dumps(graph(("a", "b"))),
                      "model": "another-model"}]
            found = self._pair(here, left, right)
            self.assertTrue(found["ok"])
            self.assertFalse(found["same_base_model"])
            self.assertIn("DIFFERENT MODELS", found["summary"],
                          "a pairing across two models must say so where the "
                          "number is read, not in a footnote elsewhere.")


class TheDenominatorIsOneAndTheStatesAreThreeTest(unittest.TestCase):
    """Refusal 1, and the reason it could not be met before."""

    def test_both_arms_get_the_same_reference_edge_total(self):
        """Even when one arm answers nothing at all."""
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            reference = write(here / "reference.jsonl", [
                {"row_id": 0, "expected": graph(("a", "b"))},
                {"row_id": 1, "expected": graph(("c", "d"))},
            ])
            left = write(here / "left.jsonl", [
                {"row_id": 0, "answer": FENCE + "json", "model": "m"},
                {"row_id": 1, "answer": FENCE + "json", "model": "m"}])
            right = write(here / "right.jsonl", [
                {"row_id": 0, "answer": json.dumps(graph(("a", "b"))), "model": "m"},
                {"row_id": 1, "answer": json.dumps(graph(("c", "d"))), "model": "m"}])
            found = pair_edge_direction(
                arms=[{"name": "base", "predictions_path": str(left)},
                      {"name": "adapter", "predictions_path": str(right)}],
                reference_paths=[str(reference)],
                out_path=str(here / "t.tsv"))
            self.assertEqual(found["reference_edges"], 2)
            self.assertEqual(found["b_cov"], 0)
            self.assertEqual(found["c_cov"], 2,
                             "an arm that answered nothing must still have a "
                             "denominator, or it cannot be told from an arm "
                             "that was never run.")

    def test_there_is_no_fourth_state(self):
        """A `skipped` value is what the dropped denominator looked like."""
        self.assertEqual(set(STATES), {"correct", "reversed", "missing"})

    def test_a_pairing_needs_exactly_two_arms(self):
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            reference = write(here / "reference.jsonl",
                              [{"row_id": 0, "expected": graph(("a", "b"))}])
            found = pair_edge_direction(arms=[], reference_paths=[str(reference)])
            self.assertFalse(found["ok"])
            self.assertEqual(found["error"], "two_arms_required")


class TheTwoReadingsAreAPairTest(unittest.TestCase):
    """The research lane's ruling: never the default, always recorded."""

    def _run(self, here, strip):
        reference = write(here / "reference.jsonl",
                          [{"row_id": 0, "expected": graph(("a", "b"))}])
        fenced = FENCE + "json" + NL + json.dumps(graph(("a", "b"))) + NL + FENCE
        left = write(here / "left.jsonl",
                     [{"row_id": 0, "answer": fenced, "model": "m"}])
        right = write(here / "right.jsonl",
                      [{"row_id": 0, "answer": json.dumps(graph(("a", "b"))),
                        "model": "m"}])
        return pair_edge_direction(
            arms=[{"name": "base", "predictions_path": str(left)},
                  {"name": "adapter", "predictions_path": str(right)}],
            reference_paths=[str(reference)],
            out_path=str(here / ("t" + str(strip) + ".tsv")), strip_fence=strip)

    def test_stripping_is_off_by_default(self):
        """The eval's own instruction says no fence, so obeying it is the task."""
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            self.assertFalse(self._run(here, False)["fence_stripped"])

    def test_the_gap_between_the_readings_is_the_format_measurement(self):
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            strict = self._run(here, False)
            lenient = self._run(here, True)
            self.assertTrue(lenient["fence_stripped"])
            self.assertEqual(strict["arms"][0]["matched"], 0,
                             "a fenced answer failed the instruction it was "
                             "given, and strict is what says so.")
            self.assertEqual(lenient["arms"][0]["matched"], 1,
                             "and lenient is what says the graph was there.")


class TheRealRunReproducesTest(unittest.TestCase):
    """The two figures this tool was built to stop being hand-assembled."""

    #: FOUND, NOT HARD-CODED. The first version of this file pasted the
    #: absolute path this run happened to sit at, which named a home
    #: directory - and `test_no_shipped_file_names_a_person` caught it. A
    #: fixture is about the shape, never about whose machine it came from.
    EV = REPO / "evals" / "architecture-json"

    @staticmethod
    def _find_run():
        """run_15 under any sandbox in this checkout's gitignored runs/."""
        for found in (REPO / "runs").glob("*/sandboxes/*/runs/run_15"):
            if (found / "predictions.jsonl").is_file():
                return found
        return None

    def test_run_15_gives_the_published_pair(self):
        run = self._find_run()
        if run is None:
            self.skipTest("run_15 is not in this checkout; runs/ is gitignored")
        with tempfile.TemporaryDirectory() as scratch:
            arms = [{"name": "base",
                     "predictions_path": str(run / "predictions_base.jsonl")},
                    {"name": "adapter",
                     "predictions_path": str(run / "predictions.jsonl")}]
            refs = [str(self.EV / "held-out.jsonl"),
                    str(self.EV / "held-out-extra.jsonl")]
            table = str(Path(scratch) / "t.tsv")
            strict = pair_edge_direction(arms=arms, reference_paths=refs,
                                         out_path=table)
            lenient = pair_edge_direction(arms=arms, reference_paths=refs,
                                          out_path=table, strip_fence=True)
            self.assertEqual(strict["reference_edges"], 118)
            self.assertEqual((strict["b_cov"], strict["c_cov"]), (0, 56))
            self.assertEqual((lenient["b_cov"], lenient["c_cov"]), (0, 53))
            self.assertEqual(lenient["arms"][0]["ambiguous_answers"], 17,
                             "17 of the base's forty replies carried more than "
                             "one balanced object; that count is the reason "
                             "the lenient reading is quoted with a rule.")


class TheWholePathEndToEndTest(unittest.TestCase):
    """THE DRY RUN, so run 2's verdict comes through the tool and not by hand.

    Kill 13's numbers were computed by hand because the tool did not exist,
    and then the tool REFUSED that pair because its baseline artefact never
    named a model. Both facts are recorded. This is the other half: proof that
    an artefact pair which DOES carry `model` on both arms goes through the
    tool end to end - accepted, joined, tabulated - so the next real pair does
    not quietly fall back to a hand path again.

    The specimen is built here. A test whose subject is a run directory loses
    its subject the moment somebody reruns or prunes it, which this file's
    sibling learned the expensive way.
    """

    #: TWO reference files with DISJOINT id ranges, which is the case that
    #: caught a real mis-join: predictions numbered from zero against a set
    #: numbered from a hundred have matching COUNTS, so a positional join
    #: succeeds and scores answers against different questions.
    def _two_references(self, here):
        first = write(here / "held-out.jsonl", [
            {"row_id": 0, "expected": graph(("browser", "rest api"))},
            {"row_id": 1, "expected": graph(("worker", "queue"))},
        ])
        second = write(here / "held-out-extra.jsonl", [
            {"row_id": 100, "expected": graph(("tablet", "ingest"))},
            {"row_id": 101, "expected": graph(("cache", "store"))},
        ])
        return [str(first), str(second)]

    def _arms(self, here, model="a-real-model", strip_from=None):
        """Both arms over all four row_ids, spanning both reference files."""
        answers = {
            0: graph(("browser", "rest api")),
            1: graph(("queue", "worker")),          # reversed
            100: graph(("tablet", "ingest")),
            101: {"nodes": [], "edges": []},         # matched nothing
        }
        made = []
        for name in ("base", "adapter"):
            rows = []
            for rid, answer in answers.items():
                row = {"row_index": len(rows), "row_id": rid,
                       "answer": json.dumps(answer)}
                if name != strip_from:
                    row["model"] = model
                rows.append(row)
            made.append(str(write(here / (name + ".jsonl"), rows)))
        return made

    def test_a_pair_that_names_its_model_goes_all_the_way_through(self):
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            refs = self._two_references(here)
            base, adapter = self._arms(here)
            found = pair_edge_direction(
                arms=[{"name": "base", "predictions_path": base},
                      {"name": "adapter", "predictions_path": adapter}],
                reference_paths=refs,
                out_path=str(here / "table.tsv"))

            self.assertTrue(found["ok"], found.get("summary"))
            self.assertTrue(found["same_base_model"])

            #: FOUR REFERENCE EDGES ACROSS TWO FILES, not two from one.
            self.assertEqual(found["reference_edges"], 4)
            for key in ("b_cov", "c_cov", "n", "z_cov", "b_dir", "c_dir",
                        "n_both"):
                self.assertIn(key, found,
                              "the paired test's own inputs must come out of "
                              "the tool, or a lane computes them by hand again.")

            rows = Path(found["table_path"]).read_text(
                encoding="utf-8").splitlines()
            self.assertEqual(len(rows) - 1, found["reference_edges"],
                             "one row per reference edge, or the table and "
                             "the counts are two different denominators.")
            header = rows[0].split(TAB)
            for column in ("model_base", "model_adapter", "objects_base",
                           "rule_base"):
                self.assertIn(column, header)
            for line in rows[1:]:
                cells = line.split(TAB)
                self.assertTrue(cells[header.index("model_base")].strip(),
                                "an empty model cell is the fault this tool "
                                "was built to make impossible.")

    def test_the_join_is_by_declared_row_id_and_not_by_position(self):
        """THE CONTROL THAT WOULD CATCH THE REAL MIS-JOIN.

        Row 100's answer is right and row 0's is right, and they sit at
        different positions in the two reference files. Under a positional
        join, the answers for 100 and 101 would be scored against rows 0 and
        1 - which has matching counts and produces a plausible table.
        """
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            refs = self._two_references(here)
            base, adapter = self._arms(here)
            found = pair_edge_direction(
                arms=[{"name": "base", "predictions_path": base},
                      {"name": "adapter", "predictions_path": adapter}],
                reference_paths=refs, out_path=str(here / "t.tsv"))
            rows = Path(found["table_path"]).read_text(
                encoding="utf-8").splitlines()[1:]
            ids = sorted({line.split(TAB)[0] for line in rows})
            self.assertEqual(ids, ["0", "1", "100", "101"],
                             "the table lost the reference's own ids, so a "
                             "reader cannot tell which questions were asked.")
            by_id = {line.split(TAB)[0]: line.split(TAB) for line in rows}
            self.assertEqual(by_id["100"][1:3], ["tablet", "ingest"],
                             "row 100 carries another row's edge, which is a "
                             "positional join wearing a plausible table.")

    def test_stripping_ONE_arm_of_its_model_refuses_the_whole_pairing(self):
        """Not both arms - one. A pair is only as identified as its worse half."""
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            refs = self._two_references(here)
            base, adapter = self._arms(here, strip_from="adapter")
            found = pair_edge_direction(
                arms=[{"name": "base", "predictions_path": base},
                      {"name": "adapter", "predictions_path": adapter}],
                reference_paths=refs, out_path=str(here / "t.tsv"))
            self.assertFalse(found["ok"],
                             "one identified arm and one anonymous arm is not "
                             "a pairing; it is a number with half a provenance.")
            self.assertEqual(found["error"], "model_not_recorded")
            self.assertEqual(found["arm"], "adapter",
                             "the refusal must name WHICH arm is anonymous.")
            self.assertFalse((here / "t.tsv").exists(),
                             "a refused pairing wrote a table anyway, which is "
                             "a file somebody will read as a result.")

    def test_an_arm_that_was_never_asked_is_not_an_arm_that_answered_wrong(self):
        """THE FAULT THE DRY RUN FOUND, on a specimen built here.

        A reference edge no arm reached and a reference edge one arm was never
        GIVEN are both `missing` in the outcomes, and the second inflates the
        other arm's `c_cov`. Measured on a real partial run: a base arm that
        timed out after 29 of 40 rows still produced n = 118, so eleven rows
        it never saw counted as edges the challenger gained.
        """
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            refs = self._two_references(here)
            base, adapter = self._arms(here)
            #: The base stops after two rows, as a timed-out arm does.
            kept = [l for l in Path(base).read_text(encoding="utf-8").splitlines()
                    if json.loads(l)["row_id"] in (0, 1)]
            Path(base).write_text(NL.join(kept), encoding="utf-8")

            found = pair_edge_direction(
                arms=[{"name": "base", "predictions_path": base},
                      {"name": "adapter", "predictions_path": adapter}],
                reference_paths=refs, out_path=str(here / "t.tsv"))

            self.assertTrue(found["ok"])
            self.assertFalse(found["both_arms_answered_the_same_rows"],
                             "a partial pairing reported as a whole one is a "
                             "number about questions one arm never received.")
            self.assertEqual(found["rows_only_in_adapter"], ["100", "101"])
            self.assertEqual(found["rows_only_in_base"], [])
            self.assertIn("PARTIAL", found["summary"],
                          "the asymmetry must be where the number is read.")

    def test_a_fresh_baseline_pairs_on_its_declared_id_with_no_positional_fallback(self):
        """THE CONTROL FOR THE WRITER FIX, and it shows what the fix prevents.

        A baseline artefact written after `measure_baseline` learned to carry
        `row_id` numbers its rows positionally in `row_index` AND declares the
        eval file's own id. Against a reference numbered from 100 those two
        disagree, which is exactly the case where a positional join succeeds
        and answers the wrong questions.

        Both halves are asserted: with the id, the right rows; without it, the
        WRONG ones. A test that only checked the first would pass on a tool
        that ignored the id entirely.
        """
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            refs = self._two_references(here)

            def baseline(with_id):
                rows = []
                for position, rid in enumerate((100, 101)):
                    row = {"row_index": position, "model": "a-real-model",
                           "answer": json.dumps(
                               graph(("tablet", "ingest")) if rid == 100
                               else graph(("cache", "store")))}
                    if with_id:
                        row["row_id"] = rid
                    rows.append(row)
                name = "with-id" if with_id else "without-id"
                return str(write(here / (name + ".jsonl"), rows))

            challenger = write(here / "challenger.jsonl", [
                {"row_index": 0, "row_id": 100, "model": "a-real-model",
                 "answer": json.dumps(graph(("tablet", "ingest")))},
                {"row_index": 1, "row_id": 101, "model": "a-real-model",
                 "answer": json.dumps(graph(("cache", "store")))}])

            declared = pair_edge_direction(
                arms=[{"name": "baseline", "predictions_path": baseline(True)},
                      {"name": "challenger", "predictions_path": str(challenger)}],
                reference_paths=refs, out_path=str(here / "a.tsv"))
            self.assertTrue(declared["ok"], declared.get("summary"))
            rows = Path(declared["table_path"]).read_text(
                encoding="utf-8").splitlines()[1:]
            scored = {line.split(TAB)[0] for line in rows
                      if line.split(TAB)[3] != "missing"}
            self.assertEqual(
                scored, {"100", "101"},
                "the baseline's answers landed on rows it never answered, so "
                "the declared id was ignored in favour of the position.")

            #: THE SAME FILE WITHOUT THE ID. It used to fall back to the
            #: POSITION, resolve to reference row 0, and score the answer
            #: against a system it was never shown - silently, with a
            #: plausible table. Measured on run 2, whose eval carried no
            #: row_id and whose twenty rows had to be matched to a reference
            #: BY COMPARING PROMPT TEXT, because the numbers alone could not
            #: say which twenty they were. That check happened by hand.
            inferred = pair_edge_direction(
                arms=[{"name": "baseline", "predictions_path": baseline(False)},
                      {"name": "challenger", "predictions_path": str(challenger)}],
                reference_paths=refs, out_path=str(here / "b.tsv"))
            self.assertFalse(
                inferred["ok"],
                "a positional join across two reference sets was accepted. "
                "Nothing about an index says which set it counts within, and "
                "one that is a valid id in the other set joins confidently "
                "to the wrong questions.")
            self.assertEqual(inferred["error"],
                             "positional_join_across_several_references")
            self.assertEqual(inferred["arms"], ["baseline"],
                             "the refusal must name WHICH arm lacks the id.")
            self.assertFalse((here / "b.tsv").exists(),
                             "a refused pairing wrote a table anyway.")

    def test_one_reference_and_no_id_still_pairs(self):
        """THE CASE THAT MUST NOT BE REFUSED, or the rule is too strict.

        With a single named reference, a positional index is the caller's own
        provenance claim and there is no other set for it to belong to. Run 2
        is exactly this shape, and refusing it would have blocked a legitimate
        scoring rather than caught a mis-join.
        """
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            one = write(here / "held-out.jsonl", [
                {"row_id": 0, "expected": graph(("browser", "rest api"))},
                {"row_id": 1, "expected": graph(("worker", "queue"))}])
            rows = [{"row_index": 0, "model": "m",
                     "answer": json.dumps(graph(("browser", "rest api")))},
                    {"row_index": 1, "model": "m",
                     "answer": json.dumps(graph(("worker", "queue")))}]
            left = write(here / "a.jsonl", rows)
            right = write(here / "b.jsonl", rows)
            found = pair_edge_direction(
                arms=[{"name": "base", "predictions_path": str(left)},
                      {"name": "adapter", "predictions_path": str(right)}],
                reference_paths=[str(one)], out_path=str(here / "t.tsv"))
            self.assertTrue(found["ok"], found.get("summary"))
            self.assertEqual(found["arms"][0]["join"], "position",
                             "the join basis must be reported even when it is "
                             "safe, or a reader cannot tell which runs rest "
                             "on a declared id and which on a position.")
    def test_both_names_for_the_adapter_field_are_read(self):
        """TWO NAMES FOR ONE FIELD, BOTH IN THE WILD.

        The recipe on main writes `adapter`; artefacts from a recipe version
        that no longer exists write `adapter_dir` - run 2's predictions are
        that shape. A reader that knows only one name reports \"no adapter\"
        for an arm that names one perfectly well, which is a provenance gap
        invented by the reader rather than found in the artefact.
        """
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            one = write(here / "ref.jsonl",
                        [{"row_id": 0, "expected": graph(("a", "b"))}])
            answer = json.dumps(graph(("a", "b")))
            old = write(here / "old.jsonl", [
                {"row_index": 0, "model": "m", "answer": answer,
                 "adapter_dir": "/somewhere/run2/adapter"}])
            new = write(here / "new.jsonl", [
                {"row_index": 0, "model": "m", "answer": answer,
                 "adapter": "/somewhere/run3/adapter"}])
            found = pair_edge_direction(
                arms=[{"name": "older", "predictions_path": str(old)},
                      {"name": "newer", "predictions_path": str(new)}],
                reference_paths=[str(one)], out_path=str(here / "t.tsv"))
            self.assertTrue(found["ok"], found.get("summary"))
            older, newer = found["arms"]
            self.assertEqual(older["adapter"], "/somewhere/run2/adapter")
            self.assertEqual(older["adapter_field"], "adapter_dir",
                             "the field name that answered must be reported: "
                             "a field that moved dates the recipe.")
            self.assertEqual(newer["adapter"], "/somewhere/run3/adapter")
            self.assertEqual(newer["adapter_field"], "adapter")

    def test_a_base_arm_names_no_adapter_and_says_so(self):
        """None is the right answer for the control, not a missing key."""
        with tempfile.TemporaryDirectory() as scratch:
            here = Path(scratch)
            one = write(here / "ref.jsonl",
                        [{"row_id": 0, "expected": graph(("a", "b"))}])
            answer = json.dumps(graph(("a", "b")))
            rows = [{"row_index": 0, "model": "m", "answer": answer}]
            left = write(here / "l.jsonl", rows)
            right = write(here / "r.jsonl", rows)
            found = pair_edge_direction(
                arms=[{"name": "base", "predictions_path": str(left)},
                      {"name": "also", "predictions_path": str(right)}],
                reference_paths=[str(one)], out_path=str(here / "t.tsv"))
            self.assertIsNone(found["arms"][0]["adapter"])
            self.assertIsNone(found["arms"][0]["adapter_field"])

    def test_a_real_artefact_pair_carrying_model_is_accepted(self):
        """The same path over real predictions, when the machine has them.

        run_16's arms are WITHDRAWN EVIDENCE - the arm was retired because one
        of its branches was unreachable - so nothing here asserts a coverage
        figure. **The numbers mean nothing and the path means everything.**
        Enshrining a withdrawn measurement in a fixture is how a retired
        number gets quoted back a week later.
        """
        run = None
        for found in (REPO / "runs").glob("*/sandboxes/*/runs/run_16"):
            if (found / "predictions_base.jsonl").is_file():
                run = found
        if run is None:
            self.skipTest("run_16 is not in this checkout; runs/ is gitignored")
        refs = [str(REPO / "evals" / "architecture-json" / "held-out.jsonl"),
                str(REPO / "evals" / "architecture-json" / "held-out-extra.jsonl")]
        with tempfile.TemporaryDirectory() as scratch:
            found = pair_edge_direction(
                arms=[{"name": "base",
                       "predictions_path": str(run / "predictions_base.jsonl")},
                      {"name": "adapter",
                       "predictions_path": str(run / "predictions.jsonl")}],
                reference_paths=refs,
                out_path=str(Path(scratch) / "t.tsv"))
            self.assertTrue(found["ok"], found.get("summary"))
            self.assertEqual(
                found["arms"][0]["model_source"],
                "the predictions rows themselves",
                "a real run stopped carrying its model per row, so the tool "
                "fell back to a config or a log - which is the weaker "
                "provenance refusal 6 was written to retire.")
            self.assertTrue(found["same_base_model"])
if __name__ == "__main__":
    unittest.main()
