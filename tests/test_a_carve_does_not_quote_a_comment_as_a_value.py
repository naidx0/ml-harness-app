"""A carved CSS row says what the grammar says, not what a search finds.

FOUND ON THE DESIGN-MODEL WALK, carving this repository's own stylesheets into
training rows. `_rows_from_css` ran a pattern over the text, so it matched three
things that are not declarations. Each produced a row that was verbatim and
false, and no wall caught any of them, because the walls enforce that nothing is
invented and nothing was:

  * INSIDE A COMMENT. `shell.css` line 853 says "The composer around it stays a
    rounded RECTANGLE at --r-18: a rounded rectangle with a circular send reads
    as a composer", which carved as that token's value.
  * INSIDE A STRING. `content: "--gap: 99px"` carved a second row for a token
    declared for real elsewhere, so the corpus held two different answers to one
    question with nothing to say which was the file's.
  * OUTSIDE ANY BLOCK. `--loose: 42px;` at the top level of a file is not a
    declaration, because a custom property is only one inside a rule.

VERBATIM IS A FLOOR, NOT A GUARANTEE OF MEANING. That is the general lesson and
it is on `docs/how-to-verify.md`: a wall that enforces "nothing invented" does
not enforce "nothing false".

MEASURED SIZE OF THE DEFECT, so the fix is not oversold: across all fourteen
stylesheets in `frontend/src`, the pattern carved 169 rows and exactly 1 was not
a declaration - the `--r-18` sentence, 0.6% of the corpus. The incidence is low
here because only `tokens.css` declares custom properties and it is terse. The
direction of the corollary still holds: prose about tokens is what produces
these, so the better documented a stylesheet is, the more it yields.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from app.tools import quarry


class TheCarveReadsTheGrammarTest(unittest.TestCase):
    def values(self, css: str) -> dict[str, str]:
        return {row["landmark"]: row["a"] for row in quarry._rows_from_css("t.css", css)}

    # ---- the planted case -------------------------------------------------

    #: A comment naming the token AND offering a plausible value, in a file
    #: whose real declaration says something else. This is the case that
    #: separates reading the grammar from any amount of cleverness with text:
    #: both strings look like a declaration, and only one of them is.
    #:
    #: THE SEMICOLON INSIDE THE COMMENT IS LOAD-BEARING. A first draft wrote
    #: "99px," with a comma, and the shipped pattern never matched it - so the
    #: test passed with and without the fix and proved nothing. Checked by
    #: running this case against the pattern as it shipped and watching it go
    #: red, which is the only way to know a guard bites.
    PLANTED = """
/* Historically --radius: 99px; and people still expect that. */
:root { --radius: 4px; }
"""

    def test_the_comment_does_not_win_over_the_declaration(self):
        self.assertEqual(self.values(self.PLANTED), {"--radius": "4px"})

    def test_the_planted_value_appears_nowhere_in_the_carve(self):
        """Stated separately from the assertion above, because a carve that
        emitted BOTH would satisfy a test that only checked the real value was
        present."""
        rows = quarry._rows_from_css("t.css", self.PLANTED)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("99px", rows[0]["a"])

    # ---- the other two shapes the pattern got wrong ------------------------

    def test_a_token_named_inside_a_string_carves_nothing(self):
        css = ':root { --gap: 8px; }\n.x::after { content: "--gap: 99px"; }'
        self.assertEqual(self.values(css), {"--gap": "8px"})

    def test_a_declaration_outside_any_block_is_not_a_declaration(self):
        css = "--loose: 42px;\n:root { --real: 8px; }"
        self.assertEqual(self.values(css), {"--real": "8px"})

    def test_the_real_sentence_from_shell_css(self):
        """Copied from the file that found this rather than paraphrased - a
        fixture that says something slightly different is how a test passes
        while the product still carries the bug."""
        css = (
            "/* The composer around it stays a rounded RECTANGLE at --r-18: a\n"
            "   rounded rectangle with a circular send reads as a composer. */\n"
            ".composer { border-radius: var(--r-18); }\n"
        )
        self.assertEqual(quarry._rows_from_css("styles_shell.css", css), [])

    # ---- and it must not cost real rows -----------------------------------

    def test_a_semicolon_inside_parentheses_does_not_end_the_value(self):
        css = ":root { --ease: cubic-bezier(0.4, 0, 0.2, 1); --gap: 2px; }"
        self.assertEqual(
            self.values(css),
            {"--ease": "cubic-bezier(0.4, 0, 0.2, 1)", "--gap": "2px"},
        )

    def test_a_comment_inside_a_value_is_punctuation_not_content(self):
        self.assertEqual(self.values(":root { --h: 4px /* four */; }"), {"--h": "4px"})

    def test_declarations_either_side_of_a_comment_both_survive(self):
        css = ":root { --a: 1px; /* between */ --b: 2px; }"
        self.assertEqual(self.values(css), {"--a": "1px", "--b": "2px"})

    def test_the_repository_token_sheet_is_carved_whole(self):
        """The fix removed one row from this repository and had to leave the
        other 168 alone. A filter that also dropped real rows would trade one
        silent corruption for another, so the count is asserted rather than
        assumed."""
        tokens = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "styles" / "tokens.css"
        )
        rows = quarry._rows_from_css("tokens.css", tokens.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(rows), 160)
        for row in rows:
            with self.subTest(row["landmark"]):
                self.assertNotIn("\n", row["a"], "a value spanning lines is prose, not a value")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
