import { createResource, For, onCleanup, Show } from "solid-js"
import { Button } from "@opencode/ui/button"
import type { ComposerModel } from "@/composer/model"
import { useServerSDK } from "@/runtime/server/client"
import { harness } from "../engine"
import { connectionLabel, type Connection } from "../providers/local"
import { useLocal } from "@/providers/models/selection"
import { useCommand } from "@/shell/commands/command"
import { unsupportedCommandOverrides } from "../session/unsupported"
import { useHarnessRead } from "../ui"
import { HarnessSurfaceMarks } from "../session/marks"
import { useOpenModels } from "../settings/models-open"

/**
 * What a new chat shows under the composer (patch P14).
 *
 * Their new-session screen is a wordmark and a composer, which is right for
 * a tool whose user already knows what to type. The harness's first screen
 * also answered three questions the person has on arrival, and they are kept:
 *
 *   - What can this machine do? One line of hardware, measured.
 *   - Where do I start? Four starter prompts; a click fills the composer.
 *   - Which model? If none is connected, two buttons and nothing else: a
 *     model on this computer, or one with an API key. Both open Settings >
 *     Models, the one page where models are added (Jaden, 2026-10-03: "attach
 *     a local model takes you to route, select a model takes you to route
 *     settings ... simple").
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
  const selection = useLocal()
  const openModels = useOpenModels()
  // A new chat's composer registers their shell mode and their location
  // cycle; the same overrides the session mount makes (session/unsupported.ts),
  // made here too because a new chat has no session mount yet.
  useCommand().register("harness.start", () => [...unsupportedCommandOverrides()])
  const [specs] = createResource(() => harness<Specs>("/local_specs").catch(() => undefined))
  // The connections, re-read whenever they may have changed: on the facade's
  // `provider.updated` / `model.updated` (app/facade/stream.py CATALOG_EVENTS),
  // so a model connected in Settings clears the card without a reload.
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
  const fill = (text: string) => {
    props.composer.onInput(text, [{ type: "text", content: text, start: 0, end: text.length }], text.length)
    props.composer.restoreFocus(text.length)
  }

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
        <div
          data-slot="start-no-model"
          class="flex w-full max-w-[520px] flex-col items-center gap-3 rounded-[12px] bg-v2-background-bg-layer-01 px-4 py-4"
        >
          <div class="flex flex-col items-center gap-1">
            <div class="text-[14px] [font-weight:560] text-v2-text-text-base">Connect a model to start</div>
            <div class="text-12-regular text-v2-text-text-muted">
              ML Harness ships no AI. Use one on this computer, or one you reach with an API key.
            </div>
          </div>
          <Show when={openModels}>
            {(open) => (
              <div class="flex flex-wrap justify-center gap-2">
                <Button size="normal" variant="contrast" icon="monitor" onClick={() => open()("local")}>
                  Use a model on this computer
                </Button>
                <Button size="normal" variant="neutral" icon="key" onClick={() => open()("api")}>
                  Use an API key
                </Button>
              </div>
            )}
          </Show>
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
