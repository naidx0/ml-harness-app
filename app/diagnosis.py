"""The diagnosis engine: the five-gate honesty test, executed instead of asserted.

`docs/diagnosis_engine.yaml` states an invariant in prose: no user is ever told
to train unless all five gates have been passed on the path that reached the
recommendation, and every outcome the file declares must be reachable by some
consistent set of facts. Prose cannot fail a build. This module is the
mechanical form of that sentence, so the test suite can.

THE REACHABILITY HALF IS NOT ABOUT TRAINING. It was read that way once - scoped
to the nine `TRAIN__` outcomes - and under that scope a widened condition killed
NO_LLM__SETFIT, NO_LLM__ENCODER_FINETUNE and a reroute without a single test
going red. A dead no-train outcome is an answer the product claims it can give
and cannot, and the no-train answers are the product. `Spec.declared_outcomes()`
is what the test now iterates, and it covers every prefix.

THE ENGINE KNOWS NOTHING ABOUT MACHINE LEARNING, AND AS OF THIS PASS THAT IS
TRUE RATHER THAN ASPIRATIONAL. Six names used to be Python constants holding the
first ledger's choices: `ENTRY_STAGE`, `STAGE_9`, `UNSET`, the literal `TRAIN__`
inside SC1, the verdict string `"TRAIN"` in the exit check, and the same prefix
again in the origin policy's refusal. Every one of them is a NAME, and not one of
them is a RULE. They are declared by the ledger now, in `contract.roles` and
`contract.outcome_prefixes`, under one sentence:

    THE LEDGER OWNS EVERY NAME. THE ENGINE OWNS EVERY RULE ABOUT NAMES.

A ledger may call its commit stage `stage_9_shape_selector`; it may not choose
whether a proposal has to reach one. It may name its irreversible prefix
`BUILD__`; it may not choose whether that prefix requires every gate. It may
write a fork's table; it may not write the fork's algorithm - `select:` is a
closed vocabulary this file owns.

The consequence worth stating: `docs/ledgers/ai_engineering.yaml` diagnoses on
this engine with no Python of its own, and it deliberately spells every one of
those names differently, so a constant left behind here cannot pass by
coincidence. See tests/test_a_second_ledger_runs_on_this_engine.py.

Two public entry points:

  `load_spec(path)`   reads and VALIDATES the YAML. A malformed spec raises
                      `SpecError` at load time. It does not degrade, does not
                      skip what it cannot parse, and does not guess. In
                      particular, a node the engine has no way to execute is a
                      load-time error, not a node that is silently ignored -
                      silently-ignored nodes are how four training outcomes came
                      to be dead while the file claimed all nine were gated.

  `diagnose(facts)`   walks the tree. Pure: no file I/O, no network, no GPU, no
                      model call, no clock, no randomness. It reads a fact dict
                      and the loaded spec and returns a `Diagnosis`.

WHY `diagnose` TAKES A PLAIN DICT AND NOTHING ELSE. The product will eventually
let a user's own model FILL facts - read a repo, count an eval set, bucket
failures. It must never let a model DECIDE a gate. That is kept true by
construction here: `validate_facts` rejects any fact value that is callable, so
there is no way to hand the engine something it will ask at gate time. A gate is
evaluated by `_Evaluator` against the `requires` string in the YAML and against
values that are already sitting in the dict. Filling is upstream. Deciding is
here, and it is not pluggable.

AND FILLING WAS NOT INNOCENT EITHER, which is the wall this module gained last.
A model that cannot decide a gate can still SUPPLY the fact the gate reads, and
a provider that merely claimed eval_size_n, baseline_measured, baseline_score,
prompt_iterations, retrieval_tried and model_swap_tried got TRAIN__LORA_SFT with
all five gates green. Every structural check passed while it happened, because
every structural check is about the shape of the graph. So a fact is no longer a
bare value: it is a value and an ORIGIN, and a gate may only be opened by an
origin the ledger's own `source:` tag admits. See `Fact` below and the
`fact_origins` block of the spec, which is where the policy lives and where the
argument for it is written down. A bare value is an ASSERTED value - the engine
never guesses a provenance upward - so the channel that matters, a JSON object
from the user's own model, fails closed without any boundary code remembering to
do anything.

WHY PyYAML AND NOT A STDLIB PARSER. Declared in `pyproject.toml` as its own
dependency, deliberately, per the repo rule. The spec file uses folded and
literal block scalars, flow mappings inside block sequences, nested sequences of
mappings, and quoted strings containing colons and braces. A hand-rolled subset
parser would have to get all of that right to be trusted, and the failure mode
of getting it subtly wrong is the worst one available to this file: a condition
that parses into something slightly different from what the author wrote, in the
one document whose whole job is to be exactly what the author wrote. PyYAML is
mature, pure-Python, and already the de facto standard. `yaml.safe_load` is used
- never `yaml.load` - so the document cannot construct Python objects.

WHAT THIS MODULE DOES NOT DO. It does not render, price, or plan. It answers one
question - what should this user do - and shows its work in `path`.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import yaml

#: Where the ledgers actually are on THIS installation.
#:
#: In a checkout that is the repository root, and `docs/diagnosis_engine.yaml`
#: sits under it exactly as it is written down. In an installed package there is
#: no repository, so the build copies `docs/` into `app/_bundled/` and this
#: returns that instead - see `setup.py`. **The `docs/` segment is preserved on
#: purpose**: every stored name (`threads.ledger`, every refusal that quotes a
#: path, every row in a database that already exists) is relative to this root,
#: so keeping the shape keeps those names byte-identical across a checkout and
#: an install. A bundle that flattened the path would silently orphan every
#: thread.
#:
#: THIS IS NOT TWO PLACES A LEDGER MAY LIVE. `docs/` is the source and the only
#: thing a person edits; `app/_bundled/` is a build artifact, generated, and
#: absent from the tree. The checkout branch is taken whenever it exists, so a
#: developer can never be reading a stale copy of their own edit.
def _ledger_root() -> Path:
    # THE REPOSITORY WINS WHENEVER IT IS THERE, and the order matters more than
    # it looks. The first version of this preferred the bundle whenever it
    # existed - and building a wheel in a checkout CREATES one, so the next
    # engine started in that tree read the generated copy and ignored every
    # edit to `docs/`. Caught by this function's own test, which is the hazard
    # it was written for.
    here = Path(__file__).resolve()
    repository = here.parents[1]
    if (repository / "docs" / "diagnosis_engine.yaml").is_file():
        return repository
    return here.parent / "_bundled"


LEDGER_ROOT = _ledger_root()

SPEC_PATH = LEDGER_ROOT / "docs" / "diagnosis_engine.yaml"

#: The grammar this engine executes. Owned by the ENGINE, not by a ledger's
#: author - see `ledger_format` versus `ledger_version` in `_read_format`.
CURRENT_LEDGER_FORMAT = 3

#: Formats this engine can read. Anything older is read by UPGRADING it to
#: CURRENT_LEDGER_FORMAT first; the validator and the walk only ever see the
#: current one. Anything newer is REFUSED - never best-effort. A gate table half
#: understood is the honesty test defeated by a shrug.
SUPPORTED_LEDGER_FORMATS = (2, 3)

NODE_ID_RE = re.compile(r"^S[0-9]+_")
GATE_ID_RE = re.compile(r"^G[0-9]_")

#: The `select:` vocabulary a fork may name. CLOSED, AND THE ENGINE OWNS IT.
#: A ledger picks a strategy from this list and writes the table; it never
#: writes the strategy. Adding a third entry is an engine change with a test,
#: which is exactly the cost it should carry. (This is DMN's hit policy, and the
#: reason to copy DMN is that it has let non-programmers write decision tables
#: for a decade without letting them write hit-policy code.)
FORK_SELECTORS = ("value", "argmax")

# How many stage entries before we call it a runaway. `cycle_guard` in the spec
# stops at the third entry of any one stage; this is the belt-and-braces bound
# on the whole walk so a bug cannot spin forever.
MAX_STAGE_ENTRIES = 64


class SpecError(Exception):
    """The spec file is malformed, or says something the engine cannot execute."""


class LedgerError(SpecError):
    """A refusal an AUTHOR can act on: where it is, what was expected, what to do.

    A SpecError, so every existing caller and test keeps working. What it adds
    is the four things a message with none of them cannot give a person who did
    not write this engine: the document and line, the rule that objected, and
    the edit that would fix it.

    THE CHECK ID IS NOT BUREAUCRACY. It is what lets the conformance suite
    assert on a stable identifier while the message text keeps improving. A
    suite that asserts on prose is a suite that punishes anyone who makes an
    error message clearer.

    THIS DOES NOT APPLY ITSELF TO THE 62 `_require` CALLS THAT PREDATE IT. Those
    are the first ledger's own load-time checks and they work; converting them is
    step 4 of docs/LEDGER_FORMAT.md's migration path and it is a pass of its own.
    What is carried here is every check a SECOND ledger's author can actually
    trip - the format version, the roles block, the fork schema, the prefixes -
    because those are the ones that will be read by somebody who has never
    opened this file.
    """

    def __init__(
        self,
        check_id: str,
        message: str,
        *,
        where: str | None = None,
        document: Path | str | None = None,
        line: int | None = None,
        expected: str | None = None,
        found: str | None = None,
        remedy: str | None = None,
    ) -> None:
        self.check_id = check_id
        self.where = where
        self.document = None if document is None else str(document)
        self.line = line
        self.expected = expected
        self.found = found
        self.remedy = remedy
        head = self.document or "<ledger>"
        if line is not None:
            head = f"{head}:{line}"
        lines = [f"{head}  [{check_id}]"]
        lines.append(f"  {where}: {message}" if where else f"  {message}")
        for label, value in (("expected", expected), ("found", found), ("remedy", remedy)):
            if value:
                lines.append(f"  {label}: {value}")
        super().__init__("\n".join(lines))


class FactError(ValueError):
    """The caller handed in facts the ledger does not describe."""


class EngineError(Exception):
    """An engine bug. The spec's ERROR__ prefixes raise; they never render."""


# ---------------------------------------------------------------------------
# Origins. A fact is a value AND where the value came from.
#
# The four names and the argument for four rather than three are in the spec's
# `fact_origins.vocabulary`; they are read back out of the file at load time and
# checked against these constants, so the two cannot drift apart silently.

MEASURED = "MEASURED"
STATED = "STATED"
ASSERTED = "ASSERTED"
DEFAULTED = "DEFAULTED"

ORIGINS = (MEASURED, STATED, ASSERTED, DEFAULTED)

#: The one origin a caller may never claim. DEFAULTED means "the engine applied
#: the ledger's own default", and only the engine is entitled to say that.
ENGINE_ONLY_ORIGINS = frozenset({DEFAULTED})


@dataclass(frozen=True)
class Fact:
    """A value that knows where it came from.

    Anywhere the engine accepts a fact value it also accepts one of these. A
    BARE VALUE IS AN ASSERTION - see `fact_origins.why_unattributed_is_asserted`
    in the spec - so wrapping is the deliberate act and leaving a value bare is
    the safe default rather than the convenient one.

    `Fact(None, MEASURED)` is a value nobody has, and it resolves the same way an
    absent key does: through the ledger's default, origin DEFAULTED. "The tool
    ran and found nothing" and "the tool did not run" are the same state of
    knowledge about the number, and stamping the first one MEASURED would put a
    provenance badge on an empty field.
    """

    value: Any
    origin: str

    def __post_init__(self) -> None:
        if self.origin not in ORIGINS:
            raise FactError(
                f"{self.origin!r} is not a fact origin. The vocabulary is "
                f"{', '.join(ORIGINS)}, and it is declared in "
                "docs/diagnosis_engine.yaml under fact_origins.vocabulary."
            )


def measured(value: Any) -> Fact:
    """A tool ran and the engine watched it produce this."""
    return Fact(value, MEASURED)


def stated(value: Any) -> Fact:
    """The user said so, in their own person."""
    return Fact(value, STATED)


def asserted(value: Any) -> Fact:
    """A model said so, or nobody said where it came from."""
    return Fact(value, ASSERTED)


@dataclass(frozen=True)
class Settled(Fact):
    """A DEFAULTED value the engine applied by a RULE rather than from the file.

    `DEFAULTED` has always meant "nobody supplied this, so the ledger's own
    default was used", and `ENGINE_ONLY_ORIGINS` exists because only the engine
    is entitled to say that. That refusal still stands for every caller, and
    `resolve_facts` still raises on a plain `Fact(value, DEFAULTED)`.

    THIS IS THE SECOND WAY A DEFAULT CAN BE APPLIED, and it needed a carrier
    rather than a fifth origin word. Under permission `full` the harness settles
    an ask-fact from a written rule - see `app/full_defaults.py` - and records
    the answer with `how` saying which rule and which numbers. That is the
    ledger's default for THIS thread, arrived at by arithmetic instead of by
    the file's `default:` key, and it is neither MEASURED (no instrument read
    it), nor STATED (the person did not say it), nor ASSERTED (no model claimed
    it). It is the engine's own default and the origin word stays DEFAULTED, so
    a card that shows the provenance shows the weakest word on the sheet and a
    later STATED row from the person outranks it without anything special.

    A CLASS AND NOT A FLAG, because the wall has to be mechanical. A model
    reaches this engine through JSON; JSON cannot carry a Python class, so no
    argument a model sends can ever arrive as a `Settled`. The only producer is
    `evidence.assemble_facts`, reading a row that `evidence.record` would only
    write for the harness itself.
    """

    #: The rule and the numbers it used, carried through from the ledger row so
    #: the sentence a person reads is the one that was recorded, not one
    #: rebuilt later from the value.
    how: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.origin != DEFAULTED:
            raise FactError(
                f"a Settled fact was built with origin {self.origin!r}. Settled is "
                f"how the engine carries its OWN default, so its origin is "
                f"{DEFAULTED} and nothing else."
            )


def settled(value: Any, how: str = "") -> Settled:
    """The engine applied a rule, and `how` is the rule and its numbers."""
    return Settled(value, DEFAULTED, how)


# ---------------------------------------------------------------------------
# The audit trail.


@dataclass(frozen=True)
class PathEntry:
    """One record in `path`, exactly as contract.path_semantics.PathEntry defines it.

    `row` is set only on gate entries. It is the `method_class` key of the
    `passes_when` row that evaluated true; without it a gate passed under one
    method class is indistinguishable from a gate passed under another, and that
    indistinguishability was the live bypass this shape exists to close.

    `clause` IS THE CONDITION THE ENTRY WAS DECIDED BY, ON BOTH KINDS. On a gate
    entry it is the row's `requires` string. On a node entry it is that node's
    own `condition:`, verbatim from the file.

    IT USED TO BE NULL ON NODES, AND THAT COST THE MOST COMMON EARLY ANSWER ITS
    QUESTION. A run that stops above the gate tree - the empty sheet reaches
    `BLOCKED__DEFINE_SUCCESS_FIRST` two nodes in - passes no gate and fails none,
    so every row of `gate_ledger` is NOT_REACHED with `clause: null`, and a
    surface that derives its question from the frontier's clause had nothing at
    all to read. The condition was parsed at load time and sitting in
    `Spec.conditions` the whole while; the wire simply did not carry it. Now the
    path says what each node was asked, which is the same thing the gate entries
    have always said about gates.

    NULL SURVIVES IN EXACTLY ONE PLACE, AND IT IS HONEST THERE. A gate's own node
    - `S0_NO_EVAL_SET`, `S1_UNMEASURED` and the other three - lives in the
    `gates:` block, not in a stage, and has no `condition:` of its own; what gets
    evaluated at that point is the gate row, which is the gate's property and is
    already recorded on the gate entry that follows. Writing the row's `requires`
    onto the node would be this file inventing a condition the node does not
    have, so those entries keep a null and the reason is here rather than in a
    reviewer's memory.
    """

    id: str
    kind: str  # "node" | "gate"
    row: str | None = None
    clause: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "row": self.row, "clause": self.clause}


@dataclass(frozen=True)
class OutcomeSite:
    """One place in a ledger document where an outcome string is stated.

    `Spec.outcome_sites()` returns these and is the ONLY enumeration of them.
    `node` is the node id the site sits in, or None for a gate's `on_fail` and
    for `fact_origins.unsubstantiated_outcome`, which are not in the graph.
    `where` is prose for an error message and is never parsed.
    """

    outcome: str
    node: str | None
    where: str


@dataclass(frozen=True)
class GateReading:
    """One gate row, found by the fact its condition reads. See `Spec.gate_reading`.

    Both the gate and the row come back, because the two hold different halves
    of what a tool needs and a caller that got only one went and looked the
    other up by id. The gate carries `asks`, `on_fail` and
    `what_counts_as_the_baseline`; the row carries `requires`, which is where a
    threshold lives. `gate_id` and `row_key` are here so a tool can ATTRIBUTE
    what it read - "G0_EVAL_SET.passes_when in <this ledger>" - rather than
    print a number with no address, which invariant 3 forbids.
    """

    gate_id: str
    gate: dict[str, Any]
    row_key: str
    row: dict[str, Any]


@dataclass
class Diagnosis:
    outcome: str
    verdict: str
    path: list[PathEntry]
    gate_ledger: dict[str, dict[str, Any]]
    proposed_method: str
    rejected: list[dict[str, Any]]
    struck_methods: set[str]
    constraints: set[str]
    helper_answers: list[dict[str, Any]]
    size_row: dict[str, Any] | None
    route: str | None
    hardware_permits: bool | None
    hardware_reference: dict[str, Any] | None
    cost_provenance: str
    node: str
    say: str | None = None
    #: Every declared fact, mapped to the origin the value carried in this run.
    #: Invariant 3 says a number with no provenance does not get displayed; this
    #: is where the renderer gets the provenance for every number, not only for
    #: the four hardware ones `cost_provenance` used to cover.
    fact_origins: dict[str, str] = field(default_factory=dict)
    #: One row per fact that was load-bearing for a gate and whose origin the
    #: ledger does not admit. Empty on every other run. Each row carries the
    #: fact, the gate that refused, the `source:` the ledger declares, the origin
    #: the value actually had, and the substantiation line read off the spec.
    unsubstantiated: list[dict[str, Any]] = field(default_factory=list)
    #: THE VALUE BESIDE THE ORIGIN, because the two answer different questions
    #: and `fact_origins` alone cannot tell "nobody has said" from "a rule
    #: said, weakly". Both are DEFAULTED - that is the whole point of
    #: `app/full_defaults.py` writing at rank zero so the person overrules it
    #: by simply speaking - and `app/asking.py` was treating every DEFAULTED
    #: fact as unanswered, so a bar Full had just computed was asked for again
    #: on the very next walk. Compared to nothing and carried for the asker.
    fact_values: dict[str, Any] = field(default_factory=dict, compare=False)
    #: node id -> the declared facts that node's condition ACTUALLY READ.
    #:
    #: NOT ON `PathEntry`, because `contract.path_semantics` fixes that shape
    #: and a reader depending on a field the engine keeps for its own asker
    #: would turn it into a promise. `and` short-circuits, so `task_family in
    #: {extraction, classification} and ... classes_n <= 5` reads `classes_n`
    #: on a classification thread and not on a generation one - while a parse
    #: of the expression names it either way, which is what `app/asking.py`
    #: built its question from. Measured 2026-09-19: a generation thread was
    #: told "Blocked on `classes_n`. Run assess_the_data" by a node that had
    #: already answered False without looking at it, and forty minutes of a
    #: real run went into that question.
    #:
    #: A node absent from this map recorded nothing - a handler node, an
    #: `always`, a gate row - and the caller falls back to the parse, which is
    #: right for a gate row: every fact in a `requires` string counts.
    reached_by: dict[str, tuple[str, ...]] = field(default_factory=dict, compare=False)
    #: THE LEDGER THIS VERDICT WAS COMPUTED FROM, carried on the answer rather
    #: than looked up again by whoever reads it.
    #:
    #: `app/tools/propose.py` is 9,800 lines of code that takes a `Diagnosis`
    #: and plans work for it, and every one of its own spec reads went to
    #: `default_spec()` - so a verdict minted from one ledger was planned
    #: against another, and nothing in either half could tell. The fix that
    #: scales is not a second channel into every function: it is that AN ANSWER
    #: CARRIES THE KNOWLEDGE IT WAS COMPUTED FROM, so every consumer of a
    #: diagnosis already holds the right ledger and cannot reach a different one
    #: by accident.
    #:
    #: `compare=False, repr=False` because a `Spec` is 3,468 lines of parsed
    #: YAML: two diagnoses are the same answer when they say the same thing, and
    #: a test that prints one should print the verdict, not the ledger.
    #: `None` only for a `Diagnosis` some test built by hand; `diagnose()`
    #: always fills it.
    spec: "Spec | None" = field(default=None, compare=False, repr=False)

    def path_ids(self) -> list[str]:
        return [e.id for e in self.path]


# ---------------------------------------------------------------------------
# The condition language.
#
# Conditions in the spec are written for a human first: `need_type contains
# cost`, `is null`, `ALL of: A AND B`, bare enum words inside set literals. They
# are close enough to Python that a normalizer plus a restricted evaluator can
# run them, and running the author's own strings is the point - the alternative
# is a second copy of every condition in Python, which is a drift machine.


def _normalize(expr: str) -> str:
    """Rewrite the spec's dialect into something `ast.parse` accepts.

    The `contains` right operand is turned into a STRING LITERAL, not a name.
    This matters: `need_type contains privacy` names the `privacy` member of the
    need_type enum, and `privacy` is also a fact. Resolving it as a fact would
    compare need_type against "public_ok" and quietly answer the wrong question.
    """
    s = " ".join(expr.split())
    s = s.replace("ALL of:", " ")
    s = re.sub(r"\bAND\b", "and", s)
    s = re.sub(r"\bOR\b", "or", s)
    s = re.sub(r"\bNOT\b", "not", s)
    s = re.sub(r"\bis not null\b", "is not None", s)
    s = re.sub(r"\bis null\b", "is None", s)
    s = re.sub(r"\btrue\b", "True", s)
    s = re.sub(r"\bfalse\b", "False", s)
    s = re.sub(
        r"([A-Za-z_][A-Za-z0-9_.]*)\s+contains\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"contains(\1, '\2')",
        s,
    )
    return s


def compile_condition(expr: str) -> ast.expr:
    normalized = _normalize(expr)
    try:
        return ast.parse(normalized, mode="eval").body
    except SyntaxError as exc:
        raise SpecError(f"condition does not parse: {expr!r} -> {normalized!r} ({exc})") from exc


