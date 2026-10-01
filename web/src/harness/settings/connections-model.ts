import { shortModelName, type Connection, type Preset } from "../providers/local"

/**
 * The rules behind Settings > Connections, kept out of the component so they
 * can be tested without a network or a DOM.
 *
 * Carried over from the outgoing `Settings.tsx` (Models and Keys) and
 * `ConnectModel.tsx`. Each rule below existed there; the comments say why.
 */

/**
 * A connection as `GET /api/providers` returns it (`_provider_public` in
 * app/main.py). `Connection` in providers/local.ts is the subset the one-click
 * path needs; the settings page also shows what the probe learned.
 */
export type ConnectionRow = Connection & {
  capability_detail?: string
  ctx_len?: number | null
  ctx_len_provenance?: string
  created_at?: string
}

/** `GET /api/keychain`. Carries no secret: a backend name, a label, a prefix. */
export type Keychain = {
  available: boolean
  backend: string | null
  service: string
  env_prefix: string
  detail: string
}

/** One entry of `GET /api/providers/discover`. */
export type Candidate = {
  name: string
  base_url: string
  adapter: string
  reachable: boolean
  models: string[]
  suggested_model?: string
}

export type Adapter = "ollama" | "openai-compatible"

export const ADAPTERS: { value: Adapter; label: string }[] = [
  { value: "ollama", label: "Ollama" },
  { value: "openai-compatible", label: "OpenAI-compatible" },
]

/**
 * `tool_calling` is three states, not a boolean. `unknown` means nobody has
 * probed, which is a different fact from "probed, and no".
 */
export function describeTools(row: Pick<Connection, "tool_calling">): string {
  if (row.tool_calling === "yes") return "can call tools"
  if (row.tool_calling === "no") return "cannot call tools"
  return "tool calling not checked yet"
}

/** The active marker: in use, and whether its probe has answered. */
export function activeLabel(row: Pick<Connection, "is_active" | "tool_calling">): string | undefined {
  if (row.is_active !== 1) return undefined
  return row.tool_calling === "unknown" ? "In use" : "Ready"
}

/** Who said the context length, as a sentence rather than a chip. */
export function contextTitle(provenance: string | undefined): string {
  switch ((provenance ?? "").toLowerCase()) {
    case "measured":
      return "Context length read by a probe of this connection"
    case "declared":
      return "Context length reported by the server for this model"
    case "defaulted":
      return "Context length assumed - nothing reported one"
    default:
      return "Context length"
  }
}

/**
 * The one-line summary under a connection's name. The model is its short name
 * (`shortModelName`); the row carries the full id in a title and in Edit.
 */
export function connectionSummary(row: ConnectionRow): string {
  const parts = [shortModelName(row.model) || row.model, row.base_url, row.kind === "local" ? "on this computer" : "remote", describeTools(row)]
  if (typeof row.ctx_len === "number") parts.push(`${row.ctx_len.toLocaleString()} token context`)
  if (row.has_key) parts.push("key in the keychain")
  return parts.join(" · ")
}

export type EditDraft = { name: string; base_url: string; model: string; api_key: string }

export function draftFrom(row: Connection): EditDraft {
  return { name: row.name, base_url: row.base_url, model: row.model, api_key: "" }
}

/**
 * Editing the endpoint or the model drops what the last probe measured - the
 * engine does this, and the page says so before it happens.
 */
export function dropsProbe(row: Connection, draft: EditDraft): boolean {
  return draft.base_url.trim() !== row.base_url || draft.model.trim() !== row.model
}

export type ConnectionPatch = { name?: string; base_url?: string; model?: string; api_key?: string }

/**
 * The PATCH body for an edit. Only fields that changed are sent, a blank field
 * keeps the stored value, and `api_key` is LEFT OFF when nothing was typed:
 * the engine reads absent as "keep the key" and empty as "delete it", and a
 * settings form has no key to put back because the engine never returns one.
 */
export function editPatch(row: Connection, draft: EditDraft): ConnectionPatch {
  const patch: ConnectionPatch = {}
  const name = draft.name.trim()
  const base = draft.base_url.trim()
  const model = draft.model.trim()
  if (name && name !== row.name) patch.name = name
  if (base && base !== row.base_url) patch.base_url = base
  if (model && model !== row.model) patch.model = model
  if (draft.api_key) patch.api_key = draft.api_key
  return patch
}

export function isEmptyPatch(patch: ConnectionPatch): boolean {
  return Object.keys(patch).length === 0
}

export type AddDraft = { name: string; base_url: string; adapter: Adapter; model: string; api_key: string }

export const EMPTY_ADD: AddDraft = { name: "", base_url: "", adapter: "openai-compatible", model: "", api_key: "" }

/** A preset fills the endpoint, the adapter and a name - and a model only if none is typed yet. */
export function applyPreset(draft: AddDraft, preset: Preset): AddDraft {
  return {
    ...draft,
    name: preset.name,
    base_url: preset.base_url,
    adapter: preset.adapter === "ollama" ? "ollama" : "openai-compatible",
    model: draft.model.trim() ? draft.model : preset.default_model,
  }
}

export function addReady(draft: AddDraft): boolean {
  return Boolean(draft.name.trim() && draft.base_url.trim() && draft.model.trim())
}

/** The POST body for a new connection. The key is omitted entirely when empty. */
export function addBody(draft: AddDraft) {
  return {
    name: draft.name.trim(),
    base_url: draft.base_url.trim(),
    model: draft.model.trim(),
    adapter: draft.adapter,
    ...(draft.api_key ? { api_key: draft.api_key } : {}),
  }
}

/** "a, b, c +2 more", or a plain sentence when the server listed none. */
export function modelList(models: string[], show = 3): string {
  if (models.length === 0) return "no models listed yet"
  const head = models.slice(0, show).join(", ")
  return models.length > show ? `${head} +${models.length - show} more` : head
}

export function reachable(candidates: Candidate[] | undefined): Candidate[] {
  return (candidates ?? []).filter((candidate) => candidate.reachable)
}

export function keyHolders<T extends Pick<Connection, "has_key">>(rows: T[] | undefined): T[] {
  return (rows ?? []).filter((row) => row.has_key)
}

/** The local connection already pointing at this model, if any - it is "in use", not "connect". */
export function inUseModel(rows: Connection[] | undefined, model: string): boolean {
  return (rows ?? []).some((row) => row.is_active === 1 && row.model === model)
}
