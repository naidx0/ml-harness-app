from typing import Any
from app import db

def explain_loss(run_id: int) -> dict[str, Any]:
    metrics = db.metrics_for(run_id, "loss")
    points = len(metrics)

    if points == 0:
        return {"observed": "no loss recorded", "heuristic": "", "points": 0}

    # EARLIEST and LATEST, not smallest and largest. The first version used
    # min() and max(), so `last > first` was true for almost any run and the
    # panel reported "increasing, may indicate too high a learning rate" at a
    # loss curve that was falling. metrics_for orders by step, so the ends of
    # the list are the ends of the run.
    first = round(metrics[0]["value"], 3)
    last = round(metrics[-1]["value"], 3)

    observed = (f"loss started at {first} and ended at {last} "
                f"over {points} recorded point(s)")

    if last < first:
        heuristic = "Heuristic: Loss is decreasing"
    elif last > first:
        heuristic = "Heuristic: Loss is increasing and may indicate too high a learning rate"
    else:
        heuristic = "Heuristic: Loss is flat"

    return {"observed": observed, "heuristic": heuristic, "points": points}
