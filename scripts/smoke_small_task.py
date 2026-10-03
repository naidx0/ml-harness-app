"""Live smoke: one small ML task, end to end, through the engine the window uses.

    python scripts/smoke_small_task.py            # iris, against the running engine
    python scripts/smoke_small_task.py --task csv # linear regression on a bundled CSV
    python scripts/smoke_small_task.py --no-folder # iris, as a first chat with no project folder chosen

It reads engine.json (the portfile the app writes), opens a Full session in a
fresh empty folder, sends the task, waits for the turn to end, and passes only
when a run_project_command exited 0 with the true metric in its stdout AND the
reply states that number - the same scorer as lab/log.md "H-shell". Exit 0 on a
finish, 1 on a run that did not finish, 2 when there is no engine to talk to.

It needs a model, so it is not in the unit gate; tests/test_shell_compat.py is
the gate's side of the same guarantee.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

TASKS = {
    "iris": {
        "prompt": (
            "Train a logistic regression classifier on scikit-learn's built-in iris "
            "dataset with an 80/20 train/test split and random_state=0, then tell me "
            "the test accuracy."
        ),
        "truth": r"(?<![\d.])(1\.0+|100(\.0+)?\s*%)(?![\d])",
    },
    "csv": {
        "prompt": (
            "The file data.csv in this folder has columns x1, x2 and y. Fit a linear "
            "regression that predicts y from x1 and x2 with an 80/20 train/test split "
            "and random_state=0, then tell me the test R^2."
        ),
        "truth": r"(?<![\d.])(0\.944\d*|94\.4\d*\s*%)",
    },
}


def the_csv() -> str:
    """The H-shell T2 file, byte for byte (sha256 95e5489f...)."""
    rng = random.Random(7)
    rows = ["x1,x2,y"]
    for _ in range(200):
        x1 = round(rng.uniform(0, 10), 3)
        x2 = round(rng.uniform(-5, 5), 3)
        y = round(3.0 * x1 - 2.0 * x2 + 4.0 + rng.gauss(0, 2.0), 3)
        rows.append(f"{x1},{x2},{y}")
    return "\n".join(rows) + "\n"


def portfile() -> Path | None:
    from app import paths

    for candidate in (paths.in_data_root("engine.json"), REPO / "engine.json"):
        if candidate.is_file():
            return candidate
    return None


def score(messages: list[dict], truth: re.Pattern[str]) -> dict:
    ran = False
    final = ""
    for message in messages:
        if message.get("type") != "assistant":
            continue
        for part in message.get("content", []):
            if part.get("type") == "text" and part.get("text", "").strip():
                final = part["text"]
            if part.get("type") != "tool" or part.get("name") != "run_project_command":
                continue
            text = "".join(
                x.get("text", "") for x in part.get("state", {}).get("content", []) if isinstance(x, dict)
            )
            try:
                result = json.loads(text)
            except ValueError:
                continue
            if result.get("exit_code") == 0 and truth.search(str(result.get("stdout", ""))):
                ran = True
    return {"metric_from_a_run": ran, "reply_states_it": bool(truth.search(final)), "finished": ran and bool(truth.search(final))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=sorted(TASKS), default="iris")
    parser.add_argument("--budget", type=int, default=900, help="seconds to wait for the turn")
    parser.add_argument("--out", help="write the transcript here")
    parser.add_argument(
        "--no-folder", action="store_true",
        help="send no location, as a first chat on a fresh install does (iris only)",
    )
    args = parser.parse_args()

    found = portfile()
    if found is None:
        print("no engine.json: start the app first", file=sys.stderr)
        return 2
    engine = json.loads(found.read_text(encoding="utf-8"))
    base = f"http://127.0.0.1:{engine['port']}/oc"
    headers = {"Authorization": f"Bearer {engine['token']}", "Content-Type": "application/json"}

    def call(method: str, path: str, body: dict | None = None):
        request = urllib.request.Request(
            base + path, method=method, headers=headers,
            data=json.dumps(body).encode() if body is not None else None,
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            return json.loads(raw) if raw else None

    task = TASKS[args.task]
    if args.no_folder and args.task == "csv":
        print("--no-folder needs a task with no input file", file=sys.stderr)
        return 2
    folder: Path | None = None
    request: dict = {"agent": "full", "title": f"smoke {args.task}"}
    if not args.no_folder:
        folder = Path(tempfile.mkdtemp(prefix=f"mlh-smoke-{args.task}-"))
        if args.task == "csv":
            (folder / "data.csv").write_bytes(the_csv().encode())
        request["location"] = {"directory": str(folder)}
    created = call("POST", "/api/session", request)["data"]
    session = created["id"]
    call("POST", f"/api/session/{session}/prompt", {"text": task["prompt"]})
    started = time.time()
    messages: list[dict] = []
    while time.time() - started < args.budget:
        time.sleep(8)
        body = call("GET", f"/api/session/{session}/message")
        messages = body.get("data", body) if isinstance(body, dict) else body
        if any(m.get("type") == "idle" for m in messages):
            break
    verdict = score(messages, re.compile(task["truth"]))
    where = str(folder) if folder else (created.get("location") or {}).get("directory")
    verdict.update(task=args.task, session=session, folder=where, seconds=round(time.time() - started))
    if args.out:
        Path(args.out).write_text(json.dumps({"verdict": verdict, "messages": messages}, indent=1), encoding="utf-8")
    print(json.dumps(verdict))
    return 0 if verdict["finished"] else 1


if __name__ == "__main__":
    sys.path.insert(0, str(REPO))
    sys.exit(main())
