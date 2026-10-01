import { createMemo, Match, Show, Switch, type Accessor } from "solid-js"
import { GenericTool } from "@opencode/session-ui/basic-tool"
import { useData } from "@opencode/session-ui/context"
import type { ToolProps } from "@session-ui-src/tools/tool-renderer"
import { readEvalReport } from "../panes/eval-report"
import { readRecall } from "../panes/stage-data"
import { PromptBody, RecallBody, SweepBody, sweepPill } from "./bench"
import { CarveBody, SampleBody, SandboxBody, SynthesisBody, VerificationBody } from "./datawork"
import { DiagnosisBody, VERDICT } from "./diagnosis"
import { CompareBody, EvalBody } from "./eval"
import { CardFrame, Note, StageActions } from "./frame"
import { CARD_TITLE, cardKindOf, STAGED, type CardKind } from "./kinds"
import { ProposalBody } from "./proposal"
import {
  readCarveCard,
  readChunkingSweep,
  readDiagnosisCard,
  readEvalComparison,
  readPlanTick,
  readPromptAttempt,
  readProposal,
  readSandboxResult,
  readSynthesis,
  readVerificationRecord,
  readVerificationSample,
} from "./readers"
import { baseName, firstClause, harnessOf, threadIdFor } from "./result"
import { PlanBody, TurnEffectsFooter, useTurnLog } from "./turn-cards"

/**
 * THE card their renderer draws for every harness tool in `HARNESS_CARD_TOOLS`.
 *
 * It reads the facade's envelope (`metadata.harness`), asks the readers what
 * the result is (`cardKindOf`), and draws that body inside their own tool
 * chrome. A result no reader recognises - and a call still running, which
 * has no result yet - draws exactly what their renderer would have drawn
 * without us, `GenericTool`. Failed calls never arrive here: their renderer
 * draws its error card for those before it asks the registry.
 */

/**
 * The harness thread this tool part belongs to. Their session-ui data
 * context carries the open session's id and the session list; the list
 * carries the facade's `metadata.harness.threadID`. Outside that provider (a
 * pop-out window) there is no transcript and so no thread to find.
 */
function useThreadId(props: ToolProps): Accessor<number | undefined> {
  let data: ReturnType<typeof useData> | undefined
  try {
    data = useData()
  } catch {
    data = undefined
  }
  return createMemo(() => threadIdFor(props.sessionID ?? data?.sessionID, data?.store.session))
}

/** The one line beside the title - what a collapsed card still says. */
function subtitleOf(kind: CardKind, result: unknown): string | undefined {
  switch (kind) {
    case "diagnosis": {
      const d = readDiagnosisCard(result)
      return d ? `${VERDICT[d.verdict]?.word ?? d.verdict} · ${firstClause(d.say, 72) ?? d.outcome}` : undefined
    }
    case "proposal":
      return readProposal(result)?.build.title
    case "eval": {
      const r = readEvalReport(result)
      return r ? `${baseName(r.evalPath)} · run #${r.runId}` : undefined
    }
    case "compare": {
      const c = readEvalComparison(result)
      return c ? `run ${c.runId} against run ${c.against}` : undefined
    }
    case "prompt": {
      const a = readPromptAttempt(result)
      return a ? `${a.lineName} v${a.version}` : undefined
    }
    case "sweep": {
      const s = readChunkingSweep(result)
      return s ? sweepPill(s).word.toLowerCase() : undefined
    }
    case "recall": {
      const r = readRecall(result)
      return r?.indexName ?? undefined
    }
    case "carve": {
      const c = readCarveCard(result)
      return c ? baseName(c.evalPath) : undefined
    }
    case "synthesis": {
      const s = readSynthesis(result)
      return s ? baseName(s.syntheticPath) : undefined
    }
    case "verification-sample": {
      const s = readVerificationSample(result)
      return s ? baseName(s.samplePath) : undefined
    }
    case "verification": {
      const v = readVerificationRecord(result)
      return v ? `${baseName(v.dataset)} · ${v.wrong} wrong of ${v.judged}` : undefined
    }
    case "sandbox":
      return readSandboxResult(result)?.sandbox
    case "plan": {
      const t = readPlanTick(result)
      return t ? (t.ticked ?? t.step ?? "saved") : undefined
    }
  }
}

