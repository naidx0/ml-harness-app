/**
 * Generated rows, drawn — and the two things about them that must never be a
 * disclosure somebody has to open.
 *
 * `docs/PHASES.md` on Phase 2: *"this is the most dangerous feature in the
 * product. Everything downstream of fabricated data is a statement about a
 * distribution we invented."* Three surfaces here, in the order a person meets
 * them:
 *
 *   `SynthesisCard`         — rows were written, every one of them is tagged,
 *                             and no gate opened.
 *   `VerificationSampleCard`— here is the tenth of them you have to read.
 *   `VerificationCard`      — here is what you said, and what it permits.
 *
 * ══ WHAT IS ABOVE THE FOLD, AND WHY IT IS NOT A CHOICE ═════════════════════
 *
 * Two sentences are drawn in ink, in their own row, before any disclosure:
 * **every row carries the tag**, and **nothing here opened a gate**. They are
 * the two properties that separate honest amplification from fabrication at
 * scale, and a person reading this card is looking at a file that did not exist
 * a second ago with a number on it that is bigger than their real data. That is
 * exactly the moment to say what the number is not.
 *
 * `CarveCard` learned this the expensive way and its header carries the
 * argument: a green pill on a card that just wrote a file reads as *the eval
 * set is done*. So there is no green here at all. The only hue on the synthesis
 * card is `--viz-1` on the bar, which is a quantity rather than a verdict, and
 * `--wont` on the one thing that really is a failure: a checked sample that
 * found wrong rows.
 *
 * ══ NOTHING ON THESE CARDS IS COMPUTED HERE ════════════════════════════════
 *
 * Every count is an engine field. The one derived number is `rowsWritten /
 * answeredRows`, drawn as the amplification the person asked for, and it is
 * drawn as a ratio of two shown numbers rather than as a figure on its own.
 */

import type { CSSProperties, ReactNode } from 'react';
import type {
  Synthesis,
  VerificationRecord,
  VerificationSample,
  WrittenFile,
} from '../lib/engine/datawork';
import { Icon, type IconName } from './Icon';
import { basename } from './EvalCard';

const COUNT = new Intl.NumberFormat();

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

function Fact({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="runfacts__pair">
      <span className="runfacts__k">{k}</span>
      <span className="runfacts__v mono">{v}</span>
    </div>
  );
}

/** The same six-column row `CarveCard` draws, and it is six on purpose.
 *
 *  FOUND BY LOOKING, and it is the third defect in this repository's history
 *  that every assertion missed and one screenshot caught. `.wrote__row` is
 *  `display: contents`, so its cells are laid out by the `.wrote` GRID above
 *  it - without that parent the six spans become six blocks and the row comes
 *  apart down the card, with "200" against the right edge and "rows" on the
 *  line below it. The cells are also all six rather than the four this card
 *  needs, because a grid with four cells in a six-column track is the same
 *  defect one step smaller. */
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

/** Bytes and a short digest, borrowed from `CarveCard` rather than re-derived:
 *  both say "not reported" rather than 0 or an em dash, because a file whose
 *  size nobody read and a file of zero bytes are different things. */
function bytes(value: number | null): string {
  if (value === null) return 'not reported';
  const units = ['B', 'kB', 'MB', 'GB'];
  let size = value;
  let unit = 0;
  while (size >= 1000 && unit < units.length - 1) {
    size /= 1000;
    unit += 1;
  }
  return `${size >= 100 || unit === 0 ? Math.round(size) : size.toPrecision(3)} ${units[unit]}`;
}

function shortSha(value: string | null): string {
  return value ? value.slice(0, 12) : 'not reported';
}

/* ── the card ─────────────────────────────────────────────────────────────── */

