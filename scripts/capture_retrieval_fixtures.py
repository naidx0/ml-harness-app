#!/usr/bin/env python3
"""Capture what `app/tools/retrieval.py` actually returns, as fixtures.

## Why this exists

`measure_retriever_recall` and `compare_chunkings` had no surface. Measured
before this script was written: ZERO files under `frontend/src` referenced
either tool, so both fell to `ResultView`, the generic table - and a real sweep
of eight settings gives that table 40 top-level keys, 614 rows to draw and a
payload six containers deep against its own `MAX_DEPTH` of 3.

A card had to be built for them. `docs/VISION.md`'s invariant is that no number
is ever invented, "in code, in a document OR IN A MOCKUP", so the card could not
be demonstrated against numbers somebody typed: a card demonstrated against
typed numbers is a lie about a product whose entire thesis is that numbers have
origins. This script is the other half of that rule - it produces the payloads
the card is built against, by running the real tools on real corpora and
writing down exactly what came back.

## What it will not do

It will not run against the owner's database. `ML_HARNESS_DB` names the scratch
file, `--work` names where the corpora are written, and `_guard` refuses to
start if `db.DB_PATH` resolves to the repository's own `ml_harness.db`. Every
situation runs in a conversation this script creates, because an index and a
fact belong to one and picking an existing thread id is how 98,802 rows once
landed in somebody's real conversation.

It will not edit a payload. What the tool returned is re-serialised verbatim
under `payload`; the four keys beside it - `situation`, `corpus`, `produced_by`,
`shape` - are written here and are ABOUT the payload rather than part of it.

## The nine situations, and why these nine

Eight of them are the situations a card has to survive, and the ninth is here
because it is a different SHAPE rather than a different reason:

    01  a recall that RECORDED, with a curve that rises
    02  a recall that recorded NOTHING - refusal 7, the score tie
    03  a sweep that ends in NO EVIDENCE across every pair
    04  a sweep where pairs separate: A SET AND NOT A WINNER
    05  the degenerate sweep - settings that are one cut under four names
    06  a sweep refused before running - the plan, `run` defaulting to false
    07  the passage-level-ground-truth refusal, which only a sweep can reach
    08  twelve settings: 66 comparisons, the worst case for a renderer
    09  a recall refused before scoring - the same shape holding nulls

Run it:

    ML_HARNESS_DB=/tmp/scratch.db python scripts/capture_retrieval_fixtures.py

`--check` re-captures into a temporary directory and compares payloads with the
ones on disk instead of overwriting them, which is how the README's claim that
nothing in that folder was typed by hand stays checkable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DEFAULT_OUT = REPO / "frontend" / "src" / "fixtures" / "retrieval"


# --------------------------------------------------------------------------
# THE CORPORA. Written to disk, then indexed.
# --------------------------------------------------------------------------


"""Nothing in this section is a number that ends up in a fixture: what it
decides is the SITUATION - a corpus on which recall rises with k, a corpus on
which the cut changes which document wins, a corpus with a vendored duplicate in
it - and the engine decides every number about it.

