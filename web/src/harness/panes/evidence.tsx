import { createMemo, For, Match, Show, Switch } from "solid-js"
import { Button } from "@opencode/ui/button"
import { PaneEmpty } from "../panel/frame"
import type { PaneProps } from "../panel/panes"
import { ErrorLine, kindIn, Section, useHarnessRead, useHarnessRefresh } from "../ui"
import { latestReadOf, toolResults, useThreadEvents } from "./eval-events"
import {
  actorName,
  factsInClause,
  gateLedger,
  readDiagnosis,
  readEvidence,
  showValue,
  weakestOrigin,
  type EvidenceRow,
} from "./evidence-ledger"
import { GateBadge, OriginTag } from "./evidence-origin"

/**
 * Why the harness believes what it believes: the five-gate ledger of the
 * newest diagnosis in this conversation, and under it the evidence ledger -
 * one append-only row per claim or measurement, with who said it and how.
 *
 * Ported from the outgoing `EvidencePane` (frontend/src/components/
 * PaneStack.tsx). The diagnosis comes from the newest `run_diagnosis` result
 * in the thread's event log, the same fold the outgoing shell did over its
 * transcript; the rows come from `GET /api/evidence?thread_id=`. Read-only:
 * a row is written by a tool or by a person through a tool, never here.
 *
 * Not polled: a poll would invent a freshness the engine does not promise.
 * A fact is recorded by a tool, so the ledger re-reads when this chat's
 * session says a tool answered (session/refresh.ts), and on "Read again".
 */
export default function EvidencePane(props: PaneProps) {
  return (
    <Show
      when={props.threadId}
      // KEYED: a new thread mounts a new ledger, so the previous thread's
      // gates and rows do not stay on screen while the new reads are out.
      keyed
      fallback={<PaneEmpty title="No conversation open">Open a chat to see what its gates rest on.</PaneEmpty>}
    >
      {(threadId) => <Ledger threadId={threadId} />}
    </Show>
  )
}

