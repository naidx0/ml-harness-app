"""Did as many things run as were discovered?

THE FAILURE THIS IS FOR. A test suite discovered 3,822 cases, ran 3,315, and
printed OK. No failure, no error, no skip line: a green tick over 87% of the
suite and one command away from being pushed on. Nothing in the runner's own
output distinguished that from a complete run, because a runner reports what it
ran and never what it was supposed to run.

The check is one comparison and it does not need to know WHY the numbers differ.
That is the point: a guard that needs a diagnosis first is a guard that fails on
the next cause nobody diagnosed. This one is red whenever discovery and
execution disagree, whatever produced the gap.

THE SECOND FAILURE, which the first check cannot see. A module that fails to
import is replaced by many runners with a single placeholder that raises when
run. The placeholder is discovered and runs like anything else, so the counts
still match and the count check stays green while the tests inside that module
are gone. Measured on one clean clone: 35 real cases became 2 placeholders, and
`ran == discovered` held throughout. So the unimported modules are named
separately, and they outrank an ordinary failure - a run that does not say what
the tree contains is not a run that failed, it is a run that did not happen.

NOT BOUND TO ANY RUNNER. `Ran` is four numbers and a verdict; `unittest_suite`
is a thin adapter for the one runner in the standard library. Anything that can
say how many cases it found and how many it executed can use this.
"""

from __future__ import annotations

from typing import Iterable, NamedTuple, Sequence

#: Exit codes. TWO IS NOT ONE, deliberately: a run whose count does not match,
#: or that lost a module, has not told you whether the tree is good or bad, and
#: that is a different fact from a case failing. Callers that collapse them lose
#: the distinction the whole check exists to make.
GREEN = 0
FAILED = 1
DID_NOT_SAY = 2


class Ran(NamedTuple):
    """What a run says about itself, and whether that is enough to trust it."""

    discovered: int
    ran: int
    unimported: tuple[str, ...] = ()
    failures: int = 0

    @property
    def counts_agree(self) -> bool:
        return self.discovered == self.ran

    @property
    def said_what_it_holds(self) -> bool:
        """Did the run account for the tree at all?

        Both halves. Counts that agree over a tree that lost a module agree
        about a smaller tree than the one on disk.
        """
        return self.counts_agree and not self.unimported

    @property
    def exit_code(self) -> int:
        if not self.said_what_it_holds:
            return DID_NOT_SAY
        return FAILED if self.failures else GREEN

    @property
    def verdict(self) -> str:
        """One line, and it always carries the denominator.

        A number without its denominator is the shape of the original defect:
        "3,315 tests, OK" is true and useless, and "3,315 of 3,822" is the same
        measurement with the thing that makes it readable.
        """
        if self.unimported:
            named = ", ".join(self.unimported)
            return (
                f"DID NOT SAY: {len(self.unimported)} module(s) did not import: {named}. "
                f"The count ({self.ran} of {self.discovered}) cannot see this - an "
                "unimportable module is replaced by one placeholder that is discovered "
                "and run like anything else, so the totals agree over a smaller tree."
            )
        if not self.counts_agree:
            missing = self.discovered - self.ran
            return (
                f"DID NOT SAY: {missing} case(s) never ran ({self.ran} of "
                f"{self.discovered}). A run that is missing cases has not reported on "
                "the tree, which is a different fact from a case failing."
            )
        if self.failures:
            return f"RED: {self.failures} failure(s), and all {self.ran} of {self.discovered} ran."
        return f"GREEN: {self.ran} of {self.discovered}"


def pending(name: str = "this run") -> str:
    """What to print BEFORE the work, so a killed run cannot read as a pass.

    A run that is killed halfway leaves output that ends mid-progress, and the
    absence of a verdict is easy to read as no news. Saying in advance that the
    run ends with a verdict line turns a truncated log into a visibly
    unfinished one.
    """
    return (
        f"VERDICT PENDING: {name} ends with a line beginning 'GREEN', 'RED' or "
        "'DID NOT SAY'. If the output stops before that line, the run did not "
        "finish and its result is unknown - which is not the same as green."
    )


def assert_ran(
    discovered: int,
    ran: int,
    *,
    unimported: Sequence[str] = (),
    failures: int = 0,
) -> Ran:
    """The whole check. Four numbers in, a verdict out."""
    return Ran(
        discovered=int(discovered),
        ran=int(ran),
        unimported=tuple(unimported),
        failures=int(failures),
    )


# ---------------------------------------------------------------------------
# One adapter, for the runner in the standard library.


def count_leaves(suite: Iterable) -> int:
    """Cases in a `unittest` suite, counted explicitly.

    `countTestCases()` would do it. This walks the tree instead, because the
    number is the whole point of this module and a reader should be able to see
    where it comes from without leaving the file.
    """
    total = 0
    for item in suite:
        if isinstance(item, Iterable) and not hasattr(item, "_testMethodName"):
            total += count_leaves(item)
        else:
            total += 1
    return total


def modules_that_did_not_import(suite: Iterable) -> tuple[str, ...]:
    """The modules `unittest` replaced with an erroring placeholder.

    Read off the discovered suite rather than off the loader's error list,
    because a caller that discovers twice can hold a suite whose loader has
    already been thrown away. The placeholder's own name carries the module.
    """
    found = []
    for item in suite:
        if isinstance(item, Iterable) and not hasattr(item, "_testMethodName"):
            found.extend(modules_that_did_not_import(item))
            continue
        name = getattr(item, "_testMethodName", "")
        if name.startswith(("_FailedTest", "test_")) and "_FailedTest" in type(item).__name__:
            found.append(name)
        elif type(item).__name__ == "_FailedTest":
            found.append(name)
    return tuple(sorted(set(found)))


def unittest_suite(start_dir: str = "tests", pattern: str = "test*.py"):
    """Discover once and return `(suite, discovered, unimported)`.

    ONCE is the load-bearing word. Discovering separately for the count and for
    the run compares two different discoveries, and any drift between them is
    invisible in exactly the way this module exists to prevent.
    """
    import unittest

    suite = unittest.defaultTestLoader.discover(start_dir, pattern=pattern)
    return suite, count_leaves(suite), modules_that_did_not_import(suite)
