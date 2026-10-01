"""The prompt's account of the product is derived, and the derivation is checked.

## The defect this file exists to make impossible

Max asked the running product, through the real UI, what it was and whether it
could help him build things. The connected model answered:

    "The ML Harness itself doesn't need a model; it helps users decide."
    "You will still need to handle the actual building and training if you
     decide to proceed with model development."

`start_training` was a registered tool at the time. So were `try_prompt`,
`run_eval` and `propose_build`. The model was not hallucinating a limitation - it
was repeating an instruction set that contained seventeen laws about diagnosis and
honesty and not one sentence about what the harness builds afterwards, plus a
tools fragment that was entirely about DISCIPLINE and never said what a single
tool was FOR.

`app/instructions/01b_after_the_verdict.md` is the missing law. But a law alone
would be the same defect waiting: a hand-written list of what the product can do
is wrong the day somebody registers a tool, and this repository has been bitten by
that three times already. So the list is generated from `REGISTRY`, and this file
is what makes that generation load-bearing instead of decorative.

## The two directions, and why both are needed

**Every registered tool appears in the assembled prompt.** Register a tool without
it reaching the prompt and this goes red. That is what stops the harness from
hiding a capability it has - the direction the live defect ran in.

**Every id the prompt quotes is real.** A tool name that is deleted, or invented in
a fragment somebody wrote by hand, goes red too. That is what stops the harness
from promising a capability it does not have - "never invent a number" pointed at
a different kind of claim, and the reason the fix cannot become an overclaim.

`tests/test_a_refusal_names_the_door.py` already checks the second direction over
the markdown files. This checks it over the ASSEMBLED PROMPT, which is a different
and now larger string: most of what the model is told about the tools exists in no
file at all.
"""

from __future__ import annotations

import re
import unittest
from unittest import mock

from app import diagnosis, instructions
from app.instructions import capabilities
from app.tools import Control, Registry, ToolSpec
from app.tools import blocks
from app.tools.registry import REGISTRY


#: Every combination of the conditional fragments. The capability list has to
#: survive all of them: a user whose model cannot call tools is still using a
#: product that trains models, and `cond_no_tool_calling` says so explicitly -
#: the harness runs the tools and hands back the results.
#:
#: THE PORTAL AXIS IS GONE AND `loaded` REPLACED IT. The consumer/enterprise
#: fragments were deleted on 2026-08-24; the axis that varies per turn now is
#: which capability blocks the standing diagnosis loaded. **And that axis is
#: exactly the one this file exists to hold the line on** - the list must name
#: every registered tool whether twelve of them are callable or forty, because a
#: model told about twelve tells the user this product has twelve, which is the
#: defect `app/instructions/capabilities.py` was written for.
COMBINATIONS = [
    {"tool_calling": tool_calling, "loaded": loaded, "sensitive": sensitive}
    for tool_calling in (True, False, None)
    for loaded in (None, tuple(blocks.tools_in(blocks.CORE)))
    for sensitive in (True, False)
]

#: A backticked, lowercase, underscored token: how this prompt writes an id.
QUOTED_ID = re.compile(r"`([a-z][a-z0-9_]*)`")


def quoted_ids(text: str) -> set[str]:
    return {token for token in QUOTED_ID.findall(text) if "_" in token}


def fake_registry() -> Registry:
    """A registry that is not the product's, holding one tool nobody has."""
    registry = Registry()
    registry.add(
        ToolSpec(
            name="summon_a_pony",
            description=(
                "Summon a pony onto the user's machine. It is a very good pony. "
                "This sentence exists so the summary has something to cut."
            ),
            schema={
                "type": "object",
                "properties": {"stable_path": {"type": "string"}},
                "required": ["stable_path"],
            },
            reads=(),
            writes=(),
            approval="always",
            provides=("machine.hardware.inspect",),
            control=Control(label="Summon", group="Stable", verb="summon a pony"),
            handler=lambda stable_path: None,
        )
    )
    return registry


