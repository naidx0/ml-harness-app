"""Under permission `full`, the harness settles an ask-fact by a written rule.

## The measured problem

Thread 78, 2026-09-18, permission `full` - which `app/autonomy.py` calls the
zero-ask bypass. The walk stopped at `S0_NO_TARGET_SCORE`, the brief told the
model to settle it, and the model ended its turn asking Max for `target_score`
and for what the task was. It spent the turn on a question, which is the one
thing `full` is supposed to have already answered.

Nothing in the model's way was wrong. `docs/diagnosis_engine.yaml` declares
`target_score` as `source: ask` with no default, and
`app/tools/next_moves.py` deliberately refuses to derive it:

    `target_score` resolves to `state_facts` because the user is the only
    witness to their own bar

That sentence is right under `ask` and wrong under `full`. Max, 2026-09-18:
*"based on the data, certain target scores are usually this amount... set it at
this, I think this is correct."* Under `full` the person has already said that
the harness may decide; a turn spent asking is a turn spent disobeying them.

## What this module does, and the three words that bound it

**Rule.** Every default here is arithmetic over facts already on this thread's
ledger, written out in the `how` that is recorded beside it. There is no rule
for a fact this module cannot compute, and there is deliberately no fallback
that picks something plausible: an ask-fact with no rule is left to
`conductor._full_grind_tool`, which tells the model to settle it itself. A
default nobody can recompute is a mood, not a number.

**DEFAULTED.** The row is written with origin DEFAULTED and actor `harness` -
the weakest word in `diagnosis.ORIGINS` and the one `evidence.ORIGIN_RANK`
scores at zero. So the person's own `state_facts` (STATED, rank 2) overrules it
by simply being said, with nothing here to undo, and a card that shows
provenance shows a default rather than a measurement. It is never MEASURED: no
instrument read any of these.

**Blocked.** A rule fires only for a fact the walk is actually stopped on -
`next_step.fact`, or a fact the terminal node's own condition read. Settling a
fact nobody was waiting for would be the harness filling in a form.

## Why none of this can open a gate

The four settleable facts are `target_score`, `task_family`, `modality` and
`privacy`, and NOT ONE OF THEM APPEARS IN ANY GATE ROW's `requires` string.
They are read by node conditions, which route; the five gates read row counts,
baselines, and what was tried. That is not a coincidence to rely on quietly -
`tests/test_full_mode_settles_ask_facts.py` derives the gate-row facts from the
spec and asserts the intersection is empty, so a future ledger that put one of
these into a gate row fails there rather than here.
"""

from __future__ import annotations

from typing import Any, Mapping

from app import diagnosis


#: The facts a rule below can settle, in the order they are tried. Nothing else
#: is ever defaulted, whatever the walk is blocked on.
SETTLEABLE: tuple[str, ...] = ("target_score", "task_family", "modality", "privacy")

#: The ceiling on a defaulted `target_score`. A bar of 1.0 is a bar nothing can
#: clear, and a rule that can produce one is a rule that can block a thread for
#: ever from the harness's own arithmetic.
TARGET_SCORE_CAP = 0.95

#: Max's "at least ten points above the model's baseline", as a fraction.
OVER_BASELINE = 0.10

#: The tools whose calls name the eval file. Read for the PATH only - the facts
#: these tools measured are what decides whether a rule may fire at all.
DATA_TOOLS = ("measure_baseline", "measure_eval_set", "profile_dataset")

#: Column names an eval file's expected answers are usually under, for a file
#: nobody has yet named a field for. Ordered: the first one present wins.
EXPECTED_FIELDS = (
    "expected",
    "answer",
    "output",
    "label",
    "target",
    "gold",
    "completion",
    "response",
)

#: How many rows of the eval file a task-family derivation reads. Enough for
#: `evals._label_set` to have something to say, small enough that a standing
#: diagnosis never waits on a large file.
SAMPLE_ROWS = 200

#: The share of expected values that must parse as JSON before the file is
#: called structured. Not "any", because one JSON-looking answer in a free-text
#: column is a coincidence.
JSON_SHARE = 0.6


# ---------------------------------------------------------------------------
# Reading the walk.


