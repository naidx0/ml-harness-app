/**
 * The eval bench, read off the wire.
 *
 * Every type here is transcribed from `app/tools/evals.py` — `read()` for the
 * report and `compare()` for the pairing — and nothing is widened. A field the
 * engine did not send comes back `null`, never `0` and never a guess, for the
 * same reason `facts.ts` refuses a default: a placeholder that reads like a
 * measurement is the invented number wearing a different hat.
 *
 * ══ THE ONE THING THIS FILE IS FOR ═════════════════════════════════════════
 *
 * `evals.py` never returns a score without `resolution` beside it, and it never
 * returns a delta without `resolved`. That is not a courtesy; it is the whole
 * product. `docs/PRODUCT_SPEC.md`'s own sentence — *"n=30 only resolves
 * differences larger than ~15 points… report the resolution alongside every
 * score"* — is a claim about the INTERFACE, because a resolution the renderer
 * drops is a resolution that was never reported.
 *
 * So the two payload readers below make it structurally impossible to render a
 * score without its interval or a comparison without its verdict: `score` and
 * `resolution` come out of `readEvalReport` together, and `delta` on a
 * comparison is only reachable through a `verdict` that already says whether
 * the eval set could see it. A caller that wants one has the other in hand.
 *
 * ══ WHY `resolved` IS NOT A BOOLEAN THIS FILE COMPUTES ═════════════════════
 *
 * It would be one line to compare `p_value` against .05 here. It is read off
 * the wire instead, because the threshold and the test are the engine's to
 * choose — `compare()` runs McNemar's exact binomial over the rows that
 * CHANGED, which is a different and stronger test than anything a renderer
 * holding two percentages could reconstruct. An interface that re-derived the
 * verdict would be a second opinion competing with the instrument, and on the
 * day the engine switches to a corrected test the two would disagree silently.
 */

/** The confidence block that travels with every score `evals.py` produces. */
export interface EvalResolution {
  /** Rows graded. `0` means nothing was, and then every field below is null. */
  n: number;
  /** Wilson 95%, as two fractions in [0,1]. Null when nothing was graded. */
  ci95: [number, number] | null;
  /** Half-width of that interval, in PERCENTAGE POINTS. */
  halfWidthPoints: number | null;
  /** The smallest difference two INDEPENDENT runs of this size could resolve,
   *  in percentage points. Worst case at p=0.5. The engine's own name for it
   *  is long and says which of the two figures it is; that distinction is
   *  load-bearing and is kept in the field name here. */
  resolvesDifferenceOfPoints: number | null;
  /** Rows that would resolve a 10-point difference, and how many more than
   *  this run has. */
  rowsForTenPoints: number | null;
  moreRowsNeededForTenPoints: number | null;
  /** The engine's sentence. Rendered verbatim or not at all. */
  says: string | null;
  /** How the interval was computed. Provenance for the interval itself. */
  method: string | null;
}

/**
 * A model's grade of a model's answers, as `evals._self_graded` returns it.
 *
 * TYPED, BECAUSE THE UNTYPED VERSION SILENTLY RENDERED NOTHING. This block
 * used to reach the card as `Record<string, unknown>` and the card read
 * `self.says`, `self.judge_is_the_same_model` and `self.self_graded` — three
 * key names, none of which the engine has ever sent. It sends `warning`,
 * `is_the_model_that_answered`, `rows_judged`, `judge_model` and
 * `deterministic_scores_on_the_same_rows`. Every branch of the component
 * therefore fell through to `return null`, and a run where one model graded its
 * own homework rendered as a bare score with a MEASURED tag and no disclosure
 * at all. Measured in the running app against a real `model_graded` run before
 * this type existed: `model_graded 30%` in 26px type, `exact_match 0%` and
 * `contains 80%` on the identical rows, neither of them on screen.
 *
 * `Record<string, unknown>` is what let that ship. A reader that names the
 * fields fails loudly in `tsc` when the engine renames one; a bag of unknowns
 * fails silently in front of the user.
 */
export interface SelfGraded {
  /** The model that did the grading. */
  judgeModel: string | null;
  /** How many rows it decided. */
  rowsJudged: number;
  /** Is the judge the model that produced the answers? */
  isTheModelThatAnswered: boolean;
  /** The rule-computed scores on the SAME rows, which is the honest thing to
   *  put beside a judge's number. Empty when no rule could grade them. */
  deterministic: Record<string, number>;
  /** The engine's own sentence. Rendered verbatim or not at all. */
  warning: string | null;
}