class EveryRegisteredToolReachesTheModelTest(unittest.TestCase):
    def test_every_registered_tool_is_named_in_the_assembled_prompt(self):
        """The direction the live defect ran in.

        A registered tool the prompt never mentions is a capability the product
        has and denies having, which is what happened.
        """
        names = REGISTRY.names()
        self.assertGreater(len(names), 1, "the registry is empty - check imports")
        for kwargs in COMBINATIONS:
            prompt = instructions.assemble(**kwargs)
            for name in names:
                with self.subTest(tool=name, **kwargs):
                    self.assertIn(
                        f"`{name}`",
                        prompt,
                        f"{name} is registered and the assembled prompt never "
                        "names it. The model cannot offer a capability it has "
                        "not been told about.",
                    )

    def test_start_training_is_named_and_marked_as_needing_an_approval(self):
        """The specific sentence that was false, kept as its own test.

        "You will still need to handle the actual building and training" was
        said while this tool was registered. Naming it is not enough on its own:
        a model that offers to start training without saying an approval comes
        first has replaced one wrong claim with another.
        """
        prompt = instructions.assemble()
        self.assertIn("`start_training`", prompt)
        self.assertIn("A person has to approve it before it runs.", prompt)

    def test_the_manifest_reports_what_the_prompt_was_told(self):
        self.assertEqual(instructions.manifest()["tools"], REGISTRY.names())


class ThePromptInventsNoCapabilityTest(unittest.TestCase):
    def test_every_id_the_assembled_prompt_quotes_is_real(self):
        """The other direction: no name appears which is not registered.

        Allowed: a registered tool, a fact SOME shipped ledger declares, or an
        argument some registered tool's schema declares. All three sets are read
        from the thing that owns them, so this cannot be satisfied by adding a
        word to a list kept here.

        RETIRED AND WIDENED 2026-08-25: `facts` read the default spec alone,
        which was the whole world when there was one ledger. The product now
        ships two, and the four agent instruments quote the second ledger's
        fact ids from every thread's capability list - correctly, because those
        tools genuinely exist and are buttons a person can press whatever this
        thread is diagnosing. The invariant's teeth are unchanged: an id no
        shipped ledger declares is still red here, so a typo'd or invented
        fact name cannot reach a model.
        """
        tools = set(REGISTRY.names())
        facts: set[str] = set()
        for path in diagnosis.known_ledgers():
            facts |= set(diagnosis.spec_at(path).facts)
        arguments = {
            name
            for spec in REGISTRY
            for name in (spec.schema.get("properties") or {})
        }
        for kwargs in COMBINATIONS:
            prompt = instructions.assemble(**kwargs)
            found = quoted_ids(prompt)
            self.assertTrue(found, "the prompt quotes no ids - check the regex")
            for token in sorted(found):
                with self.subTest(token=token, **kwargs):
                    self.assertTrue(
                        token in tools or token in facts or token in arguments,
                        f"the assembled prompt quotes {token!r}, which is not a "
                        "registered tool, a declared fact or any tool's "
                        "argument. A prompt that names a capability the harness "
                        "does not have is an invented number in a costume.",
                    )


