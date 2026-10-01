"""What an allowed job is.

The old answer was "whatever string arrived in the request body", which the
runner passed to the system shell. This file replaces that answer with a
narrow one, and the narrowness is the point.

## A job is a recipe, a kind, and a config

    {"recipe": "demo-metrics", "kind": "train", "config": {...}}

- **`recipe`** names a directory the harness owns under `recipes/`. It is not a
  path, not a command and not a file the caller supplies. It is a key, and the
  set of valid keys is the set of directories we shipped.
- **`kind`** is one of five verbs (`prepare`, `train`, `eval`, `convert`,
  `sweep`) and additionally must be one the recipe declares it can do.
- **`config`** is arbitrary JSON, and it is the only caller-controlled data in
  the whole job. It is **written to `run_dir/job.json` and read by the
  entrypoint**. It is never interpolated into the command line, so there is no
  quoting to get wrong and nothing for a caller to escape out of.

## Why argv can never contain caller input

`resolve_argv()` builds a fixed-shape list:

    [interpreter, entrypoint, "--kind", <validated verb>, "--job-json", <our path>]

Every element is either a path we computed or a value validated against a
closed set. `shell=False` means no shell parses any of it, so shell
metacharacters are inert bytes rather than syntax. The two defences are
independent, which is deliberate: even if a recipe name somehow carried a
semicolon, no shell would be there to read it.

## The free-text escape hatch does not survive

There is no `cmd` field and no approval flow that re-enables one. An escape
hatch would have to be defended forever, and "run whatever the user typed" is
not a thing this product ever needs to do - the real jobs are "run this pinned
recipe" (`docs/ARCHITECTURE.md` section 4.11). `POST /jobs` carrying `cmd`
is rejected as an unknown field.

## What is deliberately still missing

`interpreter` is `sys.executable` today. In `docs/ARCHITECTURE.md` section 4.11
it becomes the recipe's own pinned uv virtualenv, one per recipe, because
`unsloth` and `trl>=1.0` cannot share an environment. That is M7 work; the
shape here is built so it is a one-line change and not a redesign.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app import db, paths


REPO_ROOT = Path(__file__).resolve().parents[1]

#: The package's own copy, written by `setup.py` at build time. Named here so
#: `venv_for` can ask "did this recipe come out of the wheel" without a second
#: opinion about where the wheel puts things.
BUNDLED_RECIPES = Path(__file__).resolve().parent / "_bundled" / "recipes"


def _recipes_root() -> Path:
    """The checkout's recipes when there is a checkout, the package's otherwise.

    THE SAME SHAPE AS `diagnosis._ledger_root`, in the same order, for the same
    reason it gives: building a wheel inside a checkout CREATES the bundle, and
    a resolver that preferred the bundle would then serve a developer a stale
    generated copy of a recipe they were editing. The checkout wins whenever it
    is there.

    This is not two places a recipe may live. `recipes/` is the source and the
    only thing a person edits; `app/_bundled/recipes/` is a build artifact,
    generated, and absent from the tree.
    """
    checkout = REPO_ROOT / "recipes"
    if checkout.is_dir():
        return checkout
    return BUNDLED_RECIPES


#: Where shipped recipes live. Module-level and rebindable, matching
#: `db.DB_PATH`, so a test can point at a fixture tree without a mutable
#: registry that a request could ever reach.
RECIPES_ROOT = _recipes_root()

#: The artifact root, shared by every database on the machine. A job's own
#: directory is two levels down: `<runs>/<instance>/job_<id>/`. See
#: `runs_root_for` for why the middle level exists.
RUNS_ROOT = paths.in_data_root("runs")

#: A job's log, inside that job's own run directory. One job is one directory:
#: `job.json` goes in, `job.log` comes out. It used to be a separate flat
#: `logs/` folder at the repo root, which meant a job's artifacts were in two
#: places and only one of them was ever isolated.
LOG_NAME = "job.log"

#: The five verbs from `docs/ARCHITECTURE.md` section 4.11.
KINDS = ("prepare", "train", "eval", "convert", "sweep")

#: A recipe name is a directory name and nothing more. No dots, so `..` cannot
#: be spelled; no separators, so no path can be smuggled through; lower-case
#: only, so a case-insensitive filesystem cannot be used to reach a sibling.
_RECIPE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

#: An instance identity becomes a directory name too, so it is held to the same
#: rule for the same reasons. `db.get_instance()` mints a uuid hex, which fits
#: comfortably; the check exists so a value arriving from anywhere other than
#: that function still cannot become a path.
#:
#: Spelled out again rather than aliased to `_RECIPE_NAME`. The two patterns
#: are identical today and they are not the same policy: recipe names are a
#: shipped-content namespace that could plausibly widen one day (dots, for
#: versioning), and widening it must not silently widen what may become an
#: artifact directory.
_INSTANCE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class JobRejected(ValueError):
    """This job may not run. The message is safe to show the caller."""


@dataclass(frozen=True)
class Recipe:
    name: str
    kinds: tuple[str, ...]
    entrypoint: Path
    description: str = ""

    @property
    def interpreter(self) -> str:
        """argv[0], always ours, and NOT `sys.executable` under a freezer.

        `paths.python_executable` is the seam and the reason is this exact
        line: the runner builds `[interpreter, entrypoint.py, --kind, ...]`,
        and under PyInstaller `sys.executable` is the frozen application - so
        that argv would relaunch this product instead of running somebody's
        training script, silently, with a plausible process appearing. It
        refuses rather than guessing, and `MLH_PYTHON` is what a frozen build
        would set.
        """
        return paths.python_executable()


@dataclass(frozen=True)
class JobSpec:
    recipe: str
    kind: str
    config: dict[str, Any] = field(default_factory=dict)

    def as_json(self) -> str:
        return json.dumps(
            {"recipe": self.recipe, "kind": self.kind, "config": self.config},
            sort_keys=True,
        )


def available_recipes() -> list[str]:
    """Every recipe the harness ships, by name."""
    root = RECIPES_ROOT
    if not root.is_dir():
        return []
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir() and (d / "recipe.toml").is_file()
    )


def venv_for(recipe: Recipe) -> Path:
    """Where this recipe's environment lives — which is NOT always beside it.

    THE_PLAN V.3 A1b: a recipe's definition is package data and its virtualenv
    is user data. In a checkout they are the same directory and this returns
    what it always did, so a developer's existing 4.8 GB `.venv` keeps working
    untouched. In an INSTALLED copy the definition is inside `site-packages`,
    where a multi-gigabyte environment must not go and frequently cannot go:
    site-packages is often not writable by the user running the app, and an
    environment written there would be destroyed by the next `pip install -U`.

    So an installed recipe's environment goes in the per-user data root, beside
    the database and the runs, which is where everything else this product
    materialises already lives.
    """
    directory = recipe.entrypoint.parent
    inside_the_package = directory == BUNDLED_RECIPES or BUNDLED_RECIPES in directory.parents
    if inside_the_package:
        return paths.in_data_root("recipes") / recipe.name / ".venv"
    return directory / ".venv"


def load_recipe(name: Any) -> Recipe:
    """Resolve a recipe name to a recipe, or refuse.

    Every failure below is a refusal with a message, never a traceback and
    never a partial resolution that a later stage might rescue.
    """
    if not isinstance(name, str) or not _RECIPE_NAME.match(name):
        raise JobRejected(f"unknown recipe: {name!r}")

    root = RECIPES_ROOT.resolve()
    directory = (root / name).resolve()
    # Belt and braces with the regex above: even if the pattern were widened by
    # a later edit, a directory outside the recipes root is not a recipe.
    if root != directory.parent or not directory.is_dir():
        raise JobRejected(f"unknown recipe: {name!r}")

    manifest = directory / "recipe.toml"
    if not manifest.is_file():
        raise JobRejected(f"recipe {name!r} has no recipe.toml")
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise JobRejected(f"recipe {name!r} has an unreadable recipe.toml: {exc}")

    declared = data.get("kinds")
    if not isinstance(declared, list) or not declared:
        raise JobRejected(f"recipe {name!r} declares no kinds")
    kinds = tuple(str(k) for k in declared)
    unknown = [k for k in kinds if k not in KINDS]
    if unknown:
        raise JobRejected(f"recipe {name!r} declares unknown kinds: {unknown}")

    entry_name = data.get("entrypoint")
    if not isinstance(entry_name, str) or not entry_name:
        raise JobRejected(f"recipe {name!r} declares no entrypoint")
    entrypoint = (directory / entry_name).resolve()
    if directory not in entrypoint.parents:
        raise JobRejected(f"recipe {name!r} entrypoint escapes its directory")

    return Recipe(
        name=name,
        kinds=kinds,
        entrypoint=entrypoint,
        description=str(data.get("description", "")),
    )


def validate(spec: JobSpec) -> Recipe:
    """Check a spec end to end. Used by the API before anything is stored.

    A job that cannot run is refused at the door, not queued and discovered by
    the runner ten minutes later.
    """
    recipe = load_recipe(spec.recipe)
    if spec.kind not in KINDS:
        raise JobRejected(
            f"unknown kind: {spec.kind!r} (expected one of {', '.join(KINDS)})"
        )
    if spec.kind not in recipe.kinds:
        raise JobRejected(
            f"recipe {spec.recipe!r} does not support kind {spec.kind!r} "
            f"(it supports {', '.join(recipe.kinds)})"
        )
    if not isinstance(spec.config, dict):
        raise JobRejected("config must be an object")
    return recipe


def current_instance() -> str:
    """The identity the artifact paths are keyed on, for the database in use.

    A thin read of `db.get_instance()`, and it lives here rather than in `db`
    because "what names a directory" is this module's question. `db` stores the
    row; this is the one value that becomes a path.
    """
    return db.get_instance()["instance_id"]


def runs_root_for(instance: str | None = None) -> Path:
    """The artifact root for one database.

    `RUNS_ROOT` is shared by every database that has ever run on this machine.
    This is the part underneath it that is not shared, and it is the whole
    reason `db.get_instance()` exists: job ids restart at 1 for every fresh
    database, so `runs/job_1/` is a name two unrelated jobs both hold, and
    whichever ran second wrote over the first one's artifacts. Keyed on the
    instance, `runs/<instance>/job_1/` cannot be the same place twice.

    `instance` defaults to this database's own identity rather than being
    required, so the ordinary caller gets the guarantee without having to
    remember it. Passing one explicitly is for tests that need to name a
    database other than the one currently bound.
    """
    if instance is None:
        instance = current_instance()
    if not isinstance(instance, str) or not _INSTANCE_NAME.match(instance):
        raise JobRejected(f"unusable instance identity: {instance!r}")
    return RUNS_ROOT / instance


def run_dir_for(job_id: int, instance: str | None = None) -> Path:
    """The one directory a job may write to, and everything it leaves behind."""
    return runs_root_for(instance) / f"job_{int(job_id)}"


def log_path_for(job_id: int, instance: str | None = None) -> Path:
    """A job's log, inside that job's own run directory.

    The API does not use this: `/jobs/{id}/log` reads the `log_path` recorded
    on the row, so a job that ran when logs lived in the flat `logs/` folder
    still serves from where it actually wrote. Old rows keep working without a
    translation layer because the path was always data, never a convention the
    reader re-derived.
    """
    return run_dir_for(job_id, instance) / LOG_NAME


def prepare_run_dir(spec: JobSpec, run_dir: Path) -> Path:
    """Create the run directory and write `job.json` into it.

    This is where caller-controlled data goes: into a file the entrypoint
    parses, not onto a command line something else parses.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    job_json = run_dir / "job.json"
    job_json.write_text(spec.as_json(), encoding="utf-8")
    return job_json


