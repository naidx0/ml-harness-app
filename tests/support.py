"""Shared test scaffolding: the token, the sandbox, the fixture recipes.

Four things live here, all of them because the alternative was copying them
into a dozen files - and the last two are here because that copying is not a
tidiness problem, it is how a shared global goes unisolated in exactly one of
the dozen.

**`auth_headers()` / `api_client()`** - the token a test presents. It comes
from `security.current_token()`, which is the same value the engine accepts and
the same value it writes to `engine.json`. There is no test-only bypass, no
`DEBUG=1` that skips the check, and no keychain in the path: a bypass is a
second door, and a second door is the one nobody remembers to lock.

**`sandbox()`** - one call that gives a test its own database *and* its own
artifact root. Both, together, because isolating one and not the other is what
produced a flake that lived in the repository for two days: every test class
rebound `db.DB_PATH` into a temp directory, so every test's first job was id 1,
and the runner keyed its log on the job id under a shared repo-level `logs/`
folder. Twelve test classes therefore wrote `logs/job_1.log`, and whichever
finished last owned it. The product half of that is fixed in `app/db.py` and
`app/jobspec.py`; this is the half that stops a test asserting against a global
in the first place, and it lives here so there is one temp-dir dance rather
than one per test class.

**`recipe_fixtures()`** - a temporary `recipes/` tree. The runner's failure
paths (a job that hangs, a job that writes to stderr, a job that exits 3) used
to be expressed as shell strings, which is exactly the capability that was
removed. They are expressed as fixture recipes now. Note what this does *not*
do: it does not register anything at runtime and there is no API for a request
to add a recipe. It rebinds `jobspec.RECIPES_ROOT`, the same module-level
rebinding the suite already does with `db.DB_PATH`, so the allowlist a request
is checked against is still just "the directories on disk".

**`PROTECTED_DATABASES` / `database_fingerprint()` / `free_port()`** - the
fence around the user's real data, and the one thing a test needs in order to
stay outside it. `sandbox()` isolates a test that opens the database *in this
process*; it can do nothing about a test that starts a subprocess, because the
subprocess resolves `db.DB_PATH` for itself and never sees the parent's
rebinding. That is not hypothetical: `tests/test_demo_script_runs.py` ran
`scripts/demo_train.py` against whatever engine was listening on the default
port, which on the owner's machine was the real one, and the real
`ml_harness.db` now holds 1,036 runs named `demo-loss-curve`. The fix is for
such a test to start an engine of its own with `ML_HARNESS_DB` set; these three
helpers are what let it do that and then prove it did.

## WHAT A HARNESS'S CONVENIENCES DECIDE, WHICH IS MORE THAN CONVENIENCE

A first-gate bypass sat in `evidence.record` for three commits with 1057 tests
green over it. The finder's account of why: *"the suite cannot see it because
`support.sandbox()` gives every test a clean ledger and tests always pass a
thread_id."*

That is a statement about this file. A harness whose conveniences all point the
same way produces a suite that agrees with itself: every test starts from one
clean database, one empty artifact root, no prior conversation and no prior
history, and reaches the product through call sites that all supply the same
arguments. Every one of those is a shape a real caller does not have, and each
one is a family of defects the suite is structurally unable to see - not a
missing case somebody can be asked to add.

So the four blocks below the original four exist to make the UNUSUAL call as
cheap to write as the usual one. A test that wants two conversations, a database
with history, two callers at once, or a look at what the product wrote outside
its sandbox should not have to build any of it.

**`conversations()`** - N threads in N projects, in one line. THE SUITE HAD ONE
CONVERSATION, so no test in it could tell a thread-scoped record from a global
one; both look identical when there is only ever one thread to see. The eval-set
leak was that, and it is not the only unscoped table in the product.

**`with_history()`** - a database that is not new. Every test's first run is run
1, its first job is job 1 and its first thread is thread 1, so nothing in the
suite distinguishes "keyed on identity" from "keyed on a counter that restarts
at 1 in every database" - which is exactly the confusion `db.get_instance` was
minted to end, found only after two unrelated jobs shared a log file.

**`concurrently()`** - run callables at once and collect what each one got.
Nothing in the suite calls two things at the same time except
`test_migrations_survive_concurrency`, so every read-then-write race in the
product is untested by construction.

**`SANDBOXED_PATH_GLOBALS` / `READ_ONLY_PATH_GLOBALS` / `repo_path_globals()` /
`tree_fingerprint()`** - the fence around the working tree, and the reason
`sandbox()` now binds six globals rather than three. `db.DB_PATH`,
`jobspec.RECIPES_ROOT` and `jobspec.RUNS_ROOT` were isolated;
`feasibility.MODEL_CONFIG_ROOT`, `tools.models.HUB_CACHE_ROOT` and
`security.ENGINE_FILE` were not, and the first of those is a git-TRACKED
directory. `read_model_config` - a registered tool a model may call with no
approval - writes into it, so a test calling that tool inside `sandbox()` wrote
a file into the user's checkout. Each of those three was isolated by hand in
exactly the one test class whose author thought about it and by nothing else,
which is the eleven-and-the-twelfth shape twice over. `repo_path_globals()`
derives the list from the modules rather than repeating it, so the next one is
caught by `tests/test_the_sandbox_isolates_everything_the_product_writes.py`
instead of by whoever notices their checkout is dirty.
"""

from __future__ import annotations

import faulthandler
import hashlib
import importlib
import os
import pkgutil
import socket
import sys
import sqlite3
import tempfile
import traceback
import textwrap
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path, PurePath

from fastapi.testclient import TestClient

from app import db, jobspec, security


REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# A hung test is a named stack trace, not a slow suite
# ---------------------------------------------------------------------------

#: How long one test may take before the suite treats it as hung.
#:
#: `docs/PHASES.md` carried this as a debt in as many words: *"A hanging test
#: presents as a slow suite. There is no per-test bound, and 3,000 tests at ~4.5
#: minutes under a 600-second timeout means hung and slow differ by a factor
#: nobody has had to think about."* The suite's own worst case is a few seconds;
#: sixty is twenty times that and still a twentieth of the run.
#:
#: It is a WALL-CLOCK bound and it will therefore fire on a machine that is
#: merely very slow. That is the trade, taken deliberately: what it prints is a
#: stack trace naming the test and the line, which on a slow machine is an
#: inconvenience and on a hang is the only thing that answers "which one".
TEST_TIME_BUDGET_SECONDS = float(os.environ.get("MLH_TEST_TIMEOUT", "60"))


def _bound_every_test() -> None:
    """Arm `faulthandler` around every test in this process, once.

    THE PATCH IS ON `unittest.TestCase.run` AND THAT IS WHY IT IS GLOBAL. The
    suite runs in one process, so the first module that imports this one arms
    the bound for every test that runs after it - including the forty-odd
    modules that never import `support` at all. That is the only mechanism
    available under plain `python -m unittest discover`, which has no hook of
    its own and no conftest.

    `exit=False`, so a test that trips the bound prints its stack and the run
    carries on. Killing the interpreter would turn one hung test into no results
    at all, which is the state this exists to get out of.
    """
    if getattr(unittest.TestCase, "_mlh_time_bounded", False):
        return

    original = unittest.TestCase.run

    def run(self, result=None):  # type: ignore[no-untyped-def]
        faulthandler.dump_traceback_later(
            TEST_TIME_BUDGET_SECONDS,
            exit=False,
            file=sys.stderr,
        )
        try:
            return original(self, result)
        finally:
            faulthandler.cancel_dump_traceback_later()

    unittest.TestCase.run = run  # type: ignore[method-assign]
    unittest.TestCase._mlh_time_bounded = True  # type: ignore[attr-defined]


