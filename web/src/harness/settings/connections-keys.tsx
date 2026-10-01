import { For, Show } from "solid-js"
import { Button } from "@opencode/ui/button"
import { SettingsList } from "@/settings/list"
import { SettingsRow } from "@/settings/row"
import { harness } from "../engine"
import { connectionLabel, shortModelName } from "../providers/local"
import { keyHolders, type ConnectionRow, type Keychain } from "./connections-model"
import { EmptyLine, ErrorText, SettingsSection } from "./connections-parts"
import type { Run } from "./connections"

/**
 * Where keys live (PARITY 4.5, 8.3) - the one place in the product that says
 * where a secret is kept.
 *
 * Provider keys go to the OS keychain; the database holds a reference and
 * never the key. A person cannot run the test that proves it, so this names
 * the actual store on this computer, in the engine's own sentence, and what to
 * do on a machine that has none. The engine answers `has_key`, a yes or no,
 * and never the key.
 */
export function Keys(props: {
  keychain: Keychain | undefined
  keychainError: unknown
  connections: ConnectionRow[] | undefined
  busy: boolean
  run: Run
}) {
  const holders = () => keyHolders(props.connections)

  return (
    <SettingsSection
      title="Keys"
      note="An API key you give the harness goes to this computer's own secret store. It is never written to the database, never logged, and never sent back to this page."
    >
      <Show when={props.keychainError}>{(failure) => <ErrorText error={failure()} />}</Show>
      <SettingsList>
        <Show when={props.keychain} fallback={<EmptyLine>Asking the engine where keys go…</EmptyLine>}>
          {(keychain) => (
            <>
              <SettingsRow title="Secret store" description={keychain().detail}>
                <span
                  class="text-[13px]"
                  classList={{
                    "text-v2-text-text-base": keychain().available,
                    "text-v2-state-fg-warning": !keychain().available,
                  }}
                >
                  {keychain().backend ?? "None on this computer"}
                </span>
              </SettingsRow>
              <SettingsRow title="Filed under" description="The service name every key from this product is stored under.">
                <span class="font-mono text-[13px] text-v2-text-text-base">{keychain().service}</span>
              </SettingsRow>
              <SettingsRow
                title="Environment override"
                description="A variable with this name, ending in the connection's id, is used instead of the stored key."
              >
                <span class="font-mono text-[13px] text-v2-text-text-base">
                  {keychain().env_prefix}
                  <span class="text-v2-text-text-faint">&lt;id&gt;</span>
                </span>
              </SettingsRow>
              <Show when={!keychain().available}>
                <div class="py-4 text-[13px] text-v2-state-fg-warning">
                  With no store, a key cannot be saved here, and the key fields are switched off. The engine refuses to
                  fall back to a file or the database - a key it cannot protect is a key it declines to hold.
                </div>
              </Show>
            </>
          )}
        </Show>
      </SettingsList>

      <SettingsList variant="catalog">
        <Show
          when={holders().length > 0}
          fallback={
            <EmptyLine>
              No connection holds a key. Every one reaches its model without one, which is what a local server
              normally does.
            </EmptyLine>
          }
        >
          <For each={holders()}>
            {(row) => (
              <div class="settings-provider-row">
                <div class="settings-provider-lead">
                  <div class="settings-provider-copy">
                    <div class="settings-provider-main">
                      <span class="settings-provider-name">{connectionLabel(row)}</span>
                    </div>
                    <p class="settings-provider-description">
                      <span class="font-mono" title={row.model}>
                        {shortModelName(row.model) || row.model}
                      </span>{" "}
                      · key stored (connection {row.id})
                    </p>
                  </div>
                </div>
                <Button
                  size="normal"
                  variant="ghost-muted"
                  icon="trash"
                  disabled={props.busy}
                  onClick={() =>
                    void props.run(`Removing the key for ${connectionLabel(row)}…`, () =>
                      harness(`/api/providers/${row.id}`, { method: "PATCH", body: { api_key: "" } }),
                    )
                  }
                >
                  Remove the key
                </Button>
              </div>
            )}
          </For>
        </Show>
      </SettingsList>
    </SettingsSection>
  )
}
