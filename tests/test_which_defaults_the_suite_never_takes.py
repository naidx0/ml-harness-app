"""Which of the product's defaults has no test ever taken - and why that is not
the whole story about `thread_id`.

## The claim this file was written to check, and correct

The eval-set leak came with an account of why the suite could not see it:

> tests always pass a thread_id

Read as an argument-coverage problem that has an obvious fix: find every
parameter that is optional in the product and mandatory in the harness by
convention, and write a test that omits each one. So the enumeration was done,
mechanically, over every defaulted parameter of every function in `app/` against
every call site in `tests/`.

**It says the opposite.** `REGISTRY.call(...)` is reached from 177 places in this
suite and **63 of them omit `thread_id`**. `evidence.record(...)` is reached from
15 and **11 omit it**. The default was not an untrodden path; it was the majority
path. Sixty-three tests took the exact route the bug was on, and every one of
them was green.

That matters because it decides what to fix. If the suite had merely been
missing an omission, adding one test would have been the answer. What actually
happened is that the omission was everywhere and **UNOBSERVABLE**: a sandbox
holds one conversation, and in a database with one conversation "written with no
thread" and "written with this thread" produce identical readings. The blind spot
was not the argument. It was the argument crossed with the fixture - see
`tests/test_the_second_conversation.py`, which is the other half and the half
that can actually see it.

So this file exists to hold two facts that are easy to assume and worth pinning:

**`DEFAULTS_THE_SUITE_TAKES`** - defaults the suite genuinely exercises. Every
entry is a route somebody might otherwise "fix" by adding an omission that
already exists in sixty other places. When one of these stops being exercised,
coverage was lost and this goes red.

**`DEFAULTS_ONCE_NEVER_TAKEN`** - defaults no test took in 1057 of them, with why
each one matters. These are the real instances of the class the finding
described, and both are the same story: the default writes into the user's
checkout, so every author independently decided to pass an explicit path
instead. Nobody wrote that down, so the product shipped a default the suite had
never once run - which is how `security.write_portfile()` came to republish the
repository's real `engine.json`, token and all, the moment one test entered the
app's lifespan without passing `path=`.

The fix for a never-taken default is not a note recording that nobody takes it.
It is a harness in which taking it is harmless - `support.sandbox()` binding the
globals - and a test that takes it and proves so. Those two tests are at the
bottom of this file, so the roster now asserts each default IS exercised rather
than that it is not. The first run of this file failed on both entries the
moment those tests existed, which is the measurement working: it counts the call
sites in this file too. Excluding a file's own calls from its own measurement is
exactly the carve-out that produces a suite agreeing with itself.

## How it is measured

Statically, from the suite's own source: every `ast.Call` whose callee spells the
function's name, matched against the real `inspect.signature` so a positionally
supplied argument counts as supplied. Name matching over-collects - anything else
called `call` or `append` lands in the same bucket - and that is the safe
direction here: an over-collected call site can only make a parameter look MORE
exercised, so `DEFAULTS_THE_SUITE_NEVER_TAKES` cannot be inflated by it.

`test_the_measurement_can_report_both_answers` is the control. A measurement that
returns the same verdict for every input is not a measurement.
"""

from __future__ import annotations

import ast
import collections
import inspect
import unittest
from pathlib import Path
from typing import Any, Callable

from app import events, feasibility, security
from app.tools import evidence
from app.tools.registry import Registry

import support


TESTS_ROOT = Path(__file__).resolve().parent


#: `label -> (callable, drops self)`. The functions whose defaulted parameters
#: decide SCOPE, IDENTITY or AUTHORITY - the three things a default should never
#: quietly answer.
WATCHED: dict[str, tuple[Callable[..., Any], bool]] = {
    "Registry.call": (Registry.call, True),
    "evidence.record": (evidence.record, False),
    "evidence.assemble_facts": (evidence.assemble_facts, False),
    "events.append": (events.append, False),
    "events.create_thread": (events.create_thread, False),
    "security.write_portfile": (security.write_portfile, False),
    "feasibility.store_model_config": (feasibility.store_model_config, False),
}


#: Defaults this suite DOES take, and the count is the point. Every one of these
#: is a route somebody could waste a change "covering".
DEFAULTS_THE_SUITE_TAKES: tuple[str, ...] = (
    # The one the finding named. Sixty-three test call sites omit it.
    "Registry.call.thread_id",
    "Registry.call.actor",
    "Registry.call.approved",
    "evidence.record.thread_id",
    "evidence.record.tool",
    "evidence.assemble_facts.supplied",
    "events.append.project_id",
    "events.append.thread_id",
    "events.create_thread.project_id",
)


#: Defaults no test took in 1057 of them, and what the product does when one is
#: taken. THIS ROSTER IS HISTORY PLUS A LIVE ASSERTION: the test below checks
#: that each is exercised NOW, by `TheHarnessMakesTheDefaultSafeToTakeTest` at
#: the bottom of this file. Delete an entry only when the product stops shipping
#: the default, never to make this file quiet.
DEFAULTS_ONCE_NEVER_TAKEN: dict[str, str] = {
    "security.write_portfile.path": (
        "the default is `security.ENGINE_FILE`, the repository's own "
        "`engine.json`, and the file carries the live engine's bearer token. "
        "Every caller in the suite passes `path=`; `app.main.lifespan` does "
        "not, so the one test that entered a lifespan republished the user's "
        "real portfile on every run and nothing reported it. See "
        "tests/test_theme.py and "
        "tests/test_the_sandbox_isolates_everything_the_product_writes.py."
    ),
    "feasibility.store_model_config.root": (
        "the default is `feasibility.MODEL_CONFIG_ROOT`, which is "
        "`app/model_configs/` - TRACKED IN GIT. The one direct caller in the "
        "suite passes `root=`; `read_model_config`, a registered tool a model "
        "may call without approval, does not. `support.sandbox()` now binds "
        "the global, which is what makes the default safe to take."
    ),
}


