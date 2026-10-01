"""The storm: the approved build, executed, with the approval enforced.

`app/build.py` is the object a person approves. This is the thing that runs it.
Read that module first - this one consumes it and deliberately re-derives none
of it.

`docs/THE_PROPOSAL_LOOP.md` section 6 is the specification:

    Steps that do not depend on each other run at once. Steps that do, wait.
    Long steps stream their progress into the thread. Nothing blocks the
    conversation. Every step is verified when it finishes, against the exit
    criterion the build declared before it ran. A step that cannot show it
    worked did not work.

Four properties in this file are decisions rather than details.

## 1. APPROVAL IS A CONTRACT, AND THIS IS WHERE IT IS ENFORCED OR IT IS A LABEL

A storm may run only what was approved. `Manifest` is what was approved,
recorded at the moment the person said yes, and every path into execution goes
through it:

- **The plan cannot be swapped.** `run(storm_id, plan=...)` takes what the
  caller believes the approved plan is and refuses unless it matches the
  manifest, naming what changed in the same sentences `Build.deviations_from`
  uses. A caller that holds a plan - an editor that just moved a node, a process
  that rebuilt one after a restart - has to prove it is the same plan.
- **The step cannot be edited.** Each `StepContract` carries the
  `Step.contract_fingerprint()` it was approved with, and it is recomputed off
  the stored payload before the step runs. The stored plan and the stored hash
  have to agree with each other.
- **The tool cannot change under it.** This is the deviation `Build` cannot
  see: the step is untouched and the thing it names is not what it was.
  `tool_fingerprint()` covers a tool's schema, its `reads`, its `writes`, its
  `measures`, its `bounds` and whether it needs an approval, all recorded at
  approval time. A tool that grew an argument, gained network access or started
  requiring an approval since the person said yes stops the storm.
- **An input nobody approved cannot appear.** Arguments are bound only from
  outputs that approved steps declared they produce, and a `Ref` to anything
  else is refused before a tool is called rather than after.

Every one of those refusals STOPS AND ASKS. Nothing here decides that a change
is harmless; `docs/THE_PROPOSAL_LOOP.md` says a deviation stops and asks, and a
storm that could quietly do something outside the picture would make every
honesty claim in this product decoration.

## 2. A STEP THAT CANNOT SHOW IT WORKED DID NOT WORK

The exit criterion is the one the build declared before it ran, read out of the
manifest and evaluated by `ExitCriterion.met()` - the build's own function, not
a looser reading of it invented here. `source` says which observation to make
and this module makes exactly that one: the tool's own result, the outputs the
step declared, or a fresh diagnosis. A step whose tool returned successfully and
whose criterion was not met is `failed`, and its dependents do not run.

## 3. A STORM OUTLIVES THE ENGINE

The same way a run does, and by the same mechanism rather than a new one.

- **What was approved** is written to `storms` (migration 5) at the moment of
  approval and never again. There is exactly one `UPDATE` against that table in
  this file and it is inside `declare()`, filling in `declared_event_id` in the
  same call that inserted the row - the event announcing a storm cannot be
  written before the storm has an id to be announced under. After that moment
  nothing here writes to the row, and in particular no state is ever kept on it.
- **What has happened** is `app/events.py`, which is append-only and whose
  autoincrement id is the SSE event id. Every state change a storm makes is an
  event, committed before it is streamed.

So a storm's state is not stored, it is FOLDED out of its own log by `attach()`,
and that is what makes re-attaching free rather than a feature: a new engine
process reads the manifest and replays the events, and knows exactly what has
run. There is no status column to disagree with the log, and no heartbeat.

**A step that was running when the engine died is `stalled`, never restarted.**
This module knows which storms are live *in this process* (`_LIVE`), so a
`storm.step.started` with no matching finish and nothing live is an interrupted
step - and its side effects may or may not have landed. Guessing is how a
dataset gets written twice. `run()` refuses to resume such a storm and names the
steps; restarting one is a decision the person makes, through `restart_stalled`,
having been told what it might repeat.

## 4. WHAT THIS MODULE DOES NOT DO, SAID OUT LOUD

**It never rebuilds a cost, and nothing it rebuilds outlives the check.**
`app/build.py` arranges things so an `Estimate` cannot be constructed without
its origin. A deserialiser here would be a door straight through that: a cost
dict off disk, rehydrated, is a number whose provenance is a string that came
back from SQLite. So the manifest carries the approved plan as the *record* it
is - shown to the person, drawn as the diagram, never a source a new number
comes out of - and the executor works off `StepContract`, which has no cost on
it at all. Binding and harvesting are eight lines here rather than a `Step`
reconstruction for exactly that reason.

`Manifest.of` does turn a recorded plan back into a `Build`, and that is not
the same door. It has to: a manifest that could be minted from any dict shaped
like a plan is a contract nobody signed, which is what `_a_build_again` and the
long comment above it exist to fix. The copy it makes carries FOUR UNKNOWN
ESTIMATES and no magnitude anywhere - `Estimate.unknown` takes none from its
caller - it is handed straight to `Build.validate()`, and it is dropped. Not one
number crosses from JSON into an `Estimate`, which is the property section 4 was
always about. What was actually forbidden here, and still is, is a *number* off
disk wearing a provenance; a *structure* off disk being handed to the build's
own validator is the opposite of that - it is the check happening rather than
being assumed.

**It spawns no process.** A storm runs registered tools in this process. The one
tool that leads to a spawned process, `start_training`, queues a job that
`app/runner.py` runs - and that module already owns process-tree kill, bounded
timeouts, structured argv and no shell. Nothing here duplicates, wraps or races
it, and no proposer in `app/tools/propose.py` plans such a step today. When the
supervisor arrives (M7) it is the thing that runs jobs, and a storm waiting on
one waits on the runner rather than on a second copy of it.

That leaves four honest gaps, stated rather than hidden. The first two are what
`Manifest.of`'s validation does NOT catch, and they are listed because the one
reason several defects in this module were ever visible is that a docstring
named its own gap - and the one reason a fourth defect lived for months is that
this same docstring named a guarantee it did not provide.

**The cost figures in a plan are not re-validated, and cannot be here.** The
copy `Build.validate()` runs against carries UNKNOWN costs, so `cost` and the
one `say` line derived from it are what `_the_same_plan` skips. A dict that
never came from a proposer can therefore carry a cost with an invented figure
and an invented provenance, and this module will accept it as a record. The same
sentence covers everything `Build.validate` checks ABOUT a cost - in particular
the subject rule, which asks whether a step's cost descends from a measurement
of the thing that step runs on: a copy with no costs has no subjects to check.
Three things bound it. Nothing in this file ever reads a number out of
`blueprint` - the executor works off `StepContract`, which has no cost on it -
so an invented cost cannot change what runs. The only door into this from
outside Python is `POST /api/storms`, which re-proposes server-side and compares
fingerprints, so the cost that reaches a manifest through the product is the
proposer's own. And a step whose ARGUMENTS were edited to point at a different
file is caught, because arguments are re-derived and compared. Closing the rest
means `Estimate` and `Subject` being able to say whether they were minted or
typed, which is `app/build.py`'s to give and not this module's to work around.

**A manifest read back off disk is trusted.** `Manifest.from_dict` checks
nothing: it is a record reader, and the record is a row that `declare()` wrote
after all of the above passed. Whoever can write the `storms` table can
therefore write a manifest, and re-hashing would not help - the row carries its
own fingerprint, so a tamperer supplies both halves, which is the exact shape of
the defect this section fixed one level up. What actually bounds it is that
writing that table means holding the database file, and anybody holding the
database file can run Python. It is named here so that nobody reads
`from_dict`'s fingerprint field as a check. Re-validating on every read is not
the answer either: `attach()` calls it, and a storm whose tool was deregistered
must still be *viewable* - that deviation is `drift()`'s to report at run time,
where the person can be asked.

**A tool call cannot be stopped.** It is a function call on a thread, and Python
cannot kill a thread. `step_timeout` therefore bounds how long the storm WAITS,
not how long the call runs, and a step that exceeds it is reported as `stalled`
with those words. Claiming it was killed would be a lie, and it is the reason
the paragraph above matters: anything that genuinely needs to be killable is a
process, and a process goes through `app/runner.py`.

**Two engines on one database could run one storm twice.** `_LIVE` is
process-local, so the guard in `run()` stops a second run inside this engine and
cannot see one in another. Closing that needs a lease with a heartbeat, because
the cheap alternatives do not work: an event-based claim is indistinguishable
from the dangling `storm.started` a killed engine leaves, which is the state
`attach()` exists to read correctly. A lease is the supervisor's, alongside
running jobs (M7), and inventing a second one here would be the second
mutual-exclusion mechanism `app/migrations/__init__.py` argues against. The
product's operating model is one engine per database, published in
`engine.json`; this is what is owed to make that a guarantee rather than a
convention.

## The vocabulary

`STEP_STATES` comes from `app/build.py`, which took it from
`docs/DESIGN_SYSTEM.md` section 2.5. It is not restated here. The diagram keys
on `Step.id` and so does this executor, which is what makes a node that fails in
the picture the same node that failed in the run.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, Mapping, Sequence

from app import db, events
from app.build import (
    COST_DIMENSIONS,
    NETWORK_READS,
    PERSON_ONLY_TOOLS,
    STEP_STATES,
    Build,
    BuildInvalid,
    Cost,
    DataSnapshot,
    Environment,
    Estimate,
    ExitCriterion,
    Output,
    Question,
    Ref,
    Risk,
    Step,
    Subject,
    Verification,
)

# THE TWO PRIVATE IMPORTS IN THIS MODULE, AND THEY ARE DELIBERATE. `_digest` is
# the hash a contract fingerprint is made of and `_dig` is how an output is
# found inside a tool result. Writing either one again here would be a second
# implementation of a thing whose entire value is that there is one answer - and
# two implementations of a fingerprint is how a contract quietly stops matching
# six months from now. Importing them says the coupling out loud instead.
from app.build import _dig, _digest


# ---------------------------------------------------------------------------
# Vocabulary.


class StormError(RuntimeError):
    """This storm cannot be run, and the message says why."""


class StormRefused(StormError):
    """The contract does not hold. `deviations` names every reason, in order."""

    def __init__(self, detail: str, deviations: Sequence[str] = ()) -> None:
        super().__init__(detail)
        self.detail = detail
        self.deviations = tuple(deviations)


#: Event kinds. Namespaced so a thread's transcript can be filtered to the work
#: without a second scope, and flat strings because that is what `events.frame`
#: puts in the `event:` line a browser dispatches on.
DECLARED = "storm.declared"
STARTED = "storm.started"
REFUSED = "storm.refused"
STEP_STARTED = "storm.step.started"
STEP_FINISHED = "storm.step.finished"
STEP_SKIPPED = "storm.step.skipped"
ASKED = "storm.asked"
FINISHED = "storm.finished"

KINDS = (
    DECLARED,
    STARTED,
    REFUSED,
    STEP_STARTED,
    STEP_FINISHED,
    STEP_SKIPPED,
    ASKED,
    FINISHED,
)

#: How long the storm waits for one step before it stops waiting and says so.
#: Thirty minutes because a baseline over a few hundred rows against a local
#: model is a real thing a person will run, and because this bounds waiting
#: rather than work - see the module docstring's fourth section.
DEFAULT_STEP_TIMEOUT = 1800.0

#: How many steps of one wave run at once. Steps are tool calls, most of which
#: are file reads or a database round trip, so this is about not opening two
#: hundred provider connections rather than about CPU.
DEFAULT_WORKERS = 4

#: Storms this process is running right now, and the flag that asks one to stop.
#: `attach()` reads `_LIVE` to tell a step that is running from a step that was
#: running when the engine died. Process-local on purpose: it is a fact about
#: THIS process, and a second engine has no business claiming a storm is alive
#: because a row said so.
_LIVE: dict[int, float] = {}
_CANCELLED: set[int] = set()
_GUARD = threading.Lock()

#: Said once so the pre-check and the atomic claim cannot drift into two
#: different explanations of the same refusal.
_ALREADY_RUNNING = (
    "storm {storm} is already running in this process. Two runs of one approval "
    "would do approved work twice, which is the one thing an approval cannot "
    "cover."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _registry(registry: Any = None) -> Any:
    """The live registry, imported late - the same reason `app/build.py` does.

    `app.tools` imports the proposer, which imports `app.build`; importing the
    registry at module level here would drag that whole graph in at import time
    for a module that only needs it when something is actually declared or run.
    """
    if registry is not None:
        return registry
    from app.tools.registry import REGISTRY

    return REGISTRY


def tool_fingerprint(spec: Any) -> str:
    """What a tool WAS, hashed, so a change under an approved plan is visible.

    Everything a person was implicitly told when they approved a step that names
    this tool: what it accepts, what it reads, what it writes, what it may stamp,
    which of its arguments it says cannot be its answer, and whether it needs
    their permission each time. A change to any of those is a change to what
    saying yes meant.

    `description` is not in it. Rewording a tool's help text does not change what
    it does, and a fingerprint that trips on prose trains people to click through
    the check that matters.
    """
    return _digest(
        {
            "name": spec.name,
            "schema": spec.schema,
            "approval": spec.approval,
            "reads": list(spec.reads),
            "writes": list(spec.writes),
            "measures": list(spec.measures),
            "bounds": list(spec.bounds),
        }
    )


# ---------------------------------------------------------------------------
# The contract.


@dataclass(frozen=True)
class StepContract:
    """One approved step, reduced to what running it involves.

    Deliberately not a `Step`. It carries no cost, because the executor does not
    consume one and because a cost that could be rebuilt from JSON is a number
    with no origin wearing one - see the module docstring. `contract` is the
    `Step.contract_fingerprint()` the step was approved with; `tool_contract` is
    `tool_fingerprint()` of the tool as it was registered at that moment.
    """

    id: str
    tool: str
    why: str
    arguments: Mapping[str, Any]
    produces: tuple[Mapping[str, Any], ...]
    needs: tuple[str, ...]
    exit_criterion: Mapping[str, Any]
    contract: str
    tool_contract: str

    # -- the contract itself ----------------------------------------------

    def recomputed(self) -> str:
        """`Step.contract_fingerprint()` recomputed off what is stored here.

        The same five fields in the same order, hashed with the same function,
        so a stored plan and its stored hash have to agree with each other.
        """
        return _digest(
            {
                "id": self.id,
                "tool": self.tool,
                "arguments": dict(self.arguments),
                "needs": list(self.needs),
                "produces": [dict(item) for item in self.produces],
                "exit_criterion": dict(self.exit_criterion),
            }
        )

    def criterion(self) -> ExitCriterion:
        """The build's own type, rebuilt from the record and re-validated.

        `ExitCriterion` has no minting door on it - it is a checkable claim, not
        a number - so this is a reconstruction rather than a second reading of
        one. `met()` is then the build's function deciding whether the step
        worked, which is the whole point of stating it before it ran.
        """
        return ExitCriterion(**dict(self.exit_criterion))

    # -- inputs and outputs -----------------------------------------------

    def refs(self) -> tuple[tuple[str, str, str], ...]:
        """`(argument, step, output)` for every argument that is a reference."""
        found = []
        for key, value in dict(self.arguments).items():
            if isinstance(value, Mapping) and "$from_step" in value:
                found.append((key, str(value["$from_step"]), str(value.get("output"))))
        return tuple(found)

    def bind(self, produced: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        """Arguments with every reference replaced by what an approved step made.

        A reference that cannot be resolved raises rather than reaching a tool as
        `None`. `app/build.py`'s `Step.bind` says why in one sentence - a step
        running on a silently missing input is the shape of failure the whole
        object exists to prevent - and this is that sentence at execution time.
        """
        bound: dict[str, Any] = {}
        for key, value in dict(self.arguments).items():
            if not (isinstance(value, Mapping) and "$from_step" in value):
                bound[key] = value
                continue
            source = str(value["$from_step"])
            output = str(value.get("output"))
            available = produced.get(source)
            if available is None or output not in available:
                raise StormRefused(
                    f"step {self.id!r} needs {output!r} from step {source!r} and "
                    "it is not there. Nothing was run.",
                    (
                        f"step {self.id!r} would run on an input nobody approved: "
                        f"{source}.{output} was never produced",
                    ),
                )
            bound[key] = available[output]
        return bound

    def harvest(self, result: Mapping[str, Any] | None) -> dict[str, Any]:
        """The outputs this step promised, pulled out of the tool's own result."""
        found: dict[str, Any] = {}
        for output in self.produces:
            name = str(output.get("name"))
            at = str(output.get("at") or name)
            value, present = _dig(result or {}, at)
            if not present:
                raise StormRefused(
                    f"step {self.id!r} promised {name!r} at {at!r} in the result "
                    f"of {self.tool!r}, and it is not there. The plan and the "
                    "tool disagree.",
                    (
                        f"step {self.id!r} did not produce the approved output "
                        f"{name!r}",
                    ),
                )
            found[name] = value
        return found

    # -- serialisation -----------------------------------------------------

    @classmethod
    def of(cls, step: Mapping[str, Any], *, tool_contract: str) -> "StepContract":
        return cls(
            id=str(step["id"]),
            tool=str(step["tool"]),
            why=str(step.get("why") or ""),
            arguments=dict(step.get("arguments") or {}),
            produces=tuple(dict(item) for item in (step.get("produces") or ())),
            needs=tuple(str(name) for name in (step.get("needs") or ())),
            exit_criterion=dict(step.get("exit_criterion") or {}),
            contract=str(step.get("contract") or ""),
            tool_contract=tool_contract,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "why": self.why,
            "arguments": dict(self.arguments),
            "produces": [dict(item) for item in self.produces],
            "needs": list(self.needs),
            "exit_criterion": dict(self.exit_criterion),
            "contract": self.contract,
            "tool_contract": self.tool_contract,
        }


