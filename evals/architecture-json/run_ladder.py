"""Run the five ladder arms through the engine API, one thread each.

    python evals/architecture-json/run_ladder.py            # run every arm
    python evals/architecture-json/run_ladder.py --arm twoshot

THROUGH THE ENGINE, NEVER A MODEL DIRECTLY. Every answer this produces comes
from `measure_baseline` reached over `POST /api/tools/measure_baseline`, which
is the door a person's own application uses. Calling Ollama here would measure a
different system from the one the product is: the engine's prompt assembly, its
provider adapter and its scoring are the thing under test as much as the model
is.

ONE THREAD PER ARM, and it is not tidiness. `measure_baseline` stamps
`baseline_score` on the thread it is given, whatever eval produced it, so five
arms into one thread would leave one number wearing the last arm's value and the
first four silently replaced. The engine warns about this since `80991a5` and
does not refuse, which makes it the caller's job.

WHAT IT DOES NOT DECIDE. Nothing here computes the reported metric.
`measure_baseline` scores exact match, which is 0 of 20 on every arm because
exact-matching a serialised graph measures key order; `score.py` reads the rows
this persists and applies schema-validity and node-label F1 separately. This
file's whole job is to produce those rows, one arm at a time, and say where they
landed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parents[1]

#: The arms, in the order the question is asked: how far does an example go?
#: `offdomain` is last because it is the control rather than a rung.
ARMS = ["zeroshot", "namingrule", "oneshot", "twoshot", "threeshot", "offdomain"]

#: n for every arm. The set is twenty rows and every figure is reported with it.
ROWS = 20


def engine() -> tuple[str, str]:
    """(base url, token) for THIS checkout's engine, from its own portfile."""
    published = json.loads((REPO / "engine.json").read_text(encoding="utf-8"))
    return "http://127.0.0.1:" + str(published["port"]), str(published["token"])


def ask(path: str, payload: dict | None = None, method: str = "POST", timeout: int = 7200) -> dict:
    base, token = engine()
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        base + path,
        data=data,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return json.loads(answer.read() or b"{}")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:600]
        raise SystemExit("HTTP " + str(error.code) + " from " + path + ": " + detail)


def a_project() -> int:
    """The ladder's own project, reused if this is a resumed run."""
    for project in ask("/api/projects", method="GET") or []:
        if project.get("name") == "few-shot ladder (architecture-json)":
            return int(project["id"])
    made = ask("/api/projects", {"name": "few-shot ladder (architecture-json)",
                                 "root_path": str(REPO)})
    return int(made["id"])


def a_thread(project_id: int, arm: str) -> int:
    made = ask("/api/threads", {"title": "ladder: " + arm, "project_id": project_id})
    return int(made["id"])


def run(arm: str, provider_id: int, project_id: int) -> dict:
    eval_path = HERE / ("ladder-" + arm + ".jsonl")
    if not eval_path.is_file():
        raise SystemExit("no such arm: " + str(eval_path) + " - run build_ladder.py first")

    thread_id = a_thread(project_id, arm)
    began = time.time()
    print("  arm " + arm.ljust(10) + " thread " + str(thread_id) + " ... ", end="", flush=True)
    answer = ask(
        "/api/tools/measure_baseline",
        {
            "thread_id": thread_id,
            "approved": True,
            "arguments": {
                "eval_path": str(eval_path),
                "input_field": "input",
                "expected_field": "expected",
                "sample": ROWS,
                "provider_id": provider_id,
            },
        },
    )
    took = time.time() - began
    result = answer.get("result", answer)
    rows_path = result.get("rows_path")
    #: RECORDED RELATIVE TO THE REPOSITORY. The first version wrote the
    #: absolute path the engine returned, so this provenance file carried a
    #: real home directory and a checkout name into a tracked file - three
    #: denylist rules at once, caught by the gate, by the lane that spent
    #: Saturday writing that this is worth removing whether or not a check
    #: is pointed at it. A path is provenance only if a reader elsewhere can
    #: use it, and an absolute path on one machine is not that.
    if rows_path:
        try:
            rows_path = str(Path(rows_path).resolve().relative_to(REPO).as_posix())
        except ValueError:
            rows_path = Path(rows_path).name
    print(str(round(took)) + "s  rows -> " + str(rows_path))
    #: The engine's own exact-match score is printed but never reported as the
    #: result: it is 0 on every arm by construction, and saying so here stops it
    #: being quoted later as if the arms had all failed.
    return {
        "arm": arm,
        "thread_id": thread_id,
        "seconds": round(took, 1),
        "rows_path": rows_path,
        "exact_match_score": result.get("baseline_score"),
        "replaced_a_baseline_from": result.get("replaced_a_baseline_from"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arm", choices=ARMS, action="append",
                        help="run only this arm (repeatable); default is all five")
    parser.add_argument("--provider-id", type=int, required=True,
                        help="the provider to drive; named rather than inferred "
                             "so the arm cannot silently change model")
    args = parser.parse_args()

    arms = args.arm or ARMS
    providers = {p["id"]: p for p in ask("/api/providers", method="GET")}
    chosen = providers.get(args.provider_id)
    if chosen is None:
        raise SystemExit("no provider " + str(args.provider_id))
    print("model   " + str(chosen["model"]) + "  (provider " + str(args.provider_id) + ")")
    print("n       " + str(ROWS) + " rows per arm, which resolves about 8 points")
    print("arms    " + ", ".join(arms))
    print()

    project_id = a_project()
    done = []
    for arm in arms:
        done.append(run(arm, args.provider_id, project_id))

    out = HERE / "ladder-runs.json"
    #: APPEND RATHER THAN REPLACE. A second invocation for one arm must not
    #: erase the other four's provenance.
    was = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    out.write_text(json.dumps(was + done, indent=2) + chr(10), encoding="utf-8")
    print()
    print("wrote " + str(out))
    print("now:  python evals/architecture-json/score.py " +
          " ".join(str(d["rows_path"]) for d in done if d["rows_path"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
