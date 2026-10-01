"""The first thing in this harness that changes a user's disk.

`docs/VISION.md`: *"Data is something we work on, not only something we read.
[...] Every one of these writes a new dataset rather than editing the old one,
and records what it did, so a mistake is one sentence to undo."* This module is
the first half of that sentence being true.

Until now it was not. Fourteen tools sit in the Data group and every `writes=`
among them is `facts`, `evals`, `prompts` or `retrieval` - never a file. The
product even said so out loud: part five of `assess_the_data` computes how many
rows an eval set would take, how many would be left, and then ended *"Nothing
has been carved and no file has been written."* A product that announces the
thing it will not do has named its next piece of work.

## Why this is a sibling of `app/tools/data.py` and not more of it

`data.py` is the READING half and its own docstring is a contract: *"None of
them decides anything. They return facts and findings."* Every tool in it is
`writes=()` or `writes=("facts",)`, and not one of them can create a file. That
is worth being able to check in one place rather than tool by tool, so the file
boundary is the check: **every tool that can write to the user's disk is
declared in this module, and no tool declared in `data.py` may write one.**
`tests/test_the_harness_writes_a_dataset_and_says_so.py` asserts both halves
against the registry, which turns a preference about where code lives into a
property a future author cannot quietly break by adding a write to the reader.

The reading is still `data.py`'s and is imported rather than repeated:
`data.eval_set_floor()` reads G0's threshold, `data.check_split_leakage` is the
verification, `data.bounded` is the same clamp on `max_rows`, and
`dataquality.row_signature` is the one definition of "the same row" that the
profiler, the assessor and the writer below all count with.

## Approval, and why these two tools have it when `make_sandbox` does not

`docs/ARCHITECTURE.md` 8: *"any tool call the model proposes that touches the
network or the filesystem outside the run directory goes through the approval
path regardless of what the model claims it was told."* `make_sandbox` writes
under `runs/`, which is the run directory. These write wherever the person
points them, which is not. So both declare `approval="always"`: a model that
calls one is told, by `Registry.call`, that an approval is a person saying yes
and does not travel in a tool call. What the model CAN do without one is run
`assess_the_data`, which now names this tool in part five and says what it would
carve, so the conversation still reaches the offer.

## Four properties, and each one is in the code rather than in this docstring

**NEVER OVERWRITE, NEVER IN PLACE.** The output directory is claimed with a
bare `Path.mkdir(parents=True)` - no `exist_ok` - which is one syscall that
creates and claims at once and fails if anything is already there. That is the
guard, and it is a guard rather than a check-then-write because a
check-then-write has a window in it. Nothing is opened for writing until that
call has returned, so a refused run cannot have touched a byte. `_claim` also
refuses a destination inside a source FOLDER, because our output landing inside
somebody's dataset directory means their next profile counts our files as their
rows.

**AND THAT REASON WAS NEVER ABOUT THE SOURCE, WHICH IS WHERE THE GUARD WAS
WRONG.** Carving `graded.csv` into `corpus/carved`, where `corpus` is a folder
of `.txt` documents nobody mentioned, went through and returned `ok: true` - and
`corpus` went from `text_folder, readable: True` to `folder, readable: False` in
the same call, because `detect_format` calls a directory readable only when
every data file under it is text. A dataset the call was not asked to touch
stopped being openable by every tool in this product, silently.
`_dataset_that_would_be_broken` is the other half, and it climbs the ancestors
because `mkdir(parents=True)` creates levels and `_directory_data_files` is
`rglob`.

A write that fails PART WAY is covered by neither, and the fragments it left
used to carry the exact names a finished carve produces, with no manifest:
`check_split_leakage` over them answered "No overlap: none of the 7 eval rows
matched any of the 18 train rows" and `measure_eval_set` would have counted one.
`_mark_as_partial` renames them and writes the manifest that says the operation
did not finish, because the reply is a sentence in a conversation and the
directory is what is there tomorrow.

**IT SAYS WHERE IT CAME FROM.** Every run writes `ml_harness_manifest.json`
beside its output: what wrote it, which code (sha and fingerprint from
`app/identity.py`), the source path with its size and sha256, the rule that
decided the split with every parameter it took, and the sha256 and row count of
each file written. The rows that moved carry their source row numbers there too,
because the other file is the complement and one list reconstructs both.

THE ROWS THEMSELVES ARE WRITTEN VERBATIM, and that is a decision with a reason.
Stamping each row with its origin is the obvious way to keep provenance in the
new medium, and it defeats the verification: `check_split_leakage` compares rows
as text, so a per-row `{"split": "eval"}` would make every eval row differ from
every train row and the leak check would come back clean on any input at all. A
provenance mark that disables the check provenance exists for is worse than no
mark.

**REPRODUCIBLE, AND THE RULE IS THE RECORD.** Which rows go to eval is decided
by hashing the row, not by shuffling: a row is in the eval set when
`signature_of_text("carve_eval_set/v1|<seed>|<row signature>")` is among the
lowest for the rows that qualify. Three consequences, and the third is the one
worth the strangeness - the same call gives the same split on any machine and in
any process; the split does not depend on the order the rows were read in; and
TWO ROWS THAT ARE THE SAME ROW HASH THE SAME AND CANNOT LAND ON OPPOSITE SIDES,
so exact-duplicate leakage across a split we wrote is impossible by construction
rather than by inspection.

**WE CHECK OUR OWN WORK.** `carve_eval_set` runs the real `check_split_leakage`
over the two files it has just written and puts the answer in its own reply and
in the manifest. `drop_duplicates` re-reads what it wrote with
`dataquality.profile` and reports the duplicate count found in it. A split this
harness produced and did not verify is worse than one a user made, because ours
came with an implied promise.

## THE LINE, WHICH IS NOT A TECHNICAL ONE

G0's own recipe, in `docs/diagnosis_engine.yaml`, read from the file rather than
typed here: *"30-50 real inputs sampled from actual traffic, graded by the
person who cares about the answer."*

**Splitting is mechanical. Grading is judgement.** A held-out slice of
unlabelled rows is a pile of inputs with no right answers, and handing one over
as an eval set would be the five-gate test defeated by a file we wrote
ourselves. So `carve_eval_set` requires `answer_column` and will not carve
unless three things are true of it, each read off the disk:

* the column is one the file actually has;
* at least one row has a value in it - a column that is present and empty is a
  column somebody added and never filled;
* the answers are not all one value. At or above
  `dataquality.IMBALANCE_BLOCK_SHARE` this harness already calls that "one class
  with a label column, not a classification set", and an eval set of it measures
  nothing, because always answering the majority already scores that share.

None of that can tell whether a human graded the rows, and this module never
claims it can. What it claims is narrower and true: these rows already carried
answers, and here is the same set of them split in two.

**AND THE NUMBER THE THRESHOLD IS ABOUT IS DISTINCT ROWS.** G0 asks for "30-50
real inputs"; the same input forty times is one input. The draw counted ROWS,
so a support export of two hundred tickets that are five tickets repeated forty
times each carved clean - a forty-row eval file holding ONE distinct question,
`ok: true`, `check_split_leakage` reporting "No overlap", and `measure_eval_set`
ready to stamp `eval_size_n = 40` MEASURED. That is the sentence above coming
true with the answers present: the five-gate test opened by a file this harness
wrote itself. `_choose` counts groups, that file is now refused with what is
actually short, and a carve whose eval file holds more rows than distinct ones
says both numbers.

## AND IT MAY NOT MEASURE ANYTHING

`measures=()` on both tools, and neither handler takes an `instrument`, so
`ToolSpec.wants_instrument` is False and there is no object in scope that could
stamp. It is a shape rather than a policy.

The reason is the difference between two sentences. *"I wrote 40 rows"* is this
process's own arithmetic. *"A tool counted 40 rows in a file that exists"* is a
claim about the world, and it is the second one G0 reads. `eval_size_n` is
declared `source: inspect` and `measure_eval_set` is its instrument. A tool that
wrote a file and then stamped its own row count would open the first gate on a
number it made up on the way past - a file we wrote ourselves opening the gate
that exists to stop us. So the carve ends by naming `measure_eval_set` and
stops.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app import dataquality, diagnosis, identity
from app.tools import data
from app.tools.registry import tool


#: The most rows either tool will read. It is not a cap on the ANSWER: a
#: truncated read here would write a "deduplicated" file missing the tail of
#: somebody's data, or a "training" file that is not the complement of the eval
#: set. So when it bites, nothing is written at all and the reply says to raise
#: it. That is the opposite of what `max_rows` means to `profile_dataset`, and
#: the difference is the whole reason a reader may truncate and a writer may not.
DEFAULT_ROW_LIMIT = data.DEFAULT_ROW_LIMIT
MAX_ROW_LIMIT = 5_000_000

#: The file that says who wrote this directory. Named for the product rather
#: than `manifest.json`, so a directory of output identifies its author from the
#: listing alone.
MANIFEST_NAME = "ml_harness_manifest.json"

#: Everything is written as JSON Lines whatever came in. One object per line is
#: the only shape that survives a source whose rows do not all carry the same
#: columns - which a JSON or JSONL source routinely does not - and rewriting
#: those rows as CSV would have to invent empty cells or drop fields.
WRITTEN_FORMAT = "jsonl"

#: Prefixed into the selection hash so the same seed under a future rule does
#: not silently reproduce this one's split. If the rule changes, this string
#: changes with it and an old manifest stays checkable against the version it
#: names.
SELECTION_RULE = "carve_eval_set/v1"

#: What both tools mean by "the same row", in one sentence, written once and put
#: in the manifest. The sentence and the code cannot drift, because the code is
#: `dataquality.row_signature` and there is one of it.
DUPLICATE_IS = (
    "Two rows are the same row when their non-null values, joined in order with "
    "spaces, are identical after collapsing whitespace and lower-casing. Column "
    "names are not part of it, so two rows saying the same thing under "
    "differently spelled columns are duplicates. This is "
    "dataquality.row_signature, the same definition profile_dataset and "
    "assess_the_data report their duplicate counts under."
)

#: What the manifest says about itself. It is a record of one operation and it
#: is deliberately not evidence of anything: a gate opens on a tool's reading of
#: a file that exists, never on a file's account of its own making.
MANIFEST_IS = (
    "A record of one operation this harness performed to produce the files "
    "beside it. Nothing in it is a measurement of those files: it says what was "
    "written and how, and a count in here is this program's own arithmetic. To "
    "have the size of an eval set recorded as measured, run measure_eval_set on "
    "the file - that counts the rows that are actually there."
)

_SAFE_STEM = re.compile(r"[^A-Za-z0-9._-]+")

_HASH_CHUNK = 1 << 20


class Refusal(Exception):
    """Something that stops the write, carrying the reply that says so.

    An exception rather than a returned dict because the checks run in a fixed
    order across a streaming pass, and a returned refusal has to be threaded
    back out through every loop by hand - which is how a check ends up reached
    on some paths and not others. `payload` is the tool result verbatim.
    """

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(str(payload.get("summary") or payload.get("error")))
        self.payload = dict(payload)


def _refuse(error: str, summary: str, **rest: Any) -> Refusal:
    """A refusal in the shape every one of them has.

    `nothing_was_written` on all of them, and it is literally true rather than
    reassuring: every raise below happens before `_claim`, which is the only
    call in this module that creates anything.
    """
    return Refusal(
        {
            "ok": False,
            "error": error,
            "summary": summary,
            "nothing_was_written": True,
            **rest,
        }
    )


def _digest(path: Path) -> tuple[int, str]:
    """`(bytes, sha256)`, read in chunks.

    In chunks because this runs over a file this module has just written, which
    may be the whole of somebody's training data; `path.read_bytes()` to hash it
    would put a dataset in memory at the end of a job that carefully streamed it.
    """
    total = 0
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
    return total, digest.hexdigest()


# ---------------------------------------------------------------------------
# The destination, which is the one thing here that could destroy something.


def _clean_stem(source: Path) -> str:
    """The source's own name, safe to build a filename out of.

    The output is named after the input on purpose - `tickets.eval.jsonl` says
    where it came from without opening anything. The characters are filtered
    because that name came off somebody's filesystem and is about to become one.
    """
    stem = _SAFE_STEM.sub("_", source.stem or source.name or "").strip("._-")
    return stem or "dataset"


#: How many filesystem entries the ancestor check below will look at for one
#: directory before it gives up on it. It is not a silent truncation: reaching
#: it with no data file seen means the directory holds none in the first fifty
#: thousand entries, which is not a dataset any reader here would open, and the
#: reply says the check stopped there.
ANCESTOR_SCAN_CAP = 50_000

#: `dataquality.detect_format`'s rule for a readable folder, read here rather
#: than re-derived: a directory is `text_folder` when it holds at least one data
#: file and every data file under it is one of these.
_TEXT_FOLDER_SUFFIXES = frozenset({".txt", ".md"})


def _reads_as_a_folder_dataset(directory: Path) -> str:
    """Would `profile_dataset` read this directory as a dataset? Walk and see.

    `dataquality.detect_format` calls a directory `text_folder` - readable, one
    row per file - when `_directory_data_files` finds at least one data file
    under it and every one of them is `.txt` or `.md`. Anything else under it
    and the directory is `folder`, `readable: False`, and every tool in this
    product refuses it.

    THE EARLY EXIT IS WHAT MAKES THE CHECK ABOVE AFFORDABLE, and it is also what
    makes it complete. The first non-text data file settles this directory AND
    every directory above it, because the subtree that disqualifies this one is
    inside all of them. So the walk up the ancestors stops at the first "no",
    and the only directories walked to the end are the ones that are datasets.

    Returns `"dataset"`, `"no"` (and nothing above it can be one either),
    `"nothing_to_read"` (no data file here, so an ancestor still might be one),
    or `"gave_up"` at `ANCESTOR_SCAN_CAP`.
    """
    seen = 0
    text_files = 0
    try:
        for candidate in directory.rglob("*"):
            seen += 1
            if seen > ANCESTOR_SCAN_CAP:
                return "dataset" if text_files else "gave_up"
            suffix = candidate.suffix.lower()
            if suffix not in dataquality.DATA_EXTENSIONS:
                continue
            if not candidate.is_file():
                continue
            if suffix not in _TEXT_FOLDER_SUFFIXES:
                return "no"
            text_files += 1
    except OSError:  # a tree the OS will not walk is not a dataset we can read
        return "gave_up"
    return "dataset" if text_files else "nothing_to_read"


def _dataset_that_would_be_broken(destination: Path) -> Path | None:
    """The folder dataset this destination would land inside, if there is one.

    THE GUARD BELOW HAD THIS HALF. `_claim` refuses a destination inside the
    folder it is READING, and the docstring's reason - "our output landing
    inside somebody's dataset directory means their next profile counts our
    files as their rows" - is not about the source at all. Carving
    `graded.jsonl` into `corpus/carved`, where `corpus` is a folder of `.txt`
    documents, went through: the carve returned `ok: true`, and `corpus` went
    from `text_folder, readable: True, 5 files` to `folder, readable: False, 8
    files` in the same call. A dataset the person never mentioned stopped being
    readable by every tool in this product, and nothing said so.

    Climbs from the nearest existing ancestor. `mkdir(parents=True)` may create
    several levels, and `_directory_data_files` is `rglob`, so a file written at
    any depth counts as a row of every dataset above it.
    """
    for ancestor in (destination, *destination.parents):
        if not ancestor.is_dir():
            continue
        verdict = _reads_as_a_folder_dataset(ancestor)
        if verdict == "dataset":
            return ancestor
        if verdict in ("no", "gave_up"):
            return None
    return None


def _next_free(wanted: Path) -> Path:
    """`wanted` if nothing is there, else `wanted-2`, `wanted-3`, ... - the
    first name beside it that nothing occupies."""
    if not wanted.exists() and not wanted.is_symlink():
        return wanted
    for n in range(2, 1000):
        candidate = wanted.parent / f"{wanted.name}-{n}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    return wanted


def _claim(into: Any, source: Path) -> Path:
    """Take exclusive ownership of a new directory, or refuse. Nothing else.

    A directory that already exists, or that is the source's own folder, is
    not refused any more: the next free name beside it is taken and returned,
    and every caller reports the directory it was handed as `into`.

    `mkdir(parents=True)` WITHOUT `exist_ok` is the guard, and it is one call:
    the directory is created and claimed in the same syscall, so there is no
    window between "it was not there" and "it is mine". Every other check here
    is about a destination that would be legal and still wrong.
    """
    text = str(into or "").strip()
    if not text:
        raise _refuse(
            "no_destination",
            "No destination was given, so nothing was written. `into` names a "
            "NEW directory for the files - it must not already exist, because "
            "nothing here writes over anything.",
        )

    destination = Path(text).expanduser()
    try:
        resolved = destination.resolve()
        origin = source.resolve()
    except OSError as error:  # a path the OS will not even resolve
        raise _refuse(
            "unusable_destination",
            f"{destination} could not be resolved as a path on this machine "
            f"({type(error).__name__}), so nothing was written.",
            into=str(destination),
        ) from error

    if resolved == origin or resolved in origin.parents:
        # NOT A WALL. Max, 2026-09-17: judge_rows and draw_verification_sample
        # both refused because the model named the folder the rows were in.
        # Nothing here writes in place - that rule stands - so the output goes
        # to the next free folder BESIDE it, and the result names where.
        destination = _next_free(destination.parent / (destination.name + "-out"))
        resolved = destination.resolve()
    if destination.is_dir() and not destination.is_symlink():
        # A folder that already exists gets the next free name beside it:
        # generate_rows was refused four times on thread 75 for naming one.
        # A FILE at the destination is still refused below - that is a
        # person's file, not a folder somebody meant to fill.
        destination = _next_free(destination)
        resolved = destination.resolve()
    if origin.is_dir() and origin in resolved.parents:
        # Found by thinking about `text_folder`: a folder dataset is read as one
        # row per file under it, so output written inside it becomes rows of the
        # source the next time anybody profiles it.
        raise _refuse(
            "would_write_inside_the_source",
            f"{resolved} is inside {origin}, which is the dataset being read. A "
            "folder dataset is one row per file, so files written in there "
            "become rows of it. Name a directory outside it.",
            into=str(resolved),
            source=str(origin),
        )
    if destination.exists() or destination.is_symlink():
        raise _refuse(
            "destination_exists",
            f"{destination} already exists, and nothing here writes over "
            "anything. Name a directory that does not exist yet; it will be "
            "created.",
            into=str(destination),
        )

    broken = _dataset_that_would_be_broken(resolved)
    if broken is not None:
        raise _refuse(
            "would_write_inside_a_dataset",
            f"{resolved} is inside {broken}, which this harness reads as a "
            "dataset today - a folder of text files, one row per file. The "
            f"{WRITTEN_FORMAT} files this would write under it make it a folder "
            "of mixed types, which profile_dataset and assess_the_data then "
            "refuse to read at all. That is a dataset you did not ask this to "
            "touch, broken by where the output went. Nothing was written. Name "
            "a directory outside it.",
            into=str(resolved),
            dataset=str(broken),
        )

    try:
        destination.mkdir(parents=True)
    except FileExistsError as error:
        raise _refuse(
            "destination_exists",
            f"{destination} was created by something else between the check and "
            "the write, so nothing was written. Name a directory that does not "
            "exist yet.",
            into=str(destination),
        ) from error
    except OSError as error:
        raise _refuse(
            "destination_not_writable",
            f"{destination} could not be created: {type(error).__name__}: "
            f"{error}. Nothing was written.",
            into=str(destination),
        ) from error
    return destination


# ---------------------------------------------------------------------------
# Reading, bounded so that a partial read can never become a written file.


def _readable(path: Any) -> tuple[Path, dict[str, Any]]:
    """The source, resolved, with its format - or a refusal saying which."""
    resolved = Path(str(path or "").strip() or ".").expanduser()
    if not resolved.exists():
        raise _refuse(
            "not_found",
            f"There is nothing at {resolved}, so nothing was read and nothing "
            "was written.",
            path=str(resolved),
        )
    fmt = dataquality.detect_format(resolved)
    if not fmt.get("readable"):
        raise _refuse(
            "unreadable_format",
            f"That is a {fmt.get('name') or 'file of unknown type'} "
            f"({fmt.get('how')}) and no reader for it ships today. Nothing was "
            "read - which is not the same as nothing being wrong with it - and "
            "nothing was written.",
            path=str(resolved),
            format=fmt,
        )
    return resolved, fmt


def _records(path: Path, fmt: dict[str, Any], limit: int) -> Iterator[dict[str, Any]]:
    """Stream the source, refusing rather than truncating at `limit`.

    `dataquality.iter_records` is the one reader; this only bounds it and wraps
    a non-dict row the same way `profile` does. The generator is closed in
    `finally` because an abandoned one keeps its file handle open until the
    collector runs, which on Windows is the difference between a temporary
    directory that can be removed and one that cannot.
    """
    seen = 0
    stream = dataquality.iter_records(path, fmt)
    try:
        for record in stream:
            seen += 1
            if seen > limit:
                raise _refuse(
                    "more_rows_than_the_limit",
                    f"{path} has more than {limit:,} rows. Nothing was written: "
                    "a file written from a partial read would be missing the "
                    "rest of your data and would not say so. Raise max_rows past "
                    "the end of the file and run it again.",
                    path=str(path),
                    max_rows=limit,
                )
            yield record if isinstance(record, dict) else {"value": record}
    finally:
        stream.close()


# ---------------------------------------------------------------------------
# Writing, and the record of it.


def _line(record: dict[str, Any]) -> str:
    """One row as one line. The row is the user's and is not edited.

    No column is added, removed or renamed. See the module docstring for why a
    per-row provenance stamp is the one obvious idea this refuses.
    """
    return json.dumps(record, ensure_ascii=False) + "\n"


def _written(path: Path, rows: int) -> dict[str, Any]:
    size, sha = _digest(path)
    return {
        "file": path.name,
        "path": str(path),
        "rows": rows,
        "bytes": size,
        "sha256": sha,
        "format": WRITTEN_FORMAT,
    }


def _source_record(path: Path, fmt: dict[str, Any], rows: int) -> dict[str, Any]:
    """What the input was when it was read, in enough detail to tell later.

    Size and sha256 both, because "is this the same file I carved from" is the
    first question anybody asks of a split that looks wrong, and a path is not
    an answer to it. A folder gets no digest - it is many files - and says so
    rather than reporting a null nobody can interpret.
    """
    record: dict[str, Any] = {
        "path": str(path),
        "format": fmt.get("name"),
        "format_how": fmt.get("how"),
        "rows_read": rows,
    }
    if path.is_file():
        size, sha = _digest(path)
        record["bytes"] = size
        record["sha256"] = sha
    else:
        record["bytes"] = None
        record["sha256"] = None
        record["note"] = (
            "The source is a directory, so there is no single file to digest. "
            "The row count is the measurement of what was read."
        )
    return record


def _harness() -> dict[str, Any]:
    """Which code wrote this, off `app/identity.py` rather than a version here.

    A file that says "written by ml-harness" and does not say WHICH ml-harness
    is a file nobody can reproduce. The sha and the fingerprint are the same two
    figures `/health` publishes, so a manifest and a running engine can be
    compared without either of them being asked to remember anything.
    """
    build = identity.build()
    return {
        "product": "ml-harness",
        "sha": build.get("sha"),
        "code_fingerprint": build.get("code_fingerprint"),
        "code_files": build.get("code_files"),
        "python": build.get("python"),
    }


def _write_manifest(directory: Path, body: dict[str, Any]) -> dict[str, Any]:
    path = directory / MANIFEST_NAME
    payload = {
        "written_by": _harness(),
        "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "this_file_is": MANIFEST_IS,
        **body,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"file": path.name, "path": str(path)}


#: What a half-written file is renamed to. A fragment that keeps the name a
#: finished file would have had is the defect below; this is the mark that
#: cannot be missed by anything, including a person reading a directory listing
#: and a tool asked to open `tickets.eval.jsonl` by name.
PARTIAL_SUFFIX = ".partial"


def _mark_as_partial(directory: Path, error: Exception) -> list[dict[str, Any]]:
    """Rename what was half-written and leave a manifest saying it is a fragment.

    THE DIRECTORY IS NOT CLEANED UP, and that is deliberate twice over. Deleting
    is the one thing this module does not do; and it does not need to, because
    `_claim` created the directory in this call, so everything in it is ours and
    the user's data has not been touched.

    **BUT UNTOUCHED IS NOT THE SAME AS HARMLESS, AND THIS IS WHERE IT WAS.** A
    write that stopped after twenty-five rows left `tickets.eval.jsonl` and
    `tickets.train.jsonl` - the exact names a finished carve produces - with no
    manifest and nothing else in the directory. `check_split_leakage` on the two
    fragments came back "No overlap: none of the 7 eval rows matched any of the
    18 train rows", and `measure_eval_set` on the eval fragment would have
    counted it and opened G0 on a truncated file. The reply said `ok: false` and
    the reply is a sentence in a conversation; the directory is what is still
    there tomorrow. So the fragment is renamed and the manifest that says what
    happened is written beside it, and both are best-effort: a disk that just
    refused a write may refuse these too, and the original error is what gets
    reported either way.
    """
    marked: list[dict[str, Any]] = []
    for path in sorted(directory.glob(f"*.{WRITTEN_FORMAT}")):
        try:
            target = path.with_name(path.name + PARTIAL_SUFFIX)
            path.rename(target)
            marked.append({"was": path.name, "is_now": target.name})
        except OSError:  # noqa: PERF203 - a rename we could not do is reported
            marked.append({"was": path.name, "is_now": None})
    try:
        _write_manifest(
            directory,
            {
                "operation": "write_failed",
                "complete": False,
                "this_directory_holds": (
                    "FRAGMENTS OF AN OPERATION THAT DID NOT FINISH. Nothing here "
                    "is a dataset. The files were renamed to end in "
                    f"{PARTIAL_SUFFIX} so that nothing opens one by the name a "
                    "finished file would have had."
                ),
                "failed_with": f"{type(error).__name__}: {error}",
                "renamed": marked,
            },
        )
    except OSError:
        pass
    return marked


def _write_failed(directory: Path, source: Path, error: Exception) -> dict[str, Any]:
    """A failure part-way through writing, reported AND marked on disk."""
    marked = _mark_as_partial(directory, error)
    return {
        "ok": False,
        "error": "write_failed",
        "summary": (
            f"It could not be written: {type(error).__name__}: {error}. Your "
            f"data was not touched - {directory} was created by this call and "
            "holds only whatever had been written when it stopped, so removing "
            f"it loses nothing. What is in there was renamed to end in "
            f"{PARTIAL_SUFFIX} and a manifest beside it says the operation did "
            "not finish, so nothing downstream can open a fragment under the "
            "name a finished file would have had."
        ),
        "into": str(directory),
        "path": str(source),
        "nothing_usable_was_written": True,
        "renamed": marked,
    }


# ---------------------------------------------------------------------------
# The split rule.


def _selection_key(seed: str, signature: int) -> int:
    """Where this row sits in the draw. A hash of the row, not a shuffle.

    Hashing the ROW rather than its position is what makes two identical rows
    take the same side of the split: same signature, same key, so no ordering of
    the draw can separate them. That single property is why a carve cannot leak
    an exact duplicate across its own split - and it is checked afterwards
    anyway, because a property nobody verified is a claim.
    """
    return dataquality.signature_of_text(f"{SELECTION_RULE}|{seed}|{signature}")


def _choose(
    groups: dict[int, dict[str, int]],
    eligible: list[int],
    seed: str,
    want: int,
    cluster_of: dict[int, int],
) -> tuple[set[int], int]:
    """The lowest-keyed CLUSTERS until there are enough distinct questions.

    TAKING WHOLE GROUPS IS THE POINT. Selecting rows would let the count land in
    the middle of a run of identical rows and put the same row on both sides,
    which is the leak this split exists not to create. So the eval set can come
    out slightly LARGER than asked for, and never smaller - a short eval set is
    one that does not clear the threshold it was sized by.

    **AND THE THING BEING COUNTED IS THE GROUP, NOT THE ROW.** This counted rows
    until it had thirty of them, and on a support export of two hundred tickets
    that are five tickets repeated forty times each it stopped after the first
    group: a forty-row eval file holding ONE distinct question, `ok: true`,
    `check_split_leakage` reporting "No overlap", and `measure_eval_set` then
    stamping `eval_size_n = 40` MEASURED. That is the five-gate test opened by a
    file this harness wrote itself, which is the one thing the module docstring
    above says this tool exists not to do. G0 asks for "30-50 real inputs"; the
    same input forty times is one input, and the count that decides has to be
    the count of distinct inputs.

    **AND THE GROUP IS THE NEAR-DUPLICATE CLUSTER, NOT THE EXACT-DUPLICATE ONE.**
    That argument was made for byte-identical rows and stopped one step short of
    where its own checker already stood. `check_split_leakage` counts a pair over
    Jaccard 0.8 as a leak, so a draw that only kept IDENTICAL rows together was
    being judged by a predicate it had made no attempt to satisfy - and could
    only pass by luck. Measured, on a 161-row dataset built from this
    repository's own git log: 12 of 25 seeds came back leaking, 3 came back
    clean, and the remaining 10 refused before writing for an unrelated reason.
    On a 160-row fixture with no exact duplicates at all: 25 of 25 leaked, all 30
    eval rows every time. With the draw made in these units the same file gives
    0 leaks over the same 25 seeds. The remedy it printed - remove the
    overlapping rows and re-split - was implemented by no tool in the product.

    Two consequences, and both are the honest direction:

      * the split now satisfies the check by construction rather than by seed
        luck, so `verification` is a proof rather than a coin toss;
      * a paraphrase of a question already held out is the same question, so it
        no longer counts twice toward the number G0 asks for. A file of five
        questions rephrased forty times now REFUSES instead of writing an eval
        set that measures one thing forty times.
    """
    by_cluster: dict[int, list[int]] = {}
    for signature in eligible:
        by_cluster.setdefault(cluster_of.get(signature, signature), []).append(signature)
    ranked = sorted(
        by_cluster,
        key=lambda cluster: (_selection_key(seed, cluster), cluster),
    )
    chosen: set[int] = set()
    clusters = 0
    rows = 0
    for cluster in ranked:
        if clusters >= want:
            break
        clusters += 1
        for signature in by_cluster[cluster]:
            chosen.add(signature)
            rows += groups[signature]["rows"]
    return chosen, rows


# ---------------------------------------------------------------------------
# What G0 asks for, and what G0 says about how an eval set is built.


def _g0(spec: diagnosis.Spec | None = None) -> tuple[int, dict[str, Any]]:
    """The eval-set floor, and the engine's own words about grading.

    The floor comes from `data.eval_set_floor`, which finds the gate by the fact
    it reads - `eval_size_n` - in the ledger this thread is running. It is the
    same reading `propose.g0_minimum` takes for the build it proposes, and
    `tests/test_the_harness_writes_a_dataset_and_says_so.py` asserts the two
    agree - so a threshold cannot move for the proposer and not for the carve.

    A floor invented here would be the fabrication invariant wearing the
    engine's name, so a spec that cannot be read refuses instead of falling back.
    """
    current = spec or diagnosis.default_spec()
    floor = data.eval_set_floor(current)
    want = floor.get("rows")
    if not isinstance(want, int) or want <= 0:
        raise _refuse(
            "no_floor",
            "The number of rows G0 asks for could not be read from the engine "
            f"({floor.get('why_not')}). Nothing was carved: a size invented here "
            "would be a number nobody measured.",
            floor=floor,
        )
    try:
        # THE GATE FOUND BY THE FACT IT READS, not by an id typed here. This
        # used to open `spec.gates["G0_EVAL_SET"]`, which is one ledger's
        # spelling of the gate about eval-set size; the fact is the thing this
        # carve is actually about and it is already in this module's own
        # vocabulary. A ledger with no such gate states no recipe, which is an
        # empty string and is what the caller already handles.
        reading = current.gate_reading(data.THE_EVAL_SIZE_FACT)
        fail = (reading.gate.get("on_fail") or {}) if reading is not None else {}
        recipe = str(fail.get("recipe") or "")
        note = str(fail.get("note") or "")
    except Exception:  # noqa: BLE001 - an unreadable spec is not a crash here
        recipe, note = "", ""
    return want, {**floor, "g0_recipe": recipe, "g0_resolution_note": note}


# ---------------------------------------------------------------------------


@tool(
    "carve_eval_set",
    description=(
        "Split a dataset that ALREADY CARRIES RIGHT ANSWERS into a held-out "
        "evaluation file and a training file, written as two new files in a new "
        "directory with a manifest saying where they came from and how. The size "
        "comes from the threshold G0 asks for, read off the engine rather than "
        "chosen. The split is decided by hashing each row, so it is reproducible "
        "and two identical rows cannot land on opposite sides. It will not split "
        "unlabelled data: a held-out slice of rows with no answers is a pile of "
        "inputs, not an eval set. It writes over nothing - the destination must "
        "not exist - and it records no measurement: run measure_eval_set on the "
        "file it wrote to have the size counted."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The dataset file or folder to split.",
            },
            "answer_column": {
                "type": "string",
                "description": (
                    "The column holding the right answer for each row - the "
                    "label, the expected output, the graded response. Name it "
                    "only when the user has said which it is. A row with no "
                    "value in it is never put in the eval set."
                ),
            },
            "into": {
                "type": "string",
                "description": (
                    "A NEW directory for the two files and the manifest. It must "
                    "not already exist and it must not be inside a folder "
                    "dataset being read; nothing is ever written over."
                ),
            },
            "rows": {
                "type": "integer",
                "description": (
                    "How many rows to hold out. Left out, the number G0 asks for "
                    "is used, read off the engine rather than chosen here. Fewer "
                    "than that is refused."
                ),
            },
            "seed": {
                "type": "string",
                "description": (
                    "Changes which rows are drawn, and nothing else. Recorded in "
                    "the manifest; the same seed on the same file always gives "
                    "the same split."
                ),
            },
            "max_rows": {
                "type": "integer",
                "description": (
                    f"Stop and refuse above this many rows. Default "
                    f"{DEFAULT_ROW_LIMIT}. It never truncates: a partial read "
                    "writes nothing at all."
                ),
            },
        },
        "required": ["path", "answer_column", "into"],
    },
    reads=("filesystem", "datasets"),
    writes=("filesystem", "datasets"),
    approval="always",
    provides=("data.eval_set.carve",),
    label="Carve an eval set",
    group="Data",
    # Short on purpose: `conductor.standing_brief` prints one `name - verb` line
    # per registered tool on every turn, so a verb is a per-turn cost paid by
    # every user forever. See `WhatItCostsTest.BUDGET` in
    # `tests/test_the_diagnosis_is_not_optional.py`.
    verb="split graded data into eval and train files",
    order=20,
)
def carve_eval_set(
    path: str,
    answer_column: str,
    into: str,
    rows: int = 0,
    seed: str = "",
    max_rows: int = DEFAULT_ROW_LIMIT,
    *,
    ledger: diagnosis.Spec,
) -> dict[str, Any]:
    """Two files and a manifest, or a refusal and an untouched disk.

    The order here is load-bearing and is worth reading as an order rather than
    as a list. Everything that can refuse runs over the data FIRST, in one
    streaming pass; `_claim` - the only call that creates anything - runs after
    every one of them has passed; the second pass writes. There is no state of
    the world in which this refused and also wrote.

    WHAT IT REFUSES, and each of these is the product rather than an obstacle to
    it:

    * data with no answers in it, which is the whole grading line;
    * an answer column that is absent, empty, or holds one value;
    * fewer answered rows than the floor G0 asks for;
    * a `rows` smaller than that floor, because an eval file too small for the
      threshold it was sized by is a file that cannot do the job it was written
      for;
    * a dataset too small to give up those rows without leaving less than
      `dataquality.MIN_ROWS_FOR_TRAINING` to train on - and that refusal names
      the honest alternative, which is to use the whole file as the eval set and
      count it rather than to carve a training set nobody can train on;
    * a destination that exists, is the source, or is inside it;
    * more rows than `max_rows`, which refuses rather than truncating.
    """
    limit = data.bounded(max_rows, DEFAULT_ROW_LIMIT, 1, MAX_ROW_LIMIT)
    column = str(answer_column or "").strip()
    seed_text = str(seed or "")

    try:
        source, fmt = _readable(path)
        want, floor = _g0(ledger)
        asked = data.bounded(rows, 0, 0, MAX_ROW_LIMIT) if rows else 0
        if asked and asked < want:
            raise _refuse(
                "fewer_rows_than_the_gate_asks_for",
                f"{asked} rows were asked for and G0 opens at {want} "
                f"({floor.get('declared_in')}). An eval file below the threshold "
                "it was sized by cannot do the job it would be written for, so "
                "nothing was written. Ask for at least "
                f"{want}, or leave rows out and that is what you get.",
                asked_for=asked,
                floor=floor,
            )
        if asked:
            want = asked

        if not column:
            raise _refuse(
                "no_answer_column",
                "No answer column was named, so nothing was split. A held-out "
                "slice of rows with no right answers is a pile of inputs, "
                "whatever it is called, and handing one over as an eval set "
                "would be this harness defeating its own first gate with a file "
                f"it wrote itself. What G0 asks for: {floor['g0_recipe']}",
                path=str(source),
            )

        # -- pass one: everything that could refuse --------------------------
        groups: dict[int, dict[str, int]] = {}
        texts: dict[int, str] = {}
        held = 0
        answers: dict[str, int] = {}
        columns: list[str] = list(dataquality.declared_columns(source, fmt))
        seen_columns = set(columns)
        total = 0
        answered = 0

        for record in _records(source, fmt, limit):
            total += 1
            for key in record:
                name = str(key)
                if name not in seen_columns:
                    seen_columns.add(name)
                    columns.append(name)
            has_answer = column in record and not dataquality.is_null(record[column])
            if has_answer:
                answered += 1
                value = dataquality.text_of(record[column])
                answers[value] = answers.get(value, 0) + 1
            text = dataquality.row_text(record)
            signature = dataquality.signature_of_text(text)
            group = groups.setdefault(signature, {"rows": 0, "answered": 0})
            group["rows"] += 1
            group["answered"] += 1 if has_answer else 0
            # ONE REPRESENTATIVE TEXT PER DISTINCT ROW, for the near-duplicate
            # clustering below. Identical rows have identical text by
            # construction, so one is the whole group. Held under the same
            # character budget the similarity index uses, and when the budget is
            # spent the rows past it become singletons - which can only make the
            # draw more conservative in the direction of leaking, so the
            # verification at the end is what catches it and `exhaustive: false`
            # is what says the search was narrowed.
            if signature not in texts and held < dataquality.TEXT_BUDGET_CHARS:
                texts[signature] = text
                held += len(text)

        if not total:
            raise _refuse(
                "no_rows",
                f"No row of {source.name} was read, so there was nothing to "
                "split - and that is not the same as the file being empty, "
                "because a file nobody could parse reaches here too. Run "
                "profile_dataset on it.",
                path=str(source),
            )
        if column not in seen_columns:
            raise _refuse(
                "no_such_column",
                f"There is no column called {column!r} in {source.name}. The "
                f"columns are: {', '.join(columns) or 'none were found'}. "
                "Nothing was split and nothing was written.",
                path=str(source),
                answer_column=column,
                columns=columns,
            )
        if not answered:
            raise _refuse(
                "no_answers_in_the_column",
                f"Not one of the {total:,} rows has a value in {column!r}, so "
                "there are no right answers to hold out. Splitting this would "
                "produce a file of inputs with nothing to grade against, and "
                "that is not an eval set however it is labelled. What G0 asks "
                f"for is: {floor['g0_recipe']} That part is yours - nothing here "
                "can do it for you, and a file we wrote could not honestly stand "
                "in for it.",
                path=str(source),
                answer_column=column,
                rows_read=total,
                rows_with_an_answer=0,
                grading_is_yours=floor["g0_recipe"],
            )

        largest, largest_n = max(answers.items(), key=lambda pair: (pair[1], pair[0]))
        share = largest_n / answered
        if len(answers) < 2 or share >= dataquality.IMBALANCE_BLOCK_SHARE:
            raise _refuse(
                "the_answers_are_one_value",
                f"{largest_n:,} of the {answered:,} answered rows carry the same "
                f"value in {column!r} ({share:.0%}), at or over our "
                f"{dataquality.IMBALANCE_BLOCK_SHARE:.0%} threshold. An eval set "
                "of that measures nothing: a model that always answers the "
                f"majority already scores {share:.0%}. Nothing was written. The "
                "threshold is our policy, declared in app/dataquality.py, and "
                "not a property of your data.",
                path=str(source),
                answer_column=column,
                distinct_answers=len(answers),
                largest_share=round(share, 4),
                threshold=dataquality.IMBALANCE_BLOCK_SHARE,
            )

        # A group qualifies only if EVERY row in it carries an answer. Two rows
        # can share a signature while differing in which column that text came
        # out of, and splitting such a group would put an unanswered row into
        # the eval set.
        eligible = [sig for sig, g in groups.items() if g["rows"] == g["answered"]]
        eligible_rows = sum(groups[sig]["rows"] for sig in eligible)
        # THE UNIT OF THE DRAW IS THE UNIT OF THE CHECK, and until this line
        # existed it was not. See `dataquality.near_duplicate_clusters` and
        # `_choose`: the split was drawn by exact signature and then verified
        # with a predicate that counts near duplicates as leaks, so it could only
        # pass its own verification by luck.
        cluster_of, clustering = dataquality.near_duplicate_clusters(
            {sig: texts[sig] for sig in eligible if sig in texts}
        )
        eligible_clusters = {cluster_of.get(sig, sig) for sig in eligible}
        # DISTINCT QUESTIONS, because that is what the gate's number means. See
        # `_choose`: counting rows here let two hundred copies of five tickets
        # clear a threshold that asks for thirty inputs, and counting exact rows
        # let forty paraphrases of one ticket do the same thing.
        if len(eligible_clusters) < want:
            repeated = eligible_rows - len(eligible)
            paraphrased = len(eligible) - len(eligible_clusters)
            raise _refuse(
                "not_enough_answered_rows",
                f"{want} distinct questions are needed and "
                f"{len(eligible_clusters):,} of the {total:,} rows in "
                f"{source.name} are distinct enough to be held out - short by "
                f"{want - len(eligible_clusters):,}. Nothing was written."
                + (
                    f" The {eligible_rows:,} answered rows are only "
                    f"{len(eligible):,} distinct ones ({repeated:,} of them "
                    "repeat an earlier row), and the same question asked twice "
                    "is one question to a gate that asks for real inputs. "
                    "drop_duplicates writes a copy without the repeats, and it "
                    "does not change this count - the rows that are missing are "
                    "different rows. "
                    if repeated
                    else " "
                )
                + (
                    f"A further {paraphrased:,} are NEAR duplicates of another "
                    f"row - over Jaccard {clustering['threshold']}, which is our "
                    "threshold and not a property of your data - and a "
                    "rephrasing of a question already held out measures the same "
                    "thing twice. Those are counted once here for the same "
                    "reason identical rows are, and they cannot be split apart: "
                    "a row near one on the other side of the split IS the leak "
                    "this tool checks itself for. "
                    if paraphrased
                    else ""
                )
                + f"What is needed is more graded examples: {floor['g0_recipe']}",
                path=str(source),
                answer_column=column,
                rows_read=total,
                rows_that_could_be_held_out=eligible_rows,
                distinct_rows_that_could_be_held_out=len(eligible),
                distinct_questions_that_could_be_held_out=len(eligible_clusters),
                near_duplicate_clustering=clustering,
                floor=floor,
                short_by=want - len(eligible_clusters),
            )

        chosen, eval_rows = _choose(groups, eligible, seed_text, want, cluster_of)
        train_rows = total - eval_rows
        if train_rows < dataquality.MIN_ROWS_FOR_TRAINING:
            raise _refuse(
                "would_starve_training",
                f"Holding out {eval_rows:,} of {total:,} rows leaves "
                f"{train_rows:,} to train on, and below about "
                f"{dataquality.MIN_ROWS_FOR_TRAINING} rows a fine-tune learns "
                "the examples rather than the task. Nothing was written. If you "
                "are not training on this file and want the whole of it as the "
                "eval set, that is not a carve: run measure_eval_set on the file "
                "itself and the gate is asked on that count.",
                path=str(source),
                rows_read=total,
                would_hold_out=eval_rows,
                would_leave=train_rows,
                minimum_to_train_on=dataquality.MIN_ROWS_FOR_TRAINING,
                threshold_is=(
                    "our policy, declared in app/dataquality.py, not a property "
                    "of your data"
                ),
            )

        # -- the claim: the first thing here that touches the disk ------------
        directory = _claim(into, source)
    except Refusal as refusal:
        return refusal.payload

    stem = _clean_stem(source)
    eval_path = directory / f"{stem}.eval.{WRITTEN_FORMAT}"
    train_path = directory / f"{stem}.train.{WRITTEN_FORMAT}"

    try:
        eval_written = 0
        train_written = 0
        eval_source_rows: list[int] = []
        with open(eval_path, "w", encoding="utf-8", newline="\n") as evaluation, open(
            train_path, "w", encoding="utf-8", newline="\n"
        ) as training:
            for index, record in enumerate(_records(source, fmt, limit), start=1):
                if dataquality.row_signature(record) in chosen:
                    evaluation.write(_line(record))
                    eval_written += 1
                    eval_source_rows.append(index)
                else:
                    training.write(_line(record))
                    train_written += 1
        wrote = [
            _written(eval_path, eval_written),
            _written(train_path, train_written),
        ]
    except Exception as error:  # noqa: BLE001 - see `_write_failed`
        return _write_failed(directory, source, error)

    method = {
        "rule": SELECTION_RULE,
        "how": (
            "Rows are gathered into groups of the same question - identical rows, "
            "and rows near-identical to them, transitively - and a group is in the "
            "eval set when signature_of_text("
            f"'{SELECTION_RULE}|<seed>|<group id>') is among the lowest for the "
            f"groups that qualify. {DUPLICATE_IS}"
        ),
        "same_question_is": (
            "identical after the rule above, OR over Jaccard "
            f"{clustering['threshold']} of it on character "
            "5-gram shingles, followed transitively. Transitively matters: if A is "
            "near B and B is near C, putting A and C in the eval set and B in the "
            "training set still leaks, because B is near both. This is the same "
            "instrument and the same threshold check_split_leakage uses below, "
            "which is the point - a draw judged by a stronger predicate than it "
            "was made with can only pass by luck, and this one used to."
        ),
        "near_duplicate_clustering": clustering,
        "seed": seed_text,
        "rows_asked_for": want,
        "rows_asked_for_are": (
            "distinct QUESTIONS. A row repeated in the source, or rephrased in "
            "it, is one input to the gate that asked for this number, so the draw "
            "counts groups of the same question and not rows."
        ),
        "distinct_rows_held_out": len(chosen),
        "distinct_questions_held_out": len({cluster_of.get(s, s) for s in chosen}),
        "rows_asked_for_came_from": (
            "the caller" if asked else floor.get("declared_in")
        ),
        "answer_column": column,
        "qualifies": (
            "a row with a value in the answer column, in a group of identical "
            "rows that all have one"
        ),
        "whole_groups_only": (
            "A group of the same question is drawn as one and cannot land on "
            "opposite sides of the split. That is why the eval file can hold more "
            "rows than were asked for, and never fewer. It is also the property "
            "that makes the leakage check below a proof rather than a coin toss: "
            "the draw is made under the same definition of sameness the check "
            "judges it by. It was not, and on a 161-row dataset built from this "
            "repository's own git log the tool came back leaking on 12 of 25 "
            "seeds; drawing in these units it is 0 of 25."
        ),
        "rows_are_verbatim": (
            "No column was added, removed or renamed. Provenance is in this "
            "manifest rather than in the rows, because a per-row mark would make "
            "every eval row differ from every train row and the leakage check "
            "below would come back clean on anything."
        ),
    }

    # -- we check our own work --------------------------------------------
    leakage = data.check_split_leakage(
        train_path=str(train_path), eval_path=str(eval_path), max_rows=limit
    )
    leaked = leakage.get("leaked_rows") or 0
    partition = (eval_written + train_written) == total
    verification = {
        "tool": "check_split_leakage",
        "ran": bool(leakage.get("ran")),
        "leaked_rows": leakage.get("leaked_rows"),
        "exact_matches": leakage.get("exact_matches"),
        "near_matches": leakage.get("near_matches"),
        "threshold": leakage.get("threshold"),
        "summary": leakage.get("summary"),
        "partition_holds": partition,
        "partition_is": (
            f"{eval_written:,} + {train_written:,} = {eval_written + train_written:,} "
            f"against the {total:,} rows counted on the first pass. Every row "
            "went to exactly one of the two files; none was dropped and none was "
            "written twice."
        ),
    }

    manifest = _write_manifest(
        directory,
        {
            "operation": "carve_eval_set",
            "source": _source_record(source, fmt, total),
            "method": method,
            "wrote": wrote,
            "format_written": WRITTEN_FORMAT,
            "format_written_why": (
                "One JSON object per line, whatever the source format was, "
                "because rows from a JSON or JSONL source need not all carry the "
                "same columns and a CSV would have to invent or drop cells."
            ),
            "eval_source_rows": eval_source_rows,
            "eval_source_rows_are": (
                "the 1-based positions in the source of the rows in the eval "
                "file, in the order they were read. The training file is the "
                "complement, so one list describes both."
            ),
            "verification": verification,
            "g0": floor,
        },
    )

    summary = (
        f"Carved {eval_written:,} rows out of {total:,} into {eval_path.name} and "
        f"wrote the other {train_written:,} to {train_path.name}, under "
        f"{directory}. The size is the {want} "
        + ("you asked for" if asked else f"G0 asks for, read from {floor.get('declared_in')}")
        + f". {verification['summary']}"
    )
    if not partition:
        summary = (
            "THE TWO FILES DO NOT ADD UP TO WHAT WAS READ, which means the "
            "source changed under this call. Do not use either file. " + summary
        )
    if leaked:
        summary = (
            f"LEAKAGE IN WHAT THIS JUST WROTE: {leaked:,} of {eval_written:,} "
            "eval rows also appear in the training file, so this split is not "
            "usable and nothing should be measured against it. The files are "
            f"under {directory} and were not deleted. " + summary
        )
        # THIS IS NOW A REPORT ABOUT THE INSTRUMENT, NOT ABOUT THE DATA, and the
        # message has to say so. The draw keeps whole near-duplicate clusters
        # together, so a leak here means the clustering and the check - the same
        # instrument, run in two directions - disagreed about a pair. That
        # happens only when the search was NARROWED, which `clustering` records.
        # The old message told the user to "remove the overlapping rows from one
        # side and re-split", which no tool in this product implements:
        # drop_duplicates is exact-only and says so.
        summary += (
            " The draw keeps every group of near-identical rows on one side, so "
            "a leak here is the similarity search disagreeing with itself rather "
            "than a property of the split. What the clustering pass reported "
            f"about its own completeness: exhaustive={clustering['exhaustive']}"
            + (
                f", narrowed by {', '.join(clustering['narrowed_by'])}"
                if clustering["narrowed_by"]
                else ""
            )
            + f", over {clustering['keys']:,} distinct rows in "
            f"{clustering['clusters']:,} groups. If it was narrowed, the file is "
            "larger than the index can hold exactly and a smaller `limit` will "
            "make both passes agree. Do not measure anything against these files."
        )
        if not leakage.get("exact_matches"):
            summary += (
                " Every one of these is a NEAR match rather than an identical "
                f"row - pairs over Jaccard {leakage.get('threshold')}, which is "
                "our threshold and not a property of your data. profile_dataset "
                "counts them across the whole file; the pairs found here are in "
                "the result."
            )
    held_questions = len({cluster_of.get(s, s) for s in chosen})
    if eval_written > held_questions:
        summary += (
            f" The eval file holds {eval_written:,} rows rather than {want} "
            "because rows asking the same question are drawn together - splitting "
            "a group of them would put the same question on both sides, which is "
            f"the leak this tool checks itself for. It is {held_questions:,} "
            "DISTINCT questions, and that is the number the gate's threshold is "
            f"about: a score on it is a score on {held_questions:,} questions, not "
            f"on {eval_written:,}. drop_duplicates writes a copy of the source "
            "without the IDENTICAL repeats if you would rather the file said so "
            "too; it does not remove rephrasings, and nothing in this product "
            "does, because deciding which of two near-identical rows to keep is a "
            "judgement about your data that we are not in a position to make."
        )
    if floor.get("g0_resolution_note"):
        summary += f" {floor['g0_resolution_note']}"

    return {
        # A SPLIT THAT LEAKS IS A FAILED STEP, not a successful one with a
        # warning attached. `app/conductor.py` reads `ok` to decide what the
        # transcript says a step did, and `ok: true` beside "leakage in what
        # this just wrote" is the transcript lying quietly - which is the exact
        # defect that reading `ok` off "did it raise" produced once already.
        # The files are still there and the reply says where; what is false is
        # that this did the job it was called for.
        "ok": bool(partition) and not leaked,
        "summary": summary,
        "path": str(source),
        "into": str(directory),
        "eval_path": str(eval_path),
        "train_path": str(train_path),
        "manifest_path": manifest["path"],
        "rows_read": total,
        "eval_rows": eval_written,
        # The number the threshold is about, kept beside the row count rather
        # than instead of it, because `measure_eval_set` will count the rows and
        # the two have to be comparable. They differ exactly when the source
        # repeats a graded row.
        "eval_distinct_rows": len(chosen),
        # WHAT THE GATE'S THRESHOLD IS ACTUALLY ABOUT. `eval_distinct_rows`
        # counts byte-distinct rows; this counts distinct QUESTIONS, which is
        # what "30-50 real inputs" means and what the draw is now made in units
        # of. They differ exactly when the source rephrases a graded row.
        "eval_distinct_questions": held_questions,
        "near_duplicate_clustering": clustering,
        "train_rows": train_written,
        "rows_asked_for": want,
        "rows_asked_for_are": (
            "distinct questions. Rows asking the same question - identically or "
            "near-identically - are drawn together, so the eval file holds at "
            "least this many rows and exactly this many distinct questions."
        ),
        "answer_column": column,
        "seed": seed_text,
        "distinct_answers": len(answers),
        "wrote": wrote,
        "method": method,
        "verification": verification,
        "leakage": leakage,
        "floor": floor,
        # THE GATE IS NOT OPENED BY THIS AND MUST NOT LOOK LIKE IT.
        # `assess_the_data` says the same kind of thing about the rows existing;
        # this says it about a file existing, which is one step closer and still
        # not the claim G0 reads.
        "measured": [],
        "does_not_open_g0": (
            "This wrote a file. It did not count one. G0 reads eval_size_n, which "
            "is a count taken off a file that exists by a tool that read it - and "
            "'I wrote 40 rows' is this program's own arithmetic rather than a "
            "reading of the world. Run measure_eval_set on the eval file and the "
            "gate is asked on that count."
        ),
        "grading_is_still_yours": (
            "These rows already carried answers and were split in two. Nothing "
            "here checked that the answers are right, and nothing could: "
            + str(floor.get("g0_recipe") or "")
        ),
    }


# ---------------------------------------------------------------------------


@tool(
    "synthesize_rows",
    description=(
        "Amplify structure from your own examples by sampling: read a dataset "
        "that already carries answers, sample rows with replacement by a seed, "
        "and write them as a new file with each row tagged synthetic. It never "
        "writes an eval set and never opens a gate - run measure_eval_set on a "
        "real held-out file for that. It amplifies the distribution you already "
        "have; it does not invent new right answers."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The dataset file to amplify.",
            },
            "answer_column": {
                "type": "string",
                "description": (
                    "The column holding the right answer - the label whose "
                    "distribution is being amplified. A row with no value in it "
                    "is never sampled."
                ),
            },
            "into": {
                "type": "string",
                "description": (
                    "A NEW directory for the synthetic file and the manifest. It "
                    "must not already exist and must not be inside a folder "
                    "dataset being read; nothing is ever written over."
                ),
            },
            "count": {
                "type": "integer",
                "description": (
                    "How many synthetic rows to write. The gate that asks for "
                    "eval size reads distinct questions, and these rows are not "
                    "distinct by construction - they are samples of what you "
                    "already have."
                ),
            },
            "seed": {
                "type": "string",
                "description": "Changes which rows are sampled, and nothing else.",
            },
            "max_rows": {
                "type": "integer",
                "description": f"Refuse above this many source rows. Default {DEFAULT_ROW_LIMIT}.",
            },
        },
        "required": ["path", "answer_column", "into", "count"],
    },
    reads=("filesystem", "datasets"),
    writes=("filesystem", "datasets"),
    approval="always",
    provides=("data.synthetic.amplify",),
    label="Amplify structure from your own examples",
    group="Data",
    verb="amplify structure from your own examples",
    order=21,
)
def synthesize_rows(
    path: str,
    answer_column: str,
    into: str,
    count: int,
    seed: str = "",
    max_rows: int = DEFAULT_ROW_LIMIT,
    *,
    ledger: diagnosis.Spec,
) -> dict[str, Any]:
    """Sample with replacement, tag every row, write one file.

    Four rules, and each one is in the code rather than in this docstring:

    * **Never the eval set.** The output is synthetic by construction, so a gate
      that counts distinct questions must never count it. The file is tagged and
      the manifest says synthetic; nothing here checks whether a later call
      points measure_eval_set at it - that gate still reads the file that exists -
      but the tag is what lets a person (and a later tool) tell.
    * **Tagged at the row, forever.** Every written row carries `synthetic: true`
      plus `synthetic_source_index` (which source row it was sampled from) and the
      seed that chose it.
    * **Cannot open a gate.** `measures=()` and no instrument, so stamping never
      happens. The file is not an eval set and the gate knows it.
    * **Structure, not content.** A right answer is copied, never invented. The
      source row's answer value moves verbatim; only the sampling is new.
    """
    want = data.bounded(count, 1, 1, MAX_ROW_LIMIT)
    limit = data.bounded(max_rows, DEFAULT_ROW_LIMIT, 1, MAX_ROW_LIMIT)
    column = str(answer_column or "").strip()
    seed_text = str(seed or "")

    try:
        source, fmt = _readable(path)
        if not column:
            raise _refuse(
                "no_answer_column",
                "No answer column was named, so nothing was amplified.",
                path=str(source),
            )
        groups: dict[int, dict[str, int]] = {}
        answered_rows: list[dict[str, Any]] = []
        columns: list[str] = list(dataquality.declared_columns(source, fmt))
        seen_columns = set(columns)
        total = 0
        for record in _records(source, fmt, limit):
            total += 1
            for key in record:
                name = str(key)
                if name not in seen_columns:
                    seen_columns.add(name)
                    columns.append(name)
            if column in record and not dataquality.is_null(record[column]):
                answered_rows.append(dict(record))
        if column not in seen_columns:
            raise _refuse(
                "no_such_column",
                f"There is no column called {column!r} in {source.name}.",
                path=str(source),
                answer_column=column,
                columns=columns,
            )
        if not answered_rows:
            raise _refuse(
                "no_answers_in_the_column",
                f"Not one row has a value in {column!r}, so there is nothing to amplify.",
                path=str(source),
                answer_column=column,
            )
        directory = _claim(into, source)
        # Deterministic sampling: hash of seed|i picks the source row.
        out_path = directory / f"{_clean_stem(source)}.synthetic.{WRITTEN_FORMAT}"
        written = 0
        try:
            with open(out_path, "w", encoding="utf-8") as handle:
                for i in range(want):
                    digest = hashlib.sha256(f"{seed_text}|{i}".encode()).hexdigest()
                    idx = int(digest, 16) % len(answered_rows)
                    row = dict(answered_rows[idx])
                    row["synthetic"] = True
                    row["synthetic_source_index"] = idx
                    row["synthetic_seed"] = seed_text
                    handle.write(_line(row))
                    written += 1
        except Exception as error:
            raise _write_failed(directory, source, error) from error

        manifest = _write_manifest(
            directory,
            {
                "operation": "amplify",
                "complete": True,
                "source": _source_record(source, fmt, total),
                "answer_column": column,
                "seed": seed_text,
                "rows_read": total,
                "answered_rows": len(answered_rows),
                "rows_written": written,
                "wrote": [_written(out_path, written)],
                "method": "sample with replacement, tagged synthetic",
                "does_not_open_g0": (
                    "This wrote a synthetic file. It did not count one. G0 reads "
                    "eval_size_n, which is a count taken off a file that exists by "
                    "measure_eval_set - and a synthetic file is not an eval set by "
                    "construction."
                ),
            },
        )
        return {
            "ok": True,
            "summary": f"Wrote {written} synthetic rows from {len(answered_rows)} answered rows in {source.name}.",
            "path": str(source),
            "into": str(directory),
            "synthetic_path": str(out_path),
            "manifest_path": manifest["path"],
            "rows_read": total,
            "answered_rows": len(answered_rows),
            "rows_written": written,
            "answer_column": column,
            "seed": seed_text,
            "wrote": [_written(out_path, written)],
            "measured": [],
        }
    except Refusal as refusal:
        return dict(refusal.payload)
    except Exception as error:
        return dict(_write_failed(Path(into), Path(str(path or ".")), error).payload if "directory" in locals() else _refuse("unexpected", str(error)).payload)


# ---------------------------------------------------------------------------


@tool(
    "drop_duplicates",
    description=(
        "Write a copy of a dataset with the exactly-duplicated rows removed, and "
        "a second file holding every row that was removed so nothing is lost. "
        "Both go in a new directory with a manifest saying what a duplicate was "
        "defined as and which source rows were dropped. It removes exact "
        "duplicates only: a near-duplicate is a threshold we chose, and dropping "
        "somebody's rows on our own threshold is not this tool's to do - "
        "profile_dataset counts those and leaves them. It writes over nothing: "
        "the destination must not exist."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The dataset file or folder to deduplicate.",
            },
            "into": {
                "type": "string",
                "description": (
                    "A NEW directory for the two files and the manifest. It must "
                    "not already exist and it must not be inside a folder "
                    "dataset being read; nothing is ever written over."
                ),
            },
            "max_rows": {
                "type": "integer",
                "description": (
                    f"Stop and refuse above this many rows. Default "
                    f"{DEFAULT_ROW_LIMIT}. It never truncates: a deduplicated "
                    "file written from a partial read would be missing the rest "
                    "of the data, so a partial read writes nothing."
                ),
            },
        },
        "required": ["path", "into"],
    },
    reads=("filesystem", "datasets"),
    writes=("filesystem", "datasets"),
    approval="always",
    provides=("data.dataset.deduplicate",),
    label="Drop duplicate rows",
    group="Data",
    verb="write a copy without the duplicated rows",
    order=21,
)
def drop_duplicates(
    path: str, into: str, max_rows: int = DEFAULT_ROW_LIMIT
) -> dict[str, Any]:
    """The rows kept, the rows removed, and one definition of duplicate.

    `assess_the_data` already reports "49 scanned - 1 exact duplicates = 48" and
    leaves the 1 in place. This writes the 48 - under the SAME definition, which
    is the point. `dataquality.row_signature` is that definition and it has
    exactly one implementation; `profile`, `assess_the_data` and this all count
    with it, so the number a user is shown and the number of rows removed cannot
    disagree. Until this module existed the first two were the same idea written
    twice in two files, one of them through the salted builtin `hash()` - which
    is how a product ends up counting the same thing twice on two definitions
    and reporting both.

    EXACT ONLY, and the refusal to go further is deliberate. A near-duplicate is
    a pair over `dataquality.JACCARD_THRESHOLD`, which is our threshold, and
    dropping rows on our own threshold is deleting somebody's data on a
    judgement they never made. They are counted where counting is safe -
    `profile_dataset` - and reported here as not looked for.

    A FILE WITH NO DUPLICATES IN IT IS REFUSED rather than copied. A second copy
    of somebody's dataset under a new name is not work, and writing one would
    make "this harness deduplicated it" true of a file where it did nothing.
    """
    limit = data.bounded(max_rows, DEFAULT_ROW_LIMIT, 1, MAX_ROW_LIMIT)

    try:
        source, fmt = _readable(path)

        seen: set[int] = set()
        duplicate_rows = 0
        total = 0
        for record in _records(source, fmt, limit):
            total += 1
            signature = dataquality.row_signature(record)
            if signature in seen:
                duplicate_rows += 1
            else:
                seen.add(signature)

        if not total:
            raise _refuse(
                "no_rows",
                f"No row of {source.name} was read, so there was nothing to "
                "deduplicate - and that is not the same as the file being empty, "
                "because a file nobody could parse reaches here too. Run "
                "profile_dataset on it.",
                path=str(source),
            )
        if not duplicate_rows:
            raise _refuse(
                "no_duplicates",
                f"None of the {total:,} rows in {source.name} exactly duplicates "
                "an earlier one, so nothing was written: a copy with nothing "
                "removed is a second copy of your data under a new name. "
                "Near-duplicates are a different question and were not looked "
                f"for here - profile_dataset counts those, at Jaccard "
                f"{dataquality.JACCARD_THRESHOLD}.",
                path=str(source),
                rows_read=total,
                exact_duplicates=0,
                definition=DUPLICATE_IS,
            )

        directory = _claim(into, source)
    except Refusal as refusal:
        return refusal.payload

    stem = _clean_stem(source)
    kept_path = directory / f"{stem}.deduplicated.{WRITTEN_FORMAT}"
    removed_path = directory / f"{stem}.removed.{WRITTEN_FORMAT}"

    try:
        kept_rows = 0
        removed_rows = 0
        removed_source_rows: list[int] = []
        duplicate_of: list[int] = []
        first_seen: dict[int, int] = {}
        with open(kept_path, "w", encoding="utf-8", newline="\n") as kept, open(
            removed_path, "w", encoding="utf-8", newline="\n"
        ) as removed:
            for index, record in enumerate(_records(source, fmt, limit), start=1):
                signature = dataquality.row_signature(record)
                if signature in first_seen:
                    removed.write(_line(record))
                    removed_rows += 1
                    removed_source_rows.append(index)
                    duplicate_of.append(first_seen[signature])
                else:
                    first_seen[signature] = index
                    kept.write(_line(record))
                    kept_rows += 1
        wrote = [
            _written(kept_path, kept_rows),
            _written(removed_path, removed_rows),
        ]
    except Exception as error:  # noqa: BLE001 - see `_write_failed`
        return _write_failed(directory, source, error)

    # -- we check our own work --------------------------------------------
    check = dataquality.profile(kept_path, max_rows=kept_rows + 1, near_duplicates=False)
    left_over = (check.get("duplicates") or {}).get("exact")
    partition = (kept_rows + removed_rows) == total
    clean = left_over == 0 and check.get("rows") == kept_rows and partition
    verification = {
        "tool": "dataquality.profile",
        "rows_in_the_written_file": check.get("rows"),
        "exact_duplicates_in_the_written_file": left_over,
        "clean": clean,
        "checked_only": (
            "exact duplicates, re-counted by the profiler off the file that was "
            "written. Near-duplicate scanning was off for this pass and is listed "
            "in checks_not_run."
        ),
        "checks_not_run": check.get("checks_not_run"),
        "partition_holds": partition,
        "partition_is": (
            f"{kept_rows:,} + {removed_rows:,} = {kept_rows + removed_rows:,} "
            f"against the {total:,} rows counted on the first pass. Every row is "
            "in exactly one of the two files; nothing was dropped on the floor."
        ),
    }

    manifest = _write_manifest(
        directory,
        {
            "operation": "drop_duplicates",
            "source": _source_record(source, fmt, total),
            "method": {
                "definition": DUPLICATE_IS,
                "implementation": "dataquality.row_signature",
                "kept": "the first occurrence of each signature, in source order",
                "near_duplicates": (
                    "not looked for and not removed. A near-duplicate is a pair "
                    f"over Jaccard {dataquality.JACCARD_THRESHOLD}, which is our "
                    "threshold rather than a property of the data, and deleting "
                    "somebody's rows on our own threshold is not this tool's to "
                    "do. profile_dataset counts them."
                ),
            },
            "wrote": wrote,
            "format_written": WRITTEN_FORMAT,
            "removed_source_rows": removed_source_rows,
            "removed_duplicates_of_source_row": duplicate_of,
            "removed_source_rows_are": (
                "the 1-based positions in the source of the rows in the removed "
                "file, and beside each, the earlier row it duplicates. The kept "
                "file is the complement, so one list describes both."
            ),
            "verification": verification,
        },
    )

    summary = (
        f"{total:,} rows scanned, {duplicate_rows:,} exact duplicate"
        f"{'' if duplicate_rows == 1 else 's'} removed, {kept_rows:,} written to "
        f"{kept_path.name}. The {removed_rows:,} removed row"
        f"{'' if removed_rows == 1 else 's'} "
        f"{'is' if removed_rows == 1 else 'are'} in {removed_path.name} - nothing "
        f"was deleted. Re-read afterwards, the written file has {left_over} exact "
        "duplicates in it. Near-duplicates were not looked for: profile_dataset "
        "counts those."
    )
    if not clean:
        summary = (
            "THE FILE THIS JUST WROTE DID NOT COME BACK CLEAN, which is a defect "
            "in this harness rather than in your data. " + summary
        )

    return {
        "ok": bool(clean),
        "summary": summary,
        "path": str(source),
        "into": str(directory),
        "deduplicated_path": str(kept_path),
        "removed_path": str(removed_path),
        "manifest_path": manifest["path"],
        "rows_read": total,
        "exact_duplicates": duplicate_rows,
        "rows_kept": kept_rows,
        "rows_removed": removed_rows,
        "definition": DUPLICATE_IS,
        "wrote": wrote,
        "verification": verification,
        "checks_not_run": [
            {
                "check": "near_duplicates",
                "why": (
                    "this tool removes exact duplicates only; the near-duplicate "
                    "threshold is our policy and the rows are the user's. "
                    "profile_dataset counts them at Jaccard "
                    f"{dataquality.JACCARD_THRESHOLD}"
                ),
            }
        ],
        "measured": [],
        "records_nothing": (
            "No fact was recorded. A count of the rows this program wrote is this "
            "program's arithmetic; a measurement is a tool reading a file that "
            "exists. Run profile_dataset or measure_eval_set on the file."
        ),
    }


# ---------------------------------------------------------------------------
# The 10% a person has to read before anything trains on generated rows
# ---------------------------------------------------------------------------

#: The share of a generated file a human has to check. Not a number this file
#: chose: `docs/diagnosis_engine.yaml` writes it into the recipe of
#: `BLOCKED__COLLECT_OR_SYNTHESIZE_DATA` at all three sites that state it -
#: "Synthesize from the real input distribution with a teacher model, then have
#: a human verify a 10% sample before training on any of it."
VERIFICATION_SHARE = 0.10

#: The smallest sample worth drawing. Ten percent of forty rows is four, and
#: four is already thin; below that the sample says nothing at all, so the floor
#: is stated rather than left to arithmetic on a small file.
VERIFICATION_FLOOR = 5

#: What a filled-in sample row must carry. Three spellings each, because the
#: file goes out to a person and comes back through whatever they opened it in.
VERDICT_FIELD = "verified"
VERDICT_NOTE = "verify_note"
_RIGHT = ("yes", "y", "true", "1", "ok", "correct", "right")
_WRONG = ("no", "n", "false", "0", "wrong", "bad", "incorrect")

#: Where a finished verification is recorded. Beside the file it is about, and
#: named after it, so moving the data moves the evidence with it - a record in
#: the database would be a claim about a file the database cannot see.
VERIFICATION_SUFFIX = ".verification.json"


def _fingerprint(path: Path) -> str:
    """sha256 of the whole file.

    THE WHOLE FILE AND NOT A SAMPLE OF IT, because this is what binds a
    verification to the exact bytes a person read. Size and mtime would be
    cheaper and would both survive an edit that changed every answer in the
    file, which is the one thing this has to catch. It is one streaming pass
    over a dataset that is about to be trained on, which is the most expensive
    thing this product does.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verification_path(dataset: Path) -> Path:
    return dataset.with_name(dataset.name + VERIFICATION_SUFFIX)


