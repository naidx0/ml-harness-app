/**
 * Which engine this window talks to, read off `GET /health` (app/main.py,
 * built from `app/identity.identity()`) and, inside the desktop shell, off
 * `engine_status` (the portfile minus its token, plus a checkout if the shell
 * knows one).
 *
 * Pure, so the comparisons are tested without an engine. The outgoing About
 * section made the same two comparisons; the rules are kept:
 *
 *   - Build vs checkout: prefix comparison both ways, because one side is
 *     routinely abbreviated (7 characters against 40). No checkout, or no
 *     build sha, is "cannot tell" - never "matches".
 *   - Portfile vs socket: `engine.json` names an engine id; `/health` names
 *     the one actually answering. Different ids is a different process on the
 *     port than the one the file describes.
 */

export type Health = {
  status?: string
  engine?: {
    engine_id?: string
    pid?: number
    started_at?: string
    uptime_seconds?: number
  }
  build?: {
    sha?: string | null
    sha_source?: string
    sha_read_at?: string
    dirty?: boolean | null
    code_fingerprint?: string | null
    code_files?: number
    python?: string
    executable?: string
  }
  schema?: { build_knows?: number | null; database_at?: number | null; agrees?: boolean }
  database?: { path?: string | null; runs?: number; instance_id?: string | null }
  checks?: { name: string; ok: boolean; detail: string }[]
}

/** What the shell's `engine_status` returns. Never carries the token here. */
export type ShellStatus = {
  base_url?: string
  error?: string
  engine?: { engine?: { engine_id?: string; pid?: number }; engine_id?: string } & Record<string, unknown>
  checkout?: { revision?: unknown; source?: unknown } | null
}

/** Short hex for a person to read aloud; the full value goes in a tooltip. */
export function shortHex(value: string | null | undefined, keep = 12): string {
  if (!value) return ""
  return value.length > keep ? value.slice(0, keep) : value
}

export type Verdict =
  | { kind: "matches"; text: string }
  | { kind: "differs"; text: string }
  | { kind: "unknown"; text: string }

/** Does the engine run the code this app was built from? */
export function checkoutVerdict(sha: string | null | undefined, checkout: ShellStatus["checkout"]): Verdict {
  const revision = typeof checkout?.revision === "string" ? checkout.revision.trim().toLowerCase() : ""
  if (!revision) {
    return {
      kind: "unknown",
      text: "Cannot tell: this window was not given a checkout revision to compare against (an installed app has none).",
    }
  }
  const engine = (sha ?? "").trim().toLowerCase()
  if (!engine) return { kind: "unknown", text: "Cannot tell: the engine did not report which commit it runs." }
  const same = engine.startsWith(revision) || revision.startsWith(engine)
  return same
    ? { kind: "matches", text: `Matches this app's checkout (${shortHex(engine)})` }
    : {
        kind: "differs",
        text: `Engine ${shortHex(engine)}, app ${shortHex(revision)} - restart the engine or reinstall`,
      }
}

/** Is the engine answering the one `engine.json` describes? */
export function portfileVerdict(status: ShellStatus | undefined, health: Health | undefined): Verdict | undefined {
  const published = status?.engine?.engine?.engine_id ?? status?.engine?.engine_id
  const answering = health?.engine?.engine_id
  if (typeof published !== "string" || !published || !answering) return undefined
  return published === answering
    ? { kind: "matches", text: "The engine answering is the one engine.json describes" }
    : {
        kind: "differs",
        text: `engine.json describes ${shortHex(published)}, but ${shortHex(answering)} is answering - something else is on the port`,
      }
}

export function formatUptime(seconds: number | undefined): string | undefined {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return undefined
  const whole = Math.floor(seconds)
  const days = Math.floor(whole / 86400)
  const hours = Math.floor((whole % 86400) / 3600)
  const minutes = Math.floor((whole % 3600) / 60)
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m`
  return `${whole}s`
}

/** The build line: short commit, and whether the tree was dirty. */
export function buildLine(build: Health["build"]): string | undefined {
  if (!build?.sha) return undefined
  return `${shortHex(build.sha)}${build.dirty === true ? " (uncommitted changes)" : ""}`
}

/** The schema line: what the code knows against what the database is at. */
export function schemaLine(schema: Health["schema"]): string | undefined {
  if (!schema || (schema.build_knows == null && schema.database_at == null)) return undefined
  const known = schema.build_knows ?? "?"
  const at = schema.database_at ?? "?"
  return schema.agrees ? `version ${at}` : `code knows ${known}, database is at ${at}`
}

/**
 * `/health` answers 503 WITH its whole readout when one of its own checks
 * fails (app/main.py, `status: "not_ready"` and `checks[]`). The harness
 * client throws on any non-2xx but keeps the parsed body on
 * `HarnessError.body`, so the page shows that readout - which checks failed,
 * in the engine's words - rather than a sentence standing in for it.
 * Undefined for anything else, including a 503 with no readable body.
 */
export function notReadyHealth(failure: unknown): Health | undefined {
  const record = failure as { status?: unknown; body?: unknown } | null
  if (record?.status !== 503) return undefined
  const body = record.body
  return body && typeof body === "object" && !Array.isArray(body) ? (body as Health) : undefined
}

/** The checks a readout says failed. */
export function failedChecks(health: Health | undefined): NonNullable<Health["checks"]> {
  return (health?.checks ?? []).filter((check) => check && check.ok === false)
}

/**
 * The sentence for a `/health` that could not be read as a readout: a 503
 * whose body did not parse, a 409 (something else on the port), or the
 * request's own error.
 */
export function healthFailure(status: number | undefined, fallback: string): string {
  if (status === 503) return "The engine answered, but says it is not ready: one of its own health checks failed."
  if (status === 409) return "Something answered on the engine's port, but it is not the engine this window expected."
  return fallback
}

/** What `restart_engine` reports. Either flag means an engine is now answering. */
export type Bootstrap = { started?: boolean; already_running?: boolean; detail?: string }

export function restartOutcome(boot: Bootstrap | null | undefined): { ok: true } | { ok: false; why: string } {
  if (boot && (boot.started || boot.already_running)) return { ok: true }
  return { ok: false, why: boot?.detail || "The app could not restart the engine." }
}

/**
 * Settings > About's version: this window's (`platform.version`, set in
 * web/src/entry.tsx) and the engine's (`GET /oc/api/info`, the FastAPI app's
 * own version). One number when they agree; both, named, when they do not -
 * a window and an engine from different releases is worth seeing.
 */
export function versionLine(app: string | undefined, engine: string | undefined): string | undefined {
  if (app && engine && app !== engine) return `${app} (engine ${engine})`
  return app || engine || undefined
}

/** The run count `/health` read from the database (`answers_a_real_query`). */
export function runsLine(runs: number | undefined): string | undefined {
  if (typeof runs !== "number" || !Number.isFinite(runs) || runs < 0) return undefined
  return runs === 1 ? "1 run" : `${runs} runs`
}
