/**
 * The retrieval bench, drawn.
 *
 * Two surfaces, and they are two different questions:
 *
 *   `RetrieverRecallCard` — one index, scored alone. Is the right passage in
 *                           the top k, how much does that many questions
 *                           resolve, and was anything actually recorded.
 *   `ChunkingSweepCard`   — N indexes over one corpus, scored on one eval set,
 *                           and the refusal to crown any of them.
 *
 * ══ WHAT WAS HERE BEFORE, AND WHAT IT COST ═════════════════════════════════
 *
 * Nothing. Measured before this file existed: no file under `frontend/src`
 * referenced `measure_retriever_recall` or `compare_chunkings`, so both fell
 * to `ResultView`, the generic key/value table. A real sweep is 40 top-level
 * keys and 614 rows once flattened, and it nests six deep against
 * `ResultView`'s `MAX_DEPTH` of 3 — so `comparisons`, which holds every
 * pairwise test the sweep ran, rendered as the words *"28 items, not shown
 * here"*, and the sentence the engine spends a paragraph earning — "NO
 * EVIDENCE that any of these 8 chunking settings differs from any other on
 * this eval set" — was a cell among six hundred.
 *
 * `ResultView` is not replaced and is right about the things it is right
 * about: keys are the engine's own field names in mono, never prettified into
 * English, and an absent value says it is absent. Both rules are kept here —
 * every `Fact` row below is the engine's own key, and a null renders as its
 * own sentence and never as `0`.
 *
 * ══ THE STACK IS EvalCard's ScoreScale, N TIMES, ON ONE AXIS ═══════════════
 *
 * `EvalCard.tsx`'s own docstring is the brief: *"the score and its interval
 * are ONE COMPONENT … the interval is not a footnote under the number; it is
 * THE NUMBER'S OWN WIDTH, DRAWN TO SCALE, and a reader who never reads a word
 * of the card still sees how much of the axis this score occupies."*
 *
 * A sweep is that from one to N. Every setting's recall is a marker on a
 * shared 0–100 axis with its own 95% interval drawn under it, and eight bands
 * that overlap are visible before a word is read. That is the shape, and it is
 * borrowed from this system rather than invented.
 *
 * ══ AND THE OVERLAP IS NOT ALLOWED TO BE THE VERDICT ═══════════════════════
 *
 * This is the part that is easy to get wrong, and `EvalCard.tsx` already warns
 * about it in the opposite direction: *"Two overlapping Wilson intervals would
 * call a real paired difference unresolvable — the interface refusing a
 * finding the instrument made."* `evals.py` says the same thing: the interval
 * is the worst case for two INDEPENDENT runs, and these settings are scored on
 * THE SAME QUESTIONS, which McNemar's exact test compares pairwise and needs
 * far fewer rows for.
 *
 * So the stack draws what each setting's own number is worth, and it says so
 * in a note under the axis; the SEPARATION is drawn separately, out of the
 * engine's own pairwise tests, in `PairGrid`. On the sweep this file was
 * verified against the two agree — eight settings, nothing separated, bands
 * overlapping — but they are two pictures of two different claims and the card
 * never lets the geometry stand in for the test.
 *
 * ══ NOTHING IS CROWNED, AND THAT IS A LAYOUT RULE ══════════════════════════
 *
 * `sweep_chunkings` sets `crowned` to `None` on every path, including the one
 * where four of six comparisons separate, and `lib/engine/retrieval.ts` has no
 * field for it at all. This file honours that with geometry rather than with a
 * sentence:
 *
 *   ORDER      The stack is in the order the caller passed the settings, never
 *              sorted by recall. `_re_measuring` says why in the engine's own
 *              words: *"the rows are in the order the caller gave, not sorted
 *              by recall, for the same reason the curve is."* A sort by score
 *              is a ranking whatever the caption says.
 *   HIGHLIGHT  No row is emphasised, ever. `highest_recall_here` arrives as a
 *              LIST and is drawn only inside a block that carries the engine's
 *              own "AND THAT IS NOT A WINNER" beside it, so the number cannot
 *              appear without the sentence.
 *   MARKS      A setting something BEAT is marked, because a test said so. A
 *              setting nothing beat is not marked, because "nothing was shown
 *              to beat it" and "it is the best" are different claims and only
 *              the first one was measured. The asymmetry is the point.
 *   HUE        No marker on the stack is coloured. There is no claim to make
 *              about any one setting, and a hue would be one.
 */

import { useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import type {
  AnswerInPassage,
  ChunkingSweep,
  Levers,
  MintedFact,
  RecallPoint,
  RecallReport,
  RecallRow,
  SweepPair,
  SweepSetting,
} from '../lib/engine/retrieval';
import { Icon, type IconName } from './Icon';
import { ProvenanceTag } from './primitives';
/* ONE ROUNDING RULE ACROSS BOTH BENCHES. See the note above `pct` in
   `EvalCard.tsx`: `g3` mirrors Python's `%.3g`, which is how both `evals.py`
   and `retrieval.py` write every p-value they put in a sentence. A private
   copy here would be a second thing to keep in step with the engine. */
import { basename, g3, pct, points } from './EvalCard';

/* ── the chassis ──────────────────────────────────────────────────────────
   Sections take the proposal card's `.plansec` rhythm, which the eval card
   already borrowed, so a retrieval card and an eval card in one thread have
   one rhythm rather than two. */

function Section({
  icon,
  title,
  hint,
  tag,
  children,
}: {
  icon: IconName;
  title: string;
  hint?: string;
  /** A provenance tag on the SECTION, for the case where the card's header
   *  cannot carry one because the header's pill is a claim about a verdict
   *  rather than about these numbers. `EvalCompareCard` makes the same move. */
  tag?: 'MEASURED' | null;
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

/** One engine field, under the engine's own name. `ResultView`'s rule, kept:
 *  `passage_chars` and `posting_rows` carry their units in their names and a
 *  renderer that guessed at English would eventually guess a unit wrong. */
function Fact({ k, v }: { k: string; v: string }) {
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

/** A grey pill. Every verdict this bench reaches is an absence — no evidence,
 *  nothing crowned, nothing compared, nothing built — and page 22.2's rule for
 *  UNKNOWN is why they are all the same grey: *"it is not a bad answer on the
 *  fits-to-won't scale; it is a refusal to be on that scale without a
 *  measurement."* */
function GreyPill({ word, title }: { word: string; title?: string }) {
  return (
    <span
      className="vpill vpill--sm"
      style={
        {
          '--v-colour': 'var(--unknown)',
          '--v-wash': 'var(--unknown-wash)',
          '--v-edge': 'var(--unknown-edge)',
        } as CSSProperties
      }
      title={title}
    >
      {word}
    </span>
  );
}

/* ── the stack ────────────────────────────────────────────────────────────── */

/**
 * N recalls and N intervals on ONE axis, in the caller's own order.
 *
 * The grid is four columns wide and the axis row sits in the same grid, so
 * 0% and 100% land exactly under the ends of every track. `display: contents`
 * on each row is what keeps that true without hard-coding a label width — a
 * sweep can carry a `5000/200` label beside a `120/20` one.
 *
 * THE MARKER IS POSITIONED BY A FRACTION AND NOT BY A PERCENTAGE, which
 * `EvalCard`'s `ScoreScale` records the reason for: a recall of 0 or 1 is
 * ordinary here — the sweep this was verified against has settings at exactly
 * 1.0 — and a percentage-positioned dot sits half outside a rounded track.
 * The stylesheet insets it by its own radius.
 */
function RecallStack({
  settings,
  label,
  beatenBy,
}: {
  settings: SweepSetting[];
  label: string;
  /** Which settings something was shown to beat. Only ever read for a
   *  non-empty entry: see the header note on MARKS. */
  beatenBy: Record<string, string[]>;
}) {
  return (
    <div className="rstack" data-kind="settings">
      {settings.map((row) => {
        const ci = row.resolution.ci95;
        const low = ci ? ci[0] : row.recall;
        const high = ci ? ci[1] : row.recall;
        const beaten = beatenBy[row.setting] ?? [];
        return (
          <div className="rrow" key={row.setting} data-beaten={beaten.length > 0}>
            <span
              className="rrow__label mono"
              title={
                row.passageChars !== null
                  ? `passage_chars ${row.passageChars}, passage_overlap ${row.passageOverlap ?? '?'}` +
                    (row.indexName ? ` — index ${row.indexName}` : '')
                  : undefined
              }
            >
              {row.setting}
            </span>
            <span className="rrow__track">
              {/* NO BAND WHEN THERE IS NO INTERVAL. `min-width: 1px` on the
                  band exists so a real but very tight interval still draws;
                  applied to an ABSENT one it would put a hairline at the
                  recall and invite it to be read as an interval of nothing,
                  which is the most confident thing this card could say. */}
              {ci ? (
                <span
                  className="rrow__band"
                  style={{
                    left: `${low * 100}%`,
                    width: `${Math.max(0, high - low) * 100}%`,
                  }}
                  title={`95% confidence: ${pct(low, 1)} to ${pct(high, 1)} on ${row.of} questions`}
                />
              ) : null}
              <span
                className="rrow__marker"
                style={{ '--p': row.recall } as CSSProperties}
                title={`${row.hits} of ${row.of}`}
              />
            </span>
            <span className="rrow__count mono">
              {row.hits}
              <span className="rrow__of">/{row.of}</span>
            </span>
            <span className="rrow__pct mono">{pct(row.recall, 1)}</span>
            {/* THE INTERVAL AS A NUMBER, ON THE ROW, IN INK.
                `EvalCard`'s docstring is quoted at the top of this file: the
                interval may never be a footnote. On this card it was worse
                than a footnote — `resolution.half_width_points` and `ci_95`
                appeared in the DOM only inside `title=` on the band, so the
                only way to read the interval of any of these twelve settings
                was to hover it. A tooltip is not a reading a person can be
                shown; it does not print, it does not survive a screenshot,
                and it does not exist on a touch screen.

                The number is the engine's own `half_width_points`, rounded
                for display and nothing else. It is NOT recomputed from
                `ci_95` when the engine did not send it: a renderer deriving
                half an interval is a second instrument nobody validated, and
                on the day the two disagree this card would be the one
                lying. */}
            <span className="rrow__ci mono">
              {row.resolution.halfWidthPoints !== null ? (
                <>±{row.resolution.halfWidthPoints.toFixed(1)}</>
              ) : (
                <span className="rrow__cinone">no interval</span>
              )}
            </span>
          </div>
        );
      })}

      <div className="rrow rrow--axis">
        <span className="rrow__label" />
        <span className="rstack__axis">
          <span>0%</span>
          <span className="rstack__label">{label}</span>
          <span>100%</span>
        </span>
        <span />
        <span />
        {/* The unit for the column above, in the axis row, so the ± figures
            are not a bare number in a column with no name. */}
        <span className="rrow__ciunit">95% ± pts</span>
      </div>
    </div>
  );
}

/* ── the pairwise tests ───────────────────────────────────────────────────── */

/**
 * The one comparison two settings are in, whichever way round it is stored.
 *
 * `compare_hit_vectors` emits each pair once with the first label as `a`, in
 * the caller's order. This looks both ways round anyway rather than trusting
 * that order to have survived, and it is a scan rather than a keyed lookup on
 * purpose: the family is at most sixty-six pairs, so the whole grid is a few
 * thousand string comparisons, and building a composite key means choosing a
 * separator that no label can contain.
 *
 * THE FIRST CUT CHOSE ONE AND IT COST SOMETHING REAL. The separator was a NUL
 * written as the byte itself, and `grep` then classified this whole source
 * file as BINARY and refused to search it. `tsc` passed, the build passed and
 * every screenshot was correct; only a lint that read the bytes found it.
 * There is nothing left here to get wrong.
 */
function pairBetween(
  pairs: SweepPair[],
  first: string,
  second: string,
): SweepPair | null {
  return (
    pairs.find(
      (pair) =>
        (pair.a === first && pair.b === second) ||
        (pair.a === second && pair.b === first),
    ) ?? null
  );
}

/**
 * Every pair, drawn as the count McNemar actually reads.
 *
 * A pair's p-value comes from the questions whose verdict CHANGED between the
 * two settings and from nothing else — the rows they agree on carry no
 * information about the difference and are correctly absent from the test. So
 * the picture is that count, on a scale, against the floor the family imposes.
 *
 * THE DASHED RULE IS PAGE 27.1's MEASURED BASELINE, and it is the whole point
 * of the grid. `min_discordant_for` is arithmetic and not a rule of thumb:
 * two-sided exact McNemar over m discordant rows cannot produce a p below
 * 2**(1-m), so at this family's tightest Holm threshold no pair can separate
 * at all until at least that many questions change. A grid where every bar
 * stops short of the rule is a sweep that could not have concluded anything,
 * and that is visible without reading a number.
 *
 * NO HUE MARKS A SEPARATED PAIR. "These two settings differ" is a real finding
 * and it is not on the fits-to-won't scale, so it is carried by form — the
 * cell takes a `--edge-strong` ring and its count sets in `--ink-1` — and by
 * the word in the legend. Page 05.1: colour is the second channel; the word
 * and the number are the first.
 */
function PairGrid({
  pairs,
  settings,
  floor,
  paired,
}: {
  pairs: SweepPair[];
  settings: string[];
  /** `min_changed_questions_at_this_family_size`. Null when the engine did not
   *  send one, and then no rule is drawn rather than a rule at a guess. */
  floor: number | null;
  /** `compared_questions`, off the payload. NOT `pairs[0].agreed +
   *  pairs[0].changed`, which is what this scale used to be: the engine sends
   *  the number, and a renderer that re-derives it is a second instrument
   *  nobody validated. They agree on every sweep captured so far, which is
   *  exactly why the day they disagree nobody would notice. */
  paired: number;
}) {
  /* ══ THE SCALE IS THE PAIRED QUESTIONS, NOT THE LARGEST BAR ══════════════
     The first cut scaled every bar to `max(changed, floor)`, and drawn against
     a real sweep it put the dashed rule exactly on the right-hand end of every
     cell, where it read as a cell border rather than as a threshold — and it
     made a pair that changed 6 of 40 look like a bar most of the way across.
     Both are the same defect: a bar chart whose full width means "the biggest
     thing here" is a picture of the ranking, not of the quantity.
     `compared_questions` is the number of questions every setting scored,
     which is the honest denominator and is the same number the denominator
     section below prints. Six of forty then draws as six of forty, which is
     what `EvalCard`'s paired strip means by "a picture of nothing happening".

     The floor is still allowed to widen it: a family whose threshold needs
     more changed questions than there are questions would otherwise put the
     rule off the end of the track. */
  const span = Math.max(paired, floor ?? 0, 1);
  const rows = settings.slice(1);
  const columns = settings.slice(0, -1);

  return (
    <div className="pgrid__scroll">
      {/* THE COLUMN COUNT COMES FROM THE DATA, so the template has to be
          written here: CSS `repeat()` does not take a custom property for its
          count in any shipping engine. The per-cell minimum is a token. */}
      <div
        className="pgrid"
        style={{
          gridTemplateColumns: `auto repeat(${columns.length}, minmax(var(--sp-40), 1fr))`,
        }}
      >
        <span className="pgrid__corner" />
        {columns.map((column) => (
          <span className="pgrid__col mono" key={column}>
            {column}
          </span>
        ))}

        {rows.map((row, rowIndex) => (
          <PairRowCells
            key={row}
            row={row}
            rowIndex={rowIndex}
            columns={columns}
            pairs={pairs}
            span={span}
            floor={floor}
          />
        ))}
      </div>

      {/* NO SWATCH. The first cut drew a 40px sample of the bar with the rule
          on it, and once the scale became the paired questions the sample's
          fill was 11% of 40px — four pixels, which is not a legend, it is a
          stray dash. Every cell in the grid above already shows its own bar
          under its own number, so the sample was a second drawing of a thing
          the reader is looking at. The sentence carries the key. */}
      <p className="pgrid__key">
        <span>
          the bar is how many of the <b className="mono">{paired}</b> questions
          changed verdict between those two settings — the rows they agree on
          carry no information about the difference and McNemar does not read
          them
          {floor !== null ? (
            <>
              . The dashed rule is <b className="mono">{floor}</b>, the fewest
              changed questions the exact test can reach this family&rsquo;s
              tightest threshold with, whatever the two recalls look like
            </>
          ) : null}
          . A ringed cell is a pair the test separated.
        </span>
      </p>
    </div>
  );
}

function PairRowCells({
  row,
  rowIndex,
  columns,
  pairs,
  span,
  floor,
}: {
  row: string;
  rowIndex: number;
  columns: string[];
  pairs: SweepPair[];
  span: number;
  floor: number | null;
}) {
  return (
    <>
      <span className="pgrid__row mono">{row}</span>
      {columns.map((column, columnIndex) => {
        if (columnIndex > rowIndex) return <span className="pgrid__empty" key={column} />;
        /* `compare_hit_vectors` emits each pair once, first label as `a`. Read
           both ways round rather than assuming the caller's order survived. */
        const pair =
          pairBetween(pairs, column, row);
        if (!pair) return <span className="pgrid__empty" key={column} />;
        return (
          <span
            className="pcell"
            key={column}
            data-separated={pair.separated}
            title={pair.says ?? undefined}
          >
            <span className="pcell__n mono">{pair.changed}</span>
            <span className="pcell__bar">
              {/* ZERO DRAWS NOTHING. `min-width: 1px` keeps a one-question bar
                  visible; on a pair where not one question changed it drew a
                  hairline that says "a little", and "not one row changed its
                  verdict" is a different claim the engine makes in those
                  words. */}
              {pair.changed > 0 ? (
                <span
                  className="pcell__fill"
                  style={{ width: `${(pair.changed / span) * 100}%` }}
                />
              ) : null}
              {floor !== null ? (
                <span
                  className="pcell__rule"
                  style={{ left: `${(floor / span) * 100}%` }}
                />
              ) : null}
            </span>
          </span>
        );
      })}
    </>
  );
}

/** The same tests as rows, for a family too small to be a grid. Two settings
 *  is one comparison, and a one-cell matrix is a worse drawing of it than a
 *  sentence. */
function PairRows({ pairs }: { pairs: SweepPair[] }) {
  return (
    <div className="prows">
      {pairs.map((pair) => (
        <div className="prow" key={`${pair.a}-${pair.b}`} data-separated={pair.separated}>
          <span className="prow__pair mono">
            {pair.a} <span className="prow__v">vs</span> {pair.b}
          </span>
          <span className="prow__changed mono">
            {pair.changed}
            <span className="prow__of">/{pair.agreed + pair.changed}</span>
          </span>
          <span className="prow__label">changed verdict</span>
          <span className="prow__p mono">p = {g3(pair.p)}</span>
          {/* "of 0.05" read as though the p-value were a fraction of the
              threshold. The two numbers are a measurement and the line it had
              to clear, and the word between them has to say so. */}
          {pair.holmThreshold !== null ? (
            <span className="prow__thr">
              against a threshold of{' '}
              <span className="mono">{g3(pair.holmThreshold)}</span>
            </span>
          ) : null}
          {pair.says ? <p className="prow__says">{pair.says}</p> : null}
        </div>
      ))}
    </div>
  );
}

/* ── the blocks that carry a refusal ─────────────────────────────────────── */

/**
 * What the ledger took, and — far more often here — what it did not.
 *
 * `compare_chunkings` declares `measures=()`, checked at registration, so its
 * `measured` is `[]` on every path that exists. `measure_retriever_recall` can
 * stamp, and refuses to on seven different shapes of run. Both states are this
 * one block: grey, because nothing failed, and never absent, because "so what
 * do I write down" is the question a person asks next.
 */
function Stamp({
  measured,
  notMeasured,
  recorded,
}: {
  measured: MintedFact[];
  notMeasured: string;
  recorded?: string | null;
}) {
  if (measured.length === 0 && !notMeasured) return null;
  const took = measured.length > 0;
  return (
    <div className="stamp" data-took={took}>
      <div className="stamp__head">
        <Icon name="key" size={13} />
        <span className="stamp__title">
          {took ? 'What was recorded' : 'Nothing was recorded'}
        </span>
        {took ? <ProvenanceTag tag="MEASURED" /> : <GreyPill word="NO FACT" />}
      </div>
      {measured.map((fact) => (
        <div className="stamp__fact" key={fact.fact}>
          <span className="stamp__k mono">{fact.fact}</span>
          <span className="stamp__v mono">
            {fact.value === null ? 'not reported' : fact.value}
          </span>
          {fact.how ? <p className="stamp__how">{fact.how}</p> : null}
        </div>
      ))}
      {recorded ? <p className="stamp__recorded mono">{recorded}</p> : null}
      {notMeasured ? <p className="stamp__why">{notMeasured}</p> : null}
    </div>
  );
}

/**
 * The four levers `NO_TRAIN__FIX_RETRIEVAL` names, and which one this is.
 *
 * ON THE CARD, NOT DROPPED AS PROSE. The engine puts this block on every reply
 * it produces — including every refusal — and says why: *"a person told to fix
 * their retriever deserves to know which quarter of the job this is."* So the
 * four names and which side each is on are in the primary reading, at full
 * size; only the paragraph on WHY each is impossible and WHO can pull it is a
 * click away, which is page 14.6's line — a fact is never ONLY in a surface
 * you can miss, and each of these is named twice over.
 */
function LeverBlock({ levers }: { levers: Levers }) {
  const total = 1 + levers.weCannotPull.length;
  return (
    <Section
      icon="sliders"
      title="The four levers"
      hint={`1 of ${total} is ours — the other ${levers.weCannotPull.length} each need a model this harness does not ship`}
    >
      <div className="levers">
        <LeverRow ours lever="chunking" body={levers.weCanVary} />
        {levers.weCannotPull.map((lever) => (
          <LeverRow
            key={lever.lever}
            ours={false}
            lever={lever.lever}
            body={lever.whyNot}
            who={lever.whoCan}
          />
        ))}
      </div>
      {levers.inOneLine ? (
        <Disclosure
          title="The whole sentence, as the engine writes it"
          summary="what a sweep of chunk sizes is and is not an answer to"
        >
          <p className="levers__says">{levers.inOneLine}</p>
        </Disclosure>
      ) : null}
    </Section>
  );
}

function LeverRow({
  ours,
  lever,
  body,
  who,
}: {
  ours: boolean;
  lever: string;
  body: string;
  who?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="lever" data-ours={ours} data-open={open}>
      <button
        type="button"
        className="lever__head"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <Icon name={ours ? 'check' : 'x'} size={13} />
        <span className="lever__name mono">{lever}</span>
        <span className="lever__role">
          {ours ? 'this harness can vary it and re-measure' : 'not ours to pull'}
        </span>
        <Icon name="chevright" size={12} rotate={open ? 90 : 0} />
      </button>
      {open ? (
        <div className="lever__body">
          <p className="lever__why">{body}</p>
          {who ? (
            <p className="lever__who">
              <span className="lever__whok">who can</span> {who}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/* ══ THE SWEEP ════════════════════════════════════════════════════════════ */

/** The word in the header pill. Every one of them is an absence, and every one
 *  of them survives collapse — page 22.5: the claim is what the collapsed card
 *  keeps, because a card that collapsed to a title with no verdict would be a
 *  folder. */
function sweepPill(sweep: ChunkingSweep): { word: string; title: string } {
  if (sweep.state === 'refused') {
    return {
      word: 'NOTHING BUILT',
      title: 'This call was refused before any index was written.',
    };
  }
  if (sweep.state === 'plan') {
    return {
      word: 'NOT RUN',
      title: 'Nothing was built. The counts on this card are what it would do.',
    };
  }
  if (sweep.state === 'nothing_compared') {
    return {
      word: 'NOTHING COMPARED',
      title: 'The sweep stopped before it reached a comparison.',
    };
  }
  if (sweep.verdict === 'no_evidence') {
    return {
      word: 'NO EVIDENCE',
      title:
        'Not one pairwise test separated any two of these settings on this eval set.',
    };
  }
  return {
    word: 'NOTHING CROWNED',
    title:
      'Some pairs separated. No setting was crowned: the best recall in a sweep is a maximum selected on the same questions it would be reported against.',
  };
}

export function ChunkingSweepCard({ sweep }: { sweep: ChunkingSweep }) {
  const [open, setOpen] = useState(true);
  const pill = sweepPill(sweep);

  return (
    <div className="card card--sweep" data-open={open} data-state={sweep.state}>
      <div className="card__head">
        <Icon name="sliders" />
        <span className="card__kicker">Chunking sweep</span>
        <span className="card__clip" title={sweep.corpusPath ?? undefined}>
          {sweep.corpusPath ? basename(sweep.corpusPath) : 'a corpus'}
        </span>
        <span className="card__headright">
          <GreyPill word={pill.word} title={pill.title} />
          <button
            type="button"
            className="iconbtn"
            aria-label={open ? 'Collapse the chunking sweep' : 'Expand the chunking sweep'}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <Icon name="chevright" size={14} rotate={open ? 90 : 0} />
          </button>
        </span>
      </div>

      {open ? <div className="card__body">{sweepBody(sweep)}</div> : null}
    </div>
  );
}

function sweepBody(sweep: ChunkingSweep): ReactNode {
  const compared = sweep.state === 'compared';
  const settings = sweep.perSetting.map((row) => row.setting);
  const questions = sweep.questions;

  return (
    <>
      <SweepVerdict sweep={sweep} />

      {/* BEFORE THE CURVE AND BEFORE THE VERDICT'S DETAIL, because it changes
          what the verdict is ABOUT. `_sweep_sentence` puts it in the same
          place for the same reason: "NO EVIDENCE that any of these settings
          differs" over settings that produced one index is a true sentence a
          person reads as a fact about chunking, and the fact is that chunking
          never varied. */}
      {sweep.cuts?.says ? (
        <div className="collapse">
          <p className="collapse__head">
            <Icon name="alert" size={13} />
            <span>
              {sweep.cuts.distinctCuts !== null && sweep.planned.length > 0 ? (
                <>
                  These <b>{sweep.planned.length}</b> settings are{' '}
                  <b>{sweep.cuts.distinctCuts}</b> distinct{' '}
                  {sweep.cuts.distinctCuts === 1 ? 'cut' : 'cuts'} of this corpus.
                </>
              ) : (
                <>Some of these settings cut this corpus identically.</>
              )}
            </span>
          </p>
          {sweep.cuts.identicalGroups.map((group) => (
            <p className="collapse__group mono" key={group.join(' ')}>
              {group.join('  ·  ')}
            </p>
          ))}
          <p className="collapse__says">{sweep.cuts.says}</p>
        </div>
      ) : null}

      {compared && sweep.perSetting.length > 0 ? (
        <Section
          icon="chart"
          title="The whole curve"
          hint={`${sweep.perSetting.length} settings, in the order you passed them — never sorted by recall`}
          /* THE RECALLS ARE READINGS, and the header pill is a claim about the
             VERDICT rather than about them. `EvalCompareCard` moves provenance
             the same way and for the same reason: the tag lands on the thing
             it is true of. */
          tag="MEASURED"
        >
          <RecallStack
            settings={sweep.perSetting}
            beatenBy={sweep.beatenBy}
            label={`recall at k=${questions?.k ?? '?'} on the ${sweep.comparedQuestions} questions every setting scored`}
          />
          <p className="rstack__note">
            <Icon name="info" size={13} />
            <span>
              Each band is that setting&rsquo;s own 95% interval, which is the
              worst case for two <b>independent</b> runs. Whether two settings
              differ is decided by the paired tests below — over the questions
              whose verdict changed between them — and not by whether these
              bands overlap.
            </span>
          </p>
        </Section>
      ) : null}

      {compared ? <NothingCrowned sweep={sweep} /> : null}

      {compared && sweep.comparisons.length > 0 ? (
        <Section
          icon="branch"
          title="What the test could see"
          hint={`${sweep.familySize} pairwise comparison${sweep.familySize === 1 ? '' : 's'}, corrected together`}
          tag="MEASURED"
        >
          <div className="reso__row">
            {sweep.mostChangedByAnyPair !== null ? (
              <Figure
                value={String(sweep.mostChangedByAnyPair)}
                unit="questions"
                caption="the most any pair disagreed on"
              />
            ) : null}
            {sweep.minChangedAtThisFamilySize !== null ? (
              <Figure
                value={String(sweep.minChangedAtThisFamilySize)}
                unit="questions"
                caption="the fewest that could separate anything here"
              />
            ) : null}
            {sweep.tightestThreshold !== null ? (
              <Figure
                value={g3(sweep.tightestThreshold)}
                unit=""
                caption={`Holm's tightest threshold at alpha ${sweep.alpha ?? '?'}`}
              />
            ) : null}
          </div>

          {/* THE ONE SENTENCE THIS SECTION IS FOR, and it is arithmetic on two
              numbers the engine sent rather than an opinion about the sweep.
              Holm is step-down: the smallest p in the family is compared
              against alpha/m, so if no pair changed enough questions to reach
              that threshold, nothing could separate however the recalls
              looked. */}
          {sweep.minChangedAtThisFamilySize !== null &&
          sweep.mostChangedByAnyPair !== null ? (
            <p
              className="pgrid__floor"
              data-reachable={
                sweep.mostChangedByAnyPair >= sweep.minChangedAtThisFamilySize
              }
            >
              <Icon
                name={
                  sweep.mostChangedByAnyPair >= sweep.minChangedAtThisFamilySize
                    ? 'info'
                    : 'alert'
                }
                size={13}
              />
              <span>
                {sweep.mostChangedByAnyPair >= sweep.minChangedAtThisFamilySize ? (
                  <>
                    At least one pair changed enough questions to be reachable by
                    this family&rsquo;s threshold, so the tests below decide the
                    verdict.
                  </>
                ) : (
                  <>
                    No pair changed enough questions for the test to separate it
                    at all. <b>This sweep could not have concluded anything</b>{' '}
                    about these settings on this eval set, and that was true
                    before it ran.
                  </>
                )}
              </span>
            </p>
          ) : null}

          {sweep.familySize > 3 && settings.length > 2 ? (
            <PairGrid
              pairs={sweep.comparisons}
              settings={settings}
              floor={sweep.minChangedAtThisFamilySize}
              paired={sweep.comparedQuestions}
            />
          ) : (
            <PairRows pairs={sweep.comparisons} />
          )}

          {/* NOT `.reso__method`, which `evals.css` sets at --ink-4 and 10px.
              That is where a Wilson interval's derivation lives and it can
              afford to be a footnote; this sentence says what every test in
              the family would have kept uncorrected and what the tightest one
              has to clear now, which is the reason the verdict above is what
              it is. Page 03.3: if a reader is meant to get information out of
              it, it cannot be ink 4.

              THE SENTENCE THIS COMMENT USED TO PARAPHRASE WAS WRONG. It said
              "28 tests at 0.05 apiece would give a one-in-three chance of a
              false winner", copied from `correction` itself, where the
              probability was typed rather than computed and the settings
              count contradicted the interpolated family size. Corrected in
              `app/tools/retrieval.py` and guarded by
              `test_the_correction_states_only_numbers_this_payload_carries`;
              the card still prints the engine's words verbatim. */}
          {sweep.correction ? (
            <p className="sweep__method">
              <Icon name="info" size={12} />
              <span>{sweep.correction}</span>
            </p>
          ) : null}
        </Section>
      ) : null}

      {/* THE DENOMINATOR RENDERS ON THE `nothing_compared` PATH TOO, and that
          is the path it matters most on. `_sweep_refusal` carries
          `dropped_not_scored_by_every_setting` and `dropped_decided_by_a_tie`
          on the `no_comparable_questions` error — the case where every row was
          dropped and there was nothing left to compare — so a card that drew
          the block only on a finished sweep would hide the counts exactly
          when they are the whole answer. */}
      {compared || sweep.state === 'nothing_compared' ? (
        <Denominator sweep={sweep} />
      ) : null}
      {compared ? <Confirmation sweep={sweep} /> : null}

      {sweep.state === 'plan' ? <ThePlan sweep={sweep} /> : null}
      {sweep.state === 'nothing_compared' || sweep.state === 'refused' ? (
        <WhatWasBuilt sweep={sweep} />
      ) : null}

      <Stamp measured={sweep.measured} notMeasured={sweep.notMeasured} />

      {sweep.reMeasuring ? <ReMeasuring sweep={sweep} /> : null}

      {sweep.levers ? <LeverBlock levers={sweep.levers} /> : null}

      {/* ══ THE ENGINE'S OWN PARAGRAPH, KEPT AND FOLDED ═══════════════════
          `EvalCompareCard` keeps `says` in the primary reading at 11px and
          says why: it is the engine's authoritative wording and a person who
          does not trust the card should not have to hunt for it. That
          argument was made about five sentences.

          MEASURED HERE, in this harness, on the nine fixtures: `says` runs
          5,645 to 7,903 characters on a finished sweep and renders 660 to 915
          PIXELS TALL — most of a screen of 11px grey prose, and it contains
          `STAMPS_NOTHING` (1,708 characters) and the levers line verbatim, both
          of which have their own blocks six inches above. Printing it in the
          primary reading would state every fact on the card twice at the
          bottom of it, which is the verbatim-echo defect `EvalCard.tsx` warns
          about three times.

          So it is folded, and page 14.6's condition is checked rather than
          assumed: a fact may not live ONLY in a surface you can miss. Every
          clause of `says` has a structural home above — the curve in the
          stack, the collapse in its own block, the dropped rows and the
          unlabelled rows in the denominator, the threshold arithmetic in the
          three figures, `selected_on_noise` in the crownless block, the
          re-measuring counts in the ledger, the levers in their section. The
          last of those was NOT true when this fold was first written:
          `re_measuring.says` carried the setting-to-index-id mapping and
          nothing else did, so `ReMeasuring` below now draws it as rows. */}
      {sweep.says ? (
        <Disclosure
          title="The bench&rsquo;s own summary"
          summary="every fact on this card, in one paragraph, in the engine's words"
        >
          <p className="compare__saysv">{sweep.says}</p>
        </Disclosure>
      ) : null}

      <SweepFacts sweep={sweep} />
    </>
  );
}

/**
 * The verdict, in the biggest type on the card, and never a recall.
 *
 * `EvalCompareCard`'s rule, applied to N: *"a `+19.2%` set in 26px is a
 * result, whatever is written under it."* The largest recall in a sweep is
 * worse than that, because it is a maximum selected on the same questions it
 * would be reported against, so no recall appears in this block on any branch.
 */
function SweepVerdict({ sweep }: { sweep: ChunkingSweep }) {
  const n = sweep.perSetting.length;

  if (sweep.state === 'refused' || sweep.state === 'nothing_compared') {
    return (
      <div className="rverdict" data-kind="absent">
        <span className="rverdict__word">
          {sweep.state === 'refused' ? 'Nothing built' : 'Nothing compared'}
        </span>
        <span className="rverdict__line">
          <Icon name="eye" size={14} />
          {sweep.error ? (
            <span className="mono">{sweep.error}</span>
          ) : (
            'the sweep did not reach a comparison'
          )}
        </span>
      </div>
    );
  }

  if (sweep.state === 'plan') {
    const will = sweep.willDo;
    return (
      <div className="rverdict" data-kind="absent">
        <span className="rverdict__word">Not run</span>
        <span className="rverdict__line">
          <Icon name="eye" size={14} />
          {will && will.rebuilds !== null
            ? `${will.rebuilds} rebuilds, ${will.passagesWritten ?? '?'} passages and ${will.retrievals ?? '?'} retrievals — counted, not estimated`
            : 'nothing was written; the counts below are what it would do'}
        </span>
      </div>
    );
  }

  if (sweep.verdict === 'no_evidence') {
    return (
      <div className="rverdict" data-kind="none">
        <span className="rverdict__word">No evidence</span>
        <span className="rverdict__line">
          <Icon name="eye" size={14} />
          {sweep.familySize === 0
            ? 'there was no pair to test'
            : `Not one of ${sweep.familySize} pairwise test${sweep.familySize === 1 ? '' : 's'} separated any two of these ${n} settings`}
        </span>
      </div>
    );
  }

  return (
    <div className="rverdict" data-kind="some">
      <span className="rverdict__figure mono">{sweep.separatedN}</span>
      <span className="rverdict__unit">of {sweep.familySize} pairs separated</span>
      <span className="rverdict__line">
        <Icon name="branch" size={14} />
        Nothing was crowned — the settings nothing beat are a set, not a winner
      </span>
    </div>
  );
}

/**
 * What `measure_retriever_recall` would actually do with each setting here.
 *
 * The engine recommends going and taking the stamp yourself, and is explicit
 * that what comes back is NEITHER a copy of the number in the curve NOR a cure
 * for how it was chosen: a sweep compares the rows EVERY setting scored minus
 * every row a tie decided anywhere in the family, and a single run scores one
 * index over the rows THAT index can score. Different denominators whenever
 * the sweep dropped anything.
 *
 * DRAWN AS ROWS AND NOT AS THE ENGINE'S SENTENCE, and that is not a stylistic
 * preference. `_re_measuring` puts the setting-to-index-id mapping inside its
 * prose and nowhere else in the payload, so folding `says` away — which this
 * card does, for the reason recorded there — would have made this mapping live
 * only in a surface you can miss. Every value below is read off `per_setting`,
 * which is where the engine computed them.
 */
function ReMeasuring({ sweep }: { sweep: ChunkingSweep }) {
  const info = sweep.reMeasuring;
  if (!info) return null;
  return (
    <div className="remeasure">
      <p className="remeasure__head">
        <Icon name="refresh" size={13} />
        <span>If you go and take the stamp yourself</span>
      </p>
      <div className="reso__row">
        <Figure
          value={String(info.settingsThatWouldStamp)}
          unit={`of ${sweep.perSetting.length}`}
          caption="settings whose own run would record a fact"
        />
        <Figure
          value={String(info.settingsOnTheSameRows)}
          unit={`of ${sweep.perSetting.length}`}
          caption="settings scored on the same rows as this comparison"
        />
        <Figure
          value={String(info.rowsDroppedBeforeComparing)}
          unit="rows"
          caption="dropped here that a single run keeps"
        />
      </div>

      <div className="denom">
        {sweep.perSetting.map((row) => {
          const own = row.ownRun;
          const same = own !== null && own.of === row.of;
          return (
            <div
              className="denom__row"
              key={row.setting}
              data-dropped={own !== null && !own.stampableOnItsOwn}
            >
              <span className="denom__v mono">{row.setting}</span>
              <span className="denom__k">
                index <span className="mono">{row.indexId ?? '?'}</span>
                {row.indexName ? (
                  <>
                    {' '}
                    <span className="mono">{row.indexName}</span>
                  </>
                ) : null}{' '}
                &middot; <span className="mono">{row.hits}/{row.of}</span> here
                {own ? (
                  <>
                    {' '}
                    &middot; <span className="mono">{own.hits}/{own.of}</span> on
                    its own rows{same ? '' : ' — a different denominator'}
                    {' '}&middot;{' '}
                    <b>{own.stampableOnItsOwn ? 'would stamp' : 'would NOT stamp'}</b>
                  </>
                ) : null}
              </span>
            </div>
          );
        })}
      </div>

      {info.howToNameASetting ? (
        <p className="remeasure__how">{info.howToNameASetting}</p>
      ) : null}
    </div>
  );
}

/**
 * `highest_recall_here`, and the sentence it may not appear without.
 *
 * This is the one place on the card where the best recall in the sweep is
 * named, and it is deliberately not on the stack: a highlighted row is a
 * crowning whatever the caption says. Here the number and the engine's own
 * "AND THAT IS NOT A WINNER" are one block, which is the treatment `EvalCard`
 * gives a judge's score — the disclosure IS the component, so the figure
 * cannot be rendered without it.
 */
function NothingCrowned({ sweep }: { sweep: ChunkingSweep }) {
  const beaten = Object.entries(sweep.beatenBy).filter(
    ([, by]) => by.length > 0,
  );
  /* The count behind the label, looked up rather than recomputed: these are
     `per_setting`'s own hits over `per_setting`'s own denominator. */
  const top = sweep.perSetting.find((row) =>
    sweep.highestRecallHere.includes(row.setting),
  );
  return (
    <div className="crownless">
      <div className="crownless__head">
        <Icon name="eye" size={13} />
        {/* NOT A PARAGRAPH. The first cut of this block opened with "2
            settings tie for the highest recall in this sweep, and a tie at the
            top is not a shortlist" — which is `why_nothing_is_crowned`'s own
            first clause, printed four lines above `why_nothing_is_crowned`.
            The engine says it better and says it once; what this line owes is
            a label for the figure beside it. */}
        <span className="crownless__title">
          The highest recall in this sweep
          {top ? (
            <>
              , which is{' '}
              <b className="mono">
                {top.hits} of {top.of}
              </b>
            </>
          ) : null}
        </span>
        <GreyPill
          word="NOT CROWNED"
          title="compare_chunkings returns crowned: null on every path, including the one where four of six comparisons separate."
        />
      </div>

      <p className="crownless__set mono">{sweep.highestRecallHere.join('  ·  ')}</p>

      {beaten.length > 0 ? (
        <div className="crownless__beaten">
          {beaten.map(([setting, by]) => (
            <p className="crownless__row" key={setting}>
              <span className="crownless__who mono">{setting}</span>
              <span className="crownless__by">was beaten by</span>
              <span className="crownless__whom mono">{by.join(' · ')}</span>
            </p>
          ))}
          <p className="crownless__unbeaten">
            <span className="crownless__unbeatenk">
              nothing was shown to beat
            </span>{' '}
            <span className="mono">{sweep.notBeatenByAnything.join(' · ')}</span>{' '}
            &mdash; which is a different claim from &ldquo;this one is
            best&rdquo;, and the second needs comparisons this eval set did not
            resolve.
          </p>
        </div>
      ) : null}

      {sweep.whyNothingIsCrowned ? (
        <p className="crownless__why">{sweep.whyNothingIsCrowned}</p>
      ) : null}
    </div>
  );
}

/**
 * The denominator's honesty: what is in no number above, and why.
 *
 * A row only some settings could score, and a row a score tie rather than the
 * retriever decided, are dropped FOR EVERY SETTING AT ONCE — dropping from one
 * side only would unpair the rows. Losing that block loses the meaning of
 * every count on the card, which is why it renders even when both figures are
 * zero: a reader who never sees it is a reader who does not know it is
 * checked.
 */
function Denominator({ sweep }: { sweep: ChunkingSweep }) {
  const questions = sweep.questions;
  const dropped = sweep.dropped;
  const anyDropped =
    dropped.notScoredByEverySetting > 0 || dropped.decidedByATie > 0;

  return (
    <Section
      icon="dataset"
      title="The denominator"
      hint={sweep.measuredOn ?? 'what every number above is over'}
    >
      <div className="denom">
        <div className="denom__row" data-role="kept">
          <span className="denom__v mono">{sweep.comparedQuestions}</span>
          <span className="denom__k">
            questions every setting scored, with the answer decided by the
            retriever — every number above is over these
          </span>
        </div>
        <div className="denom__row" data-dropped={dropped.notScoredByEverySetting > 0}>
          <span className="denom__v mono">{dropped.notScoredByEverySetting}</span>
          <span className="denom__k">
            not scored by every setting
            {dropped.notScoredRows.length > 0 ? (
              <span className="denom__rows mono">
                {dropped.notScoredRows.map((row) => `#${row}`).join(' ')}
                {dropped.notScoredRows.length < dropped.notScoredByEverySetting
                  ? ` +${dropped.notScoredByEverySetting - dropped.notScoredRows.length}`
                  : ''}
              </span>
            ) : null}
          </span>
        </div>
        <div className="denom__row" data-dropped={dropped.decidedByATie > 0}>
          <span className="denom__v mono">{dropped.decidedByATie}</span>
          <span className="denom__k">
            decided by a score tie rather than by the retriever
            {dropped.tieRows.length > 0 ? (
              <span className="denom__rows mono">
                {dropped.tieRows.map((row) => `#${row}`).join(' ')}
                {dropped.tieRows.length < dropped.decidedByATie
                  ? ` +${dropped.decidedByATie - dropped.tieRows.length}`
                  : ''}
              </span>
            ) : null}
          </span>
        </div>
        {questions && (questions.unlabelled ?? 0) > 0 ? (
          <div className="denom__row" data-dropped="true">
            <span className="denom__v mono">{questions.unlabelled}</span>
            <span className="denom__k">
              rows in {questions.evalPath ? basename(questions.evalPath) : 'the eval set'}{' '}
              carry no ground truth or no question and could not be scored by
              anything — so the denominator above is the labelled rows and not
              your eval set
            </span>
          </div>
        ) : null}
      </div>

      {anyDropped && dropped.why ? <p className="denom__why">{dropped.why}</p> : null}
    </Section>
  );
}

/**
 * Choose on half the questions, look the choice up on the other half.
 *
 * The only part of the sweep that touches the upward bias of a maximum, and
 * the only recall on the card that was not selected on its own questions.
 * `gapIsAReadOnSelection` is read off the wire rather than derived from the
 * sign here, because the engine is explicit that a NEGATIVE gap is not a
 * smaller quantity of selection — the bias is non-negative by construction —
 * and a card that drew "shrinkage: -3.3 points" as a measurement of selection
 * would be stating a number as something it is not.
 */
function Confirmation({ sweep }: { sweep: ChunkingSweep }) {
  const confirmation = sweep.confirmation;
  if (!confirmation) return null;

  if (!confirmation.ok) {
    return (
      <Section icon="gauge" title="Chosen on half, confirmed on the other half">
        <p className="card__absent">
          {confirmation.why ??
            'There is no split-half confirmation on this sweep.'}
        </p>
      </Section>
    );
  }

  return (
    <Section
      icon="gauge"
      title="Chosen on half, confirmed on the other half"
      hint={`${confirmation.chosenOnQuestions ?? '?'} questions chose, ${confirmation.confirmedOnQuestions ?? '?'} confirmed`}
      tag="MEASURED"
    >
      <div className="confirm">
        {confirmation.rows.map((row) => (
          <div className="confirm__row" key={row.setting}>
            <span className="confirm__setting mono">{row.setting}</span>
            <span className="confirm__pair mono">
              {row.chosenOnHits}/{row.chosenOnOf}
            </span>
            <span className="confirm__label">when it was chosen</span>
            <Icon name="chevright" size={12} />
            <span className="confirm__pair mono">
              {row.confirmedHits}/{row.confirmedOf}
            </span>
            <span className="confirm__label">on the questions that did not</span>
            {row.shrinkage !== null ? (
              <span className="confirm__gap mono">
                {row.shrinkage > 0 ? '−' : row.shrinkage < 0 ? '+' : '±'}
                {points(Math.abs(row.shrinkage) * 100)} pts
              </span>
            ) : null}
          </div>
        ))}
      </div>

      <p
        className="confirm__reading"
        data-selection={confirmation.gapIsAReadOnSelection}
      >
        <Icon name={confirmation.gapIsAReadOnSelection ? 'alert' : 'info'} size={13} />
        <span>
          {confirmation.gapIsAReadOnSelection ? (
            <>
              The gap went <b>down</b>, which is consistent with a choice made on
              noise. It is one draw of a noisy quantity and <b>not</b> a
              correction to subtract.
            </>
          ) : (
            <>
              This split measured no quantity of selection
              {confirmation.gapDirection ? (
                <>
                  {' '}
                  — the gap came out <b className="mono">{confirmation.gapDirection}</b>
                </>
              ) : null}
              . The upward bias of a maximum is non-negative by construction, so
              a gap that is not downward is not a smaller amount of it and not
              evidence there was none.
            </>
          )}
        </span>
      </p>

      {confirmation.assumes ? (
        <p className="confirm__assumes">
          <span className="confirm__assumesk">what the split assumes</span>{' '}
          {confirmation.assumes}
        </p>
      ) : null}

      {confirmation.says ? (
        <Disclosure
          title="The confirmation in full"
          summary={confirmation.splitBy ? 'how the halves were split' : 'the engine’s own account'}
        >
          <p className="levers__says">{confirmation.says}</p>
          {confirmation.splitBy ? <Fact k="split_by" v={confirmation.splitBy} /> : null}
        </Disclosure>
      ) : null}
    </Section>
  );
}

/** What the sweep would write, before it writes any of it. No duration
 *  anywhere: nothing in this harness has measured one on this machine, and the
 *  engine refuses to invent one rather than rounding it off. */
function ThePlan({ sweep }: { sweep: ChunkingSweep }) {
  const will = sweep.willDo;
  if (!will) return null;
  return (
    <>
      <Section
        icon="dataset"
        title="What it would do"
        hint={will.countedBy ? 'counted by the same function that writes the rows' : undefined}
      >
        <div className="reso__row">
          <Figure
            value={String(will.rebuilds ?? 0)}
            unit={`of ${will.settings ?? 0}`}
            caption="indexes to build — the rest are already there"
          />
          <Figure
            value={String(will.passagesWritten ?? 0)}
            unit="passages"
            caption="written into this project's database"
          />
          <Figure
            value={String(will.postingRowsWritten ?? 0)}
            unit="posting rows"
            caption="one distinct term in one passage"
          />
          <Figure
            value={String(will.retrievals ?? 0)}
            unit="retrievals"
            caption={`${will.questionsEachSettingIsScoredOn ?? '?'} questions, once per setting`}
          />
        </div>
        <p className="plan__nodur">
          <Icon name="clock" size={13} />
          <span>
            No duration is stated anywhere on this card, because nothing in this
            harness has measured how long a rebuild of this corpus takes on this
            machine.
          </span>
        </p>
      </Section>

      {sweep.planned.length > 0 ? (
        <Section
          icon="sliders"
          title="Per setting"
          hint="in the order you passed them"
        >
          <div className="denom">
            {sweep.planned.map((row) => (
              <div className="denom__row" key={row.indexName ?? String(row.passageChars)}>
                <span className="denom__v mono">
                  {row.passageChars ?? '?'}/{row.passageOverlap ?? '?'}
                </span>
                <span className="denom__k">
                  <span className="mono">{row.passages ?? 0}</span> passages,{' '}
                  <span className="mono">{row.postingRows ?? 0}</span> posting rows
                  {row.alreadyBuilt ? ' — already built, would be reused' : null}
                  {row.shortFragmentsDropped ? (
                    <>
                      {' '}
                      · <span className="mono">{row.shortFragmentsDropped}</span>{' '}
                      fragments too short to index
                    </>
                  ) : null}
                </span>
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {sweep.statistics?.says ? (
        <Section
          icon="branch"
          title="What this sweep could resolve"
          hint="arithmetic about its shape, known before it runs"
        >
          <div className="reso__row">
            <Figure
              value={String(sweep.statistics.familySize ?? 0)}
              unit="pairwise tests"
              caption="corrected together"
            />
            {sweep.statistics.minChangedToSeparateAnyPair !== null ? (
              <Figure
                value={String(sweep.statistics.minChangedToSeparateAnyPair)}
                unit="questions"
                caption="would have to change before any pair could separate"
              />
            ) : null}
          </div>
          <p className="reso__says">{sweep.statistics.says}</p>
        </Section>
      ) : null}
    </>
  );
}

/** The indexes a stopped sweep left in the conversation. Named rather than
 *  hidden: an index this call wrote is on disk whether or not the comparison
 *  reached the end, and a card that did not mention it would be a card about a
 *  database that is not the one there. */
function WhatWasBuilt({ sweep }: { sweep: ChunkingSweep }) {
  return (
    <Section
      icon="dataset"
      title="What this call left behind"
      hint={
        sweep.indexes.length === 0
          ? 'nothing was written'
          : `${sweep.indexes.length} index${sweep.indexes.length === 1 ? '' : 'es'} in this conversation`
      }
    >
      {sweep.indexes.length === 0 ? (
        <p className="card__absent">
          No index was built, so there is nothing in this conversation that was
          not there before.
        </p>
      ) : (
        <div className="denom">
          {sweep.indexes.map((index) => (
            <div className="denom__row" key={index.indexId ?? index.indexName}>
              <span className="denom__v mono">{index.indexId ?? '?'}</span>
              <span className="denom__k">
                <span className="mono">{index.indexName}</span> —{' '}
                {index.passages ?? '?'} passages from {index.documents ?? '?'}{' '}
                documents
                {index.reused ? ' · reused, nothing was rebuilt' : null}
                {index.truncated ? ' · TRUNCATED' : null}
              </span>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

/** The reproducibility block. Every key is the engine's own field name. */
function SweepFacts({ sweep }: { sweep: ChunkingSweep }) {
  const questions = sweep.questions;
  return (
    <Disclosure
      title="How this was run"
      summary={`${sweep.perSetting.length || sweep.planned.length} settings · k=${questions?.k ?? '?'} · BM25 on this machine`}
    >
      {sweep.corpusPath ? <Fact k="corpus_path" v={sweep.corpusPath} /> : null}
      {sweep.evalPath ? <Fact k="eval_path" v={sweep.evalPath} /> : null}
      {questions?.questionField ? (
        <Fact k="question_field" v={questions.questionField} />
      ) : null}
      {questions?.groundTruthField ? (
        <Fact
          k="ground_truth_field"
          v={`${questions.groundTruthField}${questions.groundTruthChosenHow ? ` — ${questions.groundTruthChosenHow}` : ''}`}
        />
      ) : null}
      {questions?.rowsRead !== null && questions?.rowsRead !== undefined ? (
        <Fact
          k="rows"
          v={`${questions.rowsRead} read of ${questions.rowsSeen ?? '?'} seen · ${questions.eligible ?? '?'} eligible`}
        />
      ) : null}
      {sweep.alpha !== null ? <Fact k="alpha" v={String(sweep.alpha)} /> : null}
      {sweep.tightestThreshold !== null ? (
        <Fact k="tightest_threshold" v={g3(sweep.tightestThreshold)} />
      ) : null}
      {sweep.scorer ? <Fact k="scorer" v={sweep.scorer} /> : null}
      {sweep.cuts?.distinctCuts !== null && sweep.cuts?.distinctCuts !== undefined ? (
        <Fact k="distinct_cuts" v={String(sweep.cuts.distinctCuts)} />
      ) : null}
      {sweep.indexes.map((index) => (
        <Fact
          key={index.indexId ?? index.indexName}
          k={`index ${index.indexId ?? '?'}`}
          v={`${index.indexName ?? '?'} — ${index.passages ?? '?'} passages, ${index.documents ?? '?'} documents${index.cutBy ? `, ${index.cutBy}` : ''}`}
        />
      ))}
      {sweep.decidesNothing ? (
        <p className="runfacts__note">{sweep.decidesNothing}</p>
      ) : null}
      {sweep.stampsNothing ? (
        <p className="runfacts__note">{sweep.stampsNothing}</p>
      ) : null}
    </Disclosure>
  );
}

/* ══ ONE INDEX ════════════════════════════════════════════════════════════ */

/** How many missed rows stand open before the list asks to be unfolded. The
 *  same eight `EvalCard` uses, for the same measured reason: a 26px row and a
 *  cap of twenty makes an uncapped list a 520px block inside a card that
 *  already runs past a screen. */
const MISSES_SHOWN = 8;

export function RetrieverRecallCard({ report }: { report: RecallReport }) {
  const [open, setOpen] = useState(true);
  const recorded = report.measured.length > 0;

  return (
    <div
      className="card card--recall"
      data-open={open}
      data-recorded={String(recorded)}
    >
      <div className="card__head">
        <Icon name="search" />
        <span className="card__kicker">Retriever recall</span>
        <span className="card__clip" title={report.evalPath}>
          {report.indexName ?? 'an index'}
          {report.evalPath ? ` · ${basename(report.evalPath)}` : ''}
        </span>
        <span className="card__headright">
          {/* PAGE 22.1 PART 2: the tag in this slot is a claim about what the
              card RESTS ON. A run that stamped rests on a reading the ledger
              took. A run that did not — and there are seven ways to be one —
              rests on nothing recorded, and MEASURED there would be the
              header asserting a fact the engine refused to write. */}
          {recorded ? (
            <ProvenanceTag tag="MEASURED" />
          ) : (
            <GreyPill
              word="NOTHING RECORDED"
              title="This run did not stamp retriever_recall_at_k. The reason is on the card."
            />
          )}
          <button
            type="button"
            className="iconbtn"
            aria-label={open ? 'Collapse the recall run' : 'Expand the recall run'}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <Icon name="chevright" size={14} rotate={open ? 90 : 0} />
          </button>
        </span>
      </div>

      {open ? (
        <div className="card__body">
          <RecallHead report={report} />

          {report.recall !== null ? (
            <>
              <RecallScale report={report} />
              {report.curve.length > 1 ? (
                <Section
                  icon="chart"
                  title="Recall rises with k"
                  hint={`the whole curve, k=1 to k=${report.k}`}
                  tag="MEASURED"
                >
                  <RecallCurve curve={report.curve} reportedAt={report.k} />
                </Section>
              ) : null}
            </>
          ) : null}

          <RecallDenominator report={report} />

          {report.misses.length > 0 || report.questionsScored > 0 ? (
            <Section
              icon="filter"
              title="The questions that missed"
              hint={
                report.hits !== null
                  ? `${report.questionsScored - report.hits} of ${report.questionsScored}`
                  : undefined
              }
            >
              <Misses report={report} />
            </Section>
          ) : null}

          {report.answerInPassage ? (
            <Proxy proxy={report.answerInPassage} />
          ) : null}

          <Stamp
            measured={report.measured}
            notMeasured={report.notMeasured}
            recorded={report.recorded}
          />

          {report.columns.length > 0 ? (
            <Section
              icon="dataset"
              title="The columns this file does have"
              hint="none of them names a document or a passage"
            >
              <p className="denom__cols mono">{report.columns.join('  ·  ')}</p>
            </Section>
          ) : null}

          <RecallFacts report={report} />
        </div>
      ) : null}
    </div>
  );
}

function RecallHead({ report }: { report: RecallReport }) {
  const recorded = report.measured.length > 0;
  if (report.recall === null) {
    return (
      <div className="rverdict" data-kind="absent">
        <span className="rverdict__word">Nothing measured</span>
        <span className="rverdict__line">
          <Icon name="eye" size={14} />
          {report.error ? <span className="mono">{report.error}</span> : 'no question could be scored'}
        </span>
      </div>
    );
  }
  const level = report.groundTruthLevel;
  const what =
    level === 'passage'
      ? 'the right passage'
      : level === 'document'
        ? 'a passage from the right document'
        : 'the right passage or document';
  return (
    <div className="rhead">
      <span className="rhead__score" data-recorded={String(recorded)}>
        {pct(report.recall)}
      </span>
      {/* EVERY NUMBER ON THIS LINE IS MONO, and two of them were not. The
          headline read "18 of 24 questions had ... in the top 5" with the 18
          and the 24 set in the sans and only the 5 in the mono, on one line,
          at one size — so the same kind of thing was drawn two ways a
          centimetre apart. `k` keeps the bold because it is the parameter the
          sentence is about; the count and its denominator take the mono and
          not the emphasis. */}
      <span className="rhead__of">
        <span className="mono">{report.hits}</span> of{' '}
        <span className="mono">{report.questionsScored}</span> questions had{' '}
        {what} in the top <b className="mono">{report.k}</b>
      </span>
    </div>
  );
}

/**
 * The recall and its interval, on one 0–100 axis.
 *
 * `EvalCard`'s `ScoreScale` without the trivial baseline, because this bench
 * has none: `evals.py` measures what answering the most common label would
 * score, and there is no equivalent for "the right passage came back". Drawing
 * a baseline at some assumed rate would be inventing the reference, so the
 * axis carries the measurement and nothing else.
 */
function RecallScale({ report }: { report: RecallReport }) {
  const ci = report.resolution.ci95;
  const recall = report.recall ?? 0;
  const low = ci ? ci[0] : recall;
  const high = ci ? ci[1] : recall;
  return (
    <div className="scale">
      <div className="scale__track">
        <span
          className="scale__band"
          style={{ left: `${low * 100}%`, width: `${Math.max(0, high - low) * 100}%` }}
          title={
            ci
              ? `95% confidence: ${pct(low, 1)} to ${pct(high, 1)}`
              : 'no interval — nothing was scored'
          }
        />
        <span
          className="scale__marker"
          data-beats="unknown"
          style={{ '--p': recall } as CSSProperties}
        />
      </div>
      <div className="scale__axis">
        <span>0%</span>
        {/* `k` IS A NUMBER AND WAS SET IN THE SANS. Three of them were, all
            of them trailing a "k=" inside a sentence, while every other
            figure on this card is mono — including the `k` in the headline
            four lines up. Same kind of thing, two faces. */}
        <span className="scale__label">
          retriever_recall_at_k, k=<span className="mono">{report.k}</span>
        </span>
        <span>100%</span>
      </div>
      <div className="reso">
        <div className="reso__row">
          {report.resolution.halfWidthPoints !== null ? (
            <Figure
              value={`±${points(report.resolution.halfWidthPoints)}`}
              unit="points"
              caption="95% interval on this recall"
            />
          ) : null}
          {report.resolution.resolvesDifferenceOfPoints !== null ? (
            <Figure
              value={points(report.resolution.resolvesDifferenceOfPoints, 0)}
              unit="points"
              caption="smallest difference this many questions can see"
            />
          ) : null}
          <Figure
            value={String(report.questionsScored)}
            unit="questions"
            caption="scored"
          />
        </div>
        {report.resolution.says ? (
          <p className="reso__says">{report.resolution.says}</p>
        ) : null}
      </div>
    </div>
  );
}

/**
 * The whole curve, because recall rises with k.
 *
 * The tool's own description says the number is meaningless without the depth
 * it was taken at, and `Instrument.measured` writes "RECALL RISES WITH K and
 * this number is at k=N" into the ledger row. A card that drew only the
 * headline would leave the reader with the one figure that cannot be compared
 * with anybody else's.
 *
 * The bar runs from zero rather than carrying a band, and that is deliberate:
 * the engine computes one interval, for the run, and it is drawn once above.
 * A per-k interval here would be this file computing a statistic the
 * instrument did not.
 */
function RecallCurve({
  curve,
  reportedAt,
}: {
  curve: RecallPoint[];
  reportedAt: number;
}) {
  return (
    <div className="rstack" data-kind="curve">
      {curve.map((point) => (
        <div
          className="rrow"
          key={point.k}
          data-reported={point.k === reportedAt}
        >
          <span className="rrow__label mono">k={point.k}</span>
          <span
            className="rrow__track"
            title={`${point.hits} of ${point.of} at k=${point.k}`}
          >
            {/* Zero draws nothing here too: a depth at which the retriever
                returned the right thing for no question at all is a real and
                important reading, and a hairline would soften it. */}
            {point.recall !== null && point.recall > 0 ? (
              <span
                className="rrow__fill"
                style={{ width: `${point.recall * 100}%` }}
              />
            ) : null}
          </span>
          <span className="rrow__count mono">
            {point.hits}
            <span className="rrow__of">/{point.of}</span>
          </span>
          <span className="rrow__pct mono">
            {point.recall === null ? '—' : pct(point.recall, 1)}
          </span>
        </div>
      ))}
      {curve.some((point) => point.tieDecided > 0) ? (
        <p className="rstack__ties">
          <Icon name="alert" size={13} />
          <span>
            {curve
              .filter((point) => point.tieDecided > 0)
              .map((point) => `k=${point.k}: ${point.tieDecided}`)
              .join(' · ')}{' '}
            — at those depths that many questions had the answer decided by two
            passages tying on score rather than by the retriever.
          </span>
        </p>
      ) : null}
    </div>
  );
}

/** Every row the file had, and where each one went. The counts that make the
 *  recall above mean something. */
function RecallDenominator({ report }: { report: RecallReport }) {
  return (
    <Section
      icon="dataset"
      title="The denominator"
      hint={report.evalPath ? basename(report.evalPath) : undefined}
    >
      <div className="denom">
        <div className="denom__row" data-role="kept">
          <span className="denom__v mono">{report.questionsScored}</span>
          <span className="denom__k">
            questions scored — the denominator of the recall above
          </span>
        </div>
        <div className="denom__row">
          <span className="denom__v mono">{report.rowsRead}</span>
          <span className="denom__k">
            rows read{report.rowsSeen !== null && report.rowsSeen !== report.rowsRead
              ? ` of ${report.rowsSeen} in the file`
              : ' from the file'}
            {report.hitRowCap ? ' — THE ROW CAP BIT, so this is a prefix and not a sample' : ''}
          </span>
        </div>
        <div className="denom__row" data-dropped={report.unlabelledN > 0}>
          <span className="denom__v mono">{report.unlabelledN}</span>
          <span className="denom__k">
            rows with no ground truth or no question
            {Object.keys(report.unlabelledByReason).length > 0 ? (
              <span className="denom__rows">
                {Object.entries(report.unlabelledByReason)
                  .map(([reason, count]) => `${count} — ${reason}`)
                  .join(' · ')}
              </span>
            ) : null}
          </span>
        </div>
        <div className="denom__row" data-dropped={report.unresolvedN > 0}>
          <span className="denom__v mono">{report.unresolvedN}</span>
          <span className="denom__k">
            rows whose ground truth names something this index does not contain
            {report.unresolvedRows.length > 0 ? (
              <span className="denom__rows mono">
                {report.unresolvedRows.slice(0, 10).join(' ')}
              </span>
            ) : null}
          </span>
        </div>
        <div className="denom__row" data-dropped={report.tieDecidedN > 0}>
          <span className="denom__v mono">{report.tieDecidedN}</span>
          <span className="denom__k">
            rows where a score tie rather than the retriever decided whether the
            right passage was inside the top <span className="mono">{report.k}</span>
            {report.tieDecidedRows.length > 0 ? (
              <span className="denom__rows mono">
                {report.tieDecidedRows.map((row) => `#${row}`).join(' ')}
              </span>
            ) : null}
          </span>
        </div>
      </div>
      {report.groundTruthField ? (
        <p className="denom__why">
          Ground truth read from{' '}
          <span className="mono">{report.groundTruthField}</span>
          {report.groundTruthChosenHow ? `, ${report.groundTruthChosenHow}` : ''}
          {report.groundTruthLevel
            ? `, resolving at the ${report.groundTruthLevel} level`
            : ''}
          .
        </p>
      ) : null}
    </Section>
  );
}

function Misses({ report }: { report: RecallReport }) {
  const [all, setAll] = useState(false);
  const [openRow, setOpenRow] = useState<number | null>(null);
  /* How many questions missed IN TOTAL, which is the engine's two counts and
     not the length of the list it happened to return. Null when nothing was
     scored, because then there is no total rather than a total of zero. */
  const total =
    report.hits === null ? null : report.questionsScored - report.hits;

  if (report.misses.length === 0) {
    return (
      <p className="card__absent">
        {report.hits !== null && report.hits === report.questionsScored
          ? 'Every scored question found its answer inside the top ' + report.k + '.'
          : 'No missed question came back in this reply.'}
      </p>
    );
  }

  const shown = all ? report.misses : report.misses.slice(0, MISSES_SHOWN);
  const hidden = report.misses.length - shown.length;

  return (
    <div className="rows">
      {shown.map((row) => (
        <MissRow
          key={row.row}
          row={row}
          k={report.k}
          open={openRow === row.row}
          onToggle={() => setOpenRow(openRow === row.row ? null : row.row)}
        />
      ))}
      {hidden > 0 ? (
        <button type="button" className="rows__all" onClick={() => setAll(true)}>
          <Icon name="chevdown" size={12} />
          Show the other {hidden} missed question{hidden === 1 ? '' : 's'} this reply returned
        </button>
      ) : null}

      {/* THE ONES THE REPLY DID NOT CARRY. `score_recall` caps `misses` at
          twenty, so on a run with more than that the list is a sample and the
          card has to say so — `EvalCard` makes the same statement about
          `failuresTotal`, and for the same reason: a list that quietly stops
          is a denominator nobody was told about. */}
      {total !== null && total > report.misses.length ? (
        <p className="rows__more">
          {total - report.misses.length} more missed question
          {total - report.misses.length === 1 ? ' was' : 's were'} not returned
          in this reply. Every scored row is on disk; ask for more and the bench
          reads them without asking any model anything.
        </p>
      ) : null}
    </div>
  );
}

function MissRow({
  row,
  k,
  open,
  onToggle,
}: {
  row: RecallRow;
  k: number;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="qrow" data-open={open}>
      <button type="button" className="frow__head" onClick={onToggle} aria-expanded={open}>
        <Icon name="chevright" size={12} rotate={open ? 90 : 0} />
        <span className="frow__index">#{row.row}</span>
        <span className="frow__input">{row.question}</span>
        <span className="qrow__truth mono">{row.groundTruth}</span>
      </button>
      {open ? (
        <div className="frow__body">
          {/* NO TONES. `evals.css` washes `expected` in --fits and `answered`
              in --wont, and there that is a claim: the row FAILED and the
              answer is the wrong one. A missed question is not that. The
              passages that came back are not wrong, they are simply not the
              one that was wanted, and nobody measured anything about them —
              so painting them red would be this card making a judgement the
              engine did not, and painting a ground-truth path green would be
              a judgement about nothing at all. */}
          <div className="frow__pair">
            <span className="frow__k">wanted</span>
            <span className="frow__v mono">{row.groundTruth}</span>
          </div>
          <div className="frow__pair">
            <span className="frow__k">came back</span>
            <span className="frow__v mono">
              {row.returned.length ? row.returned.join('  ') : <i>nothing</i>}
            </span>
          </div>
          <div className="frow__foot">
            {/* THE BAND A TIE LEAVES THE TRUE RANK IN. `score_recall` computes
                both ends because a rank read off a tie is not a reading of the
                retriever, and the two being equal is how a reader knows the
                answer was the retriever's. */}
            {row.bestPossibleRank !== null && row.worstPossibleRank !== null ? (
              <span className="frow__by">
                rank{' '}
                <b className="mono">
                  {row.bestPossibleRank === row.worstPossibleRank
                    ? row.bestPossibleRank
                    : `${row.bestPossibleRank}–${row.worstPossibleRank}`}
                </b>
                {row.bestPossibleRank !== row.worstPossibleRank
                  ? ' — a score tie, not the retriever'
                  : ''}{' '}
                against k=<span className="mono">{k}</span>
              </span>
            ) : null}
            {row.matchedBy ? (
              <span className="frow__by">
                matched by <b>{row.matchedBy}</b>
              </span>
            ) : null}
            {row.level ? (
              <span className="frow__by">
                at the <b>{row.level}</b> level
              </span>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/**
 * `answer_in_passage_rate`, which is never recall.
 *
 * Grey, not red — nothing failed and the proxy is a real count. What the block
 * is for is the sentence: the engine's own paragraph naming the two directions
 * it comes apart in, rendered in full and never summarised, because a number
 * that is usually close to the right one is the most dangerous kind. The rate
 * and the warning are one component for the reason `EvalCard`'s `SelfGraded`
 * is one component: the disclosure cannot be dropped without dropping the
 * figure.
 */
function Proxy({ proxy }: { proxy: AnswerInPassage }) {
  return (
    <div className="proxy">
      <div className="proxy__head">
        <Icon name="eye" size={13} />
        <span className="proxy__title">
          A second and <b>weaker</b> reading was asked for
        </span>
        <GreyPill word="NOT RECALL" />
      </div>
      <div className="proxy__figure">
        <span className="proxy__v mono">{pct(proxy.rate, 1)}</span>
        <span className="proxy__k mono">{proxy.name}</span>
        <span className="proxy__on">
          {proxy.hits} of {proxy.of} rows, from{' '}
          <span className="mono">{proxy.answerField ?? '?'}</span>, at k=
          {proxy.k ?? '?'}
        </span>
      </div>
      <p className="proxy__says">{proxy.isNotRecall}</p>
      {proxy.provenance ? <p className="proxy__prov">{proxy.provenance}</p> : null}
    </div>
  );
}

function RecallFacts({ report }: { report: RecallReport }) {
  const levels = Object.entries(report.levels);
  const matched = Object.entries(report.matchedBy);
  return (
    <Disclosure
      title="How this was run"
      summary={`index ${report.indexId ?? '?'} · k=${report.k} · BM25 on this machine`}
    >
      {report.indexName ? (
        <Fact k="index" v={`${report.indexName} (${report.indexId ?? '?'})`} />
      ) : null}
      {report.evalPath ? <Fact k="eval_path" v={report.evalPath} /> : null}
      {report.questionField ? (
        <Fact k="question_field" v={report.questionField} />
      ) : null}
      {report.groundTruthField ? (
        <Fact
          k="ground_truth_field"
          v={`${report.groundTruthField}${report.groundTruthChosenHow ? ` — ${report.groundTruthChosenHow}` : ''}`}
        />
      ) : null}
      {levels.length > 0 ? (
        <Fact
          k="levels"
          v={levels.map(([name, count]) => `${name} ${count}`).join(' · ')}
        />
      ) : null}
      {matched.length > 0 ? (
        <Fact
          k="matched_by"
          v={matched.map(([name, count]) => `${name} ${count}`).join(' · ')}
        />
      ) : null}
      {report.resolution.method ? (
        <Fact k="resolution.method" v={report.resolution.method} />
      ) : null}
      {report.scorer ? <Fact k="scorer" v={report.scorer} /> : null}
      <Fact k="stampable" v={report.stampable ? 'true' : 'false'} />
      {report.decidesNothing ? (
        <p className="runfacts__note">{report.decidesNothing}</p>
      ) : null}
    </Disclosure>
  );
}
