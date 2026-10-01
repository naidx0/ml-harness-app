/**
 * What a tool card needs from the thread's event log that its own result
 * does not carry: the plan diff its call wrote, and the turn's side effects.
 *
 * Neither rides on the tool part. `write_plan`, `mark_step_done` and
 * `unpark_step` write their diff onto a `thread.*` event between the call and
 * the result (app/tools/planning.py), and the conductor writes `turn.effects`
 * once per turn, after the last tool and before `stream.end`
 * (app/conductor.py). So a card finds its own `tool.result` row in the log
 * and reads around it. Pure: the log comes in, the answer goes out, and the
 * fetching is `thread-events.ts`'s job.
 */

import type { ThreadEvent } from "../panes/eval-events"
import { readEffects, readPlanChange, type Effects, type PlanChange } from "./readers"
import { isRecord } from "./result"

const PLAN_EVENTS = new Set(["thread.plan_written", "thread.step_done", "thread.step_parked", "thread.step_unparked"])
/** Rows that mean the turn is over, whichever way it ended. */
const TURN_ENDS = new Set(["stream.end", "turn.started", "turn.refused", "turn.crashed"])

const payloadOf = (event: ThreadEvent) => (isRecord(event.payload) ? event.payload : {})

/**
 * The index of this call's `tool.result` row, or -1.
 *
 * The facade names a call by the engine's own call id, and when the engine
 * wrote none, by `call_<row id>` of whichever row it drew the call from - the
 * call row or, for a result whose call it never saw, the result row itself
 * (`Translator._on_tool_result`). All three are honoured.
 */
export function resultIndexOf(events: readonly ThreadEvent[], callID: string, tool?: string): number {
  if (!callID) return -1
  const byId = events.findIndex((event) => event.kind === "tool.result" && payloadOf(event).id === callID)
  if (byId !== -1) return byId
  const minted = /^call_(\d+)$/.exec(callID)
  if (!minted) return -1
  const rowId = Number(minted[1])
  const at = events.findIndex((event) => event.id === rowId)
  if (at === -1) return -1
  if (events[at].kind === "tool.result") return at
  if (events[at].kind !== "tool.call") return -1
  const name = tool ?? payloadOf(events[at]).name
  for (let i = at + 1; i < events.length; i += 1) {
    if (events[i].kind === "tool.result" && payloadOf(events[i]).name === name) return i
  }
  return -1
}

/**
 * The plan diff this call wrote, or null. Read backwards from the result to
 * the call (or to the turn's start), because the plan event is written inside
 * the tool, before its result.
 */
export function planChangeFor(events: readonly ThreadEvent[], callID: string, tool?: string): PlanChange | null {
  const at = resultIndexOf(events, callID, tool)
  if (at === -1) return null
  for (let i = at - 1; i >= 0; i -= 1) {
    const event = events[i]
    if (event.kind === "tool.call" && payloadOf(event).id === callID) break
    if (TURN_ENDS.has(event.kind)) break
    if (PLAN_EVENTS.has(event.kind)) {
      const change = readPlanChange(event.payload)
      if (change) return change
    }
  }
  return null
}

/**
 * Would this result draw a harness card? A tool that answered `ok: false`
 * is drawn as their error card, which has no footer, so it cannot carry the
 * turn's effects - the same rule the facade applies (`harness_metadata`).
 */
function drawsACard(event: ThreadEvent, cardTools: ReadonlySet<string>): boolean {
  const payload = payloadOf(event)
  if (event.kind !== "tool.result" || payload.ok === false) return false
  if (isRecord(payload.result) && payload.result.ok === false) return false
  return cardTools.has(String(payload.name ?? ""))
}

export type TurnEffects =
  /** The turn has not ended yet; ask again. */
  | { state: "pending" }
  /** Nothing to draw here: no effects, another card is the anchor, or the call is not in the log. */
  | { state: "none" }
  | { state: "found"; effectsId: number; effects: Effects; reverted: boolean }

/**
 * The turn's side effects, if THIS card is the one that draws them.
 *
 * One `turn.effects` row per turn, and one card should carry it: the last
 * harness card of the turn, which is where the outgoing transcript drew its
 * What-changed card (after the last tool row). Every earlier card in the same
 * turn answers `none`, so a turn that ticked three steps shows one block, not
 * three copies of it.
 */
export function effectsFor(
  events: readonly ThreadEvent[],
  callID: string,
  cardTools: ReadonlySet<string>,
  tool?: string,
): TurnEffects {
  const at = resultIndexOf(events, callID, tool)
  if (at === -1) return { state: "none" }
  for (let i = at + 1; i < events.length; i += 1) {
    const event = events[i]
    if (drawsACard(event, cardTools)) return { state: "none" }
    if (event.kind === "turn.effects") {
      const effects = readEffects(event.payload)
      if (effects.empty) return { state: "none" }
      const reverted = events.some(
        (other) => other.kind === "turn.effects_reverted" && Number(payloadOf(other).effects_id) === event.id,
      )
      return { state: "found", effectsId: event.id, effects, reverted }
    }
    if (TURN_ENDS.has(event.kind)) return { state: "none" }
  }
  return { state: "pending" }
}
