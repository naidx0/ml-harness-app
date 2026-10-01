"""`GET /oc/api/event`: the log, live, in their envelope, for as long as they listen.

## What their client demands of this stream, read from their source

`createClientConnection2` (`@opencode/client` dist chunk `pty-handoff-ydhz1zrh`)
is the whole contract, and it is strict in three places:

1. **The first event must be `server.connected`, within two seconds.**
   `connectTimeout = 2000` aborts the request if the first `iterator.next()`
   has not resolved, and a first event of any other type fails the connection
   with "Event stream did not start with server.connected". So that frame is
   written before the log is read: all that precedes it is two single-row
   queries (the newest event id, and the connections' fingerprint).
2. **Something must arrive at least every 45 seconds.** `defaultIdleTimeout2
   = 45000` arms a watchdog that aborts with "Event stream stalled". What resets
   it is `onActivity`, which their SSE reader (`sse()` in the generated client)
   calls on EVERY chunk read from the body, before parsing - so an SSE comment
   line is activity even though it yields no event. Their schema defines no
   heartbeat event type (`server.connected` and `global.disposed` are the only
   server events), so the heartbeat is a comment, every `HEARTBEAT_SECONDS`.
3. **Each `data:` line is one whole envelope** - `{id, type, created,
   durable?, location?, data}` - parsed with `JSON.parse`. Their reader ignores
   the `id:` and `event:` lines; they are written anyway, because the OpenAPI
   document declares them and a browser `EventSource` would use the id.

## It stays open

The engine's own `/api/events` ends each response after 25 seconds and on
every live `stream.end`, and its client reconnects. Their client treats an
ended response as a disconnection to recover from, with a reconnect delay and
a status change on screen, so this stream does not end on its own: it ends
when the client goes away. `MAX_SECONDS` exists for tests, which need a stream
that finishes, and is `None` in the product.

## Resume

Their protocol calls the stream volatile - events during a disconnection are
missed, and their client re-reads state after reconnecting. This engine's log
is durable, so a `Last-Event-ID` naming an event this stream minted resumes
exactly after it, including in the middle of one engine row's expansion.
Without one, the stream starts at the newest row: history is what
`session.message.list` is for.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import time
from typing import Any, AsyncIterator

from app import events
from app.facade.translate import Translator, event_id, parse_event_id

#: Seconds between heartbeats. A third of their 45-second watchdog, so two
#: can be lost to a slow machine before the client gives up.
HEARTBEAT_SECONDS = 15.0

#: How often the log is asked for new rows when the last ask found none. The
#: same quarter-second `/api/events` uses.
POLL_SECONDS = 0.25

#: A bound on the stream's life, for tests only. `None` in the product.
MAX_SECONDS: float | None = None

#: How often the model connections are compared against the last look. Their
#: catalogs change only when a person edits a connection, and a second is
#: faster than anyone can switch windows to look.
CATALOG_SECONDS = 1.0

#: What their client re-reads when a connection changes. Each is an empty,
#: location-scoped event in their schema (`provider.js`, `model.js`,
#: `config.js`, and `integration.updated` in `@opencode/schema`'s event
#: manifest), and their store drops one that names no location.
#: `integration.updated` is here because a connection is also a credential of
#: a keyed preset (`app/facade/integrations.py`): their settings page reads
#: which presets are connected from `integration.list`.
CATALOG_EVENTS = ("provider.updated", "model.updated", "integration.updated", "config.updated")

_CONNECTIONS = itertools.count(1)


def frame(envelope: dict[str, Any]) -> str:
    """One envelope as one SSE frame."""
    return (
        f"id: {envelope['id']}\n"
        f"event: {envelope['type']}\n"
        f"data: {json.dumps(envelope, separators=(',', ':'))}\n\n"
    )


def connected(cursor: int) -> dict[str, Any]:
    """Their `server.connected`: ephemeral, empty data, an `evt_` id of its own."""
    return {
        "id": f"{event_id(cursor, 0)}c{next(_CONNECTIONS)}",
        "type": "server.connected",
        "created": int(time.time() * 1000),
        "data": {},
    }


def start_position(last_event_id: str | None) -> tuple[int, int]:
    """`(after row, skip through index)` for a new connection.

    A `Last-Event-ID` this stream minted resumes after that event: rows before
    its row are skipped, and in its row the events up to and including its
    index. Anything else - no header, a foreign id - starts live, at the
    newest row.
    """
    parsed = parse_event_id(last_event_id)
    if parsed is not None:
        row, index = parsed
        return row - 1, index
    return events.last_event_id(), -1


def catalog_changed(cursor: int) -> list[dict[str, Any]]:
    """Their three catalog events, once for every location a client may hold.

    Their store caches providers, models and config per location (directory),
    and each event invalidates only the location it names - so one is sent
    per project folder, which is every location this engine answers for.
    """
    from app import db
    from app.facade import sessions

    now = int(time.time() * 1000)
    out = []
    for project in db.list_projects():
        location = {"directory": sessions.directory_of(project)}
        for kind in CATALOG_EVENTS:
            out.append(
                {
                    "id": f"{event_id(cursor, 0)}p{next(_CONNECTIONS)}",
                    "type": kind,
                    "created": now,
                    "location": location,
                    "data": {},
                }
            )
    return out


async def frames(request: Any = None, last_event_id: str | None = None) -> AsyncIterator[str]:
    from app.facade import catalog

    after, skip_through = start_position(last_event_id)
    resume_row = after + 1 if skip_through >= 0 else None
    loop = asyncio.get_event_loop()
    started = loop.time()
    beat = started
    looked = started
    translator = Translator(prime=True)
    # The baseline is taken BEFORE the first frame, so a connection edited in
    # the instant after the client hears `server.connected` is still a change.
    connections = catalog.fingerprint()

    yield frame(connected(after))

    while True:
        rows = events.since_all(after, limit=500)
        for row in rows:
            after = int(row["id"])
            for envelope in translator.feed(row):
                if resume_row is not None and after == resume_row:
                    parsed = parse_event_id(envelope["id"])
                    if parsed is not None and parsed[1] <= skip_through:
                        continue
                yield frame(envelope)
            if resume_row is not None and after >= resume_row:
                resume_row = None
        if request is not None and await request.is_disconnected():
            return
        now = loop.time()
        if MAX_SECONDS is not None and now - started >= MAX_SECONDS:
            return
        if now - looked >= CATALOG_SECONDS:
            looked = now
            current = catalog.fingerprint()
            if current != connections:
                connections = current
                for envelope in catalog_changed(after):
                    yield frame(envelope)
        if now - beat >= HEARTBEAT_SECONDS:
            beat = now
            yield ": heartbeat\n\n"
        if not rows:
            await asyncio.sleep(POLL_SECONDS)
