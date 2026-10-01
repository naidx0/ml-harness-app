import { For, Show } from "solid-js"
import { Button } from "@opencode/ui/button"
import { SettingsList } from "@/settings/list"
import { SettingsRow } from "@/settings/row"
import "@/settings/settings.css"
import { ProvenanceTag, useHarnessRead } from "../ui"
import { machineRows, type LocalSpecs } from "./machine-fields"
import { EmptyLine, ErrorText, PageHeader, SettingsSection } from "./connections-parts"

/**
 * Settings > This machine (PARITY 8.4): every hardware field the engine read,
 * with where it came from.
 *
 * Training happens here, so these are the numbers every feasibility verdict is
 * computed from. Each row carries its provenance tag and the command that was
 * actually run to get it - the one version of provenance a person can check
 * for themselves. A field that could not be read says so; it is never
 * defaulted into a number.
 */
/** The line in place of the rows when there are none. */
export function emptyMachineLine(read: { loading: boolean; answered: boolean }) {
  return read.loading || !read.answered ? "Reading this machine…" : "Nothing reported."
}

export default function Section() {
  const specs = useHarnessRead<LocalSpecs>(() => "/local_specs")
  const reading = () => (specs.data.error ? undefined : specs.data.latest)
  const rows = () => machineRows(reading())
  const warnings = () => reading()?.warnings ?? []

  return (
    <>
      <PageHeader
        title="This machine"
        description="What the engine measured about this computer, and how it measured each number."
      />
      <div class="settings-tab-body settings-tab-body--sectioned">
        <SettingsSection
          title="Hardware"
          action={
            <Button
              size="small"
              variant="ghost"
              icon="refresh"
              disabled={specs.data.loading}
              onClick={() => void specs.refetch()}
            >
              {specs.data.loading ? "Checking…" : "Check again"}
            </Button>
          }
        >
          <Show when={specs.data.error}>
            {(failure) => (
              <div class="flex flex-col gap-1">
                <p class="text-[13px] text-v2-text-text-muted">The engine could not report this machine:</p>
                <ErrorText error={failure()} />
              </div>
            )}
          </Show>
          <SettingsList>
            {/* "Reading" only while a read is out: after a failed read it said
                "Reading this machine…" for ever, under the error. */}
            <Show
              when={rows().length > 0}
              fallback={<EmptyLine>{emptyMachineLine(specs.data)}</EmptyLine>}
            >
              <For each={rows()}>
                {(row) => (
                  <SettingsRow
                    title={row.label}
                    description={
                      <span class="text-12-mono">{row.source ? row.source : "no source reported"}</span>
                    }
                  >
                    <div class="flex items-center gap-2">
                      <span
                        class="text-[13px] tabular-nums"
                        classList={{
                          "text-v2-text-text-base": row.value !== undefined,
                          "text-v2-text-text-faint": row.value === undefined,
                        }}
                      >
                        {row.value ?? "not detected"}
                      </span>
                      <ProvenanceTag value={row.provenance} source={row.source} />
                    </div>
                  </SettingsRow>
                )}
              </For>
            </Show>
          </SettingsList>
        </SettingsSection>

        <Show when={warnings().length > 0}>
          <SettingsSection title="What the detector could not do">
            <SettingsList>
              <For each={warnings()}>
                {(warning) => <div class="border-b border-v2-border-border-base py-4 text-[13px] text-v2-text-text-muted last:border-b-0">{warning}</div>}
              </For>
            </SettingsList>
          </SettingsSection>
        </Show>
      </div>
    </>
  )
}
