import { createEffect, createSignal, onCleanup, onMount } from "solid-js"

/**
 * COLOUR HINTS need something to key on, and their markup does not say which
 * mode a chat is in or whether it is working: the agent chip is a plain
 * button whose label is the agent's name, and the session header is an
 * untagged <h1>. So the harness writes two attributes onto the surface that
 * holds the chat, and brand/identity.css draws the hints from them:
 *
 *   data-harness-mode     plan | build | measure | write | full
 *   data-harness-working  true | false
 *
 * Small hints, never filled colour (the owner, 2026-09-18: "small colour
 * hints are wanted - modes, effort levels, the ring, the goal glyph - never
 * filled colour").
 */

export const HARNESS_MODES = ["plan", "build", "measure", "write", "full"] as const
export type HarnessMode = (typeof HARNESS_MODES)[number]

/**
 * Their agent, as a harness mode. The facade names its agents after the
 * modes (app/facade/sessions.py `AGENTS`: plan, build, measure, write, full)
 * and their picker shows each one capitalised (catalog.agents `name`), so the
 * match is on the lowercased name. Anything else is not a mode and gets no
 * hint rather than a wrong one.
 */
export function modeOf(agent: string | undefined | null): HarnessMode | undefined {
  const name = agent?.trim().toLocaleLowerCase()
  return HARNESS_MODES.find((mode) => mode === name)
}

/**
 * Write the two attributes onto the element `find` picks, starting from a
 * hidden marker this component renders (so it takes no space in the layout
 * it sits in), and remove them when it unmounts.
 */
export function HarnessSurfaceMarks(props: {
  find: (marker: HTMLElement) => HTMLElement | null | undefined
  mode: () => string | undefined
  working?: () => boolean
}) {
  const [target, setTarget] = createSignal<HTMLElement>()
  let frame: number | undefined
  // The marker is connected by the time mount callbacks run; a frame later is
  // the fallback for a parent that inserts its children after that.
  const locate = (marker: HTMLElement) => {
    const found = props.find(marker)
    if (found) return setTarget(found)
    frame = requestAnimationFrame(() => {
      frame = undefined
      const late = props.find(marker)
      if (late) setTarget(late)
    })
  }
  let marker: HTMLSpanElement | undefined
  onMount(() => marker && locate(marker))
  createEffect(() => {
    const element = target()
    if (!element) return
    const mode = modeOf(props.mode())
    if (mode) element.dataset.harnessMode = mode
    else delete element.dataset.harnessMode
    if (props.working) element.dataset.harnessWorking = String(props.working())
  })
  onCleanup(() => {
    if (frame !== undefined) cancelAnimationFrame(frame)
    const element = target()
    if (!element) return
    delete element.dataset.harnessMode
    delete element.dataset.harnessWorking
  })
  return <span ref={marker} hidden aria-hidden="true" data-slot="harness-surface-marks" />
}
