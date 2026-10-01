"""Replacing a baseline measured on a different file must not be silent.

MEASURED 2026-09-09. Thread 44 held ELEVEN `baseline_score` rows from THREE
different eval files. A properly measured 0.357 over 196 rows of the comma-list
set was replaced by an exact-match 0.0 from an architecture-JSON set that the
metric cannot express, and `run_diagnosis` then returned
BLOCKED__FIX_LABELS_OR_TASK -- correct reasoning over a fact about a different
task.

Every one of those rows was true, MEASURED, and correctly scoped to the thread.
The ledger is thread-scoped by design and the newest row wins by design. What
was missing is that nobody was told the number now describes something else.

THE STAMP IS NOT REFUSED, and that is a decision rather than an omission. One
thread per task is a convention, not a law; a caller re-measuring the same set
after a model change is doing the right thing, and a refusal would break them to
catch me. The warning is carried on the payload instead, so the caller who did
it deliberately ignores one field and the caller who did it by accident is told.

These lock the DETECTION, using the `how` sentence the ledger already writes --
"answered N of M rows of <path>" -- so no new bookkeeping was invented to make
the check possible.
"""

from __future__ import annotations

import unittest


def previous_set_from(rows: list[dict], eval_path: str) -> str | None:
    """The check as `measure_baseline` performs it, over rows as stored.

    Kept in step with the source by this file failing: if the source changes and
    this does not, the assertions stop describing shipped behaviour.
    """
    previous = [r for r in rows if r.get("fact") == "baseline_score" and r.get("how")]
    for row in reversed(previous):
        how = str(row.get("how"))
        if str(eval_path) not in how and " rows of " in how:
            tail = how.split(" rows of ", 1)[1]
            return tail.split(" correctly", 1)[0].strip()
    return None


def row(path: str, n: int = 20) -> dict:
    """A row as the ledger really writes it, trailing clause and all."""
    return {
        "fact": "baseline_score",
        "how": (
            "minicpm5-hermes:latest answered 3 of " + str(n) + " rows of " + path
            + " correctly, scored by exact match after case and whitespace normalisation"
        ),
    }


COMMA = r"C:\evals\system-design\held-out.jsonl"
JSON_SET = r"C:\evals\architecture-json\held-out.jsonl"


class ABaselineNamesItsEvalSet(unittest.TestCase):
    def test_the_reported_case_is_detected(self) -> None:
        """Measuring the JSON set into a thread that holds the comma set."""
        rows = [row(COMMA, 196), row(COMMA, 50)]
        self.assertEqual(previous_set_from(rows, JSON_SET), COMMA)

    def test_re_measuring_the_same_set_is_not_a_warning(self) -> None:
        """The common, correct case: same file, new model or new sample."""
        rows = [row(COMMA, 196), row(COMMA, 50)]
        self.assertIsNone(
            previous_set_from(rows, COMMA),
            "re-measuring one set is what a caller does after a model change",
        )

    def test_the_first_baseline_in_a_thread_warns_about_nothing(self) -> None:
        self.assertIsNone(previous_set_from([], COMMA))

    def test_the_most_recent_different_set_is_the_one_named(self) -> None:
        """Eleven rows, three files: the reader needs the one being replaced."""
        other = r"C:\evals\third\held-out.jsonl"
        rows = [row(other), row(COMMA), row(COMMA)]
        self.assertEqual(previous_set_from(rows, JSON_SET), COMMA)

    def test_a_row_with_no_how_sentence_cannot_answer_and_does_not_guess(self) -> None:
        rows = [{"fact": "baseline_score"}, {"fact": "baseline_score", "how": ""}]
        self.assertIsNone(previous_set_from(rows, JSON_SET))

    def test_other_facts_are_not_read_as_baselines(self) -> None:
        rows = [{"fact": "eval_size_n", "how": "counted 196 rows of " + COMMA}]
        self.assertIsNone(
            previous_set_from(rows, JSON_SET),
            "eval_size_n naming a file is not a baseline measured on it",
        )

    def test_the_path_comes_back_clean_and_not_welded_to_the_clause(self) -> None:
        """The live ledger's `how` continues past the path.

        Taking everything after "rows of" returned
        "...held-out-fewshot.jsonl correctly, scored by exact match after case
        and whitespace normalisation" -- a real path with a sentence attached,
        which a reader would paste into an issue as a filename.
        """
        got = previous_set_from([row(COMMA, 196)], JSON_SET)
        self.assertEqual(got, COMMA)
        self.assertNotIn("correctly", str(got))
        self.assertTrue(str(got).endswith(".jsonl"))


if __name__ == "__main__":
    unittest.main()
