/**
 * THE GOAL — target, count, checklist. Expand for Run / Doc / steps.
 *
 * Title click expands (no separate chevron). Live work shows a spinner next
 * to the count; idle/done no longer wear a status lamp (CS17 quiet chrome).
 *
 * CS12: X hides the chrome (session flag); the plan stays in SQLite.
 * CS15: one checklist (prefer plan); Doc dropdown; Icon `goal`.
 */

import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';
import { createPortal } from 'react-dom';

import {
  hideGoalBar,
  isGoalBarHidden,
  subscribeGoalBarVisibility,
} from '../lib/goalBarVisibility';
import { listWorkspaceFiles } from '../lib/engine/client';
import { stepsIn, type Seen } from '../lib/theBuildKeepsGoing';
import { useRun } from '../lib/useRun';
import { useSubAgents } from '../lib/useSubAgents';
import { Icon } from './Icon';
import { TheBuildWorksDown } from './TheBuildWorksDown';

/** "14m 17s", the way Codex's card says it - and "48s" when that is all it
 *  took, because a leading `0m` is noise. */
function minutes(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`;
}

/** The plan with one parked step put back to `- [ ]`, reason dropped. */
export function unpark(plan: string | null, step: string): string {
  const mark = ' — parked: ';
  const wanted = step.trim().toLowerCase();
  return (plan ?? '')
    .split(/\r?\n/)
    .map((line) => {
      const found = /^(\s*[-*]\s+\[)!(\]\s+)(.+)$/.exec(line);
      if (!found) return line;
      const whole = found[3];
      const at = whole.indexOf(mark);
      const text = (at >= 0 ? whole.slice(0, at) : whole).trim();
      if (text.toLowerCase() !== wanted) return line;
      return `${found[1]} ${found[2]}${text}`;
    })
    .join('\n');
}

export function stepRows(
  plan: string | null,
): { text: string; state: 'done' | 'parked' | 'open'; why: string }[] {
  const out: { text: string; state: 'done' | 'parked' | 'open'; why: string }[] = [];
  const mark = ' — parked: ';
  for (const line of (plan ?? '').split(/\r?\n/)) {
    const found = /^\s*[-*]\s+\[([ xX!])\]\s+(.+)$/.exec(line);
    if (!found) continue;
    const glyph = found[1].toLowerCase();
    let text = found[2].trim();
    let why = '';
    const at = text.indexOf(mark);
    if (at >= 0) {
      why = text.slice(at + mark.length).trim();
      text = text.slice(0, at).trim();
    }
    out.push({
      text,
      state: glyph === 'x' ? 'done' : glyph === '!' ? 'parked' : 'open',
      why,
    });
  }
  return out;
}

function slashNorm(path: string): string {
  return path.replace(/\\/g, '/');
}

function isHarnessPlan(path: string): boolean {
  return slashNorm(path).includes('/harness-plans/') || slashNorm(path).startsWith('harness-plans/');
}

export function GoalBar({
  threadId,
  mode,
  plan,
  todo = null,
  planPath,
  projectId = null,
  items,
  running,
  failed,
  lastEventId,
  onContinue,
  onOpenPlan,
  onOpenDoc,
  onSay,
  onDraft,
  onPlan,
}: {
  threadId: number | null;
  mode: string;
  plan: string | null;
  todo?: string | null;
  planPath?: string | null;
  projectId?: number | null;
  items: Seen[];
  running: boolean;
  failed: boolean;
  lastEventId: number;
  onContinue: () => Promise<void>;
  onOpenPlan: () => void;
  /** Open a sibling plan file in Files (optional). */
  onOpenDoc?: (path: string) => void;
  onSay: (words: string) => void;
  onDraft: (words: string) => void;
  onPlan: (plan: string) => Promise<void> | void;
}) {
  const [open, setOpen] = useState(false);
  const [docOpen, setDocOpen] = useState(false);
  const [docQuery, setDocQuery] = useState('');
  const [docPos, setDocPos] = useState<{ top: number; left: number } | null>(null);
  const [siblings, setSiblings] = useState<string[]>([]);
  const docWrap = useRef<HTMLSpanElement>(null);
  const docMenu = useRef<HTMLDivElement>(null);
  const hidden = useSyncExternalStore(
    subscribeGoalBarVisibility,
    isGoalBarHidden,
    () => false,
  );
  const run = useRun(threadId, lastEventId);
  const sub = useSubAgents(threadId, lastEventId);

  useLayoutEffect(() => {
    if (!docOpen || !docWrap.current) {
      setDocPos(null);
      return;
    }
    const place = () => {
      const rect = docWrap.current!.getBoundingClientRect();
      const width = 280;
      const left = Math.min(
        Math.max(8, rect.left),
        Math.max(8, window.innerWidth - width - 8),
      );
      setDocPos({ top: rect.bottom + 4, left });
    };
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [docOpen]);

  useEffect(() => {
    if (!docOpen) return;
    const onDoc = (event: MouseEvent) => {
      const target = event.target as Node;
      if (docWrap.current?.contains(target) || docMenu.current?.contains(target)) return;
      setDocOpen(false);
      setDocQuery('');
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setDocOpen(false);
        setDocQuery('');
      }
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [docOpen]);

  useEffect(() => {
    if (!docOpen || projectId == null) {
      setSiblings([]);
      return;
    }
    let live = true;
    void listWorkspaceFiles(projectId)
      .then((listing) => {
        if (!live) return;
        const paths = (listing.files || [])
          .map((row) => row.path)
          .filter(isHarnessPlan);
        setSiblings(paths);
      })
      .catch(() => {
        if (live) setSiblings([]);
      });
    return () => {
      live = false;
    };
  }, [docOpen, projectId]);

  if (hidden) return null;
  /* CS15 — one checklist: prefer threads.plan; todo only when plan is empty. */
  const list = (plan && plan.trim() ? plan : todo && todo.trim() ? todo : '') || '';
  if (threadId === null || !list.trim()) return null;

  const rows = stepRows(list);
  const counts = stepsIn(list);
  const title = (list.split(/\r?\n/).find((line) => /^#\s+/.test(line)) ?? '')
    .replace(/^#\s+/, '')
    .trim();
  const nextOpen = rows.findIndex((row) => row.state === 'open');

  const state = run.run;
  const finished = state && state.state && state.state !== 'running' ? state : null;
  const settled = counts.open === 0 && rows.length > 0;
  const took = state?.seconds ?? null;
  const live = run.live || running || sub.read.running > 0;

  const docRows = (() => {
    const seen = new Set<string>();
    const out: { id: string; label: string; current?: boolean }[] = [];
    const q = docQuery.trim().toLowerCase();
    const add = (path: string, current?: boolean) => {
      const key = slashNorm(path);
      if (seen.has(key)) return;
      if (q && !key.toLowerCase().includes(q)) return;
      seen.add(key);
      const base = key.split('/').pop() || key;
      out.push({ id: path, label: base, current });
    };
    if (planPath) add(planPath, true);
    for (const path of siblings) add(path, planPath ? slashNorm(path) === slashNorm(planPath) : false);
    if (out.length === 0 && planPath) {
      out.push({ id: planPath, label: slashNorm(planPath).split('/').pop() || 'Plan', current: true });
    }
    if (out.length === 0) {
      out.push({
        id: '__plan__',
        label: 'Open plan',
        current: true,
      });
    }
    return out;
  })();

  return (
    <div
      className="goalbar"
      data-open={open || undefined}
      data-state={
        sub.read.running > 0 || run.live
          ? 'running'
          : settled
            ? counts.parked
              ? 'partly'
              : 'done'
            : 'idle'
      }
    >
      <div className="goalbar__row">
        <button
          type="button"
          className="goalbar__disclose"
          aria-expanded={open}
          onClick={() => setOpen((was) => !was)}
          title={title || 'The plan'}
        >
          <span className="goalbar__target" aria-hidden="true" title="Goal">
            <Icon name="star" size={16} style={{ color: 'var(--gold)' }} />
          </span>
          <span className="goalbar__title">{title || 'The plan'}</span>
        </button>

        {/* CS20 — left title, right working+progress (never a centered count). */}
        <span className="goalbar__meta">
          {live ? (
            <span
              className="goalbar__spin toolstrip__spin"
              title="Working"
              aria-label="Working"
            />
          ) : null}
          <span className="goalbar__count num" title="steps done of total">
            {counts.done}/{rows.length}
          </span>
          {!live ? (
            <button
              type="button"
              className="goalbar__dismiss"
              onClick={() => hideGoalBar()}
              title="Hide this goal (plan stays saved)"
              aria-label="Hide goal"
            >
              <Icon name="x" size={11} />
            </button>
          ) : null}
        </span>
      </div>

      {open ? (
        <div className="goalbar__state">
          <span className="goalbar__loop">
            <TheBuildWorksDown
              threadId={threadId}
              mode={mode}
              plan={list}
              items={items}
              running={running}
              failed={failed}
              lastEventId={lastEventId}
              onContinue={onContinue}
            />
          </span>
          <span className="goalbar__doc" ref={docWrap}>
            <button
              type="button"
              className="goalbar__open"
              aria-expanded={docOpen}
              onClick={() => setDocOpen((was) => !was)}
              title="Plans in this project"
            >
              <Icon name="skill" size={12} />
              Doc
              <Icon name="chevdown" size={10} />
            </button>
            {docOpen && docPos
              ? createPortal(
                  <div
                    ref={docMenu}
                    className="goalbar__docmenu goalbar__docmenu--portal"
                    role="listbox"
                    aria-label="Plans"
                    style={{ top: docPos.top, left: docPos.left }}
                  >
                    <input
                      className="goalbar__docsearch"
                      type="search"
                      value={docQuery}
                      onChange={(event) => setDocQuery(event.target.value)}
                      placeholder="Search plans…"
                      aria-label="Search plans"
                      autoFocus
                    />
                    {docRows.map((row) => (
                      <button
                        key={row.id}
                        type="button"
                        className="goalbar__docrow"
                        data-current={row.current || undefined}
                        role="option"
                        aria-selected={Boolean(row.current)}
                        onClick={() => {
                          setDocOpen(false);
                          setDocQuery('');
                          if (
                            row.id === '__plan__' ||
                            (planPath && slashNorm(row.id) === slashNorm(planPath))
                          ) {
                            onOpenPlan();
                            return;
                          }
                          if (onOpenDoc) onOpenDoc(row.id);
                          else onOpenPlan();
                        }}
                      >
                        <span className="mono">{row.label}</span>
                      </button>
                    ))}
                  </div>,
                  document.body,
                )
              : null}
          </span>
          {settled && took !== null ? (
            <span className="goalbar__took num" title="how long the run took">
              {minutes(took)}
            </span>
          ) : null}
        </div>
      ) : null}

      {open && finished ? (
        <p className="goalbar__last" title={finished.detail || undefined}>
          last run: {String(finished.stop_reason || finished.state).replace(/_/g, ' ')}
          {finished.detail ? ` — ${finished.detail}` : ''}
        </p>
      ) : null}

      {open ? (
        <ol className="goalsteps">
          {rows.map((row, index) => (
            <li
              key={`${index}-${row.text}`}
              className="goalstep"
              data-state={row.state}
              data-next={index === nextOpen && mode === 'build' ? 'yes' : undefined}
            >
              <span className="goalstep__mark" aria-hidden="true" />
              <span className="goalstep__text" title={row.text}>
                {row.text}
              </span>
              {row.state === 'parked' && row.why ? (
                <span className="goalstep__why" title={`parked: ${row.why}`}>
                  {row.why}
                </span>
              ) : null}
              {index === nextOpen && mode === 'build' ? (
                <span className="goalstep__now">
                  {running ? 'working' : 'next'}
                </span>
              ) : null}

              <span className="goalstep__acts">
                {row.state !== 'done' ? (
                  <button
                    type="button"
                    className="goalstep__act"
                    title={`Ask the agent to do this step now: ${row.text}`}
                    onClick={() => onSay(`Work this step now: ${row.text}`)}
                  >
                    Work
                  </button>
                ) : null}
                <button
                  type="button"
                  className="goalstep__act"
                  title={`Ask the agent about this step: ${row.text}`}
                  onClick={() => onDraft(`About the step "${row.text}": `)}
                >
                  Ask
                </button>
                {row.state === 'parked' ? (
                  <button
                    type="button"
                    className="goalstep__act"
                    title="Put this step back on the list, so a run tries it again"
                    onClick={() => void onPlan(unpark(list, row.text))}
                  >
                    Unpark
                  </button>
                ) : null}
              </span>
            </li>
          ))}
          {planPath ? (
            <li className="goalstep goalstep--path mono">{planPath}</li>
          ) : null}
        </ol>
      ) : null}
    </div>
  );
}
