"""The question, derived. Not written by hand, and not a form.

THE FAILURE THIS EXISTS TO FIX, in the owner's own transcript this morning. The
harness needed to know how many graded examples there were. It asked in PROSE -
"please provide at least 20 example inputs". He answered in prose: *"I have
something like 1000 tickets with full information within them tracked to
clients, reasons and so on."* A model recorded that with `state_facts`, the fact
arrived ASSERTED, and `eval_size_n` is declared `source: inspect`, which admits
MEASURED and nothing else. So the gate did not move, the harness asked again,
and the round was spent. He had the data. He would have pointed at it if
anything had asked him to point at it.

Nothing in that story is a wording problem. THE PROSE ROUND-TRIP IS WHERE THE
PROVENANCE IS LOST, and a typed card is not decoration on top of it - it changes
what KIND of thing an answer is:

  * a number typed into a field by the person whose project it is arrives
    STATED - their own word, which the ledger already admits for `source: ask`;
  * a folder chosen in a picker arrives as a PATH, a tool measures it, and the
    fact arrives MEASURED, which is the only origin `source: inspect` admits.

## What this module is

Given a diagnosis that stopped somewhere, it produces THE QUESTION THAT WOULD
MOVE IT, as data. A `Question` carries which fact, what kind of answer it takes,
what the ledger DECLARES about that fact, why it is being asked - which node or
which gate it unblocks, in the ledger's own words - and, when the fact is
`source: inspect`, THE TOOL THAT WOULD MEASURE IT instead of a field to type in.

## THE DISTINCTION IS STRUCTURAL, NOT A CONVENTION

`Question.__post_init__` refuses to build a card whose answer would arrive under
an origin the ledger does not admit for that fact. One line, reading
`Spec.admissible_for`, which reads `fact_origins.admissible_for_gates` out of
the YAML:

    inspect: [MEASURED]        a typed value is STATED at best -> refused
    ask:     [MEASURED, STATED] a typed value is the best evidence there is
    derive:  [MEASURED]        never asked at all; it comes from other facts

So there is no card in this module a person could type a value into and open a
`source: inspect` gate with. Not "no card does that today" - no card CAN, and
`tests/test_a_typed_answer_never_satisfies_an_inspect_fact.py` proves it by
trying to build the forbidden object for every fact in the ledger.

A card that let a user type into an `inspect` fact would be the five-gate test
defeated by a form. An adversary will try it, and the try has to fail at
construction rather than at review.

## WHICH DOOR A FACT HAS IS NOT DECIDED HERE

`evidence.resolves(fact)` already computes it, off the registry's own
`measures=` declarations and the ledger's own `source:`, so a tool registered
next year becomes the answer for its fact on the day it is registered with
nothing here to update. This module reads that answer and renders it:

    run_as == harness  ->  a POINTER card. Point at the file, the folder or the
                           machine; the named tool measures it; MEASURED.
    run_as == user     ->  a FIELD card. `state_facts` from the person's own
                           hand; STATED. `resolves` returns this door only for
                           `source: ask`.
    tool is None       ->  NO CARD. A `Gap`, carrying the ledger's own reason.

The middle rule is the same one `Build._validate_questions` already enforces
from the other side - *a build may not ask for something the harness can go and
look at* - and it is enforced here against the same registry, so the two cannot
disagree about whether a fact is askable.

## WHICH QUESTION TO ASK IS PRODUCT_SPEC 9.8, IMPLEMENTED RATHER THAN RESTATED

    1. Find the frontier - the first node whose condition you cannot evaluate.
    2. Collect the facts that node's condition references.
    3. Drop every one you could inspect instead, and go inspect them.
    4. Of what remains, rank by how many branches the answer eliminates.
    5. Ask the top one. Just that one.

**"Cannot evaluate" is read as "the engine had to use the ledger's own
default".** `diagnose` never fails to produce a number, because every unsupplied
fact resolves through `unsupplied_value` and the walk continues. That is right
for the engine and it is exactly the state this module has to be able to see: a
condition decided on a default is a condition decided on nobody's evidence, and
`Diagnosis.fact_origins` already marks every one of them DEFAULTED. So the
frontier is the first entry on the walked path that reads a DEFAULTED fact.

**Step 3 is implemented as an ORDER, not as a deletion.** "Drop it and go
inspect it" is what a pointer card IS, so the inspectables sort ahead of
everything askable rather than being removed - a person who is asked to point at
a folder has not been asked a question in the sense 9.8 is counting.

**Step 4's count is derived and it says what it counted.** `decides(fact)` is
the number of distinct decision points in `docs/diagnosis_engine.yaml` whose
condition READS that fact - nodes with a compiled condition, plus gates,
counted once per gate rather than once per `passes_when` row so a fact that
appears in a four-row gate is not weighted four times for being read once. Both
sets come from conditions this engine parsed; nothing here holds a list of fact
names, and `Question.decides_by` carries that sentence so the number on the card
can be checked rather than believed.

**AND ONE RULE 9.8 DOES NOT STATE, WHICH IT NEEDS.** Taken literally, "the first
node you cannot evaluate" can deadlock the product before it has asked anything.
A node's condition can read only facts nobody can answer today - a `derive` fact
nothing computes, an `inspect` fact no registered tool measures - and a frontier
fixed there would ask nothing, forever. `S0_RULES_SUFFICE`, the first node of the
first stage, is exactly that shape. So the frontier is the first entry that has a
card nobody had to invent, and entries with nothing answerable are kept, in
order, as `gaps` - the reason the harness walked past them is visible rather than
absent.

WHICH facts are unanswerable is not a property of this module and moves under it,
which is the derivation working rather than a thing to fix. `classes_n` was a gap
on the morning this was written and became a pointer card the afternoon a tool
declaring `measures=("classes_n",)` was registered, with nothing here edited.
That is the whole argument for deriving the door from `resolves` instead of
writing the questions down.

## "I DON'T KNOW" IS LEGAL ON EVERY CARD, AND USES MACHINERY THAT EXISTS

`DontKnow` takes `diagnosis.unsupplied_value(decl)` - the ledger's own declared
default - and records DEFAULTED, which is what the engine already does for a
fact nobody supplied. There is no parallel "unknown" channel and there must not
be one: a second way to say nothing is a second thing to keep in step with the
first. The claim that the default is conservative is not this module's claim
either; it is read out of the ledger's own `DEFAULTED` vocabulary line.

Resurfacing is `assumptions(result)`: every fact the walked path actually READ
whose origin is DEFAULTED, with where it was read and what would settle it. That
is the list a verdict card shows, so an assumption cannot disappear into the
reasoning silently.

## WHEN THE QUESTIONS RUN OUT, THE NEXT THING IS A BUILD

`next_step` returns a `Proposal` rather than a `Question` once the frontier has
nothing answerable left. It names the outcome, whether `app/tools/propose.py`
can honestly plan for it - read from that module's own `PROPOSERS` and
`NOT_COVERED`, not from a copy - and the tool that turns it into a Build. The
surface asks that question: *do I ask again, or do I start proposing?*

## WHAT THIS MODULE DOES NOT DO, AND ONE THING IT CANNOT SEE

It does not record anything, call any tool, touch the database or reach the
network. It reads a fact dict and the loaded spec and returns cards. Answering a
card is `state_facts` or the named measuring tool, through the ordinary tool
boundary, where the actor decides what the answer is worth - which is the whole
reason a card cannot stamp its own answer.

**The one blind spot, named rather than found later.** Four facts - `vram_gb`,
`ram_gb`, `disk_free_gb`, `accelerator` - are read by `S9_HARDWARE_ROUTER`,
which is prose in the YAML with a Python handler in `app/diagnosis.py`, not a
compiled condition. No parse reaches them, so they never appear at a frontier
and `decides()` returns 0 for them. They are `source: inspect` with
`inspect_hardware` registered against them, so if a condition ever names one the
card built for it is a pointer at this machine and could not be anything else.
The gap is in what this module can SEE, never in what it would allow.
"""

