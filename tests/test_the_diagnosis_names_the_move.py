"""A blocked walk says what to GO AND DO, and asks only what it actually read.

Max, 2026-09-19, after a forty-minute Full run that ended with 0 of 5 gates
passed and a dozen identical verdicts:

    "This diagnosis block never works. An eval set exists - if it sees an eval
    set doesn't exist, GO MAKE AN EVAL SET. A baseline hasn't been measured -
    GO MAKE A BASELINE. Stop just saying not-work. The model has a sandbox, it
    has abilities, it's working in a harness, it has whatever it needs."

Four defects were under that, and each has a class here.

1. THE QUESTION WAS ABOUT A BRANCH THE WALK NEVER TOOK. `S0_RULES_SUFFICE`
   reads `task_family in {extraction, classification} and ... classes_n <= 5`.
   `and` short-circuits, so on a generation thread `classes_n` is never
   looked at - but `app/asking.py` built its question from a PARSE of the
   condition, which names every operand. The brief said "Blocked on
   `classes_n`. Run assess_the_data", the model obeyed, the tool refused, and
   the fact that actually stopped the walk was two rows below.

2. THE CIRCLE. Full sets `target_score` by rule, and the rule needs a measured
   baseline. The node that sends anybody to measure a baseline is a stage
   below a hard terminal the walk never passes. So: ask for the bar, cannot
   default the bar, say "run state_facts", repeat.

3. A SETTLED DEFAULT WAS ASKED FOR AGAIN. `full_defaults` writes at rank zero
   so a person's word beats it; the asker read every DEFAULTED fact as
   unanswered, including the one it had just written.

4. THE NUDGE THAT NEVER FIRED. `_full_grind_tool` matched a hand-written list
   of five tool names out of ninety-three.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import conductor, dataquality, events, full_defaults  # noqa: E402
from app.tools import REGISTRY, evidence  # noqa: E402


def _full_thread(title: str = "a full thread") -> int:
    thread_id = int(events.create_thread(title, mode="build")["id"])
    events.set_thread_permission(thread_id, "full")
    return thread_id


def _diagnose(thread_id: int) -> dict:
    return REGISTRY.call(
        "run_diagnosis", {}, approved=True, actor=evidence.MODEL, thread_id=thread_id
    )


class ItAsksOnlyWhatTheConditionReachedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)

    def test_a_generation_thread_is_never_asked_for_a_class_count(self):
        thread_id = _full_thread()
        REGISTRY.call(
            "state_facts",
            {"facts": {"task_family": "generation"}},
            approved=True,
            actor=evidence.MODEL,
            thread_id=thread_id,
        )
        answer = _diagnose(thread_id)
        self.assertTrue(answer["ok"])
        self.assertNotIn(
            "classes_n", answer["next"],
            "a generation thread was sent to count label classes",
        )
        self.assertNotEqual((answer.get("next_step") or {}).get("fact"), "classes_n")

    def test_the_ledger_still_names_it_and_the_walk_simply_did_not_reach_it(self):
        """THE POSITIVE CONTROL, and it is the thing that makes this a narrowing
        rather than a deletion. The condition still reads `classes_n` - nothing
        was edited out of the ledger - and a parse of it still says so. What
        changed is that the ASKER now uses what the evaluation reached instead
        of what the expression mentions, and on a generation thread the `and`
        answered False at the first operand."""
        from app import asking, diagnosis

        spec = diagnosis.default_spec()
        tree = spec.conditions["S0_RULES_SUFFICE"]
        mentioned = diagnosis._facts_read_by(spec, tree)
        self.assertIn("classes_n", mentioned, "the ledger no longer asks it at all")
        self.assertIn("task_family", mentioned)

        thread_id = _full_thread()
        REGISTRY.call(
            "state_facts",
            {"facts": {"task_family": "generation"}},
            approved=True,
            actor=evidence.MODEL,
            thread_id=thread_id,
        )
        sheet, _ = evidence.assemble_facts(thread_id, {}, evidence.MODEL, ledger=spec)
        walked = diagnosis.diagnose(sheet, spec)
        entry = next(e for e in walked.path if e.id == "S0_RULES_SUFFICE")
        reached = asking.facts_read_by(entry, walked)
        self.assertEqual(reached, frozenset({"task_family"}))
        self.assertTrue(
            reached < mentioned, "the reached set must be narrower than the parse"
        )


class ItNamesTheToolThatWouldUnblockItTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)

    def test_a_blank_full_thread_is_sent_to_count_not_to_decide(self):
        """The first blocker is `task_family`, which no tool MEASURES - but
        Full DERIVES it, by reading the eval file's own answers. "No tool
        measures it, decide it yourself" was true of the registry and wrong
        about the harness."""
        answer = _diagnose(_full_thread())
        step = answer.get("next_step") or {}
        self.assertEqual(step.get("kind"), "gap", "a gap is still named as a gap")
        self.assertEqual(step.get("fact"), "task_family")
        self.assertEqual(step.get("tool"), "measure_eval_set")
        self.assertIn("derives it rather than asking you", answer["next"])
        self.assertIn(
            "state_facts", answer["next"], "deciding it yourself is still offered"
        )

    def test_once_the_family_is_known_the_bar_routes_through_the_eval_set(self):
        thread_id = _full_thread()
        REGISTRY.call(
            "state_facts",
            {"facts": {"task_family": "generation"}},
            approved=True,
            actor=evidence.MODEL,
            thread_id=thread_id,
        )
        answer = _diagnose(thread_id)
        step = answer.get("next_step") or {}
        self.assertEqual(step.get("fact"), "target_score")
        self.assertEqual(step.get("tool"), "measure_eval_set")
        self.assertIn("carve_eval_set", answer["next"], "it names how to make one")
        self.assertIn(
            "Do not ask the person", answer["next"],
            "under Full the bar is settled from the measurement, not asked for",
        )

    def test_under_ask_the_same_thread_is_not_promised_a_rule(self):
        """The promise is a Full-mode promise. Under Ask no rule is waiting."""
        thread_id = int(events.create_thread("an ask thread", mode="build")["id"])
        REGISTRY.call(
            "state_facts",
            {"facts": {"task_family": "generation"}},
            approved=True,
            actor=evidence.MODEL,
            thread_id=thread_id,
        )
        answer = _diagnose(thread_id)
        self.assertNotIn("under Full it is settled", answer["next"])
        self.assertNotIn("derives it rather than asking you", answer["next"])

    def test_the_chain_is_eval_set_then_baseline(self):
        self.assertEqual(
            full_defaults.prerequisite_for("target_score", {})[0], "measure_eval_set"
        )
        measured_eval = {
            "fact_origins": {"eval_size_n": "MEASURED"},
            "facts_used": {"eval_size_n": {"value": 40, "origin": "MEASURED", "how": "x"}},
        }
        self.assertEqual(
            full_defaults.prerequisite_for("target_score", measured_eval)[0],
            "measure_baseline",
        )

    def test_a_fact_with_no_rule_has_no_prerequisite(self):
        self.assertIsNone(full_defaults.prerequisite_for("failure_histogram", {}))


class TheGrindNudgeCoversEveryToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)

    def test_any_registered_tool_the_brief_names_is_a_move(self):
        for name in ("assess_the_data", "measure_eval_set", "carve_eval_set", "write_plan"):
            with self.subTest(tool=name):
                self.assertEqual(
                    conductor._full_grind_tool({"next_step": {"tool": name}}), name
                )

    def test_a_name_no_tool_answers_to_is_not_a_move(self):
        self.assertIsNone(
            conductor._full_grind_tool({"next_step": {"tool": "invented_tool"}})
        )
        self.assertIsNone(conductor._full_grind_tool({"next_step": {}}))


class AFolderOfOneFormatIsReadableTest(unittest.TestCase):
    """`assess_the_data` on `ml-principles-dataset` answered "That is a folder
    (directory listing) and no reader for it ships today" - which was true of
    the classifier and false of the module: `iter_records` has had a per-file
    directory branch since `text_folder` was added, and `_directory_data_files`
    already walks every extension in `DATA_EXTENSIONS`."""

    def setUp(self) -> None:
        self.root = support.sandbox(self)

    def _splits(self, name: str = "splits") -> Path:
        folder = self.root / name
        folder.mkdir(parents=True, exist_ok=True)
        for split, rows in (("train", 6), ("eval", 4)):
            (folder / f"{split}.jsonl").write_text(
                "\n".join(
                    json.dumps({"input": f"q{i}", "expected": f"a{i}"})
                    for i in range(rows)
                )
                + "\n",
                encoding="utf-8",
            )
        return folder

    def test_a_folder_of_jsonl_reads_every_row_of_every_file(self):
        folder = self._splits()
        fmt = dataquality.detect_format(folder)
        self.assertEqual(fmt["name"], "jsonl_folder")
        self.assertTrue(fmt["readable"])
        self.assertIn("2 jsonl files", fmt["how"])

        rows = list(dataquality.iter_records(folder, fmt))
        self.assertEqual(len(rows), 10, "both files, all rows, one stream")
        self.assertEqual({row["file"] for row in rows}, {"train.jsonl", "eval.jsonl"})
        self.assertIn("expected", rows[0], "the columns survive the folder")

    def test_the_profile_counts_the_folder(self):
        folder = self._splits("counted")
        report = dataquality.profile(str(folder), max_rows=1000)
        self.assertEqual(report.get("rows"), 10)
        self.assertNotIn(
            "no reader for it ships today",
            " ".join(str(note) for note in (report.get("notes") or [])),
        )

    def test_a_folder_of_two_formats_still_refuses_and_says_which(self):
        folder = self._splits("mixed")
        (folder / "extra.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        fmt = dataquality.detect_format(folder)
        self.assertEqual(fmt["name"], "folder")
        self.assertFalse(fmt["readable"])
        self.assertIn("csv", fmt["how"])
        self.assertIn("jsonl", fmt["how"])

    def test_an_empty_folder_is_still_unreadable(self):
        folder = self.root / "empty"
        folder.mkdir()
        fmt = dataquality.detect_format(folder)
        self.assertEqual(fmt["name"], "folder")
        self.assertFalse(fmt["readable"])

    def test_a_format_nothing_can_read_is_a_wall_not_a_slip(self):
        """`unreadable_format` is usually an argument to fix. When the thing
        with no reader is a folder or a binary, "fix the argument and call
        again" is advice with nothing behind it - and it cost a run, because
        the loop counted four such turns as narration and killed itself."""
        from app import longrun

        folder_refusal = {
            "name": "assess_the_data",
            "ok": False,
            "result": {
                "ok": False,
                "error": "unreadable_format",
                "format": {"name": "folder", "how": "directory listing"},
            },
        }
        typo_refusal = {
            "name": "assess_the_data",
            "ok": False,
            "result": {
                "ok": False,
                "error": "unreadable_format",
                "format": {"name": "parquet", "how": "magic bytes"},
            },
        }
        self.assertTrue(longrun._is_a_wall(folder_refusal, frozenset()))
        self.assertFalse(longrun._is_a_wall(typo_refusal, frozenset()))


class TheEngineSendsTheMovesItNamedTest(unittest.TestCase):
    """The card said "The engine sends no alternatives with a verdict" on every
    blocked verdict for weeks, while the wire carried them."""

    def setUp(self) -> None:
        self.root = support.sandbox(self)

    def test_a_blocked_verdict_carries_alternatives_and_revisit_if(self):
        answer = _diagnose(_full_thread())
        self.assertTrue(answer["ok"])
        self.assertTrue(
            answer["alternatives"], "no move was offered under a blocked verdict"
        )
        first = answer["alternatives"][0]
        for key in ("move", "text", "tool", "run_as", "starts_now", "why"):
            self.assertIn(key, first)
        self.assertTrue(answer["revisit_if"])
        self.assertTrue(all(isinstance(one, str) for one in answer["revisit_if"]))


if __name__ == "__main__":
    unittest.main()
