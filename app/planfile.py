"""The plan as a markdown file in the project folder - the source of truth.

Max, 2026-09-12: *"the plan should be saved local first as well so that it
previews on the rail but is source of truth md in the file in that chat."*

Two directions, one table. Every write of a thread's plan column
(`events.set_thread_plan` - `write_plan`, a ticked step, the pane's Save, the
prose capture) is MIRRORED to `<project root>/harness-plans/thread-<id>-plan.md`
and the file's mtime and size are recorded here. Every read that matters (the
thread route the panes poll, the turn's start, `read_plan`) first ADOPTS the
file when it has changed since the harness last touched it: the person edited
it in Cursor or an editor, and the file wins. The column is the preview; the
file is the plan.

Nothing is written when the project has no folder on disk - the column then
stands alone, as before. A folder that cannot be written is a fact recorded
in the return value, never a raised error: a plan write must not fail because
a mirror could not be made.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app import db

FOLDER = "harness-plans"

#: ONE PLAN THE FOLDER HOLDS, BESIDE THE ONE EACH CONVERSATION HOLDS.
#:
#: Max, 2026-09-18: *"trouble sharing a journey and plan within one folder and
#: between sessions."* A thread's plan lives and dies with the thread: open a
#: new chat about the same work and the document is gone, and the person types
#: it again or the model writes a worse one. The folder is what outlives a
#: session, so the folder holds the plan a NEW conversation starts from.
#:
#: Two rules keep it from becoming a shared mutable document that every thread
#: fights over, which is the thing this must not be:
#:
#: 1. It is written ONCE, by the first plan any conversation in this project
#:    saves. After that the harness never writes it again - a second thread's
#:    edits are that thread's, in that thread's file.
#: 2. It is read ONCE PER CONVERSATION, at creation, and copied. A person who
#:    edits `project-plan.md` changes what the NEXT conversation adopts and
#:    nothing that is already running.
PROJECT_FILE = "project-plan.md"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plan_files (
    thread_id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    mtime_ns INTEGER NOT NULL,
    size INTEGER NOT NULL,
    written_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def ensure_table() -> None:
    with db.session() as connection:
        connection.executescript(_SCHEMA)


def path_for(thread: dict[str, Any] | None) -> Path | None:
    """Where this thread's plan file lives, or `None` without a project folder."""
    if not thread or not thread.get("project_id"):
        return None
    project = db.get_project(int(thread["project_id"]))
    root = (project or {}).get("root_path")
    if not root:
        return None
    root_dir = Path(str(root))
    if not root_dir.is_dir():
        return None
    return root_dir / FOLDER / f"thread-{int(thread['id'])}-plan.md"


def project_path_for(thread: dict[str, Any] | None) -> Path | None:
    """Where this project's own plan lives, or `None` without a folder.

    Beside the thread files rather than at the root of the person's project:
    `harness-plans/` is the one folder this product writes into, and putting a
    `project-plan.md` at the top of somebody's repository is this harness
    deciding where their documents go.
    """
    path = path_for(thread)
    return None if path is None else path.parent / PROJECT_FILE


def project_plan(thread: dict[str, Any] | None) -> dict[str, Any]:
    """The project's plan as text, with the path it was read from.

    Never raises and never writes: a folder that is gone, a file that cannot be
    read and a project that never had one are all the same answer here - no
    plan - and the path says where one would be.
    """
    path = project_path_for(thread)
    if path is None:
        return {"plan": "", "path": None, "why": "no project folder"}
    try:
        if not path.is_file():
            return {"plan": "", "path": str(path)}
        return {"plan": path.read_text(encoding="utf-8"), "path": str(path)}
    except OSError as error:
        return {"plan": "", "path": str(path), "why": f"{error.strerror or error}"}


def _reopened(plan: str) -> str:
    """The same document with every tick and every park put back to open.

    WHAT IS ADOPTED IS THE WORK, NOT SOMEBODY ELSE'S RECORD OF DOING IT. A
    copy that arrived with `- [x]` on half its steps would tell the new
    conversation that work it has never done is finished, which is the exact
    lie `app/journey.py` refuses to tell about a step nobody ran. Parks go too:
    a reason from another conversation ("no model connected") is a fact about
    that afternoon, not about this one.
    """
    from app.tools import planning

    out: list[str] = []
    for line in str(plan or "").splitlines():
        match = planning._STEP.match(line)
        if match is None:
            out.append(line)
            continue
        text = match.group(4).strip()
        if planning.PARKED_MARK in text:
            text = text.partition(planning.PARKED_MARK)[0].strip()
        out.append(f"{match.group(1)} {match.group(3)}{text}")
    return chr(10).join(out) + (chr(10) if str(plan or "").endswith(chr(10)) else "")