from __future__ import annotations

import ast

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app import diagnosis
from app.diagnosis import DEFAULTED, Diagnosis, MEASURED, PathEntry, Spec, STATED
from app.tools import REGISTRY, evidence


class AskingError(Exception):
    """A card that must not exist.

    Raised at construction, never at render. Every one of these is a card whose
    answer could not have counted for anything - a typed field over a fact the
    ledger says must be measured, a question about a fact no door leads to, a
    pointer with no instrument behind it. A card like that costs the person a
    round and teaches them that answering does not work, which is the more
    expensive half.
    """


# ---------------------------------------------------------------------------
# What kind of answer a card takes.
#
# The typed five come off the ledger's own declaration - an `enum` is a choice,
# a `multi` is a set of choices, a `bool` is a yes or no. The pointing two are
# what a card offers INSTEAD of a field, and which of them applies comes off the
# measuring tool's own schema: a tool that needs no arguments reads the machine,
# and a tool that needs some is pointed at what they name. "A set of rows" is
# the second of those with more than one slot - `measure_baseline` wants a file
# and the two columns - and it is spelled out by the slots rather than by a word
# here, because the slots are the tool's declaration and a word here would be a
# second opinion about it.

NUMBER = "number"
CHOICE = "choice"
CHOICES = "choices"
YES_NO = "yes_no"
TEXT = "text"
POINTER = "pointer"
MACHINE = "machine"

#: Answers a person types. Only ever offered where the ledger admits a person's
#: own word - see `Question.__post_init__`.
TYPED_ANSWERS = frozenset({NUMBER, CHOICE, CHOICES, YES_NO, TEXT})

#: Answers that name something for an instrument to read.
POINTING_ANSWERS = frozenset({POINTER, MACHINE})

ANSWERS = TYPED_ANSWERS | POINTING_ANSWERS

#: What a typed answer is worth when the person themselves sends it. Not what
#: this module decides - `evidence.SUPPLIED_ORIGIN[USER]` decides it at the call
#: site, and this is the same constant so the card cannot promise a stamp the
#: boundary would not write.
TYPED_ANSWER_ARRIVES_AS = evidence.SUPPLIED_ORIGIN[evidence.USER]

#: What a pointed-at answer is worth once the named tool has run.
POINTED_ANSWER_ARRIVES_AS = MEASURED


def _spec() -> Spec:
    """The ledger. Singular, and that is now a LIMIT rather than a design.

    Nothing in this module takes a `spec` argument. `diagnose` does, because the
    engine is a function of a file and the loader has to be testable against a
    malformed one. A CARD is a promise about what an answer will be worth when
    it reaches the product, and a card validated against some other file would
    be a promise about nothing.

    **THE SENTENCE THIS DOCSTRING USED TO END WITH WAS "AND THE PRODUCT HAS ONE
    LEDGER", AND IT STOPPED BEING TRUE AT MIGRATION v011.** The product ships
    two, a conversation names which one it is running, and this module reads
    neither: it reads `diagnosis.default_spec()`, thirteen times, from two
    dataclasses and eleven functions.

    Measured on 2026-08-27 through `GET /api/next_step` on a thread running
    `docs/ledgers/ai_engineering.yaml`: outcome `BLOCKED__DEFINE_SUCCESS_FIRST`,
    question `classes_n`, because `S0_RULES_SUFFICE`. An outcome from the other
    tree, a fact that ledger does not declare, and a card naming a tool that
    cannot measure anything in that domain - every one of them confident.

    `app/main.py::next_step_ep` now refuses that request rather than serving it,
    with a sentence naming both ledgers, so the limit is loud at the boundary
    instead of silent inside it. Threading a ledger through this module is the
    real fix and it is written down as a bounded debt in `docs/PHASES.md`;
    until it is done, this function is where the assumption lives and this
    paragraph is what stops the next reader believing the old sentence.
    """
    return diagnosis.default_spec()


# ---------------------------------------------------------------------------
# Where a condition's facts come from. Parsed, never listed.


def the_ledger_this_module_is_written_for() -> Spec:
    """The one ledger every card here is validated against.

    PUBLIC SO A CALLER DOES NOT HAVE TO GUESS, and calling `_spec()` rather than
    `diagnosis.default_spec()` on purpose. `app/tools/__init__.py` needs to know
    whether the thread's ledger is the one these cards are written for, and
    `tests/test_the_default_ledger_is_a_bounded_debt.py` pins which files read
    the default ledger unconditionally - a new reader is a new coupling and it
    is invisible in a total. Reading it THROUGH this module keeps the coupling
    where it is already counted instead of adding a fourteenth file to a census
    that exists to stop exactly that.

    It also means one answer rather than two: a caller deriving "the ledger
    asking is written for" by calling `default_spec()` itself would be a second
    definition of this module's own limit, free to drift from it the day this
    module stops defaulting.
    """
    return _spec()


def _gate_nodes() -> dict[str, str]:
    """Gate NODE id -> gate id.

    A gate is entered in the walk as a node entry carrying `gates[g]["node"]` -
    `S0_NO_EVAL_SET` for `G0_EVAL_SET` - because `_evaluate_gate` notes the node
    before it knows whether the gate passes. So a path entry that looks like a
    node can be a gate, and reading its facts out of `spec.conditions` would
    find nothing at all.
    """
    return {gate["node"]: gate_id for gate_id, gate in _spec().gates.items()}


