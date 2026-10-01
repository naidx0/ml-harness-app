"""Every training config key a person can set has a door on the tool.

Found by the critic pass of 2026-09-01: `prompt_field` and `completion_field`
were added to `training.CONFIG_KEYS` and the commit said the recipe could now
be told its columns. It could not. `CONFIG_KEYS` is a FILTER over the config
`start_training` builds from its own parameters; a filter cannot add a key
that no parameter ever put there, so the recipe's new refusal ("name both
columns or neither") was unreachable from either door - the tool schema had
no such property and the function had no such argument.

The wall: for every config key that is not engine-internal, the tool's schema
declares a property of that name AND `start_training` accepts a parameter of
that name. A key with only one of the two is a door painted on a wall.
"""

import inspect
import unittest

from app.tools import REGISTRY, training


#: Keys the ENGINE fills, never a person: not doors, and not asked to be.
ENGINE_OWNED = {"run_id", "min_free_vram_gb"}

#: Keys reachable ONLY through `run_in_sandbox`'s free-form config. This wall
#: found them on its first run (2026-09-01): they pre-date it, and
#: `start_training` neither offers them in its schema nor takes them as
#: arguments. Listed here so the gap is a recorded fact rather than a
#: surprise; the assertion below keeps it honest in both directions - a key
#: that gains a schema property must gain the parameter in the same change.
SANDBOX_ONLY = {"grad_accum", "lora_alpha", "lora_dropout", "logging_steps", "seed", "optim"}


class AConfigKeyHasADoorTest(unittest.TestCase):
    def test_every_settable_config_key_is_a_schema_property_and_a_parameter(self):
        spec = REGISTRY.get("start_training")
        properties = set(spec.schema["properties"])
        parameters = set(inspect.signature(training.start_training).parameters)
        for key in training.CONFIG_KEYS:
            if key in ENGINE_OWNED:
                continue
            if key in SANDBOX_ONLY:
                with self.subTest(key=key):
                    self.assertEqual(
                        key in properties, key in parameters,
                        f"{key} is offered on one face of start_training and "
                        "not the other - a door painted on a wall",
                    )
                continue
            with self.subTest(key=key):
                self.assertIn(
                    key, properties,
                    f"{key} is in CONFIG_KEYS but no model can send it: it is "
                    "not a property of start_training's schema",
                )
                self.assertIn(
                    key, parameters,
                    f"{key} is in CONFIG_KEYS but start_training takes no such "
                    "argument, so nothing ever puts it in the config",
                )

    def test_the_named_column_pair_reaches_the_config(self):
        """The specific pair the walk needed, pinned by name."""
        for key in ("prompt_field", "completion_field"):
            self.assertIn(key, training.CONFIG_KEYS)
            self.assertIn(key, REGISTRY.get("start_training").schema["properties"])
            self.assertIn(
                key, inspect.signature(training.start_training).parameters
            )


if __name__ == "__main__":
    unittest.main()
