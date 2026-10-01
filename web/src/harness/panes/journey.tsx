import { createMemo, createSignal, For, Index, Show } from "solid-js"
import { Button } from "@opencode/ui/button"
import { Icon } from "@opencode/ui/icon"
import { TextInput } from "@opencode/ui/text-input"
import { harness } from "../engine"
import { PaneEmpty } from "../panel/frame"
import type { PaneProps } from "../panel/panes"
import { ErrorLine, kindIn, useHarnessRead, useHarnessRefresh } from "../ui"
import { useOpenToolControls } from "../settings/controls-open"
import {
  argumentsFor,
  pct,
  refusalOf,
  stamp,
  stateInWords,
  stillMissing,
  toolLabel,
  type BlockedBy,
  type JourneyOutcome,
  type JourneyPayload,
  type JourneyStep,
  type JourneyVerdict,
  type ToolField,
} from "./journey-model"

/**
 * The route this conversation is on, and the one thing next.
 *
 * `GET /api/threads/{id}/journey` (app/journey.py). The playbook's routes are
 * ordered tool steps; before this overview every step was reachable only by
 * knowing which of the harness's tools to reach for. The pane picks a route
 * (`POST .../journey`), draws each step's state in the engine's own words, and
 * runs the step that can be pressed through `POST /api/tools/{name}` - the
 * person's door, the same one Controls uses, so the run is filed under this
 * conversation and the route learns what happened because the transcript did.
 *
 * NOT POLLED. A journey moves when a tool runs, and the tools this pane runs
 * re-read it when they answer. A step the model runs in the conversation
 * re-reads it too: the session says so (`harness:changed`, session/refresh.ts)
 * on a tool result, a finished step, an eval or a training job, as the
 * outgoing pane re-read on the thread's events. A pop-out hears no session
 * and keeps "Refresh".
 *
 * WHERE "FILL IN" WENT. The outgoing pane opened Controls on the step's tool
 * with the record's values filled in. A pane cannot open another pane from a
 * pop-out, so the missing fields are asked for here, beside the step, and the
 * call goes through the same door with the record's values and the typed ones.
 */

/** Reads a resource without falling over or flashing. Reading one in its
 *  error state throws, and a pane that re-reads on a timer must survive one
 *  failed poll; and `resource()` suspends on every re-read, which inside the
 *  panel's Suspense would swap the whole pane for "Opening..." every three
 *  seconds. `latest` suspends only on the first read. */
function settled<T>(resource: { latest: T | undefined; error?: unknown }): T | undefined {
  return resource.error ? undefined : resource.latest
}