_ALLOWED_AST = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.Compare,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Set,
    ast.Tuple,
    ast.List,
    ast.Attribute,
    ast.GeneratorExp,
    ast.ListComp,
    ast.comprehension,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
)


def _names_used(tree: ast.expr) -> tuple[set[str], set[str], set[str]]:
    """Return (value names, called names, attribute roots) in an expression.

    Set-literal members and `contains` literals are excluded from value names:
    in this dialect they are bare enum words, never fact lookups.
    """
    values: set[str] = set()
    called: set[str] = set()
    roots: set[str] = set()
    bound: set[str] = set()

    class Walker(ast.NodeVisitor):
        def visit(self, node: ast.AST) -> Any:
            if not isinstance(node, _ALLOWED_AST):
                raise SpecError(f"condition uses unsupported syntax: {type(node).__name__}")
            return super().visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            # KEYWORDS ARE REFUSED, NOT WALKED, AND NOT IGNORED EITHER.
            # This visited `node.func` and `node.args` and nothing else, so a
            # keyword slot was a hole in BOTH halves of the sandbox at once:
            # `sum(x, start=lambda: 1)` never met the AST allowlist, and
            # `sum(x, start=undeclared_fact)` never met the undeclared-name
            # check. The evaluator's own `visit_Call` reads `node.args` too, so
            # nothing in a keyword ever ran - which made this a silent-drop bug
            # rather than an execution one, and silent-drop is the class this
            # file refuses everywhere else. An author who wrote `len(x, default=0)`
            # got no error and no default.
            if node.keywords:
                raise SpecError(
                    "condition uses a keyword argument, which this dialect does not "
                    "have: the engine's functions take positional arguments only, and "
                    "a keyword would be accepted and then dropped"
                )
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            else:
                self.visit(node.func)
            for arg in node.args:
                self.visit(arg)

        def visit_Set(self, node: ast.Set) -> None:
            for elt in node.elts:
                if not isinstance(elt, (ast.Name, ast.Constant)):
                    self.visit(elt)

        def visit_Attribute(self, node: ast.Attribute) -> None:
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                roots.add(base.id)
            else:
                self.visit(base)

        def visit_comprehension(self, node: ast.comprehension) -> None:
            if isinstance(node.target, ast.Name):
                bound.add(node.target.id)
            self.visit(node.iter)
            for cond in node.ifs:
                self.visit(cond)

        def visit_Name(self, node: ast.Name) -> None:
            values.add(node.id)

    Walker().visit(tree)
    return values - bound, called, roots


# ---------------------------------------------------------------------------
# The loaded spec.


@dataclass(frozen=True)
class Roles:
    """The names the ENGINE must find, declared by the LEDGER that owns them.

    THE RULE THIS BLOCK EXISTS TO STATE: the ledger owns every NAME, the engine
    owns every RULE ABOUT NAMES. A ledger may call its commit stage
    `stage_9_shape_selector`; it may not choose whether a proposal has to reach
    one. It may name its irreversible prefix `BUILD__`; it may not choose whether
    that prefix requires every gate.

    Before this block, four of these were Python constants spelling the FIRST
    ledger's choices - `ENTRY_STAGE = "stage_0_admissibility"`,
    `STAGE_9 = "stage_9_method_selector"`, `UNSET = "UNSET"`, and the literal
    `"TRAIN__"` sitting inside SC1. A second ledger could not satisfy them and
    should never have had to: every one of them is a name, and not one of them is
    a rule. `docs/VISION.md` had already said so about the last one - *"which is
    not an ML concept but a role: the expensive irreversible outcome that must
    pass every gate."*

    `commit_stages` IS A LIST AND IT MUST BE WRITTEN EVEN WHEN EMPTY. The
    difference between "this domain has no irreversible outcome" and "somebody
    forgot" is the whole honesty test, and a default would erase it. A ledger
    that writes `commit_stages: []` is a triage ledger that only routes; the
    engine then refuses any `propose:` and any gated prefix, and says the ledger
    declared itself non-committing. That is a real ledger, not a degenerate one -
    and it says so out loud, where a reviewer sees it in a diff.
    """

    entry_stage: str
    #: Zero or more. The stages where a CANDIDATE BECOMES A VERDICT.
    #: Deliberately not `terminal_stages`: every stage in the ML ledger is
    #: terminal - all ten end at least one outcome, and stage_8_classical ends
    #: twelve - so "terminal stage" names nothing. What SC2 has always been
    #: guarding is where a proposal turns into an answer.
    commit_stages: tuple[str, ...]
    #: The sentinel meaning "no proposal has been made yet". `UNSET` in the ML
    #: ledger; a ledger with no methods still has to name one.
    no_proposal: str
    #: The node that re-asks every required gate under the proposal's real class
    #: before anything mints. NOT an ML computation - it is a piece of the
    #: honesty test - so it is bound by a declared name rather than by node id.
    gate_sweep_node: str | None = None


@dataclass
class Spec:
    raw: dict[str, Any]
    path: Path
    facts: dict[str, dict[str, Any]]
    methods: dict[str, dict[str, Any]]
    gates: dict[str, dict[str, Any]]
    stages: dict[str, list[dict[str, Any]]]
    contract: dict[str, Any]
    required_gates: list[str]
    node_index: dict[str, dict[str, Any]]
    node_stage: dict[str, str]
    literals: set[str]
    conditions: dict[str, ast.expr]
    gate_conditions: dict[tuple[str, str], ast.expr]
    method_classes: set[str]
    train_outcomes: list[str]
    #: The `fact_origins` block, verbatim.
    origin_policy: dict[str, Any]
    #: ledger `source:` value -> the origins that may satisfy a gate reading a
    #: fact with that source. Read out of fact_origins.admissible_for_gates.
    admissible_origins: dict[str, frozenset[str]]
    #: (gate_id, row_key) -> the declared facts that row's condition READS.
    #: Parsed out of the `requires` string with the engine's own compiler at load
    #: time. Nothing anywhere writes this list down; that is the whole point of
    #: deriving it, because a fact added to a gate row next year is covered on
    #: the day it is added and not on the day somebody remembers.
    gate_row_facts: dict[tuple[str, str], frozenset[str]]
    #: contract.roles, read out of the file. See `Roles`.
    roles: Roles
    #: The ledger format the document was written in, BEFORE any upgrade. Kept
    #: so a reader can tell a format-2 document that was upgraded from a
    #: format-3 document that was written that way.
    ledger_format: int
    #: The one prefix declared `gated: all` - the expensive irreversible outcome
    #: that must pass every gate. None when the ledger declares no such prefix,
    #: which is legal only when `roles.commit_stages` is empty.
    gated_prefix: str | None = None
    #: The single node the gated prefix's `mintable_only_at:` names.
    mint_node: str | None = None
    #: Top-level (and one level in) key -> the line it is declared on. For error
    #: messages only; the engine never routes on it.
    line_of: dict[str, int] = field(default_factory=dict)

    # -- pure lookups the spec defines and the engine and tests both need -----

    @property
    def as_written(self) -> str:
        """How to name this ledger in a sentence somebody reads: its stored path.

        `docs/diagnosis_engine.yaml`, never the absolute spelling and never the
        bare file name. THE SAME STRING `threads.ledger` STORES, so a refusal
        that names the ledger names something the reader can look up and
        something the database could hold - and a person reading two messages
        from two layers sees one name for one file. A ledger outside the
        repository is named as given, because there is nothing to make it
        relative to.
        """
        try:
            return self.path.relative_to(LEDGER_ROOT).as_posix()
        except ValueError:
            return str(self.path)

    @property
    def no_proposal(self) -> str:
        """The ledger's own name for "nothing proposed yet"."""
        return self.roles.no_proposal

    @property
    def gated_outcomes(self) -> list[str]:
        """The concrete outcomes the gated prefix's minting node emits.

        The general name for `train_outcomes`, which is what this field is called
        because for one ledger it holds nine TRAIN__ ids. THE OLD NAME IS KEPT
        RATHER THAN REPLACED: five test modules and two tool modules read it, all
        of them against the ML ledger where the name is accurate, and renaming a
        field across modules a sibling lane is holding is a merge conflict bought
        for tidiness. New readers should use this one; the field is the debt.
        """
        return self.train_outcomes

    def commits_at(self, stage: str) -> bool:
        return stage in self.roles.commit_stages

    def method_block(self, node: str) -> dict[str, Any]:
        """A node's `method:` block as the mapping it is, or {} when it is not one.

        THE ONE READER OF THIS FIELD, and it is here because two lanes wrote
        their own. `app/tools/propose.py::engine_method` and
        `app/tools/classical.py::libraries_the_engine_names` both walked
        `node_index[node]["method"]["libs"]`, one parameterised by node and one
        hard-wired to `S8_TABULAR_STANDARD`, and they agreed - which is what
        makes it worth removing now rather than after they stop agreeing. Two
        readers of one spec field is the drift this file argues against
        everywhere else.

        A node whose `method:` is a plain sentence - `S8_TABULAR_WITH_TEXT`'s is
        - comes back empty rather than mangled: there is no block in it to read.
        Neither tool module may import the other (the registry imports both), so
        the shared reader lives with the spec it reads.
        """
        row = self.node_index.get(str(node or "")) or {}
        found = row.get("method")
        return dict(found) if isinstance(found, dict) else {}

    def method_libs(self, node: str) -> tuple[str, ...]:
        """The `method.libs` a node names, verbatim, as a tuple of clean strings."""
        libs = self.method_block(node).get("libs")
        if isinstance(libs, str):
            libs = [libs]
        if not isinstance(libs, (list, tuple)):
            return ()
        return tuple(str(one).strip() for one in libs if str(one).strip())

    def method_class(self, method: str) -> str:
        try:
            return self.methods[method]["class"]
        except KeyError:
            raise EngineError(f"ERROR__UNCLASSIFIED_METHOD: {method!r} is not in `methods`") from None

    def row_key(self, gate_id: str, method_class: str) -> str:
        """contract.path_semantics.row_key, verbatim.

        The `method_class` key of the single `passes_when` row that applies to
        that class: the row named for the class if there is one, otherwise the
        row keyed `any`.
        """
        rows = self.gates[gate_id]["passes_when"]
        for row in rows:
            if row["method_class"] == method_class:
                return method_class
        for row in rows:
            if row["method_class"] == "any":
                return "any"
        raise EngineError(
            f"ERROR__UNCLASSIFIED_METHOD: gate {gate_id} has no row for class {method_class!r}"
        )

    def gate_row(self, gate_id: str, method_class: str) -> dict[str, Any]:
        key = self.row_key(gate_id, method_class)
        for row in self.gates[gate_id]["passes_when"]:
            if row["method_class"] == key:
                return row
        raise EngineError(f"gate {gate_id} lost row {key!r}")  # pragma: no cover

    def gate_reading(self, fact: str, *, method_class: str = "any") -> "GateReading | None":
        """The gate row whose condition READS this fact - found by fact, not by id.

        THE ID WAS A PROXY FOR THE FACT ALL ALONG. Six places in `app/tools/`
        opened `spec.gates["G0_EVAL_SET"]` or `spec.gates["G1_BASELINE_MEASURED"]`
        because they were about to stamp `eval_size_n` or `baseline_measured` and
        wanted to know what the gate asks of it. The fact is already in the
        tool's own `measures=` declaration; the gate id was a second spelling of
        it, hardcoded to one ledger, and wrong on any other. Asking by fact is
        also strictly MORE correct on the ledger it came from: a fact moved to a
        different gate next year is followed on the day it moves, where the
        hardcoded version reads the wrong gate and says nothing.

        `gate_row_facts` is the index and it is parsed by the engine's own
        compiler at load time, so what counts as "reads" is what the condition
        actually evaluates rather than what a regular expression found in it.

        **`None` IS THE LOAD-BEARING ANSWER.** A ledger whose gates never read
        this fact has no such gate, and the caller must say so rather than
        proceed on an empty mapping. That is Eclipse's contract for an extension
        point nobody bound: unbound is empty, and empty is a fact.

        The tie is broken by the ledger's OWN declared order, never by position
        alone. `eval_size_n` is read by `G0_EVAL_SET/any` and by
        `G2_PROMPT_EXHAUSTED/llm_weights`; `contract.required_gates` lists G0
        before G2, so the earliest required gate that reads the fact wins. That
        is not "the eval-set gate is the first one" - an invariant nobody
        declared and the reason `required_gates[0]` was rejected - it is "the
        first gate this ledger requires that asks about this fact at all", which
        is a sentence the ledger itself is entitled to answer.
        """
        name = str(fact)
        order = {gate_id: n for n, gate_id in enumerate(self.required_gates)}
        after = len(order)
        hits: list[tuple[int, int, str, str]] = []
        for (gate_id, row_key), facts in self.gate_row_facts.items():
            if name not in facts:
                continue
            # Within one gate, the row for this method class beats the `any`
            # row, and any row that reads the fact beats none at all - the same
            # precedence `row_key` already applies, restricted to the rows that
            # actually mention the fact.
            precedence = 0 if row_key == method_class else (1 if row_key == "any" else 2)
            hits.append((order.get(gate_id, after), precedence, gate_id, row_key))
        if not hits:
            return None
        _, _, gate_id, row_key = min(hits)
        gate = self.gates[gate_id]
        for row in gate["passes_when"]:
            if row["method_class"] == row_key:
                return GateReading(gate_id=gate_id, gate=gate, row_key=row_key, row=row)
        return None  # pragma: no cover - the index is built from these rows

    # -- the origin policy, read out of the file rather than restated ---------

    @property
    def unattributed_origin(self) -> str:
        """What a bare value counts as. The file says ASSERTED and says why."""
        return self.origin_policy["origin_of_an_unattributed_value"]

    @property
    def unsubstantiated_outcome(self) -> str:
        """The outcome for a gate whose load-bearing fact was only claimed."""
        return self.origin_policy["unsubstantiated_outcome"]

    def admissible_for(self, fact: str) -> frozenset[str]:
        """Which origins may open a gate that reads this fact.

        Keyed by the fact's own `source:` tag, so there is no per-fact table to
        keep in step with the ledger. A fact whose source the policy does not
        cover admits nothing, and SC5 refuses to load a spec in that state - but
        the reading here is refusal rather than permission anyway, because the
        one direction this must never fail in is open.
        """
        source = self.facts[fact].get("source")
        return self.admissible_origins.get(source, frozenset())

    def substantiation(self, fact: str) -> str:
        """What would turn this fact's claim into something that opens a gate."""
        source = self.facts[fact].get("source")
        return self.origin_policy["substantiation"][source]

    def outcome_prefix(self, outcome: str) -> tuple[str, dict[str, Any]]:
        for prefix, spec in self.contract["outcome_prefixes"].items():
            if outcome.startswith(prefix):
                return prefix, spec
        raise SpecError(f"outcome {outcome!r} has no prefix in contract.outcome_prefixes")

    def outcome_sites(self) -> list[OutcomeSite]:
        """EVERY PLACE THIS DOCUMENT STATES AN OUTCOME. One list, read by all of them.

        THIS IS THE ONLY ENUMERATION, AND THAT IS THE WHOLE POINT OF IT. Three
        separate checks used to walk the file looking for outcomes and each one
        knew its own list of places to look: `declared_outcomes` knew four, SC1
        knew one, and the reachability tests knew whatever they were written
        against. When `fork:` arrived it added a FIFTH place a ledger may state
        an outcome - `fork.no_match.outcome` - and not one of the three was told.
        The consequence was not cosmetic: SC1 gathers the nodes that may mint the
        expensive irreversible verdict, so a ledger written after that change
        could mint it from a fork in a node that is not `mintable_only_at`, load
        clean, and come back with `verdict: TRAIN` having walked past the mint's
        `emits:` fence. The honesty test was intact and something had been built
        beside it that the test could not see.

        So the sites live here, once, and every check reads them. A sixth way to
        state an outcome is a change to THIS function, and
        `tests/test_a_ledger_says_what_the_engine_must_find.py` scans the raw
        document for outcome-shaped strings and fails if any of them is not
        found here - so forgetting is a red test rather than a blind spot.

        The five sites today:

          * a node's `outcome:`, which is most of them;
          * `emits` on a node whose outcome is a TEMPLATE. S9_MINT_TRAIN_VERDICT
            declares `TRAIN__{proposed_method}` and lists the nine values that
            stands for;
          * a node's `fork.no_match.outcome` - what a declared fork does with a
            value it has no route for;
          * a gate's `on_fail.outcome`, which is where BLOCKED__BUILD_EVAL_SET
            and ACTION__MEASURE_BASELINE live and nowhere else;
          * `fact_origins.unsubstantiated_outcome`, which no node and no gate
            `on_fail` names. It is the answer for a gate that would have passed
            on values nobody can vouch for, and it is emitted by the gate
            machinery rather than by the graph - so a reader of the stages alone
            will not find it, and neither would this function if it did not look
            here.

        `node` is the node id where the site sits, or None for a site that is
        not in the graph at all. SC1 needs it; `declared_outcomes` does not.
        """
        sites: list[OutcomeSite] = []
        for node_id, node in self.node_index.items():
            outcome = node.get("outcome")
            if isinstance(outcome, str) and "{" in outcome:
                # A templated outcome names a family. `emits` is the family, and
                # _validate_nodes refuses to load a template without one.
                for emitted in node.get("emits") or ():
                    if isinstance(emitted, str):
                        sites.append(OutcomeSite(emitted, node_id, f"node {node_id} emits"))
            elif isinstance(outcome, str):
                sites.append(OutcomeSite(outcome, node_id, f"node {node_id} outcome"))
            fork = node.get("fork")
            if isinstance(fork, Mapping):
                stated = (fork.get("no_match") or {})
                if isinstance(stated, Mapping) and isinstance(stated.get("outcome"), str):
                    sites.append(
                        OutcomeSite(
                            stated["outcome"], node_id, f"node {node_id} fork no_match outcome"
                        )
                    )
        for gate_id, gate in self.gates.items():
            stated = (gate.get("on_fail") or {}).get("outcome")
            if isinstance(stated, str):
                sites.append(OutcomeSite(stated, None, f"gate {gate_id} on_fail outcome"))
        if isinstance(self.unsubstantiated_outcome, str):
            sites.append(
                OutcomeSite(
                    self.unsubstantiated_outcome,
                    None,
                    "fact_origins.unsubstantiated_outcome",
                )
            )
        return sites

    def declared_outcomes(self) -> set[str]:
        """Every TERMINAL outcome this file claims the product can produce.

        THE LIST COMES OUT OF THE FILE, ALWAYS. A copy of it in a test is a copy
        that goes stale in exactly the direction nobody looks: an outcome the
        graph can no longer reach stays in the copy and stays green.

        `terminal` comes from contract.outcome_prefixes, not from a prefix
        spelled out here, so REROUTE and the ERROR__ pair drop out because the
        contract says they are not terminal - not because this function knows
        their names.
        """
        outcomes: set[str] = set()
        for site in self.outcome_sites():
            _, decl = self.outcome_prefix(site.outcome)
            if decl.get("terminal"):
                outcomes.add(site.outcome)
        return outcomes


def gates_passed_under(path: Sequence[PathEntry], method_class: str, spec: Spec) -> set[str]:
    """contract.path_semantics.gates_passed_under, verbatim.

    Not bare membership in `path`. A gate entry counts for a proposal only if it
    was written under the row that applies to that proposal's class. This one
    filter is the difference between the guarantee and the appearance of it: a
    G3 passed under `llm_weights` on the walk down the LLM spine has not
    answered `retrieval_tried and reranker_tried`, and must not look as though
    it has.
    """
    return {
        e.id
        for e in path
        if e.kind == "gate" and e.row == spec.row_key(e.id, method_class)
    }


# ---------------------------------------------------------------------------
# Loading and validating.


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SpecError(message)


# ---------------------------------------------------------------------------
# The strict loader. PyYAML implements YAML 1.1, and three of its behaviours are
# live hazards for a document whose whole job is to be exactly what its author
# wrote. Measured against the PyYAML actually installed here:
#
#   [yes, no, on, off]  -> [True, False, True, False]   an enum member spelled
#                                                       `no` becomes a boolean,
#                                                       and `_collect_literals`
#                                                       would then offer the bare
#                                                       word `False` to conditions
#   12:30               -> 750                          sexagesimal integers
#   dup_key: 1 / dup_key: 2  -> {dup_key: 2}            SILENTLY. In a 3,468-line
#                                                       hand-written file a
#                                                       duplicated node key is a
#                                                       SILENTLY DELETED NODE -
#                                                       the exact failure class
#                                                       this module's header says
#                                                       the loader exists to
#                                                       prevent
#
# All three are closed against PyYAML's public API with no new dependency. The
# narrowing is YAML 1.2's own behaviour, which exists precisely because 1.1's
# implicit typing was found to be a trap.
#
# AND ALIASES ARE REFUSED. The second ledger, hand-written before any of this
# existed, contained a YAML anchor and an alias, and that is how its `route:`
# came to be a mapping instead of a stage name. A ledger is a document, not a
# program; an alias is the smallest step towards a file that computes something
# slightly different from what it appears to say.

