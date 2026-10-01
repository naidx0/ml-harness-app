import { render } from "solid-js/web"
import { afterEach, describe, expect, it, vi } from "vitest"
import { PlatformProvider } from "@/runtime/platform/platform"
import type { Platform } from "@/runtime/platform/platform"

/**
 * Settings > About is the harness's (the owner, 2026-09-23: "About says
 * OpenCode, anomaly, etc. - get rid of that About"): every value on it is
 * read from the engine, and the interface's origin is one line.
 */

const answers = new Map<string, unknown>()
vi.mock("../engine", () => ({
  harness: (path: string) =>
    answers.has(path) ? Promise.resolve(answers.get(path)) : Promise.reject(new Error(`no answer for ${path}`)),
}))

const { default: About, CREDIT } = await import("./about")

const tick = () => new Promise((done) => setTimeout(done, 0))

let dispose: (() => void) | undefined
afterEach(() => {
  dispose?.()
  dispose = undefined
  answers.clear()
  document.body.innerHTML = ""
})

async function mount(version = "0.1.0") {
  const host = document.createElement("div")
  document.body.append(host)
  dispose = render(
    () => (
      <PlatformProvider value={{ version } as Platform}>
        <About />
      </PlatformProvider>
    ),
    host,
  )
  await tick()
  await tick()
  return host
}

describe("the harness's About", () => {
  it("names the product and reads version, build, engine and database from the engine", async () => {
    answers.set("/health", {
      status: "ok",
      engine: { engine_id: "eng-7f3a9c21d4b5e6f7a8" },
      build: { sha: "2cd94381aa5b6c7d8e9f", dirty: false },
      database: { path: "C:/data/harness.db", runs: 12 },
    })
    answers.set("/oc/api/info", { version: "0.1.0" })
    const host = await mount()
    const text = host.textContent ?? ""
    expect(text).toContain("ML Harness")
    expect(text).toContain("0.1.0")
    expect(text).not.toContain("(engine")
    expect(text).toContain("2cd94381aa5b")
    expect(text).toContain("eng-7f3a9c21d4b5")
    expect(text).toContain("C:/data/harness.db")
    expect(text).toContain("12 runs")
  })

  it("credits the interface once, and carries none of their colophon", async () => {
    answers.set("/health", { status: "ok" })
    answers.set("/oc/api/info", { version: "0.1.0" })
    const host = await mount()
    const text = host.textContent ?? ""
    expect(CREDIT).toBe("Interface derived from OpenCode (MIT)")
    expect(text.split("OpenCode").length - 1).toBe(1)
    expect(host.querySelector('[data-slot="about-credit"]')?.textContent).toBe(CREDIT)
    for (const theirs of ["Anomaly", "anomaly", "opencode.ai", "Discord", "thdxr", "Written by", "trademark"])
      expect(text).not.toContain(theirs)
    expect(host.querySelector("img, svg")).toBeNull()
  })

  it("names a different engine release, and says so when the engine does not answer", async () => {
    answers.set("/oc/api/info", { version: "0.2.0" })
    const host = await mount("0.1.0")
    const text = host.textContent ?? ""
    expect(text).toContain("0.1.0 (engine 0.2.0)")
    expect(text).toContain("engine not answering")
    expect(text).not.toMatch(/\d+ runs?\b/)
  })
})
