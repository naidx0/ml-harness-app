"""Finding a model: a fit ranker, not a search box.

A search box answers "what is popular". That question has a different answer
from "what will run on this machine, for this job, under this licence", and the
gap between the two is where a person who is not an ML engineer loses a
weekend. `VISION.md` puts the whole moat in one sentence - *ease is not having
to know what to ask* - and a ranked shortlist is what that sentence looks like
when the question is "which model".

So downloads is worth **five points out of a hundred** here. Whether the thing
fits the card in front of you is worth thirty-five. That ratio is the product.

## One request, not two hundred

The Hub's list endpoint takes `expand[]`, so a single call returns, for every
candidate at once: `safetensors.parameters` (the exact parameter count),
`tags` (licence, format, library), `gated`, `library_name`, `pipeline_tag`,
`sha` and `config.architectures`. Two hundred candidates therefore cost one
request rather than two hundred, which matters because the anonymous budget is
500 requests per five minutes per IP - a figure this module does not take on
faith either: the server states it on every response in the `RateLimit` header
and `parse_rate_limit` reads it back.

What `expand[]=config` does *not* return is geometry. It carries
`architectures`, `model_type` and the tokenizer config, and nothing about
layers or heads - measured against the live API, not assumed. Geometry needs
the real `config.json`, one fetch per model, so this module ranks the whole
field on the parameter count and then reads `config.json` only for the few
candidates that survive. `app/feasibility.py` is what turns those bytes into a
KV-cache term.

## Ranking on a floor, and saying that it is a floor

Without geometry the estimator can compute the weights and the fixed overhead
and not the KV cache. That is a **floor**, not an estimate, and the two must
not be spelled the same way. `feasibility.verdict()` already draws that line -
weights alone over the card is `WONT_FIT` and certain; weights under the card
with the cache unread is `UNKNOWN` - so ranking gates on the first and never
claims the second. A model is eliminated only when it cannot fit whatever the
cache turns out to cost.

## Offline is a state, not an error

The Hub is not always reachable and a local-first harness that only works with
a network is not local-first. Every response is cached on disk; when the
network fails the cache is served with its age attached and `source` set to
`cache`, and when there is no cache the answer is "I could not look", never an
empty shortlist that reads like "nothing fits". Those two are different
answers and a user cannot tell them apart unless we do.

## The models already on this machine

An Ollama model that is already pulled is the strongest fit signal available -
zero download, zero wait, and proof it runs here - and it costs one loopback
request to find out. Its geometry comes from the GGUF metadata the daemon
already parsed, which is a measurement of the actual file on disk rather than
a claim about a repo.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from app import feasibility, hwdetect
from app.providers import ollama as ollama_adapter
from app.tools.registry import tool


REPO_ROOT = Path(__file__).resolve().parents[2]

#: Where Hub responses are kept. Per-machine runtime state, not source, and
#: rebindable so a test never touches the real one.
HUB_CACHE_ROOT = REPO_ROOT / ".hub-cache"

HUB_API = "https://huggingface.co/api"
HUB_FILES = "https://huggingface.co"
OLLAMA_BASE = "http://127.0.0.1:11434"

USER_AGENT = "ml-harness/0.1 (local; +https://github.com/ml-harness)"

#: How old a cached response may be before we try the network again. A model's
#: metadata is not volatile; six hours is well inside the useful life of a
#: parameter count and well outside the length of one session.
CACHE_MAX_AGE_SECONDS = 6 * 3600

#: Seconds before a Hub call is abandoned. The user is waiting.
HUB_TIMEOUT = 20

#: The sequence length a ranking is budgeted against when nobody has said one.
#: Reported as `defaulted`, never as a measurement.
DEFAULT_SEQ_LEN = 2048

#: Seconds before the loopback Ollama call is abandoned. It is on this machine
#: or it is not.
OLLAMA_TIMEOUT = 5

#: Every field the list endpoint will expand, checked against the live API's
#: own error message rather than against documentation. `childrenModelCount`
#: is *not* one of them, despite being the field the roadmap hoped for.
LIST_EXPAND = (
    "safetensors",
    "tags",
    "downloads",
    "gated",
    "pipeline_tag",
    "library_name",
    "config",
    "sha",
    "lastModified",
    "likes",
)

#: Pipeline tags the harness will rank. A closed set, because "any string the
#: model made up" reaches the Hub as a filter that silently matches nothing.
TASKS = (
    "text-generation",
    "text2text-generation",
    "text-classification",
    "token-classification",
    "question-answering",
    "summarization",
    "translation",
    "feature-extraction",
    "sentence-similarity",
    "image-classification",
    "object-detection",
    "image-segmentation",
    "automatic-speech-recognition",
    "tabular-classification",
    "tabular-regression",
)

#: Licence buckets. Four, and UNKNOWN is never quietly treated as permissive:
#: `license:other` is one of the commonest tags on the Hub and carries no
#: information at all. The harness presents the licence and its conditions and
#: does not render a legal judgement - being wrong here costs the user, not us.
CLEAR_COMMERCIAL = frozenset(
    {
        "apache-2.0",
        "mit",
        "bsd",
        "bsd-2-clause",
        "bsd-3-clause",
        "cc0-1.0",
        "cc-by-4.0",
        "cc-by-sa-4.0",
        "unlicense",
        "isc",
        "artistic-2.0",
        "mpl-2.0",
        "lgpl-3.0",
    }
)

#: Commercial use is allowed *subject to conditions a person has to read* -
#: acceptable-use policies, monthly-active-user thresholds, attribution.
CONDITIONAL = frozenset(
    {
        "llama2",
        "llama3",
        "llama3.1",
        "llama3.2",
        "llama3.3",
        "llama4",
        "gemma",
        "openrail",
        "openrail++",
        "bigscience-openrail-m",
        "bigcode-openrail-m",
        "creativeml-openrail-m",
        "tii-falcon-llm",
        "deepfloyd-if-license",
        "qwen",
        "qwen-research",
        "apple-ascl",
        "apple-amlr",
    }
)

NOT_COMMERCIAL = frozenset(
    {
        "cc-by-nc-4.0",
        "cc-by-nc-sa-4.0",
        "cc-by-nc-nd-4.0",
        "cc-by-nc-2.0",
        "cc-by-nc-3.0",
        "afl-3.0",
        "nvidia-open-model-license",
        "cc-by-nc-sa-3.0",
    }
)

#: The score is out of 100 and every weight is named here rather than buried in
#: an expression. `DOWNLOADS` is 5 on purpose: it is the number every other
#: tool sorts by, and sorting by it is the behaviour this module exists to
#: replace.
WEIGHTS = {
    "FIT": 35,
    "TASK": 20,
    "LICENCE": 15,
    "FINE_TUNABLE": 15,
    "QUANTIZED": 10,
    "DOWNLOADS": 5,
}

#: The headroom the fit curve peaks at. Too tight and the first long sequence
#: OOMs; far too loose and the user bought a model smaller than their machine
#: can carry. `docs/ROADMAP.md` M5.
HEADROOM_SWEET_SPOT = (0.15, 0.40)


class HubUnavailable(RuntimeError):
    """The Hub could not be reached and nothing was cached."""


# ---------------------------------------------------------------------------
# The cache, and the honest degradation it exists for.


def _cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    return HUB_CACHE_ROOT / f"{digest}.json"


def _cache_read(url: str) -> dict[str, Any] | None:
    try:
        body = json.loads(_cache_path(url).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict) or "payload" not in body:
        return None
    return body


def _cache_write(url: str, payload: Any) -> None:
    path = _cache_path(url)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"url": url, "fetched_at": time.time(), "payload": payload}),
            encoding="utf-8",
        )
    except OSError:
        # A cache that cannot be written is a slower harness, not a broken one.
        pass


_RATE_FIELD = re.compile(r"([a-z]+)=(\d+)")


def parse_rate_limit(headers: Any) -> dict[str, Any] | None:
    """Read the IETF `RateLimit` headers the Hub actually sends.

    Measured, not assumed: the live response carries
    `RateLimit: "api";r=499;t=264` and
    `RateLimit-Policy: "fixed window";"api";q=500;w=300`. `r` is what is left,
    `t` is seconds until the window resets, `q` is the quota. Reading them is
    how a backoff can be precise instead of a guessed sleep.
    """
    if headers is None:
        return None
    try:
        limit = headers.get("RateLimit")
        policy = headers.get("RateLimit-Policy")
    except AttributeError:
        return None
    if not limit and not policy:
        return None
    out: dict[str, Any] = {}
    for key, value in _RATE_FIELD.findall(str(limit or "")):
        if key == "r":
            out["remaining"] = int(value)
        elif key == "t":
            out["resets_in_seconds"] = int(value)
    for key, value in _RATE_FIELD.findall(str(policy or "")):
        if key == "q":
            out["quota"] = int(value)
        elif key == "w":
            out["window_seconds"] = int(value)
    return out or None


def fetch_json(
    url: str,
    *,
    timeout: int = HUB_TIMEOUT,
    max_age: float = CACHE_MAX_AGE_SECONDS,
    allow_network: bool = True,
) -> dict[str, Any]:
    """Get `url` as JSON, and say where the answer came from.

    Never raises for a network fault. Returns a dict whose `source` is one of:

    * `network` - fetched now;
    * `cache` - the network failed or was not allowed, and this is what we had,
      with `age_seconds` attached so the caller can say how old it is;
    * `unavailable` - no network and nothing cached. `ok` is `False`, and that
      is a different answer from an empty result.
    """
    cached = _cache_read(url)
    now = time.time()
    if cached is not None:
        age = now - float(cached.get("fetched_at") or 0)
        if not allow_network or age <= max_age:
            return {
                "ok": True,
                "payload": cached["payload"],
                "source": "cache",
                "age_seconds": round(age, 1),
                "url": url,
            }

    if allow_network:
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                rate = parse_rate_limit(response.headers)
            _cache_write(url, payload)
            return {
                "ok": True,
                "payload": payload,
                "source": "network",
                "age_seconds": 0.0,
                "rate_limit": rate,
                "url": url,
            }
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            detail = f"{type(exc).__name__}: {exc}"
    else:
        detail = "network lookup was not permitted for this call"

    if cached is not None:
        return {
            "ok": True,
            "payload": cached["payload"],
            "source": "cache",
            "age_seconds": round(now - float(cached.get("fetched_at") or 0), 1),
            "stale": True,
            "detail": detail,
            "url": url,
        }
    return {
        "ok": False,
        "payload": None,
        "source": "unavailable",
        "detail": detail,
        "url": url,
        "help": (
            "The Hugging Face Hub could not be reached and nothing for this "
            "query is cached. This is not the same as 'no model fits'."
        ),
    }


# ---------------------------------------------------------------------------
# Reading the Hub.


def search_url(
    *, task: str | None, query: str | None, limit: int, sort: str = "downloads"
) -> str:
    params: list[tuple[str, str]] = []
    if task:
        params.append(("pipeline_tag", task))
    if query:
        params.append(("search", query))
    params.append(("sort", sort))
    params.append(("direction", "-1"))
    params.append(("limit", str(int(limit))))
    params.extend(("expand[]", field) for field in LIST_EXPAND)
    return f"{HUB_API}/models?" + urllib.parse.urlencode(params)


def licence_of(tags: list[str]) -> tuple[str | None, str]:
    """`(licence id, bucket)`. `UNKNOWN` when the tag says nothing useful."""
    for tag in tags or ():
        if not isinstance(tag, str) or not tag.startswith("license:"):
            continue
        name = tag.split(":", 1)[1].strip().lower()
        if name in CLEAR_COMMERCIAL:
            return name, "CLEAR_COMMERCIAL"
        if name in NOT_COMMERCIAL:
            return name, "NOT_COMMERCIAL"
        if name in CONDITIONAL:
            return name, "CONDITIONAL"
        if name.startswith("cc-by-nc"):
            return name, "NOT_COMMERCIAL"
        return name, "UNKNOWN"
    return None, "UNKNOWN"


def _params_b(record: dict[str, Any]) -> tuple[float | None, str]:
    """Exact parameter count from the safetensors index, or nothing.

    Never parsed from the name. Two repos both called `8B` differ by hundreds
    of millions of parameters, and a mixture-of-experts repo called `30B-A3B`
    holds thirty billion resident whatever its name suggests about the three.
    """
    safetensors = record.get("safetensors")
    if isinstance(safetensors, dict):
        total = safetensors.get("total")
        if isinstance(total, int) and not isinstance(total, bool) and total > 0:
            return round(total / 1e9, 3), "safetensors index (measured)"
    return None, "no safetensors index on this repo; parameter count unknown"


def summarize(record: dict[str, Any]) -> dict[str, Any]:
    """One Hub record reduced to the fields a ranking decision uses."""
    tags = [t for t in (record.get("tags") or []) if isinstance(t, str)]
    licence, bucket = licence_of(tags)
    params_b, params_source = _params_b(record)
    config = record.get("config") if isinstance(record.get("config"), dict) else {}
    return {
        "repo_id": record.get("id"),
        "sha": record.get("sha"),
        "task": record.get("pipeline_tag"),
        "library": record.get("library_name"),
        "architectures": config.get("architectures") or [],
        "model_type": config.get("model_type"),
        "gated": bool(record.get("gated")),
        "downloads": record.get("downloads"),
        "likes": record.get("likes"),
        "last_modified": record.get("lastModified"),
        "licence": licence,
        "licence_bucket": bucket,
        "params_b": params_b,
        "params_source": params_source,
        "has_safetensors": "safetensors" in tags or bool(record.get("safetensors")),
        "is_gguf": "gguf" in tags,
        "quantized_from": [
            t.split("base_model:quantized:", 1)[1]
            for t in tags
            if t.startswith("base_model:quantized:")
        ],
        "tags": tags,
    }


def fetch_config(repo_id: str, *, revision: str | None = None) -> dict[str, Any]:
    """Fetch one repo's real `config.json` and store it with its provenance.

    Two requests, and both are needed: the API call resolves the revision and
    the exact parameter count, and the file call gets the geometry. Storing the
    revision is what makes the stored geometry re-checkable later rather than
    an undated copy of something that has since moved.
    """
    meta_url = f"{HUB_API}/models/{repo_id}?expand[]=sha&expand[]=safetensors"
    meta = fetch_json(meta_url)
    sha = revision
    params_total = None
    if meta["ok"] and isinstance(meta["payload"], dict):
        sha = revision or meta["payload"].get("sha")
        safetensors = meta["payload"].get("safetensors")
        if isinstance(safetensors, dict) and isinstance(
            safetensors.get("total"), int
        ):
            params_total = safetensors["total"]

    ref = sha or "main"
    config_url = f"{HUB_FILES}/{repo_id}/resolve/{ref}/config.json"
    got = fetch_json(config_url)
    if not got["ok"] or not isinstance(got["payload"], dict):
        return {
            "ok": False,
            "repo_id": repo_id,
            "error": "config_unreadable",
            "detail": got.get("detail", "config.json could not be read"),
            "source": got["source"],
        }

    try:
        path = feasibility.store_model_config(
            repo_id,
            got["payload"],
            revision=sha,
            url=config_url,
            parameters_total=params_total,
            parameters_source="huggingface safetensors index",
        )
    except OSError as exc:
        # A read-only install can still rank; it just cannot remember. Say so
        # rather than failing the whole call, and do not claim it was stored.
        return {
            "ok": False,
            "repo_id": repo_id,
            "revision": sha,
            "error": "config_unstorable",
            "detail": f"read it, could not keep it: {type(exc).__name__}: {exc}",
            "geometry": _geometry_dict(
                feasibility.geometry_from_config(
                    got["payload"], source=f"config.json of {repo_id} at {sha}"
                )
            ),
        }
    geometry = feasibility.geometry_for(repo_id)
    return {
        "ok": True,
        "repo_id": repo_id,
        "revision": sha,
        "source": got["source"],
        "stored_at": str(path),
        "geometry": _geometry_dict(geometry),
        "parameters_total": params_total,
        "parameters_source": (
            "huggingface safetensors index (measured)"
            if params_total
            else "no safetensors index on this repo"
        ),
    }


def _geometry_dict(geometry: feasibility.ModelGeometry | None) -> dict[str, Any] | None:
    if geometry is None:
        return None
    return {
        "num_hidden_layers": geometry.num_hidden_layers,
        "num_attention_heads": geometry.num_attention_heads,
        "num_key_value_heads": geometry.num_key_value_heads,
        "head_dim": geometry.head_dim,
        "hidden_size": geometry.hidden_size,
        "vocab_size": geometry.vocab_size,
        "provenance": geometry.provenance,
        "source": geometry.source,
    }


# ---------------------------------------------------------------------------
# The ranker.


def _headroom_score(fraction: float | None) -> float:
    """0 to 1 across the headroom curve. Peaks inside the sweet spot.

    Penalises both ends. A model that leaves 2% free will OOM on the first long
    batch; a model that leaves 85% free means the user is running something far
    smaller than the card they own, which is a worse answer than it looks.
    """
    if fraction is None:
        return 0.0
    low, high = HEADROOM_SWEET_SPOT
    if fraction < 0:
        return 0.0
    if low <= fraction <= high:
        return 1.0
    if fraction < low:
        return max(0.0, fraction / low)
    return max(0.0, 1.0 - (fraction - high) / (1.0 - high))


def fit_of(
    candidate: dict[str, Any],
    *,
    vram: feasibility.Field,
    method: str,
    seq_len: int,
    geometry: feasibility.ModelGeometry | None = None,
    grad_checkpointing: bool = True,
) -> dict[str, Any]:
    """What this candidate costs, and whether that is a floor or a total.

    `grad_checkpointing` defaults to on because every adapter recipe worth
    driving turns it on, and the published floors this repo validates against
    (`tests/test_feasibility_memory_math.py`) are measured with it on. Costing
    a LoRA run without it makes the activation term dominate everything and
    every model on the Hub comes back as "will not fit", which is a wrong
    answer arrived at honestly - still wrong.
    """
    params_b = candidate.get("params_b")
    if method == "inference":
        estimate = feasibility.estimate_vram(
            params_b, "Q4_K_M", seq_len, "q8_0", geometry=geometry
        )
        known = estimate["weights_gb"]
    else:
        estimate = feasibility.estimate_training_vram(
            params_b,
            method,
            seq_len,
            geometry=geometry,
            grad_checkpointing=grad_checkpointing,
        )
        known = None
        if estimate["base_weights_gb"] is not None:
            known = (
                estimate["base_weights_gb"]
                + (estimate["gradients_gb"] or 0.0)
                + (estimate["optimizer_gb"] or 0.0)
                # THE LOGITS BUFFER. It was absent from this sum while
                # `total_gb` included it, so the verdict was computed against a
                # cost the same function had already said was higher. Measured
                # on the owner's card: Qwen3-8B QLoRA at 2,048 tokens came back
                # SPILLS with 0.71 GB of headroom, while its own `total_gb` was
                # 8.45 GB against 8.0 - the product promising that a run which
                # OOMs will work. It is `s*b*vocab*4`, and every one of those is
                # known once config.json is read, so it is CERTAIN rather than
                # variable - which is where `feasibility.can_this_machine_train`
                # already puts it. These two now agree.
                + (estimate["logits_gb"] or 0.0)
            )
    variable_gb = (
        estimate.get("kv_gb") if method == "inference" else estimate.get("activations_gb")
    )
    if (
        method != "inference"
        and variable_gb is not None
        and estimate.get("logits_gb") is None
    ):
        # Geometry sized the activations but carried no `vocab_size`, so a term
        # this module knows is one of the largest is unsized. Ruling 6: a
        # verdict computed from a missing term treated as zero renders as
        # UNKNOWN, not as a verdict.
        variable_gb = None
    verdict = feasibility.verdict(
        vram,
        known,
        variable_gb,
        overhead_gb=estimate["overhead_gb"],
        geometry_provenance=estimate["geometry_provenance"],
    )
    floor_gb = None if known is None else round(known + estimate["overhead_gb"], 2)
    # Headroom feeds `score()` through `_headroom_score`, so an overstated one
    # does not merely misreport - it RANKS a model that will not fit above one
    # that will, which is how a model needing 8.45 GB came to be recommended for
    # an 8 GB card. Measure it against the real total wherever the total is
    # known; fall back to the floor only when it is not, and say which was used.
    headroom_basis = estimate.get("total_gb")
    if headroom_basis is None:
        headroom_basis = floor_gb
    headroom_fraction = None
    if headroom_basis is not None and vram.value:
        headroom_fraction = (
            float(vram.value) - float(headroom_basis)
        ) / float(vram.value)
    return {
        "verdict": verdict["verdict"],
        "floor_gb": floor_gb,
        "floor_is_a_floor": geometry is None,
        "grad_checkpointing": method != "inference" and grad_checkpointing,
        "total_gb": estimate.get("total_gb"),
        "headroom_fraction": (
            None if headroom_fraction is None else round(headroom_fraction, 3)
        ),
        #: "total" when the headroom above is the real cost, "floor" when the
        #: total could not be computed and it is therefore a best case.
        "headroom_basis": (
            None
            if headroom_basis is None
            else ("total" if estimate.get("total_gb") is not None else "floor")
        ),
        "vram_gb": vram.value,
        "vram_provenance": vram.provenance,
        "geometry_provenance": estimate["geometry_provenance"],
        "reason": verdict.get("reason", ""),
        "assumptions": estimate["assumptions"],
    }


def score(
    candidate: dict[str, Any],
    fit: dict[str, Any],
    *,
    task: str | None,
    intent: str,
    method: str,
    max_downloads: int,
) -> dict[str, Any]:
    """A capped score out of 100, itemised so the reasoning can be shown."""
    parts: dict[str, float] = {}

    parts["fit"] = round(
        WEIGHTS["FIT"] * _headroom_score(fit.get("headroom_fraction")), 1
    )
    parts["task"] = float(
        WEIGHTS["TASK"] if (task is None or candidate.get("task") == task) else 0
    )

    bucket = candidate["licence_bucket"]
    if bucket == "CLEAR_COMMERCIAL":
        parts["licence"] = float(WEIGHTS["LICENCE"])
    elif bucket == "CONDITIONAL":
        parts["licence"] = WEIGHTS["LICENCE"] * 0.6
    elif bucket == "NOT_COMMERCIAL":
        parts["licence"] = 0.0 if intent == "commercial" else WEIGHTS["LICENCE"] * 0.4
    else:
        parts["licence"] = WEIGHTS["LICENCE"] * 0.2

    wants_training = method in ("lora", "qlora", "full")
    if wants_training:
        parts["fine_tunable"] = float(
            WEIGHTS["FINE_TUNABLE"] if candidate["has_safetensors"] else 0
        )
    else:
        parts["fine_tunable"] = WEIGHTS["FINE_TUNABLE"] * 0.5

    parts["quantized"] = float(
        WEIGHTS["QUANTIZED"]
        if (candidate["is_gguf"] or candidate["quantized_from"])
        else 0
    )

    downloads = candidate.get("downloads") or 0
    parts["downloads"] = round(
        WEIGHTS["DOWNLOADS"] * (min(downloads, max_downloads) / max(max_downloads, 1)),
        1,
    )

    if candidate["gated"]:
        parts["gated_demotion"] = -10.0

    total = round(sum(parts.values()), 1)
    return {"score": max(0.0, min(100.0, total)), "parts": parts}


def eliminate(
    candidate: dict[str, Any], fit: dict[str, Any], *, task: str | None, intent: str
) -> str | None:
    """A hard gate, with the reason. `None` means the candidate survives.

    Every gate here returns a sentence a person can act on. "No results" is
    the failure mode this replaces: it tells a user nothing about whether they
    asked wrongly, whether their card is too small, or whether the Hub was down.
    """
    if task and candidate.get("task") and candidate["task"] != task:
        return f"this repo is for {candidate['task']}, not {task}"
    if fit["verdict"] == "WONT_FIT":
        # Two different WONT_FITs, and saying the wrong one is a lie that reads
        # as a contradiction: "the weights alone need 5.95 GB and this machine
        # has 8.0 GB, so it will not fit" is a sentence that argues against
        # itself. When the total is known, quote the total.
        if fit.get("total_gb") is not None:
            return (
                f"this needs about {fit['total_gb']} GB in total - weights, "
                "gradients, optimizer state, activations and overhead - and "
                f"this machine has {fit['vram_gb']} GB"
            )
        return (
            f"the weights alone need {fit['floor_gb']} GB and this machine has "
            f"{fit['vram_gb']} GB, so it will not fit whatever else costs"
        )
    if intent == "commercial" and candidate["licence_bucket"] == "NOT_COMMERCIAL":
        return (
            f"licence {candidate['licence']} forbids commercial use and you "
            "said this is commercial"
        )
    if candidate.get("params_b") is None:
        return (
            "this repo publishes no safetensors index, so its parameter count "
            "cannot be read and its memory cost cannot be computed"
        )
    return None


def rank(
    records: list[dict[str, Any]],
    *,
    vram: feasibility.Field,
    task: str | None = None,
    intent: str = "unspecified",
    method: str = "qlora",
    seq_len: int = 2048,
    geometry_by_repo: dict[str, feasibility.ModelGeometry] | None = None,
    grad_checkpointing: bool = True,
) -> dict[str, Any]:
    """Rank candidates by fit for this job on this machine. Never by downloads."""
    candidates = [summarize(record) for record in records if isinstance(record, dict)]
    max_downloads = max(
        [c.get("downloads") or 0 for c in candidates] or [1], default=1
    ) or 1

    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for candidate in candidates:
        geometry = (geometry_by_repo or {}).get(candidate["repo_id"])
        fit = fit_of(
            candidate,
            vram=vram,
            method=method,
            seq_len=seq_len,
            geometry=geometry,
            grad_checkpointing=grad_checkpointing,
        )
        reason = eliminate(candidate, fit, task=task, intent=intent)
        if reason:
            dropped.append(
                {"repo_id": candidate["repo_id"], "reason": reason,
                 "verdict": fit["verdict"]}
            )
            continue
        scored = score(
            candidate,
            fit,
            task=task,
            intent=intent,
            method=method,
            max_downloads=max_downloads,
        )
        entry = dict(candidate)
        entry["fit"] = fit
        entry["score"] = scored["score"]
        entry["score_parts"] = scored["parts"]
        entry["demotions"] = _demotions(candidate)
        kept.append(entry)

    kept.sort(key=lambda e: (-e["score"], -(e.get("downloads") or 0)))
    return {"ranked": kept, "eliminated": dropped, "weights": dict(WEIGHTS)}


def _demotions(candidate: dict[str, Any]) -> list[str]:
    out = []
    if candidate["gated"]:
        out.append(
            "gated: metadata is public but the files need approval, which can "
            "take days. Nobody here accepts a licence on your behalf."
        )
    if candidate["licence_bucket"] == "UNKNOWN":
        out.append(
            f"licence {candidate['licence'] or 'not stated'} carries no usable "
            "information; read it before you rely on it"
        )
    if candidate["licence_bucket"] == "CONDITIONAL":
        out.append(
            f"licence {candidate['licence']} permits commercial use subject to "
            "conditions you have to read"
        )
    if not candidate["has_safetensors"]:
        out.append("no safetensors weights, so this cannot be fine-tuned as-is")
    return out


# ---------------------------------------------------------------------------
# The models already on this machine.


GGUF_KEYS = {
    "layers": "block_count",
    "heads": "attention.head_count",
    "kv_heads": "attention.head_count_kv",
    "hidden": "embedding_length",
    "key_length": "attention.key_length",
    "vocab": "vocab_size",
}


def geometry_from_gguf(model_info: dict[str, Any]) -> feasibility.ModelGeometry | None:
    """Geometry from the GGUF metadata Ollama already parsed.

    A measurement of the file on this disk, not a claim about a repo, so the
    provenance is `measured` and the source names the daemon.

    `vocab_size` is allowed to be missing here and is not allowed to be missing
    in `feasibility.geometry_from_config`. That is deliberate rather than
    inconsistent: `general.architecture` already establishes that this is a
    decoder, which is the thing `vocab_size` was standing in for on the config
    path, and several real GGUFs on this machine simply do not carry the field.
    Without it the KV term still computes and the logits term does not.
    """
    if not isinstance(model_info, dict):
        return None
    arch = model_info.get("general.architecture")
    if not isinstance(arch, str) or not arch:
        return None

    def read(name: str) -> int | None:
        value = model_info.get(f"{arch}.{GGUF_KEYS[name]}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return int(value) if value > 0 else None

    layers, heads, hidden = read("layers"), read("heads"), read("hidden")
    if not (layers and heads and hidden):
        return None
    head_dim = read("key_length")
    if head_dim is None:
        if hidden % heads:
            return None
        head_dim = hidden // heads
    return feasibility.ModelGeometry(
        num_hidden_layers=layers,
        num_key_value_heads=read("kv_heads") or heads,
        head_dim=head_dim,
        vocab_size=read("vocab"),
        hidden_size=hidden,
        num_attention_heads=heads,
        provenance="measured",
        source=f"GGUF metadata for {arch}, read by the local Ollama daemon",
    )


def _ollama(path: str, payload: dict[str, Any] | None = None) -> Any | None:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_BASE + path,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST" if data else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# The tools.


def _vram_field() -> feasibility.Field:
    """This machine's VRAM, with the provenance `hwdetect` gave it."""
    specs = hwdetect.local_specs()
    return feasibility.Field(
        specs.get("vram_gb"),
        (specs.get("provenance") or {}).get("vram_gb", "defaulted"),
        (specs.get("sources") or {}).get("vram_gb", "app/hwdetect.py"),
    )


