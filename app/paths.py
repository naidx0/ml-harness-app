"""Where this installation keeps its things, decided in one place.

`docs/THE_PLAN.md` Phase V step A2 asks for "one `paths.py`, one per-user data
root", and the reason is measured: `pip install .` produces an engine whose
database, token file and run directory all resolve to `parents[1]` of the
package - which in a wheel is `site-packages`. An installed engine would write
its database into somebody's Python installation.

## The rule, and it is the one `diagnosis._ledger_root` already established

**A checkout keeps its own files where they are. An install gets a per-user
root.** The checkout branch is taken whenever the repository is there, decided
by the same marker the ledger loader uses.

THIS IS NOT A COSMETIC PREFERENCE AND IT IS THE HALF THAT MATTERS MOST. Moving
`ml_harness.db` to `%LOCALAPPDATA%` unconditionally would ORPHAN THE DATABASE OF
EVERY PERSON WHO ALREADY HAS ONE - every conversation, every measured fact,
every stored run, silently, with a fresh empty database appearing in its place
and nothing saying why. The migration to a per-user root is a real question with
a real answer and it is not this module's to answer by accident.

## Precedence, and why the environment stays first

Every one of these already had its own environment override - `ML_HARNESS_DB`,
`MLH_ENGINE_FILE` - and those keep winning. A person or a test that has named a
path has said something more specific than this module knows, and the whole
point of the override is that it is not negotiable. `MLH_DATA_ROOT` sits between
the overrides and the default: it moves the ROOT without naming each file.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


#: The file that says "this is a checkout and not an installed package". The
#: same marker `app/diagnosis.py::_ledger_root` uses, and deliberately so: two
#: functions deciding "am I in a repository" by two different tests is two
#: answers waiting to disagree on the machine where it matters.
CHECKOUT_MARKER = Path("docs") / "diagnosis_engine.yaml"

#: What the per-user root is called under whichever directory the platform
#: gives us. One name on every platform, because a support answer that has to
#: ask which operating system you are on before it can name a folder is a worse
#: support answer.
APPLICATION = "ml-harness"


def _checkout() -> Path | None:
    """The repository root, or None when this is an installed package."""
    here = Path(__file__).resolve()
    repository = here.parents[1]
    return repository if (repository / CHECKOUT_MARKER).is_file() else None


def _per_user() -> Path:
    """The platform's place for an application's own data.

    `%LOCALAPPDATA%` on Windows and `~/.local/share` elsewhere, which is the
    XDG default rather than a guess - and `XDG_DATA_HOME` is honoured where it
    is set, because a person who has moved their data directory has said so.

    LOCAL rather than ROAMING on Windows, and it is a real choice. `%APPDATA%`
    follows a user between machines on a domain, and what this directory holds
    is a SQLite database, a token file and run artifacts sized in gigabytes -
    none of which should be copied across a network at login.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / APPLICATION
        return Path.home() / "AppData" / "Local" / APPLICATION
    return Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / APPLICATION


def data_root() -> Path:
    """Where this installation writes. The checkout wins when there is one.

    Read every time rather than resolved at import, for `db.DB_PATH`'s reason:
    a module-level constant computed once is a constant a test cannot move, and
    every path in this product that a test needs to move is a path that was
    moved by rebinding.
    """
    named = os.environ.get("MLH_DATA_ROOT")
    if named:
        return Path(named)
    checkout = _checkout()
    return checkout if checkout is not None else _per_user()


def in_data_root(*parts: str) -> Path:
    """A path under the data root, without creating anything.

    NOTHING IS CREATED HERE ON PURPOSE. A function that made a directory as a
    side effect of being asked where one would be would create a folder in
    somebody's home directory the first time a test imported this module.
    """
    return data_root().joinpath(*parts)


def python_executable() -> str:
    """The interpreter to hand a subprocess - which is NOT always `sys.executable`.

    Phase V step A3, and the reason is one line in `app/jobspec.py`:
    `interpreter` returns `sys.executable` and the runner builds
    `[interpreter, entrypoint.py, --kind, ..., --job-json, ...]`. **Under a
    freezer, `sys.executable` is the frozen application**, so that argv would
    relaunch this product instead of running somebody's training script -
    silently, with a plausible-looking process appearing and no error.

    `sys._MEIPASS` is PyInstaller's own marker and `sys.frozen` is the flag both
    it and cx_Freeze set. When either is present this refuses to guess and says
    so, because there is no honest default: the interpreter a frozen build
    should use is whatever that build shipped or bootstrapped, and
    `docs/THE_PLAN.md` V.4 says that is `uv` rather than a freezer for exactly
    this reason. `MLH_PYTHON` is the seam that build would set.

    In every other case - a checkout, a wheel, a virtualenv - `sys.executable`
    is right and is returned unchanged.
    """
    named = os.environ.get("MLH_PYTHON")
    if named:
        return named
    if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"):
        raise RuntimeError(
            "This is a frozen build and sys.executable is the application "
            "itself, not a Python interpreter. Handing it to a recipe would "
            "relaunch this product instead of running the training script, and "
            "it would look like it worked. Set MLH_PYTHON to the interpreter "
            "this build ships or bootstraps. docs/THE_PLAN.md V.4 recommends "
            "shipping uv and bootstrapping a real interpreter on first run, "
            "and this refusal is the mechanism that makes ignoring it loud."
        )
    return sys.executable


__all__ = [
    "APPLICATION",
    "CHECKOUT_MARKER",
    "data_root",
    "in_data_root",
    "python_executable",
]
