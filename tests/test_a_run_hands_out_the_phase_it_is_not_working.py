"""A run gives away the phase it is not aiming at, and keeps working its own.

Max, 2026-09-18: *"it's not using any sub agents."*

MEASURED that day on his database: `delegate_phase` had been called ZERO times
on a real thread. The machinery has worked since 2026-09-13
(`tests/test_one_phase_one_sub_agent.py`); nothing ever opened the door,
because the door was a tool call a small model had to think of making in the
middle of a step.

A run knows what the model has to work out: which step it is aiming at, so
which phase is being worked, and - off the plan's own `**Tools:**` lines -
which other phase cannot collide with it. `app/longrun.py` hands that one out
before the turn aims.

Five claims, each one a way this could be worse than not doing it:

1. A SECOND PHASE WITH DISJOINT TOOLS GOES OUT ON THE FIRST TURN.
2. AN OVERLAPPING PHASE DOES NOT. Two agents on one tool is the collision the
   parent's own wait exists to avoid.
3. A CAP OF ZERO IS OFF. `app/settings.py` - *"if any at all"*.
4. THE SAME PHASE IS NEVER HANDED OUT TWICE, across turns and across states.
5. THE PARENT STILL WORKS ITS OWN AIMED PHASE. A run that delegated and then
   waited would have spent a sub-agent to do less.

Every turn below is scripted and every delegation is a stand-in, for the reason
`tests/test_a_long_run_works_the_plan_down.py` gives: the only way to assert
what the loop does rather than what a model did.
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
from app import events, longrun, settings, subagents  # noqa: E402
from app.tools import planning  # noqa: E402

DISJOINT = chr(10).join(
    [
        "# Train the router",
        "",
        "## Phase 1 - Data",
        "**Tools:** `carve_eval_set`, `measure_eval_set`",
        "- [ ] Carve the eval set with `carve_eval_set`",
        "",
        "## Phase 2 - Hardware",
        "**Tools:** `inspect_hardware`",
        "- [ ] Read this machine with `inspect_hardware`",
        "",
    ]
)

OVERLAPPING = DISJOINT.replace(
    "**Tools:** `inspect_hardware`", "**Tools:** `inspect_hardware`, `carve_eval_set`"
).replace(
    "- [ ] Read this machine with `inspect_hardware`",
    "- [ ] Read this machine with `inspect_hardware`" + chr(10)
    + "- [ ] Carve again with `carve_eval_set`",
)

NO_TOOLS_LINE = chr(10).join(
    [
        "# Train the router",
        "",
        "## Phase 1 - Data",
        "- [ ] Carve the eval set with `carve_eval_set`",
        "",
        "## Phase 2 - Hardware",
        "- [ ] Read this machine with `inspect_hardware`",
        "",
    ]
)


def _tick(step: str) -> Callable[[int], None]:
    def act(thread_id: int) -> None:
        planning.tick_step(thread_id, step, by="test")

    return act


def _nothing(thread_id: int) -> None:
    return None


def _turns(script: list[Callable[[int], None]]) -> Callable[..., Any]:
    """One scripted turn per entry, ending the way a real one ends."""

    def take(thread_id: int, scaffold: str | None = None):
        index = min(take.taken["n"], len(script) - 1)  # type: ignore[attr-defined]
        take.taken["n"] += 1  # type: ignore[attr-defined]
        take.aimed.append(  # type: ignore[attr-defined]
            [s["text"] for s in planning.open_steps(
                events.get_thread(thread_id)["plan"] or ""
            )][:1]
        )
        script[index](thread_id)
        yield events.append("stream.end", {"ending": "answered"}, thread_id=thread_id)

    take.taken = {"n": 0}  # type: ignore[attr-defined]
    take.aimed = []  # type: ignore[attr-defined]
    return take


class _Handouts:
    """A stand-in for `subagents.delegate` that records and does not spawn.

    It writes the same `subagents` row the real one writes, because that row is
    the record the run reads to know a phase has already gone out - a fake that
    skipped it would make claim 4 untestable by construction.
    """

    def __init__(self, ok: bool = True) -> None:
        self.calls: list[str] = []
        self.ok = ok

    def __call__(self, thread_id: int, phase: str, **kw: Any) -> dict[str, Any]:
        self.calls.append(phase)
        if not self.ok:
            return {"ok": False, "error": "would_not_start"}
        child = events.create_thread(phase, mode="build")
        subagents.ensure_table()
        from app import db

        with db.session() as connection:
            cursor = connection.execute(
                "INSERT INTO subagents(parent_thread_id, child_thread_id, phase, state) "
                "VALUES (?, ?, ?, ?)",
                (int(thread_id), int(child["id"]), phase, subagents.DONE),
            )
            made = int(cursor.lastrowid)
        return {
            "ok": True,
            "subagent_id": made,
            "child_thread_id": int(child["id"]),
            "phase": phase,
            "steps": [],
            "running": 0,
            "at_most": subagents.at_most_for(thread_id),
        }


class RunDelegationTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        longrun.ensure_table()
        subagents.ensure_table()
        self._look, self._at_most = (
            subagents.LOOK_EVERY_SECONDS,
            subagents.WAIT_AT_MOST_SECONDS,
        )
        subagents.LOOK_EVERY_SECONDS, subagents.WAIT_AT_MOST_SECONDS = 0.01, 0.2
        row = support.conversations(1)[0]
        self.thread = int(row["id"])
        self.project = int(row["project"]["id"])
        events.set_thread_mode(self.thread, "build")

    def tearDown(self) -> None:
        subagents.LOOK_EVERY_SECONDS, subagents.WAIT_AT_MOST_SECONDS = (
            self._look,
            self._at_most,
        )

    def run_with(self, plan: str, script: list[Callable[[int], None]], handouts: _Handouts):
        events.set_thread_plan(self.thread, plan)
        take = _turns(script)
        out = longrun.start(
            self.thread, background=False, turn=take, delegate=handouts
        )
        return out, take

    # -- 1 and 5 -----------------------------------------------------------

    def test_a_disjoint_phase_goes_out_on_the_first_turn(self) -> None:
        handouts = _Handouts()
        self.run_with(DISJOINT, [_tick("Carve the eval set"), _nothing], handouts)
        self.assertEqual(handouts.calls, ["Phase 2 - Hardware"])
        rows = [
            r["payload"]
            for r in events.since(f"thread:{self.thread}", limit=500)
            if r["kind"] == "run.delegated"
        ]
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["phase"], "Phase 2 - Hardware")
        self.assertEqual(rows[0]["tools"], ["inspect_hardware"])

    def test_the_parent_works_its_own_aimed_phase_meanwhile(self) -> None:
        handouts = _Handouts()
        _, take = self.run_with(
            DISJOINT, [_tick("Carve the eval set"), _tick("Read this machine")], handouts
        )
        self.assertEqual(  # type: ignore[attr-defined]
            take.aimed[0], ["Carve the eval set with `carve_eval_set`"]
        )
        plan = events.get_thread(self.thread)["plan"]
        ticked = [s["text"] for s in planning.steps_in(plan) if s["state"] == "done"]
        self.assertTrue(any("Carve the eval set" in step for step in ticked), ticked)

    # -- 2 -----------------------------------------------------------------

    def test_an_overlapping_phase_is_not_handed_out(self) -> None:
        handouts = _Handouts()
        self.run_with(OVERLAPPING, [_tick("Carve the eval set"), _nothing], handouts)
        self.assertEqual(handouts.calls, [])

    def test_a_phase_that_declares_no_tools_is_not_handed_out(self) -> None:
        """Disjointness is a claim about two sets; an empty one is not one."""
        handouts = _Handouts()
        self.run_with(NO_TOOLS_LINE, [_tick("Carve the eval set"), _nothing], handouts)
        self.assertEqual(handouts.calls, [])

    # -- 3 -----------------------------------------------------------------

    def test_a_cap_of_zero_hands_out_nothing(self) -> None:
        settings.write(self.project, subagents_max=0)
        handouts = _Handouts()
        self.run_with(DISJOINT, [_tick("Carve the eval set"), _nothing], handouts)
        self.assertEqual(handouts.calls, [])

    def test_a_full_cap_hands_out_nothing_more(self) -> None:
        settings.write(self.project, subagents_max=1)
        # One already working, anywhere on the machine, is the cap.
        other = events.create_thread("somebody else's child", mode="build")
        from app import db

        with db.session() as connection:
            connection.execute(
                "INSERT INTO subagents(parent_thread_id, child_thread_id, phase, state) "
                "VALUES (?, ?, ?, ?)",
                (int(other["id"]) + 1000, int(other["id"]), "Theirs", subagents.RUNNING),
            )
        handouts = _Handouts()
        self.run_with(DISJOINT, [_tick("Carve the eval set"), _nothing], handouts)
        self.assertEqual(handouts.calls, [])

    # -- 4 -----------------------------------------------------------------

    def test_a_phase_is_never_handed_out_twice(self) -> None:
        handouts = _Handouts()
        # Four turns that tick nothing: the run keeps aiming at Phase 1's step
        # and would hand Phase 2 out again on every one of them.
        self.run_with(
            DISJOINT, [_nothing, _nothing, _nothing, _tick("Carve the eval set")], handouts
        )
        self.assertEqual(handouts.calls, ["Phase 2 - Hardware"])

    def test_a_sub_agent_hands_nothing_out(self) -> None:
        """One level, and the run loop respects it without asking."""
        events.set_thread_plan(self.thread, DISJOINT)
        subagents.ensure_table()
        from app import db

        with db.session() as connection:
            connection.execute(
                "INSERT INTO subagents(parent_thread_id, child_thread_id, phase, state) "
                "VALUES (?, ?, ?, ?)",
                (9999, int(self.thread), "Phase 1 - Data", subagents.RUNNING),
            )
        handouts = _Handouts()
        longrun.start(
            self.thread,
            background=False,
            turn=_turns([_tick("Carve the eval set"), _nothing]),
            delegate=handouts,
        )
        self.assertEqual(handouts.calls, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
