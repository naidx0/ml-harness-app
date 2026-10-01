/**
 * THE PLAN, BESIDE THE CHAT, ONE PHASE AT A TIME.
 *
 * Max: *"hopefully, you can have a good follow editor and have a harness to get
 * open the side by side and sectioned off."*
 *
 * Side by side is the inspector, which is already a column next to the
 * transcript. Sectioned off is `lib/thePlanInPhases.ts`, which cuts the
 * document at `##` headings - the same shape `app/conductor._mode_note` asks
 * the model to write, so the reader and the instruction agree on one rule.
 *
 * ## WHY IT EDITS AND DOES NOT ONLY DISPLAY
 *
 * The plan is what a building turn is handed every turn and what the loop works
 * down. A plan you can only read is one you have to argue a model into changing
 * - which is the slowest possible way to fix a typo in the thing that will be
 * repeated for the next hour. So a phase is a textarea, and Save writes the
 * whole document back through the same `POST /api/threads/{id}/plan` the Build
 * button uses.
 *
 * ## WHAT IT WILL NOT DO
 *
 * It does not save as you type. A plan is the standing instruction for every
 * later turn, and a keystroke that reaches the prompt is a half-written
 * sentence reaching the prompt. Save is a press.
 *
 * It does not renumber, reformat or tidy the markdown. The round-trip property
 * in `thePlanInPhases` is the whole reason the panel can be opened without
 * changing the document, and a tidier would spend that.
 */

import { useEffect, useState } from 'react';

import { setThreadPlan } from '../lib/engine/client';
import { splitIntoPhases, withPhaseBody } from '../lib/thePlanInPhases';
import { Icon } from './Icon';

export function PlanPanel({
  threadId,
  plan,
  onSaved,
}: {
  threadId: number | null;
  /** The thread's `plan` column. `null` until somebody presses Build. */
  plan: string | null;
  onSaved: () => void;
}) {
  const phases = splitIntoPhases(plan ?? '');
  const [at, setAt] = useState(0);
  const [draft, setDraft] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  /* A different thread, or a plan the model rewrote, discards an edit in
     progress rather than saving it over the new document. */
  useEffect(() => {
    setAt(0);
    setDraft(null);
    setFailed(false);
  }, [threadId, plan]);

  if (threadId === null || !plan || !plan.trim()) {
    return (
      <div className="planpane planpane--empty">
        <p>
          No plan yet. Plan mode is a conversation with the harness; when the shape of
          the work is agreed it writes the plan out in phases, and <b>Build plan</b>{' '}
          saves what it wrote here.
        </p>
      </div>
    );
  }

  const phase = phases[Math.min(at, phases.length - 1)];
  const body = draft ?? phase.body;
  const dirty = draft !== null && draft !== phase.body;

  async function save() {
    if (!dirty || busy) return;
    setBusy(true);
    setFailed(false);
    try {
      await setThreadPlan(threadId as number, withPhaseBody(plan as string, at, body));
      setDraft(null);
      onSaved();
    } catch {
      /* The engine refused or is gone. The edit STAYS in the box: throwing away
         what somebody typed because a request failed is the one unrecoverable
         thing this panel could do. */
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="planpane">
      <nav className="planpane__phases" aria-label="Phases">
        {phases.map((each, index) => (
          <button
            key={index}
            type="button"
            className="planpane__phase"
            aria-current={index === at}
            onClick={() => {
              setAt(index);
              setDraft(null);
            }}
            title={each.heading || 'Before the first phase'}
          >
            <span className="planpane__n">{each.number ?? '-'}</span>
            <span className="planpane__label">{each.label}</span>
          </button>
        ))}
      </nav>

      <div className="planpane__body">
        <textarea
          className="planpane__edit"
          value={body}
          spellCheck={false}
          onChange={(event) => setDraft(event.target.value)}
          aria-label={phase.heading || 'Plan'}
        />
        <div className="planpane__bar">
          {failed ? (
            <span className="planpane__failed">
              <Icon name="alert" /> not saved - your edit is still here
            </span>
          ) : (
            <span className="planpane__count">
              {phases.length} phase{phases.length === 1 ? '' : 's'}
            </span>
          )}
          <button
            type="button"
            className="planpane__revert"
            disabled={!dirty || busy}
            onClick={() => setDraft(null)}
          >
            Revert
          </button>
          <button
            type="button"
            className="planpane__save"
            disabled={!dirty || busy}
            onClick={() => void save()}
          >
            {busy ? 'Saving' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