def _row(payload: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
    row = (payload.get("facts_used") or {}).get(name)
    return row if isinstance(row, Mapping) else None


def _value(payload: Mapping[str, Any], name: str) -> Any:
    row = _row(payload, name)
    return row.get("value") if row is not None else None


def _origin(payload: Mapping[str, Any], name: str) -> str | None:
    origin = (payload.get("fact_origins") or {}).get(name)
    return str(origin) if origin is not None else None


def _number(value: Any) -> float | None:
    """A plain float, with any claim mark left behind.

    `evidence._row` hands a non-MEASURED value back as a marked subclass, and a
    number derived from a marked one is marked too. Nothing here stamps
    anything, so the mark costs nothing - but the value is about to be written
    back into the ledger and read by a person, and a `ClaimedFloat` in a row
    the harness wrote would say the harness was quoting somebody.
    """
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def blocked_facts(payload: Mapping[str, Any] | None) -> set[str]:
    """The facts this walk actually stopped on, read off the wire.

    Two sources and both are already in the payload: `next_step.fact` is what
    `app/tools/__init__.py` decided the next question or gap is, and
    `revisit_if_source.facts` is `app/tools/next_moves.py` reading the terminal
    node's own condition backwards. Neither is a list maintained here, so a node
    that starts reading a new fact next year is covered on the day it does.
    """
    out: set[str] = set()
    if not payload:
        return out
    step = payload.get("next_step")
    if isinstance(step, Mapping) and step.get("fact"):
        out.add(str(step["fact"]))
    source = payload.get("revisit_if_source")
    if isinstance(source, Mapping):
        for row in source.get("facts") or ():
            if isinstance(row, Mapping) and row.get("fact"):
                out.add(str(row["fact"]))

    # AND A SETTLEABLE FACT THE WALK READ ON ITS WAY HERE, which the two
    # sources above can miss. `next_step.fact` is the ONE question the frontier
    # decided to ask and `revisit_if_source` is the TERMINAL node's condition;
    # a fact read by a node the walk passed through earlier is in neither. On
    # a thread with a measured eval set the walk runs `S0_RULES_SUFFICE`,
    # reads `task_family`, answers False and moves on - so the fact Full can
    # derive from the eval file was never offered to the rules.
    #
    # THE ASYMMETRY IS DELIBERATE, and it is the opposite of the one
    # `app/asking.py` needs. Over-reading there means ASKING a question the
    # walk did not need - measured 2026-09-19, forty minutes of a real run
    # spent on `classes_n` for a generation task. Over-reading HERE means the
    # harness computes a documented default from measurements it already
    # holds, writes it DEFAULTED (rank zero), and says in the row how it got
    # there. The person's own `state_facts` outranks it by being said, and the
    # module header's standing proof applies: not one of these four facts
    # appears in any gate row's `requires`, so none of this can open a gate.
    # A wrong question costs a turn; a recomputable default costs nothing.
    clauses = " ".join(
        str((entry or {}).get("clause") or "")
        for entry in (payload.get("path") or ())
        if isinstance(entry, Mapping)
    )
    for name in SETTLEABLE:
        if name in clauses and _is_open(payload, name):
            out.add(name)
    return out


def _is_open(payload: Mapping[str, Any], name: str) -> bool:
    """Nobody has settled this fact on this thread yet.

    DEFAULTED with no value is "the ledger's own default applied", which for
    these four is null. DEFAULTED WITH a value is a rule that already fired, and
    firing it again would write a second row saying the same thing every turn.
    """
    if _origin(payload, name) != diagnosis.DEFAULTED:
        return False
    return _value(payload, name) is None


# ---------------------------------------------------------------------------
# The rules.


def _target_score(
    thread_id: int, payload: Mapping[str, Any], spec: diagnosis.Spec
) -> tuple[Any, str] | None:
    """max(trivial + resolution, baseline + 0.10), capped at 0.95.

    IT NEEDS A MEASURED BASELINE AND A MEASURED TRIVIAL BASELINE and returns
    nothing without them, which is the half of this rule that keeps it honest.
    A bar set before anything was scored is a number with nothing under it; the
    walk's own answer to a thread with no baseline is to go and measure one, and
    that path already exists. So this rule can only fire AFTER the measuring,
    which is also when it has something to compute from.

    The two halves are Max's sentence and the eval set's own arithmetic. "At
    least ten points above the model's baseline" is the improvement worth
    training for. `trivial + resolution` is the other floor: a bar the eval set
    cannot tell apart from the majority-class answer is not a bar, and
    `evals.resolution_for` says what this many rows can resolve between two
    runs - computed from n, never a rule of thumb.
    """
    if _origin(payload, "baseline_score") != diagnosis.MEASURED:
        return None
    if _origin(payload, "trivial_baseline_score") != diagnosis.MEASURED:
        return None
    baseline = _number(_value(payload, "baseline_score"))
    trivial = _number(_value(payload, "trivial_baseline_score"))
    rows = _number(_value(payload, "eval_size_n"))
    if baseline is None or trivial is None or not rows or rows < 1:
        return None

    from app.tools import evals

    n = int(rows)
    block = evals.resolution_for(int(round(baseline * n)), n)
    points = block.get("resolves_a_difference_of_at_least_points")
    if points is None:
        return None
    resolution = float(points) / 100.0

    over_trivial = trivial + resolution
    over_baseline = baseline + OVER_BASELINE
    value = round(min(TARGET_SCORE_CAP, max(over_trivial, over_baseline)), 4)
    how = (
        "Full: set to the trivial baseline plus the resolution this eval set can "
        "tell apart, and at least ten points above the model's baseline. Trivial "
        f"{trivial:.3f} + resolution {resolution:.3f} on {n} rows = "
        f"{over_trivial:.3f}; baseline {baseline:.3f} + {OVER_BASELINE:.3f} = "
        f"{over_baseline:.3f}; the larger of the two, capped at "
        f"{TARGET_SCORE_CAP:.2f}, is {value:.3f}. Say a different number with "
        "state_facts and yours wins."
    )
    return value, how


def _eval_file(thread_id: int) -> tuple[str, str | None] | None:
    """The eval file this thread has profiled, and the column it grades on.

    Read off the thread's own tool calls rather than out of a ledger row's
    prose: `measure_baseline` takes `eval_path` and `expected_field` by name,
    and `measure_eval_set` and `profile_dataset` take `path`. The newest call
    that named one wins, because the newest is the file the thread is working.
    """
    from app import events

    path: str | None = None
    field: str | None = None
    for row in events.since(f"thread:{int(thread_id)}", limit=100_000):
        payload = row.get("payload") or {}
        if str(payload.get("name") or "") not in DATA_TOOLS:
            continue
        if row.get("kind") == "tool.call":
            arguments = payload.get("arguments") or {}
            named = arguments.get("eval_path") or arguments.get("path")
            if named:
                path = str(named)
                field = str(arguments.get("expected_field") or "") or None
        elif row.get("kind") == "tool.result" and payload.get("ok"):
            result = payload.get("result")
            if isinstance(result, Mapping):
                named = result.get("eval_path") or result.get("path")
                if named:
                    path = str(named)
    if path is None:
        return None
    return path, field


def _expected_values(path: str, field: str | None) -> tuple[list[str], str] | None:
    """Up to `SAMPLE_ROWS` expected answers out of the eval file, and the column.

    Returns `None` rather than an empty list when the file cannot be read or has
    no column that looks like an answer. The difference matters: an empty list
    would derive `generation` from having read nothing.
    """
    from app import dataquality

    values: list[str] = []
    chosen = field
    stream = dataquality.iter_records(path)
    try:
        for record in stream:
            if not isinstance(record, Mapping):
                continue
            if chosen is None:
                for candidate in EXPECTED_FIELDS:
                    if candidate in record:
                        chosen = candidate
                        break
                if chosen is None:
                    return None
            got = record.get(chosen)
            if got is None:
                continue
            values.append(str(got))
            if len(values) >= SAMPLE_ROWS:
                break
    except Exception:  # noqa: BLE001 - an unreadable file settles nothing
        return None
    finally:
        close = getattr(stream, "close", None)
        if close is not None:
            close()
    if not values or chosen is None:
        return None
    return values, chosen


def _family_of(values: list[str]) -> str:
    """JSON records -> extraction, a short closed label set -> classification.

    THE SAME TWO READERS THE GRADER USES, on purpose. `evals._looks_like_json`
    is what decides a reply is `wrong_format`, and `evals._label_set` is what
    decides the expected column is a closed vocabulary at all - with both bounds,
    so twenty labels over twenty-five rows is still free text. A second pair of
    rules here would be a second opinion about the same file, and the two would
    disagree the first time either changed.

    `structured_generation` is NOT a value this returns, and that is the ledger's
    decision rather than a preference: `task_family`'s enum does not declare it,
    and `settle` refuses any value the enum does not hold. JSON records are
    `extraction`.
    """
    from app.tools import evals, measure

    structured = sum(1 for value in values if evals._looks_like_json(value))
    if structured >= JSON_SHARE * len(values):
        # A RECORD OF PROSE IS WRITTEN, NOT EXTRACTED. Max's ml-principles set:
        # every expected answer is a JSON record, but three of its five fields
        # are sentences the model has to write (summary, steps, pitfalls) and
        # two are labels. Calling that `extraction` sent the walk down the
        # branch for pulling closed fields out of an input. The fields are
        # classified by the same rule the `fields` grader uses, so the family
        # and the ruler cannot disagree about what the record is.
        shape = measure.record_shape(values)
        if len(shape["free_text"]) > len(shape["compared"]):
            return "generation"
        return "extraction"
    if evals._label_set(values):
        return "classification"
    return "generation"


def _from_the_eval_file(
    thread_id: int, payload: Mapping[str, Any], spec: diagnosis.Spec
) -> dict[str, tuple[Any, str]]:
    """`task_family` and `modality`, derived from the profiled file's answers.

    Only for a thread that HAS a profiled eval set - `eval_size_n` measured by
    `measure_eval_set` or `profile_dataset`. Without one there is no file to
    read and no rule, so the walk goes and profiles one, which is what it
    already says to do.
    """
    if _origin(payload, "eval_size_n") != diagnosis.MEASURED:
        return {}
    found = _eval_file(thread_id)
    if found is None:
        return {}
    path, field = found
    read = _expected_values(path, field)
    if read is None:
        return {}
    values, column = read

    family = _family_of(values)
    from app.tools import measure as _measure

    shape = _measure.record_shape(values)
    fields = (
        f" The answers are JSON records with fields {', '.join(shape['fields'])}: "
        f"{', '.join(shape['compared']) or 'none'} short enough to compare, "
        f"{', '.join(shape['free_text']) or 'none'} written prose."
        if shape["fields"]
        else ""
    )
    out: dict[str, tuple[Any, str]] = {
        "task_family": (
            family,
            f"Derived: read the {column!r} column of {path} - {len(values)} expected "
            f"answers - and derived {family} by the rule the grader already uses "
            "for that column: JSON records of mostly short fields are extraction and "
            "of mostly prose are generation, a short closed label set is "
            "classification, anything else is generation." + fields,
        ),
    }
    if _is_text(values):
        out["modality"] = (
            "text",
            f"Derived: the {len(values)} answers read from the {column!r} column of "
            f"{path} are text, and none of them names an image, audio or video "
            "file, so the modality this thread is working in is text. Say "
            "otherwise with state_facts and yours wins.",
        )
    return out


#: File endings that mean a value NAMES media rather than being text. A column
#: of `cat_001.png` is an image task written down as strings, and calling it
#: text would send the walk down the wrong branch of the fork.
MEDIA_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff",
    ".wav", ".mp3", ".flac", ".ogg", ".m4a", ".mp4", ".mov", ".avi", ".webm",
)


