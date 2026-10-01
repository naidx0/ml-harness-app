import { harness } from "../engine"

/**
 * One click from "a model on this machine" to "the model this chat uses".
 *
 * The same flow the outgoing app's `connectLocal` had, and for the same
 * reasons: a model already pulled into Ollama needs no URL, no adapter choice
 * and no key, so none is asked for; and pressing it twice must not pile up
 * identical connections, so an existing row for the same endpoint and model is
 * activated and re-probed instead of duplicated.
 */

export type Connection = {
  id: number
  name: string
  base_url: string
  model: string
  adapter: string
  kind: "local" | "remote"
  tool_calling: string
  is_active: 0 | 1
  has_key: boolean
  effort: string
}

export type Preset = { name: string; base_url: string; adapter: string; default_model: string; needs_key: boolean }

export type LocalModel = {
  name: string
  family: string | null
  params_b: number | null
  capabilities: string[]
  on_disk_gb: number | null
}

/** Used only if the presets route fails; `app/providers.PRESETS` is the source. */
const OLLAMA_FALLBACK: Preset = {
  name: "Ollama",
  base_url: "http://127.0.0.1:11434",
  adapter: "ollama",
  default_model: "",
  needs_key: false,
}

export async function listLocalModels(): Promise<LocalModel[]> {
  const outcome = await harness<{ result?: { ok?: boolean; models?: LocalModel[]; detail?: string; error?: string } }>(
    "/api/tools/list_local_models",
    { body: { arguments: {}, approved: false } },
  )
  const result = outcome?.result
  if (result?.ok === false) throw new Error(result.detail ?? result.error ?? "Ollama did not answer")
  return result?.models ?? []
}

/** A tag that says how big the model is ("4b", "0.5b", "8x7b", "e2b", "270m"), which is worth keeping. */
const SIZE_TAG = /^(?:\d+x)?(?:e)?\d+(?:\.\d+)?[bm](?![a-z])/i
/** What the file is packed as, which says nothing about the model. */
const FORMAT_MARKER = /[-_.](?:gguf|safetensors)$/i

/**
 * A model id as a person reads it (the owner, 2026-09-22: "automatically
 * extract the model name instead of the whole link"):
 *
 *   hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0  ->  MiniCPM5-1B
 *   qwen3.5:4b                           ->  qwen3.5 4b
 *   llama3.2:latest                      ->  llama3.2
 *
 * The last path segment; a trailing `:tag` dropped unless it is a size, which
 * is kept after a space because two sizes of one family are different models;
 * then a packing marker (-GGUF, -safetensors) dropped. The full id stays the
 * thing stored and sent - this is only what a surface prints.
 */
export function shortModelName(id: string | null | undefined): string {
  const whole = (id ?? "").trim()
  if (!whole) return ""
  const segment = whole.split("/").filter(Boolean).pop() ?? whole
  const colon = segment.lastIndexOf(":")
  let base = colon > 0 ? segment.slice(0, colon) : segment
  const tag = colon > 0 ? segment.slice(colon + 1) : ""
  while (FORMAT_MARKER.test(base)) base = base.replace(FORMAT_MARKER, "")
  const size = SIZE_TAG.exec(tag)?.[0]
  const name = base || segment
  return size ? `${name} ${size}` : name
}

/**
 * The name a new local connection gets: the model, not the endpoint. Every
 * one-click connection used to be named after the endpoint, which is the same
 * string for all of them - the owner once had six rows all reading "Ollama".
 * Now the short name: a nickname of "hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0" was
 * the whole link again.
 */
export function nameForALocalModel(model: string) {
  return shortModelName(model) || model
}

/**
 * The name a connection shows: its nickname, unless the nickname is only the
 * model id again (what one-click connections used to be named, with or without
 * `:latest`) - then the short name. A blank nickname is no nickname.
 */
export function connectionLabel(row: Pick<Connection, "name" | "model"> | undefined): string {
  if (!row) return ""
  const nickname = row.name?.trim() ?? ""
  const model = row.model ?? ""
  if (nickname && nickname !== model && nickname !== model.replace(/:latest$/, "")) return nickname
  return shortModelName(model) || nickname
}

/**
 * What a model on this machine is called on screen: the nickname of the
 * connection already made for it (the connection's `name`, which Settings >
 * Connections edits), or the model's short name when there is none. A
 * connection is for this model when it is an Ollama connection to the same
 * model id - the pair `connectLocal` would reuse.
 */
export function localModelLabel(
  model: string,
  connections: readonly Pick<Connection, "name" | "model" | "adapter">[] | undefined,
): string {
  const row = connections?.find((one) => one.adapter === "ollama" && one.model === model)
  return row ? connectionLabel(row) : shortModelName(model) || model
}

export async function connectLocal(model: string): Promise<Connection> {
  const [connections, presets] = await Promise.all([
    harness<Connection[]>("/api/providers"),
    harness<Preset[]>("/api/provider_presets").catch(() => [] as Preset[]),
  ])
  const target = presets.find((preset) => preset.adapter === "ollama") ?? OLLAMA_FALLBACK
  const existing = connections.find(
    (row) => row.model === model && row.adapter === target.adapter && row.base_url === target.base_url,
  )
  const row =
    existing ??
    (await harness<Connection>("/api/providers", {
      body: { name: nameForALocalModel(model), base_url: target.base_url, model, adapter: target.adapter },
    }))
  await harness(`/api/providers/${row.id}/activate`, { method: "POST" })
  return harness<Connection>(`/api/providers/${row.id}/probe`, { method: "POST" })
}
