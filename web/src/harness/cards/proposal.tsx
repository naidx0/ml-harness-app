import { createEffect, createSignal, For, Match, on, onCleanup, Show, Switch } from "solid-js"
import { Button } from "@opencode/ui/button"
import { Icon } from "@opencode/ui/icon"
import { harness, HarnessError } from "../engine"
import { Block, Facts, Note, Pill, type Tone } from "./frame"
import {
  COST_DIMENSIONS,
  DIMENSION_LABEL,
  readStorm,
  stormIdFor,
  stormIsRunning,
  type Estimate,
  type Proposal,
  type StepState,
  type Storm,
} from "./readers"

/**
 * The build proposal and the storm it starts - parity 5.18.
 *
 * Ported from the outgoing `ProposalCard.tsx`, `StormCard.tsx`,
 * `useStorms.ts` and `useApprovals.ts`. The plan is read before the buttons
 * are the nearest thing to the cursor: title, why, the steps, the cost in
 * four dimensions with what is unknown said to be unknown, where it runs,
 * what could go wrong, what only the person can answer, and when it is done.
 *
 * THE APPROVAL IS THREE CONTROLS, NOT FOUR. "Allow once" is the solid button
 * and the default; Deny is ordinary, never red; Stop halts a running storm.
 * There is no "Always allow" on a build, for the outgoing card's reason: a
 * build is one plan against one data snapshot with one fingerprint, so a
 * standing grant for it could only mean "always allow builds", which nobody
 * asked for. Standing grants belong to tool approvals (their permission dock).
 *
 * WHAT IS SENT IS NOT THE PLAN. `POST /api/storms` takes the question the
 * proposal was made from and the fingerprint; the engine proposes again and
 * refuses to record anything if what it would run now is not what the person
 * read. Approving and starting are two acts and two routes: the contract is
 * written first, then the run is asked for.
 */

export const DENIALS = "mlh.denied-builds"

export type Denial = { at: string; reason: "clicked" }

/**
 * Where one denial is filed: the thread AND the fingerprint. The fingerprint
 * is a hash of the plan's content, so the same plan proposed in two
 * conversations has the same one; keyed by it alone, "Deny" in one chat hid
 * the approval in the other.
 */
export function denialKey(threadId: number | undefined, fingerprint: string): string {
  return `${threadId ?? "none"}:${fingerprint}`
}

/** A denial is the browser's own record: the engine has no row for "no". */
export function readDenial(threadId: number | undefined, fingerprint: string): Denial | null {
  try {
    const all = JSON.parse(localStorage.getItem(DENIALS) ?? "{}") as Record<string, Denial>
    return all[denialKey(threadId, fingerprint)] ?? null
  } catch {
    return null
  }
}

export function writeDenial(threadId: number | undefined, fingerprint: string, denial: Denial | null) {
  try {
    const all = JSON.parse(localStorage.getItem(DENIALS) ?? "{}") as Record<string, Denial>
    const key = denialKey(threadId, fingerprint)
    if (denial) all[key] = denial
    else delete all[key]
    localStorage.setItem(DENIALS, JSON.stringify(all))
  } catch {
    // Private windows and blocked storage: the denial holds for this view only.
  }
}

const STATE_LOOK: Record<StepState, { word: string; tone: Tone }> = {
  queued: { word: "Queued", tone: "muted" },
  preflight: { word: "Checking", tone: "info" },
  running: { word: "Running", tone: "info" },
  waiting_input: { word: "Waiting on you", tone: "warn" },
  waiting_approval: { word: "Waiting for approval", tone: "warn" },
  stalled: { word: "Stalled", tone: "warn" },
  done: { word: "Done", tone: "good" },
  failed: { word: "Failed", tone: "bad" },
  cancelled: { word: "Stopped", tone: "muted" },
}

function magnitude(estimate: Estimate): string {
  if (estimate.provenance === "UNKNOWN" || estimate.value === null) return "unknown"
  const value = estimate.value
  if (estimate.unit === "seconds") {
    if (value < 90) return `${Math.round(value)} s`
    if (value < 5400) return `${Math.round(value / 60)} min`
    return `${(value / 3600).toFixed(1)} h`
  }
  if (estimate.unit === "bytes") {
    const units = ["B", "kB", "MB", "GB"]
    let size = value
    let unit = 0
    while (size >= 1000 && unit < units.length - 1) {
      size /= 1000
      unit += 1
    }
    return `${size >= 100 || unit === 0 ? Math.round(size) : size.toPrecision(3)} ${units[unit]}`
  }
  return `${Math.round(value).toLocaleString("en")} ${estimate.unit}`
}

