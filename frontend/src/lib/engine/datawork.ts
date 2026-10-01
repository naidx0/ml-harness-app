/**
 * The first tool in this product that changes a user's disk, read off the wire.
 *
 * Every type here is transcribed from `app/tools/datawork.py` — `carve_eval_set`
 * for the write and `_refuse` for the twelve ways it declines — and nothing is
 * widened. A field the engine did not send comes back `null`, never `0` and
 * never a guess, which is `evals.ts`'s rule and the same rule for the same
 * reason: a placeholder that reads like a measurement is the invented number
 * wearing a different hat.
 *
 * ══ WHY THIS FILE EXISTS AT ALL, MEASURED ══════════════════════════════════
 *
 * Measured before it did, by running the real tool on a real file and counting
 * the reply with a transcription of `ResultView.tsx`'s own recursion:
 *
 *                                    clean    leaking   refused
 *   top-level keys                      22         22         7
 *   rows a flat table would draw        83         83         7
 *   rows the payload holds              92        186         7
 *   deepest nesting                      5          7         2
 *   containers dropped at depth 3        1          4         0
 *   rows hidden behind them              9        103         0
 *
 * `ResultView`'s `MAX_DEPTH` is 3. So on the payload that matters most — the
 * one where the split this harness just wrote LEAKS — 103 of 186 rows do not
 * render, and what does not render is `leakage.examples`: the actual pairs of
 * rows found on both sides of a file we produced. That is the chunking sweep's
 * defect exactly, one product surface later.
 *
 * AND A CLAIM THAT WAS MADE HERE AND WAS WRONG, kept because the correction is
 * the useful part. This header first said that `does_not_open_g0` and
 * `grading_is_still_yours` — the two sentences that keep the five-gate promise —
 * were both past `LONG_TEXT` (320) and so rendered folded. They are not: 299 and
 * 221 characters, measured. The two strings that ARE folded are `summary`, which
 * on the leaking payload is 1,221 characters beginning *"LEAKAGE IN WHAT THIS
 * JUST WROTE"*, and `method.how` at 526, which is the rule that decided the
 * split. The card's argument never rested on the wrong half of that and does not
 * need it: seven deep against a cap of three, and the leak pairs are what the cap
 * falls on.
 *
 * The refusal payload is a different matter — 7 keys, 2 deep, nothing hidden —
 * and `ResultView` renders it honestly. It gets a card anyway, and a small one,
 * for a reason that is not about shape: a tool that writes files declining to
 * write must say *nothing was written* where a person reads it, not as the
 * fourth key of a table.
 *
 * ══ WHAT THIS READER MAKES STRUCTURALLY UNDROPPABLE ════════════════════════
 *
 * `openedNoGate` AND `gradingIsStillYours` ARE NOT OPTIONAL FIELDS. They are
 * required strings on `Carve`, so a card cannot be written that omits them and
 * still compiles. The tool sends both on every successful path and is explicit
 * about why: *"'I wrote 40 rows' is this program's own arithmetic"*. A card
 * that showed a row count and dropped that sentence would be a file we wrote
 * looking like a gate we opened.
 *
 * `leaked` AND `examples` COME OUT TOGETHER. There is no shape here that hands
 * a caller a leak count without the rows behind it, because the count without
 * the rows is what `ResultView` already draws.
 *
 * `measured` IS ALWAYS PRESENT AND IS ALWAYS EMPTY. `carve_eval_set` declares
 * `measures=()`, checked at registration, so this is `[]` on every path; it is
 * read anyway so that the day it is not, the card says so instead of quietly
 * drawing a fact nobody stamped.
 */

/* ── shared helpers, the three `evals.ts` and `retrieval.ts` use ───────────── */

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

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

/* ── what it wrote ────────────────────────────────────────────────────────── */

/** One file on the person's disk, with the two things that identify it later. */
export type WrittenFile = {
  file: string;
  path: string;
  rows: number;
  bytes: number | null;
  sha256: string | null;
  format: string | null;
};

function readWritten(raw: unknown): WrittenFile | null {
  if (!isRecord(raw)) return null;
  const file = str(raw.file);
  if (!file) return null;
  return {
    file,
    path: text(raw.path),
    rows: int(raw.rows),
    bytes: num(raw.bytes),
    sha256: str(raw.sha256),
    format: str(raw.format),
  };
}

