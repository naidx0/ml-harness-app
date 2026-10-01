import { onCleanup, onMount } from "solid-js"
import { dismissToast, showToast } from "@/shell/notifications/toast"
import { tauriInvoke } from "../../platform/tauri"
import { harness } from "../engine"
import {
  classify,
  failingChecks,
  identityOf,
  readingOfFailure,
  type Health,
  type Identity,
  type Liveness,
  type Reading,
} from "./liveness"

/**
 * The engine notice, as their toast.
 *
 * The outgoing app had a strip under its top bar for this. Their interface has
 * no global strip, and their titlebar slot is absent in the vertical-tabs
 * layout, so the notice uses the one surface present in every layout: a
 * persistent toast with the action that fixes the problem. It appears only
 * when something is wrong and replaces itself when the state changes.
 *
 * Checked every 15 seconds and whenever the window comes back into view - the
 * moment a person is most likely to act on something stale.
 */
const EVERY = 15_000

export function EngineNotice() {
  let first: Identity | undefined
  let shown: { state: Liveness; toast: number } | undefined

  const reload = () => window.location.reload()
  const start = async () => {
    const invoke = tauriInvoke()
    if (invoke) await invoke("start_engine").catch(() => undefined)
    reload()
  }

  const present = (state: Liveness, reading: Reading | undefined) => {
    if (shown?.state === state) return
    if (shown) dismissToast(shown.toast)
    shown = undefined
    if (state === "ok") return
    const toast =
      state === "gone"
        ? showToast({
            variant: "error",
            title: "The harness engine is not answering",
            description: "It may have stopped or crashed. Anything running in it is paused until it is back.",
            persistent: true,
            actions: tauriInvoke()
              ? [{ label: "Start the engine", onClick: () => void start() }]
              : [{ label: "Reload", onClick: reload }],
          })
        : state === "not-ready"
          ? // Up, but one of its own checks failed. "Start the engine" would be
            // wrong advice - it is running - so the toast names what failed.
            showToast({
              variant: "error",
              title: "The engine is running but not ready",
              description: notReadyLine(reading),
              persistent: true,
              actions: [{ label: "Reload", onClick: reload }],
            })
          : showToast({
              title: "The engine restarted",
              description: "Reload the window to reconnect with its new session.",
              persistent: true,
              actions: [{ label: "Reload", onClick: reload }],
            })
    shown = { state, toast }
  }

  const check = async () => {
    const reading: Reading | undefined = await harness<Health>("/health").then(
      (health) => ({ status: 200, health }),
      (failure: unknown) => readingOfFailure(failure),
    )
    const state = classify(first, reading)
    if (reading && !first) first = identityOf(reading.health)
    present(state, reading)
  }

  onMount(() => {
    void check()
    const timer = setInterval(() => void check(), EVERY)
    const onVisible = () => {
      if (document.visibilityState === "visible") void check()
    }
    document.addEventListener("visibilitychange", onVisible)
    window.addEventListener("focus", onVisible)
    onCleanup(() => {
      clearInterval(timer)
      document.removeEventListener("visibilitychange", onVisible)
      window.removeEventListener("focus", onVisible)
    })
  })

  return null
}

/** The not-ready toast's details: the engine's failing checks, in its words. */
export function notReadyLine(reading: Reading | undefined): string {
  const failing = failingChecks(reading?.health)
  const named = failing.map((check) => (check.detail ? `${check.name}: ${check.detail}` : check.name)).join("; ")
  return named
    ? `Failing: ${named}. Settings > Engine lists every check.`
    : "One of its own health checks failed. Settings > Engine lists every check."
}
