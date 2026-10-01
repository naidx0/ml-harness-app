"""The seven numbers, computed from events somebody planted on purpose.

WHY THIS TEST EXISTS AND WHAT IT CANNOT DO. `scripts/nightly_journey.py` drives
a live model for an hour; nothing in a suite can do that, and a driver whose
arithmetic is only ever exercised by the thing it measures is a driver whose
first wrong number arrives in a committed row. So the script has a DRY PATH -
it reads a database that already exists and computes the row from it - and this
file is what that path is for: a transcript with known events in it, and each
of the seven definitions asserted against a number a reader can count by hand.

THE FIXTURE IS BUILT THROUGH THE PRODUCT'S OWN WRITERS. `events.append`,
`events.set_thread_plan`, `events.add_message` - not hand-written SQL - because
a fixture assembled by INSERT is a fixture that can hold a row shape the engine
would never write, and a reader that only ever met that shape would be green
against a database that cannot happen. The two exceptions are timestamps and
`fact_evidence`, and both are exceptions on purpose: `CURRENT_TIMESTAMP` is
`now` and two of these numbers are arithmetic ON time, so the fixture has to be
able to say when.

THE NEGATIVES ARE HALF THE POINT. Every qualifier in a definition is a place a
reading can be wrong in the direction of flattering: `plan_written_on_turn_1`
is nothing unless a plan written LATE reads `no`, `questions_asked` is nothing
unless a question asked before `full` is NOT counted, and
`minutes_to_first_measurement` is nothing unless a STATED row sitting earlier
in the table is ignored. Each of those has a planted case here, so a reading
that stopped looking at the qualifier goes red.
"""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path

import support

nightly = support.import_file(
    "nightly_journey",
    support.REPO_ROOT / "scripts" / "nightly_journey.py",
)


#: The thread's clock. Every stamp in the fixture is relative to this, and the
#: two time-based numbers are counted from it by hand in the assertions.
OPENED = "2026-01-01 00:00:00"


