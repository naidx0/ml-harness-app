# What already exists

Verified 2026-08-18 by direct web search, not taken from an agent's summary.

## The finding that changes the plan

**Unsloth shipped most of the training half of this product, and shipped it recently.**

- **Unsloth Studio** — launched 15 March 2026. Fully local, open source, free, web UI.
  Run, train, and export 500+ LLMs without writing Python. Mac, Windows, Linux.
  Loading a model, creating datasets, training, evaluating, exporting — all in one
  local interface. Data never leaves the machine. Front page of Hacker News within
  24 hours.
- **Unsloth Desktop** — shipped August 2026, roughly a week before this was written.
  Free, open source, native app for macOS, Windows and Linux. Runs and fine-tunes
  LLMs, diffusion, TTS and embedding models locally. No telemetry, works offline.
  CPU, Apple, NVIDIA, AMD, Intel, multi-GPU. 2x faster training with 70% less VRAM.

Sources: <https://unsloth.ai/docs/new/studio>, <https://unsloth.ai/>,
<https://github.com/unslothai/unsloth>, <https://unsloth.ai/docs/new/changelog>

## What this takes off the table

"Make it easy for a person to do a low-rank adaptation at home on their own setup"
is no longer an unoccupied position. It is occupied by a free, open-source,
well-funded, faster product with a year's head start on kernels.

We should not write a trainer. We would be building a slower version of something
free.

## What it does not take off the table

Unsloth Studio is a **trainer**. It assumes you have already decided to fine-tune.
Everything it does begins after that decision. It will never tell you not to train.

That decision is the hard part, and it is where people waste their money:

- Is machine learning the right tool here at all, or is this a prompting,
  retrieval, or evaluation-loop problem?
- Is there even an eval set? Is there a measured baseline to beat?
- Is a fine-tune going to fix a *knowledge* gap it cannot fix, when retrieval would?
- Is this tabular data where a gradient-boosted tree wins?
- Is it worth the time and the electricity?

Nothing in the landscape asks those questions before taking your data. Not Unsloth,
not AutoTrain, not the six-figure consultancies — the consultancies least of all,
since their incentive runs the other way.

Also unoccupied:

- **The harness shape.** Unsloth is a form-driven GUI. Ours is a chat box you talk
  to, which takes your repository and your files as context the way a coding
  harness does, and asks the questions an ML engineer would ask.
- **Bring your own model as the brain.** Unsloth ships no reasoning layer. Our whole
  product is a reasoning layer that the user powers with their own key.
- **The teaching layer.** Watching the network learn. Nobody is doing this inside a
  working tool.
- **Enterprise data sensitivity.** Residency and egress control as an enforced
  property, not a promise.

## The resulting position

We are the layer **above** the trainer, not the trainer.

Diagnose honestly, decide what to build, prepare the data, pick the model, then hand
execution to Unsloth or HF peft/trl or MLX-LM as a pinned backend and supervise it.
The moat is the decision and the explanation, not the CUDA kernel.

This is a smaller build than writing a trainer, not a larger one. The hardest and
most expensive part of the original plan — making training work correctly across
NVIDIA, Apple Silicon, AMD and CPU — is now someone else's solved problem that we
are allowed to call.

## Control-surface neighbour (not a trainer) — T3 Code, gated 2026-09-14

**T3 Code** ([pingdotgg/t3code](https://github.com/pingdotgg/t3code),
[t3.codes](https://t3.codes)) is an open-source **agent harness control surface**:
web, desktop, and mobile UIs that orchestrate coding-agent CLIs you already pay
for (Codex, Claude Code, Cursor Agent, Grok, OpenCode, Antigravity). It is not a
trainer and it is not a diagnosis engine. It wins on composer density, permission
ladders, remote approvals, per-turn checkpoints/diffs, subagent and usage
visibility.

It does **not** occupy our position (honest train / do-not-train with provenance).
It *does* set a bar for how visible mode, run state, cost, and workers should
feel. The full comparison, gap matrix, and non-goals live in
[`docs/CONTROL_SURFACE_GATE.md`](CONTROL_SURFACE_GATE.md). The build queue is
**Control surface (CS)** in [`docs/PHASES.md`](PHASES.md).

## Open question for Max

This changes positioning, not direction. Confirm you are happy being the decision
layer that delegates execution, rather than owning training end to end. Work is
proceeding on that assumption because it is the only defensible one, but it is your
call and it is reversible.
