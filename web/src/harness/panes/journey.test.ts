import { describe, expect, it } from "vitest"
import { argumentsFor, pct, refusalOf, stamp, stateInWords, stillMissing, toolLabel, type JourneyStep, type ToolField } from "./journey-model"

const FIELDS: ToolField[] = [
  { name: "path", type: "string", description: "", required: true, enum: null },
  { name: "rows", type: "integer", description: "", required: false, enum: null },
  { name: "rate", type: "number", description: "", required: false, enum: null },
  { name: "dry", type: "boolean", description: "", required: false, enum: null },
  { name: "config", type: "object", description: "", required: false, enum: null },
]

function step(over: Partial<JourneyStep>): JourneyStep {
  return {
    ordinal: 1,
    tool: "carve_eval_set",
    why: "",
    args_hint: "",
    needs_approval: false,
    prefill: {},
    readiness: { mode: "click", missing: [] },
    state: "ahead",
    unnecessary_because: null,
    attempted: null,
    evidence: null,
    ran_at: null,
    driven_by: null,
    produced: null,
    satisfied_by: null,
    ...over,
  }
}

describe("reading a tool's answer", () => {
  it("counts anything but ok:false as ran", () => {
    expect(refusalOf({ ok: true })).toEqual({ ok: true })
    expect(refusalOf({ summary: "fine" })).toEqual({ ok: true })
    expect(refusalOf(null)).toEqual({ ok: true })
  })

  it("finds the refusal in detail, summary or error, and adds help", () => {
    expect(refusalOf({ ok: false, detail: "no folder" })).toEqual({ ok: false, detail: "no folder" })
    expect(refusalOf({ ok: false, summary: " nothing to carve " })).toEqual({ ok: false, detail: "nothing to carve" })
    expect(refusalOf({ ok: false, error: "bad_path", help: "Attach a folder." })).toEqual({
      ok: false,
      detail: "bad_path Attach a folder.",
    })
    expect(refusalOf({ ok: false, detail: "   " })).toEqual({ ok: false, detail: undefined })
  })
})

describe("the call's arguments", () => {
  it("starts from the record and types what was filled in by the schema", () => {
    const args = argumentsFor(
      { path: { value: "/data", from: "attach_context" } },
      { rows: "30", rate: "0.5", dry: "TRUE", config: '{"epochs": 2}', path: "" },
      FIELDS,
    )
    expect(args).toEqual({ path: "/data", rows: 30, rate: 0.5, dry: true, config: { epochs: 2 } })
  })

  it("lets a typed value replace the record's, and treats unknown fields as text", () => {
    expect(argumentsFor({ path: { value: "/a", from: "x" } }, { path: "/b", note: "hi" }, FIELDS)).toEqual({
      path: "/b",
      note: "hi",
    })
  })

  it("refuses a value the schema cannot take, naming the field, before anything runs", () => {
    expect(() => argumentsFor({}, { rows: "3.5" }, FIELDS)).toThrow(/rows needs a whole number/)
    expect(() => argumentsFor({}, { rate: "fast" }, FIELDS)).toThrow(/rate needs a number/)
    expect(() => argumentsFor({}, { dry: "yes" }, FIELDS)).toThrow(/dry needs true or false/)
    expect(() => argumentsFor({}, { config: "{" }, FIELDS)).toThrow(/config needs JSON/)
  })

  it("says which missing fields are still empty", () => {
    expect(stillMissing(["path", "rows"], { path: " /x ", rows: "  " })).toEqual(["rows"])
  })
})

describe("words", () => {
  it("never calls a step met elsewhere done", () => {
    expect(stateInWords(step({ state: "done_elsewhere", satisfied_by: { tool: "run_eval", facts: [] } }))).toBe(
      "met by run_eval",
    )
    expect(stateInWords(step({ state: "not_needed", unnecessary_because: "carve_rows" }))).toBe(
      "not needed here, carve_rows covered it",
    )
    expect(stateInWords(step({ state: "next" }))).toBe("you are here")
  })

  it("labels tools, stamps and scores the way the engine wrote them", () => {
    expect(toolLabel("carve_eval_set")).toBe("Carve eval set")
    expect(stamp("2026-09-19T18:04:33")).toBe("2026-09-19 18:04")
    expect(stamp(null)).toBeNull()
    expect(pct(0.126)).toBe("13%")
    expect(pct(null)).toBe("—")
  })
})
