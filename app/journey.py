"""Where a thread is on its journey, read off the record.

## What this is for

`app/knowledge/playbook.json` has held five named routes since 2026-08-30, and
`train_on_my_files` is seventeen ordered steps from a folder to a scored
adapter. `map_the_ask` hands that route to a MODEL. Nothing handed it to a
PERSON: the steps existed as data, and each one was reachable only by knowing
which of sixty-seven registered tools to reach for, and what to put in it.

Max, relayed 2026-09-02: *"launching a journey overview... with easy
interactable tools, and simple prompting and instruction."* This module is the
reading behind that overview - one GET, no writes, the same law the Stage is
under: **it is a second reader of what the thread already did, never a second
writer.** Building it twice files nothing, which a test asserts.

## The rule, and why it is two rules

The obvious implementation asks, per step, "did this tool run in this thread?"
and it is wrong in both directions. Thread 33 walked this exact route for real
on 1 September and **skipped five of its steps**: it arrived with data already
carved, and it put a baseline on the record with `run_eval` rather than
`measure_baseline`. Asking only "did step 13 run" reads that thread as stuck at
step 2 forever. Ticking step 13 anyway claims a tool ran that never ran.

So there are two questions and the reply keeps them apart:

- **done** - a `tool.result` event for this step's tool, in this thread, that
  came back ok. The step's own summary line comes with it, so the overview can
  say what it produced without re-deriving anything.
- **done_elsewhere** - the step's tool declares facts in `measures`, and every
  one of them is on the ledger, stamped by a DIFFERENT tool. The reply names
  that tool. This is the honest reading of thread 33's baseline: the purpose is
  met, the step did not run, and neither half is hidden.

A step whose tool measures nothing can only ever be `done`. An "all of them are
present" rule over an empty set is vacuously true, and would tick every such
step on an empty thread - which is exactly the generous failure above, arrived
at by a logician rather than by carelessness.

**Order is the route's claim, not the person's obligation.** `next` is the
first step that is neither done nor met, scanning from the top; running step 15
early marks step 15 done and moves nothing, because a later step finishing does
not mean the ones before it happened.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from app import db, diagnosis, events, journey_report
from app.tools import REGISTRY, evidence, knowledge

#: Which states a step can be in. `next` is exactly one step, or none.
DONE = "done"
DONE_ELSEWHERE = "done_elsewhere"
#: Work that does not have to happen on THIS walk. Somebody who arrives with
#: graded rows cannot run `carve_rows` - there is no folder of documents to cut
#: - and `carve_eval_set` succeeding proves rows existed and were good enough
#: to split, which is what that step exists to produce. Marking it done would
#: claim work nobody did; leaving it not-started would demand work nobody
#: needs. Which later step makes which earlier one moot is the ROUTE's
#: knowledge and is declared in `playbook.json` as `unnecessary_if`.
NOT_NEEDED = "not_needed"
NEXT = "next"
AHEAD = "ahead"


def _route(name: str) -> dict[str, Any] | None:
    """The named journey out of the playbook, or None."""
    book = knowledge.load("playbook.json")
    if not book.get("ok"):
        return None
    for journey in book.get("journeys", []):
        if journey.get("name") == name:
            return journey
    return None


def _journeys_available() -> list[str]:
    book = knowledge.load("playbook.json")
    return [j["name"] for j in book.get("journeys", [])] if book.get("ok") else []


def _ran_in(thread_id: int) -> dict[str, dict[str, Any]]:
    """The FIRST successful run of each tool in this thread, by tool name.

    First rather than last, because the overview answers "has this step
    happened", and the answer's timestamp should be when it happened rather
    than when it was last repeated. `read_eval_results` ran nine times in
    thread 33; the step it belongs to happened once.
    """
    out: dict[str, dict[str, Any]] = {}
    with db.session() as connection:
        rows = connection.execute(
            "SELECT payload_json, ts FROM events "
            "WHERE thread_id = ? AND kind = 'tool.result' ORDER BY id",
            (int(thread_id),),
        ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):  # pragma: no cover - we wrote it
            continue
        name = str(payload.get("name") or "")
        if not name or name in out or not payload.get("ok"):
            continue
        result = payload.get("result")
        summary = None
        if isinstance(result, dict):
            said = result.get("summary") or result.get("say")
            summary = str(said) if said else None
        out[name] = {
            "ran_at": row["ts"],
            "driven_by": payload.get("driven_by"),
            "produced": summary,
        }
    return out


def _attempts_in(thread_id: int) -> dict[str, dict[str, Any]]:
    """The newest REFUSED run of each tool in this thread, with what it said.

    ## Why a refusal is worth carrying, and why it is carried as guidance

    Two literature reviews commissioned overnight put numbers on feedback in a
    guided task: bare right/wrong is d = 0.05, DISCOURAGING feedback is
    NEGATIVE at -0.14, and feedback that says why and what next is 0.49, with
    high-information at 0.99. A step that ends in a bare failure is measurably
    worse than one that says nothing at all.

    This route said nothing, which is the other failure. Seventeen refused runs
    sat in one database's event log, each carrying a `detail` this product had
    already written AS A REMEDY - "needs an approval before it can run... it is
    a person saying yes to this specific action" - and none of it reached the
    person walking the route. They pressed the button, it refused, and the step
    looked untouched.

    Newest rather than first, and only while the step is still not done: a
    remedy that worked and is still on screen is this surface telling somebody
    off for something they already fixed, which is the -0.14 case exactly.
    """
    out: dict[str, dict[str, Any]] = {}
    with db.session() as connection:
        rows = connection.execute(
            "SELECT payload_json, ts FROM events "
            "WHERE thread_id = ? AND kind = 'tool.result' ORDER BY id",
            (int(thread_id),),
        ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):  # pragma: no cover - we wrote it
            continue
        name = str(payload.get("name") or "")
        if not name or payload.get("ok"):
            continue
        result = payload.get("result")
        said = result.get("detail") or result.get("summary") if isinstance(result, dict) else None
        out[name] = {
            "at": row["ts"],
            "error": (result or {}).get("error") if isinstance(result, dict) else None,
            "detail": str(said) if said else None,
        }
    return out


def _facts_in(thread_id: int) -> dict[str, str]:
    """Fact name to the tool that most recently stamped it, for this thread."""
    with db.session() as connection:
        rows = connection.execute(
            "SELECT fact, tool FROM fact_evidence WHERE thread_id = ? ORDER BY id",
            (int(thread_id),),
        ).fetchall()
    return {str(row["fact"]): str(row["tool"] or "") for row in rows}


def _results_in(thread_id: int) -> dict[str, dict[str, Any]]:
    """The newest successful RESULT BODY of each tool in this thread.

    `_ran_in` keeps the first run, because "has this step happened" is answered
    by the first time it did. This keeps the LAST, because what a step knows is
    whatever is truest now: a person who carved twice meant the second carve.
    """
    out: dict[str, dict[str, Any]] = {}
    with db.session() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM events "
            "WHERE thread_id = ? AND kind = 'tool.result' ORDER BY id",
            (int(thread_id),),
        ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):  # pragma: no cover - we wrote it
            continue
        name = str(payload.get("name") or "")
        result = payload.get("result")
        if name and payload.get("ok") and isinstance(result, dict):
            out[name] = result
    return out


def _project_root(project_id: int | None) -> str | None:
    """The folder this project already records, or None."""
    if project_id is None:
        return None
    with db.session() as connection:
        row = connection.execute(
            "SELECT root_path FROM projects WHERE id = ?", (int(project_id),)
        ).fetchone()
    return None if row is None else (row["root_path"] or None)


def _baseline_run(thread_id: int) -> int | None:
    """The eval run a later score is paired against: the OLDEST complete run in
    this conversation. It is the one every comparison in `app/stage.py` uses,
    and picking a different one here would let two surfaces disagree about what
    "the baseline" means in the same thread."""
    with db.session() as connection:
        row = connection.execute(
            "SELECT id FROM eval_runs WHERE thread_id = ? ORDER BY id LIMIT 1",
            (int(thread_id),),
        ).fetchone()
    return None if row is None else int(row["id"])


def _newest_sandbox(project_id: int | None) -> str | None:
    """The newest sandbox in this PROJECT, which is the scope sandboxes have.

    Deliberately not thread-scoped, and the wording that goes with it matters.
    A sandbox belongs to a project - `sandbox.every` lists them that way - so a
    conversation that never made one can still be offered the one its project
    holds, which is right and useful. The first draft called it "the sandbox
    you made", and a walk through a fresh thread on an old project caught it:
    that thread made nothing, and the sentence was a claim about the person
    rather than a reading of the record.
    """
    from app.tools import sandbox as sandbox_tools

    try:
        made = sandbox_tools.every(project_id=project_id)
    except Exception:  # noqa: BLE001 - a missing runs directory is not an error here
        return None
    names = [str(one.get("name")) for one in made if one.get("name")]
    return names[-1] if names else None


def _recipe_defaults(recipe: str) -> dict[str, Any]:
    """A recipe's declared `[defaults]`, read from its own `recipe.toml`.

    THE LORA CHOICE, MADE VISIBLE. `lora_r`, `lora_alpha`, `learning_rate` and
    `max_steps` are real knobs with real defaults, and until they were offered
    a person had no way to know they existed: the recipe applied its own and
    the form said nothing. Offering them is what turns a hidden default into a
    choice somebody can see and change.

    Read from the recipe rather than copied here. `entrypoint.py` reads the
    same table, so there is ONE copy of each number and tuning one moves both
    readers at once - which is the whole reason this is not a dict in this
    file. An earlier draft of `_training_config` left `max_steps` out on the
    grounds that nobody had measured it, and that was right while the only
    alternative was inventing one; a value the recipe DECLARES is neither
    invented nor measured, it is the setting that will be used, and hiding it
    served nobody.
    """
    from app import jobspec

    try:
        directory = Path(jobspec.RECIPES_ROOT) / recipe
        manifest = directory / "recipe.toml"
        if not manifest.is_file():
            return {}
        return dict(tomllib.loads(manifest.read_text(encoding="utf-8")).get("defaults") or {})
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return {}


def _training_config(
    results: dict[str, dict[str, Any]], train_path: Any
) -> tuple[str, Any, str]:
    """The training config, assembled from what was chosen and what was copied.

    It is the hardest thing on the route to type and every part of it that CAN
    be known is known:

    - `base_model` is the repo the person had SIZED - `read_model_config`'s own
      answer - rather than the first name on the shortlist. Reading a config is
      how somebody says which model they mean.
    - `dataset_path` is the training file AS THE SANDBOX COPIED IT, matched to
      the carve's own `train_path` through the manifest rather than picked by a
      filename that looks right. The original path and the copy are different
      files, and handing the original to a sandboxed run is the single most
      likely way this step fails.

    `max_steps` is deliberately absent. Nobody measured it, the recipe's own
    default stands when it is left alone, and a number invented here would sit
    in a filled field looking exactly like the two beside it that were read.
    """
    body: dict[str, Any] = {}
    # The recipe's own declared knobs first, so `base_model` and `dataset_path`
    # read as the answers and these read as the settings around them.
    body.update(_recipe_defaults("hf-peft-lora"))
    sized = (results.get("read_model_config") or {}).get("repo_id")
    if sized:
        body["base_model"] = sized

    copied = None
    for entry in (results.get("make_sandbox") or {}).get("snapshotted") or []:
        if not isinstance(entry, dict):
            continue
        if train_path and str(entry.get("path")) == str(train_path):
            copied = entry.get("copied_to")
            break
    if copied:
        body["dataset_path"] = copied

    if not body:
        return ("config", None, "")
    parts = []
    if "base_model" in body:
        parts.append("the model you sized")
    if "dataset_path" in body:
        parts.append("the training half, as the sandbox copied it")
    parts.append("the recipe's own defaults for the rest")
    return ("config", body, ", ".join(parts))


#: `recipe = hf-peft-lora` inside a step's own `args_hint`. The route has
#: always named its backend there; this reads it rather than holding a copy,
#: because a second route with a different backend would otherwise need a
#: change in this module that nobody would remember to make.
_RECIPE_IN_HINT = re.compile(r"recipe\s*=\s*([a-z0-9][a-z0-9._-]*)", re.I)


def _prefill(tool: str, *, thread_id: int, project_id: int | None,
             results: dict[str, dict[str, Any]],
             args_hint: str = "") -> dict[str, dict[str, Any]]:
    """What this step's control can be opened already knowing.

    EVERY VALUE HERE IS READ OFF THE RECORD AND CARRIES `from`. Nothing is
    defaulted: a value nobody measured is left out rather than guessed, because
    a guess sitting in a filled field is indistinguishable from a measurement
    to the person about to press Run. That is the same rule the fact ledger
    lives by, applied to a form.

    The training tail is what forced this. `run_in_sandbox` wants a sandbox
    name and `score_the_adapter` wants a sandbox, a baseline run id and a
    thread id - three things nobody can be expected to type and all three of
    which this harness measured itself.
    """
    carve = results.get("carve_eval_set") or {}
    eval_path = carve.get("eval_path")
    train_path = carve.get("train_path")
    answer_column = carve.get("answer_column")
    from_carve = "the eval set you carved"

    offered: dict[str, dict[str, Any]] = {}

    def offer(field: str, value: Any, source: str) -> None:
        if value is None or value == "":
            return
        offered[field] = {"value": value, "from": source}

    if tool == "make_sandbox":
        # A STEP THAT CAN BE PRESSED IS NOT THE SAME AS ONE THAT IS USEFUL
        # WHEN PRESSED. `make_sandbox` requires nothing, so the route called
        # it a one-click step, and clicking it made a sandbox with no recipe -
        # which `run_in_sandbox` then refused, correctly, with "pins no
        # recipe, so there is nothing in it to run". Found by walking the
        # route as a stranger.
        named = _RECIPE_IN_HINT.search(str(args_hint or ""))
        if named:
            offer("recipe", named.group(1), "the recipe this route names")
    elif tool == "attach_context":
        offer("path", _project_root(project_id), "this project's own folder")
    elif tool == "measure_eval_set":
        offer("path", eval_path, from_carve)
    elif tool == "check_split_leakage":
        offer("train_path", train_path, "the training half you carved")
        offer("eval_path", eval_path, from_carve)
    elif tool in ("measure_baseline", "run_eval"):
        offer("eval_path", eval_path, from_carve)
        # The QUESTION column is not in the carve's record - it only names the
        # answer - so `input_field` is left for the person rather than guessed.
        offer("expected_field", answer_column, "the answer column you carved on")
    elif tool in ("can_this_machine_train", "where_to_train"):
        # THE MODEL THEY SIZED, and step 10 itself is deliberately not filled:
        # choosing which model to read a config for IS the choice, and a
        # shortlist entry offered into that field would be this product making
        # it for them and calling it a reading.
        offer(
            "repo_id",
            (results.get("read_model_config") or {}).get("repo_id"),
            "the model you sized",
        )
    elif tool == "run_in_sandbox":
        offer("name", _newest_sandbox(project_id), "the newest sandbox in this project")
        offer("kind", "train", "this step of the route")
        offer(*_training_config(results, train_path))
    elif tool == "score_the_adapter":
        offer("sandbox", _newest_sandbox(project_id), "the newest sandbox in this project")
        offer("baseline_run_id", _baseline_run(thread_id), "the baseline in this conversation")
        offer("thread_id", thread_id, "this conversation")

    # NEVER A FIELD THE TOOL DOES NOT TAKE. A prefill for a field a tool's
    # schema does not declare would be dropped by the form and look, to anyone
    # reading this reply, like an argument that was sent.
    spec = REGISTRY.declaration(tool) if hasattr(REGISTRY, "declaration") else None
    if spec is None:
        spec = getattr(REGISTRY, "_tools", {}).get(tool)
    declared = set(((getattr(spec, "schema", {}) or {}).get("properties") or {}))
    return {name: body for name, body in offered.items() if name in declared}


def _measures(tool: str) -> tuple[str, ...]:
    """What this tool declares it measures, or () if it is not registered.

    Read off the registry rather than written down here: a hand-kept table of
    step-to-fact would be a second copy of a declaration the tools already
    carry, and the two would disagree the first time a tool learned a fact.
    """
    spec = REGISTRY.declaration(tool) if hasattr(REGISTRY, "declaration") else None
    if spec is None:
        spec = getattr(REGISTRY, "_tools", {}).get(tool)
    return tuple(getattr(spec, "measures", ()) or ())


def _needs_approval(tool: str) -> bool:
    """Does this tool want a person to say yes before it runs?

    READ OFF THE CONTROL FACE, which is the face this question belongs to.
    The first draft read `spec.needs_approval`, an attribute no ToolSpec has -
    the spec carries `approval`, and the boolean is what `as_control()`
    derives from it - so this returned False for every tool on the route and
    the "asks first" chip never once appeared. Found by a test asserting that
    approval outranks a complete argument list, which is the same question
    asked from the other side.
    """
    spec = REGISTRY.declaration(tool) if hasattr(REGISTRY, "declaration") else None
    if spec is None:
        spec = getattr(REGISTRY, "_tools", {}).get(tool)
    if spec is None:
        return False
    try:
        return bool(spec.as_control().get("needs_approval"))
    except Exception:  # noqa: BLE001 - a spec that cannot describe itself asks for nothing
        return False


def _outcome(thread_id: int) -> dict[str, Any] | None:
    """What came out the other end: the adapter's score against the baseline.

    THE LOOP CLOSES HERE. A route could reach seventeen of seventeen and say
    nothing about what it produced - the scores sat in the eval bench, the
    adapter sat on disk, and a person had to go and find both. This reads the
    runs the thread already has and reports the comparison.

    It is `evals.compare`, the same function the Stage uses and the same one
    `score_the_adapter` reported with. A second implementation of "is this
    difference real" would disagree with the first within a month, and this
    surface is the last place that should be inventing a verdict.

    The adapter's run is found by its model name carrying the adapter marker,
    which is what `score_the_adapter` writes there. The baseline is the
    thread's oldest complete run - the same one every other comparison in this
    product pairs against.
    """
    from app.tools import evals

    baseline = _baseline_run(int(thread_id))
    if baseline is None:
        return None
    with db.session() as connection:
        rows = connection.execute(
            "SELECT id, model FROM eval_runs WHERE thread_id = ? ORDER BY id DESC",
            (int(thread_id),),
        ).fetchall()
    scored = next(
        (int(row["id"]) for row in rows if "adapter" in str(row["model"] or "").lower()),
        None,
    )
    if scored is None or scored == baseline:
        return None
    try:
        paired = evals.compare(scored, baseline)
    except Exception:  # noqa: BLE001 - two runs that cannot be paired are not an outcome
        return None
    if not paired.get("ok"):
        return None
    return {
        "adapter_run_id": scored,
        "baseline_run_id": baseline,
        "score": paired.get("score"),
        "baseline_score": paired.get("score_against"),
        "delta": paired.get("delta"),
        "improved": paired.get("improved"),
        "regressed": paired.get("regressed"),
        "paired_rows": paired.get("paired_rows"),
        "p_value": paired.get("p_value"),
        "verdict": paired.get("verdict"),
        "resolved": paired.get("resolved"),
        "rows_that_would_resolve_this_delta": paired.get("rows_that_would_resolve_this_delta"),
        "says": paired.get("says"),
    }


#: A fact name as the ledger writes them. Used to find which facts a gate's
#: own clause reads, by intersecting the clause's identifiers with the facts
#: the ledger declares - never by parsing the expression, which would be this
#: module holding an opinion about the ledger's grammar.
_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*")


def _not_reached_yet(
    answer: dict[str, Any], facts: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The rule that comes first, for a route that stopped before any gate.

    A gate that never ran carries no `clause` - the engine writes one only
    when it evaluates a rule. `_blocked_by` reads the first FAILED gate, so on
    these routes it returned nothing and the screen showed no rule at all, on
    exactly the refusal it exists for. Thread 39 is the live case:
    BLOCKED__DEFINE_SUCCESS_FIRST with all five gates NOT_REACHED.

    "Nothing failed" is not "nothing was checked". The honest reading is that
    zero of five were checked and this is the one that comes first, so the
    rule is read from the ledger's own `passes_when` row rather than invented.

    Two things this refuses to do. It stays quiet unless the outcome is
    actually a refusal, because a route still in progress is not blocked and a
    first-rule banner on a healthy one would be noise. And where the rule
    depends on a method class the run has not chosen - G2 and G3 carry no
    `any` row - it reports the class as undecided instead of picking one,
    since naming the wrong class's rule teaches a rule that does not apply.
    """
    outcome = str(answer.get("outcome") or "")
    if not (outcome.startswith("BLOCKED__") or outcome.startswith("NO_TRAIN__")):
        return None
    gates = answer.get("gates") or {}
    try:
        order = list(diagnosis.load_spec().required_gates)
    except Exception:  # pragma: no cover - a ledger that will not load
        return None

    def status(gate: str) -> str:
        return str((gates.get(gate) or {}).get("status") or "NOT_REACHED")

    first = next((g for g in order if status(g) == "NOT_REACHED"), None)
    if first is None:
        return None
    clause = ""
    undecided = False
    try:
        row = diagnosis.load_spec().gate_row(first, str(answer.get("method_class") or "any"))
        clause = str(row.get("requires") or "")
    except Exception:
        undecided = True
    known = {str(f.get("fact")): f for f in facts}
    declared = set(answer.get("fact_origins") or {})
    reads = []
    for fact in dict.fromkeys(_IDENTIFIER.findall(clause)):
        if fact not in declared and fact not in known:
            continue
        row_f = known.get(fact)
        reads.append(
            {
                "fact": fact,
                "value": row_f.get("value") if row_f else None,
                "origin": row_f.get("origin") if row_f else None,
                "how": row_f.get("how") if row_f else None,
                "unmeasured": row_f is None,
            }
        )
    return {
        "gate": first,
        "reached": False,
        "clause": clause,
        "class_undecided": undecided,
        "checked": sum(1 for g in order if status(g) in {"PASSED", "FAILED"}),
        "of": len(order),
        "reads": reads,
    }


