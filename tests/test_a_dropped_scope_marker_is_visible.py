"""The decidable subset of the one class the diff gate cannot settle alone.

`THE-JUDGE.md` records that the gate cannot decide whether a genuine content
removal widened a promise. A removal that drops a scope marker — a time bound, a
quantity cap, an exclusivity, a condition, a hedge, a named party, a day/time
window — widens it by construction, and that is a question about two strings.

Measured 2026-09-05, `runs/judge-scope-markers/results.jsonl`: 14 of 16 removals
reaching the diff carry a dropped marker, 0 of 72 non-degradations and 0 of 34
surface rewrites fire, and **5 of 5** of the judge's known flips on removals are
marker-shaped.
"""

from __future__ import annotations

import json
import unittest

import support

markers = support.import_file(
    "a_dropped_scope_marker",
    support.REPO_ROOT / "scripts" / "a_dropped_scope_marker.py",
)
plant = support.import_file(
    "plant_the_defects", support.REPO_ROOT / "scripts" / "plant_the_defects.py"
)
overs = support.import_file(
    "over_promise_deletions",
    support.REPO_ROOT / "scripts" / "over_promise_deletions.py",
)

_ANSWERS = support.REPO_ROOT / "runs" / "honest-path" / "train.jsonl"
REAL = (
    [
        json.loads(line)["response"]
        for line in _ANSWERS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if _ANSWERS.is_file()
    else []
)
NEEDS_THE_REAL_ANSWERS = unittest.skipUnless(
    REAL, f"{_ANSWERS} is not in this checkout (runs/ is gitignored)"
)


class ADroppedMarkerIsSeenTest(unittest.TestCase):
    def test_a_time_bound_that_went(self):
        self.assertIn(
            "time bound",
            markers.the_markers_this_rewrite_dropped(
                "You can return it within 30 days for credit.",
                "You can return it for credit.",
            ),
        )

    def test_a_quantity_cap_that_went(self):
        self.assertIn(
            "quantity cap",
            markers.the_markers_this_rewrite_dropped(
                "We do, up to two boxes at a time.", "We do."
            ),
        )

    def test_a_day_window_that_went_despite_its_capital_letter(self):
        """THE BUG THIS ROW EXISTS FOR. `_normalised` lowercases and the
        patterns are written with capitals, so matching without the
        case-insensitive flag made `on Sundays` and `Tuesday to Saturday`
        unmatchable - two real removals read as carrying no marker at all."""
        self.assertIn(
            "day/time window",
            markers.the_markers_this_rewrite_dropped(
                "The multi storey is two minutes away and free on Sundays.",
                "The multi storey is two minutes away and free.",
            ),
        )

    def test_the_reason_names_the_family(self):
        said = markers.why_this_removal_widens_the_promise(
            "10 percent with a valid student card, in store only.",
            "10 percent, in store only.",
        )
        self.assertIsNotNone(said)
        self.assertIn("named party", said)


class NotationIsNotADroppedMarkerTest(unittest.TestCase):
    """The first version failed its own preregistration here: the day/time
    family matches digits, so rewriting `between 10 and 5` as `between ten and
    5` made the marker vanish and the check fired on a row where nothing was
    removed."""

    def test_a_numeral_written_as_a_word_does_not_fire(self):
        self.assertEqual(
            markers.the_markers_this_rewrite_dropped(
                "it is answered between 10 and 5, Tuesday to Saturday",
                "it is answered between ten and 5, Tuesday to Saturday",
            ),
            [],
        )

    def test_nothing_changed_drops_nothing(self):
        text = "We hold reservations for 48 hours under your name."
        self.assertEqual(markers.the_markers_this_rewrite_dropped(text, text), [])


@NEEDS_THE_REAL_ANSWERS
class TheMeasuredNumbersAreLockedTest(unittest.TestCase):
    def test_every_family_is_used_by_at_least_two_answers(self):
        """A family present in one answer is a coincidence, not a vocabulary -
        and the list's whole claim is that it came from this corpus."""
        counts = markers.the_family_counts_over(sorted(set(REAL)))
        for name, used in counts.items():
            with self.subTest(family=name):
                self.assertGreaterEqual(used, 2, f"{name} appears in {used} answers")

    def test_it_fires_on_no_surface_rewrite(self):
        """A rule that fires everywhere decides nothing."""
        fired = [
            k for k in plant.keeps_that_are_not_deletions(REAL, per_type=99)
            if markers.the_markers_this_rewrite_dropped(k["chosen"], k["rejected"])
        ]
        self.assertEqual(fired, [])

    def test_it_fires_on_no_number_negation_or_entity_substitution(self):
        """Measured: 0 of 19 number rows, 0 of 6 negation rows, 0 of 3 entity
        rows. Those substitutions leave every marker where it was."""
        fired = [
            p for p in plant.plant(REAL, per_type=99)
            if p["edit_type"] in ("number", "negation", "entity")
            and markers.the_markers_this_rewrite_dropped(p["chosen"], p["rejected"])
        ]
        self.assertEqual(fired, [])

    def test_one_unit_row_fires_and_the_reason_is_recorded_as_an_accident(self):
        """AN ACCIDENT, NAMED RATHER THAN CLAIMED AS A FEATURE. `for seven
        days` -> `for seven weeks` fires the time-bound family, and the widened
        bound IS a real over-promise - but the check sees it only because the
        pattern's alternation lists `days` and not `weeks`. Add `weeks` to the
        pattern and this stops firing, which would make a genuine widening
        invisible.

        So it is right for the wrong reason, 1 of 11 unit rows, and this test
        holds the number rather than the story. A later version that catches
        unit widening ON PURPOSE should change this test and say so.
        """
        fired = [
            p for p in plant.plant(REAL, per_type=99)
            if p["edit_type"] == "unit"
            and markers.the_markers_this_rewrite_dropped(p["chosen"], p["rejected"])
        ]
        self.assertEqual(len(fired), 1, [f["edit"] for f in fired])
        self.assertEqual(fired[0]["edit"], "unit 'days' -> 'weeks'")

    def test_most_over_promise_deletions_carry_a_marker(self):
        """14 of 16 when measured. The two misses are a bare price and a
        threshold - both real restrictions with no family in the list, which is
        why coverage is a LOWER bound on what a marker check could decide."""
        deletions = overs.the_deletion_pairs(REAL)
        carried = [
            d for d in deletions
            if markers.the_markers_this_rewrite_dropped(d["chosen"], d["rejected"])
        ]
        self.assertGreaterEqual(len(carried) / len(deletions), 0.70)


if __name__ == "__main__":
    unittest.main()
