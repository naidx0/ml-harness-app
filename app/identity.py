"""What this engine IS, in a form a caller can CHECK rather than assume.

`engine.json` used to carry `base_url`, `host`, `pid`, `port` and `token`.
Every one of those says *where to send a request*. Not one of them says *what
is going to answer it*, and that gap is the single cause of five separate
failures on one evening:

1. The file published `pid: 24636`. The process actually listening on 8078 was
   `23220`, so `taskkill` on the published pid killed something that was not
   the server, and the launcher then believed it had cleared the port.
2. The replacement engine died with `[Errno 10048] only one usage of each
   socket address` - into a log file nobody read.
3. `GET /health` answered `{"status": "ok"}` from the STALE engine still
   holding the port. The check passed. It was checking that *something* was
   listening, which was never in doubt.
4. The stale engine was older code, so `GET /local_specs` returned
   `gpu_name: null` and the interface said "I couldn't find a graphics card"
   on a machine with an idle RTX 2060 SUPER.
5. The bearer token is minted per process, so a browser tab left open across a
   restart starts 401ing with no explanation.

Every one of those is answered by the same thing: **an identity that travels
over the socket.** A pid is a claim about the operating system that the file
cannot substantiate and the reader cannot check. A nonce that the engine mints
for itself, writes into `engine.json`, and echoes back from `/health` is
checkable by anyone with a socket - and that is exactly the population that
cares, because the socket is the thing they are about to talk to.

## The four things published, and why each one earns its place

**`ENGINE_ID`** - 128 bits, minted once per process. This is the only field
here that *cannot* be wrong: it is not a reading of anything external, it is a
value this process invented and will repeat until it dies. Its whole job is to
let a reader join two facts - "the file says engine X" and "the socket says
engine X" - into one. Where those disagree, the file is stale and the socket is
right, and a reader can now find that out instead of guessing.

**`code_fingerprint()`** - a sha256 over every file under `app/`, content
addressed. This is the field that answers "is this engine running my current
code?", and it answers it better than a git sha can, because the question
during development is almost never about commits. A tree with an uncommitted
edit has the same sha as the tree without it; it does not have the same
fingerprint. See `code_fingerprint` for exactly what it does and does not
cover - the list is short and the gaps are real.

**`git_head()` / `git_dirty()`** - the sha and the dirty flag, because a
fingerprint is 64 characters of hex that nobody can read out loud, and "you are
on `e2b6ff1`, clean" is the sentence a person actually wants when they are
deciding whether the thing in front of them is the thing they just wrote. The
sha is read out of `.git` directly, no subprocess. The dirty flag needs `git`
and says `None` when it cannot have it, because `False` there would be a claim
we did not check.

**`known_schema_version()`** - the highest migration this build ships. Not
hypothetical: a build that knew schema 8 met a database at 9 and answered every
request with a 500. The database's *actual* version is a separate reading and
belongs to `/health`, because it is a property of the database and can change
while this process is alive; this one is a property of the build and cannot.

## What is deliberately NOT here

**The token.** It is published to `engine.json`, which is written user-only,
and it is never part of an identity payload that a route hands out. `/health`
requires no token by design - a client that cannot yet authenticate still has
to be able to find out whether it is talking to the right engine - so anything
placed in this module is, in effect, public to every process on the machine.

**Anything computed at import.** Both expensive readings here are lazy and
cached. The suite runs in one process and pays each of them once; an engine
pays them at startup because `write_portfile` asks for them there. Doing the
work at import would charge every `from app import security` in the repository
for a reading most of them never look at.
"""

from __future__ import annotations

import hashlib
import os
import platform
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

#: The directory whose contents make up "the code this engine is running".
#: `app/` and nothing else - see `code_fingerprint` for what that leaves out.
#:
#: THE PACKAGE ITSELF, NOT `parents[1] / "app"`, and the difference is Phase V
#: step A4. The old form worked in a wheel only by coincidence: `parents[1]` of
#: an installed `app/identity.py` happens to be `site-packages`, and
#: `site-packages/app` happens to be this package. It would have gone wrong the
#: first time this package was vendored under any other directory, and it would
#: have gone wrong silently - a fingerprint over a directory that is not the
#: code being run reports "same code" across every change. `__file__.parent` is
#: the package under every layout there is.
CODE_ROOT = Path(__file__).resolve().parent

#: Names a `/health` response and a portfile both carry, so a reader can tell
#: our engine from any other HTTP server that happens to hold the port. The
#: launcher refuses to kill a process that does not say this.
SERVICE = "ml-harness-engine"

