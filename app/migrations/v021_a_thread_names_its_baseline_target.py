"""The local model a thread's baseline is measured on, by name.

Max, 2026-09-17: the model measured the baseline of itself because nothing
let it name the model it meant to train. v020 gave the thread a provider
id with a route and no door; this is the name, set by a tool.
"""

from __future__ import annotations

VERSION = 21

SQL = """
ALTER TABLE threads ADD COLUMN baseline_model TEXT;
"""
