"""What changed in the plan, as lines, small enough to put on an event.

Max, 2026-09-14: *"We should have the file diff - when the agent reads or
writes anything and does any change, like adding to the plan, we should have
that diff as an expandable feature to our thing."*

## Why a diff and not "the plan was rewritten"

`thread.plan_written` said `phases: 4, characters: 1180, steps_open: 9`. Every
one of those is true and none of them answers the question a person actually
has, which is *what did it just change*. A plan that goes from nine open steps
to nine open steps looks identical in that payload whether the model fixed a
typo or replaced every line.

## Why the diff lives on the event rather than being computed later

The transcript does not hold the plan at each point in its history - it holds
messages and tool rows. To draw "what changed" after the fact, something would
have to reconstruct every intermediate version of the document from the event
log and diff them in the browser. The change is known exactly once, at the
moment it is made, by the code making it. That is where it is recorded.

## Why lines and not characters

A plan is a markdown document of steps. The unit a person reads it in is the
line, the unit the harness works it in is the line (`- [ ]`), and a character
diff of a reordered list is noise. This is a line diff with two lines of
context, which is what makes an added step legible as *an added step* rather
than as an edit at offset 412.

## The bound, and why the payload can carry this at all

Events are replayed in full on every cold open, so a payload that can be
arbitrarily large is a payload that will one day be. `MOST_ROWS` caps it, the
count of what was cut is reported, and the plan file on disk remains the whole
truth for anyone who wants it. A capped diff that says it was capped is honest;
an uncapped one is a future outage.
"""
from __future__ import annotations

import difflib
from typing import Any

#: Lines of unchanged text kept either side of a change, so an added step is
#: read in the phase it joined rather than floating alone.
CONTEXT = 2

#: The most rows one change may put on one event. A plan is tens of lines and a
#: single write usually changes a handful; this is the ceiling for the case
#: where a model replaces the whole document.
MOST_ROWS = 80

#: Longer than any line worth reading in a rail-width pane. The full line is on
#: disk in the plan file.
LONGEST_LINE = 400


def rows_between(before: str | None, after: str | None) -> dict[str, Any]:
    """The line diff from `before` to `after`.

    Returns `{"rows": [...], "added": n, "removed": n, "clipped": n}` where each
    row is `{"kind": "ctx" | "add" | "del", "old": int | None, "cur": int | None,
    "text": str}` - `old` and `cur` being 1-based line numbers in the document
    that has the line, and `None` in the one that does not.

    An unchanged document returns no rows, which is how a caller tells "nothing
    happened" from "something happened": `park_step` on a step that does not
    match writes nothing, and its event should not claim a change.
    """
    old_lines = (before or "").splitlines()
    new_lines = (after or "").splitlines()
    if old_lines == new_lines:
        return {"rows": [], "added": 0, "removed": 0, "clipped": 0}

    rows: list[dict[str, Any]] = []
    added = 0
    removed = 0
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            span = list(range(i1, i2))
            #: Only the context either side of a change. The middle of a long
            #: unchanged run is what a diff exists to leave out.
            if len(span) <= CONTEXT * 2:
                keep = span
            else:
                keep = span[:CONTEXT] + span[-CONTEXT:]
            for index in keep:
                rows.append(
                    {
                        "kind": "ctx",
                        "old": index + 1,
                        "cur": j1 + (index - i1) + 1,
                        "text": _clip(old_lines[index]),
                    }
                )
            continue
        for index in range(i1, i2):
            removed += 1
            rows.append(
                {"kind": "del", "old": index + 1, "cur": None, "text": _clip(old_lines[index])}
            )
        for index in range(j1, j2):
            added += 1
            rows.append(
                {"kind": "add", "old": None, "cur": index + 1, "text": _clip(new_lines[index])}
            )

    clipped = 0
    if len(rows) > MOST_ROWS:
        clipped = len(rows) - MOST_ROWS
        rows = rows[:MOST_ROWS]
    return {"rows": rows, "added": added, "removed": removed, "clipped": clipped}


def _clip(line: str) -> str:
    text = line.rstrip()
    return text if len(text) <= LONGEST_LINE else text[: LONGEST_LINE - 1] + "…"
