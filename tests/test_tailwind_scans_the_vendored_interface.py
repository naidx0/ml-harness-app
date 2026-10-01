"""Tailwind must scan the vendored interface, or every pane collapses.

MEASURED 2026-09-22. OpenCode's app uses about 917 distinct Tailwind utility
classes for its layout - heights, flex, overflow, spacing. Their
@opencode/ui/styles/tailwind entry declares @source globs relative to where
that package sits in THEIR monorepo. Installed from npm it sits under
node_modules, where those globs point at nothing, so Tailwind generated none of
the 917. The build was green, the type check was green, the unit tests were
green, and the component CSS still rendered correctly because it keys off data
attributes. Only launching the real app showed every pane squashed into a band
at the top of the window.

The fix is a declared patch in scripts/vendor_opencode.py adding @source lines
to their index.css that are right for this layout. These tests hold it: the
lines exist, every one resolves to a real path from the file it sits in, and
the two trees that carry layout classes are both covered.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import support  # noqa: F401  - puts the repo root on the path

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "vendor" / "opencode" / "packages" / "app" / "src" / "index.css"
SOURCE = re.compile(r'^@source\s+(not\s+)?"([^"]+)"\s*;', re.MULTILINE)


class TheSourcesResolveTest(unittest.TestCase):
    def setUp(self):
        self.text = INDEX.read_text(encoding="utf-8")
        self.sources = [(bool(m.group(1)), m.group(2)) for m in SOURCE.finditer(self.text)]

    def test_the_patch_is_applied(self):
        included = [path for negated, path in self.sources if not negated]
        self.assertTrue(
            included,
            "their index.css has no @source lines - the vendoring patch did not "
            "apply, and Tailwind will generate none of the layout utilities",
        )

    def test_every_source_resolves_from_the_file_it_is_in(self):
        """DERIVED FROM THE FILE, not hand-listed: a new @source line with bad
        path arithmetic fails here rather than as a collapsed window."""
        for negated, path in self.sources:
            if negated:
                continue
            with self.subTest(source=path):
                target = (INDEX.parent / path).resolve()
                self.assertTrue(target.exists(), f"@source \"{path}\" points at {target}, which does not exist")

    def test_both_trees_that_carry_layout_classes_are_scanned(self):
        """The app shell and the transcript renderer both put utilities in their
        class lists. Covering one and not the other collapses half the UI."""
        resolved = {(INDEX.parent / p).resolve() for negated, p in self.sources if not negated}
        app = (REPO / "vendor" / "opencode" / "packages" / "app" / "src").resolve()
        session_ui = (REPO / "vendor" / "opencode" / "packages" / "session-ui" / "src").resolve()
        self.assertIn(app, resolved)
        self.assertIn(session_ui, resolved)

    def test_our_own_entry_is_scanned_too(self):
        """index.html carries the root's `h-dvh` - the one class whose absence
        is visible as a band across the whole window."""
        resolved = {(INDEX.parent / p).resolve() for negated, p in self.sources if not negated}
        self.assertIn((REPO / "web" / "index.html").resolve(), resolved)


if __name__ == "__main__":
    unittest.main()
