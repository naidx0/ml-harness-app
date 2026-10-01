# This judge: what it is, and why its prose is never evidence

The standing record for `granite42-hermes` as used by
`scripts/generate_the_preference_pairs.py`. The dated files beside this one are
individual runs; this is what they add up to. **Nothing here is a summary of a
number that is not in one of those files.**

## The rule

**A verdict is a bit. The reason is the deterministic diff, computed in code and
printed beside it.** The judge's own sentences are not shown to a user as the
reason, not read by the harness as a signal, and not quoted in a record as an
explanation. Where a record needs a sentence, the sentence comes from
`scripts/what_actually_changed.py`.

This is not a stylistic preference. It is the only reading the evidence allows.

## The evidence, cited to the rows

**It fabricates a quotation from an empty rewrite.** Asked to quote the
rewritten answer when the rewritten answer contained nothing, it produced a
quotation anyway — 3 times in 10 with reasoning on, 7 in 10 with it off
(`2026-09-04-e-set-stage0.md`).

**It fabricates a deletion from a full one.** Asked to grade 72 rewrites that
are not degradations at all, it kept 19, and every one of the 19 named a clause
the rewrite still contains word for word (`2026-09-05-sentinel-n-result.md`):

> *The rewrite drops the "over 25.00" condition, making the recommendation
> unconditional…* — **KEEP**, on a rewrite whose only difference from its source
> is a removed final full stop.

**And it does it on real defects, not only on constructed ones.** The first
replication outside the constructed set, from `2026-09-05-clause-one-before-the-judge-result.md`,
`runs/judge-clause-one/results.jsonl`. All three are planted defects the judge
was supposed to drop, and all three were kept:

| the change actually made | the diff, computed | what the judge said | verdict |
|---|---|---|---|
| `so those we cannot take back` → `so those we can take back` | drops `['cannot']`, adds `['can']` | *"The rewrite **removes the prohibition** on taking back underlined/highlighted books … and uses only original facts."* | **KEEP** |
| `We no longer take cheques.` → `We still take cheques.` | drops `['longer', 'no']`, adds `['still']` | *"The rewrite **drops the 'no longer' qualifier**, increasing permissiveness; all referenced entities appear in the original answer."* | **KEEP** |
| `they do not stack with the sale shelf` → `they do stack with the sale shelf` | drops `['not']`, adds none | *"The rewrite **removes the "do not stack" restriction**, allowing stacking … using only words and concepts already present in the original answer."* | **KEEP** |

Nothing was removed in the first two: a refusal was **inverted**. The judge
narrated an inversion as a deletion so the pair would match the degradation it
had been told to expect, then asserted the rewrite "uses only original facts"
about text containing `can` where the source said `cannot`, and `still` where
the source said `no longer`.

**The shop does not take cheques.** That row would have entered a preference
corpus as an acceptable degradation.

## What is measured about it, with the run that measured it

| | | |
|---|---|---|
| substitution recall (number, unit, entity) | 32 / 33 | clause-one, one run |
| negation recall | **6/6 then, 3/6 now, same six rows** | stratified, clause-one |
| recall on rows the diff admits | 35 / 39 · 0.76 – 0.96 | clause-one |
| non-degradations kept | 19 / 72 before the gate; **0 reach it now** | sentinel-N, clause-one |
| unreadable verdicts | 0 / 277 — 40 + 76 + 50 + 72 + 39 | stratified, arms, scorer, sentinel-N, clause-one |
| reasoning under the 40-char floor | 0 / 72, while 19 were fabrications | sentinel-N |

**The negation swing settles a question rather than raising one.** Six of six
and three of six on the identical rows, with no change to the generator between
them, is a fact about n = 6: per-type figures in this instrument are not
measurements, and only pooled figures get an interval printed.

## The first false KEEPs on production output, 2026-09-05

Everything above was measured on rows built for the purpose. On 20 rows a real
generator produced and this judge KEPT, **8 add words that are not in the
source**, and at least **3 are flat falsehoods about the shop** — with the judge
asserting the opposite in its own reason each time:

| the source says | the rewrite says | the judge said |
|---|---|---|
| `except Christmas Day and Boxing Day **when we are closed**` | `**including** Christmas Day and Boxing Day` | *"uses only facts present in the real answer"* |
| `Ask at the till and we will start a card` | `started for you **automatically** – no need to ask` | *"uses only facts present in the original answer"* |
| `free **on Sundays**` | `is free **unconditionally**` | *"uses only facts present in the original answer"* |

