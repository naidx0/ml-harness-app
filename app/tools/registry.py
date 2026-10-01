"""One declaration, two callers: the model's tool call and the user's button.

VISION.md says *every tool is also a control*, and that sentence is load-bearing
rather than decorative. It is what keeps the product usable when the connected
model cannot call tools - the buttons are all still there - and it is what makes
a session reproducible instead of a story about what an AI once did. A registry
that only emits JSON schemas would deliver half of that and quietly make the
other half somebody's later problem.

So a `ToolSpec` carries both faces at once:

- the **model face** - name, description, JSON Schema - via `model_tools()`
- the **control face** - label, group, verb, argument fields - via `controls()`

They cannot drift, because there is one declaration. Adding a tool adds a
button. Changing a parameter changes the form. That is the whole design, and
the next phase (the React chat surface) reads `controls()` directly.

`reads` and `writes` are not documentation. They are what lets the transcript
collapse a turn into a summary without losing what it touched, and they are
what the approval system in `ARCHITECTURE.md` §8 keys on.

## THE HARD RULE

**No tool a model can call may set a gate outcome.** Not "no tool does today" -
no tool *can*, structurally, and a future agent who tries gets a red suite
rather than a merged change.

Three walls, and each one alone would be enough to be worth having:

1. **A tool may not declare a reserved write.** `gate`, `gate_ledger`,
   `verdict`, `outcome`, `diagnosis` are refused at registration. A tool that
   claims the authority does not get registered.
2. **A tool's schema may not accept a reserved argument.** There is no
   parameter named `gate`, `gates_passed`, `verdict` or `outcome` on any tool,
   so a model has no slot to put a decision in even if it wanted one.
3. **The one tool that produces a verdict computes it.** `run_diagnosis` takes
   *facts* and hands them to `app/diagnosis.py`, which walks the tree itself.
   The model's arguments never reach an outcome; `diagnosis.validate_facts`
   independently rejects any key that is not a declared fact, and gate ids are
   not facts.

That last one is the reason the split matters more than it looks. The user's
model may FILL facts. It may NEVER DECIDE a gate. A model that wants to be
helpful will agree that you should fine-tune, every single time, and the entire
value of this product is the answer that says no.

## THE SECOND HARD RULE: A MODEL MAY FILL FACTS. IT MAY NOT VALUE THEM.

The three walls above proved a model cannot decide a gate. They said nothing
about whether passing a gate MEANT anything, and it did not: a model that simply
asserted `eval_size_n` and `baseline_measured` got all five gates green, because
nothing tracked where a fact came from. `app/diagnosis.py` now refuses to open a
gate on an inadmissibly-originated fact. Two more walls here are what make that
refusal reach the tool surface.

4. **A tool's schema may not accept an argument that names a provenance.**
   `origin`, `origins`, `provenance`, `measured`, `evidence`, `instrument`,
   `actor`, `thread_id` are refused at registration alongside the gate words. A
   model has no slot in which to say how much its own number is worth, and
   `Registry.call` reports any it tried to send as `refused_arguments` so the
   attempt is visible in the transcript rather than silently dropped.

5. **Only a tool that DECLARED a fact may stamp it MEASURED, and `measures=` is
   checked against the fact ledger.** The name must be a declared fact and its
   `source:` must admit MEASURED, so `measures=("prompt_iterations",)` - a fact
   about the user's own week, which no instrument can read - is refused at
   import. The stamp itself is written through `evidence.Instrument`, which the
   registry hands the handler as a keyword argument. A minting handler's
   arguments arrive MARKED as the caller's, and `Instrument.measured` refuses a
   marked value or anything derived from one - so the question the wall asks is
   where a number came from and not what it happens to equal.

The actor is the other half. `call(..., actor=...)` is set by the call SITE -
the conductor passes `model`, the control route passes `user` - and it decides
what a supplied value is worth. It is not an argument, it is not in any schema,
and wall 4 stops one from ever appearing.

## WALL 6: A TOOL SAYS WHICH OF ITS ARGUMENTS COULD NEVER BE THE ANSWER

`app/tools/evidence.py` refuses to stamp a value that is, strictly by type, a
number the caller sent. That check is what catches an identity-preserving
rebuild - `operator.index(n)`, `n.numerator`, `json.loads(json.dumps(n))`, a
file written with `n` lines and then counted - none of which touches a marked
object on the way, so none of which the mark can see.

It has one honest false refusal, and it was live and user-facing for a whole
commit: `profile_dataset` counting a 120-row eval file with `max_rows=120`
counted 120 honestly and was refused, because the count equalled an argument.
The number cannot decide that case. **`120` sent as a cap and `120` counted off
a disk are the same number of the same type in the same process**, and CPython
interns the small ones, so not even object identity separates them.

What separates them is a statement about the ARGUMENT: *this one bounds the
work, it does not answer the question*. That is a property of the tool, not of
the value, so it is declared on the tool:

    @tool("profile_dataset", ..., measures=("eval_size_n",), bounds=("max_rows",))

`bounds=` sits beside `measures=` on purpose. `measures=` is the tool saying
what it may stamp; `bounds=` is the tool saying which of its inputs cannot be
what it stamps. Both are read at registration, by a reviewer, in one place -
and `_validate` refuses a bound that is not a real argument and a bound on a
tool that measures nothing, so the declaration cannot become decoration.

THE DEFAULT IS STRICT AND THE RELAXATION HAS TO BE TYPED. A tool that declares
no bounds has every argument quarantined, which is why the twenty-nine routes in
`tests/test_laundering_routes.py` - none of which declares anything - are shut.
A tool CAN still stamp its own declared bound back, and nothing here can stop
it: that is wall 1's answer, a dishonest source, visible at registration. The
declaration moves the question from "what does this number equal" to "is this
tool's source honest", which is a question a person can actually answer.

## WALL 7: A TOOL SAYS WHICH BLOCK IT IS IN, AND IN THE ENGINE'S WORDS

All forty tools reached the model on every turn, of every thread, for every
model, forever - 9,815 tokens of schema a turn whether or not one of them had
anything to do with what the person asked. `provides=` is the third declaration
in this row and it sits beside the other two on purpose:

    @tool("carve_eval_set", ..., measures=("eval_size_n",),
          provides=("data.eval_set.carve",))

`measures=` says what a tool may stamp. `bounds=` says which of its inputs
could never be what it stamps. `provides=` says what it is FOR, in a closed
vocabulary `app/tools/blocks.py` publishes - and the first dotted segment IS
the capability block, so declaring the capability is declaring the membership
and there is no manifest anywhere to keep in step. Checked at registration
against that vocabulary, so a misspelling is a red import rather than a pack
nobody can ask for.

**THE MODEL FACE IS SCOPED AND THE CONTROL FACE IS NOT.** `model_tools(only=)`
narrows what the model may call; `controls()` has no such parameter and never
gets one. A pack that is not loaded is a tool the model will not reach for, and
never a tool the person cannot run.

## WALL 8: A TOOL WORKS IN THE DOMAIN ITS CONVERSATION IS IN, OR SAYS IT CANNOT

Everything above assumes one ledger, and for the whole of this product's life
there was one. `docs/CAPABILITY_BLOCKS.md` measured what a second one costs:
thirty-three sites across fifteen modules resolve *the ledger* to the first
one unconditionally - **including `_validate` below**, which asked
`evidence.may_be_declared_measurable` about a fact the second ledger declares
and refused a perfectly honest tool at import, with a message that was right at
every step and consulted the wrong file at every step.

Two questions were being asked with one function, and they have different
answers:

* **May this tool DECLARE `measures=(name,)`?** Asked at import, where there is
  no conversation and so no domain, against the union of every ledger this
  build ships (`evidence.declarable_in_any_ledger`). This is what makes the
  four tools `docs/PHASES.md` names for the AI-engineering ledger writable at
  all.
* **May this call STAMP it?** Asked here, per call, against
  `evidence.ledger_for_thread(thread_id)` - the ledger the conversation says it
  is running. A tool whose every measurable fact is foreign to that ledger has
  no instrument in this domain and `call` refuses before the handler runs,
  naming the ledger it read and the ledgers that do declare the fact. A tool
  that measures a mix gets the narrower refusal, inside `Instrument.measured`,
  on the one fact.

**Silence is the failure, not refusal.** Reading the wrong ledger to look busy
returns a number about a question nobody asked, and there is no error to notice.

The ledger reaches a handler on a SECOND INJECTION CHANNEL beside `instrument`,
not as a field on it: `Instrument`'s docstring says it carries no way to read
the fact ledger, deliberately, and two channels with two walls is cheaper than
one channel with a caveat. `ledger` is a reserved argument name for the same
reason `origin` is - a model that could name its own ledger could choose the
domain whose gates it finds easiest.
"""

