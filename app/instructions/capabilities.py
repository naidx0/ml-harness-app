"""What the harness can do, read off the registry instead of written down.

## Why this is code and not another markdown fragment

Every other fragment in this package is prose, on purpose: a law is a sentence
somebody has to be able to diff. This one is not prose, for the opposite reason
and with the same goal.

A hand-written list of what the product can do is wrong the moment somebody
registers a tool, and this repository has now been bitten by exactly that three
times - `propose.py` calling itself "the only scoring tool here" after
`run_eval` landed, the roadmap's status claims twice, and the defect this module
exists to close: asked through the real UI whether it could help build anything,
the connected model said *"you will still need to handle the actual building and
training if you decide to proceed with model development"* while `start_training`
was a registered tool. The model was not wrong. It was repeating what we told it,
and what we told it was that the harness has tools it must not misuse - never
what any of them was FOR.

So the list is derived. `render()` reads `REGISTRY` at the moment the prompt is
assembled:

- a tool that is registered appears in what the harness says about itself,
  automatically;
- a tool that is removed disappears;
- there is no second copy of the list, so there is nothing to go stale.

`tests/test_the_prompt_says_what_the_harness_can_do.py` asserts both directions -
every registered tool is in the assembled prompt, and every id the prompt quotes
is real - which is what makes the drift impossible rather than merely fixed today.

## What is still written by hand here, and why that is safe

Two things: the framing paragraphs, and one line of gloss per group. Neither can
hide a tool. A group with no gloss still renders, with its name and all of its
tools, so the failure mode of forgetting to write one is a heading that reads a
little flatter - not a capability that vanishes. That is the property to protect,
and it is why `_GLOSS.get(group, "")` is a `.get` rather than a lookup.

## What each line says, and where each half comes from

`name` - the id. `what it does` - the first sentence or two of the tool's own
`description`, the same words the model gets in the tool schema. `what it needs` -
the schema's `required` list. Plus, when the tool declares them: the facts it may
stamp MEASURED, because a model reasoning about the five gates needs to know which
tools can open one; and whether a person has to approve it first, because
`start_training` is the tool this whole product is careful about.

## Two lengths, and the short one is not a trim

`render(detail=False)` drops the description and the `required` list and keeps
everything else - every group, every name, every approval, every measured fact.
It is used when, and only when, the harness is also sending the tool schemas,
because in that case `what it does` and `what it needs` are a **verbatim second
copy** of text the model already has: `REGISTRY.model_tools()` puts all 28 full
descriptions and all 28 parameter schemas in the same request, 28,999 characters
of them. Restating the opening of each description in the system prompt is the
one thing this module exists to prevent - a second copy of a fact - and it costs
tokens on every turn to do it.

Measured on granite4-hermes's own tokeniser, through `/api/chat`'s
`prompt_eval_count`: the long list is 6,981 characters and the short one is
2,730. The whole system prompt goes from 8,025 tokens to 7,108, and a turn's
fixed cost - prompt plus schemas, before the user has typed anything - from
14,130 to 13,213. That is 917 tokens saved on every turn of every conversation.

The larger number is the one this file cannot reach: the schemas themselves cost
6,074 of the remaining 13,213, and they live in `app/tools/`.

When the connected model **cannot** call tools, or has not been probed, the
schemas are not sent - `app/conductor.py` passes `offered = None` - and the long
form is the only account of the tools the model gets. So the length follows the
one question that decides whether the detail is already in the room, and nothing
else. The default is the long form: a caller who has not said which situation it
is in gets the complete one.
"""

from __future__ import annotations

import re
from typing import Any, Iterable


#: One line per control group, written by hand and looked up with `.get` so a
#: group nobody has glossed still renders every tool it holds. See the module
#: docstring: the invariant is that no tool can disappear, not that every
#: heading reads well.
_GLOSS: dict[str, str] = {
    "Look": "what is already on this machine, before you ask anybody anything",
    "Context": "what the user pointed at, and what is actually inside it",
    "Data": (
        "measuring, and the AI-engineering work the no-train verdicts name - "
        "evals, prompt attempts, and what they scored"
    ),
    "Decide": "the verdict, and the build that follows it",
    "Choose": "which model, for this machine and this job",
    "Train": "training itself, which this harness runs rather than describes",
}

#: A sentence shorter than this is almost always a title rather than an
#: explanation - `state_facts` opens "Record facts about this project." and the
#: sentence that matters is the next one. Keep taking sentences until there is
#: enough of one to be worth reading.
_MIN_SUMMARY = 40


def _default_registry() -> Any:
    """`REGISTRY`, imported when asked for rather than at module import.

    Deliberately lazy. `app/instructions/` is the one package in this product
    that a reader should be able to import and read on its own, and several
    modules under `app/tools/` already reference these fragments in their
    docstrings - a top-level import here is the edge that would close that
    circle the first time one of them turns a reference into an import.
    """
    from app.tools.registry import REGISTRY

    return REGISTRY


