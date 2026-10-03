import { createResource, createSignal, For, onCleanup, Show } from "solid-js"
import { Button } from "@opencode/ui/button"
import { useDialog } from "@opencode/ui/context/dialog"
import type { ComposerModel } from "@/composer/model"
import { useServerSDK } from "@/runtime/server/client"
import { useWorkspaceLocation } from "@/workspaces/location"
import { harness } from "../engine"
import { connectionLabel, connectLocal, listLocalModels, localModelLabel, type Connection } from "../providers/local"
import { useLocal } from "@/providers/models/selection"
import { useCommand } from "@/shell/commands/command"
import { unsupportedCommandOverrides } from "../session/unsupported"
import { useHarnessRead } from "../ui"
import { HarnessSurfaceMarks } from "../session/marks"
import { DEFAULT_LOCAL_MODEL, INSTALL_LINE, whatIsMissing, type LocalRead } from "./setup"

/**
 * What a new chat shows under the composer (patch P14).
 *
 * Their new-session screen is a wordmark and a composer, which is right for
 * a tool whose user already knows what to type. The harness's first screen
 * also answered three questions the person has on arrival, and they are kept:
 *
 *   - What can this machine do? One line of hardware, measured.
 *   - Where do I start? Four starter prompts; a click fills the composer.
 *   - Which model? If none is connected, the models already on this machine,
 *     each one click away - the only step the harness ever required before
 *     a first message, now done without leaving the page.
 */

const STARTERS = [
  "I have a folder of support tickets and I want the model to answer like our team does.",
  "I want a small model that runs on this machine and does one thing well.",
  "I have a spreadsheet and I want to predict a column in it.",
  "The model we're using works. It's too slow and it costs too much.",
]

type Specs = { gpu_name?: string | null; vram_gb?: number | null; ram_gb?: number | null }

function machineLine(specs: Specs | undefined) {
  if (!specs) return
  const parts = [
    specs.gpu_name ?? "No graphics card detected",
    specs.vram_gb ? `${Math.round(specs.vram_gb)} GB video memory` : undefined,
    specs.ram_gb ? `${Math.round(specs.ram_gb)} GB memory` : undefined,
  ].filter(Boolean)
  return parts.join(" · ")
}

