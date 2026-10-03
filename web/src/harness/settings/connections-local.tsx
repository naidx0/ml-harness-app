import { createSignal, For, Match, Show, Switch } from "solid-js"
import { Badge } from "@opencode/ui/badge"
import { Button } from "@opencode/ui/button"
import { SettingsList } from "@/settings/list"
import { useHarnessRead } from "../ui"
import { connectLocal, listLocalModels, localModelLabel, type Connection, type LocalModel } from "../providers/local"
import { inUseModel, modelList, reachable, type Candidate } from "./connections-model"
import { EmptyLine, message, SettingsSection } from "./connections-parts"
import type { Run } from "./connections"
import { InstallLine } from "../start/install-line"
import { DEFAULT_LOCAL_MODEL } from "../start/setup"

/**
 * What a local model's capabilities say about tool calling. No list at all
 * (null, or absent from an older engine) is "not checked" - never "no tool
 * calling", which is a claim about the model nobody measured.
 */
export function toolCallingOf(capabilities: readonly string[] | null | undefined): string {
  if (!Array.isArray(capabilities)) return "tool calling not checked"
  return capabilities.includes("tools") ? "can call tools" : "no tool calling"
}

/**
 * The two "on this computer" lists from the outgoing connect dialog.
 *
 * Models on this computer (PARITY 4.3): whatever Ollama already has, one click
 * each. `connectLocal` creates, activates and probes, and reuses an existing
 * row for the same endpoint and model rather than piling up duplicates.
 *
 * Already running here (PARITY 4.2): what `GET /api/providers/discover` found
 * listening on the usual ports. Display only - connecting stays an explicit
 * act, through the list above or the form below.
 */

export function LocalModels(props: { connections: Connection[] | undefined; busy: boolean; run: Run }) {
  // OUR OWN IN-FLIGHT COUNT, as `useHarnessRead` keeps one (ui.tsx): a raw
  // resource's `loading` stays true inside their transitions, so "Looking…"
  // never came back. `useHarnessRead` itself reads a GET path, and this list
  // is a tool call (`POST /api/tools/list_local_models`, providers/local.ts).
  const [found, setFound] = createSignal<LocalModel[]>()
  const [failure, setFailure] = createSignal<unknown>()
  const [reads, setReads] = createSignal(0)
  const refetch = async () => {
    setReads((n) => n + 1)
    try {
      setFound(await listLocalModels())
      setFailure(undefined)
    } catch (error) {
      setFailure(error ?? new Error("Ollama did not answer"))
    } finally {
      setReads((n) => n - 1)
    }
  }
  void refetch()
  const models = {
    get loading() {
      return reads() > 0
    },
    get error() {
      return failure()
    },
  }
  const [pending, setPending] = createSignal<string>()

  const list = () => (failure() ? undefined : found())

  const connect = async (model: string) => {
    setPending(model)
    await props.run(`Connecting ${localModelLabel(model, props.connections)} and asking what it can do…`, () =>
      connectLocal(model),
    )
    setPending(undefined)
  }

  return (
    <SettingsSection
      title="On this computer"
      note="A model pulled into Ollama needs no address and no key. One click connects it and makes it the one in use."
      action={
        <Button
          size="small"
          variant="ghost"
          icon="refresh"
          disabled={models.loading}
          onClick={() => void refetch()}
        >
          {models.loading ? "Looking…" : "Look again"}
        </Button>
      }
    >
      <SettingsList variant="catalog">
        <Switch>
          <Match when={models.error}>
            {/* Not running Ollama is an ordinary choice, not a fault. */}
            <div data-slot="local-missing" data-missing="ollama" class="flex flex-col gap-2 px-3 py-3 text-[13px] text-v2-text-text-muted">
              <span>
                Ollama is not answering on this computer. If it is installed, open it from the Start menu. If not, run
                this line in PowerShell: it installs Ollama and {DEFAULT_LOCAL_MODEL} (about 5 GB) and connects it. Or
                use an API key below.
              </span>
              <InstallLine />
              <span class="font-mono text-[11px] text-v2-text-text-faint">
                Ollama: {models.error instanceof Error ? models.error.message : String(models.error)}
              </span>
            </div>
          </Match>
          <Match when={models.loading && !list()}>
            <EmptyLine>Reading the models on this computer…</EmptyLine>
          </Match>
          <Match when={(list() ?? []).length === 0}>
            <div data-slot="local-missing" data-missing="model" class="flex flex-col gap-2 px-3 py-3 text-[13px] text-v2-text-text-muted">
              <span>
                Ollama is running and has no models yet. Run this line in PowerShell: it pulls {DEFAULT_LOCAL_MODEL}
                (about 3.4 GB) and connects it. A model you pull yourself appears here after Look again.
              </span>
              <InstallLine />
            </div>
          </Match>
          <Match when={true}>
            <For each={list()}>
              {(entry) => {
                const using = () => inUseModel(props.connections, entry.name)
                const meta = () =>
                  [
                    entry.params_b !== null ? `${entry.params_b}B parameters` : undefined,
                    entry.on_disk_gb !== null ? `${entry.on_disk_gb} GB on disk` : undefined,
                    toolCallingOf(entry.capabilities),
                  ]
                    .filter(Boolean)
                    .join(" · ")
                return (
                  <div class="settings-provider-row">
                    <div class="settings-provider-lead">
                      <div class="settings-provider-copy">
                        <div class="settings-provider-main">
                          <span class="settings-provider-name truncate font-mono" title={entry.name}>
                            {localModelLabel(entry.name, props.connections)}
                          </span>
                        </div>
                        <p class="settings-provider-description">{meta()}</p>
                      </div>
                    </div>
                    <Show
                      when={!using()}
                      fallback={<Badge variant="accent">In use</Badge>}
                    >
                      <Button
                        size="normal"
                        variant="neutral"
                        icon="plus"
                        disabled={props.busy}
                        onClick={() => void connect(entry.name)}
                      >
                        {pending() === entry.name ? "Connecting…" : "Connect"}
                      </Button>
                    </Show>
                  </div>
                )
              }}
            </For>
          </Match>
        </Switch>
      </SettingsList>
    </SettingsSection>
  )
}

