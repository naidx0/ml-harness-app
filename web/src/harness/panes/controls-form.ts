/**
 * Every tool is also a control - the logic behind the Controls pane.
 *
 * `GET /api/tools` returns the SAME declaration the model is handed,
 * described for a person: label, group, verb, and fields taken out of the
 * identical JSON Schema (`app/tools/registry.py::as_control`). So nothing in
 * this file has a list of tools in it or knows what any tool does. Adding a
 * tool to the registry adds a button; changing a parameter changes the form.
 * A second declaration here would drift, and the half that drifted would be
 * the one a person with a text-only model depends on.
 */

export type ToolField = {
  name: string
  type: string
  description: string
  required: boolean
  enum: string[] | null
}

export type ToolControl = {
  name: string
  label: string
  group: string
  /** The imperative, for the approval line: "start a training run on this machine". */
  verb: string
  order: number
  description: string
  fields: ToolField[]
  reads: string[]
  writes: string[]
  measures?: string[]
  packs?: string[]
  needs_approval: boolean
}

export type ToolCatalogue = { controls: ToolControl[]; instruction_set: string }

/** `POST /api/tools/{name}` answers `{ tool, result }`. */
export type ToolRunAnswer = { tool: string; result: unknown }

export type ToolGroup = { group: string; controls: ToolControl[] }

/**
 * Tools grouped into packs, in the order the engine returned them - which is
 * the registry's own sort, `order` then name. A pack appears where its first
 * tool does; nothing is re-sorted here, because a second ordering would be a
 * second opinion about which tools matter.
 */
export function groupTools(controls: ToolControl[]): ToolGroup[] {
  const groups: ToolGroup[] = []
  const byName = new Map<string, ToolGroup>()
  for (const control of controls) {
    const existing = byName.get(control.group)
    if (existing) existing.controls.push(control)
    else {
      const group = { group: control.group, controls: [control] }
      byName.set(control.group, group)
      groups.push(group)
    }
  }
  return groups
}

/**
 * The search box. Every word must appear somewhere in the tool's name,
 * label, verb, pack or description, so "eval run" finds `run_eval` and
 * "training" finds the tool whose verb says it starts one. A pack with no
 * match is dropped rather than shown empty.
 */
export function filterTools(groups: ToolGroup[], query: string): ToolGroup[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return groups
  const matches = (control: ToolControl) => {
    const haystack = [control.name, control.name.replace(/_/g, " "), control.label, control.verb, control.group, control.description]
      .join(" ")
      .toLowerCase()
    return words.every((word) => haystack.includes(word))
  }
  return groups
    .map((group) => ({ group: group.group, controls: group.controls.filter(matches) }))
    .filter((group) => group.controls.length > 0)
}

/** The pack a tool lives in, so a focused tool can open its pack on arrival. */
export function packOf(groups: ToolGroup[], name: string): string | undefined {
  return groups.find((group) => group.controls.some((control) => control.name === name))?.group
}

export type FieldKind = "choice" | "flag" | "json" | "number" | "text"

/** Which input a schema field becomes. */
export function fieldKind(field: ToolField): FieldKind {
  if (field.enum && field.enum.length > 0) return "choice"
  if (field.type === "boolean") return "flag"
  if (field.type === "object" || field.type === "array") return "json"
  if (field.type === "integer" || field.type === "number") return "number"
  return "text"
}

/**
 * The fields a person is asked for.
 *
 * `thread_id` is dropped when a conversation is open, because the registry
 * fills it from the call site and overwrites whatever was typed
 * (`app/tools/registry.py`, the "call site's replaces it" note). A box whose
 * value is thrown away is a question with no effect. With no conversation
 * open the registry has nothing to fill it from, so the box stays.
 */
export function visibleFields(control: ToolControl, threadId: number | undefined): ToolField[] {
  if (threadId === undefined) return control.fields
  return control.fields.filter((field) => field.name !== "thread_id")
}

