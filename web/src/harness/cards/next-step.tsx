import { createResource, createSignal, For, Show } from "solid-js"
import { Button } from "@opencode/ui/button"
import { harness, HarnessError } from "../engine"
import {
  coerce,
  missingFields,
  outcomeOf,
  visibleFields,
  type RunOutcome,
  type ToolCatalogue,
  type ToolControl,
  type ToolRunAnswer,
} from "../panes/controls-form"
import { OriginTag } from "../panes/evidence-origin"
import { isRecord, show } from "./result"
import type { FactUsed, NextStep } from "./readers"

/**
 * The control that settles a claim - parity 5.17's "next step".
 *
 * Ported from the outgoing `NextStep.tsx`. A claim the engine would not take
 * on trust comes with the tool that would measure it; this is that tool as a
 * button. A tool with no required argument runs at once; one with required
 * arguments opens the smallest form that fills them, built from the same
 * `GET /api/tools` declaration the Controls pane reads (`controls-form.ts`),
 * so nothing here knows what any tool does. It runs through the user's door,
 * `POST /api/tools/{name}`, where the engine records the actor as the person.
 */

let catalogue: Promise<ToolCatalogue> | undefined

/** The tool catalogue, read once per window and shared by every card. */
function toolCatalogue(): Promise<ToolCatalogue> {
  catalogue ??= harness<ToolCatalogue>("/api/tools").catch((failure: unknown) => {
    catalogue = undefined
    throw failure
  })
  return catalogue
}

function sentence(verb: string): string {
  return verb ? verb.charAt(0).toUpperCase() + verb.slice(1) : "Run it"
}

type Recorded = { fact: string; value: unknown; origin: string; note: string }

function readRecorded(result: unknown): Recorded[] {
  if (!isRecord(result) || !Array.isArray(result.recorded)) return []
  return result.recorded.filter(isRecord).flatMap((row) =>
    typeof row.fact === "string"
      ? [{ fact: row.fact, value: row.value, origin: typeof row.origin === "string" ? row.origin : "", note: typeof row.if_not === "string" ? row.if_not : "" }]
      : [],
  )
}

function readDetail(result: unknown): string | null {
  if (!isRecord(result)) return null
  for (const key of ["summary", "detail", "help", "error"]) {
    const value = result[key]
    if (typeof value === "string" && value) return value
  }
  return null
}

