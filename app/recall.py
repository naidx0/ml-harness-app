"""Recall: every earlier conversation, searchable, with no model in the loop.

## What this was written from

Max, 2026-09-11, on the memory this product had: *"where is my consistent
memory system? it is rescanning every time."* And then, having read what
Hermes does: *"implement all 3 exact same systems in ours."* This is the first
of the three - Hermes' `session_search` (`tools/session_search_tool.py` in the
copy on his machine), rebuilt over this harness's own tables.

Hermes' shape, kept exactly: ONE tool, three calling modes told apart by which
arguments are present, no LLM anywhere, every shape returns actual messages
from the database.

  DISCOVER  pass `query`. FTS5 over the messages table, hits deduplicated by
            conversation, the top few conversations each with the snippet, a
            window of messages around the hit, and the conversation's
            opening and latest messages (Hermes' "bookends").
  SCROLL    pass `in_thread` + `around_message_id`. A window centred on
            that message, no search. To scroll, re-anchor on the first or
            last id the window returned.
  BROWSE    pass nothing. Recent conversations, newest first, with a preview.

## What is different, and why

* **Scoped to the project by default.** Hermes has one flat session history
  per profile; this product has projects, and a thread about the support
  tickets should not surface a thread about the design model unless asked.
  `scope="all"` widens it.
* **It is an index over tables that already exist.** `messages` is
  migration-managed (v004) and holds every user and assistant message of
  every thread since the product first ran; the index is a contentless
  FTS5 table over it that heals itself the way `contexts` does - created
  and back-filled on first use, kept current by triggers, no migration to
  forget.
* **Numbers that come back are quotations.** A figure in an earlier
  conversation was measured THEN, on that thread's ledger. The result says
  so in its `provenance` field, and the sentry treats what a tool returned
  the way it treats any tool result. Re-measuring is one call.

## What it will not do

Summarise. Hermes removed its own LLM summary path (their history note on
PR #20238 vs #26419) because a summary of a transcript is a second opinion
about what was said; this tool returns what was said.
"""

from __future__ import annotations

import re
from typing import Any

from app import db

#: Hermes scans this many FTS rows before deduplicating by conversation, so a
#: thread with many matching messages cannot starve the ones behind it.
SCAN_LIMIT = 300

#: How much of a message a result carries. A small local model reads these
#: inside a tool result inside a prompt; a whole transcript would be the
#: context window it is trying to save.
TEXT_LIMIT = 240

#: Messages either side of a hit or an anchor.
DEFAULT_WINDOW = 3
MAX_WINDOW = 8

#: Conversations a discover returns. Hermes defaults to a handful; five is
#: the ceiling because each carries a window and two bookends.
DEFAULT_LIMIT = 3
MAX_LIMIT = 5

#: The opening and the latest messages of a conversation, Hermes' bookends.
BOOKEND = 3

