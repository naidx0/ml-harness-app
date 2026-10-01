# Phases — how we get from here to there

`docs/VISION.md` says what we are building. This says in what order, and how we
will know each part is done.

**Ordered by what would change the plan if it failed**, not by what is most
interesting to build. The two cheapest decisive experiments come first, because
both of them can invalidate everything after them, and both take about a day.

Every "done" below is a measurement, not a judgement. That is deliberate: a
phase that ends when somebody feels it has ended is a phase that never ends.

---

---

## EVERY PHASE READ AGAINST ITS OWN DONE-CONDITION — 2026-09-11

**This section exists because the file had never had one.** Each phase carries
its own status marker, written on the day that phase was worked, and **two of
them were stale by months** while the table at the top of the file was stale by
a fortnight. Nothing below is remembered; the command or the artefact is beside
every verdict.

| phase | its own done-condition, in short | verdict | what it rests on |
|---|---|---|---|
| **0a** | a second domain diagnoses end to end, no engine change | **MET** | `docs/ledgers/ai_engineering.yaml` loads and diagnoses; 3 ledgers registered |
| **0b** | a screenshot of a thread from a file to a verdict | **MET** | two ML journeys driven to `deviations: []` |
| **1a** | a turn sends only the blocks its diagnosis calls for | **MET** | `tests/test_a_turn_says_which_blocks_it_loaded.py`, swept |
| **1** | diagnosed, verdict often "do not", **≥3 outcomes lead to a real build** | ***MET — and the "MOSTLY DONE" marker was stale*** | **14 of 23** AI outcomes have a build against a bar of **3**; **13 of 23** are refusal-shaped; both driven-journey tests pass |
| **2** | thirty examples and no eval set reach a measured result | **MET**, and the result is NO EVIDENCE | step 7 driven 2026-09-09; the trivial baseline beat the model, which is a result and not a failure |
| **3** | *(replaced 2026-09-09)* a stage may sit at zero **only if** every dead outcome names what is absent | **MET under the replacement, NOT MET under the original** | measured above; all nine reasons read, none says "nobody wrote the proposer" |
| **4** | build, run, inspect, dispose an environment | **MET** | four verbs driven 2026-09-09 |
| **5** | **a stranger gets from zero to a DIAGNOSED PROBLEM without asking a question** | ***REACHED 2026-09-11, at 7B, with qualifications*** | rebuilt installer, three walks — see below |

### EVERY PHASE DRIVEN, NOT ONLY READ — 2026-09-11

**An audit that reads a done-condition and an audit that RUNS the thing which
proves it are different documents.** The table above is the first; this is the
second. Each row names the test that drives that phase's condition and the count
it returned when run on this tree.

| phase | driven by | cases |
|---|---|---|
| 0a | `test_a_second_ledger_runs_on_this_engine.py` | **20 OK** |
| 0b | `test_one_journey_closes_in_every_domain.py` | **2 OK** |
| 1a | `test_a_turn_says_which_blocks_it_loaded.py` | **48 OK** |
| 1 | `test_the_instruments_drive_a_gated_verdict.py` + `test_the_ai_ledger_refuses_before_it_builds.py` | **30 OK** |
| 2 | `…eval_set_is_carved_not_manufactured`, `…counted_at_any_size`, `…baseline_names_its_eval_set`, `…trivial_baseline_that_wins…`, `…refuses_data_that_leaks…` | **95 OK** |
| 3 | `test_a_stage_with_no_builds_has_a_written_reason.py` | **3 OK** |
| 4 | `…sandbox_is_disposable`, `…is_reproducible`, `…knows_which_project`, `…isolates_everything_the_product_writes`, `…recipe_says_how_to_build_its_environment` | **81 OK** |
| 5 | ***three live Windows Sandbox walks on a rebuilt installer*** | verdict reached |

***279 cases across phases 0–4, every file green, and phase 5 driven live rather
than by proxy.*** All of it also runs inside the 5,069-case gate that certified
the commit carrying this table — these were run singly so each phase's condition
has a command beside it rather than a share of one number.

**Phase 5 is the one that cannot be driven by a test on this machine**, and that
is a property of the claim rather than a gap: its sentence is about somebody who
has never seen the repository, so the only instrument that answers it is a bare
VM. That is why it is the only row here whose evidence is a walk.

### Phase 1's marker was stale, and the stale half was the one that mattered

It read **MOSTLY DONE**, and the two caveats under it were the React surface —
already found stale and struck — and the TRAIL census. **Neither is in the
done-condition.** Measured today:

    AI receivable outcomes                23
    with a real build                     14     (the bar is 3)
    refusal-shaped ("do not")             13 of 23
    tests/test_the_instruments_drive_a_gated_verdict.py    OK
    tests/test_the_ai_ledger_refuses_before_it_builds.py   OK, 28 cases

***The condition is met roughly five times over on its own numeric clause.***
The TRAIL census remains owed and is **outside the done-condition**: it governs
how far `read_agent_traces` may be trusted against third-party traces, not
whether the ledger diagnoses. It is blocked on a gated dataset needing an account
grant and a credential, and **that has not moved and will not move from here.**

### Phase 5 is the one that is genuinely open, and the reason has moved four times

**Three walks, three model sizes, one bare Windows Sandbox each**, 2026-09-10.
Install → `/health` → `/api/providers` → Ollama by zip → pull → connect →
activate → probe → thread → goal → turn, every hop measured. **Zero to
installed, connected, probed, routed, and calling tools: MEASURED. Zero to a
DIAGNOSED PROBLEM: NOT REACHED**, at any size tried.

    qwen2.5:0.5b   named the harness's tools IN PROSE and called none
    qwen2.5:3b     called the right tool with `arguments: {}`

***The gradient is the finding: argument construction is where a small local
model fails***, which is a more useful sentence than "a local model cannot drive
this".

**The reason phase 5 is open has now moved four times, and each move was a
fix:** nothing told a new person a model was needed (fixed — `mlh doctor` and
the connect banner); the walk could not install a model (fixed — the zip, after
both silent-flag families were measured dead); nothing warned when a model
*claimed* tools and called none (fixed 2026-09-11 by the intake lane at
`09dba42` / `ef5d434`, from this lane's measurement); **and what remains is that
the last hop needs a model that actually constructs arguments.**

### RE-DRIVEN ON A REBUILT INSTALLER, 2026-09-11 — and a stranger reaches a diagnosis

**The installer was rebuilt from `ac25075` and the fix proved INSIDE the wheel**
by reading its own `app/conductor.py`, not inferred from a date. Each page
prints that provenance — commit, wheel sha256 (`disk`), installer bytes, model
and arm — before anything else, so a stale-build reading is impossible.

| rung | 7B, fill on | 3B, fill on | 3B, fill off |
|---|---|---|---|
| tool chosen | yes | yes | yes |
| arguments well-formed | yes | yes | yes |
| gate paid | no | no | no |
| **verdict reached** | ***yes*** | no | no |
| journey steps done | 0 of 6 | **2 of 6** | 0 of 6 |

***ZERO TO A DIAGNOSED PROBLEM IS REACHED, at 7B:*** `BLOCKED__DEFINE_SUCCESS_FIRST`,
`trains: false`, blocked at `G0_EVAL_SET` on `eval_size_n >= 30`, unmeasured. A
stranger with no Python, no Ollama and no key installed the product, connected a
model it downloaded itself, pointed it at their own file, and was told **do not
train yet — define success first.**

***And the failure that kept this phase open is gone.*** The 2026-09-10 walk
stopped with 3B calling `map_the_ask` with `arguments: {}`. On the rebuilt
installer it called `map_the_ask`, `attach_context`, `assess_the_data`,
`carve_eval_set` and `state_facts` — four in one turn, every one with
well-formed arguments. **3B stops at an APPROVAL gate**, `carve_eval_set` being
withheld because *"an approval is not something a tool call can carry"*, which
is the product waiting on a person by design.

**THE FILL WAS NEVER OBSERVED TO FIRE in either arm** — its disclosure sentence
is absent from both threads' full message dumps, which carry `tool_calls_json`
verbatim, so the check can tell *did not fire* from *not printed*. The 3B model
supplied the argument itself both times. ***The difference between the two 3B
arms is therefore NOT attributable to the fill on this evidence***: one run per
arm, a non-deterministic model, and a mechanism that never announced itself is a
direction and not a law. Repeats would settle it.

**Two things keep the green qualified.** The walk obtains Ollama by **zip**
because both silent-flag families are measured dead, so *"a stranger gets
there"* and *"an automated walk gets there by a route a stranger would not
take"* remain two claims and only the second is measured. And **the verdict came
at 7B while 3B reached two journey steps — neither arm did both**, on one run
each.

### CORRECTION, SAME DAY: that last blocker WAS closed by writing code

**This section first said the remaining blocker "is not a defect this repository
can close by writing code". That is wrong, and the repository had already
disproved it.**

`app/conductor.py:3983-4116` carries `FROM_THE_THREAD`, which supplies a
required argument the thread is already holding — and its own comment cites
**this lane's walk (`530fc0b`)** as the measurement that produced it:

> *"the model called `map_the_ask` with EMPTY ARGUMENTS, and the harness
> answered by asking the person to say again what they had already said…
> THAT IS A PRODUCT FAULT AND NOT A MODEL ONE."*

It is wired into the tool path at line 3886, switchable for a weak-model ladder
so the fill cannot confound a trial, disclosed to the person when it fires, and
covered by 19 passing cases in
`tests/test_a_dropped_argument_is_not_the_persons_fault.py`.

***So the exact failure the 3B walk hit is fixed, and the walk has not been
re-driven since.***

### Why the verdict above still stands, and exactly what would move it

**The verdict is unchanged but its BASIS is now narrower**, and the difference
matters: phase 5 is not open because the blocker is unfixable, it is open
because **nobody has re-measured since it was fixed.**

**Re-measuring needs the installer rebuilt, and it cannot be rebuilt from here
today:**

    src-tauri/…/ML Harness_0.1.0_x64-setup.exe   built 2026-09-02
    src-tauri/resources/ml_harness-…-py3-none-any.whl   built 2026-09-02 20:08
    cargo 1.98.0, rustc 1.98.0, npm 11.6.2        present
    frontend/node_modules/.bin/tauri              PRESENT

The sandbox installs a wheel bundled at build time, so a walk driven today would
measure **the 2026-09-02 product** and would fail at exactly the place it failed
before — a result that would look like a confirmation and would be an artefact
of a stale installer.

> ***The next step on phase 5 is therefore a BUILD, not a walk: rebuild the
> installer from current source, then re-drive.***

**AND NO TOOLCHAIN INSTALL IS NEEDED — a claim this section made an hour ago and
got wrong.** It said `cargo tauri` was not installed and called the fix a
machine decision. **The project ships the CLI as an npm devDependency**
(`@tauri-apps/cli ^2.11.4` in `frontend/package.json`), `frontend/node_modules/
.bin/tauri` exists, and `.github/workflows/release.yml` builds with
`npm --prefix frontend exec -- tauri build`. **I checked for the `cargo`
subcommand, did not find one, and concluded the tool was absent** — when the
repository's own CI had been building with it all along. `beforeBuildCommand`
runs `scripts/stage_bundle.py`, which rebuilds the wheel into
`bundle.resources`, so the whole rebuild is that one command.

**The remaining question is WHERE to build, and it is a real one rather than a
formality.** The shared checkout has the warm `src-tauri/target/` from
2026-09-02 and would build incrementally, but it is **35 commits behind
`origin/main`** and other lanes use it. The `mlbuild` worktree is at
`origin/main` and clean, but has no `node_modules` and no warm target, so it
would compile Rust from scratch. **Bringing a shared checkout forward is
coordination, not a measurement, so that one is asked rather than taken.**

**And one thing the rebuild would still not settle:** the walk obtains Ollama by
zip because both silent-flag families are measured dead. *"A stranger gets
there"* and *"an automated walk gets there by a route a stranger would not
take"* remain two claims, and only the second is measurable by this machinery.

**Phase 5's sentence is honest and unmet, and saying so is worth more than
moving the goalposts to meet it** — which is the same rule phase 3's two
done-conditions are recorded under, one section above. **What has changed is
that the reason is now "unmeasured since the fix" rather than "unfixable", and
those two are not the same sentence.**

### The status table at the top of this file, re-taken

**Dated 2026-08-26 and drifted.** Only rows a command answers are restated;
the method is beside each because the table's own rule is that a number without
one is why the previous version drifted.

| row | was | **now** | how |
|---|---|---|---|
| tests | 3,281 | **5,069**, 72 skipped, 3 expected failures | tonight's gate, `OK` |
| tools | 93 | **93** | `len(list(app.tools.REGISTRY))` — 2026-09-18 (later): `read_observation` (context; ObservationPack) and `generate_tool_rows` (data; chain-first rows); earlier the same day: `compile_the_plan` (ledger, core) and P9's two programs, `build_environment` (sandbox) and `write_the_results` (training); was 88 from 2026-09-17's `set_baseline_target`. Both cells hold the live count, which is what the test reads |
| ledgers | 3 | 3 | `len(diagnosis.known_ledgers())` |
| ML outcomes | 55 | **56** | `len(ml.declared_outcomes())` |
| ML outcomes with a build | 13 | **18** | `declared_outcomes() & propose.COVERAGE` |
| AI outcomes with a build | 14 of 23 | 14 of 23 | same |
| total proposers | 43 | 43 | `len(propose.COVERAGE)` |
| stages with no build | "3 of 10" | **ML 2 of 10, AI 1 of 6** | the gate's own `_built_and_dead` |
| ways a stranger can install this | **0** | ***3 walks, installer exit 0*** | 2026-09-10, Windows Sandbox |

***"3 of 10" was a denominator fault*** — it counted BOTH ledgers' empty stages
against the ML ledger's stage count. The stages it names were right; the
fraction was not. **That is the third denominator fault this project has caught
in its own published numbers**, and like the other two it was found by
recomputing rather than by re-reading.

## Memory — three systems from Hermes, built and measured 2026-09-11

Max, on the product's memory: *"where is my consistent memory system? it is
rescanning every time"* — and, having read the memory Hermes actually keeps on
his machine (`AppData\Local\hermes\hermes-agent`): *"implement all 3 exact same
systems in ours."* Each was rebuilt in this product's idiom, and each was
measured live on his model before it landed.

| system | Hermes' | ours | measured |
|---|---|---|---|
| **recall** | `session_search`: FTS5 over every session, three shapes, no LLM | `recall` (`app/recall.py`): FTS5 over `messages`, discover / scroll / browse, scoped to the project, index healed on first use | fresh threads asking what a sibling settled: recall called **3 of 3**, answered with the reason **3 of 3**, 8–23 s |
| **memory** | `MEMORY.md` + `USER.md`, `§` entries, 2,200 / 1,375 chars, one tool | `remember` + a Memory pane (`app/memory.py`): notes per PROJECT, one profile, Hermes' limits, a number needs its origin word | told to keep a decision: model wrote it **1 of 3**; the harness keeps an explicit ask in the person's words — entry stored **3 of 3**, next thread right **3 of 3**, once from the note alone |
| **compaction** | `context_compressor`: head + token-budget tail protected, structured checkpoint, iterative | `app/compaction.py`: the same, the same model summarises, every summary line read by the provenance sentry, stored as a `thread.compacted` event — messages never rewritten | see the compaction commit for the live figures |

What was NOT taken: Hermes' pluggable external providers (one local product), and
its frozen-at-session-start snapshot (a harness turn is a request; the note can
refresh per turn). What was added everywhere: a remembered or summarised number
is never a measured one — `budget.py`'s rule, applied to memory.

## Where we actually are, 2026-08-26

Measured, not remembered. Re-taken on 2026-08-27 after the data floor's two
walls, the verification step and the three UI surfaces landed; the rows that did
not move were re-run rather than carried over, and the command that took each one
is beside it.

**One caveat on the test row and it is about a machine, not about this code.**
The suite was last run in a container with no GPU, no connected model and no
scikit-learn, where eleven cases are red for those reasons alone — the same
eleven are red there on the commit before any of this work. The count below is
therefore *tests that ran*, and the four expected failures are the declared ones.

| | | how |
|---|---|---|
| tests | **3,281, of which 11 fail for want of a GPU, a model and sklearn**; 4 expected failures | `python -m unittest discover -s tests -t tests` |
| tools | **93** | `len(list(app.tools.REGISTRY))` — 86 since AU4; 87 since 2026-09-16: CS17 `unpark_step`; 88 since 2026-09-17: `set_baseline_target`; **91 since 2026-09-18**: `compile_the_plan` (the journey written out as the plan, core) and P9's two missing programs, `build_environment` and `write_the_results`; **93 later that day**: `read_observation` (ObservationPack's door) and `generate_tool_rows` (chain-first rows) |
| capability packs | **15**, core is 3 packs / 29 tools | `app/tools/blocks.py`; see 1a below |
| tools a turn hands the model | **29–68 of 93** | RE-TAKEN 2026-09-18 (later): `read_observation` is CONTEXT (core) so both ends move by one; `generate_tool_rows` (DATA) loads on the widest sheet. Earlier that day at integration: `compile_the_plan` is LEDGER (core) so both ends move by one; `build_environment` (SANDBOX) and `write_the_results` (TRAINING) both load on the widest sheet, so the ceiling moves two more |
| tool SCHEMAS a turn sends | **9–12 of those**, 1,512–2,238 tokens | NEW 2026-09-18, `blocks.on_the_wire`: the row above is what a turn OFFERS and what the capability list names; only the tools the aimed phase, the diagnosis, the last reply or this thread's own evidence NAME arrive with their parameters. Measured with `budget.estimate` over `REGISTRY.model_tools`: all 88 cost 26,992 tokens, a fresh build thread's 48 cost 13,514 and now send 1,512. `MLH_ALL_SCHEMAS=1` restores every schema and the turn records that it did |
| ledgers that load and diagnose | **3** | `len(diagnosis.known_ledgers())` — ML (five gates), AI engineering (five), harness design (six) |
| ML outcomes | 55 | `len(load_spec().declared_outcomes())` |
| ML outcomes that lead to a build | **13** (was 12) | outcomes in `propose.COVERAGE` that the ML ledger declares |
| AI outcomes that lead to a build | **14 of 23** (was 4, then 8) | same computation on `docs/ledgers/ai_engineering.yaml`; floors asserted in `tests/test_an_action_outcome_cannot_point_nowhere.py` |
| AI `BUILD__` outcomes with proposers | **3 of 3** | `BUILD__AGENT_WITH_TOOLS`, `BUILD__TOOLS_FOR_AN_EXISTING_LOOP`, `BUILD__MULTI_AGENT` |
| total proposers registered | **43** | `len(propose.COVERAGE)` |
| stages with no build at all | **3 of 10** (was 4) | see Phase 3 below; `stage_4_format` closed 2026-08-27 |
| complete journeys recorded | **3** | two ML (0b) + one AI instrument journey (Phase B, driven) |
| ways a stranger can install this | **0** | unchanged |

