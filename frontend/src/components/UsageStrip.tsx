/**
 * CS3 — compact thread usage above the composer path line.
 * Every figure carries a ProvenanceTag; details open the Context pane.
 */
import { useEffect, useState } from 'react';

import {
  readThreadUsage,
  type ThreadUsageRead,
} from '../lib/engine/client';
import type { WireProvenance } from '../lib/engine/types';

function asWire(p: string | undefined): WireProvenance | undefined {
  const v = (p || '').toLowerCase();
  if (v === 'measured' || v === 'inferred' || v === 'declared' || v === 'defaulted') {
    return v;
  }
  return 'measured';
}

function fmtSeconds(s: number | null | undefined): string {
  if (s == null || Number.isNaN(s)) return '—';
  if (s < 60) return `${Math.round(s * 10) / 10}s`;
  const m = Math.floor(s / 60);
  const r = Math.round(s % 60);
  return `${m}m ${r}s`;
}

function fmtTokens(n: number | null | undefined): string {
  if (n == null) return '—';
  if (n >= 1000) return `${Math.round(n / 100) / 10}k`;
  return String(n);
}

export function UsageStrip({
  threadId,
  tick,
  onOpenDetails,
}: {
  threadId: number | null;
  tick: number;
  onOpenDetails: () => void;
}) {
  const [read, setRead] = useState<ThreadUsageRead | null>(null);

  useEffect(() => {
    if (threadId === null) {
      setRead(null);
      return;
    }
    let live = true;
    readThreadUsage(threadId)
      .then((out) => {
        if (live) setRead(out);
      })
      .catch(() => {
        if (live) setRead(null);
      });
    return () => {
      live = false;
    };
  }, [threadId, tick]);

  if (threadId === null || !read || read.thread.turn_count === 0) return null;

  const t = read.thread;
  const p = read.provenance;

  return (
    <div className="usage-strip" aria-label="Thread usage">
      {/* No provenance chips down here. Max, 2026-09-17: a person at the
          composer wants the number; who counted it is the title on hover
          and the whole story is one click away in details. */}
      <span
        className="usage-strip__fig"
        title={`${read.counted_by.tokens} (${asWire(p.tokens)}) · last prompt ${fmtTokens(t.latest_tokens)}`}
      >
        <span className="num">{fmtTokens(t.total_tokens ?? t.latest_tokens)}</span>
        <span className="usage-strip__unit">tok total</span>
      </span>
      {t.latest_tokens != null && t.total_tokens != null && t.total_tokens !== t.latest_tokens ? (
        <span className="usage-strip__fig" title="Tokens on the last prompt only">
          <span className="num">{fmtTokens(t.latest_tokens)}</span>
          <span className="usage-strip__unit">last</span>
        </span>
      ) : null}
      <span className="usage-strip__fig" title={read.counted_by.tool_calls}>
        <span className="num">{t.total_tool_calls}</span>
        <span className="usage-strip__unit">calls</span>
      </span>
      <span className="usage-strip__fig" title={read.counted_by.seconds}>
        <span className="num">{fmtSeconds(t.total_seconds)}</span>
      </span>
      <button
        type="button"
        className="usage-strip__more"
        onClick={onOpenDetails}
        title="Open the context window breakdown"
      >
        details
      </button>
    </div>
  );
}
