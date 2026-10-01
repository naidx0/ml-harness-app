"""A graded failure run keeps its cases, and two of them compare pairwise.

## What this closes, and why it was the blocker

`app/tools/agents.py` contained no database write of any kind. `run_the_failures`
graded every case, stamped `baseline_success_rate` and `failure_buckets`,
reported, and forgot. The rate reached the ledger; the rows behind it did not.

`docs/PHASES.md` names the six outcomes this ledger reaches most often -
*the tool description is the bug*, *the prompt is the bug*, *constrain the
output*, *fix the context*, *fix the tool*, *one API call* - and every one of
them is a cheap, local fix. **A cheap fix is only worth naming if the person can
find out whether it worked**, and finding that out honestly is a PAIRED
comparison over the same failures asked twice. There was no first recording for
a second one to be compared against, so all six were verdicts that terminated.

`propose.NOT_COVERED` had already written down exactly this, months before the
table existed: *"the paired proof is designed (change description, re-run same
rows, McNemar) and half-built."*

## The two things worth reading twice

**Pairing is by QUESTION, not by row position.** `eval_results` pairs on
`row_index` because an eval set is a file this harness carved and counts
through. A failure set is the person's export, and between two recordings they
will have re-exported it, sorted it, dropped a fixed case or added three new
ones. Pairing on position then compares case 7 of one run against a different
case 7 of the other and calls the difference an improvement. So a case is keyed
by a digest of its input and expected answer, and `test_a_shuffled_export_still_pairs`
is the case that would go red if that were ever traded for an index.

**NO EVIDENCE is inherited rather than re-derived.** `evals.mcnemar` and
`evals.resolution_for` are the eval bench's own functions. A second
implementation of "is this difference real" here would be a second answer, and
the two would disagree within a month.
"""

import json
import tempfile
import unittest
from pathlib import Path

from app import events
from app.tools import REGISTRY, agents

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "agent"
FAILURES = FIXTURES / "journey-failures.jsonl"
AI_LEDGER = "docs/ledgers/ai_engineering.yaml"

FIELDS = {
    "input_field": "input",
    "expected_field": "expected",
    "answer_field": "answer",
}


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write(path: Path, rows: list[dict]) -> str:
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return str(path)


class ARunKeepsWhatItGradedTest(unittest.TestCase):
    def setUp(self):
        import support

        support.sandbox(self)
        self.tmp = Path(tempfile.mkdtemp())
        self.thread = events.create_thread(title="an agent", ledger=AI_LEDGER)["id"]

    def _run(self, path=FAILURES, label=""):
        return REGISTRY.call(
            "run_the_failures",
            {"failures_path": str(path), "label": label, **FIELDS},
            actor="user",
            thread_id=self.thread,
        )

    def test_it_records_the_run_and_one_row_per_case(self):
        result = self._run(label="before")
        self.assertTrue(result["ok"], result)
        recording = result["recording"]
        self.assertIn("run_id", recording)
        self.assertEqual(result["graded"], recording["cases_kept"])

        stored = agents.cases_of(recording["run_id"])
        self.assertEqual(result["graded"], len(stored))
        self.assertEqual(
            result["passed"], sum(1 for row in stored if row["passed"])
        )

    def test_the_label_is_the_persons_and_is_never_invented(self):
        self.assertEqual("", self._run()["recording"]["label"])
        self.assertEqual("after the fix", self._run(label="after the fix")["recording"]["label"])

    def test_a_run_with_no_conversation_never_gets_as_far_as_recording(self):
        """WRITTEN THE OTHER WAY ROUND FIRST, AND THE CODE WAS RIGHT.

        This case began as "it grades and records nothing", on the assumption
        that a recording is the only thing a thread is needed for. It is not:
        a threadless call resolves to the DEFAULT ledger, which is the ML one,
        and this tool measures five facts that ledger has never heard of - so
        it is refused by the domain wall before a single case is graded.

        A recording belongs to one conversation for the same reason every fact
        it produces does, and here those are the same reason twice over. The
        `thread_id is not None` guard in the writer stays as the belt to that
        wall's braces, because an `Instrument` built by hand can have no
        thread and a lost recording must never cost a grading."""
        result = REGISTRY.call(
            "run_the_failures",
            {"failures_path": str(FAILURES), **FIELDS},
            actor="user",
            thread_id=None,
        )
        self.assertFalse(result["ok"])
        self.assertEqual("not_in_this_domain", result["error"])
        self.assertNotIn("recording", result)
        self.assertNotIn("graded", result)

    def test_a_duplicated_question_is_refused_rather_than_averaged(self):
        """A failure export with the same question twice is ordinary. Two
        verdicts for one question is not, because a comparison pairs on the
        question."""
        rows = _rows(FAILURES)
        doubled = _write(self.tmp / "doubled.jsonl", rows + [dict(rows[0])])
        result = self._run(path=doubled)
        recording = result["recording"]
        self.assertEqual(13, result["graded"])
        self.assertEqual(12, recording["cases_kept"])
        self.assertEqual(1, recording["duplicate_questions"])
        self.assertIn("same question", recording["what_that_means"])


