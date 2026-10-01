import { FACADE } from "./engine"

/**
 * Their client's fetch: engine `/api/*` requests are sent to the facade.
 *
 * FOUND WHILE BUILDING THE FACADE: their generated client builds every URL as
 * `new URL("/api/session", baseUrl)`. That path is absolute, so a base of
 * `http://127.0.0.1:8078/oc` loses its `/oc` and the request lands on the
 * engine's root. The engine keeps their protocol under `/oc` on purpose - the
 * security boundary and their error shape key off the prefix - so the prefix
 * is put back here, in the one fetch only their client uses.
 *
 * The rule is unambiguous because their client never calls a harness route:
 * the harness's own surfaces use `harness()` (web/src/harness/engine.ts), which
 * is handed the unwrapped fetch. Anything not addressed to the engine's origin
 * passes through untouched.
 */
export function facadeFetch(base: typeof fetch, engineOrigin: string): typeof fetch {
  const origin = new URL(engineOrigin).origin
  return async (input, init) => {
    const request = new Request(input, init)
    const url = new URL(request.url)
    if (url.origin !== origin || !url.pathname.startsWith("/api/")) return base(request)
    url.pathname = `${FACADE}${url.pathname}`
    // BUFFER THE BODY; NEVER PASS THE REQUEST THROUGH. `new Request(url,
    // request)` turns a body into a stream, and Chromium sends streamed
    // uploads only over HTTP/2 - so every POST with a body failed with
    // ERR_ALPN_NEGOTIATION_FAILED against the HTTP/1.1 engine, found by
    // walking the app in a browser. Their bodies are small JSON.
    const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer()
    return base(url, {
      method: request.method,
      headers: request.headers,
      body,
      signal: request.signal,
      credentials: request.credentials,
      cache: request.cache,
      redirect: request.redirect,
    })
  }
}
