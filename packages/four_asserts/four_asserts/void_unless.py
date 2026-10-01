"""A verdict is void until its reason survives a rule.

THE FAILURE THIS IS FOR. A model was asked to grade 72 rewrites that are not
degradations at all. It kept 19, and every one of the 19 justified itself with a
clause the rewrite still contains word for word:

    "The rewrite drops the 'over 25.00' condition, making the recommendation
     unconditional."                                                     KEEP

The only difference between that rewrite and its source was a removed full
stop. A day earlier the same instrument invented a QUOTATION from an empty
rewrite. So the prose was decoupled from the text in both directions: it
fabricated quotes from nothing and fabricated deletions from something.

Storing the reason does not help. Seven of twenty-five surveyed tools store a
reason field; none checks it. A stored reason that nobody re-derives is a
decoration on a verdict, and it reads as evidence.

WHAT THIS DOES. A verdict arrives with a reason and is VOID. A registered
predicate is asked to re-derive that reason from the two artifacts. If it can,
the verdict stands; if it cannot, the verdict is void and counted as void, with
its denominator. The judge decides; it does not explain.

WHAT IT DOES NOT DO. It does not decide whether the verdict was right. A reason
that survives its rule can still be a bad call, and this says only that the
stated reason is about the text in front of it.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

#: The reason a predicate could not be found for. Kept distinct from "the
#: predicate ran and said no", because "nobody checked" and "the check failed"
#: are different facts and collapsing them is how an unchecked field starts
#: looking checked.
NO_RULE = "no rule registered for that reason"


@dataclass(frozen=True)
class Verdict:
    """A decision, the reason given for it, and the pair it is about."""

    value: str
    reason: str
    before: str
    after: str


@dataclass
class Ruling:
    """What became of a verdict once its reason met a rule."""

    verdict: Verdict
    rule: str
    stands: bool
    why: str

    @property
    def void(self) -> bool:
        return not self.stands


@dataclass
class Register:
    """The rules that can re-derive a reason, and nothing else can."""

    rules: dict[str, Callable[[str, str], bool]] = field(default_factory=dict)
    detectors: dict[str, Callable[[str], bool]] = field(default_factory=dict)

    def add(
        self,
        name: str,
        *,
        claims: Callable[[str], bool],
        holds: Callable[[str, str], bool],
    ) -> None:
        """Register a rule.

        `claims` reads the REASON and says whether it is making this kind of
        claim. `holds` reads the two artifacts and says whether the claim is
        true of them. Splitting those is what stops a rule from being asked a
        question it was not written for.
        """
        self.detectors[name] = claims
        self.rules[name] = holds

    def which_rule(self, reason: str) -> str | None:
        for name, claims in self.detectors.items():
            if claims(reason.lower()):
                return name
        return None

    @staticmethod
    def _ask(rule: Callable, verdict: Verdict) -> bool:
        """Call a rule, giving it the reason only if it asks for one.

        MEASURED 2026-09-07, and this is an interface limit rather than a
        preference. `holds(before, after)` cannot see the reason, so a rule that
        must read the span the reason NAMES could not be written at all - and
        that is the rule the harness needed. `dropped_clause` answers "did the
        rewrite lose any words"; the fabrication is always about WHICH words.
        The two come apart: a rewrite of "That is" to "That's" really does lose
        a word, so the coarse rule let a verdict stand whose named conditional
        was still present, untouched.

        Two-argument rules keep working unchanged. Nothing that was registered
        before this existed has to know about it.
        """
        try:
            wants = len(inspect.signature(rule).parameters)
        except (TypeError, ValueError):
            wants = 2
        if wants >= 3:
            return bool(rule(verdict.before, verdict.after, verdict.reason))
        return bool(rule(verdict.before, verdict.after))

    def check(self, verdict: Verdict) -> Ruling:
        name = self.which_rule(verdict.reason)
        if name is None:
            return Ruling(verdict, rule="", stands=False, why=NO_RULE)
        holds = self._ask(self.rules[name], verdict)
        return Ruling(
            verdict,
            rule=name,
            stands=holds,
            why=(
                "the {} claimed by the reason is present in the pair".format(name)
                if holds
                else "the {} claimed by the reason is NOT present in the pair".format(name)
            ),
        )


#: Punctuation that sits on the outside of a word and is not part of it.
#: Trailing marks are stripped because the case this module was built from
#: turns on exactly one: the only difference between the rewrite and its source
#: was a removed full stop, and a tokenizer that keeps "25.00." apart from
#: "25.00" reports a dropped clause for a dropped period. Inner marks stay -
#: "25.00" and "don't" are one token each.
EDGES = ".,;:!?'" + chr(34)


def _words(text: str) -> list[str]:
    found = re.findall(r"[a-z0-9][a-z0-9.,'-]*", text.lower())
    return [w for w in (word.strip(EDGES) for word in found) if w]


def _numbers(text: str) -> list[str]:
    return re.findall(r"-?\d[\d,]*(?:\.\d+)?", text)


NEGATIONS = ("not", "no", "never", "cannot", "without", "unless", "except")


# ---------------------------------------------------------------------------
# The four rules. Each one is a claim a reason commonly makes about a rewrite.


def dropped_clause(before: str, after: str) -> bool:
    """Did the rewrite actually lose words the original had?"""
    lost = set(_words(before)) - set(_words(after))
    return bool(lost)


#: A span the reason puts in quotes, and the verbs that assert its removal.
#: Straight and curly both, because one reply uses both.
A_NAMED_SPAN = re.compile(r"[“‘\"']([^”’\"']{4,80})[”’\"']")
A_REMOVAL_VERB = re.compile(
    r"\b(?:drops?|dropping|removes?|removing|omits?|omitting|deletes?|deleting|strips?)\b",
    re.I,
)
#: How far after the verb a quoted span is still its object. A reason saying
#: `replaces "A" with "B"` quotes the REPLACEMENT, and a rule reading any quote
#: takes the new text for the deleted one - which is the fabrication itself,
#: committed by the checker.
SPAN_WINDOW = 60


def _named_span_removed(reason: str, before: str, after: str) -> bool | None:
    """Whether the span the reason NAMES really left the text.

    None when the reason names no span, which hands the question back to the
    coarse rule rather than inventing an answer.
    """
    for verb in A_REMOVAL_VERB.finditer(reason or ""):
        for span in A_NAMED_SPAN.findall(str(reason)[verb.end(): verb.end() + SPAN_WINDOW]):
            wanted = " ".join(_words(span))
            if not wanted:
                continue
            in_after = wanted in " ".join(_words(after))
            in_before = wanted in " ".join(_words(before))
            if in_before:
                return not in_after
    return None


def dropped_clause_named(before: str, after: str, reason: str = "") -> bool:
    """`dropped_clause`, but held to the span the reason actually named.

    MEASURED on 19 fabricated KEEPs: the coarse question ("did anything go?")
    and the real claim ("did THAT go?") agree on 10 of them and disagree on the
    rest. Where a reason names a span, the named span is the claim, and
    answering the easier question is how a check passes something it should
    have caught.
    """
    named = _named_span_removed(reason, before, after)
    if named is not None:
        return named
    return dropped_clause(before, after)


def added_word(before: str, after: str) -> bool:
    """Did the rewrite actually add words the original did not have?"""
    return bool(set(_words(after)) - set(_words(before)))


def changed_number(before: str, after: str) -> bool:
    """Did any figure actually move?"""
    return sorted(_numbers(before)) != sorted(_numbers(after))


def inverted_negation(before: str, after: str) -> bool:
    """Did a negation appear or disappear?

    Counted rather than merely detected: "not" surviving in both texts is not
    an inversion, and a reason claiming one over an unchanged count is exactly
    the fabrication this module is for.
    """
    count = lambda text: sum(_words(text).count(word) for word in NEGATIONS)
    return count(before) != count(after)


def standard_register() -> Register:
    """The four rules, with the phrases each reason kind uses.

    The phrase lists are CLOSED and literal. A model deciding which rule
    applies would put a model back inside the check, which is the thing being
    checked.
    """
    register = Register()
    register.add(
        "dropped clause",
        claims=lambda r: any(
            #: GERUNDS WERE MISSING AND IT COST THREE ROWS. Measured 2026-09-07:
            #: replies reading "By removing the ... clause" and "By dropping the
            #: ... condition" matched nothing here, so `void_unless` reported
            #: NO RULE REGISTERED for three of nineteen fabricated verdicts - the
            #: answer that means "nobody checked", about a claim a rule was
            #: sitting right there to check. A closed list is the correct design
            #: and an incomplete closed list still fails closed-ish and quietly.
            w in r for w in ("drops", "dropped", "dropping", "removes", "removed",
                             "removing", "omits", "omitted", "omitting",
                             "loses", "lost", "losing", "strips", "stripped")
        ),
        holds=dropped_clause_named,
    )
    register.add(
        "added word",
        claims=lambda r: any(w in r for w in ("adds", "added", "adding", "introduces", "introduced",
                                              "introducing", "inserts", "inserted", "inserting")),
        holds=added_word,
    )
    register.add(
        "changed number",
        claims=lambda r: any(
            w in r for w in ("changes the number", "changed the number", "different number", "figure", "amount")
        ),
        holds=changed_number,
    )
    register.add(
        "inverted negation",
        claims=lambda r: any(
            w in r for w in ("negation", "inverts", "inverted", "reverses", "reversed", "opposite")
        ),
        holds=inverted_negation,
    )
    return register


def void_unless(verdicts: Iterable[Verdict], register: Register | None = None) -> list[Ruling]:
    """Rule on every verdict. Nothing stands until its reason is re-derived."""
    register = register or standard_register()
    return [register.check(v) for v in verdicts]


def account(rulings: list[Ruling]) -> str:
    """The sentence a record should carry, with the denominator.

    Voided verdicts are counted WITH the total, because "19 were void" and "19
    of 72 were void" are different claims and only the second is a measurement.
    """
    if not rulings:
        return "no verdicts were ruled on"
    void = [r for r in rulings if r.void]
    unruled = [r for r in void if r.why == NO_RULE]
    return (
        "{void} of {total} verdicts are void; {unruled} of those because no rule "
        "was registered for the reason given, which is not the same as a reason "
        "that failed its rule".format(
            void=len(void), total=len(rulings), unruled=len(unruled)
        )
    )
