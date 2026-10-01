"""The durable transcript: threads, messages, and the append-only event log.

VISION.md makes two promises that most chat products make and do not keep. This
file is where both of them are either true or false.

**"The transcript is the artifact."** The thread is the lab notebook. That is
only true if the thread is written to disk as it happens, rather than
reconstructed afterwards from whatever the browser still had in memory. So
threads and messages live here, next to the event log, and not in a cache.

**"Long-running work lives in the conversation."** Training takes hours and the
laptop closes. The answer is not a reconnect protocol we invent; it is that
every frame the client ever sees has an integer id, that id is the primary key
of a row that was already committed before the frame was written to a socket,
and a client that comes back says "I had up to 412" and gets 413 onwards.

The two rules that make that work, and that nothing here may bend:

1. **The autoincrement id IS the SSE event id.** Not a counter kept alongside
   it, not a UUID, not the index of the frame within one response. One number,
   one meaning, monotonic across the whole database. `ARCHITECTURE.md` §4.2.
2. **Nothing streams that was not first durably written.** `append()` returns
   only after the row is committed. The Conductor calls `append()` and streams
   what `append()` gave back - never the other way round. A frame that never
   got an id cannot be replayed, and the frame that cannot be replayed will be
   the one that mattered.

`since` is strictly greater-than, never greater-or-equal. `Last-Event-ID` is
the id of the last frame the client *received*; replaying it would duplicate a
token, and a duplicated token in a streamed sentence is a visible defect.

**Append-only.** Nothing in this repository issues `UPDATE` or `DELETE` against
`events`. There is no retention job yet; when there is one, it is the only
exception and it gets its own review.

## Why the tables are no longer created here

They used to be. This file created `threads`, `messages` and `events` with the
same self-healing `CREATE TABLE IF NOT EXISTS` the rest of the tree used,
because the Conductor needed them and the migration runner did not exist yet -
`docs/ROADMAP.md` step 1.4 says exactly that, and lists folding them into a
numbered migration as still owed.

That is now `app/migrations/v004_threads_belong_to_a_project.py`, which also
gives a thread the `project_id` it always should have had. `ensure_tables()`
survives as the name every reader here calls, and runs the migration runner.
The statements are unchanged, so a database written before the fold applies
migration 4 as a no-op plus two `ALTER TABLE`s.

`providers` has not been folded yet and is still self-healing in
`app/providers/store.py`. Said here rather than left to be discovered.
"""

from __future__ import annotations

import json
from typing import Any

from app import db, modes
from app import diagnosis, diagnosis


#: The scopes a stream may be opened on. A scope is `"<kind>:<id>"` and the
#: kind maps to a column. Anything else is a `ValueError` rather than a silent
#: empty result, because "you asked for a scope that does not exist" and "that
#: scope has no events yet" are different answers and a client needs to tell
#: them apart.
SCOPE_COLUMNS = {
    "project": "project_id",
    "thread": "thread_id",
    "run": "run_id",
}

#: Emitted when a turn is complete. The stream endpoint uses it to close a
#: response rather than hold the socket open forever.
END_KIND = "stream.end"


def ensure_tables() -> None:
    """Bring the schema up to date. The transcript tables are migration 4's."""
    from app import migrations

    migrations.migrate()


# ---------------------------------------------------------------------------
# Threads and messages - the transcript itself.


