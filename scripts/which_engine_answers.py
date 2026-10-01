"""ITEM 2: which engine a client of each checkout would authenticate against.

    python scripts/which_engine_answers.py

**THE ONE ITEM THE DESIGNED COLLISION RUN LEFT OPEN.** Its in-run probe timed
out at 60 seconds in both arms, under the load of two concurrent suites, and the
gap was reported as a gap rather than filled in from a standalone probe that had
answered under a different condition. This is that measurement made properly,
with the machine quiet, as its own artefact.

**AND IT IS THE ONLY ONE OF THE NINE THAT CAN SEE THE SHARED VIRTUALENV FROM THE
OUTSIDE.** Two lanes authenticating against one engine is what a shared `app`
package looks like at the security boundary. Nothing collides, no path is
written twice, no test fails - a client simply talks to an engine in a tree it
does not own. Every path-level check in the collision instrument is blind to it.

WHY IT IS A BOUNDARY QUESTION AND NOT AN IMPORT QUESTION. `ENGINE_FILE` is
`data_root()/engine.json` and `data_root()` prefers the checkout of whichever
`app` was imported. So the import decides the data root, the data root decides
the engine file, and the engine file decides which token a local client
presents. One wrong entry on `sys.path` moves all three.

NO TOKEN IS EVER PRINTED. These are live local credentials; what is printed is
whether two of them are the SAME, via a truncated digest. A measurement that
leaks the thing it measures is worse than no measurement.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

#: The two trees on this machine. Named rather than discovered: this answers a
#: question about two specific lanes, and a glob would silently answer about
#: whatever else happened to be lying around.
TREES = {
    "stage": Path(__file__).resolve().parents[1],
    "ml-harness": Path.home() / "OneDrive" / "Documents" / "GitHub" / "ml-harness",
}

#: What a client would ask, from a process that has NOT put a checkout first.
#: Run with the working directory OUTSIDE any checkout, because `python -c` puts
#: the working directory on `sys.path` - a probe run from inside the tree
#: reproduces the correct case while claiming to reproduce the accident, and
#: returns a clean answer. That false negative already happened once.
PROBE = (
    "import json, pathlib;"
    "import app.security as s, app.paths as p;"
    "published = s.read_portfile(s.ENGINE_FILE) or {};"
    "print(json.dumps({"
    "'app_package': str(pathlib.Path(s.__file__).resolve().parents[1]),"
    "'engine_file': str(s.ENGINE_FILE),"
    "'data_root': str(p.data_root()),"
    "'published_pid': published.get('pid'),"
    "'token_present': bool(published.get('token')),"
    "'token_digest': __import__('hashlib').sha256("
    "    (published.get('token') or '').encode()).hexdigest()[:12] if published.get('token') else None"
    "}))"
)


def fingerprint(token: str | None) -> str | None:
    """Twelve hex characters. Enough to compare two tokens, useless as one."""
    return hashlib.sha256(token.encode()).hexdigest()[:12] if token else None


def what_is_published(tree: Path) -> dict:
    """Read the engine file sitting in a tree, without importing anything."""
    engine = tree / "engine.json"
    try:
        published = json.loads(engine.read_text(encoding="utf-8"))
    except (OSError, ValueError) as why:
        return {"engine_file": str(engine), "present": False, "why": repr(why)}
    return {
        "engine_file": str(engine),
        "present": True,
        "pid": published.get("pid"),
        "token_digest": fingerprint(published.get("token")),
        "build": published.get("build") or published.get("sha"),
    }


def asked_from(cwd: Path, first_on_the_path: Path | None) -> dict:
    """Ask the probe, optionally with a checkout forced to the front."""
    environment = dict(os.environ)
    if first_on_the_path is not None:
        environment["PYTHONPATH"] = str(first_on_the_path)
    else:
        environment.pop("PYTHONPATH", None)
    try:
        done = subprocess.run(
            [sys.executable, "-c", PROBE], cwd=str(cwd), env=environment,
            capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        return {"timed_out": True}
    if done.returncode != 0 or not done.stdout.strip():
        return {"failed": f"exit {done.returncode}: {done.stderr.strip()[-300:]}"}
    return json.loads(done.stdout.strip().splitlines()[-1])


def main() -> int:
    outside = Path(tempfile.gettempdir())
    print(f"asked from {outside}, which is inside no checkout\n")

    if os.environ.get("MLH_TOKEN"):
        print("NOTE: MLH_TOKEN is set in this environment, so both lanes would "
              "share a token by arrangement and this measurement says nothing "
              "about resolution. It is not set on the run that produced the "
              "recorded result.\n")

    published = {name: what_is_published(tree) for name, tree in TREES.items()}
    for name, found in published.items():
        if found["present"]:
            print(f"{name:12s} publishes {found['engine_file']}")
            print(f"{'':12s}   pid {found['pid']}, token {found['token_digest']}")
        else:
            print(f"{name:12s} has no engine file at {found['engine_file']}")
    print()

    rows = []
    for name, tree in TREES.items():
        rows.append((f"{name}, repo first", asked_from(outside, tree)))
    rows.append(("no repo first", asked_from(outside, None)))

    for label, answer in rows:
        print(f"{label:24s}")
        if "timed_out" in answer or "failed" in answer:
            print(f"    {answer}")
            continue
        print(f"    app package  {answer['app_package']}")
        print(f"    engine file  {answer['engine_file']}")
        print(f"    data root    {answer['data_root']}")
        print(f"    would present token {answer['token_digest']} "
              f"(published by pid {answer['published_pid']})")
    print()

    #: THE ANSWER TO ITEM 2, and it is a comparison rather than a path.
    naked = dict(rows[-1][1])
    verdict = []
    for name, tree in TREES.items():
        if naked.get("app_package") and Path(naked["app_package"]) == tree:
            verdict.append(
                f"A process in ANY tree that does not put its own checkout first "
                f"imports {name}'s `app`, resolves {name}'s data root, and would "
                f"present {name}'s engine token."
            )
    print("\n".join(verdict) or "no tree claimed the bare import")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