_bound_every_test()


def _protected_databases() -> tuple[Path, ...]:
    """The database files a test must never open. Real data lives in them.

    Two entries, not one, because "the real database" is not a fixed path.
    `app/db.py` resolves `DB_PATH` from `ML_HARNESS_DB` and falls back to
    `<repo>/ml_harness.db`, so on a machine where that variable is set the
    user's data is somewhere else entirely and a guard that only knows the
    repo-root path would wave it straight through.

    The variable is read once, here, at import - before any test has had the
    chance to set it for a child process it is about to start. A test that
    hands `ML_HARNESS_DB=<temp>` to a subprocess is doing the right thing and
    must not thereby move the fence.
    """
    paths = [REPO_ROOT / "ml_harness.db"]
    from_env = os.environ.get("ML_HARNESS_DB")
    if from_env:
        candidate = Path(from_env)
        if candidate.resolve() != paths[0].resolve():
            paths.append(candidate)
    return tuple(paths)


#: See `_protected_databases`. Read by `test_tests_do_not_touch_the_real_database`.
PROTECTED_DATABASES: tuple[Path, ...] = _protected_databases()


def database_fingerprint(path: Path) -> tuple[int, int, str] | None:
    """`(size, mtime_ns, sha256)` for `path`, or `None` if it is not there.

    All three, because each one alone can be fooled: a SQLite page rewritten in
    place can keep the size, a filesystem with coarse timestamps can keep the
    mtime, and a file that is deleted and rebuilt can keep both. The hash is
    the one that actually answers "is this the same data", and hashing a couple
    of megabytes twice per suite run costs nothing worth counting.
    """
    path = Path(path)
    try:
        stat = path.stat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime_ns, digest)


def free_port() -> int:
    """A loopback port nothing is listening on, for a test that starts a server.

    Bind to port 0, ask the OS what it picked, release it. There is a window
    between releasing and rebinding in which something else could take the
    port; it is small, and the alternative - a hardcoded port - is not a
    smaller risk but a certain collision with the engine the user has running.
    """
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# ---------------------------------------------------------------------------
# The fence around the working tree.


#: Module-level path globals the product WRITES THROUGH, and which `sandbox()`
#: therefore rebinds. `(module, attribute, why it is rebound)`.
#:
#: `db.DB_PATH`, `RECIPES_ROOT` and `RUNS_ROOT` were the whole list, and the
#: list was wrong by three. The other three name places inside the repository
#: that product code opens for writing on a path a *registered tool* can reach,
#: and each was isolated by hand in exactly one test class:
#: `MODEL_CONFIG_ROOT` in `test_model_geometry_is_read_not_assumed`,
#: `HUB_CACHE_ROOT` in `test_model_fit_ranker`, `ENGINE_FILE` by every caller
#: remembering to pass `path=`. Everywhere else in 1057 tests they pointed at
#: the user's checkout.
SANDBOXED_PATH_GLOBALS: tuple[tuple[str, str, str], ...] = (
    (
        "app.db",
        "DB_PATH",
        "every table in the product. Not restored on cleanup - see sandbox().",
    ),
    (
        "app.jobspec",
        "RECIPES_ROOT",
        "the allowlist a job request is checked against, as directories on disk",
    ),
    (
        "app.jobspec",
        "RUNS_ROOT",
        "job logs and run artifacts; the b024da4 collision lived here",
    ),
    (
        "app.feasibility",
        "MODEL_CONFIG_ROOT",
        "store_model_config() writes here, reached from the read_model_config "
        "tool, and the directory is TRACKED IN GIT",
    ),
    (
        "app.tools.models",
        "HUB_CACHE_ROOT",
        "_cache_write() writes here on any hub fetch; per-machine and volatile, "
        "so the sandbox copy starts EMPTY and no test can inherit a cache hit "
        "the developer's machine happened to have",
    ),
    (
        "app.security",
        "ENGINE_FILE",
        "write_portfile() publishes the live engine's port and bearer token "
        "here when no path= is passed",
    ),
)


#: Path globals inside the repository that the product only ever READS. Listed
#: rather than ignored, because "nothing writes here" is a claim a reviewer
#: should have to make on purpose - and because the derived test needs to tell
#: a global somebody considered from one somebody has not seen yet.
READ_ONLY_PATH_GLOBALS: tuple[tuple[str, str, str], ...] = (
    (
        "app.import_boundary",
        "_THIS_PACKAGE",
        "this package's own directory, used to tell the guard's own frames from "
        "the caller's while walking out of the import machinery. COMPARED AND "
        "NEVER OPENED: the only operations on it are `==` and `in .parents`. It "
        "is deliberately computed from `__file__` at import rather than named "
        "as a constant, because when this guard fires it may be the WRONG "
        "tree's copy running - a path baked into the source would be the wrong "
        "tree's opinion of itself, stated with total confidence, in the one "
        "situation the guard exists for.",
    ),
    (
        "app.tools.knowledge",
        "KNOWLEDGE_ROOT",
        "the freshness-stamped world snapshots (model ladder, GPU prices). "
        "Product code only READS them - every answer carries the file's own "
        "fetched_at. The one writer is scripts/refresh_knowledge.py, run by a "
        "person, which is why a test can never dirty the checkout through "
        "this path.",
    ),
    (
        "app.jobspec",
        "BUNDLED_RECIPES",
        "the package's own copy of the recipe definitions, written by "
        "`setup.py` at BUILD time and never by product code. THE_PLAN V.3 A1b "
        "split a recipe in two: the definition is package data and ships here, "
        "and the virtualenv is user data and does not - `jobspec.venv_for` "
        "sends an installed recipe's environment to the data root precisely so "
        "that nothing ever writes beside this path. In a checkout it does not "
        "exist at all until somebody builds a wheel, and `_recipes_root()` "
        "prefers the checkout whenever it is there, so the running product "
        "reads it only in an install.",
    ),
    (
        "app.paths",
        "CHECKOUT_MARKER",
        "the file that says 'this is a checkout and not an installed package'. "
        "RELATIVE, and never opened at all: `data_root()` joins it onto a "
        "candidate root and asks `.is_file()`, which is the whole of its use. "
        "It is the same marker `diagnosis._ledger_root` decides by, on purpose "
        "- two functions answering 'am I in a repository' by two different "
        "tests are two answers waiting to disagree on the machine where it "
        "matters. Read-only in the strongest sense available: nothing in this "
        "product ever takes a handle on it.",
    ),
    (
        "app.diagnosis",
        "LEDGER_ROOT",
        "where the ledgers are on THIS installation - the repository in a "
        "checkout, app/_bundled in an installed package. SPEC_PATH and "
        "LEDGERS_DIR are both computed from it, so it is the same read-only "
        "source they are, one level up. Nothing writes a ledger: setup.py's "
        "build step copies docs/ into the bundle, and that is a build, not the "
        "product",
    ),
    ("app.diagnosis", "SPEC_PATH", "the diagnosis spec is source; load_spec reads"),
    (
        "app.diagnosis",
        "LEDGERS_DIR",
        "docs/ledgers/ is source, the same way SPEC_PATH is - it is where the "
        "ledgers beyond the first one live, and `known_ledgers()` globs it so "
        "that adding a ledger takes one file and no second edit. Nothing in "
        "app/ ever opens it for writing: a ledger is authored, never generated.",
    ),
    ("app.instructions", "HERE", "the instruction set is source; only read"),
    (
        "app.identity",
        "REPO_ROOT",
        "used to find .git for the sha; read, never written",
    ),
    (
        "app.identity",
        "CODE_ROOT",
        "app/ itself, hashed to answer 'what code is this'. Read-only by "
        "construction: a fingerprint that wrote anything would change the "
        "thing it is measuring.",
    ),
    ("app.jobspec", "REPO_ROOT", "used to compose PYTHONPATH for a job"),
    ("app.security", "REPO_ROOT", "used to compose ENGINE_FILE's default"),
    ("app.tools.models", "REPO_ROOT", "used to compose HUB_CACHE_ROOT"),
)


