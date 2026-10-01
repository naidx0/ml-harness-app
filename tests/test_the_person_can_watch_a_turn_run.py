"""While a turn runs, the person can see what the model is thinking and which tool it is in.

Max, 2026-09-21: he could not see what the model was thinking or which tool it
was calling while a turn ran. Two halves:

- ENGINE. `tool.call` is committed BEFORE the tool executes, with its
  arguments, so "calling measure_baseline" can be drawn while it runs rather
  than when it returns. (It already was; this locks it.) And a thinking
  model's reasoning streams as its own kind, `chat.reasoning`, as it arrives -
  it used to be dropped by the adapters altogether.
- FACADE. Their schema has a reasoning part (`session.reasoning.started` /
  `.delta` / `.ended`, `Session.Message.Assistant.Reasoning`); `chat.reasoning`
  now maps to it, and `tool.call` still maps to `session.tool.input.started` /
  `session.tool.called`.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import openapi_contract as contract  # noqa: E402
import support  # noqa: E402
from app import conductor, events  # noqa: E402
from app.facade import translate  # noqa: E402
from app.providers import Delta, ToolCall  # noqa: E402
from app.providers import store as provider_store  # noqa: E402

MESSAGE = {"$ref": "#/components/schemas/Session.Message.Info"}

#: Their data fields, read from `@opencode/schema/dist/event-manifest.d.ts`
#: (2.0.14, the version `event_contract.json` names). `state` is optional on
#: started/ended and this engine has none to send.
REASONING_FIELDS = {
    "session.reasoning.started": {"sessionID", "assistantMessageID", "ordinal"},
    "session.reasoning.delta": {"sessionID", "assistantMessageID", "ordinal", "delta"},
    "session.reasoning.ended": {"sessionID", "assistantMessageID", "ordinal", "text"},
}


class Scripted:
    id = "fake"
    locality = "local"

    def __init__(self, scripts):
        self.scripts = list(scripts)

    def stream(self, messages, tools=None, *, secret=None, **_):
        for delta in (self.scripts.pop(0) if self.scripts else []):
            yield delta

    def capabilities(self, *, secret=None):
        raise AssertionError("no probe mid-turn")


class TheEngineShowsTheTurnAsItRuns(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        row = provider_store.create("Fake", "http://127.0.0.1:11434", "fake-model", "ollama")
        # A connection that can call tools, or the conductor offers none and
        # drops every call the model makes.
        caps = type(
            "Caps", (), {"tool_calling": True, "detail": "set by the test", "ctx_len": None, "provenance": {}}
        )()
        provider_store.record_capabilities(row["id"], caps)
        provider_store.set_active(row["id"])

    def test_the_call_row_is_committed_before_the_tool_runs(self) -> None:
        thread = int(events.create_thread("t")["id"])
        events.add_message(thread, "user", "what runs have I got?")
        provider = Scripted(
            [
                [Delta(kind="tool_call", tool_calls=(ToolCall("c-live", "run_diagnosis", {"facts": {}}),))],
                [Delta(kind="text", text="None yet.")],
            ]
        )
        original_build = conductor.build
        conductor.build = lambda *a, **k: provider
        self.addCleanup(setattr, conductor, "build", original_build)

        seen_at_run_time: list[dict] = []
        real_call = conductor.REGISTRY.call

        def spy(name, arguments=None, **kwargs):
            if name == "run_diagnosis" and kwargs.get("actor") == "model":
                rows = events.since(f"thread:{thread}", limit=100_000)
                seen_at_run_time.extend(
                    r["payload"] for r in rows if r["kind"] == "tool.call"
                )
                self.assertFalse(
                    any(r["kind"] == "tool.result" for r in rows), "the result came first"
                )
            return real_call(name, arguments, **kwargs)

        conductor.REGISTRY.call = spy
        self.addCleanup(setattr, conductor.REGISTRY, "call", real_call)
        list(conductor.run_turn(thread))
        self.assertEqual(
            [(p["id"], p["name"], p["arguments"]) for p in seen_at_run_time],
            [("c-live", "run_diagnosis", {"facts": {}})],
        )

    def test_reasoning_is_written_as_it_arrives_before_the_reply(self) -> None:
        thread = int(events.create_thread("t")["id"])
        events.add_message(thread, "user", "should I train?")
        provider = Scripted(
            [[Delta(kind="reasoning", text="Check the eval set first.\n"), Delta(kind="text", text="Count it first.")]]
        )
        original_build = conductor.build
        conductor.build = lambda *a, **k: provider
        self.addCleanup(setattr, conductor, "build", original_build)
        list(conductor.run_turn(thread))
        rows = events.since(f"thread:{thread}", limit=100_000)
        kinds = [r["kind"] for r in rows if r["kind"] in (conductor.REASONING_KIND, "chat.delta")]
        self.assertEqual(kinds[0], conductor.REASONING_KIND)
        self.assertIn("chat.delta", kinds)


class TheFacadeDrawsThinkingAndTools(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        (thread,) = support.conversations(1)
        self.tid = thread["id"]

    def write(self, *rows):
        for kind, payload in rows:
            events.append(kind, payload, thread_id=self.tid)

    def replay(self):
        return translate.translate(events.since(f"thread:{self.tid}", 0, limit=10_000))

    def test_reasoning_becomes_their_reasoning_part_then_the_tool_then_the_text(self) -> None:
        self.write(
            ("turn.started", {"provider": "Local", "model": "m-7b"}),
            ("chat.reasoning", {"text": "The eval set "}),
            ("chat.reasoning", {"text": "is not counted."}),
            ("tool.call", {"id": "c1", "name": "measure_eval_set", "arguments": {"path": "eval.jsonl"}}),
            ("tool.result", {"id": "c1", "name": "measure_eval_set", "ok": True, "result": {"rows": 40}}),
            ("chat.reasoning", {"text": "Forty rows."}),
            ("chat.delta", {"text": "Counted 40."}),
            ("stream.end", {"ending": "answered", "rounds": 2, "seconds": 0.1}),
        )
        out = self.replay()
        self.assertEqual(
            [e["type"] for e in out],
            [
                "session.execution.started",
                "session.step.started",
                "session.reasoning.started",
                "session.reasoning.delta",
                "session.reasoning.delta",
                "session.reasoning.ended",
                "session.tool.input.started",
                "session.tool.called",
                "session.tool.success",
                "session.reasoning.started",
                "session.reasoning.delta",
                "session.reasoning.ended",
                "session.text.started",
                "session.text.delta",
                "session.text.ended",
                "session.step.ended",
                "session.execution.succeeded",
            ],
        )
        for event in out:
            wanted = REASONING_FIELDS.get(event["type"])
            if wanted is not None:
                self.assertEqual(set(event["data"]), wanted, event)
            self.assertEqual(contract.event_problems(event), [], event)
            self.assertEqual("durable" in event, not translate.is_ephemeral(event["type"]), event)
        ordinals = [
            (e["type"], e["data"]["ordinal"])
            for e in out
            if e["type"] in ("session.reasoning.ended", "session.text.ended")
        ]
        self.assertEqual(
            ordinals,
            [("session.reasoning.ended", 0), ("session.reasoning.ended", 1), ("session.text.ended", 2)],
        )
        called = next(e for e in out if e["type"] == "session.tool.called")
        self.assertEqual(called["data"]["input"], {"path": "eval.jsonl"})

        messages = translate.fold(out)
        reply = next(m for m in messages if m["type"] == "assistant")
        self.assertEqual([p["type"] for p in reply["content"]], ["reasoning", "tool", "reasoning", "text"])
        self.assertEqual(reply["content"][0]["text"], "The eval set is not counted.")
        self.assertIn("completed", reply["content"][0]["time"])
        for message in messages:
            self.assertEqual(contract.errors(message, MESSAGE), [], message)

    def test_a_folded_replay_draws_the_same_thinking(self) -> None:
        self.write(
            ("turn.started", {"provider": "Local", "model": "m-7b"}),
            ("chat.reasoning", {"text": "one "}),
            ("chat.reasoning", {"text": "two"}),
            ("chat.delta", {"text": "Done."}),
            ("stream.end", {"ending": "answered", "rounds": 1, "seconds": 0.1}),
        )
        rows = events.since(f"thread:{self.tid}", 0, limit=10_000)
        live = translate.fold(translate.translate(rows))
        folded = translate.fold(translate.translate(events.fold_replay(rows)))
        strip = lambda ms: [[{k: v for k, v in p.items() if k != "time"} for p in m.get("content", [])] for m in ms]  # noqa: E731
        self.assertEqual(strip(live), strip(folded))
        self.assertEqual(len(events.fold_replay(rows)), len(rows) - 1, "two reasoning rows fold to one")


if __name__ == "__main__":
    unittest.main()
