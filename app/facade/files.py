"""Their file tree, previews and @-mentions, confined to the project's folder.

Their interface reads files through three operations
(`vendor/opencode/packages/app/src/workspaces/files/model.tsx`):

* `fs.list(path, location)` - one directory's children, for the file tree.
  Each entry's `path` is RELATIVE TO THE LOCATION DIRECTORY, not to the listed
  directory: the tree builds `absolute` as `${location}/${entry.path}`.
* `fs.read(path, location)` - a file's bytes, for a preview. Their viewer
  decides text or binary itself (`fileContentFromBytes`). A file outside the
  workspace is asked for with its own parent as the location.
* `fs.find(query, type, limit, location)` - a fuzzy search, for @-mentions and
  "open file".

And one write: `experimental.fs.write(path)`, their attachment upload, which
streams a file into `server.info`'s `paths.tmp` and hands the resolved path to
the composer (`composer/attachments/destination.ts`).

## The confinement rule

EVERY PATH IS RESOLVED BEFORE IT IS JUDGED, AND JUDGED AGAINST A ROOT THIS
ENGINE CHOSE. A location is accepted only when it is a project's folder (or
default workspace), a directory inside one, or inside the engine's temporary
directory; the path is then resolved against it - symlinks followed, `..`
collapsed - and refused unless the result is still inside that same root. So
`../../secrets`, an absolute path elsewhere, and a symlink pointing out of the
project are all the same refusal, with their declared error. Writing is
narrower still: only inside the temporary directory, because an upload is an
attachment, never an edit to the person's files.

## Bounded, and ignoring what git ignores

A listing is capped at `MAX_LIST` entries and a search at `MAX_FIND`. In a git
work tree the listing drops what `git check-ignore` says is ignored (one
subprocess per listing), and the search walks `git ls-files -co
--exclude-standard` rather than the disk; outside one, the walk skips the
usual heavy directories and stops after `MAX_WALK` files. A read is refused
above `MAX_READ_BYTES`, and a binary file their viewer cannot draw is sent as
its first `SNIFF_BYTES` only - enough for their viewer's own binary test to
show its placeholder - rather than in full. Images and PDFs, which their
viewer does draw, are sent whole.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from app import db
from app.facade import sessions

MAX_LIST = 2000
MAX_FIND = 200
DEFAULT_FIND = 50
MAX_WALK = 20000
MAX_READ_BYTES = 10 * 1024 * 1024
SNIFF_BYTES = 8000
#: An upload larger than this is refused part way rather than filling a disk.
MAX_WRITE_BYTES = 512 * 1024 * 1024
GIT_TIMEOUT = 10.0
NUL = chr(0)

#: Directories a search outside git never enters. Inside git, `.gitignore`
#: decides instead.
HEAVY = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"})

#: File kinds their viewer draws from bytes (`artifactKind` in
#: `workspaces/files/artifact.ts`), which are therefore sent whole.
MEDIA = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svg", ".avif",
        ".pdf", ".mp3", ".wav", ".ogg", ".mp4", ".webm", ".mov",
    }
)


class Outside(Exception):
    """A path that resolves outside every root this engine will read."""


class Missing(Exception):
    """A path inside a root that names no file."""


def tmp_dir() -> Path:
    """The engine's temporary directory: `tmp` beside the database.

    Beside the database for the reason the default workspace was: the test
    sandbox moves the database, so this moves with it and a test cannot write
    into a checkout. For the installed product the database is in the data
    root, so this is under the data root. Created on first ask.
    """
    folder = Path(db.DB_PATH).resolve().parent / "tmp"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _resolve(path: Path) -> Path:
    return Path(os.path.realpath(path))


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def roots() -> list[Path]:
    """Every folder a read may happen in: each project's, and the temp dir."""
    out = []
    for project in db.list_projects():
        out.append(_resolve(Path(sessions.directory_of(project))))
    out.append(_resolve(tmp_dir()))
    return out


def base_for(directory: str | None) -> tuple[Path, Path]:
    """`(root, base)` for a location: the root it lies in, and itself resolved.

    No location means the default project's folder. A location inside no root
    is `Outside` - a folder this engine has no project for is not one it reads.
    """
    if not directory:
        base = _resolve(Path(sessions.directory_of(db.default_project())))
        return base, base
    base = _resolve(Path(directory))
    for root in roots():
        if _inside(base, root):
            return root, base
    raise Outside(f"{directory} is not a project folder this engine has, or inside one")


def target(directory: str | None, path: str | None) -> tuple[Path, Path, Path]:
    """`(root, base, resolved path)`, or `Outside` when the path escapes its root."""
    root, base = base_for(directory)
    if not path:
        return root, base, base
    given = Path(path)
    resolved = _resolve(given if given.is_absolute() else base / given)
    if not _inside(resolved, root):
        raise Outside(f"{path} is outside {root}")
    return root, base, resolved


def relative(path: Path, base: Path) -> str:
    """A path as their tree names it: relative to the location, with `/`."""
    return path.relative_to(base).as_posix()


