"""A thread remembers its permission ladder step (ask / measure / write / full).

CS1, 2026-09-14: binary autonomous becomes four named modes. `autonomous` stays
derived (`write`/`full` → 1) so older readers keep working for one release.
"""

from __future__ import annotations

VERSION = 17

SQL = """
ALTER TABLE threads ADD COLUMN permission TEXT NOT NULL DEFAULT 'ask';
"""

DOWN = """
-- SQLite cannot drop a column before 3.35 without a rewrite; leave it.
"""
