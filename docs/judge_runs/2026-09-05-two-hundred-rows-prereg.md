> **CORRECTION, 2026-09-06 00:30.** This page and the body of `b7690ca` first
> reported **192 judgements, 164 KEEP and 28 DROP**. Both figures are wrong. The
> run judged **188**, keeping 164 and dropping **24**, and the derived
> near-copy rate is 7 of 188 = 3.7% rather than 7 of 192 = 3.6%.
>
> **The error was arithmetically visible on its own line.** The same table said
> *validator refused 12* beside *reached the judge 192*, and 200 − 12 is 188.
> Nothing had to be recomputed to catch it; the two numbers simply were not
> checked against each other, and a wrong total then travelled into three more
> places on two pages before a reader asked which of the two records was right.
>
> Settled from three independent directions, all agreeing on 188 and 24:
> `report.json` (`validator.dropped` 12, `judge.kept` 164, `judge.dropped` 24);
> 200 − 12 = 188 and 164 + 24 = 188; and `dropped.jsonl`, which holds 36 rows
> whose own `dropped_by` field splits 24 judge to 12 validator.
>
> **No conclusion on this page moves.** 3.7% is inside the same 13.8% bound as
> 3.6%, the escalation condition was on a proportion of kept rows and 164 is
> unchanged, and every finding about the judge rests on the 164 or on the 68,
> neither of which the error touched. What it damages is the record's right to
> be taken on trust: a page that reports a total it can disprove with its own
> subtraction has to be read with a calculator, and that cost is real even when
> every conclusion survives.

# Two hundred rows through the wired pipeline — preregistration

**Written 2026-09-05 before any call.** The same pipeline as
`2026-09-05-the-gates-on-generated-rows-prereg.md`, both gates wired, at a draw
eight times larger. It is one run that is also the dataset.

## The cost, stated before it is spent

**Measured rate: 49 seconds per call**, from 49 calls in ~2,400 s on the 25-row
run. Two hundred rows is one generation and one judgement each — up to **400
calls, about 5½ hours of card**. That is the whole of a night's GPU and it is
written here so the number is agreed rather than discovered.

Results file, named before the run: **`runs/two-hundred/`**, with
`train.synthetic.jsonl`, `dropped.jsonl`, `report.json` and `arms.jsonl`.

## What is counted

1. generator failures
2. validator refusals, by fault
3. **gate refusals** — the backstop and the diff gate, separately
4. the judge's KEEP/DROP split
5. scope-marker agreement on the KEPT rows
6. **rows whose rewrite adds a word absent from the source** — the class the
   2026-09-05 reading found at 8 of 20, which nothing catches

## Predictions, written first

* **Gate refusals: zero again.** At 0 of 24 the Wilson ceiling on gate-refusable
  output is **13.8%**; at 0 of 200 it falls to **1.88%** — and the peer relaying
  this quoted ~1.5%, which is the figure this preregistration corrects before it
  is used. **One refusal is a finding**, and it would be the first time either
  gate fired on production output.
* **Added-word rows near 8 in 20**, i.e. **around 80 of 200**, since that is the
  rate the smaller run measured and nothing has changed to alter it. If it comes
  in far below, the 25-row draw was unlucky and the false-KEEP finding narrows.
* **Scope-marker agreement**: 11 of 20 kept rows on the small draw, interval
  0.34–0.74, which says almost nothing. At 200 it becomes a number worth one
  sentence — and it stays an observation about two instruments agreeing, never a
  validation, because this run has no ground truth either.

## What would make me stop the run

A generator failure rate above 1 in 10, or an unreadable-verdict share above the
pipeline's own 10% stop. Both are the pipeline's existing refusals and the run
inherits them rather than adding new ones.

## What it cannot settle

Still one generator, one model, one shop's 49 answers, one named degradation.
Two hundred rows drawn round-robin from 49 sources means **each source appears
about four times**, so the rows are not 200 independent observations of the
generator's behaviour — they are 49 sources sampled four ways, and any per-row
rate should be read with that in mind. This is the first preregistration on this
corpus where n exceeds the source count, and it is the honest limit of the draw.

## Waiting on the card

`gpu.lock` is held — `lane=practical` at 18:52Z, then `lane=orchestrator` at
19:07Z. The run starts when it is free, verified directly, with the lock taken
at start in UTC and deleted at end in the same turn.

---

# Result: both gates fired, and the prediction that they would not is refuted

**2026-09-05, under the lock from 19:53:42Z, released at the end.** 200
generations and 188 judgements.

