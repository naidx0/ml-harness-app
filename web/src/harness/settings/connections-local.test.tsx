import { render } from "solid-js/web"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const listLocalModels = vi.fn<() => Promise<unknown[]>>()
vi.mock("../providers/local", async (original) => ({
  ...(await original<typeof import("../providers/local")>()),
  listLocalModels: () => listLocalModels(),
  connectLocal: async () => undefined,
}))
const harness = vi.fn<(path: string) => Promise<unknown>>()
vi.mock("../engine", () => ({ harness: (path: string) => harness(path) }))

const { AlreadyRunning, LocalModels, toolCallingOf } = await import("./connections-local")

let dispose: (() => void) | undefined
beforeEach(() => {
  listLocalModels.mockReset()
  harness.mockReset()
})
afterEach(() => {
  dispose?.()
  dispose = undefined
  document.body.innerHTML = ""
})

const tick = () => new Promise((resolve) => setTimeout(resolve, 0))

async function mount(view: () => any) {
  const host = document.createElement("div")
  document.body.append(host)
  dispose = render(view, host)
  await tick()
  await tick()
  return host
}

const model = (name: string, capabilities: string[] | null) => ({
  name,
  family: null,
  params_b: null,
  capabilities,
  on_disk_gb: null,
})

describe("a local model's tool calling", () => {
  it("is 'not checked' when the engine sent no capabilities, never 'no tool calling'", () => {
    expect(toolCallingOf(null)).toBe("tool calling not checked")
    expect(toolCallingOf(undefined)).toBe("tool calling not checked")
    expect(toolCallingOf([])).toBe("no tool calling")
    expect(toolCallingOf(["completion", "tools"])).toBe("can call tools")
  })

  it("reads that way on the page", async () => {
    listLocalModels.mockResolvedValue([model("qwen3:8b", null), model("llama3:8b", ["completion"])])
    const host = await mount(() => <LocalModels connections={[]} busy={false} run={async () => true} />)
    const rows = [...host.querySelectorAll(".settings-provider-row")].map((row) => row.textContent ?? "")
    expect(rows[0]).toContain("tool calling not checked")
    expect(rows[1]).toContain("no tool calling")
  })
})

describe("a local model's name on the list", () => {
  it("is the short name, or the connection's nickname, with the full id in its title", async () => {
    const id = "hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0"
    listLocalModels.mockResolvedValue([model(id, null), model("qwen2.5-coder:7b", null)])
    const connections = [{ name: "Coder", model: "qwen2.5-coder:7b", adapter: "ollama" }] as never
    const host = await mount(() => <LocalModels connections={connections} busy={false} run={async () => true} />)
    const names = [...host.querySelectorAll<HTMLElement>(".settings-provider-name")]
    expect(names.map((one) => one.textContent?.trim())).toEqual(["MiniCPM5-1B", "Coder"])
    expect(names.map((one) => one.title)).toEqual([id, "qwen2.5-coder:7b"])
  })
})

describe("looking for local models", () => {
  it("comes back from 'Looking…' once the list has answered", async () => {
    listLocalModels.mockResolvedValue([model("qwen3:8b", ["tools"])])
    const host = await mount(() => <LocalModels connections={[]} busy={false} run={async () => true} />)
    const button = [...host.querySelectorAll("button")].find((one) => /Look/.test(one.textContent ?? ""))!
    expect(button.textContent).toContain("Look again")
    expect(button.disabled).toBe(false)
  })
})

describe("what is already running here, when the read fails", () => {
  it("says it could not read, with the error, and does not claim nothing is listening", async () => {
    harness.mockRejectedValue(new Error("the engine is not answering"))
    const host = await mount(() => <AlreadyRunning />)
    const line = host.querySelector('[data-slot="discover-error"]')
    expect(line?.textContent).toContain("Could not read")
    expect(line?.textContent).toContain("the engine is not answering")
    expect(host.textContent).not.toContain("Nothing is listening")
  })

  it("still says nothing is listening when the read answered empty", async () => {
    harness.mockResolvedValue({ candidates: [] })
    const host = await mount(() => <AlreadyRunning />)
    expect(host.textContent).toContain("Nothing is listening on the usual local ports.")
    expect(host.querySelector('[data-slot="discover-error"]')).toBeNull()
  })
})

describe("when there is no local model to pick (on Windows)", () => {
  const INSTALL = "irm https://raw.githubusercontent.com/naidx0/ml-harness-app/main/install.ps1 | iex"
  const agent = navigator.userAgent
  beforeEach(() => {
    Object.defineProperty(navigator, "userAgent", { value: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", configurable: true })
  })
  afterEach(() => {
    Object.defineProperty(navigator, "userAgent", { value: agent, configurable: true })
  })

  it("says Ollama is not answering, shows its words, and offers the one-line fix", async () => {
    listLocalModels.mockRejectedValue(new Error("connection refused at 127.0.0.1:11434"))
    const host = await mount(() => <LocalModels connections={[]} busy={false} run={async () => true} />)
    const card = host.querySelector<HTMLElement>('[data-slot="local-missing"]')!
    expect(card.dataset.missing).toBe("ollama")
    expect(card.textContent).toContain("Ollama is not answering on this computer")
    expect(card.textContent).toContain("connection refused at 127.0.0.1:11434")
    expect(card.querySelector("code")?.textContent).toBe(INSTALL)
  })

  it("says Ollama has no model yet, and offers the same line, which pulls one and connects it", async () => {
    listLocalModels.mockResolvedValue([])
    const host = await mount(() => <LocalModels connections={[]} busy={false} run={async () => true} />)
    const card = host.querySelector<HTMLElement>('[data-slot="local-missing"]')!
    expect(card.dataset.missing).toBe("model")
    expect(card.textContent).toContain("Ollama is running and has no models yet")
    expect(card.textContent).toContain("qwen3.5:4b")
    expect(card.querySelector("code")?.textContent).toBe(INSTALL)
  })
})

describe("when there is no local model to pick (on a Mac)", () => {
  const agent = navigator.userAgent
  beforeEach(() => {
    Object.defineProperty(navigator, "userAgent", { value: "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5)", configurable: true })
  })
  afterEach(() => {
    Object.defineProperty(navigator, "userAgent", { value: agent, configurable: true })
  })

  it("gives the Terminal line and says Applications, not PowerShell and the Start menu", async () => {
    listLocalModels.mockRejectedValue(new Error("connection refused"))
    const host = await mount(() => <LocalModels connections={[]} busy={false} run={async () => true} />)
    const card = host.querySelector<HTMLElement>('[data-slot="local-missing"]')!
    expect(card.querySelector("code")?.textContent).toBe(
      "curl -fsSL https://raw.githubusercontent.com/naidx0/ml-harness-app/main/install.sh | sh",
    )
    expect(card.textContent).toContain("Terminal")
    expect(card.textContent).toContain("Applications")
    expect(card.textContent).not.toContain("PowerShell")
    expect(card.textContent).not.toContain("Start menu")
  })
})