def adopt_project_plan(thread: dict[str, Any] | None) -> dict[str, Any] | None:
    """A new conversation starts from the folder's plan, if the folder has one.

    Called once, from `events.create_thread`, which is every door a thread is
    opened through - the person's New Chat, a test, anything later. A thread
    that already has a plan is left alone; a sub-agent's child never gets here
    at all, because `subagents.delegate` opens it with
    `adopt_project_plan=False` and gives it its one phase instead.

    Best effort, always: a conversation that could not be opened because a
    markdown file would not read is a conversation nobody can have.
    """
    if not thread or str(thread.get("plan") or "").strip():
        return None
    found = project_plan(thread)
    text = str(found.get("plan") or "")
    if not text.strip():
        return None
    from app import events  # lazy: events imports this module the same way

    fresh = _reopened(text)
    row = events.set_thread_plan(int(thread["id"]), fresh)
    events.append(
        "thread.plan_adopted",
        {
            "thread_id": int(thread["id"]),
            "source": "project",
            "path": found.get("path"),
            "characters": len(fresh),
        },
        project_id=thread.get("project_id"),
        thread_id=int(thread["id"]),
    )
    return row


def _stamp(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return int(stat.st_mtime_ns), int(stat.st_size)


def _record(thread_id: int, path: Path) -> None:
    ensure_table()
    mtime_ns, size = _stamp(path)
    with db.session() as connection:
        connection.execute(
            "INSERT INTO plan_files(thread_id, path, mtime_ns, size, written_at) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(thread_id) DO UPDATE SET path = excluded.path, "
            "mtime_ns = excluded.mtime_ns, size = excluded.size, written_at = CURRENT_TIMESTAMP",
            (int(thread_id), str(path), mtime_ns, size),
        )


def _recorded(thread_id: int) -> dict[str, Any] | None:
    ensure_table()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM plan_files WHERE thread_id = ?", (int(thread_id),)
        ).fetchone()
    return None if row is None else dict(row)


def mirror(thread: dict[str, Any] | None, plan: str | None) -> dict[str, Any]:
    """Write the column's plan to the file. Best effort; says what it did."""
    path = path_for(thread)
    if path is None:
        return {"mirrored": False, "why": "no project folder"}
    try:
        if plan is None or not str(plan).strip():
            if path.exists():
                path.unlink()
            ensure_table()
            with db.session() as connection:
                connection.execute("DELETE FROM plan_files WHERE thread_id = ?", (int(thread["id"]),))
            return {"mirrored": True, "path": str(path), "removed": True}
        path.parent.mkdir(parents=True, exist_ok=True)
        text = str(plan)
        if not text.endswith("\n"):
            text += "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
        _record(int(thread["id"]), path)
        out = {"mirrored": True, "path": str(path)}
        # THE FIRST PLAN IN A FOLDER BECOMES THE FOLDER'S PLAN. Once. After
        # that this file is the person's: their edits decide what the next
        # conversation adopts, and a harness that kept overwriting it with
        # whichever thread saved last would make that impossible to keep.
        shared = project_path_for(thread)
        if shared is not None and not shared.exists():
            shared.write_text(text, encoding="utf-8", newline="\n")
            out["project_plan"] = str(shared)
        return out
    except OSError as error:
        return {"mirrored": False, "why": f"{path}: {error.strerror or error}"}


def sync(thread: dict[str, Any] | None) -> dict[str, Any] | None:
    """Adopt the file into the column when the file changed since we wrote it.

    Returns the thread row, re-read if the plan was adopted, with `plan_path`
    on it either way (or `None`). Nothing is written to disk here.
    """
    if not thread:
        return thread
    path = path_for(thread)
    out = dict(thread)
    out["plan_path"] = str(path) if path is not None else None
    if path is None:
        return out
    if not path.is_file():
        # LOCAL FIRST, EVEN FOR A PLAN FROM BEFORE THE FILE EXISTED: a plan
        # in the column with no file beside it is written out on the first
        # read, so the folder always holds what the rail shows.
        if str(thread.get("plan") or "").strip():
            mirror(thread, str(thread.get("plan")))
        return out
    try:
        stamp = _stamp(path)
        recorded = _recorded(int(thread["id"]))
        if recorded is not None and (int(recorded["mtime_ns"]), int(recorded["size"])) == stamp:
            return out
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    current = str(thread.get("plan") or "")
    if text.strip() == current.strip():
        _record(int(thread["id"]), path)
        return out
    from app import events  # lazy: events imports this module the same way

    row = events.set_thread_plan(int(thread["id"]), text.rstrip("\n"), mirror=False)
    _record(int(thread["id"]), path)
    events.append(
        "thread.plan_adopted",
        {"thread_id": int(thread["id"]), "path": str(path), "characters": len(text)},
        project_id=thread.get("project_id"),
        thread_id=int(thread["id"]),
    )
    if row is None:
        return out
    row = dict(row)
    row["plan_path"] = str(path)
    return row
