"""The retrieval bench: index the user's own documents, watch the retriever
work, and score it ALONE - or refuse, by name, when nothing on disk says which
passage was the right one.

## THE HOLE THIS CLOSES, MEASURED

`docs/diagnosis_engine.yaml` specified the missing instrument in full and then
could not run it:

    retriever_recall_at_k: {type: float, source: inspect, scope: thread}

    - node: S3_RECALL_UNMEASURED
      condition: "retrieval_tried and retriever_recall_at_k is null"
      outcome: ACTION__MEASURE_RETRIEVER_RECALL
      asks: "When your retriever fetches its top few passages, how often is the
             right one actually among them?"
      action: "Score the retriever alone on the eval set: for each question, is
               the right passage in the top k. Record it as
               retriever_recall_at_k, then re-enter."

`source: inspect` admits MEASURED and nothing else, so the person is not
permitted to answer it. Before this module `evidence.resolves
('retriever_recall_at_k')` returned `tool: None` with the sentence *"No tool in
this harness measures this yet"*, which is the shape `app/tools/propose.py`
names **a fact with no door**: the engine asks somebody a question they are
structurally forbidden from answering. Two nodes below it - `S3_WEAK_RETRIEVAL`
and `TRAIN__EMBEDDING_FINETUNE` - both test `retriever_recall_at_k < 0.8`, which
is FALSE on a null, so an unmeasured retriever read exactly like a working one
and the stage fell through.

That is `docs/VISION.md`'s dead end in its purest form. *"If it was retrieval, it
builds an index over your documents and measures whether the right passage
actually comes back"* - and the product told people to go and do that somewhere
else.

## FOUR TOOLS, AND THE SECOND ONE IS NOT A CONVENIENCE

**`build_retrieval_index`** - a corpus on this machine, cut into passages, with
an inverted index over them. No network, no model, no new dependency.

**`search_the_index`** - the top k passages for one query, with their scores and
their sources. It exists so a PERSON CAN SEE THE RETRIEVER WORKING before anybody
reports a number about it. A recall of 0.34 on an index that chopped every
sentence in half is a true number about a broken instrument, and the only cheap
way to find that out is to look at what comes back. `docs/DESIGN_DIRECTIVES.md`
§7 is the same rule pointed at a UI: *a change is not done because it renders*.

**`measure_retriever_recall`** - for each question in the eval set, is the right
passage in the top k. It alone declares `measures=("retriever_recall_at_k",)`.

**`compare_chunkings`** - the same corpus cut several ways, every setting scored
on the SAME eval set with the SAME ground truth, compared PAIRED, and a verdict
that crowns nothing. It exists because the measurement above made
`S3_RETRIEVAL_IS_THE_BOTTLENECK` reachable: the engine can now tell somebody
their retriever scores 0.55 and to go and fix it, and of the four levers
`NO_TRAIN__FIX_RETRIEVAL` names - chunking, hybrid BM25 + dense, a cross-encoder
reranker, query rewriting - THIS HARNESS OWNS EXACTLY ONE. The other three need
a model we do not ship, and the reply says so every time rather than presenting
the quarter we can do as the whole answer.

It declares `measures=()` and the refusal is the interesting part: a best-of-N
recall is a maximum selected on the same questions it would be reported against,
so it is not admissible as `retriever_recall_at_k` however good it looks. See
the section below.

## WHY A SWEEP IS HARDER THAN THE TWO-RUN CASE evals.py SURVIVES

`app/tools/evals.py` earned this repository's hardest lesson on two prompts and
thirty rows: *"A delta inside the resolution is reported as NO EVIDENCE, in
those words."* Comparing N settings is strictly worse, in two ways that do not
exist with two:

1. **The maximum of N noisy estimates is biased upward.** Eight settings whose
   TRUE recall is identical at 0.5, ninety questions, two hundred simulated
   trials: the best-of-eight averages 0.577 against a truth of 0.500. Nothing
   is wrong with any retriever; the selection was made on the noise. Counted in
   `tests/test_a_sweep_of_chunkings_crowns_nothing.py`.
2. **N settings is N(N-1)/2 tests.** Eight is twenty-eight. On the same two
   hundred null families, 85 of 200 contain at least one pair at raw p<=0.05,
   and 7 of 200 do after Holm.

Three answers live in this file and none of them is sufficient alone.
`holm` corrects the family and does nothing about (1). `compare_hit_vectors`
crowns nothing - it returns a SET, the settings nothing was shown to beat, or NO
EVIDENCE - and that is a refusal rather than a measurement.
`confirm_on_held_out` is the only part that touches (1): it chooses on half the
questions and reports the chosen setting's recall on the other half, which
played no part in choosing it, so the gap between the two is the selection bias
measured on the caller's own rows.

## BM25, AND WHY THERE IS NO EMBEDDING RETRIEVER IN THIS FILE

Measured on this machine: `numpy` yes, `scikit-learn` yes, `scipy` yes;
`rank_bm25` no, `sentence-transformers` no, `faiss` no. The connected Ollama
holds three CHAT models and no embedding model.

BM25 is forty lines over a token count, it is the floor every serious retrieval
bench measures against, and - the part that decides it - **it ships no model**.
`docs/VISION.md`: *"We ship no AI."* A retriever we bundle is a model we bundle.

The constants are Robertson and Walker's published defaults, `k1 = 1.5` and
`b = 0.75`, not numbers chosen here; they are stored on the index row and named
in every result, because two indexes scored under different constants were never
comparable. The scoring function is written out in `_bm25_scores` so that a
reader can check the arithmetic rather than trust a library's flag.

A DENSE RETRIEVER IS NOT BUILT, and the refusal is deliberate rather than
pending. It would need embeddings, and the only honest source of one here is the
user's own connected model - which means every number it produced would be a
number about somebody's endpoint, would have to say so, and would send the
corpus through it. That is a different tool with a different provenance story
and a different egress conversation. `docs/PRODUCT_SPEC.md` §6.6 lists hybrid
BM25 + dense as the THIRD step, after an index and a measurement. This file is
the first two.

## THE DESIGN DECISION THIS MODULE TURNS ON

Recall@k needs GROUND TRUTH: for each question, which passage is the right one.
An eval set may not carry it, and what happens then is the whole character of the
tool.

* **Named in a column** - use it, say which column, and say whether the column
  named a PASSAGE or a DOCUMENT, because those are two different claims.
* **Not there** - REFUSE. `measured` comes back EMPTY, `not_measured` carries a
  sentence naming exactly what is needed and how to supply it, and the reply has
  the same shape as a successful call so that nothing downstream has to special
  case it.
* **NEVER ASK A MODEL WHICH PASSAGE IS CORRECT AND CALL THE RESULT A
  MEASUREMENT.** There is no argument on any tool here that would let one, and
  there is not meant to be. `app/tools/evidence.py`'s wall 7 exists because that
  exact laundering - a judge's number given a second name - was live in this
  product. A retrieval judge would be the same defect with a corpus attached.
* **The weaker proxy is a DIFFERENT MEASUREMENT WITH A DIFFERENT NAME.** If the
  caller names the column holding the expected ANSWER, this file will count how
  often that answer's text appears somewhere in the retrieved passages, and it
  reports that as `answer_in_passage_rate`. It NEVER stamps
  `retriever_recall_at_k` from it, in any configuration.

The argument for that last refusal, which is Max's and which this file agrees
with on the evidence: *"the answer text appears somewhere in the top 5"* and
*"the right passage was retrieved"* are different claims, and the gate reads the
second. They come apart in both directions and neither direction is rare. A
one-word answer like `yes` appears in almost every passage, so the proxy reads
high on a retriever that returned nothing useful. An answer paraphrased by the
document it came from - which is what a real corpus does - is absent from the
passage that was genuinely right, so the proxy reads low on a retriever that was
perfect. `docs/PRODUCT_SPEC.md` §6.6 had already written the rule down: *"an
unlabelled eval set gives a retrieval hit rate the user must verify, clearly
marked as such, never a recall number."*

## WHAT A RUN MUST REACH BEFORE ANYTHING IS STAMPED

`retriever_recall_at_k` is stamped when a real scored run happened over real rows
with real ground truth and reached the end. Seven ways that fails, all of them
recording NOTHING and all of them saying so in words:

1. **No ground truth.** The refusal above.
2. **Ground truth that resolves to nothing in the index.** A column naming
   `policies/refunds.md` against an index built from `handbook.txt` scores zero
   on every row, and zero would be a true statement about a broken join rather
   than about a retriever. Any unresolved row stops the stamp, and the reply
   names the rows and what they said.
3. **A row cap.** `max_questions` bounds the work; a run that hits it has scored
   a PREFIX of the file, which on a file sorted by topic is not a sample.
4. **A truncated index.** An index that stopped at `MAX_PASSAGES` is still
   searchable and still worth looking at. It is not the corpus, so a recall
   measured against it is not a recall over the corpus.
5. **Zero scorable rows.** Nothing to measure is not a measurement of nothing.
6. **A row the file held that carried no ground truth, or no question.** The
   same claim as 2 with the join missing instead of broken, and the one an
   adversary found live: a 500-row eval set with 499 blank ground-truth cells
   stamped `1 of 1 questions in <file>` at MEASURED with an empty
   `not_measured`, and a partially-labelled eval set is the most ordinary shape
   a hand-made one has. Every row read is now counted, the ones that could not
   be scored are counted by reason, and they block the stamp.
7. **A row whose hit was decided by a score TIE and not by the retriever.** A
   corpus holding `alpha.md` and a byte-identical copy of it, ground truth
   `alpha.md`, k=1: with the copy named `zzz_copy.md` the recall is 1.0, with it
   named `aaa_copy.md` the recall is 0.0. Same corpus, same query, same
   retriever, same ground truth; the number is the alphabetical order of two
   file names. `_resolve` already refuses an ambiguous BASENAME because
   *"choosing between them would decide your recall number on a coin flip"* -
   identical CONTENT is the same coin flip and `_rank_bounds` is where it is
   noticed.

## THE NUMBER IS A COUNT, AND IT ARRIVES WITH ITS RESOLUTION

Reported the way `app/tools/evals.py` reports a score, because a score without
its resolution is half a number and recall on twelve questions is not evidence
about a retriever. `evals.resolution_for` is IMPORTED rather than re-derived, so
a recall and an eval score are stated with the same instrument - the same reason
`evals` imports `measure.normalise_answer` rather than writing a second one.

    34 of 50 questions had the right passage in the top 5 (68%).

**And recall@k rises with k, which is the one way this number can be gamed.**
The fact `retriever_recall_at_k` carries no k in its name, and the engine's bar
is a flat `>= 0.8`, so a caller who asks for k=100 can stamp a very good number
about a very bad retriever. Two things answer that and neither is a threshold
invented here: `k` is named in the `how=` sentence that travels with the stamp,
and **the curve is reported** - recall at every depth from 1 to k, off the same
ranked lists, for nothing. A person looking at `recall@1 12/50, recall@5 34/50,
recall@50 49/50` can see what k bought. One number cannot be read that way, so
one number is not what comes back.

## THE SHAPE THE SIBLINGS CONSUME

Python, not HTTP. Import these; do not re-derive them.

    retrieval.build(...)          -> dict, the index report
    retrieval.search(...)         -> dict, the ranked passages
    retrieval.score_recall(...)   -> dict, the recall report (no stamping)
    retrieval.plan_chunkings(...) -> dict, what a sweep would write, in counts
    retrieval.sweep_chunkings(...)-> dict, the sweep and its verdict (no stamping)
    retrieval.compare_hit_vectors(vectors) -> dict, the statistics alone
    retrieval.confirm_on_held_out(vectors) -> dict, the split-half check
    retrieval.holm(p_values)      -> list[dict], the family correction
    retrieval.min_discordant_for(alpha) -> int, the floor a refusal owes
    retrieval.indexes_in(thread)  -> list[dict], newest first
    retrieval.tokenise(text)      -> list[str]
    retrieval.cut_into_passages(text, ...) -> list[str]
    retrieval.kept_passages(text, ...) -> ([(passage, terms)], short, empty)

`score_recall` does the work and stamps nothing, for the reason `evals.run` does:
the tool holds the instrument and decides what may be stamped, and the function
holds the work, so a sibling bench can have the number without touching the fact
ledger.

## EGRESS, IN ONE SENTENCE

There is no network call in this file. There is no adapter, no provider, no
secret and no base URL; a local index is local, and the corpus is read off the
disk it was already on. That is not a promise about intent - `import` at the top
of this module is the whole list of what it can reach.

## WHAT THIS MODULE DELIBERATELY DOES NOT DO

* It does not decide `retrieval_tried`. That fact is `source: ask` and the YAML
  says why: *"Whether retrieval was tried is yours to say... a wrong yes here
  costs a month."* Building an index in this harness is not the same event as
  having tried retrieval on the system the person actually ships.
* It does not rerank, rewrite queries, or run a hybrid. Those are §6.6's step 3,
  they are levers applied ONE AT A TIME because two at once is not an
  experiment, and each needs its own before-and-after row.
* It does not answer a question. Retrieval recall and answer quality are
  different measurements and the bench never merges them.
* It does not check whether the corpus would simply FIT in the context window -
  `NO_TRAIN__CONTEXT_STUFFING`, which §6.6 calls the bench's cheapest answer.
  Measuring that honestly needs the connected model's own tokenizer, and a token
  count from the wrong tokenizer is an invented number. `total_tokens` here is a
  count of THIS module's tokens and is named as such everywhere it appears.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Iterator

from app import build as build_costs, dataquality, db
from app.tools import evals, evidence
from app.tools.context import quarantine
from app.tools.evidence import Instrument
from app.tools.registry import REGISTRY, tool


# ---------------------------------------------------------------------------
# Constants. Every one of them says where it came from.


#: Robertson and Walker's published Okapi BM25 defaults. NOT numbers chosen
#: here, and not tuned against anything in this repository - tuning them would
#: need a labelled retrieval benchmark, which is the very thing this module
#: exists because people do not have. They are stored on the index row so that
#: two indexes scored under different constants can be told apart.
BM25_K1 = 1.5
BM25_B = 0.75

#: How long a passage may be, in characters, before the cutter splits it.
#:
#: THIS IS A CHOICE AND NOT A MEASUREMENT, and `docs/PRODUCT_SPEC.md` §6.6 is
#: explicit that it has to look like one: *"Chunking is a stated choice with its
#: parameters visible, not a hidden default - chunk size, overlap, and whether
#: structure was respected."* So it is an argument, it is stored on the index,
#: it is named in every report and in the `how=` of every stamp, and nothing
#: here claims it is right for anybody's corpus. Changing it and re-measuring is
#: the fourth lever §6.6 lists, and the only reason that lever means anything is
#: that the parameter is visible.
DEFAULT_PASSAGE_CHARS = 1200

#: How much of the previous passage the next one repeats when a paragraph has to
#: be split. Overlap exists because a split lands mid-argument and the sentence
#: that answers the question ends up straddling the cut; it costs index size and
#: buys recall, and like the window above it is a stated choice rather than a
#: measured optimum.
DEFAULT_PASSAGE_OVERLAP = 200

#: A fragment shorter than this is dropped rather than indexed, and the count of
#: dropped fragments is reported. A twelve-character passage is a heading or a
#: list bullet on its own; it can win a BM25 score on one rare term and it can
#: never answer anything.
MIN_PASSAGE_CHARS = 40

#: The largest corpus this index will hold, in passages, and it is
#: `dataquality.DEFAULT_ROW_CAP` rather than a new number: a passage is this
#: bench's row, so the bench's row cap is the profiler's row cap. It is reported
#: when it bites, and an index that hit it stamps nothing - see WHAT A RUN MUST
#: REACH in the module docstring.
MAX_PASSAGES = dataquality.DEFAULT_ROW_CAP

#: How much of one document is read. `dataquality.MAX_FILE_CHARS`, for the same
#: reason: a folder of text files is a dataset by that module's own reckoning
#: and the two readers should not disagree about how much of a file they see.
MAX_DOCUMENT_CHARS = dataquality.MAX_FILE_CHARS

#: How deep a search goes unless told otherwise. The engine's own question is
#: *"when your retriever fetches its top few passages"*; five is what "a few"
#: means in every retrieval paper and in the brief's own example sentence, and
#: it is not load-bearing because the curve at every depth from 1 to k comes
#: back with the number.
DEFAULT_K = 5

#: A bound on how deep one search may go. Recall@k is monotonic in k, so an
#: unbounded k is a way to report 100% about any index at all; this is not a
#: threshold on what is honest - the `how=` sentence and the curve do that work
#: - it is a bound on how much text one call will return and hold.
MAX_K = 100

#: How many eval rows one recall run will score. A run that hits this stamps
#: NOTHING, so it is a bound on the work rather than a sample size: scoring is
#: local and costs no tokens, so there is no reason to sample, and every reason
#: not to pretend a prefix of a file is one.
MAX_QUESTIONS = 20_000

#: The column names an eval set conventionally uses for "which document or
#: passage was the right one". Used ONLY when the caller did not name a column,
#: only when EXACTLY ONE of them is present, and the one that was used is named
#: in the reply and in the stamp. Two matches is a refusal rather than a
#: precedence order: choosing between two columns that both look like ground
#: truth is a judgement about somebody's data, and getting it wrong is silent.
GROUND_TRUTH_COLUMNS = (
    "gold_passage",
    "gold_passage_id",
    "gold_doc",
    "gold_document",
    "relevant_passage",
    "relevant_document",
    "passage_id",
    "doc_id",
    "document_id",
    "source_document",
    "source_doc",
    "source_file",
)

#: What a term is. Lowercase runs of letters and digits, and nothing cleverer -
#: no stemmer, no stop list, no synonyms. `measure.normalise_answer`'s reasoning
#: applies unchanged: anything smarter is a scoring policy that would make the
#: number depend on a choice nobody can see, and this one is reproducible by eye
#: on any string.
_TERM = re.compile(r"[a-z0-9]+")

#: Paragraph boundary: a blank line, however it is spelled. Structure is
#: respected before the character window is, which is the half of §6.6's
#: chunking question that is usually left unanswered.
_PARAGRAPH = re.compile(r"\n[ \t]*\n+")

#: Which scorer this build has. One entry, on purpose - see the module
#: docstring on why there is no dense retriever here.
BM25 = "bm25"

#: The two ways a ground-truth column can name the right thing, and they are
#: different claims about how good the retriever is. Reported on every run.
PASSAGE_LEVEL = "passage"
DOCUMENT_LEVEL = "document"


# ---------------------------------------------------------------------------
# Tokenising and cutting. Both are pure, both are exported, both are the answer
# to "what did it actually do to my documents".


def tokenise(text: Any) -> list[str]:
    """The terms in one string, in order. Lowercase alphanumeric runs."""
    return _TERM.findall(str(text if text is not None else "").casefold())


def cut_into_passages(
    text: Any,
    passage_chars: int = DEFAULT_PASSAGE_CHARS,
    overlap: int = DEFAULT_PASSAGE_OVERLAP,
) -> list[str]:
    """One document into passages: paragraphs first, then the character window.

    STRUCTURE IS RESPECTED BEFORE SIZE IS, which is the choice `docs/PRODUCT_SPEC.md`
    §6.6 asks to be told about. Three rules, in order, and a person can reproduce
    every one of them with a text editor:

    1. Split on blank lines. A paragraph is the author's own unit and cutting
       through one is destroying information that was free.
    2. Pack consecutive paragraphs together while they fit inside
       `passage_chars`. A corpus of one-line entries would otherwise become a
       corpus of one-line passages, where no passage has enough terms for a
       length-normalised score to mean anything.
    3. A single paragraph longer than the window is split at WORD boundaries,
       with `overlap` characters of the previous piece repeated at the front of
       the next, so the sentence that straddles a cut still lives somewhere
       whole.

    `overlap` is clamped below `passage_chars` because an overlap at or past the
    window does not advance and the loop would not terminate. The database says
    the same thing in a `CHECK`; this says it where the loop is.
    """
    body = str(text if text is not None else "")
    window = max(1, int(passage_chars))
    step_back = max(0, min(int(overlap), window - 1))

    out: list[str] = []
    packed = ""
    for paragraph in _PARAGRAPH.split(body):
        piece = paragraph.strip()
        if not piece:
            continue
        if len(piece) > window:
            if packed:
                out.append(packed)
                packed = ""
            out.extend(_split_long(piece, window, step_back))
            continue
        if not packed:
            packed = piece
        elif len(packed) + 2 + len(piece) <= window:
            packed = f"{packed}\n\n{piece}"
        else:
            out.append(packed)
            packed = piece
    if packed:
        out.append(packed)
    return out


def kept_passages(
    text: Any,
    passage_chars: int = DEFAULT_PASSAGE_CHARS,
    overlap: int = DEFAULT_PASSAGE_OVERLAP,
) -> tuple[list[tuple[str, list[str]]], int, int]:
    """`([(passage, its terms)], fragments too short, passages with no term)`.

    THE CUT AND ITS FILTER IN ONE PLACE, so that a count made before a build and
    the build itself cannot disagree. `compare_chunkings` states what a sweep is
    about to write - passages and posting rows, per setting - before it writes
    any of it, and the only way that promise stays true is for the counting and
    the writing to run the same code. A second implementation of "which pieces
    survive the cut" is a second implementation that drifts, and a cost preview
    that drifts is worse than none: it is a number with a provenance sentence
    attached to it that has stopped being true.

    Pure. Reads nothing, writes nothing, and `len(set(terms))` for each kept
    passage is exactly the number of rows `build` inserts into
    `retrieval_postings` for it, because that insert is one row per DISTINCT
    term.
    """
    kept: list[tuple[str, list[str]]] = []
    short_fragments = 0
    empty_passages = 0
    for piece in cut_into_passages(text, passage_chars, overlap):
        if len(piece) < MIN_PASSAGE_CHARS:
            short_fragments += 1
            continue
        terms = tokenise(piece)
        if not terms:
            empty_passages += 1
            continue
        kept.append((piece, terms))
    return kept, short_fragments, empty_passages


def _split_long(piece: str, window: int, step_back: int) -> list[str]:
    """One over-long paragraph, cut at word boundaries with overlap.

    The break is searched for backwards from the window edge so that a cut lands
    between words. A stretch with no whitespace in it at all - a base64 blob, a
    minified line - has no word boundary to find, and is cut at the window
    rather than allowed to grow without bound; that is reported by the passage
    length distribution rather than silently.
    """
    out: list[str] = []
    start = 0
    while start < len(piece):
        end = min(len(piece), start + window)
        if end < len(piece):
            space = piece.rfind(" ", start + 1, end)
            if space > start:
                end = space
        out.append(piece[start:end].strip())
        if end >= len(piece):
            break
        start = max(end - step_back, start + 1)
    return [chunk for chunk in out if chunk]


# ---------------------------------------------------------------------------
# Reading a corpus off the disk. No network, no model.


def _document_key(root: Path, candidate: Path) -> str:
    """The name a ground-truth column would plausibly use for this file.

    The path relative to the corpus root, in forward slashes, so that an eval
    set written on one machine names the same document on another. The BASENAME
    is matched separately at scoring time and the match is reported as being by
    basename, because two files called `README.md` in different folders are two
    documents and a silent choice between them is exactly the guess this module
    refuses to make.
    """
    try:
        relative = candidate.relative_to(root)
    except ValueError:  # pragma: no cover - candidate always sits under root
        relative = Path(candidate.name)
    return relative.as_posix()


def _read_documents(
    path: str, text_field: str | None, id_field: str | None
) -> Iterator[dict[str, Any]]:
    """Yield `{doc_key, source, text}` or `{doc_key, source, skipped_why}`.

    A SKIPPED DOCUMENT IS YIELDED RATHER THAN DROPPED. `app/dataquality.py`'s
    whole argument is that a check which did not run has to be listed rather than
    left out, and a corpus report that names only the files that worked is the
    same defect with a folder around it.
    """
    root = Path(path)
    if root.is_dir():
        # `_directory_data_files` IS PRIVATE AND IS REACHED ON PURPOSE. The
        # public route to a folder is `iter_records`, which reads a directory
        # only when EVERY file in it is `.txt` or `.md` (`text_folder`) and
        # yields nothing at all otherwise - so a documents folder with one CSV
        # in it would index as empty. This is the same listing `profile` walks,
        # under the same `DATA_EXTENSIONS`, so the two readers agree about what
        # a data file is; writing a second walker here is how they would stop
        # agreeing.
        for candidate in dataquality._directory_data_files(root):
            key = _document_key(root, candidate)
            source = str(candidate)
            try:
                handle, _ = dataquality.open_text(candidate, newline=None)
            except OSError as error:
                yield {"doc_key": key, "source": source,
                       "skipped_why": f"could not be opened: {error}"}
                continue
            try:
                body = handle.read(MAX_DOCUMENT_CHARS)
            except OSError as error:  # pragma: no cover - opened, then failed
                yield {"doc_key": key, "source": source,
                       "skipped_why": f"could not be read: {error}"}
                continue
            finally:
                handle.close()
            if not body.strip():
                yield {"doc_key": key, "source": source,
                       "skipped_why": "the file has no text in it"}
                continue
            yield {"doc_key": key, "source": source, "text": body}
        return

    fmt = dataquality.detect_format(root)
    name = fmt.get("name")
    if name in ("csv", "tsv", "jsonl", "json"):
        stream = dataquality.iter_records(root, fmt)
        try:
            for number, record in enumerate(stream):
                if not isinstance(record, dict):
                    record = {"value": record}
                identifier = (
                    str(record.get(id_field))
                    if id_field and record.get(id_field) is not None
                    else f"{root.name}#{number}"
                )
                body = record.get(text_field)
                if body is None or not str(body).strip():
                    yield {
                        "doc_key": identifier,
                        "source": f"{root}#{number}",
                        "skipped_why": f"row {number} has nothing in {text_field!r}",
                    }
                    continue
                yield {
                    "doc_key": identifier,
                    "source": f"{root}#{number}",
                    "text": str(body)[:MAX_DOCUMENT_CHARS],
                }
        finally:
            # See `dataquality.count_rows`: an abandoned generator holds its file
            # handle until the collector runs, which on Windows keeps the
            # directory and breaks a test's own teardown.
            stream.close()
        return

    handle, _ = dataquality.open_text(root, newline=None)
    try:
        body = handle.read(MAX_DOCUMENT_CHARS)
    finally:
        handle.close()
    if not body.strip():
        yield {"doc_key": root.name, "source": str(root),
               "skipped_why": "the file has no text in it"}
        return
    yield {"doc_key": root.name, "source": str(root), "text": body}


def _structured(path: str) -> str | None:
    """The row-shaped format this path is, or None. Content, never extension."""
    p = Path(path)
    if p.is_dir():
        return None
    name = dataquality.detect_format(p).get("name")
    return name if name in ("csv", "tsv", "jsonl", "json") else None


def _columns_of(path: str) -> list[str]:
    """The column names a structured corpus declares, for a refusal to name."""
    names: set[str] = set()
    declared = dataquality.declared_columns(path)
    names.update(str(column) for column in declared)
    stream = dataquality.iter_records(path)
    try:
        for number, record in enumerate(stream):
            if isinstance(record, dict):
                names.update(str(key) for key in record)
            if number >= 200 or len(names) >= dataquality.COLUMN_CAP:
                break
    except Exception:  # noqa: BLE001 - a refusal must not fail on the file it is about
        pass
    finally:
        stream.close()
    return sorted(names)


# ---------------------------------------------------------------------------
# The store. Nothing here issues an UPDATE to a passage or a posting.


def ensure_tables() -> None:
    """Bring the schema up to date. The retrieval tables are migration 10's."""
    from app import migrations

    migrations.migrate()


