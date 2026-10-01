/**
 * The build, read off the wire — `app/build.py` `Build.as_dict()`.
 *
 * ══ THE ONE PROPERTY THIS FILE EXISTS TO CARRY ACROSS THE WIRE ═════════════
 *
 * `docs/THE_PROPOSAL_LOOP.md`: **the proposal is the same object the executor
 * consumes.** Not prose a second system re-derives into steps. So there is no
 * "diagram model" in this codebase and there is not going to be one: the
 * diagram reads `Build.steps` for its nodes and `Build.edges` for its lines,
 * keyed by the same `Step.id` the executor reports state under. A node that
 * changes colour during a storm is that step changing state, because it is
 * that step.
 *
 * The mirror of `lib/engine/facts.ts`, and the same discipline: every type is
 * transcribed from the engine, nothing is widened, and a payload that does not
 * satisfy the contract comes back `null` rather than half-read. `app/build.py`
 * refuses to construct an invalid build so that "a build that cannot be
 * validated must never be shown to a user as a plan" is a property of the type.
 * This file is the other end of that promise: a build that does not READ
 * cleanly is not drawn as a plan either.
 *
 * ══ A COST CANNOT BE RENDERED WITHOUT ITS ORIGIN ═══════════════════════════
 *
 * The instruction for this surface is that a cost with no provenance must be
 * *impossible to render*, not merely discouraged. `app/build.py` makes it
 * impossible to CONSTRUCT — no constructor there accepts a bare magnitude.
 * TypeScript cannot stop a renderer from printing `payload.cost.wall_clock`,
 * but it can stop one from reaching a magnitude without first saying which
 * provenance it is looking at, and that is what `Estimate` below does:
 *
 *   - it is a discriminated union on `provenance`, and
 *   - **the UNKNOWN arm has no `value` field at all.**
 *
 * So `estimate.value` does not type-check until the code has narrowed on the
 * provenance, and every narrowing branch has the provenance in hand at the
 * point where it prints the number. A number and its origin cannot be
 * separated by an accident.
 *
 * `readEstimate` then refuses, rather than repairs:
 *
 *   - MEASURED with no `reading` — the badge would be the only measurement in
 *     the room. `app/build.py` raises `CostError` on exactly this.
 *   - UNKNOWN carrying a number — if there is a number it came from somewhere,
 *     and that somewhere is its provenance.
 *   - UNKNOWN with no `find_out_by` — "I do not know how long this takes, let
 *     me run it on 1% and find out" is worth more than a guess; "I do not
 *     know" alone is where a proposal stops being useful.
 *   - a provenance word this file has never seen, a non-finite magnitude, a
 *     unit that does not match the dimension.
 *
 * Any one of those makes the whole build unreadable, which makes it render as
 * an ordinary tool result instead of as a plan. That is deliberate and it is
 * the same call `readDiagnosis` makes about a gate ledger with a missing row:
 * a plan with an unvouched number in it is worse than no plan, because a
 * proposal is the surface a person says yes on.
 */

/* ── The vocabulary, from app/build.py ───────────────────────────────────── */

/** `PROVENANCES`. Three arms, and INFERRED is the one the spec adds. */
export type CostProvenance = 'MEASURED' | 'INFERRED' | 'UNKNOWN';

/** `COST_DIMENSIONS`. All four, always: a dimension left out reads as free. */
export const COST_DIMENSIONS = [
  'model_tokens',
  'model_requests',
  'wall_clock',
  'disk',
] as const;

export type CostDimension = (typeof COST_DIMENSIONS)[number];

/** `DIMENSIONS` — dimension to unit. The engine sends the unit; this is what it
 *  is checked against, so a `wall_clock` estimate labelled `bytes` is refused
 *  rather than printed. */
const UNIT_OF: Record<CostDimension, string> = {
  model_tokens: 'tokens',
  model_requests: 'requests',
  wall_clock: 'seconds',
  disk: 'bytes',
};

/** What a person reads instead of the engine's field name. The engine's own
 *  name is shown beside it in mono, because that is the name in the tool
 *  schema and the one that makes this checkable. */
