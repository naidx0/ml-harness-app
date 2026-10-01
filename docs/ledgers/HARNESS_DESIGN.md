# The harness-building ledger — the domain content

This is what Phase IV turns into YAML. It is written here first for the reason
`AI_ENGINEERING_DESIGN.md` gives: **the content is the product and the YAML is
the encoding**, and a ledger authored the other way round is a schema with
opinions poured into it afterwards.

Nothing here is code yet. `docs/THE_PLAN.md` Phase IV holds the authoring
checklist — every file that must change, every LF rule, the two rosters that
would otherwise skip a new domain (now derived, `e1c9b6e`).

---

## The question this ledger answers

**"You want to build a thing that uses a model. Should you, what shape, and what
would tell you that you were wrong?"**

The ML ledger asks *should you train*. The AI-engineering ledger asks *should you
build this agent*. This one is **upstream of both**, and that is the whole reason
it is a third file rather than more nodes in the second.

### Why it cannot be part of the AI-engineering ledger

Measured, not argued. `docs/ledgers/ai_engineering.yaml`'s first gate,
`G0_SOMETHING_TO_MEASURE`, asks *"Are there real failures written down that we
can check against?"* with a floor of ten. Driven on an empty sheet it returns
`BLOCKED__NOTHING_TO_MEASURE_AGAINST` with `G0` FAILED and every later gate
`NOT_REACHED`.

**A person who has not built anything yet has no failures and never will.** They
are not failing that gate, they are standing before it. Widening G0 to admit them
would delete the thing that ledger is for — a ledger whose entry gate admits
everybody is a ledger that diagnoses nobody.

So the two meet at a handoff: the moment something exists and fails ten times,
this ledger's answer is *go and use that one*.

---

## The gates

Six, weakest first. `method_class_ladder: [tools, pipeline, agent, multi_agent]`.

Two have direct analogues in both shipped ledgers. **One has no analogue anywhere
and is this domain's reason to exist.**

### G0_THE_TASK_IS_CHECKABLE — *"Is there a written task a program can check?"*

The eval-set analogue, one rung earlier. Not "do you have failures" but "is there
a definition of success at all". A person who cannot say what right looks like
cannot be helped by anything downstream, and every question after this one would
be measuring against a moving target.

Fails to: `BLOCKED__NO_SUCCESS_CRITERION`, or `SPEC__WRITE_THE_TASK` when there
is a goal but no checkable form of it.

**SETTLED CONSERVATIVELY, 2026-08-28, and it is Max's to overturn.** The
tempting fact here was `success_check_runs` — the harness executes the person's
own checker on one case and reports pass / fail / did-not-run. That would mean
running somebody else's program, and `app/tools/blocks.py`'s `agent` pack states
the rule plainly: *never execute somebody else's system, read files.*

**So the gate is denominated in something readable instead**, which is the same
move that turned `cost_per_run_usd` into `tokens_per_run` when a price turned out
to be a fact about somebody's contract rather than about the work:

* `success_check_named` — `source: ask`. Is there a checker, and where is it?
* `success_check_is_a_program` — `source: inspect`. It exists at that path and is
  a file this harness can read. **Read, not run.**

That is weaker than executing it and it is enough for a FIRST gate, whose job is
to separate "there is a definition of success" from "there is not". Whether the
checker actually passes is what G1's twenty tasks are for, and by then the person
has run it themselves.

**Why this was decided rather than left open.** Choosing the option that keeps an
existing wall intact is not the same kind of call as choosing one that widens it:
a wall kept can be opened later on purpose, a wall widened is opened by accident
first. If executing a checker in the sandbox is wanted, that is a deliberate
change to the `agent` pack's rule with its own argument, not a side effect of a
new ledger's first gate.

### G1_TASKS_TO_MEASURE_ON — *"At least twenty real tasks, re-runnable?"*

Twenty rather than the AI ledger's ten, and the difference is not arbitrary. That
ledger counts **failures** of a thing that exists. This one counts **tasks** a
thing has never attempted, and what a harness has to hold is reliability across
repeated attempts rather than a rate on one pass.

Fails to: `SPEC__BUILD_A_STARTER_EVAL`.

### G2_THE_MODEL_ALONE_WAS_SCORED — *"What does the bare model do, and at what cost?"*

