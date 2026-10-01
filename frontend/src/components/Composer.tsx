/**
 * The composer — the most important component in the product, drawn to
 * Graphite.
 *
 * "A rounded rectangle at --r-16 (--r-18 here, on the adopted ramp), surface
 * one step above the ground, one quiet border, multi-line capable. The control
 * row lives INSIDE the composer; the run-target tabs and the branch indicator
 * live outside and below it, muted and small, because they are state rather
 * than input."
 *
 * THE SIGNATURE ELEMENT IS RESTORED. DESIGN_SYSTEM §5 mandated a 28px square
 * at --r-6 and argued that a circular send "reads as a search box". Graphite
 * restores Codex's circular filled send and resolves that objection a different
 * way: the composer itself stays a rounded RECTANGLE and never a pill. A
 * rounded rectangle with a circular send reads as a composer; a pill with a
 * circular send reads as a search box. The shape of the container was always
 * the real carrier of that signal.
 *
 * ── THE PLUS, AFTER MAX USED IT ──────────────────────────────────────────
 *
 *   "The plus takes you to knowledge, which looks like it takes you to the
 *    terminal or something. It's cool, but it's a little hard to understand."
 *
 * He was right, and the reason is specific rather than cosmetic. The plus
 * opened the Data pane, and the Data pane is an empty state — it says the
 * harness reads data by path and points at the tools panel. So pressing the
 * one affordance whose job is "give me your stuff" produced a paragraph
 * explaining that this is not where you give it your stuff. Two hops from a
 * button to an explanation of why the button could not help.
 *
 * Codex's plus is the reference and its labelling is the point: it names what
 * it attaches, in words, so the glyph never has to carry the meaning alone. So
 * the plus now opens a small labelled panel that DOES the thing — one path
 * field, one optional line about what it is for, and `attach_context` behind
 * the button. The panel also reads back what the engine MEASURED the path to
 * be — a folder, a git repository, a file — rather than what the user called
 * it, because `describe_path` looks and the difference is worth showing.
 *
 * Nothing in the panel is a promise a browser cannot keep. There is no drag and
 * drop, and the file picker APPEARS ONLY WHERE IT CAN WORK: both drag-drop and
 * `<input type=file>` hand back a `File` object, and every data tool in this
 * product takes a PATH on this machine, which a web page is not allowed to
 * learn. Saying "type or paste the path" is the honest version of that.
 *
 * Under the native shell it IS knowable - `pick_path` is one of the two Rust
 * commands THE_PLAN Phase B names - so the button renders when
 * `hasNativeShell()` and not otherwise. **A control that is absent is better
 * than one that is present and apologises**, and the hint under the field
 * changes with it, so the sentence a person reads is true of the build they
 * are in rather than of the one it was written for.
 *
 * WHAT THE REFERENCE HAS THAT THIS STILL DOES NOT, and why:
 *   · The mic and terminal glyphs — nothing is behind either.
 *   · Local / Worktree / Cloud and the branch indicator — every run is local
 *     and there is no worktree concept in the engine yet.
 * Each of those comes back when the thing behind it exists.
 *
 * CS15 — `/goal`, `/plan`, `/doc` are bound slash commands. They never change
 * mode or permission.
 *
 * THE BANNER SITS ABOVE THE COMPOSER, where Graphite puts it: "Blocked state
 * is an amber strip ABOVE the composer naming exactly what is missing and
 * offering to make it. It is a finding, not an error — the composer stays
 * fully usable underneath."
 */

import { createContext, useCallback, useEffect, useRef, useState, type ReactNode, useMemo} from 'react';
import { engineFetch, listThreadContexts, type ThreadContext } from '../lib/engine/client';
import type { Provider } from '../lib/engine/types';
import { hasNativeShell, nativePickPath } from '../lib/engine/shell';
import type { TurnState } from '../lib/useChat';
import { Icon } from './Icon';
import type { IconName } from './Icon';
import { Button, Strip } from './primitives';
import { MenuButton, type MenuRow } from './Menu';
import { ModeSwitch } from './ModeSwitch';
import { ContextRing } from './ContextRing';
import type { PermissionMode } from './PermissionLadder';
import { lastAssistantText } from '../lib/transcript';
import './connect.css';

/** The same signature `App.tsx` already passes to the transcript's controls:
 *  one tool, through THE USER'S DOOR, with the thread the facts belong to. */
export type RunToolFromComposer = (
  name: string,
  args: Record<string, unknown>,
  threadId: number | null,
) => Promise<{ ok: boolean; result: unknown; error: string | null }>;

/** Lets the suggestion cards put the caret where their text just went.
 *
 *  A card fills the composer and nothing else. Measured on the walk: the card
 *  sits about a hundred pixels above the box it writes into, focus stays on
 *  the button, and a stranger who clicks one sees no response at the place
 *  they clicked. The commonest next move is to click it again. Nothing is
 *  broken - the text is there - which is the worst kind of stuck, because the
 *  product looks like it ignored them.
 *
 *  A context rather than a ref threaded up through App: the cards are already
 *  rendered inside this component's own subtree, so the shortest honest path
 *  from the click to the textarea is straight down. Defaults to a no-op, so
 *  suggestion cards rendered anywhere else still work and simply do not move
 *  focus.
 */