def _blocked_by(answer: dict[str, Any], facts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The rule that stopped this route, the values it read, and where they
    came from.

    From the research lane's built format (`10-Signals/specs/
    refusal-formats.md` §1): a refusal screen earns its place only if it
    carries "the rule, the value, its origin, the arithmetic". The route was
    naming the outcome and counting gates, which is the WHAT; this is the why.

    Everything here is the ledger's own. The gate and its `clause` are
    `journey_report`'s, the facts are the ones that clause names, and the
    values carry the origins the ledger stamped. A fact the clause wants and
    nobody measured is reported as unmeasured rather than as false - the
    commonest refusal on this route is a rule that is unanswered, not one that
    is broken, and a screen that conflated them would be teaching the wrong
    lesson.
    """
    gates = answer.get("gates") or {}
    blocking = next(
        (
            (name, body)
            for name, body in gates.items()
            if str((body or {}).get("status")) == "FAILED"
        ),
        None,
    )
    if blocking is None:
        return _not_reached_yet(answer, facts)
    name, body = blocking
    clause = str((body or {}).get("clause") or "")
    declared = set((answer.get("fact_origins") or {}))
    known = {str(f.get("fact")): f for f in facts}
    wanted = [
        token
        for token in dict.fromkeys(_IDENTIFIER.findall(clause))
        if token in declared or token in known
    ]
    reads = []
    for fact in wanted:
        row = known.get(fact)
        reads.append(
            {
                "fact": fact,
                "value": row.get("value") if row else None,
                "origin": row.get("origin") if row else None,
                "how": row.get("how") if row else None,
                "unmeasured": row is None,
            }
        )
    order = list(gates)
    checked = sum(
        1 for g in order if str((gates.get(g) or {}).get("status")) in {"PASSED", "FAILED"}
    )
    return {
        "gate": name,
        "reached": True,
        "clause": clause,
        "class_undecided": False,
        "checked": checked,
        "of": len(order),
        "reads": reads,
    }


def _verdict(thread_id: int) -> dict[str, Any] | None:
    """The ledger's own answer, and the gates it stands on.

    THE OTHER HALF OF THE SENTENCE. Max's framing was "data in one end, a
    trained adapter OR AN HONEST DO-NOT-TRAIN out the other", and `_outcome`
    carries only the first. The second - the verdict this whole product exists
    to be able to give - was reachable from the Evidence pane and from the
    Stage's gate map, and from nowhere on the route a person was actually
    walking.

    Read from `journey_report`, the same builder the printable report and the
    Stage use. Nothing here re-walks the tree: a second opinion about a verdict
    would be a second product, and the two would part company the first time
    either changed.

    `trains` is computed once, here, off the `TRAIN__` prefix the ledger's own
    invariant is written in - so no reader downstream has to know that rule to
    tell which of the two answers it got.
    """
    try:
        report = journey_report.build(int(thread_id))
    except (KeyError, OSError, ValueError):
        return None
    answer = (report or {}).get("verdict") or {}
    outcome = answer.get("outcome")
    if not outcome:
        return None
    gates = answer.get("gates") or {}
    passed = sum(
        1 for gate in gates.values() if str((gate or {}).get("status")) == "PASSED"
    )
    return {
        "outcome": str(outcome),
        "trains": str(outcome).startswith("TRAIN__"),
        "blocked_by": _blocked_by(answer, list((report or {}).get("facts") or [])),
        "say": answer.get("say") or "",
        "gates_passed": passed,
        "gates_total": len(gates),
    }


def _readiness(tool: str, prefill: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Can this step be a click, and if not, what does it still need?

    The goal's acceptance is blunt - "every step is ONE obvious click, and if
    a step needs a form the form is the design failure" - and that is true of
    most of this route rather than all of it. Saying WHICH is the honest
    surface; opening a form seventeen times and letting a person find out is
    not.

      click    every required argument is on the record already.
      approve  the same, and the tool wants a person to say yes first. Two
               clicks there is deliberate: `Registry.call`'s own rule is that
               approval "is a person saying yes to THIS specific action", so a
               button that sent `approved: true` on its own would launder it.
      needs    something required is missing that only the person can give -
               their own words, or a choice nobody measured. The fields are
               NAMED so the control can ask for them by name.
    """
    spec = REGISTRY.declaration(tool) if hasattr(REGISTRY, "declaration") else None
    if spec is None:
        spec = getattr(REGISTRY, "_tools", {}).get(tool)
    schema = (getattr(spec, "schema", {}) or {})
    required = list(schema.get("required") or [])
    missing = [name for name in required if name not in prefill]
    if missing:
        return {"mode": "needs", "missing": missing}
    return {"mode": "approve" if _needs_approval(tool) else "click", "missing": []}


def build(thread_id: int) -> dict[str, Any]:
    """The journey overview for one thread. Reads; never writes."""
    thread = events.get_thread(int(thread_id))
    if thread is None:
        raise KeyError(thread_id)

    name = thread.get("goal_journey")
    origin = "recorded" if name else None
    matched_on: list[str] = []
    goal = thread.get("goal")
    if not name and goal:
        # The thread has words but nobody matched them - a thread whose goal
        # was set before the playbook, or by a route that does not match. The
        # match is the same one `map_the_ask` makes, and it is reported as
        # `matched` rather than `recorded` so the overview can say it inferred.
        asked = knowledge.map_the_ask(str(goal))
        if asked.get("ok") and asked.get("matched"):
            name = str(asked["matched"])
            origin = "matched"
            matched_on = list(asked.get("matched_on") or [])

    route = _route(str(name)) if name else None
    if route is None:
        return {
            "thread_id": int(thread_id),
            "journey": None,
            "journey_origin": None,
            "matched_on": [],
            "says": None,
            "steps": [],
            "total": 0,
            "done_n": 0,
            "next": None,
            "outcome": None,
            "verdict": None,
            "journeys_available": _journeys_available(),
            "say": (
                "This conversation has no goal on it yet, so there is no route to "
                "show. Say what you have and what you want - the journey is "
                "matched from your own words, and the match is shown before "
                "anything runs."
                if not goal
                else (
                    f"No journey in the playbook matches this conversation's goal. "
                    f"The routes that exist: {', '.join(_journeys_available())}."
                )
            ),
        }

    ran = _ran_in(int(thread_id))
    facts = _facts_in(int(thread_id))
    results = _results_in(int(thread_id))
    attempts = _attempts_in(int(thread_id))
    project_id = thread.get("project_id")

    steps: list[dict[str, Any]] = []
    for ordinal, step in enumerate(route.get("steps", []), start=1):
        tool = str(step.get("tool") or "")
        entry: dict[str, Any] = {
            "ordinal": ordinal,
            "tool": tool,
            "why": step.get("why") or "",
            "args_hint": step.get("args_hint") or "",
            "needs_approval": _needs_approval(tool),
            "prefill": (filled := _prefill(
                tool,
                thread_id=int(thread_id),
                project_id=project_id,
                results=results,
                args_hint=str(step.get("args_hint") or ""),
            )),
            "readiness": _readiness(tool, filled),
            "state": AHEAD,
            "unnecessary_because": None,
            "attempted": None,
            "evidence": None,
            "ran_at": None,
            "driven_by": None,
            "produced": None,
            "satisfied_by": None,
        }
        run = ran.get(tool)
        # A STEP THAT ACTUALLY RAN OUTRANKS BEING EXPLAINED AWAY. It happened,
        # and the route says so rather than deciding after the fact that it
        # need not have.
        superseded = str(step.get("unnecessary_if") or "")
        if run is None and superseded and superseded in ran:
            entry.update(state=NOT_NEEDED, unnecessary_because=superseded)
            steps.append(entry)
            continue
        if run is not None:
            entry.update(
                state=DONE,
                evidence="event",
                ran_at=run["ran_at"],
                driven_by=run["driven_by"],
                produced=run["produced"],
            )
        else:
            wanted = _measures(tool)
            # The empty-set guard. See the module docstring: vacuous truth here
            # would tick every step whose tool stamps nothing.
            if wanted and all(fact in facts for fact in wanted):
                by = {facts[fact] for fact in wanted if facts.get(fact)}
                if by == {tool}:
                    # THE STEP'S OWN TOOL STAMPED IT, so the step ran and the
                    # ledger is the record of it. Found by reading thread 32
                    # rather than by reasoning: its `measure_eval_set` left a
                    # fact and no event row, because user-driven calls did not
                    # write one until 1 September, and the first draft reported
                    # step 7 as "done elsewhere, by measure_eval_set" - which
                    # is not English and not true.
                    entry.update(state=DONE, evidence="ledger")
                else:
                    entry.update(
                        state=DONE_ELSEWHERE,
                        evidence="ledger",
                        satisfied_by={
                            "tool": sorted(by)[0] if by else None,
                            "facts": sorted(wanted),
                        },
                    )
        # A REFUSAL SURVIVES ONLY WHILE IT IS STILL TRUE. Once the step is
        # done - by its own tool or by another's facts - the remedy has been
        # taken and leaving it on screen would be scolding somebody for
        # something they already fixed.
        if entry["state"] not in (DONE, DONE_ELSEWHERE):
            refused = attempts.get(tool)
            if refused and refused.get("detail"):
                entry["attempted"] = refused
        steps.append(entry)

    following = None
    for entry in steps:
        if entry["state"] == AHEAD:
            entry["state"] = NEXT
            following = entry
            break

    # THE FIRST STEP THAT CAN ACTUALLY BE PRESSED, which is not always the
    # first one nobody has done. Found by walking the route on a workspace
    # that arrived with graded rows: step 2 is `carve_rows`, which wants a
    # folder of markdown this workspace does not have, so the route offered
    # exactly one action and that action asked for something that does not
    # exist - while steps 6, 7 and 9 sat ready. `next` stays the answer to
    # "where am I"; this is the answer to "what can I press".
    runnable = next(
        (
            entry
            for entry in steps
            if entry["state"] in (NEXT, AHEAD)
            and entry["readiness"]["mode"] in ("click", "approve")
        ),
        None,
    )

    done_n = sum(1 for s in steps if s["state"] in (DONE, DONE_ELSEWHERE, NOT_NEEDED))
    return {
        "thread_id": int(thread_id),
        "journey": route.get("name"),
        "journey_origin": origin,
        "matched_on": matched_on,
        "says": route.get("says"),
        "steps": steps,
        "total": len(steps),
        "done_n": done_n,
        "next": (None if following is None else
            {
                "ordinal": following["ordinal"],
                "tool": following["tool"],
                "why": following["why"],
                "args_hint": following["args_hint"],
                "needs_approval": following["needs_approval"],
                "readiness": following["readiness"],
            }
        ),
        "next_runnable": (None if runnable is None else
            {
                "ordinal": runnable["ordinal"],
                "tool": runnable["tool"],
                "why": runnable["why"],
                "args_hint": runnable["args_hint"],
                "needs_approval": runnable["needs_approval"],
                "readiness": runnable["readiness"],
            }
        ),
        "outcome": _outcome(int(thread_id)),
        "verdict": _verdict(int(thread_id)),
        "journeys_available": _journeys_available(),
        "say": (
            f"Every step of {route.get('name')} has been done or met. "
            "The route has nothing left to ask for."
            if following is None
            else f"Step {following['ordinal']} of {len(steps)}: {following['why']}."
        ),
    }


# ---------------------------------------------------------------------------
# The journey COMPILES the plan
# ---------------------------------------------------------------------------
#
# Max, 2026-09-18: *"journey is an amazing way to empower the plan... it's not
# using any sub agents... trouble sharing a journey and plan within one folder
# and between sessions."*
#
# MEASURED before this was written, on his own database: `delegate_phase` had
# been called ZERO times, and the reason is upstream of delegation. A phase is
# what one agent can be handed, and the plans a small model types have phases
# with nothing under them - thread 75, 2026-09-17: eight phases, eight
# `**Tools:**` lines, not one `- [ ]` step, and the run parked everything it
# aimed at.
#
# The route this module already reads is the opposite shape. Every step IS a
# tool call; `_prefill` already knows the arguments this conversation measured
# for it; `_measures` already knows the fact it puts on the ledger. So the
# route can be WRITTEN OUT in the document shape `app/instructions/
# cond_planning.md` specifies, and not one line of it has to be invented.
#
# THE READING LAW STILL HOLDS WHERE IT WAS WRITTEN. `build()` writes nothing,
# and the module docstring's "never a second writer" is about that function and
# the overview it serves. Compiling is a different act through a different
# door: it is asked for, it writes the plan column once, through the same path
# `write_plan` writes it, and it leaves the same `thread.plan_written` row
# behind - with `source: "journey"`, so a person reading the transcript can see
# which hand wrote the document.

NEWLINE = chr(10)

#: A PHASE IS A PACK. `app/tools/blocks.py`: the pack is the first segment of a
#: capability name, and every tool declares its own - so which phase a step
#: belongs to is read off the step's tool rather than from a table of
#: step-to-phase that would go stale the first time a route gained a step.
#:
#: CONSECUTIVE, NEVER GATHERED. `score_the_adapter` is step 17 of
#: `train_on_my_files` and is in `training` beside `can_this_machine_train`,
#: which is step 11 - and a phase that put those two
#: together would hand an agent an adapter that does not exist yet. Order is
#: the route's claim (see the module docstring); compiling must not reorder it.
_PHASE_NAMES: dict[str, str] = {
    "machine": "Read this machine",
    "context": "Point at the material",
    "data": "Get the data into a state something can be measured on",
    "ledger": "Record what has been decided",
    "knowledge": "Choose from the dated ladder",
    "models": "Size the model that was chosen",
    "measurement": "Measure where this starts",
    "prompt": "The cheap rungs first",
    "retrieval": "An index, and what it recalls",
    "tabular": "The classical branch",
    "training": "Training, and whether this machine can do it",
    "sandbox": "An isolated, pinned place for the run",
    "agent": "Read the other system's agent",
    "harness": "Whether a harness earns its place",
    "intent": "The standing goal",
}

#: Argument names that hold a path. Used only to fill `**Files/data:**`, which
#: is the phase's own line about what it reads and writes.
_A_PATH = ("path", "root", "dir", "file", "corpus", "index")


def _pack_of_tool(tool: str) -> str:
    """The capability pack this tool is in, or `unregistered`."""
    spec = REGISTRY.get(str(tool)) if hasattr(REGISTRY, "get") else None
    provides = tuple(getattr(spec, "provides", ()) or ()) if spec is not None else ()
    if not provides:
        return "unregistered"
    from app.tools import blocks

    return blocks.pack_of(provides[0])


def _label_of(tool: str) -> str:
    """This tool's control label - the words on its own button, or ``""``."""
    spec = REGISTRY.get(str(tool)) if hasattr(REGISTRY, "get") else None
    if spec is None:
        return ""
    try:
        return str(spec.as_control().get("label") or "")
    except Exception:  # noqa: BLE001 - a spec that cannot describe itself has no label
        return ""


def _reads_and_writes(block: dict[str, Any]) -> str:
    """What this phase touches when it names no path: its tools' declarations.

    `reads=` and `writes=` are not documentation (`app/tools/registry.py`):
    they are what the approval system keys on and what lets a turn be
    summarised without losing what it touched. A phase whose steps name no
    file - reading the model ladder, stating a fact, sizing a config - still
    has an answer to "what does this touch", and it is theirs rather than a
    sentence written here.
    """
    reads: list[str] = []
    writes: list[str] = []
    for entry in block["steps"]:
        spec = REGISTRY.get(str(entry.get("tool") or "")) if hasattr(REGISTRY, "get") else None
        for name in tuple(getattr(spec, "reads", ()) or ()):
            if name not in reads:
                reads.append(str(name))
        for name in tuple(getattr(spec, "writes", ()) or ()):
            if name not in writes:
                writes.append(str(name))
    return (
        "no path of its own - reads " + (", ".join(reads) or "nothing")
        + ", writes " + (", ".join(writes) or "nothing")
    )


def _short(value: Any) -> str:
    """One argument, as a person reads it: no quotes, no JSON, and bounded."""
    if isinstance(value, dict):
        body = ", ".join(f"{key}={_short(item)}" for key, item in value.items())
    elif isinstance(value, (list, tuple)):
        body = ", ".join(_short(item) for item in value)
    else:
        body = str(value)
    body = " ".join(body.split())
    return body if len(body) <= 96 else body[:93] + "..."


def _arguments(entry: dict[str, Any]) -> str:
    """The arguments this conversation already knows for this step.

    `_prefill`'s values, which are read off the record and carry where they
    came from - the eval path it carved, the answer column it carved on, the
    model it sized, the baseline run in this conversation. When it knows none,
    the route's own `args_hint` is written instead: a step still has to say
    what it takes, and the hint is the route saying it. The approval half of
    the hint is dropped because the line carries `(asks first)` for that.
    """
    known = {
        field: body
        for field, body in (entry.get("prefill") or {}).items()
        # NEVER `thread_id`. The registry fills it from the call site and
        # overwrites whatever arrived (`registry.call`, and the three plans a
        # model's invented thread id cost on 2026-09-11), so writing it into a
        # step would be the plan telling somebody to type a number that is
        # ignored.
        if field != "thread_id"
    }
    if known:
        return ", ".join(
            f"{field} = {_short((body or {}).get('value'))}"
            for field, body in known.items()
        )
    hint = str(entry.get("args_hint") or "")
    kept = [
        part.strip()
        for part in hint.split(";")
        if part.strip()
        and "approval" not in part.lower()
        and part.strip().lower() not in ("none", "no arguments")
    ]
    return "; ".join(kept)


def _step_line(entry: dict[str, Any]) -> str:
    """One `- [ ]` line: the tool, the arguments, and the tick it has earned.

    A step the journey reads as `done` or `done_elsewhere` is written `- [x]`,
    because a compiled plan that asked for work already on the record would
    send a run to do it again. A step the route says is NOT NEEDED on this walk
    is PARKED with the reason rather than ticked - `carve_rows` did not happen
    and claiming it did would be the generous lie the module docstring refuses.
    """
    from app.tools import planning

    tool = str(entry.get("tool") or "")
    why = " ".join(str(entry.get("why") or "").split())
    sentence = (why[:1].upper() + why[1:]) if why else f"Call {tool}"
    args = _arguments(entry)
    line = sentence + f" with `{tool}`" + (f" - {args}" if args else "")
    if entry.get("needs_approval"):
        line += " (asks first)"
    state = str(entry.get("state") or "")
    if state in (DONE, DONE_ELSEWHERE):
        return "- [x] " + line
    if state == NOT_NEEDED:
        because = str(entry.get("unnecessary_because") or "a later step")
        return (
            "- [!] "
            + line
            + planning.PARKED_MARK
            + f"not needed on this walk - {because} did this step's work"
        )
    return "- [ ] " + line


def _phase_blocks(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The route's steps cut into phases, in order, each named once.

    A name is made unique by naming the phase's first tool when the same pack
    comes round twice, because the name is what a sub-agent is handed:
    `subagents.phase_slice` refuses a phase that matches two headings, so two
    phases called `Training` would be two phases nobody can delegate.
    """
    out: list[dict[str, Any]] = []
    for entry in steps:
        pack = _pack_of_tool(str(entry.get("tool") or ""))
        if out and out[-1]["pack"] == pack:
            out[-1]["steps"].append(entry)
            continue
        out.append({"pack": pack, "steps": [entry]})
    taken: set[str] = set()
    for block in out:
        name = _PHASE_NAMES.get(
            block["pack"], str(block["pack"]).replace("_", " ").title()
        )
        if name in taken:
            # A pack that comes round twice is named for what this visit
            # DOES, off the tool's own control label - `Score the adapter`
            # rather than `Training, and whether this machine can do it` for
            # the second time. The label is the button a person presses for
            # that tool, so the phase and the control say the same words.
            first = str(block["steps"][0].get("tool") or "")
            name = _label_of(first) or first or name
            while name in taken:
                name = f"{name} ({first})"
        taken.add(name)
        block["name"] = name
    return out


def _files_line(block: dict[str, Any], attached: list[str], root: str | None) -> str:
    """`**Files/data:**` - the paths this phase reads or writes, when known."""
    seen: list[str] = []
    for entry in block["steps"]:
        for field, body in (entry.get("prefill") or {}).items():
            if not any(word in str(field).lower() for word in _A_PATH):
                continue
            value = _short((body or {}).get("value"))
            if value and value not in seen:
                seen.append(value)
    if not seen and any(e.get("tool") == "attach_context" for e in block["steps"]):
        seen = [p for p in attached[:3] if p] or ([str(root)] if root else [])
    # NO PATH IS NOT NO ANSWER, AND IT IS NOT THE PROJECT FOLDER EITHER. The
    # first draft fell back to the project root on every phase, so six phases
    # of the training route claimed to read a folder none of them opens. What
    # a pathless phase touches is what its tools declare they touch.
    return ", ".join(seen) if seen else _reads_and_writes(block)


def _verify_line(block: dict[str, Any], *, name_the_tools: bool = True) -> str:
    """`**Verify:**` - the fact this phase leaves on the ledger, or the record.

    THE FACT IS THE MEASUREMENT. A tool's `measures=` is what it may stamp, so
    a phase whose tools declare facts has a verification nobody has to invent:
    the names are on the ledger afterwards or the phase did not happen. A phase
    whose tools measure nothing verifies by its own result, which is the honest
    weaker claim rather than a number made up to look like one.
    """
    facts: list[str] = []
    for entry in block["steps"]:
        for fact in _measures(str(entry.get("tool") or "")):
            if fact not in facts:
                facts.append(fact)
    if facts:
        named = ", ".join(f"`{fact}`" for fact in facts)
        return (
            f"the ledger carries {named} for this conversation, stamped by the "
            f"tool that measured {'them' if len(facts) > 1 else 'it'}"
        )
    many = len(block["steps"]) > 1
    if not name_the_tools:
        # The caller has already said the tool's name in the same sentence;
        # saying it twice is how the closing line read before this.
        return "its result is on this conversation's record"
    tools = ", ".join(f"`{e.get('tool')}`" for e in block["steps"])
    return (
        f"{tools} came back ok, and what {'they' if many else 'it'} produced is "
        "on this conversation's record"
    )


def _document(
    overview: dict[str, Any],
    thread: dict[str, Any],
    attached: list[str],
    root: str | None,
) -> str:
    """The plan, in the shape `app/instructions/cond_planning.md` specifies."""
    steps = list(overview.get("steps") or [])
    phases = _phase_blocks(steps)
    route = str(overview.get("journey") or "")
    says = " ".join(str(overview.get("says") or "").split()).rstrip(".")
    goal = " ".join(str(thread.get("goal") or "").split())
    last = steps[-1]
    origin = str(overview.get("journey_origin") or "")
    matched_on = [str(word) for word in (overview.get("matched_on") or [])]

    lines: list[str] = ["# " + (says or route), "", "## Root of the ask"]
    lines.append(
        goal
        if goal
        else "This conversation has not put its goal in the person's own words "
        "yet; the route below is what it has been doing."
    )
    provenance = ""
    if origin == "matched" and matched_on:
        provenance = f", matched from the goal's own words ({', '.join(matched_on)})"
    elif origin == "recorded":
        provenance = ", recorded on this conversation"
    lines.append(f"The route is `{route}`" + provenance + ".")
    lines.append(
        "Done is: "
        + " ".join(str(last.get("why") or "").split())
        + f", with `{last.get('tool')}`."
    )
    done_n = int(overview.get("done_n") or 0)
    if done_n:
        lines.append(
            f"{done_n} of {len(steps)} steps are already on this conversation's "
            "record and are ticked below; a run starts at the first open one."
        )

    for number, block in enumerate(phases, start=1):
        tools: list[str] = []
        for entry in block["steps"]:
            name = str(entry.get("tool") or "")
            if name and name not in tools:
                tools.append(name)
        lines.extend(
            [
                "",
                f"## Phase {number} - {block['name']}",
                "**Files/data:** " + _files_line(block, attached, root),
                "**Tools:** " + ", ".join(f"`{name}`" for name in tools),
            ]
        )
        lines.extend(_step_line(entry) for entry in block["steps"])
        lines.append("**Verify:** " + _verify_line(block) + ".")

    closing = str(last.get("tool") or "")
    ticked = str(last.get("state") or "") in (DONE, DONE_ELSEWHERE)
    lines.extend(
        [
            "",
            "## Verification",
            ("- [x] " if ticked else "- [ ] ")
            + f"Check the route closed, with `{closing}`: "
            + _verify_line({"steps": [last]}, name_the_tools=False)
            + ".",
            "",
            "## Out of scope",
            f"- Anything the `{route}` route does not name. This plan IS that "
            "route compiled, step for step, so a step no registered tool can do "
            "is not in it.",
        ]
    )
    skipped = [
        str(entry.get("tool"))
        for entry in steps
        if str(entry.get("state") or "") == NOT_NEEDED
    ]
    if skipped:
        lines.append(
            "- "
            + ", ".join(f"`{name}`" for name in skipped)
            + " - this conversation arrived past "
            + ("them" if len(skipped) > 1 else "it")
            + ", so the steps are parked above with the reason rather than planned."
        )
    return NEWLINE.join(lines) + NEWLINE


def compile_plan(
    thread_id: int, *, write: bool = True, replace: bool = False
) -> dict[str, Any]:
    """Turn this conversation's journey into its plan, and save it.

    Refuses rather than overwrites when a plan is already saved: a plan is a
    document a person read and pressed Build on, and a compiler that replaced
    it would be this harness arguing with them. `replace=True` is for a caller
    that has already decided, and nothing in the product passes it today.
    """
    try:
        overview = build(int(thread_id))
    except KeyError:
        return {"ok": False, "error": "no_such_thread", "thread_id": int(thread_id)}
    if not overview.get("journey") or not overview.get("steps"):
        return {
            "ok": False,
            "error": "no_journey",
            "detail": (
                "This conversation has no journey to compile. Say what it is for "
                "with set_goal, or write the plan yourself with write_plan. "
                + str(overview.get("say") or "")
            ).strip(),
            "journeys_available": list(overview.get("journeys_available") or []),
        }
    thread = events.get_thread(int(thread_id)) or {}
    saved = str(thread.get("plan") or "").strip()
    if saved and write and not replace:
        return {
            "ok": False,
            "error": "a_plan_is_already_saved",
            "detail": (
                "This conversation already has a plan. Read it with read_plan and "
                "revise it with write_plan - compiling would write over a document "
                "the person may have edited."
            ),
        }
    attached: list[str] = []
    try:
        from app.tools import context as _context

        attached = [
            str(row.get("path")) for row in _context.list_contexts(int(thread_id))
        ]
    except Exception:  # noqa: BLE001 - a plan is not worth failing over a file list
        attached = []
    text = _document(
        overview, thread, attached, _project_root(thread.get("project_id"))
    )

    from app.tools import planning

    answer: dict[str, Any] = {
        "ok": True,
        "journey": overview.get("journey"),
        "phases": len(_phase_blocks(list(overview.get("steps") or []))),
        "characters": len(text),
        "steps_open": len(planning.open_steps(text)),
        "steps_done": sum(1 for s in planning.steps_in(text) if s["state"] == "done"),
        "phases_without_steps": planning.phases_without_steps(text),
        "steps_without_a_tool": planning.steps_without_a_tool(text),
        "plan": text,
    }
    if not write:
        answer["written"] = False
        return answer

    # THE SAME PATH `write_plan` WRITES, AND THE SAME ROW AFTERWARDS. A second
    # way of saving a plan would be a second set of things to keep in step -
    # the file mirror, the diff the transcript expands, the pane that polls.
    from app import plandiff

    before = thread.get("plan")
    row = events.set_thread_plan(int(thread_id), text)
    if row is None:  # pragma: no cover - the thread was read one line above
        return {"ok": False, "error": "no_such_thread", "thread_id": int(thread_id)}
    events.append(
        "thread.plan_written",
        {
            "thread_id": int(thread_id),
            "source": "journey",
            "journey": overview.get("journey"),
            "phases": answer["phases"],
            "characters": len(text),
            "headings": planning.headings_in(text)[:16],
            "steps_open": answer["steps_open"],
            "phases_without_steps": answer["phases_without_steps"],
            "diff": plandiff.rows_between(before, text),
        },
        project_id=thread.get("project_id"),
        thread_id=int(thread_id),
    )
    answer["written"] = True
    answer["saved"] = True
    return answer