def repo_path_globals() -> dict[tuple[str, str], Path]:
    """Every module-level path global in `app/` that names somewhere in the repo.

    DERIVED, NOT LISTED. The two rosters above say what to DO about each one;
    this says which ones exist, by importing every module under `app` and
    looking at what it holds. A global added next year is in this dict the day
    it is written, which is the only way the rosters can be checked rather than
    believed.
    """
    import app

    for info in pkgutil.walk_packages(app.__path__, "app."):
        try:
            importlib.import_module(info.name)
        except Exception:  # noqa: BLE001 - an unimportable module is not our news
            continue

    # Read the answer out of `sys.modules` rather than out of the walk. The walk
    # is what makes sure every module on disk has been imported; the registry is
    # what makes sure a module reached by any OTHER route is included too. A
    # check that only ever sees the files it went looking for is a check that
    # cannot be given a positive control.
    modules = [
        module
        for name, module in list(sys.modules.items())
        if module is not None and (name == "app" or name.startswith("app."))
    ]

    found: dict[tuple[str, str], Path] = {}
    for module in modules:
        for name in dir(module):
            if name.startswith("__"):
                continue
            try:
                value = getattr(module, name)
            except Exception:  # noqa: BLE001 - a property that raises is not a path
                continue
            if not isinstance(value, PurePath):
                continue
            try:
                resolved = Path(value).resolve()
            except OSError:
                continue
            if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
                found[(module.__name__, name)] = resolved
    return found


def process_state_snapshot() -> dict[tuple[str, str], int]:
    """`{(module, name): size}` for every module-level container in `app/`.

    A fresh database is not a fresh process, and this is what says so. `sandbox()`
    hands out a new temporary directory and a new SQLite file; it cannot hand out
    a new interpreter, so every module-level dict, set and list in `app/` carries
    whatever the last test put in it.

    Sizes rather than contents, because the question is *did this call leave
    something behind*, and a length answers it without holding references to
    objects a test is about to drop. Compared by
    `tests/test_process_state_does_not_outlive_a_test.py`, which derives the
    answer this way rather than from a list of names somebody maintains -
    the caches that matter are the ones nobody remembered to write down.
    """
    import app

    for info in pkgutil.walk_packages(app.__path__, "app."):
        try:
            importlib.import_module(info.name)
        except Exception:  # noqa: BLE001
            continue

    out: dict[tuple[str, str], int] = {}
    for name, module in list(sys.modules.items()):
        if module is None or not (name == "app" or name.startswith("app.")):
            continue
        for attribute in dir(module):
            if attribute.startswith("__"):
                continue
            try:
                value = getattr(module, attribute)
            except Exception:  # noqa: BLE001
                continue
            if type(value) in (dict, set, list):
                out[(name, attribute)] = len(value)
    return out


#: Directory names whose CONTENTS are fingerprinted structurally rather than by
#: bytes. A virtualenv is thousands of files nobody in this repository authored,
#: and hashing them is where this function's time goes.
UNHASHED_DIRS: frozenset[str] = frozenset({".venv"})


def _structural(directory: Path) -> tuple[int, str]:
    """Entry count, total bytes and newest mtime for a directory, cheaply.

    The three facts that a WRITE changes. The way anything writes into a
    virtualenv is by installing into it, and an install adds files and bytes and
    moves the newest mtime; there is no plausible route by which a test leaves
    all three identical. What is given up is an in-place same-size overwrite of
    an existing file inside a `.venv`, which is not a write pattern any test in
    this suite produces.
    """
    entries = 0
    total = 0
    newest = 0.0
    # `os.scandir` AND NOT `rglob`, because this is the whole cost. A DirEntry
    # carries the stat the directory listing already returned, so counting
    # 26,000 files costs one syscall per directory rather than one per file;
    # measured on this machine's `recipes/`, that is the difference between 21.9
    # seconds and 2.1 for the same three answers.
    stack = [str(directory)]
    while stack:
        try:
            with os.scandir(stack.pop()) as listing:
                for entry in listing:
                    entries += 1
                    try:
                        stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    newest = max(newest, stat.st_mtime)
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    else:
                        total += stat.st_size
        except OSError:
            continue
    return entries, f"entries={entries} bytes={total} newest={newest:.0f}"


def tree_fingerprint(root: Path) -> dict[str, tuple[int, str]]:
    """`{relative path: (size, sha256)}` for every file under `root`.

    The filesystem half of what `database_fingerprint` does for SQLite, and it
    exists for the same reason: `sandbox()` can only isolate a global this
    process holds, and cannot see a subprocess, a background thread that
    resolved the global before it moved, or a global nobody thought to bind.
    Comparing bytes answers "did anything write here" without needing to know
    who would have.

    ## Virtualenvs are fingerprinted structurally, ruled 2026-09-10

    MEASURED before it was changed: `tree_fingerprint("recipes")` walked 65,691
    entries in 74.9 s, and it runs at least twice per gate - once at module
    import for the baseline, once in the assertion - so **roughly 150 seconds of
    a 1,270-second gate was SHA-256ing about 14 GB of virtualenv**, for every
    lane, every run, growing with every environment anyone builds.

    Under the ruling, a directory named in `UNHASHED_DIRS` contributes ONE entry
    holding its count, its byte total and its newest mtime instead of a hash per
    file. **The guarantee the caller depends on survives** - see `_structural`
    for why - and the assertion message names which of the three moved, so a
    virtualenv rebuilt during a gate reads as
    `recipes/hf-quantize/.venv: entries=18061 -> entries=18062` rather than as a
    leak of unknown shape.

    **This is a weakening and it is recorded as one.** A byte-for-byte change
    inside a virtualenv that leaves count, size and newest mtime all unchanged
    is no longer noticed. That was the owner's trade to make and it was made
    explicitly rather than by a passing lane deciding the check was slow.
    """
    root = Path(root)
    out: dict[str, tuple[int, str]] = {}
    if not root.exists():
        return out
    if root.is_file():
        data = root.read_bytes()
        return {root.name: (len(data), hashlib.sha256(data).hexdigest())}
    # PRUNED RATHER THAN FILTERED. `sorted(root.rglob("*"))` materialises and
    # sorts every path under the root before anything is skipped, so filtering
    # afterwards still pays for the walk into 70,000 virtualenv files - which is
    # most of what the ruling was about.
    for directory, subdirectories, files in os.walk(root):
        here = Path(directory)
        for name in sorted(subdirectories):
            if name in UNHASHED_DIRS:
                child = here / name
                out[str(child.relative_to(root)).replace("\\", "/")] = _structural(child)
        subdirectories[:] = sorted(
            name for name in subdirectories if name not in UNHASHED_DIRS
        )
        for name in sorted(files):
            path = here / name
            try:
                data = path.read_bytes()
            except OSError:
                continue
            out[str(path.relative_to(root)).replace("\\", "/")] = (
                len(data),
                hashlib.sha256(data).hexdigest(),
            )
    return out


