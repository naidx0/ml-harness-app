"""Every refusal Max's run of 2026-09-19/20 walked into now names a next move.

Thread 83 and its six children ran for a night and never measured a baseline.
263 tool calls. What they were spent on, counted off `ml_harness.db`:

  64  run_diagnosis          the same verdict, over and over
  62  read_observation       opening handles for verdicts already in hand
  19  state_facts            `task_family`, nineteen times, refused every time
  19  measure_eval_set
  11  measure_baseline / run_eval, every one of them at a path that does not
      exist, with `input_field="q", expected_field="a"`
   6  assess_the_data        `unreadable_format`, six identical dead ends

Four faults, each one a wall the harness put up and then gave no door through:

1. THE PLAYBOOK INVENTED COLUMN NAMES. `app/knowledge/playbook.json` carried
   `args_hint: "eval_path, input_field=q, expected_field=a"`. There is no `q`
   and no `a` in his eval file - the hint was a worked example, and the model
   read it as a fact about the file in front of it, eleven times.
   See [[a-generic-example-teaches-the-wrong-argument]].

2. A REFUSAL ABOUT AN EVAL FILE DID NOT NAME THE EVAL FILE THE THREAD HAD
   ALREADY COUNTED. `measure_eval_set` had counted 40 rows at
   `.../data/splits/eval.jsonl` and recorded it. `measure_baseline` answered
   "no rows could be read" and stopped there.

3. A FOLDER REFUSAL DID NOT NAME THE FILES IN THE FOLDER. `assess_the_data` on
   a folder of 74 mixed files said "no reader ships for folder" eight times.
   Every one of those files has a reader; the folder is unreadable only as ONE
   dataset.

4. `task_family` HAD NO ROUTE AT ALL. No instrument measures it, `state_facts`
   records it and tells you it "cannot, at this origin", and `evidence.resolves`
   called it "a gap in the product rather than something you can answer" - while
   `full_defaults` had been deriving it from the eval file the whole time.

And the loop around all of it: `run_diagnosis` and `what_is_missing` were
PACKED. A model asks what to do next, is handed a receipt, and spends the next
round opening it. They are never packed now.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402,F401

#: One backslash, built rather than typed - see the vault note on tool writes.
CHR_BACKSLASH = chr(92)
from app import dataquality, observations  # noqa: E402
from app.tools import evidence  # noqa: E402


class TheHintDoesNotInventAColumn(unittest.TestCase):
    """A worked example beside a specific object is read as being about it."""

    def test_no_route_hint_names_a_column_nobody_read(self):
        book = json.loads((REPO / "app" / "knowledge" / "playbook.json").read_text("utf-8"))
        hints: list[str] = []

        def walk(node):
            if isinstance(node, dict):
                if "args_hint" in node:
                    hints.append(str(node["args_hint"]))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(book)
        self.assertTrue(hints, "the playbook stopped carrying args_hint")
        # The literal that cost the run, and the two beside it in the same
        # shape. A hint may say WHERE to read a column name; it may not say
        # what the column is called, because it has not read the file.
        for hint in hints:
            self.assertNotIn("input_field=q", hint)
            self.assertNotIn("expected_field=a", hint)
            self.assertNotIn("answer_column = a;", hint)
            self.assertNotIn("answer_column = text;", hint)


class AFolderRefusalNamesItsFiles(unittest.TestCase):
    """`assess_the_data` on a mixed folder says which files it could read."""

    def _folder(self) -> Path:
        box = tempfile.TemporaryDirectory()
        self.addCleanup(box.cleanup)
        root = Path(box.name)
        (root / "data" / "splits").mkdir(parents=True)
        (root / "corpus").mkdir()
        # The shape of his: prose that sorts first alphabetically, and the one
        # file anybody wants buried three folders down.
        for name in ("00-summary.md", "01-attention.md", "02-scaling.md"):
            (root / "corpus" / name).write_text("# a heading\n", "utf-8")
        (root / "README.md").write_text("# read me\n", "utf-8")
        (root / "data" / "splits" / "eval.jsonl").write_text(
            '{"input": "q1", "expected": "a1"}\n', "utf-8"
        )
        return root

    def test_the_refusal_lists_the_readable_files_and_counts_them(self):
        root = self._folder()
        report = dataquality.profile(str(root))
        self.assertFalse(report["format"]["readable"], "a mixed folder is still not one dataset")
        self.assertEqual(report["data_files_inside_count"], 5)
        self.assertIn("data/splits/eval.jsonl", report["data_files_inside"])
        self.assertTrue(
            any("Point this tool at one of them" in note for note in report["notes"]),
            report["notes"],
        )

    def test_row_files_come_before_prose(self):
        """Sorted by name, the only table in his folder fell off the list."""
        root = self._folder()
        shown = dataquality.profile(str(root))["data_files_inside"]
        self.assertEqual(shown[0], "data/splits/eval.jsonl")


class ARefusalPointsAtAFileThatExists(unittest.TestCase):
    """The eleven calls at `eval.jsonl` were eleven guesses at a missing path.

    And the search is a FILESYSTEM reading, not a claims reading: a tool that
    can stamp MEASURED may not read the transcript or the ledger
    (`evidence.refuse_a_minting_reader`), which is what the first cut of this
    did - it read `events.since` from inside `measure_baseline` and threw
    `MeasurementError` on every empty eval file in the suite. Names on a disk
    are nobody's claim.
    """

    def test_a_path_that_exists_gets_no_did_you_mean(self):
        """The hint is for a MISSING path. A real file that is empty is a
        different answer and must not be buried under a list of other files."""
        from app.tools import evals

        box = tempfile.TemporaryDirectory()
        self.addCleanup(box.cleanup)
        here = Path(box.name) / "eval.jsonl"
        here.write_text("", "utf-8")
        self.assertEqual(evals._and_what_is_on_disk(None, str(here)), {})

    def test_it_matches_on_the_name_and_reads_nothing(self):
        from app.tools import evals

        box = tempfile.TemporaryDirectory()
        self.addCleanup(box.cleanup)
        root = Path(box.name)
        (root / "data" / "splits").mkdir(parents=True)
        (root / "data" / "splits" / "eval.jsonl").write_text("{}", "utf-8")
        (root / "data" / "splits" / "train.jsonl").write_text("{}", "utf-8")
        (root / "notes.md").write_text("# not a split", "utf-8")
        names = sorted(
            str(one.relative_to(root)).replace(CHR_BACKSLASH, "/")
            for one in root.rglob("*")
            if one.is_file()
            and one.suffix.lower() in evals._ROW_SUFFIXES
            and "eval" in one.name.lower()
        )
        self.assertEqual(names, ["data/splits/eval.jsonl"])

    def test_the_lookup_never_reads_the_transcript(self):
        """The law it broke once, pinned so it cannot break it again."""
        source = (REPO / "app" / "tools" / "evals.py").read_text("utf-8")
        body = source[source.index("def eval_files_under_the_workspace") :]
        body = body[: body.index(chr(10) + "def ")]
        # The docstring EXPLAINS the law, so it names the closed doors. Only
        # the code is under test.
        quotes = chr(34) * 3
        code = body.split(quotes)[2] if body.count(quotes) >= 2 else body
        for closed in ("events.since", "_events.since", "assemble_facts", "messages_for"):
            self.assertNotIn(closed, code, closed)
        # And it really does look at the disk, or the test proves nothing.
        self.assertIn("rglob", code)


class AHandleIsNotAnInteger(unittest.TestCase):
    """Thread 87 walked six consecutive event ids in one turn, 11 refusals.

    The real list was in a `handles` key beside the message every time. What a
    model acts on is the sentence, so the sentence carries it now - and says
    that the next number up is not the next handle.
    """

    def test_the_wording_carries_the_warning_and_the_list(self):
        source = (REPO / "app" / "tools" / "observe.py").read_text("utf-8")
        self.assertIn("are NOT consecutive", source)
        self.assertIn("This conversation holds ", source)


class AFactWithNoInstrumentStillHasARoute(unittest.TestCase):
    """`task_family`: derived from the eval file, and the answer says so."""

    def test_resolves_names_the_tool_that_starts_the_derivation(self):
        answer = evidence.resolves("task_family")
        self.assertEqual(answer["derived_by"], "measure_eval_set")
        self.assertEqual(answer["derived_from"], "eval_size_n")

    def test_the_route_is_not_smuggled_into_the_settler_field(self):
        """`tool` means "this instrument stamps this fact", and it still does.

        The first cut of this put `measure_eval_set` in `tool`. `app/asking.py`
        holds every card's tool to `measures=(fact,)` and refused to derive a
        question at all - 70 reds in one gate run, all of them the invariant
        working. A derivation is a different claim and gets its own field.
        """
        answer = evidence.resolves("task_family")
        self.assertIsNone(answer["tool"])
        from app.tools.registry import REGISTRY

        settler = evidence.resolves("eval_size_n")["tool"]
        declared = next(c for c in REGISTRY if c.name == settler)
        self.assertIn("eval_size_n", declared.measures)

    def test_it_no_longer_calls_the_route_a_gap_in_the_product(self):
        note = evidence.resolves("task_family")["note"]
        self.assertNotIn("gap in the product", note)
        self.assertIn("run_diagnosis again", note)

    def test_a_fact_with_neither_instrument_nor_rule_is_still_told_plainly(self):
        """The honest branch survives - this is not a blanket suppression."""
        from app import full_defaults

        unrouted = [
            name
            for name in evidence.spec(None).facts
            if name not in full_defaults.PREREQUISITES
            and (evidence.spec(None).facts[name] or {}).get("source") == "inspect"
            and not evidence.resolves(name).get("tool")
        ]
        self.assertTrue(unrouted, "no unrouted inspect fact left to prove the branch")
        self.assertIn("gap in the product", evidence.resolves(unrouted[0])["note"])


class TheAnswerToWhatNextIsNeverAReceipt(unittest.TestCase):
    """A tool whose whole output IS the next move rides whole, every time."""

    def test_the_two_state_reports_are_never_packed(self):
        self.assertIn("run_diagnosis", observations.NEVER_PACKED)
        self.assertIn("what_is_missing", observations.NEVER_PACKED)

    def test_the_reader_is_still_never_packed(self):
        self.assertIn("read_observation", observations.NEVER_PACKED)


if __name__ == "__main__":
    unittest.main()


class AParkIsNotAVerdict(unittest.TestCase):
    """`unpark_step` was registered and named nowhere in the product.

    Max's run of 2026-09-19/20 ended "9 turns, 7 steps ticked, 7 parked" with
    the advice "Start the run again, or switch model" - and starting it again
    parks the same seven for the same reasons, because nothing reopens them
    and nothing told the model they could be reopened. His words, 2026-09-20:
    *"we're not just parking for no reason. Get, we're giving the models ways
    to unpark and not stop."*
    """

    def test_the_tool_exists_and_is_registered(self):
        from app.tools.registry import REGISTRY

        self.assertTrue(any(c.name == "unpark_step" for c in REGISTRY))

    def test_a_run_that_inherits_parks_is_told_on_its_first_turn(self):
        from app import longrun

        said = longrun.PARKED_NUDGE.format(count=7, lines="\n- a step")
        self.assertIn("unpark_step", said)
        self.assertIn("7 parked step(s)", said)
        # And it must not send the model back into a wall that still stands.
        self.assertIn("leave it parked", said)

    def test_the_stop_reason_names_the_door(self):
        source = (REPO / "app" / "longrun.py").read_text("utf-8")
        body = source[source.index("def _finish(") :]
        body = body[: body.index(chr(10) + "def ")]
        self.assertIn("unpark_step", body)

    def test_no_stop_reason_claims_nothing_was_parked(self):
        """It said "Nothing was parked" in the same strip as "7 parked"."""
        source = (REPO / "app" / "longrun.py").read_text("utf-8")
        self.assertNotIn("Nothing was parked", source)


class AMissingPathGetsTheFilesThatExist(unittest.TestCase):
    """A schema says what SHAPE to send; it never says what value is there.

    Max's run of 2026-09-20, on the engine still up at the time: 15 of 28 tool
    calls were `measure_eval_set`, six of them with no arguments at all. The
    reply carried the full schema every time, and the next call was another
    guess, because a required `path` with nothing to point it at is a guess by
    construction.
    """

    def _project(self):
        import tempfile

        box = tempfile.TemporaryDirectory()
        self.addCleanup(box.cleanup)
        root = Path(box.name)
        (root / "data" / "splits").mkdir(parents=True)
        (root / ".hub-cache").mkdir()
        (root / "node_modules" / "pkg").mkdir(parents=True)
        (root / "data" / "splits" / "eval.jsonl").write_text("{}", "utf-8")
        (root / "notes.md").write_text("#", "utf-8")
        (root / "engine.json").write_text("{}", "utf-8")
        (root / ".hub-cache" / "abc.json").write_text("{}", "utf-8")
        (root / "node_modules" / "pkg" / "package.json").write_text("{}", "utf-8")
        return root

    def _listing(self, root: Path) -> list[str]:
        """The ranker and the filter, over a real tree."""
        from app.tools import registry

        found = [
            "/".join(one.relative_to(root).parts)
            for one in sorted(root.rglob("*"))
            if one.is_file()
            and one.suffix.lower() in registry._PATHS_WORTH_NAMING
            and not any(p.startswith(".") for p in one.relative_to(root).parts[:-1])
            and not any(
                p in registry._NOT_SOMEBODYS_DATA
                for p in one.relative_to(root).parts[:-1]
            )
        ]
        return found

    def test_bookkeeping_is_not_offered_as_data(self):
        root = self._project()
        listed = self._listing(root)
        self.assertIn("data/splits/eval.jsonl", listed)
        self.assertNotIn(".hub-cache/abc.json", listed)
        self.assertNotIn("node_modules/pkg/package.json", listed)

    def test_only_an_argument_that_names_a_path_gets_a_listing(self):
        from app.tools import registry

        self.assertEqual(registry._files_for_a_missing_path(["sample"], 1), {})
        self.assertEqual(registry._files_for_a_missing_path([], 1), {})

    def test_it_says_nothing_when_the_thread_has_no_project(self):
        from app.tools import registry

        self.assertEqual(registry._files_for_a_missing_path(["path"], None), {})


class AVerdictSaysSomethingAndNamesAToolThatCanRun(unittest.TestCase):
    """Max's run of 2026-09-21, after it had passed two gates.

    The card read, in this order: `ACTION__CLASSIFY_FAILURES`, then "The engine
    returned no note for this outcome. say was empty on the wire, and nothing
    here writes one", then a move offering `rebucket_failures` - "re-tally a
    histogram you corrected" - directly above the line "Ask again when
    failure_histogram changes from {}".

    So the product apologised for itself, and then offered the one tool that
    cannot produce a histogram from nothing, to produce a histogram from
    nothing.
    """

    def _his_ledger(self):
        from app.diagnosis import MEASURED, STATED, Fact, default_spec, diagnose

        spec = default_spec()
        return spec, diagnose(
            {
                "eval_size_n": Fact(40, MEASURED),
                "baseline_measured": Fact(True, MEASURED),
                "baseline_score": Fact(0.0, MEASURED),
                "trivial_baseline_score": Fact(0.05, MEASURED),
                "target_score": Fact(0.246, STATED),
                "task_family": Fact("classification", STATED),
                "modality": Fact("text", STATED),
            },
            spec,
        )

    def test_the_outcome_he_reached_carries_a_note(self):
        _, result = self._his_ledger()
        self.assertEqual(result.outcome, "ACTION__CLASSIFY_FAILURES")
        self.assertTrue((result.say or "").strip(), "the card would apologise again")

    def test_the_move_names_a_tool_that_can_produce_the_fact(self):
        from app.tools import next_moves

        spec, result = self._his_ledger()
        rows = next_moves.alternatives(result, spec=spec).get("alternatives") or []
        self.assertTrue(rows)
        tools = [row.get("tool") for row in rows]
        self.assertIn("run_eval", tools)
        self.assertNotIn("rebucket_failures", tools)

    def test_the_ledger_ordering_is_what_decides_it(self):
        """Not a preference of this test - `contract.capabilities.builds`."""
        from app.tools import next_moves

        spec, _ = self._his_ledger()
        self.assertEqual(
            next_moves._tool_the_ledger_starts_with("ACTION__CLASSIFY_FAILURES", spec),
            "run_eval",
        )

    def test_every_reachable_outcome_has_a_note(self):
        """The apology is a missing `say`, and it should never be possible."""
        from app.diagnosis import default_spec

        spec = default_spec()
        silent = [
            name
            for name, node in spec.node_index.items()
            if node.get("outcome")
            # REROUTE IS NOT A VERDICT. Those three nodes hand the walk to
            # another stage and the person never sees them; a note on one would
            # be words written for nobody. Every node that ends a walk says
            # something.
            and str(node.get("outcome")) != "REROUTE"
            and not str(node.get("say") or "").strip()
            and not str(node.get("action") or "").strip()
        ]
        self.assertEqual(silent, [], "these nodes would make the card apologise")


class AFactNoGateReadsIsNotABlocker(unittest.TestCase):
    """`data_quality` cost him turns while blocking nothing.

    The model read "a gap in the product", called it a blocked gate, announced
    "no training or scoring can be run", and kept calling `state_facts` at it.
    No gate in the ledger reads that fact.
    """

    def test_it_says_no_gate_reads_it(self):
        answer = evidence.resolves("data_quality")
        self.assertTrue(answer["held_shut_by_no_gate"])
        self.assertIn("cannot hold anything shut", answer["note"])
        self.assertIn("Do not spend turns on it", answer["note"])

    def test_a_fact_a_gate_does_read_is_not_told_to_be_ignored(self):
        from app.diagnosis import default_spec
        from app.tools.evidence import _a_gate_reads

        self.assertTrue(_a_gate_reads("eval_size_n", default_spec()))
        self.assertFalse(_a_gate_reads("data_quality", default_spec()))


class TheBriefCarriesTheLedgerItCounts(unittest.TestCase):
    """"Why does our model forget some of these things?" - it never knew them.

    Max, 2026-09-21, watching it re-read his hardware and his plan on turn
    after turn. The brief said *"this thread's ledger, 12 facts, and the walk
    over them"*, named none of the twelve, and spent the rest of its budget on
    ninety-three tool descriptions. `vram_gb = 8.0 MEASURED` was on the sheet
    the whole time and the number 8 appeared nowhere in the prompt.

    `_already_read_note` was the only other route, and it carries KEY NAMES
    rather than values - `inspect_hardware -> answered (ram_gb, vram_gb, ...)`.
    So a model that needs a number it has already measured has exactly one way
    to get it: run the instrument again.
    """

    def _brief(self) -> str:
        from app import conductor

        return conductor.standing_brief(
            {
                "verdict": "BLOCKED",
                "outcome": "ACTION__CLASSIFY_FAILURES",
                "gate_ledger": {},
                "facts_used": {
                    "vram_gb": {"value": 8.0, "origin": "MEASURED"},
                    "eval_size_n": {"value": 40, "origin": "MEASURED"},
                    "task_family": {"value": "classification", "origin": "STATED"},
                    "target_score": {"value": 0.246, "origin": "DEFAULTED"},
                },
                "fact_origins": {},
            }
        )

    def test_the_values_are_in_the_prompt(self):
        brief = self._brief()
        self.assertIn("vram_gb = 8.0", brief)
        self.assertIn("eval_size_n = 40", brief)

    def test_every_fact_carries_its_origin(self):
        """A number without its origin is what this product refuses elsewhere."""
        brief = self._brief()
        self.assertIn("vram_gb = 8.0 [MEASURED]", brief)
        self.assertIn("task_family = classification [STATED]", brief)
        self.assertIn("target_score = 0.246 [DEFAULTED]", brief)

    def test_readings_come_before_assertions(self):
        brief = self._brief()
        self.assertLess(
            brief.index("vram_gb"), brief.index("task_family"),
            "a model reading from the top should meet the measurements first",
        )

    def test_the_count_and_the_list_agree(self):
        brief = self._brief()
        self.assertIn("4 facts", brief)
        named = [line for line in brief.splitlines() if line.startswith("  ") and " = " in line]
        self.assertEqual(len(named), 4)


class TheAlreadyReadNoteDoesNotDescribeItself(unittest.TestCase):
    """8 of 14 lines were `read_observation`, and the real readings fell off."""

    def test_the_reader_is_excluded_from_the_note(self):
        source = (REPO / "app" / "conductor.py").read_text("utf-8")
        body = source[source.index("def _already_read_note(") :]
        body = body[: body.index(chr(10) + "def ")]
        self.assertIn("_observations.READER", body)
        self.assertIn("continue", body)