/** The input as it was when it was read. A folder has no digest and says so.
 *
 *  THE FULL RECORD IS IN THE MANIFEST, NOT IN THE REPLY. Measured by reading a
 *  real payload: `source` is a manifest key and the tool result carries `path`
 *  and `rows_read` at the top level instead. So this is assembled from whichever
 *  the engine sent, and the digest fields stay `null` rather than being filled
 *  in from somewhere — a sha256 this file invented would be the worst kind of
 *  invented number, because its whole purpose is to be compared. */
export type Source = {
  path: string;
  format: string | null;
  rowsRead: number;
  bytes: number | null;
  sha256: string | null;
  note: string | null;
};

/* ── the check it ran on its own output ───────────────────────────────────── */

/**
 * ROW TEXT OUT OF SOMEBODY'S FILE, AND IT IS DATA RATHER THAN WORDS.
 *
 * `app/tools/context.py`'s `quarantine()` is the contract and the envelope is
 * the enforcement: *"a caller that wants the text has to reach into an object
 * labelled `data`, whose `trusted` field is false, whose `handling` field says
 * what to do with it, and whose `instruction_like` field lists anything in it
 * that tried to talk to the model."* This is the first surface in the frontend
 * that draws one — measured: no file under `frontend/src` mentioned
 * `instruction_like` before it — so the envelope is transcribed rather than
 * unwrapped, and a card that shows the content shows the flag beside it.
 *
 * `trusted` is read even though the engine sets it false on every path, for
 * `measured`'s reason: the day it is not, the card can say so rather than
 * quietly drawing somebody's file as if it were ours.
 */
export type Excerpt = {
  content: string;
  source: string;
  characters: number | null;
  truncated: boolean;
  trusted: boolean;
  /** Lines in this row that read as an instruction to a model. Reported, never
   *  removed: usually a prompt template somebody forgot was in their data, and
   *  worth saying out loud either way. */
  instructionLike: { line: number | null; why: string; quote: string }[];
};

function readExcerpt(raw: unknown): Excerpt | null {
  if (!isRecord(raw)) return null;
  const content = raw.content;
  if (typeof content !== 'string') return null;
  return {
    content,
    source: text(raw.source),
    characters: num(raw.characters),
    truncated: raw.truncated === true,
    trusted: raw.trusted === true,
    instructionLike: list(raw.instruction_like).flatMap((one) => {
      if (!isRecord(one)) return [];
      return [
        {
          line: num(one.line),
          why: text(one.why),
          quote: text(one.quote),
        },
      ];
    }),
  };
}

/** A pair of rows found on both sides of a split this harness wrote.
 *
 *  `check_split_leakage` returns these under `leakage.examples`, and they are
 *  the reason this file exists: they are exactly what `ResultView` replaces
 *  with the words *"3 items, not shown here"*. */
export type LeakExample = {
  /** What kind of match it was, in the engine's own word. `exact` and the
   *  near-duplicate basis are different claims and the card says which. */
  basis: string | null;
  similarity: number | null;
  /** Whether that similarity was measured or inferred, in the engine's own
   *  vocabulary. Read rather than assumed: a similarity with no provenance is
   *  the invented number wearing a decimal point. */
  similarityProvenance: string | null;
  trainRow: number | null;
  evalRow: number | null;
  train: Excerpt | null;
  evaluation: Excerpt | null;
};

function readExample(raw: unknown): LeakExample | null {
  if (!isRecord(raw)) return null;
  const train = readExcerpt(raw.train_excerpt);
  const evaluation = readExcerpt(raw.eval_excerpt);
  const basis = str(raw.similarity_basis);
  const similarity = num(raw.similarity);
  if (!train && !evaluation && !basis && similarity === null) return null;
  return {
    basis,
    similarity,
    similarityProvenance: str(raw.similarity_provenance),
    trainRow: num(raw.train_row),
    evalRow: num(raw.eval_row),
    train,
    evaluation,
  };
}

/** What we found when we checked our own work. Never a boolean on its own. */
export type Verification = {
  tool: string;
  ran: boolean;
  /** `null` means the check did not report a number, which is not zero. */
  leaked: number | null;
  exact: number | null;
  near: number | null;
  threshold: number | null;
  thresholdIs: string | null;
  summary: string | null;
  /** Does eval + train add up to what was read. */
  partitionHolds: boolean;
  partitionIs: string;
  examples: LeakExample[];
  /** Checks the leakage tool declined to run, in its own words. */
  notRun: string[];
};

/* ── how it chose ─────────────────────────────────────────────────────────── */

export type Method = {
  rule: string | null;
  how: string;
  seed: string;
  rowsAskedFor: number | null;
  /** WHERE THE SIZE CAME FROM, and it is the whole provenance of the number.
   *  Either "the caller" or the engine file the floor was read out of. */
  rowsAskedForCameFrom: string | null;
  answerColumn: string | null;
  qualifies: string;
  wholeGroupsOnly: string;
  rowsAreVerbatim: string;
};

