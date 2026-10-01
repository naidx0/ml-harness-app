"""`/goal` and compaction, through their command and compact operations.

`command.list` offers the one slash command the engine runs; every other one
stays on their side. `session.command` with `goal` runs the turn the old
composer's "may edit goal/todo" box ran - `invite_goal_edit`, the engine's own
turn option - and asks the interface to open the Plan pane with a
`harness.ui.open` event. `session.compact` is the engine's compaction.
"""

from __future__ import annotations

import unittest
from unittest import mock

from app import events
from app.facade import sessions, translate, turns

import openapi_contract as contract
from test_the_facade_speaks_their_protocol import FacadeTestCase


class GoalIsAServerCommandTest(FacadeTestCase):
    def setUp(self):
        super().setUp()
        from app import conductor

        self.runs: list[dict] = []

        def run_turn(thread_id, **options):
            self.runs.append({"thread_id": thread_id, **options})
            return iter(())

        patcher = mock.patch.object(conductor, "run_turn", side_effect=run_turn)
        patcher.start()
        self.addCleanup(patcher.stop)

    def opened(self, thread_id):
        stream = translate.translate(events.since(f"thread:{thread_id}", 0, limit=1000))
        return [e for e in stream if e["type"] == "harness.ui.open"]

    def test_the_list_offers_goal_and_only_goal(self):
        body = contract.assert_response(self, "command.list", self.client.get("/oc/api/command"))
        self.assertEqual([c["name"] for c in body["data"]], ["goal"])

    def test_goal_with_text_admits_it_runs_an_invited_turn_and_opens_the_plan(self):
        sid = self.create()["id"]
        response = self.client.post(
            f"/oc/api/session/{sid}/command", json={"name": "goal", "text": "classify the tickets"}
        )
        contract.assert_response(self, "session.command", response, 204)
        thread_id = self.settle(sid)
        self.assertEqual(self.runs, [{"thread_id": thread_id, "invite_goal_edit": True}])
        user = [m for m in events.messages_for(thread_id) if m["role"] == "user"]
        self.assertEqual([m["content"] for m in user], ["classify the tickets"])
        (opened,) = self.opened(thread_id)
        self.assertEqual(opened["data"], {"tab": "plan", "sessionID": sid, "threadID": thread_id})
        self.assertEqual(contract.event_problems(opened), [])

    def test_goal_alone_opens_the_plan_and_runs_nothing(self):
        sid = self.create()["id"]
        response = self.client.post(f"/oc/api/session/{sid}/command", json={"name": "goal", "text": " "})
        contract.assert_response(self, "session.command", response, 204)
        thread_id = sessions.thread_id_of(sid)
        self.assertTrue(turns.wait(thread_id, timeout=5))
        self.assertEqual(self.runs, [])
        self.assertEqual(events.messages_for(thread_id), [])
        self.assertEqual(len(self.opened(thread_id)), 1)

    def test_a_plain_prompt_is_not_invited(self):
        sid = self.create()["id"]
        self.client.post(f"/oc/api/session/{sid}/prompt", json={"text": "hello"})
        thread_id = self.settle(sid)
        self.assertEqual(self.runs, [{"thread_id": thread_id}])

    def test_an_unknown_command_is_their_not_found(self):
        sid = self.create()["id"]
        response = self.client.post(f"/oc/api/session/{sid}/command", json={"name": "plan", "text": "x"})
        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertEqual(contract.errors(body, contract.component("CommandNotFoundErrorEncoded")), [])
        self.assertEqual(body["command"], "plan")


class CompactIsTheEnginesCompactionTest(FacadeTestCase):
    def test_a_compaction_is_their_compaction_item(self):
        from app import main

        sid = self.create()["id"]
        outcome = {"ok": True, "summary": "the earlier turns, briefly", "removed": 12}
        with mock.patch.object(main, "compact_thread_ep", return_value=outcome) as compact:
            response = self.client.post(f"/oc/api/session/{sid}/compact", json={})
        body = contract.assert_response(self, "session.compact", response)["data"]
        compact.assert_called_once_with(sessions.thread_id_of(sid))
        self.assertEqual((body["type"], body["sessionID"], body["payload"]), ("compaction", sid, outcome))

    def test_no_model_is_their_400_with_the_engines_sentence(self):
        sid = self.create()["id"]
        response = self.client.post(f"/oc/api/session/{sid}/compact", json={})
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(contract.errors(body, contract.component("InvalidRequestErrorEncoded")), [])
        self.assertIn("connect a model first", body["message"])

    def test_a_running_reply_is_their_conflict(self):
        sid = self.create()["id"]
        with mock.patch.object(turns, "busy", return_value=True):
            response = self.client.post(f"/oc/api/session/{sid}/compact", json={})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(contract.errors(response.json(), contract.component("ConflictErrorEncoded")), [])


if __name__ == "__main__":
    unittest.main()