export const DIMENSION_LABEL: Record<CostDimension, string> = {
  model_tokens: 'Your model’s tokens',
  model_requests: 'Requests to your model',
  wall_clock: 'Wall-clock time',
  disk: 'Disk',
};

/** `STEP_STATES` — docs/DESIGN_SYSTEM.md §2.5, which is the single statement of
 *  it. Identical to `RunStatus` in `types.ts` by construction, and a test in
 *  this file's own module keeps them that way: the diagram and the run rail
 *  must not be able to pick different words for the same node. */
export const STEP_STATES = [
  'queued',
  'preflight',
  'running',
  'waiting_input',
  'waiting_approval',
  'stalled',
  'done',
  'failed',
  'cancelled',
] as const;

export type StepState = (typeof STEP_STATES)[number];

/* ── Readings and estimates ──────────────────────────────────────────────── */

/** A magnitude that was READ, and what it was read off. `Reading.as_dict()`. */
export interface Reading {
  dimension: string;
  value: number;
  unit: string;
  /** "stat() reported 41232 bytes for eval.jsonl". Shown verbatim. */
  how: string;
  at: string;
}

/**
 * One number in a proposal, or the honest absence of one.
 *
 * Read the header before adding an arm. The UNKNOWN arm carrying no `value`
 * is not an omission — it is the whole mechanism.
 */
export type Estimate =
  | {
      provenance: 'MEASURED';
      dimension: CostDimension;
      unit: string;
      value: number;
      /** The reading's own sentence. */
      how: string;
      reading: Reading;
      from: Estimate[];
    }
  | {
      provenance: 'INFERRED';
      dimension: CostDimension;
      unit: string;
      value: number;
      /** The derivation, shown — the spec requires an inference to show it. */
      how: string;
      reading: Reading | null;
      from: Estimate[];
    }
  | {
      provenance: 'UNKNOWN';
      dimension: CostDimension;
      unit: string;
      /** Why it is not known. */
      how: string;
      /** How it could be found out. Required by the engine and by this reader:
       *  "run it on 1% and read the seconds it reports". */
      findOutBy: string;
      from: Estimate[];
    };

export type Cost = Record<CostDimension, Estimate>;

/* ── The rest of a build ─────────────────────────────────────────────────── */

export interface Output {
  name: string;
  type: string;
  description: string;
  /** The dotted path inside the tool's own result. */
  at: string;
}

/** An argument that is an earlier step's output — `Ref.as_dict()`. This is what
 *  makes a dependency checkable rather than asserted, and the diagram draws the
 *  two differently for that reason. */
export interface Ref {
  step: string;
  output: string;
}

export interface ExitCriterion {
  /** The sentence a person reads before saying yes. */
  stated: string;
  /** Which observation the executor makes: tool_result, diagnosis, outputs. */
  source: string;
  subject: string;
  comparator: string;
  value: unknown;
}

export interface Risk {
  what: string;
  what_we_do: string;
}

export interface Question {
  ask: string;
  why: string;
  fact: string;
  answered_by: string;
}

export interface DataSnapshot {
  path: string;
  bytes: number;
  modified_at: string;
  how: string;
}

export interface Environment {
  name: string;
  working_dir: string;
  /** False means this sandbox cannot reach the network, whatever the model
   *  says. True must carry a reason, and the engine refuses one without. */
  egress: boolean;
  egress_reason: string;
  data: DataSnapshot[];
  installs: string[];
  python: string;
}

export interface Step {
  /** The node id in the diagram AND the key the executor reports state under.
   *  One id, because they are one object. */
  id: string;
  tool: string;
  why: string;
  arguments: Record<string, unknown>;
  produces: Output[];
  needs: string[];
  cost: Cost;
  exitCriterion: ExitCriterion;
  risks: Risk[];
  /** `Step.contract_fingerprint()` — what was approved about what this step
   *  DOES. Deliberately narrower than the whole step: it excludes the cost, so
   *  an estimate that improved between proposal and execution is not a
   *  deviation. Held by the approval so a deviation is proved, not promised. */
  contract: string;
}

