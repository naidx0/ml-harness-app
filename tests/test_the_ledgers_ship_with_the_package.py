"""An installed engine can load its own knowledge.

## The bug

`pip install .` copies the `app/` package and nothing else. `app/diagnosis.py`
read its ledger from `docs/`, which is outside the package, so an installed
engine **started and could not load the file holding every gate, outcome and
fact it has**. Measured before the fix: `ml_harness.egg-info/SOURCES.txt` carried
zero entries for `diagnosis_engine.yaml`.

It was invisible because the README says `pip install -e .`, and an editable
install points site-packages back at the checkout — so `docs/` is right there and
everything works. The bug only appeared for the one install a stranger would do.

## Why a build step rather than moving the file

The ledger is a DOCUMENT. `AGENTS.md`'s authority table sends a reviewer to
`docs/diagnosis_engine.yaml` to answer *"how does the product decide?"*, 107
files name it by that path, and `threads.ledger` rows in databases that already
exist hold that string. Moving it would ship more easily and would take the
document out of the place people are told to read it.

So: **one source, one generated copy.** `docs/` is edited; `app/_bundled/` is
produced by `setup.py`'s `build_py`, is gitignored, and is never read when a
checkout is present — so a developer cannot be reading a stale copy of their own
edit.

## The one thing that would make this worse than the bug

A build hook that silently copies nothing ships exactly the original defect
wearing a green build. `setup.py::_bundle` therefore RAISES on a missing source
rather than producing an empty bundle, and that is asserted below.

## What is NOT asserted here, and where it is

That a real wheel contains the files. Building one takes seconds this suite
should not spend on every run; it was driven by hand when this landed, and an
installed copy with no `docs/` beside it reported
`docs/diagnosis_engine.yaml` and loaded all 55 outcomes. The packaging step's
own acceptance is a real install on a clean machine, which is named in
`docs/THE_PLAN.md` and cannot be faked here.
"""

import unittest
from pathlib import Path

from app import diagnosis


REPO = Path(__file__).resolve().parents[1]


class TheLedgersShipWithThePackageTest(unittest.TestCase):
    def test_a_checkout_reads_its_own_docs_and_never_a_bundle(self):
        """THE HALF THAT PROTECTS THE DEVELOPER.

        If this ever resolved to `app/_bundled/` in a working tree, somebody
        would edit `docs/diagnosis_engine.yaml`, see no change, and lose an
        afternoon. The checkout branch is taken whenever the repository is
        there, which is what makes one source and one generated copy safe.
        """
        self.assertEqual(diagnosis.LEDGER_ROOT, REPO)
        self.assertEqual(
            diagnosis.SPEC_PATH, REPO / "docs" / "diagnosis_engine.yaml"
        )

    def test_every_ledger_still_names_itself_the_way_it_is_stored(self):
        """THE HALF THAT PROTECTS EVERY DATABASE THAT ALREADY EXISTS.

        `threads.ledger` holds `docs/ledgers/ai_engineering.yaml` as a string,
        and `evidence.ledger_for_thread` turns it back into a file through
        `resolve_ledger`. The bundle preserves the `docs/` segment for exactly
        this reason: a bundle that flattened the path would resolve to a
        different name and orphan every thread ever created.
        """
        named = sorted(
            diagnosis.spec_at(path).as_written for path in diagnosis.known_ledgers()
        )
        # THE LIST IS SPELLED OUT AND IT IS NOT A SECOND SOURCE OF TRUTH. What
        # this asserts is the SHAPE of every stored name - `docs/` preserved,
        # posix, relative to the root - because that shape is what makes a name
        # in `threads.ledger` round-trip. A third ledger arriving here is the
        # test asking to be read, which is what happened on 2026-08-28 when
        # `harness_design.yaml` landed.
        self.assertEqual(
            named,
            [
                "docs/diagnosis_engine.yaml",
                "docs/ledgers/ai_engineering.yaml",
                "docs/ledgers/harness_design.yaml",
            ],
        )
        self.assertEqual(diagnosis.DEFAULT_LEDGER, "docs/diagnosis_engine.yaml")

        # And a stored name round-trips to a real file, which is the property
        # the whole scheme rests on.
        for name in named:
            with self.subTest(ledger=name):
                self.assertTrue(diagnosis.resolve_ledger(name).is_file())

    def test_the_build_declares_the_bundle_it_produces(self):
        """A copy nothing declares is a copy the wheel drops.

        The AST sweep in `test_what_this_package_imports_it_declares.py` finds
        `Path(__file__).parent / "<name>"` sites; `_ledger_root` builds its path
        through a local, so this names it directly.
        """
        import tomllib

        config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
        globs = (config["tool"]["setuptools"]["package-data"]["app"])
        self.assertIn("_bundled/docs/*.yaml", globs)
        self.assertIn("_bundled/docs/ledgers/*.yaml", globs)

    def test_the_build_step_refuses_rather_than_bundling_nothing(self):
        """THE FAILURE THAT WOULD BE WORSE THAN THE BUG.

        A hook that copies nothing and exits zero ships an engine that cannot
        load its ledger — the original defect, with a green build on top. Driven
        against an empty tree rather than asserted from the source.
        """
        import tempfile
        import importlib.util

        spec = importlib.util.spec_from_file_location("mlh_setup", REPO / "setup.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with self.assertRaises(SystemExit) as refused:
            module._bundle(Path(tempfile.mkdtemp()))
        self.assertIn("cannot bundle the ledgers", str(refused.exception))

    def test_the_ledger_glob_is_a_glob_and_not_a_list(self):
        """`known_ledgers()` is a directory glob because "a second place naming
        which ledgers ship is a second place that goes stale". The bundler is
        the second place, so it globs too — a third ledger dropped into
        `docs/ledgers/` ships without anybody editing `setup.py`."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("mlh_setup", REPO / "setup.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertIn("*", module.LEDGER_GLOB)
        bundled = module._bundle(REPO)
        self.assertEqual(
            len([p for p in bundled if "ledgers" in p.parts]),
            len(list((REPO / "docs" / "ledgers").glob("*.yaml"))),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
