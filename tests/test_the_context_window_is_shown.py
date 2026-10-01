"""What a turn spends of the window is counted when it is sent, and read back.

Max, 2026-09-13: *"we need a context window showcase for ML Harness."*
`app/contextwindow.py` reads the `turn.context` rows the conductor writes at
assembly time. The numbers are the ones the adapter's own budget check
counts, on the prompt that was actually sent - the pane does no arithmetic
and invents no estimate for a prompt that was never built.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import contextwindow, events  # noqa: E402
from app.providers import Delta  # noqa: E402
from app.providers import store as provider_store  # noqa: E402

CONVERSATION = [
    {"role": "system", "content": "you are a harness " * 400},
    {"role": "user", "content": "carve the eval set"},
    {"role": "assistant", "content": "done"},
]
TOOLS = [
    {"type": "function", "function": {"name": "carve_eval_set", "description": "x " * 50, "parameters": {}}},
    {"type": "function", "function": {"name": "measure_baseline", "description": "y " * 50, "parameters": {}}},
]


class MeasureTest(unittest.TestCase):
    def test_the_three_halves_of_a_prompt_are_counted_apart(self):
        cost = contextwindow.measure(CONVERSATION, TOOLS)
        self.assertGreater(cost["system"], 500, "a 400-phrase system prompt is not small")
        self.assertGreater(cost["tools"], 0)
        self.assertGreater(cost["history"], 0)
        self.assertEqual(cost["total"], cost["system"] + cost["tools"] + cost["history"])
        self.assertEqual(cost["messages"], 2, "the system prompt is not one of the messages")
        self.assertEqual(cost["tool_count"], 2)

    def test_no_tools_costs_no_tokens_for_tools(self):
        self.assertEqual(contextwindow.measure(CONVERSATION, None)["tools"], 0)
        self.assertEqual(contextwindow.measure(None, None)["total"], 0)


class PartsTest(unittest.TestCase):
    """The breakdown Max asked for, counted on the pieces the prompt was
    built FROM rather than on the string they were joined into."""

    def setUp(self) -> None:
        support.sandbox(self)

    def test_every_piece_is_named_counted_and_sorted_biggest_first(self):
        rows = contextwindow.parts(
            conversation=CONVERSATION + [{"role": "user", "content": "THE BRIEF " * 30}],
            tools=TOOLS,
            instructions="the instruction set " * 300,
            notes={"memory": "what this project knows " * 20, "plan": "", "goal": "the goal"},
            brief="THE BRIEF " * 30,
        )
        by_key = {row["key"]: row for row in rows}
        self.assertIn("instructions", by_key)
        self.assertIn("memory", by_key)
        self.assertIn("goal", by_key)
        self.assertNotIn("plan", by_key, "an empty note is not a row")
        self.assertIn("brief", by_key)
        self.assertIn("messages", by_key)
        self.assertEqual(by_key["instructions"]["label"], "Instruction set")
        self.assertTrue(by_key["memory"]["why"], "every row says what it is")
        self.assertEqual(
            [row["tokens"] for row in rows],
            sorted((row["tokens"] for row in rows), reverse=True),
            "biggest first, so the thing to do something about is at the top",
        )

    def test_the_brief_is_its_own_row_and_not_counted_as_conversation(self):
        brief = "THE BRIEF " * 30
        rows = contextwindow.parts(
            conversation=[{"role": "user", "content": "hello"}, {"role": "user", "content": brief}],
            tools=None,
            instructions="x",
            notes={},
            brief=brief,
        )
        by_key = {row["key"]: row for row in rows}
        self.assertEqual(by_key["messages"]["count"], 1, "the brief is not one of the messages")
        self.assertGreater(by_key["brief"]["tokens"], by_key["messages"]["tokens"])

    def test_tool_schemas_are_grouped_by_the_pack_the_registry_puts_them_in(self):
        from app.tools.registry import REGISTRY

        schemas = REGISTRY.model_tools(["inspect_hardware", "write_plan", "read_plan"])
        rows = contextwindow.parts(
            conversation=None, tools=schemas, instructions="", notes={}, brief=""
        )
        packs = {row["key"] for row in rows if row["key"].startswith("tools:")}
        self.assertTrue(packs, "the tools are grouped, not one lump")
        counted = sum(row["count"] for row in rows if row["key"].startswith("tools:"))
        self.assertEqual(counted, 3, "every offered tool is counted exactly once")


class ATurnRecordsWhatItSpentTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        row = provider_store.create("Fake", "http://127.0.0.1:11434", "fake-model", "ollama")
        provider_store.record_capabilities(
            row["id"],
            type("Caps", (), {"tool_calling": True, "detail": "test", "ctx_len": 8192,
                              "provenance": {"ctx_len": "measured"}})(),
        )
        provider_store.set_active(row["id"])
        self.thread = int(events.create_thread("t", mode="build")["id"])
        events.add_message(self.thread, "user", "carve the eval set")

    def run_turn(self) -> None:
        from app import conductor

        class Fake:
            id = "fake"
            locality = "local"

            def stream(self, messages, tools=None, *, secret=None):
                yield Delta(kind="text", text="Done.")

        original = conductor.build
        conductor.build = lambda *a, **k: Fake()
        try:
            for _ in conductor.run_turn(self.thread):
                pass
        finally:
            conductor.build = original

    def test_the_turn_writes_one_reading_and_the_pane_reads_it(self):
        self.run_turn()
        rows = [r for r in events.since(f"thread:{self.thread}", limit=5000)
                if r["kind"] == contextwindow.KIND]
        self.assertEqual(len(rows), 1, "one reading per turn, at assembly")
        payload = rows[0]["payload"]
        self.assertGreater(payload["system"], 0, "the system prompt is on every wire")
        self.assertGreater(payload["total"], payload["system"] - 1)
        self.assertEqual(payload["mode"], "build")

        # The breakdown rides on the same row, so the pane draws what was sent.
        self.assertTrue(payload["parts"], "a turn carries its breakdown")
        keys = {row["key"] for row in payload["parts"]}
        self.assertIn("instructions", keys)
        self.assertIn("brief", keys)
        self.assertTrue(any(key.startswith("tools:") for key in keys))
        self.assertLessEqual(
            sum(row["tokens"] for row in payload["parts"]),
            int(payload["total"] * 1.05) + 50,
            "the parts add up to about the total - they are the same prompt",
        )

        # AND WHICH TOOLS THOSE SCHEMAS WERE, added 2026-09-18 with
        # `app/tools/blocks.py:on_the_wire`. The `tools` figure says what they
        # COST; without this the pane can show a turn carrying nine schemas on a
        # harness of 88 and give a person no way to tell a narrow turn from a
        # small product - which is the live fabrication
        # `app/instructions/capabilities.py` exists for, redrawn in a pane.
        wire = payload["schemas_on_wire"]
        self.assertEqual(payload["tool_count"], len(wire["tools"]))
        self.assertEqual(set(wire["because"]), set(wire["tools"]))
        self.assertEqual(
            set(wire["tools"]) | set(wire["withheld"]), set(wire["considered"])
        )
        self.assertIn("all_schemas", wire, "the arm the turn ran in is not recorded")

        read = contextwindow.read(self.thread)
        self.assertEqual(read["latest"]["total"], payload["total"])
        self.assertEqual(read["latest"]["parts"], payload["parts"])
        self.assertEqual(read["latest"]["schemas_on_wire"], wire)
        self.assertEqual(read["model"], "fake-model")
        self.assertEqual(len(read["turns"]), 1)
        self.assertEqual(read["compactions"], [])
        self.assertIn("budget.py", read["counted_by"])

    def test_the_window_and_the_headroom_come_from_the_probe(self):
        self.run_turn()
        read = contextwindow.read(self.thread)
        self.assertEqual(read["window"], 8192)
        self.assertEqual(read["window_provenance"], "measured")
        self.assertEqual(read["headroom"], max(0, 8192 - read["latest"]["total"]))
        self.assertGreater(read["share"], 0.0)
        # MEASURED HERE, and it is the reason the pane exists: this harness's
        # own system prompt and tool schemas do not fit an 8k window at all -
        # the reading is over 1.0 before the person has typed a second
        # message. A real turn against such a model is refused by
        # `budget.plan` before a byte is sent; the pane is where a person
        # sees that coming.
        self.assertGreater(read["latest"]["total"], 8192)
        self.assertGreater(read["share"], 1.0)
        self.assertEqual(read["headroom"], 0, "over the window is zero headroom, never a negative one")

    def test_two_turns_are_two_readings_in_order(self):
        self.run_turn()
        events.add_message(self.thread, "user", "and the baseline")
        self.run_turn()
        read = contextwindow.read(self.thread)
        self.assertEqual(len(read["turns"]), 2)
        self.assertLess(read["turns"][0]["event_id"], read["turns"][1]["event_id"])
        self.assertGreaterEqual(read["turns"][1]["history"], read["turns"][0]["history"],
                                "the conversation only grows until something compacts it")

    def test_a_thread_with_no_turn_says_so_rather_than_guessing(self):
        quiet = int(events.create_thread("quiet", mode="build")["id"])
        read = contextwindow.read(quiet)
        self.assertIsNone(read["latest"])
        self.assertEqual(read["turns"], [])
        self.assertIsNone(read["headroom"])
        self.assertIsNone(read["share"])


class OverHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        from app.main import app

        self.client = support.api_client(app)
        self.addCleanup(self.client.close)

    def test_the_route_answers_and_404s_for_a_missing_thread(self):
        thread = self.client.post("/api/threads", json={"title": "t"}).json()
        got = self.client.get(f"/api/threads/{thread['id']}/context")
        self.assertEqual(got.status_code, 200, got.text)
        body: dict[str, Any] = got.json()
        self.assertEqual(body["thread_id"], thread["id"])
        self.assertIsNone(body["latest"])
        self.assertEqual(self.client.get("/api/threads/99999/context").status_code, 404)


if __name__ == "__main__":
    unittest.main()
