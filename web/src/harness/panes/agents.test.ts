import { describe, expect, it } from "vitest"
import { boardHeadline, clock, endingInWords, howLong, type SubAgent, type SubAgentRead } from "./agents-model"

function agent(over: Partial<SubAgent>): SubAgent {
  return {
    id: 1,
    thread_id: 10,
    phase: "Phase 1 - Data",
    state: "done",
    reason: "",
    detail: "",
    harvested: true,
    turns: 2,
    seconds: 30,
    steps: 3,
    done: 3,
    open: 0,
    parked: [],
    started_at: "2026-09-19 18:04:33",
    updated_at: "2026-09-19 18:09:00",
    ...over,
  }
}

function board(subagents: SubAgent[]): SubAgentRead {
  return {
    thread_id: 1,
    subagents,
    running: subagents.filter((one) => one.state === "running").length,
    running_anywhere: 0,
    at_most: 2,
  }
}

describe("the board's headline", () => {
  it("says what is out and what came back", () => {
    expect(boardHeadline(board([agent({ state: "running" }), agent({})]))).toBe("1 working, 1 back")
    expect(boardHeadline(board([agent({ state: "running" })]))).toBe("1 of 2 working")
    expect(boardHeadline(board([agent({})]))).toBe("1 phase came back")
    expect(boardHeadline(board([agent({}), agent({})]))).toBe("2 phases came back")
  })
})

describe("how one ended", () => {
  it("names failure, stop, parking and a clean finish, and nothing while running", () => {
    expect(endingInWords(agent({ state: "running" }))).toBe("")
    expect(endingInWords(agent({ state: "failed" }))).toBe("it failed")
    expect(endingInWords(agent({ state: "stopped" }))).toBe("stopped")
    expect(endingInWords(agent({ done: 0, parked: [{ step: "a", why: "b" }] }))).toBe("nothing could be done")
    expect(endingInWords(agent({ done: 2, parked: [{ step: "a", why: "b" }] }))).toBe("2 done, 1 parked")
    expect(endingInWords(agent({}))).toBe("all 3 done")
  })
})

describe("times", () => {
  it("drops a leading 0m", () => {
    expect(howLong(48)).toBe("48s")
    expect(howLong(252)).toBe("4m 12s")
    expect(howLong(null)).toBe("")
  })

  it("reads a zoneless SQLite stamp as UTC", () => {
    const zoneless = clock("2026-09-19 18:04:33", "en-GB")
    const utc = new Date("2026-09-19T18:04:33Z").toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
    expect(zoneless).toBe(utc)
    expect(clock("2026-09-19T18:04:33+00:00", "en-GB")).toBe(utc)
    expect(clock("not a time")).toBe("")
    expect(clock(null)).toBe("")
  })
})
