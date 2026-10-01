import { readdirSync, readFileSync } from "node:fs"
import { join, resolve } from "node:path"
import { describe, expect, it } from "vitest"
import {
  blocksOf,
  countSteps,
  everyStepSettled,
  joinPhases,
  planTitle,
  splitIntoPhases,
  stepsOf,
  tickedLine,
  toggleStepAt,
  unparkAt,
  withPhaseBody,
} from "./plan-model"

const PLAN = [
  "# Train on my files",
  "",
  "Why: the model misses our jargon.",
  "",
  "## Phase 1 - Data",
  "- [x] carve the eval set",
  "- [ ] count the rows",
  "",
  "## Phase 2 — Baseline",
  "- [!] score the baseline — parked: no model connected",
  "- [ ] count the rows",
  "```",
  "## not a phase",
  "- [ ] not a step",
  "```",
].join("\n")

describe("phases", () => {
  it("round-trips any document, including adjacent headings and CRLF", () => {
    for (const text of [PLAN, "## A\n## B", "", "\n\n", "## A\r\n- [ ] x\r\n", "plain"]) {
      expect(joinPhases(splitIntoPhases(text))).toBe(text)
    }
  })

  it("cuts at ## outside fences, and reads Phase N with any dash", () => {
    const phases = splitIntoPhases(PLAN)
    expect(phases.map((phase) => [phase.number, phase.label])).toEqual([
      [null, "Before the first phase"],
      [1, "Data"],
      [2, "Baseline"],
    ])
  })

  it("replaces one phase body and leaves the rest byte for byte", () => {
    const next = withPhaseBody(PLAN, 1, "- [ ] one step")
    expect(next).toContain("## Phase 1 - Data\n- [ ] one step\n## Phase 2")
    expect(next.startsWith("# Train on my files\n\nWhy:")).toBe(true)
    expect(withPhaseBody(PLAN, 9, "x")).toBe(PLAN)
  })
})

describe("steps", () => {
  it("finds open, done and parked steps by line, ignoring fenced ones", () => {
    const steps = stepsOf(PLAN)
    expect(steps.map((step) => [step.line, step.state, step.text])).toEqual([
      [5, "done", "carve the eval set"],
      [6, "open", "count the rows"],
      [9, "parked", "score the baseline"],
      [10, "open", "count the rows"],
    ])
    expect(steps[2].why).toBe("no model connected")
  })

  it("counts them and says N of M steps ticked", () => {
    const counts = countSteps(PLAN)
    expect(counts).toEqual({ open: 2, done: 1, parked: 1, total: 4 })
    expect(tickedLine(counts)).toBe("1 of 4 steps ticked · 1 parked")
    expect(tickedLine(countSteps("- [x] a\n- [X] b"))).toBe("2 of 2 steps ticked · every step done")
    expect(tickedLine(countSteps("no steps"))).toBe("")
  })

  it("settles only when nothing is open and something was done", () => {
    expect(everyStepSettled(countSteps(PLAN))).toBe(false)
    expect(everyStepSettled(countSteps("- [x] a\n- [!] b"))).toBe(true)
    expect(everyStepSettled(countSteps("- [!] b"))).toBe(false)
    expect(everyStepSettled(countSteps(""))).toBe(false)
  })

  it("ticks the addressed line only, even when two steps share their words", () => {
    const ticked = toggleStepAt(PLAN, 10)
    expect(stepsOf(ticked).map((step) => step.state)).toEqual(["done", "open", "parked", "done"])
    expect(toggleStepAt(ticked, 10)).toBe(PLAN)
  })

  it("never ticks a parked step, a fenced line or a non-step", () => {
    expect(toggleStepAt(PLAN, 9)).toBe(PLAN)
    expect(toggleStepAt(PLAN, 0)).toBe(PLAN)
    expect(toggleStepAt(PLAN, 99)).toBe(PLAN)
  })

  it("keeps a carriage return on the line it edits", () => {
    expect(toggleStepAt("- [ ] a\r\n- [ ] b\r\n", 1)).toBe("- [ ] a\r\n- [x] b\r\n")
  })

  it("unparks back to open and drops the reason", () => {
    const next = unparkAt(PLAN, 9)
    expect(next.split("\n")[9]).toBe("- [ ] score the baseline")
    expect(unparkAt(PLAN, 6)).toBe(PLAN)
  })
})

