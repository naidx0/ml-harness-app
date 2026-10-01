"""Run each check with one of its inputs taken away, and see which still pass.

    python scripts/which_checks_are_silently_partial.py

WHY. `test_no_shipped_file_names_a_person` ran four of its eleven rules on every
machine but the one that wrote it, found nothing, and reported OK - because its
denylist is gitignored and its absence made the scan smaller rather than louder.
A check that shrinks quietly when an input goes missing reports the same green
as a check that ran in full, and nothing in the result distinguishes them.

So this asks the question of every check that reads something from outside
itself: take the input away, run it, and record whether it still passes. **A
pass with the input gone is the defect.** A failure is the check noticing, and a
skip is the check saying it could not run - both are honest.

WHAT IT CANNOT DO. It does not prove a check is correct when its inputs ARE
present; that is what the checks themselves are for. And it only reaches inputs
that can be emptied from here - a check reading something this script cannot
reach is listed as not audited rather than as passing.
"""

from __future__ import annotations

import importlib
import io
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "scripts" / "release"))


def outcome(module: str, patches: list[tuple[object, str, object]]) -> str:
    """Run one test module with those attributes replaced. `pass` is the defect."""
    saved = [(obj, name, getattr(obj, name)) for obj, name, _ in patches]
    for obj, name, value in patches:
        setattr(obj, name, value)
    try:
        suite = unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(module))
        quiet = io.StringIO()
        with redirect_stdout(quiet), redirect_stderr(quiet):
            result = unittest.TextTestRunner(stream=quiet, verbosity=0).run(suite)
        if not result.wasSuccessful():
            return "RED - it noticed"
        if result.skipped:
            return f"SKIPPED {len(result.skipped)} - it said it could not run"
        return "PASSED - silently partial"
    finally:
        for obj, name, value in saved:
            setattr(obj, name, value)


def main() -> int:
    import test_every_law_is_cited_to_something_real as citations
    import test_no_literal_backslash_eats_a_fixture as backslash
    import test_no_shipped_file_names_a_person as shipped
    import test_one_gate_command_is_named_everywhere as one_gate

    nowhere = REPO / "scripts" / "release" / "no-such-directory"

    # PATCH WHAT THE TEST HOLDS, NOT A COPY OF IT. The first version imported
    # `mirror` here and patched that; the test module loads its OWN instance
    # from the same file by path, so the two are different objects and removing
    # an input from one removed nothing from the other. Both shipped-file audits
    # came back "silently partial" and both verdicts were this script, not the
    # checks. An audit that cannot remove the input measures nothing.
    the_mirror = shipped.mirror

    audits = [
        ("the shipped-file scan, with no file list",
         "test_no_shipped_file_names_a_person",
         [(the_mirror, "tracked", lambda: [])]),
        ("the shipped-file scan, with no denylist",
         "test_no_shipped_file_names_a_person",
         [(the_mirror, "HERE", nowhere)]),
        ("the backslash guard, with nothing to scan",
         "test_no_literal_backslash_eats_a_fixture",
         [(backslash, "WHERE", ()), (backslash, "PROSE", ())]),
        ("the citation guard, with no laws page",
         "test_every_law_is_cited_to_something_real",
         [(citations, "LAWS", nowhere / "absent.md")]),
        ("the gate-command guard, with git tracking nothing",
         "test_one_gate_command_is_named_everywhere",
         [(one_gate, "files_git_tracks", lambda: set())]),
    ]

    print(f"{'check, with one input removed':46s} outcome")
    print("-" * 92)
    partial = 0
    for label, module, patches in audits:
        got = outcome(module, patches)
        partial += got.startswith("PASSED")
        print(f"{label:46s} {got}")
    print("-" * 92)
    print(f"silently partial: {partial} of {len(audits)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
