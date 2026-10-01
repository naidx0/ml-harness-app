import { createSignal, type Accessor } from "solid-js"
import { harness } from "../engine"
import { eventsPath, parseSse, type ThreadEvent } from "../panes/eval-events"

/**
 * One thread's event log, shared by every card in that thread's transcript.
 *
 * A transcript can hold dozens of harness cards and each may want the log
 * (for its plan diff, or to learn whether it carries the turn's effects).
 * Fetching it once per card would be dozens of identical reads of the whole
 * history, so the read is shared: one signal per thread, one request in
 * flight at a time, and a fresh-enough answer is reused rather than fetched
 * again. The read itself is the Eval pane's (`eventsPath`, `parseSse`): the
 * same finite `follow=false` history request.
 *
 * Module state, not a context, because cards are mounted by THEIR renderer
 * and a provider of ours cannot be put around them without editing their
 * tree.
 */

type Entry = {
  events: Accessor<ThreadEvent[] | undefined>
  set: (events: ThreadEvent[]) => void
  at: number
  inflight: Promise<void> | undefined
}

const entries = new Map<number, Entry>()

function entryOf(threadId: number): Entry {
  let entry = entries.get(threadId)
  if (!entry) {
    const [events, set] = createSignal<ThreadEvent[] | undefined>(undefined, { equals: false })
    entry = { events, set, at: 0, inflight: undefined }
    entries.set(threadId, entry)
  }
  return entry
}

/**
 * Read the log again unless the last read is younger than `maxAgeMs`. A
 * failed read keeps the last good log: a card that loses its footer for a
 * network blip is noise, and the next poll or mount asks again.
 */
export function refreshThreadEvents(threadId: number, maxAgeMs = 1500): Promise<void> {
  const entry = entryOf(threadId)
  if (entry.inflight) return entry.inflight
  if (entry.events() !== undefined && Date.now() - entry.at < maxAgeMs) return Promise.resolve()
  entry.inflight = harness<string>(eventsPath(threadId))
    .then((body) => {
      entry.at = Date.now()
      entry.set(typeof body === "string" ? parseSse(body) : [])
    })
    .catch(() => {
      entry.at = Date.now()
      if (entry.events() === undefined) entry.set([])
    })
    .finally(() => {
      entry.inflight = undefined
    })
  return entry.inflight
}

/** The shared log for a thread; reading it the first time starts the fetch. */
export function threadEvents(threadId: number): Accessor<ThreadEvent[] | undefined> {
  const entry = entryOf(threadId)
  if (entry.events() === undefined && !entry.inflight) void refreshThreadEvents(threadId)
  return entry.events
}
