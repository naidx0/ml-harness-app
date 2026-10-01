import { createRoot, createSignal } from "solid-js"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("./engine", () => ({ harness: () => new Promise(() => {}) }))

const { HARNESS_CHANGED_EVENT, HARNESS_REFRESH_GATHER_MS, kindIn, useHarnessRefresh } = await import("./ui")

const say = (target: EventTarget, detail: unknown) =>
  target.dispatchEvent(new CustomEvent(HARNESS_CHANGED_EVENT, { detail }))

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe("useHarnessRefresh", () => {
  it("re-reads on a change for its thread, and not for another thread or a malformed detail", () => {
    const target = new EventTarget()
    const refetch = vi.fn()
    const dispose = createRoot((dispose) => {
      useHarnessRefresh(3, refetch, undefined, target)
      return dispose
    })
    say(target, { threadId: 4, kind: "eval.progress" })
    say(target, { threadId: "3", kind: "eval.progress" })
    say(target, { threadId: 3 })
    vi.advanceTimersByTime(HARNESS_REFRESH_GATHER_MS + 1)
    expect(refetch).not.toHaveBeenCalled()
    say(target, { threadId: 3, kind: "eval.progress" })
    vi.advanceTimersByTime(HARNESS_REFRESH_GATHER_MS + 1)
    expect(refetch).toHaveBeenCalledTimes(1)
    dispose()
  })

  it("gathers a burst into one re-read", () => {
    const target = new EventTarget()
    const refetch = vi.fn()
    const dispose = createRoot((dispose) => {
      useHarnessRefresh(3, refetch, undefined, target)
      return dispose
    })
    for (const kind of ["step.ended", "tool.result", "eval.finished", "thread.step_done"]) say(target, { threadId: 3, kind })
    vi.advanceTimersByTime(HARNESS_REFRESH_GATHER_MS - 1)
    expect(refetch).not.toHaveBeenCalled()
    vi.advanceTimersByTime(2)
    expect(refetch).toHaveBeenCalledTimes(1)
    // The next burst is its own read.
    say(target, { threadId: 3, kind: "tool.result" })
    vi.advanceTimersByTime(HARNESS_REFRESH_GATHER_MS + 1)
    expect(refetch).toHaveBeenCalledTimes(2)
    dispose()
  })

  it("takes only the kinds it was given", () => {
    const target = new EventTarget()
    const refetch = vi.fn()
    const dispose = createRoot((dispose) => {
      useHarnessRefresh(3, refetch, kindIn("eval", "tool.result"), target)
      return dispose
    })
    say(target, { threadId: 3, kind: "subagent.started" })
    say(target, { threadId: 3, kind: "evaluation" })
    vi.advanceTimersByTime(HARNESS_REFRESH_GATHER_MS + 1)
    expect(refetch).not.toHaveBeenCalled()
    say(target, { threadId: 3, kind: "eval.reused" })
    vi.advanceTimersByTime(HARNESS_REFRESH_GATHER_MS + 1)
    expect(refetch).toHaveBeenCalledTimes(1)
    dispose()
  })

  it("follows a thread accessor, and stops listening with its owner, pending call included", () => {
    const target = new EventTarget()
    const refetch = vi.fn()
    const [thread, setThread] = createSignal<number | undefined>(undefined)
    const dispose = createRoot((dispose) => {
      useHarnessRefresh(thread, refetch, undefined, target)
      return dispose
    })
    say(target, { threadId: 5, kind: "run.turn" })
    vi.advanceTimersByTime(HARNESS_REFRESH_GATHER_MS + 1)
    expect(refetch).not.toHaveBeenCalled()
    setThread(5)
    say(target, { threadId: 5, kind: "run.turn" })
    dispose()
    vi.advanceTimersByTime(HARNESS_REFRESH_GATHER_MS + 1)
    say(target, { threadId: 5, kind: "run.turn" })
    vi.advanceTimersByTime(HARNESS_REFRESH_GATHER_MS + 1)
    expect(refetch).not.toHaveBeenCalled()
  })
})
