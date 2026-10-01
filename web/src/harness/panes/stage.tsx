import { createMemo, createSignal, For, Match, Show, Switch, type JSX } from "solid-js"
import { Button } from "@opencode/ui/button"
import { Select } from "@opencode/ui/select"
import { Tabs } from "@opencode/ui/tabs"
import { PaneEmpty } from "../panel/frame"
import type { PaneProps } from "../panel/panes"
import { ErrorLine, ProvenanceTag, Row, Section, useHarnessRead, useHarnessRefresh } from "../ui"
import { LineChart, Meter, SERIES, Swatch, TONE } from "./chart"
import { allReadsOf, latestReadOf, liveWork, pollWhile, toolResults, useThreadEvents } from "./eval-events"
import { gateLedger } from "./evidence-ledger"
import { GateBadge, OriginTag } from "./evidence-origin"
import { detachStage, isStageWindow } from "./stage-detach"
import { Lattice } from "./stage-lattice"
import {
  benchReading,
  currentRun,
  factValue,
  gatesReading,
  pct,
  points,
  progressionReading,
  READING_LABEL,
  readCarve,
  readRecall,
  retrievalReading,
  runLabel,
  sandboxReading,
  secondsLabel,
  shortModel,
  STAGE_PANELS,
  targetOf,
  trainRuns,
  type Carve,
  type Reading,
  type RecallReport,
  type StagePanelId,
  type StagePayload,
  type StageRun,
  type StageSandbox,
  type StageSandboxRun,
} from "./stage-data"

/**
 * The Stage: one instrument surface, five panels.
 *
 * Ported from the outgoing `frontend/src/components/Stage.tsx`. Everything
 * it draws arrives in one read, `GET /api/threads/{id}/stage` (app/stage.py):
 * each run's rows, the paired verdicts against the baseline, the sandboxes
 * and their run logs, the card, the diagnosis. The recall and carve results
 * the Retrieval panel needs are not on that route - the outgoing Stage took
 * them from the transcript - so they are read from the thread's event log,
 * like the Eval pane's reports. The Stage computes no statistic: every
 * p-value, delta and resolution is the engine's, quoted with its run id.
 *
 * The outgoing Stage had three sizes of one thing (inline row, split,
 * detached window). Here the split is this side-panel tab, the pop-out
 * button in the frame gives a pane-sized window, and "Detach" opens the
 * shell's own large Stage window. The inline transcript row is a tool card,
 * which is not this file's to draw.
 *
 * It re-reads on an interval only while something in the thread is spending
 * - an eval grading, a training job without its terminal event - because
 * the original refreshed off the event stream, which is silent otherwise.
 */
export default function StagePane(props: PaneProps) {
  return (
    <Show
      when={props.threadId}
      // KEYED: a new thread mounts a new surface. Unkeyed, the surface stayed
      // mounted and its reads kept the previous thread's last value on screen
      // (with its run selection and its polling) until the new read answered.
      keyed
      fallback={<PaneEmpty title="No conversation open">Open a chat to see what it has measured.</PaneEmpty>}
    >
      {(threadId) => <StageSurface threadId={threadId} />}
    </Show>
  )
}

