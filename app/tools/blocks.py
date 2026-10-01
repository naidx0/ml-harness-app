"""Which tools reach the model this turn, and who decided.

`docs/CAPABILITY_BLOCKS.md` is the research this implements. Its one-line
recommendation, and the one this file holds to:

> **A block is a namespace on a capability name, declared once on the tool.**
> The ledger never names a tool. The active set is chosen by the standing
> diagnosis, which already runs before the model speaks on every turn. The core
> is the closure of the selector.

## The vocabulary is the engine's, the binding is the tool's, the need is the ledger's

Three parties and none of them may name another's identifiers - the rule
`docs/LEDGER_FORMAT.md` §3 settled for facts, applied to capabilities:

* **the engine publishes `CAPABILITIES`**, a closed vocabulary. Nothing else may
  invent a name in it, and `registry._validate` refuses a tool that tries -
  the same wall `measures=` already gets, at the same moment, in front of the
  same reviewer.
* **a tool binds to one or more of those names** with `provides=`. The first
  dotted segment IS the pack, so declaring the capability is declaring the
  membership. There is no second list to go stale; that is the whole reason the
  pack is not a manifest file. `app/instructions/capabilities.py` learned this
  the expensive way and its module docstring is the argument.
* **a ledger says which packs a stage's work needs**, in `contract.capabilities`,
  in the engine's vocabulary and against its own node ids. It may not name
  `carve_eval_set`, which is a Python function in a package a ledger's author
  has never read.

Both shipped ledgers declare that block and they had to. Until 2026-08-24
neither did, the selection was derived alone, and the derivation was measured:
over all 63 fixture sheets the ML ledger has, the union of packs ever selected
was SIX OF ELEVEN, and the five that never loaded - `prompt`, `tabular`,
`models`, `training`, `sandbox` - hold fifteen of the forty tools. They are
precisely the packs whose tools stamp no fact, because every derived source
keys on a fact: what a gate is waiting on, what an alternative would settle,
what this thread has already measured. **All three look backward.** A thread
whose verdict was `TRAIN__LORA_SFT` could not be handed `start_training`.

So the declaration is not a refinement of the derivation, it is the other half
of it: the derivation says what the answer RESTS ON, the declaration says what
the answer ASKS FOR. **The selection is on always, beside the declaration** -
see `active()` for why that is the right order rather than the convenient one -
and `declared()` now refuses a block that names some of a ledger's stages and
not all of them, because a stage left out is that measured defect returning by
omission.

## What is core, and the argument is mechanical rather than aesthetic

**The core is the closure of the selector.** The packs are chosen by the walk,
so anything the walk depends on must be loaded before the walk can choose
anything. Four groups, and each would be enough on its own:

1. **`ledger`** - `run_diagnosis`, `propose_build`, `state_facts`,
   `offer_to_measure`. Drop the first and there is no route from any state back
   to the thing that decides which tools a turn gets: a state the system cannot
   leave. Anthropic's tool-search API enforces the identical invariant from the
   other end and returns a 400 for violating it - *"At least one tool must have
   `defer_loading=false`."* `offer_to_measure` is here because the honesty test
   is domain-general: it names no fact of its own, reads whatever ledger it is
   handed, and the instrument that keeps a claim from becoming a gate is not
   optional on any turn of any domain.
2. **`context`** - what the person pointed at. A bootstrapping argument, not a
   convenience one: the diagnosis reads these before it can classify anything,
   and the classification is what picks the packs. `preview_dataset_rows` is in
   this pack and not in `data` for exactly that reason - it is how the model
   finds out what the file IS, which is upstream of every question about it.
3. **`machine`** - every domain's cost estimate is about the same card. An
   AI-engineering thread bounding a loop's cost and an ML thread sizing a LoRA
   ask that card the same question.

And the rule that keeps the core from growing one ledger at a time: **a
capability is core only if EVERY ledger would name it, and the test for "every"
is a ledger that does not exist yet.** Machine, context and the engine's own
doors pass it. A trace reader does not, however much the AI ledger will want one.

## Additive, not exclusive - and the sharp version of it

`docs/PHASES.md`: *"If the ML block hid the data tools we would have rebuilt
tabs on the inside, where the user cannot even see them."* The sharpest way to
hold that is not a rule about which tools a pack may hide. It is a rule about
**who is being scoped**:

**Blocks scope what the model may CALL. They never scope what the harness IS.**

Two consequences, and both are asserted by tests rather than hoped for:

* `Registry.controls()` is not scoped and `app/main.py` keeps serving all of
  them, so a wrongly-scoped turn is a turn where the person clicks the button
  and the tool runs anyway. **The failure mode is visible and recoverable
  rather than invisible and permanent**, which is the argument against tabs
  restated at the layer where it can be enforced.
* `app/instructions/capabilities.py` keeps listing every registered tool. The
  law is `NEVER INVENT A CAPABILITY` and its neighbour, *"and do not hide what
  it can"* - a model that has not been told `start_training` exists tells the
  user this product cannot train, which was a live, user-facing defect and is
  the reason that module exists. What the scoped list changes is which tools
  have a callable schema in the room, and `capabilities.render` says which
  those are rather than leaving the reader to assume.

## What this file may never do

It reads a diagnosis. It cannot make one, cannot write a fact, and cannot open
a gate. And the sibling of `registry.py`'s hard rule: **no tool a model can call
may widen the tool set.** That holds structurally rather than by policy, because
every input to `active()` is either a constant, a diagnosis the model's
arguments cannot reach, or a row in the evidence ledger that only an instrument
can write. There is no `blocks.request` tool and there is not meant to be one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


#: A capability name: two or three dotted segments, lower case. The first is the
#: pack. Two rather than one because a bare word is a pack and not a capability,
#: and a ledger binding to `data` would be binding to a folder.
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,2}$")


class BlockError(ValueError):
    """A capability name the engine does not publish, or a pack nobody declares."""


#: THE PUBLISHED VOCABULARY. Every name a tool may declare in `provides=` and
#: every name a ledger may name in `contract.capabilities`. The engine owns it;
#: see the module docstring for why that ownership is the whole design.
#:
#: A name here with no provider is LEGAL and is not an oversight. It is how "the
#: ledger asks for something this product cannot do yet" is representable at all,
#: which is XACML's rule for a policy enforcement point and this repository's own
#: rule for coverage: an outcome naming a capability nothing provides is not
#: covered, in those words, with the capability named - never a plausible plan
#: with no step that moves anything. `providers()` returns `()` for such a name
#: and callers must be able to say so.
#:
#: The gloss is for a person reading a refusal. Nothing routes on it.
CAPABILITIES: dict[str, str] = {
    # -- machine: what is already in this box -------------------------------
    "machine.hardware.inspect": "read the accelerator, memory and disk on this machine",
    "machine.local_models.list": "list the models already downloaded here",
    "machine.runs.list": "list the training runs recorded here",
    # -- context: what the person pointed at, and what is inside it ---------
    "context.attachment.add": "attach a file or folder to this conversation",
    "context.attachment.list": "list what has been attached",
    "context.file.read": "read an attached file as data",
    "context.repository.profile": "profile a code repository",
    # The project's standing constraints - PRODUCT_SPEC 4.3's `HARNESS.md`.
    # In `context` and not `ledger` because it is prose the person wrote about
    # their own project, not a fact anything measured: nothing it says opens a
    # gate, and the tool that reads it declares `measures=()` for that reason.
    "context.project.constraints": "read the project's standing constraints",
    "context.dataset.preview": "look at the rows of a dataset",
    # Earlier conversations, searched. Hermes' `session_search` rebuilt over
    # this harness's messages table (`app/recall.py`), 2026-09-11, on the
    # owner's "where is my consistent memory system". In `context` because it
    # is what the person and this product already said, and core for the
    # reason `map_the_ask` is: the first turn of a new thread is exactly the
    # turn that needs to know what a sibling thread settled.
    "context.recall.search": "search earlier conversations in this project",
    # Curated memory, Hermes' MEMORY.md / USER.md rebuilt per project
    # (`app/memory.py`), the second of the three. Core for the same reason:
    # what a project already knows has to be on the first turn, and the door
    # to write it has to be in the room when something durable is learned.
    "context.memory.write": "save a durable fact to this project's memory or the person's profile",
    # AU4 — free-text shell in the project folder (auto under permission full).
    "context.shell.run": "run a free-text shell command in this project's folder",
    # ObservationPack, 2026-09-18 (`app/observations.py`): a large tool result
    # rides whole for two rounds, then as a handle and an excerpt; this is the
    # door the handle opens. In `context` because it reads what this
    # conversation already holds, and it costs nothing it did not already pay.
    "context.observation.read": "read a packed tool result back in full, or a window of it",
    # -- ledger: the engine's own doors, and the evidence door --------------
    "ledger.facts.state": "record what the person says about their project",
    "ledger.diagnosis.run": "walk the ledger over this thread's facts",
    # The other half of running the diagnosis. `ledger.diagnosis.run` says where
    # a thread stopped; this says what would move it. They were one door and a
    # route for a fortnight - the deriving was built, served at
    # `GET /api/next_step`, and offered to nobody: 67 tools registered, 67
    # offered to a model, none of them the asker.
    "ledger.asking.next_step": "say which single fact would move this thread",
    "ledger.build.propose": "turn an outcome into a build the person can approve",
    "ledger.claim.challenge": "turn a claimed number into an offer to measure it",
    "ledger.plan.write": "save the phased plan this conversation will build",
    "ledger.plan.read": "read the plan saved for this conversation",
    # THE JOURNEY COMPILES THE PLAN (2026-09-18, app/journey.py). The route
    # already holds every step's tool and the arguments this thread measured
    # for it; writing that out by hand is what produced eight phases with no
    # steps in them on thread 75.
    "ledger.plan.compile": "write the plan from the journey this conversation is on",
    # The to-do list is the goal function (2026-09-12, app/tools/planning.py):
    # a build ticks `- [ ]` steps and keeps going until none is open.
    "ledger.plan.step": "tick one step of the plan as done",
    # ONE PHASE, ONE SUB-AGENT (2026-09-13, app/subagents.py). The orchestrator
    # hands a phase out and reads back the ticks and the parks - not the child's
    # transcript, which is the whole economy of it.
    "ledger.plan.phase": "hand one phase of the plan to a sub-agent, and read what came back",
    # CS9 — ask-gated; pack `intent` is never CORE and only loads when invited.
    "intent.goal.write": "set or clear this conversation's standing goal, when invited",
    "intent.todo.write": "write or clear the secondary todo checklist, when invited",
    # -- data: the floor under every domain that needs examples -------------
    "data.dataset.profile": "profile a dataset file and count what is in it",
    "data.dataset.assess": "judge whether a dataset can be used at all",
    "data.dataset.deduplicate": "remove duplicate rows and write the result",
    "data.eval_set.carve": "carve an evaluation set out of a dataset",
    "data.eval_set.count": "count an evaluation set that already exists",
    "data.preferences.count": "count the preference pairs in a file - rows carrying a prompt, a chosen answer and a rejected one",
    "data.synthetic.amplify": "amplify structure from your own examples by sampling",
    "data.synthetic.sample_for_review": "draw the share of generated rows a person has to read",
    "data.synthetic.record_review": "record what a person judged about that sample",
    # INVENTING A DATASET, 2026-09-12 (`app/tools/invent.py`): a connected
    # model writes new rows for a task from the person's seeds, and a judge
    # scores them against the person's rubric - the generator/judge halves
    # of the loop Adaptive ML sells, with every row saying who wrote it and
    # nothing here able to open a gate.
    "data.synthetic.generate": "invent new training rows with a model from a task and your seeds",
    "data.synthetic.judge": "score generated rows against a rubric and keep the good ones",
    # Chain first, question last (ToolGrad, 2026-09-18; `app/tools/chainfirst.py`):
    # the registry runs a chain of read-only tools for real and the model
    # writes the question that chain answers.
    "data.synthetic.chain_first": "write tool-use rows by running real tool chains first, then deriving the question",
    "data.split.check_leakage": "check whether train rows appear in the eval set",
    # -- harness: the third ledger's own pack ------------------------------
    # `docs/ledgers/harness_design.yaml` declares eleven `inspect` facts and an
    # `inspect` fact with no instrument is a gate nobody can open. These six are
    # that ledger's instruments (`app/tools/harness.py`), and they are a pack of
    # their own rather than additions to `agent` for the reason the ledgers are
    # separate files: a person diagnosed on the AI ledger must not be handed a
    # tool whose success writes the harness ledger's fact ids.
    "harness.success_check.read": "read the file that decides whether an answer was right - read, never run",
    "harness.tasks.count": "count the tasks in a set and how many can be graded",
    "harness.variant.score": "grade a recorded run of one rung of the ladder",
    "harness.component.ablate": "pair a recorded with-and-without run for each component",
    "harness.tools.risk": "count the tools a harness reaches and how many say what they destroy",
    "harness.run.bound": "read one run's trace for its token total and whether it stopped",
    # -- measurement: the baseline and the eval run -------------------------
    "measurement.baseline.score": "score a baseline against an evaluation set",
    "measurement.baseline.target": "pin which local model the baseline is measured on",
    # Re-tallying a histogram over the person's OWN re-reading of the rows an
    # eval run already graded. A separate capability from `measurement.eval.run`
    # because it is a different instrument answering the same fact - the counts
    # are read off rows, the buckets are the person's - and wall 9 binds a fact
    # to capabilities so that being the wrong KIND of instrument is a refusal.
    "measurement.eval.rebucket": "re-tally a failure histogram somebody corrected",
    "measurement.eval.run": "run an evaluation and bucket what failed",
    "measurement.eval.read": "read back an evaluation that already ran",
    # -- knowledge: the freshness-stamped world, dated in every answer --------
    "context.ask.map": "the person's words, mapped to the journey that serves them",
    "data.rows.carve": "turn pointed-at files into verbatim, tagged rows",
    "knowledge.models.shortlist": "the curated model ladder with live-fetched facts",
    "knowledge.gpu.prices": "what rented GPUs ask, sampled from a live marketplace",
    "knowledge.local.recipes": "validated local-serving recipes, snapshotted with a date",
    "measurement.format.score": "count how many outputs satisfy a declared schema",
    # A SEPARATE CAPABILITY FROM `format.score`, and the difference is the whole
    # point of it. Format asks whether an output satisfies a schema; this asks
    # whether the RELATIONS in it point the right way, which a schema cannot
    # express - a graph with every arrow reversed is perfectly valid. It returns
    # a pair rather than a score, because direction is scored over matched edges
    # and a model that matches nothing therefore reverses nothing: a constant
    # answer measured 0.0% reversed, the best possible value, against a real
    # model's 26.5%. Coverage travels with the share or neither is quoted.
    "measurement.direction.score": (
        "score which way relations point, with coverage beside the share"
    ),
    # A PAIRING IS NOT TWO SCORES. b and c need to know WHICH edges changed,
    # not how many each arm got, and two shares cannot be paired. This was
    # hand-built twice for kill 13 - and the second time its model-identity
    # columns committed EMPTY, because backticks in a shell string were read
    # as command substitution. A table that says nothing looks exactly like a
    # table that says something.
    "measurement.direction.pair": (
        "pair two runs edge by edge, with each arm's model named in the table"
    ),
    # -- prompt: the cheapest thing, exhausted -------------------------------
    "prompt.attempt.score": "score a prompt change against the eval set",
    "prompt.bench.read": "read back what the prompt attempts scored",
    # -- retrieval: the other cheap thing ------------------------------------
    "retrieval.index.build": "build a retrieval index over a corpus",
    "retrieval.index.search": "search a retrieval index",
    "retrieval.recall.score": "measure what a retriever actually recalls",
    "retrieval.chunking.compare": "sweep chunkings and report what each scored",
    # -- tabular: the classical branch ---------------------------------------
    "tabular.tree.fit": "fit a gradient-boosted tree on a table",
    # -- models: which one, for this machine and this job --------------------
    "models.candidate.find": "find candidate base models",
    "models.config.read": "read a model's configuration",
    # Scoring a model NOBODY HAS TRAINED, on the person's own rows. It sits in
    # the `models` pack rather than `measurement` on purpose: it answers "is
    # this candidate any good", which is a question about choosing a model, and
    # `measurement.*` is where the facts that open gates are measured. This one
    # stamps nothing - see `score_a_candidate_model`.
    "models.candidate.score": "score a candidate model on rows already graded",
    # -- training: the expensive irreversible half ---------------------------
    "training.feasibility.check": "decide whether this machine can train a model",
    "training.feasibility.record": "record that this card refuses a model, and by how much",
    "training.placement.choose": "decide where a training run should happen",
    "training.recipe.list": "list the pinned training recipes",
    "training.run.start": "start a training run",
    "training.run.status": "report on a training run",
    "training.adapter.score": "score a trained adapter against the eval set",
    # THE RUN ENDS IN RESULTS AND AN ARTICLE (2026-09-18, Max: *"what elements
    # and tools and built frameworks do we provide for this training and
    # working loop"*, and earlier, that a run should end in "results and
    # article"). In `training` rather than `measurement` for the reason
    # `models.candidate.score` is in `models`: `measurement.*` is where the
    # facts that open gates are MEASURED, and this stamps nothing at all - it
    # reads what the thread already measured and writes it down. Its subject is
    # a training run, and the person holding a finished run is the person who
    # needs the write-up.
    "training.results.write": "write up a training run's results and a draft article",
    # -- sandbox: where a build runs -----------------------------------------
    "sandbox.instance.create": "create an isolated, pinned, egress-free directory",
    # BUILDING one, as against MAKING one. `instance.create` makes a directory
    # and reports what a RECIPE pinned; this makes the sandbox's own virtualenv,
    # installs the requirements into it, records the versions that landed, and
    # asks that environment whether it can see the card.
    "sandbox.environment.build": "build a sandbox's own environment and check its GPU",
    "sandbox.instance.list": "list the sandboxes on this machine",
    "sandbox.instance.run": "run a pinned recipe inside a sandbox",
    "sandbox.shell.run": "run a free-text shell command inside a sandbox work dir",
    "sandbox.instance.delete": "dispose of a sandbox",
    # -- agent: somebody else's agent, READ rather than run -------------------
    #
    # THE ARGUMENT FOR A NEW PACK, and it is the same mechanical one this file
    # already makes for the core: *a capability is core only if EVERY ledger
    # would name it, and the test for "every" is a ledger that does not exist
    # yet.* The docstring above names a trace reader as the example that FAILS
    # that test, written before one existed. A data ledger does not want one; a
    # machine ledger does not want one; the AI-engineering ledger cannot be
    # honest without one. That is a pack.
    #
    # And it is a pack rather than four names spread across `measurement` and
    # `context`, because what they have in common is not the file type - it is
    # the SUBJECT. These four read a system that is not this harness and that
    # this harness will never run: somebody else's traces, somebody else's tool
    # schemas, somebody else's failures, somebody else's loop. Every other pack
    # here acts on the user's data or on this machine. `agent.*` is the first
    # one whose whole subject is a third system, and the rule that follows from
    # that - never execute it, read files, refuse and name what was needed - is
    # a property of the pack rather than of any one tool in it.
    "agent.traces.read": "read a trace file and report what an agent did",
    "agent.tools.read": "read tool definitions and report what they declare",
    "agent.failures.run": "re-run a failure set against an agent and score it",
    "agent.results.read": "read back a graded failure run, or compare two of them",
    "agent.loop.bound": "measure steps, tokens and termination over runs",
}


#: One line per pack, for a person reading a label. Derived membership means
#: this cannot hide a tool: a pack with no gloss still renders with its name.
PACKS: dict[str, str] = {
    "machine": "what is already in this box",
    "context": "what the person pointed at, and what is inside it",
    "ledger": "the engine's own doors, and the evidence door",
    "data": "getting data into a state something can be measured on",
    "measurement": "the baseline, and what an evaluation actually scored",
    "prompt": "the cheapest thing, and whether it has been exhausted",
    "retrieval": "an index, and what it actually recalls",
    "tabular": "the classical branch: a model that is not a language model",
    "models": "which model, for this machine and this job",
    "training": "training itself, which this harness runs rather than describes",
    "sandbox": "an isolated, pinned, egress-free place for a build to run",
    "agent": "somebody else's agent, read rather than run",
    "harness": "whether to build a harness at all, and which of its parts earn their place",
    "knowledge": "the world as of a date: model ladder, rented-compute asks",
    "intent": "goal and todo edits the person invited for this turn only",
}


#: ALWAYS ON. The closure of the selector - see the module docstring for the
#: argument, which is mechanical: the packs are chosen by the walk, so what the
#: walk depends on cannot itself be selectable.
#:
#: A ledger may WIDEN this with `contract.capabilities.core`. It may not narrow
#: it, and `_core_packs` says why in one sentence: a ledger that could switch
#: `run_diagnosis` off could switch off the thing that reads the ledger.
CORE: tuple[str, ...] = ("ledger", "context", "machine")


def packs() -> tuple[str, ...]:
    """Every pack the vocabulary defines, in declaration order.

    Derived from `CAPABILITIES`, never listed beside it, so a capability added
    under a new namespace is a pack on the day it is added. `PACKS` holds the
    glosses and is checked against this by the suite rather than trusted.
    """
    seen: dict[str, None] = {}
    for name in CAPABILITIES:
        seen.setdefault(pack_of(name), None)
    return tuple(seen)


def pack_of(capability: str) -> str:
    """The first dotted segment. THE PACK IS THE NAMESPACE - there is no table."""
    return str(capability).split(".", 1)[0]


def check_name(capability: str) -> str:
    """Refuse anything the engine does not publish, and name what would work.

    A refusal that names nothing is a wall with no door; this file has the whole
    vocabulary in front of it, so the door is the list.
    """
    name = str(capability)
    if not NAME_RE.match(name):
        raise BlockError(
            f"{capability!r} is not a usable capability name. Two or three "
            "dotted segments, lower case, digits and underscores - `pack.thing` "
            "or `pack.thing.verb`. The first segment is the pack, which is why "
            "a bare word is refused: it names a namespace, not a capability."
        )
    if name not in CAPABILITIES:
        near = [
            published
            for published in CAPABILITIES
            if pack_of(published) == pack_of(name)
        ]
        raise BlockError(
            f"{capability!r} is not a capability this engine publishes. The "
            "vocabulary is closed on purpose: a ledger binds to these names and "
            "a misspelling that became a new capability would be a pack nobody "
            "can ask for. Add it to `CAPABILITIES` in app/tools/blocks.py, with "
            "a gloss, in the same change that needs it."
            + (
                f" Published under {pack_of(name)!r}: {', '.join(sorted(near))}."
                if near
                else f" Packs: {', '.join(packs())}."
            )
        )
    return name


def check_pack(name: str) -> str:
    """Refuse a pack name nothing publishes. The ledger's door into this file."""
    if str(name) not in packs():
        raise BlockError(
            f"{name!r} is not a pack this engine publishes. A ledger may name "
            f"any of: {', '.join(packs())}. Pack names are the first segment of "
            "a published capability - there is no separate list to add one to."
        )
    return str(name)


