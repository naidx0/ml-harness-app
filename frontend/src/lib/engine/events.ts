/**
 * The event stream — `GET /api/events?scope=thread:7&since=0`.
 *
 *     id: 412
 *     event: chat.delta
 *     data: {"text":"…"}
 *
 * `app/events.py`: "the autoincrement id IS the SSE event id", and "nothing
 * streams that was not first durably written". Those two together are what
 * make a dropped connection cost nothing — a client that comes back says "I
 * had up to 412" and gets 413 onwards.
 *
 * ── WHY THIS IS A FETCH READER AND NOT `EventSource` ─────────────────────────
 *
 * The previous version of this file used `EventSource` and argued that writing
 * a reconnect loop would defeat the reason SSE was chosen. Three facts about
 * the engine that actually shipped make that wrong, and each one alone would
 * be enough:
 *
 * 1. **Every `/api/*` path requires `Authorization: Bearer …`**
 *    (`app/security.py requires_token`). `EventSource` has no API for request
 *    headers. In dev the Vite proxy fills the header in, so the gap is
 *    invisible; packaged, there is no proxy and the stream is a 401. A fetch
 *    reader sets the header itself and the gap closes rather than moving.
 *
 * 2. **The engine ends the response on purpose, roughly every 25 seconds**
 *    (`event_stream(timeout: float = 25.0)`), and immediately on `stream.end`.
 *    Reconnecting is the ordinary path through this code, not the exception,
 *    and a local model answering a real question takes longer than one
 *    connection lasts. This loop is not a replacement for SSE's reconnect —
 *    it IS the long-poll the engine is written for.
 *
 * 3. **`EventSource` only delivers frames you subscribed to by name.** The old
 *    reader listed fourteen fixed kinds. `app/tools/training.py` emits
 *    `train.<kind>` where the kind comes from the recipe's own structured
 *    output, so it is open-ended — every one of those frames would have been
 *    dropped in silence. A fetch reader parses the `event:` line and hands
 *    over whatever arrives.
 *
 * ── RESUMPTION ───────────────────────────────────────────────────────────────
 *
 * `Last-Event-ID` is sent as a header, which is what the engine prefers:
 *
 *     header = request.headers.get("last-event-id")
 *     cursor = since
 *     if header: cursor = int(header)
 *
 * `since` in the query string carries the same number, so a proxy that strips
 * the header cannot lose the client's place. And `onEvent` is expected to be
 * idempotent by `id` — `useChat` keys events in a Map — so even a full replay
 * is harmless. Three layers, because the cost of getting this wrong is a
 * duplicated token in the middle of a streamed sentence, which is visible.
 */

import { engineSession } from './config';
import { hasNativeShell, nativeEngineFetch } from './shell';
import { recoverFromUnauthorized } from './liveness';
import type { EngineEvent, EventScope } from './types';

export type StreamStatus =
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'failed'
  | 'closed';

export interface EventStreamOptions {
  /** Where to resume from. `0` means the whole thread from the beginning. */
  since?: number;
  onEvent: (event: EngineEvent) => void;
  onStatus?: (status: StreamStatus, detail?: string) => void;
}

export interface EventStreamHandle {
  /** Stop for good. Safe to call twice. */
  close: () => void;
  /** The highest event id delivered so far. */
  lastEventId: () => number;
  /**
   * Drop the current connection without stopping the stream — the loop
   * reconnects from `lastEventId` immediately.
   *
   * This exists to be *used*, not to be admired: it is how the reconnection
   * claim gets tested by pulling the cable mid-reply rather than by reading
   * the code and believing it.
   */
  interrupt: (why?: string) => void;
}

/** How long the engine is asked to hold one connection open. Its own default
 *  is 25s; naming it here means the client's expectation is explicit. */
const FOLLOW_SECONDS = 25;

/** Backoff after a failed connection, in milliseconds. A clean end (the
 *  engine's own timeout) reconnects immediately with no wait at all. */
const BACKOFF_MS = [500, 1000, 2000, 4000, 8000] as const;

