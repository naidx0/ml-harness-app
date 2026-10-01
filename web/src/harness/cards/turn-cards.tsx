import { createEffect, createMemo, createSignal, For, onCleanup, Show, type Accessor } from "solid-js"
import { Button } from "@opencode/ui/button"
import { harness } from "../engine"
import { Block, Note, Pill } from "./frame"
import { HARNESS_CARD_TOOL_NAMES } from "./kinds"
import { foldRepeats, type PlanChange, type PlanTick } from "./readers"
import { baseName } from "./result"
import { refreshThreadEvents, threadEvents } from "./thread-events"
import { effectsFor, planChangeFor, type TurnEffects } from "./turn-log"

/**
 * The two cards that read the thread's log rather than their own result:
 * the plan diff (parity 5.20) and what changed this turn (parity 5.19).
 */

const CARD_TOOLS: ReadonlySet<string> = new Set(HARNESS_CARD_TOOL_NAMES)

/** How long a card keeps asking for a turn that has not ended: two minutes at 3s. */
const POLL_MS = 3000
const POLL_LIMIT = 40

/**
 * This card's view of the log: its plan diff and whether it carries the
 * turn's effects. While the turn is still running the answer is `pending`,
 * and the shared log is re-read on a bounded interval until it is not.
 */
export function useTurnLog(threadId: Accessor<number | undefined>, callID: Accessor<string>, tool: Accessor<string>) {
  const events = createMemo(() => {
    const id = threadId()
    return id === undefined ? undefined : threadEvents(id)()
  })
  const effects = createMemo<TurnEffects>(() => {
    const log = events()
    return log ? effectsFor(log, callID(), CARD_TOOLS, tool()) : { state: "none" }
  })
  const plan = createMemo<PlanChange | null>(() => {
    const log = events()
    return log ? planChangeFor(log, callID(), tool()) : null
  })
  // A boolean memo, so the poll below is started and stopped by the answer
  // changing - not restarted (and its bound reset) by every re-read of the log.
  const pending = createMemo(() => threadId() !== undefined && (events() === undefined || effects().state === "pending"))
  createEffect(() => {
    const id = threadId()
    // A log not read yet, or a turn not ended yet: keep asking, bounded.
    if (id === undefined || !pending()) return
    let asked = 0
    const timer = setInterval(() => {
      asked += 1
      if (asked > POLL_LIMIT) return clearInterval(timer)
      void refreshThreadEvents(id, POLL_MS - 500)
    }, POLL_MS)
    onCleanup(() => clearInterval(timer))
  })
  return { effects, plan, refresh: () => threadId() !== undefined && refreshThreadEvents(threadId()!, 0) }
}

/** The lines of a plan that changed, both line numbers, the way the outgoing `PlanDiff` drew them. */
export function PlanDiff(props: { change: PlanChange }) {
  return (
    <details>
      <summary class="flex cursor-pointer list-none items-center gap-2 text-12-regular">
        <Show when={props.change.added}>
          <span class="tabular-nums text-v2-state-fg-success">+{props.change.added}</span>
        </Show>
        <Show when={props.change.removed}>
          <span class="tabular-nums text-v2-state-fg-danger">-{props.change.removed}</span>
        </Show>
        <span class="text-v2-text-text-muted">see what changed</span>
      </summary>
      <div class="mt-1 overflow-x-auto rounded-md bg-v2-background-bg-layer-01 py-1">
        <For each={props.change.rows}>
          {(row) => (
            <div
              class="flex min-w-0 gap-2 px-2 text-12-mono"
              classList={{
                "text-v2-state-fg-success": row.kind === "add",
                "text-v2-state-fg-danger": row.kind === "del",
                "text-v2-text-text-muted": row.kind === "ctx",
              }}
            >
              <span class="w-6 shrink-0 text-right tabular-nums text-v2-text-text-faint">{row.old ?? ""}</span>
              <span class="w-6 shrink-0 text-right tabular-nums text-v2-text-text-faint">{row.cur ?? ""}</span>
              <span class="w-3 shrink-0">{row.kind === "add" ? "+" : row.kind === "del" ? "-" : ""}</span>
              <span class="min-w-0 flex-1 truncate" title={row.text}>
                {row.text || " "}
              </span>
            </div>
          )}
        </For>
        <Show when={props.change.clipped}>
          <p class="px-2 pt-1 text-12-regular text-v2-text-text-faint">
            {props.change.clipped} more line{props.change.clipped === 1 ? "" : "s"} changed, not shown here. The plan file on disk
            has all of it.
          </p>
        </Show>
      </div>
    </details>
  )
}

/** What a plan tool answered, and the diff it wrote. */
export function PlanBody(props: { tick: PlanTick; change: PlanChange | null }) {
  const t = () => props.tick
  return (
    <>
      <p class="text-[13px] text-v2-text-text-base">
        {t().ticked ? `Ticked: ${t().ticked}` : t().step ? `Back to open: ${t().step}` : "Plan saved"}
      </p>
      <Show when={t().done !== null && t().of !== null}>
        <Note>
          {t().done} of {t().of} steps done
        </Note>
      </Show>
      <Show when={props.change}>{(change) => <PlanDiff change={change()} />}</Show>
      <Show when={t().next}>
        <Note>{t().next}</Note>
      </Show>
      <Show when={t().openSteps.length > 0 && !t().next}>
        <Block title="Still open">
          <ul class="flex list-disc flex-col pl-5 text-12-regular text-v2-text-text-muted">
            <For each={t().openSteps.slice(0, 6)}>{(step) => <li class="truncate">{step}</li>}</For>
          </ul>
        </Block>
      </Show>
    </>
  )
}

