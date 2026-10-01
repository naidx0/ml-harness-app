/**
 * The storms in this conversation, and the two acts that start one.
 *
 * ══ WHY THIS IS EVENT-DRIVEN AND NOT A TIMER ═══════════════════════════════
 *
 * A storm reports itself into the thread: `storm.declared`, `storm.started`,
 * `storm.step.started`, `storm.step.finished`, `storm.asked`, `storm.refused`,
 * `storm.finished` (`app/storm.py KINDS`). Every one of those is committed to
 * the event log before it is streamed, and the transcript is already following
 * that stream — so `lastEventId` moving IS the signal that a node changed
 * state, and refreshing on it means the picture updates because the work
 * happened rather than because a clock went off.
 *
 * That also makes the diagram's liveness exactly as durable as everything else
 * here: a dropped connection replays from `Last-Event-ID`, the fold re-runs,
 * this refetches, and the nodes are where they actually are.
 *
 * ══ WHAT `approve` DOES, AND WHAT IT REFUSES TO DO ═════════════════════════
 *
 * It sends the arguments the proposal was made from and the fingerprint that
 * was on screen. It does not send a plan to run — `POST /api/storms` will not
 * take one, and that is the point: the harness re-proposes and compares, so
 * the object that executes is always one it built and validated itself.
 *
 * A 409 comes back as `StormDeviation` rather than as an error. The plan moving
 * between showing and saying yes is the contract working, and the caller's job
 * is to show what changed, not to retry.
 */

import { useCallback, useEffect, useState } from 'react';
import { EngineError } from './engine/client';
import {
  approveStorm,
  cancelStorm,
  listStorms,
  readStorm,
  readStormDeviation,
  runStorm,
  type Storm,
  type StormDeviation,
} from './engine/storm';

/** What an approval attempt produced. Exactly one of these is set. */
export type ApproveOutcome =
  | { kind: 'started'; storm: Storm }
  | { kind: 'deviated'; deviation: StormDeviation }
  | { kind: 'refused'; detail: string };

export interface StormsState {
  storms: Storm[];
  loading: boolean;
  error: string | null;
  /** The storm recorded against this build fingerprint, if there is one. */
  forFingerprint: (fingerprint: string) => Storm | null;
  approve: (
    threadId: number,
    fingerprint: string,
    proposalArgs: Record<string, unknown>,
    build: unknown,
  ) => Promise<ApproveOutcome>;
  cancel: (stormId: number) => Promise<void>;
  refresh: () => void;
}

export function useStorms(threadId: number | null, lastEventId: number): StormsState {
  const [storms, setStorms] = useState<Storm[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (threadId === null) {
      setStorms([]);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    listStorms(threadId)
      .then((rows) => {
        if (cancelled) return;
        setStorms(rows);
        setError(null);
      })
      .catch((failure: unknown) => {
        if (cancelled) return;
        /* A thread with no storms is a 200 with an empty list, so anything that
           lands here is a real failure and is reported rather than shown as
           "no storms" — which would read as "nothing was approved". */
        setError(failure instanceof Error ? failure.message : String(failure));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [threadId, lastEventId, nonce]);

  const refresh = useCallback(() => setNonce((value) => value + 1), []);

  const forFingerprint = useCallback(
    (fingerprint: string) =>
      storms.find((storm) => storm.fingerprint === fingerprint) ?? null,
    [storms],
  );

  const approve = useCallback(
    async (
      thread: number,
      fingerprint: string,
      proposalArgs: Record<string, unknown>,
      build: unknown,
    ): Promise<ApproveOutcome> => {
      let declared: Storm | null = null;
      try {
        declared = readStorm(
          await approveStorm(thread, fingerprint, proposalArgs, build),
        );
      } catch (failure) {
        if (failure instanceof EngineError) {
          const deviation = readStormDeviation(failure.body);
          if (deviation) return { kind: 'deviated', deviation };
          return { kind: 'refused', detail: failure.detail || failure.message };
        }
        return {
          kind: 'refused',
          detail: failure instanceof Error ? failure.message : String(failure),
        };
      }
      if (!declared) {
        return {
          kind: 'refused',
          detail:
            'The engine recorded an approval this interface could not read back, ' +
            'so nothing was started. Nothing here guesses at a storm it cannot see.',
        };
      }

      /* APPROVING AND STARTING ARE TWO ACTS AND TWO ROUTES, and the order
         matters: the contract is a row that is written once, and only then is
         anything asked to run. If the run call fails, what was approved is
         still recorded and still says so. */
      try {
        const started = readStorm(await runStorm(declared.id));
        refresh();
        return { kind: 'started', storm: started ?? declared };
      } catch (failure) {
        refresh();
        return {
          kind: 'refused',
          detail:
            (failure instanceof EngineError
              ? failure.detail || failure.message
              : String(failure)) +
            ' — the approval is recorded; nothing ran.',
        };
      }
    },
    [refresh],
  );

  const cancel = useCallback(
    async (stormId: number) => {
      try {
        await cancelStorm(stormId);
      } finally {
        refresh();
      }
    },
    [refresh],
  );

  return { storms, loading, error, forFingerprint, approve, cancel, refresh };
}
