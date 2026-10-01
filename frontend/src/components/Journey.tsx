/**
 * The journey overview — the route a person is on, and the one thing next.
 *
 * `docs/PHASES.md` "The Journey Overview", J2. Max, relayed 2026-09-02:
 * *"launching a journey overview... with easy interactable tools, and simple
 * prompting and instruction."* `playbook.json` has held the five routes since
 * 2026-08-30 and `train_on_my_files` is seventeen ordered steps; until now the
 * route existed as data and every step of it was reachable only by knowing
 * which of sixty-seven tools to reach for.
 *
 * THE HUE BUDGET OF THIS SURFACE, counted. Green (--fits) marks a step that is
 * done and nothing else. Cobalt (--accent) marks exactly one thing: the step
 * you are on, because the accent means "the product needs you" and here it
 * literally does. Amber, red and blue appear nowhere: a route has no verdicts.
 * Gold stays what it is everywhere else — selection — and this surface selects
 * nothing, so it does not appear either.
 *
 * WHAT THIS DRAWS AND WHAT IT REFUSES TO DRAW. `done_elsewhere` is its own
 * state with its own words — "met by run_eval" — rather than a tick, because a
 * tick would claim a tool ran that never ran. `app/journey.py` explains why
 * that distinction is the whole design; this file's job is not to collapse it
 * back into a checkbox on the way to the screen.
 */

import type {
  BlockedBy,
  JourneyOutcome,
  Readiness,
  JourneyPayload,
  JourneyStep,
  JourneyVerdict,
  Prefilled,
} from '../lib/engine/journey';
import { useState } from 'react';

import { Icon, type IconName } from './Icon';
import './Journey.css';

/* `ahead` gets no glyph on purpose: a step nobody has reached has nothing to
   report, and a dot for it would be one more mark competing with the check
   and the chevron that do mean something. CSS draws its hollow ring. */
const STATE_ICON: Record<JourneyStep['state'], IconName | null> = {
  done: 'check',
  done_elsewhere: 'check',
  /* NOT a check. This step did not happen and saying it did would be a claim
     about work nobody performed - the whole reason the state exists. An `x`
     reads as failure, so it takes the same quiet dash the design uses for a
     thing that is simply absent. */
  not_needed: 'x',
  next: 'chevright',
  ahead: null,
};

/** A score as a whole percent, or an em dash. The engine's own number,
 *  rounded for reading and never recomputed. */
