import { readdirSync, readFileSync } from "node:fs"
import { join, resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { TONE } from "./chart"

/**
 * This product's colours each carry one meaning: cobalt (their accent) is for
 * send and focus, gold is for selection. A pane is a readout, so nothing in
 * it - a selected run, a meter, a "next" label - may wear the accent.
 *
 * The subject set is DERIVED: every .tsx in panes/, plus the two cards that
 * draw meters. A pane added tomorrow is scanned without anyone listing it.
 */

// Vitest runs from web/ (happy-dom gives import.meta.url an http scheme).
const harness = resolve(process.cwd(), "src", "harness")
const panes = join(harness, "panes")
const subjects = [
  ...readdirSync(panes)
    .filter((name) => name.endsWith(".tsx") && !name.includes(".test."))
    .map((name) => join(panes, name)),
  join(harness, "cards", "bench.tsx"),
  join(harness, "cards", "eval.tsx"),
]

// A theme accent token in any of its spellings: a utility class, a CSS
// variable, or the chart's old TONE key.
const ACCENT = /\b(?:text|bg|border|fill|stroke|icon)-v2-[a-z]+-[a-z]+-accent\b|--v2-[a-z-]*-accent\b|TONE\.accent\b/

describe("panes never use the accent", () => {
  it("the scan can see an accent when there is one", () => {
    // Positive controls, so a zero below means something.
    expect(ACCENT.test('class="text-v2-text-text-accent"')).toBe(true)
    expect(ACCENT.test('class="h-full bg-v2-icon-icon-accent"')).toBe(true)
    expect(ACCENT.test("fill: var(--v2-text-text-accent)")).toBe(true)
    expect(ACCENT.test("color={TONE.accent}")).toBe(true)
    expect(ACCENT.test("the accent is for send")).toBe(false)
    expect(subjects.length).toBeGreaterThan(10)
  })

  it("no pane or meter card names an accent token", () => {
    const offenders = subjects.flatMap((path) =>
      readFileSync(path, "utf-8")
        .split("\n")
        .map((line, index) => ({ path, line: index + 1, text: line.trim() }))
        .filter((entry) => ACCENT.test(entry.text)),
    )
    expect(offenders).toEqual([])
  })

  it("the chart's own palette has no accent", () => {
    expect(Object.values(TONE).filter((value) => /accent/.test(value))).toEqual([])
  })
})
