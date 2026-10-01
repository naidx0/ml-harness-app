import { render } from "solid-js/web"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { NextStep } from "./readers"

const harness = vi.fn<(path: string, init?: { body?: { approved?: boolean } }) => Promise<unknown>>()
vi.mock("../engine", () => ({
  harness: (path: string, init?: unknown) => harness(path, init as never),
  HarnessError: class HarnessError extends Error {
    constructor(
      readonly status: number,
      message: string,
    ) {
      super(message)
    }
  },
}))

const { NextStepControl } = await import("./next-step")
const { HarnessError } = await import("../engine")

const control = (name: string, needs_approval: boolean) => ({
  name,
  label: name,
  group: "g",
  verb: "",
  order: 0,
  description: "",
  fields: [],
  reads: [],
  writes: [],
  needs_approval,
})
const CATALOGUE = { instruction_set: "t", controls: [control("risky_tool", true), control("plain_tool", false)] }

const step = (tool: string): NextStep => ({
  fact: "f",
  tool,
  runAs: "user",
  verb: "measure it",
  substantiation: "",
  also: [],
  note: null,
})

/** What each run was sent, in order. */
let sent: { tool: string; approved: boolean | undefined }[] = []
let refuseUnapproved = false

beforeEach(() => {
  sent = []
  refuseUnapproved = false
  harness.mockReset()
  harness.mockImplementation(async (path, init) => {
    if (path === "/api/tools") return CATALOGUE
    const tool = decodeURIComponent(path.replace("/api/tools/", ""))
    sent.push({ tool, approved: init?.body?.approved })
    if (refuseUnapproved && !init?.body?.approved) throw new HarnessError(428, "this tool needs approval")
    return { tool, result: { ok: true, summary: "measured" } }
  })
})

let dispose: (() => void) | undefined
afterEach(() => {
  dispose?.()
  dispose = undefined
  document.body.innerHTML = ""
})

const tick = () => new Promise((resolve) => setTimeout(resolve, 0))

async function mount(tool: string) {
  const host = document.createElement("div")
  document.body.append(host)
  dispose = render(() => <NextStepControl step={step(tool)} threadId={3} />, host)
  await tick()
  await tick()
  return host
}

function press(host: HTMLElement, words: string) {
  const found = [...host.querySelectorAll("button")].find((button) => button.textContent?.includes(words))
  if (!found) throw new Error(`no button saying ${words}; saw: ${host.textContent}`)
  found.click()
}

describe("a next step whose tool needs approval", () => {
  it("asks before it sends, and sends approved:true only on the yes", async () => {
    const host = await mount("risky_tool")
    press(host, "Measure it")
    await tick()
    expect(sent).toEqual([])
    expect(host.querySelector('[data-slot="next-step-confirm"]')).not.toBeNull()
    press(host, "Yes, run it")
    await tick()
    expect(sent).toEqual([{ tool: "risky_tool", approved: true }])
    expect(host.textContent).toContain("measured")
  })

  it("sends nothing when the person says not now", async () => {
    const host = await mount("risky_tool")
    press(host, "Measure it")
    await tick()
    press(host, "Not now")
    await tick()
    expect(sent).toEqual([])
    expect(host.querySelector('[data-slot="next-step-confirm"]')).toBeNull()
  })

  it("offers the yes when the engine answers 428, instead of ending on the refusal", async () => {
    refuseUnapproved = true
    const host = await mount("uncatalogued_tool")
    press(host, "Measure it")
    await tick()
    expect(sent).toEqual([{ tool: "uncatalogued_tool", approved: false }])
    expect(host.querySelector('[data-slot="next-step-confirm"]')).not.toBeNull()
    press(host, "Yes, run it")
    await tick()
    expect(sent.at(-1)).toEqual({ tool: "uncatalogued_tool", approved: true })
    expect(host.textContent).toContain("measured")
  })
})

describe("a next step whose tool does not need approval", () => {
  it("runs on the first press, unapproved", async () => {
    const host = await mount("plain_tool")
    press(host, "Measure it")
    await tick()
    expect(sent).toEqual([{ tool: "plain_tool", approved: false }])
    expect(host.querySelector('[data-slot="next-step-confirm"]')).toBeNull()
  })
})
