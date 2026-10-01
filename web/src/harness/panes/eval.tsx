import { createMemo, createSignal, For, Match, Show, Switch } from "solid-js"
import { Button } from "@opencode/ui/button"
import { Select } from "@opencode/ui/select"
import { PaneEmpty } from "../panel/frame"
import type { PaneProps } from "../panel/panes"
import { ErrorLine, kindIn, ProvenanceTag, Row, Section, useHarnessRefresh } from "../ui"
import { shortModelName } from "../providers/local"
import { Meter, SERIES, TONE } from "./chart"
import { allReadsOf, liveWork, pollWhile, toolResults, useThreadEvents } from "./eval-events"
import {
  currentReport,
  distinctReports,
  dominantMode,
  failureModeRoute,
  failureModeWord,
  pct,
  readEvalReport,
  scoreIsAnOpinion,
  type EvalFailure,
  type EvalReport,
} from "./eval-report"

/**
 * One eval run, drawn: the score with its interval, what the score rests on,
 * where the failures went, and the rows that failed.
 *
 * Ported from the outgoing `EvalReportBody` (frontend/src/components/
 * EvalCard.tsx) and the `EvalPane` around it in PaneStack.tsx. The original
 * was handed its reports by the shell, folded out of the transcript. This
 * pane reads them itself from the thread's event log (eval-events.ts), so it
 * works the same in a pop-out window with no chat around it.
 *
 * Milestone 3's rule still decides where this lives: nothing heavy streams
 * into the transcript. A run returns twenty failing rows, and twenty expanded
 * rows is a wall in a chat column. The transcript keeps the one-line result;
 * the rows are a thing a person comes here to read.
 */
export default function EvalPane(props: PaneProps) {
  return (
    <Show
      when={props.threadId}
      // KEYED: a new thread mounts a new body, so the previous thread's
      // reports, pick and polling do not stay on screen while the new log reads.
      keyed
      fallback={<PaneEmpty title="No conversation open">Open a chat to see the eval runs it has made.</PaneEmpty>}
    >
      {(threadId) => <EvalRuns threadId={threadId} />}
    </Show>
  )
}

function EvalRuns(props: { threadId: number }) {
  const thread = useThreadEvents(() => props.threadId)
  const reports = createMemo(() => distinctReports(allReadsOf(toolResults(thread.events()), readEvalReport)))
  const live = createMemo(() => liveWork(thread.events()).evals)

  // The original re-read on every event; with no stream here, a running eval
  // is re-read on an interval until its `eval.finished` arrives, then the
  // pane goes quiet and waits for a person to ask again.
  // LIVE: the log is re-read on this chat's eval events and tool results
  // (session/refresh.ts) - the report itself lands as a tool result, after
  // `eval.finished` has already stopped the poll below, which stays as the
  // fallback while a run is grading.
  useHarnessRefresh(props.threadId, () => void thread.read.refetch(), kindIn("eval", "tool.result"))
  pollWhile(() => live().length > 0, 3000, () => void thread.read.refetch())

  // `null` is "the newest", so a run that lands while the pane is open
  // becomes the subject without fighting an explicit pick, which sticks.
  const [picked, setPicked] = createSignal<number | null>(null)
  const report = createMemo(() => currentReport(reports(), picked()))

  return (
    <div class="flex flex-col pb-6">
      <Section
        title={reports().length > 1 ? `${reports().length} runs in this conversation` : "Eval run"}
        action={
          <Button size="small" variant="ghost" onClick={() => void thread.read.refetch()} disabled={thread.read.data.loading}>
            {thread.read.data.loading ? "Reading" : "Read again"}
          </Button>
        }
      >
        <For each={live()}>
          {(run) => (
            <div class="flex items-center gap-3 px-4 py-1 text-12-regular text-v2-text-text-muted">
              <span class="shrink-0 tabular-nums">Run {run.runId} is grading</span>
              <div class="min-w-0 flex-1">
                <Meter value={run.planned > 0 ? run.graded / run.planned : null} color={TONE.info} height={6} />
              </div>
              <span class="shrink-0 tabular-nums">
                {run.graded} of {run.planned || "?"}
              </span>
            </div>
          )}
        </For>
        <Show when={reports().length > 1}>
          <div class="px-4 pb-1">
            <Select
              aria-label="Eval run"
              options={reports()}
              current={report() ?? undefined}
              value={(entry) => String(entry.runId)}
              label={pickerLabel}
              onSelect={(entry) => entry && setPicked(entry.runId)}
              placement="bottom-start"
              gutter={6}
            />
          </div>
        </Show>
      </Section>

      <Switch>
        <Match when={thread.read.data.error}>
          <ErrorLine error={thread.read.data.error} />
        </Match>
        <Match when={report()}>{(current) => <ReportBody report={current()} />}</Match>
        {/* Before the log answers there is nothing to say "no run" about. */}
        <Match when={!thread.read.data.answered}>
          <PaneEmpty title="Reading…" />
        </Match>
        <Match when={live().length === 0}>
          <PaneEmpty title="No eval run in this conversation yet">
            Ask in the chat to score the model on an eval file, or run run_eval from the Controls panel. Its score, its
            interval, the failure buckets and the rows that failed appear here.
          </PaneEmpty>
        </Match>
      </Switch>
    </div>
  )
}

