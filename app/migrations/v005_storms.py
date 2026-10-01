"""5 - the approved contract gets a home that outlives the process.

A storm executes a build that a person approved. Two things therefore have to
survive the engine being killed, and they are different in kind:

**What was approved** is written once and never changes. That is the contract,
and this table is where it lives. `manifest_json` is the plan exactly as it was
shown - the same object `app/build.py` emits from `Build.as_dict()`, plus the
per-step contract fingerprints the executor checks each step against.
`fingerprint` is `Build.fingerprint()`, which is the hash of what the person
actually read.

**What has happened** is append-only and belongs in `events`, not here. There is
deliberately no `state` column on this table and no `UPDATE` anywhere in
`app/storm.py`: a storm's state is folded out of its own events, whose ids are
the SSE event ids, which is what makes a storm resumable for the same reason a
streamed turn is. A status column would be a second answer to the same question
and the two would disagree the first time a process died between the write and
the commit.

So the rows here are INSERT-only, exactly like `events`. That is the whole
design: one immutable record of what was promised, one append-only log of what
was done, and nothing that can be edited to make the two agree.

`thread_id` is a real foreign key because a storm without a conversation is an
orphan - the progress events are thread-scoped so the transcript shows the work
while it happens, and `docs/THE_PROPOSAL_LOOP.md` is explicit that nothing
blocks the conversation.

`declared_event_id` points at the `storm.declared` event. It is not the storm's
identity: the storm's identity is this row's autoincrement id, minted here so a
storm can be named in a URL before anything is streamed about it.

SHIPPED. Never edit this file. A correction is a new migration.
"""

VERSION = 5

SQL = """
CREATE TABLE IF NOT EXISTS storms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    build_id TEXT NOT NULL,
    title TEXT NOT NULL,
    for_outcome TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    declared_event_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_storms_thread ON storms(thread_id, id);
"""