export function NextStepControl(props: { step: NextStep; claimed?: FactUsed; threadId: number | undefined }) {
  const [tools] = createResource(() => props.step.tool ?? undefined, async (name) => {
    const all = await toolCatalogue().catch(() => undefined)
    return all?.controls.find((control) => control.name === name) ?? null
  })
  const [phase, setPhase] = createSignal<"closed" | "form" | "confirm" | "running" | "done">("closed")
  const [values, setValues] = createSignal<Record<string, string>>({})
  const [outcome, setOutcome] = createSignal<RunOutcome>()
  const [bad, setBad] = createSignal<string>()

  const control = (): ToolControl | null => tools.latest ?? null
  const required = () => {
    const found = control()
    return found ? visibleFields(found, props.threadId).filter((field) => field.required) : []
  }
  const label = () => sentence(props.step.verb || control()?.verb || "")

  /**
   * A tool that wants a person's yes (`needs_approval`) is asked twice, as
   * Journey and Controls ask: the first press shows what will run, and only
   * "Yes, run it" sends `approved: true`. A button that sent it by itself
   * would launder the approval. An engine that answers 428 to an unapproved
   * run (the catalogue did not load, or did not say) gets the same ask.
   */
  const [confirmedFrom, setConfirmedFrom] = createSignal<"closed" | "form">("closed")
  const asksFirst = () => control()?.needs_approval === true

  const run = async (approved = false) => {
    setBad(undefined)
    let args: Record<string, unknown>
    try {
      // `state_facts` takes `facts: {name: value}` and the step already names
      // the fact, so the person answers one question rather than writing JSON.
      // Derived from the schema and the step, never from the tool's name.
      const factField = (field: { type: string }) => field.type === "object" && !!props.step.fact
      args = coerce(
        required().filter((field) => !factField(field)),
        values(),
      )
      for (const field of required()) {
        if (factField(field)) {
          const raw = (values()[field.name] ?? "").trim()
          const scalar = /^(true|yes)$/i.test(raw)
            ? true
            : /^(false|no)$/i.test(raw)
              ? false
              : raw !== "" && Number.isFinite(Number(raw))
                ? Number(raw)
                : raw
          args[field.name] = { [props.step.fact]: scalar }
        }
      }
    } catch (failure) {
      setBad(failure instanceof Error ? failure.message : String(failure))
      return
    }
    if (!approved && asksFirst()) {
      setConfirmedFrom(phase() === "form" ? "form" : "closed")
      setPhase("confirm")
      return
    }
    const from = phase() === "form" ? "form" : phase() === "confirm" ? confirmedFrom() : "closed"
    setPhase("running")
    try {
      const answer = await harness<ToolRunAnswer>(`/api/tools/${encodeURIComponent(props.step.tool!)}`, {
        body: { arguments: args, approved, thread_id: props.threadId ?? null },
      })
      setOutcome(outcomeOf(answer?.result))
    } catch (failure) {
      if (!approved && failure instanceof HarnessError && failure.status === 428) {
        setConfirmedFrom(from)
        setPhase("confirm")
        return
      }
      setOutcome({ kind: "refused", error: failure instanceof Error ? failure.message : String(failure) })
    }
    setPhase("done")
  }

  return (
    <Show
      when={props.step.tool}
      fallback={<p class="text-12-regular text-v2-text-text-muted">{props.step.note ?? "Nothing in this harness measures this yet."}</p>}
    >
      <div class="flex flex-col gap-1.5">
        <div class="flex flex-wrap items-center gap-2">
          <Button
            size="small"
            variant="neutral"
            disabled={phase() === "running"}
            onClick={() => {
              // No required argument: the button IS the run. Otherwise the
              // smallest form that fills them - still a control that starts
              // the work, never a page of advice.
              if (required().length === 0) return void run()
              setPhase(phase() === "form" ? "closed" : "form")
            }}
          >
            {label()}
          </Button>
          <span class="text-12-mono text-v2-text-text-muted">{props.step.tool}</span>
          <Show when={props.step.runAs === "user"}>
            <span
              class="text-12-regular text-v2-text-text-faint"
              title="Facts you record here count as STATED - your own word. The same facts from a model count as ASSERTED and open nothing."
            >
              in your own person
            </span>
          </Show>
        </div>
        <Show when={props.step.also.length}>
          <p class="text-12-regular text-v2-text-text-faint">also measured by {props.step.also.join(", ")}</p>
        </Show>
        <Show when={phase() === "form"}>
          <div class="flex flex-col gap-1.5 rounded-md bg-v2-background-bg-layer-01 px-3 py-2">
            <Show when={props.claimed}>
              {(claimed) => (
                <p class="flex flex-wrap items-center gap-1.5 text-12-regular text-v2-text-text-muted">
                  <span class="text-12-mono">{props.step.fact}</span> was given as
                  <span class="text-12-mono text-v2-text-text-base">{show(claimed().value)}</span>
                  <OriginTag origin={claimed().origin} />
                  <span>{claimed().how}</span>
                </p>
              )}
            </Show>
            <For each={required()}>
              {(field) => (
                <label class="flex flex-col gap-0.5">
                  <span class="text-12-mono text-v2-text-text-muted">
                    {field.type === "object" && props.step.fact ? props.step.fact : field.name}
                  </span>
                  <input
                    class="w-full rounded-md bg-v2-background-bg-layer-02 px-2 py-1 text-[13px] text-v2-text-text-base outline-none placeholder:text-v2-text-text-faint"
                    placeholder={field.description}
                    value={values()[field.name] ?? ""}
                    onInput={(event) => setValues((current) => ({ ...current, [field.name]: event.currentTarget.value }))}
                    onKeyDown={(event) => event.stopPropagation()}
                  />
                </label>
              )}
            </For>
            <Show when={bad()}>
              <p class="text-12-regular text-v2-state-fg-danger">{bad()}</p>
            </Show>
            <div class="flex items-center gap-2">
              <Button
                size="small"
                variant="submit"
                disabled={missingFields(required(), values()).length > 0}
                onClick={() => void run()}
              >
                Run it
              </Button>
              <Button size="small" variant="ghost" onClick={() => setPhase("closed")}>
                Cancel
              </Button>
            </div>
          </div>
        </Show>
        <Show when={phase() === "confirm"}>
          <div data-slot="next-step-confirm" class="flex flex-col gap-1.5 rounded-md bg-v2-background-bg-layer-01 px-3 py-2">
            <p class="text-12-regular text-v2-text-text-base">
              This one asks first. It will run <span class="text-12-mono">{props.step.tool}</span>
              {required().length ? ` with ${required().map((field) => field.name).join(", ")} as you gave them.` : "."}
            </p>
            <div class="flex items-center gap-2">
              <Button size="small" variant="submit" onClick={() => void run(true)}>
                Yes, run it
              </Button>
              <Button size="small" variant="ghost" onClick={() => setPhase(confirmedFrom())}>
                Not now
              </Button>
            </div>
          </div>
        </Show>
        <Show when={phase() === "running"}>
          <p class="text-12-regular text-v2-text-text-muted">
            Running <span class="text-12-mono">{props.step.tool}</span> on this machine.
          </p>
        </Show>
        <Show when={phase() === "done" ? outcome() : undefined}>{(done) => <Outcome outcome={done()} />}</Show>
      </div>
    </Show>
  )
}

/** What the run said, in the engine's words, with the origin it gave each row it recorded. */
function Outcome(props: { outcome: RunOutcome }) {
  const outcome = props.outcome
  if (outcome.kind === "refused") return <p class="text-12-regular text-v2-state-fg-danger">{outcome.error}</p>
  return (
    <div class="flex flex-col gap-1">
      <p class="text-12-regular" classList={{ "text-v2-text-text-base": outcome.ok, "text-v2-state-fg-danger": !outcome.ok }}>
        {readDetail(outcome.result) ??
          (outcome.ok ? "The tool ran and reported nothing to record." : "The tool refused, and sent no reason this surface can read.")}
      </p>
      <For each={readRecorded(outcome.result)}>
        {(row) => (
          <p class="flex flex-wrap items-center gap-1.5 text-12-regular">
            <span class="text-12-mono">{row.fact}</span>
            <span class="text-12-mono">{show(row.value)}</span>
            <OriginTag origin={row.origin} />
            <Show when={row.note}>
              <span class="text-v2-text-text-muted">{row.note}</span>
            </Show>
          </p>
        )}
      </For>
    </div>
  )
}
