"""Run system-design prompt arms through the engine API, one thread each.

    python evals/system-design/run_arms.py --provider-id 6 arm-components-bare.jsonl

THROUGH THE ENGINE, NEVER OLLAMA DIRECTLY. `baseline.py` posts to
`/v1/chat/completions` itself, which measures the model; this measures the
product - the engine's prompt assembly, its provider adapter and its transport
are as much under test as the weights.

ONE THREAD PER ARM. `measure_baseline` stamps `baseline_score` on the thread it
is given whatever eval produced it, so two arms sharing a thread leave one
number wearing the second arm's value with the first silently replaced.

The exact-match score the engine returns is NOT the result for `components`,
whose answers are sets; `score_arms.py` reads the persisted rows and applies the
per-family metrics.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parents[1]


def engine():
    published = json.loads((REPO / "engine.json").read_text(encoding="utf-8"))
    return "http://127.0.0.1:" + str(published["port"]), str(published["token"])


def ask(path, payload=None, method="POST", timeout=14400):
    base, token = engine()
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        base + path, data=data,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return json.loads(answer.read() or b"{}")
    except urllib.error.HTTPError as error:
        raise SystemExit("HTTP " + str(error.code) + " from " + path + ": "
                         + error.read().decode("utf-8", "replace")[:500])


def a_project():
    for project in ask("/api/projects", method="GET") or []:
        if project.get("name") == "system-design prompt arms":
            return int(project["id"])
    return int(ask("/api/projects", {"name": "system-design prompt arms",
                                     "root_path": str(REPO)})["id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("arms", nargs="+")
    parser.add_argument("--provider-id", type=int, required=True)
    args = parser.parse_args()

    providers = {p["id"]: p for p in ask("/api/providers", method="GET")}
    chosen = providers.get(args.provider_id)
    if chosen is None:
        raise SystemExit("no provider " + str(args.provider_id))
    print("model  " + str(chosen["model"]) + "  (provider " + str(args.provider_id) + ")")

    project_id = a_project()
    done = []
    for name in args.arms:
        path = HERE / Path(name).name
        if not path.is_file():
            raise SystemExit("no such arm: " + str(path))
        rows = sum(1 for line in path.open(encoding="utf-8") if line.strip())
        thread_id = int(ask("/api/threads", {"title": "arm: " + path.stem,
                                             "project_id": project_id})["id"])
        began = time.time()
        print("  " + path.stem.ljust(38) + " n=" + str(rows).rjust(3)
              + " thread " + str(thread_id) + " ... ", end="", flush=True)
        answer = ask("/api/tools/measure_baseline", {
            "thread_id": thread_id, "approved": True,
            "arguments": {"eval_path": str(path), "input_field": "input",
                          "expected_field": "expected", "sample": rows,
                          "provider_id": args.provider_id}})
        took = time.time() - began
        result = answer.get("result", answer)
        rows_path = result.get("rows_path")
        relative = str(Path(rows_path).resolve().relative_to(REPO).as_posix()) if rows_path else None
        print(str(round(took)) + "s  " + str(round(took / max(rows, 1), 1)) + "s/row")
        done.append({"arm": path.stem, "n": rows, "thread_id": thread_id,
                     "seconds": round(took, 1), "rows_path": relative})

    out = HERE / "arm-runs.json"
    was = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    out.write_text(json.dumps(was + done, indent=2) + chr(10), encoding="utf-8")
    print()
    print("wrote " + str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