# ---------------------------------------------------------------------------
# What the registry provides, read off the registry.


def _registry(registry: Any | None) -> Any:
    """`REGISTRY`, imported when asked for rather than at module import.

    `app/tools/registry.py` imports this module to validate `provides=`, so a
    top-level import back would close the circle. The same laziness
    `app/instructions/capabilities.py` uses, for the same reason.
    """
    if registry is not None:
        return registry
    from app.tools.registry import REGISTRY

    return REGISTRY


def providers(capability: str, registry: Any | None = None) -> tuple[str, ...]:
    """Which registered tools provide this capability. Possibly none.

    NONE IS AN ANSWER AND NOT AN ERROR. `docs/PHASES.md` names four tools the
    AI-engineering ledger cannot be honest without and none of them exists; a
    ledger that binds to one of them must be told exactly that, with the
    capability named, rather than handed a plan whose first step moves nothing.
    """
    name = str(capability)
    return tuple(
        spec.name for spec in _registry(registry) if name in spec.provides
    )


def tools_in(names: Iterable[str], registry: Any | None = None) -> tuple[str, ...]:
    """Every registered tool in any of these packs, in declaration order."""
    wanted = {str(one) for one in names}
    return tuple(
        spec.name for spec in _registry(registry) if spec.packs & wanted
    )