class TheListIsDerivedNotWrittenTest(unittest.TestCase):
    """Proof the list follows the registry, rather than happening to match it.

    A test that only reads the real registry cannot tell a generated list from a
    hand-written one that is currently correct. These render against a registry
    the product does not own.
    """

    def test_a_tool_only_this_test_registered_appears_in_the_list(self):
        text = capabilities.render(fake_registry())
        self.assertIn("`summon_a_pony`", text)
        self.assertIn("Summon a pony onto the user's machine.", text)
        self.assertIn("Needs `stable_path`.", text)
        self.assertIn("A person has to approve it before it runs.", text)
        self.assertIn("### Stable", text)

    def test_a_tool_that_is_not_registered_does_not_appear(self):
        text = capabilities.render(fake_registry())
        for name in REGISTRY.names():
            with self.subTest(tool=name):
                self.assertNotIn(f"`{name}`", text)

    def test_the_count_is_counted_and_not_quoted(self):
        self.assertIn("There are 1 of them", capabilities.render(fake_registry()))
        self.assertIn(
            f"There are {len(REGISTRY)} of them", capabilities.render()
        )

    def test_a_group_nobody_glossed_still_renders_every_tool_in_it(self):
        """The one hand-written thing left, and it cannot hide a tool.

        `Stable` has no gloss. The heading is plainer for it and the tool is
        still there, which is the failure mode this is allowed to have.
        """
        text = capabilities.render(fake_registry())
        self.assertIn("### Stable\n", text)
        self.assertNotIn("### Stable -", text)
        self.assertIn("`summon_a_pony`", text)

    def test_every_registered_tool_lands_in_exactly_one_group(self):
        text = capabilities.render()
        headings = [line for line in text.splitlines() if line.startswith("### ")]
        self.assertEqual(
            len(headings),
            len({spec.control.group for spec in REGISTRY}),
            "a control group vanished from the rendered list",
        )
        for spec in REGISTRY:
            with self.subTest(tool=spec.name):
                self.assertEqual(text.count(f"- `{spec.name}` - "), 1)

    def test_the_version_moves_when_the_registry_moves(self):
        """A registry change is an instruction-set change, and must be visible.

        Two transcripts produced under different instructions have to be
        distinguishable afterwards. Registering a tool changes what every prompt
        from that moment claims the product can do, and moves no file on disk.
        """
        before = instructions.version()
        with mock.patch("app.tools.registry.REGISTRY", fake_registry()):
            during = instructions.version()
        self.assertNotEqual(before, during)
        self.assertEqual(before, instructions.version())


class TheLawAfterTheVerdictTest(unittest.TestCase):
    def test_the_law_is_a_core_file_and_therefore_unconditional(self):
        names = [path.name for path in instructions.core_files()]
        self.assertIn("01b_after_the_verdict.md", names)

    def test_the_prime_directive_no_longer_reads_as_a_full_stop(self):
        """Law 2 is true and stays. A reader who stops there is the problem.

        "Diagnosis comes before construction, always" is exactly what a model
        given nothing else reads as "construction never comes".
        """
        prompt = instructions.assemble()
        self.assertTrue(
            instructions.contains(
                prompt, "Diagnosis comes before construction, always"
            )
        )
        self.assertTrue(
            instructions.contains(prompt, "Before it, not instead of it")
        )

    def test_the_loop_is_stated_end_to_end(self):
        """The loop lost its "understand" and "propose" steps on 2026-09-21,
        deliberately: a small model read the long form as six things to narrate
        before doing one. "prove" replaced the approval it used to wait for -
        it defends the plan with numbers instead of asking twice. The list is
        still hand-written, not parsed off the arrow line, because a test that
        reads the loop out of the prompt it is checking cannot fail.
        """
        prompt = instructions.assemble()
        for step in (
            "diagnose",
            "plan",
            "prove",
            "show",
            "approve",
            "run",
            "verify",
            "hand back",
        ):
            with self.subTest(step=step):
                self.assertIn(step, prompt)
        self.assertIn("`propose_build`", prompt)

    def test_the_law_forbids_overclaiming_as_well_as_underclaiming(self):
        """Both halves, because a fix for one that breaks the other is not one."""
        prompt = instructions.assemble()
        self.assertTrue(instructions.contains(prompt, "Never invent a capability"))
        self.assertTrue(
            instructions.contains(prompt, "Do not promise what the harness cannot do")
        )
        self.assertTrue(instructions.contains(prompt, "And do not hide what it can"))


if __name__ == "__main__":
    unittest.main()