/* ── the reply ────────────────────────────────────────────────────────────── */

export type Carve = {
  ok: boolean;
  summary: string;
  into: string;
  evalPath: string;
  trainPath: string;
  manifestPath: string | null;
  rowsRead: number;
  evalRows: number;
  trainRows: number;
  answerColumn: string | null;
  distinctAnswers: number | null;
  wrote: WrittenFile[];
  formatWritten: string | null;
  formatWrittenWhy: string;
  source: Source | null;
  method: Method | null;
  verification: Verification | null;
  /** Always `[]`: the tool declares `measures=()`. Read so the day it is not,
   *  the card can say so rather than draw a fact nobody stamped. */
  measured: string[];
  /** REQUIRED. See the header: a card cannot be written that drops these. */
  openedNoGate: string;
  gradingIsStillYours: string;
};

/** A carve reply, or `null` for anything that is not one.
 *
 *  Keyed on the two paths plus `into`, which no other tool in this registry
 *  returns together. `readCarveRefusal` takes the other half, and the two are
 *  disjoint by `nothing_was_written`. */
export function readCarve(raw: unknown): Carve | null {
  if (!isRecord(raw)) return null;
  if (raw.nothing_was_written === true) return null;
  const evalPath = str(raw.eval_path);
  const trainPath = str(raw.train_path);
  const into = str(raw.into);
  if (!evalPath || !trainPath || !into) return null;

  const method = isRecord(raw.method) ? raw.method : null;
  const verification = isRecord(raw.verification) ? raw.verification : null;
  const leakage = isRecord(raw.leakage) ? raw.leakage : null;
  const source = isRecord(raw.source) ? raw.source : null;

  return {
    ok: raw.ok === true,
    summary: text(raw.summary),
    into,
    evalPath,
    trainPath,
    manifestPath: str(raw.manifest_path),
    rowsRead: int(raw.rows_read),
    evalRows: int(raw.eval_rows),
    trainRows: int(raw.train_rows),
    answerColumn: str(raw.answer_column),
    distinctAnswers: num(raw.distinct_answers),
    wrote: list(raw.wrote)
      .map(readWritten)
      .filter((one): one is WrittenFile => one !== null),
    formatWritten: str(raw.format_written),
    formatWrittenWhy: text(raw.format_written_why),
    source: source
      ? {
          path: text(source.path),
          format: str(source.format),
          rowsRead: int(source.rows_read),
          bytes: num(source.bytes),
          sha256: str(source.sha256),
          note: str(source.note),
        }
      : str(raw.path)
        ? {
            path: text(raw.path),
            format: null,
            rowsRead: int(raw.rows_read),
            bytes: null,
            sha256: null,
            note: null,
          }
        : null,
    method: method
      ? {
          rule: str(method.rule),
          how: text(method.how),
          seed: text(method.seed),
          rowsAskedFor: num(method.rows_asked_for),
          rowsAskedForCameFrom: str(method.rows_asked_for_came_from),
          answerColumn: str(method.answer_column),
          qualifies: text(method.qualifies),
          wholeGroupsOnly: text(method.whole_groups_only),
          rowsAreVerbatim: text(method.rows_are_verbatim),
        }
      : null,
    verification: verification
      ? {
          tool: text(verification.tool) || 'check_split_leakage',
          ran: verification.ran === true,
          leaked: num(verification.leaked_rows),
          exact: num(verification.exact_matches),
          near: num(verification.near_matches),
          threshold: num(verification.threshold),
          thresholdIs: str(leakage?.threshold_is),
          summary: str(verification.summary),
          partitionHolds: verification.partition_holds === true,
          partitionIs: text(verification.partition_is),
          /* THE ROWS, NOT ONLY THE COUNT. They live one level deeper than the
             count, under `leakage`, which is exactly why the generic table
             loses them. */
          examples: list(leakage?.examples)
            .map(readExample)
            .filter((one): one is LeakExample => one !== null),
          notRun: list(leakage?.checks_not_run).map(text).filter(Boolean),
        }
      : null,
    measured: list(raw.measured).map(text).filter(Boolean),
    openedNoGate: text(raw.does_not_open_g0),
    gradingIsStillYours: text(raw.grading_is_still_yours),
  };
}

/* ── the refusals ─────────────────────────────────────────────────────────── */

