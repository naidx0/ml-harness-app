import { readdirSync, readFileSync } from "node:fs"
import { join, resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { cardKindOf, HARNESS_CARD_TOOLS, HARNESS_CARD_TOOL_NAMES, kindsAccepting, STAGED, type CardKind } from "./kinds"
import { SPECIMENS } from "./test-specimens"

describe("cardKindOf", () => {
  for (const [kind, specimen] of Object.entries(SPECIMENS)) {
    it(`reads a ${kind} result as ${kind} and as nothing else`, () => {
      expect(cardKindOf(specimen)).toBe(kind)
    })
  }

  it("draws no card for a result no reader recognises", () => {
    expect(cardKindOf({ ok: true, rows: 12 })).toBeNull()
    expect(cardKindOf("plain text")).toBeNull()
    expect(cardKindOf(undefined)).toBeNull()
  })

  it("reads a refusal as no card, because their error card draws it", () => {
    expect(cardKindOf({ ok: false, error: "no_honest_build", detail: "nothing to build" })).toBeNull()
    expect(cardKindOf({ ok: false, error: "no_shared_rows", run_id: 5, against: 4, p_value: 1 })).toBeNull()
    expect(cardKindOf({ ok: false, nothing_was_written: true, error: "no_rows", eval_path: "a", train_path: "b", into: "c" })).toBeNull()
  })

  it("keeps the readers disjoint: no specimen is accepted by two of them", () => {
    // A property of the SET of readers, so it is asked of every pair at once.
    for (const [kind, specimen] of Object.entries(SPECIMENS)) expect(kindsAccepting(specimen)).toEqual([kind])
  })

  it("draws a prompt attempt that also carries a run's fields as the prompt card", () => {
    const attempt = { ...(SPECIMENS.prompt as object), run_id: 6, planned: 10, graded: 10 }
    expect(kindsAccepting(attempt)).toEqual(["prompt", "eval"])
    expect(cardKindOf(attempt)).toBe("prompt")
  })
})

describe("the tools that get a card", () => {
  // Vitest runs from web/ (happy-dom gives import.meta.url an http scheme).
  const toolsDir = resolve(process.cwd(), "..", "app", "tools")
  // Derived from the engine's own declarations, not hand-listed: `@tool("x"`,
  // a name on the next line, and `name="x"` are the spellings in app/tools.
  const declared = new Set<string>()
  for (const file of readdirSync(toolsDir).filter((name) => name.endsWith(".py"))) {
    const source = readFileSync(join(toolsDir, file), "utf-8")
    for (const match of source.matchAll(/@tool\(\s*(?:name=)?"([a-z_]+)"/g)) declared.add(match[1])
  }

  it("found the engine's tool declarations at all", () => {
    expect(declared.size).toBeGreaterThan(50)
  })

  for (const name of HARNESS_CARD_TOOL_NAMES) {
    it(`${name} is a tool the engine declares`, () => {
      expect(declared.has(name)).toBe(true)
    })
  }

  it("names every card kind at least once, so no card is unreachable", () => {
    const reachable = new Set(Object.values(HARNESS_CARD_TOOLS).flat())
    for (const kind of Object.keys(SPECIMENS)) expect(reachable.has(kind as CardKind)).toBe(true)
  })

  it("offers the Stage only for what the Stage draws", () => {
    expect([...STAGED].sort()).toEqual(["carve", "compare", "diagnosis", "eval", "prompt", "recall", "sandbox"])
  })
})
