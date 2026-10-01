"""Curated memory: what a project already knows, and who the person is.

## What this was written from

Hermes' built-in memory (`tools/memory_tool.py` in the copy on the owner's
machine), rebuilt for a product that has projects. Hermes keeps two bounded
files - `MEMORY.md`, the agent's own notes, and `USER.md`, what it knows
about the person - as `§`-delimited entries, edited through ONE tool with
add / replace / remove, and injects both into the system prompt as a
snapshot. Max, 2026-09-11, having read it: *"implement all 3 exact same
systems in ours."* This is the second.

Kept exactly: two targets, the character limits (2,200 and 1,375 - Hermes'
numbers, characters rather than tokens because a character count is the
same for every model), one tool with three actions, replace and remove by a
short unique substring rather than an id, a refusal that says what is over
the limit rather than silently truncating, and the guidance (declarative
facts, nothing that will be stale in a week, procedures are not memory).

## What differs, and why

* **The notes are PER PROJECT.** Hermes has one `MEMORY.md` per profile.
  This product has projects, and "we ruled out renting a GPU" is true of
  the ticket router and not of the design model. The person's profile is
  one, as in Hermes - it is about them, not about a project.
* **It is a table, not a file.** Rows in this harness's own SQLite, healed
  on first use like `contexts` and the recall index. A file in the project
  folder would be Hermes' shape, and it would also be a file another tool
  could read as data and a place a model could write outside this door.
  The Memory pane shows and edits the same rows.
* **A number needs its origin.** Hermes will remember "VRAM is 8 GB" as a
  fact. Here a remembered number is not a measured one, so an entry with a
  figure in it must say where the figure came from - `measured`, `stated`,
  `declared` or `defaulted`, the same four words every other number in this
  product carries - or it is refused, with the reason. The sentry then
  treats the block the way it treats the brief: a model quoting it is
  quoting us, and a model saying an instrument ran NOW when it ran then is
  still stopped.

## What it will not do

Write itself. Nothing here extracts memory from a transcript; the model
calls `remember` when it has learned something durable, exactly as Hermes'
model does, and the person edits the same rows in the pane. A memory nobody
chose to write is a memory nobody can vouch for.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app import db

#: Hermes' own limits, in characters.
LIMITS: dict[str, int] = {"project": 2200, "user": 1375}

TARGETS = ("project", "user")
ACTIONS = ("add", "replace", "remove")

#: Hermes' entry delimiter, kept for the pane's text form and for anyone
#: who exports the rows.
DELIMITER = "\n§\n"

#: The four words a number carries in this product. An entry with a figure
#: and none of them is a remembered number, which is the thing this product
#: refuses to have.
ORIGIN_WORDS = ("measured", "stated", "declared", "defaulted")
#: The provenance tails this module writes itself. See `a_number_without_its_origin`.
_THREAD_TAIL = re.compile(r"\((?:from )?thread \d+\)|\(stated by the person(?:, thread \d+)?\)", re.IGNORECASE)

_NUMBER = re.compile(r"(?<![A-Za-z_])\d+(?:[.,]\d+)?")
#: Numbers that are not readings: a date, a version, a model size in a name
#: (`granite4`, `7b`, `2026-09-11`, `v0.1.0`, `RTX 2060`).
_NOT_A_READING = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|\bv?\d+\.\d+\.\d+\b|\b\d+[bB]\b|\b(?:RTX|GTX|A|H|L)\s?\d{3,4}\b|[A-Za-z]\d+"
)

_SCHEMA = """
    CREATE TABLE IF NOT EXISTS memory_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target TEXT NOT NULL,
        project_id INTEGER,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
