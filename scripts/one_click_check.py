"""What would run on this machine, and what would not — made of parts we own.

    python scripts/one_click_check.py

It reads the card, the lock, the runtime and a small catalogue, and prints one
page. **It loads no model, downloads nothing, and never writes a lock.**

WHY THIS RATHER THAN PULLING AND FINDING OUT. Most people pull and find out, and
that is a fine way to learn one thing slowly. This makes one number known before
the download instead of after. It does not claim anyone needs it first.

THE FOUR LAWS IT ENFORCES ON ITSELF, each borrowed from a place they were
learned the hard way:

* **The count, with its denominator.** The first line is `measured N of M`: how
  many lines came from an instrument and how many from a default or an absence.
  A page with more defaults than measurements says so at the top rather than
  reading like a report.
* **It reads the lock and never writes one.** A check that took the card to
  tell you about the card would be the thing it is warning you about.
* **It carries a witness of what it read** — a sha256 of each config it opened —
  so a page can be checked against the files it was computed from after those
  files change.
* **A `fits` is void unless the geometry it rests on was measured.** A defaulted
  geometry prints `unknown`, never `fits`. This is the one claim registered
  before the build, because it is the one nobody can tune: the provenance COUNT
  depends on how many lines somebody writes, and this does not.

WHERE IT LIVES, and it is a deviation from the design page. That page says the
check ships beside the card owner. `card_owner/` is excluded from any public
mirror by this repository's release policy - it necessarily names one private
path - so a check whose whole audience is a person on a fresh machine would not
reach them from there. It lives in `scripts/`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

#: What a line's number is worth. `measured` came from an instrument;
#: `defaulted` from an assumption; `not found` from a thing that is not on this
#: machine; `unknown` from a question that could not be decided, which is NOT
#: the same as an answer of no.
MEASURED = "measured"
DEFAULTED = "defaulted"
NOT_FOUND = "not found"
UNKNOWN = "unknown"

#: A KV element at q8_0: 34 bytes per 32-element block, 32 quants and one fp16
#: scale. Definitional, not measured.
KV_BYTES_PER_ELEMENT = 34 / 32

#: The constant and per-window parts of llama.cpp's compute overhead, fitted on
#: eighteen measured rows on one card. Carried as a per-family constant because
#: it is measured rather than derived - and it is why a fit line near the edge
#: is a bracket rather than a verdict.
COMPUTE_OVERHEAD_MIB = 266
WINDOW_OVERHEAD_MIB_PER_1K = 2.27

#: Bits per weight for the quantisation this catalogue uses. Q4_K_M averages
#: about 4.5; it is an assumption and is labelled as one wherever it decides a
#: line.
BITS_PER_WEIGHT = 4.5


@dataclass
class Line:
    label: str
    value: str
    provenance: str
    why: str = ""


@dataclass
class Page:
    lines: list[Line] = field(default_factory=list)
    witnesses: dict = field(default_factory=dict)

    @property
    def measured(self) -> int:
        return sum(1 for line in self.lines if line.provenance == MEASURED)

    @property
    def not_measured(self) -> int:
        return len(self.lines) - self.measured

    @property
    def total(self) -> int:
        return len(self.lines)

    @property
    def first_line(self) -> str:
        return f"measured {self.measured} of {self.total}"

    @property
    def exit_code(self) -> int:
        """Always zero. A machine with no card is a fact, not a failure, and a
        check that exited non-zero for describing one would teach people to
        stop running it."""
        return 0


# ---------------------------------------------------------------------------
# The geometry, and the one rule that matters.


def geometry(config: dict) -> tuple[dict | None, str]:
    """The four numbers a KV estimate needs, or `(None, why)`.

    THE TRAP, planted case 1: a model config passed as SAVED, with the geometry
    one level down under `config`. The honest answer is that the geometry was
    not read - never that the model does not fit, which is an answer to a
    question nobody could ask.
    """
    if not isinstance(config, dict):
        return None, "geometry not read: the config is not an object"
    if "config" in config and isinstance(config["config"], dict):
        return None, (
            "geometry not read: this looks like a saved envelope with the "
            "geometry one level down - pass the config's inner object"
        )
    layers = config.get("num_hidden_layers")
    # NO FALLBACK TO THE ATTENTION HEAD COUNT. A grouped-query model has far
    # fewer KV heads than attention heads - eight against thirty-two is
    # ordinary - so substituting one for the other overstates the cache by that
    # ratio and prints a confident "does not fit" that is wrong by thousands of
    # MiB. Caught on this machine's own page: a model whose header omits
    # `head_count_kv` was reported as missing by 14,458 MiB. Missing is
    # missing.
    kv_heads = config.get("num_key_value_heads")
    hidden = config.get("hidden_size")
    heads = config.get("num_attention_heads")
    if not all(isinstance(v, int) and v > 0 for v in (layers, kv_heads, hidden, heads)):
        missing = [
            name
            for name, value in (
                ("num_hidden_layers", layers),
                ("num_key_value_heads", kv_heads),
                ("hidden_size", hidden),
                ("num_attention_heads", heads),
            )
            if not isinstance(value, int) or value <= 0
        ]
        return None, "geometry not read: " + ", ".join(missing) + " missing from the config"
    return {
        "layers": layers,
        "kv_heads": kv_heads,
        "head_dim": hidden // heads,
        "layer_types": config.get("layer_types"),
    }, ""


def attention_layers(geo: dict) -> tuple[int, str]:
    """How many layers actually hold a KV cache, and how that was decided.

    PLANTED CASE 5. A hybrid header declares `layer_types`, and only the
    attention layers hold a cache; using the dense formula over all forty would
    overstate the window by the ratio of the two. So the walk is per layer when
    the header says so, and the page says which walk it used.
    """
    kinds = geo.get("layer_types")
    if isinstance(kinds, list) and kinds:
        full = sum(1 for k in kinds if "attention" in str(k).lower())
        return full, f"per-layer walk over {len(kinds)} declared layer types, {full} attention"
    return geo["layers"], f"dense formula over all {geo['layers']} layers"


def kv_mib(geo: dict, ctx: int) -> tuple[float, str]:
    attn, how = attention_layers(geo)
    per_token = 2 * attn * geo["kv_heads"] * geo["head_dim"] * KV_BYTES_PER_ELEMENT
    return per_token * ctx / (1024 * 1024), how


def token_embedding_mib(config: dict) -> float:
    """The embedding table llama.cpp keeps on the HOST, not on the card.

    IT IS SUBTRACTED, AND LEAVING IT IN IS A 138 MiB ERROR ON AN 8 GiB CARD.
    Found by this module's own case 6: the walk overshot the bench by exactly
    `vocab_size x embedding_length` at 4.5 bits - 100,352 x 2,560 for the model
    in that case - because the weights figure counts a tensor the card never
    holds. A number that is 138 too big near the edge turns a `fits` into a
    `does not fit`, which is the direction that costs somebody a download.
    """
    vocab = config.get("vocab_size")
    hidden = config.get("hidden_size")
    if not (isinstance(vocab, int) and isinstance(hidden, int)):
        return 0.0
    return vocab * hidden * BITS_PER_WEIGHT / 8 / (1024 * 1024)


def resident_mib(config: dict, ctx: int, weights_mib: int = 0) -> float | None:
    """Predicted resident MiB at that window, or None if the geometry is not there.

    THE INSTRUMENT IS THE PER-LAYER WALK AND ITS FITTED OVERHEAD, which is what
    the fit bench predicts. It is deliberately NOT a live `ollama ps` figure:
    those are different quantities - one is a prediction validated against an
    `nvidia-smi` delta, the other is the runtime's own accounting - and reading
    a tolerance across the two measures the gap between instruments rather than
    the walk.
    """
    geo, _ = geometry(config)
    if geo is None:
        return None
    kv, _ = kv_mib(geo, ctx)
    on_the_card = weights_mib - token_embedding_mib(config)
    return round(on_the_card + kv + COMPUTE_OVERHEAD_MIB + WINDOW_OVERHEAD_MIB_PER_1K * ctx / 1024)


def a_fit_line(name: str, config: dict, ctx: int, free_mib: int | None,
               weights_mib: int = 0) -> Line:
    """Would this model at this window fit in the memory that is free?

    **A `fits` is void unless the geometry was measured.** That is the whole
    rule: a defaulted or unreadable geometry prints `unknown` and says what is
    missing, because a confident `does not fit` computed from an assumption is
    worse than no line at all - it is wrong in a way the reader cannot see.
    """
    geo, why = geometry(config)
    if geo is None:
        return Line(f"{name} at {ctx:,}", UNKNOWN, UNKNOWN, why)
    need = resident_mib(config, ctx, weights_mib)
    _, how = attention_layers(geo)
    if free_mib is None:
        return Line(
            f"{name} at {ctx:,}", UNKNOWN, UNKNOWN,
            f"needs about {need:,} MiB; free VRAM not found, so nothing can be decided ({how})",
        )
    room = free_mib - need
    if room >= 0:
        return Line(f"{name} at {ctx:,}", f"fits with {room:,} MiB to spare", MEASURED, how)
    return Line(f"{name} at {ctx:,}", f"does not fit by {abs(room):,} MiB", MEASURED, how)


# ---------------------------------------------------------------------------
# The machine, the card, the runtime.


def born_of(pid: int) -> str:
    """That process's start time, for a lock line that carries identity."""
    from scripts.take_the_card import born_utc  # noqa: PLC0415

    return born_utc(pid)


