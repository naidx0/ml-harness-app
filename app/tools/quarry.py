"""Carve rows out of raw files — the data-collection instrument the walk exposed.

## Why this tool exists, measured before it was built

The from-zero walk of 2026-08-30 proved the app could amplify
(`synthesize_rows`), verify (`check_split_leakage` caught 10 near-duplicate
leaks nothing else had seen), profile, measure and train — but the SEED rows
had to be made by hand scripts outside the app, because nothing registered
could turn a pointed-at folder of markdown, css and html into a rows file.
"Everything through the app" failed at exactly one instrument, and this is it.

## The law it inherits

Data is work: amplify structure by sampling, tag every row, never invent
content. Carving is the reading half of that law. Every row's `text` is a
VERBATIM excerpt of one file; the only authored strings are three fixed ask
templates that carry no facts (they name the file and the landmark, both read
off the file itself). Every row is tagged with `source`, `family` and the
landmark it was cut at, so a row can be walked back to its bytes.

## What it carves, deterministically

  markdown   every `## heading` section: q = write that section, a = the body
  css        every `--name: value;` custom property: q = the declared value
             of --name in that file, a = the value
  html       every top-level <section|header|footer|nav|style> block:
             q = write that block, a = the block

Each row carries BOTH shapes: `q`/`a` for eval carving and grading, and
`text` (q + newline + a) for completion training - so `carve_eval_set`,
`synthesize_rows`, `check_split_leakage` and the LoRA recipe all consume the
same file without a converter in anybody's editor.

## What it refuses

Paths outside the attached/project scope it was pointed at are not walked
(the walk starts at `root` and never follows `..`); binary and oversized
files are skipped and counted; an empty carve is an error naming what was
looked at, never an empty file that downstream tools would read as data.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


#: Files the carver reads, by suffix. A closed list on purpose: carving a
#: format is a claim the extractor understands it, and .py/.ts/.json carving
#: would be new families with their own landmarks - added deliberately or not
#: at all.
CARVABLE = {".md", ".css", ".html", ".htm"}

MAX_FILE_BYTES = 2_000_000
ANSWER_MAX = 1400
MIN_BODY = 40

MD_SECTION = re.compile(r"(?m)^## +(.+?)\n(.*?)(?=^## |\Z)", re.S)
CSS_DECL = re.compile(r"--([a-zA-Z0-9-]+)\s*:\s*([^;{}]+);")
#: A CSS comment, stripped before declarations are looked for.
#:
#: FOUND ON THE DESIGN-MODEL WALK. The declaration pattern was run over the raw
#: file, so it matched inside comments. A design system's stylesheet discusses
#: its own tokens in prose - "The composer around it stays a rounded RECTANGLE
#: at --r-18: a rounded rectangle with a circular send reads as a composer" -
#: and that produced the row: q "In shell.css, what value is declared for
#: --r-18?", answer "a rounded rectangle with a circular send reads as a
#: composer" - a fragment of that sentence, carrying a newline, offered as the
#: token's declared value.
#:
#: Every word of that answer is verbatim from the file, which is why no wall
#: caught it: the law those walls enforce is that nothing is invented, and
#: nothing was. It is still false. The row says a token's declared value is a
#: sentence about composers, and a model trained on it learns exactly that.
#: Verbatim is a floor, not a guarantee of meaning - the more prose a
#: stylesheet carries, the more of these it yields, so the best-documented
#: files are the ones that poison a corpus fastest.
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
HTML_BLOCK = re.compile(r"(?i)(?=<(?:section|header|footer|nav|style)\b)")
MANIFEST_NAME = "ml_harness_manifest.json"


def _a_section_cut_at(text: str, limit: int) -> str | None:
    """`text` trimmed to `limit`, or None when trimming would break it.

    FOUND ON THE CARVER WALK. Cutting a markdown section at a character count
    lands inside a fenced code block one time in twenty: measured on this
    repository's own docs, 13 of 259 carved sections ended with an odd number of
    ``` fences, so the "verbatim" answer was a code block that opens and never
    closes. The row is not false the way a comment quoted as a value is false -
    every character is from the file - but the question says "write the section"
    and the answer is a section that cannot be written, so a model trained on it
    learns to stop mid-fence.

    The honest cut is at a fence boundary. Where the text before the limit
    closes every fence it opened, that prefix is a whole answer and is used.
    Where it does not, this returns None and the caller carves no row at all: a
    section too long to carve whole is better missing than malformed, and
    silently repairing it by appending a fence would be writing something the
    file does not contain.
    """
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if cut.count("```") % 2 == 0:
        return cut
    # Fall back to the last point where the fences balance.
    closed = cut.rfind("```")
    while closed != -1:
        candidate = cut[:closed]
        if candidate.count("```") % 2 == 0 and len(candidate) >= MIN_BODY:
            return candidate.rstrip()
        closed = cut.rfind("```", 0, closed)
    return None


