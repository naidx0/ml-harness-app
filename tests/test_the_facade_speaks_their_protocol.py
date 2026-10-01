"""The engine answers OpenCode's client in OpenCode's own shapes.

The desktop interface is now OpenCode's, and it talks to its server through a
generated client that trusts every response to match their OpenAPI document
(`app/facade/openapi.json` - upstream `anomalyco/opencode` at commit
`ad1a4a6`, MIT). `app/facade` speaks that protocol over this engine's threads,
turns and tools. These tests hold it to the document rather than to memory:
every implemented operation's response is validated against the schema that
operation declares, using `tests/openapi_contract.py`.

Four things are proved here:

1. **Every implemented operation answers in their schema**, including the
   transcript read after a real turn has run through the real conductor.
2. **Their composer's controls drive the harness's own settings**: an agent is
   the thread's plan/build mode and permission ladder, a model variant is the
   connection's effort, approving in their dock runs the held tool as the
   person, and an interrupt is the engine's stop.
3. **The surfaces this engine does not have are answered, not broken**: each is
   enumerated in `app/facade/answered.py`, reads return their empty shape with
   200 and actions return their declared 400 - never a 404 or a 500.
4. **Every operation their interface calls is either implemented or in that
   enumerated set**, so a panel cannot meet a 404 nobody decided on.
"""

from __future__ import annotations

import base64
import re
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app import db, events, security
from app.facade import answered, sessions, turns
from app.providers import Delta, ToolCall
from app.providers import store as provider_store

import openapi_contract as contract
import support

REPO = Path(__file__).resolve().parents[1]


def basic(token: str, user: str = "opencode") -> dict[str, str]:
    raw = base64.b64encode(f"{user}:{token}".encode()).decode()
    return {"Authorization": f"Basic {raw}"}


class ScriptedTurns:
    """A model that calls one lookup, then answers - a real two-round turn."""

    id = "scripted"
    locality = "local"

    def __init__(self) -> None:
        self.rounds = 0

    def stream(self, messages, tools=None, *, secret=None):
        self.rounds += 1
        if self.rounds == 1 and tools:
            yield Delta(
                kind="tool_call",
                tool_calls=(ToolCall(id="call-1", name="list_context", arguments={}),),
            )
            return
        yield Delta(kind="text", text="Here is ")
        yield Delta(kind="text", text="the answer.")

    def capabilities(self, *, secret=None):
        raise AssertionError("the loop must not probe mid-turn")


