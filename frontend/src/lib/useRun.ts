/**
 * THE LONG RUN, FOLLOWED FROM THE PAGE.
 *
 * The run itself is in the engine (`app/longrun.py`): it takes turns until
 * every step of the plan is ticked or parked, and it survives this window
 * being closed, which is the whole reason it is not the browser loop it
 * replaces. This hook is only the view of it - it reads the run's row when
 * the thread's event stream moves, because every turn the run takes writes
 * events, so the thread moving IS the run progressing. No timer.
 */

import { useCallback, useEffect, useState } from 'react';

import { readRun, startRun, stopRun, type RunState } from './engine/client';

export interface RunView {
  run: RunState | null;
  /** The engine is taking turns right now. */
  live: boolean;
  busy: boolean;
  error: string | null;
  start: () => Promise<void>;
  stop: () => Promise<void>;
  refresh: () => Promise<void>;
}

export function useRun(threadId: number | null, lastEventId: number): RunView {
  const [run, setRun] = useState<RunState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (threadId === null) {
      setRun(null);
      return;
    }
    try {
      setRun(await readRun(threadId));
    } catch {
      /* The engine is gone or the thread is; the chip then draws nothing
         rather than claiming a run that cannot be read. */
      setRun(null);
    }
  }, [threadId]);

  useEffect(() => {
    void refresh();
  }, [refresh, lastEventId]);

  const start = useCallback(async () => {
    if (threadId === null || busy) return;
    setBusy(true);
    setError(null);
    try {
      await startRun(threadId);
      await refresh();
    } catch (failure) {
      /* The engine's own sentence - "switch to Build under the chat box
         first", "every step is ticked or parked" - not a paraphrase. */
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }, [threadId, busy, refresh]);

  const stop = useCallback(async () => {
    if (threadId === null || busy) return;
    setBusy(true);
    try {
      await stopRun(threadId);
      await refresh();
    } catch {
      /* Same rule as the mode switch: a control that moved anyway would
         claim a state the engine does not hold. */
    } finally {
      setBusy(false);
    }
  }, [threadId, busy, refresh]);

  return {
    run,
    live: run?.state === 'running',
    busy,
    error,
    start,
    stop,
    refresh,
  };
}