class TwoRunsCompareTest(unittest.TestCase):
    def setUp(self):
        import support

        support.sandbox(self)
        self.tmp = Path(tempfile.mkdtemp())
        self.thread = events.create_thread(title="an agent", ledger=AI_LEDGER)["id"]
        self.rows = _rows(FAILURES)

    def _run(self, rows, label):
        path = _write(self.tmp / f"{label.replace(' ', '-')}.jsonl", rows)
        result = REGISTRY.call(
            "run_the_failures",
            {"failures_path": path, "label": label, **FIELDS},
            actor="user",
            thread_id=self.thread,
        )
        self.assertTrue(result["ok"], result)
        return result["recording"]["run_id"]

    def _compare(self, run_id, against):
        return REGISTRY.call(
            "read_agent_results",
            {"run_id": run_id, "against": against},
            actor="user",
            thread_id=self.thread,
        )

    def _fixed(self, how_many):
        """The same failure set with `how_many` cases now answered correctly."""
        rows = [dict(row) for row in self.rows]
        for row in rows[:how_many]:
            row["answer"] = row["expected"]
        return rows

    def test_two_identical_recordings_report_no_difference_at_all(self):
        """Not a small win. Not a positive delta. Nothing changed, and the
        sentence says so in those words."""
        before = self._run(self.rows, "before")
        after = self._run(self.rows, "after")
        report = self._compare(after, before)

        self.assertTrue(report["ok"], report)
        self.assertEqual(12, report["paired_cases"])
        self.assertEqual(0, report["changed"])
        self.assertEqual(0.0, report["delta"])
        self.assertEqual("no_evidence", report["verdict"])
        self.assertIn("Not one", report["says"])

    def test_a_real_improvement_resolves(self):
        before = self._run(self.rows, "before")
        after = self._run(self._fixed(9), "after")
        report = self._compare(after, before)

        self.assertEqual("different", report["verdict"])
        self.assertTrue(report["resolved"])
        self.assertGreater(report["delta"], 0)
        self.assertEqual(9, report["improved"])
        self.assertEqual(0, report["regressed"])
        self.assertLess(report["p_value"], 0.05)
        self.assertIn("real difference", report["says"])

    def test_a_small_improvement_says_no_evidence(self):
        """THE ONE THAT MATTERS. One case out of twelve changing is exactly the
        shape of result a person wants to believe, and twelve failures cannot
        tell it from noise. Reporting it as a win is the defect the eval
        bench's NO EVIDENCE semantics exist to prevent, inherited here rather
        than re-argued."""
        before = self._run(self.rows, "before")
        after = self._run(self._fixed(1), "after")
        report = self._compare(after, before)

        self.assertEqual("no_evidence", report["verdict"])
        self.assertFalse(report["resolved"])
        self.assertGreater(report["delta"], 0, "the rate really did go up")
        self.assertIn("NO EVIDENCE", report["says"])
        self.assertIn("more failures", report["says"])

    def test_a_shuffled_export_still_pairs(self):
        """THE REASON THE KEY IS A QUESTION AND NOT A ROW INDEX. A person who
        re-exports their failures between two recordings gets them in whatever
        order their tool emitted; pairing on position would compare different
        questions to each other and call the difference a result."""
        before = self._run(self.rows, "before")
        shuffled = list(reversed(self._fixed(9)))
        after = self._run(shuffled, "after")
        report = self._compare(after, before)

        self.assertEqual(12, report["paired_cases"])
        self.assertTrue(report["same_question_set"])
        self.assertEqual(9, report["improved"])
        self.assertEqual(0, report["regressed"])

    def test_a_moved_file_still_pairs_because_the_signature_is_the_questions(self):
        """The signature is a digest of the questions, not of the path. Saving
        the same failures somewhere else is not a different subject."""
        before = self._run(self.rows, "before")
        moved = _write(self.tmp / "somewhere-else.jsonl", self.rows)
        after_result = REGISTRY.call(
            "run_the_failures",
            {"failures_path": moved, "label": "after", **FIELDS},
            actor="user",
            thread_id=self.thread,
        )
        report = self._compare(after_result["recording"]["run_id"], before)
        self.assertTrue(report["same_question_set"])
        self.assertEqual(12, report["paired_cases"])

    def test_two_different_question_sets_are_named_rather_than_subtracted(self):
        """A delta measured across two subjects is not a delta. What only one
        run graded is excluded from both sides and counted out loud."""
        before = self._run(self.rows[:8], "before")
        after = self._run(self.rows[4:], "after")
        report = self._compare(after, before)

        self.assertTrue(report["ok"], report)
        self.assertFalse(report["same_question_set"])
        self.assertEqual(4, report["paired_cases"])
        self.assertEqual(4, report["only_in_this_run"])
        self.assertEqual(4, report["only_in_the_other"])
        self.assertIn("not over the same question set", report["says"])

    def test_two_sets_with_nothing_in_common_are_refused(self):
        before = self._run(self.rows[:6], "before")
        after = self._run(self.rows[6:], "after")
        report = self._compare(after, before)

        self.assertFalse(report["ok"])
        self.assertEqual("no_shared_cases", report["error"])
        self.assertIn("nothing to pair", report["summary"])

    def test_a_run_compared_with_itself_is_refused(self):
        only = self._run(self.rows, "only")
        report = self._compare(only, only)
        self.assertFalse(report["ok"])
        self.assertEqual("same_run", report["error"])

    def test_the_test_is_the_eval_benchs_own(self):
        """One implementation of "is this difference real". A second one here
        would be a second answer, and the two would disagree within a month."""
        from app.tools import evals

        before = self._run(self.rows, "before")
        after = self._run(self._fixed(9), "after")
        report = self._compare(after, before)
        self.assertEqual(
            evals.mcnemar(report["improved"], report["regressed"]), report["p_value"]
        )
        self.assertIn("McNemar", report["test"])