function StageSurface(props: { threadId: number }) {
  const stage = useHarnessRead<StagePayload>(() => `/api/threads/${props.threadId}/stage`)
  const thread = useThreadEvents(() => props.threadId)
  const results = createMemo(() => toolResults(thread.events()))
  const recalls = createMemo(() => allReadsOf(results(), readRecall))
  const carve = createMemo(() => latestReadOf(results(), readCarve))
  const spending = createMemo(() => {
    const live = liveWork(thread.events())
    return live.evals.length > 0 || live.trains.length > 0
  })
  const refresh = () => {
    void stage.refetch()
    void thread.read.refetch()
  }
  // LIVE: every engine event for this chat can move the Stage (a run, a
  // grade, a result, a sub-agent), so it re-reads on each, gathered
  // (session/refresh.ts). The poll stays as the fallback while a run spends -
  // a pop-out hears no session, and a small eval says little between its
  // start and its end.
  useHarnessRefresh(props.threadId, refresh)
  pollWhile(spending, 4000, refresh)

  // The error first: a failed read has no last value, and everything below
  // draws from the last good one while a poll is in flight.
  const payload = () => (stage.data.error ? undefined : stage.data())

  // One selection shared by every panel, as in the outgoing Stage: which run
  // (null = the newest complete one) and which panel.
  const [panel, setPanel] = createSignal<StagePanelId>("bench")
  const [runId, setRunId] = createSignal<number | null>(null)
  const run = createMemo(() => {
    const data = payload()
    return data ? currentRun(data, runId()) : null
  })

  return (
    <div class="flex flex-col pb-6">
      <div class="flex items-center gap-2 px-4 pt-1 pb-2">
        <Show when={spending()}>
          <span class="text-12-regular text-v2-state-fg-info">A run is spending; re-reading every few seconds</span>
        </Show>
        <span class="flex-1" />
        <Button size="small" variant="ghost" onClick={refresh} disabled={stage.data.loading}>
          {stage.data.loading ? "Reading" : "Read again"}
        </Button>
        <Show when={!isStageWindow()}>
          <Button size="small" variant="ghost" icon="square-arrow-top-right" onClick={() => void detachStage(props.threadId)}>
            Detach
          </Button>
        </Show>
      </div>

      <Tabs variant="pill" value={panel()} onChange={(value: string) => setPanel(value as StagePanelId)}>
        <Tabs.List class="no-scrollbar overflow-x-auto px-4">
          <For each={STAGE_PANELS}>{(entry) => <Tabs.Trigger value={entry.id}>{entry.title}</Tabs.Trigger>}</For>
        </Tabs.List>
      </Tabs>

      <Switch fallback={<PaneEmpty title={stage.data.answered ? "Nothing reported" : "Reading…"} />}>
        <Match when={stage.data.error}>
          <ErrorLine error={stage.data.error} />
        </Match>
        <Match when={payload()}>
          {(data) => (
            <>
              <Show when={data().runs.length > 0 && (panel() === "bench" || panel() === "progression")}>
                <div class="px-4 pt-2">
                  <Select
                    aria-label="Eval run"
                    options={data().runs}
                    current={run() ?? undefined}
                    value={(entry) => String(entry.run_id)}
                    label={(entry) =>
                      `${entry.run_id} · ${runLabel(entry, data().baseline_run_id)} · ${
                        entry.complete ? pct(entry.score) : `${entry.graded}/${entry.planned}`
                      }`
                    }
                    onSelect={(entry) => entry && setRunId(entry.run_id)}
                    placement="bottom-start"
                    gutter={6}
                  />
                </div>
              </Show>
              <Switch>
                <Match when={panel() === "bench"}>
                  <BenchPanel payload={data()} selected={run()} onPick={setRunId} />
                </Match>
                <Match when={panel() === "sandbox"}>
                  <SandboxPanel payload={data()} />
                </Match>
                <Match when={panel() === "progression"}>
                  <ProgressionPanel payload={data()} />
                </Match>
                <Match when={panel() === "gates"}>
                  <GatesPanel payload={data()} />
                </Match>
                <Match when={panel() === "retrieval"}>
                  <RetrievalPanel recalls={recalls()} carve={carve()} payload={data()} />
                </Match>
              </Switch>
              <Provenance payload={data()} threadId={props.threadId} />
            </>
          )}
        </Match>
      </Switch>
    </div>
  )
}

/* 1 · Bench */