def _a_block_cut_at(text: str, limit: int) -> str | None:
    """`text` trimmed to `limit` at a tag boundary, or None if it cannot be.

    THE SAME DEFECT AS THE MARKDOWN FENCE, AND FAR MORE OF IT. Cutting an HTML
    block at a character count lands inside a tag most of the time: measured on
    this repository's own pages, **132 of 342 carved blocks - 38.6% - ended with
    a `<` after their last `>`**, so the answer stopped inside an element, like
    `...<span class="e`. The question says "write block N as that file builds
    it" and the answer is markup that does not parse.

    Cut after the last complete tag instead, and carve nothing when that leaves
    too little to be a block. Closing the element here would be writing markup
    the file does not contain, which is the line this whole module holds.
    """
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if cut.rfind("<") <= cut.rfind(">"):
        return cut
    trimmed = cut[: cut.rfind("<")].rstrip()
    return trimmed if len(trimmed) >= 200 else None


def _rows_from_markdown(rel: str, body: str) -> list[dict[str, Any]]:
    out = []
    for match in MD_SECTION.finditer(body):
        heading = match.group(1).strip()
        section = _a_section_cut_at(match.group(2).strip(), ANSWER_MAX)
        if section is None or len(section) < MIN_BODY:
            continue
        q = f'Write the section "## {heading}" of {rel}.'
        out.append({"q": q, "a": section, "family": "markdown_section",
                    "landmark": f"## {heading}"})
    return out


def custom_properties(body: str) -> list[tuple[str, str]]:
    """Every custom property this stylesheet actually declares, in order.

    A SCANNER RATHER THAN A PATTERN, AND THAT IS THE WHOLE POINT. What
    `--r-18` is worth is what a CSS declaration says it is, never what a
    substring search finds near the name. The pattern version matched three
    things that are not declarations, and each produced a row that was verbatim
    and false:

      * inside a comment - a stylesheet that documents its own tokens says
        "stays a rounded RECTANGLE at --r-18: a rounded rectangle with a
        circular send reads as a composer", and that carved as the value;
      * inside a string - `content: "--gap: 99px"` carved a SECOND row for a
        token that is also declared for real elsewhere, so the corpus held two
        different answers to one question and nothing could say which was the
        file's;
      * outside any block - `--loose: 42px;` at the top level of a file is not
        a declaration at all, because a custom property is only one inside a
        rule.

    The scanner walks the text once, holding three pieces of state: whether it
    is inside a comment, inside a string (and which quote opened it), and how
    deep it is in braces. A declaration is read only at depth one or more, and
    its value ends at the first `;` or `}` seen at that same depth. That is
    less than a full CSS parser and it is exactly the part this carve depends
    on; anything it cannot read it declines to carve rather than guessing.
    """
    found: list[tuple[str, str]] = []
    depth = 0
    index = 0
    length = len(body)
    while index < length:
        char = body[index]

        # Comments: skipped whole, at any depth.
        if char == "/" and body.startswith("/*", index):
            end = body.find("*/", index + 2)
            index = length if end == -1 else end + 2
            continue

        # Strings: skipped whole, escapes honoured, so their contents can never
        # be read as declarations.
        if char in "\"'":
            quote = char
            index += 1
            while index < length:
                if body[index] == "\\":
                    index += 2
                    continue
                if body[index] == quote:
                    index += 1
                    break
                index += 1
            continue

        if char == "{":
            depth += 1
            index += 1
            continue
        if char == "}":
            depth = max(0, depth - 1)
            index += 1
            continue

        # A custom property, only where one can legally be declared.
        if depth >= 1 and char == "-" and body.startswith("--", index):
            cursor = index + 2
            while cursor < length and (body[cursor].isalnum() or body[cursor] in "-_"):
                cursor += 1
            name = body[index + 2 : cursor]
            after = cursor
            while after < length and body[after] in " \t\r\n":
                after += 1
            if name and after < length and body[after] == ":":
                value_start = after + 1
                cursor = value_start
                # The value ends at the first `;` or `}` - but a value may
                # itself contain strings, comments and nested parentheses, and
                # a `;` inside any of those does not end it.
                parens = 0
                while cursor < length:
                    here = body[cursor]
                    if here == "/" and body.startswith("/*", cursor):
                        end = body.find("*/", cursor + 2)
                        cursor = length if end == -1 else end + 2
                        continue
                    if here in "\"'":
                        quote = here
                        cursor += 1
                        while cursor < length:
                            if body[cursor] == "\\":
                                cursor += 2
                                continue
                            if body[cursor] == quote:
                                cursor += 1
                                break
                            cursor += 1
                        continue
                    if here == "(":
                        parens += 1
                    elif here == ")":
                        parens = max(0, parens - 1)
                    elif parens == 0 and here in ";}":
                        break
                    cursor += 1
                # A comment inside a value is punctuation, not part of it:
                # `--h: 4px /* four */;` declares 4px. The scan above steps
                # over comments so a `;` inside one cannot end the value early;
                # this drops them from what is quoted back.
                value = CSS_COMMENT.sub(" ", body[value_start:cursor])
                value = " ".join(value.split())
                if value:
                    found.append((name, value))
                index = cursor
                continue

        index += 1
    return found


