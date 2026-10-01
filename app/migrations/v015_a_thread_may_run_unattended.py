"""A thread remembers whether the person put it in autonomous mode.

Max asked for this by name: a switch that pre-approves the gated steps so a
journey can run end to end without somebody clicking yes six times. He set its
limits in the same sentence - *"it is opt-in per thread and never the
default"* - and this column is where both halves live.

## Why NOT NULL DEFAULT 0, unlike v013's nullable goal

"Nobody has said" and "off" are the same state here, and must be: a thread
whose autonomy nobody has expressed an opinion about is a thread that asks
before it acts. There is no third reading to preserve, and a nullable column
would invite one - some later reader treating NULL as "inherit from
somewhere", which is exactly the silent-on-by-default this feature must never
have. Every existing thread reads back 0, which is what every existing thread
has in fact been doing.

The column governs approval only. It does not widen what tools a turn is
handed, does not touch the gates, and cannot make an inadmissible fact
admissible: `app/autonomy.py` holds the allowlist, and everything not named
there still stops and asks even with this set to 1.

## What this does to a database with nothing wrong with it

Adds one column. Measured on a fresh database and on one with threads in it:
`PRAGMA table_info(threads)` gains `autonomous INTEGER NOT NULL DEFAULT 0`,
every existing thread reads back 0, and no other table is touched.

SHIPPED. Never edit this file. A correction is a new migration.
"""

VERSION = 15

SQL = """
ALTER TABLE threads ADD COLUMN autonomous INTEGER NOT NULL DEFAULT 0;
"""
