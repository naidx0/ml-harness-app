import { describe, expect, it } from "vitest"
import {
  BANDS,
  FREE_COLOUR,
  compactNote,
  segments,
  share,
  thousands,
  turnBars,
  withheldSentence,
  type ContextTurn,
} from "./context-read"

const turn = (total: number, parts: [string, number][] = [], id = 1): ContextTurn => ({
  event_id: id,
  system: 0,
  tools: 0,
  history: 0,
  total,
  messages: 1,
  tool_count: 0,
  window: null,
  mode: "build",
  parts: parts.map(([key, tokens]) => ({ key, label: key, why: "", tokens, count: 1 })),
})

describe("shares and thousands", () => {
  it("gives one decimal under ten percent and none above", () => {
    expect(share(636, 10000)).toBe("6.4%")
    expect(share(6360, 10000)).toBe("64%")
  })

  it("says nothing it cannot know", () => {
    expect(share(10, null)).toBe("—")
    expect(share(10, 0)).toBe("—")
    expect(thousands(undefined)).toBe("—")
    expect(thousands(null)).toBe("—")
  })
})

describe("the bar", () => {
  it("measures parts against the window and ends with the free space", () => {
    const { parts, free } = segments(turn(3000, [["system", 2000], ["history", 1000]]), 10000)
    expect(parts.map((p) => p.width)).toEqual([20, 10])
    expect(free).toMatchObject({ tokens: 7000, width: 70, colour: FREE_COLOUR })
  })

  it("colours biggest first, in band order, and wraps after eight", () => {
    const many = Array.from({ length: 9 }, (_, i) => [`p${i}`, 10] as [string, number])
    const { parts } = segments(turn(90, many), 1000)
    expect(parts[0].colour).toBe(BANDS[0])
    expect(parts[8].colour).toBe(BANDS[0])
    expect(new Set(parts.slice(0, 8).map((p) => p.colour)).size).toBe(8)
  })

  it("fills the bar between the parts when there is no window, with no free segment", () => {
    const { parts, free } = segments(turn(400, [["a", 300], ["b", 100]]), null)
    expect(parts.map((p) => p.width)).toEqual([75, 25])
    expect(free).toBeUndefined()
  })

  it("never draws past the end of the bar, or a negative free space, when a turn is over the window", () => {
    const { parts, free } = segments(turn(1500, [["a", 1500]]), 1000)
    expect(parts[0].width).toBe(100)
    expect(free).toMatchObject({ tokens: 0, width: 0 })
  })

  it("draws nothing for a turn recorded before parts existed", () => {
    const old = { ...turn(500), parts: undefined }
    expect(segments(old, 1000).parts).toEqual([])
  })
})

describe("the per-turn chart", () => {
  it("scales against the window and marks turns over it", () => {
    const bars = turnBars([turn(250, [], 1), turn(1200, [], 2)], 1000)
    expect(bars.map((b) => b.height)).toEqual([25, 100])
    expect(bars.map((b) => b.over)).toEqual([false, true])
  })

  it("scales to the largest turn without a window, and keeps a tiny turn visible", () => {
    const bars = turnBars([turn(1, [], 1), turn(500, [], 2), turn(1000, [], 3)], null)
    expect(bars.map((b) => b.height)).toEqual([4, 50, 100])
    expect(bars.every((b) => !b.over)).toBe(true)
  })

  it("survives an empty list and all-zero turns", () => {
    expect(turnBars([], null)).toEqual([])
    expect(turnBars([turn(0)], null)[0].height).toBe(4)
  })
})

describe("sentences", () => {
  it("names withheld tools in the right number, and says nothing for none", () => {
    expect(withheldSentence(0)).toBeUndefined()
    expect(withheldSentence(1)).toMatch(/^1 more tool was active .* without its parameters\. The model can still call it,/)
    expect(withheldSentence(3)).toMatch(/^3 more tools were active .* without their parameters\. The model can still call them,/)
  })

  it("reports a compaction, and a refusal as the engine's own words", () => {
    expect(compactNote({ ok: true, messages_summarised: 12, tokens_before: 9000, tokens_after: 1500 })).toBe(
      `Compacted 12 messages, ${(9000).toLocaleString()} to ${(1500).toLocaleString()} tokens.`,
    )
    expect(compactNote({ ok: false, detail: "nothing to compact" })).toBe("nothing to compact")
    expect(compactNote({ ok: false })).toBe("Nothing to compact.")
  })
})
