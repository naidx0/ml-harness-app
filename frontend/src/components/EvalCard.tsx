/**
 * The evaluation bench, drawn.
 *
 * Three surfaces live here and they are three different moments:
 *
 *   `EvalRunRow`     — the run while it is happening. Graphite page 26.
 *   `EvalCard`       — one finished run: the score, its resolution, the
 *                      failure buckets, and the rows that actually failed.
 *   `EvalCompareCard`— two runs, paired, and the refusal to declare a winner
 *                      this eval set cannot see.
 *
 * ══ THE SCORE IS NEVER ALONE ═══════════════════════════════════════════════
 *
 * `docs/PRODUCT_SPEC.md`: *"n=30 only resolves differences larger than ~15
 * points. n>=100 to trust a 5-10 point delta. Report the resolution alongside
 * every score."* That is a rule about this file. `evals.py` computes the
 * interval and hands it over; a renderer that prints `73%` and drops the
 * interval has un-reported it, and the product's honesty was spent in the
 * engine for nothing.
 *
 * So the score and its interval are one component — `ScoreScale` — and there is
 * no code path in this file that draws a percentage without drawing what that
 * many rows can see. The interval is not a footnote under the number; it is the
 * number's own width, drawn to scale, and a reader who never reads a word of
 * the card still sees how much of the axis this score occupies.
 *
 * ══ AND THE TRIVIAL BASELINE IS ON THE SAME AXIS ═══════════════════════════
 *
 * `evals.py` measures what answering the single most common label would have
 * scored, on the same rows, and calls it `trivial_baseline`. A sentiment set
 * that is 70% positive gives 70% to a model that says "positive" every time.
 * A score of 73% on that set is not a good score, it is a rounding error above
 * doing nothing, and the only way to know is to see the two on one axis.
 *
 * Page 27.1 already draws this: *"the measured baseline as a dashed
 * `--viz-baseline` rule"*. It is a loss chart there and a score scale here, and
 * it is the same claim — a measurement is meaningless without the reference
 * that says what it beat.
 *
 * ══ WHY THE COMPARISON DOES NOT PUT TWO NUMBERS SIDE BY SIDE ═══════════════
 *
 * This is the part that is easy to get wrong and it is the reason the bench
 * exists. Two percentages in two columns are a claim that one is bigger,
 * whatever the caption underneath says, because the reader has finished reading
 * before the caption starts. A prompt playground shows 73% and 76% and lets you
 * conclude; if the eval cannot resolve three points, letting you conclude is
 * the same defect as inventing a number, arrived at by arithmetic on two real
 * ones.
 *
 * So the layout is not two columns. Both runs are markers on ONE axis, and the
 * largest type on the card is the VERDICT, never the delta. When McNemar
 * separated them the delta gets that slot and gets its colour; when it did not,
 * the slot says "No evidence" in `--unknown` grey and the delta is demoted to a
 * grey annotation inside a drawn noise span. The two scores are 10px mono axis
 * labels in both cases — present, because they are measurements and this
 * product does not hide measurements, but never the biggest thing on screen.
 *
 * That treatment is not invented here. It is Graphite's UNKNOWN verdict, which
 * `DiagnosisCard` already uses for a blocked run: *"the card does not degrade —
 * it changes verdict, and grey is deliberate. Not knowing is an absence, not a
 * problem."* An unresolvable comparison is exactly that shape. The person did
 * nothing wrong, the run did not fail, and the honest answer is a grey one.
 *
 * ══ THE PAIRED STRIP, AND WHY IT IS NOT TWO CONFIDENCE INTERVALS ═══════════
 *
 * The obvious picture for "are these two different" is two Wilson intervals
 * that overlap. It is the wrong picture and it would be this file inventing a
 * second, weaker test than the one the engine ran.
 *
 * `evals.py` says so directly: *"the difference figure is the worst case
 * (p=0.5) for two INDEPENDENT runs; two runs over the same rows are compared
 * pairwise with McNemar's exact test, which needs fewer rows."* Two overlapping
 * Wilson intervals would call a real paired difference unresolvable — the
 * interface refusing a finding the instrument made, which is as dishonest as
 * the reverse and much easier to feel virtuous about.
 *
 * So the picture is McNemar's actual input: the rows that CHANGED. Of the
 * paired rows, how many agreed, how many the new run fixed, and how many it
 * broke. Four changed out of thirty is a picture of nothing happening, and it
 * is the honest reason the verdict is grey.
 */

import { useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import type {
  EvalComparison,
  EvalFailure,
  EvalRefusal,
  EvalReport,
  EvalResolution,
  SelfGraded as SelfGradedFacts,
} from '../lib/engine/evals';
import {
  dominantMode,
  failureModeRoute,
  failureModeWord,
  scoreIsAnOpinion,
} from '../lib/engine/evals';
import type { DisplayTag } from '../lib/engine/types';
import type { EvalItem } from '../lib/transcript';
import { Icon } from './Icon';
import { ProvenanceTag } from './primitives';

/* ── Small shared formatters ──────────────────────────────────────────────
   `pct` is the only place a fraction becomes a percentage in this file. One
   rounding rule, so the axis label and the sentence beside it can never
   disagree by a point — which is the cheapest way to look like you are making
   numbers up.

   EXPORTED, AND THE REASON IS THE SAME RULE ONE LEVEL UP. `RetrievalCard.tsx`
   sets recalls and McNemar p-values beside the ones this file sets — the two
   benches share `evals.resolution_for` and `evals.mcnemar` in the engine — and
   a second copy of `g3` over there would be a second thing to keep in step
   with `retrieval.py`'s own `f"{p:.3g}"`. That is precisely the "same
   measurement rendered twice" defect `g3` was written to close, so the
   function is shared rather than the rule restated. */

export function pct(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function points(value: number, digits = 1): string {
  return `${value.toFixed(digits)}`;
}

/**
 * A p-value, rounded the way the engine rounds it, and for that reason only.
 *
 * `evals.py` writes every p-value into its own sentence with `f"{p:.3g}"`, and
 * this file printed the same number with `toFixed(3)` or `toExponential(1)`.
 * On the comparison this was verified against the card read `p = 0.063` six
 * lines above the engine's sentence reading `p=0.0625`, and the resolved one
 * read `p = 1.9e-6` above `p=1.91e-06`. Neither is wrong and both are the same
 * measurement rendered twice — which this file's own header calls "the cheapest
 * way to look like you are making numbers up", about percentages, three
 * functions above.
 *
 * So this mirrors `%.3g`: three significant figures, exponential below 1e-4 or
 * at or above 1000, trailing zeros stripped. `toPrecision(3)` alone does not —
 * JavaScript only switches to exponential below 1e-7, so 0.0000191 would set as
 * `0.0000191` beside the engine's `1.91e-05`.
 */
export function g3(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  if (value === 0) return '0';
  const magnitude = Math.abs(value);
  if (magnitude < 1e-4 || magnitude >= 1000) {
    /* Python pads the exponent to two digits: 1.91e-06, not 1.91e-6. */
    const [mantissa, exponent] = value.toExponential(2).split('e');
    const sign = exponent.startsWith('-') ? '-' : '+';
    const digits = exponent.replace(/^[+-]/, '').padStart(2, '0');
    return `${trimZeros(mantissa)}e${sign}${digits}`;
  }
  return trimZeros(value.toPrecision(3));
}

function trimZeros(text: string): string {
  return text.includes('.') ? text.replace(/0+$/, '').replace(/\.$/, '') : text;
}

/** A path shown as its filename, with the whole thing on the title. */
export function basename(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

/* ── The run row — Graphite page 26 ───────────────────────────────────────── */

/**
 * One eval run, while it runs. 38px, `--r-10`, four answers left to right.
 *
 * Page 26.1's four questions, answered in this order: is it alive (the dot),
 * is it spending (the elapsed clock, present only while it is), is it going
 * well (the count, and on a finished run the score), does it need me (the
 * state word, in its role colour at 600).
 *
 * THE PROGRESS BAR IS THE ROW'S BACKGROUND, not a separate widget under it. A
 * run row is a row; giving it a second line for a bar would make an eval louder
 * in the transcript than a training job, which streams for hours and gets one
 * line. The fill is `--accent-wash` — the accent is the one hue that is not a
 * verdict, so "how far through" cannot be misread as "how well".
 */
export function EvalRunRow({ item }: { item: EvalItem }) {
  const running = item.state === 'running';
  const share = item.planned > 0 ? Math.min(1, item.graded / item.planned) : 0;

  const ROLE: Record<EvalItem['state'], { word: string; token: string }> = {
    running: { word: 'Evaluating', token: 'st-active' },
    finished: { word: 'Evaluated', token: 'st-done' },
    /* Grey, not red. An interrupted run kept every row it graded and continues
       where it stopped — `evals.py` guarantees it — so nothing was lost and
       nobody failed. Red would claim otherwise. */
    interrupted: { word: 'Stopped', token: 'st-neutral' },
    reused: { word: 'Already run', token: 'st-neutral' },
  };
  const role = ROLE[item.state];

  return (
    <div
      className="evalrow"
      data-state={item.state}
      style={{ '--fill': `${share * 100}%` } as CSSProperties}
    >
      <span className="evalrow__dot" style={{ background: `var(--${role.token})` }} />
      <span className="evalrow__body">
        <span className="evalrow__title" title={item.evalPath ?? undefined}>
          {item.evalPath ? basename(item.evalPath) : `Eval run ${item.runId}`}
        </span>
        <span className="evalrow__meta">
          <span className="evalrow__state" style={{ color: `var(--${role.token})` }}>
            {role.word}
          </span>
          {item.metric ? <> · {item.metric}</> : null}
          {item.model ? <> · {item.model}</> : null}
          {/* A baseline run is worth naming on the row: it is the one kind of
              run that opens a gate, and `evals.py` records only the default
              prompt as the baseline the gates read. */}
          {item.promptIsDefault ? <> · baseline</> : null}
        </span>
      </span>

      {running && item.seconds !== null ? (
        <span className="evalrow__num">{points(item.seconds, 1)}s</span>
      ) : null}

      {item.state === 'reused' ? (
        <span className="evalrow__num evalrow__num--quiet">nothing spent</span>
      ) : (
        <span className="evalrow__num">
          {item.graded}
          <span className="evalrow__of">/{item.planned || '?'}</span>
        </span>
      )}

      {item.state === 'finished' && item.score !== null ? (
        <span className="evalrow__score">{pct(item.score)}</span>
      ) : null}
    </div>
  );
}

/* ── The score scale ──────────────────────────────────────────────────────── */

/**
 * A score, its 95% interval, and the trivial baseline, on one 0–100 axis.
 *
 * The interval is drawn to scale. That is the whole point: at n=30 the band is
 * a third of the axis wide and a reader sees, without reading, that the number
 * is soft. At n=400 it is a sliver. Nothing on this component tells anybody the
 * score is good or bad, and nothing is coloured by how high it is — the only
 * hue is the one that answers a question the engine asked, which is whether the
 * interval clears the trivial baseline.
 */
function ScoreScale({
  score,
  resolution,
  trivial,
  trivialAnswer,
  label,
}: {
  score: number;
  resolution: EvalResolution;
  trivial: number | null;
  trivialAnswer: string | null;
  label: string;
}) {
  const ci = resolution.ci95;
  const low = ci ? ci[0] : score;
  const high = ci ? ci[1] : score;

  /* THE ONE CLAIM THIS COMPONENT MAKES, and it is the engine's arithmetic on
     the engine's own two numbers rather than a judgement: does the 95% interval
     clear what answering the majority label would have scored? If it does not,
     this score has not been shown to beat doing nothing, and that is worth a
     hue because it is a finding and not an opinion. Null when there is no
     trivial baseline to clear — then nothing is coloured at all. */
  const beatsTrivial =
    trivial === null || ci === null ? null : low > trivial;

  return (
    <div className="scale">
      <div className="scale__track">
        {/* The interval, drawn to scale. Under the marker, so the marker is
            never hidden by its own uncertainty. */}
        <span
          className="scale__band"
          style={{ left: `${low * 100}%`, width: `${Math.max(0, high - low) * 100}%` }}
          title={
            ci
              ? `95% confidence: ${pct(low, 1)} to ${pct(high, 1)}`
              : 'no interval — nothing was graded'
          }
        />
        {trivial !== null ? (
          <span
            className="scale__baseline"
            style={{ left: `${trivial * 100}%` }}
            title={
              trivialAnswer
                ? `Answering "${trivialAnswer}" every time scores ${pct(trivial, 1)} on these rows`
                : `The trivial baseline is ${pct(trivial, 1)}`
            }
          />
        ) : null}
        {/* The marker's position is handed over as a 0–1 FRACTION rather than a
            percentage, so the stylesheet can inset it by its own radius. A
            score of 0 or 100 — both of which this bench produces routinely, and
            the baseline run below is one — put a percentage-positioned dot half
            outside the rounded track. Found by looking at a real 0% run. */}
        <span
          className="scale__marker"
          data-beats={beatsTrivial === null ? 'unknown' : String(beatsTrivial)}
          style={{ '--p': score } as CSSProperties}
        />
      </div>

      <div className="scale__axis">
        <span>0%</span>
        <span className="scale__label">{label}</span>
        <span>100%</span>
      </div>

      {trivial !== null ? (
        <p
          className="scale__note"
          data-beats={beatsTrivial === null ? 'unknown' : String(beatsTrivial)}
        >
          <Icon name={beatsTrivial === false ? 'alert' : 'info'} size={13} />
          <span>
            {beatsTrivial === false ? (
              <>
                Answering <b>{trivialAnswer ?? 'the most common label'}</b> to every row
                scores {pct(trivial, 1)} on these same rows, and this score&rsquo;s
                interval does not clear it. On this eval set the model has not been
                shown to beat doing nothing.
              </>
            ) : (
              <>
                Answering <b>{trivialAnswer ?? 'the most common label'}</b> to every row
                scores {pct(trivial, 1)} on these same rows.
              </>
            )}
          </span>
        </p>
      ) : null}
    </div>
  );
}

/** The resolution, in the engine's own sentence and its own numbers. */
function Resolution({ resolution }: { resolution: EvalResolution }) {
  if (resolution.n === 0) {
    return (
      <p className="card__absent">
        Nothing was graded, so there is no score and no interval.
      </p>
    );
  }
  return (
    <div className="reso">
      <div className="reso__row">
        {resolution.halfWidthPoints !== null ? (
          <Figure
            value={`±${points(resolution.halfWidthPoints)}`}
            unit="points"
            caption="95% interval on this score"
          />
        ) : null}
        {resolution.resolvesDifferenceOfPoints !== null ? (
          <Figure
            value={points(resolution.resolvesDifferenceOfPoints, 0)}
            unit="points"
            caption="smallest difference this many rows can see"
          />
        ) : null}
        <Figure value={String(resolution.n)} unit="rows" caption="graded" />
      </div>
      {resolution.says ? <p className="reso__says">{resolution.says}</p> : null}
      {resolution.method ? (
        <p className="reso__method">
          <Icon name="info" size={12} />
          <span>{resolution.method}</span>
        </p>
      ) : null}
    </div>
  );
}

function Figure({
  value,
  unit,
  caption,
}: {
  value: string;
  unit: string;
  caption: string;
}) {
  return (
    <span className="fig">
      <span className="fig__value">
        {value}
        <span className="fig__unit">{unit}</span>
      </span>
      <span className="fig__caption">{caption}</span>
    </span>
  );
}

/* ── The failure buckets ──────────────────────────────────────────────────── */

/**
 * Where the failures went, and where the diagnosis would route them.
 *
 * The interesting part of an eval is not the score, it is which rows failed and
 * why, and this is the "why" at the level the engine acts on. Each bucket is a
 * bar, the count is the number, and the stage `S1_ROUTE_BY_FAILURE_MODE` sends
 * that bucket to is beside it — because a person looking at "38 wrong_format"
 * should be able to see that their diagnosis is about to be a format diagnosis.
 *
 * The bars are `--viz-*`, not verdict hues. A failure bucket is a category, not
 * a judgement, and spending the verdict budget on eight categories is exactly
 * what page 27 says the `--viz-*` namespace exists to prevent.
 */
function Buckets({ report }: { report: EvalReport }) {
  const entries = Object.entries(report.failureHistogram).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, count]) => sum + count, 0) + report.unclassified;
  const dominant = dominantMode(report.failureHistogram);

  if (total === 0) {
    return (
      <p className="card__absent">
        No row was bucketed. Either nothing failed, or the failures carried no
        mode the engine has a route for.
      </p>
    );
  }

  const max = Math.max(...entries.map(([, count]) => count), report.unclassified);

  return (
    <div className="buckets">
      {entries.map(([mode, count], index) => {
        const route = failureModeRoute(mode);
        return (
          <div className="bucket" key={mode}>
            <span className="bucket__name">{failureModeWord(mode)}</span>
            <span className="bucket__bar">
              <span
                className="bucket__fill"
                style={{
                  width: `${(count / max) * 100}%`,
                  background: `var(--viz-${(index % 6) + 1})`,
                }}
              />
            </span>
            <span className="bucket__count">{count}</span>
            <span className="bucket__route">
              {route ? `→ ${route}` : <span className="bucket__unrouted">no route</span>}
            </span>
          </div>
        );
      })}

      {report.unclassified > 0 ? (
        <div className="bucket bucket--unclassified">
          <span className="bucket__name">Unclassified</span>
          <span className="bucket__bar">
            <span
              className="bucket__fill bucket__fill--none"
              style={{ width: `${(report.unclassified / max) * 100}%` }}
            />
          </span>
          <span className="bucket__count">{report.unclassified}</span>
          <span className="bucket__route">
            <span className="bucket__unrouted">no rule matched</span>
          </span>
        </div>
      ) : null}

      {/* THE ENGINE'S OWN THRESHOLD, said out loud. `S1_MIXED_FAILURES` fires
          below 0.5 and its outcome is ACTION__SPLIT_THE_TASK — "one fine-tune
          cannot fix four different problems". Which side of that line a run
          falls on decides the whole rest of the diagnosis, and leaving a reader
          to eyeball it off four bars is leaving them to guess. */}
      {dominant ? (
        <p className="buckets__verdict" data-dominates={String(dominant.dominates)}>
          <Icon name={dominant.dominates ? 'branch' : 'alert'} size={13} />
          <span>
            {dominant.dominates ? (
              <>
                <b>{failureModeWord(dominant.mode)}</b> is {pct(dominant.share)} of the
                bucketed failures, so the diagnosis routes on it
                {failureModeRoute(dominant.mode)
                  ? ` — to ${failureModeRoute(dominant.mode)}`
                  : ''}
                .
              </>
            ) : (
              <>
                No single mode reaches half the failures — the largest is{' '}
                <b>{failureModeWord(dominant.mode)}</b> at {pct(dominant.share)}. The
                engine treats that as more than one problem, and one fine-tune cannot
                fix four different problems.
              </>
            )}
          </span>
        </p>
      ) : null}

      {report.bucketsDecidedBy ? (
        <p className="buckets__by">{report.bucketsDecidedBy}</p>
      ) : null}
    </div>
  );
}

