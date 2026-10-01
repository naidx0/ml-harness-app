"""A recipe that ships a lockfile must say how to build it, in the file.

`README.md`: *"Real training depends on pinned per-recipe environments you build
first."* That was the whole zero-to-training barrier, and the instructions for
crossing it lived as PROSE in each `requirements.lock` header - three recipes,
three phrasings, four commands to retype each, and nothing checking any of it.
It was not right either: `hf-quantize`'s header said python 3.12 for an
environment measured at 3.11.15.

So the steps became a `[environment]` table in `recipe.toml` and
`scripts/build_recipe_env.py` executes them. This file is what stops the two
drifting apart again, and what stops a NEW recipe shipping a lockfile with its
build steps hidden in a comment.

## The part that is not a schema check

`[environment.verify]` exists because installing the wrong torch IS NOT AN
ERROR. PyPI's Windows wheel is CPU-only; the CUDA build lives only on
download.pytorch.org. Somebody who gets the wrong one completes every step, sees
nothing fail, clicks train, and waits - a run that did not work looking exactly
like a run that did, which is this repository's recurring defect. So the builder
imports the module afterwards and refuses to say READY unless CUDA is really
there, and `test_the_check_fails_when_cuda_is_absent` constructs that failure
rather than trusting that it would be caught.
"""

import unittest
from pathlib import Path

import support  # noqa: F401  - installs the suite's sandbox fences

REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPES = REPO_ROOT / "recipes"

import importlib.util as _util
_spec = _util.spec_from_file_location(
    "build_recipe_env", REPO_ROOT / "scripts" / "build_recipe_env.py"
)
builder = _util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(builder)


def _with_a_lockfile():
    return sorted(
        d.name for d in RECIPES.iterdir()
        if d.is_dir() and (d / "requirements.lock").is_file()
    )


class ARecipeSaysHowToBuildItsEnvironmentTest(unittest.TestCase):
    def test_there_are_recipes_with_lockfiles_to_check(self):
        """The positive control for the class. Without it every assertion below
        passes vacuously the day `recipes/` is empty or renamed."""
        self.assertTrue(
            _with_a_lockfile(),
            "no recipe ships a requirements.lock, so this file checks nothing.",
        )

    def test_every_recipe_with_a_lockfile_declares_its_environment(self):
        for name in _with_a_lockfile():
            with self.subTest(recipe=name):
                env = builder.declaration(name)
                self.assertTrue(
                    str(env.get("python") or "").strip(),
                    f"{name} declares [environment] without a python version.",
                )
                before = env.get("before_lock") or []
                self.assertTrue(
                    before,
                    f"{name} declares nothing to install before the lockfile. "
                    "If that is genuinely right, say so with an empty list on "
                    "purpose; every recipe here needs torch from a non-PyPI "
                    "index and getting it from PyPI fails silently.",
                )
                for step in before:
                    self.assertTrue(step.get("requirement"), f"{name}: a before_lock step with no requirement")
                    self.assertTrue(
                        str(step.get("why") or "").strip(),
                        f"{name}: a before_lock step that does not say WHY it "
                        "cannot come from the lockfile like everything else.",
                    )

    def test_every_declaration_names_something_to_verify(self):
        """A build that cannot check itself is a build that reports success for
        a CPU-only wheel."""
        for name in _with_a_lockfile():
            with self.subTest(recipe=name):
                want = builder.declaration(name).get("verify") or {}
                self.assertTrue(
                    str(want.get("import_module") or "").strip(),
                    f"{name} declares no [environment.verify].import_module, so "
                    "the builder would call it READY without importing anything.",
                )

    def test_the_check_fails_when_cuda_is_absent(self):
        """THE CONTROL. `verify` must go False on the failure it exists for.

        Constructed rather than imagined: the same real interpreter is asked for
        a module that has no `cuda` attribute at all, under a declaration that
        says expect_cuda. If this ever passes, the READY line means nothing.
        """
        ready = [n for n in _with_a_lockfile() if builder.interpreter(n).exists()]
        if not ready:
            self.skipTest(
                "no recipe environment is built on this machine, so there is no "
                "interpreter to run the control against"
            )
        name = ready[0]
        self.assertFalse(
            builder.verify(name, {"verify": {"import_module": "json",
                                             "expect_cuda": True}}),
            "verify() said an environment was fine when the module it imported "
            "reports no CUDA at all. The READY line is not checking anything.",
        )
        # And the other direction, so this is not a function that only says no.
        self.assertTrue(
            builder.verify(name, {"verify": {"import_module": "json",
                                             "expect_cuda": False}}),
            "verify() refuses an environment it was asked nothing about.",
        )


if __name__ == "__main__":
    unittest.main()
