import { render } from "solid-js/web"
import { afterEach, describe, expect, it, vi } from "vitest"

/**
 * Settings > Harness > Controls files a run under the chat Settings was
 * opened over. Their root settings pages have no server context, so the page
 * must find that chat's thread without their session store: `useData()` there
 * threw and took the app to its error screen. This renders the page with
 * nothing of theirs around it but the settings surface.
 */

let route: { type: string; sessionId?: string } = { type: "session", sessionId: "ses_9" }
vi.mock("@/settings/surface", () => ({ useSettingsSurface: () => ({ route: () => route }) }))
vi.mock("@/runtime/server/current", () => ({
  useData: () => {
    throw new Error("Server context must be used within a context provider")
  },
}))
const reads: string[] = []
vi.mock("../engine", () => ({
  harness: async (path: string) => {
    reads.push(path)
    return { data: { id: "ses_9", metadata: { harness: { threadID: "7" } } } }
  },
}))
vi.mock("../panes/controls", () => ({
  default: (props: { threadId: number | undefined }) => <div data-testid="pane">{String(props.threadId)}</div>,
}))

const { default: ControlsSection } = await import("./controls")
const tick = () => new Promise((done) => setTimeout(done, 0))

let dispose: (() => void) | undefined
afterEach(() => {
  dispose?.()
  dispose = undefined
  reads.length = 0
  document.body.innerHTML = ""
})

describe("the Controls settings page", () => {
  it("renders outside their server context and files under the chat it was opened over", async () => {
    dispose = render(() => <ControlsSection />, document.body)
    await tick()
    await tick()
    expect(reads).toEqual(["/oc/api/session/ses_9"])
    expect(document.querySelector('[data-testid="pane"]')?.textContent).toBe("7")
  })

  it("opened from anywhere but a chat, it reads nothing and files nothing", async () => {
    route = { type: "home" }
    dispose = render(() => <ControlsSection />, document.body)
    await tick()
    expect(reads).toEqual([])
    expect(document.querySelector('[data-testid="pane"]')?.textContent).toBe("undefined")
    route = { type: "session", sessionId: "ses_9" }
  })
})
