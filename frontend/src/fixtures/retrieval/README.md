# Retrieval fixtures

**Nothing in this folder was typed by hand: every payload here is verbatim
output that `app/tools/retrieval.py` produced on a scratch database over corpora
this repository generated, captured by re-serialising the dict the tool
returned.**

If a situation could not be produced by the engine it is not in this folder. No
number in any `payload` was chosen, rounded, prettified or filled in, and no
number anywhere in a card built against these files may be either -
`docs/VISION.md`'s invariant is that every displayed number carries provenance,
and a card demonstrated against numbers somebody typed is a lie about a product
whose entire thesis is that numbers have origins.

## The envelope

Each file is one situation. The engine's reply is under **`payload`** and is the
only part of the file that came from the engine; the four keys beside it were
written by the capture script and are about the payload, not part of it.

```jsonc
{
  "situation":   "which of the eight situations this is, and why it is interesting",
  "corpus":      "what was on disk and what makes that corpus produce this",
  "produced_by": { "tool", "arguments", "index_built_first", "thread_id",
                   "database", "captured_at_utc", "engine" },
  "shape":       { "what ResultView would draw for this payload, counted" },
  "payload":     { /* VERBATIM. This is the tool result. */ }
}
```

`SHAPES.json` is every `shape` block in one file, keyed by fixture name.

## The nine files

| file | tool | what it is |
| --- | --- | --- |
| `01-recall-recorded.json` | `measure_retriever_recall` | A recall that **RECORDED**. 18 of 24 at k=5, `stampable: true`, one row in `measured_facts`. The curve rises 4 → 8 → 12 → 15 → 18 of 24, so `recall@1` is 4/24 and `recall@5` is 18/24 off the same ranked lists: this is the payload that shows what k bought. |
| `02-recall-refused-a-tie-decided-it.json` | `measure_retriever_recall` | A recall that **recorded nothing and said why** - refusal 7 of the seven, where a score TIE and not the retriever decided whether the right passage was in the top k. The hard case: it has a recall (`0.0`), a curve and a per-row table, every number a successful run has, and may not stamp one of them. |
| `03-sweep-no-evidence.json` | `compare_chunkings` | **NO EVIDENCE across every pair**, over four genuinely different cuts. 34/40, 36/40, 40/40, 40/40 - four visibly different scores, six comparisons, none separating. `most_changed_by_any_pair: 6` against `min_changed_questions_at_this_family_size: 8`: the refusal's arithmetic is in the payload. |
| `04-sweep-a-set-and-not-a-winner.json` | `compare_chunkings` | Some pairs **DO** separate. Nine of fifteen comparisons separate after Holm, `not_beaten_by_anything` holds **three** settings, and `crowned` is still `null`. THAT IS A SET AND NOT A WINNER, with real numbers behind it. |
| `05-sweep-identical-cuts.json` | `compare_chunkings` | The **degenerate** sweep: four settings, one distinct cut, passage-for-passage identical indexes. `cuts.says` is the sentence that has to be read before the verdict, because "NO EVIDENCE that any of these settings differs" over one index is a true sentence about nothing. |
| `06-sweep-plan-only.json` | `compare_chunkings` | The sweep **refused before running** - `run` defaulting to false. `ran: false`, seventeen keys instead of forty, and counts (`4` rebuilds, `1038` passages, `26366` posting rows, `160` retrievals) counted by the same `kept_passages()` that `build()` writes from rather than estimated. Same call as `03` with `run` left out. |
| `07-sweep-refused-passage-level-ground-truth.json` | `compare_chunkings` | The **passage-level-ground-truth refusal**, which only a sweep can reach: a passage key names a cut and a sweep varies the cut. The refusal fires inside the per-setting loop, so **one** index of the two asked for was already built, and `indexes` names it rather than pretending the database is untouched. |
| `08-sweep-twelve-settings.json` | `compare_chunkings` | **The worst case for a renderer.** Twelve settings, the most the tool allows: 66 pairwise comparisons, a Holm threshold of 0.05/66, and 1,612 rows for a flat table to draw. |
| `09-recall-refused-no-ground-truth.json` | `measure_retriever_recall` | Not one of the eight and here because it is a different SHAPE, not just a different reason. Refusal 1 returns before anything is scored, and `_refusal` gives it **the same shape as a successful call carrying the honest null in every slot**: `recall_at_k: null`, `hits: null`, `recall_curve: []`, `rows: []`, `questions_scored: 0`. So a card that reads `payload.recall_at_k` gets `null` rather than a missing key here, and 38 rows reach the table against `02`'s 77. A card that survives `02` has not yet been shown to survive this. |