/**
 * A picker row asks the card's question again: a judge's 30% printed in the
 * same words as a rule's 96% would reintroduce, one level up, the defect the
 * card exists to close. So a model-graded run says so in its label.
 */
function pickerLabel(entry: EvalReport) {
  const score = entry.score === null ? `${entry.graded}/${entry.planned}` : pct(entry.score)
  const how = scoreIsAnOpinion(entry) ? "judged by a model" : entry.metric
  return `#${entry.runId} · ${how}${entry.promptIsDefault ? " · baseline" : ""} · ${score}`
}

function ReportBody(props: { report: EvalReport }) {
  const score = () => (props.report.complete ? props.report.score : props.report.partialScore)
  const opinion = () => scoreIsAnOpinion(props.report)
  return (
    <>
      <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 pt-1 pb-2">
        <Show
          when={score() !== null}
          fallback={<span class="text-20-medium text-v2-text-text-faint">no score</span>}
        >
          {/* A judge's number keeps its slot - it is what was asked for - and
              loses the ink a reading gets, the same way a partial run's does. */}
          <span
            class="text-20-medium tabular-nums"
            classList={{
              "text-v2-text-text-base": props.report.complete && !opinion(),
              "text-v2-text-text-muted": !props.report.complete || opinion(),
            }}
          >
            {pct(score() ?? 0)}
          </span>
        </Show>
        <span class="text-12-regular text-v2-text-text-muted tabular-nums">
          {props.report.correct} of {props.report.graded} rows right
          <Show when={!props.report.complete}>
            {` · partial, ${props.report.planned - props.report.graded} still to grade`}
          </Show>
        </span>
        <Show when={opinion()}>
          <span class="text-12-regular text-v2-text-text-muted">· a model's opinion, not a reading</span>
        </Show>
        <Show when={props.report.reused}>
          <span class="text-12-regular text-v2-text-text-faint">answered from the stored run; nothing was spent</span>
        </Show>
      </div>

      <Show when={score() !== null}>
        <ScoreScale report={props.report} score={score() ?? 0} />
      </Show>

      <Show when={props.report.selfGraded}>{(self) => <SelfGradedNote self={self()} />}</Show>

      <Section title="What this many rows can resolve">
        <Resolution report={props.report} />
      </Section>

      <Section title={`Where the failures went · ${props.report.failuresTotal} failing rows`}>
        <Buckets report={props.report} />
      </Section>

      <Section title="The rows that failed">
        <Failures report={props.report} />
      </Section>

      <RunFacts report={props.report} />
    </>
  )
}

/**
 * The score on a 0-100% track with its 95% interval drawn to the same scale,
 * and a marker where answering the most common label every time would land.
 * The one claim made here is the engine's arithmetic on the engine's own two
 * numbers: does the interval clear the trivial baseline? If not, the score
 * has not been shown to beat doing nothing, and that is a finding worth a hue.
 */
