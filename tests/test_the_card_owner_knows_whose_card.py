"""Planted cases for the host field, built with one machine on the record.

    a host field on the per-call record and on the lock line (host=<machine
    name> after lane=), written by every writer from now, the reader accepting
    lines without it as this host; a lock file per card (gpu.lock for this
    machine, gpu.<host>.lock for another) with the card owner's reader taking a
    host argument and refusing to read a lock for a card it would not use; and a
    host table in the provider configuration with this machine as its only row

Nothing here needs a second host to exist. The refusal is tested against a host
name that is not this one, which is a string, not a machine.
"""

from __future__ import annotations

import unittest

import support

host = support.import_file(
    "card_owner_the_host", support.REPO_ROOT / "card_owner" / "the_host.py"
)
log = support.import_file(
    "card_owner_the_lock_log", support.REPO_ROOT / "card_owner" / "the_lock_log.py"
)

ELSEWHERE = "SOME-OTHER-BOX"
A_LINE = (
    "lane=mlharness since=2026-09-06T01:37:29Z pid=4264 "
    "born=134331322491779160 what=the sentinel-N pair"
)


class ALineWithoutTheFieldIsThisHostTest(unittest.TestCase):
    """RULE 1. Every line already in the ledger was written by this machine, so
    reading them as this host's is what they MEAN, not a default that guesses."""

    def test_a_line_with_no_host_field_reads_as_this_machine(self):
        self.assertEqual(host.the_host_this_line_is_about(A_LINE), host.this_host())

    def test_a_line_that_names_a_host_keeps_it(self):
        line = host.with_the_host_field(A_LINE, ELSEWHERE)
        self.assertEqual(host.the_host_this_line_is_about(line), ELSEWHERE)

    def test_an_empty_or_missing_line_still_answers_this_host(self):
        for line in ("", None, "nonsense"):
            with self.subTest(line=line):
                self.assertEqual(
                    host.the_host_this_line_is_about(line), host.this_host()
                )

    def test_this_host_is_never_blank(self):
        """A blank host would make every lock file `gpu..lock` and every
        comparison true."""
        self.assertTrue(host.this_host().strip())


class TheFieldGoesAfterLaneAndOnlyOnceTest(unittest.TestCase):
    def test_it_lands_directly_after_lane(self):
        line = host.with_the_host_field(A_LINE)
        self.assertIn(f"lane=mlharness host={host.this_host()} since=", line)

    def test_the_rest_of_the_line_is_untouched(self):
        line = host.with_the_host_field(A_LINE)
        for field in ("since=2026-09-06T01:37:29Z", "pid=4264", "born=1343313224917791"):
            self.assertIn(field, line)
        self.assertTrue(line.endswith("what=the sentinel-N pair"))

    def test_a_line_that_already_has_one_is_not_given_a_second(self):
        """Two host= fields on one line is a line no reader can resolve."""
        once = host.with_the_host_field(A_LINE, ELSEWHERE)
        twice = host.with_the_host_field(once, "A-THIRD-BOX")
        self.assertEqual(once, twice)
        self.assertEqual(twice.count("host="), 1)

    def test_a_line_with_no_lane_is_returned_unchanged(self):
        """The field is defined as going after `lane=`. With no lane there is no
        defined place for it, and inventing one would write a line the protocol
        does not describe."""
        self.assertEqual(host.with_the_host_field("garbage"), "garbage")

    def test_the_lock_log_reader_still_reads_a_line_carrying_it(self):
        """The field must not break the reader that already exists."""
        holders = log.the_holders(host.with_the_host_field(A_LINE) + "\n")
        self.assertEqual(len(holders), 1)
        self.assertEqual(holders[0].lane, "mlharness")
        self.assertIsNotNone(holders[0].took)


class OneLockFilePerCardTest(unittest.TestCase):
    """RULE 2. The host is in the NAME, so a reader knows whose card it is
    before it opens anything."""

    def test_this_machine_keeps_the_name_it_already_has(self):
        """Every existing line, script and habit still works."""
        card = host.the_card_of()
        self.assertEqual(card.lock_name, "gpu.lock")
        self.assertTrue(card.is_here)
        self.assertEqual(card.host, host.this_host())

    def test_another_host_gets_its_own_file(self):
        card = host.the_card_of(ELSEWHERE)
        self.assertEqual(card.lock_name, f"gpu.{ELSEWHERE}.lock")
        self.assertFalse(card.is_here)

    def test_naming_this_machine_explicitly_is_still_this_machine(self):
        """Asking for THIS host by name must not invent a second file for the
        one card that exists."""
        self.assertEqual(host.the_card_of(host.this_host()).lock_name, "gpu.lock")

    def test_the_comparison_ignores_case(self):
        """Windows reports the name in upper case and people type it in lower."""
        self.assertEqual(host.the_card_of(host.this_host().lower()).lock_name, "gpu.lock")
        self.assertEqual(host.the_card_of(host.this_host().upper()).lock_name, "gpu.lock")

    def test_an_empty_host_is_this_machine_not_a_file_called_gpu_dot_lock(self):
        for given in ("", "   ", None):
            with self.subTest(given=given):
                self.assertEqual(host.the_card_of(given).lock_name, "gpu.lock")


