import { describe, expect, it } from "vitest"
import { sessionUsage, type UsageMessage, type UsageTokens } from "./context-usage"

const zero: UsageTokens = { input: 0, output: 0, reasoning: 0, cache: { read: 0, write: 0 } }
const used = (input: number, output: number, reasoning = 0, read = 0, write = 0): UsageTokens => ({
  input,
  output,
  reasoning,
  cache: { read, write },
})
const user = (created: number): UsageMessage => ({ type: "user", time: { created } })
const reply = (created: number, tokens: UsageTokens = zero, model = { providerID: "local-ollama", id: "qwen3:8b" }) => ({
  type: "assistant",
  time: { created },
  tokens,
  model,
})
const catalogue = (providerID: string, modelID: string) =>
  providerID === "local-ollama" && modelID === "qwen3:8b"
    ? { providerName: "Ollama", modelName: "Qwen3 8B", limit: 40000 }
    : undefined

describe("their session readouts, merged", () => {
  it("counts messages by kind and names the model the way their catalogue does", () => {
    const usage = sessionUsage([user(1), reply(2), user(3), reply(4)], { title: "Tickets", time: { created: 1 } }, catalogue)
    expect(usage.counts).toEqual({ all: 4, user: 2, assistant: 2 })
    expect(usage.provider).toBe("Ollama")
    expect(usage.model).toBe("Qwen3 8B")
    expect(usage.limit).toBe(40000)
    expect(usage.title).toBe("Tickets")
    expect(usage.created).toBe(1)
    expect(usage.lastReply).toBe(4)
  })

  it("the facade's zero usage and zero cost are not reported as measured zeros", () => {
    // What app/facade/translate.py sends on every reply today.
    const usage = sessionUsage([user(1), reply(2, zero)], { cost: 0 }, catalogue)
    expect(usage.tokens).toBeUndefined()
    expect(usage.cost).toBeUndefined()
  })

  it("reported usage is shown with their total and their whole-percent share", () => {
    const usage = sessionUsage([user(1), reply(2, used(9000, 800, 100, 50, 50))], { cost: 0.0123 }, catalogue)
    expect(usage.tokens).toEqual({
      total: 10000,
      input: 9000,
      output: 800,
      reasoning: 100,
      cacheRead: 50,
      cacheWrite: 50,
      usage: 25,
    })
    expect(usage.cost).toBe(0.0123)
  })

  it("takes the last reply that reported usage, skipping later zero ones", () => {
    const usage = sessionUsage([reply(1, used(100, 20)), reply(2, zero)], undefined, catalogue)
    expect(usage.tokens?.total).toBe(120)
    expect(usage.lastReply).toBe(2)
  })

  it("no share without a declared window, and the raw ids when the catalogue does not know the model", () => {
    const other = { providerID: "openrouter", id: "some/model" }
    const usage = sessionUsage([reply(1, used(100, 20), other)], undefined, catalogue)
    expect(usage.tokens?.usage).toBeNull()
    expect(usage.limit).toBeUndefined()
    expect(usage.provider).toBe("openrouter")
    expect(usage.model).toBe("some/model")
  })

  it("an empty session says nothing it does not know", () => {
    const usage = sessionUsage([], undefined, catalogue)
    expect(usage).toMatchObject({
      counts: { all: 0, user: 0, assistant: 0 },
      provider: undefined,
      model: undefined,
      limit: undefined,
      tokens: undefined,
      cost: undefined,
      created: undefined,
      lastReply: undefined,
      systemPrompt: undefined,
    })
  })

  it("keeps the last non-blank system prompt, trimmed", () => {
    const usage = sessionUsage(
      [{ type: "system", text: "old" }, user(1), { type: "system", text: "  current rules \n" }],
      undefined,
      catalogue,
    )
    expect(usage.systemPrompt).toBe("current rules")
  })
})
