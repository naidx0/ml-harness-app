import { render } from "solid-js/web"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const showToast = vi.fn((_input: unknown) => 1)
vi.mock("@/shell/notifications/toast", () => ({
  showToast: (input: unknown) => showToast(input),
  dismissToast: () => undefined,
}))
// Inside the desktop shell, where "Start the engine" would be offered for a gone engine.
vi.mock("../../platform/tauri", () => ({ tauriInvoke: () => async () => undefined }))
const harness = vi.fn<(path: string) => Promise<unknown>>()
vi.mock("../engine", () => ({ harness: (path: string) => harness(path) }))

const { EngineNotice, notReadyLine } = await import("./notice")

const NOT_READY = {
  status: "not_ready",
  engine: { pid: 10, engine_id: "a" },
  checks: [
    { name: "process", ok: true, detail: "pid 10" },
    { name: "schema_agrees", ok: false, detail: "code knows 41, database is at 40" },
  ],
}

let dispose: (() => void) | undefined
beforeEach(() => {
  showToast.mockClear()
  harness.mockReset()
})
afterEach(() => {
  dispose?.()
  dispose = undefined
  document.body.innerHTML = ""
})

const tick = () => new Promise((resolve) => setTimeout(resolve, 0))

type Toast = { title: string; description: string; actions: { label: string }[] }

async function noticeFor(answer: () => Promise<unknown>) {
  harness.mockImplementation(answer)
  const host = document.createElement("div")
  document.body.append(host)
  dispose = render(() => <EngineNotice />, host)
  await tick()
  await tick()
  return showToast.mock.calls.map(([input]) => input as Toast)
}

describe("the engine notice", () => {
  it("says 'not ready' for a 503, names the failing check, and never offers to start a running engine", async () => {
    const toasts = await noticeFor(() =>
      Promise.reject(Object.assign(new Error("503 from /health"), { status: 503, body: NOT_READY })),
    )
    expect(toasts).toHaveLength(1)
    expect(toasts[0]!.title).toMatch(/not ready/i)
    expect(toasts[0]!.description).toContain("schema_agrees: code knows 41, database is at 40")
    expect(toasts[0]!.actions.map((action) => action.label)).toEqual(["Reload"])
  })

  it("still says 'not answering', with Start the engine, when nothing answers", async () => {
    const toasts = await noticeFor(() => Promise.reject(new TypeError("Failed to fetch")))
    expect(toasts).toHaveLength(1)
    expect(toasts[0]!.title).toMatch(/not answering/i)
    expect(toasts[0]!.actions.map((action) => action.label)).toEqual(["Start the engine"])
  })

  it("says nothing while the engine is ready", async () => {
    expect(await noticeFor(async () => ({ ...NOT_READY, status: "ok", checks: [] }))).toEqual([])
  })

  it("falls back to a general line when the 503 names no failing check", () => {
    expect(notReadyLine({ status: 503, health: {} })).toMatch(/health checks failed/)
  })
})
