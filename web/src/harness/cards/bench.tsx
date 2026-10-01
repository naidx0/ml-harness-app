import { For, Show } from "solid-js"
import { Icon } from "@opencode/ui/icon"
import { ProvenanceTag } from "../ui"
import { Meter, TONE } from "../panes/chart"
import { failureModeWord, pct } from "../panes/eval-report"
import type { RecallReport } from "../panes/stage-data"
import { CompareBody } from "./eval"
import { Block, Facts, Fold, Note, Pill, type Tone } from "./frame"
import type { ChunkingSweep, PromptAttempt } from "./readers"
import { baseName } from "./result"
import { shortModelName } from "../providers/local"

/**
 * The prompt bench and the retrieval bench - parity 5.20.
 *
 * Ported from the outgoing `PromptCard.tsx` and `RetrievalCard.tsx`
 * (`ChunkingSweepCard`, `RetrieverRecallCard`), trimmed to what a transcript
 * card must carry; the Stage's retrieval panel draws the full curve.
 */

const PROMPT_VERDICT: Record<string, { word: string; tone: Tone; says: string }> = {
  first: { word: "First version", tone: "muted", says: "There was nothing to compare this against yet, so it becomes the one to beat." },
  different: { word: "Better", tone: "good", says: "The eval set could resolve this difference, and more rows improved than regressed." },
  no_evidence: { word: "No evidence", tone: "muted", says: "This eval set cannot tell the two versions apart, so nothing was promoted." },
  incomplete: { word: "Unfinished", tone: "muted", says: "The run stopped before it graded every row, so it has no score to compare." },
  not_comparable: { word: "Not comparable", tone: "muted", says: "The two versions share no graded row, so there is nothing to pair." },
  different_models: {
    word: "Different models",
    tone: "muted",
    says: "These two versions were scored on different models, so the difference is not the prompt.",
  },
}

export function PromptBody(props: { attempt: PromptAttempt }) {
  const a = () => props.attempt
  const look = () =>
    PROMPT_VERDICT[a().verdict] ?? { word: a().verdict, tone: "muted" as Tone, says: "The bench returned a verdict this surface has no treatment for." }
  return (
    <>
      {/* Not the score first: the question a person scanning the thread asks
          is "did my change stick", and the bench already computed it. */}
      <div class="flex flex-wrap items-center gap-2">
        <Icon name={a().championChanged ? "check" : "outline-eye"} size="small" />
        <span class="text-[13px] text-v2-text-text-base [font-weight:530]">
          {a().championChanged
            ? `Version ${a().version} is the new one to beat`
            : a().verdict === "first"
              ? `Version ${a().version} is the one to beat`
              : "Not promoted"}
        </span>
        <Pill tone={look().tone}>{look().word}</Pill>
        <ProvenanceTag value="measured" />
      </div>
      <Show when={!a().championChanged && a().againstVersion !== null}>
        <Note>Version {a().againstVersion} is still the one to beat.</Note>
      </Show>
      <Note>{look().says}</Note>
      <Show when={a().changeNote}>
        <Facts rows={[["what changed", a().changeNote]]} />
      </Show>
      <Show when={a().targeted}>
        {(target) => (
          <Note tone={target().resolved ? "good" : "muted"}>
            {failureModeWord(target().mode)} was the target: {target().fixed} of {target().rows} fixed.
            {target().says ? ` ${target().says}` : ""}
          </Note>
        )}
      </Show>
      <Show when={a().comparison}>
        {(comparison) => (
          <Block title={`Against version ${a().againstVersion ?? "?"}`}>
            <CompareBody comparison={comparison()} />
          </Block>
        )}
      </Show>
      <Show when={a().text}>
        <Fold
          summary={`Version ${a().version} in full`}
          hint={[a().author ? `by ${a().author}` : "", a().exemplars ? `${a().exemplars} exemplars` : ""].filter(Boolean).join(" · ")}
        >
          <pre class="max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-v2-background-bg-layer-01 px-3 py-2 text-12-mono text-v2-text-text-base">
            {a().text}
          </pre>
        </Fold>
      </Show>
      <Show when={a().measuredNothing}>
        <Note>{a().measuredNothing}</Note>
      </Show>
      <Facts rows={[["line", a().lineName], ["eval set", a().evalPath ? baseName(a().evalPath) : null], ["model", shortModelName(a().model) || null], ["run", a().runId !== null ? `#${a().runId}` : null]]} />
    </>
  )
}

/** The sweep's headline word, the outgoing card's `sweepPill`. */
export function sweepPill(sweep: ChunkingSweep): { word: string; title: string } {
  if (sweep.state === "refused") return { word: "NOTHING BUILT", title: "This call was refused before any index was written." }
  if (sweep.state === "plan") return { word: "NOT RUN", title: "Nothing was built. The counts on this card are what it would do." }
  if (sweep.state === "nothing_compared") return { word: "NOTHING COMPARED", title: "The sweep stopped before it reached a comparison." }
  if (sweep.verdict === "no_evidence") {
    return { word: "NO EVIDENCE", title: "Not one pairwise test separated any two of these settings on this eval set." }
  }
  return {
    word: "NOTHING CROWNED",
    title:
      "Some pairs separated. No setting was crowned: the best recall in a sweep is a maximum selected on the same questions it would be reported against.",
  }
}

