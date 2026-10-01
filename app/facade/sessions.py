"""Their names for our things: sessions, projects, directories, agents.

OpenCode's protocol and this engine describe the same objects with different
keys. A thread is their session, a project is their project, the folder a
project points at is their location, and the pair of settings a person flips on
a thread - planning or building, and how much may run without asking - is what
their composer calls an agent. This module is the one place those
correspondences are written, so the router, the event translator and the tests
all read the same answer.

## Why a table, when everything else is derived

Their client MINTS the session id. `createData().session.create` makes
`ses_<descending>` in the browser, draws the new chat under that id at once,
and sends the prompt against it before the create request has even returned
(`sendAdmission` waits on the create, then posts to the id it made). A facade
that answered with an id of its own would leave the client posting to a
session that does not exist. So a client-made id is recorded against the
thread it names, and every other thread answers to `ses_<thread id>`, which
cannot collide with theirs because theirs are twenty-six characters of
time-and-random after the prefix.

A row is never deleted, not even with its thread. Thread ids are
`AUTOINCREMENT` and never reused, so a row for a deleted thread names nothing
that can come back - and the event stream still needs it after the delete, to
tell their client WHICH session `thread.deleted` removed.

Self-healing `CREATE TABLE IF NOT EXISTS`, the pattern `app/providers/store.py`
uses, because this table belongs to the facade rather than to the engine's
schema: a database that has never been opened through `/oc` never grows it.

## Where the default workspace lives

The product promise is that a person lands in a chat with no configuration,
and their interface needs every session to have a real directory. A project
with no folder gets one, created on first use, and a PERSON MUST BE ABLE TO
FIND IT: for their own engine that is `~/Documents/ML Harness/<project>`,
not the data root under AppData (`workspace_root`). A test sandbox or a
custom database keeps it beside the database instead, for the reason
`db.DB_PATH` is rebound in every test: the sandbox moves the database, so a
workspace derived from it moves with it, and a test can never create a
folder in the checkout or in a home directory. It is computed on every call,
never held in a module-level path, so `support.repo_path_globals()` has
nothing to account for.

The folder is named after the project, so RENAMING a folder-less project
points it at a new, empty folder; the old one stays on disk under the old
name. Giving the project that folder as its own (`root_path`) is the way to
keep one across a rename.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import autonomy, db, events, modes

#: The protocol version string their `session.created` event carries. Their
#: servers put their own release here; ours names the engine so a transcript
#: exported through their client says what wrote it.
VERSION = "ml-harness"

_SESSION = re.compile(r"^ses_([0-9]+)$")
_PROJECT = re.compile(r"^prj_([0-9]+)$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facade_sessions (
    oc_id TEXT PRIMARY KEY,
    thread_id INTEGER NOT NULL UNIQUE
);
"""


def ensure_table() -> None:
    with db.session() as connection:
        connection.executescript(_SCHEMA)


# ---------------------------------------------------------------------------
# Identifiers


def remember(oc_id: str, thread_id: int) -> None:
    """Record that their id `oc_id` names our thread `thread_id`."""
    ensure_table()
    with db.session() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO facade_sessions (oc_id, thread_id) VALUES (?, ?)",
            (str(oc_id), int(thread_id)),
        )


def session_id(thread_id: int) -> str:
    """The id their client knows this thread by."""
    ensure_table()
    with db.session() as connection:
        row = connection.execute(
            "SELECT oc_id FROM facade_sessions WHERE thread_id = ?", (int(thread_id),)
        ).fetchone()
    return str(row["oc_id"]) if row else f"ses_{int(thread_id)}"


def thread_id_of(sid: str) -> int | None:
    """Our thread for their session id, or `None` when it names nothing.

    The recorded table is asked FIRST: a client-made id is opaque, and reading
    it with the `ses_<n>` pattern before checking the table would let an id
    that happened to be digits resolve to somebody else's thread.
    """
    ensure_table()
    with db.session() as connection:
        row = connection.execute(
            "SELECT thread_id FROM facade_sessions WHERE oc_id = ?", (str(sid),)
        ).fetchone()
    if row:
        return int(row["thread_id"])
    match = _SESSION.match(str(sid))
    return int(match.group(1)) if match else None


def project_id(project: int) -> str:
    return f"prj_{int(project)}"


