"""Which precisions a recipe can actually run, read off the recipe.

## The evening this is for

A base-weight figure of 0.74 GiB was published for a 1.5B model and a training
run recommended on it. 0.74 GiB is an **NF4** number - the model's own
1,543,569,408 parameters at fp16 are 2.88 GiB. The recipe that would have run it
could not quantise at the time: `bitsandbytes` did not appear in its lock file
and `load_in_4bit` did not appear in its entrypoint. **The estimate was correct
about the machine and wrong about the software**, and in fp16 every sequence
length on that card is infeasible.

`app/feasibility.py` already refuses when it lacks geometry. It does not refuse
when it HAS geometry and the runner cannot reach the configuration it priced,
because nothing in the harness could answer that question. This module answers
it.

## What it reads, and what that is worth

A recipe directory, statically: the dependency in `requirements.lock` and the
code path in the entrypoint. That is exactly how the error was found - somebody
read a lock file - and it is worth saying plainly that a static read is weaker
than running the thing. A lock file naming `bitsandbytes` does not prove the
4-bit path works; it proves the recipe was built to have one. **The direction
that matters is the refusal**: absent the dependency, the path cannot work, and
that is the case that cost an evening.

So `can_reach` is honest in one direction and hopeful in the other, and says so.
A precision it rejects is genuinely unreachable. A precision it accepts is
reachable as far as the recipe's own declarations go.

## Why it is not in `feasibility.py`

That module is about arithmetic over a machine. This is a fact about software on
disk. Keeping them apart is what lets a caller say *the number is right and the
runner cannot get there*, which is a different sentence from either half.
"""

from __future__ import annotations

from pathlib import Path

#: What a precision needs before a recipe can be said to reach it. `None` means
#: nothing beyond the base framework - a recipe that trains at all trains in
#: fp16, so there is nothing to look for and nothing to refuse.
#:
#: The two markers are the two halves that have to agree: the package has to be
#: INSTALLABLE (it is in the lock) and REACHED (the entrypoint names the flag).
#: Either alone is how the mistake happened - a recipe can depend on a library
#: it never calls, and can name a flag it cannot import.
WHAT_A_PRECISION_NEEDS: dict[str, tuple[str, str] | None] = {
    "NF4": ("bitsandbytes", "load_in_4bit"),
    "INT8": ("bitsandbytes", "load_in_8bit"),
    "Q8": ("bitsandbytes", "load_in_8bit"),
    "FP16": None,
    "BF16": None,
    "FP32": None,
}

#: Where the two halves are looked for. A recipe that keeps its dependencies
#: somewhere else reads as unable, which is the safe direction to be wrong in.
THE_LOCK = "requirements.lock"
THE_ENTRYPOINT = "entrypoint.py"


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def why_not(recipe_dir: Path, precision: str) -> str | None:
    """Why this recipe cannot run at this precision, or `None` if it can.

    A SENTENCE AND NOT A BOOLEAN, because the caller's job is to tell somebody
    what to do about it, and "your card is too small" and "this recipe cannot
    quantise" lead to different actions on the same arithmetic.
    """
    name = str(precision or "").upper()
    if name not in WHAT_A_PRECISION_NEEDS:
        return f"{precision!r} is not a precision this harness knows"

    needs = WHAT_A_PRECISION_NEEDS[name]
    if needs is None:
        return None

    package, flag = needs
    where = Path(recipe_dir)
    if package not in _text(where / THE_LOCK).lower():
        return (
            f"{name} needs {package}, and {where.name}/{THE_LOCK} does not "
            f"pin it - so the run would fail at import, not at the card"
        )
    if flag not in _text(where / THE_ENTRYPOINT):
        return (
            f"{name} needs {package} AND a code path that uses it; "
            f"{where.name}/{THE_ENTRYPOINT} pins the package but never names "
            f"{flag}, so nothing would load the weights that way"
        )
    return None


#: What `transformers` loads when nobody names a dtype. Not a choice the
#: harness makes - a fact about the library the recipes run on.
THE_FRAMEWORK_DEFAULT = "FP32"

