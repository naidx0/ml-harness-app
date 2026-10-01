/**
 * CS5 / CS16 / CS17 / CS19 — “What changed” under an assistant turn.
 *
 * Collapsed by default: short labels, quiet kind mark. Click a row to expand.
 * Card itself shows at most three rows until “Show N more” (CS19).
 */

import { useState, type ReactNode } from 'react';

import { revertTurnEffects } from '../lib/engine/client';
import { Icon } from './Icon';
import { displayTag } from '../lib/format';
import type { WireProvenance } from '../lib/engine/types';

export interface EffectsPayload {
  effectsId: number;
  stepsDone: string[];
  stepsParked: { step: string; why: string }[];
  facts: { fact: string; origin: string; how: string; tool: string }[];
  files: string[];
  planWrites: number;
  canRevert: boolean;
}

type Kind = 'ticked' | 'plan' | 'file' | 'fact' | 'parked';

function KindChip({ kind, children }: { kind: Kind; children: string }) {
  return (
    <span className="what-changed__k" data-kind={kind}>
      {children}
    </span>
  );
}

function Sign({ sense }: { sense: 'plus' | 'minus' | 'neutral' }) {
  const glyph = sense === 'plus' ? '+' : sense === 'minus' ? '−' : '·';
  return (
    <span className="what-changed__sign" data-sense={sense} aria-hidden="true">
      {glyph}
    </span>
  );
}

function baseName(path: string): string {
  const norm = path.replace(/\\/g, '/');
  const parts = norm.split('/').filter(Boolean);
  return parts[parts.length - 1] || path;
}

/** THE FACT IS THE ROW, and the tool is how it got there.
 *
 *  This returned `fact.tool` whenever there was one, so every fact
 *  `measure_eval_set` stamped read "measure_eval_set" - and Max photographed
 *  three rows saying exactly that, one under the other, looking like the same
 *  row three times. What changed is `eval_size_n`; `measure_eval_set` is the
 *  instrument, and the detail below already names it. */
function shortFactLabel(fact: { fact: string; tool: string }): string {
  const one = fact.fact.trim().split(/\s+/).slice(0, 6).join(' ');
  if (one) return one.length < fact.fact.trim().length ? `${one}…` : one;
  return fact.tool.trim() || 'fact';
}

/** ONE ROW PER FACT, however many times the turn stamped it.
 *
 *  A turn that calls `measure_eval_set` three times stamps `eval_size_n`
 *  three times, and `turn.effects` records all three - correctly, it is a log.
 *  The card is not a log: it answers "what changed", and a fact re-measured to
 *  the same value by the same tool changed once. Three identical rows also
 *  shared one React key, because the key is built from the fact and the tool.
 *  The count rides along when it is more than one, because a tool run three
 *  times is worth seeing. */
function foldRepeats<T extends { fact: string; origin: string; tool: string }>(
  facts: readonly T[],
): { fact: T; times: number }[] {
  const order: string[] = [];
  const seen = new Map<string, { fact: T; times: number }>();
  for (const one of facts) {
    const key = `${one.fact}|${one.origin}|${one.tool}`;
    const had = seen.get(key);
    if (had) {
      had.times += 1;
      continue;
    }
    order.push(key);
    seen.set(key, { fact: one, times: 1 });
  }
  return order.map((key) => seen.get(key)!);
}

function Row({
  sense,
  kind,
  kindLabel,
  summary,
  detail,
  title,
}: {
  sense: 'plus' | 'minus' | 'neutral';
  kind: Kind;
  kindLabel: string;
  summary: ReactNode;
  detail?: ReactNode;
  title?: string;
}) {
  const [open, setOpen] = useState(false);
  const expandable = Boolean(detail);
  return (
    <li data-open={open || undefined}>
      <button
        type="button"
        className="what-changed__row"
        aria-expanded={expandable ? open : undefined}
        disabled={!expandable}
        title={title}
        onClick={() => {
          if (expandable) setOpen((was) => !was);
        }}
      >
        <Sign sense={sense} />
        <KindChip kind={kind}>{kindLabel}</KindChip>
        <span className="what-changed__body">{summary}</span>
      </button>
      {open && detail ? <div className="what-changed__detail">{detail}</div> : null}
    </li>
  );
}

type BuiltRow = {
  key: string;
  sense: 'plus' | 'minus' | 'neutral';
  kind: Kind;
  kindLabel: string;
  summary: ReactNode;
  detail?: ReactNode;
  title?: string;
};