function Ledger(props: { threadId: number }) {
  const thread = useThreadEvents(() => props.threadId)
  const evidence = useHarnessRead<unknown>(() => `/api/evidence?thread_id=${props.threadId}`)
  const diagnosis = createMemo(() => latestReadOf(toolResults(thread.events()), readDiagnosis))
  const ledger = createMemo(() => gateLedger(diagnosis()?.gateLedger))
  const rows = createMemo(() => (evidence.data.error ? null : readEvidence(evidence.data())))
  const loading = () => thread.read.data.loading || evidence.data.loading
  const refresh = () => {
    void thread.read.refetch()
    void evidence.refetch()
  }
  // A fact is recorded, and a diagnosis delivered, by a tool: the ledger
  // re-reads on this chat's tool results (session/refresh.ts). Still no poll.
  useHarnessRefresh(props.threadId, refresh, kindIn("tool.result"))

  return (
    <div class="flex flex-col pb-6">
      <Section
        // The counter is "n of 5" and never a percentage: three of five gates
        // is not 60% of a guarantee.
        title={`Gate ledger · ${ledger().passed} of ${ledger().of} passed`}
        action={
          <Button size="small" variant="ghost" onClick={refresh} disabled={loading()}>
            {loading() ? "Reading" : "Read again"}
          </Button>
        }
      >
        <Show when={thread.read.data.error}>
          <ErrorLine error={thread.read.data.error} />
        </Show>
        <For each={ledger().gates}>
          {(gate, index) => {
            // The second fact on every row: not "did it pass" but "on what" -
            // the weakest origin among the facts the gate's own clause names.
            const origin = () => {
              const found = diagnosis()
              const entry = found?.gateLedger[gate.id]
              return entry ? weakestOrigin(factsInClause(entry.clause, found!.factOrigins), found!.factOrigins) : null
            }
            return (
              <div class="flex min-h-8 items-center gap-3 px-4 py-1 text-12-regular" title={gate.asks}>
                <span class="w-4 shrink-0 tabular-nums text-v2-text-text-faint">{index() + 1}</span>
                <span class="min-w-0 flex-1 truncate text-v2-text-text-base">{gate.name}</span>
                <OriginTag origin={origin()} />
                <GateBadge status={gate.status} />
              </div>
            )
          }}
        </For>
        <Show when={!diagnosis() && !thread.read.data.error}>
          <div class="px-4 pt-1 text-12-regular text-v2-text-text-muted">
            {thread.read.data.answered
              ? "Nothing decided yet. This fills in when a diagnosis runs in this conversation."
              : "Reading…"}
          </div>
        </Show>
        <Show when={diagnosis()?.say}>
          <div class="px-4 pt-1 text-12-regular text-v2-text-text-muted">"{diagnosis()!.say}"</div>
        </Show>
      </Section>

      <Section title={`Why the harness believes this${rows() ? ` · ${rows()!.rows.length} rows` : ""}`}>
        <Switch>
          <Match when={evidence.data.error}>
            <ErrorLine error={evidence.data.error} />
          </Match>
          <Match when={!evidence.data.answered}>
            <div class="px-4 py-1 text-12-regular text-v2-text-text-muted">Reading…</div>
          </Match>
          <Match when={rows() && rows()!.rows.length === 0}>
            <div class="px-4 py-1 text-12-regular text-v2-text-text-muted">
              Nothing has been claimed or measured in this conversation yet. Rows appear the moment a tool measures
              something or somebody says something.
            </div>
          </Match>
          <Match when={rows()}>
            <For each={rows()!.rows}>{(row) => <EvidenceLine row={row} />}</For>
          </Match>
        </Switch>
        <Show when={rows() && (rows()!.quarantined > 0 || rows()!.unscoped > 0)}>
          <div class="px-4 pt-2 text-12-regular text-v2-text-text-faint">
            {[
              rows()!.quarantined > 0 ? `${rows()!.quarantined} quarantined` : "",
              rows()!.unscoped > 0 ? `${rows()!.unscoped} visible to no conversation` : "",
            ]
              .filter(Boolean)
              .join(" · ")}
            {" "}rows are kept in the ledger and can open no gate. Nothing was deleted.
          </div>
        </Show>
      </Section>

      {/* Said once, behind a disclosure: true, worth saying, and not worth
          four standing lines beside the rows it is about. */}
      <details class="px-4 pt-1">
        <summary class="cursor-pointer list-none text-12-medium text-v2-text-text-muted">Why two rows can disagree</summary>
        <p class="pt-1 text-12-regular text-v2-text-text-muted">
          Rows are append-only and nothing is updated in place, so a measurement taken after a claim sits beside it
          rather than replacing it. The engine resolves them - measured beats stated beats asserted, recency breaking
          ties - and this pane does not, because a second resolution here could disagree with the one that decided the
          gates.
        </p>
      </details>
    </div>
  )
}

function EvidenceLine(props: { row: EvidenceRow }) {
  const who = () => actorName(props.row.actor) ?? props.row.actor
  return (
    <div class="flex flex-col gap-0.5 px-4 py-1.5">
      <div class="flex min-w-0 items-center gap-2 text-12-regular">
        <span class="min-w-0 truncate text-12-mono text-v2-text-text-base">{props.row.fact}</span>
        <span class="min-w-0 flex-1 truncate text-12-mono text-v2-text-text-muted tabular-nums" title={String(props.row.value)}>
          {showValue(props.row.value)}
        </span>
        <OriginTag origin={props.row.origin} by={who()} />
      </div>
      {/* The engine's own sentence of how. `Instrument.measured` refuses a
          stamp without one, so a MEASURED row always has something to say. */}
      <Show when={props.row.how}>
        <div class="text-12-regular text-v2-text-text-muted">{props.row.how}</div>
      </Show>
      <div class="text-12-regular text-v2-text-text-faint">
        {who()}
        <Show when={props.row.tool}>
          {" · "}
          <span class="text-12-mono">{props.row.tool}</span>
        </Show>
        <Show when={props.row.createdAt}>{` · ${props.row.createdAt}`}</Show>
      </div>
    </div>
  )
}
