"""Whether the `app` that resolved here belongs to the tree that asked for it.

Registered at `docs/judge_runs/2026-09-07-the-import-guard-prereg.md`, and built
on the measurement at `32319aa` rather than on a reading.

## The failure

A bare `import app` resolves by working directory. From a tree ROOT the cwd
holds `app/` and wins, so the answer is right and the hazard is invisible. From
a SUBDIRECTORY it does not, and the editable install in the one virtualenv on
this machine hands back whichever checkout that install points at. Because
`paths.data_root()` prefers the checkout of whichever `app` was imported, the
mis-resolution reaches the database, the run directory and the engine token -
not only the code.

## This checks; it does not change resolution

Rewiring how `app` resolves is surgery on infrastructure every process in both
checkouts runs through. **This runs after resolution and says whether the answer
was right.** Delete it and behaviour is exactly what it is today.

## WHY THE GUARD LIVES INSIDE THE PACKAGE IT AUDITS

It is the one place that runs without being remembered. A helper the 35th script
has to call is a helper the 35th script will not call - and the 35th script,
written from a subdirectory by somebody who does not know the virtualenv is
shared, is the entire reason this exists. `app/__init__.py` runs on every route
into the package.

**And it still works when it is the wrong tree's copy running.** That is not
obvious and it is the design's load-bearing point: if checkout B's process
wrongly imports checkout A's `app`, then this file is A's file - but it decides
by comparing *where this package is* against *where the calling code is*, and
both are discovered at runtime from real paths. Neither side is a constant baked
in by whichever tree happened to win. A guard that trusted anything about "my
tree" from its own source would be reading the wrong tree's opinion.

## It must be able to convict and must refuse to guess

The one case in the whole measured matrix that reproduces the hazard is a script
in another tree's `scripts/` run from that directory, and `tests/` builds it for
real. A guard that is green everywhere cannot be told from a guard that does
nothing.

The other half matters as much: **a check that cannot identify its subject must
not convict it.** From a tree root the answer is correct and a complaint there
would teach people to ignore the guard. An installed `app`, a notebook, the
REPL, `python -c`, a script in a home directory - in every one of those this
says nothing, because it cannot name the tree the caller belongs to and a
conviction without a subject is worse than no check at all.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app import paths

#: The deliberate override. `paths.py` already establishes the precedent -
#: `MLH_DATA_ROOT`, `ML_HARNESS_DB` and `MLH_ENGINE_FILE` all let a person who
#: has named something beat what the module infers, for the reason given there:
#: a person or a test that has named a path has said something more specific
#: than this module knows. It is an override, not a default, and no shipped file
#: sets it - `tests/` asserts that.
THE_OVERRIDE = "MLH_ALLOW_FOREIGN_APP"

#: This package's own directory, and the tree above it.
_THIS_PACKAGE = Path(__file__).resolve().parent


def the_tree_holding(path: Path) -> Path | None:
    """The checkout `path` sits in, or None when it is not in one.

    ONE MARKER, ONE ANSWER. It calls `paths.CHECKOUT_MARKER` rather than
    restating the test, because two functions deciding "am I in a repository"
    by two different tests is two answers waiting to disagree on the machine
    where it matters - which is the reason `paths._checkout` gives for using
    the marker `diagnosis.py` already uses.

    Reimplementing a rule instead of calling it is also the specific mistake
    that cost this house a wrong lock key last night, one `.lower()` deep.
    """
    try:
        here = Path(path).resolve()
    except (OSError, ValueError):
        return None
    for candidate in (here, *here.parents):
        if (candidate / paths.CHECKOUT_MARKER).is_file():
            return candidate
    return None


#: Frames that are never the caller: the import machinery itself, and this
#: package. Walking out to the first frame that is neither is what finds the
#: code that actually asked for `app`.
#: A CALLER INSIDE AN INSTALLED-PACKAGES DIRECTORY IS A LIBRARY, AND A LIBRARY
#: HAS NO TREE. It was installed into an environment; the directory it happens
#: to sit in says nothing about whose code asked.
#:
#: MEASURED 2026-09-09, and it stopped an engine from starting. The one
#: virtualenv on this machine lives INSIDE one of the two checkouts, so
#: `the_tree_holding(uvicorn/importer.py)` answers with that checkout - and a
#: `python -m uvicorn app.main:app` launched correctly from the OTHER tree,
#: with cwd set to it and `app` resolving to it, was convicted of a crossed
#: import it had not made. The resolution was right and the guard called it
#: wrong, which is the failure this file names as worse than no check: a
#: conviction without a subject teaches people to reach for the override, and
#: an override reached for out of habit is how a real crossing gets waved
#: through later.
#:
#: Skipping the frame rather than staying silent outright: the entry point may
#: sit further out and still be nameable, and it is the entry point this guard
#: wants. For `python -m uvicorn` the next frame is stdlib `runpy`, which is in
#: no checkout, so the answer is silence by the existing rule.
_INSTALLED_PACKAGES = ("site-packages", "dist-packages")


def _is_a_library(where: Path) -> bool:
    return any(part in _INSTALLED_PACKAGES for part in where.parts)


def _the_file_that_asked() -> Path | None:
    """The nearest frame outside this package and outside importlib.

    Returns None when there is no such frame, and None is a silence rather than
    a conviction: `python -c`, the REPL and a frozen entry point all give a
    caller with no real file, and the guard has no subject to name.
    """
    frame = sys._getframe() if hasattr(sys, "_getframe") else None
    while frame is not None:
        name = frame.f_globals.get("__file__")
        if name:
            try:
                where = Path(name).resolve()
            except (OSError, ValueError):
                frame = frame.f_back
                continue
            inside_this_package = where.parent == _THIS_PACKAGE or _THIS_PACKAGE in where.parents
            is_import_machinery = "importlib" in where.parts or where.name in {
                "<frozen importlib._bootstrap>",
                "<frozen importlib._bootstrap_external>",
            }
            if (not inside_this_package and not is_import_machinery
                    and not _is_a_library(where)):
                return where
        frame = frame.f_back
    return None


def why_this_app_is_not_the_callers_app(caller_file: Path | None = None) -> str | None:
    """The sentence for a crossed import, or None when there is nothing to say.

    Silence is the answer in every case where the guard cannot positively
    identify BOTH trees and see that they differ. The four conditions are
    registered in advance; this is them, in order.
    """
    if os.environ.get(THE_OVERRIDE):
        return None

    app_tree = paths._checkout()
    if app_tree is None:
        return None  # an installed package: a legitimate resolution, not a leak

    caller = caller_file if caller_file is not None else _the_file_that_asked()
    if caller is None:
        return None  # no subject to name

    if _is_a_library(caller):
        #: ONE RULE, BOTH DOORS. The frame walker skips libraries; so must
        #: the predicate, or the two disagree for a caller passed in by hand
        #: - which is the same 'two functions deciding one thing two ways'
        #: this file warns about in `the_tree_holding`, and it is how the
        #: first version of this very fix passed its own code and failed its
        #: own test.
        return None  # a library has no tree; the directory it sits in names nobody

    caller_tree = the_tree_holding(caller)
    if caller_tree is None:
        return None  # the caller is not in a checkout: a notebook, a home script

    if caller_tree == app_tree:
        return None  # the ordinary case, and the one that must stay quiet

    return (
        f"THIS IS THE WRONG CHECKOUT'S `app`.\n"
        f"  the code that imported it : {caller}\n"
        f"  which belongs to the tree : {caller_tree}\n"
        f"  but `app` resolved to     : {app_tree}\n"
        f"  so data_root() is         : {paths.data_root()}\n"
        f"\n"
        f"A bare `import app` resolves by working directory. From a tree root the\n"
        f"cwd holds `app/` and wins; from a subdirectory it does not, and the\n"
        f"shared virtualenv's editable install answers instead. This process\n"
        f"would read and write ANOTHER CHECKOUT's database, run directory and\n"
        f"engine token.\n"
        f"\n"
        f"Fix it in the entry point, above the import:\n"
        f"    import sys; from pathlib import Path\n"
        f"    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
        f"`insert(0, ...)` and not `append` - append puts it last, where the\n"
        f"editable install still wins.\n"
        f"\n"
        f"If you meant it, set {THE_OVERRIDE}=1 for this process."
    )


def refuse_a_foreign_app(caller_file: Path | None = None) -> None:
    """Raise when the resolved `app` belongs to another checkout.

    Loud on purpose. The alternative is a warning into a log nobody reads while
    the process writes to the other lane's database - and a mis-resolution that
    only shows up as corrupted data three days later is the failure this exists
    to prevent, not a milder version of it.
    """
    said = why_this_app_is_not_the_callers_app(caller_file)
    if said is not None:
        raise RuntimeError(said)
