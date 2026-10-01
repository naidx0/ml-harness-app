import { createMemo, createSignal, For, Match, Show, Switch } from "solid-js"
import { Button } from "@opencode/ui/button"
import { Checkbox } from "@opencode/ui/checkbox"
import { Icon } from "@opencode/ui/icon"
import { IconButton } from "@opencode/ui/icon-button"
import { Textarea } from "@opencode/ui/textarea"
import { Tooltip } from "@opencode/ui/tooltip"
import { blocksOf, splitIntoPhases, withPhaseBody, type Step } from "./plan-model"

/**
 * The two ways of looking at one plan: a document with live checkboxes, and
 * an editor one phase at a time.
 *
 * The owner asked for both, on different days. Of the pop-out (2026-09-12):
 * "this markdown style view the same way Cursor has it" - so the read view is
 * the whole plan as one page, with its `- [ ]` steps as boxes that tick. And
 * of the side panel: "a good follow editor... sectioned off" - so the editor
 * cuts the plan at its `##` phases and saves one phase back into the whole.
 */

export type StepActions = {
  /** A step whose box is being written, so a second click cannot race it. */
  busy: boolean
  /** The first open step, which a run or a Work press takes next. */
  next: number | undefined
  live: boolean
  onTick: (step: Step) => void
  onUnpark: (step: Step) => void
  onWork: (step: Step) => void
  /** Draft a question about the step into the composer; never sends. */
  onAsk: (step: Step) => void
  /** Whether a composer is in reach (false in a pop-out, where Ask copies). */
  canCompose: boolean
  /** The step a Work press is sending, so its button can say so. */
  working: number | undefined
}

/**
 * THE TYPE, ON THEIR SCALE AND ON WHOLE PIXELS. The owner, 2026-09-22: "our
 * plan text looks a little blurry and weird, because it was purely copied
 * over from before." The copy set 13px text on the body's inherited leading
 * and their 13px classes, whose line height is 150% - 19.5px - so every row
 * below the first sat on a half pixel, and grayscale antialiasing (their
 * body's) smears a glyph that starts half-way through a pixel. Measured: the
 * third step's text at y = 404.5.
 *
 * So: their classes for size, weight and face (text-14-medium titles,
 * text-12-regular body, text-12-mono only for code), each with a whole-pixel
 * line height forced over theirs (`leading-5!` = 20px, `leading-6!` = 24px),
 * and every offset in whole pixels. Only the weights that are loaded: Plex
 * 400 and the Text cut's 450-560.
 */
const BODY = "text-12-regular leading-5!"

/**
 * The plan as a page. Ticking a box writes `[x]` into the plan column - the
 * same thing `mark_step_done` does when the model finishes a step - so the
 * person and the agent are working one list. Un-ticking works too.
 */
export function PlanRead(props: { plan: string; actions: StepActions; onEditPhase: (index: number) => void }) {
  const blocks = createMemo(() => blocksOf(props.plan))
  return (
    <div data-component="harness-plan-read" class="flex flex-col pb-4">
      <For each={blocks()}>
        {(block) => (
          <Switch>
            {/* The title is the pane's own heading above, so it is not printed twice. */}
            <Match when={block.kind === "title"}>{null}</Match>
            <Match when={block.kind === "phase" && block}>
              {(phase) => (
                /* A phase is a list heading: a hairline above it, its title in
                   their 14 medium, and the edit pencil on the same 24px line. */
                <div class="mt-3 flex items-start gap-2 border-t border-v2-border-border-muted px-4 pt-3 pb-1">
                  <h3 class="min-w-0 flex-1 break-words text-14-medium leading-6! text-v2-text-text-base">
                    {phase().text}
                  </h3>
                  <Tooltip value="Edit this phase" placement="left">
                    <IconButton
                      icon={<Icon name="pencil-line" />}
                      variant="ghost-muted"
                      size="small"
                      aria-label={`Edit ${phase().text}`}
                      onClick={() => props.onEditPhase(phase().index)}
                    />
                  </Tooltip>
                </div>
              )}
            </Match>
            <Match when={block.kind === "heading" && block}>
              {(heading) => (
                <div class="px-4 pt-3 pb-0.5 text-12-medium leading-5! text-v2-text-text-muted">{heading().text}</div>
              )}
            </Match>
            <Match when={block.kind === "step" && block}>
              {(row) => <StepRow step={row().step} actions={props.actions} />}
            </Match>
            <Match when={block.kind === "bullet" && block}>
              {(bullet) => (
                <div class={`flex items-start gap-3 px-4 py-0.5 text-v2-text-text-muted ${BODY}`}>
                  {/* A 4px dot on the middle of the 20px line: 8px down. */}
                  <span aria-hidden="true" class="mt-2 ml-1.5 size-1 shrink-0 rounded-full bg-v2-text-text-faint" />
                  <span class="min-w-0 flex-1 break-words">{bullet().text}</span>
                </div>
              )}
            </Match>
            <Match when={block.kind === "code" && block}>
              {(code) => (
                <pre class="mx-4 my-1 overflow-x-auto rounded-sm border border-v2-border-border-muted bg-v2-background-bg-layer-01 px-3 py-2 text-12-mono leading-5! text-v2-text-text-base">
                  {code().text}
                </pre>
              )}
            </Match>
            <Match when={block.kind === "text" && block}>
              {(text) => <p class={`px-4 py-0.5 break-words text-v2-text-text-muted ${BODY}`}>{text().text}</p>}
            </Match>
            <Match when={block.kind === "gap"}>
              <div class="h-1" />
            </Match>
          </Switch>
        )}
      </For>
    </div>
  )
}

