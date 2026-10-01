"""Stop the turn that is running, at the next round boundary and never inside a tool.

Max, 2026-09-19, watching a turn spend 49 seconds while the composer told him
his next message would be queued until it finished. `app/interrupt.py` says
why the boundary is where it is. Pinned here:

- a stop asked for before the turn starts ends it without asking the model
  for a single round;
- a stop asked for mid-turn lets the tool that is running finish and be
  recorded, and no further round is asked for;
- a stop asked for while the model is writing ends that call and starts none
  of the tools it asked for (2026-09-23; the timing is pinned in
  `test_a_stop_ends_the_model_call.py`);
- the turn ends `stopped_by_the_person`, which is not `round_cap` and not
  `answered`, and there is no closing model round;
- the flag never outlives its turn.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402,F401
from app import conductor, events, interrupt  # noqa: E402
from app.providers import Delta, ToolCall  # noqa: E402
from test_a_turn_always_speaks import ScriptedProvider, TurnTestCase, says  # noqa: E402


def _calls(n: int) -> list[list[Delta]]:
    return [
        [Delta(kind="tool_call", tool_calls=(ToolCall(f"s{i}", "list_runs", {"limit": i + 1}),))]
        for i in range(n)
    ]


class _StoppingProvider(ScriptedProvider):
    """Presses stop from inside round `at`, the way a person does mid-turn."""

    def __init__(self, scripts, *, thread_id: int, at: int):
        super().__init__(scripts)
        self.thread_id = thread_id
        self.at = at

    def stream(self, messages, tools=None, *, secret=None):
        if self.rounds + 1 == self.at:
            interrupt.ask_to_stop(self.thread_id)
        yield from super().stream(messages, tools, secret=secret)


class AStopEndsTheTurnTest(TurnTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(lambda: [interrupt.clear(t) for t in interrupt.waiting()])

    def test_a_stop_before_the_turn_spends_no_round_at_all(self):
        self.connect()
        thread_id = self.new_thread()
        provider = ScriptedProvider(_calls(4) + [says("done")])
        self.install(provider)
        interrupt.ask_to_stop(thread_id)
        rows = list(conductor.run_turn(thread_id, max_tool_rounds=8))
        self.assertEqual(provider.rounds, 0, "the model was asked for a round after a stop")
        self.assertEqual([r for r in rows if r["kind"] == "tool.call"], [])
        end = [r for r in rows if r["kind"] == "stream.end"][-1]
        self.assertEqual(end["payload"]["ending"], interrupt.ENDING)

    def test_a_stop_mid_turn_finishes_the_running_tool_and_asks_for_no_more(self):
        """THE PRESS LANDS INSIDE THE SECOND TOOL, and it used to land inside the
        second MODEL CALL. Rewritten 2026-09-23 with every assertion kept: a stop
        in a model call now ends that call and runs none of its tools
        (`test_a_stop_in_a_model_call_runs_none_of_its_tools` below,
        `tests/test_a_stop_ends_the_model_call.py`), so the specimen for "the
        running tool finishes" has to be a press made while a tool runs."""
        self.connect()
        thread_id = self.new_thread()
        provider = ScriptedProvider(_calls(6) + [says("done")])
        self.install(provider)
        original = conductor.REGISTRY.call
        ran: list[str] = []

        def pressing_inside_the_second_tool(name, *args, **kwargs):
            if name == "list_runs":
                ran.append(name)
                if len(ran) == 2:
                    interrupt.ask_to_stop(thread_id)
            return original(name, *args, **kwargs)

        with mock.patch.object(conductor.REGISTRY, "call", side_effect=pressing_inside_the_second_tool):
            rows = list(conductor.run_turn(thread_id, max_tool_rounds=8))

        self.assertEqual(provider.rounds, 2, "a round was asked for after the stop")
        calls = [r for r in rows if r["kind"] == "tool.call"]
        results = [r for r in rows if r["kind"] == "tool.result"]
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            len(results), len(calls),
            "a tool that started was not recorded - the stop landed inside it",
        )
        end = [r for r in rows if r["kind"] == "stream.end"][-1]
        self.assertEqual(end["payload"]["ending"], interrupt.ENDING)

    def test_a_stop_in_a_model_call_runs_none_of_its_tools(self):
        """Pressed while round 2's reply is arriving: round 1's tool ran and is
        recorded, round 2's tool never starts, and no third round is asked for."""
        self.connect()
        thread_id = self.new_thread()
        provider = _StoppingProvider(_calls(6) + [says("done")], thread_id=thread_id, at=2)
        self.install(provider)
        rows = list(conductor.run_turn(thread_id, max_tool_rounds=8))

        self.assertEqual(provider.rounds, 2, "a round was asked for after the stop")
        calls = [r for r in rows if r["kind"] == "tool.call"]
        results = [r for r in rows if r["kind"] == "tool.result"]
        self.assertEqual(len(calls), 1, "a tool the stopped reply asked for was started")
        self.assertEqual(len(results), len(calls))
        end = [r for r in rows if r["kind"] == "stream.end"][-1]
        self.assertEqual(end["payload"]["ending"], interrupt.ENDING)

    def test_the_transcript_says_a_person_stopped_it(self):
        self.connect()
        thread_id = self.new_thread()
        self.install(_StoppingProvider(_calls(4) + [says("done")], thread_id=thread_id, at=1))
        rows = list(conductor.run_turn(thread_id, max_tool_rounds=8))
        notices = [
            r["payload"] for r in rows
            if r["kind"] == "conductor.notice" and r["payload"].get("reason") == interrupt.ENDING
        ]
        self.assertEqual(len(notices), 1)
        self.assertIn("after_rounds", notices[0])

    def test_it_is_not_a_round_cap_and_not_an_answer(self):
        """A person deciding they have seen enough is not a budget running out.
        A score row that read the two as one would call a deliberate stop a stall."""
        self.assertNotIn(interrupt.ENDING, conductor.FORCED_ANSWER)
        self.assertNotEqual(interrupt.ENDING, "round_cap")
        self.assertNotEqual(interrupt.ENDING, "answered")

    def test_the_flag_never_outlives_its_turn(self):
        self.connect()
        thread_id = self.new_thread()
        self.install(ScriptedProvider([says("first")]))
        interrupt.ask_to_stop(thread_id)
        list(conductor.run_turn(thread_id, max_tool_rounds=8))
        self.assertFalse(interrupt.was_asked(thread_id))

        events.add_message(thread_id, "user", "again")
        second = ScriptedProvider(_calls(2) + [says("second")])
        self.install(second)
        rows = list(conductor.run_turn(thread_id, max_tool_rounds=8))
        end = [r for r in rows if r["kind"] == "stream.end"][-1]
        self.assertNotEqual(
            end["payload"]["ending"], interrupt.ENDING,
            "a stale stop ended the next turn",
        )
        self.assertGreater(second.rounds, 0)

    def test_one_thread_s_stop_does_not_touch_another(self):
        self.connect()
        mine = self.new_thread()
        theirs = self.new_thread()
        interrupt.ask_to_stop(mine)
        self.assertTrue(interrupt.was_asked(mine))
        self.assertFalse(interrupt.was_asked(theirs))
        provider = ScriptedProvider(_calls(2) + [says("done")])
        self.install(provider)
        rows = list(conductor.run_turn(theirs, max_tool_rounds=8))
        end = [r for r in rows if r["kind"] == "stream.end"][-1]
        self.assertNotEqual(end["payload"]["ending"], interrupt.ENDING)


class TheDoorIsOnTheApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)

    def test_stopping_an_unknown_thread_is_a_404_not_a_crash(self):
        from app.main import app
        client = support.api_client(app)
        answer = client.post("/api/threads/99999/turn/stop")
        self.assertEqual(answer.status_code, 404)

    def test_stopping_an_idle_thread_sets_no_flag_to_go_stale(self):
        """The press is recorded and nothing is armed. A flag set on an idle
        thread is the stale flag that would kill the person's NEXT turn."""
        from app.main import app
        client = support.api_client(app)
        made = client.post("/api/threads", json={"title": "idle"})
        thread_id = made.json()["id"]
        self.addCleanup(interrupt.clear, thread_id)
        answer = client.post(f"/api/threads/{thread_id}/turn/stop")
        self.assertEqual(answer.status_code, 200)
        self.assertTrue(answer.json()["ok"])
        self.assertFalse(answer.json()["a_turn_was_running"])
        self.assertFalse(interrupt.was_asked(thread_id))
        kinds = [row["kind"] for row in events.since(f"thread:{thread_id}")]
        self.assertIn("turn.stop_asked", kinds)

    def test_stopping_a_thread_mid_turn_arms_the_flag(self):
        from app.main import app
        client = support.api_client(app)
        made = client.post("/api/threads", json={"title": "busy"})
        thread_id = made.json()["id"]
        self.addCleanup(interrupt.clear, thread_id)
        # What a turn in flight looks like on the log: a start with no end.
        events.append("turn.started", {"thread_id": thread_id}, thread_id=thread_id)
        self.assertTrue(interrupt.a_turn_is_running(thread_id))
        answer = client.post(f"/api/threads/{thread_id}/turn/stop")
        self.assertTrue(answer.json()["a_turn_was_running"])
        self.assertTrue(interrupt.was_asked(thread_id))

    def test_a_finished_turn_is_not_running(self):
        from app.main import app
        client = support.api_client(app)
        thread_id = client.post("/api/threads", json={"title": "done"}).json()["id"]
        self.addCleanup(interrupt.clear, thread_id)
        events.append("turn.started", {"thread_id": thread_id}, thread_id=thread_id)
        events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)
        self.assertFalse(interrupt.a_turn_is_running(thread_id))