def _gate_row(gate_id: str, row_key: str) -> dict[str, Any]:
    for row in _spec().gates[gate_id]["passes_when"]:
        if row["method_class"] == row_key:
            return row
    raise AskingError(f"gate {gate_id} has no row {row_key!r}")


def _row_key_for(gate_id: str, result: Diagnosis | None) -> str:
    """Which `passes_when` row applied, taken from the run wherever possible.

    A gate asks a different question of a different method class, so the row is
    what decides which facts the gate READ - and reading the wrong row would
    name facts the run never looked at. Three sources, best first: the gate entry
    the walk wrote when the gate passed, the gate ledger's own row, and finally
    the row the proposal's class selects.
    """
    spec = _spec()
    if result is not None:
        for entry in result.path:
            if entry.kind == "gate" and entry.id == gate_id and entry.row:
                return entry.row
        recorded = (result.gate_ledger.get(gate_id) or {}).get("row")
        if recorded:
            return str(recorded)
        klass = spec.method_class(result.proposed_method)
        return spec.row_key(gate_id, klass)
    # `spec.no_proposal` rather than the old module constant `diagnosis.UNSET`:
    # the sentinel is a NAME the ledger owns and declares in `contract.roles`,
    # not a string the engine holds. Same value for this ledger, and the right
    # value for one that spells it differently.
    return spec.row_key(gate_id, spec.method_class(spec.no_proposal))


def facts_read_by(entry: PathEntry, result: Diagnosis | None = None) -> frozenset[str]:
    """The declared facts one entry on the walked path READ.

    Three shapes, and all three are answered out of what the engine already
    parsed at load time:

      * a gate entry, or a node entry that is a gate's node - `gate_row_facts`,
        which `app/diagnosis.py` built from the row's own `requires:` string;
      * a node with a compiled condition - the same parse, run over
        `spec.conditions`;
      * a node the engine executes with a Python handler, or one whose condition
        is `always` - the empty set, because there is no expression to read and a
        guess about what a handler touches would be exactly the hand-written list
        this module exists not to have.
    """
    spec = _spec()
    gates = _gate_nodes()

    if entry.kind == "gate":
        return frozenset(spec.gate_row_facts.get((entry.id, entry.row or ""), frozenset()))

    gate_id = gates.get(entry.id)
    if gate_id is not None:
        row_key = _row_key_for(gate_id, result)
        return frozenset(spec.gate_row_facts.get((gate_id, row_key), frozenset()))

    # WHAT IT REACHED BEATS WHAT IT MENTIONS. `and` short-circuits, so the
    # parse below names every operand while the evaluation may have stopped at
    # the first. The engine records the reached set on the path entry as it
    # walks (`PathEntry.reached`), which costs nothing and cannot drift from
    # the answer, because it IS the answer's own reads.
    #
    # Measured 2026-09-19, and the docstring above this function had already
    # named the node it would happen on: `S0_RULES_SUFFICE` asks
    # `task_family in {extraction, classification} and ... and classes_n <= 5`.
    # On a generation thread it answers False at the first operand and never
    # looks at `classes_n` - but the parse named it, `classes_n` has a tool,
    # so the frontier made it the question and the brief said "Blocked on
    # `classes_n`. Run assess_the_data." The model obeyed, the tool refused,
    # and the walk's real blocker two rows down was never mentioned.
    reached = (getattr(result, "reached_by", None) or {}).get(entry.id)
    if reached is not None:
        return frozenset(reached)
    tree = spec.conditions.get(entry.id)
    if tree is None:
        return frozenset()
    return frozenset(diagnosis._facts_read_by(spec, tree))


def facts_guarded_by_measured(entry: PathEntry) -> frozenset[str]:
    """Facts this entry's condition reads ONLY to ask whether a tool stamped them.

    WHY THIS IS NOT THE FRONTIER'S BUSINESS. The frontier is "everywhere the
    walk decided something on nobody's evidence" - a fact whose origin is
    DEFAULTED, so the ledger's own default picked the fork and a person could
    have picked it differently. `measured(f)` is not that question. It reads the
    ORIGIN, and an absent fact answers it FALSE with certainty: nothing was
    stamped, so the guard is closed and the node's condition is settled without
    anybody supplying anything. There is no fork here to offer somebody.

    MEASURED 2026-09-10, and this is why the function exists. `cannot_train_here`
    is read at `S0_THE_CARD_ALREADY_SAID_NO`, which sits at stage 0 - so on every
    thread that had never called the recorder, the frontier reported it
    unevaluable and the asker offered it FIRST, ELEVEN TIMES, ahead of
    `target_score` and `eval_size_n`. The intake loop stopped advancing: a
    walk that should have reached "define success" sat on a question about a
    refusal that had not happened. A closure that closes nothing must not
    become the first thing a person is asked.

    IT IS ALSO UNANSWERABLE, which is the second half of the argument. Only
    `record_that_this_card_refuses` can make `measured(f)` true; a person saying
    "yes it cannot" arrives STATED and RC10_AN_ASSERTION_NEVER_MINTS keeps it
    out. Offering a card for it promises a door that does not open.
    """
    spec = _spec()
    tree = spec.conditions.get(entry.id)
    if tree is None:
        return frozenset()
    guarded = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "measured":
            continue
        for argument in node.args:
            if isinstance(argument, ast.Name):
                guarded.add(argument.id)
    return frozenset(guarded)


_DECISION_POINTS: dict[int, dict[str, tuple[tuple[str, ...], tuple[str, ...]]]] = {}


def _decision_points() -> dict[str, tuple[tuple[str, ...], tuple[str, ...]]]:
    """fact -> (nodes that read it, gates that read it). Computed once per spec.

    GATES ARE COUNTED ONCE, not once per `passes_when` row. A gate asks one
    question; that it asks it four different ways of four method classes is a
    property of the gate and not four separate forks a single answer opens.
    Counting rows was the other option and it inflates exactly the facts that
    appear in the widest gates, which is a ranking that would look derived and
    would not be about branches at all.
    """
    spec = _spec()
    key = id(spec)
    cached = _DECISION_POINTS.get(key)
    if cached is not None:
        return cached

    nodes: dict[str, set[str]] = {}
    for node_id, tree in spec.conditions.items():
        for name in diagnosis._facts_read_by(spec, tree):
            nodes.setdefault(name, set()).add(node_id)

    gates: dict[str, set[str]] = {}
    for (gate_id, _row), names in spec.gate_row_facts.items():
        for name in names:
            gates.setdefault(name, set()).add(gate_id)

    table = {
        name: (tuple(sorted(nodes.get(name, ()))), tuple(sorted(gates.get(name, ()))))
        for name in spec.facts
    }
    _DECISION_POINTS[key] = table
    return table


