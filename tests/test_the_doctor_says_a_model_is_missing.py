"""A fresh install passes every check and cannot do anything, unless it says so.

## Measured, not imagined

2026-09-10, Windows Sandbox, nothing on the machine but the installer
(`scripts/the_stranger_installs_the_harness.py`). The install succeeded, the
engine published `engine.json`, and `GET /health` answered **HTTP 200 with every
check green**. Then `/api/providers` returned an **empty list**.

So a stranger had a working product that could not diagnose anything, and
nothing anywhere told them. `docs/PHASES.md` Phase 5 is done when somebody
reaches *"a diagnosed problem without asking a question"* - and every row of
`mlh doctor` would have told them they were ready.

## KNOWN-OPEN, not broken

`doctor`'s own docstring reserved a third state: *"three things - fine,
KNOWN-OPEN, or broken - and only the third exits [1] ... Nothing sets `open`
today; the next honest unknown will."* This is that unknown. A fresh install
with no model is not a fault; it is the one step left, and exiting 1 would tell
every new person their install is broken when it is complete and waiting.

## Why these tests bind the database rather than the data root

The first draft set `MLH_DATA_ROOT` and called `_findings()`. `db.DB_PATH` is
read ONCE at import - the module comment says so - so the environment variable
changed nothing and the call went at the real `ml_harness.db`. The suite's fence
caught it, which is the fence working: *"a test tried to open ... which holds
the user's real data."* So each case below binds `db.DB_PATH` explicitly, inside
the sandbox root.
"""

import unittest
from pathlib import Path

import support

from app import cli, db
from app.providers import store


class TheDoctorNamesTheMissingModelTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)

    def _rows(self) -> dict:
        return {row["check"]: row for row in cli._findings()}

    def _with_no_database(self) -> dict:
        """The state a stranger's machine is actually in when they run this.

        The engine creates the database on first start; `mlh doctor` is the
        command somebody runs BEFORE that, so there is nothing to open.
        """
        db.DB_PATH = self.root / "not-started-yet" / "ml_harness.db"
        self.assertFalse(db.DB_PATH.exists())
        return self._rows()

    def test_a_fresh_install_reports_no_model(self):
        rows = self._with_no_database()
        self.assertIn("model", rows, "doctor no longer reports the one thing a "
                                     "fresh install is missing")
        self.assertFalse(rows["model"]["ok"])

    def test_a_missing_database_is_not_reported_as_a_broken_store(self):
        """An OperationalError here reads as a fault in the installation when
        the truth is simply that nothing has run yet."""
        rows = self._with_no_database()
        self.assertNotIn("Error", rows["model"]["detail"],
                         "a database that does not exist yet is being reported "
                         "as a broken one")
        self.assertIn("none connected", rows["model"]["detail"])

    def test_it_is_known_open_rather_than_broken(self):
        """THE WHOLE POINT. A correct, complete install that is merely waiting
        for a connection must not exit 1."""
        rows = self._with_no_database()
        self.assertTrue(rows["model"].get("open"),
                        "a fresh install would exit 1 and read as broken")

    def test_a_started_engine_with_no_connections_says_the_same_thing(self):
        """The database exists after the first start and is still empty, which
        is the state somebody is in for as long as it takes them to connect
        something. Same row, same reason - the table opening is not the thing
        being asked about."""
        store.ensure_table()
        rows = self._rows()
        self.assertFalse(rows["model"]["ok"])
        self.assertTrue(rows["model"].get("open"))
        self.assertIn("none connected", rows["model"]["detail"])

    def test_a_connected_model_turns_the_row_green_and_names_it(self):
        """The row has to be able to go green, or it is a permanent scold rather
        than a check - and it names what it found, because 'ok' with no name
        cannot tell a person whether the thing they connected is the thing
        doctor sees."""
        store.create(
            name="local ollama",
            base_url="http://127.0.0.1:11434/v1",
            model="qwen2.5-coder:7b",
            adapter="ollama",
        )
        rows = self._rows()
        self.assertTrue(rows["model"]["ok"])
        self.assertFalse(rows["model"].get("open"))
        self.assertIn("local ollama", rows["model"]["detail"])
        self.assertIn("qwen2.5-coder:7b", rows["model"]["detail"])

    def test_the_row_says_what_to_do_about_it(self):
        """A row that says a thing is missing and not what to do is a dead end,
        and this one is the last thing between a stranger and the product."""
        why = self._with_no_database()["model"]["why"].lower()
        self.assertIn("ollama", why)
        self.assertIn("openai-compatible", why)

    def test_a_missing_model_does_not_make_doctor_exit_one(self):
        """The exit code is what a script and a person both read, and this is
        the case that would have flipped it for every new install."""
        self._with_no_database()
        self.assertEqual(0, cli.doctor())

    def test_the_readme_tells_a_stranger_a_model_is_needed(self):
        """The same shape as `--stop`: a remedy nobody is told about is not a
        remedy. `test_a_started_product_can_be_stopped.py` makes this exact
        assertion for stopping the engine, and the reason is the same one - the
        product could do the thing and the person could not find out how.

        The README's `Run it locally` block went `pip install` -> `start.ps1` ->
        the gate, with no step between starting it and asking it something, and
        the thing in that gap is the only reason the product can answer at all.
        """
        readme = (support.REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("mlh doctor", readme)
        self.assertIn("Connect a model", readme)

    def test_doctor_does_not_probe_the_network(self):
        """`doctor` writes nothing, starts nothing and asks nothing. Reaching
        out to look for a running Ollama would be a fourth thing it does not do,
        and the connections this installation HAS are a local fact."""
        source = Path(cli.__file__).read_text(encoding="utf-8")
        block = source[source.index('"check": "model"'):]
        for reaching in ("urlopen", "requests.", "httpx.", "socket.", "subprocess"):
            self.assertNotIn(reaching, block)


if __name__ == "__main__":
    unittest.main()
