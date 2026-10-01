"""Emit a fake-but-labeled loss curve so the dashboard can be tested.

**This script never opens a database, and that is exactly why it was dangerous.**
It POSTs to whatever engine answers on `app.config.BASE_URL`, and the rows land
in whatever `ML_HARNESS_DB` resolved to *in that engine's* process. So no amount
of care in the caller's process protects anything: rebinding `db.DB_PATH` before
running this script rebinds a global the script's target never reads.

On a machine where the real engine is listening on the default port, every run
of this script adds one run and thirty metric rows to the user's real database.
The repository's `ml_harness.db` holds 1,036 runs named `demo-loss-curve`,
because the test suite ran this script on every pass.

The knob that decides where the curve lands is therefore `MLH_PORT` - the port
of the engine being written to - and it is read by `app/config.py`, not here.
A caller that wants a disposable curve starts an engine of its own with
`ML_HARNESS_DB` pointing somewhere temporary and sets `MLH_PORT` to that
engine's port. `tests/test_demo_script_runs.py` does precisely that, and checks
afterwards that the real file did not move a byte.

Because the destination is invisible from the call site, the script prints it
before it writes anything.
"""

import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app import security
from app.config import BASE_URL


BASE = BASE_URL

#: Steps in the curve.
STEPS = 30

#: The pause between steps. It exists so the dashboard shows a curve *arriving*
#: rather than a finished picture, which is the whole point of the demo, so it
#: stays the default. A caller that only wants the rows - the test - sets
#: `MLH_DEMO_STEP_DELAY=0` and gets the same thirty of them with no wait.
STEP_DELAY = float(os.environ.get("MLH_DEMO_STEP_DELAY", "0.15"))


def post(path: str, payload: dict) -> dict:
    # The engine's API is authenticated. The token is read from engine.json,
    # which the engine writes at startup - the same file the dashboard
    # launcher and the test suite read.
    headers = {"Content-Type": "application/json"}
    headers.update(security.auth_header())
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def main() -> int:
    # Said out loud, before the first write, because the destination is chosen
    # by an environment variable in another process and is otherwise invisible.
    print(f"writing demo run to {BASE}")
    try:
        run = post(
            "/api/runs",
            {"name": "demo-loss-curve", "params": {"lr": 0.01, "synthetic": True}},
        )
        for step in range(STEPS):
            loss = math.exp(-step / 8) + 0.03 * math.sin(step)
            post(f"/api/runs/{run['id']}/metrics", {"step": step, "name": "loss", "value": loss})
            if STEP_DELAY:
                time.sleep(STEP_DELAY)
        post(f"/api/runs/{run['id']}/complete", {})
    except urllib.error.URLError as error:
        # Covers a refused connection and an HTTP error alike - HTTPError is a
        # URLError. A traceback here used to read as a bug in the script; it is
        # almost always "no engine is running on that port", so say that.
        print(f"no usable engine at {BASE}: {error}", file=sys.stderr)
        return 1
    print(f"completed demo run {run['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