def _fingerprint(rows: Iterable[tuple[str, str]]) -> str:
    """The hash that identifies a CORPUS: each document's key and its text.

    Not the file's bytes and not its mtime. Two folders with the same documents
    under the same names are the same corpus however they were copied, and a
    rebuild for a changed timestamp would spend a person's afternoon on nothing.
    Cutting parameters are NOT in here - they are their own columns, so that a
    reuse check can say "same corpus, different chunking" rather than "different
    corpus", which is the sentence §6.6's fourth lever needs.
    """
    digest = hashlib.sha256()
    for key, text in rows:
        digest.update(f"{key}\x00".encode("utf-8"))
        digest.update(hashlib.sha256(text.encode("utf-8")).digest())
        digest.update(b"\x1e")
    return digest.hexdigest()


def _thread_help(tool: str, because: str) -> dict[str, Any]:
    """`thread_id_help` with THIS tool's own reason kept rather than overwritten.

    A REFUSAL THAT NAMES NOTHING IS A WALL WITH NO DOOR, and this one was
    silently one. `evidence.thread_id_help` returns a `detail` key holding
    `thread_is_required_by(tool)`, which is the empty string for a tool that
    measures nothing and writes no fact - `build_retrieval_index` and
    `search_the_index` are both that. Spreading the help dict AFTER a `detail`
    of one's own therefore replaced a real sentence with `""`, and the refusal
    reached the caller with no reason in it at all. Found by firing every
    refusal in this module and reading what came back, which is the only way
    this class of defect is ever found.

    Both sentences are kept when the ledger has one, in that order: the ledger's
    is about what a thread-less row would DO, and this one is about what the
    call was trying to do.
    """
    help_block = dict(evidence.thread_id_help(str(tool)))
    ledger = str(help_block.get("detail") or "").strip()
    help_block["detail"] = f"{ledger} {because}".strip() if ledger else because
    return help_block


def index_row(index_id: int) -> dict[str, Any] | None:
    ensure_tables()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM retrieval_indexes WHERE id = ?", (int(index_id),)
        ).fetchone()
    return None if row is None else dict(row)


def indexes_in(thread_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """Every index in this conversation, newest first."""
    ensure_tables()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT * FROM retrieval_indexes WHERE thread_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (int(thread_id), int(limit)),
        ).fetchall()
    return [dict(row) for row in rows]


def _named(thread_id: int, name: str) -> dict[str, Any] | None:
    ensure_tables()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM retrieval_indexes WHERE thread_id = ? AND name = ?",
            (int(thread_id), str(name)),
        ).fetchone()
    return None if row is None else dict(row)


def documents_of(index_id: int) -> list[dict[str, Any]]:
    ensure_tables()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT * FROM retrieval_documents WHERE index_id = ? ORDER BY ordinal",
            (int(index_id),),
        ).fetchall()
    return [dict(row) for row in rows]


def passages_of(index_id: int, limit: int | None = None) -> list[dict[str, Any]]:
    ensure_tables()
    sql = (
        "SELECT p.*, d.doc_key AS doc_key, d.source AS doc_source "
        "FROM retrieval_passages p "
        "JOIN retrieval_documents d ON d.id = p.document_id "
        "WHERE p.index_id = ? ORDER BY p.ordinal"
    )
    parameters: tuple[Any, ...] = (int(index_id),)
    if limit is not None:
        sql += " LIMIT ?"
        parameters = (int(index_id), int(limit))
    with db.session() as connection:
        rows = connection.execute(sql, parameters).fetchall()
    return [dict(row) for row in rows]


def delete_index(index_id: int) -> None:
    """Remove one index and everything under it. Used by a rebuild."""
    ensure_tables()
    with db.session() as connection:
        connection.execute(
            "DELETE FROM retrieval_indexes WHERE id = ?", (int(index_id),)
        )


# ---------------------------------------------------------------------------
# BM25. Written out rather than imported, so the arithmetic is checkable.


def _bm25_scores(
    connection: Any,
    index_id: int,
    query_terms: list[str],
    passages_n: int,
    avg_tokens: float,
    k1: float,
    b: float,
) -> dict[int, float]:
    """Okapi BM25 over the postings for THESE terms and no others.

        idf(t) = ln( (N - df + 0.5) / (df + 0.5) + 1 )
        score  = sum_t idf(t) * tf * (k1 + 1)
                 / ( tf + k1 * (1 - b + b * len / avg_len) )

    The `+ 1` inside the logarithm is the standard non-negative form: without
    it a term appearing in more than half the passages gets a NEGATIVE idf, and
    a passage is then punished for containing a common word - which on a corpus
    of one topic (which is what a person's documents are) makes the best passage
    lose. That is not a tuning preference, it is the difference between a
    ranking and a scrambling, and it is why the formula is here rather than
    behind a library flag.

    Only the postings for the query's terms are read. That is the whole reason
    `retrieval_postings` is a table: a per-passage blob would mean loading the
    corpus to answer one question.
    """
    if not query_terms or passages_n <= 0 or avg_tokens <= 0:
        return {}
    wanted = sorted(set(query_terms))
    counted = Counter(query_terms)
    lengths: dict[int, int] = {}
    scores: dict[int, float] = {}

    # Chunked so a very long query cannot build an SQL statement with more
    # placeholders than SQLite will accept (999 on older builds).
    for start in range(0, len(wanted), 400):
        block = wanted[start : start + 400]
        placeholders = ", ".join("?" for _ in block)
        rows = connection.execute(
            "SELECT o.term AS term, o.passage_id AS passage_id, o.tf AS tf, "
            "p.tokens AS tokens FROM retrieval_postings o "
            "JOIN retrieval_passages p ON p.id = o.passage_id "
            f"WHERE o.index_id = ? AND o.term IN ({placeholders})",
            (int(index_id), *block),
        ).fetchall()
        by_term: dict[str, list[tuple[int, int]]] = {}
        for row in rows:
            by_term.setdefault(str(row["term"]), []).append(
                (int(row["passage_id"]), int(row["tf"]))
            )
            lengths[int(row["passage_id"])] = int(row["tokens"])
        for term, postings in by_term.items():
            df = len(postings)
            idf = math.log((passages_n - df + 0.5) / (df + 0.5) + 1.0)
            repeats = counted[term]
            for passage_id, tf in postings:
                length = lengths.get(passage_id, 0)
                denominator = tf + k1 * (1.0 - b + b * (length / avg_tokens))
                if denominator <= 0:  # pragma: no cover - tf >= 1 and k1 >= 0
                    continue
                scores[passage_id] = scores.get(passage_id, 0.0) + (
                    repeats * idf * tf * (k1 + 1.0) / denominator
                )
    return scores


def _ranked(index: dict[str, Any], query: str, depth: int) -> list[dict[str, Any]]:
    """The top `depth` passages for one query, best first. Never raises."""
    return _ranked_and_scored(index, query, depth)[0]


def _ranked_and_scored(
    index: dict[str, Any], query: str, depth: int
) -> tuple[list[dict[str, Any]], dict[int, float]]:
    """The top `depth` passages AND every score this query produced.

    The second half exists because a rank alone cannot say whether the rank was
    DECIDED. Two passages with the same score are ordered by the tie-break on
    the line below, and a caller that only sees the truncated list cannot tell a
    passage that won from a passage that was ahead alphabetically. The scores
    are already in memory here - returning them costs one reference, and
    `score_recall` uses them to work out which of its rows a tie-break decided.
    """
    terms = tokenise(query)
    passages_n = int(index["passages_n"])
    total_tokens = int(index["total_tokens"])
    if not terms or passages_n <= 0 or total_tokens <= 0:
        return [], {}
    average = total_tokens / passages_n
    with db.session() as connection:
        scores = _bm25_scores(
            connection,
            int(index["id"]),
            terms,
            passages_n,
            average,
            float(index["k1"]),
            float(index["b"]),
        )
        if not scores:
            return [], {}
        # Ties broken by ordinal so that two runs over one index rank
        # identically. A retriever whose order depends on dict iteration is not
        # an instrument.
        best = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))[:depth]
        ids = [passage_id for passage_id, _ in best]
        placeholders = ", ".join("?" for _ in ids)
        rows = connection.execute(
            "SELECT p.*, d.doc_key AS doc_key, d.source AS doc_source "
            "FROM retrieval_passages p "
            "JOIN retrieval_documents d ON d.id = p.document_id "
            f"WHERE p.id IN ({placeholders})",
            tuple(ids),
        ).fetchall()
    by_id = {int(row["id"]): dict(row) for row in rows}
    out: list[dict[str, Any]] = []
    for rank, (passage_id, score) in enumerate(best, start=1):
        row = by_id.get(passage_id)
        if row is None:  # pragma: no cover - the join cannot lose a row
            continue
        row["rank"] = rank
        row["score"] = float(score)
        out.append(row)
    return out, scores


# ---------------------------------------------------------------------------
# Building.


def _as_number(value: Any, default: Any = None) -> Any:
    """A caller's number, WITHOUT converting one numeric type into another.

    Taken from `evals._as_number`, argument included, because the hazard is the
    same one: `evidence._note_conversion` remembers an `int()` or `float()`
    performed on a caller's value, and `Instrument.measured` then refuses to
    stamp anything equal to what was remembered. `int(k)` on a `k` of 1 would
    remember `1` and `1.0`, and a retriever that put the right passage in the
    top 1 every time - recall exactly `1.0` - would be refused a stamp for a
    reason with nothing to do with where its number came from.
    """
    if value is None:
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _clamped(value: Any, default: int, low: int, high: int) -> int:
    """Bound a caller's number BY COMPARISON, never by conversion. See above."""
    number = _as_number(value, default)
    if not isinstance(number, (int, float)) or isinstance(number, bool):
        return default
    if number > high:
        return high
    if number < low:
        return low
    return number


def build(
    *,
    path: str,
    thread_id: int | None,
    name: str | None = None,
    text_field: str | None = None,
    id_field: str | None = None,
    passage_chars: int = DEFAULT_PASSAGE_CHARS,
    passage_overlap: int = DEFAULT_PASSAGE_OVERLAP,
    rebuild: bool = False,
) -> dict[str, Any]:
    """Index a corpus on this machine. Stamps nothing; returns what it did.

    Separated from the tool handler for `evals.run`'s reason: the tool holds the
    instrument and the function holds the work, so a sibling bench can build an
    index without touching the fact ledger - and nothing in here CAN write a
    fact, because nothing in here has an `Instrument`.
    """
    if thread_id is None:
        return {
            "ok": False,
            "error": "no_thread",
            **_thread_help(
                "build_retrieval_index",
                "An index belongs to one conversation: it is built from that "
                "conversation's documents and it is what that conversation's "
                "recall number is measured against. This call did not say which.",
            ),
        }
    if not evidence.names_a_conversation(thread_id):
        return {
            "ok": False,
            "error": "no_such_thread",
            "detail": (
                f"There is no conversation {thread_id!r} on this machine, so "
                "there is nowhere to file an index. Nothing was read and nothing "
                "was written."
            ),
        }

    root = Path(str(path))
    if not root.exists():
        return {
            "ok": False,
            "error": "no_such_path",
            "summary": (
                f"There is nothing at {path}. Nothing was indexed. Point this at "
                "a folder of documents, or at one file, on this machine."
            ),
        }

    structured = _structured(str(root))
    if structured and not text_field:
        columns = _columns_of(str(root))
        return {
            "ok": False,
            "error": "no_text_field",
            "summary": (
                f"{path} is a {structured} file, so one row is one document, and "
                "nothing here knows which column holds the text to index. Call "
                "this again with text_field naming that column. The columns in "
                f"this file are: {columns or 'none that could be read'}. Nothing "
                "was indexed and nothing was written."
            ),
            "columns": columns,
            "format": structured,
        }

    window = _clamped(passage_chars, DEFAULT_PASSAGE_CHARS, 1, MAX_DOCUMENT_CHARS)
    step_back = _clamped(passage_overlap, DEFAULT_PASSAGE_OVERLAP, 0, MAX_DOCUMENT_CHARS)
    if step_back >= window:
        # REFUSED RATHER THAN CLAMPED, and this was a silent clamp for one draft.
        # `cut_into_passages` reduces an overlap of 500 in a window of 50 to 49
        # so that the loop terminates - which it must, as a pure function - and
        # the result is a 1-character stride: a 500-character document became
        # 451 passages, every one of them almost the same text. That is not what
        # anybody asked for and it does not look like a failure from outside.
        # A parameter that cannot mean what it says is a refusal.
        return {
            "ok": False,
            "error": "overlap_past_the_window",
            "summary": (
                f"passage_overlap is {step_back} and passage_chars is {window}, "
                "so each passage would repeat all of the one before it and the "
                "cut would barely advance. Silently reducing the overlap would "
                "cut your corpus by a rule you did not choose."
                + (
                    f" Note that passage_overlap was not supplied here: "
                    f"{DEFAULT_PASSAGE_OVERLAP} is this tool's default, and it "
                    f"is too large for a window of {window}."
                    if step_back == DEFAULT_PASSAGE_OVERLAP
                    and passage_overlap is DEFAULT_PASSAGE_OVERLAP
                    else ""
                )
                + " Set passage_overlap below passage_chars - a few hundred "
                "characters of a window measured in thousands is the usual "
                "shape - and call this again. Nothing was indexed."
            ),
            "passage_chars": window,
            "passage_overlap": step_back,
        }

    label = str(name).strip() if name and str(name).strip() else root.name or str(root)

    # -- read the corpus first, so a reuse check has something to hash --------
    documents: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    try:
        for document in _read_documents(str(root), text_field, id_field):
            if "text" in document:
                documents.append(document)
            else:
                skipped.append(document)
    except (OSError, UnicodeDecodeError) as error:
        return {
            "ok": False,
            "error": "corpus_unreadable",
            "summary": (
                f"{path} could not be read: {type(error).__name__}: {error}. "
                "Nothing was indexed."
            ),
        }

    if not documents:
        return {
            "ok": False,
            "error": "no_documents",
            "summary": (
                f"Nothing under {path} could be read as a document, so there is "
                f"nothing to index. {len(skipped)} candidate(s) were looked at "
                "and every one was skipped; the reasons are listed. Nothing was "
                "written."
            ),
            "skipped": skipped[:50],
            "skipped_n": len(skipped),
        }

    fingerprint = _fingerprint((d["doc_key"], d["text"]) for d in documents)

    existing = _named(int(thread_id), label)
    if existing is not None and not rebuild:
        same = (
            str(existing["corpus_fingerprint"]) == fingerprint
            and int(existing["passage_chars"]) == window
            and int(existing["passage_overlap"]) == step_back
            and str(existing["source_path"]) == str(root)
        )
        if same:
            report = read_index(int(existing["id"]))
            report["reused"] = True
            report["summary"] = (
                f"An index named {label!r} over exactly these documents, cut the "
                "same way, is already in this conversation. Answered from it "
                "without re-reading anything. Pass rebuild=true to build it "
                "again. " + report["summary"]
            )
            return report
        return {
            "ok": False,
            "error": "name_taken",
            "summary": (
                f"This conversation already has an index named {label!r}, and it "
                "is not this corpus cut this way - so searching it would return "
                "passages from documents you did not just point at. Give this one "
                "a different name, or pass rebuild=true to replace the old one. "
                "Nothing was written."
            ),
            "existing_index_id": int(existing["id"]),
            "existing_source_path": existing["source_path"],
            "existing_passage_chars": int(existing["passage_chars"]),
            "existing_passage_overlap": int(existing["passage_overlap"]),
        }
    if existing is not None and rebuild:
        delete_index(int(existing["id"]))

    cut_by = (
        f"blank-line paragraphs, packed up to {window} characters; a paragraph "
        f"longer than that split at word boundaries with {step_back} characters "
        f"of overlap; fragments under {MIN_PASSAGE_CHARS} characters dropped"
    )

    ensure_tables()
    truncated = False
    short_fragments = 0
    empty_passages = 0
    passages_n = 0
    total_tokens = 0
    lengths: list[int] = []

    with db.session() as connection:
        cursor = connection.execute(
            "INSERT INTO retrieval_indexes "
            "(thread_id, name, source_path, text_field, scorer, k1, b, "
            " tokeniser, cut_by, passage_chars, passage_overlap, "
            " corpus_fingerprint) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                int(thread_id),
                label,
                str(root),
                str(text_field) if text_field else None,
                BM25,
                BM25_K1,
                BM25_B,
                "lowercase runs of letters and digits; no stemming, no stop list",
                cut_by,
                window,
                step_back,
                fingerprint,
            ),
        )
        index_id = int(cursor.lastrowid)

        ordinal = 0
        # A JSONL corpus may carry the same id on several rows - three facets
        # of one glossary concept, three tickets for one customer. Two documents
        # sharing a doc_key is allowed and recall resolves it at the document
        # level; two PASSAGES sharing a passage_key is a UNIQUE violation that
        # used to abort the whole build. The first document keeps the plain key
        # so nothing that already reads `concept#0` changes; a repeat carries
        # its ordinal so the key stays unique and still says which document.
        seen_doc_keys: dict[str, int] = {}
        for number, document in enumerate(documents):
            if truncated:
                break
            doc_key = str(document["doc_key"])
            repeat = seen_doc_keys.get(doc_key, 0)
            seen_doc_keys[doc_key] = repeat + 1
            passage_stem = doc_key if repeat == 0 else f"{doc_key}@{number}"
            kept, dropped_short, dropped_empty = kept_passages(
                document["text"], window, step_back
            )
            short_fragments += dropped_short
            empty_passages += dropped_empty
            document_row = connection.execute(
                "INSERT INTO retrieval_documents "
                "(index_id, ordinal, doc_key, source, characters, passages_n) "
                "VALUES (?, ?, ?, ?, ?, 0)",
                (
                    index_id,
                    number,
                    str(document["doc_key"]),
                    str(document["source"]),
                    len(document["text"]),
                ),
            )
            document_id = int(document_row.lastrowid)
            written = 0
            for in_document, (piece, terms) in enumerate(kept):
                if passages_n >= MAX_PASSAGES:
                    truncated = True
                    break
                passage_row = connection.execute(
                    "INSERT INTO retrieval_passages "
                    "(index_id, document_id, ordinal, in_document, passage_key, "
                    " text, characters, tokens) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        index_id,
                        document_id,
                        ordinal,
                        in_document,
                        f"{passage_stem}#{in_document}",
                        piece,
                        len(piece),
                        len(terms),
                    ),
                )
                passage_id = int(passage_row.lastrowid)
                connection.executemany(
                    "INSERT INTO retrieval_postings "
                    "(index_id, term, passage_id, tf) VALUES (?, ?, ?, ?)",
                    [
                        (index_id, term, passage_id, count)
                        for term, count in Counter(terms).items()
                    ],
                )
                ordinal += 1
                written += 1
                passages_n += 1
                total_tokens += len(terms)
                lengths.append(len(terms))
            connection.execute(
                "UPDATE retrieval_documents SET passages_n = ? WHERE id = ?",
                (written, document_id),
            )
            if written == 0 and not truncated:
                connection.execute(
                    "UPDATE retrieval_documents SET skipped_why = ? WHERE id = ?",
                    (
                        "read, and nothing in it survived the cut: every piece "
                        f"was shorter than {MIN_PASSAGE_CHARS} characters or had "
                        "no indexable term in it",
                        document_id,
                    ),
                )

        for number, document in enumerate(skipped, start=len(documents)):
            connection.execute(
                "INSERT INTO retrieval_documents "
                "(index_id, ordinal, doc_key, source, characters, passages_n, "
                " skipped_why) VALUES (?, ?, ?, ?, 0, 0, ?)",
                (
                    index_id,
                    number,
                    str(document["doc_key"]),
                    str(document["source"]),
                    str(document["skipped_why"]),
                ),
            )

        connection.execute(
            "UPDATE retrieval_indexes SET documents_n = ?, skipped_n = ?, "
            "passages_n = ?, total_tokens = ?, truncated = ? WHERE id = ?",
            (
                len(documents),
                len(skipped),
                passages_n,
                total_tokens,
                1 if truncated else 0,
                index_id,
            ),
        )

    report = read_index(index_id)
    report["short_fragments_dropped"] = short_fragments
    report["passages_with_no_indexable_term"] = empty_passages
    report["passage_tokens"] = _spread(lengths)
    return report