#: What `decides` counted, in one sentence, carried on every card so the number
#: can be checked. Never rephrased at a call site.
DECIDES_BY = (
    "distinct decision points in docs/diagnosis_engine.yaml whose condition "
    "reads this fact: nodes with a compiled condition, plus gates counted once "
    "each rather than once per passes_when row. Parsed by app/diagnosis.py at "
    "load time; nothing here holds a list of fact names."
)


def decides(fact: str) -> int:
    """How many forks in the tree this one answer settles."""
    nodes, gates = _decision_points().get(str(fact), ((), ()))
    return len(nodes) + len(gates)


def decision_points(fact: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The nodes and the gates behind `decides`, so the count is checkable."""
    return _decision_points().get(str(fact), ((), ()))


# ---------------------------------------------------------------------------
# The parts of a card.


@dataclass(frozen=True)
class Slot:
    """One thing a pointer card asks the person to point at.

    Read off the measuring tool's own JSON Schema - the same schema the model is
    given and the same one `ToolSpec.as_control()` renders as a form - so a card
    cannot ask for an argument the tool does not have, and gains one the day the
    tool does.

    `bounds` is the tool's own `bounds=` declaration: an argument that caps the
    work rather than answering the question. A surface should not present one as
    part of the answer, and `max_rows` on `profile_dataset` is the reason - a
    count equal to a cap has already been mistaken for a laundered value once.
    """

    name: str
    type: str
    describe: str
    required: bool
    bounds: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "describe": self.describe,
            "required": self.required,
            "bounds": self.bounds,
        }


@dataclass(frozen=True)
class Because:
    """Why this is being asked: the node or gate it unblocks, in the file's words.

    Every string here is read out of `docs/diagnosis_engine.yaml`. A gate's
    `asks:` is already a sentence written for a person - *"Is there a set of
    examples we can score, so that 'better' is a measurement and not a
    feeling?"* - and a node carries `say:` and `action:` for the same purpose.
    Composing a sentence here would put words in the engine's mouth, and the
    engine is the thing being explained.

    ONE HONEST MISMATCH, LABELLED RATHER THAN PAPERED OVER. A gate's `asks:` is
    a question. A node's `say:` is what the node says when it FIRES - *"This is a
    lookup, regex or SQL problem"* - so on a node card `asks` reads as WHAT THIS
    FORK DECIDES rather than as a question put to the person. That is the ledger
    as it stands, and a surface should render it as context beside the card and
    not as the card's own headline. Writing a question here to fill the gap
    would be this module inventing the engine's reasoning, which is the one
    thing it must not do; the durable fix is an `asks:` line on the ask nodes,
    in the YAML, where a reviewer can see it.
    """

    entry: str
    kind: str  # "node" | "gate"
    stage: str
    gate: str = ""
    row: str = ""
    asks: str = ""
    action: str = ""
    note: str = ""
    requires: str = ""
    unblocks: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry": self.entry,
            "kind": self.kind,
            "stage": self.stage,
            "gate": self.gate,
            "row": self.row,
            "asks": self.asks,
            "action": self.action,
            "note": self.note,
            "requires": self.requires,
            "unblocks": self.unblocks,
        }


@dataclass(frozen=True)
class DontKnow:
    """The legal answer to every card, and what taking it costs.

    It is the engine's own behaviour for a fact nobody supplied, named so a
    surface can offer it as a button rather than leaving the person to guess
    that silence is allowed. `takes` is `diagnosis.unsupplied_value` over the
    fact's own declaration; `recorded_as` is DEFAULTED, which is the one origin
    a caller may not claim, because only the engine is entitled to say that the
    ledger's default was applied.
    """

    takes: Any
    recorded_as: str
    how: str
    resurfaces_as: str
    conservative_because: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "legal": True,
            "takes": self.takes,
            "recorded_as": self.recorded_as,
            "how": self.how,
            "resurfaces_as": self.resurfaces_as,
            "conservative_because": self.conservative_because,
        }


def _dont_know(fact: str) -> DontKnow:
    spec = _spec()
    decl = spec.facts[fact]
    vocabulary = (spec.origin_policy.get("vocabulary") or {}).get(DEFAULTED, "")
    return DontKnow(
        takes=diagnosis.unsupplied_value(decl),
        recorded_as=DEFAULTED,
        how=(
            "leave the fact out of the sheet. The engine applies the ledger's "
            "own default and records the origin as DEFAULTED; there is no "
            "separate 'unknown' to send, and a caller may not supply DEFAULTED "
            "itself."
        ),
        resurfaces_as=(
            "an assumption on the next verdict - app/asking.py assumptions(), "
            "which lists every DEFAULTED fact the walk actually read"
        ),
        conservative_because=" ".join(str(vocabulary).split()),
    )


def _declared(fact: str) -> dict[str, Any]:
    """What the ledger DECLARES about this fact. Read, never described.

    `evidence.declaration` already answers most of it in the shape a caller
    needs to send a fact, so this is that answer plus the three things a CARD
    needs and a tool refusal does not: the scope the row would be written at,
    the default an "I don't know" would take, and the gates that read it - which
    is what makes "why does this matter" answerable without a second lookup.
    """
    spec = _spec()
    decl = spec.facts[fact]
    out = dict(evidence.declaration(fact))
    out["scope"] = evidence.scope_of(fact)
    out["default"] = diagnosis.unsupplied_value(decl)
    out["declares_a_default"] = "default" in decl
    out["gates_that_read_it"] = list(evidence.gates_that_read(fact))
    out["substantiation"] = spec.substantiation(fact).strip()
    if "fallback" in decl:
        # The four hardware facts carry `fallback: ask`. It is a real input
        # route and it is NOT a measurement - a stated vram_gb sets
        # cost_provenance to UNKNOWN and opens nothing - so it is carried as a
        # note on the pointer card and never as a field beside it.
        out["fallback"] = decl["fallback"]
    if "opinion_of" in decl:
        out["opinion_of"] = decl["opinion_of"]
    if "must_be" in decl:
        out["must_be"] = decl["must_be"]
    return out


def _accepts(fact: str) -> tuple[str, dict[str, Any]]:
    """The answer kind and its exact shape, for a fact a person may type.

    Refuses anything the ledger declares in a shape a field cannot hold. Today
    that is `map[failure_mode,int]`, which is `source: derive` and reaches a
    pointer card instead - but the refusal is on the SHAPE rather than on that
    fact's name, so a mapping declared `source: ask` next year is refused too
    instead of being rendered as a text box nobody could fill correctly.
    """
    decl = _spec().facts[fact]
    if "enum" in decl:
        return CHOICE, {"one_of": list(decl["enum"])}
    if "multi" in decl:
        return CHOICES, {"any_of": list(decl["multi"])}
    declared = str(decl.get("type") or "")
    if declared == "bool":
        return YES_NO, {"type": "bool"}
    if declared in ("int", "float"):
        return NUMBER, {"type": declared}
    if declared == "str":
        return TEXT, {"type": "str"}
    raise AskingError(
        f"{fact!r} is declared {declared!r}, which is not a shape a person can "
        "type into a field. A card that rendered it anyway would collect "
        "something the ledger would then refuse."
    )


def _slots(tool_name: str) -> tuple[Slot, ...]:
    spec = REGISTRY.get(tool_name)
    if spec is None:
        raise AskingError(
            f"{tool_name!r} is not a registered tool, so nothing would run when "
            "this card was answered."
        )
    properties = spec.schema.get("properties") or {}
    required = set(spec.schema.get("required") or ())
    bounds = set(getattr(spec, "bounds", ()) or ())
    return tuple(
        Slot(
            name=name,
            type=str((declared or {}).get("type") or "string"),
            describe=str((declared or {}).get("description") or "").strip(),
            required=name in required,
            bounds=name in bounds,
        )
        for name, declared in properties.items()
    )


# ---------------------------------------------------------------------------
# The card, and the one place the wall is.


@dataclass(frozen=True)
class Question:
    """One card. One fact. One kind of answer, and the origin it will arrive as.

    THE INVARIANT IS IN `__post_init__` AND IT IS ONE COMPARISON: the origin
    this card's answer would carry has to be one the ledger admits for this
    fact. Everything else here is rendering.

    That comparison is what makes "a typed value cannot satisfy an inspect fact"
    a property of the type rather than a rule somebody follows. `admissible_for`
    reads `fact_origins.admissible_for_gates` out of the YAML, so the day the
    ledger changes its mind about a source, this changes with it and no code
    here is edited.
    """

    fact: str
    answer: str
    arrives_as: str
    accepts: dict[str, Any]
    declared: dict[str, Any]
    because: Because
    settled_by: dict[str, Any]
    dont_know: DontKnow
    decides: int
    decides_by: str = DECIDES_BY
    slots: tuple[Slot, ...] = ()
    also_settles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        spec = _spec()
        fact = self.fact

        if fact not in spec.facts:
            raise AskingError(
                f"{fact!r} is not a declared fact. A card about it would collect "
                "an answer with nowhere to go; the ledger is in "
                "docs/diagnosis_engine.yaml."
            )
        if self.answer not in ANSWERS:
            raise AskingError(f"{self.answer!r} is not an answer kind this module renders")

        source = spec.facts[fact].get("source")
        admissible = spec.admissible_for(fact)

        # THE WALL. Not "a typed value is refused for inspect facts" - the card
        # promises an origin, and an origin the ledger will not admit is a
        # promise the product cannot keep.
        if self.arrives_as not in admissible:
            raise AskingError(
                f"a card for {fact!r} would collect an answer arriving "
                f"{self.arrives_as}, and the ledger declares it source: {source}, "
                f"which admits {sorted(admissible)}. "
                + spec.substantiation(fact).strip()
            )

        if evidence.is_an_opinion(fact):
            # Wall 7. Nothing settles a challenge on an opinion, so nothing asks
            # one either: a card would be the harness inviting a judgement and
            # then filing it where a reading belongs.
            raise AskingError(
                f"{fact!r} is declared opinion_of: {evidence.opinion_of(fact)}. "
                "A judgement is not a reading however carefully it is collected, "
                "and no gate reads this fact."
            )

        measured_by = sorted(
            tool_spec.name for tool_spec in REGISTRY if fact in tool_spec.measures
        )

        if self.answer in TYPED_ANSWERS:
            if self.arrives_as != TYPED_ANSWER_ARRIVES_AS:
                raise AskingError(
                    f"a field over {fact!r} collects a person's own word, which "
                    f"is {TYPED_ANSWER_ARRIVES_AS}, not {self.arrives_as!r}."
                )
            if source != "ask":
                # Belt and braces over the wall above. Today `ask` is the only
                # source admitting STATED, so this cannot fire on its own - and
                # if a future ledger admitted STATED somewhere else, that would
                # be a decision worth making on purpose rather than inheriting.
                raise AskingError(
                    f"{fact!r} is declared source: {source}. A field is offered "
                    "only for a fact the ledger says is the person's to supply."
                )
            if measured_by:
                # The same rule `Build._validate_questions` enforces, against the
                # same registry: look before you ask.
                raise AskingError(
                    f"a field over {fact!r} asks the person for something "
                    f"{measured_by[0]!r} measures. Look before you ask: a "
                    "question the product could answer itself is a step it "
                    "failed to take."
                )
            if self.slots:
                raise AskingError("a typed field points at nothing and has no slots")
        else:
            if self.arrives_as != POINTED_ANSWER_ARRIVES_AS:
                raise AskingError(
                    f"a pointer card for {fact!r} ends in an instrument reading, "
                    f"which is {POINTED_ANSWER_ARRIVES_AS}, not {self.arrives_as!r}."
                )
            tool = str(self.settled_by.get("tool") or "")
            if not tool or self.settled_by.get("run_as") != evidence.HARNESS:
                raise AskingError(
                    f"a pointer card for {fact!r} names no tool the harness would "
                    "run, so nothing would measure anything when it was answered."
                )
            if tool not in measured_by:
                raise AskingError(
                    f"{tool!r} does not declare measures=({fact!r},), so it could "
                    "not stamp the answer even if it ran."
                )
            if self.answer == MACHINE and any(slot.required for slot in self.slots):
                raise AskingError(
                    f"{tool!r} requires arguments, so this card has something to "
                    "point at and is not a reading of the machine."
                )
            if self.answer == POINTER and not any(slot.required for slot in self.slots):
                raise AskingError(
                    f"{tool!r} requires no arguments, so there is nothing for the "
                    "person to point at."
                )

    # -- reading ----------------------------------------------------------

    @property
    def typed(self) -> bool:
        """Does this card render a field the person types into?"""
        return self.answer in TYPED_ANSWERS

    @property
    def points(self) -> bool:
        """Does this card render a way to point at something instead?"""
        return self.answer in POINTING_ANSWERS

    @property
    def answered_by(self) -> str:
        return str(self.settled_by.get("tool") or "")

    @property
    def run_as(self) -> str:
        return str(self.settled_by.get("run_as") or "")

    def opens(self) -> tuple[str, ...]:
        """The gates this answer could open, at the origin this card produces."""
        if self.arrives_as not in _spec().admissible_for(self.fact):  # pragma: no cover
            return ()
        return tuple(evidence.gates_that_read(self.fact))

    def as_dict(self) -> dict[str, Any]:
        return {
            "fact": self.fact,
            "answer": self.answer,
            "typed": self.typed,
            "arrives_as": self.arrives_as,
            "accepts": dict(self.accepts),
            "declared": dict(self.declared),
            "because": self.because.as_dict(),
            "settled_by": dict(self.settled_by),
            "answered_by": self.answered_by,
            "run_as": self.run_as,
            "slots": [slot.as_dict() for slot in self.slots],
            "also_settles": list(self.also_settles),
            "opens": list(self.opens()),
            "decides": self.decides,
            "decides_by": self.decides_by,
            "dont_know": self.dont_know.as_dict(),
        }


@dataclass(frozen=True)
class Gap:
    """A fact at the frontier that no card in this harness can honestly collect.

    Three kinds reach here and all three are worth telling apart, which is why
    the reason is carried verbatim from whoever refused:

      * an `inspect` fact no registered tool measures - `tabular_rows` and
        `schema_compliance` on the day this was written. A field would be a typed
        value over a fact the gates may only read as a measurement, so there is
        no card. The fix is a tool, not a form, and `evidence.resolves` says so
        in as many words. `app/tools/propose.py` refuses to plan for the outcome
        that waits on `tabular_rows` for the same reason and at length;
      * a `derive` fact nothing computes - `modality` and `task_family` on that
        same day. It comes from other facts, and the answer for it is a build:
        the engine's own `ACTION__NAME_THE_MODALITY` build previews the rows and
        profiles the data first, so the person answers while looking at their own
        file instead of from memory;
      * an opinion. `judge_score` is a model's grade of its own homework, no gate
        reads it, and no card asks for it.

    THE FIRST TWO LISTS MOVE. A tool registered against one of those facts turns
    its gap into a pointer card here with nothing edited, which is the point;
    the examples are dated rather than maintained.

    A Gap is not a failure. It is the honest reply, and it is what stops this
    module inventing a door where the product has none.
    """

    fact: str
    reason: str
    declared: dict[str, Any]
    settled_by: dict[str, Any]
    because: Because

    def as_dict(self) -> dict[str, Any]:
        return {
            "fact": self.fact,
            "reason": self.reason,
            "declared": dict(self.declared),
            "settled_by": dict(self.settled_by),
            "because": self.because.as_dict(),
        }


# ---------------------------------------------------------------------------
# Building one card.


def _because_for(entry: PathEntry, result: Diagnosis | None) -> Because:
    spec = _spec()
    gates = _gate_nodes()

    gate_id = entry.id if entry.kind == "gate" else gates.get(entry.id)
    if gate_id is not None:
        gate = spec.gates[gate_id]
        row_key = entry.row if entry.kind == "gate" and entry.row else _row_key_for(gate_id, result)
        row = _gate_row(gate_id, row_key)
        on_fail = gate.get("on_fail") or {}
        return Because(
            entry=gate["node"],
            kind="gate",
            stage=str(gate.get("stage") or ""),
            gate=gate_id,
            row=row_key,
            asks=_line(gate.get("asks")),
            action=_line(on_fail.get("action") or on_fail.get("recipe")),
            note=_line(on_fail.get("note")),
            requires=_line(row.get("requires")),
            unblocks=str(on_fail.get("outcome") or on_fail.get("route") or ""),
        )

    node = spec.node_index.get(entry.id) or {}
    return Because(
        entry=entry.id,
        kind="node",
        stage=str(spec.node_stage.get(entry.id) or ""),
        # `asks:` FIRST, AND IT IS A DIFFERENT THING FROM `say:`. `say:` is what
        # this fork DECIDES - "Nothing downstream is decidable until 'good' is
        # defined" - and putting it where a question belongs shows the person a
        # verdict when they were being asked something. The six ASK-policy nodes
        # carry a real question in `asks:`; the rest have only `say:`, and for
        # them it stays the honest fallback rather than nothing at all.
        asks=_line(node.get("asks") or node.get("say")),
        # `effect:` when there is no `action:`. A constraint node - the one that
        # strikes every hosted-API outcome when the data may not leave - carries
        # neither `say` nor `action`, and what it DOES is the honest answer to
        # "why are you asking me this". Still the file's own words.
        action=_line(node.get("action") or node.get("effect")),
        note=_line(node.get("exit_criterion")),
        requires=_line(node.get("condition")),
        unblocks=str(node.get("outcome") or node.get("route") or ""),
    )


def _line(value: Any) -> str:
    """A YAML block scalar as one line. Quotes and folded newlines both go."""
    text = " ".join(str(value or "").split())
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()
    return text


def question_for(fact: str, because: Because | None = None) -> Question | Gap:
    """The card for one fact, or the honest reason there is not one.

    THE THREE-WAY SPLIT IS `evidence.resolves`'S AND NOT THIS FUNCTION'S. That
    matters more than it looks: `resolves` derives the door from the registry's
    `measures=` declarations and the ledger's `source:`, so a tool registered
    next year turns the card for its fact from a field into a pointer on the day
    it is registered. A rule written here would be a second opinion about the
    same question, and the two would disagree the first week.
    """
    name = str(fact)
    spec = _spec()
    if name not in spec.facts:
        raise AskingError(
            f"{name!r} is not a declared fact; the ledger is in "
            "docs/diagnosis_engine.yaml."
        )

    why = because or Because(entry="", kind="node", stage="")
    settled = evidence.resolves(name)
    declared = _declared(name)
    tool = settled.get("tool")
    run_as = settled.get("run_as")

    if tool and run_as == evidence.HARNESS:
        slots = _slots(str(tool))
        answer = POINTER if any(slot.required for slot in slots) else MACHINE
        return Question(
            fact=name,
            answer=answer,
            arrives_as=POINTED_ANSWER_ARRIVES_AS,
            accepts={
                "point_at": [slot.name for slot in slots if slot.required],
                # THE ARGUMENTS THE SCHEMA DOES NOT DEMAND AND THE ANSWER OFTEN
                # NEEDS, and leaving them out cost a round trip every time.
                #
                # `point_at` is built from `slot.required`, which is a property
                # of the SCHEMA. `classes_n` is settled by `assess_the_data`,
                # whose only required argument is `path` - so a caller does
                # exactly what it was told, and the tool stamps NOTHING, because
                # it counts classes only when `label_column` names the column.
                # That is the tool being honest: told nothing, it reports a
                # guess as a guess. The reply then names the argument, so the
                # loop closes on the SECOND call.
                #
                # Measured 2026-09-09 driving the intake for the
                # architecture-JSON task: three decisions, and the first one
                # takes two calls because the first is spent learning what the
                # second needs. A person cannot see the difference between "you
                # have not pointed at anything yet" and "you pointed and it did
                # not count"; both come back as the same question again.
                #
                # These are NOT promoted into `point_at`. They are not
                # required, and saying they are would be a different lie - a
                # caller with no label column would be told to supply one that
                # does not exist. They are offered beside it, which is what the
                # `slots` list already carried and no consumer was reading.
                "and_these_change_the_answer": [
                    slot.name for slot in slots if not slot.required
                ],
                "measured_by": tool,
                "produces": declared.get("accepts"),
            },
            declared=declared,
            because=why,
            settled_by=dict(settled),
            dont_know=_dont_know(name),
            decides=decides(name),
            slots=slots,
        )

    if tool and run_as == evidence.USER:
        answer, accepts = _accepts(name)
        return Question(
            fact=name,
            answer=answer,
            arrives_as=TYPED_ANSWER_ARRIVES_AS,
            accepts=accepts,
            declared=declared,
            because=why,
            settled_by=dict(settled),
            dont_know=_dont_know(name),
            decides=decides(name),
        )

    return Gap(
        fact=name,
        reason=_line(settled.get("note")) or (
            "Nothing in this harness settles this fact, and no card is offered "
            "for it."
        ),
        declared=declared,
        settled_by=dict(settled),
        because=why,
    )


# ---------------------------------------------------------------------------
# The frontier.


def _rank(card: Question) -> tuple[int, int, str]:
    """PRODUCT_SPEC 9.8 steps 3 and 4, as one sort key.

    Inspectables first - step 3 says drop them and go inspect, and a pointer
    card is what "go inspect" looks like when the harness needs to be told where
    to look. Then by how many branches the answer eliminates, descending. Then
    by fact name, which decides nothing and only makes the order the same twice.
    """
    return (0 if card.points else 1, -card.decides, card.fact)


def rank(cards: Sequence[Question]) -> tuple[Question, ...]:
    """The cards in the order 9.8 asks for. Public because the surface needs it.

    A surface that shows a frontier - "here is everything I still do not know" -
    has to show it in the same order the harness would ask, or the person and
    the product are working from two different priorities.
    """
    return tuple(sorted(cards, key=_rank))


@dataclass(frozen=True)
class Unevaluable:
    """One entry on the walked path whose condition was decided on a default.

    `unknown` is every fact it read that nobody supplied. `questions` is the
    ranked subset a card exists for; `gaps` is the rest, kept rather than
    dropped so that "the harness walked past this" has a visible reason.
    """

    entry: str
    kind: str
    because: Because
    unknown: tuple[str, ...]
    questions: tuple[Question, ...]
    gaps: tuple[Gap, ...]

    @property
    def answerable(self) -> bool:
        return bool(self.questions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry": self.entry,
            "kind": self.kind,
            "because": self.because.as_dict(),
            "unknown": list(self.unknown),
            "questions": [q.as_dict() for q in self.questions],
            "gaps": [g.as_dict() for g in self.gaps],
        }


@dataclass(frozen=True)
class Frontier:
    """Everywhere the walk decided something on nobody's evidence, in order."""

    outcome: str
    verdict: str
    entries: tuple[Unevaluable, ...] = ()

    @property
    def first_answerable(self) -> Unevaluable | None:
        for entry in self.entries:
            if entry.answerable:
                return entry
        return None

    @property
    def exhausted(self) -> bool:
        """No card left to offer. The next thing is a build, not a question."""
        return self.first_answerable is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "verdict": self.verdict,
            "exhausted": self.exhausted,
            "entries": [entry.as_dict() for entry in self.entries],
        }