/** Who ran it, when it was not the model - the outgoing tool row's words. */
export function driver(drivenBy: string | null | undefined): string | null {
  if (drivenBy === "harness") return "Run by the harness: the connected model cannot call tools, so the harness ran this itself."
  if (drivenBy === "user") return "Run by you, from a control through your own door; the engine recorded it on this thread."
  return null
}

export function HarnessResultCard(props: ToolProps) {
  const envelope = createMemo(() => harnessOf(props.metadata))
  const result = () => envelope()?.result
  const kind = createMemo(() => (envelope() && envelope()!.result !== undefined ? cardKindOf(result()) : null))
  const threadId = useThreadId(props)
  const log = useTurnLog(
    threadId,
    () => envelope()?.callID ?? "",
    () => props.tool,
  )
  const footer = () => <TurnEffectsFooter threadId={threadId()} effects={log.effects()} onReverted={() => void log.refresh()} />

  return (
    <Show
      when={kind()}
      fallback={
        <>
          <GenericTool tool={props.tool} status={props.status} hideDetails={props.hideDetails} input={props.input} />
          <Show when={envelope()?.omitted}>
            {(omitted) => (
              <Note>
                The result was {omitted().chars.toLocaleString("en")} characters, over the {omitted().limit.toLocaleString("en")} a
                card carries; the whole result is in the engine's transcript.
              </Note>
            )}
          </Show>
          {footer()}
        </>
      }
    >
      {(k) => (
        <CardFrame
          tool={props}
          title={CARD_TITLE[k()]}
          subtitle={subtitleOf(k(), result())}
        >
          <Switch>
            <Match when={k() === "diagnosis" && readDiagnosisCard(result())}>
              {(data) => <DiagnosisBody data={data()} threadId={threadId()} />}
            </Match>
            <Match when={k() === "proposal" && readProposal(result())}>
              {(proposal) => <ProposalBody proposal={proposal()} args={props.input} threadId={threadId()} />}
            </Match>
            <Match when={k() === "eval" && readEvalReport(result())}>{(report) => <EvalBody report={report()} />}</Match>
            <Match when={k() === "compare" && readEvalComparison(result())}>
              {(comparison) => <CompareBody comparison={comparison()} />}
            </Match>
            <Match when={k() === "prompt" && readPromptAttempt(result())}>{(attempt) => <PromptBody attempt={attempt()} />}</Match>
            <Match when={k() === "sweep" && readChunkingSweep(result())}>{(sweep) => <SweepBody sweep={sweep()} />}</Match>
            <Match when={k() === "recall" && readRecall(result())}>{(report) => <RecallBody report={report()} />}</Match>
            <Match when={k() === "carve" && readCarveCard(result())}>{(carve) => <CarveBody carve={carve()} />}</Match>
            <Match when={k() === "synthesis" && readSynthesis(result())}>{(synthesis) => <SynthesisBody synthesis={synthesis()} />}</Match>
            <Match when={k() === "verification-sample" && readVerificationSample(result())}>
              {(sample) => <SampleBody sample={sample()} />}
            </Match>
            <Match when={k() === "verification" && readVerificationRecord(result())}>
              {(record) => <VerificationBody record={record()} />}
            </Match>
            <Match when={k() === "sandbox" && readSandboxResult(result())}>{(run) => <SandboxBody run={run()} />}</Match>
            <Match when={k() === "plan" && readPlanTick(result())}>{(tick) => <PlanBody tick={tick()} change={log.plan()} />}</Match>
          </Switch>
          <Show when={driver(envelope()?.drivenBy)}>{(line) => <Note>{line()}</Note>}</Show>
          <Show when={STAGED.has(k())}>
            <StageActions threadId={threadId()} />
          </Show>
          {footer()}
        </CardFrame>
      )}
    </Show>
  )
}