def create_thread(
    title: str,
    project_id: int | None = None,
    ledger: str | None = None,
    mode: str = "build",
    adopt_project_plan: bool = True,
) -> dict[str, Any]:
    """Start a thread. It always belongs to a project, and it always names a ledger.

    `project_id=None` means `db.default_project()`, which creates one named
    `Default` if the database has none. That is what lets every caller in this
    milestone be project-scoped without the UI having to ship a project picker
    first, and it is why `project_id` can be nullable in the schema without
    being null in practice: nothing here ever writes a thread without one.

    `ledger=None` means `diagnosis.DEFAULT_LEDGER`, which is the column's own
    default and is what every thread that has ever existed is running. It is
    NOT a way for a caller to choose a domain: `docs/VISION.md` is explicit that
    the harness infers the discipline and the user never picks one, and the
    thing that infers it is the ledger walk itself. The parameter exists so the
    engine can record what it inferred, and so a test can build the second
    ledger's thread without writing SQL - not so a chooser can be built on top
    of it.

    `mode` is `build` unless a caller says otherwise, and that default is
    the same kind of statement the `ledger` paragraph above makes: this is
    a storage primitive, not the place a product decision lives. Every
    caller this function has ever had was handed tools, so every caller
    that does not ask keeps being handed them. The one door where a PERSON
    opens a conversation - `POST /api/threads` - passes
    `modes.WHEN_A_PERSON_OPENS_A_CONVERSATION`, so a new chat opens in
    planning without a fixture in the suite silently losing its tools.
    `modes.normalise` decides what an unrecognised value means; nothing is
    refused here, because a thread whose mode column is odd should still
    answer and the control shows the person which mode it is in.

    The path is stored as it is given and is REFUSED rather than repaired if it
    does not load: a thread pointing at a ledger this build cannot read would
    fail at its first tool call, several turns later, in a place that could not
    say what was wrong. `diagnosis.spec_at` is the validator and it is the same
    one every tool call goes through, so a thread that was created is a thread
    whose ledger is known to parse.
    """
    ensure_tables()
    if project_id is None:
        project_id = db.default_project()["id"]
    named = diagnosis.DEFAULT_LEDGER if ledger is None else str(ledger)
    diagnosis.spec_at(named)  # refuse a thread whose knowledge does not load
    with db.session() as connection:
        #: THE MODE IS WRITTEN, never left to the column default. Migration
        #: v016 defaults the column to `build` so that every thread which
        #: already existed keeps the tools it has always been handed. What
        #: a thread created NOW is in is this argument, which means the
        #: decision is visible at the call site that made the thread rather
        #: than reaching backwards through the table.
        cursor = connection.execute(
            "INSERT INTO threads (title, project_id, ledger, mode) "
            "VALUES (?, ?, ?, ?)",
            (title, project_id, named, modes.normalise(mode)),
        )
        row = connection.execute(
            "SELECT * FROM threads WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    # A NEW CONVERSATION IN A FOLDER THAT HAS A PLAN STARTS FROM IT. Max,
    # 2026-09-18: *"trouble sharing a journey and plan within one folder and
    # between sessions."* The copy has every tick and every park reset, because
    # what is shared is the work and not another conversation's record of doing
    # it (`app/planfile.py`). A project with no folder, or a folder with no
    # `project-plan.md`, adopts nothing and this costs one `is_file()`.
    #
    # `adopt_project_plan=False` IS FOR A CALLER THAT IS ABOUT TO WRITE THE
    # PLAN ITSELF, and there is one: `subagents.delegate` gives its child a
    # single phase on the line after this returns. Adopting first would write
    # the whole plan to the child's file and leave a `thread.plan_adopted` row
    # that is false by the time anybody reads it.
    fresh = dict(row)
    if not adopt_project_plan:
        return fresh
    try:
        from app import planfile

        adopted = planfile.adopt_project_plan(fresh)
    except Exception:  # noqa: BLE001 - a conversation must open whatever the disk says
        adopted = None
    return dict(adopted) if adopted is not None else fresh


def list_threads(
    project_id: int | None = None, include_archived: bool = False
) -> list[dict[str, Any]]:
    """Newest first. A rail read oldest-first buries today's work.

    Filtered by project when one is given, which is the query the rail's tree
    is drawn from; unfiltered it is every live thread, which is what the flat
    list the product ships today asks for.
    """
    ensure_tables()
    #: AND WHOSE SUB-AGENT IT IS, if it is one. Max, 2026-09-14: *"have the
    #: sub-agents pop up under and indented from the chat on the rail, so that
    #: if the chat moves up you can see on the side rail how many sub-agents
    #: are running."* The rail cannot nest a child under its parent without
    #: knowing the link, and asking per row would be one request per thread on
    #: every rail read. A LEFT JOIN costs this query nothing and a thread that
    #: is nobody's sub-agent gets three nulls, which is the honest answer.
    from app import subagents as _subagents

    _subagents.ensure_table()
    query = (
        "SELECT t.*, s.parent_thread_id AS subagent_of, s.phase AS subagent_phase, "
        "s.state AS subagent_state FROM threads t "
        "LEFT JOIN subagents s ON s.child_thread_id = t.id"
    )
    where = []
    parameters: list[Any] = []
    if project_id is not None:
        where.append("t.project_id = ?")
        parameters.append(project_id)
    if not include_archived:
        where.append("t.archived_at IS NULL")
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY t.id DESC"
    with db.session() as connection:
        rows = connection.execute(query, tuple(parameters)).fetchall()
    return [dict(row) for row in rows]


def rename_thread(thread_id: int, title: str) -> dict[str, Any] | None:
    """Retitle one thread. `None` when it does not exist, like `add_message`.

    `updated_at` moves too: the rail is sorted by recency and a thread the user
    just touched that stays where it was reads as a rail that ignored them.
    """
    return _update_thread(
        thread_id,
        "UPDATE threads SET title = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE id = ?",
        (title, thread_id),
    )


def set_thread_goal(
    thread_id: int, goal: str | None, journey: str | None
) -> dict[str, Any] | None:
    """Record what this thread is FOR — the person's own words, verbatim.

    The owner's ask (2026-08-31): "it doesn't save your goal anywhere... I
    kind of want a similar thing where it saves this kind of goal idea."
    `goal` is either the person's first substantive message (copied by the
    conductor, no model in the loop) or their correction through
    `POST /api/threads/{id}/goal`; it is never a model's paraphrase, because
    a reworded goal would be an ASSERTED claim standing where the person's
    word belongs. `journey` is the playbook's keyword match for those words,
    or None when nothing matched. `None, None` clears both — "no goal" is a
    real state and must stay expressible.
    """
    return _update_thread(
        thread_id,
        "UPDATE threads SET goal = ?, goal_journey = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (goal, journey, thread_id),
    )


def set_thread_todo(thread_id: int, todo: str | None) -> dict[str, Any] | None:
    """CS9 — secondary checklist, separate from the diagnosis plan."""
    return _update_thread(
        thread_id,
        "UPDATE threads SET todo = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (todo, thread_id),
    )


def set_thread_checklist_source(thread_id: int, source: str) -> dict[str, Any] | None:
    """CS9 — which markdown list GoalBar and longrun work: `plan` or `todo`."""
    if source not in ("plan", "todo"):
        raise ValueError("checklist_source must be 'plan' or 'todo'")
    return _update_thread(
        thread_id,
        "UPDATE threads SET checklist_source = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (source, thread_id),
    )


def set_thread_autonomous(thread_id: int, on: bool) -> dict[str, Any] | None:
    """Turn this thread's autonomous mode on or off.

    One thread, one switch. There is deliberately no global setting: Max's
    own limit on this feature was "opt-in per thread and never the default",
    and a machine-wide toggle is the shape that quietly becomes the default.

    CS1: also mirrors onto `permission` (`write` when on, `ask` when off) so
    the ladder and the legacy bit stay aligned for callers that only flip
    the boolean.
    """
    from app import autonomy as _autonomy

    permission = "write" if on else "ask"
    return _update_thread(
        thread_id,
        "UPDATE threads SET autonomous = ?, permission = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (1 if on else 0, permission, thread_id),
    )


def set_thread_permission(thread_id: int, mode: str) -> dict[str, Any] | None:
    """Set the permission ladder step; derives `autonomous` for one release.

    AU6 — `full` forces `mode=build`. Full is zero-ask execution; plan mode
    only offers lookups + write_plan, so Full+plan is a contradiction that
    made models narrate blocked gates instead of calling measure_baseline.
    """
    from app import autonomy as _autonomy

    mode = _autonomy.normalise(mode)
    if mode == "full":
        return _update_thread(
            thread_id,
            "UPDATE threads SET permission = ?, autonomous = ?, mode = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (mode, 1, "build", thread_id),
        )
    return _update_thread(
        thread_id,
        "UPDATE threads SET permission = ?, autonomous = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (mode, 1 if _autonomy.autonomous_from_permission(mode) else 0, thread_id),
    )


def set_thread_baseline_provider(
    thread_id: int, provider_id: int | None
) -> dict[str, Any] | None:
    """AU3 — which local connection baseline scoring should use for this thread."""
    return _update_thread(
        thread_id,
        "UPDATE threads SET baseline_provider_id = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (provider_id, thread_id),
    )


def set_thread_baseline_model(
    thread_id: int, model: str | None
) -> dict[str, Any] | None:
    """Which LOCAL model the baseline is measured on, by name; None unpins."""
    return _update_thread(
        thread_id,
        "UPDATE threads SET baseline_model = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (model, thread_id),
    )


def set_thread_mode(thread_id: int, mode: str) -> dict[str, Any] | None:
    """Put this thread in `plan` or `build`. `None` when it does not exist.

    A MODE IS SET BY A PERSON. There is no caller that derives one from the
    question, and `app/modes.py` says why: matching on the question is the
    road `conductor.standing_brief` rejected twice. This function is reached
    from the control in the app bar and from nowhere else.

    AU6 — entering `plan` forces `permission=ask` (mirrors ModeSwitch). Plan
    is consultation; keeping Full while in plan left measure tools unloaded.
    """
    from app import autonomy as _autonomy

    if not modes.is_a_mode(mode):
        raise ValueError(
            "mode must be one of " + ", ".join(sorted(modes.MODES))
            + "; got " + repr(mode)
        )
    if modes.normalise(mode) == "plan":
        return _update_thread(
            thread_id,
            "UPDATE threads SET mode = ?, permission = ?, autonomous = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            ("plan", "ask", 0, thread_id),
        )
    return _update_thread(
        thread_id,
        "UPDATE threads SET mode = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE id = ?",
        (mode, thread_id),
    )


def set_thread_plan(thread_id: int, plan: str | None, *, mirror: bool = True) -> dict[str, Any] | None:
    """Write the agreed plan, or clear it with `None`.

    Not `goal`, and the difference is the point. `goal` is the person's own
    words for what the thread is for, set once and never a model's paraphrase
    (migration v013). A plan is the steps, it is rewritten every time planning
    iterates, and in `build` it is carried into the brief as the thing being
    executed.
    """
    text = None if plan is None else str(plan).strip() or None
    row = _update_thread(
        thread_id,
        "UPDATE threads SET plan = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE id = ?",
        (text, thread_id),
    )
    # THE FILE IS THE PLAN. Every write of the column is mirrored to
    # `<project root>/harness-plans/thread-<id>-plan.md` (app/planfile.py);
    # `mirror=False` is the adoption path writing what it just read.
    if row is not None and mirror:
        from app import planfile  # lazy: planfile reads projects through db and calls back here

        planfile.mirror(row, text)
    return row


def archive_thread(thread_id: int) -> dict[str, Any] | None:
    """Archive one thread. `None` when it does not exist.

    Not deletion. The transcript is the artifact; archiving takes a thread out
    of the rail and leaves every message and every event exactly where they
    are, which is why this writes a timestamp rather than issuing a `DELETE`.
    """
    return _update_thread(
        thread_id,
        "UPDATE threads SET archived_at = CURRENT_TIMESTAMP WHERE id = ?",
        (thread_id,),
    )


#: Every table that hangs a row off a thread WITHOUT `ON DELETE CASCADE`.
#: `messages`, `storms`, `eval_runs`, `prompt_lines`, `retrieval_indexes` and
#: `agent_runs` all declare the cascade and go with the thread row; these four
#: were written before anyone deleted a thread and carry a bare `thread_id`.
#: `messages_fts` follows `messages` through its own AFTER DELETE trigger.
THREAD_TABLES_WITHOUT_CASCADE = ("contexts", "quarantined_facts", "fact_evidence", "events", "plan_files")


def delete_thread(thread_id: int) -> dict[str, Any] | None:
    """Delete one thread and every row that belongs to it. `None` when absent.

    Max, 2026-09-12: *"add a delete thread and project/file so that old
    projects that people really don't work with aren't just infinitely
    archived adding space, but they are deleted and removed."* Archive stays
    the reversible door; this is the other one. It removes the database rows
    only - nothing on disk is touched, an attached folder or file is the
    person's and was never copied in - and it returns what it removed, by
    table, so the caller can say so. The one row that survives is written by
    the caller: a `thread.deleted` event on the project, with the title, so
    the ledger still says the conversation existed.
    """
    ensure_tables()
    with db.session() as connection:
        row = connection.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
        if row is None:
            return None
        removed: dict[str, int] = {}
        have = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table in THREAD_TABLES_WITHOUT_CASCADE:
            if table not in have:
                continue
            columns = {r[1] for r in connection.execute(f"PRAGMA table_info({table})")}
            if "thread_id" not in columns:
                continue
            removed[table] = connection.execute(
                f"DELETE FROM {table} WHERE thread_id = ?", (thread_id,)
            ).rowcount
        removed["messages"] = connection.execute(
            "SELECT COUNT(*) FROM messages WHERE thread_id = ?", (thread_id,)
        ).fetchone()[0]
        connection.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
    return {"thread": dict(row), "removed": removed}


def move_thread(thread_id: int, project_id: int) -> dict[str, Any] | None:
    """Move one thread to another project. `None` when the thread is not there.

    The project is not checked here - the foreign key does that, and the caller
    that wants a 404 rather than an `IntegrityError` looks the project up
    first. See `app/main.py`.
    """
    return _update_thread(
        thread_id,
        "UPDATE threads SET project_id = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE id = ?",
        (project_id, thread_id),
    )


def _update_thread(
    thread_id: int, statement: str, parameters: tuple[Any, ...]
) -> dict[str, Any] | None:
    """One `UPDATE` against one thread, returning the row or `None`.

    The existence check and the update share a transaction so that "does it
    exist" and "change it" cannot disagree, and the three callers above share
    this so the `None` contract is written once rather than three times.
    """
    ensure_tables()
    with db.session() as connection:
        exists = connection.execute(
            "SELECT 1 FROM threads WHERE id = ?", (thread_id,)
        ).fetchone()
        if exists is None:
            return None
        connection.execute(statement, parameters)
        row = connection.execute(
            "SELECT * FROM threads WHERE id = ?", (thread_id,)
        ).fetchone()
    return dict(row)


def adopt_ledger(thread_id: int, ledger: str) -> dict[str, Any] | None:
    """Record the domain this conversation turned out to be in.

    `create_thread`'s docstring says the `ledger` parameter exists "so the
    engine can record what it inferred… not so a chooser can be built on top of
    it", and until 2026-08-28 nothing ever inferred - so every conversation ran
    the default and the second ledger was unreachable by any person.

    THIS IS THAT RECORDING, AND ITS GUARD IS THE WHOLE OF ITS SAFETY. It refuses
    a thread that has ANY fact evidence, because `evidence.ledger_for_thread` is
    right that "a thread that named a ledger must never quietly get a different
    one" - and a thread that has measured something has named one by using it.
    A thread with no evidence has invested nothing: no fact was recorded under
    the old domain, so nothing is orphaned and nothing changes meaning.

    The move is an EVENT as well as a column, because a domain the engine chose
    is a thing the person is entitled to see and disagree with. That is the same
    rule every inferred value in this product follows.

    Returns the updated row, or `None` when it refused - and the caller treats
    `None` as "leave the wall where it is".
    """
    from app.tools import evidence

    # NO CONVERSATION, NOTHING TO ADOPT. `Registry.call` is reached with
    # `thread_id=None` by callers that genuinely have no thread - the same case
    # `evidence.ledger_for_thread` guards, and it is guarded the same way here.
    # Found by `test_a_run_with_no_conversation_never_gets_as_far_as_recording`,
    # whose whole point is that a call with no thread must not get this far.
    if isinstance(thread_id, bool) or not isinstance(thread_id, int) or thread_id <= 0:
        return None

    named = str(ledger or "").strip()
    if not named:
        return None
    diagnosis.spec_at(named)  # refuse a ledger this build cannot read

    row = get_thread(int(thread_id))
    if row is None or str(row.get("ledger") or "") == named:
        return None
    if str(row.get("ledger") or "") != diagnosis.DEFAULT_LEDGER:
        # A THREAD ON A NON-DEFAULT LEDGER WAS NAMED, AND A NAMED THREAD NEVER
        # MOVES. The column cannot tell a ledger somebody chose from the one
        # that was defaulted into it - so the default is treated as the only
        # absence of a choice, and everything else as a choice. That is the
        # narrow reading, and it is the one that keeps
        # `evidence.ledger_for_thread`'s rule literally true: "a thread that
        # said it was an AI-engineering thread must never quietly get the ML
        # one."
        return None
    if evidence.rows_for(int(thread_id)):
        # Something has been measured under the ledger this thread is on.
        # Moving now would leave those rows describing a domain the thread no
        # longer runs, and `assemble_facts` would silently drop every one of
        # them - a conversation that forgot what it had looked at.
        return None

    # `_update_thread` rather than raw SQL, because its docstring says why it
    # exists: the existence check and the update share a transaction so "does it
    # exist" and "change it" cannot disagree, and the `None` contract is written
    # once. This is its fourth caller.
    updated = _update_thread(
        int(thread_id), "UPDATE threads SET ledger = ? WHERE id = ?", (named, int(thread_id))
    )
    if updated is None:
        return None
    append(
        "thread.ledger.inferred",
        {"from": row.get("ledger"), "to": named},
        thread_id=int(thread_id),
        project_id=row.get("project_id"),
    )
    return updated


def get_thread(thread_id: int) -> dict[str, Any] | None:
    ensure_tables()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM threads WHERE id = ?", (thread_id,)
        ).fetchone()
    return None if row is None else dict(row)