**The stage count moved from 5 to 4 and the reason is the attribution, not a
build.** This table previously said 5 of 10 with no method beside it. Counting
an outcome against the stage of the node that states it - via
`Spec.outcome_sites()`, which is the only enumeration of those - the stages with
no build at all were `stage_4_format`, `stage_6_capability`,
`stage_7_efficiency` and `stage_8_offtheshelf_first`. A different attribution
gives a different number, which is exactly why the rule is written down here
now.

**And 4 to 3 on 2026-08-27, and THAT one is a build.** `stage_4_format` has one:
`ACTION__MEASURE_THE_FORMAT`, its ask node, is covered by `app/tools/shapes.py`
and a proposer over it. The three left are read again below, and the reading is
the point of the exercise rather than the count.

The engine that decides is close to complete. The engine that *does* covers a
fifth of it. **The loop has now been driven to `deviations: []` twice**, and the
sentence this paragraph used to carry - *"nobody has driven the whole loop"* -
was stale the day 0b's second journey landed. What is still true is narrower and
is the thing to keep saying: the loop closes when the path lands on a covered
outcome and stops at a coverage gap when it does not, and 43 of 55 outcomes are
the second kind. See 0b.

---

## Phase 0 — The two proofs

**Two experiments, both cheap, both able to change everything after them.** Do
not start Phase 1 until these have answers.

### 0a. A second ledger runs on the same engine — **DONE, 2026-08-24**

Write a small AI-engineering ledger — six or so outcomes, two gates, one honest
refusal — and point `load_spec()` at it.

We already know `load_spec()` takes a path, and that eight of the nine ML leaks
in `app/diagnosis.py` are the `TRAIN__` prefix. That prefix is not an ML concept:
it marks **the expensive irreversible outcome that must pass every gate**. Renaming
the role is most of the work.

**Done when:** a second domain diagnoses end to end with no change to the engine,
or we have the exact list of what is in the way.

**THE ANSWER IS YES.** `docs/ledgers/ai_engineering.yaml` loads by path, walks,
and mints its own gated verdict with its own five gates. Nothing about it is
machine learning: its prefix is `BUILD__`, its verdict vocabulary is
`[NO_BUILD, BUILD, BLOCKED]`, its gates are `G0_SOMETHING_TO_MEASURE ..
G4_COST_AND_TERMINATION_BOUNDED`, and not one ML fact appears in it. Measured,
same engine, one process:

| sheet | answer |
|---|---|
| an empty sheet | `BLOCKED__NOTHING_TO_MEASURE_AGAINST`, no gate paid |
| nine failing cases | same — G0's floor is ten |
| twenty failures, no target rate | `ACTION__SET_A_TARGET_RATE`, G0 paid |
| everything measured, simple version never tried | `NO_AGENT__ONE_API_CALL` |
| every gate paid, failures bucketed | `BUILD__MULTI_AGENT`, all five paid |
| the same run with the loop unbounded | `ACTION__BOUND_THE_LOOP`, G4 unpaid |
| the same run with the numbers only CLAIMED | `ACTION__SUBSTANTIATE_CLAIMED_FACTS` |

The last row is the one worth reading twice: the origin policy, written for the
ML ledger, refuses a claimed measurement in a domain it has never seen, with no
code that knows what an agent is.

**What changed since 2026-08-24:** the four instruments Phase 1 named now ship in
`app/tools/agents.py` (`read_agent_traces`, `read_tool_definitions`,
`run_the_failures`, `bound_the_loop`), and every AI `inspect` fact has an
instrument. The platform thesis is proven; the *content* and *surfaces* are what
Phase 1's remainder is about.

### 0b. One journey closes, on real data — **DONE**, and the first attempt is kept because it says something the second one cannot

Two journeys are recorded below. The FIRST stopped at ten rungs on a coverage
gap and is left here in full, because "the diagnosis half closes and the doing
half does not" is the measurement Phase 3 exists to move. The SECOND closes, and
has now been re-driven a third time under capability blocks. Read them in order.

#### 0b, first journey — ten rungs, then a coverage gap

Not a demo. A person's actual shape of problem, driven start to finish, recorded.

**Done when:** a screenshot exists of a thread that starts with a file and ends
with an artifact and its proof, and every number in it carries an origin.

**IT DOES NOT CLOSE, AND THE PLACE IT STOPS HAS MOVED.** Driven 2026-08-24 on a
scratch database with real data — 161 rows built from this repository's own git
log, the commit subject as the input and the top-level directory that received
the most changed files as the label — and a real local model. Ten rungs:

| rung | what happened |
|---|---|
| 1 | `assess_the_data`: 123 of 161 rows usable, 38 exact duplicates |
| 2 | `state_facts`: target 0.80, modality, task family — recorded STATED |
| 3 | diagnose → `BLOCKED__BUILD_EVAL_SET` |
| 4 | `carve_eval_set`: 31 rows / **30 distinct questions** held out, 130 to train on, **its own leak check: 0 leaked** |
| 5 | `measure_eval_set`: `eval_size_n = 31` MEASURED |
| 6 | `measure_baseline`: the model scores **0%**, a majority-class guess scores **30%**, both MEASURED |
| 7 | `state_facts` for the prompt and retrieval work → `ACTION__CLASSIFY_FAILURES`, **G0 and G1 both PASSED** |
| 8 | same |
| 9 | `run_eval`: `failure_histogram = {wrong_format: 30}` MEASURED |
| 10 | diagnose → **`NO_TRAIN__CONSTRAINED_DECODING`** — *"Never fine-tune for a format a grammar can enforce."* |

That is the right answer, reached from measurements, with every number carrying
an origin. **And it is one of the 43 outcomes with no build.**
`propose.NOT_COVERED` says exactly why: constrained decoding needs a decoding
backend that does not ship, and *"planning 'switch structured outputs on' with no
step that switches anything"* is the dead end this product refuses to write.

**So the first wall is now a COVERAGE gap, which is Phase 3's job, not a defect.**
The two defects that used to sit in front of it were found by an adversary on
2026-08-24 and are fixed:

  * **rung 4** — `carve_eval_set` drew its split by exact row signature and then
    verified it with a strictly stronger predicate (near duplicates at Jaccard
    0.8), so it could only pass its own check by luck. On this file it refused
    its own output on **12 of 25 seeds**, and on a fixture with no exact
    duplicates at all it leaked every eval row on **25 of 25**. The draw is now
    made in the units the check judges it in — whole groups of the same question,
    transitively — and on the same file it is **0 leaks over 25 seeds**.
  * **rung 7** — `S1_LABELS_ARE_NOISE` tested a ONE-sided window
    (`trivial >= baseline - 0.05`) under a sentence that said *"within 5 points"*,
    so a trivial baseline sixty-three points ahead of the model got told its
    labels were wrong. It sits directly above `S1_CLOSED_SET_CLASSIFICATION`, so
    it shut the small-encoder door on precisely the users it was opened for. The
    window is two-sided now and the run walks on.

**Why first, still:** every claim in `VISION.md` rests on the loop closing. What
this run establishes is narrower and worth stating precisely: **the diagnosis
half closes on real data.** The doing half does not, and the reason is countable
rather than mysterious — 12 built, 43 not.

---

#### 0b, second journey — **IT CLOSES.** Twelve rungs, verified, no deviations

The journey above stopped at a coverage gap. A second one, driven by the parent
lane through the real HTTP surface against granite4-hermes on a 400-row
support-ticket export, **reached a covered outcome and went all the way**.
Thread 16, storm 4.

| # | rung | what happened |
|---|---|---|
| 1–3 | arrive, measure, diagnose | `labeled_examples_n 400`, `classes_n 4` → `BLOCKED__BUILD_EVAL_SET` |
| 4 | approve a carve | 30 out, 370 to train, a manifest — real files on disk |
| 5–6 | count it, re-diagnose | 30 rows → **`G0_EVAL_SET PASSED`** |
| 7 | score the baseline | **model 0%, trivial baseline 35%, both measured** |
| 8 | re-diagnose | **`G1 PASSED`** → `ACTION__CLASSIFY_FAILURES` |
| 9 | propose | 3 steps, exit criterion stated before it ran |
| 10 | approve | `201`, on the `Build.fingerprint()` |
| 11 | storm | `run` → `read` → `recheck`, all done |
| 12 | verify | `ok: true`, **`deviations: []`** |

The verification, verbatim, because it is what the whole design rests on:

```
"stated":  "failure_histogram is MEASURED - buckets this harness produced
            from rows it graded itself, not a shape somebody described"
"saw":     "MEASURED"
"because": "origin is 'MEASURED', and only MEASURED counts here"
```

**Both journeys are true and they say different things.** The loop CLOSES when
the path lands on a covered outcome, and STOPS AT A COVERAGE GAP when it does
not. That is Phase 3's job, and both runs independently reached the same
conclusion: the machine works and the content is thin.

**And both found the same thing about the product's real value.** Two unrelated
datasets, two different models, and in both cases the connected model scored
**zero** while always answering the commonest label scored **30–35%**. The
trivial baseline beat the model twice. Nothing about that was constructed.

---

#### 0b, second journey, RE-DRIVEN 2026-08-24 under capability blocks — **IT STILL CLOSES**

Not remembered. Re-driven on a scratch database against granite4-hermes over the
same HTTP surface, with the blocks change in the tree, on a 30-row support-ticket
eval set. The four steps of the `ACTION__CLASSIFY_FAILURES` build all ran:

```
rung 8   -> ACTION__CLASSIFY_FAILURES  {G0_EVAL_SET: PASSED, G1_BASELINE_MEASURED: PASSED}
rung 9   -> [(count, measure_eval_set), (run, run_eval), (read, read_eval_results),
             (recheck, run_diagnosis)]
rung 10  -> 201
rung 11  -> 200  ['done', 'done', 'done', 'done']
rung 12  state: done      deviations: []
         verification: {"ok": true,
           "stated": "failure_histogram is MEASURED - buckets this harness produced
                      from rows it graded itself, not a shape somebody described",
           "saw": "MEASURED",
           "because": "origin is 'MEASURED', and only MEASURED counts here"}
```

**The model scored 0.0 over 20 graded rows and the buckets were
`{wrong_format: 19, refuses: 1}`**, so the recheck landed on
`NO_TRAIN__CONSTRAINED_DECODING` — the first journey's answer, reached
independently on different data. Nothing about that was arranged.

Two honest notes. Rungs 1 and 5–7 were stamped as stand-ins through the same
instrument channel the tools use, because this run was about whether the loop
closes under blocks rather than about re-measuring a baseline. And the blocks did
not stand in the way: on that thread the turn loaded 21 of 40 tools and
`run_eval` was one of them.

---

## Phase 1a — Capability blocks (a prerequisite, not a nicety)

Max, 2026-08-22, asking how the format should be organised so it stays
model-agnostic: *"the machine learning information block ... that's where we get
that context and that instruction set."*

Three quarters of this already exists and none of it is bound together:

- **Per-domain knowledge** is the ledger. Built.
- **Conditional instructions** already exist — `app/instructions/cond_*.md` load
  on a condition rather than always. Keyed on situation, not domain.
- **Tool grouping** exists — every tool declares `group` (Look, Context, Data,
  Decide, Choose, Train) — but it is a UI label. Nothing loads or unloads by it,
  and all 40 tools reach the model on every turn.

**The pressure is measurable in our own history.** The standing brief's character
budget has been raised three times as tools were added: 2,400 → 2,600 → 3,200.
One lane hit it mid-build and trimmed its verbs to fit. Every tool taxes every
turn for every model forever, and *model-agnostic* is exactly where that bites:
40 tools is fine for a frontier model and hopeless for the granite-class model
actually connected on this machine.

**The design, and the one correction to the obvious version:** blocks are
ADDITIVE, NOT EXCLUSIVE. A core is always loaded — look at the machine, read
files, the evidence ledger — and domain packs layer on top. If the ML block hid
the data tools we would have rebuilt tabs on the inside, where the user cannot
even see them, and the moat is holding the machine, the data, the repo and the
budget at once.

**Why a block beats the alternatives, and it is an advantage almost nobody has.**
MCP servers, Skills, tool search and RAG-over-tool-descriptions all make *the
model* find the right tools. We do not have to. **The ledger has already
diagnosed the domain** before the model says a word. The pack is not retrieved or
guessed — it is selected by the thing that already knows the answer.

**Done when:** a turn sends the model only the blocks its diagnosis calls for,
the brief's budget stops rising as tools are added, and the active block is
visible in the interface as a label rather than a choice.

### **DONE, 2026-08-24 — and it was not done when it was first declared**

All three conditions hold and every one of them is a measurement below. It is
recorded in two parts because the second part is the interesting one.

**What was built.** `app/tools/blocks.py` implements
`docs/CAPABILITY_BLOCKS.md`: a block is a namespace on a capability name
declared once on the tool (`provides=("data.eval_set.carve",)`), the engine
publishes the closed vocabulary, the pack is the first dotted segment, and the
active set is computed from the standing diagnosis that already runs before the
model speaks. All 40 tools declare `provides=`; `registry._validate` refuses one
that does not. Eleven packs; the core is `ledger`, `context`, `machine`, which is
12 tools. `run_turn` computes `blocks.active(...)` once and three surfaces read
that record; `turn.started` carries `blocks`, `blocks.changed` fires when and
only when the set moves, and `frontend/src/lib/transcript.ts` draws it as a
notice strip. `REGISTRY.controls()` is NOT scoped — 40 of 40 — so a wrongly
scoped turn is recoverable by a button, and `app/instructions/capabilities.py`
still names every registered tool, marking the loaded ones.

**AND THEN AN ADVERSARY REFUTED IT, AND WAS RIGHT.** The first version had four
selection sources and every one of them keyed on a FACT: what a failed gate is
waiting on, what an alternative would settle, what this thread has already
stamped. All three look BACKWARD, at work already behind the answer. **Nothing
read the answer.** So a pack whose tools declare no `measures=` was unreachable,
and five packs are exactly that — because measuring and DOING are different
jobs and it is the doing tools that stamp nothing:

| pack | tools | tools declaring `measures=` |
|---|---|---|
| prompt | 2 | 0 |
| tabular | 1 | 0 |
| models | 2 | 0 |
| training | 6 | 0 |
| sandbox | 4 | 0 |

Swept over every fixture sheet the ML corpus has, before the fix:

```
UNION of packs ever selected: ['context','data','ledger','machine','measurement','retrieval']
NEVER activated:              ['models','prompt','sandbox','tabular','training']
tools in never-activated packs: 15 of 40
```

**A thread whose verdict was `TRAIN__LORA_SFT` could not be handed
`start_training`.** A thread whose answer WAS the tree could not be handed
`fit_a_tree_model`. That is a regression in the ML path dressed as a saving, and
`not_loaded`'s help shipped a sentence — *"the work this tool belongs to loads
with the answer they reach"* — that the selector could not keep for 15 of 40
tools.

**The fix is the ledger declaring what its own stages' work needs**, which is the
mechanism `docs/CAPABILITY_BLOCKS.md` designed and neither shipped ledger had
written. `contract.capabilities.needs` in `docs/diagnosis_engine.yaml`, one line
per stage, taken from `Spec.outcome_sites()` rather than guessed — and
`blocks.declared` now REFUSES a block that names some of a ledger's stages and
not all of them, so the defect cannot return by omission. `stage_9_method_selector:
[training, sandbox, models]`; `stage_8_classical: [tabular, data, measurement]`;
`stage_0_admissibility: [data]`. The AI ledger declares five stages of `[]`, with
the reason written above them: not one tool in this harness measures one of its
facts, and borrowing the ML packs would put a tool in the model's hands whose
success writes the other ledger's fact ids.

After the fix, same sweep, and the assertion is now in the suite:

```
UNION of packs ever selected: all 11
NEVER activated:              []
every registered tool reaches the model on some sheet: 40 of 40
```

**The three done-conditions, measured.**

| condition | measurement |
|---|---|
| only the blocks the diagnosis calls for | 12–27 tools of 40 across the ML corpus; 18 on an empty thread; 12 on every AI sheet |
| the budget stops rising | `test_adding_a_tool_does_not_grow_a_focused_turn` registers a 41st tool in the `training` pack and asserts the empty-ledger brief does not move by one character — with the negative beside it, that the UNSCOPED brief grows by exactly that tool's line |
| the block is a visible label | `blocks.changed` with `added`/`removed`/`because`, drawn by `transcript.ts`, asserted against the payload the conductor actually writes |

**The brief, in characters, over every sheet both ledgers have:**

| | before | after |
|---|---|---|
| ML, empty ledger | 2,398 | **1,105** (18 tools) |
| ML, longest of 73 sheets | 2,784 | **1,847** (`NO_TRAIN__RULED_OUT_EARLIER`) |
| AI, empty ledger | 2,398 | **755** (12 tools) |
| AI, longest of 20 sheets | 2,788 | **1,145** (`ACTION__BUILD_AN_EVAL_HARNESS`) |

**And the number this table replaces was overstated, which is worth keeping.**
It read 755 and 1,715 for the ML rows. Split three ways on an empty ML thread:
2,398 for all forty tools, 1,545 for the twenty-five that were REACHABLE, 755 for
the twelve chosen. **853 characters — 52% — of the advertised saving was fifteen
tools priced as though they had been scoped when they had been made
unreachable.** The honest saving was 790. It is 1,293 now, and every character of
it is a tool some other thread can still be handed.

`WhatItCostsTest.BUDGET` stays at 3,200 and now bounds the degenerate shape — a
turn whose walk could not be computed, which loads everything on purpose.
`FOCUSED_BUDGET = 1,900` bounds an ordinary scoped turn and was NOT raised: it
leaves 53 characters over the worst of the four, less headroom than this file's
bound has ever carried, deliberately.

**What is still honest about it.** Every AI-ledger sheet selects exactly the 12
core tools, because no tool here measures one of that ledger's 16 facts. The
blocks do not hide that; the ledger now says it in its own document.

---

## Phase 1 — The AI engineering ledger

The pivot, made real. This is the largest content effort in the plan and it is
content, not architecture, if Phase 0a succeeds.

**Done when:** a person describing an agent problem is diagnosed, gets a verdict
that is often "do not", and at least three outcomes lead to a real build.

### ~~**MOSTLY DONE, 2026-08-26**~~ — **DONE against its own done-condition, MEASURED 2026-09-11**

**The "MOSTLY" was stale and both of its reasons were outside the done-condition.** 14 of 23 AI outcomes lead to a real build against a bar of three, 13 of 23 are refusal-shaped, and both driven-journey tests pass. The React surface was closed 2026-08-27 and struck below; the TRAIL census is owed, is blocked on a credential, and **governs how far `read_agent_traces` may be trusted rather than whether the ledger diagnoses.** See the phase audit at the top of this file.

#### What landed, 2026-08-26 — instruments, builds, and one driven journey

The content was designed in `docs/ledgers/AI_ENGINEERING_DESIGN.md` and encoded
in `docs/ledgers/ai_engineering.yaml`. Format research lives in
`docs/AGENT_INSTRUMENTS.md`. What landed on `main` at `972f906`:

