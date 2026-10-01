import { createMemo, createSignal, Show } from "solid-js"
import { Button } from "@opencode/ui/button"
import { useData } from "@/runtime/server/current"
import { useServerSDK } from "@/runtime/server/client"
import { useLanguage } from "@/runtime/i18n/language"
import { usePlatform } from "@/runtime/platform/platform"
import { useProviders } from "@/providers/catalog/providers"
import { useWorkspaceLocation } from "@/workspaces/location"
import { useSessionLayout } from "@/session/session-layout"
import { createSessionContextFormatter } from "@/session/files/session-context-format"
import { fetchSessionExport, saveSessionExport, sessionExportFilename } from "@/session/commands/export"
import ContextPane from "../panes/context"
import { sessionUsage, type SessionUsage, type UsageMessage } from "../panes/context-usage"
import { ProvenanceTag, Row, Section } from "../ui"
import { PaneFrame } from "./frame"
import { CONTEXT_PANE, threadIdOf } from "./panes"

/**
 * ONE CONTEXT VIEW. Stands in for their `session/files/session-context-tab`
 * (SUBSTITUTES in web/vite.config.ts), so their context ring in the session
 * header - its icon, its click, its tab - opens this. It is the harness
 * Context view (panes/context.tsx: the measured prompt breakdown, compaction,
 * attachments) under the session readouts their tab showed, taken from their
 * session store the way their tab takes them (see panes/context-usage.ts for
 * which of their figures are shown and why the facade's zeros are not).
 *
 * Their tab's raw-message dump is left out: it is every message as JSON, and
 * the harness's Evidence pane is the record of what a conversation did.
 */
export function SessionContextTab() {
  const data = useData()
  const language = useLanguage()
  const location = useWorkspaceLocation()
  const providers = useProviders(() => location().directory)
  const { params } = useSessionLayout()

  const info = createMemo(() => (params.id ? data.session.get(params.id) : undefined))
  const messages = createMemo(() => (params.id ? data.session.message.list(params.id) : []))
  const usage = createMemo(() =>
    sessionUsage(messages() as unknown as UsageMessage[], info(), (providerID, modelID) => {
      const provider = providers.all().get(providerID)
      if (!provider) return
      const model = provider.models[modelID]
      return { providerName: provider.name, modelName: model?.name, limit: model?.limit.context }
    }),
  )
  const threadId = createMemo(() => threadIdOf(info()))

  return (
    <PaneFrame pane={CONTEXT_PANE} threadId={threadId()}>
      <SessionReadout usage={usage()} fallbackTitle={params.id} sessionID={params.id} locale={language.intl()} />
      <ContextPane threadId={threadId()} />
    </PaneFrame>
  )
}

function SessionReadout(props: { usage: SessionUsage; fallbackTitle?: string; sessionID?: string; locale: string }) {
  const format = createMemo(() => createSessionContextFormatter(props.locale))
  const usd = createMemo(() => new Intl.NumberFormat(props.locale, { style: "currency", currency: "USD" }))
  const counts = () => props.usage.counts
  const model = () => [props.usage.provider, props.usage.model].filter(Boolean).join(" · ")

  return (
    <Section title="This chat" action={<ExportButton sessionID={props.sessionID} />}>
      <Row label="Session">{props.usage.title ?? props.fallbackTitle ?? "—"}</Row>
      <Row label="Model">{model() || "No reply yet"}</Row>
      <Show when={props.usage.limit}>
        {(limit) => (
          <Row label="Context window" tag={<ProvenanceTag value="declared" source="the model list" />}>
            {format().number(limit())} tokens
          </Row>
        )}
      </Show>
      <Row label="Messages">
        {format().number(counts().all)} · {format().number(counts().user)} from you · {format().number(counts().assistant)}{" "}
        {counts().assistant === 1 ? "reply" : "replies"}
      </Row>
      <Show
        when={props.usage.tokens}
        fallback={
          <Row label="Reply usage" title="This engine does not report a provider's per-reply token usage or cost.">
            <span class="text-v2-text-text-muted">Not reported; the prompt each turn sent is counted below</span>
          </Row>
        }
      >
        {(tokens) => (
          <>
            <Row label="Last reply" tag={<ProvenanceTag value="measured" source="the provider's usage on the last reply" />}>
              {format().number(tokens().total)} tokens
              <Show when={tokens().usage !== null}> · {format().percent(tokens().usage)} of the window</Show>
            </Row>
            <Row label="Input · output">
              {format().number(tokens().input)} · {format().number(tokens().output)}
            </Row>
            <Show when={tokens().reasoning > 0}>
              <Row label="Reasoning">{format().number(tokens().reasoning)}</Row>
            </Show>
            <Show when={tokens().cacheRead > 0 || tokens().cacheWrite > 0}>
              <Row label="Cache read · write">
                {format().number(tokens().cacheRead)} · {format().number(tokens().cacheWrite)}
              </Row>
            </Show>
          </>
        )}
      </Show>
      <Show when={props.usage.cost}>
        {(cost) => (
          <Row label="Cost" tag={<ProvenanceTag value="measured" source="the provider's reported cost" />}>
            {usd().format(cost())}
          </Row>
        )}
      </Show>
      <Row label="Started">{format().time(props.usage.created)}</Row>
      <Row label="Last reply at">{format().time(props.usage.lastReply)}</Row>
      <Show when={props.usage.systemPrompt}>
        {(prompt) => (
          <div class="mx-4 mt-1 max-h-48 overflow-auto rounded-sm bg-v2-background-bg-layer-01 px-3 py-2 text-12-regular whitespace-pre-wrap text-v2-text-text-base">
            {prompt()}
          </div>
        )}
      </Show>
    </Section>
  )
}

/** Their Export, unchanged in what it does: the session and its messages, saved as JSON. */
function ExportButton(props: { sessionID?: string }) {
  const platform = usePlatform()
  const server = useServerSDK()
  const [state, setState] = createSignal<"idle" | "busy" | "failed">("idle")
  const save = async () => {
    const sessionID = props.sessionID
    if (!sessionID || state() === "busy") return
    setState("busy")
    try {
      const exported = await fetchSessionExport({ sessionID, api: server.api })
      await saveSessionExport(sessionExportFilename(exported.info), exported, platform)
      setState("idle")
    } catch {
      setState("failed")
    }
  }
  return (
    <Button
      size="small"
      variant="ghost"
      icon="download"
      disabled={!props.sessionID || state() === "busy"}
      onClick={() => void save()}
    >
      {state() === "busy" ? "Exporting" : state() === "failed" ? "Export failed; retry" : "Export"}
    </Button>
  )
}
