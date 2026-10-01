import { describe, expect, it } from "vitest"
import { entriesOf, memoryUse, overLimit } from "./memory-text"

// The engine's delimiter is a newline, the section sign and a newline. Built
// from its parts here so the expected lengths below can be read off it.
const NL = String.fromCharCode(10)
const SEP = `${NL}§${NL}`

describe("entries as the engine stores them", () => {
  it("splits on the section sign, collapses whitespace, and drops blanks", () => {
    expect(entriesOf(`  first   entry ${SEP}${SEP}second${NL}${NL}line  §`)).toEqual(["first entry", "second line"])
  })

  it("reads an empty box as no entries", () => {
    expect(entriesOf("")).toEqual([])
    expect(entriesOf(` ${NL} § `)).toEqual([])
  })
})

describe("the count beside the box", () => {
  it("counts entries plus separators, the way app/memory.py does", () => {
    // "abc" + SEP + "de" = 3 + 3 + 2
    expect(memoryUse(`abc${SEP}de`)).toBe(8)
    // The same entries written untidily count the same.
    expect(memoryUse(`  abc  §§ de ${NL}${NL}`)).toBe(8)
  })

  it("counts code points, as Python's len does, not UTF-16 units", () => {
    const rocket = String.fromCodePoint(0x1f680)
    expect(rocket.length).toBe(2)
    expect(memoryUse(rocket)).toBe(1)
  })

  it("is over only past the limit, not at it", () => {
    expect(overLimit("abcde", 5)).toBe(false)
    expect(overLimit("abcdef", 5)).toBe(true)
  })
})