| piece | status | where |
|---|---|---|
| five gates | **done** | `ai_engineering.yaml` |
| 23 outcomes | **done** | `ai_engineering.yaml`; content quality asserted in `tests/test_the_ai_ledger_refuses_before_it_builds.py` |
| four agent instruments | **done** | `app/tools/agents.py` — OTLP/JSON traces, static tool defs, failure re-runs, loop bounding |
| three `BUILD__` proposers | **done** | `propose.py` — all three execute through storm with `deviations: []` in the driven test |
| per-thread ledger | **done** | migration `v011`, `threads.ledger`; merged before this branch |
| Phase B driven journey | **done** | `tests/test_the_instruments_drive_a_gated_verdict.py` — instruments → gates → storm → verify |
| journey report (backend) | **done** | `app/journey_report.py`, `GET /api/threads/{id}/report`, `GET /ui/report/{id}` |
| journey export (backend) | **done** | `GET /api/threads/{id}/export` |
| first-run discovery | **done** | `providers.discover()`, wired in `ConnectModel.tsx` |
| studios frame (backend) | **done** | `GET /api/studios` |

**What is still honest about it:**

- ~~**No React surface for the report or export.**~~ **STALE — closed
  2026-08-27 by queue step 1** and never struck here.
  `frontend/src/components/JourneyActions.tsx` is that surface, driven in
  Chromium against a scratch engine: the report opens from the app bar and
  renders the verdict, the five-gate ledger and `eval_size_n 40 MEASURED
  measure_eval_set`, and the export downloads `ml-harness/journey-export` v1
  carrying `code_fingerprint`. **The queue marked it done and this list did
  not**, which is the same drift the eight index-page numbers were: a status
  correct when written and never re-read against the thing it described.
- **TRAIL census still owed, and it is BLOCKED ON A DOWNLOAD.** The trace
  reader has been tested on synthetic fixtures shaped like real OTLP/GenAI
  exports, not on a public annotated corpus. `read_agent_traces` should not be
  trusted against third-party traces until that census is run and recorded in
  `docs/AGENT_INSTRUMENTS.md`.

  **Checked 2026-09-10, and the cache entry is a trap.**
  `~/.cache/huggingface/hub/datasets--PatronusAI--TRAIL` **exists** — which
  reads, in a directory listing beside three real model caches, as though the
  corpus is on this machine. It holds **one file, forty bytes**: `refs/main`,
  a commit sha and nothing else. **No snapshot, no blobs, no traces.** A
  bookmark wearing a cache's directory layout.

  So the census needs a fetch, and the fetch is somebody's decision rather than
  a measurement anyone here can take. **This is the same shape as the Qwen
  weights** — and the same shape as every other defect this file records: a
  thing that cannot distinguish *"downloaded"* from *"referenced"* gets read as
  the reassuring one.
- **Nineteen AI outcomes correctly have no build.** Refusals like
  `NO_AGENT__ONE_API_CALL` are the product; they belong in `NOT_COVERED` with an
  explanation, not in `COVERAGE` with a fake proposer.

**The trap:** writing outcomes we cannot act on. Two real builds beat six that
mislead. An outcome with no honest build is a dead end and we have measured what
those cost - 43 of 55 in the ML ledger, for exactly this reason.

---

## Phase 2 — The data floor

Six places in the ML ledger stop on *you do not have the data*, and the AI
engineering ledger will stop on *you have nothing to measure against* just as
often. This is the most common wall in both domains.

**What it contains:**

- Synthesis from the user's own snippets — amplifying **structure**, not
  inventing **content**. Max named the reference: a makemore-shaped generator
  learns the SHAPE of what you give it. That is the honest half. Generating a
  thousand more replies in your house style from thirty of yours is shape;
  generating a thousand more factual question-and-answer pairs is fabrication at
  scale and will train a model to be confidently wrong. **The tool must know
  which one it is being asked for and refuse the second.**
- The four rules from `VISION.md`, enforced in code rather than documented:
  never the eval set, tagged at the row, cannot open a gate, structure not
  content.
- The 10% human verification the ML ledger already prescribes, as a real step.

**Done when:** a person with thirty examples and no eval set can reach a measured
result, and no generated row has ever opened a gate.

### **STARTED 2026-08-26, WALLED 2026-08-27**

`app/tools/datawork.py::synthesize_rows` amplifies **structure** by sampling with
replacement from the user's own rows, tags every synthetic row, refuses
in-place writes, and refuses a missing answer column. Asserted in
`tests/test_synthesis_is_structure_not_content.py`.

**And, 2026-09-12, the inventive half** — `app/tools/invent.py`, on Max's
"lets create our own invent a dataset tools": `generate_rows` has a connected
model write new prompt/answer rows for a task from the person's seeds (two
answers per prompt on request), and `judge_rows` scores them 0–10 against the
person's rubric, keeps the ones above the bar, and writes chosen/rejected
pairs for `hf-peft-dpo` — the generator and judge of the loop Adaptive ML
sells. Every row carries `generated`, `synthetic`, the generator, the task and
the seeds it saw; every judged row carries `judge_score` and `judge_model`;
neither can open a gate, and both walls below apply to them unchanged because
they carry the same `synthetic: true` tag. Asserted in
`tests/test_a_dataset_can_be_invented.py`.

**And then the two walls, which are the part that makes it safe rather than
merely tagged.** `synthesize_rows`' own docstring said what tagging left open:
*"nothing here checks whether a later call points measure_eval_set at it - that
gate still reads the file that exists"*. The writer is the end that cannot
enforce this.

- **A generated row cannot open a gate.** `Instrument.measured(from_file=...)`
  is wall 8, beside the seven that already stop a number being laundered: a fact
  measured off a file holding generated rows is refused at the STAMP, which is
  the one place every MEASURED row in this product passes through. Driven:
  amplify 12 real rows into 200, point the counter at them, `ok: false`, nothing
  stamped, G0 shut. All 22 file-reading stamps in `app/` name their file and a
  structural sweep asserts the four that do not are the four that read this
  machine.
- **A generated row cannot become weights.** `draw_verification_sample` writes
  10% of the file out for a person to read; `record_verification` files what
  they said, bound to the file's sha256; `start_training` refuses until that
  record exists and found nothing wrong. This is the ledger's own recipe -
  *"have a human verify a 10% sample before training on any of it"* - which had
  been a sentence in a data file that nothing enforced.

Both are the same lesson from two directions: a rule enforced at the writer is a
rule the next call routes around.

### **STEP 7 DRIVEN 2026-09-09 — the chain closed to a trained artefact, and reading the sample found something**

Driven on this machine, which has the connected model the earlier container did
not: thirty real rows from `runs/honest-path/train.jsonl` → `synthesize_rows` to
200 → `draw_verification_sample` drew 20 → **read** → `record_verification`
("20 right, 0 wrong") → `start_training` → **60 steps, 26.0s, peak VRAM 0.63 GB,
adapter written**.

**The gate is proven in BOTH directions, which is the part that matters.** The
same synthetic file, unverified, is refused at `start_training` with
`not_verified`, quoting the ledger's own recipe back. Verified, it proceeds. A
wall only tested on the side that passes is not tested.

**AND READING THE SAMPLE FOUND WHAT COUNTING IT WOULD NOT.** `synthesize_rows`
is a RESAMPLER, NOT A GENERATOR. Measured over the 200 rows it wrote:

    synthetic rows written          200
    DISTINCT (instruction, answer)   30
    every row a verbatim copy?     True
    most-repeated row appears        12 times

It fabricates nothing — the safety property this phase cared about most, and the
tagging and both walls are sound. But 200 rows carrying 30 questions adds no
information a trainer can use; training on that file is training on thirty
examples with a different epoch count, and **nothing in the pipeline says so**.
Tagged, counted, walled and honest — and still not amplification. That is a
finding a human verifier catches and a passing test does not, which is the
argument for the 10% read being a person rather than a checksum.

### The measured half, 2026-09-09 — **STEP 7 IS DONE, and the result is NO EVIDENCE**

Three arms, one instrument, the same 24 held-out rows of
`runs/honest-path/eval.jsonl`, all graded by `granite4-hermes` as judge:

| run | arm | score |
|---|---|---|
| 58 | `SmolLM2-135M`, adapter disabled | 2/24 = **8.3%** |
| 57 | `SmolLM2-135M` + the LoRA from job_4 | 6/24 = **25.0%** |
| 56 | `granite4-hermes` off the shelf, the G1 anchor | 5/24 = **20.8%** |

**And the answer this phase exists to be able to give is NO EVIDENCE, in those
words.** `evals.compare(58, 57)`: 8 discordant rows, McNemar two-sided exact
**p = 0.29**, `resolved: false`, and it names what would settle it — **70 rows**.
Adapter against the anchor is weaker still: 7 discordant, **p = 1.00**, 1,107
rows to resolve. A tripling of the score, reported as no evidence, because 24
rows cannot carry it.

That is the done-condition met. Thirty real examples reached a measured result,
and the measurement's verdict is that the number is not yet a number.

**THE INSTRUMENT WAS WRONG FIRST, AND THAT IS THE REUSABLE PART.** The anchor was
first run under `contains` (run 55). `grade` computes `CONTAINS: wanted in got` -
the whole expected reply must appear verbatim - and the expected replies here run
8 to 32 words, **median 18**. No model reproduces an 18-word free-form sentence
verbatim, so every arm scores 0 and the comparison cannot tell *the adapter did
nothing* from *the metric sees nothing*. **That is this project's own recurring
defect** - a state that cannot distinguish did-not-run from ran-and-found-nothing
- and it would have sat in the phase's headline number. `model_graded` was not
chosen because `contains` gave a bad number; it is what this project already used
on this dataset (run 50, thread 33, same judge), and the flaw is a property of
the instrument knowable before running it.

**Two things the tooling got right that prose got wrong.** The adapter's base is
`SmolLM2-135M`; the sandbox's `purpose` string says it trains SmolLM2-1.7B.
`_adapter_at` reads `base_model_name_or_path` out of `adapter_config.json`
instead of believing the label, which is the only reason the arms are named
correctly here. And `score_the_adapter` refused an anchor from another thread
before any of this, which is what forced the anchor to be measured rather than
borrowed.

### The adapter and ONE SENTENCE reach the same score — measured 2026-09-09

Found while building the quantisation recipe, by noticing that its "base" arm
disagreed with step 7's. **The two runs used different prompts**, and step 7's
`{input}` was the bare question with no instruction at all. Controlled in ONE
code path (`recipes/hf-quantize` eval), same dtype, same seed, same judge, only
the prompt differing:

| arm | prompt | score |
|---|---|---|
| `SmolLM2-135M`, untouched | `{input}` | **1/24** |
| `SmolLM2-135M`, untouched | one instruction sentence | **6/24** |
| `SmolLM2-135M` + the trained LoRA (run 57) | `{input}` | **6/24** |

**The trained adapter and one sentence of English land on the same number**,
while the untouched baseline sits at 1-2/24. Run 58's 2/24 through the other
recipe agrees with 1/24 here, so the code paths are consistent and the prompt is
the variable. Whatever the LoRA bought, the sentence bought too - and step 7
never ran the sentence.

**That is `G2_PROMPT_EXHAUSTED`, and it is the gate this whole product exists to
enforce.** It was not bypassed: `start_training` checks the synthetic-data
verification wall and **does not consult the five gates**, because the gates
guard the route from a diagnosis to a `TRAIN__` outcome. I called the tool
directly instead of asking the engine whether to train, so the gate was never
consulted rather than defeated. **The harness would have refused this run had it
been asked.** The honest reading of step 7 is therefore stronger against the
adapter than the NO EVIDENCE verdict alone suggests, and the prompt arm belongs
in the comparison before any adapter is scored again.

The prompt effect is itself unresolved at this size - 1 vs 6 is McNemar
**p = 0.125** - which is the same finding one more time: **24 rows resolve
nothing here.**

### What the NO EVIDENCE verdict rests on, and what would overturn it

A pipeline that reaches a trained artefact and reports no evidence is only
useful if the next reader can tell which of three things it means. **It is the
third, and the other two are ruled out by numbers rather than by preference.**

* **NOT "the training did nothing."** The adapter changed **8 of the 24 rows**,
  and the change is **6:2 in its favour** - six rows the adapter got right and
  the base did not, two the other way. Something happened.
* **NOT "the eval could not see it."** `model_graded` separated the arms by 16.7
  points. More decisively, on 8 discordant pairs the exact two-sided binomial
  reaches **p = 0.0078 at an 8:0 split** - so a set this size COULD have declared
  significance and the instrument was not the ceiling. (`contains` genuinely was
  blind: 0 for every arm, which is the case this is being contrasted with.)
* **IT IS "the comparison was never powered to show it."** 6:2 on 8 pairs is
  **p = 0.2891**. The full ladder at n=8: 8:0 → 0.0078, 7:1 → 0.0703, 6:2 →
  0.2891, 5:3 → 0.7266. **Only a perfect split would have resolved.**

**What would overturn it**, holding the observed 3:1 ratio as rows are added:

| rows | discordant | p |
|---|---|---|
| 48 | 12:4 | 0.0768 |
| **72** | **18:6** | **0.0227 — resolved** |
| 96 | 24:8 | 0.0070 |

**Two independent methods agree on the same answer.** `resolution_for` put it at
**70 rows** from the Wilson interval; the exact binomial on the observed
discordant ratio puts it at **72**. Neither number was quoted from a rule of
thumb. **The finding is that the eval set is three times too small**, and that
is a sentence about `runs/honest-path/eval.jsonl` - not about the adapter.

**WHAT THIS ARTEFACT OPTIMISES, stated because a sibling lane asked and because
two different evals are in flight at once.** The job_4 adapter is trained on 200
rows resampled from 30 real replies of one bookshop and scored on 24 held-out
replies from the same shop, by a model judge asked whether the reply agrees with
the reference. **It is not node-label F1 and it never was.** The architecture-JSON
eval, its node-label metric, and the 79% that one instruction sentence reached on
it belong to a different dataset, a different base model and a different lane;
that floor does not transfer here and quoting it against this artefact would be
comparing two evals that share nothing but a machine. The floor that binds this
artefact is run 56 on its own rows: **20.8%**.

**Measured, not assumed:** `granite4-hermes` was never resident while
`bonsai-tuned` held the card - `OLLAMA_MAX_LOADED_MODELS=1`, so naming a
non-resident model evicts and reloads 4.2 GB per request. That, not the model,
was the 160s/row. Liveness checks must never name a model.



**The trap:** this is the most dangerous feature in the product. Everything
downstream of fabricated data is a statement about a distribution we invented. If
it cannot be done under the rules, it should not be done at all.

---

## Phase 3 — Coverage

The grind. Both ledgers, worst-first by dead ends.

For ML the order is measured, and the numbers here were RE-TAKEN on 2026-08-24
because the ones that stood before disagreed with the file. Attributing each
outcome to the stage of the node that states it, through `Spec.outcome_sites()`:

| stage | built | dead |
|---|---|---|
| stage_9_method_selector | 1 | **12** |
| stage_8_classical | 1 | **10** |
| stage_4_format | 1 | 4 |
| stage_7_efficiency | **0** | 5 |
| stage_5_behaviour | 2 | 4 |
| stage_3_knowledge | 3 | 4 |
| stage_0_admissibility | 2 | 3 |
| stage_1_baseline | 2 | 3 |
| stage_6_capability | **0** | 3 |
| stage_8_offtheshelf_first | **0** | 1 |

Two orderings fall out of that and they are different questions. **Worst by dead
count** is stage 9 then stage 8. **Worst by having nothing at all** is the stages
with a zero in the built column, and those are the ones where a user gets no
build whatever they arrive with. The second list is the one this phase is "done"
against.

**And the outcome the only real journey so far actually reached is in neither
list's top slot:** `NO_TRAIN__CONSTRAINED_DECODING`, in stage 4. It needs a
decoding backend, which is a dependency, which is its own step - see
`propose.NOT_COVERED`, which says so in the file rather than here.

### Re-taken 2026-09-09 — the table above is stale, and it was measuring one ledger

Recomputed from `Spec.outcome_sites()`, `Spec.node_stage` and
`propose.COVERAGE` on 2026-09-09. **Every cell above moved**, and the reason
the old table cannot simply be patched is that it never said which
attribution rule produced it.

**THE ATTRIBUTION RULE, STATED, because the count depends on it.** Five ML
outcomes are stated by nodes in MORE THAN ONE stage - `REROUTE` in four,
`BLOCKED__COLLECT_OR_SYNTHESIZE_DATA` in five, plus
`ACTION__RE_BUCKET_THE_FAILURES`, `NO_DEEP__FIND_THE_MISSING_FEATURE` and
`NO_TRAIN__SHIP_AS_IS`. Counting each outcome once, at the first stage that
states it, hides them; counting it in every stage that states it does not.
**The table below uses "every stage whose node states it."** Under the
first-seen rule stage_7_efficiency reads 0/4 and stage_8_offtheshelf_first
reads 0/1 - the same three stages have zero builds either way, so the
conclusion is not an artefact of the rule.

| ledger | stage | built | dead |
|---|---|---|---|
| ML | stage_9_method_selector | 3 | **12** |
| ML | stage_8_classical | 2 | **10** |
| ML | stage_7_efficiency | **0** | 5 |
| ML | stage_1_baseline | 1 | 4 |
| ML | stage_3_knowledge | 3 | 4 |
| ML | stage_4_format | 1 | 4 |
| ML | stage_0_admissibility | 1 | 3 |
| ML | stage_5_behaviour | 3 | 3 |
| ML | stage_6_capability | 1 | 3 |
| ML | stage_8_offtheshelf_first | **0** | 2 |
| AI | stage_0_can_we_answer | 1 | 4 |
| AI | stage_5_control_flow | **0** | 3 |
| AI | stage_9_shape_selector | 3 | 3 |
| AI | stage_1_reproduce | 2 | 1 |
| AI | stage_2_not_the_loop | 3 | 0 |
| AI | stage_3_tools | 2 | 0 |

ML holds 58 distinct outcomes, 18 built; AI holds 27, 14 built. **stage_6_capability
is no longer at zero** and stage_5_behaviour gained one, so the grind has been
moving even where nobody was writing it down here.

### The done-condition as written is wrong, and this is the evidence

**"No stage in either ledger has zero builds"** would be satisfied by writing
proposers into the three stages below. Read one at a time, their own recorded
reasons say a build there would be a defect rather than coverage - and the
`ACTION__COUNT_THE_ROWS` trap this file already names is exactly the shape of
building something to move a number.

* **AI `stage_5_control_flow` (0/3) - correctly dead, and the invariant is why.**
  `NO_AGENT__A_SCRIPT`, `NO_AGENT__A_WORKFLOW`, `NO_AGENT__ONE_AGENT_FIRST`.
  Thirteen refusals across the two ledgers DO have builds, including
  `NO_AGENT__ONE_API_CALL` one stage earlier, so "a refusal cannot have a build"
  is not the reason and would be false. The reason is narrower and it is
  structural: those thirteen are buildable because the harness can MEASURE the
  alternative it recommends - run the one API call over the failures and show the
  rate. The alternative here is *code the person writes and runs*, and
  **no shell execution** is an invariant. `run_the_failures` says so in its own
  docstring: it grades answers they hand us rather than driving their system,
  because "their code is theirs." A build for these three would have to run it.