def the_card(nvidia_smi: str | None, free_mib: int | None = None) -> list[Line]:
    from app import hwdetect

    if not nvidia_smi:
        why = "not found: no nvidia-smi on this machine"
        return [
            Line("GPU", NOT_FOUND, NOT_FOUND, why),
            Line("VRAM total", NOT_FOUND, NOT_FOUND, why),
            Line("VRAM free", NOT_FOUND, NOT_FOUND, why),
        ]
    read = hwdetect.parse_nvidia_smi(nvidia_smi)
    parts = [p.strip() for p in nvidia_smi.strip().splitlines()[0].split(",")]
    total = parts[1] if len(parts) > 1 else ""
    free_line = (
        Line("VRAM free", f"{free_mib} MiB", MEASURED, "nvidia-smi --query-gpu=memory.free")
        if free_mib is not None
        else Line("VRAM free", NOT_FOUND, NOT_FOUND,
                  "not found: nvidia-smi answered for the card but not for free memory")
    )
    return [
        Line("GPU", str(read.get("gpu_name") or "unreadable"), MEASURED, "nvidia-smi"),
        Line("VRAM total", total, MEASURED, "nvidia-smi"),
        free_line,
    ]


def the_lock_line(holder: dict | None) -> Line:
    """Who holds the card, read and never written.

    PLANTED CASES 3 AND 4. A lock carrying a pid and a birth can be decided; the
    old three-field line cannot, and the answer for it is `cannot decide`, never
    `free`. A card owner that guessed liveness from a lane name would be
    inventing the fact it exists to record.
    """
    if holder is None:
        return Line("card", "free: no lock file", MEASURED, "read, never written")
    lane = holder.get("lane", "an unnamed lane")
    if not holder.get("pid") or not holder.get("born"):
        return Line(
            "card", f"held by {lane}, and whether that holder is alive cannot be decided",
            UNKNOWN,
            "the lock line carries no pid and no birth time, so liveness is not askable",
        )
    from card_owner import the_lock

    alive = the_lock.is_the_holder_alive(holder)
    if alive is None:
        return Line("card", f"held by {lane}, liveness cannot be decided", UNKNOWN,
                    "the holder's identity could not be read")
    if alive:
        return Line("card", f"held by {lane} for {holder.get('what', 'an unnamed job')}",
                    MEASURED, "read, never written")
    return Line("card", f"a stale lock from {lane}; its holder is gone", MEASURED,
                "read, never written")