@tool(
    "find_models",
    description=(
        "Search the Hugging Face Hub and return models ranked by how well they "
        "fit THIS machine, THIS task and THIS licence intent - not by how "
        "popular they are. Downloads is worth 5 points out of 100; whether it "
        "fits the card is worth 35. Every candidate that was thrown out comes "
        "back with the reason. Reads the real config.json for the top few so "
        "the memory figure is a total rather than a floor."
    ),
    schema={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Hugging Face pipeline tag to filter on.",
                "enum": list(TASKS),
            },
            "query": {
                "type": "string",
                "description": "Free-text search, e.g. a family name like 'qwen3'.",
            },
            "method": {
                "type": "string",
                "description": (
                    "What the model is for. Training methods are costed as "
                    "training; 'inference' is costed as inference."
                ),
                "enum": ["qlora", "lora", "full", "inference"],
            },
            "intent": {
                "type": "string",
                "description": "Whether the use is commercial. Decides the licence gate.",
                "enum": ["commercial", "non-commercial", "unspecified"],
            },
            "max_seq_len": {
                "type": "integer",
                "description": (
                    "Sequence length to budget against. If you have measured "
                    "the p95 token length of the user's own data, pass it; "
                    "leave it out and the ranking is labelled as budgeted "
                    "against a default, because this one number sets the "
                    "KV-cache term and therefore who passes the fit gate."
                ),
            },
            "vram_gb": {
                "type": "number",
                "description": (
                    "Override the detected VRAM. Leave empty to use the "
                    "measured value from this machine."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "How many Hub candidates to consider. Default 50.",
            },
            "detail": {
                "type": "integer",
                "description": (
                    "How many of the top candidates get their config.json read "
                    "so their memory figure is a total rather than a floor. "
                    "Default 3; each one is one extra request."
                ),
            },
        },
    },
    reads=("hardware", "huggingface_hub"),
    writes=("model_config_cache",),
    provides=("models.candidate.find",),
    label="Find a model that fits",
    group="Choose",
    verb="rank models by fit for this machine and this job",
    order=40,
)
def find_models(
    task: str | None = None,
    query: str | None = None,
    method: str = "qlora",
    intent: str = "unspecified",
    max_seq_len: int | None = None,
    vram_gb: float | None = None,
    limit: int = 50,
    detail: int = 3,
) -> dict[str, Any]:
    if task is not None and task not in TASKS:
        return {
            "ok": False,
            "error": "unknown_task",
            "detail": f"{task!r} is not a Hugging Face pipeline tag this harness ranks",
            "known_tasks": list(TASKS),
        }
    if method not in ("qlora", "lora", "full", "inference"):
        method = "qlora"
    try:
        bound = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        bound = 50
    try:
        detail_count = max(0, min(int(detail), 10))
    except (TypeError, ValueError):
        detail_count = 3
    # The provenance of this one number is load-bearing, so it is tracked
    # rather than assumed. `docs/ROADMAP.md` M5: `max_seq_len` sets the
    # KV-cache term, which sets the memory budget, which decides who passes the
    # fit gate - so a ranking budgeted against a default must say so and must
    # not read as though somebody measured the user's data.
    if max_seq_len is None:
        seq_len = DEFAULT_SEQ_LEN
        seq_len_source = "defaulted"
    else:
        try:
            seq_len = max(128, min(int(max_seq_len), 131072))
            seq_len_source = "declared"
        except (TypeError, ValueError):
            seq_len = DEFAULT_SEQ_LEN
            seq_len_source = "defaulted"

    if vram_gb is None:
        vram = _vram_field()
    else:
        vram = feasibility.Field(
            float(vram_gb), "declared", "supplied with the tool call"
        )

    got = fetch_json(search_url(task=task, query=query, limit=bound))
    if not got["ok"]:
        return {
            "ok": False,
            "error": "hub_unavailable",
            "detail": got["detail"],
            "source": got["source"],
            "help": got["help"],
        }
    records = got["payload"] if isinstance(got["payload"], list) else []

    def ranking(
        geometry_by_repo: dict[str, feasibility.ModelGeometry] | None,
    ) -> dict[str, Any]:
        return rank(
            records,
            vram=vram,
            task=task,
            intent=intent,
            method=method,
            seq_len=seq_len,
            geometry_by_repo=geometry_by_repo,
        )

    # Read the real config.json for the candidates at the top, then rank again
    # so their figure is a total and not a floor - and then look again, because
    # reading a config can *eliminate* a leader (its activations turn out not to
    # fit), and that promotes models nobody has looked at yet. One pass leaves
    # the detail on the models that just got dropped, which is precisely
    # backwards. Bounded by `budget` so this cannot become a request storm.
    geometry_by_repo: dict[str, feasibility.ModelGeometry] = {}
    read_configs: list[dict[str, Any]] = []
    tried: set[str] = set()
    budget = detail_count * 2
    final = ranking(None)

    for _ in range(3):
        wanted = [
            entry["repo_id"]
            for entry in final["ranked"][:detail_count]
            if isinstance(entry["repo_id"], str)
            and entry["repo_id"] not in geometry_by_repo
            and entry["repo_id"] not in tried
        ]
        if not wanted or budget <= 0:
            break
        for repo_id in wanted[:budget]:
            tried.add(repo_id)
            budget -= 1
            geometry = feasibility.geometry_for(repo_id)
            if geometry is None:
                read_configs.append(fetch_config(repo_id))
                geometry = feasibility.geometry_for(repo_id)
            if geometry is not None:
                geometry_by_repo[repo_id] = geometry
        final = ranking(geometry_by_repo)

    return {
        "ok": True,
        "asked": {
            "task": task,
            "query": query,
            "method": method,
            "intent": intent,
            "max_seq_len": seq_len,
            "max_seq_len_source": seq_len_source,
            "max_seq_len_note": (
                "Measured p95 token length from the user's own data is the "
                "honest value. Nothing here has measured it."
                if seq_len_source == "defaulted"
                else "Supplied with the call."
            ),
            "considered": len(records),
        },
        "vram_gb": vram.value,
        "vram_provenance": vram.provenance,
        "source": got["source"],
        "age_seconds": got.get("age_seconds"),
        "stale": got.get("stale", False),
        "rate_limit": got.get("rate_limit"),
        "ranked": final["ranked"][:10],
        "eliminated": final["eliminated"][:20],
        "weights": final["weights"],
        "configs_read": read_configs,
        "how_ranked": (
            "Hard gates first (wrong task, cannot fit, licence forbids the "
            "stated intent, no readable parameter count), then demotions, then "
            "a score out of 100 in which downloads is worth 5 and fitting this "
            "machine is worth 35."
        ),
        "provenance": {
            "params_b": "measured from the repo's safetensors index",
            "vram_gb": vram.provenance,
            "kv_cache": (
                "computed from the model's own config.json where one was read; "
                "otherwise not computed and the figure is a floor"
            ),
        },
    }