class OneJourneyScoredTest(unittest.TestCase):
    """A planted transcript, and the seven numbers taken off it."""

    def setUp(self):
        self.root = support.sandbox(self)
        from app import db, events, longrun
        from app.tools import planning

        self.db = db
        self.events = events
        self.planning = planning
        longrun.ensure_table()

        self.good = self._a_journey_that_went_well()
        self.bad = self._a_journey_that_did_not()

    # -- the fixtures ----------------------------------------------------

    def _stamp_event(self, event_id: int, when: str) -> None:
        with self.db.session() as connection:
            connection.execute(
                "UPDATE events SET ts = ? WHERE id = ?", (when, int(event_id))
            )

    def _stamp_message(self, message_id: int, when: str) -> None:
        with self.db.session() as connection:
            connection.execute(
                "UPDATE messages SET created_at = ? WHERE id = ?",
                (when, int(message_id)),
            )

    def _stamp_thread(self, thread_id: int, when: str) -> None:
        with self.db.session() as connection:
            connection.execute(
                "UPDATE threads SET created_at = ? WHERE id = ?",
                (when, int(thread_id)),
            )

    def _fact(self, thread_id: int, origin: str, when: str) -> None:
        """One `fact_evidence` row, by INSERT.

        The one place this fixture writes SQL. The product mints these through
        the provenance path, which needs a live tool run to produce one, and
        what is under test here is the READER - which sees a table, not a tool.
        """
        with self.db.session() as connection:
            connection.execute(
                "INSERT INTO fact_evidence "
                "(thread_id, fact, value, origin, actor, tool, how, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    int(thread_id),
                    "accelerator",
                    "RTX 2060 SUPER",
                    origin,
                    "harness",
                    "read_machine",
                    "nvidia-smi",
                    when,
                ),
            )

    def _long_run(self, thread_id: int, state: str, reason: str, turns: int) -> None:
        with self.db.session() as connection:
            connection.execute(
                "INSERT INTO long_runs"
                "(thread_id, state, turns, cap, stop_reason, detail, started_at, updated_at) "
                "VALUES (?, ?, ?, 24, ?, ?, ?, ?)",
                (
                    int(thread_id),
                    state,
                    int(turns),
                    reason,
                    "two ticked; one parked" if reason else "",
                    OPENED,
                    OPENED,
                ),
            )

    def _a_journey_that_went_well(self) -> int:
        """Four steps open at run start, two ticked, one parked, three turns.

        Counted by hand so the assertions can be read without running it:
        three `tool.call`, two refusals (one `ok: false`, one carrying an
        `error` under a true `ok`), three `stream.end` of which the last said
        nothing, and one `turn.context` before a second that must be ignored.
        """
        events = self.events
        thread = events.create_thread("nightly journey")
        thread_id = int(thread["id"])
        self._stamp_thread(thread_id, OPENED)

        permission = events.append(
            "thread.permission", {"id": thread_id, "permission": "full"},
            thread_id=thread_id,
        )
        self._stamp_event(int(permission["id"]), "2026-01-01 00:00:10")

        events.append(
            "turn.context",
            {"system": 900, "tools": 1600, "history": 40, "total": 2540},
            thread_id=thread_id,
        )
        events.append("chat.delta", {"text": "Here is the plan."}, thread_id=thread_id)
        events.append(
            "tool.call", {"id": "c1", "name": "write_plan"}, thread_id=thread_id
        )
        events.append(
            "tool.result",
            {"id": "c1", "name": "write_plan", "ok": True, "result": {"ok": True}},
            thread_id=thread_id,
        )
        #: BEFORE the first `run.turn`, which is the whole of the definition.
        events.append(
            "thread.plan_written",
            {"thread_id": thread_id, "phases": 1, "steps_open": 4},
            thread_id=thread_id,
        )
        events.append(
            "stream.end", {"ending": "answered", "rounds": 2}, thread_id=thread_id
        )

        events.append("run.started", {"thread_id": thread_id, "open": 4},
                      thread_id=thread_id)
        events.append("run.turn", {"turn": 1, "open": 4}, thread_id=thread_id)
        events.append(
            "tool.call", {"id": "c2", "name": "read_files"}, thread_id=thread_id
        )
        #: REFUSAL ONE: the harness said no itself.
        events.append(
            "tool.result",
            {"id": "c2", "name": "read_files", "ok": False,
             "result": {"refused": "that folder is outside the project"}},
            thread_id=thread_id,
        )
        events.append("chat.delta", {"text": "Read the splits."}, thread_id=thread_id)
        events.append("stream.end", {"ending": "answered", "rounds": 2},
                      thread_id=thread_id)

        events.append("run.turn", {"turn": 2, "open": 3}, thread_id=thread_id)
        events.append(
            "tool.call", {"id": "c3", "name": "measure_baseline"}, thread_id=thread_id
        )
        #: REFUSAL TWO: the tool RAN and failed, and `ok` is still true. A
        #: counter that only reads `ok` misses this one, which is the shape the
        #: docstring of `refusals_per_call` says it was written for.
        events.append(
            "tool.result",
            {"id": "c3", "name": "measure_baseline", "ok": True,
             "result": {"error": "there is no eval set"}},
            thread_id=thread_id,
        )
        #: NOTHING SAID between the previous `stream.end` and this one.
        events.append("stream.end", {"ending": "answered", "rounds": 1},
                      thread_id=thread_id)
        #: A SECOND `turn.context`, larger, which the reading must not take.
        events.append(
            "turn.context",
            {"system": 1000, "tools": 1700, "history": 900, "total": 3600},
            thread_id=thread_id,
        )
        events.append(
            "run.finished",
            {"thread_id": thread_id, "reason": "plan_worked_down", "turns": 3,
             "done": 2, "open": 0, "parked": []},
            thread_id=thread_id,
        )

        parked_line = (
            "- [!] measure the baseline"
            + self.planning.PARKED_MARK
            + "there is no eval set"
        )
        plan = chr(10).join(
            [
                "# Train an adapter",
                "",
                "## Phase 1",
                "- [x] read the splits",
                "- [x] write the schema note",
                parked_line,
                "- [ ] train the adapter",
            ]
        )
        events.set_thread_plan(thread_id, plan, mirror=False)

        events.add_message(thread_id, "user", "a massive prompt")
        #: BEFORE `full` was set, so it must NOT be counted. The qualifier in
        #: the definition is the thing this row exists to hold to account.
        early = events.add_message(thread_id, "assistant", "Which dataset did you mean?")
        self._stamp_message(int(early["id"]), "2025-12-31 23:00:00")
        first = events.add_message(thread_id, "assistant", "Which split should I hold out?")
        self._stamp_message(int(first["id"]), "2026-01-01 00:00:20")
        flat = events.add_message(thread_id, "assistant", "Read the splits.")
        self._stamp_message(int(flat["id"]), "2026-01-01 00:01:00")
        second = events.add_message(thread_id, "assistant", "Shall I train now?")
        self._stamp_message(int(second["id"]), "2026-01-01 00:05:00")

        #: A STATED row FIRST and EARLIER, so a reader that took the first row
        #: of the table rather than the first MEASURED one reads 2.0 and fails.
        self._fact(thread_id, "STATED", "2026-01-01 00:02:00")
        self._fact(thread_id, "MEASURED", "2026-01-01 00:07:30")

        self._long_run(thread_id, "done", "plan_worked_down", 3)
        return thread_id

    def _a_journey_that_did_not(self) -> int:
        """The other side of every qualifier, in one thread.

        The plan arrives AFTER the first `run.turn`; nobody ever set `full`;
        no turn was ever assembled; nothing was measured; a `tool.result`
        refused with no `tool.call` before it; and the run was stopped rather
        than finished, so there is no `run.finished` to read a reason off.
        """
        events = self.events
        thread = events.create_thread("the night it stalled")
        thread_id = int(thread["id"])
        self._stamp_thread(thread_id, OPENED)

        events.append("run.started", {"thread_id": thread_id, "open": 0},
                      thread_id=thread_id)
        events.append("run.turn", {"turn": 1, "open": 0}, thread_id=thread_id)
        events.append(
            "thread.plan_written",
            {"thread_id": thread_id, "phases": 1, "steps_open": 2},
            thread_id=thread_id,
        )
        events.append(
            "tool.result",
            {"id": "x1", "name": "train", "ok": False, "result": {"refused": "no card"}},
            thread_id=thread_id,
        )
        events.append("stream.end", {"ending": "answered", "rounds": 1},
                      thread_id=thread_id)

        asked = events.add_message(thread_id, "assistant", "Do you want me to stop?")
        self._stamp_message(int(asked["id"]), "2026-01-01 00:03:00")

        self._long_run(thread_id, "stopped", "", 1)
        return thread_id

    def _score(self, thread_id: int):
        return nightly.score(
            self.db.DB_PATH,
            model="minicpm5-hermes:latest",
            sha="0123456789abcdef",
            today="2026-01-01",
            thread_id=thread_id,
        )

    # -- the seven numbers -----------------------------------------------

    def test_plan_written_on_turn_1_is_yes_when_the_plan_came_first(self):
        self.assertTrue(self._score(self.good).plan_written_on_turn_1)

    def test_plan_written_on_turn_1_is_no_when_the_plan_came_late(self):
        """THE PLANTED NEGATIVE. The row is there, and it is after the first
        `run.turn` - a reading that only asked "is there a plan" says yes."""
        self.assertFalse(self._score(self.bad).plan_written_on_turn_1)

    def test_steps_ticked_is_over_the_steps_open_at_run_start(self):
        row = self._score(self.good)
        self.assertEqual(row.steps_ticked, 2)
        self.assertEqual(row.steps_open_at_run_start, 4)

    def test_the_parked_step_carries_the_reason_written_on_its_line(self):
        row = self._score(self.good)
        self.assertEqual(
            row.parked,
            [{"step": "measure the baseline", "why": "there is no eval set"}],
        )

    def test_refusals_count_both_shapes_over_the_calls(self):
        """`ok: false` AND a result carrying an `error` under a true `ok`.

        Two refusals of three calls. A counter that read only `ok` says one of
        three, which is the optimistic half of the same mistake
        `scripts/did_it_answer_the_question.py` documents at length.
        """
        row = self._score(self.good)
        self.assertEqual((row.refusals, row.tool_calls), (2, 3))
        self.assertEqual(row.refusals_per_call, round(2 / 3, 4))

    def test_no_calls_is_a_rate_of_zero_with_a_numerator_that_says_why(self):
        """The bad night refused once and called nothing, so the rate is 0.0
        and the row's `refusals` is 1. THE DENOMINATOR IS WHY THAT IS NOT A
        CONTRADICTION, and it is in the CSV for exactly this case."""
        row = self._score(self.bad)
        self.assertEqual((row.refusals, row.tool_calls, row.refusals_per_call), (1, 0, 0.0))

    def test_empty_replies_counts_the_turn_that_said_nothing(self):
        row = self._score(self.good)
        self.assertEqual((row.empty_replies, row.replies), (1, 3))

    def test_tokens_before_first_word_is_the_first_turns_system_plus_tools(self):
        """900 + 1600. The second `turn.context` is larger and must be ignored;
        this number is the fixed cost BEFORE any work, not the latest one."""
        self.assertEqual(self._score(self.good).tokens_before_first_word, 2500)

    def test_a_journey_that_never_assembled_a_turn_reads_zero(self):
        self.assertEqual(self._score(self.bad).tokens_before_first_word, 0)

    def test_questions_asked_counts_only_the_ones_asked_while_full(self):
        """Three assistant questions in the thread, one of them before `full`.

        Two. A reading that dropped the qualifier says three, and would report
        the product breaking an instruction it had not been given yet.
        """
        self.assertEqual(self._score(self.good).questions_asked, 2)

    def test_a_question_with_no_permission_row_is_not_counted(self):
        self.assertEqual(self._score(self.bad).questions_asked, 0)

    def test_minutes_to_first_measurement_skips_the_stated_row(self):
        """00:00:00 to 00:07:30 is 7.5 minutes. The STATED row at 00:02:00 sits
        EARLIER in the table, so a reader that took the first row reads 2.0."""
        self.assertEqual(self._score(self.good).minutes_to_first_measurement, 7.5)

    def test_nothing_measured_is_none_and_never_zero(self):
        """`None`, not `0`. Zero would read as instant, which is the opposite
        of what happened."""
        self.assertIsNone(self._score(self.bad).minutes_to_first_measurement)

    # -- what the row carries beside the seven ----------------------------

    def test_the_stop_reason_and_the_plan_come_back_with_the_row(self):
        row = self._score(self.good)
        self.assertEqual(row.stop_reason, "plan_worked_down")
        self.assertEqual(row.turns, 3)
        self.assertIn("train the adapter", row.plan)

    def test_a_run_that_was_stopped_still_names_its_state(self):
        """No `run.finished` was ever written for a stopped run, so a reader
        that only knew that event would report nothing on exactly the nights
        that went long."""
        row = self._score(self.bad)
        self.assertIn("stopped", row.stop_reason)

    def test_what_the_driver_saw_lands_on_the_page(self):
        """The cap, and a journey that broke off, are facts the DATABASE does
        not hold - the engine never wrote them down, the driver watched them
        happen. A page that only rendered the database would be silent about
        the worst nights."""
        row = self._score(self.good)
        row.driver_note = "the driver stopped it at the 60 minute cap"
        self.assertIn("the driver stopped it at the 60 minute cap", nightly.markdown(row))

    def test_a_page_with_no_note_says_the_run_ended_on_its_own(self):
        """A blank line where a fact belongs reads as a fact nobody looked
        for."""
        self.assertIn(
            "the run ended on its own", nightly.markdown(self._score(self.good))
        )

    def test_a_plan_is_quoted_line_by_line_and_opens_no_fence(self):
        """LAW SUBSTITUTED 2026-09-18. This used to fence the plan with a
        longer fence than any it contained. A plan carries `## Phase` headings,
        and a fence does not stop the repo's own markdown carver from
        splitting the page on them: the second live row's file was cut inside
        its fence (tests/test_a_carved_answer_is_whole.py). The plan is now
        quoted with `> ` per line, the way the conductor quotes it into a
        prompt, so nothing in it can open a section or a fence."""
        row = self._score(self.good)
        row.plan = "## Phase 1" + chr(10) + "```bash" + chr(10) + "pip install" + chr(10) + "```"
        page = nightly.markdown(row)
        self.assertIn("> ## Phase 1", page)
        self.assertIn("> pip install", page)
        self.assertNotIn(chr(10) + "```", page)
        self.assertNotIn(chr(10) + "## Phase 1", page)

    def test_every_header_column_has_a_field_under_it(self):
        """THE PAIR, NOT EACH. A header and a line are only right together: a
        column added to one and not the other shifts every value after it, and
        no per-field assertion can see that."""
        row = self._score(self.good)
        self.assertEqual(
            len(nightly.CSV_HEADER.split(",")),
            len(row.csv_line().split(",")),
        )


