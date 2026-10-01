"""The README's code blocks are executed verbatim, by the tool that already did it.

## WHAT THIS FILE GOT WRONG FIRST, AND IT IS THE POINT

The first version of this file ran four usage lines I wrote MYSELF, resembling
the README's, with names I injected so they would work. I then reported that I
had "run all four to check rather than reading them". **That was not true.** I
ran four paraphrases of my own devising; the README's own block did not run at
all - `assert_ran(discovered, ran, unimported=modules)` names three variables
that do not exist, and a `with` statement whose body is `...`.

Upstream had already found this and fixed it properly. `tools/run_readme.py`
exists there, its docstring says **VERBATIM MEANS VERBATIM - no preamble is
added, no names are injected, nothing is wrapped**, and it runs on every push on
two Python versions. Its opening paragraph records why: *two of the four usages
in this README did not work*, found by a person on a fresh machine typing them
in.

So I reinvented a check that already existed, and reinvented it weaker, in a
repository whose own law is **call the function; a copy is a fork that agrees
for now**. The check I wrote could not have caught the bug the real one was built
for, because injecting the names is precisely what hides it.

This file now calls that tool. The paraphrases are gone.

## WHY THE ENVIRONMENT DIFFERS AND THE CODE DOES NOT

Upstream's CI `pip install`s the package before running the blocks. Nothing
installs it here - the harness puts the package root on `sys.path` instead - so
the subprocess needs `PYTHONPATH` to find it. That is an environment difference
and not a difference in the block, and saying so is the whole of the fix.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
README = PACKAGE / "README.md"
TOOL = PACKAGE / "tools" / "run_readme.py"


def run_the_tool(*args: str) -> int:
    """Call `tools/run_readme.py` in-process, from the package directory.

    `cwd` matters: the tool copies `pyproject.toml` and `README.md` beside each
    block so a block may read a file the package ships, and `witness(
    "pyproject.toml")` in the README depends on exactly that.
    """
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("run_readme", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    was_cwd = os.getcwd()
    was_path = os.environ.get("PYTHONPATH")
    try:
        os.chdir(PACKAGE)
        # The subprocess inherits this; nothing else makes the package importable
        # in a checkout that has not installed it.
        os.environ["PYTHONPATH"] = str(PACKAGE)
        return module.main(list(args))
    finally:
        os.chdir(was_cwd)
        if was_path is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = was_path


class TheReadmeBlocksRunVerbatimTest(unittest.TestCase):
    """THE CASE."""

    def test_the_tool_is_here(self):
        """Vendored from upstream rather than rewritten. If it goes missing, the
        rest of this file is testing nothing."""
        self.assertTrue(TOOL.is_file(), "tools/run_readme.py is not in this copy")

    def test_every_python_block_in_the_readme_runs(self):
        self.assertEqual(run_the_tool("README.md"), 0, "a README block did not run")

    def test_the_runner_can_go_red(self):
        """`--plant` appends a deliberately wrong block to a COPY and requires a
        failure. A gate you cannot make fail is not a gate, and this one ships
        its own red case rather than needing me to invent one."""
        self.assertEqual(run_the_tool("README.md", "--plant"), 0,
                         "the planted wrong block was not caught")

    def test_a_readme_with_no_blocks_is_refused_rather_than_passed(self):
        """A runner that finds nothing and passes is the failure this whole
        package is about. Upstream returns 2; this asserts it still does."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "README.md"
            empty.write_text("# nothing executable here\n", encoding="utf-8")
            self.assertEqual(run_the_tool(str(empty)), 2)


class TheBlockIsRunnableAndNotProseTest(unittest.TestCase):
    """The pseudocode block this copy used to carry, kept out by assertion."""

    def block(self) -> str:
        text = README.read_text(encoding="utf-8")
        fence = text.index("```python\nfrom four_asserts import")
        start = text.index("\n", fence) + 1  # past the fence line itself
        return text[start: text.index("```", start)]

    def test_it_does_not_name_variables_it_never_defines(self):
        block = self.block()
        for ghost in ("assert_ran(discovered, ran", "void_unless(verdicts)"):
            with self.subTest(ghost=ghost):
                self.assertNotIn(ghost, block, "the pseudocode block came back")

    def test_it_compiles(self):
        compile(self.block(), "README", "exec")

    def test_it_prints_something_a_reader_can_compare(self):
        """An example that runs and shows nothing teaches less than one that
        does. Upstream's block prints each result."""
        self.assertIn("print(", self.block())


class TheDescriptionKeptUpWithTheCodeTest(unittest.TestCase):
    """Prose is not executable, so it is checked the only way prose can be."""

    def test_it_says_the_named_span_is_the_claim(self):
        self.assertIn("span the reason names", README.read_text(encoding="utf-8").lower())

    def test_it_says_a_rule_may_take_the_reason(self):
        text = README.read_text(encoding="utf-8").lower()
        self.assertIn("third argument", text)
        self.assertIn("two-argument rules are unchanged", text)

    def test_the_numbers_it_quotes_carry_their_denominators(self):
        """Not that the runs happened - this cannot see them - but that no
        number is printed bare. A count without its denominator is a ceiling."""
        text = " ".join(README.read_text(encoding="utf-8").split())
        for claim in ("19 of 19", "3 of 170 genuine degradations", "up from 14"):
            with self.subTest(claim=claim):
                self.assertIn(claim, text)


if __name__ == "__main__":
    unittest.main()
