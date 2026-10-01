"""The paired per-edge table, as a tool, so nobody builds it in a shell again.

## Why this exists

The table two lanes needed for kill 13 was hand-built twice - once for `run_14`
against a naming-rule baseline, once for `run_15`'s same-base pair. **The second
time, the model-identity columns committed EMPTY**, because the block was
assembled in a shell string where the backticks around each model name were read
as command substitution. The commit message asserted "one model in both arms"
directly above a table that named neither.

**A table that says nothing looks exactly like a table that says something.** So
the table is produced here, from the artefacts, and the identity columns are
filled by this code rather than by whoever is typing.

## What it emits

One row per reference edge, so the reference-edge total is the SAME for both
arms by construction - the research lane's refusal 1, which the metric could not
satisfy until an unparseable answer stopped being dropped from its own
denominator.

    row_id  from  to  <a>  <b>  model_<a>  model_<b>  objects_<a>  objects_<b>
            rule_<a>  rule_<b>

Outcomes are ``correct``, ``reversed``, ``missing`` - three states and no
fourth. A ``skipped`` state is what the denominator fault looked like from the
inside, and its absence is load-bearing.

## THE AMBIGUITY THAT IS RECORDED RATHER THAN RESOLVED

`strip_fence` keeps the first balanced object out of a fenced or chatty reply.
**On a reply containing several balanced objects that rule picks an arbitrary
one and reports a confident number from it.**

Measured 2026-09-10 on `run_15`'s base arm: only 1 of 40 replies ever closed its
fence, 17 of 40 carried more than one balanced object - up to six - and in 24 of
40 the first balanced object ended before HALF the text. A base coverage of
"2.5%" was published off that rule. It was a number about a fragment the parser
chose.

So `objects_seen` is recorded per answer and the rule that chose is named beside
it. A lenient reading that quietly picked one of six is not a reading; it is a
guess with a percentage attached.

**And `strip_fence` must be applied to every arm or none.** A base that wraps
its JSON in a fence and an adapter that does not are not comparable if only one
is unwrapped, and the arm that gets unwrapped is the one that looks better.

## Where the model identity comes from, and why that is reported

`predictions.jsonl` rows carry `model` from 2026-09-10. Runs made before that do
not, so this looks beside the predictions - the run's `job.json`, the adapter's
own `adapter_config.json`, the run log's `eval_finished` event - and **says
which source answered**. It refuses only when no file names the model at all.

That middle path is deliberate. A hard refusal would make the tool unable to
read the very runs that motivated it; silently accepting would rebuild the fault
refusal 6 was filed against, where the one fact a comparison turns on lives in
prose. Reporting the source lets a reader weigh it.
"""

from __future__ import annotations

import json
from math import sqrt
from pathlib import Path
from typing import Any

from app.tools.edge_direction_core import (
    build_map,
    edges_of,
    label_of,
    reference_rows,
)
from app.tools.registry import REGISTRY

tool = REGISTRY.tool

#: The three states an edge can be in for one arm. There is no fourth, and a
#: test asserts it: a `skipped` value would make the reference-edge total a
#: fiction, which is exactly what the dropped-denominator fault produced.
STATES = ("correct", "reversed", "missing")

#: Built from chr() so a literal tab or newline cannot be mangled by an editor,
#: a shell, or a paste. The same reason this table exists at all.
TAB = chr(9)
NL = chr(10)
BACKSLASH = chr(92)


def balanced_objects(text: str) -> list[str]:
    """Every top-level balanced ``{...}`` in a string, braces in strings ignored.

    Top-level means not nested inside another object already being scanned, so a
    reply that answers, closes, and then answers again yields two - which is the
    case the caller has to be told about rather than have resolved for it.
    """
    found: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == BACKSLASH:
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth:
                depth -= 1
                if depth == 0 and start >= 0:
                    found.append(text[start:i + 1])
                    start = -1
    return found


