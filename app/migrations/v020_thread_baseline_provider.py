"""AU3 — which local provider baseline scoring should use for this thread."""

from __future__ import annotations

VERSION = 20

SQL = """
ALTER TABLE threads ADD COLUMN baseline_provider_id INTEGER;
"""

DOWN = """
-- SQLite cannot drop a column before 3.35 without a rewrite; leave it.
"""
