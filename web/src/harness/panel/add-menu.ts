import type { PaneSpec } from "./panes"

/**
 * What the side panel's one "+" offers (patch P8): their "Open file" first,
 * then the harness panels, all filtered by one search. Kept apart from the
 * drawing so the rule is testable without a menu.
 *
 * Their "Browser" entry is not here: the harness has no browser pane.
 */
export type AddEntry = { kind: "file" } | { kind: "pane"; pane: PaneSpec }

/** Words the "Open file" entry is found by, beside its label. */
export const OPEN_FILE_WORDS = "open file browse project files tree"

export function addEntries(query: string, fileLabel: string, panes: readonly PaneSpec[]): AddEntry[] {
  const q = query.trim().toLowerCase()
  const matches = (text: string) => !q || text.toLowerCase().includes(q)
  const file: AddEntry[] = matches(`${fileLabel} ${OPEN_FILE_WORDS}`) ? [{ kind: "file" }] : []
  return [...file, ...panes.filter((pane) => matches(`${pane.title} ${pane.hint}`)).map((pane) => ({ kind: "pane" as const, pane }))]
}
