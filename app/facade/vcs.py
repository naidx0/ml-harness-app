"""Their review panel, over the git CLI in the project's folder.

Their review panel (`vendor/opencode/packages/app/src/session/review/model.ts`)
offers "git" when the session's project has `vcs`, and "branch" when
`vcs.get` names a current branch that is not the default one. It then reads
`vcs.diff` with `mode` `working` (for "git") or `branch`, and re-reads when a
`filesystem.changed` event arrives. The file tree's status badges read
`vcs.status`; the branch picker reads `vcs.branch.list`.

EVERYTHING HERE IS THE git CLI, RUN IN THE PROJECT'S FOLDER - no shell, a
timeout on every call, output read as bytes and decoded here (`files._git`).
The folder is confined exactly as the file tree's is (`files.base_for`), so
the review panel cannot be pointed at a repository that is no project. In a
folder that is inside a larger repository, paths are relative to the folder
(`--relative`, pathspec `.`) and changes elsewhere in the repository are not
this project's.

## What a diff holds

* **working**: the work tree against `HEAD` (against the empty tree before the
  first commit), plus every untracked file not ignored, each diffed against
  nothing with `git diff --no-index`.
* **branch**: the work tree against the merge base of `HEAD` and the base
  branch - everything this branch changes, committed or not - plus untracked.
* **committed**: `HEAD` against that merge base; commits only.

Binary files are left out of a diff (they are still in `vcs.status`), and so
is a file whose patch is longer than `MAX_PATCH_CHARS`; at most `MAX_FILES`
files are diffed.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from app.facade import files

#: git's well-known id for the empty tree: what `HEAD` is before a first commit.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
MAX_FILES = 300
MAX_PATCH_CHARS = 1_000_000
DEFAULT_CONTEXT = 3
MAX_CONTEXT = 100_000
DEFAULT_BRANCHES = 100
MAX_BRANCHES = 500
#: Untracked files larger than this are listed in status and not diffed.
MAX_UNTRACKED_BYTES = 2 * 1024 * 1024
NUL = chr(0)


class Unavailable(Exception):
    """git is not installed, or did not answer."""


def have_git() -> bool:
    return shutil.which("git") is not None


def _run(cwd: Path, *args: str, ok: tuple[int, ...] = (0,)) -> str | None:
    done = files._git(cwd, "-c", "core.quotepath=false", *args)
    if done is None or done.returncode not in ok:
        return None
    return done.stdout


#: How long "is this folder a repository" is remembered. `project.list` asks
#: it of every project, two git processes each, and their client reads that
#: list often; a folder becomes a repository rarely.
REPO_TTL_SECONDS = 5.0
_REPO_CACHE: dict[str, tuple[float, bool]] = {}


def is_repo(directory: Path) -> bool:
    """A git work tree that tracks this folder.

    A folder git IGNORES is inside a work tree without being part of it - a
    default workspace under a checkout's gitignored `workspaces/` is one - and
    its changes are nobody's commits, so it is not offered as a repository.
    """
    key = str(directory)
    now = time.monotonic()
    remembered = _REPO_CACHE.get(key)
    if remembered is not None and now - remembered[0] < REPO_TTL_SECONDS:
        return remembered[1]
    answer = False
    if have_git() and files.in_work_tree(directory):
        ignored = files._git(directory, "check-ignore", "-q", ".")
        answer = not (ignored is not None and ignored.returncode == 0)
    _REPO_CACHE[key] = (now, answer)
    return answer


def current_branch(cwd: Path) -> str | None:
    out = _run(cwd, "symbolic-ref", "--short", "-q", "HEAD")
    return out.strip() or None if out is not None else None


def local_branches(cwd: Path) -> list[str]:
    out = _run(cwd, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return [line.strip() for line in (out or "").splitlines() if line.strip()]


def default_branch(cwd: Path) -> str | None:
    """The remote's default branch, else a local `main` or `master`."""
    out = _run(cwd, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD")
    if out and out.strip():
        name = out.strip()
        return name.split("/", 1)[1] if name.startswith("origin/") else name
    branches = local_branches(cwd)
    for name in ("main", "master"):
        if name in branches:
            return name
    return None


def info(cwd: Path) -> dict[str, Any]:
    """Their `Vcs.Info`: `{}` for a folder that is not a work tree."""
    if not is_repo(cwd):
        return {"branch": {}}
    branch: dict[str, str] = {}
    current = current_branch(cwd)
    if current:
        branch["current"] = current
    default = default_branch(cwd)
    if default:
        branch["default"] = default
    return {"provider": "git", "branch": branch}


def _head(cwd: Path) -> str:
    return "HEAD" if _run(cwd, "rev-parse", "-q", "--verify", "HEAD") is not None else EMPTY_TREE


def _created_from(cwd: Path, branch: str) -> str | None:
    """The branch `branch` was made from, as the reflogs remember it.

    The branch's own reflog says `branch: Created from <start>` - but `git
    checkout -b feature` with no start point records `Created from HEAD`,
    which names nothing. Then HEAD's reflog has the move that made it,
    `checkout: moving from main to feature`, and the oldest such move is the
    one that created the branch.
    """
    log = _run(cwd, "reflog", "show", "--format=%gs", f"refs/heads/{branch}") or ""
    created = None
    for line in reversed(log.splitlines()):
        if line.startswith("branch: Created from "):
            created = line[len("branch: Created from "):].strip()
            break
    if created and created not in ("HEAD", branch):
        return created
    moves = _run(cwd, "reflog", "show", "--format=%gs", "HEAD") or ""
    suffix = f" to {branch}"
    for line in reversed(moves.splitlines()):
        if line.startswith("checkout: moving from ") and line.endswith(suffix):
            source = line[len("checkout: moving from "): -len(suffix)].strip()
            if source and source != branch and source in local_branches(cwd):
                return source
    return None


def base(cwd: Path, name: str | None = None) -> dict[str, Any] | None:
    """Their `Vcs.Base`: which branch this one is measured against, and where.

    Named explicitly, it is that branch. Otherwise the reflog says what the
    current branch was created from ("reflog"); failing that it is the
    default branch ("default"). `None` on the default branch itself, or with
    nothing to measure against.
    """
    if not have_git():
        raise Unavailable("git is not installed on this machine")
    if not is_repo(cwd):
        return None
    current = current_branch(cwd)
    source = "default"
    if not name and current:
        created = _created_from(cwd, current)
        if created:
            name, source = created, "reflog"
    if not name:
        name = default_branch(cwd)
    if not name or name == current:
        return None
    ref = _run(cwd, "merge-base", "HEAD", name)
    if not ref or not ref.strip():
        return None
    return {"name": name, "ref": ref.strip(), "source": source}


def _numstat(cwd: Path, *spec: str) -> list[tuple[str, int, int, bool]]:
    """`(file, additions, deletions, binary)` for a diff, names unquoted."""
    out = _run(cwd, "diff", "--numstat", "-z", "--no-renames", "--relative", *spec, "--", ".")
    rows = []
    for record in (out or "").split(NUL):
        fields = record.split("\t", 2)
        if len(fields) != 3 or not fields[2]:
            continue
        added, deleted, name = fields
        binary = added == "-" or deleted == "-"
        rows.append((name, 0 if binary else int(added), 0 if binary else int(deleted), binary))
    return rows


def _statuses(cwd: Path, *spec: str) -> dict[str, str]:
    out = _run(cwd, "diff", "--name-status", "-z", "--no-renames", "--relative", *spec, "--", ".")
    parts = [part for part in (out or "").split(NUL) if part]
    found = {}
    for letter, name in zip(parts[0::2], parts[1::2]):
        found[name] = {"A": "added", "D": "deleted"}.get(letter[:1], "modified")
    return found


def untracked(cwd: Path) -> list[str]:
    out = _run(cwd, "ls-files", "-z", "--others", "--exclude-standard", "--", ".")
    return [name for name in (out or "").split(NUL) if name]


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return NUL.encode() in handle.read(8000)
    except OSError:
        return True


def _line_count(path: Path) -> int:
    try:
        data = path.read_bytes()
    except OSError:
        return 0
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def _spec(cwd: Path, mode: str, base_name: str | None) -> tuple[str, ...]:
    """The revision arguments a mode diffs, as `git diff` takes them."""
    if mode == "working":
        return (_head(cwd),)
    measured = base(cwd, base_name)
    if measured is None:
        # No other branch to measure against: this branch's changes are the
        # working ones.
        return (_head(cwd),) if mode == "branch" else (_head(cwd), _head(cwd))
    if mode == "branch":
        return (measured["ref"],)
    return (measured["ref"], "HEAD")


def status(cwd: Path) -> list[dict[str, Any]]:
    """Their `Vcs.FileStatus` for every change in the work tree, untracked too."""
    if not is_repo(cwd):
        return []
    spec = (_head(cwd),)
    kinds = _statuses(cwd, *spec)
    out = [
        {"file": name, "additions": added, "deletions": deleted, "status": kinds.get(name, "modified")}
        for name, added, deleted, _binary in _numstat(cwd, *spec)
    ]
    for name in untracked(cwd):
        path = cwd / name
        lines = 0 if _is_binary(path) else _line_count(path)
        out.append({"file": name, "additions": lines, "deletions": 0, "status": "added"})
    return out


def _patch(cwd: Path, context: int, *spec: str, name: str) -> str | None:
    return _run(
        cwd, "diff", f"-U{context}", "--no-renames", "--no-color", "--relative", *spec, "--", name
    )


def _patches(cwd: Path, context: int, spec: tuple[str, ...], names: list[str]) -> dict[str, str]:
    """Every file's patch from ONE `git diff`, split at its `diff --git` lines.

    One process rather than one per file, because their panel re-reads on
    every `filesystem.changed`. The sections come in the order `--numstat`
    listed the files - the same diff, the same order - so they are matched by
    position; if the counts disagree (a name git had to quote, say) each file
    is asked for alone instead of guessing.
    """
    if not names:
        return {}
    out = _run(cwd, "diff", f"-U{context}", "--no-renames", "--no-color", "--relative", *spec, "--", ".")
    sections: list[str] = []
    for line in (out or "").splitlines(keepends=True):
        if line.startswith("diff --git ") or not sections:
            sections.append(line)
        else:
            sections[-1] += line
    if out and len(sections) == len(names):
        return dict(zip(names, sections))
    found = {}
    for name in names:
        patch = _patch(cwd, context, *spec, name=name)
        if patch is not None:
            found[name] = patch
    return found


def _untracked_patch(cwd: Path, context: int, name: str) -> str | None:
    # `--no-index` answers 1 when the two sides differ, which they always do.
    return _run(
        cwd, "diff", "--no-index", f"-U{context}", "--no-color", "--", "/dev/null", name, ok=(0, 1)
    )


def diff(cwd: Path, mode: str, base_name: str | None = None, context: Any = None) -> list[dict[str, Any]]:
    """Their `FileDiff.Info` list for a mode, bounded as the module says."""
    if mode not in ("working", "branch", "committed"):
        raise ValueError("mode must be working, branch or committed")
    try:
        lines = DEFAULT_CONTEXT if context in (None, "") else int(context)
    except (TypeError, ValueError) as bad:
        raise ValueError(f"context must be a whole number, got {context!r}") from bad
    lines = max(0, min(lines, MAX_CONTEXT))
    if not have_git():
        raise Unavailable("git is not installed on this machine")
    if not is_repo(cwd):
        return []
    spec = _spec(cwd, mode, base_name)
    kinds = _statuses(cwd, *spec)
    stats = _numstat(cwd, *spec)
    # Binary files are in the diff git prints ("Binary files differ"), so the
    # split needs every name; they are dropped after.
    patches = _patches(cwd, lines, spec, [name for name, *_rest in stats])
    out: list[dict[str, Any]] = []
    for name, added, deleted, binary in stats:
        if binary or len(out) >= MAX_FILES:
            continue
        patch = patches.get(name)
        if patch is None or len(patch) > MAX_PATCH_CHARS:
            continue
        out.append(
            {
                "file": name,
                "patch": patch,
                "additions": added,
                "deletions": deleted,
                "status": kinds.get(name, "modified"),
            }
        )
    if mode != "committed":
        for name in untracked(cwd):
            path = cwd / name
            if len(out) >= MAX_FILES or _is_binary(path):
                continue
            try:
                if path.stat().st_size > MAX_UNTRACKED_BYTES:
                    continue
            except OSError:
                continue
            patch = _untracked_patch(cwd, lines, name)
            if patch is None or len(patch) > MAX_PATCH_CHARS:
                continue
            out.append(
                {
                    "file": name,
                    "patch": patch,
                    "additions": _line_count(path),
                    "deletions": 0,
                    "status": "added",
                }
            )
    return out


def branches(cwd: Path, search: str | None, limit: Any) -> list[str]:
    try:
        wanted = DEFAULT_BRANCHES if limit in (None, "") else int(limit)
    except (TypeError, ValueError) as bad:
        raise ValueError(f"limit must be a whole number, got {limit!r}") from bad
    wanted = max(1, min(wanted, MAX_BRANCHES))
    if not is_repo(cwd):
        return []
    needle = (search or "").casefold()
    return [name for name in local_branches(cwd) if needle in name.casefold()][:wanted]