def pack_index(registry: Any | None = None) -> dict[str, tuple[str, ...]]:
    """pack -> the tools in it, derived from `provides=` and nothing else."""
    out: dict[str, list[str]] = {}
    for spec in _registry(registry):
        for one in sorted(spec.packs):
            out.setdefault(one, []).append(spec.name)
    return {name: tuple(tools) for name, tools in out.items()}


def pack_of_tool(name: str, registry: Any | None = None) -> frozenset[str]:
    """The packs one tool belongs to. Empty for a name nothing registered."""
    spec = _registry(registry).get(str(name))
    return spec.packs if spec is not None else frozenset()


# ---------------------------------------------------------------------------
# What a ledger declares. Read when it is there; never invented when it is not.


@dataclass(frozen=True)
class Declared:
    """`contract.capabilities`, as this engine reads it. Empty when absent.

    THREE FIELDS AND NO DEFAULTS INSIDE THEM. `docs/LEDGER_FORMAT.md` §3's rule
    is that a stage with nothing extra to ask for writes `needs: []` - empty is a
    legal answer and absent is not, because "this stage needs nothing" and
    "somebody forgot" are different and a default would erase the difference.
    That rule binds a ledger AUTHOR. It cannot bind a ledger written before the
    block existed, and `present` is how the two are told apart here: a ledger
    that declares nothing is reported as declaring nothing, and `active()` says
    so in the reason it writes rather than pretending a `[]` was authored.
    """

    present: bool = False
    core: tuple[str, ...] = ()
    needs: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    builds: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


def check_fact_instruments(spec: Any) -> dict[str, tuple[str, ...]]:
    """Read `measured_by:` off every fact, checking each name as it goes.

    THE OTHER PLACE A LEDGER NAMES A CAPABILITY. `contract.capabilities` says
    which packs a STAGE's work needs; a fact's `measured_by:` says which
    capability may READ it - wall 9 in `app/tools/evidence.py`. Both bind the
    ledger to this file's closed vocabulary, so both are checked here, by
    `check_name`, and a misspelling is a refused ledger rather than a fact that
    quietly admits nothing.

    THE MISSPELLING IS THE DANGEROUS DIRECTION AND IT IS WORTH SAYING WHY. An
    unchecked `measured_by: [data.eval_set.cout]` would name a capability no
    tool provides, so wall 9 would refuse EVERY instrument for that fact - the
    fact would become unmeasurable, its gate would never open, and the product
    would tell somebody to go and measure something no tool of its own can
    measure. That is a silent, total failure produced by one dropped letter.
    """
    found: dict[str, tuple[str, ...]] = {}
    for name, declaration in (getattr(spec, "facts", None) or {}).items():
        if not isinstance(declaration, Mapping):
            continue
        wanted = declaration.get("measured_by")
        if not wanted:
            continue
        if isinstance(wanted, str):
            wanted = [wanted]
        found[str(name)] = tuple(check_name(one) for one in wanted)
    return found


def declared(spec: Any) -> Declared:
    """Read `contract.capabilities` off a loaded ledger, or report its absence.

    THIS FILE DOES NOT LOAD YAML: it reads `Spec.contract`, which the engine has
    already parsed and validated. Both shipped ledgers now carry the block - the
    ML ledger's `needs:` was taken from `Spec.outcome_sites()`, the AI ledger's
    is five empty lists and the comment above them says why - and a ledger
    written before the block existed still returns `Declared()` with nothing
    guessed.

    Every name is checked against the published vocabulary as it is read. A
    ledger that names `capabilties` or `retrievel` is refused loudly rather than
    silently ignored, which is exactly the hazard `_refuse_unknown_keys` was
    written for one level up: *"a misspelled key that becomes an annotation is
    that defect with a new spelling."*

    ## One departure from the research, and the reason is the document's shape

    `docs/CAPABILITY_BLOCKS.md` §4 puts a stage's packs on the stage:

        stages:
          stage_0_admissibility:
            needs: [data]

    There is no `stages:` mapping in either shipped ledger. A stage is a
    top-level key whose value is a bare LIST of nodes - `stage_0_admissibility:`
    followed by twelve `- node:` entries - so there is nowhere on it to hang a
    sibling key without turning every stage in every ledger from a list into a
    mapping, which is a restructuring of the whole document body rather than a
    new block in it.

    So `needs:` lives inside `contract.capabilities`, keyed by stage, beside
    `core` and `builds`. It is the same information, it costs one closed block
    instead of a rewrite of every ledger's body, and it gains something the
    research's shape could not have: a stage name that matches no stage is
    REFUSED here, because this block can be checked against `Spec.stages` in one
    place. On the stage itself, a misspelling would simply have been a stage
    nobody ever selected.
    """
    # BEFORE THE EARLY RETURN, because a fact may name an instrument in a
    # ledger that has no `contract.capabilities` block at all, and a check that
    # only ran for ledgers carrying one would skip exactly the older files most
    # likely to have a typo in a block nobody has read recently.
    check_fact_instruments(spec)

    contract = getattr(spec, "contract", None) or {}
    block = contract.get("capabilities") if isinstance(contract, Mapping) else None
    if not isinstance(block, Mapping):
        return Declared()

    unknown = sorted(set(block) - _CAPABILITY_KEYS)
    if unknown:
        raise BlockError(
            f"contract.capabilities declares {unknown}, which this engine does "
            f"not read. The keys are {', '.join(sorted(_CAPABILITY_KEYS))}."
        )

    core = tuple(check_pack(one) for one in (block.get("core") or ()))
    builds = {
        str(outcome): tuple(check_name(one) for one in (wanted or ()))
        for outcome, wanted in (block.get("builds") or {}).items()
    }

    stages = set(getattr(spec, "stages", None) or {})
    needs: dict[str, tuple[str, ...]] = {}
    for stage, wanted in (block.get("needs") or {}).items():
        name = str(stage)
        if stages and name not in stages:
            raise BlockError(
                f"contract.capabilities.needs names a stage {name!r} this ledger "
                "does not have. A stage nothing matches is a declaration that "
                "silently does nothing, which is the drift a closed block exists "
                f"to refuse. This ledger's stages: {', '.join(sorted(stages))}."
            )
        needs[name] = tuple(check_pack(one) for one in (wanted or ()))

    # AND THE OTHER DIRECTION, WHICH IS THE ONE THAT WAS MEASURED TO MATTER.
    # A stage named here that the ledger does not have is refused above; a stage
    # the ledger HAS and this block does not name was, until 2026-08-24, a
    # silently narrow turn. That is the failure this whole block exists to stop,
    # so it may not be reintroduced by omission: `docs/LEDGER_FORMAT.md` §3's
    # rule is that empty is a legal answer and absent is not, and the difference
    # between "this stage's work needs nothing extra" and "somebody forgot" is
    # exactly the difference between a scoped turn and a broken one.
    #
    # IT BINDS ONLY A LEDGER THAT DECLARES. `present` is false for a ledger
    # written before the block existed and nothing here fires for it - the check
    # is "if you declare, declare completely", not "every ledger must declare".
    missing = sorted(stages - set(needs))
    if missing:
        raise BlockError(
            "contract.capabilities is declared but its needs: does not name "
            f"{', '.join(missing)}. Every stage this ledger has must appear, "
            "with an empty list where the stage's work needs no pack beyond the "
            "core. A stage left out is a stage whose answer reaches a person "
            "with the tools that would act on it unloaded, which is the defect "
            "this block was written to close."
        )

    return Declared(present=True, core=core, needs=needs, builds=builds)


