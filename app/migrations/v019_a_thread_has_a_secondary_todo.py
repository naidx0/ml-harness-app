"""Secondary checklist column + which list GoalBar/longrun use (CS9)."""

from __future__ import annotations

VERSION = 19

SQL = """
ALTER TABLE threads ADD COLUMN todo TEXT;
ALTER TABLE threads ADD COLUMN checklist_source TEXT NOT NULL DEFAULT 'plan';
"""

DOWN = """
-- SQLite cannot drop a column before 3.35 without a rewrite; leave them.
"""
