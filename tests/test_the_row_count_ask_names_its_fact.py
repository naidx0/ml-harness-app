"""The row-count objection names the fact it is about.

The owner's run of 2026-09-23 (thread 93): the verdict said *"I could not read
how many rows your dataset has"* while the sheet showed `eval_size_n = 40
[MEASURED]`. The node is about `tabular_rows`, the training table's own row
count, and never said so; the model read the two as a contradiction and spent
a 105-second round arguing with the engine instead of counting. A sentence a
model will act on names the fact and says which number it is NOT.

The subject is the spec's own node, read through `load_spec`, so an edit to
the yaml is what this test measures.
"""

from __future__ import annotations

import unittest

import support  # noqa: F401  - puts the repo root on the path

from app import diagnosis


class TheRowCountAskNamesItsFactTest(unittest.TestCase):
    def test_the_tabular_rows_ask_names_tabular_rows_and_not_the_eval_set(self):
        spec = diagnosis.load_spec()
        node = spec.node_index["S8_TABULAR_ROWS_UNKNOWN"]
        say = str(node.get("say") or "")
        self.assertIn("tabular_rows", say, "the objection must name the fact it wants")
        self.assertIn("eval_size_n", say, "and say it is not the eval set's count")
        self.assertNotIn("your dataset has", say, "the old wording read as the whole dataset")


if __name__ == "__main__":
    unittest.main()
