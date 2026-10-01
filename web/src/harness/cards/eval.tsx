import { createSignal, For, Show } from "solid-js"
import { Button } from "@opencode/ui/button"
import { ProvenanceTag } from "../ui"
import { Meter, SERIES, TONE } from "../panes/chart"
import {
  dominantMode,
  failureModeRoute,
  failureModeWord,
  pct,
  scoreIsAnOpinion,
  type EvalFailure,
  type EvalReport,
} from "../panes/eval-report"
import { Block, Facts, Fold, Note, Pill } from "./frame"
import type { EvalComparison } from "./readers"
import { shortModelName } from "../providers/local"

/**
 * The eval card and the comparison card - parity 5.11 and 5.20.
 *
 * Ported from the outgoing `EvalCard.tsx` (`EvalCard`, `EvalCompareCard`),
 * on the Eval pane's own reader and vocabulary (`panes/eval-report.ts`) and
 * its chart (`panes/chart.tsx`). The rules kept: a score is never shown
 * without its resolution; a model-graded score loses the ink a reading gets
 * and says whose opinion it is; a comparison that cannot resolve its
 * difference headlines the words "No evidence", never the delta.
 */

const FAILURES_SHOWN = 6

export function EvalBody(props: { report: EvalReport }) {
  const r = () => props.report
  const score = () => (r().complete ? r().score : r().partialScore)
  const opinion = () => scoreIsAnOpinion(r())
  const ci = () => r().resolution.ci95
  const trivial = () => r().trivialBaselineScore
  const beats = () => {
    const interval = ci()
    const floor = trivial()
    return floor === null || interval === null ? null : interval[0] > floor
  }
  return (
    <>
      <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Show when={score() !== null} fallback={<span class="text-16-medium text-v2-text-text-faint">no score</span>}>
          <span
            class="text-20-medium tabular-nums"
            classList={{
              "text-v2-text-text-base": !opinion() && r().complete,
              "text-v2-text-text-muted": opinion() || !r().complete,
            }}
          >
            {pct(score()!)}
          </span>
        </Show>
        <span class="text-12-regular tabular-nums text-v2-text-text-muted">
          {r().correct} of {r().graded} rows right
          {r().complete ? "" : ` · partial, ${r().planned - r().graded} still to grade`}
        </span>
        <ProvenanceTag value={opinion() ? "declared" : "measured"} />
        <Show when={r().reused}>
          <span class="text-12-regular text-v2-text-text-faint">answered from the stored run; nothing was spent</span>
        </Show>
      </div>

      <Show when={score() !== null}>
        <div class="flex flex-col gap-1">
          <Meter
            value={score()}
            band={ci()}
            marker={trivial()}
            markerColor={beats() === false ? TONE.bad : TONE.label}
            color={opinion() ? TONE.label : TONE.data}
            height={10}
            title={ci() ? `95% confidence: ${pct(ci()![0], 1)} to ${pct(ci()![1], 1)}` : "No interval: nothing was graded"}
          />
          <div class="flex justify-between text-12-regular text-v2-text-text-faint">
            <span>0%</span>
            <span>{r().metric}</span>
            <span>100%</span>
          </div>
          <Show when={trivial() !== null}>
            <Note tone={beats() === false ? "bad" : "muted"}>
              Answering "{r().trivialAnswer ?? "the most common label"}" to every row scores {pct(trivial()!, 1)} on these
              same rows
              {beats() === false
                ? ", and this score's interval does not clear it. On this eval set the model has not been shown to beat doing nothing."
                : "."}
            </Note>
          </Show>
        </div>
      </Show>

      <Show when={r().selfGraded}>
        {(self) => (
          <div class="flex flex-col gap-1 rounded-md bg-v2-background-bg-layer-01 px-3 py-2 text-12-regular">
            <span class="text-v2-text-text-base">
              {self().isTheModelThatAnswered
                ? `This score is ${self().judgeModel}'s opinion of its own answers`
                : `This score is ${self().judgeModel}'s opinion of another model's answers`}
              <span class="text-v2-text-text-muted">{` · ${self().rowsJudged} row${self().rowsJudged === 1 ? "" : "s"} judged`}</span>
            </span>
            <Show
              when={Object.keys(self().deterministic).length > 0}
              fallback={<span class="text-v2-text-text-muted">No rule could grade these rows, so there is no second reading to put beside the judge.</span>}
            >
              <span class="flex flex-wrap items-center gap-x-3 text-v2-text-text-muted">
                <span class="inline-flex items-center gap-1.5">
                  the same rows, graded by rule <ProvenanceTag value="measured" />
                </span>
                <For each={Object.entries(self().deterministic)}>
                  {([name, value]) => (
                    <span class="tabular-nums">
                      <span class="text-v2-text-text-base">{pct(value, 1)}</span> {name}
                    </span>
                  )}
                </For>
              </span>
            </Show>
            <Show when={self().warning}>
              <span class="text-v2-text-text-muted">{self().warning}</span>
            </Show>
          </div>
        )}
      </Show>

      <Block title="What this many rows can resolve">
        <Show when={r().resolution.n > 0} fallback={<Note>Nothing was graded, so there is no score and no interval.</Note>}>
          <Facts
            rows={[
              ["95% interval", r().resolution.halfWidthPoints !== null ? `±${r().resolution.halfWidthPoints!.toFixed(1)} points` : null],
              [
                "can resolve",
                r().resolution.resolvesDifferenceOfPoints !== null
                  ? `a difference of ${r().resolution.resolvesDifferenceOfPoints!.toFixed(0)} points or more`
                  : null,
              ],
              ["rows graded", r().resolution.n],
            ]}
          />
          <Show when={r().resolution.says}>
            <Note>{r().resolution.says}</Note>
          </Show>
        </Show>
      </Block>

      <Block title="Where the failures went" hint={`${r().failuresTotal} failing rows`}>
        <Buckets report={r()} />
      </Block>

      <Block title="The rows that failed" hint="what to write the next prompt against">
        <Failures report={r()} />
      </Block>

      <Fold
        summary="How this was run"
        hint={`${shortModelName(r().model) || "unknown model"} · ${r().metric}${r().promptIsDefault ? " · baseline prompt" : " · custom prompt"}`}
      >
        <Facts
          rows={[
            ["run", `#${r().runId}`],
            ["file", r().evalPath],
            ["fields", `${r().inputField ?? "?"} to ${r().expectedField ?? "?"}`],
            ["rows", `${r().graded} graded of ${r().rowsAvailable ?? "?"} available`],
            ["model", `${shortModelName(r().model) || "?"} (${r().provider ?? "?"}, ${r().locality ?? "?"})`],
            ["judge", r().judgeModel],
            ["eval fingerprint", r().evalFingerprint],
            ["prompt", r().promptIsDefault ? "the default, so this run is the baseline the gates read" : (r().prompt ?? "(none)")],
            [
              "every metric",
              Object.keys(r().scores).length > 1
                ? Object.entries(r().scores)
                    .map(([name, value]) => `${name} ${pct(value, 1)}`)
                    .join(" · ")
                : null,
            ],
          ]}
        />
      </Fold>
    </>
  )
}

