"""Slice 2a of docs/plan-mode-v2-plan.md: one constrained request, then write_plan."""
from __future__ import annotations

import json
import unittest

import support

from app import events, plan_v2_turn
from app.providers import Delta


class _Fake:
    """An adapter that records its call and replies with one fixed text."""

    def __init__(self, reply: str, error: str | None = None):
        self.reply, self.error, self.calls = reply, error, []

    def stream(self, messages, tools=None, *, secret=None, response_format=None):
        self.calls.append({"messages": messages, "tools": tools, "response_format": response_format})
        if self.error:
            yield Delta(kind="error", detail=self.error)
            return
        yield Delta(kind="text", text=self.reply)
        yield Delta(kind="end")


TOOLS = [
    ("measure_eval_set", "count the eval rows"),
    ("measure_baseline", "score the base model"),
    ("start_training", "train an adapter"),
]
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
        {"do": "Measure the eval set", "tool": "measure_eval_set", "args": {}, "check": "rows counted", "approval": ""},
        {"do": "Measure the baseline", "tool": "measure_baseline", "args": {}, "check": "score exists", "approval": ""},
        {"do": "Train a LoRA adapter", "tool": "start_training", "args": {}, "check": "job id", "approval": "time"},
        {"do": "Score the adapter", "tool": "measure_baseline", "args": {}, "check": "delta reported", "approval": ""},
    ],
}


class OneConstrainedRequestTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.thread = int(events.create_thread("plan", None)["id"])

    def test_the_request_carries_the_schema_and_no_tools(self):
        fake = _Fake(json.dumps(PLAN))
        out = plan_v2_turn.plan_once(fake, "train an adapter", "", TOOLS, thread_id=self.thread)
        self.assertTrue(out["ok"], out)
        call = fake.calls[0]
        self.assertIsNone(call["tools"])
        enum = call["response_format"]["properties"]["todos"]["items"]["properties"]["tool"]["enum"]
        self.assertEqual(enum, ["measure_baseline", "measure_eval_set", "start_training", "edit"])
        self.assertNotIn("verb-first step", call["messages"][0]["content"])
        self.assertIn("- measure_eval_set: count the eval rows", call["messages"][0]["content"])

    def test_the_plan_lands_on_the_thread(self):
        plan_v2_turn.plan_once(_Fake(json.dumps(PLAN)), "train", "", TOOLS, thread_id=self.thread)
        self.assertIn("## Phase 1 - Measure the eval set", events.get_thread(self.thread)["plan"])

    def test_a_pasted_plan_is_refused_and_nothing_is_saved(self):
        bad = dict(PLAN, todos=[dict(t, do="verb-first step") for t in PLAN["todos"]])
        out = plan_v2_turn.plan_once(_Fake(json.dumps(bad)), "train", "", TOOLS, thread_id=self.thread)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "template_or_filler_todos")
        self.assertFalse(events.get_thread(self.thread).get("plan"))

    def test_not_json_and_provider_errors_are_reported(self):
        not_json = plan_v2_turn.plan_once(_Fake("I will plan now"), "t", "", TOOLS, thread_id=self.thread)
        self.assertEqual(not_json["error"], "not_json")
        down = plan_v2_turn.plan_once(_Fake("", error="down"), "t", "", TOOLS, thread_id=self.thread)
        self.assertEqual(down["error"], "provider_error")


class _Script:
    """Replies in order; records each request's messages."""

    def __init__(self, replies: list[str]):
        self.replies, self.calls = list(replies), []

    def stream(self, messages, tools=None, *, secret=None, response_format=None):
        self.calls.append([dict(m) for m in messages])
        yield Delta(kind="text", text=self.replies.pop(0))


class OneRetryTest(unittest.TestCase):
    """H-v2b: slice 3's run 2 fell back on `not_json`, and both plans that landed copied
    the prompt's description of done_when."""

    def setUp(self):
        support.sandbox(self)
        self.thread = int(events.create_thread("plan", None)["id"])

    def test_a_copied_done_when_is_refused(self):
        copied = dict(PLAN, done_when="a number on a named set, a file or a test, and the bar it must clear")
        fake = _Script([json.dumps(copied), json.dumps(copied)])
        out = plan_v2_turn.plan_once(fake, "train", "", TOOLS, thread_id=self.thread)
        self.assertEqual((out["ok"], out["error"], out["attempts"]), (False, "template_goal", 2))
        self.assertFalse(events.get_thread(self.thread).get("plan"))

    def test_the_retry_names_the_fault_and_a_good_second_reply_lands(self):
        fake = _Script(["", json.dumps(PLAN)])
        out = plan_v2_turn.plan_once(fake, "train", "", TOOLS, thread_id=self.thread)
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["attempts"], 2)
        self.assertIn("not_json", fake.calls[1][-1]["content"])
        self.assertIn("## Phase 1 - Measure the eval set", events.get_thread(self.thread)["plan"])

    def test_a_provider_error_is_not_retried(self):
        fake = _Fake("", error="down")
        plan_v2_turn.plan_once(fake, "t", "", TOOLS, thread_id=self.thread)
        self.assertEqual(len(fake.calls), 1)


if __name__ == "__main__":
    unittest.main()