class TheRowIsWrittenOnceTest(unittest.TestCase):
    """The dry path, end to end: a scratch root in, a page and one line out."""

    def setUp(self):
        self.root = support.sandbox(self)
        from app import db, events

        self.db = db
        thread = events.create_thread("one journey")
        thread_id = int(thread["id"])
        events.append("run.started", {"thread_id": thread_id, "open": 1},
                      thread_id=thread_id)
        events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

        #: A SCRATCH ROOT SHAPED LIKE THE REAL ONE: the database is named
        #: `ml_harness.db` and sits at the root, which is what `MLH_DATA_ROOT`
        #: produces and what `--from-root` is handed.
        self.scratch = self.root / "mlh-nightly" / "2026-01-01"
        self.scratch.mkdir(parents=True)
        shutil.copyfile(self.db.DB_PATH, self.scratch / "ml_harness.db")
        self.out = self.root / "score_rows"

    def _run(self) -> int:
        return nightly.main(
            [
                "--dry-run",
                "--from-root",
                str(self.scratch),
                "--out",
                str(self.out),
                "--model",
                "minicpm5-hermes:latest",
            ]
        )

    def test_a_dry_run_writes_the_row_and_exits_zero(self):
        self.assertEqual(self._run(), 0)
        pages = sorted(self.out.glob("*.md"))
        self.assertEqual(len(pages), 1, "one page per night")
        self.assertIn("minutes_to_first_measurement", pages[0].read_text(encoding="utf-8"))

    def test_rows_csv_gets_exactly_one_line_per_run(self):
        """Two runs, two lines, one header. The header is written only when the
        file is not there; a driver that rewrote the table could lose a night,
        and one that wrote the header twice would break every reader of it."""
        self._run()
        self._run()
        lines = (self.out / "rows.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], nightly.CSV_HEADER)
        self.assertEqual(len(lines), 3, lines)
        for line in lines[1:]:
            self.assertEqual(
                len(line.split(",")), len(nightly.CSV_HEADER.split(","))
            )

    def test_the_line_is_written_with_lf_and_no_carriage_return(self):
        """CRLF in a tracked file is a diff the whole team re-reads. Written as
        bytes, appended in binary, and checked as bytes."""
        self._run()
        self.assertNotIn(b"\r", (self.out / "rows.csv").read_bytes())


class ItRefusesTheCheckoutTest(unittest.TestCase):
    """The guard, on both paths, with a positive control beside it.

    A refusal that cannot be shown to ACCEPT anything is a refusal that might
    just be broken, so the scratch directory is asserted to pass in the same
    class that asserts the checkout fails.
    """

    def setUp(self):
        self.root = support.sandbox(self)

    def test_the_checkout_is_refused_by_its_own_marker(self):
        complaint = nightly.why_this_root_is_not_scratch(support.REPO_ROOT)
        self.assertIsNotNone(complaint)
        self.assertIn("CHECKOUT", complaint)

    def test_a_directory_inside_the_checkout_is_refused_too(self):
        """It carries no marker, and it is still the working tree."""
        inside = support.REPO_ROOT / "docs" / "score_rows"
        self.assertIsNotNone(nightly.why_this_root_is_not_scratch(inside))

    def test_a_scratch_directory_is_accepted(self):
        """THE POSITIVE CONTROL. Without it, a guard that refused everything
        would pass every test above."""
        self.assertIsNone(nightly.why_this_root_is_not_scratch(self.root))

    def test_the_dry_path_exits_two_and_writes_nothing(self):
        out = self.root / "score_rows"
        code = nightly.main(
            ["--dry-run", "--from-root", str(support.REPO_ROOT), "--out", str(out)]
        )
        self.assertEqual(code, 2)
        self.assertFalse(
            out.exists(),
            "the refusal must land before anything is created, or a refused "
            "run still leaves a directory behind in the tree",
        )

    def test_the_owners_port_is_refused_by_name(self):
        """8078 is the engine Max has open. A nightly job that took it would
        take his session away at 03:30, and a default that is merely different
        is one `--port 8078` away from doing it."""
        code = nightly.main(["--port", str(nightly.HIS_PORT)])
        self.assertEqual(code, 2)


class TheDefinitionsAreWrittenDownTest(unittest.TestCase):
    """The README is the contract; this is what keeps it one.

    `docs/score_rows/README.md` defines the seven numbers and the script
    implements them. Nothing can check that the prose is TRUE - but a column
    that exists in the header and is named nowhere in the definition is a
    number nobody agreed to, and that is checkable.
    """

    def test_every_csv_column_is_named_in_the_readme(self):
        readme = (support.REPO_ROOT / "docs" / "score_rows" / "README.md").read_text(
            encoding="utf-8"
        )
        missing = [
            column
            for column in nightly.CSV_HEADER.split(",")
            if column not in readme
        ]
        self.assertEqual(missing, [], "columns in rows.csv that the README never defines")

    def test_the_brief_is_the_one_the_journey_posts(self):
        """The default `--brief-file` has to be there, or every night exits 2
        on a file that was never committed."""
        brief = Path(nightly.DEFAULT_BRIEF)
        self.assertTrue(brief.is_file(), f"{brief} is the default brief and is not there")
        self.assertIn("Full mode: do not ask me anything", brief.read_text(encoding="utf-8"))


class TheSchedulerIsRegisteredByHandTest(unittest.TestCase):
    """The task is registered by a person, once, and by nothing else.

    A scheduled task that appeared as a side effect of a checkout, a test run
    or an agent doing something adjacent would be a job running nightly on a
    machine whose owner never chose it. That is a property of this tree and it
    is checkable, so it is checked here rather than remembered.
    """

    SCHEDULER = support.REPO_ROOT / "scripts" / "schedule_nightly_journey.ps1"
    README = support.REPO_ROOT / "docs" / "score_rows" / "README.md"

    def test_the_script_is_there_with_its_remove_switch(self):
        text = self.SCHEDULER.read_text(encoding="utf-8")
        self.assertIn("[switch]$Remove", text)
        self.assertIn("Register-ScheduledTask", text)
        self.assertIn("Unregister-ScheduledTask", text)

    def test_the_task_name_the_log_and_the_time_are_the_ones_the_readme_names(self):
        """THE PAIR AGAIN. A default changed in one file and not the other
        leaves a person removing a task that is not the one that is running."""
        script = self.SCHEDULER.read_text(encoding="utf-8")
        readme = self.README.read_text(encoding="utf-8")
        for agreed in ("ML Harness nightly journey", "03:30", "nightly.log"):
            self.assertIn(agreed, script, f"{agreed} is not in the scheduler")
            self.assertIn(agreed, readme, f"{agreed} is not in the README")

    def test_the_readme_carries_the_one_command(self):
        readme = self.README.read_text(encoding="utf-8")
        self.assertIn("schedule_nightly_journey.ps1", readme)
        self.assertIn("-Remove", readme)

    #: What RUNNING something looks like in this tree. A line that names the
    #: scheduler and carries one of these is an invocation; a line that only
    #: names it is prose, and `scripts/nightly_journey.py` says in its own
    #: docstring which file schedules it, which is documentation and not a
    #: caller. THE LIMIT IS STATED: a caller assembled out of pieces - a name
    #: built by concatenation, a path read from a config - is not caught, and
    #: catching that would need a call graph rather than a read.
    RUNS_IT = ("subprocess", "Popen", "Start-Process", "powershell", "pwsh", "Invoke-")

    def test_nothing_in_the_product_or_the_scripts_runs_the_registration(self):
        """Derived from the tree, not from a list somebody kept up to date."""
        name = "schedule_nightly_journey"
        callers = []
        for folder in ("app", "scripts"):
            for path in sorted((support.REPO_ROOT / folder).rglob("*")):
                if not path.is_file() or path.suffix not in (".py", ".ps1", ".sh"):
                    continue
                if path.name.startswith(name):
                    continue
                try:
                    body = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for line in body.splitlines():
                    if name in line and any(mark in line for mark in self.RUNS_IT):
                        callers.append(f"{path.name}: {line.strip()}")
        self.assertEqual(
            callers,
            [],
            "these would register a nightly scheduled task on somebody's "
            "machine without them asking for it",
        )

    def test_the_scan_can_see_an_invocation_when_there_is_one(self):
        """THE POSITIVE CONTROL for the scan above. A check that reports zero
        because it cannot see anything passes for ever, and this repository has
        met that twice."""
        line = 'subprocess.run(["powershell", "scripts/schedule_nightly_journey.ps1"])'
        self.assertTrue(
            "schedule_nightly_journey" in line
            and any(mark in line for mark in self.RUNS_IT)
        )


if __name__ == "__main__":
    unittest.main()
