import { createEffect } from "solid-js"
import type { TimelineDetail } from "@opencode/session-ui/timeline/detail"
import { useSettings } from "@/settings/model"
import { useCommand } from "@/shell/commands/command"
import { useLanguage } from "@/runtime/i18n/language"
import { tabLayoutCommand } from "./rail/layout"

/**
 * Harness defaults applied to their settings, once per install.
 *
 * Mounted as an entry child, inside their `SettingsProvider`. Their defaults
 * are right for their product and wrong in a few places for this one; every
 * one of these is a setting a person can change back, so each set is applied
 * ONCE, recorded, and never re-asserted over a choice someone made. A new set
 * gets a new key, so an install that took an earlier set still takes the new
 * one - once.
 *
 * v1
 *   - The agent picker is hidden by default (`showCustomAgents: false`), and
 *     when hidden their composer forces the agent to "build"
 *     (`providers/models/selection.tsx`). In the harness the agents ARE the
 *     modes - plan, build, measure, write, full - so hiding the picker would
 *     hide Plan mode and three of the four permission levels.
 *   - Their titlebar has a terminal button. The harness has no terminal
 *     surface (the engine answers `pty.*` empty and the emulator is a stub),
 *     so the button would open a panel that can only fail.
 *
 * v2 - the owner's identity inside their layout
 *   - The interface font. Their settings write `--font-family-sans` as an
 *     INLINE style on the root from `appearance.sans`, falling back to Inter,
 *     so the IBM Plex Sans declared in brand/identity.css never applied -
 *     found by reading why the text did not look like the harness. The
 *     setting itself now names IBM Plex Sans.
 *   - The vertical tab layout: their resizable left sidebar, which is where
 *     the harness session rail lives, with project names on the tabs.
 *
 * v3 - the model's thinking, live (2026-09-23)
 *   - Their default timeline is Compact, which GROUPS thinking: while the
 *     model thinks, it sits inside a collapsed "Used ..." row, and their live
 *     Thinking row is never built (session-ui timeline/projection.ts builds
 *     it only for placement "separate"). The sparkle and the capped live body
 *     the owner asked for that day were two clicks deep. Thinking gets its own
 *     row, still collapsed; the other five categories stay as they were, and
 *     a person who hid thinking or already shows it keeps their choice.
 */
export function withLiveThinking(detail: TimelineDetail): TimelineDetail {
  if (detail.thinking.placement !== "grouped") return detail
  return { ...detail, thinking: { placement: "separate", details: "collapsed" } }
}

export const HARNESS_DEFAULT_SETS: { key: string; apply: (settings: ReturnType<typeof useSettings>) => void }[] = [
  {
    key: "harness.defaults.v1",
    apply: (settings) => {
      settings.general.setShowCustomAgents(true)
      settings.general.setShowTerminal(false)
    },
  },
  {
    key: "harness.defaults.v2",
    apply: (settings) => {
      settings.appearance.setUIFont("IBM Plex Sans")
      settings.appearance.setTabLayout("vertical")
      settings.appearance.setShowProjectName(true)
    },
  },
  {
    key: "harness.defaults.v3",
    apply: (settings) => {
      settings.general.setTimelineDetail(withLiveThinking(settings.general.timelineDetail()))
    },
  },
]

function taken(key: string) {
  try {
    return localStorage.getItem(key) === "1"
  } catch {
    // Storage refused (a private window, a locked profile): applying on
    // every launch is the harmless direction to fail in.
    return false
  }
}

function record(key: string) {
  try {
    localStorage.setItem(key, "1")
  } catch {
    // See above.
  }
}

export function HarnessRoot() {
  const settings = useSettings()
  const language = useLanguage()

  // Tabs across the top or the session rail, one key from anywhere (the
  // owner, 2026-09-23; rail/layout.ts). Here because this root is mounted in
  // both layouts, and the rail only in one.
  useCommand().register("harness.layout", () => [
    tabLayoutCommand(settings, language.t("command.category.view")),
  ])

  createEffect(() => {
    if (!settings.ready()) return
    for (const set of HARNESS_DEFAULT_SETS) {
      if (taken(set.key)) continue
      set.apply(settings)
      record(set.key)
    }
  })

  return null
}