def auth_headers() -> dict[str, str]:
    """The `Authorization` header a legitimate local client sends."""
    return {"Authorization": f"Bearer {security.current_token()}"}


def api_client(app) -> TestClient:
    """A `TestClient` that authenticates, for tests that are not about auth."""
    return TestClient(app, headers=auth_headers())


#: Fixture recipes, each a (kinds, entrypoint source) pair. Between them they
#: cover every failure path the old shell-string tests covered, plus two the
#: old contract could not express at all.
FIXTURE_RECIPES: dict[str, tuple[tuple[str, ...], str]] = {
    # Prints a value that arrived in config. Proves the config round-trip:
    # caller data reaches the job through job.json, never through argv.
    "printer": (("train",), """
        import argparse, json
        p = argparse.ArgumentParser()
        p.add_argument("--kind"); p.add_argument("--job-json")
        a = p.parse_args()
        job = json.loads(open(a.job_json, encoding="utf-8").read())
        print(job["config"].get("message", ""))
        print("kind=" + a.kind)
    """),
    # Hangs. The timeout bound is measured against this.
    "sleeper": (("train",), """
        import time
        time.sleep(30)
    """),
    # Writes to stderr only.
    "noisy": (("eval",), """
        import sys
        sys.stderr.write("boom")
    """),
    # Produces nothing at all.
    "silent": (("prepare",), """
        pass
    """),
    # Fails with a specific code.
    "failing": (("train",), """
        import sys
        sys.exit(3)
    """),
    # Prints, then waits for a sentinel file, then prints again. The streaming
    # test needs a job that is still running when it looks at the log.
    "halting": (("train",), """
        import argparse, json, os, time
        p = argparse.ArgumentParser()
        p.add_argument("--kind"); p.add_argument("--job-json")
        a = p.parse_args()
        job = json.loads(open(a.job_json, encoding="utf-8").read())
        sentinel = job["config"]["sentinel"]
        print("first", flush=True)
        for _ in range(400):
            if os.path.exists(sentinel):
                break
            time.sleep(0.05)
        print("second", flush=True)
    """),
    # Declared in recipe.toml, absent on disk. The modern equivalent of the old
    # "binary does not exist" case, which a caller can no longer cause.
    "brokenentry": (("train",), None),
}


@contextmanager
def recipe_fixtures(root: Path):
    """Point `jobspec` at a fixture recipe tree and a fixture runs directory."""
    recipes = Path(root) / "recipes"
    recipes.mkdir(parents=True, exist_ok=True)
    for name, (kinds, source) in FIXTURE_RECIPES.items():
        directory = recipes / name
        directory.mkdir(parents=True, exist_ok=True)
        kind_list = ", ".join(f'"{k}"' for k in kinds)
        (directory / "recipe.toml").write_text(
            f'name = "{name}"\n'
            f"kinds = [{kind_list}]\n"
            'entrypoint = "entrypoint.py"\n',
            encoding="utf-8",
        )
        if source is not None:
            (directory / "entrypoint.py").write_text(
                textwrap.dedent(source).strip() + "\n", encoding="utf-8"
            )

    previous_recipes = jobspec.RECIPES_ROOT
    previous_runs = jobspec.RUNS_ROOT
    jobspec.RECIPES_ROOT = recipes
    jobspec.RUNS_ROOT = Path(root) / "runs"
    try:
        yield recipes
    finally:
        jobspec.RECIPES_ROOT = previous_recipes
        jobspec.RUNS_ROOT = previous_runs


_SHIPPED_CONFIGS: dict[str, bytes] | None = None


def _shipped_model_configs() -> dict[str, bytes]:
    """`{filename: bytes}` for the model configs the repository ships, read once.

    Read once per process and held, because `sandbox()` seeds them into every
    test's temporary directory and re-reading 80KB off disk several hundred
    times a run is work nobody asked for. They are source files: they do not
    change while the suite runs, and if one did, the suite is running against a
    tree somebody is editing underneath it.
    """
    global _SHIPPED_CONFIGS
    if _SHIPPED_CONFIGS is None:
        shipped = REPO_ROOT / "app" / "model_configs"
        _SHIPPED_CONFIGS = (
            {path.name: path.read_bytes() for path in sorted(shipped.glob("*.json"))}
            if shipped.is_dir()
            else {}
        )
    return _SHIPPED_CONFIGS


def _quiesce_process_state() -> None:
    """Put back the process-wide state a test can leave behind it.

    A fresh database is not a fresh process. Three things in `app/` outlive
    `sandbox()`'s temporary directory, and all three are keyed on a counter that
    RESTARTS AT 1 IN EVERY DATABASE - which is the confusion `db.get_instance`
    was minted to end for job ids, and it was not ended anywhere else.

    * `storm._LIVE` / `storm._CANCELLED` hold storm ids. A test that abandons
      `storm.run()`'s generator leaves an id behind, and the NEXT test's first
      storm has the same id in a database that has never seen it, so it is
      refused as "already running in this process".
    * `training._SUPERVISORS` holds live threads. A supervisor started by one
      test resolves `db.DB_PATH` when it next reads it, not when it started, so
      one still running when the next test rebinds the global writes job rows
      and events into an unrelated test's database. That is the b024da4 shape
      with a thread in place of a filename.

    Best-effort and quick on purpose: the join uses a short timeout because a
    supervisor that will not stop is a defect to report, not a reason to stall
    every remaining test for a minute.
    """
    try:
        from app.tools import training

        training.wait_for_supervisors(timeout=5.0)
    except Exception:  # noqa: BLE001 - cleanup must not mask the test's own failure
        pass
    try:
        from app import storm

        with storm._GUARD:
            storm._LIVE.clear()
            storm._CANCELLED.clear()
    except Exception:  # noqa: BLE001
        pass


def a_gpu_was_measured() -> bool:
    """Did `inspect_hardware` find a card on THIS machine?

    Several tests in this suite are about what the provenance walls do to a
    REAL measured number - they run `inspect_hardware`, take the `vram_gb` it
    stamped, and check that the same figure is released under the instrument
    that produced it and stopped under one that did not. On a machine with no
    GPU there is no such figure, so there is nothing to run the wall against:
    the test's subject is absent, not broken.

    That is the whole of why this exists, and the line it must not cross.
    Substituting a made-up VRAM figure so the test could proceed would be this
    suite inventing a measurement to test the wall that exists to stop
    invented measurements - so the tests skip and SAY SO, and every one of
    them names this function in its reason.

    Measured against every GitHub runner: no NVIDIA card, so `nvidia-smi`
    answers nothing and `vram_gb` is never stamped. Nine tests failed on both
    operating systems for this one reason in every CI run this repository has
    had.
    """
    from app import hwdetect

    return hwdetect.local_specs().get("vram_gb") is not None


#: Said once, so nine tests give one reason rather than nine paraphrases.
NO_GPU_HERE = (
    "this machine has no GPU that nvidia-smi can read, so inspect_hardware "
    "stamps no vram_gb and there is no measured number for this test to put "
    "through the wall - see support.a_gpu_was_measured"
)


