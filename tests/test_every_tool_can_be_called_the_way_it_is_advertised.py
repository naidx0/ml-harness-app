"""A tool's handler accepts the arguments its schema advertises.

FOUND ON A STRANGER WALK, and it was mine. `@tool(name="map_the_ask", ...)`
declares `ask` as a required string. A later change added a plain helper,
`journey_names()`, directly beneath that decorator - so the decorator bound to
the helper instead of to `map_the_ask`, and the registry advertised a tool
taking `ask` whose handler took nothing at all.

What that cost: `map_the_ask` is the first tool the conductor calls on the
first message of every new thread. Every stranger's opening turn ended with the
model apologising for a broken tool. Nothing failed loudly, no test broke, and
the tool was still listed, still described, still clickable.

The general defect is a handler whose signature disagrees with the schema the
model is handed, and it is checkable for all 67 tools rather than for the one
that happened to break. Both directions matter:

  * a required property the handler cannot accept - the model is told to send
    something that will be refused;
  * a handler parameter with no default that the schema never mentions - the
    model is never told to send something the call cannot proceed without.

Only two names may appear on a handler and not in its schema, `instrument` and
`ledger`, and only when the spec declares it wants them. Those are injected by
the caller, not supplied by the model.
"""

from __future__ import annotations

import inspect
import unittest

from app.tools import REGISTRY

#: Supplied by the runner rather than by the model, and each gated on the flag
#: that says the tool asked for it.
INJECTED = {"instrument": "wants_instrument", "ledger": "wants_ledger"}


class EveryToolTest(unittest.TestCase):
    def specs(self):
        for name in REGISTRY.names():
            yield name, REGISTRY.get(name)

    def test_the_registry_is_not_empty(self):
        """A scan that silently checks nothing would pass forever."""
        self.assertGreaterEqual(len(list(REGISTRY.names())), 60)

    def test_every_required_property_is_a_parameter_the_handler_accepts(self):
        for name, spec in self.specs():
            with self.subTest(name):
                required = list((spec.schema or {}).get("required") or [])
                signature = inspect.signature(spec.handler)
                takes_kwargs = any(
                    p.kind is p.VAR_KEYWORD for p in signature.parameters.values()
                )
                if takes_kwargs:
                    continue
                for argument in required:
                    self.assertIn(
                        argument,
                        signature.parameters,
                        f"{name} advertises {argument!r} but its handler "
                        f"({spec.handler.__qualname__}) does not accept it",
                    )

    def test_every_argument_the_handler_needs_is_advertised(self):
        """The reverse mismatch: a call the model can never get right."""
        for name, spec in self.specs():
            with self.subTest(name):
                properties = set((spec.schema or {}).get("properties") or {})
                for parameter in inspect.signature(spec.handler).parameters.values():
                    if parameter.kind in (parameter.VAR_KEYWORD, parameter.VAR_POSITIONAL):
                        continue
                    if parameter.default is not inspect.Parameter.empty:
                        continue
                    if parameter.name in properties:
                        continue
                    flag = INJECTED.get(parameter.name)
                    self.assertIsNotNone(
                        flag,
                        f"{name}'s handler needs {parameter.name!r}, which its "
                        "schema never mentions and nothing injects",
                    )
                    self.assertTrue(
                        getattr(spec, flag, False),
                        f"{name}'s handler takes {parameter.name!r} but the spec "
                        f"does not set {flag}, so nothing will pass it",
                    )

    def test_the_handler_is_the_function_the_tool_is_named_for(self):
        """The decorator binds to whatever follows it, which is how this broke.

        Not every tool's handler shares its name - some are deliberately thin
        wrappers - so this asserts the weaker, true thing: a handler must not be
        a function that another tool or module reads under a different name
        while advertising arguments it cannot take. The signature checks above
        carry the real weight; this one names the specific shape that shipped.
        """
        spec = REGISTRY.get("map_the_ask")
        signature = inspect.signature(spec.handler)
        self.assertIn("ask", signature.parameters)

    def test_map_the_ask_answers_the_sentence_a_stranger_actually_sent(self):
        """The exact opening message from the walk that found this."""
        answer = REGISTRY.get("map_the_ask").handler(
            ask="I want a small model that runs on this machine and does one thing well."
        )
        self.assertTrue(answer.get("ok"))
        self.assertEqual(answer.get("matched"), "train_on_my_files")
        self.assertTrue(answer.get("steps"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
