import { createSignal } from "solid-js"
import { Button } from "@opencode/ui/button"
import { hostOS, INSTALL_LINE, installFor } from "./setup"

/**
 * The one install line, with a Copy button.
 *
 * A refused clipboard write (a webview can deny it) says how to copy by hand
 * - one click on the line selects all of it - instead of doing nothing.
 */
export function InstallLine(props: { line?: string }) {
  const text = () => props.line ?? installFor(hostOS())?.line ?? INSTALL_LINE
  const [copied, setCopied] = createSignal<"copied" | "selected">()
  let line: HTMLElement | undefined
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text())
      setCopied("copied")
    } catch {
      const range = document.createRange()
      if (line) range.selectNodeContents(line)
      window.getSelection()?.removeAllRanges()
      window.getSelection()?.addRange(range)
      setCopied("selected")
    }
  }
  return (
    <div
      data-slot="install-line"
      class="flex w-full items-center gap-2 rounded-[8px] bg-v2-background-bg-layer-02 px-2 py-1 text-left"
    >
      <code ref={line} class="min-w-0 flex-1 select-all break-all font-mono text-[12px] text-v2-text-text-base">
        {text()}
      </code>
      <Button size="small" variant="neutral" onClick={() => void copy()}>
        {copied() === "copied"
          ? "Copied"
          : copied() === "selected"
            ? `Click the line, then ${hostOS() === "macos" ? "Cmd" : "Ctrl"}+C`
            : "Copy"}
      </Button>
    </div>
  )
}
