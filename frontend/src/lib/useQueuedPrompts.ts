/**
 * WHAT YOU TYPED WHILE IT WAS STILL WORKING.
 *
 * Max, 2026-09-14: *"also add a queueing prompt feature."*
 *
 * A turn against a local 7B takes tens of seconds and sometimes minutes. The
 * composer was disabled for all of it - `canSend` is `!busy` - so a thought you
 * had while reading the reply either waited in your head or waited in the box
 * with the send button greyed out. Neither is the product doing its job: the
 * work is happening on the engine, and there is no reason the person has to
 * stand still while it does.
 *
 * ## What a queue must not do
 *
 * It must not fabricate a turn. Each queued line is sent as the PERSON'S OWN
 * message, in the order they typed it, exactly as if they had waited and
 * pressed send - the same rule `theBuildKeepsGoing.ts` states for never
 * inventing a "continue". A transcript that showed a message nobody typed, or
 * showed them in a different order, would be a transcript that lies about the
 * conversation.
 *
 * ## Why it drains one at a time
 *
 * A turn is one question and one answer. Sending three queued lines at once
 * would either concatenate three thoughts into one message - changing what was
 * asked - or start three turns against a model that can run one. So the queue
 * releases its head the moment the thread stops being busy, and waits again.
 *
 * ## Why the queue is not persisted
 *
 * It is a handful of seconds long by construction. Something typed and not yet
 * sent when the window closes was never sent, and reviving it on next launch
 * would put a question from yesterday at the top of today's conversation.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export interface QueuedPrompts {
  /** In the order they were typed. */
  waiting: readonly string[];
  /** Hold one back until the thread is free. */
  add: (text: string) => void;
  /** Take one out again - the person changed their mind. */
  drop: (index: number) => void;
  clear: () => void;
}

export function useQueuedPrompts(
  busy: boolean,
  send: (text: string) => void,
): QueuedPrompts {
  const [waiting, setWaiting] = useState<readonly string[]>([]);

  /* `send` is a new function on most renders, and an effect that depended on
     it would fire on every one of them. The queue only ever cares about the
     busy edge. */
  const sender = useRef(send);
  sender.current = send;

  /* ONE PER IDLE STRETCH, and this needed a latch rather than a condition.
     The first cut released whenever the thread was not busy, and setting the
     shorter queue re-ran the effect with `busy` still false - so it drained
     the whole queue in one cascade and started a turn per line. Caught by the
     test that asked for exactly one send; in the app it would have looked like
     three questions fired at once at a model that answers one.

     The latch clears when the thread goes busy again, which is what the send
     it just made will do. If that send never starts a turn, the rest wait -
     the honest failure, rather than firing them all at a provider that is
     already not answering. */
  const releasedThisIdle = useRef(false);
  useEffect(() => {
    if (busy) {
      releasedThisIdle.current = false;
      return;
    }
    if (releasedThisIdle.current || waiting.length === 0) return;
    releasedThisIdle.current = true;
    const [head, ...rest] = waiting;
    setWaiting(rest);
    sender.current(head);
  }, [busy, waiting]);

  const add = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setWaiting((was) => [...was, trimmed]);
  }, []);

  const drop = useCallback((index: number) => {
    setWaiting((was) => was.filter((_, at) => at !== index));
  }, []);

  const clear = useCallback(() => setWaiting([]), []);

  return { waiting, add, drop, clear };
}
