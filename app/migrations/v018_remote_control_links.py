"""Remote-control share links for Approve and Stop (CS2).

Stores only sha256(token). The raw token is returned once at mint time and
never written to SQLite.
"""

from __future__ import annotations

VERSION = 18

SQL = """
CREATE TABLE IF NOT EXISTS remote_links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  capabilities TEXT NOT NULL DEFAULT 'approve,stop',
  label TEXT NOT NULL DEFAULT '',
  expires_at TEXT,
  revoked_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_remote_links_thread ON remote_links(thread_id);
"""

DOWN = """
DROP TABLE IF EXISTS remote_links;
"""
