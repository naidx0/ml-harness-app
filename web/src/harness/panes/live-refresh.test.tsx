import type { Component } from "solid-js"
import { render } from "solid-js/web"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { PaneProps } from "../panel/panes"
import { HARNESS_CHANGED_EVENT, HARNESS_REFRESH_GATHER_MS } from "../ui"
import { claimSessionBridge } from "../bridge/events"

/**
 * THE STATS PANES MOVE WHILE A RUN IS LIVE. Each one re-reads its own route
 * when its session says the engine changed something for its thread
 * (`harness:changed`, session/refresh.ts), and not for another thread.
 */

/** How many times each path was read. Reads never answer: the count is the subject. */
const reads = new Map<string, number>()
vi.mock("../engine", () => ({
  harness: (path: string) => {
    reads.set(path, (reads.get(path) ?? 0) + 1)
    return new Promise(() => {})
  },
}))

const wait = (ms: number) => new Promise((done) => setTimeout(done, ms))
const say = (threadId: number, kind: string) =>
  window.dispatchEvent(new CustomEvent(HARNESS_CHANGED_EVENT, { detail: { threadId, kind } }))

let dispose: (() => void) | undefined
afterEach(() => {
  dispose?.()
  dispose = undefined
  reads.clear()
  document.body.innerHTML = ""
})

const CASES: { pane: string; load: () => Promise<{ default: unknown }>; path: string; kind: string }[] = [
  { pane: "Eval", load: () => import("./eval"), path: "/api/events?scope=thread:1&since=0&follow=false", kind: "eval.progress" },
  { pane: "Evidence", load: () => import("./evidence"), path: "/api/evidence?thread_id=1", kind: "tool.result" },
  { pane: "Stage", load: () => import("./stage"), path: "/api/threads/1/stage", kind: "train.started" },
  { pane: "Context", load: () => import("./context"), path: "/api/threads/1/context", kind: "step.ended" },
  { pane: "Agents", load: () => import("./agents"), path: "/api/threads/1/subagents", kind: "subagent.finished" },
  { pane: "Journey", load: () => import("./journey"), path: "/api/threads/1/journey", kind: "thread.step_done" },
]

describe("a stats pane re-reads on its own thread's changes", () => {
  for (const { pane, load, path, kind } of CASES) {
    it(pane, async () => {
      const Pane = (await load()).default as Component<PaneProps>
      const host = document.createElement("div")
      document.body.append(host)
      dispose = render(() => <Pane threadId={1} />, host)
      await wait(0)
      const first = reads.get(path) ?? 0
      expect(first).toBe(1)

      say(2, kind)
      await wait(HARNESS_REFRESH_GATHER_MS + 30)
      expect(reads.get(path)).toBe(first)

      say(1, kind)
      await wait(HARNESS_REFRESH_GATHER_MS + 30)
      expect(reads.get(path)).toBe(first + 1)
    })
  }
})

describe("the Context pane no longer polls inside a session", () => {
  it("reads once and waits for the session, where it used to re-read every four seconds", async () => {
    vi.useFakeTimers()
    const release = claimSessionBridge()
    try {
      const { default: ContextPane } = await import("./context")
      const host = document.createElement("div")
      document.body.append(host)
      dispose = render(() => <ContextPane threadId={1} />, host)
      await vi.advanceTimersByTimeAsync(12_000)
      expect(reads.get("/api/threads/1/context")).toBe(1)
      expect(reads.get("/api/threads/1/contexts")).toBe(1)
    } finally {
      release()
      vi.useRealTimers()
    }
  })

  it("keeps polling in a pop-out, where no session says anything", async () => {
    vi.useFakeTimers()
    try {
      const { default: ContextPane } = await import("./context")
      const host = document.createElement("div")
      document.body.append(host)
      dispose = render(() => <ContextPane threadId={1} />, host)
      await vi.advanceTimersByTimeAsync(8_100)
      expect(reads.get("/api/threads/1/context")).toBe(3)
    } finally {
      vi.useRealTimers()
    }
  })
})