function StepRow(props: { step: Step; actions: StepActions }) {
  const isNext = () => props.actions.next === props.step.line
  return (
    <div
      data-slot="harness-plan-step"
      data-state={props.step.state}
      class="group flex items-start gap-2 px-4 py-1.5 hover:bg-v2-overlay-simple-overlay-hover"
    >
      <div class="min-w-0 flex-1">
        <Switch>
          <Match when={props.step.state === "parked"}>
            {/* A parked step is not a box: the run could not do it and said why,
                and ticking it would claim work nobody performed. Its way back is
                Unpark, which puts it on the list for the next run. The 14px
                sign sits 3px down, level with the checkboxes' 16px at 2px. */}
            <div class="flex items-start gap-3">
              <Icon name="warning" size="small" class="mt-[3px] ml-px shrink-0 text-v2-state-fg-warning" />
              <div class="min-w-0">
                <div class={`break-words text-v2-text-text-base ${BODY}`}>{props.step.text}</div>
                <Show when={props.step.why}>
                  <div class={`break-words text-v2-text-text-muted ${BODY}`}>Parked: {props.step.why}</div>
                </Show>
              </div>
            </div>
          </Match>
          <Match when={true}>
            {/* Their checkbox, top-aligned: the 16px box 2px down the 20px line. */}
            <Checkbox
              checked={props.step.state === "done"}
              disabled={props.actions.busy}
              onChange={() => props.actions.onTick(props.step)}
              style={{ "--checkbox-align": "flex-start", "--checkbox-offset": "2px" }}
            >
              <span
                class={`block break-words ${BODY}`}
                classList={{
                  "text-v2-text-text-faint line-through": props.step.state === "done",
                  "text-v2-text-text-base": props.step.state !== "done",
                }}
              >
                {props.step.text}
              </span>
            </Checkbox>
          </Match>
        </Switch>
      </div>
      <Show when={isNext()}>
        {/* The colour hints the owner kept: plan purple for the step a run
            takes next, cobalt (working) while a run is on it. */}
        <span
          class="shrink-0 text-12-medium leading-5!"
          classList={{
            "text-[color:var(--harness-build-ink)]": props.actions.live,
            "text-[color:var(--harness-plan-ink)]": !props.actions.live,
          }}
        >
          {props.actions.live ? "working" : "next"}
        </span>
      </Show>
      {/* The actions sit on the text's line (a 24px button, 2px above and
          below the 20px line). Shown on the next step, and on any row under
          the pointer or the keyboard, so the list reads as a list. */}
      <div
        class="-my-0.5 flex shrink-0 items-center gap-1"
        classList={{ "opacity-0 group-hover:opacity-100 focus-within:opacity-100": !isNext() }}
      >
        <Show when={props.step.state === "parked"}>
          <Tooltip value="Put this step back on the list, so a run tries it again" placement="left">
            <Button size="small" variant="ghost" disabled={props.actions.busy} onClick={() => props.actions.onUnpark(props.step)}>
              Unpark
            </Button>
          </Tooltip>
        </Show>
        <Show when={props.step.state !== "done"}>
          <Tooltip
            value={
              props.actions.live
                ? "A run is working the plan. Stop it first, so two loops do not send turns into one conversation."
                : `Ask the agent to do this step now: ${props.step.text}`
            }
            placement="left"
          >
            <Button
              size="small"
              variant="ghost"
              disabled={props.actions.live || props.actions.working !== undefined}
              onClick={() => props.actions.onWork(props.step)}
            >
              {props.actions.working === props.step.line ? "Sending" : "Work"}
            </Button>
          </Tooltip>
        </Show>
        {/* "Ask" drafts `About the step "<text>": ` into the composer for the
            person to finish, as the outgoing goal bar did - on every step,
            done ones included. It never sends. In a pop-out there is no
            composer, so it copies the draft instead. */}
        <Tooltip
          value={
            props.actions.canCompose
              ? `Ask the agent about this step: ${props.step.text}`
              : "Copy a question about this step, to paste into the conversation in the main window"
          }
          placement="left"
        >
          <Button size="small" variant="ghost" onClick={() => props.actions.onAsk(props.step)}>
            Ask
          </Button>
        </Tooltip>
      </div>
    </div>
  )
}

