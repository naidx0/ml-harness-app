"""A test wrote a file into the user's checkout, and 1057 tests could not see it.

## What went wrong

`support.sandbox()` bound three module-level globals: `db.DB_PATH`,
`jobspec.RECIPES_ROOT`, `jobspec.RUNS_ROOT`. The product has six it writes
through. The three it did not bind:

* **`feasibility.MODEL_CONFIG_ROOT`** - `app/model_configs/`, **tracked in git**.
  `store_model_config()` writes a file per repo id, and the caller is
  `read_model_config`, a registered tool with `approval="never"` that a model
  may call. A sandboxed test that calls it lands a new `.json` in the user's
  working tree, and calling it for a repo id the harness already ships
  OVERWRITES a tracked file.
* **`tools.models.HUB_CACHE_ROOT`** - `.hub-cache/`, written by `_cache_write()`
  on any hub fetch.
* **`security.ENGINE_FILE`** - `engine.json`, written by `write_portfile()` when
  no `path=` is passed, and it carries the live engine's bearer token.

Each of the three IS isolated - in exactly one test class each, by the one
author who thought about it: `MODEL_CONFIG_ROOT` in
`test_model_geometry_is_read_not_assumed`, `HUB_CACHE_ROOT` in
`test_model_fit_ranker`, `ENGINE_FILE` by every caller of `write_portfile`
remembering to pass `path=`. That is the b024da4 job-log defect exactly: shared
state isolated in eleven places and forgotten in the twelfth, three times over
in one repository.

## Why the existing fence does not reach it

`tests/test_tests_do_not_touch_the_real_database.py` wraps `sqlite3.connect` and
fingerprints the database files. Both mechanisms are about SQLite. A tool that
opens a `.json` for writing is not a database call and does not change
`ml_harness.db`, so both mechanisms are quiet while a test rewrites source.

## What this file does, in three layers that fail in different directions

**1. The roster is derived, not listed.** `support.repo_path_globals()` imports
every module under `app` and reports every module-level path that resolves
inside the repository. A global added next year appears the day it is written,
and `test_every_repo_path_global_is_accounted_for` fails until somebody says -
in `support.py`, where a reviewer reads it - whether the product writes through
it. This is the layer that catches the FOURTH one.

**2. The bindings are checked from inside a sandbox.** Not "the list says it is
bound" but "open a sandbox and look at where the global points". A roster entry
whose binding was deleted is a lie the roster cannot tell.

**3. The writes are recorded, and separately the bytes are watched.** These are
two mechanisms that fail in different directions, the same arrangement
`test_tests_do_not_touch_the_real_database.py` uses for SQLite.

`Path.write_text` and `Path.write_bytes` are wrapped for the whole test process
at import - and `unittest discover` imports every module before running any
test, so the wrapper is live for the entire run regardless of where this file
sorts. Every in-process write to a watched repository path is recorded WITH THE
STACK THAT MADE IT, so the offending test names itself. That is how
`test_theme.py` was found: it was the only test in the suite that entered the
app's lifespan, `app.main.lifespan` calls `security.write_portfile()` with no
path, and every suite run therefore rewrote the repository's real `engine.json`
- the file the launcher and the CLI client read the engine's port and BEARER
TOKEN from. The database guard could not see it because it is a JSON file.

`tree_fingerprint` over the directories, taken at import and compared at the
end, is the half that catches a subprocess, a background thread that resolved a
global before it moved, and a global nobody has bound at all - because it asks
about the file rather than about who opened it.

**`engine.json` is watched by the recorder and NOT by the bytes**, and that is a
considered exception rather than an oversight. The engine republishes it every
time the owner starts it, and a second copy of this suite running at the same
time rewrites it too - both of which are facts about the machine rather than
about this run. Comparing its bytes measures who else was busy; recording who
opened it measures what this suite did. For the directories there is no such
outside writer, so bytes are the stronger check there.

## Two limits, stated rather than discovered later

- Both the recorder's report and the byte comparison are assertions made at the
  point this file runs. A test that sorts AFTER it and writes is missed by
  both - the same limit `test_tests_do_not_touch_the_real_database.py` states
  about its own snapshot, and for the same reason: there is no "after
  everything" hook in `unittest`.
- The recorder wraps `Path.write_text` and `Path.write_bytes`. It does not see
  `open(path, "w")`, and it cannot see a subprocess at all. The byte comparison
  is what covers the second of those; nothing covers the first, and a writer in
  `app/` that starts using `open()` for one of these files needs this wrapper to
  learn about it.

## The controls, because a guard that cannot fire certifies nothing

* `test_the_derived_check_reports_an_unaccounted_global` builds a module holding
  an unlisted repository path and asserts the derived check names it. Without
  this, layer 1 passing means only that nothing was found.
* `test_the_tree_watcher_sees_a_write` writes a file under a watched path,
  fingerprints, and asserts the comparison notices - then removes it.
* `test_the_model_config_tool_writes_into_the_sandbox` is the original defect,
  run forwards: the tool is called, and the file it produced must be in the
  sandbox and must not be in the repository. Deleting the binding in
  `support.py` turns this red, which is the property that matters.
"""

