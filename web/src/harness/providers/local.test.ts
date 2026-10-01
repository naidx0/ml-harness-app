import { describe, expect, it, vi } from "vitest"

vi.mock("../engine", () => ({ harness: () => new Promise(() => {}) }))

const { connectionLabel, localModelLabel, nameForALocalModel, shortModelName } = await import("./local")

describe("localModelLabel", () => {
  const connections = [
    { name: "Coder", model: "qwen2.5-coder:7b", adapter: "ollama" },
    { name: "Remote qwen", model: "qwen2.5:14b", adapter: "openai" },
    { name: "  ", model: "llama3.2:3b", adapter: "ollama" },
  ]

  it("is the nickname of the Ollama connection made for that model", () => {
    expect(localModelLabel("qwen2.5-coder:7b", connections)).toBe("Coder")
  })

  it("is the short name when no connection exists, or only a remote one of the same id, or a blank name", () => {
    expect(localModelLabel("mistral:7b", connections)).toBe("mistral 7b")
    expect(localModelLabel("qwen2.5:14b", connections)).toBe("qwen2.5 14b")
    expect(localModelLabel("llama3.2:3b", connections)).toBe("llama3.2 3b")
    expect(localModelLabel("mistral:7b", undefined)).toBe("mistral 7b")
  })

  it("is the short name when the nickname is only the model id again", () => {
    const id = "hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0"
    expect(localModelLabel(id, [{ name: id, model: id, adapter: "ollama" }])).toBe("MiniCPM5-1B")
    expect(localModelLabel("llama3.2:latest", [{ name: "llama3.2", model: "llama3.2:latest", adapter: "ollama" }])).toBe(
      "llama3.2",
    )
  })
})

describe("shortModelName", () => {
  const table: [string, string][] = [
    ["hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0", "MiniCPM5-1B"],
    ["qwen3.5:4b", "qwen3.5 4b"],
    ["granite4.2:3b", "granite4.2 3b"],
    ["llama3.2:latest", "llama3.2"],
    ["llama3.2", "llama3.2"],
    ["qwen2.5-coder:7b-instruct-q4_K_M", "qwen2.5-coder 7b"],
    ["hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF:q4_K_M", "Llama-3.2-3B-Instruct"],
    ["gemma3n:e2b", "gemma3n e2b"],
    ["mixtral:8x7b", "mixtral 8x7b"],
    ["qwen3:0.6b", "qwen3 0.6b"],
    ["someone/model-gguf", "model"],
    ["org/weights-safetensors", "weights"],
    ["anthropic/claude-3.5-sonnet", "claude-3.5-sonnet"],
    ["gpt-4o", "gpt-4o"],
    ["phi4:fp16", "phi4"],
    ["  qwen3:8b  ", "qwen3 8b"],
    ["", ""],
  ]
  for (const [id, expected] of table) {
    it(`${JSON.stringify(id)} -> ${JSON.stringify(expected)}`, () => {
      expect(shortModelName(id)).toBe(expected)
    })
  }

  it("is empty for no id", () => {
    expect(shortModelName(undefined)).toBe("")
    expect(shortModelName(null)).toBe("")
  })
})

describe("connectionLabel and nameForALocalModel", () => {
  it("prefers a real nickname, and falls back to the short name for a blank or id-shaped one", () => {
    expect(connectionLabel({ name: "Coder", model: "qwen2.5-coder:7b" })).toBe("Coder")
    expect(connectionLabel({ name: " ", model: "qwen2.5-coder:7b" })).toBe("qwen2.5-coder 7b")
    expect(connectionLabel({ name: "qwen3:8b", model: "qwen3:8b" })).toBe("qwen3 8b")
    expect(connectionLabel(undefined)).toBe("")
  })

  it("names a new one-click connection by the short name, not the link", () => {
    expect(nameForALocalModel("hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0")).toBe("MiniCPM5-1B")
    expect(nameForALocalModel("llama3.2:latest")).toBe("llama3.2")
  })
})
