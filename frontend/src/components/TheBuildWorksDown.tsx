/**
 * THE LOOP MAX ASKED FOR, drawn as the one control that can stop it.
 *
 * *"I just put build plan, and it sets that. We have like a... we create a goal
 * tool, which basically just sets an autonomous loop running to kinda keep the
 * model working through the goal in detail."*
 *
 * The decision of whether to run another turn is not here - it is
 * `lib/theBuildKeepsGoing.ts`, which is a pure function with its own tests,
 * because a stop condition that only exists inside a `useEffect` is a stop
 * condition nobody can check. This component is the effect, the counter and
 * the button.
 *
 * ## THERE ARE TWO LOOPS NOW, AND THE OWNER ASKED FOR THE SECOND
 *
 * This one is the browser's: it continues a build after the person has spoken,
 * and it stops when the window closes. That property was argued for here and
 * the argument still holds for what it covers - the thing that spends an hour
 * of a local model is the thing the person is looking at.
 *
 * It is not enough for the thing Max asked for on 2026-09-13: *"some sort of
 * long running tasks structure, executed from the plan... after each section
 * is finished and pushed back, the to-do keeps executing."* A to-do list that
 * dies when a window closes is not a long-running task. So the RUN lives in
 * the engine (`app/longrun.py`) and this chip starts and stops it.
 *
 * The old objection - a driver inside the engine keeps going with nobody
 * watching - is answered rather than ignored: a run is started by a person and
 * by nothing else, it has a turn cap it reports, its stop is a row in a table
 * so any window can end it, and every turn it takes writes the same events the
 * transcript already draws. While a run is live this browser loop stands down,
 * because two loops sending turns into one thread is the one shape neither
 * could be reasoned about.
 *
 * ## WHAT IT NEVER DOES
 *
 * It never posts a message. The transcript shows what the person actually said,
 * and "continue" typed by nobody would be a lie in the one record that is meant
 * to be evidence. `POST /api/threads/{id}/turn` runs a turn with no message,
 * which is exactly the shape this needs.
 */

import { useEffect, useRef, useState } from 'react';

import {
  anApprovalIsWaiting,
  MOST_TURNS_WITHOUT_A_PERSON,
  shouldRunAnotherTurn,
  stepsIn,
  type Seen,
} from '../lib/theBuildKeepsGoing';
import { saveThreadReport, stopTurn } from '../lib/engine/client';
import { useRun } from '../lib/useRun';
import { hasNativeShell } from '../lib/engine/shell';
import { Icon } from './Icon';

