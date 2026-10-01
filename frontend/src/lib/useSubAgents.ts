/**
 * THE PHASES THIS CONVERSATION HANDED OUT, followed from the page.
 *
 * Two clocks, on purpose. The thread's own event id moves when a sub-agent
 * starts, finishes or is folded back in, because all three write events on the
 * PARENT thread - so the strip is right the instant something changes here.
 * But a sub-agent's own progress writes events on the CHILD, which this window
 * is not streaming, so a slow poll fills that in: how many steps it has ticked
 * while it works. The poll runs only while something is working, which is the
 * only time the answer can change without an event.
 */

import { useCallback, useEffect, useState } from 'react';

import { NONE, readSubAgents, stopSubAgent, type SubAgentRead } from './engine/subagents';

const WHILE_WORKING = 3000;

export interface SubAgentsView {
  read: SubAgentRead;
  stop: (id: number) => Promise<void>;
  refresh: () => Promise<void>;
}

export function useSubAgents(threadId: number | null, lastEventId: number): SubAgentsView {
  const [read, setRead] = useState<SubAgentRead>(NONE);

  const refresh = useCallback(async () => {
    if (threadId === null) {
      setRead(NONE);
      return;
    }
    try {
      setRead(await readSubAgents(threadId));
    } catch {
      /* The engine is gone or restarting. Drawing nothing is the honest
         reading of "we cannot ask", the same as the rail's. */
      setRead(NONE);
    }
  }, [threadId]);

  useEffect(() => {
    void refresh();
  }, [refresh, lastEventId]);

  const working = read.running > 0;
  useEffect(() => {
    if (!working) return undefined;
    const timer = window.setInterval(() => void refresh(), WHILE_WORKING);
    return () => window.clearInterval(timer);
  }, [working, refresh]);

  const stop = useCallback(
    async (id: number) => {
      try {
        await stopSubAgent(id);
      } finally {
        await refresh();
      }
    },
    [refresh],
  );

  return { read, stop, refresh };
}