function BenchPanel(props: { payload: StagePayload; selected: StageRun | null; onPick: (runId: number) => void }) {
  const paired = () => (props.selected ? (props.payload.comparisons[String(props.selected.run_id)] ?? null) : null)
  const target = () => targetOf(props.payload)
  return (
    <Show
      when={props.payload.runs.length > 0}
      fallback={<Note>No eval run in this conversation yet. Score the model on an eval file and every row lands here.</Note>}
    >
      <div class="pt-3">
        <Lattice payload={props.payload} selected={props.selected} onPick={props.onPick} />
      </div>
      <Section title={props.selected ? `Run ${props.selected.run_id}${paired() ? ` vs ${paired()!.against}` : ""}` : "No run selected"}>
        <Show when={props.selected}>
          {(selected) => (
            <>
              <Row label="Model">
                <span title={selected().model ?? undefined}>{shortModel(selected().model)}</span>
              </Row>
              <Row label="Judged by">
                {selected().judge_model ? (
                  <span title={selected().judge_model ?? undefined}>{shortModel(selected().judge_model)}</span>
                ) : (
                  selected().metric
                )}
              </Row>
              <Row label="Score">
                {pct(selected().score)}{" "}
                <span class="text-v2-text-text-muted">
                  {selected().correct} of {selected().graded}
                </span>
              </Row>
              <Show when={selected().resolution}>
                {(resolution) => (
                  <>
                    <Row label="95% interval">
                      {pct(resolution().ci_95[0])} to {pct(resolution().ci_95[1])}
                    </Row>
                    <Row label="Resolves">
                      {points(resolution().resolves_a_difference_of_at_least_points, 0)} points or more
                    </Row>
                  </>
                )}
              </Show>
              <Show when={paired()}>
                {(pair) => (
                  <>
                    <Row label="Improved">
                      <span class="text-v2-state-fg-success">{pair().improved}</span>
                    </Row>
                    <Row label="Regressed">
                      <span class="text-v2-state-fg-danger">{pair().regressed}</span>
                    </Row>
                    <Row label="McNemar p">{points(pair().p_value, 3)}</Row>
                    <Row label="Verdict">
                      <span classList={{ "text-v2-state-fg-success": pair().verdict === "different" }}>
                        {pair().verdict === "different" ? "Different" : "No evidence"}
                      </span>
                    </Row>
                    <Show when={pair().rows_that_would_resolve_this_delta}>
                      <Row label="Rows to resolve">{pair().rows_that_would_resolve_this_delta}</Row>
                    </Show>
                  </>
                )}
              </Show>
            </>
          )}
        </Show>
        {/* The bar is drawn when there is one; "no target stated" would be a
            row about a thing that is not there. */}
        <Show when={target()}>
          {(bar) => (
            <Row label="Bar set" tag={<OriginTag origin={bar().origin} />}>
              {pct(bar().value)}
            </Row>
          )}
        </Show>
      </Section>
      <Section title="Scores">
        <ScoreBars payload={props.payload} target={target()?.value ?? null} selected={props.selected?.run_id ?? null} />
      </Section>
      <ReadingBand items={benchReading(props.payload, props.selected, paired(), target()?.value ?? null)} />
      <Glossary panel="bench" />
    </Show>
  )
}

function ScoreBars(props: { payload: StagePayload; target: number | null; selected: number | null }) {
  const sorted = () =>
    props.payload.runs.filter((run) => run.complete && run.score !== null).sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
  // Series colours for what kind of arm a run is: trained, control, prompt.
  const colour = (run: StageRun) =>
    /adapter/i.test(run.model ?? "") ? SERIES[1] : run.run_id === props.payload.baseline_run_id ? TONE.label : SERIES[0]
  return (
    <For each={sorted()}>
      {(run) => (
        <div class="flex min-h-7 items-center gap-3 px-4 text-12-regular">
          {/* The selected run in gold - selection, as in the lattice above -
              never the accent, which is for send and focus. */}
          <span
            class="w-28 shrink-0 truncate text-v2-text-text-base"
            style={{ color: run.run_id === props.selected ? "var(--harness-gold)" : undefined }}
          >
            {runLabel(run, props.payload.baseline_run_id)} <span class="text-v2-text-text-faint">{run.run_id}</span>
          </span>
          <div class="min-w-0 flex-1">
            <Meter value={run.score} color={colour(run)} marker={props.target} height={8} />
          </div>
          <span class="w-10 shrink-0 text-right tabular-nums text-v2-text-text-base">{pct(run.score)}</span>
        </div>
      )}
    </For>
  )
}