* **ML `stage_8_offtheshelf_first` (0/2) - blocked on an instrument, not a proposer.**
  Reached only for image and audio data. All three scorers here send TEXT to a
  chat provider; the roster went from one to three during a past milestone and
  the conclusion never moved, because more ways to send text is not a way to
  score audio. What changes it is an adapter that sends pixels or samples.
* **ML `stage_7_efficiency` (0/5) - three of five are the person's judgement.**
  `ACTION__FIX_QUALITY_FIRST`, `BLOCKED__LICENCE` and `NO_TRAIN__SHIP_AS_IS` ask
  what your bar is and whether a licence is acceptable; automating them would be
  inventing the user's judgement, which is inventing a number wearing a
  different coat. `NO_TRAIN__CACHE_AND_ROUTE` is a serving layer and
  `PRODUCT_SPEC` 6.4 draws the line outside it on purpose.

**But the fifth one in stage 7 is a real opener, and it is cheap.**
`NO_TRAIN__QUANTIZE`'s recorded reason names its own remedy - *"a quantising
backend - a recipe, not a proposer."* Measured 2026-09-09: `jobspec.KINDS`
already admits `"convert"`, and `propose.THE_SCORING_KINDS` is already
`("eval", "convert")`. **No engine change is required; nothing implements the
kind.** That is the same shape as the one-line `kinds = ["train", "eval"]` fix
that unblocked adapter scoring, and it lives entirely in `recipes/`. Doing it
takes ML stage_7_efficiency off zero honestly, by building the thing the
outcome actually recommends.

### stage_7_efficiency is off zero, 2026-09-09 — `recipes/hf-quantize`

Built, and it measures rather than asserts. `kinds = ["convert", "eval"]`, its
own pinned venv, bitsandbytes NF4. On `SmolLM2-135M` over the same 24 rows, same
judge:

| | peak VRAM | generate | score |
|---|---|---|---|
| fp16 base | 0.314 GB | 74.3 s | 6/24 |
| 4-bit NF4 | **0.125 GB** | **120.1 s** | 4/24 |

**Memory is real and deterministic: −60%.** **Speed is real and it is WORSE:
1.6x slower**, because on a 135M model the dequantisation cost dominates the
matmul it saves - which is the opposite of what the outcome's own advice implies
and is exactly why this had to be measured rather than recommended. **Quality is
NO EVIDENCE**: 8 discordant rows, McNemar **p = 0.7266**.

So `NO_TRAIN__QUANTIZE` can now be answered with three numbers instead of a
sentence, and one of them contradicts the folklore. The recipe grades nothing
itself, on purpose - two graders would be two instruments - so the verdicts come
from the same judge as every other number on this thread.

**One defect found in my own recipe, and it is the recurring one.** `emit()` was
passed `compute_dtype` twice, so the eval crashed after generating every answer.
The pipeline returned exit 0 and the only symptom was that the final summary
line never printed. I read the exit code as success once before catching it:
**a run that dies after doing the work looks exactly like a run that finished.**

**Done-condition, replacing the one above, and it is ENFORCED rather than
proposed:** a stage may have zero builds ONLY IF every dead outcome in it has a
written reason in `propose.NOT_COVERED` naming what is absent - an instrument, a
backend, or a judgement that is the person's. No stage may sit at zero merely
because nobody wrote the proposer.
`tests/test_a_stage_with_no_builds_has_a_written_reason.py` checks it on both
ledgers, with a positive control that fails if no stage is empty (which would
make the check vacuous) and a second that stops it drifting into "every dead
outcome anywhere needs prose".

**It went red the moment it was written, and the defect was in the COUNT.**
`REROUTE` was being charged to four ML stages as an uncovered outcome. The
ledger declares it `terminal: false` / *"continue at another stage"*, and
`Spec.declared_outcomes()` - the engine's own set of 55 outcomes a person can
receive - excludes it. A build for `REROUTE` is meaningless because the walk
simply carries on. **Every count published above this line over-charged it**,
and the test now filters on `declared_outcomes()` rather than on a hardcoded
name.

**Corrected counts** (receivable outcomes only, deduped per stage-and-outcome).
ML: 55 receivable, `stage_8_classical` 2/9, `stage_1_baseline` 1/3,
`stage_6_capability` 1/2, `stage_8_offtheshelf_first` 0/1. AI: 23 receivable, and
`stage_9_shape_selector` is **3 built / 0 dead** rather than 3/3 - the AI ledger
is in better shape than the table above says. **The three zero-build stages are
the same under all three attribution rules tried**, so that conclusion never
depended on the counting.

**The table above is kept and not corrected in place** because the numbers are
now computed by the test rather than transcribed, and a table in a document is
what drifted twice already. Read the test.

### Correction: the recipe did NOT take stage_7 off zero

An earlier commit message in this lane said `recipes/hf-quantize` "takes ML
stage_7_efficiency off zero builds." **That is wrong and it is withdrawn.**
`propose.COVERAGE` counts PROPOSERS, and a recipe is a backend. Measured after
the recipe shipped, `stage_7_efficiency` is still **0 built / 5 dead**.

What the recipe did do is retire the outcome's stated blocker.
`_NOTHING_HERE_QUANTISES` read *"no bitsandbytes... in the pinned lockfile...
what would change this is a quantising backend - a recipe, not a proposer"*, and
that had gone false the same way `_DATA_BENCH` did. It is rewritten to say what
is actually missing now - a GGUF writer, and a proposer.

**And the backend's first measurement changed what a proposer may claim**, which
is why one is not written yet rather than written badly: 4-bit NF4 cut peak VRAM
by 60% and made generation **1.6x slower**. This outcome recommends quantising
to cut the cost of serving, so a proposer drawing it without a latency arm would
recommend a change that makes the thing it was called about worse.

### stage_4_format, worked, 2026-08-27 — and the lesson is where the fix was

Its five outcomes had five written reasons and **none of them was "nobody wrote a
proposer"**. Read in order they say the same thing three different ways: the
engine asks a person for a number and the ledger will not accept it from them.

* `ACTION__MEASURE_THE_FORMAT` named its own remedy - *"it closes when a tool
  measures `schema_compliance`, not when a proposer is written."* **Built.**
  `app/tools/shapes.py` counts what fraction of a person's outputs satisfy a
  schema they name: two files on this machine, no model called, nothing sent
  anywhere. The JSON Schema checker is a declared subset and **refuses a schema
  using anything outside it** rather than skipping the keyword and reporting a
  number — a validator that silently ignored `allOf` would report 100%
  compliance for a schema whose hardest half it never looked at, which is a
  fabricated number with a real provenance chain. Every row is in the
  denominator, including the ones that are not JSON at all, because a fraction
  computed over "the rows that parsed" RISES as the system gets worse.
* `NO_TRAIN__CONSTRAINED_DECODING` needs a decoding backend, which is a
  dependency and its own step. **Unchanged and still right.**
* `ACTION__FIX_THE_DECODER` is a wiring fault in code this harness does not own.
  **Half of its reason has now been answered** — confirming the fix means
  re-measuring `schema_compliance`, and that is measurable today — and the other
  half is not: there is still no step that can read somebody's calling code.
* `ACTION__RE_BUCKET_THE_FAILURES` and `BLOCKED__COLLECT_OR_SYNTHESIZE_DATA` are
  unchanged, and both reasons are worth re-reading rather than re-summarising.

**The one that is still a defect, and it is a defect in a DECLARATION.**
`schema_expressible` - *could a schema express your target shape at all* - is a
judgement about the person's own requirements. It is declared `source: derive`
**with no entry in the ledger's own `derived:` block**, so nothing derives it; no
tool can read it; and `derive` admits MEASURED only, so the person cannot state
it either. Every route in, shut. That closes when the ledger says `source: ask`,
not when a proposer is written, and it is pinned in
`tests/test_the_format_stage_gets_a_build.py::TheOtherHalfIsStillOpenAndSaysSo`
so the day it changes this file is asked to be re-read.

**The lesson generalises to the three stages still at zero.** Their reasons are
about missing INSTRUMENTS and missing JUDGEMENTS, not missing proposers -
`NO_TRAIN__SWAP_MODEL` and `NO_TRAIN__QUANTIZE` both stop one step short of a
number that needs a connected model; `ACTION__FIX_QUALITY_FIRST` and
`BLOCKED__LICENCE` are the person's call and a build that automated them would
be inventing the user's judgement. Writing proposers for those would be the
`ACTION__COUNT_THE_ROWS` trap: a plan that spends somebody's afternoon to land
back on the same outcome.

Most of the rest assemble tools that already exist; every proposer written so far
has discovered the pieces were already there.

**Done when:** ~~no stage in either ledger has zero builds, and the most common
early outcome in each is covered.~~ **SUPERSEDED 2026-09-09** by the condition
in *"stage_7_efficiency is off zero"* above, which is the one the gate enforces.
Struck rather than deleted, and the reason it was replaced is below.

**Measure it as:** built-versus-dead per stage, computed from
`propose.COVERAGE`, `propose.NOT_COVERED` and `Spec.outcome_sites()`, never from
memory — and say which attribution rule was used, because the count depends on
it and a table without the rule is the reason the previous one drifted.

### Both conditions, MEASURED 2026-09-10, and they disagree

Computed by importing `_built_and_dead` from
`tests/test_a_stage_with_no_builds_has_a_written_reason.py` — **the function the
gate enforces**, rather than a second implementation of the same rule wearing
its name, which is the drift the instruction above is about. **Attribution
rule:** an outcome is counted in every stage whose node states it, and only
outcomes a person can receive (`declared_outcomes()`, which excludes `REROUTE`).

    ML   stage_7_efficiency          0 built / 5 dead
         stage_8_offtheshelf_first   0 built / 1 dead
    AI   stage_5_control_flow        0 built / 3 dead

    THE ORIGINAL CONDITION   NOT MET   three stages sit at zero
    THE REPLACEMENT          MET       every dead outcome in all three
                                       carries a written reason

***So phase 3 is done under a criterion written AFTER the measurement and not
done under the one registered before it.*** That sentence is the whole of what
this section exists to say, because this lane spent a night refusing exactly
that shape in other people's numbers and does not get to skip it in its own.

### Why the replacement is defensible here, and what would make it not

**The reasons were read, not counted.** The test can enforce that a reason
*exists*; it cannot enforce that the reason is a real one, so all nine were read
by a person on 2026-09-10:

* **Three are the person's judgement** — `ACTION__FIX_QUALITY_FIRST`,
  `BLOCKED__LICENCE`, `NO_TRAIN__SHIP_AS_IS`. *"A build that automated it would
  be inventing the user's judgement, which is the same defect as inventing a
  number."* **Building these would violate an invariant to satisfy a count.**
* **Three are the refusal itself** — the AI ledger's `NO_AGENT__A_SCRIPT`,
  `NO_AGENT__A_WORKFLOW`, `NO_AGENT__ONE_AGENT_FIRST`. *"The refusal IS the
  product: one API call beats the loop. Nothing to build; everything to say."*
* **One is out of scope on purpose** — `NO_TRAIN__CACHE_AND_ROUTE`: we measure
  what a cache or router would save and do not build a serving layer.
  `PRODUCT_SPEC` 6.4 draws that line.
* **Two name a missing INSTRUMENT and have been narrowed by measurement rather
  than restated** — `NO_TRAIN__OFF_THE_SHELF_MODEL` needs an adapter that sends
  audio or pixels, since all three scoring tools send text; `NO_TRAIN__QUANTIZE`
  needs a GGUF converter (`llama-quantize.exe` is already on this machine and
  offers Q4_K_M as type 15; nothing here converts safetensors into a GGUF for it)
  and a third measured size before a proposer may state a cost.

***Not one of the nine says "nobody wrote the proposer", and that is precisely
what the replacement forbids.*** The original condition would have been met by
writing three proposers that invent the user's judgement, argue against the
product's own refusal, or recommend quantising without a latency arm — and the
backend's own measurement is why the last one is not written: 4-bit cost **1.62x
latency at 135M and 1.26x at 1.7B**, so a proposer drawn without a cost at the
person's size would recommend a change that makes the thing it was called about
worse.

**What would make the replacement a dodge, stated so it can be checked:** a
stage sitting at zero because nobody got round to it. The test's positive
control fails if no stage is empty — so the check cannot go vacuous — and the
second half stops it drifting into *"every dead outcome anywhere needs prose"*.
**If a future reason reads "not built yet", it fails this section's standard
even while passing the test, and the test is not the thing to change.**

---

## Phase 4 — Sandboxes first, environments later — **DONE 2026-09-09 against its own done-condition**

Sandboxes exist and are already part of a build: pinned environment, isolated
directory, data snapshot, no egress. Phase 4 makes them a surface people use
deliberately rather than a step they pass through.

Reinforcement-learning environments come **after**, and the honest reason is in
`VISION.md`: a reward that means anything is a harder measurement problem than
everything else in this plan combined. Treat any earlier attempt as a research
spike, not a feature.

**Done when:** a person can build, run, inspect and dispose of an environment
from the chat, and the harness can say what happened inside it.

### The four verbs, DRIVEN 2026-09-09 — **the sandbox half is DONE**

Every call through `Registry.call`, which is the entry point a model's tool call
uses, so this proves the chat path rather than a Python back door.

| verb | tool | result |
|---|---|---|
| build | `make_sandbox` | ok, `recipe` and `egress` applied |
| run | `run_in_sandbox` | **exit 0**, `step 0 loss 1.0000` through `step 4 loss 0.5838`, run 1121 |
| inspect | `list_sandboxes` | listed, purpose intact |
| dispose | `delete_sandbox` | removed 3 files, 6 directories, 1,994 bytes; **0 listed after** |

And "the harness can say what happened inside it" is the strongest part rather
than the weakest. **Two refusals arrived as free negative controls, and each one
carried its own number:**

* **GPU contention.** *"The GPU is already holding 5.06 GB of 8.0 GB -
  granite4-hermes (4.79 GB)... the last time this happened, 200 steps that take
  46 seconds on a free card took 56 minutes."* A refusal with a measured
  consequence and a named escape hatch (`config.share_gpu`), not a warning.
* **No egress.** The first run exited 1 and said exactly why: *"cannot reach the
  engine at 127.0.0.1:8078: HTTP Error 401: Unauthorized"*, with a `note`
  explaining the sandbox was handed no address and no token, and a `reach` block
  splitting what is ENFORCED from what is NOT - *"the filesystem is not a jail...
  'it cannot reach anything it was not given' is true of what this hands a run,
  and false as a statement about what the run can do."* Granting egress with a
  reason made the same run exit 0.

**A NEAR-MISS WORTH KEEPING.** That exit-1 was almost recorded here as a defect -
"the run failed and the harness could not say why" - because the driving script
printed `error`, `detail` and `summary`, none of which exist on this reply. The
answer was in `output` and `note` all along. **The instrument that was blind was
the one I wrote to read the result**, which is this repository's recurring defect
arriving from the other side: not a tool that cannot say, but a reader that did
not look where it says.

### Why this is DONE, and the correction that got it there

**This phase was reported blocked for hours, by me, and it was not.** The
done-condition above is the four verbs plus the harness saying what happened
inside. All four were driven through `Registry.call` and the reporting is
demonstrated below. **Reinforcement-learning environments are not in the
done-condition** — the section is titled *"Sandboxes first, environments
later"*, and its second paragraph puts them explicitly **after**.

I listed them as a Phase 4 blocker repeatedly. That came from remembering the
section rather than reading its criterion, which is the same defect this plan
keeps recording in other forms: **a claim carried forward without being
re-checked against the thing it is a claim about.**

**What is NOT in this phase, and remains later by design:** reinforcement-learning
environments. `VISION.md` defers them on purpose - a reward that means anything
is a harder measurement problem than everything else in this plan combined - and
nothing above touches that. The sandbox is the foundation and the foundation is
proven; the environment is still a later headline.

---

## Phase 5 — Launch

Today a stranger cannot get this. `pyproject.toml` says version 0.1.0, `start.sh`
assumes a developer, nothing is published, and the README's own "honest current
state" section describes a product from months ago.

**What it contains:** one-command install, a README that matches what exists, a
first-user shape chosen deliberately, and one recorded session as the demo.

**Done when:** somebody who has never seen the repository gets from zero to a
diagnosed problem without asking a question.

**Cheapest item in the whole plan:** rewriting the README's current-state
section. It presently undersells the product by about six months.

### Re-read 2026-09-09 — two of the four claims above are stale

* **"The README's own honest current state describes a product from months
  ago"** and **"the cheapest item is rewriting it"** are both **WRONG NOW**. It
  already documents three ledgers, 70 tools in 14 packs, the gate, the launcher's
  `--stop`, and a `Limitations` section that says plainly *"there is no installer
  and no cloud execution."* Somebody fixed it and did not update this file.
  **That quoted sentence is itself now out of date** — corrected 2026-09-10, the
  same day the sandbox drove the installer; the README says unsigned-but-real,
  and carries the connect-a-model step it had never documented at all.
* **"Nothing is published"** needs splitting. `scripts/release/`,
  `scripts/one_click_on_a_fresh_machine.py` and
  `scripts/the_stranger_on_a_fresh_machine.py` are real and run in Windows
  Sandbox - **but they test `four-asserts`, the library lifted OUT of this
  repository, not the harness.** A stranger can install that. A stranger still
  cannot install ml-harness, so the phase's own done-condition is untouched by
  it, and reading the script names without reading the scripts would have
  suggested otherwise.

**What DID close, and it is the training path's zero-to-working barrier.** The
README's own line was *"real training depends on pinned per-recipe environments
you build first"*, and those instructions lived as PROSE in three
`requirements.lock` headers, in three different phrasings, four commands each to
retype. **They were also wrong**: `hf-quantize`'s header said Python 3.12 for an
environment measured at 3.11.15.

The steps are now DECLARED in each `recipe.toml` under `[environment]` -
interpreter, what must be installed before the lockfile and from which index,
and what to verify afterwards - and `scripts/build_recipe_env.py` executes the
declaration. `python scripts/build_recipe_env.py --all` builds every recipe;
`--check` verifies without building.

**The verify step is the reason this is worth more than a shell alias.**
Installing the wrong torch IS NOT AN ERROR: PyPI's Windows wheel is CPU-only,
the CUDA build exists only on download.pytorch.org, and somebody who gets the
wrong one completes every step, sees nothing fail, clicks train and waits. The
builder therefore imports the module afterwards and **refuses to print READY
unless CUDA is really there** - a run that did not work looking exactly like a
run that did, caught at setup instead of at 3 a.m.
`tests/test_a_recipe_says_how_to_build_its_environment.py` refuses a recipe that
ships a lockfile without a declaration, and **constructs the CUDA-absent failure
rather than trusting it would be caught.**

