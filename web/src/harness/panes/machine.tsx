import { For, Match, Show, Switch } from "solid-js"
import { Button } from "@opencode/ui/button"
import { ErrorLine, ProvenanceTag, Row, Section, useHarnessRead, type Provenance } from "../ui"
import type { PaneProps } from "../panel/panes"

/**
 * What this machine is, with where each number came from.
 *
 * `GET /local_specs` (app/hwdetect.py). A field the detector could not read
 * is null, never a guess, so it is shown as "not detected" rather than
 * hidden: a missing row is invisible, an empty one is information.
 *
 * Better than the outgoing pane in two ways the parity list recorded: it can
 * be re-checked, and the two buttons that had no handler are gone.
 */

type Field = "gpu_name" | "vram_gb" | "driver_version" | "compute_capability" | "ram_gb" | "disk_free_gb" | "os"

type LocalSpecs = Partial<Record<Field, string | number | null>> & {
  provenance?: Partial<Record<Field, Provenance>>
  sources?: Partial<Record<Field, string>>
  warnings?: string[]
}

const ROWS: { field: Field; label: string; unit?: string }[] = [
  { field: "gpu_name", label: "Graphics card" },
  { field: "vram_gb", label: "Video memory", unit: "GB" },
  { field: "driver_version", label: "Driver" },
  { field: "compute_capability", label: "Compute capability" },
  { field: "ram_gb", label: "Memory", unit: "GB" },
  { field: "disk_free_gb", label: "Free disk", unit: "GB" },
  { field: "os", label: "System" },
]

function show(value: string | number | null | undefined, unit?: string) {
  if (value === null || value === undefined || value === "") return undefined
  if (typeof value === "number") return `${Number.isInteger(value) ? value : value.toFixed(1)}${unit ? ` ${unit}` : ""}`
  return value
}

export default function MachinePane(_: PaneProps) {
  const specs = useHarnessRead<LocalSpecs>(() => "/local_specs")
  return (
    <Section
      title="This computer"
      action={
        <Button size="small" variant="ghost" onClick={() => void specs.refetch()} disabled={specs.data.loading}>
          {specs.data.loading ? "Checking" : "Check again"}
        </Button>
      }
    >
      <Switch>
        <Match when={specs.data.error}>
          <ErrorLine error={specs.data.error} />
        </Match>
        <Match when={true}>
          <For each={ROWS}>
            {(row) => {
              const value = () => show(specs.data()?.[row.field], row.unit)
              return (
                <Row
                  label={row.label}
                  tag={
                    <ProvenanceTag
                      value={specs.data()?.provenance?.[row.field]}
                      source={specs.data()?.sources?.[row.field]}
                    />
                  }
                >
                  <Show when={value()} fallback={<span class="text-v2-text-text-faint">{specs.data.loading ? "…" : "not detected"}</span>}>
                    {value()}
                  </Show>
                </Row>
              )
            }}
          </For>
          <For each={specs.data()?.warnings ?? []}>
            {(warning) => <div class="px-4 py-1 text-12-regular text-v2-text-text-muted">{warning}</div>}
          </For>
        </Match>
      </Switch>
    </Section>
  )
}