#: The keys `contract.capabilities` may hold. `knowledge` is read here only to
#: be permitted: `docs/CAPABILITY_BLOCKS.md` §8.2 gives it to the four hardcoded
#: NODE ids - `ledger.knowledge("failure.buckets")` - which is a question about
#: where a ledger keeps a piece of knowledge, not about which pack loads. It
#: belongs to the module that owns node ids; refusing it here would refuse an
#: honest format-4 ledger for using a block this file has no business reading.
_CAPABILITY_KEYS = frozenset({"core", "needs", "builds", "knowledge"})


# ---------------------------------------------------------------------------
# The selection.


#: Why a pack is on. One clause per source, and every one of them is a record of
#: something that happened rather than a category. `docs/PHASES.md`'s
#: done-condition is a visible LABEL, and a label with no reason is a number with
#: no provenance.
BECAUSE_CORE = "the core is loaded on every turn of every thread"
BECAUSE_DECLARED_CORE = "this ledger declares it core"
BECAUSE_STAGE = "the ledger's {stage} declares it in needs:"
BECAUSE_BUILD = "the ledger says a build for {outcome} needs {capability}"
BECAUSE_DIAGNOSIS = "the diagnosis reached {outcome} and names {tool} as the move"
BECAUSE_UNSUBSTANTIATED = "{fact} was claimed rather than measured, and {tool} settles it"
BECAUSE_EVIDENCE = "{tool} measured {fact} on this thread"
BECAUSE_RESTS_ON = "this answer rests on {fact}, and {tool} is what reads it"
BECAUSE_THE_WALK_IS_STUCK = (
    "the walk is stopped on {fact}, which no tool measures, so withholding "
    "{tool} could not have helped"
)


@dataclass(frozen=True)
class Active:
    """The packs this turn runs under, the tools that follow, and why each pack.

    `tools` is derived from `packs` and the live registry, never carried beside
    it. Two fields that must agree is the drift machine at the smallest possible
    scale; one field and a derivation cannot disagree with itself.
    """

    packs: frozenset[str]
    tools: tuple[str, ...]
    because: Mapping[str, str]

    def names(self) -> tuple[str, ...]:
        return self.tools

    def as_dict(self) -> dict[str, Any]:
        """What goes on the wire, in `turn.started` and in `blocks.changed`."""
        return {
            "packs": sorted(self.packs),
            "tools": list(self.tools),
            "because": {name: self.because[name] for name in sorted(self.because)},
        }


#: Why every pack is on. THE DEFAULT DIRECTION OF BEING WRONG, stated as a
#: reason a person reads rather than as a silent fallback.
BECAUSE_NO_WALK = (
    "the diagnosis could not be computed for this turn, so nothing narrowed the set"
)


def everything(registry: Any | None = None, because: str = BECAUSE_NO_WALK) -> Active:
    """Every pack on, which is what the product did before this file existed.

    Used where there is genuinely no diagnosis to select from - `run_turn`
    reaches it when the walk could not be computed at all, and `active` reaches
    it when a ledger's own capability block cannot be read. **A turn that could
    not compute a selection gets MORE tools, not fewer**, because the expensive
    direction of being wrong here is a person who cannot reach the thing they
    need, and a failure to select is not evidence about their situation.

    `because` is carried rather than defaulted silently, so the widening always
    arrives with the sentence that explains it. A label with no reason is a
    number with no provenance.
    """
    live = sorted({one for spec in _registry(registry) for one in spec.packs})
    return Active(
        packs=frozenset(live),
        tools=tools_in(live, registry),
        because={name: because for name in live},
    )


def active(
    payload: Mapping[str, Any] | None,
    *,
    thread_id: int | None = None,
    spec: Any | None = None,
    registry: Any | None = None,
    evidence_rows: Iterable[Mapping[str, Any]] | None = None,
) -> Active:
    """The packs this turn gets. Chosen by the walk that has already happened.

    ## Four sources, unioned, and none of them is the model

    1. **The core**, always - plus whatever this ledger declares core on top.
    2. **What the ledger declares** for the standing stage (`needs:`) and for the
       standing outcome (`contract.builds`). Absent from both shipped ledgers
       today; read the moment it is written, with nothing here to change.
    3. **What the diagnosis itself named**, in two readings of the same join.
       `run_diagnosis` already puts the tools that would move this thread forward
       on the wire - `alternatives` from the node's own words through
       `evidence.resolves`, and `unsubstantiated[].next_step` from the fact a
       gate is waiting on. And beneath both, the facts the answer actually rests
       on: the FAILED gate's row, or the frontier node's own condition, read out
       of the engine's compiled indexes. `alternatives` names at most one tool
       per move because a card holds three rows; a pack is not a card, so this
       reads the whole set rather than the one that fit.
    4. **What this thread has measured.** A pack stays for as long as a tool in
       it has stamped something here, because a model that measured a number and
       can no longer talk about it is worse than one that never measured it.

    ## Why 3 is on even when 2 is declared, rather than instead of it

    The obvious version makes the derivation a fallback for the declaration.
    That is wrong in the direction this product cares about. A stage's `needs:`
    is the AUTHOR's statement about the work below it, written once, in advance,
    for every thread; the diagnosis's `alternatives` is what the engine reached
    on THIS sheet a millisecond ago. The second is more specific and it is the
    one that follows a thread when the work turns out to be something else -
    which `docs/PHASES.md` records happening in the only real journey there has
    been, ten rungs of ML diagnosis landing on an answer about decoding. Making
    the specific one conditional on the general one being absent would switch it
    off exactly when a ledger got more careful.

    So a declaration WIDENS. It removes the one-turn lag - a stage that knows its
    work needs the data floor gets it before a fact has named it - and it cannot
    narrow anything, which is the same shape as `CORE`.

    ## Bounded, and that is a property rather than a hope

    Every source is finite in the work actually done: the core is a constant, the
    declarations are one stage and one outcome, the diagnosis names at most three
    alternatives and its unsubstantiated rows, and the evidence is one row per
    fact this thread has measured. A long thread does not converge on "everything
    loaded"; it converges on "everything this thread has evidence about", which
    is the correct set. `docs/CAPABILITY_BLOCKS.md` §7 rejects accumulate-forever
    for precisely the reason it would be the 40-tool problem reached slowly.
    """
    if payload is None:
        # No walk, no selection. Everything, and the reason on every pack -
        # less whatever this project switched off, which is a person's choice
        # and outranks "we could not compute a selection".
        whole = everything(registry)
        return _minus_what_was_switched_off(dict(whole.because), thread_id, registry)

    spec = _spec(spec)
    known = set(packs())
    reasons: dict[str, str] = {}

    def add(name: str, why: str) -> None:
        one = str(name)
        if one and one in known:
            reasons.setdefault(one, why)

    # 0. What this ledger DECLARES, read first because reading it can fail and a
    #    ledger whose own block is malformed must not quietly get a narrow turn.
    #    Loud where an author can see it, wide where a user is standing: the
    #    refusal is the exception `declared` raises at load-time review, and the
    #    running product widens rather than guesses.
    try:
        book = declared(spec) if spec is not None else Declared()
    except BlockError as error:
        return everything(
            registry,
            because=f"this ledger's contract.capabilities could not be read: {error}",
        )

    # 1. The core, and whatever this ledger adds to it. Never less.
    for name in _core_packs(book):
        add(name, BECAUSE_CORE if name in CORE else BECAUSE_DECLARED_CORE)

    outcome = str(payload.get("outcome") or "")

    # 2. What the ledger declares about this stage and this outcome.
    stage = _stage_of(payload, spec)
    for name in book.needs.get(stage, ()):
        add(name, BECAUSE_STAGE.format(stage=stage))
    for capability in book.builds.get(outcome, ()):
        add(
            pack_of(capability),
            BECAUSE_BUILD.format(outcome=outcome, capability=capability),
        )

    # 3. What the diagnosis named as the next move, on this sheet, just now.
    for row in payload.get("alternatives") or ():
        if not isinstance(row, Mapping):
            continue
        for name in pack_of_tool(str(row.get("tool") or ""), registry):
            add(name, BECAUSE_DIAGNOSIS.format(outcome=outcome, tool=row.get("tool")))
    for row in payload.get("unsubstantiated") or ():
        if not isinstance(row, Mapping):
            continue
        step = row.get("next_step")
        tool = str((step if isinstance(step, Mapping) else {}).get("tool") or "")
        for name in pack_of_tool(tool, registry):
            add(
                name,
                BECAUSE_UNSUBSTANTIATED.format(fact=row.get("fact"), tool=tool),
            )
    for fact in rests_on(payload, spec):
        for tool in _measured_by(fact, registry):
            for name in pack_of_tool(tool, registry):
                add(name, BECAUSE_RESTS_ON.format(fact=fact, tool=tool))

    # 5. THE INSTRUMENTS THE WALK CANNOT REACH, WHEN THE WALK CANNOT MOVE.
    #
    # MEASURED 2026-09-13, thread 70 of the owner's own database, nine turns:
    # the walk sat at `S0_RULES_SUFFICE`, whose condition reads `task_family`,
    # a fact declared `source: derive` - no tool measures it, so nothing the
    # engine could offer would ever settle it. Sources 1-4 above therefore
    # offered 36 tools, and `measure_baseline`, `try_prompt`,
    # `build_retrieval_index` and `measure_retriever_recall` were not among
    # them. The model announced `measure_baseline` on every one of those nine
    # turns, could not call it, called `measure_eval_set` on the same file
    # twice instead, tripped the repeat guard and ended. Forever.
    #
    # Max, the same afternoon: *"we don't overpopulate too many requirements
    # and too many tools, the models get stuck in infinite loops... if you
    # could measure it, you could finish it, go do it. If you can't, then let's
    # take a step back."* This is the taking a step back, and it is the only
    # place the scoping may widen for a reason that is not a fact: a frontier
    # nothing can settle is not a reason to keep the instruments in the drawer,
    # because there is no move that opens the drawer. So every pack that
    # measures any fact any gate of this ledger reads comes on, and the walk
    # stops being a gate on the work.
    #
    # It is still bounded, and by the same argument the docstring makes: the
    # gates are a constant of the ledger, so this is a fixed set, not an
    # accumulation. And it fires only when the frontier is unsettleable - a
    # thread whose next move is a tool call gets exactly the narrow turn it
    # has always got.
    if spec is not None:
        stuck_on = _what_no_tool_can_settle(payload, spec, registry)
        if stuck_on:
            # MINIMAL COVER, NOT EVERY GATE. Loading instruments for every fact
            # any gate of the ledger reads ballooned the stuck-walk set; the
            # work that can still move the thread is on gates the walk has not
            # PASSED yet. Soften clouding without putting the drawer shut again.
            for fact in sorted(_facts_unsettled_gates_read(payload, spec)):
                for tool in _measured_by(fact, registry):
                    for name in pack_of_tool(tool, registry):
                        add(name, BECAUSE_THE_WALK_IS_STUCK.format(fact=stuck_on, tool=tool))

    # 4. What this thread has already measured.
    for row in _evidence(thread_id, evidence_rows):
        tool = str(row.get("tool") or "")
        for name in pack_of_tool(tool, registry):
            add(name, BECAUSE_EVIDENCE.format(tool=tool, fact=row.get("fact")))

    # 5. AND WHAT THE PERSON SWITCHED OFF. Max, 2026-09-14: *"make sure the
    #    models aren't clouded with too many tools and guidelines so that they
    #    can have free roam."* MEASURED on his database that day: 12,735 tokens
    #    of tool schemas for 44 tools, against 3,562 tokens of conversation.
    #
    #    LAST, AND SUBTRACTIVE, which is the only safe place for it. The four
    #    sources above are the engine's reasoning about what this turn needs;
    #    this is a person overruling it. Putting it first would have the walk
    #    reason about packs that are not going to be offered and produce
    #    "because the walk is stuck on X" for a tool nobody can call.
    #
    #    A SUB-AGENT ALSO NARROWS HERE. Its plan is one phase; tools named in
    #    those steps name the packs it needs. Core stays; everything else that
    #    no step named drops out so the child is a freer, smaller worker.
    reasons = _narrow_to_phase_packs(reasons, thread_id, registry)
    return _minus_what_was_switched_off(reasons, thread_id, registry)