export function openEventStream(
  scope: EventScope,
  options: EventStreamOptions,
): EventStreamHandle {
  const { since = 0, onEvent, onStatus } = options;

  let lastId = since;
  let closed = false;
  let failures = 0;
  let controller: AbortController | null = null;

  const status = (next: StreamStatus, detail?: string) => {
    if (!closed || next === 'closed') onStatus?.(next, detail);
  };

  void (async () => {
    status('connecting');
    while (!closed) {
      controller = new AbortController();
      try {
        const session = await engineSession();
        if (!session.available) {
          status('failed', session.reason ?? 'The engine is not running.');
          return;
        }

        /* ── IN THE SHELL, POLL THROUGH THE CARRIED WIRE ──────────────────
           The stream below reads a browser fetch body incrementally, and the
           browser's networking is exactly the layer the shell no longer
           trusts (see shell.ts). The engine's `follow=false` returns whatever
           exists and closes, so a fast poll over the carried wire delivers
           the same events with none of the browser's opinions. This is the
           bug the owner described as "my prompt disappears and it doesn't
           complete": the message POSTed, the reply streamed, and this loop -
           still on browser fetch - never heard any of it.

           Both wires produce the same `Response`, so everything downstream —
           the once-only 401 recovery, the error path, the frame reader — is
           one shared body of code rather than two that drift. */
        const carried =
          session.engineBaseUrl && hasNativeShell()
            ? await nativeEngineFetch(
                `${session.engineBaseUrl}/api/events?scope=${encodeURIComponent(scope)}` +
                  `&since=${lastId}&follow=false`,
                { token: session.token },
              )
            : null;

        let response = carried;
        if (!response) {
          const url =
            `${session.baseUrl}/api/events?scope=${encodeURIComponent(scope)}` +
            `&since=${lastId}&follow=true&timeout=${FOLLOW_SECONDS}`;

          const headers = new Headers({ Accept: 'text/event-stream' });
          if (session.token) headers.set('Authorization', `Bearer ${session.token}`);
          /* The whole reconnection story, in one header. */
          if (lastId > 0) headers.set('Last-Event-ID', String(lastId));

          response = await fetch(url, {
            headers,
            cache: 'no-store',
            signal: controller.signal,
          });
        }

        /* ── THE TOKEN ROTATED UNDER A LIVE STREAM ────────────────────────
           This loop is the one thing on the page that runs forever, so it is
           the one that meets a restarted engine first — and before this it met
           it by throwing "→ 401 Unauthorized" into the backoff and retrying
           the SAME dead token every 8 seconds, for as long as the tab stayed
           open. The status line read "reconnecting" the whole time, which is
           true and useless.

           One re-read of the session, then straight back round with whatever
           it found. `failures` is reset because a rotated token is not a flaky
           connection and should not inherit its backoff. */
        if (response.status === 401) {
          const recovery = await recoverFromUnauthorized(session.token);
          if (recovery.kind === 'retry') {
            failures = 0;
            status('reconnecting', 'the engine restarted — took its new token');
            continue;
          }
          const wait = BACKOFF_MS[Math.min(failures, BACKOFF_MS.length - 1)];
          failures += 1;
          /* Not `failed`: that stops the loop for good, and an engine that is
             being restarted comes back. Keep trying, but say the true thing
             while trying. */
          status('reconnecting', recovery.why);
          await sleep(wait);
          continue;
        }

        if (!response.ok || !response.body) {
          throw new Error(
            `GET /api/events → ${response.status} ${response.statusText}`,
          );
        }

        failures = 0;
        status('open');

        let heard = false;
        for await (const frame of readFrames(response.body)) {
          if (closed) break;
          heard = true;
          if (frame.id !== null && frame.id > lastId) lastId = frame.id;
          onEvent({
            id: frame.id ?? lastId,
            kind: frame.event,
            payload: frame.data,
          });
        }
        if (closed) break;

        /* A carried poll closes after handing over whatever existed, so the
           cadence lives here: quick while events flow, easy while idle. */
        if (carried) {
          await sleep(heard ? 150 : 600);
          continue;
        }

        /* The body ended. That is the engine's timeout or `stream.end`, both
           of which are normal. Go straight round again — no backoff, because
           nothing failed. */
        status('connecting');
      } catch (error) {
        if (closed) break;
        if (isAbort(error)) {
          /* interrupt() — deliberate, so it is not a failure. Straight back. */
          status('reconnecting', 'connection dropped on purpose');
          continue;
        }
        const wait = BACKOFF_MS[Math.min(failures, BACKOFF_MS.length - 1)];
        failures += 1;
        status(
          'reconnecting',
          `${error instanceof Error ? error.message : String(error)} — retrying in ${wait}ms`,
        );
        await sleep(wait);
      }
    }
  })();

  return {
    close() {
      if (closed) return;
      closed = true;
      controller?.abort();
      status('closed');
    },
    lastEventId: () => lastId,
    interrupt(why = 'interrupted') {
      if (closed) return;
      status('reconnecting', why);
      controller?.abort();
    },
  };
}

/* ── SSE parsing ─────────────────────────────────────────────────────────────
   Frames are separated by a blank line. A line starting with `:` is a comment
   (the engine sends `: keep-alive` to hold the socket open through a proxy)
   and carries no id, because it is not an event. */

interface RawFrame {
  id: number | null;
  event: string;
  data: unknown;
}

async function* readFrames(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<RawFrame> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let split = buffer.indexOf('\n\n');
      while (split !== -1) {
        const block = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);
        const frame = parseFrame(block);
        if (frame) yield frame;
        split = buffer.indexOf('\n\n');
      }
    }
    const tail = parseFrame(buffer);
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}

function parseFrame(block: string): RawFrame | null {
  const text = block.replace(/\r/g, '').trim();
  if (!text || text.startsWith(':')) return null;

  let id: number | null = null;
  let event = 'message';
  const dataLines: string[] = [];

  for (const line of text.split('\n')) {
    if (line.startsWith('id:')) {
      const parsed = Number(line.slice(3).trim());
      if (Number.isFinite(parsed)) id = parsed;
    } else if (line.startsWith('event:')) {
      event = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''));
    }
  }

  if (dataLines.length === 0 && id === null) return null;
  return { id, event, data: parseData(dataLines.join('\n')) };
}

function parseData(data: string): unknown {
  try {
    return JSON.parse(data);
  } catch {
    /* A frame that is not JSON is data too. Returning the raw string beats
       dropping the one message that mattered. */
    return data;
  }
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