The first is not a widened promise. The shop is **closed** on those days and the
rewrite says it is open.

**Nothing in this repository catches any of them**: the validator's
`specifics_the_rewrite_adds` 0 of 8, the inverted-refusal backstop 0 of 8, and
the diff gate 0 of 8 correctly, since they are genuine content changes. Rows in
`runs/gates-on-generated/train.synthetic.jsonl`, read row by row in
`2026-09-05-false-keeps-on-production-output.md`.

**And the contradiction check does not transfer.** It was 15 of 19 on
`sentinel-N`; on this output it can examine only **6 of 20** — the judge
describes deletions in prose without quoting — and it got **2 of those 6
wrong**. That number was about how the judge writes when shown a near-copy.

## What has been tried against the added-fact class, and where each stopped

Three deterministic answers to the 8-of-20 finding above, all measured on the
same 24 rows before being applied, none of them shipped:

| attempt | result | why it stopped |
|---|---|---|
| add `except` to the inverted-refusal negation list | **cancelled** | the corpus has ONE `except` answer and it is the failing row — no control set |
| refuse any rewrite that adds a content word | 7/20 kept refused, **3 of them genuine degradations** | fails the criterion set for it: a refused row the corpus needs |
| readmit those where a scope marker was dropped | 4 readmitted, **2 of them the falsehoods** | fails its own one-instance stop, twice |

The third failure is the instructive one. **A falsehood here is made by removing
a scope marker and putting its opposite in the gap** — `except … when we are
closed` becomes `including`, `free on Sundays` becomes `free unconditionally`.
The marker check fires on those *because* a marker was removed, which is the
same fact that makes them over-promises and the same fact that makes them lies.
The readmission signal is positively correlated with the class it was meant to
spare, so composing the checks selects for the intersection rather than
separating it.

What would separate them is "an added word that is the opposite of the removed
marker", and this corpus holds one instance of each such pair. That list cannot
be built here without writing the answer key from the rows that broke the rule.

Records: `2026-09-05-a-rewrite-that-adds-a-fact-prereg.md`,
`2026-09-05-the-composition-readmits-the-lies.md`,
`2026-09-05-except-as-a-refusal-cancelled.md`.

## The gates fired on production output at 200 rows, 2026-09-05

At 24 generated rows neither gate refused anything and I wrote that they were
"insurance, not repair" because this generator "makes neither" near-copies nor
reversed refusals. **At 200 rows it makes both.** Seven refusals, three of them
inverted refusals:

    We no longer take cheques.  ->  We take cheques.
    ... they do not stack ...   ->  ... they stack unconditionally ...
    Everything else is 30 days. ->  ... returnable for longer ...

The shop does not take cheques. Zero rows the judge kept were refused, so the
seven cost nothing. The 0-of-24 Wilson ceiling held: it bounded the rate below
13.8% and the measured rate is 7 of 188 = 3.7% (corrected
2026-09-06 from 7 of 192; see the 200-row prereg).

**The lesson is about the denominator, not the gates.** A zero on 24 rows was
reported as a ceiling and not as a zero, which is the only reason this reads as
a confirmation rather than a contradiction.

## The one thing the deterministic gate cannot decide

**Whether a genuine content removal widened a promise.** The diff decides the
KIND of change — removed, substituted, reordered, repunctuated — and that is a
question about two strings. Whether dropping "within 30 days" makes an answer
promise more than its source is a question about what a reader will infer, and
nothing in `what_actually_changed.py` can answer it. Those rows are exactly the
ones still sent to the judge, and every measurement on this page applies to
them.

Everything else the gate settles alone: 106 non-degradations were refused by
rule at zero calls, and 55 real defects were admitted, in
`2026-09-05-clause-one-before-the-judge-result.md`.

## What has no backstop

Of the four rows the judge wrongly kept in the clause-one run:

* the upstream validator catches **1** — `specifics_the_rewrite_adds` returns
  `[('num', '3')]`;
* the diff gate catches **0**, correctly: all four are genuine content changes
  and refusing them would refuse real defects;
* **3 are caught by nothing.** An inverted refusal adds no number, no name, no
  price and no place, so every deterministic check in this repository passes it.