describe("read view blocks", () => {
  it("draws the title, phases with the editor's index, steps and code", () => {
    const blocks = blocksOf(PLAN)
    expect(blocks[0]).toEqual({ kind: "title", text: "Train on my files" })
    const phases = blocks.filter((block) => block.kind === "phase")
    expect(phases).toEqual([
      { kind: "phase", text: "Phase 1 - Data", index: 1 },
      { kind: "phase", text: "Phase 2 — Baseline", index: 2 },
    ])
    expect(blocks.filter((block) => block.kind === "step")).toHaveLength(4)
    expect(blocks.at(-1)).toEqual({ kind: "code", text: "## not a phase\n- [ ] not a step" })
  })

  it("numbers the first phase 0 when the plan opens on a heading", () => {
    const blocks = blocksOf("## Phase 1 - A\n- [ ] x\n## B")
    expect(blocks.filter((block) => block.kind === "phase").map((block) => (block as { index: number }).index)).toEqual([
      0, 1,
    ])
    expect(splitIntoPhases("## Phase 1 - A\n- [ ] x\n## B")).toHaveLength(2)
  })

  it("reads the title", () => {
    expect(planTitle(PLAN)).toBe("Train on my files")
    expect(planTitle("## only a phase")).toBe("")
  })
})

describe("the plan's type sits on whole pixels", () => {
  // The owner, 2026-09-22: "our plan text looks a little blurry and weird".
  // Their 13px classes carry a 150% line height - 19.5px - so a stack of rows
  // put text on half pixels (measured: y = 404.5), and grayscale antialiasing
  // smears a glyph that starts mid-pixel. Every string in the pane that names
  // one of their type utilities also forces a whole-pixel line height over
  // it; and the copied-over 13px text and synthetic weights are gone.
  const here = resolve(process.cwd(), "src", "harness", "panes")
  const sources = readdirSync(here)
    .filter((name) => /^plan.*\.tsx$/.test(name))
    .map((name) => ({ name, text: readFileSync(join(here, name), "utf-8") }))

  const TYPE = /\btext-1[246]-(?:regular|medium|mono)\b/
  const WHOLE = /(?:^|\s)leading-(?:4|5|6)!?(?=\s|$)/
  function loose(source: string) {
    return [...source.matchAll(/["`]([^"`\n]*)["`]/g)]
      .map((match) => match[1]!)
      .filter((klass) => TYPE.test(klass) && !WHOLE.test(klass))
  }

  it("the scan sees a planted loose class, and passes a pinned one", () => {
    expect(loose('<p class="px-4 text-12-regular text-v2-text-text-base">')).toEqual([
      "px-4 text-12-regular text-v2-text-text-base",
    ])
    expect(loose('<p class="px-4 text-12-regular leading-5! text-v2-text-text-base">')).toEqual([])
    expect(sources.map((source) => source.name)).toEqual(expect.arrayContaining(["plan.tsx", "plan-views.tsx"]))
  })

  it("every type class in the plan pane carries a whole-pixel line height", () => {
    expect(sources.flatMap((source) => loose(source.text).map((klass) => `${source.name}: ${klass}`))).toEqual([])
  })

  it("no copied-over 13px text, no synthetic weight, no undefined border token", () => {
    for (const source of sources) {
      expect(source.text).not.toMatch(/text-\[13px\]|\[font-weight:|border-v2-border-border-weak/)
    }
  })
})
