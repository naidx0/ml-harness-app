from typing import Any

def render_plan(answers: dict[str, str], rec: dict[str, Any], verdict_info: dict[str, float]) -> str:
    return (
        f"# Training plan\n"
        f"{rec['model']}\n"
        f"verdict: {verdict_info['verdict']}\n"
        f"\n## Phase 1 - Data\nExit criterion: Collected and preprocessed sufficient data for model training.\n"
        f"\n## Phase 2 - Preprocess\nExit criterion: Completed all preprocessing steps, including normalization and feature engineering.\n"
        f"\n## Phase 3 - Train\nExit criterion: Model achieved desired performance metrics on validation set.\n"
        f"\n## Phase 4 - Evaluate\nExit criterion: Evaluated model using appropriate evaluation metrics and met the specified requirements.\n"
        # .get, not [...]: POST /intake accepts any dict, so an intake with no
        # goal is storable, and a bare subscript here turned that into a 500 on
        # /plan, /plan/download and /ui/plan.
        f"\nGoal: {answers.get('goal', 'unspecified')}\n"
        f"Method: {rec['method']}\nQuantization: {rec['quant']}"
    )
