"""The engine's event log, replayed through the translator, is their stream.

OpenCode's client builds its whole transcript from the event stream: a step is
opened, a text part is started and filled and closed, a tool part streams,
runs and settles, an execution ends. `app/facade/translate.py` produces those
events from the rows `app/conductor.py` writes. These tests feed it runs built
from the conductor's own row kinds and payloads, and check what comes out
against two contracts:

* `app/facade/event_contract.json`, generated from `@opencode/schema` by
  `scripts/extract_event_contract.py` - the envelope keys, and each event's
  required and allowed data fields;
* their OpenAPI document (`app/facade/openapi.json`, upstream `ad1a4a6`, MIT),
  against which the transcript folded from those events must validate as
  `Session.Message.Info`.

And the live stream is held to what their client demands of it, read from
`createClientConnection2` in `@opencode/client`: `server.connected` first and
within two seconds, activity at least every 45 seconds, one JSON envelope per
`data:` line.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app import events, security
from app.facade import stream, translate

import openapi_contract as contract
import support

MESSAGE = {"$ref": "#/components/schemas/Session.Message.Info"}


def data_of(frame: str) -> dict | None:
    lines = [line[5:].strip() for line in frame.split("\n") if line.startswith("data:")]
    return json.loads("\n".join(lines)) if lines else None


class TranslatorTestCase(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        (self.thread,) = support.conversations(1)
        self.tid = self.thread["id"]

    def write(self, *rows):
        for kind, payload in rows:
            events.append(kind, payload, thread_id=self.tid)

    def replay(self):
        return translate.translate(events.since(f"thread:{self.tid}", 0, limit=10_000))

    def types(self, stream_events):
        return [event["type"] for event in stream_events]

    def assert_well_formed(self, stream_events):
        problems = [p for event in stream_events for p in contract.event_problems(event)]
        self.assertEqual(problems, [])
        ids = [event["id"] for event in stream_events]
        self.assertEqual(ids, sorted(ids), "their ids must sort in the order they were sent")
        self.assertEqual(len(ids), len(set(ids)))
        for event in stream_events:
            self.assertEqual("durable" in event, not translate.is_ephemeral(event["type"]), event)
        messages = translate.fold(stream_events)
        for message in messages:
            self.assertEqual(contract.errors(message, MESSAGE), [], message)
        return messages

    def turn(self, *middle, ending="answered"):
        self.write(("turn.started", {"provider": "Local", "model": "m-7b"}), *middle)
        self.write(("stream.end", {"ending": ending, "rounds": 1, "seconds": 0.1}))


class AWholeTurnTest(TranslatorTestCase):
    def test_a_turn_with_text_and_a_tool_is_the_sequence_their_reducer_reads(self):
        self.write(("message.created", {"id": 1, "role": "user", "content": "hi", "oc_id": "msg_abc"}))
        self.turn(
            ("chat.delta", {"text": "Hel"}),
            ("chat.delta", {"text": "lo"}),
            ("tool.call", {"id": "c1", "name": "list_context", "arguments": {}}),
            ("tool.result", {"id": "c1", "name": "list_context", "ok": True, "result": {"count": 0}}),
            ("chat.delta", {"text": " done"}),
        )
        out = self.replay()
        self.assertEqual(
            self.types(out),
            [
                "session.inbox.enqueued",
                "session.inbox.delivered",
                "session.execution.started",
                "session.step.started",
                "session.text.started",
                "session.text.delta",
                "session.text.delta",
                "session.text.ended",
                "session.tool.input.started",
                "session.tool.called",
                "session.tool.success",
                "session.text.started",
                "session.text.delta",
                "session.text.ended",
                "session.step.ended",
                "session.execution.succeeded",
            ],
        )
        ended = [e["data"] for e in out if e["type"] == "session.text.ended"]
        self.assertEqual([(e["ordinal"], e["text"]) for e in ended], [(0, "Hello"), (1, " done")])
        messages = self.assert_well_formed(out)
        self.assertEqual([m["type"] for m in messages], ["user", "assistant", "idle"])
        self.assertEqual(messages[0]["id"], "msg_abc")
        reply = messages[1]
        self.assertEqual([p["type"] for p in reply["content"]], ["text", "tool", "text"])
        self.assertEqual(reply["model"], {"id": "m-7b", "providerID": "conn-gone"})

    def test_the_folded_replay_and_the_live_deltas_build_the_same_transcript(self):
        """History is folded (`events.fold_replay`); live is not. Same result."""
        self.turn(*[("chat.delta", {"text": piece}) for piece in ("a", "b", "c")])
        rows = events.since(f"thread:{self.tid}", 0)
        live = translate.fold(translate.translate(rows))
        folded = translate.fold(translate.translate(events.fold_replay(rows)))
        self.assertEqual(
            [m["content"] for m in live if m["type"] == "assistant"],
            [m["content"] for m in folded if m["type"] == "assistant"],
        )


class TheWaysATurnEndsTest(TranslatorTestCase):
    def test_a_stop_is_their_interruption_not_an_error(self):
        self.turn(("chat.delta", {"text": "partial"}), ending="stopped_by_the_person")
        out = self.replay()
        self.assertIn("session.execution.interrupted", self.types(out))
        self.assertNotIn("session.execution.failed", self.types(out))
        self.assertNotIn("session.step.failed", self.types(out))
        interrupted = [e for e in out if e["type"] == "session.execution.interrupted"][0]
        self.assertEqual(interrupted["data"]["reason"], "user")
        messages = self.assert_well_formed(out)
        self.assertEqual(messages[-1]["outcome"], "interrupted")

    def test_a_tool_that_never_reports_is_closed_when_the_turn_ends(self):
        self.turn(("tool.call", {"id": "c1", "name": "start_training", "arguments": {"x": 1}}))
        out = self.replay()
        failed = [e["data"] for e in out if e["type"] == "session.tool.failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["error"]["type"], "tool.unfinished")
        self.assertIn("session.execution.succeeded", self.types(out))
        messages = self.assert_well_formed(out)
        self.assertEqual(messages[0]["content"][0]["state"]["status"], "error")

    def test_a_turn_whose_engine_died_is_closed_by_the_next_one(self):
        self.write(
            ("turn.started", {"provider": "Local", "model": "m"}),
            ("chat.delta", {"text": "never finished"}),
        )
        self.turn(("chat.delta", {"text": "second"}))
        out = self.replay()
        self.assertEqual(self.types(out).count("session.step.started"), 2)
        self.assertEqual(self.types(out).count("session.step.failed"), 1)
        messages = self.assert_well_formed(out)
        assistants = [m for m in messages if m["type"] == "assistant"]
        self.assertEqual(assistants[0]["finish"], "error")
        self.assertEqual(assistants[1]["finish"], "stop")

    def test_a_provider_failure_carries_the_engines_own_words(self):
        self.turn(("chat.error", {"detail": "connection refused"}), ending="provider_failed")
        out = self.replay()
        failed = [e["data"] for e in out if e["type"] == "session.step.failed"][0]
        self.assertEqual(failed["error"]["message"], "connection refused")
        self.assertIn("session.execution.failed", self.types(out))
        self.assert_well_formed(out)

    def test_a_turn_that_could_not_start_is_an_error_card(self):
        self.write(("turn.refused", {"detail": "No model is connected."}))
        out = self.replay()
        self.assertEqual(
            self.types(out),
            ["session.execution.started", "session.step.started", "session.step.failed", "session.execution.failed"],
        )
        messages = self.assert_well_formed(out)
        self.assertEqual(messages[0]["error"]["message"], "No model is connected.")


class ArrivalsTheReducerDidNotExpectTest(TranslatorTestCase):
    def test_a_result_before_its_call_does_not_crash_and_still_draws_a_card(self):
        self.turn(
            ("tool.result", {"id": "late", "name": "list_runs", "ok": True, "result": []}),
            ("tool.call", {"id": "late", "name": "list_runs", "arguments": {}}),
        )
        out = self.replay()
        messages = self.assert_well_formed(out)
        statuses = [p["state"]["status"] for p in messages[0]["content"]]
        self.assertEqual(statuses, ["completed", "error"])

    def test_a_person_driven_tool_outside_a_turn_is_its_own_step(self):
        self.write(
            ("tool.call", {"id": "user-1", "name": "attach_context", "arguments": {"path": "/x"}, "driven_by": "user"}),
            ("tool.result", {"id": "user-1", "name": "attach_context", "ok": True, "result": {"ok": True}, "driven_by": "user"}),
        )
        out = self.replay()
        self.assertEqual(
            self.types(out),
            [
                "session.step.started",
                "session.tool.input.started",
                "session.tool.called",
                "session.tool.success",
                "session.step.ended",
            ],
        )
        self.assert_well_formed(out)

    def test_an_empty_or_odd_payload_is_ignored_not_raised(self):
        self.write(("chat.delta", {}), ("tool.result", {}), ("thread.mode", {"mode": None}), ("stream.end", {}))
        self.assert_well_formed(self.replay())


class TheEnginesOwnEventsRideAlongTest(TranslatorTestCase):
    """What their protocol has no word for arrives as `harness.<kind>`."""

    def test_an_untranslated_row_passes_through_with_its_ids(self):
        self.write(("thread.plan", {"id": self.tid, "chars": 12}))
        events.append("project.root_set", {"id": 1, "root_path": "/x"}, project_id=self.thread["project"]["id"])
        rows = events.since(f"thread:{self.tid}", 0) + events.since(
            f"project:{self.thread['project']['id']}", 0
        )
        out = translate.translate(sorted({r["id"]: r for r in rows}.values(), key=lambda r: r["id"]))
        passed = {e["type"]: e["data"] for e in out if e["type"].startswith("harness.")}
        self.assertEqual(passed["harness.thread.plan"]["payload"], {"id": self.tid, "chars": 12})
        self.assertEqual(passed["harness.thread.plan"]["threadID"], self.tid)
        self.assertEqual(passed["harness.thread.plan"]["sessionID"], f"ses_{self.tid}")
        self.assertNotIn("sessionID", passed["harness.project.root_set"])
        self.assert_well_formed(out)

    def test_a_tool_result_carries_the_structured_result(self):
        self.turn(
            ("tool.call", {"id": "c1", "name": "list_runs", "arguments": {}}),
            ("tool.result", {"id": "c1", "name": "list_runs", "ok": True, "result": {"runs": [1, 2]}}),
        )
        out = self.replay()
        success = [e["data"] for e in out if e["type"] == "session.tool.success"][0]
        self.assertEqual(success["metadata"]["harness"]["result"], {"runs": [1, 2]})
        messages = self.assert_well_formed(out)
        state = messages[0]["content"][0]["state"]
        self.assertEqual(state["metadata"]["harness"]["tool"], "list_runs")

    def test_a_huge_result_is_said_to_be_omitted_not_cut_mid_structure(self):
        rows = [{"text": "x" * 1000} for _ in range(300)]
        self.turn(
            ("tool.call", {"id": "c1", "name": "preview_dataset_rows", "arguments": {}}),
            ("tool.result", {"id": "c1", "name": "preview_dataset_rows", "ok": True, "result": {"rows": rows}}),
        )
        success = [e["data"] for e in self.replay() if e["type"] == "session.tool.success"][0]
        harness = success["metadata"]["harness"]
        self.assertNotIn("result", harness)
        self.assertGreater(harness["resultOmitted"]["chars"], translate.MAX_RESULT_CHARS)
        self.assertIn("cut at", success["content"][0]["text"])


class ApprovalsAreTheirPermissionRequestsTest(TranslatorTestCase):
    def test_approval_required_asks_and_a_reply_is_answered(self):
        self.turn(
            ("tool.call", {"id": "c1", "name": "carve_rows", "arguments": {"path": "p"}}),
            (
                "tool.result",
                {
                    "id": "c1",
                    "name": "carve_rows",
                    "ok": False,
                    "result": {"ok": False, "error": "approval_required", "detail": "needs a click"},
                },
            ),
        )
        out = self.replay()
        asked = [e for e in out if e["type"] == "permission.asked"]
        self.assertEqual(len(asked), 1)
        request = asked[0]["data"]
        self.assertEqual(contract.errors(request, contract.component("Permission.Request")), [])
        self.assertEqual(translate.pending_approval(self.tid), request)
        self.write(
            (
                "tool.result",
                {
                    "id": "c1",
                    "name": "carve_rows",
                    "ok": False,
                    "result": {"ok": False, "error": "declined"},
                    "answers": request["id"],
                    "decision": "reject",
                },
            )
        )
        out = self.replay()
        self.assertEqual(self.types(out)[-1], "permission.replied")
        self.assertEqual(out[-1]["data"]["reply"], "reject")
        self.assertIsNone(translate.pending_approval(self.tid))
        self.assert_well_formed(out)

    def test_moving_the_ladder_is_their_agent_and_permissions_not_a_request(self):
        from app import main

        main.set_thread_mode_ep(self.tid, main.ThreadMode(mode="plan"))
        main.set_thread_mode_ep(self.tid, main.ThreadMode(mode="build"))
        main.set_thread_permission_ep(self.tid, main.ThreadPermission(mode="write"))
        main.set_thread_permission_ep(self.tid, main.ThreadPermission(mode="full"))
        out = self.replay()
        self.assertNotIn("permission.asked", self.types(out))
        agents = [e["data"]["agent"] for e in out if e["type"] == "session.agent.selected"]
        # `write` is a ladder step, not an agent (three agents since
        # 2026-09-22): moving onto it is still `session.permissions`, and the
        # agent stays `build` until the ladder reaches `full`.
        self.assertEqual(agents, ["plan", "build", "full"])
        self.assertIn("session.permissions", self.types(out))
        self.assert_well_formed(out)


class TheWholeLogReaderKeepsBothWallsTest(TranslatorTestCase):
    """`events.since_all` reads every scope at once, so it gets `since`'s walls.

    The stream is the first reader of the log that is not scoped to one thread.
    A reader that sees MORE of what models have said must not be the one that
    lets a measuring tool read it back (`tests/test_laundering_routes.py`,
    route 09), nor hand back a number unmarked.
    """

    def test_a_measuring_tool_is_refused(self):
        from app.tools import evidence

        holder = type("Holder", (), {"tool": "a_minting_tool"})()
        token = evidence._MINTING.set(holder)
        try:
            with self.assertRaises(evidence.MeasurementError):
                events.since_all(0)
        finally:
            evidence._MINTING.reset(token)

    def test_a_number_read_back_is_marked_as_a_claim(self):
        from app.tools import evidence

        self.write(("tool.call", {"id": "c", "name": "state_facts", "arguments": {"n": 1234}}))
        rows = [r for r in events.since_all(0) if r["kind"] == "tool.call"]
        self.assertTrue(evidence.is_caller_value(rows[-1]["payload"]["arguments"]["n"]))


class TheLiveStreamTest(TranslatorTestCase):
    """`stream.frames`, driven directly, bounded by `MAX_SECONDS`."""

    def setUp(self):
        super().setUp()
        for name, value in (("POLL_SECONDS", 0.01), ("MAX_SECONDS", 0.4)):
            patcher = mock.patch.object(stream, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def collect(self, during=None, last_event_id=None):
        async def run():
            frames = stream.frames(None, last_event_id)
            started = time.monotonic()
            first = await frames.__anext__()
            waited = time.monotonic() - started
            out = [first]
            if during is not None:
                during()
            async for item in frames:
                out.append(item)
            return waited, out

        return asyncio.run(run())

    def envelopes(self, frames):
        return [data_of(f) for f in frames if data_of(f) is not None]

    def test_the_first_frame_is_server_connected_and_it_is_fast(self):
        self.turn(("chat.delta", {"text": "old news"}))
        waited, frames = self.collect()
        first = data_of(frames[0])
        self.assertEqual(first["type"], "server.connected")
        self.assertEqual(contract.event_problems(first), [])
        self.assertLess(waited, 2.0, "their client aborts a connection that takes two seconds")
        # Live, not history: a finished turn before the stream opened is not resent.
        self.assertEqual([e["type"] for e in self.envelopes(frames)], ["server.connected"])

    def test_a_quiet_stream_still_sends_activity(self):
        with mock.patch.object(stream, "HEARTBEAT_SECONDS", 0.05):
            _waited, frames = self.collect()
        beats = [f for f in frames if f.startswith(":")]
        self.assertGreaterEqual(len(beats), 2, frames)
        self.assertTrue(all(data_of(beat) is None for beat in beats), "a heartbeat carries no event")

    def test_rows_written_while_it_listens_arrive_translated(self):
        _waited, frames = self.collect(
            during=lambda: self.turn(("chat.delta", {"text": "live"}))
        )
        envelopes = self.envelopes(frames)
        self.assertEqual(envelopes[0]["type"], "server.connected")
        self.assertIn("session.text.delta", [e["type"] for e in envelopes])
        self.assertEqual(envelopes[-1]["type"], "session.execution.succeeded")
        for envelope in envelopes:
            self.assertEqual(contract.event_problems(envelope), [])
        # The SSE `id:` line is the envelope's own id.
        framed = [f for f in frames if f.startswith("id: ")]
        self.assertEqual(framed[1].split("\n")[0][4:], envelopes[1]["id"])

    def test_a_stream_opened_mid_turn_continues_that_turn(self):
        self.write(("turn.started", {"provider": "Local", "model": "m"}), ("chat.delta", {"text": "before "}))
        _waited, frames = self.collect(
            during=lambda: self.write(("chat.delta", {"text": "after"}), ("stream.end", {"ending": "answered"}))
        )
        kinds = [e["type"] for e in self.envelopes(frames)]
        self.assertNotIn("session.step.started", kinds, "the step was already open")
        self.assertNotIn("session.text.started", kinds, "the text part was already open")
        ended = [e["data"] for e in self.envelopes(frames) if e["type"] == "session.text.ended"]
        self.assertEqual(ended[0]["text"], "before after")

    def test_a_changed_connection_tells_every_location_to_re_read_its_catalogs(self):
        from app.providers import store as provider_store

        def connect():
            row = provider_store.create("Local", "http://127.0.0.1:11434", "m", "ollama")
            provider_store.set_active(row["id"])

        with mock.patch.object(stream, "CATALOG_SECONDS", 0.05):
            _waited, frames = self.collect(during=connect)
        updates = [e for e in self.envelopes(frames) if e["type"] in stream.CATALOG_EVENTS]
        self.assertEqual(sorted({e["type"] for e in updates}), sorted(stream.CATALOG_EVENTS))
        project = self.thread["project"]
        from app.facade import sessions

        self.assertIn(
            {"directory": sessions.directory_of(project)}, [e["location"] for e in updates]
        )
        for envelope in updates:
            self.assertEqual(contract.event_problems(envelope), [])

    def test_last_event_id_resumes_inside_a_row(self):
        self.write(("turn.started", {"provider": "Local", "model": "m"}))
        start = events.last_event_id()
        replayed = translate.Translator(prime=True).feed(events.since(f"thread:{self.tid}", start - 1)[0])
        # Resume after the first of turn.started's two events.
        _waited, frames = self.collect(last_event_id=replayed[0]["id"])
        kinds = [e["type"] for e in self.envelopes(frames)]
        self.assertEqual(kinds, ["server.connected", "session.step.started"])


class TheStreamOverHTTPTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        patcher = mock.patch.object(stream, "MAX_SECONDS", 0.3)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_it_is_an_event_stream_behind_their_credential(self):
        from app.main import app

        token = base64.b64encode(f"opencode:{security.current_token()}".encode()).decode()
        with TestClient(app) as client:
            response = client.get("/oc/api/event", headers={"Authorization": f"Basic {token}"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/event-stream")
        first = data_of(response.text.split("\n\n")[0])
        self.assertEqual(first["type"], "server.connected")


if __name__ == "__main__":
    unittest.main()
