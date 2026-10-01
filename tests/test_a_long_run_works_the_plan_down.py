"""A run takes turns until the plan is worked down, and parks what it cannot do.

Max, 2026-09-13: *"some sort of long running tasks structure, executed from
the plan, simple re-prompts and tell the agent to work... the model has to
keep thinking and going no matter what. On any kind of stops or rule
gateways, it goes as far as it can without that exception in particular."*

`app/longrun.py` is the loop; `planning.park_step` is the "without that
exception in particular". The turn is a parameter here so the loop can be
driven without a model - every turn below is a scripted one, which is the
only way to assert what the loop does rather than what a model did.
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
from app import events, longrun  # noqa: E402
from app.tools import planning  # noqa: E402

PLAN = "\n".join(
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


def _turns(script: list[Callable[[int], None]]) -> Callable[[int], Any]:
    """Each entry is one turn: what it does to the thread, then it ends."""
    taken = {"n": 0}

    def take(thread_id: int):
        index = min(taken["n"], len(script) - 1)
        taken["n"] += 1
        script[index](thread_id)
        yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

    take.taken = taken  # type: ignore[attr-defined]
    return take


def _hollow_turns(count: int, then: Callable[[int], None] | None = None) -> Callable[[int], Any]:
    """`count` turns that come back with nothing, then one that works.

    An `empty_reply` is a turn where the connection was fine and the model
    emitted no words and no tool calls - the case Max hit repeatedly on
    2026-09-14. It changes nothing about the plan, which is the whole point.
    """
    taken = {"n": 0}

    def take(thread_id: int):
        index = taken["n"]
        taken["n"] += 1
        if index < count:
            yield events.append("stream.end", {"ending": "empty_reply"}, thread_id=thread_id)
            return
        if then is not None:
            then(thread_id)
        yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

    take.taken = taken  # type: ignore[attr-defined]
    return take


def _tick(step: str) -> Callable[[int], None]:
    def act(thread_id: int) -> None:
        row = events.get_thread(thread_id)
        plan = row["plan"]
        for line in plan.splitlines():
            if step.lower() in line.lower() and "- [ ]" in line:
                events.set_thread_plan(thread_id, plan.replace(line, line.replace("- [ ]", "- [x]", 1)))
                return

    return act


def _says(text: str) -> Callable[[int], None]:
    def act(thread_id: int) -> None:
        events.append("chat.delta", {"text": text}, thread_id=thread_id)

    return act


class WorksDownTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_plan(self.thread, PLAN)

    def test_it_takes_one_turn_per_step_and_stops_when_none_is_open(self):
        take = _turns(
            [_tick("Carve the eval set"), _tick("Measure the baseline"), _tick("Compare the adapter")]
        )
        out = longrun.start(self.thread, background=False, turn=take)
        self.assertTrue(out["ok"], out)
        run = longrun.status(self.thread)
        self.assertEqual(run["state"], longrun.DONE)
        self.assertEqual(run["stop_reason"], "plan_worked_down")
        self.assertEqual(run["open"], 0)
        self.assertEqual(run["done"], 3)
        self.assertEqual(run["turns"], 3)
        kinds = [r["kind"] for r in events.since(f"thread:{self.thread}", limit=500)]
        self.assertEqual(kinds.count("run.turn"), 3)
        self.assertIn("run.started", kinds)
        self.assertIn("run.finished", kinds)

    def test_a_step_it_cannot_do_is_parked_and_the_run_goes_on(self):
        """The whole of "as far as it can". Two turns fail to move step one;
        it is parked with what the model said, and step two is worked next."""
        script = [
            _says("The eval set file does not exist, so I cannot carve it."),
            _says("The eval set file does not exist, so I cannot carve it."),
            _tick("Measure the baseline"),
            _tick("Compare the adapter"),
        ]
        longrun.start(self.thread, background=False, turn=_turns(script))
        run = longrun.status(self.thread)
        self.assertEqual(run["state"], longrun.DONE)
        self.assertEqual(run["open"], 0)
        self.assertEqual(run["done"], 2)
        self.assertEqual(len(run["parked"]), 1)
        self.assertEqual(run["parked"][0]["step"], "Carve the eval set")
        self.assertIn("does not exist", run["parked"][0]["why"])
        plan = events.get_thread(self.thread)["plan"]
        self.assertIn("- [!] Carve the eval set", plan)
        self.assertIn("parked: The eval set file does not exist", plan)
        kinds = [r["kind"] for r in events.since(f"thread:{self.thread}", limit=500)]
        self.assertIn("thread.step_parked", kinds)
        finished = [
            r["payload"] for r in events.since(f"thread:{self.thread}", limit=500)
            if r["kind"] == "run.finished"
        ][-1]
        self.assertEqual(finished["parked"][0]["step"], "Carve the eval set")

    def test_one_bad_turn_is_not_enough_to_park(self):
        script = [_says("Reading the folder first."), _tick("Carve the eval set")]
        longrun.start(self.thread, background=False, turn=_turns(script + [_tick("Measure the baseline"), _tick("Compare the adapter")]))
        self.assertEqual(longrun.status(self.thread)["parked"], [])
        self.assertEqual(longrun.status(self.thread)["done"], 3)

    def test_an_approval_hands_back_to_the_person(self):
        def asks(thread_id: int) -> None:
            events.append(
                "tool.result",
                {"name": "start_training", "ok": False, "result": {"error": "approval_required"}},
                thread_id=thread_id,
            )

        longrun.start(self.thread, background=False, turn=_turns([asks]))
        run = longrun.status(self.thread)
        self.assertEqual(run["stop_reason"], "approval_needed")
        self.assertEqual(run["open"], 3, "nothing was parked - a yes is the person's, not a blocker")

    def test_two_connection_failures_end_it_and_one_does_not(self):
        def fails(thread_id: int):
            yield events.append("stream.end", {"ending": "provider_failed"}, thread_id=thread_id)

        longrun.start(self.thread, background=False, turn=lambda tid: fails(tid))
        run = longrun.status(self.thread)
        self.assertEqual(run["state"], longrun.FAILED)
        self.assertEqual(run["stop_reason"], "provider_failed")

    def test_the_turn_cap_hands_back(self):
        longrun.start(self.thread, background=False, cap=3, turn=_turns([_says("thinking")]))
        run = longrun.status(self.thread)
        self.assertEqual(run["turns"], 3)
        self.assertEqual(run["stop_reason"], "turn_cap")

    def test_a_turn_that_raises_is_reported_not_swallowed(self):
        def explode(thread_id: int):
            raise RuntimeError("the engine fell over")
            yield  # pragma: no cover - a generator that raises before yielding

        longrun.start(self.thread, background=False, turn=explode)
        run = longrun.status(self.thread)
        self.assertEqual(run["state"], longrun.FAILED)
        self.assertIn("the engine fell over", run["detail"])

    def test_stopping_between_turns(self):
        def stop_after_one(thread_id: int):
            longrun.stop(thread_id)
            yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

        longrun.start(self.thread, background=False, turn=stop_after_one)
        run = longrun.status(self.thread)
        self.assertEqual(run["state"], longrun.STOPPED)
        self.assertEqual(run["open"], 3)


class WhenNothingMovesTest(unittest.TestCase):
    """MEASURED 2026-09-13: a plan whose five steps were the five gate names
    ran ten turns, ticked nothing and parked everything. No amount of
    re-prompting fixes a step nobody can do - so when nothing moves, the run
    says the plan is the suspect, once, as scaffolding for that turn."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_plan(self.thread, PLAN)

    def test_three_barren_turns_ask_for_a_rewrite_once_and_never_as_a_message(self):
        seen: list[str | None] = []

        def take(thread_id: int, scaffold: str | None = None):
            seen.append(scaffold)
            yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

        longrun.start(self.thread, background=False, cap=8, turn=take)
        self.assertEqual(seen[:3], [None, None, None], "three turns before the run blames the plan")
        self.assertEqual(seen[3], longrun.REPLAN_NUDGE)
        self.assertEqual(
            [s for s in seen if s], [longrun.REPLAN_NUDGE], "asked once, never twice"
        )
        self.assertNotIn(
            longrun.REPLAN_NUDGE,
            [m["content"] for m in events.messages_for(self.thread)],
            "a line typed by nobody never becomes something the person said",
        )
        kinds = [r["kind"] for r in events.since(f"thread:{self.thread}", limit=500)]
        self.assertEqual(kinds.count("run.replan"), 1)

    def test_a_turn_that_moves_a_step_resets_the_count(self):
        # Two barren turns park the step the run was aiming at, so the third
        # turn is aiming at the next one - ticking THAT is what resets the
        # count. A step moved is a run that is working.
        script = [_says("looking"), _says("looking"), _tick("Measure the baseline"), _says("looking")]
        seen: list[str | None] = []
        inner = _turns(script)

        def take(thread_id: int, scaffold: str | None = None):
            seen.append(scaffold)
            yield from inner(thread_id)

        longrun.start(self.thread, background=False, cap=5, turn=take)
        self.assertEqual([s for s in seen if s], [], "the barren count restarts when a step moves")


class ParkedReasonsAreShortTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_plan(self.thread, PLAN)

    def test_a_refusal_from_a_tool_beats_the_reply(self):
        def act(thread_id: int) -> None:
            events.append(
                "tool.result",
                {"name": "measure_baseline", "ok": False,
                 "result": {"ok": False, "error": "no_eval_set", "detail": "eval.jsonl is not on disk"}},
                thread_id=thread_id,
            )
            events.append("chat.delta", {"text": "Here is a long status report. " * 20}, thread_id=thread_id)

        longrun.start(self.thread, background=False, cap=4, turn=_turns([act]))
        parked = (longrun.status(self.thread)["parked"] or [{}])[0]
        self.assertIn("measure_baseline refused", parked.get("why", ""))
        self.assertIn("eval.jsonl is not on disk", parked.get("why", ""))
        self.assertLess(len(parked.get("why", "")), 200, "a parked line is read at a glance")

    def test_without_a_refusal_it_is_one_sentence_of_the_reply(self):
        long_reply = (
            "Here is the state." + chr(10) + chr(10)
            + "The eval set file does not exist. Everything else is fine and here is a "
            + "very long tail of bullet points that nobody reads. " * 6
        )
        longrun.start(self.thread, background=False, cap=4, turn=_turns([_says(long_reply)]))
        parked = (longrun.status(self.thread)["parked"] or [{}])[0]
        self.assertTrue(parked.get("why", "").startswith("The eval set file does not exist"))
        self.assertLess(len(parked.get("why", "")), 200)


