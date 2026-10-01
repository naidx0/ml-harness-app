"""Every count typed into README.md and docs/PHASES.md equals what runs.

README.md states the policy this file enforces, in the bullet that
carries the tool count: the tool count is "the
one number in this section, and it is here because the packs are meaningless
without it. Everything else ... is read from the running system rather than
typed. A number retyped into a README is a number that goes stale at the next
commit, and this repository has been bitten by that three times."

It was bitten a fourth time. Measured on 2026-09-02 at origin/main 093056f:
the README said 49 tools in 12 capability packs while the registry held 67 in
14, and the PHASES.md table said 49 tools, 12 packs, 2 ledgers and 26
proposers against 67, 14, 3 and 43. Every one of those numbers had been true
when it was typed. That is the whole problem: prose cannot notice a commit.

So the numbers stay - they are load-bearing, and a README that refused to say
how big the product is would be worse - and this test is what makes them
answerable. Each row below names the runtime expression the document's own
"how" column already cites, and asserts the typed figure equals it. When a
tool is registered tomorrow, this test fails and names the line to fix, which
is the only way a retyped number is ever allowed to exist.

WHAT THIS DELIBERATELY DOES NOT ASSERT. Recipes: README:270 names which
recipe directories exist and which one runs without a built environment,
because `recipes/demo-metrics/recipe.toml:3` says demo-metrics is "the only
recipe that ships today" and trains nothing - that is a sentence about
capability, not a count, and a test that parsed a number out of it would be
inventing one. The sweep row (tools a turn hands the model) carries its own
walls in `test_a_turn_says_which_blocks_it_loaded.py`, which SWEEPS rather
than counts; this file reads its constants rather than re-deriving them,
because two independent derivations of one number is how they drift apart.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from app import diagnosis
from app.tools import REGISTRY, blocks, propose

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
PHASES = ROOT / "docs" / "PHASES.md"


def _table_rows(text: str, label: str) -> list[list[str]]:
    """EVERY PHASES.md table row whose first cell is exactly `label`.

    THIS USED TO RETURN THE FIRST ONE AND READ ITS SECOND CELL, and that is an
    instrument fault this file caught on 2026-09-18 by going red for the right
    number. There are two `| tools |` rows in the document - one in the
    re-taken status table, whose columns are `row | was | now | how`, and one
    in the what-runs-today table, whose columns are `label | value | how`. The
    second cell of the first of those is the HISTORICAL figure, so what the
    check read was "what the count used to be", and it passed for a year
    because each retake had written the same number into both cells. The day
    they legitimately differed - `compile_the_plan` making it 89, with `was`
    still 88 - the check failed while the document was right.

    So the row is returned whole, and the value is read from the cell before
    the `how` cell (`_current_number`), which is the current figure in either
    table. Both rows are checked rather than the first, because a count typed
    twice can go stale twice.
    """
    out: list[list[str]] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) > 2 and cells[0] == label:
            out.append(cells)
    if not out:
        raise AssertionError(
            f"docs/PHASES.md has no table row labelled {label!r}. The row was "
            "renamed or removed; this test names what it counts and must be "
            "updated with it rather than deleted."
        )
    return out


def _current_number(cells: list[str]) -> int:
    """The figure a row states NOW: the cell before its `how` cell."""
    return _first_number(cells[-2])


def _first_number(cell: str) -> int:
    """The first integer in a table cell, ignoring bold markers and commas."""
    match = re.search(r"\*{0,2}([\d,]+)", cell)
    if not match:
        raise AssertionError(f"no number in {cell!r}")
    return int(match.group(1).replace(",", ""))


class TheDocumentsCountWhatRunsTest(unittest.TestCase):
    """One assertion per typed number, against the expression the doc names."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = README.read_text(encoding="utf-8")
        cls.phases = PHASES.read_text(encoding="utf-8")

    # -- README.md -------------------------------------------------------

    def test_the_readme_headline_counts_the_registry_and_the_packs(self):
        """README.md's one permitted count: `N registered tools in M packs`."""
        match = re.search(
            r"\*\*(\d+) registered tools in (\d+) capability packs\.?\*\*",
            self.readme,
        )
        self.assertIsNotNone(
            match,
            "README.md no longer carries the '<n> registered tools in <m> "
            "capability packs' sentence that README.md calls the one "
            "number in that section.",
        )
        tools, packs = int(match.group(1)), int(match.group(2))
        self.assertEqual(
            tools, len(list(REGISTRY)),
            "README.md's tool count is not len(list(app.tools.REGISTRY)).",
        )
        self.assertEqual(
            packs, len(blocks.PACKS),
            "README.md's pack count is not len(app.tools.blocks.PACKS).",
        )

    def test_the_readme_names_every_ledger_that_loads(self):
        """The ledgers bullet may not undercount, and may not claim one gate
        count for ledgers that do not share one: harness_design declares six
        where the other two declare five."""
        for path in diagnosis.known_ledgers():
            relative = path.relative_to(ROOT).as_posix()
            # assertTrue, not assertIn: assertIn prints the haystack, and the
            # haystack here is the whole README.
            self.assertTrue(
                relative in self.readme,
                f"{relative} loads and diagnoses but the README does not name it.",
            )
        self.assertNotRegex(
            self.readme,
            r"Two ledgers, one engine",
            "The README says two ledgers; diagnosis.known_ledgers() finds "
            f"{len(diagnosis.known_ledgers())}.",
        )

    # -- docs/PHASES.md --------------------------------------------------

    def test_the_phases_table_counts_the_registry(self):
        """EVERY row that states this count, in either table - see `_table_rows`
        for the day one of them was historical and the check read it."""
        for cells in _table_rows(self.phases, "tools"):
            with self.subTest(row=cells[0], states=cells[-2]):
                self.assertEqual(_current_number(cells), len(list(REGISTRY)))

    def test_the_phases_table_counts_the_packs(self):
        for cells in _table_rows(self.phases, "capability packs"):
            with self.subTest(states=cells[-2]):
                self.assertEqual(_current_number(cells), len(blocks.PACKS))

    def test_the_phases_table_counts_the_ledgers(self):
        for cells in _table_rows(self.phases, "ledgers that load and diagnose"):
            with self.subTest(states=cells[-2]):
                self.assertEqual(
                    _current_number(cells), len(diagnosis.known_ledgers())
                )

    def test_the_phases_table_counts_the_proposers(self):
        for cells in _table_rows(self.phases, "total proposers registered"):
            with self.subTest(states=cells[-2]):
                self.assertEqual(_current_number(cells), len(propose.COVERAGE))

    def test_no_document_still_says_forty_nine_or_forty_eight_tools(self):
        """The two prose sentences that carried the old total.

        A table row is parsed above; these are sentences, and a sentence with
        a stale total in it is the same defect wearing prose.
        """
        for name, text in (("README.md", self.readme), ("docs/PHASES.md", self.phases)):
            for stale in (r"\b49 registered tools\b", r"\bthe 48 tools\b"):
                self.assertNotRegex(
                    text, stale,
                    f"{name} still carries {stale!r}; the registry holds "
                    f"{len(list(REGISTRY))}.",
                )


if __name__ == "__main__":
    unittest.main()