export function ProposalBody(props: { proposal: Proposal; args: Record<string, unknown>; threadId: number | undefined }) {
  const build = () => props.proposal.build
  const [denial, setDenial] = createSignal<Denial | null>(readDenial(props.threadId, props.proposal.approve))
  const [asking, setAsking] = createSignal(false)
  const [refused, setRefused] = createSignal<string>()
  const [tick, setTick] = createSignal(0)

  // The storm recorded against THIS fingerprint, if any - found by the
  // fingerprint the engine keeps on the storm, never by position.
  //
  // OUR OWN SIGNALS, NOT A RESOURCE. Until the first read answers, whether
  // this plan was already approved is unknown, and the Approve ask must not
  // flash for a plan that was. A resource's `loading` sticks inside their
  // transitions and its `latest` throws once the read fails, so the three
  // states - reading, read, could not read - are kept here by hand.
  const [storm, setStorm] = createSignal<Storm | null>(null)
  const [stormError, setStormError] = createSignal<string>()
  const [settled, setSettled] = createSignal(false)
  let generation = 0
  const readStormNow = async () => {
    const thread = props.threadId
    if (thread === undefined) return
    const mine = ++generation
    try {
      const list = await harness(`/api/storms?thread_id=${thread}`)
      const id = stormIdFor(list, props.proposal.approve)
      const found = id === null ? null : readStorm(await harness(`/api/storms/${id}`))
      if (mine !== generation) return
      setStorm(found)
      setStormError(undefined)
    } catch (failure) {
      if (mine !== generation) return
      setStormError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      if (mine === generation) setSettled(true)
    }
  }
  createEffect(on([() => props.threadId, tick], () => void readStormNow()))

  // While a storm is spending, re-read it; the work reports into the thread
  // and this picture follows. Stops by itself when the storm settles.
  const timer = setInterval(() => {
    const current = storm()
    if (current && stormIsRunning(current.state)) void readStormNow()
  }, 3000)
  onCleanup(() => clearInterval(timer))

  const allow = async () => {
    if (props.threadId === undefined) return
    setAsking(true)
    setRefused(undefined)
    try {
      const declared = readStorm(
        await harness("/api/storms", {
          body: { thread_id: props.threadId, approve: props.proposal.approve, proposal: props.args, build: props.proposal.raw },
        }),
      )
      if (!declared) {
        setRefused(
          "The engine recorded an approval this interface could not read back, so nothing was started. Nothing here guesses at a storm it cannot see.",
        )
        return
      }
      await harness(`/api/storms/${declared.id}/run`, { body: { background: true, restart_stalled: [] } })
      setTick((n) => n + 1)
    } catch (failure) {
      if (failure instanceof HarnessError && failure.message === "not_the_plan_you_approved") {
        setRefused(
          "The plan the harness would run now is not the one you said yes to, so nothing was recorded and nothing ran. Ask for a fresh proposal and approve that one if it is what you want.",
        )
      } else {
        setRefused(failure instanceof Error ? failure.message : String(failure))
      }
    } finally {
      setAsking(false)
    }
  }

  const stop = async (id: number) => {
    try {
      await harness(`/api/storms/${id}/cancel`, { body: {} })
    } catch (failure) {
      setRefused(failure instanceof Error ? failure.message : String(failure))
    }
    setTick((n) => n + 1)
  }

  return (
    <>
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-[13px] text-v2-text-text-base [font-weight:530]">{build().title}</span>
        <span class="text-12-mono text-v2-text-text-faint">{build().forOutcome || build().id}</span>
      </div>
      <Show when={build().because}>
        <p class="text-[13px] text-v2-text-text-base">{build().because}</p>
      </Show>

      <Block title="The plan" hint={`${build().steps.length} step${build().steps.length === 1 ? "" : "s"}`}>
        <ol class="flex flex-col gap-1">
          <For each={build().steps}>
            {(step, index) => {
              const live = () => storm()?.steps.find((one) => one.id === step.id)
              return (
                <li class="flex flex-col gap-0.5 rounded-md bg-v2-background-bg-layer-01 px-3 py-1.5">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="text-12-regular tabular-nums text-v2-text-text-faint">{index() + 1}</span>
                    <span class="text-12-mono text-v2-text-text-base">{step.tool}</span>
                    <Show when={step.needs.length}>
                      <span class="text-12-regular text-v2-text-text-faint">after {step.needs.join(", ")}</span>
                    </Show>
                    <span class="flex-1" />
                    <Show when={live()}>{(one) => <Pill tone={STATE_LOOK[one().state].tone}>{STATE_LOOK[one().state].word}</Pill>}</Show>
                  </div>
                  <Show when={step.why}>
                    <p class="text-12-regular text-v2-text-text-muted">{step.why}</p>
                  </Show>
                  <Show when={step.exit}>
                    <p class="text-12-regular text-v2-text-text-faint">done when {step.exit}</p>
                  </Show>
                </li>
              )
            }}
          </For>
        </ol>
      </Block>

      <Block title="What it will cost" hint="your model's tokens and requests, wall-clock time and disk">
        <div class="flex flex-col gap-1">
          <For each={COST_DIMENSIONS.filter((dimension) => build().cost[dimension])}>
            {(dimension) => {
              const estimate = () => build().cost[dimension]!
              return (
                <div class="flex flex-col gap-0.5">
                  <div class="flex items-center gap-2 text-12-regular">
                    <span class="w-40 shrink-0 text-v2-text-text-muted">{DIMENSION_LABEL[dimension]}</span>
                    <span
                      class="tabular-nums"
                      classList={{
                        "text-v2-text-text-base": estimate().provenance !== "UNKNOWN",
                        "text-v2-text-text-faint": estimate().provenance === "UNKNOWN",
                      }}
                    >
                      {magnitude(estimate())}
                    </span>
                    <Pill tone={estimate().provenance === "MEASURED" ? "good" : "muted"}>{estimate().provenance}</Pill>
                  </div>
                  <p class="text-12-regular text-v2-text-text-faint">
                    {estimate().how}
                    {estimate().provenance === "UNKNOWN" && estimate().findOutBy ? ` To find out: ${estimate().findOutBy}` : ""}
                  </p>
                </div>
              )
            }}
          </For>
        </div>
      </Block>

      <Show when={build().environment}>
        {(env) => (
          <Block title="Where it runs">
            <Facts
              rows={[
                ["sandbox", env().name],
                ["working folder", env().workingDir],
                ["network", env().egress ? `allowed - ${env().egressReason || "no reason given"}` : "none"],
                ["installs", env().installs.length ? env().installs.join(", ") : null],
              ]}
            />
          </Block>
        )}
      </Show>

      <Show when={build().risks.length > 0}>
        <Block title="What could go wrong">
          <For each={build().risks}>
            {(risk) => (
              <p class="text-12-regular">
                <span class="text-v2-text-text-base">{risk.what}</span>
                <span class="text-v2-text-text-muted">{` ${risk.whatWeDo}`}</span>
              </p>
            )}
          </For>
        </Block>
      </Show>

      <Show when={build().questions.length > 0}>
        <Block title="What we need from you" hint="the parts only you can answer">
          <For each={build().questions}>
            {(question) => (
              <div class="flex flex-col">
                <p class="text-[13px] text-v2-text-text-base">{question.ask}</p>
                <p class="text-12-regular text-v2-text-text-muted">{question.why}</p>
                <Show when={question.fact}>
                  <p class="text-12-regular text-v2-text-text-faint">
                    <span class="text-12-mono">{question.fact}</span> answered through{" "}
                    <span class="text-12-mono">{question.answeredBy}</span>
                  </p>
                </Show>
              </div>
            )}
          </For>
        </Block>
      </Show>

      <Show when={build().exit}>
        <p class="flex items-start gap-1.5 text-12-regular text-v2-text-text-base">
          <Icon name="check" size="small" />
          <span>
            <span class="[font-weight:530]">Done when</span> {build().exit}
          </span>
        </p>
      </Show>

      <Switch
        fallback={
          <Show
            when={denial()}
            fallback={
              <ApprovalAsk
                proposal={props.proposal}
                asking={asking()}
                threadId={props.threadId}
                refused={refused()}
                onAllow={() => void allow()}
                onDeny={() => {
                  const record: Denial = { at: new Date().toISOString(), reason: "clicked" }
                  writeDenial(props.threadId, props.proposal.approve, record)
                  setDenial(record)
                }}
              />
            }
          >
            {(denied) => (
              <div class="flex flex-wrap items-center gap-2 rounded-md bg-v2-background-bg-layer-01 px-3 py-2 text-12-regular">
                <span class="text-v2-text-text-base">Denied by you</span>
                <span class="text-v2-text-text-faint">{new Date(denied().at).toLocaleString()}</span>
                <span class="text-v2-text-text-muted">
                  Nothing ran. A denial starts nothing, so the engine has no row for it; this record is your browser's.
                </span>
                <Button
                  size="small"
                  variant="ghost"
                  onClick={() => {
                    writeDenial(props.threadId, props.proposal.approve, null)
                    setDenial(null)
                  }}
                >
                  Ask again
                </Button>
              </div>
            )}
          </Show>
        }
      >
        <Match when={storm()}>
          {(current) => (
            <StormProgress storm={current()} onStop={(id) => void stop(id)} error={refused() ?? stormError()} />
          )}
        </Match>
        <Match when={props.threadId !== undefined && !settled()}>
          <p data-slot="storm-reading" class="text-12-regular text-v2-text-text-muted">
            Reading whether this plan was approved…
          </p>
        </Match>
        <Match when={stormError()}>
          {(why) => (
            <div class="flex flex-wrap items-center gap-2 rounded-md bg-v2-background-bg-layer-01 px-3 py-2">
              <p data-slot="storm-error" class="text-12-regular text-v2-state-fg-danger">
                Could not read whether this plan was already approved, so it is not offered for approval yet: {why()}
              </p>
              <Button size="small" variant="ghost" onClick={() => setTick((n) => n + 1)}>
                Read again
              </Button>
            </div>
          )}
        </Match>
      </Switch>
    </>
  )
}

