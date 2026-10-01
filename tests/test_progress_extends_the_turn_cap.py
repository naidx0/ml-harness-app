"""A run that is still ticking steps at its cap gets six more turns, twice over.

Max, 2026-09-18: *"at the cap, if a step was ticked within the last 3 turns,
extend the cap by 6 more turns (repeatable, bounded by an absolute ceiling of
96); if not, stop as today."*

## What the cap is for, and what it was doing instead

`TURN_CAP = 24` exists to stop a run that is going NOWHERE from spending the
afternoon. The file says so in its own words - three things stop a run, "and
each is the person's business rather than the plan's".

A run ticking a step every other turn is not that run. Stopping it at 24
throws away a plan that is working, three steps from the end, and hands the
person a half-done checklist to restart by hand - which costs them the
twenty-four turns already spent as well as the ones it would have taken. The
bound was right about the failure and wrong about the success, because it could
not tell them apart.

## What decides it

`thread.step_done`, and nothing else. It is the harness's one record of a step
ticking: `mark_step_done` writes it when the model says so, and
`planning.tick_for_tool` writes the same row with `by: harness` when a
tool-shaped step ticks itself. Words, tool calls, or a turn that looked
productive are all things this loop already refuses to treat as work - it
refuses to PARK on them, and it must not extend on them either.

## Why it is bounded twice

The cap moves by six, so the decision is asked again in six turns and a run
that stops moving stops. And `ABSOLUTE_TURN_CEILING = 96` is the wall no amount
of ticking gets past: "it kept ticking so it kept going" with no ceiling is a
loop that ends when somebody notices rather than when the work does. The
ceiling is what makes this a bound being RAISED rather than a bound removed.
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


def _a_plan(steps: int) -> str:
    """A plan with `steps` open steps, numbered so a tick can name exactly one.

    Long enough that the cap is what ends these runs rather than the plan
    running out - which is the difference between testing the cap and testing
    the checklist.

    ZERO-PADDED, AND THAT IS NOT TIDINESS. `mark_step_done` matches a step by a
    few of its words, so "Step 1" names "Step 1", "Step 10" and "Step 12" at
    once; an ambiguous name is refused, the step does not tick, and the run
    quietly takes one more turn than the case expects. Measured here on the
    first run of this file: 13 turns where 12 were asserted, on a plan of
    twelve. "Step 01" is nobody else's prefix.
    """
    lines = ["# A long job", "", "## Phase 1 - Work"]
    lines += [f"- [ ] Step {n:02d}" for n in range(1, steps + 1)]
    return chr(10).join(lines)


def _turns(script: list[Callable[[int], None]]) -> Callable[[int], Any]:
    """Each entry is one turn; the last entry repeats for every turn after it.

    The same shape as `tests/test_a_long_run_works_the_plan_down.py`'s helper,
    and it is repeated rather than imported because these runs take thirty
    turns and that file's script is written for three.
    """
    taken = {"n": 0}

    def take(thread_id: int):
        index = min(taken["n"], len(script) - 1)
        taken["n"] += 1
        script[index](thread_id)
        yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

    take.taken = taken  # type: ignore[attr-defined]
    return take


def _tick_the_next_step(thread_id: int) -> None:
    """Tick whichever step is open next, THROUGH `mark_step_done`.

    NOT by rewriting the plan text, which is what the sibling file's `_tick`
    does and is right for what it tests. The cap extension reads
    `thread.step_done`, and a fixture that edited the checklist behind the
    harness's back would tick the plan while writing no such row - a run that
    the product would extend and the test would watch stop, or the reverse.
    The tool the model calls is the tool the fixture calls.
    """
    thread = events.get_thread(thread_id) or {}
    open_now = planning.open_steps(planning.checklist_text(thread))
    if open_now:
        planning.mark_step_done(open_now[0]["text"], thread_id)


def _blocked(thread_id: int) -> None:
    """A turn that reports a real blocker and ticks nothing.

    A REASON RATHER THAN NARRATION, because the loop treats "I'll get to it"
    as a turn that says nothing about the step and retries instead of striking.
    This is the shape that strikes - and, for this file, the shape that does
    not move the plan.
    """
    events.append(
        "chat.delta",
        {"text": "The file it needs does not exist, so I cannot do this step."},
        thread_id=thread_id,
    )


def _extensions(thread_id: int) -> list[dict[str, Any]]:
    return [
        row["payload"]
        for row in events.since(f"thread:{thread_id}", limit=5000)
        if row["kind"] == "run.extended"
    ]


class TheNumbersAreTheOnesMaxNamedTest(unittest.TestCase):
    """Read off the module, so a change to one has to be a decision."""

    def test_six_more_turns(self):
        self.assertEqual(6, longrun.CAP_EXTENSION)

    def test_within_the_last_three(self):
        self.assertEqual(3, longrun.PROGRESS_WINDOW)

    def test_a_ceiling_of_ninety_six(self):
        self.assertEqual(96, longrun.ABSOLUTE_TURN_CEILING)

    def test_the_ceiling_is_above_the_cap(self):
        """A ceiling at or below the cap would make the extension unreachable
        and every test here green for the wrong reason."""
        self.assertGreater(longrun.ABSOLUTE_TURN_CEILING, longrun.TURN_CAP)


class ARunThatIsStillMovingCarriesOnTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])

    def test_a_run_ticking_steps_at_the_cap_gets_six_more(self):
        """THE CASE. Three steps ticked, the cap reached, six more turns, and
        the plan finishes instead of being handed back half done."""
        events.set_thread_plan(self.thread, _a_plan(6))
        take = _turns([_tick_the_next_step])
        longrun.start(self.thread, cap=3, background=False, turn=take)

        run = longrun.status(self.thread)
        self.assertEqual("plan_worked_down", run["stop_reason"])
        self.assertEqual(0, run["open"])
        self.assertEqual(6, run["done"])
        self.assertEqual(6, run["turns"])
        self.assertEqual(9, run["cap"], "the cap did not move")

    def test_the_extension_is_an_event_with_its_reason(self):
        """A cap that moved is what somebody asks about when a run took forty
        turns, and a number with no sentence beside it is the log declining to
        answer."""
        events.set_thread_plan(self.thread, _a_plan(6))
        longrun.start(
            self.thread, cap=3, background=False, turn=_turns([_tick_the_next_step])
        )
        rows = _extensions(self.thread)
        self.assertEqual(1, len(rows), rows)
        self.assertEqual(9, rows[0]["cap"])
        self.assertEqual(3, rows[0]["turns"])
        self.assertEqual(3, rows[0]["ticked_on_turn"])
        self.assertIn("still working the plan down", rows[0]["why"])

    def test_it_is_repeatable(self):
        """Six more turns is a question asked again, not an exemption granted.
        Twelve steps, a cap of three: it is asked at 3 and again at 9."""
        events.set_thread_plan(self.thread, _a_plan(12))
        longrun.start(
            self.thread, cap=3, background=False, turn=_turns([_tick_the_next_step])
        )
        run = longrun.status(self.thread)
        self.assertEqual("plan_worked_down", run["stop_reason"])
        self.assertEqual(12, run["turns"])
        self.assertEqual([9, 15], [row["cap"] for row in _extensions(self.thread)])


class ARunThatHasStoppedMovingStopsTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])

    def test_a_run_that_ticked_nothing_stops_at_the_cap(self):
        """THE CONTROL, and the one that matters: the cap still bounds the run
        it was written for. Without this the change would have removed the
        bound and called it an extension."""
        events.set_thread_plan(self.thread, _a_plan(6))
        longrun.start(self.thread, cap=3, background=False, turn=_turns([_blocked]))

        run = longrun.status(self.thread)
        self.assertEqual("turn_cap", run["stop_reason"])
        self.assertEqual(3, run["turns"])
        self.assertEqual(3, run["cap"], "the cap moved for a run going nowhere")
        self.assertEqual([], _extensions(self.thread))

    def test_a_tick_older_than_the_window_does_not_extend(self):
        """Three steps, then three turns that move nothing. At the cap the last
        tick is exactly `PROGRESS_WINDOW` turns back, which is outside a window
        that means "within the last three"."""
        events.set_thread_plan(self.thread, _a_plan(8))
        script = [
            _tick_the_next_step,
            _tick_the_next_step,
            _tick_the_next_step,
            _blocked,
        ]
        longrun.start(self.thread, cap=6, background=False, turn=_turns(script))

        run = longrun.status(self.thread)
        self.assertEqual("turn_cap", run["stop_reason"])
        self.assertEqual(6, run["turns"])
        self.assertEqual(6, run["cap"])
        self.assertEqual([], _extensions(self.thread))

    def test_a_tick_inside_the_window_does_extend(self):
        """THE PAIR TO THE ONE ABOVE, differing by one turn. Without it, a
        window of zero would pass that test and this change would do nothing.
        """
        events.set_thread_plan(self.thread, _a_plan(8))
        script = [
            _tick_the_next_step,
            _tick_the_next_step,
            _tick_the_next_step,
            _tick_the_next_step,
            _blocked,
        ]
        longrun.start(self.thread, cap=6, background=False, turn=_turns(script))
        self.assertEqual(1, len(_extensions(self.thread)))
        self.assertEqual(12, longrun.status(self.thread)["cap"])

    def test_narration_is_not_progress(self):
        """The loop already refuses to PARK on a turn that only talks. It must
        not EXTEND on one either, or the cheapest way for a model to buy
        another six turns is to keep saying things."""
        events.set_thread_plan(self.thread, _a_plan(6))

        def _narrates(thread_id: int) -> None:
            events.append(
                "chat.delta",
                {"text": "I'll get the next step now."},
                thread_id=thread_id,
            )

        longrun.start(self.thread, cap=3, background=False, turn=_turns([_narrates]))
        self.assertEqual([], _extensions(self.thread))


class TheCeilingHoldsTest(unittest.TestCase):
    """No amount of progress climbs past it, and the last step is clamped."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.thread = int(events.create_thread("t", mode="build")["id"])
        #: THE CEILING IS LOWERED FOR THIS CLASS, and the specimen is this
        #: test's own. Reaching the real one means driving ninety-six scripted
        #: turns to assert a comparison and a `min()`; lowering it asserts the
        #: same two things in four. The real value is asserted in
        #: `TheNumbersAreTheOnesMaxNamedTest` above, so the constant cannot
        #: drift while this class stays green.
        self._was = longrun.ABSOLUTE_TURN_CEILING
        longrun.ABSOLUTE_TURN_CEILING = 4
        self.addCleanup(
            lambda: setattr(longrun, "ABSOLUTE_TURN_CEILING", self._was)
        )

    def test_a_run_still_ticking_stops_at_the_ceiling(self):
        events.set_thread_plan(self.thread, _a_plan(20))
        longrun.start(
            self.thread, cap=3, background=False, turn=_turns([_tick_the_next_step])
        )
        run = longrun.status(self.thread)
        self.assertEqual("turn_cap", run["stop_reason"])
        self.assertEqual(4, run["turns"])
        self.assertGreater(run["open"], 0, "the plan ran out before the ceiling did")

    def test_the_last_extension_is_clamped_rather_than_overshooting(self):
        """`cap + 6` past the ceiling would be a cap ABOVE the wall, and the
        wall would then only be a number in a docstring."""
        events.set_thread_plan(self.thread, _a_plan(20))
        longrun.start(
            self.thread, cap=3, background=False, turn=_turns([_tick_the_next_step])
        )
        self.assertEqual([4], [row["cap"] for row in _extensions(self.thread)])
        self.assertEqual(4, longrun.status(self.thread)["cap"])

    def test_the_ending_says_it_was_the_ceiling(self):
        """A run that stopped while it was still working is a different piece
        of news from one that stopped because it stalled, and the person
        reading the card gets to know which."""
        events.set_thread_plan(self.thread, _a_plan(20))
        longrun.start(
            self.thread, cap=3, background=False, turn=_turns([_tick_the_next_step])
        )
        self.assertIn("ceiling", longrun.status(self.thread)["detail"])

    def test_a_stalled_run_is_not_told_about_the_ceiling(self):
        """THE CONTROL ON THE SENTENCE. A run that stopped for the ordinary
        reason must not be handed an explanation about a wall it never met."""
        events.set_thread_plan(self.thread, _a_plan(20))
        longrun.start(self.thread, cap=3, background=False, turn=_turns([_blocked]))
        self.assertNotIn("ceiling", longrun.status(self.thread)["detail"])


if __name__ == "__main__":
    unittest.main()