def _narrow_to_phase_packs(
    chosen: dict[str, str], thread_id: int | None, registry: Any | None
) -> dict[str, str]:
    """Keep core + the packs the work in front of the model names.

    Two callers narrow here. A SUB-AGENT's whole plan is one phase, so every
    tool its steps name is in scope. A PARENT ON A LIVE RUN narrows to the
    phase its first open step sits in - its `**Tools:**` line and the tools
    its steps name - because that is the work this turn is for.

    Max, 2026-09-17, measured on thread 75: 51 tools and 13.5k tokens of
    schema on every turn of a run whose aimed phase named one tool. The
    plan already says which tools each phase uses; a turn that carries the
    other eight packs is carrying them for nobody.
    """
    if thread_id is None:
        return chosen
    try:
        from app import subagents as _subagents
        from app import events as _events
        from app.tools.registry import REGISTRY as _reg

        live = registry if registry is not None else _reg
        row = _events.get_thread(int(thread_id)) or {}
        plan = row.get("plan") or ""
        if _subagents.is_a_subagent(int(thread_id)):
            scope = " ".join(str(step.get("text") or "") for step in planning_steps(plan))
        elif _a_run_is_live(int(thread_id)):
            scope = phase_of_first_open_step(plan)
        else:
            return chosen
        named: set[str] = set()
        low = scope.lower()
        for spec in live:
            name = str(getattr(spec, "name", "") or "")
            if name and name.lower() in low:
                named.update(pack_of_tool(name, live))
        if not named:
            return chosen
        keep = set(CORE) | named
        return {pack: why for pack, why in chosen.items() if pack in keep}
    except Exception:  # noqa: BLE001 - never fail a turn over a phase parse
        return chosen


def _a_run_is_live(thread_id: int) -> bool:
    from app import longrun as _longrun

    run = _longrun.status(int(thread_id)) or {}
    return str(run.get("state") or "") == _longrun.RUNNING


def phase_of_first_open_step(plan: str) -> str:
    """The text of the `## ` section holding the first open step, or empty.

    The section runs from its heading to the next `## ` heading, so a phase's
    `**Tools:**` line and its steps are both in it.
    """
    steps = planning_steps(plan)
    if not steps:
        return ""
    lines = str(plan or "").splitlines()
    at = int(steps[0]["line"])
    start = at
    while start > 0 and not lines[start].strip().startswith("## "):
        start -= 1
    end = at + 1
    while end < len(lines) and not lines[end].strip().startswith("## "):
        end += 1
    return chr(10).join(lines[start:end])


def planning_steps(plan: str) -> list[dict[str, Any]]:
    """Open steps of a plan, imported late to avoid a cycle at module load."""
    from app.tools import planning as _planning

    return list(_planning.open_steps(plan))


def _minus_what_was_switched_off(
    chosen: dict[str, str], thread_id: int | None, registry: Any | None
) -> Active:
    """The packs, less the ones this project turned off, as an `Active`.

    BOTH PATHS GO THROUGH HERE, and the first cut of this did not - the filter
    sat at the end of the reasoned path only, so `active(None, ...)` (no walk,
    everything offered) ignored the switches entirely. That is the path a fresh
    thread takes, which is exactly when a person's "stop offering me the data
    pack" matters most. Caught by the test rather than by reading it.

    THE CORE IS NOT REMOVABLE. A turn with no ledger tools cannot write a plan
    or tick a step, so switching it off would not make the model freer, it
    would make it mute - and the person would read that as the model failing
    rather than as a switch they threw.
    """
    off = _switched_off(thread_id)
    if off:
        chosen = {
            name: why
            for name, why in chosen.items()
            if name not in off or name in CORE
        }
    names = frozenset(chosen)
    return Active(packs=names, tools=tools_in(names, registry), because=chosen)


def _switched_off(thread_id: int | None) -> frozenset[str]:
    """Packs this project's settings say not to offer. Empty on any fault.

    Fails OPEN - every pack offered - because failing closed would silently
    take a person's tools away and leave them blaming the model for not using
    them. A settings table that cannot be read is a settings table nobody set.
    """
    if thread_id is None:
        return frozenset()
    try:
        from app import settings as _settings

        return frozenset(_settings.for_thread(int(thread_id)).get("packs_off") or ())
    except Exception:  # noqa: BLE001 - a missing table must not end a turn
        return frozenset()


def _what_no_tool_can_settle(
    payload: Mapping[str, Any],
    spec: Any,
    registry: Any | None = None,
) -> str:
    """The frontier fact no instrument reads, or `""` when a tool could move it.

    A fact is unsettleable here when nothing in the registry DECLARES it in
    `measures=`. That is the same index `_measured_by` reads and the same one
    the diagnosis's `settled_by` is written against, so this cannot disagree
    with what the engine would offer - it is that offer coming back empty.

    Names the first such fact rather than all of them: the reason string wants
    one, and one is enough to know the frontier is not a tool call away.
    """
    for fact in rests_on(payload, spec):
        if not _measured_by(fact, registry):
            return str(fact)
    return ""


def _every_fact_a_gate_reads(spec: Any) -> frozenset[str]:
    """Every fact any gate of this ledger rests on, from the compiled index.

    `spec.gate_row_facts` is parsed at load time by the engine itself and keyed
    `(gate_id, method_class)`; the union of its values is what the whole ledger
    could ever need measured. Read rather than re-parsed for the reason
    `rests_on` gives: two readers of one source become one wrong reader.
    """
    rows = getattr(spec, "gate_row_facts", None)
    if not rows:
        return frozenset()
    out: set[str] = set()
    for facts in rows.values():
        out.update(str(fact) for fact in facts)
    return frozenset(out)


def _facts_unsettled_gates_read(
    payload: Mapping[str, Any] | None, spec: Any
) -> frozenset[str]:
    """Facts that gates the walk has not PASSED still read.

    The stuck-walk cover used to union every gate's facts. A thread blocked on
    an early derive fact then loaded instruments for G2–G4 as well, which is
    clouding without a move. Restricting to non-PASSED gates keeps
    `measure_baseline` reachable when G1 is open work, and drops packs whose
    gates the walk has already cleared or never needs on this path.
    """
    rows = getattr(spec, "gate_row_facts", None) or {}
    if not rows:
        return frozenset()
    ledger = (payload or {}).get("gate_ledger") if isinstance(payload, Mapping) else None
    if not isinstance(ledger, Mapping) or not ledger:
        return _every_fact_a_gate_reads(spec)
    out: set[str] = set()
    for (gate_id, _row), facts in rows.items():
        status = (ledger.get(gate_id) or {}).get("status")
        if status == "PASSED":
            continue
        out.update(str(fact) for fact in facts)
    return frozenset(out) if out else _every_fact_a_gate_reads(spec)


def _spec(spec: Any | None) -> Any:
    """The ledger this selection is being made against.

    THROUGH `evidence.spec()` AND DELIBERATELY NOT THROUGH
    `diagnosis.default_spec()`. `docs/CAPABILITY_BLOCKS.md` §8.1 counts 33 sites
    that want "the ledger this thread is running, whichever one that is", and
    names the cheapest fix: thread the handle into the three functions in
    `app/tools/evidence.py` and seventeen sites in eight modules follow. This is
    an eighteenth, written on the right side of that line on the day it is
    written, so when the per-thread handle lands there is nothing here to edit.
    Calling `default_spec()` from this file would have been one more site on the
    wrong side of it.

    Returns `None` rather than raising if the ledger cannot be read at all: the
    declaration and the fact-derived source go quiet, the core and the thread's
    own evidence still choose a set, and a turn is not lost to it.
    """
    if spec is not None:
        return spec
    from app.tools import evidence

    try:
        return evidence.spec()
    except Exception:  # noqa: BLE001 - a turn is not lost to a ledger read
        return None


def _core_packs(book: Declared) -> tuple[str, ...]:
    """`CORE`, widened by whatever this ledger declares core. Never narrowed.

    A ledger that could REMOVE `ledger` from the core could remove the tool that
    reads the ledger, and the selection would have selected away the selector.
    `docs/CAPABILITY_BLOCKS.md` §6 names that trap and Anthropic's tool-search
    API enforces the same invariant from the other end with a 400. So the union,
    in one line, and the direction is not configurable: there is no syntax for a
    ledger to say "not this one", because there is no answer to "then what reads
    me".
    """
    return tuple(dict.fromkeys((*CORE, *book.core)))


def _measured_by(fact: str, registry: Any | None = None) -> tuple[str, ...]:
    """Every registered tool that declares `measures=` on this fact.

    A REGISTRY LOOKUP AND NOT A LEDGER ONE, deliberately. `evidence.resolves`
    answers the neighbouring question and answers it better for a person - it
    picks the tool that asks least of them and writes a sentence about it - but
    it reaches the ledger to do so, and reaching the ledger from here would put
    this file in the coupling `docs/CAPABILITY_BLOCKS.md` §8.1 exists to remove.
    A pack does not need the cheapest door; it needs all of them, which is the
    `measures=` declarations and nothing else.
    """
    name = str(fact)
    return tuple(
        spec.name for spec in _registry(registry) if name in spec.measures
    )