def _rows_from_css(rel: str, body: str) -> list[dict[str, Any]]:
    out = []
    for name, value in custom_properties(body):
        if len(value) > 120 or "var(" in value:
            continue
        q = f"In {rel}, what value is declared for --{name}? Reply with the value only."
        out.append({"q": q, "a": value, "family": "css_declaration",
                    "landmark": f"--{name}"})
    return out


def _rows_from_html(rel: str, body: str) -> list[dict[str, Any]]:
    out, n = [], 0
    for piece in HTML_BLOCK.split(body):
        piece = piece.strip()
        opening = re.match(r"<(\w+)", piece)
        if not opening or len(piece) < 200:
            continue
        n += 1
        tag = opening.group(1).lower()
        q = f"Write block {n} of {rel} (a <{tag}> element), as that file builds it."
        answer = _a_block_cut_at(piece, ANSWER_MAX)
        if answer is None:
            n -= 1
            continue
        out.append({"q": q, "a": answer, "family": "html_block",
                    "landmark": f"<{tag}> #{n}"})
    return out


_CARVERS = {".md": _rows_from_markdown, ".css": _rows_from_css,
            ".html": _rows_from_html, ".htm": _rows_from_html}


def carve_rows_from_files(
    root: str,
    into: str,
    exclude: list[str] | None = None,
    max_rows: int = 20000,
) -> dict[str, Any]:
    base = Path(root).resolve()
    if not base.is_dir():
        return {"ok": False, "error": "not_a_folder",
                "detail": f"{base} is not a folder on this machine."}
    holdouts = [str(e) for e in (exclude or []) if str(e).strip()]

    rows: list[dict[str, Any]] = []
    skipped: dict[str, int] = {"held_out": 0, "too_big": 0, "unreadable": 0, "other_type": 0}
    files_read = 0
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base).as_posix()
        if path.suffix.lower() not in CARVABLE:
            skipped["other_type"] += 1
            continue
        if any(h in rel for h in holdouts):
            skipped["held_out"] += 1
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            skipped["too_big"] += 1
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            skipped["unreadable"] += 1
            continue
        files_read += 1
        for row in _CARVERS[path.suffix.lower()](rel, body):
            row["source"] = rel
            row["text"] = f"{row['q']}\n{row['a']}"
            rows.append(row)
            if len(rows) >= max_rows:
                break
        if len(rows) >= max_rows:
            break

    if not rows:
        return {"ok": False, "error": "empty_carve",
                "detail": (f"read {files_read} carvable file(s) under {base} and found "
                           f"nothing to carve (skipped: {skipped}). An empty rows "
                           "file would be read as data by everything downstream, "
                           "so nothing was written.")}

    out_dir = Path(into).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{base.name}.carved.jsonl"
    out_file.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    families: dict[str, int] = {}
    for r in rows:
        families[r["family"]] = families.get(r["family"], 0) + 1
    manifest = {
        "written_by": "carve_rows",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": str(base),
        "held_out": holdouts,
        "files_read": files_read,
        "skipped": skipped,
        "rows": len(rows),
        "families": families,
        "law": ("every `a` and `text` is a verbatim excerpt of `source`; the ask "
                "templates are fixed and carry no facts; nothing was invented"),
    }
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "path": str(out_file),
        "rows": len(rows),
        "families": families,
        "files_read": files_read,
        "skipped": skipped,
        "held_out": holdouts,
        "summary": (f"Carved {len(rows)} rows from {files_read} file(s) under "
                    f"{base.name} ({', '.join(f'{v} {k}' for k, v in sorted(families.items()))})"
                    + (f", holding out {holdouts}" if holdouts else "")
                    + f". Every row is a verbatim excerpt tagged with its source; wrote {out_file.name}."),
    }