/**
 * A required field nobody has answered.
 *
 * AN EMPTY OBJECT OR ARRAY IS AN ANSWER, NOT A BLANK. JSON Schema `required`
 * means the key must be present, never that the object must be non-empty:
 * `run_diagnosis` takes a required `facts` object whose own description says
 * anything already measured is merged in for you, so `{}` is the honest fact
 * sheet. `coerce` sends `{}` or `[]` for a blank required one, so only
 * scalars can be missing.
 */
export function missingFields(fields: ToolField[], values: Record<string, string>): string[] {
  return fields
    .filter((field) => field.required && fieldKind(field) !== "json" && fieldKind(field) !== "flag")
    .filter((field) => !values[field.name]?.trim())
    .map((field) => field.name)
}

/**
 * Form strings to the types the schema declares.
 *
 * An empty optional field is OMITTED rather than sent as `""` or `0`, so the
 * engine's own default applies. Sending a zero where the person typed
 * nothing would be this layer inventing a value, which is the thing the
 * never-invent-a-number rule is about. Throws a sentence naming the field
 * when a value cannot be what the schema says it is.
 */
export function coerce(fields: ToolField[], values: Record<string, string>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const field of fields) {
    const raw = values[field.name]
    const kind = fieldKind(field)
    if (raw === undefined || raw.trim() === "") {
      if (field.required && field.type === "object") out[field.name] = {}
      if (field.required && field.type === "array") out[field.name] = []
      // A required flag left unticked is a false, not an absence: an unticked
      // box is the person's answer, and the schema asked for a boolean.
      if (field.required && kind === "flag") out[field.name] = false
      continue
    }
    if (kind === "flag") {
      out[field.name] = raw === "true"
      continue
    }
    if (kind === "number") {
      const parsed = Number(raw)
      if (!Number.isFinite(parsed)) throw new Error(`${field.name}: "${raw}" is not a number.`)
      if (field.type === "integer" && !Number.isInteger(parsed)) {
        // Rounding would send a number the person did not type.
        throw new Error(`${field.name}: "${raw}" is not a whole number.`)
      }
      out[field.name] = parsed
      continue
    }
    if (kind === "json") {
      let parsed: unknown
      try {
        parsed = JSON.parse(raw)
      } catch (failure) {
        throw new Error(
          `${field.name}: that is not valid JSON - ${failure instanceof Error ? failure.message : String(failure)}`,
        )
      }
      if (field.type === "array" && !Array.isArray(parsed)) throw new Error(`${field.name}: this parameter is a list, written [ ... ].`)
      if (field.type === "object" && (parsed === null || typeof parsed !== "object" || Array.isArray(parsed))) {
        throw new Error(`${field.name}: this parameter is an object, written { ... }.`)
      }
      out[field.name] = parsed
      continue
    }
    out[field.name] = raw
  }
  return out
}

export type RunOutcome =
  | { kind: "refused"; error: string }
  | { kind: "ran"; ok: boolean; result: unknown }

/**
 * A tool that ran and reported its own failure (`ok: false`) is a failed
 * step, not a successful one - the same reading `app/main.py` makes when it
 * files the `tool.result` row, so a button and a model call describe the
 * same run the same way.
 */
export function outcomeOf(result: unknown): RunOutcome {
  const failed = typeof result === "object" && result !== null && (result as { ok?: unknown }).ok === false
  return { kind: "ran", ok: !failed, result }
}

/**
 * The heading over a result. A refusal by the engine (a 4xx with a
 * sentence) is not the same as a tool that ran and said no, and neither is
 * the same as one that answered.
 */
export function outcomeHeading(outcome: RunOutcome): string {
  if (outcome.kind === "refused") return "The engine refused"
  return outcome.ok ? "Result" : "The tool said no"
}

/** Pretty text for the result block: strings as they are, everything else as indented JSON. */
export function prettyResult(result: unknown): string {
  if (typeof result === "string") return result
  if (result === undefined) return "(no answer)"
  try {
    return JSON.stringify(result, null, 2)
  } catch {
    return String(result)
  }
}
