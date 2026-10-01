/**
 * The answers that produce no storm — which is to say, the denials.
 *
 * ══ WHY THIS SHRANK ════════════════════════════════════════════════════════
 *
 * The first cut of this module held every approval and compared fingerprints
 * itself, because there was nothing on the engine to hold them. There is now:
 * `POST /api/storms` records the contract, `app/storm.py Manifest` is the row
 * that is written once, and `Manifest.deviations_from` is the comparison. A
 * second implementation of that comparison living in the interface would be a
 * second opinion about whether a plan changed, and two opinions about a
 * contract is worse than none — so the local one was deleted rather than kept
 * as a fallback. `lib/useStorms.ts` asks the engine.
 *
 * WHAT IS LEFT IS THE ONE ANSWER THE ENGINE HAS NO ROW FOR: **no.** Denying a
 * proposal starts nothing, records nothing and changes nothing on the engine,
 * and that is correct — there is no such thing as a storm that was refused.
 * But Graphite page 15.1 is equally clear that an approval card "does not
 * disappear when it is answered — it becomes the record of the answer", and a
 * card that snapped back to offering the same three buttons would have thrown
 * away a decision the person made.
 *
 * So a denial is remembered here, in this browser, and the card says so in
 * those words rather than implying the engine knows. A cleared browser loses
 * it and the proposal is offered again, which is the honest failure mode: the
 * worst it can do is ask a question twice.
 */

import { useCallback, useEffect, useState } from 'react';

const KEY = 'mlh.denials';

export interface Denial {
  /** `Build.fingerprint()` — everything that was shown, hashed. */
  fingerprint: string;
  /** ISO, from this machine's clock. */
  at: string;
  /** Whether the person said no, or the window closed on them. A timeout
   *  resolves to Deny and never to Allow, and the record keeps which it was:
   *  "the row is permanent and says why, so a reader six months later does not
   *  think the tool failed" (page 15.3). */
  reason: 'clicked' | 'timeout';
}

export interface DenialsState {
  forFingerprint: (fingerprint: string) => Denial | null;
  deny: (fingerprint: string, reason: 'clicked' | 'timeout') => void;
  forget: (fingerprint: string) => void;
}

export function useDenials(threadId: number | null): DenialsState {
  const [rows, setRows] = useState<Denial[]>([]);

  useEffect(() => {
    setRows(load(threadId));
  }, [threadId]);

  const deny = useCallback(
    (fingerprint: string, reason: 'clicked' | 'timeout') => {
      setRows((current) => {
        const next = [
          { fingerprint, at: new Date().toISOString(), reason },
          ...current.filter((row) => row.fingerprint !== fingerprint),
        ];
        save(threadId, next);
        return next;
      });
    },
    [threadId],
  );

  const forget = useCallback(
    (fingerprint: string) => {
      setRows((current) => {
        const next = current.filter((row) => row.fingerprint !== fingerprint);
        save(threadId, next);
        return next;
      });
    },
    [threadId],
  );

  const forFingerprint = useCallback(
    (fingerprint: string) => rows.find((row) => row.fingerprint === fingerprint) ?? null,
    [rows],
  );

  return { forFingerprint, deny, forget };
}

/* ── storage ──────────────────────────────────────────────────────────────── */

function storageKey(threadId: number | null): string {
  return `${KEY}.${threadId ?? 'new'}`;
}

function load(threadId: number | null): Denial[] {
  try {
    const raw = localStorage.getItem(storageKey(threadId));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    /* Read as strictly as anything else here: a half-parsed decision is a
       decision nobody can vouch for, and the safe reading of one is that it was
       never made — which offers the proposal again rather than suppressing it. */
    return parsed.filter(isDenial);
  } catch {
    return [];
  }
}

function save(threadId: number | null, rows: Denial[]): void {
  try {
    localStorage.setItem(storageKey(threadId), JSON.stringify(rows));
  } catch {
    /* A full or blocked store loses the record and not the click: the card's
       state comes from the same array, so the answer still shows for as long as
       the page is open. Nothing in the product acts on a denial. */
  }
}

function isDenial(value: unknown): value is Denial {
  if (typeof value !== 'object' || value === null) return false;
  const row = value as Record<string, unknown>;
  if (typeof row.fingerprint !== 'string' || !row.fingerprint) return false;
  if (typeof row.at !== 'string') return false;
  return row.reason === 'clicked' || row.reason === 'timeout';
}