@dataclass(frozen=True)
class Manifest:
    """What was approved. Written once, never edited, and the storm's authority.

    `blueprint` is the whole build exactly as `Build.as_dict()` emitted it, kept
    because it is the record the person read and the object the diagram draws -
    after a restart the picture has to come from somewhere, and it comes from
    here rather than from a re-proposal that might differ. `steps` is the
    executable reduction of the same thing. A test asserts the two agree.
    """

    build_id: str
    title: str
    for_outcome: str
    because: str
    fingerprint: str
    exit_criterion: Mapping[str, Any]
    environment: Mapping[str, Any]
    waves: tuple[tuple[str, ...], ...]
    needs_approval: tuple[str, ...]
    steps: tuple[StepContract, ...]
    blueprint: Mapping[str, Any]
    approved_at: str = ""

    # -- construction ------------------------------------------------------

    @classmethod
    def of(
        cls,
        plan: Any,
        *,
        fingerprint: str = "",
        registry: Any = None,
    ) -> "Manifest":
        """The manifest of a plan, refusing anything that could not honestly run.

        `plan` is a `Build` or the dict one emitted, and either way A MANIFEST IS
        MINTED ONLY FROM A BUILD THAT VALIDATED. A dict is turned back into one
        by `_a_build_again` and checked against the record it came from; if it
        will not become a `Build`, it is not a plan and nothing is recorded.

        THE FINGERPRINT IS NOT WHAT SAYS THAT, and this docstring used to claim
        it was. `Build.fingerprint()` is the digest of the dict it is handed, so
        a caller supplying the object supplies the hash too, and the check
        reduces to `_digest(x) == _digest(x)`. What it genuinely says is WHICH
        plan: a dict that does not hash to the figure the person approved is not
        the plan they approved, which is a real and different guarantee. What
        says the plan is a plan is the paragraph above.

        Three checks, in this order, and each one refuses on its own:

        1. **Which plan.** The dict hashes to the approved figure.
        2. **The executable subset, against THIS registry.** The tool is
           registered here, it is not one that only means something when a person
           runs it, the arguments are ones it takes. Re-asked at the storm's door
           because the storm must never run a step on the strength of a
           validation somebody else says happened - and against the registry this
           storm was handed, which is the one it will actually call.
        3. **A plan at all.** `Build.validate()` - the graph, the types, the
           enums, the references, the egress rule - run by the build's own code
           on the plan rebuilt, never by a second reading of it here. A second
           implementation of that check would be a second opinion, and two
           opinions about whether a plan is runnable is how one quietly stops
           being checked.
        """
        registry = _registry(registry)
        # A plan that cannot even say what it is refuses as a refusal, not as
        # whatever exception its own `as_dict` happened to raise. `Build.as_dict`
        # calls `waves()`, which raises on a graph that does not schedule, and a
        # caller catching `StormRefused` would otherwise get that one bare.
        try:
            blueprint = plan.as_dict() if hasattr(plan, "as_dict") else dict(plan)
            approved = fingerprint or (
                plan.fingerprint() if hasattr(plan, "fingerprint") else ""
            )
        except Exception as error:  # noqa: BLE001 - a plan that will not read out is not a plan
            raise StormRefused(
                "this plan cannot be read out as a plan, so there is nothing to "
                f"record: {type(error).__name__}: {error}. Nothing was recorded.",
                (f"the plan will not describe itself: {type(error).__name__}: {error}",),
            ) from error
        if not approved:
            raise StormRefused(
                "a plan arrived with no fingerprint, so there is nothing saying "
                "which plan a person approved. Nothing was recorded."
            )
        if _digest(blueprint) != approved:
            raise StormRefused(
                "this plan does not hash to the figure that was approved, so it "
                "is not the plan that was approved. Nothing was recorded.",
                ("the plan and the approval do not describe the same object",),
            )

        steps: list[StepContract] = []
        for raw in blueprint.get("steps") or ():
            spec = registry.get(str(raw.get("tool")))
            if spec is None:
                raise StormRefused(
                    f"step {raw.get('id')!r} names the tool {raw.get('tool')!r}, "
                    "which is not registered on this machine. A plan whose steps "
                    "name tools that do not exist cannot run.",
                    (f"step {raw.get('id')!r} names an unregistered tool",),
                )
            contract = StepContract.of(raw, tool_contract=tool_fingerprint(spec))
            _check_the_step_can_run(contract, spec)
            if contract.contract and contract.recomputed() != contract.contract:
                raise StormRefused(
                    f"step {contract.id!r} does not match its own contract "
                    "fingerprint, so the plan and the hash of the plan disagree.",
                    (f"step {contract.id!r} was edited after it was fingerprinted",),
                )
            steps.append(contract)

        # THE PLAN IS A BUILD OR IT IS NOTHING. Last of the three checks, so the
        # sentences the earlier two produce - which name a step and say what is
        # wrong with it - are the ones a person reads when they apply. This one
        # catches what a per-step check structurally cannot: the graph, the
        # types, the enums, the references, and any field of the record that a
        # validated build of it does not reproduce.
        _the_plan_that_validated(plan, blueprint, registry)

        manifest = cls(
            build_id=str(blueprint.get("id") or ""),
            title=str(blueprint.get("title") or ""),
            for_outcome=str(blueprint.get("for_outcome") or ""),
            because=str(blueprint.get("because") or ""),
            fingerprint=approved,
            exit_criterion=dict(blueprint.get("exit_criterion") or {}),
            environment=dict(blueprint.get("environment") or {}),
            waves=tuple(
                tuple(str(name) for name in wave)
                for wave in (blueprint.get("waves") or ())
            ),
            needs_approval=tuple(
                str(name) for name in (blueprint.get("needs_approval") or ())
            ),
            steps=tuple(steps),
            blueprint=dict(blueprint),
            approved_at=_now(),
        )
        manifest._check_the_environment(registry)
        return manifest

    # -- reading -----------------------------------------------------------

    def step(self, step_id: str) -> StepContract:
        for item in self.steps:
            if item.id == step_id:
                return item
        raise KeyError(step_id)

    @property
    def step_ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.steps)

    def _check_the_environment(self, registry: Any) -> None:
        """The egress rule, re-checked against the tools this plan actually names.

        `Build.validate` did this at proposal time. It is done again because the
        environment is part of what the person approved and because a tool can
        gain a `reads` entry between a proposal and a run - which is precisely
        the drift this module exists to catch, and it must not be caught only
        after the request has already left the machine.
        """
        if self.environment.get("egress"):
            return
        for item in self.steps:
            spec = registry.get(item.tool)
            reaches = sorted(set(getattr(spec, "reads", ())) & NETWORK_READS)
            if reaches:
                raise StormRefused(
                    f"step {item.id!r} runs {item.tool!r}, which reads {reaches}, "
                    f"and the environment "
                    f"{self.environment.get('name')!r} declares no egress.",
                    (
                        f"step {item.id!r} would leave this machine from a sandbox "
                        "that said it could not",
                    ),
                )

    # -- the contract, checked ---------------------------------------------

    def deviations_from(self, plan: Any) -> tuple[str, ...]:
        """What is different about `plan`, in sentences. Empty means it matches.

        The same comparison `Build.deviations_from` makes, from the other side:
        this object is the approved one, so the sentences are about `plan`.
        `tests/test_the_storm_runs_only_what_was_approved.py` asserts the two
        agree sentence for sentence on the same mutations, which is what stops
        this becoming a weaker copy of the check it stands in for.
        """
        other = plan.as_dict() if hasattr(plan, "as_dict") else dict(plan)
        notes: list[str] = []
        theirs_id = str(other.get("id") or "")
        if theirs_id != self.build_id:
            notes.append(
                f"this is build {theirs_id!r}, not the approved {self.build_id!r}"
            )
        if str(other.get("for_outcome") or "") != self.for_outcome:
            notes.append(
                f"it now answers {str(other.get('for_outcome') or '')!r}, not "
                f"{self.for_outcome!r}"
            )
        if dict(other.get("environment") or {}) != dict(self.environment):
            notes.append("the environment changed")
        if dict(other.get("exit_criterion") or {}) != dict(self.exit_criterion):
            notes.append("the exit criterion changed")

        theirs = {str(step.get("id")): step for step in (other.get("steps") or ())}
        mine = {item.id: item for item in self.steps}
        for added in sorted(set(theirs) - set(mine)):
            notes.append(f"step {added!r} was added and was never approved")
        for removed in sorted(set(mine) - set(theirs)):
            notes.append(f"approved step {removed!r} is gone")
        for shared in sorted(set(theirs) & set(mine)):
            fingerprint = str(theirs[shared].get("contract") or "")
            if not fingerprint:
                fingerprint = StepContract.of(
                    theirs[shared], tool_contract=""
                ).recomputed()
            if fingerprint != mine[shared].contract:
                notes.append(f"step {shared!r} does something different now")
        return tuple(notes)

    def drift(self, registry: Any = None) -> tuple[str, ...]:
        """What has changed about the TOOLS since this was approved.

        The deviation `Build.deviations_from` structurally cannot see: every step
        is byte for byte what it was, and the thing a step names is not. A tool
        that grew an argument, that reads the network now, that writes somewhere
        new, or that started requiring a person's permission is a different
        promise from the one the person read.
        """
        registry = _registry(registry)
        notes: list[str] = []
        for item in self.steps:
            spec = registry.get(item.tool)
            if spec is None:
                notes.append(
                    f"step {item.id!r} runs {item.tool!r}, which is no longer a "
                    "registered tool on this machine"
                )
                continue
            if tool_fingerprint(spec) != item.tool_contract:
                # NAME THE CHANGE WHERE IT CAN BE NAMED. The fingerprint says
                # something moved; a permission that appeared is the one change
                # a person most needs told in words, because it is the one where
                # carrying on would mean the harness doing on its own authority
                # a thing the tool now says needs theirs.
                if getattr(spec, "approval", "never") == "always" and (
                    item.id not in self.needs_approval
                ):
                    notes.append(
                        f"step {item.id!r} runs {item.tool!r}, which now needs your "
                        "permission each time and did not when this was approved"
                    )
                else:
                    notes.append(
                        f"the tool {item.tool!r} that step {item.id!r} runs is not "
                        "the tool that was approved: what it accepts, what it "
                        "touches or what it may record has changed since you said yes"
                    )
        for item in self.steps:
            if item.contract and item.recomputed() != item.contract:
                notes.append(
                    f"step {item.id!r} no longer matches the contract it was "
                    "approved with"
                )
        return tuple(notes)

    # -- serialisation -----------------------------------------------------

    def as_dict(self) -> dict[str, Any]:
        return {
            "build_id": self.build_id,
            "title": self.title,
            "for_outcome": self.for_outcome,
            "because": self.because,
            "fingerprint": self.fingerprint,
            "exit_criterion": dict(self.exit_criterion),
            "environment": dict(self.environment),
            "waves": [list(wave) for wave in self.waves],
            "needs_approval": list(self.needs_approval),
            "steps": [item.as_dict() for item in self.steps],
            "blueprint": dict(self.blueprint),
            "approved_at": self.approved_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Manifest":
        """Read a manifest back off disk. NOTHING IS RECONSTRUCTED BUT THE RECORD.

        No `Build`, no `Step`, no `Cost` and above all no `Estimate` comes out of
        this. The costs inside `blueprint` stay what they are - JSON, a record of
        what was shown, with the provenance the proposer put on them - and
        nothing in this module reads a number out of them. See the fourth section
        of the module docstring for why that door stays shut.
        """
        return cls(
            build_id=str(payload.get("build_id") or ""),
            title=str(payload.get("title") or ""),
            for_outcome=str(payload.get("for_outcome") or ""),
            because=str(payload.get("because") or ""),
            fingerprint=str(payload.get("fingerprint") or ""),
            exit_criterion=dict(payload.get("exit_criterion") or {}),
            environment=dict(payload.get("environment") or {}),
            waves=tuple(
                tuple(str(name) for name in wave)
                for wave in (payload.get("waves") or ())
            ),
            needs_approval=tuple(
                str(name) for name in (payload.get("needs_approval") or ())
            ),
            steps=tuple(
                StepContract(
                    id=str(step.get("id")),
                    tool=str(step.get("tool")),
                    why=str(step.get("why") or ""),
                    arguments=dict(step.get("arguments") or {}),
                    produces=tuple(dict(o) for o in (step.get("produces") or ())),
                    needs=tuple(str(n) for n in (step.get("needs") or ())),
                    exit_criterion=dict(step.get("exit_criterion") or {}),
                    contract=str(step.get("contract") or ""),
                    tool_contract=str(step.get("tool_contract") or ""),
                )
                for step in (payload.get("steps") or ())
            ),
            blueprint=dict(payload.get("blueprint") or {}),
            approved_at=str(payload.get("approved_at") or ""),
        )


def _check_the_step_can_run(step: StepContract, spec: Any) -> None:
    """Can this step's tool actually be called with these arguments?

    The executable subset of `Build.validate`, re-asked at the storm's door. Each
    refusal here is a plan that would have failed AFTER somebody approved it,
    which is the worst moment to find out.
    """
    if step.tool in PERSON_ONLY_TOOLS:
        raise StormRefused(
            f"step {step.id!r} names {step.tool!r}, which only means anything when "
            "the person calls it themselves. Run by the harness it would record "
            "somebody else's word as theirs.",
            (f"step {step.id!r} names a tool the harness may not run for a person",),
        )
    properties = dict(spec.schema.get("properties") or {})
    required = set(spec.schema.get("required") or ())
    supplied = dict(step.arguments)
    unknown = sorted(set(supplied) - set(properties))
    if unknown:
        raise StormRefused(
            f"step {step.id!r} passes {unknown} to {step.tool!r}, which has no such "
            f"argument. Its schema takes {sorted(properties)}.",
            (f"step {step.id!r} would send an argument {step.tool!r} does not take",),
        )
    missing = sorted(required - set(supplied))
    if missing:
        raise StormRefused(
            f"step {step.id!r} calls {step.tool!r} without {missing}, which its "
            "schema requires.",
            (f"step {step.id!r} is missing an argument {step.tool!r} requires",),
        )


# ---------------------------------------------------------------------------
# A PLAN BECOMES A BUILD AGAIN, OR IT DOES NOT BECOME A MANIFEST.
#
# THE DEFECT THIS CLOSES. `Manifest.of` used to say, in its own docstring, that
# "the fingerprint is what says this dict came from a `Build` that passed the
# first one". It said no such thing. The digest was taken over the dict the
# caller supplied, so whoever supplied the object supplied the hash, and the
# check reduced to `_digest(x) == _digest(x)`. Two plans that `Build.validate()`
# refuses loudly were declared and ran to `done` through that hole: one whose
# dependencies form a cycle (`a` needs `b`, `b` needs `a`, with hand-written
# waves that never asked the graph anything), and one passing a string to an
# argument its tool's schema declares as an integer. Neither is reachable over
# HTTP - `POST /api/storms` re-proposes server-side and never accepts a plan -
# and no model has an approve or a run tool. Both are reachable from Python, and
# a guard that reads as protection in a review and is not one is worse than no
# guard at all, which is the thing this repository has now decided twice.
#
# THE MECHANISM. A manifest is minted from a `Build`, and only from a `Build`. A
# `Build` validates in `__post_init__`, so an invalid one cannot exist; a dict
# that arrives instead is turned back into one, and if it will not become one it
# is not a plan and nothing is recorded. The checking is `Build.validate` itself
# rather than a reading of it here, for the reason the old docstring gave and
# then failed to honour: a second implementation of that check is a second
# opinion, and two opinions about whether a plan is runnable is how one quietly
# stops being checked.
#
# WHAT IS NOT REBUILT, AND WHY THE COST DOOR STAYS SHUT. Section 4 of the module
# docstring is not weakened by a line of this. NO COST IS EVER REBUILT. `Step`
# will not exist without a `Cost`, so the throwaway copy is given four UNKNOWN
# estimates - the one arm of `Estimate` that carries no magnitude at all - and
# the plan's own costs stay in `blueprint` as the record they are. Not one
# number crosses from JSON into an `Estimate`, which is precisely what
# `app/build.py` welded shut and what a naive deserialiser here would have
# reopened while fixing something else.


#: What `_the_same_plan` does not compare whole, named here because a skipped
#: check must be visible. `cost` is skipped entirely - the copy that gets
#: validated carries none, see `_a_cost_that_claims_nothing`.
#:
#: `say` is here only to be taken OFF the plain comparison and handed to
#: `_the_same_costless_say`, which drops one line of it and compares the rest.
#: Skipping it whole would have been the easy reading - its fourth line is the
#: cost in words - and it is wrong, because `declare()` writes `say` straight
#: into the conversation as an assistant message. That left a caller able to put
#: any sentence at all into a person's transcript under the harness's name,
#: which I did to myself while attacking this and did not enjoy reading.
_NOT_RE_DERIVED = ("cost", "say")


def _a_cost_that_claims_nothing() -> Cost:
    """Four UNKNOWN estimates: a cost that states no figure and pretends to none.

    `Step.__post_init__` refuses a step with no cost, and rebuilding the plan's
    real one would be exactly the door section 4 of the module docstring keeps
    shut - a cost dict off disk, rehydrated, is a number whose provenance is a
    string that came back from SQLite. `Estimate.unknown` takes no magnitude
    from anybody, so this object cannot carry one. It exists for as long as
    `Build.validate()` takes to run and is then dropped; nothing reads it, and
    the costs a person was shown stay in the manifest's `blueprint`.
    """
    return Cost(
        **{
            dimension: Estimate.unknown(
                dimension,
                why=(
                    "the storm does not rebuild costs. This is the throwaway copy "
                    "of the plan that `Build.validate` is run against; the figures "
                    "a person was shown are in the record and are not read here."
                ),
                find_out_by=(
                    "read the cost in the manifest's blueprint, which is what the "
                    "proposer put there and what the person approved"
                ),
            )
            for dimension in COST_DIMENSIONS
        }
    )


#: WHAT THE RECORD IS ALLOWED TO CONTAIN, so that a field this module does not
#: know how to turn back into a `Build` is refused BY NAME rather than dropped.
#: `_the_same_plan` would catch a dropped field anyway - that is what the round
#: trip is for - but it would catch it as "step 'x' is not what a validated build
#: says it is", and the next person deserves to be told which field and why.
#:
#: These sets are a coupling to `app/build.py` and they are meant to be: when a
#: `Step` or a `Build` grows a field, the storm stops accepting plans until
#: somebody has decided how that field is validated. That is the direction this
#: has to fail in. `contract` and `edges` and `waves` and `needs_approval` and
#: `step_states` and `say` are derived by `as_dict()` rather than stored on the
#: object, so they are listed as recorded but never passed to a constructor.
#:
#: `Step.operates_on` IS NOT HERE, AND THAT IS A DECISION RATHER THAN AN
#: OVERSIGHT. `app/build.py` keeps it out of `Step.as_dict()` and says the choice
#: belongs to whoever owns this list. It does, and the answer is no: a `Subject`
#: carries a `witness` - a size and a modification time read at the moment it was
#: established - and a witness rebuilt from JSON is a witness that certifies
#: itself, which is the same defect as the one this whole section closes. If the
#: field is ever recorded, what has to arrive with it is a way for a `Subject` to
#: say whether it was minted or typed, and that is `app/build.py`'s to give.
_RECORDED_STEP_KEYS = frozenset(
    {
        "id",
        "tool",
        "why",
        "arguments",
        "produces",
        "needs",
        "cost",
        "exit_criterion",
        "risks",
        "contract",
        # `operates_on` is what a step's cost was measured AGAINST, and it is
        # the whole point of the subject binding: a step costed from a count of
        # a different file is the defect that binding exists to refuse. It was
        # kept out of `Step.as_dict()` until this list knew about it, because
        # `_nothing_unrecorded` correctly refuses a recorded key it cannot map
        # onto a constructor argument - a field the validation never sees is a
        # field nobody checked. Now that `_a_step_again` rebuilds it, it is
        # recorded, rehydrated, and compared by `_the_same_plan` for free.
        "operates_on",
    }
)
_RECORDED_BUILD_KEYS = frozenset(
    {
        "id",
        "title",
        "for_outcome",
        "because",
        "steps",
        "edges",
        "waves",
        "environment",
        "cost",
        "exit_criterion",
        "risks",
        "questions",
        "facts",
        "needs_approval",
        "step_states",
        "say",
    }
)
_RECORDED_ENVIRONMENT_KEYS = frozenset(
    {
        "name",
        "working_dir",
        "egress",
        "egress_reason",
        "data",
        "installs",
        "python",
    }
)


def _nothing_unrecorded(what: str, raw: Mapping[str, Any], known: frozenset) -> None:
    unknown = sorted(set(raw) - known)
    if unknown:
        raise BuildInvalid(
            f"{what} carries {unknown}, which this storm does not know how to turn "
            "back into a build. A field the validation never sees is a field nobody "
            "checked, so it is refused rather than dropped. If `app/build.py` grew "
            "this field, `app/storm.py` has to say how it is validated."
        )


def _an_argument_again(value: Any) -> Any:
    """A recorded argument, with a reference made a `Ref` again.

    `Ref` is the only argument shape `Build.as_dict()` flattens, and it has to
    come back as one or `Build._validate_ref` never runs on it - which would
    leave the check that a step's input really is an earlier step's declared
    output out of the rebuild, in the module whose whole subject is inputs
    nobody approved.
    """
    if isinstance(value, Mapping) and "$from_step" in value:
        return Ref(str(value["$from_step"]), str(value.get("output")))
    return value


def _a_step_again(raw: Mapping[str, Any]) -> Step:
    _nothing_unrecorded(f"step {str(raw.get('id'))!r}", raw, _RECORDED_STEP_KEYS)
    return Step(
        id=str(raw.get("id")),
        tool=str(raw.get("tool")),
        why=str(raw.get("why") or ""),
        arguments={
            str(key): _an_argument_again(value)
            for key, value in dict(raw.get("arguments") or {}).items()
        },
        produces=tuple(Output(**dict(item)) for item in (raw.get("produces") or ())),
        needs=tuple(str(name) for name in (raw.get("needs") or ())),
        cost=_a_cost_that_claims_nothing(),
        exit_criterion=ExitCriterion(**dict(raw.get("exit_criterion") or {})),
        risks=tuple(Risk(**dict(item)) for item in (raw.get("risks") or ())),
        # Copied verbatim, never re-stat'ed, for exactly the reason
        # `_an_environment_again` gives for `DataSnapshot`: a `Subject` carries
        # a `witness` - size and mtime as they were when the subject was
        # established - and reading the file again here would be measuring a
        # different moment and calling it the approved one. A file whose mtime
        # moved between proposal and approval must be caught by the check that
        # is FOR that, not silently absorbed by the rebuild.
        operates_on=_a_subject_again(raw),
    )


def _a_subject_again(raw: Mapping[str, Any]) -> Subject | None:
    """The step's subject as recorded, or a refusal that names it.

    Copied verbatim, never re-stat'ed, for exactly the reason
    `_an_environment_again` gives for `DataSnapshot`: a `Subject` carries a
    `witness` - size and mtime as they were when the subject was established -
    and reading the file again here would be measuring a different moment and
    calling it the approved one. A file whose mtime moved between proposal and
    approval must be caught by the check that is FOR that, not silently absorbed
    by the rebuild.

    It is a function rather than an expression because of what happens when the
    record is malformed. `Subject(**raw)` on a dict missing a field raises a bare
    `TypeError`, which arrives at the caller as "this plan does not pass
    Build.validate ... missing 1 required positional argument: 'how'" - the
    field never named, the reader left to guess which of a step's keys was
    wrong. `test_a_field_this_module_cannot_rebuild_is_refused_by_name` exists
    to insist on the opposite and its docstring says why: the round trip would
    catch a bad field anyway, but it would catch it as "step 'x' is not what a
    validated build says it is", which tells the next person nothing.
    """
    recorded = raw.get("operates_on")
    if recorded is None:
        return None
    try:
        return Subject(**dict(recorded))
    except (TypeError, ValueError) as error:
        raise StormRefused(
            f"step {str(raw.get('id'))!r} records an `operates_on` this module "
            f"cannot rebuild: {error}. A subject is what a step's cost was "
            "measured against, so a record whose subject cannot be reconstructed "
            "is a plan whose most important claim nobody can check. Nothing was "
            "recorded."
        ) from error


def _an_environment_again(raw: Mapping[str, Any]) -> Environment:
    """The sandbox as recorded. `DataSnapshot` is copied, not re-measured.

    A snapshot is a reading of a file taken at proposal time, and re-taking it
    here would be measuring a different moment and calling it the approved one.
    `Build.validate` does not look at snapshots, so nothing in the check turns
    on them; they are carried verbatim so that `_the_same_plan` can compare the
    whole environment rather than a convenient part of it.
    """
    _nothing_unrecorded("the environment", raw, _RECORDED_ENVIRONMENT_KEYS)
    return Environment(
        name=str(raw.get("name") or ""),
        working_dir=str(raw.get("working_dir") or ""),
        egress=bool(raw.get("egress")),
        egress_reason=str(raw.get("egress_reason") or ""),
        data=tuple(DataSnapshot(**dict(item)) for item in (raw.get("data") or ())),
        installs=tuple(str(item) for item in (raw.get("installs") or ())),
        python=str(raw.get("python") or ""),
    )


def _a_build_again(blueprint: Mapping[str, Any]) -> Build:
    """The recorded plan as a `Build`, which is to say: validated, or refused.

    Nothing is returned that did not pass `Build.validate()`, because `Build`
    runs it in `__post_init__`. Every type used here is the build's own; the
    only thing this function decides is how a recorded field maps onto a
    constructor argument, and a field that maps onto nothing raises rather than
    being dropped.
    """
    _nothing_unrecorded("this plan", blueprint, _RECORDED_BUILD_KEYS)
    return Build(
        id=str(blueprint.get("id") or ""),
        title=str(blueprint.get("title") or ""),
        for_outcome=str(blueprint.get("for_outcome") or ""),
        because=str(blueprint.get("because") or ""),
        steps=tuple(_a_step_again(raw) for raw in (blueprint.get("steps") or ())),
        environment=_an_environment_again(dict(blueprint.get("environment") or {})),
        exit_criterion=ExitCriterion(**dict(blueprint.get("exit_criterion") or {})),
        risks=tuple(Risk(**dict(item)) for item in (blueprint.get("risks") or ())),
        questions=tuple(
            Question(**dict(item)) for item in (blueprint.get("questions") or ())
        ),
        facts=dict(blueprint.get("facts") or {}),
    )


def _the_same_costless_say(said: Any, rederived: str) -> bool:
    """Is this the sentence a validated build of this plan says about itself?

    `Build.say()` is five or six lines and exactly one of them is the cost read
    out in words, which the rebuilt copy cannot reproduce because it carries no
    cost. So the FIRST line beginning `Cost:` is dropped from each side and the
    rest must match exactly - the first only, so that a second `Cost:` line
    smuggled in beside it is compared like everything else rather than filtered
    away with the one that had a reason to be skipped.

    This matters more than it looks: `declare()` puts `say` into the thread as an
    assistant message. It is the one field of the record that becomes something a
    person reads as the harness speaking.
    """
    def without_the_cost_line(text: str) -> list[str]:
        lines = str(text).splitlines()
        for index, line in enumerate(lines):
            if line.startswith("Cost:"):
                return lines[:index] + lines[index + 1:]
        return lines

    return without_the_cost_line(said) == without_the_cost_line(rederived)


def _the_same_plan(
    blueprint: Mapping[str, Any], rebuilt: Build
) -> tuple[str, ...]:
    """Is the record the object that was validated? Sentences, empty if it is.

    THIS IS THE HALF A REBUILD ON ITS OWN WOULD MISS. Validating a copy proves
    nothing about the original unless the two are the same plan: a field the
    reconstruction ignores, or one it quietly normalises, would be a field
    nobody checked sitting in the record the person reads and the diagram draws.
    So the copy's own `as_dict()` is compared back against the record, key for
    key, and anything that does not survive the round trip is refused rather
    than accepted on the strength of the parts that did.

    It compares by naming what it skips, and the list is short: `cost`, whole,
    because the validated copy has none - and inside `say`, the one line that
    reads that cost out, which `_the_same_costless_say` drops and nothing else.
    A field added to `Build.as_dict()` later appears here as a mismatch and stops
    the storm, which is the direction this check is meant to fail in.
    """
    theirs = dict(blueprint)
    mine = rebuilt.as_dict()
    notes: list[str] = []

    for key in sorted(set(theirs) | set(mine)):
        if key in _NOT_RE_DERIVED or key == "steps":
            if key == "say" and not _the_same_costless_say(
                theirs.get("say") or "", str(mine.get("say") or "")
            ):
                notes.append(
                    "the plan says something about itself that a validated build "
                    "of it does not say - and `say` is what goes into the "
                    "conversation as the harness speaking"
                )
            continue
        if theirs.get(key) != mine.get(key):
            notes.append(
                f"the plan's {key!r} is not what a validated build of this plan "
                f"says {key!r} is"
            )

    theirs_steps = list(theirs.get("steps") or ())
    mine_steps = list(mine.get("steps") or ())
    if len(theirs_steps) != len(mine_steps):
        notes.append(
            f"the plan records {len(theirs_steps)} steps and a validated build of "
            f"it has {len(mine_steps)}"
        )
        return tuple(notes)
    for recorded, rederived in zip(theirs_steps, mine_steps):
        without_cost_a = {
            key: value for key, value in dict(recorded).items() if key != "cost"
        }
        without_cost_b = {
            key: value for key, value in dict(rederived).items() if key != "cost"
        }
        if without_cost_a != without_cost_b:
            notes.append(
                f"step {str(recorded.get('id'))!r} is not what a validated build "
                "of this plan says that step is"
            )
    return tuple(notes)


def _the_plan_that_validated(plan: Any, blueprint: Mapping[str, Any], registry: Any) -> Build:
    """The `Build` behind this plan, or a refusal. There is no third answer.

    A `Build` handed in is one already: it validated when it was constructed and
    cannot exist otherwise. A dict is turned back into one, and then the record
    and the object are checked against each other.

    `validate(registry)` is called again on both paths, because the registry a
    storm was handed is not necessarily the live one a `Build` validated against
    when it was built - and the whole subject of this module is a plan meeting a
    world that has moved since somebody said yes to it.

    `type(plan) is Build`, NOT `isinstance`, and this is not fussiness. I wrote
    `isinstance` first and then walked a `Build` subclass whose `validate()`
    returned `self` through my own new door: it declared a step passing a string
    to an argument its tool's schema declares an integer, and the storm ran it to
    `done`. A subclass is exactly the thing that can replace the validation being
    trusted, so it is not trusted - it goes down the same path a dict does, where
    a real `Build` is constructed from its record and checked against it.
    """
    try:
        rebuilt = plan if type(plan) is Build else _a_build_again(blueprint)
        rebuilt.validate(registry)
    except StormError:
        raise
    except Exception as error:  # noqa: BLE001 - anything at all here means "not a plan"
        raise StormRefused(
            "this plan does not pass `Build.validate`, so it is not a plan anybody "
            "could have been shown and approved: "
            f"{type(error).__name__}: {error}. Nothing was recorded.",
            (
                "the plan is not a build that validates: "
                f"{type(error).__name__}: {error}",
            ),
        ) from error

    notes = _the_same_plan(blueprint, rebuilt)
    if notes:
        raise StormRefused(
            "the plan that was validated is not the plan in this record, so what "
            "was checked and what would be run are not the same object. Nothing "
            "was recorded.",
            notes,
        )
    return rebuilt


# ---------------------------------------------------------------------------
# Declaring a storm: the moment approval becomes a record.


def declare(
    plan: Any,
    *,
    approved: str = "",
    thread_id: int,
    registry: Any = None,
) -> dict[str, Any]:
    """Record an approval. Nothing runs; this is the contract being written down.

    `plan` is a `Build`, or the dict `propose_build` returned together with the
    `approve` fingerprint from the same call. The fingerprint is what the person
    said yes to and it is verified against the plan rather than trusted.

    Two writes, in this order and for the reason `app/events.py` gives: the row
    first, because it is the contract and it must exist before anything claims to
    be executing it, then the `storm.declared` event, because an event is a thing
    that happened and it did not happen until the row was there.
    """
    manifest = Manifest.of(plan, fingerprint=approved, registry=registry)
    thread = events.get_thread(int(thread_id))
    if thread is None:
        raise StormError(
            f"there is no thread {thread_id}. A storm belongs to a conversation: "
            "its progress is that conversation's transcript, and a storm with "
            "nowhere to report is work nobody can see."
        )

    events.ensure_tables()
    with db.session() as connection:
        cursor = connection.execute(
            "INSERT INTO storms (thread_id, build_id, title, for_outcome, "
            "fingerprint, manifest_json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                int(thread_id),
                manifest.build_id,
                manifest.title,
                manifest.for_outcome,
                manifest.fingerprint,
                json.dumps(manifest.as_dict()),
            ),
        )
        storm_id = int(cursor.lastrowid)

    declared = events.append(
        DECLARED,
        {
            "storm": storm_id,
            "build": manifest.build_id,
            "title": manifest.title,
            "for_outcome": manifest.for_outcome,
            "fingerprint": manifest.fingerprint,
            "waves": [list(wave) for wave in manifest.waves],
            "steps": [
                {"id": item.id, "tool": item.tool, "why": item.why, "state": "queued"}
                for item in manifest.steps
            ],
            "needs_approval": list(manifest.needs_approval),
            "exit_criterion": dict(manifest.exit_criterion),
            "say": manifest.blueprint.get("say", ""),
        },
        thread_id=int(thread_id),
        project_id=thread.get("project_id"),
    )
    with db.session() as connection:
        connection.execute(
            "UPDATE storms SET declared_event_id = ? WHERE id = ?",
            (int(declared["id"]), storm_id),
        )

    # The transcript is the artifact. A storm that only existed as events would
    # be invisible to the model the person is talking to, which reads messages -
    # so the plan goes into the conversation once, at the moment it is approved,
    # and the outcome goes in once at the end. Not per step: a message per step
    # would bury the conversation in machine chatter, and the events are where
    # the live picture belongs.
    events.add_message(
        int(thread_id),
        "assistant",
        "Approved and queued as storm "
        f"{storm_id}.\n{manifest.blueprint.get('say') or manifest.title}",
    )
    return {"storm": storm_id, "declared": declared, "manifest": manifest}