def project_of(pid: str) -> int | None:
    match = _PROJECT.match(str(pid))
    return int(match.group(1)) if match else None


def ms(stamp: Any) -> int:
    """SQLite's `CURRENT_TIMESTAMP` text as epoch milliseconds.

    The engine stores UTC text; their protocol counts milliseconds. A value
    that does not parse reads as 0 rather than raising, because a timestamp is
    decoration on a row and a row that cannot be dated should still be listed.
    """
    if stamp is None:
        return 0
    text = str(stamp).strip().replace("T", " ")
    for pattern in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(text[:26], pattern)
        except ValueError:
            continue
        return int(parsed.replace(tzinfo=timezone.utc).timestamp() * 1000)
    try:
        return int(datetime.fromisoformat(str(stamp)).timestamp() * 1000)
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# Directories


def _same_directory(left: str, right: str) -> bool:
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(
        os.path.normpath(right)
    )


#: Names Windows will not give a file or folder, whatever follows the dot.
_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"} | {f"com{n}" for n in range(1, 10)} | {f"lpt{n}" for n in range(1, 10)}
)
#: Characters no folder name may hold on Windows, plus the control characters.
#: Built rather than written, so no escape in this file can be lost.
_UNSAFE = frozenset('<>:"/|?*') | {chr(92)} | {chr(code) for code in range(32)}

#: What the person-findable root is called under their Documents folder.
DOCUMENTS_FOLDER = "ML Harness"


def workspace_root() -> Path | None:
    """Where folder-less projects' workspaces live, or `None` for "beside the database".

    Three rules, first match wins, and none of them touches the database or
    the disk:

    1. `MLH_WORKSPACE_ROOT` names it. A person or a packaging script that
       said where has said something more specific than this function knows.
    2. The database is the default per-user one - `db.DB_PATH` is
       `paths.in_data_root("ml_harness.db")` and `ML_HARNESS_DB` is not set -
       so this is a person's own engine: `~/Documents/ML Harness`. The
       installed app's data root is under AppData, where nobody would look
       for the files a conversation made.
    3. Anything else - a test sandbox, a custom database - keeps the
       workspaces beside that database, so they move with it and a test can
       never make a folder in a real home directory.
    """
    from app import paths

    named = os.environ.get("MLH_WORKSPACE_ROOT")
    if named:
        return Path(named)
    if not os.environ.get("ML_HARNESS_DB") and _same_directory(
        str(db.DB_PATH), str(paths.in_data_root("ml_harness.db"))
    ):
        return Path.home() / "Documents" / DOCUMENTS_FOLDER
    return None


def safe_folder_name(name: str, project: int) -> str:
    """A project's name as a folder name on every platform, never empty."""
    cleaned = "".join("-" if char in _UNSAFE else char for char in str(name or ""))
    cleaned = " ".join(cleaned.split())[:80].rstrip(" .")
    if not cleaned:
        return f"project-{int(project)}"
    if cleaned.split(".")[0].casefold() in _RESERVED:
        return f"{cleaned} ({int(project)})"
    return cleaned


def _folder_name(project: int) -> str:
    """This project's folder under the root: its safe name, made unique.

    Two projects called "Default" must not share a folder, so the older one
    (lower id) keeps the plain name and a younger one gets its id appended.
    Archived projects count, because their folders are still on disk.
    """
    everyone = {int(p["id"]): p for p in db.list_projects(include_archived=True)}
    mine = everyone.get(int(project))
    name = safe_folder_name(str((mine or {}).get("name") or ""), int(project))
    taken = any(
        other_id < int(project)
        and safe_folder_name(str(other.get("name") or ""), other_id).casefold() == name.casefold()
        for other_id, other in everyone.items()
    )
    return f"{name} ({int(project)})" if taken else name


def legacy_workspace(project: int) -> Path:
    """Where a folder-less project worked before 2026-09-22: beside the database."""
    return Path(db.DB_PATH).resolve().parent / "workspaces" / f"project-{int(project)}"


