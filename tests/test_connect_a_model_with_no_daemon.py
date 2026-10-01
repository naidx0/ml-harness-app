"""What a stranger sees when "Connect a model" probes a daemon that is not there.

## The gap, and who found it

ML BUILD drove the stranger walk to its own `=== done ===` on a bare Windows
Sandbox for the first time (`4d2416d`) and named what it had NOT covered: the
walk drove `POST /api/providers` - create, without a probe - but never
`activate` and `probe`, **which is what the one-click "Connect a model" button
actually calls**. So nobody had seen the product's answer at the one moment a
stranger is guaranteed to meet it: a fresh machine, no daemon, first click.

## What the answer was

    could not reach http://127.0.0.1:11434: <urlopen error [WinError 10061] ...>

A Python exception, handed to somebody who has never heard of urllib, at the
exact moment they are trying to start. That is the complaint this lane exists
for - *"it throws tools in your face"* - at the first step of the product.

## What it is now, and why each sentence is in it

Three sentences, each one a thing the person can either do or stop worrying
about:

1. **which of the two states this is** - `list_local_models` already shipped
   that distinction (*"this is not 'you have no models'"*) and the connect
   button did not have it;
2. **where the thing comes from** - named, and deliberately not automated:
   measured the same day, Ollama's Windows installer answers no unattended
   flag (`/S` and `/VERYSILENT` both still alive after 240 seconds) and a human
   clicks through it in seconds. Telling somebody to click is honest; pretending
   to do it for them and hanging is not;
3. **that nobody has to come back and press anything.** This one matters most.
   A person who is not told the harness re-probes will sit and click.

## What is asserted, and what deliberately is not

The route is asserted **verbatim**, because the whole point is the words. The
exception is asserted only to be PRESENT - a maintainer reading a log still
needs `WinError 10061`, it just stops being the whole answer.

Nothing here starts a daemon, and the port is asserted closed first: a test
that passes because something happened to be listening on 11434 would be
measuring the developer's laptop.
"""

from __future__ import annotations

import socket
import unittest

import support

from app.providers import ollama as ollama_adapter


def a_port_nothing_is_on() -> int:
    """A port that is closed right now, obtained by asking the OS for one.

    THE FIRST VERSION OF THIS SKIPPED WHEN 11434 WAS BUSY, and on the machine
    that wrote it 11434 is ALWAYS busy - the daemon is installed here. So the
    case that matters ran nowhere and the file reported OK with three skips,
    which is the "partial result wearing a pass" this repository refuses
    everywhere else.

    A stranger's machine has no daemon on 11434; this machine has no daemon on
    a port the OS just told us is free. The thing under test is "the probe
    could not reach a daemon", and that is the same on both.
    `test_the_default_local_url_is_the_one_a_stranger_meets` pins the 11434
    half separately, so the pairing is asserted without depending on whether
    this developer happens to be running Ollama.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        port = int(taken.getsockname()[1])
    return port


class TheRouteIsTheAnswerTest(unittest.TestCase):
    """The words, exactly, because the words are the change."""

    def test_it_names_which_of_the_two_states_this_is(self):
        said = ollama_adapter.THE_DAEMON_IS_NOT_RUNNING
        self.assertIn("The local model daemon is not running", said)
        self.assertIn("not 'you have no models'", said)

    def test_it_says_nothing_is_wrong_with_their_setup(self):
        """A stranger's first reading of a failure is that they broke it."""
        self.assertIn(
            "nothing is wrong with your setup", ollama_adapter.THE_DAEMON_IS_NOT_RUNNING
        )

    def test_it_names_where_the_thing_comes_from(self):
        self.assertIn("https://ollama.com/download", ollama_adapter.THE_DAEMON_IS_NOT_RUNNING)

    def test_it_says_the_harness_re_probes(self):
        """THE SENTENCE THAT SAVES THE MOST TIME. Without it a person sits and
        clicks the button again."""
        self.assertIn("re-probes when it appears", ollama_adapter.THE_DAEMON_IS_NOT_RUNNING)

    def test_the_exception_is_kept_but_is_not_the_answer(self):
        said = ollama_adapter.cannot_reach("http://127.0.0.1:11434", "WinError 10061")
        self.assertTrue(said.startswith("The local model daemon is not running"))
        self.assertIn("WinError 10061", said)
        self.assertIn("http://127.0.0.1:11434", said)

    def test_the_two_places_that_say_this_say_the_same_thing(self):
        """`list_local_models` and the connect button are the same moment in a
        person's day reached two ways. Two hand-written versions drift until
        the product contradicts itself about whether anything is wrong.

        THE FIRST VERSION OF THIS COMPARED MODULE ALIASES - `models.ollama_adapter`
        against the adapter - which are the same object however the `help`
        field is written. Mutation changed the field to a hand-written sentence
        and the test stayed green: it was asserting that an import happened,
        not that the answer used it. It calls the tool now.
        """
        from app.tools import models

        was = models.OLLAMA_BASE
        models.OLLAMA_BASE = f"http://127.0.0.1:{a_port_nothing_is_on()}"
        try:
            said = models.list_local_models()
        finally:
            models.OLLAMA_BASE = was

        self.assertEqual("no_local_daemon", said.get("error"))
        self.assertEqual(ollama_adapter.THE_DAEMON_IS_NOT_RUNNING, said.get("help"))


