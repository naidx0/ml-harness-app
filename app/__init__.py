"""ML Harness application package.

The import boundary is checked here because this is the one place that runs
without being remembered. See `app/import_boundary.py` for what it decides and
`docs/judge_runs/2026-09-07-the-import-guard-prereg.md` for what was registered
before it existed. On this machine today it is silent on all 34 entry points;
it speaks when a process has imported another checkout's package.
"""

from app import import_boundary as _import_boundary

# A CROSSED IMPORT RAISES. A DEFECT IN THE GUARD DOES NOT.
#
# These need different words, which is this repository's oldest law: "nothing
# failed is not nothing was checked". The RuntimeError below is the guard
# convicting, and it propagates - a process holding the wrong checkout's
# database must not continue. Anything else reaching here is a defect in the
# guard itself, and taking down every process in both checkouts over one is a
# worse outcome than the hazard: so it is written to stderr in a sentence that
# says the check DID NOT RUN, rather than being swallowed into a silence that
# reads like a pass.
try:
    _import_boundary.refuse_a_foreign_app()
except RuntimeError:
    raise
except BaseException as _defect:  # noqa: BLE001 - deliberate, and it re-raises nothing
    import sys as _sys

    print(
        f"ML HARNESS: the import-boundary guard DID NOT RUN ({_defect!r}). This "
        f"process has NOT been checked against another checkout's `app`; it is "
        f"not a clean bill. See app/import_boundary.py.",
        file=_sys.stderr,
    )
