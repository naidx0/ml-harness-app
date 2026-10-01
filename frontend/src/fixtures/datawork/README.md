# Data-work fixtures

**Nothing in this folder was typed by hand: every payload here is verbatim
output that `app/tools/datawork.py` produced on a scratch database over datasets
this repository generated, captured by re-serialising the dict the tool
returned.**

`docs/VISION.md`'s invariant is that no number is ever invented — in code, in a
document or in a mockup — so `CarveCard.tsx` could not be built against numbers
somebody chose. `scripts/capture_datawork_fixtures.py` produces these; run it
with `--check` to re-capture into a temporary directory and compare the shape
blocks with the ones on disk instead of overwriting them, which is how the
sentence above stays checkable.

## The envelope

Each file is one situation. The engine's reply is under **`payload`** and is the
only part of the file that came from the engine; the four keys beside it were
written by the capture script and are about the payload, not part of it.

```jsonc
{
  "situation":   "which of the four this is, and why it is interesting",
  "dataset":     "what was on disk and what makes that file produce this",
  "produced_by": { "tool", "arguments", "thread_id", "database",
                   "captured_at_utc", "engine" },
  "shape":       { "what ResultView would draw for this payload, counted" },
  "payload":     { /* VERBATIM. This is the tool result. */ }
}
```

`SHAPES.json` is every `shape` block in one file, keyed by fixture name.

## The four files

| file | what it is |
| --- | --- |
| `01-carved-and-clean.json` | A carve that **WROTE** and whose own leak check found nothing. `ok: true`, which in this tool is the conjunction of *the two files account for every row read* and *the leak check found nothing* rather than a mood. 30 held out of 400 read, the size read off `G0_EVAL_SET.passes_when`. |
| `02-carved-and-leaking.json` | A carve that **WROTE AND LEAKS**. `ok: false` — a split that leaks is a failed artifact, not a successful one with a note. Three near-duplicate pairs, at 0.825, 0.825 and 0.805 against a threshold of 0.8, with the rows themselves in `leakage.examples`. This is the payload the card exists for. |
| `03-refused-no-such-column.json` | A refusal: the column named as holding the answers is not in the file. `nothing_was_written: true`, and it is literally true — every check runs before the one call that creates anything. |
| `04-refused-would-starve-training.json` | A refusal that carries arithmetic: holding out 30 of 60 rows would leave 30 to train on against `minimum_to_train_on: 100`. The refusal whose extra fields a card cannot know in advance, which is why `CarveRefusalCard` draws whatever the payload carried under the engine's own key names. |

## What `ResultView` does with them, measured

Counted by a transcription of `ResultView.tsx`'s own recursion (`MAX_DEPTH = 3`,
`LONG_TEXT = 320`): one row per entry of every object it draws, none for a
container at or past the depth cap. Depth counts containers, so the top-level
object is 1.

| | 01 clean | 02 leaking | 03 refused | 04 refused |
| --- | --- | --- | --- | --- |
| top-level keys | 22 | 22 | 7 | 10 |
| rows a flat table would draw | 83 | 83 | 7 | 10 |
| rows the payload holds | 92 | 186 | 7 | 10 |
| deepest nesting | 5 | 7 | 2 | 1 |
| containers dropped at depth 3 | 1 | 4 | 0 | 0 |
| rows hidden behind them | 9 | 103 | 0 | 0 |
| strings past the 320 fold | 2 | 2 | 0 | 0 |

**The cap does not fall on the boring part.** On `02` it falls on
`leakage.examples`, which is the three pairs of rows found on both sides of a
split this harness had just written — so the generic table answers *which three
rows leaked* with the words *"3 items, not shown here"*. That is the reason
`CarveCard.tsx` exists, and it is the same defect the chunking sweep had one
product surface earlier.

**And a claim that was made and was wrong, kept because the correction is the
useful part.** The card's first draft said `does_not_open_g0` and
`grading_is_still_yours` were both past the 320 fold and therefore rendered
collapsed. They are not: 299 and 221 characters. The two strings that are folded
are `summary` — 1,221 characters on `02`, beginning *"LEAKAGE IN WHAT THIS JUST
WROTE"* — and `method.how` at 526. The card's argument never rested on the wrong
half, and `tests/test_an_eval_set_is_carved_not_manufactured.py` now asserts the
true version in both directions so it cannot drift back.

## What is NOT in here

`drop_duplicates`, the other tool in `app/tools/datawork.py`. Its payload has not
been measured against `ResultView` and no card was built for it, so nothing in
this folder or in `frontend/src` makes any claim about how it renders. That is a
gap named rather than filled: a card built for a payload nobody counted would be
the thing this folder exists to prevent.