def parse_answer(text: str, strip_fence: bool) -> tuple[dict, bool, int, str]:
    """(graph, parsed, objects seen, the rule that chose).

    `verbatim` means the whole answer was the graph - the only rule that cannot
    have picked the wrong object, because there was nothing to pick from.
    """
    objects = balanced_objects(str(text))
    try:
        return json.loads(text), True, len(objects), "verbatim"
    except (ValueError, TypeError):
        pass
    if strip_fence:
        for candidate in objects:
            try:
                return json.loads(candidate), True, len(objects), "first_balanced_object"
            except (ValueError, TypeError):
                continue
    return {"nodes": [], "edges": []}, False, len(objects), "none"


#: TWO NAMES FOR ONE FIELD, BOTH IN THE WILD. The recipe on main writes
#: `adapter`; artefacts from a recipe version that no longer exists write
#: `adapter_dir` - run 2's predictions are that shape. A reader that knows
#: only one name reports "no adapter" for an arm that names one perfectly
#: well, which is a provenance gap invented by the reader rather than found.
#:
#: Both are read and the NAME THAT ANSWERED is reported, because a field that
#: moved is a fact about the artefact worth carrying: it dates the recipe.
ADAPTER_FIELDS = ("adapter", "adapter_dir")


def adapter_of(rows: list[dict]) -> tuple[str | None, str | None]:
    """(the adapter this arm names, which field name carried it)."""
    for field in ADAPTER_FIELDS:
        named = {str(r[field]) for r in rows if r.get(field)}
        if len(named) == 1:
            return named.pop(), field
        if len(named) > 1:
            return None, field
    return None, None


def model_of(predictions: Path) -> tuple[str | None, str]:
    """(model identity, where it was read). Never a guess, never a sentence."""
    rows = [json.loads(l) for l in
            predictions.read_text(encoding="utf-8").splitlines() if l.strip()]
    named = {str(r["model"]) for r in rows if r.get("model")}
    if len(named) == 1:
        return named.pop(), "the predictions rows themselves"
    if len(named) > 1:
        return None, ("the predictions rows name more than one model ("
                      + ", ".join(sorted(named)[:3]) + "), so this file is not "
                      "one arm")

    run_dir = predictions.parent
    job = run_dir / "job.json"
    if job.is_file():
        config = json.loads(job.read_text(encoding="utf-8")).get("config", {})
        if config.get("base_model"):
            return str(config["base_model"]), "the run's job.json"
        adapter = config.get("adapter_dir") or config.get("adapter")
        if adapter:
            manifest = Path(str(adapter)) / "adapter_config.json"
            if manifest.is_file():
                named_by = json.loads(manifest.read_text(encoding="utf-8")).get(
                    "base_model_name_or_path")
                if named_by:
                    return str(named_by), "the adapter's own adapter_config.json"

    log = run_dir / "job.log"
    if log.is_file():
        found = None
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("MLH_EVENT"):
                try:
                    event = json.loads(line[len("MLH_EVENT"):].strip())
                except ValueError:
                    continue
                if event.get("base_model"):
                    found = str(event["base_model"])
        if found:
            return found, "the run log's eval_finished event"
    return None, "no file beside these predictions names a model"


