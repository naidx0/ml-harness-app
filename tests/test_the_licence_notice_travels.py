"""The notice has to travel with the binary, and this is what makes it.

THIS IS NOT A TEST ABOUT BEHAVIOUR. Every other test in this suite protects
something a user would notice going wrong. This one protects a legal
obligation, which is why it is the first test of the rebuild and why it asserts
the LETTER of the condition rather than the spirit.

MIT permits this product to include OpenCode's source, privately and
commercially, on exactly one condition:

    "The above copyright notice and this permission notice shall be included in
     all copies or substantial portions of the Software."

Both halves. A copyright line on its own does not satisfy it, and neither does
a cheerful "built with OpenCode" in an About box. The test below therefore
checks for the copyright line, the permission paragraph AND the warranty
disclaimer, because those three together are what "this permission notice"
means.

It also pins the provenance commit. Not for the licence - MIT does not ask for
it - but because an upstream diff is impossible without knowing what we forked
from, and the day that matters is the day nobody remembers.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import support  # noqa: F401  - puts the repo root on the path

REPO = Path(__file__).resolve().parent.parent
NOTICES = REPO / "THIRD-PARTY-NOTICES.txt"
VENDOR = REPO / "vendor" / "opencode"

#: The three fragments that together ARE the MIT permission notice. Quoted
#: exactly, not paraphrased: a reworded licence is not the licence.
COPYRIGHT = "Copyright (c) 2025 opencode"
PERMISSION = "Permission is hereby granted, free of charge"
DISCLAIMER = "WITHOUT WARRANTY OF ANY KIND"

#: What we forked from. Changing this means re-vendoring, so the test names it
#: rather than reading it from the file it is checking.
PINNED = "ad1a4a653958da4e62be20bb34a3a3aed3089db3"


class TheNoticeExistsTest(unittest.TestCase):
    def test_the_notices_file_is_in_the_repository(self):
        self.assertTrue(
            NOTICES.is_file(),
            "THIRD-PARTY-NOTICES.txt is the file that ships with the binary. "
            "Without it the distribution does not satisfy the MIT condition.",
        )

    def test_the_upstream_licence_is_kept_beside_the_vendored_source(self):
        """A copy at the root of the vendored tree, so it cannot drift away
        from the code it licenses."""
        self.assertTrue((VENDOR / "LICENSE").is_file())


class TheNoticeSaysWhatItMustTest(unittest.TestCase):
    def setUp(self):
        self.text = NOTICES.read_text(encoding="utf-8")

    def test_the_copyright_line_is_present(self):
        self.assertIn(COPYRIGHT, self.text)

    def test_the_permission_paragraph_is_present(self):
        """THE HALF EVERYONE FORGETS. The condition is 'the above copyright
        notice AND this permission notice' - a copyright line alone fails it."""
        self.assertIn(PERMISSION, self.text)

    def test_the_warranty_disclaimer_is_present(self):
        """Part of the same notice, and the part with actual liability
        consequences if it is dropped."""
        self.assertIn(DISCLAIMER, self.text)

    def test_the_upstream_is_named_with_a_resolvable_url(self):
        self.assertIn("https://github.com/anomalyco/opencode", self.text)

    def test_the_apache_dependencies_are_declared(self):
        """@pierre/diffs and @pierre/trees are Apache-2.0 and are NOT covered
        by OpenCode's MIT, which is the mistake this names."""
        self.assertIn("Apache License", self.text)
        self.assertIn("@pierre/diffs", self.text)

    def test_the_trademark_boundary_is_stated(self):
        """MIT grants copyright, not trademark. Their wordmark and icons are
        not ours to ship, and the notice says so where a reader will see it."""
        self.assertIn("trademark", self.text.lower())


class TheProvenanceIsRecordedTest(unittest.TestCase):
    def setUp(self):
        self.record = json.loads((VENDOR / "PROVENANCE.json").read_text(encoding="utf-8"))

    def test_the_commit_is_pinned(self):
        self.assertEqual(self.record["commit"], PINNED)

    def test_the_notices_name_the_same_commit_the_provenance_does(self):
        """Two files carrying one fact is two chances to be wrong, so they are
        checked against each other rather than each against a memory."""
        self.assertIn(self.record["commit"], NOTICES.read_text(encoding="utf-8"))

    def test_the_split_between_vendored_and_npm_is_recorded(self):
        """Which packages are copied and which are dependencies decides how an
        upgrade is done, and it is not inferable from the tree."""
        self.assertIn("packages/app", self.record["vendored"])
        self.assertIn("packages/session-ui", self.record["vendored"])
        self.assertIn("@opencode/ui", self.record["from_npm"])

    def test_every_vendored_path_actually_exists(self):
        """DERIVED, NOT LISTED. The subject set comes from the record, so a
        package added to it without being copied fails here rather than at
        build time."""
        for relative in self.record["vendored"]:
            with self.subTest(package=relative):
                self.assertTrue(
                    (VENDOR / relative).is_dir(),
                    f"{relative} is recorded as vendored and is not on disk",
                )


if __name__ == "__main__":
    unittest.main()
