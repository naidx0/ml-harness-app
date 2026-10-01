# The Harness — what we are building

## One sentence

**One chat box for building with AI, on your own machine, powered by a model you
lend us.**

## The shape of it, in one more sentence

**Diagnose honestly, then do the thing that was actually right** — a better
prompt, a retrieval index, a cleaner dataset, an agent with tools that work, a
fine-tune — without the person leaving the conversation, and with the
measurement that proves it worked sitting in the same thread.

The first half is what nobody else will do. The second half is what makes the
first half worth having.

Max, 2026-08-22: *"This is like the building tool for their building tools."*
That is the sentence this document exists to make real.

## The problem

Agentic coding harnesses did something specific and it is worth being precise
about what. They did not add a feature to the IDE. They collapsed a process —
read the code, plan the change, edit, run, test, debug, explain — into a single
conversation. The win was not any one capability. **It was that you stopped
navigating.**

Building with AI has no equivalent, and it is now the thing most people are
actually doing. Writing a prompt that holds. Deciding whether you need retrieval.
Giving an agent tools and finding out whether they fire when they should.
Knowing whether the change you just made helped. Working out whether to train at
all. Each of these is a real discipline, they interact, and today they live in
different tools, different tabs, different notebooks — and the seams between them
are where people give up.

**Access to models is solved. Access to judgment is not.** Anyone can call a
model. Almost nobody can tell you whether their eval set is large enough to
support the claim they just made, whether that three-point gain is real, or
whether the expensive thing they are about to do is the right thing. That
judgment is what senior practitioners have, what agencies charge six figures
for, and what this product encodes.

## What we do about it

You open one chat box and talk. Everything happens there:

- **Say what you are trying to build.** Not which tab you need — you should not
  have to know that, and the person who most needs this product is precisely the
  one who does not.
- **It looks.** Your machine, your folder, your repository, your last run, your
  budget. It asks only what it genuinely cannot see.
- **It diagnoses.** What is actually wrong, and what would fix it. Often that is
  not what you came in asking about.
- **It proposes a build** — a typed plan of what it intends to do, drawn as a
  diagram, costed with every estimate carrying its origin.
- **You approve it, and what you approved is what runs.**
- **It does the work**, streaming into the thread, and verifies each step against
  the criterion the plan declared *before* it ran.
- **You end holding an artifact and the evidence it works.**

Same box. Same thread. No tabs to learn.

## The mechanism: one engine, many ledgers

This is the architectural heart and it is what makes a single chat box able to
cover more than one discipline without becoming a launcher.

The engine does not know anything about machine learning. **The knowledge lives
in a ledger** — `docs/diagnosis_engine.yaml` — and the engine walks it. Measured
on 2026-08-22: the ML ledger is 3,468 lines holding 79 outcomes, five gates,
every fact, condition and question. The Python that reads it is 2,413 lines. **The
knowledge is bigger than the machine that runs it**, and `load_spec()` already
takes a path.

So a discipline is a ledger:

| ledger | what it decides |
|---|---|
| machine learning | should you train, and if not, what instead |
| AI engineering | should you build this agent, and what is actually wrong with it |
| data | is this data usable, and can it be made so |
| environments | can this be simulated, measured, rewarded |

**You never pick one.** The harness infers the discipline the way it already
infers modality and task family — from what you said and what it can see. The
moment a person has to choose between a "prompt engineering chat" and an "agent
engineering chat", we have rebuilt the control panel we exist to replace, and we
have asked them to diagnose themselves, which is our job.

Different tools, yes — dozens. Different surfaces for results, yes — cards,
diagrams, sandboxes. **Different chats, no.**

## Why this is not a control panel, and not an all-in-one

Unsloth Studio is good, it is free, and it is a control panel. It has tabs and
forms and it assumes you already know which tab you need and what belongs in the
fields. Everything it does begins after you have decided to fine-tune. It will
never tell you not to.

That is the difference in one line: **a form can only advise on what its own
fields hold.** It cannot know that your dataset has a leak between train and
eval, that your GPU has 8 GB, that your repository already contains an eval set
hiding in its git history, and that your real problem is retrieval — all at once,
while you are asking about learning rate.

And **"all-in-one" is not our claim either.** Everybody says it and it usually
means a tab bar. Bundling free tools is not a product; the tools are already
free. What is scarce is the judgment about what to do with them and whether it
worked.

**Ease is not a nicer form. Ease is not having to know what to ask.**

## The moat, stated plainly

Four things, and only the last two are hard to copy.

1. **Unification.** One place holds the machine, the data, the repository, the
   last run and the budget at once, so its advice can be better than a form's.
2. **The advice and the work are the same object.** The proposal is what the
   executor consumes. A tool that advises and a tool that acts drift apart within
   a week; here they cannot, because they are one thing.
3. **We never invent a number.** Every figure carries where it came from —
   measured, inferred with the derivation shown, or unknown and said so. A delta
   inside the resolution is reported as NO EVIDENCE, in those words. This is
   domain-general, it is rare, and it is the reason to come back.
4. **We are willing to say do not.** Do not train. Do not build the agent. Ship
   what you have. That sentence costs us a sale and buys the only thing that
   matters, which is that the next sentence is believed.

## The answer we have to be willing to give

Most people who think they need a fine-tune need a better prompt, a retrieval
step, or an evaluation loop run a hundred times. Most people who think they need
an agent need a script and one API call.

Saying so — before they spend a month and a GPU bill — is the point. **A product
that cannot say "do not" has no way to make "do" mean anything.**

