"""A thread is either planning or building, and it remembers which.

## What this is for, in the owner's words

2026-09-11: *"we should have selected modes like planning and building.
Planning is discussion with an ML expert who has a library of knowledge on the
harness to help him. Action or building full access mode is when the plan is
built, the model follows the plan, sets that as a goal function and executes on
it rigorously until it fulfils in full... same as the Cursor mode where you
plan, make a md list, overview, check, iterate - and then click build plan."*

## The transcript that caused it

A 7B was asked to help choose a use case and a training direction. It spent 241
seconds and all eight tool rounds inside the diagnosis machinery, had a
`run_diagnosis` call rejected on invented fact names, and closed by asserting a
gate the engine had not opened - which the conflict guard withheld. Every guard
worked. The person got nothing, because **the question was a design
conversation and every tool on offer answered "may we train yet".**

A mode is the structural answer to that. `plan` hands the model NO tools, so a
question about direction cannot be answered by walking a decision tree; there
is nothing to walk with.

## The two columns

`mode` - `'plan'` or `'build'`. `app/modes.py` holds what each offers and is
the only place that decides; nothing derives a mode from the question, because
matching on the question is the brittle road `standing_brief` already rejected
twice.

`plan` - the agreed markdown, nullable. It is NOT `goal`. `goal` is the
person's own words for what the thread is for, set once and never a model's
paraphrase (v013). The plan is the steps everyone agreed, it is rewritten every
time planning iterates, and in `build` it is carried into the brief as the
thing being executed.

## Why DEFAULT 'build' when the product wants planning first

The same reasoning v015 used for `NOT NULL DEFAULT 0`, pointed the other way.
Every thread that exists has been running with tools offered; defaulting them
to `plan` would silently take the tools away from work already in progress. So
the column default preserves what every existing thread has in fact been doing,
and **a NEW thread is opened in `plan` explicitly by whoever opens it** - which
is a decision at creation, visible in the code that makes threads, rather than
a default that reaches backwards through the table.

## What this does to a database with nothing wrong with it

Adds two columns. `PRAGMA table_info(threads)` gains `mode TEXT NOT NULL
DEFAULT 'build'` and `plan TEXT`; every existing thread reads back `build` and
a null plan, and no other table is touched.

SHIPPED. Never edit this file. A correction is a new migration.
"""

VERSION = 16

SQL = """
ALTER TABLE threads ADD COLUMN mode TEXT NOT NULL DEFAULT 'build';
ALTER TABLE threads ADD COLUMN plan TEXT;
"""
