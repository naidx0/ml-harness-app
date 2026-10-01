"""Slice 2b of docs/plan-mode-v2-plan.md: `MLH_PLAN_V2=1` makes a plan turn one request.

With the flag on, a plan-mode turn's first round is one constrained request (the A12
schema as `response_format`, no tools) and the plan lands on the thread. A refused
plan, or a connection that cannot constrain its output, is recorded and the turn runs
the tool loop as before. With the flag off nothing changes.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import conductor, events, plan_v2_turn  # noqa: E402
from app.providers import Delta  # noqa: E402
from app.providers import store as provider_store  # noqa: E402

PLAN = {
    "kind": "plan",
    "goal": "an adapter that answers ML-principles questions better than the base model",
    "done_when": "adapter beats baseline on eval.jsonl by 10 points",
    "known": [],
    "gates": {g: "blocked" for g in plan_v2_turn.GATES},
    "decided": [],
    "not_doing": "",
    "question": "",
    "todos": [
        {"do": "Look at the attached files", "tool": "list_context", "args": {}, "check": "files listed", "approval": ""},
        {"do": "Read the eval rows", "tool": "preview_dataset_rows", "args": {}, "check": "rows shown", "approval": ""},
        {"do": "Read the machine", "tool": "inspect_hardware", "args": {}, "check": "VRAM known", "approval": ""},
        {"do": "Check train and eval do not overlap", "tool": "check_split_leakage", "args": {}, "check": "0 pairs", "approval": ""},
    ],
}

HAS_A_PLAN = "## Phase 1 - Data\n- [ ] Read the rows\n"


class _Constrained:
    """An Ollama-shaped adapter: takes `response_format`, scripted replies."""

    id = "fake"
    locality = "local"

    def __init__(self, script: list[str]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def stream(self, messages, tools=None, *, secret=None, response_format=None):
        self.calls.append({"tools": tools, "response_format": response_format})
        yield Delta(kind="text", text=self.script.pop(0) if self.script else "Done.")


class _Plain:
    """An adapter with no `response_format` (the OpenAI-compatible shape)."""

    id = "fake"
    locality = "local"

    def __init__(self) -> None:
        self.calls = 0

    def stream(self, messages, tools=None, *, secret=None):
        self.calls += 1
        yield Delta(kind="text", text="Here is my thinking about the plan.")


def _connect() -> None:
    row = provider_store.create("Fake", "http://127.0.0.1:11434", "fake-model", "ollama")
    provider_store.record_capabilities(
        row["id"],
        type("Caps", (), {"tool_calling": True, "detail": "test", "ctx_len": None, "provenance": {}})(),
    )
    provider_store.set_active(row["id"])


class PlanV2InTheConductorTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        _connect()
        self._env = os.environ.get(plan_v2_turn.FLAG)
        os.environ[plan_v2_turn.FLAG] = "1"
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        if self._env is None:
            os.environ.pop(plan_v2_turn.FLAG, None)
        else:
            os.environ[plan_v2_turn.FLAG] = self._env

    def _run(
        self, fake: Any, mode: str = "plan", *, full: bool = False, plan: str = ""
    ) -> tuple[int, list[dict[str, Any]]]:
        thread = int(events.create_thread("t", mode=mode)["id"])
        if full:
            events.set_thread_permission(thread, "full")
        if plan:
            events.set_thread_plan(thread, plan)
        events.add_message(thread, "user", "train an adapter on my ML principles data")
        original = conductor.build
        conductor.build = lambda *a, **k: fake
        try:
            for _ in conductor.run_turn(thread):
                pass
        finally:
            conductor.build = original
        return thread, events.since(f"thread:{thread}", limit=5000)

    @staticmethod
    def _notices(rows: list[dict[str, Any]]) -> list[str]:
        return [r["payload"].get("reason") for r in rows if r["kind"] == "conductor.notice"]

    def test_the_flag_makes_the_plan_turn_one_constrained_request(self):
        fake = _Constrained([json.dumps(PLAN)])
        thread, rows = self._run(fake)
        self.assertEqual(len(fake.calls), 1, "one request, no tool rounds")
        call = fake.calls[0]
        self.assertIsNone(call["tools"])
        enum = call["response_format"]["properties"]["todos"]["items"]["properties"]["tool"]["enum"]
        self.assertIn("start_training", enum, "the plan may name build tools, not only plan-mode lookups")
        self.assertIn("## Phase 1 - Look at the attached files", events.get_thread(thread)["plan"])
        end = [r["payload"] for r in rows if r["kind"] == events.END_KIND][-1]
        self.assertEqual((end["ending"], end["rounds"]), ("answered", 1))
        self.assertTrue([r for r in rows if r["kind"] == "thread.plan_written"])
        self.assertTrue([r for r in rows if r["kind"] == "thread.plan_ready"])
        said = [m["content"] for m in events.messages_for(thread) if m["role"] == "assistant"]
        self.assertTrue(said and "4 steps" in said[-1], said)

    def test_a_refused_plan_falls_back_to_the_tool_loop(self):
        pasted = dict(PLAN, todos=[dict(t, do="verb-first step") for t in PLAN["todos"]])
        fake = _Constrained([json.dumps(pasted), json.dumps(pasted), "I could not plan that."])
        thread, rows = self._run(fake)
        self.assertIn("plan_v2_refused", self._notices(rows))
        self.assertEqual(len(fake.calls), 3, "the plan request, its one retry, then the loop")
        self.assertIsNotNone(fake.calls[1]["response_format"])
        self.assertIsNone(fake.calls[2]["response_format"], "the loop's request is not constrained")
        self.assertFalse(events.get_thread(thread).get("plan"))

    def test_a_connection_that_cannot_constrain_runs_the_loop(self):
        fake = _Plain()
        _, rows = self._run(fake)
        self.assertIn("plan_v2_unsupported", self._notices(rows))
        self.assertEqual(fake.calls, 1)

    def test_flag_off_changes_nothing(self):
        os.environ.pop(plan_v2_turn.FLAG, None)
        fake = _Constrained(["A plain answer."])
        _, rows = self._run(fake)
        self.assertIsNone(fake.calls[0]["response_format"])
        self.assertFalse([n for n in self._notices(rows) if str(n).startswith("plan_v2")])

    def test_build_mode_is_untouched(self):
        fake = _Constrained(["Built nothing."])
        _, rows = self._run(fake, mode="build")
        self.assertIsNone(fake.calls[0]["response_format"])
        self.assertFalse([n for n in self._notices(rows) if str(n).startswith("plan_v2")])

    def test_a_full_threads_first_turn_is_planned_once(self):
        """Slice 2c: Full forces build, and the journey runs in Full."""
        fake = _Constrained([json.dumps(PLAN)])
        thread, rows = self._run(fake, mode="build", full=True)
        self.assertEqual(len(fake.calls), 1)
        self.assertIsNotNone(fake.calls[0]["response_format"])
        self.assertIn("## Phase 1 - Look at the attached files", events.get_thread(thread)["plan"])

    def test_a_full_thread_with_a_plan_is_not_replanned(self):
        fake = _Constrained(["Working the plan."])
        _, rows = self._run(fake, mode="build", full=True, plan=HAS_A_PLAN)
        self.assertIsNone(fake.calls[0]["response_format"])
        self.assertFalse([n for n in self._notices(rows) if str(n).startswith("plan_v2")])


if __name__ == "__main__":
    unittest.main()
