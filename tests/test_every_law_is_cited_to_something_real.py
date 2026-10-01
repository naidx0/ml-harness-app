"""The laws page cites commits, and every citation resolves.

WHY THIS IS A TEST AND NOT A HABIT. `docs/how-to-verify.md` is the page a
reviewer is sent to. Its whole claim on a reader's trust is that each law was
LEARNED somewhere - a commit where the defect was fixed, or a judge record
where it was found - rather than asserted by whoever was writing that night. A
citation nobody can open is a rumour with a hash on it, which is one of the
laws on the page.

It was checked by hand once, on 2026-09-05, over 28 laws and 22 commit
citations. A check run once is a check that has already stopped running: a
rebased branch, a squashed merge, or a typo in a hash makes a citation dangle
silently, and the page goes on looking rigorous.

WHAT THIS DOES NOT CLAIM. It does not read the commit and confirm it is ABOUT
the law - no test can - and it does not require every law to cite a commit.
Six do not, and they are the research lane's, cited to judge records that live
outside git. What it holds is narrower and checkable: a hash written on this
page resolves to a commit in this repository.

MEASURED 2026-09-05, before this file existed: 28 laws, 22 citing a commit, 0
unresolved.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LAWS = REPO / "docs" / "how-to-verify.md"

#: Seven to forty hex characters. Short enough to catch abbreviated hashes,
#: long enough not to catch every "add" and "face" in the prose - and digits
#: alone are dropped below, because a bare number is a row count, not a commit.
A_HASH = re.compile(r"\b([0-9a-f]{7,40})\b")


def the_laws() -> list[str]:
    """Each law, split on the bold claim that opens it.

    The page's own shape: every law begins with `**The claim.**` at the start
    of a line. If that shape ever changes this returns one blob and the count
    assertion below fails loudly, which is the right way for a reader of a file
    to notice the file was reorganised under it.
    """
    text = LAWS.read_text(encoding="utf-8")
    starts = [m.start() for m in re.finditer(r"^\*\*", text, re.M)]
    return [text[a:b] for a, b in zip(starts, starts[1:] + [len(text)])]


def a_commit(sha: str) -> bool:
    finished = subprocess.run(
        ["git", "cat-file", "-t", sha],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return finished.stdout.strip() == "commit"


class EveryLawIsCitedToSomethingRealTest(unittest.TestCase):
    def test_the_page_is_still_a_list_of_laws(self):
        """If this fails, the page was restructured and the rest of this file
        is measuring the wrong thing - read it before trusting the others."""
        self.assertGreaterEqual(len(the_laws()), 20)

    def test_every_hash_on_the_page_resolves_to_a_commit(self):
        dangling = []
        for number, law in enumerate(the_laws(), 1):
            for sha in A_HASH.findall(law):
                if sha.isdigit():
                    continue  # a row count, not a hash
                if not a_commit(sha):
                    dangling.append(f"law {number}: {sha}")
        self.assertEqual(
            dangling,
            [],
            "a law cites a hash that is not a commit in this repository, so the "
            "evidence a reader is pointed at cannot be opened",
        )

    def test_the_index_lists_every_law_and_no_others(self):
        """The index is generated; nothing regenerates it.

        Item 41 put an index of every law's opening claim at the top of the
        page, so a reviewer can reach one law without reading all of them. It
        was built by a script that lives in a scratchpad, not in this
        repository - so a law added tomorrow leaves the index behind, silently,
        and the index goes on looking complete. Measured when this was written:
        **34 entries, 34 laws, 0 missing**, and nothing checking it.

        This checks the CLAIM rather than the formatting: every law's opening
        sentence must appear as an index entry, and every entry must belong to a
        law. It compares a prefix rather than the whole sentence, because the
        index carries the claim and the law carries the claim plus its evidence.
        """
        text = LAWS.read_text(encoding="utf-8")
        start = text.index("## The laws, in one screen")
        end = text.index(chr(10) + "## ", start + 5)
        entries = [
            " ".join(line[2:].split())
            for line in text[start:end].splitlines()
            if line.startswith("- ")
        ]
        # The index carries the claim with its emphasis stripped; a law opens
        # with the claim in bold. Compare the claim, not the markup - the first
        # version compared a law's raw text, kept its asterisks, and reported all
        # 34 laws missing from an index that held all 34.
        claims = []
        for law in the_laws():
            if law.startswith("**If you arrived"):
                continue  # the reviewer preamble, not a law
            inner = law[2:]
            claims.append(" ".join(inner[: inner.index("**")].split())[:60])

        missing = [c for c in claims if not any(c[:40] in e for e in entries)]
        self.assertEqual(
            missing,
            [],
            f"{len(missing)} law(s) are not in the index; it is generated and "
            "nothing regenerates it, so it goes stale looking complete",
        )
        self.assertEqual(
            len(entries),
            len(claims),
            f"{len(entries)} index entries against {len(claims)} laws - the index "
            "has entries that are not laws, or the page was restructured",
        )

    def test_most_laws_cite_something(self):
        """Not every law: six are the research lane's and cite judge records
        that are not in git. But a page where the CITED ones became a minority
        would have stopped being a record of what was learned."""
        laws = the_laws()
        cited = [law for law in laws if A_HASH.search(law)]
        self.assertGreater(
            len(cited) * 2,
            len(laws),
            f"only {len(cited)} of {len(laws)} laws cite anything at all",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
