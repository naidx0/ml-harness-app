import { describe, expect, it } from "vitest"
import { timelinePresets, type TimelineDetail } from "@opencode/session-ui/timeline/detail"
import { HARNESS_DEFAULT_SETS, withLiveThinking } from "./root"

/**
 * THE LIVE THINKING IS SHOWN BY DEFAULT (root.tsx, v3). Their default
 * timeline is Compact, which groups thinking: while it streams it sits inside
 * a collapsed "Used ..." row and their live Thinking row is never built
 * (session-ui timeline/projection.ts, `thinking` needs placement "separate").
 * So the sparkle and the capped live body the owner asked for were two clicks
 * deep. v3 moves thinking to its own row, collapsed, and touches nothing else.
 */

const preset = (id: string) => structuredClone(timelinePresets.find((p) => p.id === id)!.value) as TimelineDetail

describe("the live-thinking default", () => {
  it("takes their Compact default to thinking on its own row, collapsed, and changes nothing else", () => {
    const before = preset("compact")
    const after = withLiveThinking(before)
    expect(after.thinking).toEqual({ placement: "separate", details: "collapsed" })
    expect({ ...after, thinking: undefined }).toEqual({ ...before, thinking: undefined })
  })

  it("leaves a choice someone made: hidden stays hidden, separate keeps its details", () => {
    for (const id of ["quiet", "text-only", "everything"]) {
      const before = preset(id)
      expect(withLiveThinking(before), id).toEqual(before)
    }
  })

  it("is a new set, applied through their setter once, like v1 and v2", () => {
    const set = HARNESS_DEFAULT_SETS.find((one) => one.key === "harness.defaults.v3")
    expect(set).toBeDefined()
    const written: TimelineDetail[] = []
    const fake = {
      general: {
        timelineDetail: () => preset("compact"),
        setTimelineDetail: (value: TimelineDetail) => written.push(value),
      },
    }
    set!.apply(fake as never)
    expect(written.map((value) => value.thinking)).toEqual([{ placement: "separate", details: "collapsed" }])
    // The keys are distinct, or a later set would be skipped as already taken.
    const keys = HARNESS_DEFAULT_SETS.map((one) => one.key)
    expect(new Set(keys).size).toBe(keys.length)
  })
})
