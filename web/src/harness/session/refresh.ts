import { HARNESS_CHANGED_EVENT, type HarnessChange } from "../ui"

/**
 * WHAT THE SESSION TELLS ITS PANES, so they re-read when the engine did
 * something instead of on a clock.
 *
 * The facade's stream carries every thread's events to every window
 * (app/facade/translate.py). The session mount already hears it; this picks
 * the events that change what a pane shows, keeps only the ones for THIS
 * session, and says so on `window` as `harness:changed` {threadId, kind}.
 * Panes subscribe with `useHarnessRefresh` (ui.tsx).
 *
 * Which events, and why each:
 *
 *   harness.<kind>        - an engine event their protocol has no word for,
 *                           passed through as written (`_pass_through`):
 *                           eval.started/progress/finished/interrupted/reused,
 *                           train.*, subagent.*, run.*, thread.step_done. The
 *                           kind is the engine's own. `harness.ui.open` is an
 *                           instruction, not a change, and is left out.
 *   session.tool.success  - a tool result (`_on_tool_result`), which is where
 *                           an eval report, a diagnosis or a recorded fact
 *                           lands. Sent as kind `tool.result`, the engine's word.
 *   session.step.ended    - a step of a turn closed (`_end_step`): the context
 *                           window has grown. Sent as kind `step.ended`.
 *
 * An event is this session's when it names this session (`sessionID`) or
 * this session's harness thread (`threadID`), the rule `uiOpenTab` uses.
 */

const RENAMED: Readonly<Record<string, string>> = {
  "session.tool.success": "tool.result",
  "session.step.ended": "step.ended",
}

const NOT_A_CHANGE = new Set(["harness.ui.open"])

export function harnessChangeOf(
  event: unknown,
  here: { sessionID?: string; threadID?: number },
): HarnessChange | undefined {
  if (here.threadID === undefined) return undefined
  const record = event as { type?: unknown; data?: { sessionID?: unknown; threadID?: unknown } } | null
  const type = record?.type
  if (typeof type !== "string" || NOT_A_CHANGE.has(type)) return undefined
  const kind = type.startsWith("harness.") ? type.slice("harness.".length) : RENAMED[type]
  if (!kind) return undefined
  const data = record?.data
  const bySession = !!here.sessionID && data?.sessionID === here.sessionID
  const byThread = data?.threadID === here.threadID
  return bySession || byThread ? { threadId: here.threadID, kind } : undefined
}

/** Says a change on `target` (the window), and whether there was one to say. */
export function rebroadcastHarnessChange(
  event: unknown,
  here: { sessionID?: string; threadID?: number },
  target: EventTarget = window,
): boolean {
  const change = harnessChangeOf(event, here)
  if (!change) return false
  target.dispatchEvent(new CustomEvent<HarnessChange>(HARNESS_CHANGED_EVENT, { detail: change }))
  return true
}