TOKEN COUNTS ARE KEPT DISTINCT ACROSS EVERY DOCUMENT OF A CORPUS, deliberately.
BM25 here normalises by a passage's token count, so two passages with the same
term frequency and the same token count score EXACTLY equal - and an exact tie
is what `_tie_decided` refuses to stamp over. In `duplicated()` that tie is the
whole point. Everywhere else it would be an accident that turned a fixture into
a refusal, so the padding on every document is a different length.
"""

#: Distinct rare terms, one per document, so a query naming one has a small and
#: countable set of documents it could mean and BM25's idf is doing visible work
#: rather than being trusted.
TERMS = [
    "zarquon", "blorptide", "quibblesnap", "frobnicate", "wibblethorn",
    "gnarflux", "plumbago", "skerrivant", "thrumbolt", "vexilate",
    "morrowgate", "clindersome", "arbuthnot", "dwindlecap", "estovar",
    "fenwicket", "grumbleaxe", "hesperine", "inkwhistle", "jorbelisk",
    "kessleroy", "lumbertide", "marchpane", "nockspindle",
    "oxenholme", "pattersfen", "quarrenden", "rushbourne",
    "sallowgate", "tinderwick", "undercroft", "vellichor",
    "wanderlock", "xanthebar", "yarrowmede", "zephyrant",
    "arncliffe", "bellingdon", "corvenal", "durnsford",
]

FILLER = (
    "Routine handling of the schedule, the approvals and the archive is "
    "described here in the same words that every other section of this "
    "document uses, so that the paragraph is long without being findable."
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------


def handbook(root: Path, count: int = 24) -> Path:
    """A corpus on which RECALL RISES WITH K for a reason a person can point at.

    Each section owns a rare term. Beside the sections sit `n % 7` short NOTICES
    that mention the same term once - a circular, a memo, the one-line version
    of the same rule - and BM25 normalises by length, so every notice outranks
    the section it is about. Section `n` therefore lands at rank `n % 7 + 1`:
    four of the twenty-four questions are answered at k=1, six of them are not
    answered by k=5 at all, and the curve between those two is the whole reason
    `measure_retriever_recall` reports one instead of a single number.

    That is not a contrived corpus. A handbook with a summary page beside every
    chapter is what most people's documents look like, and "the summary outranks
    the source" is the most ordinary retrieval failure there is.

    ONE PARAGRAPH PER DOCUMENT, and every one of them shorter than 900
    characters. `cut_into_passages` packs paragraphs up to the window and never
    splits one that fits, so this corpus is cut IDENTICALLY at 900 and at 2600 -
    which is the degenerate sweep, on disk, and the reason this same folder
    serves two fixtures.
    """
    folder = Path(root) / "handbook"
    notices = 0
    for number in range(count):
        term = TERMS[number % len(TERMS)]
        # 95 + number keeps every section a different number of tokens long, and
        # keeps all of them longer than every notice below.
        padding = " ".join(["stage"] * (60 + number))
        _write(
            folder / "sections" / f"hb-{number:02d}.md",
            f"Section {number} of the operations handbook sets out the {term} "
            f"procedure in full, including who owns it, what must be recorded "
            f"before it starts and what must be archived after it ends. The "
            f"ordering of the stages is: {padding}.\n",
        )
        for repeat in range(number % 7):
            notices += 1
            _write(
                folder / "notices" / f"notice-{number:02d}-{repeat}.md",
                f"Notice: the {term} procedure applies from this quarter. "
                + " ".join(["stage"] * notices)
                + ".\n",
            )
    return folder


def handbook_questions(count: int = 24) -> list[dict]:
    return [
        {
            "question": f"{TERMS[n % len(TERMS)]} procedure",
            "gold_document": f"sections/hb-{n:02d}.md",
        }
        for n in range(count)
    ]


# ---------------------------------------------------------------------------


#: The six clauses whose answer the CUT decides, and the window at which each
#: one changes its mind, in characters. Six, and not eight, on purpose: Holm
#: over a family of six needs EIGHT questions to change before any pair can
#: separate at all, so a sweep over this corpus produces a NO EVIDENCE verdict
#: whose arithmetic is visible - six changed, eight were needed - rather than a
#: NO EVIDENCE that is really "nothing moved".
CONTESTED_AT = (400, 500, 700, 850, 1000, 1150)


def contracts(root: Path, count: int = 40) -> Path:
    """MANY PARAGRAPHS PER DOCUMENT, of many different lengths, so that the
    window decides which of them share a passage.

    At 250 characters a paragraph is mostly its own passage; at 2200 seven of
    them are packed into one. Every setting in a sweep over this corpus
    therefore indexes a genuinely different cut - which is what the handbook
    above cannot give, and what a NO EVIDENCE verdict has to be measured over
    before it is a statement about chunking rather than about one index wearing
    four names.

    THIRTY-FOUR OF THE FORTY CLAUSES ARE SETTLED. Their rare term sits in a
    short opening paragraph with the rest of the query beside it, no other
    document mentions that term, and no window in any sweep here changes who
    wins. They are the flat part of every curve.

    THE OTHER SIX ARE CONTESTED, and they are the ledger structure in
    miniature: the clause holds its rare term in the opening paragraph and the
    word `schedule` five paragraphs later, while a shorter NOTE holds both in
    one line and is longer overall. Below a window wide enough to make the
    clause one passage the note wins; at or above it the clause does. The six
    windows are `CONTESTED_AT`, so a sweep from 250 to 2200 characters watches
    recall climb six steps.
    """
    folder = Path(root) / "contracts"
    contested = {count - 6 + index: chars for index, chars in enumerate(CONTESTED_AT)}
    for number in range(count):
        mine = TERMS[number % len(TERMS)]
        if number in contested:
            _write(
                folder / f"contract-{number:02d}.md",
                _contested_clause(number, mine, contested[number]),
            )
            for copy in range(3):
                _write(
                    folder / f"note-{number:02d}-{copy}.md",
                    _contested_note(mine, copy),
                )
            continue
        # Paragraph lengths inside one document differ by design: a greedy
        # packer over equal-length paragraphs changes its answer only at
        # multiples of one paragraph, which would collapse a twelve-setting
        # sweep into three or four distinct cuts.
        body = [
            f"Clause {number} sets out the {mine} obligation and the schedule "
            f"against which it is measured."
            + " " + " ".join(["ledger"] * (4 + number % 5)) + ".",
            "The parties have exchanged the registers described in the "
            "schedule to this clause, and each register is held by the party "
            "that maintains it." + " " + " ".join(["record"] * (12 + number % 9)) + ".",
            "Paragraph two records that the obligations of the counterparty "
            "are unaffected by anything agreed here."
            + " " + " ".join(["notice"] * (20 + number % 7)) + ".",
            FILLER + " " + " ".join(["archive"] * (6 + number % 11)) + ".",
            "Paragraph four records that no waiver is implied by any of the "
            "foregoing." + " " + " ".join(["waiver"] * (9 + number % 6)) + ".",
            "The figures are entered in the register at the close of each "
            "period." + " " + " ".join(["period"] * (14 + number % 8)) + ".",
            FILLER + " " + " ".join(["appendix"] * (3 + number % 13)) + ".",
        ]
        _write(folder / f"contract-{number:02d}.md", "\n\n".join(body) + "\n")
    return folder


def _contested_clause(number: int, term: str, width: int) -> str:
    """A clause whose two query terms are separated by exactly enough filler
    that the whole document is `width` characters long.

    Below a window of `width` no passage of it holds both terms; at or above,
    the document is one passage and holds both.
    """
    head = f"Clause {number} sets out the {term} obligation."
    tail = (
        "The obligation is measured against the schedule at the close of each "
        "period and the figures are entered in the register above."
    )
    body = [head]
    # Grow the middle until the whole document is `width` characters.
    filler = 0
    while True:
        candidate = body + [FILLER] * filler + [tail]
        text = "\n\n".join(candidate)
        if len(text) >= width or filler > 40:
            break
        filler += 1
    body = body + [FILLER] * filler + [tail]
    text = "\n\n".join(body)
    # Trim or pad the last paragraph so the document is exactly `width` long.
    if len(text) < width:
        body[-1] = body[-1][:-1] + " " + " ".join(
            ["stage"] * ((width - len(text)) // 6)
        ) + "."
    return "\n\n".join(body) + "\n"


def _contested_note(term: str, copy: int) -> str:
    """One of the three notes that outrank the clause while it is in pieces.

    Both query terms sit in one short opening line, so a small window gives the
    note a short passage holding everything the question asks for while the
    clause has passages holding half of it each. Nine paragraphs of filler
    behind it are what make the note LOSE once the window is wide enough to
    pack them into that passage. Three of them, each a slightly different
    length, so that below the flip the clause is at rank 4 and a k of 3 cannot
    reach it.
    """
    opening = (
        f"The {term} obligation note is filed against the schedule here."
        + " " + " ".join(["copy"] * (1 + copy)) + "."
    )
    return "\n\n".join([opening] + [FILLER] * 9) + "\n"


def contract_questions(count: int = 40) -> list[dict]:
    return [
        {
            "question": f"{TERMS[n % len(TERMS)]} obligation schedule",
            "gold_document": f"contract-{n:02d}.md",
        }
        for n in range(count)
    ]


def contract_passage_questions(count: int = 40) -> list[dict]:
    """The same questions with the ground truth naming A PASSAGE, which only a
    sweep refuses: a passage key names a cut and a sweep varies the cut."""
    return [
        {
            "question": f"{TERMS[n % len(TERMS)]} obligation schedule",
            "gold_passage": f"contract-{n:02d}.md#0",
        }
        for n in range(count)
    ]


# ---------------------------------------------------------------------------


def ledger(root: Path, count: int = 16) -> Path:
    """A corpus where THE CUT DECIDES WHICH DOCUMENT WINS, so something can
    separate.

    The right document holds the two query terms FAR APART, in different
    paragraphs. A decoy holds them together in one short paragraph and is much
    longer overall. At a small window the decoy has a short passage carrying
    both terms and the right document has passages carrying one term each, so
    the decoy wins. At a window wider than the whole right document, that
    document is one passage holding both terms and is shorter than anything the
    decoy can offer, so it wins.

    A bench that refuses everything is as useless as one that concludes
    everything, and this is the corpus that proves this one does not.
    """
    folder = Path(root) / "ledger"
    for number in range(count):
        term = TERMS[number % len(TERMS)]
        right = [f"The {term} register is opened at the start of the period."]
        right.extend(FILLER for _ in range(3))
        right.append(
            "Reconciliation of the period is performed at the close and the "
            "reconciliation figures are entered into the register above."
        )
        _write(folder / f"book-{number:02d}.md", "\n\n".join(right) + "\n")
        decoy = [f"The {term} reconciliation note is filed with the ledger here."]
        decoy.extend(FILLER for _ in range(9))
        _write(folder / f"note-{number:02d}.md", "\n\n".join(decoy) + "\n")
    return folder


def ledger_questions(count: int = 16) -> list[dict]:
    return [
        {
            "question": f"{TERMS[n % len(TERMS)]} reconciliation",
            "gold_document": f"book-{n:02d}.md",
        }
        for n in range(count)
    ]


# ---------------------------------------------------------------------------


def duplicated(root: Path, copy_name: str = "handbook (1).md") -> Path:
    """FOUR DOCUMENTS AND A VENDORED COPY OF ONE OF THEM.

    Not a contrived corpus: `report (1).md` beside `report.md` is what a
    downloads folder looks like. Two byte-identical passages get the same BM25
    score to the bit, the tie is broken by passage ordinal, and the ordinal
    follows the directory walk - so at k=1 the recall is the alphabetical order
    of two file names, and the tool refuses to stamp it.
    """
    folder = Path(root) / "duplicated"
    bodies: dict[str, str] = {}
    for number in range(4):
        term = TERMS[number]
        name = "handbook.md" if number == 0 else f"appendix-{number}.md"
        bodies[name] = (
            f"The {term} protocol governs stage {number} of the ordering.\n\n"
            f"It is a stage about ordering and about nothing else at all, "
            f"which is why the word ordering appears in every document of this "
            f"corpus and the {term} term appears in exactly one of them.\n"
        )
    bodies[copy_name] = bodies["handbook.md"]
    for name, body in bodies.items():
        _write(folder / name, body)
    return folder


def duplicated_questions() -> list[dict]:
    return [{"question": "zarquon protocol", "gold_document": "handbook.md"}]


# ---------------------------------------------------------------------------


def jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    return path


# --------------------------------------------------------------------------
# WHAT ResultView WOULD DRAW, counted rather than guessed.
# --------------------------------------------------------------------------


"""A transcription of `frontend/src/components/ResultView.tsx` and not a second
opinion about it: the recursion below has the same three cases (scalar, array,
object), the same `MAX_DEPTH = 3` cut-off, and the same rule that a `kv__row` is
emitted once per entry of an object that is drawn. Anything it reports is
therefore a count of rows that component would render, not an estimate of one.
"""

#: `ResultView.tsx`: `const MAX_DEPTH = 3;`
MAX_DEPTH = 3

#: `ResultView.tsx`: `const LONG_TEXT = 320;`
LONG_TEXT = 320


def rows_drawn(value: Any, depth: int = 0) -> int:
    """How many `kv__row` elements `ResultView` emits for this value.

    An array is an `<ol>` of `<li>`, which are not key/value rows; the rows
    come from the objects inside it. A container at or past `MAX_DEPTH` draws
    ONE summary span and no rows at all, which is the whole point of the
    measurement.
    """
    if isinstance(value, dict):
        if not value or depth >= MAX_DEPTH:
            return 0
        return len(value) + sum(
            rows_drawn(entry, depth + 1) for entry in value.values()
        )
    if isinstance(value, list):
        if not value or depth >= MAX_DEPTH:
            return 0
        return sum(rows_drawn(entry, depth + 1) for entry in value)
    return 0


def rows_uncapped(value: Any) -> int:
    """The same count with `MAX_DEPTH` lifted: every row the payload holds."""
    if isinstance(value, dict):
        return len(value) + sum(rows_uncapped(entry) for entry in value.values())
    if isinstance(value, list):
        return sum(rows_uncapped(entry) for entry in value)
    return 0


def nesting_depth(value: Any) -> int:
    """How many containers deep the deepest leaf of this payload sits.

    A scalar is 0. The top-level object is 1. A list of objects hanging off it
    is 3 by the time you reach a field of one of those objects.
    """
    if isinstance(value, dict):
        if not value:
            return 1
        return 1 + max(nesting_depth(entry) for entry in value.values())
    if isinstance(value, list):
        if not value:
            return 1
        return 1 + max(nesting_depth(entry) for entry in value)
    return 0


def summarised_away(value: Any, depth: int = 0) -> dict[str, int]:
    """The containers `ResultView` replaces with `N items, not shown here`.

    `containers` is how many such summaries appear on screen; `rows_hidden` is
    how many key/value rows are inside them and therefore not drawn anywhere.
    """
    containers = 0
    hidden = 0
    if isinstance(value, (dict, list)) and value:
        if depth >= MAX_DEPTH:
            return {"containers": 1, "rows_hidden": rows_uncapped(value)}
        children = value.values() if isinstance(value, dict) else value
        for entry in children:
            inner = summarised_away(entry, depth + 1)
            containers += inner["containers"]
            hidden += inner["rows_hidden"]
    return {"containers": containers, "rows_hidden": hidden}


def summarised_paths(value: Any, depth: int = 0, path: str = "") -> list[str]:
    """WHICH parts of the payload `ResultView` replaces with a summary line.

    A count of hidden rows understates this: `rows[].returned` is an array of
    strings, so it hides no key/value ROWS at all and still turns the list of
    passages the retriever actually returned into `5 items, not shown here`.
    List indices are collapsed to `[]` so twenty-four identical paths read as
    one, with the number of occurrences beside it.
    """
    found: list[str] = []
    if isinstance(value, (dict, list)) and value:
        if depth >= MAX_DEPTH:
            return [path or "<root>"]
        if isinstance(value, dict):
            for key, entry in value.items():
                found.extend(
                    summarised_paths(
                        entry, depth + 1, f"{path}.{key}" if path else key
                    )
                )
        else:
            for entry in value:
                found.extend(summarised_paths(entry, depth + 1, f"{path}[]"))
    return found


def long_strings(value: Any) -> int:
    """Values past `LONG_TEXT`, which draw a `show all N characters` button."""
    if isinstance(value, str):
        return 1 if len(value) > LONG_TEXT else 0
    if isinstance(value, dict):
        return sum(long_strings(entry) for entry in value.values())
    if isinstance(value, list):
        return sum(long_strings(entry) for entry in value)
    return 0


def longest_string(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return max((longest_string(e) for e in value.values()), default=0)
    if isinstance(value, list):
        return max((longest_string(e) for e in value), default=0)
    return 0


def measure(payload: Any) -> dict[str, Any]:
    """Every number the sibling lane needs to know what it is drawing."""
    away = summarised_away(payload)
    counted: dict[str, int] = {}
    for where in summarised_paths(payload):
        counted[where] = counted.get(where, 0) + 1
    return {
        "top_level_keys": len(payload) if isinstance(payload, dict) else 0,
        "rows_a_flat_table_would_draw": rows_drawn(payload),
        "rows_the_payload_actually_holds": rows_uncapped(payload),
        "max_nesting_depth": nesting_depth(payload),
        "containers_summarised_away_at_depth_3": away["containers"],
        "rows_hidden_behind_those_summaries": away["rows_hidden"],
        "what_is_summarised_away": dict(
            sorted(counted.items(), key=lambda pair: (-pair[1], pair[0]))
        ),
        "strings_past_320_chars_that_get_a_show_all_button": long_strings(payload),
        "longest_string_chars": longest_string(payload),
        "how": (
            "Counted by a transcription of ResultView.tsx's own recursion "
            "(MAX_DEPTH = 3, LONG_TEXT = 320): one row per entry of every "
            "object it draws, none for a container at or past the depth cap. "
            "Depth counts containers, so the top-level object is 1."
        ),
    }


# --------------------------------------------------------------------------
# THE NINE SITUATIONS, as calls.
# --------------------------------------------------------------------------


def build_everything(work: Path) -> dict[str, Path]:
    """Every corpus and every eval file on disk. Returns the paths."""
    paths = {
        "handbook": handbook(work),
        "contracts": contracts(work),
        "ledger": ledger(work),
        "duplicated": duplicated(work),
    }
    paths["handbook_eval"] = jsonl(
        work / "evals" / "handbook.jsonl", handbook_questions()
    )
    paths["handbook_unlabelled_eval"] = jsonl(
        work / "evals" / "handbook_unlabelled.jsonl",
        [
            {"question": row["question"], "expected_answer": "see the section"}
            for row in handbook_questions()
        ],
    )
    paths["contracts_eval"] = jsonl(
        work / "evals" / "contracts.jsonl", contract_questions()
    )
    paths["contracts_passage_eval"] = jsonl(
        work / "evals" / "contracts_passages.jsonl",
        contract_passage_questions(),
    )
    paths["ledger_eval"] = jsonl(
        work / "evals" / "ledger.jsonl", ledger_questions()
    )
    paths["duplicated_eval"] = jsonl(
        work / "evals" / "duplicated.jsonl", duplicated_questions()
    )
    return paths


def settings(*pairs: tuple[int, int]) -> list[dict]:
    return [
        {"passage_chars": chars, "passage_overlap": overlap}
        for chars, overlap in pairs
    ]


#: Four windows chosen because the CONTESTED clauses in `contracts`
#: change their answer inside this range: two of the four sit below enough of
#: the flip points to score differently, and the difference is still smaller
#: than Holm over a family of six can resolve.
CONTRACT_FOUR = settings((250, 60), (450, 60), (900, 60), (1800, 60))

CONTRACT_TWELVE = settings(
    (250, 60), (350, 60), (450, 60), (550, 60), (650, 60), (750, 60),
    (900, 60), (1100, 60), (1300, 60), (1500, 60), (1800, 60), (2200, 60),
)

LEDGER_SIX = settings(
    (150, 20), (250, 20), (400, 20), (900, 20), (1600, 20), (5000, 20)
)

HANDBOOK_FOUR = settings((900, 120), (1400, 120), (2000, 120), (2600, 120))


def plan(paths: dict[str, Path]) -> list[dict]:
    """The eight situations plus the one extra refusal worth having, in order.

    `index` is the `build_retrieval_index` call a recall situation needs first;
    a sweep builds its own indexes and has none.
    """
    return [
        {
            "slug": "01-recall-recorded",
            "situation": (
                "A measured recall that RECORDED. measure_retriever_recall over "
                "an eval set that names the right document for every question, "
                "on an index that is not truncated, with no unresolved row, no "
                "unlabelled row and no row a score tie decided - which is every "
                "one of the seven conditions the stamp is guarded by, met."
            ),
            "corpus": (
                "handbook/ - 24 sections, each owning one rare term, and 66 "
                "short notices that mention the same terms. BM25 normalises by "
                "length so a notice outranks the section it summarises: section "
                "n lands at rank n%7+1, which is why recall rises with k here "
                "instead of being flat."
            ),
            "index": {"path": str(paths["handbook"]), "name": "handbook"},
            "tool": "measure_retriever_recall",
            "arguments": {
                "eval_path": str(paths["handbook_eval"]),
                "question_field": "question",
                "ground_truth_field": "gold_document",
                "k": 5,
            },
        },
        {
            "slug": "02-recall-refused-a-tie-decided-it",
            "situation": (
                "A recall that recorded NOTHING and said why: refusal 7 of the "
                "seven, the one where a score TIE and not the retriever decided "
                "whether the right passage was inside the top k. Chosen over "
                "the other six because it is the one that still produces a "
                "recall, a curve and a per-row table - every number a "
                "successful run has - and may not stamp any of it."
            ),
            "corpus": (
                "duplicated/ - four documents and one byte-identical vendored "
                "copy, `handbook (1).md` beside `handbook.md`, which is what a "
                "downloads folder looks like. At k=1 the recall is the "
                "alphabetical order of two file names."
            ),
            "index": {"path": str(paths["duplicated"]), "name": "duplicated"},
            "tool": "measure_retriever_recall",
            "arguments": {
                "eval_path": str(paths["duplicated_eval"]),
                "question_field": "question",
                "ground_truth_field": "gold_document",
                "k": 1,
            },
        },
        {
            "slug": "03-sweep-no-evidence",
            "situation": (
                "A sweep that ends in NO EVIDENCE across every pair, over cuts "
                "that genuinely differ - four distinct cuts, six pairwise "
                "comparisons, none of them separating after Holm."
            ),
            "corpus": (
                "contracts/ - 40 documents of seven paragraphs each, of "
                "deliberately unequal lengths, so a greedy packer answers "
                "differently at 300 characters and at 1200."
            ),
            "index": None,
            "tool": "compare_chunkings",
            "arguments": {
                "corpus_path": str(paths["contracts"]),
                "eval_path": str(paths["contracts_eval"]),
                "question_field": "question",
                "ground_truth_field": "gold_document",
                "settings": CONTRACT_FOUR,
                "k": 3,
                "name": "contracts",
                "run": True,
            },
        },
        {
            "slug": "04-sweep-a-set-and-not-a-winner",
            "situation": (
                "A sweep where some pairs DO separate, so "
                "not_beaten_by_anything holds more than one setting. THAT IS A "
                "SET AND NOT A WINNER: three settings beat three others and "
                "nothing separates the three from each other, and `crowned` is "
                "still None."
            ),
            "corpus": (
                "ledger/ - 16 right documents whose two query terms sit in "
                "different paragraphs, and 16 longer decoys that hold both "
                "terms in one short paragraph. Below a window that fits the "
                "whole right document the decoy wins; above it the right "
                "document does."
            ),
            "index": None,
            "tool": "compare_chunkings",
            "arguments": {
                "corpus_path": str(paths["ledger"]),
                "eval_path": str(paths["ledger_eval"]),
                "question_field": "question",
                "ground_truth_field": "gold_document",
                "settings": LEDGER_SIX,
                "k": 1,
                "name": "ledger",
                "run": True,
            },
        },
        {
            "slug": "05-sweep-identical-cuts",
            "situation": (
                "The degenerate sweep: several settings produce "
                "passage-for-passage identical indexes, which the tool detects "
                "and explains before it states any verdict. NO EVIDENCE here is "
                "a fact about these windows on this corpus and not a finding "
                "about chunking, and `cuts.says` is the sentence that says so."
            ),
            "corpus": (
                "handbook/ - every document is one paragraph shorter than 900 "
                "characters, and cut_into_passages never splits a paragraph "
                "that fits, so 900, 1400, 2000 and 2600 are one cut."
            ),
            "index": None,
            "tool": "compare_chunkings",
            "arguments": {
                "corpus_path": str(paths["handbook"]),
                "eval_path": str(paths["handbook_eval"]),
                "question_field": "question",
                "ground_truth_field": "gold_document",
                "settings": HANDBOOK_FOUR,
                "k": 1,
                "name": "handbook-sweep",
                "run": True,
            },
        },
        {
            "slug": "06-sweep-plan-only",
            "situation": (
                "A sweep refused before running: `run` defaulting to false, "
                "which is the reply a caller gets when they did not ask for the "
                "work. Nothing is built, nothing is written, and the counts are "
                "counted by the same kept_passages() that build() writes from "
                "rather than estimated. It is the same call as 03 with `run` "
                "left out, so the plan and the run can be read against each "
                "other."
            ),
            "corpus": "contracts/ - as 03. Nothing was indexed to produce this.",
            "index": None,
            "tool": "compare_chunkings",
            "arguments": {
                "corpus_path": str(paths["contracts"]),
                "eval_path": str(paths["contracts_eval"]),
                "question_field": "question",
                "ground_truth_field": "gold_document",
                "settings": CONTRACT_FOUR,
                "k": 3,
                "name": "contracts-plan",
            },
        },
        {
            "slug": "07-sweep-refused-passage-level-ground-truth",
            "situation": (
                "The passage-level-ground-truth refusal, which only a sweep can "
                "reach: measure_retriever_recall accepts a passage key happily "
                "for one index, and a sweep cannot, because a passage key names "
                "a cut and a sweep varies the cut. Two indexes were built "
                "before the refusal and the reply names them rather than "
                "pretending the database is untouched."
            ),
            "corpus": (
                "contracts/ - as 03, scored against an eval set whose "
                "ground-truth column holds `contract-NN.md#0`."
            ),
            "index": None,
            "tool": "compare_chunkings",
            "arguments": {
                "corpus_path": str(paths["contracts"]),
                "eval_path": str(paths["contracts_passage_eval"]),
                "question_field": "question",
                "ground_truth_field": "gold_passage",
                "settings": settings((400, 60), (1200, 60)),
                "k": 3,
                "name": "contracts-passages",
                "run": True,
            },
        },
        {
            "slug": "08-sweep-twelve-settings",
            "situation": (
                "THE WORST CASE FOR A RENDERER: the largest family the tool "
                "allows. Twelve settings is 66 pairwise comparisons, a Holm "
                "threshold of 0.05/66, and a floor on how many questions would "
                "have to change before any pair could reach it at all."
            ),
            "corpus": (
                "contracts/ - as 03, with twelve windows from 250 to 2200 "
                "characters."
            ),
            "index": None,
            "tool": "compare_chunkings",
            "arguments": {
                "corpus_path": str(paths["contracts"]),
                "eval_path": str(paths["contracts_eval"]),
                "question_field": "question",
                "ground_truth_field": "gold_document",
                "settings": CONTRACT_TWELVE,
                "k": 3,
                "name": "contracts-twelve",
                "run": True,
            },
        },
        {
            "slug": "09-recall-refused-no-ground-truth",
            "situation": (
                "NOT ON THE LIST OF EIGHT, and here because it is a different "
                "SHAPE and not just a different reason: refusal 1 of the seven "
                "is built by `_refusal`, so it returns before anything is "
                "scored and carries no recall, no curve and no rows at all - "
                "half the keys situation 02 has. A card that survives 02 has "
                "not yet been shown to survive this."
            ),
            "corpus": (
                "handbook/ - scored against an eval set that has a question "
                "column and an answer column and nothing naming a document."
            ),
            "index": {"path": str(paths["handbook"]), "name": "handbook"},
            "tool": "measure_retriever_recall",
            "arguments": {
                "eval_path": str(paths["handbook_unlabelled_eval"]),
                "question_field": "question",
                "k": 5,
            },
        },
    ]


# --------------------------------------------------------------------------
# THE DRIVER. A scratch database, nine conversations, nine files.
# --------------------------------------------------------------------------


def _guard() -> Path:
    """Refuse to start against the owner's database.

    `db.DB_PATH` is read from `ML_HARNESS_DB` at import time, so this is the
    value everything downstream will actually open. Checked rather than
    documented: a comment saying "point this somewhere else first" is what was
    in place the day `REGISTRY.call` wrote 98,802 rows into a real conversation.
    """
    from app import db

    path = Path(db.DB_PATH).resolve()
    if path == (REPO / "ml_harness.db").resolve():
        raise SystemExit(
            "REFUSING TO RUN. ML_HARNESS_DB resolves to the repository's own "
            f"database ({path}), which holds real runs. Point it at a scratch "
            "file: ML_HARNESS_DB=/tmp/scratch.db python "
            "scripts/capture_retrieval_fixtures.py"
        )
    return path


def _conversation(title: str) -> int:
    """A project and a thread of this script's own, and the thread's id.

    Never an id picked out of the air. A fact and an index are scoped to a
    conversation, and writing against a thread that does not exist yet is a row
    the next conversation inherits.
    """
    from app import db, events

    project = db.create_project(title)
    return int(events.create_thread(title, project_id=project["id"])["id"])


def capture(work: Path, out: Path, *, verbose: bool = True) -> dict[str, dict]:
    """Run all nine situations and return `{slug: fixture}`. Writes to `out`."""
    from app import db
    from app.tools import REGISTRY, retrieval
    from app.tools.evidence import USER

    database = _guard()
    db.init_db()
    retrieval.ensure_tables()
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    if verbose:
        print(f"database: {database}")
        print(f"corpora:  {work}")
        print(f"fixtures: {out}")

    paths = build_everything(work)
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fixtures: dict[str, dict] = {}

    for entry in plan(paths):
        slug = entry["slug"]
        thread = _conversation(slug)
        built = None
        if entry["index"]:
            built = REGISTRY.call(
                "build_retrieval_index",
                dict(entry["index"]),
                actor=USER,
                thread_id=thread,
            )
            if not built.get("ok"):
                raise SystemExit(f"{slug}: the index this needs failed: {built}")
        arguments = dict(entry["arguments"])
        if built is not None:
            arguments["index_id"] = int(built["index_id"])
        payload = REGISTRY.call(
            entry["tool"], dict(arguments), actor=USER, thread_id=thread
        )
        fixtures[slug] = {
            "situation": entry["situation"],
            "corpus": entry["corpus"],
            "produced_by": {
                "tool": entry["tool"],
                "arguments": arguments,
                "index_built_first": entry["index"],
                "thread_id": thread,
                "database": str(database),
                # WHERE THE CORPUS SAT, recorded because the payload quotes it.
                # `corpus_path`, `eval_path` and every `how=` sentence carry the
                # absolute path of the file they read, so two captures of the
                # same situation from two directories are equal everywhere
                # except here. `--check` needs to know which prefix to discount
                # in order to compare what the ENGINE decided rather than where
                # a temporary directory happened to be.
                "work_root": str(work.resolve()),
                "captured_at_utc": captured_at,
                "engine": "app/tools/retrieval.py, via app.tools.REGISTRY.call",
            },
            "shape": measure(payload),
            "payload": payload,
        }
        if verbose:
            drawn = fixtures[slug]["shape"]
            print(
                f"  {slug}: thread {thread}, "
                f"{drawn['top_level_keys']} keys, "
                f"{drawn['rows_a_flat_table_would_draw']} rows drawn, "
                f"depth {drawn['max_nesting_depth']}"
            )

    for slug, fixture in fixtures.items():
        (out / f"{slug}.json").write_text(
            json.dumps(fixture, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    (out / "SHAPES.json").write_text(
        json.dumps(
            {slug: fixture["shape"] for slug, fixture in fixtures.items()}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    return fixtures


def _without_the_directory(value: object, root: str) -> object:
    """The payload with the corpus's own absolute path replaced by a marker.

    NOT a way of making a comparison pass. A corpus at a different absolute
    path IS different in exactly one respect and the payload is right to say so:
    `corpus_path`, `eval_path` and the `how=` sentence on every stamp quote the
    file they read, which is the provenance. What `--check` is asking is a
    different question - did the ENGINE decide the same things - and that
    question cannot be asked without discounting the one difference the caller
    created by running from somewhere else.
    """
    if isinstance(value, str):
        return value.replace(root, "<CORPUS>").replace(
            root.replace("\\", "\\\\"), "<CORPUS>"
        )
    if isinstance(value, dict):
        return {key: _without_the_directory(v, root) for key, v in value.items()}
    if isinstance(value, list):
        return [_without_the_directory(v, root) for v in value]
    return value


def _first_differences(left: object, right: object, path: str = "") -> list[str]:
    """Where two payloads stop agreeing, as key paths, deepest name first."""
    if isinstance(left, dict) and isinstance(right, dict):
        out: list[str] = []
        for key in sorted(set(left) | set(right)):
            if key not in left:
                out.append(f"{path}.{key} (only in the fresh capture)")
            elif key not in right:
                out.append(f"{path}.{key} (only on disk)")
            else:
                out.extend(
                    _first_differences(left[key], right[key], f"{path}.{key}")
                )
        return out
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return [f"{path} (length {len(left)} vs {len(right)})"]
        out = []
        for index, (a, b) in enumerate(zip(left, right)):
            out.extend(_first_differences(a, b, f"{path}[{index}]"))
        return out
    return [] if left == right else [path or "<root>"]


def check(out: Path) -> int:
    """Re-capture into a temporary directory and compare payloads with `out`.

    THIS IS WHAT MAKES THE README'S CLAIM CHECKABLE. That folder says nothing in
    it was typed by hand; the only way anybody can believe that later is to run
    the engine again and see the same payloads come back. A difference is not
    automatically a defect - the engine may have changed on purpose - so the
    differing key paths are named rather than merely counted, and it is always
    something a person has to look at.
    """
    with tempfile.TemporaryDirectory() as temporary:
        room = Path(temporary)
        fresh = capture(room / "corpora", room / "fixtures", verbose=False)
    bad = 0
    for slug, fixture in fresh.items():
        stored = out / f"{slug}.json"
        if not stored.exists():
            print(f"MISSING  {slug}.json")
            bad += 1
            continue
        on_disk = json.loads(stored.read_text(encoding="utf-8"))
        was = _without_the_directory(
            on_disk["payload"], on_disk["produced_by"]["work_root"]
        )
        now = _without_the_directory(
            fixture["payload"], fixture["produced_by"]["work_root"]
        )
        if was == now:
            print(f"SAME     {slug}")
            continue
        bad += 1
        where = _first_differences(now, was)
        print(f"DIFFERS  {slug} - {len(where)} field(s):")
        for name in where[:8]:
            print(f"           {name}")
        if len(where) > 8:
            print(f"           ... and {len(where) - 8} more")
    print()
    print(
        f"{len(fresh) - bad} of {len(fresh)} payloads are what this engine "
        "produces today, compared with the corpus's own directory discounted."
    )
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="where the fixtures go"
    )
    parser.add_argument(
        "--work",
        type=Path,
        default=None,
        help="where the corpora are written. Default: a temporary directory.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-capture into a temporary directory and compare, writing nothing",
    )
    arguments = parser.parse_args()

    if arguments.check:
        return check(arguments.out)
    if arguments.work is not None:
        capture(arguments.work, arguments.out)
        return 0
    with tempfile.TemporaryDirectory() as temporary:
        capture(Path(temporary), arguments.out)
    return 0


if __name__ == "__main__":
    if "ML_HARNESS_DB" not in os.environ:
        raise SystemExit(
            "Set ML_HARNESS_DB to a scratch file first. This script builds "
            "thirty indexes and writes over a hundred thousand posting rows, "
            "and none of that belongs in the database holding your real runs."
        )
    raise SystemExit(main())