def add_message(
    thread_id: int,
    role: str,
    content: str,
    tool_calls_json: str | None = None,
) -> dict[str, Any] | None:
    """Append one message. `None` when the thread does not exist.

    Returning `None` rather than raising matches `db.add_metric`, which is the
    house style for "you named a parent row that is not there".
    """
    ensure_tables()
    with db.session() as connection:
        exists = connection.execute(
            "SELECT 1 FROM threads WHERE id = ?", (thread_id,)
        ).fetchone()
        if exists is None:
            return None
        cursor = connection.execute(
            "INSERT INTO messages (thread_id, role, content, tool_calls_json) "
            "VALUES (?, ?, ?, ?)",
            (thread_id, role, content, tool_calls_json),
        )
        connection.execute(
            "UPDATE threads SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (thread_id,),
        )
        row = connection.execute(
            "SELECT * FROM messages WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def messages_for(thread_id: int) -> list[dict[str, Any]]:
    """Oldest first. A transcript read newest-first is unreadable.

    Closed to a tool that can stamp MEASURED - see `since()`.
    """
    _refuse_a_minting_reader("messages_for")
    ensure_tables()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT * FROM messages WHERE thread_id = ? ORDER BY id ASC",
            (thread_id,),
        ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# The event log - the spine.


def append(
    kind: str,
    payload: dict[str, Any],
    *,
    project_id: int | None = None,
    thread_id: int | None = None,
    run_id: int | None = None,
) -> dict[str, Any]:
    """Write one event and return it, id included.

    This is the only way an event is created, and it returns only once the row
    is committed. Callers stream the dict this returns; they never stream
    something and then write it, because that ordering loses whatever was in
    flight when the process died.
    """
    ensure_tables()
    body = json.dumps(payload)
    with db.session() as connection:
        cursor = connection.execute(
            "INSERT INTO events (project_id, thread_id, run_id, kind, payload_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, thread_id, run_id, kind, body),
        )
        row = connection.execute(
            "SELECT * FROM events WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return _decode(row)


def parse_scope(scope: str) -> tuple[str, int]:
    """`"thread:7"` -> `("thread_id", 7)`. Raises `ValueError` otherwise."""
    kind, separator, raw = str(scope).partition(":")
    if not separator:
        raise ValueError(f"scope must be '<kind>:<id>', got {scope!r}")
    if kind not in SCOPE_COLUMNS:
        raise ValueError(
            f"unknown scope kind {kind!r}; expected one of "
            f"{', '.join(sorted(SCOPE_COLUMNS))}"
        )
    try:
        target = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"scope id must be an integer, got {raw!r}") from None
    return SCOPE_COLUMNS[kind], target


def _refuse_a_minting_reader(reader: str) -> None:
    """WALL 3, AT THE SECOND DOOR. The transcript is a record of what was said.

    `app/tools/evidence.py` shuts the claim ledger to a tool that is holding a
    measuring instrument, because reading a claim and re-stamping it MEASURED is
    laundering. The claim ledger was not the only place a model's numbers live.

    `conductor._run_tool` appends a `tool.call` event carrying `call.name` and
    `call.arguments` VERBATIM, scoped to the thread, before it runs anything. So
    every number a model has ever put in a tool call is sitting in this table,
    in the same database, at thread scope - and a minting handler that reads it
    back gets the model's own claim with nothing marked on it, because it went
    through JSON and SQLite on the way. That is route 09 in
    `tests/test_laundering_routes.py`.

    The same sentence therefore applies to the same records: a tool that can
    stamp does not get to read what anybody said. Nothing in the product loses
    anything by it - `since()` is called by the SSE endpoint and `messages_for()`
    by the conductor when it builds a conversation, and neither of those runs
    inside a tool handler.

    Imported inside the function on purpose: `app.tools` imports this module, so
    a module-level import would be a cycle.
    """
    from app.tools import evidence

    evidence.refuse_a_minting_reader(reader, "the transcript")


def latest_id(scope: str) -> int:
    """The newest event id in `scope`, or 0. A cursor, not a payload.

    `app/longrun.py` takes one before a turn and reads the events after it,
    which is how a loop outside the conductor sees what that turn did without
    holding on to the generator it consumed.
    """
    column, target = parse_scope(scope)
    ensure_tables()
    with db.session() as connection:
        row = connection.execute(
            f"SELECT MAX(id) FROM events WHERE {column} = ?",  # noqa: S608 - column from a fixed dict
            (target,),
        ).fetchone()
    return int((row[0] if row else 0) or 0)


def since(scope: str, after: int = 0, limit: int = 500) -> list[dict[str, Any]]:
    """Events in `scope` with `id` strictly greater than `after`, oldest first.

    Strictly greater. `after` is what the client already has.

    Closed to a tool that can stamp MEASURED. See `_refuse_a_minting_reader`,
    and `_as_a_claim` for the half of that which a worker thread cannot walk
    round.
    """
    _refuse_a_minting_reader("since")
    column, target = parse_scope(scope)
    ensure_tables()
    with db.session() as connection:
        rows = connection.execute(
            f"SELECT * FROM events WHERE {column} = ? AND id > ? "  # noqa: S608 - column from a fixed dict
            "ORDER BY id ASC LIMIT ?",
            (target, int(after), int(limit)),
        ).fetchall()
    return [_as_a_claim(_decode(row)) for row in rows]


def since_all(after: int = 0, limit: int = 500) -> list[dict[str, Any]]:
    """Every event with `id` strictly greater than `after`, whatever its scope.

    `since()` answers for one scope because every client this file had was
    looking at one thread. OpenCode's event stream is not: their client opens
    ONE subscription for the whole server and sorts events into sessions
    itself, so `app/facade` needs the log in id order across every thread and
    project at once. Opening a scope per thread instead would be a query per
    thread per poll, and would still miss a thread created after the stream
    opened.

    THE SAME TWO WALLS AS `since()`, and they are not optional for a reader
    that sees more of the log rather than less: a minting reader is refused,
    and every payload comes back marked as something somebody said.
    """
    _refuse_a_minting_reader("since_all")
    ensure_tables()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT * FROM events WHERE id > ? ORDER BY id ASC LIMIT ?",
            (int(after), int(limit)),
        ).fetchall()
    return [_as_a_claim(_decode(row)) for row in rows]