from __future__ import annotations

import inspect
import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator

from app import diagnosis
from app import events
from app.tools import blocks, evidence


NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,47}$")

#: A tool may not claim to write any of these. See THE HARD RULE.
RESERVED_WRITES = frozenset(
    {"gate", "gates", "gate_ledger", "verdict", "outcome", "diagnosis"}
)

#: A tool's schema may not accept a parameter with any of these names, in any
#: casing. The model needs no slot in which to hand us a decision, and - the
#: second half, added with fact origins - no slot in which to tell us what its
#: own numbers are worth. The spec warns about exactly this in
#: `fact_origins.the_origin_is_never_supplied_by_the_thing_being_checked`:
#: "if a future tool schema ever grows an `origins` argument a model can fill,
#: this whole block becomes decoration on that day". This is the day not
#: arriving.
RESERVED_ARGUMENTS = frozenset(
    {
        "gate",
        "gates",
        "gate_ledger",
        "gates_passed",
        "gate_outcome",
        "verdict",
        "outcome",
        "diagnosis",
        # Provenance. A value's origin is decided by what produced it and by
        # who is calling, never by what the caller typed.
        "origin",
        "origins",
        "provenance",
        "measured",
        "fact_origins",
        "evidence",
        "instrument",
        "actor",
        # WHICH LEDGER A THREAD RUNS IS A PROPERTY OF THE CONVERSATION, NOT AN
        # ARGUMENT. A model that could name its own ledger could pick the
        # domain whose gates it finds easiest, which is wall 1 with a new
        # spelling: the model may fill facts, it may not choose the knowledge
        # those facts are judged against. It arrives by injection, from
        # `threads.ledger`, set where the thread was created.
        "ledger",
    }
)
# `thread_id` is deliberately NOT on that list. `start_training` takes one and
# is right to: which conversation a run belongs to is a fact about the request.
# The thread the EVIDENCE is scoped to arrives on a different channel entirely -
# `Registry.call(thread_id=...)`, set by the call site - so a tool argument by
# that name cannot reach it and does not need to be banned.

#: Keyword arguments the registry itself injects into a handler. They are named
#: here so nothing can declare them in a schema and so `call` can tell an
#: injected parameter from a caller-supplied one.
#:
#: `ledger` IS THE SECOND CHANNEL AND IT IS SEPARATE FROM THE FIRST ON PURPOSE.
#: `Instrument`'s own docstring says it carries no way to READ the fact ledger,
#: on purpose - see wall 3 - so hanging a `Spec` on it would blur a line
#: somebody drew deliberately, and the blur would be found later by an adversary
#: rather than now by a reader. Two channels, two names, two walls.
INJECTED_ARGUMENTS = frozenset({"instrument", "ledger"})

#: Tools whose only argument is a `facts` object, for which a name sent at the
#: top level is read as a fact rather than dropped. See `Registry.call`.
FOLD_TOP_LEVEL_INTO_FACTS = frozenset({"state_facts"})

#: The argument names that hold a location on disk, across the registry —
#: the names the playbook's own `args_hint`s use. Named explicitly rather
#: than sniffed from descriptions, because a rewrite that guesses which
#: arguments are paths is a rewrite that one day rewrites a model name.
WORKSPACE_PATH_ARGUMENTS = frozenset(
    {"path", "root", "into", "train", "eval", "corpus", "data", "eval_path", "train_path", "dataset_path"}
)

#: The names a path argument takes when it is not one of the exact names above.
#: Found by review (2026-09-01): the workspace note PROMISED that relative
#: paths resolve against the project folder, and the fixed set missed most
#: `*_path` / `*_dir` arguments — a promise the door did not keep is worse
#: than no promise. A name is a path when it ends in one of these words.
_PATH_NAME = re.compile(r"(^|_)(path|dir|directory|folder|file|root)s?$")


def _names_a_path(key: str) -> bool:
    return key in WORKSPACE_PATH_ARGUMENTS or bool(_PATH_NAME.search(key))


#: Suffixes worth naming back when a path argument is missing. Data files and
#: the folders that hold them; not source, not logs.
_PATHS_WORTH_NAMING = (".jsonl", ".ndjson", ".csv", ".tsv", ".json", ".parquet")

#: How many to print. Enough to choose from, short enough not to become the
#: reply; `files_here_count` carries the real number.
_NAME_AT_MOST = 20

#: Directories that hold the machine's bookkeeping rather than anybody's data.
_NOT_SOMEBODYS_DATA = frozenset(
    {"node_modules", "__pycache__", "target", "dist", "build", "venv", ".venv"}
)

#: Words in a file NAME that say it is part of a dataset. Ranking only - a file
#: without one of them is still listed, just after the ones with them.
_NAMES_OF_A_SPLIT = ("eval", "train", "valid", "test", "split", "holdout", "data")


