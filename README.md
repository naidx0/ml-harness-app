# ML Harness

**The layer above the trainer.** ML Harness is a local-first tool that answers
the question nobody else will answer: should you train a model at all?

Most people who think they need a fine-tune need a better prompt, a retrieval
step, or an evaluation loop run a hundred times. Telling them that honestly —
before they spend a month and a GPU bill — is the point of this product. When
training genuinely is the right call, we do not run it ourselves: we hand
execution to a pinned backend (Unsloth, Hugging Face peft+trl, MLX-LM) and put
our effort into the decision, the evidence behind it, and making it legible.

## ⬇️ Download

<p>
  <a href="https://github.com/naidx0/ml-harness-app/releases/download/v0.1.0/ML-Harness-Setup-0.1.0-x64.exe"><img alt="Download for Windows (installer)" src="https://img.shields.io/badge/Download-Windows%20installer%20(.exe)-0078D4?style=for-the-badge&logo=windows&logoColor=white"></a>
  <a href="https://github.com/naidx0/ml-harness-app/releases/download/v0.1.0/ML-Harness-0.1.0-x64.msi"><img alt="Download for Windows (MSI)" src="https://img.shields.io/badge/Download-Windows%20MSI-5E5E5E?style=for-the-badge&logo=windows&logoColor=white"></a>
  <a href="https://github.com/naidx0/ml-harness-app/releases/latest"><img alt="All releases" src="https://img.shields.io/badge/Releases-all%20versions-24292F?style=for-the-badge&logo=github&logoColor=white"></a>
</p>

