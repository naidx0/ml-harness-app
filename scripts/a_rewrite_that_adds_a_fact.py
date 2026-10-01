"""A rewrite that adds a content word absent from its source.

WHAT THIS IS FOR, measured 2026-09-05 on rows a real generator produced
(`docs/judge_runs/2026-09-05-false-keeps-on-production-output.md`). Of 20 rows
the pipeline's judge KEPT, eight add words that are not in the source, and three
are flat falsehoods about the shop:

    source : except Christmas Day and Boxing Day WHEN WE ARE CLOSED
    rewrite: INCLUDING Christmas Day and Boxing Day
    judge  : "uses only facts present in the real answer"          KEEP

The shop is closed on those days. Nothing in this repository caught it: the
validator's `specifics_the_rewrite_adds` looks for numbers, money, names and
places and finds none; the inverted-refusal backstop has no negation token to
miss; the diff gate admits it correctly, because it IS a content change.

Clause (2) of the pipeline's own contract already forbids this - "Every fact,
number, name, price and place in the rewritten answer already appears in the
real answer" - so this is not a new rule. It is that rule, enforced at zero
calls instead of asked of a judge that certifies the opposite.

## Why the word list is a grammatical class and not a frequency cut

The instruction was to build it from the corpus rather than from my head. **Pure
frequency does not separate them at this size.** In the 49 answers, `day`,
`tell`, `order`, `number`, `shelf`, `card` and `email` each occur 6 or 7 times -
exactly as often as `are`, `or`, `that`, `do` and `your`. A frequency cut would
either keep `shelf` as a function word or drop `only` as a content word.

So the class comes from English grammar, which is not mine to choose, and the
MEMBERSHIP is filtered to words this corpus actually uses: every entry below
appears in `runs/honest-path/train.jsonl`, and `the_function_words_this_corpus_uses`
prints each with its count so a reader checks the list rather than trusting it.
A word that is grammatical but never used here is not in the list.
"""

from __future__ import annotations

import re
from collections import Counter

#: Closed-class English: articles, pronouns, auxiliaries, prepositions,
#: conjunctions, and the handful of adverbs that carry no fact about a shop.
#: Membership is grammar; which of these actually ship is decided by the corpus.
CLOSED_CLASS: frozenset[str] = frozenset({
    "a", "an", "the", "this", "that", "these", "those",
    "i", "you", "we", "they", "it", "he", "she", "me", "us", "them", "him", "her",
    "my", "your", "our", "their", "its", "his", "yours", "ours",
    "am", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had",
    "will", "would", "can", "could", "shall", "should", "may", "might", "must",
    "of", "in", "on", "at", "to", "for", "with", "by", "from", "into", "onto",
    "about", "as", "over", "under", "between", "through", "during", "up", "out",
    "and", "or", "but", "so", "if", "then", "than", "because", "while", "when",
    "where", "which", "who", "whom", "whose", "what", "how",
    "there", "here", "also", "just", "very", "too", "still", "any", "some",
    "no", "not", "yes", "all", "each", "both", "other", "another", "same",
    "one", "two", "three", "four", "five", "ten",
    "please", "thanks", "sorry",
})


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", (text or "").lower().replace("’", "'"))


def the_function_words_this_corpus_uses(answers: list[str]) -> dict[str, int]:
    """Closed-class words attested in these answers, with their counts.

    Printed rather than asserted: a reader checks which grammatical words this
    shop actually writes, and a word in `CLOSED_CLASS` that never appears here
    is not doing any work.
    """
    counts = Counter(word for answer in answers for word in _words(answer))
    return {word: counts[word] for word in sorted(CLOSED_CLASS) if counts[word]}


def the_content_words_this_rewrite_adds(real: str, rewrite: str) -> list[str]:
    """Content words in the rewrite that are not in the real answer.

    Counts, not presence: a rewrite using `days` twice where the source used it
    once has not added a fact, so only words that appear MORE often count -
    and `Counter` subtraction gives that for nothing.
    """
    added = Counter(_words(rewrite)) - Counter(_words(real))
    return sorted({word for word in added.elements() if word not in CLOSED_CLASS})


def why_this_rewrite_adds_a_fact(real: str, rewrite: str) -> str | None:
    """The reason this pair may not ship, or None.

    A DEGRADATION REMOVES; IT DOES NOT INVENT. The corpus is pairs of a good
    answer and a worse one, and a rewrite that introduces a word the source
    never used is making a claim the source cannot support - whether that claim
    happens to be true, like a rephrase, or false, like "including Christmas
    Day" about a shop that is closed.
    """
    added = the_content_words_this_rewrite_adds(real, rewrite)
    if not added:
        return None
    return (
        f"the rewrite introduces content the real answer does not contain: "
        f"{added}. Clause (2) of the judge's own contract requires every fact "
        "in the rewrite to appear in the real answer, and this is that clause "
        "enforced without asking."
    )
