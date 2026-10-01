"""Refresh the product's freshness-stamped knowledge: models and GPU prices.

The gap this closes was measured before it was built: the ledgers are
hand-edited and carry their currency in comments; the model configs are
live-fetched but only for models somebody already asked about. Nothing in the
product could answer "which model should I start with TODAY" or "what does a
rented GPU cost RIGHT NOW" without somebody's memory doing the work — and a
memory is exactly the kind of source this product refuses everywhere else.

Two files, both written only from live responses, both stamped:

  app/knowledge/model_shortlist.json   the curated ladder, with every FACT
                                       (params, license, gating, last release,
                                       30-day downloads) read from the
                                       huggingface.co API at run time
  app/knowledge/gpu_prices.json        the rentable-GPU market, read from
                                       vast.ai's public offer search — real
                                       asks from a real marketplace, not a
                                       vendor's rate card

## What is curated and what is fetched — the line, precisely

The LIST of repo ids below is editorial: somebody chose a ladder of sensible
starting points per size class and role. Every NUMBER AND CLAIM about them is
fetched. A repo the API cannot confirm is dropped from the output with a note,
never carried on memory. If either source is unreachable, that file is left
untouched: stale knowledge with an honest date beats fresh-looking fiction.

## Why the snapshots are committed

Unlike the uv sidecar (47 MB, regenerated per build), these are a few KB of
provenance-stamped JSON that an installed copy needs OUT OF THE BOX — a first
run with no network still deserves last month's truthful table over an empty
one. `mlh doctor` reports their age; this script is how the age resets.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "knowledge"

#: The ladder. Editorial, reviewed by hand; every fact about each entry is
#: fetched. `role` is what the entry is FOR, which an API cannot say.
SHORTLIST: list[dict[str, str]] = [
    {"repo_id": "HuggingFaceTB/SmolLM2-135M", "size_class": "tiny", "role": "experiments and pipeline proofs on any hardware"},
    {"repo_id": "HuggingFaceTB/SmolLM2-1.7B", "size_class": "small", "role": "the smallest model worth fine-tuning for real output"},
    {"repo_id": "Qwen/Qwen3.5-4B", "size_class": "small", "role": "current best small generalist; LoRA fits 8 GB cards"},
    {"repo_id": "google/gemma-4-E4B-it", "size_class": "mid", "role": "strong 8B-class instruct, permissive license"},
    {"repo_id": "Qwen/Qwen3.5-9B", "size_class": "mid", "role": "current best mid generalist; QLoRA on 12-16 GB"},
    {"repo_id": "deepseek-ai/DeepSeek-R1-Distill-Llama-8B", "size_class": "mid", "role": "reasoning-distilled 8B when chains of thought matter"},
    {"repo_id": "openai/gpt-oss-20b", "size_class": "large", "role": "open 20B MoE; strong quality per active param"},
    {"repo_id": "Qwen/Qwen3.5-35B-A3B", "size_class": "large", "role": "MoE with 3B active - large quality, small step cost"},
    {"repo_id": "openai/gpt-oss-120b", "size_class": "xl", "role": "open frontier-class; rented multi-GPU territory"},
    {"repo_id": "meta-llama/Llama-3.1-8B-Instruct", "size_class": "mid", "role": "the ecosystem default; most adapters and tools target it"},
    {"repo_id": "sentence-transformers/all-MiniLM-L6-v2", "size_class": "tiny", "role": "embeddings for retrieval; the default index model"},
    {"repo_id": "BAAI/bge-reranker-v2-m3", "size_class": "small", "role": "reranking retrieved passages; pairs with the above"},
]

#: GPUs the price table keys on. Editorial filter: cards a person would
#: actually train on, matched against the marketplace's own gpu_name strings.
GPUS_OF_INTEREST = {
    "RTX 3060", "RTX 3090", "RTX 4070", "RTX 4090", "RTX 5090",
    "RTX A5000", "RTX 6000Ada", "L4", "Tesla V100",
    "A100 PCIE", "A100 SXM4", "H100 PCIE", "H100 NVL", "H200",
}


def _get(url: str, timeout: int = 30):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_shortlist() -> dict:
    rows, dropped = [], []
    for entry in SHORTLIST:
        rid = entry["repo_id"]
        try:
            d = _get(f"https://huggingface.co/api/models/{urllib.parse.quote(rid)}")
        except Exception as error:  # noqa: BLE001 - the note IS the handling
            dropped.append({"repo_id": rid, "why": f"{type(error).__name__}: {error}"})
            continue
        safetensors = d.get("safetensors") or {}
        rows.append({
            **entry,
            "parameters_total": safetensors.get("total"),
            "license": (d.get("cardData") or {}).get("license"),
            "gated": d.get("gated"),
            "last_modified": d.get("lastModified"),
            "downloads_30d": d.get("downloads"),
            "url": f"https://huggingface.co/{rid}",
        })
    if len(rows) < len(SHORTLIST) * 2 // 3:
        raise SystemExit(
            f"only {len(rows)}/{len(SHORTLIST)} shortlist entries answered; "
            "refusing to write a mostly-empty table over a complete stale one."
        )
    return {
        "fetched_at": now(),
        "source": "huggingface.co/api/models/<repo_id>, one request per row",
        "what_is_editorial": "the choice of repo ids, size_class and role; every other field is the API's answer verbatim",
        "models": rows,
        "dropped": dropped,
    }


def fetch_gpu_prices() -> dict:
    q = json.dumps({
        "verified": {"eq": True}, "rentable": {"eq": True},
        "num_gpus": {"eq": 1}, "order": [["dph_total", "asc"]],
        "type": "on-demand",
    })
    offers = _get(
        "https://console.vast.ai/api/v0/bundles?q=" + urllib.parse.quote(q)
    ).get("offers", [])
    if len(offers) < 10:
        raise SystemExit(
            f"vast.ai answered {len(offers)} offers; a near-empty market read "
            "is a bad sample, not a price table. Nothing written."
        )
    by_gpu: dict[str, dict] = {}
    for offer in offers:
        name = offer.get("gpu_name")
        price = offer.get("dph_total")
        if not name or not price or name not in GPUS_OF_INTEREST:
            continue
        row = by_gpu.setdefault(name, {"gpu": name, "offers": [], "vram_gb": None})
        row["offers"].append(float(price))
        ram = offer.get("gpu_ram")
        if ram:
            row["vram_gb"] = round(ram / 1024)
    table = []
    for row in sorted(by_gpu.values(), key=lambda r: min(r["offers"])):
        prices = sorted(row["offers"])
        table.append({
            "gpu": row["gpu"],
            "vram_gb": row["vram_gb"],
            "usd_per_hour_min": round(prices[0], 3),
            "usd_per_hour_median": round(prices[len(prices) // 2], 3),
            "offers_sampled": len(prices),
        })
    return {
        "fetched_at": now(),
        "source": "console.vast.ai public offer search (verified, rentable, single-GPU, on-demand)",
        "honesty": (
            "These are live marketplace asks at fetch time, not a vendor rate "
            "card and not a promise. A single-offer row is one machine's price. "
            "Prices move daily; the fetched_at above is part of the number."
        ),
        "gpus": table,
        "market_offers_seen": len(offers),
    }


def fetch_local_recipes() -> dict:
    """Validated local-serving recipes from 0xSero's Local AI Registry.

    The owner pointed at it and the kinship is real: every field there carries
    its own provenance and captured_at, unobserved facts say `state: unknown`
    rather than a number, and "validated" means launched and measured, not
    hoped. Only a compact slice is kept - id, model, quant, engine, hardware,
    launchable - because the tool that serves this answers "how do people
    actually RUN a model like mine locally", not "mirror the registry"."""
    raw = _get(
        "https://local-ai-registry.vercel.app/api/v1/recipes"
        "?validation=validated&limit=80"
    )
    rows = []
    for r in raw.get("data", []):
        model = r.get("model") or {}
        rows.append({
            "id": r.get("id"),
            "model": model.get("name"),
            "repo": (model.get("huggingface") or {}).get("repository"),
            "params_b": model.get("params"),
            "quant": (r.get("quantization") or {}).get("format")
                      or r.get("quant") or None,
            "engine": (r.get("engine") or {}).get("name") or r.get("engine"),
            "launchable": r.get("launchable"),
        })
    if len(rows) < 10:
        raise SystemExit(
            f"the registry answered {len(rows)} validated recipes; refusing to "
            "overwrite a full table with a thin one."
        )
    return {
        "fetched_at": now(),
        "source": "local-ai-registry.vercel.app/api/v1/recipes?validation=validated (0xSero's Local AI Registry, github.com/0xSero/local-ai-registry)",
        "honesty": (
            "A curated slice of somebody else's measured work. Every claim's "
            "full provenance lives in the registry itself; this snapshot keeps "
            "the launchable shape and the pointer."
        ),
        "recipes": rows,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, build in (("model_shortlist.json", fetch_shortlist),
                        ("gpu_prices.json", fetch_gpu_prices),
                        ("local_recipes.json", fetch_local_recipes)):
        data = build()
        path = OUT / name
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        n = len(data.get("models") or data.get("gpus") or data.get("recipes") or [])
        print(f"wrote {path.name}: {n} rows, fetched_at {data['fetched_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
