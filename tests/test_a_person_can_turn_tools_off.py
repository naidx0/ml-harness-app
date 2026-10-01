"""A person can switch packs off and cap sub-agents, and it reaches the turn.

Max, 2026-09-14: *"add some UI components which lets you configure the tools -
like how many sub-agents you want to be using, if any at all, often or not
often, and so on, with skills as well."* And, about the same problem in the
same breath: *"make sure the models aren't clouded with too many tools and
guidelines so that they can have free roam in the computer."*

MEASURED on his database that day: thread 73 sent 26,367 tokens of harness
furniture against 3,562 tokens of conversation - 88% of the prompt was this
product talking, of which 12,735 was tool schemas for 44 tools. A switch is
only worth shipping if throwing it actually takes those tokens back, so that
is what this asserts: not that the row was written, but that the turn changes.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import support  # noqa: E402
from app import db, events, settings, subagents  # noqa: E402
from app.tools import blocks  # noqa: E402


class TheSettingsAreTheDefaultsUntilSomebodyChangesThemTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.project = int(db.default_project()["id"])

    def test_a_project_nobody_configured_runs_on_the_defaults(self):
        """Not a null and not an error: what every project ran on before."""
        out = settings.read(self.project)
        self.assertEqual(out["subagents_max"], settings.DEFAULT_SUBAGENTS)
        self.assertEqual(out["packs_off"], [])

    def test_absent_means_unchanged_rather_than_default(self):
        settings.write(self.project, subagents_max=0, packs_off=["data"])
        settings.write(self.project, subagents_max=1)
        out = settings.read(self.project)
        self.assertEqual(out["subagents_max"], 1)
        self.assertEqual(
            out["packs_off"], ["data"],
            "writing one field reset the other, so a person changing the cap "
            "silently turned their tools back on")

    def test_the_cap_is_held_inside_its_range(self):
        self.assertEqual(settings.write(self.project, subagents_max=99)["subagents_max"],
                         settings.MOST_SUBAGENTS)
        self.assertEqual(settings.write(self.project, subagents_max=-3)["subagents_max"], 0)


class SwitchingAPackOffReachesTheTurnTest(unittest.TestCase):
    """The assertion that makes the switch worth shipping."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.project = int(db.default_project()["id"])
        self.thread = int(
            events.create_thread("t", project_id=self.project, mode="build")["id"]
        )

    def test_the_pack_and_its_tools_leave_the_turn(self):
        before = blocks.active(None, thread_id=self.thread)
        self.assertIn("data", before.packs, "the fixture does not offer data to begin with")
        data_tools = set(blocks.tools_in(["data"]))

        settings.write(self.project, packs_off=["data"])

        after = blocks.active(None, thread_id=self.thread)
        self.assertNotIn("data", after.packs)
        self.assertFalse(
            data_tools & set(after.tools),
            "the pack left but its tools stayed, so the schemas are still on "
            "the wire and nothing was given back")
        self.assertLess(len(after.tools), len(before.tools))

    def test_the_core_cannot_be_switched_off(self):
        """A turn with no ledger tools cannot write a plan or tick a step.

        Switching it off would not make the model freer, it would make it mute
        - and the person would read that as the model failing rather than as a
        switch they threw.
        """
        settings.write(self.project, packs_off=list(blocks.CORE) + ["data"])
        after = blocks.active(None, thread_id=self.thread)
        for name in blocks.CORE:
            self.assertIn(name, after.packs, f"{name} is core and was removed")
        self.assertNotIn("data", after.packs, "the non-core pack should still go")

    def test_an_unreadable_setting_fails_open(self):
        """Every pack offered, not none.

        Failing closed would silently take a person's tools away and leave them
        blaming the model for not using them.
        """
        settings.ensure_table()
        with db.session() as connection:
            connection.execute(
                "INSERT INTO project_settings(project_id, subagents_max, packs_off) "
                "VALUES (?, 2, 'not json at all') "
                "ON CONFLICT(project_id) DO UPDATE SET packs_off = excluded.packs_off",
                (self.project,),
            )
        self.assertEqual(settings.read(self.project)["packs_off"], [])
        self.assertIn("data", blocks.active(None, thread_id=self.thread).packs)


class SubAgentsCanBeTurnedOffTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        self.project = int(db.default_project()["id"])
        self.thread = int(
            events.create_thread("t", project_id=self.project, mode="build")["id"]
        )
        events.set_thread_plan(
            self.thread,
            chr(10).join(["# P", "", "## Phase 1 - Data", "- [ ] Carve the eval set"]),
        )

    def test_zero_means_nobody_is_sent_and_it_says_so(self):
        settings.write(self.project, subagents_max=0)
        out = subagents.delegate(self.thread, "Phase 1")
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "subagents_are_off")
        self.assertEqual(out["at_most"], 0)
        self.assertEqual(
            subagents.read(self.thread)["subagents"], [],
            "it refused and started one anyway")

    def test_the_cap_a_person_set_is_the_cap_that_is_enforced(self):
        settings.write(self.project, subagents_max=1)
        self.assertEqual(subagents.at_most_for(self.thread), 1)
        self.assertEqual(subagents.read(self.thread)["at_most"], 1)

    def test_it_falls_back_to_the_constant_when_there_is_no_project(self):
        self.assertEqual(subagents.at_most_for(None), subagents.AT_MOST_RUNNING)


if __name__ == "__main__":
    unittest.main()