def frontier(result: Diagnosis) -> Frontier:
    """Where this run stopped believing itself, and what would move it.

    An entry is on the frontier when a fact its condition READ has origin
    DEFAULTED - nobody supplied it, so the ledger's own default decided the
    fork. That is the mechanical reading of 9.8's "a node whose condition you
    cannot evaluate": the engine can always produce an answer, and this is the
    set of places where the answer was produced out of nothing.
    """
    entries: list[Unevaluable] = []
    seen: set[tuple[str, str]] = set()

    for entry in result.path:
        key = (entry.id, entry.row or "")
        if key in seen:
            continue
        seen.add(key)

        read = facts_read_by(entry, result) - facts_guarded_by_measured(entry)
        # DEFAULTED, AND NOBODY HAS WRITTEN OVER THE LEDGER'S OWN DEFAULT.
        #
        # `full_defaults` writes its answers at rank zero on purpose, so a
        # person's word beats them by being said - which means a fact the
        # harness has just settled still reads DEFAULTED, and asking for it
        # again is how a Full thread that HAD its bar computed was told
        # "Blocked on `target_score`" on the very next walk.
        #
        # THE TEST IS AGAINST THE DECLARED DEFAULT, NOT AGAINST NONE, and the
        # first cut got that wrong. `eval_size_n` is `default: 0`, so "has a
        # value" was true of a count nobody had taken and the eval set fell
        # off the frontier entirely - three tests said so in the same breath.
        # A fact whose value still equals what the ledger says it is when
        # unanswered is unanswered. `full_defaults._is_open` draws the same
        # line for the four facts whose declared default happens to be null.
        values = getattr(result, "fact_values", {}) or {}

        def _still_unanswered(name: str) -> bool:
            if result.fact_origins.get(name, DEFAULTED) != DEFAULTED:
                return False
            value = values.get(name)
            if value is None:
                return True
            declared = (_spec().facts.get(name) or {})
            return "default" in declared and value == declared["default"]

        unknown = tuple(sorted(f for f in read if _still_unanswered(f)))
        if not unknown:
            continue

        why = _because_for(entry, result)
        cards = [question_for(name, why) for name in unknown]
        questions = rank([c for c in cards if isinstance(c, Question)])
        gaps = tuple(c for c in cards if isinstance(c, Gap))
        questions = tuple(_with_company(card, questions) for card in questions)

        entries.append(
            Unevaluable(
                entry=entry.id,
                kind="gate" if entry.kind == "gate" or entry.id in _gate_nodes() else "node",
                because=why,
                unknown=unknown,
                questions=questions,
                gaps=gaps,
            )
        )

    return Frontier(outcome=result.outcome, verdict=result.verdict, entries=tuple(entries))


