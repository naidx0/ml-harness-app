import { describe, expect, it } from "vitest"
import { lastRunLine, minutes, workingLine, type RunState } from "./plan-run"

const run = (over: Partial<RunState>): RunState => ({ thread_id: 1, state: "", ...over })

describe("the run in words", () => {
  it("counts down while working", () => {
    expect(workingLine(run({ state: "running", done: 3, open: 5 }))).toBe("Working the plan · 3 done, 5 left")
    expect(workingLine(run({ state: "running", done: 3, open: 5, parked: [{ step: "a", why: "b" }] }))).toBe(
      "Working the plan · 3 done, 5 left · 1 parked",
    )
    expect(workingLine(undefined)).toBe("Working the plan")
  })

  it("says how the last run ended, in the engine's words, and nothing while running or never run", () => {
    expect(lastRunLine(run({ state: "stopped", stop_reason: "turn_cap", seconds: 857 }))).toBe(
      "Last run: turn cap · 14m 17s",
    )
    expect(lastRunLine(run({ state: "done" }))).toBe("Last run: done")
    expect(lastRunLine(run({ state: "running" }))).toBe("")
    expect(lastRunLine(run({ state: "" }))).toBe("")
    expect(lastRunLine(undefined)).toBe("")
  })

  it("drops a leading 0m", () => {
    expect(minutes(48)).toBe("48s")
    expect(minutes(60)).toBe("1m 00s")
  })
})