class OneMachineWithTwoTrueNamesTest(unittest.TestCase):
    """MEASURED 2026-09-06 on this machine, and the reason the comparison is
    membership rather than equality:

        COMPUTERNAME          29733
        platform.node()       DESKTOP-AKGMH12
        socket.gethostname()  DESKTOP-AKGMH12

    Both are stable and both are real - the NetBIOS name and the DNS hostname
    differ here. A single name compared with `==` would make a lane writing
    `host=DESKTOP-AKGMH12` and a lane reading `host=29733` disagree about which
    machine they are on, and refuse each other's locks on one card: the exact
    collision the host field exists to prevent, produced by the host field.
    """

    def test_every_name_this_machine_answers_to_resolves_to_its_own_card(self):
        for name in host.the_names_of_this_host():
            with self.subTest(name=name):
                self.assertEqual(host.the_card_of(name).lock_name, "gpu.lock")
                self.assertIsNone(host.why_this_lock_is_not_ours("gpu.lock", name))

    def test_the_name_it_writes_is_one_of_the_names_it_answers_to(self):
        """Otherwise it would write lines it would not recognise as its own."""
        self.assertIn(host.this_host().casefold(), host.the_names_of_this_host())

    def test_it_answers_to_more_than_one_name_here_or_says_why_not(self):
        """Not a requirement - a machine may have one name - but if this ever
        collapses to one on this box, the measurement above has changed and the
        docstring is stale."""
        names = host.the_names_of_this_host()
        self.assertGreaterEqual(len(names), 1)
        self.assertTrue(all(name == name.casefold() for name in names))

    def test_a_name_no_source_reports_is_still_another_host(self):
        """Membership must not become "anything is us"."""
        self.assertNotIn(ELSEWHERE.casefold(), host.the_names_of_this_host())
        self.assertEqual(host.the_card_of(ELSEWHERE).lock_name, f"gpu.{ELSEWHERE}.lock")

    def test_no_name_is_blank(self):
        self.assertTrue(all(name.strip() for name in host.the_names_of_this_host()))


class AReaderRefusesACardItWouldNotUseTest(unittest.TestCase):
    """RULE 3, and the heart of it. A reader that opened another machine's lock
    and reported "free" would hand out a card it cannot see."""

    def test_our_own_lock_is_not_refused(self):
        self.assertIsNone(host.why_this_lock_is_not_ours("gpu.lock"))

    def test_another_hosts_lock_is_refused(self):
        said = host.why_this_lock_is_not_ours(f"gpu.{ELSEWHERE}.lock")
        self.assertIsNotNone(said)
        self.assertIn(f"gpu.{ELSEWHERE}.lock", said)
        self.assertIn("gpu.lock", said)

    def test_the_refusal_says_it_is_not_reporting_the_card_free(self):
        """The failure this exists to prevent, named in the sentence."""
        said = host.why_this_lock_is_not_ours(f"gpu.{ELSEWHERE}.lock")
        self.assertIn("not reported free", said)
        self.assertIn("not knowable from here", said)

    def test_asking_about_another_host_refuses_this_machines_lock(self):
        """The refusal runs both ways: reading OUR lock while asking about
        THEIR card is the same mistake mirrored."""
        said = host.why_this_lock_is_not_ours("gpu.lock", ELSEWHERE)
        self.assertIsNotNone(said)
        self.assertIn(ELSEWHERE, said)

    def test_the_refusal_is_separate_from_the_reading(self):
        """So a caller cannot print one while meaning the other - the same
        separation `the_record` and `the_window` already keep."""
        self.assertIsNone(host.why_this_lock_is_not_ours("gpu.lock"))
        self.assertIsInstance(host.the_card_of(ELSEWHERE), tuple)


class TheHostTableHasOneRowAndIsATableTest(unittest.TestCase):
    """A second host is a ROW, not a rewrite of everything that assumed one
    card. That is the whole reason to write it with one machine."""

    def test_one_row_this_machine(self):
        table = host.the_host_table()
        self.assertEqual(len(table), 1)
        self.assertEqual(table[0]["host"], host.this_host())
        self.assertEqual(table[0]["lock"], "gpu.lock")
        self.assertTrue(table[0]["is_this_machine"])

    def test_the_row_says_how_it_knows(self):
        """Provenance, as every other measured field on this project carries."""
        self.assertTrue(table_how().startswith("MEASURED"))

    def test_it_claims_no_host_it_cannot_see(self):
        self.assertNotIn(ELSEWHERE, [row["host"] for row in host.the_host_table()])


def table_how() -> str:
    return host.the_host_table()[0]["how"]


if __name__ == "__main__":
    unittest.main()
