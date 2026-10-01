"""The build step that puts the ledgers inside the package.

`pyproject.toml` is the whole of this project's configuration and this file adds
ONE thing to it, deliberately: a `build_py` that copies `docs/diagnosis_engine.yaml`
and `docs/ledgers/*.yaml` into `app/_bundled/docs/` before the package is built.

## Why this exists

`pip install .` copies the `app/` package and nothing else. `app/diagnosis.py`
reads its ledger from `docs/`, which is outside the package - so an installed
engine started and could not load the file holding every gate, outcome and fact
it has. Measured before this: `ml_harness.egg-info/SOURCES.txt` carried zero
entries for `diagnosis_engine.yaml`. `pip install -e .` hid it completely,
because an editable install points back at the checkout, and `-e .` is what the
README has always said.

## Why a build step rather than moving the file

The ledger is a DOCUMENT. `AGENTS.md`'s authority table sends a reviewer to
`docs/diagnosis_engine.yaml` to answer "how does the product decide?", 107 files
name it by that path, and `threads.ledger` rows in databases that already exist
hold that string. Moving it into the package would ship more easily and would
take the document out of the place people are told to read it.

So: one source, one generated copy. `docs/` is edited; `app/_bundled/` is
produced, is in `.gitignore`, and is never read when a checkout is present -
`diagnosis._ledger_root` prefers the repository, so a developer cannot be reading
a stale copy of their own edit.

## The failure this must not have

A build hook that silently copies nothing ships an engine that cannot load its
ledger, which is the bug it exists to fix, wearing a green build. So it RAISES
if a source file is missing, and
`tests/test_the_ledgers_ship_with_the_package.py` asserts the copy happened.
"""

from pathlib import Path
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py

HERE = Path(__file__).parent.resolve()

#: What the engine reads at runtime and therefore what has to travel with it.
#: A glob rather than a list for `docs/ledgers/`, because `known_ledgers()` is a
#: directory glob too and a second list of which ledgers ship is the second place
#: that goes stale.
SOURCES = ("docs/diagnosis_engine.yaml",)
LEDGER_GLOB = "docs/ledgers/*.yaml"

#: A recipe's DEFINITION, which is code and travels. THE_PLAN V.3 A1b asked
#: whether a recipe is package data or user data and the answer is BOTH, in
#: two parts that happen to share a directory: `recipe.toml`,
#: `entrypoint.py` and `requirements.lock` are a few KB the product cannot
#: run without, and `.venv` is 4.8 GB of materialised environment that must
#: never be in a wheel.
#:
#: The glob is `recipes/*/*` filtered to FILES, so the venv is excluded by
#: its SHAPE rather than by its name: everything directly inside a recipe
#: directory ships, nothing in a subdirectory does. A rule keyed on the
#: string ".venv" would ship the next environment somebody named
#: ".venv311".
RECIPE_GLOB = "recipes/*/*"
BUNDLE = "app/_bundled"


def _bundle(root: Path) -> list[Path]:
    """Copy the ledgers into the package. Raises rather than shipping nothing."""
    written: list[Path] = []
    wanted = [root / name for name in SOURCES] + sorted(root.glob(LEDGER_GLOB))
    missing = [str(path) for path in wanted if not path.is_file()]
    if missing or not wanted:
        raise SystemExit(
            "setup.py: cannot bundle the ledgers, so this build would produce an "
            "engine that starts and cannot load its own knowledge. Missing: "
            + (", ".join(missing) or "no ledger matched " + LEDGER_GLOB)
        )

    # THE RECIPES, AND THE SAME REFUSAL FOR THE SAME REASON. A build with no
    # recipe definitions produces a product that installs, starts, answers, and
    # cannot train anything - which is the exact defect V.0 measured for the
    # ledgers and `mlh doctor` was written to report.
    recipes = sorted(
        path
        for path in root.glob(RECIPE_GLOB)
        if path.is_file() and (path.parent / "recipe.toml").is_file()
    )
    if not recipes:
        raise SystemExit(
            "setup.py: no recipe definition matched " + RECIPE_GLOB + ", so this "
            "build would produce a product that cannot run a single training "
            "job. A recipe's .venv is deliberately NOT bundled; its recipe.toml, "
            "entrypoint and lockfile are."
        )
    wanted += recipes
    for source in wanted:
        target = root / BUNDLE / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        written.append(target)
    return written


class BuildWithLedgers(build_py):
    def run(self):  # noqa: D102 - setuptools' own interface
        _bundle(HERE)
        super().run()


# GUARDED, BECAUSE THIS FILE IS ALSO READ RATHER THAN RUN.
# `tests/test_the_ledgers_ship_with_the_package.py` imports `_bundle` to drive
# its refusal directly. Unguarded, importing this called `setup()`, which parsed
# the TEST RUNNER's argv and died on "invalid command 'discover'". setuptools
# executes this file as a script, so the guard costs the build nothing.
if __name__ == "__main__":
    setup(cmdclass={"build_py": BuildWithLedgers})