export function SweepBody(props: { sweep: ChunkingSweep }) {
  const s = () => props.sweep
  const pill = () => sweepPill(s())
  return (
    <>
      <div class="flex flex-wrap items-center gap-2">
        <Pill tone="muted" title={pill().title}>
          {pill().word}
        </Pill>
        <Show when={s().corpusPath}>
          <span class="text-12-mono text-v2-text-text-muted" title={s().corpusPath!}>
            {baseName(s().corpusPath!)}
          </span>
        </Show>
      </div>
      <Show when={s().says}>
        <p class="text-[13px] text-v2-text-text-base">{s().says}</p>
      </Show>

      <Show when={s().state === "plan" && s().planned.length > 0}>
        <Block title="What it would do" hint={`${s().planned.length} settings`}>
          <ul class="flex flex-col text-12-mono text-v2-text-text-base">
            <For each={s().planned}>{(setting) => <li>{setting}</li>}</For>
          </ul>
        </Block>
      </Show>

      <Show when={s().perSetting.length > 0}>
        <Block title="Per setting" hint={`on the ${s().comparedQuestions} questions every setting scored`}>
          <For each={s().perSetting}>
            {(row) => (
              <div class="flex items-center gap-3 text-12-regular">
                <span class="w-24 shrink-0 text-12-mono text-v2-text-text-base">{row.setting}</span>
                <div class="min-w-0 flex-1">
                  <Meter value={row.recall} color={TONE.data} height={6} />
                </div>
                <span class="w-24 shrink-0 text-right tabular-nums text-v2-text-text-base">
                  {row.hits} of {row.of}
                </span>
                <span
                  class="w-24 shrink-0 truncate text-v2-text-text-faint"
                  title={s().notBeatenByAnything.includes(row.setting) ? "No other setting separated from this one" : undefined}
                >
                  {s().notBeatenByAnything.includes(row.setting) ? "not beaten" : ""}
                </span>
              </div>
            )}
          </For>
        </Block>
      </Show>

      <Show when={s().comparisons.length > 0}>
        <Fold summary="The pairwise tests" hint={`${s().separatedN} of ${s().familySize || s().comparisons.length} separated`}>
          <div class="flex flex-col gap-0.5">
            <For each={s().comparisons}>
              {(pair) => (
                <div class="flex flex-wrap items-center gap-2 text-12-regular">
                  <span class="text-12-mono text-v2-text-text-base">
                    {pair.a} vs {pair.b}
                  </span>
                  <span class="tabular-nums text-v2-text-text-muted">
                    {pair.aBetterOn} / {pair.bBetterOn} of {pair.changed} changed
                  </span>
                  <span class="tabular-nums text-v2-text-text-faint">
                    p {pair.p.toPrecision(2)}
                    {pair.adjustedP !== null ? `, adjusted ${pair.adjustedP.toPrecision(2)}` : ""}
                  </span>
                  <Pill tone={pair.separated ? "good" : "muted"}>{pair.separated ? `${pair.better ?? "one"} better` : "not separated"}</Pill>
                </div>
              )}
            </For>
          </div>
        </Fold>
      </Show>

      <Show when={s().whyNothingIsCrowned}>
        <Note>{s().whyNothingIsCrowned}</Note>
      </Show>
      <Show when={s().confirmation}>
        {(check) => (
          <Note tone={check().ok ? "muted" : "warn"}>
            Chosen on half, confirmed on the other half: {check().says ?? check().why ?? (check().ok ? "held" : "did not hold")}
          </Note>
        )}
      </Show>
      <Note>{s().stampsNothing}</Note>
    </>
  )
}

export function RecallBody(props: { report: RecallReport }) {
  const r = () => props.report
  return (
    <>
      <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Show when={r().recall !== null} fallback={<span class="text-16-medium text-v2-text-text-faint">no recall</span>}>
          <span class="text-20-medium tabular-nums text-v2-text-text-base">{pct(r().recall!)}</span>
        </Show>
        <span class="text-12-regular tabular-nums text-v2-text-text-muted">
          recall at {r().k} · {r().hits ?? 0} of {r().questionsScored} questions
        </span>
        <Show when={r().stampable} fallback={<Pill tone="muted" title="This run did not stamp retriever_recall_at_k. The reason is below.">NOT STAMPED</Pill>}>
          <ProvenanceTag value="measured" />
        </Show>
      </div>
      <Show when={r().curve.length > 1}>
        <Block title="Recall rises with k">
          <For each={r().curve}>
            {(point) => (
              <div class="flex items-center gap-3 text-12-regular">
                <span class="w-12 shrink-0 tabular-nums text-v2-text-text-muted">k = {point.k}</span>
                <div class="min-w-0 flex-1">
                  <Meter value={point.recall} color={TONE.data} height={6} />
                </div>
                <span class="w-20 shrink-0 text-right tabular-nums text-v2-text-text-base">
                  {point.hits} of {point.of}
                </span>
              </div>
            )}
          </For>
        </Block>
      </Show>
      <Show when={!r().stampable && r().notMeasured}>
        <Note tone="warn">{r().notMeasured}</Note>
      </Show>
      <Show when={r().unresolvedN > 0}>
        <Note>
          {r().unresolvedN} question{r().unresolvedN === 1 ? "" : "s"} named a right passage no index row could be matched to, so{" "}
          {r().unresolvedN === 1 ? "it was" : "they were"} left out of the denominator
          {r().unresolvedRows.length ? `: ${r().unresolvedRows.slice(0, 5).join(", ")}` : ""}.
        </Note>
      </Show>
      <Facts
        rows={[
          ["index", r().indexName ?? (r().indexId !== null ? `#${r().indexId}` : null)],
          ["questions", `${r().questionsScored} scored of ${r().questionsEligible} eligible`],
        ]}
      />
    </>
  )
}
