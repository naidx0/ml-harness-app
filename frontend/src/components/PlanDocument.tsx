/**
 * THE PLAN AS A DOCUMENT - the pop-out's view, and the shape Cursor's plans have.
 *
 * Max, 2026-09-12, of the pop-out: *"it generated a plan in phases, but it
 * doesn't reciprocate on the pop-out. I want the pop out to be this markdown
 * style view the same way Cursor has it."* So the window renders the whole
 * plan as markdown through the transcript's own renderer - headings, the
 * root-of-the-ask paragraph, `- [ ]` steps as checkboxes - with the phases as
 * a side nav, and an Edit toggle that hands over to the same phase editor the
 * inline pane uses. One document, two ways of looking at it.
 *
 * THE CHECKBOXES ARE LIVE. Ticking one writes `[x]` into the plan column, the
 * same thing `mark_step_done` does when the model finishes a step, so the
 * person and the agent are working one list. Un-ticking works too: a step the
 * model ticked and the person disagrees with goes back to open, and the build
 * loop picks it up again.
 */

import { useState } from 'react';

import { setThreadPlan } from '../lib/engine/client';
import { splitIntoPhases } from '../lib/thePlanInPhases';
import { Icon } from './Icon';
import { PlanPanel } from './PlanPanel';
import { Markdown } from './Transcript';

const STEP = /^(\s*[-*]\s+\[)([ xX])(\]\s+.*)$/;

/** Flip the n-th step line (in document order) between open and done. */
export function toggleStep(plan: string, index: number): string {
  let seen = -1;
  return plan
    .split(/\r?\n/)
    .map((line) => {
      const match = STEP.exec(line);
      if (!match) return line;
      seen += 1;
      if (seen !== index) return line;
      const next = match[2].toLowerCase() === 'x' ? ' ' : 'x';
      return `${match[1]}${next}${match[3]}`;
    })
    .join('\n');
}

export function PlanDocument({
  threadId,
  plan,
  planPath = null,
  onSaved,
}: {
  threadId: number;
  plan: string | null;
  /** The file in the project folder this plan is mirrored to, when there is
   *  one - named in the summary, because the file is the source of truth. */
  planPath?: string | null;
  onSaved: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const phases = splitIntoPhases(plan ?? '');
  const steps = (plan ?? '').split(/\r?\n/).filter((line) => STEP.test(line));
  const open = steps.filter((line) => !/\[[xX]\]/.test(line)).length;

  if (!plan || !plan.trim()) {
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

  async function tick(index: number) {
    if (busy) return;
    setBusy(true);
    try {
      await setThreadPlan(threadId, toggleStep(plan as string, index));
      onSaved();
    } catch {
      /* The engine refused or is gone; the box stays as it was. */
    } finally {
      setBusy(false);
    }
  }

  /* THE SUMMARY AT THE TOP, THEN ONE PAGE. Max, 2026-09-12, of the cards:
     "have that whole plan not be sectioned off, summary quick at the top, and
     then same as Cursor - one clean page where the whole md view can just be
     clear and visible." The title, the count, the phases as chips that jump
     to their heading; under it the plan flows as one document, no borders,
     no boxes - the sections below are anchors, not cards. */
  const title = (plan.split(/\r?\n/).find((line) => /^#\s+/.test(line)) ?? '').replace(/^#\s+/, '').trim();
  const named = phases.filter((each) => each.heading);

  return (
    <div className="plandoc">
      <header className="plandoc__summary">
        <div className="plandoc__summaryrow">
          <h1 className="plandoc__title">{title || 'Plan'}</h1>
          <button
            type="button"
            className="plandoc__toggle"
            aria-pressed={editing}
            onClick={() => setEditing((was) => !was)}
          >
            <Icon name={editing ? 'book' : 'sliders'} size={12} />
            {editing ? 'Read' : 'Edit'}
          </button>
        </div>
        <p className="plandoc__count num">
          {named.length} phase{named.length === 1 ? '' : 's'}
          {steps.length ? ` · ${steps.length - open} of ${steps.length} steps ticked` : ''}
          {steps.length && open === 0 ? ' · every step done' : ''}
        </p>
        {planPath ? (
          <p className="plandoc__path mono" title="Edit this file and the harness adopts it; the harness writes it on every change">
            {planPath}
          </p>
        ) : null}
        {named.length ? (
          <nav className="plandoc__chips" aria-label="Phases">
            {phases.map((each, index) =>
              each.heading ? (
                <a
                  key={index}
                  className="plandoc__phase"
                  href={`#plan-phase-${index}`}
                  title={each.heading}
                >
                  {each.number !== null && each.number !== undefined ? (
                    <span className="planpane__n">{each.number}</span>
                  ) : null}
                  <span className="planpane__label">{each.label}</span>
                </a>
              ) : null,
            )}
          </nav>
        ) : null}
      </header>
      {editing ? (
        <PlanPanel threadId={threadId} plan={plan} onSaved={onSaved} />
      ) : (
        <article className="plandoc__doc prose" onClick={(event) => {
          /* A click on a rendered task row ticks the matching step. The
             renderer draws `.md__tasks li` rows in document order, the
             same order the plan's step lines are in, so the n-th row is
             the n-th `- [ ]` line. */
          const target = event.target as HTMLElement;
          const row = target.closest('.md__tasks li');
          if (!row) return;
          const rows = Array.from(
            (event.currentTarget as HTMLElement).querySelectorAll('.md__tasks li'),
          );
          const index = rows.indexOf(row);
          if (index >= 0) void tick(index);
        }}>
          {phases.map((each, index) => (
            <section key={index} id={`plan-phase-${index}`} className="plandoc__section">
              {each.heading ? <Markdown source={each.heading} /> : null}
              <Markdown source={stripTitle(each.body, index === 0 ? title : '')} />
            </section>
          ))}
        </article>
      )}
    </div>
  );
}

/** The `# Title` line is the summary's heading, so the first section does
 *  not print it a second time. */
function stripTitle(body: string, title: string): string {
  if (!title) return body;
  return body
    .split(/\r?\n/)
    .filter((line) => !(/^#\s+/.test(line) && line.replace(/^#\s+/, '').trim() === title))
    .join('\n');
}
