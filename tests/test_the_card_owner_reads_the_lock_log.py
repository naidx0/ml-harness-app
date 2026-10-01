"""Planted case for the lock log: a release whose held seconds disagree.

    a release line whose held seconds disagree with the take and release stamps
    is reported, not trusted

The card's night was reconstructed from commit bodies and lane pages, and two of
its holders were wrong as a result. This log exists so a reader never has to do
that again - and the number the writer puts in it is checked against the two
stamps rather than believed, because the writer is exactly what got the last
lock-line format wrong.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import support

log = support.import_file(
    "card_owner_the_lock_log", support.REPO_ROOT / "card_owner" / "the_lock_log.py"
)

TOOK = "2026-09-06T01:37:29Z"
TOOK_AT = datetime(2026, 9, 6, 1, 37, 29, tzinfo=timezone.utc)
A_TAKE = (
    f"lane=mlharness since={TOOK} pid=4264 born=134331322491779160 "
    "what=the direct sentinel-N pair, 144 calls"
)


def a_log(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def released(at: str, held: int, lane: str = "mlharness") -> str:
    return f"released lane={lane} at={at} held={held}"


class AReleaseThatDisagreesWithTheStampsIsReportedTest(unittest.TestCase):
    """THE PLANTED CASE."""

    def test_a_held_that_matches_the_stamps_is_not_reported(self):
        """A rule that complained about everything would pass the test below."""
        holders = log.the_holders(a_log(A_TAKE, released("2026-09-06T03:40:36Z", 7387)))
        self.assertEqual(len(holders), 1)
        self.assertIsNone(log.why_this_release_cannot_be_trusted(holders[0]))
        self.assertAlmostEqual(holders[0].measured_held, 7387, places=0)

    def test_a_held_that_disagrees_is_reported_with_all_three_numbers(self):
        holders = log.the_holders(a_log(A_TAKE, released("2026-09-06T03:40:36Z", 3600)))
        said = log.why_this_release_cannot_be_trusted(holders[0])
        self.assertIsNotNone(said)
        self.assertIn("held=3600s", said)
        self.assertIn("7387s", said)
        self.assertIn("3787s", said)

    def test_neither_number_is_preferred_over_the_other(self):
        """Reported, NOT trusted, and not silently corrected: the reader does
        not know which of the three is wrong."""
        holders = log.the_holders(a_log(A_TAKE, released("2026-09-06T03:40:36Z", 3600)))
        holder = holders[0]
        self.assertEqual(holder.claimed_held, 3600)
        self.assertAlmostEqual(holder.measured_held, 7387, places=0)
        self.assertIn("Neither number is preferred", log.why_this_release_cannot_be_trusted(holder))

    def test_the_stamps_own_rounding_is_not_a_disagreement(self):
        """Whole-second stamps can put a 4.9 s span a second apart. One second
        of slack is the stamps' resolution, not tolerance for bad arithmetic."""
        took = A_TAKE.replace(TOOK, "2026-09-06T01:00:00Z")
        holders = log.the_holders(a_log(took, released("2026-09-06T01:00:10Z", 9)))
        self.assertIsNone(log.why_this_release_cannot_be_trusted(holders[0]))
        holders = log.the_holders(a_log(took, released("2026-09-06T01:00:10Z", 8)))
        self.assertIsNotNone(log.why_this_release_cannot_be_trusted(holders[0]))

    def test_a_release_before_its_take_is_named_as_such(self):
        holders = log.the_holders(a_log(A_TAKE, released("2026-09-06T00:00:00Z", 100)))
        said = log.why_this_release_cannot_be_trusted(holders[0])
        self.assertIn("BEFORE the take stamp", said)

    def test_an_unreadable_take_stamp_leaves_the_claim_unchecked_not_accepted(self):
        broken = A_TAKE.replace(TOOK, "yesterday-ish")
        holders = log.the_holders(a_log(broken, released("2026-09-06T03:40:36Z", 7387)))
        said = log.why_this_release_cannot_be_trusted(holders[0])
        self.assertIn("nothing checks it", said)
        self.assertIn("not counted", said)


