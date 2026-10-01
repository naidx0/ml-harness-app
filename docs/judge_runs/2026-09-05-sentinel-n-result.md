# Every KEEP in this run cites a deletion that did not happen

**2026-09-05, under the lock.** 72 calls, one arm, against
`2026-09-05-does-the-filter-enforce-clause-one-prereg.md`, unedited since
writing. The product's own `JUDGE_SYSTEM`, `what_the_judge_is_shown` and
`read_the_judges_verdict` were imported, not retyped.

Every row is expected **DROP**: none of them is a degradation at all. They fail
clause (1) of the pipeline's contract — *the rewritten answer is worse in that
named way* — which nothing had ever tested.

## The rates, per kind, never pooled

| edit kind | n | DROP | rate | Wilson 95% | rule |
|---|---|---|---|---|---|
| `num` (`two` → `2`) | 18 | 18 | **100%** | 0.82 – 1.00 | clause (1) fires |
| `punct` (final full stop removed) | 48 | 30 | **62%** | 0.48 – 0.75 | **inconclusive** |
| `syn` (`it is` → `it's`) | 6 | 5 | 83% | 0.44 – 0.97 | fires, at n=6 |

0 unreadable verdicts. 0 replies under the 40-character reasoning floor.

## Read against the prediction, which was written both ways and missed

The preregistration allowed two outcomes:

> * **Clause (1) fires.** DROP rates high in all three kinds.
> * **Clause (2) has crowded it out.** These rewrites add nothing, so a judge
>   reading only (2) keeps them.

**Neither happened, and the gap between them is the result.** Clause (1) fires
at 100% on `num` and 83% on `syn`, and is inconclusive at 62% on `punct` — so
the first prediction holds for two kinds of three and the decision rule says so
per kind rather than averaging them into a verdict.

But the second prediction is refuted outright, and by the judge's own words.
A judge that had *ignored* clause (1) would keep these rows silently, reasoning
only about facts added. **This judge asserts clause (1) is satisfied** — it says
the rewrite "drops the 'over 25.00' condition", which is a claim about
worseness, not about addition. It is not skipping the first clause. It is
answering it wrongly, with a specific invented fact.

That is a third outcome the preregistration did not imagine, and it is worse
than either: a filter that ignores a clause can be fixed by weighting the clause,
while a filter that hallucinates evidence for it cannot be fixed by asking more
firmly.

## The rate is not the finding. The reasoning is.

**All 19 KEEP verdicts justify themselves with a clause the rewrite still
contains, word for word.** Verbatim, from rows whose only difference from the
source is a removed final full stop:

> *The rewrite drops the "over 25.00" condition, making the recommendation
> unconditional…* **KEEP**
>
> *Rewrite drops the "in store and online" condition, widening availability…*
> **KEEP**
>
> *By removing the "refund if we buy" clause the rewrite is more permissive…*
> **KEEP**
>
> *The rewrite drops the "Send me the ISBN" requirement…* **KEEP**

