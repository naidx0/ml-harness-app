"""The TypeScript still type-checks, because the gate could not see that it did not.

## What this was written from

2026-09-11: commit `1b095fc` reached `main` green, and `npm run build` failed
on it. A test fixture named a field `id` on a type whose field is `node`. Every
Python test passed - there are five thousand of them and not one reads a `.tsx`
file as anything but text - and `vitest` passed too, because vitest STRIPS types
rather than checking them. The break surfaced when the Tauri build ran `tsc -b`
as part of `beforeBuildCommand`, which is to say: when somebody tried to ship.

A gate that cannot see a broken build is a gate that certifies a tree nobody
can build from.

## Why `tsc -b` and not `npm run build`

`tsc -b` is the half that fails deterministically and in five seconds. The rest
of `npm run build` is `vite build`, which writes `frontend/dist` - a gate must
not leave artefacts behind, and a bundler's output is not what this is asking
about. `tsc -b` follows the project references in `frontend/tsconfig.json`,
which is what makes it see TEST files: `tsconfig.app.json` alone does not, and
`npx tsc --noEmit -p tsconfig.json` is the invocation that let this through.

## It SKIPS rather than fails when the toolchain is absent

A machine with no `node_modules` has not broken anything - it has not been set
up. Skipping there is the honest answer, and the skip names what is missing so
a green run on a bare machine cannot be mistaken for a checked one.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"

#: Long enough for a cold type-check on a loaded machine. Measured at ~5s warm.
PATIENCE = 240


class TheFrontendStillCompilesTest(unittest.TestCase):
    def test_typescript_type_checks(self) -> None:
        if not (FRONTEND / "node_modules").is_dir():
            self.skipTest("frontend/node_modules is absent; nothing to check with")
        npx = shutil.which("npx") or shutil.which("npx.cmd")
        if npx is None:
            self.skipTest("npx is not on PATH; the toolchain is not installed here")

        finished = subprocess.run(
            [npx, "tsc", "-b", "--noEmit"],
            cwd=FRONTEND,
            capture_output=True,
            text=True,
            timeout=PATIENCE,
        )
        #: The compiler prints its errors on stdout, not stderr.
        self.assertEqual(
            finished.returncode,
            0,
            "the frontend does not type-check, so `npm run build` and the Tauri "
            "bundle both fail on this tree:" + chr(10) + (finished.stdout or finished.stderr),
        )


if __name__ == "__main__":
    unittest.main()