_BOOL_1_2 = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")
_INT_1_2 = re.compile(r"^[-+]?(?:0|[1-9][0-9]*|0o?[0-7]+|0x[0-9a-fA-F]+)$")
_FLOAT_1_2 = re.compile(
    r"^[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?$"
    r"|^[-+]?\.(?:inf|Inf|INF)$"
    r"|^\.(?:nan|NaN|NAN)$"
)
_NARROWED_TAGS = frozenset(
    {"tag:yaml.org,2002:bool", "tag:yaml.org,2002:int", "tag:yaml.org,2002:float"}
)


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader with YAML 1.1's implicit typing narrowed to YAML 1.2's."""


_StrictLoader.yaml_implicit_resolvers = {
    ch: [(tag, rx) for (tag, rx) in pairs if tag not in _NARROWED_TAGS]
    for ch, pairs in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_StrictLoader.add_implicit_resolver("tag:yaml.org,2002:bool", _BOOL_1_2, list("tTfF"))
_StrictLoader.add_implicit_resolver("tag:yaml.org,2002:int", _INT_1_2, list("-+0123456789"))
_StrictLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float", _FLOAT_1_2, list("-+0123456789.")
)


def _strict_compose_node(self, parent, index):  # type: ignore[no-untyped-def]
    if self.check_event(yaml.events.AliasEvent):
        event = self.peek_event()
        raise LedgerError(
            "LF002",
            f"a ledger may not use YAML aliases (*{event.anchor}); write the value out",
            document=getattr(self, "_ledger_path", None),
            line=event.start_mark.line + 1,
            expected="a value written in full",
            remedy=(
                "delete the anchor (&name) and the alias (*name) and write the value "
                "at both places. A ledger is read by people as often as by the engine, "
                "and an alias hides what one of the two places actually says."
            ),
        )
    return yaml.composer.Composer.compose_node(self, parent, index)


def _strict_construct_mapping(self, node, deep=False):  # type: ignore[no-untyped-def]
    seen: dict[Any, int] = {}
    for key_node, _value_node in node.value:
        key = self.construct_object(key_node, deep=True)
        try:
            first = seen.get(key)
        except TypeError:  # pragma: no cover - unhashable keys are a YAML error anyway
            first = None
        if first is not None:
            raise LedgerError(
                "LF003",
                f"duplicate key {key!r} (first defined at line {first})",
                document=getattr(self, "_ledger_path", None),
                line=key_node.start_mark.line + 1,
                expected="each key written once",
                remedy=(
                    "delete one of the two, or rename it. PyYAML would silently keep "
                    "the last one, and in a hand-written ledger that is a silently "
                    "deleted node - which is how four training outcomes came to be "
                    "dead while the file claimed all nine were gated."
                ),
            )
        seen[key] = key_node.start_mark.line + 1
    return yaml.constructor.SafeConstructor.construct_mapping(self, node, deep=deep)


_StrictLoader.compose_node = _strict_compose_node  # type: ignore[assignment]
_StrictLoader.construct_mapping = _strict_construct_mapping  # type: ignore[assignment]


def _line_index(text: str, path: Path | str | None) -> dict[str, int]:
    """Top-level key -> the line it is declared on, for error messages.

    `yaml.compose()` returns a node graph carrying `start_mark`, so this costs a
    second parse and no dependency. An error an author can act on has to say
    WHERE, and every validator worth copying - JSON Schema's `instanceLocation`,
    Drools', OPA's - carries a location for exactly this reason.
    """
    index: dict[str, int] = {}
    try:
        root = yaml.compose(text, Loader=_StrictLoader)
    except Exception:  # noqa: BLE001 - the real parse already reported anything fatal
        return index
    if root is None or not hasattr(root, "value"):
        return index
    for key_node, value_node in getattr(root, "value", []) or []:
        key = getattr(key_node, "value", None)
        if isinstance(key, str):
            index[key] = key_node.start_mark.line + 1
        if key in ("contract", "gates", "facts", "methods") and hasattr(value_node, "value"):
            for sub_key, _sub in getattr(value_node, "value", []) or []:
                name = getattr(sub_key, "value", None)
                if isinstance(name, str):
                    index[f"{key}.{name}"] = sub_key.start_mark.line + 1
    return index


def _strict_load(text: str, path: Path | str | None = None) -> Any:
    loader = _StrictLoader(text)
    loader._ledger_path = path  # type: ignore[attr-defined]
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def _is_fork(node: Mapping[str, Any]) -> bool:
    """True for a node carrying a declared `fork:` block."""
    return isinstance(node.get("fork"), Mapping)


def _enum_members(decl: Any) -> list[str]:
    """The declared values of one fact or derived entry. One reader, two callers."""
    if not isinstance(decl, Mapping):
        return []
    out: list[str] = []
    for key in ("enum", "multi"):
        for member in decl.get(key, []) or []:
            out.append(str(member))
    return out


def _collect_literals(raw: Mapping[str, Any], facts: Mapping[str, Any]) -> set[str]:
    """Every bare word a condition is allowed to use as a value rather than a lookup.

    THREE SOURCES, AND ALL THREE ARE DECLARATIONS. A fact's own `enum:`/`multi:`,
    the method names and classes, and a DERIVED value's `enum:` - which is the
    same shape as a fact's and is read the same way.

    THE DERIVED HALF USED TO BE A REGEX OVER PROSE. It reached into
    `raw["derived"]["route"]` by that exact key and scraped capitalised words out
    of the sentence it found, which is how a ledger with no `derived.route` got a
    bare `KeyError` from a loader whose entire job is to refuse with a message.
    It was also far too generous: any capitalised word in that paragraph became a
    value a condition could use. `derived: {route: {enum: [...]}}` says the same
    thing where a reviewer can see it, in the shape facts already use, and a
    derived value that declares no enum now contributes nothing instead of
    contributing whatever its documentation happened to shout.
    """
    literals: set[str] = {"any"}
    for decl in facts.values():
        literals.update(_enum_members(decl))
    for method, decl in raw["methods"].items():
        literals.add(method)
        literals.add(decl["class"])
    for decl in (raw.get("derived") or {}).values():
        literals.update(_enum_members(decl))
    return literals


def _stage_items(raw: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    stages: dict[str, list[dict[str, Any]]] = {}
    for key, value in raw.items():
        if not key.startswith("stage_"):
            continue
        _require(isinstance(value, list), f"{key} must be a list of nodes")
        stages[key] = list(value)
    return stages


# ---------------------------------------------------------------------------
# Ledger format versions. TWO DIFFERENT THINGS ARE BEING VERSIONED and the old
# single `version:` field confused them:
#
#   ledger_format:   an integer major owned by the ENGINE. Which GRAMMAR this
#                    document is written in.
#   ledger_version:  owned by the AUTHOR. Which revision of their KNOWLEDGE this
#                    is. The engine never reads it; a surface renders it, because
#                    a person reading a diagnosis should be able to see which
#                    edition of a domain's judgment produced it.
#
# Load path: parse -> upgrade to CURRENT_LEDGER_FORMAT -> validate against
# CURRENT_LEDGER_FORMAT only -> execute. That last clause is the whole design:
# the 60-odd checks and the walk NEVER fork on version, so an older format is a
# pure data transform in front of one validator rather than a second code path
# that drifts. Many formats read, exactly one executed.


def _read_format(raw: Mapping[str, Any], where: Path | str, lines: Mapping[str, int]) -> int:
    """Which grammar this document claims, refusing what this engine cannot read."""
    declared = raw.get("ledger_format")
    if declared is None:
        if "version" in raw:
            # Format 2 had no way to name its own grammar. The absence IS the
            # signal, and it is unambiguous because format 3 requires the key.
            return 2
        raise LedgerError(
            "LF001",
            "the document declares no `ledger_format:` and no legacy `version:`",
            document=where,
            line=1,
            expected=f"ledger_format: {CURRENT_LEDGER_FORMAT}",
            remedy=(
                f"add `ledger_format: {CURRENT_LEDGER_FORMAT}` as the first key. It says "
                "which GRAMMAR this file is written in, and it is the engine's, not "
                "yours - `ledger_version:` is the one you own."
            ),
        )
    if not isinstance(declared, int) or isinstance(declared, bool):
        raise LedgerError(
            "LF001",
            "`ledger_format:` must be an integer major",
            document=where,
            line=lines.get("ledger_format"),
            found=repr(declared),
            expected=f"one of {list(SUPPORTED_LEDGER_FORMATS)}",
            remedy="write a bare integer, e.g. `ledger_format: 3`",
        )
    if declared not in SUPPORTED_LEDGER_FORMATS:
        raise LedgerError(
            "LF001",
            f"ledger_format: {declared}, and this engine reads "
            f"{' and '.join(str(v) for v in SUPPORTED_LEDGER_FORMATS)}",
            document=where,
            line=lines.get("ledger_format"),
            found=str(declared),
            expected=f"one of {list(SUPPORTED_LEDGER_FORMATS)}",
            remedy=(
                "either upgrade the harness, or write "
                f"`ledger_format: {CURRENT_LEDGER_FORMAT}` and fix what the loader "
                "then reports. A newer format is never read best-effort: a gate "
                "table half understood is the honesty test defeated by a shrug."
            ),
        )
    return declared


def _upgrade_2_to_3(raw: dict[str, Any], where: Path | str) -> dict[str, Any]:
    """Format 2 -> 3, as a pure data transform. Total, and lossless for anything read.

    THIS IS THE ONE PLACE THE FIRST LEDGER'S NAMES ARE STILL SPELLED, AND THAT IS
    WHERE THEY BELONG. Format 2 had no `contract.roles`, so those names were
    CONVENTIONS OF THAT GRAMMAR - `stage_0_admissibility` is where a format-2
    document starts because format 2 said so. An upgrader is allowed to know the
    old grammar's conventions; that is what an upgrader IS. What matters is that
    they are quarantined here, in front of the validator, and that neither the
    64 checks nor the walk can see them.

    IT DERIVES WHERE THE OLD GRAMMAR GUARANTEED AN ANSWER, AND REFUSES WHERE IT
    DID NOT. `commit_stages` and `mintable_only_at` are read out of the document
    - format 2's own SC1 guaranteed exactly one node mints, so there is exactly
    one candidate and deriving is safe. `entry_stage` and `no_proposal` were
    conventions with no in-document evidence, so they are assumed and then
    CHECKED against the document, and a format-2 file that does not match gets a
    refusal naming the format-3 edit rather than a silent wrong answer.
    """
    out = dict(raw)
    if "version" in out and "ledger_version" not in out:
        out["ledger_version"] = out.pop("version")
    out["ledger_format"] = 3

    contract = dict(out.get("contract") or {})
    stages = _stage_items(out)

    # The gated prefix. Format 2 spelled it TRAIN__ and nothing else could be it.
    prefixes = {k: dict(v) for k, v in (contract.get("outcome_prefixes") or {}).items()}
    minters = sorted(
        node["node"]
        for items in stages.values()
        for node in items
        if isinstance(node, Mapping)
        and isinstance(node.get("outcome"), str)
        and node["outcome"].startswith("TRAIN__")
        and "node" in node
    )
    if "TRAIN__" in prefixes:
        if len(minters) != 1:
            raise LedgerError(
                "LF010",
                "this format-2 document has "
                f"{'no node' if not minters else str(len(minters)) + ' nodes'} carrying a "
                "`TRAIN__` outcome, so the engine cannot tell which one commits",
                document=where,
                found=str(minters),
                expected="exactly one, which format 2's own SC1 required",
                remedy=(
                    f"write `ledger_format: {CURRENT_LEDGER_FORMAT}` and declare "
                    "`contract.roles.commit_stages` and "
                    "`contract.outcome_prefixes.<PREFIX>.mintable_only_at` yourself. "
                    "Format 3 asks you to name them rather than leaving them to a "
                    "convention the engine has to guess at."
                ),
            )
        prefixes["TRAIN__"] = {
            **prefixes["TRAIN__"],
            "gated": "all",
            "mintable_only_at": minters[0],
        }
        contract["outcome_prefixes"] = prefixes
        commit_stages = [
            stage for stage, items in stages.items()
            if any(isinstance(n, Mapping) and n.get("node") == minters[0] for n in items)
        ]
    else:
        commit_stages = []

    roles: dict[str, Any] = {
        "entry_stage": "stage_0_admissibility",
        "commit_stages": commit_stages,
        "no_proposal": "UNSET",
    }
    if commit_stages:
        roles["gate_sweep_node"] = "S9_GATE_SWEEP"
    for name, value, remedy in (
        (
            "entry_stage",
            roles["entry_stage"],
            "format 2 always entered at `stage_0_admissibility` and had no way to say "
            "otherwise. Write `ledger_format: 3` and declare "
            "`contract.roles.entry_stage:` for the stage you actually start at.",
        ),
    ):
        if value not in stages:
            raise LedgerError(
                "LF011",
                f"format 2's convention for {name} was {value!r}, and this document has "
                "no such stage",
                document=where,
                found=f"stages: {sorted(stages)}",
                expected=f"a stage named {value!r}",
                remedy=remedy,
            )
    if roles.get("gate_sweep_node") and not any(
        isinstance(n, Mapping) and n.get("node") == roles["gate_sweep_node"]
        for items in stages.values()
        for n in items
    ):
        raise LedgerError(
            "LF011",
            "format 2's convention for the gate sweep was `S9_GATE_SWEEP`, and this "
            "document has no such node",
            document=where,
            expected="a node named S9_GATE_SWEEP in the committing stage",
            remedy=(
                f"write `ledger_format: {CURRENT_LEDGER_FORMAT}` and declare "
                "`contract.roles.gate_sweep_node:` for the node you actually sweep at."
            ),
        )
    if "UNSET" not in (out.get("methods") or {}) and (out.get("methods") or {}):
        raise LedgerError(
            "LF011",
            "format 2's sentinel for `no proposal yet` was the method `UNSET`, and "
            "this document's `methods` does not declare it",
            document=where,
            found=f"methods: {sorted(out.get('methods') or {})}",
            expected="a method named UNSET",
            remedy=(
                f"write `ledger_format: {CURRENT_LEDGER_FORMAT}` and declare "
                "`contract.roles.no_proposal:` naming your own sentinel."
            ),
        )
    contract["roles"] = roles
    out["contract"] = contract

    # `derived.route`, which format 2 read BY THAT EXACT KEY and scraped for
    # capitalised words to decide which bare words a condition could use as
    # values. That rule is gone from the engine - a derived value declares its
    # members the way a fact does - so the transform has to reproduce it here or
    # a format-2 document stops loading. WHICH IS EXACTLY HOW THIS WAS FOUND:
    # the first run of the upgrader proof failed with `node S9_QLORA_QUALITY_TAX:
    # uses undeclared name 'QLORA'`, because the enum those conditions read had
    # been living in a paragraph. An upgrader that is not run against the real
    # old document is a claim, not a transform.
    derived = dict(out.get("derived") or {})
    route = derived.get("route")
    if isinstance(route, str):
        head = route.split(".")[0]
        derived["route"] = {
            "enum": sorted(set(re.findall(r"\b[A-Z][A-Z_]+\b", head))),
            "means": route,
        }
        out["derived"] = derived

    # `routes:` as a bare mapping was a fork with no declared strategy, and
    # `route:`/`routes:` differed by one character while meaning unrelated
    # things. Both become the nested `fork:` block, whose keys are two or more
    # characters apart from anything else in the grammar.
    for stage, items in stages.items():
        rebuilt: list[Any] = []
        for node in items:
            if isinstance(node, Mapping) and isinstance(node.get("routes"), Mapping):
                node = dict(node)
                node["fork"] = {
                    "branch_on": _FORMAT_2_FORKS[node["node"]][0],
                    "select": _FORMAT_2_FORKS[node["node"]][1],
                    "routes": node.pop("routes"),
                    # Format 2 raised an EngineError here. That is preserved
                    # verbatim: an upgrader may not decide a question the old
                    # document never answered.
                    "no_match": {"error": _FORMAT_2_FORKS[node["node"]][2]},
                }
            rebuilt.append(node)
        out[stage] = rebuilt
    return out


#: node id -> (branch_on, select, the message its format-2 handler raised).
#: Format 2's forks were Python functions keyed by node id, so the only way to
#: carry a format-2 document forward is to know which two the engine shipped.
#: This table is the whole of `ROUTE_KEYS`, moved to where it belongs: an
#: upgrader for a grammar that no longer exists.
_FORMAT_2_FORKS: dict[str, tuple[str, str, str]] = {
    "S0_MODALITY_FORK": (
        "modality",
        "value",
        "S0_MODALITY_FORK has no route for modality {value!r}",
    ),
    "S1_ROUTE_BY_FAILURE_MODE": (
        "failure_histogram",
        "argmax",
        "S1_ROUTE_BY_FAILURE_MODE reached with no failure mode it routes for: {keys}",
    ),
}


#: format -> the transform that carries a document of that format to the next
#: one. The engine is BACKWARD compatible over formats it has an upgrader for,
#: and deliberately NOT FORWARD compatible: an old engine given a newer format
#: refuses (see `_read_format`).
_UPGRADERS: dict[int, Callable[[dict[str, Any], Any], dict[str, Any]]] = {
    2: _upgrade_2_to_3,
}


def _read_roles(
    contract: Mapping[str, Any],
    stages: Mapping[str, Any],
    where: Path | str,
    lines: Mapping[str, int],
) -> Roles:
    """contract.roles, checked. Every field is a NAME; every check here is a RULE."""
    line = lines.get("contract.roles") or lines.get("contract")
    block = contract.get("roles")
    if block is None:
        raise LedgerError(
            "LF012",
            "`contract:` has no `roles:` block",
            document=where,
            line=lines.get("contract"),
            expected="roles: {entry_stage, commit_stages, no_proposal}",
            remedy=(
                "add a `roles:` block naming the stage the walk starts at, the stages "
                "where a candidate becomes a verdict (write `commit_stages: []` if this "
                "ledger never commits to anything irreversible), and the sentinel that "
                "means nothing has been proposed yet."
            ),
        )
    if not isinstance(block, Mapping):
        raise LedgerError(
            "LF012",
            "`contract.roles` must be a mapping",
            document=where,
            line=line,
            found=type(block).__name__,
        )
    _refuse_unknown_keys(
        block,
        {"entry_stage", "commit_stages", "no_proposal", "gate_sweep_node"},
        where="contract.roles",
        check_id="LF013",
        document=where,
        line=line,
    )

    for key in ("entry_stage", "commit_stages", "no_proposal"):
        if key not in block:
            raise LedgerError(
                "LF012",
                f"`contract.roles` is missing {key!r}",
                document=where,
                line=line,
                expected=_ROLE_WHY[key],
                remedy=(
                    "write it. The axis here is not required-to-HAVE, it is "
                    "required-to-STATE: an empty answer is legal and a missing one is "
                    "not, because a default would silently decide something "
                    "load-bearing."
                ),
            )

    entry = block["entry_stage"]
    if entry not in stages:
        raise LedgerError(
            "LF014",
            f"`contract.roles.entry_stage` names {entry!r}, which is not a stage",
            document=where,
            line=line,
            found=f"stages: {sorted(stages)}",
            expected="a top-level key beginning `stage_`",
        )

    commit = block["commit_stages"]
    if not isinstance(commit, list):
        raise LedgerError(
            "LF012",
            "`contract.roles.commit_stages` must be a list, and an empty list is the "
            "way to say this ledger commits to nothing",
            document=where,
            line=line,
            found=repr(commit),
        )
    for stage in commit:
        if stage not in stages:
            raise LedgerError(
                "LF014",
                f"`contract.roles.commit_stages` names {stage!r}, which is not a stage",
                document=where,
                line=line,
                found=f"stages: {sorted(stages)}",
            )

    sweep = block.get("gate_sweep_node")
    if sweep is not None and not isinstance(sweep, str):
        raise LedgerError(
            "LF012", "`contract.roles.gate_sweep_node` must be a node id",
            document=where, line=line, found=repr(sweep),
        )
    return Roles(
        entry_stage=str(entry),
        commit_stages=tuple(str(s) for s in commit),
        no_proposal=str(block["no_proposal"]),
        gate_sweep_node=sweep,
    )


_ROLE_WHY = {
    "entry_stage": "the stage the walk starts at",
    "commit_stages": "the stages where a candidate becomes a verdict; [] is a legal answer",
    "no_proposal": "the sentinel meaning nothing has been proposed yet",
}


def _refuse_unknown_keys(
    block: Mapping[str, Any],
    known: set[str],
    *,
    where: str,
    check_id: str,
    document: Path | str,
    line: int | None = None,
) -> None:
    """An unrecognised key in a CLOSED block is an error, and it names the near miss.

    JSON Schema says unknown keywords SHOULD become annotations. That is right
    for a format strangers extend in flight and WRONG here, and the reason is
    this module's own header: *a node the engine has no way to execute is a
    load-time error, not a node that is silently ignored - silently-ignored nodes
    are how four training outcomes came to be dead while the file claimed all
    nine were gated.* A misspelled key that becomes an annotation is that defect
    with a new spelling.

    THE ESCAPE HATCH IS DECLARED RATHER THAN IMPLIED: keys prefixed `x_` are the
    author's own and are carried through untouched. A declared place for
    undeclared things is what stops people smuggling notes into keys the engine
    might one day claim.

    THIS IS APPLIED TO THE BLOCKS THIS PASS DEFINES AND NOT YET TO THE WHOLE
    DOCUMENT. Those blocks have a small closed vocabulary the engine owns; a
    whole-document key inventory is a bigger and separate piece of work, and
    claiming it here on the strength of four blocks would be the same error as
    the blocker list this pass had to correct.
    """
    for key in block:
        name = str(key)
        if name.startswith("x_") or name in known:
            continue
        near = _nearest(name, known)
        raise LedgerError(
            check_id,
            f"unknown key {name!r}" + (f". Did you mean {near!r}?" if near else ""),
            where=where,
            document=document,
            line=line,
            expected=f"one of {sorted(known)}",
            remedy=(
                f"rename it to {near!r}" if near
                else "delete it, or prefix it `x_` if it is a note of your own"
            ),
        )


def _nearest(name: str, known: set[str]) -> str | None:
    """The closest known key, by a cheap edit distance. Message-only."""
    best, best_score = None, 0.0
    for candidate in sorted(known):
        shared = len(set(name) & set(candidate))
        score = shared / max(len(set(name) | set(candidate)), 1)
        if name[:3] == candidate[:3]:
            score += 0.5
        if score > best_score:
            best, best_score = candidate, score
    return best if best_score >= 0.6 else None


def _check_gate_identity(
    gates: Mapping[str, Any],
    node_index: Mapping[str, Any],
    stages: Mapping[str, Any],
    where: Path | str,
    lines: Mapping[str, int],
) -> None:
    """A gate's `node:` and `stage:` are what a person is SHOWN, so they must be true.

    A GATE'S NODE IS A NAME THAT EXISTS NOWHERE ELSE, AND THAT IS DELIBERATE.
    `S0_NO_EVAL_SET` is not an item in `stage_0_admissibility`; it is the id the
    gate machinery writes onto the path when the gate refuses, and the stages
    reference the gate itself with `gate_ref:`. So "is it in node_index" is the
    WRONG question - the answer is no for all five of the ML ledger's gates and
    for all five of the AI ledger's - and an adversary who checked membership
    would have concluded the engine was fine while both real halves of the
    problem sat open:

      * TWO GATES SHARING A `node:`, or a gate whose `node:` is a real node id.
        `app/asking.py:_because_for` reads `_gate_nodes()` to turn a path entry
        back into the gate that wrote it, so a shared id means a card explaining
        one gate under another gate's question, and a collision with a real node
        means a card explaining a node as though it were a gate. That is a
        displayed sentence with the wrong provenance, silently.
      * A `stage:` that names no stage, or names a stage the `gate_ref` is not
        in. The same function puts that string on the card as where the gate
        lives. It is written by hand in the `gates:` block and nothing read it
        against the stage that actually holds the reference, so the two could
        disagree for the life of the file and the only symptom would be a person
        told to look in the wrong place.

    Both are decidable from data the loader is already holding, and both are the
    same rule: an id a ledger displays has to name the thing it claims to name.
    """
    referenced: dict[str, list[str]] = {}
    for stage_name, items in stages.items():
        for item in items:
            if isinstance(item, Mapping) and "gate_ref" in item:
                referenced.setdefault(str(item["gate_ref"]), []).append(stage_name)

    seen: dict[str, str] = {}
    for gate_id, gate in gates.items():
        node_id = str(gate["node"])
        if node_id in node_index:
            raise LedgerError(
                "LF015",
                f"gate {gate_id} declares `node: {node_id}`, which is also a real node",
                document=where,
                line=lines.get(gate_id),
                expected="an id used by this gate and nothing else",
                remedy=(
                    "a gate's node id is the name written onto the path when the gate "
                    "refuses. Sharing it with a node in a stage makes one path entry "
                    "mean two different things, and the card built from it explains "
                    "whichever the lookup found first."
                ),
            )
        if node_id in seen:
            raise LedgerError(
                "LF015",
                f"gates {seen[node_id]} and {gate_id} both declare `node: {node_id}`",
                document=where,
                line=lines.get(gate_id),
                expected="one node id per gate",
                remedy=(
                    "the path records which gate refused by this id, so two gates "
                    "sharing one are indistinguishable in the audit trail the whole "
                    "product is built on."
                ),
            )
        seen[node_id] = gate_id

        stage_name = str(gate["stage"])
        if stage_name not in stages:
            raise LedgerError(
                "LF015",
                f"gate {gate_id} declares `stage: {stage_name}`, which is not a stage",
                document=where,
                line=lines.get(gate_id),
                found=f"stages: {sorted(stages)}",
                remedy="name the stage whose `gate_ref:` reaches this gate",
            )
        where_used = referenced.get(gate_id) or []
        if where_used and stage_name not in where_used:
            raise LedgerError(
                "LF015",
                f"gate {gate_id} declares `stage: {stage_name}` and its `gate_ref:` is "
                f"in {where_used}",
                document=where,
                line=lines.get(gate_id),
                expected="the stage that actually references it",
                remedy=(
                    "this string is shown to a person as where the gate lives. Written "
                    "by hand in the `gates:` block and never read against the stage "
                    "holding the reference, it can be wrong forever and the only "
                    "symptom is somebody sent to the wrong part of their own diagnosis."
                ),
            )


_PREFIX_KEYS = {"verdict", "terminal", "meaning", "gated", "mintable_only_at"}


def _read_gated_prefix(
    contract: Mapping[str, Any],
    roles: Roles,
    where: Path | str,
    lines: Mapping[str, int],
) -> tuple[str | None, str | None]:
    """Which outcome prefix is THE EXPENSIVE IRREVERSIBLE ONE, and where it may be minted.

    This is the role `TRAIN__` was secretly playing. `docs/VISION.md` named it
    exactly right - *"not an ML concept but a role: the expensive irreversible
    outcome that must pass every gate"* - and it was written as a string literal
    in the middle of SC1, where it sat unnoticed for the life of the file because
    it looked exactly like the sixty-odd checks around it.

    A ledger declares it on the prefix that plays it:

        outcome_prefixes:
          BUILD__: {verdict: BUILD, terminal: true,
                    gated: all, mintable_only_at: S9_MINT_BUILD_VERDICT}

    AT MOST ONE PREFIX MAY BE GATED, and the reason is not tidiness. `gated: all`
    means "every gate in contract.required_gates"; two gated prefixes sharing one
    flat `required_gates` list would be two different risks wearing the same
    question set. A data ledger with both `SYNTHESISE__` and `RELABEL__` genuinely
    wants different gates for each - inventing rows and paying humans are not the
    same risk - so the grammar admits the shape now and the engine REFUSES it
    until it is built. A key you do not understand is a refusal, never a shrug;
    accepting `gated: [G0, G2]` and silently applying all five would be the
    honesty test defeated by a convenience.
    """
    line = lines.get("contract")
    prefixes = contract.get("outcome_prefixes")
    if not isinstance(prefixes, Mapping) or not prefixes:
        raise LedgerError(
            "LF020",
            "`contract.outcome_prefixes` is missing or empty",
            document=where,
            line=line,
            expected="a mapping of prefix -> {verdict, terminal, meaning}",
        )

    # THE DECLARED VERDICT VOCABULARY, WHICH WAS WRITTEN DOWN AND NEVER READ.
    # `contract.diagnosis.verdict.enum` is the ledger saying which words its
    # verdicts are. Nothing consulted it, so a prefix mapping to `SHIP_IT_NOW` -
    # or to a dict - loaded clean and came back in `Diagnosis.verdict`, which is
    # a value the interface branches on and shows. A vocabulary a document
    # declares and the engine ignores is worse than none: the author believes
    # they constrained something.
    vocabulary = ((contract.get("diagnosis") or {}).get("verdict") or {}).get("enum")
    if not isinstance(vocabulary, list) or not vocabulary:
        raise LedgerError(
            "LF028",
            "`contract.diagnosis.verdict.enum` is missing or empty",
            document=where, line=line,
            expected="a list of the verdict words this ledger's prefixes map to",
            remedy=(
                "the verdict is the one word a person is shown and the interface "
                "branches on. Name the closed set, e.g. `verdict: {enum: [NO_TRAIN, "
                "TRAIN, BLOCKED]}`."
            ),
        )

    gated: list[str] = []
    for prefix, decl in prefixes.items():
        if not isinstance(decl, Mapping):
            raise LedgerError(
                "LF020", f"outcome prefix {prefix!r} is not a mapping",
                document=where, line=line, found=repr(decl),
            )
        _refuse_unknown_keys(
            decl, _PREFIX_KEYS,
            where=f"contract.outcome_prefixes.{prefix}",
            check_id="LF021", document=where, line=line,
        )
        if "verdict" not in decl:
            raise LedgerError(
                "LF028",
                f"outcome prefix {prefix!r} declares no `verdict:`",
                document=where, line=line,
                expected=f"one of {vocabulary}, or `verdict: null` for a non-terminal prefix",
            )
        stated = decl["verdict"]
        if stated is not None and stated not in vocabulary:
            raise LedgerError(
                "LF028",
                f"outcome prefix {prefix!r} maps to verdict {stated!r}",
                document=where, line=line,
                found=repr(stated),
                expected=f"one of `contract.diagnosis.verdict.enum` {vocabulary}, or null",
                remedy=(
                    "either add the word to the declared vocabulary or use one that is "
                    "in it. The enum is the ledger's own statement of which verdicts "
                    "exist; a prefix outside it puts a word on the screen that the file "
                    "says cannot happen."
                ),
            )
        if stated is None and decl.get("terminal"):
            raise LedgerError(
                "LF028",
                f"outcome prefix {prefix!r} is terminal and has `verdict: null`",
                document=where, line=line,
                remedy=(
                    "a run that ENDS here has to end with a verdict. `verdict: null` is "
                    "for the prefixes a walk passes through - REROUTE and ERROR__ - and "
                    "reaching one as a terminal is an engine error at the exit, which "
                    "is a stack trace where a diagnosis was owed."
                ),
            )
        mark = decl.get("gated")
        if mark is None:
            continue
        if mark != "all":
            raise LedgerError(
                "LF022",
                f"outcome prefix {prefix!r} declares `gated: {mark!r}`; per-prefix gate "
                "sets are declared but not implemented",
                document=where,
                line=line,
                expected="gated: all",
                remedy=(
                    "write `gated: all`, which means every gate in "
                    "`contract.required_gates`. A narrower set is a real thing a ledger "
                    "will want - inventing rows and paying humans are not the same risk "
                    "- and it is refused rather than ignored, because an author who "
                    "wrote a narrower set and silently got the full one would believe "
                    "the wrong thing about their own file."
                ),
            )
        gated.append(str(prefix))

    if not gated:
        if roles.commit_stages:
            raise LedgerError(
                "LF023",
                "this ledger declares commit stages "
                f"{list(roles.commit_stages)} and no `gated:` outcome prefix, so "
                "nothing it commits to would have to pass a gate",
                document=where,
                line=line,
                expected="exactly one prefix carrying `gated: all` and `mintable_only_at:`",
                remedy=(
                    "either mark the prefix your commit stage mints with `gated: all` "
                    "and `mintable_only_at: <node>`, or write `commit_stages: []` if "
                    "this ledger genuinely commits to nothing irreversible."
                ),
            )
        return None, None

    if len(gated) > 1:
        raise LedgerError(
            "LF024",
            f"{len(gated)} outcome prefixes are declared `gated: all`: {sorted(gated)}",
            document=where, line=line,
            expected="at most one",
            remedy=(
                "`contract.required_gates` is a single flat list, so two gated prefixes "
                "would be two different risks asked the same questions. Split the "
                "ledger, or wait for per-prefix gate sets."
            ),
        )
    prefix = gated[0]
    if not roles.commit_stages:
        raise LedgerError(
            "LF023",
            f"outcome prefix {prefix!r} is declared `gated: all`, and "
            "`contract.roles.commit_stages` is empty",
            document=where, line=line,
            remedy=(
                "a ledger that declares itself non-committing may not also declare a "
                "gated prefix. Name the stage where the candidate becomes a verdict, or "
                "drop the `gated:` mark."
            ),
        )
    mint_node = prefixes[prefix].get("mintable_only_at")
    if not isinstance(mint_node, str) or not mint_node:
        raise LedgerError(
            "LF025",
            f"outcome prefix {prefix!r} is `gated: all` and names no `mintable_only_at:`",
            document=where, line=line,
            expected="mintable_only_at: <the one node that may emit this prefix>",
            remedy=(
                "name the single node. Exactly one node may mint the irreversible "
                "verdict; that is not a shape a schema can state, and it is the "
                "sentence the whole five-gate test rests on."
            ),
        )
    if not prefixes[prefix].get("terminal"):
        raise LedgerError(
            "LF026",
            f"outcome prefix {prefix!r} is `gated: all` and is not declared terminal",
            document=where, line=line,
            remedy="a run has to be able to END at the expensive answer",
        )
    # `gated: all` OVER AN EMPTY SET IS VACUOUSLY TRUE, AND THAT IS THE WHOLE
    # HONESTY TEST TURNED OFF BY ONE LINE IN A DATA FILE.
    #
    # Found by an adversary, and it is the worst shape in this file's history
    # because every OTHER corner of it was already refused: LF023 refuses a gated
    # prefix with no commit stage and a commit stage with no gated prefix, LF025
    # refuses a missing `mintable_only_at`, LF050 refuses a missing sweep, LF051
    # refuses a sweep outside the commit stage. Write `required_gates: []` and
    # all five of those refusals stay satisfied and every one of them becomes a
    # no-op: the sweep has nothing to ask, `_check_sweep_is_declared` returned
    # early on the empty list, and `_finish`'s ERROR__GATE_SKIPPED check computes
    # `set([]) - passed`, which is empty, so the last line of defence verifies
    # nothing. A ledger could mint an irreversible verdict with an EMPTY
    # `gate_ledger` while the gate that would have refused it sat defined, in
    # full, three lines further down the same document.
    #
    # A prefix is not "gated" because it says the word. It is gated because
    # questions are asked, and zero questions is not a smaller number of
    # questions - it is a different claim, and a ledger has to make it out loud
    # by not declaring the prefix gated at all.
    if not list(contract.get("required_gates") or []):
        raise LedgerError(
            "LF027",
            f"outcome prefix {prefix!r} is declared `gated: all` and "
            "`contract.required_gates` is empty",
            document=where,
            line=line,
            found="required_gates: []",
            expected="at least one gate id, because `all` of nothing is nothing",
            remedy=(
                "`gated: all` means every gate in `contract.required_gates`, and over "
                "an empty list it is vacuously true - the sweep asks nothing, the exit "
                "check compares against nothing, and the verdict comes back with an "
                "empty gate ledger. Either name the gates this prefix must pass, or "
                "drop the `gated:` mark and say plainly that this ledger commits to "
                "nothing that has to be earned."
            ),
        )
    return prefix, mint_node


def _check_derived_is_resolvable(spec: Spec) -> None:
    """A `derived:` name a condition may use must be one the engine can produce.

    `derived:` is documentation for most of its length, and one thing more: it is
    the list of names a condition may read that are not facts. Before this check
    a ledger could declare `derived: {my_thing: "..."}`, use `my_thing` in a
    condition, load clean, and then die at eval time with `condition names
    'my_thing', which resolves to nothing` - safe and broken, in front of a user,
    for a mistake that was visible at load.
    """
    unknown = sorted(set(spec.raw.get("derived") or {}) - _ENGINE_NAMES - set(spec.facts))
    if unknown:
        raise LedgerError(
            "LF030",
            f"`derived:` declares {unknown}, which this engine cannot compute",
            document=spec.path,
            line=spec.line_of.get("derived"),
            found=str(unknown),
            expected=f"names the engine resolves: {sorted(_ENGINE_NAMES)}",
            remedy=(
                "a derived value is computed by the ENGINE, so declaring one it does "
                "not compute means every condition reading it would fail at run time "
                "rather than at load. Remove it, or make it a fact."
            ),
        )


def load_spec(path: Path | str | None = None) -> Spec:
    """Read and validate the spec. Raises SpecError on anything it cannot execute."""
    spec_path = Path(path) if path is not None else SPEC_PATH
    text = spec_path.read_text(encoding="utf-8")
    raw = _strict_load(text, spec_path)
    _require(isinstance(raw, dict), "spec must be a mapping at the top level")
    lines = _line_index(text, spec_path)

    ledger_format = _read_format(raw, spec_path, lines)
    if ledger_format < CURRENT_LEDGER_FORMAT:
        raw = _UPGRADERS[ledger_format](raw, spec_path)

    for key in ("contract", "methods", "gates", "facts", "fact_origins"):
        _require(key in raw, f"spec is missing top-level key {key!r}")
    _require(
        isinstance(raw.get("ledger_version"), (int, str)),
        "spec is missing `ledger_version:`. It is YOURS - which revision of this "
        "domain's knowledge this file is - and it is separate from `ledger_format:`, "
        "which is the engine's grammar. Confusing the two is how a format version "
        "ends up unreadable.",
    )
    _require(
        isinstance(raw.get("derived", {}), dict),
        "`derived:` must be a mapping when present; a ledger with none may omit it",
    )

    contract = raw["contract"]
    for key in ("required_gates", "path_semantics", "outcome_prefixes", "diagnosis"):
        _require(key in contract, f"contract is missing {key!r}")

    facts = raw["facts"]
    _require(isinstance(facts, dict) and facts, "facts must be a non-empty mapping")
    methods = raw["methods"]
    _require(isinstance(methods, dict) and methods, "methods must be a non-empty mapping")
    for name, decl in methods.items():
        _require(isinstance(decl, dict) and "class" in decl, f"method {name!r} has no class")
    method_classes = {decl["class"] for decl in methods.values()}

    gates = raw["gates"]
    required_gates = list(contract["required_gates"])
    for gate_id in required_gates:
        _require(gate_id in gates, f"required gate {gate_id!r} is not defined in `gates`")
    for gate_id, gate in gates.items():
        _require(bool(GATE_ID_RE.match(gate_id)), f"gate id {gate_id!r} does not match ^G[0-9]_")
        for key in ("node", "stage", "asks", "passes_when", "on_fail"):
            _require(key in gate, f"gate {gate_id} is missing {key!r}")
        _require(
            bool(NODE_ID_RE.match(gate["node"])),
            f"gate {gate_id}'s node {gate['node']!r} does not match ^S[0-9]+_",
        )
        rows = gate["passes_when"]
        _require(isinstance(rows, list) and rows, f"gate {gate_id} has no passes_when rows")
        seen_classes: set[str] = set()
        for row in rows:
            _require(
                isinstance(row, dict) and "method_class" in row and "requires" in row,
                f"gate {gate_id} has a malformed passes_when row: {row!r}",
            )
            klass = row["method_class"]
            _require(
                klass == "any" or klass in method_classes,
                f"gate {gate_id} has a row for unknown class {klass!r}",
            )
            _require(klass not in seen_classes, f"gate {gate_id} has two rows for {klass!r}")
            seen_classes.add(klass)
        # SC3: every method must have a row in every gate, or the engine has no
        # question to ask it and would wave it through.
        for name, decl in methods.items():
            klass = decl["class"]
            _require(
                klass in seen_classes or "any" in seen_classes,
                f"SC3: method {name!r} (class {klass}) has no row in gate {gate_id}",
            )

    stages = _stage_items(raw)
    _require(bool(stages), "spec declares no stages; the engine has nothing to walk")
    roles = _read_roles(contract, stages, spec_path, lines)
    gated_prefix, mint_node = _read_gated_prefix(contract, roles, spec_path, lines)

    node_index: dict[str, dict[str, Any]] = {}
    node_stage: dict[str, str] = {}
    for stage_name, items in stages.items():
        for item in items:
            _require(isinstance(item, dict), f"{stage_name} holds a non-mapping item")
            if "gate_ref" in item:
                _require(
                    item["gate_ref"] in gates,
                    f"{stage_name} references unknown gate {item['gate_ref']!r}",
                )
                continue
            _require("node" in item, f"{stage_name} holds an item with no node id: {item!r}")
            node_id = item["node"]
            _require(
                bool(NODE_ID_RE.match(node_id)),
                f"node id {node_id!r} does not match ^S[0-9]+_",
            )
            _require(node_id not in node_index, f"duplicate node id {node_id!r}")
            node_index[node_id] = item
            node_stage[node_id] = stage_name

    # The two namespaces must not overlap; `kind` is authoritative but this is
    # the belt-and-braces check the spec asks for.
    overlap = set(node_index) & set(gates)
    _require(not overlap, f"node and gate id namespaces overlap: {sorted(overlap)}")

    _check_gate_identity(gates, node_index, stages, spec_path, lines)

    literals = _collect_literals(raw, facts)
    literals |= set(node_index) | set(gates) | set(stages)

    spec = Spec(
        raw=raw,
        path=spec_path,
        facts=facts,
        methods=methods,
        gates=gates,
        stages=stages,
        contract=contract,
        required_gates=required_gates,
        node_index=node_index,
        node_stage=node_stage,
        literals=literals,
        conditions={},
        gate_conditions={},
        method_classes=method_classes,
        train_outcomes=[],
        origin_policy=raw["fact_origins"],
        admissible_origins={},
        gate_row_facts={},
        roles=roles,
        ledger_format=ledger_format,
        gated_prefix=gated_prefix,
        mint_node=mint_node,
        line_of=lines,
    )

    _check_derived_is_resolvable(spec)
    _check_sweep_is_declared(spec)
    _load_origin_policy(spec)
    _compile_gate_rows(spec)
    _validate_nodes(spec)
    _static_checks(spec, text)
    return spec


def _load_origin_policy(spec: Spec) -> None:
    """SC5. Read `fact_origins`, and refuse to load a spec whose policy has a hole.

    Every check here fails a build rather than degrading, and that direction is
    the whole point. A missing `source:` on one fact, or a source the
    admissibility table has no row for, would silently make that fact's
    admissible set empty - which happens to fail CLOSED, so the product would
    still be safe and would also be quietly unable to open a gate that fact sits
    in. Safe and broken is not the same as safe and working, and a build that
    stops is the only way anyone finds out which one they have.
    """
    policy = spec.origin_policy
    _require(isinstance(policy, dict), "fact_origins must be a mapping")
    for key in (
        "vocabulary",
        "origin_of_an_unattributed_value",
        "admissible_for_gates",
        "substantiation",
        "unsubstantiated_outcome",
    ):
        _require(key in policy, f"fact_origins is missing {key!r}")

    vocabulary = policy["vocabulary"]
    _require(isinstance(vocabulary, dict) and vocabulary, "fact_origins.vocabulary is empty")
    _require(
        set(vocabulary) == set(ORIGINS),
        "fact_origins.vocabulary and app/diagnosis.py disagree about the origin "
        f"names: only in the file {sorted(set(vocabulary) - set(ORIGINS))}, only "
        f"in the module {sorted(set(ORIGINS) - set(vocabulary))}",
    )

    unattributed = policy["origin_of_an_unattributed_value"]
    _require(
        unattributed in vocabulary,
        f"fact_origins says an unattributed value is {unattributed!r}, which is "
        "not in the vocabulary",
    )
    _require(
        unattributed not in ENGINE_ONLY_ORIGINS,
        f"fact_origins reads an unattributed value as {unattributed!r}, which "
        "only the engine may assign",
    )

    table = policy["admissible_for_gates"]
    _require(isinstance(table, dict) and table, "fact_origins.admissible_for_gates is empty")
    for source, allowed in table.items():
        _require(
            isinstance(allowed, list) and allowed,
            f"fact_origins.admissible_for_gates[{source!r}] admits no origin at all",
        )
        for origin in allowed:
            _require(
                origin in vocabulary,
                f"fact_origins.admissible_for_gates[{source!r}] names {origin!r}, "
                "which is not in the vocabulary",
            )
            _require(
                origin not in ENGINE_ONLY_ORIGINS,
                f"fact_origins.admissible_for_gates[{source!r}] admits {origin!r}. "
                "That origin means the ledger's own default was applied, and a "
                "default may never open a gate - see RC9_NO_DEFAULT_OPENS_A_GATE.",
            )
        spec.admissible_origins[source] = frozenset(allowed)

    substantiation = policy["substantiation"]
    _require(isinstance(substantiation, dict), "fact_origins.substantiation must be a mapping")

    # Every fact carries a source, and every source the ledger uses is covered by
    # both tables. This is the half that stops a hole arriving by omission.
    sources: set[str] = set()
    for name, decl in spec.facts.items():
        source = decl.get("source")
        _require(
            isinstance(source, str) and source,
            f"fact {name!r} carries no `source:`. Every fact needs one - it is "
            "what decides which origins may open a gate the fact appears in, and "
            "it is what lets the interface say where a displayed number came "
            "from at all.",
        )
        sources.add(source)
    missing = sorted(sources - set(table))
    _require(
        not missing,
        f"fact_origins.admissible_for_gates has no row for source(s) {missing}, "
        "which the ledger uses",
    )
    missing = sorted(sources - set(substantiation))
    _require(
        not missing,
        f"fact_origins.substantiation has no line for source(s) {missing}. A gate "
        "that refuses a claimed fact has to be able to say what would substantiate "
        "it; refusing without a next step is not this product's voice.",
    )

    outcome = policy["unsubstantiated_outcome"]
    _require(isinstance(outcome, str) and outcome, "fact_origins.unsubstantiated_outcome is empty")
    _, decl = spec.outcome_prefix(outcome)
    _require(
        bool(decl.get("terminal")),
        f"fact_origins.unsubstantiated_outcome is {outcome!r}, whose prefix the "
        "contract does not declare terminal. A run has to be able to END there.",
    )
    _require(
        spec.gated_prefix is None or not outcome.startswith(spec.gated_prefix),
        f"fact_origins.unsubstantiated_outcome is {outcome!r}, which carries this "
        f"ledger's gated prefix {spec.gated_prefix!r}. The answer to an unsubstantiated "
        "claim can never be the expensive irreversible verdict.",
    )


def _resolvable(spec: Spec, name: str) -> bool:
    return (
        name in spec.facts
        or name in (spec.raw.get("derived") or {})
        or name in _ENGINE_NAMES
        or name in spec.literals
    )


def _check_names(spec: Spec, where: str, tree: ast.expr) -> None:
    values, called, roots = _names_used(tree)
    for name in called:
        _require(name in _FUNCTIONS, f"{where}: calls unknown function {name!r}")
    for name in values:
        _require(_resolvable(spec, name), f"{where}: uses undeclared name {name!r}")
    for name in roots:
        _require(
            _resolvable(spec, name) or name in spec.node_index,
            f"{where}: reads attributes of undeclared name {name!r}",
        )


def _compile_gate_rows(spec: Spec) -> None:
    for gate_id, gate in spec.gates.items():
        for row in gate["passes_when"]:
            tree = compile_condition(row["requires"])
            _check_names(spec, f"gate {gate_id} row {row['method_class']}", tree)
            spec.gate_conditions[(gate_id, row["method_class"])] = tree
            spec.gate_row_facts[(gate_id, row["method_class"])] = _facts_read_by(spec, tree)


def _facts_read_by(spec: Spec, tree: ast.expr) -> frozenset[str]:
    """The declared facts a compiled condition READS.

    Parsed, never listed. `_names_used` already knows the dialect's two traps -
    a bare word inside a set literal is an enum member and the right operand of
    `contains` is a string, neither of them a fact lookup - so this is that
    function's answer intersected with the ledger. Attribute roots come along
    too, because `failure_histogram.values()` reads failure_histogram and a
    version of this that only looked at bare names would miss it.

    THE ONE THING THAT MUST NOT HAPPEN HERE IS A HAND-WRITTEN LIST. The check
    this feeds is only as complete as this set, and a fact somebody adds to a
    gate row next year has to be covered on the day it is added.
    """
    values, _called, roots = _names_used(tree)
    return frozenset((values | roots) & set(spec.facts))


_FORK_KEYS = {"branch_on", "select", "routes", "no_match"}
_NO_MATCH_KEYS = {"outcome", "route", "error"}


def _validate_fork(spec: Spec, node_id: str, node: Mapping[str, Any]) -> None:
    """A fork is a DECLARED TABLE plus a strategy the engine owns. Four keys, all required.

    THE STRATEGY IS THE MACHINE'S, THE TABLE IS THE DOMAIN'S. That one sentence
    is the whole design, and it is DMN's hit policy borrowed wholesale. Before
    this, a fork was a `routes:` mapping in the YAML plus a Python function
    registered by NODE ID, so a ledger whose fork was not called
    `S0_MODALITY_FORK` or `S1_ROUTE_BY_FAILURE_MODE` could not have a fork at
    all, no matter what it wrote. The error it got - *"node S9_ROUTE routes by a
    key the engine has no rule for"* - named no key, no rule and no remedy.

    `no_match:` IS REQUIRED, AND THAT IS THE HALF THAT PAYS. The ML ledger
    already records why, in its own `uninspectable_facts.one_known_gap`: the
    failure-mode fork RAISES when the histogram carries only keys it has no route
    for. A fork that can be reached with an unroutable value and has not said
    what to do is a run that dies in front of a user. Requiring the key turns a
    latent crash into a question the author answers while writing, which is the
    cheapest possible moment.

    THREE ANSWERS ARE LEGAL AND `error:` IS ONE OF THEM. A ledger may say the
    unroutable case is an ENGINE BUG and should raise - that is what both ML
    forks do today, and writing it down is strictly better than the engine
    deciding it silently. What is not legal is saying nothing.
    """
    fork = node["fork"]
    where = f"node {node_id} `fork:`"
    _refuse_unknown_keys(
        fork, _FORK_KEYS, where=where, check_id="LF042", document=spec.path
    )
    for key in sorted(_FORK_KEYS):
        if key not in fork:
            raise LedgerError(
                "LF043",
                f"fork is missing `{key}`",
                where=where,
                document=spec.path,
                expected=_FORK_WHY[key],
                remedy=_FORK_REMEDY[key],
            )

    branch_on = str(fork["branch_on"])
    if branch_on not in spec.facts and branch_on not in (spec.raw.get("derived") or {}):
        raise LedgerError(
            "LF044",
            f"fork branches on {branch_on!r}, which is not a declared fact or derived value",
            where=where, document=spec.path,
            expected="a key of `facts:` or of `derived:`",
            remedy=(
                "declare it under `facts:` with its `type:`, `source:` and `scope:`, or "
                "branch on one that is already declared. A bare word that happens to be "
                "an enum member is not something to branch ON - it is something to "
                "branch TO."
            ),
        )

    select = fork["select"]
    if select not in FORK_SELECTORS:
        raise LedgerError(
            "LF045",
            f"fork selects by {select!r}",
            where=where, document=spec.path,
            found=repr(select),
            expected=f"one of {list(FORK_SELECTORS)}",
            remedy=(
                "`value` routes on the value itself; `argmax` routes on the key with "
                "the largest count in a mapping, ties resolved in the order the routes "
                "are written. The list is CLOSED and the engine owns it: a ledger picks "
                "a strategy, it never writes one."
            ),
        )

    routes = fork["routes"]
    if not isinstance(routes, Mapping) or not routes:
        raise LedgerError(
            "LF046", "fork `routes:` must be a non-empty mapping of value -> stage",
            where=where, document=spec.path, found=repr(routes),
        )
    for value, target in routes.items():
        if target not in spec.stages:
            raise LedgerError(
                "LF046",
                f"fork routes {value!r} to {target!r}, which is not a stage",
                where=where, document=spec.path,
                found=f"stages: {sorted(spec.stages)}",
                remedy=(
                    "a fork resumes the walk at a STAGE, never mid-stage. Landing on a "
                    "node would make `skip_leading_gates` ambiguous, and gate-skipping "
                    "ambiguity is the exact class of bug the per-gate row machinery "
                    "exists to prevent."
                ),
            )

    no_match = fork["no_match"]
    if not isinstance(no_match, Mapping) or len(no_match) != 1:
        raise LedgerError(
            "LF047",
            "fork `no_match:` must name exactly one of "
            f"{sorted(_NO_MATCH_KEYS)}",
            where=where, document=spec.path, found=repr(no_match),
        )
    _refuse_unknown_keys(
        no_match, _NO_MATCH_KEYS, where=f"{where} no_match", check_id="LF047",
        document=spec.path,
    )
    if "outcome" in no_match:
        spec.outcome_prefix(no_match["outcome"])
    elif "route" in no_match and no_match["route"] not in spec.stages:
        raise LedgerError(
            "LF047",
            f"fork no_match routes to {no_match['route']!r}, which is not a stage",
            where=where, document=spec.path, found=f"stages: {sorted(spec.stages)}",
        )
    elif "error" in no_match and not str(no_match["error"] or "").strip():
        raise LedgerError(
            "LF047",
            "fork no_match declares `error:` with no message",
            where=where, document=spec.path,
            remedy=(
                "say what the bug is. `error:` means the author asserts this case "
                "cannot legitimately happen, and a reader has to be able to check that "
                "claim against the sentence."
            ),
        )


_FORK_WHY = {
    "branch_on": "the declared fact or derived value whose value picks a route",
    "select": f"how the value picks a route: one of {list(FORK_SELECTORS)}",
    "routes": "a mapping of value -> stage",
    "no_match": "what to do when the value matches no route",
}
_FORK_REMEDY = {
    "branch_on": "name the fact you are branching on, e.g. `branch_on: modality`",
    "select": "`select: value` for a plain value, `select: argmax` for a histogram",
    "routes": "write the table: `routes: {tabular: stage_8_classical, ...}`",
    "no_match": (
        "add `no_match: {outcome: <an ACTION__ outcome>}`, or "
        "`no_match: {route: <stage>}`, or `no_match: {error: \"<why this cannot "
        "happen>\"}` if the unroutable case is an engine bug rather than a user's "
        "situation. This key is required because a fork that can be reached with an "
        "unroutable value and has not said what to do is a stack trace in front of a "
        "user."
    ),
}


def _validate_nodes(spec: Spec) -> None:
    """Every node must be something the engine can actually execute.

    A node the walker would silently skip is worse than a missing node: it looks
    like coverage. So anything without a compilable condition and an executable
    consequence is a load-time error, and adding a prose node to the YAML breaks
    the build until someone writes the handler.
    """
    for node_id, node in spec.node_index.items():
        stage_name = spec.node_stage[node_id]
        condition = node.get("condition")
        _require(condition is not None, f"node {node_id} has no condition")
        if node_id in CONDITION_HANDLERS:
            pass
        elif condition == "always":
            pass
        else:
            tree = compile_condition(condition)
            _check_names(spec, f"node {node_id}", tree)
            spec.conditions[node_id] = tree

        if _is_fork(node):
            _validate_fork(spec, node_id, node)
        elif isinstance(node.get("routes"), Mapping):
            raise LedgerError(
                "LF040",
                f"node {node_id} carries a bare `routes:` mapping",
                document=spec.path,
                expected="a `fork:` block declaring branch_on, select, routes and no_match",
                remedy=(
                    "wrap the table: `fork: {branch_on: <fact>, select: value, routes: "
                    "{...}, no_match: {...}}`. A bare mapping said which key went where "
                    "and never said what the key WAS or what to do when nothing matched, "
                    "so the engine supplied both from a Python function keyed by this "
                    "node's id - which is why no second ledger could have a fork at all."
                ),
            )
        elif "routes" in node:
            # A `routes:` LIST is prose - S9_HARDWARE_ROUTER's ladder is written
            # as sentences. Prose needs a handler like any other prose.
            _require(
                node_id in ACTION_HANDLERS,
                f"node {node_id} describes routes in prose and has no handler",
            )

        route = node.get("route")
        if route is not None:
            _require(route in spec.stages, f"node {node_id} routes to unknown stage {route!r}")

        outcome = node.get("outcome")
        if outcome is not None and outcome != "REROUTE":
            spec.outcome_prefix(outcome)
        if isinstance(outcome, str) and "{" in outcome:
            # A templated outcome stands for a family of real ones, and the
            # family has to be written down or `declared_outcomes` cannot see it
            # - which would make every outcome in it invisible to the
            # reachability check, the exact shape of hole that check exists for.
            emits = node.get("emits")
            _require(
                isinstance(emits, list) and bool(emits),
                f"node {node_id} declares the templated outcome {outcome!r} and no "
                "`emits` list saying which real outcomes it stands for",
            )
            for emitted in emits:
                _require(
                    isinstance(emitted, str) and "{" not in emitted,
                    f"node {node_id} emits {emitted!r}, which is not a concrete outcome",
                )
                spec.outcome_prefix(emitted)

        propose = node.get("propose")
        if propose is not None:
            _require(propose in spec.methods, f"node {node_id} proposes unknown method {propose!r}")
            # SC2: a proposal is a candidate, not an answer. It must be routed to
            # a stage that can commit, or already be inside one.
            if not spec.roles.commit_stages:
                raise LedgerError(
                    "LF041",
                    f"node {node_id} proposes {propose!r}, and this ledger declares "
                    "`commit_stages: []`",
                    document=spec.path,
                    remedy=(
                        "a ledger that commits to nothing has nowhere to turn a "
                        "candidate into a verdict. Either name the committing stage in "
                        "`contract.roles.commit_stages`, or drop the proposal."
                    ),
                )
            _require(
                route in spec.roles.commit_stages or stage_name in spec.roles.commit_stages,
                f"SC2: node {node_id} proposes {propose} without routing to one of "
                f"{list(spec.roles.commit_stages)} (contract.roles.commit_stages)",
            )

        executable = (
            node_id in ACTION_HANDLERS
            or node_id == spec.roles.gate_sweep_node
            or _is_fork(node)
            or propose is not None
            or (outcome is not None)
            or route is not None
        )
        _require(
            executable,
            f"node {node_id} has no outcome, no route, no proposal and no handler - "
            "the engine would skip it silently",
        )
        if "effect" in node and node_id not in ACTION_HANDLERS:
            raise SpecError(
                f"node {node_id} carries an `effect:` the engine has no handler for"
            )

    # Every stage a gate's on_fail names must exist.
    for gate_id, gate in spec.gates.items():
        on_fail = gate["on_fail"]
        if "route" in on_fail:
            _require(
                on_fail["route"] in spec.stages,
                f"gate {gate_id} on_fail routes to unknown stage {on_fail['route']!r}",
            )
        for target in (on_fail.get("route_by_class") or {}).values():
            _require(
                target in spec.stages,
                f"gate {gate_id} on_fail routes to unknown stage {target!r}",
            )
        if "outcome" in on_fail:
            spec.outcome_prefix(on_fail["outcome"])


def _static_checks(spec: Spec, text: str) -> None:
    """The INVARIANTS. These stay Python, and they stay Python on purpose.

    A schema can say "this key must be a string". It cannot say "exactly one node
    may mint the irreversible verdict." Every part of the five-gate honesty test
    is that second kind of sentence, and moving it into a declarative rule
    language would be handing an author the ability to write a ledger that
    declares itself exempt - because the exemption would be IN THE LEDGER, the
    one document the author controls.

    So these are parameterised by `contract.roles` and by the gated prefix, and
    they are not weakened by being parameterised: what a ledger gets to choose is
    the NAME of its commit stage and the SPELLING of its irreversible prefix.
    What it does not get to choose is that exactly one node may mint it, that the
    node must sit in a commit stage, or that a sweep must ask every gate first.

    SC2 and SC3 are enforced in `_validate_nodes` and `load_spec`, where the
    thing they check is being read.
    """
    _check_commit_shape(spec)
    _check_ml_size_table(spec)


def _check_commit_shape(spec: Spec) -> None:
    """SC1, generalised: exactly one node mints, and the sweep runs before it.

    A ledger with `commit_stages: []` has nothing here to protect and says so;
    every check below is skipped and that is the declared answer, not an
    omission.
    """
    prefix = spec.gated_prefix
    if prefix is None:
        _require(
            not spec.roles.commit_stages,
            "a ledger with commit stages and no gated prefix reached _static_checks; "
            "_read_gated_prefix should have refused it",  # pragma: no cover
        )
        spec.train_outcomes = []
        return

    # EVERY SITE, NOT EVERY NODE `outcome:`. This read `node.get("outcome")` and
    # nothing else, which was correct for exactly as long as a node's `outcome:`
    # was the only way to state one. `fork: no_match: {outcome: ...}` made it
    # wrong without touching this line: a ledger could mint the gated prefix from
    # a fork in any node it liked and SC1 would report `found []`, satisfied that
    # nobody minted at all. `Spec.outcome_sites()` is the single enumeration, so
    # a future sixth site is caught here by construction.
    minters = sorted(
        {
            site.node
            for site in spec.outcome_sites()
            if site.node is not None and site.outcome.startswith(prefix)
        }
    )
    stated_by_gates = sorted(
        site.where
        for site in spec.outcome_sites()
        if site.node is None and site.outcome.startswith(prefix)
    )
    _require(
        not stated_by_gates,
        f"SC1: {prefix} is the gated prefix and is stated outside the graph, at "
        f"{stated_by_gates}. A gate's `on_fail` and the unsubstantiated outcome are "
        "reached without passing the gates, which is what the prefix means.",
    )
    _require(
        minters == [spec.mint_node],
        f"SC1: exactly one node may emit a {prefix} outcome - "
        f"contract.outcome_prefixes.{prefix}.mintable_only_at names {spec.mint_node!r} - "
        f"and found {minters}",
    )

    mint = spec.node_index[str(spec.mint_node)]
    stage = spec.node_stage[str(spec.mint_node)]
    _require(
        stage in spec.roles.commit_stages,
        f"SC1: {spec.mint_node} mints {prefix} from stage {stage!r}, which is not one "
        f"of contract.roles.commit_stages {list(spec.roles.commit_stages)}",
    )

    emits = list(mint["emits"])
    expected = {f"{prefix}{m}" for m in spec.methods if m != spec.no_proposal}
    _require(
        set(emits) == expected,
        f"{spec.mint_node}.emits disagrees with `methods`: "
        f"only in emits {sorted(set(emits) - expected)}, "
        f"only in methods {sorted(expected - set(emits))}",
    )
    # AND THE FENCE ITSELF, which `emits` only half states. `emits` says what the
    # template stands for; it does not say that nothing ELSE at this node states
    # a gated outcome. A `fork: no_match: {outcome: TRAIN__DPO}` written into the
    # minting node satisfies both checks above - right node, right emits - and
    # still hands out the irreversible verdict from a branch nobody costed.
    off_menu = sorted(
        f"{site.outcome} at {site.where}"
        for site in spec.outcome_sites()
        if site.outcome.startswith(prefix) and site.outcome not in expected
    )
    _require(
        not off_menu,
        f"SC1: {prefix} outcomes outside {spec.mint_node}.emits are stated at "
        f"{off_menu}. The gated prefix names one family and `emits:` is that family; "
        "an outcome in it that no method backs is a verdict with nothing to cost.",
    )
    spec.train_outcomes = emits

    # And the sweep, which `_check_sweep_is_declared` has already proved exists
    # and lives here, must be written ABOVE the mint. A sweep below the mint asks
    # its questions of a verdict that has already been given.
    sweep = spec.roles.gate_sweep_node
    if not sweep:
        return
    order = [n.get("node") for n in spec.stages[spec.node_stage[sweep]]]
    _require(
        order.index(sweep) < order.index(str(spec.mint_node)),
        f"SC1: the gate sweep {sweep!r} is written AFTER the minting node "
        f"{spec.mint_node!r} in {spec.node_stage[sweep]}. A sweep below the mint "
        "asks its questions of a verdict that has already been given.",
    )


def _check_sweep_is_declared(spec: Spec) -> None:
    """THE SWEEP IS PART OF THE HONESTY TEST, NOT AN ML COMPUTATION.

    It is what re-asks every required gate under the PROPOSAL'S OWN class before
    anything mints. Without it a run that passed a gate on one spine could
    propose a method of another class and never be asked that class's question -
    the exact bypass `contract.path_semantics.latching` exists to close. So a
    ledger with gates and a commit stage must name one, and it must live in a
    commit stage.

    CHECKED BEFORE `_validate_nodes` ON PURPOSE. A node that is the sweep is
    executable BECAUSE it is the sweep, so a ledger whose `gate_sweep_node`
    points somewhere else used to fail with *"node S9_SWEEP has no outcome, no
    route, no proposal and no handler"* - true, useless, and about the wrong
    node. Ordering the checks so the cause is reported before the symptom is the
    whole reason tiers exist.
    """
    # ONE CONDITION, NOT TWO. This read `not spec.roles.commit_stages or not
    # spec.required_gates`, and the second half was the disabling clause: a
    # ledger with `required_gates: []` skipped the sweep requirement entirely.
    # LF027 now refuses a gated prefix over an empty gate list at load, so a
    # committing ledger always has gates and this half can never be the reason to
    # skip. Removing it means that if LF027 is ever loosened, this fails closed
    # instead of quietly waving the ledger through.
    if not spec.roles.commit_stages:
        return
    sweep = spec.roles.gate_sweep_node
    if not sweep:
        raise LedgerError(
            "LF050",
            f"this ledger requires gates {spec.required_gates} and commits at "
            f"{list(spec.roles.commit_stages)}, and declares no `gate_sweep_node`",
            document=spec.path,
            line=spec.line_of.get("contract"),
            expected="contract.roles.gate_sweep_node: <a node in the commit stage>",
            remedy=(
                "the sweep is what re-asks every gate under the proposal's own class. "
                "Without it a gate passed under some other class looks passed, and the "
                "run either mints on a question nobody asked or dies at the exit check. "
                "Add a node with `condition: always` and an `order:` listing every "
                "required gate, and name it here."
            ),
        )
    if sweep not in spec.node_index:
        raise LedgerError(
            "LF051",
            f"`contract.roles.gate_sweep_node` names {sweep!r}, which is not a node",
            document=spec.path,
            line=spec.line_of.get("contract"),
            found=f"nodes in the commit stages: "
                  f"{sorted(n for n, s in spec.node_stage.items() if s in spec.roles.commit_stages)}",
        )
    stage = spec.node_stage[sweep]
    if stage not in spec.roles.commit_stages:
        raise LedgerError(
            "LF051",
            f"`contract.roles.gate_sweep_node` {sweep!r} lives in stage {stage!r}",
            document=spec.path,
            line=spec.line_of.get("contract"),
            expected=f"a node in one of {list(spec.roles.commit_stages)}",
            remedy=(
                "the sweep has to run on the way to the mint, and the mint is in a "
                "commit stage. A sweep anywhere else is a sweep some proposals walk "
                "past."
            ),
        )


def _check_ml_size_table(spec: Spec) -> None:
    """SC4, and it is a theorem about ONE LEDGER'S TABLE rather than about ledgers.

    Kept, guarded on the node existing, and named honestly. Every other check in
    this file is a property any ledger must have; this one is about
    `S9_SIZE_TO_METHOD`, a node only the ML ledger has. It reached that node by
    name and would have raised `KeyError` on any second ledger - one more instance
    of the class this pass exists to fix, and the reason it is not fixed the same
    way is that it is not a NAME the engine needs, it is a CHECK one domain wants.

    The right home is a per-ledger check registry, which the ledger's own
    `static_checks:` block is already the documentation half of. That is its own
    piece of work; skipping this check for ledgers that have no such node is the
    honest interim, and weakening it for the ledger that does would not be.
    """
    node = spec.node_index.get("S9_SIZE_TO_METHOD")
    if node is None or not isinstance(node.get("table"), list):
        return
    # SC4: the size table's ranks are numbers, and nothing compares
    # required_rank to one. The second half is the half that matters - it is what
    # stops the string-versus-256 defect returning through a different field.
    table = node["table"]
    for row in table:
        lo, hi = row.get("rank_min"), row.get("rank_max")
        both_null = lo is None and hi is None
        both_int = isinstance(lo, int) and isinstance(hi, int)
        _require(
            both_null or both_int,
            f"SC4: size table row {row.get('examples')!r} has non-integer rank bounds",
        )
        if both_null:
            _require("note" in row, f"SC4: row {row.get('examples')!r} has null ranks and no reason")
        _require(row.get("method") in spec.methods, f"SC4: row names unknown method {row.get('method')!r}")
        _require(isinstance(row.get("full_ft_offered"), bool), "SC4: full_ft_offered must be a bool")
    for node_id, node in spec.node_index.items():
        condition = node.get("condition")
        if isinstance(condition, str) and "required_rank" in condition:
            raise SpecError(
                f"SC4: node {node_id} compares required_rank in a condition; "
                "the table it derives from is a table of bands, not a number to test"
            )
    for gate_id, gate in spec.gates.items():
        for row in gate["passes_when"]:
            if "required_rank" in row["requires"]:
                raise SpecError(f"SC4: gate {gate_id} compares required_rank")


_SPEC_CACHE: dict[Path, Spec] = {}

#: Where a ledger that is not the first one lives. A DIRECTORY RATHER THAN A
#: LIST, for the reason `app/instructions/capabilities.py` gives about the tool
#: list it derives: a second place naming which ledgers ship is a second place
#: that goes stale, and it goes stale in the direction nobody looks - a ledger
#: added and not listed is simply invisible, with nothing red to say so.
LEDGERS_DIR = LEDGER_ROOT / "docs" / "ledgers"

#: What a thread with no ledger of its own runs, written the way it is stored:
#: relative to the repository, so a checkout that moves does not orphan every
#: row. `resolve_ledger` is the one place that turns it into a file.
DEFAULT_LEDGER = "docs/diagnosis_engine.yaml"


def resolve_ledger(path: Path | str | None) -> Path:
    """A ledger as it is WRITTEN DOWN -> the file on this machine.

    A stored ledger path is a promise that must survive the checkout moving, so
    the form that gets stored is relative to the repository root and this is the
    single place that reads it. An absolute path is honoured as given - a test
    or a ledger outside the tree is a real case - and `None` is the default
    ledger rather than an error, because "this thread never said" and "this
    thread said something unreadable" are different states and only the second
    one is a fault.
    """
    if path is None:
        path = DEFAULT_LEDGER
    candidate = Path(str(path))
    if candidate.is_absolute():
        return candidate
    return (LEDGER_ROOT / candidate).resolve()


def spec_at(path: Path | str | None) -> Spec:
    """The ledger at `path`, loaded once per file. The only I/O in this module.

    `default_spec()` is this function on the default ledger and nothing else, so
    there is one cache, one loader and one place a ledger becomes a `Spec`. The
    cache is keyed on the RESOLVED path, so `docs/diagnosis_engine.yaml` and the
    absolute spelling of the same file are one entry rather than two copies that
    could be validated to different conclusions.

    A ledger that will not load RAISES, here, at the first call that wanted it.
    There is no fallback to the default and there must not be: a thread that
    said it was an AI-engineering thread and silently got the ML ledger would
    diagnose confidently against the wrong knowledge, which is the whole defect
    this surface exists to remove. `_load_origin_policy` states the rule in the
    engine's own voice - safe and broken is not the same as safe and working.
    """
    resolved = resolve_ledger(path)
    if resolved not in _SPEC_CACHE:
        _SPEC_CACHE[resolved] = load_spec(resolved)
    return _SPEC_CACHE[resolved]


def default_spec() -> Spec:
    """The repo's first ledger, loaded once.

    STILL HERE, AND SCOPED. Two callers genuinely have no thread and so no
    ledger of their own: the harness's standing walk over nothing, and tool
    registration, which happens at import before any conversation exists.
    Anything holding a thread should be asking `spec_at` through the ledger the
    registry injected, and the unconditional use of this by something that knows
    which conversation it is in is the defect, not the function.
    """
    return spec_at(SPEC_PATH)


def known_ledgers() -> tuple[Path, ...]:
    """Every ledger this build ships, discovered rather than listed.

    The default ledger first, then whatever is in `docs/ledgers/`, sorted so the
    answer does not depend on the order a filesystem hands files back.

    THIS IS WHAT REGISTRATION IS CHECKED AGAINST, and it is why it is derived.
    A tool declaring `measures=("has_traces",)` - a fact only the AI-engineering
    ledger declares - was refused at import with a sentence that was right at
    every step and consulted the wrong file at every step. What may be declared
    is "a fact some ledger in this product declares"; what may be STAMPED is
    decided per call, against the ledger the thread is actually running.
    """
    found = [resolve_ledger(SPEC_PATH)]
    if LEDGERS_DIR.is_dir():
        for one in sorted(LEDGERS_DIR.glob("*.yaml")):
            resolved = one.resolve()
            if resolved not in found:
                found.append(resolved)
    return tuple(found)


# ---------------------------------------------------------------------------
# Facts.

_HELPER_KEYS = ("user_confirms", "user_can_produce")
_HARDWARE_FACTS = ("accelerator", "vram_gb", "ram_gb", "disk_free_gb")


def bare(value: Any) -> Any:
    """The value inside a `Fact`, or the value itself if it is already bare."""
    return value.value if isinstance(value, Fact) else value


# `supplied_facts()` used to live here and answered "which keys did the caller
# give a value for". It is gone, and deliberately rather than by tidying:
# `resolve_facts` returns an origin for every fact, and DEFAULTED is exactly the
# answer that function gave. Two ways to ask the same question is the drift
# machine this file argues against everywhere else, and this one had already
# drifted once - it tracked PRESENCE, and presence was being read as provenance.


def unsupplied_value(decl: Mapping[str, Any]) -> Any:
    """What a fact resolves to when nobody supplied it.

    The declared default, else the empty list for a `multi`, else null. Copied
    and never handed out by reference: the spec is cached for the life of the
    process, so a run that mutated its default would contaminate every run after
    it in a way no single test could see.

    Factored out because two callers need the same answer, and they must not be
    allowed to disagree. `validate_facts` uses it for a fact the caller left out.
    `_masked_row_passes` uses it for a fact the caller DID supply but cannot
    vouch for, which is the same state of knowledge from the gate's point of
    view - the engine has no value it is entitled to use.
    """
    if "default" in decl:
        default = decl["default"]
        if isinstance(default, dict):
            return dict(default)
        if isinstance(default, list):
            return list(default)
        return default
    if "multi" in decl:
        return []
    return None


def resolve_facts(facts: Mapping[str, Any], spec: Spec) -> tuple[dict[str, Any], dict[str, str]]:
    """Type-check the fact dict against the ledger, apply defaults, read origins.

    Returns (values, origins). Every declared fact appears in both, so nothing
    downstream has to handle a missing key, and `origins` is a complete answer to
    "where did each of these come from" rather than a partial one covering only
    what was interesting at the time.

    Rejects callables anywhere. That is not decoration: it is the mechanical
    reason a user's model can fill facts but can never decide a gate. There is
    nothing in a fact dict the engine will call back into.

    AN EXPLICIT NULL IS TREATED AS AN ABSENT FACT, and this is the fix for a
    defect a property test found rather than a preference. A fact's declared
    `default` is the file's own honest reading of "nobody has done this yet" -
    `failure_histogram: {}`, `fewshot_tried: false`. Omitting the key applied
    that default; passing the key with `None` skipped it, so the two ways a
    caller says "I do not know" gave two different answers. One of them raised:
    `sum(failure_histogram.values())` against a null is not a false answer, it is
    a crash, and a blank field on an intake form sends exactly that. The two
    inputs mean the same thing and now resolve the same way.

    A `Fact(value, origin)` IS ACCEPTED WHEREVER A BARE VALUE IS, and a bare
    value is read as whatever `fact_origins.origin_of_an_unattributed_value`
    says - ASSERTED. The engine never guesses a provenance upward. The one origin
    a caller may not supply is DEFAULTED: that word means the ledger's own
    default was applied, and only the engine is entitled to say so.
    """
    for key, value in facts.items():
        if key in _HELPER_KEYS:
            _require_fact(isinstance(bare(value), bool), f"{key} must be a bool")
            continue
        if key not in spec.facts:
            # THE LEDGER THAT REFUSED, NOT THE FIRST ONE. This named
            # `docs/diagnosis_engine.yaml` as a literal, so a run against the AI
            # engineering ledger that mentioned an undeclared fact was told to go
            # and look in the machine-learning file - the tenth ML leak, in the
            # one message a person actually meets while a second ledger is being
            # written, which is precisely when being sent to the wrong document
            # costs the most.
            raise FactError(
                f"{key!r} is not a declared fact; the ledger is in {spec.path}"
            )
        if (
            isinstance(value, Fact)
            and value.origin in ENGINE_ONLY_ORIGINS
            and not isinstance(value, Settled)
        ):
            # `Settled` IS THE ENGINE SAYING IT, which is the one thing this
            # refusal was ever asking for. It cannot arrive from a model - a
            # tool call is JSON and JSON carries no Python class - so the only
            # route to one is `evidence.assemble_facts` reading a row the
            # harness itself wrote. See `Settled`.
            raise FactError(
                f"fact {key!r} was supplied with origin {value.origin!r}. That origin "
                "means the engine applied the ledger's own default, and only the "
                "engine may say that. Leave the fact out to get the default."
            )
        if callable(bare(value)):
            raise FactError(
                f"fact {key!r} is callable. Facts are values. A callable fact would let "
                "something outside the engine decide a gate at gate time."
            )

    unattributed = spec.unattributed_origin
    resolved: dict[str, Any] = {}
    origins: dict[str, str] = {}
    for name, decl in spec.facts.items():
        supplied = facts.get(name)
        value = bare(supplied)
        if value is not None:
            resolved[name] = _coerce(name, decl, value)
            origins[name] = supplied.origin if isinstance(supplied, Fact) else unattributed
        else:
            resolved[name] = unsupplied_value(decl)
            origins[name] = DEFAULTED
    for key in _HELPER_KEYS:
        resolved[key] = bool(bare(facts.get(key, False)))
    return resolved, origins


def validate_facts(facts: Mapping[str, Any], spec: Spec) -> dict[str, Any]:
    """The values half of `resolve_facts`, kept for callers that only want them."""
    return resolve_facts(facts, spec)[0]


def _require_fact(condition: bool, message: str) -> None:
    if not condition:
        raise FactError(message)


#: The shapes a `multi:` fact may arrive in. A bare string is one member -
#: `need_type: "style"` is what a form sends when only one box is ticked - and
#: everything else has to be an ordered or unordered collection of members.
#: `Mapping` is deliberately NOT here: `list({"style": 1})` is `["style"]`, so
#: accepting a mapping would silently read a dict's KEYS as the answer and the
#: caller would never learn their values went nowhere.
_MULTI_SHAPES = (list, tuple, set, frozenset)

#: `map[failure_mode,int]` -> `("failure_mode", "int")`. One regex rather than a
#: string split, so a declared type this file does not understand is caught by
#: `_map_types` returning nothing rather than by an IndexError three lines on.
_MAP_TYPE = re.compile(r"^map\[\s*([^,\]]+?)\s*,\s*([^,\]]+?)\s*\]$")

#: How a declared scalar type is checked. One table, read by `_coerce` for a
#: bare fact and by `_coerce_map` for a mapping's members, so the two can never
#: disagree about what `int` means - which is how `map[failure_mode,int]` came
#: to accept `{"wrong_style": "lots"}` and crash `sum()` two stages later.
_SCALAR_CHECKS: dict[str, tuple[Callable[[Any], bool], str]] = {
    "bool": (lambda v: isinstance(v, bool), "a bool"),
    "int": (lambda v: isinstance(v, int) and not isinstance(v, bool), "an int"),
    "float": (
        lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "a number",
    ),
    "str": (lambda v: isinstance(v, str), "a str"),
}


def _map_types(declared: str) -> tuple[str, str] | None:
    match = _MAP_TYPE.match(str(declared))
    return (match.group(1), match.group(2)) if match else None


def _coerce(name: str, decl: Mapping[str, Any], value: Any) -> Any:
    """Every rejection here is a `FactError`, and that is the whole contract.

    A fact arrives from a caller - a model filling `run_diagnosis`, a person
    typing into a form, a row read back out of the evidence ledger - and a
    caller can send anything. `FactError` is the one exception every layer above
    this catches and turns into a sentence: `run_diagnosis` returns
    `rejected_fact`, `state_facts` returns `rejected_fact`, the tool route
    answers 400. A raw builtin escaping from here has no handler anywhere in the
    stack and becomes an unhandled 500 with a traceback, which is the same
    product promise broken in the ugliest possible way.

    It was broken exactly here. `items = [value] if isinstance(value, str) else
    list(value)` raised `TypeError: 'int' object is not iterable` on
    `{"need_type": 5}` - one line from the mapping branch that had been raising
    a proper `FactError` all along - and a 200,000-draw fuzz found 763 crashes
    of which every single one was that signature. So the rule is stated rather
    than implied: NOTHING IN THIS FUNCTION MAY RAISE ANYTHING BUT `FactError`,
    and a shape it does not recognise is a rejection with a message, never an
    exception from a builtin that happened to be handed the wrong type.
    """
    if value is None:
        return None
    if "enum" in decl:
        _require_fact(
            value in decl["enum"],
            f"fact {name!r} = {value!r} is not one of {decl['enum']}",
        )
        return value
    if "multi" in decl:
        if isinstance(value, str):
            items: list[Any] = [value]
        elif isinstance(value, _MULTI_SHAPES):
            items = list(value)
        else:
            raise FactError(
                f"fact {name!r} must be one of {decl['multi']} or a list of them, "
                f"got {value!r}. A single member may be sent on its own; anything "
                "that is not a member and not a list of members is not an answer "
                "to this fact."
            )
        for item in items:
            _require_fact(
                item in decl["multi"],
                f"fact {name!r} member {item!r} is not one of {decl['multi']}",
            )
        return items
    declared = decl.get("type")
    check = _SCALAR_CHECKS.get(str(declared))
    if check is not None:
        predicate, described = check
        _require_fact(predicate(value), f"fact {name!r} must be {described}, got {value!r}")
    elif declared and str(declared).startswith("map"):
        _require_fact(isinstance(value, Mapping), f"fact {name!r} must be a mapping, got {value!r}")
        return _coerce_map(name, str(declared), value)
    return value


def _coerce_map(name: str, declared: str, value: Mapping[Any, Any]) -> dict[str, Any]:
    """A `map[K,V]` fact, with its VALUES checked and its keys left open.

    The values are checked because nothing was checking them and the engine does
    arithmetic on them: `failure_histogram` is declared `map[failure_mode,int]`,
    `sum(failure_histogram.values())` and `max(...)` are what S1 routes on, and
    `{"wrong_style": "lots"}` sailed through `isinstance(value, Mapping)` to
    raise `TypeError: unsupported operand type(s) for +: 'int' and 'str'` inside
    `_fn_sum`. That is the same defect as the `multi` one, in the branch next
    door, and the fuzz that found the first one never drew a mapping with a
    string in it.

    THE KEYS ARE DELIBERATELY NOT CHECKED AGAINST A CLOSED SET, and that is not
    an oversight. `failure_mode` is not a declared enum - the spec says so
    itself under `uninspectable_facts.one_known_gap` - so there is no list here
    to check against, and inventing one would close a gap the file records
    honestly. What IS required is that a key is a string, because a key is a
    name and every caller that reaches this through JSON can only send strings
    anyway; a non-string key is a Python caller doing something the wire cannot
    express.
    """
    types = _map_types(declared)
    value_check = _SCALAR_CHECKS.get(types[1]) if types else None
    out: dict[str, Any] = {}
    for key, item in value.items():
        _require_fact(
            isinstance(key, str),
            f"fact {name!r} is a mapping keyed by name, and {key!r} is not a name",
        )
        if value_check is not None and item is not None:
            predicate, described = value_check
            _require_fact(
                predicate(item),
                f"fact {name!r} is declared {declared} and {key!r} holds {item!r}, "
                f"which is not {described}",
            )
        out[key] = item
    return out


# ---------------------------------------------------------------------------
# Engine state.

_ENGINE_NAMES = {
    "path",
    "proposed_method",
    "method_class",
    "struck_methods",
    "size_row",
    "required_rank",
    "route",
    "hardware_permits",
    "from_scratch_cost_estimate",
    "labels_are_open_ended",
    "methods",
    "gates",
    "contract",
}


def _render(tree: ast.expr) -> str:
    """A compiled condition back as text, for a message a person can act on.

    `ast.unparse` can itself raise on a tree it does not expect, and a failure
    inside an error path is how a real error gets replaced by a confusing one.
    So the fallback is the node type, which is worse than the source and much
    better than a second traceback.
    """
    try:
        return repr(ast.unparse(tree))
    except Exception:  # noqa: BLE001 - never let the message-builder be the failure
        return f"<{type(tree).__name__}>"


@dataclass
class _State:
    spec: Spec
    facts: dict[str, Any]
    path: list[PathEntry] = field(default_factory=list)
    #: node id -> the facts its condition actually read. See `Diagnosis.reached_by`.
    reached: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: Overwritten in `diagnose` with `spec.no_proposal`. The empty string is not
    #: a default anybody could mistake for a legitimate sentinel - a ledger names
    #: its own, and the engine has no opinion about the spelling.
    proposed_method: str = ""
    struck_methods: set[str] = field(default_factory=set)
    struck_outcomes: set[str] = field(default_factory=set)
    constraints: set[str] = field(default_factory=set)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    helper_answers: list[dict[str, Any]] = field(default_factory=list)
    size_row: dict[str, Any] | None = None
    required_rank: int | None = None
    route: str | None = None
    hardware_permits: bool | None = None
    hardware_reference: dict[str, Any] | None = None
    stage_entries: dict[str, int] = field(default_factory=dict)
    failed_gates: dict[str, str] = field(default_factory=dict)
    origins: dict[str, str] = field(default_factory=dict)
    #: gate_id -> the facts that gate read which the caller supplied under an
    #: origin the ledger does not admit. Written only when that was the reason
    #: the gate did not pass.
    unsubstantiated: dict[str, list[str]] = field(default_factory=dict)

    def method_class(self) -> str:
        return self.spec.method_class(self.proposed_method)

    def enter_stage(self, stage: str) -> None:
        count = self.stage_entries.get(stage, 0) + 1
        if count > 2:
            raise EngineError(
                f"ERROR__CYCLE: stage {stage} would be entered a third time. "
                f"path so far: {[e.id for e in self.path]}"
            )
        if sum(self.stage_entries.values()) + 1 > MAX_STAGE_ENTRIES:
            raise EngineError("ERROR__CYCLE: runaway walk")  # pragma: no cover
        self.stage_entries[stage] = count

    def note_node(self, node_id: str) -> None:
        """Record that this node was evaluated, and what it was asked.

        The clause is the node's own `condition:` READ OFF THE SPEC, not
        rebuilt: `ast.unparse` of the compiled tree would put this file's dialect
        on the wire in place of the author's, and the author's is the string a
        person can check against the file. Null for a gate's own node, which has
        no condition of its own - see `PathEntry`.
        """
        declared = self.spec.node_index.get(node_id) or {}
        condition = declared.get("condition")
        self.path.append(
            PathEntry(
                node_id,
                "node",
                clause=None if condition is None else " ".join(str(condition).split()),
            )
        )

    def eval(self, tree: ast.expr) -> Any:
        """Evaluate one condition. THE ONLY WAY OUT OF HERE IS AN ENGINE ERROR.

        `_coerce` is where a caller's value is supposed to be rejected, and it
        now rejects every shape the ledger does not describe. This is the second
        line, and it exists because the first line has been wrong twice in the
        same release - once for `multi`, once for the values inside a `map` -
        and both times a builtin raised from somewhere down here and escaped the
        whole stack as an unhandled 500.

        So anything that is not already one of this module's own exceptions is
        turned into one, with the condition that raised it printed. That is not
        a swallow: nothing is answered False, nothing continues, the run still
        stops. What changes is that it stops as `EngineError`, which every
        caller in this repository already handles, and that the message names
        the expression instead of pointing at a line inside `sum()`.
        """
        try:
            return _Evaluator(self).visit(tree)
        except (EngineError, SpecError, FactError):
            raise
        except RecursionError:  # pragma: no cover - a spec deep enough to blow the stack
            raise EngineError(
                f"condition {_render(tree)} recursed past the interpreter's limit"
            ) from None
        except Exception as error:  # noqa: BLE001 - see the docstring: this is the net
            raise EngineError(
                f"condition {_render(tree)} could not be evaluated: "
                f"{type(error).__name__}: {error}. The engine reached a value it "
                "cannot compute with. That is a defect in this file or in the "
                "spec, and it is never a verdict."
            ) from error

    def eval_condition(self, node_id: str) -> bool:
        tree = self.spec.conditions.get(node_id)
        if tree is None:
            raise EngineError(f"node {node_id} has no compiled condition")  # pragma: no cover
        # WHAT IT READ, RECORDED WHERE IT IS READ. The walk evaluates every
        # condition exactly once; capturing the reached names here costs that
        # evaluation nothing and means nothing has to re-run a condition, or
        # rebuild a state, to know which operand decided it.
        seen: set[str] = set()
        try:
            answer = _truthy(_Evaluator(self, watch=seen).visit(tree))
        except (EngineError, SpecError, FactError):
            raise
        except RecursionError:  # pragma: no cover
            raise EngineError(
                f"condition {_render(tree)} recursed past the interpreter's limit"
            ) from None
        except Exception as error:
            raise EngineError(f"condition {_render(tree)} could not be evaluated: {error}") from error
        self.note_reached(node_id, seen)
        return answer

    def note_reached(self, node_id: str, names: set[str]) -> None:
        """Record which declared facts that node's condition actually read."""
        self.reached[node_id] = tuple(sorted(names & set(self.spec.facts)))