## What `ResultView` does with them, measured

Counted by a transcription of `ResultView.tsx`'s own recursion (`MAX_DEPTH = 3`,
`LONG_TEXT = 320`): one row per entry of every object it draws, none for a
container at or past the depth cap. Depth counts containers, so the top-level
object is 1.

| fixture | keys | rows drawn | rows the payload holds | depth | summarised away | rows hidden | strings > 320 chars |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01-recall-recorded | 38 | 411 | 411 | 4 | 30 | 0 | 3 |
| 02-recall-refused-a-tie-decided-it | 36 | 77 | 77 | 4 | 4 | 0 | 2 |
| 03-sweep-no-evidence | 40 | 372 | 559 | 6 | 17 | 187 | 18 |
| 04-sweep-a-set-and-not-a-winner | 40 | 586 | 802 | 6 | 24 | 216 | 13 |
| 05-sweep-identical-cuts | 40 | 372 | 553 | 6 | 20 | 181 | 14 |
| 06-sweep-plan-only | 17 | 150 | 159 | 4 | 3 | 9 | 7 |
| 07-sweep-refused-passage-level-ground-truth | 29 | 142 | 151 | 4 | 3 | 9 | 8 |
| 08-sweep-twelve-settings | 40 | 1612 | 2223 | 6 | 49 | 611 | 34 |
| 09-recall-refused-no-ground-truth | 35 | 38 | 38 | 2 | 0 | 0 | 2 |

**And the depth cap does not fall on the boring parts.** `what_is_summarised_away`
in each `shape` block names them; across the sweeps it is the same three every
time:

* `per_setting[].resolution` - **every setting's 95% interval, in every sweep.**
  `ci_95`, `half_width_points`, `resolves_a_difference_of_at_least_points` all
  land inside `5 fields, not shown here`. That is the number's own width, which
  is the one thing `EvalCard`'s docstring says may never be a footnote.
* `per_setting[].own_run` - each setting's own recall, its own curve, and
  whether it would have been stampable alone.
* `rows[].returned` - the passages the retriever actually returned, on every
  row of every recall payload. 24 of them in `01`.
* `levers.we_cannot_pull` - the three levers of `NO_TRAIN__FIX_RETRIEVAL` this
  harness does not own, which the tool names in every reply including every
  refusal, and which arrives on screen as `3 items, not shown here`.

## How these were produced, and how to check that claim

`scripts/capture_retrieval_fixtures.py` wrote every file here.

```sh
ML_HARNESS_DB=/tmp/scratch.db python scripts/capture_retrieval_fixtures.py --check
```

`--check` re-runs all nine situations into a temporary directory, compares the
payloads with the ones on disk and writes nothing. It is the answer to "how do I
know none of this was typed": run the engine again and see whether the same
numbers come back. Drop `--check` to regenerate.

The script refuses to start unless `ML_HARNESS_DB` names something that is not
the repository's own `ml_harness.db`. Every situation ran in a conversation the
script created - thread ids 1 through 9, one per fixture, in each file's
`produced_by.thread_id` - because an index and a fact are scoped to a
conversation and borrowing an existing thread id is how 98,802 rows once landed
in somebody's real one.

The corpora are generated by the same script: a handbook whose summary notices
outrank the sections they summarise, a set of contracts of which six are
contested by a shorter note, a ledger whose two query terms sit in different
paragraphs, and a folder holding a byte-identical vendored copy of one of its
own documents.

**Two things in these files depend on where the corpus sat.** `corpus_path`,
`eval_path` and the `how=` sentence on the stamp in `01` quote the absolute path
of the file they read - that is the provenance and it is meant to be there - so
`shape.longest_string_chars` moves with the length of that path. Nothing else
does: keys, rows, depth, what is summarised away and the counts in the table
above are identical whatever directory the capture ran from, which is what
`--check` compares.

Everything else is deterministic. BM25 over a token count, no model, no network,
no randomness anywhere in `app/tools/retrieval.py`.