| | |
|---|---|
| generated | 200 |
| generator failed | **0** |
| validator refused | 12 |
| reached the judge | **188** — 164 KEEP, 24 DROP |
| **refused by the two gates** | **7** |
| rows arm A kept that the gates refuse | **0** |

Change kinds: **83 `content_removed`, 105 `content_substituted`, 4
`content_added`.** Files: `runs/two-hundred/train.synthetic.jsonl`,
`dropped.jsonl`, `report.json`, and `analysis.jsonl` rebuilt from them.

## The prediction was wrong, and that is the finding

> *Gate refusals: zero again … **One refusal is a finding.***

There are **seven**, and three of them are the inverted refusals the backstop
was built for and the 24-row draw never produced:

```
REAL   : We no longer take cheques. Card, cash and bank transfer are all fine.
REWRITE: We take cheques.                                    <- backstop
REAL   : ... they do not stack with the sale shelf.
REWRITE: ... they stack unconditionally with the sale shelf. <- backstop
REAL   : ... they do not stack with the sale shelf.
REWRITE: ... you can stack the code with the sale shelf.      <- backstop
REAL   : Everything else is 30 days.
REWRITE: Everything else is returnable for longer ...         <- diff gate
REAL   : Card, cash and bank transfer are all fine.
REWRITE: Card, cash, bank transfer, and any other accepted    <- diff gate
         payment method are all fine.
REAL   : ... whichever you have to hand.
REWRITE: ... without you needing ...                          <- diff gate
REAL   : We hold reservations for 48 hours ...
REWRITE: We hold reservations for at least 48 hours ...       <- diff gate
```

**The shop does not take cheques.** That row would have entered the corpus.

**This retires my own framing from the 24-row run.** I called the gates
"insurance, not repair" because nothing fired at n=24, and wrote that this
generator "makes neither" near-copies nor reversed refusals. At n=200 it makes
both. The Wilson ceiling was the honest part of that report and it held: 0 of 24
bounded the rate below 13.8%, and the measured rate is **7 of 188 = 3.7%** —
inside the bound, and not zero.

**And no cost.** Every one of the seven was a row the judge would have dropped
anyway or a row that should not exist; zero rows the judge kept were refused.

## The fourth outcome: 68 of 164 kept rows add a content word

41% of kept rows, against 40% on the pilot — the rate is stable across an
eight-fold larger draw.

**The reading the ruling requires is not finished.** Of the subset that also
drops a scope marker — the pilot's shape for a genuine degradation — I have read
seven:

| row | verdict |
|---|---|
| `usually have two or three` → `have two or three **titles** today` | genuine degradation, would be lost |
| `**Only** secondhand CD sets` → `We **sell** secondhand CD sets` | genuine, would be lost |
| `**If** both are still showing on Friday` → `We will refund one of the **charges**` | genuine, would be lost |
| `within 30 days` → `You can **return the book and receive** credit` | genuine, would be lost |
| `**occasionally** Spanish` → `we **always include** Spanish` | **a lie**, correctly refused |
| `we refund **if we buy**` → `we **always** refund it, **regardless**` | **a lie**, correctly refused |
| `**only** findable by asking` → `can be found **without needing to ask**` | **a lie**, correctly refused |

**Four of seven are genuine degradations.** If that fraction holds across the
68, the plain rule would lose about **39 of 164 kept rows — 24%**, against the
pilot's 3 of 20 (15%). That is the escalation condition, and seven rows is not
enough to declare it: the remaining sixty-one are the next thing read, and the
number goes to Max with the rows either way.

## A failure of my runner, after the work and costing nothing

The script crashed at the very end on `UnicodeEncodeError: '\u2011'` — a
non-breaking hyphen in one of the rewrites it was printing. The pipeline had
already written its three files, so **no GPU time was lost**; only my
`arms.jsonl` was missing, and it was rebuilt from disk with no further calls.
The lock released as designed, because the release was chained to the command
and not to the script's success.

It is the fourth time this night that a character escape has broken something of
mine, and the first time it did so on output rather than on source.

---

# The 68 read, and the rule stays

**All 68 kept rows that add a content word, read one at a time.** The ruling set
the line before the reading: *the plain rule stays whatever the count, unless
the 68 show fewer than one lie blocked per three genuine degradations lost.*

| | count |
|---|---|
| **lies blocked** — the rewrite states something the source contradicts | **42** |
| **genuine degradations lost** — a real over-promise the rule refuses too | **22** |
| neither — a rephrase, or a rewrite that makes the offer worse | 4 |
| ~~unclear on the text I have~~ **now scored** | ~~3~~ 0 |
| **total** | **68** |