class TheButtonsOwnPathWithNoDaemonTest(unittest.TestCase):
    """`activate` then `probe` - what the button calls, not what a test finds
    convenient to call."""

    def setUp(self):
        support.sandbox(self)
        from app import conductor
        from app.providers import store as provider_store

        self.conductor = conductor
        self.store = provider_store
        self.closed = a_port_nothing_is_on()
        self.provider = provider_store.create(
            name="Local model",
            adapter="ollama",
            base_url=f"http://127.0.0.1:{self.closed}",
            model="granite4-hermes",
        )

    def test_the_default_local_url_is_the_one_a_stranger_meets(self):
        """The 11434 half, pinned here rather than by refusing to run when the
        developer has a daemon installed."""
        from app.tools import models

        self.assertEqual("http://127.0.0.1:11434", models.OLLAMA_BASE)

    def test_activate_succeeds_because_saving_a_row_is_not_reaching_a_server(self):
        """THE CONTROL, and it is why the gap existed. Activate touches only
        the database, so a walk that stopped there saw nothing wrong."""
        row = self.store.set_active(int(self.provider["id"]))
        self.assertIsNotNone(row)

    def test_the_probe_answers_with_the_route(self):
        """THE CASE. No daemon, the button's second call, and the answer is
        the three sentences rather than a traceback."""
        self.store.set_active(int(self.provider["id"]))
        row = self.conductor.probe(int(self.provider["id"]))
        self.assertIsNotNone(row)
        #: `capability_detail` is the column the probe writes to - found by
        #: reading `store.record_capabilities` rather than by guessing at the
        #: name, which is how the first version of this asserted against an
        #: empty string and passed nothing.
        detail = str(row.get("capability_detail") or "")
        self.assertIn("The local model daemon is not running", detail)
        self.assertIn("https://ollama.com/download", detail)
        self.assertIn("re-probes when it appears", detail)

    def test_the_probe_does_not_claim_a_capability_it_could_not_measure(self):
        """A cheerful `True` here is how a product reports numbers it never
        took. Nothing answered, so tool-calling is not known."""
        self.store.set_active(int(self.provider["id"]))
        row = self.conductor.probe(int(self.provider["id"]))
        #: `unknown`, not `no`: a probe that could not reach anything has not
        #: learned that the model cannot call tools, and `no` would be a
        #: measurement nobody took.
        self.assertEqual("unknown", row.get("tool_calling"))


if __name__ == "__main__":
    unittest.main()
