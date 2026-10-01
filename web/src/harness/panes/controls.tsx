import { createEffect, createMemo, createSignal, For, Match, on, Show, Switch } from "solid-js"
import { createStore } from "solid-js/store"
import { Button } from "@opencode/ui/button"
import { Checkbox } from "@opencode/ui/checkbox"
import { Collapsible } from "@opencode/ui/collapsible"
import { Icon } from "@opencode/ui/icon"
import { Select } from "@opencode/ui/select"
import { TextInput } from "@opencode/ui/text-input"
import { Textarea } from "@opencode/ui/textarea"
import { harness } from "../engine"
import { ErrorLine, useHarnessRead } from "../ui"
import { PaneEmpty } from "../panel/frame"
import type { PaneProps } from "../panel/panes"
import { clearToolFocus, focusedTool } from "./controls-focus"
import {
  coerce,
  fieldKind,
  filterTools,
  groupTools,
  missingFields,
  outcomeHeading,
  outcomeOf,
  packOf,
  prettyResult,
  visibleFields,
  type RunOutcome,
  type ToolCatalogue,
  type ToolControl,
  type ToolField,
  type ToolRunAnswer,
} from "./controls-form"

/**
 * Every tool, run by hand.
 *
 * VISION.md: "The harness works by calling the same operations a person
 * could click. That is what makes the product survive a user whose local
 * model cannot do tool calling - the buttons are all still there." So this
 * pane has no list of tools in it. It renders whatever `GET /api/tools`
 * returns, and each form is built from the same JSON Schema the model is
 * handed (see controls-form.ts).
 *
 * A run goes through `POST /api/tools/{name}` - the user's door, where the
 * engine hard-codes the actor - carrying the open thread. With a thread, the
 * engine writes the same `tool.call` / `tool.result` pair a model's call
 * writes, marked "run by you", so the run is part of the conversation. With
 * none, nothing is filed and the result lives only here; the pane says which.
 *
 * Packs start collapsed. Max, 2026-09-12, on the outgoing dialog: "I want to
 * make sure it doesn't all come auto expanded". A search opens every pack
 * with a match, because a filter whose hits are folded away finds nothing.
 *
 * The result is shown as text. The rich cards the outgoing panel drew for a
 * diagnosis, a proposal, an eval report or a prompt attempt are a separate,
 * later task (docs/PARITY.md 5.20, registered in their tool-card registry so
 * the transcript and this pane share one design); until then a person still
 * gets the whole answer, just not drawn.
 */
