import { describe, expect, it, vi } from "vitest"
import { connectionFor, engineServer, ensureEngine } from "./engine"

const RUNNING = { base_url: "http://127.0.0.1:8078", token: "t0k" }
const noWait = async () => {}

describe("finding the engine", () => {
  it("uses a running engine without starting another", async () => {
    const invoke = vi.fn(async (command: string) => (command === "engine_status" ? RUNNING : null))
    await expect(ensureEngine(invoke, undefined, noWait)).resolves.toEqual({
      url: "http://127.0.0.1:8078",
      password: "t0k",
    })
    expect(invoke).not.toHaveBeenCalledWith("start_engine", undefined)
  })

  it("starts the engine when nothing answers, and says so", async () => {
    let started = false
    const invoke = vi.fn(async (command: string) => {
      if (command === "start_engine") {
        started = true
        return { started: true, already_running: false, detail: "started" }
      }
      return started ? RUNNING : { error: "no engine.json" }
    })
    const progress = vi.fn()
    await expect(ensureEngine(invoke, progress, noWait)).resolves.toMatchObject({ password: "t0k" })
    expect(progress).toHaveBeenCalledWith(expect.stringMatching(/starting/i))
  })

  it("reports the shell's own reason when starting fails", async () => {
    const invoke = vi.fn(async (command: string) =>
      command === "start_engine"
        ? { started: false, already_running: false, detail: "no usable Python; set MLH_PYTHON" }
        : { error: "no engine.json" },
    )
    await expect(ensureEngine(invoke, undefined, noWait)).rejects.toThrow("no usable Python; set MLH_PYTHON")
  })

  it("never treats an engine without a token as found", async () => {
    // engine_status strips the token of a dead engine; that is "not running".
    const invoke = vi.fn(async (command: string) =>
      command === "engine_status" ? { base_url: RUNNING.base_url } : { started: false, already_running: false, detail: "x" },
    )
    await expect(ensureEngine(invoke, undefined, noWait)).rejects.toThrow()
    expect(invoke).toHaveBeenCalledWith("start_engine")
  })
})

describe("the connection their app is given", () => {
  it("is their built-in sidecar type, pointed at the engine", () => {
    const server = engineServer(vi.fn(), connectionFor(RUNNING))
    expect(server.type).toBe("sidecar")
    expect(server.variant).toBe("base")
    expect(server.http.url).toBe("http://127.0.0.1:8078")
  })

  it("re-reads the engine on reconnect, so a restart's new token is picked up", async () => {
    const invoke = vi.fn(async () => ({ ...RUNNING, token: "fresh" }))
    const server = engineServer(invoke, connectionFor(RUNNING))
    if (server.variant !== "base") throw new Error("expected the base sidecar")
    await expect(server.reconnect!(new AbortController().signal)).resolves.toMatchObject({ password: "fresh" })
  })
})
