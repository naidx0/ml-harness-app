/**
 * The storm, once a plan has become one — the record of the approval, and what
 * has happened to the contract since.
 *
 * This is the surface Graphite page 15.2 describes as what an approval card
 * becomes: "it does not disappear when it is answered — it becomes the record
 * of the answer." What it records here is not "you clicked yes"; it is the
 * fingerprint that was approved, when, and the state of the thing that was
 * approved to run. The picture above it is the same picture, with the states
 * on it, because it is the same object.
 *
 * ══ THE THREE THINGS THIS SAYS AND NOTHING ELSE DOES ═══════════════════════
 *
 * 1. **What was approved.** `manifest.fingerprint`, on screen in mono. It is
 *    the hash of everything the person read; showing it is what makes "what was
 *    approved is what runs" a claim somebody could check rather than one they
 *    have to take.
 * 2. **Whether anything is still holding the card.** `live` is a fact about the
 *    engine process, not a row somebody wrote: `app/storm.py` treats a step
 *    that is `running` with nothing live as **stalled**, because "whether it
 *    finished its work is not knowable from here, so it is neither done nor
 *    queued". That distinction is the difference between waiting and being
 *    stuck, and it gets the words rather than a spinner.
 * 3. **Whether it worked**, against the criterion the build stated BEFORE it
 *    ran. `verification` carries the engine's own sentence and what it saw. A
 *    storm that finished and cannot show it worked did not work, and this says
 *    that in the engine's words rather than in a green tick of our own.
 *
 * ══ DEVIATIONS ════════════════════════════════════════════════════════════
 *
 * `storm.deviations` is non-empty when the executor stopped because the world
 * moved under the contract. Nothing here decides that a change was harmless —
 * every line is rendered, in the engine's order, and the choice is the
 * person's. That is the whole of "any deviation stops and asks".
 */

import type { CSSProperties } from 'react';
import type { Storm } from '../lib/engine/storm';
import { stepStateView } from '../lib/runState';
import { DeviationBlock } from './Approval';
import { Icon } from './Icon';
import { Button, StatusDot } from './primitives';

export function StormProgress({
  storm,
  onCancel,
}: {
  storm: Storm;
  onCancel: (stormId: number) => void;
}) {
  const view = stepStateView(storm.state);
  const steps = [...storm.steps.values()];
  const done = steps.filter((step) => step.state === 'done').length;
  const running = storm.state === 'running' || storm.state === 'preflight';

  return (
    <div className="storm" data-state={storm.state}>
      <div className="storm__head">
        <StatusDot role={view.role} shape={view.dot} />
        <span
          className="storm__state"
          style={{ color: `var(--${view.role})` } as CSSProperties}
        >
          {view.label}
        </span>
        {/* n of m, never a percentage — the same rule the gate ledger's counter
            follows. Four of six steps is not 67% of a build. */}
        <span className="storm__count">
          {done} of {steps.length} steps done
        </span>
        <span className="storm__id mono">storm {storm.id}</span>
        {running ? (
          <Button small onClick={() => onCancel(storm.id)}>
            <Icon name="stop" size={12} />
            Stop
          </Button>
        ) : null}
      </div>

      <p className="storm__contract">
        <Icon name="check" size={12} />
        <span>
          Approved{' '}
          <span className="mono">{storm.fingerprint.slice(0, 16)}</span>
          {storm.approvedAt ? <> at {when(storm.approvedAt)}</> : null}. What runs
          is what is in that hash;{' '}
          {storm.live
            ? 'this engine is running it now.'
            : 'nothing is running it in this engine process.'}
        </span>
      </p>

      {storm.stalled.length > 0 ? (
        <p className="storm__stalled">
          <Icon name="alert" size={12} />
          <span>
            {storm.stalled.length === 1
              ? 'One step was running when the engine stopped'
              : `${storm.stalled.length} steps were running when the engine stopped`}{' '}
            — <span className="mono">{storm.stalled.join(', ')}</span>. Whether
            the work landed is not knowable from here, so nothing restarts it on
            an assumption.
          </span>
        </p>
      ) : null}

      <DeviationBlock notes={storm.deviations} />

      {storm.verification ? (
        <p className="storm__verified" data-ok={storm.verification.ok}>
          <Icon name={storm.verification.ok ? 'check' : 'alert'} size={12} />
          <span>
            <b>{storm.verification.ok ? 'It worked' : 'It did not'}</b>{' '}
            {storm.verification.stated} — {storm.verification.because}
          </span>
        </p>
      ) : null}
    </div>
  );
}

function when(iso: string): string {
  const parsed = Date.parse(iso);
  if (!Number.isFinite(parsed)) return iso;
  return new Date(parsed).toLocaleString();
}
