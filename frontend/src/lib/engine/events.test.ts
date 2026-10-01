/**
 * The reconnection claim, tested by pulling the cable.
 *
 * `events.ts` carries the strongest promise this product makes about its own
 * durability: *"A dropped connection, a closed laptop, a page reload all cost
 * nothing — reopening replays from `since` and reconstructs the turn."* The
 * cursor that makes it true is `lastId`, advanced inside the frame loop and
 * spent on the next request as both `?since=` and the `Last-Event-ID` header.
 *
 * **Nothing on `origin/main` tested any of it.** No test file referenced
 * `openEventStream` at all, so the promise was carried entirely by the
 * comments describing it — including `interrupt()`, whose own docstring says
 * it *"exists to be used, not to be admired: it is how the reconnection claim
 * gets tested by pulling the cable mid-reply rather than by reading the code
 * and believing it."* This file is that use.
 *
 * The engine is not started here. `fetch` is stubbed with a body that ends
 * when the test says so, which is what makes "the cable was pulled after
 * event 7" a thing a test can arrange at all.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const A_SESSION = {
  available: true,
  baseUrl: '/engine',
  engineBaseUrl: null,
  token: 'a-token',
  identity: null,
  reason: null,
};

vi.mock('./config', () => ({
  engineSession: () => Promise.resolve(A_SESSION),
  refreshEngineSession: () => Promise.resolve(A_SESSION),
}));

vi.mock('./shell', () => ({
  hasNativeShell: () => false,
  nativeEngineFetch: () => Promise.resolve(null),
}));

vi.mock('./liveness', () => ({
  recoverFromUnauthorized: () => Promise.resolve({ kind: 'stuck', why: 'no' }),
}));

const { openEventStream } = await import('./events');

/** One SSE frame, in the wire's own shape. */
function frame(id: number, kind: string, payload: unknown): string {
  return `id: ${id}\nevent: ${kind}\ndata: ${JSON.stringify(payload)}\n\n`;
}

/** A response whose body yields `chunks` and then ends — a connection that
 *  closed, which is exactly what the loop must survive. */
function streamOf(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

interface Call {
  url: string;
  lastEventId: string | null;
}

describe('the event stream reconnects from where it stopped', () => {
  let calls: Call[];

  beforeEach(() => {
    calls = [];
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  /** Stub fetch so each connection serves one scripted body, then hangs. */
  function serve(bodies: string[][]) {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init: RequestInit = {}) => {
        const headers = new Headers(init.headers);
        calls.push({ url: String(url), lastEventId: headers.get('Last-Event-ID') });
        const next = bodies[calls.length - 1];
        if (!next) {
          // No more scripted connections: park here instead of spinning while
          // the test makes its assertions - but HONOUR THE ABORT SIGNAL, the
          // way a real fetch does. A stub that ignored it made `interrupt()`
          // look broken when it was the stub that could not be interrupted.
          return new Promise<Response>((_resolve, reject) => {
            const signal = init.signal;
            if (!signal) return;
            if (signal.aborted) {
              reject(new DOMException('aborted', 'AbortError'));
              return;
            }
            signal.addEventListener('abort', () =>
              reject(new DOMException('aborted', 'AbortError')),
            );
          });
        }
        return Promise.resolve(streamOf(next));
      }),
    );
  }

  async function settle(times = 6) {
    for (let i = 0; i < times; i += 1) await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
  }

  it('asks from since=0 with no Last-Event-ID on the first connection', async () => {
    serve([[]]);
    const handle = openEventStream('thread:33', { since: 0, onEvent: () => {} });
    await settle();

    expect(calls[0].url).toContain('since=0');
    expect(calls[0].url).toContain('scope=thread%3A33');
    expect(
      calls[0].lastEventId,
      'a first connection has nothing to resume from and must not claim to',
    ).toBeNull();

    handle.close();
  });

  it('carries the highest id it saw into the next connection, twice over', async () => {
    const seen: number[] = [];
    serve([
      [frame(5, 'chat.delta', { text: 'a' }), frame(7, 'chat.delta', { text: 'b' })],
      [frame(9, 'chat.end', {})],
    ]);

    const handle = openEventStream('thread:33', {
      since: 0,
      onEvent: (event) => seen.push(event.id),
    });
    await settle(40);

    expect(seen).toEqual([5, 7, 9]);
    expect(handle.lastEventId()).toBe(9);

    // The second connection resumes from 7 - the highest id the FIRST one
    // delivered - in both the query and the header. This is the whole claim.
    expect(calls[1].url).toContain('since=7');
    expect(calls[1].lastEventId).toBe('7');

    // And the third resumes from 9, so the cursor advances rather than
    // sticking at whatever the first reconnection happened to use.
    expect(calls[2].url).toContain('since=9');
    expect(calls[2].lastEventId).toBe('9');

    handle.close();
  });

  it('an interrupt reconnects from the cursor rather than from zero', async () => {
    serve([
      [frame(4, 'chat.delta', { text: 'x' })],
      [frame(6, 'chat.delta', { text: 'y' })],
    ]);

    const handle = openEventStream('thread:33', { since: 0, onEvent: () => {} });
    await settle(40);

    const before = calls.length;
    handle.interrupt('pulled by a test');
    await settle(40);

    expect(
      calls.length,
      'interrupt() did not cause a reconnection',
    ).toBeGreaterThan(before);
    for (const call of calls.slice(1)) {
      expect(
        call.url,
        'a reconnection went back to since=0 and would replay the whole thread',
      ).not.toContain('since=0');
    }

    handle.close();
  });

  it('close stops the loop: no connection is opened after it', async () => {
    serve([[frame(2, 'chat.delta', { text: 'z' })]]);
    const handle = openEventStream('thread:33', { since: 0, onEvent: () => {} });
    await settle(40);

    handle.close();
    const after = calls.length;
    await settle(40);

    expect(calls.length).toBe(after);
  });

  it('a caller that resumes hands its own cursor to the first request', async () => {
    serve([[]]);
    const handle = openEventStream('thread:33', { since: 41, onEvent: () => {} });
    await settle();

    expect(calls[0].url).toContain('since=41');
    expect(calls[0].lastEventId).toBe('41');

    handle.close();
  });
});
