"""What this data is, whether it is any good, and whether training is possible.

`docs/ARCHITECTURE.md` §4.9 gives this layer one responsibility: answer "what is
this data, is it any good, and is it dangerous." This module owns the first two.
It is the half of VISION's argument that a form cannot reach - a learning-rate
field cannot know that the label is 94% one class and that 41 rows appear on
both sides of the split, and those two facts change the answer more than the
learning rate does.

## The three defects this file was written to close

They are listed in `docs/ARCHITECTURE.md` §4.9 and `README.md`, and each one is
still covered by a test in `tests/test_dataquality_defects.py`:

1. ``open()`` omitted ``encoding=``, so on Windows - where the default is the
   ANSI codepage, not UTF-8 - any CSV containing ``cafe`` with an accent raised
   ``UnicodeDecodeError``. Every read in this file now goes through
   `encoding_ladder_for`, which sniffs the BOM and then tries UTF-8 before
   falling to latin-1, and the report says which rung it landed on.
2. An empty file left ``reader.fieldnames`` as ``None`` and the column loop
   raised ``TypeError``. An empty file is now an empty report that says it is
   empty.
3. Worst because it was silent: a column that is 100% missing was reported as
   having a null rate of 0.0. ``csv.DictReader`` fills a short row with ``None``,
   not ``""``, and the null test was ``record[column] == ""``, which ``None``
   fails. A column of nothing scored as a column of clean data. `is_null` now
   treats absent, empty and whitespace-only alike, and a column with no data
   rows under it reports ``None`` - no rate - rather than ``0.0``.

Defect 3 is the pattern the rest of this module is built against. **A check that
could not run says so. It never reports a clean bill of health it did not earn.**
Every profile carries `checks_not_run`, and a Parquet file we have no reader for
comes back with an empty finding list *and* a note saying the list is empty
because nothing was inspected - not because nothing was wrong.

## Provenance, on every number

Invariant 3: a number with no provenance does not get displayed. So every figure
here is `measured` (we counted it), `inferred` (we computed or estimated it from
something we counted) or `defaulted` (we could not tell and filled it in). The
distinction is load-bearing in two places in particular:

- **Length is measured in characters, and says so.** `docs/ARCHITECTURE.md` §4.9
  wants p95 in *tokens* using the candidate model's own tokenizer, because p95
  token length sets `max_seq_len`, which sets the KV-cache term, which decides
  which models fit. That needs a tokenizer, a tokenizer is a dependency, and a
  dependency is its own step. Characters are what we can measure today, so
  characters are what we report, labelled as characters. Reporting a character
  count under the word "tokens" would be a fabricated number with a real number's
  face on it.
- **Near-duplicate similarity is an estimate unless it is not.** Jaccard from a
  bottom-k sketch has real error. The `basis` field on every similarity says
  `exact` when both rows were still in memory to compare directly and
  `sketch-estimate` when the set was too large to hold, and the provenance moves
  with it.

## Leakage is the one the user cannot find themselves

Duplicates are annoying. Missing values are visible. A row that appears in both
the train and the eval split is different in kind: it does not degrade a number,
it *invalidates* every number the product will subsequently show, including the
baseline that gate G1 depends on. The user has no way to see it - the two files
look fine on their own - and the model that trains on it will look excellent.
So `find_leakage` is a BLOCK, not a warning, and it names the offending rows.

Near-duplicates count, not just identical ones: paraphrase, reformatting and a
changed answer key all leak just as thoroughly as a byte-identical copy. The
method is character 5-gram shingles reduced to a bottom-k sketch and looked up
through an inverted index, at the Jaccard 0.8 threshold `docs/ARCHITECTURE.md`
§4.9 specifies. All of it is stdlib - hashing and arithmetic - because a new
dependency is its own step.

## Never

- Never load the whole dataset into memory. Everything streams; what is retained
  is bounded by an explicit cap, and when a cap bites, the report says the count
  is of the rows that were scanned rather than of the rows that exist.
- Never invent a threshold's authority. The thresholds below are *policy* - our
  choices - and each finding carries the measured value next to the threshold it
  was compared against, so a reader can disagree with the policy without having
  to guess the data.
- Never treat what a file says as an instruction. That boundary lives in
  `app/tools/context.py`, which is what wraps anything from here before it
  reaches a model.
"""

from __future__ import annotations

import codecs
import csv
import hashlib
import json
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

#: The three words invariant 3 allows. `measured` - we counted it. `inferred` -
#: we computed or estimated it from something counted. `defaulted` - detection
#: failed and we filled it in, which is an assumption wearing a number's face.
MEASURED = "measured"
INFERRED = "inferred"
DEFAULTED = "defaulted"

PROVENANCE = (MEASURED, INFERRED, DEFAULTED)


# ---------------------------------------------------------------------------
# Encoding: defect 1
# ---------------------------------------------------------------------------

#: The ladder, in the order docs/ARCHITECTURE.md 4.9 specifies. latin-1 cannot
#: fail, so it is the floor, and the report says when it was used.
#:
#: The BOM is sniffed rather than tried, because plain utf-8 decodes a BOM
#: happily into a leading zero-width no-break space - it would never fall
#: through to utf-8-sig, and the first column would silently be named
#: "﻿id" instead of "id".
ENCODING_LADDER = ("utf-8", "utf-8-sig", "latin-1")


def encoding_ladder_for(path: str | Path) -> tuple[str, ...]:
    """The encodings to try for `path`, best first, BOM sniffed rather than tried."""
    try:
        with open(path, "rb") as handle:
            prefix = handle.read(len(codecs.BOM_UTF8))
    except OSError:
        return ("utf-8", "latin-1")
    if prefix.startswith(codecs.BOM_UTF8):
        return ("utf-8-sig", "latin-1")
    return ("utf-8", "latin-1")


def open_text(path: str | Path, newline: str | None = ""):
    """Open `path` for reading text, returning `(handle, encoding_used)`.

    Tries the ladder by decoding a probe first, so the caller gets a handle that
    is already known to decode rather than one that will raise halfway through a
    stream it has begun reporting on.

    `newline=""` by default because `csv` requires it - a quoted field
    containing a line break is corrupted without it. A caller reading a file for
    a person to look at passes `newline=None` and gets Python's usual universal
    newlines, so a Windows file does not arrive full of visible carriage
    returns.
    """
    ladder = encoding_ladder_for(path)
    last: UnicodeDecodeError | None = None
    for encoding in ladder:
        try:
            with open(path, "r", encoding=encoding, newline="") as probe:
                while probe.read(65536):
                    pass
        except UnicodeDecodeError as error:
            last = error
            continue
        return open(path, "r", encoding=encoding, newline=newline), encoding
    raise last  # unreachable: latin-1 decodes any byte sequence


def is_null(value: Any) -> bool:
    """A missing field, an empty field and a whitespace-only field are all null.

    This is defect 3 in one function. ``DictReader`` writes ``None`` into a short
    row's trailing columns and ``""`` into an explicitly empty one; testing only
    for ``""`` reported a wholly absent column as clean.
    """
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return False
    if isinstance(value, (list, tuple)):
        # csv puts overflow fields from a long row into a list under restkey.
        return all(is_null(item) for item in value)
    if isinstance(value, dict):
        return not value
    return str(value).strip() == ""


def read_rows(path: str | Path) -> tuple[list[str], list[dict[str, Any]], str]:
    """Read a CSV, returning ``(fieldnames, records, encoding_used)``.

    Kept because `data_quality_report` is a published shape other code and other
    tests call. New work should use `profile`, which streams.
    """
    handle, encoding = open_text(path)
    try:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        records = list(reader)
    finally:
        handle.close()
    return fieldnames, records, encoding


# ---------------------------------------------------------------------------
# Format detection: magic bytes, not extensions
# ---------------------------------------------------------------------------

#: Magic prefixes, longest first so `SQLite format 3\0` is not shadowed. Each
#: one is a measurement: the bytes are either there or they are not.
MAGIC_BYTES: tuple[tuple[bytes, str], ...] = (
    (b"SQLite format 3\x00", "sqlite"),
    (b"ARROW1", "arrow"),
    (b"PAR1", "parquet"),
    (b"PK\x03\x04", "zip"),
    (b"\x1f\x8b", "gzip"),
    (b"\x89HDF", "hdf5"),
)

#: Formats we can stream rows out of today. Everything else is reported
#: honestly as unreadable rather than half-guessed.
READABLE_FORMATS = frozenset({"csv", "tsv", "jsonl", "json", "text", "text_folder"})

#: Extensions that count as "a data file" when we are looking at a directory or
#: deciding whether a candidate filename is an eval set.
DATA_EXTENSIONS = frozenset(
    {".csv", ".tsv", ".jsonl", ".ndjson", ".json", ".parquet", ".txt", ".md", ".arrow"}
)

DELIMITERS = ((",", "csv"), ("\t", "tsv"), (";", "csv"), ("|", "csv"))


def detect_format(path: str | Path) -> dict[str, Any]:
    """What kind of file this is, decided by content and never by extension.

    An extension is a claim by whoever named the file. Magic bytes are a fact
    about the file, so they win; content sniffing is second; the extension is
    recorded but only ever breaks a tie.
    """
    p = Path(path)
    result: dict[str, Any] = {
        "name": None,
        "how": None,
        "provenance": DEFAULTED,
        "readable": False,
        "delimiter": None,
        "extension": p.suffix.lower(),
    }

    if not p.exists():
        result.update(name=None, how="the path does not exist", provenance=MEASURED)
        return result

    if p.is_dir():
        files = _directory_data_files(p)
        text_like = [f for f in files if f.suffix.lower() in {".txt", ".md"}]
        result.update(
            how="directory listing",
            provenance=MEASURED,
            file_count=len(files),
        )
        if files and len(text_like) == len(files):
            result.update(name="text_folder", readable=True)
        elif files:
            # A FOLDER OF ONE READABLE FORMAT IS READABLE. Max, 2026-09-19,
            # after a forty-minute run died here: *"An eval set exists - if it
            # sees an eval set doesn't exist, GO MAKE AN EVAL SET... stop just
            # saying not-work."* He pointed `assess_the_data` at
            # `ml-principles-dataset`, a folder of .jsonl, and got back "That
            # is a folder (directory listing) and no reader for it ships
            # today" - which was true of the CLASSIFIER and false of this
            # module: `iter_records` has had a per-file directory branch since
            # the day `text_folder` was added, and `_directory_data_files`
            # already walks every extension in `DATA_EXTENSIONS`.
            #
            # Only ONE format, deliberately. A folder holding CSV and JSONL
            # together has no single column vocabulary, and a profile that
            # averaged two schemas would be a number nobody could recompute.
            # Mixed stays unreadable and says which formats it found.
            kinds = {
                (detect_format(one).get("name") or "") for one in files
            }
            kinds.discard("")
            readable_kinds = kinds & READABLE_FORMATS
            if len(kinds) == 1 and len(readable_kinds) == 1:
                only = next(iter(readable_kinds))
                result.update(
                    name=f"{only}_folder",
                    readable=True,
                    inner_format=only,
                    how=f"directory listing - {len(files)} {only} files",
                )
            else:
                result.update(
                    name="folder",
                    readable=False,
                    how=(
                        "directory listing - "
                        + (
                            ", ".join(sorted(kinds)) + " together, which have no "
                            "one set of columns between them"
                            if len(kinds) > 1
                            else "no format here ships a reader"
                        )
                    ),
                )
        else:
            result.update(name="folder", readable=False)
        return result

    try:
        with open(p, "rb") as handle:
            head = handle.read(65536)
    except OSError as error:
        result.update(how=f"could not be opened: {error}", provenance=MEASURED)
        return result

    for prefix, name in MAGIC_BYTES:
        if head.startswith(prefix):
            result.update(
                name=name,
                how="magic bytes",
                provenance=MEASURED,
                readable=name in READABLE_FORMATS,
            )
            return result

    if not head:
        # An empty file is not a format failure, it is an empty CSV. Defect 2
        # was this case raising instead of reporting.
        result.update(name="csv", how="the file is empty", provenance=MEASURED, readable=True)
        return result

    if b"\x00" in head:
        result.update(
            name="binary", how="a null byte in the first 64 KB", provenance=MEASURED
        )
        return result

    text = _decode_probe(p, head)
    if text is None:
        result.update(name="binary", how="it does not decode as text", provenance=MEASURED)
        return result

    stripped = text.lstrip()
    lines = [line for line in text.splitlines() if line.strip()]

    if stripped.startswith("{") or stripped.startswith("["):
        object_lines = 0
        first: Any = None
        for index, line in enumerate(lines[:20]):
            try:
                parsed_line = json.loads(line)
            except ValueError:
                break
            if index == 0:
                first = parsed_line
            object_lines += 1
        if object_lines == min(len(lines), 20) and object_lines >= 1:
            # ONE LINE HOLDING AN ARRAY IS A JSON DOCUMENT, NOT JSONL. JSONL
            # means one row per line; a lone `[{...}, {...}]` is one line and
            # many rows, and reading it as JSONL yields a single record whose
            # only field is the whole array. That counted a 137-row eval set as
            # 1 row and stamped `eval_size_n = 1` MEASURED - and only below
            # 64 KB, because the sniffer reads that much and a longer array's
            # single line comes back truncated and unparsable, so the same file
            # was classified two different ways either side of a size nobody
            # told the user about.
            if len(lines) == 1 and isinstance(first, list):
                result.update(
                    name="json", how="one line holding a JSON array",
                    provenance=INFERRED, readable=True,
                )
                return result
            result.update(
                name="jsonl", how="every sampled line parses as JSON",
                provenance=INFERRED, readable=True,
            )
            return result
        result.update(
            name="json", how="the file opens with a JSON bracket",
            provenance=INFERRED, readable=True,
        )
        return result

    header = lines[0] if lines else ""
    counts = {char: header.count(char) for char, _ in DELIMITERS}
    best = max(DELIMITERS, key=lambda pair: counts[pair[0]])
    if counts[best[0]] > 0:
        result.update(
            name=best[1], how="a delimiter in the first line",
            provenance=INFERRED, readable=True, delimiter=best[0],
        )
        return result

    if p.suffix.lower() in {".txt", ".md"} or len(lines) <= 1:
        result.update(
            name="text", how="no delimiter in the first line",
            provenance=INFERRED, readable=True,
        )
        return result

    result.update(
        name="csv", how="no delimiter found; treated as a single column",
        provenance=INFERRED, readable=True, delimiter=",",
    )
    return result


