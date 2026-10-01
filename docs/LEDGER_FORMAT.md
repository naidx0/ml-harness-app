# The ledger format — where the engine ends and a domain begins

Research output, 2026-08-24. **No product code was written for this document.**
Everything below that carries a number was measured; the commands are pasted
where the number is used, and a prototype that proves the recommendation runs is
described in [§10](#10-the-proof-that-this-runs).

`docs/VISION.md` stakes the platform thesis on one sentence: *"A second ledger
runs on the same engine with no code change."* `docs/PHASES.md` makes that Phase
0a and says the deliverable is either the second ledger or **the exact list of
what is in the way**. This is that list, plus the design that removes it, plus
the reason the design is still right at six ledgers rather than two.

**The one-line recommendation.** Move four names out of Python and into a
`contract.roles` block; give routers a declared schema with a closed selector
vocabulary owned by the engine; validate in three named tiers instead of 64
scattered `_require` calls, and never let tier 3 become data; version the
*format* separately from the ledger's own content and refuse-or-upgrade rather
than guess; stay on YAML and make it a **constrained** YAML with a strict loader.

---

## 1. What is actually in the way

The header of `docs/ledgers/ai_engineering.yaml` lists three blockers. Two of
them are real and understated, one of them is **not a blocker at all**, and the
largest blocker is not on the list. This matters, because the list is what the
next lane would have implemented.

### 1.1 The probe

A ledger was patched in memory, one fix at a time, and re-loaded after each. The
repository was not touched; the scratch copy lived in a temp file.

```
 1. the file as its author wrote it          -> KeyError: 'route'
        [diagnosis.py:608 in _collect_literals]
 2. + derived.route invented                 -> SpecError: node S9_ROUTE describes routes in prose and has no handler
 3. + router written the ML way              -> SpecError: node S9_ROUTE routes by a key the engine has no rule for
 4. + router deleted entirely                -> SpecError: node S9_MINT_BUILD_VERDICT: uses undeclared name 'UNSET'
 5. + a proposing node instead               -> SpecError: node S9_MINT_BUILD_VERDICT: uses undeclared name 'UNSET'
 6. + a pseudo-method named UNSET            -> SpecError: node S9_MINT_BUILD_VERDICT declares the templated outcome
                                                'BUILD__{proposed_method}' and no `emits` list
 7. + emits listing the BUILD__ family       -> SpecError: SC1: exactly one node may emit a TRAIN__ outcome; found []
 8. + SC1/SC4 neutered in the probe          -> LOADS
```

Read step 8 twice. **Once four ML names are out of the way the second ledger
loads**, and what remains (`ERROR__NO_NODE_MATCHED: stage_0_admissibility ran off
the end`) is a content bug in the author's own file — it declares its gates but
never places a `gate_ref:` in a stage, so no gate is ever evaluated. That is
encouraging and it is also the reason to get the boundary right rather than
patch four names: the machine is nearly domain-general, so the remaining cost is
almost entirely *deciding what the interface is*.

### 1.2 The corrections to the header's list

**Blocker 1 is real and understated.** `STAGE_9 = "stage_9_method_selector"` is
one of *two* stage constants; `ENTRY_STAGE = "stage_0_admissibility"` is the
other, and it is read by the walk itself (`diagnosis.py:2241`), not merely by the
loader.

**Blocker 2 is much larger than "the shape is undocumented".** A router's `routes:`
mapping is only half of a router. The other half is a Python function registered
by node id:

```python
ROUTE_KEYS: dict[str, Callable[[_State, dict[str, Any]], str]] = {}
```

Two are registered, `S0_MODALITY_FORK` and `S1_ROUTE_BY_FAILURE_MODE`. A ledger
whose router is not one of those two names **cannot have a router at all**, no
matter what it writes. The same is true of `ACTION_HANDLERS` and
`CONDITION_HANDLERS`; measured, in `app/diagnosis.py`:

```
$ grep -c "^@_action("     app/diagnosis.py   ->  9
$ grep -c "^@_condition("  app/diagnosis.py   ->  1
$ grep -c "^@_route_key("  app/diagnosis.py   ->  2
```

Twelve node handlers, every one keyed by a node id of the first ledger. And:

```
$ grep -o '"S[0-9]_[A-Z_]*"' app/diagnosis.py | sort -u | wc -l
13
```

Thirteen node ids of the ML ledger are named in the engine. That is not a schema
gap; it is the engine holding a private list of the first ledger's nodes.

**Blocker 3 is wrong.** The eight blocks — `escalation_ladder`, `shadowing_rule`,
`helpers`, `uninspectable_facts`, `static_checks`, `runtime_checks`,
`sources_policy`, `sources` — are **not required by the loader, and not one of
them is read by the engine or by any tool**. Counting every Python reference to
each block name across `app/` and `tests/`:

```
escalation_ladder      app/=0   tests/=0
shadowing_rule         app/=0   tests/=0
helpers                app/=0   tests/=0
uninspectable_facts    app/=0   tests/=2
static_checks          app/=0   tests/=0
runtime_checks         app/=0   tests/=0
sources_policy         app/=0   tests/=0
sources                app/=5   tests/=1
```

The five `sources` hits in `app/` were checked one by one and none of them is the
ledger block — they are `app/hwdetect.py`, `app/provenance.py`,
`app/tools/models.py`, `app/tools/training.py` and `app/tools/__init__.py`,
reading a hardware-spec `sources` dictionary of the same name.

The loader requires exactly seven top-level keys — `version`, `contract`,
`methods`, `gates`, `facts`, `derived`, `fact_origins` (`diagnosis.py:632`) — and
the probe never once complained about the eight. The author's file loads past
them. What it *does* require blindly is `derived["route"]`, which is why step 1
is a bare `KeyError` rather than a `SpecError`: `_collect_literals` reaches into
`raw["derived"]["route"]` with no guard.

**And the blocker that is not on the list at all is the biggest one.** `SC1`
hardcodes the string `TRAIN__`:

```python
minters = [node_id for node_id, node in spec.node_index.items()
           if isinstance(node.get("outcome"), str) and node["outcome"].startswith("TRAIN__")]
_require(minters == ["S9_MINT_TRAIN_VERDICT"], ...)
```

`docs/VISION.md` already names this exactly right: *"eight are the `TRAIN__`
prefix — which is not an ML concept but a role: the expensive irreversible
outcome that must pass every gate."* SC1 is that role, written as a literal. No
second ledger can satisfy it, and no second ledger should have to spell its
verdicts `TRAIN__`.

### 1.3 The wall behind the wall, which nobody has costed

The engine is not the only thing bound to the first ledger's names.

```
$ grep -rn "default_spec()" --include=*.py app/ | grep -v "def default_spec" | wc -l
26
$ grep -rln "default_spec()" --include=*.py app/ | grep -v diagnosis.py | wc -l
11
```

Twenty-six call sites across eleven modules besides `diagnosis.py`, and
`default_spec()` resolves to `SPEC_PATH` — the ML ledger — unconditionally. Those
call sites then index it by ML id: `G0_EVAL_SET`, `G2_PROMPT_EXHAUSTED`,
`S8_TABULAR_STANDARD`, `S1_ROUTE_BY_FAILURE_MODE` and eight more, twelve distinct
ids in six tool modules.

This document does not solve that, and pretending otherwise would be the same
failure mode the header comment fell into. It is named here, with its number, in
[§12](#12-what-this-does-not-fix) — because a boundary that fixes the engine and
leaves the tools reading a hard-wired ML ledger is a boundary that will be
discovered as broken by the person writing ledger three.

### 1.4 The size of the validator

```
load-time validation region = load_spec .. _static_checks (lines 625-1060)
  _require( sites          : 62
  raise SpecError sites    : 2
  total load-time checks   : 64
  lines in that region     : 436
```

64 checks in 436 lines. The brief guessed ~40; it is 64. That density is
[§7](#7-should-the-engine-validate-against-a-declared-schema)'s whole argument:
SC1's hardcoded `TRAIN__` has been sitting in the middle of it since the file was
written, and nobody saw it, because it looks exactly like the other 63.

---

## 2. What everybody else does, and what they agree on

This is a solved problem in seven other places. They disagree about syntax and
agree about structure, and the agreement is the useful part.

| system | names the entry point | router / branch | validates by | versions the format |
|---|---|---|---|---|
| **OPA / Rego** | `entrypoint: true` **annotation** in the policy, or `-e` on the CLI | rules; `default` rule for the else-branch | `opa check`; `schemas` annotations bind a data path to a JSON Schema | `import rego.v1` opt-in, then a default flip; `--v0-compatible` for stragglers |
| **DMN 1.5** | a Decision Service lists its **`outputDecisions`** (plural) | decision table with a **`hitPolicy`** from a closed set | Drools' `DMNValidator`: `VALIDATE_SCHEMA`, `VALIDATE_MODEL`, `VALIDATE_COMPILATION` | model namespace / spec version |
| **JSON Schema 2020-12** | `$id` / `$ref` | n/a | the **meta-schema** named by `$schema`; `$vocabulary` says which are mandatory | `$schema` URI *is* the version; unknown keywords become annotations |
| **CEL** | the embedding app declares the environment | n/a | parse → **check against declared environment** → evaluate | environment versioning by the host |
| **Kubernetes CRDs** | `apiVersion` + `kind`; `versions[].storage: true` picks the one stored | n/a | structural OpenAPI schema, plus CEL `x-kubernetes-validations` with `message` | many versions served, one stored, **conversion webhook**, round-trip without loss |
| **Terraform providers** | `required_providers` block names them | n/a | provider schema, checked by core | `SchemaVersion` + `StateUpgraders`; protocol **negotiated** in the handshake |
| **Python packaging** | **entry points** declared in package metadata, discovered by group | n/a | n/a | n/a |

Four things every one of them does, and this engine currently does none of:

1. **The name the machine must find is declared by the author, not compiled into
   the machine.** OPA's `entrypoint` annotation, DMN's `outputDecisions`, CRD's
   `storage: true`, `[project.entry-points]`. Not one of them says "the rule must
   be called `authz`".
2. **The branching *strategy* is a closed vocabulary the engine owns; the
   branching *table* is data the author owns.** DMN's hit policies are the
   cleanest statement of this: an author picks `UNIQUE` or `FIRST` or `COLLECT`
   from a list and never writes hit-policy code.
3. **Validation is tiered and each tier has a name**, so a failure says which
   kind of wrong it is. Drools names three tiers explicitly.
4. **The format version is a first-class field with a declared policy for the
   unknown.** JSON Schema is the sharpest: *"If the value is true, then
   implementations that do not recognize the vocabulary MUST refuse to process
   any schemas that declare this meta-schema with `$schema`."* Refusal, not
   best-effort.

---

## 3. The principle that decides the rest

The five-gate honesty test is the product. Every design choice below is settled
by one question: **does this make the honesty test easier to state and harder to
weaken, or does it move a piece of it into data where an author can quietly
delete it?**

That gives a rule with real teeth, and it is the rule this document keeps
returning to:

> **The ledger owns every *name*. The engine owns every *rule about names*.**

A ledger may choose to call its commit stage `stage_9_shape_selector`; it may not
choose whether a proposal must reach one. A ledger may name its irreversible
prefix `BUILD__`; it may not choose whether that prefix requires every gate. A
ledger may write a router table; it may not write the router's algorithm.

The corollary settles the required-versus-optional question, which is otherwise
a matter of taste:

> **The axis is not required-to-*have*. It is required-to-*state*.**

Eight blocks a small ledger has no use for should be optional to have — nothing
reads them (§1.2). But a ledger with **no** commit stage must say
`commit_stages: []` in so many words, because the difference between "this domain
has no irreversible outcome" and "somebody forgot" is the entire honesty test,
and a default would erase it. `_load_origin_policy` already argues this in the
engine's own voice: *"Safe and broken is not the same as safe and working, and a
build that stops is the only way anyone finds out which one they have."*

Applied to the top level, that gives three categories rather than two, and the
middle one is the one every schema language gets wrong:

| category | blocks | rule |
|---|---|---|
| **Required to have** | `ledger_format`, `contract`, `facts`, `fact_origins`, `methods`, `gates`, at least one `stage_*` | the engine cannot walk without them |
| **Required to state** | `contract.roles.commit_stages`, `contract.required_gates`, `no_match:` on every router, `gated:` on the committing prefix | a default here would silently decide something load-bearing. Empty is a legal answer; *absent* is not |
| **Optional** | `escalation_ladder`, `shadowing_rule`, `helpers`, `uninspectable_facts`, `static_checks`, `runtime_checks`, `sources_policy`, `sources`, `derived`, `fact_scopes` | documentation and per-ledger house rules; absent means empty |

`required_gates: []` deserves the same treatment as `commit_stages: []`: legal,
and only when written. A ledger with no gates and no commit stage is a router
between disciplines. A ledger with no gates and a commit stage is the honesty
test switched off, and the engine should refuse to load it in those words.

---

## 4. How a ledger names its terminal stage

### The recommendation

A `roles:` block inside `contract:`, which is already the place this file
declares its interface.

```yaml
contract:
  roles:
    entry_stage:     stage_0_admissibility
    commit_stages:   [stage_9_method_selector]   # zero or more. Must be written.
    gate_sweep_node: S9_GATE_SWEEP               # optional; required if commit_stages is non-empty
    no_proposal:     UNSET                       # the sentinel meaning "nothing proposed yet"
```

and the role that `TRAIN__` was secretly playing moves onto the prefix that plays
it:

```yaml
contract:
  outcome_prefixes:
    TRAIN__: {verdict: TRAIN, terminal: true,
              gated: all,                        # every gate in required_gates, under this proposal's class
              mintable_only_at: S9_MINT_TRAIN_VERDICT,
              meaning: "train this"}
```

`STAGE_9`, `ENTRY_STAGE`, the literal `"TRAIN__"` and the literal `"UNSET"` all
disappear from Python. SC1 becomes domain-general in one line: *for the single
prefix declared `gated: all`, exactly the node named in `mintable_only_at` may
emit it.*

Note the name. It is **not** `terminal_stage`. **Every** stage in the ML ledger
is terminal; counted out of the loaded spec, all ten of them end at least one
outcome and `stage_8_classical` ends twelve:

```
  stage_8_classical                12        stage_9_method_selector           5
  stage_3_knowledge                10        stage_0_admissibility             4
  stage_7_efficiency                7        stage_1_baseline                  4
  stage_5_behaviour                 6        stage_6_capability                4
  stage_4_format                    5        stage_8_offtheshelf_first         1
```

So "terminal stage" names nothing. The stage the engine needs to find is the one
where a *candidate becomes a verdict*, which is what `SC2` has always been
guarding: *"a proposal is a candidate, not an answer."* Naming it `commit_stages`
makes the check readable in the error message, and an error the author can act on
is [§7](#7-should-the-engine-validate-against-a-declared-schema)'s point.

### Two terminal stages

`commit_stages` is a list, so two is structural rather than special. What the
list does **not** solve, and what will actually bite at six ledgers, is that
`required_gates` is a single flat list applied to everything. A data ledger with
both `SYNTHESISE__` and `RELABEL__` will want different gates for each — inventing
rows and paying humans are not the same risk.

So the grammar admits it now and the engine refuses it until it is built:

- `gated: all` — every gate in `contract.required_gates`. Implemented.
- `gated: [G0_…, G2_…]` — a subset. **Parsed, and refused at load time** with
  *"per-prefix gate sets are declared but not implemented; this engine supports
  `gated: all`"*.

That is JSON Schema's `$vocabulary` discipline applied to our own format: a key
you do not understand is a refusal, never a shrug. The alternative — accept the
list and ignore it — would mean an author could write a narrower gate set,
believe it, and get the full one. Or worse, the reverse.

### No terminal stage

`commit_stages: []`, written out. Then the engine refuses any `propose:` and any
`gated:` prefix, with a message that says the ledger declared itself
non-committing. This is a real ledger, not a degenerate one: a triage ledger that
only ever routes into another discipline has no irreversible outcome of its own,
and the five gates protect nothing there. It does not weaken the honesty test —
it declares that it has nothing for the test to protect — and it says so out
loud, where a reviewer sees it in a diff.

**A missing `commit_stages` key is an error, not an empty default.** See §3.

### Rejected

- **Keep the constant, pick a nicer conventional name** (`stage_commit`,
  `stage_final`). Rejected: convention is a hardcoded name with better public
  relations. It fails identically for the second author, and it fails silently
  for the third, who names their stage something sensible and gets *"spec has no
  stage_commit"* with no hint that a rename would fix it. Every system in §2
  abandoned convention for declaration.
- **A per-stage `role: commit` key.** This is the CRD `storage: true` shape and
  it has one genuine advantage: the declaration sits where the author is
  writing. Rejected on two counts. Answering *"which stage commits?"* becomes a
  scan of 3,468 lines rather than a read of one block, and a stage is a
  several-hundred-line object whose head is nowhere near its tail. The good idea
  in it is kept: the error message must name the declaration site, which
  [§7](#7-should-the-engine-validate-against-a-declared-schema) makes mandatory.
- **Infer it** — the commit stage is the one containing the minting node.
  Rejected hardest. Inference is how you get a confidently wrong answer when
  there are two candidates, and this engine's whole character is refusing rather
  than guessing. `Spec.declared_outcomes()` already learned this and wrote it
  down: *"THE LIST COMES OUT OF THE FILE, ALWAYS."*
- **An annotation on the stage, OPA-style** (`# ROLE: commit` in a comment).
  Rejected: comments are not data in YAML, and a format whose semantics live in
  comments cannot be validated. OPA can do this because Rego's parser reads
  annotations into the AST; PyYAML discards them.

---

## 5. The schema for a router node

### The problem, stated precisely

Today a router is a `routes:` mapping *plus* a Python function keyed by node id.
The author of ledger two cannot supply the second half. The error they get is:

```
SpecError: node S9_ROUTE routes by a key the engine has no rule for
```

which names no key, no rule, and no remedy. And when they write the ladder as
prose instead — which is how `S9_HARDWARE_ROUTER` is written in the ML ledger,
so it is a reasonable thing to copy — they get:

```
SpecError: node S9_ROUTE describes routes in prose and has no handler
```

Both messages are true and neither is actionable.

### The recommendation

```yaml
- node: S0_MODALITY_FORK
  condition: always
  router:
    branch_on: modality            # a declared fact
    select:    value               # a member of the engine's closed selector vocabulary
    routes:
      tabular:    stage_8_classical
      timeseries: stage_8_classical
      text:       stage_1_baseline
    no_match:                      # REQUIRED. What happens when nothing matches.
      outcome: ACTION__NAME_THE_MODALITY
```

```yaml
- node: S1_ROUTE_BY_FAILURE_MODE
  condition: always
  router:
    branch_on: failure_histogram
    select:    argmax              # the key with the largest count; ties resolve in YAML order
    routes:
      wrong_facts:  stage_3_knowledge
      wrong_format: stage_4_format
    no_match:
      outcome: ACTION__CLASSIFY_FAILURES
```

Four keys, all four required, and the engine can say what each one is for when it
is missing. The design has three parts and each is load-bearing.

**`select:` is a closed vocabulary owned by the engine.** `value` and `argmax`
today; adding a third is an engine change with a test, exactly as it should be.
This is DMN's hit policy, and the reason to copy DMN here is that DMN has been
letting non-programmers write decision tables for a decade: an author picks
`UNIQUE` or `FIRST` from a list and never writes hit-policy code. The strategy is
the machine's, the table is the domain's, and that is §3's rule with a concrete
name on it.

**`no_match:` is required, not optional.** The author's own ledger already records
why, in `uninspectable_facts.one_known_gap`: *the router raises if the histogram
carries only keys the router has no route for.* A router that can be reached with
an unroutable value and has not said what to do is a run that dies with an
`EngineError` in front of a user. Making the key required converts a latent crash
into a question the author must answer while writing — which is the cheapest
possible moment.

**`router:` is a nested block, and `route:` gets renamed.** Today `route:` (one
stage name) and `routes:` (a table) differ by one character and mean unrelated
things. The author of ledger two confused them, and the confusion is in the file
on disk:

```yaml
  routes:
  - &id001
    when: tool_count > 0
    propose: agent_with_tools
  - when: otherwise
    propose: a_script
  route: *id001                    # a `route` that is a mapping, not a stage
```

One character of distance between two keys with different types is a design
defect, not an author error. Recommend `goto:` for the single-target jump and
`router:` for the table. No two keys in the format may be within one character of
each other.

### The thing that made this concrete, and it is worth the paragraph

The first draft of this schema used `on:` for the branch fact. Running the
prototype produced:

```
SpecError: node S0_ROUTE_BY_REPRODUCIBILITY: router is missing `on`.
```

which was false — `on:` was right there. PyYAML implements YAML 1.1, where `on`
is a **boolean**:

```
keys of router: [True, 'select', 'routes', 'no_match']
```

The key name had been silently converted to `True`. This document's own proposed
schema was broken by the hazard [§9](#9-is-yaml-still-right-at-six-ledgers)
argues about, in the first ten minutes of using it. `branch_on:` is the fix, and
the incident is the evidence for the strict loader.

### Rejected

- **A `when:`-list router** (`routes: [{when: <condition>, goto: <stage>}, …]`,
  first match wins). Genuinely tempting: it is more expressive than `select:`, it
  needs no closed vocabulary, and the condition compiler already exists. Rejected
  because it is *too* expressive — it collapses the distinction between a router
  and an ordinary stage, which is a sequence of conditions with the first match
  winning. If routers can carry arbitrary conditions, `condition: always` stops
  meaning anything, and the `shadowing_rule` — the file's own hardest-won lesson,
  which cost it seven dead outcomes across two incidents — would need re-deriving
  for a second construct. Keep routers total and dumb; put conditions in nodes.
- **Registering handlers by name from the ledger** (`handler: modality_fork`).
  Rejected: it renames the private list rather than removing it, and the second
  author still cannot write a router the engine has not already anticipated.
- **Letting `routes:` values be node ids as well as stage ids.** Rejected: the
  walk resumes at a *stage*; a router that could land mid-stage would make
  `skip_leading_gates` ambiguous, and gate-skipping ambiguity is precisely the
  class of bug the `row`-per-gate machinery exists to prevent.
- **Keeping the bare `routes:` mapping and adding the metadata beside it.**
  Rejected: it leaves `routes:` meaning two different things depending on whether
  it is a list or a mapping, which is the ambiguity that produced the useless
  "describes routes in prose" message.

---

## 6. What happens to `derived.route`

`_collect_literals` reads `raw["derived"]["route"]` and scrapes capitalised words
out of it to decide which bare words a condition may use as values. That is why a
missing key is a `KeyError` and not a message.

Recommendation: **delete the special case.** A router's verdict vocabulary should
come from the router that produces it, or from a fact's own `enum:`. `derived:`
becomes an ordinary optional block. The ML ledger keeps its `derived.route`
entry as documentation; nothing reads it blind.

This is the smallest item here and it is listed separately because it is the only
one of the four current blockers that is a plain bug rather than a design
question, and it should not be smuggled into a design change.

---

## 7. Should the engine validate against a declared schema

### Short answer

Yes for shape and references, **never** for the invariants — and the reason to do
the first two is not tidiness. It is that SC1's hardcoded `TRAIN__` survived
inside 64 look-alike checks for the whole life of this file.

### The three tiers

The names come from Drools' `DMNValidator`, which splits validation into
`VALIDATE_SCHEMA`, `VALIDATE_MODEL` and `VALIDATE_COMPILATION` for the same
reason: a failure should say which *kind* of wrong it is.

**Tier 1 — SHAPE.** Does the document have the right blocks, keys and types? Data
driven, from one table:

```python
BLOCK = {
    "contract": Required(mapping, keys={
        "roles":            Required(mapping, why="the names the engine must find"),
        "required_gates":   Required(list_of(gate_id)),
        "outcome_prefixes": Required(mapping),
        ...
    }),
    "escalation_ladder": Optional(mapping, why="documentation; nothing reads it"),
    ...
}
```

The `why=` is not decoration. It is what the error message prints, and it is the
difference between *"spec is missing top-level key 'derived'"* and *"`derived:`
declares values the engine computes rather than reads; a ledger with none may
write `derived: {}`"*.

**Tier 2 — REFERENCES.** Does every id resolve? Node → stage, `gate_ref` → gates,
`propose` → methods, outcome → a declared prefix, `branch_on` → facts,
`mintable_only_at` → a node. Driven by a declaration of *which fields are
references to what*, never by a hand-written list of the fields. The engine
already knows why: `_facts_read_by` says *"THE ONE THING THAT MUST NOT HAPPEN
HERE IS A HAND-WRITTEN LIST… a fact somebody adds to a gate row next year has to
be covered on the day it is added."* A reference field added in 2027 must be
checked in 2027.

This tier is CEL's middle phase, and the analogy is exact. CEL parses, then
**checks against a declared environment**, then evaluates; control planes do the
first two at config time and store the AST. `_check_names` + `compile_condition`
is already precisely that, and it is the best-designed part of the current
validator. Tier 2 is generalising what `_check_names` does for conditions to
everything else in the file that is a name.

**Tier 3 — INVARIANTS.** SC1 through SC5, reachability, shadowing, gate-row/class
coverage, "no node the walker would silently skip". **These stay Python, and they
stay Python on purpose.**

Here is the line, and it should be quotable:

> **A schema can say "this key must be a string". It cannot say "exactly one node
> may mint the irreversible verdict."**

Every part of the five-gate honesty test lives in tier 3. Moving it into a
declarative rule language would be handing an author the ability to write a
ledger that declares itself exempt, and no amount of care about the rule language
would fix that, because the exemption would be *in the ledger* — the document the
author controls. Kubernetes drew the same line for the same reason: structural
schemas handle shape, but the checks that must not be locally overridable live in
the API machinery, and `ValidatingAdmissionPolicy` deliberately keeps
`failurePolicy: Fail` available so an evaluation error is a rejection.

### What tier 3 gains from tiers 1 and 2

Today `_static_checks` is 57 lines containing SC1 and SC4 mixed with the shape
checks that reach `spec.node_index["S9_SIZE_TO_METHOD"]["table"]` by name. After
the split, tier 3 is a short file whose every check is a theorem about the graph,
parameterised by `contract.roles`. It becomes possible to read the list of
invariants and ask whether it is complete — which is impossible at 64 checks
deep, and is the actual reason `TRAIN__` hid there.

### Errors an author can act on

The engines in §2 all attach a location to a failure, and JSON Schema is the most
explicit: its output format carries `instanceLocation` and `keywordLocation` so
the report points at both the offending part of the document *and* the rule that
objected.

Recommendation: a `LedgerError` carrying `(document_path, line, expected, found,
remedy, check_id)`. Illustrative rendering — this exact error does not exist yet,
the shape is the proposal:

```
docs/ledgers/ai_engineering.yaml:573  [LF014]
  stage_9_method_selector[0] "S9_ROUTE": router is missing `no_match`.
  expected: what to do when `branch_on: tool_count` has a value no route covers
  remedy:   add `no_match: {outcome: <an ACTION__ outcome>}` or `no_match: {goto: <stage>}`
```

**Line numbers are available with no new dependency.** Measured:

```
$ python -c "... yaml.compose(open(path)) ..."
   contract                   declared at line 40
   gates                      declared at line 539
   stage_9_method_selector    declared at line 572
```

`yaml.compose()` returns a node graph carrying `start_mark`, so the loader can
keep a path→line index beside the parsed dict.

**`check_id` is not bureaucracy.** It is what lets the conformance suite
([§8.4](#84-a-conformance-suite-is-the-thing-that-makes-this-an-interface)) assert
on a stable identifier while the message text keeps improving. Regal names its
Rego lint rules; DMN validation messages carry ids; the reason is the same.

### Rejected

- **Adopt JSON Schema and a `jsonschema` dependency.** Rejected on the standing
  invariant (no new dependency), and — more interestingly — it would not have
  bought much. The checks that actually matter here are the ones JSON Schema
  cannot express. What is worth stealing is its *output* discipline, and that is
  free.
- **Hand-write a JSON Schema meta-schema and a validator for it.** Rejected: that
  is implementing a spec instead of a validator, and the spec's hard parts
  (`$ref`, `$dynamicRef`, annotation collection) are irrelevant to a
  seven-block document.
- **Leave the 64 `_require` calls alone.** Rejected, and this is the one where the
  minimal fix is genuinely tempting — they work, they are tested, and the suite is
  green at 2,848. It is rejected because of what it costs at six ledgers: 64
  checks that read as one undifferentiated wall is how the ML leak got in, and six
  ledgers means six authors who will each meet that wall as an error message with
  no location and no remedy.
- **Generate the validator from the ML ledger.** Rejected: it would encode the
  first ledger's accidents as the format.

---

## 8. Ledger format versions

### What exists

```
$ grep -rn 'raw\["version"\]\|spec\.raw\["version"\]' --include=*.py app/ tests/
app/diagnosis.py:634:    _require(isinstance(raw["version"], int), "version must be an integer")
tests/test_diagnosis_loader.py:37:        self.assertIsInstance(spec.raw["version"], int)

$ grep -n "^version:" docs/diagnosis_engine.yaml docs/ledgers/ai_engineering.yaml
docs/diagnosis_engine.yaml:179:version: 2
docs/ledgers/ai_engineering.yaml:39:version: 1
```

Two reads, both `isinstance(int)`. Two ledgers that disagree about the version.
No consequence either way. That is not a versioning scheme; it is a field.

### 8.1 Two different things are being versioned

Rename, because the current name invites the wrong reading:

- **`ledger_format:`** — an integer major owned by the *engine*. Which grammar
  this document is written in.
- **`ledger_version:`** — owned by the *author*. Which revision of their
  knowledge this is. The engine never reads it; it renders it, because a user
  reading a diagnosis should be able to see which edition of a domain's judgment
  produced it.

Confusing the two is how format versions end up unreadable: someone bumps
"version" because they added an outcome, and now the engine cannot tell an
author's edit from a grammar change.

### 8.2 The mechanism: refuse, or upgrade. Never guess.

```python
CURRENT_FORMAT   = 3
SUPPORTED_FORMATS = {2, 3}        # 2 is read by upgrading it to 3, then forgotten
UPGRADERS = {2: upgrade_2_to_3}
```

Load path: **parse → upgrade to `CURRENT_FORMAT` → validate against
`CURRENT_FORMAT` only → execute.**

That last clause is the whole design and it is stolen from Kubernetes CRDs, where
many versions are *served* but *"one and only one version must be marked as the
storage version"* and everything is converted to it. The engine's 64+ checks and
its walk never fork on version. Every older format is a pure data transform in
front of one validator. Terraform does the same for provider state:
*"Each StateUpgrader implementation is expected to wholly upgrade the resource
state from the prior version to the current version."*

A format the engine does not know is a **refusal**, in JSON Schema's words:
*"implementations that do not recognize the vocabulary MUST refuse to process any
schemas that declare this meta-schema."* The message names both numbers and what
to do, the way Terraform's does (*"This configuration does not support Terraform
version 1.4.6"*):

```
docs/ledgers/environments.yaml:1  [LF001]
  ledger_format: 5, and this engine reads 2 and 3.
  Either upgrade the harness, or write ledger_format: 3 and run
  `python -m app.ledger.check docs/ledgers/environments.yaml` to see what changed.
```

**Never** best-effort a newer format. A gate table half-understood is the honesty
test defeated by a shrug.

### 8.3 The compatibility contract, stated in the format's own document

Borrowing Confluent's vocabulary, because it is precise and widely understood:

- **The engine is BACKWARD_TRANSITIVE over ledger formats**, back to
  `CURRENT_FORMAT - 1` at minimum and further where an upgrader is cheap. A new
  engine reads every ledger it has an upgrader for.
- **The engine is not FORWARD compatible, deliberately.** An old engine given a
  newer format refuses.
- **An upgrader must be total and lossless for anything the engine reads.** It may
  drop nothing that a check or the walk consults. Prose it does not understand is
  carried through untouched — CRD's *"conversions need to be done in BOTH
  directions without losing information"*, applied one-way.

And the rollout, which is OPA's and is the part most schemes skip: **the new
grammar should be writable before it is required.** OPA shipped `import rego.v1`
so a policy could opt in per file, with `opa check --rego-v1` to test compliance
and `opa fmt --rego-v1` to do the edit, and only later flipped the default. The
equivalent here is that format 3 lands with an upgrader and a checker command
*before* format 2 stops being accepted, and the ML ledger's own conversion is a
reviewable diff rather than a flag day.

### 8.4 A conformance suite is the thing that makes this an interface

At one ledger the format is a habit. At six it is an interface, and an interface
without a conformance suite is a rumour.

Recommend `tests/ledgers/conformance/`: a corpus of tiny ledgers, each valid or
invalid for exactly one declared reason, each asserting on a **check id** rather
than a message string. This is JSON-Schema-Test-Suite's shape and it is why
independent JSON Schema implementations agree.

It also answers "what happens to a ledger somebody else wrote": their file is a
case in the suite, or it is not covered. That is a much better answer than a
promise.

### 8.5 An unknown key is an error, and this is where we part company with JSON Schema

JSON Schema says *"Unknown keywords SHOULD be treated as annotations, where the
value of the keyword is the value of the annotation."* That is right for a
format meant to be extended by strangers in flight. **It is wrong here**, and the
reason is in the engine's own docstring: *"a node the engine has no way to execute
is a load-time error, not a node that is silently ignored — silently-ignored
nodes are how four training outcomes came to be dead while the file claimed all
nine were gated."* A misspelled `gate_ref:` that becomes an annotation is that
defect with a new spelling.

So: **an unrecognised key at any level is a load error**, and it names the nearest
key it does recognise so a typo is one glance away —

```
docs/ledgers/environments.yaml:812  [LF031]
  node S4_REWARD_UNMEASURED: unknown key `outcomes`. Did you mean `outcome`?
```

with one escape hatch, borrowed from OPA's `custom` annotation (*"a mapping of
user-defined data… to arbitrarily typed values"*): keys prefixed `x_` are the
author's own and are carried through untouched. A declared place for undeclared
things is what stops people smuggling notes into keys the engine might one day
claim.

This is also the interaction with §8.2 that matters. Because unknown keys are
refused rather than annotated, a *newer* format's keys cannot be silently
tolerated by an *older* engine — the two rules reinforce each other, and neither
one leaves a hole for the other to cover.

---

## 9. Is YAML still right at six ledgers

**Commit: yes — and stop using all of it.** Keep YAML as the serialisation; move
to a *constrained* YAML loaded by a strict loader. The format that needs to
change is the schema, not the file extension.

### 9.1 The case against, measured

PyYAML 6.0.3 implements YAML 1.1. Measured against it:

```
enum_that_bites: [yes, no, on, off, y, n, true, false]
   -> [True, False, True, False, 'y', 'n', True, False]
country_code: no      -> False
version_like: 1.10    -> 1.1
a_time: 12:30         -> 750
```

An enum member spelled `no` becomes `False`, and `_collect_literals` would then
offer the bare word `False` as a literal a condition may use. A ledger about
countries, or about `on`/`off` states, or a version string, is a live hazard
today.

```
dup_key: 1
dup_key: 2            -> {'dup_key': 2}     (silently; last wins)
```

In a 3,468-line hand-written file holding 79 outcomes, a duplicated node key is a
**silently deleted node** — the exact failure class the module header says the
loader exists to prevent: *"silently-ignored nodes are how four training outcomes
came to be dead while the file claimed all nine were gated."*

And the expressive power gets used by accident. The second ledger, hand-written
this morning, contains a YAML anchor and an alias, which is how its `route:`
came to be a mapping instead of a stage name (§5).

Add to that the incident in §5, where `on:` as a key in this document's own
proposed schema silently became `True`.

### 9.2 The case for, which is stronger than it looks

The ML ledger is 3,468 lines and a large fraction of it is **argument** —
`shadowing_rule`, `what_the_gates_decide`, `why_unattributed_is_asserted`, the
paragraph explaining why `UNSET` is provisional rather than strict. That prose is
not commentary on the knowledge; in a product whose thesis is judgment, it *is*
part of the knowledge, and it is what makes the file reviewable. A format that
cannot hold comments and folded block scalars would delete the reason this
project works.

It also has to survive code review. A ledger must be diffable line by line in a
pull request, because that is how the argument in it gets checked by a second
person.

### 9.3 The strict loader, measured

Three hazards, all closed with ~30 lines against PyYAML's public API and **no new
dependency**:

```
--- PyYAML SafeLoader as shipped ---
  {'enum_with_norway': [True, False, True, False], 'dup_key': 2, ...}
--- strict loader ---
  norway + on/off  -> {'e': ['yes', 'no', 'on', 'off']}
  duplicate key    -> REFUSED at line 2: duplicate key 'dup' (first defined at line 1)
  alias            -> REFUSED at line 2: a ledger may not use YAML aliases (*x); write the value out
```

1. **Drop the YAML-1.1 boolean resolver** for everything but `true`/`false`, via
   `add_implicit_resolver` and a filtered `yaml_implicit_resolvers` — this is YAML
   1.2's behaviour, which exists precisely because *"boolean is narrowed to
   exactly `true` and `false`"*.
2. **Duplicate keys are an error**, via a `construct_mapping` override, and the
   error carries both line numbers.
3. **Anchors and aliases are refused**, via a `compose_node` override.

Plus the `yaml.compose()` line index from §7, which the loader needs anyway.

### 9.4 Rejected

- **JSON.** No comments. Deletes §9.2 outright. Rejected in one line.
- **TOML** (`tomllib`, stdlib since 3.11 — genuinely no new dependency; duplicate
  keys are an error *by specification*; no implicit booleans; no anchors).
  Rejected on ergonomics, not on principle: a 79-outcome decision tree in
  arrays-of-tables is far less readable than nested sequences, and multi-line
  prose is awkward where prose is half the value. It is the strongest runner-up
  and the reason it loses is worth stating plainly — the file is read by humans
  more often than by the engine.
- **CUE, KCL, Dhall, Jsonnet, Starlark.** All bring a real schema story — CUE's
  pitch is exactly ours: *"the majority of problems with traditional
  configuration languages can be traced back to a lack of a schema
  specification"*, and its schemas are written in CUE itself. Rejected on two
  counts. Each is a new dependency, against the standing invariant. And each
  brings an *evaluator* — the file stops being a document and becomes a program
  that computes a document. For the one file in this repository whose entire job
  is to be exactly what its author wrote, and whose conditions are executed
  verbatim on purpose, that is a new class of defect: a ledger that computes
  something slightly different from what it appears to say. The module header
  already refuses a weaker version of this argument about the parser; it applies
  with more force to the language.
- **A database.** Rejected: not diffable, not reviewable, and the argument in the
  file would not survive the migration.
- **Splitting one ledger across many files.** Not rejected — *deferred*, because
  it is orthogonal to the format question and should be decided when a ledger's
  size demands it, not now. When it comes, the seam is per-stage files with the
  `contract:` block staying whole, because the contract is the interface.

---

## 10. The proof that this runs

A prototype in the scratchpad — **not product code, not committed** — monkeypatched
`app.diagnosis` in-process to implement the recommendation: roles-driven entry and
commit stages, prefix-driven mint, and routers executed from a declared
`router:` block rather than from `ROUTE_KEYS` keyed by node id.

### Claim A — the migration is behaviour-preserving on the ML ledger

`upgrade_2_to_3()` is a pure data transform: it adds `contract.roles`, adds
`gated: all` + `mintable_only_at` to the `TRAIN__` prefix, and rewrites the two
existing routers into declared `router:` blocks. No prose changed, no condition
changed, nothing deleted.

Both engines were then run over the repository's own fixtures —
`tests/diagnosis_fixtures.MINTING`, `SPREAD` and `REACHING`, plus six hand-written
fact sets:

```
  identical answers      : 78 of 78
  of which real verdicts  : 49
  of which identical errors: 29 (fixture rows that carry an `outcome` key,
                                 rejected the same way by both engines)
```

All nine `TRAIN__` mints, both forks through the routers, the gate sweep, the
struck-method path and the unsubstantiated-fact refusal — every one identical.
The 29 errors are a fixture artifact (those rows carry an `outcome` key that
`validate_facts` rejects as an undeclared fact); both engines reject them
identically, so they are reported separately rather than counted as verdicts.

### Claim B — a second ledger runs with no Python of its own

The AI-engineering ledger was rewritten into the format-3 shape — `contract.roles`,
a `BUILD__` prefix declared `gated: all`, gates placed in stages with `gate_ref:`,
and one router it declares itself. Its `facts` / `fact_origins` / `fact_scopes`
blocks were reused verbatim from the author's file.

```
SECOND LEDGER LOADED.
  stages          : ['stage_0_admissibility', 'stage_0_flaky', 'stage_1_simplest', 'stage_9_shape_selector']
  required_gates  : ['G0_SOMETHING_TO_MEASURE', 'G1_SIMPLE_VERSION_TRIED']

  nothing measured yet                             -> BLOCKED__NOTHING_TO_MEASURE_AGAINST    BLOCKED
  4 failures only                                  -> BLOCKED__NOTHING_TO_MEASURE_AGAINST    BLOCKED
  40 failures, does not reproduce                  -> ACTION__MAKE_IT_REPRODUCE              BLOCKED
  40 failures, reproduces, simple untried          -> NO_AGENT__ONE_API_CALL                 NO_BUILD
  40 failures, reproduces, simple tried, no tools  -> BUILD__a_script                        BUILD
  40 failures, reproduces, simple tried, 3 tools   -> BUILD__agent_with_tools                BUILD
  a MODEL merely claims the failure count          -> ACTION__SUBSTANTIATE_CLAIMED_FACTS     BLOCKED
```

An honest refusal, two gated builds, a router the ledger wrote itself, and — the
last row — **the origin policy holding across domains**: a model that merely
*claims* the failure count cannot open a gate whose fact the ledger declares
`source: inspect`, in a ledger the origin machinery has never seen.

No repository file was modified for any of this: the probes and the prototype
live in a scratch directory, the patched ledgers in temp files, and the only file
this lane adds to the repository is this document. The suite was run from the
repository root before the work started and again after this document was
written:

```
$ python -m unittest discover -s tests -t tests      # before
Ran 2848 tests in 343.544s
OK (expected failures=4)

$ python -m unittest discover -s tests -t tests      # after this document was written
Ran 2848 tests in 373.755s
OK (expected failures=4)
```

---

## 11. The migration path

Ordered so that each step is independently reviewable and the suite is the gate
at every one.

**Step 0 — the strict loader.** `app/ledger/loader.py`: duplicate keys, YAML-1.1
booleans, aliases, and the `compose()` line index. Both ledgers must load
unchanged through it. Non-vacuous check: introduce a duplicate key into a scratch
copy and confirm the new test fails.

**Step 1 — `derived.route` stops being read blind.** The one plain bug (§6). One
line, its own commit, so it is not smuggled into a design change.

**Step 2 — `contract.roles`, and `ledger_format: 3`.** Add the block to the ML
ledger; delete `STAGE_9`, `ENTRY_STAGE`, `"UNSET"` and `"TRAIN__"` from the
engine; add `gated:` and `mintable_only_at:` to `outcome_prefixes`. This is the
step Claim A measured, and its gate is that the fixture answers do not move.
Where a test asserts the old constant, **rewrite it to the new behaviour** — a
test that says the terminal stage must be called `stage_9_method_selector` is
asserting the defect.

**Step 3 — the router schema.** `router:` with `branch_on` / `select` / `routes` /
`no_match`; `route:` → `goto:`; the two ML routers converted; `ROUTE_KEYS`
deleted. The gate is Claim A again plus a conformance case per selector and per
missing key.

**Step 4 — the validator split.** Tier 1 and tier 2 become tables; tier 3 becomes
a short file of graph theorems parameterised by `contract.roles`. `LedgerError`
with location, remedy and check id. The gate is that the 64 checks are all still
enforced — every one gets a conformance case that fails without it.

**Step 5 — the conformance suite**, grown alongside step 4 rather than after it.

**Step 6 — the second ledger for real**, written by someone who has not read
`app/diagnosis.py`. That is the actual acceptance test for all of the above, and
it is the Phase 0a "done" condition in `docs/PHASES.md`.

**Not in this path, deliberately:** the remaining `ACTION_HANDLERS` and
`CONDITION_HANDLERS` for `S9_SIZE_TO_METHOD`, `S9_HARDWARE_ROUTER`,
`S9_DATA_INSUFFICIENT` and the rest. Those are genuinely ML-specific *computations*,
not naming. They should become a declared extension point later — a ledger
naming a capability the engine implements — but attempting it in the same pass as
the naming work would mix a boundary question with a plug-in-architecture
question, and the plug-in question needs its own research.

---

## 12. What this does not fix

Stated with its number, because §1.2 is a demonstration of what happens when a
blocker list is written from memory.

**26 `default_spec()` call sites across 11 modules outside the engine, and 12
distinct ML ledger ids named across six of those modules.**
`app/tools/propose.py` asks for `G0_EVAL_SET`;
`app/tools/classical.py` asks for `S8_TABULAR_STANDARD`; `app/tools/evals.py`
asks for `S1_ROUTE_BY_FAILURE_MODE`. Every one of them loads the ML ledger by
`SPEC_PATH` regardless of which ledger the thread is actually running.

Nothing in this document changes that. A second ledger will diagnose correctly
and then hand its verdict to a tool layer that is still reading the first
ledger's file. The shape of the answer is probably a per-thread ledger handle
replacing the module-level `default_spec()`, and a declared capability name
replacing the hardcoded ids — but that is a second piece of research, and
claiming it here would be the same error as the header comment that started this.

**Re-counted 2026-08-24, by AST rather than grep, excluding `app/diagnosis.py`:
25 executable `default_spec()` calls in 11 modules, plus 5 `evidence.spec()`
calls in 3 more.** The 26/11 above was a grep count and it undercounted the
MODULES because `app/asking.py`, `app/build.py`, `app/provenance.py` and
`app/tools/blocks.py` reach the ledger through `evidence.spec()`,
`evidence.resolves()` and `evidence.declared_fact()` without the string
`default_spec` appearing near them. Still open. `docs/PHASES.md` carries it under
Debts with the module list.

**One half of the "declared capability name" did land, and it is worth naming
here because it is a new closed block in `contract:`.**
`contract.capabilities` — read by `app/tools/blocks.py`, refused key by key
against a vocabulary the ENGINE publishes, holding `core`, `needs` (keyed by this
ledger's own stage ids) and `builds` (keyed by outcome id). It names PACKS, never
tools: a ledger's author may not name `carve_eval_set`, which is a Python
function in a package they have never read. §3's rule applies to it in full and
is enforced rather than asked for — **a ledger that declares the block must name
every stage it has, with `[]` where the stage's work needs nothing extra**,
because "needs nothing" and "somebody forgot" are different and the difference
was measured to be worth 15 of 40 tools. Both shipped ledgers declare it. It does
NOT replace the hardcoded NODE ids in `app/tools/`, which is the other half and
is still open.

---

## 13. Sources

- [Open Policy Agent — Policy Language: metadata annotations](https://www.openpolicyagent.org/docs/policy-language) — the `entrypoint` annotation, `schemas` annotations, `custom` annotations and scope precedence.
- [Open Policy Agent — Upgrading to v1.0](https://www.openpolicyagent.org/docs/v0-upgrade) and [OPA 1.0 is coming](https://blog.openpolicyagent.org/opa-1-0-is-coming-heres-what-you-need-to-know-c8fb0d258368) — `import rego.v1`, `opa check --rego-v1`, `opa fmt --rego-v1`, `--v0-compatible`.
- [Open Policy Agent — Rego Style Guide](https://www.openpolicyagent.org/docs/style-guide).
- [OMG — Decision Model and Notation 1.5](https://www.omg.org/spec/DMN/1.5/About-DMN) and [Trisotech — Using Decision Services](https://www.trisotech.com/using-decision-services/) — `outputDecisions` versus `encapsulatedDecisions`.
- [Drools — Decision Model and Notation](https://docs.drools.org/latest/drools-docs/drools/DMN/index.html) and [`DMNValidator`](https://github.com/kiegroup/drools/blob/main/kie-dmn/kie-dmn-validation/src/main/java/org/kie/dmn/validation/DMNValidator.java) — `VALIDATE_SCHEMA` / `VALIDATE_MODEL` / `VALIDATE_COMPILATION`, and decision-table hit policies.
- [JSON Schema 2020-12 core](https://json-schema.org/draft/2020-12/json-schema-core) — `$schema` as dialect identifier, `$vocabulary` and the MUST-refuse rule, unknown keywords as annotations.
- [JSON Schema — Interpreting output](https://json-schema.org/blog/posts/interpreting-output) and [Fixing JSON Schema output](https://json-schema.org/blog/posts/fixing-json-schema-output) — `instanceLocation`, `keywordLocation`, and the flag/basic/detailed/verbose formats.
- [CEL — overview](https://cel.dev/overview/cel-overview) and [cel-go](https://github.com/google/cel-go) — parse, check against a declared environment, evaluate; control planes check at config time.
- [Kubernetes — Versions in CustomResourceDefinitions](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definition-versioning/) — many served, one stored, conversion webhooks, lossless round-tripping.
- [Kubernetes — Validating Admission Policy](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/) — CEL `validations`, `message` / `messageExpression`, `reason`, `failurePolicy`.
- [Terraform — State upgrade (Plugin Framework)](https://developer.hashicorp.com/terraform/plugin/framework/resources/state-upgrade) and [terraform-plugin-sdk `helper/schema`](https://pkg.go.dev/github.com/hashicorp/terraform-plugin-sdk/v2/helper/schema) — `SchemaVersion`, `StateUpgraders`.
- [Terraform — plugin protocol](https://github.com/hashicorp/terraform/blob/main/docs/plugin-protocol/README.md) — major-version negotiation in the handshake.
- [Confluent — Schema Evolution and Compatibility Types](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html) — BACKWARD / FORWARD / FULL / TRANSITIVE.
- [Python Packaging — Entry points specification](https://packaging.python.org/specifications/entry-points/) and [Creating and discovering plugins](https://packaging.python.org/guides/creating-and-discovering-plugins/) — declared names discovered by group, never hardcoded.
- [CUE](https://appliedgo.net/spotlight/cue/) — schema-as-the-language, and the diagnosis that configuration problems trace back to a missing schema.
- The YAML 1.1 hazards ("the Norway problem" and the wider family of implicit type coercions) are widely written up; every claim about them in §9 was re-measured against the PyYAML 6.0.3 actually installed here rather than cited.
