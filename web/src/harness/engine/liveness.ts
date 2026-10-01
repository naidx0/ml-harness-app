/**
 * Is the engine this window started with still the one answering?
 *
 * `GET /health` names the process (`engine.pid`, `engine.engine_id`) and the
 * code it runs (`build.code_fingerprint`). The window remembers the first
 * answer and compares every later one against it. Four outcomes, and each
 * needs a different sentence and a different button:
 *
 *   ok         - same engine, ready. Say nothing.
 *   gone       - nothing answered. The engine stopped or crashed; start it.
 *   not-ready  - the engine answered 503: it is up, but one of its own health
 *                checks failed. Starting it again is the wrong advice - it is
 *                running - so the notice names the failing checks instead.
 *   restarted  - a DIFFERENT engine answered. Its token is new, so requests
 *                made with the old one will be refused until the window
 *                reloads.
 *
 * Pure, so it is tested without a network.
 */

export type Check = { name: string; ok: boolean; detail: string }

export type Health = {
  status?: string
  engine?: { pid?: number; engine_id?: string }
  build?: { code_fingerprint?: string }
  checks?: Check[]
}

export type Identity = { engineId?: string; pid?: number; fingerprint?: string }

export type Liveness = "ok" | "gone" | "not-ready" | "restarted"

/** One `/health` answer: the body, and the status code it came with. */
export type Reading = { status: number; health: Health }

export function identityOf(health: Health): Identity {
  return { engineId: health.engine?.engine_id, pid: health.engine?.pid, fingerprint: health.build?.code_fingerprint }
}

/**
 * The reading inside a failed `/health` request, when there is one. The
 * engine answers 503 WITH the full readout when a check fails; anything
 * without a body (a refused connection, a proxy error page) is no reading.
 * Structural rather than `instanceof HarnessError`, to stay pure.
 */
export function readingOfFailure(failure: unknown): Reading | undefined {
  const record = failure as { status?: unknown; body?: unknown } | null
  if (!record || typeof record.status !== "number") return undefined
  const body = record.body
  if (!body || typeof body !== "object" || Array.isArray(body)) return undefined
  return { status: record.status, health: body as Health }
}

export function failingChecks(health: Health | undefined): Check[] {
  return (health?.checks ?? []).filter((check) => check && check.ok === false)
}

export function classify(first: Identity | undefined, reading: Health | Reading | undefined): Liveness {
  if (!reading) return "gone"
  // A bare body is a 200: `harness()` only returns one for a 2xx answer.
  const { status, health }: Reading = "health" in reading ? reading : { status: 200, health: reading }
  if (first) {
    const now = identityOf(health)
    if (first.engineId && now.engineId && first.engineId !== now.engineId) return "restarted"
    if (first.pid && now.pid && first.pid !== now.pid) return "restarted"
  }
  if (status === 503) return "not-ready"
  if (status < 200 || status >= 300) return "gone"
  return "ok"
}