/* ── The rows that failed ─────────────────────────────────────────────────── */

/**
 * The actual failing rows. The reason per-row results are stored at all.
 *
 * A score tells you how much is wrong. Only the rows tell you what is wrong,
 * and the product's whole no-train answer — *"rewrite the system prompt against
 * the failure buckets, name the rule that was broken"* — cannot be acted on by
 * somebody who has not read them.
 *
 * Collapsed by default and one line each, because twenty of these expanded is
 * the wall §9.1 forbids. `expected` and `answer` are the two the eye compares,
 * so they are adjacent and in mono; `input` is what the row asked and sits
 * above them.
 */
/** How many failing rows stand open before the list asks to be unfolded.
 *
 *  MEASURED RATHER THAN CHOSEN BY TASTE: the row is 30px (`--row-h`) and
 *  `run_eval` returns twenty by default, so the uncapped list is a 600px block
 *  inside a card that already runs past a screen. §9.1's rule against a heavy
 *  result in the chat column is about exactly that shape. Eight fills the space
 *  a reader will actually scan before deciding, and the other twelve are one
 *  click and no round trip away — they are already in the payload. */
const FAILURES_SHOWN = 8;

function Failures({ report }: { report: EvalReport }) {
  const [open, setOpen] = useState<number | null>(null);
  const [all, setAll] = useState(false);

  if (report.failures.length === 0) {
    return (
      <p className="card__absent">
        {report.failuresTotal === 0
          ? 'No row failed.'
          : `${report.failuresTotal} rows failed, and none of them came back in this reply.`}
      </p>
    );
  }

  const shown = all ? report.failures : report.failures.slice(0, FAILURES_SHOWN);
  const hidden = report.failures.length - shown.length;

  return (
    <div className="rows">
      {shown.map((row) => (
        <FailingRow
          key={row.rowIndex}
          row={row}
          open={open === row.rowIndex}
          onToggle={() => setOpen(open === row.rowIndex ? null : row.rowIndex)}
        />
      ))}

      {hidden > 0 ? (
        <button type="button" className="rows__all" onClick={() => setAll(true)}>
          <Icon name="chevdown" size={12} />
          Show the other {hidden} failing rows this reply returned
        </button>
      ) : null}

      {report.failuresTotal > report.failures.length ? (
        <p className="rows__more">
          {report.failuresTotal - report.failures.length} more failing rows were not
          returned in this reply. Every one of them is stored; ask for more and the
          bench reads them off disk without asking the model anything.
        </p>
      ) : null}
    </div>
  );
}