def _truthy(value: Any) -> bool:
    if value is None:
        return False
    return bool(value)


# ---------------------------------------------------------------------------
# The evaluator.


#: How many nodes one condition may evaluate before the engine gives up.
#:
#: THE DEBT THIS PAYS, in `docs/PHASES.md`'s own words: *"The condition dialect
#: has no bound on cost. Arithmetic on text is refused now... but nothing bounds
#: a comprehension over a large map, and nothing times a condition out. A ledger
#: is authored rather than user input, so this is a ROBUSTNESS debt, not a
#: security one - and it should be written down as which before somebody treats
#: a ledger as untrusted input."*
#:
#: Written down as which: **robustness.** A ledger is a file a person wrote and
#: reviewed, so nothing here is defending against an attacker. What it defends
#: against is an author's mistake becoming a hang - `sum(x for x in big_map)`
#: over a fact that turned out to hold half a million rows is a condition that
#: runs for a minute and looks like the product being broken.
#:
#: A STEP COUNT AND NOT A CLOCK, and the choice is the load-bearing part. A
#: wall-clock timeout makes a ledger's validity a property of the machine it is
#: evaluated on: the same file passes on a laptop and fails in CI under load,
#: and a diagnosis that depends on how busy the box was is not a diagnosis. A
#: step count is deterministic - the same condition over the same facts costs
#: the same everywhere - so a ledger that loads here loads for everybody.
#:
#: It bounds BOTH halves the debt names with one mechanism: a comprehension over
#: a large map spends a step per item, and a condition that would run long
#: spends steps to do it.
#:
#: THE NUMBER, MEASURED. Swept over every fixture sheet this repository has, the
#: most expensive condition in either shipped ledger costs **35 steps** - the
#: gate-ladder check `not all(g in gates_passed_under(path, ...))`, which is a
#: comprehension over the five gates. Nothing else reaches 20. 100,000 leaves
#: more than three orders of magnitude of headroom, which
#: is deliberate: this is a bound on RUNAWAY, not a budget anybody should have
#: to think about while authoring. A condition that reaches it is not a
#: condition somebody wrote slightly too generously; it is one that is not going
#: to finish.
CONDITION_STEP_BUDGET = 100_000


