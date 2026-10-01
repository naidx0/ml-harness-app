import { harness, HarnessError } from "../engine"
import type { Connection } from "./local"

/**
 * Their "Custom provider" form, saved as harness connections (patch P16).
 *
 * The form is fully built in their interface - name, base URL, key, a list of
 * models - and its save is disabled upstream until their server grows a config
 * API. The harness already has one: a connection is an OpenAI-compatible
 * endpoint, a model and an optional key. So each model the form lists becomes
 * one connection, and the first is made active and probed, which is exactly
 * what "Connect and check" did in the outgoing app. This is how LM Studio,
 * llama.cpp or vLLM at a non-default address are connected.
 *
 * The key goes to the engine once and into the OS keychain; it is never kept
 * here.
 */

type CustomProvider = {
  name: string
  key?: string
  config: { options: { baseURL: string }; models: Record<string, { name: string }> }
}

export async function saveHarnessCustomProvider<T extends CustomProvider>(result: T): Promise<T> {
  const models = Object.entries(result.config.models)
  if (models.length === 0) throw new Error("Add at least one model id.")
  const created: Connection[] = []
  for (const [model, info] of models) {
    const name = info.name || `${result.name} ${model}`
    try {
      created.push(
        await harness<Connection>("/api/providers", {
          body: {
            name,
            base_url: result.config.options.baseURL,
            model,
            adapter: "openai-compatible",
            ...(result.key ? { api_key: result.key } : {}),
          },
        }),
      )
    } catch (failure) {
      throw new Error(partialSaveMessage(failure, name, created, models.length, !!result.key))
    }
  }
  const first = created[0]!
  await harness(`/api/providers/${first.id}/activate`, { method: "POST" })
  await harness(`/api/providers/${first.id}/probe`, { method: "POST" })
  return result
}

/**
 * What a create that failed partway leaves behind, said plainly - their
 * dialog shows the thrown message.
 *
 * A keyed create answers 503 when there is no OS keychain, and by then the
 * engine has ALREADY saved the connection - without its key (app/main.py,
 * `create_provider_ep`: "the connection was saved but the key was not"). So
 * that row exists keyless, the rows before it exist with their key, and
 * nothing after it was attempted. Nothing is activated or probed: a keyless
 * row made active would fail on the first message with no reason given.
 */
export function partialSaveMessage(
  failure: unknown,
  name: string,
  created: readonly Pick<Connection, "name">[],
  total: number,
  keyed: boolean,
): string {
  const detail = failure instanceof Error ? failure.message : String(failure)
  const before = created.map((row) => row.name)
  const skipped = total - created.length - 1
  const parts: string[] = []
  if (keyed && failure instanceof HarnessError && failure.status === 503) {
    parts.push(`"${name}" was saved WITHOUT its key: ${detail}.`)
    if (before.length) parts.push(`Saved with the key before that: ${before.map((one) => `"${one}"`).join(", ")}.`)
    parts.push(
      "Nothing was made active. Add the key to that connection in Settings > Connections once this computer has a keychain, or remove it.",
    )
  } else {
    parts.push(`Could not save "${name}": ${detail}.`)
    if (before.length) parts.push(`Already saved: ${before.map((one) => `"${one}"`).join(", ")}. Nothing was made active.`)
  }
  if (skipped > 0) parts.push(`${skipped} more model${skipped === 1 ? " was" : "s were"} not saved.`)
  return parts.join(" ")
}
