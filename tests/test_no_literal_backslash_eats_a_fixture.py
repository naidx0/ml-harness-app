"""A fixture that stopped describing anything real, caught at the character.

FIVE TIMES IN ONE NIGHT on this branch, a literal backslash typed into file
content changed what a test was testing:

  - a Windows path in a docstring where the escape was read
  - a separator that collapsed into a real newline
  - a drive letter followed by "venv" in a process-list fixture, where the
    escape Python read is a VERTICAL TAB
  - "bash.exe" in the same fixture, where the escape Python read is a BACKSPACE
  - and the standing note telling me not to do it, which did not stop the fifth

The fifth is the reason this is a test and not a sixth note. A rule kept in
somebody's memory is not where the hand reads it; a rule the gate enforces is.

WHY THESE CHARACTERS AND NOT "BACKSLASHES". Banning backslashes would be wrong:
carriage-return-and-newline handling is real and this repository does it in
four places on purpose. The signal is narrower and it is deterministic - a string literal
whose VALUE contains a bell, a backspace, a vertical tab, a form feed or an
escape. Nobody writes those into a test fixture deliberately. They arrive one
way: a Windows path typed with real backslashes into a non-raw string, where
the letter after the backslash happened to be one Python knows.

CARRIAGE RETURN IS NOT ON THE LIST. Measured 2026-09-05 across 354 files: six
literals carried one of these characters, and four were carriage-return-newline pairs in
`app/dataquality.py`, `app/main.py` and `app/tools/quarry.py`, doing exactly
what they look like they are doing. The other two were in
`tests/test_a_green_run_says_what_it_ran_beside.py`, both mine, and both had
been "fixed" once already - they survived because that test asserts an EMPTY
result, and corrupted input matches nothing just as well as real input does. A
negative test proving nothing is the family this whole area exists to catch.

WHAT THIS CANNOT SEE. A backslash escape that produces a printable
character stays two characters, and Python's own SyntaxWarning covers that
case already. The gap between them is a backslash before a letter Python knows,
which is precisely the trap, and that is what this holds.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Bell, backspace, vertical tab, form feed, escape. Carriage return (13) and
#: the whitespace everyone means (9 tab, 10 newline) are deliberately absent.
NOBODY_MEANS_THESE = {
    7: "a bell",
    8: "a backspace",
    11: "a vertical tab",
    12: "a form feed",
    27: "an escape",
}

#: `packages` is here because code that leaves this repository should not
#: carry a control character out with it, and eight of these faults have
#: landed on this branch - one of them in product source, where the escape
#: became a real BACKSPACE and the matcher would have matched nothing.
WHERE = ("app", "tests", "scripts", "packages")


def literals_carrying_a_stray_control_character() -> list[str]:
    found = []
    for top in WHERE:
        for path in sorted((REPO / top).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, OSError):  # pragma: no cover - not this file's job
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                for code in sorted({ord(c) for c in node.value} & NOBODY_MEANS_THESE.keys()):
                    found.append(
                        f"{path.relative_to(REPO).as_posix()}:{node.lineno} "
                        f"contains {NOBODY_MEANS_THESE[code]}"
                    )
    return found


#: Text trees scanned WHOLE rather than through the parser. `docs/` holds no
#: Python, so the AST walk above never reached it - and item 69 found two
#: corrupted lines sitting there: a law describing the backspace fault that
#: CONTAINED a real backspace where it meant to quote the escape, and a libuv
#: error path whose `\a` had become a bell.
#:
#: This does NOT reach the whole family and the difference is worth keeping
#: straight. A separator that collapses into a real NEWLINE inside prose is
#: undetectable here, because a newline in markdown is ordinary - that remains
#: the one class caught by neither this nor the parser. What is detectable is
#: the same five characters nobody types on purpose, in a tree nobody was
#: looking at.
PROSE = ("docs",)
PROSE_SUFFIXES = (".md", ".txt", ".yaml", ".yml", ".json", ".jsonl", ".csv")

#: Dated records are read, not rewritten - but a control character in one is
#: still a corrupted record, so they are scanned like everything else. Nothing
#: is excluded here, because unlike the gate-command rule there is no reading
#: on which a bell belongs in a sentence.


def prose_carrying_a_stray_control_character() -> list[str]:
    found = []
    for top in PROSE:
        for path in sorted((REPO / top).rglob("*")):
            if not path.is_file() or path.suffix.lower() not in PROSE_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:  # pragma: no cover
                continue
            # NOT `splitlines()`. IT EATS TWO OF THE FIVE. Python splits on
            # vertical tab and form feed as well as newline, so a scan that
            # looks for characters WITHIN a line can never see those two - they
            # are consumed as line boundaries before the search begins. Found by
            # planting one and watching this pass. So the whole text is
            # searched and the line number is counted from the newlines before
            # the hit.
            for position, character in enumerate(text):
                code = ord(character)
                if code in NOBODY_MEANS_THESE:
                    number = text.count(chr(10), 0, position) + 1
                    found.append(
                        f"{path.relative_to(REPO).as_posix()}:{number} "
                        f"contains {NOBODY_MEANS_THESE[code]}"
                    )
    return found


class NoLiteralBackslashEatsAFixtureTest(unittest.TestCase):
    def test_no_string_literal_carries_a_stray_control_character(self):
        self.assertEqual(
            literals_carrying_a_stray_control_character(),
            [],
            "a string literal contains a control character nobody types on "
            "purpose. It is almost certainly a Windows path written with real "
            "backslashes in a non-raw string - build the path with forward "
            "slashes, or assemble the separator with chr(), and check what the "
            "fixture is now actually asserting.",
        )

    def test_the_check_can_see_the_defect_it_was_written_for(self):
        """A guard is not trusted until it has been seen to fail. The two
        strings below are the exact shapes that got through five times."""
        for text, why in (
            ("C:" + chr(92) + "venv" + chr(92) + "Scripts", "a vertical tab"),
            ("C:/Git/bin/" + chr(92) + "bash.exe", "a backspace"),
        ):
            with self.subTest(why):
                cooked = ast.literal_eval('"' + text.replace('"', '') + '"')
                self.assertTrue(
                    {ord(c) for c in cooked} & NOBODY_MEANS_THESE.keys(),
                    f"the check no longer recognises {why}",
                )

    def test_no_document_carries_a_stray_control_character(self):
        """ITEM 69. The tree no guard was scanning, and it had two.

        One was a law describing the backspace fault that contained a real
        backspace where it meant to quote the escape - the record of the fault
        carrying the fault - and one was a libuv error path whose escape had
        become a bell, so a path a reader might copy was silently wrong.
        """
        self.assertEqual(
            prose_carrying_a_stray_control_character(),
            [],
            "a document contains a control character nobody types on purpose. "
            "It is almost certainly an escape that was eaten on the way in - "
            "check what the sentence was trying to quote.",
        )

    def test_the_prose_scan_reaches_a_real_number_of_documents(self):
        """A scan that walks nothing reports the same zero as a clean tree."""
        found = [
            p for top in PROSE for p in (REPO / top).rglob("*")
            if p.is_file() and p.suffix.lower() in PROSE_SUFFIXES
        ]
        self.assertGreater(len(found), 50)

    def test_it_scans_a_real_number_of_files(self):
        """If a path or a glob breaks, this returns an empty list and reads as
        a pass. The count is what stops silence from looking like health."""
        files = [
            path
            for top in WHERE
            for path in (REPO / top).rglob("*.py")
            if "__pycache__" not in path.parts
        ]
        self.assertGreater(len(files), 300)



#: Source that is NOT Python, where the same accident leaves a raw byte on
#: disk instead of a parsed one in a value.
OTHER_SOURCE = ("frontend/src", "src-tauri/src")
OTHER_SUFFIXES = (".ts", ".tsx", ".rs", ".css", ".html")

#: Tab, newline and carriage return are ordinary whitespace in a source
#: file. Everything else below 0x20 is not.
ORDINARY_WHITESPACE = frozenset({9, 10, 13})


def other_source_files() -> list[Path]:
    """Every non-Python source file, derived from the tree, not listed.

    A hand-written list cannot fail for a file nobody remembered to add,
    and this fault arrives in whatever file somebody was editing.
    """
    found: list[Path] = []
    for top in OTHER_SOURCE:
        root = REPO / top
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if "node_modules" in path.parts:
                continue
            if path.suffix.lower() in OTHER_SUFFIXES:
                found.append(path)
    return found


class NoSourceFileCarriesAControlByteTest(unittest.TestCase):
    r"""The same fault, one language over, where nothing parses it for us.

    The class above reads Python string VALUES, so it needs Python to have
    parsed the file. A TypeScript regex with the same accident never gets
    that treatment: the byte just sits there, the pattern still compiles,
    and it matches something nobody meant.

    TWO REAL ONES, FOUND THE DAY THIS WAS WRITTEN:

    `frontend/src/components/Journey.test.tsx` line 726 had read
    `expect(said).not.toMatch(/<0x08>of \d+<0x08>/)` since 2026-09-09 - both
    word boundaries written as literal BACKSPACE. That pattern cannot match
    ordinary text, so `not.toMatch` passed for every possible input. A test
    that could not fail, green in the suite for two days.

    `frontend/src/lib/markdown.ts` had a horizontal-rule matcher whose
    backreference reached disk as a literal 0x01, so `---` never became a
    rule. That one failed loudly, because a test asserted the block it
    should produce - which is the only reason I went looking for the first.

    THIS DOCSTRING IS RAW ON PURPOSE. The first version of it was not, and
    the class above caught it immediately: prose about a bell, a backspace
    and a form feed, written with the escapes, becomes those characters.
    """

    def test_the_subject_set_is_not_empty(self):
        """A sweep that found nothing to look at proves nothing."""
        self.assertGreater(len(other_source_files()), 100)

    def test_no_control_bytes_in_non_python_source(self):
        offenders = []
        for path in other_source_files():
            raw = path.read_bytes()
            bad = sorted(
                {b for b in raw if b < 32 and b not in ORDINARY_WHITESPACE}
            )
            if not bad:
                continue
            line = raw[: raw.index(bytes([bad[0]]))].count(bytes([10])) + 1
            offenders.append(
                "%s line %d: %s"
                % (
                    path.relative_to(REPO).as_posix(),
                    line,
                    ", ".join("0x%02x" % b for b in bad),
                )
            )
        self.assertEqual(
            offenders,
            [],
            "a control byte in source is almost always an escape eaten on the "
            "way to disk. The regex still compiles; it just matches something "
            "nobody meant, which is why this is a sweep and not a review.",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