**Still open for Phase 5, stated precisely because I had it wrong.** The
done-condition is *"somebody who has never seen the repository gets from zero to
a diagnosed problem without asking a question."* **A code-signing certificate is
not part of it** — the words "certificate" and "sign" appear zero times in this
phase. That requirement belongs to `THE_PLAN.md`'s Phase C, which is a different
milestone in a different document, and I cited it as a Phase 5 blocker for
several hours without checking.

### DRIVEN 2026-09-10 — the install half works on a machine with nothing

Windows Sandbox, nothing mapped in but the installer, `scripts/
the_stranger_installs_the_harness.py`:

    python on PATH:  False      git on PATH: False      uv on PATH: False

    installer exit 0; shell, uv, uninstaller and the product wheel all landed
    engine.json at %LOCALAPPDATA%\ml-harness\engine.json
    GET /health -> HTTP 200, status "ok", all three checks passing
    sha_source "not-a-git-checkout"    <- a real installed copy
    python 3.11.15 built by uv inside the sandbox; schema agrees at 13

**A stranger can install this and get a working engine**, and that was never in
evidence before — every prior measurement of the installed path was taken on the
machine that produced it.

**AND THE WALL IS EXACTLY WHERE THE DONE-CONDITION POINTS.** `/api/providers`
answers HTTP 200 with an **empty list**. The person has a working product that
cannot diagnose anything, because a diagnosis needs a model and that machine has
no Ollama, no key and no cache.

So the remaining gap is **not the installer**: it is that nothing walks a new
person from a running engine to a connected model. That is the whole distance
between where this phase now stands and its own sentence.

#### CORRECTED SAME DAY — that sentence is wrong about the window

**"Nothing walks a new person from a running engine to a connected model" is
false for the GUI, and I wrote it from a test that never opened the window.**
The stranger script drives the engine over HTTP. It launches
`ml-harness-shell.exe`, waits for `engine.json`, and then asks `/health` and
`/api/providers` — so what it measured is what the ENGINE says, and I read that
as what the PRODUCT says.

What the window actually does with zero connections, read in
`frontend/src/components/Composer.tsx`:

* `ConnectionBanner` is rendered unconditionally above the composer, before the
  first message. With no provider it reads *"No model connected — the harness
  thinks with a model you lend it"* over a button that opens the connect
  dialog.
* The model selector in the composer row reads **"Connect a model"** rather than
  a model name, and is the same button.
* `ConnectModel.tsx` then offers two equal roads, and **both of its empty states
  are already written for exactly this machine**: a daemon that is not running
  says so in the tool's own words and points at the API road; a daemon that
  answers with nothing pulled says *"there is nothing to click"*.

So the walk exists, it is one click from the first screen, and it is honest
about a machine with nothing on it. **The defect the sandbox really found was
narrower and it was mine:** every ENGINE-side surface said the install was fine.
`mlh doctor` — a stranger's first command, and the only one available without
the window — printed five green rows and never mentioned that a model is needed.

**FIXED 2026-09-10: `mlh doctor` now carries a `model` row.** It is KNOWN-OPEN
rather than broken, using the flag `app/cli.py` had reserved in writing for the
next honest unknown, so a correct fresh install still exits 0 instead of telling
every new person their installation is broken. It runs **no network probe** —
`doctor`'s contract is that it writes nothing, starts nothing and asks nothing,
and a missing database is reported as *"none connected"* rather than as the
`OperationalError` that reads like a fault. Eight cases in
`tests/test_the_doctor_says_a_model_is_missing.py`, including the two that would
have been wrong in the reassuring direction: the exit code, and a database that
does not exist yet.

**What is still genuinely undriven** is the click-through itself on a machine
with nothing: a Windows Sandbox has no Ollama and no key, so the two roads out
of that banner both leave the sandbox. That is a measurement about *this*
machine's Ollama plus a deliberately dead port, not another sandbox run, and it
is the next thing.

#### DRIVEN, same day — banner to a connected model to a diagnosis question

Not another sandbox run: a **scratch engine on its own data root**
(`MLH_DATA_ROOT` + `MLH_ENGINE_FILE` + `ML_HARNESS_DB` into a temp directory,
port 8099) whose `/api/providers` answers `[]` — the stranger's exact state,
reproduced where a real Ollama exists. The dev server is a second Vite on 5233
with its own `cacheDir` (`frontend/vite.stranger.config.ts`), because 5199 is
pinned with `strictPort` and **correctly refused a second instance** rather than
sliding to 5200 and letting a screenshot be taken of another lane's app. That
refusal is the feature working; the config file exists so the next person does
not have to rebuild it.

**What the first screen says with nothing connected**, photographed:

* the amber banner above the composer — *"No model connected — the harness
  thinks with a model you lend it"* over *"Pick one on this machine, or connect
  an API key"*
* the composer chip reading **Connect a model** rather than a model name
* the rail, bottom-left: *No model connected*

**One click on the banner, one click on a row.** The dialog listed the local
models with `can call tools` read off the GGUF **before** anything was
connected. Clicking `granite42-hermes:latest` left the engine holding:

    is_active 1   tool_calling "yes"   ctx_len 131072 (measured)
    capability_detail "reported by the Ollama server for this model"

No URL typed, no adapter chosen, no key. **Create, activate and probe, from one
click** — the sequence `connectLocal` promises, driven rather than read.

**And the thread that followed reached the question the ledger needs.** The
first suggestion card, sent: the thread took `docs/diagnosis_engine.yaml`,
routed to `route_or_classify`, loaded four tool packs, called `map_the_ask` then
`what_is_missing`, and asked for **the folder path and the label column**.

**That is the walk's honest end on this machine, and it is not a wall.** Phase
5's sentence is *"without asking a question"* — meaning without having to ask
**us** one. A product asking the person for their own data is the walk working;
what is not driven is a diagnosis **on data**, and the reason is that there is no
folder of support tickets here, which is a fact about the machine and not about
the product.

**What is still undriven, stated precisely so it is not read as done:** the same
click-through on a machine that has never seen this repository. A Windows
Sandbox has no Ollama and no key, so both roads out of that banner leave it —
that needs either a model pulled inside the sandbox or a key, and both are
somebody's decision rather than a measurement anyone can take.

### DRIVEN THREE TIMES, 2026-09-10 — and the paragraph below is what it replaced

**The next paragraph said "nobody has driven the path" and that the walk needed
"either a model pulled inside the sandbox or a key, and both are somebody's
decision".** Both halves fell over on being tested: **Ollama goes into a bare
Windows Sandbox by ZIP** — 1,469,375,054 bytes in 82 s, no installer and no
decision — and the path was then driven end to end three times, at three model
sizes. **It is kept below rather than deleted**, because a blocker that
dissolved on contact is worth more on the page than a tidy one.

**Install → `/health` → `/api/providers` → zip → pull → connect → activate →
probe → thread → goal → turn: every hop measured, installer exit 0.** Zero to
connected, probed, routed and calling tools: **MEASURED**. Zero to a DIAGNOSED
PROBLEM: **NOT REACHED** — 0.5B named the harness's tools in prose and called
none; 3B called the right tool with `arguments: {}`. ***Argument construction is
where a small local model fails***, and that is the phase's remaining blocker.
Full walk records in the nightshift build-verify page; the phase audit at the
top of this file carries the verdict.

**One qualification that must travel with it:** the walk obtains Ollama by zip
because both standard silent-flag families are measured dead. A person clicks
through that installer in seconds; an unattended walk cannot. **"A stranger gets
there" and "an automated walk gets there by a route a stranger would not take"
are not the same claim, and only the second is measured.**

---

**What actually remains is that nobody has driven the path.** `THE_PLAN.md` C.d.4
records the installer being built, installed silently into
`%LOCALAPPDATA%\ML Harness`, reaching an engine in **16 seconds** and
uninstalling cleanly — so the install half is measured. What has never been done
end to end is the whole sentence: install, connect a model, and reach a
diagnosis, by somebody with no checkout. **That is a driving job, not a
purchasing one**, and the Windows Sandbox machinery for it already exists —
`scripts/the_stranger_on_a_fresh_machine.py`, currently pointed at `four-asserts`
rather than at the harness.

---

## Execution queue — what to build next, 2026-08-26

This is the work queue. One step per agent run; each step carries its own
acceptance test. The letter labels (A–F) were used during the instruments
integration branch and are kept here because they name surfaces that still need
UI work — they are not separate from the numbered phases above.

| step | phase | what | acceptance |
|---|---|---|---|
| ~~**1**~~ | 1 / C | Journey report + export in the chat UI | **DONE 2026-08-27** — driven in Chromium against a scratch engine on its own database: the report opens from the app bar and renders the verdict, the five-gate ledger and `eval_size_n 40 MEASURED measure_eval_set`; the export downloads `ml-harness/journey-export` v1 carrying `code_fingerprint`; a scan of the bundle for token/secret/password/credential-shaped fields found none. One honest note: the thread was driven through the HTTP surface rather than by a model, because no model can be connected in that container |
| ~~**2**~~ | 1 / C | Studios frame in React | **DONE 2026-08-27** — browser check driven, 12 packs drawn in the empty state, `agent` opens to `read_agent_traces read_tool_definitions run_the_failures bound_the_loop`, no console errors, both themes |
| ~~**A**~~ | 1 / 3 | **Wire the four AI builds that were already written** | **DONE 2026-08-27** — `_propose_run_the_failures`, `_propose_read_the_traces` and `_propose_classify_the_agent_failures` were finished, 778 lines, and referenced nowhere; so were the three predicates written to gate them. Registered, driven to `deviations: []` on real fixtures, and held to both structural sweeps. **AI ledger 4 of 23 → 8 of 23** |
| ~~**B**~~ | 3 | **An `ACTION__` outcome cannot point nowhere** | **DONE 2026-08-27** — every `ACTION__` and `BLOCKED__` in both shipped ledgers has a build or a reason over 60 characters, never both, and every proposer is keyed on an outcome some ledger declares. A new one in neither state reddens the run that adds it |
| **3** | 1 | TRAIL trace census | `docs/AGENT_INSTRUMENTS.md` updated with measured results from a public corpus; Phase B journey fixtures re-pointed at real traces |
| ~~**4**~~ | 2 / E | Synthetic rows cannot open gates | **DONE 2026-08-27** — wall 8 on `Instrument.measured`: a fact measured off a file holding generated rows is refused at the stamp, all 22 file-reading stamps name their file, and a structural sweep asserts the four that do not are the four that read this machine. Driven end to end: amplify 12 real rows to 200, count them, `ok: false`, G0 shut |
| ~~**5**~~ | 2 / E | 10% human verification step | **DONE 2026-08-27** — `draw_verification_sample` and `record_verification`, and `start_training` refuses a generated dataset until a matching verification exists and found nothing wrong. The record is bound to the file's sha256, so rewriting the data invalidates it |
| ~~**6**~~ | 2 / E | Synthesis UI card | **DONE 2026-08-27** — three cards, browser-checked in both themes against payloads the real tools produced. The tag and "nothing here opened a gate" are in ink above any disclosure. A layout defect the assertions missed and the screenshot caught is recorded in the component |
| ~~**7**~~ | 2 / E | Phase 2 done-condition journey | **DONE 2026-08-28** — driven end to end against `granite4-hermes:latest` over Ollama on a scratch database, from a cold-start thread nobody chose a ledger for. Fourteen rungs: arrive → connect → state → `BLOCKED__BUILD_EVAL_SET` → carve 297 eval rows (30 distinct, leak check ran) → count → `ACTION__MEASURE_BASELINE` → score → `ACTION__CLASSIFY_FAILURES` with G0 and G1 PASSED → propose `classify_the_failures [run, read, recheck]` → approve on the fingerprint → storm `done`, all steps `done`, `deviations: []`, `verification.ok` with `saw: MEASURED` → re-enter to `NO_TRAIN__CONSTRAINED_DECODING` → the report renders with 9 facts and every one carrying an origin. **THE FINDING, MEASURED AND NOT CONSTRUCTED: the model scored `0.0` and the majority-class baseline scored `0.45`.** The trivial answer beat the model, and the failure histogram says why — `{wrong_format: 18, refuses: 2}`, so the answers were not in the label set at all, which is precisely what `NO_TRAIN__CONSTRAINED_DECODING` is the remedy for. A scripted model could not have produced this: it scores what it was scripted to score |
| ~~**C**~~ | 3 | **The workbench: the six refusals that name a cheap fix** | **DONE 2026-08-27** — the prerequisite below was built first (`v012`, `read_agent_results`), then all six: attach → grade before → grade after → compare paired with McNemar → re-enter the tree. Driven to `deviations: []` on all six, and the verdict is earned rather than assumed — 9 of 12 cases fixed returns `different`, an identical 'after' file returns `no_evidence`, and 1 of 12 returns `no_evidence` too, which is the +8.3% that would otherwise have been reported as a win. **AI ledger 8 of 23 → 14 of 23** |
| **8** | 3 | ML coverage — stage with zero builds | **`stage_4_format` DONE 2026-08-27**, and it did not need a proposer: its own `NOT_COVERED` entry named the remedy — *"it closes when a tool measures `schema_compliance`, not when a proposer is written"* — so `app/tools/shapes.py` is that tool and `ACTION__MEASURE_THE_FORMAT` now has a build. The other three are argued rather than owed and are re-read below |
| ~~**9**~~ | infra | ROADMAP 1.18 — frontend test runner | **DONE 2026-08-27** — vitest 4 + jsdom + @testing-library/react, `npm test`, four cases over the studios card including the one that matters: it draws nothing when the engine did not answer. Playwright is NOT installed as a dependency; browser checks run against the chromium already on the machine, which is how this repository has always taken them |
| ~~**10**~~ | docs | Reconcile `docs/ROADMAP.md` | **DONE 2026-08-27** — retired as the queue, kept as the reference, with what is stale in it named at the top. `AGENTS.md` and `TASKS.md` point here |
| **11** | 5 | Launch — one-command install | Stranger reaches a diagnosed problem without asking a question. **The README half is done** (2026-08-27): the current-state section names the 67 tools, the data floor and its two walls, and the journey surfaces, and the install line says `-e .[test]` for the gate. **The packaging half closed too**: NSIS builds an installer, and on 2026-09-10 it was driven in a Windows Sandbox with no Python, no git and no uv on the machine — silent install, an interpreter uv built inside the sandbox, `/health` answering as a real installed copy. `pip install -e .` is no longer the only way in; the line above saying otherwise was stale, as was the README's *"there is no installer"*, both corrected the same day. **What is left is neither the README nor the packaging: it is the click-through.** Nobody has gone banner → connect → diagnosis on a machine with nothing, because both roads out of that banner (a local Ollama, or a key) leave a sandbox |

### Agent freedom — queued 2026-09-14, from the measure→gate withhold loop and clouding research

Research (Anthropic tool search / RAG-MCP / skills progressive disclosure) said the
same thing `docs/CAPABILITY_BLOCKS.md` §5 already decided: **do not let the model
pick its tools.** Deepen the diagnosis graph as topology; free agents by making
truthful moves succeed and by keeping goal/todo off casual asks.

| step | what | acceptance |
|---|---|---|
| ~~**AF1**~~ | **Standing refresh after measurement + soft vs hard gate claims** | **DONE 2026-09-14** — `_Standing.note` re-walks after any tool with `measures=`; soft narration ("baseline was measured") is allowed when facts are MEASURED even if the gate row is still `NOT_REACHED`; naming `G1_… is satisfied` still withholds. `tests/test_standing_refreshes_after_a_measurement.py`, extended `test_a_gate_is_not_a_word_it_is_a_row.py` |
| ~~**AF2**~~ | **Goal/todo is a Run skill, not every-turn glue** | **DONE 2026-09-14** — `_plan_note` / `_goal_note` grind only when autonomy or `longrun.is_running`; browser `shouldRunAnotherTurn` never auto-chains (press Run); Build with open steps starts `longrun.start`; `tick_for_tool` only while working. Frontend + `test_the_todo_list_is_the_goal.py` |
| ~~**AF3**~~ | **Host-side topology: builds, stuck-walk, fat schemas, plan loaded marks** | **DONE 2026-09-14** — `contract.builds` populated for eight ML outcomes; stuck-walk covers unsettled gates only; `propose_build` description shortened; plan-mode capability marks use `modes.tools_for` |
| ~~**AF4**~~ | **Instruction compression behind NON_NEGOTIABLE + eval** | **DONE 2026-09-14** — `01b` and `03` compressed; `16_worked_examples` opt-in (`examples=` / loaded on working turns); `tests/test_instruction_compression_eval.py` holds laws + token ceiling. Live behavior rates (empty reply, gate withhold, cannot-build lie) named for a connected-model run |
| ~~**AF5**~~ | **Sub-agents as freer workers** | **DONE 2026-09-14** — light standing brief for children; packs narrowed to core + tools named in the phase plan. `tests/test_a_subagent_is_a_freer_worker.py` |
| **AF6** | Progressive schema disclosure inside `active()` (name+one-liner for non-aimed tools) | Provider adapters tolerate partial schema sets; aimed step's tools keep full JSON; measured fixed-cost drop on a 65k window without empty-reply rise |
| **AF7** | Live behavior eval against a connected local model | Fill `BEHAVIOR_METRICS` in `test_instruction_compression_eval.py` from a real provider; compression judged by rates, not tokens alone |
| **AF8** | Memory/RL hooks for tool-definition evolution | Failed-call memory writes that improve schemas only behind AF7's eval gate |

### Control surface — queued 2026-09-14, from gating UI/features against T3 Code

T3 Code is a multi-provider *coding* control plane. We are the diagnosis layer.
Steal control-surface craft (permissions, remote approve, usage, turn diffs,
subagent visibility); do not become their product. Argument and non-goals:
`docs/CONTROL_SURFACE_GATE.md`. Process gate: a T3 user would know mode, run
state, and how to stop/approve in under two seconds — without weakening
five-gate honesty or provenance.

| step | what | acceptance |
|---|---|---|
| ~~**CS1**~~ | **Composer permission ladder** | **DONE 2026-09-14** — `threads.permission` (ask/measure/write/full); `app/autonomy.may_run`; `PermissionLadder` replaces binary Autonomous. **AU1 2026-09-15:** `full` is zero-ask bypass — model `state_facts` open gates; `FULL_NEVER` is only `delete_sandbox`; QuestionCard hidden under full. |

### Agent workspace — queued 2026-09-15 (Max: full bypass + sandbox shell)