def _decode_probe(path: Path, head: bytes) -> str | None:
    for encoding in encoding_ladder_for(path):
        try:
            return head.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


#: How many file names a refusal prints. Enough to choose from, short enough
#: that a 5,200-file corpus does not become the whole reply; the count beside
#: it is the real number, and is never capped.
FILES_NAMED_IN_A_REFUSAL = 40

#: The extensions that hold ROWS rather than prose. A refusal about a folder
#: lists these first: a data-quality tool pointed at a folder is looking for a
#: table, and a listing that buries the only table under sixty markdown files
#: is a listing nobody can act on.
ROW_EXTENSIONS = frozenset({".jsonl", ".ndjson", ".csv", ".tsv", ".json", ".parquet"})


def _directory_data_files(root: Path, cap: int | None = None) -> list[Path]:
    """Every data file under `root`, in a stable order. Uncapped by default.

    IT USED TO STOP AT 5,000 AND SAY NOTHING, which is defect 3 in a folder's
    clothing: a directory of 5,200 examples reported `file_count: 5000`, yielded
    5,000 rows, and `profile` marked the count `measured` because no row cap had
    bitten. `measure_eval_set` then stamped `eval_size_n = 5000` MEASURED on a
    set of 5,200. A wrong number wearing a measurement badge is worse than the
    refusal this file was rewritten to remove.

    The cap also bought nothing: `sorted(root.rglob("*"))` materialises the whole
    listing before the first comparison, so truncating the output afterwards
    saved no memory - it only made the answer wrong. Bounding the ROWS is
    `profile`'s job and it reports when it bites; bounding the FILE LIST was a
    silent second cap on the same quantity.
    """
    out: list[Path] = []
    for candidate in sorted(root.rglob("*")):
        if cap is not None and len(out) >= cap:
            break
        if candidate.is_file() and candidate.suffix.lower() in DATA_EXTENSIONS:
            out.append(candidate)
    return out


# ---------------------------------------------------------------------------
# Streaming records
# ---------------------------------------------------------------------------

#: Caps. Every one of them is reported when it bites; a truncated scan that
#: does not say it was truncated is the same class of lie as defect 3.
DEFAULT_ROW_CAP = 200_000
LENGTH_SAMPLE_CAP = 20_000
DISTINCT_CAP = 1_000
COLUMN_CAP = 500
MAX_FILE_CHARS = 2_000_000

#: A whole JSON document has to be in memory to be parsed at all - there is no
#: streaming JSON reader in the standard library - so this is a bound on the
#: file rather than on the rows, and it is checked BEFORE the read rather than
#: applied during it.
#:
#: It replaces `handle.read(MAX_FILE_CHARS)`, which was not a bound but a bug: a
#: prefix of a JSON array never parses, so every `.json` file over two million
#: characters came back as a dataset with no rows in it, `truncated` false, and
#: `rows` provenance MEASURED. A 60,000-row eval set was stamped
#: `eval_size_n = 0, MEASURED` and the summary read "Counted 0 rows". Reading
#: the whole document up to a real limit, and saying so above it, is the fix;
#: see `whole_document_limit`.
MAX_JSON_BYTES = 64 * 1024 * 1024


