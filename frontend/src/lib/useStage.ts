/**
 * The Stage's data, refreshed off the thread's own event stream.
 *
 * Same shape as `useStorms`: one GET per (thread, lastEventId), so the Stage
 * re-reads whenever the transcript learned something new and never on a
 * timer. The Stage is a second reader of the events the transcript reads —
 * it does not subscribe to a second stream, and it does not poll.
 */

import { useCallback, useEffect, useState } from 'react';

import { getStage, type StagePayload } from './engine/stage';

export interface StageData {
  payload: StagePayload | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useStage(threadId: number | null, lastEventId: number, enabled = true): StageData {
  const [payload, setPayload] = useState<StagePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (threadId === null || !enabled) {
      if (threadId === null) setPayload(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getStage(threadId)
      .then((body) => {
        if (cancelled) return;
        setPayload(body);
        setError(null);
      })
      .catch((failure: unknown) => {
        if (cancelled) return;
        /* A thread with nothing measured is a 200 with empty lists. Anything
           landing here is a real failure and is reported as one, never drawn
           as "nothing measured". */
        setError(failure instanceof Error ? failure.message : String(failure));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [threadId, lastEventId, nonce, enabled]);

  const refresh = useCallback(() => setNonce((value) => value + 1), []);
  return { payload, loading, error, refresh };
}
