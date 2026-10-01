import unittest

from app.feasibility import recommend


class RecommendReachabilityTest(unittest.TestCase):
    """The fine-tune branch must be reachable from a realistic goal sentence.

    Two of these tests used to use "Fine-tune a small image classifier on my RTX
    2060 Super" as their realistic goal, and asserted that it produced QLoRA on
    Qwen3 - a language model, for an image classifier. That was the defect, not
    the spec: `recommend` never received the data kind and so answered every
    goal out of a two-entry language-model catalogue. The reachability intent is
    preserved by keeping a long, realistic, capitalised, hyphenated goal string;
    the data kind in it is now text, and the image case is asserted separately
    below.
    """

    def test_realistic_fine_tune_goal_uses_qlora_below_threshold(self):
        result = recommend("Fine-tune a small text classifier on my RTX 2060 Super", 8.0)

        self.assertEqual(result["method"], "QLoRA")

    def test_case_insensitive_fine_tune_goal_uses_qlora(self):
        result = recommend("Fine-tune", 8.0)

        self.assertEqual(result["method"], "QLoRA")

    def test_surrounding_whitespace_is_ignored(self):
        result = recommend(" fine-tune ", 8.0)

        self.assertEqual(result["method"], "QLoRA")

    def test_finetune_variant_uses_qlora(self):
        result = recommend("finetune a model", 8.0)

        self.assertEqual(result["method"], "QLoRA")

    def test_fine_tune_variant_uses_qlora(self):
        result = recommend("fine tune a model", 8.0)

        self.assertEqual(result["method"], "QLoRA")

    def test_realistic_fine_tune_goal_uses_lora_above_threshold(self):
        result = recommend("Fine-tune a small text classifier on my RTX 2060 Super", 16.0)

        self.assertEqual(result["method"], "LoRA")

    def test_unrelated_goal_remains_inference_only(self):
        result = recommend("Serve a chatbot for inference", 8.0)

        self.assertEqual(result["method"], "inference-only")

    def test_an_image_goal_is_not_answered_with_a_language_model(self):
        """The defect this file's own goal string used to demonstrate."""
        result = recommend(
            "Fine-tune a small image classifier on my RTX 2060 Super",
            8.0,
            data_kind="Image",
        )

        self.assertEqual(result["data_kind"], "image")
        self.assertNotIn("Qwen", result["model"])
        self.assertIn("vit", result["model"].lower())

    def test_an_image_goal_is_caught_even_when_the_data_kind_is_not_declared(self):
        result = recommend("Fine-tune a small image classifier", 8.0)

        self.assertEqual(result["data_kind"], "image")
        self.assertEqual(result["data_kind_provenance"], "inferred")
        self.assertNotIn("Qwen", result["model"])

    def test_a_tabular_goal_is_not_answered_with_a_neural_network(self):
        result = recommend("Predict churn from my customer table", 8.0, data_kind="Tabular")

        self.assertEqual(result["data_kind"], "tabular")
        self.assertEqual(result["method"], "gradient boosting")
        self.assertNotIn("Qwen", result["model"])

    def test_a_declared_data_kind_beats_the_goal_text(self):
        # "image" appears in the goal, but the user said the data is text.
        result = recommend("Fine-tune on my image captions", 8.0, data_kind="Text")

        self.assertEqual(result["data_kind"], "text")
        self.assertEqual(result["data_kind_provenance"], "declared")

    def test_the_vram_figure_is_the_one_it_was_given_not_a_constant(self):
        small = recommend("fine-tune", 8.0)
        large = recommend("fine-tune", 24.0)

        self.assertNotEqual(small["model"], large["model"])

    def test_an_unknown_vram_figure_picks_the_conservative_model(self):
        unknown = recommend("fine-tune", None)

        self.assertEqual(unknown["model"], "Qwen3-4B")
        self.assertEqual(unknown["method"], "QLoRA")


if __name__ == "__main__":
    unittest.main()
