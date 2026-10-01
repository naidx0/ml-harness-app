/**
 * The journey overview's data, refreshed off the thread's own event stream.
 *
 * Same shape and the same argument as `useStage`: one GET per
 * (thread, lastEventId), so the overview re-reads whenever the transcript
 * learned something new, and never on a timer. Every step's state is a
 * reading of events and facts the thread already wrote, so the moment the
 * transcript moves is exactly the moment this can have changed.
 */

import { useCallback, useEffect, useState } from 'react';

import { getJourney, type JourneyPayload } from './engine/journey';

export interface JourneyData {
  payload: JourneyPayload | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useJourney(
  threadId: number | null,
  lastEventId: number,
  enabled = true,
): JourneyData {
  const [payload, setPayload] = useState<JourneyPayload | null>(null);
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
    getJourney(threadId)
      .then((body) => {
        if (cancelled) return;
        setPayload(body);
        setError(null);
      })
      .catch((problem: unknown) => {
        if (cancelled) return;
        /* The payload is NOT cleared on a failure. A route that was read a
           moment ago is still the truest thing this surface has, and blanking
           it would replace a slightly stale reading with none at all. The
           error sits beside it and says so. */
        setError(problem instanceof Error ? problem.message : String(problem));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [threadId, lastEventId, enabled, nonce]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  return { payload, loading, error, refresh };
}