export function TheBuildWorksDown({
  threadId,
  mode,
  plan,
  items,
  running,
  failed,
  lastEventId,
  onContinue,
}: {
  threadId: number;
  mode: string;
  plan: string | null;
  items: Seen[];
  running: boolean;
  failed: boolean;
  /** The thread's newest event id. Every turn a run takes writes events, so
   *  this moving is the run progressing - which is why the run is read off
   *  it rather than off a timer. */
  lastEventId: number;
  onContinue: () => Promise<void>;
}) {
  const [taken, setTaken] = useState(0);
  const [stopped, setStopped] = useState(false);
  /* A turn is started inside an effect, so a second render while it is in
     flight must not start a second one. `running` flips a tick later than the
     call does. */
  const inFlight = useRef(false);

  /* A new thread, or a person speaking, is a fresh budget. `items.length` and
     the user rows in it are how this notices the person came back. */
  const spoke = items.filter((item) => item.kind === 'user').length;
  const wasSpoken = useRef(spoke);
  useEffect(() => {
    if (spoke !== wasSpoken.current) {
      wasSpoken.current = spoke;
      setTaken(0);
      setStopped(false);
    }
  }, [spoke]);
  useEffect(() => {
    setTaken(0);
    setStopped(false);
  }, [threadId]);

  const run = useRun(threadId, lastEventId);

  const verdict = shouldRunAnotherTurn({
    mode,
    plan,
    items,
    running,
    awaitingApproval: anApprovalIsWaiting(items),
    failed,
    taken,
    /* THE BROWSER LOOP STANDS DOWN WHILE THE ENGINE RUN IS LIVE. Two loops
       posting turns into one thread would each see the other's turn as its
       own and neither could be reasoned about. */
    stopped: stopped || run.live,
  });

  useEffect(() => {
    if (!verdict.go || inFlight.current) return;
    inFlight.current = true;
    setTaken((count) => count + 1);
    void onContinue().finally(() => {
      inFlight.current = false;
    });
    /* WHY `running` AND `taken` ARE IN THE LIST, stated as what was actually
       checked. The loop re-fires because `verdict.go` itself goes true,
       false, true across a continuation - it is false while a turn runs -
       and each of those transitions is a dependency change. So
       `[verdict.go, onContinue]` does loop, and the test below passes
       against it; I thought otherwise and was wrong.

       These two stay because the re-fire should not DEPEND on that toggle.
       If the promise ever settles without React rendering the `running`
       true in between - a faster engine, a batching change, a caller that
       does not flip the flag - `go` never changes value and the only thing
       left that differs is `taken`. Both are read in the effect's own
       closure, so listing them is also what the exhaustive-deps rule asks
       for. It is insurance, not a fix, and calling it a fix would put a
       bug that was never demonstrated into the record. */
  }, [verdict.go, running, taken, onContinue]);

  /* THE REPORT WRITES ITSELF. Max, 2026-09-12: "save the journey report into
     this project's folder on disk - it should automatically save, you
     shouldn't have to even click that." The moment every step of a plan
     is ticked in the shell, the report is written into the project folder,
     once per thread; the Journey pane's save button is gone. */
  const steps = stepsIn(plan);
  const finished = mode === 'build' && steps.done > 0 && steps.open === 0;
  const [reported, setReported] = useState<{ thread: number; detail: string } | null>(null);
  useEffect(() => {
    if (!finished || !hasNativeShell() || reported?.thread === threadId) return;
    let cancelled = false;
    void saveThreadReport(threadId)
      .then((outcome) => {
        if (!cancelled) setReported({ thread: threadId, detail: outcome.detail });
      })
      .catch(() => {
        if (!cancelled) setReported({ thread: threadId, detail: 'the report could not be written' });
      });
    return () => {
      cancelled = true;
    };
  }, [finished, threadId, reported?.thread]);

  if (mode !== 'build' || !plan || !plan.trim()) return null;

  /* THE RUN, WHICH IS THE LONG-RUNNING HALF. While it is live this chip is
     its dashboard and the browser loop above is dormant. */
  if (run.live) {
    const state = run.run;
    return (
      <div className="buildloop" data-working="yes">
        <Icon name="run" />
        <span className="buildloop__why">
          Working the plan
          {typeof state?.open === 'number'
            ? ` \u00b7 ${state.done} done, ${state.open} left`
            : ''}
          {state?.parked?.length ? ` \u00b7 ${state.parked.length} parked` : ''}
        </span>
        <button
          type="button"
          className="buildloop__stop"
          disabled={run.busy}
          onClick={() => void run.stop()}
          title="Stop after the turn that is running. A turn already in flight finishes and is recorded."
        >
          Stop
        </button>
      </div>
    );
  }

  const finishedRun =
    run.run && run.run.state && run.run.state !== 'running' ? run.run : null;
  const done = taken > 0 && !verdict.go && !running;
  /* The loop is stopped and there is still work in the plan: offer the one
     turn rather than only the whole run. */
  const canPushOneTurn = !verdict.go && !running && !stopped && stepsIn(plan).open > 0;
  return (
    <div className="buildloop" data-working={verdict.go || running ? 'yes' : 'no'}>
      <Icon name={verdict.go || running ? 'play' : 'check'} />
      {/* HOW FAR DOWN THE PLAN IS, at a glance. Counts alone make "6 done, 12
          left" and "12 done, 6 left" read the same at speed. The bar is the
          Ramp Kit's task-row idiom (usebastion.io/design, `tasks:brackets`)
          in this product's own tokens: filled for done, the rest hollow, and
          a fraction beside it. Drawn only when there is a plan to be down. */}
      {steps.done + steps.open > 0 ? (
        <span
          className="buildloop__rail"
          title={`${steps.done} of ${steps.done + steps.open} steps done`}
        >
          <span className="buildloop__railtrack" aria-hidden="true">
            <span
              className="buildloop__railfill"
              style={{
                width: `${Math.round((steps.done / (steps.done + steps.open)) * 100)}%`,
              }}
            />
          </span>
          <span className="buildloop__railnum num">
            {steps.done}/{steps.done + steps.open}
          </span>
        </span>
      ) : null}
      <span className="buildloop__why">
        {running
          ? `Working the plan \u00b7 ${steps.done} done, ${steps.open} left`
          : done
            ? `${verdict.why} - ${taken} of ${MOST_TURNS_WITHOUT_A_PERSON}`
            : verdict.why}
      </span>
      {running || verdict.go ? (
        <button
          type="button"
          className="buildloop__stop"
          onClick={() => {
            /* BOTH HALVES, because "Stop" means stop. This used to set a
               local flag only - it ended the frontend's keep-going loop and
               left the engine's turn streaming, which is what Max watched on
               his GPU on 2026-09-19 while the card said stopped. The flag
               still ends the loop; `stopTurn` ends the turn in flight at its
               next round boundary, and the run with it. A tool already
               running finishes and is recorded - see app/interrupt.py. */
            setStopped(true);
            void stopTurn(threadId).catch(() => undefined);
          }}
          title="Stop now. The turn ends after the step it is on - a tool already running finishes and is recorded - and the loop does not start another."
        >
          Stop
        </button>
      ) : null}
      {canPushOneTurn ? (
        <button
          type="button"
          className="buildloop__resume"
          onClick={() => {
            /* ONE TURN, BY HAND. Whatever stopped the loop - a question,
               a failed turn, the ceiling - there are still open steps, and
               the person can spend one turn on the next one without
               restarting the whole run. The ordinary rule applies again to
               whatever that turn does. */
            setTaken((count) => count + 1);
            void onContinue();
          }}
          title="Work the next open step once. The loop stopped, and this spends a single turn on it without starting the run again."
        >
          Continue
        </button>
      ) : null}
      {stopped ? (
        <button
          type="button"
          className="buildloop__resume"
          onClick={() => {
            setTaken(0);
            setStopped(false);
          }}
          title="Work down the plan again, from a fresh budget of turns."
        >
          Resume
        </button>
      ) : null}

      {/* START THE RUN. One press, and the engine takes turns until every
          step is ticked or parked - `app/longrun.py`. Offered whenever a
          step is open, including after the browser loop has stopped. */}
      {steps.open > 0 && !running ? (
        <button
          type="button"
          className="buildloop__resume buildloop__run"
          disabled={run.busy}
          onClick={() => void run.start()}
          title={
            'Work the whole plan down in the engine: one turn per step, ' +
            'until every step is ticked or parked. It keeps going if you ' +
            'close this window, and stops on an approval, a failed ' +
            'connection or the turn cap.'
          }
        >
          <Icon name="play" size={12} />
          Run the plan
        </button>
      ) : null}

      {finishedRun ? (
        <span className="buildloop__ran" title={finishedRun.detail || undefined}>
          last run: {String(finishedRun.stop_reason || finishedRun.state).replace(/_/g, ' ')}
          {finishedRun.parked?.length ? ` \u00b7 ${finishedRun.parked.length} parked` : ''}
        </span>
      ) : null}
      {run.error ? <span className="buildloop__ran buildloop__ran--wont">{run.error}</span> : null}
    </div>
  );
}
