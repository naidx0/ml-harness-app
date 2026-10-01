"""Under Full, a refusal over an argument does not park the step.

Max's thread 75, 2026-09-17: six steps parked, and every park reason was an
argument the model could have fixed on the next call - a wrong path,
state_facts with no facts, a value not in the fact's own list, a number sent
as a string, a folder that already existed, nothing to deduplicate. The run
read each `ok: false` as proof the aimed step could not be done, parked it,
and moved on; by the end six of six were parked and the person read "not one
of the 6 steps could be done" about a plan nobody had tried.

A wall is a tool saying the world refuses - no model, no GPU, generated rows,
a person's yes. And only the aimed step's OWN tool can say it: state_facts
refusing says nothing about carving the eval set, which the build prompt
already promised.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import events, longrun  # noqa: E402

NL = chr(10)
PLAN = NL.join([
    "# Train the router",
    "",
    "## Phase 1 - Data",
    "- [ ] Measure the baseline with measure_baseline on eval.jsonl",
    "- [ ] Carve the eval set with carve_eval_set",
])


def _turns(script: list[Callable[[int], None]]) -> Callable[[int], Any]:
    taken = {"n": 0}

    def take(thread_id: int, scaffold: str | None = None):
        index = min(taken["n"], len(script) - 1)
        taken["n"] += 1
        script[index](thread_id)
        yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

    return take


def _refusal(name: str, error: str, detail: str = "") -> Callable[[int], None]:
    def act(thread_id: int) -> None:
        events.append(
            "tool.result",
            {"name": name, "ok": False,
             "result": {"ok": False, "error": error, "detail": detail or error}},
            thread_id=thread_id,
        )
        events.append("chat.delta", {"text": "The step is still open."}, thread_id=thread_id)

    return act


class UnderFullTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_permission(self.thread, "full")
        events.set_thread_plan(self.thread, PLAN)

    def test_a_rejected_fact_on_another_tool_parks_nothing(self):
        slip = _refusal("state_facts", "rejected_fact",
                        "fact 'privacy' = 'full' is not one of ['public_ok', 'regulated']")
        longrun.start(self.thread, background=False, cap=6, turn=_turns([slip] * 6))
        run = longrun.status(self.thread) or {}
        self.assertEqual(run["parked"], [], run)
        self.assertNotIn("- [!]", events.get_thread(self.thread)["plan"])

    def test_a_taken_folder_or_a_missing_file_parks_nothing(self):
        script = [
            _refusal("generate_rows", "destination_exists", "that folder already exists"),
            _refusal("read_context_file", "not_found", "no such file"),
            _refusal("measure_baseline", "missing_arguments", "needs eval_path"),
        ] * 2
        longrun.start(self.thread, background=False, cap=6, turn=_turns(script))
        self.assertEqual((longrun.status(self.thread) or {})["parked"], [])

    def test_a_wall_from_the_steps_own_tool_still_parks_it(self):
        wall = _refusal("measure_baseline", "no_provider", "No model is connected")
        longrun.start(self.thread, background=False, cap=6, turn=_turns([wall] * 4))
        run = longrun.status(self.thread) or {}
        self.assertEqual(len(run["parked"]), 1, run)
        self.assertIn("measure_baseline refused: No model is connected", run["parked"][0]["why"])

    def test_a_wall_from_a_tool_the_step_did_not_name_parks_nothing(self):
        elsewhere = _refusal("start_training", "no_gpu", "this machine has no card")
        longrun.start(self.thread, background=False, cap=6, turn=_turns([elsewhere] * 6))
        self.assertEqual((longrun.status(self.thread) or {})["parked"], [])

    def test_the_park_reason_is_never_an_argument_slip(self):
        """`_last_words` preferred any refusal to the reply; a slip on an
        unrelated tool became the written reason for a parked step."""
        rows = [
            {"kind": "tool.result", "payload": {"name": "state_facts", "ok": False,
             "result": {"ok": False, "error": "nothing_supplied", "detail": "No facts were given"}}},
            {"kind": "chat.delta", "payload": {"text": "The eval file is not on disk."}},
        ]
        self.assertEqual(longrun._last_words(rows), "The eval file is not on disk.")


class TheWallSetIsHonestTest(unittest.TestCase):
    def test_a_shell_exit_code_is_not_a_wall(self):
        payload = {"name": "run_project_command", "ok": False,
                   "result": {"ok": False, "exit_code": 1, "stderr": "no such cmdlet"}}
        self.assertFalse(longrun._is_a_wall(payload, frozenset()))

    def test_a_real_refusal_from_a_named_tool_is(self):
        payload = {"name": "measure_baseline", "ok": False,
                   "result": {"ok": False, "error": "generated_rows"}}
        self.assertTrue(longrun._is_a_wall(payload, frozenset({"measure_baseline"})))
        self.assertFalse(longrun._is_a_wall(payload, frozenset({"carve_eval_set"})))


if __name__ == "__main__":
    unittest.main()
