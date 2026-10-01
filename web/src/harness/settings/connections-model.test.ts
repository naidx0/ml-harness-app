import { describe, expect, it } from "vitest"
import {
  activeLabel,
  addBody,
  addReady,
  applyPreset,
  connectionSummary,
  describeTools,
  draftFrom,
  dropsProbe,
  editPatch,
  EMPTY_ADD,
  inUseModel,
  isEmptyPatch,
  keyHolders,
  modelList,
  reachable,
  type ConnectionRow,
} from "./connections-model"

const row = (extra: Partial<ConnectionRow> = {}): ConnectionRow => ({
  id: 7,
  name: "qwen",
  base_url: "http://127.0.0.1:11434",
  model: "qwen3:8b",
  adapter: "ollama",
  kind: "local",
  tool_calling: "unknown",
  is_active: 0,
  has_key: false,
  effort: "default",
  ...extra,
})

describe("tool calling is three states", () => {
  it("never collapses unknown into no", () => {
    expect(describeTools(row({ tool_calling: "yes" }))).toBe("can call tools")
    expect(describeTools(row({ tool_calling: "no" }))).toBe("cannot call tools")
    expect(describeTools(row({ tool_calling: "unknown" }))).toBe("tool calling not checked yet")
  })

  it("marks only the active row, and says whether its probe answered", () => {
    expect(activeLabel(row())).toBeUndefined()
    expect(activeLabel(row({ is_active: 1 }))).toBe("In use")
    expect(activeLabel(row({ is_active: 1, tool_calling: "yes" }))).toBe("Ready")
  })

  it("names the model by its short name, not the whole link", () => {
    const summary = connectionSummary(row({ model: "hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0" }))
    expect(summary.startsWith("MiniCPM5-1B · ")).toBe(true)
    expect(summary).not.toContain("hf.co")
  })

  it("summarises context and key only when there are some", () => {
    expect(connectionSummary(row())).not.toContain("context")
    expect(connectionSummary(row())).not.toContain("key")
    const full = connectionSummary(row({ ctx_len: 32768, has_key: true, kind: "remote" }))
    expect(full).toContain("token context")
    expect(full).toContain("key in the keychain")
    expect(full).toContain("remote")
  })
})

describe("editing a connection", () => {
  it("sends only what changed, and never an empty key", () => {
    const original = row()
    expect(isEmptyPatch(editPatch(original, draftFrom(original)))).toBe(true)
    expect(editPatch(original, { ...draftFrom(original), name: "  Qwen 8B " })).toEqual({ name: "Qwen 8B" })
    expect(editPatch(original, { ...draftFrom(original), api_key: "sk-1" })).toEqual({ api_key: "sk-1" })
    expect("api_key" in editPatch(original, { ...draftFrom(original), api_key: "" })).toBe(false)
  })

  it("a blank field keeps the stored value rather than blanking it", () => {
    const original = row()
    expect(editPatch(original, { ...draftFrom(original), model: "   ", base_url: "" })).toEqual({})
  })

  it("warns exactly when the endpoint or the model changes", () => {
    const original = row()
    expect(dropsProbe(original, { ...draftFrom(original), name: "other" })).toBe(false)
    expect(dropsProbe(original, { ...draftFrom(original), model: "llama3" })).toBe(true)
    expect(dropsProbe(original, { ...draftFrom(original), base_url: "http://x:1" })).toBe(true)
    // Whitespace alone is not a different model.
    expect(dropsProbe(original, { ...draftFrom(original), model: " qwen3:8b " })).toBe(false)
  })
})

describe("adding by hand", () => {
  const preset = { name: "LM Studio", base_url: "http://127.0.0.1:1234/v1", adapter: "openai-compatible", default_model: "m", needs_key: false }

  it("a preset fills the address and keeps a model already typed", () => {
    const filled = applyPreset({ ...EMPTY_ADD, model: "mine" }, preset)
    expect(filled).toMatchObject({ name: "LM Studio", base_url: preset.base_url, adapter: "openai-compatible", model: "mine" })
    expect(applyPreset(EMPTY_ADD, preset).model).toBe("m")
    expect(applyPreset(EMPTY_ADD, { ...preset, adapter: "ollama" }).adapter).toBe("ollama")
  })

  it("needs a name, an address and a model", () => {
    expect(addReady(EMPTY_ADD)).toBe(false)
    expect(addReady({ ...EMPTY_ADD, name: "a", base_url: "b", model: " " })).toBe(false)
    expect(addReady({ ...EMPTY_ADD, name: "a", base_url: "b", model: "c" })).toBe(true)
  })

  it("leaves the key off the body when none was typed", () => {
    expect("api_key" in addBody({ ...EMPTY_ADD, name: "a", base_url: "b", model: "c" })).toBe(false)
    expect(addBody({ ...EMPTY_ADD, name: " a ", base_url: "b", model: "c", api_key: "k" })).toMatchObject({ name: "a", api_key: "k" })
  })
})

describe("lists", () => {
  it("shortens a long model list and says when there is none", () => {
    expect(modelList([])).toBe("no models listed yet")
    expect(modelList(["a", "b"])).toBe("a, b")
    expect(modelList(["a", "b", "c", "d", "e"])).toBe("a, b, c +2 more")
  })

  it("shows only what answered, and only the rows holding a key", () => {
    const candidate = { name: "x", base_url: "u", adapter: "ollama", models: [] }
    expect(reachable([{ ...candidate, reachable: true }, { ...candidate, reachable: false }])).toHaveLength(1)
    expect(reachable(undefined)).toEqual([])
    expect(keyHolders([row({ id: 1, has_key: true }), row({ id: 2 })]).map((r) => r.id)).toEqual([1])
  })

  it("a local model is in use only when the active connection runs it", () => {
    expect(inUseModel([row({ is_active: 1 })], "qwen3:8b")).toBe(true)
    expect(inUseModel([row({ is_active: 0 })], "qwen3:8b")).toBe(false)
    expect(inUseModel(undefined, "qwen3:8b")).toBe(false)
  })
})
