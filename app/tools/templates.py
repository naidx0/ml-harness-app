"""Strip the boilerplate a corpus repeats, so a leak check measures content.

## The trap this exists for

`app/tools/data.py::check_split_leakage` shingles whole rows. When every row of
a training set and its eval carries the same fixed instruction, that instruction
dominates the shingles and **every pair scores as a near-duplicate.**

Measured on `evals/architecture-json`, 2026-09-10, by the lane that built it:

| comparison | on the full `prompt` | on the description alone |
|---|---|---|
| train vs held-out | 0.00 | 0.00 |
| train vs valid (carved) | **0.95** | **0.00** |

So a raw hit cannot be a refusal on its own. `start_training` refuses data that
leaks into the eval set its thread has measured against, and without this it
would refuse a legitimate fine-tune on any templated corpus - which is most of
them, and is exactly the corpus this project is about to train on.

## Three earlier versions of this were wrong, each in a way worth recording

1. **Line prefixes only.** The corpus APPENDS its instruction, so the shared
   text is a tail. A prefix-only helper reported "no template" on the very file
   it was written for.
2. **Raw character stripping.** Cutting characters off a JSONL line leaves text
   that is no longer JSON. `check_split_leakage` then read ZERO rows and
   reported the split clean - a check that silently measures nothing, arriving
   inside the wall built to prevent exactly that. Everything here rewrites rows
   AS JSON.
3. **One affix per row, from the longest string.** That picked `completion` (a
   JSON graph) over `prompt`, so it compared graphs and found no template. The
   template is PER FIELD: measured on that corpus, `prompt` shares a
   269-character tail and `completion` shares four.

## Per field, and per file

Per field because that is where the boilerplate lives. Per file because the two
sides name their fields differently - `prompt`/`completion` against
`input`/`expected` - so each file's own boilerplate is removed from its own
rows, which leaves the content on both sides.

Asymmetric stripping is only dangerous when it cuts CONTENT, and an affix shared
by every row of a field is not content. The guard is the threshold below: a few
characters in common is coincidence, hundreds is a template.
"""

from __future__ import annotations

import json
from pathlib import Path

#: A shared opening or closing at least this long is a template rather than
#: content. Below it, stripping would eat real text.
TEMPLATE_AFFIX_CHARS = 40

#: Rows the detector reads per file. It is looking for a constant, so a sample
#: settles it and a large corpus need not be held in memory.
SAMPLE_ROWS = 200


def _common_affixes(values: list[str]) -> tuple[str, str]:
    """The opening and closing every one of these strings shares."""
    if len(values) < 2:
        return "", ""
    head = values[0]
    for value in values[1:]:
        cut, limit = 0, min(len(head), len(value))
        while cut < limit and head[cut] == value[cut]:
            cut += 1
        head = head[:cut]
        if not head:
            break
    tail = values[0]
    for value in values[1:]:
        cut, limit = 0, min(len(tail), len(value))
        while cut < limit and tail[-1 - cut] == value[-1 - cut]:
            cut += 1
        tail = tail[len(tail) - cut:] if cut else ""
        if not tail:
            break
    return (
        head if len(head) >= TEMPLATE_AFFIX_CHARS else "",
        tail if len(tail) >= TEMPLATE_AFFIX_CHARS else "",
    )


def affixes_of(path: Path) -> dict[str, tuple[str, str]]:
    """Per field, the template this file repeats. `{}` when there is none."""
    seen: dict[str, list[str]] = {}
    try:
        with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
            taken = 0
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    for key, value in row.items():
                        if isinstance(value, str):
                            seen.setdefault(key, []).append(value)
                taken += 1
                if taken >= SAMPLE_ROWS:
                    break
    except OSError:
        return {}

    found: dict[str, tuple[str, str]] = {}
    for key, values in seen.items():
        head, tail = _common_affixes(values)
        if head or tail:
            found[key] = (head, tail)
    return found


def affixes_for_pair(left: Path, right: Path) -> tuple[dict, dict]:
    """Each file's template, with a fallback when one side is too small.

    A file needs at least two rows in a field before a repeated opening or
    closing can be detected in it. An eval set of ONE row therefore reports no
    template - and stripping one side while leaving the other is precisely what
    makes a real duplicate invisible, which is how the control for this caught
    an earlier version.

    So when one side finds nothing and the other does, the one that found
    something lends its affixes. They only apply where a row actually starts or
    ends with them, so lending cannot cut text that is not there.
    """
    mine, theirs = affixes_of(left), affixes_of(right)
    if mine and not theirs:
        theirs = dict(mine)
    elif theirs and not mine:
        mine = dict(theirs)
    return mine, theirs


def without_template(path: Path, affixes: dict, into: Path) -> Path:
    """A copy of `path` with each field's template removed, still valid JSONL."""
    with Path(path).open("r", encoding="utf-8", errors="replace") as source:
        with Path(into).open("w", encoding="utf-8") as target:
            for line in source:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except ValueError:
                    target.write(raw + chr(10))
                    continue
                if isinstance(row, dict):
                    trimmed = {}
                    for key, value in row.items():
                        head, tail = affixes.get(key, ("", ""))
                        if isinstance(value, str):
                            if head and value.startswith(head):
                                value = value[len(head):]
                            if tail and value.endswith(tail):
                                value = value[: len(value) - len(tail)]
                        trimmed[key] = value
                    row = trimmed
                target.write(json.dumps(row) + chr(10))
    return Path(into)