class ReadingBackOneRunTest(unittest.TestCase):
    def setUp(self):
        import support

        support.sandbox(self)
        self.thread = events.create_thread(title="an agent", ledger=AI_LEDGER)["id"]

    def test_it_refuses_before_anything_has_been_graded(self):
        report = REGISTRY.call("read_agent_results", {}, actor="user", thread_id=self.thread)
        self.assertFalse(report["ok"])
        self.assertEqual("no_runs", report["error"])
        self.assertIn("run_the_failures", report["summary"])

    def test_it_defaults_to_the_newest_and_says_what_to_do_next(self):
        REGISTRY.call(
            "run_the_failures",
            {"failures_path": str(FAILURES), "label": "first", **FIELDS},
            actor="user",
            thread_id=self.thread,
        )
        report = REGISTRY.call("read_agent_results", {}, actor="user", thread_id=self.thread)
        self.assertTrue(report["ok"], report)
        self.assertEqual("first", report["label"])
        self.assertIn("record your agent's answers again", report["what_now"])

    def test_it_records_no_fact_of_its_own(self):
        """Reading back a run that already happened is not a new reading of
        anything, and a tool that stamped one here would be the laundering
        wall 2 exists to stop."""
        REGISTRY.call(
            "run_the_failures",
            {"failures_path": str(FAILURES), **FIELDS},
            actor="user",
            thread_id=self.thread,
        )
        report = REGISTRY.call("read_agent_results", {}, actor="user", thread_id=self.thread)
        self.assertEqual([], report["measured"])
        self.assertIn("records_nothing", report)
        self.assertEqual((), REGISTRY.get("read_agent_results").measures)

    def test_a_run_from_another_conversation_is_not_readable(self):
        """Thread scoped, for the eval-set leak's reason: a run readable from
        another conversation is a measurement about somebody else's system
        answering this person's gates."""
        REGISTRY.call(
            "run_the_failures",
            {"failures_path": str(FAILURES), **FIELDS},
            actor="user",
            thread_id=self.thread,
        )
        other = events.create_thread(title="another", ledger=AI_LEDGER)["id"]
        report = REGISTRY.call("read_agent_results", {"run_id": 1}, actor="user", thread_id=other)
        self.assertFalse(report["ok"])
        self.assertEqual("no_runs", report["error"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