class AReleaseIsNeverReadAsATakeTest(unittest.TestCase):
    """MEASURED ON REAL DATA another lane wrote, within an hour of the format
    being agreed:

        released lane=sequence at=2026-09-06T08:30:45Z held=60 stale=holder-gone

    `A_RELEASE` ended at `held=(\S+)\s*$`, so the trailing `stale=holder-gone`
    made it fail to match - and the line then fell through to the take branch,
    which asks only for a `lane=` field. Every release line has one. SO A
    RELEASE WAS READ AS A TAKE, and the real ledger reported THREE open holders
    where one was open.

    That is this module's own failure mode arriving through the module: a reader
    that says three lanes hold one card is worse than no reader at all.
    """

    A_REAL_RELEASE_WITH_AN_EXTRA_FIELD = (
        "released lane=sequence at=2026-09-06T08:30:45Z held=60 stale=holder-gone"
    )

    def test_a_release_with_a_trailing_field_is_still_a_release(self):
        holders = log.the_holders(
            a_log(
                "lane=sequence since=2026-09-06T08:29:46Z pid=24340 what=x",
                self.A_REAL_RELEASE_WITH_AN_EXTRA_FIELD,
            )
        )
        self.assertEqual(len(holders), 1)
        self.assertFalse(holders[0].is_open, "the release was read as a take")
        self.assertEqual(holders[0].claimed_held, 60)

    def test_it_does_not_invent_a_holder(self):
        """The count is the thing that went wrong in the wild."""
        holders = log.the_holders(a_log(self.A_REAL_RELEASE_WITH_AN_EXTRA_FIELD))
        self.assertEqual(
            sum(1 for h in holders if h.took is not None),
            0,
            "a release line produced a holder with a take time",
        )

    def test_a_release_that_cannot_be_parsed_at_all_is_still_not_a_take(self):
        """THE FIX THAT MATTERS. Its first word says what it is, so an
        unreadable release is recorded as unreadable rather than becoming a
        holder nobody wrote. Fail towards the reading that cannot invent one."""
        for broken in (
            "released lane=sequence",
            "released something went wrong here",
            "released lane=x at=nonsense",
        ):
            with self.subTest(line=broken):
                holders = log.the_holders(a_log(broken))
                self.assertEqual(len(holders), 1)
                self.assertIsNone(holders[0].took, "an unreadable release took the card")
                self.assertNotEqual(holders[0].lane, "sequence")

    def test_a_take_is_still_a_take(self):
        """A rule that read everything as a release would pass the tests above."""
        holders = log.the_holders(a_log(A_TAKE))
        self.assertTrue(holders[0].is_open)
        self.assertEqual(holders[0].lane, "mlharness")
        self.assertIsNotNone(holders[0].took)

    def test_the_real_ledgers_shape_reads_as_one_open_holder(self):
        """The interleaving that exposed it: takes and releases from one lane in
        quick succession, one of them carrying the extra field."""
        holders = log.the_holders(
            a_log(
                "lane=sequence since=2026-09-06T08:23:15Z pid=28548 what=a",
                "released lane=sequence at=2026-09-06T08:28:16Z held=301",
                "lane=sequence since=2026-09-06T08:29:46Z pid=24340 what=b",
                self.A_REAL_RELEASE_WITH_AN_EXTRA_FIELD,
                "lane=sequence since=2026-09-06T08:30:46Z pid=17884 what=c",
            )
        )
        self.assertEqual(len(holders), 3)
        self.assertEqual(sum(1 for h in holders if h.is_open), 1)
        self.assertIn("1 still open", log.the_holders_line(holders))


class AnOpenHolderIsUnknownNotZeroTest(unittest.TestCase):
    """The card is either still held or the holder died. Both are unknown."""

    def test_a_take_with_no_release_is_open(self):
        holders = log.the_holders(a_log(A_TAKE))
        self.assertTrue(holders[0].is_open)
        self.assertIsNone(holders[0].measured_held)

    def test_an_open_holder_is_not_reported_as_untrustworthy(self):
        """It has made no claim to disbelieve."""
        self.assertIsNone(log.why_this_release_cannot_be_trusted(log.the_holders(a_log(A_TAKE))[0]))

    def test_the_count_line_never_hides_an_open_holder_in_a_total(self):
        holders = log.the_holders(
            a_log(A_TAKE, released("2026-09-06T03:40:36Z", 7387), A_TAKE)
        )
        said = log.the_holders_line(holders)
        # Two holders, not three: the release closes the first take, and the
        # second take is the open one. A release line is not itself a holder.
        self.assertIn("holders 2", said)
        self.assertIn("1 still open", said)
        self.assertIn("are not zero", said)

    def test_two_takes_and_one_release_leaves_the_first_open(self):
        """The log does not say which was released, so nothing is invented to
        make the pairing tidy."""
        holders = log.the_holders(
            a_log(A_TAKE, A_TAKE, released("2026-09-06T03:40:36Z", 7387))
        )
        self.assertEqual(len(holders), 2)
        self.assertTrue(holders[0].is_open)
        self.assertFalse(holders[1].is_open)