/** One failing row, exactly as `read()` returns it. */
export interface EvalFailure {
  rowIndex: number;
  input: string;
  expected: string;
  answer: string;
  failureMode: string | null;
  verdicts: Record<string, boolean>;
  gradedBy: string | null;
  bucketedBy: string | null;
  seconds: number | null;
}

/** One stored run. `read(run_id)` in `app/tools/evals.py`. */
export interface EvalReport {
  runId: number;
  threadId: number | null;
  complete: boolean;
  reused: boolean;
  evalPath: string;
  evalFingerprint: string | null;
  inputField: string | null;
  expectedField: string | null;
  metric: string;
  prompt: string | null;
  promptIsDefault: boolean;
  provider: string | null;
  model: string | null;
  locality: string | null;
  judgeModel: string | null;
  planned: number;
  graded: number;
  correct: number;
  rowsAvailable: number | null;
  /** The score, ONLY on a complete run. A partial run reports `partialScore`
   *  under its own name so a renderer cannot print half a measurement as a
   *  whole one by reading the field it expected to find. */
  score: number | null;
  partialScore: number | null;
  /** Every deterministic metric's score on the same rows. */
  scores: Record<string, number>;
  /** What answering the single most common label would have scored. The
   *  number that decides whether a score means anything at all. */
  trivialBaselineScore: number | null;
  trivialAnswer: string | null;
  resolution: EvalResolution;
  failureHistogram: Record<string, number>;
  unclassified: number;
  failures: EvalFailure[];
  failuresTotal: number;
  /** Present and non-null when a MODEL graded any row of this run. */
  selfGraded: SelfGraded | null;
  bucketsDecidedBy: string | null;
  summary: string | null;
}

/**
 * Was this score produced by a rule, or by a model's opinion?
 *
 * The one question the eval card's provenance tag has to answer before it is
 * allowed to say MEASURED, and it is a question about the METRIC and not about
 * who ran the tool. `evals.py` runs a real tool and this interface watches it
 * either way; what differs is whether what it watched was a rule applied to a
 * string or a model being asked whether it was right.
 *
 * `docs/diagnosis_engine.yaml` settles the vocabulary and this file only reads
 * it: a model's grade is `judge_score`, declared `opinion_of: model`, and the
 * ledger's own note is that such a fact "may never carry the MEASURED origin".
 * The interface's job is the same claim in pixels — see `EvalCard`.
 */
export function scoreIsAnOpinion(report: EvalReport): boolean {
  return report.metric === 'model_graded' || report.selfGraded !== null;
}

/**
 * Each run's own aggregate score over its OWN rows, and their difference.
 *
 * THIS IS THE NUMBER THAT SHIPPED AS THE HEADLINE AND WAS WRONG. `evals.py`
 * demoted it here — "it is a fact about two runs; it is not the difference
 * between them" — and the interface has to keep it demoted. It is carried
 * because it is real and somebody will want it, and it is never the big type,
 * never coloured, and never printed without the sentence that says which two
 * row sets it spans.
 */
export interface EvalAggregate {
  /** This run's own score over its own rows. Null on an unscored run. */
  score: number | null;
  scoreAgainst: number | null;
  /** The subtraction the old headline showed. */
  difference: number | null;
  rows: number;
  rowsAgainst: number;
  onlyThisRunGraded: number[];
  onlyTheOtherGraded: number[];
  onlyThisRunGradedCount: number;
  onlyTheOtherGradedCount: number;
  /** The engine's own sentence about it. Rendered verbatim or not at all. */
  says: string | null;
}

/**
 * Two runs over the same eval set, paired row by row.
 *
 * `verdict` is the field the interface must branch on and it has exactly two
 * values. `different` means McNemar separated them. `no_evidence` means this
 * eval set cannot tell them apart — and `delta` is still populated, which is
 * the trap: it is a real subtraction of two real paired scores and it is not a
 * result.
 *
 * `sameRows` IS THE SECOND TRAP AND IT IS NEWER. A shared `evalFingerprint`
 * says the two runs are about the same eval SET; it says nothing about which
 * ROWS either of them graded, because `sample` and `hold_out` decide that and
 * neither is hashed. When it is false the reported delta is still honest — the
 * engine pairs on the intersection — but rows were dropped from both sides to
 * get there, and a card that does not say so is showing a comparison of a
 * subset while looking like a comparison of the set.
 */
