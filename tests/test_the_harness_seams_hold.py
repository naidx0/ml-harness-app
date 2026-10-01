"""The places this product reaches into OpenCode's interface, held in place.

The harness surfaces live inside their interface through three kinds of seam
(docs/PHASE-5-SURFACES.md): declared text patches, whole-module substitution
by resolved path, and imports from our tree that those patches add. Each one
fails SILENTLY when upstream moves:

  - a substitution whose target file was renamed simply never matches, the
    build is green, and the harness mount is gone from every session;
  - a patch that stopped applying leaves their file as it was, and every
    harness tab renders as a file tab;
  - a patch that imports a name our module no longer exports breaks the
    whole session screen, found only by opening one.

These tests read the files as text. They do not build or render anything:
they check the three contracts a re-vendor or a rename can break, with the
subject set derived from the source of truth (the PATCHES tuple, the
SUBSTITUTES table), never hand-listed.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

import support  # noqa: F401  - puts the repo root on the path

REPO = Path(__file__).resolve().parent.parent
VENDOR_APP = REPO / "vendor" / "opencode" / "packages" / "app" / "src"
WEB = REPO / "web"

sys.path.insert(0, str(REPO / "scripts"))
import vendor_opencode  # noqa: E402


def substitutes() -> dict[str, str]:
    text = (WEB / "vite.config.ts").read_text(encoding="utf-8")
    block = re.search(r"const SUBSTITUTES: Record<string, string> = \{(.*?)\n\}", text, re.DOTALL)
    assert block, "vite.config.ts has no SUBSTITUTES table"
    return dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', block.group(1)))


class SubstitutionsTest(unittest.TestCase):
    def test_the_table_is_not_empty(self):
        # Positive control: a regex that stopped matching would pass every
        # test below by finding nothing to check.
        self.assertIn("session/header/session-header-actions.tsx", substitutes())

    def test_every_target_is_a_vendored_file(self):
        for target in substitutes():
            with self.subTest(target=target):
                self.assertTrue(
                    (VENDOR_APP / target).is_file(),
                    f"{target} is not in the vendored app any more - the substitution "
                    "would never match, and the build would not say so",
                )

    def test_every_replacement_exists(self):
        for target, replacement in substitutes().items():
            with self.subTest(target=target):
                self.assertTrue((WEB / replacement).resolve().is_file(), f"{replacement} is missing")


class PatchesTest(unittest.TestCase):
    def test_every_patch_is_applied(self):
        for relative, _before, after in vendor_opencode.PATCHES:
            with self.subTest(file=relative, after=after[:60]):
                text = (vendor_opencode.VENDOR / relative).read_text(encoding="utf-8")
                self.assertIn(after, text, "the vendored tree is missing a declared patch")

    def test_every_harness_name_a_patch_imports_is_exported(self):
        imports = re.compile(r'import \{([^}]+)\} from "@harness/([^"]+)"')
        checked = 0
        for relative, _before, after in vendor_opencode.PATCHES:
            for names, module in imports.findall(after):
                candidates = [WEB / "src" / "harness" / f"{module}{ext}" for ext in (".tsx", ".ts")]
                source = next((path for path in candidates if path.is_file()), None)
                self.assertIsNotNone(source, f"@harness/{module} (imported by a patch to {relative}) does not exist")
                text = source.read_text(encoding="utf-8")
                for name in (n.strip() for n in names.split(",")):
                    checked += 1
                    with self.subTest(module=module, name=name):
                        self.assertRegex(text, rf"export (async function|function|const|class) {name}\b")
        self.assertGreater(checked, 0, "no patch imports from @harness - the scan found nothing to check")

    def test_the_tab_prefix_in_the_patches_is_ours(self):
        panes = (WEB / "src" / "harness" / "panel" / "panes.ts").read_text(encoding="utf-8")
        prefix = re.search(r'HARNESS_TAB_PREFIX = "([^"]+)"', panes).group(1)
        used = {m for _, _, after in vendor_opencode.PATCHES for m in re.findall(r'startsWith\("([^"]+)"\)', after)}
        self.assertEqual(used, {prefix})


if __name__ == "__main__":
    unittest.main()
