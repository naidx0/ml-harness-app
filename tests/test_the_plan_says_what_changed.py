"""A plan change records what it changed, not just that it happened.

Max, 2026-09-14: *"We should have the file diff - when the agent reads or
writes anything and does any change, like adding to the plan, we should have
that diff as an expandable feature to our thing."*

`thread.plan_written` used to carry `phases`, `characters`, `headings` and
`steps_open`. Every one of those is true, and a rewrite that fixed a typo and a
rewrite that replaced every step produce the same four numbers. The question a
person has is what the model just did to their plan, and nothing on the event
could answer it.

WHY THE ENGINE RECORDS IT RATHER THAN THE BROWSER COMPUTING IT: the transcript
holds messages and tool rows, not the plan's history. To draw "what changed"
after the fact something would have to rebuild every intermediate version of
the document from the event log. The change is known exactly once, by the code
making it, one line before the old text stops existing.
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
from app import events, plandiff  # noqa: E402
from app.tools import planning  # noqa: E402

NL = chr(10)


class TheDiffReadsLikeAPlanTest(unittest.TestCase):
    BEFORE = NL.join(
        [
            "# Train the router",
            "",
            "## Phase 1 - Data",
            "- [ ] Carve the eval set",
            "- [ ] Measure the baseline",
        ]
    )

    def test_a_ticked_step_is_one_line_out_and_one_in(self):
        after = self.BEFORE.replace("- [ ] Carve", "- [x] Carve")
        change = plandiff.rows_between(self.BEFORE, after)
        self.assertEqual((change["added"], change["removed"]), (1, 1))
        kinds = [row["kind"] for row in change["rows"]]
        self.assertIn("del", kinds)
        self.assertIn("add", kinds)

    def test_an_added_step_is_one_line_in_and_none_out(self):
        after = self.BEFORE + NL + "- [ ] Compare the adapter"
        change = plandiff.rows_between(self.BEFORE, after)
        self.assertEqual((change["added"], change["removed"]), (1, 0))
        added = [row for row in change["rows"] if row["kind"] == "add"]
        self.assertEqual(added[0]["text"], "- [ ] Compare the adapter")
        #: An added line exists only in the new document, so it has no old
        #: number. Zero would be a line that is not there.
        self.assertIsNone(added[0]["old"])
        self.assertEqual(added[0]["cur"], 6)

    def test_a_write_that_changes_nothing_reports_nothing(self):
        """The one that stops a notice claiming a change it did not make.

        `park_step` on a step that matches nothing writes the plan back
        unchanged, and its event must not then draw an empty diff card.
        """
        change = plandiff.rows_between(self.BEFORE, self.BEFORE)
        self.assertEqual(change["rows"], [])
        self.assertEqual((change["added"], change["removed"]), (0, 0))

    def test_the_first_plan_is_all_addition(self):
        change = plandiff.rows_between(None, self.BEFORE)
        self.assertEqual(change["removed"], 0)
        self.assertEqual(change["added"], len(self.BEFORE.splitlines()))

    def test_unchanged_runs_are_cut_to_context(self):
        """A diff exists to leave out the middle of what did not change."""
        before = NL.join(f"- [ ] Step {n}" for n in range(40))
        after = before + NL + "- [ ] Step 40"
        change = plandiff.rows_between(before, after)
        self.assertLess(
            len(change["rows"]), 12,
            "the whole unchanged document came through - the context window is "
            "not being applied, and the event will carry the entire plan.")

    def test_it_is_bounded_because_events_are_replayed_in_full(self):
        """A payload that can be arbitrarily large is one that will be."""
        before = NL.join(f"- [ ] old {n}" for n in range(300))
        after = NL.join(f"- [ ] new {n}" for n in range(300))
        change = plandiff.rows_between(before, after)
        self.assertLessEqual(len(change["rows"]), plandiff.MOST_ROWS)
        self.assertGreater(
            change["clipped"], 0,
            "rows were cut and the payload does not say so, which is a diff "
            "that lies about being complete.")

    def test_a_very_long_line_is_clipped_rather_than_carried(self):
        long = "- [ ] " + ("x" * 2000)
        change = plandiff.rows_between("", long)
        self.assertLessEqual(len(change["rows"][0]["text"]), plandiff.LONGEST_LINE)


class TheEventCarriesItTest(unittest.TestCase):
    """The wiring, driven rather than asserted: write a plan, tick a step, and
    read what the engine actually put on the events."""

    def setUp(self) -> None:
        support.sandbox(self)

    def test_writing_and_ticking_both_record_their_change(self):
        thread = events.create_thread("a plan that changes", mode="build")
        tid = int(thread["id"])

        first = NL.join(
            ["# Goal", "", "## Phase 1", "- [ ] Read the machine with inspect_hardware"]
        )
        planning.write_plan(first, thread_id=tid)
        written = [
            row for row in events.since(f"thread:{tid}", after=0, limit=500)
            if row["kind"] == "thread.plan_written"
        ]
        self.assertTrue(written, "no plan_written event")
        self.assertIn("diff", written[-1]["payload"])
        self.assertGreater(written[-1]["payload"]["diff"]["added"], 0)

        planning.mark_step_done("Read the machine", thread_id=tid)
        ticked = [
            row for row in events.since(f"thread:{tid}", after=0, limit=500)
            if row["kind"] == "thread.step_done"
        ]
        self.assertTrue(ticked, "no step_done event")
        change = ticked[-1]["payload"].get("diff")
        self.assertIsNotNone(change, "a ticked step recorded no diff")
        self.assertEqual((change["added"], change["removed"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