def _is_text(values: list[str]) -> bool:
    """Every value is a string of text, and not one of them names a media file."""
    seen = 0
    for value in values:
        text = str(value).strip().lower()
        if not text:
            continue
        if text.endswith(MEDIA_SUFFIXES) or text.startswith("data:"):
            return False
        seen += 1
    return seen > 0


def _privacy(
    thread_id: int, payload: Mapping[str, Any], spec: diagnosis.Spec
) -> tuple[Any, str] | None:
    """`on_prem_only` when every connected provider is local.

    A machine whose only models run on it is a machine that has not sent a row
    anywhere, and that is what the constraint says. One remote provider and this
    rule does not fire at all - it does not weigh them up, because "mostly local"
    is not a privacy posture and guessing which way somebody leans is exactly
    the invention this module is not allowed to make.
    """
    from app.providers import store

    rows = store.list_all()
    if not rows:
        return None
    kinds = {str(row.get("kind") or "") for row in rows}
    if kinds != {"local"}:
        return None
    return (
        "on_prem_only",
        f"Full: all {len(rows)} connected providers on this machine are local, so "
        "no row of this data leaves it. Recorded as on_prem_only; a hosted "
        "provider, or your own word through state_facts, changes it.",
    )


# ---------------------------------------------------------------------------
# Settling.


