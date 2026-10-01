"""The stylesheets parse, because nothing else in this suite opens them.

## Why this exists, and it is not hypothetical

2026-09-14. A commit landed on main with an unbalanced brace in `shell.css` -
one `}` left behind when a rule above it was cut out. The gate ran 5,393 tests
and every one of them passed, because not one of them reads a stylesheet. The
fault surfaced fifteen minutes later in `vite build`, in the owner's own
checkout, as `[lightningcss minify] Invalid empty selector` - after the gate had
already said green and pushed.

That is the shape worth fixing rather than the brace. A gate that cannot see a
whole language the product ships in will keep letting that language through, and
the next one will not be a brace.

## Why not just run `vite build`

Because it costs about a minute, needs `node_modules` present, and would make
this suite fail for a reason that has nothing to do with a stylesheet - a broken
npm install, a missing binary, a network. What CAN be checked cheaply and
without a toolchain is the property that actually broke: the braces balance, and
no rule is left with an empty selector. Both are pure text, both are what
lightningcss refused, and neither can pass while the file is malformed the way
this one was.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

STYLES = REPO / "frontend" / "src" / "styles"

#: `/* ... */` including newlines. Comments in this codebase are prose and the
#: prose has braces in it - "a `{` in a sentence" - so they come out first or
#: every count below is wrong.
COMMENT = re.compile(r"/\*.*?\*/", re.S)


def sheets() -> list[Path]:
    return sorted(STYLES.glob("*.css"))


class TheStylesheetsParseTest(unittest.TestCase):
    def test_there_are_stylesheets_to_check(self):
        """A guard that cannot fail is worse than no guard: if the styles move,
        this file must go red rather than quietly check nothing."""
        found = sheets()
        self.assertGreater(len(found), 2, f"no stylesheets under {STYLES}")

    def test_every_brace_is_closed(self):
        """THE ONE THAT WOULD HAVE CAUGHT IT. An extra `}` ends the rule that
        contains it, and everything after reads as a selector until the parser
        meets something that cannot be one."""
        for sheet in sheets():
            with self.subTest(sheet=sheet.name):
                body = COMMENT.sub("", sheet.read_text(encoding="utf-8"))
                opens, closes = body.count("{"), body.count("}")
                self.assertEqual(
                    opens, closes,
                    f"{sheet.name} has {opens} '{{' and {closes} '}}'. An "
                    "unbalanced brace fails `vite build` with an invalid "
                    "selector, which no other test in this suite can see.")

    def test_no_rule_has_an_empty_selector(self):
        """The other half of what lightningcss refused: `{` with nothing in
        front of it, which is what a stray `}` leaves behind."""
        for sheet in sheets():
            with self.subTest(sheet=sheet.name):
                body = COMMENT.sub("", sheet.read_text(encoding="utf-8"))
                depth = 0
                selector: list[str] = []
                for index, character in enumerate(body):
                    if character == "{":
                        if depth == 0 and not "".join(selector).strip():
                            line = body[:index].count("\n") + 1
                            self.fail(
                                f"{sheet.name} line {line}: a rule opens with "
                                "no selector in front of it.")
                        depth += 1
                        selector = []
                    elif character == "}":
                        depth = max(0, depth - 1)
                        selector = []
                    elif depth == 0:
                        selector.append(character)

    def test_the_braces_never_go_negative(self):
        """A file that closes more than it opened is malformed even when the
        totals happen to match, which is the case a pure count would miss."""
        for sheet in sheets():
            with self.subTest(sheet=sheet.name):
                body = COMMENT.sub("", sheet.read_text(encoding="utf-8"))
                depth = 0
                for index, character in enumerate(body):
                    if character == "{":
                        depth += 1
                    elif character == "}":
                        depth -= 1
                        if depth < 0:
                            line = body[:index].count("\n") + 1
                            self.fail(
                                f"{sheet.name} line {line}: a '}}' with no rule "
                                "open. Something above it was cut out and its "
                                "closing brace was left behind.")


if __name__ == "__main__":
    unittest.main()