function ScoreScale(props: { report: EvalReport; score: number }) {
  const ci = () => props.report.resolution.ci95
  const trivial = () => props.report.trivialBaselineScore
  const beats = () => {
    const interval = ci()
    const floor = trivial()
    return floor === null || interval === null ? null : interval[0] > floor
  }
  return (
    <div class="flex flex-col gap-1 px-4 pb-2">
      <Meter
        value={props.score}
        band={ci()}
        marker={trivial()}
        markerColor={beats() === false ? TONE.bad : TONE.label}
        color={scoreIsAnOpinion(props.report) ? TONE.label : TONE.data}
        height={10}
        title={
          ci()
            ? `95% confidence: ${pct(ci()![0], 1)} to ${pct(ci()![1], 1)}`
            : "No interval: nothing was graded"
        }
      />
      <div class="flex justify-between text-12-regular text-v2-text-text-faint">
        <span>0%</span>
        <span>{props.report.metric}</span>
        <span>100%</span>
      </div>
      <Show when={trivial() !== null}>
        <p
          class="text-12-regular"
          classList={{
            "text-v2-state-fg-danger": beats() === false,
            "text-v2-text-text-muted": beats() !== false,
          }}
        >
          Answering "{props.report.trivialAnswer ?? "the most common label"}" to every row scores{" "}
          {pct(trivial() ?? 0, 1)} on these same rows
          {beats() === false
            ? ", and this score's interval does not clear it. On this eval set the model has not been shown to beat doing nothing."
            : "."}
        </p>
      </Show>
    </div>
  )
}

/**
 * Immediately under the number and not four sections down: a disclosure
 * that a model graded the answers is what the number rests on, so it sits
 * where a reader who has just taken the score has not yet moved past it.
 */
function SelfGradedNote(props: { self: NonNullable<EvalReport["selfGraded"]> }) {
  const rules = () => Object.entries(props.self.deterministic)
  return (
    <div class="mx-4 mb-2 flex flex-col gap-1 rounded-md bg-v2-background-bg-layer-01 px-3 py-2 text-12-regular">
      <div class="text-v2-text-text-base" title={props.self.judgeModel}>
        {props.self.isTheModelThatAnswered
          ? `This score is ${shortModelName(props.self.judgeModel)}'s opinion of its own answers`
          : `This score is ${shortModelName(props.self.judgeModel)}'s opinion of another model's answers`}
        <span class="text-v2-text-text-muted">
          {` · ${props.self.rowsJudged} row${props.self.rowsJudged === 1 ? "" : "s"} judged`}
        </span>
      </div>
      <Show
        when={rules().length > 0}
        fallback={
          <div class="text-v2-text-text-muted">
            No rule could grade these rows, so there is no second reading to put beside the judge.
          </div>
        }
      >
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-v2-text-text-muted">
          <span class="inline-flex items-center gap-1.5">
            The same rows, graded by rule <ProvenanceTag value="measured" />
          </span>
          <For each={rules()}>
            {([name, value]) => (
              <span class="tabular-nums">
                <span class="text-v2-text-text-base">{pct(value, 1)}</span> {name}
              </span>
            )}
          </For>
        </div>
      </Show>
      <Show when={props.self.warning}>
        <div class="text-v2-text-text-muted">{props.self.warning}</div>
      </Show>
    </div>
  )
}

function Resolution(props: { report: EvalReport }) {
  const resolution = () => props.report.resolution
  return (
    <Show
      when={resolution().n > 0}
      fallback={<div class="px-4 py-1 text-12-regular text-v2-text-text-muted">Nothing was graded, so there is no score and no interval.</div>}
    >
      <Show when={resolution().halfWidthPoints !== null}>
        <Row label="95% interval">±{resolution().halfWidthPoints!.toFixed(1)} points</Row>
      </Show>
      <Show when={resolution().resolvesDifferenceOfPoints !== null}>
        <Row label="Can resolve">a difference of {resolution().resolvesDifferenceOfPoints!.toFixed(0)} points or more</Row>
      </Show>
      <Row label="Rows graded">{resolution().n}</Row>
      <Show when={resolution().says}>
        <div class="px-4 py-1 text-12-regular text-v2-text-text-muted">{resolution().says}</div>
      </Show>
      <Show when={resolution().method}>
        <div class="px-4 py-1 text-12-regular text-v2-text-text-faint">{resolution().method}</div>
      </Show>
    </Show>
  )
}

/**
 * Where the failures went and where the diagnosis would route them. The bars
 * take the categorical series colours, not verdict colours: a failure bucket
 * is a category, not a judgement.
 */
