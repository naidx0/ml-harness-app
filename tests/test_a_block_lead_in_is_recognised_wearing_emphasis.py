"""What counts as the line that introduces a block, pinned.

`conductor._SENTENCE_END` treats a newline as a full stop, so every bullet and
every table row is audited ALONE, stripped of the line that said whose machine
it was. `provenance.leads_a_block` is the whole repair: it carries the lead-in
forward so a row can be read under the sentence that introduced it.

IT WAS NEVER TESTED. An adversary put it plainly: `leads_a_block` appeared
exactly once in the three provenance test files, as a CALL inside `audit()`.
Nothing pinned what counts as a lead-in - which is how a fix resting entirely
on it shipped unmeasured, and how it turned out to be keyed on a single
unadorned character at end of line.

    'Your system has:'      lead-in     -> '- VRAM: 11 GB' under it is audited
    '**Your system has:**'  NOT lead-in -> the same row reached the user whole

The register is measured, not imagined: `**Training Location:**` is a line from
this product's own harvest of granite4-hermes, one of eleven bold label lines
and five markdown headings in eight hundred harvested lines.

And the inconsistency was internal. `_flatten` already strips emphasis for the
ROW - which is why `**Your VRAM is 10 GB.**` was stopped - and the lead-in one
line above it was tested raw.

## What this file does NOT claim

Closing this bought ZERO extra catches on the harvested corpora: 2 of 112
sibling fabrications and 16 of 163 tempted turns, before and after. The
mechanism is fixed and the bypass is gone, but no harvested turn happened to
put an emphasised lead-in above a fabricated reading. Saying otherwise would be
the overclaim this repository keeps having to retract.
"""

import unittest

from app import conductor, provenance

import support  # noqa: F401  - installs the suite's sandbox fences


class _Ground(provenance.Ground):
    """Nothing ran, nothing on the ledger, the user said nothing, no brief."""

    def __init__(self):
        super().__init__(None)
        self.ran = {}
        self._ledger = {}
        self._said = set()
        self.briefed = set()


#: A row that is a fabricated reading of a declared, inspect-only fact.
ROW = "- VRAM: 11 GB"

#: A lead-in whose CUE is what makes the row above readable. A lead-in lends
#: its cue and nothing else - not its numbers, not its instrument.
CUED = "According to the hardware inspection, your system has:"


def reaches_the_user(*lines) -> bool:
    """Drive the REAL sentry over a block, in order, as a turn arrives."""
    sentry = conductor._Sentry(conductor._Standing(None), _Ground())
    return not any(sentry._refuses(line) for line in lines)


class ALeadInIsStillALeadInWearingEmphasisTest(unittest.TestCase):
    def test_the_plain_colon_is_a_lead_in(self):
        """The control. If this ever fails, the rest of the file proves nothing."""
        self.assertTrue(provenance.leads_a_block("Your system has:"))
        self.assertFalse(reaches_the_user(CUED, ROW))

    def test_bold_italic_and_code_do_not_disarm_it(self):
        for wrapped in (
            f"**{CUED}**",
            f"*{CUED}*",
            f"`{CUED}`",
            f"__{CUED}__",
        ):
            with self.subTest(lead_in=wrapped):
                self.assertTrue(provenance.leads_a_block(wrapped))
                self.assertFalse(reaches_the_user(wrapped, ROW))

    def test_a_markdown_heading_introduces_a_block(self):
        """A heading does a colon's job and carries no colon."""
        for heading in ("## According to the hardware inspection",
                        "### According to the hardware inspection",
                        "# According to the hardware inspection"):
            with self.subTest(heading=heading):
                self.assertTrue(provenance.leads_a_block(heading))

    def test_a_bold_label_line_introduces_a_block(self):
        """`**Detected configuration**` is a heading in a model avoiding
        heading syntax. Counted in this product's own harvest."""
        self.assertTrue(provenance.leads_a_block("**Detected configuration**"))
        self.assertTrue(provenance.leads_a_block("**Training Location:**"))


class WhatIsNotALeadInTest(unittest.TestCase):
    """The other half. A lead-in test that says yes to everything would pass
    every assertion above and hand every row a cue it was never given."""

    def test_an_emphasised_ordinary_sentence_is_not_a_label(self):
        """Terminal punctuation is what separates a label from a sentence."""
        self.assertFalse(provenance.leads_a_block("**We should train a LoRA.**"))
        self.assertFalse(provenance.leads_a_block("**Do not do that.**"))

    def test_an_ordinary_sentence_is_not_a_lead_in(self):
        self.assertFalse(provenance.leads_a_block("Your system has 11 GB of VRAM"))
        self.assertFalse(provenance.leads_a_block("I ran inspect_hardware"))

    def test_a_hash_that_is_not_a_heading_is_not_a_lead_in(self):
        """`#3` is an issue number and `#!/usr/bin/env` is a shebang."""
        self.assertFalse(provenance.leads_a_block("#3 in the queue"))
        self.assertFalse(provenance.leads_a_block("#!/usr/bin/env python"))

    def test_an_uncued_lead_in_lends_nothing(self):
        """A lead-in carries its CUE across, so one with no cue changes
        nothing - which is why recognising more lead-ins costs no false
        catches. `## Your machine` attributes to no instrument."""
        self.assertTrue(provenance.leads_a_block("## Your machine"))
        self.assertTrue(reaches_the_user("## Your machine", "- Epochs: 3"))


if __name__ == "__main__":
    unittest.main()
