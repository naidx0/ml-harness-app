import { describe, expect, it } from "vitest"
import {
  coerce,
  fieldKind,
  filterTools,
  groupTools,
  missingFields,
  outcomeHeading,
  outcomeOf,
  packOf,
  prettyResult,
  visibleFields,
  type ToolControl,
  type ToolField,
} from "./controls-form"
import { clearToolFocus, focusTool, focusedTool } from "./controls-focus"

const field = (name: string, type: string, extra: Partial<ToolField> = {}): ToolField => ({
  name,
  type,
  description: "",
  required: false,
  enum: null,
  ...extra,
})

const tool = (name: string, group: string, extra: Partial<ToolControl> = {}): ToolControl => ({
  name,
  label: name.replace(/_/g, " "),
  group,
  verb: `do ${name}`,
  order: 0,
  description: "",
  fields: [],
  reads: [],
  writes: [],
  needs_approval: false,
  ...extra,
})

describe("grouping tools into packs", () => {
  it("keeps the engine's order and puts each pack where its first tool is", () => {
    const groups = groupTools([tool("a", "Context"), tool("b", "Eval"), tool("c", "Context")])
    expect(groups.map((g) => g.group)).toEqual(["Context", "Eval"])
    expect(groups[0].controls.map((c) => c.name)).toEqual(["a", "c"])
  })

  it("finds the pack a focused tool lives in", () => {
    const groups = groupTools([tool("a", "Context"), tool("run_eval", "Eval")])
    expect(packOf(groups, "run_eval")).toBe("Eval")
    expect(packOf(groups, "nope")).toBeUndefined()
  })
})

describe("the search box", () => {
  const groups = groupTools([
    tool("run_eval", "Eval", { description: "Score the prompt against the set" }),
    tool("start_training", "Train", { verb: "start a training run on this machine" }),
    tool("attach_context", "Context"),
  ])

  it("returns every pack for an empty query", () => {
    expect(filterTools(groups, "   ")).toBe(groups)
  })

  it("needs every word, in any field, and reads underscores as spaces", () => {
    expect(filterTools(groups, "eval run").flatMap((g) => g.controls.map((c) => c.name))).toEqual(["run_eval"])
    expect(filterTools(groups, "TRAINING machine").flatMap((g) => g.controls.map((c) => c.name))).toEqual([
      "start_training",
    ])
  })

  it("drops a pack with no match rather than showing it empty", () => {
    expect(filterTools(groups, "attach").map((g) => g.group)).toEqual(["Context"])
    expect(filterTools(groups, "zzz")).toEqual([])
  })

  it("keeps the tool objects themselves, so a row's identity survives a search", () => {
    expect(filterTools(groups, "attach")[0].controls[0]).toBe(groups[2].controls[0])
  })
})

describe("schema fields to inputs", () => {
  it("chooses an input per field", () => {
    expect(fieldKind(field("mode", "string", { enum: ["a", "b"] }))).toBe("choice")
    expect(fieldKind(field("dry", "boolean"))).toBe("flag")
    expect(fieldKind(field("facts", "object"))).toBe("json")
    expect(fieldKind(field("rows", "array"))).toBe("json")
    expect(fieldKind(field("n", "integer"))).toBe("number")
    expect(fieldKind(field("lr", "number"))).toBe("number")
    expect(fieldKind(field("path", "string"))).toBe("text")
    expect(fieldKind(field("empty_enum", "string", { enum: [] }))).toBe("text")
  })

  it("hides thread_id when a conversation is open, because the registry overwrites it", () => {
    const control = tool("read_plan", "Plan", { fields: [field("thread_id", "integer"), field("path", "string")] })
    expect(visibleFields(control, 7).map((f) => f.name)).toEqual(["path"])
    expect(visibleFields(control, undefined).map((f) => f.name)).toEqual(["thread_id", "path"])
  })

  it("counts only blank required scalars as missing - an empty object is an answer", () => {
    const fields = [
      field("path", "string", { required: true }),
      field("facts", "object", { required: true }),
      field("dry", "boolean", { required: true }),
      field("note", "string"),
    ]
    expect(missingFields(fields, {})).toEqual(["path"])
    expect(missingFields(fields, { path: "  " })).toEqual(["path"])
    expect(missingFields(fields, { path: "/data" })).toEqual([])
  })
})