export interface Edge {
  from: string;
  to: string;
}

export interface Build {
  id: string;
  title: string;
  /** The diagnosis outcome this plan answers. A plan that is not the answer to
   *  anything is a plan nobody asked for. */
  forOutcome: string;
  because: string;
  steps: Step[];
  edges: Edge[];
  /** What may run at once, in order. The executor's whole schedule, and the
   *  diagram's rows. */
  waves: string[][];
  environment: Environment;
  cost: Cost;
  exitCriterion: ExitCriterion;
  risks: Risk[];
  questions: Question[];
  facts: Record<string, string>;
  /** Step ids whose tool will not run without a recorded approval. */
  needsApproval: string[];
  say: string;
}

/** What `propose_build` returns when it produced a plan. */
export interface Proposal {
  outcome: string;
  verdict: string;
  /** The diagnosis's own note. NOT the build's `say`. */
  diagnosisSay: string | null;
  build: Build;
  /**
   * The build EXACTLY as it came off the wire, untouched.
   *
   * Kept because `POST /api/storms` compares what it would build now against
   * what was shown using `Manifest.deviations_from`, which reads
   * `Build.as_dict()`'s own keys — `for_outcome`, `exit_criterion`,
   * `environment`. Sending the parsed object above instead would hand it
   * camelCase fields it cannot find and produce a deviation report that says
   * "it now answers ''" about a plan that changed in no such way. Found by
   * approving a real proposal and reading the sentences that came back.
   *
   * The rule this is an instance of: **a payload that will be sent back to the
   * engine goes back as it arrived.** Parsing is for rendering.
   */
  raw: unknown;
  /** `Build.fingerprint()` — everything shown to the person, hashed. This is
   *  what an approval is an approval OF. */
  approve: string;
  factsRecordedAs: string;
  note: string;
}

/** What it returns when it refused to draw a plan it could not run. Not a
 *  failure: `app/tools/propose.py` calls it "a refusal to draw a plan that
 *  could not run". */
export interface ProposalRefusal {
  error: string;
  outcome: string | null;
  detail: string;
  needs: string[];
  help: string;
  coveredOutcomes: string[];
}

/* ── Reading ─────────────────────────────────────────────────────────────── */

export function readProposal(value: unknown): Proposal | null {
  if (!isRecord(value)) return null;
  if (value.ok !== true) return null;
  if (typeof value.approve !== 'string' || !value.approve) return null;
  const build = readBuild(value.build);
  if (!build) return null;
  return {
    outcome: typeof value.outcome === 'string' ? value.outcome : '',
    verdict: typeof value.verdict === 'string' ? value.verdict : '',
    diagnosisSay:
      typeof value.say === 'string' && value.say.trim() ? value.say : null,
    build,
    raw: value.build,
    approve: value.approve,
    factsRecordedAs:
      typeof value.your_facts_were_recorded_as === 'string'
        ? value.your_facts_were_recorded_as
        : '',
    note: typeof value.note === 'string' ? value.note : '',
  };
}

/**
 * A refusal, read strictly enough that it cannot be confused with a tool that
 * merely fell over. `no_honest_build` is the proposer declining to draw
 * something it could not run; `proposer_defect` is our bug and says so.
 */
export function readProposalRefusal(value: unknown): ProposalRefusal | null {
  if (!isRecord(value)) return null;
  if (value.ok !== false) return null;
  const error = typeof value.error === 'string' ? value.error : '';
  if (error !== 'no_honest_build' && error !== 'proposer_defect') return null;
  if (typeof value.detail !== 'string' || !value.detail.trim()) return null;
  return {
    error,
    outcome: typeof value.outcome === 'string' ? value.outcome : null,
    detail: value.detail,
    needs: stringList(value.needs),
    help: typeof value.help === 'string' ? value.help : '',
    coveredOutcomes: stringList(value.covered_outcomes),
  };
}