#: Where a recipe says which dtype it loads. `hf-quantize` declares
#: `compute_dtype`; the two training recipes declare nothing, which is the
#: whole of the problem below.
THE_DECLARATIONS = ("compute_dtype", "dtype", "torch_dtype")

#: What a declared string means. Anything unrecognised is left alone rather
#: than mapped, because a recipe naming a dtype this table has never heard of
#: is a recipe this module should not be answering for.
WHAT_A_DECLARATION_MEANS = {
    "float16": "FP16", "fp16": "FP16", "half": "FP16",
    "bfloat16": "BF16", "bf16": "BF16",
    "float32": "FP32", "fp32": "FP32", "full": "FP32",
}


def declares(recipe_dir: Path) -> str | None:
    """The dtype this recipe says it loads, or `None` if it says nothing."""
    text = _text(Path(recipe_dir) / "recipe.toml")
    for line in text.splitlines():
        bare = line.split("#", 1)[0]
        if "=" not in bare:
            continue
        key, _, value = bare.partition("=")
        if key.strip() not in THE_DECLARATIONS:
            continue
        said = value.strip().strip('"').strip("'").lower()
        if said in WHAT_A_DECLARATION_MEANS:
            return WHAT_A_DECLARATION_MEANS[said]
    return None


def what_it_will_load(recipe_dir: Path, requested: str) -> tuple[str, str | None]:
    """The precision this recipe will really load, and why if it is not asked for.

    THE DEFAULT NOBODY PASSED. `hf-peft-lora` hands `SFTTrainer` the base model
    as a STRING on the unquantised path - `model_for_trainer = base_model` -
    so nothing calls `from_pretrained` with a dtype and transformers loads at
    its own default, fp32. `fp16=True` in `TrainingArguments` is autocast over
    fp32 master weights, not a half-precision load. Every adapter on this disk
    labelled fp16 was trained at four bytes per parameter while the estimator
    priced two, and the difference was carried for an evening as a mysterious
    constant the estimator omitted.

    The quantised path is not affected and this must not claim it is: that
    branch passes `dtype=torch.float16` explicitly beside its
    `BitsAndBytesConfig`, so an NF4 request loads what it asked for.

    READ, NOT INFERRED. The answer comes from what the recipe DECLARES in
    `recipe.toml`. This module deliberately does not read the entrypoint for a
    dtype: `hf-peft-lora` passes one in three places, none of them the training
    load, and a check that found those would report fp16 for exactly the path
    that does not get it. A recipe that loads half precision and says so
    nowhere reads as fp32 here - which over-states the memory, is the safe
    direction to be wrong in, and is fixed by one line in a toml file.
    """
    name = str(requested or "").upper()
    refusal = why_not(recipe_dir, name)
    if refusal is not None:
        return name, refusal

    if WHAT_A_PRECISION_NEEDS.get(name):
        # A quantised request the recipe can reach. Its loader names a compute
        # dtype at the call site, which is what makes the request honest.
        return name, None

    said = declares(recipe_dir)
    if said is not None:
        return said, None if said == name else (
            f"{Path(recipe_dir).name} declares it loads {said}, not {name}"
        )
    if name == THE_FRAMEWORK_DEFAULT:
        return name, None
    return THE_FRAMEWORK_DEFAULT, (
        f"{name} was asked for and {Path(recipe_dir).name} names no dtype, so "
        f"the base loads at the framework default {THE_FRAMEWORK_DEFAULT} - "
        f"twice the bytes per parameter. `fp16=True` in TrainingArguments is "
        f"autocast over {THE_FRAMEWORK_DEFAULT} master weights, not a "
        f"half-precision load. Price this at {THE_FRAMEWORK_DEFAULT}, or have "
        f"the recipe declare the dtype it loads."
    )


def can_reach(recipe_dir: Path, precision: str) -> bool:
    """Whether this recipe can run at this precision, as far as it declares.

    Trustworthy when False. Hopeful when True - see the module docstring.
    """
    return why_not(recipe_dir, precision) is None


def what_it_can_reach(recipe_dir: Path) -> frozenset[str]:
    """Every precision this recipe declares its way to."""
    return frozenset(
        name for name in WHAT_A_PRECISION_NEEDS if can_reach(recipe_dir, name)
    )