def _with_company(card: Question, cards: Sequence[Question]) -> Question:
    """What else one run of the same instrument would settle here.

    Only for pointer cards, and only within one frontier entry. Pointing at a
    folder once and getting four facts back is one act by the person, and a
    surface that made them do it four times would be a form again.
    """
    if not card.points:
        return card
    company = tuple(
        other.fact
        for other in cards
        if other.fact != card.fact and other.answered_by == card.answered_by
    )
    if not company:
        return card
    return Question(
        fact=card.fact,
        answer=card.answer,
        arrives_as=card.arrives_as,
        accepts=card.accepts,
        declared=card.declared,
        because=card.because,
        settled_by=card.settled_by,
        dont_know=card.dont_know,
        decides=card.decides,
        decides_by=card.decides_by,
        slots=card.slots,
        also_settles=company,
    )


def next_question(result: Diagnosis) -> Question | None:
    """Exactly one card, or none. Step 5 of 9.8, and the word is *exactly*.

    A form asks six. Six questions from something claiming to have looked at the
    machine reads as something that has not looked at anything, and the whole
    reason this product's advice can beat a control panel's is that it looked
    first.
    """
    entry = frontier(result).first_answerable
    return entry.questions[0] if entry is not None else None


# ---------------------------------------------------------------------------
# Assumptions, which is how "I don't know" comes back.