def _declared(spec: diagnosis.Spec, fact: str, value: Any) -> bool:
    """Is this a value the ledger declares for this fact?

    An enum fact may only be defaulted to a member of its own enum. A rule that
    produced `structured_generation` for `task_family` would be the harness
    inventing a category, and `diagnosis._coerce` would refuse it one layer on
    with a sentence about a fact nobody asked about.
    """
    decl = spec.facts.get(fact)
    if decl is None:
        return False
    choices = decl.get("enum")
    if choices:
        return value in list(choices)
    return value is not None


def settle(
    thread_id: int | None,
    payload: Mapping[str, Any] | None,
    *,
    permission: str | None = None,
    ledger: diagnosis.Spec | None = None,
) -> list[dict[str, Any]]:
    """Write a DEFAULTED row for every blocked ask-fact a rule can answer.

    Returns one dict per row written - `fact`, `value`, `how` - and an empty
    list for every other permission mode, for a walk that is not blocked on one
    of these, and for a fact whose rule had nothing to compute from.

    It never re-settles: `_is_open` is false the moment a row exists, so a
    thread that has been settled once pays one walk and no writes on every turn
    after it.
    """
    from app import autonomy, events
    from app.tools import evidence

    if thread_id is None or not payload:
        return []
    mode = permission
    if mode is None:
        thread = events.get_thread(int(thread_id)) or {}
        mode = str(thread.get("permission") or "ask")
    full = autonomy.normalise(mode) == "full"

    # THE THREAD'S OWN LEDGER, never the first one by default: a Full thread
    # on the AI-engineering ledger must not have ML facts settled on it
    # (tests/test_the_default_ledger_is_a_bounded_debt.py).
    if ledger is None:
        thread_row = events.get_thread(int(thread_id)) or {}
        ledger = diagnosis.spec_at(thread_row.get("ledger") or None)
    spec = ledger

    # A `derive` FACT IS THE HARNESS'S TO WORK OUT, UNDER EVERY PERMISSION.
    # `task_family` and `modality` are declared `source: derive` - the ledger's
    # own word for "computed from data, never asked" - and this rule was
    # fenced behind Full as if they were ask-facts. Max's run of 2026-09-21
    # was not on Full: the eval set was counted, the walk stopped on
    # `modality`, and the harness told the model to decide what no tool it had
    # could settle, while the file that answers it sat counted on the thread.
    # So the eval-file rule fires for these two wherever the file can be read,
    # blocked or not - a routing fact nobody reads yet is still one the next
    # node will read - and the ask-facts below stay Full's and the walk's.
    derivable = tuple(
        name
        for name in ("task_family", "modality")
        if (spec.facts.get(name) or {}).get("source") == "derive"
    )
    blocked = blocked_facts(payload)
    if not full:
        blocked = set()
    if not blocked and not any(_is_open(payload, name) for name in derivable):
        return []

    proposals: dict[str, tuple[Any, str]] = {}
    if "target_score" in blocked and _is_open(payload, "target_score"):
        found = _target_score(int(thread_id), payload, spec)
        if found is not None:
            proposals["target_score"] = found
    wanted = {
        name
        for name in ("task_family", "modality")
        if _is_open(payload, name) and (name in blocked or name in derivable)
    }
    if wanted:
        for name, found in _from_the_eval_file(int(thread_id), payload, spec).items():
            if name in wanted:
                proposals[name] = found
    if "privacy" in blocked and _is_open(payload, "privacy"):
        found = _privacy(int(thread_id), payload, spec)
        if found is not None:
            proposals["privacy"] = found

    written: list[dict[str, Any]] = []
    for fact in SETTLEABLE:
        if fact not in proposals:
            continue
        value, how = proposals[fact]
        if not _declared(spec, fact, value):
            continue
        evidence.record(
            fact=fact,
            value=value,
            origin=diagnosis.DEFAULTED,
            actor=evidence.HARNESS,
            how=how,
            thread_id=int(thread_id),
            ledger=spec,
        )
        written.append(
            {"fact": fact, "value": value, "how": how, "kind": "full" if full else "derived"}
        )
    return written