#: Bumped when the SHAPE of `engine.json` changes in a way a reader must know
#: about. Version 1 was `{base_url, host, pid, port, token}` - no identity at
#: all. A reader that finds a version it does not know should say so rather
#: than index into fields that may not be there.
PORTFILE_VERSION = 2

#: This process, named by itself. Minted at import so that every reading of it
#: within one process is the same value, including the one `write_portfile`
#: publishes and the one `/health` echoes. That equality is the whole point:
#: it is what turns "the file and the socket agree" into a checkable sentence.
ENGINE_ID = secrets.token_hex(16)

#: A value chosen by WHOEVER STARTED THIS PROCESS, echoed back so they can
#: recognise their own child over the socket. `None` when nobody set it.
#:
#: THIS EXISTS BECAUSE A PID DOES NOT SURVIVE THE TRIP. `scripts/launch.py`
#: originally verified readiness by asking "is the process answering on this
#: port the pid I just started". It failed on the first run, on the machine
#: this product is built on, because `subprocess.Popen(...).pid` is the pid of
#: the venv's `python.exe` and the interpreter that actually ends up running
#: the code is a DIFFERENT process - measured here as Popen.pid 12468 against a
#: server that logged `Started server process [25392]`. That is the same shape
#: as the failure this whole module is a response to (`engine.json` claiming
#: 24636 while 23220 held the port), arriving from a different direction: a pid
#: is a fact about a process table that the two ends of a socket do not share.
#:
#: A nonce does survive. The launcher invents one, hands it to the child in the
#: environment, and asks `/health` whether it matches. No number of re-exec
#: layers, shims or pid recycles can break that, because the value is carried
#: by the thing being identified rather than inferred about it.
#:
#: NOT A SECRET AND NOT A CREDENTIAL. It is published in an unauthenticated
#: `/health` response on purpose - the whole point is that a caller can check
#: it before it has a token. Nothing may ever authorise anything on the
#: strength of it; the bearer token in `app/security.py` is what does that.
LAUNCH_NONCE = os.environ.get("MLH_LAUNCH_NONCE") or None

#: When this process started, near enough. Import time rather than a
#: `psutil`-style process-creation time, and the difference is documented
#: rather than hidden: it is later than the real fork by however long the
#: interpreter took to get here. Nothing depends on it being exact; it exists
#: so a person reading `engine.json` can tell a five-second-old engine from one
#: that has been up since Tuesday.
STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")

#: The reference `uptime_seconds()` actually measures against. `STARTED_AT` is
#: rounded to the second for readability, and subtracting a rounded timestamp
#: from an unrounded clock gives an uptime that can read 1.0 seconds on a
#: process a tenth of a second old. A monotonic reading cannot go backwards
#: when the system clock is adjusted either, which a wall-clock difference can.
_STARTED_MONOTONIC = time.monotonic()

#: Directory and file names that are not source and must not move the
#: fingerprint. `__pycache__` is derived from the very files we are hashing, so
#: including it would make the fingerprint depend on whether the engine had
#: been run yet.
#:
#: `_bundled` IS THE OTHER KIND OF NOT-SOURCE. `setup.py`'s build step copies
#: `docs/diagnosis_engine.yaml` and `docs/ledgers/*.yaml` into `app/_bundled/`
#: so an installed engine can load them, and `code_fingerprint`'s own docstring
#: already says the ledgers are OUTSIDE this fingerprint. Hashing a generated
#: copy of a file this deliberately excludes would be incoherent in both
#: directions: in a checkout the engine reads `docs/` and never the bundle, so a
#: developer who built a wheel once would carry a fingerprint that moves on a
#: file nothing reads; in an install it would smuggle the ledger back in through
#: a side door the docstring says is closed.
_IGNORED_DIRECTORIES = frozenset(
    {"__pycache__", ".pytest_cache", ".mypy_cache", "_bundled"}
)
_IGNORED_SUFFIXES = (".pyc", ".pyo")

_FINGERPRINT: tuple[str, int] | None = None
_GIT_HEAD: tuple[str | None, str] | None = None

