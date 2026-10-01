import { describe, expect, it } from "vitest"
import { linearScale, niceDomain, niceStep, tickLabel, ticksOf } from "./chart"

describe("linearScale", () => {
  it("maps the domain ends onto the range ends, including an inverted range", () => {
    const y = linearScale([0, 2], [190, 10])
    expect(y(0)).toBe(190)
    expect(y(2)).toBe(10)
    expect(y(1)).toBe(100)
  })

  it("draws a flat series as a flat line in the middle rather than NaN", () => {
    const x = linearScale([3, 3], [0, 100])
    expect(x(3)).toBe(50)
    expect(Number.isNaN(x(7))).toBe(false)
  })
})

describe("nice numbers", () => {
  it("picks steps of 1, 2 or 5 times a power of ten", () => {
    expect(niceStep(1, 4)).toBe(0.5)
    expect(niceStep(2.3, 4)).toBe(1)
    expect(niceStep(700, 4)).toBe(200)
    expect(niceStep(0, 4)).toBe(1)
  })

  it("widens the domain outwards to whole steps, from zero when asked", () => {
    // 2.41 over about four ticks is a step of 1, so the axis tops out at 3.
    expect(niceDomain([1.93, 2.41], { zero: true })).toEqual([0, 3])
    expect(niceDomain([0.12, 0.93], { zero: true })).toEqual([0, 1])
    const [lo, hi] = niceDomain([1.93, 2.41])
    expect(lo).toBeLessThanOrEqual(1.93)
    expect(hi).toBeGreaterThanOrEqual(2.41)
  })

  it("gives a flat series a domain with width, and never a negative loss axis", () => {
    const [lo, hi] = niceDomain([0.8, 0.8], { zero: true })
    expect(hi).toBeGreaterThan(lo)
    expect(lo).toBe(0)
    expect(niceDomain([])).toEqual([0, 1])
  })

  it("puts the outermost ticks exactly on the ends of a nice domain", () => {
    const domain = niceDomain([0.12, 2.9], { zero: true })
    const ticks = ticksOf(domain)
    expect(ticks[0]).toBe(domain[0])
    expect(ticks[ticks.length - 1]).toBe(domain[1])
  })
})

describe("one scale for marks, lines and labels", () => {
  // The property the chart helper exists for: the grid line and the tick
  // label for a value are placed by the same function as a mark at that
  // value, so a mark sitting on the top grid line has the top label's value.
  it("places a mark at a tick value exactly on that tick's line", () => {
    const values = [2.4, 1.7, 1.1, 0.62]
    const domain = niceDomain(values, { zero: true })
    const y = linearScale(domain, [190, 10])
    const top = ticksOf(domain).at(-1)!
    expect(y(top)).toBe(10)
    expect(y(domain[0])).toBe(190)
    for (const value of values) {
      expect(y(value)).toBeLessThanOrEqual(190)
      expect(y(value)).toBeGreaterThanOrEqual(10)
    }
  })
})

describe("tickLabel", () => {
  it("prints as many decimals as the step needs", () => {
    expect(tickLabel(2, 1)).toBe("2")
    expect(tickLabel(0.5, 0.5)).toBe("0.5")
    expect(tickLabel(0.25, 0.05)).toBe("0.25")
    expect(tickLabel(400, 200)).toBe("400")
  })
})