/**
 * The editor, one phase at a time. It does not save as you type: the plan is
 * the standing instruction for every later turn, and a keystroke reaching the
 * prompt is a half-written sentence reaching the prompt. Save is a press.
 */
export function PlanEdit(props: {
  plan: string
  at: number
  onAt: (index: number) => void
  onSave: (next: string) => Promise<void>
}) {
  const phases = createMemo(() => splitIntoPhases(props.plan))
  const index = () => Math.max(0, Math.min(props.at, phases().length - 1))
  const phase = () => phases()[index()]
  const [draft, setDraft] = createSignal<string | undefined>()
  /* The plan the edit started from. If the model rewrites the plan while a
     person is typing, the edit is KEPT and they are told, rather than thrown
     away - throwing away what somebody typed is the one unrecoverable thing
     this editor could do. */
  const [base, setBase] = createSignal<string | undefined>()
  const [busy, setBusy] = createSignal(false)
  const [failed, setFailed] = createSignal<string | undefined>()
  const body = () => draft() ?? phase()?.body ?? ""
  const dirty = () => draft() !== undefined && draft() !== phase()?.body
  const movedUnder = () => dirty() && base() !== undefined && base() !== props.plan

  const revert = () => {
    setDraft(undefined)
    setBase(undefined)
    setFailed(undefined)
  }

  const save = async () => {
    if (!dirty() || busy()) return
    setBusy(true)
    setFailed(undefined)
    try {
      await props.onSave(withPhaseBody(props.plan, index(), body()))
      revert()
    } catch (error) {
      // The edit STAYS in the box; only the sentence about why is added.
      setFailed(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div class="flex flex-col gap-2 px-4 pb-4">
      <nav class="flex flex-wrap gap-1" aria-label="Phases">
        <For each={phases()}>
          {(each, at) => (
            <button
              type="button"
              class="flex max-w-full items-center gap-1.5 rounded-sm px-2 py-1 text-12-regular leading-5!"
              classList={{
                "bg-v2-background-bg-layer-02 text-v2-text-text-base": at() === index(),
                "text-v2-text-text-muted hover:bg-v2-overlay-simple-overlay-hover": at() !== index(),
              }}
              aria-current={at() === index() ? "true" : undefined}
              title={each.heading.trim() || "Before the first phase"}
              onClick={() => {
                if (at() === index()) return
                // Moving to another phase with an unsaved edit would silently
                // drop it; the switch waits until it is saved or reverted.
                if (dirty()) {
                  setFailed("Save or revert this phase before opening another.")
                  return
                }
                revert()
                props.onAt(at())
              }}
            >
              <span class="tabular-nums text-v2-text-text-faint">{each.number ?? "–"}</span>
              <span class="truncate">{each.label}</span>
            </button>
          )}
        </For>
      </nav>
      <Textarea
        rows={16}
        value={body()}
        spellcheck={false}
        aria-label={phase()?.heading.trim() || "Plan"}
        onInput={(event) => {
          if (draft() === undefined) setBase(props.plan)
          setDraft(event.currentTarget.value)
        }}
      />
      <Show when={movedUnder()}>
        <div class="text-12-regular leading-5! text-v2-state-fg-warning">
          The plan changed while you were editing. Save writes your text into this phase of the new plan; Revert shows
          the new text.
        </div>
      </Show>
      <div class="flex items-center gap-2">
        <span class="flex-1 text-12-regular leading-5!" classList={{ "text-v2-state-fg-danger": !!failed(), "text-v2-text-text-muted": !failed() }}>
          <Show when={failed()} fallback={`${phases().length} phase${phases().length === 1 ? "" : "s"}`}>
            {(why) => `Not saved - your edit is still here. ${why()}`}
          </Show>
        </span>
        <Button size="small" variant="ghost" disabled={!dirty() || busy()} onClick={revert}>
          Revert
        </Button>
        <Button size="small" variant="neutral" disabled={!dirty() || busy()} onClick={() => void save()}>
          {busy() ? "Saving" : "Save"}
        </Button>
      </div>
    </div>
  )
}