export function WhatChangedCard({
  effects,
  threadId,
  onReverted,
}: {
  effects: EffectsPayload;
  threadId: number | null;
  onReverted?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const hasTicks =
    effects.stepsDone.length > 0 ||
    effects.stepsParked.length > 0 ||
    effects.planWrites > 0;
  if (!hasTicks && !effects.facts.length && !effects.files.length) {
    return null;
  }

  async function revert() {
    if (threadId === null || !effects.canRevert || busy) return;
    setBusy(true);
    setNote(null);
    try {
      await revertTurnEffects(threadId, effects.effectsId);
      setNote('Plan ticks restored. Ledger facts were left alone.');
      onReverted?.();
    } catch (failure) {
      setNote(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }

  const rows: BuiltRow[] = [];
  for (const step of effects.stepsDone) {
    rows.push({
      key: `d-${step}`,
      sense: 'plus',
      kind: 'ticked',
      kindLabel: 'Ticked',
      summary: <span className="what-changed__sum">{step}</span>,
      title: step,
    });
  }
  for (const row of effects.stepsParked) {
    rows.push({
      key: `p-${row.step}`,
      sense: 'minus',
      kind: 'parked',
      kindLabel: 'Parked',
      summary: <span className="what-changed__sum">{row.step}</span>,
      title: row.why ? `${row.step} — ${row.why}` : row.step,
      detail: row.why ? <p className="what-changed__why">parked: {row.why}</p> : undefined,
    });
  }
  if (effects.planWrites > 0) {
    rows.push({
      key: 'plan',
      sense: 'plus',
      kind: 'plan',
      kindLabel: 'Plan',
      summary: (
        <span className="what-changed__sum">
          rewritten <code className="what-changed__tool">write_plan</code>
        </span>
      ),
    });
  }
  for (const { fact, times } of foldRepeats(effects.facts)) {
    const originRaw = fact.origin.trim().toLowerCase();
    const origin = (
      originRaw === 'measured' ||
      originRaw === 'inferred' ||
      originRaw === 'declared' ||
      originRaw === 'defaulted'
        ? originRaw
        : 'inferred'
    ) as WireProvenance;
    const tag = displayTag(origin) ?? 'INFERRED';
    rows.push({
      key: `f-${fact.fact}-${fact.tool}`,
      sense: 'plus',
      kind: 'fact',
      kindLabel: 'Fact',
      summary: (
        <span className="what-changed__sum">
          {shortFactLabel(fact)}
          <span className="what-changed__prov" title={tag}>
            {tag.toLowerCase()}
          </span>
          {times > 1 ? (
            <span
              className="what-changed__times"
              title={`This turn stamped it ${times} times, to the same value each time.`}
            >
              &times;{times}
            </span>
          ) : null}
        </span>
      ),
      title: fact.fact,
      detail: (
        <>
          <p className="what-changed__fact">{fact.fact}</p>
          {fact.tool ? (
            <p>
              via <code className="what-changed__tool">{fact.tool}</code>
              {times > 1 ? `, run ${times} times this turn` : ''}
            </p>
          ) : null}
          {fact.how ? <p className="what-changed__why">{fact.how}</p> : null}
        </>
      ),
    });
  }
  for (const path of effects.files) {
    rows.push({
      key: `file-${path}`,
      sense: 'plus',
      kind: 'file',
      kindLabel: 'File',
      summary: <span className="what-changed__sum mono">{baseName(path)}</span>,
      title: path,
      detail: <code className="what-changed__path">{path}</code>,
    });
  }

  const visible = expanded ? rows : rows.slice(0, 3);
  const hidden = rows.length - visible.length;

  return (
    <aside className="what-changed" aria-label="What changed this turn">
      <header className="what-changed__head">
        <Icon name="skill" size={12} />
        <span className="what-changed__title">What changed</span>
        {effects.canRevert && threadId !== null ? (
          <button
            type="button"
            className="what-changed__revert"
            disabled={busy}
            onClick={() => void revert()}
            title="Restore plan/todo ticks from before this turn. Does not delete ledger facts."
          >
            {busy ? 'Reverting…' : 'Revert ticks'}
          </button>
        ) : null}
      </header>
      <ul className="what-changed__list">
        {visible.map((row) => (
          <Row
            key={row.key}
            sense={row.sense}
            kind={row.kind}
            kindLabel={row.kindLabel}
            summary={row.summary}
            detail={row.detail}
            title={row.title}
          />
        ))}
      </ul>
      {rows.length > 3 ? (
        <button
          type="button"
          className="what-changed__more"
          onClick={() => setExpanded((was) => !was)}
        >
          {expanded ? 'Show less' : `Show ${hidden} more`}
        </button>
      ) : null}
      {note ? <p className="what-changed__note">{note}</p> : null}
    </aside>
  );
}