class _Evaluator:
    """A restricted interpreter for the spec's condition dialect.

    Unknown values are `None` and a `None` in an ordering comparison makes the
    comparison FALSE rather than raising. That is the honest reading: a score
    that has not been measured is not greater than a target. Type mismatches
    that are not `None` - the string-versus-256 shape - raise, loudly, because
    that is a defect in the file and silently answering False is how that one
    stayed hidden.

    **AND IT IS BOUNDED.** See `CONDITION_STEP_BUDGET` for the argument and for
    why the bound is a step count rather than a clock.
    """

    def __init__(
        self,
        state: _State,
        budget: int = CONDITION_STEP_BUDGET,
        watch: set[str] | None = None,
    ) -> None:
        self.state = state
        self.budget = int(budget)
        self.steps = 0
        #: Every name `resolve` was asked for, when a caller wants to know
        #: which operands the short-circuit actually reached. One door, so
        #: recording here records everything - see `PathEntry.reached`.
        self.watch = watch

    # -- entry -----------------------------------------------------------
    def visit(self, node: ast.AST) -> Any:
        # ONE COUNTER, AT THE ONE DOOR. Every visit_* method reaches its
        # children through this, so counting here counts everything -
        # including a comprehension's per-item work, which is where the cost
        # actually lives. A counter inside `_comprehend` would bound the case
        # somebody thought of and nothing else.
        self.steps += 1
        if self.steps > self.budget:
            raise EngineError(
                f"condition {_render(node)} did not finish within "
                f"{self.budget:,} evaluation steps and the engine stopped. "
                "NOTHING WAS ANSWERED: this is not a False and it is not a "
                "verdict - a gate decided by a condition that ran out of budget "
                "would be a gate decided by exhaustion. Almost always this is a "
                "comprehension or a sum over a fact that turned out to hold far "
                "more rows than the condition's author expected. Look at what "
                "that fact actually holds for this thread."
            )
        method = getattr(self, f"visit_{type(node).__name__}", None)
        if method is None:
            raise SpecError(f"condition uses unsupported syntax: {type(node).__name__}")
        return method(node)

    # -- literals and names ----------------------------------------------
    def visit_Constant(self, node: ast.Constant) -> Any:
        return node.value

    def visit_Name(self, node: ast.Name) -> Any:
        return self.resolve(node.id)

    def resolve(self, name: str) -> Any:
        if self.watch is not None:
            self.watch.add(name)
        state = self.state
        if name in state.facts:
            return state.facts[name]
        if name == "proposed_method":
            return state.proposed_method
        if name == "method_class":
            return state.method_class()
        if name == "struck_methods":
            return state.struck_methods
        if name == "size_row":
            return state.size_row
        if name == "required_rank":
            return state.required_rank
        if name == "route":
            return state.route
        if name == "hardware_permits":
            return state.hardware_permits
        if name == "labels_are_open_ended":
            closed = state.facts.get("labels_are_closed_set")
            return None if closed is None else (not closed)
        if name == "from_scratch_cost_estimate":
            return _from_scratch_cost(state)
        if name == "path":
            return state.path
        if name == "methods":
            return state.spec.methods
        if name == "gates":
            return state.spec.gates
        if name == "contract":
            return state.spec.contract
        if name in state.spec.literals:
            return name
        raise EngineError(f"condition names {name!r}, which resolves to nothing")

    def visit_Set(self, node: ast.Set) -> set[Any]:
        # Bare words inside a set literal are enum members, never lookups.
        members: set[Any] = set()
        for elt in node.elts:
            if isinstance(elt, ast.Name):
                members.add(elt.id)
            elif isinstance(elt, ast.Constant):
                members.add(elt.value)
            else:
                members.add(self.visit(elt))
        return members

    def visit_List(self, node: ast.List) -> list[Any]:
        return [self.visit(e) for e in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> tuple[Any, ...]:
        return tuple(self.visit(e) for e in node.elts)

    # -- operators --------------------------------------------------------
    def visit_BoolOp(self, node: ast.BoolOp) -> bool:
        results = (_truthy(self.visit(v)) for v in node.values)
        return all(results) if isinstance(node.op, ast.And) else any(results)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        if isinstance(node.op, ast.Not):
            return not _truthy(self.visit(node.operand))
        value = self.visit(node.operand)
        return None if value is None else -value

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left, right = self.visit(node.left), self.visit(node.right)
        if left is None or right is None:
            return None
        # ARITHMETIC IS ARITHMETIC. Every `+ - * /` in both ledgers is over
        # numbers - `labeled_examples_n >= 8 * classes_n`, `baseline_score -
        # 0.05` - and Python's `*` over a string is not arithmetic, it is
        # allocation. `'a' * 2_000_000_000` is two constants a ledger author can
        # type, and it takes two gigabytes and two seconds before anything else
        # in this file gets a say. Refusing the type is the fix rather than
        # bounding the size: there is no condition anyone wants to write that
        # multiplies text, and a bound would be a number invented here.
        for side in (left, right):
            if isinstance(side, bool) or not isinstance(side, (int, float)):
                raise SpecError(
                    f"condition does arithmetic on {type(side).__name__}: "
                    f"{side!r}. `+ - * /` are over numbers."
                )
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise EngineError("condition divides by zero")
            return left / right
        raise SpecError(f"unsupported operator {type(node.op).__name__}")  # pragma: no cover

    def visit_Compare(self, node: ast.Compare) -> bool:
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            if not self._compare(op, left, right):
                return False
            left = right
        return True

    def _compare(self, op: ast.cmpop, left: Any, right: Any) -> bool:
        if isinstance(op, ast.Is):
            return left is right
        if isinstance(op, ast.IsNot):
            return left is not right
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, (ast.In, ast.NotIn)):
            if right is None:
                contained = False
            else:
                contained = left in right
            return contained if isinstance(op, ast.In) else not contained
        if left is None or right is None:
            return False
        try:
            if isinstance(op, ast.Lt):
                return left < right
            if isinstance(op, ast.LtE):
                return left <= right
            if isinstance(op, ast.Gt):
                return left > right
            if isinstance(op, ast.GtE):
                return left >= right
        except TypeError as exc:
            raise EngineError(
                f"condition compares {left!r} with {right!r}, which are not comparable. "
                "That is a defect in the spec, not a false answer."
            ) from exc
        raise SpecError(f"unsupported comparison {type(op).__name__}")  # pragma: no cover

    # -- calls, attributes, comprehensions --------------------------------
    def visit_Call(self, node: ast.Call) -> Any:
        if isinstance(node.func, ast.Attribute):
            target = self.visit(node.func.value)
            attr = node.func.attr
            if target is None:
                # The same None-safe reading visit_Attribute already gives. An
                # unknown map has no values to list, and `sum(None)` is 0, which
                # is the honest count of a thing nobody has bucketed. Raising
                # here handed the user a stack trace instead of the node that
                # tells them to go bucket their failures.
                return None
            if isinstance(target, Mapping) and attr in ("values", "keys", "items"):
                return list(getattr(target, attr)())
            raise SpecError(f"unsupported method call .{attr}()")
        name = node.func.id
        func = _FUNCTIONS.get(name)
        if func is None:
            raise SpecError(f"condition calls unknown function {name!r}")
        args = [self.visit(a) for a in node.args]
        return func(self.state, node, args)

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        if isinstance(node.value, ast.Name) and node.value.id in self.state.spec.node_index:
            if node.attr != "condition":
                raise SpecError(f"unsupported node attribute .{node.attr}")
            return self.state.eval_condition(node.value.id)
        target = self.visit(node.value)
        if target is None:
            return None
        if isinstance(target, Mapping):
            return target.get(node.attr)
        raise SpecError(f"cannot read .{node.attr} off {type(target).__name__}")

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> list[Any]:
        return self._comprehend(node.elt, node.generators)

    def visit_ListComp(self, node: ast.ListComp) -> list[Any]:
        return self._comprehend(node.elt, node.generators)

    def _comprehend(self, elt: ast.expr, generators: Sequence[ast.comprehension]) -> list[Any]:
        if len(generators) != 1:
            raise SpecError("only single-generator comprehensions are supported")
        gen = generators[0]
        if not isinstance(gen.target, ast.Name):
            raise SpecError("comprehension target must be a plain name")
        iterable = self.visit(gen.iter) or []
        out: list[Any] = []
        saved = self.state.facts.get(gen.target.id, _MISSING)
        try:
            for item in iterable:
                self.state.facts[gen.target.id] = item
                if all(_truthy(self.visit(c)) for c in gen.ifs):
                    out.append(self.visit(elt))
        finally:
            if saved is _MISSING:
                self.state.facts.pop(gen.target.id, None)
            else:
                self.state.facts[gen.target.id] = saved
        return out