def read_verdict(value: Any) -> bool | None:
    """`True`, `False`, or None for "this row was not judged".

    None is not a failure state. It is the state every row starts in, and
    telling it apart from `False` is the whole point: a sample that came back
    with three rows judged and two blank has not been verified, and reading the
    blanks as "wrong" would refuse the person instead of asking them to finish.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return None
    if text in _RIGHT:
        return True
    if text in _WRONG:
        return False
    return None


def verification_for(dataset: Path) -> dict[str, Any] | None:
    """The recorded verification for this file, or None.

    Returns None rather than raising for every way it can be absent - no file,
    unreadable, not JSON, or about different bytes - because the caller's
    question is always "may this be trained on", and every one of those answers
    it the same way.
    """
    record_path = verification_path(dataset)
    if not record_path.is_file():
        return None
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    if record.get("dataset_sha256") != _fingerprint(dataset):
        # The data changed after it was verified. Not an error and not a
        # forgery - somebody re-generated with a different seed and kept the
        # name - and the record simply is not about this file any more.
        return {**record, "matches": False}
    return {**record, "matches": True}


def may_be_trained_on(dataset: Path) -> dict[str, Any]:
    """May a training run read this file? The one question, answered once.

    Called by `start_training` and by anything else that will put rows through
    a model's weights. It is a function rather than a check inside the trainer
    because the rule belongs to the data, and a second implementation of it
    somewhere else is how the two would come to disagree.
    """
    census = dataquality.synthetic_census(dataset)
    if not census.get("ok"):
        # Unreadable is the trainer's problem to report, in its own words.
        return {"ok": True, "generated_rows": 0, "why": ""}
    if census.get("clean") is True:
        return {"ok": True, "generated_rows": 0, "why": ""}
    if census.get("clean") is None:
        return {
            "ok": False,
            "error": "unfinished_scan",
            "generated_rows": None,
            "why": (
                f"The scan of {dataset.name} for generated rows stopped after "
                f"{census.get('seconds')}s at {census.get('rows')} rows, so "
                "nothing here can say whether it holds any. A training run is "
                "the most expensive thing this machine does and it does not "
                "start on a file nobody could finish reading."
            ),
        }

    generated = int(census.get("synthetic") or 0)
    record = verification_for(dataset)
    if record is None:
        return {
            "ok": False,
            "error": "not_verified",
            "generated_rows": generated,
            "why": (
                f"{dataset.name} holds {generated} generated row(s) out of "
                f"{census.get('rows')}, and nobody has read a sample of them. "
                "The ledger's own recipe is 'have a human verify a 10% sample "
                "before training on any of it', and this is that step: run "
                "draw_verification_sample on this file, read the rows it writes "
                "out, mark each one right or wrong, then run record_verification "
                "on the sample. Nothing was queued."
            ),
        }
    if not record.get("matches"):
        return {
            "ok": False,
            "error": "verification_is_about_other_bytes",
            "generated_rows": generated,
            "why": (
                f"There is a verification beside {dataset.name} and it is about "
                "different bytes - the file has been rewritten since somebody "
                "read it. Draw a fresh sample and verify this version."
            ),
        }
    if record.get("wrong"):
        return {
            "ok": False,
            "error": "sample_found_errors",
            "generated_rows": generated,
            "why": (
                f"The verified sample of {dataset.name} found "
                f"{record.get('wrong')} wrong row(s) out of "
                f"{record.get('judged')}. Training on the rest would be training "
                "on a distribution somebody has already shown to be wrong. "
                "Amplification copies answers verbatim, so a wrong generated row "
                "means a wrong source row: fix the source and generate again."
            ),
        }
    return {
        "ok": True,
        "generated_rows": generated,
        "why": "",
        "verified": {
            "judged": record.get("judged"),
            "wrong": record.get("wrong"),
            "share": record.get("share"),
            "at": record.get("verified_at"),
        },
    }


@tool(
    "draw_verification_sample",
    description=(
        "Draw the 10% sample a person has to read before anything trains on "
        "generated rows, and write it out as a file to mark up. Every row comes "
        "with an empty verified column: put yes or no in it, save, then run "
        "record_verification on the same file."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The generated dataset to draw a sample from.",
            },
            "into": {
                "type": "string",
                "description": (
                    "A NEW directory for the sample file. It must not already "
                    "exist; nothing is ever written over."
                ),
            },
            "seed": {
                "type": "string",
                "description": "Changes which rows are drawn, and nothing else.",
            },
        },
        "required": ["path", "into"],
    },
    reads=("filesystem", "datasets"),
    writes=("filesystem", "datasets"),
    approval="always",
    provides=("data.synthetic.sample_for_review",),
    label="Draw a sample to check",
    group="Data",
    verb="draw a sample of generated rows for you to read",
    order=34,
)
def draw_verification_sample(
    path: str,
    into: str,
    seed: str = "",
    *,
    ledger: diagnosis.Spec,
) -> dict[str, Any]:
    """Write out 10% of a generated file for a person to read.

    IT DRAWS AND IT DOES NOT JUDGE. Nothing in this harness can tell whether a
    generated answer is right - that is the whole reason a person is in this
    loop - so this tool's entire job is to choose which rows they read and to
    write them somewhere they can be marked up. The judgement arrives back
    through `record_verification`.

    The draw is deterministic in the seed, for `synthesize_rows`' reason: a
    sample nobody can reproduce is a sample nobody can check.
    """
    seed_text = str(seed or "")
    try:
        source, fmt = _readable(path)
        census = dataquality.synthetic_census(source)
        if census.get("clean") is True:
            raise _refuse(
                "nothing_generated",
                f"No row in {source.name} is tagged "
                f"{dataquality.SYNTHETIC_FIELD!r}, so there is nothing here for a "
                "person to check. This step is about rows this harness wrote.",
                path=str(source),
            )
        rows = [dict(record) for record in _records(source, fmt, MAX_ROW_LIMIT)]
        if not rows:
            raise _refuse(
                "no_rows",
                f"No rows could be read from {source.name}.",
                path=str(source),
            )
        wanted = min(len(rows), max(VERIFICATION_FLOOR, math.ceil(len(rows) * VERIFICATION_SHARE)))
        order = sorted(
            range(len(rows)),
            key=lambda i: hashlib.sha256(f"{seed_text}|{i}".encode()).hexdigest(),
        )
        picked = sorted(order[:wanted])

        directory = _claim(into, source)
        out_path = directory / f"{_clean_stem(source)}.to-verify.{WRITTEN_FORMAT}"
        written = 0
        try:
            with open(out_path, "w", encoding="utf-8") as handle:
                for index in picked:
                    row = dict(rows[index])
                    row["source_row_index"] = index
                    row[VERDICT_FIELD] = ""
                    row[VERDICT_NOTE] = ""
                    handle.write(_line(row))
                    written += 1
        except Exception as error:
            raise _write_failed(directory, source, error) from error

        manifest = _write_manifest(
            directory,
            {
                "operation": "draw_verification_sample",
                "complete": True,
                "source": _source_record(source, fmt, len(rows)),
                "dataset_sha256": _fingerprint(source),
                "seed": seed_text,
                "share": VERIFICATION_SHARE,
                "floor": VERIFICATION_FLOOR,
                "rows_written": written,
                "wrote": [_written(out_path, written)],
                "what_to_do": (
                    f"Read each row and put yes or no in the {VERDICT_FIELD!r} "
                    f"column - yes if the answer on that row is right for that "
                    f"input. {VERDICT_NOTE!r} is yours to use and is not read by "
                    "anything. Then run record_verification on this file."
                ),
            },
        )
        return {
            "ok": True,
            "summary": (
                f"Wrote {written} of {len(rows)} rows from {source.name} for you "
                f"to check - {VERIFICATION_SHARE:.0%}, floor {VERIFICATION_FLOOR}. "
                f"Mark each one yes or no in the {VERDICT_FIELD!r} column and run "
                "record_verification on it."
            ),
            "path": str(source),
            "into": str(directory),
            "sample_path": str(out_path),
            "manifest_path": manifest["path"],
            "rows_total": len(rows),
            "rows_written": written,
            "generated_rows": census.get("synthetic"),
            "seed": seed_text,
            "wrote": [_written(out_path, written)],
            "measured": [],
            "records_nothing": (
                "No fact was recorded. Choosing which rows a person reads is not "
                "a measurement of anything."
            ),
        }
    except Refusal as refusal:
        return dict(refusal.payload)


@tool(
    "record_verification",
    description=(
        "Read back a sample somebody has marked up and record it against the "
        "generated file it came from. Until this has run and found no wrong "
        "rows, nothing will train on that file."
    ),
    schema={
        "type": "object",
        "properties": {
            "sample_path": {
                "type": "string",
                "description": "The marked-up sample file written by draw_verification_sample.",
            },
        },
        "required": ["sample_path"],
    },
    reads=("filesystem", "datasets"),
    writes=("filesystem",),
    approval="always",
    provides=("data.synthetic.record_review",),
    label="Record what you checked",
    group="Data",
    verb="record the sample you checked",
    order=35,
)
def record_verification(sample_path: str, *, ledger: diagnosis.Spec) -> dict[str, Any]:
    """Count the verdicts a person wrote, and file them beside the data.

    IT RECORDS AND IT DOES NOT JUDGE EITHER. What it writes is what somebody
    said, with the bytes they said it about; whether that is enough to train on
    is `may_be_trained_on`'s question and `start_training`'s to ask.

    A sample that is not fully marked up is refused rather than counted. Reading
    a blank as "wrong" would fail the person for stopping halfway; reading it as
    "right" would let an unread file through, which is the whole thing this
    step exists to prevent.
    """
    try:
        sample, fmt = _readable(sample_path)
        manifest_file = sample.parent / MANIFEST_NAME
        if not manifest_file.is_file():
            raise _refuse(
                "no_manifest",
                f"There is no {MANIFEST_NAME} beside {sample.name}, so there is "
                "no record of which file this sample was drawn from. Only a "
                "sample written by draw_verification_sample can be recorded.",
                path=str(sample),
            )
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except ValueError as error:
            raise _refuse(
                "unreadable_manifest",
                f"{manifest_file} is not readable JSON: {error}",
                path=str(sample),
            ) from error
        dataset_text = str((manifest.get("source") or {}).get("path") or "")
        if not dataset_text:
            raise _refuse(
                "manifest_names_no_source",
                f"{manifest_file} does not say which file this sample came from.",
                path=str(sample),
            )
        dataset = Path(dataset_text)
        if not dataset.is_file():
            raise _refuse(
                "source_is_gone",
                f"The file this sample was drawn from is no longer at {dataset}. "
                "A verification records what somebody read about a file that "
                "exists; there is nothing here to record it against.",
                path=str(sample),
            )

        judged = 0
        wrong = 0
        blank = 0
        for record in _records(sample, fmt, MAX_ROW_LIMIT):
            verdict = read_verdict(record.get(VERDICT_FIELD))
            if verdict is None:
                blank += 1
                continue
            judged += 1
            if not verdict:
                wrong += 1
        if blank:
            raise _refuse(
                "not_finished",
                f"{blank} row(s) in {sample.name} carry no verdict, so this "
                f"sample has not been read yet. Put yes or no in the "
                f"{VERDICT_FIELD!r} column of every row and run this again - "
                "a blank counted either way would be this product deciding "
                "something only you can.",
                path=str(sample),
                judged=judged,
                blank=blank,
            )
        if not judged:
            raise _refuse(
                "nothing_to_record",
                f"No row in {sample.name} carries a verdict.",
                path=str(sample),
            )

        record = {
            "written_by": _harness(),
            "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "this_file_is": (
                "the record of a person reading a sample of generated rows. "
                "start_training reads it before it will train on that file."
            ),
            "dataset": str(dataset),
            "dataset_sha256": _fingerprint(dataset),
            "sample": str(sample),
            "judged": judged,
            "wrong": wrong,
            "share": VERIFICATION_SHARE,
            "how": (
                f"{judged} row(s) read by a person and marked in the "
                f"{VERDICT_FIELD!r} column of {sample.name}"
            ),
        }
        out = verification_path(dataset)
        out.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        return {
            "ok": True,
            "summary": (
                f"Recorded {judged} row(s) you read: {judged - wrong} right, "
                f"{wrong} wrong."
                + (
                    " Nothing will train on this file while the sample says some "
                    "of it is wrong - amplification copies answers verbatim, so a "
                    "wrong generated row is a wrong source row."
                    if wrong
                    else f" {dataset.name} can be trained on."
                )
            ),
            "dataset": str(dataset),
            "sample": str(sample),
            "judged": judged,
            "wrong": wrong,
            "verification_path": str(out),
            "measured": [],
            "records_nothing": (
                "No fact was recorded on the ledger. What a person judged about "
                "generated rows is not a measurement of the world, and no gate "
                "opens on it - it is permission to train, which is a different "
                "thing and is written beside the data rather than in the ledger."
            ),
        }
    except Refusal as refusal:
        return dict(refusal.payload)


__all__ = [
    "DEFAULT_ROW_LIMIT",
    "DUPLICATE_IS",
    "VERIFICATION_FLOOR",
    "VERIFICATION_SHARE",
    "VERDICT_FIELD",
    "MANIFEST_IS",
    "MANIFEST_NAME",
    "MAX_ROW_LIMIT",
    "Refusal",
    "SELECTION_RULE",
    "WRITTEN_FORMAT",
    "carve_eval_set",
    "drop_duplicates",
    "may_be_trained_on",
    "read_verdict",
    "verification_for",
    "verification_path",
]


# ---------------------------------------------------------------------------
# carve_rows - REGISTERED HERE because the writing half is exactly one module
# (tests/test_the_harness_writes_a_dataset_and_says_so.py). The extractors live
# in app/tools/quarry.py as a library; this is the door, beside every other
# tool that writes a dataset, so the roster of writers stays one page.
from app.tools import quarry as _quarry  # noqa: E402

@tool(
    name="carve_rows",
    description=(
        "Turn a folder of markdown, css and html into a rows file: every "
        "`## section`, `--token: value` and top-level block becomes one row "
        "with q, a and text columns - the answer verbatim from the file, the "
        "row tagged with its source and the landmark it was cut at. This is "
        "data COLLECTION: nothing is invented, and an empty carve is an error, "
        "not an empty file."
    ),
    schema={
        "type": "object",
        "properties": {
            "root": {"type": "string",
                     "description": "The folder to carve. Walked recursively; only .md/.css/.html are read."},
            "into": {"type": "string",
                     "description": "A directory for the carved rows file and its manifest."},
            "exclude": {"type": "array", "items": {"type": "string"},
                        "description": "Path fragments to hold out entirely - e.g. a file the eval will own."},
            "max_rows": {"type": "integer", "description": "Stop after this many rows. Default 20000."},
        },
        "required": ["root", "into"],
    },
    reads=("filesystem", "contexts"),
    writes=("filesystem", "datasets"),
    measures=(),
    approval="always",
    provides=("data.rows.carve",),
    label="Carve rows",
    group="Data",
    verb="carve files into rows",
    order=20,
)
def carve_rows(
    root: str,
    into: str,
    exclude: list[str] | None = None,
    max_rows: int = 20000,
):
    return _quarry.carve_rows_from_files(root, into, exclude=exclude, max_rows=max_rows)