function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${Math.round(value * 100)}%`;
}

/** The step's state as a sentence, for the row's accessible name.
 *
 *  The mark is `aria-hidden` - it is a shape - so before this the state
 *  reached a screen reader not at all: every row announced its tool and
 *  nothing about whether it was done, next, or untouched. `done_elsewhere`
 *  says MET BY and names the tool, because collapsing it to "done" here would
 *  undo, for anyone listening, the distinction the whole engine keeps.
 */
function stateInWords(step: JourneyStep): string {
  if (step.state === 'next') return 'you are here';
  if (step.state === 'done') return 'done';
  if (step.state === 'ahead') return 'not started';
  if (step.state === 'not_needed') {
    const by = step.unnecessary_because;
    return by ? `not needed here, ${by} covered it` : 'not needed here';
  }
  const by = step.satisfied_by?.tool;
  return by ? `met by ${by}` : 'met by another tool';
}

/** A tool name as a person reads it: `carve_eval_set` → "Carve eval set". */
function toolLabel(tool: string): string {
  const words = tool.replace(/_/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function when(stamp: string | null): string | null {
  if (!stamp) return null;
  /* The engine's own `CURRENT_TIMESTAMP`, which is UTC and has no zone on it.
     Shown as the date it carries rather than converted, because inventing a
     zone for a stamp that does not name one is inventing information. */
  return stamp.replace('T', ' ').slice(0, 16);
}

export function Journey({
  payload,
  loading,
  error,
  onDoStep,
  onRunStep,
  onChooseJourney,
}: {
  payload: JourneyPayload | null;
  loading?: boolean;
  error?: string | null;
  /** Take me to the thing that does this step. The overview never RUNS a tool
   *  itself - it is a reader, and a reader that ran something would be writing
   *  into the thread it is reading. It opens the control instead, expanded,
   *  with its fields empty: what goes in them is the person's to say, and a
   *  path this product guessed at would be the one number it cannot measure. */
  onDoStep?: (tool: string, prefill: Record<string, Prefilled>) => void;
  /** Run a ready step from the button. Resolves with what the engine said -
   *  including a refusal, which is shown in the flow rather than thrown. */
  onRunStep?: (
    tool: string,
    prefill: Record<string, Prefilled>,
    approved: boolean,
  ) => Promise<{ ok: boolean; detail?: string }>;
  /** Put this thread on a route. Absent in read-only surfaces, and then the
   *  routes are listed rather than offered - a button that did nothing would
   *  be a promise this surface cannot keep. */
  onChooseJourney?: (journey: string) => void;
}) {
  if (error && !payload) {
    return <p className="jrn__empty">The route could not be read: {error}</p>;
  }
  if (!payload) {
    if (loading) return <p className="jrn__empty">Reading the route…</p>;
    /* Found on a stranger walk by reading all eight panes side by side. Every
       sibling says what is missing AND the way out - Files offers "Open a
       thread, or pick a project in the rail". This one said "No conversation
       open." and stopped, which names the gap and leaves the reader holding
       it. A pane with nothing in it is the one that most needs to say what
       would put something there. */
    return (
      <p className="jrn__empty">
        No conversation open. Start a thread, or pick one in the sidebar, and this pane shows
        the route it is on, which step is next, and what is blocking it.
      </p>
    );
  }

  if (!payload.journey) {
    return (
      <div className="jrn">
        <p className="jrn__say">{payload.say}</p>
        <div className="jrn__routes">
          <span className="jrn__eyebrow">
            {onChooseJourney ? 'pick one to start' : 'the routes that exist'}
          </span>
          {/* CHOOSING IS A CLICK NOW. These five have been listed since the
              pane shipped and none of them was choosable: a person who could
              SEE the route they wanted still had to guess a sentence the
              keyword matcher would agree with. Picking one records the ROUTE
              and leaves the goal alone - the goal is their own words, and a
              menu pick is not those. */}
          <ul>
            {payload.journeys_available.map((name) => (
              <li key={name}>
                {onChooseJourney ? (
                  <button type="button" className="jrn__pick" onClick={() => onChooseJourney(name)}>
                    {toolLabel(name)}
                  </button>
                ) : (
                  toolLabel(name)
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    );
  }

  const pct = payload.total === 0 ? 0 : Math.round((payload.done_n / payload.total) * 100);
  return (
    <div className="jrn">
      <header className="jrn__head">
        <div className="jrn__title">
          <Icon name="branch" />
          <span>{toolLabel(payload.journey)}</span>
          {payload.journey_origin === 'matched' ? (
            <span
              className="jrn__inferred"
              title={`Matched from this conversation's own words: ${payload.matched_on.join(', ')}`}
            >
              inferred
            </span>
          ) : null}
        </div>
        <span className="jrn__count">
          {payload.done_n} of {payload.total}
        </span>
      </header>

      {payload.says ? <p className="jrn__says">{payload.says}</p> : null}

      <div
        className="jrn__bar"
        role="img"
        aria-label={`${payload.done_n} of ${payload.total} steps done`}
      >
        <i style={{ width: `${pct}%` }} />
      </div>

      {payload.verdict ? <Verdict verdict={payload.verdict} /> : <NoVerdictYet />}
      {payload.outcome ? <Outcome outcome={payload.outcome} /> : null}

      <ol className="jrn__steps">
        {payload.steps.map((step) => (
          <li
            key={step.ordinal}
            className="jrn__step"
            data-state={step.state}
            aria-label={`Step ${step.ordinal} of ${payload.total}: ${toolLabel(step.tool)} — ${stateInWords(step)}`}
          >
            <span className="jrn__mark" aria-hidden="true">
              {STATE_ICON[step.state] ? <Icon name={STATE_ICON[step.state]!} size={12} /> : null}
            </span>
            <span className="jrn__ord">{step.ordinal}</span>
            <div className="jrn__body">
              <div className="jrn__line">
                <span className="jrn__tool">{toolLabel(step.tool)}</span>
                {step.needs_approval ? (
                  <span className="jrn__approval" title="This one asks you before it runs">
                    asks first
                  </span>
                ) : null}
                {/* THE "you are here" CHIP IS GONE, and its absence is the
                    point. It was a third accent element saying what the mark
                    and the button already said - §3.4 allows one per screen,
                    and the button is where the product genuinely needs a
                    person. The words survive where they were missing entirely:
                    in the row's accessible name. */}
              </div>
              <p className="jrn__why">{step.why}</p>
              {/* A LINE, NOT AN ESSAY. Caught by a screenshot and by nothing
                  else: `make_sandbox` answers with eleven lines about pinned
                  requirements, interpreters and egress, and drawn in full it
                  swallowed the whole route around it. Clamped to two lines
                  with the full text on hover - the summary is the tool's own
                  and none of it is thrown away, it just stops being the
                  loudest thing on a surface about seventeen other steps. */}
              {step.produced ? (
                <p className="jrn__produced" title={step.produced}>
                  {step.produced}
                </p>
              ) : null}
              {step.state === 'not_needed' ? (
                <p className="jrn__met">
                  not needed here{step.unnecessary_because ? <> — <b>{step.unnecessary_because}</b> covered it</> : null}
                </p>
              ) : null}
              {step.state === 'done_elsewhere' && step.satisfied_by ? (
                <p className="jrn__met">
                  met by <b>{step.satisfied_by.tool}</b> — it recorded{' '}
                  {step.satisfied_by.facts.join(', ')}
                </p>
              ) : null}
              {step.state === 'next' ? <p className="jrn__hint">{step.args_hint}</p> : null}
              {/* WHAT HAPPENED WHEN YOU TRIED, and it is deliberately not an
                  alarm. Bare right/wrong feedback measures d = 0.05 and
                  DISCOURAGING feedback is negative at -0.14; what works is
                  saying why and what next (0.49, and 0.99 when it is
                  specific). This product's refusals are already written that
                  way - "needs an approval before it can run... it is a person
                  saying yes to this specific action" - so the tool's own
                  sentence is the highest-information thing available and it
                  was being thrown away. Neutral ink, no red, no cross. */}
              {step.attempted?.detail ? (
                <p className="jrn__tried">
                  <span className="jrn__triedmark">tried</span>
                  {step.attempted.detail}
                </p>
              ) : null}
              {/* WHAT A STEP ALREADY KNOWS IS INFORMATION, NOT AN ACTION, so it
                  is drawn on every step that has it rather than only on the one
                  you are on. Thread 33 is why: it is thirteen steps of
                  seventeen done, it skipped the first five because it arrived
                  with data already carved, and its `next` is therefore step 1.
                  Showing this line only there would have hidden the fact that
                  step 17 is holding a sandbox name and a baseline run id and is
                  ready to go. */}
              {Object.keys(step.prefill).length > 0 && step.state !== 'done' ? (
                <p className="jrn__knows">
                  opens knowing{' '}
                  {Object.entries(step.prefill).map(([field], i) => (
                    <span key={field}>
                      {i > 0 ? ', ' : ''}
                      <b>{field}</b>
                    </span>
                  ))}
                </p>
              ) : null}
              {/* THE RUN CONTROL FOLLOWS WHAT CAN BE PRESSED, not what is
                  next in the list. A workspace that arrived with graded rows
                  makes step 2 (`carve_rows`) ask for a folder of markdown it
                  does not have, and anchoring the only action there left the
                  route pointing at something that could not happen while
                  three later steps sat ready. One primary control still - the
                  next POSSIBLE one. A blocked `next` keeps its own line
                  saying what it wants, which is information, not a rival. */}
              {step.ordinal === payload.next_runnable?.ordinal ? (
                <StepAction step={step} onDoStep={onDoStep} onRunStep={onRunStep} />
              ) : step.state === 'next' && onDoStep ? (
                <button
                  type="button"
                  className="jrn__pick"
                  onClick={() => onDoStep(step.tool, step.prefill)}
                >
                  {step.readiness.missing.length > 0
                    ? `Fill in ${step.readiness.missing.join(', ')}`
                    : 'Open this step'}
                </button>
              ) : null}
              {when(step.ran_at) ? (
                <p className="jrn__stamp">
                  {when(step.ran_at)}
                  {step.driven_by ? ` · run by ${step.driven_by === 'user' ? 'you' : 'the model'}` : ''}
                  {step.evidence === 'ledger' ? ' · from the fact it recorded' : ''}
                </p>
              ) : step.evidence === 'ledger' && step.state === 'done' ? (
                <p className="jrn__stamp">recorded on the ledger by this step's own tool</p>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

/**
 * What came out the other end, drawn where a person cannot miss it.
 *
 * The verdict is the ENGINE'S, quoted with the two run ids behind it. Nothing
 * here decides whether a difference is real - `evals.compare` did, with
 * McNemar's exact test, and a second opinion computed in a browser would
 * disagree with the first the day either changed.
 *
 * NO EVIDENCE is drawn as calmly as a win, and that is the point: this
 * product exists to be able to say a training run bought nothing, and a
 * surface that greyed that answer out while celebrating the other would be
 * arguing with its own thesis.
 */
function Outcome({ outcome }: { outcome: JourneyOutcome }) {
  const better = (outcome.delta ?? 0) > 0;
  const resolved = outcome.resolved === true;
  return (
    <section className="jrn__outcome" data-verdict={outcome.verdict ?? 'unknown'}>
      <div className="jrn__oline">
        <span className="jrn__overdict">
          {resolved ? (better ? 'BETTER' : 'WORSE') : 'NO EVIDENCE'}
        </span>
        <span className="jrn__odelta">
          {pct(outcome.score)} <span className="jrn__ovs">vs</span> {pct(outcome.baseline_score)}
          {/* Two percentages with no n are not a comparison a reader can weigh:
              7% against 13% is a different claim on 30 rows than on 300. The
              denominator travels with the number, and the engine already
              measured it - the card was simply dropping it. */}
          {typeof outcome.paired_rows === 'number' ? (
            <span className="jrn__oden"> on {outcome.paired_rows} paired rows</span>
          ) : null}
        </span>
        <span className="jrn__oruns">
          run {outcome.adapter_run_id} against {outcome.baseline_run_id}
        </span>
      </div>
      {outcome.says ? <p className="jrn__osays">{outcome.says}</p> : null}
      {/* "NO EVIDENCE" is the one verdict that leaves the reader without a next
          move, so the row count that would settle it is worth showing - but
          only when nothing else is already saying it. The engine's own `says`
          states it as rows still to grade (403) where this states the total
          (433); both on screen is one fact wearing two numbers, which is worse
          than either alone. A screenshot caught this; the tests could not. */}
      {!resolved && !outcome.says && typeof outcome.rows_that_would_resolve_this_delta === 'number' ? (
        <p className="jrn__onext">
          A delta this size would need about{' '}
          <b>{outcome.rows_that_would_resolve_this_delta}</b> paired rows to separate from chance.
        </p>
      ) : null}
    </section>
  );
}

/**
 * The ledger's answer, on the route rather than two panes away.
 *
 * THE DO-NOT-TRAIN ANSWER IS THE PRODUCT, so it is drawn first and drawn
 * plainly - above the adapter's score, because a person who has been told not
 * to train should read that before they read what training got them.
 *
 * It carries the gate count because a verdict is only worth what the gates
 * behind it are worth, and `NOT REACHED` gates are the honest reason a route
 * can end early. The wording is the engine's own `say`, never a paraphrase:
 * this surface has no opinion about training and is not the place to acquire
 * one.
 */
/** The card that stands where a verdict will be, before one exists.
 *
 *  Found on the design-model walk. A fresh route draws all seventeen steps and
 *  then nothing: no outcome, no gate count, no rule. The same route on a thread
 *  where one tool had run showed "0 of 5 gates passed" and named the rule that
 *  comes first. From the reader's side those two screens are indistinguishable
 *  in the way that matters - they cannot tell whether the harness has no
 *  opinion yet or simply is not showing the one it has, and those call for
 *  different next moves.
 *
 *  So the absence gets a card of its own, saying what produces a verdict rather
 *  than only that there is not one, for the same reason every other empty
 *  surface here does.
 *
 *  ITS WORDING SURVIVED A SECOND WALK AND THE FIRST DRAFT DID NOT. That draft
 *  ended "Run a step above - or tell the harness where your material is". A
 *  person who had just attached their folder saw the counter read 1 of 17 and,
 *  underneath it, advice to do the thing they had done. Attaching a folder
 *  records a location, and a gate opens on a measured fact, so the honest line
 *  names that difference instead of naming an action.
 *
 *  IT STATES NO DENOMINATOR, AND THAT IS THE POINT. The first draft of this
 *  card read "0 of 5 gates reached", which is true of the machine-learning
 *  ledger and false of the harness-design one, which declares six. With no
 *  verdict there is no `gates_total` to read, so the honest line names no
 *  total at all - inventing one here, in the card that exists because a
 *  denominator was missing, would have been the exact failure this surface is
 *  supposed to prevent.
 */
function NoVerdictYet() {
  return (
    <section className="jrn__verdict jrn__verdict--none">
      <div className="jrn__vline">
        <span className="jrn__vname">NO VERDICT YET</span>
        <span className="jrn__vgates">no gate reached</span>
      </div>
      <p className="jrn__vsays">
        Nothing has been measured in this conversation, so the ledger has not been asked
        anything. A verdict appears as soon as a step records a fact — running one that only
        says where your material lives records a location, not a measurement.
      </p>
    </section>
  );
}

function Verdict({ verdict }: { verdict: JourneyVerdict }) {
  return (
    <section className="jrn__verdict" data-trains={verdict.trains || undefined}>
      <div className="jrn__vline">
        <span className="jrn__vname">{verdict.outcome}</span>
        <span className="jrn__vgates">
          {verdict.gates_passed} of {verdict.gates_total} gates passed
        </span>
      </div>
      {verdict.say ? <p className="jrn__vsays">{verdict.say}</p> : null}
      {verdict.blocked_by ? <Blocking blocked={verdict.blocked_by} /> : null}
    </section>
  );
}

/**
 * The rule that stopped the route, drawn the way the research lane built it:
 * the rule, the value, its origin — `10-Signals/specs/refusal-formats.md` §1.
 *
 * The route already named the outcome and counted gates, which is the WHAT.
 * This is the why, and every line of it is the ledger's own: the gate id and
 * its clause come from the diagnosis, the facts are the ones that clause
 * names, and each value carries the origin the ledger stamped on it.
 *
 * A FACT NOBODY MEASURED READS AS UNANSWERED, NOT AS FALSE. It is the
 * commonest refusal on this route - `baseline_score is not null` fails because
 * nobody has scored anything yet, not because a score came back empty - and a
 * screen that conflated the two would teach the wrong lesson about what a gate
 * is doing.
 */
function Blocking({ blocked }: { blocked: BlockedBy }) {
  // A gate the engine never evaluated is not a gate that failed. Naming the
  // first unchecked rule "the rule that stopped this" would be a lie the
  // reader could act on, so the two states get different words and the
  // unreached one says plainly that nothing has been checked yet.
  const stopped = blocked.reached;
  return (
    <div className={stopped ? "jrn__rule" : "jrn__rule jrn__rule--unreached"}>
      <div className="jrn__rulerow">
        <span className="jrn__rulek">{stopped ? "stopped at" : "first rule"}</span>
        <b>{blocked.gate}</b>
        <span className="jrn__rulecount">
          {blocked.checked} of {blocked.of} gates checked
        </span>
      </div>
      {!stopped && (
        <div className="jrn__rulenote">
          Nothing failed. The route stopped before any gate was evaluated, so this is the rule
          that comes first, not one that was broken.
        </div>
      )}
      <div className="jrn__rulerow">
        <span className="jrn__rulek">rule</span>
        {blocked.class_undecided ? (
          <span className="jrn__unmeasured">
            depends on the method class, which this run has not chosen yet
          </span>
        ) : (
          <span>{blocked.clause}</span>
        )}
      </div>
      {blocked.reads.map((read) => (
        <div className="jrn__rulerow" key={read.fact}>
          <span className="jrn__rulek">{read.fact}</span>
          {read.unmeasured ? (
            <span className="jrn__unmeasured">nothing has measured this yet</span>
          ) : (
            <span title={read.how ?? undefined}>
              <b>{String(read.value)}</b> <span className="jrn__ruleorigin">{read.origin}</span>
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

/**
 * The control on the step you are on, and it is three controls wearing one
 * name because a route has three honest answers rather than one.
 *
 *   click    every argument is on the record. The button RUNS it. No form -
 *            the goal's acceptance is explicit that a form here is the design
 *            failure, and for seven of this route's seventeen steps there is
 *            genuinely nothing to fill in.
 *   approve  the same, and the tool wants a person to say yes. Two clicks,
 *            deliberately: `Registry.call`'s rule is that approval "is a
 *            person saying yes to THIS specific action", so a button that
 *            sent `approved: true` by itself would be laundering it. The
 *            second click is the yes, and what it will do is on screen when
 *            it is given.
 *   needs    something only the person can give. The button NAMES it rather
 *            than opening a form and letting them discover it.
 *
 * A REFUSAL LANDS HERE, NOT IN A DIALOG. That is the whole point of the
 * flow: the engine's refusals are already written as remedies, and the
 * evidence says bare failure feedback measures d = 0.05 while "why and what
 * next" reaches 0.49. So a "no" renders in place, in the tool's own words,
 * with the step still there to try again.
 */
function StepAction({
  step,
  onDoStep,
  onRunStep,
}: {
  step: JourneyStep;
  onDoStep?: (tool: string, prefill: Record<string, Prefilled>) => void;
  onRunStep?: (
    tool: string,
    prefill: Record<string, Prefilled>,
    approved: boolean,
  ) => Promise<{ ok: boolean; detail?: string }>;
}) {
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const mode: Readiness['mode'] = step.readiness?.mode ?? 'needs';

  const run = async (approved: boolean) => {
    if (!onRunStep) return;
    setBusy(true);
    setRefused(null);
    const answer = await onRunStep(step.tool, step.prefill, approved);
    setBusy(false);
    setConfirming(false);
    if (!answer.ok) {
      /* EVEN THE FALLBACK CARRIES A NEXT ACTION. The first draft read "It did
         not run, and said nothing about why." - which is a bare failure, the
         d = 0.05 case, and the exact thing this route exists not to do. If a
         tool ever refuses without a sentence, the honest line still points
         somewhere a person can look. */
      setRefused(
        answer.detail ??
          'It did not run and gave no reason. The Evidence pane holds what the ' +
            'engine recorded for this thread, and the tool can be run from ' +
            'Controls with its arguments visible.',
      );
    }
  };

  if ((mode === 'click' || mode === 'approve') && onRunStep) {
    return (
      <>
        {confirming ? (
          <div className="jrn__confirm">
            <p className="jrn__confirmsay">
              This one asks first. It will run <b>{step.tool}</b>
              {Object.keys(step.prefill).length > 0
                ? ` with ${Object.keys(step.prefill).join(', ')} as shown above.`
                : '.'}
            </p>
            <div className="jrn__confirmrow">
              <button type="button" className="jrn__do" disabled={busy} onClick={() => void run(true)}>
                {busy ? 'Running…' : 'Yes, run it'}
              </button>
              <button type="button" className="jrn__pick" onClick={() => setConfirming(false)}>
                Not now
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="jrn__do"
            disabled={busy}
            onClick={() => (mode === 'approve' ? setConfirming(true) : void run(false))}
          >
            {busy ? 'Running…' : mode === 'approve' ? 'Review and run' : 'Run this step'}
            <Icon name="chevright" size={12} />
          </button>
        )}
        {/* ONLY IF THE STEP IS NOT ALREADY SAYING IT. A refusal that came
            back through the button is usually the same sentence the engine
            then reports as `attempted` on the next read, and drawing both
            printed it twice - caught by a screenshot, invisible to every
            assertion. The local copy still earns its place: a refusal that
            RAISES (an approval 428, a rejected argument) leaves no event row
            at all, so the engine never learns of it and this is the only
            place it can appear. */}
        {refused && refused.trim() !== (step.attempted?.detail ?? '').trim() ? (
          <p className="jrn__tried">
            <span className="jrn__triedmark">tried</span>
            {refused}
          </p>
        ) : null}
      </>
    );
  }

  if (!onDoStep) return null;
  const wants = step.readiness?.missing ?? [];
  return (
    <button type="button" className="jrn__do" onClick={() => onDoStep(step.tool, step.prefill)}>
      {wants.length > 0 ? `Fill in ${wants.join(', ')}` : 'Do this step'}
      <Icon name="chevright" size={12} />
    </button>
  );
}
