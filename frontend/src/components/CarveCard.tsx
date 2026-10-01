/**
 * The first thing this product wrote to somebody's disk, drawn.
 *
 * Two surfaces, and they are two different sentences:
 *
 *   `CarveCard`         — two files exist, here is what is in them, here is
 *                         what we found when we checked our own work, and here
 *                         is the gate this did NOT open.
 *   `CarveRefusalCard`  — nothing was written, and why.
 *
 * ══ WHY THIS FILE EXISTS AT ALL, MEASURED ══════════════════════════════════
 *
 * The counts are in `lib/engine/datawork.ts`'s header, taken by running
 * `carve_eval_set` on a real file and counting the reply with a transcription
 * of `ResultView.tsx`'s own recursion. The short version: 22 top-level keys, 83
 * rows in a flat table, and on the payload where the split LEAKS it nests seven
 * deep against `MAX_DEPTH` of 3, so 103 of 186 rows do not render — including
 * `leakage.examples`, the actual pairs of rows found on both sides of a file we
 * wrote. That is the chunking sweep's defect one surface later, and it is the
 * whole argument for this file.
 *
 * ══ THE HUE BUDGET, COUNTED: THREE CLAIMS, THREE HUES ══════════════════════
 *
 *   --fits     ONE claim: the leak check this tool ran over its own two files
 *              found nothing AND the two files account for every row read.
 *              That is `ok` in the engine, and `ok` is the conjunction rather
 *              than a mood.
 *   --wont     ONE claim: they do not. A split that leaks is a failed artifact,
 *              not a successful one with a note — `carve_eval_set` sets `ok`
 *              false for exactly this and says why in its own source.
 *   --unknown  Nothing was written. Page 22.2: it is not a bad answer on the
 *              fits-to-won't scale, it is a refusal to be on that scale.
 *   --viz-1    The split bar, and it is the data series rather than a verdict.
 *              Page 06 exists so a picture of a quantity does not spend the
 *              verdict budget.
 *
 * NOTHING ELSE IS COLOURED. No heading, no divider, no file row, no chrome.
 *
 * ══ AND GREEN IS NOT A GATE ════════════════════════════════════════════════
 *
 * This is the trap on this card and it is worth naming before the code. A green
 * pill on a card that just wrote an eval file reads as *the eval set is done*,
 * and it is not: `carve_eval_set` declares `measures=()`, writes nothing to the
 * ledger, and says so in its own reply. So the pill's word is `NO LEAK` — a
 * claim about the check that ran, and the only claim green is making — and
 * `openedNoGate` is drawn in ink, in its own section, ABOVE the fold of any
 * disclosure. `lib/engine/datawork.ts` types that field as a required string so
 * a future edit that drops it does not compile. It is NOT there because the
 * generic table would have folded it — measured, it would not: 299 characters
 * against a 320 fold. It is there because two rows of an eighty-three-row table
 * are two rows of an eighty-three-row table.
 *
 * ══ NOTHING IS --ink-4 ═════════════════════════════════════════════════════
 *
 * Page 03.3: --ink-4 misses both contrast floors and its whole permitted use is
 * disabled controls. "Not a timestamp, not a unit, not a placeholder, NOT A
 * COUNT." Every count, hash, row index and denominator on this card is --ink-3
 * or above. The one exception is the chevron glyph in `Disclosure`, which is
 * chrome and carries no information.
 */

import { useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import type {
  Carve,
  CarveRefusal,
  Excerpt,
  LeakExample,
  WrittenFile,
} from '../lib/engine/datawork';
import type { WireProvenance } from '../lib/engine/types';
import { displayTag } from '../lib/format';
import { Icon, type IconName } from './Icon';
import { ProvenanceTag } from './primitives';
/* ONE ROUNDING RULE ACROSS EVERY BENCH. `basename` and `g3` are the eval card's
   and the retrieval card's; a private copy here would be a second thing to keep
   in step with the engine. */
import { basename, g3 } from './EvalCard';

/* ── the chassis, borrowed rather than re-invented ────────────────────────── */

function Section({
  icon,
  title,
  hint,
  children,
}: {
  icon: IconName;
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="plansec">
      <div className="plansec__head">
        <Icon name={icon} size={14} />
        <span className="plansec__title">{title}</span>
        {hint ? <span className="plansec__hint">{hint}</span> : null}
      </div>
      {children}
    </div>
  );
}

/** One engine field, under the engine's own name. `ResultView`'s rule, kept:
 *  `rows_asked_for_came_from` and `sha256` say what they are, and a renderer
 *  that guessed at English would eventually guess one wrong. */
function Fact({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="runfacts__pair">
      <span className="runfacts__k">{k}</span>
      <span className="runfacts__v mono">{v}</span>
    </div>
  );
}

function Disclosure({
  title,
  summary,
  children,
}: {
  title: string;
  summary: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="runfacts" data-open={open}>
      <button
        type="button"
        className="runfacts__toggle"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <Icon name="chevright" size={12} rotate={open ? 90 : 0} />
        <span>{title}</span>
        <span className="runfacts__sum">{summary}</span>
      </button>
      {open ? <div className="runfacts__body">{children}</div> : null}
    </div>
  );
}

function Pill({
  word,
  hue,
  title,
}: {
  word: string;
  hue: 'fits' | 'wont' | 'unknown';
  title?: string;
}) {
  return (
    <span
      className="vpill vpill--sm"
      style={
        {
          '--v-colour': `var(--${hue})`,
          '--v-wash': `var(--${hue}-wash)`,
          '--v-edge': `var(--${hue}-edge)`,
        } as CSSProperties
      }
      title={title}
    >
      {word}
    </span>
  );
}

/* ── formatting, and none of it invents anything ──────────────────────────── */

const COUNT = new Intl.NumberFormat();

/** Bytes at three significant figures, in the unit a person reads.
 *  Never rounded into meaninglessness and never shown as `0` for absent —
 *  `null` is the engine saying it could not digest a directory. */
function bytes(value: number | null): string {
  if (value === null) return 'not reported';
  if (value < 1024) return `${COUNT.format(value)} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let size = value / 1024;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${g3(size)} ${units[index]}`;
}

/** The first twelve of a sha256, which is what a person compares by eye.
 *  The whole digest is in the manifest and in `title`; a 64-character string
 *  in a 26px row is a string nobody reads either way. */
function shortSha(value: string | null): string {
  return value ? value.slice(0, 12) : 'not reported';
}

/* ── what it wrote ────────────────────────────────────────────────────────── */

/**
 * The two halves as one bar, to the scale of the rows that were read.
 *
 * ONE PICTURE OF ONE QUANTITY, and the reason it is drawn at all is that "30
 * out of 400" is the shape of this operation and a person should not have to do
 * the division. The eval half is `--viz-1`; the training half is the track. The
 * bar is positioned by a FRACTION rather than by a percentage string, which is
 * `EvalCard`'s `ScoreScale` rule: a carve of every row is a real case, and a
 * percentage-positioned segment sits half outside a rounded track.
 *
 * IT IS NOT DRAWN WHEN NOTHING WAS READ. A zero-width bar over a zero
 * denominator is a picture of a division nobody did.
 */
function SplitBar({
  evalRows,
  trainRows,
  rowsRead,
}: {
  evalRows: number;
  trainRows: number;
  rowsRead: number;
}) {
  if (rowsRead <= 0) return null;
  const held = Math.max(0, Math.min(1, evalRows / rowsRead));
  return (
    <div className="carvebar">
      <span
        className="carvebar__track"
        title={`${COUNT.format(evalRows)} held out of ${COUNT.format(rowsRead)} read`}
      >
        <span className="carvebar__held" style={{ '--p': held } as CSSProperties} />
      </span>
      <span className="carvebar__legend">
        <span className="carvebar__key" data-part="eval" />
        <span className="carvebar__word">eval</span>
        <span className="carvebar__n mono">{COUNT.format(evalRows)}</span>
        <span className="carvebar__key" data-part="train" />
        <span className="carvebar__word">train</span>
        <span className="carvebar__n mono">{COUNT.format(trainRows)}</span>
        <span className="carvebar__word carvebar__of">
          of {COUNT.format(rowsRead)} read
        </span>
      </span>
    </div>
  );
}

/** One file that now exists on the person's disk. The path is the whole path in
 *  `title`, because a basename is not something you can go and find. */
function FileRow({ file, role }: { file: WrittenFile; role: string }) {
  return (
    <div className="wrote__row">
      <span className="wrote__role">{role}</span>
      <span className="wrote__name mono" title={file.path}>
        {file.file}
      </span>
      <span className="wrote__rows mono">{COUNT.format(file.rows)}</span>
      <span className="wrote__unit">rows</span>
      <span className="wrote__bytes mono">{bytes(file.bytes)}</span>
      <span className="wrote__sha mono" title={file.sha256 ?? undefined}>
        {shortSha(file.sha256)}
      </span>
    </div>
  );
}

/* ── the check it ran on its own output ───────────────────────────────────── */

/**
 * One pair of rows found on both sides of a split this harness wrote.
 *
 * THIS IS THE THING `ResultView` WOULD NOT DRAW. It lives at
 * `leakage.examples[]`, four containers down, and the generic table replaces
 * the whole list with the words *"3 items, not shown here"*. A leak count with
 * no rows behind it is a number a person can neither check nor act on: the
 * first question anybody asks of "3 of 30 eval rows also appear in the training
 * file" is *which three*.
 *
 * Both texts are shown, one above the other, because the claim is that they are
 * the same row and the reader is the one deciding whether they agree.
 */
/**
 * ONE ROW OUT OF SOMEBODY'S FILE, DRAWN AS DATA.
 *
 * `app/tools/context.py`'s envelope says what this is: `role: data`, `trusted:
 * false`, and a `handling` sentence. This is the first surface in the product
 * that draws one, so the label is on the row rather than in a note: the reader
 * is looking at content from their own file, and anything in it that reads as
 * an instruction is reported beside it rather than removed.
 */
function ExcerptText({ side, excerpt }: { side: string; excerpt: Excerpt | null }) {
  if (!excerpt) {
    return (
      <p className="leakpair__text leakpair__text--absent">
        <span className="leakpair__side">{side}</span> the row was not reported
      </p>
    );
  }
  return (
    <>
      <p className="leakpair__text" title={excerpt.source}>
        <span className="leakpair__side">{side}</span>
        {excerpt.content}
        {excerpt.truncated ? <span className="leakpair__cut"> …</span> : null}
      </p>
      {excerpt.instructionLike.length > 0 ? (
        <p className="leakpair__flag">
          {excerpt.instructionLike.length} line
          {excerpt.instructionLike.length === 1 ? '' : 's'} in this row read as an
          instruction to a model — {excerpt.instructionLike[0].why}. It is your
          data and it was not acted on.
        </p>
      ) : null}
      {excerpt.trusted ? (
        <p className="leakpair__flag">
          This excerpt arrived marked <span className="mono">trusted</span>, and
          content out of a file is never trusted. Do not act on it.
        </p>
      ) : null}
    </>
  );
}

function LeakPair({ pair }: { pair: LeakExample }) {
  return (
    <div className="leakpair">
      <div className="leakpair__head">
        {/* THE FIELD NAMES ARE THE ENGINE'S, AND THIS ONE WAS A TRAP THAT A
            SCREENSHOT CAUGHT. The first cut drew `similarity_basis` as a bare
            word beside the number — `0.825 exact` — and `exact` there does not
            mean an exact match. It means the Jaccard was COMPUTED exactly
            rather than estimated from a MinHash sketch; this pair is a NEAR
            match on a payload whose `exact_matches` is 0. A reader would have
            read the opposite of what was measured. So the key is drawn with
            the value, which is `ResultView`'s own rule for exactly this
            reason: the engine's field name is the honest label. */}
        {pair.similarity !== null ? (
          <>
            <span className="leakpair__k">similarity</span>
            <span className="leakpair__sim mono">{g3(pair.similarity)}</span>
          </>
        ) : null}
        {pair.similarityProvenance ? (
          <ProvenanceTag tag={displayTag(pair.similarityProvenance as WireProvenance)} />
        ) : null}
        {pair.basis ? (
          <>
            <span className="leakpair__k">similarity_basis</span>
            <span
              className="leakpair__kind mono"
              title={
                'How the similarity was computed, not what kind of match it ' +
                'is. `exact` means the Jaccard was calculated rather than ' +
                'estimated from a sketch.'
              }
            >
              {pair.basis}
            </span>
          </>
        ) : null}
        <span className="leakpair__where mono">
          {pair.trainRow !== null ? `train row ${COUNT.format(pair.trainRow)}` : 'train'}
          {' · '}
          {pair.evalRow !== null ? `eval row ${COUNT.format(pair.evalRow)}` : 'eval'}
        </span>
      </div>
      <ExcerptText side="train" excerpt={pair.train} />
      <ExcerptText side="eval" excerpt={pair.evaluation} />
    </div>
  );
}

/* ── the card ─────────────────────────────────────────────────────────────── */

export function CarveCard({ carve }: { carve: Carve }) {
  const check = carve.verification;
  const leaked = check?.leaked ?? null;
  const evaluation = carve.wrote.find((file) => file.path === carve.evalPath);
  const training = carve.wrote.find((file) => file.path === carve.trainPath);

  return (
    <div className="card card--carve" data-ok={carve.ok}>
      <div className="card__head">
        <Icon name="info" />
        <span className="card__kicker">Carved an eval set</span>
        <span className="card__headright">
          {carve.ok ? (
            <Pill
              word="NO LEAK"
              hue="fits"
              title={
                'The leak check this tool ran over its own two files found ' +
                'nothing, and the two files account for every row read. It is ' +
                'not a claim that a gate opened.'
              }
            />
          ) : (
            <Pill
              word={leaked ? 'LEAKED' : 'NOT USABLE'}
              hue="wont"
              title={
                'A split that leaks, or that does not account for every row ' +
                'read, is a failed artifact rather than a successful one with ' +
                'a note. Nothing should be measured against it.'
              }
            />
          )}
        </span>
      </div>

      <div className="card__body">
        <p className="card__text">{carve.summary}</p>

        <Section
          icon="file"
          title="What it wrote"
          hint={carve.into}
        >
          <SplitBar
            evalRows={carve.evalRows}
            trainRows={carve.trainRows}
            rowsRead={carve.rowsRead}
          />
          <div className="wrote">
            {evaluation ? <FileRow file={evaluation} role="eval" /> : null}
            {training ? <FileRow file={training} role="train" /> : null}
          </div>
          {carve.manifestPath ? (
            <p className="card__absent">
              Where it came from and how is written beside them in{' '}
              <span className="mono">{basename(carve.manifestPath)}</span>.
              {carve.formatWrittenWhy ? ` ${carve.formatWrittenWhy}` : ''}
            </p>
          ) : null}
        </Section>

        <Section
          icon="check"
          title="We checked our own work"
          hint={check?.tool ?? 'check_split_leakage'}
        >
          {check ? (
            <>
              <div className="runfacts__body">
                <Fact
                  k="leaked_rows"
                  v={leaked === null ? 'not reported' : COUNT.format(leaked)}
                />
                <Fact
                  k="exact_matches"
                  v={check.exact === null ? 'not reported' : COUNT.format(check.exact)}
                />
                <Fact
                  k="near_matches"
                  v={check.near === null ? 'not reported' : COUNT.format(check.near)}
                />
                <Fact
                  k="threshold"
                  v={check.threshold === null ? 'not reported' : g3(check.threshold)}
                />
              </div>
              {check.thresholdIs ? (
                <p className="card__absent">{check.thresholdIs}</p>
              ) : null}
              <p className="card__absent">{check.partitionIs}</p>
              {check.examples.length > 0 ? (
                <div className="leaks">
                  {check.examples.map((pair, index) => (
                    <LeakPair key={index} pair={pair} />
                  ))}
                </div>
              ) : null}
              {check.notRun.length > 0 ? (
                <p className="card__absent">
                  Not run: {check.notRun.join('; ')}
                </p>
              ) : null}
            </>
          ) : (
            <p className="card__absent">
              This reply carried no verification block, so nothing here can say
              whether the two files overlap. Run{' '}
              <span className="mono">check_split_leakage</span> on them before
              measuring anything against the eval half.
            </p>
          )}
        </Section>

        {/* THE SECTION THIS CARD EXISTS FOR, AND IT IS NOT BEHIND A CHEVRON.
            In the generic table these are two of eighty-three rows, keyed
            `does_not_open_g0` and `grading_is_still_yours`, between
            `distinct_answers` and `wrote`. Here they are the third thing a
            reader meets, in ink, because on a card that has just told somebody
            two files now exist, "this did not count them and it did not open
            the gate" is the sentence that stops the card being read as a gate. */}
        <Section icon="info" title="What this did not do">
          <p className="carvenot">{carve.openedNoGate}</p>
          <p className="carvenot">{carve.gradingIsStillYours}</p>
          {carve.measured.length > 0 ? (
            <p className="card__absent">
              This reply also claims to have recorded{' '}
              <span className="mono">{carve.measured.join(', ')}</span>, and this
              tool declares <span className="mono">measures=()</span>. Do not
              trust either sentence until that is explained.
            </p>
          ) : null}
        </Section>

        {carve.method ? (
          <Disclosure
            title="How it chose"
            summary={
              carve.method.rowsAskedForCameFrom
                ? `${carve.method.rowsAskedFor ?? '?'} rows, from ${
                    carve.method.rowsAskedForCameFrom
                  }`
                : 'the rule, the seed and the column'
            }
          >
            <Fact k="rule" v={carve.method.rule ?? 'not reported'} />
            <Fact
              k="seed"
              v={carve.method.seed === '' ? 'none given' : carve.method.seed}
            />
            <Fact
              k="rows_asked_for"
              v={
                carve.method.rowsAskedFor === null
                  ? 'not reported'
                  : COUNT.format(carve.method.rowsAskedFor)
              }
            />
            <Fact
              k="rows_asked_for_came_from"
              v={carve.method.rowsAskedForCameFrom ?? 'not reported'}
            />
            <Fact k="answer_column" v={carve.method.answerColumn ?? 'not reported'} />
            <Fact k="qualifies" v={carve.method.qualifies} />
            <Fact k="whole_groups_only" v={carve.method.wholeGroupsOnly} />
            <Fact k="rows_are_verbatim" v={carve.method.rowsAreVerbatim} />
            <Fact k="how" v={carve.method.how} />
          </Disclosure>
        ) : null}

        {carve.source ? (
          <Disclosure
            title="Where it came from"
            summary={`${basename(carve.source.path)} — ${COUNT.format(
              carve.source.rowsRead,
            )} rows read`}
          >
            <Fact k="path" v={carve.source.path} />
            <Fact k="format" v={carve.source.format ?? 'not reported'} />
            <Fact k="rows_read" v={COUNT.format(carve.source.rowsRead)} />
            <Fact k="bytes" v={bytes(carve.source.bytes)} />
            <Fact
              k="sha256"
              v={
                <span title={carve.source.sha256 ?? undefined}>
                  {shortSha(carve.source.sha256)}
                </span>
              }
            />
            {carve.source.note ? <Fact k="note" v={carve.source.note} /> : null}
            <Fact k="answer_column" v={carve.answerColumn ?? 'not reported'} />
            <Fact
              k="distinct_answers"
              v={
                carve.distinctAnswers === null
                  ? 'not reported'
                  : COUNT.format(carve.distinctAnswers)
              }
            />
          </Disclosure>
        ) : null}
      </div>
    </div>
  );
}

/* ── the refusal ──────────────────────────────────────────────────────────── */

/**
 * Nothing was written, and why.
 *
 * `ResultView` renders this payload honestly — 7 keys, 2 deep, nothing hidden —
 * and it gets a card anyway, for a reason that is not about shape. A tool that
 * writes files declining to write must say *nothing was written* where a person
 * reads it, in ink, rather than as the fourth row of a key/value table where it
 * is the same size as the error code.
 *
 * The extra fields are drawn under the engine's own names and are NOT a closed
 * table: `would_leave` and `minimum_to_train_on` belong to the starvation
 * refusal, `columns` to the missing-column one, and a list here would go stale
 * the first time a thirteenth reason is added.
 */
export function CarveRefusalCard({ refusal }: { refusal: CarveRefusal }) {
  const rest = refusal.rest.filter(
    ([, value]) => value !== null && value !== undefined && value !== '',
  );
  return (
    <div className="card card--carve card--carverefusal">
      <div className="card__head">
        <Icon name="info" />
        <span className="card__kicker">Nothing was carved</span>
        <span className="card__headright">
          <Pill
            word="NOTHING WRITTEN"
            hue="unknown"
            title={
              'Every check runs before the one call that creates anything, so ' +
              'there is no state in which this refused and also wrote.'
            }
          />
        </span>
      </div>
      <div className="card__body">
        <p className="card__text">{refusal.summary}</p>
        <p className="carvenot">
          Your files are exactly as they were. Nothing was created, nothing was
          moved and nothing was written over.
        </p>
        <div className="runfacts__body">
          <Fact k="error" v={refusal.error} />
          {rest.map(([key, value]) => (
            <Fact
              key={key}
              k={key}
              v={
                typeof value === 'number'
                  ? COUNT.format(value)
                  : typeof value === 'string'
                    ? value
                    : Array.isArray(value)
                      ? value.map(String).join(', ')
                      : JSON.stringify(value)
              }
            />
          ))}
        </div>
      </div>
    </div>
  );
}
