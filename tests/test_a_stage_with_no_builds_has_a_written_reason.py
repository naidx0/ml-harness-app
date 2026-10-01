"""Phase 3's done-condition, made checkable instead of argued.

`docs/PHASES.md` used to say the phase is done when **no stage in either ledger
has zero builds**. Re-measured on 2026-09-09, three stages had zero, and reading
their own recorded reasons one at a time showed that satisfying that condition
would have meant building things the ledger says should not exist:

* AI `stage_5_control_flow` recommends a script, a workflow, or one agent before
  a fleet. Thirteen refusals across the two ledgers DO have builds - so "a
  refusal cannot have a build" is false and is not the reason. The reason is
  narrower: those thirteen are buildable because the harness can MEASURE the
  alternative it recommends. Here the alternative is **code the person writes
  and runs**, and no shell execution is an invariant. `run_the_failures` says so
  itself: it grades answers they hand us rather than driving their system.
* ML `stage_8_offtheshelf_first` is reached only for image and audio data, and
  every scorer sends TEXT to a chat provider. More ways to send text is not a
  way to score audio.

So the condition was replaced, and this file is the replacement:

    A stage may have zero builds ONLY IF every dead outcome in it has a written
    reason in `propose.NOT_COVERED`. No stage may be at zero merely because
    nobody wrote the proposer.

That keeps the pressure exactly where the old condition put it - a stage cannot
quietly sit empty - without paying for coverage with builds nobody should ship.
The day somebody adds an outcome to a zero-build stage and does not say why it
is uncovered, this goes red.
"""

import unittest
from collections import defaultdict
from pathlib import Path

from app import diagnosis
from app.tools import propose

import support  # noqa: F401  - installs the suite's sandbox fences

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Both shipped ledgers. A ledger added here without a `stages:` block would
#: fail to load, which is the point of reading them rather than listing stages.
LEDGERS = (
    ("ML", REPO_ROOT / "docs" / "diagnosis_engine.yaml"),
    ("AI", REPO_ROOT / "docs" / "ledgers" / "ai_engineering.yaml"),
)


def _built_and_dead(spec: diagnosis.Spec):
    """(stage -> built count, stage -> the dead outcomes in it).

    THE ATTRIBUTION RULE, and it is stated because the count depends on it: an
    outcome is counted in EVERY stage whose node states it. Five ML outcomes are
    stated in more than one stage - `REROUTE` in four - and counting each once
    at the first stage that names it hides them.
    """
    built = set(propose.COVERAGE)
    # ONLY OUTCOMES A PERSON CAN ACTUALLY RECEIVE. `declared_outcomes()` is the
    # engine's own set and it excludes `REROUTE`, which the ledger declares
    # `terminal: false` / "continue at another stage". A build for REROUTE is
    # meaningless - the walk simply carries on - and counting it as a dead
    # outcome charges a stage for something no proposer could ever cover.
    # The first version of this file did exactly that and went red on it.
    receivable = spec.declared_outcomes()
    counts: dict[str, int] = defaultdict(int)
    dead: dict[str, set[str]] = defaultdict(set)
    for site in spec.outcome_sites():
        if site.outcome not in receivable:
            continue
        stage = spec.node_stage.get(site.node, "(no stage)")
        if site.outcome in built:
            counts[stage] += 1
        else:
            dead[stage].add(site.outcome)
            counts.setdefault(stage, 0)
    return counts, dead


class AStageWithNoBuildsHasAWrittenReasonTest(unittest.TestCase):
    def test_every_zero_build_stage_says_why_each_outcome_is_uncovered(self):
        for label, path in LEDGERS:
            spec = diagnosis.load_spec(str(path))
            counts, dead = _built_and_dead(spec)
            empty = sorted(s for s, n in counts.items() if n == 0)
            for stage in empty:
                for outcome in sorted(dead[stage]):
                    with self.subTest(ledger=label, stage=stage, outcome=outcome):
                        reason = propose.NOT_COVERED.get(outcome)
                        self.assertTrue(
                            reason and str(reason).strip(),
                            f"{label} {stage} has no builds at all and "
                            f"{outcome} does not say why it is uncovered. A "
                            "stage may sit at zero only when every dead "
                            "outcome in it names what is absent - an "
                            "instrument, a backend, or a judgement that is the "
                            "person's. Write the reason in "
                            "propose.NOT_COVERED, or write the proposer.",
                        )

    def test_the_check_is_looking_at_stages_that_really_are_empty(self):
        """The positive control. Without it this file would pass just as well
        if `_built_and_dead` returned no empty stages for every ledger it was
        ever pointed at - which is the shape of blindness this repository keeps
        finding in its own instruments."""
        found = {}
        for label, path in LEDGERS:
            spec = diagnosis.load_spec(str(path))
            counts, _ = _built_and_dead(spec)
            found[label] = sorted(s for s, n in counts.items() if n == 0)
        self.assertTrue(
            any(found.values()),
            "no stage in either ledger has zero builds, so the assertion above "
            "checked nothing. That is GOOD NEWS about coverage and it means "
            "this file is now vacuous: delete it, or re-read PHASES.md's "
            "Phase 3 done-condition, which this test exists to enforce.",
        )

    def test_a_stage_with_builds_is_not_asked_for_reasons(self):
        """The other half: this must not become 'every dead outcome anywhere
        needs a reason'. 63 outcomes are uncovered and most sit in stages that
        DO offer builds; demanding prose for all of them would be a different
        and much larger promise than the one PHASES.md makes."""
        spec = diagnosis.load_spec(str(LEDGERS[0][1]))
        counts, dead = _built_and_dead(spec)
        with_builds = [s for s, n in counts.items() if n > 0 and dead.get(s)]
        self.assertTrue(
            with_builds,
            "no stage both offers a build and still has dead outcomes, so this "
            "test is not distinguishing the two cases it exists to separate.",
        )


if __name__ == "__main__":
    unittest.main()