def rests_on(payload: Mapping[str, Any], spec: Any | None) -> tuple[str, ...]:
    """The facts this answer actually rests on: the gate row's, or the node's.

    THE SAME RULE `app/tools/next_moves.py::_facts_behind` USES, against a
    payload rather than a `Diagnosis`, and reading the engine's own compiled
    indexes rather than parsing anything again: `gate_row_facts` for a run a gate
    stopped, the node's compiled condition otherwise. Both were parsed at load
    time, and `gate_row_facts`'s own docstring gives the reason this is derived
    rather than listed - *"a fact added to a gate row next year is covered on the
    day it is added and not on the day somebody remembers."*

    ONLY THE GATE THAT FAILED, never every gate the walk touched. A run that
    passed G0 through G4 touched every fact in the gate tree; treating that as
    "what this answer rests on" would load nearly every pack on exactly the
    threads that got furthest, which is the too-inclusive failure wearing a
    derivation.
    """
    if spec is None:
        return ()
    path = [entry for entry in (payload.get("path") or ()) if isinstance(entry, Mapping)]
    if not path:
        return ()
    frontier = str(path[-1].get("id") or "")

    for gate_id, entry in (payload.get("gate_ledger") or {}).items():
        if not isinstance(entry, Mapping):
            continue
        if entry.get("status") != "FAILED" or str(entry.get("node") or "") != frontier:
            continue
        try:
            klass = spec.method_class(payload.get("proposed_method"))
            key = spec.row_key(str(gate_id), klass)
        except Exception:  # noqa: BLE001 - a selection is not worth a lost turn
            return ()
        return tuple(sorted(spec.gate_row_facts.get((str(gate_id), key), ())))

    from app.tools import next_moves

    try:
        return tuple(next_moves._facts_of_node(frontier, spec))
    except Exception:  # noqa: BLE001 - see above
        return ()


def _stage_of(payload: Mapping[str, Any], spec: Any | None) -> str:
    """Which stage the walk stopped in, from the node it stopped at.

    The payload carries `path`, whose last entry is the frontier. `node_stage`
    is the engine's own index and it is read rather than reconstructed. A gate's
    own node - `S0_NO_EVAL_SET` and its four siblings - lives in the `gates:`
    block rather than in a stage and is absent from that index BY DESIGN, which
    `docs/PHASES.md` records as a correction to an adversary's report; so this
    walks the path backwards to the last entry the index does know, and returns
    `""` when there is none. `""` matches no declared stage, which is the honest
    answer rather than a guess at a neighbouring one.
    """
    index = getattr(spec, "node_stage", None) or {}
    for entry in reversed(list(payload.get("path") or ())):
        if not isinstance(entry, Mapping):
            continue
        stage = index.get(str(entry.get("id") or ""))
        if stage:
            return str(stage)
    return ""


def _evidence(
    thread_id: int | None, rows: Iterable[Mapping[str, Any]] | None
) -> list[Mapping[str, Any]]:
    """The rows this thread can see, or the ones a caller handed over.

    A read, through `evidence.ledger_view`, which is the same door
    `app/tools/context.py` already renders to a person as *"through"*. No new
    table, no new lifecycle, no eviction policy: the link from a fact back to
    the tool that stamped it is a column that already exists.
    """
    if rows is not None:
        return [row for row in rows if isinstance(row, Mapping)]
    if thread_id is None:
        return []
    from app.tools import evidence

    try:
        return [row for row in evidence.ledger_view(thread_id) if isinstance(row, Mapping)]
    except Exception:  # noqa: BLE001 - a turn is not lost to a ledger read
        return []


def changed(before: Iterable[str] | None, after: Active) -> dict[str, Any] | None:
    """`blocks.changed`, or `None` when nothing moved.

    `docs/PHASES.md`'s done-condition is *"the active block is visible in the
    interface as a label rather than a choice"*, and `docs/CAPABILITY_BLOCKS.md`
    §7 fixes the shape: an event, when and only when the set changes, carrying
    what moved and why. Not a modal, not a confirmation, not a question. The
    person is being told what the harness did, in the same register as every
    other number it shows them - and the way they correct it is the button,
    which is still on the screen because `controls()` is not scoped.

    `before=None` is a thread's first turn: everything is `added`, because it is.
    """
    was = frozenset(str(one) for one in (before or ()))
    now = after.packs
    if before is not None and was == now:
        return None
    added = sorted(now - was)
    removed = sorted(was - now)
    return {
        "added": added,
        "removed": removed,
        "active": sorted(now),
        "because": {name: after.because[name] for name in added if name in after.because},
        "tools": list(after.tools),
        "controls_are_not_scoped": (
            "Every tool in this harness is still a button in the app. A pack "
            "that is not loaded is a tool the model will not reach for, never "
            "one the person cannot run."
        ),
    }


# ---------------------------------------------------------------------------
# TOOLS ON DEMAND. A pack chooses which tools are ACTIVE; this chooses which of
# them spend a full JSON Schema on the wire this turn.
# ---------------------------------------------------------------------------
#
# MEASURED 2026-09-18, with `app/providers/budget.py`'s estimator over
# `REGISTRY.model_tools`, on the owner's own registry:
#
#   * every pack on          - 88 schemas, 26,992 tokens
#   * a build turn's core    - 27 schemas,  6,330 tokens
#   * a fresh build thread   - 48 schemas, 13,514 tokens against a 65k window,
#                              which is the owner's thread 75 reproduced here
#   * the capability list    -  0 schemas,  1,716 tokens, AND IT NAMES ALL 88
#
# and 58 of the 88 have never been called by any model on that machine. That
# fresh thread now sends NINE schemas and 1,512 tokens.
#
# Max, 2026-09-14: *"make sure the models aren't clouded with too many tools and
# guidelines so that they can have free roam."* Packs were the first answer and
# they are not enough: the narrowest pack selection this engine produces is
# still 27 tools, because the ledger core is three packs wide and a pack is the
# unit an AUTHOR reasons in, not the unit a TURN needs.
#
# THE SPLIT THIS FILE NOW MAKES. A name is cheap and a schema is not. Every tool
# keeps its NAME in front of the model - `app/instructions/capabilities.py`
# renders all 88 of them for 1,716 tokens and its docstring holds the measured
# reason it may never be shortened - and a full schema rides only for the tools
# something in front of the model NAMES. Six sources, and none of them is the
# model asking:
#
#   1. the plan's AIMED PHASE - its `**Tools:**` line and its step text. The
#      work this turn is for says which instruments it uses; the plan wrote
#      that down before the turn began.
#   2. THE DIAGNOSIS, in the same readings `active` already takes: the
#      `next_step` tool, `unsubstantiated[].next_step.tool`, and `alternatives`.
#   3. WHAT THE LAST REPLY NAMED. A model that said `try_prompt` and had no
#      schema for it is a model asking for the schema in the only vocabulary it
#      has. It gets it on the next round - which is the door that stops this
#      being the nine-turn loop of thread 70 with a smaller number on it.
#      AND WHAT ITS REASONING NAMED (2026-09-23): a thinking model states its
#      intent there and leaves the text empty on a tool-calling round.
#      2b. On a fresh thread with a project folder and no dataset on record,
#      the five DISCOVERY tools - the situation names them before anything
#      else can.
#   4. THE LEDGER CORE, always: the nine tools that write this thread's state
#      and read this machine. Under ten, and it is the closure of the selector -
#      a turn that cannot call `run_diagnosis` cannot move any of the three
#      sources above.
#   5. WHAT THIS THREAD HAS ALREADY MEASURED WITH. `active`'s own fourth source
#      one layer in, and it is here because a test went red rather than because
#      it was reasoned about first - see the comment on it below.
#   6. AND NOTHING A PERSON SWITCHED OFF, which needs no code here: the pool
#      this chooses from is `active.tools`, and `_minus_what_was_switched_off`
#      has already taken those packs out of it.
#
# WHAT THIS IS NOT. It is not a search interface and it is not a request. The
# same rule `registry.py` and `active` hold to applies one layer in: a model may
# call tools and may not decide which tools it has. Source 3 looks like an
# exception and is not - it reads what the model SAID on a turn that is already
# over, the way `active` reads a diagnosis that is already over.
#
# AND THE NAME STAYS IN THE ROOM, WHICH IS WHAT MAKES THIS SAFE. The failure
# mode `app/instructions/capabilities.py` was built against - a model told about
# twelve tools telling the user this product has twelve - is not reached here,
# because the list is still complete and still names all 88. What varies is
# which of them arrive with their parameters. A model that wants one it was not
# handed names it, and source 3 hands it over on the next round.


#: The tools whose schema rides every turn of every thread. The ledger core that
#: writes state, plus the two that read the machine.
#:
#: NINE, AND THE BOUND IS THE POINT. `docs/CAPABILITY_BLOCKS.md` A6 argues the
#: core in packs; this is the same argument in tools, and it is deliberately
#: smaller than the packs those tools live in. `run_diagnosis` is here because
#: every other source above is downstream of it - withhold it and a thread can
#: never widen. `read_plan` and `write_plan` are here because a turn that cannot
#: write a plan cannot name the phase source 1 reads. `inspect_hardware` and
#: `list_local_models` are here because "what can this machine do" is the one
#: question a person asks at any stage, which
#: `test_a_question_about_this_machine_can_be_asked_at_any_stage` already pins
#: at the pack level.
ALWAYS_ON: tuple[str, ...] = (
    "run_diagnosis",
    "what_is_missing",
    "state_facts",
    "write_plan",
    "read_plan",
    "mark_step_done",
    "unpark_step",
    "inspect_hardware",
    "list_local_models",
)

#: The switch, and it is the same shape as `MLH_FILL_BLANKS_FROM_THREAD` in
#: `app/conductor.py` and for the same reason: on-demand schemas are a CONFOUND
#: for any run that compares models, so a trial has to be able to turn them off,
#: and a reading that cannot say which arm it was in is not a reading. The
#: choice is recorded on `turn.context` either way.
ALL_SCHEMAS_VARIABLE = "MLH_ALL_SCHEMAS"
ALL_SCHEMAS_ON = {"1", "on", "true", "yes"}


def all_schemas_ride() -> bool:
    """Default OFF - on-demand. Only an explicit, recognised word turns it on.

    The opposite default to `conductor.filling_is_on()`, and deliberately: the
    fill is help a PERSON gets and this is a cost a person PAYS, so the safe
    direction is the one where the window stays theirs. An unrecognised value
    reads as on-demand rather than as everything, because a typo that quietly
    put 27,000 tokens back on every turn is the defect this section closes.
    """
    import os

    said = os.environ.get(ALL_SCHEMAS_VARIABLE, "").strip().lower()
    return said in ALL_SCHEMAS_ON