def workspace_for(project: int) -> Path:
    """The folder a project with no folder of its own works in.

    Computed on every call - never held in a module-level path - so a test
    that moves the database moves this, and `support.repo_path_globals()` has
    nothing to account for.

    A WORKSPACE THAT ALREADY HOLDS FILES STAYS WHERE IT IS. Before this rule a
    folder-less project worked beside the database; a person whose
    conversations already wrote files there keeps that folder rather than
    being moved to an empty new one and losing sight of them. Only an empty
    or missing old folder gives way to the findable one.
    """
    root = workspace_root()
    legacy = legacy_workspace(project)
    if root is None:
        return legacy
    try:
        if legacy.is_dir() and any(legacy.iterdir()):
            return legacy
    except OSError:
        pass
    return root / _folder_name(project)


def directory_of(project: dict[str, Any]) -> str:
    """The project's folder, or its default workspace, which exists after this."""
    root = project.get("root_path")
    if root:
        return str(root)
    folder = workspace_for(int(project["id"]))
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


def find_project(directory: str) -> dict[str, Any] | None:
    """The live project whose folder, or default workspace, is `directory`.

    The workspace beside the database is recognised too, whichever rule now
    applies, so a location their client saved before the rule changed still
    names its project rather than becoming a new one.
    """
    for project in db.list_projects():
        if project.get("root_path"):
            if _same_directory(str(project["root_path"]), directory):
                return project
            continue
        pid = int(project["id"])
        if _same_directory(str(workspace_for(pid)), directory) or _same_directory(
            str(legacy_workspace(pid)), directory
        ):
            return project
    return None


def project_for_directory(directory: str | None, *, create: bool = True) -> dict[str, Any]:
    """The project a directory belongs to.

    No directory means the default project, which is where a person who has
    configured nothing lands. A directory that is a project's folder, or a
    project's default workspace, is that project. A directory nobody has
    mentioned before becomes a new project pointed at it - the same thing
    their server does when a client opens a folder it has not seen - with the
    engine's own `project.created` event, so every other window hears of it.
    """
    if not directory:
        return db.default_project()
    found = find_project(directory)
    if found is not None:
        return found
    if not create or not os.path.isabs(directory):
        return db.default_project()
    name = Path(directory).name or directory
    project = db.create_project(name[:120], directory)
    events.append(
        "project.created",
        {"id": project["id"], "name": project["name"], "portal": project["portal"]},
        project_id=project["id"],
    )
    return project


def project_info(project: dict[str, Any]) -> dict[str, Any]:
    """A project as their `Project` schema describes one.

    `vcs` is `"git"` when the folder is in a git work tree: their review panel
    offers its git modes only for a project that says so
    (`session/review/model.ts`), and `app/facade/vcs.py` answers them.
    """
    from app.facade import vcs

    directory = directory_of(project)
    created = ms(project.get("created_at"))
    info: dict[str, Any] = {
        "id": project_id(project["id"]),
        "canonical": directory,
        "name": str(project.get("name") or ""),
        "time": {"created": created, "updated": created},
        "sandboxes": [],
    }
    if vcs.is_repo(Path(directory)):
        info["vcs"] = "git"
    return info


def location_info(project: dict[str, Any]) -> dict[str, Any]:
    directory = directory_of(project)
    return {
        "directory": directory,
        "project": {
            "id": project_id(project["id"]),
            "directory": directory,
            "canonical": directory,
        },
    }


# ---------------------------------------------------------------------------
# Agents: a thread's mode and permission, as one choice


#: THE AGENTS THEIR PICKER OFFERS, AND WHAT EACH ONE SETS ON THE THREAD.
#: Exactly three, the old composer's three presets: Plan (plan + ask), Build
#: (build + ask) and Full (build + full). Max, 2026-09-22: he wants it simple.
#: The two middle ladder steps, `measure` and `write`, were agents here for a
#: while so every step was one click away; they are not offered any more, and
#: stay reachable only through the engine's own permission route - `POST
#: /api/threads/{id}/permission`, a ruleset on the session, or an "always"
#: approval - where a thread on one of them reads as `build` (`agent_of`).
#: Switching agent makes the change through the engine's own two doors
#: (`POST /api/threads/{id}/mode` and `/permission`).
AGENTS: dict[str, dict[str, str]] = {
    "plan": {
        "mode": "plan",
        "permission": "ask",
        "description": modes.MODES["plan"],
    },
    "build": {
        "mode": "build",
        "permission": "ask",
        "description": modes.MODES["build"],
    },
    "full": {
        "mode": "build",
        "permission": "full",
        "description": (
            "Execution with nothing held for a click: every gated tool runs "
            "without asking except the irreversible sandbox wipe. "
            + modes.MODES["build"]
        ),
    },
}


