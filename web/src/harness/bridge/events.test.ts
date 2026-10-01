import { describe, expect, it } from "vitest"
import {
  claimSessionBridge,
  COMPOSE_EVENT,
  onBridge,
  OPEN_PANE_EVENT,
  OPEN_THREAD_EVENT,
  paneRequestIsOurs,
  readDetail,
  requestCompose,
  requestOpenThread,
  requestPane,
  sessionBridgePresent,
  uiOpenTab,
} from "./events"

describe("the bridge's event names", () => {
  it("keeps the open-pane name the result cards already dispatch", () => {
    // cards/frame.tsx dispatches this literal; the mount must still hear it.
    expect(OPEN_PANE_EVENT).toBe("harness:open-pane")
    expect(COMPOSE_EVENT).toBe("harness:compose")
    expect(OPEN_THREAD_EVENT).toBe("harness:open-thread")
  })
})

describe("a request nobody answers", () => {
  it("reads as not taken, which is how a pop-out knows to fall back", () => {
    const target = new EventTarget()
    expect(requestCompose("About the step", target)).toBe(false)
    expect(requestOpenThread(7, target)).toBe(false)
    expect(requestPane("plan", undefined, target)).toBe(false)
  })
})

describe("a request a session answers", () => {
  it("delivers the detail and reads as taken", () => {
    const target = new EventTarget()
    const heard: unknown[] = []
    const stop = onBridge(COMPOSE_EVENT, (detail) => void heard.push(detail), target)
    expect(requestCompose('About the step "count the rows": ', target)).toBe(true)
    expect(heard).toEqual([{ text: 'About the step "count the rows": ' }])
    stop()
    expect(requestCompose("again", target)).toBe(false)
    expect(heard).toHaveLength(1)
  })

  it("reads as not taken when the handler declines", () => {
    const target = new EventTarget()
    onBridge(OPEN_PANE_EVENT, (detail) => (detail.pane === "plan" ? undefined : false), target)
    expect(requestPane("plan", undefined, target)).toBe(true)
    expect(requestPane("nowhere", undefined, target)).toBe(false)
  })

  it("only hears its own type", () => {
    const target = new EventTarget()
    const threads: number[] = []
    onBridge(OPEN_THREAD_EVENT, ({ threadId }) => void threads.push(threadId), target)
    expect(requestCompose("words", target)).toBe(false)
    expect(requestOpenThread(12, target)).toBe(true)
    expect(threads).toEqual([12])
  })
})

describe("a malformed detail", () => {
  it("is refused before any handler sees it", () => {
    expect(readDetail(COMPOSE_EVENT, { text: "   " })).toBeUndefined()
    expect(readDetail(COMPOSE_EVENT, { text: 3 })).toBeUndefined()
    expect(readDetail(COMPOSE_EVENT, null)).toBeUndefined()
    expect(readDetail(OPEN_THREAD_EVENT, { threadId: "7" })).toBeUndefined()
    expect(readDetail(OPEN_THREAD_EVENT, { threadId: 0 })).toBeUndefined()
    expect(readDetail(OPEN_THREAD_EVENT, { threadId: 1.5 })).toBeUndefined()
    expect(readDetail(OPEN_PANE_EVENT, { pane: "" })).toBeUndefined()
    expect(readDetail(OPEN_THREAD_EVENT, { threadId: 7 })).toEqual({ threadId: 7 })
  })

  it("from a foreign dispatch is not taken", () => {
    const target = new EventTarget()
    let called = false
    onBridge(OPEN_THREAD_EVENT, () => void (called = true), target)
    const event = new CustomEvent(OPEN_THREAD_EVENT, { detail: { threadId: "7" }, cancelable: true })
    expect(target.dispatchEvent(event)).toBe(true)
    expect(called).toBe(false)
  })
})

describe("whether a session is answering in this window", () => {
  it("is true while one is claimed, and a release counts once", () => {
    expect(sessionBridgePresent()).toBe(false)
    const first = claimSessionBridge()
    const second = claimSessionBridge()
    expect(sessionBridgePresent()).toBe(true)
    first()
    first()
    expect(sessionBridgePresent()).toBe(true)
    second()
    expect(sessionBridgePresent()).toBe(false)
  })
})

describe("an engine ui.open on the shared stream", () => {
  // The facade's stream carries every thread's events to every window.
  const here = { sessionID: "ses_here", threadID: 7 }
  const event = (data: Record<string, unknown>) => ({ type: "harness.ui.open", data })

  it("opens the pane when it names this session", () => {
    expect(uiOpenTab(event({ tab: "plan", sessionID: "ses_here", threadID: 7 }), here)).toBe("plan")
  })

  it("opens the pane when it names this session's thread", () => {
    expect(uiOpenTab(event({ tab: "plan", threadID: 7 }), here)).toBe("plan")
  })

  it("is ignored when it is for another session", () => {
    expect(uiOpenTab(event({ tab: "plan", sessionID: "ses_other", threadID: 8 }), here)).toBeUndefined()
  })

  it("is ignored when it names no session at all", () => {
    expect(uiOpenTab(event({ tab: "plan" }), here)).toBeUndefined()
    expect(uiOpenTab(event({ tab: "plan" }), {})).toBeUndefined()
  })

  it("is not some other event type", () => {
    expect(uiOpenTab({ type: "harness.stage.started", data: { tab: "stage", sessionID: "ses_here" } }, here)).toBeUndefined()
  })
})

describe("an open-pane request from a card", () => {
  it("carries its thread", () => {
    const target = new EventTarget()
    const heard: unknown[] = []
    onBridge(OPEN_PANE_EVENT, (detail) => void heard.push(detail), target)
    requestPane("stage", 12, target)
    expect(heard).toEqual([{ pane: "stage", threadId: 12 }])
  })

  it("is declined by a session on another thread, so the card falls back", () => {
    const target = new EventTarget()
    const sessionThread = 7
    onBridge(OPEN_PANE_EVENT, (detail) => (paneRequestIsOurs(detail, sessionThread) ? undefined : false), target)
    expect(requestPane("stage", 12, target)).toBe(false)
    expect(requestPane("stage", 7, target)).toBe(true)
    expect(requestPane("stage", undefined, target)).toBe(true)
  })

  it("refuses a malformed thread rather than reading it as none", () => {
    expect(readDetail(OPEN_PANE_EVENT, { pane: "stage", threadId: "7" })).toBeUndefined()
    expect(readDetail(OPEN_PANE_EVENT, { pane: "stage", threadId: 7 })).toEqual({ pane: "stage", threadId: 7 })
  })
})