/* 2 · Sandbox */

function SandboxPanel(props: { payload: StagePayload }) {
  const gpu = () => props.payload.gpu
  const boxes = () => props.payload.sandboxes.filter((box) => box.ok !== false)
  return (
    <>
      <Section title="The card, now">
        <Show
          when={gpu().occupancy}
          fallback={<Note>No NVIDIA card answered. The guard has nothing to read.</Note>}
        >
          {(occupancy) => (
            <>
              <Row label="GPU memory" tag={<ProvenanceTag value="measured" source={occupancy().source} />}>
                {points(occupancy().used_gb)} <span class="text-v2-text-text-muted">of {points(occupancy().total_gb)} GB in use</span>
              </Row>
              <div class="px-4 pb-1">
                <Meter
                  value={occupancy().total_gb > 0 ? occupancy().used_gb / occupancy().total_gb : null}
                  marker={occupancy().total_gb > 0 ? gpu().crowded_above_gb / occupancy().total_gb : null}
                  markerColor={TONE.warn}
                  color={gpu().guard ? TONE.bad : SERIES[0]}
                  height={10}
                  title={occupancy().source}
                />
                <div class="flex flex-wrap gap-x-3 pt-1 text-12-regular text-v2-text-text-muted">
                  <Swatch color={gpu().guard ? TONE.bad : SERIES[0]}>in use</Swatch>
                  <Swatch color={TONE.warn} line>
                    crowded above {gpu().crowded_above_gb} GB
                  </Swatch>
                </div>
              </div>
              <Row label="Resident models">
                {occupancy().resident.length === 0
                  ? "none"
                  : occupancy()
                      .resident.map((model) => `${model.name} (${model.size_gb} GB)`)
                      .join(", ")}
              </Row>
              <Row label="Guard">
                <span classList={{ "text-v2-state-fg-danger": !!gpu().guard, "text-v2-state-fg-success": !gpu().guard }}>
                  {gpu().guard ? "crowded, a training run is refused" : "card free, a run is allowed"}
                </span>
              </Row>
              <Show when={gpu().guard}>
                <Note>{gpu().guard}</Note>
              </Show>
            </>
          )}
        </Show>
      </Section>
      <Show when={boxes().length > 0} fallback={<Note>No sandbox in this project yet.</Note>}>
        <For each={boxes()}>{(box) => <SandboxCard box={box} />}</For>
      </Show>
      <ReadingBand items={sandboxReading(props.payload)} />
      <Glossary panel="sandbox" />
    </>
  )
}