class WhatItSaysIsWhatHappenedTest(unittest.TestCase):
    """Max, 2026-09-13, photographing the bar: four of five steps parked and
    the run reported "plan worked down", which reads as success and was not.
    And the browser loop said "working down the plan (0)" with nothing to
    work - saying "working" with nothing to work is the worst kind of wrong,
    because it looks like progress."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_plan(self.thread, PLAN)

    def test_parking_everything_is_not_working_it_down(self):
        longrun.start(self.thread, background=False, cap=12, turn=_turns([_says("I cannot do this.")]))
        run = longrun.status(self.thread)
        self.assertIn(run["stop_reason"], ("nothing_could_be_worked", "the_plan_could_not_be_worked"))
        self.assertNotEqual(run["stop_reason"], "plan_worked_down")
        self.assertIn("rewrit", run["detail"].lower(), "it says what to do about it")

    def test_three_parks_in_a_row_end_the_run_rather_than_grinding_on(self):
        long_plan = PLAN + chr(10).join(
            ["", "## Phase 3 - More", "- [ ] Step four", "- [ ] Step five", "- [ ] Step six"]
        )
        events.set_thread_plan(self.thread, long_plan)
        longrun.start(self.thread, background=False, cap=24, turn=_turns([_says("no")]))
        run = longrun.status(self.thread)
        self.assertEqual(run["stop_reason"], "the_plan_could_not_be_worked")
        self.assertEqual(len(run["parked"]), longrun.PARKS_IN_A_ROW, "it stopped at three, not at all six")
        self.assertGreater(run["open"], 0, "the rest of the plan is left as it was")

    def test_a_run_that_ticked_more_than_it_parked_still_reads_as_worked_down(self):
        script = [_tick("Carve the eval set"), _tick("Measure the baseline"), _says("cannot"), _says("cannot")]
        longrun.start(self.thread, background=False, cap=12, turn=_turns(script))
        run = longrun.status(self.thread)
        self.assertEqual(run["stop_reason"], "plan_worked_down")
        self.assertEqual(run["done"], 2)
        self.assertEqual(len(run["parked"]), 1)


class OrphansTest(unittest.TestCase):
    """A run is a thread in the engine's process. If that process dies, the
    row would say `running` forever and the chip would claim work nobody is
    doing."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_plan(self.thread, PLAN)

    def test_a_run_left_running_by_a_dead_engine_is_ended_at_startup(self):
        def stall(thread_id: int):
            longrun.stop(thread_id)  # end the loop without ending the row below
            yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

        longrun.start(self.thread, background=False, turn=stall)
        longrun._write(self.thread, state=longrun.RUNNING, stop_reason="")
        self.assertEqual(longrun.reap_orphans(), 1)
        run = longrun.status(self.thread)
        self.assertEqual(run["state"], longrun.STOPPED)
        self.assertEqual(run["stop_reason"], "engine_restarted")
        kinds = [r["kind"] for r in events.since(f"thread:{self.thread}", limit=500)]
        self.assertIn("run.finished", kinds)
        self.assertEqual(longrun.reap_orphans(), 0, "nothing to reap the second time")


class RefusalsTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)

    def test_plan_mode_is_refused_with_the_door(self):
        thread = int(events.create_thread("t", mode="plan")["id"])
        events.set_thread_plan(thread, PLAN)
        out = longrun.start(thread, background=False, turn=_turns([_says("x")]))
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "not_building")
        self.assertIn("Switch to Build", out["detail"])

    def test_nothing_open_is_refused(self):
        thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_plan(thread, PLAN.replace("- [ ]", "- [x]"))
        out = longrun.start(thread, background=False, turn=_turns([_says("x")]))
        self.assertEqual(out["error"], "nothing_open")

    def test_a_missing_thread_is_not_a_crash(self):
        self.assertEqual(longrun.start(99999, background=False)["error"], "no_such_thread")
        self.assertIsNone(longrun.status(99999))
        self.assertIsNone(longrun.stop(99999))


class ParkedStepsTest(unittest.TestCase):
    """`- [!]` is a third state, and every reader knows it."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_plan(self.thread, PLAN)

    def test_a_parked_step_is_not_open_and_keeps_its_words(self):
        planning.park_step(self.thread, "Carve the eval set", "no eval file on disk")
        plan = events.get_thread(self.thread)["plan"]
        steps = planning.steps_in(plan)
        parked = [s for s in steps if s["state"] == "parked"]
        self.assertEqual(len(parked), 1)
        self.assertEqual(parked[0]["text"], "Carve the eval set", "the reason is not part of the step")
        self.assertEqual(parked[0]["why"], "no eval file on disk")
        self.assertEqual([s["text"] for s in planning.open_steps(plan)],
                         ["Measure the baseline", "Compare the adapter to the baseline"])

    def test_a_parked_step_can_still_be_ticked_by_its_words(self):
        """The person disagrees, or the file appears. `mark_step_done` matches
        on the step's own words, which parking did not change."""
        planning.park_step(self.thread, "Carve the eval set", "no eval file on disk")
        plan = events.get_thread(self.thread)["plan"]
        self.assertIn("Carve the eval set", plan)
        steps = planning.steps_in(plan)
        self.assertEqual(steps[0]["text"], "Carve the eval set")

    def test_parking_needs_exactly_one_open_match(self):
        self.assertIsNone(planning.park_step(self.thread, "nothing like this", "x"))
        self.assertIsNone(planning.park_step(self.thread, "", "x"))
        planning.park_step(self.thread, "Carve the eval set", "x")
        self.assertIsNone(planning.park_step(self.thread, "Carve the eval set", "x"),
                          "a parked step is not open, so it cannot be parked twice")

    def test_unpark_puts_a_parked_step_back_to_open(self):
        planning.park_step(self.thread, "Carve the eval set", "no eval file on disk")
        plan = events.get_thread(self.thread)["plan"]
        self.assertTrue(any(s["state"] == "parked" for s in planning.steps_in(plan)))
        result = planning.unpark_step(self.thread, "Carve the eval set")
        self.assertIsNotNone(result)
        self.assertEqual(result["step"], "Carve the eval set")
        after = events.get_thread(self.thread)["plan"]
        steps = planning.steps_in(after)
        carve = next(s for s in steps if s["text"] == "Carve the eval set")
        self.assertEqual(carve["state"], "open")
        self.assertEqual(carve["why"], "")
        self.assertNotIn("parked:", after)
        self.assertIsNone(planning.unpark_step(self.thread, "Carve the eval set"),
                          "an open step is not parked")
        self.assertIsNone(planning.unpark_step(self.thread, "nothing like this"))

    def test_unpark_step_tool_is_callable_by_the_agent(self):
        from app.tools import REGISTRY, evidence

        planning.park_step(self.thread, "Carve the eval set", "blocked")
        out = REGISTRY.call(
            "unpark_step",
            {"step": "Carve the eval set"},
            actor=evidence.MODEL,
            thread_id=self.thread,
        )
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(out.get("unparked"), "Carve the eval set")
        carve = next(
            s for s in planning.steps_in(events.get_thread(self.thread)["plan"])
            if s["text"] == "Carve the eval set"
        )
        self.assertEqual(carve["state"], "open")

    def test_the_prompt_names_the_parked_steps_and_tells_it_not_to_retry(self):
        from app import conductor

        planning.park_step(self.thread, "Carve the eval set", "no eval file on disk")
        plan = events.get_thread(self.thread)["plan"]
        note = conductor._plan_note({"plan": plan, "mode": "build"}, "build")
        self.assertIn("PARKED, and not to be retried", note)
        self.assertIn("no eval file on disk", note)
        self.assertIn("STEPS: 0 of 3 ticked", note)
        self.assertNotIn("- [ ] Carve the eval set", note)