/** One of the twelve ways `carve_eval_set` declines, plus whatever numbers that
 *  particular refusal carries.
 *
 *  `rest` is deliberately not a closed table of the twelve shapes. Every
 *  refusal carries `error`, `summary` and `nothing_was_written`; what else it
 *  carries differs per reason — `would_leave` and `minimum_to_train_on` for the
 *  starvation one, `columns` for the missing column, `share` for the one-value
 *  one — and a private list here would go stale the first time the sibling lane
 *  adds a thirteenth. So the named fields are read and the rest is handed over
 *  under the engine's own key names, which is `ResultView`'s rule kept rather
 *  than dropped. */
export type CarveRefusal = {
  error: string;
  summary: string;
  nothingWasWritten: boolean;
  /** Anything else the refusal carried, under the engine's own field names. */
  rest: [string, unknown][];
};

const DRAWN_ALREADY = new Set(['ok', 'error', 'summary', 'nothing_was_written']);

export function readCarveRefusal(raw: unknown): CarveRefusal | null {
  if (!isRecord(raw)) return null;
  if (raw.nothing_was_written !== true) return null;
  const error = str(raw.error);
  if (!error) return null;
  return {
    error,
    summary: text(raw.summary),
    nothingWasWritten: true,
    rest: Object.entries(raw).filter(([key]) => !DRAWN_ALREADY.has(key)),
  };
}

/* ── amplified rows, and the tenth of them somebody has to read ───────────── */

/**
 * `synthesize_rows` — the reply, transcribed.
 *
 * This is the most dangerous tool in the product and the card that draws it has
 * one job beyond reporting: make the two facts that keep it honest impossible
 * to miss. **Every row is tagged**, and **nothing here opened a gate**. Both are
 * engine fields, not sentences this file wrote: `wrote` carries the file, and
 * `does_not_open_g0` is the engine's own words in the manifest.
 *
 * `answersMovedVerbatim` has no engine field behind it and there is none to
 * read: it is a property of the code - the answer column's value is copied and
 * never generated - so the card states it as what it is, an assurance about the
 * method, in the method section rather than beside a number.
 */
export type Synthesis = {
  ok: boolean;
  summary: string;
  into: string;
  sourcePath: string;
  syntheticPath: string;
  manifestPath: string | null;
  rowsRead: number;
  answeredRows: number;
  rowsWritten: number;
  answerColumn: string | null;
  seed: string;
  wrote: WrittenFile[];
};

export function readSynthesis(raw: unknown): Synthesis | null {
  if (!isRecord(raw)) return null;
  const syntheticPath = str(raw.synthetic_path);
  const into = str(raw.into);
  if (!syntheticPath || !into) return null;
  return {
    ok: raw.ok === true,
    summary: text(raw.summary),
    into,
    sourcePath: text(raw.path),
    syntheticPath,
    manifestPath: str(raw.manifest_path),
    rowsRead: int(raw.rows_read),
    answeredRows: int(raw.answered_rows),
    rowsWritten: int(raw.rows_written),
    answerColumn: str(raw.answer_column),
    seed: text(raw.seed),
    wrote: list(raw.wrote)
      .map(readWritten)
      .filter((one): one is WrittenFile => one !== null),
  };
}

/** `draw_verification_sample` — the rows a person has been asked to read. */
export type VerificationSample = {
  ok: boolean;
  summary: string;
  samplePath: string;
  sourcePath: string;
  rowsTotal: number;
  rowsWritten: number;
  generatedRows: number;
  seed: string;
};

export function readVerificationSample(raw: unknown): VerificationSample | null {
  if (!isRecord(raw)) return null;
  const samplePath = str(raw.sample_path);
  if (!samplePath) return null;
  return {
    ok: raw.ok === true,
    summary: text(raw.summary),
    samplePath,
    sourcePath: text(raw.path),
    rowsTotal: int(raw.rows_total),
    rowsWritten: int(raw.rows_written),
    generatedRows: int(raw.generated_rows),
    seed: text(raw.seed),
  };
}

/** `record_verification` — what the person said about what they read. */
export type VerificationRecord = {
  ok: boolean;
  summary: string;
  dataset: string;
  judged: number;
  wrong: number;
  verificationPath: string | null;
};

export function readVerificationRecord(raw: unknown): VerificationRecord | null {
  if (!isRecord(raw)) return null;
  const dataset = str(raw.dataset);
  const path = str(raw.verification_path);
  if (!dataset || !path) return null;
  if (typeof raw.judged !== 'number') return null;
  return {
    ok: raw.ok === true,
    summary: text(raw.summary),
    dataset,
    judged: int(raw.judged),
    wrong: int(raw.wrong),
    verificationPath: path,
  };
}
