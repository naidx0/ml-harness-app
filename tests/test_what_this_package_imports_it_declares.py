"""Every third-party module `app/` imports is declared in `pyproject.toml`.

This is a class of defect, not an incident. Three have shipped so far and all
three had the same shape: a module that happened to be installed in the
developer's interpreter was imported, worked, was tested, was committed, and was
never declared - so the install instruction in `start.sh` produced a tree that
could not start on anybody else's machine.

* `markdown` - used by the plan page, undeclared. Found in August and added.
* `python-multipart` - `POST /ui/intake` takes `Form(...)` fields, which FastAPI
  refuses to build a route from without a multipart parser. It raises at IMPORT
  time, so the failure is not "the form 500s", it is `import app.main` raising
  and no engine at all. Found on 2026-08-27 by installing this project into a
  clean interpreter, which is the only way any of the three were ever found.
* `httpx2` - not a runtime import; `tests/support.py` needs it to build a
  `TestClient`. The gate every step passes needs it, so it is declared as the
  `test` extra and asserted below in its own case.

**Why this test rather than more care.** `AGENTS.md` requires the full suite to
pass before a commit, and the suite passes on a machine where the undeclared
package is installed. That is exactly the shape `docs/PHASES.md` records under
*"a bound that only ever pushes in one direction cannot see the failure in the
other"* - every existing check ran the code, and running the code is satisfied
by an interpreter that happens to have the module. Nothing compared the imports
against the declaration.

**Two kinds of import, and the difference is the whole design.** A module
imported at MODULE level in `app/` is a hard dependency: the package will not
import without it, so it must be declared. A module imported INSIDE a function
may be deliberately optional, and this repository has exactly one such family -
`app/tools/classical.py` imports sklearn and numpy inside the handler, behind a
check that refuses with a sentence naming what is missing, precisely so that
neither becomes a runtime dependency of the whole product. That file's docstring
is the argument. So this test asserts the optional set is a KNOWN set, and that
every member of it is imported only from inside a function - an optional import
that migrates to module level turns into a hard dependency silently, and that is
the same defect from the other direction.

The import walk is an AST walk rather than an import: importing `app.main` to
see what it needs is the circular version of this question, and it would pass on
the very machine where the answer is wrong.
"""

import ast
import pathlib
import sys
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"


def _declared() -> dict[str, set[str]]:
    """The distribution names in `pyproject.toml`, runtime and per extra."""
    document = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = document["project"]

    def names(requirements: list[str]) -> set[str]:
        found = set()
        for requirement in requirements:
            # "httpx2>=2.0" -> "httpx2". Enough for the shapes this file uses;
            # a full PEP 508 parser is a dependency, which is the joke.
            name = requirement.split(";")[0].strip()
            for separator in ("<", ">", "=", "!", "~", "["):
                name = name.split(separator)[0]
            found.add(name.strip().lower().replace("_", "-"))
        return found

    declared = {"": names(project.get("dependencies", []))}
    for extra, requirements in project.get("optional-dependencies", {}).items():
        declared[extra] = names(requirements)
    return declared


# The distribution a module name comes from, where the two differ. Only modules
# this project actually imports need an entry; an unknown third-party module
# fails the test rather than being guessed at, because a guess here would be the
# same "it works on my machine" the test exists to refuse.
DISTRIBUTION = {
    "fastapi": "fastapi",
    "markdown": "markdown",
    "multipart": "python-multipart",
    "pydantic": "pydantic",
    "starlette": "starlette",
    "uvicorn": "uvicorn",
    "yaml": "pyyaml",
}

# Declared by something we declare, and imported directly. FastAPI depends on
# both and re-exports from them, so importing them is not an undeclared
# dependency in the sense this test is about - it is using what FastAPI brought.
BY_A_DECLARED_PACKAGE = {"pydantic", "starlette"}

# Deliberately NOT declared, imported from inside a handler, and refused with a
# sentence that names them when they are absent. See the module docstring of
# `app/tools/classical.py`: "A module-level import here would have made sklearn
# a runtime dependency of the whole product by accident."
OPTIONAL = {"numpy", "sklearn"}