export function readBuild(value: unknown): Build | null {
  if (!isRecord(value)) return null;
  if (typeof value.id !== 'string' || !value.id) return null;
  if (typeof value.title !== 'string' || !value.title.trim()) return null;

  const exitCriterion = readExitCriterion(value.exit_criterion);
  if (!exitCriterion) return null;
  const cost = readCost(value.cost);
  if (!cost) return null;
  const environment = readEnvironment(value.environment);
  if (!environment) return null;

  if (!Array.isArray(value.steps) || value.steps.length === 0) return null;
  const steps: Step[] = [];
  for (const entry of value.steps) {
    const step = readStep(entry);
    /* One unreadable step and the plan is not drawn. A diagram missing a node
       is a picture that lies about what will happen, which is the one thing
       this surface may never do. */
    if (!step) return null;
    steps.push(step);
  }

  const ids = new Set(steps.map((step) => step.id));
  const edges: Edge[] = [];
  if (!Array.isArray(value.edges)) return null;
  for (const entry of value.edges) {
    if (!isRecord(entry)) return null;
    const from = entry.from;
    const to = entry.to;
    if (typeof from !== 'string' || typeof to !== 'string') return null;
    /* An edge to a node that is not in the picture would be a line drawn to
       nowhere. The engine cannot produce one; if it ever does, this refuses. */
    if (!ids.has(from) || !ids.has(to)) return null;
    edges.push({ from, to });
  }

  const waves: string[][] = [];
  if (!Array.isArray(value.waves)) return null;
  for (const entry of value.waves) {
    const wave = stringList(entry);
    if (wave.length === 0) return null;
    if (wave.some((id) => !ids.has(id))) return null;
    waves.push(wave);
  }
  /* Every step appears in exactly one wave, or the layout would silently drop
     a node. `Build.waves()` guarantees it; this checks rather than trusts. */
  const laid = new Set(waves.flat());
  if (laid.size !== ids.size) return null;

  return {
    id: value.id,
    title: value.title,
    forOutcome: typeof value.for_outcome === 'string' ? value.for_outcome : '',
    because: typeof value.because === 'string' ? value.because : '',
    steps,
    edges,
    waves,
    environment,
    cost,
    exitCriterion,
    risks: readRisks(value.risks),
    questions: readQuestions(value.questions),
    facts: stringMap(value.facts),
    needsApproval: stringList(value.needs_approval).filter((id) => ids.has(id)),
    say: typeof value.say === 'string' ? value.say : '',
  };
}

function readStep(value: unknown): Step | null {
  if (!isRecord(value)) return null;
  if (typeof value.id !== 'string' || !value.id) return null;
  if (typeof value.tool !== 'string' || !value.tool) return null;
  if (typeof value.why !== 'string' || !value.why.trim()) return null;
  if (typeof value.contract !== 'string' || !value.contract) return null;

  const cost = readCost(value.cost);
  /* `app/build.py`: "a step with no cost makes the build's total a lie by
     omission". The same is true of a step whose cost this surface could not
     read, so it is the same refusal. */
  if (!cost) return null;
  const exitCriterion = readExitCriterion(value.exit_criterion);
  if (!exitCriterion) return null;

  return {
    id: value.id,
    tool: value.tool,
    why: value.why,
    arguments: isRecord(value.arguments) ? { ...value.arguments } : {},
    produces: readOutputs(value.produces),
    needs: stringList(value.needs),
    cost,
    exitCriterion,
    risks: readRisks(value.risks),
    contract: value.contract,
  };
}

function readOutputs(value: unknown): Output[] {
  if (!Array.isArray(value)) return [];
  const out: Output[] = [];
  for (const entry of value) {
    if (!isRecord(entry)) continue;
    if (typeof entry.name !== 'string' || typeof entry.type !== 'string') continue;
    out.push({
      name: entry.name,
      type: entry.type,
      description: typeof entry.description === 'string' ? entry.description : '',
      at: typeof entry.at === 'string' ? entry.at : entry.name,
    });
  }
  return out;
}

function readCost(value: unknown): Cost | null {
  if (!isRecord(value)) return null;
  const cost: Partial<Cost> = {};
  for (const dimension of COST_DIMENSIONS) {
    const estimate = readEstimate(value[dimension], dimension);
    /* All four, always. A dimension this surface could not read would render
       as absent, and absent reads as free. */
    if (!estimate) return null;
    cost[dimension] = estimate;
  }
  return cost as Cost;
}

