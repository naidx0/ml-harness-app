"""Build a recipe's pinned environment from what the recipe DECLARES.

    python scripts/build_recipe_env.py hf-peft-lora
    python scripts/build_recipe_env.py --all
    python scripts/build_recipe_env.py hf-quantize --check

## Why this exists

`README.md` states the barrier in one line: *"Real training depends on pinned
per-recipe environments you build first."* Until now those steps lived as PROSE
in each `requirements.lock` header, in three different phrasings, and a
newcomer had to read a comment and retype four commands per recipe. Nothing
checked the prose was right, and it was not: `hf-quantize`'s header said python
3.12 for an environment measured at 3.11.15.

So the steps moved into `recipe.toml` under `[environment]`, and this script
executes them. One source of truth, and `tests/test_a_recipe_says_how_to_build_
its_environment.py` refuses a recipe that ships a lockfile without one.

## The check that makes it honest

Installing the wrong torch is not an error. PyPI's Windows wheel is CPU-only;
the CUDA build exists only on download.pytorch.org. Somebody who gets the wrong
one COMPLETES EVERY STEP, sees no failure, clicks train, and waits. So
`[environment.verify]` is executed too: the built interpreter imports the module
and reports `torch.cuda.is_available()`, and an environment that cannot say True
is reported NOT READY rather than built.

`--check` runs only that verification against an environment that already
exists, which is the cheap thing to run before a training job rather than after
a slow one.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

try:  # 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - the repo targets 3.11+
    import tomli as tomllib  # type: ignore[no-redef]

REPO = Path(__file__).resolve().parents[1]
RECIPES = REPO / "recipes"


def declaration(recipe: str) -> dict:
    """The `[environment]` table, or a refusal that names the file to fix."""
    manifest = RECIPES / recipe / "recipe.toml"
    if not manifest.is_file():
        raise SystemExit(f"there is no recipe at {manifest}")
    body = tomllib.loads(manifest.read_text(encoding="utf-8"))
    env = body.get("environment")
    if not env:
        raise SystemExit(
            f"{manifest} declares no [environment], so this script does not "
            "know how to build it. Add one - python, before_lock, verify - "
            "rather than putting the steps in a comment nobody executes."
        )
    return env


def interpreter(recipe: str) -> Path:
    venv = RECIPES / recipe / ".venv"
    win = venv / "Scripts" / "python.exe"
    return win if win.exists() or sys.platform == "win32" else venv / "bin" / "python"


def run(argv: list[str]) -> int:
    print("   $", " ".join(str(a) for a in argv))
    return subprocess.call(argv)


def verify(recipe: str, env: dict) -> bool:
    """Import what the recipe named and report what is REALLY there.

    Returns True only when every declared expectation held. The point is that
    an environment which installed cleanly and cannot reach the GPU is a
    FAILURE with no error message, so this manufactures the error message.
    """
    want = env.get("verify") or {}
    module = str(want.get("import_module") or "").strip()
    if not module:
        print("   (this recipe declares nothing to verify)")
        return True
    python = interpreter(recipe)
    if not python.exists():
        print(f"   NOT READY: no interpreter at {python}")
        return False
    probe = (
        "import importlib,sys;"
        f"m=importlib.import_module({module!r});"
        "v=getattr(m,'__version__','?');"
        "cuda=getattr(getattr(m,'cuda',None),'is_available',lambda:None)();"
        "print(f'{v}|{cuda}')"
    )
    done = subprocess.run(
        [str(python), "-c", probe], capture_output=True, text=True
    )
    if done.returncode != 0:
        print(f"   NOT READY: importing {module} failed:\n{done.stderr.strip()[:500]}")
        return False
    version, _, cuda = done.stdout.strip().partition("|")
    print(f"   {module} {version}, cuda_available={cuda}")
    if bool(want.get("expect_cuda")) and cuda != "True":
        print(
            f"   NOT READY: {recipe} declares expect_cuda and this "
            f"{module} reports {cuda}. Nothing errored and nothing will - a "
            "CPU-only wheel installs cleanly and then trains at a crawl. "
            "Delete the .venv and build again; the index in "
            "[[environment.before_lock]] is the one that carries the CUDA build."
        )
        return False
    return True


def uv() -> str | None:
    """`uv` if it is on PATH, else None.

    PREFERRED OVER pip, AND THE FIRST REASON I GAVE FOR IT WAS A MEASUREMENT
    ARTEFACT. This docstring claimed a uv-built venv was 86 MB against pip's
    4.9 GB. **That was wrong**, and rebuilding with uv is what caught it: the
    rebuilt environment came out at 4.7 GB, not 86 MB.

    The 86 MB came from `du -sh recipes/*/.venv`, which counts each INODE ONCE
    per invocation and attributes shared storage to whichever directory it walks
    first. `hf-peft-lora` and `hf-peft-dpo` ship IDENTICAL lockfiles, so uv
    hardlinked them together - `torch_cpu.dll` has one inode with a link count
    of 4 across both - and du charged all of it to the first and 86 MB to the
    second. Measured properly: 4.9 GB each alone, **5.0 GB together**, not 9.8.

    WHAT IS ACTUALLY TRUE, and it still favours uv:

      * It hardlinks from its cache, so a second recipe with the same pins costs
        almost nothing. That is real and it is why the two peft recipes occupy
        5.0 GB rather than 9.8.
      * Its install is leaner in FILE COUNT for the same lockfile: rebuilding
        `hf-quantize` took it from 26,571 files to 18,061. That matters beyond
        disk, because
        `tests/test_the_sandbox_isolates_everything_the_product_writes.py`
        fingerprints `recipes/` by walking `rglob("*")` on every gate run, so
        every file is hashed by every lane every time.
      * And it is what every recipe's own lockfile header already tells a person
        to use, so this script agreeing with them removes a discrepancy rather
        than adding a preference.

    `hf-quantize` does not share with the peft pair because its package set
    differs - bitsandbytes in, peft and trl out - so its 4.7 GB is genuinely its
    own.

    pip stays as the fallback, because a machine without uv must still be able
    to build a recipe - it is slower and larger, and it says so.
    """
    return shutil.which("uv")


def build(recipe: str) -> bool:
    env = declaration(recipe)
    home = RECIPES / recipe
    lock = home / "requirements.lock"
    venv = home / ".venv"
    python = interpreter(recipe)

    print(f"== {recipe}")
    tool = uv()
    wanted = str(env.get("python") or "").strip()
    if not venv.exists():
        if tool:
            argv = [tool, "venv"]
            if wanted:
                argv += ["--python", wanted]
            argv.append(str(venv))
            print("   -- uv: hardlinks from its cache, so a recipe sharing "
                  "another's pins costs almost nothing, and its install "
                  "carries fewer files for the same lockfile")
        else:
            argv = [sys.executable, "-m", "venv", str(venv)]
            print("   -- uv is not on PATH, falling back to venv+pip: this "
                  "copies rather than hardlinking and lands about 8,000 more "
                  "files for the same lockfile, every one of which is hashed "
                  "by every gate run that fingerprints recipes/")
        if run(argv) != 0:
            print("   could not create the virtualenv"); return False
    else:
        print(f"   reusing {venv}")

    # BEFORE THE LOCK, AND IN ORDER. Each entry names its own index because the
    # whole reason it is separate is that it does not come from PyPI.
    for step in env.get("before_lock", []):
        requirement = str(step.get("requirement") or "").strip()
        if not requirement:
            continue
        argv = ([tool, "pip", "install", "--python", str(python)]
                if tool else [str(python), "-m", "pip", "install"])
        index = str(step.get("index_url") or "").strip()
        if index:
            argv += ["--index-url", index]
        argv.append(requirement)
        print(f"   -- {requirement}: {step.get('why') or 'declared before the lock'}")
        if run(argv) != 0:
            print("   that install failed; the environment is not built"); return False

    if lock.is_file():
        argv = ([tool, "pip", "install", "--python", str(python), "-r", str(lock)]
                if tool else [str(python), "-m", "pip", "install", "-r", str(lock)])
        if run(argv) != 0:
            print("   the lockfile install failed"); return False
    else:
        print(f"   (no requirements.lock beside {home / 'recipe.toml'})")

    return verify(recipe, env)


def recipes_with_a_lockfile() -> list[str]:
    return sorted(
        d.name for d in RECIPES.iterdir()
        if d.is_dir() and (d / "requirements.lock").is_file()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipe", nargs="?", help="the recipe directory name")
    parser.add_argument("--all", action="store_true",
                        help="every recipe that ships a requirements.lock")
    parser.add_argument("--check", action="store_true",
                        help="verify an existing environment; build nothing")
    args = parser.parse_args()

    if args.all:
        names = recipes_with_a_lockfile()
    elif args.recipe:
        names = [args.recipe]
    else:
        parser.error("name a recipe, or pass --all. "
                     f"Recipes with a lockfile: {', '.join(recipes_with_a_lockfile())}")

    ok = True
    for name in names:
        if args.check:
            print(f"== {name}")
            ok = verify(name, declaration(name)) and ok
        else:
            ok = build(name) and ok
    print("\nREADY" if ok else "\nNOT READY - read the lines above")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