#: Why one tool's schema is on the wire. One clause per source, each a record of
#: something that happened rather than a category - the same rule the pack
#: reasons above follow.
BECAUSE_ALWAYS_ON = "the ledger core writes this thread's state and rides every turn"
#: `read_observation` rides when this thread has been handed a handle - a
#: pack names the reader in its text, and a name without parameters is a door
#: without a handle. Not in `ALWAYS_ON`: a turn with no large result has no
#: handle to open.
BECAUSE_A_HANDLE_EXISTS = "an earlier result of this thread is on file under a handle it can open"
BECAUSE_THE_PHASE_NAMES = "the plan's aimed phase names {tool}"
BECAUSE_THE_PLAN_NAMES = "this sub-agent's plan names {tool}"
BECAUSE_THE_NEXT_STEP = "the diagnosis names {tool} as the next step"
BECAUSE_AN_ALTERNATIVE = "the diagnosis offers {tool} as a move from here"
BECAUSE_A_CLAIM_NEEDS_SETTLING = (
    "{fact} was claimed rather than measured, and {tool} settles it"
)
BECAUSE_THE_LAST_REPLY_NAMED = (
    "the last reply named {tool} and its schema was not in the room"
)
#: THE SAME DOOR, IN THE REGISTER A THINKING MODEL ACTUALLY SPEAKS IN.
#: MEASURED 2026-09-23 on the owner's model (minicpm5-hermes, 1B, thinking): its
#: reasoning said *"Let me use profile_repository on the ml-principles-dataset
#: folder"* three times, its content said nothing, and its tool channel called
#: `list_local_models` three times - the one it had a schema for. The text rule
#: above read an empty string on every one of those rounds.
BECAUSE_THE_REASONING_NAMED = (
    "the model named {tool} in its reasoning and its schema was not in the room"
)
BECAUSE_IT_ALREADY_MEASURED_SOMETHING_HERE = "{tool} measured {fact} on this thread"
#: Why a tool that rode is withdrawn for the rest of this turn. Recorded in
#: `withheld_because`, never in `because`, which says why a schema RODE.
BECAUSE_ALREADY_CALLED = (
    "already called this turn with these arguments; the result is above"
)
#: Why the discovery tools ride on a thread that has nothing to work from yet.
BECAUSE_NOTHING_ON_RECORD = "no dataset on record; discovery rides first"
#: At most this many characters of reasoning are read - the TAIL, which is what
#: the model was thinking when it chose its call. A thinking model can spend
#: thousands of tokens before a word, and a reader that took all of them would
#: be the whole-transcript accumulation `_what_the_last_reply_said` refuses.
REASONING_CAP = 4_000
#: The tools that READ WHAT THE PROJECT FOLDER HOLDS. On a fresh thread with a
#: folder and no dataset on record these are the first move and nothing else
#: names them: the diagnosis names `measure_eval_set` (MEASURED 2026-09-23, a
#: blank walk's `next_step`), which needs a file the model has not found yet.
#: FIVE, 2,853 CHARACTERS OF SCHEMA MEASURED THE SAME DAY WITH
#: `REGISTRY.model_tools` - under the 7,040 `propose_build` alone costs, and the
#: turn that lacked them sent ten schemas and could not look at the folder.
DISCOVERY: tuple[str, ...] = (
    "list_context",
    "profile_repository",
    "profile_dataset",
    "read_context_file",
    "preview_dataset_rows",
)
BECAUSE_EVERY_SCHEMA_WAS_ASKED_FOR = (
    "MLH_ALL_SCHEMAS is on, so every active tool's schema rides"
)
BECAUSE_NOTHING_NARROWED_IT = (
    "the diagnosis could not be computed for this turn, so nothing narrowed the schemas"
)


@dataclass(frozen=True)
class OnTheWire:
    """The tools whose full schema this turn sends, and why each one.

    `considered` is the pool it chose from - the active tools this mode allows -
    so the record says what was WITHHELD as well as what rode, which is the only
    way a person reading the context pane can tell a narrow turn from a small
    harness. `all_schemas` says which arm the turn ran in.

    `withheld_because` holds a reason only for a tool something named and this
    record took back anyway - a call repeated with the same arguments. A tool
    withheld because nothing named it needs no sentence; one withdrawn after
    it rode does, or the pane shows a core tool missing with no account of it.
    """

    tools: tuple[str, ...]
    because: Mapping[str, str]
    considered: tuple[str, ...]
    all_schemas: bool
    withheld_because: Mapping[str, str] = field(default_factory=dict)

    def names(self) -> tuple[str, ...]:
        return self.tools

    def as_dict(self) -> dict[str, Any]:
        """What goes on `turn.context`, `turn.started` and `blocks.changed`."""
        riding = set(self.tools)
        return {
            "tools": list(self.tools),
            "because": {name: self.because[name] for name in sorted(self.because)},
            "considered": list(self.considered),
            "withheld": [name for name in self.considered if name not in riding],
            "withheld_because": {
                name: self.withheld_because[name] for name in sorted(self.withheld_because)
            },
            "all_schemas": bool(self.all_schemas),
            "switch": ALL_SCHEMAS_VARIABLE,
        }


#: The characters a tool name is made of. Matching on these rather than on a
#: substring is not tidiness: `recall` is a registered tool and it is a
#: substring of `measure_retriever_recall`, so a phase that names the second
#: would silently have loaded the first.
_NAME_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_")


def _identifiers(text: str) -> frozenset[str]:
    """Every identifier-shaped run of characters in `text`, lowercased."""
    found: set[str] = set()
    token: list[str] = []
    for character in str(text or "").lower():
        if character in _NAME_CHARACTERS:
            token.append(character)
        elif token:
            found.add("".join(token))
            token = []
    if token:
        found.add("".join(token))
    return frozenset(found)


def _named_in(text: str, pool: Iterable[str]) -> tuple[str, ...]:
    """The tools of `pool` this text names, in the pool's own order."""
    said = _identifiers(text)
    return tuple(name for name in pool if name in said)


def _the_work_in_front_of_the_model(thread_id: int | None) -> tuple[str, str]:
    """The plan text this turn is aimed at, and which reason describes it.

    A SUB-AGENT's whole plan is one phase, so all of its steps are in scope; a
    PARENT is aimed at the phase holding its first open step. The same two
    readings `_narrow_to_phase_packs` takes, with one difference that matters:
    there, a parent narrows only on a live run, because dropping a PACK a casual
    build turn chose takes a tool away from the model entirely. Here nothing is
    taken away - the name is still in the capability list, the tool is still
    offered, and source 3 hands the schema over the moment the model names it -
    so here the narrowing is the default and the widening is what is earned.
    """
    if thread_id is None:
        return "", ""
    try:
        from app import events as _events
        from app import subagents as _subagents

        plan = str((_events.get_thread(int(thread_id)) or {}).get("plan") or "")
        if not plan.strip():
            return "", ""
        if _subagents.is_a_subagent(int(thread_id)):
            steps = " ".join(str(step.get("text") or "") for step in planning_steps(plan))
            return steps, BECAUSE_THE_PLAN_NAMES
        return phase_of_first_open_step(plan), BECAUSE_THE_PHASE_NAMES
    except Exception:  # noqa: BLE001 - never fail a turn over a plan parse
        return "", ""