def _files_for_a_missing_path(
    missing: list[str], thread_id: int | None
) -> dict[str, Any]:
    """Candidate files for a missing path argument, or {} when there is none.

    Only when one of the missing arguments NAMES a path (`_names_a_path`, the
    same test the workspace rehoming uses) and the thread's project sits on a
    folder. Matched on suffix and sorted by depth then name, so the splits a
    dataset keeps two folders down are not buried under its prose.
    """
    if thread_id is None:
        return {}
    wanted = [name for name in missing if _names_a_path(name)]
    if not wanted:
        return {}
    try:
        from app import db, events as _events

        thread = _events.get_thread(int(thread_id))
        project_id = (thread or {}).get("project_id")
        project = db.get_project(int(project_id)) if project_id else None
        root = (project or {}).get("root_path")
    except Exception:  # noqa: BLE001 - a lookup must never break a refusal
        return {}
    if not root or not os.path.isdir(root):
        return {}
    base = Path(str(root))
    found: list[str] = []
    try:
        for candidate in sorted(base.rglob("*")):
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() not in _PATHS_WORTH_NAMING:
                continue
            parts = candidate.relative_to(base).parts
            # A LIST NOBODY CAN ACT ON IS NOT AN ANSWER. Sorted by depth alone,
            # his project answered `engine.json`, `.hub-cache/40372dee….json`
            # and `.claude/launch.json` before anything he owns. Hidden
            # directories and build output are the machine's bookkeeping, not
            # the person's data.
            if any(one.startswith(".") for one in parts[:-1]):
                continue
            if any(one in _NOT_SOMEBODYS_DATA for one in parts[:-1]):
                continue
            found.append("/".join(parts))
    except OSError:
        return {}
    if not found:
        return {}
    # A split before a schema before a cache: the name is the only evidence
    # available without opening anything, so the name is what ranks them.
    def _rank(one: str) -> tuple[int, int, str]:
        leaf = one.rsplit("/", 1)[-1].lower()
        named = 0 if any(word in leaf for word in _NAMES_OF_A_SPLIT) else 1
        return (named, one.count("/"), one)

    found.sort(key=_rank)
    return {
        "for_" + wanted[0]: found[:_NAME_AT_MOST],
        "files_here_count": len(found),
        "files_here_are_relative_to": str(base),
        "how_to_choose": (
            f"{wanted[0]} takes one of those, relative to the project folder. "
            "They are file NAMES read off the disk - nothing in them was "
            "opened - so check it is the one you mean before you use it."
        ),
    }


def _rehome_workspace_paths(
    accepted: dict[str, Any], thread_id: int | None
) -> dict[str, dict[str, str]]:
    """Resolve relative path arguments against the thread's workspace folder.

    Mutates `accepted` in place and returns `{argument: {from, to}}` for the
    result to report. Empty — and the arguments untouched — when the thread
    has no project, the project has no folder, or every path is absolute.
    """
    if thread_id is None:
        return {}
    try:
        from app import db, events as _events

        thread = _events.get_thread(int(thread_id))
        project_id = (thread or {}).get("project_id")
        project = db.get_project(int(project_id)) if project_id else None
        root = (project or {}).get("root_path")
    except Exception:  # noqa: BLE001 - a broken lookup must not break the call
        return {}
    if not root or not os.path.isdir(root):
        return {}
    moved: dict[str, dict[str, str]] = {}
    for key, value in list(accepted.items()):
        if not _names_a_path(key):
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        expanded = os.path.expanduser(value)
        # Absolute, or drive-relative on Windows ('C:data.jsonl' names a
        # place relative to that drive's own cwd, not to this folder): pass
        # through untouched and UNREPORTED — reporting it as 'resolved against
        # the workspace' would be a rewrite that did not happen.
        if os.path.isabs(expanded) or os.path.splitdrive(expanded)[0]:
            continue
        resolved = os.path.normpath(os.path.join(root, value))
        accepted[key] = resolved
        moved[key] = {"from": value, "to": resolved}
        # '..' resolves against the workspace too - and leaves it. That is
        # allowed (a person may mean the folder next door) but it must be
        # SAID, or the report reads as "inside your project" when it is not.
        try:
            inside = os.path.commonpath(
                [os.path.realpath(resolved), os.path.realpath(root)]
            ) == os.path.realpath(root)
        except ValueError:
            inside = False
        if not inside:
            moved[key]["outside_workspace"] = True
    return moved


def _resolve_missing_reads(
    spec: "ToolSpec", accepted: dict[str, Any], thread_id: int | None
) -> dict[str, dict[str, Any]]:
    """A read-only tool's missing path that plainly means one workspace file.

    H-path-e (2026-09-25): read_context_file refused 162 of 200 journey calls,
    130 `not_found`, because a small model drops `ml-principles-dataset/` or
    guesses the wrong folder. Only for tools that write nothing: a write is
    never redirected. Mutates `accepted` for a resolved path and returns
    `{argument: {from, to, by}}`, or `{argument: {from, candidates}}` when
    two or more files fit, for the result to report.
    """
    if os.environ.get("MLH_PATH_RESOLVE") != "1":
        # Opt-in until its journey A/B is scored (log: H-path-e).
        return {}
    if spec.writes or thread_id is None:
        return {}
    try:
        from app import db, events as _events

        thread = _events.get_thread(int(thread_id))
        project_id = (thread or {}).get("project_id")
        project = db.get_project(int(project_id)) if project_id else None
        root = (project or {}).get("root_path")
    except Exception:  # noqa: BLE001 - a broken lookup must not break the call
        return {}
    if not root or not os.path.isdir(root):
        return {}
    from app.tools.path_resolve import resolve_missing

    found: dict[str, dict[str, Any]] = {}
    for key, value in list(accepted.items()):
        if not _names_a_path(key) or not isinstance(value, str) or not value.strip():
            continue
        if os.path.exists(os.path.expanduser(value)):
            continue
        out = resolve_missing(value, root)
        if out["status"] == "resolved":
            accepted[key] = out["to"]
            found[key] = {"from": value, "to": out["to"], "by": out["by"]}
        elif out["status"] == "ambiguous":
            found[key] = {"from": value, "candidates": out["candidates"]}
    return found


#: `never` - run it when asked. `always` - a recorded approval row first.
APPROVALS = ("never", "always")


class ToolError(ValueError):
    """A tool declaration that must not be registered."""


class ApprovalRequired(PermissionError):
    """A tool marked `approval="always"` was called without one."""


