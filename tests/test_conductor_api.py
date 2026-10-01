"""The Conductor's HTTP surface: threads, the replayable stream, controls.

The stream is the half worth being careful about. `Last-Event-ID` is what the
browser sends on reconnect without being asked, and it has to beat the `since`
query parameter, because `since` is what the client assembled from memory
before it dropped and `Last-Event-ID` is what it actually received.
"""

from __future__ import annotations

import json
import unittest

from app import events
from app.providers import store as provider_store

import support


def frames(body: str) -> list[dict]:
    """Parse an SSE body into `{id, event, data}` dicts, ignoring comments."""
    out = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        frame = {}
        for line in block.splitlines():
            if line.startswith("id: "):
                frame["id"] = int(line[4:])
            elif line.startswith("event: "):
                frame["event"] = line[7:]
            elif line.startswith("data: "):
                frame["data"] = json.loads(line[6:])
        if frame:
            out.append(frame)
    return out


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        from app.main import app

        self.app = app
        self.client = support.api_client(app)
        self.addCleanup(self.client.close)


class ThreadRoutesTest(ApiTestCase):
    def test_a_thread_holds_a_conversation(self):
        created = self.client.post("/api/threads", json={"title": "t"})
        self.assertEqual(created.status_code, 201)
        thread_id = created.json()["id"]

        posted = self.client.post(
            f"/api/threads/{thread_id}/messages", json={"content": "hello"}
        )
        self.assertEqual(posted.status_code, 201)
        self.assertEqual(posted.json()["role"], "user")

        fetched = self.client.get(f"/api/threads/{thread_id}").json()
        self.assertEqual(len(fetched["messages"]), 1)
        self.assertEqual(fetched["thread"]["title"], "t")
        self.assertEqual(len(self.client.get("/api/threads").json()), 1)

    def test_a_client_cannot_choose_the_role(self):
        """A client that could send `system` could rewrite the instruction set."""
        thread_id = self.client.post("/api/threads", json={"title": "t"}).json()["id"]
        posted = self.client.post(
            f"/api/threads/{thread_id}/messages",
            json={"content": "hi", "role": "system"},
        )
        self.assertEqual(posted.status_code, 201)
        self.assertEqual(posted.json()["role"], "user")
        roles = [
            m["role"] for m in self.client.get(f"/api/threads/{thread_id}").json()["messages"]
        ]
        self.assertEqual(roles, ["user"])

    def test_a_missing_thread_404s_rather_than_500s(self):
        self.assertEqual(self.client.get("/api/threads/99999").status_code, 404)
        self.assertEqual(
            self.client.post(
                "/api/threads/99999/messages", json={"content": "x"}
            ).status_code,
            404,
        )

    def test_a_turn_with_no_provider_is_a_409_that_explains_itself(self):
        thread_id = self.client.post("/api/threads", json={"title": "t"}).json()["id"]
        response = self.client.post(f"/api/threads/{thread_id}/turn")
        self.assertEqual(response.status_code, 409)
        self.assertIn("also a button", response.json()["detail"])


class EventStreamTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.thread = events.create_thread("t")
        self.scope = f"thread:{self.thread['id']}"

    def test_every_frame_carries_its_durable_id(self):
        events.append("chat.delta", {"text": "one"}, thread_id=self.thread["id"])
        end = events.append(events.END_KIND, {}, thread_id=self.thread["id"])

        body = self.client.get(f"/api/events?scope={self.scope}&since=0").text
        parsed = frames(body)
        self.assertEqual([f["event"] for f in parsed], ["chat.delta", events.END_KIND])
        self.assertEqual(parsed[0]["data"], {"text": "one"})
        self.assertEqual(parsed[-1]["id"], end["id"])

    def test_since_replays_only_what_the_client_has_not_seen(self):
        first = events.append("chat.delta", {"text": "one"}, thread_id=self.thread["id"])
        events.append("chat.delta", {"text": "two"}, thread_id=self.thread["id"])
        events.append(events.END_KIND, {}, thread_id=self.thread["id"])

        body = self.client.get(f"/api/events?scope={self.scope}&since={first['id']}").text
        self.assertNotIn('"one"', body)
        self.assertIn('"two"', body)

    def test_last_event_id_beats_the_since_parameter(self):
        """The browser's own header describes what actually arrived."""
        first = events.append("chat.delta", {"text": "one"}, thread_id=self.thread["id"])
        events.append("chat.delta", {"text": "two"}, thread_id=self.thread["id"])
        events.append(events.END_KIND, {}, thread_id=self.thread["id"])

        body = self.client.get(
            f"/api/events?scope={self.scope}&since=0",
            headers={"Last-Event-ID": str(first["id"])},
        ).text
        self.assertNotIn('"one"', body)
        self.assertIn('"two"', body)

    def test_a_nonsense_last_event_id_falls_back_rather_than_crashing(self):
        events.append("chat.delta", {"text": "one"}, thread_id=self.thread["id"])
        events.append(events.END_KIND, {}, thread_id=self.thread["id"])
        response = self.client.get(
            f"/api/events?scope={self.scope}&since=0",
            headers={"Last-Event-ID": "not-a-number"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('"one"', response.text)

    def test_an_unknown_scope_is_a_400(self):
        self.assertEqual(
            self.client.get("/api/events?scope=dataset:1").status_code, 400
        )
        self.assertEqual(self.client.get("/api/events?scope=nonsense").status_code, 400)

    def test_a_stream_with_nothing_in_it_returns_rather_than_hanging(self):
        response = self.client.get(f"/api/events?scope={self.scope}&follow=false")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(frames(response.text), [])

    def test_a_history_read_returns_the_whole_thread_not_its_first_page(self):
        """`follow=false` is a history read, and history is every row.

        It read one page of 500 and returned. Every token delta is a row, so a
        thread with a few turns ran past 500 and the client lost its later
        turns without a word. The first page here ENDS on a replayed
        `stream.end`, which is the second way the old read stopped early.
        """
        thread_id = self.thread["id"]
        for index in range(499):
            events.append("chat.delta", {"text": "a"}, thread_id=thread_id)
        events.append(events.END_KIND, {}, thread_id=thread_id)
        for index in range(120):
            events.append("chat.delta", {"text": "b"}, thread_id=thread_id)
        events.append(events.END_KIND, {}, thread_id=thread_id)
        last = events.append(
            "turn.effects", {"marker": "the-last-word"}, thread_id=thread_id
        )

        response = self.client.get(
            f"/api/events?scope={self.scope}&since=0&follow=false"
        )
        self.assertEqual(response.status_code, 200)
        parsed = frames(response.text)
        ids = [f["id"] for f in parsed]
        self.assertEqual(ids, sorted(set(ids)), "ids repeat or run backwards")
        self.assertEqual(parsed[-1]["id"], last["id"])
        self.assertEqual(parsed[-1]["data"], {"marker": "the-last-word"})
        text = "".join(
            f["data"].get("text", "") for f in parsed if f["event"] == "chat.delta"
        )
        self.assertEqual(text, "a" * 499 + "b" * 120)
        self.assertEqual(
            [f["event"] for f in parsed],
            ["chat.delta", events.END_KIND, "chat.delta", events.END_KIND, "turn.effects"],
        )

    def test_a_history_read_folds_a_reply_that_spans_a_page_boundary(self):
        """A run of deltas cut by the page edge is still one replayed row."""
        thread_id = self.thread["id"]
        for index in range(650):
            events.append("chat.delta", {"text": "x"}, thread_id=thread_id)
        end = events.append(events.END_KIND, {}, thread_id=thread_id)

        parsed = frames(
            self.client.get(f"/api/events?scope={self.scope}&follow=false").text
        )
        self.assertEqual([f["event"] for f in parsed], ["chat.delta", events.END_KIND])
        self.assertEqual(parsed[0]["data"]["text"], "x" * 650)
        self.assertEqual(parsed[-1]["id"], end["id"])

    def test_the_response_is_an_event_stream_that_proxies_will_not_buffer(self):
        events.append(events.END_KIND, {}, thread_id=self.thread["id"])
        response = self.client.get(f"/api/events?scope={self.scope}")
        self.assertTrue(
            response.headers["content-type"].startswith("text/event-stream")
        )
        self.assertEqual(response.headers["cache-control"], "no-cache")
        self.assertEqual(response.headers["x-accel-buffering"], "no")


class ProviderRoutesTest(ApiTestCase):
    def test_a_connection_is_created_classified_and_activated(self):
        created = self.client.post(
            "/api/providers",
            json={
                "name": "Ollama",
                "base_url": "http://127.0.0.1:11434",
                "model": "granite4-hermes:latest",
                "adapter": "ollama",
            },
        )
        self.assertEqual(created.status_code, 201)
        row = created.json()
        self.assertEqual(row["kind"], "local")
        self.assertEqual(row["tool_calling"], "unknown")
        self.assertFalse(row["has_key"])

        activated = self.client.post(f"/api/providers/{row['id']}/activate")
        self.assertEqual(activated.status_code, 200)
        self.assertEqual(provider_store.active()["id"], row["id"])

    def test_activating_one_connection_deactivates_the_rest(self):
        first = provider_store.create("a", "http://127.0.0.1:11434", "m", "ollama")
        second = provider_store.create("b", "https://api.example.com/v1", "m", "openai-compatible")
        self.client.post(f"/api/providers/{first['id']}/activate")
        self.client.post(f"/api/providers/{second['id']}/activate")
        active = [r for r in provider_store.list_all() if r["is_active"]]
        self.assertEqual([r["id"] for r in active], [second["id"]])

    def test_an_unknown_adapter_is_a_422_not_a_500(self):
        response = self.client.post(
            "/api/providers",
            json={
                "name": "x",
                "base_url": "https://api.anthropic.com",
                "model": "m",
                "adapter": "anthropic",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_a_missing_provider_404s(self):
        self.assertEqual(
            self.client.post("/api/providers/99999/activate").status_code, 404
        )
        self.assertEqual(
            self.client.post("/api/providers/99999/probe").status_code, 404
        )

    def test_the_presets_are_offered_with_their_locality_implied(self):
        presets = self.client.get("/api/provider_presets").json()
        self.assertGreaterEqual(len(presets), 5)
        self.assertIn("Ollama", {p["name"] for p in presets})


class ControlsTest(ApiTestCase):
    """Every tool is also a control - over HTTP, not only in Python."""

    def test_the_controls_route_describes_every_tool(self):
        payload = self.client.get("/api/tools").json()
        names = {c["name"] for c in payload["controls"]}
        self.assertIn("inspect_hardware", names)
        self.assertIn("run_diagnosis", names)
        self.assertIn("list_runs", names)
        self.assertTrue(payload["instruction_set"])

    def test_a_control_runs_the_same_tool_a_model_would_call(self):
        response = self.client.post("/api/tools/list_runs", json={"arguments": {}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["count"], 0)

    def test_a_control_needs_no_body(self):
        self.assertEqual(
            self.client.post("/api/tools/inspect_hardware").status_code, 200
        )

    def test_an_unknown_control_404s(self):
        self.assertEqual(self.client.post("/api/tools/not_a_tool").status_code, 404)

    def test_a_control_cannot_set_a_gate_outcome(self):
        """The hard rule, reachable over HTTP.

        Arguments outside a tool's schema are dropped, and the drop is
        reported, so a caller who tries to post a verdict gets told it was
        ignored rather than quietly getting away with it.

        A RESERVED name is reported separately from an invented one, and this
        test was rewritten when that split arrived. "You tried to hand me a
        verdict" and "you invented a parameter" used to come back in the same
        list, which made the interesting event indistinguishable from a typo in
        the transcript. `refused_arguments` is the louder half.
        """
        response = self.client.post(
            "/api/tools/run_diagnosis",
            json={"arguments": {"facts": {}, "verdict": "TRAIN", "wobble": 1}},
        )
        result = response.json()["result"]
        self.assertEqual(result["refused_arguments"], ["verdict"])
        self.assertEqual(result["ignored_arguments"], ["wobble"])
        self.assertTrue(result["refused_because"])
        self.assertNotEqual(result["verdict"], "TRAIN")
        self.assertEqual(result["decided_by"], "app/diagnosis.py")

    def test_a_control_is_the_user_speaking_and_a_tool_call_is_not(self):
        """The actor, over HTTP, on the route that is the person's own door.

        `POST /api/tools/{name}` is a person pressing a button in their own
        application, so what they supply is STATED. There is no field in the
        request body that could have said so and there must never be one - the
        route hard-codes it exactly as `POST .../messages` hard-codes the role.
        """
        response = self.client.post(
            "/api/tools/run_diagnosis", json={"arguments": {"facts": {}}}
        )
        self.assertEqual(response.json()["result"]["your_facts_were_recorded_as"], "STATED")

        # And a body that tries to claim the origin cannot: `actor` is not a
        # schema property of any tool, so it never reaches the handler.
        claimed = self.client.post(
            "/api/tools/run_diagnosis",
            json={"arguments": {"facts": {}, "actor": "user", "origin": "MEASURED"}},
        )
        result = claimed.json()["result"]
        self.assertEqual(result["refused_arguments"], ["actor", "origin"])


class TokenBoundaryTest(ApiTestCase):
    """The Conductor's routes inherit the existing boundary. Verify, do not assume."""

    def test_every_conductor_route_refuses_an_unauthenticated_caller(self):
        from fastapi.testclient import TestClient

        anonymous = TestClient(self.app)
        self.addCleanup(anonymous.close)
        for method, path in (
            ("get", "/api/threads"),
            ("get", "/api/tools"),
            ("get", "/api/providers"),
            ("get", "/api/events?scope=thread:1"),
            ("post", "/api/threads"),
            ("post", "/api/tools/list_runs"),
            ("post", "/api/threads/1/turn"),
        ):
            with self.subTest(route=path):
                response = getattr(anonymous, method)(path)
                self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
