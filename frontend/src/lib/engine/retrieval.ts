/**
 * The retrieval bench, read off the wire.
 *
 * Every type here is transcribed from `app/tools/retrieval.py` — `score_recall`
 * and `_refusal` for one index, `sweep_chunkings`, `plan_chunkings` and
 * `_sweep_refusal` for a family of them — and nothing is widened. A field the
 * engine did not send comes back `null`, never `0` and never a guess, which is
 * `evals.ts`'s rule and the same rule for the same reason: a placeholder that
 * reads like a measurement is the invented number wearing a different hat.
 *
 * ══ WHY THIS FILE EXISTS AT ALL ════════════════════════════════════════════
 *
 * Measured before it did: ZERO files under `frontend/src` referenced either
 * tool, so both fell through to `ResultView`, the generic key/value table. A
 * real sweep returns 40 top-level keys, 614 rows once flattened, and nests six
 * deep against `ResultView`'s `MAX_DEPTH` of 3 — so the deepest parts, which
 * include every pairwise test, rendered as *"28 items, not shown here"*.
 *
 * ══ THE THREE THINGS THE READER MAKES STRUCTURALLY UNDROPPABLE ═════════════
 *
 * `crowned` IS NOT READ AS A VALUE, IT IS READ AS A GUARANTEE. `sweep_chunkings`
 * sets it to `None` on every path, including the one where four of six
 * comparisons separate, and `compare_hit_vectors` sets it to `None` too. So
 * there is no `crowned` field on `ChunkingSweep` for a component to draw. What
 * there is instead is `whyNothingIsCrowned`, which is a sentence, and
 * `highestRecallHere`, which arrives as a LIST and cannot be rendered as a
 * winner without ignoring its own type. If the engine ever starts crowning
 * something, this file fails to compile rather than silently drawing a leader.
 *
 * `recall` AND `resolution` COME OUT TOGETHER, per setting and for the single
 * run, exactly as `readEvalReport` binds a score to its interval. There is no
 * shape in this file that hands a caller a recall without the interval beside
 * it.
 *
 * `measured` AND `notMeasured` ARE BOTH ALWAYS PRESENT. `compare_chunkings`
 * declares `measures=()`, checked at registration, so a sweep's `measured` is
 * `[]` on every path and `notMeasured` carries `STAMPS_NOTHING`. A card that
 * showed a recall curve and no stamp block would be showing the one number in
 * this bench that opens a gate with nothing saying it was not recorded.
 */

/* ── shared helpers, the same three `evals.ts` uses ───────────────────────── */

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

function strList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((entry): entry is string => typeof entry === 'string');
}

function counts(value: unknown): Record<string, number> {
  if (!isRecord(value)) return {};
  const out: Record<string, number> = {};
  for (const [key, entry] of Object.entries(value)) {
    if (typeof entry === 'number' && Number.isFinite(entry)) out[key] = entry;
  }
  return out;
}

function records(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord);
}

/* ── the interval ─────────────────────────────────────────────────────────
   `retrieval.py` calls `evals.resolution_for`, so a recall's interval and an
   eval score's interval are one instrument's output under two names. Read with
   the same field names `evals.ts` reads, deliberately: two numbers a person is
   asked to compare must not be stated by two different readers. */

export interface RecallResolution {
  /** Questions scored. `0` means none were, and every field below is null. */
  n: number;
  /** Wilson 95%, two fractions in [0,1]. Null when nothing was scored. */
  ci95: [number, number] | null;
  /** Half-width of that interval, in PERCENTAGE POINTS. */
  halfWidthPoints: number | null;
  /** The smallest difference two INDEPENDENT runs of this size could resolve,
   *  in percentage points. The engine's own name says which of the two figures
   *  it is and that distinction is load-bearing, so it is kept here. */
  resolvesDifferenceOfPoints: number | null;
  rowsForTenPoints: number | null;
  moreRowsNeededForTenPoints: number | null;
  /** The engine's sentence. Rendered verbatim or not at all. */
  says: string | null;
  method: string | null;
}