**The three unclear rows are scored.** They were unreadable because
`analysis.jsonl` truncated row text at 100 characters — my own file, not the
run's — so the fix was to rewrite it from `train.synthetic.jsonl` with the full
text. Read in full: one is a **lie** (`If it has been longer than that, tell me
and I will chase it` → `We will chase it until the refund appears`, which
invents an unconditional commitment to chase), and two are **neither** — `bring
anything down` → `bring any number of items down` is a rephrase, and `we refund
if we buy` → dropping the refund entirely makes the offer *worse*, which is not
a widened promise.

**Final: 42 lies blocked, 22 degradations lost, 4 neither. Ratio 1.91.**

**The ratio is 42 to 22 — 1.91 lies blocked per degradation lost.** The line was
1 per 3, or 0.33. **The rule stays**, and not marginally: it blocks between five
and six times as many lies as the threshold requires.

**The escalation condition is also not met.** 22 genuine degradations lost of
164 kept rows is **13.4%**, against the pilot's 3 of 20 = 15%. The loss rate did
not rise with the larger draw; it fell slightly.

## What the 41 look like

Not subtle, and mostly outright reversals of the source:

```
We no longer take cheques.          ->  We accept cheques, cards, cash ...
Sale shelf sales are final.         ->  Sale shelf sales are returnable.
free on Sundays                     ->  is free every day
no encyclopaedias, magazines or     ->  water damaged books are acceptable
  water damaged books
the mezzanine is up eight stairs    ->  The mezzanine is accessible.
dust jacket rubbed, name on flyleaf ->  The copy is clean and tight throughout.
occasionally Spanish                ->  Spanish is always included
whichever you have to hand          ->  no need to hand over either
return it within 30 days            ->  return it at any time
```

Nine of the 41 add the word `always` or `every` to a source that hedged.

## What the 22 look like, so the cost is not abstract

```
usually have two or three           ->  have two or three titles today
Only secondhand CD sets             ->  We sell secondhand CD sets
If it has not shipped I can cancel  ->  I can cancel the order now
If both are still showing on Friday ->  We will refund one of the charges
10 percent ... in store only        ->  the discount applies to all purchases
Orders placed on the 3rd ship ...   ->  Your order will ship ...
```

Every one is the named degradation performed by a model that rephrased while it
degraded. They are real losses and the trade takes them knowingly.

## What is still not known

`runs/two-hundred/analysis.jsonl` now holds every row's source, rewrite and
judge sentence in FULL, so anyone can disagree with any line above. And this is one reader's judgement on one shop's corpus: the counts are
ASSERTED, the rows are all on disk, and a reader who reclassifies six rows moves
the ratio from 1.86 to 1.4 without coming near the line.

---

# Two readers, the same 68 rows, 1.91 against 0.74

The research lane read the same sixty-eight blind at 20:40 and counted **29
lies and 39 degradations, ratio 0.74**. I counted **42 and 22, ratio 1.91**.

**Both keep the rule** — the line was 0.33 and both readings clear it — so the
decision is not in doubt and nothing is reclassified here. What is worth having
is *which rows* the two readers split on, and that needs my per-row list, which
the commits carried only as totals.

**`docs/judge_runs/data/2026-09-05-the-sixty-eight-classified.jsonl`** holds all
68: id, class, a one-clause reason, the added words, and both texts in full. The
ids are positions in the added-fact subset of `analysis.jsonl`, in file order,
so the two lanes can line up row for row.

**It is under `docs/` and not beside `analysis.jsonl` because `runs/` is
gitignored.** A classification written there would be on one machine and
readable by nobody — the same trap that made two test modules fail to import on
a clean checkout earlier tonight. A file another lane is asked to compare
against has to be a file another lane can fetch.

## Where I expect the split to be, stated before I see theirs

Not everywhere. The rows I called lies for a **direct contradiction** are hard to
read the other way:

```
 1  except Christmas Day ... when we are closed  ->  including Christmas Day
13  Sale shelf sales are final                   ->  are returnable
16  We no longer take cheques                    ->  We accept cheques
22  free on Sundays                              ->  free every day
```

The split will be in the rows where a **hedge became a statement**. I called
`usually arrives` → `will arrive within` a degradation when nothing else moved
(3, 19, 31, 51) and a **lie** when the rewrite added an absolute like `always`
or `every` (10, 26, 27, 40, 48, 57, 62). That boundary is mine and it is a
judgement, not a rule: a reader who treats every hedge-to-statement as a lie
would move seven rows and land near 49/15; one who treats them all as
degradations would move eleven the other way and land near 31/33 — which is
close to what the research lane reports.

