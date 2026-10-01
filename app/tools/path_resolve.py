"""A missing path that plainly means one file in the workspace, found for a read.

Small models drop a folder from a path (`data/splits/eval.jsonl` for
`ml-principles-dataset/data/splits/eval.jsonl`) or guess the wrong one
(`data/splits/schema.json` for `ml-principles-dataset/data/schema.json`). Across
the 09-24 and 09-25 journeys read_context_file refused 162 of 200 calls, 130 of
them `not_found`, and one run spent its whole hour on them (F-path-1).

The rule, in order: the one file under the workspace whose relative path ends
with the request; else the one file with the request's name. Two or more is
ambiguous and nothing is read; the caller names the candidates instead. A
request for a folder (a trailing slash, or a name with no suffix) is never
resolved to a file. Only read-only tools use this: a write is never
redirected to a place nobody named.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

#: The machine's bookkeeping, not anybody's data (same set the registry skips).
_SKIP_DIRS = frozenset(
    {"node_modules", "__pycache__", "target", "dist", "build", "venv", ".venv"}
)

#: How many candidates a refusal names.
NAME_AT_MOST = 3

#: A workspace bigger than this is not walked: the answer would be slow and
#: the candidates too many to trust.
_WALK_AT_MOST = 20_000


def _files_under(root: Path) -> list[str]:
    found: list[str] = []
    for here, dirs, files in os.walk(root):
        dirs[:] = sorted(
            d for d in dirs if not d.startswith(".") and d not in _SKIP_DIRS
        )
        rel_here = Path(here).relative_to(root).parts
        for name in sorted(files):
            found.append("/".join((*rel_here, name)))
            if len(found) >= _WALK_AT_MOST:
                return found
    return found


def _relative_request(requested: str, root: Path) -> str | None:
    """The request as a path relative to root, or None when it points elsewhere."""
    text = os.path.expanduser(str(requested).strip()).replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    if os.path.isabs(text) or os.path.splitdrive(text)[0]:
        try:
            rel = os.path.relpath(os.path.normpath(text), os.path.normpath(root))
        except ValueError:
            return None
        rel = rel.replace("\\", "/")
        if rel.startswith(".."):
            return None
        return rel
    while text.startswith("./"):
        text = text[2:]
    if text.startswith("../"):
        return None
    return text


def resolve_missing(requested: str, root: str | os.PathLike[str]) -> dict[str, Any]:
    """What a missing `requested` most plainly means under `root`.

    Returns {"status": "resolved", "to": abs path, "by": "suffix"|"name"},
    {"status": "ambiguous", "candidates": [...]} or {"status": "none",
    "candidates": [...]} (candidates relative to root, at most NAME_AT_MOST).
    """
    base = Path(root)
    rel = _relative_request(requested, base)
    if rel is None or not base.is_dir():
        return {"status": "none", "candidates": []}
    if rel.endswith("/") or not rel.strip("/"):
        return {"status": "none", "candidates": []}
    rel = rel.strip("/")
    leaf = rel.rsplit("/", 1)[-1]
    if "." not in leaf.strip("."):
        # No suffix: a folder, or a tool name typed as a path.
        return {"status": "none", "candidates": []}
    files = _files_under(base)
    by_suffix = [f for f in files if f == rel or f.endswith("/" + rel)]
    if len(by_suffix) == 1:
        return {"status": "resolved", "to": str(base / by_suffix[0]), "by": "suffix"}
    if len(by_suffix) > 1:
        return {"status": "ambiguous", "candidates": by_suffix[:NAME_AT_MOST]}
    by_name = [f for f in files if f.rsplit("/", 1)[-1].lower() == leaf.lower()]
    if len(by_name) == 1:
        return {"status": "resolved", "to": str(base / by_name[0]), "by": "name"}
    if len(by_name) > 1:
        return {"status": "ambiguous", "candidates": by_name[:NAME_AT_MOST]}
    return {"status": "none", "candidates": []}
