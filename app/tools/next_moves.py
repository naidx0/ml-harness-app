"""What would change this answer, and what to do about it - both read off the spec.

## The two named absences this closes

`frontend/src/components/DiagnosisCard.tsx` says it plainly, twice, and it is
right to:

> Page 23.4 specifies three controls that start the alternative work. The engine
> sends no alternatives with a verdict - `run_diagnosis` returns `say` and
> nothing that names a next action - so none are drawn here rather than
> invented.

> The diagnosis contract requires `revisit_if` alongside every verdict - what
> would change this answer. It is not on the wire yet.

Both are true and both are the engine's fault rather than the card's. The card
did the right thing: it drew a named absence instead of three plausible buttons
and a plausible sentence. This module is the other half - the fields it was
waiting for, derived rather than authored.

## Derived, and why that word is load-bearing here

There is a version of this file that is a dictionary: outcome id on the left,
a nice sentence and a button on the right, fifty-five rows. It would look
identical on screen on the day it was written and it would be a lie within a
month, because nothing would make it change when the graph changed. The whole
argument of `docs/diagnosis_engine.yaml` is that the guarantee has to be a
property of the file rather than of anyone's diligence, and a hand-maintained
side table of remedies is exactly the diligence that fails.

So everything below is read out of the spec at call time:

* **the sentence** is the node's or the gate's own `action`, `recipe`, `note` or
  `say`, VERBATIM. Nothing here rewords the engine. A lead-in that turns the
  engine's words into a claim they do not make is the prose version of
  inventing a number, and the card has already been bitten by exactly that
  ("Ask me again if This run was not refused").
* **the fact** comes from the compiled condition, through
  `diagnosis._facts_read_by`, so a fact added to a node next year is covered on
  the day it is added.
* **the tool** comes from `evidence.resolves`, which derives it from the
  registry's own `measures=` declarations. A remedy no registered tool can start
  gets `tool: None` and `starts_now: False`. That is not a gap to paper over: of
  the forty-six non-training outcomes, `docs/VISION.md` says roughly a third end
  in a question only the person can answer, and there is no retrieval bench in
  this harness yet. Drawing a button for work the product cannot do would be
  inventing a capability, which invariant 5's neighbour forbids in the same
  breath as inventing a number.

## Three moves, because a blocked gate produces three

Graphite 23.4, on why the row holds three and not five: *"Three because that is
how many genuinely different next moves a blocked gate produces - do the thing
that was skipped, exhaust the cheaper thing again, or re-examine the data the
finding rests on. A fourth would be padding and a fifth would be a menu."*

Those three are the `move` values below, and each one has a different mechanical
source: a FAILED gate, the node that fired, and the facts that node read. The
cap is three; `more` says how many were found beyond it, so the trim is visible
rather than silent.

## What this module may never do

It reads a `Diagnosis`. It cannot make one. Nothing here writes a fact, opens a
gate, or names an outcome that the engine did not already reach - and the tool
that carries these fields to the wire, `run_diagnosis`, still declares
`writes=()` and `measures=()`. An alternative is a suggestion about what to run
next; it is not a decision, and a caller running every one of them still
arrives at the same five gates.
"""

from __future__ import annotations

from typing import Any, Mapping

from app import diagnosis
from app.tools import evidence


#: Graphite 23.4's three, in the order a person reads them.
MOVES = (
    "do_the_thing_that_was_skipped",
    "exhaust_the_cheaper_thing",
    "re_examine_the_data",
)

#: How many alternatives reach the card. Graphite 23.4: "A fourth would be
#: padding and a fifth would be a menu."
HOW_MANY = 3


# ---------------------------------------------------------------------------
# Reading a value back out of a run.