def outcomes_for(predictions: Path, reference_paths, strip_fence: bool) -> dict[str, Any]:
    """Per-edge outcomes for one arm, plus what the parse had to decide."""
    ordered, by_id = reference_rows(reference_paths)
    positional = {str(i): row for i, row in enumerate(ordered)}
    rows = [json.loads(l) for l in
            predictions.read_text(encoding="utf-8").splitlines() if l.strip()]
    out: dict[tuple[str, tuple[str, str]], str] = {}
    seen: dict[str, int] = {}
    rules: dict[str, str] = {}
    bases: dict[str, str] = {}
    parsed = 0
    for row in rows:
        want = None
        basis = None
        if row.get("row_id") is not None:
            want = by_id.get(str(row["row_id"]))
            if want is not None:
                basis = "declared_row_id"
        if want is None and row.get("row_index") is not None:
            key = str(row["row_index"])
            want = by_id.get(key) or positional.get(key)
            if want is not None:
                #: THE ID WAS NOT DECLARED, so this row was matched by where
                #: it sat in the file. Recorded because a positional match
                #: against a reference whose ids ARE positions is safe, and
                #: against one numbered from anything else it silently scores
                #: a different question - and the two are indistinguishable
                #: from the answer alone.
                basis = "position"
        if want is None:
            continue
        expected = want["expected"]
        if isinstance(expected, str):
            expected = json.loads(expected)
        answer, ok, objects, rule = parse_answer(row.get("answer", ""), strip_fence)
        parsed += 1 if ok else 0
        rid = str(want["row_id"])
        seen[rid] = objects
        rules[rid] = rule
        bases[rid] = basis
        reference_labels = {l for l in label_of(expected).values() if l}
        mapping = build_map(answer, reference_labels, True)
        theirs, _ = edges_of(answer)
        theirs = {(mapping.get(a), mapping.get(b)) for a, b in theirs}
        theirs = {(a, b) for a, b in theirs if a and b}
        ours, _ = edges_of(expected)
        for edge in ours:
            if edge in theirs:
                out[(rid, edge)] = "correct"
            elif (edge[1], edge[0]) in theirs:
                out[(rid, edge)] = "reversed"
            else:
                out[(rid, edge)] = "missing"
    ambiguous = sum(1 for rid, n in seen.items()
                    if n > 1 and rules.get(rid) == "first_balanced_object")
    return {"outcomes": out, "objects_seen": seen, "rules": rules,
            "answers_parsed": parsed, "answers": len(rows),
            "ambiguous_answers": ambiguous,
            "join": ("declared_row_id"
                     if bases and all(b == "declared_row_id" for b in bases.values())
                     else "position" if bases else None),
            #: WHICH ROWS THIS ARM ACTUALLY ANSWERED. Needed because a
            #: reference edge no arm reached and a reference edge one arm
            #: was never GIVEN look identical from the outcomes alone -
            #: both are `missing` - and the second inflates the other arm.
            "rows_resolved": set(seen)}


def _z(c: int, b: int, n: int) -> float | None:
    under = b + c - (b - c) ** 2 / n
    return round((c - b) / sqrt(under), 3) if under > 0 else None


