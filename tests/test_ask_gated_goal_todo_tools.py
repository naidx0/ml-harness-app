"""CS9: goal/todo tools refuse without an invite; succeed with one."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import events, goal_invite  # noqa: E402
from app.tools import goal_todo  # noqa: E402


class AskGatedGoalTodoTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)
        goal_invite.clear(None)

    def test_write_todo_refuses_without_invite(self) -> None:
        tid = events.create_thread("todo gate")["id"]
        goal_invite.clear(tid)
        out = goal_todo.write_todo("# Todo\n- [ ] one", thread_id=tid)
        self.assertEqual(out.get("error"), "invite_required")
        self.assertIsNone((events.get_thread(tid) or {}).get("todo"))

    def test_write_todo_works_with_invite_and_does_not_mirror_plan(self) -> None:
        tid = events.create_thread("todo ok")["id"]
        events.set_thread_plan(tid, "# Plan\n- [ ] plan step")
        goal_invite.set_invited(tid, True)
        out = goal_todo.write_todo("# Todo\n- [ ] only todo", thread_id=tid)
        self.assertTrue(out.get("ok"))
        row = events.get_thread(tid) or {}
        self.assertIn("only todo", row.get("todo") or "")
        self.assertIn("plan step", row.get("plan") or "")
        goal_invite.clear(tid)

    def test_set_goal_refuses_without_invite(self) -> None:
        tid = events.create_thread("goal gate")["id"]
        out = goal_todo.set_goal("train a router", thread_id=tid)
        self.assertEqual(out.get("error"), "invite_required")

    def test_invite_pack_is_exactly_the_four_goal_todo_tools(self) -> None:
        """Reachability for `intent` is the invite door, not a diagnosis sheet."""
        from app.tools import blocks

        names = set(blocks.tools_in(frozenset({"intent"})))
        self.assertEqual(
            names,
            {"set_goal", "clear_goal", "write_todo", "clear_todo"},
        )
        # CORE alone never includes intent — invite is the only widen.
        self.assertNotIn("intent", blocks.CORE)


if __name__ == "__main__":
    unittest.main()
