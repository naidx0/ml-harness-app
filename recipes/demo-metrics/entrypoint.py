"""Emit a synthetic, clearly-labelled loss curve through the engine API.

This is the reference shape for every recipe entrypoint:

- it is handed `--kind` and `--job-json` and nothing else;
- everything the caller chose is read from `job.json`, never from argv;
- it prints progress to stdout, one line at a time, because the runner streams
  stdout to the job log and a job that prints nothing for six hours is
  indistinguishable from a job that is stuck.

The numbers are `exp(-step/8)` plus a sine wobble. They are not measured and
the run is named so that nobody can mistake them for measurements.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request


def post(base_url: str, token: str | None, path: str, payload: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base_url + path,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", required=True)
    parser.add_argument("--job-json", required=True)
    args = parser.parse_args()

    job = json.loads(open(args.job_json, encoding="utf-8").read())
    config = job.get("config") or {}
    steps = int(config.get("steps", 30))
    run_name = str(config.get("run_name", "synthetic-loss-curve"))

    port = os.environ.get("MLH_PORT", "8078")
    base_url = f"http://127.0.0.1:{port}"
    token = os.environ.get("MLH_TOKEN")

    print(f"recipe demo-metrics, kind {args.kind}, {steps} synthetic steps")
    try:
        run = post(base_url, token, "/api/runs",
                   {"name": run_name, "params": {"synthetic": True, "steps": steps}})
    except urllib.error.URLError as exc:
        print(f"cannot reach the engine at {base_url}: {exc}", file=sys.stderr)
        return 1

    for step in range(steps):
        loss = math.exp(-step / 8) + 0.03 * math.sin(step)
        post(base_url, token, f"/api/runs/{run['id']}/metrics",
             {"step": step, "name": "loss", "value": loss})
        print(f"step {step} loss {loss:.4f}")
        time.sleep(0.05)

    post(base_url, token, f"/api/runs/{run['id']}/complete", {})
    print(f"completed synthetic run {run['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
