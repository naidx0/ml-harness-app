"""A model-driven tool call is the one with no `driven_by` on its event.

## Why this needs a test of its own

ML BUILD measured a fourth state on the stranger walk: the probe reports
`tool_calling: "yes"`, the turn ends with `tool_calls_json` null, and Composer
warns only on `"no"` - so a 0.5B that names the harness's tools in PROSE and
calls none reaches the person as a confident answer with no signal at all.

Any reading that separates "the model called nothing" from "nothing was called"
has to know which calls were the model's. Today that is decided by an ABSENCE:

    conductor.py  writes  driven_by: "harness"   (the standing-brief calls)
    main.py       writes  driven_by: "user"      (a person pressing a button)
    a model call  writes  NOTHING

An absence is a load-bearing signal that nothing announces. Add a
`driven_by: "model"` for tidiness one afternoon - a reasonable-looking change,
and the obvious one for anybody who meets this shape without the history - and
every such reading inverts: model calls stop being counted as the model's, the
banner goes quiet, and the fourth state becomes invisible again while the
tests that matter still pass.

So this file fails the day that happens, and says why in its own failure text.

## What is asserted

The two writers, by reading the source rather than by trusting a docstring; the
model path, by driving `_run_tool` and reading the event back out of the log.
The third is the one that matters: a claim about a shape a reader cannot see is
worth less than one taken off a row the product actually wrote.

## What this does not do

It does not assert anything about the banner or the reading that will consume
this. Those are a frontend change and this checkout has no `tsc`; a test here
claiming to cover them would be the "partial result wearing a pass" this
repository refuses everywhere else. It pins the CONTRACT, so whoever lands the
reading lands it on something that cannot move under them.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import support

from app import events


REPO = Path(__file__).resolve().parents[1]

#: The one word that must never appear as a `driven_by` value.
THE_VALUE_THAT_WOULD_INVERT_EVERY_READING = "model"


def driver_sites(path: Path) -> list[str]:
    """Every literal `driven_by` value this file writes, ONE PER SITE.

    A LIST AND NOT A SET, and mutation is why. The first version returned a
    set, so deleting one of the conductor's two harness-marked calls left
    `{"harness"}` unchanged and the suite green - a test that could not tell
    one writer from two, in a file whose whole subject is which writers exist.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    return re.findall(r'"driven_by":\s*"([a-z]+)"', text)


def written_drivers(path: Path) -> set[str]:
    return set(driver_sites(path))


class TheTwoWritersAreTheOnlyWritersTest(unittest.TestCase):
    #: Counted, not just named. The numbers are small and knowable, and a
    #: writer appearing or vanishing is the change this file exists to notice.
    THE_CONDUCTORS_HARNESS_CALLS = 2
    THE_APIS_USER_CALLS = 2

    def test_the_conductor_writes_harness_and_only_harness(self):
        sites = driver_sites(REPO / "app" / "conductor.py")
        self.assertEqual({"harness"}, set(sites))
        self.assertEqual(
            self.THE_CONDUCTORS_HARNESS_CALLS, len(sites),
            "the number of harness-driven calls changed. If one was removed, a "
            "reading that counts model calls by absence now counts that one "
            "too; if one was added, say so here.",
        )

    def test_the_api_writes_user_and_only_user(self):
        sites = driver_sites(REPO / "app" / "main.py")
        self.assertEqual({"user"}, set(sites))
        self.assertEqual(self.THE_APIS_USER_CALLS, len(sites))

    def test_nothing_anywhere_writes_model(self):
        """THE ASSERTION THIS FILE EXISTS FOR.

        `driven_by: "model"` is the tidy-looking change that silently inverts
        every reading built on the absence. It is refused here rather than
        discovered later by a banner that stopped appearing.
        """
        for path in sorted((REPO / "app").rglob("*.py")):
            with self.subTest(file=path.relative_to(REPO).as_posix()):
                self.assertNotIn(
                    THE_VALUE_THAT_WOULD_INVERT_EVERY_READING,
                    written_drivers(path),
                    f"{path.name} writes driven_by='model'. Every reading that "
                    "separates a model's calls from the harness's does it by "
                    "the ABSENCE of this key - see this file's docstring. "
                    "Adding the value does not make the data tidier; it makes "
                    "the fourth state invisible again.",
                )


class AModelCallCarriesNoDriverTest(unittest.TestCase):
    """Read off a row the product wrote, not off a docstring."""

    def setUp(self):
        support.sandbox(self)
        self.thread = int(events.create_thread("a turn", None)["id"])

    def a_model_call(self) -> dict:
        """The event `_run_tool` writes for a call the MODEL asked for."""
        from app import conductor

        class ACall:
            id = "call_1"
            name = "read_the_standing_constraints"
            arguments: dict = {}

        list(
            conductor._run_tool(
                self.thread,
                [],
                ACall(),
                memo={},
                offered=frozenset({"read_the_standing_constraints"}),
            )
        )
        row = events.latest("tool.call", self.thread)
        self.assertIsNotNone(row, "no tool.call was written")
        return row

    def test_the_event_has_no_driven_by_key_at_all(self):
        """NOT `None` - ABSENT. A key present and null is a value somebody can
        read as a claim, and a row written before this feature existed would
        not have it either."""
        payload = self.a_model_call().get("payload") or {}
        self.assertNotIn("driven_by", payload)

    def test_the_harness_driven_call_does_carry_one(self):
        """THE CONTROL, and it is what makes the absence mean something. If
        nothing ever wrote the key, its absence would distinguish nothing."""
        events.append(
            "tool.call",
            {"id": "harness_x", "name": "x", "arguments": {}, "driven_by": "harness"},
            thread_id=self.thread,
        )
        row = events.latest("tool.call", self.thread)
        self.assertEqual("harness", (row.get("payload") or {}).get("driven_by"))


if __name__ == "__main__":
    unittest.main()
