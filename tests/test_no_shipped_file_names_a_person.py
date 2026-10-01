"""Nothing that would ship in a public mirror names a person or their machine.

MEASURED BEFORE THIS TEST EXISTED: 50 hits across 26 files - 25 a real Windows
home directory, 21 a personal identifier, 3 a private directory path, 1 a
personal note vault - in frontend fixtures, test fixtures and two source files.
Every one was a real capture from a real machine, pasted in because that is
what the run produced.

WHY A TEST AND NOT A ONE-OFF SCRUB. A fixture is captured from a run, and the
next capture carries the next home directory. The scrub fixes the files that
exist; this fixes the ones that do not exist yet, which is the only half that
stays fixed.

WHAT IT DOES NOT DO. It does not scan `docs/`, `runs/`, `recipes/` or the agent
instructions, because the mirror's policy already holds those back and dated
records must not be rewritten to match today. It scans exactly what would be
published, which is the only set the question is about.

FOUR NAMES ARE ALLOWED THROUGH AND NONE OF THEM IS A PERSON: GitHub Actions'
`runneradmin` and `RUNNER~1`, Windows Sandbox's `WDAGUtilityAccount`, and a
one-letter placeholder. Scrubbing those would have deleted true statements
about where this software runs - see `scripts/release/mirror.py`.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / "release" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


policy = _load("policy")
mirror = _load("mirror")


class NoShippedFileNamesAPersonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shipped = [f for f in mirror.tracked() if policy.decide(f)[0]]

    def test_the_shipped_set_is_a_real_set(self):
        """If the policy or `git ls-files` ever returns nothing, the scan below
        passes by scanning nothing, which is the failure mode of every check
        that reports zero."""
        self.assertGreater(len(self.shipped), 500)

    def test_nothing_that_would_ship_carries_a_shape_that_names_a_machine(self):
        """THE HALF THAT CAN RUN ANYWHERE, and it is split out for that reason.

        Home directories, note vaults and token shapes need no private data, so
        this half runs on CI, in a fresh clone, and in every other lane's
        checkout. It caught 25 of the 50 matches on the pre-scrub tree - the
        whole home-directory class - so it is not the small half.
        """
        hits = mirror.scan(self.shipped, include_identifiers=False)
        self.assertEqual(
            hits,
            [],
            "a file that would be published names a person, their home "
            "directory, or a private path. Was it captured from a run? Replace "
            "the captured path with a neutral one; the fixture is about the "
            "shape, not about whose machine it came from.",
        )

    def test_the_identifier_half_runs_or_says_it_did_not(self):
        """A PASS FOR A SCAN THAT ONLY PARTLY RAN IS THE DEFECT THIS REPOSITORY
        IS ABOUT, and this guard was committing it.

        The denylist is gitignored - it is the private data it protects - so it
        is absent on every machine but the one that wrote it. Measured
        2026-09-06: with it missing the scan ran 4 of 11 rules, found nothing,
        and this test reported OK. On CI and in every other lane's checkout the
        guard had been running a third of itself and saying clean.

        It skips now rather than passing. A skip is neither green nor red, which
        is the honest reading of a check that could not be run - the same shape
        as the gate's own exit 2 for a run that did not say.
        """
        if not mirror.identifiers_are_available():
            self.skipTest(
                "no identifier list on this machine, so the personal-identifier "
                f"rules did not run; {len(mirror.SHAPES)} shape rules did, and "
                "they are asserted separately. This is NOT a clean bill."
            )
        self.assertEqual(
            mirror.scan(self.shipped),
            [],
            "a file that would be published names a person or a private path.",
        )

    def test_the_scan_can_still_see_the_thing_it_is_looking_for(self):
        """A scan narrowed until it finds nothing is a scan that passes. This
        plants each shape and requires a hit."""
        import tempfile

        # ASSEMBLED, NEVER TYPED. This file is inside the set the scan reads,
        # so a plant written as a literal makes the test fail its own check -
        # which is exactly what happened on the first full gate, four hits, all
        # of them these four lines. The scanner's own comments record the same
        # wall from the other side: a rule that spells out its own trigger
        # fails its own check. Built from parts, the file text carries no
        # trigger and the runtime value carries all of it.
        user = "some" + "person"
        planted = {
            "a real Windows home directory": "path = 'C:/Users/" + user + "/Projects/x'",
            "a real macOS home directory": "path = '/Users/" + user + "/Documents/x'",
            "a personal note vault": "note = 'Obsid" + "ian Vault'",
            "something shaped like a live API token": "k = 'sk" + "-abcdefghijklmnopqrstuvwxyz0123'",
        }
        with tempfile.TemporaryDirectory() as tmp:
            real = mirror.REPO
            try:
                mirror.REPO = Path(tmp)
                for why, line in planted.items():
                    with self.subTest(why):
                        (Path(tmp) / "planted.py").write_text(line, encoding="utf-8")
                        found = mirror.scan(["planted.py"])
                        self.assertTrue(
                            any(why in hit for hit in found),
                            f"the scan no longer catches {why}",
                        )
            finally:
                mirror.REPO = real

    def test_the_named_placeholders_are_still_let_through(self):
        """The other direction. A check that cries wolf on CI's own paths gets
        widened until it stops working."""
        import tempfile

        for allowed in (
            "C:/Users/runneradmin/work",
            "C:/Users/RUNNER~1/AppData",
            "C:/Users/WDAGUtilityAccount/Desktop",
            "C:/Users/example/Projects",
        ):
            with self.subTest(allowed), tempfile.TemporaryDirectory() as tmp:
                real = mirror.REPO
                try:
                    mirror.REPO = Path(tmp)
                    (Path(tmp) / "planted.py").write_text(f"p = '{allowed}'", encoding="utf-8")
                    self.assertEqual(mirror.scan(["planted.py"]), [])
                finally:
                    mirror.REPO = real


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
