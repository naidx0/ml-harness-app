from typing import Any

def render_diagram(rec: dict[str, Any], verdict_info: dict[str, float]) -> str:
    fence = chr(96) * 3
    lines = [
        f"{fence}mermaid",
        "flowchart LR",
        "    data[Data] --> preprocess[Preprocess]",
        f"    preprocess --> train[Train {rec['model']}]",
        "    train --> eval[Evaluate]",
        f"    eval --> serve[Serve {verdict_info['verdict']}]",
        fence,
    ]
    return "\n".join(lines)
