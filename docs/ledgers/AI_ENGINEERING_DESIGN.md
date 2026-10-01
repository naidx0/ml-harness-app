# The AI engineering ledger — the domain content

This is what Phase 1 turns into YAML. It is written here first because the
content is the product and the YAML is the encoding, and because
`docs/ledgers/ai_engineering.yaml` is a live file another lane is holding.

The ML ledger took months to reach 79 outcomes and five gates. This does not
have to be complete to be useful — it has to be **honest about a small thing**
before it is broad about a large one.

---

## The question this ledger answers

**"Should you build this agent, and if not, what instead?"**

Same shape as the ML ledger's *"should you train?"*, and for the same reason:
the expensive irreversible thing is the one people reach for first, and almost
nobody needs it. Most agents are one API call and a loop somebody did not try.

---

## The gates

The ML five are: an eval set exists, a baseline is measured, prompting is
exhausted, retrieval was considered, a cheaper model was considered. Three of
these have direct analogues. **Two do not, and they are the interesting ones.**

### G0_SOMETHING_TO_MEASURE — *"Do we have failures we can check against?"*

The eval-set analogue. Ten real failures from actual use, written down, that you
can re-run. Without them every change is a guess and every claim of improvement
is a story.

Fails to: `BLOCKED__NOTHING_TO_MEASURE_AGAINST`
Recipe: ten real failures from actual use, with what should have happened.

### G1_BASELINE_MEASURED — *"Do we know how often the current thing fails?"*

The baseline analogue, and it is the number every later "it got better" is
measured against. **A rate, not an impression.** "It fails sometimes" is not a
baseline; 14 of 50 is.

Fails to: `ACTION__MEASURE_THE_BASELINE`

### G2_SIMPLE_VERSION_TRIED — *"Has the version without a loop been tried?"*

The prompting-exhausted analogue, and the gate that will refuse the most people.
One API call. A fixed sequence. A script. **Model-driven control flow is the
expensive thing** — it is the part that is slow, non-deterministic, hard to
test, and hard to bound.

Fails to: `NO_AGENT__ONE_API_CALL`

### G3_FAILURE_REPRODUCES — *"Can you make it fail on demand?"*

**No ML analogue, and this is the one this domain needs most.** Agent failures
are intermittent by nature: the same input takes a different path twice. A
failure you cannot reproduce cannot be fixed, only coincided with — and the
literature on this product's own defects says the same thing in a different
costume, because a hang and a failure are indistinguishable to whoever reads the
result.

Fails to: `BLOCKED__CANNOT_REPRODUCE`
Recipe: pin the seed, the model, the tools and the inputs, and make it fail
twice in a row before changing anything.

### G4_COST_AND_TERMINATION_BOUNDED — *"Do you know what one run costs, and does it stop?"*

**No ML analogue either, and it is agent-specific.** A training run has a known
end: the epochs finish. An agent loop does not. It can spend unbounded tokens,
call a tool a thousand times, and recurse. A build that cannot say what a run
costs and cannot prove it terminates is a build nobody can approve, and approval
is a contract.

Fails to: `ACTION__BOUND_THE_LOOP`

---

## The outcomes

Ordered the way the ML ledger orders them: **the refusals first, because they
are the product.**

### The refusals — do not build the agent

| outcome | when | what to do instead |
|---|---|---|
| `NO_AGENT__ONE_API_CALL` | the simple version was never tried | one call with a good prompt |
| `NO_AGENT__A_SCRIPT` | the task is deterministic and the steps are known | write the code; a model in the loop adds latency and doubt |
| `NO_AGENT__A_WORKFLOW` | steps are fixed, only the content varies | a fixed sequence of calls, no model-driven control flow |
| `NO_TOOLS__PROMPT_IS_THE_BUG` | tools fire correctly, the answers are still wrong | the instructions, not the tools |
| `NO_TOOLS__DESCRIPTION_IS_THE_BUG` | the right tool exists and is not called | the tool's description is what the model reads; fix that first |
| `NO_AGENT__SHIP_IT` | the failure rate is already below the target | stop; you are done and did not notice |

`NO_TOOLS__DESCRIPTION_IS_THE_BUG` deserves its own line because it is the most
common real defect in agent systems and the least often diagnosed. A tool that
is never called looks exactly like a tool that does not work.

### The blocked — cannot answer yet