def _spread(values: list[int]) -> dict[str, Any]:
    """Smallest, median, largest and total over a list of counts.

    A mean on its own hides the thing worth seeing: a corpus whose median
    passage is 190 tokens and whose largest is 4 is not possible, and a corpus
    whose median is 8 has been cut into confetti. Every figure here is counted
    off the passages that were written.
    """
    if not values:
        return {"n": 0, "says": "no passage was written, so there is nothing to spread"}
    ordered = sorted(values)
    middle = len(ordered) // 2
    median = (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / 2.0
    )
    return {
        "n": len(ordered),
        "smallest": ordered[0],
        "median": median,
        "largest": ordered[-1],
        "total": sum(ordered),
        "counted_by": (
            "app/tools/retrieval.py's own tokeniser - lowercase runs of letters "
            "and digits - and NOT by any model's tokenizer. It is a count of "
            "these terms and is not a context-window budget."
        ),
    }


def read_index(index_id: int, *, sample: int = 3) -> dict[str, Any]:
    """One stored index as the report shape the siblings consume."""
    index = index_row(index_id)
    if index is None:
        return {"ok": False, "error": "no_such_index", "index_id": int(index_id)}
    documents = documents_of(index_id)
    skipped = [row for row in documents if row["skipped_why"]]
    first = passages_of(index_id, limit=max(0, int(sample)))

    summary = (
        f"Indexed {index['documents_n']} document(s) from {index['source_path']} "
        f"into {index['passages_n']} passage(s), {index['total_tokens']} term(s) "
        f"in total, scored by BM25 (k1={index['k1']}, b={index['b']}) on this "
        f"machine. Cut by: {index['cut_by']}."
    )
    if skipped:
        summary += f" {len(skipped)} document(s) produced no passage; each one says why."
    if index["truncated"]:
        summary += (
            f" THE INDEX STOPPED AT {MAX_PASSAGES} PASSAGES and does not cover the "
            "whole corpus. It can be searched and it must not be scored: a recall "
            "measured against part of a corpus is not a recall over the corpus."
        )
    return {
        "ok": True,
        "index_id": int(index["id"]),
        "thread_id": int(index["thread_id"]),
        "name": index["name"],
        "reused": False,
        "source_path": index["source_path"],
        "text_field": index["text_field"],
        "scorer": index["scorer"],
        "k1": index["k1"],
        "b": index["b"],
        "tokeniser": index["tokeniser"],
        "cut_by": index["cut_by"],
        "passage_chars": int(index["passage_chars"]),
        "passage_overlap": int(index["passage_overlap"]),
        "documents": int(index["documents_n"]),
        "passages": int(index["passages_n"]),
        "total_tokens": int(index["total_tokens"]),
        "skipped": [
            {
                "doc_key": row["doc_key"],
                "source": row["source"],
                "why": row["skipped_why"],
            }
            for row in skipped[:50]
        ],
        "skipped_n": len(skipped),
        "truncated": bool(index["truncated"]),
        "corpus_fingerprint": index["corpus_fingerprint"],
        "first_passages": [
            {
                "passage_key": row["passage_key"],
                "doc_key": row["doc_key"],
                "tokens": int(row["tokens"]),
                # EVERY CHARACTER HERE CAME OUT OF SOMEBODY'S FILE. A corpus is
                # the one thing in this product that is MADE OF other people's
                # text, which makes it the likeliest place for a line addressed
                # at the model to arrive. See `app/tools/data.py`'s boundary.
                "text": quarantine(
                    row["text"], source=f"{row['passage_key']} of {index['name']}"
                ),
            }
            for row in first
        ],
        "local": (
            "Built on this machine from files already on it. No network call, no "
            "model, no dependency outside the standard library and this "
            "repository."
        ),
        "decides_nothing": (
            "This tool says what was indexed. It measures no fact and opens no "
            "gate. Whether retrieval was tried is retrieval_tried, which is "
            "yours to say; whether the retriever works is "
            "measure_retriever_recall."
        ),
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Searching.


def search(
    *,
    query: str,
    thread_id: int | None,
    index_id: int | None = None,
    k: int = DEFAULT_K,
) -> dict[str, Any]:
    """The top k passages for one query. Stamps nothing, costs nothing."""
    found = _index_for(thread_id, index_id, doing="search", tool="search_the_index")
    if "error" in found:
        return found
    index = found["index"]
    depth = _clamped(k, DEFAULT_K, 1, MAX_K)
    text = str(query if query is not None else "")
    terms = tokenise(text)

    if not terms:
        return {
            "ok": False,
            "error": "no_query_terms",
            "index_id": int(index["id"]),
            "summary": (
                f"{text!r} has no indexable term in it - this tokeniser keeps "
                "lowercase runs of letters and digits and nothing else - so "
                "there is no query to run and no ranking to report. That is not "
                "an empty result set."
            ),
        }

    hits = _ranked(index, text, depth)
    return {
        "ok": True,
        "index_id": int(index["id"]),
        "index_name": index["name"],
        "query": text,
        "query_terms": terms,
        "k": depth,
        "returned": len(hits),
        "passages": [
            {
                "rank": hit["rank"],
                "score": hit["score"],
                "passage_key": hit["passage_key"],
                "doc_key": hit["doc_key"],
                "source": hit["doc_source"],
                "tokens": int(hit["tokens"]),
                "characters": int(hit["characters"]),
                "text": quarantine(
                    hit["text"], source=f"{hit['passage_key']} of {index['name']}"
                ),
            }
            for hit in hits
        ],
        "scorer": (
            f"BM25, k1={index['k1']}, b={index['b']}, over {index['passages_n']} "
            f"passages averaging "
            f"{int(index['total_tokens']) / max(1, int(index['passages_n'])):.1f} "
            "terms. Higher is better; the scale is not a probability and two "
            "scores from two different indexes are not comparable."
        ),
        "truncated_index": bool(index["truncated"]),
        "decides_nothing": (
            "This is what the retriever returned, for you to look at. It is not "
            "a measurement of anything: one query is one query, and how often "
            "the RIGHT passage comes back is measure_retriever_recall."
        ),
        "summary": (
            f"{len(hits)} passage(s) for {text!r} from {index['name']}, best "
            "first."
            if hits
            else (
                f"Not one passage in {index['name']} contains any of "
                f"{terms}. The index has {index['passages_n']} passage(s) in it. "
                "An empty result here is a real answer about this query and this "
                "corpus."
            )
        ),
    }


def _index_for(
    thread_id: int | None, index_id: int | None, *, doing: str, tool: str
) -> dict[str, Any]:
    """The index this call means, or the refusal that says why there is none.

    `tool` is taken rather than assumed: `evidence.thread_id_help` names the
    tool in the sentence it returns, and a refusal from the recall path that
    told the caller to add a thread to `search_the_index` would send them to the
    wrong door - which is the whole failure `evidence.thread_id_help` exists to
    avoid.
    """
    if thread_id is None:
        return {
            "ok": False,
            "error": "no_thread",
            **_thread_help(
                tool,
                f"An index belongs to one conversation and this call did not say "
                f"which, so there is nothing to {doing}. An index built in "
                "another conversation is somebody else's corpus as far as this "
                "one is concerned.",
            ),
        }
    if index_id is not None:
        index = index_row(int(index_id))
        if index is None or int(index["thread_id"]) != int(thread_id):
            return {
                "ok": False,
                "error": "no_such_index",
                "index_id": int(index_id),
                "detail": (
                    f"There is no index {int(index_id)} in this conversation. "
                    "Indexes belong to the conversation they were built in, for "
                    "the same reason facts do. Build one with "
                    "build_retrieval_index."
                ),
            }
        return {"index": index}
    mine = indexes_in(int(thread_id), limit=1)
    if not mine:
        return {
            "ok": False,
            "error": "no_index",
            "detail": (
                "This conversation has no retrieval index, so there is nothing "
                f"to {doing}. Point build_retrieval_index at a folder or a file "
                "on this machine first."
            ),
        }
    return {"index": mine[0]}


# ---------------------------------------------------------------------------
# Ground truth: the decision this whole module turns on.


def _normalise_key(value: Any) -> str:
    """A document or passage name, compared the way a person would compare one.

    Case-folded, whitespace-collapsed, and backslashes turned into forward
    slashes so that a ground-truth column written on Windows names the same
    document as one written anywhere else. Nothing else - no stemming, no
    fuzzy distance. A near-match is a guess about somebody's data.
    """
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip().replace(
        "\\", "/"
    ).casefold()


def _resolution_tables(index_id: int) -> dict[str, Any]:
    """Three lookups off one index, plus the names that are ambiguous.

    A basename that belongs to two documents is NOT put in the lookup. Two files
    called `README.md` under different folders are two documents; picking one
    would be a coin flip that decides somebody's recall number.
    """
    passages = passages_of(index_id)
    by_passage: dict[str, int] = {}
    by_document: dict[str, set[int]] = {}
    by_source: dict[str, set[int]] = {}
    basenames: dict[str, set[str]] = {}
    for row in passages:
        by_passage[_normalise_key(row["passage_key"])] = int(row["id"])
        by_document.setdefault(_normalise_key(row["doc_key"]), set()).add(int(row["id"]))
        by_source.setdefault(_normalise_key(row["doc_source"]), set()).add(int(row["id"]))
        stem = _normalise_key(str(row["doc_key"]).replace("\\", "/").rsplit("/", 1)[-1])
        basenames.setdefault(stem, set()).add(_normalise_key(row["doc_key"]))
    ambiguous = {stem for stem, keys in basenames.items() if len(keys) > 1}
    by_basename = {
        stem: by_document[next(iter(keys))]
        for stem, keys in basenames.items()
        if stem not in ambiguous and next(iter(keys)) in by_document
    }
    return {
        "passage": by_passage,
        "document": by_document,
        "source": by_source,
        "basename": by_basename,
        "ambiguous_basenames": sorted(ambiguous),
        "passages": passages,
    }


def _resolve(tables: dict[str, Any], value: Any) -> dict[str, Any]:
    """What in the index this ground-truth value names, or why nothing does.

    Four rules, in order, first match wins, and the rule that fired is REPORTED
    - because "the right passage came back" and "some passage from the right
    document came back" are different claims and the second is weaker.
    """
    key = _normalise_key(value)
    if not key:
        return {"resolved": False, "why": "the ground-truth cell is empty"}
    if key in tables["passage"]:
        return {
            "resolved": True,
            "level": PASSAGE_LEVEL,
            "by": "passage_key",
            "ids": {tables["passage"][key]},
        }
    if key in tables["document"]:
        return {
            "resolved": True,
            "level": DOCUMENT_LEVEL,
            "by": "doc_key",
            "ids": set(tables["document"][key]),
        }
    if key in tables["source"]:
        return {
            "resolved": True,
            "level": DOCUMENT_LEVEL,
            "by": "source path",
            "ids": set(tables["source"][key]),
        }
    if key in tables["basename"]:
        return {
            "resolved": True,
            "level": DOCUMENT_LEVEL,
            "by": "file name",
            "ids": set(tables["basename"][key]),
        }
    if key in tables["ambiguous_basenames"]:
        return {
            "resolved": False,
            "why": (
                f"{value!r} is the file name of more than one document in this "
                "index, and choosing between them would decide your recall "
                "number on a coin flip. Name the document by its path relative "
                "to the corpus root instead."
            ),
        }
    return {
        "resolved": False,
        "why": f"{value!r} names no document and no passage in this index",
    }


def _ground_truth_column(
    columns: list[str], named: str | None
) -> dict[str, Any]:
    """Which column carries the ground truth, or the refusal that says none does.

    THE REFUSAL IS THE POINT OF THIS FUNCTION. Auto-detection is allowed exactly
    once - a single conventional name, present, reported by name in the reply and
    in the stamp - and refuses in both other directions. Two candidates is a
    refusal rather than a precedence order, because choosing between two columns
    that both look like ground truth is a judgement about somebody's data whose
    error is silent: the number still comes out, it is just wrong.
    """
    if named:
        if str(named) in columns:
            return {"column": str(named), "how": "named in the call"}
        return {
            "error": "no_such_column",
            "detail": (
                f"{named!r} is not a column in this eval set. The columns it has "
                f"are: {columns}."
            ),
        }
    present = [name for name in GROUND_TRUTH_COLUMNS if name in columns]
    if len(present) == 1:
        return {
            "column": present[0],
            "how": (
                f"not named in the call; {present[0]!r} is the only column in "
                "this file with a conventional ground-truth name, so it was used "
                "and is reported here"
            ),
        }
    if len(present) > 1:
        return {
            "error": "ambiguous_ground_truth",
            "detail": (
                f"This eval set has {len(present)} columns that could be the "
                f"ground truth - {present} - and choosing between them is a "
                "judgement about your data, not a default. Name the one you mean "
                "with ground_truth_field."
            ),
            "candidates": present,
        }
    return {"error": "no_ground_truth", "candidates": [], "columns": columns}


NO_GROUND_TRUTH = (
    "Nothing was measured. Recall@k asks whether the RIGHT passage came back, "
    "and this eval set does not say which passage is right: {path} has the "
    "columns {columns} and not one of them names a document or a passage. Add a "
    "column holding, for each question, the document or passage that answers it "
    "- the path relative to the corpus root ({example_doc}), or one passage key "
    "({example_passage}) - and pass its name as ground_truth_field. I will not "
    "ask a model which passage was the right one and report the result as a "
    "measurement: that is a fabricated instrument, and retriever_recall_at_k is "
    "declared source: inspect precisely so that only a reading can fill it."
)


# ---------------------------------------------------------------------------
# The measurement.


def _rank_bounds(
    scores: dict[int, float], targets: set[int]
) -> tuple[int | None, int | None]:
    """The best and worst rank the right passage could take under ANY tie order.

    `(None, None)` when no passage of the target scored at all, which is an
    unambiguous miss at every depth: `_bm25_scores` only returns passages that
    hold at least one query term, so a passage that is absent from `scores` can
    never be returned however deep k goes.

    Otherwise, with `s` the best score any target passage reached:

        best  = 1 + (passages scoring strictly more than s)
        worst = best + (NON-target passages scoring exactly s)

    Exact equality is the right comparison and not a sloppy one. Two passages
    tie at the bit level when the arithmetic over them was identical - which is
    what a duplicated document in a corpus produces, and a duplicated document
    (a vendored copy, a `report (1).md`) is an ordinary corpus rather than a
    contrived one. Two passages whose scores merely round to the same display
    are ordered by their scores, and the retriever decided them.
    """
    reachable = [scores[passage] for passage in targets if passage in scores]
    if not reachable:
        return None, None
    best_score = max(reachable)
    better = sum(1 for score in scores.values() if score > best_score)
    tied = sum(
        1
        for passage, score in scores.items()
        if score == best_score and passage not in targets
    )
    return better + 1, better + tied + 1


def _tie_decided(best_rank: int | None, worst_rank: int | None, k: int) -> bool:
    """True when `is the right passage in the top k` is answered by the tie-break.

    THE CASE THIS EXISTS FOR, MEASURED. A corpus holding `alpha.md` and a
    byte-identical copy of it, ground truth `alpha.md`, k=1: with the copy named
    `zzz_copy.md` the recall is 1.0 and with it named `aaa_copy.md` the recall is
    0.0 - same corpus, same query, same retriever, same ground truth, and the
    number is the alphabetical order of two file names. `_resolve` already
    refuses an ambiguous BASENAME because *"choosing between them would decide
    your recall number on a coin flip"*; identical CONTENT is the same coin flip
    one layer down, and this is where it is noticed.
    """
    if best_rank is None or worst_rank is None:
        return False
    return (best_rank <= k) != (worst_rank <= k)


def score_recall(
    *,
    eval_path: str,
    question_field: str,
    thread_id: int | None,
    index_id: int | None = None,
    ground_truth_field: str | None = None,
    answer_field: str | None = None,
    k: int = DEFAULT_K,
    max_questions: int = MAX_QUESTIONS,
    full_rows: bool = False,
) -> dict[str, Any]:
    """Score the retriever alone on an eval set. Stamps nothing; reports all.

    The one thing this function decides is `stampable`: True only when a real
    scored run happened over real rows with real ground truth and reached the
    end. The tool handler stamps on that and on nothing else, so the rule lives
    in one place and a sibling that wants the number without the ledger gets the
    same verdict about whether it is worth anything.

    `full_rows` adds `all_rows`, every scored row rather than the first fifty,
    and it exists for ONE caller: `compare_chunkings` pairs settings question by
    question, and a comparison built on a truncated list of rows would silently
    pair the first fifty and call the answer a comparison of the eval set. The
    tool handler never passes it - `rows` stays capped in anything a person or a
    model reads - so this is a Python door for a sibling bench and not a change
    to what `measure_retriever_recall` returns.
    """
    found = _index_for(
        thread_id, index_id, doing="score", tool="measure_retriever_recall"
    )
    if "error" in found:
        return found
    index = found["index"]

    depth = _clamped(k, DEFAULT_K, 1, MAX_K)
    cap = _clamped(max_questions, MAX_QUESTIONS, 1, MAX_QUESTIONS)

    if not Path(str(eval_path)).exists():
        return {
            "ok": False,
            "error": "no_such_eval_set",
            "summary": (
                f"There is nothing at {eval_path}, so there are no questions to "
                "score. Nothing was measured."
            ),
        }

    rows, columns, seen = _read_eval_rows(str(eval_path), cap)
    if not seen:
        return {
            "ok": False,
            "error": "no_rows",
            "summary": (
                f"No row could be read from {eval_path}. Nothing was measured."
            ),
        }
    if str(question_field) not in columns:
        return {
            "ok": False,
            "error": "no_such_question_column",
            "summary": (
                f"No row in {eval_path} has a {question_field!r} column. The "
                f"columns present are {columns}. Nothing was measured."
            ),
            "columns": columns,
        }

    tables = _resolution_tables(int(index["id"]))
    example_document = (
        tables["passages"][0]["doc_key"] if tables["passages"] else "documents/one.md"
    )
    example_passage = (
        tables["passages"][0]["passage_key"]
        if tables["passages"]
        else "documents/one.md#0"
    )

    chosen = _ground_truth_column(columns, ground_truth_field)
    if "error" in chosen:
        if chosen["error"] == "no_ground_truth":
            sentence = NO_GROUND_TRUTH.format(
                path=eval_path,
                columns=columns,
                example_doc=example_document,
                example_passage=example_passage,
            )
        else:
            sentence = "Nothing was measured. " + chosen["detail"]
        return _refusal(
            index,
            eval_path=str(eval_path),
            error=chosen["error"],
            sentence=sentence,
            columns=columns,
            depth=depth,
            rows=rows,
            question_field=str(question_field),
            answer_field=answer_field,
            candidates=chosen.get("candidates"),
        )

    column = chosen["column"]
    # EVERY ROW THE FILE HELD IS ACCOUNTED FOR, AND THE ONES THAT ARE NOT
    # SCORABLE ARE COUNTED RATHER THAN DROPPED.
    #
    # This used to be a filter, and the rows it removed were not counted, not
    # reported and not remembered - so a 500-row eval set with one labelled row
    # stamped `1 of 1 questions in <file>` at MEASURED with an empty
    # `not_measured`, and every sentence a person read was true about a
    # denominator nobody had told them about. A partially-labelled eval set -
    # somebody labels twenty rows of five hundred and means to finish - is the
    # most ordinary shape a hand-made eval file has.
    #
    # It is the SAME CLAIM as `unresolved`, which this module already refuses in
    # its own words: a recall over the rows that happened to join is not a
    # recall over the eval set. A blank cell is that situation with the join
    # missing instead of broken, so it blocks the stamp the same way.
    eligible: list[dict[str, Any]] = []
    unlabelled: list[dict[str, Any]] = []
    unlabelled_by_reason: Counter[str] = Counter()
    for number, row in enumerate(rows):
        has_question = (
            row.get(str(question_field)) is not None
            and str(row.get(str(question_field))).strip()
        )
        has_truth = row.get(column) is not None and str(row.get(column)).strip()
        if has_question and has_truth:
            eligible.append(row)
            continue
        if has_question:
            why = f"a question with nothing in {column!r}"
        elif has_truth:
            why = f"a ground truth with nothing in {question_field!r}"
        else:
            why = f"neither a {question_field!r} nor a {column!r}"
        unlabelled_by_reason[why] += 1
        unlabelled.append({"row": number, "why": why})
    if not eligible:
        return _refusal(
            index,
            eval_path=str(eval_path),
            error="no_scorable_rows",
            sentence=(
                f"Nothing was measured. {column!r} is in {eval_path} and not one "
                f"row has a value in both {question_field!r} and {column!r}, so "
                "there is no question with a right answer attached. A measured "
                "zero here would be a statement about the columns and not about "
                "the retriever."
            ),
            columns=columns,
            depth=depth,
            rows=rows,
            question_field=str(question_field),
            answer_field=answer_field,
        )

    # -- run it ---------------------------------------------------------------
    unresolved: list[dict[str, Any]] = []
    per_row: list[dict[str, Any]] = []
    levels: Counter[str] = Counter()
    matched_by: Counter[str] = Counter()
    hits_at: list[int] = [0] * depth
    ties_at: list[int] = [0] * depth
    tie_decided: list[dict[str, Any]] = []

    for number, row in enumerate(eligible):
        question = str(row[str(question_field)])
        wanted = row[column]
        target = _resolve(tables, wanted)
        if not target["resolved"]:
            unresolved.append(
                {"row": number, "ground_truth": str(wanted)[:200], "why": target["why"]}
            )
            continue
        ranked, scores = _ranked_and_scored(index, question, depth)
        found_at: int | None = None
        for hit in ranked:
            if int(hit["id"]) in target["ids"]:
                found_at = int(hit["rank"])
                break
        levels[target["level"]] += 1
        matched_by[target["by"]] += 1
        if found_at is not None:
            for position in range(found_at - 1, depth):
                hits_at[position] += 1
        best_rank, worst_rank = _rank_bounds(scores, target["ids"])
        ambiguous = [
            position + 1
            for position in range(depth)
            if _tie_decided(best_rank, worst_rank, position + 1)
        ]
        for k_value in ambiguous:
            ties_at[k_value - 1] += 1
        if depth in ambiguous:
            tie_decided.append(
                {
                    "row": number,
                    "question": question[:200],
                    "ground_truth": str(wanted)[:200],
                    "why": (
                        f"the right passage scored exactly what "
                        f"{(worst_rank or 0) - (best_rank or 0)} other passage(s) "
                        f"in this index scored, so whether it lands inside the "
                        f"top {depth} is decided by the tie-break and not by the "
                        "retriever"
                    ),
                }
            )
        per_row.append(
            {
                "row": number,
                "question": question[:200],
                "ground_truth": str(wanted)[:200],
                "level": target["level"],
                "matched_by": target["by"],
                "found_at_rank": found_at,
                "best_possible_rank": best_rank,
                "worst_possible_rank": worst_rank,
                "tie_decided_at_k": ambiguous,
                "top_passage": ranked[0]["passage_key"] if ranked else None,
                "returned": [hit["passage_key"] for hit in ranked],
            }
        )

    scored = len(per_row)
    # THE PROXY IS COUNTED OVER EVERY ROW READ, not over the labelled ones. Its
    # own eligibility rule is a question and an answer, and the ground-truth
    # column has nothing to do with it - so counting it over `eligible` here
    # while `_refusal` counts it over `rows` would give the same file two
    # different denominators depending on whether its ground-truth column
    # happened to be readable. One rule, stated in `of`, on both paths.
    hit_rate = _answer_in_passage(index, rows, question_field, answer_field, depth)

    hit_cap = seen > cap
    level = _one_level(levels)
    stampable = bool(
        scored
        and not unresolved
        and not unlabelled
        and not tie_decided
        and not hit_cap
        and not index["truncated"]
    )

    payload: dict[str, Any] = {
        "ok": True,
        "index_id": int(index["id"]),
        "index_name": index["name"],
        "eval_path": str(eval_path),
        "question_field": str(question_field),
        "ground_truth_field": column,
        "ground_truth_chosen_how": chosen["how"],
        "ground_truth_level": level,
        "levels": dict(levels),
        "matched_by": dict(matched_by),
        "k": depth,
        "questions_scored": scored,
        "questions_eligible": len(eligible),
        "rows_seen": seen,
        "rows_read": len(rows),
        "hit_row_cap": hit_cap,
        "unlabelled_rows": unlabelled[:20],
        "unlabelled_n": len(unlabelled),
        "unlabelled_by_reason": dict(unlabelled_by_reason),
        "tie_decided_rows": tie_decided[:20],
        "tie_decided_n": len(tie_decided),
        "hits": hits_at[depth - 1] if scored else 0,
        "recall_at_k": (hits_at[depth - 1] / scored) if scored else None,
        "recall_curve": [
            {"k": position + 1, "hits": hits_at[position],
             "of": scored,
             "recall": (hits_at[position] / scored) if scored else None,
             # How many of those rows a score tie decided rather than the
             # retriever. A curve entry is a displayed number too, and it gets
             # the same disclosure the headline gets.
             "tie_decided": ties_at[position]}
            for position in range(depth)
        ],
        "unresolved_ground_truth": unresolved[:20],
        "unresolved_n": len(unresolved),
        "rows": per_row[:50],
        "misses": [row for row in per_row if row["found_at_rank"] is None][:20],
        "answer_in_passage": hit_rate,
        "resolution": evals.resolution_for(hits_at[depth - 1] if scored else 0, scored),
        "stampable": stampable,
        "scorer": (
            f"BM25, k1={index['k1']}, b={index['b']}, over {index['passages_n']} "
            "passages. No model was asked anything and nothing left this machine."
        ),
        "decides_nothing": (
            "This is a measurement of the retriever alone. It does not say the "
            "answer would be right, it does not set retrieval_tried - which is "
            "yours to say - and it opens no gate by itself."
        ),
    }
    if full_rows:
        payload["all_rows"] = per_row
    payload["summary"] = _summarise_recall(payload, index)
    return payload


def _one_level(levels: Counter[str]) -> str | None:
    """`passage`, `document`, or `mixed` - never a silent majority.

    A run where some rows named a passage and some named a document is scored
    honestly row by row, and the headline says `mixed`, because a single word
    that covered both would be describing the stronger claim with the weaker
    evidence under it.
    """
    if not levels:
        return None
    if len(levels) == 1:
        return next(iter(levels))
    return "mixed"


def _read_eval_rows(path: str, cap: int) -> tuple[list[dict[str, Any]], list[str], int]:
    """`(rows up to the cap, every column seen, rows seen)`.

    The file is read PAST the cap so that `rows_seen` is a real count and a run
    can tell whether the cap bit. Only `cap` rows are kept.
    """
    rows: list[dict[str, Any]] = []
    columns: set[str] = set()
    seen = 0
    stream = dataquality.iter_records(path)
    try:
        for record in stream:
            if not isinstance(record, dict):
                record = {"value": record}
            seen += 1
            if len(columns) < dataquality.COLUMN_CAP:
                columns.update(str(key) for key in record)
            if len(rows) < cap:
                rows.append(record)
    finally:
        stream.close()
    return rows, sorted(columns), seen


def _answer_in_passage(
    index: dict[str, Any],
    rows: list[dict[str, Any]],
    question_field: Any,
    answer_field: str | None,
    depth: int,
) -> dict[str, Any] | None:
    """The WEAKER PROXY, computed only when asked, and never called recall.

    `docs/PRODUCT_SPEC.md` §6.6: *"an unlabelled eval set gives a retrieval hit
    rate the user must verify, clearly marked as such, never a recall number."*
    This is that hit rate. It is returned under its own name, it carries the
    sentence saying what it is not, and no code path anywhere in this module
    stamps `retriever_recall_at_k` from it.

    The two ways it comes apart from recall are named in the reply rather than
    left for a reader to work out, because a number that is usually close to the
    right one is the most dangerous kind.
    """
    if not answer_field:
        return None
    field = str(answer_field)
    scored = 0
    hits = 0
    for row in rows:
        answer = row.get(field)
        question = row.get(str(question_field))
        if answer is None or not str(answer).strip():
            continue
        if question is None or not str(question).strip():
            continue
        scored += 1
        wanted = evals.normalise_answer(answer)
        if not wanted:
            continue
        for hit in _ranked(index, str(question), depth):
            if wanted in evals.normalise_answer(hit["text"]):
                hits += 1
                break
    if not scored:
        return None
    return {
        "name": "answer_in_passage_rate",
        "hits": hits,
        "of": scored,
        "rate": hits / scored,
        "answer_field": field,
        "k": depth,
        "is_not_recall": (
            "THIS IS NOT retriever_recall_at_k AND IS NEVER STAMPED AS IT. It "
            "counts how often the expected answer's text appears somewhere in "
            "the top passages, which is a different claim from 'the right "
            "passage was retrieved', and the diagnosis engine reads the second. "
            "It comes apart in both directions: a one-word answer like 'yes' is "
            "in almost every passage, so this reads high on a retriever that "
            "returned nothing useful; and a document that paraphrases its own "
            "answer does not contain the answer string, so this reads low on a "
            "retriever that was perfect. Verify it by eye against the passages "
            "search_the_index returns before you believe it."
        ),
        "provenance": (
            "measured by app/tools/retrieval.py over the rows named above, and "
            "recorded nowhere: it is not a fact this harness's ledger declares, "
            "so it is reported and never stored as one."
        ),
    }


def _refusal(
    index: dict[str, Any],
    *,
    eval_path: str,
    error: str,
    sentence: str,
    columns: list[str],
    depth: int,
    rows: list[dict[str, Any]],
    question_field: str,
    answer_field: str | None,
    candidates: list[str] | None = None,
) -> dict[str, Any]:
    """A refusal in THE SAME SHAPE as a successful call, with `measured` empty.

    The brief asked for this shape and it is the right one: a caller that
    special-cases a refusal is a caller that can forget to. Every key a scored
    run returns is here, holding the honest null, and `not_measured` carries the
    sentence that names what would fix it.
    """
    proxy = _answer_in_passage(index, rows, question_field, answer_field, depth)
    payload: dict[str, Any] = {
        "ok": True,
        "error": error,
        "index_id": int(index["id"]),
        "index_name": index["name"],
        "eval_path": eval_path,
        "question_field": question_field,
        "ground_truth_field": None,
        "ground_truth_chosen_how": None,
        "ground_truth_level": None,
        "levels": {},
        "matched_by": {},
        "k": depth,
        "questions_scored": 0,
        "questions_eligible": 0,
        "rows_read": len(rows),
        "hits": None,
        "recall_at_k": None,
        "recall_curve": [],
        "unresolved_ground_truth": [],
        "unresolved_n": 0,
        "unlabelled_rows": [],
        "unlabelled_n": 0,
        "unlabelled_by_reason": {},
        "tie_decided_rows": [],
        "tie_decided_n": 0,
        "rows": [],
        "misses": [],
        "answer_in_passage": proxy,
        "resolution": evals.resolution_for(0, 0),
        "stampable": False,
        "columns": columns,
        "measured": [],
        "not_measured": sentence,
        "summary": sentence,
        "decides_nothing": (
            "Nothing was measured, so nothing was recorded and no gate moved. "
            "The engine still has retriever_recall_at_k as null, which is the "
            "true state of knowledge."
        ),
    }
    if candidates:
        payload["candidates"] = candidates
    return payload


def _summarise_recall(payload: dict[str, Any], index: dict[str, Any]) -> str:
    """The count, then what that many rows can resolve, then what was not done."""
    scored = payload["questions_scored"]
    if not scored:
        return (
            "Not one question could be scored: every eligible row's ground truth "
            "names something this index does not contain. Nothing was measured."
        )
    hits = payload["hits"]
    level = payload["ground_truth_level"]
    what = {
        PASSAGE_LEVEL: "the right passage",
        DOCUMENT_LEVEL: "a passage from the right document",
    }.get(str(level), "the right passage or document")
    line = (
        f"{hits} of {scored} questions had {what} in the top {payload['k']} "
        f"({payload['recall_at_k']:.0%}), measured against {index['name']} - "
        f"{index['passages_n']} passages from {index['documents_n']} documents, "
        f"BM25, on this machine. Ground truth came from the "
        f"{payload['ground_truth_field']!r} column, {payload['ground_truth_chosen_how']}."
    )
    curve = ", ".join(
        f"k={entry['k']} {entry['hits']}/{entry['of']}"
        for entry in payload["recall_curve"]
    )
    line += f" Recall rises with k and here is the whole curve: {curve}."
    line += f" {payload['resolution']['says']}"
    if payload["unresolved_n"]:
        line += (
            f" {payload['unresolved_n']} row(s) name a document or passage this "
            "index does not contain and were not scored at all - and because of "
            "them nothing was recorded, since a recall over the rows that "
            "happened to join is not a recall over the eval set."
        )
    if payload["unlabelled_n"]:
        reasons = ", ".join(
            f"{count} carried {why}"
            for why, count in sorted(payload["unlabelled_by_reason"].items())
        )
        line += (
            f" {payload['unlabelled_n']} of the {payload['rows_read']} row(s) "
            f"read from {payload['eval_path']} could not be scored at all "
            f"({reasons}), so the {scored} above is a count over the rows that "
            "happened to be labelled and not over your eval set - and nothing "
            "was recorded. Label the rest, or point this at a file holding only "
            "the rows you labelled, and the number will be about a denominator "
            "you can see."
        )
    if payload["tie_decided_n"]:
        line += (
            f" {payload['tie_decided_n']} row(s) were decided by a tie rather "
            "than by the retriever: the right passage scored exactly what one or "
            f"more other passages scored, so whether it fell inside the top "
            f"{payload['k']} is the tie-break's answer and not a measurement. "
            "Duplicate documents in the corpus are the usual cause. Nothing was "
            "recorded."
        )
    if payload["hit_row_cap"]:
        line += (
            f" The run stopped at {payload['rows_read']} of {payload['rows_seen']} "
            "rows, so it scored a prefix of the file rather than the file, and "
            "nothing was recorded."
        )
    if index["truncated"]:
        line += (
            " The index itself is truncated, so this is a recall over part of "
            "your corpus and nothing was recorded."
        )
    return line


# ---------------------------------------------------------------------------
# The sweep. Several chunkings, one eval set, and a verdict that refuses.
#
# THE FAILURE THIS SECTION EXISTS TO SURVIVE IS NOT THE ONE `evals.compare`
# SURVIVES. `evals.compare` answers "are these two different"; a sweep asks
# "which of these N is best", and that question has two new ways of lying in it
# that the two-run case does not:
#
#   1. THE MAXIMUM OF N NOISY ESTIMATES IS BIASED UPWARD. Score eight settings
#      on ninety questions, report the best, and its recall is optimistic EVEN
#      IF every setting is truly identical - the maximum was selected on noise
#      and then reported as though it had been chosen in advance.
#   2. EIGHT SETTINGS IS TWENTY-EIGHT PAIRWISE TESTS. At p<0.05 apiece, TWO IN
#      FIVE families of eight settings that do not differ at all contain at
#      least one false separation - 42.0% of 200 seeded null families, measured
#      in `test_pure_noise_between_eight_settings_separates_nothing_and_the_
#      correction_is_why`, against 3.5% of the same families after Holm. That
#      is `evals.py`'s "a user shown forty unresolvable deltas will believe the
#      tenth" arriving in a new costume.
#
#      THIS SAID "ROUGHLY A ONE-IN-THREE CHANCE" UNTIL 2026-08-21 and the same
#      clause was in the reply the user reads. It was wrong at every family
#      size the tool allows and it was never measured: 33% is what 1-(1-.05)^k
#      gives at k=8, and eight SETTINGS is k=28, where the independent figure
#      is 76.2% and the measured one is 42.0%. The two differ because these
#      tests share their questions and McNemar's exact test is discrete. The
#      figure above is the measured one and the simulation is named beside it.
#
# Three answers, all of them here, none of them sufficient alone:
#
#   * HOLM-BONFERRONI over the family of pairwise tests actually run, which
#     controls the probability of ANY false separation under arbitrary
#     dependence - and these tests are heavily dependent, because every one of
#     them is over the same questions. Holm rather than plain Bonferroni
#     because it is uniformly more powerful and needs no independence
#     assumption either. This answers (2) and does NOTHING about (1).
#   * NOTHING IS CROWNED. The verdict is a SET - the settings nothing else was
#     shown to beat - and where the family separates nothing at all the answer
#     is NO EVIDENCE in those words. `compare_hit_vectors` has no code path
#     that returns a single winner.
#   * A SPLIT-HALF CONFIRMATION, which is the only one of the three that
#     touches (1). The questions are split alternately; the setting with the
#     highest recall on one half is looked up on the other half, which played
#     no part in choosing it, and both numbers are reported. The gap between
#     them is the selection bias, MEASURED ON THE USER'S OWN ROWS rather than
#     asserted.
#
# AND THE SWEEP STAMPS NOTHING. `retriever_recall_at_k` is `source: inspect`
# and `measure_retriever_recall` is its only instrument; a best-of-N recall is
# a maximum selected on the same questions it is reported against, and stamping
# it would put the one number in this bench that opens a gate under exactly the
# defect this section is about. See `WHAT THE SWEEP MAY NOT STAMP` on
# `sweep_chunkings`.


#: The family-wise error rate the sweep is corrected to hold. NOT an argument,
#: on purpose: an alpha a caller can raise is a winner a caller can buy, and
#: `evals.compare` fixes the same 0.05 in code for the same reason.
SWEEP_ALPHA = 0.05

#: Fewer settings than this is not a comparison. Two is the smallest sweep, and
#: it is exactly the case `evals.compare` was built for.
MIN_SETTINGS = 2

#: The largest sweep this tool will run, and the bound is about what a sweep can
#: RESOLVE rather than about how long it takes. Cost is linear in settings - one
#: whole rebuild each - and the pairwise family is quadratic: twelve settings is
#: sixty-six comparisons, a Holm threshold of 0.05/66, and (see
#: `min_discordant_for`) no pair can reach it unless twelve questions change
#: their verdict between those two settings.
#:
#: AND THE NUMBER TWELVE IS A JUDGEMENT, NOT A DERIVATION. That is said here
#: because the paragraph above reads like one and an earlier version of it left
#: the distinction to be inferred. The floor climbs in steps and sits on a
#: plateau across this cap: eleven, twelve, thirteen and fourteen settings all
#: need twelve changed questions, and the next step to thirteen changed
#: questions is at fifteen settings. So nothing in the arithmetic singles out
#: twelve - what the arithmetic says is that the floor is already twelve
#: questions here, that it never comes back down, and that every setting added
#: past this point tightens the threshold for every REAL comparison in the
#: sweep. Where on the plateau to stop is a choice, and it is this one.
#: `tests/test_a_sweep_of_chunkings_crowns_nothing.py` asserts the plateau, so a
#: future edit that moves the cap has to look at the shape rather than the
#: sentence.
MAX_SETTINGS = 12

#: The four levers `NO_TRAIN__FIX_RETRIEVAL` names, and which of them this
#: machine can actually pull. THREE OF THE FOUR ARE REFUSALS OF HONESTY RATHER
#: THAN OF EFFORT, and they are named in every reply this tool produces -
#: including every refusal - because a person told "fix your retriever" deserves
#: to know which of the four things we can do with them and which they must do
#: themselves. Quietly shipping the one we own and omitting the other three
#: would read as though chunking were the whole of the answer.
LEVERS_WE_DO_NOT_OWN = (
    {
        "lever": "hybrid BM25 + dense retrieval",
        "why_not": (
            "a dense retriever needs an embedding model, and this harness ships "
            "no AI. rank_bm25, sentence-transformers and faiss are not installed "
            "and adding one is a new dependency; the connected Ollama on this "
            "machine holds chat models and no embedding model."
        ),
        "who_can": (
            "you, by connecting an embedding model - at which point every number "
            "it produced would be a number about that endpoint, would have to "
            "say so, and would mean sending your corpus through it. That is a "
            "different tool with a different provenance and a different egress "
            "conversation, and it is not this one."
        ),
    },
    {
        "lever": "a cross-encoder reranker",
        "why_not": (
            "the same reason with a heavier model attached: a cross-encoder is a "
            "model, this harness ships none, and there is no reranker on this "
            "machine to call."
        ),
        "who_can": (
            "you, with your own reranker. The bench would then measure it the "
            "same way it measures chunking here - one lever at a time, paired, "
            "on the same eval set - because two levers at once is not an "
            "experiment."
        ),
    },
    {
        "lever": "query rewriting",
        "why_not": (
            "rewriting a query means asking a model to write a new one, so the "
            "recall it produced would be a fact about your connected model and "
            "not about your retriever, and this file makes no network call at "
            "all."
        ),
        "who_can": (
            "you, with your own connected model - and the resulting number "
            "belongs to that model as much as to the index, which is why it "
            "cannot be reported next to these as though it were the same "
            "measurement."
        ),
    },
)

#: The one lever this file owns, said in the same breath as the three it does
#: not, so the sentence a person reads is a complete answer rather than the
#: flattering half of one.
LEVER_WE_OWN = (
    "chunking - passage_chars and passage_overlap, which build_retrieval_index "
    "declares as a stated choice rather than a measured optimum. It is local, "
    "it costs no tokens, it sends nothing anywhere, and it is the only one of "
    "the four this harness can vary and re-measure for you."
)


def min_discordant_for(alpha: float) -> int:
    """The fewest CHANGED questions McNemar's exact test needs to reach `alpha`.

    Two-sided exact McNemar over `m` discordant rows is at its smallest when
    every one of them goes the same way, and then

        p = 2 * C(m, 0) / 2**m = 2**(1 - m)

    so no arrangement of fewer than `m` changed rows can reach `alpha`, whatever
    the two recalls look like. That makes "how many questions would have to
    change" arithmetic rather than a rule of thumb, and it is the sweep's
    version of `evals.rows_for_points` - the sentence a refusal owes the person
    reading it, which is not "no" but "no, and here is what would make it yes".
    """
    if alpha >= 1.0:
        return 1
    needed = 1
    while needed < 4096:
        if 2.0 ** (1 - needed) <= alpha:
            return needed
        needed += 1
    return needed  # pragma: no cover - alpha below 2**-4095 is not reachable


def holm(p_values: list[float], alpha: float = SWEEP_ALPHA) -> list[dict[str, Any]]:
    """Holm-Bonferroni, step-down, over a family of p-values. One row per test.

    HOLM RATHER THAN BONFERRONI because it is uniformly more powerful and gives
    up nothing: both control the family-wise error rate - the chance of making
    ANY false claim of a difference - and Holm does it without assuming the
    tests are independent, which matters here because they are the opposite of
    independent. Every comparison in a sweep is over the same questions against
    the same corpus, so the p-values move together.

    FAMILY-WISE AND NOT FALSE-DISCOVERY, because of what the claim is. A sweep
    that separates a pair is about to tell somebody "this chunking is better
    than that one, go and use it". One such sentence being wrong is the failure;
    controlling the expected PROPORTION of wrong ones is the wrong error rate
    for a tool that will usually make only a handful of claims.

    Sorted ascending, `p_(j)` is compared against `alpha / (m - j)`, and the
    procedure stops at the first test that fails - every test after it is not
    separated regardless of its own p. `adjusted_p` is the monotone
    Holm-adjusted value, reported so a reader can see how far a p was from the
    line rather than only which side of it it fell.
    """
    count = len(p_values)
    if count == 0:
        return []
    order = sorted(range(count), key=lambda position: (p_values[position], position))
    out: list[dict[str, Any]] = [{} for _ in range(count)]
    still_rejecting = True
    running = 0.0
    for rank, position in enumerate(order):
        remaining = count - rank
        threshold = alpha / remaining
        running = max(running, min(1.0, remaining * float(p_values[position])))
        separated = still_rejecting and float(p_values[position]) <= threshold
        if not separated:
            still_rejecting = False
        out[position] = {
            "p": float(p_values[position]),
            "rank_in_family": rank + 1,
            "holm_threshold": threshold,
            "adjusted_p": running,
            "separated": separated,
        }
    return out


def compare_hit_vectors(
    vectors: list[tuple[str, list[bool]]], *, alpha: float = SWEEP_ALPHA
) -> dict[str, Any]:
    """The whole statistical verdict, over hit vectors and nothing else.

    PURE, AND SEPARATED FROM THE INDEXES ON PURPOSE. Everything above this
    function is about corpora and BM25; everything in it is arithmetic over
    booleans. That is what lets the null be CONSTRUCTED rather than argued
    about: a test can hand this function eight settings that are drawn from one
    distribution - genuinely identical, differing only by noise - and read what
    the tool says. A statistical guard welded to an index is a guard that can
    only ever be checked on whatever corpus somebody happens to have.

    `vectors` is `[(setting label, [hit, hit, ...]), ...]`, every vector the
    same length and over THE SAME QUESTIONS IN THE SAME ORDER. That is the
    pairing, and it is the caller's job to establish it; this function checks
    the lengths and can check nothing else.

    Reuses `evals.mcnemar` and `evals.resolution_for` rather than re-deriving
    them, for the reason this module already imports `resolution_for`: a recall
    and an eval score stated by two different instruments are two numbers a
    person cannot put beside each other.
    """
    if len(vectors) < MIN_SETTINGS:
        return {
            "ok": False,
            "error": "not_enough_settings",
            "detail": (
                f"{len(vectors)} setting(s) is not a comparison. A sweep needs at "
                f"least {MIN_SETTINGS}."
            ),
        }
    labels = [str(label) for label, _ in vectors]
    if len(set(labels)) != len(labels):
        return {
            "ok": False,
            "error": "duplicate_settings",
            "detail": (
                "Two settings in this family carry the same label, so one of them "
                "is being compared with itself. That inflates the family size and "
                "adds a comparison whose answer is known in advance."
            ),
        }
    hits = [[bool(value) for value in vector] for _, vector in vectors]
    widths = {len(vector) for vector in hits}
    if len(widths) != 1:
        return {
            "ok": False,
            "error": "unpaired_vectors",
            "detail": (
                f"These settings were scored over different numbers of questions "
                f"({sorted(widths)}), so there is nothing to pair. A difference "
                "between two settings means something only over the questions "
                "both of them answered."
            ),
        }
    n = widths.pop()
    if n <= 0:
        return {
            "ok": False,
            "error": "no_questions",
            "detail": (
                "Not one question was scored by every setting, so there is "
                "nothing to compare. Nothing was measured."
            ),
        }

    per_setting = []
    for position, label in enumerate(labels):
        correct = sum(1 for value in hits[position] if value)
        per_setting.append(
            {
                "setting": label,
                "hits": correct,
                "of": n,
                "recall": correct / n,
                "resolution": evals.resolution_for(correct, n),
            }
        )

    pairs: list[dict[str, Any]] = []
    raw: list[float] = []
    for first in range(len(labels)):
        for second in range(first + 1, len(labels)):
            improved = sum(
                1
                for row in range(n)
                if hits[first][row] and not hits[second][row]
            )
            regressed = sum(
                1
                for row in range(n)
                if hits[second][row] and not hits[first][row]
            )
            p_value = evals.mcnemar(improved, regressed)
            raw.append(p_value)
            pairs.append(
                {
                    "a": labels[first],
                    "b": labels[second],
                    # `a_better` is the count of questions a got right and b did
                    # not. The rows both settings agree on carry NO information
                    # about the difference and are correctly absent from every
                    # number in this row - which is the whole reason the sweep
                    # keeps a hit vector per setting rather than a rate.
                    "a_better_on": improved,
                    "b_better_on": regressed,
                    "changed": improved + regressed,
                    "agreed": n - improved - regressed,
                    "delta": (improved - regressed) / n,
                    "test": (
                        "McNemar, two-sided exact binomial over the questions "
                        "whose verdict changed"
                    ),
                }
            )
    marks = holm(raw, alpha)
    tightest = alpha / len(pairs) if pairs else alpha
    needed_discordant = min_discordant_for(tightest)
    for pair, mark in zip(pairs, marks):
        pair.update(mark)
        pair["better"] = (
            pair["a"]
            if pair["a_better_on"] > pair["b_better_on"]
            else pair["b"]
            if pair["b_better_on"] > pair["a_better_on"]
            else None
        )
        pair["min_changed_questions_to_separate"] = min_discordant_for(
            pair["holm_threshold"]
        )
        pair["says"] = _pair_sentence(pair, n)

    beaten_by: dict[str, list[str]] = {label: [] for label in labels}
    for pair in pairs:
        if pair["separated"] and pair["better"]:
            loser = pair["b"] if pair["better"] == pair["a"] else pair["a"]
            beaten_by[loser].append(str(pair["better"]))
    unbeaten = [label for label in labels if not beaten_by[label]]
    separated_n = sum(1 for pair in pairs if pair["separated"])

    top = max(row["hits"] for row in per_setting)
    bottom = min(row["hits"] for row in per_setting)
    highest = [row["setting"] for row in per_setting if row["hits"] == top]
    most_changed = max((pair["changed"] for pair in pairs), default=0)

    if len(highest) == len(labels):
        leader = (
            f"Every one of the {len(labels)} settings scored exactly {top} of "
            f"{n}, so there is not even an apparent leader to be tempted by."
        )
    elif len(highest) > 1:
        leader = (
            f"{len(highest)} settings tie for the highest recall in this sweep "
            f"at {top} of {n} - {highest} - AND A TIE AT THE TOP IS NOT A "
            "SHORTLIST."
        )
    else:
        leader = (
            f"{highest[0]!r} has the highest recall in this sweep at {top} of "
            f"{n}, AND THAT IS NOT A WINNER."
        )
    selected_on_noise = (
        leader + f" The largest of {len(labels)} estimates measured on the same "
        f"{n} questions is biased upward even when every setting is truly "
        "identical - the selection is made on the noise and then reported as "
        "though the setting had been chosen in advance. The split-half "
        "confirmation is where that bias is measured on your own rows rather "
        "than asserted."
    )

    if separated_n == 0:
        says = (
            f"NO EVIDENCE that any of these {len(labels)} chunking settings "
            f"differs from any other on this eval set. Recall over the {n} "
            f"questions every setting scored ran from {bottom} of {n} to {top} "
            f"of {n}; {len(pairs)} pairwise McNemar exact test(s) were run over "
            f"the questions that changed verdict, corrected together by "
            f"Holm-Bonferroni at alpha={alpha}, and not one of them separated. "
            f"The most any pair disagreed on was {most_changed} question(s), and "
            f"at this family size the tightest threshold is {tightest:.5g}, "
            f"which McNemar's exact test cannot reach at all until at least "
            f"{needed_discordant} question(s) change verdict between the two "
            f"settings being compared. {selected_on_noise}"
        )
    else:
        says = (
            f"{separated_n} of {len(pairs)} pairwise comparison(s) separated "
            f"after Holm-Bonferroni at alpha={alpha}, over the {n} questions "
            f"every setting scored. {len(unbeaten)} setting(s) were not shown to "
            f"be beaten by anything: {unbeaten}. THAT IS A SET AND NOT A WINNER "
            "- 'nothing was shown to beat it' and 'it is the best' are different "
            "claims, and the second needs comparisons this eval set did not "
            f"resolve. {selected_on_noise}"
        )

    return {
        "ok": True,
        "questions": n,
        "settings_n": len(labels),
        "alpha": alpha,
        "per_setting": per_setting,
        "comparisons": pairs,
        "family_size": len(pairs),
        "separated_n": separated_n,
        "tightest_threshold": tightest,
        "min_changed_questions_at_this_family_size": needed_discordant,
        "most_changed_by_any_pair": most_changed,
        "beaten_by": beaten_by,
        "not_beaten_by_anything": unbeaten,
        "highest_recall_here": highest,
        "verdict": "no_evidence" if separated_n == 0 else "some_settings_separated",
        "crowned": None,
        "why_nothing_is_crowned": selected_on_noise,
        # THE SENTENCE USED TO CARRY A NUMBER NOBODY COMPUTED, and it survived
        # into a real reply. It read "{len(pairs)} tests at {alpha} apiece would
        # give roughly a one-in-three chance of at least one false separation at
        # eight settings" - an f-string interpolating the real family size into
        # a clause whose "one-in-three" and "eight settings" were typed. On the
        # twelve-setting sweep that renders as "66 tests ... at eight settings",
        # which contradicts itself in one line, and the probability was wrong
        # for every family size the tool allows:
        #
        #   8 settings = 28 tests: 1-(1-.05)^28 = 76.2% if independent, and
        #     measured 42.0% over 400 seeded null families of 90 questions
        #     (the simulation is `test_pure_noise_between_eight_settings_...`).
        #   12 settings = 66 tests: 96.6% if independent, measured 57.8%.
        #
        # Neither is one in three, and the two figures differ because these
        # tests are NOT independent - every one of them is over the same
        # questions - and McNemar's exact test is discrete and conservative on
        # top of that. So no probability is quoted at all now. What replaces it
        # is the pair of thresholds this function has actually computed, which
        # is the mechanism the sentence was reaching for: uncorrected, every
        # test keeps `alpha`; corrected, the tightest one has to clear
        # `alpha / len(pairs)`. Both are in this payload beside it.
        "correction": (
            f"Holm-Bonferroni, step-down, over all {len(pairs)} pairwise "
            f"comparison(s) in this sweep, holding the family-wise error rate at "
            f"{alpha}. Uncorrected, every one of those {len(pairs)} tests would "
            f"keep {alpha} of its own; corrected, the tightest threshold any of "
            f"them has to clear is {tightest:.5g}. Letting a family this size "
            f"keep {alpha} apiece is the same defect as reporting forty "
            "unresolvable deltas and letting somebody believe the tenth."
        ),
        "measured_on": (
            "the questions EVERY setting scored, which is the only set on which "
            "a difference between them means anything"
        ),
        "says": says,
        "summary": says,
    }


def _pair_sentence(pair: dict[str, Any], n: int) -> str:
    """One comparison, in the vocabulary `evals.compare` uses for two runs."""
    if pair["changed"] == 0:
        # NOT "these two cut the corpus differently and retrieved identically",
        # which is what this said until the structural null was run. Two
        # settings whose windows are both larger than every paragraph in the
        # corpus produce THE SAME PASSAGES, and a sentence asserting the cuts
        # differed would have been a claim about the corpus that this function
        # has no way to check - an invented fact in ordinary English, which is
        # the shape `tests/test_a_fabrication_in_ordinary_english_is_still_a_
        # fabrication.py` exists for. What is known here is what changed: nothing.
        return (
            f"Not one of the {n} questions changed its verdict between "
            f"{pair['a']!r} and {pair['b']!r}. There is no evidence of any "
            "difference between these two chunkings on this eval set, and none "
            "to report as a small win."
        )
    if pair["separated"]:
        return (
            f"{pair['better']!r} is ahead by {abs(pair['delta']):.1%} on {n} "
            f"paired questions: {pair['changed']} changed verdict "
            f"({pair['a_better_on']} to {pair['a']!r}, "
            f"{pair['b_better_on']} to {pair['b']!r}), McNemar exact "
            f"p={pair['p']:.3g}, Holm-adjusted {pair['adjusted_p']:.3g}, inside "
            f"this family's threshold of {pair['holm_threshold']:.3g}."
        )
    return (
        f"NO EVIDENCE between {pair['a']!r} and {pair['b']!r}. They differ by "
        f"{pair['delta']:+.1%} on {n} paired questions, but only "
        f"{pair['changed']} changed verdict ({pair['a_better_on']} to "
        f"{pair['a']!r}, {pair['b_better_on']} to {pair['b']!r}), McNemar exact "
        f"p={pair['p']:.3g} against this family's threshold of "
        f"{pair['holm_threshold']:.3g}. At least "
        f"{pair['min_changed_questions_to_separate']} question(s) would have to "
        "change verdict between these two before the test could separate them "
        "at all."
    )


def split_halves(count: int) -> tuple[list[int], list[int]]:
    """Alternating positions: the even ones choose, the odd ones confirm.

    ALTERNATING RATHER THAN A SEED, and rather than the first half. There is no
    random number generator anywhere in this module and there is not going to be
    one: a split that depends on a seed is a split whose result a caller can
    re-roll, and a split that takes the first half of a file sorted by topic
    gives one half every question about chapter one. Alternating is reproducible
    by eye, needs nothing remembered, and interleaves whatever order the file
    was in.
    """
    total = max(0, int(count))
    return (
        [position for position in range(total) if position % 2 == 0],
        [position for position in range(total) if position % 2 == 1],
    )


def confirm_on_held_out(
    vectors: list[tuple[str, list[bool]]], *, alpha: float = SWEEP_ALPHA
) -> dict[str, Any]:
    """Choose on half the questions, then look the choice up on the other half.

    THE ONLY PART OF THIS SWEEP THAT TOUCHES THE UPWARD BIAS OF A MAXIMUM.
    Holm answers a different question - it stops the sweep claiming a difference
    that is not there - and it does nothing at all about the fact that the
    highest of N recalls measured on N settings is optimistic. Nothing computed
    on the questions that made the choice can answer that, because the choice
    used them.

    So the questions are split alternately, the highest recall on the SELECT
    half is looked up on the CONFIRM half, and both numbers are returned. The
    confirm number is unbiased for the setting that was chosen, because those
    questions played no part in choosing it. The gap between them is ONE DRAW of
    the selection bias and not the quantity itself - a distinction this function
    used to skip, and skipping it made the reply false whenever the draw came
    out negative. See the comment above `says` below.

    Three honest limits, all reported rather than left to be discovered. The
    confirm half is half the size, so its own resolution is worse - that is what
    `resolution_for` on it is for. A tie on the select half is a real outcome: it
    is reported as a tie with every tied setting confirmed, rather than broken by
    an order nobody chose. And the split assumes the two halves are
    interchangeable, which a hit vector cannot show; `assumes` says so, because
    an eval file that alternates easy and hard questions breaks it completely and
    the numbers still come out looking like a measurement.
    """
    if len(vectors) < MIN_SETTINGS:
        return {
            "ok": False,
            "why": "a confirmation needs at least two settings to choose between",
        }
    n = len(vectors[0][1])
    select, confirm = split_halves(n)
    if not select or not confirm:
        return {
            "ok": False,
            "why": (
                f"{n} question(s) cannot be split into a half that chooses and a "
                "half that confirms, so there is no way to measure how much of "
                "the best setting's lead is selection. The whole-sweep numbers "
                "above are all there is, and the highest of them is a maximum."
            ),
            "questions": n,
        }

    select_hits = {
        label: sum(1 for position in select if vector[position])
        for label, vector in vectors
    }
    confirm_hits = {
        label: sum(1 for position in confirm if vector[position])
        for label, vector in vectors
    }
    top = max(select_hits.values())
    chosen = [label for label, _ in vectors if select_hits[label] == top]

    rows = []
    for label in chosen:
        picked = select_hits[label] / len(select)
        held = confirm_hits[label] / len(confirm)
        rows.append(
            {
                "setting": label,
                "chosen_on_hits": select_hits[label],
                "chosen_on_of": len(select),
                "chosen_on_recall": picked,
                "confirmed_hits": confirm_hits[label],
                "confirmed_of": len(confirm),
                "confirmed_recall": held,
                "shrinkage": picked - held,
                "resolution": evals.resolution_for(
                    confirm_hits[label], len(confirm)
                ),
            }
        )

    curve = [
        {
            "setting": label,
            "chosen_on_hits": select_hits[label],
            "chosen_on_of": len(select),
            "confirmed_hits": confirm_hits[label],
            "confirmed_of": len(confirm),
        }
        for label, _ in vectors
    ]

    tied = len(chosen) > 1
    lead = ", ".join(
        f"{row['setting']!r} {row['chosen_on_hits']}/{row['chosen_on_of']} when it "
        f"was chosen and {row['confirmed_hits']}/{row['confirmed_of']} on the "
        f"questions that did not choose it"
        for row in rows
    )

    # -- WHICH WAY THE GAP ACTUALLY WENT, before a word is written about it ----
    # THE SENTENCE HERE USED TO BE UNCONDITIONAL AND IT WAS FALSE WHENEVER THE
    # GAP CAME OUT NEGATIVE. It asserted that the difference "is the part of the
    # lead that was selection rather than retrieval" and that "the gap here is
    # larger than the bias in the whole-sweep maximum above". The upward bias of
    # a maximum is NON-NEGATIVE by construction, so a negative gap cannot be a
    # quantity of it and is not larger than one. Counted on the plain iid null
    # this module already simulates - eight identical settings, ninety
    # questions - the gap came out negative in 362 of 4000 trials, so this was
    # not a corner case: roughly one reply in eleven carried a number whose
    # stated meaning was wrong. A displayed number described as something it is
    # not is this repository's own defect class, and it does not stop being one
    # because the number sits in an explanatory paragraph rather than a verdict.
    gaps = [row["shrinkage"] for row in rows]
    if all(gap > 0 for gap in gaps):
        direction = "fell"
    elif all(gap < 0 for gap in gaps):
        direction = "rose"
    elif all(gap == 0 for gap in gaps):
        direction = "unchanged"
    else:
        direction = "mixed"
    spread = ", ".join(
        f"{row['setting']!r} {row['shrinkage'] * 100:+.1f} points" for row in rows
    )

    if direction == "fell":
        about_the_gap = (
            "The chosen setting(s) scored LOWER on the questions that played no "
            f"part in choosing than on the ones that did: {spread}. A choice made "
            "on noise looks better on the rows that made it, and this gap is "
            "CONSISTENT WITH that reading rather than proof of it - the "
            "alternative is the paragraph directly below, and on these numbers "
            "alone the two cannot be told apart. IT IS NOT "
            "A CORRECTION TO SUBTRACT: this choice was made on half your "
            f"questions ({len(select)} of {n}), and a choice made on half the "
            "data is noisier than the same choice made on all of it, so a gap "
            "measured this way runs larger IN EXPECTATION than the bias in the "
            "whole-sweep maximum above. This is one draw of it and a single draw "
            "is noisy in both directions. What it is for is the direction and "
            "the order of magnitude - it is the reason the sweep's own maximum "
            "is not a number to report, not a number to report in its place."
        )
    elif direction == "rose":
        about_the_gap = (
            "The chosen setting(s) scored HIGHER on the questions that played no "
            f"part in choosing than on the ones that did: {spread}. THAT IS NOT A "
            "MEASUREMENT OF SELECTION AND MUST NOT BE READ AS ONE, in either "
            "direction: the upward bias of a maximum is non-negative by "
            "construction, so a negative gap is not a smaller amount of it and "
            "not evidence there was none. Two things produce it. The gap is one "
            "draw of a noisy quantity, and under a true null - every setting "
            "genuinely identical - it comes out negative often. Or the two "
            "halves are not interchangeable, which is what an eval file with a "
            "period-two structure, one easy and one hard question per document, "
            "does to a split by alternating position. Neither makes the sweep's "
            "own maximum safe to report: the reason for that is the selection, "
            "and it is unchanged."
        )
    elif direction == "unchanged":
        about_the_gap = (
            "The chosen setting(s) scored EXACTLY THE SAME on the questions that "
            "played no part in choosing as on the ones that did, so this split "
            "measured no gap at all. That is one draw of a noisy quantity and not "
            "a finding that the selection cost nothing; it is what a sweep looks "
            "like when the settings are at a ceiling or a floor on both halves, "
            "which the two recalls above will show. The reason the sweep's own "
            "maximum is not a number to report is the selection, and it is "
            "unchanged."
        )
    else:
        about_the_gap = (
            "The settings that tied for the choice went DIFFERENT WAYS between "
            f"the two halves: {spread}. A gap that changes sign across settings "
            "chosen on the same rows is noise in the split rather than a "
            "quantity of selection, which is non-negative by construction, so no "
            "single number here is that quantity. The reason the sweep's own "
            "maximum is not a number to report is the selection, and it is "
            "unchanged."
        )

    assumption = (
        " WHAT THE SPLIT ASSUMES, since it is not checkable from here: that the "
        "two halves are interchangeable. It splits by alternating POSITION AMONG "
        "THE ROWS THIS COMPARISON KEPT - not by line in your file, because rows "
        "some setting could not score and rows a score tie decided are already "
        "out - so a file whose questions alternate easy and hard hands the two "
        "halves different questions, and then every number in this block is "
        "about that structure and not about chunking."
    )

    says = (
        (
            f"{len(chosen)} settings tied for the highest recall on the "
            f"{len(select)} questions used to choose, so the selection did not "
            "pick one. "
            if tied
            else ""
        )
        + f"Chosen on {len(select)} question(s), confirmed on the {len(confirm)} "
        f"question(s) that played no part in choosing: {lead}. "
        + about_the_gap
        + assumption
    )
    return {
        "ok": True,
        "chosen_on_questions": len(select),
        "confirmed_on_questions": len(confirm),
        "split_by": (
            "alternating position among the rows this comparison kept, in file "
            "order - even positions choose, odd positions confirm. Those are the "
            "rows every setting scored minus the rows a score tie decided, so a "
            "position here is not a line number in the eval file. No seed, "
            "nothing random, reproducible by eye."
        ),
        "assumes": (
            "that the two halves are interchangeable. An eval file that "
            "alternates easy and hard questions is not, and this function cannot "
            "see that from a hit vector."
        ),
        # THE SIGN, AS DATA AND NOT ONLY AS PROSE, so a caller does not have to
        # parse English to find out whether the gap it is about to display is a
        # quantity of selection at all.
        "gap_direction": direction,
        "gap_is_a_read_on_selection": direction == "fell",
        "rows": rows,
        "tie_on_the_choosing_half": tied,
        "chosen": chosen,
        "confirm_curve": curve,
        "says": says,
    }

# ---------------------------------------------------------------------------
# What the sweep is about to do, counted before it does any of it.


def _setting_label(base: str, chars: int, overlap: int) -> str:
    """The index name one setting gets. Deterministic, so a re-run is free.

    The parameters are IN THE NAME rather than beside it, which is what makes
    `build`'s own reuse check do the sweep's caching for nothing: an index of
    this name over this corpus cut this way is returned without re-reading a
    byte, so running the same sweep twice rebuilds nothing and the cost plan can
    say so honestly.
    """
    return f"{base}#chunk-{chars}-{overlap}"


def _whole(value: Any) -> int | None:
    """A caller's setting as a whole number, or None if it is not one.

    `int()` here is deliberate and it is the one place in this module that does
    it. `compare_chunkings` declares `measures=()` - checked at registration -
    so there is no stamp for `evidence`'s remembered conversion to block, and a
    passage length has to be a whole number of characters before it can be a
    row in `retrieval_indexes` at all.
    """
    number = _as_number(value, None)
    if not isinstance(number, (int, float)) or isinstance(number, bool):
        return None
    if number != int(number):
        return None
    return int(number)


def normalise_settings(
    settings: Any, default_overlap: Any = DEFAULT_PASSAGE_OVERLAP
) -> dict[str, Any]:
    """`[(passage_chars, passage_overlap), ...]`, or the refusal that says why not.

    NOTHING IS CLAMPED AND NOTHING IS DROPPED. `build` clamps a single index's
    parameters into range because one index is one index; a sweep's settings ARE
    the experiment, and quietly moving one of them changes what was compared,
    while quietly dropping one changes the size of the family every p-value in
    the reply was corrected against. Both are silent from outside. So an
    out-of-range setting is a refusal that names it.
    """
    if settings is None or (isinstance(settings, (list, tuple)) and not settings):
        return {
            "error": "no_settings",
            "detail": (
                "This call named no chunk settings to compare, and there is no "
                "default. WHICH SETTINGS TO TRY IS THE FAMILY SIZE, and the "
                "family size decides what this sweep can resolve - every "
                "p-value in the reply is corrected against it - so it cannot be "
                "a hidden default. Pass settings as a list, for example "
                "[{\"passage_chars\": 600}, {\"passage_chars\": 1200}, "
                "{\"passage_chars\": 2400}]: three windows a factor of two "
                "apart, which is the smallest sweep that can show a direction. "
                "That is a suggested starting shape and not a measurement of "
                "anything about your corpus."
            ),
        }
    if not isinstance(settings, (list, tuple)):
        return {
            "error": "settings_not_a_list",
            "detail": (
                f"settings is a {type(settings).__name__}. It has to be a list "
                "of chunk settings - each one either a number of characters or "
                "an object with passage_chars and optionally passage_overlap."
            ),
        }
    fallback = _whole(default_overlap)
    if fallback is None or fallback < 0:
        fallback = DEFAULT_PASSAGE_OVERLAP

    out: list[tuple[int, int]] = []
    for position, entry in enumerate(settings):
        if isinstance(entry, dict):
            chars = _whole(entry.get("passage_chars"))
            overlap = (
                fallback
                if entry.get("passage_overlap") is None
                else _whole(entry.get("passage_overlap"))
            )
        else:
            chars = _whole(entry)
            overlap = fallback
        if chars is None or overlap is None:
            return {
                "error": "setting_is_not_a_whole_number",
                "detail": (
                    f"Setting {position} is {entry!r}. A passage length and an "
                    "overlap are whole numbers of characters."
                ),
            }
        if chars < 1 or chars > MAX_DOCUMENT_CHARS:
            return {
                "error": "setting_out_of_range",
                "detail": (
                    f"Setting {position} asks for passage_chars={chars}, and this "
                    f"bench indexes between 1 and {MAX_DOCUMENT_CHARS} characters "
                    "per passage. Nothing was clamped: a sweep's settings are the "
                    "experiment, and moving one of them quietly would change what "
                    "was compared."
                ),
            }
        if overlap < 0 or overlap >= chars:
            return {
                "error": "overlap_past_the_window",
                "detail": (
                    f"Setting {position} asks for passage_overlap={overlap} inside "
                    f"passage_chars={chars}, so each passage would repeat all of "
                    "the one before it and the cut would barely advance. "
                    + (
                        f"Note that this setting did not name an overlap: "
                        f"{fallback} is the default and it is too large for a "
                        f"window of {chars}. Name passage_overlap on this setting."
                        if (not isinstance(entry, dict))
                        or entry.get("passage_overlap") is None
                        else "Set it below passage_chars."
                    )
                ),
            }
        out.append((chars, overlap))

    if len(out) < MIN_SETTINGS:
        return {
            "error": "not_enough_settings",
            "detail": (
                f"{len(out)} setting is not a comparison. A sweep needs at least "
                f"{MIN_SETTINGS} chunk settings to compare - and two is exactly "
                "the case evals.compare was built for."
            ),
        }
    if len(out) > MAX_SETTINGS:
        family = len(out) * (len(out) - 1) // 2
        return {
            "error": "too_many_settings",
            "detail": (
                f"{len(out)} settings is {family} pairwise comparisons, and this "
                f"sweep runs at most {MAX_SETTINGS}. The bound is about what a "
                "sweep can RESOLVE and not about how long it takes: cost is "
                "linear in settings - one whole rebuild each - and the family is "
                f"quadratic, so at {len(out)} settings Holm's tightest threshold "
                f"is {SWEEP_ALPHA / family:.2g} and no pair could be separated "
                f"until {min_discordant_for(SWEEP_ALPHA / family)} questions "
                "changed verdict between them. Past that a sweep is buying "
                "comparisons its own arithmetic says it cannot separate. "
                f"THE NUMBER {MAX_SETTINGS} IS A JUDGEMENT AND NOT A DERIVATION: "
                "the floor climbs in steps, and it needs "
                f"{min_discordant_for(SWEEP_ALPHA / (MAX_SETTINGS * (MAX_SETTINGS - 1) // 2))} "
                f"changed questions at {MAX_SETTINGS} settings and the same "
                f"number at {MAX_SETTINGS + 2}, so the arithmetic does not pick "
                "this line out of the plateau it sits on. What it does say is "
                "that the floor is already there and never comes back down."
            ),
        }
    duplicates = sorted({pair for pair in out if out.count(pair) > 1})
    if duplicates:
        return {
            "error": "duplicate_settings",
            "detail": (
                f"These settings appear more than once: {duplicates}. The same "
                "chunking twice is one index compared with itself - a comparison "
                "whose answer is known before it runs - and it inflates the "
                "family size that every other p-value in the sweep is corrected "
                "against."
            ),
        }
    return {"settings": out}


def _sweep_cost(
    *, rebuilds: int, passages: int, posting_rows: int, retrievals: int
) -> dict[str, Any]:
    """The four cost dimensions, through `app/build.py`'s doors and no other.

    `Estimate` is used rather than a dict of numbers for one property: an
    UNKNOWN estimate CANNOT carry a value, checked in its constructor, so a
    duration nobody has measured is not a thing this function is able to
    produce. `docs/THE_PROPOSAL_LOOP.md` names the sentence it exists to stop -
    *"about forty minutes and roughly fourteen cents"* - and a sweep that
    rebuilds an index eight times is exactly where somebody would write it.

    The counts that ARE known live beside this block rather than inside it, as
    counts, because they are what `kept_passages` actually counted.
    """
    spec = REGISTRY.get("compare_chunkings")
    reads = list(spec.reads) if spec is not None else ["filesystem", "datasets", "retrieval"]
    because = (
        f"compare_chunkings declares reads={reads}, which does not include "
        "`providers`, so nothing it does can reach your model. Every retrieval "
        "in this sweep is BM25 arithmetic over a token count on this machine."
    )
    return build_costs.Cost(
        model_tokens=build_costs.Estimate.none(build_costs.MODEL_TOKENS, because=because),
        model_requests=build_costs.Estimate.none(
            build_costs.MODEL_REQUESTS, because=because
        ),
        wall_clock=build_costs.Estimate.unknown(
            build_costs.WALL_CLOCK,
            why=(
                "nothing in this harness has recorded how long a rebuild of this "
                "corpus takes on this machine, so there is no measurement to "
                "derive one from and any duration here would be invented. What "
                f"is known is the work: {rebuilds} rebuild(s), {passages} "
                f"passage(s), {posting_rows} posting row(s) and {retrievals} "
                "retrieval(s), all counted rather than guessed"
            ),
            find_out_by=(
                "run this sweep with a single setting - the reply says what that "
                "one setting writes - time it, and the rest is arithmetic over "
                "the per-setting counts already in this plan"
            ),
        ),
        disk=build_costs.Estimate.unknown(
            build_costs.DISK,
            why=(
                f"this writes {passages} passage row(s) and {posting_rows} "
                "posting row(s) into this project's own database, and nothing "
                "has measured how many bytes a row of either costs"
            ),
            find_out_by=(
                "compare the size of the harness database before and after one "
                "setting of this sweep"
            ),
        ),
    ).as_dict()


def _identical_cuts(planned: list[dict[str, Any]]) -> dict[str, Any]:
    """Which of these settings are the same experiment wearing different numbers.

    A DIFFERENCE THAT IS NOT ONE COSTS TWICE. It costs a rebuild - a whole index
    written for a cut already in the database - and it costs power, because every
    pair it adds enters the Holm family and tightens the threshold that every
    REAL comparison in the sweep is judged against. Eight settings that collapse
    to two cuts run twenty-eight tests of which twenty-seven have a known answer,
    and Holm's tightest threshold is 0.05/28 rather than 0.05/1.

    The family is REPORTED and not silently recomputed. The number of settings is
    the family size every p-value is corrected against, `compare_chunkings`
    refuses to choose it for the caller, and quietly correcting over a smaller
    family than the one that ran would be choosing it for them after the fact.
    What this returns is the arithmetic, so the reply can state both numbers.
    """
    groups: dict[str, list[str]] = {}
    for row in planned:
        label = f"{row['passage_chars']}/{row['passage_overlap']}"
        groups.setdefault(str(row["cut_fingerprint"]), []).append(label)
    collapsed = [members for members in groups.values() if len(members) > 1]
    distinct = len(groups)
    family = len(planned) * (len(planned) - 1) // 2
    over_distinct = distinct * (distinct - 1) // 2
    if not collapsed:
        return {
            "distinct_cuts": distinct,
            "identical_groups": [],
            "family_over_distinct_cuts": over_distinct,
            "says": "",
        }
    return {
        "distinct_cuts": distinct,
        "identical_groups": collapsed,
        "family_over_distinct_cuts": over_distinct,
        "says": (
            f"THESE {len(planned)} SETTINGS ARE {distinct} DISTINCT "
            + ("CUT" if distinct == 1 else "CUTS")
            + f" OF THIS CORPUS, NOT {len(planned)}: "
            + "; ".join(
                f"{members} produce passage-for-passage identical indexes"
                for members in collapsed
            )
            + ". A window wider than every paragraph it would have to split is "
            "inert, so those settings are one experiment under several names. "
            "Nothing is wrong with your corpus and nothing was clamped - but of "
            f"the {family} pairwise comparison(s) this sweep runs, "
            f"{over_distinct} compare genuinely different cuts and "
            f"{family - over_distinct} have their answer before they run. Holm "
            f"corrects against the {family} that ran rather than the "
            f"{over_distinct} that carry any information, which costs real "
            "power. A verdict of NO EVIDENCE across settings that are the same "
            "index is a fact about these windows on this corpus and NOT a "
            "finding about chunking. Pass windows small enough to split a "
            "paragraph if you want the lever to move at all."
        ),
    }


def _plan_chunkings(
    *,
    corpus_path: str,
    eval_path: str,
    question_field: str,
    thread_id: int | None,
    settings: Any,
    ground_truth_field: str | None = None,
    text_field: str | None = None,
    id_field: str | None = None,
    name: str | None = None,
    passage_overlap: Any = DEFAULT_PASSAGE_OVERLAP,
    k: int = DEFAULT_K,
    max_questions: int = MAX_QUESTIONS,
    rebuild: bool = False,
) -> dict[str, Any]:
    """What this sweep would do, in counts, having written nothing.

    EVERY REFUSAL THAT CAN BE REACHED WITHOUT BUILDING IS REACHED HERE. A sweep
    with no ground-truth column, an eval set past the row cap, a setting that
    would truncate the index, a name already taken by somebody else's index -
    each of those is a refusal that used to cost eight rebuilds to discover, and
    each of them is now free. That is not only a kindness: `docs/PRODUCT_SPEC.md`
    and this module both treat a truncated index as unscoreable, so a plan that
    can see the truncation coming and builds anyway would be spending a person's
    corpus to produce a number it already knows it must refuse.

    The passage and posting counts are exact, not approximate, because
    `kept_passages` is the same function `build` writes from.
    """
    if thread_id is None:
        return {
            "ok": False,
            "error": "no_thread",
            **_thread_help(
                "compare_chunkings",
                "A sweep builds several indexes and every one of them belongs to "
                "one conversation, alongside the eval set they are all scored "
                "against. This call did not say which.",
            ),
            "levers": levers_block(),
        }
    if not evidence.names_a_conversation(thread_id):
        return {
            "ok": False,
            "error": "no_such_thread",
            "detail": (
                f"There is no conversation {thread_id!r} on this machine, so "
                "there is nowhere to file an index. Nothing was read and nothing "
                "was written."
            ),
            "levers": levers_block(),
        }

    chosen_settings = normalise_settings(settings, passage_overlap)
    if "error" in chosen_settings:
        return {
            "ok": False,
            "error": chosen_settings["error"],
            "summary": "Nothing was built and nothing was measured. "
            + chosen_settings["detail"],
            "detail": chosen_settings["detail"],
            "levers": levers_block(),
        }
    pairs: list[tuple[int, int]] = chosen_settings["settings"]

    root = Path(str(corpus_path))
    if not root.exists():
        return {
            "ok": False,
            "error": "no_such_path",
            "summary": (
                f"There is nothing at {corpus_path}, so there is no corpus to cut "
                "several ways. Nothing was built."
            ),
            "levers": levers_block(),
        }
    structured = _structured(str(root))
    if structured and not text_field:
        columns = _columns_of(str(root))
        return {
            "ok": False,
            "error": "no_text_field",
            "summary": (
                f"{corpus_path} is a {structured} file, so one row is one "
                "document, and nothing here knows which column holds the text. "
                f"Call this again with text_field. The columns are: "
                f"{columns or 'none that could be read'}. Nothing was built."
            ),
            "columns": columns,
            "levers": levers_block(),
        }

    depth = _clamped(k, DEFAULT_K, 1, MAX_K)
    cap = _clamped(max_questions, MAX_QUESTIONS, 1, MAX_QUESTIONS)

    # -- the corpus, read once and cut once per setting ----------------------
    documents: list[dict[str, Any]] = []
    skipped = 0
    try:
        for document in _read_documents(str(root), text_field, id_field):
            if "text" in document:
                documents.append(document)
            else:
                skipped += 1
    except (OSError, UnicodeDecodeError) as error:
        return {
            "ok": False,
            "error": "corpus_unreadable",
            "summary": (
                f"{corpus_path} could not be read: {type(error).__name__}: "
                f"{error}. Nothing was built."
            ),
            "levers": levers_block(),
        }
    if not documents:
        return {
            "ok": False,
            "error": "no_documents",
            "summary": (
                f"Nothing under {corpus_path} could be read as a document, so "
                f"there is nothing to cut. {skipped} candidate(s) were looked at "
                "and every one was skipped. Nothing was built."
            ),
            "levers": levers_block(),
        }
    fingerprint = _fingerprint((d["doc_key"], d["text"]) for d in documents)
    base = str(name).strip() if name and str(name).strip() else root.name or str(root)

    # -- the eval set, checked before a single passage is written ------------
    if not Path(str(eval_path)).exists():
        return {
            "ok": False,
            "error": "no_such_eval_set",
            "summary": (
                f"There is nothing at {eval_path}, so there are no questions to "
                "score any of these settings on. Nothing was built."
            ),
            "levers": levers_block(),
        }
    rows, columns, seen = _read_eval_rows(str(eval_path), cap)
    if not seen:
        return {
            "ok": False,
            "error": "no_rows",
            "summary": f"No row could be read from {eval_path}. Nothing was built.",
            "levers": levers_block(),
        }
    if str(question_field) not in columns:
        return {
            "ok": False,
            "error": "no_such_question_column",
            "summary": (
                f"No row in {eval_path} has a {question_field!r} column. The "
                f"columns present are {columns}. Nothing was built."
            ),
            "columns": columns,
            "levers": levers_block(),
        }
    if seen > cap:
        return {
            "ok": False,
            "error": "hit_row_cap",
            "summary": (
                f"{eval_path} holds {seen} rows and this run would read {cap}, so "
                "every setting would be scored on a PREFIX of the file rather "
                "than the file - which on a file sorted by topic is not a sample, "
                "and would be the same prefix for all of them without being the "
                "eval set for any of them. Nothing was built. Raise "
                "max_questions, or point this at a file holding the rows you mean."
            ),
            "rows_seen": seen,
            "levers": levers_block(),
        }
    column = _ground_truth_column(columns, ground_truth_field)
    if "error" in column:
        if column["error"] == "no_ground_truth":
            # THE EXAMPLE IS A REAL DOCUMENT FROM THIS CORPUS, which is why the
            # corpus is read before the eval set is checked even though the eval
            # set is the cheaper thing to look at. `score_recall` can name a real
            # passage key because it has an index to look in; a plan has no index
            # and would otherwise have to print a made-up file name in the one
            # sentence whose whole job is to say exactly what to add.
            sentence = NO_GROUND_TRUTH.format(
                path=eval_path,
                columns=columns,
                example_doc=documents[0]["doc_key"],
                example_passage=f"{documents[0]['doc_key']}#0",
            )
        else:
            sentence = "Nothing was measured. " + column["detail"]
        return {
            "ok": False,
            "error": column["error"],
            "summary": "Nothing was built. " + sentence,
            "detail": sentence,
            "columns": columns,
            "candidates": column.get("candidates"),
            "levers": levers_block(),
        }
    truth_field = column["column"]

    eligible = 0
    unlabelled_by_reason: Counter[str] = Counter()
    for row in rows:
        has_question = (
            row.get(str(question_field)) is not None
            and str(row.get(str(question_field))).strip()
        )
        has_truth = row.get(truth_field) is not None and str(row.get(truth_field)).strip()
        if has_question and has_truth:
            eligible += 1
        elif has_question:
            unlabelled_by_reason[f"a question with nothing in {truth_field!r}"] += 1
        elif has_truth:
            unlabelled_by_reason[f"a ground truth with nothing in {question_field!r}"] += 1
        else:
            unlabelled_by_reason[f"neither a {question_field!r} nor a {truth_field!r}"] += 1
    if not eligible:
        return {
            "ok": False,
            "error": "no_scorable_rows",
            "summary": (
                f"Not one row in {eval_path} has a value in both "
                f"{question_field!r} and {truth_field!r}, so there is no question "
                "with a right answer attached and nothing for any setting to be "
                "scored on. Nothing was built."
            ),
            "levers": levers_block(),
        }

    planned: list[dict[str, Any]] = []
    for chars, overlap in pairs:
        passages = 0
        posting_rows = 0
        terms = 0
        short = 0
        empty = 0
        # THE CUT ITSELF, HASHED, not only how many pieces it made. Two settings
        # can be different numbers and still be the same experiment: a window
        # wider than every paragraph in the corpus is inert, so 2000, 4000 and
        # 9000 over one-paragraph documents produce three BIT-IDENTICAL indexes.
        # `normalise_settings` already refuses a setting repeated verbatim, on
        # the grounds that "one index compared with itself" is a comparison whose
        # answer is known before it runs and that it inflates the family every
        # other p-value is corrected against - and that argument is about the
        # RESULTING CUT rather than about the typed number, so it applied here
        # too and was not being made. It is not a refusal: a caller cannot know
        # their corpus is flat at these windows, and "these eight windows all cut
        # your corpus the same way" is the most useful sentence this tool can say
        # about such a corpus. It is a FACT, reported, so that "no evidence that
        # these settings differ" is not read as a finding about chunking when
        # chunking never varied. `kept_passages` is already called here, so it
        # costs one hash.
        cut = hashlib.sha256()
        for document in documents:
            kept, dropped_short, dropped_empty = kept_passages(
                document["text"], chars, overlap
            )
            short += dropped_short
            empty += dropped_empty
            cut.update(document["doc_key"].encode("utf-8", "replace"))
            for piece, words in kept:
                passages += 1
                terms += len(words)
                posting_rows += len(set(words))
                cut.update(b"\x00")
                cut.update(piece.encode("utf-8", "replace"))
        label = _setting_label(base, chars, overlap)
        existing = _named(int(thread_id), label)
        reusable = existing is not None and (
            str(existing["corpus_fingerprint"]) == fingerprint
            and int(existing["passage_chars"]) == chars
            and int(existing["passage_overlap"]) == overlap
            and str(existing["source_path"]) == str(root)
        )
        planned.append(
            {
                "passage_chars": chars,
                "passage_overlap": overlap,
                "index_name": label,
                "cut_fingerprint": cut.hexdigest(),
                "passages": passages,
                "posting_rows": posting_rows,
                "terms": terms,
                "short_fragments_dropped": short,
                "passages_with_no_indexable_term": empty,
                "would_truncate": passages > MAX_PASSAGES,
                "already_built": bool(reusable),
                "existing_index_id": int(existing["id"]) if existing is not None else None,
                "name_taken_by_another_corpus": bool(
                    existing is not None and not reusable
                ),
            }
        )

    truncating = [row for row in planned if row["would_truncate"]]
    if truncating:
        worst = truncating[0]
        return {
            "ok": False,
            "error": "would_truncate",
            "summary": (
                f"{len(truncating)} of these {len(planned)} settings would cut "
                f"this corpus into more than {MAX_PASSAGES} passages - "
                f"passage_chars={worst['passage_chars']} makes "
                f"{worst['passages']} - and an index that stops at the cap is not "
                "the corpus, so a recall measured against it is not a recall over "
                "the corpus. Comparing a truncated index with a whole one would "
                "be comparing two different corpora. Nothing was built. Use "
                "larger passage_chars, or a smaller corpus."
            ),
            "settings": planned,
            "levers": levers_block(),
        }
    collisions = [row for row in planned if row["name_taken_by_another_corpus"]]
    if collisions and not rebuild:
        return {
            "ok": False,
            "error": "name_taken",
            "summary": (
                f"{len(collisions)} of the index name(s) this sweep would use are "
                f"already taken in this conversation by something that is not this "
                f"corpus cut this way - the first is "
                f"{collisions[0]['index_name']!r}. Rebuilding over them would "
                "throw away an index you did not ask to lose, and searching them "
                "would return passages from documents you did not point at. "
                "Nothing was built. Pass rebuild=true to replace them, or give "
                "this sweep a different name."
            ),
            "settings": planned,
            "levers": levers_block(),
        }

    rebuilds = [row for row in planned if not row["already_built"]]
    reused = [row for row in planned if row["already_built"]]
    passages_total = sum(row["passages"] for row in rebuilds)
    postings_total = sum(row["posting_rows"] for row in rebuilds)
    retrievals = len(planned) * eligible
    family = len(planned) * (len(planned) - 1) // 2
    tightest = SWEEP_ALPHA / family if family else SWEEP_ALPHA
    cuts = _identical_cuts(planned)

    will_do = {
        "settings": len(planned),
        "distinct_cuts": cuts["distinct_cuts"],
        "rebuilds": len(rebuilds),
        "reused_without_rebuilding": len(reused),
        "documents_each_time": len(documents),
        "documents_skipped": skipped,
        "passages_written": passages_total,
        "posting_rows_written": postings_total,
        "retrievals": retrievals,
        "questions_each_setting_is_scored_on": eligible,
        "pairwise_comparisons": family,
        "pairwise_comparisons_over_distinct_cuts": cuts["family_over_distinct_cuts"],
        "counted_by": (
            "app/tools/retrieval.py's own kept_passages(), which is the same "
            "function build() writes from - so these are the rows that will "
            "actually be inserted and not an estimate of them. A posting row is "
            "one distinct term in one passage, which is exactly what build "
            "inserts. No duration is stated anywhere here because nothing has "
            "measured one on this machine."
        ),
    }
    return {
        "ok": True,
        "ran": False,
        "corpus_path": str(root),
        "eval_path": str(eval_path),
        "index_name_base": base,
        "corpus_fingerprint": fingerprint,
        "settings": planned,
        "cuts": cuts,
        "will_do": will_do,
        "cost": _sweep_cost(
            rebuilds=len(rebuilds),
            passages=passages_total,
            posting_rows=postings_total,
            retrievals=retrievals,
        ),
        "questions": {
            "eval_path": str(eval_path),
            "question_field": str(question_field),
            "ground_truth_field": truth_field,
            "ground_truth_chosen_how": column["how"],
            "rows_seen": seen,
            "rows_read": len(rows),
            "eligible": eligible,
            "unlabelled": sum(unlabelled_by_reason.values()),
            "unlabelled_by_reason": dict(unlabelled_by_reason),
            "k": depth,
        },
        "statistics": {
            "alpha": SWEEP_ALPHA,
            "family_size": family,
            "correction": "Holm-Bonferroni over every pairwise comparison in the sweep",
            "tightest_threshold": tightest,
            "min_changed_questions_to_separate_any_pair": min_discordant_for(tightest),
            "says": (
                f"{len(planned)} settings is {family} pairwise comparison(s). "
                f"Holm's tightest threshold at that family size is "
                f"{tightest:.5g}, and McNemar's exact test cannot produce a "
                f"p below 2**(1-m) with m questions changed - so no two of these "
                f"settings can be separated at all unless at least "
                f"{min_discordant_for(tightest)} of the {eligible} question(s) "
                "change their verdict between them. That is arithmetic about "
                "this sweep's shape, known before it runs."
            ),
        },
        "levers": levers_block(),
        "stamps_nothing": STAMPS_NOTHING,
        "summary": _plan_sentence(
            planned, will_do, eligible, depth, family, tightest, cuts
        ),
    }


def plan_chunkings(**arguments: Any) -> dict[str, Any]:
    """`_plan_chunkings`, with the levers line put on every refusal it returns.

    ONE CHOKE POINT RATHER THAN TWELVE REMEMBERINGS. `_plan_chunkings` has a
    dozen early returns - no ground truth, a duplicate setting, a name already
    taken, a row cap - and each one is a sentence somebody reads INSTEAD of a
    comparison. The brief's rule is that the three levers this harness cannot
    pull are named in the output every time, and "every time" includes the times
    the sweep did not happen. Appending it at each return site is a list to keep
    in sync; appending it here is a property.

    The check for the line already being present keeps the wrapper idempotent,
    so a refusal that grew its own copy does not get two.
    """
    report = _plan_chunkings(**arguments)
    if report.get("ok"):
        return report
    line = levers_block()["in_one_line"]
    for key in ("summary", "detail"):
        text = str(report.get(key) or "").strip()
        if text and line not in text:
            report[key] = f"{text} {line}"
    if not report.get("summary"):
        report["summary"] = report.get("detail", line)
    report.setdefault("levers", levers_block())
    report.setdefault("stamps_nothing", STAMPS_NOTHING)
    report.setdefault("measured", [])
    report.setdefault("not_measured", report["summary"])
    return report


def _plan_sentence(
    planned: list[dict[str, Any]],
    will_do: dict[str, Any],
    eligible: int,
    depth: int,
    family: int,
    tightest: float,
    cuts: dict[str, Any] | None = None,
) -> str:
    """What is about to happen, in counts, with no duration in it."""
    per = "; ".join(
        f"{row['passage_chars']}/{row['passage_overlap']} -> {row['passages']} "
        f"passages, {row['posting_rows']} posting rows"
        + (" (already built, will be reused)" if row["already_built"] else "")
        for row in planned
    )
    # THE COLLAPSE IS SAID IN THE PLAN, WHICH IS THE ONLY PLACE IT IS FREE TO
    # ACT ON. A person reading this before spending eight rebuilds on two
    # distinct cuts can change the windows; a person reading it afterwards has
    # already paid for six indexes that were copies.
    collapse = f"{cuts['says']} " if cuts and cuts.get("says") else ""
    return collapse + (
        f"THIS HAS NOT RUN. It would build {will_do['rebuilds']} index(es) over "
        f"{will_do['documents_each_time']} document(s) - "
        f"{will_do['reused_without_rebuilding']} of the {will_do['settings']} "
        f"settings are already built over exactly this corpus cut that way and "
        f"would be reused - writing {will_do['passages_written']} passage(s) and "
        f"{will_do['posting_rows_written']} posting row(s) into this project's "
        f"database, and would then run {will_do['retrievals']} BM25 retrieval(s): "
        f"{eligible} question(s) at k={depth}, once per setting. Per setting: "
        f"{per}. No duration is stated because nothing here has measured one on "
        f"this machine; the cost block says how to find out. The comparison would "
        f"be {family} pairwise test(s) corrected together, and at that family size "
        f"no two settings can be separated unless at least "
        f"{min_discordant_for(tightest)} question(s) change verdict between them. "
        "Call this again with run=true to do it. "
        # THE THREE LEVERS TRAVEL IN THE SENTENCE AND NOT ONLY IN THE STRUCTURED
        # BLOCK. A plan is the reply somebody reads BEFORE deciding whether this
        # is worth doing, which makes it the most important place to say that
        # chunking is one quarter of what the engine asked for - a person who
        # only reads the summary must not come away thinking a chunk sweep is
        # the whole of "fix your retriever".
        + levers_block()["in_one_line"]
    )


def levers_block() -> dict[str, Any]:
    """The one lever this bench owns and the three it does not. In every reply.

    NOT AN APPENDIX. `NO_TRAIN__FIX_RETRIEVAL` names four things - chunking,
    hybrid BM25 + dense, a cross-encoder reranker, query rewriting - and this
    harness can do exactly one of them. Shipping the one and staying quiet about
    the other three would read as though chunking were the whole answer, and the
    person would go away thinking they had done the work the engine asked for.
    Three of the four are refusals of HONESTY rather than of effort, and each one
    says who can pull it and what it would cost in provenance.
    """
    return {
        "we_can_vary": LEVER_WE_OWN,
        "we_cannot_pull": [dict(row) for row in LEVERS_WE_DO_NOT_OWN],
        "says": (
            "The diagnosis engine's NO_TRAIN__FIX_RETRIEVAL names four levers and "
            "this harness owns one of them. WE CAN VARY: " + LEVER_WE_OWN + " WE "
            "CANNOT PULL, and these are refusals of honesty rather than of "
            "effort: "
            + " ".join(
                f"{row['lever'].upper()} - {row['why_not']} Who can: {row['who_can']}"
                for row in LEVERS_WE_DO_NOT_OWN
            )
            + " A sweep of chunk sizes is one quarter of what the engine asked "
            "for, and if it comes back saying nothing separates, that is a real "
            "answer about chunking and says nothing at all about the other three."
        ),
        # THE SAME CLAIM, SHORT ENOUGH TO TRAVEL IN EVERY SUMMARY. `says` above
        # is the full account and it belongs in the structured reply; a summary
        # that carried all of it would be mostly this paragraph, and a sentence
        # nobody finishes reading is a sentence that did not name anything. The
        # three levers are named in both, which is the part that may not be
        # dropped.
        "in_one_line": (
            # TENSE-NEUTRAL, because this sentence travels on a plan that has
            # not run and on a refusal where nothing was varied at all. "This
            # varied the one lever..." was true of exactly one of the three
            # replies it appears in, which makes it a small false statement in
            # ordinary English on the other two.
            "CHUNKING IS ONE OF THE FOUR LEVERS NO_TRAIN__FIX_RETRIEVAL NAMES "
            "and it is the only one this harness owns. The other three - hybrid "
            "BM25 + "
            "dense retrieval, a cross-encoder reranker, query rewriting - are "
            "not refusals of effort. Each needs a model this harness does not "
            "ship, and pulling any of them would make the resulting number a "
            "fact about your endpoint as much as about your index. The levers "
            "block says who can pull each one and what it would cost in "
            "provenance. This is one quarter of what the engine asked for, and "
            "a sweep that separates nothing is a real answer about chunking and "
            "no answer at all about the other three."
        ),
    }


#: Why a sweep may not stamp the fact this bench owns. In every reply, including
#: every refusal, because the question "so what do I write down" is the one a
#: person asks next and the answer has two halves that are easy to conflate.
#:
#: THE SECOND HALF USED TO BE FALSE AND IT WAS FALSE ON ORDINARY RUNS. It said
#: that re-running `measure_retriever_recall` on the setting you pick and this
#: same file "returns a bit-for-bit identical number with a stamp on it". Driven
#: end to end on a corpus of ninety documents where twenty-one questions were
#: decided by a score tie: the sweep reported the leading setting at 25 of 69 and
#: `measure_retriever_recall` on that very index and that very file returned 30
#: of 90. Two different denominators, because a sweep drops every row some
#: setting could not score and every row a tie decided ANYWHERE in the family,
#: while a single run keeps its own. On five of those eight settings
#: `own_run.stampable_on_its_own` was False, so the promised stamp would not have
#: arrived at all. The tool computed that falsifier - it is in `per_setting` -
#: and printed the promise beside it. That is this file's own defect class, in
#: the one paragraph whose whole subject is provenance, so the sentence now says
#: what is actually true and `re_measuring` below carries the counts.
STAMPS_NOTHING = (
    "Nothing was recorded and nothing here can record anything: compare_chunkings "
    "declares measures=(), checked at registration, so the instrument it is handed "
    "cannot stamp a fact. retriever_recall_at_k is source: inspect and "
    "measure_retriever_recall is its only instrument. THE REASON IS NOT "
    "BOOKKEEPING: the highest recall in a sweep is a maximum selected on the same "
    "questions it would be reported against, and stamping it would put the one "
    "number in this bench that opens a gate under exactly that bias. GOING AND "
    "TAKING THE STAMP YOURSELF IS THE RIGHT NEXT MOVE, AND IT IS NEITHER A COPY "
    "OF THE NUMBER HERE NOR A CURE FOR HOW IT WAS CHOSEN. Scoring is "
    "deterministic, so nothing about re-running changes what the retriever does - "
    "but measure_retriever_recall scores ONE index over the rows THAT index can "
    "score, and this comparison is made over the rows EVERY setting scored minus "
    "every row a score tie decided under any of them. Those are different "
    "denominators whenever a sweep dropped anything, and then the figure it hands "
    "back is a different number from the one in the curve. It also goes through "
    "the seven refusals it owns, and any of them returns a number with no stamp, "
    "or no number: a setting whose own run has an unresolved ground truth, a tie, "
    "or a truncated index is not stampable, and this reply says which of these "
    "settings are. What re-measuring buys is PROVENANCE, which is real and is the "
    "right thing to do before anybody quotes a figure. What it buys about "
    "SELECTION is nothing - re-scoring the setting a maximum picked, on the "
    "questions that picked it, cannot un-pick it. The number in this reply that "
    "was not selected on its own questions is the confirmed recall in the "
    "confirmation block."
)

def _re_measuring(payload: dict[str, Any]) -> dict[str, Any]:
    """What `measure_retriever_recall` would actually do with each setting here.

    `STAMPS_NOTHING` above is the invariant and it travels on plans and refusals
    too, so it can only speak in general terms. THIS IS THE SAME PARAGRAPH IN
    COUNTS, and it exists because the general sentence was wrong for two years'
    worth of ordinary runs before anybody drove it: the person is told to go and
    take the stamp themselves, and what they get back is a different denominator
    from the curve they were reading, or a refusal. Both of those are already
    computed - `dropped_*` for the denominator and `own_run.stampable_on_its_own`
    per setting - so the reply can say it rather than let it be discovered.

    Nothing here is a recommendation of a setting. The rows are in the order the
    caller gave, not sorted by recall, for the same reason the curve is.
    """
    dropped = int(payload["dropped_not_scored_by_every_setting"]) + int(
        payload["dropped_decided_by_a_tie"]
    )
    rows = [
        {
            "setting": row["setting"],
            "index_id": row["index_id"],
            "index_name": row["index_name"],
            "in_this_comparison": f"{row['hits']}/{row['of']}",
            "on_its_own_rows": f"{row['own_run']['hits']}/{row['own_run']['of']}",
            "same_denominator": int(row["own_run"]["of"]) == int(row["of"]),
            "would_stamp": bool(row["own_run"]["stampable_on_its_own"]),
        }
        for row in payload["per_setting"]
    ]
    stampable = [row for row in rows if row["would_stamp"]]
    same = [row for row in rows if row["same_denominator"]]
    named = ", ".join(
        f"{row['setting']} -> index_id {row['index_id']} ({row['index_name']!r}), "
        f"{row['in_this_comparison']} here and {row['on_its_own_rows']} on its own "
        f"rows, " + ("stampable" if row["would_stamp"] else "NOT stampable")
        for row in rows
    )
    return {
        "rows_this_comparison_used": int(payload["compared_questions"]),
        "rows_dropped_before_comparing": dropped,
        "settings_whose_own_run_uses_the_same_rows": len(same),
        "settings_whose_own_run_would_stamp": len(stampable),
        "how_to_name_a_setting": (
            "measure_retriever_recall takes index_id. Without one it scores the "
            "newest index in this conversation, which after a sweep is whichever "
            "setting happened to be LAST in the list you passed - an order, not a "
            "choice. Name the id."
        ),
        "says": (
            f"IF YOU GO AND TAKE THE STAMP: this comparison is over "
            f"{payload['compared_questions']} question(s); {dropped} row(s) were "
            "dropped from it and measure_retriever_recall does not drop them, so "
            f"{len(rows) - len(same)} of these {len(rows)} setting(s) would be "
            "scored on a different denominator and hand back a different figure "
            f"from the curve above. {len(stampable)} of {len(rows)} would stamp "
            "at all; the rest hit one of the seven refusals measure_retriever_"
            f"recall owns and return no fact. Setting by setting: {named}."
        ),
    }


# ---------------------------------------------------------------------------
# Running it.


def _sweep_refusal(
    *, error: str, sentence: str, plan: dict[str, Any], **extra: Any
) -> dict[str, Any]:
    """A sweep that stopped, in the same shape as one that finished.

    `_refusal` above is the same idea for a single recall run and the reason is
    the same: a caller that has to special-case a refusal is a caller that can
    forget to. Every key a finished sweep returns is here, holding the honest
    null, and what WAS built is named rather than hidden - an index this call
    wrote is in the conversation whether or not the comparison reached the end,
    and a reply that did not mention it would be a reply about a database that
    is not the one on disk.
    """
    payload: dict[str, Any] = {
        "ok": True,
        "ran": True,
        "error": error,
        "corpus_path": plan.get("corpus_path"),
        "eval_path": plan.get("eval_path"),
        "settings": plan.get("settings", []),
        "cuts": plan.get("cuts", {}),
        "will_do": plan.get("will_do", {}),
        "cost": plan.get("cost"),
        "questions": plan.get("questions", {}),
        "indexes": [],
        "compared_questions": 0,
        "per_setting": [],
        "comparisons": [],
        "family_size": 0,
        "separated_n": 0,
        "not_beaten_by_anything": [],
        "highest_recall_here": [],
        "crowned": None,
        "verdict": "nothing_was_compared",
        "confirmation": {"ok": False, "why": "the sweep did not reach a comparison"},
        "measured": [],
        "not_measured": sentence,
        "levers": levers_block(),
        "stamps_nothing": STAMPS_NOTHING,
        "decides_nothing": (
            "Nothing was compared, so nothing was concluded and no gate moved. "
            "retriever_recall_at_k is whatever it already was."
        ),
        "summary": sentence + " " + levers_block()["in_one_line"],
        "says": sentence + " " + levers_block()["in_one_line"],
    }
    payload.update(extra)
    return payload


def sweep_chunkings(
    *,
    corpus_path: str,
    eval_path: str,
    question_field: str,
    thread_id: int | None,
    settings: Any = None,
    ground_truth_field: str | None = None,
    text_field: str | None = None,
    id_field: str | None = None,
    name: str | None = None,
    passage_overlap: Any = DEFAULT_PASSAGE_OVERLAP,
    k: int = DEFAULT_K,
    max_questions: int = MAX_QUESTIONS,
    run: bool = False,
    rebuild: bool = False,
) -> dict[str, Any]:
    """Several chunkings, one eval set, and what can honestly be concluded.

    Stamps nothing and CANNOT stamp anything - see `STAMPS_NOTHING`. Separated
    from the tool handler for the reason `build` and `score_recall` are: the
    function holds the work, the tool holds the instrument, and a sibling bench
    that wants the comparison does not have to go near the fact ledger to get it.

    ## WHAT THIS SWEEP REFUSES THAT A TWO-RUN COMPARISON NEVER HAS TO

    **Passage-level ground truth.** `alpha.md#3` is the fourth passage of
    `alpha.md` AT ONE CHUNKING. Change `passage_chars` and it is a different
    piece of text, or it does not exist. So a ground-truth column naming
    passages is not comparable across settings even when every row resolves: the
    question being asked of each setting would be a different question. Document
    level is invariant under the cut and is the only level this sweep will
    compare. This refusal exists ONLY in a sweep - `measure_retriever_recall`
    scores one index and is right to accept a passage key - and it was found by
    asking what a passage key names.

    **Rows a score tie decided.** `_tie_decided` already blocks a single run's
    stamp when whether the right passage fell inside the top k was the
    tie-break's answer rather than the retriever's. In a sweep such a row is
    worse than useless: it could hand the comparison to the alphabetical order
    of two file names. Every row tie-decided under ANY setting is dropped from
    the comparison, counted, and named - and it is dropped for all settings at
    once, because dropping it from one side only would unpair the rows.

    **Rows one setting could score and another could not.** The comparison is
    over the questions EVERY setting scored, which is `evals.compare`'s "the
    rows both runs graded" with N sides instead of two. Each setting's own
    recall over its own rows is reported too, demoted and labelled, for the same
    reason `compare` keeps `aggregate`: it is a real fact about one setting and
    it is not the number a comparison is made of.
    """
    plan = plan_chunkings(
        corpus_path=corpus_path,
        eval_path=eval_path,
        question_field=question_field,
        thread_id=thread_id,
        settings=settings,
        ground_truth_field=ground_truth_field,
        text_field=text_field,
        id_field=id_field,
        name=name,
        passage_overlap=passage_overlap,
        k=k,
        max_questions=max_questions,
        rebuild=rebuild,
    )
    if not plan.get("ok") or not run:
        if plan.get("ok"):
            plan["ran"] = False
            plan["measured"] = []
            plan["not_measured"] = (
                "Nothing was measured: this call has not run. The counts above "
                "are what it would do."
            )
        return plan

    depth = int(plan["questions"]["k"])
    truth_field = plan["questions"]["ground_truth_field"]
    cap = _clamped(max_questions, MAX_QUESTIONS, 1, MAX_QUESTIONS)

    indexes: list[dict[str, Any]] = []
    scorings: list[dict[str, Any]] = []
    for setting in plan["settings"]:
        report = build(
            path=plan["corpus_path"],
            thread_id=thread_id,
            name=setting["index_name"],
            text_field=text_field,
            id_field=id_field,
            passage_chars=setting["passage_chars"],
            passage_overlap=setting["passage_overlap"],
            rebuild=bool(rebuild),
        )
        if not report.get("ok"):
            return _sweep_refusal(
                error=str(report.get("error") or "index_failed"),
                sentence=(
                    f"The setting passage_chars={setting['passage_chars']}, "
                    f"passage_overlap={setting['passage_overlap']} could not be "
                    f"indexed, so the sweep stopped rather than compare the "
                    f"settings that happened to work: a family that lost a member "
                    f"is a different family and every p-value in it would have "
                    f"been corrected against the wrong size. "
                    + str(report.get("summary") or report.get("detail") or "")
                    + f" {len(indexes)} index(es) had already been built and are "
                    "in this conversation."
                ),
                plan=plan,
                indexes=indexes,
            )
        indexes.append(
            {
                "passage_chars": setting["passage_chars"],
                "passage_overlap": setting["passage_overlap"],
                "index_id": int(report["index_id"]),
                "index_name": report["name"],
                "passages": int(report["passages"]),
                "documents": int(report["documents"]),
                "total_tokens": int(report["total_tokens"]),
                "reused": bool(report.get("reused")),
                "truncated": bool(report.get("truncated")),
                "cut_by": report["cut_by"],
            }
        )
        scored = score_recall(
            eval_path=plan["eval_path"],
            question_field=str(question_field),
            thread_id=thread_id,
            index_id=int(report["index_id"]),
            ground_truth_field=truth_field,
            k=depth,
            max_questions=cap,
            full_rows=True,
        )
        if not scored.get("ok") or scored.get("error"):
            return _sweep_refusal(
                error=str(scored.get("error") or "scoring_failed"),
                sentence=(
                    f"The setting passage_chars={setting['passage_chars']}, "
                    f"passage_overlap={setting['passage_overlap']} could not be "
                    "scored, so there is no comparison. "
                    + str(scored.get("summary") or scored.get("detail") or "")
                ),
                plan=plan,
                indexes=indexes,
            )
        if scored["ground_truth_level"] != DOCUMENT_LEVEL:
            return _sweep_refusal(
                error="ground_truth_is_not_invariant_under_the_cut",
                sentence=(
                    "Nothing was compared. The ground truth in "
                    f"{truth_field!r} resolves at the "
                    f"{scored['ground_truth_level']} level, and A PASSAGE KEY "
                    "NAMES A CUT. This sweep varies the cut: "
                    f"{plan['settings'][0]['index_name']}'s passage 3 and "
                    f"{plan['settings'][-1]['index_name']}'s passage 3 are "
                    "different pieces of text, and at some settings a given "
                    "passage key does not exist at all - so each setting would "
                    "be asked a different question and the answers would not be "
                    "comparable however good the arithmetic on top of them was. "
                    "Name the DOCUMENT that answers each question instead - the "
                    "path relative to the corpus root - which is the same "
                    "document however the corpus is chopped. "
                    f"{len(indexes)} index(es) were built and are in this "
                    "conversation; you can search them and you can score any one "
                    "of them on its own with measure_retriever_recall, where a "
                    "passage key is a perfectly good ground truth."
                ),
                plan=plan,
                indexes=indexes,
                ground_truth_level=scored["ground_truth_level"],
            )
        scorings.append(scored)

    # -- the rows every setting scored, minus the rows a tie decided ---------
    row_sets = [{int(row["row"]) for row in scored["all_rows"]} for scored in scorings]
    common = set(row_sets[0]).intersection(*row_sets[1:]) if row_sets else set()
    tied_rows: set[int] = set()
    for scored in scorings:
        for row in scored["all_rows"]:
            if depth in (row.get("tie_decided_at_k") or []):
                tied_rows.add(int(row["row"]))
    compared = sorted(common - tied_rows)
    dropped_unscored = sorted(set().union(*row_sets) - common) if row_sets else []
    dropped_tied = sorted(common & tied_rows)

    if not compared:
        return _sweep_refusal(
            error="no_comparable_questions",
            sentence=(
                "Nothing was compared. Of the "
                f"{plan['questions']['eligible']} labelled question(s), none "
                "survived to be scored by every setting with the answer decided "
                f"by the retriever: {len(dropped_unscored)} question(s) were not "
                f"scored under every setting and {len(dropped_tied)} question(s) "
                "had the answer decided by a score tie rather than by the "
                "retriever under at least one of them. A "
                "comparison over the questions that happened to work for each "
                "side separately is not a comparison. "
                f"{len(indexes)} index(es) were built and are in this "
                "conversation."
            ),
            plan=plan,
            indexes=indexes,
            dropped_not_scored_by_every_setting=len(dropped_unscored),
            dropped_decided_by_a_tie=len(dropped_tied),
        )

    vectors: list[tuple[str, list[bool]]] = []
    for setting, scored in zip(plan["settings"], scorings):
        by_row = {int(row["row"]): row for row in scored["all_rows"]}
        vectors.append(
            (
                f"{setting['passage_chars']}/{setting['passage_overlap']}",
                [by_row[row]["found_at_rank"] is not None for row in compared],
            )
        )
    verdict = compare_hit_vectors(vectors, alpha=SWEEP_ALPHA)
    if not verdict.get("ok"):
        return _sweep_refusal(  # pragma: no cover - the guards above make this dead
            error=str(verdict.get("error")),
            sentence="Nothing was compared. " + str(verdict.get("detail")),
            plan=plan,
            indexes=indexes,
        )
    confirmation = confirm_on_held_out(vectors, alpha=SWEEP_ALPHA)

    for row, setting, scored, index in zip(
        verdict["per_setting"], plan["settings"], scorings, indexes
    ):
        row["passage_chars"] = setting["passage_chars"]
        row["passage_overlap"] = setting["passage_overlap"]
        row["index_id"] = index["index_id"]
        row["index_name"] = index["index_name"]
        row["passages"] = index["passages"]
        # DEMOTED, NOT DELETED, exactly as `evals.compare` demotes `aggregate`.
        # A setting's recall over every row IT could score is a real fact about
        # that setting; it is not a number any comparison here is made of,
        # because the settings did not all score the same rows.
        row["own_run"] = {
            "hits": scored["hits"],
            "of": scored["questions_scored"],
            "recall": scored["recall_at_k"],
            "recall_curve": scored["recall_curve"],
            "unresolved_n": scored["unresolved_n"],
            "tie_decided_n": scored["tie_decided_n"],
            "stampable_on_its_own": bool(scored["stampable"]),
            "says": (
                f"Over every row this setting could score on its own - "
                f"{scored['questions_scored']} of them - it retrieved the right "
                f"document for {scored['hits']}. That is a different denominator "
                f"from the {verdict['questions']} question(s) the comparison is "
                "made on and it is not the number any comparison here used."
            ),
        }

    payload: dict[str, Any] = {
        "ok": True,
        "ran": True,
        "corpus_path": plan["corpus_path"],
        "eval_path": plan["eval_path"],
        "settings": plan["settings"],
        "cuts": plan.get("cuts", {}),
        "will_do": plan["will_do"],
        "cost": plan["cost"],
        "questions": plan["questions"],
        "indexes": indexes,
        "compared_questions": verdict["questions"],
        "dropped_not_scored_by_every_setting": len(dropped_unscored),
        "dropped_decided_by_a_tie": len(dropped_tied),
        "dropped_rows": {
            "not_scored_by_every_setting": dropped_unscored[:20],
            "decided_by_a_tie": dropped_tied[:20],
            "why": (
                "A question only some settings could score, or one whose answer "
                "was decided by two passages tying on score rather than by the "
                "retriever, carries no information about the cut - and leaving "
                "either in would let the tie-break or the join decide which "
                "chunking wins. Dropped for every setting at once, because "
                "dropping it from one side only would unpair the rows."
            ),
        },
        "per_setting": verdict["per_setting"],
        "comparisons": verdict["comparisons"],
        "family_size": verdict["family_size"],
        "separated_n": verdict["separated_n"],
        "alpha": verdict["alpha"],
        "correction": verdict["correction"],
        "tightest_threshold": verdict["tightest_threshold"],
        "min_changed_questions_at_this_family_size": verdict[
            "min_changed_questions_at_this_family_size"
        ],
        "most_changed_by_any_pair": verdict["most_changed_by_any_pair"],
        "beaten_by": verdict["beaten_by"],
        "not_beaten_by_anything": verdict["not_beaten_by_anything"],
        "highest_recall_here": verdict["highest_recall_here"],
        "crowned": None,
        "why_nothing_is_crowned": verdict["why_nothing_is_crowned"],
        "verdict": verdict["verdict"],
        "confirmation": confirmation,
        "measured_on": verdict["measured_on"],
        "measured": [],
        "not_measured": STAMPS_NOTHING,
        "stamps_nothing": STAMPS_NOTHING,
        "levers": levers_block(),
        "scorer": (
            "BM25, k1={k1}, b={b}, on this machine. Every setting was scored on "
            "the same eval set with the same ground truth column at the same k. "
            "No model was asked anything and nothing left this machine."
        ).format(k1=BM25_K1, b=BM25_B),
        "decides_nothing": (
            "This is a comparison of chunkings and nothing else. It does not set "
            "retrieval_tried - which is yours to say - it records no fact, and it "
            "opens no gate."
        ),
    }
    payload["re_measuring"] = _re_measuring(payload)
    payload["says"] = _sweep_sentence(payload, verdict, confirmation)
    payload["summary"] = payload["says"]
    return payload


def _sweep_sentence(
    payload: dict[str, Any],
    verdict: dict[str, Any],
    confirmation: dict[str, Any],
) -> str:
    """The whole verdict, in the order a person needs it.

    What was varied, what it was measured on, the CURVE - every setting, never
    only the best - then what can and cannot be concluded, then the selection
    bias measured on the caller's own rows, then what was recorded (nothing) and
    what it would take to record anything, then the three levers this bench
    cannot pull. The curve comes before the verdict on purpose: a reader who
    stops after one sentence should have seen all of the numbers rather than the
    largest of them.
    """
    curve = ", ".join(
        f"{row['setting']} {row['hits']}/{row['of']}"
        for row in payload["per_setting"]
    )
    line = (
        f"Varied ONE lever - chunking - across "
        f"{payload['will_do']['settings']} setting(s) over "
        f"{payload['will_do']['documents_each_time']} document(s) from "
        f"{payload['corpus_path']}, scored on the SAME "
        f"{payload['compared_questions']} question(s) from "
        f"{payload['eval_path']} with the same ground truth column "
        f"({payload['questions']['ground_truth_field']!r}) at "
        f"k={payload['questions']['k']}. The whole curve, which is what there is "
        f"to report: {curve}."
    )
    # BEFORE THE VERDICT, because it changes what the verdict is about. "NO
    # EVIDENCE that any of these settings differs" over settings that produced
    # one index is a true sentence a person reads as a fact about chunking, and
    # the fact is that chunking never varied.
    if payload.get("cuts", {}).get("says"):
        line += " " + payload["cuts"]["says"]
    if payload["dropped_not_scored_by_every_setting"] or payload[
        "dropped_decided_by_a_tie"
    ]:
        line += (
            f" {payload['dropped_not_scored_by_every_setting']} question(s) were "
            "not scored by every setting and "
            f"{payload['dropped_decided_by_a_tie']} were decided by a score tie "
            "rather than by the retriever under at least one setting; all of them "
            "are out of every number above, for every setting at once."
        )
    if payload["questions"]["unlabelled"]:
        line += (
            f" {payload['questions']['unlabelled']} of the "
            f"{payload['questions']['rows_read']} row(s) in the eval set carry no "
            "ground truth or no question and could not be scored by anything, so "
            "the denominator above is the labelled rows and not your eval set."
        )
    line += " " + verdict["says"]
    line += " " + str(confirmation.get("says") or confirmation.get("why") or "")
    line += " " + STAMPS_NOTHING
    # THE COUNTS THAT MAKE THE PARAGRAPH ABOVE CHECKABLE, in the summary and not
    # only in the structured block. `STAMPS_NOTHING` tells a person to go and
    # take the stamp themselves; what they get back has a different denominator
    # whenever this sweep dropped a row, and may be a refusal. A reader who stops
    # at the summary must not be one of the people who finds that out afterwards.
    if payload.get("re_measuring"):
        line += " " + payload["re_measuring"]["says"]
    line += " " + levers_block()["in_one_line"]
    return line


# ---------------------------------------------------------------------------
# The four tools.


@tool(
    "build_retrieval_index",
    description=(
        "Index a folder of documents, or one file, on this machine so the "
        "retriever can be searched and scored. Cuts each document into passages "
        "on paragraph boundaries and builds a BM25 index over them. It ships no "
        "model, makes no network call and adds no dependency: the index is a "
        "table in this project's own database. It reports what it actually did "
        "- how many documents, how many passages, exactly how it cut them, and "
        "every file it skipped with the reason. A structured file (CSV, JSONL) "
        "is one document per row and needs text_field naming the column to "
        "index. It measures no fact and decides nothing."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "The folder or file to index, on this machine. A folder is "
                    "walked for readable text files."
                ),
            },
            "name": {
                "type": "string",
                "description": (
                    "What to call this index in this conversation. Default: the "
                    "folder or file name."
                ),
            },
            "text_field": {
                "type": "string",
                "description": (
                    "For a CSV or JSONL corpus, the column holding the text to "
                    "index. Required for those, because one row is one document "
                    "and nothing on disk says which column is the document."
                ),
            },
            "id_field": {
                "type": "string",
                "description": (
                    "For a CSV or JSONL corpus, the column holding each row's "
                    "identifier - the name an eval set's ground-truth column "
                    "would use. Default: filename#rownumber."
                ),
            },
            "passage_chars": {
                "type": "integer",
                "description": (
                    f"How long a passage may be, in characters. Default "
                    f"{DEFAULT_PASSAGE_CHARS}. This is a stated choice, not a "
                    "measured optimum; it is recorded on the index and reported "
                    "with every number that comes off it."
                ),
            },
            "passage_overlap": {
                "type": "integer",
                "description": (
                    f"How much of the previous passage the next one repeats when "
                    f"a paragraph has to be split. Default "
                    f"{DEFAULT_PASSAGE_OVERLAP}."
                ),
            },
            "rebuild": {
                "type": "boolean",
                "description": (
                    "Replace an index of this name in this conversation instead "
                    "of refusing. Without it, an existing name over a different "
                    "corpus is a refusal rather than a silent overwrite."
                ),
            },
        },
        "required": ["path"],
    },
    reads=("filesystem", "datasets"),
    writes=("retrieval",),
    provides=("retrieval.index.build",),
    label="Build a retrieval index",
    group="Data",
    verb="index a corpus of documents on this machine",
    order=27,
)
def build_retrieval_index(
    path: str,
    name: str | None = None,
    text_field: str | None = None,
    id_field: str | None = None,
    passage_chars: int = DEFAULT_PASSAGE_CHARS,
    passage_overlap: int = DEFAULT_PASSAGE_OVERLAP,
    rebuild: bool = False,
    *,
    instrument: Instrument,
) -> dict[str, Any]:
    """Build it, and report what it did rather than that it worked.

    `measures=()` and it is structural rather than a promise: the instrument
    this handler is given can stamp nothing at all, checked at registration. An
    index is not a measurement of anything. What it enables is
    `measure_retriever_recall`, which is where the one fact in this bench is
    stamped and where every refusal that guards it lives.
    """
    return build(
        path=str(path),
        thread_id=instrument.thread_id,
        name=name,
        text_field=text_field,
        id_field=id_field,
        passage_chars=passage_chars,
        passage_overlap=passage_overlap,
        rebuild=bool(rebuild),
    )