**The ladder gate, and the one that will refuse the most people.** Three rows:
`any` requires the solo run scored; `pipeline`/`agent` additionally require the
fixed sequence built and scored; `multi_agent` additionally requires a single
loop scored.

This is `G2_SIMPLE_VERSION_TRIED` generalised from one rung to a ladder, and it
is what stops somebody asking for a team having never run one call.

Fails to: `NO_HARNESS__ONE_CALL`, `NO_HARNESS__ONE_LOOP_FIRST`.

### G3_EVERY_COMPONENT_IS_LOAD_BEARING — *"For each component, a score with it and without it?"*

**No analogue in either shipped ledger, and the reason this domain is worth a
file.** A harness is a pile of components each encoding an assumption about what
the model cannot do alone, and those assumptions rot as models improve. The ML
ledger has nothing like it because a trained model is one artifact; the AI ledger
has nothing like it because it diagnoses a loop that already exists.

Fails to: `NO_HARNESS__STRIP_A_COMPONENT`, `SPEC__ABLATE_THE_HARNESS`.

**What it costs to build:** `evals.compare` and `evals.mcnemar` already do paired
comparison with a real *no evidence* answer, so the statistics exist. What does
not exist is anything that reads a harness variant and pairs runs by component.
That is a new instrument and probably a new capability name.

### G4_THE_BLAST_RADIUS_IS_DECLARED — *"Is every reachable tool classified by what it can destroy?"*

Rows split at model-driven control flow, and the split is the point: a fixed
pipeline calls a known set in a known order, so its blast radius is a property of
the code. A loop **chooses**, so its blast radius is the union of everything it
can reach — and `agent`/`multi_agent` therefore require every tool annotated and
a declared human boundary on the destructive ones.

Fails to: `SPEC__DECLARE_THE_BLAST_RADIUS`.

### G5_THE_RUN_IS_BOUNDED_AND_RECORDED — *"What does one run cost, does it stop, is there a trace?"*

The one gate that is nearly free: `tokens_per_run`, `run_terminates` and
`has_traces` are already measured by `bound_the_loop` and `read_agent_traces` in
the `agent` pack.

**Denominated in tokens, never dollars.** The AI ledger fought this argument and
won it (`ai_engineering.yaml:83-91`): a price is a fact about somebody's contract
on a Tuesday, a token count is a fact about the work.

Fails to: `SPEC__BOUND_THE_RUN`, `SPEC__INSTRUMENT_THE_LOOP`.

---

## The outcomes

Prefixes, all spelled unlike both shipped ledgers so a name leaking into Python
shows up as a failure rather than a coincidence: `HARNESS__` (gated, `BUILD`),
`NO_HARNESS__` / `NO_TOOLS__` / `HANDOFF__` (`NO_BUILD`), `SPEC__` / `BLOCKED__`
(`BLOCKED`), `REROUTE` / `ERROR__` (`null`).

### The refusals — do not build the harness

The reason this ledger is worth having, and the half that must be written first.

| outcome | when |
|---|---|
| `NO_HARNESS__ONE_CALL` | the bare model, scored on your tasks, already clears your bar |
| `NO_HARNESS__A_SCRIPT` | the steps are known and do not depend on what the last returned |
| `NO_HARNESS__USE_AN_EXISTING_ONE` | a shipped harness already does this |
| `NO_HARNESS__STRIP_A_COMPONENT` | a component is not load-bearing; remove it and re-measure |
| `NO_HARNESS__NOT_AN_AI_PROBLEM` | the failure is data, integration or permissions |
| `NO_HARNESS__ONE_LOOP_FIRST` | you asked for a team and have not measured one loop |
| `NO_HARNESS__THE_MODEL_MOVED` | the assumption a component encodes was true of an older model |
| `NO_TOOLS__FEWER_TOOLS` | too many overlapping tools to choose between |
| `NO_TOOLS__REWRITE_THE_DESCRIPTIONS` | the tools exist and are not chosen; the description is what the model reads |
| `NO_TOOLS__TYPE_THE_BOUNDARY` | the hand-offs are untyped; invalid messages should fail fast |
| `NO_TOOLS__TRIM_THE_CONTEXT` | the harness's own prompt competes with itself for attention |

### The handoffs — this is another ledger's question

