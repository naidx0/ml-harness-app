import { createSignal } from "solid-js"
import { render } from "solid-js/web"
import { afterEach, describe, expect, it } from "vitest"
import { HARNESS_MODES, HarnessSurfaceMarks, modeOf } from "./marks"

let dispose: (() => void) | undefined
afterEach(() => {
  dispose?.()
  dispose = undefined
  document.body.innerHTML = ""
})

describe("modeOf", () => {
  it("reads the facade's agents as modes, case-insensitively, and nothing else", () => {
    // The facade's agents, as their picker names them (catalog.agents: name.capitalize()).
    expect(["Plan", "Build", "Measure", "Write", "Full"].map(modeOf)).toEqual([...HARNESS_MODES])
    expect(modeOf(" plan ")).toBe("plan")
    expect(modeOf("general")).toBeUndefined()
    expect(modeOf(undefined)).toBeUndefined()
    expect(modeOf("")).toBeUndefined()
  })
})

describe("HarnessSurfaceMarks", () => {
  it("marks the surface it finds, follows the mode and the work, and unmarks on unmount", () => {
    const surface = document.createElement("section")
    const slot = document.createElement("div")
    slot.dataset.slot = "session-review-toggle"
    surface.append(slot)
    document.body.append(surface)
    const [agent, setAgent] = createSignal<string | undefined>("Plan")
    const [busy, setBusy] = createSignal(false)
    dispose = render(
      () => (
        <HarnessSurfaceMarks
          find={(marker) => marker.closest<HTMLElement>('[data-slot="session-review-toggle"]')?.parentElement}
          mode={agent}
          working={busy}
        />
      ),
      slot,
    )
    expect(surface.dataset.harnessMode).toBe("plan")
    expect(surface.dataset.harnessWorking).toBe("false")
    // It takes no room in the header it sits in.
    expect(slot.querySelector<HTMLElement>('[data-slot="harness-surface-marks"]')!.hidden).toBe(true)

    setAgent("Full")
    setBusy(true)
    expect(surface.dataset.harnessMode).toBe("full")
    expect(surface.dataset.harnessWorking).toBe("true")

    // An agent that is not a mode gets no hint, not a stale one.
    setAgent("general")
    expect(surface.dataset.harnessMode).toBeUndefined()

    dispose()
    dispose = undefined
    expect(surface.dataset.harnessWorking).toBeUndefined()
    expect(surface.hasAttribute("data-harness-mode")).toBe(false)
  })
})
