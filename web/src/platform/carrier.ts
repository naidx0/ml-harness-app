import { Channel } from "@tauri-apps/api/core"

/**
 * A `fetch` whose requests to this machine travel through the shell.
 *
 * Their client takes a `fetch` override on the platform and uses it for every
 * call, the event stream included. This is that override. Requests to the
 * engine go to the shell's `engine_stream` command (`src-tauri/src/carrier.rs`),
 * which answers with ordered frames - a head, body chunks as they are read, an
 * end - and this wraps them in a real `Response` whose body is a
 * `ReadableStream`. Their SSE reader cannot tell it from the browser's fetch,
 * and the event stream is live rather than delivered at the end of a turn.
 *
 * WHY NOT THE BROWSER'S FETCH. The window's origin is the shell's custom
 * protocol, and Chromium treats a request from it to 127.0.0.1 as
 * public-to-private: CORS and private-network preflights stand between the
 * window and its own engine. The old frontend moved its traffic into the shell
 * for that reason (`engine_fetch`), and this keeps that property.
 *
 * Anything not addressed to this machine goes to the browser's fetch
 * untouched - a model-authored image URL is not the engine's business.
 */

export type Frame =
  | { kind: "head"; status: number; headers: [string, string][] }
  | { kind: "chunk"; data: string }
  | { kind: "end" }
  | { kind: "error"; message: string }

type Invoke = (command: string, args?: Record<string, unknown>) => Promise<unknown>

/** Loopback over plain http - the only requests the shell agrees to carry. */
export function isCarried(url: string) {
  if (!URL.canParse(url)) return false
  const parsed = new URL(url)
  return parsed.protocol === "http:" && (parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost")
}

let nextId = 1

export function createCarriedFetch(
  invoke: Invoke,
  makeChannel: (onFrame: (frame: Frame) => void) => unknown = (onFrame) => new Channel<Frame>(onFrame),
  fallback: typeof fetch = globalThis.fetch.bind(globalThis),
): typeof fetch {
  return async (input, init) => {
    const request = new Request(input, init)
    if (!isCarried(request.url)) return fallback(request)

    const id = nextId++
    const headers: [string, string][] = []
    request.headers.forEach((value, name) => headers.push([name, value]))
    const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.text()

    const encoder = new TextEncoder()
    let controller: ReadableStreamDefaultController<Uint8Array> | undefined
    let finished = false
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        controller = c
      },
      cancel() {
        finished = true
        void invoke("engine_stream_cancel", { id }).catch(() => {})
      },
    })

    return new Promise<Response>((resolve, reject) => {
      let headed = false
      const abort = () => {
        if (finished) return
        finished = true
        void invoke("engine_stream_cancel", { id }).catch(() => {})
        const reason = request.signal.reason ?? new DOMException("The request was aborted", "AbortError")
        if (headed) controller?.error(reason)
        else reject(reason)
      }
      if (request.signal.aborted) return abort()
      request.signal.addEventListener("abort", abort, { once: true })

      const channel = makeChannel((frame) => {
        if (finished && frame.kind !== "end" && frame.kind !== "error") return
        switch (frame.kind) {
          case "head":
            headed = true
            resolve(
              new Response(request.method === "HEAD" || frame.status === 204 ? null : stream, {
                status: frame.status,
                headers: frame.headers,
              }),
            )
            return
          case "chunk":
            controller?.enqueue(encoder.encode(frame.data))
            return
          case "end":
            if (!finished) controller?.close()
            finished = true
            request.signal.removeEventListener("abort", abort)
            if (!headed) reject(new TypeError("The engine closed the connection before answering"))
            return
          case "error":
            request.signal.removeEventListener("abort", abort)
            if (finished) return
            finished = true
            // Their client reads a network failure as a TypeError from fetch,
            // and so does their reconnect logic. Same shape, same handling.
            if (headed) controller?.error(new TypeError(frame.message))
            else reject(new TypeError(frame.message))
            return
        }
      })

      invoke("engine_stream", {
        id,
        url: request.url,
        method: request.method,
        headers,
        body,
        onFrame: channel,
      }).catch((error: unknown) => {
        if (finished) return
        finished = true
        reject(new TypeError(String(error)))
      })
    })
  }
}
