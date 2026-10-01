import { describe, expect, it } from "vitest"
import { HARNESS_CHANGED_EVENT } from "../ui"
import { harnessChangeOf, rebroadcastHarnessChange } from "./refresh"

const here = { sessionID: "ses_7", threadID: 7 }

describe("which stream events the session says again to its panes", () => {
  it("an engine event for this thread, by thread id, under the engine's own kind", () => {
    expect(harnessChangeOf({ type: "harness.eval.progress", data: { threadID: 7, payload: {} } }, here)).toEqual({
      threadId: 7,
      kind: "eval.progress",
    })
    expect(harnessChangeOf({ type: "harness.subagent.started", data: { sessionID: "ses_7" } }, here)).toEqual({
      threadId: 7,
      kind: "subagent.started",
    })
  })

  it("a tool result and a closed step, renamed to the engine's words", () => {
    expect(harnessChangeOf({ type: "session.tool.success", data: { sessionID: "ses_7" } }, here)?.kind).toBe("tool.result")
    expect(harnessChangeOf({ type: "session.step.ended", data: { sessionID: "ses_7" } }, here)?.kind).toBe("step.ended")
  })

  it("nothing for another chat, even of a kind that would count", () => {
    expect(harnessChangeOf({ type: "harness.eval.finished", data: { threadID: 8, sessionID: "ses_8" } }, here)).toBeUndefined()
    expect(harnessChangeOf({ type: "session.tool.success", data: { sessionID: "ses_8" } }, here)).toBeUndefined()
    // Naming neither is nobody's.
    expect(harnessChangeOf({ type: "harness.train.log", data: {} }, here)).toBeUndefined()
  })

  it("nothing that is not a change: an instruction, their own chatter, a malformed event", () => {
    expect(harnessChangeOf({ type: "harness.ui.open", data: { threadID: 7, tab: "plan" } }, here)).toBeUndefined()
    expect(harnessChangeOf({ type: "session.text.delta", data: { sessionID: "ses_7" } }, here)).toBeUndefined()
    expect(harnessChangeOf({ type: "harness.", data: { threadID: 7 } }, here)).toBeUndefined()
    expect(harnessChangeOf(null, here)).toBeUndefined()
    expect(harnessChangeOf({ data: { threadID: 7 } }, here)).toBeUndefined()
  })

  it("nothing before the session knows its thread", () => {
    expect(harnessChangeOf({ type: "harness.eval.progress", data: { sessionID: "ses_7" } }, { sessionID: "ses_7" })).toBeUndefined()
  })

  it("is said on the target as harness:changed, once per event that counts", () => {
    const target = new EventTarget()
    const heard: unknown[] = []
    target.addEventListener(HARNESS_CHANGED_EVENT, (event) => heard.push((event as CustomEvent).detail))
    expect(rebroadcastHarnessChange({ type: "harness.run.turn", data: { threadID: 7 } }, here, target)).toBe(true)
    expect(rebroadcastHarnessChange({ type: "harness.run.turn", data: { threadID: 9 } }, here, target)).toBe(false)
    expect(heard).toEqual([{ threadId: 7, kind: "run.turn" }])
  })
})
