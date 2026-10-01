import { threadIdOf } from "../panel/panes"

/**
 * Which OpenCode session is a harness thread.
 *
 * The facade (app/facade/sessions.py) names a thread in one of two ways: the
 * id their client minted when it created the conversation (recorded in
 * `facade_sessions`), or `ses_<thread>` for a thread the engine made itself -
 * which is what a sub-agent's child is, since `subagents` creates it without
 * any client. Every session it describes carries `metadata.harness.threadID`,
 * and a child carries its parent's session id as `parentID` (the list route
 * filters on it). So the thread is always matched by that metadata, never by
 * reading an id, and the `ses_<n>` guess is only ever a question to the
 * server whose answer is checked.
 */

export type SessionLike = { id: string; metadata?: unknown }

export function sessionForThread<T extends SessionLike>(sessions: Iterable<T>, threadId: number): T | undefined {
  for (const session of sessions) if (threadIdOf(session) === threadId) return session
}

/** The id the facade gives a thread that no client named. A guess to ask
 *  about, not an answer: a client-minted id can be anything `ses...`. */
export const engineSessionId = (threadId: number) => `ses_${threadId}`

export type SessionSources<T extends SessionLike> = {
  /** Sessions this window already holds. */
  known: () => Iterable<T>
  /** The current session's children - where a sub-agent's conversation is listed. */
  children?: () => Promise<T[]>
  /** One session by id; rejects or resolves undefined when there is none. */
  get: (sessionID: string) => Promise<T | undefined>
}

/**
 * Cheapest first: what is already loaded, then the children of this
 * conversation (one list call), then the engine-made id asked directly and
 * accepted only if the answer names the same thread.
 */
export async function resolveThreadSession<T extends SessionLike>(
  threadId: number,
  sources: SessionSources<T>,
): Promise<T | undefined> {
  const known = sessionForThread(sources.known(), threadId)
  if (known) return known
  if (sources.children) {
    const children = await sources.children().catch(() => [] as T[])
    const child = sessionForThread(children, threadId)
    if (child) return child
  }
  const asked = await sources.get(engineSessionId(threadId)).catch(() => undefined)
  return asked && threadIdOf(asked) === threadId ? asked : undefined
}
