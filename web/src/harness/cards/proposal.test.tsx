import { render } from "solid-js/web"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { readProposal } from "./readers"
import { SPECIMENS } from "./test-specimens"

const harness = vi.fn<(path: string, init?: unknown) => Promise<unknown>>()
vi.mock("../engine", () => ({
  harness: (path: string, init?: unknown) => harness(path, init),
  HarnessError: class HarnessError extends Error {},
}))

const { DENIALS, ProposalBody, readDenial, writeDenial } = await import("./proposal")

const proposal = readProposal(SPECIMENS.proposal)!
const FINGERPRINT = proposal.approve

let dispose: (() => void) | undefined
beforeEach(() => {
  harness.mockReset()
  localStorage.clear()
})
afterEach(() => {
  dispose?.()
  dispose = undefined
  document.body.innerHTML = ""
})

function mount(threadId: number | undefined) {
  const host = document.createElement("div")
  document.body.append(host)
  dispose = render(() => <ProposalBody proposal={proposal} args={{}} threadId={threadId} />, host)
  return host
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0))

describe("a denial", () => {
  it("is filed under the thread as well as the plan's fingerprint", () => {
    writeDenial(1, FINGERPRINT, { at: "2026-09-22T00:00:00Z", reason: "clicked" })
    expect(readDenial(1, FINGERPRINT)).not.toBeNull()
    // The same plan in another conversation is not denied there.
    expect(readDenial(2, FINGERPRINT)).toBeNull()
    expect(Object.keys(JSON.parse(localStorage.getItem(DENIALS)!))).toEqual([`1:${FINGERPRINT}`])
  })

  it("in one chat does not hide the approval in another", async () => {
    writeDenial(1, FINGERPRINT, { at: "2026-09-22T00:00:00Z", reason: "clicked" })
    harness.mockResolvedValue({ storms: [] })
    const host = mount(2)
    await tick()
    expect(host.textContent).toContain("Allow once")
    expect(host.textContent).not.toContain("Denied by you")
  })
})

describe("the storm read", () => {
  it("shows neither the ask nor a denial while it is loading", async () => {
    let answer: (value: unknown) => void = () => {}
    harness.mockImplementation(() => new Promise((resolve) => (answer = resolve)))
    const host = mount(5)
    await tick()
    expect(host.textContent).not.toContain("Allow once")
    expect(host.querySelector('[data-slot="storm-reading"]')).not.toBeNull()
    answer({ storms: [] })
    await tick()
    expect(host.textContent).toContain("Allow once")
  })

  it("never flashes the ask for a plan that was already approved", async () => {
    harness.mockImplementation(async (path: string) =>
      path.startsWith("/api/storms?")
        ? { storms: [{ id: 9, fingerprint: FINGERPRINT }] }
        : { storm: 9, state: "done", manifest: { fingerprint: FINGERPRINT }, steps: [] },
    )
    const host = mount(5)
    expect(host.textContent).not.toContain("Allow once")
    await tick()
    await tick()
    expect(host.textContent).not.toContain("Allow once")
    expect(host.textContent).toContain("storm 9")
  })

  it("shows a failed read in the danger colour, and no ask", async () => {
    harness.mockRejectedValue(new Error("the engine is not answering"))
    const host = mount(5)
    await tick()
    const line = host.querySelector('[data-slot="storm-error"]')
    expect(line?.classList.contains("text-v2-state-fg-danger")).toBe(true)
    expect(line?.textContent).toContain("the engine is not answering")
    expect(host.textContent).not.toContain("Allow once")
  })
})