@tool(
    "search_the_index",
    description=(
        "Retrieve the top k passages for one query from an index in this "
        "conversation, with their BM25 scores and the document each came from. "
        "This exists so a person can SEE the retriever working before anybody "
        "reports a number about it - a bad index is obvious by eye and invisible "
        "in a score. It costs nothing, asks no model anything and sends nothing "
        "anywhere. It measures no fact: one query is one query, and how often "
        "the right passage comes back is measure_retriever_recall."
    ),
    schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The question or phrase to retrieve for.",
            },
            "index_id": {
                "type": "integer",
                "description": (
                    "Which index to search. Default: the most recent one in this "
                    "conversation."
                ),
            },
            "k": {
                "type": "integer",
                "description": (
                    f"How many passages to return. Default {DEFAULT_K}, maximum "
                    f"{MAX_K}."
                ),
            },
        },
        "required": ["query"],
    },
    reads=("retrieval",),
    writes=(),
    provides=("retrieval.index.search",),
    label="Search the index",
    group="Data",
    verb="retrieve the top passages for a query",
    order=28,
)
def search_the_index(
    query: str,
    index_id: int | None = None,
    k: int = DEFAULT_K,
    *,
    instrument: Instrument,
) -> dict[str, Any]:
    """Look at what comes back. Every passage arrives quarantined as data.

    A retrieved passage is other people's text selected BY A QUERY, which makes
    it the most reachable surface in this product for a line addressed at the
    model: a document containing "ignore previous instructions" is retrieved
    precisely when somebody asks about it. `app/tools/context.quarantine` wraps
    every one, so the model receives an object labelled `data` with
    `trusted: false` rather than a string that reads like an instruction.
    """
    return search(
        query=str(query),
        thread_id=instrument.thread_id,
        index_id=index_id,
        k=k,
    )


