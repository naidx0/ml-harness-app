"""A phase handed out, worked somewhere else, and folded back in.

Max, 2026-09-13: *"whenever it comes up with a plan, it goes and it gives one
phase of that plan to one sub-agent... at the most we can run two... and then
the orchestrator model just waits for the agent to finish and reads its
responses, so it doesn't burn up its own context window."*

Four claims are worth pinning, and each of them is a way the feature could look
like it works while being useless:

1. THE CHILD GETS THE PHASE AND ONLY THE PHASE. A sub-agent handed the whole
   plan is not delegation, it is a second orchestrator.
2. TWO IS TWO, ACROSS THE MACHINE. A cap that counts per conversation lets four
   sub-agents run on one card, which is the thing the number exists to stop.
3. WHAT COMES BACK IS THE TICKS AND THE PARKS, NOT THE TRANSCRIPT. This is the
   whole economy of the feature; a digest that quoted the child would spend the
   context window it was written to save.
4. THE PARENT DOES NOT BURN TURNS WAITING. A run that took turns while its
   children worked would aim at steps somebody else is doing and park them.

The child's run is a parameter throughout, so every sub-agent below is scripted
turns rather than a model - the only way to assert what the machinery does.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import db, events, longrun, subagents  # noqa: E402
from app.tools import delegation, planning  # noqa: E402

PLAN = chr(10).join(
    [
        "# Train the router",
        "",
        "## Phase 1 - Data",
        "- [ ] Carve the eval set",
        "- [ ] Measure the baseline",
        "",
        "## Phase 2 - Ship",
        "- [ ] Compare the adapter to the baseline",
    ]
)


def _tick(step: str) -> Callable[[int], None]:
    def act(thread_id: int) -> None:
        planning.tick_step(thread_id, step, by="test")

    return act


def _park(step: str, why: str) -> Callable[[int], None]:
    def act(thread_id: int) -> None:
        planning.park_step(thread_id, step, why)

    return act


def _nothing(thread_id: int) -> None:
    return None


def _turns(script: list[Callable[[int], None]]) -> Callable[..., Any]:
    """One scripted turn per entry, ending the way a real one ends."""

    def take(thread_id: int, scaffold: str | None = None):
        index = take.taken["n"]  # type: ignore[attr-defined]
        take.taken["n"] += 1  # type: ignore[attr-defined]
        script[min(index, len(script) - 1)](thread_id)
        yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

    take.taken = {"n": 0}  # type: ignore[attr-defined]
    return take


def _run_with(script: list[Callable[[int], None]]) -> Callable[..., dict[str, Any]]:
    """A stand-in for `longrun.start` that runs the child here and now."""

    def start(child_id: int, *, background: bool = True) -> dict[str, Any]:
        return longrun.start(child_id, background=False, turn=_turns(script))

    return start


class OnePhaseOneSubAgent(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        subagents.ensure_table()
        longrun.ensure_table()
        # THE WAIT IS REAL TIME, so it is shortened here and nowhere else. A
        # test that slept the product's two hours would not be a test.
        self._look, self._at_most = subagents.LOOK_EVERY_SECONDS, subagents.WAIT_AT_MOST_SECONDS
        subagents.LOOK_EVERY_SECONDS, subagents.WAIT_AT_MOST_SECONDS = 0.01, 0.2
        self.parent = events.create_thread("Train the router", mode="build")
        events.set_thread_plan(int(self.parent["id"]), PLAN)

    def tearDown(self) -> None:
        subagents.LOOK_EVERY_SECONDS, subagents.WAIT_AT_MOST_SECONDS = self._look, self._at_most

    def _delegate(self, phase: str, script: list[Callable[[int], None]]):
        return subagents.delegate(
            int(self.parent["id"]), phase, background=False, run=_run_with(script)
        )

    # -- 1. the child gets the phase and only the phase --------------------

    def test_the_child_carries_that_phase_and_no_other(self) -> None:
        out = self._delegate("Phase 1", [_nothing])
        self.assertTrue(out["ok"], out)
        child = events.get_thread(int(out["child_thread_id"]))
        steps = [s["text"] for s in planning.steps_in(child["plan"])]
        self.assertEqual(steps, ["Carve the eval set", "Measure the baseline"])
        self.assertNotIn("Compare the adapter", child["plan"])
        # It says where it came from, so a person opening it is not lost.
        self.assertIn(str(self.parent["id"]), child["plan"])
        self.assertIn("Phase 1 - Data", child["plan"])
        # And it is a real conversation in the same project, with the same
        # folder, which is what lets it build anything at all.
        self.assertEqual(child["project_id"], self.parent["project_id"])
        self.assertEqual(child["mode"], "build")

    def test_a_child_of_a_full_parent_runs_under_full(self) -> None:
        """The second live score row, 2026-09-18: five children of a Full
        parent ran under `write` and every one parked on a question the
        parent had been told never to ask."""
        events.set_thread_permission(int(self.parent["id"]), "full")
        out = self._delegate("Phase 1", [_nothing])
        self.assertTrue(out["ok"], out)
        child = events.get_thread(int(out["child_thread_id"]))
        self.assertEqual(child["permission"], "full")

    def test_a_child_of_an_ask_parent_stays_on_ask(self) -> None:
        out = self._delegate("Phase 1", [_nothing])
        child = events.get_thread(int(out["child_thread_id"]))
        self.assertEqual(child["permission"], "ask")

    def test_a_phase_that_names_nothing_is_refused_with_the_phases(self) -> None:
        out = subagents.delegate(int(self.parent["id"]), "Phase 9", background=False)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "no_such_phase")
        self.assertIn("Phase 1 - Data", out["phases"])

    def test_a_phase_with_nothing_open_is_refused(self) -> None:
        planning.tick_step(int(self.parent["id"]), "Compare the adapter")
        out = subagents.delegate(int(self.parent["id"]), "Phase 2", background=False)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "phase_has_no_open_steps")

    # -- 2. two is two, across the machine ---------------------------------

    def test_two_run_and_a_third_is_refused_wherever_it_is_asked_from(self) -> None:
        """The cap is on the card, not on the conversation.

        Both sub-agents here are left RUNNING - their child runs never start,
        so nothing settles them - and the third is asked for from a DIFFERENT
        conversation, which a per-conversation cap would happily allow.
        """
        held: dict[str, Any] = {"ok": True, "run": {}}
        first = subagents.delegate(
            int(self.parent["id"]), "Phase 1", background=False,
            run=lambda child_id, background=True: held,
        )
        second = subagents.delegate(
            int(self.parent["id"]), "Phase 2", background=False,
            run=lambda child_id, background=True: held,
        )
        self.assertTrue(first["ok"] and second["ok"])
        self.assertEqual(subagents.running_anywhere(), 2)

        elsewhere = events.create_thread("Another project's work", mode="build")
        events.set_thread_plan(int(elsewhere["id"]), PLAN)
        third = subagents.delegate(int(elsewhere["id"]), "Phase 1", background=False)
        self.assertFalse(third["ok"])
        self.assertEqual(third["error"], "at_the_limit")
        self.assertEqual(third["at_most"], 2)
        self.assertIn("two sub-agents", third["detail"].lower())

    def test_a_sub_agent_may_not_delegate(self) -> None:
        out = self._delegate("Phase 1", [_nothing])
        child_id = int(out["child_thread_id"])
        events.set_thread_plan(child_id, PLAN)
        again = subagents.delegate(child_id, "Phase 2", background=False)
        self.assertFalse(again["ok"])
        self.assertEqual(again["error"], "sub_agents_do_not_delegate")

    # -- 3. the ticks and the parks come back, the transcript does not -----

    def test_what_the_child_did_is_written_into_the_parent_s_plan(self) -> None:
        out = self._delegate(
            "Phase 1",
            [
                _tick("Carve the eval set"),
                _park("Measure the baseline", "no model is connected"),
            ],
        )
        self.assertTrue(out["ok"], out)
        folded = subagents.harvest(int(self.parent["id"]))
        self.assertEqual(len(folded), 1)

        plan = events.get_thread(int(self.parent["id"]))["plan"]
        states = {s["text"]: s["state"] for s in planning.steps_in(plan)}
        self.assertEqual(states["Carve the eval set"], "done")
        self.assertEqual(states["Measure the baseline"], "parked")
        self.assertEqual(states["Compare the adapter to the baseline"], "open")
        why = [s["why"] for s in planning.steps_in(plan) if s["state"] == "parked"]
        self.assertIn("no model is connected", why[0])

    def test_a_step_the_child_never_reached_is_parked_saying_so(self) -> None:
        """It must not sit open waiting for a sub-agent that has stopped.

        The child here is stopped with a step still OPEN - not parked by its
        own run, which is the other case and comes back with the child's own
        reason. A step nobody worked and nobody refused is the one that would
        otherwise sit open forever.
        """
        held: dict[str, Any] = {"ok": True, "run": {}}
        out = subagents.delegate(
            int(self.parent["id"]), "Phase 1", background=False,
            run=lambda child_id, background=True: held,
        )
        self.assertTrue(out["ok"], out)
        planning.tick_step(int(out["child_thread_id"]), "Carve the eval set")
        subagents.stop(int(out["subagent_id"]), "stopped by hand")
        subagents.harvest(int(self.parent["id"]))
        plan = events.get_thread(int(self.parent["id"]))["plan"]
        states = {s["text"]: s["state"] for s in planning.steps_in(plan)}
        self.assertEqual(states["Carve the eval set"], "done")
        self.assertEqual(states["Measure the baseline"], "parked")
        why = {s["text"]: s["why"] for s in planning.steps_in(plan)}
        self.assertIn("stopped before reaching it", why["Measure the baseline"])

    def test_reading_the_strip_folds_a_finished_child_back_in(self) -> None:
        """The promise `delegate_phase` returns, made true off a run.

        No long run here: the model handed a phase out in an ordinary turn.
        Nothing but a read happens, and the parent's plan has to move anyway.
        """
        self._delegate("Phase 1", [_tick("Carve the eval set"), _tick("Measure the baseline")])
        before = planning.steps_in(events.get_thread(int(self.parent["id"]))["plan"])
        self.assertEqual([one["state"] for one in before], ["open", "open", "open"])

        subagents.read(int(self.parent["id"]))

        after = planning.steps_in(events.get_thread(int(self.parent["id"]))["plan"])
        self.assertEqual([one["state"] for one in after], ["done", "done", "open"])
        # And reading again folds nothing a second time.
        self.assertEqual(subagents.harvest(int(self.parent["id"])), [])

    def test_a_finished_sub_agent_closes_its_own_conversation(self) -> None:
        """Max, 2026-09-14: *"once they stop running they should be closed,
        only shown when they are running under one plan or session. Once those
        phases finish then they should close the session so they can't be seen,
        for easy UX."*

        ARCHIVED, NOT DELETED. `events.archive_thread` writes a timestamp and
        takes the thread out of the rail, leaving every message and event where
        they are - so the sub-agent's reasoning is on the record for anyone who
        goes looking, and nobody is asked to keep track of six finished
        conversations they never opened. What it DID is already in the parent's
        plan by the time this runs.
        """
        self._delegate("Phase 1", [_tick("Carve the eval set")])
        child = int(subagents.read(int(self.parent["id"]))["subagents"][0]["thread_id"])

        row = events.get_thread(child)
        self.assertIsNotNone(row["archived_at"], "it stayed in the rail after finishing")
        # Not deleted: the transcript is the artifact.
        self.assertIsNotNone(row["plan"], "archiving must not take the record with it")
        self.assertNotIn(child, [t["id"] for t in events.list_threads()],
                         "the rail read still lists a closed sub-agent")

        # AND A WORKING ONE STAYS. The scripted turn above finishes inside
        # `_delegate`, so there is no moment in this test where that child is
        # observably running - the honest way to pin the other half is a row
        # that IS running, which `harvest` skips by its first condition.
        #
        # THE RUN HAS TO MOVE TOO, and the first draft of this did not: harvest
        # calls `settle` before it reads the state, `settle` reads the child's
        # `long_runs` row, and a subagent row flipped to running against a run
        # that says done is put straight back. That is the module being right,
        # so the fixture is what changes.
        with db.session() as connection:
            connection.execute(
                "UPDATE long_runs SET state = ? WHERE thread_id = ?",
                (longrun.RUNNING, child),
            )
            connection.execute(
                "UPDATE subagents SET state = ?, harvested = 0 WHERE child_thread_id = ?",
                (subagents.RUNNING, child),
            )
            connection.execute(
                "UPDATE threads SET archived_at = NULL WHERE id = ?", (child,)
            )
        subagents.harvest(int(self.parent["id"]))
        self.assertIsNone(
            events.get_thread(child)["archived_at"],
            "a sub-agent that is still working had its conversation closed")

    def test_harvesting_twice_folds_once(self) -> None:
        self._delegate("Phase 1", [_tick("Carve the eval set"), _tick("Measure the baseline")])
        first = subagents.harvest(int(self.parent["id"]))
        second = subagents.harvest(int(self.parent["id"]))
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    def test_the_digest_is_a_paragraph_and_never_the_child_s_words(self) -> None:
        """THE ECONOMY OF THE WHOLE FEATURE, asserted.

        The child says a great deal in its own thread. What reaches the
        orchestrator is the phase, the counts and the parked reasons - and the
        assertion that matters is the NEGATIVE one.
        """
        spoken = "I read every file in the repository and here is what I think " * 40

        def talk(thread_id: int) -> None:
            events.append("chat.delta", {"text": spoken}, thread_id=thread_id)
            planning.tick_step(thread_id, "Carve the eval set")

        out = self._delegate("Phase 1", [talk, _park("Measure the baseline", "no eval rows")])
        self.assertTrue(out["ok"], out)
        folded = subagents.harvest(int(self.parent["id"]))
        digest = subagents.digest_for(int(self.parent["id"]), folded)

        self.assertIn("Phase 1 - Data", digest)
        self.assertIn("no eval rows", digest)
        self.assertNotIn("every file in the repository", digest)
        self.assertLess(len(digest), 1200, digest)

    def test_no_sub_agents_means_no_digest(self) -> None:
        self.assertEqual(subagents.digest_for(int(self.parent["id"]), []), "")

    # -- 4. the parent waits rather than working over its children ---------

    def test_a_run_waiting_on_a_child_spends_no_turns_on_it(self) -> None:
        """The parent's loop finds the phase done rather than working it.

        The child is run to completion first, then the parent's run is started
        with a turn that would tick nothing. Without the wait-and-harvest the
        parent would aim at "Carve the eval set", tick nothing twice and park a
        step its own sub-agent had already done.
        """
        self._delegate(
            "Phase 1",
            [_tick("Carve the eval set"), _tick("Measure the baseline")],
        )
        seen: dict[str, Any] = {"scaffolds": []}

        def take(thread_id: int, scaffold: str | None = None):
            seen["scaffolds"].append(scaffold)
            planning.tick_step(thread_id, "Compare the adapter")
            yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

        longrun.start(int(self.parent["id"]), background=False, turn=take)
        run = longrun.status(int(self.parent["id"]))
        self.assertEqual(run["state"], longrun.DONE)
        self.assertEqual(run["stop_reason"], "plan_worked_down")
        # One turn: the one that did the step nobody was handed.
        self.assertEqual(run["turns"], 1)
        # And that turn was told what came back, in the harness's own voice.
        self.assertTrue(seen["scaffolds"][0])
        self.assertIn("come back", seen["scaffolds"][0])
        self.assertIn("[harness]", seen["scaffolds"][0])

    def test_stopping_the_run_stops_what_it_handed_out(self) -> None:
        held: dict[str, Any] = {"ok": True, "run": {}}
        out = subagents.delegate(
            int(self.parent["id"]), "Phase 1", background=False,
            run=lambda child_id, background=True: held,
        )

        def stop_itself(thread_id: int, scaffold: str | None = None):
            longrun.stop(thread_id)
            yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

        longrun.start(int(self.parent["id"]), background=False, turn=stop_itself)
        row = subagents.read(int(self.parent["id"]))["subagents"][0]
        self.assertEqual(row["state"], subagents.STOPPED)
        self.assertEqual(subagents.running_anywhere(), 0)
        self.assertEqual(int(out["subagent_id"]), row["id"])

    # -- what the tools say ------------------------------------------------

    def test_the_tool_refuses_at_the_limit_in_words_a_model_can_act_on(self) -> None:
        held: dict[str, Any] = {"ok": True, "run": {}}
        for phase in ("Phase 1", "Phase 2"):
            subagents.delegate(
                int(self.parent["id"]), phase, background=False,
                run=lambda child_id, background=True: held,
            )
        events.set_thread_plan(
            int(self.parent["id"]),
            events.get_thread(int(self.parent["id"]))["plan"] + chr(10)
            + "## Phase 3 - Later" + chr(10) + "- [ ] Write it up" + chr(10),
        )
        out = delegation.delegate_phase("Phase 3", thread_id=int(self.parent["id"]))
        self.assertFalse(out["ok"])
        self.assertIn("check_the_sub_agents", out["detail"])

    def test_check_folds_before_it_answers(self) -> None:
        self._delegate("Phase 1", [_tick("Carve the eval set"), _tick("Measure the baseline")])
        out = delegation.check_the_sub_agents(thread_id=int(self.parent["id"]))
        self.assertTrue(out["ok"])
        self.assertEqual(out["running"], 0)
        self.assertEqual(len(out["just_came_back"]), 1)
        self.assertEqual(len(out["just_came_back"][0]["ticked"]), 2)
        plan = events.get_thread(int(self.parent["id"]))["plan"]
        self.assertEqual(
            [s["state"] for s in planning.steps_in(plan)], ["done", "done", "open"]
        )

    def test_check_with_nothing_handed_out_says_how_to_hand_one_out(self) -> None:
        out = delegation.check_the_sub_agents(thread_id=int(self.parent["id"]))
        self.assertTrue(out["ok"])
        self.assertEqual(out["subagents"], [])
        self.assertIn("delegate_phase", out["next"])

    # -- the reap, same argument as the runs' -------------------------------

    def test_a_sub_agent_from_a_dead_engine_is_not_working(self) -> None:
        held: dict[str, Any] = {"ok": True, "run": {}}
        subagents.delegate(
            int(self.parent["id"]), "Phase 1", background=False,
            run=lambda child_id, background=True: held,
        )
        self.assertEqual(subagents.running_anywhere(), 1)
        self.assertEqual(subagents.reap_orphans(), 1)
        self.assertEqual(subagents.running_anywhere(), 0)
        row = subagents.read(int(self.parent["id"]))["subagents"][0]
        self.assertEqual(row["state"], subagents.STOPPED)
        self.assertIn("engine stopped", row["detail"])


if __name__ == "__main__":
    unittest.main()