function SandboxCard(props: { box: StageSandbox }) {
  const pinned = () => props.box.pinned ?? {}
  const curves = () => props.box.runs.filter((run) => run.kind === "train" && run.curve.length > 1).slice(0, 3)
  return (
    <Section
      title={`${props.box.name} · ${pinned().recipe ?? "no recipe"}${pinned().pinned ? " · pinned" : ""}${
        props.box.reach?.egress ? " · egress on" : " · no egress"
      } · ${props.box.runs.length} run${props.box.runs.length === 1 ? "" : "s"}`}
    >
      <Show when={props.box.purpose}>
        <Note>{props.box.purpose}</Note>
      </Show>
      <Row label="Interpreter">
        <span title={pinned().interpreter}>{pinned().interpreter?.replace(/^.*[\\/]recipes[\\/]/, "recipes/") ?? "—"}</span>
      </Row>
      <Row
        label="Environment on disk"
        tag={pinned().on_disk_gb !== undefined ? <ProvenanceTag value="measured" /> : undefined}
      >
        {pinned().on_disk_gb !== undefined ? `${points(pinned().on_disk_gb, 2)} GB` : "—"}
      </Row>
      <For each={props.box.snapshotted ?? []}>
        {(snap) => (
          <Row label={snap.path.replace(/^.*[\\/]/, "")}>
            {(snap.bytes / 1024).toFixed(1)} KB <span class="text-12-mono text-v2-text-text-faint">{snap.digest.slice(0, 12)}</span>
          </Row>
        )}
      </For>
      <Show when={props.box.runs.length > 0} fallback={<Note>No runs inside yet.</Note>}>
        <For each={props.box.runs}>{(run) => <SandboxRunRow run={run} />}</For>
      </Show>
      <Show when={curves().length > 0}>
        <div class="px-4 pt-2">
          <LineChart
            label={`Training loss by step in ${props.box.name}`}
            xUnit="steps"
            height={120}
            series={curves().map((run, index) => ({
              id: run.name,
              color: SERIES[index % SERIES.length],
              points: run.curve.map((point) => ({ x: point.step, y: point.loss })),
            }))}
          />
        </div>
      </Show>
    </Section>
  )
}

function SandboxRunRow(props: { run: StageSandboxRun }) {
  return (
    <div class="flex min-h-7 items-center gap-3 px-4 text-12-regular">
      <span class="w-24 shrink-0 truncate text-12-mono text-v2-text-text-base">{props.run.name}</span>
      <span class="min-w-0 flex-1 truncate text-v2-text-text-muted" title={props.run.base_model ?? undefined}>
        {props.run.kind ?? "—"}
        {props.run.max_steps ? ` · ${props.run.max_steps} steps` : ""}
        {props.run.base_model ? ` · ${shortModel(props.run.base_model)}` : ""}
      </span>
      <span class="shrink-0 tabular-nums text-v2-text-text-base">{secondsLabel(props.run.elapsed_seconds)}</span>
      <span class="w-20 shrink-0 text-right tabular-nums text-v2-text-text-faint">
        {props.run.peak_vram_gb !== null ? `${points(props.run.peak_vram_gb, 2)} GB peak` : ""}
      </span>
    </div>
  )
}

/* 3 · Progression */