@tool(
    "measure_retriever_recall",
    description=(
        "Score the retriever ALONE on an eval set: for each question, is the "
        "right passage in the top k. This is the instrument the diagnosis "
        "engine's ACTION__MEASURE_RETRIEVER_RECALL has been asking for, and the "
        "only tool that can record retriever_recall_at_k. It needs the eval set "
        "to say which document or passage is right, in a column - and where it "
        "does not, it REFUSES and says exactly what to add, rather than asking a "
        "model to decide which passage was correct and calling the answer a "
        "measurement. The number comes back as a count with the resolution that "
        "many questions can support, and with the recall at every depth from 1 "
        "to k, because recall rises with k. Nothing is recorded from a partial "
        "run, a run that hit the row cap, a truncated index, a run whose ground "
        "truth names something the index does not contain, a file with rows "
        "that carry no ground truth or no question, or a run where a score tie "
        "rather than the retriever decided whether the right passage was in the "
        "top k."
    ),
    schema={
        "type": "object",
        "properties": {
            "eval_path": {
                "type": "string",
                "description": "The evaluation file on this machine.",
            },
            "question_field": {
                "type": "string",
                "description": "The column holding the question to retrieve for.",
            },
            "ground_truth_field": {
                "type": "string",
                "description": (
                    "The column naming the document or passage that answers each "
                    "question. Leave it out only if the file uses a conventional "
                    "name - and the reply says which column it used."
                ),
            },
            "answer_field": {
                "type": "string",
                "description": (
                    "The column holding the expected ANSWER TEXT. Supplying it "
                    "adds answer_in_passage_rate, a WEAKER and DIFFERENT "
                    "measurement - how often the answer's text appears somewhere "
                    "in the retrieved passages. It is never recorded as "
                    "retriever_recall_at_k."
                ),
            },
            "index_id": {
                "type": "integer",
                "description": (
                    "Which index to score. Default: the most recent one in this "
                    "conversation."
                ),
            },
            "k": {
                "type": "integer",
                "description": (
                    f"How deep the retriever may look. Default {DEFAULT_K}, "
                    f"maximum {MAX_K}. Recall rises with k, so the k used is "
                    "named in the record and the whole curve is reported."
                ),
            },
            "max_questions": {
                "type": "integer",
                "description": (
                    f"Stop after this many rows. Default and maximum "
                    f"{MAX_QUESTIONS}. A run that hits it records NOTHING: it "
                    "scored a prefix of the file, which on a sorted file is not "
                    "a sample."
                ),
            },
        },
        "required": ["eval_path", "question_field"],
    },
    reads=("filesystem", "datasets", "retrieval"),
    writes=("facts",),
    measures=("retriever_recall_at_k",),
    # WALL 6. What this stamps is a fraction in [0, 1] counted off the ranked
    # lists. `k` and `max_questions` are the two arguments that could collide
    # with it, and neither could ever BE the answer: `k` is how deep the
    # retriever was allowed to look and `max_questions` is how many rows the run
    # would read. Both are integers a caller can send as `1`, and a retriever
    # that put the right passage first every time scores exactly `1.0`; without
    # this declaration that honest run is refused a stamp - the `profile_dataset`
    # false refusal in `app/tools/registry.py`'s WALL 6, arriving here.
    # `eval_path`, `question_field`, `ground_truth_field`, `answer_field` and
    # `index_id` are deliberately NOT bounded: they stay quarantined.
    bounds=("k", "max_questions"),
    provides=("retrieval.recall.score",),
    label="Measure retriever recall",
    group="Data",
    verb="score the retriever alone on the eval set",
    order=29,
)
def measure_retriever_recall(
    eval_path: str,
    question_field: str,
    ground_truth_field: str | None = None,
    answer_field: str | None = None,
    index_id: int | None = None,
    k: int = DEFAULT_K,
    max_questions: int = MAX_QUESTIONS,
    *,
    instrument: Instrument,
) -> dict[str, Any]:
    """Score it, and stamp only what a finished run over real ground truth earned.

    THE STAMP IS GUARDED BY ONE BOOLEAN COMPUTED IN ONE PLACE. `score_recall`
    sets `stampable`, and it is False for every one of the seven ways a run can
    look like a measurement without being one - listed in the module docstring.
    Putting the rule there rather than here means a sibling bench that calls the
    function directly gets the same verdict about whether the number is worth
    anything, instead of a number and a footnote it has to remember to read.

    The instrument cannot be talked out of any of it. `measures=` bounds what may
    be stamped at registration; `Instrument.measured` refuses a value this call
    was handed; and the fraction below is `hits / scored`, both of them counts
    this function made off ranked lists it produced. There is no argument on this
    tool that could become the answer, and there is no argument anywhere in this
    module that lets a model say which passage was the right one.
    """
    report = score_recall(
        eval_path=str(eval_path),
        question_field=str(question_field),
        thread_id=instrument.thread_id,
        index_id=index_id,
        ground_truth_field=ground_truth_field,
        answer_field=answer_field,
        k=k,
        max_questions=max_questions,
    )
    if not report.get("ok"):
        report["measured"] = []
        report["not_measured"] = report.get("detail") or report.get(
            "summary", "Nothing was measured."
        )
        return report
    if not report.get("stampable"):
        # Already shaped by `_refusal` when the ground truth was missing. A run
        # that scored rows and still may not stamp gets the same two keys here,
        # so every reply from this tool answers "what was recorded" the same way.
        report.setdefault("measured", [])
        report.setdefault(
            "not_measured",
            "Nothing was recorded. " + str(report.get("summary", "")),
        )
        report["not_measured"] = report["not_measured"] or report["summary"]
        return report

    scored = int(report["questions_scored"])
    hits = int(report["hits"])
    recall = hits / scored
    level = str(report["ground_truth_level"])
    what = (
        "the right passage"
        if level == PASSAGE_LEVEL
        else "a passage from the right document"
    )
    try:
        instrument.measured(
            "retriever_recall_at_k",
            recall,
            how=(
                f"{hits} of {scored} questions in {eval_path} had {what} in the "
                f"top {report['k']} of index {report['index_name']!r} "
                f"({report['index_id']}), which holds "
                f"{index_row(int(report['index_id']))['passages_n']} passages "
                f"scored by BM25 on this machine; ground truth read from the "
                f"{report['ground_truth_field']!r} column, "
                f"{report['ground_truth_chosen_how']}; 95% interval "
                f"{report['resolution']['ci_95'][0]:.0%}-"
                f"{report['resolution']['ci_95'][1]:.0%}. RECALL RISES WITH K and "
                f"this number is at k={report['k']}"
            ),
            # Wall 8: G3 reads this, and recall measured over generated
            # questions is recall against questions the sampler drew twice.
            from_file=eval_path,
        )
    except evidence.MeasurementError as error:
        # The ledger refused the row - almost always because this call names no
        # conversation, and a fact about somebody's retriever belongs to one.
        # Reported rather than raised: a tool that raised here would take the
        # whole turn down over an argument the caller cannot see.
        report["measured"] = []
        report["not_measured"] = str(error)
        return report

    report["measured"] = list(instrument.minted)
    report["not_measured"] = ""
    report["recorded"] = (
        f"retriever_recall_at_k = {recall:.4f} MEASURED, at k={report['k']}, "
        "scoped to this conversation. The k is in the record because the fact's "
        "name does not carry it and the engine's bar is a flat 0.8."
    )
    return report