function Buckets(props: { report: EvalReport }) {
  const entries = () => Object.entries(props.report.failureHistogram).sort((a, b) => b[1] - a[1])
  const total = () => entries().reduce((sum, [, count]) => sum + count, 0) + props.report.unclassified
  const max = () => Math.max(1, ...entries().map(([, count]) => count), props.report.unclassified)
  const dominant = () => dominantMode(props.report.failureHistogram)
  return (
    <Show
      when={total() > 0}
      fallback={
        <div class="px-4 py-1 text-12-regular text-v2-text-text-muted">
          No row was bucketed. Either nothing failed, or the failures carried no mode the engine has a route for.
        </div>
      }
    >
      <For each={entries()}>
        {([mode, count], index) => (
          <BucketRow
            name={failureModeWord(mode)}
            count={count}
            share={count / max()}
            color={SERIES[index() % SERIES.length]}
            route={failureModeRoute(mode) ? `to ${failureModeRoute(mode)}` : "no route"}
          />
        )}
      </For>
      <Show when={props.report.unclassified > 0}>
        <BucketRow
          name="Unclassified"
          count={props.report.unclassified}
          share={props.report.unclassified / max()}
          color={TONE.label}
          route="no rule matched"
        />
      </Show>
      <Show when={dominant()}>
        {(top) => (
          <div class="px-4 pt-1 text-12-regular text-v2-text-text-muted">
            {top().dominates
              ? `${failureModeWord(top().mode)} is ${pct(top().share)} of the bucketed failures, so the diagnosis routes on it${
                  failureModeRoute(top().mode) ? `, to ${failureModeRoute(top().mode)}` : ""
                }.`
              : `No single mode reaches half the failures; the largest is ${failureModeWord(top().mode)} at ${pct(
                  top().share,
                )}. The engine treats that as more than one problem, and one fine-tune cannot fix several.`}
          </div>
        )}
      </Show>
      <Show when={props.report.bucketsDecidedBy}>
        <div class="px-4 pt-1 text-12-regular text-v2-text-text-faint">{props.report.bucketsDecidedBy}</div>
      </Show>
    </Show>
  )
}

function BucketRow(props: { name: string; count: number; share: number; color: string; route: string }) {
  return (
    <div class="flex min-h-7 items-center gap-3 px-4 text-12-regular">
      <span class="w-28 shrink-0 truncate text-v2-text-text-base">{props.name}</span>
      <div class="min-w-0 flex-1">
        <Meter value={props.share} color={props.color} height={6} />
      </div>
      <span class="w-8 shrink-0 text-right tabular-nums text-v2-text-text-base">{props.count}</span>
      <span class="w-24 shrink-0 truncate text-v2-text-text-faint">{props.route}</span>
    </div>
  )
}

/**
 * How many failing rows stand open before the list asks to be unfolded.
 * Measured in the outgoing card rather than chosen by taste: eight fills the
 * space a reader scans before deciding, and the rest are already in the
 * payload, one click and no round trip away.
 */
const FAILURES_SHOWN = 8

function Failures(props: { report: EvalReport }) {
  const [all, setAll] = createSignal(false)
  const shown = () => (all() ? props.report.failures : props.report.failures.slice(0, FAILURES_SHOWN))
  const hidden = () => props.report.failures.length - shown().length
  return (
    <Show
      when={props.report.failures.length > 0}
      fallback={
        <div class="px-4 py-1 text-12-regular text-v2-text-text-muted">
          {props.report.failuresTotal === 0
            ? "No row failed."
            : `${props.report.failuresTotal} rows failed, and none of them came back in this reply.`}
        </div>
      }
    >
      <For each={shown()}>{(row) => <FailingRow row={row} />}</For>
      <Show when={hidden() > 0}>
        <div class="px-2">
          <Button size="small" variant="ghost" icon="chevron-down" onClick={() => setAll(true)}>
            Show the other {hidden()} failing rows
          </Button>
        </div>
      </Show>
      <Show when={props.report.failuresTotal > props.report.failures.length}>
        <div class="px-4 py-1 text-12-regular text-v2-text-text-faint">
          {props.report.failuresTotal - props.report.failures.length} more failing rows were not returned in this reply.
          Every one is stored; ask for more and the bench reads them off disk without asking the model anything.
        </div>
      </Show>
    </Show>
  )
}

/**
 * One failing row, one line until opened. `<details>` rather than a
 * hand-rolled toggle: the browser already implements the disclosure pattern,
 * its keyboard and its screen-reader semantics.
 */