export function HarnessStart(props: { composer: ComposerModel }) {
  const dialog = useDialog()
  const location = useWorkspaceLocation()
  const selection = useLocal()
  // A new chat's composer registers their shell mode and their location
  // cycle; the same overrides the session mount makes (session/unsupported.ts),
  // made here too because a new chat has no session mount yet.
  useCommand().register("harness.start", () => [...unsupportedCommandOverrides()])
  const [specs] = createResource(() => harness<Specs>("/local_specs").catch(() => undefined))
  // The connections, re-read whenever they may have changed: after the API-key
  // dialog closes, and on the facade's `provider.updated` / `model.updated`
  // (app/facade/stream.py CATALOG_EVENTS), so a model connected in Settings or
  // in that dialog clears "Pick a model" without a reload.
  //
  // A failed read is NOT "no model": it used to fall back to an empty list,
  // which told a person with a model connected to pick one.
  const connections = useHarnessRead<Connection[]>(() => "/api/providers")
  const refetch = () => connections.refetch()
  const settledList = () => {
    const state = connections.data.state
    return connections.data.error || (state !== "ready" && state !== "refreshing") ? undefined : connections.data.latest
  }
  const noModel = () => {
    const list = settledList()
    return list !== undefined && !list.some((row) => row.is_active)
  }
  const activeConnection = () => settledList()?.find((row) => row.is_active)
  const sdk = useServerSDK()
  onCleanup(sdk.event.on("provider.updated", () => void refetch()))
  onCleanup(sdk.event.on("model.updated", () => void refetch()))
  // A failed read is Ollama not answering, which is not the same as Ollama
  // answering with no models: each has its own sentence below, and the error
  // is shown in Ollama's own words rather than dropped.
  const [local, { refetch: lookAgain }] = createResource(noModel, () =>
    listLocalModels().then(
      (models): LocalRead => ({ models }),
      (error): LocalRead => ({ models: [], error: error instanceof Error ? error.message : String(error) }),
    ),
  )
  const missing = () => whatIsMissing(local.latest)
  // While nothing can be picked, look again every few seconds, so a model
  // pulled in another window (or by the install line) appears by itself.
  const poll = setInterval(() => {
    if (noModel() && missing() && !local.loading) void lookAgain()
  }, 5_000)
  onCleanup(() => clearInterval(poll))
  // A refused clipboard write (a webview can deny it) says how to copy by
  // hand - one click on the line selects all of it - instead of doing nothing.
  const [copied, setCopied] = createSignal<"copied" | "selected">()
  let line: HTMLElement | undefined
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(INSTALL_LINE)
      setCopied("copied")
    } catch {
      const range = document.createRange()
      if (line) range.selectNodeContents(line)
      window.getSelection()?.removeAllRanges()
      window.getSelection()?.addRange(range)
      setCopied("selected")
    }
  }
  const [busy, setBusy] = createSignal<string>()
  const [failure, setFailure] = createSignal<string>()

  const fill = (text: string) => {
    props.composer.onInput(text, [{ type: "text", content: text, start: 0, end: text.length }], text.length)
    props.composer.restoreFocus(text.length)
  }

  const connect = async (model: string) => {
    setBusy(model)
    setFailure(undefined)
    try {
      await connectLocal(model)
      await refetch()
    } catch (error) {
      setFailure(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(undefined)
    }
  }

  const openKeyDialog = () =>
    void import("@/providers/connect/dialog").then(({ DialogConnectProvider }) => {
      void dialog.show(
        () => <DialogConnectProvider directory={location().directory} />,
        () => void refetch(),
      )
    })

  return (
    // CENTRED, "This computer" first (the owner, 2026-09-22: "This computer at
    // the top, all the things under should be centered").
    <div data-slot="harness-start" class="mt-4 flex w-full flex-col items-center gap-4 text-center">
      {/* The composer's mode hint on a new chat (session/marks.tsx). */}
      <HarnessSurfaceMarks
        find={(marker) => marker.closest<HTMLElement>('[data-component="new-session"]')}
        mode={() => selection.agent.current()?.name}
      />
      <Show when={machineLine(specs())}>
        {(line) => (
          <div data-slot="harness-start-machine" class="text-12-regular text-v2-text-text-faint">
            This computer: {line()}
          </div>
        )}
      </Show>
      {/* Which model this chat will use, by its nickname (Settings >
          Connections) or its short name - never the whole link. */}
      <Show when={activeConnection()}>
        {(row) => (
          <div data-slot="harness-start-model" class="text-12-regular text-v2-text-text-faint" title={row().model}>
            Model: {connectionLabel(row())}
          </div>
        )}
      </Show>
      <Show when={connections.data.error}>
        {(error) => (
          <div data-slot="start-connections-error" class="text-12-regular text-v2-state-fg-danger">
            Could not read the model connections: {error() instanceof Error ? error().message : String(error())}
          </div>
        )}
      </Show>
      <Show when={noModel()}>
        <div class="flex w-full flex-col items-center gap-2 rounded-[10px] bg-v2-background-bg-layer-01 p-3">
          <div class="text-[13px] [font-weight:530] text-v2-text-text-base">Pick a model to start</div>
          <Show
            when={(local.latest?.models ?? []).length > 0}
            fallback={
              <Show
                when={missing()}
                fallback={<div class="text-12-regular text-v2-text-text-muted">Looking for models on this computer…</div>}
              >
                {(what) => (
                  <div data-slot="start-no-local" data-missing={what()} class="flex w-full max-w-[560px] flex-col items-center gap-2">
                    <div class="text-12-regular text-v2-text-text-muted">
                      {what() === "ollama"
                        ? "Ollama is not answering on this computer, so there is no local model to pick. If it is installed, open it from the Start menu. If not, run this line in PowerShell: it installs Ollama and the model " +
                          DEFAULT_LOCAL_MODEL +
                          " (about 5 GB) and connects it."
                        : "Ollama is running and has no models yet. Run this line in PowerShell: it pulls " +
                          DEFAULT_LOCAL_MODEL +
                          " (about 3.4 GB) and connects it. A model you pull yourself appears here too."}
                    </div>
                    <div class="flex w-full items-center gap-2 rounded-[8px] bg-v2-background-bg-layer-02 px-2 py-1 text-left">
                      <code ref={line} class="min-w-0 flex-1 select-all break-all font-mono text-[12px] text-v2-text-text-base">
                        {INSTALL_LINE}
                      </code>
                      <Button size="small" variant="outline" onClick={() => void copy()}>
                        {copied() === "copied" ? "Copied" : copied() === "selected" ? "Click the line, then Ctrl+C" : "Copy"}
                      </Button>
                    </div>
                    <Show when={local.latest?.error}>
                      {(error) => <div class="font-mono text-[11px] text-v2-text-text-faint">Ollama: {error()}</div>}
                    </Show>
                    <Button size="small" variant="ghost" onClick={() => void lookAgain()}>
                      Look again
                    </Button>
                  </div>
                )}
              </Show>
            }
          >
            <div class="flex flex-wrap justify-center gap-2">
              <For each={local.latest?.models}>
                {(model) => (
                  <Button
                    size="small"
                    variant="outline"
                    disabled={busy() !== undefined}
                    title={model.name}
                    onClick={() => void connect(model.name)}
                  >
                    {busy() === model.name
                      ? `Connecting ${localModelLabel(model.name, settledList())}…`
                      : localModelLabel(model.name, settledList())}
                  </Button>
                )}
              </For>
            </div>
          </Show>
          <Show when={failure()}>
            <div class="text-12-regular text-v2-state-fg-danger">{failure()}</div>
          </Show>
          <div>
            <Button size="small" variant="ghost" onClick={openKeyDialog}>
              Use an API key instead
            </Button>
          </div>
        </div>
      </Show>

      <div data-slot="harness-start-starters" class="flex flex-wrap justify-center gap-2">
        <For each={STARTERS}>
          {(text) => (
            <button
              type="button"
              class="rounded-[8px] bg-v2-background-bg-layer-01 px-3 py-2 text-center text-12-regular text-v2-text-text-muted hover:bg-v2-overlay-simple-overlay-hover hover:text-v2-text-text-base"
              onClick={() => fill(text)}
            >
              {text}
            </button>
          )}
        </For>
      </div>
    </div>
  )
}