def whole_document_limit(
    path: str | Path, fmt: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """The one limit that is known to bite BEFORE a single row is read, or None.

    Row caps are decided while scanning and reported when they bite. This is the
    other kind: a format this build can only read all-at-once, in a file too big
    to hold. Nothing downstream can notice it from the rows, because there are
    no rows - which is exactly how `eval_size_n = 0` got a MEASURED badge.

    Returning it as data rather than raising is deliberate: `iter_records` is a
    generator consumed inside loops, and a reader that raises turns a reportable
    limit into a traceback in whatever happened to be iterating.
    """
    p = Path(path)
    fmt = fmt or detect_format(p)
    if fmt.get("name") != "json" or not p.is_file():
        return None
    try:
        size = p.stat().st_size
    except OSError:
        return None
    if size <= MAX_JSON_BYTES:
        return None
    return {
        "limit": "whole_json_document",
        "bytes": size,
        "budget_bytes": MAX_JSON_BYTES,
        "why": (
            f"This is one JSON document of {size:,} bytes. JSON has to be parsed "
            f"whole - there is no streaming reader for it in this build - and this "
            f"one is over the {MAX_JSON_BYTES:,}-byte limit on how much will be "
            "held in memory at once, so no row in it was read. That is not a file "
            "with nothing in it."
        ),
        "what_to_do": (
            "Convert it to JSONL - one JSON object per line, no enclosing array - "
            "and it streams, with no size limit but the time it takes to read."
        ),
    }


def json_read_nothing(
    path: str | Path, fmt: dict[str, Any] | None = None, rows: int = 0
) -> dict[str, Any] | None:
    """A JSON document that produced no rows: did it parse, or did it fail?

    `iter_records` swallows the `ValueError` - it is a generator inside somebody
    else's loop and cannot raise a parse error at them - so a malformed document
    and an empty one arrive here as the same zero. They are not the same thing:
    `[]` is a dataset with nothing in it, and a truncated or invalid document is
    a dataset that was never read, and calling the second one a measured zero is
    defect 3 with a whole file inside it.

    So this ASKS, rather than guessing from the file's size. It re-parses, which
    costs a second read of a document already known to be under `MAX_JSON_BYTES`,
    and only ever in the zero-row case. What it buys is the parser's own message
    and position, which is the most actionable sentence anybody can be given
    about a broken file.
    """
    p = Path(path)
    fmt = fmt or detect_format(p)
    if rows or fmt.get("name") != "json" or not p.is_file():
        return None
    if whole_document_limit(p, fmt) is not None:
        return None  # a different limit, already reported by that function
    try:
        handle, _ = open_text(p)
        try:
            raw = handle.read()
        finally:
            handle.close()
    except OSError as error:
        return {
            "limit": "json_unreadable",
            "why": f"The file could not be read: {error}",
            "what_to_do": "Check the file is present and readable and try again.",
        }
    try:
        json.loads(raw)
    except ValueError as error:
        return {
            "limit": "json_did_not_parse",
            "why": (
                f"This file is a JSON document and it does not parse: {error}. No "
                "row in it was read, so nothing here is a count of its rows - "
                "least of all zero."
            ),
            "what_to_do": (
                "Fix the file at the position above, or - if it was meant to be "
                "one JSON object per line - note that a line in it does not parse, "
                "which is why it was read as a single document rather than as JSONL."
            ),
        }
    return None


def iter_records(path: str | Path, fmt: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    """Stream one dict per row. Never builds the whole dataset in memory.

    A CSV row is its fields. A JSONL row is its object. A folder of text is one
    row per file, and a lone text file is one row per non-empty line - stated
    here because it is a choice, and a reader comparing "rows" between two
    formats deserves to know what a row was.
    """
    p = Path(path)
    fmt = fmt or detect_format(p)
    name = fmt.get("name")

    if name in ("csv", "tsv"):
        delimiter = fmt.get("delimiter") or ("\t" if name == "tsv" else ",")
        handle, _ = open_text(p)
        try:
            reader = csv.DictReader(handle, delimiter=delimiter)
            for record in reader:
                yield {k: v for k, v in record.items() if k is not None}
        finally:
            handle.close()
        return

    if name == "jsonl":
        handle, _ = open_text(p)
        try:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except ValueError:
                    yield {"_unparsed": line}
                    continue
                yield parsed if isinstance(parsed, dict) else {"value": parsed}
        finally:
            handle.close()
        return

    if name == "json":
        # Whole document or nothing. A prefix of a JSON array is not a smaller
        # JSON array, it is a parse error, and reading one silently turned every
        # large `.json` dataset into an empty one. `whole_document_limit` says
        # when this branch yields nothing because the file is too big, so that a
        # caller can tell "no rows in it" from "not read".
        if whole_document_limit(p, fmt) is not None:
            return
        handle, _ = open_text(p)
        try:
            raw = handle.read()
        finally:
            handle.close()
        try:
            parsed = json.loads(raw)
        except ValueError:
            return
        for record in _records_from_json(parsed):
            yield record
        return

    if name == "text":
        handle, _ = open_text(p)
        try:
            for line in handle:
                if line.strip():
                    yield {"text": line.rstrip("\r\n")}
        finally:
            handle.close()
        return

    if name == "text_folder":
        for candidate in _directory_data_files(p):
            handle, _ = open_text(candidate)
            try:
                body = handle.read(MAX_FILE_CHARS)
            finally:
                handle.close()
            yield {"file": candidate.name, "text": body}
        return

    # A FOLDER OF ONE READABLE FORMAT, READ FILE BY FILE. `detect_format` names
    # these `<format>_folder`; every row carries the file it came from, so a
    # profile over a split directory can still say which file a column is
    # missing from. The rows of all the files are one stream on purpose: that
    # is what "how many rows are in this dataset" means to the person who
    # pointed at the folder.
    if name.endswith("_folder"):
        for candidate in _directory_data_files(p):
            inner = detect_format(candidate)
            if not inner.get("readable"):
                continue
            for record in iter_records(candidate, inner):
                if isinstance(record, dict):
                    yield {"file": candidate.name, **record}
                else:
                    yield {"file": candidate.name, "value": record}
        return

    return


def declared_columns(path: str | Path, fmt: dict[str, Any] | None = None) -> list[str]:
    """The column names a file declares, even when it has no rows under them.

    A header-only CSV has columns and no data. Building the column list out of
    the rows alone would report it as having neither, which loses the one thing
    such a file does tell you - and reintroduces defect 3 from the other side:
    a column nobody can see cannot be reported as empty.
    """
    p = Path(path)
    fmt = fmt or detect_format(p)
    if fmt.get("name") not in ("csv", "tsv") or not p.is_file():
        return []
    delimiter = fmt.get("delimiter") or ("	" if fmt.get("name") == "tsv" else ",")
    try:
        handle, _ = open_text(p)
    except OSError:
        return []
    try:
        reader = csv.DictReader(handle, delimiter=delimiter)
        return [str(name) for name in (reader.fieldnames or []) if name is not None]
    finally:
        handle.close()


def _records_from_json(parsed: Any) -> Iterator[dict[str, Any]]:
    if isinstance(parsed, list):
        for item in parsed:
            yield item if isinstance(item, dict) else {"value": item}
        return
    if isinstance(parsed, dict):
        # A wrapper object around the real rows is the common export shape.
        lists = [(k, v) for k, v in parsed.items() if isinstance(v, list) and v]
        if lists:
            key, longest = max(lists, key=lambda pair: len(pair[1]))
            for item in longest:
                yield item if isinstance(item, dict) else {key: item}
            return
        yield parsed
        return
    yield {"value": parsed}


# ---------------------------------------------------------------------------
# Counting, which is not profiling
# ---------------------------------------------------------------------------

#: How long a count will run before it stops and asks. Seconds of wall clock,
#: not rows, and that unit is the whole point: a row cap bounds THE ANSWER, and
#: an answer that stops at 200,000 is not a count of a 200,001-row file. A time
#: budget bounds what it costs to get the answer and leaves the answer alone.
#:
#: Measured, on one machine, on one 7.9 MB / 200,001-row JSONL fixture:
#: counting took 0.23 s, profiling the same rows with near-duplicate detection
#: off took 1.77 s, and profiling them as `measure_eval_set` actually did - with
#: near-duplicate detection on, as it defaults - took 57.7 s. Those three
#: figures are why this is a separate operation rather than a flag on `profile`:
#: `DEFAULT_ROW_CAP` is a sensible bound on the 57.7 s one and it is about two
#: orders of magnitude too tight for the 0.23 s one. Your machine's numbers will
#: differ; the ratio is the part that argues.
#:
#: Thirty seconds therefore reaches far past any evaluation set a person has,
#: and when it does bite the caller is told the rate it measured and offered the
#: unbounded run rather than a smaller number.
COUNT_TIME_BUDGET_SECONDS = 30.0

#: How often the clock is consulted, in rows. Not every row, because a budget
#: that slows the thing it bounds is paying for itself twice - and not a huge
#: stride either, because the stride is how far past the budget a slow reader
#: can run before anything notices. 512 costs about one `time.perf_counter()`
#: per 512 rows against roughly a microsecond of work per row, which is noise,
#: and it keeps the overshoot to a fraction of a second on any reader that is
#: not already pathological.
#:
#: `perf_counter` and not `monotonic`: on this Windows box `time.monotonic()`
#: ticks every 15.6 ms and `perf_counter` every 0.5 us, both measured. The coarse
#: clock made `elapsed` read as exactly 0.0 on a short scan, which divided by
#: zero on the way to reporting a rate - found by the test that squeezes the
#: budget to nothing, which is the only reason the branch was ever exercised.
_CLOCK_EVERY = 512


def count_rows(
    path: str | Path,
    *,
    fmt: dict[str, Any] | None = None,
    time_budget_seconds: float | None = None,
    unbounded: bool = False,
) -> dict[str, Any]:
    """How many rows are in this dataset. Exactly, or not at all, and it says which.

    A COUNT AND A PROFILE ARE DIFFERENT OPERATIONS AND THIS IS THE CHEAP ONE.
    `profile` holds a near-duplicate index, a per-column distinct set and an
    exact-duplicate table, all of which grow with the data; `DEFAULT_ROW_CAP`
    exists to bound those and it is right to. Counting holds one integer and a
    set of column names. It is O(1) in memory at any file size, so nothing about
    the number of rows needs to bound it, and inheriting a cap sized for the
    expensive operation is what made the product's answer to `G0_EVAL_SET`
    unable to answer `G0_EVAL_SET`.

    The rows counted are the rows `iter_records` yields, because that is what
    every other part of this product will see - a count taken by a faster route
    that disagreed with the reader would be a different defect wearing this
    one's fix.

    `exact` is the field that matters. It is true only when the scan reached the
    end of the data, and `rows` is a lower bound whenever it is false. Callers
    that stamp provenance must read `exact` and not `rows`; `provenance` is
    given alongside it, already resolved, so that a caller cannot get the rule
    subtly wrong on its own.

    `time_budget_seconds` defaults to `None` and resolves `COUNT_TIME_BUDGET_SECONDS`
    HERE rather than in the signature, because a default bound at import is a
    constant no test can lower and no setting can raise - the budget would then
    be a branch that only a multi-gigabyte fixture could reach, which is a branch
    nobody would ever test.
    """
    p = Path(path)
    fmt = fmt or detect_format(p)
    started = time.perf_counter()

    out: dict[str, Any] = {
        "path": str(p),
        "exists": p.exists(),
        "readable": bool(fmt.get("readable")),
        "format": fmt,
        "rows": None,
        "exact": False,
        "provenance": DEFAULTED,
        "columns": [],
        "seconds": 0.0,
        "rows_per_second": None,
        "bytes": None,
        "stopped_because": None,
        "note": "",
        "what_to_do": "",
    }

    if not p.exists():
        out["note"] = f"There is nothing at {p}, so nothing was counted."
        out["stopped_because"] = "no_such_path"
        out["what_to_do"] = "Check the path and run it again."
        return out

    if not fmt.get("readable"):
        out["note"] = (
            f"This is a {fmt.get('name') or 'file of unknown type'} "
            f"({fmt.get('how')}). No reader for it ships today, so nothing in it "
            "was counted. That is not a count of zero."
        )
        out["stopped_because"] = "no_reader"
        out["what_to_do"] = (
            "Export it as CSV, JSONL or a folder of text files and point this at "
            "that instead."
        )
        return out

    try:
        out["bytes"] = p.stat().st_size if p.is_file() else None
    except OSError:
        out["bytes"] = None

    limit = whole_document_limit(p, fmt)
    if limit is not None:
        out["stopped_because"] = limit["limit"]
        out["note"] = limit["why"]
        out["what_to_do"] = limit["what_to_do"]
        out["limit"] = limit
        return out

    budget = (
        COUNT_TIME_BUDGET_SECONDS if time_budget_seconds is None else time_budget_seconds
    )
    deadline = None if unbounded else started + max(0.0, float(budget))
    rows = 0
    seen: set[str] = set()
    columns: list[str] = []
    stopped: str | None = None

    stream = iter_records(p, fmt)
    try:
        for record in stream:
            rows += 1
            if isinstance(record, dict) and len(columns) < COLUMN_CAP:
                for key in record:
                    name = str(key)
                    if name not in seen:
                        seen.add(name)
                        columns.append(name)
                        if len(columns) >= COLUMN_CAP:
                            break
            if deadline is not None and rows % _CLOCK_EVERY == 0:
                if time.perf_counter() >= deadline:
                    stopped = "time_budget"
                    break
    finally:
        # Same reason `profile` closes its stream by hand: a generator abandoned
        # mid-iteration keeps its file handle until the collector gets to it,
        # and on Windows that is the difference between a temp directory that
        # can be removed and one that cannot.
        stream.close()

    elapsed = time.perf_counter() - started
    out["rows"] = rows
    out["columns"] = columns
    out["seconds"] = round(elapsed, 3)
    # `None` rather than a division by an interval that rounded to nothing. A
    # rate is a measurement like any other, and there is no honest one to report
    # from a scan too short to have been timed.
    out["rows_per_second"] = round(rows / elapsed) if elapsed > 0 else None
    unparsed = json_read_nothing(p, fmt, rows) if stopped is None else None
    if unparsed is not None:
        stopped = unparsed["limit"]
        out["limit"] = unparsed

    out["exact"] = stopped is None
    out["stopped_because"] = stopped
    out["provenance"] = MEASURED if stopped is None else INFERRED

    if unparsed is not None:
        out["note"] = unparsed["why"]
        out["what_to_do"] = unparsed["what_to_do"]
        return out

    if stopped is None:
        out["note"] = f"Counted {rows:,} rows in {p}."
    else:
        rate = out["rows_per_second"]
        out["note"] = (
            f"Counting stopped after {out['seconds']:g} seconds, at {rows:,} rows, "
            f"before the end of the data. {rows:,} is therefore the fewest rows "
            "this data has and not the number of rows it has."
        )
        out["what_to_do"] = (
            "Run it again and ask it to finish the count"
            + (f": it read about {rate:,} rows a second here, and it" if rate else ", and it")
            + " will keep going to the end however long that takes."
        )
    return out


# ---------------------------------------------------------------------------
# Synthetic rows, and the one question every gate fact has to ask about a file
# ---------------------------------------------------------------------------

#: The tag `app/tools/datawork.py::synthesize_rows` writes onto every row it
#: generates. It is a column name rather than a sidecar file on purpose: a
#: manifest can be lost, moved away from its data, or simply not read, and the
#: rule this tag exists to enforce - `docs/VISION.md`, "tagged at the row" -
#: has to survive somebody copying the rows into a spreadsheet and back.
SYNTHETIC_FIELD = "synthetic"

#: Written beside it, and kept here so a reader that wants to strip the tagging
#: does not have to know three string literals that live in another module.
SYNTHETIC_COMPANIONS = ("synthetic_source_index", "synthetic_seed")


def is_synthetic_row(record: dict[str, Any]) -> bool:
    """Is this one row generated rather than real?

    Truthiness rather than `is True`, because the row makes a round trip through
    CSV on the way to anywhere: `synthetic: True` in JSONL is the string
    `"True"` after a save-as, and a check that only accepted the boolean would
    quietly stop being a check at the first spreadsheet.

    The negative spellings are read too. A file that says `synthetic: false` is
    a file whose author thought about the question, and reading `"false"` as
    truthy - which every non-empty string is - would refuse the honest case.
    """
    if SYNTHETIC_FIELD not in record:
        return False
    value = record[SYNTHETIC_FIELD]
    if isinstance(value, str):
        return value.strip().lower() not in ("", "false", "no", "0", "none", "null")
    return bool(value)


def synthetic_census(
    path: str | Path,
    fmt: dict[str, Any] | None = None,
    *,
    time_budget_seconds: float | None = None,
    unbounded: bool = False,
) -> dict[str, Any]:
    """How many of this file's rows are generated, and how many are real.

    THIS IS THE ONE QUESTION A GATE FACT HAS TO ASK, and until 2026-08-27
    nothing asked it. `synthesize_rows` tags every row it writes and its own
    docstring said what was missing in as many words: *"nothing here checks
    whether a later call points measure_eval_set at it - that gate still reads
    the file that exists"*. So the rule "synthetic data can never open a gate"
    was enforced at the writer, which is the end that cannot enforce it. A file
    of a thousand generated rows counted as a thousand-row eval set, G0 opened
    on it, and every score downstream was a statement about a distribution this
    product invented.

    The census is deliberately SEPARATE from `count_rows`. Counting is O(1) in
    memory and does not look inside a row; this looks at one field of every row.
    Keeping them apart means the cheap operation stays cheap and the caller that
    needs the expensive answer asks for it by name - and it means the count and
    the census are read by the same `iter_records`, so they cannot disagree
    about what a row is.

    `exact` is the field that decides. Like `count_rows`, a scan that stopped
    early gives lower bounds, and a lower bound on "how many rows here are
    invented" is not an answer a gate may be opened on: **`clean` is None when
    the scan did not finish**, and a caller that stamps must read `clean` rather
    than comparing `synthetic` to zero itself.
    """
    p = Path(path)
    budget = COUNT_TIME_BUDGET_SECONDS if time_budget_seconds is None else time_budget_seconds
    started = time.monotonic()
    fmt = fmt or detect_format(p)

    total = 0
    synthetic = 0
    stopped: str | None = None
    tagged = SYNTHETIC_FIELD in set(declared_columns(p, fmt))

    try:
        for record in iter_records(p, fmt):
            total += 1
            if SYNTHETIC_FIELD in record:
                tagged = True
                if is_synthetic_row(record):
                    synthetic += 1
            if not unbounded and (total % 1000 == 0):
                if time.monotonic() - started > budget:
                    stopped = "time"
                    break
    except OSError as error:
        return {
            "path": str(p),
            "ok": False,
            "why": f"{p} could not be read: {error}",
            "rows": None,
            "synthetic": None,
            "real": None,
            "clean": None,
            "tagged": tagged,
            "exact": False,
        }

    exact = stopped is None
    return {
        "path": str(p),
        "ok": True,
        "rows": total,
        "synthetic": synthetic,
        "real": total - synthetic,
        # The whole point of the function, resolved here rather than by every
        # caller: True only when the scan finished AND found nothing generated.
        "clean": (synthetic == 0) if exact else None,
        # Whether the file carries the tag at all. A file with no tagging is
        # clean as far as anything can tell, and saying "as far as anything can
        # tell" is the honest half.
        "tagged": tagged,
        "exact": exact,
        "stopped_because": stopped,
        "seconds": round(time.monotonic() - started, 3),
        "how": (
            f"read every row of {p.name} and counted the ones whose "
            f"{SYNTHETIC_FIELD!r} field is set"
        ),
    }


# ---------------------------------------------------------------------------
# Near-duplicate machinery: shingles, a bottom-k sketch, an inverted index
# ---------------------------------------------------------------------------

SHINGLE_SIZE = 5

#: docs/ARCHITECTURE.md 4.9: "MinHash LSH over character 5-gram shingles at
#: Jaccard 0.8". A policy threshold, not a measurement.
JACCARD_THRESHOLD = 0.8

#: How many of a row's smallest shingle hashes make up its sketch.
#:
#: A bottom-k sketch rather than k independent permutations, and the reason is
#: that k-permutation MinHash costs `len(shingles) * k` modular multiplications
#: per row in pure Python - about nineteen thousand for a 300-character row -
#: which turned a profile of a twelve-thousand-row file into a minute of
#: arithmetic. A bottom-k sketch is one sort of a set we already built. It is
#: the same family of estimator (KMV), it supports the same candidate lookup,
#: and it is fast enough that near-duplicate detection can stay on by default
#: rather than becoming an option nobody switches on.
SKETCH_SIZE = 64

#: A sketch value that appears in more rows than this is a common shingle
#: rather than a signal, and indexing it further only produces candidates that
#: fail verification. Rows keep their other sketch values, so a genuine
#: near-duplicate pair is still found through a rarer one.
POSTING_CAP = 500

#: How many candidates one row will verify before giving up. It only bites on
#: pathological data, and when it does the caller is told.
CANDIDATE_CAP = 200

#: How much normalised row text we keep so a candidate pair can be verified by
#: exact Jaccard instead of a sketch estimate. When the budget runs out the
#: report says `sketch-estimate` rather than pretending the number is exact.
TEXT_BUDGET_CHARS = 8_000_000

#: How many shingle hashes may be cached across all retained rows. Caching them
#: is what stops verification re-deriving the same set once per candidate pair;
#: the budget is what stops that cache being the thing that runs the machine out
#: of memory on a file we promised to stream.
SHINGLE_BUDGET = 4_000_000

_WHITESPACE = re.compile(r"\s+")


def normalise_text(value: str) -> str:
    """Lower case, whitespace collapsed. Formatting is not content."""
    return _WHITESPACE.sub(" ", str(value).strip().lower())


def shingles(text: str, size: int = SHINGLE_SIZE) -> set[int]:
    """Character n-gram shingles, hashed to ints.

    A string shorter than the window becomes one shingle rather than none - the
    alternative is that every short row has an empty set, an empty set has an
    undefined Jaccard with everything, and short rows silently stop being
    checked. Silently stopping checking is the defect this file exists to close.
    """
    text = normalise_text(text)
    if not text:
        return set()
    if len(text) <= size:
        return {_stable_hash(text)}
    return {_stable_hash(text[i : i + size]) for i in range(len(text) - size + 1)}


def _stable_hash(value: str) -> int:
    """A process-stable 64-bit hash.

    Not `hash()`. Python salts that per process, so a signature computed today
    would not match one computed by the engine tomorrow, and a leakage result
    that changes between two runs over the same two files is worse than no
    leakage result at all.

    `blake2b` truncated to eight bytes rather than a hand-rolled FNV loop, for
    the unglamorous reason that a Python loop over the bytes of a five-character
    shingle is the single hottest line in a profile of a large file, and this
    one runs in C.
    """
    return int.from_bytes(
        hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest(), "big"
    )


def sketch(shingle_set: set[int], size: int = SKETCH_SIZE) -> tuple[int, ...]:
    """The `size` smallest shingle hashes: a bottom-k (KMV) sketch of the set.

    Smallest rather than a random sample, because "smallest under a fixed hash"
    is the same choice for every row - which is what makes two sketches
    comparable at all.
    """
    if not shingle_set:
        return ()
    return tuple(sorted(shingle_set)[:size])


def jaccard(left: set[int], right: set[int]) -> float:
    """Exact Jaccard over two shingle sets.

    One set operation, not two: `|A u B|` is `|A| + |B| - |A n B|`, so building
    the union as well as the intersection doubles the cost of the hottest line
    in this module for a number arithmetic already has.
    """
    if not left and not right:
        return 1.0
    intersection = len(left & right)
    union = len(left) + len(right) - intersection
    return intersection / union if union else 0.0


def sketch_jaccard(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    """Estimated Jaccard from two bottom-k sketches.

    The KMV estimator: take the k smallest values of the union of the two
    sketches, and count how many of them are in both. It is an estimate, it is
    labelled as one everywhere it surfaces, and it is only ever used when the
    rows themselves were too large to keep for an exact comparison.
    """
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    left_set, right_set = set(left), set(right)
    merged = sorted(left_set | right_set)[: min(len(left), len(right))]
    if not merged:
        return 0.0
    shared = sum(1 for value in merged if value in left_set and value in right_set)
    return shared / len(merged)


@dataclass
class _RowIndex:
    """Rows seen so far, indexed for near-duplicate lookup.

    Four structures, each with a job. `exact` catches identical rows for free.
    `postings` narrows a near-duplicate search from every row to a handful, by
    the observation that two rows at Jaccard 0.8 almost certainly share one of
    their sixty-four smallest shingle hashes. `sketches` is what a candidate is
    scored against when the row itself is gone. `texts` holds normalised text
    while a budget allows, so the common case - a local dataset that fits - is
    verified exactly rather than estimated.

    `saturated` is the honesty valve: a shingle common enough to appear in five
    hundred rows is noise, indexing it further only manufactures candidates that
    fail verification, and the set records which values were dropped so a caller
    can say the search was narrowed rather than pretending it was exhaustive.
    """

    exact: dict[int, list[int]] = field(default_factory=dict)
    postings: dict[int, list[int]] = field(default_factory=dict)
    saturated: set[int] = field(default_factory=set)
    sketches: dict[int, tuple[int, ...]] = field(default_factory=dict)
    texts: dict[int, str] = field(default_factory=dict)
    shingle_cache: dict[int, set[int]] = field(default_factory=dict)
    shingles_held: int = 0
    chars_held: int = 0
    text_budget_spent: bool = False
    candidate_cap_hit: bool = False

    def prepare(self, text: str) -> tuple[str, int, set[int], tuple[int, ...]]:
        """Everything derived from one row, computed once.

        `add` and `matches` both need the normalised text, its hash, its shingle
        set and its sketch. Deriving them twice per row is the difference between
        a profile that returns while the user is still looking at the screen and
        one that does not.
        """
        normalised = normalise_text(text)
        mine = shingles(normalised)
        return normalised, _stable_hash(normalised), mine, sketch(mine)

    def add(self, row_id: int, text: str, prepared=None) -> None:
        normalised, exact_hash, mine, row_sketch = prepared or self.prepare(text)
        self.exact.setdefault(exact_hash, []).append(row_id)
        self.sketches[row_id] = row_sketch
        for value in row_sketch:
            if value in self.saturated:
                continue
            posting = self.postings.setdefault(value, [])
            posting.append(row_id)
            if len(posting) > POSTING_CAP:
                self.saturated.add(value)
                self.postings.pop(value, None)
        if self.chars_held + len(normalised) <= TEXT_BUDGET_CHARS:
            self.texts[row_id] = normalised
            self.chars_held += len(normalised)
            # Shingles are cached under the same budget the text is kept under,
            # so verification never re-derives them for a candidate. Without
            # this, a file of near-identical rows recomputes the same shingle
            # set once per candidate pair and the cost is quadratic.
            if self.shingles_held + len(mine) <= SHINGLE_BUDGET:
                self.shingle_cache[row_id] = mine
                self.shingles_held += len(mine)
        else:
            self.text_budget_spent = True

    def _shingles_for(self, row_id: int) -> set[int] | None:
        cached = self.shingle_cache.get(row_id)
        if cached is not None:
            return cached
        text = self.texts.get(row_id)
        return None if text is None else shingles(text)

    def matches(
        self, text: str, threshold: float = JACCARD_THRESHOLD, prepared=None
    ) -> list[dict[str, Any]]:
        """Rows already indexed that are at or above `threshold` similarity."""
        _, exact_hash, mine, my_sketch = prepared or self.prepare(text)
        found: dict[int, dict[str, Any]] = {}

        for row_id in self.exact.get(exact_hash, ()):
            found[row_id] = {
                "row": row_id,
                "similarity": 1.0,
                "basis": "exact",
                "provenance": MEASURED,
            }

        # Count how many sketch values each candidate shares, rather than only
        # that it shares one. Two things follow. Collection stops early instead
        # of gathering tens of thousands of rows and sorting them, which on a
        # small-vocabulary dataset was most of the cost of profiling the file.
        # And when the cap does bite, what survives is the candidates that share
        # the most with this row rather than the ones that happen to have the
        # lowest row numbers.
        shared: dict[int, int] = {}
        for value in my_sketch:
            posting = self.postings.get(value)
            if not posting:
                continue
            for row_id in posting:
                shared[row_id] = shared.get(row_id, 0) + 1
            if len(shared) > CANDIDATE_CAP * 4:
                self.candidate_cap_hit = True
                break
        for row_id in found:
            shared.pop(row_id, None)
        candidates = [
            row_id
            for row_id, _ in sorted(shared.items(), key=lambda kv: (-kv[1], kv[0]))[
                :CANDIDATE_CAP
            ]
        ]

        mine_size = len(mine)
        for row_id in candidates:
            theirs = self._shingles_for(row_id)
            if theirs is not None:
                # |A n B| / |A u B| can never exceed min(|A|,|B|) / max(|A|,|B|),
                # so two rows of very different length cannot be near-duplicates
                # and do not need comparing. An exact bound, not a heuristic: it
                # discards no pair that could have passed.
                theirs_size = len(theirs)
                larger = max(mine_size, theirs_size)
                if larger and min(mine_size, theirs_size) / larger < threshold:
                    continue
                score = jaccard(mine, theirs)
                basis, provenance = "exact", MEASURED
            else:
                score = sketch_jaccard(my_sketch, self.sketches[row_id])
                basis, provenance = "sketch-estimate", INFERRED
            if score >= threshold:
                found[row_id] = {
                    "row": row_id,
                    "similarity": round(score, 3),
                    "basis": basis,
                    "provenance": provenance,
                }
        return sorted(found.values(), key=lambda m: (-m["similarity"], m["row"]))


def row_text(record: dict[str, Any]) -> str:
    """One row flattened to the text a similarity check compares.

    Keys are dropped and values joined: two rows that say the same thing under
    differently spelled column names are the same row for leakage purposes, and
    that is exactly the case a user cannot spot by eye.
    """
    parts = []
    for value in record.values():
        if is_null(value):
            continue
        if isinstance(value, (dict, list)):
            parts.append(json.dumps(value, sort_keys=True, ensure_ascii=False))
        else:
            parts.append(str(value))
    return " ".join(parts)


def signature_of_text(text: str) -> int:
    """The signature of a piece of row text. One line, and it is the definition.

    `_stable_hash` rather than `hash()`, and that is the whole content of this
    function: Python salts `hash()` per process, so a signature computed today
    does not match one computed tomorrow. That did not matter while signatures
    only ever counted duplicates inside one call, and it matters completely now
    that `app/tools/datawork.py` DECIDES WHICH ROWS GO WHERE from one - a split
    that comes out differently on the next run is a split nobody can reproduce
    and therefore a split nobody can defend.
    """
    return _stable_hash(normalise_text(text))


def row_signature(record: dict[str, Any]) -> int:
    """WHEN TWO ROWS ARE THE SAME ROW. There is one of these, deliberately.

    `profile` counts exact duplicates with it, `assess_the_data` reports
    "49 scanned - 1 exact duplicates = 48" from it, and `drop_duplicates` writes
    the file by it. Before this existed, the first two were the same idea
    expressed twice in two files - one of them through the salted `hash()` - and
    a product that counts the same thing twice on two definitions eventually
    reports both. A writer is where that stops being an untidiness: the count a
    user is shown and the number of rows a tool removes have to be the same
    number, and the only way to be sure is for there to be one implementation.
    """
    return signature_of_text(row_text(record))


def near_duplicate_clusters(
    texts: dict[int, str], *, threshold: float = JACCARD_THRESHOLD
) -> tuple[dict[int, int], dict[str, Any]]:
    """Group keys whose texts are NEAR duplicates, transitively. One unit per question.

    WHY THIS EXISTS, AND IT IS A DEFECT REPORT RATHER THAN A FEATURE REQUEST.
    `carve_eval_set` drew its split by EXACT row signature and then verified the
    result with `find_leakage`, which is a STRICTLY STRONGER predicate: near
    duplicates at Jaccard >= 0.8 count as leaks. So the draw made no attempt to
    satisfy the thing that judges it and could only pass by luck. Driven on a
    161-row dataset built from this repository's own git log it refused its own
    output on 12 OF 25 SEEDS - 3 came back clean and 10 refused before writing,
    for an unrelated and legitimate reason - and on a 160-row fixture with zero
    exact duplicates it leaked on 25 OF 25, all 30 eval rows every time. The
    tool's own remedy - remove the overlapping rows and re-split - was
    implemented by nothing in the product.

    THE UNIT OF THE DRAW HAS TO BE THE UNIT OF THE CHECK. That is the whole fix,
    and it is the same argument `_choose` already makes for exact duplicates -
    "the same question asked twice is one question to a gate that asks for real
    inputs" - carried the one step further that the checker was already taking.

    TRANSITIVE, AND THAT IS NOT AN IMPLEMENTATION CONVENIENCE. If A is near B and
    B is near C but A is not near C, putting A and C in the eval set and B in the
    training set still leaks: B is near both. Only connected components give the
    guarantee, so connected components is what this computes.

    THE INSTRUMENT IS THE SAME ONE THE CHECK USES, `_RowIndex`, at the same
    threshold - which matters more than exactness. Both saturate the same way on
    a file too big to hold, so the draw and the verification agree about what
    they can see rather than disagreeing about it. `report["exhaustive"]` says
    whether anything was dropped, and it is False rather than absent when the
    search was narrowed, because "we looked at everything" is a claim.

    Returns `(cluster_of, report)`: a key -> cluster-id map where the id is the
    smallest key in the component, and what the search cost and whether it was
    complete.
    """
    parent: dict[int, int] = {key: key for key in texts}

    def find(key: int) -> int:
        root = key
        while parent[root] != root:
            root = parent[root]
        while parent[key] != root:
            parent[key], key = root, parent[key]
        return root

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            # Smaller key wins, so the id of a component is the smallest key in
            # it and the answer does not depend on insertion order.
            parent[max(a, b)] = min(a, b)

    index = _RowIndex()
    pairs = 0
    for key in sorted(texts):
        prepared = index.prepare(texts[key])
        for match in index.matches(texts[key], threshold, prepared=prepared):
            union(key, int(match["row"]))
            pairs += 1
        index.add(key, texts[key], prepared=prepared)

    cluster_of = {key: find(key) for key in texts}
    sizes: dict[int, int] = {}
    for cluster in cluster_of.values():
        sizes[cluster] = sizes.get(cluster, 0) + 1
    exhaustive = not (index.candidate_cap_hit or index.text_budget_spent or index.saturated)
    report = {
        "keys": len(texts),
        "clusters": len(sizes),
        "pairs_found": pairs,
        "largest_cluster": max(sizes.values()) if sizes else 0,
        "threshold": threshold,
        "threshold_is": "our policy, not a property of the data",
        "method": (
            f"character {SHINGLE_SIZE}-gram shingles, a bottom-{SKETCH_SIZE} sketch "
            "looked up through an inverted index, verified by exact Jaccard where "
            "both rows were still in memory; components are transitive"
        ),
        "exhaustive": exhaustive,
        "narrowed_by": sorted(
            name
            for name, hit in (
                ("candidate_cap", index.candidate_cap_hit),
                ("text_budget", index.text_budget_spent),
                ("saturated_shingles", bool(index.saturated)),
            )
            if hit
        ),
        "provenance": MEASURED if exhaustive else INFERRED,
    }
    return cluster_of, report


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

BLOCK = "BLOCK"
WARN = "WARN"
INFO = "INFO"

#: Policy thresholds. Ours, not the data's. Each finding carries the measured
#: value beside the threshold it was compared against so a reader can disagree
#: with the policy without having to re-derive the data.
MIN_ROWS_FOR_TRAINING = 100
DUPLICATE_WARN_RATE = 0.01
DUPLICATE_BLOCK_RATE = 0.30
NEAR_DUPLICATE_WARN_RATE = 0.05
NULL_WARN_RATE = 0.05
IMBALANCE_WARN_SHARE = 0.60
IMBALANCE_BLOCK_SHARE = 0.95
SHORT_ROW_CHARS = 10
SHORT_ROW_WARN_RATE = 0.10

#: Text that teaches a model to refuse. Common in synthetic sets, and training
#: on it is training the model to decline.
DEGENERATE_MARKERS = (
    "as an ai language model",
    "as an ai assistant",
    "i'm sorry, but i can't",
    "i'm sorry, but i cannot",
    "i cannot fulfill that request",
    "i am unable to provide",
    "lorem ipsum",
)


@dataclass(frozen=True)
class Finding:
    """One thing that is true about this data, and what to do about it."""

    level: str
    code: str
    message: str
    remediation: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "remediation": self.remediation,
            "evidence": dict(self.evidence),
        }


# ---------------------------------------------------------------------------
# Shape classification
# ---------------------------------------------------------------------------

#: Column-name signatures, scored rather than matched, because a real dataset
#: rarely uses the canonical names and a silent misclassification sends the
#: loss function, the prompt template and the eval metric all the wrong way.
SHAPE_SIGNATURES: dict[str, tuple[tuple[frozenset[str], float], ...]] = {
    "instruction_pairs": (
        (frozenset({"instruction", "output"}), 1.0),
        (frozenset({"instruction", "input", "output"}), 1.0),
        (frozenset({"instruction", "response"}), 1.0),
        (frozenset({"prompt", "completion"}), 0.9),
        (frozenset({"question", "answer"}), 0.8),
        (frozenset({"query", "response"}), 0.7),
    ),
    "chat": (
        (frozenset({"messages"}), 1.0),
        (frozenset({"conversations"}), 1.0),
        (frozenset({"conversation"}), 0.9),
        (frozenset({"role", "content"}), 0.8),
    ),
    "preference_pairs": (
        (frozenset({"chosen", "rejected"}), 1.0),
        (frozenset({"prompt", "chosen", "rejected"}), 1.0),
        (frozenset({"preferred", "dispreferred"}), 0.9),
        (frozenset({"response_a", "response_b"}), 0.7),
    ),
    "labelled_classification": (
        (frozenset({"text", "label"}), 1.0),
        (frozenset({"sentence", "label"}), 0.9),
        (frozenset({"text", "target"}), 0.8),
        (frozenset({"text", "class"}), 0.8),
        (frozenset({"label"}), 0.5),
        (frozenset({"labels"}), 0.5),
    ),
    "span_extraction": (
        (frozenset({"text", "spans"}), 1.0),
        (frozenset({"text", "entities"}), 1.0),
        (frozenset({"context", "answers"}), 0.9),
        (frozenset({"start", "end"}), 0.6),
    ),
    "raw_text": (
        (frozenset({"text"}), 0.4),
        (frozenset({"content"}), 0.4),
        (frozenset({"document"}), 0.4),
        (frozenset({"body"}), 0.3),
    ),
    "tabular": (),
}

LABEL_NAMES = (
    "label", "labels", "target", "class", "category", "y",
    "sentiment", "intent", "tag",
)


def classify_shape(profile_result: dict[str, Any]) -> dict[str, Any]:
    """What kind of dataset this is - with a confidence and a runner-up, always.

    `docs/ARCHITECTURE.md` §4.9 requires the runner-up because the failure mode
    is not "wrong", it is "wrong and confident". A user shown "instruction pairs
    (0.55), second guess preference pairs (0.45)" will correct it. A user shown
    "instruction pairs" will not.
    """
    columns = [str(c).strip().lower() for c in (profile_result.get("columns") or [])]
    column_set = set(columns)
    fmt = (profile_result.get("format") or {}).get("name")
    schema = profile_result.get("schema") or {}

    scores: dict[str, float] = {}
    signals: dict[str, list[str]] = {}

    for shape, patterns in SHAPE_SIGNATURES.items():
        best = 0.0
        hit: list[str] = []
        for names, weight in patterns:
            if names <= column_set:
                if weight > best:
                    best = weight
                    hit = sorted(names)
        if best:
            scores[shape] = best
            signals[shape] = [f"columns {', '.join(hit)}"]

    # Structural evidence, which beats a name. A `messages` column holding a
    # list of role/content dicts is chat whatever else the file is called.
    for column in columns:
        column_schema = schema.get(column) or {}
        if column in ("messages", "conversations") and column_schema.get("type") == "list":
            scores["chat"] = max(scores.get("chat", 0.0), 1.2)
            signals.setdefault("chat", []).append(f"{column} holds a list per row")

    if fmt in ("text", "text_folder"):
        scores["raw_text"] = max(scores.get("raw_text", 0.0), 1.0)
        signals.setdefault("raw_text", []).append(f"the format is {fmt}")

    label = profile_result.get("label") or {}
    if label.get("column"):
        distinct = label.get("distinct")
        if isinstance(distinct, int) and 1 < distinct <= 50:
            scores["labelled_classification"] = max(
                scores.get("labelled_classification", 0.0), 1.0
            )
            signals.setdefault("labelled_classification", []).append(
                f"{label['column']} has {distinct} distinct values"
            )

    numeric = sum(
        1
        for column in columns
        if (schema.get(column) or {}).get("type") in ("integer", "number")
    )
    if len(columns) >= 3 and numeric >= max(2, len(columns) // 2):
        scores["tabular"] = max(scores.get("tabular", 0.0), 0.7)
        signals.setdefault("tabular", []).append(
            f"{numeric} of {len(columns)} columns are numeric"
        )

    if not scores:
        scores["tabular"] = 0.2
        signals["tabular"] = ["nothing matched; this is the fallback"]

    for shape in SHAPE_SIGNATURES:
        scores.setdefault(shape, 0.0)

    ranked = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
    total = sum(score for _, score in ranked) or 1.0
    winner, winner_score = ranked[0]
    runner_up, runner_score = ranked[1]

    return {
        "shape": winner,
        "confidence": round(winner_score / total, 2),
        "confidence_provenance": INFERRED,
        "runner_up": runner_up,
        "runner_up_confidence": round(runner_score / total, 2),
        "signals": signals.get(winner, []),
        "must_be_confirmed": True,
        "why_confirmed": (
            "A wrong shape sends the loss function, the prompt template and the "
            "eval metric all the wrong way, and nothing downstream would notice."
        ),
    }


# ---------------------------------------------------------------------------
# The profile
# ---------------------------------------------------------------------------

_INT_RE = re.compile(r"^[+-]?\d+$")
_NUM_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
_BOOLS = frozenset({"true", "false", "yes", "no", "0", "1"})


def _value_type(value: Any) -> str | None:
    """The inferred type of one value, or `None` for a null."""
    if is_null(value):
        return None
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    text = str(value).strip()
    if _INT_RE.match(text):
        return "integer"
    if _NUM_RE.match(text):
        return "number"
    if text.lower() in _BOOLS:
        return "boolean"
    return "string"


def text_of(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    position = (len(values) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(values[low])
    return float(values[low] + (values[high] - values[low]) * (position - low))


def profile(
    path: str | Path,
    *,
    split: str | None = None,
    max_rows: int = DEFAULT_ROW_CAP,
    sample_rows: int = 5,
    near_duplicates: bool = True,
) -> dict[str, Any]:
    """Everything we can measure about one dataset, in one streaming pass.

    The contract that matters is not the field list, it is `checks_not_run`: a
    check that could not run appears there with the reason, and never as a
    silently absent finding. A Parquet file we have no reader for produces an
    empty finding list *and* the sentence explaining that the list is empty
    because nothing was inspected.
    """
    p = Path(path)
    fmt = detect_format(p)

    report: dict[str, Any] = {
        "path": str(p),
        "split": split,
        "exists": p.exists(),
        "format": fmt,
        "readable": bool(fmt.get("readable")),
        "encoding": None,
        "rows": 0,
        "rows_scanned": 0,
        "truncated": False,
        "columns": [],
        "schema": {},
        "duplicates": {},
        "length": {},
        "label": {},
        "degenerate": {},
        "sample": [],
        "notes": [],
        "checks_not_run": [],
        "provenance": {},
    }

    if not p.exists():
        report["notes"].append("The path does not exist, so nothing was profiled.")
        report["checks_not_run"] = _all_checks_not_run("the path does not exist")
        return report

    if not fmt.get("readable"):
        report["notes"].append(
            f"This is a {fmt.get('name') or 'file of unknown type'} "
            f"({fmt.get('how')}). No reader for it ships today, so nothing in "
            "it was inspected. That is not a clean bill of health."
        )
        report["checks_not_run"] = _all_checks_not_run(
            f"no reader ships for {fmt.get('name') or 'this format'}"
        )
        # A REFUSAL ABOUT A FOLDER NAMES THE FILES IN IT. Max's run of
        # 2026-09-19/20: the diagnosis named `assess_the_data` for `classes_n`,
        # the path on the record was a folder of 74 mixed files, and the answer
        # said "no reader ships for folder" eight times and stopped. Six calls
        # in a row got that same dead end, and four sub-agents were killed by
        # the no-blocker rule narrating around it. Every one of those files IS
        # readable on its own - the folder is unreadable only as ONE dataset,
        # because two formats have no column vocabulary between them. Saying so
        # and listing them turns a wall into the next call.
        if p.is_dir():
            inside = _directory_data_files(p)
            if inside:
                # ROW FILES FIRST, and his folder is why: sorted by name, the
                # first forty of 74 were all prose, and `data/splits/eval.jsonl`
                # - the one file this tool exists to profile - fell off the end
                # of the list. A folder's prose is readable; it is not a
                # dataset. Ordering by shape puts the answer where it is read.
                inside.sort(
                    key=lambda one: (
                        one.suffix.lower() not in ROW_EXTENSIONS,
                        str(one),
                    )
                )
                shown = [str(one.relative_to(p)).replace("\\", "/") for one in inside]
                report["data_files_inside"] = shown[:FILES_NAMED_IN_A_REFUSAL]
                report["data_files_inside_count"] = len(shown)
                report["notes"].append(
                    f"The folder holds {len(shown)} data file(s) that each have "
                    "a reader. This refusal is about reading them as ONE "
                    "dataset, which they are not. Point this tool at one of "
                    "them - `data_files_inside` lists them, relative to the "
                    "folder - and it will profile that file."
                )
        return report

    # A limit that bites before the first row is read cannot be noticed from the
    # rows, because there are none. Left unsaid, an unread 60,000-row `.json`
    # file profiled as a dataset with no rows in it, `truncated` false, `rows`
    # provenance MEASURED - and `profile_dataset` and `measure_eval_set` both
    # stamped `eval_size_n = 0` MEASURED off the back of it. `truncated` is set
    # here so that every existing reader of this report, none of which know this
    # limit exists, already handles it: they all treat truncated as "not a count".
    unread = whole_document_limit(p, fmt)
    if unread is not None:
        report["truncated"] = True
        report["unread"] = unread
        report["notes"].append(unread["why"] + " " + unread["what_to_do"])
        report["checks_not_run"] = _all_checks_not_run(
            "the file is a single JSON document too large to parse whole"
        )
        report["provenance"] = {"rows": INFERRED, "format": fmt.get("provenance", DEFAULTED)}
        return report

    if p.is_file():
        try:
            handle, encoding = open_text(p)
            handle.close()
            report["encoding"] = encoding
        except OSError as error:
            report["notes"].append(f"The file could not be read: {error}")
            report["checks_not_run"] = _all_checks_not_run("the file could not be read")
            return report
        if encoding and not encoding.startswith("utf-8"):
            report["notes"].append(
                f"Decoded as {encoding}; it is not valid UTF-8, so some "
                "characters may not be what the author intended."
            )

    columns: list[str] = []
    seen_columns: set[str] = set()
    nulls: dict[str, int] = {}
    present: dict[str, int] = {}
    types: dict[str, dict[str, int]] = {}
    distinct: dict[str, set[str]] = {}
    distinct_capped: dict[str, bool] = {}
    lengths: dict[str, list[int]] = {}

    row_lengths: list[int] = []
    exact_seen: dict[int, int] = {}
    exact_duplicates = 0
    near_duplicate_rows = 0
    near_index = _RowIndex() if near_duplicates else None
    degenerate_hits: dict[str, int] = {}
    short_rows = 0
    sample: list[dict[str, Any]] = []

    def register(name: str) -> None:
        if name in seen_columns or len(columns) >= COLUMN_CAP:
            return
        columns.append(name)
        seen_columns.add(name)
        nulls[name] = 0
        present[name] = 0
        types[name] = {}
        distinct[name] = set()
        distinct_capped[name] = False
        lengths[name] = []

    # Seed from the header before reading a single row, so a header-only file
    # still reports its columns rather than looking like a file with nothing
    # in it at all.
    for name in declared_columns(p, fmt):
        register(name)

    rows = 0
    stream = iter_records(p, fmt)
    for record in stream:
        if rows >= max_rows:
            report["truncated"] = True
            break
        rows += 1

        if not isinstance(record, dict):
            record = {"value": record}

        for key in record:
            register(str(key))

        for name in columns:
            value = record.get(name)
            if is_null(value):
                nulls[name] += 1
                continue
            present[name] += 1
            kind = _value_type(value)
            types[name][kind] = types[name].get(kind, 0) + 1
            text = text_of(value)
            if len(distinct[name]) < DISTINCT_CAP:
                distinct[name].add(text)
            else:
                distinct_capped[name] = True
            if len(lengths[name]) < LENGTH_SAMPLE_CAP:
                lengths[name].append(len(text))

        joined = row_text(record)
        if len(row_lengths) < LENGTH_SAMPLE_CAP:
            row_lengths.append(len(joined))
        if len(joined) < SHORT_ROW_CHARS:
            short_rows += 1

        lowered = joined.lower()
        for marker in DEGENERATE_MARKERS:
            if marker in lowered:
                degenerate_hits[marker] = degenerate_hits.get(marker, 0) + 1

        signature = signature_of_text(joined)
        is_exact_duplicate = signature in exact_seen
        if is_exact_duplicate:
            exact_duplicates += 1
        else:
            exact_seen[signature] = rows

        if near_index is not None:
            prepared = near_index.prepare(joined)
            # Counted only when the row is not already an exact duplicate, so
            # the two figures add up rather than overlap. A reader shown "3%
            # duplicated and 5% near-duplicated" will add them, and they should
            # be right to.
            if not is_exact_duplicate and near_index.matches(joined, prepared=prepared):
                near_duplicate_rows += 1
            near_index.add(rows, joined, prepared=prepared)

        if len(sample) < sample_rows:
            sample.append(
                {
                    "row": rows,
                    "values": {
                        name: _truncate(text_of(record.get(name)))
                        for name in columns
                        if not is_null(record.get(name))
                    },
                }
            )

    # A generator abandoned mid-iteration keeps its file handle open until the
    # collector gets to it. Closing it here runs its `finally` now, which on
    # Windows is the difference between a temp directory that can be removed and
    # one that cannot.
    stream.close()

    report["rows"] = rows
    report["rows_scanned"] = rows
    report["columns"] = columns
    report["sample"] = sample

    if report["truncated"]:
        report["notes"].append(
            f"Scanning stopped at {max_rows:,} rows. Every count below is of the "
            "rows that were scanned, not of the rows that exist."
        )

    if len(columns) >= COLUMN_CAP:
        report["notes"].append(
            f"Only the first {COLUMN_CAP} columns were profiled."
        )

    # "No rows" and "not read" are the same zero here and they are not the same
    # fact. `profile_dataset` stamps `eval_size_n` off this report, so a document
    # that failed to parse must not leave with a count of zero and a MEASURED
    # badge; `truncated` is the flag every existing reader already treats as
    # "this is not the whole count".
    unparsed = json_read_nothing(p, fmt, rows)
    if unparsed is not None:
        report["truncated"] = True
        report["unread"] = unparsed
        report["notes"].append(unparsed["why"] + " " + unparsed["what_to_do"])

    if rows == 0:
        if unparsed is None:
            report["notes"].append(
                "There are no data rows, so no rate can be computed. Nothing here "
                "says the data is clean; it says there is no data."
            )
        report["checks_not_run"].extend(
            [
                {
                    "check": name,
                    "why": (
                        "there are no data rows"
                        if unparsed is None
                        else "no row was read: the document does not parse"
                    ),
                }
                for name in (
                    "duplicates", "near_duplicates", "length_distribution",
                    "label_imbalance", "missing_values", "degenerate_targets",
                )
            ]
        )

    schema: dict[str, Any] = {}
    for name in columns:
        counted = present[name]
        kinds = types[name]
        dominant = max(kinds.items(), key=lambda pair: pair[1])[0] if kinds else None
        mixed = bool(kinds) and (max(kinds.values()) / float(counted or 1)) < 0.95
        column_lengths = sorted(lengths[name])
        schema[name] = {
            "type": ("mixed" if mixed else dominant) if kinds else "empty",
            "type_provenance": INFERRED,
            "type_counts": dict(sorted(kinds.items())),
            "non_null": counted,
            "nulls": nulls[name],
            # Defect 3 lives here. No data rows means no rate, and `None` is the
            # honest answer; `0.0` would read as "no nulls".
            "null_rate": (round(nulls[name] / rows, 4) if rows else None),
            "null_rate_provenance": MEASURED if rows else DEFAULTED,
            "distinct": len(distinct[name]),
            "distinct_is_exact": not distinct_capped[name],
            "distinct_provenance": MEASURED if not distinct_capped[name] else INFERRED,
            "length_chars": {
                "min": column_lengths[0] if column_lengths else None,
                "p50": _percentile(column_lengths, 0.50),
                "p95": _percentile(column_lengths, 0.95),
                "max": column_lengths[-1] if column_lengths else None,
                "basis": (
                    "all non-null values"
                    if counted <= LENGTH_SAMPLE_CAP
                    else f"the first {LENGTH_SAMPLE_CAP:,} non-null values"
                ),
                "unit": "characters",
                "provenance": MEASURED if counted <= LENGTH_SAMPLE_CAP else INFERRED,
            },
            "examples": sorted(distinct[name])[:3] if len(distinct[name]) <= 20 else [],
        }
    report["schema"] = schema

    report["duplicates"] = {
        "exact": exact_duplicates,
        "exact_rate": round(exact_duplicates / rows, 4) if rows else None,
        "near": near_duplicate_rows if near_index is not None else None,
        "near_rate": (
            round(near_duplicate_rows / rows, 4)
            if rows and near_index is not None
            else None
        ),
        "threshold": JACCARD_THRESHOLD,
        "threshold_is": "our policy, not a property of the data",
        "provenance": MEASURED if near_index is not None else DEFAULTED,
        "method": (
            f"exact match on the whole row, plus character {SHINGLE_SIZE}-gram "
            f"shingles compared at Jaccard {JACCARD_THRESHOLD}"
        ),
        "near_excludes_exact": True,
    }
    if near_index is None:
        report["checks_not_run"].append(
            {"check": "near_duplicates", "why": "near-duplicate scanning was turned off"}
        )

    ordered_lengths = sorted(row_lengths)
    report["length"] = {
        "unit": "characters",
        "not_tokens": (
            "Characters, not tokens. Token length needs the candidate model's "
            "own tokenizer, which is a dependency this build does not have; "
            "reporting characters under the word tokens would be a made-up number."
        ),
        "min": ordered_lengths[0] if ordered_lengths else None,
        "p50": _percentile(ordered_lengths, 0.50),
        "p95": _percentile(ordered_lengths, 0.95),
        "max": ordered_lengths[-1] if ordered_lengths else None,
        "short_rows": short_rows,
        "short_row_threshold_chars": SHORT_ROW_CHARS,
        "basis": (
            "all rows" if rows <= LENGTH_SAMPLE_CAP
            else f"the first {LENGTH_SAMPLE_CAP:,} rows"
        ),
        "provenance": MEASURED if rows <= LENGTH_SAMPLE_CAP else INFERRED,
    }

    report["label"] = _label_summary(columns, schema, rows, p, fmt, max_rows)
    report["degenerate"] = {
        "rows_with_markers": sum(degenerate_hits.values()),
        "markers": dict(sorted(degenerate_hits.items())),
        "provenance": MEASURED,
        "method": "substring match against a fixed list of refusal templates",
    }

    report["provenance"] = {
        "rows": MEASURED if not report["truncated"] else INFERRED,
        "columns": MEASURED,
        "encoding": MEASURED,
        "format": fmt.get("provenance", DEFAULTED),
        "duplicates": report["duplicates"]["provenance"],
        "length": report["length"]["provenance"],
        "label": report["label"].get("provenance", DEFAULTED),
    }
    return report


def _truncate(text: str, limit: int = 300) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "..."


def _all_checks_not_run(why: str) -> list[dict[str, str]]:
    return [
        {"check": name, "why": why}
        for name in (
            "row_count", "schema", "duplicates", "near_duplicates",
            "length_distribution", "label_imbalance", "missing_values",
            "degenerate_targets",
        )
    ]


def _label_summary(
    columns: list[str],
    schema: dict[str, Any],
    rows: int,
    path: Path,
    fmt: dict[str, Any],
    max_rows: int,
) -> dict[str, Any]:
    """Which column is the label, and how lopsided it is.

    The choice of column is `inferred` and says so. Getting it wrong is cheap -
    the user reads the name and corrects it - but presenting the guess as a
    measurement would not be.
    """
    if rows == 0 or not columns:
        return {
            "column": None,
            "why": "there are no rows to look at",
            "provenance": DEFAULTED,
        }

    by_name = [c for c in columns if str(c).strip().lower() in LABEL_NAMES]
    candidate = None
    why = ""
    if by_name:
        candidate = by_name[0]
        why = f"the column is named {candidate!r}"
    else:
        # A label has many rows per value. A column with one distinct value per
        # row is an id or a free-text field, and treating it as a label made a
        # preference-pair dataset classify as a classification set - the exact
        # silent misclassification the shape guess exists to prevent.
        ceiling = min(20, max(2, rows // 5))
        low_cardinality = [
            c
            for c in columns
            if schema[c]["distinct"] > 1
            and schema[c]["distinct"] <= ceiling
            and schema[c]["distinct_is_exact"]
            and schema[c]["non_null"] >= max(2, rows // 2)
            and schema[c]["type"] != "list"
        ]
        if low_cardinality and rows >= 20:
            candidate = min(low_cardinality, key=lambda c: schema[c]["distinct"])
            why = (
                f"no column is named like a label, so the lowest-cardinality "
                f"column ({schema[candidate]['distinct']} distinct values) was "
                "used as a guess"
            )

    if candidate is None:
        return {
            "column": None,
            "why": "no column looks like a label",
            "provenance": DEFAULTED,
        }

    counts = _count_values(path, fmt, candidate, max_rows)
    total = sum(counts.values())
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], str(pair[0])))
    majority = ranked[0] if ranked else (None, 0)
    return {
        "column": candidate,
        "why": why,
        "column_provenance": INFERRED,
        "distinct": schema[candidate]["distinct"],
        "counts": dict(ranked[:20]),
        "counts_truncated": len(ranked) > 20,
        "majority_class": majority[0],
        "majority_count": majority[1],
        "majority_share": round(majority[1] / total, 4) if total else None,
        "counted_rows": total,
        "provenance": MEASURED,
    }


def _count_values(
    path: Path, fmt: dict[str, Any], column: str, max_rows: int
) -> dict[str, int]:
    """A second streaming pass, for one column only.

    A second pass rather than holding every value from the first: the first pass
    caps distinct tracking at `DISTINCT_CAP` and cannot produce exact counts, and
    holding every value of every column to avoid this would be the "never load
    the dataset into memory" rule broken to save a file read.
    """
    counts: dict[str, int] = {}
    seen = 0
    stream = iter_records(path, fmt)
    for record in stream:
        if seen >= max_rows:
            break
        seen += 1
        if not isinstance(record, dict):
            continue
        value = record.get(column)
        if is_null(value):
            continue
        key = text_of(value)
        counts[key] = counts.get(key, 0) + 1
    stream.close()
    return counts


# ---------------------------------------------------------------------------
# Leakage
# ---------------------------------------------------------------------------


def find_leakage(
    train_path: str | Path,
    eval_path: str | Path,
    *,
    threshold: float = JACCARD_THRESHOLD,
    max_rows: int = DEFAULT_ROW_CAP,
    max_examples: int = 10,
) -> dict[str, Any]:
    """Rows that appear on both sides of the split.

    This is the check the user cannot run themselves and cannot see by eye, and
    it is the one that decides whether any later number means anything. A single
    leaked row does not degrade the eval, it removes its meaning: the model is
    being scored on material it was trained on, and the score it produces is the
    number the harness would then quote back as a measured baseline for gate G1.

    Both exact and near matches count. Paraphrase, reformatting and a rewritten
    answer key all leak just as thoroughly as a byte-identical copy, and a split
    made by a script that shuffled after deduplicating is the common way it
    happens.
    """
    train = Path(train_path)
    evaluation = Path(eval_path)
    result: dict[str, Any] = {
        "train_path": str(train),
        "eval_path": str(evaluation),
        "ran": False,
        "threshold": threshold,
        "threshold_is": "our policy, not a property of the data",
        "method": (
            f"character {SHINGLE_SIZE}-gram shingles, a bottom-{SKETCH_SIZE} "
            "sketch looked up through an inverted index, verified by exact "
            "Jaccard where both rows were still in memory"
        ),
        "train_rows": 0,
        "eval_rows": 0,
        "leaked_rows": 0,
        "leak_rate": None,
        "exact_matches": 0,
        "near_matches": 0,
        "examples": [],
        "notes": [],
        "checks_not_run": [],
        "provenance": {},
    }

    for label, candidate in (("train", train), ("eval", evaluation)):
        if not candidate.exists():
            result["checks_not_run"].append(
                {"check": "split_leakage", "why": f"the {label} path does not exist"}
            )
            return result
        fmt = detect_format(candidate)
        if not fmt.get("readable"):
            result["checks_not_run"].append(
                {
                    "check": "split_leakage",
                    "why": (
                        f"the {label} file is {fmt.get('name') or 'of unknown type'} "
                        "and no reader for it ships today"
                    ),
                }
            )
            return result

    index = _RowIndex()
    train_fmt = detect_format(train)
    train_rows = 0
    train_excerpts: dict[int, str] = {}
    train_stream = iter_records(train, train_fmt)
    for record in train_stream:
        if train_rows >= max_rows:
            result["notes"].append(
                f"Only the first {max_rows:,} train rows were indexed."
            )
            break
        train_rows += 1
        text = row_text(record)
        index.add(train_rows, text)
        if len(train_excerpts) < 100_000:
            train_excerpts[train_rows] = _truncate(text, 160)
    train_stream.close()

    eval_fmt = detect_format(evaluation)
    eval_rows = 0
    leaked = 0
    exact = 0
    near = 0
    examples: list[dict[str, Any]] = []
    eval_stream = iter_records(evaluation, eval_fmt)
    for record in eval_stream:
        if eval_rows >= max_rows:
            result["notes"].append(
                f"Only the first {max_rows:,} eval rows were checked."
            )
            break
        eval_rows += 1
        text = row_text(record)
        matches = index.matches(text, threshold)
        if not matches:
            continue
        leaked += 1
        best = matches[0]
        if best["basis"] == "exact" and best["similarity"] >= 1.0:
            exact += 1
        else:
            near += 1
        if len(examples) < max_examples:
            examples.append(
                {
                    "eval_row": eval_rows,
                    "eval_excerpt": _truncate(text, 160),
                    "train_row": best["row"],
                    "train_excerpt": train_excerpts.get(best["row"], ""),
                    "similarity": best["similarity"],
                    "similarity_basis": best["basis"],
                    "similarity_provenance": best["provenance"],
                }
            )
    eval_stream.close()

    if index.text_budget_spent:
        result["notes"].append(
            "The train set was too large to hold in memory for exact comparison, "
            "so some similarities are sketch estimates. Each example says which."
        )

    result.update(
        ran=True,
        train_rows=train_rows,
        eval_rows=eval_rows,
        leaked_rows=leaked,
        leak_rate=round(leaked / eval_rows, 4) if eval_rows else None,
        exact_matches=exact,
        near_matches=near,
        examples=examples,
        provenance={
            "train_rows": MEASURED,
            "eval_rows": MEASURED,
            "leaked_rows": MEASURED,
            "leak_rate": INFERRED,
            "exact_matches": MEASURED,
            "near_matches": INFERRED,
        },
    )
    return result


# ---------------------------------------------------------------------------
# The quality report
# ---------------------------------------------------------------------------


def quality_report(
    profile_result: dict[str, Any], leakage: dict[str, Any] | None = None
) -> list[Finding]:
    """Everything wrong with this data, worst first, each with a remediation.

    An empty list from this function means "we looked and found nothing" only
    when `profile_result["checks_not_run"]` is also empty. `describe` says so in
    words, because the difference between "clean" and "not inspected" is the
    difference this module was rewritten to stop blurring.
    """
    findings: list[Finding] = []
    rows = profile_result.get("rows") or 0

    if not profile_result.get("exists"):
        return [
            Finding(
                BLOCK,
                "path_missing",
                "There is nothing at that path, so nothing was checked.",
                "Check the path and attach it again.",
                {"path": profile_result.get("path")},
            )
        ]

    if not profile_result.get("readable"):
        fmt = profile_result.get("format") or {}
        return [
            Finding(
                BLOCK,
                "format_unreadable",
                (
                    f"This looks like a {fmt.get('name') or 'file of an unknown type'} "
                    f"({fmt.get('how')}), and no reader for it ships today. "
                    "Nothing in it has been inspected, so nothing below is a "
                    "clean bill of health."
                ),
                (
                    "Export it to CSV or JSONL and attach that, or wait for the "
                    "reader for this format."
                ),
                {"format": fmt.get("name"), "detected_by": fmt.get("how")},
            )
        ]

    if rows == 0:
        return [
            Finding(
                BLOCK,
                "no_rows",
                "The file has no data rows.",
                "Point at a file that has rows in it, or check the export that produced this one.",
                {"rows": 0, "provenance": MEASURED},
            )
        ]

    if rows < MIN_ROWS_FOR_TRAINING:
        findings.append(
            Finding(
                BLOCK,
                "volume_vs_method",
                (
                    f"{rows:,} rows is not enough to train on. Below about "
                    f"{MIN_ROWS_FOR_TRAINING} usable rows a fine-tune learns the "
                    "examples rather than the task, and you will not be able to "
                    "tell, because there is not enough left over to evaluate with."
                ),
                (
                    "Put these rows in the prompt instead - few-shot prompting "
                    "uses the same examples and costs nothing to undo. Come back "
                    "to training when you have more data than a prompt can hold."
                ),
                {
                    "rows": rows,
                    "rows_provenance": MEASURED,
                    "threshold": MIN_ROWS_FOR_TRAINING,
                    "threshold_is": "our policy, not a property of the data",
                },
            )
        )

    duplicates = profile_result.get("duplicates") or {}
    exact_rate = duplicates.get("exact_rate")
    if exact_rate is not None and exact_rate >= DUPLICATE_BLOCK_RATE:
        findings.append(
            Finding(
                BLOCK,
                "duplicates",
                (
                    f"{duplicates['exact']:,} of {rows:,} rows "
                    f"({exact_rate:.0%}) are exact copies of an earlier row."
                ),
                "Deduplicate before training. Repeated rows are extra weight on whatever they say.",
                {
                    "duplicate_rows": duplicates["exact"],
                    "rate": exact_rate,
                    "provenance": MEASURED,
                    "threshold": DUPLICATE_BLOCK_RATE,
                },
            )
        )
    elif exact_rate is not None and exact_rate >= DUPLICATE_WARN_RATE:
        findings.append(
            Finding(
                WARN,
                "duplicates",
                (
                    f"{duplicates['exact']:,} of {rows:,} rows "
                    f"({exact_rate:.0%}) are exact copies of an earlier row."
                ),
                "Deduplicating is cheap and usually helps. It is not a blocker at this rate.",
                {
                    "duplicate_rows": duplicates["exact"],
                    "rate": exact_rate,
                    "provenance": MEASURED,
                    "threshold": DUPLICATE_WARN_RATE,
                },
            )
        )

    near_rate = duplicates.get("near_rate")
    if near_rate is not None and near_rate >= NEAR_DUPLICATE_WARN_RATE:
        findings.append(
            Finding(
                WARN,
                "near_duplicates",
                (
                    f"{duplicates['near']:,} rows are near-copies of an earlier "
                    f"row (at least {JACCARD_THRESHOLD:.0%} similar), on top of "
                    "the exact duplicates."
                ),
                (
                    "Near-copies are usually a generation script run twice with a "
                    "different seed. Check where they came from before training."
                ),
                {
                    "near_duplicate_rows": duplicates["near"],
                    "rate": near_rate,
                    "provenance": INFERRED,
                    "threshold": NEAR_DUPLICATE_WARN_RATE,
                    "method": duplicates.get("method"),
                },
            )
        )

    schema = profile_result.get("schema") or {}
    for column, stats in schema.items():
        rate = stats.get("null_rate")
        if rate is None:
            continue
        if rate >= 1.0:
            findings.append(
                Finding(
                    BLOCK,
                    "column_entirely_missing",
                    f"The column {column!r} is empty in every one of the {rows:,} rows.",
                    (
                        "Drop the column or fix the export that produced it. An "
                        "empty column that looks populated is how a training run "
                        "ends up learning from nothing."
                    ),
                    {"column": column, "null_rate": rate, "provenance": MEASURED},
                )
            )
        elif rate >= NULL_WARN_RATE:
            findings.append(
                Finding(
                    WARN,
                    "missing_values",
                    f"{rate:.0%} of the values in {column!r} are missing.",
                    "Fill them, drop those rows, or confirm that missing is meaningful here.",
                    {
                        "column": column,
                        "null_rate": rate,
                        "provenance": MEASURED,
                        "threshold": NULL_WARN_RATE,
                    },
                )
            )

    label = profile_result.get("label") or {}
    share = label.get("majority_share")
    if label.get("column") and share is not None:
        evidence = {
            "column": label["column"],
            "column_choice_provenance": label.get("column_provenance", INFERRED),
            "majority_class": label.get("majority_class"),
            "majority_share": share,
            "share_provenance": MEASURED,
            "counts": label.get("counts"),
        }
        if share >= IMBALANCE_BLOCK_SHARE:
            findings.append(
                Finding(
                    BLOCK,
                    "label_imbalance",
                    (
                        f"The label {label['column']!r} is {share:.0%} one class "
                        f"({label.get('majority_class')!r}). A model that always "
                        f"answers that class scores {share:.0%} and has learned nothing."
                    ),
                    (
                        "Rebalance, or change what you measure - accuracy is "
                        "meaningless at this ratio; use per-class recall."
                    ),
                    {**evidence, "threshold": IMBALANCE_BLOCK_SHARE},
                )
            )
        elif share >= IMBALANCE_WARN_SHARE:
            findings.append(
                Finding(
                    WARN,
                    "label_imbalance",
                    (
                        f"The label {label['column']!r} is {share:.0%} one class "
                        f"({label.get('majority_class')!r})."
                    ),
                    (
                        "Report per-class scores, not just accuracy, and consider "
                        "rebalancing before you train."
                    ),
                    {**evidence, "threshold": IMBALANCE_WARN_SHARE},
                )
            )

    degenerate = profile_result.get("degenerate") or {}
    hits = degenerate.get("rows_with_markers") or 0
    if hits:
        findings.append(
            Finding(
                WARN,
                "degenerate_targets",
                (
                    f"{hits:,} rows contain refusal or filler templates such as "
                    "\"As an AI language model\"."
                ),
                (
                    "Remove them. Training on refusals teaches the model to "
                    "refuse, which is rarely what the dataset was collected for."
                ),
                {
                    "rows": hits,
                    "markers": degenerate.get("markers"),
                    "provenance": MEASURED,
                },
            )
        )

    length = profile_result.get("length") or {}
    short = length.get("short_rows") or 0
    if rows and short / rows >= SHORT_ROW_WARN_RATE:
        findings.append(
            Finding(
                WARN,
                "short_rows",
                (
                    f"{short:,} of {rows:,} rows hold fewer than "
                    f"{SHORT_ROW_CHARS} characters of content."
                ),
                "Check whether those rows are truncated or empty placeholders.",
                {
                    "short_rows": short,
                    "rate": round(short / rows, 4),
                    "provenance": MEASURED,
                    "threshold": SHORT_ROW_WARN_RATE,
                },
            )
        )

    if length.get("p95") is not None:
        findings.append(
            Finding(
                INFO,
                "length_distribution",
                (
                    f"Rows are typically {int(length['p50']):,} characters, and "
                    f"95% are under {int(length['p95']):,}."
                ),
                (
                    "This is characters, not tokens. The sequence length a model "
                    "needs is set from tokens, and that measurement needs the "
                    "candidate model's own tokenizer."
                ),
                {
                    "p50": length.get("p50"),
                    "p95": length.get("p95"),
                    "max": length.get("max"),
                    "unit": "characters",
                    "provenance": length.get("provenance", INFERRED),
                    "basis": length.get("basis"),
                },
            )
        )

    if leakage is not None:
        findings.append(leakage_finding(leakage))

    order = {BLOCK: 0, WARN: 1, INFO: 2}
    return sorted(findings, key=lambda f: order.get(f.level, 3))


def leakage_finding(leakage: dict[str, Any]) -> Finding:
    if not leakage.get("ran"):
        why = "; ".join(
            entry.get("why", "") for entry in leakage.get("checks_not_run") or []
        )
        return Finding(
            WARN,
            "split_leakage_not_checked",
            (
                "The train/eval leakage check did not run, so nothing here says "
                "your splits are clean."
                + (f" Reason: {why}." if why else "")
            ),
            "Attach both splits in a readable format and run the check again.",
            {"ran": False},
        )

    leaked = leakage.get("leaked_rows") or 0
    if leaked == 0:
        return Finding(
            INFO,
            "split_leakage",
            (
                f"No leakage found: none of the {leakage.get('eval_rows', 0):,} "
                f"eval rows matched any of the {leakage.get('train_rows', 0):,} "
                "train rows."
            ),
            (
                "This covers the two files given. If you later evaluate against a "
                "benchmark the harness has never seen, the check has to be run again."
            ),
            {
                "train_rows": leakage.get("train_rows"),
                "eval_rows": leakage.get("eval_rows"),
                "threshold": leakage.get("threshold"),
                "provenance": MEASURED,
            },
        )

    return Finding(
        BLOCK,
        "split_leakage",
        (
            f"{leaked:,} of {leakage.get('eval_rows', 0):,} eval rows also appear "
            f"in the train set ({leakage.get('exact_matches', 0):,} identical, "
            f"{leakage.get('near_matches', 0):,} near-identical). Every number "
            "measured against this eval set is invalid, including the baseline."
        ),
        (
            # THE REMEDY HAS TO NAME A DOOR THAT EXISTS. This said "remove the
            # overlapping rows from one side and re-split", and no tool in this
            # product removes them: drop_duplicates is exact-only and says so, and
            # on a real file it left 3 of 30 near-duplicate leaks in place. A
            # refusal whose only instruction cannot be carried out is a dead end
            # wearing the clothes of an action.
            "Re-split with carve_eval_set, which draws whole groups of the same "
            "question - identical and near-identical, transitively - so the split "
            "it makes cannot contain this leak by construction. If these two files "
            "were split by something else, that is where the fix belongs: an "
            "eval row and a train row this similar have to end up on the same "
            "side, and choosing which of two near-identical rows to discard is a "
            "judgement about your data rather than a step a tool can take for "
            "you. Either way, do it before measuring anything: a baseline taken "
            "now is a number about the leak, not about the model."
        ),
        {
            "leaked_rows": leaked,
            "eval_rows": leakage.get("eval_rows"),
            "leak_rate": leakage.get("leak_rate"),
            "exact_matches": leakage.get("exact_matches"),
            "near_matches": leakage.get("near_matches"),
            "examples": leakage.get("examples"),
            "threshold": leakage.get("threshold"),
            "provenance": MEASURED,
        },
    )


# ---------------------------------------------------------------------------
# Plain language
# ---------------------------------------------------------------------------


def describe(
    profile_result: dict[str, Any],
    findings: list[Finding] | None = None,
    leakage: dict[str, Any] | None = None,
) -> str:
    """The report as a colleague would say it out loud.

    `docs/VISION.md`: the harness "profiles what you gave it and describes it
    back to you in plain language". The target sentence is the one in the brief -
    "12,400 rows, 3% duplicated, the label is 80% one class, and 41 rows appear
    in both your train and eval splits" - which is four measurements and no
    jargon, and which a person can act on without opening anything.
    """
    if not profile_result.get("exists"):
        return f"There is nothing at {profile_result.get('path')}, so I could not look."

    fmt = (profile_result.get("format") or {}).get("name") or "file"
    if not profile_result.get("readable"):
        return (
            f"That is a {fmt} and I have no reader for it, so I have not looked "
            "inside. I am not telling you it is fine - I am telling you I could "
            "not check."
        )

    rows = profile_result.get("rows") or 0
    parts: list[str] = []

    columns = profile_result.get("columns") or []
    if rows == 0:
        parts.append("no data rows")
    else:
        parts.append(f"{rows:,} rows")
    if columns:
        parts.append(
            f"{len(columns)} column{'s' if len(columns) != 1 else ''} "
            f"({', '.join(str(c) for c in columns[:6])}"
            f"{', ...' if len(columns) > 6 else ''})"
        )

    duplicates = profile_result.get("duplicates") or {}
    if rows and duplicates.get("exact"):
        parts.append(f"{duplicates['exact_rate']:.0%} duplicated")
    if rows and duplicates.get("near"):
        parts.append(f"{duplicates['near']:,} more rows are near-copies")

    empty_columns = [
        name
        for name, stats in (profile_result.get("schema") or {}).items()
        if stats.get("null_rate") is not None and stats["null_rate"] >= 1.0
    ]
    if empty_columns:
        parts.append(
            f"{', '.join(repr(c) for c in empty_columns)} "
            f"{'is' if len(empty_columns) == 1 else 'are'} empty in every row"
        )

    label = profile_result.get("label") or {}
    if label.get("column") and label.get("majority_share") is not None:
        parts.append(
            f"the label {label['column']!r} is "
            f"{label['majority_share']:.0%} one class"
        )

    length = profile_result.get("length") or {}
    if length.get("p95") is not None:
        parts.append(
            f"95% of rows are under {int(length['p95']):,} characters "
            "(characters, not tokens)"
        )

    if leakage is not None and leakage.get("ran"):
        leaked = leakage.get("leaked_rows") or 0
        if leaked:
            parts.append(
                f"{leaked:,} rows appear in both your train and eval splits"
            )
        else:
            parts.append("no rows appear in both your train and eval splits")

    sentence = _join_plainly(parts)
    text = f"{sentence.capitalize() if sentence[:1].islower() else sentence}."

    not_run = profile_result.get("checks_not_run") or []
    if leakage is not None:
        not_run = list(not_run) + list(leakage.get("checks_not_run") or [])
    if not_run:
        text += (
            " Not everything was checked: "
            + "; ".join(
                f"{entry['check']} ({entry['why']})" for entry in not_run
            )
            + ". Those are unknown, not clean."
        )

    findings = findings if findings is not None else []
    blockers = [f for f in findings if f.level == BLOCK]
    if blockers:
        text += " " + " ".join(f.message for f in blockers)

    return text


def _join_plainly(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if not parts:
        return "nothing to report"
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


# ---------------------------------------------------------------------------
# The original entry point, unchanged in shape
# ---------------------------------------------------------------------------


def data_quality_report(path: str) -> dict[str, Any]:
    """The CSV report other code and older tests already call.

    Kept at its published shape on purpose. `profile` is the one to reach for in
    new work - it streams, it handles more than CSV, and every number it returns
    carries provenance - but quietly changing the keys under a caller is how a
    fix becomes an outage.
    """
    if not Path(path).exists():
        return {
            "rows": 0,
            "null_rate": {},
            "duplicates": 0,
            "columns": [],
            "encoding": None,
            "notes": ["File does not exist."],
        }

    fieldnames, records, encoding = read_rows(path)
    rows = len(records)
    notes: list[str] = []
    if not encoding.startswith("utf-8"):
        notes.append(
            f"Decoded as {encoding}; it is not valid UTF-8, so some characters "
            f"may not be what the author intended."
        )
    if not fieldnames:
        notes.append("The file has no header row, so there are no columns to profile.")

    null_rate: dict[str, float | None] = {}
    for column in fieldnames:
        if rows == 0:
            # No data rows means no rate. Reporting 0.0 here would say "clean",
            # which is the same silent lie as defect 3.
            null_rate[column] = None
            continue
        count_nulls = sum(1 for record in records if is_null(record.get(column)))
        null_rate[column] = round(count_nulls / rows, 2)

    if rows == 0 and fieldnames:
        notes.append("Header only: no data rows, so no null rate can be computed.")

    seen_tuples: set[tuple[Any, ...]] = set()
    duplicates = 0
    for record in records:
        # Normalise None and "" to one token so two identical rows are not
        # treated as different because one was short.
        signature = tuple(
            "" if is_null(record.get(column)) else str(record.get(column))
            for column in fieldnames
        )
        if signature in seen_tuples:
            duplicates += 1
        else:
            seen_tuples.add(signature)

    return {
        "rows": rows,
        "null_rate": null_rate,
        "duplicates": duplicates,
        "columns": fieldnames,
        "encoding": encoding,
        "notes": notes,
    }
