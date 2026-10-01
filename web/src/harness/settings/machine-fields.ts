import type { Provenance } from "../ui"

/**
 * What `GET /local_specs` (app/hwdetect.py) reports, turned into rows.
 *
 * A field the detector could not read is null, never a guess, and it is shown
 * as "not detected" rather than hidden: a missing row is invisible, an empty
 * one is information.
 *
 * EVERY FIELD, NOT A HAND-PICKED LIST. The known fields get a label and a unit;
 * any other value the engine adds to the payload still gets a row, under its
 * own name, so a new reading cannot go missing from this page just because
 * nobody added it here.
 */

export type LocalSpecs = Record<string, unknown> & {
  provenance?: Record<string, string>
  sources?: Record<string, string>
  warnings?: string[]
}

export type MachineRow = {
  field: string
  label: string
  value: string | undefined
  provenance: Provenance | undefined
  source: string | undefined
}

const KNOWN: { field: string; label: string; unit?: string }[] = [
  { field: "gpu_name", label: "Graphics card" },
  { field: "vram_gb", label: "Video memory", unit: "GB" },
  { field: "driver_version", label: "Driver" },
  { field: "compute_capability", label: "Compute capability" },
  { field: "ram_gb", label: "System memory", unit: "GB" },
  { field: "disk_free_gb", label: "Free disk", unit: "GB" },
  { field: "os", label: "Operating system" },
]

/** Keys that describe the readings rather than being one. */
const META = new Set(["provenance", "sources", "warnings"])

const PROVENANCES: readonly string[] = ["measured", "inferred", "declared", "defaulted", "untested_on_this_platform"]

export function provenanceOf(value: unknown): Provenance | undefined {
  if (typeof value !== "string") return undefined
  const lower = value.toLowerCase()
  return PROVENANCES.includes(lower) ? (lower as Provenance) : undefined
}

export function formatReading(value: unknown, unit?: string): string | undefined {
  if (value === null || value === undefined || value === "") return undefined
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return undefined
    const text = Number.isInteger(value) ? String(value) : value.toFixed(1)
    return unit ? `${text} ${unit}` : text
  }
  if (typeof value === "boolean") return value ? "yes" : "no"
  if (typeof value === "string") return value
  return JSON.stringify(value)
}

/** `some_field_gb` -> "Some field gb". Only for fields this file has no label for. */
function labelFor(field: string): string {
  const words = field.replace(/_/g, " ").trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export function machineRows(specs: LocalSpecs | undefined): MachineRow[] {
  if (!specs) return []
  const row = (field: string, label: string, unit?: string): MachineRow => ({
    field,
    label,
    value: formatReading(specs[field], unit),
    provenance: provenanceOf(specs.provenance?.[field]),
    source: specs.sources?.[field],
  })
  const known = KNOWN.map((entry) => row(entry.field, entry.label, entry.unit))
  const seen = new Set(KNOWN.map((entry) => entry.field))
  const extra = Object.keys(specs)
    .filter((field) => !seen.has(field) && !META.has(field))
    .sort()
    .map((field) => row(field, labelFor(field)))
  return [...known, ...extra]
}