#: The chain a Full-mode rule needs before it can compute anything, in the
#: order the harness would walk it. Each entry is (the fact the rule is waiting
#: on, the tool that measures it, what to say). Derived from the rules above -
#: `_target_score` reads `baseline_score`, `trivial_baseline_score` and
#: `eval_size_n`; `_from_the_eval_file` reads `eval_size_n` - so a change to
#: either rule that forgets this list is caught by
#: `tests/test_full_mode_settles_ask_facts.py`.
PREREQUISITES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "target_score": (
        (
            "eval_size_n",
            "measure_eval_set",
            "there are no graded rows to set a bar against yet. Carve one out of "
            "real rows with carve_eval_set if there is no file, then count it "
            "with measure_eval_set",
        ),
        (
            "baseline_score",
            "measure_baseline",
            "nothing has been scored yet, so any bar would be a number with "
            "nothing under it. Pin the model with set_baseline_target, then "
            "measure_baseline on the eval set",
        ),
    ),
    "task_family": (
        (
            "eval_size_n",
            "measure_eval_set",
            "the rule reads the answers in the eval file to tell extraction "
            "from classification from generation, and no eval file has been "
            "counted on this thread yet",
        ),
    ),
    "modality": (
        (
            "eval_size_n",
            "measure_eval_set",
            "same file, same reason as task_family",
        ),
    ),
}