def summarise(description: str) -> str:
    """The opening of a tool's own description, whole sentences only.

    The model is handed the full text in the tool schema; this is the harness
    describing itself, where twenty-four full descriptions would bury the list
    it is trying to make readable. Nothing is paraphrased - a summary written
    here would be a second copy of the description, which is the defect this
    whole module exists to avoid.
    """
    text = " ".join(str(description or "").split())
    for match in re.finditer(r"(?<=[.!?])\s+", text):
        head = text[: match.start()]
        if len(head) >= _MIN_SUMMARY:
            return head
    return text


def _needs(spec: Any) -> str:
    required = list((spec.schema or {}).get("required") or ())
    if not required:
        return "Takes no required input."
    quoted = ", ".join(f"`{name}`" for name in required)
    return f"Needs {quoted}."


def _how_to_read(*, detail: bool, loaded: set[str] | None, total: int) -> str:
    """The one line that says what the list is and where the rest of it lives."""
    if detail:
        return "Each line is what it is called, what it does, and what it needs first."
    if loaded is None:
        return _WHERE_THE_DETAIL_IS
    return _WHERE_THE_LOADED_DETAIL_IS.format(loaded=len(loaded), total=total)


def _line(spec: Any, *, detail: bool = True, loaded: set[str] | None = None) -> str:
    """One tool. `detail=False` keeps everything the tool schema does not carry.

    What the short form drops is exactly what `REGISTRY.model_tools()` is
    already sending: the description and the `required` list. What it keeps is
    what the schema has no field for and the model would otherwise never learn -
    which facts this tool may stamp MEASURED, and whether a person has to
    approve it. `start_training` losing its approval line would be a real hole,
    so it does not lose it in either form.

    `loaded` marks the ones whose schema is in this request. IT MARKS RATHER
    THAN FILTERS, and the mark goes on the name so that a reader scanning the
    list can tell in one pass which half of it is callable right now.
    """
    mark = _LOADED_MARK if loaded is not None and spec.name in loaded else ""
    said: list[str] = []
    if detail:
        said.append(summarise(spec.description))
        said.append(_needs(spec))
    if spec.measures:
        stamped = ", ".join(f"`{fact}`" for fact in spec.measures)
        said.append(f"Records {stamped} as measured.")
    if spec.approval == "always":
        said.append("A person has to approve it before it runs.")
    if not said:
        return f"- `{spec.name}`{mark}"
    return f"- `{spec.name}`{mark} - " + " ".join(said)


def _grouped(registry: Iterable[Any]) -> list[tuple[str, list[Any]]]:
    """Groups in pipeline order, tools in declaration order inside each.

    Both orders come off the registry: a group sorts by the lowest `order` any
    of its tools declared, which is the same number that already lays the
    controls out for a person. Nothing here decides what belongs where.
    """
    buckets: dict[str, list[Any]] = {}
    for spec in registry:
        buckets.setdefault(spec.control.group, []).append(spec)
    for tools in buckets.values():
        tools.sort(key=lambda spec: (spec.control.order, spec.name))
    return sorted(
        buckets.items(), key=lambda item: (item[1][0].control.order, item[0])
    )


def tool_names(registry: Any | None = None) -> list[str]:
    """Every registered tool name. The test's other half reads this."""
    return [spec.name for spec in (registry if registry is not None else _default_registry())]


#: How the list says where the rest of each tool's story is. Only true when the
#: schemas are in the same request, which is the only case `detail=False` is
#: used in - see the module docstring.
#:
#: IT USED TO SAY "FOR EVERY ONE OF THEM" AND THAT STOPPED BEING TRUE. Capability
#: blocks scope which schemas a turn sends, so the sentence is now split: this
#: one for a turn that sent them all, `_WHERE_THE_LOADED_DETAIL_IS` for a turn
#: that sent some. A prompt that told the model its schemas were in the room when
#: they were not would be the harness lying about its own request, which is the
#: same defect as a number without a provenance and in the same voice.
_WHERE_THE_DETAIL_IS = (
    "Each line is what the tool is called. What it does and what it needs are "
    "in the tool definitions sent with this message - the full description and "
    "the full parameter schema for every one of them, generated from this same "
    "registry. Read them there rather than asking. Nothing is missing from this "
    "list; the descriptions are simply not repeated into it twice."
)

#: The same sentence when the turn is scoped to its capability blocks. TWO
#: COUNTS AND ONE LIST, and neither count is decoration: the first says what is
#: callable right now, the second says what this product is, and a prompt
#: carrying only one of them is either understating the harness or overstating
#: the request.
_WHERE_THE_LOADED_DETAIL_IS = (
    "Each line is what the tool is called. {loaded} of these {total} are loaded "
    "for this turn - marked (*) below - and their full description and full "
    "parameter schema are in the tool definitions sent with this message; read "
    "them there rather than asking. The rest are listed because they are part of "
    "this harness: every one of them is also a button in the app, which a person "
    "can press at any time, and the diagnosis loads the block the work belongs "
    "to when it reaches an answer that calls for it. This list is complete; what "
    "varies from turn to turn is which of it you can call."
)

