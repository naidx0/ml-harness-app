"""The first screen a stranger sees is reachable.

FOUND BY LOOKING, on a stranger walk at 1440x900. `.empty` centred its panel
with `align-items: center` and had no scroll region. When the panel is taller
than the pane - which it is on any normal window, because the machine card and
the studios table are both on it - centring centres the overflow too: the
content is pushed above the top edge, and `scrollTop` cannot go negative, so
the top is unreachable. Measured before the fix, `.empty__inner` sat at -169px
against a container top of 44. A stranger's first screen began in the middle of
the machine card, with "Let's build" cut off above it and no way to get there.

Why this test is in Python. It asserts a CSS contract, so it belongs with the
frontend suite - except jsdom does not lay out, so the geometry cannot be
asserted there either way, and reading the stylesheet from vitest needs
`@types/node` (`?raw` comes back empty under this config). A new dependency
gets its own step rather than a ride on a bug fix, and this suite already reads
files. The assertion is the same wherever it runs.

What it holds is the property that produced the defect, not the pixels: this
container centres with `margin` on the item and keeps a scroll region, rather
than centring with `align-items` and swallowing the overflow.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SHELL_CSS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "styles" / "shell.css"

#: A CSS comment. Stripped before matching, because the note inside the very
#: rule under test quotes the declaration that caused the defect - a plain text
#: search would match the explanation and report the bug still present.
_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def rule_body(selector: str) -> str:
    """The declarations of one top-level rule, comments removed."""
    css = SHELL_CSS.read_text(encoding="utf-8")
    start = re.search(rf"^\s*{re.escape(selector)}\s*\{{", css, re.M)
    if start is None:  # pragma: no cover - the selector is in the file
        raise AssertionError(f"{selector} is not in shell.css")
    opened = css.index("{", start.start())
    closed = css.index("}", opened)
    return _COMMENT.sub("", css[opened + 1 : closed])


class TheEmptyScreenTest(unittest.TestCase):
    def test_it_keeps_a_scroll_region_so_tall_content_can_be_reached(self):
        self.assertRegex(rule_body(".empty"), r"overflow-y:\s*auto")

    def test_it_does_not_centre_with_align_items_which_swallows_the_overflow(self):
        """The exact declaration that shipped the defect. Centring is still
        wanted; centring in a way that puts content out of reach is not."""
        self.assertNotRegex(rule_body(".empty"), r"align-items:\s*center")

    def test_the_panel_centres_with_margin_which_yields_to_the_scroller(self):
        self.assertRegex(rule_body(".empty__inner"), r"margin-block:\s*auto")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
