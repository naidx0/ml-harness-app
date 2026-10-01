"""One plan the folder holds, so a new session does not start from nothing.

Max, 2026-09-18: *"trouble sharing a journey and plan within one folder and
between sessions."*

A thread's plan lives and dies with the thread. Open a new chat about the same
work and the document is gone - the person types it again, or a small model
writes a worse one (thread 75, 2026-09-17: eight phases, no steps). The folder
is what outlives a session, so `app/planfile.py` gives the folder a plan:
`<root>/harness-plans/project-plan.md`.

The four ways this could go wrong, and each is asserted below:

1. IT IS NEVER WRITTEN TWICE BY THE HARNESS. The first plan saved in a folder
   becomes the folder's; after that the file is the person's, and a second
   thread's edits do not touch it.
2. A NEW CONVERSATION ADOPTS A COPY, OPEN. Ticks and parks reset, because what
   is shared is the work and not somebody else's record of having done it.
3. NOTHING LEAKS. Thread A editing its plan changes A's file. The adopted copy
   in B is B's.
4. NO FOLDER, NO FILE, NO ERROR - the rule the module has had since it was
   written, extended to the new file.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import db, events, planfile  # noqa: E402
from app.tools import evidence, planning  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402

PLAN = chr(10).join(
    [
        "# Router",
        "",
        "## Phase 1 - Data",
        "**Tools:** `carve_eval_set`",
        "- [ ] Carve the eval set with `carve_eval_set`",
        "",
        "## Phase 2 - Baseline",
        "**Tools:** `measure_baseline`",
        "- [ ] Measure the baseline with `measure_baseline`",
        "",
    ]
)


class ProjectPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        (self.root / "proj").mkdir()
        self.project = db.create_project("Router", root_path=str(self.root / "proj"))
        self.first = int(
            events.create_thread("first", project_id=self.project["id"], mode="plan")["id"]
        )

    def shared(self) -> Path:
        return self.root / "proj" / "harness-plans" / "project-plan.md"

    # -- 1: mirrored on the first write, and only then ----------------------

    def test_the_first_plan_written_becomes_the_project_plan(self) -> None:
        self.assertFalse(self.shared().exists())
        events.set_thread_plan(self.first, PLAN)
        self.assertTrue(self.shared().is_file())
        self.assertEqual(self.shared().read_text(encoding="utf-8").rstrip(), PLAN.rstrip())

    def test_a_later_write_does_not_touch_the_project_plan(self) -> None:
        events.set_thread_plan(self.first, PLAN)
        events.set_thread_plan(self.first, PLAN.replace("Router", "Router v2"))
        self.assertNotIn("Router v2", self.shared().read_text(encoding="utf-8"))
        own = self.root / "proj" / "harness-plans" / f"thread-{self.first}-plan.md"
        self.assertIn("Router v2", own.read_text(encoding="utf-8"))

    # -- 2: a new conversation adopts a copy, open -------------------------

    def test_a_new_conversation_adopts_the_project_plan_with_the_ticks_reset(self) -> None:
        events.set_thread_plan(self.first, PLAN)
        planning.tick_step(self.first, "carve the eval set", by="test")
        planning.park_step(self.first, "measure the baseline", "no model connected")
        # The project plan is the FIRST write, so it is still all open - and
        # the adoption resets anyway, which is what this asserts.
        second = events.create_thread("second", project_id=self.project["id"], mode="plan")
        steps = planning.steps_in(second["plan"] or "")
        self.assertEqual([s["state"] for s in steps], ["open", "open"])
        self.assertIn("Carve the eval set", second["plan"])
        rows = events.since(f"thread:{int(second['id'])}", limit=50)
        adopted = [r["payload"] for r in rows if r["kind"] == "thread.plan_adopted"]
        self.assertEqual(len(adopted), 1, rows)
        self.assertEqual(adopted[0]["source"], "project")
        self.assertEqual(adopted[0]["path"], str(self.shared()))

    def test_a_ticked_project_plan_is_adopted_open(self) -> None:
        ticked = PLAN.replace("- [ ] Carve", "- [x] Carve")
        self.shared().parent.mkdir(parents=True, exist_ok=True)
        self.shared().write_text(ticked, encoding="utf-8")
        third = events.create_thread("third", project_id=self.project["id"], mode="plan")
        self.assertEqual(
            [s["state"] for s in planning.steps_in(third["plan"] or "")],
            ["open", "open"],
        )

    def test_a_sub_agent_gets_its_phase_and_never_the_folder_s_plan(self) -> None:
        events.set_thread_plan(self.first, PLAN)
        from app import subagents

        out = subagents.delegate(
            self.first,
            "Phase 1",
            background=False,
            run=lambda child_id, **kw: {"ok": True},
        )
        self.assertTrue(out["ok"], out)
        child_id = int(out["child_thread_id"])
        child = events.get_thread(child_id)
        self.assertNotIn("Phase 2 - Baseline", child["plan"])
        # And no row claiming it adopted one, which is the half a later reader
        # would be misled by.
        kinds = [r["kind"] for r in events.since(f"thread:{child_id}", limit=50)]
        self.assertNotIn("thread.plan_adopted", kinds)

    def test_a_conversation_that_already_has_a_plan_adopts_nothing(self) -> None:
        events.set_thread_plan(self.first, PLAN)
        mine = "# Mine" + chr(10) + chr(10) + "- [ ] Do it my way" + chr(10)
        second = events.create_thread("second", project_id=self.project["id"], mode="plan")
        events.set_thread_plan(int(second["id"]), mine)
        third = events.create_thread("third", project_id=self.project["id"], mode="plan")
        self.assertIn("Carve the eval set", third["plan"])
        self.assertNotIn("my way", third["plan"])

    # -- 3: what one conversation does stays in it -------------------------

    def test_an_edit_in_one_conversation_does_not_reach_the_other(self) -> None:
        events.set_thread_plan(self.first, PLAN)
        second = events.create_thread("second", project_id=self.project["id"], mode="plan")
        second_id = int(second["id"])
        events.set_thread_plan(second_id, (second["plan"] or "") + "- [ ] Ship it" + chr(10))
        self.assertNotIn("Ship it", events.get_thread(self.first)["plan"])
        self.assertNotIn("Ship it", self.shared().read_text(encoding="utf-8"))
        planning.tick_step(self.first, "carve the eval set", by="test")
        self.assertNotIn(
            "- [x]", events.get_thread(second_id)["plan"]
        )

    def test_editing_the_project_plan_changes_only_what_is_adopted_next(self) -> None:
        events.set_thread_plan(self.first, PLAN)
        self.shared().write_text(
            PLAN.replace("Carve the eval set", "Carve the eval set on 40 rows"),
            encoding="utf-8",
        )
        self.assertNotIn("40 rows", events.get_thread(self.first)["plan"])
        later = events.create_thread("later", project_id=self.project["id"], mode="plan")
        self.assertIn("40 rows", later["plan"])

    # -- the model's door --------------------------------------------------

    def test_read_plan_can_ask_for_the_project_scope(self) -> None:
        events.set_thread_plan(self.first, PLAN)
        second = int(
            events.create_thread("second", project_id=self.project["id"], mode="plan")["id"]
        )
        events.set_thread_plan(second, (PLAN + "- [ ] Ship it" + chr(10)))
        out = REGISTRY.call(
            "read_plan", {"scope": "project"}, actor=evidence.MODEL, thread_id=second
        )
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["scope"], "project")
        self.assertTrue(out["has_plan"])
        self.assertNotIn("Ship it", out["plan"])
        self.assertEqual(out["path"], str(self.shared()))
        # And the default is still this conversation's own plan.
        mine = REGISTRY.call("read_plan", {}, actor=evidence.MODEL, thread_id=second)
        self.assertEqual(mine["scope"], "thread")
        self.assertIn("Ship it", mine["plan"])


class NoFolderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)

    def test_a_project_with_no_folder_writes_nothing_and_adopts_nothing(self) -> None:
        thread = events.create_thread("t", mode="plan")
        self.assertIsNone(thread["plan"])
        events.set_thread_plan(int(thread["id"]), PLAN)
        self.assertIsNone(planfile.project_path_for(events.get_thread(int(thread["id"]))))
        self.assertEqual(
            planfile.project_plan(events.get_thread(int(thread["id"])))["plan"], ""
        )
        second = events.create_thread("second", mode="plan")
        self.assertIsNone(second["plan"])

    def test_a_folder_that_is_gone_is_no_folder(self) -> None:
        project = db.create_project("Gone", root_path=str(self.root / "missing"))
        thread = events.create_thread("t", project_id=project["id"], mode="plan")
        self.assertIsNone(thread["plan"])
        events.set_thread_plan(int(thread["id"]), PLAN)
        self.assertFalse((self.root / "missing").exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