def _row(storm_id: int) -> dict[str, Any]:
    events.ensure_tables()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM storms WHERE id = ?", (int(storm_id),)
        ).fetchone()
    if row is None:
        raise StormError(f"there is no storm {storm_id}")
    return dict(row)


def load(storm_id: int) -> tuple[int, Manifest]:
    """The thread and the manifest for one storm, off disk. Raises if unknown."""
    row = _row(storm_id)
    return int(row["thread_id"]), Manifest.from_dict(json.loads(row["manifest_json"]))


def list_for_thread(thread_id: int) -> list[dict[str, Any]]:
    """Every storm in one conversation, newest first."""
    events.ensure_tables()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT id, thread_id, build_id, title, for_outcome, fingerprint, "
            "declared_event_id, created_at FROM storms WHERE thread_id = ? "
            "ORDER BY id DESC",
            (int(thread_id),),
        ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Attaching: the state of a storm, folded out of its own log.


@dataclass(frozen=True)
class StepState:
    """Where one node in the picture is. The names are `build.STEP_STATES`."""

    id: str
    tool: str
    why: str
    state: str
    ok: bool | None = None
    because: str = ""
    result: Any = None
    verification: Mapping[str, Any] | None = None
    outputs: Mapping[str, Any] = field(default_factory=dict)
    attempts: int = 0
    started_event: int = 0
    finished_event: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "why": self.why,
            "state": self.state,
            "ok": self.ok,
            "because": self.because,
            "verification": dict(self.verification) if self.verification else None,
            "outputs": dict(self.outputs),
            "attempts": self.attempts,
            "started_event": self.started_event,
            "finished_event": self.finished_event,
        }


