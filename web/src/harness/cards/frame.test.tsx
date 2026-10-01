import { render } from "solid-js/web"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import source from "./frame.tsx?raw"

const detachStage = vi.fn(async (_threadId: number) => "browser" as const)
vi.mock("../panes/stage-detach", () => ({ detachStage: (threadId: number) => detachStage(threadId) }))

const { Fold, StageActions } = await import("./frame")
const { onBridge, OPEN_PANE_EVENT, paneRequestIsOurs } = await import("../bridge/events")

let dispose: (() => void) | undefined
let stops: (() => void)[] = []
beforeEach(() => detachStage.mockClear())
afterEach(() => {
  dispose?.()
  dispose = undefined
  for (const stop of stops) stop()
  stops = []
  document.body.innerHTML = ""
})

function mount(view: () => any) {
  const host = document.createElement("div")
  document.body.append(host)
  dispose = render(view, host)
  return host
}

function buttonSaying(host: HTMLElement, words: string) {
  const found = [...host.querySelectorAll("button")].find((button) => button.textContent?.includes(words))
  if (!found) throw new Error(`no button saying ${words}`)
  return found
}

/** A session mount on `thread`, answering open-pane the way session/mount.tsx does. */
function sessionOn(thread: number, opened: string[]) {
  stops.push(
    onBridge(OPEN_PANE_EVENT, (detail) => {
      if (!paneRequestIsOurs(detail, thread)) return false
      opened.push(detail.pane)
    }),
  )
}

describe("a Stage card's Open in panel", () => {
  it("opens the pane when the session is on the card's thread", () => {
    const opened: string[] = []
    sessionOn(12, opened)
    const host = mount(() => <StageActions threadId={12} />)
    buttonSaying(host, "Open in panel").click()
    expect(opened).toEqual(["stage"])
    expect(detachStage).not.toHaveBeenCalled()
  })

  it("is declined by a session on another thread, and pops its own thread out instead", () => {
    const opened: string[] = []
    sessionOn(7, opened)
    const host = mount(() => <StageActions threadId={12} />)
    buttonSaying(host, "Open in panel").click()
    expect(opened).toEqual([])
    expect(detachStage).toHaveBeenCalledWith(12)
  })

  it("pops out when no session is listening (a pop-out window)", () => {
    const host = mount(() => <StageActions threadId={12} />)
    buttonSaying(host, "Open in panel").click()
    expect(detachStage).toHaveBeenCalledWith(12)
  })
})

describe("the card frame's own styles", () => {
  it("never uses a bare `rounded`, which their Tailwind theme generates no CSS for", () => {
    const bare = source.match(/class(?:List)?=\{?[`"][^`"]*(?<![\w-])rounded(?![\w-])/g) ?? []
    expect(bare).toEqual([])
  })

  it("the scan above finds a planted bare `rounded` (positive control)", () => {
    const planted = 'class="inline-flex rounded px-1"'
    expect(planted.match(/class(?:List)?=\{?[`"][^`"]*(?<![\w-])rounded(?![\w-])/g)).toHaveLength(1)
  })

  it("draws a chevron on a Fold, since the browser's marker is removed", () => {
    const host = mount(() => <Fold summary="Rows">body</Fold>)
    const summary = host.querySelector("summary")!
    expect(summary.classList.contains("list-none")).toBe(true)
    expect(summary.querySelector('[data-slot="fold-chevron"] svg')).not.toBeNull()
  })
})