/**
 * One estimate, or nothing. The four refusals in the header are all here, and
 * each one of them is a number that would otherwise reach a person's eye
 * wearing a badge it did not earn.
 */
export function readEstimate(value: unknown, dimension: CostDimension): Estimate | null {
  if (!isRecord(value)) return null;
  if (value.dimension !== dimension) return null;
  if (typeof value.unit !== 'string' || value.unit !== UNIT_OF[dimension]) return null;
  const how = typeof value.how === 'string' ? value.how.trim() : '';
  /* "an estimate that carries no account of where it came from" is the whole
     thing the type exists to require, on this side too. */
  if (!how) return null;

  const from = Array.isArray(value.from)
    ? value.from
        .map((entry) => readEstimate(entry, readDimensionOf(entry) ?? dimension))
        .filter((entry): entry is Estimate => entry !== null)
    : [];

  const provenance = value.provenance;

  if (provenance === 'UNKNOWN') {
    /* If there is a number, it came from somewhere, and that somewhere is its
       provenance. A payload that says UNKNOWN and carries one is not an
       estimate this surface knows how to be honest about. */
    if (value.value !== null && value.value !== undefined) return null;
    const findOutBy =
      typeof value.find_out_by === 'string' ? value.find_out_by.trim() : '';
    if (!findOutBy) return null;
    return { provenance: 'UNKNOWN', dimension, unit: value.unit, how, findOutBy, from };
  }

  if (provenance !== 'MEASURED' && provenance !== 'INFERRED') return null;

  const magnitude = value.value;
  if (typeof magnitude !== 'number' || !Number.isFinite(magnitude)) return null;
  if (magnitude < 0) return null;

  const reading = readReading(value.reading);

  if (provenance === 'MEASURED') {
    /* "a MEASURED estimate is built from a Reading. Without one there is
       nothing that read anything, and the badge is the only measurement in the
       room." */
    if (!reading) return null;
    return {
      provenance: 'MEASURED',
      dimension,
      unit: value.unit,
      value: magnitude,
      how,
      reading,
      from,
    };
  }

  return {
    provenance: 'INFERRED',
    dimension,
    unit: value.unit,
    value: magnitude,
    how,
    reading,
    from,
  };
}

function readDimensionOf(value: unknown): CostDimension | null {
  if (!isRecord(value)) return null;
  const dimension = value.dimension;
  return (COST_DIMENSIONS as readonly string[]).includes(dimension as string)
    ? (dimension as CostDimension)
    : null;
}

function readReading(value: unknown): Reading | null {
  if (!isRecord(value)) return null;
  if (typeof value.value !== 'number' || !Number.isFinite(value.value)) return null;
  const how = typeof value.how === 'string' ? value.how.trim() : '';
  if (!how) return null;
  return {
    dimension: typeof value.dimension === 'string' ? value.dimension : '',
    value: value.value,
    unit: typeof value.unit === 'string' ? value.unit : '',
    how,
    at: typeof value.at === 'string' ? value.at : '',
  };
}

function readExitCriterion(value: unknown): ExitCriterion | null {
  if (!isRecord(value)) return null;
  const stated = typeof value.stated === 'string' ? value.stated.trim() : '';
  /* "an exit criterion with no stated sentence is not stated before it runs,
     which is the only property that makes it worth anything". */
  if (!stated) return null;
  if (typeof value.source !== 'string' || !value.source) return null;
  if (typeof value.subject !== 'string' || !value.subject) return null;
  if (typeof value.comparator !== 'string' || !value.comparator) return null;
  return {
    stated,
    source: value.source,
    subject: value.subject,
    comparator: value.comparator,
    value: value.value ?? null,
  };
}