class TheTwoLinesAreWhatTheProtocolAsksForTest(unittest.TestCase):
    def test_the_take_line_is_the_lock_line_verbatim(self):
        """So the log and the lock file cannot become two accounts of one take."""
        self.assertEqual(log.the_take_line(A_TAKE + "\n"), A_TAKE)

    def test_the_release_line_matches_the_protocol(self):
        said = log.the_release_line("mlharness", TOOK_AT + timedelta(seconds=7387), 7387)
        self.assertEqual(said, "released lane=mlharness at=2026-09-06T03:40:36Z held=7387")

    def test_what_it_writes_is_what_it_reads(self):
        """The round trip, which is the only thing that makes the pair of
        functions a protocol rather than two guesses."""
        written = a_log(
            log.the_take_line(A_TAKE),
            log.the_release_line("mlharness", TOOK_AT + timedelta(seconds=7387), 7387),
        )
        holders = log.the_holders(written)
        self.assertEqual(len(holders), 1)
        self.assertFalse(holders[0].is_open)
        self.assertIsNone(log.why_this_release_cannot_be_trusted(holders[0]))

    def test_a_lock_line_in_either_born_format_still_reads(self):
        """The protocol page accepts ISO and FILETIME for born, after this lane
        wrote one format while its own page asked for the other."""
        for born in ("134331322491779160", "2026-09-06T01:37:29Z"):
            with self.subTest(born=born):
                line = f"lane=mlharness since={TOOK} pid=4264 born={born} what=x"
                holders = log.the_holders(a_log(line))
                self.assertEqual(holders[0].lane, "mlharness")
                self.assertEqual(holders[0].took, TOOK_AT)

    def test_a_line_with_a_host_field_still_reads(self):
        """`host=` is queued for this line; the reader must not break when it
        arrives, and a line without it is this host."""
        line = f"lane=mlharness host=DESKTOP since={TOOK} pid=4264 what=x"
        holders = log.the_holders(a_log(line))
        self.assertEqual(holders[0].lane, "mlharness")
        self.assertEqual(holders[0].took, TOOK_AT)


class TheLogIsTheRecordOfHoldersNotTheCommitsTest(unittest.TestCase):
    """The card's night had to be reconstructed from commit bodies, and two
    holders came out wrong. This reads holders from the log alone."""

    def test_several_lanes_interleaved_are_each_paired_to_their_own_release(self):
        text = a_log(
            "lane=mlharness since=2026-09-06T01:00:00Z pid=1 what=a",
            "lane=sequence since=2026-09-06T02:00:00Z pid=2 what=b",
            released("2026-09-06T02:30:00Z", 1800, lane="sequence"),
            released("2026-09-06T03:00:00Z", 7200, lane="mlharness"),
        )
        holders = log.the_holders(text)
        self.assertEqual([h.lane for h in holders], ["mlharness", "sequence"])
        self.assertEqual([h.is_open for h in holders], [False, False])
        for holder in holders:
            self.assertIsNone(log.why_this_release_cannot_be_trusted(holder))

    def test_a_release_with_no_take_is_kept_and_not_dropped(self):
        """The take may predate the log. Dropping the release would lose the
        only evidence the holder existed."""
        holders = log.the_holders(a_log(released("2026-09-06T03:00:00Z", 60)))
        self.assertEqual(len(holders), 1)
        self.assertIsNone(holders[0].took)
        self.assertIn("nothing checks it", log.why_this_release_cannot_be_trusted(holders[0]))

    def test_an_empty_log_is_no_holders_not_an_error(self):
        for text in ("", "\n\n", None):
            with self.subTest(text=text):
                self.assertEqual(log.the_holders(text), [])
        self.assertIn("holders 0", log.the_holders_line([]))


if __name__ == "__main__":
    unittest.main()