export default function ControlsPane(props: PaneProps) {
  const catalogue = useHarnessRead<ToolCatalogue>(() => "/api/tools")
  const [query, setQuery] = createSignal("")
  const [openPacks, setOpenPacks] = createSignal<ReadonlySet<string>>(new Set())

  // Read through `.latest` once there is an answer, so a re-read does not
  // throw the whole pane back to the Suspense fallback. The error is checked
  // first because `.latest` rethrows it.
  const controls = createMemo(() => (catalogue.data.error ? [] : (catalogue.data.latest?.controls ?? [])))
  const groups = createMemo(() => groupTools(controls()))
  const shown = createMemo(() => filterTools(groups(), query()))
  const searching = () => query().trim().length > 0

  // Row state per tool, started afresh when the pane follows another
  // conversation: an answer filed under one thread is not this thread's.
  const [rows, setRows] = createSignal(new Map<string, RowState>())
  createEffect(on(() => props.threadId, () => setRows(new Map()), { defer: true }))
  const stateOf = (name: string) => {
    const held = rows()
    let state = held.get(name)
    if (!state) {
      state = createRowState()
      held.set(name, state)
    }
    return state
  }

  const setPack = (group: string, open: boolean) =>
    setOpenPacks((current) => {
      const next = new Set(current)
      if (open) next.add(group)
      else next.delete(group)
      return next
    })

  // A tool asked for from outside - a command, the journey - opens its pack
  // here and its row below. Consumed once, so closing the row afterwards is
  // the person's choice and not something the pane argues with.
  const [target, setTarget] = createSignal<{ name: string; seq: number }>()
  createEffect(() => {
    const wanted = focusedTool()
    const pack = wanted && packOf(groups(), wanted.name)
    if (!wanted || !pack) return
    setQuery("")
    setPack(pack, true)
    setTarget(wanted)
    clearToolFocus()
  })

  return (
    <Switch>
      <Match when={catalogue.data.error}>
        <ErrorLine error={catalogue.data.error} />
      </Match>
      {/* Before the catalogue answers, the search box read "Search 0 tools". */}
      <Match when={!catalogue.data.answered}>
        <PaneEmpty title="Reading…" />
      </Match>
      <Match when={controls().length === 0}>
        <PaneEmpty title="No tools">The engine reported no tools, so there is nothing to run by hand.</PaneEmpty>
      </Match>
      <Match when={true}>
        <div class="flex flex-col pb-4">
          <div class="flex flex-col gap-2 px-4 pt-1 pb-2">
            <TextInput
              type="search"
              class="!w-full"
              leadingIcon={<Icon name="magnifying-glass" size="small" />}
              placeholder={`Search ${controls().length} tools`}
              aria-label="Search tools"
              value={query()}
              onInput={(event) => setQuery(event.currentTarget.value)}
              showClearButton={searching()}
              clearLabel="Clear search"
              onClearClick={() => setQuery("")}
            />
            <div class="text-12-regular text-v2-text-text-muted">
              <Show
                when={props.threadId !== undefined}
                fallback="No conversation is open, so a run here is not filed anywhere: its result appears under its button and nowhere else."
              >
                A run here is written to this conversation as run by you - the same rows a model's call writes.
              </Show>
            </div>
          </div>

          <Show when={searching() && shown().length === 0}>
            <div class="px-4 py-2 text-[13px] text-v2-text-text-muted">No tool matches "{query().trim()}".</div>
          </Show>

          <For each={shown()}>
            {(group) => (
              <Collapsible
                variant="ghost"
                open={searching() || openPacks().has(group.group)}
                onOpenChange={(open) => setPack(group.group, open)}
              >
                <Collapsible.Trigger class="gap-1 px-2 text-[13px] [font-weight:530] text-v2-text-text-base">
                  <Collapsible.Arrow />
                  <span class="min-w-0 flex-1 truncate text-left">{group.group}</span>
                  <span class="shrink-0 pr-2 text-12-regular text-v2-text-text-faint tabular-nums">
                    {group.controls.length} tool{group.controls.length === 1 ? "" : "s"}
                  </span>
                </Collapsible.Trigger>
                <Collapsible.Content>
                  <For each={group.controls}>
                    {(control) => (
                      <ControlRow
                        control={control}
                        threadId={props.threadId}
                        target={target()?.name === control.name ? target()?.seq : undefined}
                        state={stateOf(control.name)}
                      />
                    )}
                  </For>
                </Collapsible.Content>
              </Collapsible>
            )}
          </For>

          <Show when={catalogue.data.latest?.instruction_set}>
            {(version) => <div class="px-4 pt-3 text-[11px] text-v2-text-text-faint">Instruction set {version()}</div>}
          </Show>
        </div>
      </Match>
    </Switch>
  )
}

/**
 * What a person has done to one tool's row: open or shut, what they typed,
 * the approval box, the last answer. Held by the pane, keyed by tool name,
 * rather than inside the row, because the row is unmounted whenever its pack
 * folds or a search filters it out - and typing a path, searching for
 * another tool and coming back to find the path gone is the form arguing
 * with the person.
 */
type RowState = {
  open: () => boolean
  setOpen: (open: boolean) => void
  values: Record<string, string>
  setValue: (name: string, value: string) => void
  approved: () => boolean
  setApproved: (approved: boolean) => void
  running: () => boolean
  setRunning: (running: boolean) => void
  outcome: () => RunOutcome | undefined
  setOutcome: (outcome: RunOutcome | undefined) => void
  badField: () => string | undefined
  setBadField: (message: string | undefined) => void
  /** The last focus request this row answered, so a remount does not scroll to it again. */
  handled: number | undefined
}

function createRowState(): RowState {
  const [open, setOpen] = createSignal(false)
  const [values, setValues] = createStore<Record<string, string>>({})
  const [approved, setApproved] = createSignal(false)
  const [running, setRunning] = createSignal(false)
  const [outcome, setOutcome] = createSignal<RunOutcome>()
  const [badField, setBadField] = createSignal<string>()
  return {
    open,
    setOpen,
    values,
    setValue: (name, value) => setValues(name, value),
    approved,
    setApproved,
    running,
    setRunning,
    outcome,
    setOutcome: (next) => setOutcome(() => next),
    badField,
    setBadField: (next) => setBadField(() => next),
    handled: undefined,
  }
}