**So the disagreement is probably one boundary, not sixty-eight judgements.**
That is a testable claim and their row-by-row write-up will settle it.

## What the disagreement means, whichever way it falls

Two careful readers of one corpus, working from the same definition, differ by
thirteen rows on whether a rewrite lies or merely over-promises. That is the
same shape as this repository's law that **two label sets that disagree are a
rubric that did not decide** — and it says the lie/degradation boundary is not
crisp enough to be a key, only crisp enough to be a *ratio*, which is why the
ruling that shipped the rule set a ratio and not a count.

Nothing here reclassifies a row. The counts stand as each lane read them.

## CORRECTION, 2026-09-06 07:30: every count on this page is rows, not distinct rows

**The 164 kept rows are 127 distinct `(prompt, chosen, rejected)` triples.** This
page, and every page that took its numbers from it, counted duplicate rows as
separate rows. The whole record, recounted:

| reported | rows | **distinct** |
|---|---|---|
| kept by judge pass 1 | 164 | **127** |
| kept by both judge passes | 156 | **119** |
| kept by both passes and all three gates | 95 | **60** |
| a twenty-row run that reported adding 11 | 11 | **3** |

One triple appears **seven times** in the 95; fourteen appear twice, three
appear three times, three appear four times.

**The cause.** The generator draws from 49 source answers with one degradation
instruction and reproduces the same rewrite for the same source repeatedly, and
nothing in the pipeline deduplicated - not the generator, not the validator, not
the judge, not the report. A dedup gate now refuses a triple the corpus already
holds, at generation, with zero judge calls and its own `duplicate` column.

**What moves and what does not.** Rates expressed as a proportion of kept rows -
68 of 164 adding a content word, 39 of 164 lost to the plain rule, 13.4% - are
proportions of *rows* and remain true of rows. What changes is every claim about
HOW MUCH DATA THERE IS: the corpus is 60 distinct three-gate rows, not 95, and
the showcase's line of 100 is 37 away rather than 5. See
`docs/journeys/2026-09-06-the-showcase-stopped-before-training.md`.

**How this survived two days.** I met these duplicates while writing
`data/the_sixty_eight_ids.py` and wrote a comment about them - *"the corpus holds
rows whose two sides are identical to another row's"* - then used
first-occurrence-wins to work around them and never asked how many there were.
Noticing a thing, coding around it, and not asking what it cost is a different
failure from getting a number wrong, and a worse one: the arithmetic errors on
this project were caught within the hour, and this ran for two days under every
decision made about whether the corpus was big enough.

## The yield estimate, restated on distinct rows

The corpus's growth was estimated as **0.414 three-gate rows per generated row**,
and that number is rows, not distinct rows. Recomputed on distinct
`(prompt, chosen, rejected)` triples, from 220 generated rows across two runs:

| | |
|---|---|
| generated rows | 220 |
| distinct three-gate rows they produced | **63** |
| **generated rows per distinct row** | **3.5** |
| the twenty-row run's marginal yield | **3 new distinct from 20 = 0.15** |

**The marginal figure is the one that matters and it is a quarter of the
headline.** 0.414 was measured against a corpus that did not yet contain the
rows being counted; 0.15 is what a run adds to a corpus that already holds 60
distinct rows. The gap between them is saturation, and it will keep widening:
**40 of the 49 source answers already contribute**, at a mean of 1.60 distinct
rows each.

**What this does to the plan built on 0.414.** Clearing the line was costed at
twelve rows and half an hour, then corrected to twenty rows and fifty minutes
when the probability was computed rather than the expectation. On distinct rows
both are wrong by an order of magnitude: 37 more distinct rows at 0.15 is about
**247 generated rows, 740 calls, and seven hours** - and that assumes the
marginal rate holds, which saturation says it will not.

**The honest bound.** With one degradation instruction and 49 sources, the
ceiling is roughly 49 x the distinct-per-source rate. At 1.60 that is about 78,
and the corpus is at 63. **More generation against this design cannot reach 100.**
Reaching it needs more source answers or more degradation types, and either is a
change to the design rather than another run of it.

This is the third correction to this number in one night. The first was
arithmetic I asserted without running; the second was an expectation reported as
a guarantee; this one is a denominator that counted the same row up to seven
times. All three moved the same way - the estimate was optimistic - and all three
are on the record rather than swapped in.