function ApprovalAsk(props: {
  proposal: Proposal
  asking: boolean
  threadId: number | undefined
  refused: string | undefined
  onAllow: () => void
  onDeny: () => void
}) {
  return (
    <div class="flex flex-col gap-2 rounded-md bg-v2-background-bg-layer-01 px-3 py-2">
      <p class="text-[13px] text-v2-text-text-base">
        Run this plan: <span class="[font-weight:530]">{props.proposal.build.title}</span>
      </p>
      <div class="flex flex-wrap items-center gap-2">
        <Button
          size="small"
          variant="submit"
          disabled={props.asking || props.threadId === undefined}
          onClick={props.onAllow}
        >
          {props.asking ? "Approving…" : "Allow once"}
        </Button>
        <Button size="small" variant="neutral" onClick={props.onDeny}>
          Deny
        </Button>
      </div>
      <Show when={props.refused}>
        <p class="text-12-regular text-v2-state-fg-danger">{props.refused}</p>
      </Show>
      <p class="text-12-regular text-v2-text-text-faint">
        Approving binds this exact plan - <span class="text-12-mono">{props.proposal.approve.slice(0, 16)}</span>, the hash
        of everything above. What is sent is not the plan: the harness is handed the question this proposal was made from
        and that hash, proposes again, and records nothing if what it would run now is not what you are looking at.
        <Show when={props.threadId === undefined}>
          {" "}A storm belongs to a conversation, and this proposal has none open.
        </Show>
      </p>
    </div>
  )
}