@dataclass(frozen=True)
class Storm:
    """A storm as it stands right now: the contract, and what has happened to it."""

    id: int
    thread_id: int
    manifest: Manifest
    state: str
    steps: Mapping[str, StepState]
    live: bool = False
    deviations: tuple[str, ...] = ()
    verification: Mapping[str, Any] | None = None
    last_event_id: int = 0

    @property
    def stalled(self) -> tuple[str, ...]:
        return tuple(
            name for name, step in self.steps.items() if step.state == "stalled"
        )

    @property
    def produced(self) -> dict[str, dict[str, Any]]:
        """`{step: {output: value}}` for every step that finished and verified."""
        return {
            name: dict(step.outputs)
            for name, step in self.steps.items()
            if step.state == "done"
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "storm": self.id,
            "thread_id": self.thread_id,
            "state": self.state,
            "live": self.live,
            "build": self.manifest.blueprint,
            "manifest": {
                key: value
                for key, value in self.manifest.as_dict().items()
                if key != "blueprint"
            },
            "steps": [self.steps[name].as_dict() for name in self.manifest.step_ids],
            "waves": [list(wave) for wave in self.manifest.waves],
            "stalled": list(self.stalled),
            "deviations": list(self.deviations),
            "verification": dict(self.verification) if self.verification else None,
            "last_event_id": self.last_event_id,
            "step_states": list(STEP_STATES),
        }


