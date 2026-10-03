import { render } from "solid-js/web"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const harness = vi.fn<(path: string) => Promise<unknown>>()
vi.mock("../engine", () => ({ harness: (path: string) => harness(path) }))
/** What Settings was asked to open. */
const opened: string[] = []
vi.mock("@/settings/surface", () => ({ useSettingsSurface: () => ({ open: (tab: string) => opened.push(tab) }) }))
vi.mock("@/providers/models/selection", () => ({ useLocal: () => ({ agent: { current: () => ({ name: "Plan" }) } }) }))
/** What the card registered with their command registry, by key. */
const registered = new Map<string, () => { id: string; disabled?: boolean; hidden?: boolean }[]>()
vi.mock("@/shell/commands/command", () => ({
  useCommand: () => ({ register: (key: string, options: () => never[]) => registered.set(key, options) }),
}))

/** The facade's catalog events, as `sdk.event.on` handlers. */
const handlers = new Map<string, () => void>()
vi.mock("@/runtime/server/client", () => ({
  useServerSDK: () => ({
    event: {
      on: (type: string, handler: () => void) => {
        handlers.set(type, handler)
        return () => handlers.delete(type)
      },
    },
  }),
}))

const { HarnessStart } = await import("./start")
const { takeModelsSection } = await import("../settings/models-open")

const composer = { onInput: () => undefined, restoreFocus: () => undefined } as never

let providerReads = 0
let providers: () => Promise<unknown> = async () => []

beforeEach(() => {
  providerReads = 0
  handlers.clear()
  opened.length = 0
  harness.mockReset()
  harness.mockImplementation(async (path) => {
    if (path === "/api/providers") {
      providerReads += 1
      return providers()
    }
    return undefined
  })
})

let dispose: (() => void) | undefined
afterEach(() => {
  dispose?.()
  dispose = undefined
  document.body.innerHTML = ""
})

const tick = () => new Promise((resolve) => setTimeout(resolve, 0))

async function mount() {
  const host = document.createElement("div")
  document.body.append(host)
  dispose = render(() => <HarnessStart composer={composer} />, host)
  await tick()
  await tick()
  return host
}

describe("the new-chat surface", () => {
  it("carries the composer's mode for the colour hint", async () => {
    const surface = document.createElement("div")
    surface.dataset.component = "new-session"
    document.body.append(surface)
    const host = document.createElement("div")
    surface.append(host)
    dispose = render(() => <HarnessStart composer={composer} />, host)
    await tick()
    expect(surface.dataset.harnessMode).toBe("plan")
  })

  it("puts This computer first and centres everything under it", async () => {
    harness.mockImplementation(async (path) => {
      if (path === "/local_specs") return { gpu_name: "RTX 2060 SUPER", vram_gb: 8, ram_gb: 32 }
      if (path === "/api/providers") return [{ id: 1, name: "m", is_active: true }]
      return undefined
    })
    const host = await mount()
    const root = host.querySelector<HTMLElement>('[data-slot="harness-start"]')!
    const machine = root.querySelector('[data-slot="harness-start-machine"]')!
    const starters = root.querySelector('[data-slot="harness-start-starters"]')!
    expect(machine.textContent).toBe("This computer: RTX 2060 SUPER · 8 GB video memory · 32 GB memory")
    // First visible child: the marker before it is hidden.
    const visible = [...root.children].filter((child) => !(child as HTMLElement).hidden)
    expect(visible[0]).toBe(machine)
    expect(machine.compareDocumentPosition(starters) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(root.classList.contains("items-center")).toBe(true)
    expect(root.classList.contains("text-center")).toBe(true)
    expect(starters.classList.contains("justify-center")).toBe(true)
  })

  it("turns off their shell mode and location cycle, which a new chat's composer registers", async () => {
    await mount()
    const options = registered.get("harness.start")?.() ?? []
    for (const id of ["prompt.mode.shell", "session.location.cycle", "terminal.toggle"]) {
      expect(options.find((option) => option.id === id)).toMatchObject({ disabled: true, hidden: true })
    }
  })
})

describe("the new-chat card's model check", () => {
  it("says the connections could not be read, instead of asking to pick a model", async () => {
    providers = async () => {
      throw new Error("the engine is not answering")
    }
    const host = await mount()
    const line = host.querySelector('[data-slot="start-connections-error"]')
    expect(line?.classList.contains("text-v2-state-fg-danger")).toBe(true)
    expect(line?.textContent).toContain("the engine is not answering")
    expect(host.textContent).not.toContain("Pick a model to start")
  })

  it("names the active model by its nickname, or its short name, under This computer", async () => {
    const link = "hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0"
    providers = async () => [
      { id: 1, name: "Coder", model: "qwen2.5-coder:7b", adapter: "ollama", is_active: false },
      { id: 2, name: link, model: link, adapter: "ollama", is_active: true },
    ]
    let host = await mount()
    let line = host.querySelector<HTMLElement>('[data-slot="harness-start-model"]')
    expect(line?.textContent).toBe("Model: MiniCPM5-1B")
    expect(line?.title).toBe(link)
    dispose?.()
    document.body.innerHTML = ""
    providers = async () => [{ id: 1, name: "Coder", model: "qwen2.5-coder:7b", adapter: "ollama", is_active: true }]
    host = await mount()
    line = host.querySelector<HTMLElement>('[data-slot="harness-start-model"]')
    expect(line?.textContent).toBe("Model: Coder")
  })

  it("asks to connect a model with two buttons and nothing else when none is active", async () => {
    providers = async () => [{ id: 1, name: "m", is_active: false }]
    const host = await mount()
    const card = host.querySelector<HTMLElement>('[data-slot="start-no-model"]')!
    expect(card.textContent).toContain("Connect a model to start")
    const buttons = [...card.querySelectorAll("button")].map((one) => one.textContent?.trim())
    expect(buttons).toEqual(["Use a model on this computer", "Use an API key"])
    expect(card.querySelector("code")).toBeNull()
  })

  it("opens Settings > Models at the road each button names", async () => {
    providers = async () => []
    const host = await mount()
    const button = (text: string) => [...host.querySelectorAll("button")].find((one) => one.textContent?.trim() === text)!
    button("Use a model on this computer").click()
    expect(opened).toEqual(["harness:connections"])
    expect(takeModelsSection()).toBe("local")
    button("Use an API key").click()
    expect(opened).toEqual(["harness:connections", "harness:connections"])
    expect(takeModelsSection()).toBe("api")
    expect(takeModelsSection()).toBeUndefined()
  })

  it("shows no card once a model is in use", async () => {
    providers = async () => [{ id: 1, name: "m", is_active: true }]
    const host = await mount()
    expect(host.querySelector('[data-slot="start-no-model"]')).toBeNull()
  })

  it("re-reads the connections on the facade's provider.updated and model.updated", async () => {
    providers = async () => []
    await mount()
    const before = providerReads
    handlers.get("provider.updated")!()
    await tick()
    handlers.get("model.updated")!()
    await tick()
    expect(providerReads).toBe(before + 2)
  })
})