function ProgressionPanel(props: { payload: StagePayload }) {
  const series = () => trainRuns(props.payload).slice(0, 3)
  const target = () => targetOf(props.payload)
  const adapters = () => props.payload.runs.filter((run) => run.complete && /adapter/i.test(run.model ?? ""))
  const baseline = () => props.payload.runs.find((run) => run.run_id === props.payload.baseline_run_id) ?? null
  return (
    <>
      <Section title="Training loss">
        <Show when={series().length > 0} fallback={<Note>No training run with a loss curve in this project's sandboxes.</Note>}>
          <div class="px-4">
            <LineChart
              label="Training loss by step"
              xUnit="steps"
              series={series().map((entry, index) => ({
                id: entry.run.name,
                color: SERIES[index % SERIES.length],
                points: entry.run.curve.map((point) => ({ x: point.step, y: point.loss })),
              }))}
            />
            <div class="flex flex-col gap-1 pt-1 text-12-regular text-v2-text-text-muted">
              <For each={series()}>
                {(entry, index) => (
                  <Swatch color={SERIES[index() % SERIES.length]} line>
                    {entry.box}/{entry.run.name} · {entry.run.steps ?? entry.run.max_steps ?? "?"} steps ·{" "}
                    {secondsLabel(entry.run.elapsed_seconds)}
                    {entry.run.final_loss !== null ? ` · final loss ${points(entry.run.final_loss, 2)}` : ""}
                  </Swatch>
                )}
              </For>
            </div>
          </div>
        </Show>
      </Section>
      <Section title="Held-out, same judge, same rows">
        <Show when={baseline()}>
          {(base) => <Row label={`Baseline · ${base().run_id}`}>{pct(base().score)}</Row>}
        </Show>
        <For each={adapters()}>
          {(run) => {
            const delta = () => props.payload.comparisons[String(run.run_id)]?.delta ?? null
            return (
              <Row label={`${shortModel(run.model)} · ${run.run_id}`}>
                {pct(run.score)}
                <Show when={delta() !== null}>
                  <span
                    classList={{
                      "text-v2-state-fg-danger": delta()! < 0,
                      "text-v2-state-fg-success": delta()! > 0,
                    }}
                  >
                    {` ${delta()! < 0 ? "▾" : "▴"}${Math.abs(Math.round(delta()! * 100))}`}
                  </span>
                </Show>
              </Row>
            )
          }}
        </For>
        <Show when={!baseline() && adapters().length === 0}>
          <Note>No baseline or adapter run scored yet.</Note>
        </Show>
        <Show when={target()}>
          {(bar) => (
            <Row label="Target" tag={<OriginTag origin={bar().origin} />}>
              {pct(bar().value)}
            </Row>
          )}
        </Show>
      </Section>
      <ReadingBand items={progressionReading(series(), adapters(), baseline())} />
      <Glossary panel="progression" />
    </>
  )
}

/* 4 · Gate map */

function GatesPanel(props: { payload: StagePayload }) {
  const diagnosis = () => props.payload.diagnosis
  const ledger = () => gateLedger(diagnosis()?.verdict?.gates)
  return (
    <Show when={diagnosis()} fallback={<Note>No diagnosis in this conversation yet.</Note>}>
      {(report) => (
        <>
          <Section title={`${report().verdict?.outcome ?? "No verdict"} · ${ledger().passed} of ${ledger().of} gates passed`}>
            <For each={ledger().gates}>
              {(gate, index) => {
                const clause = () => report().verdict?.gates?.[gate.id]?.clause
                return (
                  <div class="flex flex-col px-4 py-1" title={gate.asks}>
                    <div class="flex min-h-6 items-center gap-3 text-12-regular">
                      <span class="w-4 shrink-0 tabular-nums text-v2-text-text-faint">{index()}</span>
                      <span class="min-w-0 flex-1 truncate text-v2-text-text-base">{gate.name}</span>
                      <GateBadge status={gate.status} />
                    </div>
                    <Show when={clause()}>
                      <div class="pl-7 text-12-mono break-words text-v2-text-text-faint">{clause()}</div>
                    </Show>
                  </div>
                )
              }}
            </For>
            <Show when={report().verdict?.say}>
              <Note>"{report().verdict!.say}"</Note>
            </Show>
          </Section>
          <Section title="Facts on record">
            <For each={report().facts ?? []} fallback={<Note>No facts recorded yet.</Note>}>
              {(fact) => (
                <div class="flex min-h-7 items-center gap-3 px-4 text-12-regular" title={fact.how ?? undefined}>
                  <span class="w-40 shrink-0 truncate text-12-mono text-v2-text-text-base">{fact.fact}</span>
                  <span class="min-w-0 flex-1 truncate tabular-nums text-v2-text-text-base">{factValue(fact.value)}</span>
                  <OriginTag origin={fact.origin} />
                  <Show when={fact.tool}>
                    <span class="max-w-24 shrink-0 truncate text-12-mono text-v2-text-text-faint">{fact.tool}</span>
                  </Show>
                </div>
              )}
            </For>
          </Section>
          <ReadingBand items={gatesReading(report(), ledger().passed)} />
          <Glossary panel="gates" />
        </>
      )}
    </Show>
  )
}

/* 5 · Retrieval & split */

function RetrievalPanel(props: { recalls: RecallReport[]; carve: Carve | null; payload: StagePayload }) {
  // WHICH INDEX. A thread that scored two retrievers holds two measurements,
  // and the newest is not "the" one. The pick is the panel's own, by
  // position: one index can be scored twice (a second k, a corrected ground
  // truth), and those are two measurements with one id.
  const scored = () => props.recalls.filter((report) => report.curve.length > 0)
  const [picked, setPicked] = createSignal<number>(0)
  const recall = () => scored()[picked()] ?? scored()[0] ?? null
  const label = (report: RecallReport) =>
    `${report.indexId ?? "?"} · ${report.indexName ?? "index"} · ${pct(report.recall)}${report.stampable ? "" : " · not recorded"}`
  return (
    <>
      <Section title={recall() ? `Recall by k · ${recall()!.indexName ?? `index ${recall()!.indexId ?? "?"}`}` : "Recall by k"}>
        <Show when={scored().length > 1}>
          <div class="px-4 pb-1">
            <Select
              aria-label="Index scored"
              options={scored().map((report, index) => ({ report, index }))}
              current={recall() ? { report: recall()!, index: picked() } : undefined}
              value={(entry) => String(entry.index)}
              label={(entry) => label(entry.report)}
              onSelect={(entry) => entry && setPicked(entry.index)}
              placement="bottom-start"
              gutter={6}
            />
          </div>
        </Show>
        <Show when={recall()} fallback={<Note>No retriever scored in this conversation yet.</Note>}>
          {(report) => (
            <>
              <For each={report().curve}>
                {(point) => (
                  <div class="flex min-h-7 items-center gap-3 px-4 text-12-regular">
                    <span class="w-10 shrink-0 tabular-nums text-v2-text-text-muted">k={point.k}</span>
                    <div class="min-w-0 flex-1">
                      <Meter value={point.recall} color={SERIES[0]} height={8} />
                    </div>
                    <span class="w-24 shrink-0 text-right tabular-nums text-v2-text-text-base">
                      {point.hits}/{point.of} · {pct(point.recall)}
                    </span>
                  </div>
                )}
              </For>
              <Row label="Questions scored">
                {report().questionsScored} of {report().questionsEligible}
              </Row>
              <Row label="Recorded as a fact" tag={report().stampable ? <ProvenanceTag value="measured" /> : undefined}>
                <Show
                  when={report().stampable}
                  fallback={
                    <span class="text-v2-state-fg-danger">
                      no, {report().unresolvedN} row(s) name a document the index lacks
                    </span>
                  }
                >
                  yes
                </Show>
              </Row>
            </>
          )}
        </Show>
      </Section>
      <Section title="Where the rows went">
        <Show when={props.carve} fallback={<Note>No carve in this conversation.</Note>}>
          {(carve) => (
            <>
              <Row label="Read">{carve().rowsRead} rows</Row>
              <Row label="Eval">{carve().evalRows} rows</Row>
              <Row label="Train">{carve().trainRows} rows</Row>
              <Row label="Leak check">
                <Show when={carve().checked} fallback="not run">
                  <span
                    classList={{
                      "text-v2-state-fg-success": carve().leaked === 0,
                      "text-v2-state-fg-danger": carve().leaked !== 0,
                    }}
                  >
                    {carve().leaked ?? "?"} leaked
                  </span>
                </Show>
              </Row>
            </>
          )}
        </Show>
        <Show when={recall() && recall()!.unresolvedRows.length > 0}>
          <div class="px-4 pt-1 text-12-regular text-v2-text-text-muted">Concepts no train-side method can reach</div>
          <div class="px-4 text-12-regular text-v2-state-fg-danger">{Array.from(new Set(recall()!.unresolvedRows)).join(" · ")}</div>
        </Show>
      </Section>
      <ReadingBand items={retrievalReading(recall(), props.carve, props.payload)} />
      <Glossary panel="retrieval" />
    </>
  )
}

/* shared pieces */

function Note(props: { children: JSX.Element }) {
  return <div class="px-4 py-1 text-12-regular text-v2-text-text-muted">{props.children}</div>
}

/** What happened, why it matters, what to do - one claim and one sentence each. */
function ReadingBand(props: { items: Reading[] }) {
  return (
    <Show when={props.items.length > 0}>
      <div class="mx-4 mt-2 flex flex-col gap-2 rounded-md bg-v2-background-bg-layer-01 px-3 py-2">
        <For each={props.items}>
          {(item) => (
            <div class="flex flex-col gap-0.5 text-12-regular">
              <span class="text-12-medium text-v2-text-text-muted">{READING_LABEL[item.k]}</span>
              <span class="text-v2-text-text-muted">
                <span class="text-12-medium text-v2-text-text-base">{item.claim}</span> {item.body}
              </span>
            </div>
          )}
        </For>
      </div>
    </Show>
  )
}

/**
 * The words a panel uses, each with its one-line definition on hover and in
 * its accessible name. Dotted, not coloured: a term is not a claim.
 */
const GLOSSARY: Record<string, string> = {
  "eval set": "The held-out questions nothing trains on. The exam, not the textbook.",
  judge: 'A model answers "was this right?" per row. Sees meaning; can flatter. Every row keeps the rule verdicts beside it.',
  McNemar: "Compares two runs only on rows that flipped. The honest test for a paired comparison.",
  resolution: 'The smallest difference this many rows can see. Below it, "no evidence" is the only honest word.',
  "recall@k": "For each question, is the right document in the retriever's top k. Scores the retriever alone.",
  LoRA: "Trains two small matrices on a frozen base. Cheap, and it can only select what the base already knows.",
  loss: "Surprise at the next true token. Falls as the model memorises the training sentences; says nothing about held-out questions.",
  spill: "Weights that do not fit the card page through system memory. Runs, many times slower, and looks like training in the log.",
  gate: 'A question the ledger will not skip on the way to "train". Only measured or stated facts open one, never a model\'s claim.',
  baseline: "What the connected model scores cold, under the default prompt, before anything changes. Every later run is paired against it.",
  provenance: "Where a number came from: MEASURED by an instrument, STATED by you, ASSERTED by a model (opens nothing), DEFAULTED (nobody measured it).",
}

const PANEL_TERMS: Record<StagePanelId, string[]> = {
  bench: ["eval set", "judge", "McNemar", "resolution", "baseline"],
  sandbox: ["spill", "provenance"],
  progression: ["loss", "LoRA", "eval set"],
  gates: ["gate", "provenance", "baseline"],
  retrieval: ["recall@k", "eval set"],
}

function Glossary(props: { panel: StagePanelId }) {
  return (
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 pt-3 text-12-regular text-v2-text-text-muted">
      <span class="text-v2-text-text-faint">The words</span>
      <For each={PANEL_TERMS[props.panel]}>
        {(term) => (
          <span
            tabindex="0"
            class="cursor-help underline decoration-dotted underline-offset-2"
            title={GLOSSARY[term]}
            aria-label={`${term}: ${GLOSSARY[term]}`}
          >
            {term}
          </span>
        )}
      </For>
    </div>
  )
}

/**
 * Where every number on this surface came from. Everything arrives in one
 * request, and a surface showing that many figures without naming its source
 * would be this product's own defect wearing OpenCode's colours.
 */
function Provenance(props: { payload: StagePayload; threadId: number }) {
  return (
    <details class="px-4 pt-3">
      <summary class="cursor-pointer list-none text-12-regular text-v2-text-text-faint">
        From GET /api/threads/{props.threadId}/stage
      </summary>
      <div class="flex flex-col gap-0.5 pt-1">
        <For each={Object.entries(props.payload.reads ?? {})}>
          {([part, how]) => (
            <div class="flex gap-3 text-12-regular">
              <span class="w-24 shrink-0 text-v2-text-text-muted">{part}</span>
              <span class="min-w-0 flex-1 text-12-mono break-words text-v2-text-text-faint">{how}</span>
            </div>
          )}
        </For>
      </div>
    </details>
  )
}