| step | what | acceptance |
|---|---|---|
| ~~**AU1**~~ | **`full` = zero-ask bypass** | **DONE 2026-09-15** — Model `state_facts` under full → STATED / opens ask gates; no QuestionCard; `start_training` auto; `FULL_NEVER` = `delete_sandbox` only; `test_full_mode_settles_ask_facts.py` |
| ~~**AU2**~~ | Transcript notice/card condensation | **DONE 2026-09-15** — housekeeping notices → `.planline`; historical `DiagnosisCard` defaults collapsed |
| ~~**AU3**~~ | Baseline binds to train-target provider | **DONE 2026-09-15** — `threads.baseline_provider_id`; `measure_baseline` prefers it; `POST …/baseline_provider` |
| ~~**AU4**~~ | Free-text sandbox (+ project under full) shell | **DONE 2026-09-15** — `run_sandbox_command` / `run_project_command`; argv via powershell/sh (not JobSpec shell=True); sandbox auto at write+; project auto only at full |
| ~~**AU5**~~ | **Full settles + goal tools without invite** | **DONE 2026-09-15** — `standing_brief`/`_next_move_line` under full order `state_facts` (never ask the person); `_permission_note` hardened; `run_turn` forces `invite_goal_edit` on full; `goal_todo` allows writes when permission is full; `test_full_mode_settles_ask_facts.py`. |
| ~~**AU6**~~ | **Full⇔build + grind nudge** | **DONE 2026-09-15** — `set_thread_permission(full)` forces `mode=build`; `set_thread_mode(plan)` forces `permission=ask`; `_run_turn_body` corrects stale full+plan and always merges `intent` under full; `state_facts` description names Full=STATED; `EMPTY_REPLY_NUDGE_FULL` / `FULL_GRIND_NUDGE` when Full narrates with an open measure/settle next_step; tests in `test_full_mode_settles_ask_facts.py`. |
| ~~**AU7**~~ | **Longrun: narration ≠ park; Full settle first** | **DONE 2026-09-15** — longrun does not strike on `said_it_would` with no tools (screenshot parking loop); `INTENT_NUDGE_FULL` + plan-note never "wait for approve"; Full injects settle scaffold for open ask-facts; `tick_for_tool` uses checklist_source. |

**Non-goals for this cluster:** weakening ask/measure/write honesty; shell from untrusted HTTP bodies without a thread permission.
| ~~**CS2**~~ | **Remote/mobile path to Approve and Stop Run** | **DONE 2026-09-14** — `remote_links` stores sha256 only; `GET/POST /remote/{token}` Approve/Deny/Stop; mint + revoke API; GoalBar Remote copies URL once. |
| ~~**CS3**~~ | **Turn + thread cost/usage strip with provenance** | **DONE 2026-09-14** — `GET /api/threads/{id}/usage` from `turn.context`/`tool.call`/`stream.end`; `UsageStrip` above composer path with ProvenanceTag; details opens Context pane. |
| ~~**CS4**~~ | **Sub-agent inspector pane (status, aimed step, packs, last digest)** | **DONE 2026-09-14** — pane id `agents` in `PANE_ORDER`; `AgentsPane` + detailed `SubAgentBoard`; `GET …/subagents` adds packs + last_digest; Stop works from the pane. |
| ~~**CS5**~~ | **Per-turn “what changed” card (facts stamped, plan ticks, artifacts; safe revert where defined)** | **DONE 2026-09-14** — `turn.effects` before `stream.end`; `WhatChangedCard`; `POST …/effects/{id}/revert` restores plan/todo only (`facts_untouched`); `tests/test_turn_effects_revert_restores_plan.py`. |
| ~~**CS6**~~ | **Bind Terminal / Stage to the active longrun or recipe** | **DONE 2026-09-14** — live `useRun` / `spendingRows` auto-focus Stage (Terminal for train keys) unless `sessionStorage mlh.inspectorPinned`; pin on rail click; run/sandbox ids passed into Terminal. |
| ~~**CS7**~~ | **New-thread start sheet (model, Plan/Build, permission ladder, project, optional journey)** | **DONE 2026-09-14** — `StartSheet` when `threadId===null`; prefs applied on create via `setThreadMode`/`setThreadPermission`; journey cards prefill composer. |
| ~~**CS8**~~ | **Plan optional and cancelable; no auto-Run on Build** | **DONE 2026-09-14** — GoalBar Cancel clears plan via `setThreadPlan(null)`; `ModeSwitch.toBuild` no longer calls `startRun`; Run remains on TheBuildWorksDown. |
| ~~**CS9**~~ | **Ask-gated goal/todo tools; secondary checklist ≠ plan** | **DONE 2026-09-14** — `threads.todo` + `checklist_source`; invite-gated `set_goal`/`write_todo`/…; composer checkbox; GoalBar Plan\|Todo; longrun reads active checklist. |
| ~~**CS10**~~ | **Retire shallow top GoalLine chrome** | **DONE 2026-09-14** — `GoalLine` removed from `App.tsx`; component and `.goalline` styles deleted. Standing `threads.goal` remains backend context. |
| ~~**CS12**~~ | **GoalBar X hides≠clears; layout; target+arrow; status lamp** | **DONE 2026-09-15** — X sets `mlh.goalbarHidden` (plan stays in SQLite); reopen via Plan / `showGoalBar`; row trails chev+X in one cell so X does not wrap; bullseye+arrow target; lamp `data-state` idle/done/partly/failed. |
| ~~**CS11**~~ | **Chrome-tab half work panel; Data∪Stage** | **DONE 2026-09-15** — `InspectorState` is `{tabs, active}`; rail opens/focuses tabs; Chrome strip with close; work panes widen ~50%; `data` redirects to `stage`; Stage header carries Data tag. |
| ~~**CS13**~~ | **Plan / Goal orchestration affordance** | **DONE 2026-09-15** — `GoalOrchestrate` beside ModeSwitch: Plan → plan mode + Plan tab + showGoalBar; Goal → arm invite + Plan tab + showGoalBar; Full shows Goal as always armed; invite clears after a turn. |
| ~~**CS15**~~ | **Composer slash / GoalBar / Doc / buildloop** | **DONE 2026-09-15** — removed `GoalOrchestrate` demotion paths; `/goal` `/plan` `/doc` slash menu (never changes permission); GoalBar one checklist (prefer plan); Doc searchable `harness-plans` dropdown; buildloop `"Working the plan · N done, M left"`; Icon `goal` glyph. |
| ~~**CS14**~~ | **Cursor top tabs + `+` menu** | **DONE 2026-09-15** — removed left icon rail; top tab strip (icon + short label, X on hover); searchable `+` pane menu; header is provenance/pop-out only (no duplicate pane title); app-bar show/hide unchanged. |
| ~~**CS16**~~ | **WhatChanged color language** | **DONE 2026-09-15** — leading `+`/`−` with `--fits`/`--wont`; kind chips Ticked/Plan/File/Fact/Parked in distinct token hues; tool names in mono accent. |
| ~~**CS17**~~ | **Quiet control surface** | **DONE 2026-09-16** — GoalBar quiet chrome; `unpark_step`; Inspector full + Search panes portal; WhatChanged condensed; planline H-scroll fixed; Doc/Plan pops out; gleaming Calling/Thinking; Full hides ask cards + Settling pill; longrun will not park on intent/"I'll…" or under Full without a tool refusal; ProposalRefusal condensed; usage strip shows **tok total**. |
| ~~**CS18**~~ | **Shared header + square chrome + quieter blank** | **DONE 2026-09-16** — appbar spans chat+inspector; inspector body-row split (no overlay float); square `--r-8` chrome tabs; StartSheet brand fonts, no duplicate journeys; sharper goal target at 16px. |
| ~~**CS19**~~ | **Quiet panes, readable Files, star Goal** | **DONE 2026-09-16** — hide `from GET…` strips; bigger centered chrome tabs, no panel-header X; Stage tab scroll chevrons; Files side list + Pretty/Source; Context Compact via `POST …/compact`; Doc/Plan opens inspector tab (pop-out stays); star for Goal; quiet Plan saved notices; WhatChanged max 3 + Show more; pane empties sans; quieter Settings About. |
| ~~**CS20**~~ | **Goal progress left/right; rail busy = shimmer title** | **DONE 2026-09-16** — GoalBar count+ASCII spin on the right (star/title left); rail drops the orbit spinner, keeps context dial, working title shimmers in accent like Thinking. |

**Non-goals for this cluster:** multi-CLI coding adapters as the product; general
IDE; worktrees-per-thread unless parallel builds collide; PR factory unless we
own shipping an adapter branch.

### The Stage — queued 2026-09-02, from Max's decision of the same day

One new surface for the work the 436px inspector hides: a full-width instrument
view with five panels and three sizes. Drawn before it was queued — the panels in
the artifact "Basilica Overview Components", the placements in "Overview in the
Shell" — every number in those drawings a real run from thread 33 of the Practical
ML workspace, which is the fixture every step below renders. The decision, verbatim
from `06-Decisions/Decision Log.md` in the vault: **C, a detached instrument window,
while a run launches and works; D, an inline row in the transcript, when it is done
— still expandable back into C; A, a draggable split in the shell, as the minimised
in-between. B, a docked strip above the composer, is dropped.**

The invariant that comes with it: the transcript is the record and the conversation
is the driver. The Stage never has a chat box. Nothing on it changes state without a
row appearing in the thread. When a run finishes, the window's content folds into
the transcript row where the result landed and the window closes or moves to the
next spending run — never two records of one thing. One selection, gold, shared
across every size. The Stage is a second READER of `GET /api/events`, never a second
writer; it computes no statistic the engine already computes.

| step | what | acceptance |
|---|---|---|
| ~~**S0**~~ | **The Stage's one read** — `GET /api/threads/{id}/stage`, `app/stage.py::build` | **DONE 2026-09-02** — rows per run off `eval_results` (with migration 14's re-bucketing overlaid), the paired verdict from `evals.compare` and never a second implementation, sandboxes with their runs read off `job.json` and the `MLH_EVENT` lines of `job.log`, the card from the guard's own `_gpu_occupancy`, the diagnosis from `journey_report.build`. Six tests in `test_the_stage_reads_what_the_thread_measured.py`, the last of which counts the thread's messages before and after the read and holds them equal: the reader filed no row |
| ~~**S1**~~ | Stage model — selected run (gold), panel, sizes | **DONE 2026-09-02** — `lib/stageState.ts`, a reducer with four actions; `stageState.test.ts` holds that a size change never changes the selection or the panel, and that the inline row is open at one anchor or none |
| ~~**S2**~~ | Panel: Bench | **DONE 2026-09-02** — runs as rows, eval rows as cells, flipped cells outlined against the baseline, the paired figures read off the payload. `Stage.test.tsx` renders the real thread-33 fixture (`fixtures/stage/thread-33.json`, `GET /api/threads/33/stage` off the live database): 9 runs × 30 cells, run 45's improved/regressed/p as `evals.compare` gave them. Screenshot looked at, at 1600, in all three sizes |
| ~~**S3**~~ | Panel: Sandbox Ledger | **DONE 2026-09-02** — pin, snapshot digests, reach, runs inside with elapsed and peak VRAM, the occupancy scale with the measured-memory rule and the guard's sentence. Driven on the real `practical-ml` sandbox: run_1 500 steps 56:23 · run_4 200 steps 46 s, both 6.65 GB peak, and the reading band says which was 29× slower per step and why |
| ~~**S4**~~ | Panel: Progression | **DONE 2026-09-02** — loss by step for the sandbox's train runs (A solid, B dashed 6 3) from the run logs' own events, beside the held-out scores of the adapter runs against the baseline with the stated target as a rule. Screenshot looked at |
| ~~**S5**~~ | Panels: Gate Map · Retrieval & Split | **DONE 2026-09-02** — NO_TRAIN__RAG, 3 of 5 PASSED, the ledger's sentence verbatim, 22 facts each with its origin and the instrument that produced it; recall 29/30 at k=5 on the full-glossary index, the split's rows and its leak check. A class-name collision with the evidence pane's `.gate`/`.fact` laid the gates out as a row on the first screenshot; every Stage class is now `stg-`-prefixed. **The recall defect is closed:** the panel now takes EVERY recall report in the thread and lets the person pick the index, because a thread that scored two retrievers holds two measurements and the newest is not "the" one — thread 33 shows three, two of them under one index id, which is why the chips are keyed by position as well as id |
| ~~**S6**~~ | Size D — the inline row | **DONE 2026-09-02** — a finished row whose result the Stage can draw carries `stage`; open, it reads `on stage` in gold and the Stage unfolds under it at column width. Browser check at **1280 and 1600**: `document.documentElement.scrollWidth > clientWidth` is false with the row open, and no console error. The inspector does not collapse to its rail on open; the row scrolls wide content inside its own box instead, which the check proves is enough |
| ~~**S7**~~ | Size A — the split | **DONE 2026-09-02** — a `stage` pane on the inspector's rail; arriving there by tab or by the row's split button widens the pane once (never touching a width the person dragged). **A defect the 1280 screenshot caught:** the first widen ignored `--col-min`, so at 1280 the chat fell to 360px, the inspector went to `overlay` and the Stage covered the conversation it is a view of. Both the widen and the drag clamp are now bounded by `viewport − rail − 420`. Screenshots looked at at 1280 and 1600 |
| ~~**S8**~~ | Size C — the detached window | **DONE 2026-09-02, with one half owed and named.** `open_stage`/`close_stage` (one window, label `stage`, rebuilt on re-point), the capability extended, `nativeOpenStage`/`nativeCloseStage`, `?stage=<thread>` routed in `main.tsx` to `StageWindow`, which follows the thread's own event stream and says `following`. Auto-open on a spending run and fold-in to D on completion are wired off the transcript's own rows. **Driven:** the shell compiled and ran (`tauri dev`, window up); the page at `/?stage=33` screenshotted in a browser. **Proved by test:** `src-tauri/tests/the_stage_window_is_declared_where_it_is_enforced.rs` — the label the builder uses, the two lookups, the registered commands, the capability's window list and the query parameter `main.tsx` routes on must all agree; a mismatch there is a webview that can invoke nothing. **Still owed, and it needs a person:** clicking detach in the running shell and watching a live run fold into D. No display automation in this environment can reach that window |
| ~~**S13**~~ | **The detached window drew an empty Retrieval panel** | **DONE 2026-09-02** — size C is the one the ruling puts on screen while a run works, and its Retrieval panel said "no retriever scored in this thread yet" about a thread that had scored three. The cause: a recall score is in NO table — the tool computes it, the reply carries it, the event log is the only durable record — and `StageWindow` took each event's id and dropped the event. It keeps them now, folds them with the transcript's own `foldEvents`, and reads them with the same readers `App` uses, so the two sizes of one Stage cannot disagree about what a thread measured. Those readers moved out of `App.tsx` into `lib/transcriptReads.ts` (six tests, red first), which is why the window could not reach them in the first place. Frames are keyed by id because a reconnect replays from `Last-Event-ID`. Screenshot looked at: three index chips, the curve to 29/30, the carve's 135 → 30 + 105 with 0 leaked |
| ~~**S12**~~ | **The Stage pane skipped the inspector's own contract** | **DONE 2026-09-02** — §9.12: "any pane whose content is derived carries one line under the header naming its source and when it was read… the strip is not optional and not hover-revealed." The Stage is the case that rule is about — nine runs' rows, the paired verdicts, the sandbox, the card and the diagnosis all arrive in ONE request — and it shipped without one. `paneProvenance` now answers for it and the line reads `from GET /api/threads/33/stage · re-read when the thread moves`, with the thread's own id in it; no thread open means no line, because a route with a placeholder would be a source line for data that does not exist. Four tests, one red first. Screenshot looked at. **No header qualifier, deliberately:** §18.4 allows one and the Stage's own run strip already carries the run count, so a second copy in the header would be the header arguing with the surface under it |
| ~~**S11**~~ | **The detached window could not be closed** | **DONE 2026-09-02** — found by reading the shell rather than the Stage: the window is `decorations: false` and its bar was a drag region with no controls, so a person who detached it was stuck with it. Worse, `on_window_event` hid EVERY window to the tray on close, and the tray menu restores `main` alone — a hidden Stage would have been a window that exists, cannot be seen and cannot be got back. `hides_to_tray(label)` now answers that question in one place, unit-tested in-crate; the app's window still hides because the engine outlives it, and a view closes for real. `StageWindow` renders `WindowControls` |
| ~~**S10**~~ | **The C→D transition itself, as a testable rule** | **DONE 2026-09-02** — the ruling was wired into `App.tsx` as three closures nothing could reach, which is the half of a decision that decays. `lib/stageTransition.ts` is now a pure function of the transcript — `spendingRows`, `foldAnchor`, `nextStageMove` — and `stageTransition.test.ts` holds all four moments plus the two judgements: a window the PERSON opened is never folded away (nothing in `seen`), and a run starting in the same frame as another finishing wins over the fold, because folding first would close a window the next evaluation reopens. Eleven tests, written red against a module that did not exist |
| ~~**S9**~~ | Reading bands and the glossary | **DONE 2026-09-02** — three cells under every panel from the payload's own figures with their run ids, plus a glossary line: eleven terms, each a dotted `.stg-term` with its one-line definition as a hover/focus card, `prefers-reduced-motion` respected. Which terms a panel shows is a property of the panel |

### The Journey Overview — queued 2026-09-02, from Max relayed the same day

His words: *"launching a journey overview following with granite 4.2, then
through the whole design model workflow with weights training, LoRA, any of the
following, with easy interactable tools, and simple prompting and
instruction."*

The thing being built: a person opens the app, says what they have, and is
walked from data to a trained adapter or an honest do-not-train — without
needing to know which of sixty-seven tools to reach for. `playbook.json` has
held the five routes since 2026-08-30 and `train_on_my_files` is seventeen
ordered steps; the route existed as data and nobody could see it.

**The law this surface is under is the Stage's:** it reads what the thread did
and never writes. A reader that wrote would file rows into the conversation it
is reading.