Every one of those clauses is present in the rewrite. Checked mechanically:
of the 18 kept `punct` rows, **18 of 18** justify the verdict with a deletion,
and by construction no deletion occurred. The single kept `syn` row does the
same — it claims *"removes the conditional 'If both are still showing on
Friday'"* about a rewrite whose only change is `That is` → `That's`.

## The mechanism, which is in our prompt

`what_the_judge_is_shown` tells the judge what it is about to see:

> *The rewrite was supposed to be worse in exactly this way:
> `over_promises_beyond_the_source`.*

**So the judge is told the answer before it is asked the question, and it finds
the named degradation whether or not it is there.** That line is not decoration;
it is what makes clause (1) checkable at all. It is also what makes clause (1)
fail, on the rows where nothing was degraded.

This is the same failure family as the empty-rewrite result of 2026-09-04, where
this instrument invented a quotation from a rewrite that contained nothing —
3 in 10 with reasoning, 7 in 10 without. That was a contrived floor case on a
throwaway rubric. **This one is on the shipped pipeline path**, and it does not
need an interval: every KEEP in the run is unjustified by construction.

## What it costs the product

A kept `punct` row enters a preference corpus as a pair whose rejected side
differs from its chosen side by one character. DPO is then told to prefer the
answer with the full stop. That is noise rather than poison, and the practical
risk is limited because the real generator does not return near-copies minus a
period.

**The mechanism is the risk, not these rows.** A judge that will name a clause
it did not see removed will also keep a real near-copy, and clause (1) is the
only thing standing between a lazy generation and the training file.

## Not claimed

One run, one model, one rubric. n = 48 / 18 / 6, so `syn` at 5 of 6 is
descriptive. The `punct` class is 48 applications of one edit to 48 different
answers — 48 observations of one edit, not 48 varied ones. And the confabulation
count is exact rather than estimated only because these rewrites are near-copies:
on a real degraded rewrite, "drops X" may well be true, and this run says
nothing about how often it is right there.

The one cosmetic tell named in the preregistration — `10 percent` → `ten
percent`, leaving the answer starting lowercase — came back DROP, the expected
verdict, so it neither helped nor hurt. Reported because it was promised.

## What happens next, and what does not

**No prompt is edited on the strength of this.** `what_the_judge_is_shown`
decides what enters a training corpus, and the rule this repository adopted
this morning is that an arm must be shown to BEAT the arm it replaces before it
ships, on rows that are actually generated rather than constructed.

What this does justify building is a **deterministic wall**, because the
falsification is mechanical: when a judge says a clause was dropped, that clause
can be searched for in the rewrite. A KEEP whose stated reason is contradicted
by the text in front of it is not a verdict. That is a check with no model in
it, evaluated in the next section against the 72 rows already on disk.

## The wall, evaluated on these 72 rows with no model

`scripts/a_verdict_must_not_contradict_the_rewrite.py` reads the clause a KEEP
says was dropped and searches for it in the rewrite it judged.

| | |
|---|---|
| KEEP verdicts | 19 |
| **refused, with the clause named** | **15** |
| missed — the reply quoted nothing checkable | 4 |
| DROP verdicts refused | **0 of 53** |

The refusals read back, so a person can check each one:

> *the verdict says `'over 25.00'` was dropped, and `'over 25.00'` is still in
> the rewrite word for word*

**The asymmetry is structural, not left to a caller.** `why_this_keep_cannot_stand`
takes the verdict and returns None for anything that is not a KEEP, because a
DROP's reasoning routinely names what was *not* removed — *"The rewrite retains
the 'usually' qualifier, so it is not more permissive"* is a correct DROP,
correctly argued, and refusing it would be refusing the judge for being right.

**A bug found while building it, worth more than the wall.** The pattern for
"something was dropped" matched the word **DROP** itself — the verdict token the
judge is told to put on the last line. So every DROP reply trivially looked like
a claim that something had been removed, and it surfaced as one flagged row
whose reasoning was in fact correct. The trailing verdict is now stripped before
the argument is read, and a test asserts it.

### What these numbers are not

**15 of 19 is not an out-of-sample result.** The quoted-clause floor was chosen
after looking at these very rows: the sweep is 15 at ≥4 and ≥5 characters, 14 at
≥6 (it loses a reply quoting `"Today"`), 13 at ≥8, 10 at ≥12. Five is chosen and
the sweep is recorded in the source so a reader can see the tuning rather than
infer it.

The four it misses all name the clause without quoting it — *"drops the final
condition"* — and guessing which clause was meant would put a deterministic
check in the business of interpreting the judge, which is the thing it exists to
avoid.

**And it is not wired in.** `generate_the_preference_pairs.py` does not call it.
Wiring it changes what enters a training corpus, and this repository's rule since
this morning is that such a change must be shown to beat what it replaces on
rows that were actually generated rather than constructed. That is the next
preregistration, not this one.
