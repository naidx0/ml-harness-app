/**
 * Context fill as a quiet ring next to Send — not a MEASURED strip.
 * Click opens the Context pane. No provenance tags; the number is ambient.
 */

import { useEffect, useState } from 'react';

import { readThreadUsage } from '../lib/engine/client';

const R = 7;
const C = 2 * Math.PI * R;

export function ContextRing({
  threadId,
  tick,
  onOpen,
}: {
  threadId: number | null;
  tick: number;
  onOpen: () => void;
}) {
  const [fill, setFill] = useState<number | null>(null);
  const [label, setLabel] = useState('Context');

  useEffect(() => {
    if (threadId === null) {
      setFill(null);
      setLabel('Context');
      return;
    }
    let live = true;
    readThreadUsage(threadId)
      .then((out) => {
        if (!live) return;
        const tokens = out.thread.latest_tokens;
        const window = out.thread.window;
        if (tokens != null && window != null && window > 0) {
          const pct = Math.min(100, Math.round((tokens / window) * 100));
          setFill(pct);
          setLabel(`${pct}% of context`);
        } else if (tokens != null) {
          setFill(null);
          setLabel(
            tokens >= 1000
              ? `${Math.round(tokens / 100) / 10}k tokens`
              : `${tokens} tokens`,
          );
        } else {
          setFill(null);
          setLabel('Context');
        }
      })
      .catch(() => {
        if (live) {
          setFill(null);
          setLabel('Context');
        }
      });
    return () => {
      live = false;
    };
  }, [threadId, tick]);

  if (threadId === null) return null;

  const dash = fill == null ? 0 : (fill / 100) * C;

  return (
    <button
      type="button"
      className="composer-ctx"
      onClick={onOpen}
      title={label}
      aria-label={label}
      data-empty={fill == null || undefined}
    >
      <svg className="composer-ctx__svg" width="16" height="16" viewBox="0 0 18 18" aria-hidden="true">
        <circle
          cx="9"
          cy="9"
          r={R}
          fill="none"
          stroke="var(--surface-3)"
          strokeWidth="2"
        />
        <circle
          cx="9"
          cy="9"
          r={R}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${C}`}
          transform="rotate(-90 9 9)"
        />
      </svg>
    </button>
  );
}
