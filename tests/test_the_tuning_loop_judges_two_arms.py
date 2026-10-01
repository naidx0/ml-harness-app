"""The half of the tuning loop that decides anything, tested without a card.

`scripts/tune_the_harness.py` needs a GPU to run a matrix, and a GPU is the one
thing a suite cannot have. So the script is split at the seam: everything from
"here are some databases" onwards runs under `--dry-run`, and this file drives
that half end to end against two fixture databases built by hand.

THE FIXTURE IS THE POINT. One arm ticks 5 of its 6 steps and the other ticks 1
of 6 - a gap big enough that six attempts a side can actually see it, which is
itself the demonstration that six attempts usually cannot. The test asserts the
verdict AND that the p-value printed is the one `fisher` returns for that exact
2x2, so a future rewrite that quietly starts approximating is red here rather
than in a report somebody reads six months later.

**A test must own its specimen.** Both databases are built in this file, from
`events.append` and plain SQL, and nothing here reads a database another lane
regenerates. The premise is asserted before the verdict is: if the fixture ever
stops being 5-of-6 against 1-of-6, the first failure says so.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import db, events  # noqa: E402

tune = support.import_file("tune_the_harness", REPO / "scripts" / "tune_the_harness.py")
score_row = support.import_file("score_row_for_tuning", REPO / "scripts" / "score_row.py")
judge_script = support.import_file(
    "the_existing_judge", REPO / "scripts" / "did_it_answer_the_question.py"
)

NL = chr(10)

#: Enough of a preregistration to clear the floor, and it says what would
#: refute it, because a fixture that models a bad prereg teaches the shape.
PREREG = (
    "We expect the treated arm to tick more steps than the control. It would be "
    "refuted by the treated arm ticking the same or fewer, or by refusing more "
    "per call at p < 0.05. KEEP requires beating the control, not clearing a bar."
)


def plan_with(ticked: int, total: int) -> str:
    lines = ["# The task", "", "## Phase 1"]
    for index in range(total):
        mark = "x" if index < ticked else " "
        lines.append(f"- [{mark}] step {index + 1}")
    return NL.join(lines)


class TheTuningLoopJudgesTwoArmsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.out = self.root / "out"

    # -- building two arms, each in its own database -----------------------

    def an_arm(
        self,
        name: str,
        *,
        ticked: int,
        total: int,
        calls: int = 8,
        refused: int = 1,
        instruction_set: str = "laws-aaa",
        tools: int = 200,
    ) -> Path:
        """One scratch root holding one database holding exactly one thread.

        Built by pointing `db.DB_PATH` at the arm's own file and letting the
        product's own migrations make it, so the fixture cannot drift from the
        schema the script will meet on a real arm. Restored afterwards, because
        the next arm needs the same treatment and the sandbox's cleanup is not
        a substitute for leaving the global where you found it.
        """
        root = self.root / name
        root.mkdir(parents=True, exist_ok=True)
        database = root / "arm.db"
        was = db.DB_PATH
        db.DB_PATH = database
        try:
            db.init_db()
            thread_id = int(events.create_thread(f"tuning arm {name}")["id"])
            with db.session() as connection:
                connection.execute(
                    "UPDATE threads SET permission = 'full', plan = ? WHERE id = ?",
                    (plan_with(ticked, total), thread_id),
                )
            events.append(
                score_row.TURN_STARTED,
                {"model": "granite4-hermes", "instruction_set": instruction_set},
                thread_id=thread_id,
            )
            events.append(
                score_row.TURN_CONTEXT,
                {"system": 400, "tools": tools, "history": 60, "tool_count": 9,
                 "total": 460 + tools, "mode": "build"},
                thread_id=thread_id,
            )
            events.append(score_row.PLAN_WRITTEN, {"phases": 1, "steps_open": total}, thread_id=thread_id)
            events.append(score_row.RUN_TURN, {"turn": 1, "open": total}, thread_id=thread_id)
            for index in range(calls):
                events.append(
                    score_row.TOOL_CALL,
                    {"id": f"c{index}", "name": "preview_dataset_rows", "arguments": {}},
                    thread_id=thread_id,
                )
                bad = index < refused
                events.append(
                    score_row.TOOL_RESULT,
                    {
                        "id": f"c{index}",
                        "name": "preview_dataset_rows",
                        "ok": not bad,
                        "result": {"ok": False, "error": "tool_failed"} if bad else {"ok": True},
                    },
                    thread_id=thread_id,
                )
            events.append(score_row.STREAM_END, {"ending": "answered", "rounds": 2}, thread_id=thread_id)
        finally:
            db.DB_PATH = was
        return root

    def two_arms(self, **kwargs) -> tuple[Path, Path]:
        control = self.an_arm("control", ticked=1, total=6, **kwargs)
        treated = self.an_arm("treated", ticked=5, total=6, **kwargs)
        return control, treated

    def a_matrix(self) -> Path:
        path = self.root / "matrix.json"
        path.write_text(
            json.dumps(
                {
                    "name": "fixture",
                    "prereg": PREREG,
                    "task": {"brief_file": "docs/tuning/brief-classify-tickets.md",
                             "model": "granite4-hermes"},
                    "turns_cap": 12,
                    "repeats": 1,
                    "arms": [{"name": "control", "env": {}},
                             {"name": "treated", "env": {"MLH_ALL_SCHEMAS": "0"}}],
                }
            ),
            encoding="utf-8",
        )
        return path

    def dry_run(self, control: Path, treated: Path, matrix: Path | None = None) -> int:
        return tune.main(
            [
                str(matrix or self.a_matrix()),
                "--dry-run",
                "--arm", f"control={control}",
                "--arm", f"treated={treated}",
                "--out", str(self.out),
            ]
        )

    def report(self) -> str:
        return (self.out / "report.md").read_text(encoding="utf-8")

    def rows(self) -> list[dict[str, str]]:
        with (self.out / "rows.csv").open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    # -- the premise, asserted before anything is concluded from it --------

    def test_the_fixture_really_is_five_of_six_against_one_of_six(self) -> None:
        control, treated = self.two_arms()
        with sqlite3.connect(control / "arm.db") as connection:
            ids = [int(r[0]) for r in connection.execute("SELECT id FROM threads")]
        self.assertEqual(len(ids), 1, "an arm is one thread")
        self.assertEqual(
            score_row.compute_row(control / "arm.db", ids[0])["steps_ticked"], 1
        )
        self.assertEqual(
            score_row.compute_row(control / "arm.db", ids[0])["steps_open_at_start"], 6
        )
        with sqlite3.connect(treated / "arm.db") as connection:
            other = [int(r[0]) for r in connection.execute("SELECT id FROM threads")]
        self.assertEqual(
            score_row.compute_row(treated / "arm.db", other[0])["steps_ticked"], 5
        )

    # -- the verdict, and the p that carries it ----------------------------

    def test_five_of_six_against_one_of_six_does_not_reach_a_verdict(self) -> None:
        """THE FIXTURE THE SPEC ASKED FOR, AND ITS ANSWER IS NO DIFFERENCE.

        This is the whole argument for the script, sitting in one assertion.
        Five of six against one of six is a 67-POINT GAP - the largest
        difference anybody would ever hope to see between two harness
        configurations - and at six attempts a side Fisher puts it at p=0.080,
        which does not clear 0.05. The run cannot tell the arms apart.

        The temptation, when this is red for somebody, will be to raise alpha
        or to call 0.08 "trending". It is neither. The resolution sentence in
        the same report says the run could not have resolved anything below
        about 57 points; the honest move is more attempts, which is what
        `test_ten_of_twelve_against_two_of_twelve_is_kept` shows.
        """
        control, treated = self.two_arms()
        self.assertEqual(self.dry_run(control, treated), 0)
        report = self.report()
        self.assertIn("**`treated`: NO DIFFERENCE**", report)
        self.assertIn("5 of 6", report)
        self.assertIn("1 of 6", report)

    def test_the_p_value_is_the_existing_fisher_functions_answer(self) -> None:
        """Not 'a p value was printed' - THAT p value, from THAT function.

        `fisher(5, 1, 1, 5)` is the 2x2 the fixture builds: five ticked and one
        not for the treated arm, one ticked and five not for the control.

        The function is identified by the FILE ITS CODE CAME FROM rather than
        by object identity. Both modules are loaded by path, so two loads make
        two function objects that are not `is` each other while being the same
        source - and an identity assertion would be red for a reason that has
        nothing to do with the thing it is guarding, which is a copy of the
        test appearing in this repository.
        """
        self.assertTrue(
            tune.fisher.__code__.co_filename.endswith("did_it_answer_the_question.py"),
            f"the tuning loop's Fisher came from {tune.fisher.__code__.co_filename}, "
            "which is not the repository's one",
        )
        expected = judge_script.fisher(5, 1, 1, 5)
        self.assertAlmostEqual(
            expected, 0.080, places=3, msg="six a side resolves almost nothing"
        )
        self.assertEqual(tune.fisher(5, 1, 1, 5), expected)
        control, treated = self.two_arms()
        self.dry_run(control, treated)
        self.assertIn(f"{expected:.3f}", self.report())

    def test_ten_of_twelve_against_two_of_twelve_is_kept(self) -> None:
        """The only case in this file that produces KEEP, and it needs 12 a side.

        The same 67-point gap as the test above, twice as many attempts:
        p=0.003. Nothing about the harness changed between those two tests -
        only how much of it was measured.
        """
        control = self.an_arm("control", ticked=2, total=12)
        treated = self.an_arm("treated", ticked=10, total=12, instruction_set="laws-bbb")
        self.assertEqual(self.dry_run(control, treated), 0)
        report = self.report()
        self.assertIn("**`treated`: KEEP**", report)
        self.assertIn("83%", report, "the rate is printed beside the verdict")
        self.assertIn(f"{judge_script.fisher(10, 2, 2, 10):.3f}", report)

    def test_two_arms_that_did_the_same_work_are_no_difference(self) -> None:
        control = self.an_arm("control", ticked=6, total=12)
        treated = self.an_arm("treated", ticked=6, total=12, instruction_set="laws-bbb")
        self.assertEqual(self.dry_run(control, treated), 0)
        self.assertIn("**`treated`: NO DIFFERENCE**", self.report())

    def test_an_arm_that_ticks_fewer_is_worse_not_merely_different(self) -> None:
        control = self.an_arm("control", ticked=10, total=12)
        treated = self.an_arm("treated", ticked=2, total=12, instruction_set="laws-bbb")
        self.assertEqual(self.dry_run(control, treated), 0)
        self.assertIn("**`treated`: WORSE**", self.report())

    def test_repeats_are_pooled_and_not_averaged(self) -> None:
        """Two repeats of 5-of-6 is 10 of 12, and 10 of 12 is what is tested.

        Asserted on `judge` directly rather than through a run, because
        `--dry-run` takes one root per arm and repeats are a live-run shape.
        The claim the report makes about pooling is checked here or nowhere.
        """
        rows = []
        for repeat in (1, 2):
            rows.append({"name": "control", "repeat": repeat, "steps_ticked": 1,
                         "steps_open_at_start": 6, "refusals": 0, "tool_calls": 8})
            rows.append({"name": "treated", "repeat": repeat, "steps_ticked": 5,
                         "steps_open_at_start": 6, "refusals": 0, "tool_calls": 8})
        verdicts = tune.judge(rows)
        pair = verdicts["pairs"][0]
        self.assertEqual(pair["steps_ticked"], [10, 12], "summed, not averaged to 83%")
        self.assertEqual(pair["control_steps_ticked"], [2, 12])
        self.assertAlmostEqual(pair["steps_ticked_p"], judge_script.fisher(10, 2, 2, 10))
        self.assertEqual(
            pair["verdict"],
            "KEEP",
            "the second repeat is what made the same gap decidable",
        )

    def test_a_matrix_of_three_arms_gets_two_pairs_and_two_verdicts(self) -> None:
        """Everything else in this file has exactly two arms, which is the
        shape that hides an off-by-one in the pairing and a knob table that
        describes only the last arm's variables."""
        rows = [
            {"name": "control", "repeat": 1, "steps_ticked": 2, "steps_open_at_start": 12,
             "refusals": 1, "tool_calls": 8, "fingerprint": "base"},
            {"name": "a", "repeat": 1, "steps_ticked": 10, "steps_open_at_start": 12,
             "refusals": 1, "tool_calls": 8, "fingerprint": "aaa"},
            {"name": "b", "repeat": 1, "steps_ticked": 3, "steps_open_at_start": 12,
             "refusals": 1, "tool_calls": 8, "fingerprint": "bbb"},
        ]
        matrix = {
            "name": "three", "prereg": PREREG,
            "task": {"model": "m", "brief_file": "b.md"}, "turns_cap": 12,
            "arms": [
                {"name": "control", "env": {"MLH_ALL_SCHEMAS": "1"}},
                {"name": "a", "env": {"MLH_ALL_LAWS": "1"}},
                {"name": "b", "env": {"MLH_FOOTER_VARIANT": "terse"}},
            ],
        }
        verdicts = tune.judge(rows)
        self.assertEqual([p["arm"] for p in verdicts["pairs"]], ["a", "b"])
        self.assertEqual([p["verdict"] for p in verdicts["pairs"]], ["KEEP", "NO DIFFERENCE"])

        self.out.mkdir(parents=True, exist_ok=True)
        tune.write_report(
            self.out / "report.md", matrix, rows, verdicts, tune.inertness(rows), True
        )
        report = self.report()
        self.assertIn("**`a`: KEEP**", report)
        self.assertIn("**`b`: NO DIFFERENCE**", report)
        for knob in ("MLH_ALL_SCHEMAS", "MLH_ALL_LAWS", "MLH_FOOTER_VARIANT"):
            self.assertIn(f"- `{knob}` - ", report, f"{knob} is not described")

    def test_writing_two_reports_in_one_process_describes_the_knobs_twice(self) -> None:
        """The knob table is built from a module-level dict, and a first
        version consumed it with `pop`, so the second report in one process
        described no knobs at all."""
        rows = [
            {"name": "control", "repeat": 1, "steps_ticked": 2, "steps_open_at_start": 12,
             "refusals": 0, "tool_calls": 8, "fingerprint": "base"},
            {"name": "treated", "repeat": 1, "steps_ticked": 10, "steps_open_at_start": 12,
             "refusals": 0, "tool_calls": 8, "fingerprint": "aaa"},
        ]
        matrix = {
            "name": "twice", "prereg": PREREG,
            "task": {"model": "m", "brief_file": "b.md"}, "turns_cap": 12,
            "arms": [{"name": "control", "env": {"MLH_ALL_SCHEMAS": "1"}},
                     {"name": "treated", "env": {"MLH_ALL_SCHEMAS": "0"}}],
        }
        verdicts, inert = tune.judge(rows), tune.inertness(rows)
        self.out.mkdir(parents=True, exist_ok=True)
        first = self.out / "first.md"
        second = self.out / "second.md"
        tune.write_report(first, matrix, rows, verdicts, inert, True)
        tune.write_report(second, matrix, rows, verdicts, inert, True)
        self.assertEqual(
            first.read_bytes(), second.read_bytes(), "the same inputs, the same report"
        )
        self.assertIn("- `MLH_ALL_SCHEMAS` - ", second.read_text(encoding="utf-8"))

    def test_an_arm_with_no_attempts_gets_no_p_rather_than_a_made_up_one(self) -> None:
        """A 2x2 needs four cells. An empty margin is not a zero."""
        rows = [
            {"name": "control", "steps_ticked": 3, "steps_open_at_start": 6,
             "refusals": 1, "tool_calls": 8},
            {"name": "treated", "steps_ticked": 0, "steps_open_at_start": 0,
             "refusals": 0, "tool_calls": 0},
        ]
        pair = tune.judge(rows)["pairs"][0]
        self.assertIsNone(pair["steps_ticked_p"])
        self.assertIsNone(pair["refusals_p"])
        self.assertEqual(pair["verdict"], "NO DIFFERENCE")

    def test_an_arm_that_refuses_more_for_the_same_work_is_worse(self) -> None:
        """The direction is read off the rates, not off the p alone.

        Both arms tick 3 of 6, so `steps_ticked` cannot separate them; the
        treated arm refuses 14 of 20 against the control's 1 of 20. An arm that
        did the same work with the harness saying no four times as often is
        WORSE, and a script that only asked "is p small?" would have called it
        a finding to keep.
        """
        control = self.an_arm("control", ticked=3, total=6, calls=20, refused=1)
        treated = self.an_arm(
            "treated", ticked=3, total=6, calls=20, refused=14, instruction_set="laws-bbb"
        )
        self.assertEqual(self.dry_run(control, treated), 0)
        report = self.report()
        self.assertIn("**`treated`: WORSE**", report)
        self.assertIn("more refusals", report)

    # -- inertness ---------------------------------------------------------

    def test_two_arms_sent_the_same_prompt_are_named_inert(self) -> None:
        control, treated = self.two_arms()
        self.dry_run(control, treated)
        report = self.report()
        self.assertIn("INERT", report)
        self.assertIn("the engine did not read this knob", report)
        self.assertIn(
            "so the verdict is about noise",
            report,
            "an inert arm's verdict must not be read as evidence about the knob",
        )

    def test_an_arm_sent_a_different_prompt_is_not_inert(self) -> None:
        control = self.an_arm("control", ticked=1, total=6, tools=200)
        treated = self.an_arm("treated", ticked=5, total=6, tools=1400)
        self.dry_run(control, treated)
        report = self.report()
        self.assertIn("the knob was read", report)
        self.assertNotIn("the engine did not read this knob", report)

    # -- what the report owes the reader -----------------------------------

    def test_the_report_quotes_the_preregistration_above_the_numbers(self) -> None:
        control, treated = self.two_arms()
        self.dry_run(control, treated)
        report = self.report()
        self.assertIn("> " + PREREG.split(".")[0], report)
        self.assertLess(
            report.index("preregistered"),
            report.index("Fisher"),
            "the prereg is quoted before the numbers, not after them",
        )

    def test_the_report_says_what_the_run_could_not_have_seen(self) -> None:
        control, treated = self.two_arms()
        self.dry_run(control, treated)
        report = self.report()
        self.assertIn("What this run could not have seen", report)
        self.assertIn("two arms differ only above ~", report)
        self.assertIn("attempts", report)

    def test_every_rate_ships_the_counts_it_was_computed_from(self) -> None:
        control, treated = self.two_arms()
        self.dry_run(control, treated)
        rows = self.rows()
        self.assertEqual({row["arm"] for row in rows}, {"control", "treated"})
        for row in rows:
            self.assertEqual(int(row["refusals"]), 1)
            self.assertEqual(int(row["tool_calls"]), 8)
            self.assertAlmostEqual(float(row["refusals_per_call"]), 1 / 8)

    # -- the refusals ------------------------------------------------------

    def test_a_matrix_with_no_preregistration_will_not_run(self) -> None:
        path = self.root / "bare.json"
        path.write_text(
            json.dumps(
                {
                    "task": {"brief_file": "b.md", "model": "m"},
                    "arms": [{"name": "control"}, {"name": "treated"}],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(tune.MatrixError) as caught:
            tune.read_matrix(path)
        self.assertIn("preregistration", str(caught.exception))

    def test_a_placeholder_preregistration_is_not_one(self) -> None:
        path = self.root / "tbd.json"
        path.write_text(
            json.dumps(
                {
                    "prereg": "tbd",
                    "task": {"brief_file": "b.md", "model": "m"},
                    "arms": [{"name": "control"}, {"name": "treated"}],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(tune.MatrixError):
            tune.read_matrix(path)

    def test_the_refusal_is_an_exit_code_and_not_a_traceback(self) -> None:
        path = self.root / "bare.json"
        path.write_text(json.dumps({"arms": []}), encoding="utf-8")
        self.assertEqual(tune.main([str(path)]), 2)

    def test_a_matrix_whose_first_arm_is_not_the_control_is_refused(self) -> None:
        path = self.root / "backwards.json"
        path.write_text(
            json.dumps(
                {
                    "prereg": PREREG,
                    "task": {"brief_file": "b.md", "model": "m"},
                    "arms": [{"name": "treated"}, {"name": "control"}],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(tune.MatrixError) as caught:
            tune.read_matrix(path)
        self.assertIn("control", str(caught.exception))

    def test_one_arm_is_a_run_and_not_a_comparison(self) -> None:
        path = self.root / "one.json"
        path.write_text(
            json.dumps(
                {
                    "prereg": PREREG,
                    "task": {"brief_file": "b.md", "model": "m"},
                    "arms": [{"name": "control"}],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(tune.MatrixError):
            tune.read_matrix(path)

    def test_a_root_holding_two_threads_is_refused_rather_than_guessed_at(self) -> None:
        control, treated = self.two_arms()
        was = db.DB_PATH
        db.DB_PATH = treated / "arm.db"
        try:
            events.create_thread("a second conversation in the same root")
        finally:
            db.DB_PATH = was
        self.assertEqual(
            self.dry_run(control, treated), 2, "ambiguous is refused, not resolved"
        )

    # -- the fence around a real installation -------------------------------
    #
    # These are the tests that matter most in this file, because the failure
    # they prevent is not a wrong number in a report - it is an arm driving the
    # owner's own conversations with a tuning brief, or overwriting his
    # database. Measured 2026-09-18: `tests/support.py`'s sqlite3 guard does
    # NOT cover this, because it protects `<repo>/ml_harness.db` resolved from
    # the checkout the code runs in, so from an agent's git worktree it guards
    # the worktree's copy and leaves the real one open. The script carries its
    # own fence for that reason and these assert it.

    def test_a_matrix_may_not_set_the_variables_that_are_the_fence(self) -> None:
        for reserved in tune.RESERVED:
            path = self.root / f"escape-{reserved}.json"
            path.write_text(
                json.dumps(
                    {
                        "prereg": PREREG,
                        "task": {"brief_file": "b.md", "model": "m"},
                        "arms": [
                            {"name": "control", "env": {}},
                            {"name": "treated", "env": {reserved: "anything"}},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(tune.MatrixError, msg=reserved) as caught:
                tune.read_matrix(path)
            self.assertIn(reserved, str(caught.exception))

    def test_the_owners_port_is_refused(self) -> None:
        with self.assertRaises(RuntimeError) as caught:
            tune.refuse_a_real_installation(self.root, self.root / "arm.db", 8078)
        self.assertIn("owner's engine", str(caught.exception))

    def test_a_real_installations_database_is_refused_by_its_name(self) -> None:
        with self.assertRaises(RuntimeError) as caught:
            tune.refuse_a_real_installation(
                self.root, self.root / tune.THE_REAL_DATABASE, 9999
            )
        self.assertIn(tune.THE_REAL_DATABASE, str(caught.exception))

    def test_a_root_that_holds_a_real_database_is_not_a_scratch_root(self) -> None:
        (self.root / tune.THE_REAL_DATABASE).write_bytes(b"")
        with self.assertRaises(RuntimeError) as caught:
            tune.refuse_a_real_installation(self.root, self.root / "arm.db", 9999)
        self.assertIn("real installation", str(caught.exception))

    def test_an_arm_will_not_be_scored_on_a_database_it_did_not_write(self) -> None:
        (self.root / "arm.db").write_bytes(b"")
        with self.assertRaises(RuntimeError) as caught:
            tune.refuse_a_real_installation(self.root, self.root / "arm.db", 9999)
        self.assertIn("already exists", str(caught.exception))

    def test_a_scratch_root_this_script_made_is_allowed(self) -> None:
        """The positive control. A fence that refuses everything proves nothing."""
        tune.refuse_a_real_installation(self.root, self.root / "arm.db", 9999)

    def test_free_port_never_returns_the_owners(self) -> None:
        self.assertNotIn(tune.HIS_PORT, {tune.free_port() for _ in range(40)})

    def test_a_knob_cannot_overwrite_the_fence_even_without_a_matrix(self) -> None:
        """The second lock, on an `Arm` built directly rather than from a matrix."""
        arm = tune.Arm(
            "sneaky",
            self.root / "sneaky",
            {"ML_HARNESS_DB": "C:/somebody/else/ml_harness.db", "MLH_ALL_LAWS": "1"},
        )
        try:
            environment = arm.environment()
        finally:
            arm.stop()
        self.assertEqual(
            environment["ML_HARNESS_DB"],
            str(arm.database),
            "the arm's own database, not the one the knob named",
        )
        self.assertEqual(environment["MLH_ALL_LAWS"], "1", "and the real knob survived")

    def test_the_shipped_example_matrix_is_one_this_script_accepts(self) -> None:
        """The example in docs/ is checked by loading it, not by reading it."""
        matrix = tune.read_matrix(REPO / "docs" / "tuning" / "matrix-tools-vs-schemas.json")
        self.assertEqual([arm["name"] for arm in matrix["arms"]], ["control", "on_demand"])
        self.assertIn("WHAT WOULD REFUTE IT", matrix["prereg"])
        brief = REPO / matrix["task"]["brief_file"]
        self.assertTrue(brief.exists(), f"the example names a brief that is not there: {brief}")


if __name__ == "__main__":
    unittest.main()