"""


def ensure_memory_table() -> None:
    """Self-healing, the `contexts` rule: created the first time anything asks."""
    with db.session() as connection:
        connection.execute(_SCHEMA)


def _scope(target: str, project_id: int | None) -> tuple[str, list[Any]]:
    if target == "user":
        return "target = 'user'", []
    return "target = 'project' AND project_id = ?", [int(project_id)]


def entries(target: str, project_id: int | None = None) -> list[dict[str, Any]]:
    """The entries of one target, oldest first."""
    _check_target(target, project_id)
    ensure_memory_table()
    where, parameters = _scope(target, project_id)
    with db.session() as connection:
        rows = connection.execute(
            f"SELECT * FROM memory_entries WHERE {where} ORDER BY id ASC", parameters
        ).fetchall()
    return [dict(row) for row in rows]


def used(target: str, project_id: int | None = None) -> int:
    """Characters in use, counted the way Hermes counts: entries plus delimiters."""
    return len(as_text(target, project_id))


def as_text(target: str, project_id: int | None = None) -> str:
    """The target as one `§`-delimited text - the pane's edit form."""
    return DELIMITER.join(row["content"] for row in entries(target, project_id))


def _check_target(target: str, project_id: int | None) -> None:
    if target not in TARGETS:
        raise ValueError(f"target must be one of {TARGETS}, not {target!r}")
    if target == "project" and project_id is None:
        raise ValueError("a project memory needs a project_id")


def a_number_without_its_origin(content: str) -> str | None:
    """The reason an entry is refused, or None.

    A figure in an entry must be accompanied by one of the four origin
    words. Dates, versions, model sizes and product names are not figures.
    """
    # A thread id in the harness's own provenance tail - "(from thread 7)",
    # "(thread 7)" - is a reference, not a reading, and is written by this
    # module, never by a model. Stripped before the figures are counted.
    stripped = _THREAD_TAIL.sub(" ", _NOT_A_READING.sub(" ", content))
    figures = _NUMBER.findall(stripped)
    if not figures:
        return None
    lowered = content.lower()
    if any(word in lowered for word in ORIGIN_WORDS):
        return None
    return (
        f"the entry carries a number ({figures[0]}) and does not say where it "
        "came from. A remembered number is not a measured one: write "
        "`measured`, `stated`, `declared` or `defaulted` beside it, with the "
        "instrument or the person it came from - or leave the figure out."
    )


def _clean(content: Any) -> str:
    return " ".join(str(content or "").split())


def add(target: str, content: str, project_id: int | None = None) -> dict[str, Any]:
    """Append one entry. Refused when over the limit, a duplicate, or a bare number."""
    _check_target(target, project_id)
    text = _clean(content)
    if not text:
        return {"ok": False, "error": "empty", "detail": "nothing to remember"}
    why = a_number_without_its_origin(text)
    if why:
        return {"ok": False, "error": "number_without_origin", "detail": why}
    current = entries(target, project_id)
    if any(row["content"].lower() == text.lower() for row in current):
        return {"ok": False, "error": "duplicate", "detail": "that entry is already there"}
    limit = LIMITS[target]
    after = len(DELIMITER.join([*(row["content"] for row in current), text]))
    if after > limit:
        return {
            "ok": False,
            "error": "over_limit",
            "detail": (
                f"{target} memory would be {after:,} of {limit:,} characters. Remove "
                "or replace an entry first - the ones least likely to still matter "
                "in a week."
            ),
            "used": used(target, project_id),
            "limit": limit,
        }
    with db.session() as connection:
        connection.execute(
            "INSERT INTO memory_entries(target, project_id, content) VALUES (?, ?, ?)",
            (target, None if target == "user" else int(project_id), text),
        )
    return {"ok": True, "action": "add", "entry": text, "used": after, "limit": limit}


