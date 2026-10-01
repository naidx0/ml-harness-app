import type { Component } from "solid-js"
import { render } from "solid-js/web"
import { afterEach, describe, expect, it, vi } from "vitest"

/**
 * A settings page must tell "still reading", "the read failed" and "the
 * engine has none" apart. It said "Nothing is connected yet" and "No
 * projects yet" under a read that had FAILED, and "Reading this machine…"
 * for ever after one.
 */

const pending = new Map<string, { resolve: (value: unknown) => void; reject: (error: unknown) => void }>()
vi.mock("../engine", () => ({
  harness: (path: string) => new Promise((resolve, reject) => pending.set(path, { resolve, reject })),
}))

// Loaded once, up front: a cold import of a settings page takes longer than
// one test's timeout on this machine.
const { default: Connections } = await import("./connections")
const { default: Tools } = await import("./tools")
const { default: Machine } = await import("./machine")

const tick = () => new Promise((done) => setTimeout(done, 0))

async function settle(path: string, how: { value?: unknown; error?: Error }) {
  await tick()
  const request = pending.get(path)
  if (!request) throw new Error(`no read of ${path} is out; out: ${[...pending.keys()].join(", ")}`)
  pending.delete(path)
  if (how.error) request.reject(how.error)
  else request.resolve(how.value)
  await tick()
}

let dispose: (() => void) | undefined
afterEach(() => {
  dispose?.()
  dispose = undefined
  pending.clear()
  document.body.innerHTML = ""
})

function mount(Page: Component) {
  const host = document.createElement("div")
  document.body.append(host)
  dispose = render(() => <Page />, host)
  return host
}

describe("settings pages tell a failed read from an empty one", () => {
  it("Connections: reading, then failed - never 'Nothing is connected yet'", async () => {
    const host = mount(Connections)
    await tick()
    expect(host.textContent).toContain("Reading your connections…")
    await settle("/api/providers", { error: new Error("engine is not running") })
    expect(host.textContent).not.toContain("Nothing is connected yet")
    expect(host.textContent).toContain("Could not read your connections.")
    expect(host.textContent).toContain("engine is not running")
  })

  it("Connections: an answered empty list is the empty line", async () => {
    const host = mount(Connections)
    await settle("/api/providers", { value: [] })
    expect(host.textContent).toContain("Nothing is connected yet")
  })

  it("Tools: a failed projects read is not 'No projects yet'", async () => {
    const host = mount(Tools)
    await tick()
    expect(host.textContent).toContain("Reading projects…")
    await settle("/api/projects", { error: new Error("projects table is locked") })
    expect(host.textContent).not.toContain("No projects yet")
    expect(host.textContent).toContain("Could not read the projects")
    expect(host.textContent).toContain("projects table is locked")
  })

  it("Tools: an answered empty list says no projects", async () => {
    const host = mount(Tools)
    await settle("/api/projects", { value: [] })
    expect(host.textContent).toContain("No projects yet")
  })

  it("This machine: a failed read stops saying 'Reading'", async () => {
    const host = mount(Machine)
    await tick()
    expect(host.textContent).toContain("Reading this machine…")
    await settle("/local_specs", { error: new Error("detector crashed") })
    expect(host.textContent).not.toContain("Reading this machine…")
    expect(host.textContent).toContain("Nothing reported.")
    expect(host.textContent).toContain("detector crashed")
  })
})