from __future__ import annotations

import importlib
import json
import pathlib
import sys
import traceback
import types
import unittest
from pathlib import Path

import support


REPO_ROOT = support.REPO_ROOT


#: Repository paths the product opens for writing. Every one of them is watched
#: by the recorder below; the directories are watched by their bytes as well.
WRITABLE_REPO_PATHS: tuple[Path, ...] = (
    REPO_ROOT / "app" / "model_configs",
    REPO_ROOT / ".hub-cache",
    REPO_ROOT / "engine.json",
    REPO_ROOT / "recipes",
)

#: The subset compared by bytes. `engine.json` is deliberately absent - see the
#: module docstring. The owner's engine republishes it and a second copy of this
#: suite rewrites it, so its bytes answer a question about the machine rather
#: than about this run. The recorder still watches it, exactly.
BYTE_WATCHED_PATHS: tuple[Path, ...] = tuple(
    path for path in WRITABLE_REPO_PATHS if path.name != "engine.json"
)

#: Taken at import, which under `unittest discover` is before any test runs.
BASELINE: dict[str, dict[str, tuple[int, str]]] = {
    str(path): support.tree_fingerprint(path) for path in BYTE_WATCHED_PATHS
}


#: Every in-process write to a watched path, as `(path, stack)`. Recorded rather
#: than refused: a refusal turns one reported defect into an exception in
#: somebody else's assertion, and the point is to name the caller.
WRITES: list[tuple[str, str]] = []


def _watched(target: object) -> str | None:
    """The watched path `target` is inside, or `None`."""
    try:
        resolved = Path(target).resolve()
    except (TypeError, ValueError, OSError):
        return None
    for path in WRITABLE_REPO_PATHS:
        if resolved == path or path in resolved.parents:
            return str(resolved)
    return None


def _install_write_recorder() -> None:
    """Record any in-process write under a watched repository path.

    `Path.write_text` and `Path.write_bytes` are the two calls every writer in
    `app/` uses for these files - `security.write_portfile`,
    `feasibility.store_model_config` and `models._cache_write` between them. Job
    logs go through `open()` and are not wrapped, because they are written under
    `RUNS_ROOT`, which `sandbox()` has bound since b024da4.

    Idempotent by flag: this module can legitimately be imported twice, and
    wrapping a wrapper would double the stack for nothing.
    """
    if getattr(pathlib.Path.write_text, "_mlh_tree_guard", False):
        return

    original_text = pathlib.Path.write_text
    original_bytes = pathlib.Path.write_bytes

    def record(self):
        target = _watched(self)
        if target is not None:
            WRITES.append((target, "".join(traceback.format_stack()[:-2])))

    def write_text(self, *args, **kwargs):
        record(self)
        return original_text(self, *args, **kwargs)

    def write_bytes(self, *args, **kwargs):
        record(self)
        return original_bytes(self, *args, **kwargs)

    write_text._mlh_tree_guard = True
    write_bytes._mlh_tree_guard = True
    pathlib.Path.write_text = write_text
    pathlib.Path.write_bytes = write_bytes


