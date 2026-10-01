import { createSignal, For, Show } from "solid-js"
import { Icon } from "@opencode/ui/icon"
import { FIVE_GATES, factsInClause, weakestOrigin, type GateLedgerEntry } from "../panes/evidence-ledger"
import { OriginTag } from "../panes/evidence-origin"
import { Block, Note, Pill, type Tone } from "./frame"
import { NextStepControl } from "./next-step"
import type { DiagnosisCardData } from "./readers"
import { show } from "./result"

/**
 * The diagnosis card - parity 5.17.
 *
 * Ported from the outgoing `DiagnosisCard.tsx`: the verdict, the engine's own
 * sentence, the five-gate ledger with the facts each gate read and the origin
 * of the weakest one, the claims the engine would not take on trust with the
 * control that settles each (`NextStepControl`), the moves that would change
 * the answer, and when to ask again. Nothing is paraphrased: the gate asks
 * its own question, the outcome is the engine's identifier.
 */

type VerdictLook = { word: string; tone: Tone; why: string }

/** Three verdicts reach a renderer, and each gets a hue for a stated reason. */
export const VERDICT: Record<string, VerdictLook> = {
  // Not a failure: "do not train" is the answer, and the finding is neither good nor bad news.
  NO_TRAIN: { word: "Do not train", tone: "info", why: "this is the answer, not a failure" },
  // Grey, because not knowing is an absence, not a problem the person caused.
  BLOCKED: { word: "Blocked", tone: "muted", why: "nothing has been decided yet" },
  TRAIN: { word: "Train", tone: "good", why: "all five gates passed" },
}

export function VerdictPill(props: { verdict: string }) {
  const look = () => VERDICT[props.verdict]
  return (
    <Show
      when={look()}
      fallback={
        <Pill tone="muted" title="The engine sent a verdict this surface has no treatment for.">
          {props.verdict || "no verdict"}
        </Pill>
      }
    >
      {(look) => (
        <Pill tone={look().tone} title={look().why}>
          {look().word}
        </Pill>
      )}
    </Show>
  )
}

export type RowState = "passed" | "blocked" | "not-started" | "unsubstantiated" | "not-reached"

/**
 * A gate row's state. FAILED on the wire splits three ways: facts that were
 * only claimed (`unsubstantiated` - the row a person can close), a clause
 * that names no fact anything has supplied (`not-started`), and a clause
 * that was tested and did not hold (`blocked`, the only red one).
 */
export function rowState(
  entry: GateLedgerEntry | undefined,
  origins: Record<string, string>,
  unsubstantiated: readonly string[] | undefined,
): RowState {
  if (!entry) return "not-reached"
  if (entry.status === "PASSED") return "passed"
  if (entry.status === "NOT_REACHED") return "not-reached"
  if (unsubstantiated?.length) return "unsubstantiated"
  if (entry.clause && factsInClause(entry.clause, origins).length === 0) return "not-started"
  return "blocked"
}

const LOOK: Record<RowState, { tone: Tone; icon: string; word: string }> = {
  passed: { tone: "good", icon: "check", word: "passed" },
  blocked: { tone: "bad", icon: "circle-exclamation", word: "blocked" },
  "not-started": { tone: "muted", icon: "chevron-right", word: "not started" },
  unsubstantiated: { tone: "muted", icon: "outline-eye", word: "unverified" },
  "not-reached": { tone: "muted", icon: "close", word: "not reached" },
}

const TONE_TEXT: Record<Tone, string> = {
  good: "text-v2-state-fg-success",
  bad: "text-v2-state-fg-danger",
  warn: "text-v2-state-fg-warning",
  info: "text-v2-state-fg-info",
  muted: "text-v2-text-text-faint",
}

