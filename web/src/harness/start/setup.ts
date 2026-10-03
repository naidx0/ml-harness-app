/**
 * The one line that sets up a local model, and the model it sets up.
 *
 * The same line the README gives a new user: it installs the app (skipped when
 * this version is already installed), Ollama when it is missing, pulls the
 * model below and connects it. So when the first screen finds no local model,
 * it offers exactly the line that fixes either cause.
 */
export const DEFAULT_LOCAL_MODEL = "qwen3.5:4b"

export const INSTALL_LINE = "irm https://raw.githubusercontent.com/naidx0/ml-harness-app/main/install.ps1 | iex"

/** What the start card read from this machine's Ollama. */
export type LocalRead = { models: { name: string }[]; error?: string }

/** Which one is missing: Ollama itself (it did not answer) or a pulled model. */
export function whatIsMissing(read: LocalRead | undefined): "ollama" | "model" | undefined {
  if (!read) return
  if (read.error !== undefined) return "ollama"
  if (read.models.length === 0) return "model"
  return
}