def _value_of(
    name: str,
    facts_used: Mapping[str, Any],
    spec: diagnosis.Spec,
    origin: str | None,
) -> tuple[Any, bool]:
    """The value this run used for `name`, and whether we actually know it.

    Returns `(value, known)`. Three cases, and the third one is the reason this
    returns a pair rather than a value:

    * a row in `facts_used` - somebody supplied it or a tool measured it, so the
      value is exactly what the run saw;
    * no row and origin DEFAULTED - nobody supplied it, so the ledger's own
      default is what the run saw, read from the ledger rather than repeated
      here;
    * no row and some other origin - the caller did not hand over the trail. We
      do not know the value and we say so. The first cut fell back to the
      default in this case too, and printed `baseline_score changes from null`
      on a run that fired `baseline_score >= target_score`. A revisit condition
      that names a value the run did not hold is worse than one that names no
      value at all.
    """
    row = facts_used.get(name)
    if isinstance(row, Mapping) and "value" in row:
        return row["value"], True
    decl = spec.facts.get(name)
    if decl is None:
        return None, False
    if origin in (None, diagnosis.DEFAULTED):
        return diagnosis.unsupplied_value(decl), True
    return None, False


def _show(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return str(value)


def _gate_at(result: diagnosis.Diagnosis, spec: diagnosis.Spec) -> str | None:
    """The gate this run stopped at, or `None` if it stopped at an ordinary node.

    Matched on the gate's own `node:` against the node the run terminated on,
    and confirmed against the ledger's FAILED status, so a run that merely
    PASSED through a gate node does not look like a run that was stopped by it.
    """
    for gate_id, entry in (result.gate_ledger or {}).items():
        if entry.get("status") == "FAILED" and entry.get("node") == result.node:
            return gate_id
    return None


def _facts_of_node(node_id: str, spec: diagnosis.Spec) -> list[str]:
    """The declared facts the node's own condition reads, in a stable order.

    Parsed from the compiled condition. A router (`condition: always`) and a
    node whose condition is handled in Python rather than compiled both come
    back empty, which is the honest answer: there is no fact behind them to name.
    """
    tree = spec.conditions.get(node_id)
    if tree is None:
        return []
    return sorted(diagnosis._facts_read_by(spec, tree))


# ---------------------------------------------------------------------------
# revisit_if - what would change this answer.


def revisit_if(
    result: diagnosis.Diagnosis,
    *,
    spec: diagnosis.Spec | None = None,
    facts_used: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The contract's `revisit_if`, and where each line of it came from.

    Two sources, in this order:

    1. **Declared.** Three nodes in the spec carry a literal `revisit_if:` list
       today. Those lines are the author's and they are passed through word for
       word, first, because a hand-written condition is more specific than any
       derivation.

    2. **Derived from the predicate that fired.** The engine reached this
       outcome because one predicate was true of these facts. It stops being the
       answer when one of those facts changes, so each fact the predicate read
       becomes a line: `eval_size_n changes from 0`. That is not a guess about
       the future, it is the engine's own predicate read backwards, and it is
       the shape graphite 23.5 asks for - "It is conditions, not dates".

       WHICH PREDICATE depends on what stopped the run, and getting this wrong
       is what the block below the docstring is about: a gate node has no
       `condition:` at all, so reading only node conditions sent an empty list
       on every `BLOCKED__` answer a failed gate produced - the exact answers a
       person most needs a route out of.

    A run whose terminal node is a router or has no compiled condition, and
    which declares nothing, gets an EMPTY list and a `why_empty` sentence. The
    absence is reported. It is not filled in.
    """
    current = spec or diagnosis.default_spec()
    used = dict(facts_used or {})
    node = current.node_index.get(result.node) or {}

    declared_raw = node.get("revisit_if") or []
    declared = [str(line) for line in declared_raw if isinstance(line, str)]

    # A GATE NODE HAS NO COMPILED CONDITION, and the first cut therefore sent an
    # empty `revisit_if` on exactly the runs that need it most - every
    # BLOCKED__ answer a failed gate produced. A gate is a predicate too; it
    # just lives in `passes_when` rather than in `condition:`. The row that was
    # evaluated is the thing that would change the answer, so it is read from
    # there, and its `requires` string goes on the wire verbatim beside it.
    gate_id = _gate_at(result, current)
    requires: str | None = None
    if gate_id is not None:
        row_key = current.row_key(gate_id, current.method_class(result.proposed_method))
        requires = current.gate_row(
            gate_id, current.method_class(result.proposed_method)
        )["requires"]
        names = sorted(current.gate_row_facts.get((gate_id, row_key), ()))
    else:
        names = _facts_of_node(result.node, current)

    derived: list[dict[str, Any]] = []
    for name in names:
        origin = result.fact_origins.get(name)
        value, known = _value_of(name, used, current, origin)
        derived.append(
            {
                "condition": (
                    f"{name} changes from {_show(value)}"
                    if known
                    else f"{name} changes"
                ),
                "fact": name,
                "now": value,
                "value_known": known,
                "origin": origin,
            }
        )

    conditions = declared + [row["condition"] for row in derived]
    payload: dict[str, Any] = {
        "revisit_if": conditions,
        "revisit_if_source": {
            "declared": len(declared),
            "derived": len(derived),
            "node": result.node,
            "gate": gate_id,
            "condition": requires if gate_id is not None else node.get("condition"),
            "facts": derived,
            "how": (
                "Lines marked declared are this node's own `revisit_if:` in "
                "docs/diagnosis_engine.yaml, verbatim. The rest are the facts "
                "that node's condition read, with the value this run used - "
                "change one and the answer is recomputed rather than repeated."
            ),
        },
    }
    if not conditions:
        payload["revisit_if_source"]["why_empty"] = (
            f"{result.node} declares no `revisit_if:` and its condition names no "
            "declared fact - it is a router or a helper question - so there is "
            "nothing here to say and nothing is invented to fill the line."
        )
    return payload


def _facts_behind(result: diagnosis.Diagnosis, spec: diagnosis.Spec) -> list[str]:
    """The facts this run's answer actually rests on - the gate row's, or the node's."""
    gate_id = _gate_at(result, spec)
    if gate_id is None:
        return _facts_of_node(result.node, spec)
    klass = spec.method_class(result.proposed_method)
    return sorted(spec.gate_row_facts.get((gate_id, spec.row_key(gate_id, klass)), ()))


# ---------------------------------------------------------------------------
# alternatives - what to do instead, as controls rather than prose.


def _tool_the_ledger_starts_with(
    outcome: str, spec: diagnosis.Spec
) -> str | None:
    """The first registered tool providing a capability this outcome `builds`.

    `contract.capabilities.builds` is the spec author naming, in order, the
    capabilities that start an outcome. Where it speaks it outranks any ranking
    this module could invent - see the note in `alternatives`.
    """
    from app.tools import blocks as _blocks
    from app.tools.registry import REGISTRY

    try:
        book = _blocks.declared(spec)
    except Exception:  # noqa: BLE001 - a missing block must not break a remedy
        return None
    for capability in book.builds.get(str(outcome), ()) or ():
        for candidate in sorted(REGISTRY, key=lambda c: (c.control.order, c.name)):
            if capability in (candidate.provides or ()):
                return candidate.name
    return None


def _row(
    move: str,
    text: str,
    *,
    source: str,
    fact: str | None = None,
    why: str = "",
    spec: diagnosis.Spec | None = None,
    tool: str | None = None,
) -> dict[str, Any]:
    """One alternative, with the tool that starts it derived from the fact.

    `evidence.resolves` is the derivation and it is the same one the
    unsubstantiated rows already use, so a remedy and a challenge on the same
    fact hand back the same tool rather than two surfaces disagreeing.

    `tool=` overrides that, for the one case where the ledger has already said
    which tool starts this outcome. The VERB still comes from the registry, so
    the row cannot name a tool and describe a different one.
    """
    from app.tools.registry import REGISTRY

    step = evidence.resolves(fact, spec) if fact else None
    if tool:
        named = next((c for c in REGISTRY if c.name == tool), None)
        if named is not None:
            step = {
                "tool": named.name,
                "verb": named.control.verb,
                "run_as": "harness",
            }
    tool = (step or {}).get("tool")
    return {
        "move": move,
        "text": " ".join(str(text).split()),
        "from": source,
        "fact": fact,
        "tool": tool,
        "verb": (step or {}).get("verb") or "",
        "run_as": (step or {}).get("run_as"),
        "arguments": {},
        "starts_now": bool(tool),
        "why": why
        or (
            ""
            if tool
            else "No tool in this harness starts this yet, so this is the "
            "sentence and not a control. Saying so beats drawing a button "
            "that does nothing."
        ),
    }


def _gate_fact(gate_id: str, klass: str, spec: diagnosis.Spec) -> str | None:
    """The fact of this gate's applicable row that a tool could actually settle.

    Derived from `spec.gate_row_facts`, which is parsed out of the row's own
    `requires` string at load time. Preference goes to a fact a tool measures;
    failing that, the first fact of the row, so the row is never nameless.
    """
    key = (gate_id, spec.row_key(gate_id, klass))
    names = sorted(spec.gate_row_facts.get(key, ()))
    for name in names:
        if evidence.resolves(name, spec).get("tool"):
            return name
    return names[0] if names else None


def alternatives(
    result: diagnosis.Diagnosis,
    *,
    spec: diagnosis.Spec | None = None,
    limit: int = HOW_MANY,
) -> dict[str, Any]:
    """Up to three things to do instead, each read off the spec.

    The three moves and their three mechanical sources:

    * **do_the_thing_that_was_skipped** - a gate in the ledger whose status is
      FAILED. Its `on_fail` block is the remedy the spec already wrote, and the
      fact its `passes_when` row reads is what names the tool.
    * **exhaust_the_cheaper_thing** - the node that actually fired. Its own
      `action:` is the cheaper thing, in the spec's own words; `say:` when it
      has no action, because some nodes carry the instruction in the sentence.
    * **re_examine_the_data** - a fact the firing node's condition read whose
      origin in this run was not MEASURED, and which a registered tool could
      measure. That is literally re-examining what the finding rests on.
    """
    current = spec or diagnosis.default_spec()
    klass = current.method_class(result.proposed_method)
    rows: list[dict[str, Any]] = []

    # 1. The gate that stopped this, if one did.
    for gate_id, entry in (result.gate_ledger or {}).items():
        if entry.get("status") != "FAILED":
            continue
        gate = current.gates.get(gate_id) or {}
        on_fail = gate.get("on_fail") or {}
        text = (
            on_fail.get("action")
            or on_fail.get("recipe")
            or gate.get("asks")
            or ""
        )
        if not text:
            continue
        rows.append(
            _row(
                MOVES[0],
                text,
                source=f"{gate_id}.on_fail",
                fact=_gate_fact(gate_id, klass, current),
                why=f"{gate_id} is the gate this run stopped at: {gate.get('asks', '')}",
                spec=current,
            )
        )

    # 2. The cheaper thing this outcome names.
    node = current.node_index.get(result.node) or {}
    own = node.get("action") or node.get("say") or ""
    if own:
        names = _facts_behind(result, current)
        settleable = next(
            (n for n in names if evidence.resolves(n, current).get("tool")), None
        )
        # THE LEDGER ALREADY SAID WHICH TOOL STARTS THIS OUTCOME, IN ORDER.
        #
        # `evidence.resolves` picks by `measures=` and breaks ties on the tool
        # that asks least - fewest facts, fewest arguments. For
        # `failure_histogram` that is `rebucket_failures` (2 facts) over
        # `run_eval` (5), and rebucket is a CORRECTOR: it re-tallies a
        # histogram somebody already has. Offered against an empty histogram it
        # is a door that cannot open, and Max's run of 2026-09-21 was handed
        # exactly that - "re-tally a histogram you corrected" as the way to
        # produce a histogram, on an outcome whose own line reads "Ask again
        # when failure_histogram changes from {}".
        #
        # `contract.capabilities.builds` is the spec author saying which
        # capabilities start an outcome and in which order, and for
        # ACTION__CLASSIFY_FAILURES it reads `measurement.eval.run` first and
        # `measurement.eval.rebucket` second. That ordering is the answer;
        # nothing here has to rank tools at all. `resolves` stays as the
        # fallback for every outcome the ledger does not list.
        started_by = _tool_the_ledger_starts_with(result.outcome, current)
        settled_by = (
            evidence.resolves(settleable, current).get("tool") if settleable else None
        )
        rows.append(
            _row(
                MOVES[1],
                own,
                source=f"{result.node}.{'action' if node.get('action') else 'say'}",
                fact=settleable,
                tool=started_by or settled_by,
                why=f"{result.outcome} is what the engine reached, and this is the "
                f"remedy it names in {current.as_written}.",
                spec=current,
            )
        )

    # 3. Re-examine what the finding rests on.
    #
    # `source: ask` facts are deliberately NOT here, and the exclusion is the
    # difference between the third move and the second. This move is graphite's
    # "re-examine the data the finding rests on" - it is about a reading, and a
    # reading is what `inspect` and `derive` promise. `target_score` resolves to
    # `state_facts` because the user is the only witness to their own bar, so a
    # row telling them to go and MEASURE it would be the product asking a person
    # to instrument their own opinion. That row also duplicated move 2 exactly,
    # which is how the wrong scope showed itself.
    #
    # THAT SENTENCE IS SCOPED AND NOT REPEALED (P3, 2026-09-18). Under
    # permission `full` the person has said in advance that the harness decides,
    # and `app/full_defaults.py` settles `target_score` by a written rule before
    # this module is ever reached - as a DEFAULTED row, which is the weakest
    # word on the sheet and which the person's own STATED row outranks. Nothing
    # changes HERE: an alternative is still never a place to invent a reading,
    # and under every other mode the witness is still the person.
    already = {row["fact"] for row in rows if row["fact"]}
    for name in _facts_behind(result, current):
        if name in already:
            continue
        if result.fact_origins.get(name) == diagnosis.MEASURED:
            continue
        if (current.facts.get(name) or {}).get("source") not in ("inspect", "derive"):
            continue
        step = evidence.resolves(name, current)
        if not step.get("tool"):
            continue
        rows.append(
            _row(
                MOVES[2],
                f"{step['verb'].capitalize()} - this finding rests on {name}, "
                f"whose origin in this run was "
                f"{result.fact_origins.get(name) or 'unrecorded'} rather than a "
                "reading.",
                source=f"{result.node}.condition",
                fact=name,
                why="The answer above was computed from this value. Reading it "
                "either confirms the finding or changes it.",
                spec=current,
            )
        )

    seen: set[tuple[str | None, str]] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = (row["tool"], row["text"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)

    shown = unique[: max(0, int(limit))]
    source: dict[str, Any] = {}
    if not unique:
        # NAMED, NOT PAPERED OVER. A node with no `action:` and no `say:` - and
        # there are a few, S7_QUANTIZE carries its remedy in a `recommendation:`
        # map instead - has no sentence for this row to carry, and nothing here
        # will write one for it. That is a gap in the spec, and reporting it as
        # one is how it gets closed.
        source["why_empty"] = (
            f"{result.node} carries no `action:` and no `say:` in "
            "docs/diagnosis_engine.yaml, and no gate failed on this run, so "
            "there is no sentence to read out and none is written here. This is "
            "a gap in the spec rather than in the card."
        )
    return {
        "alternatives": shown,
        "alternatives_source": {
            **source,
            "found": len(unique),
            "more": max(0, len(unique) - len(shown)),
            "moves": list(MOVES),
            "how": (
                "Each row's sentence is read verbatim from "
                "docs/diagnosis_engine.yaml - a gate's on_fail block, or the "
                "node that fired - and its tool is derived from the registry's "
                "own measures= declarations through evidence.resolves. Nothing "
                "here is written by hand, and a remedy no registered tool can "
                "start carries tool: null rather than a button that does nothing."
            ),
        },
    }


def next_moves(
    result: diagnosis.Diagnosis,
    *,
    spec: diagnosis.Spec | None = None,
    facts_used: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Both fields at once, in the shape `run_diagnosis` puts on the wire."""
    current = spec or diagnosis.default_spec()
    payload = dict(revisit_if(result, spec=current, facts_used=facts_used))
    payload.update(alternatives(result, spec=current))
    return payload
