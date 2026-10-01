"""Every read helper in app/db.py must survive an empty database.

Generated from the module itself rather than written one function at a time,
because the one-at-a-time approach kept missing cases.

Four defects this session were the same shape:

  list_jobs          no ensure_jobs_table, only found when a page listed nothing
  next_queued_job    same, found by the test written for list_jobs
  job_log            Path(None) on a queued row, found by running the server
  explain_loss       min/max instead of first/last, found by reading output

Each was invisible because every acceptance test creates its own fixtures
before reading, so the empty case is never exercised. A generated test always
sets up its own data - that is what makes it self-contained, and that is
exactly what hides this class of bug.

So this test discovers the helpers instead of naming them. Add a new read
helper to db.py and it is covered here from the moment it exists, without
anyone remembering to add a case.
"""
import inspect
import tempfile
import unittest
from pathlib import Path

from app import db

# Helpers that legitimately need an argument to mean anything. The value is a
# lookup that should simply miss on an empty database.
PROBE_ARGS = {
    "get_intake": ("nobody",),
    "get_job": (999999,),
    "get_project": (999999,),
    "metrics_for": (999999,),
    "complete_run": (999999,),
}

# Not reads: these create or mutate, so "empty database" is not a meaningful
# precondition for them.
#
# `default_project` is in here and it is the interesting one. It takes no
# arguments and looks exactly like a reader, but it CREATES a project when
# there is none - that is its whole job, and it is what lets every caller be
# project-scoped without a picker. Discovery would call it and then `list_
# projects` would return the row it made, failing the "invented rows from
# nothing" assertion below for a reason that has nothing to do with the defect
# class this file guards. Naming it here beats depending on the order the two
# functions happen to be defined in.
SKIP = {"connect", "session", "init_db", "create_run", "add_metric",
        "create_hardware_profile", "create_intake", "create_job",
        "create_model", "create_dataset", "finish_job",
        "ensure_intake_table", "ensure_jobs_table", "ensure_models_table",
        "ensure_datasets_table", "ensure_projects", "default_project",
        "create_project", "rename_project", "archive_project",
        # `set_project_root` takes a project id and a path and returns the row
        # it wrote. Discovery would call it with a probe id, get `None` for a
        # project that does not exist, and pass - which is the right answer for
        # the wrong reason. Its real empty-state behaviour is asserted in
        # `tests/test_a_project_can_be_pointed_at_a_directory.py`.
        "set_project_root"}


def read_helpers():
    """Every public zero-or-probeable-argument reader in db.py."""
    found = []
    for name, fn in vars(db).items():
        if name.startswith("_") or name in SKIP or not inspect.isfunction(fn):
            continue
        if fn.__module__ != db.__name__:
            continue
        params = [p for p in inspect.signature(fn).parameters.values()
                  if p.default is p.empty]
        if not params or name in PROBE_ARGS:
            found.append((name, fn, PROBE_ARGS.get(name, ())))
    return found


class EmptyStateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "empty.db"
        db.init_db()

    def tearDown(self):
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def test_every_read_helper_survives_an_empty_database(self):
        helpers = read_helpers()
        self.assertGreater(len(helpers), 4,
                           "discovery found almost nothing, the filter is wrong")
        for name, fn, args in helpers:
            with self.subTest(helper=name):
                try:
                    result = fn(*args)
                except Exception as exc:            # noqa: BLE001
                    self.fail(f"db.{name}{args} raised {type(exc).__name__}: "
                              f"{exc} on an empty database")
                self.assertIn(type(result), (list, dict, type(None)),
                              f"db.{name} returned {type(result).__name__}")
                if isinstance(result, list):
                    self.assertEqual(result, [],
                                     f"db.{name} invented rows from nothing")


if __name__ == "__main__":
    unittest.main()