def agent_of(thread: dict[str, Any]) -> str:
    """Which of `AGENTS` this thread's two settings amount to.

    Planning is `plan` whatever the ladder says, because a planning turn is
    handed lookups only and the ladder has nothing to pre-approve in it. A
    building thread is `full` on the full step and `build` on every other -
    `measure` and `write` included, which are not agents (see `AGENTS`), so
    the name returned is always one the picker offers.
    """
    if modes.normalise(thread.get("mode")) == "plan":
        return "plan"
    step = autonomy.normalise(str(thread.get("permission") or ""))
    return "full" if step == "full" else "build"


def ruleset_of(permission: str | None) -> list[dict[str, str]]:
    """What a ladder step pre-approves, as their permission rules.

    One `allow` rule per tool the step covers, read off `autonomy.covers_for`,
    so the list is exactly what will run without a click - never a summary of
    it. `ask` covers nothing and is the empty list: every gated tool asks.
    """
    mode = autonomy.normalise(permission)
    return [
        {"action": name, "resource": "*", "effect": "allow"}
        for name in sorted(autonomy.covers_for(mode))
    ]


def permission_from_ruleset(rules: list[dict[str, Any]] | None) -> str:
    """The smallest ladder step that allows every tool the rules allow.

    Their rules are free-form and the ladder is four steps, so this rounds UP
    to a step that covers the request rather than silently granting less than
    was asked. A wildcard `allow` is `full`; no `allow` at all is `ask`.
    """
    allowed = {
        str(rule.get("action"))
        for rule in rules or []
        if str(rule.get("effect")) == "allow"
    }
    if not allowed:
        return "ask"
    if "*" in allowed:
        return "full"
    for step in autonomy.MODES:
        if allowed <= set(autonomy.covers_for(step)):
            return step
    return "full"


def parent_of(thread_id: int) -> int | None:
    """The thread whose sub-agent this one is, if it is one."""
    from app import subagents

    subagents.ensure_table()
    with db.session() as connection:
        row = connection.execute(
            "SELECT parent_thread_id FROM subagents WHERE child_thread_id = ?",
            (int(thread_id),),
        ).fetchone()
    return int(row["parent_thread_id"]) if row and row["parent_thread_id"] else None


def session_info(thread: dict[str, Any]) -> dict[str, Any]:
    """A thread as their `Session.Info` describes one.

    `tokens` is every turn's record summed (`spend.thread`): `input` is the
    prompt the conductor counted on each turn's `turn.context` - the figure
    `/api/threads/{id}/usage` reports - and `output` / `reasoning` are the
    model's streamed text, estimated with the same counter. `cost` is 0
    because the engine prices nothing.
    """
    from app.facade import catalog, spend

    project = db.get_project(int(thread["project_id"])) if thread.get("project_id") else None
    if project is None:
        project = db.default_project()
    info: dict[str, Any] = {
        "id": session_id(int(thread["id"])),
        "projectID": project_id(project["id"]),
        "agent": agent_of(thread),
        "cost": 0,
        "tokens": spend.thread(int(thread["id"])),
        "time": {
            "created": ms(thread.get("created_at")),
            "updated": ms(thread.get("updated_at") or thread.get("created_at")),
        },
        "title": str(thread.get("title") or ""),
        "permissions": ruleset_of(thread.get("permission")),
        "location": {"directory": directory_of(project)},
        # A client-minted session id cannot be read back into a thread id, and
        # the harness's own panes (plan, context, runs) are keyed on the
        # thread. Their `Session.Metadata` is an open object for exactly this.
        "metadata": {
            "harness": {"threadID": int(thread["id"]), "projectID": int(project["id"])}
        },
    }
    if thread.get("archived_at"):
        info["time"]["archived"] = ms(thread["archived_at"])
    model = catalog.active_model_ref()
    if model is not None:
        info["model"] = model
    parent = parent_of(int(thread["id"]))
    if parent is not None:
        info["parentID"] = session_id(parent)
    return info
