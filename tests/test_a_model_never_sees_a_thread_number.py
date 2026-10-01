"""The model never sees its thread number - not in the schema either.

The second live score row, 2026-09-18, on b601da9: one reply carried two
hundred `read_plan` calls, six rounds carried 1,246, each with a different
`thread_id` - 2, 3, ... 196 - because the schema advertised the field. The
registry fills that field from the call site and overwrites whatever the
model sent, so the argument did nothing except defeat the memo that would
have caught the repeat. Nine minutes and a provider timeout, for nothing.

Two laws. No model-facing schema carries `thread_id`, derived over the whole
registry rather than listed. And a round runs at most MAX_CALLS_PER_ROUND
calls and says so, because a list of two hundred identical calls is a loop
written as a list.
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
from app import conductor, events  # noqa: E402
from app.providers import Delta, ToolCall  # noqa: E402
from app.tools import REGISTRY, evidence  # noqa: E402


class NoSchemaCarriesTheThreadNumberTest(unittest.TestCase):
    def test_every_model_facing_schema_is_free_of_thread_id(self):
        offenders = []
        for spec in REGISTRY:
            params = spec.as_model_tool()["function"]["parameters"]
            if "thread_id" in (params.get("properties") or {}) or "thread_id" in (params.get("required") or ()):
                offenders.append(spec.name)
        self.assertEqual(offenders, [], "these tools still advertise thread_id to the model")

    def test_the_registry_still_fills_it_from_the_call_site(self):
        support.sandbox(self)
        thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_plan(thread, "## Phase 1 - A" + chr(10) + "- [ ] Measure with measure_baseline")
        out = REGISTRY.call("read_plan", {"thread_id": 999}, actor=evidence.MODEL, thread_id=thread)
        self.assertTrue(out["ok"], out)
        self.assertIn("measure_baseline", out.get("plan") or "")

    def test_the_wire_declaration_keeps_every_other_parameter(self):
        spec = REGISTRY.get("measure_baseline")
        params = spec.as_model_tool()["function"]["parameters"]
        self.assertIn("eval_path", params["properties"])
        self.assertEqual(sorted(params["required"]), ["eval_path", "expected_field", "input_field"])


from test_a_turn_always_speaks import ScriptedProvider, TurnTestCase, says  # noqa: E402


class ARoundRunsSoManyCallsAndSaysSoTest(TurnTestCase):
    def test_two_hundred_calls_in_one_reply_run_twelve_and_leave_a_notice(self):
        self.connect()
        thread_id = self.new_thread()
        storm = [Delta(kind="tool_call", tool_calls=tuple(
            ToolCall(f"s{i}", "list_runs", {"limit": i + 1}) for i in range(200)
        ))]
        self.install(ScriptedProvider([storm, says("done")]))
        rows = list(conductor.run_turn(thread_id, max_tool_rounds=8))
        calls = [r for r in rows if r["kind"] == "tool.call"]
        notices = [r["payload"] for r in rows if r["kind"] == "conductor.notice"
                   and r["payload"].get("reason") == "too_many_calls_in_one_round"]
        self.assertLessEqual(len(calls), conductor.MAX_CALLS_PER_ROUND)
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]["asked"], 200)
        self.assertEqual(notices[0]["ran"], conductor.MAX_CALLS_PER_ROUND)


if __name__ == "__main__":
    unittest.main()