class FacadeTestCase(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        from app.main import app

        self.client = TestClient(app, headers=basic(security.current_token()))
        self.addCleanup(self.client.close)

    def connect(self, model=None, *, name="Local", effort=None):
        from app import conductor

        row = provider_store.create(name, "http://127.0.0.1:11434", "scripted-7b", "ollama")
        provider_store.set_active(row["id"])
        if effort:
            provider_store.update(row["id"], effort=effort)
        if model is not None:
            original = conductor.build
            conductor.build = lambda *a, **k: model
            self.addCleanup(setattr, conductor, "build", original)
        return provider_store.get(row["id"])

    def create(self, **body):
        response = self.client.post("/oc/api/session", json=body)
        return contract.assert_response(self, "session.create", response)["data"]

    def settle(self, session_id):
        thread_id = sessions.thread_id_of(session_id)
        self.assertTrue(turns.wait(thread_id, timeout=30), "the facade turn did not finish")
        return thread_id


class TheCatalogsAnswerInTheirSchemaTest(FacadeTestCase):
    def test_server_info(self):
        body = contract.assert_response(self, "server.info", self.client.get("/oc/api/info"))
        self.assertTrue(body["urls"][0].endswith("/oc"))

    def test_location_without_a_directory_is_the_default_workspace_and_it_exists(self):
        body = contract.assert_response(self, "location.get", self.client.get("/oc/api/location"))
        self.assertTrue(Path(body["directory"]).is_dir(), body)
        self.assertEqual(body["project"]["id"], f"prj_{db.default_project()['id']}")
        # Beside the sandbox's database, never in the checkout.
        self.assertIn(self.root, Path(body["directory"]).parents)

    def test_location_for_a_folder_nobody_has_opened_becomes_a_project(self):
        folder = self.root / "their-repo"
        folder.mkdir()
        response = self.client.get("/oc/api/location", params={"location[directory]": str(folder)})
        body = contract.assert_response(self, "location.get", response)
        self.assertEqual(Path(body["directory"]), folder)
        project = db.get_project(sessions.project_of(body["project"]["id"]))
        self.assertEqual(Path(project["root_path"]), folder)

    def test_projects_config_agents_models_providers(self):
        self.connect(effort="high")
        contract.assert_response(self, "project.list", self.client.get("/oc/api/project"))
        config = contract.assert_response(self, "config.get", self.client.get("/oc/api/config"))
        self.assertEqual(config[0]["info"]["default_agent"], "plan")
        self.assertEqual(config[0]["info"]["model"]["variant"], "high")
        agents = contract.assert_response(self, "agent.list", self.client.get("/oc/api/agent"))
        # THREE, since 2026-09-22 (Max: keep it simple). `measure` and `write`
        # are ladder steps reached through the engine's permission route only.
        self.assertEqual([a["id"] for a in agents["data"]], ["plan", "build", "full"])
        models = contract.assert_response(self, "model.list", self.client.get("/oc/api/model"))
        self.assertEqual(
            [v["id"] for v in models["data"][0]["variants"]], ["off", "low", "medium", "high"]
        )
        contract.assert_response(self, "model.default", self.client.get("/oc/api/model/default"))
        providers = contract.assert_response(self, "provider.list", self.client.get("/oc/api/provider"))
        self.assertEqual(providers["data"][0]["package"], "ollama")

    def test_a_connected_model_is_one_their_picker_shows(self):
        """Their picker (`providers/models/models.tsx`) shows a model unasked
        only if it was released within six months AND it is the newest of its
        family within its provider - so every model is released "now", and no
        two models share a `(provider, family)` group. Two connections to one
        remote server and two local models under the one `local-ollama`
        provider are the cases where a shared group would hide one."""
        import time

        self.connect()  # this machine's Ollama, model scripted-7b
        local = provider_store.create("Other", "http://127.0.0.1:11434", "qwen3:8b", "ollama")
        for name in ("Remote", "Remote again"):
            provider_store.create(name, "https://api.example.invalid/v1", "gpt-x", "openai-compatible")
        models = self.client.get("/oc/api/model").json()["data"]
        self.assertEqual(len(models), 4, models)
        six_months = 1000 * 60 * 60 * 24 * 180
        for model in models:
            with self.subTest(model=(model["providerID"], model["id"])):
                self.assertLess(abs(time.time() * 1000 - model["time"]["released"]), six_months)
        groups = [(m["providerID"], m["family"]) for m in models]
        self.assertEqual(len(set(groups)), len(groups), groups)
        self.assertIn(("local-ollama", local["model"]), groups)

    def test_no_model_connected_is_a_null_default_not_an_error(self):
        body = contract.assert_response(self, "model.default", self.client.get("/oc/api/model/default"))
        self.assertIsNone(body["data"])
        contract.assert_response(self, "model.list", self.client.get("/oc/api/model"))

    def test_a_key_never_reaches_the_catalog(self):
        """The keychain is never read on the way out - the row has no key and
        the answer has no field for one."""
        self.connect()
        for path in ("/oc/api/provider", "/oc/api/model", "/oc/api/config"):
            with self.subTest(path=path):
                text = self.client.get(path).text.lower()
                self.assertNotIn("api_key", text)
                self.assertNotIn("has_key", text)


class SessionsAreThreadsTest(FacadeTestCase):
    def test_their_minted_id_is_the_id_the_engine_answers_to(self):
        minted = "ses_0000c0ffee0000AbCdEfGhIjKl"
        created = self.create(id=minted, title="first")
        self.assertEqual(created["id"], minted)
        thread = events.get_thread(sessions.thread_id_of(minted))
        self.assertEqual(thread["title"], "first")
        # A new conversation opens where a person's always has: planning.
        self.assertEqual(thread["mode"], "plan")
        self.assertEqual(created["agent"], "plan")
        got = contract.assert_response(self, "session.get", self.client.get(f"/oc/api/session/{minted}"))
        self.assertEqual(got["data"]["id"], minted)
        # A minted id cannot be read back into a thread; the metadata says it.
        self.assertEqual(
            got["data"]["metadata"]["harness"],
            {"threadID": thread["id"], "projectID": thread["project_id"]},
        )
        # A retried create returns the same session rather than a second one.
        again = self.create(id=minted, title="first")
        self.assertEqual(again["id"], minted)
        self.assertEqual(len(events.list_threads()), 1)

    def test_threads_made_elsewhere_are_listed_under_their_own_ids(self):
        alice, bob = support.conversations(2)
        listed = contract.assert_response(self, "session.list", self.client.get("/oc/api/session"))
        ids = [s["id"] for s in listed["data"]]
        self.assertEqual(ids, [f"ses_{bob['id']}", f"ses_{alice['id']}"])

    def test_the_list_pages_and_filters_by_directory(self):
        for index in range(3):
            self.create(title=f"chat {index}")
        page = contract.assert_response(
            self, "session.list", self.client.get("/oc/api/session", params={"limit": "2"})
        )
        self.assertEqual([s["title"] for s in page["data"]], ["chat 2", "chat 1"])
        rest = contract.assert_response(
            self,
            "session.list",
            self.client.get("/oc/api/session", params={"limit": "2", "cursor": page["cursor"]["next"]}),
        )
        self.assertEqual([s["title"] for s in rest["data"]], ["chat 0"])
        self.assertIsNone(rest["cursor"]["next"])
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        self.create(title="over there", location={"directory": str(elsewhere)})
        filtered = contract.assert_response(
            self, "session.list", self.client.get("/oc/api/session", params={"directory": str(elsewhere)})
        )
        self.assertEqual([s["title"] for s in filtered["data"]], ["over there"])

    def listed_titles(self, **params):
        response = self.client.get("/oc/api/session", params=params)
        return [s["title"] for s in contract.assert_response(self, "session.list", response)["data"]]

    def test_a_parent_nobody_created_has_no_children(self):
        """An unknown `parentID` is an empty list, not every top-level chat.

        Their client mints a session id before the create lands and can ask
        for its children in between. `thread_id_of` answers `None` for it, and
        the filter read that as `subagent_of == None`, which is every thread
        that is nobody's sub-agent - so a new chat listed the whole rail as
        its children.
        """
        from app import subagents

        parent = self.create(title="parent")
        self.create(title="bystander")
        child = events.create_thread("child")
        subagents.ensure_table()
        with db.session() as connection:
            connection.execute(
                "INSERT INTO subagents(parent_thread_id, child_thread_id, phase, state) "
                "VALUES (?, ?, ?, ?)",
                (sessions.thread_id_of(parent["id"]), int(child["id"]), "phase", "running"),
            )
        # The positive control: a parent that exists lists exactly its child.
        self.assertEqual(self.listed_titles(parentID=parent["id"]), ["child"])
        self.assertEqual(
            self.listed_titles(parentID="ses_0000c0ffee0000NotYetMade00"), []
        )

    def test_a_chat_of_an_archived_project_leaves_the_list_with_its_project(self):
        """`/api/project` hides an archived project; the unscoped session list
        must hide its chats too, or their client invents a folder for each one
        beside the projects that exist (two strays on the owner's rail,
        2026-09-22). The chat is not deleted: unarchiving brings it back.
        """
        self.create(title="mine")  # first, so Default is the lowest project id
        old = db.create_project("old work")
        events.create_thread("in old work", project_id=int(old["id"]))
        self.assertEqual(sorted(self.listed_titles()), ["in old work", "mine"])
        db.archive_project(int(old["id"]))
        self.assertEqual(self.listed_titles(), ["mine"])
        listed_projects = self.client.get("/oc/api/project").json()
        self.assertNotIn(f"prj_{old['id']}", [p["id"] for p in listed_projects])

    def test_a_directory_no_project_owns_lists_nothing(self):
        """An unresolvable `directory` is an empty list, not every project-less thread."""
        self.create(title="mine")
        legacy = events.create_thread("from before projects")
        with db.session() as connection:
            connection.execute(
                "UPDATE threads SET project_id = NULL WHERE id = ?", (int(legacy["id"]),)
            )
        nowhere = self.root / "nobody-opened-this"
        nowhere.mkdir()
        self.assertEqual(self.listed_titles(directory=str(nowhere)), [])
        self.assertEqual(self.listed_titles(directory=str(self.root / "not-even-there")), [])
        # The `project` filter is the same shape: an id that is not one of ours.
        self.assertEqual(self.listed_titles(project="not-a-project-id"), [])

    def test_rename_and_delete_go_through_the_engine_doors(self):
        created = self.create(title="before")
        sid = created["id"]
        response = self.client.patch(f"/oc/api/session/{sid}", json={"title": "after"})
        contract.assert_response(self, "session.update", response, 204)
        thread_id = sessions.thread_id_of(sid)
        self.assertEqual(events.get_thread(thread_id)["title"], "after")
        self.assertIsNotNone(events.latest("thread.renamed", thread_id))
        response = self.client.delete(f"/oc/api/session/{sid}")
        contract.assert_response(self, "session.remove", response, 204)
        self.assertIsNone(events.get_thread(thread_id))
        missing = self.client.get(f"/oc/api/session/{sid}")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(contract.errors(missing.json(), contract.component("SessionNotFoundErrorEncoded")), [])

    def test_an_agent_is_the_mode_and_the_ladder(self):
        sid = self.create()["id"]
        thread_id = sessions.thread_id_of(sid)
        cases = {
            "build": ("build", "ask"),
            "full": ("build", "full"),
            "plan": ("plan", "ask"),
        }
        self.assertEqual(set(cases), set(sessions.AGENTS), "every agent the picker offers")
        for agent, (mode, permission) in cases.items():
            with self.subTest(agent=agent):
                response = self.client.post(f"/oc/api/session/{sid}/agent", json={"agent": agent})
                contract.assert_response(self, "session.switchAgent", response, 204)
                thread = events.get_thread(thread_id)
                self.assertEqual((thread["mode"], thread["permission"]), (mode, permission))
                info = self.client.get(f"/oc/api/session/{sid}").json()["data"]
                self.assertEqual(info["agent"], agent)
        for gone in ("measure", "write", "wizard"):
            with self.subTest(refused=gone):
                refused = self.client.post(f"/oc/api/session/{sid}/agent", json={"agent": gone})
                self.assertEqual(refused.status_code, 400)

    def test_a_middle_ladder_step_is_reached_by_the_engine_and_reads_as_build(self):
        """`measure` and `write` are not agents, and stay reachable through the
        engine's own permission route; a thread on either is `build` to their
        picker, so the name it shows is always one it offers."""
        from app import main

        sid = self.create()["id"]
        thread_id = sessions.thread_id_of(sid)
        for step in ("measure", "write"):
            with self.subTest(step=step):
                main.set_thread_mode_ep(thread_id, main.ThreadMode(mode="build"))
                main.set_thread_permission_ep(thread_id, main.ThreadPermission(mode=step))
                self.assertEqual(events.get_thread(thread_id)["permission"], step)
                info = self.client.get(f"/oc/api/session/{sid}").json()["data"]
                self.assertEqual(info["agent"], "build")
                self.assertIn(info["agent"], sessions.AGENTS)

    def test_a_ruleset_moves_the_ladder_to_a_step_that_covers_it(self):
        sid = self.create()["id"]
        thread_id = sessions.thread_id_of(sid)
        rules = [{"action": "carve_rows", "resource": "*", "effect": "allow"}]
        response = self.client.patch(f"/oc/api/session/{sid}", json={"permissions": rules})
        contract.assert_response(self, "session.update", response, 204)
        self.assertEqual(events.get_thread(thread_id)["permission"], "write")
        info = self.client.get(f"/oc/api/session/{sid}").json()["data"]
        self.assertIn(rules[0], info["permissions"])

    def test_a_variant_is_the_connections_effort(self):
        row = self.connect()
        sid = self.create()["id"]
        # `connect` is a connection to this machine's Ollama, which their
        # picker knows as `local-ollama` (`app/facade/catalog.py`).
        ref = {"id": row["model"], "providerID": "local-ollama", "variant": "low"}
        response = self.client.post(f"/oc/api/session/{sid}/model", json={"model": ref})
        contract.assert_response(self, "session.switchModel", response, 204)
        self.assertEqual(provider_store.get(row["id"])["effort"], "low")
        info = self.client.get(f"/oc/api/session/{sid}").json()["data"]
        self.assertEqual(info["model"], ref)
        # No variant is their "default", which is ours.
        del ref["variant"]
        self.client.post(f"/oc/api/session/{sid}/model", json={"model": ref})
        self.assertEqual(provider_store.get(row["id"])["effort"], "default")
        unknown = self.client.post(
            f"/oc/api/session/{sid}/model", json={"model": {"id": "x", "providerID": "conn-999"}}
        )
        self.assertEqual(unknown.status_code, 400)

    def test_active_inbox_and_an_idle_interrupt(self):
        sid = self.create()["id"]
        contract.assert_response(self, "session.active", self.client.get("/oc/api/session/active"))
        contract.assert_response(
            self, "session.inbox.list", self.client.get(f"/oc/api/session/{sid}/inbox")
        )
        response = self.client.post(f"/oc/api/session/{sid}/interrupt")
        body = contract.assert_response(self, "session.interrupt", response)
        self.assertEqual(body, {"interrupted": False})


class APromptRunsTheRealTurnTest(FacadeTestCase):
    def test_a_prompt_runs_a_turn_and_the_transcript_is_in_their_schema(self):
        self.connect(ScriptedTurns())
        sid = self.create(title="ask")["id"]
        minted = "msg_0000c0ffee00AbCdEfGhIjKlMn"
        response = self.client.post(
            f"/oc/api/session/{sid}/prompt", json={"id": minted, "text": "what is attached?"}
        )
        admitted = contract.assert_response(self, "session.prompt", response)["data"]
        self.assertEqual((admitted["id"], admitted["sessionID"]), (minted, sid))
        self.settle(sid)

        listed = contract.assert_response(
            self, "session.message.list", self.client.get(f"/oc/api/session/{sid}/message")
        )
        kinds = [m["type"] for m in listed["data"]]
        self.assertEqual(kinds, ["user", "assistant", "idle"], listed)
        user, reply, idle = listed["data"]
        self.assertEqual(user["id"], minted)
        self.assertEqual([p["type"] for p in reply["content"]][-1], "text")
        tools = [p for p in reply["content"] if p["type"] == "tool"]
        self.assertTrue(tools, reply)
        for part in tools:
            self.assertEqual(part["state"]["status"], "completed")
            harness = part["state"]["metadata"]["harness"]
            self.assertEqual((harness["tool"], harness["callID"]), (part["name"], part["id"]))
            self.assertIn("result", harness)
        self.assertEqual(reply["content"][1]["text"], "Here is the answer.")
        self.assertEqual(reply["finish"], "stop")
        self.assertEqual(reply["model"]["id"], "scripted-7b")
        self.assertEqual(idle["outcome"], "succeeded")

        one = self.client.get(f"/oc/api/session/{sid}/message/{reply['id']}")
        contract.assert_response(self, "session.message.get", one)
        newest = contract.assert_response(
            self,
            "session.message.list",
            self.client.get(f"/oc/api/session/{sid}/message", params={"limit": "1", "order": "desc"}),
        )
        self.assertEqual([m["type"] for m in newest["data"]], ["idle"])
        older = self.client.get(
            f"/oc/api/session/{sid}/message", params={"limit": "5", "cursor": newest["cursor"]["next"]}
        ).json()
        self.assertEqual([m["type"] for m in older["data"]], ["assistant", "user"])

    def test_stop_while_the_model_writes_ends_the_turn_and_the_composer_goes_idle(self):
        """Max, 2026-09-23: "the stop button doesn't seem to actually stop."

        Their Stop is `session.interrupt` with `resume=true`
        (`packages/app/src/session/composer/adapter.ts`). Pressed while the
        reply is arriving, it answers `interrupted: true`, the turn is over
        within the bound - not at a round boundary the model never reaches -
        the words already written stay, and the transcript ends in their
        `idle` item with outcome `interrupted`, which is what takes their
        composer out of its working state."""
        import threading
        import time

        from app import interrupt

        flowing = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)

        class Endless:
            id = "endless"
            locality = "local"

            def stream(self, messages, tools=None, *, secret=None):
                said = 0
                while not release.is_set():
                    said += 1
                    if said >= 3:
                        flowing.set()
                    yield Delta(kind="text", text="word ")
                    time.sleep(0.1)

            def capabilities(self, *, secret=None):
                raise AssertionError("the loop must not probe mid-turn")

        self.connect(Endless())
        sid = self.create(title="stop me")["id"]
        thread_id = sessions.thread_id_of(sid)
        self.addCleanup(interrupt.clear, thread_id)
        self.addCleanup(turns.wait, thread_id, 30)
        response = self.client.post(f"/oc/api/session/{sid}/prompt", json={"text": "write for ever"})
        contract.assert_response(self, "session.prompt", response)
        self.assertTrue(flowing.wait(30), "the model never started writing")

        pressed = time.monotonic()
        response = self.client.post(f"/oc/api/session/{sid}/interrupt", params={"resume": "true"})
        body = contract.assert_response(self, "session.interrupt", response)
        self.assertEqual(body, {"interrupted": True})
        self.assertTrue(
            turns.wait(thread_id, timeout=2.0),
            "the turn was still running 2 s after their Stop",
        )
        self.assertLess(time.monotonic() - pressed, 2.5)

        active = contract.assert_response(self, "session.active", self.client.get("/oc/api/session/active"))
        self.assertNotIn(sid, active["data"], "their session list still shows it working")
        listed = contract.assert_response(
            self, "session.message.list", self.client.get(f"/oc/api/session/{sid}/message")
        )
        kinds = [m["type"] for m in listed["data"]]
        self.assertEqual(kinds[-1], "idle", listed)
        self.assertEqual(listed["data"][-1]["outcome"], "interrupted")
        reply = [m for m in listed["data"] if m["type"] == "assistant"][-1]
        text = "".join(p.get("text", "") for p in reply["content"] if p["type"] == "text")
        self.assertIn("word word", text, "the words written before the stop were lost")

    def test_no_model_connected_is_an_error_card_in_the_conversation(self):
        sid = self.create()["id"]
        response = self.client.post(f"/oc/api/session/{sid}/prompt", json={"text": "hello"})
        contract.assert_response(self, "session.prompt", response)
        self.settle(sid)
        listed = contract.assert_response(
            self, "session.message.list", self.client.get(f"/oc/api/session/{sid}/message")
        )
        kinds = [m["type"] for m in listed["data"]]
        self.assertEqual(kinds, ["user", "assistant", "idle"])
        self.assertIn("No model is connected", listed["data"][1]["error"]["message"])
        self.assertEqual(listed["data"][2]["outcome"], "failed")

    def test_a_local_file_is_attached_through_the_harness_door(self):
        self.connect(ScriptedTurns())
        sid = self.create()["id"]
        data = self.root / "tickets.csv"
        data.write_text("id,text\n1,hello\n", encoding="utf-8")
        response = self.client.post(
            f"/oc/api/session/{sid}/prompt",
            json={"text": "count these", "files": [{"uri": data.as_uri(), "name": "tickets.csv"}]},
        )
        contract.assert_response(self, "session.prompt", response)
        thread_id = self.settle(sid)
        from app.tools import context

        context.ensure_contexts_table()
        paths = [Path(row["path"]) for row in context.list_contexts(thread_id)]
        self.assertIn(data, paths)