function FailingRow({
  row,
  open,
  onToggle,
}: {
  row: EvalFailure;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="frow" data-open={open}>
      <button type="button" className="frow__head" onClick={onToggle} aria-expanded={open}>
        <Icon name="chevright" size={12} rotate={open ? 90 : 0} />
        <span className="frow__index">#{row.rowIndex}</span>
        <span className="frow__input">{row.input}</span>
        {row.failureMode ? (
          <span className="frow__mode">{failureModeWord(row.failureMode)}</span>
        ) : null}
      </button>

      {open ? (
        <div className="frow__body">
          <Pair label="asked" value={row.input} />
          <Pair label="expected" value={row.expected} tone="expected" />
          <Pair label="answered" value={row.answer} tone="answered" />
          <div className="frow__foot">
            {/* WHO GRADED IT is provenance and gets the same treatment every
                other number in this product gets. A row a model graded and a
                row a rule graded are not the same kind of fact. */}
            {row.gradedBy ? (
              <span className="frow__by">
                graded by <b>{row.gradedBy}</b>
              </span>
            ) : null}
            {row.bucketedBy ? (
              <span className="frow__by">
                bucketed by <b>{row.bucketedBy}</b>
              </span>
            ) : null}
            {row.seconds !== null ? (
              <span className="frow__by mono">{points(row.seconds, 2)}s</span>
            ) : null}
            {Object.entries(row.verdicts).map(([name, hit]) => (
              <span className="frow__verdict" key={name} data-hit={String(hit)}>
                {name} {hit ? 'yes' : 'no'}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Pair({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: 'expected' | 'answered';
}) {
  return (
    <div className="frow__pair" data-tone={tone ?? 'plain'}>
      <span className="frow__k">{label}</span>
      <span className="frow__v mono">{value || <i>empty</i>}</span>
    </div>
  );
}

/* ── The report, without chrome ───────────────────────────────────────────── */

/**
 * One eval run, drawn: the score with its interval, what the run rests on, the
 * failure buckets, the rows that failed, and how it was run.
 *
 * SEPARATED FROM `EvalCard` SO THE PANE AND THE CARD ARE ONE IMPLEMENTATION.
 * `docs/ROADMAP.md` Milestone 3 asks for the result as "an artifact in a pane,
 * opened from a one-line badge in the thread. Nothing heavy streams into the
 * transcript; that rule is what keeps the box calm while it is doing a lot, and
 * it is not negotiable" — and then names the risk directly: "a pane that is not
 * ready is the pressure that puts an eval table into the transcript."
 *
 * A second implementation of this body for the pane would be that pressure
 * arriving from the other direction: two surfaces drifting until the pane and
 * the card disagree about the same run. There is one body. The card wraps it in
 * a collapsible `.card`; the pane puts it under the inspector's own 44px header
 * (Graphite page 18.4) and adds a picker for the other runs in the thread.
 */
export function EvalReportBody({ report }: { report: EvalReport }) {
  const score = report.complete ? report.score : report.partialScore;
  const opinion = scoreIsAnOpinion(report);

  return (
    <>
      {/* ── the score ── */}
      <div className="evalhead">
        {score !== null ? (
          <span
            className="evalhead__score"
            data-partial={String(!report.complete)}
            /* A judge's number does not get the ink or the weight a reading
               gets. It keeps the slot, because it is what was asked for and
               hiding it would be its own dishonesty, and it loses the
               authority — the same treatment `--partial` already gets for a
               score from a run that did not finish. */
            data-opinion={opinion ? 'true' : undefined}
          >
            {pct(score)}
          </span>
        ) : (
          <span className="evalhead__score evalhead__score--absent">no score</span>
        )}
        <span className="evalhead__of">
          {report.correct} of {report.graded} rows right
          {report.complete ? null : (
            <>
              {' '}
              · <b>partial</b>, {report.planned - report.graded} still to grade
            </>
          )}
        </span>
        {report.reused ? (
          <span className="evalhead__reused">
            <Icon name="refresh" size={12} />
            answered from the stored run — nothing was spent
          </span>
        ) : null}
      </div>

      {score !== null ? (
        <ScoreScale
          score={score}
          resolution={report.resolution}
          trivial={report.trivialBaselineScore}
          trivialAnswer={report.trivialAnswer}
          label={report.metric}
        />
      ) : null}

      {/* IMMEDIATELY UNDER THE NUMBER, AND NOT FOUR SECTIONS DOWN.
          Page 22.1's order is the argument: what the claim is, what it is
          about, what it RESTS ON, then what it means. A disclosure that a
          model graded itself is what the number rests on, and it used to sit
          below the resolution block — where a reader who had already taken the
          score had passed it. It also used to render nothing at all; see
          `SelfGraded`. */}
      {report.selfGraded ? <SelfGraded self={report.selfGraded} /> : null}

      <Section icon="gauge" title="What this many rows can resolve">
        <Resolution resolution={report.resolution} />
      </Section>

      <Section
        icon="filter"
        title="Where the failures went"
        hint={`${report.failuresTotal} failing rows`}
      >
        <Buckets report={report} />
      </Section>

      <Section
        icon="dataset"
        title="The rows that failed"
        hint="what to write the next prompt against"
      >
        <Failures report={report} />
      </Section>

      <RunFacts report={report} />
    </>
  );
}

/* ── The report card ──────────────────────────────────────────────────────── */

export function EvalCard({ report }: { report: EvalReport }) {
  const [open, setOpen] = useState(true);
  /* IS THIS SCORE A READING, OR A MODEL'S OPINION OF ITS OWN HOMEWORK? The one
     question that decides the header tag, and the card used to not ask it. */
  const opinion = scoreIsAnOpinion(report);

  return (
    <div className="card card--eval" data-open={open} data-opinion={String(opinion)}>
      <div className="card__head">
        <Icon name="chart" />
        <span className="card__kicker">Eval run</span>
        <span className="card__clip" title={report.evalPath}>
          {basename(report.evalPath)}
        </span>
        <span className="card__headright">
          {/* ══ THE TAG IS NOT AUTOMATIC AND USED TO BE ═══════════════════
              A rule-graded run's score IS a reading: a rule this repository
              ships was applied to rows on disk, and MEASURED is the engine's
              own word for that.

              A MODEL-GRADED run's score is not. `run_eval` with
              `metric=model_graded` asks a model whether it was right, and
              `docs/diagnosis_engine.yaml` now declares that number
              `judge_score`, `opinion_of: model` — a fact that "may never carry
              the MEASURED origin ... not because nothing ran, but because what
              ran produced an opinion". A hard-coded MEASURED here was the same
              defect the ledger spent three walls closing, drawn in a pill:
              measured against a live self-graded run, this card printed `30%`
              in 26px under a green MEASURED tag, while `exact_match 0%` and
              `contains 80%` on the identical rows sat behind a chevron.

              DECLARED is the tag, and it is not a compromise. Page 05.4: it
              "takes --unknown grey for exactly the reason UNKNOWN does: it is
              not on the good-to-bad scale, it is off the scale", and it means
              "we did not check, and we are not implying that we did" — which
              is precisely a judge's verdict. The word beside it is what carries
              the rest; see `SelfGraded`. */}
          <ProvenanceTag tag={opinion ? 'DECLARED' : 'MEASURED'} />
          <button
            type="button"
            className="iconbtn"
            aria-label={open ? 'Collapse the eval run' : 'Expand the eval run'}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <Icon name="chevright" size={14} rotate={open ? 90 : 0} />
          </button>
        </span>
      </div>

      {open ? (
        <div className="card__body">
          <EvalReportBody report={report} />
        </div>
      ) : null}
    </div>
  );
}

/**
 * A model graded these answers, said plainly, and the rules' verdict beside it.
 *
 * ══ THIS COMPONENT RENDERED NOTHING, FOR EVERY RUN, SINCE IT WAS WRITTEN ═══
 *
 * It read `self.says`, `self.judge_is_the_same_model` and `self.self_graded`
 * off a `Record<string, unknown>`. `evals._self_graded` has never sent any of
 * those three: it sends `warning`, `is_the_model_that_answered`, `rows_judged`,
 * `judge_model` and `deterministic_scores_on_the_same_rows`. Both guards were
 * therefore always false, the early `return null` always fired, and the one
 * configuration this product exists to survive — a model marking its own
 * homework — displayed with no disclosure whatsoever. Found by running a real
 * `model_graded` eval on a live Ollama and looking at the card. The typed
 * `SelfGraded` reader in `lib/engine/evals.ts` is why the next rename will
 * fail in `tsc` instead of in front of a user.
 *
 * ══ AND THE DETERMINISTIC SCORES ARE THE POINT, NOT A FOOTNOTE ═════════════
 *
 * `evals.py` computes exact-match and contains on the SAME rows of the SAME
 * run for free, and returns them here precisely so the two can be read
 * together — "read the gap between them and the judge before believing the
 * judge". They were on the card already, sixteen rows down, inside a collapsed
 * "How this was run" block, joined into one line with every other metric. That
 * is not beside anything. On the run this was verified against the judge said
 * 30% where `contains` said 80% on the identical answers, and the gap is the
 * whole news.
 *
 * The block is not red. Nothing failed and the person did nothing wrong —
 * `model_graded` exists because some tasks genuinely cannot be graded by a
 * rule, and `docs/diagnosis_engine.yaml` is explicit that this "does not refuse
 * the judge". It is `--unknown` grey, for the reason UNKNOWN is grey: it is
 * off the good-to-bad scale, not low on it.
 */
function SelfGraded({ self }: { self: SelfGradedFacts }) {
  const deterministic = Object.entries(self.deterministic);

  return (
    <div className="judged">
      <div className="judged__head">
        <Icon name="eye" size={13} />
        <span className="judged__title">
          {self.isTheModelThatAnswered ? (
            <>
              This score is <b>{self.judgeModel}</b>&rsquo;s opinion of its own
              answers.
            </>
          ) : (
            <>
              This score is <b>{self.judgeModel}</b>&rsquo;s opinion of another
              model&rsquo;s answers.
            </>
          )}
        </span>
        <span className="judged__rows">
          {self.rowsJudged} row{self.rowsJudged === 1 ? '' : 's'} judged
        </span>
      </div>

      {/* THE RULES' ANSWER ON THE SAME ROWS, side by side with nothing between
          them, because the comparison is the disclosure. */}
      {deterministic.length > 0 ? (
        <div className="judged__rules">
          <span className="judged__ruleslabel">
            the same rows, graded by rule
            <ProvenanceTag tag="MEASURED" />
          </span>
          {deterministic.map(([name, value]) => (
            <span className="judged__rule" key={name}>
              <span className="judged__rulev mono">{pct(value, 1)}</span>
              <span className="judged__rulek">{name}</span>
            </span>
          ))}
        </div>
      ) : (
        <p className="judged__norules">
          No rule could grade these rows, so there is no second reading to put
          beside the judge. That is the case <code>model_graded</code> exists
          for, and it is also the case where the judge is the only thing you
          have.
        </p>
      )}

      {self.warning ? <p className="judged__says">{self.warning}</p> : null}
    </div>
  );
}

/** What was run, against what, under which prompt. The reproducibility block. */
function RunFacts({ report }: { report: EvalReport }) {
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
        <span>How this was run</span>
        <span className="runfacts__sum">
          {report.model ?? 'unknown model'} · {report.metric}
          {report.promptIsDefault ? ' · baseline prompt' : ' · custom prompt'}
        </span>
      </button>
      {open ? (
        <div className="runfacts__body">
          <Fact k="run" v={`#${report.runId}`} />
          <Fact k="file" v={report.evalPath} />
          <Fact k="fields" v={`${report.inputField} → ${report.expectedField}`} />
          <Fact k="rows" v={`${report.graded} graded of ${report.rowsAvailable ?? '?'} available`} />
          <Fact k="model" v={`${report.model ?? '?'} (${report.provider ?? '?'}, ${report.locality ?? '?'})`} />
          <Fact k="metric" v={report.metric} />
          {report.judgeModel ? <Fact k="judge" v={report.judgeModel} /> : null}
          {/* The fingerprint is what makes two runs comparable at all. It is
              the field `compare()` refuses on, so it is worth being able to
              read off two cards and check by eye. */}
          {report.evalFingerprint ? (
            <Fact k="eval fingerprint" v={report.evalFingerprint} />
          ) : null}
          <Fact
            k="prompt"
            v={
              report.promptIsDefault
                ? `${report.prompt ?? ''} — the default, so this run is the baseline the gates read`
                : report.prompt ?? '(none)'
            }
          />
          {Object.keys(report.scores).length > 1 ? (
            <Fact
              k="every metric"
              v={Object.entries(report.scores)
                .map(([name, value]) => `${name} ${pct(value, 1)}`)
                .join(' · ')}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <div className="runfacts__pair">
      <span className="runfacts__k">{k}</span>
      <span className="runfacts__v mono">{v}</span>
    </div>
  );
}

/* ── The comparison ───────────────────────────────────────────────────────── */

/**
 * Two runs, paired. The most important surface on this screen.
 *
 * ══ WHAT SHIPPED, AND WHY THE FIX IS STRUCTURAL RATHER THAN EDITORIAL ══════
 *
 * The card that went out rendered, on one screen, a 26px headline and a paired
 * strip underneath it that disagreed — "-50.0% / A real difference on this
 * eval set / MEASURED" above "6 improved, 0 regressed, p=0.031". `evals.py`
 * has since made that arithmetically impossible: `delta` is now
 * `(improved - regressed) / paired_rows` and cannot contradict the counts.
 *
 * That closed the contradiction and it did NOT close the composition. Driven
 * against a live engine after the engine fix, with a real few-shot challenger
 * on granite4-hermes, the unresolved card still read as a win: a `MEASURED`
 * tag in the header, `A 96.2%` and `B 76.9%` as two ordered markers with a
 * rule drawn between them, and a saturated `--fits` block filling a fifth of
 * the paired strip. Every one of those components is true. The composition is
 * a claim that the eval set has just refused to make.
 *
 * ══ GRAPHITE ALREADY SOLVED THIS, ON PAGES 05 AND 22 ═══════════════════════
 *
 * The book's own answer to "a verdict we cannot stand behind" is UNKNOWN, and
 * the thing to copy is not its grey — it is what it WITHHOLDS. Page 22.2's
 * UNKNOWN feasibility card does not draw a paler budget bar. It draws *no bar
 * at all*, replaced by the words "no measured budget to draw", and it changes
 * its follow-ups to the ones that would get a number. Rule 5: "A verdict
 * resting on anything Defaulted renders as Unknown, whatever the arithmetic
 * said." Rule 3: "It is not a bad answer on the fits-to-won't scale; it is a
 * refusal to be on that scale without a measurement."
 *
 * So the unresolved card here withholds THE ORDERING, which is the only claim
 * a reader takes off a two-marker axis:
 *
 *   the header tag   MEASURED is a claim about the VERDICT in that slot
 *                    (page 22.1 part 2: "What the verdict rests on, at the
 *                    top, before the verdict itself"). An unresolved verdict
 *                    rests on a test that separated nothing, so the slot takes
 *                    the grey NO EVIDENCE pill instead — and the pill survives
 *                    collapse, which is page 22.5's rule that the claim must
 *                    survive compression. Provenance is not dropped: it moves
 *                    onto the paired counts, which really are readings.
 *   the axis         one grey interval spanning both scores inside the wider
 *                    resolution band, not two ordered markers. Both endpoints
 *                    are still printed, so no measurement is hidden; what is
 *                    withheld is which end is which, because that is precisely
 *                    what this eval set could not tell you.
 *   the strip        the changed rows are hatched grey rather than --fits
 *                    green. The hue stays on the 18x3px legend keys, where it
 *                    labels a count; it leaves the AREA, which was the largest
 *                    coloured object on a card whose verdict is grey.
 *
 * ══ AND THE OPPOSITE FAILURE, CHECKED RATHER THAN ASSUMED AWAY ═════════════
 *
 * A card that can never say "yes, this is better" is exactly as useless as one
 * that always does, and it is the easier mistake to feel virtuous about. The
 * RESOLVED branch below is untouched: the delta keeps the big type, keeps its
 * hue, the axis keeps both markers and the accent span, and the strip keeps
 * --fits and --wont. Verified against a resolved comparison in the same
 * session (+66.7%, 20 improved, 0 regressed, p=1.9e-06) so that this file is
 * known to still be able to conclude.
 */
export function EvalCompareCard({ comparison }: { comparison: EvalComparison }) {
  const [open, setOpen] = useState(true);
  const resolved = comparison.resolved;
  const a = comparison.scoreAgainst;
  const b = comparison.score;

  return (
    <div className="card card--compare" data-open={open} data-resolved={String(resolved)}>
      <div className="card__head">
        <Icon name="branch" />
        <span className="card__kicker">Compared</span>
        <span className="card__clip">
          run {comparison.runId} against run {comparison.against}
        </span>
        <span className="card__headright">
          {/* PAGE 22.1 PART 2: the tag in this slot is a claim about the
              VERDICT, not about the numbers under it. A resolved comparison's
              verdict IS a paired reading and takes MEASURED. An unresolved
              one's verdict is that there is no reading of a difference, and
              MEASURED there is the same error as painting UNKNOWN amber — it
              ranks "we could not tell" on the scale it has just declined to be
              on. The grey pill takes the slot instead, and it is what survives
              collapse (22.5: the UNKNOWN card is the one that KEEPS its tag,
              because the tag is the reason for the verdict). */}
          {resolved ? (
            <ProvenanceTag tag="MEASURED" />
          ) : (
            <span
              className="vpill vpill--sm"
              style={
                {
                  '--v-colour': 'var(--unknown)',
                  '--v-wash': 'var(--unknown-wash)',
                  '--v-edge': 'var(--unknown-edge)',
                } as CSSProperties
              }
              title="McNemar's exact test could not separate these two runs on this eval set."
            >
              NO EVIDENCE
            </span>
          )}
          <button
            type="button"
            className="iconbtn"
            aria-label={open ? 'Collapse the comparison' : 'Expand the comparison'}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <Icon name="chevright" size={14} rotate={open ? 90 : 0} />
          </button>
        </span>
      </div>

      {open ? (
        <div className="card__body">
          {/* ══ THE VERDICT OWNS THE BIG TYPE ══════════════════════════════
              On a resolved comparison the delta is the headline and carries
              its colour. On an unresolved one the headline is the WORD "No
              evidence" in grey and the delta does not appear in this block at
              all — because a `+19.2%` set in 26px is a result, whatever is
              written under it. */}
          <div
            className="verdicthead"
            data-resolved={String(resolved)}
            data-down={resolved && comparison.delta < 0 ? '' : undefined}
          >
            {resolved ? (
              <>
                <span className="verdicthead__delta" data-down={comparison.delta < 0 ? '' : undefined}>
                  {comparison.delta > 0 ? '+' : ''}
                  {pct(comparison.delta, 1)}
                </span>
                <span className="verdicthead__word">
                  <Icon
                    name={comparison.delta >= 0 ? 'check' : 'alert'}
                    size={14}
                  />
                  A real difference on this eval set
                </span>
              </>
            ) : (
              <>
                <span className="verdicthead__unknown">No evidence</span>
                <span className="verdicthead__word">
                  <Icon name="eye" size={14} />
                  {comparison.changed === 0
                    ? 'Not one row changed its verdict'
                    : 'This eval set cannot tell these two apart'}
                </span>
              </>
            )}
          </div>

          {/* ── one axis: two markers when resolved, one interval when not ── */}
          <TwoOnOneAxis comparison={comparison} a={a} b={b} />

          {/* ── the paired strip: McNemar's actual input ── */}
          <Section
            icon="run"
            title="The rows that changed"
            hint="what the test actually reads"
            /* PROVENANCE DOES NOT LEAVE THE CARD WHEN IT LEAVES THE HEADER.
               Invariant 3 is about numbers, and these counts ARE readings —
               each one is a row that went from wrong to right on disk — so the
               tag lands here, on the thing it is true of, rather than over a
               verdict it is not true of. */
            tag={resolved ? null : 'MEASURED'}
          >
            <PairedStrip comparison={comparison} />
          </Section>

          {/* THE ROWS ONLY ONE RUN GRADED, AND THE NUMBER THAT USED TO BE THE
              HEADLINE. Drawn as its own marked block rather than left inside
              the prose, where `+29.5%` was sitting in the same ink as the
              sentence around it with no tag on it at all. */}
          <AggregateNote comparison={comparison} />

          {/* ══ THE ENGINE'S OWN SENTENCE, KEPT AND DEMOTED ═══════════════
              `says` is `compare()`'s verbatim summary and it is five sentences
              long, because when it was written it was carrying the whole card:
              the delta, the counts, the p-value, the row mismatch and the
              aggregate. All five now have a structural home above it — the
              legend, the keys, the test line, the mismatch block, the
              aggregate figure — so printing it at --ink-2 12px directly under
              them made the card state every one of its facts twice, at equal
              volume. That is the verbatim-echo defect this file already warns
              about two hundred lines down, and the first cut of this fix
              committed it.

              IT IS NOT MOVED BEHIND A CHEVRON. Page 14.6's rule is that a fact
              is never ONLY in a surface you can miss; this one is not the only
              home for anything, so hiding it would be permitted — but it is
              the engine's authoritative wording and the one place the argument
              is made in full prose, and a person who does not trust the card
              should be able to read it without hunting. So it stays in the
              primary reading and loses the weight instead: labelled as the
              engine's own summary, at --ink-3 and 11px, where it reads as a
              transcript of the instrument rather than as a fifth version of
              the headline. */}
          {comparison.says ? (
            <div className="compare__says">
              <span className="compare__saysk">the bench&rsquo;s own summary</span>
              <p className="compare__saysv">{comparison.says}</p>
            </div>
          ) : null}

          {/* THE ACTION, and it is a number rather than "collect more data".

              IT DOES NOT RESTATE THE SENTENCE ABOVE IT. The first cut of this
              block read "Grade 46 more rows and ask again — …", and `says`
              already ends with the words *"Grade 46 more rows and ask again."*
              One instruction, printed twice, six lines apart. That is the
              verbatim-echo defect this lane was sent to fix, reproduced inside
              the fix, which is worth leaving on the record: the pull toward
              restating a sentence you have just been handed is not something
              only a model does.

              So the block carries the FIGURE and the caveat `says` does not
              have — that `rows_that_would_resolve_this_delta` is the unpaired
              worst case, which `evals.py` is explicit about: *"reporting the
              smaller paired figure here would require knowing how many rows are
              going to change, which is the thing being measured."* Rendering
              that number without saying which of the two it is would be
              over-promising by a factor nobody could see. */}
          {!resolved && comparison.rowsThatWouldResolveThisDelta !== null ? (
            <div className="compare__next">
              <Icon name="plus" size={13} />
              <Figure
                value={String(
                  Math.max(
                    0,
                    comparison.rowsThatWouldResolveThisDelta - comparison.pairedRows,
                  ),
                )}
                unit="more rows"
                caption="worst case, for two independent runs"
              />
              <span className="compare__caveat">
                A paired re-run over these same rows needs fewer — how many fewer
                depends on how many rows change, which is the thing being measured.
              </span>
            </div>
          ) : null}

          <ComparePrompts comparison={comparison} />
        </div>
      ) : null}
    </div>
  );
}

/**
 * The two paired scores on ONE axis — and, when the test resolved nothing, as
 * ONE object rather than two.
 *
 * ══ THE RESOLVED PICTURE ═══════════════════════════════════════════════════
 *
 * Two markers, labelled A and B, with a solid accent span between them. The
 * gap is real, McNemar said so, and the picture is allowed to say which run is
 * which and which way round they are.
 *
 * ══ THE UNRESOLVED PICTURE, AND WHY IT IS NOT THE SAME PICTURE IN GREY ═════
 *
 * Two labelled markers with a rule drawn between them are an ORDERING. A
 * reader takes "A is to the right of B" off that shape before reading a word,
 * and on an unresolved comparison the ordering is the one thing the instrument
 * declined to give them. Greying it does not stop it being read; measured in
 * the running app, the grey version still read as a win at a glance, because
 * `A 96.2%` sat visibly right of `B 76.9%` and the noise band behind them was
 * a wash two steps off the track.
 *
 * So the unresolved axis draws ONE interval covering both scores, inside the
 * resolution band, with no A and no B and no direction. Both endpoints are
 * printed on it — nothing measured is hidden, and this product does not hide
 * measurements — but they are printed as the ENDS OF ONE RANGE, which is
 * exactly what two runs the eval cannot separate are.
 *
 * This is page 22.2's move, not a new one: the UNKNOWN feasibility card does
 * not draw a fainter budget bar, it declines to draw the bar and says so. Here
 * the axis declines to draw the ordering and says so, and which run is which
 * is still one click away in the run facts, where it is a fact and not a
 * picture.
 *
 * THE BAND IS THE ENGINE'S NUMBER AND NOT THIS FILE'S. `resolvesDifference-
 * OfPoints` is the worst case for two INDEPENDENT runs, which `evals.py` is
 * explicit about; it is drawn because it is the honest width of "what this
 * many rows can see", and the note beside it says which of the two figures it
 * is rather than letting a reader assume the smaller paired one.
 */
function TwoOnOneAxis({
  comparison,
  a,
  b,
}: {
  comparison: EvalComparison;
  a: number | null;
  b: number | null;
}) {
  if (a === null || b === null) {
    return (
      <p className="card__absent">
        One of these runs has no score, so there is nothing to place on an axis.
      </p>
    );
  }

  const left = Math.min(a, b);
  const right = Math.max(a, b);
  const resolved = comparison.resolved;

  /* The noise span. On an unresolved comparison the honest width is not the gap
     — it is what this many rows CAN see, centred on the pair, which is by
     definition wider than the gap. Read off the engine's own resolution rather
     than computed here. */
  const noise = comparison.resolution.resolvesDifferenceOfPoints;
  const mid = (a + b) / 2;
  const noiseLow = noise !== null ? Math.max(0, mid - noise / 200) : left;
  const noiseHigh = noise !== null ? Math.min(1, mid + noise / 200) : right;

  if (!resolved) {
    return (
      <div className="axis2" data-resolved="false">
        <div className="axis2__track">
          {noise !== null ? (
            <span
              className="axis2__noise"
              style={{
                left: `${noiseLow * 100}%`,
                width: `${(noiseHigh - noiseLow) * 100}%`,
              }}
              title={`Two runs on ${comparison.pairedRows} rows cannot be told apart unless they differ by about ${points(noise, 0)} points`}
            />
          ) : null}

          {/* ONE OBJECT. No A, no B, no direction — the two scores are the two
              ends of a range this eval set cannot order.

              POSITIONED BY FRACTION, NOT BY PERCENTAGE, for the reason the
              markers already are and which this element reintroduced: two runs
              that both scored 100% put a percentage-positioned interval hard
              against the right edge with its 3px minimum hanging outside the
              track. Seen in the running app on a real 4-row pair at 100/100 —
              which is not an exotic case, it is what `changed === 0` looks like
              on a small slice. The stylesheet insets it by the same amount it
              insets a tick. */}
          <span
            className="axis2__both"
            style={{ '--lo': left, '--span': right - left } as CSSProperties}
            title={
              left === right
                ? `Both runs scored ${pct(left, 1)} on the ${comparison.pairedRows} rows they both graded`
                : `Both runs scored between ${pct(left, 1)} and ${pct(right, 1)} on the ${comparison.pairedRows} rows they both graded`
            }
          />
        </div>

        <div className="axis2__axis">
          <span>0%</span>
          {/* NOT "76.9%–76.9%". Two runs that scored identically on the rows
              they both graded — which is the `changed === 0` case, and the
              commonest unresolved one — have one number between them, and
              printing it as a range would be the interface implying a spread
              it just measured to be zero. */}
          <span className="axis2__legend axis2__legend--unordered">
            both runs,{' '}
            {left === right ? pct(left, 1) : `${pct(left, 1)}–${pct(right, 1)}`} on{' '}
            {comparison.pairedRows} paired rows
          </span>
          <span>100%</span>
        </div>

        <p className="axis2__note">
          {noise === null ? (
            <>
              The two scores are {points(Math.abs(comparison.delta) * 100)} points
              apart. Which run is the higher one is not drawn, because this eval
              set did not establish an order.
            </>
          ) : (
            <>
              The band is what {comparison.pairedRows} rows can see &mdash;{' '}
              {points(noise, 0)} points wide, and the two scores sit{' '}
              {points(Math.abs(comparison.delta) * 100)} points apart inside it.
              Which one is higher is not drawn, because that is the claim this
              eval set could not make.
            </>
          )}
        </p>
      </div>
    );
  }

  return (
    <div className="axis2" data-resolved="true">
      <div className="axis2__track">
        <span
          className="axis2__span"
          style={{ left: `${left * 100}%`, width: `${(right - left) * 100}%` }}
        />

        {/* Fractions, not percentages, for the same reason as the score scale:
            a run at 0% or 100% is ordinary here — the baseline below scored
            zero — and a percentage-positioned marker puts its tick and its
            label half outside the plot. The stylesheet insets both. */}
        <span className="axis2__marker axis2__marker--b" style={{ '--p': a } as CSSProperties}>
          <span className="axis2__tick" />
          <span className="axis2__tag">B {pct(a, 1)}</span>
        </span>
        <span className="axis2__marker axis2__marker--a" style={{ '--p': b } as CSSProperties}>
          <span className="axis2__tick" />
          <span className="axis2__tag">A {pct(b, 1)}</span>
        </span>
      </div>

      <div className="axis2__axis">
        <span>0%</span>
        <span className="axis2__legend">
          A · run {comparison.runId} &nbsp;·&nbsp; B · run {comparison.against}
        </span>
        <span>100%</span>
      </div>
    </div>
  );
}

/**
 * The rows only one run graded, and the aggregate difference that would have
 * been reported if nobody had noticed.
 *
 * NOTHING IS DRAWN WHEN BOTH RUNS GRADED THE SAME ROWS, which is the ordinary
 * case and where the aggregate difference IS the paired one. A block that
 * appeared every time would be noise, and a reader who sees it on every card
 * stops reading it on the one card where it matters.
 *
 * When they differ it is a real finding and it gets a real block. The number in
 * it — `+29.5%` on the run this was verified against, where the honest paired
 * answer is `+19.2%` — is the number that used to be the headline, and it was
 * previously visible only as characters inside a paragraph, in the same ink as
 * the words around it, carrying no tag. Invariant 3 does not have an exception
 * for numbers set in running text.
 *
 * ══ WHY THE FIGURE IS NOT ALONE IN HERE ANY MORE ══════════════════════════
 *
 * MEASURED IN THE RUNNING APP, on the live fixture: a champion at 26/30 and a
 * few-shot challenger at 26/26 where not one of the 26 shared rows changed.
 * The card's own reported difference is `+0.0%` and the aggregate is `+13.3%`,
 * and this block drew the aggregate at 17px/600 while the reported figure sat
 * in `PairedStrip` at 11px/450 — both in the same `--ink-3`, 110px apart.
 * The demoted number was **the largest number on the card**, one and a half
 * times the type size of the number it is subordinate to, and the only thing
 * above it was the WORD "No evidence", which is not a number at all.
 *
 * Greying it was argued from the resolved card, where the headline delta takes
 * `--fits`/`--wont` at 26px and grey really is a demotion. On the UNRESOLVED
 * card the headline is grey too, so the tonal argument buys nothing and size
 * decides — and size was pointing the wrong way.
 *
 * The fix is page 22.3's move rather than another step of grey. The UNKNOWN
 * feasibility card does not draw a fainter budget bar; it declines to draw the
 * bar and says "no measured budget to draw", because a quantity that is not on
 * the scale is not put on the scale at reduced weight. So the aggregate stops
 * being a lone figure — a shape that reads as a headline however small it is
 * set — and becomes the SECOND ROW of a two-row ledger whose first row is the
 * reported difference. Subordinate then means something structural and
 * checkable: same column, one size step down, one ink step lighter, second in
 * reading order, and the row set that produced it named beside it.
 *
 * It also answers the question this card could not answer before: the two
 * denominators are now stacked one above the other, so a reader who did not
 * know the runs graded different rows can see it in the figures themselves and
 * not only in the sentence above them.
 */
function AggregateNote({ comparison }: { comparison: EvalComparison }) {
  const aggregate = comparison.aggregate;
  if (comparison.sameRows) return null;
  if (!aggregate) return null;

  const only = aggregate.onlyTheOtherGradedCount + aggregate.onlyThisRunGradedCount;
  if (only === 0 && aggregate.difference === null) return null;

  return (
    /* `data-headline` is what the ledger below sizes itself against, and it is
       read from the CARD's own state rather than set by hand, so the rule "the
       aggregate is never larger than the reported difference" cannot come
       apart from whether there IS a reported difference in big type. */
    <div className="mismatch" data-headline={comparison.resolved ? 'figure' : 'word'}>
      <p className="mismatch__head">
        <Icon name="alert" size={13} />
        <span>
          These two runs did not grade the same rows.{' '}
          <b>
            {only} row{only === 1 ? '' : 's'}
          </b>{' '}
          {only === 1 ? 'is' : 'are'} excluded from both sides, so everything
          above is measured on the {comparison.pairedRows} rows they share.
        </span>
      </p>

      <div className="mismatch__rows">
        {aggregate.onlyTheOtherGradedCount > 0 ? (
          <RowsOnly
            label={`only run ${comparison.against} graded`}
            rows={aggregate.onlyTheOtherGraded}
            total={aggregate.onlyTheOtherGradedCount}
          />
        ) : null}
        {aggregate.onlyThisRunGradedCount > 0 ? (
          <RowsOnly
            label={`only run ${comparison.runId} graded`}
            rows={aggregate.onlyThisRunGraded}
            total={aggregate.onlyThisRunGradedCount}
          />
        ) : null}
      </div>

      {aggregate.difference !== null ? (
        /* ══ THE TWO SUBTRACTIONS, IN ONE COLUMN ═══════════════════════════
           BOTH FIGURES OR NEITHER. A contrast needs two terms, and printing
           only the disqualified one — which is what this block did — leaves
           the reader to hold the reported figure in their head from 110px
           further up the card. That is not a demotion, it is a memory test,
           and the number that wins a memory test is the one on screen.

           This is the one place the reported difference is allowed to appear
           twice, and it is not the verbatim echo this file warns about
           elsewhere: the second printing is not a restatement of the first, it
           is the other half of a comparison that means nothing with one half
           missing. On the unresolved card it does not appear twice at all —
           `PairedStrip` stands its caption down when this ledger renders. */
        <div className="subtract">
          <p className="subtract__head">
            <span className="subtract__headk">the two subtractions</span>
            <ProvenanceTag tag="MEASURED" />
          </p>

          <div className="subtract__row" data-role="reported">
            <span className="subtract__lab">reported</span>
            <span className="subtract__v mono">
              {comparison.delta > 0 ? '+' : ''}
              {pct(comparison.delta, 1)}
            </span>
            <span className="subtract__on">
              on the {comparison.pairedRows} rows both runs graded
            </span>
          </div>

          <div className="subtract__row" data-role="aggregate">
            <span className="subtract__lab">also true</span>
            <span className="subtract__v mono">
              {aggregate.difference > 0 ? '+' : ''}
              {pct(aggregate.difference, 1)}
            </span>
            {/* ONE CLAUSE. The engine's own `says` below carries the argument
                in full, and an earlier cut printed a four-line paragraph
                restating it directly above — the verbatim-echo defect this
                card's own comments already warn about, committed inside the
                fix for it. What this needs to say is the one thing the number
                cannot say for itself: which two row sets it spans. */}
            <span className="subtract__on">
              run {comparison.runId} over its own {aggregate.rows} &middot; run{' '}
              {comparison.against} over its own {aggregate.rowsAgainst} &mdash;{' '}
              <b>not</b> a difference between them
            </span>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** A short list of row indexes, capped, with the count when it was capped. */
function RowsOnly({
  label,
  rows,
  total,
}: {
  label: string;
  rows: number[];
  total: number;
}) {
  return (
    <span className="mismatch__only">
      <span className="mismatch__onlyk">{label}</span>
      <span className="mismatch__onlyv mono">
        {rows.length ? rows.map((row) => `#${row}`).join(' ') : `${total} rows`}
        {rows.length && total > rows.length ? ` +${total - rows.length}` : ''}
      </span>
    </span>
  );
}

/**
 * The rows that changed, drawn as the counts McNemar reads.
 *
 * Unchanged rows carry no information about the difference and are correctly
 * ignored by the test — but they are drawn, in grey, because the RATIO is the
 * point: four moving out of thirty is a picture of nothing happening, and the
 * grey mass is what makes the coloured slivers read as small.
 */
function PairedStrip({ comparison }: { comparison: EvalComparison }) {
  const { pairedRows, improved, regressed, changed, pValue } = comparison;
  const agreed = Math.max(0, pairedRows - changed);
  /** Does the mismatch ledger print the reported delta? The same three facts
   *  `AggregateNote` branches on, in one expression, so the caption below and
   *  the ledger cannot both claim it or both drop it. */
  const ledgerDrawsTheDelta =
    !comparison.sameRows &&
    comparison.aggregate !== null &&
    comparison.aggregate.difference !== null;
  const width = (count: number) => (pairedRows > 0 ? (count / pairedRows) * 100 : 0);
  /* THE HUE LEAVES THE AREA AND STAYS ON THE KEY.
     `--fits` on the improved SEGMENT was the largest coloured object on an
     unresolved card — a fifth of the strip, saturated green, directly under a
     grey headline reading "No evidence". Page 27.3 permits a verdict hue
     inside a plot in exactly one case: when it IS a claim about the run, which
     is why "diverged" may take --wont. "5 rows improved" on a comparison the
     test could not resolve is not a claim this card is making, so the segment
     hatches in --unknown instead. The COUNT keeps its colour on the 18x3px
     legend key below, where page 05.1's rule applies — colour is the second
     channel and the word and the number are the first — so nothing measured is
     hidden and nothing unmeasured is asserted. */
  const resolved = comparison.resolved;

  return (
    <div className="paired" data-resolved={String(resolved)}>
      <div className="paired__strip" role="img" aria-label={`${agreed} rows agreed, ${improved} improved, ${regressed} regressed of ${pairedRows}`}>
        <span
          className="paired__seg paired__seg--agreed"
          style={{ width: `${width(agreed)}%` }}
          title={`${agreed} rows gave the same verdict in both runs`}
        />
        <span
          className="paired__seg paired__seg--improved"
          style={{ width: `${width(improved)}%` }}
          title={`${improved} rows the new run got right and the old one got wrong`}
        />
        <span
          className="paired__seg paired__seg--regressed"
          style={{ width: `${width(regressed)}%` }}
          title={`${regressed} rows the old run got right and the new one got wrong`}
        />
      </div>

      <div className="paired__keys">
        <Key token="edge" label="agreed" count={agreed} />
        <Key token="fits" label="improved" count={improved} />
        <Key token="wont" label="regressed" count={regressed} />
      </div>

      <div className="paired__test">
        <span className="paired__p">p = {g3(pValue)}</span>
        {comparison.test ? <span className="paired__method">{comparison.test}</span> : null}
      </div>

      {/* THE DELTA, ON THE UNRESOLVED CARD, IN THE ONE PLACE IT CANNOT BE READ
          AS A HEADLINE: beside the counts it is arithmetically identical to.
          `evals.py` made `delta` exactly `(improved - regressed) / paired_rows`
          so that the two can never disagree; printing it here, at the size of
          a caption, is the honest way to keep a real measurement on the card
          without giving it the slot that means "result".

          IT STANDS DOWN WHEN THE MISMATCH LEDGER IS DRAWING IT, and only then.
          `AggregateNote` renders on exactly `!sameRows`, and there the reported
          figure is needed as the first row of the two-subtraction ledger — the
          term the aggregate is subordinate TO. Printed in both places it would
          be the same measurement twice on one card, which is the defect this
          file keeps warning about; the condition below is the same one the
          ledger renders on, so the two can never both be on or both be off.

          THE CONDITION IS THE LEDGER'S OWN, not a paraphrase of it. `sameRows`
          alone would be a paraphrase and would be wrong in one real case: an
          engine that sent no `aggregate` block at all — which `readAggregate`
          answers with `null`, and which the reader deliberately does not
          invent — draws no ledger, and standing down against `sameRows` would
          delete the only printing of a real measurement. `ledgerDrawsTheDelta`
          is computed from the same three facts the ledger branches on. */}
      {!resolved && !ledgerDrawsTheDelta ? (
        <p className="paired__delta">
          <span className="mono">
            = {comparison.delta > 0 ? '+' : ''}
            {pct(comparison.delta, 1)}
          </span>{' '}
          over {pairedRows} paired rows
        </p>
      ) : null}
    </div>
  );
}

function Key({
  token,
  label,
  count,
}: {
  token: string;
  label: string;
  count: number;
}) {
  return (
    <span className="paired__key">
      <span className="paired__swatch" style={{ background: `var(--${token})` }} />
      <span className="paired__count">{count}</span>
      <span className="paired__label">{label}</span>
    </span>
  );
}

/** The two prompts, when they differ. The thing that was actually changed. */
function ComparePrompts({ comparison }: { comparison: EvalComparison }) {
  const [open, setOpen] = useState(false);
  const a = comparison.prompts[String(comparison.runId)] ?? null;
  const b = comparison.prompts[String(comparison.against)] ?? null;
  if (a === null && b === null) return null;
  if (a === b) {
    return (
      <p className="compare__same">
        <Icon name="info" size={13} />
        <span>Both runs used the same prompt.</span>
      </p>
    );
  }
  return (
    <div className="runfacts" data-open={open}>
      <button
        type="button"
        className="runfacts__toggle"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <Icon name="chevright" size={12} rotate={open ? 90 : 0} />
        <span>The two prompts</span>
        <span className="runfacts__sum">what changed between the runs</span>
      </button>
      {open ? (
        <div className="runfacts__body">
          <Fact k={`A · run ${comparison.runId}`} v={a ?? '(none)'} />
          <Fact k={`B · run ${comparison.against}`} v={b ?? '(none)'} />
        </div>
      ) : null}
    </div>
  );
}

/* ── The refusal ──────────────────────────────────────────────────────────── */

/**
 * `compare()` declining, drawn as an answer rather than an error.
 *
 * Refusing to subtract two scores measured on two different eval sets is the
 * product working, so this is `--unknown` grey and not `--wont` red. Nothing
 * failed. The engine declined to do arithmetic that would have produced a
 * number meaning nothing, which is the same act as "do not train anything" at a
 * smaller scale.
 */
export function EvalRefusalCard({ refusal }: { refusal: EvalRefusal }) {
  const WORD: Record<EvalRefusal['error'], string> = {
    different_eval_sets: 'Not comparable',
    incomplete_run: 'Not finished',
    /* NOT "no overlap" and not "empty". Two runs over one eval set on disjoint
       slices of it have not been compared at all, which is a different thing
       from having been compared and found equal — and the sentence the engine
       replaced said "not one of the 0 rows changed its verdict", which read as
       agreement. */
    no_shared_rows: 'Nothing to pair',
  };
  const disjoint = refusal.error === 'no_shared_rows';

  return (
    <div className="card card--evalrefusal">
      <div className="card__head">
        <Icon name="alert" />
        <span className="card__kicker">Comparison declined</span>
      </div>
      <div className="card__body">
        <div className="card__headline">
          <span
            className="vpill"
            style={
              {
                '--v-colour': 'var(--unknown)',
                '--v-wash': 'var(--unknown-wash)',
                '--v-edge': 'var(--unknown-edge)',
              } as CSSProperties
            }
          >
            {WORD[refusal.error]}
          </span>
        </div>
        <p className="card__text">{refusal.detail}</p>

        {/* WHICH ROWS EACH RUN GRADED ALONE. Without it "score both over an
            overlapping set of rows" is advice; with it, it is an instruction
            the person can carry out. This is Graphite page 22.2's rule for the
            UNKNOWN card applied to a refusal: "when the product cannot answer,
            the useful actions are the ones that get it a number". */}
        {disjoint &&
        (refusal.onlyThisRunGraded.length || refusal.onlyTheOtherGraded.length) ? (
          <div className="mismatch__rows mismatch__rows--refusal">
            {refusal.onlyTheOtherGraded.length ? (
              <RowsOnly
                label="one run graded"
                rows={refusal.onlyTheOtherGraded}
                total={refusal.onlyTheOtherGraded.length}
              />
            ) : null}
            {refusal.onlyThisRunGraded.length ? (
              <RowsOnly
                label="the other graded"
                rows={refusal.onlyThisRunGraded}
                total={refusal.onlyThisRunGraded.length}
              />
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/* ── Section wrapper, matching the proposal card's `.plansec` rhythm ─────── */

function Section({
  icon,
  title,
  hint,
  tag,
  children,
}: {
  icon: 'gauge' | 'filter' | 'dataset' | 'run' | 'chart' | 'eye';
  title: string;
  hint?: string;
  /** A provenance tag on the SECTION, for the case where the card's header
   *  cannot carry one because the header's tag would be a claim about a
   *  verdict rather than about these numbers. See `EvalCompareCard`. */
  tag?: DisplayTag | null;
  children: ReactNode;
}) {
  return (
    <div className="plansec">
      <div className="plansec__head">
        <Icon name={icon} size={14} />
        <span className="plansec__title">{title}</span>
        {hint ? <span className="plansec__hint">{hint}</span> : null}
        {tag ? (
          <span className="plansec__tag">
            <ProvenanceTag tag={tag} />
          </span>
        ) : null}
      </div>
      {children}
    </div>
  );
}
