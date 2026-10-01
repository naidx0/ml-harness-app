"""A carved answer is a thing the file could contain, not a fragment cut in half.

MEASURED 2026-09-05 on this repository's own documents and pages, after the CSS
carver was fixed to read the grammar. The other two carvers had a different
defect of the same family: not a false claim, but an answer truncated at a
character count in the middle of a structure.

  * **Markdown: 13 of 259 sections (5.0%)** ended with an odd number of ```
    fences — a code block that opens and never closes.
  * **HTML: 132 of 342 blocks (38.6%)** ended with a `<` after their last `>` —
    the answer stopping inside an element, like `...<span class="e`.

Every character was verbatim from the file, so no data wall could see it. The
question says "write the section" or "write block N as that file builds it",
and the answer is something that cannot be written or does not parse; a model
trained on it learns to stop mid-fence and mid-tag.

BOTH CUT AT A BOUNDARY OR NOT AT ALL. Repairing the fragment — appending a
fence, closing the element — would be writing what the file does not contain,
which is the line this module holds everywhere else. A section too long to
carve whole is better missing than malformed.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from app.tools import quarry

REPO = Path(__file__).resolve().parents[1]


class ACarvedAnswerIsWholeTest(unittest.TestCase):
    def markdown_rows(self):
        rows = []
        for path in sorted((REPO / "docs").rglob("*.md")):
            rows += quarry._rows_from_markdown(
                path.name, path.read_text(encoding="utf-8", errors="replace")
            )
        return rows

    def html_rows(self):
        rows = []
        for path in sorted(REPO.rglob("*.html")):
            if "node_modules" in str(path):
                continue
            rows += quarry._rows_from_html(
                path.name, path.read_text(encoding="utf-8", errors="replace")
            )
        return rows

    def test_no_markdown_answer_opens_a_fence_it_does_not_close(self):
        rows = self.markdown_rows()
        self.assertTrue(rows, "no markdown carved, so this asserts nothing")
        broken = [r["landmark"] for r in rows if r["a"].count("```") % 2 == 1]
        self.assertEqual(broken, [], f"{len(broken)} of {len(rows)} cut inside a code fence")

    def test_no_html_answer_ends_inside_a_tag(self):
        rows = self.html_rows()
        self.assertTrue(rows, "no html carved, so this asserts nothing")
        broken = [r["q"] for r in rows if r["a"].rfind("<") > r["a"].rfind(">")]
        self.assertEqual(broken, [], f"{len(broken)} of {len(rows)} cut inside a tag")

    # ---- the cutters themselves, on the cases that matter -----------------

    def test_a_section_short_enough_is_returned_whole(self):
        self.assertEqual(quarry._a_section_cut_at("abc", 10), "abc")

    def test_a_cut_that_lands_outside_a_fence_is_taken(self):
        text = "intro\n```\ncode\n```\ntail that runs on and on"
        cut = quarry._a_section_cut_at(text, len(text) - 5)
        self.assertIsNotNone(cut)
        self.assertEqual(cut.count("```") % 2, 0)

    def test_a_cut_that_lands_inside_a_fence_falls_back_to_the_last_balanced_point(self):
        body = "x" * 60 + "\n```\n" + "y" * 400
        cut = quarry._a_section_cut_at(body, 100)
        self.assertIsNotNone(cut)
        self.assertNotIn("```", cut)

    def test_a_section_that_cannot_be_cut_whole_is_dropped_not_repaired(self):
        """No fence closes early enough and what is left is under the floor, so
        there is no honest answer. Appending a fence would be inventing text."""
        self.assertIsNone(quarry._a_section_cut_at("```\n" + "y" * 500, 100))

    def test_a_block_is_cut_after_the_last_complete_tag(self):
        block = "<div>" + "z" * 400 + "</div><span class='x'"
        cut = quarry._a_block_cut_at(block, len(block) - 5)
        self.assertIsNotNone(cut)
        self.assertLessEqual(cut.rfind("<"), cut.rfind(">"))

    def test_a_block_with_nothing_whole_in_it_is_dropped(self):
        self.assertIsNone(quarry._a_block_cut_at("<span class='" + "z" * 50, 20))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