@dataclass(frozen=True)
class Control:
    """The same tool, described for a person rather than a model.

    `label` is what the button says. `verb` is what it does, in the imperative,
    for a confirmation line. `group` is which panel it belongs in.
    """

    label: str
    group: str
    verb: str
    order: int = 100


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    schema: dict[str, Any]
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    approval: str
    control: Control
    handler: Callable[..., Any] = field(repr=False)
    #: The ledger facts this tool may stamp MEASURED. Empty for every tool that
    #: does not run an instrument, which is most of them. Checked at
    #: registration against the fact ledger - see `_validate`.
    measures: tuple[str, ...] = ()
    #: THE ARGUMENTS THAT BOUND THE WORK RATHER THAN ANSWER IT, and the only
    #: relaxation of wall 2 anywhere in this product. See WALL 6 in the module
    #: docstring. Checked at registration: every name must be a real property of
    #: this tool's schema, and a tool that measures nothing may not declare one.
    bounds: tuple[str, ...] = ()
    #: THE ARGUMENTS THROUGH WHICH THIS TOOL RECEIVES WHAT IT READS, in the
    #: order it would use them, the first one present in a call being what that
    #: call operates on. `app/build.py` states the whole contract in
    #: `declared_subject_arguments`; the short version is that a tool KNOWS
    #: which of its arguments is the file, and a validator that scans every
    #: string argument for a path is holding a second opinion about that.
    #:
    #: EMPTY MEANS THE TOOL HAS NOT SAID, never "operates on nothing". An
    #: undeclared tool is costed by `subject_of_a_call`'s fallback, which
    #: refuses to guess between two paths - so a tool that takes two of them
    #: cannot be costed at all until it declares. Checked at registration
    #: against this tool's own schema, which is the rule `bounds=` already gets.
    subject: tuple[str, ...] = ()
    #: WHAT THIS TOOL IS FOR, IN THE ENGINE'S OWN VOCABULARY, and the one edit
    #: that puts a tool in a capability block. See `app/tools/blocks.py`: the
    #: first dotted segment IS the pack, so there is no manifest to keep in step
    #: and no second list to go stale. Required, and every name is checked
    #: against the published vocabulary at registration - the same wall
    #: `measures=` gets, at the same moment, in front of the same reviewer.
    provides: tuple[str, ...] = ()

    @property
    def packs(self) -> frozenset[str]:
        """The capability blocks this tool belongs to. DERIVED, never declared.

        A separate `block=` field would be two declarations on one tool that
        have to agree, which is the drift machine at the smallest possible
        scale. The namespace costs nothing and cannot disagree with itself.
        """
        return frozenset(blocks.pack_of(name) for name in self.provides)

    @property
    def wants_ledger(self) -> bool:
        """Does the handler ask for the thread's ledger by name?

        Read off the signature, exactly like `wants_instrument` and for the
        identical reason: a handler that says `*, ledger` gets the ledger of the
        thread it is being called on, and a handler that does not cannot be
        handed one by accident. Declaring it twice - once in the signature and
        once in a field - is the drift machine at the smallest possible scale.

        THIS IS THE ONLY DOOR THROUGH THE TOOL BOUNDARY. A `@tool` handler's
        signature IS its JSON Schema, and wall 4 forbids a model-fillable
        argument that names a provenance or a decision; a ledger handle is both.
        So `spec=` passed explicitly - which is how `app/tools/next_moves.py`
        already does it inside the module - gets as far as the boundary and
        stops. Injection is what crosses it.
        """
        try:
            signature = inspect.signature(self.handler)
        except (TypeError, ValueError):  # a builtin or a C callable
            return False
        return "ledger" in signature.parameters

    @property
    def wants_instrument(self) -> bool:
        """Does the handler ask for the stamping licence by name?

        Read off the signature rather than declared twice. A handler that says
        `*, instrument` gets one; a handler that does not cannot be handed one
        by accident, and cannot stamp anything.
        """
        try:
            signature = inspect.signature(self.handler)
        except (TypeError, ValueError):  # a builtin or a C callable
            return False
        return "instrument" in signature.parameters

    # -- the model face ----------------------------------------------------

    def as_model_tool(self) -> dict[str, Any]:
        """The OpenAI-shaped declaration both adapters send.

        WITHOUT `thread_id`. The registry fills it from the call site and
        overwrites whatever the model sent (see `call`), so advertising it
        was a parameter that did nothing - until the second live score row,
        2026-09-18, when the model enumerated `read_plan(thread_id=2..196)`,
        1,246 calls in one turn, each a different argument so the memo never
        matched, nine minutes and a provider timeout for nothing. 21 tools
        advertised it. The model never sees its thread number; now it never
        sees the field.
        """
        parameters = dict(self.schema or {})
        properties = dict(parameters.get("properties") or {})
        if "thread_id" in properties:
            properties.pop("thread_id")
            parameters["properties"] = properties
            required = [name for name in (parameters.get("required") or ()) if name != "thread_id"]
            if "required" in parameters:
                parameters["required"] = required
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }

    # -- the control face --------------------------------------------------

    def as_control(self) -> dict[str, Any]:
        """The same tool as something a person can click.

        Fields come out of the identical JSON Schema the model is given, so a
        parameter cannot exist for one caller and not the other.
        """
        properties = self.schema.get("properties") or {}
        required = set(self.schema.get("required") or ())
        fields = [
            {
                "name": key,
                "type": (spec or {}).get("type", "string"),
                "description": (spec or {}).get("description", ""),
                "required": key in required,
                "enum": (spec or {}).get("enum"),
            }
            for key, spec in properties.items()
        ]
        return {
            "name": self.name,
            "label": self.control.label,
            "group": self.control.group,
            "verb": self.control.verb,
            "order": self.control.order,
            "description": self.description,
            "fields": fields,
            "reads": list(self.reads),
            "writes": list(self.writes),
            "measures": list(self.measures),
            "bounds": list(self.bounds),
            # ON THE CONTROL, WHICH IS THE FACE THAT IS NEVER SCOPED. A person
            # looking at the buttons can see which pack each one belongs to, and
            # that is how a wrongly-scoped turn is corrected: by clicking it.
            "provides": list(self.provides),
            "packs": sorted(self.packs),
            "needs_approval": self.approval == "always",
        }


def _the_domain_this_tool_belongs_to(spec: Any, running: Any) -> str | None:
    """The one shipped ledger that declares what this tool measures, or `None`.

    A LOOKUP RATHER THAN A JUDGEMENT, and that is only true because the shipped
    ledgers are disjoint - measured 2026-08-28: they share no fact name at all,
    which is `docs/ledgers/ai_engineering.yaml` renaming every role on purpose
    so a leak shows up as a failure. If two ledgers ever declared the same fact,
    that fact stops naming a domain and this returns `None`, which is the
    honest answer rather than a tie broken by whichever file the glob found
    first.

    `None` for anything ambiguous: no ledger, more than one, or the one it
    found being the one already running.
    """
    found: set[str] = set()
    for path in diagnosis.known_ledgers():
        candidate = diagnosis.spec_at(path)
        if any(name in candidate.facts for name in spec.measures):
            found.add(candidate.as_written)
    if len(found) != 1:
        return None
    only = next(iter(found))
    return None if only == running.as_written else only