_install_write_recorder()


def unaccounted_globals() -> dict[tuple[str, str], Path]:
    """Repository path globals that neither roster in `support.py` names.

    One direction only, and deliberately: after any sandboxed test has run,
    `db.DB_PATH` points at a temporary file and is no longer inside the
    repository, so "every declared global is discovered" is not a property this
    suite can hold. "Every discovered global is declared" is, and it is the
    direction that catches a new one.
    """
    declared = {(module, name) for module, name, _ in support.SANDBOXED_PATH_GLOBALS}
    declared |= {(module, name) for module, name, _ in support.READ_ONLY_PATH_GLOBALS}
    return {
        key: value
        for key, value in support.repo_path_globals().items()
        if key not in declared
    }


class TheRosterIsDerivedTest(unittest.TestCase):
    """Layer 1. The list of globals comes from the modules, not from memory."""

    def test_every_repo_path_global_is_accounted_for(self):
        unaccounted = unaccounted_globals()
        self.assertEqual(
            unaccounted,
            {},
            "a module-level path inside the repository is named by neither "
            "roster in tests/support.py. Decide which it is and say so there: "
            "SANDBOXED_PATH_GLOBALS if product code ever opens it for writing, "
            "READ_ONLY_PATH_GLOBALS if it does not. Leaving it out means every "
            "test in this suite that reaches the code behind it is writing "
            f"into the user's checkout.\n\nUnaccounted: {sorted(unaccounted)}",
        )

    def test_the_derived_check_reports_an_unaccounted_global(self):
        """THE POSITIVE CONTROL. An empty result must mean 'looked and found none'.

        A module is installed under `app.` holding a repository path, which is
        what a new global looks like, and the check above must name it.
        """
        name = "app._support_probe_module"
        module = types.ModuleType(name)
        module.PROBE_ROOT = REPO_ROOT / "some" / "new" / "place"
        sys.modules[name] = module
        parent = importlib.import_module("app")
        setattr(parent, "_support_probe_module", module)
        self.addCleanup(delattr, parent, "_support_probe_module")
        self.addCleanup(sys.modules.pop, name, None)

        unaccounted = unaccounted_globals()

        self.assertIn(
            (name, "PROBE_ROOT"),
            unaccounted,
            "the derived check did not see a repository path on a module under "
            "`app`, so its silence in the test above means nothing",
        )


class TheSandboxBindsWhatItSaysItBindsTest(unittest.TestCase):
    """Layer 2. Checked by looking, not by reading the roster."""

    def setUp(self):
        self.root = support.sandbox(self)

    def test_every_writable_global_points_inside_the_sandbox(self):
        for module_name, attribute, why in support.SANDBOXED_PATH_GLOBALS:
            with self.subTest(binding=f"{module_name}.{attribute}"):
                module = importlib.import_module(module_name)
                value = Path(getattr(module, attribute)).resolve()
                self.assertTrue(
                    self.root.resolve() == value or self.root.resolve() in value.parents,
                    f"{module_name}.{attribute} is {value}, which is not under "
                    f"this test's sandbox at {self.root}. It is bound because: "
                    f"{why}",
                )
                self.assertFalse(
                    value == REPO_ROOT or REPO_ROOT in value.parents,
                    f"{module_name}.{attribute} still points into the "
                    f"repository at {value}",
                )

    def test_the_shipped_model_configs_are_readable_from_inside_the_sandbox(self):
        """Isolating the writer must not blind the reader.

        `MODEL_CONFIG_ROOT` is seeded rather than emptied. The configs the
        repository ships are source - reviewed, tracked, and read by tests that
        assert on real model geometry - so a sandbox that hid them would change
        what reading code sees in order to protect what writing code does.
        """
        from app import feasibility

        geometry = feasibility.geometry_for("Qwen/Qwen3-4B")

        self.assertIsNotNone(
            geometry,
            "the sandbox's model config root does not carry the shipped "
            "configs, so every sandboxed test now reasons about a machine with "
            "no known model geometry",
        )
        self.assertEqual(geometry.provenance, "measured")

    def test_the_hub_cache_starts_empty(self):
        """The other half of the same decision, in the other direction.

        `.hub-cache/` is gitignored per-machine network state. A test that
        passes because the developer's machine happened to hold a cached hub
        response is a test that fails on a fresh checkout, so the sandbox copy
        is empty on purpose.
        """
        from app.tools import models

        self.assertEqual(
            sorted(Path(models.HUB_CACHE_ROOT).glob("*")),
            [],
            "the sandbox inherited a hub cache",
        )