| outcome | when |
|---|---|
| `HANDOFF__DIAGNOSE_THE_EXISTING_AGENT` | you have a loop and it fails — that is `ai_engineering.yaml`, and it wants ten re-runnable failures |
| `HANDOFF__THE_KNOWLEDGE_IS_THE_PROBLEM` | the answer was never knowable from what the model was given — retrieval or training, not shape |

**Flagged and not solved: cross-ledger routing does not exist.** These are
terminal `NO_BUILD` verdicts whose `say:` names the other file. A real handoff —
moving the conversation and carrying what it already measured — would need a
mechanism nothing in the engine has, and the disjoint-fact rule the domain
router depends on (`e7cebc2`) means the facts do not travel.

### The actions — go and find this out

`SPEC__WRITE_THE_TASK`, `SPEC__BUILD_A_STARTER_EVAL`, `SPEC__RUN_THE_MODEL_ALONE`,
`SPEC__ABLATE_THE_HARNESS`, `SPEC__INSTRUMENT_THE_LOOP`,
`SPEC__DECLARE_THE_BLAST_RADIUS`, `SPEC__BOUND_THE_RUN`,
`SPEC__SUBSTANTIATE_CLAIMED_FACTS`.

Every one is cheap, real work with a build behind it. The last is required by
`fact_origins.unsubstantiated_outcome` and is not optional.

### The builds — the expensive thing is the right thing

Four, and `methods:` **is** this list, because SC1 requires
`emits == {prefix + m for m in methods}`.

| outcome | method / class | when |
|---|---|---|
| `HARNESS__TOOL_LAYER` | `TOOL_LAYER` / tools | the model and control flow are fine; typed, described, risk-annotated tools are what is missing |
| `HARNESS__FIXED_PIPELINE` | `FIXED_PIPELINE` / pipeline | steps known and ordered; deterministic orchestration, **no** model-driven control flow |
| `HARNESS__AGENT_LOOP` | `AGENT_LOOP` / agent | the next step genuinely depends on the last, and the pipeline was built and measured |
| `HARNESS__AGENT_TEAM` | `AGENT_TEAM` / multi_agent | one context provably cannot hold the work **and** the single loop was measured |

Plus the sentinel `NOTHING_SHAPED` (class `tools`, `provisional: true`) for
`roles.no_proposal`.

---

## What this ledger needs that the harness does not have yet

Written down rather than discovered later, because a ledger whose `inspect` facts
have no instruments ships gates nobody can open. The AI ledger polices this with
`known_gaps.no_instrument_measures: []` and a two-directional test; this one must
do the same.

| fact | who could measure it |
|---|---|
| `has_traces`, `tokens_per_run`, `run_terminates` | **exist** — `read_agent_traces`, `bound_the_loop` |
| `tools_n`, `tools_risk_annotated_n` | `read_tool_definitions` exists; the risk annotation is new |
| `eval_tasks_n`, `can_rerun_tasks` | a sibling of `run_the_failures` over tasks rather than failures |
| `solo_pass_rate`, `pipeline_pass_rate`, `single_loop_pass_rate` | **new** — and the hard one, because scoring a harness variant means running somebody else's system, which the `agent` pack forbids |
| `components_proposed_n`, `components_ablated_n` | **new** — the G3 instrument, and probably a new capability |
| `success_check_named` | `source: ask` — nothing to build |
| `success_check_is_a_program` | a path check, and `context.file.read` already covers the capability |

**The disjointness rule is a hard constraint on all of these.** The shipped
ledgers share zero fact names and `app/tools/registry.py`'s domain adoption
depends on it: a fact declared by two ledgers stops naming a domain. So every
name above must be new, and `read_agent_traces` measuring `has_traces` means
**this ledger cannot reuse that fact** — it needs its own, or the instrument
needs widening. That is the first real design decision the YAML forces.

---

## Why this is not a second product

Same argument the AI ledger makes. The engine does not change: it walks a ledger,
pays gates, mints a verdict, and refuses an unsubstantiated fact in a domain it
has never seen. What changes is a file of knowledge and the instruments that
answer it.

And the shape is the same shape the other two have, which is the thesis rather
than a coincidence: **the expensive irreversible thing is the one people reach
for first, almost nobody needs it, and saying so is worth more than building it.**
For ML that sentence is *do not train*. For AI engineering it is *do not build the
agent*. Here it is **do not build the harness — the model already does this, or a
script would, or the one you have has a component in it that stopped earning its
place.**
