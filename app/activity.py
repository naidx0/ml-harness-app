"""Which conversations are working right now, and what they are carrying.

Max, 2026-09-13: *"on the left chat side, we should have it so you can
actually see which sessions are running. So if I have a session running now
when I switch to another chat, I want to see a spinner or something, or the
context circle window should pop up on the chat side rail."*

A thread is WORKING when its newest `turn.started` is newer than its newest
`stream.end` - the turn began and has not ended. That is read off the event
log rather than tracked in memory, so it is true across windows, across a
reload, and for a run taking turns with nobody watching.

Everything here is one query per column, over MAX(id) grouped by thread. The
rail asks for this every few seconds with every conversation on screen, so it
must not be a query per row.
"""
from __future__ import annotations

import datetime as _datetime
import json
from typing import Any

from app import db, events
from app.contextwindow import KIND as CONTEXT_KIND

TURN_STARTED = "turn.started"

#: WHEN THIS ENGINE STARTED, as the events table writes its own timestamps
#: (UTC, `YYYY-MM-DD HH:MM:SS`). A turn is streamed by THIS process, so a
#: `turn.started` written before this process existed cannot be in flight -
#: its writer is gone. Without this, a turn interrupted by a crash or by the
#: app quitting leaves its thread marked "working" in the rail forever, which
#: is exactly what the first reading of this module showed for a thread whose
#: run had been killed an hour earlier. Same argument as
#: `longrun.reap_orphans`, and the same evidence.
ENGINE_STARTED = _datetime.datetime.now(_datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

#: The one index this read needs. Every other index on `events` is by thread
#: or project; this groups by KIND first, which without it is a full scan -
#: MEASURED at 2,891 ms over 10,839 rows on the owner's database, for a read
#: the rail wants every few seconds.
_INDEX = "CREATE INDEX IF NOT EXISTS idx_events_kind_thread ON events(kind, thread_id, id)"


def ensure_index() -> None:
    events.ensure_tables()
    with db.session() as connection:
        connection.execute(_INDEX)


def _newest(kind: str, since: str | None = None) -> dict[int, int]:
    """`{thread_id: newest event id}` for one kind, in one query."""
    ensure_index()
    where = "kind = ? AND thread_id IS NOT NULL"
    parameters: list[Any] = [kind]
    if since:
        where += " AND ts >= ?"
        parameters.append(since)
    with db.session() as connection:
        rows = connection.execute(
            f"SELECT thread_id, MAX(id) FROM events WHERE {where} GROUP BY thread_id",  # noqa: S608
            parameters,
        ).fetchall()
    return {int(row[0]): int(row[1]) for row in rows}


def _newest_payload(kind: str) -> dict[int, dict[str, Any]]:
    """The newest payload of one kind per thread, decoded. One query."""
    ensure_index()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT e.thread_id, e.payload_json FROM events e "
            "JOIN (SELECT thread_id, MAX(id) AS top FROM events "
            "      WHERE kind = ? AND thread_id IS NOT NULL GROUP BY thread_id) newest "
            "  ON newest.top = e.id",
            (kind,),
        ).fetchall()
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        try:
            out[int(row[0])] = json.loads(row[1])
        except (TypeError, ValueError):
            continue
    return out


def read() -> dict[str, Any]:
    """Every live thread that is working or has a run, and what it is carrying."""
    # Only turns this process could still be streaming - see ENGINE_STARTED.
    started = _newest(TURN_STARTED, since=ENGINE_STARTED)
    ended = _newest(events.END_KIND)
    contexts = _newest_payload(CONTEXT_KIND)

    runs: dict[int, dict[str, Any]] = {}
    from app import longrun

    longrun.ensure_table()
    with db.session() as connection:
        for row in connection.execute(
            "SELECT thread_id, state, turns, cap, stop_reason FROM long_runs"
        ):
            runs[int(row["thread_id"])] = {
                "state": row["state"],
                "turns": row["turns"],
                "cap": row["cap"],
                "stop_reason": row["stop_reason"],
            }

    threads: list[dict[str, Any]] = []
    for thread_id in sorted(set(started) | set(runs)):
        working = started.get(thread_id, 0) > ended.get(thread_id, 0)
        run = runs.get(thread_id)
        running = bool(run and run.get("state") == longrun.RUNNING)
        if not working and not running:
            continue
        context = contexts.get(thread_id) or {}
        threads.append(
            {
                "thread_id": thread_id,
                "working": working,
                "run": run if running else None,
                "tokens": int(context.get("total") or 0) or None,
                "window": context.get("window"),
            }
        )
    return {"threads": threads, "count": len(threads)}