def prerequisite_for(
    fact: str, payload: Mapping[str, Any] | None
) -> tuple[str, str] | None:
    """The tool that has to run before Full can settle `fact` by rule.

    THE CIRCLE THIS BREAKS, measured on Max's thread 2026-09-19. The walk stops
    at `S0_NO_DEFINITION_OF_SUCCESS` because `target_score` is null. Full's rule
    for `target_score` needs a MEASURED baseline. The node that would send
    anybody to measure a baseline is `G1_BASELINE_MEASURED`, one stage below a
    hard terminal the walk never gets past. So the harness asked for the bar,
    could not default the bar, and said "run state_facts" - forty minutes, a
    dozen identical verdicts, nothing measured.

    Max: *"An eval set exists - if it sees an eval set doesn't exist, GO MAKE AN
    EVAL SET. A baseline hasn't been measured - GO MAKE A BASELINE."* He is
    right, and the harness already knows the order; it simply never said it.
    This returns the FIRST unmet step of that chain, so a thread with no eval
    set is told to count one and a thread with one is told to score it.

    Returns `(tool, why)`, or `None` when the rule could already fire or when
    there is no rule for this fact at all.
    """
    for needed, tool, why in PREREQUISITES.get(str(fact), ()):
        if _origin(payload or {}, needed) != diagnosis.MEASURED:
            return tool, why
    return None


def settled_lines(payload: Mapping[str, Any] | None) -> list[str]:
    """One line per settlement, for the brief. The rule, not just the number."""
    lines: list[str] = []
    for key, verb in (("full_settled", "Full settled"), ("derived", "The harness derived")):
        for row in (payload or {}).get(key) or []:
            if not isinstance(row, Mapping):
                continue
            lines.append(
                f"{verb} {row.get('fact')} at {row.get('value')} by rule: "
                + " ".join(str(row.get("how") or "").split())
            )
    return lines
