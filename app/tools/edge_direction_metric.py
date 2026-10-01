"""Edge direction as a pair the engine can compute, not a script beside it.

THE DENOMINATOR RULE, and it is the whole contract:

    **Direction is scored over MATCHED edges only, coverage is reported beside
    it, and any reversed share is quoted with its matched count or not at all.**

WHY IT IS A PAIR AND NOT A SCORE. Direction is scored over matched edges so that
a node named differently is charged once as a naming difference and not twice as
a direction error. That denominator is right and it is gameable: **a model that
emits one constant graph for every question matched 4 of 346 edges and reversed
none of them - a reversed share of 0.0%, the best possible value.** The real
model scores 26.5% at 79.0% coverage. A model that matches nothing has no
reversals to be charged for, so refusing to engage wins, and a training run
pointed at a bare share would learn to emit labels the reference cannot match.

So this returns `coverage` and `reversed_share` together and marks the result
`is_a_score: false` when coverage is under half. **A share may be compared
between two runs only at comparable coverage, and a run whose coverage FELL has
not improved whatever its share did.**

WHY IT IS A TOOL AND NOT A `run_eval` METRIC. `evals.grade` returns one boolean
per row and the harness averages those over rows. This quantity is an aggregate
over EDGES - 118 of them across 40 rows - and rows are not its denominator.
Forcing it into the per-row slot would either discard the edge denominator, which
is the reason the metric resolves at all, or report a mean of booleans while
calling it a share of edges. Neither is worth the convenience, so it is reachable
the same way every other computation is: one call to the engine.

It stamps no fact and opens no gate. It reads two files and returns numbers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.tools.registry import REGISTRY

tool = REGISTRY.tool

#: Coverage below this is not a measurement of direction, it is a measurement of
#: how little the model engaged. Named here rather than inline so a reader can
#: see it is a policy of ours and not a property of anybody's data.
COVERAGE_FLOOR = 0.5


#: REGISTERED, AND THE PRICE WAS MEASURED BEFORE IT WAS PAID.
#:
#: Registering a tool costs a FIXED increment to every diagnosis outcome whose
#: block loads it, and it is not the description: shortening the description and
#: then the schema moved the number not at all. Measured 2026-09-10,
#: `ACTION__COUNT_THE_ROWS` passes at 4600 without this tool and lands at 4603
#: with it.
#:
#: The lab ruled the three tokens worth paying, because this is the scorer the
#: flagship run is judged by and a scorer one decorator away from the engine is
#: the shape this house spends its nights naming. The budget moved with it and
#: `FOCUSED_BUDGET` did not - see `tests/test_the_diagnosis_is_not_optional.py`,
#: which is where a growing registry is told apart from failed scoping.
@tool(
    "score_edge_direction",
    description=(
        "Score a run for EDGE DIRECTION and return coverage with the reversed "
        "share. Direction is scored over matched edges, so a model matching "
        "nothing reverses nothing; coverage is reported beside the share and a "
        "result under half coverage is marked not a score. Reads two files."
    ),
    schema={
        "type": "object",
        "properties": {
            "predictions_path": {
                "type": "string",
                "description": "The predictions file (row_index, answer).",
            },
            "reference_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The reference set or sets (row_id, expected).",
            },
            "equality_only": {
                "type": "boolean",
                "description": "Match labels exactly, not as a shortening.",
            },
        },
        "required": ["predictions_path", "reference_paths"],
    },
    reads=("filesystem", "datasets"),
    provides=("measurement.direction.score",),
    label="Score edge direction",
    group="Evaluate",
    verb="score edge direction on a run",
    order=42,
)


def score_edge_direction(
    predictions_path: str,
    reference_paths: list[str],
    equality_only: bool = False,
) -> dict[str, Any]:
    """The pair, or a refusal that says which file could not be read.

    `is_a_score` is the field a caller should branch on. It is false when
    coverage is under the floor, and the reversed share is still returned
    because hiding it would leave a reader guessing at what was refused.
    """
    from app.tools import edge_direction_core as core  # noqa: PLC0415

    missing = [p for p in [predictions_path, *reference_paths] if not Path(p).is_file()]
    if missing:
        return {
            "ok": False,
            "error": "file_not_found",
            "missing": missing,
            "summary": "Nothing was scored: " + ", ".join(missing) + " could not be read.",
        }

    found = core.score(Path(predictions_path), [Path(p) for p in reference_paths],
                       subset_allowed=not equality_only)
    if found.get("join") is None:
        #: REFUSE RATHER THAN GUESS. `measure_baseline` writes row_index as the
        #: POSITION in the eval file, not the file's row_id, so a run over a
        #: reference whose ids start at 100 arrives carrying 0-19. Joined by id
        #: that scores one set's answers against another set's questions and
        #: returns a number - measured, 0 matched of 62, reported as 0.0%
        #: reversed. A mis-join produces a score rather than an error.
        return {"ok": False, "error": "no_join",
                "summary": "Nothing was scored: " + found["join_reason"] + "."}

    matched = found["correct"] + found["reversed"]
    total = matched + found["unmatched"]
    coverage = (matched / total) if total else 0.0
    share = (found["reversed"] / matched) if matched else 0.0
    is_a_score = coverage >= COVERAGE_FLOOR

    summary = (
        "coverage " + format(coverage, ".1%") + " (" + str(matched) + " of "
        + str(total) + " reference edges matched); reversed "
        + str(found["reversed"]) + " of " + str(matched)
        + " = " + format(share, ".1%")
    )
    if not is_a_score:
        summary += (
            ". THIS IS NOT A SCORE: coverage is below " + format(COVERAGE_FLOOR, ".0%")
            + ", and a model that matches nothing has no reversals to be charged "
            "for. Compare shares only at comparable coverage, and read a fall in "
            "coverage as a regression whatever the share does."
        )

    return {
        "ok": True,
        "is_a_score": is_a_score,
        "coverage": round(coverage, 4),
        "matched_edges": matched,
        "reference_edges": total,
        "reversed_edges": found["reversed"],
        "correct_edges": found["correct"],
        "unmatched_edges": found["unmatched"],
        #: Surfaced because it moves the DENOMINATOR: an answer that does not
        #: parse now counts its reference edges as uncovered rather than
        #: dropping the row, and a reader comparing two runs needs to see how
        #: many of each run rests on that.
        "unparsed_answers": found.get("unparsed_answers", 0),
        "reversed_share": round(share, 4),
        "coverage_floor": COVERAGE_FLOOR,
        "rule": (
            "direction over matched edges only, coverage reported beside it, "
            "any reversed share quoted with its matched count or not at all"
        ),
        "matching": "equality" if equality_only else "one-directional subset",
        "join": found["join"],
        "join_reason": found["join_reason"],
        "summary": summary,
    }