export function DiagnosisBody(props: { data: DiagnosisCardData; threadId: number | undefined }) {
  const d = () => props.data
  const passed = () => FIVE_GATES.filter((gate) => d().gateLedger[gate.id]?.status === "PASSED").length
  const extra = () => Object.keys(d().gateLedger).filter((id) => !FIVE_GATES.some((gate) => gate.id === id))
  return (
    <>
      <div class="flex flex-wrap items-center gap-2">
        <VerdictPill verdict={d().verdict} />
        <span class="text-12-mono text-v2-text-text-muted" title={d().outcome}>
          {d().outcome}
        </span>
      </div>
      <Show
        when={d().say}
        fallback={<Note>The engine returned no note for this outcome, and nothing here writes one.</Note>}
      >
        <p class="text-[13px] text-v2-text-text-base">{d().say}</p>
      </Show>

      <Block title="Gate ledger" hint={`${passed()} of ${FIVE_GATES.length} passed`}>
        <div class="flex flex-col">
          <For each={FIVE_GATES}>{(gate, index) => <GateRow data={d()} gate={gate} index={index()} />}</For>
          <For each={extra()}>
            {(id) => (
              <div class="flex min-h-7 items-center gap-2 text-12-regular text-v2-text-text-muted">
                <Icon name="info" size="small" />
                <span class="text-12-mono">{id}</span>
                <span>a gate this surface has no wording for - {d().gateLedger[id].status}</span>
              </div>
            )}
          </For>
        </div>
      </Block>

      <Show when={d().unsubstantiated.length > 0}>
        <Block
          title={
            d().unsubstantiated.length === 1 ? "A claim I have not seen" : `${d().unsubstantiated.length} claims I have not seen`
          }
        >
          <div class="flex flex-col gap-3">
            <For each={d().unsubstantiated}>
              {(row) => (
                <div class="flex flex-col gap-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="text-12-mono text-v2-text-text-base">{row.fact}</span>
                    <OriginTag origin={row.origin} />
                    <Show when={row.declaredSource}>
                      <span class="text-12-regular text-v2-text-text-faint">declared source: {row.declaredSource}</span>
                    </Show>
                  </div>
                  <Show when={row.substantiation}>
                    <Note>{row.substantiation}</Note>
                  </Show>
                  <Show when={row.nextStep}>
                    {(step) => <NextStepControl step={step()} claimed={d().factsUsed[row.fact]} threadId={props.threadId} />}
                  </Show>
                </div>
              )}
            </For>
          </div>
        </Block>
      </Show>

      <Show when={d().alternatives.length > 0}>
        <Block title="What would move this">
          <ol class="flex list-decimal flex-col gap-1 pl-5">
            <For each={d().alternatives}>
              {(one) => (
                <li class="text-12-regular" classList={{ "text-v2-text-text-base": one.startsNow, "text-v2-text-text-muted": !one.startsNow }}>
                  <span>{one.text}</span>
                  <Show when={one.tool}>
                    <span class="text-12-mono text-v2-text-text-faint" title={one.why || undefined}>
                      {` ${one.verb ? `${one.verb} - ` : ""}${one.tool}${one.runAs === "user" ? " · your call" : ""}`}
                    </span>
                  </Show>
                </li>
              )}
            </For>
          </ol>
        </Block>
      </Show>

      <Show when={d().revisitIf.length > 0 || d().help}>
        <p class="flex items-start gap-1.5 text-12-regular text-v2-text-text-muted">
          <Icon name="refresh" size="small" />
          <span>
            {d().revisitIf.length ? `Ask again when ${d().revisitIf.join(", or when ")}.` : ""}
            {d().revisitIf.length && d().help ? " " : ""}
            {d().help ?? ""}
          </span>
        </p>
      </Show>
    </>
  )
}

function GateRow(props: { data: DiagnosisCardData; gate: (typeof FIVE_GATES)[number]; index: number }) {
  const [open, setOpen] = createSignal(false)
  const entry = () => props.data.gateLedger[props.gate.id]
  const challenged = () => props.data.unsubstantiatedByGate[props.gate.id] ?? []
  const state = () => rowState(entry(), props.data.factOrigins, challenged())
  const look = () => LOOK[state()]
  const facts = () => factsInClause(entry()?.clause ?? null, props.data.factOrigins)
  // A gate that never ran read nothing, so it gets no tag.
  const origin = () => (state() === "not-reached" ? null : weakestOrigin(facts(), props.data.factOrigins))
  return (
    <div class="flex flex-col">
      <button
        type="button"
        class="flex min-h-7 w-full items-center gap-2 rounded-sm text-left hover:bg-v2-overlay-simple-overlay-hover"
        aria-expanded={open()}
        onClick={() => setOpen(!open())}
      >
        <span class={TONE_TEXT[look().tone]}>
          <Icon name={look().icon} size="small" />
        </span>
        <span class="w-4 shrink-0 text-12-regular tabular-nums text-v2-text-text-faint">{props.index + 1}</span>
        <span class="min-w-0 flex-1 truncate text-[13px] text-v2-text-text-base">{props.gate.name}</span>
        <Show when={origin()}>{(origin) => <OriginTag origin={origin()} />}</Show>
        <Pill tone={look().tone}>{look().word}</Pill>
      </button>
      <Show when={open()}>
        <div class="flex flex-col gap-1 pb-2 pl-10">
          <p class="text-12-regular text-v2-text-text-muted">{props.gate.asks}</p>
          <Show
            when={entry()?.clause}
            fallback={
              <Note>
                Nothing below the block was evaluated, so this gate has no clause and no result. It is not failed and it is
                not passed.
              </Note>
            }
          >
            <p class="text-12-regular text-v2-text-text-muted">
              requires <code class="text-12-mono text-v2-text-text-base">{entry()!.clause}</code>
            </p>
          </Show>
          <For each={facts()}>
            {(name) => {
              const used = () => props.data.factsUsed[name]
              return (
                <div class="flex flex-wrap items-center gap-2 text-12-regular">
                  <span class="text-12-mono text-v2-text-text-base">{name}</span>
                  <Show
                    when={used()}
                    fallback={
                      <span class="text-v2-text-text-faint">nobody supplied it; the fact ledger's own default was used</span>
                    }
                  >
                    <span class="text-12-mono">{show(used()!.value)}</span>
                    <span class="text-v2-text-text-muted">{used()!.how}</span>
                  </Show>
                  <OriginTag origin={used()?.origin ?? props.data.factOrigins[name]} />
                </div>
              )
            }}
          </For>
          <Show when={challenged().length > 0}>
            <Note>
              {challenged().length === 1
                ? `${challenged()[0]} was claimed rather than measured. What would settle it is below the ledger.`
                : "These claims were not measured. What would settle them is below the ledger."}
            </Note>
          </Show>
        </div>
      </Show>
    </div>
  )
}