class TheModelConfigToolIsSandboxedTest(unittest.TestCase):
    """Layer 2, at the defect itself: the registered tool that writes source.

    `read_model_config` fetches a `config.json` and keeps it. The keeping is the
    part that escaped. The hub call is stubbed here because this test is about
    where the file lands, not about the network.
    """

    def setUp(self):
        self.root = support.sandbox(self)

        from app.tools import models

        self.models = models
        previous = models.fetch_json
        self.addCleanup(setattr, models, "fetch_json", previous)
        models.fetch_json = self._stub_fetch

    @staticmethod
    def _stub_fetch(url, *args, **kwargs):
        if str(url).endswith("config.json"):
            return {
                "ok": True,
                "source": "stub",
                "payload": {
                    "num_hidden_layers": 4,
                    "hidden_size": 64,
                    "num_attention_heads": 4,
                    "num_key_value_heads": 2,
                    "vocab_size": 100,
                },
            }
        return {
            "ok": True,
            "source": "stub",
            "payload": {"sha": "deadbeef", "safetensors": {"total": 1000}},
        }

    def test_the_model_config_tool_writes_into_the_sandbox(self):
        from app import feasibility
        from app.tools import REGISTRY

        repo_id = "sandboxed/should-not-escape"
        in_repo = REPO_ROOT / "app" / "model_configs" / (
            feasibility.config_slug(repo_id) + ".json"
        )

        result = REGISTRY.call(
            "read_model_config", {"repo_id": repo_id}, actor="model", thread_id=1
        )

        self.assertTrue(result.get("ok"), result)
        written = feasibility.config_path(repo_id)
        self.assertTrue(written.is_file(), "the tool reported ok and stored nothing")
        self.assertIn(
            self.root.resolve(),
            written.resolve().parents,
            f"the tool stored a config at {written}, outside this test's sandbox",
        )
        self.assertFalse(
            in_repo.exists(),
            f"a sandboxed test created {in_repo} in the user's checkout. That "
            "directory is tracked in git, so this is a test editing source.",
        )
        self.assertEqual(
            json.loads(written.read_text(encoding="utf-8"))["repo_id"], repo_id
        )

    def test_it_cannot_overwrite_a_config_the_repository_ships(self):
        """The worse half: not a new file, an edit to a tracked one.

        `Qwen/Qwen3-4B` is one of the configs this repository keeps. Fetching it
        again with different contents must change the sandbox's copy and leave
        the checkout's copy byte-for-byte as it was.
        """
        from app import feasibility
        from app.tools import REGISTRY

        shipped = REPO_ROOT / "app" / "model_configs" / "Qwen--Qwen3-4B.json"
        if not shipped.is_file():  # pragma: no cover - a checkout without it
            self.skipTest("this checkout does not ship the Qwen3-4B config")
        before = shipped.read_bytes()

        REGISTRY.call(
            "read_model_config", {"repo_id": "Qwen/Qwen3-4B"}, actor="model", thread_id=1
        )

        self.assertEqual(
            shipped.read_bytes(),
            before,
            f"{shipped} was rewritten by a test. It is tracked in git.",
        )
        sandboxed = feasibility.config_path("Qwen/Qwen3-4B")
        self.assertEqual(
            json.loads(sandboxed.read_text(encoding="utf-8"))["config"][
                "num_hidden_layers"
            ],
            4,
            "the sandbox's own copy was not the one the tool wrote",
        )