function Buckets(props: { report: EvalReport }) {
  const entries = () => Object.entries(props.report.failureHistogram).sort((a, b) => b[1] - a[1])
  const max = () => Math.max(1, ...entries().map(([, n]) => n), props.report.unclassified)
  const dominant = () => dominantMode(props.report.failureHistogram)
  return (
    <Show
      when={entries().length > 0 || props.report.unclassified > 0}
      fallback={<Note>No row was bucketed. Either nothing failed, or the failures carried no mode the engine has a route for.</Note>}
    >
      <For each={entries()}>
        {([mode, n], index) => (
          <BucketRow
            name={failureModeWord(mode)}
            count={n}
            share={n / max()}
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
          <Note>
            {top().dominates
              ? `${failureModeWord(top().mode)} is ${pct(top().share)} of the bucketed failures, so the diagnosis routes on it${
                  failureModeRoute(top().mode) ? `, to ${failureModeRoute(top().mode)}` : ""
                }.`
              : `No single mode reaches half the failures; the largest is ${failureModeWord(top().mode)} at ${pct(top().share)}. One fine-tune cannot fix several problems.`}
          </Note>
        )}
      </Show>
    </Show>
  )
}

function BucketRow(props: { name: string; count: number; share: number; color: string; route: string }) {
  return (
    <div class="flex min-h-6 items-center gap-3 text-12-regular">
      <span class="w-28 shrink-0 truncate text-v2-text-text-base">{props.name}</span>
      <div class="min-w-0 flex-1">
        <Meter value={props.share} color={props.color} height={6} />
      </div>
      <span class="w-8 shrink-0 text-right tabular-nums text-v2-text-text-base">{props.count}</span>
      <span class="w-24 shrink-0 truncate text-v2-text-text-faint">{props.route}</span>
    </div>
  )
}

function Failures(props: { report: EvalReport }) {
  const [all, setAll] = createSignal(false)
  const shown = () => (all() ? props.report.failures : props.report.failures.slice(0, FAILURES_SHOWN))
  return (
    <Show
      when={props.report.failures.length > 0}
      fallback={
        <Note>
          {props.report.failuresTotal === 0
            ? "No row failed."
            : `${props.report.failuresTotal} rows failed, and none of them came back in this reply.`}
        </Note>
      }
    >
      <For each={shown()}>{(row) => <FailingRow row={row} />}</For>
      <Show when={props.report.failures.length > shown().length}>
        <div>
          <Button size="small" variant="ghost" icon="chevron-down" onClick={() => setAll(true)}>
            Show the other {props.report.failures.length - shown().length} failing rows
          </Button>
        </div>
      </Show>
      <Show when={props.report.failuresTotal > props.report.failures.length}>
        <Note>
          {props.report.failuresTotal - props.report.failures.length} more failing rows were not returned in this reply. Every
          one is stored; the Eval panel reads them off disk without asking the model anything.
        </Note>
      </Show>
    </Show>
  )
}