@tool(
    "read_model_config",
    description=(
        "Read one model's real config.json from the Hugging Face Hub and keep "
        "it, so memory estimates for that model are computed from its own "
        "layers, heads and vocabulary instead of borrowed from another "
        "architecture. Use this before quoting a memory figure for a specific "
        "model."
    ),
    schema={
        "type": "object",
        "properties": {
            "repo_id": {
                "type": "string",
                "description": "Hugging Face repo, e.g. 'Qwen/Qwen3-4B'.",
            },
            "revision": {
                "type": "string",
                "description": "Commit sha to pin to. Defaults to the current one.",
            },
        },
        "required": ["repo_id"],
    },
    reads=("huggingface_hub",),
    writes=("model_config_cache",),
    provides=("models.config.read",),
    label="Read a model's config",
    group="Choose",
    verb="read this model's real config.json",
    order=41,
)
def read_model_config(repo_id: str, revision: str | None = None) -> dict[str, Any]:
    if not isinstance(repo_id, str) or not repo_id.strip():
        return {"ok": False, "error": "no_repo_id", "detail": "repo_id is required"}
    result = fetch_config(repo_id.strip(), revision=revision)
    if result["ok"] and result["geometry"] is None:
        result["note"] = (
            "The config was read and does not describe an autoregressive text "
            "decoder - it has no vocabulary - so there is no KV cache to size "
            "and the memory verdict for it stays UNKNOWN. That is the honest "
            "answer, not a failure."
        )
    return result


