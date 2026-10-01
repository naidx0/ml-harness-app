"""Memory estimation and the feasibility verdict.

What changed, and why.

* The module imported itself and carried a ``test_verdict()`` function in
  production code. Both are gone.
* ``estimate_vram`` hardcoded ``2 * 32 * 8 * 128`` - Llama-3-8B's exact KV
  geometry - and applied it to every model from 270M to 27B, so a 0.5B and a
  27B model got the same cache figure. Geometry is now an argument. When it is
  not supplied the KV term is ``None``, not a guess.
* ``Q4`` was 0.5 bytes per parameter. Real Q4_K_M is 4.91 bits, 0.61 bytes -
  the old constant understated it by about 21%, in the direction that tells a
  user something fits when it will OOM (docs/ROADMAP.md, "estimate_vram is dead
  code, and it is wrong anyway"; docs/ARCHITECTURE.md section 4.7).
* The estimator modelled inference only and omitted the CUDA context and the
  desktop reserve entirely. ``estimate_training_vram`` adds gradients, optimizer
  states, activations and the logits buffer, per docs/ARCHITECTURE.md 4.8 and
  docs/ROADMAP.md M2.
* ``verdict`` gained a fourth value, ``UNKNOWN`` (Ruling 6). A verdict computed
  from a defaulted hardware number is a different claim from one computed from a
  measured GPU, and the product must not say them in the same word.
* ``recommend`` never received ``data_kind``, so an image-classification goal
  was answered with a language model.

Every constant below carries its source. Ruling 9: no invented numbers.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Literal, Mapping

GIB = 1024 ** 3

Provenance = Literal[
    "measured",
    "inferred",
    "declared",
    "defaulted",
    "untested_on_this_platform",
]

#: Provenances a confident verdict may be computed from. A value that is a
#: fallback constant, or that came from a code path never run on this platform,
#: is not one of them - that is what UNKNOWN is for.
CONFIDENT_PROVENANCE = frozenset({"measured", "inferred", "declared"})

VERDICTS = ("FITS", "SPILLS", "WONT_FIT", "UNKNOWN")

#: FITTING AND BEING PLACED ARE TWO QUESTIONS, AND THIS FILE ONLY ANSWERS ONE.
#:
#: `SPILLS` here means "needed lands within a tenth of the card" - a margin
#: band, computed from memory. It is not a claim about where a runtime will put
#: the layers, and the name reads like one.
#:
#: Measured on this card (RTX 2060 SUPER, 8,192 MiB) on 2026-09-04: a 9B Q4_K_M
#: at 65,536 context peaks at 7,081 MiB with every layer resident, which this
#: arithmetic calls FITS at 86% of the card. Ollama placed it anyway at 15% CPU
#: / 85% GPU, having sized it at 7.3 GB against 6.5 GiB it called available,
#: and generated at a fifth of the resident speed. Forcing `num_gpu` to all 33
#: layers put it entirely on the card and it ran.
#:
#: This estimator cannot see a runtime's own placement estimate and must not
#: pretend to. So an answer that fits says which question it answered, and
#: names the lever, rather than letting "YES" be read as "it will run on the
#: GPU".
PLACEMENT_IS_NOT_MEMORY = (
    "This is memory arithmetic. A serving runtime makes its own placement "
    "estimate and can put layers on the CPU even when the card has room: "
    "measured here on 2026-09-04, a 9B Q4_K_M at 65,536 context peaks at "
    "7,081 MiB of 8,192 and still ran 15% on the CPU at a fifth of the speed, "
    "because Ollama sized it at 7.3 GB against the 6.5 GiB it called "
    "available. Forcing num_gpu to all layers put it back on the card. If a "
    "run is slower than these numbers suggest, check where the layers actually "
    "went before believing the arithmetic was wrong."
)


@dataclass(frozen=True)
class Field:
    """A number that knows where it came from.

    This is the type-level fix for the whole class of bug that produced the
    hardcoded ``8.0``: a bare float cannot say whether it was measured or made
    up, so ``verdict`` treats one as ``defaulted`` and answers ``UNKNOWN``.
    """

    value: Any
    provenance: Provenance = "defaulted"
    source: str = ""

    @property
    def is_confident(self) -> bool:
        return self.value is not None and self.provenance in CONFIDENT_PROVENANCE


def as_field(value: Any, default_provenance: Provenance = "defaulted") -> Field:
    """Coerce a bare number into a ``Field``.

    A bare float is deliberately ``defaulted``. Nobody vouched for it, so the
    product will not put a confident verdict behind it.
    """
    if isinstance(value, Field):
        return value
    return Field(value, default_provenance, "unstated")


def measured(value: Any, source: str = "") -> Field:
    return Field(value, "measured", source)


def declared(value: Any, source: str = "") -> Field:
    return Field(value, "declared", source)


@dataclass(frozen=True)
class ModelGeometry:
    """The parts of a model's ``config.json`` the KV-cache term needs.

    ``provenance`` is ``measured`` when these were read from a real
    ``config.json`` and ``defaulted`` when they were not. There is no third
    option that lets us pretend.
    """

    num_hidden_layers: int
    num_key_value_heads: int
    head_dim: int
    vocab_size: int | None = None
    hidden_size: int | None = None
    num_attention_heads: int | None = None
    #: WHETHER `lm_head` IS THE EMBEDDING OR A SECOND TENSOR. `None` means the
    #: config did not say, and transformers' own `PretrainedConfig` default is
    #: True, so absent is read as tied rather than guessed at.
    tie_word_embeddings: bool | None = None
    provenance: Provenance = "measured"
    source: str = "config.json"


# ---------------------------------------------------------------------------
# Real geometry, read from a real config.json.
#
# The defect this section closes: `recommend()` returned `"geometry": None` for
# every model it could ever name, so the KV-cache term was never computed, so
# `verdict()` answered UNKNOWN at 4, 6, 8 and 24 GB alike. A verdict that is
# the same word whatever card you own is not a verdict.
#
# The fix is not a table of shapes typed into this file - that is the
# single-architecture bug again, wearing more entries. It is to read the
# model's own `config.json`, keep the bytes we read, and record which revision
# they came from. Nothing here guesses a field. When the fields that make a KV
# cache meaningful are absent, this returns `None` and UNKNOWN survives, which
# is the fourth verdict doing its job rather than being bypassed.

#: Where a fetched `config.json` is kept, one file per repo, each one an
#: envelope carrying the verbatim config plus where it came from. Module-level
#: and rebindable, matching `db.DB_PATH` and `jobspec.RECIPES_ROOT`, so a test
#: gets its own directory without a mutable registry a request could reach.
MODEL_CONFIG_ROOT = Path(__file__).resolve().parent / "model_configs"

_SLUG_BAD = re.compile(r"[^A-Za-z0-9._-]+")

#: The same field under every name four generations of Hugging Face configs
#: have spelled it. Order matters: the first match wins.
_LAYER_KEYS = ("num_hidden_layers", "n_layer", "num_layers", "n_layers")
_HIDDEN_KEYS = ("hidden_size", "n_embd", "d_model", "dim")
_HEAD_KEYS = ("num_attention_heads", "n_head", "num_heads", "n_heads")
_KV_HEAD_KEYS = ("num_key_value_heads", "n_head_kv", "num_kv_heads")

#: A multimodal config hides the decoder one level down. Merged rather than
#: replaced, because `vocab_size` often stays at the top level.
_NESTED_KEYS = ("text_config", "llm_config", "language_config", "decoder")


def config_slug(repo_id: str) -> str:
    """`Qwen/Qwen3-8B` -> `Qwen--Qwen3-8B`. A file name, never a path.

    Every character that is not a letter, digit, dot, dash or underscore
    collapses to `--`, so a repo id cannot spell a separator, a drive letter or
    `..` no matter what it contains.
    """
    return _SLUG_BAD.sub("--", str(repo_id).strip().strip("/")) or "unnamed"


def config_path(repo_id: str, root: Path | None = None) -> Path:
    base = MODEL_CONFIG_ROOT if root is None else Path(root)
    return base / f"{config_slug(repo_id)}.json"


def store_model_config(
    repo_id: str,
    config: dict[str, Any],
    *,
    revision: str | None = None,
    url: str | None = None,
    parameters_total: int | None = None,
    parameters_source: str | None = None,
    root: Path | None = None,
) -> Path:
    """Keep one `config.json` with a note of where it came from.

    The config is stored **verbatim**, not reduced to the five fields the
    estimator happens to need today. A reduction is a transcription, and a
    transcription is the step at which a number stops being the model's and
    starts being ours.
    """
    envelope = {
        "repo_id": str(repo_id),
        "revision": revision,
        "url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parameters_total": parameters_total,
        "parameters_source": parameters_source,
        "config": config,
    }
    path = config_path(repo_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def load_model_config(
    repo_id: str, root: Path | None = None
) -> dict[str, Any] | None:
    """The stored envelope for `repo_id`, or `None`. Never raises, never fetches.

    Deliberately offline. This is called from a request path, and a request
    that reaches out to the Hub is a request that hangs when the Hub is down -
    which is the state an offline harness is supposed to survive rather than
    inherit. Warming the cache is `app/tools/models.py`'s job.
    """
    path = config_path(repo_id, root)
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(envelope, dict) or not isinstance(envelope.get("config"), dict):
        return None
    return envelope


def _first_int(mapping: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, bool):  # `True` is an int in Python and is not one here
            continue
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, float) and value > 0 and float(value).is_integer():
            return int(value)
    return None


def decoder_config(config: dict[str, Any]) -> dict[str, Any]:
    """The part of a config that describes the text decoder.

    A vision-language config keeps the decoder under `text_config` and the
    projector at the top level, so reading layers from the top level gets the
    wrong model. Merged, not substituted: `vocab_size` frequently stays up top.
    """
    for key in _NESTED_KEYS:
        nested = config.get(key)
        if isinstance(nested, dict) and _first_int(nested, _LAYER_KEYS):
            merged = dict(config)
            merged.update(nested)
            return merged
    return config


def geometry_from_config(
    config: dict[str, Any],
    *,
    source: str = "config.json",
    provenance: Provenance = "measured",
) -> ModelGeometry | None:
    """Parse a `config.json` into the shape the KV-cache term needs.

    Returns `None` rather than a partly-filled guess. Four fields are required
    and each one is required for a reason:

    * **layers**, **heads** and **hidden size** - the cache is per layer, per
      head, and `head_dim` falls out of hidden size when the config does not
      state it directly.
    * **`vocab_size`** - not because the cache needs it, but because a config
      without one is not an autoregressive text decoder. `google/vit-base` has
      layers, heads and a hidden size, and no KV cache at all; computing one
      for it would produce a confident number describing nothing. The fourth
      verdict exists for exactly that case, so this hands it back.

    `num_key_value_heads` is absent on every pre-GQA model, and there the
    honest fallback is `num_attention_heads` - that *is* multi-head attention's
    definition, not a guess about it.
    """
    if not isinstance(config, dict):
        return None
    body = decoder_config(config)

    layers = _first_int(body, _LAYER_KEYS)
    hidden = _first_int(body, _HIDDEN_KEYS)
    heads = _first_int(body, _HEAD_KEYS)
    vocab = _first_int(body, ("vocab_size",))
    if not (layers and hidden and heads and vocab):
        return None

    head_dim = _first_int(body, ("head_dim",))
    if head_dim is None:
        if hidden % heads:
            return None
        head_dim = hidden // heads

    return ModelGeometry(
        num_hidden_layers=layers,
        num_key_value_heads=_first_int(body, _KV_HEAD_KEYS) or heads,
        head_dim=head_dim,
        vocab_size=vocab,
        hidden_size=hidden,
        num_attention_heads=heads,
        tie_word_embeddings=body.get("tie_word_embeddings"),
        provenance=provenance,
        source=source,
    )


def geometry_for(repo_id: str, root: Path | None = None) -> ModelGeometry | None:
    """Real geometry for a repo, from the stored config. `None` when unread."""
    envelope = load_model_config(repo_id, root)
    if envelope is None:
        return None
    revision = envelope.get("revision")
    source = f"config.json of {envelope.get('repo_id') or repo_id}"
    if revision:
        source = f"{source} at {revision}"
    return geometry_from_config(envelope["config"], source=source)


def parameters_b_for(
    repo_id: str, root: Path | None = None
) -> tuple[float | None, str | None]:
    """Exact parameter count in billions, from the safetensors index.

    Never parsed out of the model name. `Qwen/Qwen3-8B` holds 8,190,735,360
    parameters, so the name understates it by 190 million, and a name is not a
    measurement even when it happens to be close.
    """
    envelope = load_model_config(repo_id, root)
    if envelope is None:
        return None, None
    total = envelope.get("parameters_total")
    if not isinstance(total, int) or isinstance(total, bool) or total <= 0:
        return None, None
    source = envelope.get("parameters_source") or "safetensors index"
    revision = envelope.get("revision")
    if revision:
        source = f"{source} at {revision}"
    return round(total / 1e9, 3), source


#: SIX BYTES PER LOGIT, NOT FOUR, AND THE FOURTH IS NOT THE WHOLE STORY.
#:
#: This was 4 - the width of the fp32 tensor the loss is computed in - and it
#: undercounted by a third of the logits term, which on a 152k-vocabulary model
#: at sequence 2048 is 0.58 GiB.
#:
#: `transformers/loss/loss_utils.py`, `ForCausalLMLoss`:
#:
#:     # Upcast to float if we need to compute the loss to avoid potential
#:     # precision issues
#:     logits = logits.float()
#:
#: The fp16 tensor is the caller's argument and the caller still holds it, so
#: `.float()` allocates a second tensor rather than replacing the first. Both
#: are resident across the loss: 2 + 4.
#:
#: Read out of `recipes/hf-peft-dpo/.venv` rather than recalled, because a
#: constant that moves every feasibility verdict in this repo should be changed
#: against the source it is a fact about.
#: 2026-09-10: SIX WAS A CORRECT READING COUNTED INCOMPLETELY. The fp16
#: original and the fp32 upcast are two of the tensors the loss holds across a
#: step, not all of them, and reading the source told us about the two it names
#: rather than about the peak. The sweep measures the peak.
#:
#: MEASURED over eight points - four at `SmolLM2-1.7B`, four at
#: `SmolLM2-135M`, batch 1, realised == cap. The two models SHARE a vocabulary
#: of 49,152 and differ 3.56x in hidden size, which is what separates a
#: per-vocabulary term from a per-hidden one; one model could not have.
#:
#:   slope 0.742 -> activations 0.1564 + logits 0.5856 -> 12.79
#:   slope 0.618 -> activations 0.0504 + logits 0.5676 -> 12.40
#:
#: The range is carried rather than dropped, the way `DESKTOP_RESERVE_GB_RANGE`
#: is: a constant fitted to eight measurements should not read as a definition,
#: and a reader who needs to know how firm 12.6 is can see it here.
BYTES_PER_LOGIT_SWEEPS = (12.79, 12.40)
BYTES_PER_LOGIT_RANGE = (12.4, 12.8)
BYTES_PER_LOGIT = 12.6

#: THE ATTENTION MATRIX IS NOT MATERIALISED ON THIS PATH, so the term that
#: priced one is off by default.
#:
#: THE DISCRIMINATOR IS THE SHAPE OF THE SLOPE, not the size of a residual. A
#: materialised `T x T` matrix makes the per-token slope RISE with length:
#: 0.271 / 0.385 / 0.614 at full size, 0.214 / 0.271 / 0.385 halved. Measured on
#: the 1.7B sweep the adjacent slopes are 0.625, 0.742, 0.742 per 1,000 realised
#: tokens - FLAT from 512 up. Flash/SDPA attention never builds the matrix.
#:
#: KEPT BEHIND A FLAG RATHER THAN DELETED because a path that does materialise
#: it is a real path this estimator may one day be asked about, and the reason
#: it is off belongs beside the term rather than in a commit message.
#:
#: AND AN HOUR BEFORE THE SWEEP THE PROPOSAL WAS TO HALVE THIS TERM for causal
#: masking. Halving a term that should be ABSENT fitted three residuals to
#: 0.006 GiB, because one anchor was wrong in the other direction. A correction
#: that improves the fit is not evidence the correction is right.
ATTENTION_MATRIX_IS_MATERIALISED = False

#: A QUANTISED BASE IS DEQUANTISED IN BLOCKS TO BE MULTIPLIED, and the buffer
#: that holds the block is a term this estimator did not have at all.
#:
#: RE-DERIVED AGAINST THE fp32 RESIDENT (`research 497284a`), and the first
#: version of this constant was exactly twice too large. It was intercept minus
#: resident minus LoRA with resident = 0.962 - the BEFORE-call figure. Training
#: happens AFTER `prepare_model_for_kbit_training`, where the resident is 1.149
#: (`mlbuild fa5f09a`), so the term being solved for had an extra 0.187 GiB of
#: embedding in it.
#:
#:   1.7B:  1.420 - 1.149 - 0.094 = 0.177 GiB over 2,048 hidden -> 0.089
#:   135M:  0.245 - 0.157 - 0.027 = 0.061 GiB over   576 hidden -> 0.108
#:
#: Re-derived here rather than copied: 0.0885 and 0.1089, which is how the
#: hidden size in the first version was caught - 0.089 only follows at 2,048,
#: and this constant had been divided by 1,948.
#:
#: THE TWO ROWS ARE DEGENERATE AGAINST THE SWEEP AND THAT IS WHY THIS WAS
#: WRONG FOR AN HOUR. Both sweep models share a 49,152 vocabulary, so their
#: embeddings are V x H and exactly proportional to hidden size - a per-hidden
#: workspace and a per-hidden embedding correction are THE SAME FUNCTION OF THE
#: DATA. Moving 0.187 GiB between them fits all three batch rows identically to
#: the thousandth. No fit could separate them; the dtype inventory did. So a
#: test that checks this coefficient against the batch rows cannot fail for the
#: wrong split, and the row that actually pins it is the fp32 resident.
#:
#: PROVED TO BE DEQUANTISATION rather than any other fixed cost by running the
#: identical sweep WITHOUT quantisation: 0.141 against 0.044 at 135M, 6.7x once
#: the LoRA rows leave both sides. So it scales with HIDDEN SIZE and not with
#: parameter count, and it is zero when nothing is quantised.
DEQUANT_WORKSPACE_MIB_PER_HIDDEN_UNIT = 0.098
DEQUANT_WORKSPACE_MIB_RANGE = (0.089, 0.108)

#: `bitsandbytes` quantises `nn.Linear` and never `nn.Embedding`
#: (`transformers/integrations/bitsandbytes.py:316-327`), so pricing every
#: parameter at NF4 undercounts the embedding. At `Coder-1.5B` the tied tensor
#: is 233,373,696 parameters: 0.435 GiB at fp16 against 0.120 at NF4.
#:
#: THE FORK IS CLOSED AND IT CLOSED ON fp32. `mlbuild fa5f09a` took it on both
#: sides of `prepare_model_for_kbit_training` with a script rather than an ad
#: hoc inventory:
#:
#:   BEFORE  embed_tokens fp16 0.188   resident 0.962   load peak 1.594
#:   AFTER   embed_tokens fp32 0.375   resident 1.149   load peak 1.594
#:
#: EVERY TRAINING PEAK IS READ AFTER THAT CALL, so the configuration those
#: peaks describe is the fp32 one. Two lanes had disagreed by 0.435 GiB about
#: this tensor and BOTH WERE RIGHT - they were describing two different
#: moments, and the page reporting fp16 had not recorded which moment its
#: inventory was taken at. A number with real provenance could not answer a
#: question about its own order.
#:
#: COUNTED ONCE, BECAUSE THE TIE IS INTACT: 219 tensors with duplicates, 218
#: deduplicated, and 1.149 - 0.962 = +0.187 is ONE upcast rather than the
#: +0.375 a duplicate-counting sum charges. `vocab_size * hidden_size` appears
#: once below for that reason; counting it twice would be 0.188 GiB high in the
#: reassuring direction.
EMBEDDING_BYTES_PER_PARAM = 4.0
EMBEDDING_DTYPE_MEASURED_BY = (
    "mlbuild fa5f09a, both sides of prepare_model_for_kbit_training"
)
EMBEDDING_IS_NOT_QUANTISED_BY = "bitsandbytes: nn.Linear only, never nn.Embedding"

#: Formats where a dequantisation workspace exists at all.
QUANTISED_FORMATS = frozenset({"NF4", "Q4", "Q4_K_M", "Q8", "INT8"})


def is_quantised(quant: str) -> bool:
    return str(quant).upper() in QUANTISED_FORMATS


# Bits per weight. Each entry is (bits, source). Q4_K_M is the one that matters
# and the one that was wrong; the rest are definitional.
BITS_PER_WEIGHT: dict[str, tuple[float, str]] = {
    "Q4": (4.91, "Q4_K_M measured bits-per-weight, docs/ARCHITECTURE.md 4.7"),
    "Q4_K_M": (4.91, "Q4_K_M measured bits-per-weight, docs/ARCHITECTURE.md 4.7"),
    "NF4": (4.128, "QLoRA frozen NF4 base, 0.516 bytes/param, docs/ARCHITECTURE.md 4.8"),
    "Q8": (8.0, "definitional: 8-bit integer weights"),
    "INT8": (8.0, "definitional: 8-bit integer weights"),
    "FP16": (16.0, "definitional: 16-bit floats"),
    "BF16": (16.0, "definitional: 16-bit floats"),
    "FP32": (32.0, "definitional: 32-bit floats"),
}

#: A QUANTISED BLOCK CARRIES A SCALE, AND THE SCALE IS NOT FREE. These were
#: "8-bit means one byte" and "4-bit means half a byte", which is the bit width
#: and not the format. llama.cpp's `q8_0` stores 32 quants plus one fp16 scale
#: per block: 32 + 2 = 34 bytes for 32 elements, so 1.0625 bytes per element,
#: which is the 34/64 of fp16 the vault's `one-click-local` spec states. `q4_0`
#: is 16 + 2 = 18 bytes per 32 elements, 0.5625.
#:
#: MEASURED, NOT REASONED. On this card at 65,536 context, the 3.7B dense
#: granite's cache is 2,720.00 MiB (`llama_kv_cache: size = 2720.00 MiB`,
#: K q8_0 1360 + V q8_0 1360). The old table predicted 2.50 GiB = 2,560 MiB;
#: 1.0625 gives exactly 2,720.00 MiB. The error was 160 MiB at that size and
#: always in the optimistic direction, which is the wrong direction for an
#: answer to "will this fit".
KV_BYTES_PER_ELEMENT: dict[str, tuple[float, str]] = {
    "q8_0": (1.0625, "34 bytes per 32-element block: 32 quants + one fp16 scale"),
    "q4_0": (0.5625, "18 bytes per 32-element block: 16 quants + one fp16 scale"),
    "fp16": (2.0, "definitional: 16-bit KV cache elements"),
    "other": (2.0, "definitional: 16-bit KV cache elements"),
}

#: A CUDA context exists before a single weight loads.
#: docs/ARCHITECTURE.md 4.8 and docs/ROADMAP.md M2: "about 0.75 GB".
CUDA_CONTEXT_GB = 0.75

#: What a desktop compositor is already holding. docs/ARCHITECTURE.md 4.8 gives
#: a range, 0.5-1.5 GB, so the estimator carries the range and budgets against
#: the low end while naming the high end as the risk.
DESKTOP_RESERVE_GB_RANGE = (0.5, 1.5)
DESKTOP_RESERVE_GB = DESKTOP_RESERVE_GB_RANGE[0]

#: Optimizer state bytes per trainable parameter.
OPTIMIZER_BYTES_PER_PARAM: dict[str, tuple[float, str]] = {
    # AdamW keeps two fp32 moments per trainable parameter.
    "adamw": (8.0, "two fp32 moments per trainable parameter"),
    "adamw_8bit": (2.0, "8-bit optimizer cuts the term by 75%, docs/ARCHITECTURE.md 4.8"),
    "sgd": (0.0, "SGD without momentum keeps no optimizer state"),
    "sgd_momentum": (4.0, "one fp32 momentum buffer per trainable parameter"),
}

#: Fraction of parameters that carry gradients, by method.
#: LoRA and QLoRA adapter sizes vary with rank and target modules; 1% is the
#: conventional order of magnitude and is reported as an assumption, never as a
#: measurement.
TRAINABLE_FRACTION: dict[str, float] = {
    "full": 1.0,
    "lora": 0.01,
    "qlora": 0.01,
}


def bytes_per_param(quant: str) -> float:
    entry = BITS_PER_WEIGHT.get(str(quant).upper())
    if entry is None:
        raise ValueError(
            f"Invalid quantization format: {quant!r}. "
            f"Known: {', '.join(sorted(BITS_PER_WEIGHT))}"
        )
    return entry[0] / 8.0


def _kv_bytes_per_element(kv_quant: str) -> float:
    entry = KV_BYTES_PER_ELEMENT.get(str(kv_quant).lower())
    if entry is None:
        raise ValueError(
            f"Invalid KV quantization format: {kv_quant!r}. "
            f"Known: {', '.join(sorted(KV_BYTES_PER_ELEMENT))}"
        )
    return entry[0]


def kv_cache_gb(
    geometry: ModelGeometry, ctx_len: int, kv_quant: str, batch: int = 1
) -> float:
    """Bytes held by the KV cache: 2 (K and V) x layers x kv_heads x head_dim x ctx."""
    per_element = _kv_bytes_per_element(kv_quant)
    total = (
        2
        * geometry.num_hidden_layers
        * geometry.num_key_value_heads
        * geometry.head_dim
        * int(ctx_len)
        * int(batch)
        * per_element
    )
    return round(total / GIB, 2)


def overhead_gb(desktop_reserve_gb: float | None = None) -> float:
    """The two terms the old estimator omitted entirely."""
    reserve = DESKTOP_RESERVE_GB if desktop_reserve_gb is None else desktop_reserve_gb
    return round(CUDA_CONTEXT_GB + reserve, 2)


def estimate_vram(
    params_b: float | None,
    quant: str,
    ctx_len: int,
    kv_quant: str,
    *,
    geometry: ModelGeometry | None = None,
    batch: int = 1,
    desktop_reserve_gb: float | None = None,
) -> dict[str, Any]:
    """Inference memory: weights + KV cache + the overhead nobody budgets for.

    ``geometry`` is the fix for the single-architecture assumption. Without it
    ``kv_gb`` is ``None`` and ``geometry_provenance`` is ``defaulted``, which
    makes the verdict ``UNKNOWN`` rather than a confident number computed from
    another model's shape.
    """
    per_param = bytes_per_param(quant)
    assumptions: list[str] = []

    if params_b is None:
        weights_gb = None
        assumptions.append(
            "Parameter count unknown, so the weight term could not be computed."
        )
    else:
        weights_gb = round(float(params_b) * 1e9 * per_param / GIB, 2)

    if geometry is None:
        kv_gb = None
        geometry_provenance: Provenance = "defaulted"
        assumptions.append(
            "No model geometry: num_hidden_layers, num_key_value_heads and "
            "head_dim have not been read from a config.json, so the KV-cache "
            "term is not computed rather than borrowed from another model."
        )
    else:
        kv_gb = kv_cache_gb(geometry, ctx_len, kv_quant, batch)
        geometry_provenance = geometry.provenance

    over = overhead_gb(desktop_reserve_gb)
    assumptions.append(
        f"Overhead is {CUDA_CONTEXT_GB} GB of CUDA context plus "
        f"{DESKTOP_RESERVE_GB_RANGE[0]} GB of desktop reserve; a busy desktop "
        f"holds up to {DESKTOP_RESERVE_GB_RANGE[1]} GB."
    )

    total_gb = None
    if weights_gb is not None and kv_gb is not None:
        total_gb = round(weights_gb + kv_gb + over, 2)

    return {
        "weights_gb": weights_gb,
        "kv_gb": kv_gb,
        "overhead_gb": over,
        "total_gb": total_gb,
        "bytes_per_param": per_param,
        "geometry_provenance": geometry_provenance,
        "assumptions": assumptions,
    }


def estimate_training_vram(
    params_b: float | None,
    method: str,
    seq_len: int,
    batch: int = 1,
    *,
    geometry: ModelGeometry | None = None,
    base_quant: str | None = None,
    optimizer: str = "adamw",
    grad_checkpointing: bool = False,
    trainable_fraction: float | None = None,
    desktop_reserve_gb: float | None = None,
) -> dict[str, Any]:
    """Training memory. The current estimator models inference only.

    Terms, per docs/ARCHITECTURE.md 4.8 and docs/ROADMAP.md M2:

    * base weights, at NF4's 0.516 bytes per parameter for QLoRA
    * gradients, over the trainable parameters only
    * optimizer states, over the trainable parameters only
    * activations, ``s*b*h*(34 + 5*a*s/h)`` bytes per layer - usually the
      largest term and the one nobody budgets for
    * the ``s*b*vocab*4`` logits buffer
    * CUDA context and desktop reserve

    LoRA reduces gradients and optimizer states. It does **not** reduce
    activations, which is the mistake that makes people believe an adapter is
    free.
    """
    normalized = str(method).lower().replace("-", "").replace("_", "")
    if normalized not in TRAINABLE_FRACTION:
        raise ValueError(
            f"Unknown training method: {method!r}. "
            f"Known: {', '.join(sorted(TRAINABLE_FRACTION))}"
        )
    if optimizer not in OPTIMIZER_BYTES_PER_PARAM:
        raise ValueError(
            f"Unknown optimizer: {optimizer!r}. "
            f"Known: {', '.join(sorted(OPTIMIZER_BYTES_PER_PARAM))}"
        )

    assumptions: list[str] = []
    if base_quant is None:
        base_quant = "NF4" if normalized == "qlora" else "FP16"
    fraction = (
        TRAINABLE_FRACTION[normalized]
        if trainable_fraction is None
        else float(trainable_fraction)
    )
    if normalized in ("lora", "qlora") and trainable_fraction is None:
        assumptions.append(
            f"Adapter size assumed at {TRAINABLE_FRACTION[normalized]:.0%} of "
            "parameters; real rank and target modules change it."
        )

    if params_b is None:
        base_weights_gb = gradients_gb = optimizer_gb = None
        assumptions.append(
            "Parameter count unknown, so no weight, gradient or optimizer term "
            "could be computed."
        )
    else:
        params = float(params_b) * 1e9
        trainable = params * fraction
        #: THE EMBEDDING IS NOT QUANTISED. Priced at the base format it
        #: undercounts by 0.315 GiB on a 1.5B, and undercounting is the
        #: direction that invents headroom.
        embedding_params = 0.0
        if is_quantised(base_quant) and geometry is not None and geometry.vocab_size and geometry.hidden_size:
            #: TWO TENSORS WHEN THE MODEL DOES NOT TIE THEM. `lm_head` is a
            #: second `vocab x hidden` matrix on an untied model, and it is
            #: unquantised for the same reason `embed_tokens` is - it is not an
            #: `nn.Linear` that `bitsandbytes` converts.
            #:
            #: MEASURED BY THE DISAGREEMENT THIS RESOLVED. Counting one tensor
            #: for both models agreed with the sweep exactly on
            #: `Coder-1.5B` (tie_word_embeddings TRUE) and was low by almost
            #: exactly one embedding on `Coder-7B` (FALSE) - on both the fp16
            #: and the fp32 fork. A per-model error that survives a change of
            #: dtype is a structural one, not a constant.
            #:
            #: ABSENT IS READ AS TIED, because `PretrainedConfig` defaults it
            #: True. Reading absence as untied would charge for a tensor the
            #: framework says is not there.
            copies = 1 if geometry.tie_word_embeddings is not False else 2
            embedding_params = min(
                float(int(geometry.vocab_size) * int(geometry.hidden_size) * copies),
                params,
            )
        base_weights_gb = round(
            (
                (params - embedding_params) * bytes_per_param(base_quant)
                + embedding_params * EMBEDDING_BYTES_PER_PARAM
            )
            / GIB,
            2,
        )
        if embedding_params:
            assumptions.append(
                f"Embedding ({embedding_params / 1e6:.0f}M parameters) priced at "
                f"{EMBEDDING_BYTES_PER_PARAM:.0f} bytes, not at {base_quant}: "
                f"{EMBEDDING_IS_NOT_QUANTISED_BY}, and PEFT casts it to fp32 "
                "inside prepare_model_for_kbit_training - measured on both "
                f"sides ({EMBEDDING_DTYPE_MEASURED_BY}), counted once because "
                "the tie is intact."
            )
        # Gradients are held in the compute dtype, 2 bytes.
        gradients_gb = round(trainable * 2.0 / GIB, 2)
        optimizer_gb = round(
            trainable * OPTIMIZER_BYTES_PER_PARAM[optimizer][0] / GIB, 2
        )
        if normalized in ("lora", "qlora"):
            assumptions.append(
                "LoRA and QLoRA shrink gradients and optimizer states. They do "
                "not shrink activations."
            )

    activations_gb = None
    logits_gb = None
    if geometry is not None and geometry.hidden_size and geometry.num_attention_heads:
        s = int(seq_len)
        b = int(batch)
        h = int(geometry.hidden_size)
        a = int(geometry.num_attention_heads)
        per_layer_bytes = s * b * h * 34
        if ATTENTION_MATRIX_IS_MATERIALISED:
            per_layer_bytes += s * b * h * (5 * a * s / h)
        if grad_checkpointing:
            # Only one layer's activations are live at a time; the stored layer
            # inputs, 2 bytes each, remain.
            live_bytes = per_layer_bytes + s * b * h * 2 * geometry.num_hidden_layers
            assumptions.append(
                "Gradient checkpointing assumed to keep one layer live plus the "
                "per-layer inputs, at roughly +30% step time."
            )
        else:
            live_bytes = per_layer_bytes * geometry.num_hidden_layers
        activations_gb = round(live_bytes / GIB, 2)
        assumptions.append(
            "Activation formula s*b*h*34 per layer. The attention-matrix term "
            "is off: measured slopes are flat in sequence length (0.625, 0.742, "
            "0.742 per 1k tokens), and a materialised T x T matrix makes them "
            "rise. Approximate for SwiGLU and GQA."
        )
        if geometry.vocab_size:
            logits_gb = round(
                s * b * int(geometry.vocab_size) * BYTES_PER_LOGIT / GIB, 2
            )
    else:
        assumptions.append(
            "No model geometry with hidden_size and num_attention_heads, so the "
            "activation and logits terms - usually the largest - are not computed."
        )

    #: ZERO, NOT None, when nothing is quantised: there is genuinely no
    #: dequantisation buffer then, which is a measured absence rather than a
    #: term this function could not compute.
    workspace_gb = 0.0
    if is_quantised(base_quant) and geometry is not None and geometry.hidden_size:
        workspace_gb = round(
            int(geometry.hidden_size)
            * DEQUANT_WORKSPACE_MIB_PER_HIDDEN_UNIT
            * (1024 ** 2)
            / GIB,
            2,
        )
        assumptions.append(
            f"Dequantisation workspace {workspace_gb} GiB, at "
            f"{DEQUANT_WORKSPACE_MIB_PER_HIDDEN_UNIT} MiB per hidden unit "
            f"(measured {DEQUANT_WORKSPACE_MIB_RANGE[0]}-"
            f"{DEQUANT_WORKSPACE_MIB_RANGE[1]}); it scales with hidden size, "
            "not with parameter count."
        )

    over = overhead_gb(desktop_reserve_gb)
    terms = [
        base_weights_gb,
        gradients_gb,
        optimizer_gb,
        activations_gb,
        logits_gb,
        workspace_gb,
    ]
    total_gb = (
        round(sum(terms) + over, 2) if all(t is not None for t in terms) else None
    )

    geometry_provenance: Provenance = (
        geometry.provenance if geometry is not None else "defaulted"
    )

    return {
        "method": normalized,
        "base_quant": base_quant,
        "base_weights_gb": base_weights_gb,
        "gradients_gb": gradients_gb,
        "optimizer_gb": optimizer_gb,
        "activations_gb": activations_gb,
        "logits_gb": logits_gb,
        "workspace_gb": workspace_gb,
        "overhead_gb": over,
        "total_gb": total_gb,
        "trainable_fraction": fraction,
        "geometry_provenance": geometry_provenance,
        "assumptions": assumptions,
    }


def verdict(
    vram_gb: float | Field | None,
    weights_gb: float | None,
    kv_gb: float | None,
    *,
    overhead_gb: float = 0.0,
    geometry_provenance: Provenance = "declared",
) -> Dict[str, Any]:
    """FITS, SPILLS, WONT_FIT - or UNKNOWN, which is the point.

    Ruling 6, docs/ARCHITECTURE.md 4.8 and docs/DESIGN_SYSTEM.md 2.4: "a verdict
    computed from any DEFAULT input renders as UNKNOWN, not as a verdict". Pass
    a bare float and you get UNKNOWN, because a bare float carries no claim
    about where it came from. Wrap it in ``Field(8.0, "measured")`` and the
    arithmetic answers.

    The one exception is deliberate: when the weights alone exceed the card,
    WONT_FIT is certain whatever the KV cache turns out to be, so an unread
    ``config.json`` does not stop the product saying so.
    """
    vram = as_field(vram_gb)

    if not vram.is_confident:
        return _unknown(
            vram,
            "We have not measured this machine's VRAM, so we cannot answer "
            "whether this fits.",
            "hardware",
        )

    if weights_gb is None:
        return _unknown(
            vram,
            "We do not know how many parameters this model has, so we cannot "
            "size its weights.",
            "model_size",
        )

    available = float(vram.value)
    certain_gb = round(float(weights_gb) + float(overhead_gb), 2)

    if certain_gb > available:
        #: ONE EXPRESSION, USED TWICE. These were two: `needed_gb` added the
        #: uncertain term and `headroom_gb` did not, three lines apart, so a
        #: caller reading both got `vram - needed != headroom`.
        #:
        #: MEASURED 2026-09-10 on `Coder-7B` at 2,048: needed 14.10 against a
        #: reported headroom of -5.48, where `8.0 - 14.10` is `-6.10`. The
        #: refusal understated its own shortfall by 0.62 GiB - the activations
        #: term - in the direction that flatters the card. Independently
        #: corroborated: the estimator sweep's own table gives -6.10.
        #:
        #: AND `record_that_this_card_refuses` STAMPS THIS NUMBER as
        #: `training_headroom_gb`, which the diagnosis reads to tell somebody
        #: how far off they are. "NO by 5.48" and "NO by 6.10" are different
        #: sentences and only one of them is true.
        needed = certain_gb if kv_gb is None else round(certain_gb + float(kv_gb), 2)
        return {
            "verdict": "WONT_FIT",
            "needed_gb": needed,
            "vram_gb": available,
            "headroom_gb": round(available - needed, 2),
            "vram_provenance": vram.provenance,
            "geometry_provenance": geometry_provenance,
            "reason": (
                "The weights alone exceed the available VRAM, so this will not "
                "fit whatever the KV cache costs."
            ),
        }

    if kv_gb is None or geometry_provenance not in CONFIDENT_PROVENANCE:
        return _unknown(
            vram,
            "We have not read this model's config.json, so we cannot size its "
            "KV cache. The weights fit; we cannot promise the rest does.",
            "geometry",
            needed_gb=certain_gb,
        )

    needed_gb = round(certain_gb + float(kv_gb), 2)
    headroom_gb = round(available - needed_gb, 2)

    if needed_gb > available:
        verdict_str = "WONT_FIT"
    elif needed_gb <= available * 0.9:
        verdict_str = "FITS"
    else:
        verdict_str = "SPILLS"

    return {
        "verdict": verdict_str,
        "needed_gb": needed_gb,
        "vram_gb": available,
        "headroom_gb": headroom_gb,
        "vram_provenance": vram.provenance,
        "geometry_provenance": geometry_provenance,
        "reason": "",
    }


def _unknown(
    vram: Field, reason: str, missing: str, needed_gb: float | None = None
) -> Dict[str, Any]:
    return {
        "verdict": "UNKNOWN",
        "needed_gb": needed_gb,
        "vram_gb": vram.value,
        "headroom_gb": None,
        "vram_provenance": vram.provenance,
        "geometry_provenance": None,
        "missing": missing,
        "reason": reason,
    }


# The placeholder catalogue. This is not a model registry and it is not the fit
# ranker - docs/ARCHITECTURE.md 4.7 puts real ranking in M5 and deletes this.
# Until then it exists so that `recommend` can stop answering an image goal with
# a language model.
#
# `repo_id` is what changed. Each entry now names the real Hugging Face repo it
# has always meant, and everything numeric - the exact parameter count, the
# geometry the KV-cache term needs - is read from that repo's own stored
# `config.json` at call time rather than typed in here. The literals below are
# the *fallback* for a model whose config has never been read, and they say so
# in `params_source` instead of quietly reading like measurements.
MODEL_CATALOGUE: dict[str, dict[str, Any]] = {
    "Qwen3-4B": {
        "repo_id": "Qwen/Qwen3-4B",
        "params_b": None,
        "params_source": "config.json for Qwen/Qwen3-4B has not been read",
    },
    "Qwen3-8B": {
        "repo_id": "Qwen/Qwen3-8B",
        "params_b": None,
        "params_source": "config.json for Qwen/Qwen3-8B has not been read",
    },
    "google/vit-base-patch16-224": {
        "repo_id": "google/vit-base-patch16-224",
        "params_b": None,
        "params_source": "not stated in the model id; config.json not read",
    },
    "LightGBM / XGBoost": {
        "repo_id": None,
        "params_b": None,
        "params_source": "gradient-boosted trees do not run on the GPU",
    },
}

IMAGE_WORDS = ("image", "images", "vision", "photo", "picture", "cv")
TABULAR_WORDS = ("tabular", "table", "csv", "spreadsheet")
TEXT_WORDS = ("text", "language", "nlp", "chat", "instruction")
FINE_TUNE_WORDS = ("fine-tune", "finetune", "fine tune")


def infer_data_kind(goal: str) -> tuple[str, Provenance]:
    """Guess the data kind from the goal text, and say that it was a guess."""
    normalized = str(goal or "").casefold()
    for word in IMAGE_WORDS:
        if word in normalized:
            return "image", "inferred"
    for word in TABULAR_WORDS:
        if word in normalized:
            return "tabular", "inferred"
    return "text", "defaulted"


def normalize_data_kind(data_kind: str | None) -> str | None:
    if data_kind is None:
        return None
    normalized = str(data_kind).casefold().strip()
    if not normalized or normalized == "unspecified":
        return None
    for word in IMAGE_WORDS:
        if word in normalized:
            return "image"
    for word in TABULAR_WORDS:
        if word in normalized:
            return "tabular"
    for word in TEXT_WORDS:
        if word in normalized:
            return "text"
    return normalized


def recommend(
    goal: str,
    vram_gb: float | Field | None,
    data_kind: str | None = None,
) -> Dict[str, Any]:
    """Pick a starting point. Routes on the data kind first, then the goal.

    The defect: this function never received ``data_kind``, so "fine-tune an
    image classifier" was answered with Qwen3, a language model. The data kind
    decides the model family; the goal text only decides the method.

    Interim, per docs/ARCHITECTURE.md 4.7: model selection belongs in the fit
    ranker in M5, and this function is deleted when that lands.
    """
    vram = as_field(vram_gb)
    kind = normalize_data_kind(data_kind)
    if kind is None:
        kind, kind_provenance = infer_data_kind(goal)
    else:
        kind_provenance = "declared"

    normalized_goal = str(goal or "").casefold().strip()
    wants_fine_tune = any(term in normalized_goal for term in FINE_TUNE_WORDS)

    if kind == "image":
        model = "google/vit-base-patch16-224"
        result = {
            "model": model,
            "quant": "FP16",
            "method": "full fine-tune" if wants_fine_tune else "inference-only",
            "reason": (
                "Image data, so this is a vision model rather than a language "
                "model. VRAM is not the binding constraint at this size."
            ),
        }
    elif kind == "tabular":
        model = "LightGBM / XGBoost"
        result = {
            "model": model,
            "quant": "n/a",
            "method": "gradient boosting",
            "reason": (
                "Tabular data. Gradient-boosted trees are the strong baseline "
                "here and need no VRAM at all; train the deep model only after "
                "this one has been beaten."
            ),
        }
    elif wants_fine_tune:
        enough_vram = vram.value is not None and float(vram.value) >= 12
        model = "Qwen3-8B" if enough_vram else "Qwen3-4B"
        result = {
            "model": model,
            "quant": "Q4",
            "method": "LoRA" if enough_vram else "QLoRA",
            "reason": (
                "VRAM sufficient for larger model"
                if enough_vram
                else "VRAM requirement not met for larger model"
            ),
        }
    else:
        model = "Qwen3-4B"
        result = {
            "model": model,
            "quant": "Q4",
            "method": "inference-only",
            "reason": "VRAM requirement met for inference-only mode",
        }

    catalogue = MODEL_CATALOGUE.get(result["model"], {})
    repo_id = catalogue.get("repo_id")

    # Read, not assumed. `geometry_for` returns None when this repo's
    # config.json has never been fetched, or when it has been fetched and turns
    # out not to describe an autoregressive decoder - a vision encoder has no
    # KV cache to size. Both of those keep the verdict at UNKNOWN, which is the
    # honest answer; what is no longer true is that *every* model gets it.
    geometry = geometry_for(repo_id) if repo_id else None
    params_b, params_source = (
        parameters_b_for(repo_id) if repo_id else (None, None)
    )
    if params_b is None:
        params_b = catalogue.get("params_b")
        params_source = catalogue.get("params_source", "unknown model")

    result.update(
        {
            "repo_id": repo_id,
            "data_kind": kind,
            "data_kind_provenance": kind_provenance,
            "vram_provenance": vram.provenance,
            "params_b": params_b,
            "params_source": params_source,
            "geometry": geometry,
            "geometry_source": None if geometry is None else geometry.source,
        }
    )
    return result


# ---------------------------------------------------------------------------
# WHERE, AND WHAT IT WOULD COST. Answered from the machine and the job.
#
# `rent_advice` used to be three `if` branches over a number the caller passed
# in, and it read like a recommendation because it named a card and a price. It
# was neither: it never looked at the machine, it never looked at the job, and
# the price had no date on it that a reader could act on. The table below is the
# same three rows - no row has been added, because adding a row means typing a
# price nobody here measured - but the three things that were missing are now
# said out loud on every answer:
#
#   * the figure is INDICATIVE, not a quote and not a measurement;
#   * it is DATED, and the answer says how old it is today;
#   * the HOURS are UNKNOWN, so the total is UNKNOWN, and no multiplication is
#     performed. `docs/THE_PROPOSAL_LOOP.md`: "A proposal that says 'I do not
#     know how long this takes, let me run it on 1% and find out' is worth more
#     than one that guesses."

#: Rented GPUs, smallest first. `usd_per_hour` is an indicative list price and
#: is never stamped `measured` anywhere in this module.
RENT_TABLE: tuple[dict[str, Any], ...] = (
    {"gpu": "RTX 4090", "vram_gb": 24, "usd_per_hour": 0.60},
    {"gpu": "A6000", "vram_gb": 48, "usd_per_hour": 0.90},
    {"gpu": "A100 80GB", "vram_gb": 80, "usd_per_hour": 1.80},
)

#: When these prices were written down. Kept as a date rather than as the words
#: "Aug 2026" inside a sentence, so an answer can compute how stale it is
#: instead of leaving the reader to notice.
RENT_TABLE_AS_OF = "2026-08-01"
RENT_TABLE_SOURCE = "RunPod list prices, transcribed by hand"

#: The one sentence every price in this module is wrapped in.
PRICE_HONESTY = (
    "Indicative and dated. This is a list price transcribed from "
    f"{RENT_TABLE_SOURCE} as of {RENT_TABLE_AS_OF}; nothing in this harness "
    "measured it, no quote was obtained, and spot prices move. Treat it as the "
    "order of magnitude and get a real quote before committing."
)

#: What the harness does not know about a training run's duration, in the one
#: shape `docs/THE_PROPOSAL_LOOP.md` sanctions. `app/tools/propose.py` says the
#: same thing about a build step; this says it about a training run, and both
#: say it because nothing in this product stores how long anything took.
WALL_CLOCK_UNKNOWN = {
    "value": None,
    "provenance": "UNKNOWN",
    "why": (
        "nothing in this harness has recorded how long a training step takes on "
        "this machine, on data this size, with this model - so there is no "
        "measurement to derive hours from and any figure here would be invented"
    ),
    "find_out_by": (
        "run the recipe on 1% of the data and time it, then multiply by 100. "
        "That is one short run and it replaces a guess with a measurement."
    ),
}


def price_age_days(today: str | None = None) -> int | None:
    """How many days old the rental prices are. `None` if the date will not parse."""
    try:
        recorded = datetime.fromisoformat(RENT_TABLE_AS_OF)
        now = (
            datetime.fromisoformat(today)
            if today
            else datetime.now(timezone.utc).replace(tzinfo=None)
        )
    except (TypeError, ValueError):
        return None
    if recorded.tzinfo is not None:
        recorded = recorded.replace(tzinfo=None)
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    return max(0, (now - recorded).days)


def rent_advice(needed_gb: float, *, today: str | None = None) -> Dict[str, Any]:
    """The smallest rented card that holds `needed_gb`, and what it costs to say so.

    The signature is unchanged and so are the three rows, because the fix here
    was never a bigger table. What changed is that the answer now carries its
    own provenance: `price_provenance` is `indicative` and there is no code path
    in this module that makes it anything else.
    """
    try:
        needed = float(needed_gb)
    except (TypeError, ValueError):
        needed = float("inf")

    row = next((r for r in RENT_TABLE if r["vram_gb"] >= needed), None)
    over_the_table = row is None
    if row is None:
        row = RENT_TABLE[-1]

    age = price_age_days(today)
    result = {
        "gpu": row["gpu"],
        "vram_gb": row["vram_gb"],
        "usd_per_hour": row["usd_per_hour"],
        "price_provenance": "indicative",
        "priced_as_of": RENT_TABLE_AS_OF,
        "price_age_days": age,
        "price_source": RENT_TABLE_SOURCE,
        "note": PRICE_HONESTY,
        "hours": dict(WALL_CLOCK_UNKNOWN),
        "total_usd": None,
        "why_no_total": (
            "hours x price is the only arithmetic here and the hours are "
            "UNKNOWN, so there is no total to show. Multiplying an indicative "
            "price by an invented duration would produce the most trustworthy-"
            "looking number on the page and the least true one."
        ),
    }
    if over_the_table:
        result["note_on_size"] = (
            f"{needed:.2f} GB is more than the largest single card in this "
            f"table ({RENT_TABLE[-1]['vram_gb']} GB), so this row is the top of "
            "what is priced here rather than a card that holds the job. A run "
            "this size is multi-GPU, and this harness has no multi-GPU prices."
        )
    return result


# ---------------------------------------------------------------------------
# CAN THIS MACHINE TRAIN THIS? A yes or a no, with the arithmetic shown.
#
# THIS IS THE QUESTION THE GATES WERE NEVER ABOUT. The five gates ask whether
# somebody SHOULD train - is there an eval set, is there a measured baseline,
# was the prompt exhausted, was retrieval considered, was a cheaper model
# considered. Not one of those five is an input to the arithmetic below, and
# not one of them could be: whether an 8 GB card holds a 7B model is decided by
# the card's memory and the model's geometry and by nothing else.
#
# So the function below reads a measured VRAM figure and a real `config.json`
# and answers. It has no access to a gate, it produces no outcome id, and the
# word `verdict` does not appear in what it returns - the diagnosis engine owns
# that word, and a feasibility answer that borrowed it would be one rename away
# from looking like a decision it is not entitled to make.

#: What `can_train` answers with. Three words, because Max asked for three:
#: "can we train - yes or no", and UNKNOWN for when the geometry cannot be read.
ANSWERS = ("YES", "NO", "UNKNOWN")

#: `verdict()` speaks in four fit words. This is how they become an answer.
#: SPILLS maps to NO deliberately: it means the job lands inside the card with
#: less than 10% to spare, and the estimator has already budgeted the desktop
#: reserve at the BOTTOM of its 0.5-1.5 GB range. A "yes" there is a yes that
#: OOMs on the first long batch, and the person who acted on it has lost a day.
_ANSWER_FOR_FIT = {"FITS": "YES", "SPILLS": "NO", "WONT_FIT": "NO", "UNKNOWN": "UNKNOWN"}

#: Sequence lengths are searched on this grid. 64 because attention kernels are
#: happier on a multiple of 64 and because a token count quoted to the unit
#: would imply a precision the search does not have.
_SEQ_STEP = 64


def _term(name: str, gb: float | None, source: str) -> dict[str, Any]:
    return {"term": name, "gb": gb, "source": source}


def training_terms(
    estimate: Mapping[str, Any], *, optimizer: str, batch: int, seq_len: int
) -> list[dict[str, Any]]:
    """The arithmetic, one line per term, each line saying where it came from.

    This is the "with the arithmetic shown" half of the answer. It is built from
    the estimate rather than recomputed, so the lines cannot disagree with the
    total they add up to.
    """
    quant = str(estimate.get("base_quant") or "")
    bits = BITS_PER_WEIGHT.get(quant.upper())
    fraction = estimate.get("trainable_fraction")
    opt_entry = OPTIMIZER_BYTES_PER_PARAM.get(optimizer)
    return [
        _term(
            "base weights",
            estimate.get("base_weights_gb"),
            f"{quant} at {bits[0]} bits per weight - {bits[1]}"
            if bits
            else "parameter count x bytes per weight",
        ),
        _term(
            "gradients",
            estimate.get("gradients_gb"),
            f"2 bytes per trainable parameter, over {fraction:.1%} of the model"
            if isinstance(fraction, float)
            else "2 bytes per trainable parameter",
        ),
        _term(
            "optimizer state",
            estimate.get("optimizer_gb"),
            f"{optimizer}: {opt_entry[0]} bytes per trainable parameter - {opt_entry[1]}"
            if opt_entry
            else optimizer,
        ),
        _term(
            "activations",
            estimate.get("activations_gb"),
            f"s*b*h*34 per layer at s={seq_len}, b={batch}, from "
            "this model's own config.json; no attention-matrix term, because "
            "the measured slope is flat in sequence length"
            + (
                ", with gradient checkpointing"
                if any("checkpointing" in a for a in estimate.get("assumptions") or [])
                else ""
            ),
        ),
        _term(
            "logits buffer",
            estimate.get("logits_gb"),
            f"s*b*vocab*{BYTES_PER_LOGIT} bytes at s={seq_len}, b={batch}, "
            "vocabulary from this model's own config.json; the width is "
            f"measured over two sweeps ({BYTES_PER_LOGIT_SWEEPS[0]} and "
            f"{BYTES_PER_LOGIT_SWEEPS[1]}), not read off a source file",
        ),
        _term(
            "dequantisation workspace",
            estimate.get("workspace_gb"),
            f"{DEQUANT_WORKSPACE_MIB_PER_HIDDEN_UNIT} MiB per hidden unit "
            f"(measured {DEQUANT_WORKSPACE_MIB_RANGE[0]}-"
            f"{DEQUANT_WORKSPACE_MIB_RANGE[1]}), scaling with hidden size and "
            "not with parameter count; zero when the base is not quantised",
        ),
        _term(
            "CUDA context",
            CUDA_CONTEXT_GB,
            "a CUDA context exists before a single weight loads, "
            "docs/ARCHITECTURE.md 4.8",
        ),
        _term(
            "desktop reserve",
            DESKTOP_RESERVE_GB,
            f"what the compositor already holds, budgeted at the low end of the "
            f"{DESKTOP_RESERVE_GB_RANGE[0]}-{DESKTOP_RESERVE_GB_RANGE[1]} GB range",
        ),
    ]


def _fit_at(
    params_b: float | None,
    geometry: ModelGeometry | None,
    vram: Field,
    *,
    method: str,
    seq_len: int,
    batch: int,
    optimizer: str,
    grad_checkpointing: bool,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """One (estimate, fit) pair at one sequence length.

    THE LOGITS BUFFER IS INSIDE THE CERTAIN TERMS, and that is the one place
    this differs from `app/tools/models.py:fit_of`. The ranker passes weights,
    gradients and optimizer state as the certain sum and the activations as the
    uncertain one, and the logits buffer - `s*b*vocab*4`, which is 1.16 GB for
    an 8B model at 2,048 tokens - reaches neither, so it is computed into
    `total_gb`, displayed, and then left out of the comparison that decides the
    word. That is survivable in a ranker, where the figure is explicitly a
    floor and the job is to sort candidates. It is not survivable in a yes/no:
    the answer must be computed from the same total the answer displays.
    """
    estimate = estimate_training_vram(
        params_b,
        method,
        seq_len,
        batch,
        geometry=geometry,
        optimizer=optimizer,
        grad_checkpointing=grad_checkpointing,
    )
    #: THE WORKSPACE IS CERTAIN AND IT IS HERE FOR THE REASON THE DOCSTRING
    #: ABOVE GIVES. Adding `workspace_gb` to `terms` and to the returned dict
    #: puts it in the number the answer DISPLAYS; this list is the number the
    #: answer is COMPUTED from, and a term in one and not the other is exactly
    #: the logits-buffer defect this function was written to close. Measured
    #: 2026-09-10: with the row in `terms` alone the 7B read 10.64 needing
    #: against a 12.07 total - the tool disagreeing with itself by 1.43 GiB.
    #:
    #: It belongs in CERTAIN rather than beside the activations because it is
    #: fixed in sequence length: a buffer sized by hidden units does not grow
    #: with the example, which is also what keeps `largest_seq_len_that_fits`
    #: monotonic.
    certain = [
        estimate["base_weights_gb"],
        estimate["gradients_gb"],
        estimate["optimizer_gb"],
        estimate["logits_gb"],
        estimate["workspace_gb"],
    ]
    certain_gb = None if any(t is None for t in certain) else round(sum(certain), 2)
    fit = verdict(
        vram,
        certain_gb,
        estimate["activations_gb"],
        overhead_gb=estimate["overhead_gb"],
        geometry_provenance=estimate["geometry_provenance"],
    )
    return estimate, fit


def largest_seq_len_that_fits(
    params_b: float | None,
    geometry: ModelGeometry | None,
    vram: Field,
    *,
    method: str = "qlora",
    batch: int = 1,
    optimizer: str = "adamw",
    grad_checkpointing: bool = True,
    ceiling: int = 32768,
) -> int | None:
    """The longest example this machine can train on, or `None` if none can.

    Not a new estimate and not a new constant: the same function evaluated at
    different sequence lengths until it stops answering FITS. Every term above
    except the two activation-driven ones is flat in `seq_len`, so the total is
    monotonic in it and a bisection is exact on the grid.

    This is what turns a "no" into something a person can act on. "Qwen3-8B
    will not fit" and "Qwen3-8B fits up to 1,024 tokens per example" are the
    same arithmetic and only the second one is an answer.
    """
    if params_b is None or geometry is None or not vram.is_confident:
        return None

    def fits(seq_len: int) -> bool:
        _, fit = _fit_at(
            params_b,
            geometry,
            vram,
            method=method,
            seq_len=seq_len,
            batch=batch,
            optimizer=optimizer,
            grad_checkpointing=grad_checkpointing,
        )
        return fit["verdict"] == "FITS"

    if not fits(_SEQ_STEP):
        return None
    low, high = _SEQ_STEP, max(_SEQ_STEP, int(ceiling))
    if fits(high):
        return high
    while high - low > _SEQ_STEP:
        middle = ((low + high) // 2 // _SEQ_STEP) * _SEQ_STEP
        if middle <= low:
            break
        if fits(middle):
            low = middle
        else:
            high = middle
    return low


def can_train(
    *,
    vram: float | Field | None,
    params_b: float | None,
    geometry: ModelGeometry | None = None,
    repo_id: str | None = None,
    method: str = "qlora",
    seq_len: int = 2048,
    batch: int = 1,
    optimizer: str = "adamw",
    grad_checkpointing: bool = True,
    params_source: str | None = None,
) -> Dict[str, Any]:
    """Can this machine train this model? YES, NO or UNKNOWN, with the sums.

    Nothing in this function reads a gate, an eval set, a baseline or a
    diagnosis outcome, and that is the point rather than an omission. See the
    section header above.
    """
    vram_field = as_field(vram)
    estimate, fit = _fit_at(
        params_b,
        geometry,
        vram_field,
        method=method,
        seq_len=int(seq_len),
        batch=int(batch),
        optimizer=optimizer,
        grad_checkpointing=grad_checkpointing,
    )
    answer = _ANSWER_FOR_FIT.get(fit["verdict"], "UNKNOWN")

    headroom = fit.get("headroom_gb")
    available = vram_field.value

    # WHAT THE JOB NEEDS DOES NOT DEPEND ON WHAT THE CARD HAS. `verdict()`
    # returns `needed_gb: None` when it cannot vouch for the VRAM, which is
    # right for the comparison and wrong for the figure: the sum of the seven
    # terms is the same number whether or not `nvidia-smi` answered. A machine
    # with no readable GPU should still be told "this job wants 8.56 GB", so the
    # total falls back to the estimate's own rather than to nothing.
    needed = fit.get("needed_gb")
    if needed is None:
        needed = estimate.get("total_gb")

    if answer == "UNKNOWN":
        because = fit.get("reason") or "Something this answer needs has not been read."
    elif fit["verdict"] == "FITS":
        because = (
            f"{needed} GB is needed and this machine has {available} GB, "
            f"leaving {headroom} GB spare. That is memory arithmetic: it says "
            "the card can hold this, not that a serving runtime will decide to "
            "put all of it there."
        )
    elif fit["verdict"] == "SPILLS":
        because = (
            f"{needed} GB is needed against {available} GB. It lands inside the "
            f"card with {headroom} GB spare, which is under a tenth of it - and "
            f"the desktop reserve in that sum is budgeted at "
            f"{DESKTOP_RESERVE_GB_RANGE[0]} GB when a busy desktop holds up to "
            f"{DESKTOP_RESERVE_GB_RANGE[1]} GB. There is no room for the "
            "difference, so this is a no rather than a tight yes."
        )
    else:
        because = (
            f"{needed} GB is needed and this machine has {available} GB. "
            f"It is short by {round(float(needed) - float(available), 2)} GB."
            if isinstance(needed, (int, float)) and isinstance(available, (int, float))
            else fit.get("reason", "")
        )

    longest = largest_seq_len_that_fits(
        params_b,
        geometry,
        vram_field,
        method=method,
        batch=batch,
        optimizer=optimizer,
        grad_checkpointing=grad_checkpointing,
    )

    return {
        "question": "can this machine train this model",
        "answer": answer,
        "fit": fit["verdict"],
        "because": because,
        # Only where the answer is that it fits. On a WONT_FIT nothing is going
        # to be placed anywhere, and on an UNKNOWN the caveat would compete
        # with the thing that actually needs reading.
        **(
            {"placement_is_not_memory": PLACEMENT_IS_NOT_MEMORY}
            if fit["verdict"] in {"FITS", "SPILLS"}
            else {}
        ),
        "repo_id": repo_id,
        "method": str(method).lower(),
        "seq_len": int(seq_len),
        "batch": int(batch),
        "optimizer": optimizer,
        "grad_checkpointing": bool(grad_checkpointing),
        "needed_gb": needed,
        "vram_gb": available,
        "headroom_gb": headroom,
        "arithmetic": training_terms(
            estimate, optimizer=optimizer, batch=int(batch), seq_len=int(seq_len)
        ),
        "total_gb": estimate.get("total_gb"),
        "longest_example_that_fits": longest,
        "params_b": params_b,
        "params_source": params_source,
        "provenance": {
            "vram_gb": vram_field.provenance,
            "vram_source": vram_field.source,
            "geometry": estimate["geometry_provenance"],
            "geometry_source": None if geometry is None else geometry.source,
            "params_b": "measured" if params_source else "defaulted",
        },
        "missing": fit.get("missing"),
        "assumptions": estimate["assumptions"],
        "this_is_not_a_recommendation": (
            "This answers CAN, from the memory on this card and the geometry in "
            "this model's config.json. It does not answer SHOULD. Whether "
            "training is the right thing to do is the diagnosis, it needs an "
            "eval set and a measured baseline, and nothing here can open one of "
            "those gates or stand in for it."
        ),
    }


# ---------------------------------------------------------------------------
# WHERE: LOCAL, A RENTED VM, OR YOUR OWN HARDWARE.

#: The three places a training run can happen, plus the fourth word for when we
#: cannot say. These are Max's own words - "local, vm, data center" - with the
#: third one named for the property that actually distinguishes it rather than
#: for the room it is in: hardware you own and control. A bigger card in the
#: same box, a second machine, and a box in your own data centre are one answer
#: here, because what separates them from RENTED_VM is that the data never
#: leaves your custody - which is the only thing the constraint asks about.
PLACES = ("LOCAL", "RENTED_VM", "OWN_HARDWARE", "UNKNOWN")

#: Fact values that mean a hosted third party is not an option. `privacy` is a
#: declared fact of the diagnosis ledger and these are three of its four enum
#: members; the fourth, `public_ok`, is the only one that does not rule cloud
#: out. Read from the ledger's vocabulary rather than invented here, which is
#: why a compliance constraint is a FACT the harness can hold rather than a
#: sentence somebody typed into a chat box.
CLOUD_IS_RULED_OUT_BY = ("no_third_party_api", "on_prem_only", "regulated")


def where_to_train(
    answer_here: Mapping[str, Any],
    *,
    privacy: str | None = None,
    can_rent_cloud: bool | None = None,
    today: str | None = None,
) -> Dict[str, Any]:
    """Local, a rented VM, or your own hardware - decided by the machine and the job.

    `answer_here` is a `can_train` result. That is the whole input from the
    machine's side, and it is why this cannot drift from the yes/no: the two
    answers are computed from one arithmetic.

    A compliance constraint is the other input and it changes the answer rather
    than annotating it. Somebody who cannot send data to a hosted model has no
    RENTED_VM option at all, so a table of hourly prices is not an answer to
    their question and offering one is worse than saying nothing.
    """
    ruled_out_by_privacy = str(privacy or "") in CLOUD_IS_RULED_OUT_BY
    ruled_out_by_answer = can_rent_cloud is False
    cloud_available = not (ruled_out_by_privacy or ruled_out_by_answer)

    fits_here = answer_here.get("answer") == "YES"
    unknown_here = answer_here.get("answer") == "UNKNOWN"
    needed = answer_here.get("needed_gb")
    longest = answer_here.get("longest_example_that_fits")

    reasons: list[str] = []
    if ruled_out_by_privacy:
        reasons.append(
            f"privacy is {privacy!r}, which forbids sending this data to a "
            "third-party host, so a rented VM and a hosted API are both out. "
            "This is a fact in the ledger, not a preference."
        )
    if ruled_out_by_answer:
        reasons.append(
            "can_rent_cloud is false - you have said renting is not available "
            "to you - so the only options are machines you control."
        )

    rent: Dict[str, Any] | None = None
    if cloud_available and isinstance(needed, (int, float)):
        rent = rent_advice(float(needed), today=today)

    if unknown_here:
        place = "UNKNOWN"
        say = (
            "I cannot say where yet, because I cannot say whether it runs "
            "anywhere: " + str(answer_here.get("because") or "")
        )
    elif fits_here:
        place = "LOCAL"
        say = (
            f"Local, on this machine. {answer_here.get('because')} The card is "
            "already paid for, the data never leaves the building, and there is "
            "nothing to rent."
        )
    elif cloud_available:
        place = "RENTED_VM"
        say = (
            f"Not on this machine - {answer_here.get('because')} A rented GPU is "
            "the cheapest way to find out whether the trained model is worth "
            "anything, because you pay for hours rather than for a card."
        )
    else:
        place = "OWN_HARDWARE"
        say = (
            f"Not on this machine - {answer_here.get('because')} And renting is "
            "ruled out, so the honest options are hardware you own or a smaller "
            "job. A bigger card in this box is the smallest change; a second "
            "machine, or a box in your own data centre, is the next. All three "
            "keep the data inside the building, which is the constraint that "
            "removed the rented option."
        )

    smaller_job: list[str] = []
    if not fits_here and not unknown_here:
        if longest:
            smaller_job.append(
                f"train on examples of at most {longest} tokens - the same model "
                f"and the same method fit at that length on this card. Measure "
                "your own data's length first; profile_dataset does that."
            )
        if str(answer_here.get("method")).lower() != "qlora":
            smaller_job.append(
                "switch to QLoRA - it holds the base model at about half a byte "
                "per parameter instead of two, which is the largest single term "
                "in the sum above."
            )
        smaller_job.append(
            "pick a smaller base model - find_models ranks what fits this card "
            "for this job rather than what is popular."
        )

    return {
        "question": "where should this train - local, a rented VM, or your own hardware",
        "answer": place,
        "say": say,
        "places": list(PLACES),
        "cloud_available": cloud_available,
        "cloud_ruled_out_because": reasons,
        "fits_on_this_machine": answer_here.get("answer"),
        "needed_gb": needed,
        "vram_gb": answer_here.get("vram_gb"),
        "rent": rent,
        "cost": {
            "usd_per_hour": None if rent is None else rent["usd_per_hour"],
            "price_provenance": None if rent is None else rent["price_provenance"],
            "hours": dict(WALL_CLOCK_UNKNOWN),
            "total_usd": None,
            "note": (
                PRICE_HONESTY
                if rent is not None
                else "No rental price is quoted, because renting is not an "
                "option here and a price for something you cannot use is noise."
            ),
        },
        "a_smaller_job_that_would_fit": smaller_job,
        "this_is_not_a_recommendation": (
            "This answers WHERE, given that a run happens. It does not answer "
            "whether one should. That is the diagnosis and it has five gates in "
            "front of it."
        ),
    }
