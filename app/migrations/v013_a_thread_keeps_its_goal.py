"""A thread keeps the goal it was opened for.

## The gap this closes, in the owner's words

2026-08-31: "it doesn't save your goal anywhere... the same way Codex and
Claude Code have a /goal... I kind of want a similar thing where it saves this
kind of goal idea. Instead of spamming questions and mixing itself up...
every time it works blindly."

The transcript already holds the person's first message, but nothing READ it
as the standing goal: every turn's prompt was assembled without it, so a
model three turns in had no cheaper way to know what the thread is FOR than
re-asking, which is exactly the question-spam the owner named.

## The two columns

`goal` — the person's own words for what this thread is for, verbatim. Set
once by the conductor from the first substantive user message, correctable
by the person through `POST /api/threads/{id}/goal`, and NEVER a model's
paraphrase: a model rewording the goal would be an ASSERTED claim standing
where the person's word belongs.

`goal_journey` — which playbook journey those words keyword-matched, when one
did. The match is `app/tools/knowledge.py`'s own scoring — pure code over the
curated playbook, no model in the loop — so it carries no more authority than
"these words matched these keywords", and it is stored so the prompt can say
it without re-deriving it every turn.

## Why nullable, unlike v011's ledger

"No goal has been recorded yet" is a real state a reader must be able to see:
a brand-new thread, or one whose first message was a greeting, has no goal,
and inventing one ("", or the title) would put words in the person's mouth.
v011's column could take a NOT NULL default because every existing thread WAS
already running that ledger; no such truth exists here.

## What this does to a database with nothing wrong with it

Adds two nullable columns. Measured on a fresh database and on one with
threads in it: `PRAGMA table_info(threads)` gains `goal TEXT` and
`goal_journey TEXT`, every existing row reads back NULL for both, and no
other table is touched.

SHIPPED. Never edit this file. A correction is a new migration.
"""

VERSION = 13

SQL = """
ALTER TABLE threads ADD COLUMN goal TEXT;
ALTER TABLE threads ADD COLUMN goal_journey TEXT;
"""