#: What marks a loaded tool in the scoped list. A GLYPH RATHER THAN A CLAUSE:
#: one line of legend and one character per line costs 40 characters, and a
#: sentence per unloaded tool would cost about 1,200 on every turn to say the
#: same thing twenty-eight times.
_LOADED_MARK = " (*)"


def render(
    registry: Any | None = None, *, detail: bool = True, loaded: Any = None
) -> str:
    """The capability fragment for this prompt, built from the registry now.

    `detail=False` is the short form. It is complete - every group and every
    name - and is used only when the tool schemas travel in the same request,
    where the long form's middle two clauses are a second copy of them.

    `loaded` is the tool names whose schemas this turn is actually sending.
    **THE LIST STAYS COMPLETE WHATEVER IT HOLDS.** Dropping the unloaded tools
    would be cheaper by about 1,900 characters and it would rebuild, inside the
    prompt, the defect this whole module exists to close: asked through the real
    UI whether it could help build anything, a connected model said *"you will
    still need to handle the actual building and training"* while `start_training`
    was registered. It was not wrong; it was repeating what we told it. A model
    told about twelve tools tells the user this product has twelve.

    So the scope is stated rather than applied: every tool is named, the loaded
    ones are marked, and the sentence above says what the mark means.
    """
    registry = registry if registry is not None else _default_registry()
    groups = _grouped(registry)
    count = sum(len(tools) for _, tools in groups)
    here = None if loaded is None else {str(name) for name in loaded}

    out = [
        "## What this harness can actually do",
        "",
        "The list below is generated from the harness's own tool registry at the "
        "moment this prompt was assembled. Nobody wrote it out and nobody has to "
        "remember to update it: a tool that is registered appears here, a tool "
        "that is removed disappears, and there is no second copy of it to be "
        "wrong.",
        "",
        f"There are {count} of them, counted off the registry rather than from "
        "memory. This is the list the law about capabilities refers to. It is "
        "what you answer \"can this thing actually do X\" from - not from what "
        "language models generally cannot do.",
        "",
        _how_to_read(detail=detail, loaded=here, total=count),
        "",
    ]

    for group, tools in groups:
        gloss = _GLOSS.get(group, "")
        out.append(f"### {group}" + (f" - {gloss}" if gloss else ""))
        out.append("")
        out.extend(_line(spec, detail=detail, loaded=here) for spec in tools)
        out.append("")

    out.append(
        "Together these are the harness: it looks at the machine and the data "
        "itself, measures a baseline, runs the diagnosis, proposes a build for "
        "whatever the diagnosis decided, and then runs that build - the prompt "
        "work and the eval work and the training alike. A person is not being "
        "sent elsewhere to do the second half."
    )
    # NOTHING FURTHER GOES HERE, and a note about what was tried and taken back
    # out. A fourth copy of "answer the capability question in words rather than
    # running the diagnosis at it" lived here for a while, at the top of the
    # prompt where a small model would still be attending. Six samples against
    # granite4-hermes with it and six without were indistinguishable, so it was
    # removed: the rule is already stated where it belongs - as a law in
    # `01b_after_the_verdict.md` and as a tool-calling rule in
    # `cond_tools_available.md` - and a third statement of it that cannot be
    # shown to help is the same drift this module exists to prevent, wearing the
    # costume of being helpful.
    return "\n".join(out).strip()


def digest_material(registry: Any | None = None) -> bytes:
    """What `version()` hashes so a registry change moves the version.

    The instruction set is content-addressed because two transcripts produced
    under different instructions have to be distinguishable afterwards. The
    prompt now contains a section that no file holds, so a digest over the files
    alone would report the same version for two genuinely different prompts -
    the same defect that hashing only the core files had, one layer out.

    BOTH FORMS, because both ship. Hashing only the long one would leave every
    edit to the short one invisible in the version string, which is the same
    hole one level further in: the prompt a turn actually ran under would not be
    identifiable from the version it recorded.

    AND NEITHER FORM IS SCOPED HERE, DELIBERATELY. `render(loaded=...)` marks
    which tools this turn can call, and folding that into the digest would move
    the version string every time the diagnosis moved - a content address that
    changes with the content it is not addressing. The selection is recorded
    where it belongs: `turn.started` carries `blocks`, so a transcript identifies
    its prompt as instruction-set version PLUS the packs that turn ran under, and
    both halves are replayable. See `app/tools/blocks.py`.
    """
    return (render(registry) + "\n" + render(registry, detail=False)).encode("utf-8")
