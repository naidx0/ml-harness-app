import { createSignal } from "solid-js"

/**
 * How a harness pane asks the session for something it cannot reach itself.
 *
 * A pane renders in two places: OpenCode's session side panel, and a pop-out
 * window with no session around it. Neither can import the session's
 * composer or router, so a pane says what it wants on `window` and the
 * session mount (session/mount.tsx) answers. One window's events never reach
 * another, so a pop-out's request is heard by nobody - which is the signal
 * the pane needs: every request says whether it was taken.
 *
 * - `harness:open-pane` {pane, threadId?}: open a harness tab in the side
 *   panel. A request that names a thread is only for the session showing
 *   that thread; any other session declines it (`paneRequestIsOurs`).
 * - `harness:compose` {text}: put a draft into this session's composer and
 *   focus it. Never sends.
 * - `harness:open-thread` {threadId}: open the conversation behind a harness
 *   thread (a sub-agent's child) in this tab.
 */

export const OPEN_PANE_EVENT = "harness:open-pane"
export const COMPOSE_EVENT = "harness:compose"
export const OPEN_THREAD_EVENT = "harness:open-thread"

export type OpenPaneDetail = { pane: string; threadId?: number }
export type ComposeDetail = { text: string }
export type OpenThreadDetail = { threadId: number }

export type BridgeEvents = {
  [OPEN_PANE_EVENT]: OpenPaneDetail
  [COMPOSE_EVENT]: ComposeDetail
  [OPEN_THREAD_EVENT]: OpenThreadDetail
}
export type BridgeEvent = keyof BridgeEvents

/** Each detail checked on the way in: a CustomEvent on `window` can come
 *  from anything on the page, and a handler should never act on a shape it
 *  was not promised. */
const READERS: { [K in BridgeEvent]: (detail: unknown) => BridgeEvents[K] | undefined } = {
  [OPEN_PANE_EVENT]: (detail) => {
    const record = detail as { pane?: unknown; threadId?: unknown } | null
    const pane = record?.pane
    if (typeof pane !== "string" || !pane) return undefined
    const threadId = record?.threadId
    if (threadId === undefined) return { pane }
    // A thread that is named must be a real one: a malformed id read as "no
    // thread" would let any session take a request meant for one.
    return isThreadId(threadId) ? { pane, threadId } : undefined
  },
  [COMPOSE_EVENT]: (detail) => {
    const text = (detail as { text?: unknown } | null)?.text
    return typeof text === "string" && text.trim() ? { text } : undefined
  },
  [OPEN_THREAD_EVENT]: (detail) => {
    const threadId = (detail as { threadId?: unknown } | null)?.threadId
    return isThreadId(threadId) ? { threadId } : undefined
  },
}

function isThreadId(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0
}

export function readDetail<K extends BridgeEvent>(type: K, detail: unknown): BridgeEvents[K] | undefined {
  return READERS[type](detail) as BridgeEvents[K] | undefined
}

/**
 * Dispatches a request and says whether a session took it. The event is
 * cancelable and a handler that acts on it cancels it (see `onBridge`), so
 * `false` means nobody here could: a pop-out, or no session open.
 */
function send<K extends BridgeEvent>(type: K, detail: BridgeEvents[K], target: EventTarget = window): boolean {
  const event = new CustomEvent<BridgeEvents[K]>(type, { detail, cancelable: true })
  return !target.dispatchEvent(event)
}

/** `threadId` is the thread the asker belongs to (a result card's thread).
 *  A session showing another thread declines, so the asker falls back. */
export const requestPane = (pane: string, threadId?: number, target?: EventTarget) =>
  send(OPEN_PANE_EVENT, threadId === undefined ? { pane } : { pane, threadId }, target)
export const requestCompose = (text: string, target?: EventTarget) => send(COMPOSE_EVENT, { text }, target)
export const requestOpenThread = (threadId: number, target?: EventTarget) =>
  send(OPEN_THREAD_EVENT, { threadId }, target)

/**
 * Answers one request type. The handler returns `false` to decline (the
 * request then reads as not taken); anything else takes it. Returns the
 * remover.
 */
export function onBridge<K extends BridgeEvent>(
  type: K,
  handler: (detail: BridgeEvents[K]) => boolean | void,
  target: EventTarget = window,
): () => void {
  const listener = (event: Event) => {
    const detail = readDetail(type, (event as CustomEvent).detail)
    if (!detail) return
    if (handler(detail) !== false) event.preventDefault()
  }
  target.addEventListener(type, listener)
  return () => target.removeEventListener(type, listener)
}

/**
 * Whether a session in THIS window is answering requests. Module state is per
 * window, so a pop-out reads false for ever and the main window reads true
 * while a session is mounted. A pane uses it to hide or explain a control
 * before it is pressed; `send`'s answer covers the press itself.
 */
const [claims, setClaims] = createSignal(0)
export const sessionBridgePresent = () => claims() > 0

export function claimSessionBridge(): () => void {
  setClaims((count) => count + 1)
  let released = false
  return () => {
    if (released) return
    released = true
    setClaims((count) => count - 1)
  }
}

/**
 * Whether an open-pane request is for the session showing `sessionThread`.
 * A request that names no thread is for whichever session hears it; one that
 * names a thread is only for the session on that thread - a card from another
 * chat must not open this chat's pane on its data.
 */
export function paneRequestIsOurs(detail: OpenPaneDetail, sessionThread: number | undefined): boolean {
  return detail.threadId === undefined || detail.threadId === sessionThread
}

/** The engine's instruction to the interface, as the facade sends it
 *  (app/facade/translate.py `_on_ui_open`): `{tab, sessionID, threadID}`. */
export const UI_OPEN_EVENT = "harness.ui.open"

/**
 * The pane a `harness.ui.open` event asks THIS session to open, or undefined.
 *
 * The facade's stream carries every thread's events to every window, so an
 * instruction for another chat arrives here too. It is acted on only when it
 * names this session (`sessionID`) or this session's harness thread
 * (`threadID`); an event that names neither is nobody's.
 */
export function uiOpenTab(event: unknown, here: { sessionID?: string; threadID?: number }): string | undefined {
  const record = event as { type?: unknown; data?: { tab?: unknown; sessionID?: unknown; threadID?: unknown } } | null
  if (record?.type !== UI_OPEN_EVENT) return undefined
  const data = record.data
  const tab = data?.tab
  if (typeof tab !== "string" || !tab) return undefined
  const bySession = !!here.sessionID && data?.sessionID === here.sessionID
  const byThread = here.threadID !== undefined && data?.threadID === here.threadID
  return bySession || byThread ? tab : undefined
}
