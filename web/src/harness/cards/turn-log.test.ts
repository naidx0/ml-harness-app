import { describe, expect, it } from "vitest"
import type { ThreadEvent } from "../panes/eval-events"
import { effectsFor, planChangeFor, resultIndexOf } from "./turn-log"

const CARDS = new Set(["mark_step_done", "run_eval", "write_plan"])
const diff = (text: string) => ({ rows: [{ kind: "add", old: null, cur: 1, text }], added: 1, removed: 0, clipped: 0 })

/** One turn: tick a step, run an eval, then the effects and the end. Owned here. */
function turn(): ThreadEvent[] {
  return [
    { id: 10, kind: "turn.started", payload: {} },
    { id: 11, kind: "tool.call", payload: { id: "c1", name: "mark_step_done", arguments: { step: "a" } } },
    { id: 12, kind: "thread.step_done", payload: { step: "a", diff: diff("- [x] a") } },
    { id: 13, kind: "tool.result", payload: { id: "c1", name: "mark_step_done", ok: true, result: { ok: true, ticked: "a" } } },
    { id: 14, kind: "tool.call", payload: { id: "c2", name: "run_eval", arguments: {} } },
    { id: 15, kind: "tool.result", payload: { id: "c2", name: "run_eval", ok: true, result: { ok: true, run_id: 1 } } },
    { id: 16, kind: "turn.effects", payload: { steps_done: ["a"], can_revert: true } },
    { id: 17, kind: "stream.end", payload: { ending: "answered" } },
  ]
}

describe("resultIndexOf", () => {
  it("finds a result by the engine's call id", () => {
    expect(resultIndexOf(turn(), "c2")).toBe(5)
  })

  it("finds a result by the facade's call_<row id> of the call row or the result row", () => {
    const events = turn().map((event) =>
      event.kind.startsWith("tool.") ? { ...event, payload: { ...(event.payload as object), id: undefined } } : event,
    )
    expect(resultIndexOf(events, "call_14", "run_eval")).toBe(5)
    expect(resultIndexOf(events, "call_15")).toBe(5)
    expect(resultIndexOf(events, "call_99")).toBe(-1)
    expect(resultIndexOf(events, "")).toBe(-1)
  })
})

describe("planChangeFor", () => {
  it("reads the diff the call wrote between its call and its result", () => {
    expect(planChangeFor(turn(), "c1")?.rows[0].text).toBe("- [x] a")
  })

  it("does not borrow an earlier call's diff", () => {
    expect(planChangeFor(turn(), "c2")).toBeNull()
  })
})

describe("effectsFor", () => {
  it("gives the turn's effects to the LAST card of the turn only", () => {
    const events = turn()
    expect(effectsFor(events, "c1", CARDS).state).toBe("none")
    const last = effectsFor(events, "c2", CARDS)
    expect(last).toMatchObject({ state: "found", effectsId: 16, reverted: false })
  })

  it("does not count a later result that is drawn as their error card", () => {
    const events = turn()
    events[5] = { ...events[5], payload: { id: "c2", name: "run_eval", ok: true, result: { ok: false, error: "no_rows" } } }
    expect(effectsFor(events, "c1", CARDS).state).toBe("found")
  })

  it("does not count a later tool that has no harness card", () => {
    const events = turn()
    events[5] = { ...events[5], payload: { id: "c2", name: "profile_dataset", ok: true, result: {} } }
    expect(effectsFor(events, "c1", CARDS).state).toBe("found")
  })

  it("is pending while the turn has not ended, and none once it ended without effects", () => {
    const running = turn().slice(0, 6)
    expect(effectsFor(running, "c2", CARDS).state).toBe("pending")
    const quiet = turn().filter((event) => event.kind !== "turn.effects")
    expect(effectsFor(quiet, "c2", CARDS).state).toBe("none")
  })

  it("says the ticks were reverted when the log says so", () => {
    const events = [...turn(), { id: 18, kind: "turn.effects_reverted", payload: { effects_id: 16 } }]
    expect(effectsFor(events, "c2", CARDS)).toMatchObject({ state: "found", reverted: true })
  })

  it("draws nothing for effects the engine marked empty", () => {
    const events = turn()
    events[6] = { ...events[6], payload: { empty: true } }
    expect(effectsFor(events, "c2", CARDS).state).toBe("none")
  })
})