def resolve_argv(spec: JobSpec, run_dir: Path) -> list[str]:
    """The argv list. Fixed shape, no caller input, no shell."""
    recipe = validate(spec)
    if not recipe.entrypoint.is_file():
        raise JobRejected(
            f"recipe {spec.recipe!r} entrypoint is missing: {recipe.entrypoint}"
        )
    return [
        recipe.interpreter,
        str(recipe.entrypoint),
        "--kind",
        spec.kind,
        "--job-json",
        str((run_dir / "job.json").resolve()),
    ]


#: Variables a job needs to start at all. Everything else is dropped: a job
#: never inherits the engine's environment, so it never inherits a provider API
#: key that happened to be exported into the engine's shell.
_ENV_PASSTHROUGH = (
    "SystemRoot",     # Windows: python will not start without it
    "windir",
    "TEMP",
    "TMP",
    "TMPDIR",
    "PATH",
    "LANG",
    "LC_ALL",
)


def model_cache_home() -> str:
    """Where the model cache this machine already has actually is.

    THE PASSTHROUGH LIST DOES NOT CARRY `USERPROFILE`, AND THAT IS A REAL COST
    RATHER THAN A TIDY DETAIL. Measured on this machine (Windows 11, CPython
    3.11.15) with the environment `job_env()` builds:

        expanduser(~) = ~
        HF_HUB_CACHE  = ~\\.cache\\huggingface\\hub
        cache exists  = False

    and with `USERPROFILE` put back:

        expanduser(~) = C:\\Users\\example
        HF_HUB_CACHE  = C:\\Users\\example\\.cache\\huggingface\\hub
        cache exists  = True

    So a job did not find the model cache. It made one, at a path whose first
    component is a literal tilde, under whatever its working directory was:
    `runs/2e70a719b0b1480cadd90740819538c6/job_1/~/.cache/huggingface/hub`
    holds 260 MB of re-downloaded SmolLM2-135M from a real training run on this
    machine, next to the copy in the user's home the job could not see. That
    is a bill and a wait for a file that was already there, and for the eval
    kind it is worse than that: a sandbox with no egress sets `HF_HUB_OFFLINE`,
    so the run does not re-download - it REFUSES, and the reason it gives ("the
    base model is not on this machine") is false.

    The fix is not to widen the passthrough list. A job has no business
    inheriting the user's home directory, and this needs exactly one path, so
    exactly one path is named: the model cache, computed here, handed over as
    `HF_HOME`. `HF_HOME`/`HF_HUB_CACHE` already set in the engine's own
    environment win, because a user who moved their cache moved it.

    Returns `""` when this process cannot work out where home is, in which case
    nothing is set and the old behaviour stands - a guess at somebody's home
    directory is not better than no answer.
    """
    for name in ("HF_HUB_CACHE", "HF_HOME"):
        chosen = os.environ.get(name, "").strip()
        if chosen:
            return chosen
    home = os.path.expanduser("~")
    if not home or home == "~" or not os.path.isabs(home):
        return ""
    return str(Path(home) / ".cache" / "huggingface")