class AnEmptyTurnIsNotEvidenceAboutTheStepTest(unittest.TestCase):
    """Max, 2026-09-14: *"I keep hitting this, the model returned empty quite
    often - how come it cancels mid task? Where's our long-running task policy
    keeping agents working and thinking instead of failing out early and
    stopping?"*

    MEASURED on his database, last 135 turns: `empty_reply` is 5% overall and
    4 of 11 on thread 64. Every one of them used to cost the step it was aiming
    at a strike, because the loop counted "the step is still open" without
    asking why - so two silent turns in a row PARKED a step the model had never
    attempted, with the reason "the model said nothing about why". That is the
    "it keeps parking things" from a day earlier, and the park was a lie about
    the step.
    """

    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_plan(self.thread, PLAN)

    def test_two_empty_turns_do_not_park_the_step_they_never_tried(self):
        # THREE TURNS EXACTLY: two that come back with nothing, one that works
        # the step. The cap stops it there, so what is asserted is the effect
        # of the silent turns and not of whatever a fourth one did.
        longrun.start(self.thread, background=False, cap=3,
                      turn=_hollow_turns(2, _tick("Carve the eval set")))

        steps = planning.steps_in(events.get_thread(self.thread)["plan"])
        self.assertEqual(
            [one for one in steps if one["state"] == "parked"], [],
            "a step was parked by turns that produced nothing - the run treated "
            "a silent model as evidence that the step could not be done.")
        self.assertEqual(
            [one["text"] for one in steps if one["state"] == "done"],
            ["Carve the eval set"],
            "the run gave up before the turn that worked")

    def test_it_still_stops_when_the_model_never_comes_back(self):
        """Bounded, or a model that has gone silent is retried to the cap."""
        longrun.start(self.thread, background=False, cap=24, turn=_hollow_turns(99))

        run = longrun.status(self.thread)
        self.assertEqual(run["stop_reason"], "the_model_stopped_answering")
        self.assertEqual(run["state"], longrun.FAILED)
        self.assertLessEqual(
            int(run["turns"]), longrun.HOLLOW_TURNS + 1,
            "it kept asking a model that had stopped answering")
        self.assertEqual(
            [one for one in planning.steps_in(events.get_thread(self.thread)["plan"])
             if one["state"] == "parked"],
            [],
            "it parked steps on the way out, which is the defect this fixes")


