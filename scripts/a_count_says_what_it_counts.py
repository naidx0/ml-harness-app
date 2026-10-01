"""A count that does not say what it counts is a count nobody can read.

## What this exists for

`kept: 164` was read as 164 training examples for two days. It was **127
distinct** `(prompt, chosen, rejected)` triples. The 156 kept by both judge
passes were 119; the 95 that survived every gate were 60; one triple appeared
seven times. Every decision about whether the corpus was large enough was taken
against a number that counted the same row up to seven times, and nothing in the
line said so - **because `164` on its own says nothing about what it counted**.

The repair is not to count more carefully. It is to make a count that does not
say what it counts hard to print and easy to catch.

## The rule

A number that is a count must be followed by a word saying what it counts:

* **`rows`** - the honest word when the count is not distinct over anything. It
  says "these are rows, and rows repeat"
* **`distinct <key>`** - naming what it is distinct over, because "distinct" on
  its own is the same lie one word shorter
* or any other unit the line means: `calls`, `hangs`, `holders`, `sources`

The check enforces that SOMETHING is there, not that it is the right something.
`a_count_distinct_over` refuses an empty key, so the one form where the missing
word is a lie rather than a slip cannot be written at all.

## What is not a count

A checker that flagged every digit would be switched off within a day, so it
recognises what is not a count and says nothing about it: ratios and
percentages, durations and units (`53.8 min`, `0.54 ms`, `240s`), the
`N of M` form - which already names its denominator and is what a bare count is
missing - dates, times, shas and seeds.

**ADJACENCY IS THE POINT.** The word must follow the number. A line mentioning
`rows` somewhere else does not license a bare count elsewhere in it, which is how
a qualifier drifts away from the thing it qualifies.
"""

from __future__ import annotations

import re

#: WHAT THIS CHECK IS AND IS NOT. It catches a number with NO unit at all -
#: `kept: 164`, `distinct_sources 47` - which is the failure that happened and
#: ran for two days. It does NOT adjudicate whether the unit is the right one:
#: telling `164 rows` from `164 survived` needs a noun-verb distinction no
#: regex holds, and a check that guessed at that would be switched off the first
#: time it was wrong. A count followed by a word is the author's claim about
#: what it counts; a count followed by nothing is not a claim at all.
_A_WORD_AFTER = r"[A-Za-z%][A-Za-z_%-]*"

#: Not counts. Anything matched here is removed before the search for bare ones.
_NOT_A_COUNT = (
    re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?Z?)?"),  # dates, stamps
    re.compile(r"\b\d{2}:\d{2}(?::\d{2})?\b"),                          # times
    re.compile(r"\b\d+\.\d+\b"),                                        # ratios, durations
    re.compile(r"\b\d+\s*%"),                                           # percentages
    re.compile(r"\b\d+\s*(?:s|ms|min|mins|minutes|sec|secs|seconds|h|hours?)\b"),
    re.compile(r"\b\d+\s+of\s+\d+"),                                    # N of M, and its M
    re.compile(r"\b(?:seed|sha|commit|pid|born|held|port|id)\s*[= ]\s*\w+", re.I),
    re.compile(r"\b[0-9a-f]{7,}\b"),                                    # shas, filetimes
)


def _what_is_left_to_check(line: str) -> str:
    text = str(line or "")
    for pattern in _NOT_A_COUNT:
        text = pattern.sub(" ", text)
    return text


#: A line that names what it is distinct over has said what it counts,
#: wherever the number sits: `the corpus, distinct triples: 63`.
_NAMES_A_DISTINCT_KEY = re.compile(r"\bdistinct\s+\S+", re.I)


def the_bare_counts_in(line: str) -> list[str]:
    """Every number in `line` that says nothing at all about what it counts.

    THE LIMIT, STATED. A number is bare when NOTHING follows it - end of line,
    or punctuation. That is the shape the real failure had (`kept: 164`), and
    it is the shape a regex can hold. It does NOT catch `kept 164 dropped 36`,
    where each number is followed by the next label: telling a unit from the
    next field needs a lexicon, and a check that guessed would be switched off
    the first time it was wrong. Narrow and trustworthy beats broad and
    ignored.
    """
    if _NAMES_A_DISTINCT_KEY.search(str(line or '')):
        return []
    left = _what_is_left_to_check(line)
    bare = []
    for match in re.finditer(r"\b(\d+)\b", left):
        after = left[match.end():]
        if re.match(r"[ \t]*" + _A_WORD_AFTER, after):
            continue
        if re.match(r"\s*:", after):   # `pass 1:` is an index, not a count
            continue
        bare.append(match.group(1))
    return bare


def why_this_line_hides_what_it_counts(line: str) -> str | None:
    """The sentence for a line carrying a bare count, else None."""
    bare = the_bare_counts_in(line)
    if not bare:
        return None
    which = ", ".join(bare)
    return (
        f"this line prints {which} without saying what it counts. Write `N rows` "
        "when the count is not distinct over anything, or `N distinct <key>` "
        "naming the key. `kept: 164` was read as 164 training examples for two "
        "days and was 127 distinct triples; a bare count cannot be read and must "
        "not be printed."
    )


def a_count_of(many: int, what: str = "rows") -> str:
    """`164 rows`. The honest form when the count is not distinct over a key."""
    return f"{int(many)} {what}"


def a_count_distinct_over(many: int, key: str) -> str:
    """`127 distinct (prompt, chosen, rejected)`.

    The key is required. `127 distinct` is the same lie one word shorter: it
    tells a reader that duplicates were removed without telling them what was
    compared, and two different keys give two different numbers.
    """
    if not str(key).strip():
        raise ValueError(
            "a distinct count must name the key it is distinct over - "
            "`N distinct` alone says duplicates were removed without saying "
            "what was compared, and two keys give two answers"
        )
    return f"{int(many)} distinct {key}"
