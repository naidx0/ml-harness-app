"""Their context ring shows what the harness counted, not zeros.

OpenCode's context ring and its Cost / Context / Tokens tooltip
(`session/timeline/session-context-usage.tsx`, and the context tab in
`session/files/session-context-tab.tsx`) read the LAST assistant message that
has `tokens`, add `input + output + reasoning + cache.read + cache.write`, and
divide by the `limit.context` of the model that message names. Their reducer
fills a message's `tokens` from `session.step.ended`. The facade sent zeros
there and on `Session.Info`, so the ring sat at 0% on every thread.

The numbers are the engine's own: `input` is the `turn.context` total the
conductor counted on the prompt it sent (the figure `/api/threads/{id}/usage`
and `/context` report), and `output` / `reasoning` are the text the model
streamed, counted with the same `providers.budget.estimate`.
"""

from __future__ import annotations

import base64
import math
import unittest

from fastapi.testclient import TestClient

from app import events, security
from app.facade import sessions, translate, turns
from app.providers import Delta
from app.providers import budget
from app.providers import store as provider_store

import openapi_contract as contract
import support

MESSAGE = {"$ref": "#/components/schemas/Session.Message.Info"}


def tokens_for(chars: int) -> int:
    return int(math.ceil(chars / budget.CHARS_PER_TOKEN))


def ring(message: dict) -> int:
    """What their ring adds up, exactly as `session-context-usage.tsx` does."""
    t = message["tokens"]
    return t["input"] + t["output"] + t["reasoning"] + t["cache"]["read"] + t["cache"]["write"]


class SpendTestCase(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        from app.main import app

        raw = base64.b64encode(f"opencode:{security.current_token()}".encode()).decode()
        self.client = TestClient(app, headers={"Authorization": f"Basic {raw}"})
        self.addCleanup(self.client.close)
        (self.thread,) = support.conversations(1)
        self.tid = self.thread["id"]
        self.sid = sessions.session_id(self.tid)

    def write(self, *rows):
        for kind, payload in rows:
            events.append(kind, payload, thread_id=self.tid)

    def turn(self, *middle, ending="answered"):
        self.write(("turn.started", {"provider": "Local", "model": "m-7b"}), *middle)
        self.write(("stream.end", {"ending": ending, "rounds": 1, "seconds": 0.1}))

    def replay(self):
        return translate.translate(events.since(f"thread:{self.tid}", 0, limit=10_000))

    def session(self):
        response = self.client.get(f"/oc/api/session/{self.sid}")
        return contract.assert_response(self, "session.get", response)["data"]


class AMeasuredTurnIsNotZeroTest(SpendTestCase):
    def test_step_ended_carries_the_prompt_the_engine_counted_and_what_the_model_wrote(self):
        self.turn(
            ("turn.context", {"total": 5000, "system": 3000, "tools": 1500, "history": 500, "window": 32768}),
            ("chat.reasoning", {"text": "think about it"}),
            ("chat.delta", {"text": "Hello"}),
            ("chat.delta", {"text": " world"}),
        )
        out = self.replay()
        for event in out:
            self.assertEqual(contract.event_problems(event), [], event)
        (ended,) = [e["data"] for e in out if e["type"] == "session.step.ended"]
        self.assertEqual(
            ended["tokens"],
            {
                "input": 5000,
                "output": tokens_for(len("Hello world")),
                "reasoning": tokens_for(len("think about it")),
                "cache": {"read": 0, "write": 0},
            },
        )
        # The engine prices nothing (`catalog` sends `cost: []`), so 0 is true.
        self.assertEqual(ended["cost"], 0)

        (reply,) = [m for m in translate.fold(out) if m["type"] == "assistant"]
        self.assertEqual(contract.errors(reply, MESSAGE), [], reply)
        self.assertEqual(reply["tokens"], ended["tokens"])
        self.assertEqual(ring(reply), 5000 + tokens_for(11) + tokens_for(14))

    def test_the_context_pane_still_gets_its_own_row(self):
        self.turn(("turn.context", {"total": 5000}), ("chat.delta", {"text": "ok"}))
        passed = [e for e in self.replay() if e["type"] == "harness.turn.context"]
        self.assertEqual(len(passed), 1)
        self.assertEqual(passed[0]["data"]["payload"]["total"], 5000)

    def test_session_get_reports_the_threads_spend(self):
        self.turn(("turn.context", {"total": 5000}), ("chat.delta", {"text": "Hello world"}))
        info = self.session()
        self.assertEqual(info["tokens"]["input"], 5000)
        self.assertEqual(info["tokens"]["output"], tokens_for(11))
        self.assertEqual(info["tokens"]["reasoning"], 0)
        self.assertEqual(info["cost"], 0)

    def test_session_get_is_the_sum_of_every_step_it_ended(self):
        """Two readers of one log: the session total and the per-step events
        must agree, or the tooltip and the ring tell two stories."""
        self.turn(
            ("turn.context", {"total": 4000}),
            ("chat.reasoning", {"text": "a" * 37}),
            ("chat.delta", {"text": "b" * 50}),
        )
        self.turn(
            ("turn.context", {"total": 4600}),
            ("tool.call", {"id": "c1", "name": "list_context", "arguments": {}}),
            ("tool.result", {"id": "c1", "name": "list_context", "ok": True, "result": {"count": 0}}),
            ("chat.delta", {"text": "c" * 23}),
        )
        steps = [e["data"]["tokens"] for e in self.replay() if e["type"] == "session.step.ended"]
        self.assertEqual(len(steps), 2)
        total = self.session()["tokens"]
        for key in ("input", "output", "reasoning"):
            self.assertEqual(total[key], sum(step[key] for step in steps), key)
        self.assertEqual(total["input"], 8600)

    def test_a_stream_opened_mid_turn_still_knows_the_prompt(self):
        """The live stream primes a running turn silently; the prompt it
        counted is part of what it must remember."""
        self.write(
            ("turn.started", {"provider": "Local", "model": "m-7b"}),
            ("turn.context", {"total": 7000}),
            ("chat.delta", {"text": "par"}),
        )
        live = translate.Translator(prime=True)
        events.append("chat.delta", {"text": "tial"}, thread_id=self.tid)
        events.append("stream.end", {"ending": "answered"}, thread_id=self.tid)
        after = events.since(f"thread:{self.tid}", 0, limit=100)[-2:]
        out = [e for row in after for e in live.feed(row)]
        (ended,) = [e["data"] for e in out if e["type"] == "session.step.ended"]
        self.assertEqual(ended["tokens"]["input"], 7000)
        self.assertEqual(ended["tokens"]["output"], tokens_for(len("partial")))


class NoTurnsStillValidatesTest(SpendTestCase):
    def test_a_thread_with_no_turns_is_zeros_in_their_schema(self):
        info = self.session()
        self.assertEqual(info["tokens"], {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}})
        self.assertEqual(info["cost"], 0)

    def test_a_turn_that_counted_nothing_is_zero_input_not_an_error(self):
        self.turn()
        out = self.replay()
        for event in out:
            self.assertEqual(contract.event_problems(event), [], event)
        (ended,) = [e["data"] for e in out if e["type"] == "session.step.ended"]
        self.assertEqual(ended["tokens"]["input"], 0)
        self.assertEqual(self.session()["tokens"]["input"], 0)