def on_the_wire(
    active: Active,
    *,
    thread_id: int | None = None,
    payload: Mapping[str, Any] | None = None,
    last_reply: str = "",
    among: Iterable[str] | None = None,
    evidence_rows: Iterable[Mapping[str, Any]] | None = None,
    registry: Any | None = None,
    reasoning: str = "",
    repeated: Iterable[str] = (),
) -> OnTheWire:
    """Which of this turn's active tools spend a full schema on the wire.

    Runs AFTER `active` has chosen the packs, and never instead of it. The pool
    is `active.tools` - or `among`, when the caller has narrowed further, as the
    conductor does for the mode and for `read_plan` on a build turn with open
    steps - so everything the packs decided, including everything a person
    switched off, is settled before this function is asked anything.

    A TURN THAT COULD NOT COMPUTE A SELECTION GETS MORE SCHEMAS, NOT FEWER, for
    the reason `everything()`'s docstring gives one layer out: a failure to
    select is not evidence about a person's situation, and the expensive
    direction of being wrong is somebody who cannot reach what they need.

    `registry` is taken and not used, on purpose: every source here reads names
    out of `active`, which the registry already built. The parameter is here so
    a caller that scopes `active` to a test registry does not have to remember
    that this one does not need telling - and so it never grows a second
    opinion about what is registered.

    `reasoning` is what a thinking model THOUGHT on the rounds this reads, and
    `repeated` names the calls this turn already made twice with the same
    arguments - both read by `app/conductor.py` off the event log, never
    handed in by a model. See the comments on sources 3 and 3b and on the
    withdrawal at the end.
    """
    wanted = None if among is None else {str(one) for one in among}
    pool = tuple(
        name for name in active.names() if wanted is None or name in wanted
    )
    if not pool:
        return OnTheWire(tools=(), because={}, considered=(), all_schemas=False)
    if all_schemas_ride():
        return OnTheWire(
            tools=pool,
            because={name: BECAUSE_EVERY_SCHEMA_WAS_ASKED_FOR for name in pool},
            considered=pool,
            all_schemas=True,
        )

    known = set(pool)
    reasons: dict[str, str] = {}

    def add(name: Any, why: str) -> None:
        one = str(name or "")
        if one and one in known:
            reasons.setdefault(one, why)

    # 4. THE LEDGER CORE, first, because it is the closure of everything below.
    for name in ALWAYS_ON:
        add(name, BECAUSE_ALWAYS_ON)

    # 5. THE READER OF PACKED RESULTS, when there is something to read.
    if thread_id is not None:
        from app import observations as _observations

        if _observations.READER in known and _observations.has_handles(int(thread_id)):
            add(_observations.READER, BECAUSE_A_HANDLE_EXISTS)

    if payload is None:
        for name in pool:
            add(name, BECAUSE_NOTHING_NARROWED_IT)
        return _minus_the_repeats(
            OnTheWire(
                tools=tuple(name for name in pool if name in reasons),
                because=reasons,
                considered=pool,
                all_schemas=False,
            ),
            repeated,
        )

    # 1. THE WORK THIS TURN IS FOR, as the plan wrote it down.
    scope, why_scope = _the_work_in_front_of_the_model(thread_id)
    for name in _named_in(scope, pool):
        add(name, why_scope.format(tool=name))

    # 2. WHAT THE DIAGNOSIS NAMED, in the readings `active` already takes -
    #    plus the one it does not, because at the pack layer it did not have to.
    #
    #    THE SENTENCE IS A NAMING. `app/tools/__init__.py` writes `next` beside
    #    `next_step`, and it is the engine speaking the move out loud: *"the next
    #    move is propose_build"*, *"Run {tool} - it measures it from this
    #    machine"*, *"call state_facts with EXACTLY this shape"*. `next_step`
    #    carries a `tool` on two of its four branches and `{"kind": "propose"}`
    #    on a third, where the tool's name lives only in that sentence.
    #
    #    THIS IS WHAT KEEPS `propose_build` OUT OF THE ALWAYS-ON SET, and the
    #    number is why it had to: MEASURED 2026-09-18, its schema is 7,040
    #    characters and 1,957 tokens - MORE THAN THE WHOLE NINE-TOOL CORE, which
    #    is 1,512. A door that costs more than the room it opens onto is one to
    #    open when it is the door, and the engine says when that is.
    step = payload.get("next_step")
    if isinstance(step, Mapping):
        add(step.get("tool"), BECAUSE_THE_NEXT_STEP.format(tool=step.get("tool")))
    for name in _named_in(str(payload.get("next") or ""), pool):
        add(name, BECAUSE_THE_NEXT_STEP.format(tool=name))
    for row in payload.get("alternatives") or ():
        if isinstance(row, Mapping):
            add(row.get("tool"), BECAUSE_AN_ALTERNATIVE.format(tool=row.get("tool")))
    for row in payload.get("unsubstantiated") or ():
        if not isinstance(row, Mapping):
            continue
        move = row.get("next_step")
        tool = (move if isinstance(move, Mapping) else {}).get("tool")
        add(
            tool,
            BECAUSE_A_CLAIM_NEEDS_SETTLING.format(fact=row.get("fact"), tool=tool),
        )

    # 2b. NOTHING ON RECORD YET, ON A PROJECT WITH A FOLDER. MEASURED
    #     2026-09-23, the owner's journey: a fresh Build/Full thread on a folder
    #     holding `ml-principles-dataset/` sent ten schemas - the core and the
    #     diagnosis's `measure_eval_set` - and withheld all five tools that read
    #     a folder. No source above names them on that turn: there is no plan,
    #     the walk asks for an eval set it cannot see, and the model's own
    #     words come after the turn it needed them on. So the situation names
    #     them, and only while it lasts - a dataset on record, a settled
    #     verdict, or no folder at all each ends it.
    if _nothing_on_record_yet(thread_id, payload, evidence_rows):
        for name in DISCOVERY:
            add(name, BECAUSE_NOTHING_ON_RECORD)

    # 3. WHAT THE MODEL ITSELF NAMED LAST TIME, which is the door.
    for name in _named_in(last_reply, pool):
        add(name, BECAUSE_THE_LAST_REPLY_NAMED.format(tool=name))

    # 3b. AND WHAT IT NAMED IN ITS THINKING, which is where a thinking model
    #     says it. After the text rule, so a tool named in both keeps the older
    #     reason. The same reader and the same whole-identifier match, so a
    #     thought about `measure_retriever_recall` loads nothing called `recall`.
    for name in _named_in(reasoning, pool):
        add(name, BECAUSE_THE_REASONING_NAMED.format(tool=name))

    # 5. AND WHAT THIS THREAD HAS ALREADY MEASURED WITH.
    #
    # `active`'s fourth source, one layer in, and it arrived here the way that
    # one did - by a test going red rather than by being reasoned about.
    # `test_the_hardware_tool_is_offered_and_runs_mid_data_thread` drives the
    # moat: a person mid-data-thread asks what GPU they have, and the hardware
    # tool AND the data work are on the same turn rather than in two tabs. The
    # first cut of this function had no fifth source, so on that turn
    # `measure_eval_set` - which had stamped `eval_size_n` on that very thread -
    # went out with a name and no parameters.
    #
    # A TOOL THAT HAS RUN HERE IS A TOOL THIS WORK NAMED, and the argument is
    # `docs/CAPABILITY_BLOCKS.md` §7's: a model that measured a number and can
    # no longer work with it is worse than one that never measured it. Bounded
    # by the same property the pack layer relies on - one row per fact this
    # thread has measured, which is a constant of the ledger and not an
    # accumulation over turns.
    for row in _evidence(thread_id, evidence_rows):
        tool = str(row.get("tool") or "")
        add(
            tool,
            BECAUSE_IT_ALREADY_MEASURED_SOMETHING_HERE.format(
                tool=tool, fact=row.get("fact")
            ),
        )

    # AND IF SIX SOURCES NAMED NOTHING, THE POOL RIDES. Unreachable on either
    # shipped mode - the ledger core is not removable, so `ALWAYS_ON` always
    # meets the pool - and it is here for the reason every widening in this file
    # is here: a selection that came out empty is a selector that failed, and a
    # turn handed zero schemas is a model that can only talk. The adapters would
    # also be sent `tools: []`, which is a different request from `tools: null`
    # and not one this product means to make.
    if not reasons:
        return _minus_the_repeats(
            every_schema(pool, because=BECAUSE_NOTHING_NARROWED_IT), repeated
        )

    return _minus_the_repeats(
        OnTheWire(
            tools=tuple(name for name in pool if name in reasons),
            because=reasons,
            considered=pool,
            all_schemas=False,
        ),
        repeated,
    )


def _minus_the_repeats(wire: OnTheWire, repeated: Iterable[str]) -> OnTheWire:
    """`wire` without the tools this turn already called twice the same way.

    MEASURED 2026-09-23, the owner's journey: `list_local_models` called three
    times with identical empty arguments in one 45-second turn, ended
    `answered_after_repeat_loop`. `_run_tool` already answers a repeat from the
    memo without running it, and `REPEAT_NUDGE` already says so once - and a
    1B model read both and called it a third time, because its schema was
    still in the request and the one it wanted was not. A small model cannot
    repeat what is not offered.

    THE SCHEMA GOES, THE NAME STAYS. The tool is still in `considered`, so the
    capability list still names it and the record lists it as withheld, with
    `BECAUSE_ALREADY_CALLED` in `withheld_because`. `_run_tool` still permits
    it - being offered is the wider set - and a call that arrives anyway is
    answered from the memo, which is what the repeat guard was always for.

    NEVER TO NOTHING. A withdrawal that emptied the wire would hand the
    adapters `tools: []`, which the comment above `every_schema` says this
    product does not mean to send; it is not applied then, and the repeat
    guard stays the backstop it already is.
    """
    gone = {str(name) for name in repeated or ()} & set(wire.tools)
    if not gone or gone >= set(wire.tools):
        return wire
    return OnTheWire(
        tools=tuple(name for name in wire.tools if name not in gone),
        because={name: why for name, why in wire.because.items() if name not in gone},
        considered=wire.considered,
        all_schemas=wire.all_schemas,
        withheld_because={
            **dict(wire.withheld_because),
            **{name: BECAUSE_ALREADY_CALLED for name in sorted(gone)},
        },
    )


def _facts_a_dataset_puts_on_record(spec: Any) -> frozenset[str]:
    """Every fact a `data.*` capability measures, read off the ledger.

    Derived rather than listed: `eval_size_n` names `data.eval_set.count` and
    `data.dataset.profile` in its own `measured_by`, `vram_gb` names
    `machine.hardware.inspect`, and a fact added to the ledger tomorrow under a
    `data.` instrument is a dataset fact on the day it is added.
    """
    facts = getattr(spec, "facts", None)
    if not isinstance(facts, Mapping):
        return frozenset()
    return frozenset(
        str(name)
        for name, declaration in facts.items()
        if isinstance(declaration, Mapping)
        and any(
            pack_of(capability) == "data"
            for capability in declaration.get("measured_by") or ()
        )
    )


def _nothing_on_record_yet(
    thread_id: int | None,
    payload: Mapping[str, Any] | None,
    evidence_rows: Iterable[Mapping[str, Any]] | None,
) -> bool:
    """A project folder to look in, no dataset on record, and no verdict yet.

    Three conditions, each one an exit that ends the rule on its own:

    * THE PROJECT HAS A FOLDER. `projects.root_path`, the same column
      `conductor._workspace_note` reads to tell the model the folder exists.
      No folder, nothing for a discovery tool to discover.
    * NO DATASET ON RECORD. No ledger row on this thread for a fact a `data.*`
      instrument measures. A machine fact is not a dataset - a person who
      asked what GPU this is has still not shown their data. When the ledger
      cannot be read, ANY row counts, which is the direction that keeps the
      wire narrow.
    * THE DIAGNOSIS IS UNSETTLED. `BLOCKED`, or no verdict; a `NO_TRAIN` or
      `TRAIN` turn is answering, not looking.
    """
    if thread_id is None or not isinstance(payload, Mapping):
        return False
    if str(payload.get("verdict") or "").upper() in {"NO_TRAIN", "TRAIN"}:
        return False
    try:
        from app import db as _db
        from app import events as _events

        project_id = (_events.get_thread(int(thread_id)) or {}).get("project_id")
        project = _db.get_project(int(project_id)) if project_id else None
    except Exception:  # noqa: BLE001 - never fail a turn over a project read
        return False
    if not str((project or {}).get("root_path") or "").strip():
        return False
    rows = _evidence(thread_id, evidence_rows)
    dataset_facts = _facts_a_dataset_puts_on_record(_spec(None))
    if not dataset_facts:
        return not rows
    return not any(str(row.get("fact") or "") in dataset_facts for row in rows)


#: Why every active schema rode anyway. Plan mode's `modes.PLAN_TOOLS` is
#: already a hand-picked, MEASURED list - three arms on the owner's own question
#: on 2026-09-11 settled which tools a consultation gets and which it must not,
#: and the arm that was given fewer went silent - so narrowing it a second time
#: here would be this file overruling a measurement with a heuristic.
BECAUSE_THE_MODE_IS_ALREADY_THE_LIST = (
    "plan mode offers modes.PLAN_TOOLS, which is already the narrowing"
)


def every_schema(pool: Iterable[str], *, because: str) -> OnTheWire:
    """Every tool in `pool`, with the sentence that explains the widening.

    Carried rather than defaulted silently, for `everything()`'s reason: a
    widening always arrives with the sentence that explains it, so a reader of
    the record never has to guess whether a wide turn was chosen or fell out.
    """
    names = tuple(str(one) for one in pool)
    return OnTheWire(
        tools=names,
        because={name: because for name in names},
        considered=names,
        all_schemas=all_schemas_ride(),
    )
