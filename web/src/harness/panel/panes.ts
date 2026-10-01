import type { Component, ComponentProps } from "solid-js"
import type { Icon } from "@opencode/ui/icon"

/**
 * The harness's own surfaces, as side-panel tabs.
 *
 * Each is a tab id `harness:<id>` in OpenCode's own per-session tab list
 * (patches P1-P8 in scripts/vendor_opencode.py), so it opens, closes,
 * reorders, resizes and remembers its width exactly like their review and
 * file tabs. A pane is a component of `{ threadId }` built only from their UI
 * library and the harness client, so the same component renders in a pop-out
 * window with no session around it.
 *
 * Order is the order of the "+" menu: the surfaces a person reaches for most
 * first (docs/PARITY.md, "most often").
 */

export const HARNESS_TAB_PREFIX = "harness:"

export type PaneProps = { threadId: number | undefined }

type IconName = ComponentProps<typeof Icon>["name"]

/**
 * ONE ICON SET. Every icon on a harness panel comes from their v2 set
 * (`additionalIcons` in @opencode/ui): the 20-unit, square-capped strokes
 * their own side-panel tabs draw ("bubble-5" on BTW, "file-tree" on Open
 * file). Never a name their older 16-unit set also defines - that set wins
 * the lookup, so the icon would draw in the other weight. A pane's one icon
 * is used in its tab label, the "+" menu, its header and its pop-out window.
 * `panes.test.ts` holds both rules against the library's own source.
 */
export const POP_OUT_ICON: IconName = "square-arrow-top-right"

export type PaneSpec = {
  id: string
  title: string
  /** One line for the "+" menu, so a pane can be found by what it is for. */
  hint: string
  icon: IconName
  load: () => Promise<{ default: Component<PaneProps> }>
}

export const HARNESS_PANES: PaneSpec[] = [
  { id: "plan", title: "Plan", hint: "The plan and its steps; run it", icon: "checklist", load: () => import("../panes/plan") },
  { id: "stage", title: "Stage", hint: "Bench, sandbox, gates, retrieval", icon: "console", load: () => import("../panes/stage") },
  { id: "journey", title: "Journey", hint: "The guided route for this chat", icon: "arrow-right", load: () => import("../panes/journey") },
  // The owner, 2026-09-22: "I don't like the agent icon; the machine icon is
  // better." So Agents takes the plain unit Machine drew ("server"), and
  // Machine the chip - its GPU and memory are what that pane is about. The
  // monitor beside a chat's title, which he also named, is in their older
  // 16-unit set only, which panes.test.ts keeps off the panel.
  { id: "agents", title: "Agents", hint: "Sub-agents at work", icon: "monitor", load: () => import("../panes/agents") },
  { id: "eval", title: "Eval", hint: "Scores, intervals, failing rows", icon: "glasses", load: () => import("../panes/eval") },
  { id: "evidence", title: "Evidence", hint: "The gate ledger and its sources", icon: "shield", load: () => import("../panes/evidence") },
  { id: "memory", title: "Memory", hint: "What the project and you are known for", icon: "brain", load: () => import("../panes/memory") },
  { id: "machine", title: "Machine", hint: "GPU, memory, disk, with provenance", icon: "providers", load: () => import("../panes/machine") },
]

/**
 * CONTEXT IS NOT A PANEL TAB. Their context ring in the session header opens
 * their own "context" tab, and that module is substituted (SUBSTITUTES in
 * web/vite.config.ts) by the harness view, extended with the readouts theirs
 * showed (panel/context-tab.tsx). One view, one way in: so it is not in the
 * "+" menu or the palette. The spec stays for the view's header and for its
 * pop-out window, which has no session and shows the harness part alone.
 */
export const CONTEXT_PANE: PaneSpec = {
  id: "context",
  title: "Context",
  hint: "What the model sees; compact",
  icon: "prompt",
  load: () => import("../panes/context"),
}

/** Every pane a pop-out window can show: the panel tabs and Context. */
export const windowPaneOf = (id: string) => [...HARNESS_PANES, CONTEXT_PANE].find((pane) => pane.id === id)

export function paneOf(tab: string): PaneSpec | undefined {
  if (!tab.startsWith(HARNESS_TAB_PREFIX)) return
  const id = tab.slice(HARNESS_TAB_PREFIX.length)
  return HARNESS_PANES.find((pane) => pane.id === id)
}

export const tabOf = (id: string) => `${HARNESS_TAB_PREFIX}${id}`

/**
 * The harness thread behind an OpenCode session. The facade puts it on the
 * session's metadata because a session id minted by their client cannot be
 * decoded back to a thread.
 */
export function threadIdOf(session: unknown): number | undefined {
  const value = (session as { metadata?: { harness?: { threadID?: unknown } } } | undefined)?.metadata?.harness
    ?.threadID
  const id = typeof value === "string" ? Number(value) : value
  return typeof id === "number" && Number.isFinite(id) ? id : undefined
}