function readEnvironment(value: unknown): Environment | null {
  if (!isRecord(value)) return null;
  if (typeof value.name !== 'string' || !value.name) return null;
  if (typeof value.working_dir !== 'string' || !value.working_dir) return null;
  const egress = value.egress === true;
  const reason = typeof value.egress_reason === 'string' ? value.egress_reason : '';
  /* The engine refuses egress with no reason and a reason with no egress. If
     either ever reached this surface it would read to the next person as a
     guarantee that is not there, so it is refused here as well. */
  if (egress && !reason.trim()) return null;
  if (!egress && reason.trim()) return null;

  const data: DataSnapshot[] = [];
  if (Array.isArray(value.data)) {
    for (const entry of value.data) {
      if (!isRecord(entry)) continue;
      if (typeof entry.path !== 'string') continue;
      if (typeof entry.bytes !== 'number' || !Number.isFinite(entry.bytes)) continue;
      data.push({
        path: entry.path,
        bytes: entry.bytes,
        modified_at: typeof entry.modified_at === 'string' ? entry.modified_at : '',
        how: typeof entry.how === 'string' ? entry.how : '',
      });
    }
  }

  return {
    name: value.name,
    working_dir: value.working_dir,
    egress,
    egress_reason: reason,
    data,
    installs: stringList(value.installs),
    python: typeof value.python === 'string' ? value.python : '',
  };
}

function readRisks(value: unknown): Risk[] {
  if (!Array.isArray(value)) return [];
  const out: Risk[] = [];
  for (const entry of value) {
    if (!isRecord(entry)) continue;
    const what = typeof entry.what === 'string' ? entry.what.trim() : '';
    const doing = typeof entry.what_we_do === 'string' ? entry.what_we_do.trim() : '';
    /* Half of one is a disclaimer, and a proposal full of disclaimers has
       moved the work of thinking onto the person approving it. */
    if (!what || !doing) continue;
    out.push({ what, what_we_do: doing });
  }
  return out;
}

function readQuestions(value: unknown): Question[] {
  if (!Array.isArray(value)) return [];
  const out: Question[] = [];
  for (const entry of value) {
    if (!isRecord(entry)) continue;
    const ask = typeof entry.ask === 'string' ? entry.ask.trim() : '';
    const why = typeof entry.why === 'string' ? entry.why.trim() : '';
    if (!ask || !why) continue;
    out.push({
      ask,
      why,
      fact: typeof entry.fact === 'string' ? entry.fact : '',
      answered_by: typeof entry.answered_by === 'string' ? entry.answered_by : '',
    });
  }
  return out;
}

/* ── Reading the graph ───────────────────────────────────────────────────── */

/**
 * The `Ref`s in a step's arguments, as `{argument, ref}`.
 *
 * `_plain()` renders a `Ref` as `{"$from_step": ..., "output": ...}`, so the
 * marker is the engine's own and is not guessed at here. This is what lets the
 * diagram tell the two kinds of dependency apart, which is a distinction
 * `app/build.py` draws in as many words: "A `needs` entry with no `Ref` behind
 * it is an ordering the author asserted. A `Ref` is an ordering the graph can
 * check." One is data flowing; the other is only sequence.
 */
export function refsOf(step: Step): { argument: string; ref: Ref }[] {
  const out: { argument: string; ref: Ref }[] = [];
  for (const [argument, value] of Object.entries(step.arguments)) {
    if (!isRecord(value)) continue;
    const from = value.$from_step;
    const output = value.output;
    if (typeof from !== 'string' || typeof output !== 'string') continue;
    out.push({ argument, ref: { step: from, output } });
  }
  return out;
}

/** What flows along one edge, by name, or an empty list when the edge is only
 *  an ordering. */
export function outputsAlong(build: Build, edge: Edge): string[] {
  const target = build.steps.find((step) => step.id === edge.to);
  if (!target) return [];
  return refsOf(target)
    .filter((entry) => entry.ref.step === edge.from)
    .map((entry) => entry.ref.output);
}

/* ── Small readers, shared with facts.ts in spirit and not in code ───────── */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((entry): entry is string => typeof entry === 'string');
}

function stringMap(value: unknown): Record<string, string> {
  if (!isRecord(value)) return {};
  const out: Record<string, string> = {};
  for (const [key, entry] of Object.entries(value)) {
    if (typeof entry === 'string') out[key] = entry;
  }
  return out;
}