export function SynthesisCard({ synthesis }: { synthesis: Synthesis }) {
  const { rowsWritten, answeredRows, rowsRead } = synthesis;

  return (
    <div className="card card--synth">
      <div className="card__body">
        <p className="card__text">{synthesis.summary}</p>

        {/* THE TWO SENTENCES. Not a disclosure, not a footnote, not a tooltip. */}
        <div className="synth__laws">
          <p className="synth__law">
            <Icon name="dataset" size={13} />
            <span>
              Every one of these {COUNT.format(rowsWritten)} rows carries{' '}
              <code>synthetic: true</code>, the row it was sampled from, and the
              seed that chose it. The tag is on the row and travels with it.
            </span>
          </p>
          <p className="synth__law">
            <Icon name="gauge" size={13} />
            <span>
              Nothing here opened a gate. These rows are not an eval set and
              cannot become one: the harness refuses to measure{' '}
              <code>eval_size_n</code> off a file it generated, and refuses to
              train on one until you have read a sample of it.
            </span>
          </p>
        </div>

        <Section
          icon="chart"
          title="What was amplified"
          hint={`seed ${synthesis.seed || '(none)'}`}
        >
          <div className="synth__bar">
            <span
              className="synth__source"
              style={
                {
                  '--p': rowsWritten
                    ? Math.max(0.02, Math.min(1, answeredRows / rowsWritten))
                    : 1,
                } as CSSProperties
              }
            />
          </div>
          <div className="runfacts__body">
            <Fact k="rows_read" v={COUNT.format(rowsRead)} />
            <Fact k="answered_rows" v={COUNT.format(answeredRows)} />
            <Fact k="rows_written" v={COUNT.format(rowsWritten)} />
            <Fact k="answer_column" v={synthesis.answerColumn ?? '—'} />
          </div>
          <p className="synth__note">
            {COUNT.format(answeredRows)} real answered rows became{' '}
            {COUNT.format(rowsWritten)} by sampling with replacement. The answer
            on every written row was copied from its source row and never
            generated — this amplifies the shape of what you have, and invents no
            new right answers.
          </p>
        </Section>

        {synthesis.wrote.length > 0 ? (
          <Section icon="file" title="Written">
            <div className="wrote">
              {synthesis.wrote.map((file) => (
                <FileRow key={file.path} file={file} role="synthetic" />
              ))}
            </div>
            {synthesis.manifestPath ? (
              <p className="card__absent">
                Where these rows came from, which seed chose each one and the
                sentence saying this opened no gate are written beside them in{' '}
                <span className="mono">{basename(synthesis.manifestPath)}</span>.
              </p>
            ) : null}
          </Section>
        ) : null}

        <p className="synth__next">
          Before anything trains on this file, a person has to read{' '}
          <strong>10%</strong> of it — the ledger&rsquo;s own recipe. Run{' '}
          <code>draw_verification_sample</code> on it.
        </p>
      </div>
    </div>
  );
}

export function VerificationSampleCard({ sample }: { sample: VerificationSample }) {
  return (
    <div className="card card--synth">
      <div className="card__body">
        <p className="card__text">{sample.summary}</p>
        <Section icon="eye" title="Your turn" hint={basename(sample.samplePath)}>
          <div className="runfacts__body">
            <Fact k="rows_written" v={COUNT.format(sample.rowsWritten)} />
            <Fact k="rows_total" v={COUNT.format(sample.rowsTotal)} />
            <Fact k="seed" v={sample.seed || '(none)'} />
          </div>
          <p className="synth__note">
            Open that file, put <code>yes</code> or <code>no</code> in the{' '}
            <code>verified</code> column of every row — yes if the answer on that
            row is right for that input — and run{' '}
            <code>record_verification</code> on it. Nothing here judged anything:
            this harness cannot tell whether a generated answer is right, which is
            the whole reason you are in this loop.
          </p>
        </Section>
      </div>
    </div>
  );
}

export function VerificationCard({ record }: { record: VerificationRecord }) {
  const wrong = record.wrong > 0;
  return (
    <div className="card card--synth" data-wrong={wrong}>
      <div className="card__body">
        <p className="card__text">{record.summary}</p>
        <Section icon="commit" title="What you recorded" hint={basename(record.dataset)}>
          <div className="runfacts__body">
            <Fact k="judged" v={COUNT.format(record.judged)} />
            <Fact k="wrong" v={COUNT.format(record.wrong)} />
          </div>
          {wrong ? (
            <p className="synth__note synth__note--wont">
              Nothing will train on this file while the sample says some of it is
              wrong. Amplification copies answers verbatim, so a wrong generated
              row is a wrong source row — and the rest of this file came from the
              same source.
            </p>
          ) : (
            <p className="synth__note">
              {basename(record.dataset)} can be trained on. This record is filed
              beside the data and is bound to its exact bytes: rewrite the file
              and it stops applying, because it would no longer be about what you
              read.
            </p>
          )}
        </Section>
      </div>
    </div>
  );
}