def import_file(name: str, path: Path):
    """Import a module from a path WITHOUT writing bytecode beside it.

    THE DEFECT THIS CLOSES WAS ONLY EVER VISIBLE ON A FRESH CHECKOUT.
    `test_preferences_are_counted_not_claimed` loads
    `recipes/hf-peft-dpo/entrypoint.py` to prove the recipe's own refusal and
    the tool's reply send a person to the same place. `exec_module` compiles
    it, and CPython writes the result to
    `recipes/hf-peft-dpo/__pycache__/entrypoint.cpython-311.pyc` - inside the
    repository, under a path
    `test_the_sandbox_isolates_everything_the_product_writes` watches by its
    BYTES.

    On this machine that `.pyc` already existed from an earlier run, so the
    fingerprint did not move and the suite was green. On a runner, which
    checks out clean every time, it is created mid-run and the watcher
    correctly reports that the suite wrote into the working tree - which it
    did. It has failed on both operating systems in every CI run this
    repository has ever had.

    The fix is not to stop watching. `sys.dont_write_bytecode` is set for the
    duration of the import, which is the one line that makes the import leave
    nothing behind, and the watcher keeps its teeth.
    """
    import importlib.util
    import sys as _sys

    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:  # pragma: no cover - a bad path
        raise ImportError(f"no module could be loaded from {path}")
    module = importlib.util.module_from_spec(spec)
    was = _sys.dont_write_bytecode
    _sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        _sys.dont_write_bytecode = was
    return module


def sandbox(test) -> Path:
    """Give `test` its own database, recipes, artifact root and cache roots.

    Returns the temporary root, which is also where the fixture recipes and the
    fixture `runs/` tree live, so a test that needs a scratch path of its own
    can hang it off the same directory.

    What this binds is not a pile of conveniences, it is one invariant: **a test
    must not be able to reach any state a different test can reach, and must not
    be able to reach the user's checkout at all.** `db.DB_PATH` was already
    being isolated everywhere; `RUNS_ROOT` was isolated by `recipe_fixtures`;
    the job logs were not isolated at all, and that was the first gap. THE
    SECOND GAP WAS THREE MORE GLOBALS: `feasibility.MODEL_CONFIG_ROOT`,
    `models.HUB_CACHE_ROOT` and `security.ENGINE_FILE` all name places inside
    the repository that product code opens for writing, and `read_model_config`
    - a registered tool, `approval="never"`, reachable by a model - writes into
    the git-tracked first one. Binding them all in one function is what stops
    the next one of these from being isolated in eleven files and forgotten in
    the twelfth; `SANDBOXED_PATH_GLOBALS` is the list and
    `tests/test_the_sandbox_isolates_everything_the_product_writes.py` derives
    the globals independently and checks it.

    `MODEL_CONFIG_ROOT` is SEEDED with the configs the repository ships rather
    than left empty. Those files are source - tracked, reviewed, and read by
    tests that assert on real model geometry - so a sandbox that hid them would
    change what reading code sees in order to protect what writing code does.
    `HUB_CACHE_ROOT` is deliberately left EMPTY: it is gitignored per-machine
    network state, and a test that passes only because the developer's machine
    had a cached hub response is a test that fails on a fresh checkout.

    THE SEEDING COSTS ABOUT 8ms PER SANDBOX - six files, 82KB, measured - which
    is roughly 4% of this suite's wall time. It buys the invariant at the top of
    this docstring, unweakened: a shared seeded directory would be cheaper and
    would let one test see a model config another test stored. That is a smaller
    hole than writing into the checkout and it is still a hole, and trading the
    invariant for a few seconds is the shape of decision this whole file is a
    report about.

    Cleanup is registered with `addCleanup` rather than written into a
    `tearDown`, so a subclass that overrides `tearDown` and forgets to call
    `super()` still cannot leak the rebinding into the next test.

    `db.DB_PATH` is deliberately *not* restored afterwards, matching what every
    test class in this suite already does. Restoring it would point the global
    back at the real `ml_harness.db`, which turns "a test forgot to isolate its
    database" from a test that writes somewhere harmless into a test that
    writes the user's actual data. THE OTHER FIVE ARE RESTORED, and the
    asymmetry is deliberate: a dead temporary directory is not a safe default
    for a path other tests legitimately READ from - `ShippedConfigsTest` reads
    `MODEL_CONFIG_ROOT` and would see an empty directory - so the protection for
    those is the restore plus a watcher on the bytes, which is the same
    two-mechanism arrangement `test_tests_do_not_touch_the_real_database.py`
    uses for SQLite.
    """
    temp = tempfile.TemporaryDirectory()
    # RESOLVED, BECAUSE THE PRODUCT RESOLVES. On the GitHub Windows runner
    # `tempfile` hands back the 8.3 short form - `C:/Users/RUNNER~1/...` -
    # while every path the product stores has been through `.resolve()`, which
    # expands it to `C:/Users/runneradmin/...`. Four tests compared the two
    # spellings of one directory and failed on every CI run. They are the same
    # place; the fixture was naming it the other way.
    root = Path(temp.name).resolve()

    db.DB_PATH = root / "test.db"
    db.init_db()

    fixtures = recipe_fixtures(root)
    fixtures.__enter__()

    restore: list[tuple[object, str, object]] = []

    # NO MEMORY EXTRACTION IN A SANDBOX. `app/memory.extract_after_turn` runs
    # one more model call after an answered turn (2026-09-12); a scripted
    # provider in a conductor test would hand it the NEXT script, and every
    # test that counts calls would count one it did not make. The product
    # keeps it on; the sandbox turns it off and restores it.
    memory_module = importlib.import_module("app.memory")
    restore.append((memory_module, "EXTRACTION_ENABLED", memory_module.EXTRACTION_ENABLED))
    memory_module.EXTRACTION_ENABLED = False

    def bind(module_name: str, attribute: str, value: Path) -> None:
        module = importlib.import_module(module_name)
        restore.append((module, attribute, getattr(module, attribute)))
        setattr(module, attribute, value)

    configs = root / "model_configs"
    configs.mkdir(parents=True, exist_ok=True)
    # `copyfile` per entry rather than `copytree`, and the listing is taken once
    # per process rather than per test: this runs on every sandbox in the suite,
    # and copytree's per-file `copystat` plus directory walk cost about three
    # times what moving the bytes does. Nothing here needs the metadata.
    for name, data in _shipped_model_configs().items():
        (configs / name).write_bytes(data)
    bind("app.feasibility", "MODEL_CONFIG_ROOT", configs)

    hub_cache = root / "hub-cache"
    hub_cache.mkdir(parents=True, exist_ok=True)
    bind("app.tools.models", "HUB_CACHE_ROOT", hub_cache)

    bind("app.security", "ENGINE_FILE", root / "engine.json")

    # THE CARD IS NOT PART OF ANY TEST. `sandbox.run` asks the machine what is
    # resident on the GPU before a training run and refuses a crowded card; a
    # suite that read the developer's real `nvidia-smi` would pass or fail on
    # whether a chat model happened to be loaded at the time - which is exactly
    # what happened the first time it ran. Bound to "no card" here; a test that
    # is ABOUT the guard patches `_gpu_occupancy` itself, and its patch wins.
    sandbox_module = importlib.import_module("app.tools.sandbox")
    restore.append((sandbox_module, "_gpu_occupancy", sandbox_module._gpu_occupancy))
    sandbox_module._gpu_occupancy = lambda: None

    # NOR ARE THE MACHINE'S MODEL SERVERS. The facade probes a connection it
    # makes (a real request to a vendor with a test's fake key, or to the
    # developer's Ollama) and lists the models the local Ollama daemon has
    # (`app/facade/catalog.py`). Both are off in a sandbox, so a test's catalog
    # holds exactly the connections it made; a test ABOUT either turns it on
    # and fakes the server itself.
    catalog_module = importlib.import_module("app.facade.catalog")
    for flag in ("PROBE_AFTER_CONNECT", "DISCOVER_LOCAL"):
        restore.append((catalog_module, flag, getattr(catalog_module, flag)))
        setattr(catalog_module, flag, False)

    def cleanup():
        for module, attribute, previous in reversed(restore):
            setattr(module, attribute, previous)
        fixtures.__exit__(None, None, None)
        _quiesce_process_state()
        try:
            temp.cleanup()
        except (PermissionError, OSError):
            # Windows holds a handle open on a log a killed job was writing.
            # The directory is the OS's problem at that point, not the test's.
            pass

    test.addCleanup(cleanup)
    # A project shell call builds `<root>/.venv` with numpy, pandas and
    # scikit-learn (H-shell). Twelve seconds per temp project is a cost no test
    # asked for; the one that does sets it back on.
    if "MLH_PROJECT_VENV" not in os.environ:
        os.environ["MLH_PROJECT_VENV"] = "0"
        test.addCleanup(os.environ.pop, "MLH_PROJECT_VENV", None)
    return root


