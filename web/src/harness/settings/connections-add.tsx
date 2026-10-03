import { createSignal, For, Show } from "solid-js"
import { Button } from "@opencode/ui/button"
import { Select } from "@opencode/ui/select"
import { TextInput } from "@opencode/ui/text-input"
import { SettingsList } from "@/settings/list"
import { SettingsRow } from "@/settings/row"
import { harness } from "../engine"
import type { Connection, Preset } from "../providers/local"
import { ADAPTERS, addBody, addReady, applyPreset, EMPTY_ADD, type AddDraft, type Keychain } from "./connections-model"
import { SettingsSection } from "./connections-parts"
import type { Run } from "./connections"

/**
 * Add a connection by hand (PARITY 4.4, 4.7): every field, no assumptions -
 * for the case the one-click list cannot cover: a server on the network, a
 * gateway, a paid API. Presets from `GET /api/provider_presets` fill the
 * endpoint and adapter; the rest is typed.
 *
 * Create, activate, probe - in that order, as the outgoing app did. The key is
 * handed to `POST /api/providers` once, which gives it to the OS keychain, and
 * the field is cleared before the request resolves.
 */
export function AddByHand(props: { presets: Preset[]; keychain: Keychain | undefined; busy: boolean; run: Run }) {
  const [draft, setDraft] = createSignal<AddDraft>({ ...EMPTY_ADD })
  const set = <K extends keyof AddDraft>(field: K, value: AddDraft[K]) =>
    setDraft((was) => ({ ...was, [field]: value }))
  const noKeychain = () => props.keychain?.available === false

  const submit = async () => {
    if (!addReady(draft())) return
    const body = addBody(draft())
    set("api_key", "")
    const ok = await props.run("Saving the connection…", async () => {
      const row = await harness<Connection>("/api/providers", { body })
      await harness(`/api/providers/${row.id}/activate`, { method: "POST" })
      await harness(`/api/providers/${row.id}/probe`, { method: "POST" })
    })
    if (ok) setDraft({ ...EMPTY_ADD })
  }

  return (
    <SettingsSection
      title="With an API key"
      note="OpenAI, OpenRouter, or any OpenAI-compatible server. Pick one to fill the address, then type the model name and paste the key."
    >
      <Show when={props.presets.length > 0}>
        <div class="flex flex-wrap gap-2" role="group" aria-label="Presets">
          <For each={props.presets}>
            {(preset) => (
              <Button
                size="small"
                variant={draft().base_url === preset.base_url ? "neutral" : "outline"}
                icon={preset.needs_key ? "lock" : undefined}
                aria-pressed={draft().base_url === preset.base_url}
                title={preset.needs_key ? `${preset.base_url} - needs an API key` : preset.base_url}
                onClick={() => setDraft((was) => applyPreset(was, preset))}
              >
                {preset.name}
              </Button>
            )}
          </For>
        </div>
      </Show>

      <SettingsList>
        <SettingsRow title="What to call it" description="Any name you will recognise in the model picker.">
          <div class="w-full sm:w-[260px]">
            <TextInput
              type="text"
              aria-label="What to call it"
              value={draft().name}
              autocomplete="off"
              onInput={(event) => set("name", event.currentTarget.value)}
            />
          </div>
        </SettingsRow>
        <SettingsRow title="Endpoint" description="The server's base address, for example http://127.0.0.1:1234/v1.">
          <div class="w-full sm:w-[260px]">
            <TextInput
              type="text"
              class="font-mono"
              aria-label="Endpoint"
              placeholder="http://…"
              value={draft().base_url}
              spellcheck={false}
              autocomplete="off"
              onInput={(event) => set("base_url", event.currentTarget.value)}
            />
          </div>
        </SettingsRow>
        <SettingsRow
          title="How to speak to it"
          description="Ollama has its own protocol. Everything else - OpenAI, OpenRouter, LM Studio, llama.cpp, vLLM - is one OpenAI-compatible path driven by the address."
        >
          <Select
            options={ADAPTERS}
            current={ADAPTERS.find((option) => option.value === draft().adapter)}
            value={(option) => option.value}
            label={(option) => option.label}
            placement="bottom-end"
            gutter={6}
            onSelect={(option) => option && set("adapter", option.value)}
          />
        </SettingsRow>
        <SettingsRow title="Model" description="The model id this server answers to.">
          <div class="w-full sm:w-[260px]">
            <TextInput
              type="text"
              class="font-mono"
              aria-label="Model"
              value={draft().model}
              spellcheck={false}
              autocomplete="off"
              onInput={(event) => set("model", event.currentTarget.value)}
            />
          </div>
        </SettingsRow>
        <SettingsRow
          title="API key"
          description={
            noKeychain()
              ? (props.keychain?.detail ?? "There is no keychain on this computer.")
              : "Optional. Leave it empty for a server that does not want one. It goes to this computer's keychain, never to the database."
          }
        >
          <div class="w-full sm:w-[260px]">
            <TextInput
              type="password"
              class="font-mono"
              aria-label="API key"
              value={draft().api_key}
              autocomplete="off"
              disabled={noKeychain()}
              placeholder={noKeychain() ? "No keychain on this computer" : ""}
              onInput={(event) => set("api_key", event.currentTarget.value)}
            />
          </div>
        </SettingsRow>
        <SettingsRow
          title="Connect and check"
          description="Saves it, makes it the active connection, and asks the model what it can do."
        >
          <Button
            size="normal"
            variant="submit"
            disabled={!addReady(draft()) || props.busy}
            onClick={() => void submit()}
          >
            Connect and check
          </Button>
        </SettingsRow>
      </SettingsList>
    </SettingsSection>
  )
}
