# four-asserts

Four things to assert about a run before its record counts.

No dependencies. Python 3.10+.

## The measured absence

Twenty-five agent and evaluation frameworks were read in their own docs,
READMEs and published API source on 2026-09-05, and tested for four properties.

**Adding a tool is nearly free in all of them.** Eight of the twenty-five take
four lines and a decorator; one takes a single Markdown file; most of the rest
take a typed function in a list. That part of the problem is solved.

**Asserting anything about the run is no part of any of them.**

| property | present |
|---|---|
| **(a) a counting gate** — the runner asserts `ran == discovered`, denominator printed | **1 of 25** |
| **(b) a lock** — who holds the resource, and is that holder alive | **0 of 25** |
| **(c) a witness** — identity that survives the data being gone | **0 of 25** (1 hashes, for deduplication) |
| **(d) a judge reason that is checked** — the stored reason re-derived from the artifact | **0 of 25** (7 store one) |
| **all four** | **0 of 25** |
| **any two** | **0 of 25** |

The one counting gate and the one content hash are in different projects.

The sharpest datum is (b): of the twenty-five, the project whose entire surface
is GPU scheduling says *GPU* fifty-three times in its README and *lock* zero
times. The nearest misses to a lock are concurrency limiters — a cap on how
many things run at once, with no holder and no lease, which answers a different
question.

For (c), one project is content-addressed by sha256 and uses it for deduplication;
none keeps an identity once the bytes are gone, and none reports *what was read*
with a denominator. For (d), seven store a reason field — `explanation`,
`reason`, `rationale`, `comment` — and one of them explicitly ignores it during
evaluation. A stored reason that nobody re-derives is a decoration on a verdict,
and it reads as evidence.

## What each one would have caught

These are from one harness's own record, with the commits.

**`assert_ran` — a suite that discovered 3,822 cases, ran 3,315, and printed OK.**
No failure, no error, no skip line: a green tick over 87% of the suite, one
command from being pushed on. Two runs were sharing one machine. Nothing in the
runner's output distinguished that from a complete run, because a runner reports
what it ran and never what it was supposed to run (`d9c1ac4`).

And the case a count alone cannot see: a module that fails to import is replaced
by one placeholder that is discovered and runs like anything else, so the totals
agree over a smaller tree. Measured on one clean clone, 35 real cases became 2
placeholders while `ran == discovered` held throughout (`d6fe7e6`).

**`hold` — two full suites running concurrently under two interpreters while
nobody held the lock.** The lock existed. It protected only the runs that
remembered to take it, which is not a guard. So a green run now also names the
neighbours it can see (`d15b756`).

And: a lock's liveness check answered *alive* for pid 8932, and 8932 was the
desktop shell. Every operating system reuses process ids, so a lock left by a
run whose number was later handed to a long-lived program reads as held for as
long as that program runs. The holder's process start time is recorded beside
its number (`ceede9d`).

**`witness` — a path is a location, not a version.** A size-and-modification-time
stamp is free and it is not identity: on one ordinary filesystem, two *different*
files of the same length written back to back produced an identical stamp in
**157 of 200 trials**. Not an exotic filesystem with a coarse clock — the common
case for a fast rewrite.

**`void_unless` — a model asked to grade 72 rewrites that are not degradations
kept 19, and every one of the 19 justified itself with a clause the rewrite
still contains word for word.** One cited *"the rewrite drops the 'over 25.00'
condition"* where the only difference between the two texts was a removed full
stop (`4c915ac`). The day before, the same instrument attributed a quotation —
`'We open 11am to 4pm on bank holidays, except Christmas Day'` — to a rewrite
that contained no such text. The prose was decoupled from the text in both
directions: it fabricated quotes from nothing and fabricated deletions from
something.

Deciding the same question by rule instead refused 106 non-degradations at zero
model calls (`7b28bf6`).

**The rule is held to the span the reason names, not merely to whether anything
changed.** Measured 2026-09-07 on those same 19 verdicts. Asking *did the rewrite
lose any words?* is an easier question than the reason asks, and the two come
apart: one verdict said *"removes the conditional 'If both are still showing on
Friday'"* about a rewrite of `That is` to `That's`, which really does lose a
word - so the coarse question said the claim held while the named conditional sat
untouched in the text. Where a reason quotes a span, that span is the claim.

Two conditions, and both are load-bearing. The quote must be **governed by the
removal verb**, because a reason reading `replaces "A" with "B"` quotes the
replacement, and a check taking any quoted span reads the new text as the deleted
one - the fabrication itself, committed by the checker. And the span must be
present in the **original as well as** the rewrite, because presence in the
rewrite alone only means the new wording was quoted.

Together: **19 of 19 of those verdicts now void by rule**, up from 14, with 3 of
170 genuine degradations touched against a ceiling of 5 fixed before the number
was read. The closed phrase list also gained its gerunds - `removing`,
`dropping`, `omitting` - which three of the nineteen reasons used, and which had
been coming back as *no rule registered*: the answer that means **nobody
checked**, about a claim a rule was sitting right there to check.

A rule may now take a third argument, `reason`. Two-argument rules are unchanged
and nothing registered before this needs to know it exists.

## Four lines

```python
from four_asserts import assert_ran, Hold, witness, void_unless, Verdict, account

ran = assert_ran(discovered=3822, ran=3315)          # exit_code 2: it did not say
with Hold("gpu.hold", holder="lane-a", purpose="a suite"):
    pass                                             # waits while the holder lives
kept = witness("pyproject.toml")                     # sha256 + size, outlives the file
rulings = void_unless([Verdict("KEEP", "It drops a clause.", "a b c", "a b c")])

print(ran.verdict)                                   # DID NOT SAY: 507 case(s) never ran
print(kept.how)                                      # sha256 ... over all N bytes
print(account(rulings))                              # 1 of 1 verdicts are void
```

## What this does not claim

- **It does not decide whether your work is good.** It decides whether the
  record of it says what it appears to say. A run where everything ran and
  everything failed is a valid record of a bad result.
- **`void_unless` does not decide whether a verdict was right.** A reason that
  survives its rule can still be a wrong call. It says only that the stated
  reason is about the text in front of it — and it distinguishes *no rule was
  registered for this reason* from *the rule ran and the reason failed it*,
  because collapsing those is how an unchecked field starts looking checked.
- **`hold` is not a distributed lock.** It is one file created with `O_EXCL`,
  atomic on Windows and POSIX alike. One machine, named holders.
- **`witness` costs a read.** Hashing a large artifact is not free, and a
  partial witness says it is partial and refuses to be compared as an identity.
- **`assert_ran` does not explain a mismatch.** It is red whenever discovery and
  execution disagree, whatever caused it. A guard that needs a diagnosis first
  is a guard that fails on the next cause nobody diagnosed.
- **The survey is a reading of documentation and published source, not of
  behaviour.** Two projects' docs were unreachable when it was taken; those are
  recorded as *not found*, not as *confirmed absent*.

## Licence

MIT.