def pin_a_training_recipe(name: str = "hf-peft-lora") -> Path:
    """A recipe with a BUILT pinned environment, inside this test's recipes root.

    Call it after `sandbox()`. `FIXTURE_RECIPES` gives every test a tree with no
    pinned environment in it, which is right for the runner's tests and wrong
    for anything that asks "is the backend ready on this machine" - and
    `app/tools/propose.py`'s training build asks exactly that, because a recipe
    whose virtualenv has not been materialised is one its own entrypoint refuses
    to train in.

    `app/tools/sandbox.py::pin` decides `pinned` from two things it can see: a
    `requirements.lock` beside the recipe and an interpreter file inside its
    `.venv`. So that is what this writes, on both platforms' interpreter paths,
    plus the `pyvenv.cfg` the version is read out of. **The interpreter is an
    empty file and nothing here ever executes it** - what is being staged is the
    STATE of a machine, not a working environment, and a test that ran this
    would be a test that needed a real 4 GB venv.

    ## AND IT REFUSES TO WRITE INTO THE CHECKOUT, BECAUSE IT DID

    Measured on 2026-08-21, on the owner's machine, during an ordinary
    `python -m unittest discover -s tests -t tests`: this function ran with
    `jobspec.RECIPES_ROOT` still pointing at the repository's own `recipes/`
    and overwrote the SHIPPED `hf-peft-lora` recipe with the fixture -
    `recipe.toml`, `entrypoint.py` and `requirements.lock` - and then wrote a
    ZERO-BYTE FILE OVER `.venv/Scripts/python.exe`, which is the interpreter of
    the real, materialised, 4.8 GB pinned environment. The environment's
    `Lib/site-packages` survived; nothing could run it. Three tests failed
    afterwards for three different-looking reasons, none of which said "your
    virtualenv is gone".

    The docstring above already said "call it after `sandbox()`", and a
    docstring is not a mechanism. This is the mechanism: a helper whose whole
    job is to WRITE files refuses to write them into the user's checkout, and
    says which test asked. Whatever route left `RECIPES_ROOT` unbound - a test
    that forgot `sandbox()`, a cleanup that ran early, a second copy of the
    suite running in the same tree - stops being a silent 4.8 GB loss and
    becomes a failing test naming itself.
    """
    recipes = Path(jobspec.RECIPES_ROOT)
    if recipes.resolve() == (REPO_ROOT / "recipes").resolve():
        raise AssertionError(
            "pin_a_training_recipe was about to write fixture files into "
            f"{recipes}, which is the repository's own recipes directory. That "
            "overwrites the shipped recipe and puts a zero-byte file where the "
            "pinned environment's interpreter is. Nothing was written. This "
            "test must call support.sandbox(self) before staging a recipe - "
            "jobspec.RECIPES_ROOT is still the real one."
        )
    directory = recipes / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "recipe.toml").write_text(
        f'name = "{name}"\nkinds = ["train"]\nentrypoint = "entrypoint.py"\n',
        encoding="utf-8",
    )
    (directory / "entrypoint.py").write_text(
        "raise SystemExit('this fixture is never executed')\n", encoding="utf-8"
    )
    (directory / "requirements.lock").write_text(
        "# a fixture lockfile\ntorch==2.5.1\ntransformers==5.5.0\npeft==0.14.0\n",
        encoding="utf-8",
    )
    venv = directory / ".venv"
    (venv / "Scripts").mkdir(parents=True, exist_ok=True)
    (venv / "bin").mkdir(parents=True, exist_ok=True)
    (venv / "Scripts" / "python.exe").write_text("", encoding="utf-8")
    (venv / "bin" / "python").write_text("", encoding="utf-8")
    (venv / "pyvenv.cfg").write_text("version = 3.11.9\n", encoding="utf-8")
    return directory


def spec(recipe: str, kind: str = "train", **config) -> jobspec.JobSpec:
    """Shorthand for building a `JobSpec` in a test."""
    return jobspec.JobSpec(recipe=recipe, kind=kind, config=dict(config))


# ---------------------------------------------------------------------------
# The shapes a real machine has and a fresh sandbox does not.


def conversations(count: int = 2, *, projects: bool = True) -> list[dict]:
    """`count` conversations, each in its own project. Returns thread rows.

    THE ONE-LINE ANSWER TO A WHOLE FAMILY OF DEFECTS. A record that is scoped
    to a conversation and a record that is global look exactly alike when there
    is only ever one conversation to look at, and until now every test in this
    suite had one. The eval-set leak was that; it is not the only unscoped table
    in the product, and the next one will be found by a test that could afford
    to open a second conversation.

    `projects=True` puts each thread in a project of its own, because two
    threads in one project cannot tell thread scope from project scope either.
    Each row carries `project` alongside the thread's own columns, so a caller
    has both ids without a second query.

    Call it after `sandbox()`. It uses the bound database like anything else.
    """
    from app import events

    out: list[dict] = []
    for index in range(int(count)):
        if projects:
            project = db.create_project(f"project-{index + 1}")
        else:
            project = db.default_project()
        thread = events.create_thread(
            f"conversation-{index + 1}", project_id=project["id"]
        )
        row = dict(thread)
        row["project"] = project
        out.append(row)
    return out


