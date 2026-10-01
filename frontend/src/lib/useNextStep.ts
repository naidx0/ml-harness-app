/**
 * The engine's next question, for the open conversation.
 *
 * `GET /api/next_step` assembles the thread's evidence, runs the diagnosis and
 * derives THE question that would move it — `app/asking.py`. This hook holds
 * that answer and re-asks when it could have changed.
 *
 * ══ WHEN IT RE-ASKS, AND WHY IT IS NOT A POLL ══════════════════════════════
 *
 * Three moments, all of them things that actually move the ledger:
 *
 *   1. the open thread changes — a different conversation has different facts;
 *   2. a turn finishes — the model may have run a tool that measured something;
 *   3. `answered()` — the card's own tool call came back ok.
 *
 * There is no interval. A question is derived from evidence, evidence changes
 * when somebody records something, and a timer that re-asked every few seconds
 * would spend the engine's time to re-derive a card nobody had touched. It
 * would also make the card flicker between two identical renders, which reads
 * as the product being unsure.
 *
 * ══ WHAT IT DOES WITH A FAILURE, WHICH IS NOTHING ══════════════════════════
 *
 * `question` goes null and `error` carries the sentence. It does NOT fall back
 * to a remembered card: a question derived from a fact sheet that has since
 * changed is a question about a diagnosis that no longer exists, and a stale
 * card is worse than no card because a person cannot tell it is stale. The
 * transcript renders `QuestionCard`'s own client-side derivation in that case,
 * which is what it did before this hook existed and is visibly the fallback.
 */

import { useCallback, useEffect, useState } from 'react';
import { readNextStep, getNextStep, type NextStepPayload } from './engine/asking';

export interface NextStepState {
  /** The whole payload, or null when the engine has not answered or would not. */
  step: NextStepPayload | null;
  loading: boolean;
  error: string | null;
  /** An answer landed through the tool boundary; ask the engine again. */
  answered: () => void;
}

export function useNextStep(
  threadId: number | null,
  /** Bumped when a turn ends. See the header — this is a REASON to re-ask, not
   *  a clock. */
  turnKey: number,
): NextStepState {
  const [step, setStep] = useState<NextStepPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    getNextStep(threadId)
      .then((body) => {
        if (!live) return;
        const parsed = readNextStep(body);
        /* `readNextStep` returning null is the reader refusing a payload it
           could not read as a card — see `engine/asking.ts`. That is not an
           error to show a person; it is the surface declining to draw
           something, and the fallback derivation takes over. */
        setStep(parsed);
      })
      .catch((failure: unknown) => {
        if (!live) return;
        setStep(null);
        setError(failure instanceof Error ? failure.message : String(failure));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [threadId, turnKey, nonce]);

  const answered = useCallback(() => setNonce((n) => n + 1), []);

  return { step, loading, error, answered };
}
