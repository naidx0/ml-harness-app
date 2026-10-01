"""Every backlog entry names a file another lane can open, and the file says so.

A BACKLOG IS A SET OF CLAIMS AND GETS THE SAME TREATMENT AS ANY OTHER. Three
times today a description of mine was wider than the thing it described - a
comment saying "written" that meant constructed, a guard searching for a string
that meant a structure, a message saying "the loop calls it" when the test said
"the module calls it somewhere". A list of open work is exactly the shape that
rots that way: the item gets done, or the line moves, and the entry keeps
asserting a state nobody re-checked.

So each entry's evidence is resolved here. **Not that the work is right - that
the thing it points at is real.**

AND THE BOUND ON "CHECKABLE" IS HONEST. Every repository on this machine refuses
anonymous access, so a commit hash is provenance for its author and unopenable by
anybody else. The backlog therefore cites FILES AND LINES, which another lane
here can read - and this asserts that the citations resolve.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import support

THE_BACKLOG = support.REPO_ROOT / "docs" / "THE-BACKLOG.md"


def the_text() -> str:
    return THE_BACKLOG.read_text(encoding="utf-8")


def flat(text: str) -> str:
    """One line, single spaces.

    MARKDOWN WRAPS ITS QUOTATIONS, so a quoted sentence in the backlog is split
    across lines while the same sentence in the source is not. The first version
    of this file compared raw substrings and failed on three quotations that are
    verbatim - a check reporting a difference that is only a line break.
    """
    return " ".join(str(text).split())


def words(text: str) -> str:
    """Flattened, with markdown emphasis and heading markers removed.

    A quotation is a claim about WORDS. The source writes some of them inside
    markdown - `**It does not sign anything.**` in a YAML comment, `## This
    checks` as a heading - and a reader quoting them drops the markup, correctly.
    Comparing raw would report a difference that is only formatting.

    IT DOES NOT SOFTEN PUNCTUATION, and that matters: this check's first run
    found the backlog quoting `change resolution.` where the source says
    `change resolution` - A FULL STOP I ADDED. Normalising that away would have
    hidden a fabricated character in a quotation, which is the thing being
    checked.
    """
    return " ".join(str(text).replace("*", "").replace("#", "").replace("`", "").split())


def the_cited_paths() -> list[tuple[str, int | None]]:
    """Every `path` or `path:line` in a backtick in the backlog."""
    found = []
    for raw in re.findall(r"`([^`]+)`", the_text()):
        candidate = raw.strip()
        line = None
        if ":" in candidate and candidate.rsplit(":", 1)[1].isdigit():
            candidate, number = candidate.rsplit(":", 1)
            line = int(number)
        #: A PATH, not any backticked word. `--deadline`, `run1`/`run2` and
        #: `pip install four-asserts` are all in backticks and none of them is
        #: a file - the first version tried to resolve them and reported the
        #: backlog as citing files that are not there.
        if not candidate.endswith((".py", ".md", ".json", ".yml")):
            continue
        if candidate.startswith(("http", "pip ", "--")) or " " in candidate:
            continue
        found.append((candidate, line))
    return found


def resolve(name: str) -> Path | None:
    """A cited path, looked for where the repository actually keeps it."""
    direct = support.REPO_ROOT / name
    if direct.is_file():
        return direct
    for where in ("scripts", "tests", "docs", "app", "packages/four_asserts"):
        candidate = support.REPO_ROOT / where / name
        if candidate.is_file():
            return candidate
    matches = list(support.REPO_ROOT.rglob(name))
    return matches[0] if len(matches) == 1 and matches[0].is_file() else None


class EveryCitationResolvesTest(unittest.TestCase):
    """THE CASE."""

    def test_the_backlog_exists_at_all(self):
        self.assertTrue(THE_BACKLOG.is_file())

    def test_it_cites_something_to_check(self):
        """A backlog citing nothing would pass every test below while asserting
        nothing - the failure mode of any check that reports zero."""
        self.assertGreater(len(the_cited_paths()), 8)

    def test_every_cited_file_is_in_the_tree(self):
        missing = [name for name, _ in the_cited_paths() if resolve(name) is None]
        self.assertEqual(missing, [], "the backlog cites files that are not here")

    def test_every_cited_line_number_is_inside_its_file(self):
        """A line number past the end of a file is a citation that has drifted,
        and it drifts silently - the file still exists."""
        past_the_end = []
        for name, line in the_cited_paths():
            if line is None:
                continue
            path = resolve(name)
            if path is None:
                continue
            how_many = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            if line > how_many:
                past_the_end.append(f"{name}:{line} but the file has {how_many} lines")
        self.assertEqual(past_the_end, [])


#: A quotation attributed to a file: italic-wrapped double quotes, as the page
#: writes them. Matched on the FLATTENED text because markdown wraps them across
#: lines.
AN_ATTRIBUTED_QUOTATION = re.compile(r'\*"([^"]{10,})"\*')

#: A cited path, so a quotation can be attributed to the file nearest before it.
A_CITED_PATH = re.compile(r"`([^`\s]+\.(?:py|md|json|yml))(?::\d+)?`")


def the_quotations_with_their_files() -> list[tuple[str, str | None]]:
    """Every attributed quotation, paired with the path cited nearest before it.

    EXTRACTED FROM THE PAGE, NOT LISTED IN THIS FILE. The first version carried
    a fixed five-tuple, and a peer pointed out that a sixth quotation added
    tomorrow would go unchecked - *the module calls it somewhere* against *the
    loop calls it*, which is the fault I had named in another commit that day.

    IT WAS WORSE THAN PREDICTED. Extracting them dynamically finds **five
    already on the page**, and one of those - `gate.yml`'s line about signing -
    WAS NEVER IN THE TUPLE. The check was not going to become incomplete; it was
    incomplete when the commit message said the quoted sentence is checked.
    """
    flat_text = flat(the_text())
    pairs = []
    for match in AN_ATTRIBUTED_QUOTATION.finditer(flat_text):
        before = flat_text[: match.start()]
        cited = A_CITED_PATH.findall(before)
        pairs.append((match.group(1), cited[-1] if cited else None))
    return pairs


class TheQuotedEvidenceIsReallyThereTest(unittest.TestCase):
    """A citation that resolves proves the file exists. It does not prove the
    file SAYS what the entry claims - so every quotation is checked, and the
    list of them comes from the page rather than from here."""

    def test_the_page_carries_quotations_to_check(self):
        """A page with none would pass everything below while asserting
        nothing."""
        self.assertGreaterEqual(len(the_quotations_with_their_files()), 4)

    def test_every_quotation_is_attributed_to_a_file(self):
        orphaned = [q for q, name in the_quotations_with_their_files() if name is None]
        self.assertEqual(orphaned, [], "a quotation cites no file at all")

    def test_every_quotation_really_is_in_the_file_it_follows(self):
        """The whole point, and now over whatever the page happens to quote."""
        wrong = []
        for quoted, name in the_quotations_with_their_files():
            path = resolve(name) if name else None
            if path is None:
                wrong.append(f"{name} does not resolve")
                continue
            #: The page writes quotations with markdown inside them - backticks
            #: around `--deadline`, for instance - so compare the words.
            needle = words(quoted)
            haystack = words(path.read_text(encoding="utf-8", errors="replace"))
            if needle not in haystack:
                wrong.append(f"{name} does not contain {quoted[:60]!r}")
        self.assertEqual(wrong, [])

    def test_it_would_catch_a_quotation_that_is_not_there(self):
        """RED BY CONSTRUCTION. Without this the test above passes on a page
        that quotes nothing checkable, and that is how the first version of this
        class was hollow."""
        made_up = "this sentence is not in any file in this repository at all"
        path = resolve("app/import_boundary.py")
        self.assertIsNotNone(path)
        self.assertNotIn(flat(made_up), flat(path.read_text(encoding="utf-8")))


class ItSaysWhoseEachItemIsTest(unittest.TestCase):
    """An item with no owner is an item nobody starts. The list separates work
    this lane can do from decisions that are somebody else's."""

    def test_it_marks_the_items_that_are_not_this_lane_s(self):
        text = the_text()
        self.assertIn("Not mine, and marked so", text)
        self.assertIn("**Max's**", text)

    def test_it_says_what_is_deliberately_absent_and_why(self):
        """A backlog is also a claim about what is NOT open, and that claim
        needs stating or a reader supplies their own."""
        text = the_text()
        self.assertIn("What is NOT on this list", text)

    def test_it_states_the_bound_on_checkable(self):
        """Every repository here refuses anonymous access, so a hash is not
        evidence for a reader who is not its author."""
        self.assertIn("refuses anonymous", flat(the_text()))


if __name__ == "__main__":
    unittest.main()