def _test_call_sites() -> dict[str, list[tuple[set[str], int]]]:
    """`name -> [(keyword names, positional count)]` for every call in `tests/`."""
    sites: dict[str, list[tuple[set[str], int]]] = collections.defaultdict(list)
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        except (OSError, SyntaxError):  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            else:
                continue
            sites[name].append(
                ({k.arg for k in node.keywords if k.arg}, len(node.args))
            )
    return sites


def omission_report() -> dict[str, tuple[int, int]]:
    """`"label.parameter" -> (omitted, total)` for every watched default."""
    sites = _test_call_sites()
    report: dict[str, tuple[int, int]] = {}
    for label, (function, drops_self) in WATCHED.items():
        short = label.rsplit(".", 1)[-1]
        signature = inspect.signature(function)
        positional = [
            parameter.name
            for parameter in signature.parameters.values()
            if parameter.kind
            in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
        ]
        if drops_self and positional and positional[0] == "self":
            positional = positional[1:]
        defaulted = [
            parameter.name
            for parameter in signature.parameters.values()
            if parameter.default is not inspect.Parameter.empty
        ]
        found = sites.get(short, [])
        for name in defaulted:
            index = positional.index(name) if name in positional else None
            omitted = sum(
                1
                for keywords, count in found
                if name not in keywords and not (index is not None and count > index)
            )
            report[f"{label}.{name}"] = (omitted, len(found))
    return report


class TheEnumerationTest(unittest.TestCase):
    """The two rosters, checked in both directions against the live suite."""

    def setUp(self):
        self.report = omission_report()

    def test_every_default_the_roster_calls_exercised_is_still_exercised(self):
        for entry in DEFAULTS_THE_SUITE_TAKES:
            with self.subTest(default=entry):
                self.assertIn(entry, self.report, "no such parameter any more")
                omitted, total = self.report[entry]
                self.assertGreater(
                    omitted,
                    0,
                    f"no test call site omits {entry} any more ({total} sites "
                    "found). Coverage of the default path was lost, not gained: "
                    "the product still ships that default and something still "
                    "takes it.",
                )

    def test_every_default_that_was_never_taken_is_taken_now(self):
        for entry, why in sorted(DEFAULTS_ONCE_NEVER_TAKEN.items()):
            with self.subTest(default=entry):
                self.assertIn(entry, self.report, "no such parameter any more")
                omitted, total = self.report[entry]
                self.assertGreater(total, 0, f"{entry} has no call sites at all")
                self.assertGreater(
                    omitted,
                    0,
                    f"nothing in the suite takes the default for {entry} any "
                    "more. It went untaken through 1057 tests once already, "
                    "while the product's own callers took it every day - so "
                    "this is the suite going back to not running a path that "
                    f"ships.\n\nWhy it matters: {why}",
                )

    def test_the_default_named_by_the_finding_is_the_majority_path(self):
        """The correction, asserted rather than asserted about.

        If `Registry.call`'s `thread_id` were rarely omitted, "tests always pass
        a thread_id" would be an argument-coverage problem. It is omitted more
        often than not, so it is not one.
        """
        omitted, total = self.report["Registry.call.thread_id"]

        self.assertGreater(
            omitted,
            20,
            "only a handful of call sites omit thread_id, so the reading in "
            "this file's docstring no longer holds and the docstring is wrong",
        )
        self.assertGreater(total, omitted, "no call site supplies it at all")

    def test_the_measurement_can_report_both_answers(self):
        """THE CONTROL. A measure that says the same thing about everything.

        Both verdicts must be reachable from the real data: at least one watched
        default is omitted somewhere and at least one is omitted nowhere. If
        every entry came back the same, neither assertion above would mean
        anything.
        """
        values = list(self.report.values())
        self.assertTrue(any(omitted > 0 for omitted, _ in values))
        self.assertTrue(any(omitted == 0 and total > 0 for omitted, total in values))


class TheHarnessMakesTheDefaultSafeToTakeTest(unittest.TestCase):
    """The other half of a never-taken default: make taking it harmless.

    A roster that only records "nobody runs this" is a list of complaints. The
    reason both entries above exist is that the default wrote into the user's
    checkout, and `support.sandbox()` binding the globals is what turns each of
    them from a hazard into an ordinary path - which is the actual fix, because
    the caller that takes the default is product code, not a test.
    """

    def setUp(self):
        self.root = support.sandbox(self)

    def test_write_portfile_with_no_path_stays_inside_the_sandbox(self):
        published = security.write_portfile(port=support.free_port())

        self.assertIn(
            self.root.resolve(),
            Path(published).resolve().parents,
            f"write_portfile() with no path wrote to {published}",
        )
        self.assertEqual(
            security.read_portfile(published)["token"], security.current_token()
        )

    def test_store_model_config_with_no_root_stays_inside_the_sandbox(self):
        written = feasibility.store_model_config(
            "acme/tiny", {"num_hidden_layers": 2}, revision="deadbeef"
        )

        self.assertIn(
            self.root.resolve(),
            Path(written).resolve().parents,
            f"store_model_config() with no root wrote to {written}",
        )


if __name__ == "__main__":
    unittest.main()