_MISSING = object()


# ---------------------------------------------------------------------------
# The functions a condition may call.


def _fn_sum(state: _State, node: ast.Call, args: list[Any]) -> Any:
    value = args[0]
    if value is None:
        return 0
    if isinstance(value, Mapping):
        value = list(value.values())
    return sum(value)


def _fn_max(state: _State, node: ast.Call, args: list[Any]) -> Any:
    value = args[0]
    if value is None:
        return None
    if isinstance(value, Mapping):
        # `max(failure_histogram)` in S1_MIXED_FAILURES is divided by
        # `sum(failure_histogram)`. Python's max over a mapping returns the
        # largest KEY, and a string over a number is a type error, so the only
        # reading that is arithmetic at all is the largest VALUE - which is also
        # what "no single failure mode dominates" means.
        value = list(value.values())
    value = list(value)
    return max(value) if value else None


def _fn_all(state: _State, node: ast.Call, args: list[Any]) -> bool:
    return all(_truthy(v) for v in (args[0] or []))


def _fn_any(state: _State, node: ast.Call, args: list[Any]) -> bool:
    return any(_truthy(v) for v in (args[0] or []))


def _fn_len(state: _State, node: ast.Call, args: list[Any]) -> int:
    return len(args[0] or [])


def _fn_contains(state: _State, node: ast.Call, args: list[Any]) -> bool:
    collection, item = args[0], args[1]
    if collection is None:
        return False
    if isinstance(collection, str):
        return collection == item
    return item in collection


