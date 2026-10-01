"""Somewhere safe to try something, and an honest account of how safe it is.

`docs/THE_PROPOSAL_LOOP.md` already specifies what a sandbox is. It is not a
thing the user sets up first; it is part of the build:

    "a pinned environment, an isolated working directory, a snapshot of the
     data as it was, and a record of exactly what was installed."

and it exists so that three things are true - it is REPRODUCIBLE, it is
DISPOSABLE, and it CANNOT REACH ANYTHING IT WAS NOT GIVEN.

`app/build.py` already carries the *type*: `Environment` and `DataSnapshot`,
and every `Build` names one. What was missing is the thing that MAKES one, so
this file is that, and it is deliberately the smallest new surface that can be:
`app/jobspec.py` already owns per-database identity, the fixed-shape argv, the
minimal environment and the recipes allowlist, and `app/runner.py` already owns
the bound, the process group and the tree kill. None of that is written twice
here. What is new is a directory with a manifest in it, a pin, a snapshot, a
statement of reach, and a delete that cannot escape itself.

## The user-facing shape

*"Make me somewhere safe to try this."*

    make_sandbox(name="lora-try", recipe="hf-peft-lora", data=["C:/data/train.jsonl"])

and back comes what it pinned, what it snapshotted, what the sandbox can and
cannot reach, and one command that removes the whole thing. Then
`run_in_sandbox` runs a pinned recipe inside it, `list_sandboxes` says what is
there, and `delete_sandbox` removes one.

## 1. WHAT PINS AN ENVIRONMENT ON THIS MACHINE

**A recipe's own `requirements.lock` and its own `.venv`, and nothing this file
invents.** `docs/ARCHITECTURE.md` section 4.11 and `docs/ROADMAP.md` M7 both
settled this before this file existed: environments are pinned uv virtualenvs,
one per recipe, materialised into `recipes/<name>/.venv`, because
`unsloth==2026.8.18` pins `trl<=0.24.0` and `transformers<=5.5.0` and asking uv
for `unsloth` beside `trl>=1.0` does not error - it silently downgrades Unsloth
by a year. `recipes/hf-peft-lora/` is that arrangement already built and
checked in.

So a sandbox does not create an environment. It **names the one the recipe
owns, records the lockfile that defines it, and records the interpreter that
will actually be argv[0]** - and where that interpreter is not there yet, it
says `pinned: false` and why, rather than quietly falling back to whatever the
harness happens to have imported and calling that a pin. A pin that is not
there is a fact about this machine, and this product's whole argument is that a
fact about this machine beats a promise.

Three things are read rather than assumed:

- **the lockfile's digest and its requirement lines**, which become
  `Environment.installs` - the spec's "a record of exactly what was installed";
- **the interpreter path**, `.venv/Scripts/python.exe` or `.venv/bin/python`,
  checked for existence rather than composed and hoped for;
- **the interpreter's Python version, out of `pyvenv.cfg`**, which the venv
  itself wrote. Not `sys.version` - that is the harness's Python, and a sandbox
  that reported the harness's version for the recipe's interpreter would be
  reporting a real number measured off the wrong thing, which
  `app/build.py`'s second hard rule spends four hundred lines on.

`resolve_argv` in `app/jobspec.py` still builds the argv, because the fixed
shape and the recipe allowlist are its business. This substitutes argv[0] with
the interpreter the sandbox pinned - which is precisely the one-line change
that file's own docstring says it was built to accept ("`interpreter` is
`sys.executable` today... That is M7 work; the shape here is built so it is a
one-line change and not a redesign"). It is done here rather than there because
which interpreter runs is a property of the SANDBOX, and a job that runs
outside one should keep the behaviour it has.

## 2. WHAT "NO EGRESS" ACTUALLY MEANS HERE, AND WHAT IT DOES NOT

This is the claim with the most weight and the least ability to be enforced
from Python, so it gets said twice: once here, and once in every result this
module returns, because a person reading a tool result is not reading this file.

`docs/THE_PROPOSAL_LOOP.md` says *"a sandbox that has no egress cannot leak,
whatever the model says"*. **That sentence is true of a container or a network
namespace and it is not true of this.** Saying so is not pedantry: a sandbox
that CLAIMS no egress and cannot enforce it is worse than one that says what it
does, because the claim is what a person would rely on when deciding whether to
put sensitive data in it.

**What is actually enforced, and testable:**

1. **No credentials.** The environment is built by `jobspec.job_env()`, which
   passes through a fixed list of variables and drops everything else, so a
   process inside never inherits the engine's environment - no provider API
   key, no `HF_TOKEN`, nothing that was exported into the shell that started
   the engine.
2. **No address for this harness's own API, and no token for it.** The engine
   is an HTTP server on loopback holding the user's database, and
   `app/tools/training.py` hands every job `MLH_PORT` and `MLH_TOKEN` - its own
   docstring calls that "more authority than a training job needs" and records
   it as debt. A no-egress sandbox does not pass them. That is a real door and
   it is shut, and the cost is visible rather than silent: a recipe that
   reports metrics back through the API cannot, and this module says so in the
   result instead of letting the run fail mysteriously.
3. **It lands inside itself.** `cwd` is the sandbox's own `work/`, and
   `TEMP`/`TMP`/`TMPDIR` point at the sandbox's own `tmp/`, so a process that
   writes a relative path or a temporary file writes inside the sandbox rather
   than into the user's home directory.
4. **Offline switches the libraries this harness actually drives obey.**
   `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, `HF_DATASETS_OFFLINE`, plus the
   telemetry flags `jobspec.job_env` already sets. These are a request that
   `huggingface_hub` and `transformers` honour, not a wall.

**What is NOT enforced, said plainly:**

- **The operating system is not stopping a socket.** Any code that runs inside
  can `socket.connect` to anywhere the machine can reach. There is no network
  namespace, no firewall rule, no container, and no driver. On Windows there is
  no way for an ordinary Python process to deny another process the network
  without one.
- **The filesystem is not a jail.** `cwd` is where a process lands, not where
  it is confined. An absolute path reads the whole disk.
- Therefore **"cannot reach anything it was not given" is true of what we hand
  it and false as a statement about what it can do.** A sandbox here is a
  containment of CREDENTIALS AND DEFAULTS, not of capability. If what you need
  is the kernel-level guarantee, the sandbox has to be a container or a VM, and
  this is not one.

`EGRESS_ENFORCED` and `EGRESS_NOT_ENFORCED` below are those two lists as data,
and they are returned by every tool in this file, so the limit travels with the
sandbox instead of living only in a docstring nobody opens.

## 3. DISPOSABLE, AND THE WORST DEFECT THIS FILE COULD HAVE

*"An experiment that goes wrong is deleted, not untangled."*

A delete that can escape its own directory is the worst thing that could be
written here, so it is defended five times over and each defence would be worth
having alone:

1. **A name is a name, not a path.** Anything containing a separator, a colon,
   a `..` or a NUL is refused outright rather than sanitised - sanitising
   `../secrets` into `secrets` succeeds at something nobody asked for. What
   survives must match `^[a-z0-9][a-z0-9_-]{0,47}$`, so `..` cannot be spelled.
   This is `app/jobspec.py`'s rule for recipe and instance names, held for the
   same reason.
2. **The parent must be the sandboxes root, after resolution.** `resolve()`
   folds `..`, a relative path and a symlink to its target, and then the
   directory's parent is compared to the root by identity. A name that resolved
   anywhere else is refused - which closes a symlink standing where a sandbox
   should be.
3. **It must be a real directory, not a link to one.** Checked with `os.lstat`,
   which does not look through a reparse point.
4. **It must carry our manifest.** `sandbox.json`, present, parseable, and
   naming this sandbox. We delete only what we made. Even if everything above
   were somehow defeated, an arbitrary directory does not have one.
5. **The walk never descends through a link.** `_remove_tree` walks with
   `os.scandir` and `os.lstat` and, for anything that redirects elsewhere,
   removes THE LINK and never looks through it.

   **The escape this closes is real and it is one obvious refactor away.**
   Measured on this machine (Windows 11, CPython 3.11.15) against a junction
   made with `_winapi.CreateJunction`: `os.path.islink` is **False**,
   `DirEntry.is_symlink()` is **False**, `DirEntry.is_dir(follow_symlinks=
   False)` is **True**, and `os.lstat().st_reparse_tag` is
   `IO_REPARSE_TAG_MOUNT_POINT`. So the walk anybody would write - "if it is a
   directory and not a symlink, recurse" - descends into a junction and deletes
   the contents of whatever it points at. It needs no attacker: a person who
   put a junction to their dataset folder inside a sandbox for convenience
   loses the dataset to "dispose of this experiment".

   **The test is the reparse TAG, not the reparse-point attribute.** Not every
   reparse point redirects: OneDrive's Files-On-Demand placeholders are reparse
   points with their own tags, and this repository lives inside a OneDrive
   folder - treating every reparse point as a link would make an ordinary
   cloud-backed directory both undeletable and misdescribed. So only
   `IO_REPARSE_TAG_SYMLINK` and `IO_REPARSE_TAG_MOUNT_POINT` count, plus
   `S_ISLNK` for POSIX. That is the same test CPython's own
   `shutil._rmtree_isdir` makes on Windows, which is some evidence it is the
   right check rather than a clever one.

**AND `shutil.rmtree` IS NOT THE DANGER, which is worth saying because it would
be the easy thing to claim.** Measured, same machine and version: `rmtree` over
a directory containing a junction and a directory symlink deleted neither
target's contents. It is safe here. It is still not what this uses, for two
reasons that survive the measurement: it returns nothing, and a delete that
cannot say what it removed is one a person has to take on trust - `destroy`
reports files, directories, links and bytes; and its junction safety lives
inside `if os.name == 'nt'` in the standard library, guarded by no test in this
repository. Owning the walk means the property is checked against our code, on
whatever Python this ships on.

`tests/test_a_sandbox_is_disposable.py` runs each of the five as an attack
rather than trusting this paragraph, and asserts the junction's properties
first, so a future Python that changed them reports a stale positive control
instead of passing quietly.

## Why there is no migration and no table

A sandbox's record lives in the sandbox, as `sandbox.json`. That is not a
shortcut around the schema, it is the disposability property applied to the
record itself: **deleting the directory deletes the record, so there can be no
row describing a sandbox that is not there.** A database row would outlive the
thing it describes, and reconciling a table against a directory tree is exactly
the untangling a sandbox exists to avoid. The same argument decides where a run
inside a sandbox goes: into the sandbox, not into the jobs table.

The place the sandboxes live is `jobspec.runs_root_for()` - the per-database
artifact root - with `sandboxes/` under it. That is reuse rather than
convenience: `runs_root_for` is what validates the instance identity that names
the directory, so a database whose identity cannot be a directory name is
refused here by the same code that refuses it for a job, and the test suite's
isolation of `jobspec.RUNS_ROOT` covers this file without anything being added
to it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app import build, jobspec, paths, runner, security, config as app_config
from app.tools.evidence import Instrument
from app.tools.registry import tool


# ---------------------------------------------------------------------------
# Vocabulary and layout.


class SandboxRejected(ValueError):
    """This sandbox may not be made, run in, or deleted. The message is safe to show."""


#: The directory under a database's artifact root that holds sandboxes. A
#: sibling of the `job_<id>` directories `jobspec.run_dir_for` makes, and it
#: cannot collide with one: a job directory is `job_` and digits.
SANDBOXES = "sandboxes"

#: The manifest, written at the top of every sandbox. Its presence is the
#: fifth guard on delete: we remove only directories that carry one.
MANIFEST = "sandbox.json"

#: The three directories inside a sandbox, and what each is for. `work` is the
#: isolated working directory a run's `cwd` is set to; `data` holds the
#: snapshot; `tmp` is where the run's TEMP points so a library's scratch files
#: land inside the sandbox rather than in the user's profile.
WORK = "work"
DATA = "data"
TMP = "tmp"
RUNS = "runs"

#: A sandbox name is a directory name and nothing more, exactly as a recipe
#: name is in `app/jobspec.py`. No dots, so `..` cannot be spelled; no
#: separators, so no path can be smuggled through; lower case only, so a
#: case-insensitive filesystem cannot be used to reach a sibling.
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")

#: Characters that mean the caller handed us a path when the argument is a
#: name. Refused rather than stripped: sanitising `../secrets` into `secrets`
#: quietly succeeds at something nobody asked for, and the caller never learns
#: that what they typed was not what ran.
_NOT_A_NAME = ("/", "\\", ":", "..", "\x00", "%", "*", "?", '"', "<", ">", "|")

#: How much of a file this will copy into the snapshot. Above it, the file is
#: RECORDED (path, size, modification time) and not copied, and the sandbox
#: says so - the same trade `app/build.py` makes for a subject's witness: a
#: snapshot that took longer than the run it protects would not be used, and a
#: check nobody runs is not a check. 512 MB is a bound this file states, not a
#: measurement of anything.
SNAPSHOT_BYTE_LIMIT = 512 * 1024 * 1024

#: How long a run inside a sandbox may take before `app/runner.py` kills the
#: whole process tree. Twenty minutes: a sandbox run is a try, not the six-hour
#: training run `app/tools/training.py` bounds.
DEFAULT_TIMEOUT_SECONDS = 20 * 60

#: How much of a run's log the MODEL is handed. The whole log is always on disk
#: and `log_path` always names it; this bounds only what enters the payload.
#:
#: MEASURED, 2026-09-05. One `run_in_sandbox` result in thread 33 was 310,530
#: characters - about 77,632 tokens - and `data_envelope` passes a body through
#: untruncated, so all of it entered the next turn's prompt. Composition of that
#: turn: the tool result 85%, every tool schema 13%, the whole transcript 2%. It
#: is larger than a 64k context window on its own.
#:
#: HEAD AND TAIL RATHER THAN EITHER ALONE, because a run's log has its evidence
#: at both ends and filler in the middle: the setup and the first failure are at
#: the top, the final metrics and the traceback are at the bottom, and the
#: thousand progress lines between them are what makes the file large. Keeping
#: one end would drop half of what a reader needs.
LOG_HEAD_CHARS = 6_000
LOG_TAIL_CHARS = 6_000


def the_output_a_model_can_read(
    output: str, log_path: str, head: int = LOG_HEAD_CHARS, tail: int = LOG_TAIL_CHARS
) -> str:
    """A run's log, bounded, with the elision marked and the whole file named.

    Pure, and separate from the running, so it is tested in an interpreter with
    no sandbox and no recipe - the same argument `recipes/hf-peft-dpo` makes for
    splitting out `adapter_keys_in`.

    THE MARK IS NOT DECORATION. A truncated log that did not say it was
    truncated would be the worst version of this: a model reading it would
    conclude the run ended at the last line it could see, which for a timed-out
    or still-running job is a false statement about the world rather than a
    shorter true one. The note says how much is missing and where the rest is.
    """
    if len(output) <= head + tail:
        return output
    missing = len(output) - head - tail
    return (
        output[:head]
        + f"\n\n[... {missing:,} characters of this log are not shown. The whole "
        f"log is at {log_path} and nothing was deleted - only this copy is "
        "shortened, because a run's log can be larger than the model's whole "
        "context and would push out everything else in the conversation. What "
        "you can see is the first "
        f"{head:,} characters and the last {tail:,}. ...]\n\n"
        + output[-tail:]
    )

#: The Windows reparse tags that mean "this entry is somewhere else". Nothing
#: else counts as a link, and the module docstring's point 5 says why: a
#: reparse point is not necessarily a redirection, and a cloud-file placeholder
#: is a reparse point.
_REDIRECTING_TAGS = (
    getattr(stat, "IO_REPARSE_TAG_SYMLINK", 0xA000000C),
    getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003),
)

#: WHAT A NO-EGRESS SANDBOX ACTUALLY ENFORCES. Read the module docstring's
#: section 2. Returned with every sandbox so the limit travels with the thing
#: rather than living in a file nobody opens.
EGRESS_ENFORCED = (
    "The run inherits none of the engine's environment: no provider API key, "
    "no HF_TOKEN, nothing exported into the shell that started this harness. "
    "app/jobspec.py builds the environment from a fixed passthrough list.",
    "The run is not told where this harness's own API is and is given no token "
    "for it, so it cannot reach the engine that holds your database. This one "
    "is CONDITIONAL and the condition is measured, not assumed - see "
    "`harness_is_importable`: if the interpreter running the job has this "
    "product installed in it, the job can import app.security and read the "
    "token out of engine.json for itself, and this promise moves to "
    "`not_enforced` where it belongs.",
    "The working directory is this sandbox's work/ folder and TEMP, TMP and "
    "TMPDIR point at its tmp/ folder, so relative writes and scratch files "
    "land inside the sandbox.",
    "HF_HUB_OFFLINE, TRANSFORMERS_OFFLINE and HF_DATASETS_OFFLINE are set, "
    "along with the telemetry switches, which huggingface_hub and "
    "transformers obey.",
)

#: WHAT IT DOES NOT ENFORCE. This list is the reason the one above can be
#: believed. Neither is negotiable by a caller and neither is omitted from a
#: result.
EGRESS_NOT_ENFORCED = (
    "The operating system is not stopping a socket. Code that runs in here can "
    "connect anywhere this machine can reach. There is no network namespace, "
    "no firewall rule and no container - a Python process cannot deny another "
    "process the network on Windows without one.",
    "The filesystem is not a jail. cwd is where a run lands, not where it is "
    "confined; an absolute path reads the whole disk.",
    "So 'it cannot reach anything it was not given' is true of what this hands "
    "a run, and false as a statement about what the run can do. If you need "
    "the second one, the sandbox has to be a container or a virtual machine, "
    "and this is not one.",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sandbox_name(raw: Any, *, shape: bool = False) -> str:
    """A caller's word for a sandbox, as a directory name - or a refusal.

    `shape=True` is for `make_sandbox`, where a person typing "LoRA try" should
    get `lora-try` rather than a lecture. `shape=False` is for every tool that
    ACTS on an existing sandbox, where the name must be exactly what is on
    disk: shaping there would let `delete_sandbox("Lora Try")` remove
    `lora-try`, which is a delete the caller did not spell.

    Neither mode ever sanitises a path into a name. A value containing a
    separator, a colon, a `..` or a NUL is refused in both, because the
    alternative is turning `../secrets` into `secrets` and succeeding at
    something nobody asked for.
    """
    text = str(raw or "").strip().strip('"')
    if not text:
        raise SandboxRejected(
            "a sandbox needs a name to be referred to by later. Letters, "
            "digits, hyphens and underscores; it becomes a directory name."
        )
    for token in _NOT_A_NAME:
        if token in text:
            raise SandboxRejected(
                f"{text!r} is a path, not a sandbox name. A sandbox name may "
                "not contain a separator, a colon or a '..'. It names a "
                "directory this harness owns; it never says where that "
                "directory is."
            )
    if shape:
        text = re.sub(r"[^a-z0-9_-]+", "-", text.lower()).strip("-")[:48]
    if not _NAME.match(text):
        raise SandboxRejected(
            f"{text!r} is not a usable sandbox name: lower case letters, "
            "digits, hyphens and underscores, starting with a letter or a "
            "digit, up to 48 characters."
        )
    return text


def _project_of(instrument: Any) -> int | None:
    """Which project this call is in, resolved from the thread. `None` for none.

    The same three lines `app/tools/context.py` uses, and imported inside the
    function for the same reason: `app.events` reaches this module's siblings,
    and a top-level import is a cycle that only shows up in whichever process
    imports them in the unlucky order.

    ANY FAILURE IS `None`, WHICH WIDENS RATHER THAN NARROWS. A listing that
    could not work out which project it was in must show everything: the
    alternative is a person being shown an empty list because a lookup failed,
    concluding their experiment is gone, and making a second one.
    """
    thread_id = getattr(instrument, "thread_id", None)
    if thread_id is None:
        return None
    try:
        from app import events

        thread = events.get_thread(int(thread_id))
        value = (thread or {}).get("project_id")
        return int(value) if value is not None else None
    except Exception:  # noqa: BLE001 - a listing never fails over its own scope
        return None


def sandboxes_root(instance: str | None = None) -> Path:
    """Where this database's sandboxes live.

    Under `jobspec.runs_root_for`, which is the per-database artifact root, and
    that is the reuse this module is built on rather than a second identity
    scheme: `runs_root_for` validates the instance identity that names the
    directory and refuses an unusable one, so a broken identity is refused here
    by the same code that refuses it for a job.
    """
    try:
        return jobspec.runs_root_for(instance) / SANDBOXES
    except jobspec.JobRejected as rejected:
        raise SandboxRejected(str(rejected)) from rejected


def sandbox_path(name: str, instance: str | None = None) -> Path:
    """The one directory a sandbox is, with its parent proved to be the root.

    Guards 1 and 2 from the module docstring, in one place, so no caller in
    this file can reach a directory without passing both. The parent identity
    check is belt and braces with the name regex, exactly as
    `jobspec.load_recipe` does it: even if the pattern were widened by a later
    edit, a directory outside the sandboxes root is not a sandbox.
    """
    root = sandboxes_root(instance).resolve()
    target = (root / name).resolve(strict=False)
    if target.parent != root:
        raise SandboxRejected(
            f"{name!r} does not name a sandbox in {root}. A sandbox is a "
            "directory directly inside that folder and nothing else can be "
            "reached from here."
        )
    return target


# ---------------------------------------------------------------------------
# The pin. What this machine actually has, never what it ought to have.


def _lock_lines(lockfile: Path) -> tuple[str, ...]:
    """The requirement lines in a lockfile, comments and blanks dropped.

    This becomes `Environment.installs` - the spec's "a record of exactly what
    was installed". Exactly: the lines, not a summary of them.
    """
    try:
        text = lockfile.read_text(encoding="utf-8")
    except OSError:
        return ()
    return tuple(
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )


def _venv_python(venv: Path) -> Path:
    """The interpreter a virtualenv holds, on either platform."""
    windows = venv / "Scripts" / "python.exe"
    return windows if windows.is_file() else venv / "bin" / "python"


def _venv_version(venv: Path) -> tuple[str, str]:
    """The venv's Python version, out of the `pyvenv.cfg` the venv itself wrote.

    Returns the version and where it came from. NOT `sys.version`: that is the
    harness's interpreter, and reporting it for the recipe's would be a real
    number measured off the wrong thing - the defect `app/build.py`'s second
    hard rule exists for. When there is no venv, the harness's own version is
    reported AS the harness's own version, which is a different sentence.
    """
    config_file = venv / "pyvenv.cfg"
    try:
        for line in config_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip().lower() in ("version", "version_info") and value.strip():
                return value.strip(), f"read from {config_file}"
    except OSError:
        pass
    return "", ""


def pin(recipe_name: str | None) -> dict[str, Any]:
    """What this sandbox pins, read off this machine.

    A recipe pins the environment; this file does not create one. Where the
    recipe's virtualenv has not been materialised, `pinned` is FALSE and the
    reason says so, and the interpreter falls back to the harness's own - which
    is what would run anyway. It is never described as a pin. A recipe that
    ships a lockfile and has no venv is a real state of this machine and
    `recipes/hf-peft-lora/entrypoint.py` refuses to train in it; the sandbox
    reports the same thing rather than papering over it.
    """
    if not recipe_name:
        return {
            "recipe": None,
            "pinned": False,
            "why": (
                "This sandbox names no recipe, so nothing pins its "
                "environment. It is isolated and it is disposable; it is not "
                "reproducible on another machine, because what would run in it "
                "is whatever this harness happens to have imported. Name a "
                "recipe to pin one."
            ),
            "interpreter": sys.executable,
            "interpreter_is": "this harness's own interpreter",
            "python": sys.version.split()[0],
            "python_source": "sys.version of the harness process",
            "lockfile": None,
            "lock_digest": "",
            "installs": (),
        }

    recipe = jobspec.load_recipe(recipe_name)  # raises JobRejected on an unknown name
    directory = recipe.entrypoint.parent
    # NOT `directory / ".venv"`. An installed copy's recipe lives in
    # site-packages, where a 4.8 GB environment must not go - see
    # `jobspec.venv_for`, which is the one place that decides.
    venv = jobspec.venv_for(recipe)
    interpreter = _venv_python(venv)
    lockfile = directory / "requirements.lock"
    installs = _lock_lines(lockfile) if lockfile.is_file() else ()
    digest = ""
    if lockfile.is_file():
        try:
            digest = hashlib.sha256(lockfile.read_bytes()).hexdigest()
        except OSError:
            digest = ""

    built = interpreter.is_file()
    version, version_source = _venv_version(venv) if built else ("", "")
    return {
        "recipe": recipe.name,
        "kinds": list(recipe.kinds),
        "pinned": bool(built and lockfile.is_file()),
        "why": (
            ""
            if built and lockfile.is_file()
            else (
                f"{recipe.name} declares a pinned environment in "
                f"{lockfile.name} and it has not been built, so nothing here "
                "is pinned yet. The recipe will refuse to train and say how to "
                "build it; this sandbox reports that rather than running "
                "against whatever is installed."
                if lockfile.is_file()
                else f"{recipe.name} ships no requirements.lock, so there is "
                "no pin to record. It runs on this harness's interpreter."
            )
        ),
        "interpreter": str(interpreter) if built else sys.executable,
        "interpreter_is": (
            f"the {recipe.name} virtualenv's own interpreter"
            if built
            else "this harness's own interpreter, because the recipe's venv is not built"
        ),
        "python": version or sys.version.split()[0],
        "python_source": version_source or "sys.version of the harness process",
        "lockfile": str(lockfile) if lockfile.is_file() else None,
        "lock_digest": digest,
        "installs": installs,
    }


# ---------------------------------------------------------------------------
# The snapshot. The data as it was.


def _digest_of(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def snapshot(paths: Any, into: Path) -> list[dict[str, Any]]:
    """Copy the data in, and record what was copied and what was not.

    `build.DataSnapshot.of` does the recording, because a snapshot's size comes
    through `Reading.of_file_size` there and a second way of reading a file's
    size is a second thing to keep honest. This adds the copy and the digest.

    **A file over `SNAPSHOT_BYTE_LIMIT` is recorded and not copied**, and the
    row says `copied: false` with the reason. That is the honest half of a real
    trade: copying 50 GB to protect a run that reads 50 GB doubles the disk for
    no reproducibility that the recorded size and modification time do not
    already give you a way to CHECK. What is lost is named in the row rather
    than discovered later - if the original changes, this sandbox can detect it
    and cannot undo it.

    A directory is recorded, never walked. `app/build.py` says why in its own
    words: a folder's `stat()` says nothing about the files inside it, so only
    its identity is worth anything.
    """
    if isinstance(paths, (str, Path)):
        paths = [paths]
    rows: list[dict[str, Any]] = []
    into.mkdir(parents=True, exist_ok=True)
    for index, raw in enumerate(paths or []):
        source = Path(str(raw).strip().strip('"'))
        try:
            recorded = build.DataSnapshot.of(source)
        except build.BuildInvalid as invalid:
            raise SandboxRejected(
                f"cannot snapshot {source}: {invalid}. A sandbox that names "
                "data it cannot see is a sandbox that will fail after somebody "
                "relied on it."
            ) from invalid

        row: dict[str, Any] = dict(recorded.as_dict())
        row["provenance"] = {"bytes": "measured", "modified_at": "measured"}
        if source.is_dir():
            row.update(
                copied=False,
                copied_to=None,
                digest="",
                why=(
                    "A folder is recorded, not copied. Its stat() says nothing "
                    "about the files inside it, so a snapshot of the folder "
                    "would be a snapshot of nothing."
                ),
            )
            rows.append(row)
            continue

        if recorded.bytes > SNAPSHOT_BYTE_LIMIT:
            row.update(
                copied=False,
                copied_to=None,
                digest="",
                why=(
                    f"{recorded.bytes:.0f} bytes is over this sandbox's copy "
                    f"limit of {SNAPSHOT_BYTE_LIMIT} bytes, so the file is "
                    "recorded where it is rather than duplicated. Its size and "
                    "modification time are here, so a change to it can be "
                    "detected - it cannot be undone."
                ),
            )
            rows.append(row)
            continue

        # The copy is named by index as well as by filename, so two sources
        # that happen to share a basename cannot land on each other. A snapshot
        # that silently held one of two files would be the quietest possible
        # way for this to be wrong.
        destination = into / f"{index:02d}_{source.name}"
        try:
            shutil.copy2(source, destination)
            row.update(
                copied=True,
                copied_to=str(destination),
                digest=_digest_of(destination),
                why="",
            )
        except OSError as error:
            raise SandboxRejected(
                f"cannot copy {source} into the sandbox: {error}"
            ) from error
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# The manifest, and its fingerprint.


def fingerprint(manifest: dict[str, Any]) -> str:
    """What this sandbox IS, as a digest - the reproducibility claim, checkable.

    Over the environment and the data and nothing else. Deliberately NOT over
    the name, the path or the creation time, and `app/build.py` records the
    measured reason: `DataSnapshot.of` once folded `Reading.at` into what a
    build hashes, and because that is `datetime.now()` to the second, approval
    failed for every human who took longer than a second to read a plan. The
    same rule applies here for a different consequence - two sandboxes made
    from the same recipe and the same data ARE the same environment, and a
    fingerprint that disagreed because they were made a minute apart would be
    unable to say so.
    """
    pinned = manifest.get("pin") or {}
    parts = {
        "recipe": pinned.get("recipe"),
        "pinned": bool(pinned.get("pinned")),
        "lock_digest": pinned.get("lock_digest", ""),
        "installs": list(pinned.get("installs") or ()),
        "python": pinned.get("python", ""),
        "egress": bool(manifest.get("egress")),
        "data": [
            {
                "path": row.get("path"),
                "bytes": row.get("bytes"),
                "modified_at": row.get("modified_at"),
                "digest": row.get("digest", ""),
            }
            for row in manifest.get("data") or []
        ],
    }
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


#: The sentence that replaces the second promise when it is not true.
THE_JOB_CAN_IMPORT_US = (
    "The interpreter that runs a job in here HAS THIS PRODUCT INSTALLED IN IT, "
    "so a job can `import app.security`, read engine.json and take the "
    "engine's token, then `import app.db` and read the path to your real "
    "database - without being handed any of it. Withholding the address and "
    "the token does nothing when the code that finds them is on the job's "
    "import path. This is the state of an INSTALLED copy: a checkout is not "
    "installed into its own interpreter, which is why the same product does "
    "not say this when run from one. `app/jobspec.py` says the fix in its own "
    "words - `interpreter` becomes the recipe's own pinned virtualenv (M7, "
    "docs/ARCHITECTURE.md 4.11) - and until it does, this is reported rather "
    "than promised away."
)

#: Measured once per interpreter. The answer cannot change while a process
#: runs: it is a fact about what is installed in another interpreter, and
#: something that installed the product mid-run has done a stranger thing than
#: this cache can be blamed for.
_IMPORTABLE_BY: dict[str, bool] = {}


def harness_is_importable(interpreter: str | None = None) -> bool:
    """Can the interpreter that runs jobs import this harness? ASKED, not assumed.

    The whole reason this is a subprocess and not `"app" in sys.modules` is
    that the question is about a DIFFERENT interpreter than this one - today it
    is usually the same one, and the day `jobspec.interpreter` becomes the
    recipe's own virtualenv it stops being, and this keeps answering correctly
    across that change rather than becoming a stale assumption.

    Asked the way the job would ask: from a directory that is not the checkout,
    with no PYTHONPATH. `-I` isolates it from the user site directory and from
    the current directory, which is exactly the sandbox's own posture - so a
    True here means installed, not merely lying beside something.
    """
    if interpreter is None:
        try:
            # THE SAME CALL `jobspec.Recipe.interpreter` MAKES, not a second
            # opinion about it - argv[0] for every job this file starts.
            interpreter = paths.python_executable()
        except Exception:
            # `paths.python_executable` REFUSES under a freezer with no
            # MLH_PYTHON, and a refusal is not an answer of "no". A run that
            # cannot name its interpreter cannot start either, so the honest
            # report is the cautious one.
            return True

    cached = _IMPORTABLE_BY.get(interpreter)
    if cached is not None:
        return cached

    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in {"PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"}
    }
    try:
        asked = subprocess.run(
            [interpreter, "-I", "-c", "import app.security"],
            cwd=tempfile.gettempdir(),
            env=environment,
            capture_output=True,
            timeout=30,
        )
        answer = asked.returncode == 0
    except Exception:
        # An interpreter that cannot be run at all cannot run a job either.
        # Reporting the reachable state is the safe direction to be wrong in.
        answer = True

    _IMPORTABLE_BY[interpreter] = answer
    return answer


def reach(egress: bool, egress_reason: str) -> dict[str, Any]:
    """What this sandbox can and cannot reach, in the words of section 2.

    Returned with every sandbox, from every tool in this file. The limit
    travels with the thing rather than living in a docstring, because the
    person deciding whether to put sensitive data in a sandbox is reading a
    tool result and not this file.
    """
    # THE ONE PROMISE THAT IS NOT A PROPERTY OF THIS CODE. The other three are
    # things `jobspec` does and can be read off it; this one depends on what is
    # installed in another interpreter, so it is measured and MOVED rather than
    # printed regardless.
    importable = harness_is_importable()
    enforced = [
        line
        for line in EGRESS_ENFORCED
        if not (importable and line.startswith("The run is not told where"))
    ]
    not_enforced = list(EGRESS_NOT_ENFORCED)
    if importable:
        not_enforced.insert(0, THE_JOB_CAN_IMPORT_US)

    return {
        "egress": bool(egress),
        "egress_reason": str(egress_reason or ""),
        "enforced": enforced if not egress else [
            "Nothing on the no-egress list applies: this sandbox declared "
            "egress, so it is handed the engine's address and token and the "
            "offline switches are off. The reason it declared it is above."
        ],
        "not_enforced": not_enforced,
        "say": (
            "This sandbox has no egress, which here means it is handed no "
            "credentials, no address for this harness's API and no network "
            "defaults - it does NOT mean the operating system is stopping it "
            "from opening a socket. Read `not_enforced`."
            if not egress
            else "This sandbox declared egress: " + str(egress_reason)
        ),
    }


def _write_manifest(directory: Path, manifest: dict[str, Any]) -> None:
    (directory / MANIFEST).write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def read_manifest(name: str, instance: str | None = None) -> dict[str, Any]:
    """The manifest of an existing sandbox, or a refusal that names the folder."""
    directory = sandbox_path(name, instance)
    try:
        body = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SandboxRejected(
            f"there is no sandbox named {name!r}. list_sandboxes says what is "
            "there; make_sandbox makes one."
        ) from None
    except (OSError, ValueError) as error:
        raise SandboxRejected(
            f"the sandbox at {directory} has an unreadable {MANIFEST}: {error}. "
            "It is not usable and it is still deletable."
        ) from error
    if not isinstance(body, dict) or body.get("name") != name:
        raise SandboxRejected(
            f"the {MANIFEST} in {directory} does not describe a sandbox called "
            f"{name!r}. Nothing here will act on it."
        )
    return body


# ---------------------------------------------------------------------------
# Making one.


def create(
    name: str | None = None,
    *,
    project_id: int | None = None,
    thread_id: int | None = None,
    purpose: str = "",
    recipe: str | None = None,
    data: Any = None,
    egress: bool = False,
    egress_reason: str = "",
    instance: str | None = None,
) -> dict[str, Any]:
    """Make a sandbox and return everything a person needs to trust it.

    The three properties, in the order `docs/THE_PROPOSAL_LOOP.md` states them:
    the pin (reproducible), the directory (disposable), the reach (what it
    cannot get at). Every one of them is reported as what it actually is on
    this machine rather than as what it is meant to be.
    """
    if egress and not str(egress_reason or "").strip():
        # The same refusal `build.Environment` makes, made here so a person
        # meets it at the moment they ask rather than when a build is
        # validated. A sandbox with unexplained egress has given the guarantee
        # away silently, which is the one way this can be worse than useless.
        raise SandboxRejected(
            "a sandbox that can reach the network must say what for. A sandbox "
            "with no egress is handed no credentials and no address for this "
            "harness's API; one with unexplained egress has given that away "
            "and nobody reading it later can tell why."
        )
    if not egress and str(egress_reason or "").strip():
        raise SandboxRejected(
            "this sandbox has no egress but carries a reason for one, which "
            "will read to the next person as though it does."
        )

    root = sandboxes_root(instance)
    root.mkdir(parents=True, exist_ok=True)
    chosen = sandbox_name(name, shape=True) if name else _next_name(root)
    directory = sandbox_path(chosen, instance)
    if directory.exists():
        raise SandboxRejected(
            f"a sandbox named {chosen!r} is already at {directory}. Names are "
            "how a person refers to one later, so this will not overwrite it - "
            "pick another name, or delete that one first."
        )

    try:
        pinned = pin(recipe)
    except jobspec.JobRejected as rejected:
        raise SandboxRejected(str(rejected)) from rejected

    directory.mkdir(parents=True)
    for child in (WORK, DATA, TMP, RUNS):
        (directory / child).mkdir()

    try:
        rows = snapshot(data, directory / DATA)
    except SandboxRejected:
        # A half-made sandbox is worse than none: it would list, it would look
        # usable and its snapshot would be short. Remove it through the same
        # guarded delete everything else uses, so the cleanup path cannot be a
        # second, less careful remove.
        _remove_tree(directory)
        raise

    manifest = {
        "name": chosen,
        "purpose": str(purpose or "").strip(),
        "created_at": _now(),
        "instance": instance or jobspec.current_instance(),
        # WHICH PROJECT THIS BELONGS TO, and `None` is a real answer rather than
        # a hole. A sandbox made before this field existed has no project, and
        # `belongs_to` shows those to EVERYBODY - they are somebody's real
        # experiments and hiding them behind a filter they predate would be the
        # orphaning this whole approach exists to avoid.
        "project_id": project_id,
        # WHICH CONVERSATION MADE IT, and `None` is a real answer for the same
        # reason `project_id` above says it is: every sandbox made before this
        # field existed has no thread, and a sandbox with no recorded maker is
        # NOBODY'S OWN - which is exactly how `deletable_without_asking` reads
        # it. The field is what lets `full` delete a box this thread made
        # without asking; its absence is what keeps every older box asking.
        #
        # NOT IN THE FINGERPRINT. `fingerprint()` hashes what decides whether
        # two sandboxes are the same ENVIRONMENT - the pin, the reach, the
        # snapshotted data - and who happened to ask for one is not that. A
        # sandbox made on thread 4 and the same sandbox made on thread 9 are
        # the same experiment, and a fingerprint that disagreed would make
        # reproducibility a property of the conversation.
        "thread_id": thread_id,
        "path": str(directory),
        "work_dir": str(directory / WORK),
        "data_dir": str(directory / DATA),
        "tmp_dir": str(directory / TMP),
        "runs_dir": str(directory / RUNS),
        "egress": bool(egress),
        "egress_reason": str(egress_reason or "").strip(),
        "pin": pinned,
        "data": rows,
    }
    manifest["fingerprint"] = fingerprint(manifest)
    _write_manifest(directory, manifest)
    return report(manifest)


def _next_name(root: Path) -> str:
    """`sandbox-1`, `sandbox-2`... for a caller who did not bring a name.

    "Make me somewhere safe to try this" should produce one, not a question
    about naming. The number is one more than the highest that is there, so a
    deleted sandbox does not hand its name to the next one and confuse two
    experiments in a transcript.
    """
    highest = 0
    try:
        for entry in root.iterdir():
            match = re.fullmatch(r"sandbox-(\d+)", entry.name)
            if match and entry.is_dir():
                highest = max(highest, int(match.group(1)))
    except OSError:
        pass
    return f"sandbox-{highest + 1}"


def environment_for(name: str, instance: str | None = None) -> build.Environment:
    """This sandbox as the `Environment` a `Build` carries.

    THE POINT OF CONNECTION, and the reason this module returns one rather than
    describing itself in its own vocabulary. `app/build.py` already has the
    type and every `Build` names one; `Build.validate` already refuses a step
    whose tool may leave this machine inside an environment that declared no
    egress. What was missing was something that MAKES the environment, and
    making it here means a proposal's environment is a directory that exists on
    this disk with a snapshot in it, not a name in a plan.
    """
    manifest = read_manifest(name, instance)
    pinned = manifest.get("pin") or {}
    snapshots = tuple(
        build.DataSnapshot(
            path=str(row.get("path", "")),
            bytes=float(row.get("bytes") or 0.0),
            modified_at=str(row.get("modified_at", "")),
            how=str(row.get("how", "")),
        )
        for row in manifest.get("data") or []
    )
    return build.Environment(
        name=manifest["name"],
        working_dir=str(manifest.get("work_dir") or manifest.get("path")),
        egress=bool(manifest.get("egress")),
        egress_reason=str(manifest.get("egress_reason") or ""),
        data=snapshots,
        installs=tuple(pinned.get("installs") or ()),
        python=str(pinned.get("python") or ""),
    )


def report(manifest: dict[str, Any]) -> dict[str, Any]:
    """One sandbox, described for a person - what it pinned, holds and can reach."""
    pinned = manifest.get("pin") or {}
    rows = manifest.get("data") or []
    copied = [row for row in rows if row.get("copied")]
    total = sum(float(row.get("bytes") or 0.0) for row in copied)
    return {
        "ok": True,
        "name": manifest["name"],
        "purpose": manifest.get("purpose", ""),
        "created_at": manifest.get("created_at", ""),
        "path": manifest.get("path", ""),
        "work_dir": manifest.get("work_dir", ""),
        "fingerprint": manifest.get("fingerprint", ""),
        "pinned": pinned,
        "snapshotted": rows,
        "snapshot_bytes": total,
        "snapshot_provenance": "measured by stat() on each file as it was copied",
        "reach": reach(
            bool(manifest.get("egress")), str(manifest.get("egress_reason") or "")
        ),
        "delete_with": f"delete_sandbox({manifest['name']!r})",
        "say": _say(manifest),
    }


def _say(manifest: dict[str, Any]) -> str:
    """The paragraph a person reads. Every clause of it is a thing on disk."""
    pinned = manifest.get("pin") or {}
    rows = manifest.get("data") or []
    copied = [row for row in rows if row.get("copied")]
    recorded = [row for row in rows if not row.get("copied")]

    if pinned.get("pinned"):
        environment = (
            f"It pins the {pinned['recipe']} environment: "
            f"{len(pinned.get('installs') or ())} locked requirements from "
            f"{pinned.get('lockfile')}, run by {pinned.get('interpreter')} "
            f"(Python {pinned.get('python')}, {pinned.get('python_source')})."
        )
    else:
        environment = f"Nothing is pinned. {pinned.get('why', '')}"

    if not rows:
        held = "It holds no data snapshot - nothing was handed to it."
    else:
        held = (
            f"It holds {len(copied)} copied file(s) as they were, and records "
            f"{len(recorded)} more where they are."
        )

    if manifest.get("egress"):
        reaching = (
            "It declared egress: " + str(manifest.get("egress_reason"))
            + " So it is handed this harness's address and token."
        )
    else:
        reaching = (
            "It is handed no credentials, no address for this harness's API "
            "and no network defaults. That is what 'no egress' means here; the "
            "operating system is not stopping it from opening a socket, and "
            "anything that says otherwise is overclaiming."
        )

    return (
        f"{manifest['name']} is at {manifest.get('path')}. {environment} {held} "
        f"{reaching} Delete it with delete_sandbox({manifest['name']!r}); "
        "nothing outside it goes with it."
    )


# ---------------------------------------------------------------------------
# Running something in one.


def folder(manifest: dict[str, Any], key: str, name: str) -> Path:
    """One of a sandbox's own directories, recomposed if the manifest lost it.

    `sandbox.json` is a file on the user's disk and a file on the user's disk
    can be edited, truncated or half-written by a crash. Reading it with `[]`
    turns that into a `KeyError` out of a registered tool, and this product's
    boundary rule is that a person is never handed a stack trace. The fallback
    is not a guess: every one of these is a fixed child of the sandbox's own
    directory, which is where they were made.
    """
    recorded = str(manifest.get(key) or "").strip()
    if recorded:
        return Path(recorded)
    return Path(str(manifest.get("path") or "")) / name


def _run_directory(manifest: dict[str, Any]) -> Path:
    runs = folder(manifest, "runs_dir", RUNS)
    runs.mkdir(parents=True, exist_ok=True)
    highest = 0
    for entry in runs.iterdir():
        match = re.fullmatch(r"run_(\d+)", entry.name)
        if match:
            highest = max(highest, int(match.group(1)))
    made = runs / f"run_{highest + 1}"
    made.mkdir()
    return made


def _environment(manifest: dict[str, Any]) -> dict[str, str]:
    """The environment a run inside this sandbox gets. Section 2, as code.

    `jobspec.job_env` is what builds it, because the passthrough list and the
    telemetry switches are its business and a second copy of them would drift
    from the one every other job gets. What is added here is the sandbox's own
    TEMP and the offline switches; what is deliberately NOT added, unless this
    sandbox declared egress, is `MLH_PORT` and `MLH_TOKEN`.
    """
    temp = str(folder(manifest, "tmp_dir", TMP))
    extra = {"TEMP": temp, "TMP": temp, "TMPDIR": temp}
    if manifest.get("egress"):
        # Declared, and the reason is in the manifest where a person can read
        # it. `app/tools/training.py` hands every job these; a sandbox that
        # said why is the only place this file does.
        extra["MLH_PORT"] = str(app_config.PORT)
        token = security.client_token()
        if token:
            extra["MLH_TOKEN"] = token
    else:
        extra.update(
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            HF_DATASETS_OFFLINE="1",
        )
    return jobspec.job_env(extra)


#: The kinds that hold weights on the accelerator for long enough to page. NOT
#: `eval`: scoring an adapter loads the base for a few minutes while the
#: harness's judge is - by design - resident on the same card to grade the
#: answers afterwards, and refusing that would refuse the product's own
#: paired comparison. `prepare` and `convert` read and write files.
GPU_KINDS = frozenset({"train", "sweep"})

#: Below this the card is treated as free even if something small is resident -
#: a desktop compositor, a display driver - because refusing a run over 300 MB
#: of Windows would be a refusal about nothing.
GPU_CROWDED_ABOVE_GB = 1.0


def _gpu_occupancy(runner=subprocess.run) -> dict[str, Any] | None:
    """What is on the card right now: used and total memory, and which Ollama
    models are resident. `None` when there is no NVIDIA card to ask.

    MEASURED, the way `hwdetect` measures: `nvidia-smi` for the memory and the
    local Ollama daemon's own `/api/ps` for the names. The harness runs its
    judge through that daemon, so the model most likely to be sitting on the
    card when a training run starts is the harness's own.
    """
    from app import hwdetect

    try:
        asked = runner(
            [
                hwdetect._nvidia_smi_path(),
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        line = (asked.stdout or "").strip().splitlines()
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not line:
        return None
    try:
        used_mib, total_mib = (float(part.strip()) for part in line[0].split(",")[:2])
    except (ValueError, IndexError):
        return None

    resident: list[dict[str, Any]] = []
    try:
        from app.tools import models as local_models

        listed = local_models._ollama("/api/ps") or {}
        for entry in listed.get("models") or []:
            size = float(entry.get("size_vram") or entry.get("size") or 0) / 1e9
            resident.append({"name": str(entry.get("name") or "?"), "size_gb": round(size, 2)})
    except Exception:  # noqa: BLE001 - a daemon that is not there is not an error here
        resident = []

    return {
        "used_gb": round(used_mib / 1024, 2),
        "total_gb": round(total_mib / 1024, 2),
        "resident": resident,
        "source": "nvidia-smi --query-gpu=memory.used,memory.total; ollama /api/ps",
    }


def _gpu_is_crowded(occupancy: dict[str, Any] | None) -> str | None:
    """The sentence that refuses a training run on a card something else holds,
    or `None` when the card is free enough to start.

    WHY THIS EXISTS. On 2026-09-01 the same 1.7B LoRA recipe, same rows, same
    seed, ran at 0.15 steps a second for 56 minutes and then at 5.4 steps a
    second for 46 seconds. Both peaked at 6.65 GB on an 8 GB card. The slow run
    started while the harness's own judge model held 4.9 GB of that card; the
    Windows driver spilled the difference into system memory and the run spent
    an hour paging. Nothing refused it, nothing warned, and the log looked like
    training. A 36x slowdown that reads as progress is exactly the failure the
    product exists to name.
    """
    if not occupancy:
        return None
    used = float(occupancy.get("used_gb") or 0.0)
    resident = list(occupancy.get("resident") or [])
    if used <= GPU_CROWDED_ABOVE_GB and not resident:
        return None
    if used <= GPU_CROWDED_ABOVE_GB:
        # Something is loaded but not paged in; the card is effectively free.
        return None
    names = ", ".join(f"{m['name']} ({m['size_gb']} GB)" for m in resident) or "another process"
    total = float(occupancy.get("total_gb") or 0.0)
    return (
        f"The GPU is already holding {used} GB of {total} GB - {names}. A "
        "training run started now will spill into system memory and crawl: "
        "the last time this happened, 200 steps that take 46 seconds on a free "
        "card took 56 minutes. Unload what is resident first (for an Ollama "
        "model: `ollama stop <name>`), or pass config.share_gpu = true to run "
        "anyway and accept the paging. Nothing was started."
    )


def run(
    name: str,
    kind: str = "train",
    config: dict[str, Any] | None = None,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    instance: str | None = None,
) -> dict[str, Any]:
    """Run this sandbox's pinned recipe inside it, bounded, and report what happened.

    Nothing about launching a process is written here. `app/jobspec.py` builds
    the fixed-shape argv from a recipe the harness ships and writes the
    caller's config into `job.json` where no shell parses it;
    `app/runner.py::_run_streaming` owns the process group, the bound and the
    tree kill, and its docstring records the measurement that proves the bound
    is real. Two things are this file's:

    - **argv[0] is the interpreter the sandbox pinned.** `jobspec.resolve_argv`
      returns `sys.executable` there, and its own docstring says that becomes
      the recipe's venv when per-recipe environments arrive. Which interpreter
      runs is a property of the sandbox, so the substitution is here and a job
      that runs outside a sandbox keeps the behaviour it has.
    - **`cwd` is the sandbox's `work/`**, so a run that writes a relative path
      writes inside the sandbox.

    A run's directory, log and `job.json` all live inside the sandbox, so
    deleting the sandbox deletes them. That is the disposability property
    applied to the run as well as to the record: a jobs row would outlive the
    directory it describes.
    """
    manifest = read_manifest(name, instance)
    pinned = manifest.get("pin") or {}
    recipe_name = pinned.get("recipe")
    if not recipe_name:
        raise SandboxRejected(
            f"{name!r} pins no recipe, so there is nothing in it to run. Make "
            "one with a recipe, or use its working directory yourself: "
            f"{folder(manifest, 'work_dir', WORK)}"
        )

    spec = jobspec.JobSpec(
        recipe=str(recipe_name), kind=str(kind), config=dict(config or {})
    )
    try:
        jobspec.validate(spec)
    except jobspec.JobRejected as rejected:
        raise SandboxRejected(str(rejected)) from rejected

    if spec.kind in GPU_KINDS and not bool((config or {}).get("share_gpu")):
        crowded = _gpu_is_crowded(_gpu_occupancy())
        if crowded:
            raise SandboxRejected(crowded)

    run_dir = _run_directory(manifest)
    jobspec.prepare_run_dir(spec, run_dir)
    try:
        argv = list(jobspec.resolve_argv(spec, run_dir))
    except jobspec.JobRejected as rejected:
        raise SandboxRejected(str(rejected)) from rejected

    interpreter = str(pinned.get("interpreter") or sys.executable)
    if Path(interpreter).is_file():
        argv[0] = interpreter

    log_path = run_dir / jobspec.LOG_NAME
    work_dir = folder(manifest, "work_dir", WORK)
    work_dir.mkdir(parents=True, exist_ok=True)
    folder(manifest, "tmp_dir", TMP).mkdir(parents=True, exist_ok=True)

    bound = max(1, int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS))
    timed_out = False
    try:
        exit_code = runner._run_streaming(
            argv, bound, log_path, cwd=work_dir, env=_environment(manifest)
        )
    except subprocess.TimeoutExpired:
        timed_out = True
        exit_code = -1
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write("\nTIMEOUT\n")
    except OSError as error:
        with open(log_path, "w", encoding="utf-8") as handle:
            handle.write(f"FAILED TO START: {error}\n")
        exit_code = runner.REJECTED

    try:
        output = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        output = ""

    return {
        "ok": exit_code == 0,
        "sandbox": name,
        "recipe": recipe_name,
        "kind": spec.kind,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "timeout_seconds": bound,
        "run_dir": str(run_dir),
        "log_path": str(log_path),
        # BOUNDED BEFORE IT ENTERS THE PAYLOAD, not after. `data_envelope`
        # wraps a tool result for provenance and does not shorten it, so an
        # unbounded `output` here is an unbounded prompt there - measured at
        # 85% of a 91,174-token turn. The file itself is untouched and
        # `log_path` above names it.
        "output": the_output_a_model_can_read(output, str(log_path)),
        "output_chars_total": len(output),
        "interpreter": argv[0],
        "pinned": bool(pinned.get("pinned")),
        "cwd": str(work_dir),
        "reach": reach(
            bool(manifest.get("egress")), str(manifest.get("egress_reason") or "")
        ),
        "note": (
            ""
            if manifest.get("egress")
            else (
                "This sandbox has no egress, so the run was not given this "
                "harness's address or token. A recipe that reports its metrics "
                "through the engine API cannot do so from in here - that is "
                "the cost of no egress, and it is said out loud rather than "
                "left to look like a failure."
            )
        ),
    }


# ---------------------------------------------------------------------------
# Deleting one. Read section 3 of the module docstring before touching this.


def _redirects_elsewhere(status: os.stat_result) -> bool:
    """Is this entry somewhere else? A link, a directory symlink, a junction.

    A POSIX symlink answers through `S_ISLNK`. Windows answers through the
    reparse TAG and not through `FILE_ATTRIBUTE_REPARSE_POINT`, because not
    every reparse point is a redirection - a cloud-file placeholder is one, and
    this repository lives inside a OneDrive folder. Treating every reparse
    point as a link would make an ordinary cloud-backed directory both
    undeletable and misdescribed, which is a false refusal about nothing.
    """
    if stat.S_ISLNK(status.st_mode):
        return True
    return getattr(status, "st_reparse_tag", 0) in _REDIRECTING_TAGS


def _remove_tree(root: Path) -> dict[str, int]:
    """Remove `root` and everything really inside it. Never look through a link.

    THE ONE THING THIS FILE MUST NOT GET WRONG. Read section 3 of the module
    docstring for the measurements: the walk anybody would write descends
    through a Windows junction, because `os.path.islink` is False for one and
    `DirEntry.is_dir(follow_symlinks=False)` is True for one, and it therefore
    deletes the contents of whatever the junction points at.

    So: `os.lstat` on every entry, which does not look through a reparse point;
    anything that redirects has THE LINK removed and is never descended into;
    everything else is a real file or a real directory on this filesystem.

    Counting is the other half of why this is not `shutil.rmtree`, which is
    safe here and returns nothing. A delete that cannot say what it removed is
    a delete a person has to take on trust, and this one is about to be handed
    to people as the reason an experiment is disposable.
    """
    removed = {"files": 0, "directories": 0, "links": 0, "bytes": 0}
    try:
        entries = list(os.scandir(root))
    except OSError:
        entries = []
    for entry in entries:
        path = Path(entry.path)
        try:
            status = os.lstat(entry.path)
        except OSError:
            continue
        if _redirects_elsewhere(status):
            # Remove the LINK. `os.unlink` handles a POSIX symlink of either
            # kind and a Windows file symlink; a junction and a Windows
            # directory symlink need `rmdir`, which removes the link and never
            # its target.
            try:
                os.unlink(path)
            except OSError:
                try:
                    os.rmdir(path)
                except OSError:
                    continue
            removed["links"] += 1
            continue
        if stat.S_ISDIR(status.st_mode):
            inner = _remove_tree(path)
            for key, value in inner.items():
                removed[key] += value
            continue
        removed["bytes"] += int(getattr(status, "st_size", 0) or 0)
        try:
            os.chmod(path, stat.S_IWRITE)
        except OSError:
            pass
        try:
            os.unlink(path)
        except OSError:
            continue
        removed["files"] += 1
    try:
        os.rmdir(root)
        removed["directories"] += 1
    except OSError:
        pass
    return removed


def destroy(name: str, instance: str | None = None) -> dict[str, Any]:
    """Delete one sandbox, and nothing that is not inside it.

    The five guards from the module docstring, in order, each one refusing
    before anything is removed. Guard 4 is the one worth reading twice: the
    directory must carry OUR manifest, naming THIS sandbox. We delete what we
    made, not what happens to be at a path somebody handed us.
    """
    resolved = sandbox_name(name, shape=False)  # guard 1
    directory = sandbox_path(resolved, instance)  # guard 2

    try:
        status = os.lstat(directory)
    except OSError:
        raise SandboxRejected(
            f"there is no sandbox named {resolved!r} to delete. Nothing was "
            "removed. list_sandboxes says what is there."
        ) from None
    if _redirects_elsewhere(status):  # guard 3
        raise SandboxRejected(
            f"{directory} is a link, not a sandbox. Deleting it would mean "
            "deleting whatever it points at, which is exactly the escape this "
            "refusal exists for. Nothing was removed."
        )
    if not stat.S_ISDIR(status.st_mode):
        raise SandboxRejected(
            f"{directory} is not a directory, so it is not a sandbox. Nothing "
            "was removed."
        )

    manifest = read_manifest(resolved, instance)  # guard 4

    # Measured before it goes, because afterwards there is nothing to measure
    # and a number reported after a delete would have to be remembered.
    removed = _remove_tree(directory)  # guard 5
    gone = not directory.exists()
    return {
        "ok": gone,
        "name": resolved,
        "path": str(directory),
        "deleted": gone,
        "removed": removed,
        "removed_provenance": "counted while walking the directory as it was removed",
        "was": {
            "purpose": manifest.get("purpose", ""),
            "created_at": manifest.get("created_at", ""),
            "fingerprint": manifest.get("fingerprint", ""),
            "recipe": (manifest.get("pin") or {}).get("recipe"),
        },
        "outside_untouched": (
            "Only entries really inside this directory were removed. Anything "
            "that redirected elsewhere - a symlink, a directory symlink, a "
            "Windows junction - had the link removed and was never followed, "
            "so nothing outside this directory was reached."
        ),
        "detail": (
            ""
            if gone
            else (
                f"{directory} is still there. Something in it is held open - "
                "on Windows that is usually a process still writing to a run "
                "log. Nothing outside it was touched; try again once the run "
                "has stopped."
            )
        ),
    }


def belongs_to(row: Mapping[str, Any], project_id: int | None) -> bool:
    """Should this sandbox appear in a listing asked from `project_id`?

    THREE CASES AND THE MIDDLE ONE IS THE WHOLE DESIGN.

    * The caller named no project - a call from outside any conversation, or a
      test. Everything shows. Narrowing on an absent question would hide
      somebody's experiments to answer a question nobody asked.
    * **The sandbox names no project.** It was made before the manifest carried
      one. It shows EVERYWHERE, because it is a real directory holding real data
      and a filter it predates must not be the thing that loses it. This is what
      makes the change safe on a machine that already has sandboxes.
    * Both name one. They have to match.

    A property rather than a query, so the rule is in one place and the two
    callers - the listing and anything that comes later - cannot drift.
    """
    if project_id is None:
        return True
    theirs = row.get("project_id")
    return theirs is None or int(theirs) == int(project_id)


def every(
    instance: str | None = None, project_id: int | None = None
) -> list[dict[str, Any]]:
    """Every sandbox this database has, newest first, optionally one project's.

    Read off the directory tree, because the directory IS the record. A
    directory with no readable manifest is reported as unusable rather than
    hidden: it is still taking up disk and it is still deletable, and a listing
    that quietly omitted it would leave a person with a folder nobody claims.

    **AN UNREADABLE DIRECTORY IS NEVER FILTERED OUT.** It has no manifest, so it
    has no project, and deciding it belongs to somebody else would be inventing
    the one fact it is unreadable for. It shows in every listing, which is the
    same reason it shows at all.
    """
    root = sandboxes_root(instance)
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        try:
            manifest = read_manifest(entry.name, instance)
            if not belongs_to(manifest, project_id):
                continue
            rows.append(report(manifest))
        except SandboxRejected as rejected:
            rows.append(
                {
                    "ok": False,
                    "name": entry.name,
                    "path": str(entry),
                    "usable": False,
                    "detail": str(rejected),
                }
            )
    rows.sort(key=lambda row: str(row.get("created_at", "")), reverse=True)
    return rows


# ---------------------------------------------------------------------------
# The tools. One declaration, two callers - the model's call and the button.
#
# `group="Train"` on all four, and that is a decision rather than a shrug. The
# group names a panel in the control surface and the heading in the capability
# fragment `app/instructions/capabilities.py` renders, where each group carries
# a one-line gloss written by hand; a new group renders without one. "Train" is
# glossed "training itself, which this harness runs rather than describes", and
# a sandbox is where the thing that group runs actually runs, so it belongs
# with `list_recipes`, `start_training` and `training_status` rather than in a
# heading with nothing under it.


@tool(
    "make_sandbox",
    description=(
        "Make an isolated place on this machine to try something: a pinned "
        "environment, its own working directory, and a snapshot of the data as "
        "it is right now. Reports exactly what it pinned, what it copied, and "
        "what the sandbox can and cannot reach - including the parts of 'no "
        "egress' this harness cannot enforce. An experiment that goes wrong is "
        "deleted with delete_sandbox rather than untangled."
    ),
    schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "What to call it. Becomes a directory name; letters, "
                    "digits, hyphens and underscores. Left out, one is chosen."
                ),
            },
            "purpose": {
                "type": "string",
                "description": (
                    "What this sandbox is for, in the user's words, so the "
                    "next person reading the folder knows why it exists."
                ),
            },
            "recipe": {
                "type": "string",
                "description": (
                    "Which pinned backend this sandbox is for, e.g. "
                    "'hf-peft-lora'. This is what pins the environment; "
                    "without one the sandbox is isolated and disposable but "
                    "not reproducible."
                ),
            },
            "data": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Files on this machine to snapshot into the sandbox. Each "
                    "is copied as it is now, with its size and modification "
                    "time recorded. Large files are recorded where they are "
                    "rather than duplicated, and the result says which."
                ),
            },
            "egress": {
                "type": "boolean",
                "description": (
                    "Whether work in this sandbox may reach the network. False "
                    "by default. True requires egress_reason."
                ),
            },
            "egress_reason": {
                "type": "string",
                "description": (
                    "What the network is needed for. Required when egress is "
                    "true; refused when it is false."
                ),
            },
        },
    },
    reads=("recipes", "datasets", "filesystem"),
    writes=("filesystem",),
    provides=("sandbox.instance.create",),
    label="Make a sandbox",
    group="Train",
    verb="make an isolated place to try this",
    order=53,
)
def make_sandbox(
    name: str | None = None,
    purpose: str = "",
    recipe: str | None = None,
    data: Any = None,
    egress: bool = False,
    egress_reason: str = "",
    *,
    instrument: Instrument | None = None,
) -> dict[str, Any]:
    """Somewhere safe to try something, with an honest account of how safe."""
    try:
        return create(
            name,
            project_id=_project_of(instrument),
            #: WRITTEN AT THE MOMENT IT IS MADE, because there is no later
            #: moment at which it can be worked out. A directory on disk cannot
            #: be asked which conversation asked for it.
            thread_id=getattr(instrument, "thread_id", None),
            purpose=purpose,
            recipe=recipe,
            data=data,
            egress=bool(egress),
            egress_reason=egress_reason,
        )
    except SandboxRejected as rejected:
        return {
            "ok": False,
            "error": "sandbox_rejected",
            "detail": str(rejected),
            "help": (
                "Nothing was made and nothing was left behind. list_recipes "
                "says which recipes can pin an environment on this machine."
            ),
        }


@tool(
    "list_sandboxes",
    description=(
        "List the sandboxes on this machine, what each one pinned, what data "
        "it holds and what it can reach. Use it before making another one, so "
        "an experiment is resumed rather than duplicated."
    ),
    schema={"type": "object", "properties": {}},
    reads=("filesystem", "runs"),
    writes=(),
    provides=("sandbox.instance.list",),
    label="List sandboxes",
    group="Train",
    verb="list the sandboxes on this machine",
    order=54,
)
def list_sandboxes(*, instrument: Instrument | None = None) -> dict[str, Any]:
    project_id = _project_of(instrument)
    try:
        rows = every(project_id=project_id)
    except SandboxRejected as rejected:
        return {"ok": False, "error": "sandbox_rejected", "detail": str(rejected)}
    return {
        "ok": True,
        "count": len(rows),
        "sandboxes": rows,
        "root": str(sandboxes_root()),
        "source": (
            "the sandboxes directory under this database's artifact root"
            + (
                f", narrowed to project {project_id}"
                if project_id is not None
                else ""
            )
        ),
        # SAID OUT LOUD, because a filtered listing that looked complete is how
        # somebody concludes an experiment is gone and makes a second one.
        "scope_note": (
            "This lists the sandboxes of THIS project, plus any made before "
            "sandboxes recorded a project - those belong to nobody in "
            "particular and show everywhere rather than being lost behind a "
            "filter they predate. Every sandbox is still on disk under one "
            "root; the directory layout is shared and the listing is what is "
            "scoped."
            if project_id is not None
            else "Every sandbox under this database's artifact root. No "
            "conversation asked, so nothing was narrowed."
        ),
        # THE SAME LIST `reach()` BUILDS, and built the same way rather than
        # copied - a listing that omitted the measured line would be the one
        # place this product still made the promise it just stopped making.
        "reach_note": reach(False, "")["not_enforced"],
    }


@tool(
    "run_in_sandbox",
    description=(
        "Run a sandbox's pinned recipe inside that sandbox, bounded, with its "
        "working directory and its environment. Needs an approval before it "
        "runs, because it starts a process on this machine. Returns the exit "
        "code and everything the run printed."
    ),
    schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Which sandbox to run in. Exactly as it is named.",
            },
            "kind": {
                "type": "string",
                "description": "What the recipe should do.",
                "enum": list(jobspec.KINDS),
            },
            "config": {
                "type": "object",
                "description": (
                    "Settings for the recipe. Written into the run's job.json "
                    "and read there; never put on a command line."
                ),
                "additionalProperties": True,
            },
            "timeout_seconds": {
                "type": "integer",
                "description": (
                    "Hard wall-clock bound. The whole process tree is killed "
                    "at this point. Default twenty minutes."
                ),
            },
        },
        "required": ["name"],
    },
    reads=("recipes", "runs", "filesystem"),
    writes=("filesystem",),
    approval="always",
    provides=("sandbox.instance.run",),
    label="Run in a sandbox",
    group="Train",
    verb="run this sandbox's recipe inside it",
    order=55,
)
def run_in_sandbox(
    name: str,
    kind: str = "train",
    config: dict[str, Any] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    try:
        return run(
            sandbox_name(name, shape=False),
            kind=kind,
            config=config,
            timeout_seconds=timeout_seconds,
        )
    except SandboxRejected as rejected:
        return {
            "ok": False,
            "error": "sandbox_rejected",
            "detail": str(rejected),
            "help": "Nothing was started. list_sandboxes says what is there.",
        }


#: What `deletable_without_asking` says when it says no. Sentences rather than
#: a boolean, because the answer is recorded on the turn and "the harness
#: refused to auto-approve" with no reason is the log saying nothing.
NOT_ITS_OWN = "this thread did not make that sandbox"
MADE_BEFORE_MAKERS_WERE_RECORDED = (
    "that sandbox was made before sandboxes recorded which thread made them, "
    "so nobody can say whose it is"
)
NO_SUCH_SANDBOX_TO_JUDGE = "there is no sandbox by that name to judge"
IT_HOLDS_AN_ADAPTER = (
    "it holds a trained adapter, which is hours of this machine's card and is "
    "what any score measured in it was measured ON"
)
IT_HOLDS_A_MEASUREMENT = (
    "this conversation has a completed eval run that was answered inside a "
    "sandbox, and a sandbox is not named in an eval row - so every sandbox of "
    "this thread is protected rather than the one that might be it"
)
ITS_OWN_AND_EMPTY_HANDED = (
    "this thread made it and nothing measured or trained lives in it"
)


def _holds_an_adapter(manifest: dict[str, Any]) -> bool:
    """Is there an `adapter_config.json` anywhere under this sandbox's runs?

    THE ONE ARTEFACT A SANDBOX HOLDS THAT NOTHING CAN GIVE BACK. `runs/` is
    made for every `run_in_sandbox`, so "the runs directory is not empty" would
    protect a box after one `ls` and cost this exception its meaning. An
    ADAPTER is different: it is the output of a training run that spent the
    card, and `find_the_adapter` in `app/tools/training.py` searches for
    exactly this file for exactly that reason.

    Bounded to `runs/*/` and `runs/*/adapter/`, which is where
    `recipes/hf-peft-lora/entrypoint.py` writes one - the same two places
    `find_the_adapter` looks. An unbounded walk of a sandbox holding a model
    checkpoint is not a check anybody wants in an approval decision.
    """
    runs = folder(manifest, "runs_dir", RUNS)
    try:
        entries = sorted(runs.iterdir())
    except OSError:
        return False
    for entry in entries:
        if not entry.is_dir():
            continue
        for inner in (entry, entry / "adapter"):
            try:
                if (inner / "adapter_config.json").is_file():
                    return True
            except OSError:
                continue
    return False


def _thread_measured_inside_a_sandbox(thread_id: Any) -> bool:
    """Has this conversation completed an eval run that was answered in a box?

    THE HONEST ADMISSION IN THIS WHOLE RULE. `eval_runs` records the thread,
    the eval file, the metric and the provider - and NOT the sandbox. A run
    answered in one is marked by `evals.SANDBOX_ARM_PREFIX` on its provider
    name and by nothing else, so from a row alone there is no way to say WHICH
    box it happened in.

    So this does not try. If the thread has any completed sandbox-arm run, all
    of that thread's sandboxes are protected, including ones that had nothing
    to do with it. The cost of being wrong that way is a question the person
    answers in a second; the cost of being wrong the other way is a measurement
    and the weights behind it, gone, with the number already quoted in the
    transcript. `a repair destroys the evidence it was needed` is the shorter
    version of why that asymmetry decides it.

    COMPLETED MEANS GRADED ROWS. A run row is written BEFORE any grading, so a
    row on its own is an intention; `evals.runs_in` counts the results.
    """
    if thread_id is None:
        return False
    try:
        from app.tools import evals

        rows = evals.runs_in(int(thread_id))
    except Exception:  # noqa: BLE001 - an approval never fails over its own check
        return True  # cannot tell -> protect. See the asymmetry above.
    for row in rows:
        name = str(row.get("provider_name") or "")
        if name.startswith(evals.SANDBOX_ARM_PREFIX) and int(row.get("graded") or 0) > 0:
            return True
    return False


def deletable_without_asking(
    name: Any, thread_id: Any, instance: str | None = None
) -> tuple[bool, str]:
    """May `full` delete this sandbox with no click? `(answer, why)`.

    Max's rule, and it is narrower than it sounds: under `full` a thread may
    throw away ITS OWN scratch box, because a run that made somewhere to try
    something and then cannot tidy it up is a run that asks the person to come
    and press a button about a directory they never heard of. Every other
    sandbox still asks - another thread's, one made before makers were
    recorded, and any box of this thread's that holds work somebody measured.

    Both halves are required and both are read off disk rather than believed:
    the manifest says who made it, and the sandbox itself says what is in it. A
    name that resolves to nothing is `False` - "cannot tell" is never "yes" for
    a delete.

    The reason string goes on the record either way, because an auto-approval
    nobody can read the reason for is the transcript saying a person agreed.
    """
    try:
        manifest = read_manifest(sandbox_name(name, shape=False), instance)
    except Exception:  # noqa: BLE001 - a bad name, a missing box, a torn file
        return False, NO_SUCH_SANDBOX_TO_JUDGE
    recorded = manifest.get("thread_id")
    if recorded is None:
        return False, MADE_BEFORE_MAKERS_WERE_RECORDED
    try:
        if int(recorded) != int(thread_id):
            return False, NOT_ITS_OWN
    except (TypeError, ValueError):
        return False, NOT_ITS_OWN
    if _holds_an_adapter(manifest):
        return False, IT_HOLDS_AN_ADAPTER
    if _thread_measured_inside_a_sandbox(thread_id):
        return False, IT_HOLDS_A_MEASUREMENT
    return True, ITS_OWN_AND_EMPTY_HANDED


@tool(
    "delete_sandbox",
    description=(
        "Delete one sandbox and everything inside it. Needs an approval, "
        "because it is irreversible. It removes only what is really inside "
        "that sandbox's own directory: a link out of it has the link removed "
        "and is never followed, so nothing outside goes with it."
    ),
    schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Which sandbox to delete, exactly as it is named. A value "
                    "that looks like a path is refused."
                ),
            }
        },
        "required": ["name"],
    },
    reads=("filesystem",),
    writes=("filesystem",),
    approval="always",
    provides=("sandbox.instance.delete",),
    label="Delete a sandbox",
    group="Train",
    verb="delete this sandbox and everything in it",
    order=56,
)
def delete_sandbox(name: str) -> dict[str, Any]:
    """Disposable means this is easy and it does not mean it is loose.

    `approval="always"`, for the reason `start_training` carries one: a person
    clicking Delete IS the approval and it costs them nothing, while a model
    that decided to tidy up gets a recorded "this needs an approval" in the
    transcript instead of a folder that is gone. The friction is on the caller
    who cannot consent, which is the only caller it should be on.

    THE DECLARATION IS UNCHANGED, 2026-09-18, and that is deliberate: this tool
    still needs an approval, and `full` is the only mode that can supply one
    without a click. What changed is that `full` may now supply it for a box
    this thread made and nothing measured lives in - see
    `deletable_without_asking` above for the two halves and
    `app/autonomy.py` for where the decision is taken. Every other caller,
    every other mode and every other sandbox meets exactly this docstring.
    """
    try:
        return destroy(name)
    except SandboxRejected as rejected:
        return {
            "ok": False,
            "error": "sandbox_rejected",
            "detail": str(rejected),
            "help": (
                "Nothing was deleted. A sandbox is named, never located: "
                "delete_sandbox takes the name list_sandboxes shows."
            ),
        }


# ---------------------------------------------------------------------------
# THE ENVIRONMENT PROGRAM. One step: a sandbox, its own interpreter, the
# packages in it, and an honest answer about the card.
#
# Max, 2026-09-18: *"what elements and tools and built frameworks do we provide
# for this training and working loop - create data framework program, sandbox
# program, environment training program etc"*. The data half of that sentence
# has had a program since `app/tools/datawork.py` shipped; the sandbox half had
# `make_sandbox`, which makes a DIRECTORY and reports what a RECIPE pinned. It
# has never been able to put anything in one.
#
# ## WHOSE ENVIRONMENT
#
# `pin()` above answers "what does this sandbox's recipe pin", and the venv it
# reads is the RECIPE's - one per recipe, `jobspec.venv_for`, built by
# `scripts/build_recipe_env.py` outside this product. That is the right answer
# for running a shipped recipe and it is no answer at all for "put these three
# packages somewhere I can try them", because a recipe's venv is shared by
# every sandbox that names that recipe and installing into it would change what
# a later run of a different sandbox gets.
#
# So this builds a virtualenv that belongs to the SANDBOX, at `<sandbox>/env`,
# and it is deleted when the sandbox is. A sandbox can therefore have two
# interpreters - the recipe's pin and its own - and the manifest says which is
# which rather than calling either one "the environment".
#
# ## uv, AND WHY IT IS ASKED FOR RATHER THAN ASSUMED
#
# `scripts/build_recipe_env.py::uv` is the one place in this repository that
# decides how a virtualenv is built, and it decides `shutil.which("uv")` first
# and `venv` + `pip` second, with its docstring recording the measurement that
# settles it. The same order is taken here rather than a second opinion, and
# the manifest records WHICH ran, because a uv venv has no `pip` in it and a
# person who later types `python -m pip` in there needs to know that before
# they meet the error.
#
# ## NOTHING HALF-BUILT IS REPORTED AS BUILT
#
# A package that will not install removes the sandbox - through `destroy`, the
# same guarded delete `create` uses when a snapshot fails - and the refusal
# names the package and the last twenty lines the installer printed. The
# alternative is a directory that lists, looks usable, and is missing the one
# library the work needs.


#: The sandbox's own virtualenv, beside `work/`, `data/`, `tmp/` and `runs/`.
ENV = "env"

#: Bounds on the two kinds of subprocess this section starts that are not a
#: recipe. Long enough for a real wheel download, short enough that a wedged
#: index does not hold the caller's turn open forever. Both go through
#: `runner._run_bounded`, which owns the process tree and kills it - see its
#: docstring for the measurement that proves the bound is real.
INSTALL_TIMEOUT_SECONDS = 15 * 60
PROBE_TIMEOUT_SECONDS = 180

#: How many lines of an installer's stderr a refusal carries. Twenty is where
#: pip puts the actual cause: "ERROR: Could not find a version that satisfies
#: the requirement ..." is the last line and the resolver's attempts are above
#: it, so a shorter tail keeps the complaint and loses what it was about.
STDERR_TAIL_LINES = 20


def installer() -> str | None:
    """`uv` if it is on PATH, else `None`. ONE DECISION, TAKEN WHERE IT ALREADY IS.

    `scripts/build_recipe_env.py::uv` is that decision and its docstring holds
    the measurement - the 86 MB that turned out to be a `du` artefact, the file
    counts that are real, the hardlinked cache. This asks the same question the
    same way, so that a machine which builds recipes with uv also builds
    sandboxes with uv and a machine without it gets pip in both places.
    """
    return shutil.which("uv")


def distribution_name(requirement: Any) -> str:
    """The distribution a requirement string names, or `""` when it cannot say.

    Needed for one thing only: asking the built environment what VERSION it
    ended up with, which is `importlib.metadata.version(name)` and therefore
    needs a name. Deliberately small, and deliberately honest about its limit -
    a requirement it cannot parse gets `""`, the version comes back `None`, and
    the manifest records that the version is unknown rather than a guess.

    A wheel PATH is parsed too, because it is a requirement both installers
    accept and the only way to install anything on a machine with no index. The
    name is the first field of the filename with underscores put back to
    hyphens, which is what PEP 427 puts there.
    """
    text = str(requirement or "").strip()
    if not text:
        return ""
    head = text.split(";", 1)[0].strip()  # drop an environment marker
    if head.lower().endswith(".whl"):
        stem = Path(head).name
        return stem.split("-", 1)[0].replace("_", "-")
    if head.lower().endswith((".tar.gz", ".zip")):
        return ""  # an sdist's filename is not reliably its distribution name
    for cut in ("[", "@", "=", "<", ">", "!", "~", " ", ","):
        head = head.split(cut, 1)[0]
    return head.strip()


#: Asked of the built environment, IN the built environment. `importlib.metadata`
#: rather than `pip list` for a reason that bites on this machine: a uv-built
#: virtualenv has no `pip` in it at all, so `python -m pip list` there is a
#: crash and not a listing. `importlib.metadata` is the standard library and it
#: reads the same `.dist-info` directories the installer has just written.
_VERSIONS_PROBE = (
    "import json, sys\n"
    "from importlib.metadata import version\n"
    "out = {}\n"
    "for name in sys.argv[1:]:\n"
    "    try:\n"
    "        out[name] = version(name)\n"
    "    except Exception:\n"
    "        out[name] = None\n"
    "print(json.dumps(out))\n"
)

#: THE GPU CHECK, RUN INSIDE THE SANDBOX'S OWN INTERPRETER. `torch.cuda` is the
#: question a training run actually asks, and it is a different question from
#: "is there a card in this box": a CPU-only wheel installs cleanly in front of
#: an NVIDIA card and reports False, which is exactly the failure
#: `scripts/build_recipe_env.py::verify` exists to catch. So this reports what
#: torch says when torch is there and falls back to the driver only when it is
#: not - never the other way round, because the driver cannot see the wheel.
_GPU_PROBE = (
    "import json\n"
    "try:\n"
    "    import torch\n"
    "except Exception as error:\n"
    "    print(json.dumps({'torch': False, 'why': type(error).__name__}))\n"
    "else:\n"
    "    try:\n"
    "        ok = bool(torch.cuda.is_available())\n"
    "    except Exception:\n"
    "        ok = False\n"
    "    name, vram = '', None\n"
    "    if ok:\n"
    "        try:\n"
    "            name = str(torch.cuda.get_device_name(0))\n"
    "            vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)\n"
    "        except Exception:\n"
    "            name, vram = '', None\n"
    "    print(json.dumps({'torch': True, 'available': ok, 'name': name,\n"
    "                      'vram_gb': vram, 'version': str(torch.__version__)}))\n"
)


def _last_json_object(text: Any) -> dict[str, Any] | None:
    """The last JSON object a probe printed, ignoring whatever else it said.

    A virtualenv's interpreter is entitled to print things before our line - a
    deprecation, a site customisation, a warning from an import - and
    `json.loads` over the whole of stdout would turn any of those into "the
    probe failed", which is a different answer from the one the probe gave.
    """
    for line in reversed(str(text or "").splitlines()):
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            body = json.loads(stripped)
        except ValueError:
            continue
        if isinstance(body, dict):
            return body
    return None


def _tail(text: Any, lines: int = STDERR_TAIL_LINES) -> list[str]:
    return [line for line in str(text or "").splitlines() if line.strip()][-lines:]


def _make_the_venv(
    directory: Path, python_hint: str
) -> tuple[Path | None, dict[str, Any]]:
    """Build `<sandbox>/env` and return its interpreter, or `(None, refusal)`.

    THE PYTHON HINT IS HONOURED OR SAID TO BE IGNORED, never quietly dropped.
    `uv venv --python 3.11` really does find or fetch that interpreter;
    `python -m venv` copies the interpreter it is running and has no such
    switch, so on a machine without uv the hint cannot be met - and the
    manifest then records the version that was actually built beside the one
    that was asked for.
    """
    env_dir = directory / ENV
    tool = installer()
    hint = str(python_hint or "").strip()
    if tool:
        argv = [tool, "venv"]
        if hint:
            argv += ["--python", hint]
        argv.append(str(env_dir))
        built_by = "uv"
    else:
        argv = [sys.executable, "-m", "venv", str(env_dir)]
        built_by = "venv+pip"
    try:
        done = runner._run_bounded(argv, INSTALL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return None, {
            "error": "environment_not_built",
            "detail": (
                "building the virtualenv did not finish inside "
                f"{INSTALL_TIMEOUT_SECONDS} seconds and its process tree was "
                "killed."
            ),
            "built_by": built_by,
            "stderr_tail": [],
        }
    except OSError as error:
        return None, {
            "error": "environment_not_built",
            "detail": f"{argv[0]} could not be started: {error}",
            "built_by": built_by,
            "stderr_tail": [],
        }
    if done.returncode != 0:
        return None, {
            "error": "environment_not_built",
            "detail": (
                f"{built_by} could not create a virtualenv at {env_dir} "
                f"(exit {done.returncode})."
                + (
                    f" The python hint {hint!r} is the likely cause: it is "
                    "passed to uv, which has to find or fetch that version."
                    if hint
                    else ""
                )
            ),
            "built_by": built_by,
            "stderr_tail": _tail(done.stderr) or _tail(done.stdout),
        }
    return _venv_python(env_dir), {"built_by": built_by}


def _install_into(interpreter: Path, packages: list[str]) -> dict[str, Any]:
    """Install every requirement in one call, and report what broke.

    ONE CALL AND NOT ONE PER PACKAGE, because a resolver that sees the whole set
    can refuse a combination no single install would - and a loop installing
    them one at a time would report the fifth as fine while leaving the
    environment in a state no requirement file describes.

    The cost is that a failing install names the SET, so the refusal has to work
    out which requirement the installer was complaining about. It does that the
    only way that is honest: it looks for a requirement's own text in what the
    installer printed, and when it finds none it names them all rather than
    picking one.
    """
    tool = installer()
    if tool:
        argv = [tool, "pip", "install", "--python", str(interpreter), *packages]
        by = "uv pip install"
    else:
        argv = [str(interpreter), "-m", "pip", "install", *packages]
        by = "pip install"
    try:
        done = runner._run_bounded(argv, INSTALL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "by": by,
            "named": list(packages),
            "detail": (
                f"{by} did not finish inside {INSTALL_TIMEOUT_SECONDS} seconds "
                "and its process tree was killed. Nothing here can tell a slow "
                "index from a wedged one."
            ),
            "stderr_tail": [],
        }
    except OSError as error:
        return {
            "ok": False,
            "by": by,
            "named": list(packages),
            "detail": f"{argv[0]} could not be started: {error}",
            "stderr_tail": [],
        }
    if done.returncode == 0:
        return {"ok": True, "by": by, "named": [], "detail": "", "stderr_tail": []}
    printed = str(done.stdout or "") + str(done.stderr or "")
    blamed = [one for one in packages if one and one in printed]
    return {
        "ok": False,
        "by": by,
        "named": blamed or list(packages),
        "detail": f"{by} exited {done.returncode}.",
        "stderr_tail": _tail(done.stderr) or _tail(done.stdout),
    }


def _versions_in(interpreter: Path, packages: list[str]) -> list[dict[str, Any]]:
    """What each requirement actually became, read out of the environment itself.

    A REQUIREMENT IS NOT A VERSION. `torch>=2.4` is a request and `2.6.0+cu124`
    is what is on the disk, and a manifest recording the first under the name of
    the second would be a record of what somebody asked for wearing the name of
    what they got.
    """
    names = [distribution_name(one) for one in packages]
    found: dict[str, Any] = {}
    wanted = sorted({name for name in names if name})
    if wanted:
        try:
            done = runner._run_bounded(
                [str(interpreter), "-c", _VERSIONS_PROBE, *wanted],
                PROBE_TIMEOUT_SECONDS,
            )
            found = _last_json_object(done.stdout) or {}
        except (subprocess.TimeoutExpired, OSError):
            found = {}
    rows: list[dict[str, Any]] = []
    for requirement, name in zip(packages, names):
        version = found.get(name) if name else None
        rows.append(
            {
                "requirement": str(requirement),
                "distribution": name,
                "version": version,
                "version_source": (
                    f"importlib.metadata.version({name!r}) in {interpreter}"
                    if version
                    else (
                        "unknown: this requirement does not name a distribution "
                        "that could be looked up"
                        if not name
                        else f"unknown: {name!r} has no importable metadata in "
                        "that environment, which is what happens when a "
                        "requirement installs under a different distribution name"
                    )
                ),
            }
        )
    return rows


def check_the_gpu(interpreter: Path | str) -> dict[str, Any]:
    """Is there a usable accelerator? Asked of this environment, never guessed.

    THREE ANSWERS, AND THEY ARE NOT THE SAME ANSWER:

    * **torch is here.** `torch.cuda.is_available()` is the question a training
      run asks, and it is the only one of the three that can see a CPU-only
      wheel sitting in front of a real card. Its `False` is a reading.
    * **torch is not here, the driver is.** `nvidia-smi` names the card and its
      memory. That is a fact about the box and not about this environment, and
      it is labelled as such.
    * **neither.** `checked_by` says *no check possible* and nothing is
      invented.

    `available` IS A BOOL IN ALL THREE CASES AND THIS PARAGRAPH IS WHY. It means
    *did a check observe a usable accelerator*, so an unchecked machine reads
    `False` - and `False` for "nobody looked" beside `False` for "torch looked
    and said no" is the collapse this product refuses everywhere else. It is a
    bool because callers branch on it and a three-valued field gets read as a
    bool by the first caller who forgets. What `available` cannot carry is
    carried by `checked` and `checked_by` beside it, and said in a sentence in
    `why`. Read them together or quote neither.
    """
    probe: dict[str, Any] | None = None
    try:
        done = runner._run_bounded(
            [str(interpreter), "-c", _GPU_PROBE], PROBE_TIMEOUT_SECONDS
        )
        probe = _last_json_object(done.stdout)
    except (subprocess.TimeoutExpired, OSError):
        probe = None

    if probe and probe.get("torch"):
        available = bool(probe.get("available"))
        vram = probe.get("vram_gb")
        return {
            "available": available,
            "checked": True,
            "name": (str(probe.get("name") or "") or None),
            "vram_gb": (
                round(float(vram), 2) if isinstance(vram, (int, float)) else None
            ),
            "checked_by": f"torch.cuda.is_available() in {interpreter}",
            "torch_version": str(probe.get("version") or ""),
            "why": (
                "torch is installed in this environment and reports CUDA "
                "available, so this is a reading of what a training run in here "
                "would get."
                if available
                else "torch is installed in this environment and reports CUDA "
                "NOT available. That is a reading and not an absence of one: a "
                "CPU-only wheel installs cleanly in front of a real card and "
                "answers exactly this way."
            ),
        }

    smi = None
    try:
        smi = runner._run_bounded(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            PROBE_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        smi = None

    if smi is not None and smi.returncode == 0:
        first = next(
            (line for line in str(smi.stdout or "").splitlines() if line.strip()), ""
        )
        card, _, memory = first.partition(",")
        try:
            vram_gb = round(float(memory.strip()) / 1024.0, 2)
        except ValueError:
            vram_gb = None
        if card.strip():
            return {
                "available": True,
                "checked": True,
                "name": card.strip(),
                "vram_gb": vram_gb,
                "checked_by": "nvidia-smi, run by the bounded runner",
                "torch_version": "",
                "why": (
                    "torch is not installed in this environment, so the driver "
                    "was asked instead. This says there is a card in this box; "
                    "it says nothing about whether a wheel in here could use it."
                ),
            }

    return {
        "available": False,
        "checked": False,
        "name": None,
        "vram_gb": None,
        "checked_by": "no check possible",
        "torch_version": "",
        "why": (
            "torch is not installed in this environment and nvidia-smi could "
            "not be run, so nothing looked. `available` is false because "
            "nothing OBSERVED an accelerator, which is not the same as one "
            "having been ruled out - install torch, or read the driver yourself."
        ),
    }


def _environment_digest(rows: list[dict[str, Any]]) -> str:
    """A digest over requirement-and-version pairs. NOT the sandbox fingerprint.

    `fingerprint()` above is over the recipe pin and the data snapshot, and it
    is deliberately left alone: it is compared between sandboxes by
    `tests/test_a_sandbox_is_reproducible.py` and by anything that stored one,
    and folding a new field into it would move every digest ever written. So
    what is installed AFTERWARDS gets its own, and the manifest says plainly
    that the sandbox fingerprint does not cover it.
    """
    parts = [
        {"requirement": row.get("requirement"), "version": row.get("version")}
        for row in rows
    ]
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _environment_sentence(
    name: str, environment: dict[str, Any], recipe: Any
) -> str:
    """One sentence, and every clause in it is something that was read."""
    packages = environment.get("packages") or []
    gpu = environment.get("gpu") or {}
    installed = [row for row in packages if row.get("version")]
    if environment.get("built"):
        got = ", ".join(
            f"{row['distribution'] or row['requirement']} {row['version']}"
            for row in installed
        ) or "nothing that reported a version"
        head = (
            f"Sandbox {name!r} has its own {environment.get('built_by')} "
            f"virtualenv at {environment.get('path')}, running python "
            f"{environment.get('python') or 'an unread version'}, holding {got}"
        )
    else:
        head = (
            f"Sandbox {name!r} was made with no packages asked for, so no "
            "virtualenv of its own was built and the interpreter reported is "
            f"{environment.get('interpreter_is')}"
        )
    if gpu.get("checked"):
        vram = gpu.get("vram_gb")
        gpu_clause = (
            f"the GPU check ({gpu.get('checked_by')}) found "
            f"{gpu.get('name') or 'an unnamed device'}"
            + (f" with {vram} GB" if vram else "")
            if gpu.get("available")
            else f"the GPU check ({gpu.get('checked_by')}) found no usable "
            "accelerator"
        )
    else:
        gpu_clause = (
            f"no GPU check was made ({gpu.get('checked_by')}), so nothing is "
            "claimed about the card"
        )
    pinned = f", it pins the {recipe} recipe" if recipe else ", it pins no recipe"
    return f"{head}{pinned}, and {gpu_clause}."


@tool(
    "build_environment",
    description=(
        "Make a sandbox and BUILD the environment inside it, in one step: its "
        "own virtualenv, the packages you name installed into that virtualenv "
        "with their real versions recorded, and a GPU check run inside it. Use "
        "this instead of make_sandbox when the work needs libraries. A package "
        "that will not install removes the sandbox, and the refusal names the "
        "package and what the installer printed - nothing half-built is "
        "reported as built. The GPU answer is torch's when torch is there, the "
        "driver's when it is not, and 'no check possible' when neither: never a "
        "guess. Needs an approval, because it starts processes on this machine."
    ),
    schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "What to call the sandbox. It must not already exist - "
                    "nothing here writes over one. list_sandboxes says which "
                    "names are taken."
                ),
            },
            "recipe": {
                "type": "string",
                "description": (
                    "A pinned training recipe for this sandbox to name, one of "
                    "the names list_recipes returns. Optional. It pins what "
                    "run_in_sandbox would run; it is not where the packages "
                    "below go."
                ),
            },
            "packages": {
                "type": "array",
                "description": (
                    "pip requirement strings - 'torch', 'peft==0.13.2', or the "
                    "path to a wheel. They are installed into this sandbox's "
                    "own virtualenv and never into a recipe's."
                ),
                "items": {"type": "string"},
            },
            "python": {
                "type": "string",
                "description": (
                    "Which Python to build the virtualenv on, as a version - "
                    "'3.11'. Honoured when uv is on PATH; without uv this "
                    "harness's own interpreter is copied and the reply says the "
                    "hint could not be met."
                ),
            },
            "gpu_check": {
                "type": "boolean",
                "description": (
                    "Run the GPU check inside the built environment. On by "
                    "default."
                ),
            },
        },
        "required": ["name"],
    },
    reads=("recipes", "filesystem"),
    writes=("filesystem",),
    approval="always",
    provides=("sandbox.environment.build",),
    label="Build an environment",
    group="Train",
    verb="make a sandbox and install these packages in it",
    order=53,
)
def build_environment(
    name: str,
    recipe: str | None = None,
    packages: Any = None,
    python: str = "",
    gpu_check: bool = True,
    *,
    instrument: Instrument | None = None,
) -> dict[str, Any]:
    """The one door. Every refusal names what would have worked.

    Ordered so the cheap refusals happen first: the sandbox is made before
    anything is built, because `create` already refuses a name that is taken
    and a recipe that does not exist. Anything that fails after that takes the
    sandbox with it - see `give_up`.
    """
    requirements = [
        str(one).strip() for one in (packages or []) if str(one or "").strip()
    ]
    try:
        made = create(
            name,
            project_id=_project_of(instrument),
            purpose="an environment built by build_environment",
            recipe=recipe or None,
        )
    except SandboxRejected as rejected:
        return {
            "ok": False,
            "error": "sandbox_rejected",
            "detail": str(rejected),
            "help": (
                "Nothing was made and nothing was left behind. list_sandboxes "
                "says which names are taken; list_recipes says which recipes "
                "can pin an environment on this machine."
            ),
        }

    chosen = str(made["name"])
    directory = Path(str(made["path"]))
    manifest = read_manifest(chosen)
    pinned = manifest.get("pin") or {}

    def give_up(payload: dict[str, Any]) -> dict[str, Any]:
        """Remove the half-built sandbox, then return the refusal.

        Through `destroy`, the guarded delete that refuses to follow a link out
        of the directory. `create` does the same thing when a snapshot fails,
        and for the same reason its comment gives: a half-made sandbox lists,
        looks usable, and is not what it says it is. A second, less careful
        remove written here would make the cleanup path the dangerous one.
        """
        try:
            destroy(chosen)
            removed = True
        except (SandboxRejected, OSError):
            removed = False
        payload["ok"] = False
        payload["sandbox"] = chosen
        payload["sandbox_removed"] = removed
        payload["help"] = (
            f"The sandbox was removed, so the name {chosen!r} is free again."
            if removed
            else f"The sandbox at {directory} could NOT be removed and is "
            "half-built: it will list, and its environment is not the one that "
            "was asked for. delete_sandbox takes it away."
        )
        return payload

    environment: dict[str, Any] = {
        "built": False,
        "path": "",
        "python_hint": str(python or "").strip(),
        "asked_for": list(requirements),
        "packages": [],
    }

    if requirements:
        interpreter, outcome = _make_the_venv(directory, python)
        if interpreter is None:
            return give_up(outcome)
        if not interpreter.is_file():
            return give_up(
                {
                    "error": "environment_not_built",
                    "detail": (
                        f"{outcome['built_by']} reported success and there is "
                        f"no interpreter at {interpreter}."
                    ),
                    "built_by": outcome["built_by"],
                    "stderr_tail": [],
                }
            )
        installed = _install_into(interpreter, requirements)
        if not installed["ok"]:
            return give_up(
                {
                    "error": "install_failed",
                    "packages": installed["named"],
                    "detail": (
                        "These requirements did not install, so this "
                        "environment does not exist: "
                        + ", ".join(repr(one) for one in installed["named"])
                        + ". "
                        + installed["detail"]
                    ),
                    "installer": installed["by"],
                    "stderr_tail": installed["stderr_tail"],
                }
            )
        version, version_source = _venv_version(directory / ENV)
        rows = _versions_in(interpreter, requirements)
        environment.update(
            built=True,
            path=str(directory / ENV),
            interpreter=str(interpreter),
            interpreter_is="this sandbox's own virtualenv, built by this call",
            built_by=outcome["built_by"],
            installer=installed["by"],
            python=version,
            python_source=version_source,
            packages=rows,
            digest=_environment_digest(rows),
        )
        if environment["python_hint"] and outcome["built_by"] != "uv":
            environment["python_hint_note"] = (
                f"{environment['python_hint']!r} was asked for and could not be "
                "met: uv is not on PATH and `python -m venv` copies the "
                "interpreter it is running. The version recorded above is what "
                "was actually built."
            )
    else:
        environment.update(
            interpreter=str(pinned.get("interpreter") or sys.executable),
            interpreter_is=str(
                pinned.get("interpreter_is") or "this harness's own interpreter"
            ),
            built_by="not built - no packages were asked for",
            installer="",
            python=str(pinned.get("python") or ""),
            python_source=str(pinned.get("python_source") or ""),
            digest=_environment_digest([]),
            note=(
                "No packages were named, so no virtualenv of this sandbox's own "
                "was built. The interpreter reported is the one run_in_sandbox "
                "would use: the recipe's pin when there is one, and this "
                "harness's own otherwise."
            ),
        )

    if gpu_check:
        environment["gpu"] = check_the_gpu(environment["interpreter"])
    else:
        environment["gpu"] = {
            "available": False,
            "checked": False,
            "name": None,
            "vram_gb": None,
            "checked_by": "not asked for",
            "torch_version": "",
            "why": (
                "gpu_check was false, so no check ran. `available` is false "
                "because nothing looked, which is not a statement about the box."
            ),
        }
    environment["fingerprint_note"] = (
        "The sandbox fingerprint is over the recipe pin and the data snapshot, "
        "and it does NOT cover what was installed here. `environment.digest` is "
        "the digest of the requirement-and-version pairs above."
    )

    manifest["environment"] = environment
    _write_manifest(directory, manifest)

    return {
        "ok": True,
        "sandbox": chosen,
        "says": _environment_sentence(chosen, environment, pinned.get("recipe")),
        "environment": environment,
        "manifest": manifest,
        "reach": reach(
            bool(manifest.get("egress")), str(manifest.get("egress_reason") or "")
        ),
    }