function FailingRow(props: { row: EvalFailure }) {
  return (
    <details>
      <summary class="flex min-h-6 cursor-pointer list-none items-center gap-2 text-12-regular">
        <span class="shrink-0 tabular-nums text-v2-text-text-faint">#{props.row.rowIndex}</span>
        <span class="min-w-0 flex-1 truncate text-v2-text-text-base">{props.row.input}</span>
        <Show when={props.row.failureMode}>
          <span class="shrink-0 text-v2-text-text-muted">{failureModeWord(props.row.failureMode!)}</span>
        </Show>
      </summary>
      <div class="my-1 rounded-md bg-v2-background-bg-layer-01 px-3 py-2">
        <Facts
          rows={[
            ["asked", props.row.input || "(empty)"],
            ["expected", props.row.expected || "(empty)"],
            ["answered", props.row.answer || "(empty)"],
            ["graded by", props.row.gradedBy],
            ["bucketed by", props.row.bucketedBy],
          ]}
        />
      </div>
    </details>
  )
}

/** Two runs over the same eval set, paired row by row. */
export function CompareBody(props: { comparison: EvalComparison }) {
  const c = () => props.comparison
  return (
    <>
      <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Show
          when={c().resolved}
          fallback={
            <>
              <span class="text-20-medium text-v2-text-text-muted">No evidence</span>
              <span class="text-12-regular text-v2-text-text-muted">
                {c().changed === 0 ? "Not one row changed its verdict" : "This eval set cannot tell these two apart"}
              </span>
            </>
          }
        >
          <span
            class="text-20-medium tabular-nums"
            classList={{ "text-v2-state-fg-success": c().delta >= 0, "text-v2-state-fg-danger": c().delta < 0 }}
          >
            {c().delta > 0 ? "+" : ""}
            {pct(c().delta, 1)}
          </span>
          <span class="text-12-regular text-v2-text-text-base">A real difference on this eval set</span>
        </Show>
        <Show when={c().resolved} fallback={<Pill tone="muted" title="McNemar's exact test could not separate these two runs.">NO EVIDENCE</Pill>}>
          <ProvenanceTag value="measured" />
        </Show>
      </div>

      <div class="flex flex-col gap-1">
        <ScoreLine label={`run ${c().against}`} score={c().scoreAgainst} color={SERIES[1]} />
        <ScoreLine label={`run ${c().runId}`} score={c().score} color={SERIES[0]} />
        <Note>
          Both measured on {c().measuredOn ?? `the ${c().pairedRows} rows both runs graded`}
          {c().sameRows ? "." : ", which is not every row either run graded - each run's own score may differ from these."}
        </Note>
      </div>

      <Block title="The rows that changed" hint="what the test actually reads">
        <Facts
          rows={[
            ["improved", `${c().improved}${c().improvedRows.length ? ` - rows ${c().improvedRows.slice(0, 12).join(", ")}` : ""}`],
            ["regressed", `${c().regressed}${c().regressedRows.length ? ` - rows ${c().regressedRows.slice(0, 12).join(", ")}` : ""}`],
            ["changed", `${c().changed} of ${c().pairedRows} paired rows`],
            ["test", `${c().test ?? "McNemar exact"}, p = ${c().pValue.toPrecision(3)}`],
          ]}
        />
      </Block>

      <Show when={!c().resolved && c().rowsThatWouldResolveThisDelta !== null}>
        <Note>
          About {Math.ceil(c().rowsThatWouldResolveThisDelta!).toLocaleString("en")} rows would resolve a difference this size -
          the unpaired worst case; the paired test may need fewer, which is the thing being measured.
        </Note>
      </Show>

      <Show when={c().says}>
        <Fold summary="The bench's own summary">
          <Note>{c().says}</Note>
        </Fold>
      </Show>
    </>
  )
}

function ScoreLine(props: { label: string; score: number | null; color: string }) {
  return (
    <div class="flex items-center gap-3 text-12-regular">
      <span class="w-20 shrink-0 text-12-mono text-v2-text-text-muted">{props.label}</span>
      <div class="min-w-0 flex-1">
        <Meter value={props.score} color={props.color} height={6} />
      </div>
      <span class="w-14 shrink-0 text-right tabular-nums text-v2-text-text-base">
        {props.score === null ? "—" : pct(props.score, 1)}
      </span>
    </div>
  )
}