class TheApprovalDockIsTheEnginesApprovalTest(FacadeTestCase):
    """A gated tool that stopped to ask is their permission request."""

    def held(self, sid, tool="carve_rows"):
        thread_id = sessions.thread_id_of(sid)
        events.append("turn.started", {"provider": "Local", "model": "m"}, thread_id=thread_id)
        events.append(
            "tool.call", {"id": "c-1", "name": tool, "arguments": {"path": "x"}}, thread_id=thread_id
        )
        row = events.append(
            "tool.result",
            {
                "id": "c-1",
                "name": tool,
                "ok": False,
                "result": {"ok": False, "error": "approval_required", "detail": "needs a click"},
            },
            thread_id=thread_id,
        )
        events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)
        return thread_id, f"per_{row['id']}"

    def pending(self, sid):
        response = self.client.get(f"/oc/api/session/{sid}/permission")
        return contract.assert_response(self, "session.permission.list", response)["data"]

    def test_the_request_is_listed_and_a_rejection_clears_it(self):
        sid = self.create()["id"]
        thread_id, request = self.held(sid)
        listed = self.pending(sid)
        self.assertEqual([p["id"] for p in listed], [request])
        self.assertEqual(listed[0]["action"], "carve_rows")
        # Their auto-approve sweep asks per location; the same request is there.
        directory = self.client.get(f"/oc/api/session/{sid}").json()["data"]["location"]["directory"]
        swept = self.client.get("/oc/api/permission/request", params={"location[directory]": directory})
        body = contract.assert_response(self, "permission.request.list", swept)
        self.assertEqual([p["id"] for p in body["data"]], [request])
        response = self.client.post(
            f"/oc/api/session/{sid}/permission/{request}/reply", json={"decision": "reject"}
        )
        contract.assert_response(self, "session.permission.reply", response, 204)
        self.assertEqual(self.pending(sid), [])
        declined = events.latest("tool.result", thread_id)["payload"]
        self.assertEqual(declined["result"]["error"], "declined")

    def test_once_runs_the_tool_as_the_person(self):
        from app.tools import REGISTRY

        sid = self.create()["id"]
        thread_id, request = self.held(sid)
        with mock.patch.object(REGISTRY, "call", return_value={"ok": True, "wrote": 3}) as call:
            response = self.client.post(
                f"/oc/api/session/{sid}/permission/{request}/reply", json={"decision": "once"}
            )
        contract.assert_response(self, "session.permission.reply", response, 204)
        args, kwargs = call.call_args
        self.assertEqual(args[0], "carve_rows")
        self.assertTrue(kwargs["approved"])
        self.assertEqual(kwargs["actor"], "user")
        self.assertEqual(self.pending(sid), [])
        self.assertEqual(events.get_thread(thread_id)["permission"], "ask")

    def test_always_moves_the_ladder_to_the_step_that_covers_the_tool(self):
        from app.tools import REGISTRY

        sid = self.create()["id"]
        thread_id, request = self.held(sid)
        with mock.patch.object(REGISTRY, "call", return_value={"ok": True}):
            self.client.post(
                f"/oc/api/session/{sid}/permission/{request}/reply", json={"decision": "always"}
            )
        self.assertEqual(events.get_thread(thread_id)["permission"], "write")

    def test_a_request_that_is_not_pending_is_their_not_found(self):
        sid = self.create()["id"]
        response = self.client.post(
            f"/oc/api/session/{sid}/permission/per_99/reply", json={"decision": "once"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            contract.errors(response.json(), contract.component("PermissionNotFoundErrorEncoded")), []
        )


def _fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x1", path).replace("{path:path}", "a/b")


class TheSurfacesWeDoNotHaveAreAnsweredTest(FacadeTestCase):
    def test_every_answered_operation_is_theirs_at_their_path(self):
        for operation in answered.OPERATIONS:
            with self.subTest(operation=operation.operation_id):
                method, path, _body = contract.operation(operation.operation_id)
                self.assertEqual(method, operation.method)
                self.assertEqual(path.replace("*", "{path:path}"), operation.path)

    def test_reads_are_their_empty_shape_and_actions_their_declared_400(self):
        sid = self.create()["id"]
        for operation in answered.OPERATIONS:
            with self.subTest(operation=operation.operation_id):
                url = "/oc" + _fill(operation.path).replace("/session/x1", f"/session/{sid}")
                response = self.client.request(
                    operation.method, url, params={"projectID": "prj_1", "mode": "working"}, json={}
                )
                self.assertNotIn(response.status_code, (404, 500), response.text)
                if operation.kind == answered.READ:
                    body = contract.assert_response(self, operation.operation_id, response)
                    data = body.get("data", body) if isinstance(body, dict) else body
                    self.assertIn(data, ([], {"branch": {}}, {"resources": [], "templates": []}, None))
                else:
                    self.assertEqual(response.status_code, 400, response.text)
                    self.assertEqual(
                        contract.errors(response.json(), contract.component("InvalidRequestErrorEncoded")),
                        [],
                    )

    def test_nothing_is_both_implemented_and_answered(self):
        from app.facade import router as facade_router

        answered_paths = {(o.method, o.path) for o in answered.OPERATIONS}
        implemented = {
            (method, route.path[len(security.FACADE_PREFIX):])
            for route in facade_router.routes
            for method in route.methods
            if not route.name.startswith(tuple(o.operation_id for o in answered.OPERATIONS))
        }
        self.assertEqual(answered_paths & implemented, set())


#: What `createData` - their store, in `@opencode/client` 2.0.14's dist chunk
#: `pty-handoff-atpwm825.js` - calls on the client, read as `api().<name>(`.
#: The store is not in the vendored tree (it ships in the package), so its
#: calls are written down here; the interface's own calls are derived below.
STORE_CALLS = {
    "agent.list", "command.list", "config.get", "form.list", "integration.list",
    "location.get", "mcp.list", "mcp.resource.catalog", "message.list", "model.list",
    "permission.list", "permission.reply", "permission.saved.list", "project.list",
    "provider.list", "reference.list", "session.active", "session.compact",
    "session.create", "session.form.cancel", "session.form.list", "session.form.reply",
    "session.get", "session.inbox.list", "session.list", "session.message.get",
    "session.prompt", "session.switchModel", "shell.list", "skill.list", "vcs.get",
    "websearch.providers",
}

#: Their client's method names that are not their operation ids
#: (`promise/client.d.ts` against the OpenAPI document).
CLIENT_ALIASES = {
    "message.list": "session.message.list",
    "permission.list": "session.permission.list",
    "permission.reply": "session.permission.reply",
    "file.list": "fs.list",
    "file.read": "fs.read",
    "file.find": "fs.find",
    "mcp.connect": "experimental.mcp.connect",
    "mcp.disconnect": "experimental.mcp.disconnect",
    "config.update": "experimental.config.update",
}

_CALL = re.compile(r"\bapi(?:\(\))?\s*\.\s*([a-z][a-zA-Z]*(?:\s*\.\s*[a-zA-Z]+)*)\s*\(")


def interface_calls() -> set[str]:
    """Every `api.<name>(` their vendored interface makes, as operation ids."""
    ids = contract.operation_ids()
    namespaces = {op.split(".")[0] for op in ids} | {name.split(".")[0] for name in CLIENT_ALIASES}
    found: set[str] = set()
    roots = [REPO / "vendor" / "opencode" / "packages" / name / "src" for name in ("app", "session-ui")]
    for root in roots:
        for source in list(root.rglob("*.ts")) + list(root.rglob("*.tsx")):
            if ".test." in source.name:
                continue
            for match in _CALL.finditer(source.read_text(encoding="utf-8", errors="replace")):
                name = re.sub(r"\s+", "", match.group(1))
                if name.split(".")[0] not in namespaces or "." not in name:
                    continue
                found.add(CLIENT_ALIASES.get(name, name))
    return found


class EveryCallTheirInterfaceMakesIsDecidedTest(FacadeTestCase):
    def test_every_call_is_implemented_or_answered(self):
        derived = interface_calls()
        self.assertGreater(len(derived), 20, "the grep found almost nothing - is vendor/ there?")
        calls = derived | {CLIENT_ALIASES.get(name, name) for name in STORE_CALLS}
        ids = contract.operation_ids()
        self.assertEqual(sorted(calls - ids), [], "a call that names no operation of theirs")
        from app.facade import router as facade_router

        served = set()
        for route in facade_router.routes:
            path = route.path[len(security.FACADE_PREFIX):]
            for method in route.methods:
                served.add((method, path))
        missing = []
        for op in sorted(calls):
            method, path, _body = contract.operation(op)
            if (method, path.replace("*", "{path:path}")) not in served:
                missing.append(op)
        self.assertEqual(missing, [], "their interface calls these and the facade does not answer")


class TheFacadeCouldAlsoBeMountedAtTheRootTest(unittest.TestCase):
    """THEIR CLIENT DROPS THE `/oc` PREFIX, and this is the fallback kept open.

    Their generated client builds every URL as
    `new URL("/api/session", baseUrl)` - an absolute path - so a base URL of
    `http://127.0.0.1:8078/oc` resolves to `http://127.0.0.1:8078/api/session`.
    Until the desktop shell's `fetch` puts the prefix back, the only way their
    unmodified client reaches this facade is at the root. That is possible only
    while none of their paths is also one of the engine's own: they use
    singular nouns (`/api/project`, `/api/event`, `/api/provider`) where the
    engine uses plurals, and this asserts it stays that way.
    """

    def test_no_facade_path_is_an_engine_path(self):
        from app.facade import router as facade_router
        from app.main import app

        engine = set()
        for route in app.routes:
            path = getattr(route, "path", "")
            if path.startswith(security.FACADE_PREFIX + "/"):
                continue
            for method in getattr(route, "methods", None) or ():
                engine.add((method, path))
        facade_paths = set()
        for route in facade_router.routes:
            for method in route.methods:
                facade_paths.add((method, route.path[len(security.FACADE_PREFIX):]))
        self.assertEqual(sorted(engine & facade_paths), [])


class EveryPackageShipsTest(unittest.TestCase):
    """`pyproject.toml` LISTS its packages, so a new one must be listed.

    Found by this facade: `app/facade` is imported by `app.main`, and the list
    did not name it, so every test passed from the checkout while an installed
    copy could not have started. Derived from the tree, so the next package
    under `app/` is caught the day it is added.
    """

    def test_every_package_under_app_is_declared(self):
        import tomllib

        declared = set(
            tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"][
                "packages"
            ]
        )
        found = {
            ".".join(init.parent.relative_to(REPO).parts)
            for init in (REPO / "app").rglob("__init__.py")
            if "__pycache__" not in init.parts and "_bundled" not in init.parts
        }
        self.assertIn("app.facade", found, "the derivation found nothing it should have")
        self.assertEqual(sorted(found - declared), [])


class TheFacadeIsBehindTheTokenTest(FacadeTestCase):
    def test_no_token_is_their_unauthorized(self):
        from app.main import app

        with TestClient(app) as stranger:
            for path in ("/oc/api/info", "/oc/api/session", "/oc/api/event"):
                with self.subTest(path=path):
                    response = stranger.get(path)
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(
                        contract.errors(response.json(), contract.component("UnauthorizedErrorEncoded")),
                        [],
                    )

    def test_their_basic_credential_is_accepted_and_a_wrong_user_is_not(self):
        from app.main import app

        token = security.current_token()
        with TestClient(app) as client:
            self.assertEqual(client.get("/oc/api/info", headers=basic(token)).status_code, 200)
            self.assertEqual(
                client.get("/oc/api/info", headers={"Authorization": f"Bearer {token}"}).status_code, 200
            )
            self.assertEqual(client.get("/oc/api/info", headers=basic(token, "admin")).status_code, 401)
            self.assertEqual(client.get("/oc/api/info", headers=basic("wrong")).status_code, 401)


if __name__ == "__main__":
    unittest.main()
