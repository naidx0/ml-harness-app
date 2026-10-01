"""Guard: the lit ground must cover the viewport, not just the text column.

The three radial washes originally sat on `body`, which is capped at 920px and
centred. The result was a lighter column down the middle of the page with a hard
vertical seam on each side, against the flat `html` background.

Every structural check passed while that was true - the gradients were present,
`background-attachment: fixed` was set, and a computed-style read of `body`
reported three radial-gradients. None of that can tell you the ground stops
partway across the screen. A screenshot could, and did.
"""

import re
import unittest

from app.theme import GLASS_CSS


def _rule(selector: str) -> str:
    """The declaration block for a top-level selector."""
    match = re.search(
        rf"(?:^|\}}|\*/)\s*{re.escape(selector)}\s*\{{(.*?)\}}",
        GLASS_CSS,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"no rule found for {selector!r}")
    return match.group(1)


class ThemeGroundTest(unittest.TestCase):
    def test_html_carries_the_washes(self):
        html = _rule("html")
        self.assertEqual(html.count("radial-gradient"), 3)
        self.assertIn("background-attachment:fixed", html.replace(" ", ""))

    def test_body_does_not_carry_the_washes(self):
        # body is the 920px text column. Painting the ground here is what
        # produced the seam.
        body = _rule("body")
        self.assertNotIn("radial-gradient", body)

    def test_body_stays_the_measured_column(self):
        # The fix must not widen the reading measure as a side effect.
        body = _rule("body")
        self.assertIn("max-width:920px", body.replace(" ", ""))

    def test_the_ground_is_painted_explicitly(self):
        # An artifact composites over whatever the host paints, so the base
        # colour must be stated, not inherited.
        self.assertIn("var(--base)", _rule("html"))


if __name__ == "__main__":
    unittest.main()
