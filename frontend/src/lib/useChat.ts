/**
 * One turn of the conversation, from the browser's side.
 *
 * The whole loop is four calls and one rule about their order:
 *
 *   1. `POST /api/threads`                 — only if there is no thread yet
 *   2. open `GET /api/events?scope=thread:N` and keep it open
 *   3. `POST /api/threads/N/messages`      — writes `message.created`
 *   4. `POST /api/threads/N/turn`          — blocks for the whole turn
 *
 * **Step 4 is not where the reply comes from.** It returns the ids of the rows
 * the turn wrote, after the turn is over. Every token arrives on the stream
 * from step 2, because `app/conductor.py` commits each delta before it yields
 * it. That separation is the entire reason a closed laptop costs nothing, and
 * it is why this hook does not await the turn before rendering anything.
 *
 * It also means there is no race worth defending against. The stream is opened
 * with `since=0` and replays the thread from the beginning, so even if step 3
 * lands before the socket is up, nothing is missed. Events are kept in a Map
 * keyed by `events.id`, so a replay is idempotent by construction rather than
 * by timing.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  EngineError,
  createThread,
  postMessage,
  runTurn,
} from './engine/client';
import { openEventStream, type EventStreamHandle, type StreamStatus } from './engine/events';
import type { EngineEvent } from './engine/types';
import { foldEvents, type TranscriptItem } from './transcript';

/** What the composer is doing. `running` means a turn is in flight on the
 *  engine — which survives this page, so it is not a spinner we own. */
export type TurnState = 'idle' | 'sending' | 'running';

export interface ChatState {
  threadId: number | null;
  items: TranscriptItem[];
  /** True while the engine is mid-turn and the last assistant row should carry
   *  a caret. */
  streaming: boolean;
  turn: TurnState;
  /** THE ENGINE is mid-turn, whoever started it. `turn` above is this page's
   *  own record of a fetch it issued; a run's turns never touch it, so a
   *  control gated on `turn` is blind for the whole of a run. Read off the
   *  stream: a `turn.started` with no `stream.end` after it. */
  engineWorking: boolean;
  status: StreamStatus;
  statusDetail: string;
  /** The last thing that went wrong, in the engine's own words. */
  error: string | null;
  lastEventId: number;
  eventCount: number;
  send: (text: string) => Promise<void>;
  /** Run one more turn with NO new message. This is how a building thread
   *  works down its plan: `POST /api/threads/{id}/turn` already takes no
   *  message, so nothing has to fabricate a "continue" the person did not
   *  type. See `lib/theBuildKeepsGoing.ts` for what decides to call it. */
  continueTurn: () => Promise<void>;
  /** Open a thread, or start a new one. `projectId` is where a NEW thread will
   *  be created — the project of the thread you were reading, so a new
   *  conversation lands beside the one that prompted it. `null` hands the
   *  choice to the engine's own `db.default_project()` rather than to a second
   *  rule in the browser that could disagree with it. */
  openThread: (id: number | null, projectId?: number | null) => void;
  dismissError: () => void;
  /** Drop the live connection without stopping the stream. Used to prove the
   *  reconnection claim by pulling the cable rather than by reading the code. */
  interrupt: () => void;
}

