/**
 * What the window shows while its engine comes up - and if it cannot.
 *
 * Plain DOM, drawn before Solid mounts, because the whole point is that the
 * interface is not mounted yet: their app needs a server to render anything,
 * and the server is what is being waited for. On a machine that already ran
 * the harness this is on screen for well under a second. On the first run the
 * shell provisions Python, which takes minutes, so the line says so rather
 * than leaving a blank window that looks broken.
 *
 * It is NOT a connect screen. There is nothing to type and nothing to choose;
 * the only control is "Try again", and only when starting failed.
 */

const STYLE = `
.mlh-start{position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;
  font-family:"IBM Plex Sans",ui-sans-serif,system-ui,"Segoe UI",sans-serif;font-size:13px;
  background:#1f1f1d;color:#d8d4ca}
@media (prefers-color-scheme: light){.mlh-start{background:#f7f4ed;color:#3a3833}}
.mlh-start img{width:40px;height:40px;opacity:.9}
.mlh-start p{margin:0;max-width:46ch;text-align:center;line-height:1.5}
.mlh-start .mlh-detail{opacity:.65;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;white-space:pre-wrap}
.mlh-start button{font:inherit;padding:6px 14px;border-radius:6px;border:1px solid currentColor;background:transparent;color:inherit;cursor:pointer}
.mlh-start button:focus-visible{outline:2px solid currentColor;outline-offset:2px}
@media (prefers-reduced-motion: no-preference){.mlh-start .mlh-dot{animation:mlh-pulse 1.4s ease-in-out infinite}}
@keyframes mlh-pulse{50%{opacity:.35}}
`

export function showStarting(root: HTMLElement, mark: string) {
  const style = document.createElement("style")
  style.textContent = STYLE
  const screen = document.createElement("div")
  screen.className = "mlh-start"
  screen.setAttribute("role", "status")
  screen.setAttribute("aria-live", "polite")
  const logo = document.createElement("img")
  logo.src = mark
  logo.alt = ""
  const line = document.createElement("p")
  line.className = "mlh-dot"
  line.textContent = "Opening your workspace"
  const detail = document.createElement("p")
  detail.className = "mlh-detail"
  screen.append(logo, line, detail)
  root.append(style, screen)

  return {
    progress(message: string) {
      line.className = "mlh-dot"
      line.textContent = message
      detail.textContent = ""
    },
    failed(message: string, retry: () => void) {
      line.className = ""
      line.textContent = "The harness engine did not start."
      detail.textContent = message
      const button = document.createElement("button")
      button.type = "button"
      button.textContent = "Try again"
      button.onclick = () => {
        button.remove()
        retry()
      }
      screen.append(button)
      button.focus()
    },
    remove() {
      style.remove()
      screen.remove()
    },
  }
}