def a_conversation(*thread_ids: int, title: str = "a conversation") -> list[dict]:
    """Make sure a conversation exists with EACH of these exact ids.

    THE HARNESS CONVENIENCE THAT WAS MISSING, and its absence is the shape this
    file's docstring is about. Every test that wanted a thread-scoped row picked
    an integer - 1, 7, 11, 4242 - and wrote against it, because the ledger took
    any integer at all. So the suite was full of rows filed against conversations
    that did not exist, which is the exact defect `evidence.record` now refuses:
    ids are handed out in order from 1, so a row against a thread that is not
    there yet is a row the next conversation inherits.

    `conversations()` is the right call when a test just needs N of them and does
    not care what they are numbered. This one is for a test that has already
    committed to a number - a module constant, an id in an assertion, a
    fixture built to match a real database - and needs THAT number to name
    something. The id is written explicitly, which is a thing only a fixture may
    do: `events.create_thread` takes the next one, as the product must.

    Idempotent, and returns the rows. Ids already taken are left exactly as they
    are rather than overwritten, so calling this twice in a setUp is safe and a
    thread another helper already made keeps its title and its project.
    """
    from app import events

    events.ensure_tables()
    project = db.default_project()["id"]
    out: list[dict] = []
    for thread_id in thread_ids:
        with db.session() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO threads (id, title, project_id) "
                "VALUES (?, ?, ?)",
                (int(thread_id), f"{title} {thread_id}", project),
            )
        out.append(events.get_thread(int(thread_id)))
    return out


def with_history(
    *, runs: int = 0, jobs: int = 0, threads: int = 0, projects: int = 0
) -> dict[str, list[dict]]:
    """Put prior work in the database, so this test is not the first thing to run.

    Every test's first run is run 1, its first job is job 1 and its first thread
    is thread 1. That is the shape of a machine that has never been used, and it
    is the shape under which "keyed on an identity" and "keyed on a counter that
    restarts at 1 in every database" are indistinguishable - the confusion that
    produced two unrelated jobs sharing one log file.

    Returns what it made, so a test can assert about the hundredth run rather
    than about the only one.
    """
    from app import events

    made: dict[str, list[dict]] = {
        "projects": [],
        "threads": [],
        "runs": [],
        "jobs": [],
    }
    for index in range(int(projects)):
        made["projects"].append(db.create_project(f"prior-project-{index + 1}"))
    for index in range(int(threads)):
        made["threads"].append(events.create_thread(f"prior-thread-{index + 1}"))
    for index in range(int(runs)):
        made["runs"].append(db.create_run(f"prior-run-{index + 1}", "{}"))
    for index in range(int(jobs)):
        made["jobs"].append(
            db.create_job(
                f"prior-intake-{index + 1}", spec("printer", message="prior")
            )
        )
    return made


def concurrently(*callables, timeout: float = 30.0) -> list[dict]:
    """Run every callable at once; return `[{"value": ...} | {"error": ...}]`.

    Nothing in this suite calls two things at the same time except
    `test_migrations_survive_concurrency`, so every read-then-write race in the
    product was untested by construction - including the one `app/db.py`'s own
    comment named, where `next_queued_job` selected a row without claiming it.
    That one was closed on 2026-09-02 by making the claim atomic, and the
    probe this helper exists for is now its regression guard rather than a
    declared failure.

    Exceptions are CAPTURED, one per callable, and returned in the same order.
    Raising from a worker thread would surface as a stack on stderr and a
    passing test, which is the worst of both.

    Barrier-synchronised: every thread is started, then all of them are released
    together, so the calls actually overlap rather than merely being started in
    a loop.
    """
    functions = list(callables)
    results: list[dict] = [{} for _ in functions]
    barrier = threading.Barrier(len(functions) or 1)

    def run(index: int, function) -> None:
        try:
            barrier.wait(timeout=timeout)
        except threading.BrokenBarrierError:  # pragma: no cover - a stuck peer
            pass
        try:
            results[index] = {"value": function()}
        except BaseException as error:  # noqa: BLE001 - reported, not swallowed
            results[index] = {"error": error}

    workers = [
        threading.Thread(target=run, args=(index, function), daemon=True)
        for index, function in enumerate(functions)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=timeout)
    return results


# ---------------------------------------------------------------------------
# The fence. Installed HERE, at import of `support`, and not in the test file
# that asserts it works.
#
# It used to live in tests/test_tests_do_not_touch_the_real_database.py and
# install itself at that module's import. Under `unittest discover` that is
# before any test runs, so the full suite was covered - but a FILTERED run
# (`discover -p "test_a_provenance_claim*.py"`) never imports that file, so
# the fence was never installed. An agent ran exactly that pattern, a lazy
# ledger read fell through to `db.DB_PATH`, and pending migration 9 was
# applied to Max's real ml_harness.db. Nothing was lost - the migration is
# additive DDL - but the engine on 8078 then refused every request, because
# its build knew schema 8 and the file was at 9.
#
# The guard protected the suite and not the thing the suite runs against,
# which is this project's most-repeated defect shape. Every test imports
# `support`; almost none import that test file. So it lives here.
# ---------------------------------------------------------------------------

class RealDatabaseTouched(RuntimeError):
    """Raised in place of opening a database that holds the user's real data."""


#: Every attempt, as `(path, stack)`. Appended to before the refusal is raised,
#: so an attempt swallowed by a `try/except` in the offending test is still
#: reported by `test_no_test_opened_the_real_database`.
ATTEMPTS: list[tuple[str, str]] = []


def _normalise(target: object) -> str | None:
    """An absolute, case-folded path for `target`, or `None` if it is not one.

    `None` covers `:memory:`, `file:` URIs and the non-path arguments a caller
    could pass. Returning `None` means "not something this guard can judge",
    which is deliberately different from "judged and allowed" - see the limits
    in the module docstring.
    """
    if not isinstance(target, (str, os.PathLike)):
        return None
    text = os.fspath(target)
    if not text or text.startswith(":") or text.startswith("file:"):
        return None
    return os.path.normcase(os.path.abspath(text))


PROTECTED = {
    normalised
    for normalised in (_normalise(path) for path in PROTECTED_DATABASES)
    if normalised is not None
}


def _install() -> None:
    """Wrap `sqlite3.connect` so a protected path cannot be opened.

    Idempotent by flag, because this module can legitimately be imported twice
    (discovery plus a direct `python -m unittest tests.test_...` run) and
    wrapping a wrapper would work but would make the stack twice as deep for no
    gain.

    Both `sqlite3.connect` and `sqlite3.dbapi2.connect` are replaced. They are
    the same function object reached by two names, and `app/db.py` calls the
    first, but a module that did `from sqlite3.dbapi2 import connect` would
    reach past a patch of only one of them.
    """
    original = sqlite3.connect
    if getattr(original, "_mlh_guard", False):
        return

    def guarded(database, *args, **kwargs):
        resolved = _normalise(database)
        if resolved in PROTECTED:
            # The last frame is this wrapper; the caller is what we want named.
            ATTEMPTS.append((resolved, "".join(traceback.format_stack()[:-1])))
            raise RealDatabaseTouched(
                f"a test tried to open {resolved}, which holds the user's real "
                "data. Give the test its own database - support.sandbox() for "
                "an in-process one, ML_HARNESS_DB for a subprocess."
            )
        return original(database, *args, **kwargs)

    guarded._mlh_guard = True
    guarded._mlh_original = original
    sqlite3.connect = guarded
    sqlite3.dbapi2.connect = guarded


_install()


#: The label set a scripted model answers from. Four, because the ML ledger's
#: classical branch and its failure bucketer both want more than a coin flip.
SCRIPTED_LABELS = ("billing", "technical", "account", "other")