export function AlreadyRunning() {
  const discovered = useHarnessRead<{ candidates: Candidate[] }>(() => "/api/providers/discover")
  const found = () => (discovered.data.error ? [] : reachable(discovered.data.latest?.candidates))

  return (
    <SettingsSection
      title="Already running here"
      note="What answered on the usual local ports. Shown so you know it is there; connect it above or by hand below."
      action={
        <Button
          size="small"
          variant="ghost"
          icon="refresh"
          disabled={discovered.data.loading}
          onClick={() => void discovered.refetch()}
        >
          {discovered.data.loading ? "Looking…" : "Look again"}
        </Button>
      }
    >
      {/* A failed read is not "nothing is listening": that would be a claim
          about the ports nobody checked. The error replaces the empty line. */}
      <Show when={discovered.data.error}>
        {(failure) => (
          <p role="alert" data-slot="discover-error" class="text-[13px] text-v2-state-fg-danger">
            Could not read what is listening on this computer: {message(failure())}
          </p>
        )}
      </Show>
      <SettingsList variant="catalog">
        <Show
          when={found().length > 0}
          fallback={
            <Show when={!discovered.data.error}>
              <EmptyLine>
                {discovered.data.loading ? "Looking on this computer…" : "Nothing is listening on the usual local ports."}
              </EmptyLine>
            </Show>
          }
        >
          <For each={found()}>
            {(candidate) => (
              <div class="settings-provider-row">
                <div class="settings-provider-lead">
                  <div class="settings-provider-copy">
                    <div class="settings-provider-main">
                      <span class="settings-provider-name">{candidate.name}</span>
                      <Badge>Listening</Badge>
                    </div>
                    <p class="settings-provider-description break-all">
                      <span class="font-mono">{candidate.base_url}</span> · {modelList(candidate.models)}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </For>
        </Show>
      </SettingsList>
    </SettingsSection>
  )
}
