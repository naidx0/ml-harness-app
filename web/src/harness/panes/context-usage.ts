/**
 * The session readouts OpenCode's own Context tab shows, merged into the
 * harness Context view (web/src/harness/panel/context-tab.tsx).
 *
 * Their tab (session/files/session-context-tab.tsx) shows sixteen figures
 * taken from their session store: session title, message count, provider,
 * model, context limit, total tokens, usage percent, input, output,
 * reasoning and cache read/write tokens, user and assistant message counts,
 * total cost, session created and last activity - plus the system prompt,
 * the raw messages and an Export button.
 *
 * WHY THIS IS NOT A COPY OF THEIR ARITHMETIC. Their tab prints every figure
 * it is handed, and this engine's facade hands every reply
 * `tokens: {input: 0, ...}` and `cost: 0` (app/facade/translate.py,
 * `session.step.ended`): the harness counts the prompt it assembles, not the
 * provider's per-reply usage. Printed as they are, those zeros read as "this
 * conversation cost nothing and used 0% of the window" - a number nobody
 * measured. So a token figure is shown only when a reply carries a non-zero
 * one, a cost only when it is above zero, and a percentage only when both a
 * reported total and the model's declared window exist. Otherwise the view
 * says the figure is not reported, and the measured prompt breakdown below it
 * (GET /api/threads/{id}/context) is where the real count lives.
 */

export type UsageTokens = {
  input: number
  output: number
  reasoning: number
  cache: { read: number; write: number }
}

/** The fields of one of their session messages this reads. */
export type UsageMessage = {
  type: string
  time?: { created?: number }
  tokens?: UsageTokens
  model?: { providerID: string; id: string }
  text?: string
}

/** The fields of their session info this reads. */
export type UsageSession = { title?: string; cost?: number; time?: { created?: number } }

/** A model as their provider catalogue names it, with its declared window. */
export type UsageModel = { providerName?: string; modelName?: string; limit?: number }

export type SessionUsage = {
  title: string | undefined
  counts: { all: number; user: number; assistant: number }
  provider: string | undefined
  model: string | undefined
  /** The model's context window as the model list declares it. */
  limit: number | undefined
  /** Only when a reply reported non-zero usage; see the module note. */
  tokens:
    | {
        total: number
        input: number
        output: number
        reasoning: number
        cacheRead: number
        cacheWrite: number
        /** Whole percent of `limit`, or null without a declared window. */
        usage: number | null
      }
    | undefined
  /** Only when above zero. */
  cost: number | undefined
  created: number | undefined
  lastReply: number | undefined
  systemPrompt: string | undefined
}

const total = (tokens: UsageTokens) =>
  tokens.input + tokens.output + tokens.reasoning + tokens.cache.read + tokens.cache.write

export function sessionUsage(
  messages: readonly UsageMessage[],
  session: UsageSession | undefined,
  modelOf: (providerID: string, modelID: string) => UsageModel | undefined,
): SessionUsage {
  const counts = { all: messages.length, user: 0, assistant: 0 }
  for (const message of messages) {
    if (message.type === "user") counts.user += 1
    if (message.type === "assistant") counts.assistant += 1
  }

  const assistants = messages.filter((message) => message.type === "assistant")
  const lastReply = assistants.at(-1)
  const named = assistants.findLast((message) => !!message.model)
  const model = named?.model ? modelOf(named.model.providerID, named.model.id) : undefined
  const limit = model?.limit && model.limit > 0 ? model.limit : undefined

  // Their rule - the last reply that carries usage - with the one change the
  // module note explains: a reply whose usage adds up to zero reported none.
  const reported = assistants.findLast((message) => !!message.tokens && total(message.tokens) > 0)
  const tokens = reported?.tokens
    ? {
        total: total(reported.tokens),
        input: reported.tokens.input,
        output: reported.tokens.output,
        reasoning: reported.tokens.reasoning,
        cacheRead: reported.tokens.cache.read,
        cacheWrite: reported.tokens.cache.write,
        usage: limit ? Math.round((total(reported.tokens) / limit) * 100) : null,
      }
    : undefined

  const system = messages.findLast((message) => message.type === "system")?.text?.trim()

  return {
    title: session?.title || undefined,
    counts,
    provider: named?.model ? (model?.providerName ?? named.model.providerID) : undefined,
    model: named?.model ? (model?.modelName ?? named.model.id) : undefined,
    limit,
    tokens,
    cost: session?.cost && session.cost > 0 ? session.cost : undefined,
    created: session?.time?.created || undefined,
    lastReply: lastReply?.time?.created || undefined,
    systemPrompt: system || undefined,
  }
}