export interface EvalComparison {
  runId: number;
  against: number;
  evalFingerprint: string | null;
  pairedRows: number;
  /** Did both runs grade exactly the same rows? False means rows were dropped
   *  from both sides to pair them, and `aggregate` says which. */
  sameRows: boolean;
  /** PAIRED — this run's score over the rows both graded, not over its own. */
  score: number | null;
  scoreAgainst: number | null;
  /** Paired correct counts, the numerators of the two scores above. */
  correct: number;
  correctAgainst: number;
  delta: number;
  improved: number;
  regressed: number;
  changed: number;
  pValue: number;
  test: string | null;
  resolved: boolean;
  verdict: 'different' | 'no_evidence';
  /** Each run's own aggregate over its own rows. Never the headline. */
  aggregate: EvalAggregate | null;
  /** The engine's sentence naming the row set every number here was read on. */
  measuredOn: string | null;
  /** How many rows WOULD resolve a difference this size. Null when the two
   *  scores are identical, because there is no difference to resolve. */
  rowsThatWouldResolveThisDelta: number | null;
  improvedRows: number[];
  regressedRows: number[];
  /** run id (as a string, the engine's own key) → the prompt it ran under. */
  prompts: Record<string, string | null>;
  resolution: EvalResolution;
  says: string | null;
}

/** `compare()` refusing, in the three ways it refuses. All three are answers,
 *  not errors: the engine declining to subtract two numbers that must not be
 *  subtracted is the product working.
 *
 *  `no_shared_rows` IS THE THIRD AND IT ARRIVED WITHOUT THIS FILE. Two runs
 *  over one eval set on disjoint slices of it — which `sample` and `hold_out`
 *  make easy and which a shared fingerprint cannot catch — have not been
 *  compared at all, and `evals.py` now says so rather than reporting that "not
 *  one of the 0 rows changed its verdict", which read as agreement. Until it
 *  was added here the payload fell through to the raw key/value table and
 *  rendered under the word FAILED, in a product whose whole argument is that a
 *  refusal to compute is not a failure. Reproduced in the running app before
 *  it was fixed; see the report. */
export interface EvalRefusal {
  error: 'different_eval_sets' | 'incomplete_run' | 'no_shared_rows';
  detail: string;
  /** `no_shared_rows` only: which rows each run graded alone. The whole content
   *  of the refusal, and what turns "ask again" into something actionable. */
  onlyThisRunGraded: number[];
  onlyTheOtherGraded: number[];
  /** run id (as the engine's own string key) → rows it graded. */
  graded: Record<string, number>;
}

/** The run list `read_eval_results` returns with no `run_id`. */
export interface EvalRunSummary {
  runId: number;
  evalPath: string;
  metric: string;
  model: string | null;
  promptIsDefault: boolean;
  planned: number;
  graded: number;
  complete: boolean;
  evalFingerprint: string | null;
  createdAt: string | null;
}

export interface EvalRunList {
  count: number;
  runs: EvalRunSummary[];
  help: string | null;
}

/* ── Readers ──────────────────────────────────────────────────────────────
   Same shape as `readDiagnosis`: a total function to `T | null`, no throw, and
   a `null` the caller falls back from rather than an exception it must catch.
   A result that is not an eval report is not an error — it is one of the other
   thirty tools. */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function int(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.trunc(value)
    : fallback;
}