| step | what | acceptance |
|---|---|---|
| ~~**J1**~~ | **The engine answers "where am I on this route"** | **DONE 2026-09-02** — `app/journey.py` + `GET /api/threads/{id}/journey`, fourteen tests written red. Two questions kept apart, because one is not enough: a step is `done` when its tool left an ok `tool.result` in this thread, and `done_elsewhere` when every fact its tool declares in `measures` is on the ledger stamped by a DIFFERENT tool, which the reply names. Thread 33 is why — it walked this route for real and skipped five steps, putting its baseline on the record with `run_eval` rather than `measure_baseline`; "did step 13 run" reads that thread as stuck at step 2 forever, and ticking step 13 claims a tool ran that never did. A step whose tool measures nothing can only ever be `done`, because "all of them present" over an empty set is vacuously true and would tick every such step on an empty thread. Order is the route's claim and not the person's obligation: `next` is the first step that is neither, so running step 15 early moves nothing. **A defect found by running it against thread 32 rather than by reasoning:** a fact stamped by the step's OWN tool was reported as "done elsewhere, by itself" — the fact IS the record of that step running, and `evidence` now says whether the witness was the event or the ledger |
| ~~**J2**~~ | **The overview as a surface** | **DONE 2026-09-02** — a `journey` pane, FIRST in the rail, because "what am I doing and what is next" is the question under all the others; Machine's own argument is made on the first-run empty state, where a person meets it before any of this. `Journey.tsx` + `useJourney` (one GET per thread+lastEventId, never a timer) + `engine/journey.ts`. The engine's two states are kept apart on screen rather than collapsed into a tick: `done_elsewhere` reads "met by `run_eval` — it recorded baseline_measured, baseline_score, trivial_baseline_score", which is what thread 32 actually draws. Hue budget counted: green marks done, cobalt marks exactly one thing (the step you are on, where the accent's own meaning is literal), and nothing else is coloured. Nine component tests; browser-checked at 1280 and 1600 against thread 32 — 17 steps, one "you are here", one "met by", no horizontal overflow, zero console errors. §9.12's provenance strip is on it |
| ~~**J3**~~ | **One obvious action per step** | **DONE 2026-09-02** — the step you are on carries one sentence, its argument hint, and one cobalt "Do this step" button; every other step carries none. The button does not RUN the tool: the overview is a reader, and a reader that ran something would be writing into the thread it is reading. It opens that tool's own control, expanded and scrolled to, with the fields EMPTY — what goes in them is the person's to say, and a path this product guessed at would be the one thing it cannot measure. `Controls` and `ControlRow` took a `focus` prop for it. Three more component tests, including that no button is drawn when the surface was given no way to act, because a button that did nothing would be a promise the surface cannot keep. Driven in the browser against thread 32: one button, one dialog, exactly one control expanded — "Attach a folder or repository", which is step 1's `attach_context`. **Only 1 of the 17 steps takes no arguments, which is why a bare "run it" would have been dishonest for the other 16** |

| ~~**J4**~~ | **The design-model workflow end to end: a control opens knowing what the thread knows** | **DONE 2026-09-02** — Max's third item, and the training tail is what forced it: `run_in_sandbox` wants a sandbox NAME and `score_the_adapter` wants a sandbox, a BASELINE RUN ID and a thread id. Nobody can type those, and this harness measured all three itself — a form asking for them is a tool picker wearing a step's clothes. Each step now carries `prefill`, field name to `{value, from}`, read off the record: the carve's own result fills `eval_path`, `train_path` and `expected_field`; the newest sandbox fills `name`/`sandbox`; the thread's oldest complete eval run fills `baseline_run_id`. **Nothing is defaulted** — a value nobody measured is absent rather than guessed, because a guess sitting in a filled field is indistinguishable from a measurement to the person about to press Run — and nothing is offered for a field the tool's own schema does not declare. Every filled field shows `from …` under it in green, the same claim `Measured` makes everywhere else. Thread 33 answers with step 16 → `practical-ml`/`train` and step 17 → `practical-ml`/`42`/`33`. **The screenshot caught what the assertions could not**: `make_sandbox` answers with eleven lines about pinned requirements and egress, and drawn in full it swallowed the whole route — clamped to two with the full text on hover. Also: "opens knowing" moved off the `next`-only branch, because thread 33 is 13 of 17 with `next` at step 1 and the line would have hidden that the tail is ready. Five engine tests, two component tests; one first-draft assertion REWRITTEN rather than loosened, since a conversation always knows its own id |

| ~~**J5**~~ | **The training config itself, assembled rather than typed** | **DONE 2026-09-02** — J4 filled the sandbox NAME and left the hardest thing on the route to be hand-written: `run_in_sandbox.config`, which IS the training config Max named. Every part of it that can be known is now known. `base_model` is the repo the person had SIZED — `read_model_config`'s own answer, because reading a config is how somebody says which model they mean — and `dataset_path` is the training file **as the sandbox copied it**, matched to the carve's own `train_path` through the manifest rather than picked by a filename that looks right: the original and the copy are different files, and handing the original to a sandboxed run is the likeliest way this step fails. `max_steps` is deliberately absent — nobody measured it, the recipe's default stands, and a number invented here would sit in a filled field looking exactly like the two beside it that were read. The object is written into the form as JSON, because that is what the tool's own schema declares (`String({})` would have put `[object Object]` in the box). Also `attach_context.path` gets the project's own recorded folder, which is what made the whole path walkable in the browser. Live: thread 33 answers step 16 with base_model `SmolLM2-1.7B` and the sandbox's own copied train file; pressing **Do this step** in the running app fills `path` with the project folder under a green `from this project's own folder`. Four engine tests, one component test |

| ~~**J6**~~ | **The weights half, and the route walked from attach** | **DONE 2026-09-02** — steps 11 and 12 ask "can this machine train it" and "where should it run", and both now arrive holding the repo the person SIZED (`read_model_config`'s own answer). Step 10 is deliberately NOT filled: choosing which model to size IS the choice, and a shortlist entry offered into that field would be this product making it for them and calling it a reading. **Then the route was walked in the running app on a fresh thread (36) over the real workspace**, which is what found the rest: pressing *Do this step* on step 1 filled the folder, ran it, and the pane moved 0/17 → 1/17 with `next` advancing to Carve rows. Steps 4, 6, 7, 8, 9, 10, 11, 12 then ran for real — 30 rows carved out of 135, no leak, the count on the record, the bar STATED, the ladder read, the pick sized, and `where_to_train` answering "Local, on this machine. 4.99 GB is needed and this machine has 8.0 GB." **The walk found a false sentence**: a fresh thread on an old project was offered `practical-ml` under the words *"the sandbox you made"*, and that thread made nothing. Sandboxes are project-scoped, so offering it is right and the words were the defect — now "the newest sandbox in this project", with a test pinning it. Steps 2, 3 and 5 do not apply to this workspace, which arrived with graded rows rather than raw documents; the route says so honestly rather than pretending otherwise. Two engine tests |

| ~~**J7**~~ | **The LoRA choice, and what came out the other end** | **DONE 2026-09-02** — the two ends Max named. **LoRA:** `lora_r`, `lora_alpha`, `lora_dropout`, `learning_rate`, `max_seq_len` and `max_steps` are real knobs with real defaults, and a person had no way to know they existed — the recipe applied its own and the form said nothing. They are offered into the step's config now, read from a `[defaults]` table added to `recipes/hf-peft-lora/recipe.toml`, and `entrypoint.py` reads that same table with the old literals as its fallback, so there is ONE copy of each number and tuning one moves both readers. This reverses J5's decision to withhold `max_steps` and the reasoning is recorded: withholding was right while the only alternative was inventing one; a value the recipe DECLARES is neither invented nor measured, it is the setting that will be used, and hiding it served nobody. **The outcome:** a route could reach 17 of 17 and say nothing about what it produced — the scores sat in the eval bench, the adapter sat on disk, and a person had to go and find both. `journey.build` now carries an `outcome`, read off the thread's own runs with `evals.compare` — the same function the Stage uses and the same one `score_the_adapter` reported with, because a second implementation of "is this difference real" would disagree with the first within a month. Drawn as a card above the steps. **NO EVIDENCE is drawn as calmly as a win**: only a RESOLVED result borrows a claim colour, because a hue is a claim and "we cannot tell" is not one — a card that greyed that answer out while celebrating the other would be arguing with this product's own thesis. Live on thread 33: `NO EVIDENCE · 7% vs 13% · run 50 against 42`, with McNemar's p=0.688 and the 403 more rows it would take. Six engine tests, three component tests |

| ~~**J8**~~ | **The other answer: an honest do-not-train, on the route** | **DONE 2026-09-02** — Max's sentence was "data in one end, a trained adapter OR AN HONEST DO-NOT-TRAIN out the other", and J7 carried only the first half. The ledger's own verdict was reachable from the Evidence pane and from the Stage's gate map, and from nowhere on the route a person was actually walking — which is the answer this whole product exists to be able to give. `journey.build` now carries `verdict`, read from `journey_report` (the same builder the printable report and the Stage use; a second opinion about a verdict would be a second product). `trains` is computed once in the engine off the `TRAIN__` prefix the ledger's invariant is written in, so no reader downstream has to know that rule to tell the two answers apart. Drawn ABOVE the adapter's score, because a person told not to train should read that before they read what training got them, and it carries the gate count because a verdict is only worth the gates behind it. **Neither answer is coloured as good**: a do-not-train is this product's most valuable output and a TRAIN verdict is not a prize, so the name takes neutral ink in both cases and only the left edge changes. Live: thread 33 shows `NO_TRAIN__RAG · 3 of 5 gates passed` above `NO EVIDENCE · 7% vs 13%`; the fresh walk thread shows `ACTION__MEASURE_BASELINE · 1 of 5` and no outcome, because it has trained nothing. Three engine tests, three component tests |

| ~~**J9**~~ | **The controls were under the accessibility floor, measured rather than guessed** | **DONE 2026-09-02** — Max: the buttons are "very discreet, and sometimes they're hard or easy to mess up". Driven in the running app and measured with `getBoundingClientRect()` rather than read off the stylesheet: **11 interactive controls under WCAG 2.2 AA's 24x24 floor (2.5.8)**, and every one small for the same reason — it took its height from the text beside it. The Stage's own `stage` opener was 20px because it sits in a row set in 10px mono; `iconbtn--xs` was a 20px square; the segmented buttons 22px; two rail icon buttons 20px; the goal line 15px. `--tap-min` names the floor in `tokens.css` and the offenders now read it. Two exceptions are written down rather than ignored: the resize grabbers (16px across a ~1000px edge — the thing being dragged IS the boundary, 2.5.8 *Essential*), and inline glossary terms, which take vertical padding so the hit area is 25px while the line does not move. Re-measured across the Journey pane and all five Stage panels: **11 → 3**, and the three are the two grabbers plus `autotoggle`, which belongs to another session's file and is reported to them rather than edited. `docs/DESIGN_SYSTEM.md` §5.3 carries the law and the instrument, because a rule with no way to check it is a preference |

| ~~**J10**~~ | **Three accent elements saying one thing, and a state nobody could hear** | **DONE 2026-09-02** — prompted by the owner's node-kind ruling on the Sequence side ("a category is not a claim; six shapes was overspending on one"), asked of this surface and answered by measuring it: the Journey pane lit **three** accent elements — the step mark, a "you are here" chip and the button — and all three claimed the same thing. §3.4 allows one per screen, and says why: "a second accent element in the chrome means the accent has stopped meaning *the product needs you*." The button keeps it, because that is where the product genuinely needs a person. The mark for `next` is a neutral filled disc carrying a chevron, legible against an empty ring and a green check without a hue; the chip is gone. **The same audit found the state was announced to nobody**: `.jrn__mark` is `aria-hidden`, so every row read out its tool and nothing about whether it was done, next or untouched. Each row now carries `Step 2 of 17: Carve rows — you are here`, and a step met elsewhere announces `met by run_eval` rather than "done", because collapsing that for a listener would undo the distinction the whole engine keeps. Measured after: **3 accent elements → 1**. Three component tests; one earlier test REWRITTEN rather than loosened, since the property it asserted (exactly one step is the one you are on) is unchanged and only its mechanism moved |

| ~~**J11**~~ | **A step that was refused says so, and says what to do** | **DONE 2026-09-03** — two literature reviews commissioned overnight (vault `10-Signals/specs/teaching-evidence.md`) put numbers on feedback in a guided task: bare right/wrong is **d = 0.05**, DISCOURAGING feedback is **negative at -0.14**, and feedback that says why and what next is **0.49**, high-information **0.99**. This route said nothing at all, which is the other failure: **17 refused runs sat in one database's event log**, each carrying a `detail` this product had already written AS A REMEDY — *"needs an approval before it can run… it is a person saying yes to this specific action"* — and none of it reached the person walking the route. They pressed the button, it refused, and the step looked untouched. Steps now carry `attempted` and draw the tool's own sentence under an `TRIED` eyebrow: **neutral ink, no red, no cross, and the word "failed" appears nowhere**, because the evidence says the alarm is worse than the silence. A refusal survives only while the step is still not done — a remedy that worked and is still on screen is scolding somebody for something they already fixed, which is the -0.14 case exactly. Live on a fresh thread: step 7 reads *"There is nothing at …not-here.jsonl, so nothing was counted. Check the path and run it again."* **Measured at 1x, 1.5x, 2x and at 1100px**: every control clears the 24px floor except the documented grabber exception. Three engine tests, two component tests. **A limitation, stated:** approval refusals raise HTTP 428 and write no event row, so the route cannot see those — `run_tool_ep`'s approval branch belongs to another session and is reported to them rather than edited |

| ~~**J12**~~ | **Starting a journey is a click, not an essay** | **DONE 2026-09-04** — the last one-action gap, and it was the FIRST thing a person meets. The empty state has listed the five routes since the pane shipped and none of them was choosable: to get on one you typed prose in the chat and hoped `match_journey` agreed with you. `POST /api/threads/{id}/journey` records a chosen route, and the five are buttons now. **The goal is not touched**, and `set_thread_goal`'s own docstring is the reason — the goal is "the person's own words, verbatim… never a model's paraphrase", and a menu pick is not their words either, so the existing goal is read and written back unchanged beside the new route. A name the playbook does not carry is refused with the list rather than stored, because a thread holding a journey nothing can look up renders an empty route with no way back out. The buttons are quiet bordered controls rather than a second accent: §3.4 spends the accent on the step you are on, and five filled buttons would be five things claiming the product needs you. Their height comes from `--tap-min` rather than the list text beside them — measured live at exactly 24px, which is the floor and the same trap that put eleven other controls under it. Live: a brand-new thread reads "no goal on it yet", one click on *Train on my files*, and it is on a 17-step route at 0 of 17. Four engine tests, two component tests |

### GOAL — a journey completable by someone who has never used this

Set 2026-09-04. **Someone opens ML Harness, picks a journey, and reaches a
verdict without reading a manual, without a form, and without ever hitting a
screen that says something failed and stops there.**

This is the live task list for that goal. It is kept current as work lands; a
stale list is worse than none.

| # | task | state | deliverable · gate |
|---|---|---|---|
| G1 | Pick a journey in one click | **DONE** `7db161d` | five route buttons, goal untouched · 4 engine + 2 component tests |
| G2 | Every step says whether it can run, and what it still needs | **DONE** | `readiness` on each step: `click` / `approve` / `needs` + the missing field names · engine tests |
| G3 | A ready step RUNS on the button — no form | **DONE** | 7 of 17 steps run on one click; the pane advances · component tests + walked |
| G4 | A step needing approval asks once, showing what it will do | **DONE** | `approve` mode opens a confirm carrying the arguments, not a form. **Two clicks here is deliberate**: the registry's own rule is that approval "is a person saying yes to this specific action", and one click that sent `approved: true` would launder it |
| G5 | A step needing the person's own words says which words | **DONE** | `needs` mode names the missing fields on the button · component test |
| G6 | No step ends in a bare failure | **DONE** `b20563a` + this branch | returned refusals carry the tool's remedy (J11); refusals that RAISE (HTTP 428/400/422) are now caught at the button and shown the same way, closing the gap J11 named |
| G7 | Every control clears 24×24 after a real load | **DONE** | measured at 1×/1.5×/2× and 1100px · only the documented grabber exception |
| G8 | Walked end to end on this machine | **DONE** | fresh thread 39, clicked: pick route → attach → leak check → count → shortlist → sandbox → the training refusal, below |
| G9 | The route never dead-ends on a step that cannot run | **DONE** | **found by the walk, not by a test**: a workspace that arrived with graded rows makes step 2 (`carve_rows`) ask for a folder of markdown it does not have, so the one action pointed at something impossible while steps 6, 7 and 9 sat ready. `next` still answers "where am I"; `next_runnable` answers "what can I press", and the control follows the second. The blocked step keeps a quiet line saying what it wants · 4 engine + 1 component test |
| G10 | A refusal is printed once | **DONE** | the button's own refusal and the engine's `attempted` record are the same sentence and both were drawn — caught by a screenshot, invisible to every assertion. The local copy still earns its place: a refusal that RAISES leaves no event row, so it is the only surface that can carry it · 2 component tests |

| G12 | **The gate that says why**, from the research lane's built format | **DONE** | `10-Signals/specs/refusal-formats.md` §1 asks a refusal to carry "the rule, the value, its origin, the arithmetic". The route named the outcome and counted gates — the WHAT — and never the rule that stopped it. `verdict.blocked_by` now carries the first FAILED gate, its clause verbatim, and every fact that clause names with the origin the ledger stamped. **A fact nobody measured reads as unanswered, not false** — the commonest refusal here is `baseline_score is not null` failing because nothing has scored yet, and conflating those teaches the wrong lesson about what a gate does. The facts a clause reads are found by intersecting its identifiers with the ledger's declared names, never by parsing the expression, which would be this module holding an opinion about the ledger's grammar · 4 engine + 3 component tests |
| G13 | **Walked as a stranger, and it found a bare failure of my own** | **DONE** | fresh thread, nothing touched that I knew was there, every control measured after each screen. Under the floor: only the documented grabber, on all nine screens. **What it caught:** a refusal reading *"It did not run, and said nothing about why"* — a bare failure, d = 0.05, the exact thing this goal exists to prevent, and mine. Two causes fixed: the client read only `detail` when tools also refuse through `summary` or `error` + `help`; and the fallback itself was bare, where it now names where to look. **A third finding was my harness, not the product**: the remaining "no reason" clicks made no HTTP request at all — the walk script clicked before the confirm rendered. Re-driven with an explicit wait: one click → the confirm and its sentence → HTTP 200 → the full VRAM remedy |
| G14 | **A step that can be pressed is not the same as one that is useful when pressed** | **DONE** | `make_sandbox` declares no required arguments, so the route called it one-click — and clicking it made a sandbox with no recipe, which `run_in_sandbox` then refused correctly with "pins no recipe, so there is nothing in it to run". The route has always named its backend in the step's own `args_hint`; the recipe is read from there rather than written into `journey.py`, so a second route with a different backend needs no change nobody would remember to make · 1 engine test |
| G11 | A person who arrived with data can finish the route | **DONE** | was parked as a product call and is now DECIDED, because it needed no approval — it is an ordinary design judgement, reversible, and stating the reason is the whole cost. `train_on_my_files` opens by cutting a folder of markdown into rows, and every real walk of it has started from a graded JSONL instead; left alone the route read 13 of 17 forever and never completed, which fails the one thing it is for. **Marking those steps done would claim work nobody did; leaving them not-started would demand work nobody needs.** So there is a third state, `not_needed`, and the ROUTE declares when it applies — a step carries `unnecessary_if` naming the later step whose success makes it moot, in `playbook.json` beside the steps rather than as a table in `journey.py`, because a second route would otherwise need a second table nobody would remember to write. Drawn grey: not a tick, not a cross, "not needed here — carve_eval_set covered it". A step that ACTUALLY ran outranks being explained away. 5 engine + 2 component tests |

**Owned by another session, reported not edited:** `run_tool_ep`'s approval
branch (a 428 writes no event row, so the *log* never learns of it — this
branch catches it at the button instead), and `autotoggle` at 22×70, 2px under
the floor.

### The workbench, and the prerequisite that had to be built first

Step C above is the product's own thesis — the six refusals that name a cheap,
local fix are the sentences worth more than any training run, and until
2026-08-27 each was a verdict and nothing else. `NOT_COVERED` already said
precisely what the first one needed:

> the paired proof is designed (change description, re-run same rows, McNemar)
> and half-built: `run_the_failures` grades leg one today. The owed piece is the
> compare step wired to `evals.compare` over two recordings.

**Checked rather than believed: `app/tools/agents.py` contained no database
write at all.** A rate was stamped on the ledger and the rows behind it were
dropped, so there was no first recording for a second one to be compared
against. Building the compare before the storage would have produced a paired
comparison that is not paired — the exact defect the eval bench's design exists
to prevent — so the order was storage, then compare, then the six.

**`v012_an_agent_run_keeps_its_cases`** gives a run its cases: `agent_runs` and
`agent_results`, thread-scoped and cascading, mirroring `eval_runs` /
`eval_results` rather than reusing them (an eval run scores a MODEL through a
prompt; an agent run grades a recording somebody's AGENT produced, and this
harness never drives that agent). **The pairing key is `case_key`, a digest of
input+expected, and not `row_index`.** An eval set is a file this harness
carved and counts through; a failure set is the person's export, and between
two recordings they will have re-exported it, sorted it, dropped a fixed case
or added three. Pairing on position would compare case 7 of one run against a
different case 7 of the other and call the difference an improvement.

**`read_agent_results`** reads one recording back, or compares two pairwise over
the cases both graded, with `evals.mcnemar` and `evals.resolution_for` — the
same functions the eval bench uses, because a second implementation of "is this
difference real" would disagree with the first within a month. It refuses two
runs that share no question, and reports what only one side holds rather than
scoring it.

**The six builds** are then one proposer with six sentences:
attach → grade before → grade after → compare → re-enter the tree. The harness
never writes somebody's tool description; it refuses by name on
`after_answers_path` and measures whether the one they wrote worked. **The exit
criterion is that a verdict EXISTS and never that it is favourable** — NO
EVIDENCE is a successful outcome of this build, and
`tests/test_the_workbench_proves_a_fix_or_says_it_cannot.py` drives both
answers out of the same build with the same criterion.

**Three declarations driving it found, none of which reading would have.**
`run_the_failures` takes three arguments that can name a file, so nothing could
tell which one a step would open and the 'after' leg was refused outright. It
now declares `subject=("failures_path",)` — the `ToolSpec` field
`app/build.py::declared_subject_arguments` had specified in full and the
registry had never grown. The compare step declares `operates_on=None`, because
it opens no file at all. And both run ids reach the comparison as `Ref`s from
the legs that wrote them, because a row id is decided at insert time and a plan
naming one would be naming a row that does not exist yet.

---

### Step 1 landed without its acceptance, and looking at it found a defect

`8e20246` added `frontend/src/components/JourneyActions.tsx` and the two client
functions behind it, which is the feature. Its acceptance — a browser check —
was driven on 2026-08-27 and is recorded in the row above.

What a look at the code found first, before any thread existed, is that the CSS shipped with
three property names this product does not define — `--sp-3`, `--text-xs` and
`--danger`. An undefined custom property is not an error in CSS; the declaration
is dropped in silence. Measured in Chromium against the running UI, with the
markup injected onto the app bar: the button gap computed to `normal` rather
than a spacing step, and the failure line inherited the body's 13px and the
body's ink — on the one string in that row that must not read as ordinary text.
Fixed to `--sp-4`, `--t-11` and `--wont` (the role `.toolrow[data-state='failed']`
and `.streamstate[data-status='failed']` already use), and re-measured in the
same browser: `gap 4px`, `font-size 11px`, `color rgb(244,124,124)` against a
body of `rgb(245,245,247)` at 13px.

**The class is one this file already knows.** `--sp-3` and `--danger` are the
CSS spelling of the defect closed on 2026-08-24 under *"a constant one module
owns and another module spells"*. Nothing in the repository refuses an undefined
token, which is why a UI step's acceptance is a browser check and not a diff.

---

## Debts — real, found, not yet paid

These are not phases. They are things measurement has already found, and they
will be forgotten if they are not written down.

- **THE CONNECTED MODEL IS GLOBAL, so a measurement's meaning depends on what
  another lane last selected.** On 2026-09-09 a `measure_baseline` on thread 46
  silently ran against `Bonsai-27B-gguf:Q1_0` because a concurrent lane had
  changed the active provider mid-flight; the caller asked for a baseline and got
  one, against a model it never named. This is the per-thread `baseline_score`
  trap one level up — that one was fixed by scoping the FACT to a thread, and the
  MODEL is still global. Nothing refused and nothing warned.
- **`measure_baseline` stamped three MEASURED facts on thread 46 and left no
  `eval_runs` row**, so there was no `baseline_run_id` to hand
  `score_the_adapter`, which correctly refuses to borrow another thread's run
  ("a measurement made in another conversation is somebody else's"). Whether that
  is a defect or a deliberate split from `run_eval` is NOT established; it is
  written down because it is what stopped step 7 short of its done-condition.

- ~~**Any tool may claim any fact.**~~ **PAID 2026-08-27.** Wall 9: a fact
  declares `measured_by:` and names a CAPABILITY, from the same closed
  vocabulary `contract.capabilities.needs` uses — capabilities rather than tool
  names because a ledger is domain knowledge and a rename would silently unbind
  every fact in the file. Checked twice, for the reason `measures=` already is:
  at registration in `registry._validate`, swept over every shipped ledger,
  where a reviewer reads it; and per call in `Instrument.measured`, where the
  thread's own ledger is known. 23 facts across both ledgers are bound.
  The defect it closes is not hypothetical and not about malice: every one of
  the eight walls before it asks *where did this number come from*, and a tool
  of the wrong KIND passes all eight honestly — `fit_a_tree_model` scoring a
  real accuracy on a real CSV and opening G1, the gate about a text baseline.
  Driven in `tests/test_a_fact_names_its_instrument.py` with the number computed
  inside the test, so what is refused is a measurement that is true.
  **Silence stays legal and a ratchet is what keeps that from being the debt
  again:** every fact some registered tool measures must declare `measured_by:`,
  so an instrument that ships without one reddens the run that adds it.
- ~~**A hanging test presents as a slow suite.**~~ **PAID 2026-08-27.**
  `faulthandler.dump_traceback_later` is armed around every test at 60 seconds
  from `tests/support.py`, patched onto `unittest.TestCase.run` so the first
  module that imports support bounds every test in the process — the only hook
  plain `python -m unittest discover` offers. `exit=False`, because killing the
  interpreter turns one hung test into no results at all.
  `tests/test_a_hung_test_names_itself.py` drives a child interpreter and
  asserts the trace fires, names the test, and does not end the run.
- **1.1 GB of debris in `runs/`** — the same model downloaded four times into
  directories literally named `~`, from the `expanduser` bug. Fixed going
  forward; the existing copies are the owner's to remove.
- **A test overwrote the real pinned training environment** and the root cause
  was never found. A guard now converts it into a failing test that names itself,
  which is the durable answer; the diagnosis is not.
- ~~**`docs/ROADMAP.md` is 4,748 lines** and predates the pivot.~~ **PAID
  2026-08-27.** Retired as the queue and kept as the reference, with a header
  naming which of its sections are stale and to which commit they are pinned.
  `AGENTS.md`'s authority table now sends "what do I build next" here.

### Found on 2026-08-24, by adversaries, against work that had passed its own tests

The five closed here are recorded because the CLASS matters more than the
instance, and because one of them was reported wrongly and the correction is the
useful half. The last two were found against Phase 1a and its neighbours on the
same day the phase was declared done, which is the argument for the adversary in
one line.

- **CLOSED — a gated prefix over an empty gate list.** `gated: all` over
  `required_gates: []` is vacuously true, and every other corner of that shape
  was already refused: LF023 both ways, LF025, LF050, LF051, SC1. All five stayed
  satisfied and all five became no-ops — the sweep had nothing to ask and
  `_finish`'s `ERROR__GATE_SKIPPED` compared against an empty list. Measured on
  the conformance corpus's own committing ledger with one line changed: verdict
  `DO`, outcome `DO__THE_THING`, `gate_ledger {}`, while the gate requiring
  `count >= 10` sat defined in the same document and `count` was 1. Now `LF027`.
- **CLOSED — a fifth place a ledger may state an outcome, and nothing scanned
  it.** `fork: no_match: {outcome: ...}` arrived with the fork grammar; SC1
  gathered minters from `node.get("outcome")` alone, so a ledger could mint the
  gated prefix from a fork in any node and SC1 would report `found []`.
  `Spec.outcome_sites()` is now the single enumeration and every check reads it,
  with a test that scans the raw document so a SIXTH site is a red test rather
  than a blind spot.
- **CORRECTED — "a gate's `node:` is not checked for existence" was reported as a
  defect and is not one.** A gate's node id names nothing else in the document by
  design; it is the id the gate machinery writes onto the path, and it is absent
  from `node_index` for all ten gates in both shipped ledgers. Checking
  membership would have refused every honest ledger. The two real defects in the
  same place — two gates sharing a node id, and a `stage:` that disagrees with
  where the `gate_ref` sits, both of which reach a person's card through
  `app/asking.py:_because_for` — are now `LF015`. **The lesson is the one this
  file already believes: a finding that names a check is worth less than a
  finding that names a consequence, and an adversary's diagnosis is a hypothesis
  until it is driven.**

- **CLOSED — fifteen of forty tools could not be selected on any thread against
  either shipped ledger.** Found by an adversary against Phase 1a, confirmed by
  re-measuring, and fixed by the ledger declaring `contract.capabilities.needs`.
  The class is the useful half and it is a new one: **a bound that only ever
  pushes in one direction cannot see the failure in the other.** Every assertion
  in `test_a_turn_says_which_blocks_it_loaded.py` was a strict `<` against the
  registry, and all of them stayed green while a third of the product became
  unreachable — because "fewer than 40" is satisfied by 12 just as well as by
  12-of-a-reachable-40. The floor is now asserted beside the ceiling:
  `EveryToolIsReachableFromSomeAnswerTest`, which sweeps all 73 sheets and
  asserts the union of packs is ALL of them and the union of tools is all 40.

- **CLOSED — the two most common early builds could never verify, and had not
  since they were written.** `app/tools/propose.py` stated `value="passed"` on
  the exit criterion of both eval-set builds; `app/diagnosis.py` writes `PASSED`;
  `build._compare`'s `equals` is an exact string test, as it must be. Driven over
  HTTP on a scratch database: every step `done`, the eval set really carved and
  really counted, `deviations: []`, and the storm ends `failed` with
  `"because": "saw 'PASSED', wanted 'passed'"`. **Nothing in 3,000 tests compared
  the two words** — the storm suite asserted WHICH criterion was judged and WHAT
  was seen, and never the verdict. `diagnosis.GATE_PASSED` is public now and
  there is one spelling; the driven assertion and a structural sweep over every
  proposer's criteria are both in the storm suite, and both go red if the literal
  is typed again. The class: **a constant one module owns and another module
  spells is a defect waiting for a rename, and an assertion about a comparison's
  INPUTS is not an assertion about its RESULT.**

Two of the three below were paid on 2026-08-27; what is still open is
named under each and is smaller than the entry it came from.

- ~~**The condition dialect has no bound on cost.**~~ **PAID 2026-08-27.**
  `diagnosis.CONDITION_STEP_BUDGET` — 100,000 evaluation steps for one
  condition, counted in `_Evaluator.visit`, which is the one door every
  `visit_*` reaches its children through, so a comprehension's per-item work is
  counted too. **And the half this debt actually asked for was to say WHICH
  KIND: robustness.** Nothing here defends against an attacker; a ledger is a
  file a person wrote and a reviewer read. What it defends against is an
  author's honest mistake becoming a hang — a sum over a fact that turned out to
  hold half a million rows. If a ledger ever does become untrusted input this
  bound is necessary and not sufficient, and that sentence belongs here rather
  than in a later post-mortem.

  **A step count and not a clock, and that is the decision worth reading.** A
  wall-clock timeout would make a ledger's validity a property of the machine it
  is evaluated on — the same file passing on a laptop and failing in CI under
  load — and a diagnosis that depends on how busy the box was is not a
  diagnosis. Deterministic, so a ledger that loads here loads for everybody.
  Measured over every fixture sheet, the most expensive real condition costs
  **35 steps**; the ceiling is re-measured by
  `tests/test_a_condition_cannot_run_forever.py` so a change in kind is reported
  rather than absorbed. It raises rather than answering False: a gate decided by
  a condition that ran out of budget would be a gate decided by exhaustion.

- **Thirteen files call `default_spec()` unconditionally, and the debt is now
  BOUNDED rather than merely written down.** Per-thread ledger landed in
  migration `v011` and most tools take `ledger` through injection. The
  2026-08-26 sweep read `app/tools/` only and reported 9 files; re-measured
  over the whole package on 2026-08-27 it is **31 calls in 13 files**, pinned
  per file as a ceiling in `tests/test_the_default_ledger_is_a_bounded_debt.py`.
  Removing a call is free; adding one — or a fourteenth file starting to read
  it — turns the suite red and asks for a sentence. Three files' calls are
  ARGUED rather than owed (`evidence.spec`'s two honest callers,
  `propose`'s tables keyed to the first ledger's outcome ids, `asking._spec`),
  and the test asserts each still carries its written argument, because deleting
  the paragraph and keeping the call is how an argued exception becomes an
  unexamined one.

  **One of them was live on an HTTP route, and it was found by driving rather
  than by reading.** `GET /api/next_step` on a thread running the AI ledger
  answered `BLOCKED__DEFINE_SUCCESS_FIRST`, asked for `classes_n` — a fact that
  ledger does not declare — because of `S0_RULES_SUFFICE`, and named
  `assess_the_data`, a tool whose stamp `v011`'s wall would then have refused.
  Four wrong things, all confident, exactly as Phase 0 predicted: *"a second
  ledger will diagnose correctly and then hand its verdict to a tool layer still
  reading the first ledger's file."* `app/asking.py::_spec`'s own docstring gave
  the reason — *"the product has one ledger"* — a sentence that was true when it
  was written and stopped being true at `v011`. **A stale argument in a
  docstring is how a fixed defect stays fixed only where somebody remembered.**

  `next_step_ep` now refuses that request with a 409 naming both ledgers and the
  route that does work, rather than serving a card from the other domain's tree
  (`tests/test_a_card_is_not_offered_in_the_wrong_domain.py`, which constructs
  the wrong card to show the refusal is refusing something real). **What remains
  owed is making `app/asking.py` ledger-aware** — eleven functions and two
  dataclasses, one of which builds cards in `__post_init__` — and until that
  lands the limit is loud at the boundary instead of silent inside it.

### Closed on 2026-08-26 — were listed as open on 2026-08-24

- **CLOSED — four AI `inspect` facts had no instrument.** Shipped as
  `read_agent_traces`, `read_tool_definitions`, `run_the_failures`,
  `bound_the_loop` in `app/tools/agents.py` at `972f906`.
- **CLOSED — every tool read the ML ledger whatever thread it was on.**
  Migration `v011` adds `threads.ledger`; `evidence.spec(thread_id=...)` resolves
  the thread's ledger. Merged at `b250467`, before the instruments branch.

---

## Decisions still open, with who decides

Written here so they stop living in conversation, where they decay.

| decision | owner | why it is not decided |
|---|---|---|
| **The product name.** "ML Harness" no longer describes it, and the repository directory carries the name. | Max | renaming costs paths, every document, and a sibling project's integrations. It is a call, not a side effect of a rewrite. |
| **Ledger file format.** YAML today; `docs/LEDGER_FORMAT.md` argues it at six ledgers. | the research lane, then Max | committing to a format outside authors write against is harder to undo than any code here |
| ~~**Whether a fact declares which INSTRUMENT may measure it**~~ | ~~this plan~~ | **DECIDED 2026-08-27: yes, and it names a capability rather than a tool.** See Debts above. The shape is the one this row predicted — `declare what belongs to what`, the same as capability blocks — and the capability-not-tool-name half is what makes it survive a rename. |

## The one rule that governs all of it

Every phase above can be faked. Coverage can be inflated with proposers that
mislead, journeys can be recorded on data chosen to work, a ledger can be written
for a domain nobody has, and a launch can ship a README that oversells.

The defence is the same in every phase and it is the thing this project is
actually good at: **an adversary whose default verdict is REFUTED, given routes
nobody wrote down.** Every serious defect found in this repository was found that
way, including the ones found in work that had already passed its own tests.

Do not skip it to move faster. It is the only reason any of the numbers above
mean anything.

---

## Where every phase actually stands, audited 2026-09-10

Read against each phase's own written done-condition, with the evidence, because
this file has twice carried a status that was correct when written and stale
when read. **Every row below was checked in this pass rather than copied from
the section above it.**

| phase | its own done-condition | status |
|---|---|---|
| **0a** second ledger on one engine | a second domain diagnoses end to end with no engine change | **DONE** 2026-08-24 — `ai_engineering.yaml`, `BUILD__` prefix, its own five gates, seven measured sheets |
| **0b** one journey closes on real data | a thread from a file to an artefact, every number carrying an origin | **DONE** — second journey, twelve rungs, re-driven under capability blocks |
| **1a** capability blocks | only the blocks a diagnosis calls for; budget stops rising; visible as a label | **DONE** 2026-08-24, all three measured |
| **1** the AI ledger | an agent problem diagnosed, verdict often "do not", three outcomes build | **MOSTLY DONE.** The React surface is **done** and this file said otherwise until today. **The TRAIL census is the one real gap and it is blocked on a download.** |
| **2** the data floor | thirty examples, no eval set, a measured result; no generated row ever opens a gate | **DONE** — the two walls, and step 7 driven end to end to a gated verdict on a cold thread |
| **3** coverage | *replaced*: a stage may sit at zero builds only if every dead outcome names what is absent | **DONE and ENFORCED** by `tests/test_a_stage_with_no_builds_has_a_written_reason.py`, which went red when written and found the `REROUTE` over-count |
| **4** sandboxes | build, run, inspect, dispose an environment without a shell | **DONE** 2026-09-09 against its own condition |
| **5** launch | zero to a diagnosed problem without asking a question | **DONE 2026-09-10 (5a935f6)**: in Windows Sandbox, on a rebuilt installer, a stranger installed it, pulled a model, and was told `BLOCKED__DEFINE_SUCCESS_FIRST`. This row said ONE LINK UNDRIVEN until 2026-10-01; the paragraph below is the 2026-09-10 audit and is kept as history |

### The two things that are open, and neither is buildable here

**Re-read 2026-10-01:** the Phase 5 half below was driven the same night (5a935f6) and is closed. The TRAIL half is still open: the dataset is gated, so it needs a Hugging Face login that has accepted its terms (HTTP 401 without one, checked 2026-10-01).

**Phase 1's TRAIL census** needs `PatronusAI/TRAIL` fetched. The cache entry
exists and holds forty bytes of commit sha.

**Phase 5's last link** is the click-through on a machine that has never seen
this repository. The install is measured in a Windows Sandbox; the banner →
connect → diagnosis walk is measured on this machine against a scratch engine
with zero providers. **What has not been done is both at once**, and it cannot
be: a sandbox has no Ollama and no key, so both roads out of that banner leave
it. That needs a model pulled inside the sandbox or a key — **a decision, not a
measurement.**

**Everything else in the plan is closed against the condition it was written
with.** Where a done-condition was wrong — Phase 3's was — it was replaced in
writing, with the reason, and the replacement is enforced by a test rather than
asserted here.