class Registry:
    """Every tool the harness has, in declaration order."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    # -- registration ------------------------------------------------------

    def add(self, spec: ToolSpec) -> ToolSpec:
        _validate(spec)
        if spec.name in self._tools:
            raise ToolError(f"tool {spec.name!r} is already registered")
        self._tools[spec.name] = spec
        return spec

    def tool(
        self,
        name: str,
        *,
        description: str,
        schema: dict[str, Any] | None = None,
        reads: tuple[str, ...] = (),
        writes: tuple[str, ...] = (),
        measures: tuple[str, ...] = (),
        bounds: tuple[str, ...] = (),
        subject: tuple[str, ...] = (),
        provides: tuple[str, ...] = (),
        approval: str = "never",
        label: str,
        group: str,
        verb: str,
        order: int = 100,
    ):
        """Decorator form. The function keeps working as a plain function."""

        def decorate(handler: Callable[..., Any]) -> Callable[..., Any]:
            self.add(
                ToolSpec(
                    name=name,
                    description=description,
                    schema=schema or {"type": "object", "properties": {}},
                    reads=tuple(reads),
                    writes=tuple(writes),
                    measures=tuple(measures),
                    bounds=tuple(bounds),
                    subject=tuple(subject),
                    provides=tuple(provides),
                    approval=approval,
                    control=Control(label=label, group=group, verb=verb, order=order),
                    handler=handler,
                )
            )
            return handler

        return decorate

    # -- reading -----------------------------------------------------------

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self) -> Iterator[ToolSpec]:
        return iter(self._tools.values())

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def model_tools(self, only: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """The schemas this turn sends. `only` is a set of tool NAMES.

        THE MODEL FACE IS THE ONE THAT GETS SCOPED AND THE CONTROL FACE IS NOT,
        and the asymmetry is the design rather than an oversight - see
        `app/tools/blocks.py`. A pack that is not loaded is a tool the model will
        not reach for; it is never a tool the person cannot run.

        `only=None` is every tool, unchanged, and it is what a caller with no
        diagnosis to select from gets. Names the registry does not hold are
        ignored rather than raised on: this filter narrows a list, and a caller
        asking for a tool that is not registered is asking `get` for it.
        """
        if only is None:
            return [spec.as_model_tool() for spec in self._tools.values()]
        wanted = {str(name) for name in only}
        return [
            spec.as_model_tool()
            for name, spec in self._tools.items()
            if name in wanted
        ]

    def controls(self) -> list[dict[str, Any]]:
        return [
            spec.as_control()
            for spec in sorted(
                self._tools.values(), key=lambda s: (s.control.order, s.name)
            )
        ]

    def nearest(self, name: str) -> list[str]:
        """The registered tools whose name or label shares a word with `name`.

        THE SAME DEFECT AS THE ONE IN THE FACT LEDGER, in this file. A model
        that invents a tool name got `no tool named 'get_hardware_info'` back -
        correct, and a wall with no door. This harness has few enough tools that
        `call` can name every one of them, so all this does is put the likely one
        first; a match is a word the caller actually typed rather than an edit
        distance nobody can check.
        """
        wanted = evidence.informative_words(name)
        if not wanted:
            return []
        scored: list[tuple[int, str]] = []
        for spec in self._tools.values():
            own = evidence.informative_words(spec.name)
            described = evidence.informative_words(
                f"{spec.control.label} {spec.control.verb} {spec.control.group}"
            )
            score = 3 * len(wanted & own) + len(wanted & (described - own))
            if score:
                scored.append((score, spec.name))
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [candidate for _, candidate in scored]

    # -- calling -----------------------------------------------------------

    def call(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        approved: bool = False,
        actor: str = evidence.DEFAULT_ACTOR,
        thread_id: int | None = None,
    ) -> Any:
        """Run one tool. The same entry point for a model call and a button.

        Unknown arguments are dropped rather than passed through, and the drop
        is reported in the result so it is visible in the transcript. A model
        that hallucinates a parameter should not crash a turn, and it should
        not silently get away with it either.

        `actor` is the difference between a person and a model saying the same
        sentence, and it is set HERE, by the call site, because the call site is
        the only place that knows. The conductor passes `model`; the control
        route passes `user`. It is not reachable from `arguments`: no schema may
        declare it (wall 4) and the filter below would drop it anyway.

        An argument whose name is reserved is reported separately from one that
        is merely unknown. "You tried to tell me your number was measured" is a
        different event from "you invented a parameter", and the transcript
        should be able to show the first one as what it is.
        """
        spec = self._tools.get(name)
        if spec is None:
            # A REFUSAL THAT NAMES NOTHING IS A WALL WITH NO DOOR, and this was
            # one. `no tool named 'get_hardware_info'` is true and unhelpful:
            # the conductor turns it into a `no_such_tool` step in the user's
            # transcript, and the model's next guess is no better informed than
            # its first. The whole tool list is short enough to read, so the
            # refusal hands it over with the likely one named first.
            raise ToolError(_no_such_tool(self, name))
        if spec.approval == "always" and not approved:
            raise ApprovalRequired(
                f"{spec.control.verb} needs an approval before it can run. An "
                "approval is not something a tool call can carry: it is a person "
                "saying yes to this specific action, and it arrives on a "
                "different channel than the call does. Tell the user what this "
                "would do and let them start it from the control."
            )
        allowed = set((spec.schema.get("properties") or {}).keys())
        given = dict(arguments or {})
        accepted = {k: v for k, v in given.items() if k in allowed}
        refused = sorted(
            k
            for k in given
            if k not in allowed
            and (str(k).lower() in RESERVED_ARGUMENTS or k in INJECTED_ARGUMENTS)
        )
        ignored = sorted(set(given) - allowed - set(refused))

        # A FACT SENT BESIDE `facts` IS STILL A FACT, for the one tool whose
        # whole job is recording them. Max's run of 2026-09-21: told to call
        # state_facts with {"facts": {"modality": ...}}, the model sent
        # `modality` at the top level next to an empty `facts`, the name was
        # dropped as an unknown parameter, and the tool answered "No facts were
        # given" about a call that had given one. The fold moves such names
        # INTO `facts`, where the handler checks each against the ledger like
        # any other - so an invented name is still refused, by name, with the
        # ledger's help. Reported on the result, so the transcript shows it.
        folded: list[str] = []
        if spec.name in FOLD_TOP_LEVEL_INTO_FACTS and ignored:
            inner = accepted.get("facts")
            merged = dict(inner) if isinstance(inner, dict) else {}
            for name in ignored:
                merged.setdefault(name, given[name])
                folded.append(name)
            accepted["facts"] = merged
            ignored = []

        # A REQUIRED ARGUMENT THAT DID NOT ARRIVE IS A FAILED CALL, not a call
        # with a default in it. This was a live defect, found against a real
        # local model: it sent seventeen facts at the TOP LEVEL instead of
        # inside `facts`, every one of them was dropped as unknown, and
        # `run_diagnosis` answered from an empty sheet - a confident verdict
        # computed from nothing, which is the exact shape `conductor.py` warns
        # about ("a missing fact becomes a diagnosis computed from defaults").
        # Python default arguments made the malformed call indistinguishable
        # from an honest empty one. The schema already said which arguments are
        # required; nothing was reading it.
        # A TOOL THAT DECLARES `thread_id` GETS THE CALL SITE'S - whatever the
        # caller sent. The prompt does not tell the model which conversation
        # it is in - nothing in the brief carries the number - so a schema
        # that asks for it is asking for something the model cannot know, and
        # the honest source is the `thread_id` this call already arrived
        # with. Only when DECLARED: an undeclared name stays refused, so no
        # handler acquires a thread it did not ask for.
        #
        # "WHEN THE CALLER SENT NONE" WAS THE FIRST CUT, AND IT COST THREE
        # PLANS. MEASURED 2026-09-11, three live plan turns: the model called
        # `write_plan` every time, with `thread_id: 1`, `0`, `1` - numbers it
        # made up because the schema asked - and two eight-phase plans landed
        # on thread 1 while the third was refused as `no_such_thread`. A value
        # the model cannot know is not a value it can supply, so the call
        # site's replaces it rather than yielding to it.
        if "thread_id" in allowed and thread_id is not None:
            accepted["thread_id"] = int(thread_id)
        missing = sorted(set(spec.schema.get("required") or ()) - set(accepted))
        if missing:
            return {
                "ok": False,
                "error": "missing_arguments",
                "missing": missing,
                "detail": (
                    f"{spec.name} needs {', '.join(missing)} and did not get "
                    + (
                        f"{'it' if len(missing) == 1 else 'them'}. Received "
                        f"{sorted(given) or 'no arguments at all'}."
                    )
                ),
                # NAME WHAT WOULD HAVE WORKED. The old help said "the arguments
                # named in this tool's schema" without naming one of them, which
                # is a door drawn on the wall: the caller that got here is
                # exactly the caller that did not read the schema right.
                "accepts": _argument_help(spec),
                "help": (
                    "Send the arguments named above, at the top level of the "
                    "call, with nested objects where the type says object. "
                    "Nothing was run and nothing was recorded."
                ),
                # AND WHEN THE MISSING ONE IS A PATH, WHAT IS ACTUALLY THERE.
                # Max's run of 2026-09-20, on the engine that was still up:
                # 15 of 28 calls were `measure_eval_set`, six of them with no
                # arguments at all. The schema was in the reply every time. A
                # schema tells a model what SHAPE to send; it does not tell it
                # what value exists, so the next call is another guess. These
                # are names on a disk under this thread's own project folder -
                # a reading, not anybody's claim, which is why it is allowed
                # here where the ledger is not.
                **_files_for_a_missing_path(missing, thread_id),
                **({"ignored_arguments": ignored} if ignored else {}),
                **({"refused_arguments": refused} if refused else {}),
            }

        # ── A RELATIVE PATH MEANS RELATIVE TO THE WORKSPACE ──────────────────
        # Watched before it was written, twice in one afternoon (2026-08-31):
        # a thread's project sat on a real folder holding the person's data,
        # and the model sent `path: "."` and `path: "frontend/src/fixtures/..."`
        # — locations inside the ENGINE'S OWN working directory, which is an
        # implementation accident nobody chose, and in the packaged app is
        # nowhere a person could name. Telling the model the workspace in the
        # system prompt did not stop a small model guessing. So the guarantee
        # moves where guarantees live in this product: the door. A relative
        # path in a thread whose project sits on a folder is resolved against
        # that folder, the way a shell resolves against its cwd. Absolute
        # paths pass untouched, threads without a workspace are untouched, and
        # the rewrite is reported on the result so the transcript shows it.
        rehomed = _rehome_workspace_paths(accepted, thread_id)
        resolved_reads = _resolve_missing_reads(spec, accepted, thread_id)

        # WHICH LEDGER THIS CONVERSATION IS RUNNING, RESOLVED ONCE, HERE.
        # Every handler that asks for one gets this object, and the instrument
        # gets it too - so what a tool may stamp is decided against the same
        # knowledge the diagnosis is walking, rather than against whichever file
        # a module-level default happened to name. An unreadable ledger raises
        # out of `spec_at` with the path in the message: a thread that said it
        # was an AI-engineering thread must never quietly get the ML one.
        ledger = evidence.ledger_for_thread(thread_id)

        # THE INSTRUMENT MUST EXIST IN THIS DOMAIN, AND SILENCE IS NOT AN OPTION.
        # A tool declares `measures=` against the union of the ledgers this
        # product ships (see `evidence.declarable_in_any_ledger`), because
        # registration happens at import with no thread and no domain. That is
        # what lets an AI-engineering trace reader be written at all. It is NOT
        # a licence to run it anywhere: a tool whose every measurable fact is
        # unknown to this thread's ledger has no instrument here, and the honest
        # answer is to say so and name the domain, not to read the wrong file
        # and return a number about a question nobody asked.
        #
        # A tool that measures NOTHING is untouched by this - most of them - and
        # so is one that measures some facts this ledger knows and some it does
        # not; the second case is `Instrument.measured` refusing the individual
        # fact, which is a narrower answer than refusing the call.
        if spec.measures and not any(name in ledger.facts for name in spec.measures):
            # BEFORE REFUSING: IS THIS A CONVERSATION THAT HAS NOT STARTED YET?
            #
            # Every thread is created on the default ledger because nothing has
            # ever inferred one, so a person who opens the box and describes an
            # agent gets every instrument that could help them refused - and no
            # surface can move their thread. That was measured in
            # `tests/test_a_person_can_reach_the_domain_they_are_in.py` and it
            # is the gap this closes.
            #
            # The inference is a LOOKUP, not a guess: the shipped ledgers share
            # no fact names, so a tool's `measures=` names exactly one domain.
            # `events.adopt_ledger` refuses unless the thread has measured
            # nothing at all, which is what keeps
            # `evidence.ledger_for_thread`'s rule intact - a thread that has
            # used a domain has named it, and only one that has not can move.
            adopted = _the_domain_this_tool_belongs_to(spec, ledger)
            if adopted is not None and events.adopt_ledger(thread_id, adopted):
                ledger = evidence.ledger_for_thread(thread_id)
            else:
                return {
                    "ok": False,
                    "error": "not_in_this_domain",
                    "detail": _wrong_domain(spec, ledger),
                    "measures": list(spec.measures),
                    "ledger": ledger.as_written,
                    "help": (
                        "Nothing was run and nothing was recorded. Run the diagnosis "
                        "for this thread and do what it asks; the tools that can "
                        "answer this domain's questions are the ones whose facts it "
                        "declares."
                    ),
                }

        instrument = evidence.instrument_for(
            tool=spec.name,
            measures=spec.measures,
            actor=actor,
            thread_id=thread_id,
            ledger=ledger,
            # THE TAINT IS THE ACCEPTED ARGUMENTS, which is what the handler can
            # actually see. Refused and ignored keys never reach it, so tainting
            # on them would refuse honest measurements over words the tool was
            # never handed.
            arguments=accepted,
            bounds=spec.bounds,
            # WALL 9 NEEDS TO KNOW WHAT THIS TOOL IS, and the licence is where
            # it belongs: `app/tools/evidence.py` may not import this module,
            # because this module imports it.
            provides=spec.provides,
        )

        # WALL 2, AND THE ONE LINE THAT MAKES IT A PROPERTY. A handler receives
        # its arguments MARKED as the caller's - the same values under the same
        # names, as the `CallerValue` subclasses in `app/tools/evidence.py`,
        # whose every operation returns a marked result. So a handler that adds
        # one to a caller's number, parses it, doubles it or digs it out of a
        # nested object is still holding the caller's answer when it reaches
        # `measured()`, and is still refused.
        #
        # EVERY TOOL, NOT ONLY A MINTING ONE, and that is a change. It used to
        # be the tools that can stamp, on the reasoning that nothing else can
        # launder and marked values are a change to what a handler holds. That
        # reasoning has one step missing: a tool that measures nothing received
        # the caller's number UNMARKED, could put it in module state, and a
        # second tool that measures could stamp what it found there. Route 07 in
        # `tests/test_laundering_routes.py` is that pair, and it is not an
        # attack - it is `prepare_dataset` writing where `count_dataset` reads.
        # The mark is per-call and the model's turn is not, so the mark has to
        # go on at the door every value comes through.
        #
        # MERGED over `accepted` rather than replacing it, so whatever the line
        # above decided not to offer the instrument still reaches the handler
        # exactly as the caller sent it. Which arguments the instrument is told
        # about is decided there, once.
        accepted = {**accepted, **instrument.caller_arguments}

        if spec.wants_instrument:
            accepted["instrument"] = instrument
        if spec.wants_ledger:
            accepted["ledger"] = ledger

        if instrument.can_mint:
            # Wall 3. While this token is set, `evidence.assemble_facts` refuses
            # to hand anybody the claim ledger, so a tool that can stamp cannot
            # read what was claimed and re-stamp it.
            token = evidence._MINTING.set(instrument)
            try:
                result = spec.handler(**accepted)
            finally:
                evidence._MINTING.reset(token)
        else:
            result = spec.handler(**accepted)

        if isinstance(result, dict) and rehomed:
            result = dict(result)
            result["workspace_resolved"] = rehomed
            result["workspace_resolved_because"] = (
                "A relative path in a conversation whose project sits on a "
                "folder is read against that folder — the workspace — never "
                "against the harness's own working directory."
            )

        if isinstance(result, dict) and resolved_reads:
            result = dict(result)
            result["path_resolved"] = resolved_reads
            result["path_resolved_because"] = (
                "The path as sent does not exist. When exactly one file in the "
                "workspace ends with it, or has its name, that file was read; "
                "when several fit, they are named here and nothing was guessed."
            )

        if isinstance(result, dict) and folded:
            result = dict(result)
            result["folded_into_facts"] = folded
            result["folded_because"] = (
                f"{', '.join(folded)} arrived beside `facts` rather than inside it, "
                'and was read as a fact. The shape is {"facts": {"<fact>": <value>}}.'
            )
        if isinstance(result, dict) and (ignored or refused or instrument.minted):
            result = dict(result)
            if ignored or refused:
                # BOTH DROPS NOW NAME THE ALTERNATIVE. Reporting that a
                # parameter was thrown away without saying which ones exist
                # leaves the caller to guess again, and a guess costs the same
                # round the report was meant to save.
                result["accepts"] = _argument_help(spec)
            if ignored:
                result["ignored_arguments"] = ignored
                result["ignored_because"] = (
                    f"{spec.name} has no such parameter. The names it does take "
                    "are listed under `accepts`; anything else is dropped rather "
                    "than passed on, so nothing here was read."
                )
            if refused:
                result["refused_arguments"] = refused
                result["refused_because"] = (
                    "A tool argument may not name a gate or a provenance. What a "
                    "value is worth is decided by what produced it, not by what "
                    "the caller typed. There is no argument that would have "
                    "worked here and there is not meant to be one: run the tool "
                    "that measures the thing, and the origin follows from that."
                )
            if instrument.minted:
                result["measured_facts"] = list(instrument.minted)
        return result

    def clear(self) -> None:
        """Used only by tests that register throwaway tools."""
        self._tools.clear()


def _argument_help(spec: ToolSpec) -> list[str]:
    """This tool's parameters, one per line, in the shape a caller needs.

    `path: string (required) - the evaluation file or folder on this machine`.
    Built from the same JSON Schema the model was handed, so it cannot describe
    an argument the tool does not take, and it is the answer to every refusal in
    `call` that is about an argument name.
    """
    properties = spec.schema.get("properties") or {}
    required = set(spec.schema.get("required") or ())
    lines = []
    for key, declared in properties.items():
        declared = declared or {}
        shape = str(declared.get("type", "string"))
        if declared.get("enum"):
            shape += f", one of {list(declared['enum'])}"
        note = str(declared.get("description") or "").strip()
        lines.append(
            f"{key}: {shape}"
            + (" (required)" if key in required else "")
            + (f" - {note}" if note else "")
        )
    return lines or [f"{spec.name} takes no arguments at all."]


def _wrong_domain(spec: ToolSpec, ledger: diagnosis.Spec) -> str:
    """Why an instrument that exists cannot be used on this thread.

    THE SENTENCE HAS TO NAME THE DOMAIN, because the only alternative is the one
    `evidence.resolves` was caught giving: *"No tool in this harness measures
    this yet"* - true, and true for the wrong reason, said about a fact from a
    different ledger entirely. A harness whose honesty rests on saying exactly
    why it cannot answer must not have a sentence that is right by accident.

    So this one says what the tool measures, which ledger this conversation is
    running, and which ledgers DO declare those facts - which is the whole
    difference between "the product cannot do this" and "this is not the
    question you are asking".
    """
    facts = ", ".join(sorted(spec.measures))
    homes = sorted(
        {
            name
            for fact in spec.measures
            for name in evidence.ledgers_declaring(fact)
        }
    )
    return (
        f"{spec.name!r} measures {facts}, and this conversation is running "
        f"{ledger.as_written}, which declares no such fact. This tool is not "
        "refusing because the product cannot do the work - it is refusing "
        "because the work belongs to a different domain's knowledge, and "
        "reading the wrong ledger to look busy is the one thing it must not do."
        + (
            f" {facts} {'is' if len(spec.measures) == 1 else 'are'} declared in "
            f"{', '.join(homes)}."
            if homes
            else ""
        )
    )


def _no_such_tool(registry: "Registry", name: str) -> str:
    """The refusal for an invented tool name, with the door in it."""
    every = sorted(registry.names())
    if not every:
        return (
            f"no tool named {name!r}, and this registry has none at all - nothing "
            "has been registered onto it."
        )
    likely = registry.nearest(name)
    opening = f"no tool named {name!r}."
    if likely:
        opening += f" Closest by name: {', '.join(likely[:3])}."
    return (
        f"{opening} Every tool in this harness: {', '.join(every)}. Nothing was "
        "run. Tool names are fixed - they are declared in app/tools/ and handed "
        "to you verbatim; one cannot be invented or abbreviated."
    )


def _measurable_facts() -> list[str]:
    """Every fact a tool in this harness is allowed to declare `measures=` on.

    Read off the ledger through `evidence.may_be_declared_measurable`, so the
    refusal below names the real set rather than a list here that would rot the
    first time a fact's `source:` changed.
    """
    return sorted(
        {
            name
            for path in diagnosis.known_ledgers()
            for name in diagnosis.spec_at(path).facts
            if evidence.may_be_declared_measurable(name, diagnosis.spec_at(path))
        }
    )


def _validate(spec: ToolSpec) -> None:
    if not NAME_RE.match(spec.name):
        raise ToolError(
            f"{spec.name!r} is not a usable tool name: lower case, digits and "
            "underscores, 3 to 48 characters"
        )
    if not spec.description.strip():
        raise ToolError(f"tool {spec.name!r} has no description")
    if spec.approval not in APPROVALS:
        raise ToolError(
            f"tool {spec.name!r} has approval={spec.approval!r}; "
            f"expected one of {', '.join(APPROVALS)}"
        )
    if not isinstance(spec.schema, dict) or spec.schema.get("type") != "object":
        raise ToolError(f"tool {spec.name!r} must declare an object schema")
    if not callable(spec.handler):
        raise ToolError(f"tool {spec.name!r} has no handler")

    # THE HARD RULE, wall 1.
    claimed = {str(w).lower() for w in spec.writes}
    forbidden = claimed & RESERVED_WRITES
    if forbidden:
        raise ToolError(
            f"tool {spec.name!r} declares writes={sorted(forbidden)}. No tool a "
            "model can call may set a gate outcome. The gates are decided by "
            "app/diagnosis.py and by nothing else."
        )

    # THE HARD RULE, wall 2.
    properties = spec.schema.get("properties") or {}
    if not isinstance(properties, dict):
        raise ToolError(f"tool {spec.name!r} has a malformed schema")
    reserved = {k for k in properties if str(k).lower() in RESERVED_ARGUMENTS}
    if reserved:
        raise ToolError(
            f"tool {spec.name!r} accepts {sorted(reserved)} as an argument. A "
            "model must have no slot in which to hand the harness a verdict, "
            "and none in which to tell it what its own numbers are worth. "
            f"Reserved in full: {sorted(RESERVED_ARGUMENTS)}. There is no "
            "renaming that makes this legal - if the tool needs to record what "
            "it observed, declare `measures=` and stamp it with the instrument."
        )
    injected = {k for k in properties if k in INJECTED_ARGUMENTS}
    if injected:
        raise ToolError(
            f"tool {spec.name!r} declares {sorted(injected)} in its schema. The "
            "registry injects that; a schema slot for it would let a caller send "
            "one instead."
        )

    # THE SECOND HARD RULE, wall 5. What may be stamped is decided against the
    # fact ledger at import, where a reviewer can see it, rather than at runtime
    # where nobody is looking.
    for fact in spec.measures:
        if not evidence.declarable_in_any_ledger(fact):
            # The reason, and then the set that would have been accepted. The
            # reason alone sends the author back to the YAML to work out what is
            # legal, which is the same wall-with-no-door the model hits at
            # runtime - and there are only twenty-odd measurable facts, so the
            # honest answer fits.
            raise ToolError(
                f"tool {spec.name!r} declares measures={list(spec.measures)}. "
                + evidence.unmeasurable_reason(fact)
                + " A tool in this harness may declare measures= on any of: "
                + ", ".join(_measurable_facts())
                + "."
            )
    if spec.measures and not spec.wants_instrument:
        raise ToolError(
            f"tool {spec.name!r} declares measures={list(spec.measures)} but its "
            "handler takes no `instrument` parameter, so it has nothing to stamp "
            "with. Either take the instrument or stop claiming to measure."
        )

    # WALL 6. A bound is a hole in wall 2 that somebody typed on purpose, so it
    # is checked here, where a reviewer reads it, rather than believed at
    # runtime where nobody is looking.
    unknown = [name for name in spec.bounds if name not in properties]
    if unknown:
        raise ToolError(
            f"tool {spec.name!r} declares bounds={sorted(unknown)}, which "
            f"{'is' if len(unknown) == 1 else 'are'} not in its schema. A bound "
            "names an argument this tool actually takes; a bound naming nothing "
            "relaxes nothing and reads as though it did. This tool's arguments "
            f"are: {sorted(properties) or 'none'}."
        )
    if spec.bounds and not spec.measures:
        raise ToolError(
            f"tool {spec.name!r} declares bounds={list(spec.bounds)} and measures "
            "nothing. `bounds` exempts an argument from the quarantine in "
            "`Instrument.measured`, and a tool that cannot stamp never reaches "
            "it. A declaration that does nothing is a declaration that misleads "
            "the next person who reads it."
        )

    # THE SUBJECT DECLARATION, checked exactly like a bound and for the same
    # reason: it is a statement about an ARGUMENT, so a name that is not an
    # argument reads as though it said something and says nothing. See
    # `app/build.py::declared_subject_arguments` for the contract in full.
    #
    # There is deliberately NO second rule here to match "a bound on a tool that
    # measures nothing". A subject is not a relaxation of anything - a tool that
    # stamps no fact is still a tool whose steps have to be costed from the file
    # they open, and `read_agent_results` is exactly that tool.
    unknown = [name for name in spec.subject if name not in properties]
    if unknown:
        raise ToolError(
            f"tool {spec.name!r} declares subject={sorted(unknown)}, which "
            f"{'is' if len(unknown) == 1 else 'are'} not in its schema. The "
            "subject declaration names the arguments through which this tool "
            "receives what it reads, so a name it does not take cannot be one "
            "of them - and a build costed against it would be costed against a "
            "file no call will ever pass. This tool's arguments are: "
            f"{sorted(properties) or 'none'}."
        )

    # WALL 7: A TOOL SAYS WHICH BLOCK IT IS IN, AND IT SAYS IT IN THE ENGINE'S
    # WORDS. `provides=` is required rather than optional, and the reason is the
    # one `_stage_needs` gives about `needs: []` one layer out: a tool with no
    # capability is not "a tool that belongs everywhere", it is a tool no turn
    # can ever select, and a silent hole is worse than a loud one. Required to
    # state; there is no `provides=()` that means anything.
    if not spec.provides:
        raise ToolError(
            f"tool {spec.name!r} declares no `provides=`. Every tool names at "
            "least one capability from the engine's published vocabulary, and "
            "the first dotted segment of that name is the capability block the "
            "tool loads with - see app/tools/blocks.py. A tool in no block "
            "reaches no model on any turn. Packs: "
            + ", ".join(blocks.packs())
            + "."
        )
    for capability in spec.provides:
        try:
            blocks.check_name(capability)
        except blocks.BlockError as error:
            raise ToolError(
                f"tool {spec.name!r} declares provides={list(spec.provides)}. "
                + str(error)
            ) from None

    # WALL 9. A FACT SAYS WHICH INSTRUMENT MAY MEASURE IT, and this is where a
    # reviewer reads the claim.
    #
    # LAST OF THE NINE, AND FOR TWO REASONS. It reads `provides=`, so wall 7 has
    # to have established that every name in it is one the engine publishes -
    # a check against a misspelled capability would refuse for the wrong reason
    # and name the wrong fix. And it is the widest of them: every earlier wall
    # is about the tool's own declaration being internally wrong (a bound naming
    # no argument, a subject naming no argument, a fact no ledger declares),
    # which is a typo the author can see, and this one is about the tool being
    # the wrong KIND, which is a judgement. Report the typo first.
    #
    # See the wall in `app/tools/evidence.py` for the argument; the short version is that every other check in this product asks
    # where a number came from, and a tool of the wrong KIND passes all of them.
    #
    # SWEPT OVER EVERY SHIPPED LEDGER, because registration happens at import
    # with no thread and therefore no domain - the same reason the `measures=`
    # check above reads the union. A fact two ledgers both declare has to admit
    # this tool in the one it is being registered against, and `measured()`
    # asks the question again per call, where the thread's ledger is known.
    for fact in spec.measures:
        for path in diagnosis.known_ledgers():
            current = diagnosis.spec_at(path)
            if fact not in current.facts:
                continue
            if evidence.the_right_instrument(fact, spec.provides, current):
                continue
            raise ToolError(
                evidence.wrong_instrument_reason(
                    fact,
                    tool=spec.name,
                    provides=spec.provides,
                    doing="declare measures=",
                    ledger=current,
                )
            )


#: The one registry the app uses. Tools register onto it at import of
#: `app.tools`, so importing the package is what makes them exist.
REGISTRY = Registry()
tool = REGISTRY.tool