def job_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """A minimal environment for a job.

    Telemetry is off by default rather than as an option, per
    `docs/ARCHITECTURE.md` section 8: a training recipe that phones home with
    the user's dataset name is an egress event nobody asked for.

    The model cache is the one path a job is told about, and `model_cache_home`
    holds the measurement that says why. It is set under the name the engine's
    own environment used, so a user who set `HF_HUB_CACHE` gets `HF_HUB_CACHE`
    and does not silently get their cache moved one level up.
    """
    env = {k: os.environ[k] for k in _ENV_PASSTHROUGH if k in os.environ}
    # THERE IS NO PYTHONPATH HERE, AND ITS REMOVAL IS THE POINT.
    #
    # This used to be `env["PYTHONPATH"] = str(REPO_ROOT)`, which put this
    # repository on the import path of every job - including every job in a
    # sandbox that `app/tools/sandbox.py::EGRESS_ENFORCED` promises *is not
    # told where this harness's own API is and is given no token for it, so it
    # cannot reach the engine that holds your database.*
    #
    # MEASURED, from inside a real no-egress sandbox job on this machine: the
    # job did `import app.security`, read `engine.json` through
    # `security.client_token()` and `security.read_portfile()`, and printed
    # `http://127.0.0.1:8078` and a 43-character auth token; it then did
    # `import app.db` and printed `db.DB_PATH` resolving to the owner's real
    # `ml_harness.db`, `exists: True`. The sandbox's OWN
    # `EGRESS_NOT_ENFORCED` is honest that a socket is not blocked and that an
    # absolute path reads the whole disk - so the file was not wrong about the
    # operating system. It was wrong about this one line, which handed a job
    # the two things the promise says it is not given.
    #
    # Nothing shipped needs it: no recipe in `recipes/` imports `app.*`, and
    # the entrypoint that talks to the engine does it over HTTP with the
    # `MLH_PORT` / `MLH_TOKEN` that `app/runner.py` passes DELIBERATELY and
    # documents as a debt. That path is a decision somebody wrote down; this
    # one was a side effect.
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    env["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    env["DO_NOT_TRACK"] = "1"
    cache = model_cache_home()
    if cache:
        env["HF_HUB_CACHE" if os.environ.get("HF_HUB_CACHE") else "HF_HOME"] = cache
    if extra:
        env.update({str(k): str(v) for k, v in extra.items()})
    return env