describe("coercing form strings to the schema's types", () => {
  const fields = [
    field("path", "string", { required: true }),
    field("n", "integer"),
    field("lr", "number"),
    field("dry", "boolean"),
    field("facts", "object", { required: true }),
    field("rows", "array", { required: true }),
    field("extra", "object"),
    field("mode", "string", { enum: ["fast", "slow"] }),
  ]

  it("omits blank optional fields and sends empty containers for blank required ones", () => {
    expect(coerce(fields, { path: "/data" })).toEqual({ path: "/data", facts: {}, rows: [] })
  })

  it("parses numbers, flags, JSON and choices", () => {
    expect(
      coerce(fields, {
        path: "/d",
        n: "3",
        lr: "0.001",
        dry: "true",
        facts: '{"vram_gb": 8}',
        rows: "[1, 2]",
        mode: "fast",
      }),
    ).toEqual({ path: "/d", n: 3, lr: 0.001, dry: true, facts: { vram_gb: 8 }, rows: [1, 2], mode: "fast" })
  })

  it("leaves an unticked optional flag to the engine, and sends false for a required one", () => {
    expect(coerce([field("dry", "boolean")], { dry: "" })).toEqual({})
    expect(coerce([field("dry", "boolean", { required: true })], {})).toEqual({ dry: false })
  })

  it("refuses with a sentence naming the field instead of inventing a value", () => {
    expect(() => coerce(fields, { path: "/d", n: "three" })).toThrow(/^n: "three" is not a number/)
    expect(() => coerce(fields, { path: "/d", n: "2.5" })).toThrow(/not a whole number/)
    expect(() => coerce(fields, { path: "/d", facts: "{nope" })).toThrow(/^facts: that is not valid JSON/)
    expect(() => coerce(fields, { path: "/d", rows: "{}" })).toThrow(/rows: this parameter is a list/)
    expect(() => coerce(fields, { path: "/d", facts: "[]" })).toThrow(/facts: this parameter is an object/)
  })
})

describe("reading an answer", () => {
  it("treats a tool's own ok:false as a no, and anything else as an answer", () => {
    expect(outcomeOf({ ok: false, detail: "x" })).toEqual({ kind: "ran", ok: false, result: { ok: false, detail: "x" } })
    expect(outcomeOf({ rows: 3 })).toMatchObject({ ok: true })
    expect(outcomeOf("text")).toMatchObject({ ok: true })
    expect(outcomeOf(null)).toMatchObject({ ok: true })
  })

  it("heads a refusal, a no and an answer differently", () => {
    const headings = [
      outcomeHeading({ kind: "refused", error: "428" }),
      outcomeHeading(outcomeOf({ ok: false })),
      outcomeHeading(outcomeOf({ ok: true })),
    ]
    expect(new Set(headings).size).toBe(3)
  })

  it("prints strings as they are and everything else as indented JSON", () => {
    expect(prettyResult("done")).toBe("done")
    expect(prettyResult({ a: 1 })).toBe('{\n  "a": 1\n}')
    expect(prettyResult(undefined)).toBe("(no answer)")
  })
})

describe("focusing a tool from outside the pane", () => {
  it("numbers each request so asking twice for one tool is two requests", () => {
    focusTool("run_eval")
    const first = focusedTool()
    focusTool("run_eval")
    const second = focusedTool()
    expect(first?.name).toBe("run_eval")
    expect(second?.name).toBe("run_eval")
    expect(second!.seq).toBeGreaterThan(first!.seq)
    clearToolFocus()
    expect(focusedTool()).toBeUndefined()
  })
})