def _thread_events(
    thread_id: int, storm_id: int, after: int = 0
) -> list[dict[str, Any]]:
    """Every event this storm wrote, oldest first, through the public reader.

    `events.since()` and not a query of our own: it is the one door onto the log
    and it marks what it hands back as something somebody said, which is a
    property worth keeping even here. Paged, because a long conversation's
    transcript is longer than one page and a storm's history must not be
    truncated by a default.

    `after` is the id of the `storm.declared` event, and it is what keeps this
    from getting slower every time somebody talks in the thread: a storm's own
    events all come after the event that declared it, so everything before that
    id is provably not ours and is never read.
    """
    scope = f"thread:{int(thread_id)}"
    cursor = max(0, int(after) - 1)
    found: list[dict[str, Any]] = []
    while True:
        page = events.since(scope, cursor, 500)
        if not page:
            break
        for row in page:
            cursor = row["id"]
            payload = row.get("payload") or {}
            if row["kind"] in KINDS and int(payload.get("storm") or 0) == int(storm_id):
                found.append(row)
        if len(page) < 500:
            break
    return found


def attach(storm_id: int) -> Storm:
    """Re-attach to a storm: the manifest off disk, the state out of the log.

    This is the whole survival story and it is deliberately not a recovery path.
    A fresh engine process calls exactly what a running one calls, because there
    is nothing to recover: the contract is a row that was written once and every
    state change is an event that was committed before it was streamed.

    **A step that is `running` with nothing live is `stalled`.** `_LIVE` is a
    fact about this process, so a `storm.step.started` with no matching finish
    and no thread running it means the engine died with that step in flight. Its
    side effects may have landed or may not have. Calling that `queued` and
    running it again would be the silent restart the spec forbids, and calling it
    `failed` would claim we know something we do not.
    """
    row = _row(storm_id)
    thread_id = int(row["thread_id"])
    manifest = Manifest.from_dict(json.loads(row["manifest_json"]))
    declared_at = int(row["declared_event_id"] or 0)
    with _GUARD:
        live = int(storm_id) in _LIVE

    states: dict[str, dict[str, Any]] = {
        item.id: {
            "state": "queued",
            "ok": None,
            "because": "",
            "result": None,
            "verification": None,
            "outputs": {},
            "attempts": 0,
            "started_event": 0,
            "finished_event": 0,
        }
        for item in manifest.steps
    }
    storm_state = "queued"
    verification: Mapping[str, Any] | None = None
    deviations: tuple[str, ...] = ()
    finished = False
    ever_started = False
    last_event_id = 0

    for frame in _thread_events(thread_id, storm_id, declared_at):
        payload = frame.get("payload") or {}
        kind = frame["kind"]
        last_event_id = int(frame["id"])
        if kind == STARTED:
            ever_started = True
            storm_state = "running"
        elif kind == REFUSED:
            deviations = tuple(str(note) for note in (payload.get("deviations") or ()))
            storm_state = "waiting_approval"
        elif kind == ASKED:
            storm_state = "waiting_input"
        elif kind == FINISHED:
            finished = True
            storm_state = str(payload.get("state") or "done")
            verification = payload.get("verification")
        elif kind in (STEP_STARTED, STEP_FINISHED, STEP_SKIPPED):
            name = str(payload.get("step") or "")
            if name not in states:
                continue
            entry = states[name]
            if kind == STEP_STARTED:
                entry["state"] = "running"
                entry["attempts"] = int(entry["attempts"]) + 1
                entry["started_event"] = int(frame["id"])
                entry["ok"] = None
                entry["because"] = ""
            else:
                entry["state"] = str(payload.get("state") or "failed")
                entry["ok"] = payload.get("ok")
                entry["because"] = str(payload.get("because") or "")
                entry["result"] = payload.get("result")
                entry["verification"] = payload.get("verification")
                entry["outputs"] = dict(payload.get("outputs") or {})
                entry["finished_event"] = int(frame["id"])

    if not live:
        for entry in states.values():
            if entry["state"] == "running":
                entry["state"] = "stalled"
                entry["because"] = (
                    "the engine stopped while this step was running. Whether it "
                    "finished its work is not knowable from here, so it is neither "
                    "done nor queued."
                )

    # WAITING BEATS STALLED, and the order is the whole message. A storm that
    # asked a question and a storm that was interrupted are both stopped; only
    # one of them is stopped ON SOMEBODY, and that is the more useful thing for
    # a person to be shown. The stalled steps are still named in `stalled`, so
    # nothing is hidden by preferring the state that says who is holding it.
    if finished:
        pass
    elif live:
        storm_state = "running"
    elif storm_state in ("waiting_approval", "waiting_input"):
        pass
    elif any(entry["state"] == "stalled" for entry in states.values()):
        storm_state = "stalled"
    elif ever_started or any(entry["state"] != "queued" for entry in states.values()):
        storm_state = "stalled"
    else:
        storm_state = "queued"

    steps = {
        item.id: StepState(
            id=item.id,
            tool=item.tool,
            why=item.why,
            state=states[item.id]["state"],
            ok=states[item.id]["ok"],
            because=states[item.id]["because"],
            result=states[item.id]["result"],
            verification=states[item.id]["verification"],
            outputs=states[item.id]["outputs"],
            attempts=states[item.id]["attempts"],
            started_event=states[item.id]["started_event"],
            finished_event=states[item.id]["finished_event"],
        )
        for item in manifest.steps
    }
    return Storm(
        id=int(storm_id),
        thread_id=thread_id,
        manifest=manifest,
        state=storm_state,
        steps=steps,
        live=live,
        deviations=deviations,
        verification=verification,
        last_event_id=last_event_id,
    )


