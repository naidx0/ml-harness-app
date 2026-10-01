"""10 - an index of the user's own documents, and the postings that make it a
retriever rather than a folder.

## Why this needs tables at all

`docs/diagnosis_engine.yaml` declares `retriever_recall_at_k` as
`source: inspect`, which admits MEASURED and nothing else, and until this
migration no tool in the harness could produce one. The engine's own node says
what is missing, verbatim:

    - node: S3_RECALL_UNMEASURED
      condition: "retrieval_tried and retriever_recall_at_k is null"
      outcome: ACTION__MEASURE_RETRIEVER_RECALL
      action: "Score the retriever alone on the eval set: for each question, is
               the right passage in the top k."

Scoring a retriever alone needs a retriever. A retriever is a corpus, cut into
passages, with an inverted index over them - and all three have to survive the
tool call that built them, because `search_the_index` and
`measure_retriever_recall` are separate calls in a conversation that outlives a
process. `docs/VISION.md`: *"The thread survives a restart, a closed laptop, a
crashed engine."* An index held in module state does not.

`docs/PRODUCT_SPEC.md` §6.6 says *"The index is a local file in the project.
Nothing is uploaded."* The harness database is that local file. Putting the
index in it buys thread scoping, cascade deletion and one transaction per
build, none of which a pickle beside the corpus would have.

## FOUR TABLES, AND THE FOURTH ONE IS WHY THIS IS A RETRIEVER

`retrieval_indexes` - one index. It pins the INSTRUMENT, in the same spirit as
`prompt_lines` pins an eval: which corpus, how it was cut, which tokeniser, and
the two BM25 constants. Every one of those changes what comes back from a
search, so a number measured against this index is only comparable to another
number measured against an index with the same row. `truncated` is the honest
half: an index that stopped at a cap is still searchable and must never be
scored as though it covered the corpus.

`retrieval_documents` - one row per document that went in, AND one row per
document that did not. A skipped file with its reason is the point: a corpus
report that lists only what worked is the "clean bill of health nobody earned"
this repository keeps finding.

`retrieval_passages` - the unit a retriever actually returns. `passage_key` is
`doc_key#n` and it is stable, because it is what an eval set's ground-truth
column has to be able to name.

`retrieval_postings` - term, passage, count. This is the inverted index, and it
is a table rather than a JSON blob on the passage for one reason: a search must
read the postings for the QUERY'S terms and nothing else. A blob per passage
would mean loading the whole corpus into memory to answer one question, which
is how a local index stops being local and starts being a memory error.

Document frequency is deliberately NOT stored. It is `COUNT(*)` over the rows a
search is already fetching, so a stored copy would be a second answer to a
question the table answers exactly - the drift this repository has been bitten
by twice.

## WHAT THE `CHECK`s REFUSE, IN SQL RATHER THAN IN PROSE

`docs/THE_PROPOSAL_LOOP.md`: *prose is not a wall*. Three of these are walls.

* `scorer IN ('bm25')` - there is one retriever in this build and it ships no
  model. A row naming a scorer this harness cannot run would be an index whose
  numbers nothing could reproduce.
* `passage_overlap < passage_chars` - an overlap at or past the window does not
  advance, so cutting would never terminate. The cutter guards it too; a bug
  that got past the guard would be a hang rather than a bad row, and a hang is
  the worst way to find out.
* `passages_n = 0 OR total_tokens > 0` - an index with passages and no tokens
  has an average passage length of zero, and BM25's length normalisation
  divides by it. A corpus of nothing but punctuation is a real thing to have on
  disk and it is not a retriever.
"""

from __future__ import annotations

VERSION = 10

SQL = """
CREATE TABLE IF NOT EXISTS retrieval_indexes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    source_path TEXT NOT NULL,
    text_field TEXT,
    scorer TEXT NOT NULL DEFAULT 'bm25',
    k1 REAL NOT NULL,
    b REAL NOT NULL,
    tokeniser TEXT NOT NULL,
    cut_by TEXT NOT NULL,
    passage_chars INTEGER NOT NULL,
    passage_overlap INTEGER NOT NULL,
    documents_n INTEGER NOT NULL DEFAULT 0,
    skipped_n INTEGER NOT NULL DEFAULT 0,
    passages_n INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    corpus_fingerprint TEXT NOT NULL,
    truncated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (thread_id, name),
    CHECK (scorer IN ('bm25')),
    CHECK (length(name) > 0),
    CHECK (k1 >= 0.0),
    CHECK (b >= 0.0 AND b <= 1.0),
    CHECK (passage_chars > 0),
    CHECK (passage_overlap >= 0 AND passage_overlap < passage_chars),
    CHECK (documents_n >= 0 AND skipped_n >= 0 AND passages_n >= 0),
    CHECK (passages_n = 0 OR total_tokens > 0)
);
CREATE INDEX IF NOT EXISTS idx_retrieval_indexes_thread
    ON retrieval_indexes(thread_id, id);
CREATE TABLE IF NOT EXISTS retrieval_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    index_id INTEGER NOT NULL REFERENCES retrieval_indexes(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    doc_key TEXT NOT NULL,
    source TEXT NOT NULL,
    characters INTEGER NOT NULL DEFAULT 0,
    passages_n INTEGER NOT NULL DEFAULT 0,
    skipped_why TEXT,
    UNIQUE (index_id, ordinal),
    CHECK (length(doc_key) > 0),
    CHECK (characters >= 0 AND passages_n >= 0)
);
CREATE INDEX IF NOT EXISTS idx_retrieval_documents_index
    ON retrieval_documents(index_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_retrieval_documents_key
    ON retrieval_documents(index_id, doc_key);
CREATE TABLE IF NOT EXISTS retrieval_passages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    index_id INTEGER NOT NULL REFERENCES retrieval_indexes(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES retrieval_documents(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    in_document INTEGER NOT NULL,
    passage_key TEXT NOT NULL,
    text TEXT NOT NULL,
    characters INTEGER NOT NULL,
    tokens INTEGER NOT NULL,
    UNIQUE (index_id, ordinal),
    UNIQUE (index_id, passage_key),
    CHECK (tokens > 0),
    CHECK (characters > 0)
);
CREATE INDEX IF NOT EXISTS idx_retrieval_passages_index
    ON retrieval_passages(index_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_retrieval_passages_document
    ON retrieval_passages(document_id, in_document);
CREATE TABLE IF NOT EXISTS retrieval_postings (
    index_id INTEGER NOT NULL REFERENCES retrieval_indexes(id) ON DELETE CASCADE,
    term TEXT NOT NULL,
    passage_id INTEGER NOT NULL REFERENCES retrieval_passages(id) ON DELETE CASCADE,
    tf INTEGER NOT NULL,
    PRIMARY KEY (index_id, term, passage_id),
    CHECK (tf > 0)
);
"""
