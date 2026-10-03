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
  dispose = render(() => <InstallLine line={INSTALL_LINE} />, host)
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

describe("the line for this computer", () => {
  const MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko)"
  const WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
  const LINUX = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)"

  it("reads the platform the way their platform layer does", async () => {
    const { hostOS } = await import("./setup")
    expect(hostOS(MAC)).toBe("macos")
    expect(hostOS(WIN)).toBe("windows")
    expect(hostOS(LINUX)).toBe("linux")
  })

  it("is the Terminal line on a Mac, the PowerShell line on Windows, and none on Linux", async () => {
    const { installFor, INSTALL_LINES } = await import("./setup")
    expect(installFor("macos")).toEqual({ line: INSTALL_LINES.macos, shell: "Terminal", apps: "Applications" })
    expect(INSTALL_LINES.macos).toBe("curl -fsSL https://raw.githubusercontent.com/naidx0/ml-harness-app/main/install.sh | sh")
    expect(installFor("windows")?.shell).toBe("PowerShell")
    expect(installFor("linux")).toBeUndefined()
  })

  it("names the line the README and the two scripts name", async () => {
    const { readFileSync } = await import("node:fs")
    const { resolve } = await import("node:path")
    const { INSTALL_LINES } = await import("./setup")
    const root = resolve(process.cwd(), "..")
    const readme = readFileSync(resolve(root, "README.md"), "utf-8")
    expect(readme).toContain(INSTALL_LINES.windows)
    expect(readme).toContain(INSTALL_LINES.macos)
    expect(readFileSync(resolve(root, "install.ps1"), "utf-8")).toContain(INSTALL_LINES.windows)
    expect(readFileSync(resolve(root, "install.sh"), "utf-8")).toContain(INSTALL_LINES.macos)
  })
})