#: WHEN the sha above was read, ISO-8601 UTC, or "" before anything asked.
#:
#: The reading is frozen at the first call on purpose, and the freeze is the
#: correct behaviour rather than a cache to be invalidated: this process
#: executes the modules it imported at startup, so the sha that describes it is
#: the one that was HEAD then, not the one that is HEAD now. A re-read would
#: make a long-lived engine claim to be code it is not running.
#:
#: What was missing is that nothing SAID so. `sha_source` reports "git-ref",
#: which says how the answer was obtained and never when, and on 2026-09-05 a
#: gate reported a failure because a reader compared it against a live
#: `git rev-parse` across a commit and read the disagreement as a caching bug
#: in this module. Both numbers were right. The published identity now carries
#: the reading's timestamp beside it so the question can be settled by looking.
_GIT_HEAD_READ_AT: str = ""
_GIT_DIRTY: tuple[bool | None, str] | None = None


def uptime_seconds() -> float:
    """How long this process has been up, to a tenth of a second."""
    return round(time.monotonic() - _STARTED_MONOTONIC, 1)


# ---------------------------------------------------------------------------
# The code this process is running.


def _source_files(root: Path) -> list[Path]:
    """Every file under `root` that is source, sorted, ignoring build residue."""
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _IGNORED_DIRECTORIES for part in path.parts):
            continue
        if path.suffix in _IGNORED_SUFFIXES:
            continue
        found.append(path)
    return found


def code_fingerprint(root: Path | None = None) -> tuple[str, int]:
    """`(sha256, file_count)` over every file under `app/`. Cached per process.

    **What this is for.** "Is the engine on 8078 running my current code?" A
    git sha cannot answer that during development, because the answer is
    usually about an edit that has not been committed - and the sha of a tree
    with an uncommitted change is the sha of the tree without it. Content
    addressing does answer it: two engines report the same fingerprint if and
    only if every byte of `app/` was identical when each of them read it.

    **Why the whole directory and not just `*.py`.** `app/instructions/*.md`
    is the model's system prompt, assembled at runtime by `app/instructions`.
    `app/model_configs/*.json` is the geometry every VRAM estimate is computed
    from. Neither is Python and a change to either changes what the product
    says. A fingerprint that covered only the `.py` files would report "same
    code" across a rewritten prime directive, which is precisely the class of
    silent staleness this exists to catch.

    **What it does NOT catch, stated because a fingerprint that is trusted for
    more than it covers is worse than none:**

    - *Anything outside `app/`.* `docs/diagnosis_engine.yaml`, `recipes/`,
      `scripts/`, and the entire `frontend/` build are invisible here. The UI
      dev server has its own staleness story and Vite owns it.
    - *Installed dependencies.* A different FastAPI, a different `nvidia-smi`
      on `PATH`, a different Python - `build()` publishes the interpreter
      version separately for that reason, and it is not folded into this hash
      because a version string is a claim about the environment rather than
      about our source.
    - *An edit made after this reading.* The value is cached the first time it
      is asked for, which for an engine is startup. That is deliberate and it
      is the correct semantics: the question is "what code is this process
      RUNNING", and a process does not pick up an edit to a module it has
      already imported. It is also the one honest gap - a module imported
      LAZILY, after this reading, comes off disk in its edited form while the
      fingerprint still describes the tree as it was at startup. Nothing in
      this repository imports product code lazily on a request path today; if
      something does, this sentence is the reason it needs to stop.
    """
    global _FINGERPRINT
    if root is None and _FINGERPRINT is not None:
        return _FINGERPRINT

    target = CODE_ROOT if root is None else Path(root)
    digest = hashlib.sha256()
    count = 0
    for path in _source_files(target):
        relative = path.relative_to(target).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\n")
        count += 1
    result = (digest.hexdigest(), count)
    if root is None:
        _FINGERPRINT = result
    return result


# ---------------------------------------------------------------------------
# Git, read two ways, for two different reasons.


def _git_dir(root: Path) -> Path | None:
    """The `.git` directory for `root`, following a worktree's pointer file.

    A checkout made with `git worktree add` has a `.git` FILE reading
    `gitdir: <path>`, not a directory, and this repository has worktrees under
    `.claude/worktrees/`. Following the pointer is what stops the sha coming
    back `None` for an agent working in one.
    """
    dot = root / ".git"
    if dot.is_dir():
        return dot
    if dot.is_file():
        try:
            text = dot.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if text.startswith("gitdir:"):
            pointer = Path(text.split(":", 1)[1].strip())
            resolved = pointer if pointer.is_absolute() else (root / pointer)
            try:
                return resolved.resolve()
            except OSError:
                return None
    return None


