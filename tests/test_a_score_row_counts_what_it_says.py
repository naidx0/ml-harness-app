"""The seven numbers are read off the rows, and say which rows they came from.

`scripts/score_row.py` is shared by two callers that must not disagree - the
tuning loop scoring an arm and the nightly journey scoring a night - so it is
tested here rather than inside either of them. A row computation tested only
through its caller is a row computation that gets two implementations.

WHAT THESE TESTS ARE REALLY DEFENDING is the difference between a zero and a
`None`. Six of the seven numbers can come out zero for two completely opposite
reasons: a harness that called no tools has no refusal rate, and reporting it
as `0.0` scores the run that did nothing as the run that did everything right.
Every rate here is asserted `None` on an empty denominator, in its own test,
because that is the assertion a future simplification will delete first.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import db, events  # noqa: E402

score_row = support.import_file("score_row", REPO / "scripts" / "score_row.py")

NL = chr(10)

#: Six steps, five of them ticked, and the shapes written loosely on purpose:
#: `- []` and `-[x]` are what a model actually produces, and a parser that
#: stops seeing them reports a run that did the work as one that did none.
PLAN_FIVE_OF_SIX = NL.join([
    "# Train a classifier",
    "",
    "## Phase 1 - Data",
    "- [x] Carve the eval set with carve_eval_set",
    "-[x] Preview five rows with preview_dataset_rows",
    "- [X] Profile the repository",
    "",
    "## Phase 2 - Baseline",
    "- [x] Measure the baseline",
    "- [x] Record the baseline row",
    "- [] Fit the classical branch",
])


def a_thread(title: str = "arm", *, permission: str = "full") -> int:
    """A thread at a named permission, and nothing else assumed."""
    thread_id = int(events.create_thread(title)["id"])
    with db.session() as connection:
        connection.execute(
            "UPDATE threads SET permission = ? WHERE id = ?", (permission, thread_id)
        )
    return thread_id


def a_turn(
    thread_id: int,
    *,
    system: int = 400,
    tools: int = 200,
    history: int = 100,
    tool_count: int = 9,
    instruction_set: str = "abc123def456",
    ending: str = "answered",
) -> None:
    """One whole turn's worth of events, in the order the conductor writes them."""
    events.append(
        score_row.TURN_STARTED,
        {"model": "granite4-hermes", "instruction_set": instruction_set},
        thread_id=thread_id,
    )
    events.append(
        score_row.TURN_CONTEXT,
        {
            "system": system,
            "tools": tools,
            "history": history,
            "tool_count": tool_count,
            "total": system + tools + history,
            "mode": "build",
        },
        thread_id=thread_id,
    )
    events.append(score_row.STREAM_END, {"ending": ending, "rounds": 2}, thread_id=thread_id)


def a_call(thread_id: int, name: str, *, refused: bool = False, how: str = "envelope") -> None:
    """A tool call and its result. `how` picks which of the two refusal shapes."""
    events.append(score_row.TOOL_CALL, {"id": name, "name": name, "arguments": {}}, thread_id=thread_id)
    if not refused:
        payload = {"id": name, "name": name, "ok": True, "result": {"ok": True, "rows": 5}}
    elif how == "envelope":
        payload = {"id": name, "name": name, "ok": False, "result": {"ok": False, "error": "tool_failed"}}
    else:
        # THE SECOND SHAPE, and the reason both are tested: a tool that ran and
        # reported its own failure inside an `ok` envelope. Counting only the
        # first missed every self-reported refusal in the product.
        payload = {"id": name, "name": name, "ok": True, "result": {"error": "not_a_plan"}}
    events.append(score_row.TOOL_RESULT, payload, thread_id=thread_id)


class AScoreRowCountsWhatItSaysTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.db_path = db.DB_PATH

    def row(self, thread_id: int) -> dict:
        return score_row.compute_row(self.db_path, thread_id)

    # -- the plan, and whether it was written on turn 1 --------------------

    def test_a_plan_written_before_the_first_run_turn_is_a_plan_on_turn_one(self) -> None:
        thread = a_thread()
        a_turn(thread)
        events.append(score_row.PLAN_WRITTEN, {"phases": 2, "steps_open": 6}, thread_id=thread)
        events.append(score_row.RUN_TURN, {"turn": 1, "open": 6}, thread_id=thread)
        self.assertTrue(self.row(thread)["plan_written_on_turn_1"])

    def test_a_plan_written_after_the_first_run_turn_is_not(self) -> None:
        thread = a_thread()
        a_turn(thread)
        events.append(score_row.RUN_TURN, {"turn": 1, "open": 0}, thread_id=thread)
        events.append(score_row.PLAN_WRITTEN, {"phases": 2, "steps_open": 6}, thread_id=thread)
        self.assertFalse(
            self.row(thread)["plan_written_on_turn_1"],
            "a plan written on turn 2 is a plan on turn 2",
        )

    def test_a_plan_with_no_turn_at_all_is_not_a_plan_on_turn_one(self) -> None:
        thread = a_thread()
        events.append(score_row.PLAN_WRITTEN, {"phases": 2}, thread_id=thread)
        self.assertFalse(
            self.row(thread)["plan_written_on_turn_1"],
            "the row scores a run, and there was no turn 1 to write it on",
        )

    def test_a_thread_driven_without_a_run_still_has_a_turn_one(self) -> None:
        """No `run.turn` rows at all - the boundary falls back to `stream.end`.

        A thread driven by bare `POST /turn` calls never gets a `run.turn`, and
        a boundary that knew only about runs would report False here for every
        arm: a number that looks like a finding and is an artefact of the
        driver.
        """
        thread = a_thread()
        events.append(score_row.TURN_STARTED, {"instruction_set": "aaa"}, thread_id=thread)
        events.append(score_row.PLAN_WRITTEN, {"phases": 2}, thread_id=thread)
        events.append(score_row.STREAM_END, {"ending": "answered"}, thread_id=thread)
        self.assertTrue(self.row(thread)["plan_written_on_turn_1"])

    def test_without_a_run_a_plan_written_on_turn_two_is_still_turn_two(self) -> None:
        thread = a_thread()
        a_turn(thread)
        events.append(score_row.PLAN_WRITTEN, {"phases": 2}, thread_id=thread)
        a_turn(thread)
        self.assertFalse(
            self.row(thread)["plan_written_on_turn_1"],
            "the fallback is a boundary, not a pass",
        )

    def test_run_turn_wins_over_stream_end_when_both_are_there(self) -> None:
        """The two callers must agree on any thread that had a run.

        `stream.end` comes first inside a turn and `run.turn` closes it, so a
        plan written between them is written on turn 1 under the preferred
        boundary and would read False under the fallback. Preferring
        `run.turn` is what keeps the nightly journey and the tuning loop
        reporting the same number for the same thread.
        """
        thread = a_thread()
        events.append(score_row.TURN_STARTED, {"instruction_set": "aaa"}, thread_id=thread)
        events.append(score_row.STREAM_END, {"ending": "answered"}, thread_id=thread)
        events.append(score_row.PLAN_WRITTEN, {"phases": 2}, thread_id=thread)
        events.append(score_row.RUN_TURN, {"turn": 1, "open": 6}, thread_id=thread)
        self.assertTrue(self.row(thread)["plan_written_on_turn_1"])

    # -- the work ----------------------------------------------------------

    def test_five_of_six_steps_are_counted_through_loosely_written_lines(self) -> None:
        thread = a_thread()
        events.set_thread_plan(thread, PLAN_FIVE_OF_SIX)
        row = self.row(thread)
        self.assertEqual(row["steps_ticked"], 5)
        self.assertEqual(row["steps_open_at_start"], 6)

    def test_a_parked_step_is_neither_ticked_nor_dropped_from_the_denominator(self) -> None:
        thread = a_thread()
        events.set_thread_plan(
            thread,
            NL.join(["## Phase 1", "- [x] Did it", "- [!] Could not - parked: no dataset"]),
        )
        row = self.row(thread)
        self.assertEqual(row["steps_ticked"], 1, "parked is not done")
        self.assertEqual(
            row["steps_open_at_start"], 2, "a step it gave up on still counts against it"
        )

    def test_the_todo_is_read_when_the_checklist_source_says_so(self) -> None:
        thread = a_thread()
        events.set_thread_plan(thread, NL.join(["## Phase 1", "- [x] the plan's step"]))
        with db.session() as connection:
            connection.execute(
                "UPDATE threads SET todo = ?, checklist_source = 'todo' WHERE id = ?",
                (NL.join(["- [ ] one", "- [ ] two", "- [ ] three"]), thread),
            )
        row = self.row(thread)
        self.assertEqual(row["steps_ticked"], 0)
        self.assertEqual(row["steps_open_at_start"], 3, "the todo, not the plan")

    # -- the refusals ------------------------------------------------------

    def test_both_refusal_shapes_are_counted_over_the_calls_that_were_made(self) -> None:
        thread = a_thread()
        a_call(thread, "preview_dataset_rows")
        a_call(thread, "write_plan", refused=True, how="envelope")
        a_call(thread, "measure_baseline", refused=True, how="inside")
        a_call(thread, "carve_eval_set")
        row = self.row(thread)
        self.assertEqual(row["tool_calls"], 4)
        self.assertEqual(row["refusals"], 2, "the envelope's ok:false and the result's error")
        self.assertEqual(row["refusals_per_call"], 0.5)

    def test_no_tool_calls_is_no_refusal_rate_and_not_a_perfect_one(self) -> None:
        thread = a_thread()
        a_turn(thread)
        row = self.row(thread)
        self.assertEqual(row["tool_calls"], 0)
        self.assertIsNone(
            row["refusals_per_call"],
            "a harness that called nothing did not score a flawless 0.0",
        )

    # -- the silences ------------------------------------------------------

    def test_empty_replies_are_counted_over_the_turns_that_could_have_been_empty(self) -> None:
        thread = a_thread()
        a_turn(thread, ending="answered")
        a_turn(thread, ending="empty_reply")
        a_turn(thread, ending="answered_after_empty_reply")
        a_turn(thread, ending="round_cap")
        row = self.row(thread)
        self.assertEqual(row["turns"], 4)
        self.assertEqual(
            row["empty_reply_turns"],
            1,
            "a turn that went quiet and then answered is not a turn the person saw nothing from",
        )
        self.assertEqual(row["empty_replies"], 0.25)

    def test_no_turns_is_no_empty_reply_rate(self) -> None:
        thread = a_thread()
        self.assertIsNone(self.row(thread)["empty_replies"])
        self.assertEqual(self.row(thread)["turns"], 0)

    # -- what the prompt cost before a word --------------------------------

    def test_tokens_before_the_first_word_are_the_first_turns_system_and_tools(self) -> None:
        thread = a_thread()
        a_turn(thread, system=400, tools=200, history=100)
        a_turn(thread, system=400, tools=200, history=9000)
        self.assertEqual(
            self.row(thread)["tokens_before_first_word"],
            600,
            "history is what the work accumulated and is not a fixed cost",
        )

    def test_a_thread_that_never_took_a_turn_reports_no_token_figure(self) -> None:
        self.assertIsNone(self.row(a_thread())["tokens_before_first_word"])

    # -- the questions -----------------------------------------------------

    def test_questions_under_full_are_counted(self) -> None:
        thread = a_thread(permission="full")
        events.add_message(thread, "assistant", "Which dataset should I use?")
        events.add_message(thread, "assistant", "I measured the baseline at 0.62.")
        events.add_message(thread, "user", "Whatever you think?")
        row = self.row(thread)
        self.assertTrue(row["questions_measurable"])
        self.assertEqual(row["questions_asked"], 1, "the user's question is not the model's")

    def test_a_thread_not_at_full_says_the_number_is_not_measurable(self) -> None:
        thread = a_thread(permission="ask")
        events.add_message(thread, "assistant", "Which dataset should I use?")
        row = self.row(thread)
        self.assertFalse(
            row["questions_measurable"],
            "under ask a question is the product working, not a defect",
        )
        self.assertEqual(row["questions_asked"], 0)

    # -- time to the first measurement --------------------------------------

    def test_minutes_run_from_the_thread_to_the_first_measured_row(self) -> None:
        thread = a_thread()
        with db.session() as connection:
            connection.execute(
                "UPDATE threads SET created_at = ? WHERE id = ?",
                ("2026-09-18 10:00:00", thread),
            )
            for stamp, origin in (
                ("2026-09-18 10:01:00", "STATED"),
                ("2026-09-18 10:07:30", "MEASURED"),
                ("2026-09-18 10:09:00", "MEASURED"),
            ):
                connection.execute(
                    "INSERT INTO fact_evidence"
                    "(thread_id, fact, value, origin, actor, tool, how, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (thread, "rows", "5", origin, "model", "t", "how", stamp),
                )
        self.assertEqual(
            self.row(thread)["minutes_to_first_measurement"],
            7.5,
            "the first MEASURED row, and a STATED one is somebody saying so",
        )

    def test_a_thread_that_measured_nothing_reports_no_minutes(self) -> None:
        self.assertIsNone(self.row(a_thread())["minutes_to_first_measurement"])

    # -- the inertness detector ---------------------------------------------

    def test_two_arms_sent_the_same_prompt_share_a_fingerprint(self) -> None:
        one, two = a_thread("one"), a_thread("two")
        a_turn(one, system=400, tools=200, tool_count=9, instruction_set="aaa")
        a_turn(two, system=400, tools=200, tool_count=9, instruction_set="aaa")
        self.assertEqual(
            score_row.instruction_fingerprint(self.db_path, one),
            score_row.instruction_fingerprint(self.db_path, two),
            "same laws, same tools - whatever the knob did, it did not do it here",
        )

    def test_a_different_instruction_set_moves_the_fingerprint(self) -> None:
        one, two = a_thread("one"), a_thread("two")
        a_turn(one, instruction_set="aaa")
        a_turn(two, instruction_set="bbb")
        self.assertNotEqual(
            score_row.instruction_fingerprint(self.db_path, one),
            score_row.instruction_fingerprint(self.db_path, two),
        )

    def test_a_different_tool_schema_cost_moves_the_fingerprint(self) -> None:
        one, two = a_thread("one"), a_thread("two")
        a_turn(one, tools=200, tool_count=9)
        a_turn(two, tools=1400, tool_count=31)
        self.assertNotEqual(
            score_row.instruction_fingerprint(self.db_path, one),
            score_row.instruction_fingerprint(self.db_path, two),
        )

    def test_a_thread_that_never_turned_has_no_fingerprint(self) -> None:
        self.assertIsNone(score_row.instruction_fingerprint(self.db_path, a_thread()))

    # -- the refusals this module makes -------------------------------------

    def test_a_database_that_is_not_there_is_an_error_not_an_empty_run(self) -> None:
        with self.assertRaises(FileNotFoundError) as caught:
            score_row.compute_row(self.root / "no-such-arm.db", 1)
        self.assertIn("no-such-arm.db", str(caught.exception))

    def test_a_thread_that_is_not_there_is_an_error_not_an_empty_run(self) -> None:
        with self.assertRaises(LookupError):
            self.row(99999)

    def test_the_row_carries_every_field_the_csv_writes(self) -> None:
        thread = a_thread()
        a_turn(thread)
        row = self.row(thread)
        for field in score_row.FIELDS:
            self.assertIn(field, row, f"{field} is in FIELDS and not in the row")
        for field in score_row.HEADLINE:
            self.assertIn(field, row, f"{field} is a headline number and not in the row")

    def test_the_reader_cannot_write(self) -> None:
        """The whole isolation, asserted rather than promised in a comment.

        Named exception and named message, not a bare `Exception`: a write that
        failed because the column was misspelt would satisfy a broad assertion
        and prove nothing about the mode the connection was opened in.
        """
        import sqlite3

        thread = a_thread()
        connection = score_row._connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.OperationalError) as caught:
                connection.execute("UPDATE threads SET title = 'moved' WHERE id = ?", (thread,))
                connection.commit()
            self.assertIn("readonly", str(caught.exception))
        finally:
            connection.close()
        self.assertEqual(
            events.get_thread(thread)["title"], "arm", "and the row did not move"
        )


if __name__ == "__main__":
    unittest.main()