function say(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

type RunStep = (step: JourneyStep, args: Record<string, unknown>, approved: boolean) => Promise<{ ok: boolean; detail?: string }>

export default function JourneyPane(props: PaneProps) {
  return (
    <Show
      when={props.threadId}
      keyed
      fallback={
        <PaneEmpty title="No conversation open">
          Start a conversation, or pick one in the sidebar, and this shows the route it is on, which step is next, and
          what is blocking it.
        </PaneEmpty>
      }
    >
      {(threadId) => <JourneyForThread threadId={threadId} />}
    </Show>
  )
}

function JourneyForThread(props: { threadId: number }) {
  const id = props.threadId
  const journey = useHarnessRead<JourneyPayload>(() => `/api/threads/${id}/journey`)
  useHarnessRefresh(id, () => void journey.refetch(), kindIn("tool.result", "thread.step_done", "eval", "train", "subagent"))
  const payload = () => settled(journey.data)
  /* The tool schemas, fetched only when some step wants fields filled: they
     type what a person fills in (a number field sends a number) and describe
     each field in the tool's own words. */
  const tools = useHarnessRead<{ controls: { name: string; fields: ToolField[] }[] }>(() =>
    payload()?.steps.some((step) => step.readiness?.mode === "needs") ? "/api/tools" : undefined,
  )
  // Not read while loading: the first read of a resource suspends, and the
  // fields are a refinement of the form, not a reason to hide the whole route.
  const fieldsOf = (tool: string) =>
    (tools.data.loading ? undefined : settled(tools.data))?.controls.find((control) => control.name === tool)?.fields ?? []
  const [choosing, setChoosing] = createSignal<string>()
  const [error, setError] = createSignal<string>()

  const choose = async (name: string) => {
    setChoosing(name)
    setError(undefined)
    try {
      // Records the ROUTE and leaves the goal alone: the goal is the person's
      // own words, and a menu pick is not those.
      await harness(`/api/threads/${id}/journey`, { body: { journey: name } })
      await journey.refetch()
    } catch (failure) {
      setError(say(failure))
    } finally {
      setChoosing(undefined)
    }
  }

  const runStep: RunStep = async (step, args, approved) => {
    try {
      const answered = await harness<{ result?: unknown }>(`/api/tools/${encodeURIComponent(step.tool)}`, {
        body: { arguments: args, approved, thread_id: id },
      })
      return refusalOf(answered?.result)
    } catch (failure) {
      // A refusal is RETURNED, never thrown. The approval refusal (428) and a
      // rejected argument (400) carry a sentence written as a remedy, and the
      // step shows it in place; a raised refusal leaves no event row, so this
      // is the only place it can appear.
      return { ok: false, detail: say(failure) }
    } finally {
      void journey.refetch()
    }
  }

  return (
    <Show
      when={payload()}
      fallback={
        <Show when={journey.data.error} fallback={<PaneEmpty title="Reading the route…" />}>
          <div class="flex flex-col py-2">
            <ErrorLine error={`The route could not be read: ${say(journey.data.error)}`} />
            <div class="px-4">
              <Button size="small" variant="ghost" onClick={() => void journey.refetch()}>
                Try again
              </Button>
            </div>
          </div>
        </Show>
      }
    >
      {(read) => (
        <div class="flex flex-col pb-4">
          <Show when={error()}>{(message) => <ErrorLine error={message()} />}</Show>
          <Show when={read().journey} fallback={<ChooseRoute read={read()} choosing={choosing()} onChoose={(name) => void choose(name)} />}>
            {(name) => (
              <Route
                name={name()}
                read={read()}
                loading={journey.data.loading}
                onRefresh={() => void journey.refetch()}
                runStep={runStep}
                fieldsOf={fieldsOf}
              />
            )}
          </Show>
        </div>
      )}
    </Show>
  )
}

/**
 * No route yet. Choosing is a click: the routes were listed from the start and
 * none was choosable, so a person who could see the one they wanted still had
 * to guess a sentence the keyword matcher would agree with.
 */
function ChooseRoute(props: { read: JourneyPayload; choosing: string | undefined; onChoose: (name: string) => void }) {
  return (
    <div class="flex flex-col gap-2 px-4 pt-3">
      <p class="text-[13px] text-v2-text-text-base">{props.read.say}</p>
      <div class="text-12-medium text-v2-text-text-muted">Pick one to start</div>
      <div class="flex flex-col items-start gap-1">
        <For each={props.read.journeys_available}>
          {(name) => (
            <Button size="small" variant="ghost" disabled={props.choosing !== undefined} onClick={() => props.onChoose(name)}>
              {props.choosing === name ? "Choosing…" : toolLabel(name)}
            </Button>
          )}
        </For>
      </div>
    </div>
  )
}

function Route(props: {
  name: string
  read: JourneyPayload
  loading: boolean
  onRefresh: () => void
  runStep: RunStep
  fieldsOf: (tool: string) => ToolField[]
}) {
  const share = () => (props.read.total === 0 ? 0 : Math.round((props.read.done_n / props.read.total) * 100))
  return (
    <>
      <header class="flex flex-col gap-1 px-4 pt-2">
        <div class="flex items-center gap-2">
          <Icon name="branch-out" size="small" class="text-v2-icon-icon-muted" />
          <h2 class="min-w-0 flex-1 truncate text-14-medium text-v2-text-text-base">{toolLabel(props.name)}</h2>
          <Show when={props.read.journey_origin === "matched"}>
            <span
              class="rounded-sm px-1.5 py-px text-[11px] text-v2-text-text-muted bg-v2-background-bg-layer-02"
              title={`Matched from this conversation's own words: ${props.read.matched_on.join(", ")}`}
            >
              Inferred
            </span>
          </Show>
          <span class="text-12-regular text-v2-text-text-muted tabular-nums">
            {props.read.done_n} of {props.read.total}
          </span>
          <Button size="small" variant="ghost" onClick={props.onRefresh} disabled={props.loading}>
            {props.loading ? "Reading" : "Refresh"}
          </Button>
        </div>
        <Show when={props.read.says}>
          <p class="text-[13px] text-v2-text-text-muted">{props.read.says}</p>
        </Show>
        <div
          class="mt-1 h-1 overflow-hidden rounded-sm bg-v2-background-bg-layer-03"
          role="img"
          aria-label={`${props.read.done_n} of ${props.read.total} steps done`}
        >
          <div class="h-full bg-v2-state-fg-success" style={{ width: `${share()}%` }} />
        </div>
      </header>

      <Show when={props.read.verdict} fallback={<NoVerdictYet />}>
        {(verdict) => <Verdict verdict={verdict()} />}
      </Show>
      <Show when={props.read.outcome}>{(outcome) => <Outcome outcome={outcome()} />}</Show>

      {/* By position: a re-read after a run returns fresh step objects, and a
          list keyed by reference would rebuild the step and drop the refusal
          it was showing. */}
      <ol class="flex flex-col pt-2">
        <Index each={props.read.steps}>
          {(step) => (
            <StepRow
              step={step()}
              total={props.read.total}
              runnable={step().ordinal === props.read.next_runnable?.ordinal}
              runStep={props.runStep}
              fieldsOf={props.fieldsOf}
            />
          )}
        </Index>
      </ol>
    </>
  )
}

function StepMark(props: { step: JourneyStep }) {
  return (
    <span class="mt-0.5 flex size-4 shrink-0 items-center justify-center" aria-hidden="true">
      <Show
        when={props.step.state !== "ahead"}
        fallback={<span class="size-2.5 rounded-full border border-v2-border-border-base" />}
      >
        <Icon
          size="small"
          name={props.step.state === "next" ? "chevron-right" : props.step.state === "not_needed" ? "dash" : "check"}
          classList={{
            "text-v2-state-fg-success": props.step.state === "done" || props.step.state === "done_elsewhere",
            "text-v2-text-text-base": props.step.state === "next",
            "text-v2-text-text-faint": props.step.state === "not_needed",
          }}
        />
      </Show>
    </span>
  )
}

function StepRow(props: {
  step: JourneyStep
  total: number
  runnable: boolean
  runStep: RunStep
  fieldsOf: (tool: string) => ToolField[]
}) {
  const step = () => props.step
  const knows = () => Object.keys(step().prefill)
  return (
    <li
      class="flex gap-2 px-4 py-2"
      aria-label={`Step ${step().ordinal} of ${props.total}: ${toolLabel(step().tool)} - ${stateInWords(step())}`}
    >
      <StepMark step={step()} />
      <span class="w-5 shrink-0 text-12-regular text-v2-text-text-faint tabular-nums">{step().ordinal}</span>
      <div class="flex min-w-0 flex-1 flex-col gap-0.5">
        <div class="flex items-center gap-2">
          <span
            class="text-[13px] [font-weight:530]"
            classList={{
              "text-v2-text-text-base": step().state !== "not_needed",
              "text-v2-text-text-muted": step().state === "not_needed",
            }}
          >
            {toolLabel(step().tool)}
          </span>
          <Show when={step().needs_approval}>
            <span class="text-[11px] text-v2-text-text-muted" title="This one asks you before it runs">
              asks first
            </span>
          </Show>
        </div>
        <p class="text-12-regular text-v2-text-text-muted break-words">{step().why}</p>
        {/* A line, not an essay: some tools answer with eleven lines, and drawn
            in full one step swallowed the route around it. The full text is on
            hover. */}
        <Show when={step().produced}>
          <p class="line-clamp-2 text-12-regular text-v2-text-text-base break-words" title={step().produced ?? undefined}>
            {step().produced}
          </p>
        </Show>
        <Show when={step().state === "not_needed"}>
          <p class="text-12-regular text-v2-text-text-muted">
            not needed here
            <Show when={step().unnecessary_because}>
              {" - "}
              <b class="text-v2-text-text-base">{step().unnecessary_because}</b> covered it
            </Show>
          </p>
        </Show>
        <Show when={step().state === "done_elsewhere" && step().satisfied_by}>
          {(by) => (
            <p class="text-12-regular text-v2-text-text-muted">
              met by <b class="text-v2-text-text-base">{by().tool}</b> - it recorded {by().facts.join(", ")}
            </p>
          )}
        </Show>
        <Show when={step().state === "next" && step().args_hint}>
          <p class="text-12-regular text-v2-text-text-muted">{step().args_hint}</p>
        </Show>
        {/* What happened when it was tried, in the tool's own sentence and
            neutral ink: this product's refusals are written as remedies, and
            the useful part is why and what next, not an alarm. */}
        <Show when={step().attempted?.detail}>
          <p class="text-12-regular text-v2-text-text-base break-words">
            <span class="text-v2-text-text-muted">Tried: </span>
            {step().attempted!.detail}
          </p>
        </Show>
        {/* What a step already knows is information, so it is drawn on every
            step that has it, not only the one you are on. */}
        <Show when={knows().length > 0 && step().state !== "done"}>
          <p class="text-12-regular text-v2-text-text-muted">
            opens knowing <span class="text-v2-text-text-base">{knows().join(", ")}</span>
          </p>
        </Show>
        {/* The run control follows what can be pressed, not what is next in the
            list: the next step can be blocked while a later one is ready. A
            blocked next step still offers its fields. */}
        <Show when={props.runnable || step().state === "next"}>
          <StepAction step={step()} runStep={props.runStep} fieldsOf={props.fieldsOf} />
        </Show>
        <Show
          when={stamp(step().ran_at)}
          fallback={
            <Show when={step().evidence === "ledger" && step().state === "done"}>
              <p class="text-[11px] text-v2-text-text-faint">recorded on the ledger by this step's own tool</p>
            </Show>
          }
        >
          {(when) => (
            <p class="text-[11px] text-v2-text-text-faint tabular-nums">
              {when()}
              {step().driven_by ? ` · run by ${step().driven_by === "user" ? "you" : "the model"}` : ""}
              {step().evidence === "ledger" ? " · from the fact it recorded" : ""}
            </p>
          )}
        </Show>
      </div>
    </li>
  )
}

/**
 * The control on the step, and it is three controls wearing one name because a
 * route has three honest answers:
 *
 *   click    every argument is on the record; the button runs it.
 *   approve  the same, and the tool wants a person to say yes. Two clicks,
 *            deliberately: approval is a person saying yes to THIS action, so
 *            a button that sent `approved: true` by itself would launder it.
 *   needs    something only the person can give. The button names it and opens
 *            those fields here, rather than a form they have to discover.
 *
 * A refusal lands here, in the tool's own words, with the step still there to
 * try again.
 */
function StepAction(props: { step: JourneyStep; runStep: RunStep; fieldsOf: (tool: string) => ToolField[] }) {
  const [busy, setBusy] = createSignal(false)
  const [confirming, setConfirming] = createSignal(false)
  const [filling, setFilling] = createSignal(false)
  const [typed, setTyped] = createSignal<Record<string, string>>({})
  const [refused, setRefused] = createSignal<string>()
  const openControls = useOpenToolControls()
  const mode = () => props.step.readiness?.mode ?? "needs"
  const missing = () => props.step.readiness?.missing ?? []
  const fields = createMemo(() => props.fieldsOf(props.step.tool))
  const described = (name: string) => fields().find((field) => field.name === name)

  const run = async (approved: boolean) => {
    setRefused(undefined)
    let args: Record<string, unknown>
    try {
      const wanted = filling() ? stillMissing(missing(), typed()) : []
      if (wanted.length) throw new Error(`Still needed: ${wanted.join(", ")}.`)
      args = argumentsFor(props.step.prefill, filling() ? typed() : {}, fields())
    } catch (problem) {
      setRefused(say(problem))
      setConfirming(false)
      return
    }
    setBusy(true)
    const answer = await props.runStep(props.step, args, approved)
    setBusy(false)
    setConfirming(false)
    if (answer.ok) {
      setFilling(false)
      setTyped({})
      return
    }
    // Even the fallback carries a next action: a bare "it failed" is the case
    // this route exists not to produce.
    setRefused(
      answer.detail ??
        "It did not run and gave no reason. The Evidence pane holds what the engine recorded for this conversation, and the tool can be run from Settings > Harness > Controls with its arguments visible.",
    )
  }

  const asksFirst = () => mode() === "approve" || props.step.needs_approval
  const press = () => (asksFirst() ? setConfirming(true) : void run(false))

  return (
    <div class="flex flex-col gap-1.5 pt-1">
      <Show when={filling()}>
        <div class="flex flex-col gap-2 rounded-sm bg-v2-background-bg-layer-01 px-3 py-2">
          <For each={missing()}>
            {(name) => (
              <label class="flex flex-col gap-1">
                <span class="text-12-medium text-v2-text-text-base">{name}</span>
                <TextInput
                  value={typed()[name] ?? ""}
                  onInput={(event) => {
                    const value = event.currentTarget.value
                    setTyped((was) => ({ ...was, [name]: value }))
                  }}
                  placeholder={described(name)?.enum?.length ? described(name)!.enum!.map(String).join(" | ") : described(name)?.type ?? ""}
                />
                <Show when={described(name)?.description}>
                  <span class="text-[11px] text-v2-text-text-muted">{described(name)!.description}</span>
                </Show>
              </label>
            )}
          </For>
        </div>
      </Show>
      <Show
        when={confirming()}
        fallback={
          <div class="flex items-center gap-1">
            <Show
              when={mode() !== "needs" || filling()}
              fallback={
                <Button size="small" variant="neutral" onClick={() => setFilling(true)}>
                  {missing().length ? `Fill in ${missing().join(", ")}` : "Open this step"}
                </Button>
              }
            >
              <Button size="small" variant="neutral" disabled={busy()} onClick={press}>
                {busy() ? "Running…" : asksFirst() ? "Review and run" : "Run this step"}
              </Button>
              <Show when={filling()}>
                <Button size="small" variant="ghost" disabled={busy()} onClick={() => setFilling(false)}>
                  Cancel
                </Button>
              </Show>
            </Show>
            {/* After a refusal, the whole form: Settings > Harness > Controls,
                opened on this step's tool (settings/controls-open.ts). Not
                offered in a pop-out, which has no settings to open. */}
            <Show when={openControls && (refused() || props.step.attempted?.detail)}>
              <Button size="small" variant="ghost" disabled={busy()} onClick={() => openControls?.(props.step.tool)}>
                Open in Controls
              </Button>
            </Show>
          </div>
        }
      >
        <div class="flex flex-col gap-1.5 rounded-sm bg-v2-background-bg-layer-01 px-3 py-2">
          <p class="text-12-regular text-v2-text-text-base">
            This one asks first. It will run <b>{props.step.tool}</b>
            {Object.keys(props.step.prefill).length || filling()
              ? ` with ${[...Object.keys(props.step.prefill), ...(filling() ? missing() : [])].join(", ")} as shown above.`
              : "."}
          </p>
          <div class="flex items-center gap-1">
            <Button size="small" variant="neutral" disabled={busy()} onClick={() => void run(true)}>
              {busy() ? "Running…" : "Yes, run it"}
            </Button>
            <Button size="small" variant="ghost" disabled={busy()} onClick={() => setConfirming(false)}>
              Not now
            </Button>
          </div>
        </div>
      </Show>
      {/* Only if the step is not already saying it: a refusal that came back
          through the button is usually the same sentence the engine then
          reports as `attempted` on the next read, and both printed it twice. */}
      <Show when={refused() && refused()!.trim() !== (props.step.attempted?.detail ?? "").trim()}>
        <p class="text-12-regular text-v2-text-text-base break-words">
          <span class="text-v2-text-text-muted">Tried: </span>
          {refused()}
        </p>
      </Show>
    </div>
  )
}

/**
 * What came out the other end: the engine's verdict, quoted with the two run
 * ids behind it. NO EVIDENCE is drawn as calmly as a win - this product exists
 * to be able to say a training run bought nothing.
 */
function Outcome(props: { outcome: JourneyOutcome }) {
  const resolved = () => props.outcome.resolved === true
  const better = () => (props.outcome.delta ?? 0) > 0
  return (
    <section class="mx-4 mt-2 flex flex-col gap-1 rounded-sm bg-v2-background-bg-layer-01 px-3 py-2">
      <div class="flex flex-wrap items-baseline gap-x-2 text-[13px]">
        <span class="text-[13px] [font-weight:530] text-v2-text-text-base">{resolved() ? (better() ? "Better" : "Worse") : "No evidence"}</span>
        <span class="text-v2-text-text-base tabular-nums">
          {pct(props.outcome.score)} <span class="text-v2-text-text-muted">vs</span> {pct(props.outcome.baseline_score)}
          {/* The denominator travels with the number: 7% against 13% is a
              different claim on 30 rows than on 300. */}
          <Show when={typeof props.outcome.paired_rows === "number"}>
            <span class="text-v2-text-text-muted"> on {props.outcome.paired_rows} paired rows</span>
          </Show>
        </span>
        <span class="text-12-regular text-v2-text-text-faint">
          run {props.outcome.adapter_run_id} against {props.outcome.baseline_run_id}
        </span>
      </div>
      <Show when={props.outcome.says}>
        <p class="text-12-regular text-v2-text-text-muted">{props.outcome.says}</p>
      </Show>
      <Show when={!resolved() && !props.outcome.says && typeof props.outcome.rows_that_would_resolve_this_delta === "number"}>
        <p class="text-12-regular text-v2-text-text-muted">
          A delta this size would need about <b>{props.outcome.rows_that_would_resolve_this_delta}</b> paired rows to
          separate from chance.
        </p>
      </Show>
    </section>
  )
}

/** The card where a verdict will be, before one exists. It names no gate total:
 *  with no verdict there is none to read, and inventing one here would be the
 *  failure this card exists to prevent. */
function NoVerdictYet() {
  return (
    <section class="mx-4 mt-3 flex flex-col gap-1 rounded-sm bg-v2-background-bg-layer-01 px-3 py-2">
      <div class="flex items-baseline gap-2">
        <span class="flex-1 text-[13px] [font-weight:530] text-v2-text-text-base">No verdict yet</span>
        <span class="text-12-regular text-v2-text-text-muted">no gate reached</span>
      </div>
      <p class="text-12-regular text-v2-text-text-muted">
        Nothing has been measured in this conversation, so the ledger has not been asked anything. A verdict appears as
        soon as a step records a fact - running one that only says where your material lives records a location, not a
        measurement.
      </p>
    </section>
  )
}

/** The ledger's answer, on the route. The wording is the engine's own `say`. */
function Verdict(props: { verdict: JourneyVerdict }) {
  return (
    <section class="mx-4 mt-3 flex flex-col gap-1 rounded-sm bg-v2-background-bg-layer-01 px-3 py-2">
      <div class="flex items-baseline gap-2">
        <span class="flex-1 text-[13px] [font-weight:530] text-v2-text-text-base break-words">{props.verdict.outcome}</span>
        <span class="shrink-0 text-12-regular text-v2-text-text-muted tabular-nums">
          {props.verdict.gates_passed} of {props.verdict.gates_total} gates passed
        </span>
      </div>
      <Show when={props.verdict.say}>
        <p class="text-12-regular text-v2-text-text-muted">{props.verdict.say}</p>
      </Show>
      <Show when={props.verdict.blocked_by}>{(blocked) => <Blocking blocked={blocked()} />}</Show>
    </section>
  )
}

/**
 * The rule that stopped the route, the values it read, and where each came
 * from. A gate the engine never evaluated is not a gate that failed, and a fact
 * nobody measured reads as unanswered, not as false.
 */
function Blocking(props: { blocked: BlockedBy }) {
  const reached = () => props.blocked.reached
  return (
    <div class="mt-1 flex flex-col gap-0.5 border-t border-v2-border-border-muted pt-1.5 text-12-regular">
      <div class="flex flex-wrap items-baseline gap-x-2">
        <span class="text-v2-text-text-muted">{reached() ? "Stopped at" : "First rule"}</span>
        <b class="text-v2-text-text-base">{props.blocked.gate}</b>
        <span class="text-v2-text-text-faint tabular-nums">
          {props.blocked.checked} of {props.blocked.of} gates checked
        </span>
      </div>
      <Show when={!reached()}>
        <div class="text-v2-text-text-muted">
          Nothing failed. The route stopped before any gate was evaluated, so this is the rule that comes first, not one
          that was broken.
        </div>
      </Show>
      <div class="flex gap-2">
        <span class="shrink-0 text-v2-text-text-muted">Rule</span>
        <span class="min-w-0 text-v2-text-text-base break-words">
          {props.blocked.class_undecided
            ? "depends on the method class, which this run has not chosen yet"
            : props.blocked.clause}
        </span>
      </div>
      <For each={props.blocked.reads}>
        {(read) => (
          <div class="flex gap-2">
            <span class="shrink-0 font-mono text-[11px] text-v2-text-text-muted">{read.fact}</span>
            <Show when={!read.unmeasured} fallback={<span class="text-v2-text-text-faint">nothing has measured this yet</span>}>
              <span class="min-w-0 break-words" title={read.how ?? undefined}>
                <b class="text-v2-text-text-base">{String(read.value)}</b>{" "}
                <span class="text-v2-text-text-faint">{read.origin}</span>
              </span>
            </Show>
          </div>
        )}
      </For>
    </div>
  )
}