@dataclass(frozen=True)
class Assumption:
    """A fact the walk read and nobody supplied. It appears on the next verdict."""

    fact: str
    took: Any
    origin: str
    read_at: tuple[str, ...]
    declared: dict[str, Any]
    settled_by: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "fact": self.fact,
            "took": self.took,
            "origin": self.origin,
            "read_at": list(self.read_at),
            "declared": dict(self.declared),
            "settled_by": dict(self.settled_by),
        }


def assumptions(result: Diagnosis) -> tuple[Assumption, ...]:
    """Every default this run leaned on, with where it leaned.

    THE FILTER IS "READ", NOT "DEFAULTED". Sixty-odd facts are DEFAULTED in a
    run that supplied three, and listing all of them as assumptions would bury
    the four that actually decided something. A fact only becomes an assumption
    when a condition on the walked path read it, which is the difference between
    "we do not know this" and "we did not know this and answered anyway".
    """
    where: dict[str, list[str]] = {}
    for entry in result.path:
        for name in sorted(facts_read_by(entry, result)):
            if result.fact_origins.get(name, DEFAULTED) != DEFAULTED:
                continue
            seen = where.setdefault(name, [])
            if entry.id not in seen:
                seen.append(entry.id)

    spec = _spec()
    return tuple(
        Assumption(
            fact=name,
            took=diagnosis.unsupplied_value(spec.facts[name]),
            origin=DEFAULTED,
            read_at=tuple(read_at),
            declared=_declared(name),
            settled_by=dict(evidence.resolves(name)),
        )
        for name, read_at in sorted(where.items())
    )