@tool(
    "compare_chunkings",
    description=(
        "Rebuild the retrieval index at several chunk settings, score every one "
        "of them on the SAME eval set with the SAME ground truth, and say what "
        "can and cannot be concluded. It varies the ONE lever "
        "NO_TRAIN__FIX_RETRIEVAL names that this harness owns - passage_chars "
        "and passage_overlap - and it names the three it does not (hybrid dense "
        "retrieval, a cross-encoder reranker, query rewriting) in every reply, "
        "because a person told to fix their retriever deserves to know which "
        "quarter of the job this is. WITHOUT run=true IT BUILDS NOTHING and "
        "reports what it would do, in rebuilds, passages and posting rows, "
        "counted rather than estimated, and with no duration because nothing "
        "here has measured one. The comparison is PAIRED question by question "
        "with McNemar's exact test and every pairwise test in the sweep is "
        "corrected together by Holm-Bonferroni, because eight settings is "
        "twenty-eight tests and two in five families of eight settings that do "
        "not differ at all contain a false separation without it - 42.0% of "
        "200 seeded null families, against 3.5% with it, measured in this "
        "repository's own null simulation and not a rule of thumb. IT CROWNS "
        "NOTHING: the answer is the whole "
        "curve plus the set of settings nothing was shown to beat, or NO "
        "EVIDENCE in those words. The best recall in a sweep is a maximum "
        "selected on the same questions it is reported against, so this tool "
        "records no fact at all - measure_retriever_recall is the only "
        "instrument for retriever_recall_at_k, and this reply says what "
        "re-measuring does and does not fix."
    ),
    schema={
        "type": "object",
        "properties": {
            "corpus_path": {
                "type": "string",
                "description": (
                    "The folder or file of documents to index, on this machine. "
                    "Every setting indexes exactly this corpus."
                ),
            },
            "eval_path": {
                "type": "string",
                "description": (
                    "The evaluation file every setting is scored on. One file for "
                    "all of them: two settings scored on two eval sets are two "
                    "facts and not a comparison."
                ),
            },
            "question_field": {
                "type": "string",
                "description": "The column holding the question to retrieve for.",
            },
            "settings": {
                "type": "array",
                "description": (
                    "The chunk settings to compare. Each entry is either a number "
                    "of characters or an object with passage_chars and optionally "
                    "passage_overlap. There is NO DEFAULT: the number of settings "
                    "is the family size that every p-value in the reply is "
                    "corrected against, so it cannot be chosen behind your back. "
                    f"At least {MIN_SETTINGS}, at most {MAX_SETTINGS}, no "
                    "duplicates."
                ),
                "items": {"type": "object"},
            },
            "ground_truth_field": {
                "type": "string",
                "description": (
                    "The column naming the DOCUMENT that answers each question. "
                    "Document level and not passage level: a passage key names a "
                    "cut, this tool varies the cut, and the same key means "
                    "different text at every setting - so a passage-level column "
                    "is refused here even though measure_retriever_recall accepts "
                    "one happily for a single index."
                ),
            },
            "text_field": {
                "type": "string",
                "description": (
                    "For a CSV or JSONL corpus, the column holding the document "
                    "text. Required for those."
                ),
            },
            "id_field": {
                "type": "string",
                "description": (
                    "For a CSV or JSONL corpus, the column holding each row's "
                    "identifier - the name the ground-truth column uses."
                ),
            },
            "name": {
                "type": "string",
                "description": (
                    "What to call this family of indexes. Each one is named "
                    "<name>#chunk-<chars>-<overlap>, so running the same sweep "
                    "twice rebuilds nothing. Default: the corpus folder or file "
                    "name."
                ),
            },
            "passage_overlap": {
                "type": "integer",
                "description": (
                    "The overlap used for any setting that does not name its own. "
                    f"Default {DEFAULT_PASSAGE_OVERLAP}. Holding it fixed while "
                    "passage_chars varies is what makes the sweep about one thing."
                ),
            },
            "k": {
                "type": "integer",
                "description": (
                    f"How deep the retriever may look, the same for every "
                    f"setting. Default {DEFAULT_K}, maximum {MAX_K}."
                ),
            },
            "max_questions": {
                "type": "integer",
                "description": (
                    f"Stop after this many eval rows. Default and maximum "
                    f"{MAX_QUESTIONS}. A file with more rows than this is REFUSED "
                    "rather than sampled: every setting would be scored on the "
                    "same prefix, which is not the eval set for any of them."
                ),
            },
            "run": {
                "type": "boolean",
                "description": (
                    "Actually build and score. WITHOUT IT NOTHING IS WRITTEN and "
                    "the reply is the plan: how many rebuilds, how many passages, "
                    "how many posting rows, how many retrievals. Every setting "
                    "rebuilds the whole index, so what a sweep is about to do to "
                    "somebody's database is a thing they should be able to read "
                    "before it happens rather than after."
                ),
            },
            "rebuild": {
                "type": "boolean",
                "description": (
                    "Replace indexes of these names that hold something else. "
                    "Without it, a name already taken by a different corpus is a "
                    "refusal rather than a silent overwrite."
                ),
            },
        },
        # `settings` IS NOT REQUIRED HERE EVEN THOUGH IT IS REQUIRED IN
        # FACT. The registry refuses a call missing a required property with
        # "compare_chunkings needs settings and did not get it", which is
        # true and teaches nothing; normalise_settings refuses the same call
        # with the reason there is no default - the number of settings is
        # the family size every p-value is corrected against - and a
        # concrete shape to start from. The refusal that explains itself is
        # the one a caller should reach.
        "required": ["corpus_path", "eval_path", "question_field"],
    },
    reads=("filesystem", "datasets", "retrieval"),
    writes=("retrieval",),
    provides=("retrieval.chunking.compare",),
    label="Compare chunkings",
    group="Data",
    verb="rebuild the index at several chunk settings and compare them",
    order=30,
)
def compare_chunkings(
    corpus_path: str,
    eval_path: str,
    question_field: str,
    settings: Any = None,
    ground_truth_field: str | None = None,
    text_field: str | None = None,
    id_field: str | None = None,
    name: str | None = None,
    passage_overlap: int = DEFAULT_PASSAGE_OVERLAP,
    k: int = DEFAULT_K,
    max_questions: int = MAX_QUESTIONS,
    run: bool = False,
    rebuild: bool = False,
    *,
    instrument: Instrument,
) -> dict[str, Any]:
    """Compare chunkings, and stamp nothing - structurally, not by promise.

    `measures=()` is checked at registration, so the instrument this handler
    holds cannot record a fact even if a future edit here asked it to. That is
    the same guarantee `build_retrieval_index` has and it is load-bearing for a
    different reason: an index is not a measurement of anything, whereas a sweep
    produces a number that LOOKS exactly like the one the diagnosis engine reads.
    `retriever_recall_at_k` is `source: inspect` with a flat bar at 0.8, and the
    best of eight recalls measured on ninety questions is a maximum selected on
    those same ninety questions. Stamping it would be `evals.py`'s
    never-invent-a-number failure wearing statistical clothing, one layer deeper
    than the version that file already survives.

    The instrument is taken for `thread_id` alone, which is how every index and
    every eval score in this bench is scoped.
    """
    return sweep_chunkings(
        corpus_path=str(corpus_path),
        eval_path=str(eval_path),
        question_field=str(question_field),
        thread_id=instrument.thread_id,
        settings=settings,
        ground_truth_field=ground_truth_field,
        text_field=text_field,
        id_field=id_field,
        name=name,
        passage_overlap=passage_overlap,
        k=k,
        max_questions=max_questions,
        run=bool(run),
        rebuild=bool(rebuild),
    )