def _match_one(target: str, project_id: int | None, match: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """The single entry containing `match`, or a refusal saying why not one."""
    needle = _clean(match).lower()
    if not needle:
        return None, {"ok": False, "error": "no_match", "detail": "say which entry, with a few words from it"}
    hits = [row for row in entries(target, project_id) if needle in row["content"].lower()]
    if not hits:
        return None, {"ok": False, "error": "no_match", "detail": f"no entry contains {match!r}"}
    if len(hits) > 1:
        return None, {
            "ok": False,
            "error": "ambiguous",
            "detail": f"{len(hits)} entries contain {match!r} - use a longer piece of the one you mean",
            "candidates": [row["content"][:80] for row in hits],
        }
    return hits[0], None


def replace(target: str, match: str, content: str, project_id: int | None = None) -> dict[str, Any]:
    """Rewrite the one entry that contains `match`."""
    _check_target(target, project_id)
    text = _clean(content)
    if not text:
        return {"ok": False, "error": "empty", "detail": "nothing to replace it with - use remove"}
    why = a_number_without_its_origin(text)
    if why:
        return {"ok": False, "error": "number_without_origin", "detail": why}
    row, refusal = _match_one(target, project_id, match)
    if refusal:
        return refusal
    others = [r["content"] for r in entries(target, project_id) if r["id"] != row["id"]]
    limit = LIMITS[target]
    after = len(DELIMITER.join([*others, text]))
    if after > limit:
        return {
            "ok": False,
            "error": "over_limit",
            "detail": f"{target} memory would be {after:,} of {limit:,} characters",
            "used": used(target, project_id),
            "limit": limit,
        }
    with db.session() as connection:
        connection.execute(
            "UPDATE memory_entries SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (text, row["id"]),
        )
    return {"ok": True, "action": "replace", "was": row["content"], "entry": text, "used": after, "limit": limit}


def remove(target: str, match: str, project_id: int | None = None) -> dict[str, Any]:
    """Delete the one entry that contains `match`."""
    _check_target(target, project_id)
    row, refusal = _match_one(target, project_id, match)
    if refusal:
        return refusal
    with db.session() as connection:
        connection.execute("DELETE FROM memory_entries WHERE id = ?", (row["id"],))
    return {"ok": True, "action": "remove", "was": row["content"], "used": used(target, project_id), "limit": LIMITS[target]}


def set_text(target: str, text: str, project_id: int | None = None) -> dict[str, Any]:
    """Replace a target wholesale from its `§`-delimited text - the pane's Save.

    The person's edit, so the number rule is applied per entry and the
    whole save is refused if any entry breaks it: a half-saved memory is
    worse than an unsaved one, and the pane keeps their text either way.
    """
    _check_target(target, project_id)
    parts = [_clean(part) for part in str(text or "").split("§")]
    parts = [part for part in parts if part]
    for part in parts:
        why = a_number_without_its_origin(part)
        if why:
            return {"ok": False, "error": "number_without_origin", "detail": why, "entry": part}
    joined = DELIMITER.join(parts)
    limit = LIMITS[target]
    if len(joined) > limit:
        return {"ok": False, "error": "over_limit", "detail": f"{len(joined):,} of {limit:,} characters", "used": len(joined), "limit": limit}
    ensure_memory_table()
    where, parameters = _scope(target, project_id)
    with db.session() as connection:
        connection.execute(f"DELETE FROM memory_entries WHERE {where}", parameters)
        for part in parts:
            connection.execute(
                "INSERT INTO memory_entries(target, project_id, content) VALUES (?, ?, ?)",
                (target, None if target == "user" else int(project_id), part),
            )
    return {"ok": True, "count": len(parts), "used": len(joined), "limit": limit}


# ---------------------------------------------------------------------------
# What the person asked to keep is kept, whether or not the model took the door
# ---------------------------------------------------------------------------

#: The shapes a person uses to ask that something be kept. MEASURED 2026-09-11,
#: six live turns: told "keep that in mind for every conversation in this
#: project - I don't want to repeat it", the owner's model called `remember`
#: in two of them and routed the other four to the standing-constraints file
#: or to reading the machine. A door the model takes one time in three is not
#: a promise to the person. So an explicit request is honoured by the harness
#: itself, in the person's own words, when the model did not write anything
#: that turn - the same rule `goal` follows: their sentence, verbatim, kept.
KEEP_REQUEST = re.compile(
    r"\b(remember\b|keep (?:this|that|it|these) in mind|keep in mind|"
    r"for (?:every|all|future|later) (?:conversation|chat|thread)s?\b|"
    r"don'?t (?:want to|make me) repeat|so i don'?t have to repeat|note (?:this|that) down)",
    re.IGNORECASE,
)

KEPT_PREFIX = "Stated by the person"
KEPT_CHARS = 320


def asks_to_keep(text: Any) -> bool:
    """Whether this message asks for something to be kept for later."""
    return bool(KEEP_REQUEST.search(str(text or "")))


def keep_what_was_asked(project_id: int, thread_id: int, text: Any) -> dict[str, Any]:
    """Keep the person's words, prefixed with their origin - `stated` - so the
    number rule is satisfied by construction: a figure in a sentence the
    person wrote is a figure the person stated."""
    words = _clean(text)
    if len(words) > KEPT_CHARS:
        words = words[: KEPT_CHARS - 1].rstrip() + "…"
    entry = f"{KEPT_PREFIX} (thread {int(thread_id)}): {words}"
    return add("project", entry, int(project_id))


# ---------------------------------------------------------------------------
# The prompt block
# ---------------------------------------------------------------------------

#: Hermes' headers, kept so a reader of both products recognises them.
HEADERS = {
    "project": "MEMORY (this project's notes)",
    "user": "USER PROFILE (who the person is)",
}


def render_block(project_id: int | None) -> str:
    """Both targets as the prompt shows them; empty when both are empty."""
    parts = []
    for target in TARGETS:
        rows = entries(target, project_id) if (target == "user" or project_id is not None) else []
        if not rows:
            continue
        lines = "\n".join(f"- {row['content']}" for row in rows)
        parts.append(f"{HEADERS[target]}\n{lines}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# What a turn taught, kept by the harness after the turn
# ---------------------------------------------------------------------------
#
# Max, 2026-09-12, after a day of conversations: *"right now the memory is
# showing zero. Project knows nothing. About me knows nothing... it seems to
# be reading context better, but it's not really saving anything. It's not
# condensing, saving anything."* Measured the day before: handed `remember`
# and told in so many words to keep a decision, the owner's model took the
# door one turn in three. A door the model takes one time in three fills no
# memory. Hermes' external providers solve this with `sync_turn` - a pass
# after every turn that extracts what is worth keeping - and this is that
# pass, through the same connection, with this product's rules at the door:
# a number needs its origin, an entry that is already there is not added
# twice, and the person can prune every row in the pane.

#: Off in tests (tests/support.py sets it), on in the product.
EXTRACTION_ENABLED = True
#: A reply shorter than this taught nothing worth a model call.
EXTRACT_FROM_REPLIES_OVER = 200
#: The most a turn may hand the extractor, per side, in characters.
EXTRACT_WINDOW = 2400
#: The most entries one turn may add, per target.
EXTRACT_PER_TURN = 3

#: MEASURED 2026-09-12 before this wording: told "NONE is the usual answer",
#: the owner's model answered NONE to an exchange that named the router
#: model, the data path and the label column. A small model takes a hint
#: about the usual answer as the answer. So the usual answer is not named;
#: what qualifies is, with one example of each kind, and NONE is for when
#: none of them is present.
_EXTRACT_SYSTEM = (
    "You maintain a small, durable memory for a project and a profile of the "
    "person, from one exchange of a conversation. Reply with JSON lines only - "
    'one object per line: {"target": "project" | "user", "fact": "..."}\n\n'
    "KEEP, as target \"project\": a decision and why (\"The router is "
    "granite4-hermes because it stays on the card.\"); an option ruled out and "
    "why; where the data lives (\"The tickets are at data/tickets-march.jsonl.\"); "
    "which file, column, model or folder was chosen (\"The label column is "
    "intent.\"). KEEP, as target \"user\": how the person likes to work "
    "(\"Max prefers short answers with no preamble.\"); a correction they made; "
    "something they said to stop asking.\n\n"
    "DO NOT keep: task progress, what this turn did, greetings, questions, "
    "hypotheticals, or anything that will be stale in a week. Write each fact "
    "as one declarative sentence, in the person's terms. A figure is kept only "
    "with the word that says where it came from - measured, stated, declared, "
    "defaulted - and the instrument or person; otherwise leave the figure out. "
    "Skip a fact that is already in MEMORY NOW. Reply NONE only when the "
    "exchange contains nothing of the kinds above."
)


def _clip(text: Any, limit: int) -> str:
    flat = str(text or "").strip()
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _facts_in(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    body = text.strip()
    if not body or body.upper().startswith("NONE"):
        return out
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", body, re.DOTALL)
    if fenced:
        body = "\n".join(fenced)
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        target = str(obj.get("target") or "").strip().lower()
        fact = " ".join(str(obj.get("fact") or "").split())
        if target in TARGETS and fact:
            out.append((target, fact))
    return out


def extract_after_turn(
    project_id: int | None,
    thread_id: int,
    asked: str,
    spoken: str,
    ask: Any,
) -> dict[str, Any]:
    """Keep what one exchange taught. `ask(system, user) -> str` is the
    connection, handed in so this stays a pure pass over text and records.

    Never raises: a dead connection or an unreadable reply is an empty pass,
    and the event the caller writes says how many were added.
    """
    report = {"added": [], "skipped": 0, "refused": 0, "asked": False}
    # The EXCHANGE has to carry something, not the reply alone: a withheld
    # reply still sits under a message in which the person said where the
    # data lives, and that is the half worth keeping.
    if len(str(asked or "").strip()) + len(str(spoken or "").strip()) < EXTRACT_FROM_REPLIES_OVER:
        return report
    known = render_block(project_id) or "Nothing saved yet."
    user = (
        "MEMORY NOW:\n" + known + "\n\n"
        "THE EXCHANGE:\n[person] " + _clip(asked, EXTRACT_WINDOW) + "\n\n[assistant] " + _clip(spoken, EXTRACT_WINDOW)
    )
    try:
        reply = ask(_EXTRACT_SYSTEM, user)
    except Exception:  # noqa: BLE001 - a dead connection is an empty pass
        return report
    report["asked"] = True
    counts = {"project": 0, "user": 0}
    existing = {
        _norm_for_dedupe(row["content"])
        for target in TARGETS
        for row in (entries(target, project_id) if (target == "user" or project_id is not None) else [])
    }
    for target, fact in _facts_in(str(reply or "")):
        if target == "project" and project_id is None:
            report["skipped"] += 1
            continue
        if counts[target] >= EXTRACT_PER_TURN:
            report["skipped"] += 1
            continue
        key = _norm_for_dedupe(fact)
        if key in existing or any(key in have or have in key for have in existing if len(have) > 24):
            report["skipped"] += 1
            continue
        entry = fact if target == "user" else f"{fact} (from thread {int(thread_id)})"
        result = add(target, entry, project_id if target == "project" else None)
        if result.get("error") == "number_without_origin" and _every_figure_is_the_persons(fact, asked):
            # "We'll hold out 40 rows, not 30" - the figures are the person's
            # own words, and the harness can say so where the extractor
            # forgot to: a STATED origin established by reading the message,
            # not by trusting the model.
            entry = (
                f"{fact} (stated by the person)"
                if target == "user"
                else f"{fact} (stated by the person, thread {int(thread_id)})"
            )
            result = add(target, entry, project_id if target == "project" else None)
        if result.get("ok"):
            counts[target] += 1
            existing.add(key)
            report["added"].append({"target": target, "fact": fact})
        else:
            report["refused"] += 1
    return report


def _every_figure_is_the_persons(fact: str, asked: str) -> bool:
    """Whether every figure in `fact` appears in the person's own message."""
    figures = _NUMBER.findall(_NOT_A_READING.sub(" ", fact))
    return bool(figures) and all(f in str(asked or "") for f in figures)


def _norm_for_dedupe(text: Any) -> str:
    flat = " ".join(str(text or "").lower().split())
    return re.sub(r"\s*\((?:from thread \d+|stated by the person(?:, thread \d+)?)\)$", "", flat)


def summary(project_id: int | None) -> dict[str, Any]:
    """What the pane and the API show: both targets, their text, their use."""
    out: dict[str, Any] = {}
    for target in TARGETS:
        if target == "project" and project_id is None:
            out[target] = {"entries": [], "text": "", "used": 0, "limit": LIMITS[target]}
            continue
        rows = entries(target, project_id)
        out[target] = {
            "entries": rows,
            "text": DELIMITER.join(row["content"] for row in rows),
            "used": used(target, project_id),
            "limit": LIMITS[target],
        }
    return out