type Row = { key: string; sign: "+" | "-"; kind: string; summary: string; detail?: string; title?: string }

/**
 * What changed this turn - parity 5.19. Ported from the outgoing
 * `WhatChangedCard.tsx`: ticks, parks, a rewritten plan, facts stamped (a
 * repeated stamp folded with a count), files written; and "Revert ticks",
 * which restores the plan from before the turn and leaves ledger facts alone
 * (`POST /api/threads/{id}/effects/{eid}/revert`, app/effects.py).
 */
export function WhatChanged(props: {
  threadId: number
  effectsId: number
  effects: Found["effects"]
  reverted: boolean
  onReverted: () => void
}) {
  const [busy, setBusy] = createSignal(false)
  const [note, setNote] = createSignal<string>()
  const [expanded, setExpanded] = createSignal(false)

  const rows = createMemo<Row[]>(() => {
    const e = props.effects
    const out: Row[] = []
    for (const step of e.stepsDone) out.push({ key: `d-${step}`, sign: "+", kind: "Ticked", summary: step, title: step })
    for (const row of e.stepsParked) {
      out.push({ key: `p-${row.step}`, sign: "-", kind: "Parked", summary: row.step, detail: row.why ? `parked: ${row.why}` : undefined })
    }
    if (e.planWrites > 0) out.push({ key: "plan", sign: "+", kind: "Plan", summary: "rewritten with write_plan" })
    for (const { fact, times } of foldRepeats(e.facts)) {
      const words = fact.fact.trim().split(/\s+/)
      const short = words.slice(0, 6).join(" ")
      out.push({
        key: `f-${fact.fact}-${fact.tool}`,
        sign: "+",
        kind: "Fact",
        summary: `${words.length > 6 ? `${short}…` : short} · ${(fact.origin || "inferred").toLowerCase()}${times > 1 ? ` ×${times}` : ""}`,
        detail: [fact.fact, fact.tool ? `via ${fact.tool}${times > 1 ? `, run ${times} times this turn` : ""}` : "", fact.how]
          .filter(Boolean)
          .join(" - "),
      })
    }
    for (const path of e.files) out.push({ key: `file-${path}`, sign: "+", kind: "File", summary: baseName(path), detail: path })
    return out
  })
  const visible = () => (expanded() ? rows() : rows().slice(0, 3))

  const revert = async () => {
    setBusy(true)
    setNote(undefined)
    try {
      await harness(`/api/threads/${props.threadId}/effects/${props.effectsId}/revert`, { body: {} })
      setNote("Plan ticks restored. Ledger facts were left alone.")
      props.onReverted()
    } catch (failure) {
      setNote(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-label="What changed this turn" class="flex flex-col gap-1 rounded-md bg-v2-background-bg-layer-01 px-3 py-2">
      <div class="flex items-center gap-2">
        <h4 class="flex-1 text-12-medium text-v2-text-text-muted">What changed</h4>
        <Show when={props.reverted}>
          <Pill tone="muted">ticks reverted</Pill>
        </Show>
        <Show when={props.effects.canRevert && !props.reverted}>
          <Button
            size="small"
            variant="ghost"
            icon="reset"
            disabled={busy()}
            title="Restore plan/todo ticks from before this turn. Does not delete ledger facts."
            onClick={() => void revert()}
          >
            {busy() ? "Reverting…" : "Revert ticks"}
          </Button>
        </Show>
      </div>
      <For each={visible()}>
        {(row) => (
          <Show
            when={row.detail}
            fallback={<RowLine row={row} />}
          >
            <details>
              <summary class="cursor-pointer list-none">
                <RowLine row={row} />
              </summary>
              <p class="pl-16 text-12-regular text-v2-text-text-muted break-words">{row.detail}</p>
            </details>
          </Show>
        )}
      </For>
      <Show when={rows().length > 3}>
        <div>
          <Button size="small" variant="ghost" onClick={() => setExpanded(!expanded())}>
            {expanded() ? "Show less" : `Show ${rows().length - 3} more`}
          </Button>
        </div>
      </Show>
      <Show when={note()}>
        <Note>{note()}</Note>
      </Show>
    </section>
  )
}

function RowLine(props: { row: Row }) {
  return (
    <div class="flex min-h-6 min-w-0 items-center gap-2 text-12-regular" title={props.row.title}>
      <span
        class="w-3 shrink-0 text-center"
        classList={{ "text-v2-state-fg-success": props.row.sign === "+", "text-v2-text-text-faint": props.row.sign === "-" }}
        aria-hidden="true"
      >
        {props.row.sign}
      </span>
      <span class="w-12 shrink-0 text-v2-text-text-muted">{props.row.kind}</span>
      <span class="min-w-0 flex-1 truncate text-v2-text-text-base">{props.row.summary}</span>
    </div>
  )
}

type Found = Extract<TurnEffects, { state: "found" }>

const foundOf = (effects: TurnEffects): Found | undefined => (effects.state === "found" ? effects : undefined)

/** The footer every harness card carries; it draws only on the turn's last card. */
export function TurnEffectsFooter(props: { threadId: number | undefined; effects: TurnEffects; onReverted: () => void }) {
  return (
    <Show when={props.threadId !== undefined ? foundOf(props.effects) : undefined}>
      {(found) => (
        <WhatChanged
          threadId={props.threadId!}
          effectsId={found().effectsId}
          effects={found().effects}
          reverted={found().reverted}
          onReverted={props.onReverted}
        />
      )}
    </Show>
  )
}