_INDEX_SCHEMA = (
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
        content,
        content='messages',
        content_rowid='id',
        tokenize='porter unicode61'
    );
    """,
    """
    CREATE TRIGGER IF NOT EXISTS messages_fts_ai AFTER INSERT ON messages BEGIN
        INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS messages_fts_ad AFTER DELETE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content)
            VALUES ('delete', old.id, old.content);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS messages_fts_au AFTER UPDATE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content)
            VALUES ('delete', old.id, old.content);
        INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
    END;
    """,
)


def ensure_recall_index() -> None:
    """Self-healing, in the same style as `context.ensure_contexts_table`.

    The first time anything asks, the index is created over the messages
    that already exist and back-filled from them; after that the triggers
    keep it current. A database that predates recall gets it on first use,
    and nothing has to remember to run a migration.
    """
    from app import events

    events.ensure_tables()
    with db.session() as connection:
        had = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'messages_fts'"
        ).fetchone()
        for statement in _INDEX_SCHEMA:
            connection.execute(statement)
        if not had:
            # The back-fill. `rebuild` reads every row of the content table
            # into the index, which is exactly the state the triggers would
            # have produced had they existed all along.
            connection.execute("INSERT INTO messages_fts(messages_fts) VALUES ('rebuild')")


# ---------------------------------------------------------------------------
# The query, made safe for FTS5
# ---------------------------------------------------------------------------

_TERM = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.'-]*")


def _terms(query: str) -> list[str]:
    """The words in a person's query, each safe to quote for FTS5.

    FTS5 has its own syntax - `AND`, `NOT`, `*`, `:` and unbalanced quotes
    are all operators or errors - and a model's query is prose. Every word
    is quoted, so nothing in it can be read as an operator.
    """
    return [term.replace('"', "") for term in _TERM.findall(str(query or ""))][:12]


def _match(terms: list[str], joiner: str) -> str:
    return f" {joiner} ".join(f'"{term}"' for term in terms)


def _clip(text: Any, limit: int = TEXT_LIMIT) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _row(message: Any) -> dict[str, Any]:
    return {
        "id": int(message["id"]),
        "role": message["role"],
        "text": _clip(message["content"]),
        "at": message["created_at"],
    }


# ---------------------------------------------------------------------------
# The three shapes
# ---------------------------------------------------------------------------


def _scope_clause(project_id: int | None, scope: str) -> tuple[str, list[Any]]:
    if scope == "all" or project_id is None:
        return "", []
    return " AND t.project_id = ?", [int(project_id)]


def discover(
    query: str,
    *,
    project_id: int | None = None,
    scope: str = "project",
    this_thread: int | None = None,
    limit: int = DEFAULT_LIMIT,
    window: int = DEFAULT_WINDOW,
) -> dict[str, Any]:
    """The conversations that talked about `query`, best first."""
    ensure_recall_index()
    terms = _terms(query)
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    window = max(0, min(int(window or DEFAULT_WINDOW), MAX_WINDOW))
    if not terms:
        return {"ok": False, "error": "empty_query", "query": query}
    clause, parameters = _scope_clause(project_id, scope)
    sql = (
        "SELECT m.id, m.thread_id, m.role, m.created_at, "
        "  snippet(messages_fts, 0, '[', ']', '…', 14) AS snippet, "
        "  bm25(messages_fts) AS rank, "
        "  t.title, t.project_id, t.archived_at, t.updated_at "
        "FROM messages_fts "
        "JOIN messages m ON m.id = messages_fts.rowid "
        "JOIN threads t ON t.id = m.thread_id "
        "WHERE messages_fts MATCH ?" + clause + " "
        "ORDER BY rank LIMIT ?"
    )
    with db.session() as connection:
        hits = []
        joiner_used = "AND"
        for joiner in ("AND", "OR"):
            hits = connection.execute(
                sql, [_match(terms, joiner), *parameters, SCAN_LIMIT]
            ).fetchall()
            joiner_used = joiner
            if hits or len(terms) == 1:
                break
        # ONE ENTRY PER CONVERSATION, its best hit. Hermes deduplicates by
        # session lineage for the same reason: a thread that said the word
        # forty times is one place to look, not forty.
        seen: set[int] = set()
        conversations = []
        for hit in hits:
            thread_id = int(hit["thread_id"])
            if thread_id in seen:
                continue
            seen.add(thread_id)
            conversations.append(_conversation(connection, hit, this_thread, window))
            if len(conversations) >= limit:
                break
    return {
        "ok": True,
        "query": query,
        "matched": " ".join(terms) + ("" if joiner_used == "AND" else " (any of these words)"),
        "scope": "this project" if clause else "every project",
        "conversations": conversations,
        "count": len(conversations),
        "provenance": (
            "quoted from earlier conversations in this harness - a number here was "
            "measured then, on that conversation; re-measure before relying on it"
        ),
    }


def _conversation(connection: Any, hit: Any, this_thread: int | None, window: int) -> dict[str, Any]:
    thread_id = int(hit["thread_id"])
    return {
        "thread_id": thread_id,
        "title": hit["title"],
        "project_id": hit["project_id"],
        "this_conversation": this_thread is not None and thread_id == int(this_thread),
        "archived": hit["archived_at"] is not None,
        "updated_at": hit["updated_at"],
        "hit": {"message_id": int(hit["id"]), "role": hit["role"], "snippet": hit["snippet"]},
        "around": _around(connection, thread_id, int(hit["id"]), window),
        "opening": _bookend(connection, thread_id, first=True),
        "latest": _bookend(connection, thread_id, first=False),
    }


def _around(connection: Any, thread_id: int, message_id: int, window: int) -> list[dict[str, Any]]:
    before = connection.execute(
        "SELECT * FROM messages WHERE thread_id = ? AND id < ? ORDER BY id DESC LIMIT ?",
        (thread_id, message_id, window),
    ).fetchall()
    at_and_after = connection.execute(
        "SELECT * FROM messages WHERE thread_id = ? AND id >= ? ORDER BY id ASC LIMIT ?",
        (thread_id, message_id, window + 1),
    ).fetchall()
    return [_row(m) for m in reversed(before)] + [_row(m) for m in at_and_after]


def _bookend(connection: Any, thread_id: int, *, first: bool) -> list[dict[str, Any]]:
    order = "ASC" if first else "DESC"
    rows = connection.execute(
        f"SELECT * FROM messages WHERE thread_id = ? ORDER BY id {order} LIMIT ?",
        (thread_id, BOOKEND),
    ).fetchall()
    return [_row(m) for m in (rows if first else reversed(rows))]


def scroll(
    in_thread: int, around_message_id: int, *, window: int = DEFAULT_WINDOW
) -> dict[str, Any]:
    """A window of one conversation centred on one message. No search."""
    ensure_recall_index()
    window = max(0, min(int(window or DEFAULT_WINDOW), MAX_WINDOW))
    with db.session() as connection:
        thread = connection.execute(
            "SELECT id, title, project_id FROM threads WHERE id = ?", (int(in_thread),)
        ).fetchone()
        if thread is None:
            return {"ok": False, "error": "no_such_thread", "thread_id": in_thread}
        anchor = connection.execute(
            "SELECT id FROM messages WHERE id = ? AND thread_id = ?",
            (int(around_message_id), int(in_thread)),
        ).fetchone()
        if anchor is None:
            return {
                "ok": False,
                "error": "no_such_message",
                "thread_id": in_thread,
                "message_id": around_message_id,
            }
        rows = _around(connection, int(in_thread), int(around_message_id), window)
    return {
        "ok": True,
        "thread_id": int(in_thread),
        "title": thread["title"],
        "messages": rows,
        "first_id": rows[0]["id"] if rows else None,
        "last_id": rows[-1]["id"] if rows else None,
        "next": "to scroll, call again with around_message_id set to first_id or last_id",
    }


def browse(
    *,
    project_id: int | None = None,
    scope: str = "project",
    this_thread: int | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Recent conversations, newest first, each with what it opened on."""
    ensure_recall_index()
    limit = max(1, min(int(limit or 10), 25))
    clause, parameters = _scope_clause(project_id, scope)
    with db.session() as connection:
        threads = connection.execute(
            "SELECT t.id, t.title, t.project_id, t.archived_at, t.updated_at, "
            "  (SELECT COUNT(*) FROM messages m WHERE m.thread_id = t.id) AS messages "
            "FROM threads t WHERE 1 = 1" + clause + " "
            "ORDER BY t.updated_at DESC LIMIT ?",
            [*parameters, limit],
        ).fetchall()
        out = []
        for thread in threads:
            opening = _bookend(connection, int(thread["id"]), first=True)
            out.append(
                {
                    "thread_id": int(thread["id"]),
                    "title": thread["title"],
                    "project_id": thread["project_id"],
                    "this_conversation": this_thread is not None and int(thread["id"]) == int(this_thread),
                    "archived": thread["archived_at"] is not None,
                    "updated_at": thread["updated_at"],
                    "messages": int(thread["messages"]),
                    "opened_with": opening[0]["text"] if opening else "",
                }
            )
    return {
        "ok": True,
        "scope": "this project" if clause else "every project",
        "conversations": out,
        "count": len(out),
    }
