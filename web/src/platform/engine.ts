import type { ServerConnection } from "@/runtime/server/registry"

/**
 * The engine this window belongs to - found, or started, before anything is
 * drawn.
 *
 * THERE IS NO CONNECT SCREEN, AND THIS IS WHY. OpenCode's app, given an empty
 * server list, falls back to its "connect to a server" flow: a URL field and a
 * password. That flow is right for their product, where one interface can
 * drive servers on other machines. It is wrong for this one. The harness is one
 * package: the window and its engine ship together, and a person who opens it
 * should land in a chat without being asked where their own engine is.
 *
 * So the window asks the shell. `engine_status` reads the engine's published
 * address and token off disk; if nothing is answering, `start_engine` brings it
 * up (the first run on a machine also provisions its Python, which is why the
 * wait can be minutes and why the page says what it is doing meanwhile). The
 * result is handed to their app as a `sidecar` connection - their own type for
 * "the server bundled with this desktop app" - which their code treats as
 * built-in: it is never stored, never offered for removal, and never shown in
 * a server picker as something to configure.
 *
 * The token rides as their connection password. Their client turns that into
 * `Basic opencode:<token>`, and the engine's /oc facade accepts it.
 */

type Invoke = (command: string, args?: Record<string, unknown>) => Promise<unknown>

export interface EngineStatus {
  base_url?: string
  token?: string
  error?: string
}

interface Bootstrap {
  started: boolean
  already_running: boolean
  interpreter?: string | null
  detail: string
}

/**
 * The facade's mount point on the engine. NOT part of the URL their app is
 * given: their client builds absolute `/api/...` paths and would drop it, so
 * `facade-fetch.ts` puts it back on each request instead.
 */
export const FACADE = "/oc"

export function connectionFor(status: Required<Pick<EngineStatus, "base_url" | "token">>) {
  return {
    url: status.base_url.replace(/\/+$/, ""),
    password: status.token,
  }
}

async function readStatus(invoke: Invoke): Promise<EngineStatus> {
  return ((await invoke("engine_status").catch((error: unknown) => ({ error: String(error) }))) ?? {}) as EngineStatus
}

const ready = (status: EngineStatus): status is EngineStatus & { base_url: string; token: string } =>
  !!status.base_url && !!status.token

/**
 * Find the engine, starting it if nobody has. Resolves with its address and
 * token, or throws with the shell's own account of what went wrong.
 */
export async function ensureEngine(
  invoke: Invoke,
  progress: (message: string) => void = () => {},
  wait: (ms: number) => Promise<void> = (ms) => new Promise((done) => setTimeout(done, ms)),
) {
  const first = await readStatus(invoke)
  if (ready(first)) return connectionFor(first)

  progress("Starting the harness engine")
  const boot = (await invoke("start_engine").catch((error: unknown) => ({
    started: false,
    already_running: false,
    detail: String(error),
  }))) as Bootstrap

  // `start_engine` returns once the engine answers or its own timeout runs
  // out, but the portfile can land a moment after the port opens. A short
  // bounded re-read covers that; anything longer is a real failure and is
  // reported as one rather than waited on for ever.
  for (let attempt = 0; attempt < 20; attempt++) {
    const status = await readStatus(invoke)
    if (ready(status)) return connectionFor(status)
    await wait(250)
  }
  throw new Error(boot.detail || "The engine did not start, and the shell did not say why.")
}

/**
 * Their connection object for the engine. `reconnect` is called by their
 * client whenever the event stream drops; re-reading the shell's status there
 * is what lets the window follow an engine restart, which mints a new token.
 */
export function engineServer(
  invoke: Invoke,
  initial: { url: string; password: string },
): ServerConnection.Sidecar {
  return {
    type: "sidecar",
    variant: "base",
    displayName: "This computer",
    http: initial,
    reconnect: () => ensureEngine(invoke),
  }
}