export const FocusTheComposer = createContext<() => void>(() => {});

export function Composer({
  workspace,
  onAssignFolder,
  value,
  onChange,
  onSend,
  onStop,
  onConnect,
  mode,
  engineWorking,
  permission,
  plan,
  items,
  onThreadChanged,
  onControls,
  runTool,
  threadId,
  provider,
  providers,
  onUseProvider,
  presetNames,
  onSetEffort,
  providersLoading,
  turn,
  error,
  goal,
  suggestions,
  queued,
  onUnqueue,
  lastEventId = 0,
  onOpenContext,
  onSlashGoal,
  onSlashPlan,
  onSlashDoc,
}: {
  workspace: { id: number; name: string; root: string | null } | null;
  /** Attach a folder to a project that has none — the amber chip's exit. */
  onAssignFolder: (projectId: number) => void;
  value: string;
  onChange: (next: string) => void;
  onSend: () => void;
  /** Ends the turn in flight. Shown only while one is running. */
  onStop?: () => void;
  /** THE CONVERSATION'S OWN CONTROLS, under the box that talks to it.
   *  Plan/Build and the permission ladder are per-thread; they belong
   *  here, not in the frame. */
  mode: string;
  permission: PermissionMode;
  plan: string | null;
  items: { kind: string; result?: unknown }[];
  onThreadChanged: () => void;
  onConnect: () => void;
  onControls: () => void;
  /** Runs `attach_context` and `list_context` behind the plus. */
  runTool: RunToolFromComposer;
  /** Which conversation a fact belongs to. Sent with every run. */
  threadId: number | null;
  provider: Provider | null;
  /** EVERY CONNECTED MODEL, so the chip is a switch. Max, 2026-09-12:
   *  "condense the model picker so that it's easy for people to switch
   *  models... adding models and so on should just sit separately inside of
   *  the settings." The chip lists what is connected and activates one;
   *  its last row opens Settings, where connecting and removing live. */
  providers: Provider[];
  onUseProvider: (id: number) => Promise<void>;
  /** The preset names ("Ollama", "OpenAI"...). A row still carrying one as
   *  its name was never nicknamed, so the chip shows the model id for it;
   *  a row the person renamed shows the name they gave. Max, 2026-09-12:
   *  "this nickname should be reflected in the actual harness chat box." */
  presetNames: string[];
  /** Writes `effort` on the connection - the chip beside the model. */
  onSetEffort: (id: number, effort: string) => Promise<unknown>;
  providersLoading: boolean;
  turn: TurnState;
  /** The engine is mid-turn, whoever started it. Draws the Stop control. */
  engineWorking?: boolean;
  error: string | null;
  /** The suggestion cards, on an empty thread. Graphite puts them above the
   *  composer and outside it, so the dock owns the slot rather than the
   *  transcript — which is also why they survive when the transcript is
   *  scrolled. */
  /** The goal card, composed by the shell (components/GoalBar.tsx). Max,
   *  2026-09-13: "a pop up hovering above the chatbox like goal mode in
   *  cursor or codex". It sits in the dock rather than in the transcript so
   *  it stays put while the conversation scrolls under it. */
  goal?: ReactNode;
  suggestions?: ReactNode;
  /** Prompts typed while a turn was running, oldest first. */
  queued?: readonly string[];
  onUnqueue?: (index: number) => void;
  /** Advances when the event log grows — refreshes the usage strip. */
  lastEventId?: number;
  /** Opens the Context inspector pane. */
  onOpenContext?: () => void;
  /** CS15 — slash commands; never change mode/permission. */
  onSlashGoal?: () => void;
  onSlashPlan?: () => void;
  onSlashDoc?: () => void;
}) {
  const [focused, setFocused] = useState(false);
  const [attaching, setAttaching] = useState(false);
  const [modelMenu, setModelMenu] = useState(false);
  const [effortMenu, setEffortMenu] = useState(false);
  const [slashActive, setSlashActive] = useState(0);

  const slash = slashMatch(value);
  const slashRows = slash
    ? SLASH_COMMANDS.filter((row) => row.id.startsWith(slash.query))
    : [];

  function applySlash(id: string) {
    if (!slash) return;
    onChange(value.slice(0, slash.start).replace(/\s+$/, ''));
    setSlashActive(0);
    if (id === 'goal') onSlashGoal?.();
    else if (id === 'plan') onSlashPlan?.();
    else if (id === 'doc') onSlashDoc?.();
  }

  /* WHAT IS ATTACHED, on the line under the box. Read through
     `GET /api/threads/{id}/contexts` rather than `list_context` through the
     user door, because that door files a transcript row per call and a row
     on every thread open is the spam the owner keeps naming. Re-read when
     the thread changes and when the attach panel closes, which is the one
     moment the list can have grown. */
  const [contexts, setContexts] = useState<ThreadContext[]>([]);

  /* THE WORKSPACE IS NOT ALSO A FILE ATTACHED TO ITSELF.
   *
   * `attach_context` on the project's own folder is the normal first move -
   * the route's step 1 is literally "Record where the material lives with
   * `attach_context` - path = their folder" - so the root ends up in
   * `contexts` as well, and this line drew the same path twice: once as the
   * workspace, once as an attachment. Max, 2026-09-21: "the file workspace be
   * pointed out twice, kind of repetitive which isn't exactly helpful or
   * useful."
   *
   * Compared case-insensitively with separators normalised, because the
   * workspace root is stored as the person typed it and a tool resolves the
   * same folder through `workspace_resolved`; two spellings of one folder is
   * still one folder. */
  const alsoAttached = useMemo(() => {
    const root = workspace?.root;
    if (!root) return contexts;
    /* Separators and case only. `String.fromCharCode(92)` rather than a
       literal backslash: this file is written by tooling often enough that
       an escaped one has been eaten before. */
    const BACKSLASH = String.fromCharCode(92);
    const flat = (path: string) => {
      const slashed = path.split(BACKSLASH).join('/').toLowerCase();
      return slashed.endsWith('/') ? slashed.slice(0, -1) : slashed;
    };
    const here = flat(root);
    const same = (path: string) => flat(path) === here;
    return contexts.filter((one) => !same(one.path));
  }, [contexts, workspace?.root]);
  useEffect(() => {
    if (threadId === null || attaching) {
      if (threadId === null) setContexts([]);
      return;
    }
    let live = true;
    listThreadContexts(threadId)
      .then((out) => {
        if (live) setContexts(out.contexts ?? []);
      })
      .catch(() => {
        /* The line says nothing about files rather than something wrong. */
      });
    return () => {
      live = false;
    };
  }, [threadId, attaching]);
  const textarea = useRef<HTMLTextAreaElement>(null);

  /* "auto-grows to max 200px then scrolls". Height is set directly rather than
     transitioned — animating height is forbidden. */
  useEffect(() => {
    const el = textarea.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  /* Caret to the end, so a card that appends reads as "your turn to edit"
     rather than "your text was selected". */
  const focusComposer = useCallback(() => {
    const el = textarea.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);

  /* THE ENGINE'S ANSWER, NOT THIS PAGE'S. `turn` only knows about a fetch
     this browser issued; a run's turns never touch it. See `useChat`'s
     `engineWorking`. */
  const busy = turn !== 'idle' || Boolean(engineWorking);
  /* SOMETHING TO SEND IS SOMETHING TO SEND, BUSY OR NOT. Max, 2026-09-14:
     "also add a queueing prompt feature." The composer used to grey out for
     the whole of a turn, which against a local 7B is tens of seconds and
     sometimes minutes - so a thought you had while reading the reply waited in
     your head. It goes in the queue instead and is sent, as your own message
     and in the order you typed it, the moment the thread is free. */
  const canSend = value.trim().length > 0;
  const willQueue = canSend && busy;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (canSend) onSend();
  };


  return (
    <div className="composer-dock">
      <div className="composer-dock__inner">
        <FocusTheComposer.Provider value={focusComposer}>{suggestions}</FocusTheComposer.Provider>

        {/* WHAT IS WAITING, above the pair, where the banners go. Each is the
            person's own words and each can be taken back out - a queue you
            cannot edit is a queue that sends the thing you changed your mind
            about. */}
        {queued && queued.length ? (
          <ul className="queued" aria-label="Waiting to send">
            {queued.map((text, index) => (
              <li className="queued__row" key={`${index}-${text.slice(0, 24)}`}>
                <Icon name="clock" size={11} />
                <span className="queued__text" title={text}>
                  {text}
                </span>
                <button
                  type="button"
                  className="queued__drop"
                  aria-label={`Take back "${text.slice(0, 40)}"`}
                  title="Take this back out of the queue"
                  onClick={() => onUnqueue?.(index)}
                >
                  <Icon name="x" size={10} />
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        <ConnectionBanner
          provider={provider}
          loading={providersLoading}
          onConnect={onConnect}
          onControls={onControls}
        />

        {error ? (
          <div style={{ marginBottom: 'var(--sp-6)' }}>
            <Strip tone="wont" icon="alert">
              <span className="mono">{error}</span>
            </Strip>
          </div>
        ) : null}

        {/* THE GOAL CARD SITS ON THE CHAT BOX, so it must be the last thing
            before it. Max, 2026-09-14: "a small extension from the chat, and
            connected from it... not hovering separately." It was above the
            connection banner, which put anything from 0 to 55px of other
            people's business between the card's bottom edge and the box's top
            one - MEASURED at 55 with a banner showing, and the card read as
            floating exactly as he said. Anything the harness needs to warn
            about now goes ABOVE the pair rather than between them. */}
        {goal}

        <form className="composer" data-focused={focused} onSubmit={submit}>
          <label className="sr-only" htmlFor="composer-input">
            Describe what you want to build
          </label>
          <div className="composer__slashwrap">
            {slash && slashRows.length > 0 ? (
              <div className="composer__slash" role="listbox" aria-label="Commands">
                {slashRows.map((row, index) => (
                  <button
                    key={row.id}
                    type="button"
                    className="composer__slashrow"
                    role="option"
                    aria-selected={index === slashActive}
                    data-active={index === slashActive || undefined}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      applySlash(row.id);
                    }}
                  >
                    <Icon name={row.icon} size={12} />
                    <span className="composer__slashcmd mono">/{row.id}</span>
                    <span className="composer__slashhint">{row.hint}</span>
                  </button>
                ))}
              </div>
            ) : null}
            <textarea
              id="composer-input"
              ref={textarea}
              className="composer__input"
              rows={1}
              placeholder={
                busy
                  ? 'Ask the harness anything - it queues, or press stop to end this turn'
                  : 'Ask the harness anything — / for commands'
              }
              value={value}
              onChange={(event) => {
                onChange(event.target.value);
                setSlashActive(0);
              }}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              onKeyDown={(event) => {
                if (slash && slashRows.length > 0) {
                  if (event.key === 'ArrowDown') {
                    event.preventDefault();
                    setSlashActive((n) => (n + 1) % slashRows.length);
                    return;
                  }
                  if (event.key === 'ArrowUp') {
                    event.preventDefault();
                    setSlashActive(
                      (n) => (n - 1 + slashRows.length) % slashRows.length,
                    );
                    return;
                  }
                  if (event.key === 'Escape') {
                    event.preventDefault();
                    onChange(value.slice(0, slash.start));
                    return;
                  }
                  if (
                    event.key === 'Enter' &&
                    !event.shiftKey &&
                    !event.nativeEvent.isComposing
                  ) {
                    event.preventDefault();
                    applySlash(slashRows[slashActive]?.id ?? slashRows[0].id);
                    return;
                  }
                  if (event.key === 'Tab') {
                    event.preventDefault();
                    applySlash(slashRows[slashActive]?.id ?? slashRows[0].id);
                    return;
                  }
                }
                /* Enter sends, Shift+Enter is a newline. */
                if (
                  event.key === 'Enter' &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing
                ) {
                  event.preventDefault();
                  if (canSend) onSend();
                }
              }}
            />
          </div>

          {/* ONE ROW, NOTHING STACKED. Max, 2026-09-12: "put plan or build
              mode and autonomous and ask mode in the file and path's place;
              this way it doesn't stack over itself." The plus, the two mode
              dropdowns, the model switch, then the actions. The folder path
              and the attached file moved out of the box to the line under it
              (`composer__where`). Nothing mode-shaped before a thread exists. */}
          <div className="composer__row">
            {/* THE PLUS IS THE ATTACH AFFORDANCE AND NOW SAYS SO. The panel it
                opens is anchored to it, which is why the button carries the
                positioning context rather than the row. */}
            <span className="cx-attachwrap">
              <button
                type="button"
                className="plusbtn"
                aria-label="Add context — a folder, file or repository"
                aria-expanded={attaching}
                title="Add context — a folder, file or repository on this machine"
                onClick={() => setAttaching((open) => !open)}
              >
                <Icon name="plus" size={14} />
              </button>
              {attaching ? (
                <AttachPanel
                  runTool={runTool}
                  threadId={threadId}
                  onClose={() => setAttaching(false)}
                />
              ) : null}
            </span>

            {threadId !== null ? (
              <ModeSwitch
                threadId={threadId}
                mode={mode}
                permission={permission}
                plan={plan}
                planDraft={lastAssistantText(items as never)}
                onChanged={onThreadChanged}
              />
            ) : null}

            {/* THE MODEL IS A SWITCH. Every connected model as a row, the
                active one pressed; choosing another activates it through the
                same route Settings uses. Connecting or removing a model is
                the last row, which opens Settings. Mono for the name, because
                it is an identifier someone might copy. */}
            {providers.length === 0 ? (
              /* NOTHING TO SWITCH BETWEEN. A stranger's first click goes
                 straight to the connect dialog rather than to a one-row menu
                 that says the same thing. */
              <button
                type="button"
                className="modelsel"
                onClick={onConnect}
                title="Connect a model — one already on this machine, or an API key"
              >
                <Icon name="key" size={12} />
                <span className="modelsel__name">Connect a model</span>
                <Icon name="chevdown" size={12} style={{ color: 'var(--ink-3)' }} />
              </button>
            ) : (
              <MenuButton
                className="modelsel"
                label="Model"
                title="Which model the harness is thinking with. Click to switch."
                rows={modelRows(providers, presetNames, providersLoading)}
                open={modelMenu}
                setOpen={setModelMenu}
                minWidth={220}
                onChoose={(id) => {
                  if (id === 'manage') {
                    onConnect();
                    return;
                  }
                  const picked = Number(id);
                  if (Number.isFinite(picked) && picked !== provider?.id) void onUseProvider(picked);
                }}
              >
                <Icon name={provider ? 'model' : 'key'} size={12} />
                <span className="modelsel__name">
                  {provider ? labelFor(provider, presetNames) : 'Connect a model'}
                </span>
                <Icon name="chevdown" size={12} style={{ color: 'var(--ink-3)' }} />
              </MenuButton>
            )}

            {/* HOW HARD IT THINKS. Max, 2026-09-12: "I'm not seeing an effort
                system for our models." One word beside the model, a menu of
                five; the engine stores it on the connection and each adapter
                sends its own field for it (or nothing, for `default`). */}
            {provider ? (
              <MenuButton
                className="modelsel modelsel--effort"
                label="Effort"
                title={
                  'How hard the model thinks on this connection. Default sends nothing; ' +
                  'off turns a thinking model\u2019s reasoning off; low, medium and high ask ' +
                  'for that much. A model that cannot think is not asked to.'
                }
                rows={EFFORTS.map((each) => ({
                  id: each.id,
                  label: each.label,
                  current: (provider.effort || 'default') === each.id,
                }))}
                open={effortMenu}
                setOpen={setEffortMenu}
                minWidth={168}
                onChoose={(id) => {
                  if (id !== (provider.effort || 'default')) void onSetEffort(provider.id, id);
                }}
              >
                <Icon name="sliders" size={12} />
                <span className="modelsel__name" style={{ fontFamily: 'inherit' }}>
                  {effortWord(provider.effort)}
                </span>
                <Icon name="chevdown" size={12} style={{ color: 'var(--ink-3)' }} />
              </MenuButton>
            ) : null}

            <span className="composer__actions">
              {threadId !== null && onOpenContext ? (
                <ContextRing
                  threadId={threadId}
                  tick={lastEventId}
                  onOpen={onOpenContext}
                />
              ) : null}
              <button
                type="button"
                className="iconbtn"
                onClick={onControls}
                aria-label="Tools"
                title="Every tool the harness has, as buttons"
              >
                <Icon name="skill" />
              </button>

              {/* 28 x 28, --r-full, --accent-solid. The one saturated object on
                  the screen, and the only place the accent appears at full
                  strength. Disabled is --surface-3 with an --ink-4 glyph —
                  never a dimmed accent. */}
{/* THE STOP BUTTON DRAWS A STOP AND STOPS. It drew one before and did
                  nothing - `type="submit"`, `disabled` with an empty box, a
                  square glyph that was decoration. Max, 2026-09-19: "stopping
                  a prompt, stopping a plan, mid-prompt, mid-workway". Its own
                  button now, beside send rather than instead of it, so a
                  queued message and a stop are two decisions and not one. */}
              {busy && onStop ? (
                <button
                  type="button"
                  className="sendbtn sendbtn--stop"
                  onClick={onStop}
                  aria-label="Stop this turn"
                  title="Stop after the step it is on. A tool already running finishes and is recorded."
                >
                  <Icon name="stop" />
                </button>
              ) : null}
              <button
                type="submit"
                className="sendbtn"
                disabled={!canSend}
                aria-label={willQueue ? 'Queue' : 'Send'}
                data-queue={willQueue || undefined}
                title={
                  willQueue
                    ? 'The engine is mid-turn - this goes in the queue and sends itself when the turn ends'
                    : 'Send'
                }
              >
                <Icon name={willQueue ? 'clock' : 'send'} />
              </button>
            </span>
          </div>
        </form>

        {/* THE LINE UNDER THE BOX: where the next message lands. Max chose
            this over a line above ("put the composer path placement under the
            chatbox"). The folder path, ellipsized at the drive end because the
            readable half of a path is its tail; the attached files by name;
            and on the right the build loop's state. When the project has no
            folder the line turns amber and says so - absence is a state, and
            a state does not live in a tooltip. */}
        {/* Path only under the box — no tokens / calls / MEASURED strip. */}
        {workspace || threadId !== null ? (
          <div className="composer__where">
            {workspace ? (
              workspace.root ? (
                <span
                  className="where__path"
                  title={`${workspace.name} — this thread reads and writes in ${workspace.root}`}
                >
                  <Icon name="folder" size={12} />
                  <span className="where__pathtext mono">
                    {LRM}{workspace.root}{LRM}
                  </span>
                </span>
              ) : (
                <button
                  type="button"
                  className="where__path where__path--amber"
                  onClick={() => onAssignFolder(workspace.id)}
                  title={`"${workspace.name}" has no folder on disk yet, so nothing ties its work to a path you chose. Click to attach one.`}
                >
                  <Icon name="folder" size={12} />
                  <span>{workspace.name} — no folder attached</span>
                </button>
              )
            ) : null}
            {alsoAttached.length > 0 ? (
              <button
                type="button"
                className="where__files"
                onClick={() => setAttaching(true)}
                title={alsoAttached.map((c) => c.path).join(LINE)}
              >
                <Icon name="file" size={12} />
                <span className="mono">{fileNames(alsoAttached)}</span>
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** The bidi marks around the rtl-ellipsized path keep its edge punctuation
 *  from flipping; a newline for the files tooltip. Both as code points, so no
 *  editor or transport can eat a backslash. */
const LRM = String.fromCharCode(0x200e);
const LINE = String.fromCharCode(10);
const BACKSLASH = String.fromCharCode(92);

/** CS15 — composer slash commands. Never flip mode/permission. */
const SLASH_COMMANDS: { id: string; hint: string; icon: IconName }[] = [
  { id: 'goal', hint: 'Show the goal bar; invite goal tools one turn', icon: 'star' },
  { id: 'plan', hint: 'Open the Plan tab (mode stays put)', icon: 'skill' },
  { id: 'doc', hint: 'Open plans / Doc list', icon: 'file' },
];

function slashMatch(
  value: string,
): { start: number; query: string } | null {
  const found = /(^|\s)\/([a-z]*)$/i.exec(value);
  if (!found) return null;
  return {
    start: found.index + found[1].length,
    query: found[2].toLowerCase(),
  };
}

/** The five efforts, in the order a person thinks of them. */
const EFFORTS: { id: string; label: string }[] = [
  { id: 'default', label: 'Default - the server decides' },
  { id: 'off', label: 'Off - no reasoning' },
  { id: 'low', label: 'Low' },
  { id: 'medium', label: 'Medium' },
  { id: 'high', label: 'High' },
];

function effortWord(effort: string | undefined): string {
  const id = effort || 'default';
  return id === 'default' ? 'Effort' : id[0].toUpperCase() + id.slice(1);
}

/** The nickname when the person gave one; the model id otherwise. A name
 *  equal to a preset ("Ollama") or to the model id itself is not a nickname. */
function labelFor(p: Provider, presetNames: string[]): string {
  const name = (p.name || '').trim();
  if (!name || name === p.model || presetNames.includes(name)) return p.model;
  return name;
}

/** The model menu's rows: every connected model, the active one pressed, then
 *  the door to Settings. Each by its nickname, or its id when it has none. */
function modelRows(providers: Provider[], presetNames: string[], loading: boolean): MenuRow[] {
  const rows: MenuRow[] = providers.map((p) => ({
    id: String(p.id),
    label: labelFor(p, presetNames),
    icon: p.kind === 'local' ? 'model' : 'key',
    current: p.is_active === 1,
  }));
  rows.push({
    id: 'manage',
    label: providers.length === 0 ? 'Connect a model…' : 'Manage models…',
    icon: 'gear',
    disabledReason: loading ? 'Reading the connections…' : undefined,
  });
  return rows;
}

/** "tickets.jsonl", "tickets.jsonl, notes.md", "tickets.jsonl +2". */
function fileNames(contexts: ThreadContext[]): string {
  const names = contexts.map((c) => {
    const tail = c.path.split('/').filter(Boolean).pop() ?? c.path;
    return tail.split(BACKSLASH).filter(Boolean).pop() ?? tail;
  });
  if (names.length <= 2) return names.join(', ');
  return `${names[0]} +${names.length - 1}`;
}

/* ── The attach panel ────────────────────────────────────────────────────
   One tool, one field, and the engine's own reading of what it found.

   `attach_context` is idempotent — `record_context` updates the row when the
   path is already there and reports `already_attached` — so pressing this
   twice is not a way to make a duplicate. That is worth relying on rather than
   guarding against here, because a second guard could disagree with the first.

   THE RESULT IS QUOTED, NOT PARAPHRASED. The tool measures what the path is
   with `describe_path` (a folder, a git repository, a file) and states what it
   stored: "the path only; no file was copied and no directory was read". Both
   sentences come back on the response and both are printed as given. */

interface AttachResult {
  ok?: boolean;
  error?: string;
  detail?: string;
  attached?: { id?: number; path?: string; kind?: string; role?: string };
  already_attached?: boolean;
  what_it_is?: { path?: string; kind?: string; entries_at_top_level?: number };
  stored?: string;
}

interface ContextList {
  count?: number;
  contexts?: { id: number; path: string; kind: string; role: string }[];
  source?: string;
}

function AttachPanel({
  runTool,
  threadId,
  onClose,
}: {
  runTool: RunToolFromComposer;
  threadId: number | null;
  onClose: () => void;
}) {
  const [path, setPath] = useState('');
  const [role, setRole] = useState('');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<AttachResult | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [listing, setListing] = useState<ContextList | null>(null);
  const panel = useRef<HTMLDivElement>(null);

  /* Escape closes, and so does a click anywhere else. A popover that can only
     be dismissed by pressing the control that opened it is a popover people
     click around. */
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    const onDown = (event: MouseEvent) => {
      const el = panel.current;
      if (el && !el.contains(event.target as Node)) onClose();
    };
    window.addEventListener('keydown', onKey);
    /* Capture, so this runs before the plus button's own toggle and the two
       cannot cancel each other out into a no-op. */
    window.addEventListener('mousedown', onDown, true);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onDown, true);
    };
  }, [onClose]);

  /* WHAT IS ATTACHED, WITHOUT BEING ASKED. The owner attached a file and then
     could not tell whether it took: "I can't see when it's added. I can't see
     if it's still added... How could I check?" The answer used to be a button.
     Now the list is fetched the moment the popover opens and refreshed after
     every attach, so the popover IS the check. */
  const refresh = async () => {
    /* thread_id deliberately null: this is the popover refreshing itself on
       open, not a person acting, and the user door writes a transcript row
       for every run filed under a thread. A listing row on every popover
       open would be the spam the owner keeps naming. The ATTACH below still
       files under the thread, because attaching is a person acting. */
    /* THE LISTING IS SCOPED TO THIS THREAD NOW. It passed `null` so that
       reading would not file a row under the thread - see above - but the
       engine reads `thread_id` off the call to SCOPE the listing as well,
       and v017 gave attachments a thread to scope on. A person opening the
       plus wants this chat's files, not every file ever attached anywhere;
       the owner named that as the bug on 2026-09-11. */
    const outcome = await runTool('list_context', {}, threadId);
    if (!outcome.error) setListing(outcome.result as ContextList);
  };
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const attach = async () => {
    if (!path.trim() || running) return;
    setRunning(true);
    setFailure(null);
    const outcome = await runTool(
      'attach_context',
      { path: path.trim(), ...(role.trim() ? { role: role.trim() } : {}) },
      threadId,
    );
    setRunning(false);
    if (outcome.error) {
      setFailure(outcome.error);
      return;
    }
    setResult(outcome.result as AttachResult);
    void refresh();
  };

  return (
    <div
      className="cx-attach"
      ref={panel}
      role="dialog"
      aria-label="Add context"
      onMouseDown={(event) => event.stopPropagation()}
    >
      <div className="cx-attach__head">
        <Icon name="folder" size={12} />
        Add context
      </div>

      <div className="cx-attach__form">
        <p className="cx-attach__what" style={{ marginBottom: 'var(--sp-8)' }}>
          A folder, a file or a git repository on this machine. The harness
          records the path and reads from where the data already lives — nothing
          is uploaded and nothing is copied.
        </p>

        {/* The placeholder is a JSX attribute, not a JS string literal, so a
            `\\` in it renders as TWO backslashes on screen. It did, and it was
            caught in a screenshot rather than by any assertion — the fourth
            defect in this repository that was only ever going to be found by
            looking at a picture. */}
        <label className="field">
          <span className="field__label">Path on this machine</span>
          <div className="field--inline">
            <input
              className="input mono"
              value={path}
              spellCheck={false}
              autoComplete="off"
              placeholder="C:\Users\… or /Users/…"
              onChange={(event) => setPath(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  void attach();
                }
              }}
            />
            {/* RENDERED ONLY WHERE IT CAN WORK. In a browser there is no way
                to learn a real path, so this button would open a dialog whose
                answer had to be thrown away - a control that lies about what
                it does. Under the shell `pick_path` returns a real path and
                the field fills in. Cancelling and "no shell" are the same
                answer on purpose: leave the field alone and let them type. */}
            {hasNativeShell() ? (
              <button
                type="button"
                className="btn"
                onClick={() => {
                  void nativePickPath('directory').then((picked) => {
                    if (picked) setPath(picked);
                  });
                }}
              >
                Browse…
              </button>
            ) : null}
          </div>
          {/* Not a limitation we chose. A browser is never told the path of a
              file it is handed, and every data tool here takes one - so the
              sentence changes with the build rather than describing the one
              it was written in. */}
          <span className="field__hint">
            {hasNativeShell()
              ? 'Type it, paste it, or browse for it.'
              : 'Typed or pasted — a browser is never told the real path of a ' +
                'dropped file, and every data tool here works by path.'}
          </span>
        </label>

        <label className="field">
          <span className="field__label">What it is for (optional)</span>
          <input
            className="input"
            value={role}
            placeholder="training data, the app we want to improve…"
            onChange={(event) => setRole(event.target.value)}
          />
        </label>

        <div className="dialog__actions">
          <Button
            kind="primary"
            small
            onClick={() => void attach()}
            disabled={!path.trim() || running}
          >
            Attach
          </Button>
        </div>

        {failure ? (
          <div style={{ marginTop: 'var(--sp-8)' }}>
            <Strip tone="wont" icon="alert">
              <span className="mono">{failure}</span>
            </Strip>
          </div>
        ) : null}

        {result ? (
          <div style={{ marginTop: 'var(--sp-8)' }}>
            {result.ok === false ? (
              <Strip tone="wont" icon="alert">
                {result.detail ?? result.error ?? 'It could not be attached.'}
              </Strip>
            ) : (
              <Strip tone="fits" icon="check">
                {result.already_attached ? 'Already attached' : 'Attached'} —{' '}
                <span className="mono">{result.what_it_is?.path ?? path}</span>,
                which the engine read as a{' '}
                <strong>{result.what_it_is?.kind ?? 'path'}</strong>.{' '}
                {result.stored ? `It stored ${result.stored}.` : null}
              </Strip>
            )}
          </div>
        ) : null}

        {listing ? (
          <div style={{ marginTop: 'var(--sp-8)' }}>
            <p className="cx-attach__what" style={{ fontWeight: 600 }}>
              Attached now
            </p>
            {(listing.contexts?.length ?? 0) === 0 ? (
              <p className="cx-attach__what">
                Nothing is attached on this machine yet.
              </p>
            ) : (
              listing.contexts?.map((entry) => (
                <p className="cx-attach__what" key={entry.id}>
                  <span className="mono">{entry.path}</span>
                  {entry.kind ? ` · ${entry.kind}` : ''}
                  {entry.role ? ` · ${entry.role}` : ''}
                </p>
              ))
            )}
            {/* Where the list came from, in the tool's own words. */}
            {listing.source ? (
              <p className="cx-attach__what">{listing.source}</p>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * The blocked strip, told the truth four ways.
 *
 * The middle two are the interesting ones. A model that is connected but
 * cannot call tools is not a broken product — `app/conductor.py` runs a fixed
 * script itself and hands the results over as data, and every tool is still a
 * button. Saying that plainly, once, is what the Conductor's own notice does,
 * and this strip is its counterpart before the first message.
 */
function ConnectionBanner({
  provider,
  loading,
  onConnect,
  onControls,
}: {
  provider: Provider | null;
  loading: boolean;
  onConnect: () => void;
  onControls: () => void;
}) {
  if (loading) {
    return (
      <div style={{ marginBottom: 'var(--sp-6)' }}>
        <Strip tone="info" icon="clock">
          Checking what this machine is connected to…
        </Strip>
      </div>
    );
  }

  if (!provider) {
    return (
      <div style={{ marginBottom: 'var(--sp-6)' }}>
        <Strip tone="spills" icon="alert">
          No model connected — the harness thinks with a model you lend it.{' '}
          <button type="button" className="strip__action" onClick={onConnect}>
            Pick one on this machine, or connect an API key
          </button>
        </Strip>
      </div>
    );
  }

  if (provider.tool_calling === 'no') {
    /* A WARNING, not a footnote — the owner's correction. A model that cannot
       call tools means the chat cannot drive the harness, which is the single
       most confusing state a new person can land in. Amber, an alert glyph,
       and both ways out in one line. */
    return (
      <div style={{ marginBottom: 'var(--sp-6)' }}>
        <Strip tone="spills" icon="alert">
          <span className="mono">{provider.model}</span> can&rsquo;t call tools —
          chat can describe work but not do it.{' '}
          <button type="button" className="strip__action" onClick={onConnect}>
            Connect a tool-calling model
          </button>{' '}
          or{' '}
          <button type="button" className="strip__action" onClick={onControls}>
            click the tools yourself
          </button>
        </Strip>
      </div>
    );
  }

  if (provider.tool_calling === 'unknown') {
    /* Self-resolving now: the engine probes an unknown connection at the
       start of the next turn, so this strip mostly means "send anything and
       the answer arrives". The button remains for the impatient. */
    return (
      <div style={{ marginBottom: 'var(--sp-6)' }}>
        <Strip tone="info" icon="info">
          <span className="mono">{provider.model}</span> is connected; your
          first message will also ask it whether it can call tools.{' '}
          {/* The owner clicked this and it "just took you to the connect
              model thing" - because it did. Now it ASKS: one POST to the
              probe route, and the strip resolves itself. */}
          <button
            type="button"
            className="strip__action"
            onClick={() => {
              void engineFetch(`/api/providers/${provider.id}/probe`, {
                method: 'POST',
              }).then(() => window.location.reload());
            }}
          >
            Ask now
          </button>
        </Strip>
      </div>
    );
  }

  /* THE FOURTH STATE IS GONE FROM THIS SURFACE. Max, 2026-09-14: *"remove the
     failed or live AI status symbol as well please."*

     It reported a real and well-measured thing - a model whose daemon says it
     can call tools and then writes a confident numbered plan naming them in
     prose and calls none, measured on a 0.5B by ML BUILD on 2026-09-10. What
     it is NOT is a thing to hang over the chat box every turn. The three
     states above are about a connection a person has to fix before anything
     works at all, and a stranger needs them; this one is about the QUALITY of
     an answer that already arrived, which the transcript itself shows better
     than a strip can - the turn is right there, with its tool rows or without
     them.

     THE WHOLE SIGNAL WENT, not just its glyph. The first draft of this left
     `saidNothing` computed and threaded through on the theory that something
     else read it; grepping for a reader found none - the banner was its only
     consumer. A signal wired to nothing is dead code wearing a comment that
     lies about it, so `saidYesAndCalledNothing` and its own tests are the only
     things left, kept because the READING is sound and cheap to re-hang if a
     surface ever wants it. */

  /* Connected, probed, it can call tools, and it has been using them. Nothing
     to say. */
  return null;
}