def _resolve_ref(git_dir: Path, ref: str) -> str | None:
    """A ref to its sha, looking in the loose file, then `packed-refs`.

    Both, because a freshly cloned repository keeps almost every ref packed and
    a working one keeps the branch it is on loose. Checking only the first is
    how a sha reader comes back empty on a clone and works on the author's
    machine.

    `commondir` is consulted for worktrees: a worktree's own git directory
    holds its `HEAD`, and the refs it names live in the main checkout.
    """
    candidates = [git_dir]
    common = git_dir / "commondir"
    if common.is_file():
        try:
            pointer = Path(common.read_text(encoding="utf-8").strip())
        except OSError:
            pointer = None
        if pointer is not None:
            candidates.append(
                pointer if pointer.is_absolute() else (git_dir / pointer)
            )
    for base in candidates:
        loose = base / ref
        if loose.is_file():
            try:
                value = loose.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if value:
                return value
        packed = base / "packed-refs"
        if packed.is_file():
            try:
                lines = packed.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                if not line or line.startswith(("#", "^")):
                    continue
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0]
    return None


def git_head(root: Path | None = None) -> tuple[str | None, str]:
    """`(sha, source)` for `HEAD`, read out of `.git`. No subprocess.

    Read rather than shelled out for two reasons and one of them is not
    performance. `git rev-parse HEAD` is a process spawn on the engine's
    startup path, and on a machine with no `git` on `PATH` - which is a
    perfectly ordinary way to receive a zip of this repository - it produces a
    failure that has to be distinguished from "not a repository". Reading two
    small text files cannot fail that way.

    `source` names how the answer was obtained, so a caller can tell "there is
    no repository here" from "the sha is unknown". A field that says `null`
    with no reason invites the reader to invent one.

    **THE ANSWER IS FROZEN AT THE FIRST CALL, AND THAT IS THE POINT, NOT A
    CACHE TO BE INVALIDATED.** This process runs the modules it imported at
    startup. If HEAD moves afterwards - a lane commits, somebody checks out a
    branch - the code in memory does not move with it, so the sha that
    describes this engine is the one that was HEAD when it started. Re-reading
    would make a long-lived engine report a commit whose code it is not
    running, which is the failure this whole module exists to prevent.

    Passing an explicit `root` bypasses the freeze and reads live, because a
    caller asking about a particular directory is asking about that directory
    and not about this process.

    `identity.build()` publishes `sha_read_at` beside the sha so the freeze is
    visible rather than inferred - see `_GIT_HEAD_READ_AT`.
    """
    global _GIT_HEAD, _GIT_HEAD_READ_AT
    if root is None and _GIT_HEAD is not None:
        return _GIT_HEAD

    target = REPO_ROOT if root is None else Path(root)
    git_dir = _git_dir(target)
    if git_dir is None:
        result: tuple[str | None, str] = (None, "not-a-git-checkout")
    else:
        head_file = git_dir / "HEAD"
        try:
            head = head_file.read_text(encoding="utf-8").strip()
        except OSError:
            head = ""
        if not head:
            result = (None, "git-head-unreadable")
        elif head.startswith("ref:"):
            ref = head.split(":", 1)[1].strip()
            sha = _resolve_ref(git_dir, ref)
            result = (
                (sha, "git-ref") if sha else (None, f"git-ref-unresolved:{ref}")
            )
        else:
            # Detached HEAD holds the sha itself. An agent lane checked out at
            # a commit is in exactly this state, so it is not an edge case here.
            result = (head, "git-head-detached")
    if root is None:
        _GIT_HEAD = result
        _GIT_HEAD_READ_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return result