def _git(cwd: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess | None:
    """Run git in `cwd` - no shell, bounded, output as text.

    BYTES IN, TEXT OUT, ON PURPOSE. In text mode Python on Windows writes
    every newline sent to a child's stdin as CRLF, and `git check-ignore
    --stdin` then asks about `build/\\r`, which nothing ignores - measured, it
    listed an ignored folder. So stdin goes as UTF-8 bytes, and stdout is
    decoded here.
    """
    try:
        done = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            input=stdin.encode("utf-8") if stdin is not None else None,
            capture_output=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    done.stdout = done.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")
    done.stderr = done.stderr.decode("utf-8", errors="replace")
    return done


def in_work_tree(directory: Path) -> bool:
    done = _git(directory, "rev-parse", "--is-inside-work-tree")
    return bool(done and done.returncode == 0 and done.stdout.strip() == "true")


def _ignored(directory: Path, names: list[str]) -> set[str]:
    """Which of `names` (children of `directory`) git ignores. Empty outside git.

    A directory is asked about with a trailing `/`, because a pattern such as
    `node_modules/` matches only a path git knows to be a directory.
    """
    if not names or not in_work_tree(directory):
        return set()
    # `-z`: NUL-separated both ways, so a name git would otherwise quote (a
    # space, an accent) comes back as itself.
    done = _git(directory, "check-ignore", "-z", "--stdin", stdin=NUL.join(names) + NUL)
    if done is None or done.returncode not in (0, 1):
        return set()
    return {name.rstrip("/") for name in done.stdout.split(NUL) if name}


def list_entries(directory: str | None, path: str | None) -> list[dict[str, Any]]:
    """One directory's children, directories first, as their `FileSystem.Entry`."""
    _root, base, folder = target(directory, path)
    if not folder.is_dir():
        raise Missing(f"{path or folder} is not a folder")
    children: list[tuple[str, bool]] = []
    try:
        with os.scandir(folder) as found:
            for entry in found:
                if entry.name == ".git":
                    continue
                try:
                    children.append((entry.name, entry.is_dir()))
                except OSError:
                    continue
                if len(children) >= MAX_LIST * 2:
                    break
    except OSError as error:
        raise Missing(f"{folder} cannot be read: {error}") from error
    ignored = _ignored(folder, [name + "/" if is_dir else name for name, is_dir in children])
    out = []
    for name, is_dir in children:
        if name in ignored:
            continue
        out.append({"path": relative(Path(folder, name), base), "type": "directory" if is_dir else "file"})
    out.sort(key=lambda item: (item["type"] != "directory", item["path"].casefold()))
    return out[:MAX_LIST]


def _all_files(base: Path) -> list[str]:
    """Every file under `base`, relative, git's view when it is a work tree."""
    if in_work_tree(base):
        done = _git(base, "ls-files", "-z", "-co", "--exclude-standard", "--", ".")
        if done is not None and done.returncode == 0:
            # `ls-files` answers relative to the cwd, which is `base`.
            return [name for name in done.stdout.split(NUL) if name][:MAX_WALK]
    found: list[str] = []
    for current, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in HEAVY)
        for name in sorted(files):
            found.append(Path(current, name).relative_to(base).as_posix())
            if len(found) >= MAX_WALK:
                return found
    return found


def _score(query: str, candidate: str) -> int | None:
    """How well `candidate` matches `query`; lower is better, `None` is no match.

    A basename that contains the query beats a path that does, which beats the
    query's letters appearing in order - the shape of their own fuzzy finder.
    """
    if not query:
        return 3
    text = candidate.casefold()
    name = text.rsplit("/", 1)[-1]
    if name.startswith(query):
        return 0
    if query in name:
        return 1
    if query in text:
        return 2
    position = 0
    for letter in query:
        position = text.find(letter, position)
        if position < 0:
            return None
        position += 1
    return 3


def find(directory: str | None, query: str, kind: str | None, limit: Any) -> list[dict[str, Any]]:
    _root, base, _ = target(directory, None)
    try:
        wanted = int(limit) if limit not in (None, "") else DEFAULT_FIND
    except (TypeError, ValueError) as bad:
        raise ValueError(f"limit must be a whole number, got {limit!r}") from bad
    wanted = max(1, min(wanted, MAX_FIND))
    files = _all_files(base)
    candidates: list[tuple[str, str]] = []
    if kind in (None, "", "file"):
        candidates += [(path, "file") for path in files]
    if kind in (None, "", "directory"):
        folders: set[str] = set()
        for path in files:
            parts = path.split("/")[:-1]
            for depth in range(1, len(parts) + 1):
                folders.add("/".join(parts[:depth]))
        candidates += [(path, "directory") for path in sorted(folders)]
    needle = query.strip().casefold()
    scored = []
    for path, what in candidates:
        score = _score(needle, path)
        if score is not None:
            scored.append((score, len(path), path, what))
    scored.sort()
    return [{"path": path, "type": what} for _s, _l, path, what in scored[:wanted]]


def read(directory: str | None, path: str) -> bytes:
    """A file's bytes for their viewer, bounded as the module docstring says."""
    _root, _base, file = target(directory, path)
    if not file.is_file():
        raise Missing(f"no file {path}")
    size = file.stat().st_size
    if size > MAX_READ_BYTES:
        raise ValueError(
            f"{path} is {size // (1024 * 1024)} MB; previews stop at {MAX_READ_BYTES // (1024 * 1024)} MB"
        )
    data = file.read_bytes()
    if file.suffix.lower() in MEDIA:
        return data
    if b"\x00" in data[:SNIFF_BYTES]:
        return data[:SNIFF_BYTES]
    return data


def write_target(directory: str | None, path: str) -> Path:
    """Where an upload may go: inside the temporary directory, nowhere else."""
    if not path:
        raise ValueError("path is required")
    tmp = _resolve(tmp_dir())
    given = Path(path)
    if not given.is_absolute():
        # Relative to the location, as their schema says - which is a project
        # folder, so a relative upload path is refused below like any other
        # path outside the temporary directory.
        given = base_for(directory)[1] / given
    # The file does not exist yet, so its parent is resolved and the name kept.
    resolved = _resolve(given.parent) / given.name
    if not given.name or given.name in (".", "..") or not _inside(resolved, tmp) or resolved == tmp:
        raise Outside(f"{path} is outside the engine's temporary directory {tmp}")
    return resolved