def _fn_method_class(state: _State, node: ast.Call, args: list[Any]) -> str:
    return state.spec.method_class(args[0])


def _fn_gates_passed_under(state: _State, node: ast.Call, args: list[Any]) -> set[str]:
    return gates_passed_under(args[0], args[1], state.spec)


def _fn_measured(state: _State, node: ast.Call, args: list[Any]) -> bool:
    """True when this fact arrived MEASURED - a tool took it, nobody said it.

    THE ONE PREDICATE THAT READS AN ORIGIN, and it exists because a node reads a
    VALUE where a gate reads an ORIGIN, and one node now needs the second.

    `cannot_train_here` is stamped by `record_that_this_card_refuses` on a NO and
    is consulted BEFORE the define-success and build-eval gates, because the
    baseline those gates demand would have to be measured on the model the card
    has just refused to load. Refusing honestly must not require doing the
    impossible first.

    But a caller can SAY anything. `state_facts` records an `inspect` fact at a
    caller's origin and notes it "cannot, at this origin" - it does not refuse
    it, and it should not, because a sheet that drops what somebody said is a
    sheet that cannot explain itself. So the value is on the sheet and a bare
    `cannot_train_here` condition would route a thread that asserted its own
    refusal. That is harmless in outcome - a closure only ever closes - and it
    is still a walk deciding on somebody's say-so, which is what
    RC10_AN_ASSERTION_NEVER_MINTS exists to prevent.

    Takes the fact by NAME off the syntax tree rather than by value, because the
    value is exactly what must not be trusted here.
    """
    target = node.args[0] if node.args else None
    if not isinstance(target, ast.Name):
        raise SpecError(
            "measured() takes a bare fact name - measured(cannot_train_here) - "
            "because it asks where a value came from and not what it is"
        )
    return state.origins.get(target.id) == MEASURED


def _fn_user_confirms(state: _State, node: ast.Call, args: list[Any]) -> bool:
    answer = bool(state.facts.get("user_confirms", False))
    state.helper_answers.append({"helper": "user_confirms", "statement": args[0], "answer": answer})
    return answer


def _fn_user_can_produce(state: _State, node: ast.Call, args: list[Any]) -> bool:
    """CAN they produce N graded examples - and HAVE they already?

    THE DEADLOCK THIS BREAKS, found in Max's run of 2026-09-21. The walk is:

      S0_NO_DEFINITION_OF_SUCCESS  target_score is null and not
                                   user_can_produce(20, 'graded examples')
      G0_EVAL_SET                  (below it)
      G1_BASELINE_MEASURED         (below that)

    Under Full the harness settles `target_score` itself - and
    `full_defaults.PREREQUISITES` says a bar needs `baseline_score` under it
    first, which is right: a target with nothing measured beneath it is a
    number somebody made up. But `baseline_score` is measured at G1, and G1 is
    BELOW S0, which never opens while target_score is null.

    So: target_score waits on the baseline, the baseline waits on
    target_score, and every Full run he has ever started has died in that
    circle. His words, twice: "This diagnosis block never works."

    The way out is not to invent a target. It is to notice that the question
    S0 asks has already been ANSWERED BY MEASUREMENT. `user_can_produce(20,
    'graded examples')` asks whether this person can put twenty graded rows in
    front of the harness. When `measure_eval_set` has counted forty of them and
    stamped `eval_size_n` MEASURED, they have not merely demonstrated that they
    can - they have done it. Reading that is evidence, not assumption, and the
    reading is recorded in `helper_answers` beside the answer so the walk can
    be checked by hand.

    Only a MEASURED count passes. A stated one is somebody saying they have
    rows, which is the claim this node exists to stop standing in for rows.
    """
    answer = bool(state.facts.get("user_can_produce", False))
    because = "the person said so"
    if not answer:
        wanted = args[0] if args else 0
        thing = str(args[1] if len(args) > 1 else "")
        counted = state.facts.get("eval_size_n")
        graded = "graded" in thing or "example" in thing or "row" in thing
        if (
            graded
            and state.origins.get("eval_size_n") == MEASURED
            and isinstance(counted, (int, float))
            and isinstance(wanted, (int, float))
            and counted >= wanted
        ):
            answer = True
            because = (
                f"eval_size_n is {int(counted)}, MEASURED - they have already "
                f"produced {int(wanted)} graded rows, so the question is answered"
            )
    state.helper_answers.append(
        {
            "helper": "user_can_produce",
            "n": args[0] if args else None,
            "thing": args[1] if len(args) > 1 else None,
            "answer": answer,
            "because": because if answer else "no measured eval set, and nobody said so",
        }
    )
    return answer


_FUNCTIONS: dict[str, Callable[[_State, ast.Call, list[Any]], Any]] = {
    "sum": _fn_sum,
    "max": _fn_max,
    "all": _fn_all,
    "any": _fn_any,
    "len": _fn_len,
    "contains": _fn_contains,
    "method_class": _fn_method_class,
    "gates_passed_under": _fn_gates_passed_under,
    "measured": _fn_measured,
    "user_confirms": _fn_user_confirms,
    "user_can_produce": _fn_user_can_produce,
}


# ---------------------------------------------------------------------------
# Numbers that come out of the spec file, never out of the author's head.


def _money_from_prose(text: str) -> float:
    """Pull the first dollar figure out of one of the spec's `numbers:` strings.

    Reading the number rather than restating it is the point: a figure typed
    into this module could drift from the file, and a figure invented here would
    break the repo's hardest rule. If the string stops carrying a figure this
    raises, which is the correct failure - the engine must not price a
    from-scratch run out of nothing.
    """
    match = re.search(r"\$([0-9]+(?:\.[0-9]+)?)\s*([km])", text, re.IGNORECASE)
    if not match:
        raise SpecError(f"no dollar figure in {text!r}")
    scale = 1_000 if match.group(2).lower() == "k" else 1_000_000
    return float(match.group(1)) * scale


def _params_from_prose(text: str) -> float:
    match = re.search(r"~?([0-9]+(?:\.[0-9]+)?)\s*B params", text)
    if not match:
        raise SpecError(f"no parameter count in {text!r}")
    return float(match.group(1)) * 1e9


def _from_scratch_cost(state: _State) -> float | None:
    """derived.from_scratch_cost_estimate, read off S9_FROM_SCRATCH.numbers.

    The file gives two anchors and no formula. So this returns the cost of the
    smallest anchor at or above the requested size, and `None` above the largest
    anchor. `None` makes `budget_usd >= from_scratch_cost_estimate` false, so a
    run we cannot price never gets a from-scratch recommendation. Refusing to
    answer is the honest behaviour; interpolating a number the file does not
    contain is not.
    """
    target = state.facts.get("target_params")
    if target is None:
        return None
    numbers = state.spec.node_index["S9_FROM_SCRATCH"]["numbers"]
    anchors = []
    for key, text in numbers.items():
        if not key.startswith("cost_"):
            continue
        anchors.append((_params_from_prose(text), _money_from_prose(text)))
    for params, cost in sorted(anchors):
        if target <= params:
            return cost
    return None


# ---------------------------------------------------------------------------
# Walk results.


@dataclass
class _Goto:
    stage: str
    skip_leading_gates: bool = False


@dataclass
class _Terminal:
    outcome: str
    node: str
    say: str | None = None


#: THE STATUS THIS ENGINE WRITES ONTO A GATE IT EVALUATED AND OPENED, PUBLIC.
#:
#: It is public for the same reason `MEASURED` is: a plan's exit criterion
#: compares against it from another module, and a criterion that types the word
#: itself is a second copy of a name this file owns. On 2026-08-24 there were
#: two such copies and BOTH were wrong in the same way - `app/tools/propose.py`
#: stated `value="passed"` on the exit criterion of both eval-set builds while
#: `_finish` wrote `PASSED`, so `_compare`'s `equals` (an exact string test, as
#: it must be) reported `saw 'PASSED', wanted 'passed'` and the two most common
#: early builds in the product could never verify. Driven end to end: the storm
#: ran, every step finished, `deviations: []`, and the storm still ended
#: `failed`. Nothing in the suite compared the two words.
#:
#: `_gate_line` and `_finish` read this too, so there is now one spelling.
GATE_PASSED = "PASSED"

_PASSED, _FAILED, _LATCHED = GATE_PASSED, "FAILED", "LATCHED"

#: The row's predicate was true, and the facts that made it true are ones nobody
#: can vouch for. Not the same event as FAILED and it must not be told to the
#: user as one: "build an eval set" is the wrong sentence to say to somebody who
#: has just told you they have one.
_UNSUBSTANTIATED = "UNSUBSTANTIATED"


# ---------------------------------------------------------------------------
# Node handlers. Every node whose consequence the spec writes in prose needs
# one, and `_validate_nodes` refuses to load a spec that has a node without.

ACTION_HANDLERS: dict[str, Callable[[_State, dict[str, Any]], Any]] = {}
CONDITION_HANDLERS: dict[str, Callable[[_State, dict[str, Any]], bool]] = {}


def _action(node_id: str) -> Callable[[Callable], Callable]:
    def register(fn: Callable) -> Callable:
        ACTION_HANDLERS[node_id] = fn
        return fn

    return register


def _condition(node_id: str) -> Callable[[Callable], Callable]:
    def register(fn: Callable) -> Callable:
        CONDITION_HANDLERS[node_id] = fn
        return fn

    return register


# ---------------------------------------------------------------------------
# Forks. THERE IS NO REGISTRY HERE ANY MORE, and its absence is the point.
#
# `ROUTE_KEYS` used to hold two functions keyed by the FIRST LEDGER'S NODE IDS -
# `S0_MODALITY_FORK` and `S1_ROUTE_BY_FAILURE_MODE` - so a second ledger's fork
# could not exist under any other name. Both are now executed out of the
# declared `fork:` block by the two selectors below, and the ML ledger's own
# forks go through exactly this code.


def _fork_target(state: _State, node: Mapping[str, Any]) -> _Goto | _Terminal:
    """Run one declared fork. The strategy is the engine's; the table is the ledger's."""
    fork = node["fork"]
    value = _Evaluator(state).resolve(str(fork["branch_on"]))
    routes = fork["routes"]

    if fork["select"] == "value":
        if value in routes:
            return _Goto(routes[value])
    else:  # argmax - validated at load time, so there is no third branch
        counts = value if isinstance(value, Mapping) else {}
        best, best_count = None, -1
        for key in routes:  # declaration order, so ties resolve deterministically
            count = counts.get(key, 0)
            if count > best_count:
                best, best_count = key, count
        if best is not None and best_count > 0:
            return _Goto(routes[best])

    return _fork_no_match(state, node, value)


