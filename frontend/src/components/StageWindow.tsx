/**
 * The detached instrument window — size C of the Stage.
 *
 * Opened at `/?stage=<threadId>`: by the shell as a second Tauri window, or by
 * a browser as a popup. It follows one thread and says so. It has no chat box
 * and no way to change anything: the conversation stays the driver, in the
 * main window, and this one is what the conversation looks at.
 *
 * Refresh follows the thread's own event stream, the same events the
 * transcript reads — a second reader, never a second stream of its own making
 * and never a timer.
 */

import { useEffect, useMemo, useReducer, useState } from 'react';

import { readCarve } from '../lib/engine/datawork';
import type { EngineEvent } from '../lib/engine/types';
import { openEventStream } from '../lib/engine/events';
import { readRecallReport } from '../lib/engine/retrieval';
import { initialStage, stageReducer } from '../lib/stageState';
import { foldEvents } from '../lib/transcript';
import { allReadsOf, latestReadOf } from '../lib/transcriptReads';
import { useStage } from '../lib/useStage';
import { Icon } from './Icon';
import { Stage } from './Stage';
import { StatusDot } from './primitives';
import { WindowControls } from './WindowControls';
/* The window shares the shell's sheets for the vocabulary the Stage borrows —
   `.tag`, `.vpill`, `.dot` — in the same order App.tsx loads them. */
import '../styles/shell.css';
import '../styles/provenance.css';
import '../styles/evals.css';

export function StageWindow({ threadId }: { threadId: number }) {
  const [lastEventId, setLastEventId] = useState(0);
  const [streamOpen, setStreamOpen] = useState(false);
  const [state, dispatch] = useReducer(stageReducer, undefined, initialStage);
  const stage = useStage(threadId, lastEventId, true);
  /* THE EVENTS ARE KEPT, NOT COUNTED. This window used to take an event's id
     and drop the event, so its Retrieval panel drew `recall={null}` — "no
     retriever scored in this thread yet", about a thread that had scored
     three. A recall score is in no table: the tool computes it, the reply
     carries it, and the event log is the only durable record. Same fold the
     transcript uses, same readers, so the two sizes of one Stage cannot
     disagree about what a thread measured. Keyed by id, because a reconnect
     replays from `Last-Event-ID` and may hand back a frame already held. */
  const [events, setEvents] = useState<Map<number, EngineEvent>>(new Map());

  useEffect(() => {
    const handle = openEventStream(`thread:${threadId}`, {
      since: 0,
      onEvent: (event) => {
        setLastEventId(event.id);
        setEvents((held) => {
          if (held.has(event.id)) return held;
          const next = new Map(held);
          next.set(event.id, event);
          return next;
        });
      },
      onStatus: (status) => setStreamOpen(status === 'open'),
    });
    return () => handle.close();
  }, [threadId]);

  const items = useMemo(
    () => foldEvents([...events.values()].sort((a, b) => a.id - b.id)),
    [events],
  );
  const recalls = useMemo(() => allReadsOf(items, readRecallReport), [items]);
  const carve = useMemo(() => latestReadOf(items, readCarve), [items]);

  useEffect(() => {
    document.title = `Instruments · thread ${threadId}`;
  }, [threadId]);

  return (
    <div className="stagewindow">
      <div className="stagewindow__bar" data-tauri-drag-region>
        <span className="wordmark">Instruments</span>
        <span>thread {threadId}</span>
        <span className="stagewindow__following">
          <StatusDot role={streamOpen ? 'st-done' : 'st-neutral'} shape="filled" />
          {streamOpen ? 'following' : 'reconnecting'}
        </span>
        <Icon name="panelleft" />
        {/* THIS WINDOW HAS NO NATIVE FRAME EITHER, and without these it could
            not be dismissed at all: `decorations: false` and a bar that is
            only a drag region is a window a person is stuck with. Closing it
            really closes it - see `hides_to_tray` in src-tauri/src/lib.rs. */}
        <WindowControls />
      </div>
      <Stage
        payload={stage.payload}
        state={state}
        dispatch={dispatch}
        size="window"
        recall={recalls}
        carve={carve}
        loading={stage.loading}
        error={stage.error}
      />
    </div>
  );
}
