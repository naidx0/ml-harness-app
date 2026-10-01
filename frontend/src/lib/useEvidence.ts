/**
 * The evidence ledger for one thread — why the harness believes what it believes.
 *
 * `GET /api/evidence?thread_id=` returns one append-only row per claim or
 * measurement: the fact, the value, the origin, the actor, the tool that
 * produced it and one sentence of how. `app/tools/evidence.py`: "Nothing is
 * ever updated in place, so 'we measured 12 rows at 14:02 and the model had
 * claimed 500 at 13:58' survives."
 *
 * That surviving history is the point, and it is why this hook does not reduce
 * the rows to a current value per fact. The engine already resolves them —
 * MEASURED > STATED > ASSERTED, recency breaking ties — inside
 * `assemble_facts`, and a second resolution here could disagree with the one
 * that actually decided the gates. The pane shows the ledger; the card shows
 * the verdict; the engine is the only thing that turns one into the other.
 *
 * REFETCHED, NOT SUBSCRIBED. There is no event kind for a fact being recorded,
 * so this reloads on thread change and on demand — after a control runs, which
 * is the only moment in this build that writes a row from the interface. A
 * poll would be inventing a freshness the engine does not promise.
 */

import { useCallback, useEffect, useState } from 'react';
import { getEvidence } from './engine/client';
import { readEvidence, type EvidenceLedger } from './engine/facts';

export interface EvidenceState {
  ledger: EvidenceLedger;
  loading: boolean;
  /** Why it could not be read, in words. `/api/evidence` does not exist on an
   *  engine older than fact provenance, and a 404 there is a real thing to
   *  say rather than an empty ledger to draw. */
  error: string | null;
  refresh: () => void;
}

const EMPTY: EvidenceLedger = { thread_id: null, rows: [], origins: {} };

export function useEvidence(threadId: number | null): EvidenceState {
  const [ledger, setLedger] = useState<EvidenceLedger>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    getEvidence(threadId)
      .then((body) => {
        if (!live) return;
        setLedger(readEvidence(body));
      })
      .catch((failure: unknown) => {
        if (!live) return;
        setLedger(EMPTY);
        setError(failure instanceof Error ? failure.message : String(failure));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [threadId, nonce]);

  const refresh = useCallback(() => setNonce((current) => current + 1), []);

  return { ledger, loading, error, refresh };
}
