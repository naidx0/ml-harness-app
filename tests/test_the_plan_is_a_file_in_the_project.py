"""The plan is a markdown file in the project folder, and the file wins.

Max, 2026-09-12: *"the plan should be saved local first as well so that it
previews on the rail but is source of truth md in the file in that chat."*
And, the same evening: *"I switched from plan to build, and the plan
disappeared"* - Build saved the last reply over the plan column.

`app/planfile.py`: every write of the column mirrors to
`<root>/harness-plans/thread-<id>-plan.md`; every read that matters adopts the
file when it changed since the harness wrote it. No folder, no file, no error.
"""
from __future__ import annotations

import os
import sys
import time
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

PLAN = "# Router\n\n## Phase 1 - Data\n- [ ] Carve the eval set\n\n## Phase 2 - Baseline\n- [ ] Measure the baseline\n"


class MirrorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        (self.root / "proj").mkdir()
        self.project = db.create_project("Router", root_path=str(self.root / "proj"))
        self.thread = int(events.create_thread("t", project_id=self.project["id"], mode="plan")["id"])

    def path(self) -> Path:
        return self.root / "proj" / "harness-plans" / f"thread-{self.thread}-plan.md"

    def test_the_column_is_written_to_the_file(self):
        events.set_thread_plan(self.thread, PLAN)
        self.assertTrue(self.path().is_file())
        self.assertEqual(self.path().read_text(encoding="utf-8").rstrip(), PLAN.rstrip())
        self.assertEqual(planfile.sync(events.get_thread(self.thread))["plan_path"], str(self.path()))

    def test_write_plan_and_a_tick_both_reach_the_file(self):
        out = REGISTRY.call("write_plan", {"plan": PLAN}, actor=evidence.MODEL, thread_id=self.thread)
        self.assertTrue(out["ok"], out)
        self.assertIn("- [ ] Carve the eval set", self.path().read_text(encoding="utf-8"))
        events.set_thread_mode(self.thread, "build")
        REGISTRY.call("mark_step_done", {"step": "carve the eval set"}, actor=evidence.MODEL, thread_id=self.thread)
        self.assertIn("- [x] Carve the eval set", self.path().read_text(encoding="utf-8"))

    def test_an_edit_to_the_file_is_adopted_on_read(self):
        events.set_thread_plan(self.thread, PLAN)
        edited = PLAN.replace("Measure the baseline", "Measure the baseline on 40 rows")
        # A later mtime, so the stamp differs even on a coarse filesystem clock.
        self.path().write_text(edited, encoding="utf-8")
        later = time.time() + 5
        os.utime(self.path(), (later, later))
        row = planfile.sync(events.get_thread(self.thread))
        self.assertIn("on 40 rows", row["plan"])
        self.assertIn("on 40 rows", events.get_thread(self.thread)["plan"])
        kinds = [r["kind"] for r in events.since(f"thread:{self.thread}", limit=100)]
        self.assertIn("thread.plan_adopted", kinds)
        # And the adoption is recorded, so the next read adopts nothing again.
        again = planfile.sync(events.get_thread(self.thread))
        self.assertEqual(again["plan"], row["plan"])
        self.assertEqual(kinds.count("thread.plan_adopted"), 1)

    def test_read_plan_sees_the_file_edit(self):
        events.set_thread_plan(self.thread, PLAN)
        self.path().write_text(PLAN + "\n## Phase 3 - Ship\n- [ ] Ship it\n", encoding="utf-8")
        later = time.time() + 5
        os.utime(self.path(), (later, later))
        out = REGISTRY.call("read_plan", {}, actor=evidence.MODEL, thread_id=self.thread)
        self.assertIn("Ship it", out["plan"])

    def test_a_plan_from_before_the_file_existed_is_written_on_first_read(self):
        events.set_thread_plan(self.thread, PLAN, mirror=False)
        self.assertFalse(self.path().exists())
        row = planfile.sync(events.get_thread(self.thread))
        self.assertTrue(self.path().is_file())
        self.assertEqual(row["plan_path"], str(self.path()))
        self.assertIn("Carve the eval set", self.path().read_text(encoding="utf-8"))

    def test_clearing_the_plan_removes_the_file(self):
        events.set_thread_plan(self.thread, PLAN)
        events.set_thread_plan(self.thread, None)
        self.assertFalse(self.path().exists())

    def test_deleting_the_thread_leaves_the_file_and_forgets_the_record(self):
        events.set_thread_plan(self.thread, PLAN)
        out = events.delete_thread(self.thread)
        self.assertEqual(out["removed"].get("plan_files"), 1)
        self.assertTrue(self.path().is_file(), "the folder is the person's; nothing on disk is touched")


class NoFolderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)

    def test_no_folder_no_file_no_error(self):
        thread = int(events.create_thread("t", mode="plan")["id"])
        row = events.set_thread_plan(thread, PLAN)
        self.assertEqual(row["plan"].rstrip(), PLAN.rstrip())
        self.assertIsNone(planfile.sync(events.get_thread(thread))["plan_path"])

    def test_a_folder_that_is_gone_is_no_folder(self):
        project = db.create_project("Gone", root_path=str(self.root / "missing"))
        thread = int(events.create_thread("t", project_id=project["id"], mode="plan")["id"])
        events.set_thread_plan(thread, PLAN)
        self.assertIsNone(planfile.path_for(events.get_thread(thread)))


class OverHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        from app.main import app

        self.client = support.api_client(app)
        self.addCleanup(self.client.close)
        (self.root / "proj").mkdir()
        self.project = db.create_project("Router", root_path=str(self.root / "proj"))
        self.thread = int(events.create_thread("t", project_id=self.project["id"], mode="plan")["id"])

    def test_the_thread_route_names_the_file_and_adopts_an_edit(self):
        events.set_thread_plan(self.thread, PLAN)
        path = self.root / "proj" / "harness-plans" / f"thread-{self.thread}-plan.md"
        got = self.client.get(f"/api/threads/{self.thread}").json()["thread"]
        self.assertEqual(got["plan_path"], str(path))
        path.write_text(PLAN.replace("Router", "Router v2"), encoding="utf-8")
        later = time.time() + 5
        os.utime(path, (later, later))
        got = self.client.get(f"/api/threads/{self.thread}").json()["thread"]
        self.assertIn("Router v2", got["plan"])


if __name__ == "__main__":
    unittest.main()