class ScriptedModel:
    """A model that answers deterministically, and grades when asked to.

    PROMOTED FROM `tests/test_the_eval_bench_keeps_its_rows.py` on 2026-08-28,
    where it had lived since the eval bench shipped. It is promoted rather than
    copied because a fourth private scripted model is how two tests start
    disagreeing about what "the model got 20 right" means.

    Right on the first `correct` questions, then a cycle of failure shapes so a
    run of any length carries all of them: a refusal, the right answer wrapped in
    a sentence, a different member of the label set, and something no rule can
    name. That last one is deliberate - a bucketer with nothing it will not
    classify is a bucketer that guesses.

    IT ALSO GRADES when handed `evals.JUDGE_SYSTEM`, and that is not a
    convenience: with no `judge_provider_id` the bench builds the judge from the
    same connection, so one object answering both prompts is exactly the shape
    the honesty machinery is about.
    """

    def __init__(self, correct: int = 0, verdict: str = "CORRECT") -> None:
        self.correct = correct
        self.verdict = verdict
        self.asked: list[str] = []
        self.judged: list[str] = []

    @staticmethod
    def _index(question: str) -> int:
        import re

        return int(re.sub(r"\D", "", str(question)) or 0)

    def stream(self, conversation, offered=None, *, secret=None):
        from app.providers import Delta
        from app.tools import evals

        if conversation[0]["content"] == evals.JUDGE_SYSTEM:
            self.judged.append(conversation[-1]["content"])
            yield Delta(kind="text", text=self.verdict)
            return
        question = conversation[-1]["content"]
        self.asked.append(question)
        index = self._index(question)
        if index < self.correct:
            yield Delta(kind="text", text=SCRIPTED_LABELS[index % len(SCRIPTED_LABELS)])
        elif index % 4 == 0:
            yield Delta(kind="text", text="I'm sorry, I cannot answer that.")
        elif index % 4 == 1:
            yield Delta(
                kind="text",
                text=f"The answer is {SCRIPTED_LABELS[index % len(SCRIPTED_LABELS)]}.",
            )
        elif index % 4 == 2:
            yield Delta(
                kind="text",
                text=SCRIPTED_LABELS[(index + 1) % len(SCRIPTED_LABELS)],
            )
        else:
            yield Delta(kind="text", text="banana split with sprinkles")

    def capabilities(self):
        from app.providers import Caps

        return Caps(tool_calling=False, detail="scripted", ctx_len=8192)


def connect_a_model(test, model=None, *, name: str = "Scripted"):
    """Give the thread a connected model, and take it away again afterwards.

    THREE MODULES ARE PATCHED AND THAT IS THE WHOLE POINT OF THIS HELPER.
    `build` is imported BY NAME in `app/tools/evals.py`, `app/tools/measure.py`
    and `app/conductor.py`, so each holds its own reference and patching
    `app.providers.build` reaches none of them. A test that patched one and
    drove a path through another got the real builder and a connection error,
    and the fix looked like a flake.

    The provider row is `127.0.0.1`, which `providers.classify` reads as
    `kind="local"` - the egress guard refuses a remote call the model chose, so
    a scripted test against a "remote" row fails for a reason that has nothing
    to do with what it is testing.
    """
    from app.providers import store as provider_store

    model = model if model is not None else ScriptedModel()
    row = provider_store.create(name, "http://127.0.0.1:11434", "scripted", "ollama")
    provider_store.set_active(row["id"])

    from app import conductor
    from app.tools import evals, measure

    for module in (evals, measure, conductor):
        original = module.build
        module.build = lambda adapter, base_url, name, _m=model: _m
        test.addCleanup(
            lambda m=module, o=original: setattr(m, "build", o)
        )
    return model


def a_conversation_on(ledger: str, *, title: str = "a journey", project_id=None):
    """A thread that names its ledger.

    `conversations()` above always gets the default, which is what almost every
    test wants and is why this is separate rather than a keyword on it. The
    parameter exists on `events.create_thread` so the engine can record what it
    INFERRED - see that function's docstring - and a test is the other caller it
    names. It is not a chooser and must not become one: `docs/VISION.md` is
    explicit that a person never picks a domain.
    """
    from app import events

    return events.create_thread(title, project_id, ledger)


def a_completed_eval_run(thread_id: int, eval_path, *, rows: int = 100) -> dict:
    """A real, complete row in the eval bench's own tables.

    PROMOTED FROM `tests/test_the_training_build_scores_what_it_trains.py` on
    2026-08-28, where it was `a_completed_run`, because a second proposer now
    refuses without one - `propose.the_baseline_run_to_beat` is what both read -
    and two private copies of "what a pairable baseline looks like" is how two
    tests start disagreeing about it.

    Through `evals.create_run` / `evals.record_row` rather than by calling
    `run_eval`, because `run_eval` needs somebody's model running and the tests
    that want this are about the plan drawn AFTERWARDS. Every column that
    decides anything - the thread, the eval path, whether it is complete - is
    the real one.

    Half the rows are right, so a comparison against it has somewhere to move in
    either direction.
    """
    from app.tools import evals

    run = evals.create_run(
        thread_id=int(thread_id),
        signature="a-baseline",
        eval_path=str(eval_path),
        eval_fingerprint="fingerprint",
        input_field="q",
        expected_field="a",
        metric=evals.EXACT_MATCH,
        prompt="",
        prompt_is_default=1,
        provider_id=None,
        provider_name="ollama",
        model="granite4-hermes:latest",
        locality="local",
        judge_model=None,
        planned=int(rows),
        rows_available=int(rows),
        trivial_baseline=0.5,
        trivial_answer="yes",
        latency_budget_ms=None,
    )
    for index in range(int(rows)):
        right = bool(index % 2)
        evals.record_row(
            int(run["id"]),
            index,
            question=f"question {index}",
            expected="yes",
            answer="yes" if right else "no",
            correct=right,
            verdicts={"exact_match": right},
            failure_mode=None if right else "wrong_facts",
            graded_by=evals.EXACT_MATCH,
            seconds=0.1,
        )
    return dict(run)

def a_tool_that_requires_an_argument():
    """A REAL registered tool with a required argument, DERIVED not named.

    Three tests used `run_diagnosis` as the specimen for "a tool that
    refuses a call missing a required argument". On 2026-09-11 its `facts`
    argument became optional - it was the one argument that cannot open a
    gate, and requiring it made a model invent fact names to get past the
    schema - and all three went red on a property that had not changed at
    all. The property is about the registry; the specimen was a borrowed
    detail of one tool, and a borrowed specimen disappears.

    So the specimen is derived: the first tool, in name order, that
    requires an argument, needs no approval and writes nothing. Sorted so
    two runs pick the same one; `approval='never'` so the call reaches the
    argument check instead of raising `ApprovalRequired` first; writes
    nothing so a refusal cannot touch anything even if the check were the
    thing that broke.

    Fifty-one tools declare a required argument, so this is not a narrow
    escape hatch that will empty out. It raises rather than skipping if it
    ever does: a specimen that vanishes must fail loudly, because a test
    that quietly stops testing is the fault it was written against.
    """
    from app.tools.registry import REGISTRY

    for tool in sorted(REGISTRY, key=lambda each: each.name):
        if not (tool.schema.get('required') or ()):
            continue
        if getattr(tool, 'approval', None) != 'never':
            continue
        if getattr(tool, 'writes', ()):
            continue
        return tool
    raise AssertionError(
        'no registered tool requires an argument, needs no approval and '
        'writes nothing - the specimen these tests derive is gone, and the '
        'property they hold needs a new one rather than a skip'
    )