def cancel(storm_id: int) -> dict[str, Any]:
    """Ask a storm to stop. A running one stops between steps; a queued one ends.

    Between steps, not during one: a tool call is a function call and this
    process cannot interrupt one. The same honest limit as `step_timeout`, and
    the same answer - anything that must be interruptible mid-flight is a
    process, and a process goes through `app/runner.py`.
    """
    storm = attach(storm_id)
    with _GUARD:
        _CANCELLED.add(int(storm_id))
        live = int(storm_id) in _LIVE
    if live:
        return {"storm": int(storm_id), "state": storm.state, "stopping": True}
    row = events.append(
        FINISHED,
        {
            "storm": int(storm_id),
            "state": "cancelled",
            "because": "you cancelled it",
            "verification": None,
        },
        thread_id=storm.thread_id,
    )
    with _GUARD:
        _CANCELLED.discard(int(storm_id))
    return {"storm": int(storm_id), "state": "cancelled", "stopping": False,
            "event": row["id"]}


# ---------------------------------------------------------------------------
# Running.


def run(
    storm_id: int,
    *,
    plan: Any = None,
    registry: Any = None,
    restart_stalled: Sequence[str] = (),
    workers: int = DEFAULT_WORKERS,
    step_timeout: float = DEFAULT_STEP_TIMEOUT,
) -> Iterator[dict[str, Any]]:
    """Run an approved storm, yielding every event it writes, in order.

    A generator for the reason `app/conductor.py` is one: the caller streams what
    `events.append` gave back, so nothing is ever streamed that was not first
    durably written, and a client that reconnects asks for everything after the
    last id it saw.

    Before anything runs, the contract is checked three ways and any one of them
    stops the storm rather than improvising:

    1. `plan`, if the caller supplied one, must be the approved plan.
    2. No tool a step names may have changed since approval (`Manifest.drift`).
    3. No step may be stalled, unless the person named it in `restart_stalled`
       having been told what re-running it might repeat.

    Steps in the same wave run at once on daemon threads; a wave does not start
    until the one before it is finished. A step whose dependency failed does not
    run, and says which one.
    """
    thread_id, manifest = load(storm_id)
    registry = _registry(registry)
    storm = attach(storm_id)

    outbox: "queue.Queue[dict[str, Any]]" = queue.Queue()

    def emit(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = events.append(
            kind, {"storm": int(storm_id), **payload}, thread_id=thread_id
        )
        outbox.put(row)
        return row

    def refuse(detail: str, deviations: Sequence[str]) -> Iterator[dict[str, Any]]:
        emit(
            REFUSED,
            {
                "state": "waiting_approval",
                "detail": detail,
                "deviations": list(deviations),
                "what_now": (
                    "Nothing was run. What was approved is what runs, so a plan "
                    "that is not the approved one stops here and asks rather than "
                    "improvising. Look at what changed, and approve it again if it "
                    "is what you want."
                ),
            },
        )
        while not outbox.empty():
            yield outbox.get()

    if storm.state in ("done", "failed", "cancelled"):
        raise StormError(
            f"storm {storm_id} already finished as {storm.state!r}. A finished "
            "storm is a record, not something to run again."
        )

    # Checked twice on purpose. Here, so an obviously-doubled run fails before a
    # single event is written; and again as one atomic claim below, because a
    # check and a set in two different lock acquisitions is not a claim at all -
    # two callers can both pass the check before either takes the slot.
    if _is_live(storm_id):
        raise StormError(_ALREADY_RUNNING.format(storm=storm_id))

    if plan is not None:
        deviations = manifest.deviations_from(plan)
        if deviations:
            yield from refuse(
                "the plan handed to this storm is not the plan that was approved",
                deviations,
            )
            return

    drift = manifest.drift(registry)
    if drift:
        yield from refuse("something this plan depends on changed since you approved it", drift)
        return

    asked_for = {str(name) for name in restart_stalled}
    unresolved = [name for name in storm.stalled if name not in asked_for]
    if unresolved:
        emit(
            ASKED,
            {
                "state": "waiting_input",
                "stalled": list(unresolved),
                "detail": (
                    "the engine stopped while "
                    + ", ".join(repr(name) for name in unresolved)
                    + " was running. Whether it finished its work is not knowable "
                    "from here."
                ),
                "what_now": (
                    "Nothing was restarted. Re-running a step repeats whatever it "
                    "had already done, which for a step that writes is not free. "
                    "Say which of these to run again and the storm carries on from "
                    "there."
                ),
            },
        )
        while not outbox.empty():
            yield outbox.get()
        return

    with _GUARD:
        if int(storm_id) in _LIVE:
            raise StormError(_ALREADY_RUNNING.format(storm=storm_id))
        _LIVE[int(storm_id)] = time.monotonic()
        _CANCELLED.discard(int(storm_id))
    try:
        yield from _drive(
            storm_id=int(storm_id),
            thread_id=thread_id,
            manifest=manifest,
            storm=storm,
            registry=registry,
            emit=emit,
            outbox=outbox,
            restart=asked_for,
            workers=max(1, int(workers)),
            step_timeout=float(step_timeout),
        )
    finally:
        with _GUARD:
            _LIVE.pop(int(storm_id), None)
            _CANCELLED.discard(int(storm_id))


def _drive(
    *,
    storm_id: int,
    thread_id: int,
    manifest: Manifest,
    storm: Storm,
    registry: Any,
    emit: Any,
    outbox: "queue.Queue[dict[str, Any]]",
    restart: set[str],
    workers: int,
    step_timeout: float,
) -> Iterator[dict[str, Any]]:
    """The wave loop. Everything here has already passed the contract check."""
    # WHAT A RESUME SKIPS, AND WHY IT IS ONLY THIS. A step that finished and
    # verified is done and is never run twice - that is what `already` is. A
    # step that failed is a step that RAN and said so, and re-attempting it is a
    # retry rather than a repeat of something invisible. A step that was
    # interrupted is neither: nobody can say what it did, which is why `run()`
    # will not reach here at all until the person has answered for it.
    #
    # `failed` starts empty rather than seeded from the log for the same reason:
    # seeding it would skip the dependents of a step this run is about to try
    # again, deciding against a step before it had its second attempt.
    done: dict[str, dict[str, Any]] = dict(storm.produced)
    failed: set[str] = set()
    already = set(done)
    last_result: Any = None

    emit(
        STARTED,
        {
            "state": "running",
            "resumed": bool(already),
            "already_done": sorted(already),
            "waves": [list(wave) for wave in manifest.waves],
        },
    )
    while not outbox.empty():
        yield outbox.get()

    cancelled = False
    for wave in manifest.waves:
        if _stop_requested(storm_id):
            cancelled = True
            break
        ready: list[StepContract] = []
        for name in wave:
            step = manifest.step(name)
            if name in already:
                continue
            blocked = sorted(set(step.needs) & failed)
            if blocked:
                emit(
                    STEP_SKIPPED,
                    {
                        "step": name,
                        "tool": step.tool,
                        "state": "cancelled",
                        "ok": False,
                        "because": (
                            f"{', '.join(repr(item) for item in blocked)} did not "
                            "work, and this step needs it"
                        ),
                    },
                )
                failed.add(name)
                continue
            ready.append(step)
        while not outbox.empty():
            yield outbox.get()
        if not ready:
            continue

        results: "queue.Queue[tuple[str, dict[str, Any]]]" = queue.Queue()
        running: set[str] = set()
        pool = list(ready)
        while pool or running:
            while pool and len(running) < workers:
                step = pool.pop(0)
                running.add(step.id)
                thread = threading.Thread(
                    target=_execute,
                    kwargs={
                        "storm_id": storm_id,
                        "thread_id": thread_id,
                        "manifest": manifest,
                        "step": step,
                        "produced": dict(done),
                        "registry": registry,
                        "emit": emit,
                        "results": results,
                    },
                    daemon=True,
                    name=f"storm{storm_id}-{step.id}",
                )
                thread.start()
            deadline = time.monotonic() + step_timeout
            while running:
                while not outbox.empty():
                    yield outbox.get()
                try:
                    name, outcome = results.get(timeout=0.05)
                except queue.Empty:
                    if time.monotonic() > deadline:
                        break
                    continue
                running.discard(name)
                if outcome["state"] == "done":
                    done[name] = dict(outcome.get("outputs") or {})
                    last_result = outcome.get("result")
                else:
                    failed.add(name)
                if pool:
                    break
            if running and time.monotonic() > deadline:
                for name in sorted(running):
                    emit(
                        STEP_FINISHED,
                        {
                            "step": name,
                            "tool": manifest.step(name).tool,
                            "state": "stalled",
                            "ok": False,
                            "because": (
                                f"the storm stopped waiting after {step_timeout:g} "
                                "seconds. The call may still be running in this "
                                "process: a tool call is a function call and a "
                                "thread cannot be killed from outside, so nothing "
                                "claims it was stopped."
                            ),
                            "result": None,
                            "verification": None,
                            "outputs": {},
                        },
                    )
                    failed.add(name)
                running.clear()
                pool.clear()
        while not outbox.empty():
            yield outbox.get()

    if cancelled or _stop_requested(storm_id):
        emit(
            FINISHED,
            {
                "state": "cancelled",
                "because": "you cancelled it between steps",
                "verification": None,
            },
        )
        while not outbox.empty():
            yield outbox.get()
        return

    verification = _verify_the_build(
        manifest, done=done, last_result=last_result, thread_id=thread_id,
        registry=registry,
    )
    ran_everything = not failed
    emit(
        FINISHED,
        {
            "state": "done" if (ran_everything and verification.ok) else "failed",
            "ok": bool(ran_everything and verification.ok),
            "because": verification.because,
            "failed_steps": sorted(failed),
            "verification": verification.as_dict(),
            "outputs": done,
        },
    )
    while not outbox.empty():
        yield outbox.get()

    events.add_message(
        thread_id,
        "assistant",
        f"Storm {storm_id} finished: "
        + ("it worked. " if (ran_everything and verification.ok) else "it did not. ")
        + f"Stated before it ran: {verification.stated} - {verification.because}",
    )


def _stop_requested(storm_id: int) -> bool:
    with _GUARD:
        return int(storm_id) in _CANCELLED


def _is_live(storm_id: int) -> bool:
    with _GUARD:
        return int(storm_id) in _LIVE


def _execute(
    *,
    storm_id: int,
    thread_id: int,
    manifest: Manifest,
    step: StepContract,
    produced: Mapping[str, Mapping[str, Any]],
    registry: Any,
    emit: Any,
    results: "queue.Queue[tuple[str, dict[str, Any]]]",
) -> None:
    """One step, on its own thread. Every exit from here reports an outcome.

    Every exit, including the ones nobody thought of: a step that ended without
    putting something on `results` would hang the wave that is waiting for it,
    so the whole body is inside a `try` whose `finally` is the only place that
    reports. That is the same shape as the conductor's single exit funnel, for
    the same reason - a turn, or a step, may never end in silence.
    """
    outcome: dict[str, Any] = {
        "state": "failed",
        "ok": False,
        "because": "the step ended without saying what happened",
        "result": None,
        "verification": None,
        "outputs": {},
    }
    try:
        emit(
            STEP_STARTED,
            {
                "step": step.id,
                "tool": step.tool,
                "why": step.why,
                "state": "running",
                "exit_criterion": dict(step.exit_criterion),
            },
        )

        # THE CONTRACT, ONE LAST TIME, IMMEDIATELY BEFORE THE CALL. The whole
        # manifest was checked before the run began; this is the step that is
        # about to happen being the step that was approved, checked at the
        # moment it matters rather than at the moment the run started.
        if step.contract and step.recomputed() != step.contract:
            outcome["because"] = (
                f"step {step.id!r} is not the step that was approved and was not "
                "run"
            )
            return
        spec = registry.get(step.tool)
        if spec is None or tool_fingerprint(spec) != step.tool_contract:
            outcome["because"] = (
                f"the tool {step.tool!r} is not the tool that was approved, so "
                f"{step.id!r} was not run"
            )
            return

        arguments = step.bind(produced)

        from app.tools import evidence
        from app.tools.registry import ApprovalRequired, ToolError

        try:
            result = registry.call(
                step.tool,
                arguments,
                # The person approved this build, and the build listed exactly
                # which of its steps need a permission each time. A step outside
                # that list gets no approval from here.
                approved=step.id in manifest.needs_approval,
                # THE STORM IS THE HARNESS'S OWN FIXED SCRIPT, which is what
                # `evidence.HARNESS` means, and a value it supplies is worth
                # ASSERTED. Not `user`: a person approving a plan is not the
                # same act as a person stating a number, and reading it as one
                # would let an approval open a gate. Not `model` either, because
                # no model is calling. The conservative reading is also the true
                # one here, which is a rare piece of luck.
                actor=evidence.HARNESS,
                thread_id=thread_id,
            )
            ok = not (isinstance(result, Mapping) and result.get("ok") is False)
        except ApprovalRequired as error:
            result = {
                "ok": False,
                "error": "approval_required",
                "detail": str(error),
            }
            ok = False
        except ToolError as error:
            result = {"ok": False, "error": "no_such_tool", "detail": str(error)}
            ok = False
        except Exception as error:  # noqa: BLE001 - a tool fault is not a lost storm
            result = {
                "ok": False,
                "error": "tool_failed",
                "detail": f"{type(error).__name__}: {error}",
            }
            ok = False

        outcome["result"] = result
        if not ok:
            outcome["because"] = (
                f"{step.tool} did not succeed: "
                f"{(result or {}).get('detail') or (result or {}).get('error')}"
            )
            return

        try:
            outputs = step.harvest(result if isinstance(result, Mapping) else {})
        except StormRefused as error:
            outcome["because"] = error.detail
            return
        outcome["outputs"] = outputs

        # A STEP THAT CANNOT SHOW IT WORKED DID NOT WORK, and the criterion is
        # the one the build stated before it ran rather than a looser one
        # chosen now.
        observed = _observe(
            step.exit_criterion.get("source"),
            result=result,
            outputs=outputs,
            thread_id=thread_id,
            registry=registry,
        )
        verification = step.criterion().met(observed)
        outcome["verification"] = verification.as_dict()
        outcome["ok"] = bool(verification.ok)
        outcome["state"] = "done" if verification.ok else "failed"
        outcome["because"] = verification.because
    except StormRefused as error:  # a refusal raised out of bind()
        outcome["because"] = error.detail
    except Exception as error:  # noqa: BLE001 - the step must always report
        outcome["because"] = f"{type(error).__name__}: {error}"
    finally:
        emit(
            STEP_FINISHED,
            {
                "step": step.id,
                "tool": step.tool,
                "state": outcome["state"],
                "ok": outcome["ok"],
                "because": outcome["because"],
                "result": outcome["result"],
                "verification": outcome["verification"],
                "outputs": outcome["outputs"],
            },
        )
        results.put((step.id, outcome))


def _observe(
    source: Any,
    *,
    result: Any = None,
    outputs: Mapping[str, Any] | None = None,
    produced: Mapping[str, Mapping[str, Any]] | None = None,
    thread_id: int | None = None,
    registry: Any = None,
) -> Mapping[str, Any] | None:
    """The observation an exit criterion asked for, and only that one.

    `app/build.py` says `source` exists so the executor is told WHICH observation
    to make. Being told is worth nothing if the executor then looks wherever is
    convenient, so this makes exactly the named one:

    - `tool_result` - what the tool returned.
    - `outputs` - the outputs the step declared it produces, or, for a whole
      build, `{step: {output: value}}`.
    - `diagnosis` - the tree walked again. A step whose own result IS a diagnosis
      is its own observation (`run_diagnosis` stamps `decided_by`), and anything
      else gets a fresh one, which is what "a fresh diagnosis" means.
    """
    name = str(source or "")
    if name == "tool_result":
        return result if isinstance(result, Mapping) else None
    if name == "outputs":
        if produced is not None:
            return dict(produced)
        return dict(outputs or {})
    if name == "diagnosis":
        if isinstance(result, Mapping) and result.get("decided_by") == "app/diagnosis.py":
            return result
        return _fresh_diagnosis(thread_id, registry)
    return None


def _fresh_diagnosis(thread_id: int | None, registry: Any = None) -> Mapping[str, Any] | None:
    """Walk the tree again over whatever the ledger holds now.

    No facts are supplied. That is the point: a verification that handed the
    engine a sheet of facts would be verifying its own arithmetic. What opens a
    gate here is what tools measured in this thread, which is exactly what the
    steps have just been doing.
    """
    from app.tools import evidence

    registry = _registry(registry)
    try:
        answer = registry.call(
            "run_diagnosis",
            {"facts": {}},
            actor=evidence.HARNESS,
            thread_id=thread_id,
        )
    except Exception:  # noqa: BLE001 - an unverifiable step is a failed step
        return None
    return answer if isinstance(answer, Mapping) else None


def _verify_the_build(
    manifest: Manifest,
    *,
    done: Mapping[str, Mapping[str, Any]],
    last_result: Any,
    thread_id: int,
    registry: Any,
) -> Verification:
    """Did the whole build do what it said it would, by its own stated measure."""
    try:
        criterion = ExitCriterion(**dict(manifest.exit_criterion))
    except Exception as error:  # noqa: BLE001 - a build with no criterion cannot pass
        return Verification(
            ok=False,
            stated=str(manifest.exit_criterion.get("stated") or ""),
            saw=None,
            because=f"the build's exit criterion could not be read: {error}",
        )
    observed = _observe(
        criterion.source,
        result=last_result,
        produced=done,
        thread_id=thread_id,
        registry=registry,
    )
    return criterion.met(observed)


# ---------------------------------------------------------------------------
# Running one in the background, so nothing blocks the conversation.


def start(
    storm_id: int,
    *,
    restart_stalled: Sequence[str] = (),
    workers: int = DEFAULT_WORKERS,
    step_timeout: float = DEFAULT_STEP_TIMEOUT,
) -> threading.Thread:
    """Run a storm on a daemon thread and return it.

    `docs/THE_PROPOSAL_LOOP.md`: *nothing blocks the conversation: the user can
    ask what is happening and get an answer while it happens.* That is this
    function - the request that starts a storm returns immediately, the events go
    to the thread as they are committed, and the turn endpoint is free the whole
    time.

    Nothing is yielded to anybody here, and nothing needs to be: the generator's
    events are already in the log before they reach it, so draining it into
    nowhere loses exactly nothing. A reader attaches to `GET /api/events` and
    gets the same frames with the same ids.
    """

    def drain() -> None:
        try:
            for _ in run(
                storm_id,
                restart_stalled=restart_stalled,
                workers=workers,
                step_timeout=step_timeout,
            ):
                pass
        except StormError as error:
            # A storm that cannot start says so in its own log rather than in a
            # traceback nobody is attached to.
            try:
                thread_id, _ = load(storm_id)
                events.append(
                    REFUSED,
                    {
                        "storm": int(storm_id),
                        "state": "waiting_approval",
                        "detail": str(error),
                        "deviations": list(getattr(error, "deviations", ())),
                    },
                    thread_id=thread_id,
                )
            except Exception:  # noqa: BLE001 - the log is gone; nothing else to do
                pass

    thread = threading.Thread(target=drain, daemon=True, name=f"storm{storm_id}")
    thread.start()
    return thread


__all__ = [
    "ASKED",
    "DECLARED",
    "DEFAULT_STEP_TIMEOUT",
    "DEFAULT_WORKERS",
    "FINISHED",
    "KINDS",
    "Manifest",
    "REFUSED",
    "STARTED",
    "STEP_FINISHED",
    "STEP_SKIPPED",
    "STEP_STARTED",
    "StepContract",
    "StepState",
    "Storm",
    "StormError",
    "StormRefused",
    "attach",
    "cancel",
    "declare",
    "list_for_thread",
    "load",
    "run",
    "start",
    "tool_fingerprint",
]