export function readRecallResolution(value: unknown): RecallResolution {
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
    Array.isArray(raw) &&
    raw.length === 2 &&
    num(raw[0]) !== null &&
    num(raw[1]) !== null
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

/* ── the levers ───────────────────────────────────────────────────────────
   `NO_TRAIN__FIX_RETRIEVAL` names four and this harness owns one. The engine
   puts the block on EVERY reply including every refusal, and the reason it
   gives is that "a person told to fix their retriever deserves to know which
   quarter of the job this is". Typed, so a card cannot quietly drop three
   quarters of an answer by forgetting a key. */

export interface Lever {
  lever: string;
  whyNot: string;
  whoCan: string;
}

export interface Levers {
  /** The one this harness can vary. */
  weCanVary: string;
  /** The three it cannot, each with who can and what it would cost. */
  weCannotPull: Lever[];
  /** The full account, and the short line that travels in every summary. */
  says: string | null;
  inOneLine: string | null;
}

export function readLevers(value: unknown): Levers | null {
  if (!isRecord(value)) return null;
  const vary = str(value.we_can_vary);
  if (!vary) return null;
  return {
    weCanVary: vary,
    weCannotPull: records(value.we_cannot_pull).map((row) => ({
      lever: text(row.lever),
      whyNot: text(row.why_not),
      whoCan: text(row.who_can),
    })),
    says: str(value.says),
    inOneLine: str(value.in_one_line),
  };
}

/* ══ ONE INDEX, SCORED ALONE ══════════════════════════════════════════════ */

/** One point on the recall curve. RECALL RISES WITH K, so the tool returns the
 *  whole curve and not only the headline, and `tieDecided` is on every point
 *  because a curve entry is a displayed number and gets the same disclosure
 *  the headline gets. */
export interface RecallPoint {
  k: number;
  hits: number;
  of: number;
  recall: number | null;
  tieDecided: number;
}

/** One scored question. */
export interface RecallRow {
  row: number;
  question: string;
  groundTruth: string;
  level: string | null;
  matchedBy: string | null;
  /** Where the right thing came back, 1-based, or null for a miss. */
  foundAtRank: number | null;
  /** The band a score tie leaves the true rank in. Equal when nothing tied. */
  bestPossibleRank: number | null;
  worstPossibleRank: number | null;
  /** The depths at which a tie rather than the retriever decided the answer. */
  tieDecidedAtK: number[];
  topPassage: string | null;
  returned: string[];
}

function readRecallRow(value: Record<string, unknown>): RecallRow {
  return {
    row: int(value.row),
    question: text(value.question),
    groundTruth: text(value.ground_truth),
    level: str(value.level),
    matchedBy: str(value.matched_by),
    foundAtRank: num(value.found_at_rank),
    bestPossibleRank: num(value.best_possible_rank),
    worstPossibleRank: num(value.worst_possible_rank),
    tieDecidedAtK: intList(value.tie_decided_at_k),
    topPassage: str(value.top_passage),
    returned: strList(value.returned),
  };
}

/**
 * The WEAKER proxy, and it is never recall.
 *
 * `_answer_in_passage` counts how often the expected answer's text appears
 * somewhere in the retrieved passages. `PRODUCT_SPEC §6.6` allows it only
 * "clearly marked as such, never a recall number", and no code path in
 * `retrieval.py` stamps `retriever_recall_at_k` from it. `isNotRecall` is the
 * engine's own paragraph saying which two ways it comes apart, and it is
 * REQUIRED here rather than optional so a card cannot render the rate without
 * it.
 */
export interface AnswerInPassage {
  name: string;
  hits: number;
  of: number;
  rate: number;
  answerField: string | null;
  k: number | null;
  isNotRecall: string;
  provenance: string | null;
}

function readAnswerInPassage(value: unknown): AnswerInPassage | null {
  if (!isRecord(value)) return null;
  const rate = num(value.rate);
  const warning = str(value.is_not_recall);
  if (rate === null || !warning) return null;
  return {
    name: text(value.name) || 'answer_in_passage_rate',
    hits: int(value.hits),
    of: int(value.of),
    rate,
    answerField: str(value.answer_field),
    k: num(value.k),
    isNotRecall: warning,
    provenance: str(value.provenance),
  };
}

/** One row the ledger took, as `Instrument.minted` returns it. */
export interface MintedFact {
  fact: string;
  value: number | null;
  origin: string | null;
  how: string | null;
}

function readMinted(value: unknown): MintedFact[] {
  return records(value).map((row) => ({
    fact: text(row.fact),
    value: num(row.value),
    origin: str(row.origin),
    how: str(row.how),
  }));
}

/**
 * `measure_retriever_recall`, in every state it has.
 *
 * ONE SHAPE FOR THE SCORE AND FOR THE REFUSAL, because `retrieval._refusal`
 * returns every key a scored run returns holding the honest null — "a caller
 * that special-cases a refusal is a caller that can forget to". So this reader
 * does not have a refusal type; it has `error`, `recall` of `null`, and
 * `notMeasured` carrying the sentence that names what would fix it.
 */
export interface RecallReport {
  /** The engine's own error slug when it declined. Null on a scored run. */
  error: string | null;
  indexId: number | null;
  indexName: string | null;
  evalPath: string;
  questionField: string | null;
  groundTruthField: string | null;
  /** How the ground-truth column was arrived at — named in the call, or found
   *  by convention. Provenance for the column itself. */
  groundTruthChosenHow: string | null;
  /** `passage`, `document`, `mixed`, or null. Never a silent majority. */
  groundTruthLevel: string | null;
  levels: Record<string, number>;
  matchedBy: Record<string, number>;
  k: number;
  hits: number | null;
  /** Null when nothing was scored. Never 0 standing in for "no answer". */
  recall: number | null;
  resolution: RecallResolution;
  curve: RecallPoint[];
  questionsScored: number;
  questionsEligible: number;
  rowsRead: number;
  /** Null on the refusal path, which does not read past the cap. */
  rowsSeen: number | null;
  hitRowCap: boolean;
  unresolvedN: number;
  unresolvedRows: string[];
  unlabelledN: number;
  unlabelledRows: number[];
  unlabelledByReason: Record<string, number>;
  tieDecidedN: number;
  tieDecidedRows: number[];
  /** The one boolean that guards the stamp, computed in `score_recall` and
   *  read here rather than re-derived: seven different runs can look like a
   *  measurement without being one, and this is the engine's answer. */
  stampable: boolean;
  rows: RecallRow[];
  misses: RecallRow[];
  answerInPassage: AnswerInPassage | null;
  /** What the ledger actually took. Empty on every unstamped path. */
  measured: MintedFact[];
  /** Why it took nothing. Empty string when it took something. */
  notMeasured: string;
  recorded: string | null;
  scorer: string | null;
  decidesNothing: string | null;
  summary: string;
  /** The columns the file does have, on the refusal that says none of them
   *  names a document. */
  columns: string[];
  candidates: string[];
}

/**
 * A recall report, or null.
 *
 * `stampable` plus `recall_curve` plus `questions_scored` is the discriminator,
 * and all three are type-checked rather than truth-checked. `build_retrieval_
 * index`, `search_the_index` and `read_index` all carry `index_id` and two of
 * them carry `k`; none of them has ever carried `stampable`, which exists only
 * on the one tool in this module that can record a fact.
 */
export function readRecallReport(value: unknown): RecallReport | null {
  if (!isRecord(value)) return null;
  if (typeof value.stampable !== 'boolean') return null;
  if (!Array.isArray(value.recall_curve)) return null;
  if (typeof value.questions_scored !== 'number') return null;

  return {
    error: str(value.error),
    indexId: num(value.index_id),
    indexName: str(value.index_name),
    evalPath: text(value.eval_path),
    questionField: str(value.question_field),
    groundTruthField: str(value.ground_truth_field),
    groundTruthChosenHow: str(value.ground_truth_chosen_how),
    groundTruthLevel: str(value.ground_truth_level),
    levels: counts(value.levels),
    matchedBy: counts(value.matched_by),
    k: int(value.k),
    hits: num(value.hits),
    recall: num(value.recall_at_k),
    resolution: readRecallResolution(value.resolution),
    curve: records(value.recall_curve).map((row) => ({
      k: int(row.k),
      hits: int(row.hits),
      of: int(row.of),
      recall: num(row.recall),
      tieDecided: int(row.tie_decided),
    })),
    questionsScored: int(value.questions_scored),
    questionsEligible: int(value.questions_eligible),
    rowsRead: int(value.rows_read),
    rowsSeen: num(value.rows_seen),
    hitRowCap: value.hit_row_cap === true,
    unresolvedN: int(value.unresolved_n),
    unresolvedRows: strList(value.unresolved_ground_truth),
    unlabelledN: int(value.unlabelled_n),
    unlabelledRows: intList(value.unlabelled_rows),
    unlabelledByReason: counts(value.unlabelled_by_reason),
    tieDecidedN: int(value.tie_decided_n),
    tieDecidedRows: intList(value.tie_decided_rows),
    stampable: value.stampable,
    rows: records(value.rows).map(readRecallRow),
    misses: records(value.misses).map(readRecallRow),
    answerInPassage: readAnswerInPassage(value.answer_in_passage),
    measured: readMinted(value.measured),
    notMeasured: text(value.not_measured),
    recorded: str(value.recorded),
    scorer: str(value.scorer),
    decidesNothing: str(value.decides_nothing),
    summary: text(value.summary),
    columns: strList(value.columns),
    candidates: strList(value.candidates),
  };
}

/* ══ A FAMILY OF INDEXES, COMPARED ════════════════════════════════════════ */

/** One setting's recall over the questions EVERY setting scored, and — demoted
 *  and named, exactly as `evals.compare` demotes `aggregate` — its recall over
 *  every row it could score on its own. */
export interface SweepSetting {
  /** The engine's own label, `chars/overlap`. Its identifier everywhere in the
   *  payload, including the keys of `beatenBy`, so it is kept verbatim. */
  setting: string;
  hits: number;
  of: number;
  recall: number;
  resolution: RecallResolution;
  passageChars: number | null;
  passageOverlap: number | null;
  indexId: number | null;
  indexName: string | null;
  passages: number | null;
  /** This setting scored on its own rows. A DIFFERENT DENOMINATOR, and the
   *  engine says so in `says`, which is why the two counts travel together. */
  ownRun: {
    hits: number;
    of: number;
    recall: number | null;
    unresolvedN: number;
    tieDecidedN: number;
    stampableOnItsOwn: boolean;
    says: string | null;
  } | null;
}

/** One pairwise McNemar test, after Holm. */
export interface SweepPair {
  a: string;
  b: string;
  /** Questions `a` got right and `b` did not, and the other way round. The
   *  rows both settings agree on carry no information about the difference and
   *  are correctly absent from every number here except `agreed`. */
  aBetterOn: number;
  bBetterOn: number;
  changed: number;
  agreed: number;
  delta: number;
  p: number;
  adjustedP: number | null;
  holmThreshold: number | null;
  rankInFamily: number | null;
  separated: boolean;
  /** Which of the two changed more rows, or null on a tie. NOT a winner: it is
   *  only a claim when `separated` is true, and the card is what enforces
   *  that. */
  better: string | null;
  /** How many questions would have to change verdict before this pair could be
   *  separated AT ALL at its own Holm threshold. Arithmetic, not a rule of
   *  thumb: two-sided exact McNemar over m discordant rows cannot go below
   *  2**(1-m). */
  minChangedToSeparate: number | null;
  test: string | null;
  says: string | null;
}

/** Choose on half the questions, look the choice up on the other half. The
 *  only part of the sweep that touches the upward bias of a maximum. */
export interface SweepConfirmation {
  ok: boolean;
  /** Why there is no confirmation, when there is none. */
  why: string | null;
  chosenOnQuestions: number | null;
  confirmedOnQuestions: number | null;
  splitBy: string | null;
  assumes: string | null;
  /** `fell`, `rose`, `unchanged` or `mixed` — as DATA, so a card does not have
   *  to parse English to find out whether the gap it is about to draw is a
   *  quantity of selection at all. */
  gapDirection: string | null;
  /** True only when the gap is `fell`. The upward bias of a maximum is
   *  non-negative by construction, so a negative gap is not a smaller amount
   *  of it, and this boolean is the engine refusing to let a card say it is. */
  gapIsAReadOnSelection: boolean;
  tieOnTheChoosingHalf: boolean;
  chosen: string[];
  rows: {
    setting: string;
    chosenOnHits: number;
    chosenOnOf: number;
    chosenOnRecall: number | null;
    confirmedHits: number;
    confirmedOf: number;
    confirmedRecall: number | null;
    shrinkage: number | null;
    resolution: RecallResolution;
  }[];
  says: string | null;
}

function readConfirmation(value: unknown): SweepConfirmation | null {
  if (!isRecord(value)) return null;
  return {
    ok: value.ok === true,
    why: str(value.why),
    chosenOnQuestions: num(value.chosen_on_questions),
    confirmedOnQuestions: num(value.confirmed_on_questions),
    splitBy: str(value.split_by),
    assumes: str(value.assumes),
    gapDirection: str(value.gap_direction),
    gapIsAReadOnSelection: value.gap_is_a_read_on_selection === true,
    tieOnTheChoosingHalf: value.tie_on_the_choosing_half === true,
    chosen: strList(value.chosen),
    rows: records(value.rows).map((row) => ({
      setting: text(row.setting),
      chosenOnHits: int(row.chosen_on_hits),
      chosenOnOf: int(row.chosen_on_of),
      chosenOnRecall: num(row.chosen_on_recall),
      confirmedHits: int(row.confirmed_hits),
      confirmedOf: int(row.confirmed_of),
      confirmedRecall: num(row.confirmed_recall),
      shrinkage: num(row.shrinkage),
      resolution: readRecallResolution(row.resolution),
    })),
    says: str(value.says),
  };
}

/** What one setting would do if somebody went and took the stamp themselves —
 *  which the engine recommends and which does NOT hand back the number in the
 *  curve whenever this sweep dropped a row. */
export interface ReMeasuring {
  rowsThisComparisonUsed: number;
  rowsDroppedBeforeComparing: number;
  settingsOnTheSameRows: number;
  settingsThatWouldStamp: number;
  howToNameASetting: string | null;
  says: string | null;
}

function readReMeasuring(value: unknown): ReMeasuring | null {
  if (!isRecord(value)) return null;
  return {
    rowsThisComparisonUsed: int(value.rows_this_comparison_used),
    rowsDroppedBeforeComparing: int(value.rows_dropped_before_comparing),
    settingsOnTheSameRows: int(
      value.settings_whose_own_run_uses_the_same_rows,
    ),
    settingsThatWouldStamp: int(value.settings_whose_own_run_would_stamp),
    howToNameASetting: str(value.how_to_name_a_setting),
    says: str(value.says),
  };
}

/** Which settings are the same experiment wearing different numbers. A window
 *  wider than every paragraph it would have to split is inert, so several
 *  windows can produce passage-for-passage identical indexes — and then NO
 *  EVIDENCE across them is a fact about these windows and not about chunking.
 *  The engine computes it; a card that dropped it would let the verdict be
 *  read as a finding it is not. */
export interface IdenticalCuts {
  distinctCuts: number | null;
  identicalGroups: string[][];
  familyOverDistinctCuts: number | null;
  says: string | null;
}

function readCuts(value: unknown): IdenticalCuts | null {
  if (!isRecord(value)) return null;
  const groups = Array.isArray(value.identical_groups)
    ? value.identical_groups.map(strList).filter((group) => group.length > 0)
    : [];
  return {
    distinctCuts: num(value.distinct_cuts),
    identicalGroups: groups,
    familyOverDistinctCuts: num(value.family_over_distinct_cuts),
    says: str(value.says),
  };
}

/** One planned setting, counted before anything was written. */
export interface PlannedSetting {
  passageChars: number | null;
  passageOverlap: number | null;
  indexName: string | null;
  cutFingerprint: string | null;
  passages: number | null;
  postingRows: number | null;
  terms: number | null;
  shortFragmentsDropped: number | null;
  passagesWithNoIndexableTerm: number | null;
  wouldTruncate: boolean;
  alreadyBuilt: boolean;
  existingIndexId: number | null;
  nameTakenByAnotherCorpus: boolean;
}

function readPlanned(value: unknown): PlannedSetting[] {
  return records(value).map((row) => ({
    passageChars: num(row.passage_chars),
    passageOverlap: num(row.passage_overlap),
    indexName: str(row.index_name),
    cutFingerprint: str(row.cut_fingerprint),
    passages: num(row.passages),
    postingRows: num(row.posting_rows),
    terms: num(row.terms),
    shortFragmentsDropped: num(row.short_fragments_dropped),
    passagesWithNoIndexableTerm: num(row.passages_with_no_indexable_term),
    wouldTruncate: row.would_truncate === true,
    alreadyBuilt: row.already_built === true,
    existingIndexId: num(row.existing_index_id),
    nameTakenByAnotherCorpus: row.name_taken_by_another_corpus === true,
  }));
}

/** The counts a sweep would write, or did. Never a duration: nothing in this
 *  harness has measured how long a rebuild takes on this machine, and the tool
 *  says so rather than guessing. */
export interface WillDo {
  settings: number | null;
  distinctCuts: number | null;
  rebuilds: number | null;
  reusedWithoutRebuilding: number | null;
  documentsEachTime: number | null;
  documentsSkipped: number | null;
  passagesWritten: number | null;
  postingRowsWritten: number | null;
  retrievals: number | null;
  questionsEachSettingIsScoredOn: number | null;
  pairwiseComparisons: number | null;
  pairwiseComparisonsOverDistinctCuts: number | null;
  countedBy: string | null;
}

function readWillDo(value: unknown): WillDo | null {
  if (!isRecord(value)) return null;
  return {
    settings: num(value.settings),
    distinctCuts: num(value.distinct_cuts),
    rebuilds: num(value.rebuilds),
    reusedWithoutRebuilding: num(value.reused_without_rebuilding),
    documentsEachTime: num(value.documents_each_time),
    documentsSkipped: num(value.documents_skipped),
    passagesWritten: num(value.passages_written),
    postingRowsWritten: num(value.posting_rows_written),
    retrievals: num(value.retrievals),
    questionsEachSettingIsScoredOn: num(value.questions_each_setting_is_scored_on),
    pairwiseComparisons: num(value.pairwise_comparisons),
    pairwiseComparisonsOverDistinctCuts: num(
      value.pairwise_comparisons_over_distinct_cuts,
    ),
    countedBy: str(value.counted_by),
  };
}

/** The eval set, as the sweep read it. */
export interface SweepQuestions {
  evalPath: string | null;
  questionField: string | null;
  groundTruthField: string | null;
  groundTruthChosenHow: string | null;
  rowsSeen: number | null;
  rowsRead: number | null;
  eligible: number | null;
  unlabelled: number | null;
  unlabelledByReason: Record<string, number>;
  k: number | null;
}

function readQuestions(value: unknown): SweepQuestions | null {
  if (!isRecord(value)) return null;
  return {
    evalPath: str(value.eval_path),
    questionField: str(value.question_field),
    groundTruthField: str(value.ground_truth_field),
    groundTruthChosenHow: str(value.ground_truth_chosen_how),
    rowsSeen: num(value.rows_seen),
    rowsRead: num(value.rows_read),
    eligible: num(value.eligible),
    unlabelled: num(value.unlabelled),
    unlabelledByReason: counts(value.unlabelled_by_reason),
    k: num(value.k),
  };
}

/** The shape of the sweep, known before it runs. Only on the plan. */
export interface SweepStatistics {
  alpha: number | null;
  familySize: number | null;
  correction: string | null;
  tightestThreshold: number | null;
  minChangedToSeparateAnyPair: number | null;
  says: string | null;
}

function readStatistics(value: unknown): SweepStatistics | null {
  if (!isRecord(value)) return null;
  return {
    alpha: num(value.alpha),
    familySize: num(value.family_size),
    correction: str(value.correction),
    tightestThreshold: num(value.tightest_threshold),
    minChangedToSeparateAnyPair: num(
      value.min_changed_questions_to_separate_any_pair,
    ),
    says: str(value.says),
  };
}

/**
 * `compare_chunkings`, in every state it has.
 *
 * FOUR STATES, ONE SHAPE. `plan_chunkings` returns the counts with `ran:
 * false`; a refusal reached before any index is built returns `ok: false` with
 * a sentence; `_sweep_refusal` returns every key a finished sweep returns
 * holding the honest null, with `verdict: "nothing_was_compared"` and the
 * indexes it DID build named; a finished sweep returns the curve and the
 * verdict. `state` below is the discriminator a card branches on, derived from
 * the engine's own three fields and from nothing else.
 */
export type SweepState = 'refused' | 'plan' | 'nothing_compared' | 'compared';

export interface ChunkingSweep {
  state: SweepState;
  /** The engine's own error slug, when there is one. */
  error: string | null;
  /** `no_evidence`, `some_settings_separated`, `nothing_was_compared`, or null
   *  on a plan. Read off the wire and never re-derived from p-values here: the
   *  test and the threshold are the engine's to choose. */
  verdict: string | null;
  corpusPath: string | null;
  evalPath: string | null;
  questions: SweepQuestions | null;
  cuts: IdenticalCuts | null;
  willDo: WillDo | null;
  statistics: SweepStatistics | null;
  planned: PlannedSetting[];
  /** The indexes this call actually wrote. Named even on a refusal, because an
   *  index it built is in the conversation whether or not the comparison
   *  finished. */
  indexes: {
    passageChars: number | null;
    passageOverlap: number | null;
    indexId: number | null;
    indexName: string | null;
    passages: number | null;
    documents: number | null;
    totalTokens: number | null;
    reused: boolean;
    truncated: boolean;
    cutBy: string | null;
  }[];
  comparedQuestions: number;
  perSetting: SweepSetting[];
  comparisons: SweepPair[];
  familySize: number;
  separatedN: number;
  alpha: number | null;
  correction: string | null;
  tightestThreshold: number | null;
  /** The floor for the WHOLE sweep. Holm is step-down, so the smallest p in
   *  the family is compared against alpha/m; if no pair changes at least this
   *  many verdicts, nothing separates at all. */
  minChangedAtThisFamilySize: number | null;
  mostChangedByAnyPair: number | null;
  /** Which settings something was shown to beat. A key per setting, empty when
   *  nothing beat it. */
  beatenBy: Record<string, string[]>;
  notBeatenByAnything: string[];
  /** A LIST, never a scalar, because a tie at the top is not a shortlist. */
  highestRecallHere: string[];
  /** THE SENTENCE THAT MUST TRAVEL WITH `highestRecallHere`. There is no
   *  `crowned` on this type at all: the engine sets it to None on every path
   *  and a field for it would be an invitation to draw one. */
  whyNothingIsCrowned: string | null;
  measuredOn: string | null;
  confirmation: SweepConfirmation | null;
  reMeasuring: ReMeasuring | null;
  dropped: {
    notScoredByEverySetting: number;
    decidedByATie: number;
    notScoredRows: number[];
    tieRows: number[];
    why: string | null;
  };
  levers: Levers | null;
  /** Always empty. `measures=()` is checked at registration. */
  measured: MintedFact[];
  notMeasured: string;
  stampsNothing: string | null;
  decidesNothing: string | null;
  scorer: string | null;
  says: string;
  /** On the `would_truncate` and `name_taken` refusals the engine returns the
   *  planned settings and no comparison; on `ground_truth_is_not_invariant`
   *  it also returns the level it found. */
  groundTruthLevel: string | null;
}

/**
 * A chunking sweep, or null.
 *
 * `levers` plus `stamps_nothing` is the discriminator and it is the honest one:
 * every reply `compare_chunkings` produces carries both — the plan, the four
 * pre-build refusals, the mid-sweep refusals and the finished comparison — and
 * no other tool in the registry carries either. Checking `per_setting` instead
 * would have missed every refusal, which is exactly the set of replies a person
 * most needs drawn as something other than a table.
 */
export function readChunkingSweep(value: unknown): ChunkingSweep | null {
  if (!isRecord(value)) return null;
  const levers = readLevers(value.levers);
  if (levers === null) return null;
  if (typeof value.stamps_nothing !== 'string') return null;

  const ran = value.ran === true;
  const ok = value.ok === true;
  const verdict = str(value.verdict);
  const state: SweepState = !ok
    ? 'refused'
    : !ran
      ? 'plan'
      : verdict === 'nothing_was_compared'
        ? 'nothing_compared'
        : 'compared';

  const perSetting: SweepSetting[] = records(value.per_setting).map((row) => {
    const own = isRecord(row.own_run) ? row.own_run : null;
    return {
      setting: text(row.setting),
      hits: int(row.hits),
      of: int(row.of),
      recall: num(row.recall) ?? 0,
      resolution: readRecallResolution(row.resolution),
      passageChars: num(row.passage_chars),
      passageOverlap: num(row.passage_overlap),
      indexId: num(row.index_id),
      indexName: str(row.index_name),
      passages: num(row.passages),
      ownRun: own
        ? {
            hits: int(own.hits),
            of: int(own.of),
            recall: num(own.recall),
            unresolvedN: int(own.unresolved_n),
            tieDecidedN: int(own.tie_decided_n),
            stampableOnItsOwn: own.stampable_on_its_own === true,
            says: str(own.says),
          }
        : null,
    };
  });

  const beaten: Record<string, string[]> = {};
  if (isRecord(value.beaten_by)) {
    for (const [key, entry] of Object.entries(value.beaten_by)) {
      beaten[key] = strList(entry);
    }
  }

  const droppedRows = isRecord(value.dropped_rows) ? value.dropped_rows : null;

  return {
    state,
    error: str(value.error),
    verdict,
    corpusPath: str(value.corpus_path),
    evalPath: str(value.eval_path),
    questions: readQuestions(value.questions),
    cuts: readCuts(value.cuts),
    willDo: readWillDo(value.will_do),
    statistics: readStatistics(value.statistics),
    planned: readPlanned(value.settings),
    indexes: records(value.indexes).map((row) => ({
      passageChars: num(row.passage_chars),
      passageOverlap: num(row.passage_overlap),
      indexId: num(row.index_id),
      indexName: str(row.index_name),
      passages: num(row.passages),
      documents: num(row.documents),
      totalTokens: num(row.total_tokens),
      reused: row.reused === true,
      truncated: row.truncated === true,
      cutBy: str(row.cut_by),
    })),
    comparedQuestions: int(value.compared_questions),
    perSetting,
    comparisons: records(value.comparisons).map((row) => ({
      a: text(row.a),
      b: text(row.b),
      aBetterOn: int(row.a_better_on),
      bBetterOn: int(row.b_better_on),
      changed: int(row.changed),
      agreed: int(row.agreed),
      delta: num(row.delta) ?? 0,
      p: num(row.p) ?? 1,
      adjustedP: num(row.adjusted_p),
      holmThreshold: num(row.holm_threshold),
      rankInFamily: num(row.rank_in_family),
      separated: row.separated === true,
      better: str(row.better),
      minChangedToSeparate: num(row.min_changed_questions_to_separate),
      test: str(row.test),
      says: str(row.says),
    })),
    familySize: int(value.family_size),
    separatedN: int(value.separated_n),
    alpha: num(value.alpha),
    correction: str(value.correction),
    tightestThreshold: num(value.tightest_threshold),
    minChangedAtThisFamilySize: num(
      value.min_changed_questions_at_this_family_size,
    ),
    mostChangedByAnyPair: num(value.most_changed_by_any_pair),
    beatenBy: beaten,
    notBeatenByAnything: strList(value.not_beaten_by_anything),
    highestRecallHere: strList(value.highest_recall_here),
    whyNothingIsCrowned: str(value.why_nothing_is_crowned),
    measuredOn: str(value.measured_on),
    confirmation: readConfirmation(value.confirmation),
    reMeasuring: readReMeasuring(value.re_measuring),
    dropped: {
      notScoredByEverySetting: int(value.dropped_not_scored_by_every_setting),
      decidedByATie: int(value.dropped_decided_by_a_tie),
      notScoredRows: droppedRows
        ? intList(droppedRows.not_scored_by_every_setting)
        : [],
      tieRows: droppedRows ? intList(droppedRows.decided_by_a_tie) : [],
      why: droppedRows ? str(droppedRows.why) : null,
    },
    levers,
    measured: readMinted(value.measured),
    notMeasured: text(value.not_measured),
    stampsNothing: str(value.stamps_nothing),
    decidesNothing: str(value.decides_nothing),
    scorer: str(value.scorer),
    says: text(value.says) || text(value.summary) || text(value.detail),
    groundTruthLevel: str(value.ground_truth_level),
  };
}