@tool(
    "pair_edge_direction",
    description=(
        "Pair two runs edge by edge over one reference set and write the table "
        "a paired test reads: one row per reference edge, each arm's outcome, "
        "each arm's model, and what the parse had to decide. The reference-edge "
        "total is the same for both arms by construction, which is what makes b "
        "and c countable from one table instead of welded from two. Refuses "
        "rather than guessing when an arm's model cannot be read from any file "
        "beside its predictions."
    ),
    schema={
        "type": "object",
        "properties": {
            "arms": {
                "type": "array",
                "description": (
                    "Exactly two arms, each {name, predictions_path}. The FIRST "
                    "is the baseline and the second the challenger, so b counts "
                    "what the baseline had and the challenger lost."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "predictions_path": {"type": "string"},
                    },
                    "required": ["name", "predictions_path"],
                },
            },
            "reference_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The reference set or sets (row_id, expected).",
            },
            "out_path": {
                "type": "string",
                "description": (
                    "Where to write the table. Default: beside the challenger's "
                    "predictions, named for both arms."
                ),
            },
            "strip_fence": {
                "type": "boolean",
                "description": (
                    "Keep the first balanced object out of a fenced reply, for "
                    "EVERY arm. Off by default, because the eval's own "
                    "instruction forbids a fence and obeying it is part of the "
                    "task. On, it measures the graph and sets the format aside "
                    "- and records how many objects it had to choose between."
                ),
            },
        },
        "required": ["arms", "reference_paths"],
    },
    reads=("filesystem", "datasets"),
    writes=("filesystem",),
    provides=("measurement.direction.pair",),
    label="Pair two runs edge by edge",
    group="Evaluate",
    verb="pair two runs edge by edge and write the table",
    order=43,
)
def pair_edge_direction(
    arms: list[dict[str, Any]],
    reference_paths: list[str],
    out_path: str | None = None,
    strip_fence: bool = False,
) -> dict[str, Any]:
    """The table, the four counts, and what every number rests on."""
    if not isinstance(arms, list) or len(arms) != 2:
        return {"ok": False, "error": "two_arms_required",
                "summary": ("A pairing needs exactly two arms, named. One arm "
                            "is a score, and three is a table nobody can read "
                            "b and c off.")}

    refs = [Path(str(p)) for p in reference_paths]
    absent = [str(p) for p in refs if not p.is_file()]
    if absent:
        return {"ok": False, "error": "reference_missing",
                "summary": "No reference to score against: " + ", ".join(absent)}

    resolved = []
    for arm in arms:
        path = Path(str(arm["predictions_path"]))
        if not path.is_file():
            return {"ok": False, "error": "predictions_missing",
                    "summary": "No predictions at " + str(path)}
        model, source = model_of(path)
        if model is None:
            return {
                "ok": False,
                "error": "model_not_recorded",
                "arm": str(arm["name"]),
                "summary": (
                    "Arm " + str(arm["name"]) + " does not name its model: "
                    + source + ". Two arms cannot be paired unless both say "
                    "which model produced them - a comparison across different "
                    "models moves two things at once, and an identity that "
                    "lives only in a message cannot be checked by whoever reads "
                    "the table later."),
            }
        rows_here = [json.loads(l) for l in
                     path.read_text(encoding="utf-8").splitlines() if l.strip()]
        adapter_named, adapter_field = adapter_of(rows_here)
        found = outcomes_for(path, refs, strip_fence)
        found.update({"name": str(arm["name"]), "path": path, "model": model,
                      "model_source": source, "adapter": adapter_named,
                      "adapter_field": adapter_field})
        resolved.append(found)

    left, right = resolved
    keys = sorted(set(left["outcomes"]) | set(right["outcomes"]))

    #: A PARTIAL ARM IS NOT A WRONG ARM, and the difference is invisible in
    #: the outcomes. Measured 2026-09-10: a dry run over `run_16`, whose base
    #: arm timed out after 29 of 40 rows, returned n = 118 - every reference
    #: edge of all forty - so the eleven rows the base was never given counted
    #: as edges the challenger gained. That is a real number about a question
    #: one arm never received.
    #:
    #: Reported rather than refused: comparing the rows both arms answered is
    #: a legitimate thing to want, and this lane did exactly that by hand on
    #: run_16. What is not legitimate is doing it without saying so.
    #: A POSITIONAL JOIN ACROSS SEVERAL REFERENCE FILES IS UNRESOLVABLE.
    #: Nothing about an index says which file it counts within, and an index
    #: that happens to be a valid id in one of them joins confidently to the
    #: wrong questions. Measured 2026-09-10: run 2's eval carried no row_id
    #: and its twenty prompts had to be matched to a reference by comparing
    #: their text, because the numbers alone could not say which twenty rows
    #: they were. That check happened by hand and should not have to.
    positional = [a["name"] for a in resolved if a.get("join") == "position"]
    if positional and len(refs) > 1:
        return {
            "ok": False,
            "error": "positional_join_across_several_references",
            "arms": positional,
            "summary": (
                "Arm(s) " + ", ".join(positional) + " declare no row_id, and "
                + str(len(refs)) + " reference sets were named. A positional index cannot say which set it counts within, and one that happens to be a valid id in another set joins confidently to the wrong questions. Name the one reference these predictions came from, or re-run with a recipe that declares row_id."),
        }

    only_left = sorted(left["rows_resolved"] - right["rows_resolved"])
    only_right = sorted(right["rows_resolved"] - left["rows_resolved"])
    if not keys:
        return {"ok": False, "error": "no_join",
                "summary": ("Neither arm resolved a single reference row, so "
                            "there is nothing to pair. Check that these "
                            "predictions came from these reference files.")}

    if out_path:
        table = Path(str(out_path))
    else:
        table = right["path"].parent / (
            "per-edge-" + left["name"] + "-vs-" + right["name"] + ".tsv")

    header = ["row_id", "from", "to", left["name"], right["name"],
              "model_" + left["name"], "model_" + right["name"],
              "objects_" + left["name"], "objects_" + right["name"],
              "rule_" + left["name"], "rule_" + right["name"]]
    lines = [TAB.join(header)]
    for rid, edge in keys:
        lines.append(TAB.join([
            rid, edge[0], edge[1],
            left["outcomes"].get((rid, edge), "missing"),
            right["outcomes"].get((rid, edge), "missing"),
            left["model"], right["model"],
            str(left["objects_seen"].get(rid, 0)),
            str(right["objects_seen"].get(rid, 0)),
            left["rules"].get(rid, "none"),
            right["rules"].get(rid, "none"),
        ]))
    table.parent.mkdir(parents=True, exist_ok=True)
    table.write_text(NL.join(lines), encoding="utf-8", newline=NL)

    def is_matched(value):
        return value in ("correct", "reversed")

    b_cov = sum(1 for k in keys
                if is_matched(left["outcomes"].get(k, "missing"))
                and not is_matched(right["outcomes"].get(k, "missing")))
    c_cov = sum(1 for k in keys
                if is_matched(right["outcomes"].get(k, "missing"))
                and not is_matched(left["outcomes"].get(k, "missing")))
    both = [k for k in keys
            if is_matched(left["outcomes"].get(k, "missing"))
            and is_matched(right["outcomes"].get(k, "missing"))]
    b_dir = sum(1 for k in both
                if left["outcomes"][k] == "correct"
                and right["outcomes"][k] == "reversed")
    c_dir = sum(1 for k in both
                if left["outcomes"][k] == "reversed"
                and right["outcomes"][k] == "correct")

    same_model = left["model"] == right["model"]
    ambiguous = left["ambiguous_answers"] + right["ambiguous_answers"]
    return {
        "ok": True,
        "table_path": str(table),
        "reference_edges": len(keys),
        "fence_stripped": bool(strip_fence),
        "ambiguous_answers": ambiguous,
        "arms": [
            {"name": a["name"], "model": a["model"],
             "model_source": a["model_source"],
             "answers_parsed": a["answers_parsed"], "answers": a["answers"],
             "ambiguous_answers": a["ambiguous_answers"],
             "join": a.get("join"),
             "adapter": a.get("adapter"),
             "adapter_field": a.get("adapter_field"),
             "matched": sum(1 for k in keys
                            if is_matched(a["outcomes"].get(k, "missing"))),
             "reversed": sum(1 for k in keys
                             if a["outcomes"].get(k) == "reversed")}
            for a in resolved
        ],
        "b_cov": b_cov, "c_cov": c_cov, "n": len(keys),
        "z_cov": _z(c_cov, b_cov, len(keys)),
        "b_dir": b_dir, "c_dir": c_dir, "n_both": len(both),
        "z_dir": _z(c_dir, b_dir, len(both)) if both else None,
        "same_base_model": same_model,
        "rows_only_in_" + left["name"]: only_left,
        "rows_only_in_" + right["name"]: only_right,
        "both_arms_answered_the_same_rows": not (only_left or only_right),
        "summary": (
            left["name"] + " -> " + right["name"] + ": b_cov " + str(b_cov)
            + ", c_cov " + str(c_cov) + " over " + str(len(keys))
            + " reference edges; direction on " + str(len(both))
            + " both-matched. "
            + ("Both arms are " + left["model"] + ". "
               if same_model else
               "DIFFERENT MODELS (" + left["model"] + " against "
               + right["model"] + "): this pairing moves the model and the "
               "treatment together and answers neither on its own. ")
            + (str(ambiguous) + " answer(s) contained more than one balanced "
               "object and the first was taken; the count and the rule are in "
               "the table. " if ambiguous else "")
            + (("PARTIAL: " + str(len(only_left)) + " row(s) only "
                + left["name"] + " answered and " + str(len(only_right))
                + " only " + right["name"] + " did, so some reference edges "
                "count against an arm that was never given them.")
               if (only_left or only_right) else "")),
    }