__all__ = [
    "BM25",
    "BM25_B",
    "BM25_K1",
    "build",
    "build_retrieval_index",
    "compare_chunkings",
    "compare_hit_vectors",
    "confirm_on_held_out",
    "cut_into_passages",
    "DEFAULT_K",
    "DEFAULT_PASSAGE_CHARS",
    "DEFAULT_PASSAGE_OVERLAP",
    "delete_index",
    "DOCUMENT_LEVEL",
    "documents_of",
    "ensure_tables",
    "GROUND_TRUTH_COLUMNS",
    "holm",
    "index_row",
    "indexes_in",
    "kept_passages",
    "LEVER_WE_OWN",
    "levers_block",
    "LEVERS_WE_DO_NOT_OWN",
    "MAX_K",
    "MAX_PASSAGES",
    "MAX_QUESTIONS",
    "MAX_SETTINGS",
    "measure_retriever_recall",
    "min_discordant_for",
    "MIN_PASSAGE_CHARS",
    "MIN_SETTINGS",
    "normalise_settings",
    "PASSAGE_LEVEL",
    "passages_of",
    "plan_chunkings",
    "read_index",
    "score_recall",
    "search",
    "search_the_index",
    "split_halves",
    "STAMPS_NOTHING",
    "SWEEP_ALPHA",
    "sweep_chunkings",
    "tokenise",
]
