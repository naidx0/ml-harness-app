/**
 * A tool result, rendered as what it is.
 *
 * **No raw JSON in the transcript.** Not as a rule of taste — a wall of braces
 * is the single loudest way to make a calm surface look like a debugger, and
 * it hides the two things a reader actually wants (did it work, and what did
 * it find) inside punctuation.
 *
 * So a result is a table. Keys are set in mono at `--text-2xs` in `--ink-3`,
 * exactly as the engine wrote them, and are NOT prettified into English. That
 * is deliberate: `params_b`, `on_disk_gb` and `max_seq_len` carry units in
 * their names, and a renderer that guessed at "Parameters" or "On disk (GB)"
 * would eventually guess a unit wrong. The engine's field name is the honest
 * label, and it is the one that matches the tool's own schema.
 *
 * Two joins with the rest of the system:
 *
 * - A `provenance` value that exactly matches one of the engine's vocabulary
 *   words renders as a provenance tag (§9.3). One that does not — several
 *   tools return sentences like "measured, from the GGUF header" — renders as
 *   the sentence, because inventing a tag for it would be claiming a
 *   classification nobody made.
 * - `null` renders as "not reported" in `--ink-3`, never as `0`, `—` or an
 *   empty cell. PRODUCT_SPEC §3.1: a number that cannot be computed is absent,
 *   not estimated.
 */

import { useState } from 'react';
import { displayTag } from '../lib/format';
import type { WireProvenance } from '../lib/engine/types';
import { ProvenanceTag } from './primitives';

/** How deep to nest before summarising. Three levels covers every result the
 *  registry produces today; deeper is a sign the pane, not the row, is the
 *  right home for it. */
const MAX_DEPTH = 3;

/** Strings longer than this get a "show all" affordance rather than a wall. */
const LONG_TEXT = 320;

export function ResultView({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined) return <Absent />;

  if (typeof value === 'string') return <LongText text={value} />;

  if (typeof value === 'number') {
    return <span className="kv__num">{formatNumber(value)}</span>;
  }

  if (typeof value === 'boolean') {
    return <span className="kv__bool">{value ? 'yes' : 'no'}</span>;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="kv__absent">none</span>;
    if (depth >= MAX_DEPTH) {
      return <span className="kv__absent">{value.length} items, not shown here</span>;
    }
    return (
      <ol className="kv__list">
        {value.map((entry, index) => (
          <li key={index}>
            <ResultView value={entry} depth={depth + 1} />
          </li>
        ))}
      </ol>
    );
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span className="kv__absent">nothing</span>;
    if (depth >= MAX_DEPTH) {
      return (
        <span className="kv__absent">
          {entries.length} fields, not shown here
        </span>
      );
    }
    return (
      <div className="kv" data-depth={depth}>
        {entries.map(([key, entry]) => (
          <div className="kv__row" key={key}>
            <span className="kv__key">{key}</span>
            <span className="kv__val">
              {isProvenanceWord(entry) ? (
                <ProvenanceTag tag={displayTag(entry as WireProvenance)} />
              ) : (
                <ResultView value={entry} depth={depth + 1} />
              )}
            </span>
          </div>
        ))}
      </div>
    );
  }

  return <span className="kv__absent">not shown</span>;
}

function Absent() {
  /* §9.13: "a failed detection never renders as a measurement". An absent
     value says it is absent. */
  return <span className="kv__absent">not reported</span>;
}

function LongText({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  if (text.length <= LONG_TEXT) return <span className="kv__text">{text}</span>;
  return (
    <span className="kv__text">
      {open ? text : `${text.slice(0, LONG_TEXT)}…`}{' '}
      <button type="button" className="kv__more" onClick={() => setOpen(!open)}>
        {open ? 'show less' : `show all ${text.length} characters`}
      </button>
    </span>
  );
}

/** The engine's provenance vocabulary, exactly. A value that is merely
 *  *about* provenance ("measured, from the GGUF header") is not one of these
 *  and is rendered as the sentence it is. */
const PROVENANCE_WORDS = new Set([
  'measured',
  'inferred',
  'declared',
  'defaulted',
  'untested_on_this_platform',
]);

function isProvenanceWord(value: unknown): boolean {
  return typeof value === 'string' && PROVENANCE_WORDS.has(value);
}

/**
 * §3.6: "Significant figures, not fixed decimals… Never round a number into
 * meaninglessness to fit a column." The engine has already rounded what it
 * chose to round; this prints what it was given and only adds thousands
 * separators, which change nothing about the value.
 */
function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  if (Number.isInteger(value)) return value.toLocaleString();
  return String(value);
}