def git_dirty(root: Path | None = None) -> tuple[bool | None, str]:
    """`(dirty, source)` - does the working tree differ from `HEAD`?

    `None` when we could not find out, never `False`. `False` is a statement
    that the tree is clean, and a statement we did not check is the shape of
    defect this whole module exists to remove.

    This one DOES spawn a process, because there is no honest way to compute it
    from the files in `.git` alone - the answer depends on the content of every
    tracked file in the tree and on the index's stat cache. Three things keep it
    from being an invariant-1 problem or a startup cost:

    - The argv is fixed. No shell, no interpolation, nothing from a request
      body reaches it. Invariant 1 forbids `shell=True` and free-text commands;
      this is neither.
    - `--no-optional-locks` is load-bearing rather than tidy: a plain `git
      status` REFRESHES THE INDEX, which is a write into the user's repository
      performed by a process that was only asked a question. With the flag,
      git declines to take the index lock and answers read-only.
    - It is cached per process and lazy, and measured at 44 ms on this
      repository - which lives inside a OneDrive folder, so that is close to a
      worst case rather than a best one.

    **What the pair (sha, dirty) does not catch, and the reason
    `code_fingerprint` exists beside it:** a dirty tree is dirty, and that is
    all it says. Two engines can both report `e2b6ff1` dirty and be running
    completely different code, because "dirty" does not describe WHICH edit.
    An uncommitted change to a file the engine has already imported is
    invisible to the sha and indistinguishable, via the dirty flag, from any
    other uncommitted change. So the sha and the flag are for a human to read
    and the fingerprint is for a program to compare, and nothing decides
    anything on the flag alone.
    """
    global _GIT_DIRTY
    if root is None and _GIT_DIRTY is not None:
        return _GIT_DIRTY

    target = REPO_ROOT if root is None else Path(root)
    if _git_dir(target) is None:
        result: tuple[bool | None, str] = (None, "not-a-git-checkout")
    else:
        try:
            completed = subprocess.run(
                [
                    "git",
                    "--no-optional-locks",
                    "status",
                    "--porcelain",
                    "--untracked-files=no",
                ],
                cwd=str(target),
                capture_output=True,
                text=True,
                timeout=20,
                shell=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            result = (None, f"git-unavailable:{type(error).__name__}")
        else:
            if completed.returncode != 0:
                result = (None, f"git-failed:{completed.returncode}")
            else:
                result = (bool(completed.stdout.strip()), "git-status")
    if root is None:
        _GIT_DIRTY = result
    return result


# ---------------------------------------------------------------------------
# The schema this build ships.


def known_schema_version() -> int:
    """The highest migration in `app/migrations`. A property of the BUILD.

    Not of the database. The database's version is read from `schema_version`
    and can move under a running process; this number cannot change while this
    process is alive, which is what makes it part of an identity rather than a
    reading. `/health` publishes both and says whether they agree, because the
    interesting event is the disagreement: an engine that knew 8 met a database
    at 9 and answered every request with a 500, and nothing in the file it
    published would have let anybody see that coming.

    Imported inside the function: `app.migrations` imports every migration
    module, and this module is imported by `app.security`, which is imported
    early enough that a module-level import here would reorder the package.
    """
    from app import migrations

    return migrations.MIGRATIONS[-1][0] if migrations.MIGRATIONS else 0


# ---------------------------------------------------------------------------
# The published shape.


def build() -> dict[str, Any]:
    """The build half of the identity: what code, from where, on what runtime."""
    fingerprint, files = code_fingerprint()
    sha, sha_source = git_head()
    dirty, dirty_source = git_dirty()
    return {
        "sha": sha,
        "sha_source": sha_source,
        # WHEN the sha was read, which `sha_source` never said. Frozen at
        # process start on purpose, and a consumer comparing it against a live
        # `git rev-parse` needs to know that before calling the disagreement a
        # defect - one did, and reported a green tree red.
        "sha_read_at": _GIT_HEAD_READ_AT,
        "dirty": dirty,
        "dirty_source": dirty_source,
        "code_fingerprint": fingerprint,
        "code_files": files,
        "python": platform.python_version(),
        "executable": sys.executable,
    }


def engine() -> dict[str, Any]:
    """The process half: who is answering, since when."""
    return {
        "engine_id": ENGINE_ID,
        "pid": os.getpid(),
        "launch_nonce": LAUNCH_NONCE,
        "started_at": STARTED_AT,
        "uptime_seconds": uptime_seconds(),
    }


def identity() -> dict[str, Any]:
    """Everything `engine.json` and `/health` both carry, computed once here.

    One function so the two cannot drift. A portfile that described a slightly
    different build from the one the socket reports would reintroduce exactly
    the ambiguity this module removes, and "they are both built from
    `identity()`" is a property a test can assert.
    """
    return {
        "service": SERVICE,
        "portfile_version": PORTFILE_VERSION,
        "engine": engine(),
        "build": build(),
        "schema": {"build_knows": known_schema_version()},
    }


def reset_caches_for_tests() -> None:
    """Drop the cached readings so a test can exercise the reading itself."""
    global _FINGERPRINT, _GIT_HEAD, _GIT_DIRTY, _GIT_HEAD_READ_AT
    _FINGERPRINT = None
    _GIT_HEAD = None
    _GIT_DIRTY = None
    #: Cleared with the reading it timestamps. A reading time left behind by
    #: the previous reading would say the new sha was read before it existed.
    _GIT_HEAD_READ_AT = ""
