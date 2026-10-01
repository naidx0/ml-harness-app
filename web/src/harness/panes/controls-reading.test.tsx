import { render } from "solid-js/web"
import { afterEach, describe, expect, it, vi } from "vitest"

/** Before the tool catalogue answered, the search box read "Search 0 tools". */

const pending = new Map<string, { resolve: (value: unknown) => void; reject: (error: unknown) => void }>()
vi.mock("../engine", () => ({
  harness: (path: string) => new Promise((resolve, reject) => pending.set(path, { resolve, reject })),
}))

const { default: ControlsPane } = await import("./controls")

const tick = () => new Promise((done) => setTimeout(done, 0))

let dispose: (() => void) | undefined
afterEach(() => {
  dispose?.()
  dispose = undefined
  pending.clear()
  document.body.innerHTML = ""
})

describe("Controls says it is reading before the catalogue answers", () => {
  it("shows Reading…, never a search over 0 tools", async () => {
    const host = document.createElement("div")
    document.body.append(host)
    dispose = render(() => <ControlsPane threadId={undefined} />, host)
    await tick()
    expect(host.textContent).toContain("Reading…")
    expect(host.querySelector('input[placeholder="Search 0 tools"]')).toBeNull()

    pending.get("/api/tools")!.resolve({ controls: [] })
    pending.delete("/api/tools")
    await tick()
    await tick()
    expect(host.textContent).not.toContain("Reading…")
    expect(host.textContent).toContain("No tools")
  })
})