function str(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function intList(value: unknown): number[] {
  if (!Array.isArray(value)) return [];
  return value.filter((entry): entry is number => typeof entry === 'number');
}

function counts(value: unknown): Record<string, number> {
  if (!isRecord(value)) return {};
  const out: Record<string, number> = {};
  for (const [key, entry] of Object.entries(value)) {
    if (typeof entry === 'number' && Number.isFinite(entry)) out[key] = entry;
  }
  return out;
}

function verdictMap(value: unknown): Record<string, boolean> {
  if (!isRecord(value)) return {};
  const out: Record<string, boolean> = {};
  for (const [key, entry] of Object.entries(value)) {
    if (typeof entry === 'boolean') out[key] = entry;
  }
  return out;
}

/**
 * The interval block. Never invents one: an absent `resolution` yields `n: 0`
 * and nulls throughout, which the card renders as "nothing has been graded"
 * rather than as a confident interval around a score of zero.
 */
export function readResolution(value: unknown): EvalResolution {
  if (!isRecord(value)) {
    return {
      n: 0,
      ci95: null,
      halfWidthPoints: null,
      resolvesDifferenceOfPoints: null,
      rowsForTenPoints: null,
      moreRowsNeededForTenPoints: null,
      says: null,
      method: null,
    };
  }
  const raw = value.ci_95;
  const ci =
    Array.isArray(raw) && raw.length === 2 && num(raw[0]) !== null && num(raw[1]) !== null
      ? ([raw[0] as number, raw[1] as number] as [number, number])
      : null;
  return {
    n: int(value.n),
    ci95: ci,
    halfWidthPoints: num(value.half_width_points),
    resolvesDifferenceOfPoints: num(value.resolves_a_difference_of_at_least_points),
    rowsForTenPoints: num(value.rows_for_a_10_point_difference),
    moreRowsNeededForTenPoints: num(value.more_rows_needed_for_10_points),
    says: str(value.says),
    method: str(value.method),
  };
}

/**
 * A stored eval run, or null.
 *
 * `run_id` plus `planned` is the discriminator. `graded` alone would match the
 * comparison payload, and `score` alone would match half the tools in the
 * registry, so both are required and both are checked for type rather than
 * truthiness — a run with `graded: 0` is a real run that has not started.
 */
export function readEvalReport(value: unknown): EvalReport | null {
  if (!isRecord(value)) return null;
  if (value.ok !== true) return null;
  if (typeof value.run_id !== 'number') return null;
  if (typeof value.planned !== 'number') return null;
  if (typeof value.graded !== 'number') return null;
  /* A comparison also carries `run_id`; it carries `against` too, and never
     carries `planned`. Checked anyway, because a payload that satisfies both
     readers would render as two different cards depending on call order. */
  if (value.against !== undefined) return null;

  return {
    runId: value.run_id,
    threadId: num(value.thread_id),
    complete: value.complete === true,
    reused: value.reused === true,
    evalPath: text(value.eval_path),
    evalFingerprint: str(value.eval_fingerprint),
    inputField: str(value.input_field),
    expectedField: str(value.expected_field),
    metric: text(value.metric) || 'exact_match',
    prompt: str(value.prompt),
    promptIsDefault: value.prompt_is_default === true,
    provider: str(value.provider),
    model: str(value.model),
    locality: str(value.locality),
    judgeModel: str(value.judge_model),
    planned: int(value.planned),
    graded: int(value.graded),
    correct: int(value.correct),
    rowsAvailable: num(value.rows_available),
    score: num(value.score),
    partialScore: num(value.partial_score),
    scores: counts(value.scores),
    trivialBaselineScore: num(value.trivial_baseline_score),
    trivialAnswer: str(value.trivial_answer),
    resolution: readResolution(value.resolution),
    failureHistogram: counts(value.failure_histogram),
    unclassified: int(value.unclassified),
    failures: readFailures(value.failures),
    failuresTotal: int(value.failures_total),
    selfGraded: readSelfGraded(value.self_graded),
    bucketsDecidedBy: str(value.buckets_decided_by),
    summary: str(value.summary),
  };
}

/**
 * The judge block, by the engine's own field names.
 *
 * `judge_model` is required: `_self_graded` returns the whole block as `None`
 * unless a model actually decided rows, so a block without one is not a shape
 * this file understands and `null` is the honest answer. Everything else has a
 * defined absence — a judge with no warning sentence still gets disclosed,
 * because the disclosure is the presence of the block and not the prose in it.
 */
export function readSelfGraded(value: unknown): SelfGraded | null {
  if (!isRecord(value)) return null;
  const judge = str(value.judge_model);
  if (!judge) return null;
  return {
    judgeModel: judge,
    rowsJudged: int(value.rows_judged),
    isTheModelThatAnswered: value.is_the_model_that_answered === true,
    deterministic: counts(value.deterministic_scores_on_the_same_rows),
    warning: str(value.warning),
  };
}

function readFailures(value: unknown): EvalFailure[] {
  if (!Array.isArray(value)) return [];
  const out: EvalFailure[] = [];
  for (const entry of value) {
    if (!isRecord(entry)) continue;
    if (typeof entry.row_index !== 'number') continue;
    out.push({
      rowIndex: entry.row_index,
      input: text(entry.input),
      expected: text(entry.expected),
      answer: text(entry.answer),
      failureMode: str(entry.failure_mode),
      verdicts: verdictMap(entry.verdicts),
      gradedBy: str(entry.graded_by),
      bucketedBy: str(entry.bucketed_by),
      seconds: num(entry.seconds),
    });
  }
  return out;
}

/**
 * A paired comparison, or null.
 *
 * `verdict` is trusted only when it is one of the engine's two words. Anything
 * else returns null and the payload falls through to the key/value table,
 * because a comparison card whose verdict this file had to guess at is exactly
 * the surface that would declare an unresolvable winner.
 */
export function readEvalComparison(value: unknown): EvalComparison | null {
  if (!isRecord(value)) return null;
  if (value.ok !== true) return null;
  if (typeof value.run_id !== 'number') return null;
  if (typeof value.against !== 'number') return null;
  if (typeof value.p_value !== 'number') return null;
  const verdict = value.verdict;
  if (verdict !== 'different' && verdict !== 'no_evidence') return null;
  /* `resolved` and `verdict` are two spellings of one decision on the wire.
     If they ever disagree the payload is not one this surface understands, and
     falling through to the table is safer than picking the optimistic half. */
  if ((verdict === 'different') !== (value.resolved === true)) return null;

  const prompts: Record<string, string | null> = {};
  if (isRecord(value.prompts)) {
    for (const [key, entry] of Object.entries(value.prompts)) {
      prompts[key] = typeof entry === 'string' ? entry : null;
    }
  }

  return {
    runId: value.run_id,
    against: value.against,
    evalFingerprint: str(value.eval_fingerprint),
    pairedRows: int(value.paired_rows),
    /* DEFAULTS TO FALSE, NOT TRUE. An engine that has not sent the field is an
       engine this file cannot ask, and "we do not know whether the same rows
       were graded" and "the same rows were graded" are not the same state of
       knowledge. Defaulting the other way would silently drop the disclosure
       against exactly the older engine that needs it most. */
    sameRows: value.same_rows === true,
    score: num(value.score),
    scoreAgainst: num(value.score_against),
    correct: int(value.correct),
    correctAgainst: int(value.correct_against),
    delta: num(value.delta) ?? 0,
    improved: int(value.improved),
    regressed: int(value.regressed),
    changed: int(value.changed),
    pValue: value.p_value,
    test: str(value.test),
    resolved: value.resolved === true,
    verdict,
    aggregate: readAggregate(value.aggregate),
    measuredOn: str(value.measured_on),
    rowsThatWouldResolveThisDelta: num(value.rows_that_would_resolve_this_delta),
    improvedRows: intList(value.improved_rows),
    regressedRows: intList(value.regressed_rows),
    prompts,
    resolution: readResolution(value.resolution),
    says: str(value.says),
  };
}

/** Each run's own aggregate, when the engine sent one. */
function readAggregate(value: unknown): EvalAggregate | null {
  if (!isRecord(value)) return null;
  return {
    score: num(value.score),
    scoreAgainst: num(value.score_against),
    difference: num(value.difference),
    rows: int(value.rows),
    rowsAgainst: int(value.rows_against),
    onlyThisRunGraded: intList(value.only_this_run_graded),
    onlyTheOtherGraded: intList(value.only_the_other_graded),
    onlyThisRunGradedCount: int(value.only_this_run_graded_count),
    onlyTheOtherGradedCount: int(value.only_the_other_graded_count),
    says: str(value.says),
  };
}

/** `compare()` declining. Three named refusals and nothing else — an
 *  unrecognised error falls through so a new one cannot be rendered under an
 *  old sentence. */
export function readEvalRefusal(value: unknown): EvalRefusal | null {
  if (!isRecord(value)) return null;
  if (value.ok !== false) return null;
  const error = value.error;
  if (
    error !== 'different_eval_sets' &&
    error !== 'incomplete_run' &&
    error !== 'no_shared_rows'
  ) {
    return null;
  }
  const graded: Record<string, number> = {};
  if (isRecord(value.graded)) {
    for (const [key, entry] of Object.entries(value.graded)) {
      if (typeof entry === 'number' && Number.isFinite(entry)) graded[key] = entry;
    }
  }
  return {
    error,
    detail: text(value.detail),
    onlyThisRunGraded: intList(value.only_this_run_graded),
    onlyTheOtherGraded: intList(value.only_the_other_graded),
    graded,
  };
}

/** The list `read_eval_results` returns when asked for no run in particular. */
export function readEvalRunList(value: unknown): EvalRunList | null {
  if (!isRecord(value)) return null;
  if (value.ok !== true) return null;
  if (!Array.isArray(value.runs)) return null;
  if (typeof value.count !== 'number') return null;

  const runs: EvalRunSummary[] = [];
  for (const entry of value.runs) {
    if (!isRecord(entry) || typeof entry.run_id !== 'number') continue;
    runs.push({
      runId: entry.run_id,
      evalPath: text(entry.eval_path),
      metric: text(entry.metric) || 'exact_match',
      model: str(entry.model),
      promptIsDefault: entry.prompt_is_default === true,
      planned: int(entry.planned),
      graded: int(entry.graded),
      complete: entry.complete === true,
      evalFingerprint: str(entry.eval_fingerprint),
      createdAt: str(entry.created_at),
    });
  }
  return { count: value.count, runs, help: str(value.help) };
}

/* ── Failure modes ────────────────────────────────────────────────────────

   THE EIGHT ARE THE ENGINE'S, TRANSCRIBED, NOT NAMED HERE. The ids and the
   stage each one routes to are copied out of `S1_ROUTE_BY_FAILURE_MODE` in
   `docs/diagnosis_engine.yaml`; `evals.py:routable_modes()` reads the same
   table and RAISES on a key it has no route for, so a ninth bucket invented in
   this file would take down somebody's diagnosis rather than merely look wrong.

   The first draft of this map had `refusal`, `truncated`, `hallucination`,
   `off_topic`, `empty` and `error` in it. Not one of those is a bucket this
   product has: they are plausible-sounding names for a thing that already had
   real names, which is invariant 5 in its most ordinary costume. Six of ten
   entries were fabricated. They are listed here rather than quietly deleted
   because the next person to write this map from memory will reach for exactly
   the same six.

   `routes` is not decoration either. A failure histogram is the INPUT to
   stage 1 of the diagnosis, and which bucket dominates is what picks the stage
   that answers. Showing the destination beside the count is showing the reader
   what their own failures are about to be routed into. */

export interface FailureMode {
  /** The reader's word for the bucket. */
  word: string;
  /** The diagnosis stage `S1_ROUTE_BY_FAILURE_MODE` sends this bucket to. */
  routesTo: string;
}

export const FAILURE_MODES: Record<string, FailureMode> = {
  wrong_facts: { word: 'Wrong facts', routesTo: 'knowledge' },
  wrong_format: { word: 'Wrong format', routesTo: 'format' },
  wrong_style: { word: 'Wrong style', routesTo: 'behaviour' },
  inconsistent: { word: 'Inconsistent', routesTo: 'behaviour' },
  refuses: { word: 'Refuses', routesTo: 'behaviour' },
  wrong_reasoning: { word: 'Wrong reasoning', routesTo: 'capability' },
  too_slow: { word: 'Too slow', routesTo: 'efficiency' },
  too_expensive: { word: 'Too expensive', routesTo: 'efficiency' },
};

/** The word for a bucket, or the id itself. Never a prettified guess: an id
 *  this map has never seen keeps its underscores, so a reader can grep the
 *  engine for it and find out what it is. */
export function failureModeWord(mode: string): string {
  return FAILURE_MODES[mode]?.word ?? mode;
}

/** Where the diagnosis would route this bucket, or null if this surface does
 *  not know. Null renders as nothing at all, never as a guessed stage. */
export function failureModeRoute(mode: string): string | null {
  return FAILURE_MODES[mode]?.routesTo ?? null;
}

/**
 * The bucket that dominates, and whether it dominates enough to route on.
 *
 * `S1_MIXED_FAILURES` fires when `max(histogram) / sum(histogram) < 0.5` and
 * its outcome is ACTION__SPLIT_THE_TASK — *"No single failure mode dominates…
 * one fine-tune cannot fix four different problems."* That threshold is the
 * engine's, quoted here so the card can say which side of it this run fell on
 * rather than leaving a reader to eyeball a bar chart for it.
 */
export function dominantMode(
  histogram: Record<string, number>,
): { mode: string; count: number; share: number; dominates: boolean } | null {
  const entries = Object.entries(histogram);
  if (entries.length === 0) return null;
  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  if (total <= 0) return null;
  let best = entries[0];
  for (const entry of entries) if (entry[1] > best[1]) best = entry;
  const share = best[1] / total;
  return { mode: best[0], count: best[1], share, dominates: share >= 0.5 };
}