@tool(
    "list_local_models",
    description=(
        "List the models already downloaded on this machine through the local "
        "Ollama daemon, with the real geometry read from each GGUF file. A "
        "model that is already here needs no download and is proven to run, "
        "which is the strongest fit evidence available."
    ),
    schema={"type": "object", "properties": {}},
    reads=("local_models",),
    writes=(),
    provides=("machine.local_models.list",),
    label="List local models",
    group="Look",
    verb="list the models already on this machine",
    order=42,
)
def list_local_models() -> dict[str, Any]:
    tags = _ollama("/api/tags")
    if not isinstance(tags, dict):
        return {
            "ok": False,
            "error": "no_local_daemon",
            "detail": f"nothing answered at {OLLAMA_BASE}",
            #: THE SAME SENTENCE THE PROBE GIVES, imported rather than written
            #: twice. This text and the connect button's refusal are the same
            #: moment in a person's day reached by two different routes, and
            #: two hand-written versions drift until the product contradicts
            #: itself about whether anything is wrong.
            "help": ollama_adapter.THE_DAEMON_IS_NOT_RUNNING,
        }
    out = []
    for entry in tags.get("models") or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("model") or entry.get("name")
        shown = _ollama("/api/show", {"model": name}) or {}
        info = shown.get("model_info") if isinstance(shown, dict) else None
        geometry = geometry_from_gguf(info or {})
        size_bytes = entry.get("size")
        params = (info or {}).get("general.parameter_count")
        out.append(
            {
                "name": name,
                "family": (entry.get("details") or {}).get("family"),
                "quantization": (entry.get("details") or {}).get("quantization_level"),
                "on_disk_gb": (
                    round(size_bytes / (1024 ** 3), 2)
                    if isinstance(size_bytes, int)
                    else None
                ),
                "params_b": (
                    round(params / 1e9, 3)
                    if isinstance(params, int) and not isinstance(params, bool)
                    else None
                ),
                "capabilities": shown.get("capabilities") if isinstance(shown, dict) else None,
                "licence": (info or {}).get("general.license"),
                "geometry": _geometry_dict(geometry),
            }
        )
    return {
        "ok": True,
        "count": len(out),
        "models": out,
        "source": f"the Ollama daemon at {OLLAMA_BASE}",
        "provenance": {
            "on_disk_gb": "measured",
            "params_b": "measured, from the GGUF header",
            "geometry": "measured, from the GGUF header",
        },
    }


__all__ = [
    "CACHE_MAX_AGE_SECONDS",
    "DEFAULT_SEQ_LEN",
    "HUB_CACHE_ROOT",
    "TASKS",
    "WEIGHTS",
    "fetch_config",
    "fetch_json",
    "find_models",
    "fit_of",
    "geometry_from_gguf",
    "licence_of",
    "list_local_models",
    "parse_rate_limit",
    "rank",
    "read_model_config",
    "search_url",
    "summarize",
]
