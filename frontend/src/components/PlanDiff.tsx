/**
 * WHAT THE CHANGE ACTUALLY CHANGED.
 *
 * Max, 2026-09-14: *"We should have the file diff - when the agent reads or
 * writes anything and does any change, like adding to the plan, we should have
 * that diff as an expandable feature to our thing."*
 *
 * The plan notices said `Plan saved: 4 phases, 1,180 characters`. Every number
 * in that is true and none of them answers the question a person has, which is
 * *what did it just do to my plan*. A rewrite that fixed a typo and a rewrite
 * that replaced every step produce the same sentence.
 *
 * ## The drawing was already here
 *
 * `.diffwrap` and `.diffline[data-kind]` have been in `shell.css` since the
 * tokens `--diff-add-bg` / `--diff-add-gutter` / `--diff-del-*` were added, and
 * nothing has ever rendered through them - the feature they were drawn for was
 * never built. This is that component, and the CSS it uses is unchanged: the
 * wash carries the change and the gutter carries the colour, while the text
 * itself stays `--ink-1` in both, because a line you cannot read is not a diff.
 *
 * ## Expandable, and collapsed by default
 *
 * A turn that ticks four steps would otherwise put four diffs in the column
 * between two sentences. Collapsed it is one line saying how much moved; opened
 * it is the lines. The summary is the part that belongs in the flow.
 */

import { useState } from 'react';

import { Icon } from './Icon';
import type { PlanChange } from '../lib/transcript';

export function PlanDiff({ change }: { change: PlanChange }) {
  const [open, setOpen] = useState(false);
  if (!change.rows.length) return null;

  return (
    <div className="plandiff" data-open={open || undefined}>
      <button
        type="button"
        className="plandiff__toggle"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
        title={open ? 'Hide what changed' : 'Show the lines that changed'}
      >
        <Icon name="chevright" size={11} rotate={open ? 90 : 0} />
        <span className="plandiff__sum num">
          {change.added ? <span className="stat-add">+{change.added}</span> : null}
          {change.removed ? <span className="stat-del">&minus;{change.removed}</span> : null}
        </span>
        <span className="plandiff__label">
          {open ? 'what changed' : 'see what changed'}
        </span>
      </button>

      {open ? (
        <div className="diffwrap">
          {change.rows.map((row, index) => (
            <div className="diffline" data-kind={row.kind} key={`${index}-${row.old}-${row.cur}`}>
              {/* BOTH LINE NUMBERS, because a plan is read by line and a step
                  that moved from 7 to 9 moved. The column is the one the line
                  exists in; the other is blank rather than zero. */}
              <span className="diffline__ln">{row.old ?? ''}</span>
              <span className="diffline__ln">{row.cur ?? ''}</span>
              <span className="diffline__sg" aria-hidden="true">
                {row.kind === 'add' ? '+' : row.kind === 'del' ? '−' : ''}
              </span>
              {/* The whole line on the hover: `.diffline__tx` clips, and a
                  clipped line with no way to read the rest is the fault Max
                  named on the goal card. */}
              <span className="diffline__tx" title={row.text}>
                {row.text || ' '}
              </span>
            </div>
          ))}
          {change.clipped ? (
            <p className="plandiff__clipped">
              {change.clipped} more line{change.clipped === 1 ? '' : 's'} changed, not shown
              here. The plan file on disk has all of it.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