function ControlRow(props: { control: ToolControl; threadId: number | undefined; target: number | undefined; state: RowState }) {
  let row: HTMLDivElement | undefined
  const state = () => props.state

  const fields = createMemo(() => visibleFields(props.control, props.threadId))
  const missing = createMemo(() => missingFields(fields(), state().values))
  const blocked = () =>
    state().running() || missing().length > 0 || (props.control.needs_approval && !state().approved())

  // Sent here from outside: open, bring into view, and put the caret in the
  // first thing still to fill. After a frame, because the fields do not
  // exist until the row's content has been drawn. The FIRST EMPTY field,
  // never a filled one: moving past an answer to the next blank is what a
  // person filling a form does anyway.
  createEffect(
    on(
      () => props.target,
      (seq) => {
        if (seq === undefined || state().handled === seq) return
        state().handled = seq
        state().setOpen(true)
        requestAnimationFrame(() => {
          row?.scrollIntoView({ block: "center" })
          const inputs = row?.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>(
            "input:not([type=checkbox]), textarea",
          )
          ;[...(inputs ?? [])].find((input) => !input.value)?.focus()
        })
      },
    ),
  )

  const run = async () => {
    const held = state()
    held.setBadField(undefined)
    let args: Record<string, unknown>
    try {
      args = coerce(fields(), held.values)
    } catch (failure) {
      held.setBadField(failure instanceof Error ? failure.message : String(failure))
      return
    }
    held.setRunning(true)
    try {
      const answer = await harness<ToolRunAnswer>(`/api/tools/${encodeURIComponent(props.control.name)}`, {
        body: { arguments: args, approved: held.approved(), thread_id: props.threadId ?? null },
      })
      held.setOutcome(outcomeOf(answer?.result))
    } catch (failure) {
      // 428 (approval missing), 400 (a thread is required, a malformed fact),
      // 404, 422: each carries the engine's own sentence, written for a person.
      held.setOutcome({ kind: "refused", error: failure instanceof Error ? failure.message : String(failure) })
    } finally {
      held.setRunning(false)
    }
  }

  return (
    <div ref={row}>
      <Collapsible variant="ghost" open={state().open()} onOpenChange={(open) => state().setOpen(open)}>
        <Collapsible.Trigger data-hide-details="true" class="items-start gap-1 py-1 pr-4 pl-6 text-left">
          <Collapsible.Arrow />
          <span class="flex min-w-0 flex-1 flex-col py-0.5">
            <span class="flex items-center gap-2">
              <span class="min-w-0 flex-1 truncate text-[13px] text-v2-text-text-base">{props.control.label}</span>
              <Show when={props.control.needs_approval}>
                <span class="shrink-0 rounded-sm px-1.5 py-px text-[11px] text-v2-state-fg-warning bg-v2-background-bg-layer-02">
                  needs approval
                </span>
              </Show>
            </span>
            <span class="truncate text-12-regular text-v2-text-text-muted">{props.control.verb}</span>
          </span>
        </Collapsible.Trigger>
        <Collapsible.Content>
          <div class="flex flex-col gap-3 pt-1 pr-4 pb-4 pl-12">
            <p class="text-12-regular text-v2-text-text-muted whitespace-pre-line">{props.control.description}</p>

            <For each={fields()}>
              {(field) => (
                <FieldInput
                  field={field}
                  value={state().values[field.name] ?? ""}
                  onChange={(next) => state().setValue(field.name, next)}
                />
              )}
            </For>

            <Show when={props.control.needs_approval}>
              <Checkbox checked={state().approved()} onChange={(checked: boolean) => state().setApproved(checked)}>
                <span class="text-[13px] text-v2-text-text-base">
                  I am approving this: <span class="text-[13px] [font-weight:530]">{props.control.verb}</span>.
                </span>
              </Checkbox>
            </Show>

            <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Button size="small" variant="contrast" disabled={blocked()} onClick={() => void run()}>
                {state().running() ? "Running" : "Run"}
              </Button>
              <Show when={missing().length > 0}>
                <span class="text-12-regular text-v2-text-text-muted">needs {missing().join(", ")}</span>
              </Show>
              <span class="text-12-regular text-v2-text-text-faint">
                reads {props.control.reads.length ? props.control.reads.join(", ") : "nothing"} · writes{" "}
                {props.control.writes.length ? props.control.writes.join(", ") : "nothing"}
              </span>
            </div>

            <Show when={state().badField()}>
              {(message) => <div class="text-[13px] text-v2-state-fg-danger">{message()}</div>}
            </Show>

            <Show when={state().outcome()}>{(result) => <ResultBlock outcome={result()} filed={props.threadId !== undefined} />}</Show>
          </div>
        </Collapsible.Content>
      </Collapsible>
    </div>
  )
}