/** A storm's progress - the outgoing `StormCard.tsx`. n of m, never a percentage. */
export function StormProgress(props: { storm: Storm; onStop: (id: number) => void; error?: string }) {
  const look = () => STATE_LOOK[props.storm.state]
  const done = () => props.storm.steps.filter((step) => step.state === "done").length
  return (
    <div class="flex flex-col gap-1.5 rounded-md bg-v2-background-bg-layer-01 px-3 py-2">
      <div class="flex flex-wrap items-center gap-2">
        <Pill tone={look().tone}>{look().word}</Pill>
        <span class="text-12-regular tabular-nums text-v2-text-text-muted">
          {done()} of {props.storm.steps.length} steps done
        </span>
        <span class="text-12-mono text-v2-text-text-faint">storm {props.storm.id}</span>
        <span class="flex-1" />
        <Show when={stormIsRunning(props.storm.state)}>
          <Button size="small" variant="neutral" icon="stop" onClick={() => props.onStop(props.storm.id)}>
            Stop
          </Button>
        </Show>
      </div>
      <p class="text-12-regular text-v2-text-text-muted">
        Approved <span class="text-12-mono">{props.storm.fingerprint.slice(0, 16)}</span>
        {props.storm.approvedAt ? ` at ${new Date(props.storm.approvedAt).toLocaleString()}` : ""}. What runs is what is in
        that hash; {props.storm.live ? "this engine is running it now." : "nothing is running it in this engine process."}
      </p>
      <Show when={props.storm.stalled.length > 0}>
        <Note tone="warn">
          {props.storm.stalled.length === 1
            ? "One step was running when the engine stopped"
            : `${props.storm.stalled.length} steps were running when the engine stopped`}{" "}
          - {props.storm.stalled.join(", ")}. Whether the work landed is not knowable from here, so nothing restarts it on
          an assumption.
        </Note>
      </Show>
      <Show when={props.storm.deviations.length > 0}>
        <ul class="flex list-disc flex-col pl-5 text-12-regular text-v2-state-fg-warning">
          <For each={props.storm.deviations}>{(note) => <li>{note}</li>}</For>
        </ul>
      </Show>
      <Show when={props.storm.verification}>
        {(check) => (
          <p class="text-12-regular" classList={{ "text-v2-state-fg-success": check().ok, "text-v2-state-fg-danger": !check().ok }}>
            <span class="[font-weight:530]">{check().ok ? "It worked" : "It did not"}</span> {check().stated} - {check().because}
          </p>
        )}
      </Show>
      <Show when={props.error}>
        <p class="text-12-regular text-v2-state-fg-danger">{props.error}</p>
      </Show>
    </div>
  )
}