The five gates exist so that answer is structural rather than a matter of taste:
no expensive irreversible outcome is reachable without an eval set, a measured
baseline, the cheap thing exhausted, the alternatives considered. Those gates are
ML's today. Every ledger needs its own, and they are the first thing a new ledger
must define.

## And then we do the thing we said instead

An honest refusal that ends the conversation is a dead end, and for most of this
project's life that is exactly what it was.

So a "do not" produces **a build for the thing we said instead**, with the same
picture, the same approval, the same execution and the same proof at the end. The
refusal stops being the end of the conversation and becomes the beginning of the
right one.

This is the single largest body of work in front of us. On 2026-08-22, twelve of
fifty-five ML outcomes lead to a build. The engine that decides is close to
complete; the engine that *does* covers a fifth of it. Closing that is not
invention — it is assembly, and every one done so far discovered the pieces
already existed.

## Data is work, not a precondition

The most common thing standing between a person and a result is that their data
is not ready, or does not exist. Six places in the ML ledger stop on exactly
that.

So the harness works on data rather than only reading it: it profiles, splits,
deduplicates, carves an evaluation set out of what you have, checks its own
output for leakage, and writes real files it can account for.

**And where there is not enough data, it can help make more — under rules that do
not poison everything downstream.** Synthetic data is inventing the data, in a
product whose first invariant is that we never invent a number, so:

- **Synthetic rows may never be the evaluation set.** Not once, not to get
  started. The eval set is the only thing telling you the truth.
- **They are tagged at the row, forever** — provenance on the data itself, the
  same way every number carries its origin.
- **They cannot open a gate.** A gate opened by rows we generated is the honesty
  test defeated by our own output.
- **Amplifying structure is honest; inventing content is not.** Generating more
  replies in your house style from thirty of yours is shape. Generating more
  factual question-and-answer pairs is fabrication at scale, and it will train a
  model to be confidently wrong.

And the consequence worth stating out loud, because it is the opposite of what
every augmentation tool implies: **synthesis makes your evaluation set more
important, not less.** With thirty real examples the honest move is often to
spend all thirty on the eval set — real, graded, yours — synthesise the training
data, and never let the two meet.

## Sandboxes, and eventually environments

A sandbox is where a build runs, and it is part of the build rather than setup
the user does first: a pinned environment, an isolated directory, a snapshot of
the data as it was, and no egress. It exists so a run is reproducible, disposable,
and cannot reach anything it was not given.

Reinforcement-learning environments are the same idea with a reward attached.
They are the deepest thing on this roadmap and should be treated as such: a
reward that means anything is a harder measurement problem than everything else
here combined. The sandbox is the foundation and it exists. The environment is a
later headline, not an early feature.

## Bring your own model

We ship no AI. The user connects their own — a local Ollama, an OpenAI-compatible
endpoint, their own key. This is not a limitation to apologise for; it is why the
economics work at all. We do not pay for their inference and they do not pay us a
margin on it.

It also means cost is theirs, and must be shown *before* they say yes rather than
discovered afterwards.

## What we do not build

- **We do not train models ourselves.** Execution is handed to a pinned backend.
  Our effort goes into the decision, the evidence, and making it legible.
- **We do not host anything.** Local-first, the user's machine, the user's data.
- **We do not sell a model.** See above.
- **We do not differentiate consumer from enterprise.** Max, 2026-08-19: there is
  one product. The distinction was specified, never built, and a toggle that
  changes almost nothing is worse than none.

## What changed on 2026-08-22, and why

This document previously said *"one chat box for the whole of machine
learning."* The pivot is a **generalisation, not a replacement**: machine
learning becomes the first ledger rather than the whole product.

Three measurements drove it:

1. **The engine was never ML-specific.** `load_spec()` takes a path. Of the nine
   places machine learning leaks into `app/diagnosis.py`, eight are the `TRAIN__`
   prefix — which is not an ML concept but a *role*: the expensive irreversible
   outcome that must pass every gate. Exactly one line is genuinely about ML.
2. **The market is where the judgment gap is.** Far more people are building with
   AI than fine-tuning. The narrow thesis addressed the smaller room.
3. **The machinery is already a methodology engine.** Propose, show, approve as a
   contract, execute, verify against a criterion stated in advance — none of that
   is about machine learning. `docs/THE_PROPOSAL_LOOP.md` said so already: *"The
   product becomes the thing this repository's own build sessions have been."*

**What does not change:** the five-gate honesty test, never inventing a number,
provenance on every displayed figure, no shell execution, no egress, bring your
own model, and the willingness to say do not.

**Open question, deliberately not decided here:** the product is no longer
described by the name "ML Harness", and the repository directory carries that
name. Renaming has real cost — paths, a sibling project's integrations, every
document. It is a decision for the owner, not a side effect of this rewrite.

## How we will know it is real

Not by feature count. By these, in order:

1. **One complete journey, recorded.** A person arrives with a problem and real
   data and leaves holding an artifact and the measurement that proves it. Until
   the loop closes once, coverage is a number about a machine nobody has driven.
2. **A second ledger runs on the same engine with no code change.** That is the
   platform thesis proven rather than asserted.
3. **Somebody is told "do not", follows the alternative, and it works.** That is
   the whole product in one sentence.
4. **A stranger can install it.** Today they cannot. That is a launch problem and
   it is real.

## Reference

- `docs/THE_PROPOSAL_LOOP.md` — the mechanic: propose, show, approve, storm, verify.
- `docs/PHASES.md` — how we get from here to there.
- `docs/DESIGN_DIRECTIVES.md` and `docs/brand/graphite.html` — how it looks, and why.
- `docs/diagnosis_engine.yaml` — the first ledger.