/**
 * The answer, as text, folded open. A refusal from the engine is not called
 * a failure of the tool: the tool never ran, and the sentence says why.
 */
function ResultBlock(props: { outcome: RunOutcome; filed: boolean }) {
  const [open, setOpen] = createSignal(true)
  const text = () => (props.outcome.kind === "refused" ? props.outcome.error : prettyResult(props.outcome.result))
  const tone = () =>
    props.outcome.kind === "refused"
      ? "text-v2-state-fg-danger"
      : props.outcome.ok
        ? "text-v2-text-text-base"
        : "text-v2-state-fg-warning"
  return (
    <Collapsible variant="ghost" open={open()} onOpenChange={setOpen} class="rounded-md bg-v2-background-bg-layer-01">
      <Collapsible.Trigger class="gap-1 px-1">
        <Collapsible.Arrow />
        <span class={`flex-1 text-left text-12-medium ${tone()}`}>{outcomeHeading(props.outcome)}</span>
        <span class="pr-2 text-[11px] text-v2-text-text-faint">
          {props.outcome.kind === "refused" ? "nothing ran" : props.filed ? "in the conversation, run by you" : "not filed"}
        </span>
      </Collapsible.Trigger>
      <Collapsible.Content>
        <pre class="max-h-96 overflow-auto px-3 pb-3 text-12-mono whitespace-pre-wrap break-words text-v2-text-text-base select-text">
          {text()}
        </pre>
      </Collapsible.Content>
    </Collapsible>
  )
}

/** Leaving a choice to the engine is an answer too, so it is the first option rather than a blank. */
const ENGINE_DEFAULT = { value: "", label: "Leave to the engine" }

/** Ids that tie each label to its input, unique across every open row. */
let fieldIds = 0

function FieldInput(props: { field: ToolField; value: string; onChange: (next: string) => void }) {
  const label = () => `${props.field.name}${props.field.required ? "" : " (optional)"}`
  const kind = () => fieldKind(props.field)
  const id = `tool-field-${++fieldIds}`
  return (
    <div class="flex flex-col gap-1">
      <Switch>
        <Match when={kind() === "flag"}>
          <Checkbox checked={props.value === "true"} onChange={(checked: boolean) => props.onChange(checked ? "true" : "")}>
            <span class="text-12-mono text-v2-text-text-base">{label()}</span>
          </Checkbox>
        </Match>
        <Match when={kind() === "choice"}>
          <span class="text-12-mono text-v2-text-text-base">{label()}</span>
          {(() => {
            const options = [ENGINE_DEFAULT, ...(props.field.enum ?? []).map((value) => ({ value, label: value }))]
            return (
              <Select
                options={options}
                current={options.find((option) => option.value === props.value) ?? ENGINE_DEFAULT}
                value={(option) => option.value || "(engine default)"}
                label={(option) => option.label}
                onSelect={(option) => props.onChange(option?.value ?? "")}
                aria-label={props.field.name}
              />
            )
          })()}
        </Match>
        <Match when={kind() === "json"}>
          <label for={id} class="text-12-mono text-v2-text-text-base">
            {label()}
          </label>
          <Textarea
            id={id}
            class="!w-full font-mono"
            rows={3}
            spellcheck={false}
            placeholder={props.field.type === "object" ? "{ }" : "[ ]"}
            value={props.value}
            onInput={(event) => props.onChange(event.currentTarget.value)}
          />
        </Match>
        <Match when={true}>
          <label for={id} class="text-12-mono text-v2-text-text-base">
            {label()}
          </label>
          <TextInput
            id={id}
            class="!w-full"
            type={kind() === "number" ? "number" : "text"}
            numeric={kind() === "number"}
            spellcheck={false}
            value={props.value}
            onInput={(event) => props.onChange(event.currentTarget.value)}
          />
        </Match>
      </Switch>
      <Show when={props.field.description || kind() === "json"}>
        <span class="text-12-regular text-v2-text-text-muted">
          {props.field.description}
          <Show when={kind() === "json"}>
            {props.field.description ? " " : ""}Written as JSON, because this parameter is {props.field.type === "array" ? "a list" : "an object"} in the
            tool's own schema.
          </Show>
        </span>
      </Show>
    </div>
  )
}
