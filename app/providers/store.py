"""The `providers` table. It has no `api_key` column and never will.

A provider row is everything about a model connection *except* the secret:
where it is, which adapter speaks to it, which model, whether it turned out to
be able to call tools. The key itself lives in the OS keychain and is fetched
for the duration of one request by `app/providers/secrets.py`. If you find
yourself adding a column for it, that is the invariant failing, not a gap in
the schema.

`tool_calling` is TEXT and not a boolean - `unknown` / `yes` / `no` - so that
"we have not probed yet" is a different stored value from "we probed and the
answer was no". The product says different things in those two states and a
boolean cannot hold the difference.

Self-healing `CREATE TABLE IF NOT EXISTS` on first use, matching
`db.ensure_intake_table`, so there is no migration step to forget.
"""

from __future__ import annotations

from typing import Any

from app import db
from app.providers import ADAPTERS, classify


TOOL_CALLING_STATES = ("unknown", "yes", "no")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    adapter TEXT NOT NULL,
    kind TEXT NOT NULL,
    tool_calling TEXT NOT NULL DEFAULT 'unknown',
    capability_detail TEXT NOT NULL DEFAULT '',
    ctx_len INTEGER,
    ctx_len_provenance TEXT NOT NULL DEFAULT 'defaulted',
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    effort TEXT NOT NULL DEFAULT 'default'
);
"""


#: HOW HARD THE MODEL THINKS, per connection. Max, 2026-09-12: "I'm not
#: seeing an effort system for our models." `default` sends nothing and the
#: server does what it does; `off` turns a thinking model's reasoning off;
#: `low` / `medium` / `high` ask for that much. What each adapter does with
#: it is the adapter's business - Ollama's `think`, an OpenAI-compatible
#: server's `reasoning_effort` - and a model that cannot think is not asked to.
EFFORTS = ("default", "off", "low", "medium", "high")


def ensure_table() -> None:
    with db.session() as connection:
        connection.executescript(_SCHEMA)
        # The column heals the way `contexts.thread_id` does: the table's
        # owner adds it on first ask, so a database from before it existed
        # gets it without a migration step somebody could forget.
        have = {row[1] for row in connection.execute("PRAGMA table_info(providers)")}
        if "effort" not in have:
            connection.execute(
                "ALTER TABLE providers ADD COLUMN effort TEXT NOT NULL DEFAULT 'default'"
            )


def create(name: str, base_url: str, model: str, adapter: str) -> dict[str, Any]:
    if adapter not in ADAPTERS:
        raise ValueError(
            f"unknown adapter {adapter!r}; expected one of {', '.join(ADAPTERS)}"
        )
    ensure_table()
    kind = classify(base_url)
    with db.session() as connection:
        cursor = connection.execute(
            "INSERT INTO providers (name, base_url, model, adapter, kind) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, base_url, model, adapter, kind),
        )
        row = connection.execute(
            "SELECT * FROM providers WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def list_all() -> list[dict[str, Any]]:
    ensure_table()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT * FROM providers ORDER BY id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get(provider_id: int) -> dict[str, Any] | None:
    ensure_table()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM providers WHERE id = ?", (provider_id,)
        ).fetchone()
    return None if row is None else dict(row)


def set_active(provider_id: int) -> dict[str, Any] | None:
    """Make one provider the active one. Exactly one, always.

    Both statements, in one transaction. Two active providers is the bug this
    ordering exists to make impossible.
    """
    ensure_table()
    with db.session() as connection:
        exists = connection.execute(
            "SELECT 1 FROM providers WHERE id = ?", (provider_id,)
        ).fetchone()
        if exists is None:
            return None
        connection.execute("UPDATE providers SET is_active = 0")
        connection.execute(
            "UPDATE providers SET is_active = 1 WHERE id = ?", (provider_id,)
        )
        row = connection.execute(
            "SELECT * FROM providers WHERE id = ?", (provider_id,)
        ).fetchone()
    return dict(row)


def active() -> dict[str, Any] | None:
    ensure_table()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM providers WHERE is_active = 1 LIMIT 1"
        ).fetchone()
    return None if row is None else dict(row)


#: The columns `update` will write. `kind` is derived from `base_url` and never
#: accepted from a caller; `tool_calling`, `capability_detail`, `ctx_len` and
#: `ctx_len_provenance` belong to the probe and are only ever written by
#: `record_capabilities`.
EDITABLE = ("name", "base_url", "model", "adapter", "effort")


def update(provider_id: int, **fields: Any) -> dict[str, Any] | None:
    """Edit a saved connection. `None` when there is no such row.

    A CHANGED ENDPOINT OR MODEL THROWS THE PROBE AWAY, and that is the whole
    reason this is not a two-line UPDATE. `tool_calling`, `capability_detail`,
    `ctx_len` and `ctx_len_provenance` are what the probe measured about ONE
    model on ONE server. Point the row at a different model and those figures
    describe something that is no longer there - a context length measured off
    `granite4-hermes` displayed beside `gpt-4o-mini` is an invented number with
    a `measured` tag on it, which invariant 3 forbids more strongly than it
    forbids a missing one. So they reset to the unprobed state and the
    interface goes back to saying nobody has asked yet.

    Renaming the row alone changes nothing that was measured, so it does not
    reset anything.
    """
    ensure_table()
    changes = {
        key: value
        for key, value in fields.items()
        if key in EDITABLE and value is not None
    }
    unknown = set(fields) - set(EDITABLE)
    if unknown:
        raise ValueError(
            f"not an editable provider column: {', '.join(sorted(unknown))}"
        )
    if "adapter" in changes and changes["adapter"] not in ADAPTERS:
        raise ValueError(
            f"unknown adapter {changes['adapter']!r}; "
            f"expected one of {', '.join(ADAPTERS)}"
        )
    if "effort" in changes and changes["effort"] not in EFFORTS:
        raise ValueError(
            f"unknown effort {changes['effort']!r}; expected one of {', '.join(EFFORTS)}"
        )

    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM providers WHERE id = ?", (provider_id,)
        ).fetchone()
        if row is None:
            return None
        if not changes:
            return dict(row)

        if "base_url" in changes:
            changes["kind"] = classify(changes["base_url"])

        # Which of the three could make the recorded capabilities describe a
        # different thing than the row now points at.
        stale = any(
            key in changes and changes[key] != row[key]
            for key in ("base_url", "model", "adapter")
        )
        if stale:
            changes.update(
                tool_calling="unknown",
                capability_detail="",
                ctx_len=None,
                ctx_len_provenance="defaulted",
            )

        assignments = ", ".join(f"{column} = ?" for column in changes)
        connection.execute(
            f"UPDATE providers SET {assignments} WHERE id = ?",  # noqa: S608
            (*changes.values(), provider_id),
        )
        updated = connection.execute(
            "SELECT * FROM providers WHERE id = ?", (provider_id,)
        ).fetchone()
    return dict(updated)


def delete(provider_id: int) -> dict[str, Any] | None:
    """Forget a connection. Returns the row as it was, or `None`.

    THE KEY IS NOT THIS MODULE'S TO DELETE, and that separation is deliberate:
    this file holds SQL and never touches the keychain, `secrets.py` holds the
    keychain and never touches SQL, and the route in `app/main.py` is the one
    place that calls both. Deleting a row without its key would leave a secret
    on the machine with nothing left pointing at it, so the route does the pair
    and this docstring says whose job the other half is.
    """
    ensure_table()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM providers WHERE id = ?", (provider_id,)
        ).fetchone()
        if row is None:
            return None
        connection.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
    return dict(row)


def record_capabilities(provider_id: int, caps: Any) -> dict[str, Any] | None:
    """Write what the probe found onto the row.

    `tool_calling` becomes `yes` / `no` when the probe answered, and stays
    `unknown` when it could not - a probe that failed has not learned that the
    model cannot call tools, and writing `no` would be recording a measurement
    nobody took.
    """
    ensure_table()
    state = (
        "unknown"
        if caps.tool_calling is None
        else ("yes" if caps.tool_calling else "no")
    )
    provenance = caps.provenance.get("ctx_len", "defaulted")
    with db.session() as connection:
        exists = connection.execute(
            "SELECT 1 FROM providers WHERE id = ?", (provider_id,)
        ).fetchone()
        if exists is None:
            return None
        connection.execute(
            "UPDATE providers SET tool_calling = ?, capability_detail = ?, "
            "ctx_len = ?, ctx_len_provenance = ? WHERE id = ?",
            (state, caps.detail, caps.ctx_len, provenance, provider_id),
        )
        row = connection.execute(
            "SELECT * FROM providers WHERE id = ?", (provider_id,)
        ).fetchone()
    return dict(row)