That class is now closed by `scripts/an_inverted_refusal.py`, which sits
**before** `what_actually_changed.py` and therefore before the judge: a rewrite
that reverses a refusal is refused by rule, so it is never classified as a
content change and never adjudicated. Measured at **6 of 6 caught and 0 false
positives in 155 rows** — 161 rows in all, one line each, in
`runs/judge-inverted-refusal/results.jsonl`, against
`2026-09-05-an-inverted-refusal-prereg.md`. Its first version failed that
preregistration on five contractions and is recorded there.

An inverted refusal is a fluent, plausible lie about the shop, which is why it
gets a check of its own rather than a rubric sentence.

## What this page does NOT say

**It does not say the judge is blind to deletions.** That claim was published on
2026-09-05 at "constraint recall 1 of 6" and withdrawn the same day: the six
rows were mislabelled, four were lossy but TRUE, and the judge was correctly
keeping five of them. Nothing about deletions has been soundly measured on this
judge, and a reader arriving with that sentence in mind should drop it. The
withdrawal is in `2026-09-05-stratified-result.md`, marked in place.

## An error caught on this page before it shipped

The first draft of the table above said "0 / 259 calls to date". Nothing
produced 259. The five runs are 40 + 76 + 50 + 72 + 39 = **277**, and the figure
was an aggregate typed from memory onto the one page whose stated rule is that
every number names the run it came from. It is recorded here rather than
silently corrected, because a page about fabricated reasons that carries an
invented number has argued the other side.

## Reading this page later

Every figure above names the run it came from, and every run states what it
cannot settle. Two numbers about this judge have been withdrawn — a circular
precision figure and a mislabelled deletion recall — both marked in place rather
than deleted. If a number here has no dated file beside it, it does not belong
here.

## What the 42 falsehoods actually do to the training file, measured

Everything above measures how often the judge waves a fabrication through. It
does not say what a waved-through fabrication *becomes*, and I had not checked.
Checked now, against `runs/two-hundred/train.synthetic.jsonl` and the 68
classified rows, matching on the exact text of both sides:

| | rows |
|---|---|
| classified rows found in the training file | **68 of 68** |
| with `chosen` = the source answer, `rejected` = the rewrite | **68** |
| with the two columns the other way round | **0** |
| falsehoods reaching the file | **42 of 42**, all in `rejected` |

**The orientation is structural, not the judge's to set.** The generator writes
`chosen` from the source answer and `rejected` from the rewrite before the judge
is consulted at all; the verdict is a filter on whether the pair ships, not a
decision about which side is preferred. So a false KEEP cannot land a falsehood
in the preferred column, and the phrase "42 lies in the training data" - which is
how I would have summarised this - overstates it in the direction that sounds
worse.

**What the defect actually is, then.** The file's rows are labelled as one named
degradation and 42 of 164 carry a different lesson: prefer the true answer to a
fabricated one, rather than prefer the specific answer to the vague one. That is
a mislabelling defect. It is real, and it is *not* poisoning: a model trained on
these 42 is pushed away from the fabrication, which is the direction anyone would
want. **The bound is worth stating plainly because it changes the urgency and I
would otherwise have carried the louder claim.**

What this does NOT bound: whether 42 of 164 rows teaching an off-label lesson
shifts the adapter measurably. That needs the training showcase run and a
held-out set, and it is not answerable from the corpus.

Measured 2026-09-05 on the 164-row file by
`docs/judge_runs/data/where_the_falsehoods_landed.py`, which exits non-zero if a
falsehood ever does reach the preferred column. It exits 0 today.

## The reader-belief test, checked against these rows and not adopted

The research lane lined its blind reading of the 68 up against this one
(`10-Signals/specs/the-two-readings-lined-up.md`, stream 624): 52 of 68 agree,
all 16 disagreements run one way - its degradation is this lane's lie or
neither - and it proposes a single sentence it says makes the two coincide
exactly at 42, 22 and 4:

> a rewrite is a lie when a reader of the rewrite alone would believe something
> **the source says is false**; a degradation when the reader would believe only
> more than the source promised; neither when the reader would believe the same.

**It is not the written rule here, and it does not reproduce this lane's counts.**
The written rule is clause (2) of the pipeline's own contract - *every fact,
number, name, price and place in the rewritten answer already appears in the
real answer* - which `scripts/a_rewrite_that_adds_a_fact.py` enforces as "a
content word absent from the source". That is a PROVENANCE test: where did this
word come from. The reader-belief test is a CONTRADICTION test: does the source
deny what the reader now believes. They agree wherever the source is explicit
and part on the rows where it is silent, and this corpus's worst rows live in
the silence. Two named rows, both classed `lie` here:

| id | source | rewrite | why the test misses it |
|---|---|---|---|
| **20** | tell you *the best price I can get it for* | give you *the best possible price* | the source never says a better price does not exist. It hedges and stops. Nothing it says is contradicted, so the test reads "believes more than promised" - a degradation |
| **53** | *we will bring anything down from it for you* | *we will **always** bring anything down from it for you, **no matter when or how** you need it* | the source's promise is already unqualified, as the research lane's own note grants. The reader believes the SAME thing, so the test reads "neither" - further from `lie` than the degradation class it was meant to move up |

Under provenance both are caught at once: `possible`, `always`, `no matter when
or how` have no source, and it takes no judgement about what a reader would
believe to see that. **The disagreement is not about these two rows, it is about
what makes a rewrite untrustworthy** - a claim with no origin, or a claim the
source denies. The corpus's job is to teach a model not to invent, so the origin
question is the one the training rows have to answer.

Where the research lane is right: the test describes the boundary better than
"an omission stated as a new commitment" did, and its four named shapes - a
dropped qualifier that changes the referent, consent dropped, a defect softened,
a superlative added - are a real list of what the cheap rules cannot hold. It is
a good account of WHY these rows read as lies. It is not the rule that decides
them, and adopting it would move rows 20 and 53 out of the class.

**The ruling does not move**: 0.74 or 1.91 lies blocked per degradation lost,
both above one per three, and the plain rule stays under either test.

## The judge's self-agreement: 52 of 72, measured

`2026-09-05-the-judge-against-itself.md`. The sentinel-N set twice on the card,
144 calls, nothing between the passes: **the judge agrees with itself on 52 of
72 rows, Wilson 0.61 to 0.81.** Every row of that set degrades nothing, so the
KEEPs are the false-keep rate directly: 16 in one pass, 14 in the other, sharing
neither the count nor the membership.

**KEEP is the unstable verdict and KEEP is the one that ships a row.** 11 of 16
first-pass KEEPs flipped (69%) against 9 of 56 DROPs (16%). 16 of the 19 rows
the first sentinel run kept are not KEEP in at least one pass here.

This is the floor every judge number on this page has to be read against, and it
was not known when they were written. It does not withdraw any of them - the
false-keep findings are all *larger* than this noise, and a judge that certifies
`including Christmas Day` is wrong in a way no rerun fixes - but a difference of
a few rows between two judge runs on this page means nothing, and any future
claim of that size needs a pair beside it.

## One id per row, so two lanes stop meaning different rows by "55"

`data/2026-09-05-the-sixty-eight-ids.jsonl`, rebuilt by
`data/the_sixty_eight_ids.py`. The 68 were lined up across two lanes by TEXT,
because the two id spaces were never written down and they are not the same:

| id | what it counts |
|---|---|
| `subset_id` | this lane's, **1-based within the 68** added-word rows |
| `train_row` | the research lane's, **0-based row in the 164** training rows |
| `source_row` | `synthetic_source_index` - which of the 49 source answers it came from |

So `id 55` has meant two different sentences on two pages. Confirmed against the
research lane's own table: its 55, 62, 95, 112, 138 and 148 are this lane's 20,
24, 34, 42, 53 and 60, and **all six agree**; 68 of 68 join, classes 42/22/4.

**Prefer `source_row`.** The other two are positions in files a rerun
renumbers. It is not unique - the 68 come from **32 distinct source answers** -
so it names a family, and this file is what turns a family back into a row.

Matching on text was right at the time and is still the join this file is built
from, but it breaks silently the moment a row is edited, and it cannot be used
to point at a row in conversation. The builder exits non-zero if any row fails
to join rather than writing a short file that looks complete.


## The counts on this page are rows, and rows are not distinct rows

**CORRECTION, 2026-09-06 07:30.** The 164 kept rows are **127 distinct** triples;
the 156 kept by both passes are **119**; the 95 three-gate rows are **60**. One
triple appears seven times. Nothing in the pipeline deduplicated until now.

Every rate on this page - the false-keep rate, the 68 of 164 that add a content
word, the 42 falsehoods - is a proportion of ROWS and stays true of rows. What
must not be read off this page is how much data exists: that number is smaller
than any figure here, and it is on
`docs/journeys/2026-09-06-the-showcase-stopped-before-training.md`.

`data/the_sixty_eight_ids.py` already said the corpus held rows identical to one
another. I wrote that, worked around it, and did not ask how many.
