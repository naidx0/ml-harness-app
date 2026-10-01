"""`mlh` - the first thing an installed copy can be asked to do.

`docs/THE_PLAN.md` Phase V step A5 asks for `[project.scripts] mlh = "app.cli:main"`
and calls it "the first non-zero entry for the install metric". This is that
entry, and it is deliberately small: what an installer has to prove first is
that `pip install .` produces something a stranger can RUN, and the honest way
to prove that is a command that starts, reads what shipped with it, and reports
what it found.

## Why the first command is `doctor` and not `serve`

Serving is what `scripts/launch.py` does and it does it with thirty tests behind
it. Moving that here is step A6 and it is a real refactor. What A5 needs is the
console-script seam itself - proof that the entry point resolves, that the
package imports outside a checkout, and that the things `pip install .` was
found NOT to ship in Phase V.0 are there now.

So `doctor` answers exactly the questions V.0 measured as broken:

    ledger      docs/diagnosis_engine.yaml     0 hits in SOURCES.txt
    ledgers     docs/ledgers/                  0 hits
    model_configs                              0 hits
    recipes                                    0 hits

Each of those was an installed engine that could not load its own diagnosis
spec, could not compute a VRAM figure, and could not resolve a recipe. Two of
the four are fixed - `app/model_configs` is declared package data and the
ledgers are bundled by `setup.py` - and `doctor` is what says so on the machine
somebody actually installed onto, rather than in a test on the machine that
built it.

## What it deliberately does not do

Write anything. Start anything. Ask anything. A first command that created a
data directory as a side effect of being asked whether it was healthy would be
the kind of thing that makes `--dry-run` necessary.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def _findings() -> list[dict[str, Any]]:
    """What this installation can and cannot do, read rather than assumed.

    Every row is a real import and a real filesystem question, in the order
    Phase V.0 measured them broken. Imports are inside the function so a broken
    one is a FINDING rather than a stack trace on `mlh --help`.
    """
    from app import paths

    rows: list[dict[str, Any]] = [
        {
            "check": "data_root",
            "ok": True,
            "detail": str(paths.data_root()),
            "why": (
                "where this installation writes. A checkout keeps its own files "
                "where they are; an install gets a per-user root."
            ),
        }
    ]

    try:
        from app import diagnosis

        ledgers = [diagnosis.spec_at(path).as_written for path in diagnosis.known_ledgers()]
        rows.append(
            {
                "check": "ledgers",
                "ok": bool(ledgers),
                "detail": ", ".join(ledgers) or "none found",
                "why": (
                    "the files holding every gate, outcome and fact this product "
                    "has. `pip install .` shipped none of them until setup.py's "
                    "build step; an engine that starts and cannot load these "
                    "cannot answer anything."
                ),
            }
        )
    except Exception as error:  # noqa: BLE001 - a broken install is a finding
        rows.append(
            {
                "check": "ledgers",
                "ok": False,
                "detail": f"{type(error).__name__}: {error}",
                "why": "the engine could not load its own knowledge",
            }
        )

    try:
        from app import feasibility

        configs = sorted(feasibility.MODEL_CONFIG_ROOT.glob("*.json"))
        rows.append(
            {
                "check": "model_configs",
                "ok": bool(configs),
                "detail": f"{len(configs)} config(s) at {feasibility.MODEL_CONFIG_ROOT}",
                "why": (
                    "the geometries a VRAM figure is computed from. Twenty-seven "
                    "JSON files inside the package that no wheel shipped until "
                    "they were declared."
                ),
            }
        )
    except Exception as error:  # noqa: BLE001
        rows.append(
            {
                "check": "model_configs",
                "ok": False,
                "detail": f"{type(error).__name__}: {error}",
                "why": "no model geometry could be read",
            }
        )

    try:
        from app.tools import knowledge

        rows.append(knowledge.doctor_row())
    except Exception as error:  # noqa: BLE001
        rows.append({
            "check": "knowledge",
            "ok": False,
            "detail": f"{type(error).__name__}: {error}",
            "why": "the freshness-stamped world knowledge could not be read",
        })

    try:
        from app import jobspec

        recipes = sorted(jobspec.available_recipes())
        rows.append(
            {
                "check": "recipes",
                "ok": bool(recipes),
                # NO LONGER A KNOWN-OPEN QUESTION. V.3 A1b was decided on
                # 2026-08-28: a recipe's DEFINITION is package data and its
                # virtualenv is not, so an installed copy has all three recipes
                # and this row is green on a correct install. A red one now
                # means a real defect - a build that did not bundle them - which
                # is exactly what the row was always supposed to be able to say.
                "detail": ", ".join(recipes) or f"none under {jobspec.RECIPES_ROOT}",
                "why": (
                    "the training backends. A recipe's recipe.toml, entrypoint "
                    "and lockfile ship with the package; its multi-gigabyte "
                    ".venv never does and is materialised into the data root on "
                    "first use - docs/THE_PLAN.md V.3 A1b."
                ),
            }
        )
    except Exception as error:  # noqa: BLE001
        rows.append(
            {
                "check": "recipes",
                "ok": False,
                "detail": f"{type(error).__name__}: {error}",
                "why": "no recipe could be resolved",
            }
        )

    try:
        from app.tools import REGISTRY

        rows.append(
            {
                "check": "tools",
                "ok": bool(REGISTRY.names()),
                "detail": f"{len(REGISTRY.names())} registered",
                "why": "the instruments. An engine with none can measure nothing.",
            }
        )
    except Exception as error:  # noqa: BLE001
        rows.append(
            {
                "check": "tools",
                "ok": False,
                "detail": f"{type(error).__name__}: {error}",
                "why": "the tool registry did not import",
            }
        )

    # THE ROW A STRANGER ACTUALLY NEEDS, and its absence was measured rather
    # than imagined.
    #
    # 2026-09-10, Windows Sandbox, nothing on the machine but the installer:
    # the install succeeded, the engine published itself, `/health` answered
    # HTTP 200 with every check green - and `/api/providers` returned an EMPTY
    # LIST. The person had a working product that could not diagnose anything,
    # and nothing anywhere said so. `docs/PHASES.md` Phase 5 is done when
    # somebody reaches "a diagnosed problem without asking a question", and
    # every row above this one would have told them they were ready.
    #
    # NO NETWORK PROBE. This command's contract is that it writes nothing,
    # starts nothing and asks nothing, and reaching out to look for a running
    # Ollama would be a fourth thing it does not do. The connections this
    # installation has are a local fact and that is what is reported.
    try:
        from app import db
        from app.providers import store

        # A DATABASE THAT DOES NOT EXIST YET IS NOT A BROKEN ONE. The engine
        # creates it on first start; `mlh doctor` is the command somebody runs
        # BEFORE that, so on a genuinely fresh install there is nothing to open.
        # Reported as "no connections", which is true, rather than as an
        # OperationalError, which reads as a fault in the installation.
        if not db.DB_PATH.exists():
            connections: list = []
        else:
            store.ensure_table()
            connections = store.list_all()
        names = ", ".join(
            f"{c['name']} ({c['model']})" for c in connections[:4]
        ) or "none"
        rows.append(
            {
                "check": "model",
                "ok": bool(connections),
                # KNOWN-OPEN RATHER THAN BROKEN, and this file reserved the flag
                # for exactly this: "three things - fine, KNOWN-OPEN, or broken -
                # and only the third exits [1] ... Nothing sets `open` today; the
                # next honest unknown will." A fresh install with no model is not
                # a fault in the installation; it is the one step left, and
                # exiting 1 on it would tell every new person their install is
                # broken when it is complete and waiting.
                "open": not connections,
                "detail": (
                    f"{len(connections)} connected: {names}"
                    if connections
                    else "none connected - this product cannot diagnose anything yet"
                ),
                "why": (
                    "every diagnosis this product makes reads your data through "
                    "a model you lend it, and it ships none. Connect a local "
                    "Ollama or an OpenAI-compatible endpoint before asking it "
                    "anything: without one the engine runs, the tools load, and "
                    "every question ends in the same place."
                ),
            }
        )
    except Exception as error:  # noqa: BLE001 - a broken store is a finding
        rows.append(
            {
                "check": "model",
                "ok": False,
                "detail": f"{type(error).__name__}: {error}",
                "why": "the connection store did not open",
            }
        )

    return rows


def doctor(as_json: bool = False) -> int:
    """Report what this installation found. Exit 1 only if something is BROKEN.

    ## The distinction this exits on, found by doing the install

    Measured on a real wheel, installed non-editable into a throwaway
    environment and run from a directory that is not the checkout - which is the
    only arrangement where any of this is visible:

        ok  data_root      %LOCALAPPDATA%/ml-harness
        ok  ledgers        all three, by their docs/ names
        ok  model_configs  27
        ok  recipes        demo-metrics, hf-peft-dpo, hf-peft-lora
        ok  tools          62
        exit=0

    **The `recipes` row used to be red on every correct install**, and the
    machinery below for "a question this product has not answered yet" was
    built for it. V.3 A1b answered it on 2026-08-28 - the definition is package
    data, the virtualenv is not - so all five rows are green on a healthy
    install and a red `recipes` row now means a build that failed to bundle
    them.

    The known-open machinery is KEPT rather than deleted. It is the difference
    between "this installation is broken" and "this product has not decided
    that yet", and a doctor that can only say the first will one day say it
    about the second. Nothing sets `open` today; the next honest unknown will.

    An exit code that is 1 for every healthy installation is an exit code
    nothing can be built on: CI cannot gate on it, a person cannot script it,
    and the one time it means something nobody is watching. So a check is one of
    three things - fine, KNOWN-OPEN, or broken - and only the third exits
    non-zero. The open ones are still printed, because a question this product
    has not answered is worth reading; it is just not a fault in the install in
    front of you.
    """
    rows = _findings()
    broken = [row for row in rows if not row["ok"] and not row.get("open")]
    if as_json:
        print(
            json.dumps(
                {
                    "checks": rows,
                    "broken": [row["check"] for row in broken],
                    "open_questions": [
                        row["check"] for row in rows if row.get("open")
                    ],
                },
                indent=2,
            )
        )
    else:
        for row in rows:
            mark = "ok " if row["ok"] else ("?  " if row.get("open") else "RED")
            print(f"{mark} {row['check']:<14} {row['detail']}")
            if not row["ok"]:
                print(f"    {row['why']}")
        if broken:
            print(
                "\n"
                + f"{len(broken)} check(s) are BROKEN: "
                + ", ".join(row["check"] for row in broken)
            )
        elif any(row.get("open") for row in rows):
            print(
                "\nNothing is broken. The `?` rows are questions this product "
                "has not answered yet, not faults in this installation."
            )
    return 1 if broken else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mlh",
        description=(
            "The ML harness. `doctor` reports what this installation shipped "
            "with and what it can read; it writes nothing and starts nothing."
        ),
    )
    sub = parser.add_subparsers(dest="command")
    check = sub.add_parser("doctor", help="report what this installation can read")
    check.add_argument("--json", action="store_true", help="machine-readable output")

    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "doctor":
        return doctor(as_json=bool(args.json))
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