def _as_a_claim(row: dict[str, Any]) -> dict[str, Any]:
    """Mark every number in a replayed payload as something somebody SAID.

    THE REFUSAL ABOVE IS NOT ENOUGH ON ITS OWN, and this was found by probing
    rather than by reasoning: `_refuse_a_minting_reader` reads a `ContextVar`,
    so a minting handler that starts a `threading.Thread` and reads the
    transcript on it meets no guard at all, and hands the number back to the
    main thread to be stamped. That is route 09 with three extra lines in it.

    A mark goes where a context does not. `app/tools/evidence.py` does the same
    thing to the claim ledger, for the same reason, and the sentence is the same
    for both: what a model put in a tool call is what a model said, and reading
    it back later does not turn it into a measurement.

    Only on the way OUT of the log. `append()` returns the row the conductor
    streams, and that is this process's own event on its way to a socket rather
    than anybody's claim coming back.
    """
    from app.tools import evidence

    row["payload"] = evidence.mark_as_a_claim(row["payload"])
    return row


def latest(kind: str, thread_id: int) -> dict[str, Any] | None:
    """The newest event of one kind on one thread, or `None`.

    `since()` answers "what has happened after id N", which is what a client
    reconnecting needs and is the wrong shape for "what did the LAST turn
    record": the caller would have to read the whole thread and keep the final
    match, and on a long thread that is a full scan and a `limit` to get wrong.
    One indexed lookup instead.

    THE SAME TWO WALLS `since()` HAS, and they are not optional here. A minting
    reader is refused, and the payload comes back through `_as_a_claim` - what a
    model put in a tool call is what a model SAID, and reading it back later does
    not turn it into a measurement. A reader of the log gets the log's rules
    whatever it happens to be reading it for.
    """
    _refuse_a_minting_reader("latest")
    ensure_tables()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM events WHERE thread_id = ? AND kind = ? "
            "ORDER BY id DESC LIMIT 1",
            (int(thread_id), str(kind)),
        ).fetchone()
    return None if row is None else _as_a_claim(_decode(row))


