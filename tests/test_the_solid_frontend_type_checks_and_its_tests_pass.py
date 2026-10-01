"""G-types, G-unit and G-build for the Solid frontend, enforced by the main gate.

The rebuild's plan names five gates. Two of them - the type check and the
frontend's own tests - live in node, and a gate that only runs if somebody
remembers to run it is not a gate. So the Python suite runs them, the same way
`test_the_frontend_still_compiles.py` already runs `tsc` for the outgoing React
app.

G-types is `scripts/check_web_types.py`: zero errors in web/src, and nothing in
the vendored tree beyond a recorded baseline. Its reasons are in its docstring.

G-unit is vitest over web/src. It is asserted by exit code AND by a count of
passing tests, because a runner that finds no test files exits in a way that
is easy to misread: when the generator once dropped vitest from web/package.json
the runner reported "no tests" beside a green build.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

import support  # noqa: F401  - puts the repo root on the path

REPO = Path(__file__).resolve().parent.parent
WEB = REPO / "web"
NPX = "npx.cmd" if sys.platform == "win32" else "npx"


@unittest.skipUnless(shutil.which(NPX) and (REPO / "node_modules").is_dir(),
                     "node or the workspace install is absent - run npm install at the repo root")
class TheSolidFrontendTest(unittest.TestCase):
    def test_types_are_clean_in_our_code_and_no_worse_in_theirs(self):
        done = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "check_web_types.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("0 errors in web/src", done.stdout)

    def test_the_frontend_suite_runs_and_passes(self):
        done = subprocess.run(
            [NPX, "vitest", "run", "--reporter=basic"],
            cwd=WEB, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        output = re.sub(r"\x1b\[[0-9;]*m", "", done.stdout + done.stderr)
        self.assertEqual(done.returncode, 0, output[-3000:])
        # "no tests" also exits in a way that reads as benign. Require a count.
        passed = re.search(r"Tests\s+(\d+)\s+passed", output)
        self.assertIsNotNone(passed, "vitest ran but reported no passing tests:\n" + output[-2000:])
        self.assertGreater(int(passed.group(1)), 0)

    def test_the_production_build_succeeds(self):
        """G-build: the minified production build, the one the shell ships.

        Added after a stray comment fragment in a stylesheet passed the type
        check, every unit test and the dev server, and was refused only by
        the minifier. Neither tsc nor vitest reads CSS. Built into a scratch
        directory so the gate never overwrites web/dist mid-work.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as out:
            done = subprocess.run(
                [NPX, "vite", "build", "--outDir", out, "--emptyOutDir"],
                cwd=WEB, capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            output = done.stdout + done.stderr
            self.assertEqual(done.returncode, 0, output[-3000:])
            self.assertTrue((Path(out) / "index.html").is_file(), "the build reported success and wrote no index.html")


if __name__ == "__main__":
    unittest.main()