class NothingWroteIntoTheWorkingTreeTest(unittest.TestCase):
    """Layer 3. The recorder names the caller; the bytes see the subprocess."""

    def test_the_guard_is_installed(self):
        """If this fails, the two tests below are green for the wrong reason."""
        self.assertTrue(
            getattr(pathlib.Path.write_text, "_mlh_tree_guard", False),
            "Path.write_text is not wrapped: something replaced it after "
            "import, so nothing has been watching this run",
        )
        self.assertTrue(WRITABLE_REPO_PATHS, "the guard has nothing to watch")

    def test_no_test_wrote_into_the_working_tree(self):
        if not WRITES:
            return
        report = "\n\n".join(f"{path} written from:\n{stack}" for path, stack in WRITES)
        self.fail(
            f"{len(WRITES)} write(s) into the user's checkout from inside this "
            "test process. A test that needs the code behind one of these to "
            "run should open a sandbox: support.sandbox() binds every global in "
            "SANDBOXED_PATH_GLOBALS, including MODEL_CONFIG_ROOT, HUB_CACHE_ROOT "
            f"and ENGINE_FILE.\n\n{report}"
        )

    def test_the_write_recorder_sees_a_write(self):
        """THE POSITIVE CONTROL for the recorder. A quiet guard is not a guard."""
        target = REPO_ROOT / "app" / "model_configs"
        if not target.is_dir():  # pragma: no cover
            self.skipTest("no model_configs directory in this checkout")
        probe = target / "__write_recorder_control__.json"
        before = len(WRITES)
        self.addCleanup(lambda: WRITES.__delitem__(slice(before, None)))
        self.addCleanup(lambda: probe.unlink(missing_ok=True))

        probe.write_text("{}", encoding="utf-8")

        self.assertEqual(len(WRITES), before + 1)
        self.assertIn(
            Path(__file__).name,
            WRITES[before][1],
            "the recorder did not capture the stack of the caller that wrote",
        )

    def test_the_watched_paths_are_unchanged(self):
        for path in BYTE_WATCHED_PATHS:
            with self.subTest(path=str(path)):
                self.assertEqual(
                    support.tree_fingerprint(path),
                    BASELINE[str(path)],
                    f"{path} changed during this test run.\n\nMost likely: a "
                    "test reached product code that writes here through a "
                    "module-level global the sandbox does not bind. The list of "
                    "globals is `support.SANDBOXED_PATH_GLOBALS`; the check that "
                    "the list is complete is TheRosterIsDerivedTest above.\n\n"
                    "Also possible: something outside this suite wrote while it "
                    "ran - the owner's own engine republishing engine.json, or a "
                    "second copy of the suite. Check what else was running "
                    "before assuming it was a test.",
                )

    def test_the_tree_watcher_sees_a_write(self):
        """THE POSITIVE CONTROL for layer 3. A quiet watcher is not a watcher."""
        target = REPO_ROOT / "app" / "model_configs"
        if not target.is_dir():  # pragma: no cover
            self.skipTest("no model_configs directory in this checkout")
        probe = target / "__tree_watcher_control__.json"
        before = len(WRITES)
        self.addCleanup(lambda: WRITES.__delitem__(slice(before, None)))
        self.addCleanup(lambda: probe.unlink(missing_ok=True))

        probe.write_text("{}", encoding="utf-8")

        self.assertNotEqual(
            support.tree_fingerprint(target),
            BASELINE[str(target)],
            "the tree watcher did not notice a file appearing under a watched "
            "path, so its silence in the test above means nothing",
        )


if __name__ == "__main__":
    unittest.main()