# ---------------------------------------------------------------------------
# When the questions run out.


@dataclass(frozen=True)
class Proposal:
    """No more questions. Here is what happens next, and who does it.

    `covered` and `why_not` are read from `app/tools/propose.py`'s own
    `PROPOSERS` and `NOT_COVERED`, so a proposer written next week flips this to
    True without anything here being edited - and an outcome that module
    honestly refuses to plan for keeps its refusal, in that module's words. A
    copy of either list here would be a promise about a build this product
    cannot run, which is the one thing `propose.py` exists to refuse.
    """

    outcome: str
    verdict: str
    say: str
    build_with: str
    covered: bool
    how: str = ""
    why_not: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "verdict": self.verdict,
            "say": self.say,
            "build_with": self.build_with,
            "covered": self.covered,
            "how": self.how,
            "why_not": self.why_not,
        }


#: The tool that turns an outcome into a Build. Named once.
BUILD_TOOL = "propose_build"


def proposal_for(result: Diagnosis) -> Proposal:
    """What the surface does instead of asking another question."""
    from app.tools import propose as proposing  # local: propose imports the registry

    outcome = result.outcome
    covered = outcome in proposing.PROPOSERS
    return Proposal(
        outcome=outcome,
        verdict=result.verdict,
        say=_line(result.say),
        build_with=BUILD_TOOL,
        covered=covered,
        how=_line(proposing.COVERAGE.get(outcome, "")) if covered else "",
        why_not="" if covered else _line(proposing.NOT_COVERED.get(outcome, "")),
    )


QUESTION = "question"
PROPOSE = "propose"


@dataclass(frozen=True)
class NextStep:
    """Ask this, or propose that. Never both, and never neither."""

    kind: str
    outcome: str
    verdict: str
    frontier: Frontier
    assumptions: tuple[Assumption, ...] = ()
    question: Question | None = None
    proposal: Proposal | None = None

    def __post_init__(self) -> None:
        if self.kind == QUESTION and self.question is None:
            raise AskingError("a question step with no question")
        if self.kind == PROPOSE and self.proposal is None:
            raise AskingError("a propose step with no proposal")
        if self.kind not in (QUESTION, PROPOSE):
            raise AskingError(f"{self.kind!r} is not a step this module produces")

    @property
    def is_question(self) -> bool:
        return self.kind == QUESTION

    @property
    def is_build(self) -> bool:
        return self.kind == PROPOSE

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "outcome": self.outcome,
            "verdict": self.verdict,
            "question": self.question.as_dict() if self.question else None,
            "proposal": self.proposal.as_dict() if self.proposal else None,
            "assumptions": [a.as_dict() for a in self.assumptions],
            "frontier": self.frontier.as_dict(),
        }


def next_step(
    facts: Mapping[str, Any] | None = None, *, result: Diagnosis | None = None
) -> NextStep:
    """The whole surface in one call: ask one thing, or start proposing.

    Pure. It runs the engine over the facts it was handed - or reads a diagnosis
    somebody already ran - and returns cards. It records nothing, calls no tool,
    opens no file and opens no gate. Answering a card is a tool call made by
    somebody else, through the boundary where the actor decides what the answer
    is worth, which is the only place that decision can honestly be made.
    """
    if result is None:
        result = diagnosis.diagnose(dict(facts or {}))

    edge = frontier(result)
    assumed = assumptions(result)
    card = next_question(result)

    if card is not None:
        return NextStep(
            kind=QUESTION,
            outcome=result.outcome,
            verdict=result.verdict,
            frontier=edge,
            assumptions=assumed,
            question=card,
        )

    return NextStep(
        kind=PROPOSE,
        outcome=result.outcome,
        verdict=result.verdict,
        frontier=edge,
        assumptions=assumed,
        proposal=proposal_for(result),
    )


__all__ = [
    "ANSWERS",
    "AskingError",
    "Assumption",
    "Because",
    "BUILD_TOOL",
    "CHOICE",
    "CHOICES",
    "DECIDES_BY",
    "DontKnow",
    "Frontier",
    "Gap",
    "MACHINE",
    "NUMBER",
    "NextStep",
    "POINTER",
    "POINTED_ANSWER_ARRIVES_AS",
    "POINTING_ANSWERS",
    "PROPOSE",
    "Proposal",
    "QUESTION",
    "Question",
    "Slot",
    "TEXT",
    "TYPED_ANSWERS",
    "TYPED_ANSWER_ARRIVES_AS",
    "Unevaluable",
    "YES_NO",
    "assumptions",
    "decides",
    "decision_points",
    "facts_read_by",
    "frontier",
    "next_question",
    "next_step",
    "proposal_for",
    "question_for",
    "rank",
]
