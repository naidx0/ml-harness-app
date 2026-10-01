# Changelog

## 0.1.0

First release. Each piece is lifted from a working harness where it was written
in response to a specific failure, and adapted to stand on its own with no
dependency on that harness.

### Lifted from

| here | from | the failure it was written for |
|---|---|---|
| `assert_ran` | the harness's counting gate | a suite that discovered 3,822 cases, ran 3,315, and printed OK (`d9c1ac4`); and the case a count alone cannot see, where 35 cases became 2 import placeholders while the totals still agreed (`d6fe7e6`) |
| `hold` | the harness's machine lock | two suites running concurrently while nobody held the lock (`d15b756`); a liveness check that answered *alive* for a recycled pid belonging to the desktop shell (`ceede9d`) |
| `witness` | the harness's subject and derivation code | a size-and-time stamp that could not tell two different files of the same length apart in 157 of 200 trials |
| `void_unless` | the harness's judge record and its change-classifier | 19 of 72 KEEP verdicts citing a deletion that did not happen (`4c915ac`); the same question decided by rule refusing 106 non-degradations at zero model calls (`7b28bf6`) |

### Changed in the lift

- **`witness` uses sha256 where the harness uses size and modification time.**
  The harness refuses to hash on purpose: costing a step over a 50 GB dataset
  must not read 50 GB. This package makes the opposite trade and states the
  cost, because a witness meant to outlive its bytes cannot be a stamp that
  two different files can share.
- **`hold` takes no default timeout.** The harness's lock carried a 1,800-second
  one; measured, two runs queued about 18 and 19 minutes behind holders that ran
  about 28 and 30, and a third arriving behind the second would have waited half
  an hour to be told nothing. Waiting is keyed on the holder's liveness instead.
- **`assert_ran` is not bound to any runner.** The harness's version is a
  `unittest` gate. Here the check is four numbers and a verdict, with a thin
  adapter for the runner in the standard library.
- **`void_unless` tokenises differently.** The harness's classifier keeps
  trailing punctuation on a word; on the very case this was lifted for — where
  the only difference between two texts is a removed full stop — that reports a
  dropped clause for a dropped period. Edge punctuation is stripped here, and
  the package's own suite fails without that change.
