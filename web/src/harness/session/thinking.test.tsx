import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { createSignal } from "solid-js"
import { render } from "solid-js/web"
import { afterEach, describe, expect, it, vi } from "vitest"
import { DialogProvider } from "@opencode/ui/context/dialog"
import { AssistantReasoningContent } from "@opencode/session-ui/message-part"

/**
 * THE THINKING BLOCK (scripts/vendor_opencode.py P30-P31). The owner,
 * 2026-09-23: click anywhere on the open thinking to minimise it, since it
 * "keeps infinitely scrolling up"; and an icon for it - "a spinning icon or a
 * flashing sparkly icon". The motion and the height cap are CSS
 * (brand/identity.css), which happy-dom does not lay out; this holds the
 * markup they key on and the click - including that a double-click, which
 * selects a word, does not close it.
 */

let dispose: (() => void) | undefined
afterEach(() => {
  dispose?.()
  dispose = undefined
  window.getSelection()?.removeAllRanges()
  document.body.innerHTML = ""
})

/**
 * Streaming markdown projects in a Worker, which happy-dom has none of; the
 * streaming mark and the sparkle are both on the trigger, so those cases
 * mount it closed.
 */
function mount(streaming: boolean, initiallyOpen = !streaming) {
  const host = document.createElement("div")
  document.body.append(host)
  const [open, setOpen] = createSignal(initiallyOpen)
  const changes: boolean[] = []
  const onOpenChange = vi.fn((value: boolean) => {
    changes.push(value)
    setOpen(value)
  })
  dispose = render(
    () => (
      <DialogProvider>
        <AssistantReasoningContent
          id="prt_thinking"
          content={{ type: "reasoning", text: "Weighing the two chunkings first.", time: { created: 0 } } as never}
          streaming={streaming}
          open={open()}
          onOpenChange={onOpenChange}
        />
      </DialogProvider>
    ),
    host,
  )
  const part = () => host.querySelector<HTMLElement>('[data-component="reasoning-part"]')!
  const body = () => host.querySelector<HTMLElement>('[data-slot="harness-reasoning-body"]')
  return { part, body, open, changes }
}

/**
 * A click as the browser numbers it: `detail` is 1 for a single click and 2
 * for the second click of a double-click (the one that selects a word).
 */
function clickBody(target: HTMLElement, detail: number) {
  target.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, detail }))
}

/**
 * THE CLOSE WAITS OUT A DOUBLE-CLICK. The first click of a double-click is an
 * ordinary detail-1 click; closing on it would take the words away before the
 * second click could select one. So a single click closes only once a second
 * could no longer follow, and every case here runs the clock past that point
 * before it asserts - a case that asserted at once would pass on a block that
 * never closes at all.
 */
const PAST_A_DOUBLE_CLICK = 1_000

describe("the thinking block", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it("closes on a click anywhere in its open body", () => {
    const view = mount(false)
    vi.useFakeTimers()
    expect(view.body()).not.toBeNull()
    view.body()!.click()
    vi.advanceTimersByTime(PAST_A_DOUBLE_CLICK)
    expect(view.changes).toEqual([false])
    expect(view.open()).toBe(false)
  })

  it("closes on a single click (detail 1), once a double-click can no longer follow", () => {
    const view = mount(false)
    vi.useFakeTimers()
    clickBody(view.body()!, 1)
    expect(view.open()).toBe(true)
    vi.advanceTimersByTime(PAST_A_DOUBLE_CLICK)
    expect(view.changes).toEqual([false])
  })

  it("stays open on the second click of a double-click (detail 2)", () => {
    const view = mount(false)
    vi.useFakeTimers()
    clickBody(view.body()!, 2)
    vi.advanceTimersByTime(PAST_A_DOUBLE_CLICK)
    expect(view.changes).toEqual([])
    expect(view.open()).toBe(true)
  })

  it("stays open through a whole double-click (detail 1, then 2)", () => {
    const view = mount(false)
    vi.useFakeTimers()
    clickBody(view.body()!, 1)
    vi.advanceTimersByTime(120)
    clickBody(view.body()!, 2)
    vi.advanceTimersByTime(PAST_A_DOUBLE_CLICK)
    expect(view.changes).toEqual([])
    expect(view.open()).toBe(true)
  })

  it("stays open when the click ended a text selection", () => {
    const view = mount(false)
    vi.useFakeTimers()
    const range = document.createRange()
    range.selectNodeContents(view.body()!)
    window.getSelection()!.addRange(range)
    expect(window.getSelection()!.isCollapsed).toBe(false)
    view.body()!.click()
    vi.advanceTimersByTime(PAST_A_DOUBLE_CLICK)
    expect(view.changes).toEqual([])
    expect(view.open()).toBe(true)
  })

  it("stays open when the click is on a link or button inside it", () => {
    const view = mount(false)
    vi.useFakeTimers()
    const link = document.createElement("a")
    view.body()!.append(link)
    link.click()
    vi.advanceTimersByTime(PAST_A_DOUBLE_CLICK)
    expect(view.changes).toEqual([])
  })

  it("is marked while it streams, and not after", () => {
    expect(mount(true).part().getAttribute("data-harness-streaming")).toBe("true")
    dispose?.()
    document.body.innerHTML = ""
    expect(mount(false).part().hasAttribute("data-harness-streaming")).toBe(false)
  })

  it("draws the sparkle before its title, streaming or done", () => {
    for (const streaming of [true, false]) {
      expect(sparkle(streaming), `streaming=${streaming}`).toBe("models")
    }
  })
})

/** The icon the block draws, by the name in its sprite reference. */
function sparkle(streaming: boolean) {
  const view = mount(streaming)
  const icon = view.part().querySelector('[data-slot="basic-tool-tool-info-main"] > [data-harness-reasoning-icon]')
  const name = icon?.querySelector("use")?.getAttribute("href")?.replace("#opencode-v2-icon-", "")
  dispose?.()
  dispose = undefined
  document.body.innerHTML = ""
  return name
}

/**
 * ONE ICON SET (panel/panes.ts, checked the same way in panel/panes.test.ts):
 * the sparkle is a v2 icon their older set does not shadow. The name is read
 * from what the block renders, not typed here.
 */
describe("the sparkle's icon set", () => {
  const ICONS = resolve(process.cwd(), "..", "node_modules", "@opencode", "ui", "src", "icons", "icon")
  const keysOf = (source: string, start: string) => {
    const body = source.slice(source.indexOf(start))
    return new Set([...body.matchAll(/^\s+"?([a-z0-9-]+)"?:/gm)].map((match) => match[1]))
  }
  const v2 = keysOf(readFileSync(resolve(ICONS, "additional-icons.ts"), "utf-8"), "export const additionalIcons = {")
  const older = keysOf(readFileSync(resolve(ICONS, "icon.tsx"), "utf-8"), "const icons = {")

  it("reads both lists (a control: plus is in the older set)", () => {
    expect(v2.size).toBeGreaterThan(50)
    expect(older.has("plus")).toBe(true)
  })

  it("is a v2 icon the older set does not shadow", () => {
    const name = sparkle(true)!
    expect(v2.has(name)).toBe(true)
    expect(older.has(name)).toBe(false)
  })
})
