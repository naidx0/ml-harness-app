import { render } from "solid-js/web"
import { afterEach, describe, expect, it, vi } from "vitest"
import { InstallLine } from "./install-line"
import { INSTALL_LINE } from "./setup"

let dispose: (() => void) | undefined
afterEach(() => {
  dispose?.()
  dispose = undefined
  document.body.innerHTML = ""
})

const tick = () => new Promise((resolve) => setTimeout(resolve, 0))

function mount() {
  const host = document.createElement("div")
  document.body.append(host)
  dispose = render(() => <InstallLine />, host)
  return host
}

describe("the install line", () => {
  it("is the README's line", () => {
    expect(INSTALL_LINE).toBe("irm https://raw.githubusercontent.com/naidx0/ml-harness-app/main/install.ps1 | iex")
    expect(mount().querySelector("code")?.textContent).toBe(INSTALL_LINE)
  })

  it("copies the line", async () => {
    const writeText = vi.fn(async () => undefined)
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true })
    const copy = mount().querySelector("button")!
    copy.click()
    await tick()
    expect(writeText).toHaveBeenCalledWith(INSTALL_LINE)
    expect(copy.textContent).toBe("Copied")
  })

  it("selects the line and says how to copy it when the clipboard refuses", async () => {
    const writeText = vi.fn(async () => {
      throw new Error("Write permission denied.")
    })
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true })
    const copy = mount().querySelector("button")!
    copy.click()
    await tick()
    await tick()
    expect(copy.textContent).toBe("Click the line, then Ctrl+C")
    expect(window.getSelection()?.toString()).toBe(INSTALL_LINE)
  })
})