class ANewConversationDoesNotAdoptAPlanTest(unittest.TestCase):
    """Thread 81: one message, "hi", and a `thread.plan_adopted` beside it -
    eighteen open steps the person never asked for."""

    def setUp(self) -> None:
        self.root = support.sandbox(self)

    def test_opening_a_conversation_adopts_nothing_and_opens_in_plan(self):
        from app.main import app
        client = support.api_client(app)
        made = client.post("/api/threads", json={"title": "hi"})
        self.assertIn(made.status_code, (200, 201))
        thread_id = made.json()["id"]
        self.assertEqual(made.json()["mode"], "plan")
        kinds = [row["kind"] for row in events.since(f"thread:{thread_id}")]
        self.assertNotIn("thread.plan_adopted", kinds)
        self.assertFalse((events.get_thread(thread_id) or {}).get("plan"))


class EveryStopReachesTheTurnTest(unittest.TestCase):
    """Max, 2026-09-19: "Even when you click stop in the plan, it doesn't stop
    working. You can literally see it highlighted on the chat that I can see on
    my GPU."

    The run's stop wrote a database row the loop reads ONCE PER ITERATION, and
    an iteration contains a whole turn. So the row said stopped and the card
    kept streaming for the rest of it - times three, with two sub-agents out.
    `longrun.stop` asks `interrupt` now, so every door through it lands inside
    the turn as well: the run panel, the remote link, and a parent stopping a
    child."""

    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.addCleanup(lambda: [interrupt.clear(t) for t in interrupt.waiting()])

    def _mid_turn(self, title: str) -> int:
        thread_id = events.create_thread(title)["id"]
        events.append("turn.started", {"thread_id": thread_id}, thread_id=thread_id)
        self.assertTrue(interrupt.a_turn_is_running(thread_id))
        return thread_id

    def test_stopping_a_run_stops_the_turn_it_is_in(self):
        from app import longrun

        thread_id = self._mid_turn("a run")
        longrun.stop(thread_id, reason="stopped by the person")
        self.assertTrue(
            interrupt.was_asked(thread_id),
            "the run row was written and the turn was left running",
        )

    def test_stopping_a_sub_agent_stops_the_CHILD_s_turn_not_the_parent_s(self):
        from app import longrun, subagents

        parent = events.create_thread("parent")["id"]
        child = self._mid_turn("child")
        from app import db

        subagents.ensure_table()
        with db.session() as connection:
            connection.execute(
                "INSERT INTO subagents(parent_thread_id, child_thread_id, phase, state) "
                "VALUES (?, ?, ?, ?)",
                (parent, child, "## A phase", subagents.RUNNING),
            )
            subagent_id = connection.execute(
                "SELECT id FROM subagents WHERE child_thread_id = ?", (child,)
            ).fetchone()[0]

        subagents.stop(int(subagent_id), "stopped by the person")
        self.assertTrue(
            interrupt.was_asked(child),
            "the child takes its turns on its own thread; a stop on the parent never reaches it",
        )
        self.assertFalse(interrupt.was_asked(parent))
        del longrun

    def test_stopping_an_idle_thread_through_the_run_arms_nothing(self):
        from app import longrun

        thread_id = events.create_thread("idle")["id"]
        longrun.stop(thread_id)
        self.assertFalse(interrupt.was_asked(thread_id))


if __name__ == "__main__":
    unittest.main()