def _top_level_imports(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # `from . import x` and `from .thing import y` have level > 0 and
            # are this package talking to itself.
            if node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found


def _module_level(tree: ast.Module) -> set[str]:
    """Imports at the top level of the file, and at class body level - the ones
    that run on `import`. An import inside a function does not."""
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found |= _top_level_imports(node)
        elif isinstance(node, (ast.If, ast.Try, ast.ClassDef, ast.With)):
            # `if TYPE_CHECKING:` and `try: import x` still run on import.
            for inner in ast.walk(node):
                if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    found |= _top_level_imports(inner)
    return found


def _third_party(paths: list[pathlib.Path], *, module_level_only: bool):
    """module name -> the files that import it, for non-stdlib, non-local."""
    local = {"app", "tests", "support", "scripts"}
    stdlib = set(sys.stdlib_module_names)
    who: dict[str, set[str]] = {}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        modules = _module_level(tree) if module_level_only else _top_level_imports(tree)
        for module in modules:
            if module in stdlib or module in local or module.startswith("_"):
                continue
            who.setdefault(module, set()).add(path.relative_to(ROOT).as_posix())
    return who



#: The package's own source, WITHOUT the build artifact inside it.
#:
#: `app/_bundled/` is written by `setup.py` at build time - the ledgers, and now
#: the recipe definitions. The recipe entrypoints under it import torch, trl,
#: peft and friends, and NONE of those is a dependency of this package: a
#: recipe's entrypoint is argv[1] to the recipe's own virtualenv and is never
#: imported by this interpreter. `app/identity.py` excludes `_bundled` from the
#: code fingerprint for the same reason, and a walk that disagreed with it would
#: be two opinions about what this package's source is.
def _package_sources() -> list[pathlib.Path]:
    return sorted(
        path
        for path in (ROOT / "app").rglob("*.py")
        if "_bundled" not in path.parts
    )


class WhatTheRuntimeImportsTest(unittest.TestCase):
    def test_every_third_party_import_in_app_is_declared(self):
        declared = _declared()[""]
        imports = _third_party(
            _package_sources(), module_level_only=True
        )

        undeclared: dict[str, set[str]] = {}
        for module, files in imports.items():
            if module in BY_A_DECLARED_PACKAGE:
                continue
            self.assertNotIn(
                module,
                OPTIONAL,
                f"{module} is optional-by-design and is imported at MODULE "
                f"level in {sorted(files)}, which makes it a hard dependency "
                f"of the whole product. Move it back inside the handler, or "
                f"declare it in its own step.",
            )
            distribution = DISTRIBUTION.get(module)
            self.assertIsNotNone(
                distribution,
                f"{module} is imported by {sorted(files)} and this test has no "
                f"entry for which distribution ships it. Add it to "
                f"DISTRIBUTION (and to pyproject, if it is really a new "
                f"dependency - AGENTS.md: a new dependency gets its own step).",
            )
            if distribution not in declared:
                undeclared[module] = files

        self.assertEqual(
            {},
            undeclared,
            "imported by app/ and not declared in pyproject.toml - an install "
            "on any machine that does not happen to have these already will "
            "fail, and the suite will not notice because this machine has them",
        )

    def test_the_form_parser_is_not_declared_because_nothing_takes_a_form(self):
        """THE PROMPT THIS PAIR ASKED FOR, FOLLOWED. Both directions.

        The version of this that shipped said: *"If `Form(...)` ever leaves
        `app/main.py`, this case going red is the prompt to ask whether the
        dependency is still owed - it is not licence to drop it without checking
        the rest of the tree."*

        `docs/THE_PLAN.md` V.3 A9 retired `POST /ui/intake`, which was the only
        thing that took form fields. The tree WAS checked - no `Form(`, no
        `File(`, no `UploadFile` anywhere under `app/` - and `python-multipart`
        came out with its reason recorded in `pyproject.toml` where the old
        reason stood.

        So this asserts the pair rather than one half: the dependency is gone
        AND nothing has grown a form behind its back. A form arriving without
        the dependency coming back does not fail on the form - it raises at
        IMPORT time, so there is no engine at all - which is exactly why this
        is checked from the other side too.
        """
        self.assertNotIn("python-multipart", _declared()[""])

        takers = []
        for path in _package_sources():
            if "__pycache__" in path.parts:
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            for marker in ("Form(", "File(", "UploadFile"):
                if marker in source:
                    takers.append(f"{path.relative_to(ROOT)}: {marker}")
        self.assertEqual(
            takers,
            [],
            "something takes form fields again and python-multipart is not "
            "declared. That does not break the route - it raises on `import "
            "app.main`, so there is no engine at all. Put the line back in "
            "pyproject.toml with the route named in its comment.",
        )


class WhatIsOptionalOnPurposeTest(unittest.TestCase):
    """The other direction: the optional set is closed, and every member of it
    is refused with a sentence rather than an ImportError."""

    def test_the_optional_imports_are_exactly_the_known_ones(self):
        declared = _declared()[""]
        every = _third_party(
            _package_sources(), module_level_only=False
        )
        inside_only = {
            module
            for module in every
            if module not in declared
            and DISTRIBUTION.get(module, module) not in declared
            and module not in BY_A_DECLARED_PACKAGE
        }
        self.assertEqual(
            OPTIONAL,
            inside_only,
            "app/ imports a third-party module that is neither declared nor a "
            "known optional. Either declare it in its own step, or add it to "
            "OPTIONAL here with the refusal that covers its absence.",
        )

    def test_an_absent_optional_is_a_refusal_and_not_a_traceback(self):
        """`available()` is the check in front of the import, and the refusal it
        guards names what is missing. Asserted against the real function so this
        cannot be satisfied by a comment."""
        from app.tools import classical

        have = classical.available()
        for module in sorted(OPTIONAL):
            self.assertIn(
                module,
                have,
                "available() is what stands between an absent optional and an "
                "ImportError, so every optional this test knows about has to "
                "be one of the things it reports on",
            )
            self.assertIsInstance(have[module], bool)
        source = (ROOT / "app" / "tools" / "classical.py").read_text(encoding="utf-8")
        self.assertIn("no_estimator", source)
        self.assertIn("pip install ", source)


class WhatTheGateNeedsTest(unittest.TestCase):
    def test_the_test_client_library_is_declared_as_an_extra(self):
        """`pip install -e .` gives you a working engine; running the gate needs
        one more thing, and `pip install -e .[test]` is the sentence that says
        which. It is an extra rather than a runtime dependency because shipping
        an HTTP client to every user so that we can run our own tests would be
        the wrong trade in the other direction."""
        extras = _declared()
        self.assertIn("test", extras)
        self.assertIn("httpx2", extras["test"])

    def test_the_suite_really_does_need_it(self):
        """Asserted from `tests/support.py` rather than from memory: it is the
        `TestClient` construction that pulls the library in."""
        source = (ROOT / "tests" / "support.py").read_text(encoding="utf-8")
        self.assertIn("TestClient", source)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class WhatThePackageREADSItDeclaresTest(unittest.TestCase):
    """Imports were half of it. The other half is the files.

    `WhatTheRuntimeImportsTest` above found two dependencies this package used
    and never declared, by parsing every import in `app/`. The same class of
    defect exists one layer down and nothing looked for it: a module that
    resolves a path INSIDE its own package and reads it at run time is
    depending on a file, and a file has to be declared too or the wheel drops
    it in silence.

    Measured on 2026-08-28, before this test existed: a wheel built from
    `pyproject.toml` carried 23 entries for `app/instructions` and ZERO for
    `app/model_configs`, whose 27 JSON files `app/feasibility.py` reads to size
    a training run. `pip install -e .` hid it completely, because an editable
    install points back at the checkout - so the only way to see it was to
    build the artefact and look inside, which is what A1 of `docs/THE_PLAN.md`
    is about.

    THIS TEST DOES NOT BUILD A WHEEL. It reads the declaration instead, because
    the failure is a missing declaration and a build takes seconds the gate
    should not spend. What it cannot catch is a declaration that is present and
    wrong; the packaging step's own acceptance is a real install on a clean
    interpreter, and that is named in the plan rather than pretended here.
    """

    #: Directories under `app/` that are read at run time and are therefore
    #: package data. Each one is resolved in product code as
    #: `Path(__file__).parent / <name>`; the test below finds those sites by
    #: AST rather than trusting this list to be complete.
    def _package_data(self) -> dict:
        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        return (config.get("tool", {}).get("setuptools", {}) or {}).get(
            "package-data", {}
        ) or {}

    def _sibling_directories_read_at_runtime(self) -> set[str]:
        """Every `Path(__file__).resolve().parent / "<name>"` in `app/`.

        `.parent`, not `.parents[1]` - one step up from a module is still inside
        the package, and that is exactly the shape that must be shipped. The
        `parents[1]` sites are a different and larger question (the ledger lives
        in `docs/`, named by 107 files) and it is written down as an open fork
        in `docs/THE_PLAN.md` rather than guessed at here.
        """
        found: set[str] = set()
        for path in _package_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Div):
                    continue
                if not isinstance(node.right, ast.Constant):
                    continue
                if not isinstance(node.right.value, str):
                    continue
                source = ast.unparse(node.left)
                if source.endswith("__file__).resolve().parent") or source.endswith(
                    "__file__).parent"
                ):
                    found.add(node.right.value)
        return found

    def test_the_sweep_finds_something(self):
        """Non-vacuity, the way every other sweep in this suite carries one."""
        self.assertIn("model_configs", self._sibling_directories_read_at_runtime())

    def test_every_directory_the_package_reads_beside_itself_is_declared(self):
        globs = " ".join(
            pattern
            for patterns in self._package_data().values()
            for pattern in patterns
        )
        undeclared = sorted(
            name
            for name in self._sibling_directories_read_at_runtime()
            if name not in globs
        )
        self.assertEqual(
            undeclared,
            [],
            "these directories are read out of the installed package and are not "
            "in [tool.setuptools.package-data], so a wheel ships without them and "
            "only an editable install works",
        )
