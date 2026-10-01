/**
 * The Memory pane's text rules, mirrored from the engine so the count beside
 * each box is the number the engine will hold the save to.
 *
 * `app/memory.py::set_text` splits the text on `§`, collapses whitespace in
 * each entry, drops empty ones, and joins them with a newline, `§` and a
 * newline - Hermes' own delimiter - before comparing the length with the
 * limit. Counting the raw box instead would show "2,150 / 2,200" on a text
 * the engine then refuses as over, or refuse nothing while the counter reads
 * red, because blank lines and stray spaces are counted by one and not the
 * other.
 */

export type MemoryTarget = "project" | "user"

export const TARGETS: MemoryTarget[] = ["project", "user"]

export type MemoryBlock = {
  entries: { id: number; content: string; created_at: string; updated_at: string }[]
  /** The block as one `§`-delimited text - the pane's edit form. */
  text: string
  used: number
  limit: number
}

export type MemoryRead = Record<MemoryTarget, MemoryBlock>

/** `PUT /api/memory`. Refused whole, with `detail`, when an entry breaks the engine's number rule or the limit. */
export type MemorySaved = { ok: boolean; detail?: string; error?: string; count?: number; used?: number; limit?: number }

/** Hermes' limits, used only until the engine has said its own (`LIMITS` in app/memory.py). */
export const DEFAULT_LIMITS: Record<MemoryTarget, number> = { project: 2200, user: 1375 }

export const TITLE: Record<MemoryTarget, string> = {
  project: "This project knows",
  user: "About you",
}

export const EMPTY: Record<MemoryTarget, string> = {
  project:
    "Nothing yet. The model writes here when it learns something durable about this project - a decision, a ruled-out option, where the data lives. You can too.",
  user: "Nothing yet. How you like to work, what you already know, what to stop asking you.",
}

const DELIMITER = "\n§\n"

/** Entries as the engine will store them. */
export function entriesOf(text: string): string[] {
  return text
    .split("§")
    .map((part) => part.split(/\s+/).filter(Boolean).join(" "))
    .filter(Boolean)
}

/**
 * Characters the engine will count for this text. Counted in code points,
 * because Python's `len` counts code points and JavaScript's `length` counts
 * UTF-16 units - an emoji is one to the engine and two to a naive count.
 */
export function memoryUse(text: string): number {
  return [...entriesOf(text).join(DELIMITER)].length
}

export function overLimit(text: string, limit: number): boolean {
  return memoryUse(text) > limit
}