| | Step | What to do |
|---|---|---|
| 1️⃣ | **Download** | Click the blue **Windows installer** button above. You get one file of about 35 MB. |
| 2️⃣ | **Install** | Double-click it. The installer is not signed yet, so Windows may say *"Windows protected your PC"*: click **More info**, then **Run anyway**. It installs for your user only and needs no admin rights. |
| 3️⃣ | **Open** | Click the **ML Harness** icon on your desktop or in the Start menu. The first launch builds its own Python, which needs internet (11 seconds on a clean test machine). After that it opens in seconds. |
| 4️⃣ | **Connect a model** | ML Harness ships no model. Click **Connect a model** and pick one your local [Ollama](https://ollama.com/download) already has, or paste an OpenAI-compatible endpoint and key. A key goes to the Windows credential store, never to a file. |
| 5️⃣ | **Ask** | Type what you want in your own words. For example: *"Train a logistic regression on scikit-learn's iris dataset with an 80/20 split and tell me the test accuracy"*, or *"I have support tickets in this folder and want a model to route them the way my team does."* |

**You need:** 🪟 Windows 10 or 11, 64-bit · 💾 free disk space for the app and any model you add · 🌐 internet on the first launch.
**Good to have:** 🦙 [Ollama](https://ollama.com/download) for a free local model · 🔧 [Git for Windows](https://git-scm.com/download/win), so small ML tasks run in Git Bash (without it they run in PowerShell) · 🎮 an NVIDIA GPU if you will train.

🔐 **Check the file.** Each release lists the SHA-256 of every download. In PowerShell:
`Get-FileHash .\ML-Harness-Setup-0.1.0-x64.exe -Algorithm SHA256`

🧹 **Uninstall.** Windows Settings → Apps → ML Harness → Uninstall.

📦 **Source.** The public code is at [naidx0/ml-harness-app](https://github.com/naidx0/ml-harness-app).

## What runs today

A diagnosis-and-build harness for two domains, with a measurement tier and an
eval loop. One chat box (React over Vite) on a FastAPI engine, bring-your-own
model: a local Ollama or any OpenAI-compatible endpoint, bound to loopback with
a bearer token.

- **Three ledgers, one engine.** Machine learning
  (`docs/diagnosis_engine.yaml`) and AI engineering
  (`docs/ledgers/ai_engineering.yaml`) each declare five gates; harness design
  (`docs/ledgers/harness_design.yaml`) declares six. A gated outcome is
  reachable only through its own ledger's gates, enforced by tests — **an
  asserted number opens nothing.**
- **93 registered tools in 15 capability packs.** Each declares one spec and
  gets two faces from it: the JSON schema the model is given and the button a
  person clicks. That count is checked against the registry by a test, because
  a number retyped into a README goes stale at the next commit.
- **Every displayed number carries its provenance** — measured, stated,
  inferred or defaulted — and the interface shows which.

## Two things a visitor can read

**[The judge record](docs/judge_runs/THE-JUDGE.md).** What a model-as-judge was
asked, what it answered, and every time its answer was withdrawn. It is kept
because the withdrawals are the useful part.

**[The sentinel-N result](docs/judge_runs/2026-09-05-sentinel-n-result.md).**
The judge was given 72 rewrites that are not degradations at all. It kept 19,
and **every one of the 19 justified itself with a clause the rewrite still
contains word for word** — one citing a dropped condition where the two texts
differ by a single full stop. Deciding the same question by rule instead
refused 106 non-degradations at zero model calls.

**[Two hundred rows through the wired pipeline](docs/judge_runs/2026-09-05-two-hundred-rows-prereg.md).**
Preregistered before any call — what would be counted, what would stop the run,
and the cost — then run on one consumer card and written up in the same file.
**200 generated, 0 generator failures, 12 refused by the validator, 192 reaching
the judge, 7 refused by the two gates.** The registered prediction that the
gates would not fire is refuted in its own words. Reading all 68 kept rows that
add a content word: **41 lies blocked against 22 genuine degradations lost, a
ratio of 1.86** — the line for keeping the rule was 0.33, set before the
reading.

## The library lifted out of it

Four checks this harness enforces on itself, extracted so they can be used
without it: **[four-asserts](https://github.com/naidx0/four-asserts)** — as many
things ran as were discovered; the resource had a named holder that was still
alive; the artifact has an identity that outlives its bytes; the verdict's
reason survives a rule.

Across 25 agent and evaluation frameworks read on 2026-09-05, all four together
were present in **0 of 25**. Adding a tool to a builder is about four lines;
adding all four asserts to a server and its runner measured eight.

## Run it locally

```powershell
python -m pip install -e ".[test]"
.\start.ps1                          # engine and UI; reuses what is already right
.\start.ps1 --status                 # say what is running, change nothing
.\start.ps1 --stop                   # stop the engine on --port, and nothing else
python scripts/gate.py               # the suite, asserting ran == discovered
python scripts/build_recipe_env.py --all          # the pinned per-recipe environments
python scripts/build_recipe_env.py --all --check  # verify them, build nothing
```

The engine is detached, so it outlives the terminal you started it from — which
is why `--stop` is here beside `--start` rather than left for you to find. It
stops the one engine it can identify on that port and says which pid it stopped;
if something else is listening there it refuses and terminates nothing, because
stopping a process this launcher did not start is a decision for the person who
did.

Under the launcher the engine is
`python -m uvicorn app.main:app --host 127.0.0.1 --port 8078`, and that port is
checked against `app.config.DEFAULT_PORT` by a test.

### Then connect a model — the harness ships none

This is a real step and it used to be missing from this page. The engine starts,
every check goes green, and the product can diagnose nothing until you lend it a
model. The window says so: with no connection the composer carries *"No model
connected — the harness thinks with a model you lend it"* over a button, and the
model selector beside it reads **Connect a model**. Two roads, equal weight —
anything your local Ollama already has, in one click, or an OpenAI-compatible
endpoint and a key. The key goes to the OS keychain and never into SQLite.

Without the window:

```powershell
mlh doctor                           # what this installation can read, and what it still needs
```

A fresh install answers `? model  none connected - this product cannot diagnose
anything yet`. That row is a **question, not a fault** — it does not make
`doctor` exit non-zero, because an exit code that is 1 for every new install is
an exit code nothing can be gated on. It was added on 2026-09-10 after a
Windows Sandbox run proved a stranger could install this, see five green rows,
and never be told a model was needed.

The gate is the check that must pass before anything is committed. It runs the
suite and then asserts three things the runner cannot: that as many tests ran as
were discovered, that no module failed to import, and that the run reached its
own verdict line.

## Limitations, stated rather than discovered

- **Generated rows are the most dangerous thing in here** and are treated that
  way: they cannot open a gate and cannot be trained on unverified. What is not
  claimed is that the harness can tell a right generated answer from a wrong
  one — it cannot, which is exactly why a person reads the sample.
- **Only one recipe runs without a built environment**, and it trains nothing.
  Real training depends on pinned per-recipe environments you build first —
  now one command rather than four retyped out of a comment. Each recipe
  declares its own build in `recipe.toml` under `[environment]`, and
  `build_recipe_env.py` executes that declaration and then **imports torch and
  refuses to say READY unless CUDA is really there**. That check is the point:
  PyPI's Windows torch wheel is CPU-only, the CUDA build lives only on
  download.pytorch.org, and installing the wrong one is not an error — you
  complete every step, see nothing fail, click train, and wait.
- **The installer is real but unsigned, and there is no cloud execution.** This
  line used to read *"there is no installer"* and that is no longer true: NSIS
  builds one, and on 2026-09-10 it was driven in a Windows Sandbox with nothing
  else on the machine — no Python, no git, no uv — where it installed silently,
  built its own interpreter, and answered `/health` as a real installed copy.
  What it is **not** is signed, so SmartScreen will warn. Since 2026-10-01 it is
  published as a release (see Download above) as well as built locally with
  `npx tauri build`. Windows is what this
  is developed and verified on; Apple Silicon and AMD paths are best-effort until
  someone runs them there.
- **The trace reader has never been run against a public annotated corpus.**

## The rest of the documentation

`docs/VISION.md` for the full picture, `docs/PHASES.md` for what is being built
next, `docs/how-to-verify.md` for the laws this repository holds itself to and
the commit each one was learned in, and `AGENTS.md` for how to work in it.