def _fork_no_match(state: _State, node: Mapping[str, Any], value: Any) -> _Goto | _Terminal:
    """What the LEDGER said to do when nothing matched. Three answers, all declared."""
    no_match = node["fork"]["no_match"]
    if "route" in no_match:
        return _Goto(no_match["route"])
    if "outcome" in no_match:
        return _Terminal(
            outcome=no_match["outcome"],
            node=node["node"],
            say=node.get("say"),
        )
    template = str(no_match["error"])
    keys = sorted(value) if isinstance(value, Mapping) else value
    try:
        message = template.format(value=value, keys=keys)
    except (KeyError, IndexError, ValueError):
        # A ledger's message is prose, and prose contains braces. The message
        # never being the reason a failure is unreadable matters more than the
        # substitution.
        message = f"{template}  (branch_on = {value!r})"
    raise EngineError(message)


@_action("S0_PRIVACY_CONSTRAINT")
def _privacy_constraint(state: _State, node: dict[str, Any]) -> None:
    """Records the constraint. It strikes no method, and that is deliberate.

    The spec's strike is "every outcome whose RUNNING SYSTEM would still call a
    hosted third-party model", and it names the one case that must survive:
    distillation from a hosted teacher is data collection, not the deployed
    system. No entry in `methods` deploys a hosted model - all nine train local
    weights - so the strike set over methods is empty and the constraint is
    carried for whoever renders the plan. Striking anything here would delete the
    privacy branch of stage 7, which is the case the constraint exists for.
    """
    state.constraints.add("FORBID_THIRD_PARTY_API")


def _strike_methods_named_in(state: _State, node: dict[str, Any], expected: set[str]) -> None:
    effect = node["effect"]
    for method in expected:
        if method not in effect:
            raise SpecError(
                f"node {node['node']}'s effect no longer names {method}; "
                "the handler and the spec have drifted apart"
            )
    named = {m for m in state.spec.methods if m in effect}
    state.struck_methods |= named
    for method in sorted(named):
        state.rejected.append(
            {"node_id": node["node"], "reason": node.get("reason", effect), "method": method}
        )


@_action("S3_REJECT_FINETUNE_FOR_FACTS")
def _reject_finetune_for_facts(state: _State, node: dict[str, Any]) -> None:
    _strike_methods_named_in(state, node, {"LORA_SFT", "FULL_FINETUNE"})


@_action("S8_TABULAR_REJECT_NEURAL")
def _tabular_reject_neural(state: _State, node: dict[str, Any]) -> None:
    _strike_methods_named_in(state, node, {"LORA_SFT", "FULL_FINETUNE"})
    state.struck_outcomes.add("NO_TRAIN__RAG")


def _gate_sweep(state: _State, node: dict[str, Any]) -> Any:
    """The commit stage opens here. It finishes the gate ledger under the proposal's class.

    Order comes from the node's own `order:` field, so reordering the sweep means
    editing the spec, not the engine.

    BOUND BY `contract.roles.gate_sweep_node`, NOT BY NODE ID. This used to be
    registered as `@_action("S9_GATE_SWEEP")`, and it is the one entry in that
    registry that is not an ML computation - it is a piece of the five-gate test
    itself. A second ledger that could not have a sweep would have gates that are
    only ever asked under whatever class happened to be current, which is the
    latching bypass with the fix removed.
    """
    order = [g.strip() for g in node["order"].split(",")]
    if order != list(state.spec.required_gates):
        raise SpecError(
            f"{node['node']}.order disagrees with contract.required_gates: "
            f"order says {order}, required_gates says {list(state.spec.required_gates)}"
        )
    for gate_id in order:
        status = _evaluate_gate(state, gate_id)
        if status == _FAILED:
            return _gate_failure(state, gate_id)
        if status == _UNSUBSTANTIATED:
            return _unsubstantiated(state, gate_id)
    return None


@_condition("S9_DATA_INSUFFICIENT")
def _data_insufficient(state: _State, node: dict[str, Any]) -> bool:
    """The floors table. Each floor is a number already in the file, with its source."""
    floors = node["floors"]
    row = floors.get(state.proposed_method) or floors["default"]
    count_expr = str(row["count"])
    floor = row["floor"]
    if isinstance(floor, str):
        floor = state.eval(compile_condition(floor))

    if state.proposed_method == "DISTILLATION":
        # "calls_per_day, or user_can_produce(10000, 'real inputs ...')"
        if not count_expr.startswith("calls_per_day"):
            raise SpecError("the DISTILLATION floor no longer counts calls_per_day")
        calls = state.facts.get("calls_per_day") or 0
        if calls >= floor:
            return False
        return not _truthy(
            _fn_user_can_produce(state, None, [floor, "real inputs to run the teacher over"])
        )

    if count_expr not in state.spec.facts:
        raise SpecError(f"S9_DATA_INSUFFICIENT counts {count_expr!r}, which is not a fact")
    value = state.facts.get(count_expr)
    if value is None:
        return True
    if floor is None:
        raise SpecError(f"S9_DATA_INSUFFICIENT floor for {state.proposed_method} is unknown")
    return value < floor


@_action("S9_SIZE_TO_METHOD")
def _size_to_method(state: _State, node: dict[str, Any]) -> None:
    n = state.facts.get("labeled_examples_n")
    state.size_row = None if n is None else _match_band(node["table"], n)
    state.required_rank = None if state.size_row is None else state.size_row.get("rank_max")
    if state.proposed_method == state.spec.no_proposal and state.size_row is not None:
        # A named proposal is never overwritten here. That is what stops a
        # DISTILLATION or TABULAR_DEEP proposal being turned into a LoRA on its
        # way past a table written about LLM demonstration counts.
        state.proposed_method = state.size_row["method"]


def _match_band(table: Sequence[Mapping[str, Any]], n: int) -> dict[str, Any] | None:
    for row in table:
        band = str(row["examples"]).strip()
        if band.startswith(">"):
            if n > int(band[1:]):
                return dict(row)
            continue
        match = re.fullmatch(r"(\d+)-(\d+)", band)
        if not match:
            raise SpecError(f"size table band {band!r} is not readable")
        low, high = int(match.group(1)), int(match.group(2))
        if low <= n <= high:
            return dict(row)
    return None


@_action("S9_LORA_CONFIG")
def _lora_config(state: _State, node: dict[str, Any]) -> None:
    """Advice about how to run a LoRA, not a decision about whether to. No state."""
    return None


@_action("S9_HARDWARE_ROUTER")
def _hardware_router(state: _State, node: dict[str, Any]) -> None:
    """Sets `route` and `hardware_permits` from the spec's own VRAM table.

    A GAP, NAMED RATHER THAN PAPERED OVER: `reference_points` is indexed by base
    model size and the fact ledger has no base-model-size fact, so there is
    nothing to index it with. This uses the smallest reference point that
    carries all three figures - the 7B row - and records which row it used in
    `hardware_reference`, so a reader can see the assumption instead of
    inheriting it. Every number here is read out of the file.
    """
    reference = None
    for row in node["reference_points"]:
        if all(k in row for k in ("full_ft_gb", "lora_gb", "qlora_gb")):
            reference = row
            break
    if reference is None:
        raise SpecError("S9_HARDWARE_ROUTER has no reference point with all three figures")
    state.hardware_reference = dict(reference)

    vram = state.facts.get("vram_gb")
    accelerator = state.facts.get("accelerator")
    state.hardware_permits = bool(vram is not None and vram >= reference["full_ft_gb"])

    if vram is not None and vram >= reference["full_ft_gb"]:
        state.route = "FULL_FT"
    elif vram is not None and vram >= reference["lora_gb"]:
        state.route = "LORA"
    elif vram is not None and vram >= reference["qlora_gb"]:
        state.route = "QLORA"
    elif accelerator == "apple_silicon":
        state.route = "LORA"
    elif accelerator == "cpu_only":
        state.route = "SHRINK_BASE"
    elif state.facts.get("can_rent_cloud"):
        state.route = "RENT_GPU"
    else:
        state.route = "SHRINK_BASE"


@_action("S9_QLORA_QUALITY_TAX")
def _qlora_quality_tax(state: _State, node: dict[str, Any]) -> None:
    state.route = "RENT_GPU"


def _mint(state: _State, node: dict[str, Any], template: str) -> _Terminal:
    """A TEMPLATED OUTCOME, EXECUTED BY THE GRAMMAR RATHER THAN BY A NODE'S NAME.

    This was `@_action("S9_MINT_TRAIN_VERDICT")` computing `f"TRAIN__{method}"`
    from two ML literals. Both are gone: the node is whichever one the gated
    prefix's `mintable_only_at:` names, and the outcome is whatever the node's
    own `outcome:` template says, filled from the engine's declared names.

    `emits:` is still the fence. A template that produced an outcome the node did
    not list would be an outcome invisible to the reachability check - the exact
    shape of hole that check exists for - so membership is asserted here and the
    loader already refuses a template with no `emits`.
    """
    evaluator = _Evaluator(state)
    try:
        outcome = re.sub(
            r"\{([A-Za-z_][A-Za-z0-9_]*)\}",
            lambda m: str(evaluator.resolve(m.group(1))),
            template,
        )
    except EngineError as exc:
        raise EngineError(f"{node['node']} templates {template!r}: {exc}") from None
    if outcome not in (node.get("emits") or []):
        raise EngineError(
            f"ERROR__UNCLASSIFIED_METHOD: {outcome} is not in {node['node']}.emits"
        )
    return _Terminal(outcome=outcome, node=node["node"], say=node.get("say"))


# ---------------------------------------------------------------------------
# Gates.


def _evaluate_gate(state: _State, gate_id: str) -> str:
    """Ask one gate one question, under the row the proposal's class selects.

    Three answers now, not two, and the order they are worked out in is the
    argument for the whole shape. `fact_origins.rule` states it:

      1. the row against the real values. A row that is false is a FAILED gate
         and nothing about origins is even looked at - the user who admits to one
         prompt iteration is told to go and iterate, never told to substantiate
         their claim of one;
      2. the facts that row READS which the caller supplied under an origin the
         ledger does not admit;
      3. the row again with exactly those facts masked back to their unsupplied
         reading. If it still passes, they were not load-bearing and the gate
         passes.

    Step 1 before step 3 is what makes step 3 safe. Masking can only WEAKEN a
    condition - `eval_size_n < 50` becomes true when 100 is masked to the default
    0 - so a masked evaluation on its own could pass a row the real values fail.
    It is an AND of the two, so it cannot.
    """
    gate = state.spec.gates[gate_id]
    klass = state.method_class()
    row_key = state.spec.row_key(gate_id, klass)

    # Latched PER ROW, not per run. Skip only when this exact question has
    # already been asked and answered. If the applicable row has changed because
    # a proposal arrived whose class is not the class the gate was passed under,
    # the question is asked again.
    for entry in state.path:
        if entry.kind == "gate" and entry.id == gate_id and entry.row == row_key:
            return _LATCHED

    state.note_node(gate["node"])
    row = state.spec.gate_row(gate_id, klass)
    tree = state.spec.gate_conditions[(gate_id, row_key)]
    if not _truthy(state.eval(tree)):
        state.failed_gates[gate_id] = row_key
        return _FAILED

    challenged = _challenged_facts(state, gate_id, row_key)
    if challenged and not _masked_row_passes(state, tree, challenged):
        state.failed_gates[gate_id] = row_key
        state.unsubstantiated[gate_id] = challenged
        return _UNSUBSTANTIATED

    state.path.append(PathEntry(gate_id, "gate", row=row_key, clause=row["requires"]))
    return _PASSED


def _challenged_facts(state: _State, gate_id: str, row_key: str) -> list[str]:
    """The facts this row reads that the caller supplied and cannot vouch for.

    The names come from `spec.gate_row_facts`, which was parsed out of the row's
    own `requires` string at load time. There is no list of fact names in this
    module and there must never be one: the check is only as complete as this
    set, and a fact added to a gate row next year has to be covered on the day it
    is added rather than on the day somebody remembers this function exists.

    A fact the caller did NOT supply is not challenged. It resolved through the
    ledger's default and the row already read it that way; "you did not tell me"
    is a different conversation from "you told me and nobody can vouch for it",
    and only the second one is this function's business.
    """
    spec = state.spec
    challenged: list[str] = []
    for name in sorted(spec.gate_row_facts.get((gate_id, row_key), ())):
        origin = state.origins.get(name, DEFAULTED)
        if origin == DEFAULTED:
            continue
        if origin in spec.admissible_for(name):
            continue
        challenged.append(name)
    return challenged


def _masked_row_passes(state: _State, tree: ast.expr, challenged: Sequence[str]) -> bool:
    """Re-evaluate the row with the challenged facts masked back to unsupplied.

    Restores in a `finally`, because a walk that left a masked value behind
    would answer every later node with a fact the caller did supply, and the
    difference would be invisible in any single assertion.
    """
    saved = {name: state.facts[name] for name in challenged}
    try:
        for name in challenged:
            state.facts[name] = unsupplied_value(state.spec.facts[name])
        return _truthy(state.eval(tree))
    finally:
        state.facts.update(saved)


def _gate_failure(state: _State, gate_id: str) -> Any:
    gate = state.spec.gates[gate_id]
    on_fail = gate["on_fail"]
    klass = state.method_class()
    row = state.spec.gate_row(gate_id, klass)
    state.rejected.append(
        {
            "node_id": gate["node"],
            "reason": f"{gate_id} not passed for method class {klass}",
            "evidence": row["requires"],
            "proposed_method": state.proposed_method,
        }
    )
    by_class = on_fail.get("route_by_class") or {}
    if klass in by_class:
        return _Goto(by_class[klass], skip_leading_gates=True)
    if "route" in on_fail:
        return _Goto(on_fail["route"], skip_leading_gates=True)
    return _Terminal(outcome=on_fail["outcome"], node=gate["node"], say=on_fail.get("note"))


def _unsubstantiated(state: _State, gate_id: str) -> _Terminal:
    """The answer for a gate that would have passed on a claim nobody can vouch for.

    It does NOT route to the gate's cheaper remedy, and that is the difference
    the outcome exists to carry. Routing to BLOCKED__BUILD_EVAL_SET would tell a
    user who has just said they have an eval set to go and build one, which reads
    as the product not listening - the single thing this product cannot afford,
    because the whole reason anyone believes the "do not train" answer is that
    they believe the harness looked.

    So the run ends here, at an ACTION__ whose verdict is BLOCKED, saying: you
    told me this, show it to me, and here is what showing it means for each fact.
    Every word of that comes out of the spec - the gate's own
    `on_unsubstantiated.note` and the per-source `substantiation` lines - and
    nothing is composed here.
    """
    spec = state.spec
    gate = spec.gates[gate_id]
    for name in state.unsubstantiated[gate_id]:
        state.rejected.append(
            {
                "node_id": gate["node"],
                "reason": f"{gate_id} was satisfied only by a claim about {name}",
                "evidence": (
                    f"{name} is declared source: {spec.facts[name]['source']} and this "
                    f"value's origin is {state.origins.get(name)}"
                ),
                "proposed_method": state.proposed_method,
            }
        )
    note = (gate.get("on_unsubstantiated") or {}).get("note")
    return _Terminal(outcome=spec.unsubstantiated_outcome, node=gate["node"], say=note)


# ---------------------------------------------------------------------------
# The walk.


def diagnose(facts: Mapping[str, Any], spec: Spec | None = None) -> Diagnosis:
    """Walk the tree for one fact set. Pure - no I/O, no network, no model call."""
    spec = spec or default_spec()
    values, origins = resolve_facts(facts, spec)
    state = _State(
        spec=spec, facts=values, origins=origins, proposed_method=spec.no_proposal
    )

    stage = spec.roles.entry_stage
    skip_leading_gates = False
    while True:
        state.enter_stage(stage)
        result = _walk_stage(state, stage, skip_leading_gates)
        if isinstance(result, _Terminal):
            return _finish(state, result)
        stage = result.stage
        skip_leading_gates = result.skip_leading_gates


def _walk_stage(state: _State, stage: str, skip_leading_gates: bool) -> _Goto | _Terminal:
    still_leading = True
    for item in state.spec.stages[stage]:
        if "gate_ref" in item:
            if skip_leading_gates and still_leading:
                # A gate's on_fail resumes at the first node of the stage that is
                # NOT a gate_ref. A gate never re-enters itself, so "gate fails ->
                # route to the remedies" cannot loop.
                continue
            status = _evaluate_gate(state, item["gate_ref"])
            if status == _FAILED:
                return _gate_failure(state, item["gate_ref"])
            if status == _UNSUBSTANTIATED:
                return _unsubstantiated(state, item["gate_ref"])
            continue
        still_leading = False
        outcome = _evaluate_node(state, item)
        if outcome is not None:
            return outcome
    raise EngineError(
        f"ERROR__NO_NODE_MATCHED: {stage} ran off the end with no outcome. "
        f"path: {[e.id for e in state.path]}"
    )


def _evaluate_node(state: _State, node: dict[str, Any]) -> _Goto | _Terminal | None:
    node_id = node["node"]
    state.note_node(node_id)

    handler = CONDITION_HANDLERS.get(node_id)
    if handler is not None:
        fired = handler(state, node)
    elif node.get("condition") == "always":
        fired = True
    else:
        fired = state.eval_condition(node_id)
    if not fired:
        return None

    if node_id == state.spec.roles.gate_sweep_node:
        swept = _gate_sweep(state, node)
        if swept is not None:
            return swept

    action = ACTION_HANDLERS.get(node_id)
    if action is not None:
        result = action(state, node)
        if result is not None:
            return result

    if "propose" in node:
        state.proposed_method = node["propose"]

    if _is_fork(node):
        return _fork_target(state, node)

    outcome = node.get("outcome")
    if outcome == "REROUTE" or (outcome is None and node.get("route")):
        return _Goto(node["route"])
    if outcome is None:
        return None  # an effect-only node; evaluation continues in the stage

    if "{" in outcome:
        return _mint(state, node, outcome)

    prefix, _ = state.spec.outcome_prefix(outcome)
    if prefix == "ERROR__":
        raise EngineError(f"{outcome} at {node_id}: {node.get('say', '')}")
    if outcome in state.struck_outcomes:
        raise EngineError(f"{outcome} at {node_id} was struck earlier in this run")
    return _Terminal(outcome=outcome, node=node_id, say=node.get("say"))


def _finish(state: _State, result: _Terminal) -> Diagnosis:
    spec = state.spec
    outcome = result.outcome
    _, decl = spec.outcome_prefix(outcome)
    verdict = decl["verdict"]
    if verdict is None:
        raise EngineError(f"{outcome} is not a terminal outcome")  # pragma: no cover

    klass = spec.method_class(state.proposed_method)
    passed = gates_passed_under(state.path, klass, spec)

    ledger: dict[str, dict[str, Any]] = {}
    for gate_id in spec.required_gates:
        entry: dict[str, Any] = {"node": spec.gates[gate_id]["node"]}
        if gate_id in passed:
            row_key = spec.row_key(gate_id, klass)
            written = [
                e for e in state.path if e.kind == "gate" and e.id == gate_id and e.row == row_key
            ][-1]
            entry.update(status=GATE_PASSED, row=written.row, clause=written.clause)
        elif gate_id in state.failed_gates:
            row_key = state.failed_gates[gate_id]
            entry.update(
                status="FAILED",
                row=row_key,
                clause=spec.gate_row(gate_id, klass)["requires"],
            )
            if gate_id in state.unsubstantiated:
                # Still FAILED, because the gate did not pass and the ledger's
                # three statuses are the contract. WHY it did not pass goes in a
                # field of its own rather than a fourth status: a renderer that
                # only knows PASSED/FAILED/NOT_REACHED keeps working, and one
                # that wants to say "you told me, show me" has the fact names.
                entry["unsubstantiated"] = list(state.unsubstantiated[gate_id])
        else:
            entry.update(status="NOT_REACHED", row=None, clause=None)
        ledger[gate_id] = entry

    # THE DEFENSIVE HALF OF THE INVARIANT, checked once more at the exit - and
    # keyed off the GATED PREFIX rather than off the literal verdict "TRAIN",
    # which is what it used to read. That literal was a sixth instance of the
    # same class as SC1's `TRAIN__`: a ledger whose expensive verdict is called
    # BUILD would have walked straight past the last defence in the file with
    # every structural check green.
    if spec.gated_prefix is not None and outcome.startswith(spec.gated_prefix):
        missing = set(spec.required_gates) - passed
        if missing:
            raise EngineError(
                f"ERROR__GATE_SKIPPED: {outcome} reached without {sorted(missing)} "
                f"passed under class {klass}"
            )
        # And the same defence for the half a perfect graph does not give you. A
        # gate that was refused for an unsubstantiated claim cannot also have
        # been passed, so reaching here means the walk kept going after a refusal
        # - an engine bug, and one that would ship the claim without the
        # guarantee. It raises rather than rendering.
        if state.unsubstantiated:
            raise EngineError(
                f"ERROR__GATE_SKIPPED: {outcome} reached with "
                f"{sorted(state.unsubstantiated)} refused for unsubstantiated facts"
            )

    # Invariant 3, now asked of the origin rather than of mere presence. A vram_gb
    # the user typed into a box is not a vram_gb the harness read off the machine,
    # and the previous reading - "was the key present" - called them the same
    # thing. `fallback: ask` on those four lines makes a stated number a legitimate
    # input; it does not make it a measurement, and a cost derived from it may not
    # be shown as one.
    hardware_measured = all(state.origins.get(f) == MEASURED for f in _HARDWARE_FACTS)

    unsubstantiated = [
        {
            "fact": name,
            "gate": gate_id,
            "declared_source": spec.facts[name]["source"],
            "origin": state.origins.get(name),
            "substantiation": spec.substantiation(name),
        }
        for gate_id, names in state.unsubstantiated.items()
        for name in names
    ]

    return Diagnosis(
        outcome=outcome,
        verdict=verdict,
        path=list(state.path),
        gate_ledger=ledger,
        proposed_method=state.proposed_method,
        rejected=list(state.rejected),
        struck_methods=set(state.struck_methods),
        constraints=set(state.constraints),
        helper_answers=list(state.helper_answers),
        size_row=state.size_row,
        route=state.route,
        hardware_permits=state.hardware_permits,
        hardware_reference=state.hardware_reference,
        cost_provenance="MEASURED" if hardware_measured else "UNKNOWN",
        node=result.node,
        say=result.say,
        fact_origins=dict(state.origins),
        fact_values=dict(state.facts),
        reached_by=dict(state.reached),
        unsubstantiated=unsubstantiated,
        spec=spec,
    )