def last_event_id() -> int:
    """The highest id in the log, or 0 when there are none."""
    ensure_tables()
    with db.session() as connection:
        row = connection.execute(
            "SELECT COALESCE(MAX(id), 0) AS last FROM events"
        ).fetchone()
    return int(row["last"])


def fold_replay(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge adjacent `chat.delta` rows into one, for history only.

    Max, 2026-09-13: *"when I launch the app and open a chat it loads all the
    tokens and conversations from scratch... if we can fix that and remove
    latency, that'd be really cool."*

    MEASURED on his database: the busiest thread holds 3,294 events and 3,258
    of them are `chat.delta` - one per token fragment, 54 KB of text in three
    thousand frames. The bytes were never the problem; the frames were. Each
    one is an SSE parse, a Map write and a React render on a page that is
    replaying something that finished hours ago.

    So a REPLAY hands back the same text in one row per run of deltas. The
    transcript's own fold concatenates them anyway (`lib/transcript.ts`), so
    what the person reads is identical; the id carried is the LAST of the run,
    which is what a client must store to resume from. Rows are merged only
    when they are adjacent, from the same writer, and neither is a stream end -
    a delta with a different `written_by` is the harness speaking, and two
    voices never become one row.

    LIVE deltas are never folded: they arrive one at a time because that is
    what makes a reply look like it is being written.
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        payload = row.get("payload") or {}
        # `chat.reasoning` folds by the same rule, and never into a
        # `chat.delta`: thinking and the reply stay two parts.
        mergeable = (
            row.get("kind") in ("chat.delta", "chat.reasoning")
            and isinstance(payload.get("text"), str)
            and out
            and out[-1].get("kind") == row.get("kind")
            and (out[-1].get("payload") or {}).get("from_reasoning") == payload.get("from_reasoning")
            and (out[-1].get("payload") or {}).get("written_by") == payload.get("written_by")
            and (out[-1].get("payload") or {}).get("ending") == payload.get("ending")
        )
        if not mergeable:
            out.append(dict(row, payload=dict(payload)))
            continue
        last = out[-1]
        last["payload"]["text"] = str(last["payload"].get("text") or "") + payload["text"]
        last["id"] = row["id"]
    return out


def frame(row: dict[str, Any]) -> str:
    """One event as an SSE frame.

    The `id:` line is not decoration. It is the entire reason SSE was chosen
    over WebSockets: the browser stores it and sends it back as `Last-Event-ID`
    without being asked, so reconnection is the server answering a question
    rather than a hand-written protocol we have to keep correct.
    """
    return (
        f"id: {row['id']}\n"
        f"event: {row['kind']}\n"
        f"data: {json.dumps(row['payload'])}\n\n"
    )


def _decode(row: Any) -> dict[str, Any]:
    out = dict(row)
    out["payload"] = json.loads(out.pop("payload_json"))
    return out