export function useChat(
  onThreadCreated?: (id: number) => void,
  inviteGoalEdit?: boolean,
  /** CS7 — after creating a thread, apply start-sheet mode/permission/project. */
  prepareNewThread?: (threadId: number) => Promise<void>,
): ChatState {
  const [threadId, setThreadId] = useState<number | null>(null);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [events, setEvents] = useState<EngineEvent[]>([]);
  const [status, setStatus] = useState<StreamStatus>('closed');
  const [statusDetail, setStatusDetail] = useState('');
  const [turn, setTurn] = useState<TurnState>('idle');
  const [error, setError] = useState<string | null>(null);

  const stream = useRef<EventStreamHandle | null>(null);
  /** Keyed by `events.id`, so a replay after a reconnect cannot duplicate a
   *  token in the middle of a streamed sentence. */
  const byId = useRef(new Map<number, EngineEvent>());
  /* A "latest" ref, written in an effect rather than during render: the stream
     effect must not re-run just because the parent passed a new closure, and
     writing a ref during render is a rule React does not bend on. */
  const created = useRef(onThreadCreated);
  const invite = useRef(inviteGoalEdit);
  useEffect(() => {
    created.current = onThreadCreated;
  }, [onThreadCreated]);
  useEffect(() => {
    invite.current = inviteGoalEdit;
  }, [inviteGoalEdit]);

  /* One stream per thread. Closing is the cleanup, so a thread switch cannot
     leave a reader running against the thread you just left. */
  useEffect(() => {
    byId.current = new Map();
    setEvents([]);
    if (threadId === null) {
      setStatus('closed');
      setStatusDetail('');
      return;
    }

    const handle = openEventStream(`thread:${threadId}`, {
      since: 0,
      onStatus: (next, detail) => {
        setStatus(next);
        setStatusDetail(detail ?? '');
      },
      onEvent: (event) => {
        const seen = byId.current;
        if (seen.has(event.id)) return;
        seen.set(event.id, event);
        setEvents([...seen.values()].sort((a, b) => a.id - b.id));
      },
    });
    stream.current = handle;
    return () => {
      handle.close();
      stream.current = null;
    };
  }, [threadId]);

  /* `stream.end` is the engine saying the turn is over. Trusting the event
     rather than the `POST /turn` promise is deliberate: the promise belongs to
     this page and the event belongs to the thread, and only one of those two
     survives a reload. */
  useEffect(() => {
    const last = events[events.length - 1];
    if (last?.kind === 'stream.end') setTurn('idle');
  }, [events]);

  /* IS THE ENGINE WORKING? NOT "DID THIS PAGE START SOMETHING".
   *
   * `turn` above is this browser's own record of a fetch it issued, and it is
   * the wrong instrument for the question the composer asks. Max, 2026-09-19:
   * *"There's no stop button while the model's working. You can literally see
   * it highlighted on the chat that I can see on my GPU."*
   *
   * A RUN never touches `turn`. `POST /run` returns in milliseconds, a daemon
   * thread takes the turns, and `turn` stays 'idle' for the whole run - so a
   * Stop button gated on `turn` is never drawn while the thing it stops is
   * the thing actually running. Worse, a run's `stream.end` landing during a
   * hand-driven turn flipped `turn` to 'idle' under it.
   *
   * The engine's own answer is in the stream: a `turn.started` with no
   * `stream.end` after it. The same read `app/interrupt.py::a_turn_is_running`
   * does on the server, so the button and the route cannot disagree about
   * whether there is anything to stop. Backwards, and stops at the first of
   * either - the whole array would be a scan per render. */
  const engineWorking = useMemo(() => {
    for (let index = events.length - 1; index >= 0; index -= 1) {
      const kind = events[index].kind;
      if (kind === 'stream.end') return false;
      if (kind === 'turn.started') return true;
    }
    return false;
  }, [events]);

  const items = useMemo(() => foldEvents(events), [events]);

  const prepare = useRef(prepareNewThread);
  prepare.current = prepareNewThread;

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content) return;
      setError(null);
      setTurn('sending');

      let target = threadId;
      try {
        if (target === null) {
          /* The thread is named after the thing that started it. A generated
             id in the rail tells the user nothing about their own work. */
          const thread = await createThread(title(content), projectId);
          target = thread.id;
          setThreadId(target);
          if (prepare.current) await prepare.current(target);
          created.current?.(target);
        }
        await postMessage(target, content);
        setTurn('running');
        await runTurn(target, {
          invite_goal_edit: Boolean(invite.current),
        });
      } catch (failure) {
        setError(describe(failure));
      } finally {
        setTurn('idle');
      }
    },
    [threadId, projectId],
  );

  /* No thread is created here and no message is posted: a continuation is
     only meaningful for a thread that already has both. */
  const continueTurn = useCallback(async () => {
    if (threadId === null) return;
    setError(null);
    setTurn('running');
    try {
      await runTurn(threadId, {
        invite_goal_edit: Boolean(invite.current),
      });
    } catch (failure) {
      setError(describe(failure));
    } finally {
      setTurn('idle');
    }
  }, [threadId]);

  const openThread = useCallback(
    (id: number | null, target: number | null = null) => {
      setError(null);
      setTurn('idle');
      setThreadId(id);
      setProjectId(target);
    },
    [],
  );

  return {
    threadId,
    items,
    streaming: turn === 'running',
    turn,
    /** The ENGINE is mid-turn, whoever started it - a run counts. */
    engineWorking,
    status,
    statusDetail,
    error,
    lastEventId: events.length ? events[events.length - 1].id : 0,
    eventCount: events.length,
    send,
    continueTurn,
    openThread,
    dismissError: () => setError(null),
    interrupt: () => stream.current?.interrupt('dropped by hand, to test replay'),
  };
}

/** A thread title from the first thing the user said. The engine caps it at
 *  200 characters; this cuts at a word boundary well before that. */
function title(content: string): string {
  const oneLine = content.replace(/\s+/g, ' ').trim();
  if (oneLine.length <= 72) return oneLine;
  const cut = oneLine.slice(0, 72);
  const space = cut.lastIndexOf(' ');
  return `${space > 32 ? cut.slice(0, space) : cut}…`;
}

/** The engine's own words where there are any. A 409 from `POST /turn` says
 *  "No model is connected. Connect one, or use the controls directly — every
 *  tool in this app is also a button", which is better than a paraphrase. */
function describe(failure: unknown): string {
  if (failure instanceof EngineError) return failure.message;
  if (failure instanceof Error) return failure.message;
  return String(failure);
}
