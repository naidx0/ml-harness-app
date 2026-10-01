import { createSignal } from "solid-js"

/**
 * Which tool the Controls pane should open on, set from outside it.
 *
 * A module-level signal rather than a prop because the thing that wants a
 * tool focused - a palette command, the journey's "do this step", a card's
 * next-step chip - is nowhere near the pane in the component tree, and the
 * pane may not be mounted yet. The caller sets it and opens the pane; the
 * pane opens that tool's pack and row when it next reads its tools.
 *
 * Each request carries a sequence number, so asking for the same tool twice
 * in a row still moves the pane back to it after a person has scrolled away.
 */

export type ToolFocus = { name: string; seq: number }

const [focus, setFocus] = createSignal<ToolFocus | undefined>(undefined)
let seq = 0

export function focusTool(name: string) {
  seq += 1
  setFocus({ name, seq })
}

/** The pending request, or undefined. */
export const focusedTool = focus

export function clearToolFocus() {
  setFocus(undefined)
}