| outcome | why |
|---|---|
| `BLOCKED__NOTHING_TO_MEASURE_AGAINST` | no failures written down |
| `BLOCKED__CANNOT_REPRODUCE` | the failure will not happen on demand |
| `BLOCKED__NO_TRACES` | nothing recorded what the agent actually did |

### The actions — go and find this out

`ACTION__WRITE_DOWN_TEN_FAILURES`, `ACTION__MEASURE_THE_BASELINE`,
`ACTION__CLASSIFY_THE_FAILURES`, `ACTION__BOUND_THE_LOOP`,
`ACTION__RECORD_TRACES`.

`ACTION__CLASSIFY_THE_FAILURES` is the hinge of the whole ledger, exactly as the
failure histogram is in the ML one. **Until failures are bucketed, every
remedy is a guess.** The buckets:

- **tool choice** — the wrong tool was called, or none was
- **tool execution** — the right tool was called and it failed or returned junk
- **reasoning** — the tools worked and the conclusion was wrong
- **context** — the answer was not knowable from what the model was given
- **format** — the answer was right and unusable

Each bucket routes somewhere different, and three of the five route to a
refusal rather than to a build.

### The builds — the expensive thing is the right thing

| outcome | when |
|---|---|
| `BUILD__EVAL_HARNESS` | there are failures but no way to run them repeatedly |
| `BUILD__TOOLS_FOR_AN_EXISTING_LOOP` | the loop is fine, the tools are missing or wrong |
| `BUILD__AGENT_WITH_TOOLS` | all gates pass and control flow genuinely must be model-driven |
| `BUILD__MULTI_AGENT` | one context provably cannot hold the work — **and the bar is high** |

`BUILD__MULTI_AGENT` should be the hardest outcome in the ledger to reach, for
the same reason `TRAIN__FROM_SCRATCH` is in the ML one. Most multi-agent systems
are one agent with a context problem, and the honest first answer is usually to
fix the context.

---

## The facts

| fact | source | note |
|---|---|---|
| `failing_cases_n` | inspect | counted from a file the person points at |
| `failure_reproduces` | ask | only the person can say they ran it twice |
| `simple_version_tried` | ask | their own word, and it is enough |
| `has_traces` | inspect | is there a record of what the agent did |
| `tool_count` | inspect | read from their tool definitions |
| `tool_call_success_rate` | inspect | measured from traces |
| `baseline_success_rate` | inspect | measured by running the failures |
| `target_success_rate` | ask | nobody else can set it |
| `cost_per_run` | inspect | measured, or UNKNOWN and said so |
| `run_terminates` | inspect | measured over the failure set |
| `failure_mode` | derive | the histogram bucket that dominates |
| `control_flow_is_dynamic` | ask | does the next step genuinely depend on the last |

**Note the split**: seven are `inspect` — the harness measures them and nobody's
word substitutes. That ratio matters. A ledger whose facts are all `ask` is a
questionnaire, and the ML ledger's power comes from refusing to take a number on
trust.

---

## What this ledger needs that the harness does not have yet

Written down honestly, because these become Phase 1 tool work and pretending
otherwise would put outcomes in the ledger that lead nowhere — the exact defect
that left 45 of 55 ML outcomes dead.

1. **A trace reader.** `has_traces`, `tool_call_success_rate` and `failure_mode`
   all need to read what an agent actually did. No tool does this. Format is an
   open question: OpenTelemetry GenAI semantic conventions are the emerging
   standard and are worth researching before inventing one.
2. **A tool-definition reader.** `tool_count` and the description defect need to
   read somebody's tool schemas — MCP manifests, an OpenAI tools array, a Python
   file with decorators.
3. **A failure runner.** Re-running ten failures against their system is the
   baseline instrument, and it is the analogue of `run_eval`. It probably *is*
   `run_eval` with a different adapter.
4. **A loop bounder.** Measuring cost and termination over a set of runs.

Items 3 and 4 are close to tools that exist. Items 1 and 2 are new.

---

## Why this is not a second product

Everything above rides the same engine, the same proposal loop, the same
approval contract, the same storm, the same provenance rules, and the same
refusal to invent a number. `evals.compare` and `evals.mcnemar` are as correct
for an agent's success rate as for a model's accuracy — a paired comparison over
the same failure cases, and NO EVIDENCE when the difference is inside what those
cases can resolve.

**The person never chooses this ledger.** They describe a problem and the
harness works out which discipline they are in, the same way it already works
out modality. If a conversation starts in AI engineering and turns out to be a
retrieval problem, that is a route between ledgers and not a new session.