def the_runtime(runtime: str | None) -> list[Line]:
    if not runtime:
        return [Line("runtime", NOT_FOUND, NOT_FOUND,
                     "not found: no local runtime answered on this machine")]
    return [Line("runtime", runtime, MEASURED, "the runtime's own version string")]


def read_nvidia_smi() -> str | None:
    from app import hwdetect

    return hwdetect.read_nvidia_smi()


def read_free_mib() -> int | None:
    """Free VRAM, from its own query.

    IT NEEDS ITS OWN, AND THAT COST A WRONG PAGE. `hwdetect`'s query is
    `name,memory.total,driver_version,compute_cap` - there is no free-memory
    column in it at all. The first version of this check read field four of
    that line and got the COMPUTE CAPABILITY, 7.5, then computed every fit
    against 7.5 MiB and printed six confident `does not fit` lines, marked
    measured, for models that plainly fit. A number read from the wrong column
    is worse than a missing one: it has the shape of an answer.
    """
    try:
        done = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    # `splitlines()` rather than splitting on an escape: this line was written
    # three times tonight with an escape that collapsed into a real newline.
    first = (done.stdout.splitlines() or [""])[0]
    digits = "".join(c for c in first if c.isdigit())
    return int(digits) if digits else None


def read_runtime() -> str | None:
    try:
        done = subprocess.run(["ollama", "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def read_lock() -> dict | None:
    """The lock as it is, parsed from the line the lanes agree on."""
    try:
        from card_owner import the_lock

        return the_lock.what_the_lock_says()
    except Exception:  # noqa: BLE001 - a lock we cannot read is not a crash
        return None


def free_mib_from(lines: list[Line]) -> int | None:
    for line in lines:
        if line.label == "VRAM free" and line.provenance == MEASURED:
            digits = "".join(c for c in line.value if c.isdigit())
            return int(digits) if digits else None
    return None


def one(page: Page, label: str) -> Line:
    """The line with that label. Raises rather than returning a blank."""
    for line in page.lines:
        if line.label == label:
            return line
    raise KeyError(f"no line labelled {label!r}; the page has {[l.label for l in page.lines]}")


def models_on_disk() -> list[str]:
    """What the runtime holds, by name. Metadata only; nothing is loaded."""
    try:
        done = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0:
        return []
    return [line.split()[0] for line in done.stdout.splitlines()[1:] if line.strip()]


def the_page(*, nvidia_smi: str | None, holder: dict | None, runtime: str | None,
             catalogue: dict, free_mib: int | None = None,
             on_disk: list[str] | None = None) -> Page:
    page = Page()
    from app import hwdetect

    page.lines.extend(the_card(nvidia_smi, free_mib))
    ram, _, ram_source = hwdetect.physical_ram_bytes()
    page.lines.append(
        Line("system RAM", f"{ram // (1024 ** 3)} GiB" if ram else NOT_FOUND,
             MEASURED if ram else NOT_FOUND, ram_source or "not found")
    )
    page.lines.append(the_lock_line(holder))
    page.lines.extend(the_runtime(runtime))

    free = free_mib
    for name, entry in catalogue.items():
        config = entry.get("config", {})
        page.lines.append(
            a_fit_line(name, config, entry.get("ctx", 65536), free, entry.get("weights_mib", 0))
        )
        if entry.get("path"):
            path = Path(entry["path"])
            if path.exists():
                page.witnesses[name] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    # WHAT THE PAGE DID NOT COVER, said by the page. The catalogue is a
    # committed snapshot of the models that were on one machine when somebody
    # wrote it, and nothing regenerates it - measured within hours of its being
    # written, a seventh model was on disk and the catalogue named six. A page
    # that quietly omits a model a person has is a page that answered a
    # narrower question than the one they asked.
    if on_disk is not None:
        named = {m for m in catalogue} | {m.split(":")[0] for m in catalogue}
        missing = [m for m in on_disk if m not in named and m.split(":")[0] not in named]
        page.lines.append(
            Line(
                "not in this catalogue",
                "none" if not missing else ", ".join(missing),
                MEASURED if not missing else UNKNOWN,
                "" if not missing
                else "on disk and not in the catalogue, so nothing above says whether "
                     "they would run; the catalogue is a snapshot and nothing regenerates it",
            )
        )
    return page


def render(page: Page) -> str:
    out = [page.first_line, ""]
    width = max((len(l.label) for l in page.lines), default=0)
    for line in page.lines:
        tail = f"   [{line.provenance}] {line.why}" if line.provenance != MEASURED else ""
        out.append(f"  {line.label.ljust(width)}  {line.value}{tail}")
    if page.witnesses:
        out.append("")
        out.append("  read:")
        for name, digest in sorted(page.witnesses.items()):
            out.append(f"    {name}  sha256 {digest}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="What would run on this machine.")
    parser.add_argument("--json", action="store_true", help="the page as JSON")
    args = parser.parse_args(argv)

    catalogue_file = REPO / "scripts" / "one_click_catalogue.json"
    catalogue = {}
    if catalogue_file.exists():
        catalogue = json.loads(catalogue_file.read_text(encoding="utf-8"))

    page = the_page(
        nvidia_smi=read_nvidia_smi(),
        holder=read_lock(),
        runtime=read_runtime(),
        catalogue=catalogue,
        free_mib=read_free_mib(),
        on_disk=models_on_disk(),
    )
    if args.json:
        print(json.dumps(
            {"measured": page.measured, "total": page.total,
             "lines": [vars(l) for l in page.lines], "read": page.witnesses}, indent=1))
    else:
        print(render(page))
    return page.exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
