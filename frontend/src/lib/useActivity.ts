/**
 * WHICH CONVERSATIONS ARE WORKING, for the rail.
 *
 * Max, 2026-09-13: *"on the left chat side, we should have it so you can
 * actually see which sessions are running... I want to see a spinner or
 * something, or the context circle window should pop up on the chat side
 * rail."*
 *
 * The engine answers this off the event log (`app/activity.py`), so it is
 * true for work another window started and for a run taking turns with
 * nobody watching - which is the whole point of asking the engine rather
 * than tracking it here.
 *
 * A POLL, AND SAYING SO. The rail has no event stream of its own: one stream
 * per open thread is the design, and forty rails' worth of streams for the
 * threads you are NOT reading would be worse than this. Four seconds, and
 * the read costs about ten milliseconds against the owner's database.
 */

import { useEffect, useState } from 'react';

import { readActivity, type ActivityRead } from './engine/activity';

const EVERY = 4000;

export function useActivity(tick: number): ActivityRead {
  const [read, setRead] = useState<ActivityRead>({ threads: [], count: 0 });

  useEffect(() => {
    let live = true;
    const ask = () => {
      readActivity()
        .then((got) => {
          if (live) setRead(got);
        })
        .catch(() => {
          /* The engine is gone or restarting; the rail then shows nothing
             working, which is the honest reading of "we cannot ask". */
          if (live) setRead({ threads: [], count: 0 });
        });
    };
    ask();
    const timer = window.setInterval(ask, EVERY);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
    /* `tick` is the open thread's last event id: when the conversation you
       are reading moves, the others are worth re-reading too, and it costs
       one small query. */
  }, [tick]);

  return read;
}