function FailingRow(props: { row: EvalFailure }) {
  return (
    <details class="group px-4">
      <summary class="flex min-h-7 cursor-pointer list-none items-center gap-2 text-12-regular">
        <span class="shrink-0 tabular-nums text-v2-text-text-faint">#{props.row.rowIndex}</span>
        <span class="min-w-0 flex-1 truncate text-v2-text-text-base">{props.row.input}</span>
        <Show when={props.row.failureMode}>
          <span class="shrink-0 text-v2-text-text-muted">{failureModeWord(props.row.failureMode!)}</span>
        </Show>
      </summary>
      <div class="flex flex-col gap-1 rounded-md bg-v2-background-bg-layer-01 px-3 py-2 mb-2">
        <Pair label="asked" value={props.row.input} />
        <Pair label="expected" value={props.row.expected} />
        <Pair label="answered" value={props.row.answer} />
        <div class="flex flex-wrap gap-x-3 gap-y-1 pt-1 text-12-regular text-v2-text-text-faint">
          <Show when={props.row.gradedBy}>
            <span>graded by {props.row.gradedBy}</span>
          </Show>
          <Show when={props.row.bucketedBy}>
            <span>bucketed by {props.row.bucketedBy}</span>
          </Show>
          <Show when={props.row.seconds !== null}>
            <span class="tabular-nums">{props.row.seconds!.toFixed(2)}s</span>
          </Show>
          <For each={Object.entries(props.row.verdicts)}>
            {([name, hit]) => (
              <span classList={{ "text-v2-state-fg-success": hit, "text-v2-state-fg-danger": !hit }}>
                {name} {hit ? "yes" : "no"}
              </span>
            )}
          </For>
        </div>
      </div>
    </details>
  )
}

function Pair(props: { label: string; value: string }) {
  return (
    <div class="flex gap-3 text-12-regular">
      <span class="w-16 shrink-0 text-v2-text-text-muted">{props.label}</span>
      <span class="min-w-0 flex-1 whitespace-pre-wrap break-words text-12-mono text-v2-text-text-base">
        {props.value || <i class="text-v2-text-text-faint">empty</i>}
      </span>
    </div>
  )
}

/** What was run, against what, under which prompt: the reproducibility block. */
function RunFacts(props: { report: EvalReport }) {
  const r = () => props.report
  return (
    <details class="px-4 pt-2">
      <summary class="cursor-pointer list-none text-12-medium text-v2-text-text-muted">
        How this was run
        <span class="text-12-regular text-v2-text-text-faint" title={r().model ?? undefined}>
          {` · ${shortModelName(r().model) || "unknown model"} · ${r().metric}${r().promptIsDefault ? " · baseline prompt" : " · custom prompt"}`}
        </span>
      </summary>
      <div class="-mx-4 pt-1">
        <Row label="Run">#{r().runId}</Row>
        <Row label="File">
          <span title={r().evalPath}>{r().evalPath}</span>
        </Row>
        <Row label="Fields">
          {r().inputField ?? "?"} to {r().expectedField ?? "?"}
        </Row>
        <Row label="Rows">
          {r().graded} graded of {r().rowsAvailable ?? "?"} available
        </Row>
        <Row label="Model">
          <span title={r().model ?? undefined}>{shortModelName(r().model) || "?"}</span> ({r().provider ?? "?"},{" "}
          {r().locality ?? "?"})
        </Row>
        <Row label="Metric">{r().metric}</Row>
        <Show when={r().judgeModel}>
          <Row label="Judge">
            <span title={r().judgeModel ?? undefined}>{shortModelName(r().judgeModel)}</span>
          </Row>
        </Show>
        {/* The fingerprint is the field compare() refuses on, so it is worth
            being able to read off two runs and check by eye. */}
        <Show when={r().evalFingerprint}>
          <Row label="Eval fingerprint">{r().evalFingerprint}</Row>
        </Show>
        <Row label="Prompt">
          <span title={r().prompt ?? ""}>
            {r().promptIsDefault ? "the default, so this run is the baseline the gates read" : (r().prompt ?? "(none)")}
          </span>
        </Row>
        <Show when={Object.keys(r().scores).length > 1}>
          <Row label="Every metric">
            {Object.entries(r().scores)
              .map(([name, value]) => `${name} ${pct(value, 1)}`)
              .join(" · ")}
          </Row>
        </Show>
      </div>
    </details>
  )
}