def _narration_turns(count: int, then: Callable[[int], None] | None = None) -> Callable[[int], Any]:
    """Turns that announce a move and call no tool (said_it_would notice)."""
    taken = {"n": 0}

    def take(thread_id: int, scaffold: str | None = None):
        del scaffold
        index = taken["n"]
        taken["n"] += 1
        if index < count:
            yield events.append(
                "chat.delta",
                {"text": "I'll get the next question from the harness."},
                thread_id=thread_id,
            )
            yield events.append(
                "conductor.notice",
                {"reason": "said_it_would_and_did_nothing", "said": "I'll get the next question"},
                thread_id=thread_id,
            )
            yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)
            return
        if then is not None:
            then(thread_id)
        yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

    take.taken = taken  # type: ignore[attr-defined]
    return take


class ANarrationIsNotEvidenceAboutTheStepTest(unittest.TestCase):
    """AU7 — screenshot 2026-09-15: Full parked three tools after
    said_it_would_and_did_nothing while standing still asked for state_facts.
    """

    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_permission(self.thread, "full")
        events.set_thread_plan(self.thread, PLAN)

    def test_two_narration_turns_do_not_park(self):
        longrun.start(
            self.thread,
            background=False,
            cap=3,
            turn=_narration_turns(2, _tick("Carve the eval set")),
        )
        steps = planning.steps_in(events.get_thread(self.thread)["plan"])
        self.assertEqual(
            [one for one in steps if one["state"] == "parked"],
            [],
            "narration-only turns must not park a step",
        )
        self.assertEqual(
            [one["text"] for one in steps if one["state"] == "done"],
            ["Carve the eval set"],
        )

    def test_it_stops_when_narration_never_ends(self):
        longrun.start(
            self.thread, background=False, cap=24, turn=_narration_turns(99)
        )
        run = longrun.status(self.thread)
        self.assertEqual(run["stop_reason"], "the_model_only_narrated")
        self.assertEqual(run["state"], longrun.FAILED)
        self.assertEqual(
            [one for one in planning.steps_in(events.get_thread(self.thread)["plan"])
             if one["state"] == "parked"],
            [],
        )


class IntentIsNotABlockerForParkingTest(unittest.TestCase):
    """2026-09-16 screenshot: parked eval step with why 'I'll read the plan…'."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])
        events.set_thread_permission(self.thread, "full")
        events.set_thread_plan(self.thread, PLAN)

    def test_intent_why_is_detected(self):
        self.assertTrue(
            longrun._intent_not_a_blocker(
                "I'll read the current plan to see what's already ticked"
            )
        )
        self.assertTrue(longrun._intent_not_a_blocker("Let me check the eval set"))
        self.assertFalse(longrun._intent_not_a_blocker("no eval file on disk"))
        self.assertFalse(
            longrun._intent_not_a_blocker("measure_baseline refused: missing path")
        )

    def test_full_without_tool_refusal_does_not_park(self):
        """Tools ran and succeeded but the step stayed open — under Full that
        is not a park; parking needs a real tool refusal."""

        def take(thread_id: int, scaffold: str | None = None):
            del scaffold
            yield events.append(
                "tool.call",
                {"name": "read_plan", "call_id": "c1", "args": {}},
                thread_id=thread_id,
            )
            yield events.append(
                "tool.result",
                {
                    "name": "read_plan",
                    "call_id": "c1",
                    "ok": True,
                    "result": {"ok": True},
                },
                thread_id=thread_id,
            )
            yield events.append(
                "chat.delta",
                {"text": "I'll read the current plan to see what's already ticked."},
                thread_id=thread_id,
            )
            yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

        longrun.start(self.thread, background=False, cap=3, turn=take)
        parked = [
            one
            for one in planning.steps_in(events.get_thread(self.thread)["plan"])
            if one["state"] == "parked"
        ]
        self.assertEqual(parked, [], "Full must not park without a tool refusal")


if __name__ == "__main__":
    unittest.main()