class Answers:
    id = "scripted"
    locality = "local"

    def stream(self, messages, tools=None, *, secret=None):
        yield Delta(kind="text", text="Here is ")
        yield Delta(kind="text", text="the answer.")

    def capabilities(self, *, secret=None):
        raise AssertionError("the loop must not probe mid-turn")


class ARealTurnFillsTheRingTest(SpendTestCase):
    def test_a_turn_through_the_conductor_reports_its_counted_prompt(self):
        from app import conductor

        row = provider_store.create("Local", "http://127.0.0.1:11434", "scripted-7b", "ollama")
        provider_store.set_active(row["id"])
        original = conductor.build
        conductor.build = lambda *a, **k: Answers()
        self.addCleanup(setattr, conductor, "build", original)

        sid = contract.assert_response(
            self, "session.create", self.client.post("/oc/api/session", json={"title": "ask"})
        )["data"]["id"]
        self.client.post(
            f"/oc/api/session/{sid}/prompt", json={"id": "msg_0000c0ffee00AbCdEfGhIjKlMn", "text": "hi"}
        )
        thread_id = sessions.thread_id_of(sid)
        self.assertTrue(turns.wait(thread_id, timeout=30), "the facade turn did not finish")

        counted = self.client.get(f"/api/threads/{thread_id}/usage").json()["thread"]["latest_tokens"]
        self.assertGreater(counted, 0)
        listed = contract.assert_response(
            self, "session.message.list", self.client.get(f"/oc/api/session/{sid}/message")
        )["data"]
        (reply,) = [m for m in listed if m["type"] == "assistant"]
        self.assertEqual(reply["tokens"]["input"], counted)
        self.assertEqual(reply["tokens"]["output"], tokens_for(len("Here is the answer.")))
        info = contract.assert_response(
            self, "session.get", self.client.get(f"/oc/api/session/{sid}")
        )["data"]
        self.assertEqual(info["tokens"]["input"], counted)


if __name__ == "__main__":
    unittest.main()
