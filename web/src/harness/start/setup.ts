/**
 * The one line that sets up a local model, and the model it sets up.
 *
 * The same line the README gives a new user: it installs the app (skipped when
 * this version is already installed), Ollama when it is missing, pulls the
 * model below and connects it. So when the first screen finds no local model,
 * it offers exactly the line that fixes either cause - the PowerShell line on
 * Windows, the Terminal line on a Mac.
 */
export const DEFAULT_LOCAL_MODEL = "qwen3.5:4b"

export type HostOS = "windows" | "macos" | "linux"

export const INSTALL_LINES: Record<"windows" | "macos", string> = {
  windows: "irm https://raw.githubusercontent.com/naidx0/ml-harness-app/main/install.ps1 | iex",
  macos: "curl -fsSL https://raw.githubusercontent.com/naidx0/ml-harness-app/main/install.sh | sh",
}

/** The Windows line, kept under its old name for the callers that mean Windows. */
export const INSTALL_LINE = INSTALL_LINES.windows

/** Which computer this page runs on, the way their platform layer decides it (platform/tauri.ts). */
export function hostOS(agent: string = typeof navigator === "undefined" ? "" : navigator.userAgent): HostOS {
  const lower = agent.toLowerCase()
  if (lower.includes("mac os") || lower.includes("macintosh")) return "macos"
  if (lower.includes("windows")) return "windows"
  return "linux"
}

/** The line for this computer, and where a person types it. Linux has no build yet, so it gets none. */
export function installFor(os: HostOS): { line: string; shell: string; apps: string } | undefined {
  if (os === "macos") return { line: INSTALL_LINES.macos, shell: "Terminal", apps: "Applications" }
  if (os === "windows") return { line: INSTALL_LINES.windows, shell: "PowerShell", apps: "the Start menu" }
  return
}

/** What the start card read from this machine's Ollama. */
export type LocalRead = { models: { name: string }[]; error?: string }

/** Which one is missing: Ollama itself (it did not answer) or a pulled model. */
export function whatIsMissing(read: LocalRead | undefined): "ollama" | "model" | undefined {
  if (!read) return
  if (read.error !== undefined) return "ollama"
  if (read.models.length === 0) return "model"
  return
}
