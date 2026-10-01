import type { ServerConnection } from "@/runtime/server/registry"
import { FACADE } from "../platform/engine"

/**
 * The harness's own API, for surfaces OpenCode has no equivalent of.
 *
 * Their client speaks their protocol through the /oc facade. Stage, Plan,
 * Context, Journey and the rest read the engine's own routes (`/api/*`,
 * `/local_specs`, `/health`) - the same ones the outgoing frontend used, which
 * is what keeps a harness surface from needing a facade operation invented
 * for it.
 *
 * Same engine, same token, same wire: the base is the facade URL without its
 * `/oc`, and requests go through the platform's fetch, so inside the shell
 * they travel the carrier like everything else.
 */

type Fetch = typeof globalThis.fetch

let current: { base: string; token: string; fetch: Fetch } | undefined

export function setHarnessEngine(server: ServerConnection.Any, fetch: Fetch = globalThis.fetch.bind(globalThis)) {
  const url = server.http.url.replace(/\/+$/, "")
  current = {
    base: url.endsWith(FACADE) ? url.slice(0, -FACADE.length) : url,
    token: server.http.password ?? "",
    fetch,
  }
}

export class HarnessError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** The parsed answer, kept: some refusals carry more than a sentence -
     *  `/health`'s 503 is the whole readout with the failing `checks`. */
    readonly body?: unknown,
  ) {
    super(message)
  }
}

/**
 * One request to the engine. JSON in, JSON out; a non-2xx answer throws with
 * the engine's own `detail`, because that sentence was written for a person,
 * and carries the parsed body on `HarnessError.body` for a caller that reads it.
 */
export async function harness<T = unknown>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  if (!current) throw new Error("The harness engine is not connected yet.")
  const response = await current.fetch(`${current.base}${path}`, {
    method: init.method ?? (init.body === undefined ? "GET" : "POST"),
    headers: {
      Authorization: `Bearer ${current.token}`,
      ...(init.body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  })
  const text = await response.text()
  const data = text ? safeJson(text) : undefined
  if (!response.ok) {
    const detail = (data as { detail?: unknown } | undefined)?.detail
    throw new HarnessError(response.status, sentenceOf(detail) ?? `${response.status} from ${path}`, data)
  }
  return data as T
}

/**
 * The engine's refusal as a sentence, whatever shape it came in. FastAPI's
 * own validation errors are a list of `{msg}`; some harness routes answer
 * `{detail: {message}}` or `{detail: {reason}}`. Each carries a sentence
 * written for a person, and a bare status code would throw it away.
 */
export function sentenceOf(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    const parts = detail.map(sentenceOf).filter((part): part is string => !!part)
    return parts.length ? parts.join("; ") : undefined
  }
  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>
    for (const key of ["message", "msg", "reason", "detail", "error"]) {
      const found = sentenceOf(record[key])
      if (found) return found
    }
  }
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}
