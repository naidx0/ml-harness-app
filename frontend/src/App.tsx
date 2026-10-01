/**
 * The shell — three zones, one workspace. PRODUCT_SPEC §2.
 *
 * It is a working chat surface now rather than a shell. What that took, in
 * one place, because the order is the whole design:
 *
 *   the composer sends      → POST /api/threads/{id}/messages
 *   the engine runs a turn  → POST /api/threads/{id}/turn   (blocks, returns ids)
 *   the reply arrives       → GET  /api/events?scope=thread:{id}
 *
 * The reply does not come back on the turn's response. Every token is
 * committed to the event log before it is streamed (`app/events.py`), so the
 * transcript is a fold over durable rows and a dropped connection costs
 * exactly nothing. `lib/useChat.ts` holds that loop; this file holds the
 * layout around it.
 */

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { WindowControls } from './components/WindowControls';
import { Stage } from './components/Stage';
import { IconButton } from './components/primitives';
import { useStage } from './lib/useStage';
import { initialStage, stageReducer, stageShows } from './lib/stageState';
import { nextStageMove } from './lib/stageTransition';
import { allReadsOf, latestReadOf } from './lib/transcriptReads';
import { readRecallReport } from './lib/engine/retrieval';
import { readCarve } from './lib/engine/datawork';
import { nativeCloseStage, nativeOpenStage } from './lib/engine/shell';
import { Rail } from './components/Rail';
import { Transcript, type Density } from './components/Transcript';
import { Suggestions } from './components/EmptyState';
import { StartSheet, type StartSheetPrefs } from './components/StartSheet';
import { AgentsPane } from './components/AgentsPane';
import { Composer } from './components/Composer';
import { ConnectModel } from './components/ConnectModel';
import { Controls } from './components/Controls';
import { EngineNotice } from './components/EngineNotice';
import { GoalBar } from './components/GoalBar';
import { SubAgentBoard } from './components/SubAgentBoard';
import { Settings } from './components/Settings';
import { Icon } from './components/Icon';
import {
  Inspector,
  initialInspector,
  openInspectorTab,
  type InspectorState,
} from './components/Inspector';
import { wantsHalfWidth } from './lib/inspectorTabs';
import { snapTarget, snapTargets } from './lib/snapWidth';
import { useSnapDrag } from './lib/useSnapDrag';
import { ThemeToggle, useTheme } from './components/Chrome';
import { PlanPanel } from './components/PlanPanel';

/** CS17 — Doc / Plan from GoalBar: pop out a real Plan window first (Tauri or
 *  browser popup). Docked inspector L→R squeeze is the fallback only when the
 *  shell cannot open a separate pane — not the primary affordance. */
async function openPlanSurface(
  threadId: number | null,
  setInspector: (next: InspectorState | ((was: InspectorState) => InspectorState)) => void,
  _path?: string,
): Promise<void> {
  /* CS19 — Doc/Plan opens as an inspector chrome tab (column split). Pop-out
     remains on the Plan pane head for a movable OS window. */
  setInspector((was) => openInspectorTab(was, 'plan'));
  void threadId;
  void _path;
}
import { ContextPane } from './components/ContextPane';
import { JourneyPane } from './components/JourneyPane';
import { evalReportsIn, latestDiagnosis } from './lib/theThreadRead';
import { useDenials } from './lib/useApprovals';
import { useStorms } from './lib/useStorms';
import { useChat } from './lib/useChat';
import { useEvidence } from './lib/useEvidence';
import { useProviders } from './lib/useProviders';
import { useSubAgents } from './lib/useSubAgents';
import { useRun } from './lib/useRun';
import { useQueuedPrompts } from './lib/useQueuedPrompts';
import { useThreads } from './lib/useThreads';
import { useActivity } from './lib/useActivity';
import { useTools } from './lib/useTools';
import { useNextStep } from './lib/useNextStep';
import { toQuestion } from './lib/engine/asking';
import { spendingRows } from './lib/stageTransition';
import { showGoalBar } from './lib/goalBarVisibility';
import {
  duplicateProject,
  getThread,
  runTool as runToolRequest,
  setProjectRoot,
  setThreadMode,
  setThreadPermission,
  setThreadPlan,
  stopTurn,
} from './lib/engine/client';
import { hasNativeShell, nativePickPath } from './lib/engine/shell';
import './styles/tokens.css';
import './styles/base.css';
import './styles/shell.css';
import './styles/chat.css';
/* The engine notice. Before provenance/plan/evals because it styles chrome and
   nothing in it competes with a card rule at equal specificity. */
import './styles/engine.css';
import './styles/provenance.css';
import './styles/plan.css';
/* Last, because `.card--eval` and `.card--compare` raise the radius and the
   padding off the `.card` defaults `shell.css` sets, and at equal specificity
   the later rule wins. Same position and same reason as `plan.css` above. */
import './styles/evals.css';
/* After `evals.css` for the same reason it comes after `shell.css` —
   `.card--sweep` and `.card--recall` raise the same two properties — and
   because the retrieval cards reuse `.scale`, `.reso__row`, `.fig`, `.rows`
   and `.frow__*` from that sheet rather than restating them. A card that
   borrowed those shapes and then redefined them would be two components
   drifting apart under one name. */
import './styles/retrieval.css';
/* Last, and for `retrieval.css`'s reason: `.card--carve` raises the radius and
   the padding off the `.card` defaults `shell.css` sets, and the carve card
   reuses `.plansec__*`, `.runfacts__*`, `.fig` and `.vpill` from the sheets
   above rather than restating them. */
import './styles/datawork.css';

const RAIL_KEY = 'mlh.railWidth';
const PANE_KEY = 'mlh.paneWidth';
/** CS6 — person pinned an inspector subject; do not auto-focus Stage/Terminal. */
const INSPECTOR_PIN_KEY = 'mlh.inspectorPinned';
/** §9.21: density is "per thread and persisted, because it is a property of
 *  the conversation, not of the app". The shipped `threads` table has no
 *  `density` column, so it is persisted here, per thread id, and that gap is
 *  reported rather than papered over with an app-wide setting. */

export default function App() {
  const [theme, setTheme] = useTheme();
  /* No row-size state. COMPACT IS THE ONLY DENSITY THAT IS DESIGNED FOR
     (DESIGN_DIRECTIVES §2), so there is nothing to hold.

     NO PORTAL STATE EITHER. DESIGN_DIRECTIVES §3, superseded by Max on
     2026-08-19: "There is one product — consumer/enterprise is dropped… The
     scaffolding toggle in the shell should go." It has gone, and with it the
     `Scaffold` fence it sat behind, the `.scaffbar` strip under the app bar,
     the portal argument to the inspector's default, and the Settings section
     that explained a distinction this product no longer draws. A toggle that
     changes almost nothing is worse than no toggle. */

  const threads = useThreads();
  /* WHICH OTHER CONVERSATIONS ARE WORKING. Asked of the engine rather than
     tracked here, so a run taking turns in a thread nobody is reading still
     shows up in the rail. See lib/useActivity.ts. */
  const activity = useActivity(0);
  const providers = useProviders();
  const tools = useTools();

  /* CS7 — prefs for a thread that does not exist yet; applied on first create. */
  const [startPrefs, setStartPrefs] = useState<StartSheetPrefs>({
    /* PLAN, and the engine already agreed - `modes.WHEN_A_PERSON_OPENS_A
       _CONVERSATION` is 'plan' and `POST /api/threads` passes it. This default
       overrode it on the first create, which is why thread 81 carries two
       `thread.mode` rows and says "Switched to Build." twice for a message
       that said "hi". Max, 2026-09-19: "convos should also start on plan mode
       as a default". */
    mode: 'plan',
    permission: 'ask',
    projectId: null,
  });
  const startPrefsRef = useRef(startPrefs);
  startPrefsRef.current = startPrefs;

  const prepareNewThread = useCallback(async (threadId: number) => {
    const prefs = startPrefsRef.current;
    try {
      /* ONLY WHAT THE ENGINE DOES NOT ALREADY SAY. `POST /api/threads` passes
         `modes.WHEN_A_PERSON_OPENS_A_CONVERSATION`, so a new thread is
         ALREADY in plan when it gets here - and writing the mode anyway put a
         `thread.mode` row and a "Switched to Plan." line on the first frame of
         every conversation. Max, 2026-09-21, on a thread that said hello:
         "when loading a chat it's still defaults to build mode automatically
         which is kind of annoying". Two writes for one decision is also how
         the transcript ends up announcing a switch that never happened.

         The engine's own row is the truth, so it is read first and only a
         real difference is sent. */
      const already = (await getThread(threadId))?.thread;
      if (String(already?.mode ?? '') !== prefs.mode) {
        await setThreadMode(threadId, prefs.mode);
      }
      if (String(already?.permission ?? '') !== prefs.permission) {
        await setThreadPermission(threadId, prefs.permission);
      }
    } catch {
      /* Thread still exists; mode/permission stay at engine defaults. */
    }
    void threads.refresh();
  }, [threads]);

  const [inviteGoalEdit, setInviteGoalEdit] = useState(false);
  const chat = useChat(
    () => void threads.refresh(),
    inviteGoalEdit,
    prepareNewThread,
  );

  /* CS13 — invite is one turn: clear after a turn that ran finishes. */
  const wasRunning = useRef(false);
  useEffect(() => {
    if (chat.turn === 'running' || chat.turn === 'sending') {
      wasRunning.current = true;
      return;
    }
    if (chat.turn === 'idle' && wasRunning.current) {
      wasRunning.current = false;
      setInviteGoalEdit(false);
    }
  }, [chat.turn]);
  /* Read once here rather than inside both surfaces that draw it: the board in
     the transcript and the goal card's running state are one fact. */
  const subAgents = useSubAgents(chat.threadId, chat.lastEventId);
  const longRun = useRun(chat.threadId, chat.lastEventId);

  const evidence = useEvidence(chat.threadId);

  /* The last diagnosis in this thread, folded out of the durable event log
     rather than held in state. The transcript is the artifact: a verdict that
     survived a restart is a verdict the pane can still show, and one held in a
     React ref would not be. */
  const diagnosis = useMemo(() => latestDiagnosis(chat.items), [chat.items]);

  /* Every eval run this thread has read back, newest first, folded out of the
     same durable event log and for the same reason. The eval pane draws them;
     see `evalReportsIn` for why the fold de-duplicates. */
  const evals = useMemo(() => evalReportsIn(chat.items), [chat.items]);
  /* THE FOURTH STATE. The probe says the model CAN call tools; the thread says
     it has not. Only the turn can see that, so it is read here beside the
     other transcript readings and handed down - the banner prints the count it
     is given rather than recomputing one, because a second count is a second
     chance to print a number that is not the one that opened the banner. */

  /* ── THE QUESTION THE ENGINE WOULD ASK ──────────────────────────────────
     `GET /api/next_step` → `app/asking.py`. Held here rather than inside the
     transcript because the transcript is a renderer: it should not be the
     thing that decides when to spend a round trip, and the same card is going
     to be wanted by the inspector next.

     `turnKey` is a REASON, not a clock — see `useNextStep`. It moves when a
     turn ends, because that is when the model may have run a tool that
     measured something and moved the frontier. */
  /* Which control the Controls dialog should open on, set by the journey
     overview's "do this step". Cleared when the dialog closes, so opening it
     from the toolbar afterwards is about nothing in particular again. */
  const [controlsFocus, setControlsFocus] = useState<string | null>(null);
  const [controlsPrefill, setControlsPrefill] = useState<Record<
    string,
    { value: unknown; from: string }
  > | null>(null);
  const [turnKey, setTurnKey] = useState(0);
  useEffect(() => {
    if (!chat.streaming) setTurnKey((key) => key + 1);
  }, [chat.streaming]);
  /* A finished turn may have rewritten the plan (ticks, parks, write_plan).
     Re-read thread rows so GoalBar / mode chrome stay current without a reload. */
  useEffect(() => {
    if (turnKey > 1) void threads.refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turnKey]);
  const nextStep = useNextStep(chat.threadId, turnKey);

  /* The engine's card in the shape `QuestionCard` takes. `toQuestion` COPIES;
     it decides nothing. `diagnosis` is passed only so the card can show what
     somebody already claimed for this fact beside the field — shown, never
     used, and never put in the field. */
  const question = useMemo(() => {
    const card = nextStep.step?.step.question;
    return card ? toQuestion(card, diagnosis) : null;
  }, [nextStep.step, diagnosis]);

  /* THE ENGINE ANSWERED AND HAS NOTHING TO ASK — which is a different thing
     from the engine not having answered, and collapsing the two put a FALSE
     card on the screen. `kind: 'propose'` means the frontier is exhausted: the
     facts it wanted are in the ledger. `question` is null on that branch, and a
     null `question` used to send `QuestionCard` to its own client-side
     derivation, which is computed from the FROZEN diagnosis snapshot in the
     transcript. On a thread where `eval_size_n` had been measured that
     derivation drew "eval_size_n — has not been answered in this thread",
     about a fact the ledger held, and it survived a reload.

     The fallback is still right when the engine has not spoken (no payload
     yet, a failed fetch, a payload the reader refused). It is only wrong when
     the engine HAS spoken and said there is nothing to ask. */
  const frontierExhausted = nextStep.step?.step.kind === 'propose';

  /**
   * Run one tool through THE USER'S DOOR.
   *
   * `POST /api/tools/{name}` hard-codes `actor=USER`, so what a person supplies
   * here is STATED — their own word, which is what opens a `source: ask` gate.
   * The conductor's door passes `model` and the same facts are ASSERTED.
   * `app/main.py`: "Two doors, two words, neither of them reachable from the
   * message."
   *
   * NOTHING A MODEL SAID IS EVER RESENT THROUGH THIS FUNCTION. That would take
   * an assertion, push it through the user's door and hand it back stamped
   * STATED, which is the laundering the engine spent four walls refusing. The
   * arguments come from what the person typed into the control, and from
   * nowhere else.
   *
   * The evidence ledger reloads afterwards, because this route is the one thing
   * in the interface that writes a row to it.
   */
  /**
   * APPROVE ONE TOOL THE MODEL WAS REFUSED, AND RUN IT AS THE PERSON.
   *
   * `runTool` above sends `approved: false` on purpose - it serves the plus
   * menu and the question card, neither of which is an approval. This is the
   * one place in the interface that sends `true`, and it is reached only by
   * pressing a button on a card that shows the arguments it is about to
   * submit. See components/ApprovalCard.tsx for why that matters.
   *
   * It goes through the same user door, so the run is recorded on the thread
   * as an ordinary user-driven row rather than as a special kind of event.
   */
  const approveTool = useCallback(
    async (
      name: string,
      args: Record<string, unknown>,
      threadId: number | null,
    ) => {
      try {
        const outcome = await runToolRequest(name, args, true, threadId);
        const failed =
          typeof outcome.result === 'object' &&
          outcome.result !== null &&
          (outcome.result as { ok?: unknown }).ok === false;
        /* No refresh of the transcript here: the run wrote its own
           tool.call/tool.result pair into this thread through the user door,
           and those arrive on the event stream like every other row. */
        evidence.refresh();
        return { ok: !failed, result: outcome.result, error: null };
      } catch (failure) {
        return {
          ok: false,
          result: null,
          error: failure instanceof Error ? failure.message : String(failure),
        };
      }
    },
    [evidence],
  );

  const runTool = useCallback(
    async (name: string, args: Record<string, unknown>, threadId: number | null) => {
      try {
        const outcome = await runToolRequest(name, args, false, threadId);
        const failed =
          typeof outcome.result === 'object' &&
          outcome.result !== null &&
          (outcome.result as { ok?: unknown }).ok === false;
        evidence.refresh();
        return { ok: !failed, result: outcome.result, error: null };
      } catch (failure) {
        return {
          ok: false,
          result: null,
          error: failure instanceof Error ? failure.message : String(failure),
        };
      }
    },
    [evidence],
  );

  /* THE STORMS IN THIS CONVERSATION, refreshed off the event stream rather
     than a timer: a storm reports every state change into the thread's log, so
     `lastEventId` moving is a node changing state, and the picture updates
     because the work happened. `lib/useStorms.ts` has the argument.

     Denials are separate and local, because the engine has no row for "no" —
     there is no such thing as a storm that was refused. */
  const storms = useStorms(chat.threadId, chat.lastEventId);
  const denials = useDenials(chat.threadId);

  const approve = useCallback(
    (fingerprint: string, proposalArgs: Record<string, unknown>, build: unknown) => {
      if (chat.threadId === null) {
        return Promise.resolve({
          kind: 'refused' as const,
          detail:
            'A storm belongs to a conversation and there is no thread open, so ' +
            'there is nowhere to record the approval. Nothing was sent.',
        });
      }
      return storms.approve(chat.threadId, fingerprint, proposalArgs, build);
    },
    [chat.threadId, storms],
  );

  const [draft, setDraft] = useState('');
  const [dialog, setDialog] = useState<'connect' | 'controls' | 'settings' | null>(null);
  const density = useDensity(chat.threadId);
  const [inspector, setInspector] = useState<InspectorState>(initialInspector);

  const pinInspector = useCallback((next: InspectorState) => {
    try {
      sessionStorage.setItem(INSPECTOR_PIN_KEY, '1');
    } catch {
      /* private mode */
    }
    setInspector(next);
  }, []);

  /* A badge in the transcript opens the pane it belongs to. That contract is
     unchanged by there being one pane: it now aims the inspector rather than
     expanding an accordion, and it opens the inspector if it was shut. */
  const handleOpenPane = useCallback((pane: string) => {
    pinInspector(openInspectorTab(inspector, pane));
  }, [pinInspector, inspector]);

  /* §9.12's narrow response triggers on AVAILABLE CHAT WIDTH, not on the
     viewport: both side columns are resizable, so a viewport media query fires
     at the wrong moment. --col-min is 420px. */
  const viewport = useViewportWidth();
  /* Graphite's layout constants: --rail-w 280, --pane-w 392. 280 is the Codex
     reading and it is wider than the old 260 — folders plus indented thread
     rows plus a right-aligned age need the room, and cutting it truncates
     titles two words early. */
  const [railWidth, setRailWidth] = usePersistedWidth(RAIL_KEY, 280);
  const [paneWidth, setPaneWidth] = usePersistedWidth(PANE_KEY, 392);
  /* CS18 — inspector is always a column split under the shared appbar, never
     a float over the transcript. Clamp the pane so the chat keeps a readable
     measure; both side columns stay resizable. */
  const railDrag = useDrag(railWidth, setRailWidth, 216, 400, +1);
  /* THE FLOOR WAS EATING THE 25% FRAME. Max, 2026-09-19: "the chat can snap
     25%, but the actual sidebar versus machine in context, that's not getting
     snapped to 25%. It's only getting snapped to at most 40 or 33%."
     Measured: the stops are fractions of `viewport - rail`, so at 1440 with a
     280 rail the 25% frame is 290px - under the hard 320 floor, clamped to
     320, which reads as 27.6%. The frame was unreachable below a 1560px
     window. At the other end the hard 640 cap ate the 50% frame above 1560.
     Both bounds now open far enough to hold the frames they are offered,
     and no further: the chat's own room is what closes them. */
  const stops = snapTargets(viewport, railWidth);
  const lowestStop = stops.length > 0 ? stops[0] : 320;
  const highestStop = stops.length > 0 ? stops[stops.length - 1] : 640;
  const paneRoom = Math.max(320, viewport - railWidth - 360);
  const paneFloor = Math.max(240, Math.min(320, lowestStop));
  const paneMax = Math.min(Math.max(640, highestStop), paneRoom);
  /* SNAP FRAMES, and the clamps are unchanged. Max: "create snap frames at
     25%, 33%, 50% so that when we have the different sections open side by
     side they snap into frame instead of working independently". The frames
     are a fraction of the workspace (lib/snapWidth.ts); this grabber keeps the
     320..min(640, paneMax) it always had, and a frame outside that range
     simply never catches. */
  const paneDrag = useSnapDrag(
    paneWidth, setPaneWidth, paneFloor, paneMax, -1, viewport, railWidth,
  );
  /* THE STAGE'S SPLIT (size A) is the inspector widened: same grabber, wider
     clamps, because five panels at 392px is the sidebar problem the Stage
     exists to solve. Leave the chat its own measure. */
  /* The Stage keeps its 480 floor - the lattice needs the room - and
     `useSnapDrag` now offers it only the frames that clear it, so an arrow
     key never lands on a stop the clamp then flattens. */
  const stageMax = Math.min(Math.max(640, highestStop), Math.max(480, viewport - railWidth - 360));
  const stageDrag = useSnapDrag(
    paneWidth, setPaneWidth, 480, stageMax, -1, viewport, railWidth,
  );

  /* ── THE STAGE ─────────────────────────────────────────────────────────
     One state for three sizes (lib/stageState.ts), one read for five panels
     (lib/useStage.ts), refreshed off the thread's own events. The recall and
     carve panels read what the transcript already folded, so nothing is
     fetched twice. */
  const [stage, dispatchStage] = useReducer(stageReducer, undefined, initialStage);
  const stageWanted = stageShows(stage, 'row') || (inspector.open && inspector.active === 'stage');
  const stageData = useStage(chat.threadId, chat.lastEventId, stageWanted);
  /* The route this conversation is on, read off the same event stream: one GET
     per (thread, lastEventId), never a timer. Mounted here rather than in the
     pane because the shell is what knows which thread is open, and only
     fetched while the pane is showing it. */
  const latestRecall = useMemo(() => allReadsOf(chat.items, readRecallReport), [chat.items]);
  const latestCarve = useMemo(() => latestReadOf(chat.items, readCarve), [chat.items]);

  const openStageWindow = useCallback(async () => {
    if (chat.threadId === null) return;
    dispatchStage({ type: 'open', size: 'window' });
    const opened = await nativeOpenStage(chat.threadId);
    if (!opened) {
      /* No shell: the same page as a browser popup. One page, two hosts. */
      window.open(`${window.location.pathname}?stage=${chat.threadId}`, 'mlh-stage', 'width=1280,height=800');
    }
  }, [chat.threadId]);

  const openStageSplit = useCallback(() => {
    dispatchStage({ type: 'open', size: 'split' });
    setInspector((was) => openInspectorTab(was, 'stage'));
  }, []);
  /* HOWEVER THE SPLIT WAS REACHED — the button on the inline row, or the
     Stage tab on the inspector's own rail — five panels need more than the
     392px the other panes live in. Widened once, on arrival, and only when
     it is narrower than the Stage can use; a width the person dragged is
     theirs and is not touched.
     CS11: any work-half subject (files, plan, context, …) widens the same way. */
  useEffect(() => {
    if (inspector.open && wantsHalfWidth(inspector)) {
      if (inspector.active === 'stage') {
        dispatchStage({ type: 'open', size: 'split' });
      }
      /* HALF MEANS ONE NUMBER. This used to compute its own half - of the
         WINDOW, clamped to 680 - while the drag now snaps to half of the
         WORKSPACE. Two different halves is how a pane arrives at 680, gets
         dragged, and jumps: it was never in the frame it looked like it was
         in. Both read `snapTarget` now, so arriving at the half and snapping
         to the half land on the same pixel. */
      if (paneWidth < 560) {
        const half = snapTarget(viewport, railWidth, 0.5);
        setPaneWidth(Math.max(480, Math.min(stageMax, half)));
      }
    } else if (stageShows(stage, 'split') && inspector.active !== 'stage') {
      dispatchStage({ type: 'close', size: 'split' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inspector.open, inspector.active, inspector.tabs.join(',')]);

  /* SIZE C OPENS ITSELF WHILE A RUN SPENDS, AND FOLDS INTO D WHEN IT IS DONE.
     Max, 2026-09-02: "C when it launches and is working, D when it's done."
     The rule itself is `lib/stageTransition.ts` — a pure function of the
     transcript, so it can be tested, and it is: `stageTransition.test.ts`
     holds all four moments. What stays here is the only part that is not a
     decision: remembering which runs have already opened the window, so a
     reload does not reopen one for work that ended hours ago. */
  const seenSpending = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (chat.threadId === null) return;
    const move = nextStageMove({
      items: chat.items,
      seen: seenSpending.current,
      windowOpen: stageShows(stage, 'window'),
    });
    if (move.kind === 'open-window') {
      for (const key of move.started) seenSpending.current.add(key);
      if (!stageShows(stage, 'window')) void openStageWindow();
    } else if (move.kind === 'fold-into-row') {
      nativeCloseStage();
      dispatchStage({ type: 'close', size: 'window' });
      dispatchStage({ type: 'open', size: 'row', anchor: move.anchor });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chat.items, chat.threadId]);
  /* A thread the person left is a thread whose runs are somebody else's
     history: the memory of what opened a window is per conversation. */
  useEffect(() => {
    seenSpending.current = new Set();
  }, [chat.threadId]);

  /* CS6 — clear pin when the person leaves the thread. */
  useEffect(() => {
    try {
      sessionStorage.removeItem(INSPECTOR_PIN_KEY);
    } catch {
      /* ignore */
    }
  }, [chat.threadId]);

  /* CS6 — live run or spending recipe focuses Stage (or Terminal for train). */
  useEffect(() => {
    if (chat.threadId === null) return;
    let pinned = false;
    try {
      pinned = sessionStorage.getItem(INSPECTOR_PIN_KEY) === '1';
    } catch {
      pinned = false;
    }
    if (pinned) return;
    const spending = spendingRows(chat.items);
    const live = longRun.live || spending.length > 0;
    if (!live) return;
    const recipeLog = spending.some((key) => key.startsWith('train'));
    setInspector((was) => openInspectorTab(was, recipeLog ? 'terminal' : 'stage'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [longRun.live, chat.items, chat.threadId]);

  const stageControls = (size: 'row' | 'split') => (
    <>
      {size === 'row' ? (
        <IconButton label="Open the Stage as a split" icon="panel" size="xs" onClick={openStageSplit} />
      ) : null}
      <IconButton label="Detach the Stage into its own window" icon="open" size="xs" onClick={() => void openStageWindow()} />
      <IconButton
        label={size === 'row' ? 'Fold the Stage back into the row' : 'Close the Stage'}
        icon="x"
        size="xs"
        onClick={() => {
          dispatchStage({ type: 'close', size });
          if (size === 'split') setInspector((was) => openInspectorTab(was, 'eval'));
        }}
      />
    </>
  );
  const stageAt = (size: 'row' | 'split') => (
    <Stage
      payload={stageData.payload}
      state={stage}
      dispatch={dispatchStage}
      size={size}
      recall={latestRecall}
      carve={latestCarve}
      controls={stageControls(size)}
      loading={stageData.loading}
      error={stageData.error}
    />
  );

  const open = useMemo(
    () => threads.threads.find((thread) => thread.id === chat.threadId) ?? null,
    [chat.threadId, threads.threads],
  );
  /* Page 18.2: on a new thread the title renders in --ink-3 rather than
     --ink-1, "because 'New thread' is a placeholder the product wrote and not
     something the user said". */
  const title = chat.threadId === null ? 'New thread' : open?.title ?? 'Thread';
  /**
   * WHERE THE NEXT THREAD LANDS.
   *
   * `POST /api/threads` with no `project_id` files the thread in the engine's
   * `db.default_project()`. That is right when the user has expressed no
   * preference and wrong the moment they have: a project made in the rail used
   * to stay empty forever, because nothing in the interface could aim a thread
   * at it. So the destination is the project of the thread you are reading, or
   * the one you last picked in the rail, and the rail shows which.
   */
  const [pickedProject, setPickedProject] = useState<number | null>(null);
  const openProject = open?.project_id ?? pickedProject;

  /* The open project as a workspace: its name and the folder it sits on.
     Read in two places — the chip under the composer, and the question card's
     path fields — so it is resolved once, here. */
  const workspace = useMemo(() => {
    for (const g of threads.groups) {
      if (g.project && g.project.id === openProject) {
        return {
          id: g.project.id,
          name: g.project.name,
          root: g.project.root_path ?? null,
        };
      }
    }
    return null;
  }, [threads.groups, openProject]);

  /* QUEUED WHILE IT WORKS, SENT WHEN IT IS FREE. Max, 2026-09-14: "also add a
     queueing prompt feature." Each queued line goes out as the person's own
     message, in the order they typed it - never merged, never reordered, and
     one at a time, because a turn is one question and one answer. */
  const queue = useQueuedPrompts(chat.streaming, (text) => void chat.send(text));
  const send = useCallback(() => {
    const text = draft;
    if (!text.trim()) return;
    setDraft('');
    if (chat.streaming) queue.add(text);
    else void chat.send(text);
  }, [draft, chat, queue]);

  /* The transcript follows the tail while a reply is streaming, and stops
     following the moment the reader scrolls up — a column that yanks itself
     back down is unreadable. */
  const thread = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  useEffect(() => {
    const el = thread.current;
    if (!el || !following.current) return;
    el.scrollTop = el.scrollHeight;
  }, [chat.items, chat.streaming]);

  return (
    <div
      className="app"
      data-stack={inspector.open ? 'open' : 'closed'}
      style={{
        ['--rail-w' as string]: `${railWidth}px`,
        ['--pane-w' as string]: `${paneWidth}px`,
      }}
    >
      <Rail
        groups={threads.groups}
        count={threads.threads.length}
        loading={threads.loading}
        error={threads.error}
        selectedId={chat.threadId}
        destinationId={openProject}
        provider={providers.active}
        onSelect={(id) => chat.openThread(id)}
        /* A new thread lands in the project of the one you were reading, or in
           the one you picked in the rail. With neither, the choice goes to the
           engine's own `db.default_project()` rather than to a second rule here
           that could disagree with it. */
        onNew={() => chat.openThread(null, openProject)}
        onDuplicateProject={(id) => {
          void duplicateProject(id).then(() => threads.refresh());
        }}
        onArchiveProject={(id) => {
          void threads.archiveProject(id);
        }}
        onDeleteProject={async (id) => {
          await threads.removeProject(id);
          /* The project the next thread would land in is gone with its
             threads; if the open one was among them the shell returns to the
             empty state with no destination, and the rail's first project
             becomes it on the next pick. */
          if (pickedProject === id) setPickedProject(null);
          if (open?.project_id === id) chat.openThread(null, null);
        }}
        onOpenPane={handleOpenPane}
        onPickProject={(id) => {
          setPickedProject(id);
          chat.openThread(null, id);
        }}
        onAddProject={async (name) => {
          /* A PROJECT SITS ON A PATH FROM BIRTH. The owner: "as soon as you
             start a new project... A project has to sit on a path. This path
             is easily visible." So the shell asks for the folder in the same
             breath as the name. Declining the picker still creates the
             project — the amber chip under the composer then says 'no folder
             attached' and offers the same picker — so nothing blocks, but
             the default path is now to HAVE a path. */
          const root = hasNativeShell() ? await nativePickPath('directory') : null;
          /* A project you just made is a project you are about to work in.
             Aiming the composer at it here is what stops the very next thread
             going to Default and leaving the new folder empty. */
          const project = await threads.addProject(name, root);
          setPickedProject(project.id);
          chat.openThread(null, project.id);
          return project;
        }}
        onControls={() => setDialog('controls')}
        /* THE BOTTOM-LEFT ROW IS THE SETTINGS DOOR. Max: "At the bottom left
           you just have the account and settings… your local config settings
           can be controlled from here instead of an actual online account."
           The rail's foot row is that place, so it opens Settings — whose
           first section is the connections, which is what the row names. The
           fast one-click connect still lives on the composer's model chip.
           The row's own label and glyph are `components/Rail.tsx`, which
           another lane owns this run; see the report. */
        onConnect={() => setDialog('settings')}
        onResizeStart={railDrag}
        activity={activity}
        pinned={threads.pinned}
        onTogglePin={threads.togglePin}
        onRename={threads.rename}
        onArchive={async (id) => {
          await threads.archive(id);
          /* The open thread has just left the rail. Leaving it on screen would
             leave a person reading a transcript they can no longer navigate
             back to, so the shell returns to the empty state. */
          if (chat.threadId === id) chat.openThread(null, openProject);
        }}
        onDelete={async (id) => {
          await threads.remove(id);
          if (chat.threadId === id) chat.openThread(null, openProject);
        }}
      />

      <main className="workspace">
        {/* The app bar, Graphite's: the thread title, then quiet controls on
            the right. Nothing in here is coloured, and it is exactly
            --topbar-h — page 18 puts the rail, the centre and the pane on one
            44px line "so the three columns read as one window rather than
            three panels stacked into a frame".

            The old bar carried FOUR segmented groups and starved the title
            down to "What …". Three have gone: row size, because compact is the
            only density; theme, because it is one icon button now; and the
            portal switch, which page 18 lists under what a top bar never
            carries and which has now left the product altogether. ONE
            segmented control remains, and it is the only one this window has.
            Measured with all four in place, the bar was 69px and wrapped to
            two rows. */}
        <div className="appbar" data-tauri-drag-region>
          <h1
            className="appbar__title"
            data-placeholder={chat.threadId === null ? 'true' : undefined}
          >
            {title}
          </h1>

          <span className="appbar__right">
            <StreamState
              threadId={chat.threadId}
              status={chat.status}
              detail={chat.statusDetail}
              lastEventId={chat.lastEventId}
              onInterrupt={chat.interrupt}
            />

            {/* THE JOURNEY REPORT BUTTON HAS GONE, 2026-09-13. Max: "we
                don't really need that top right button at the header, it's a
                little bit repetitive and not really required." It was already
                repetitive before he said it: the report writes itself into the
                project folder the moment every step is ticked
                (components/TheBuildWorksDown.tsx), and the Files pane lists
                what it wrote. A button for a thing that happens by itself is a
                second answer to "did that happen". */}

            {/* THE MODES LEFT THE BAR, 2026-09-11. Plan/Build, autonomy and the
                build loop are per-conversation state, and the owner put them
                where the conversation is: under the chat box. The bar keeps
                the frame - the pane toggle, the theme, the window. See
                components/Composer.tsx. */}
            {/* THE DENSITY CONTROL IS GONE, 2026-09-10. Max, looking at the
                running product: "Remove the summary in normal. That doesn't
                make any sense. Just have it on normal always."

                It was already down from three levels to two on his say-so, and
                the argument that removed Verbose applies once more to what was
                left: Summary's only job was to hide a turn's arguments, which
                is a click on the row that wants it. A control whose two
                settings differ by one hideable detail is a mode for something
                the interface already does. */}
            {/* Page 18.3: "A control that toggles a layout carries an icon
                alone in a bordered 26px square, because a layout toggle has no
                name a user needs and its state is visible in the window
                itself." It lives here rather than in the inspector because the
                thing it turns on is not on screen when it is off. */}
            <button
              type="button"
              className="iconbtn iconbtn--bordered"
              aria-pressed={inspector.open}
              aria-label={inspector.open ? 'Hide the inspector' : 'Show the inspector'}
              title={inspector.open ? 'Hide the inspector' : 'Show the inspector'}
              onClick={() =>
                setInspector({ ...inspector, open: !inspector.open })
              }
            >
              <Icon name="panel" />
            </button>

            <ThemeToggle theme={theme} onChange={setTheme} />
            <WindowControls />
          </span>
        </div>

        {/* WHAT WAS HERE: the portal switch, fenced behind SCAFFOLDING.
            DESIGN_DIRECTIVES §3, superseded by Max on 2026-08-19 — "There is
            one product… the scaffolding toggle in the shell should go." It has
            gone, along with the strip that carried it. There is nothing
            between the app bar and the transcript now, which is what the top
            bar's own rule asked for in the first place.

            AND THAT IS STILL TRUE, because `EngineNotice` renders NOTHING
            unless the engine underneath this page stopped being the engine it
            loaded against. It is not a status bar; it is the absence of one
            until there is something to say. See components/EngineNotice.tsx. */}
        <EngineNotice />

        {/* CS18 — shared appbar above; chat and inspector share one body row so
            the panel is a direct split, not a float over the transcript. */}
        <div className="workspace__body">
          <div className="centre">
            <div
              className="thread scroll-y"
              ref={thread}
              onScroll={(event) => {
                const el = event.currentTarget;
                following.current =
                  el.scrollHeight - el.scrollTop - el.clientHeight < 48;
              }}
            >
              {/* The empty thread centres itself in the whole column rather than
                  sitting at the top of the measure — it is a screen, not a
                  message. */}
              {chat.threadId === null ? (
                <StartSheet
                  prefs={{
                    ...startPrefs,
                    projectId: startPrefs.projectId ?? openProject,
                  }}
                  onPrefs={(next) => {
                    setStartPrefs(next);
                    if (next.projectId !== null) {
                      setPickedProject(next.projectId);
                      chat.openThread(null, next.projectId);
                    }
                  }}
                  onPrompt={setDraft}
                  onConnect={() => setDialog('connect')}
                  onAssignFolder={(projectId) => {
                    void (async () => {
                      const picked = hasNativeShell()
                        ? await nativePickPath('directory')
                        : window.prompt('Folder path for this project (absolute):');
                      if (!picked) return;
                      await setProjectRoot(projectId, picked);
                      threads.refresh();
                    })();
                  }}
                />
              ) : (
                <Transcript
                  items={chat.items}
                  streaming={chat.streaming}
                  tools={tools.byName}
                  density={density}
                  threadId={chat.threadId}
                  runTool={runTool}
                  storms={storms.forFingerprint}
                  denials={denials}
                  onApprove={approve}
                  onCancelStorm={(id) => void storms.cancel(id)}
                  question={question}
                  frontierExhausted={frontierExhausted}
                  workspaceRoot={workspace?.root ?? null}
                  permission={
                    (['ask', 'measure', 'write', 'full'].includes(String(open?.permission ?? ''))
                      ? (String(open?.permission) as 'ask' | 'measure' | 'write' | 'full')
                      : 'ask')
                  }
                  onApproveTool={approveTool}
                  onAnswered={() => {
                    nextStep.answered();
                    evidence.refresh();
                  }}
                  stageAnchor={stageShows(stage, 'row') ? stage.anchor : null}
                  stageNode={stageAt('row')}
                  onStage={(anchor) =>
                    dispatchStage(anchor === null ? { type: 'close', size: 'row' } : { type: 'open', size: 'row', anchor })
                  }
                  onEffectsReverted={() => void threads.refresh()}
                  onOpenThread={(id) => chat.openThread(id)}
                  board={
                    <SubAgentBoard
                      read={subAgents.read}
                      onOpen={(id) => chat.openThread(id)}
                      onStop={(id) => void subAgents.stop(id)}
                    />
                  }
                />
              )}
            </div>

            <Composer
              workspace={workspace}
              onAssignFolder={(projectId) => {
                void (async () => {
                  /* The shell opens the real folder picker; a plain browser tab
                     falls back to typing the path. Either way the answer goes
                     through the engine's own door and the chip re-reads it. */
                  const picked = hasNativeShell()
                    ? await nativePickPath('directory')
                    : window.prompt('Folder path for this project (absolute):');
                  if (!picked) return;
                  await setProjectRoot(projectId, picked);
                  threads.refresh();
                })();
              }}
              value={draft}
              onChange={setDraft}
              onSend={send}
              onStop={() => {
                if (chat.threadId === null) return;
                /* The engine decides whether anything was running; the button
                   is only drawn while the turn state says it is. */
                void stopTurn(chat.threadId).catch(() => undefined);
              }}
              onConnect={() => setDialog('connect')}
              onControls={() => setDialog('controls')}
              /* The plus attaches context for real now — `attach_context` and
                 `list_context`, through the user's door, with the thread the facts
                 belong to. Same function the transcript's controls use. */
              runTool={runTool}
              threadId={chat.threadId}
              mode={String(open?.mode ?? 'build')}
              permission={
                (['ask', 'measure', 'write', 'full'].includes(String(open?.permission ?? ''))
                  ? String(open?.permission)
                  : open?.autonomous
                    ? 'write'
                    : 'ask') as 'ask' | 'measure' | 'write' | 'full'
              }
              plan={open?.plan ?? null}
              items={chat.items}
              onThreadChanged={() => void threads.refresh()}
              provider={providers.active}
              providers={providers.providers}
              onUseProvider={providers.use}
              presetNames={providers.presets.map((preset) => preset.name)}
              onSetEffort={(id, effort) => providers.update(id, { effort })}
              providersLoading={providers.loading}
              turn={chat.turn}
              engineWorking={chat.engineWorking}
              error={chat.error}
              lastEventId={chat.lastEventId}
              onOpenContext={() => setInspector((was) => openInspectorTab(was, 'context'))}
              onSlashGoal={() => {
                showGoalBar();
                setInviteGoalEdit(true);
              }}
              onSlashPlan={() => {
                void openPlanSurface(chat.threadId, setInspector);
              }}
              onSlashDoc={() => {
                showGoalBar();
                void openPlanSurface(chat.threadId, setInspector);
              }}
              /* Graphite puts the suggestion cards ABOVE the composer and outside
                 it, not in the transcript. */
              /* THE GOAL CARD, ABOVE THE CHAT BOX. Max, 2026-09-13: "a pop up
                 hovering above the chatbox like goal mode in cursor or codex."
                 It lives in the composer's dock rather than in the transcript so
                 it stays put while the conversation scrolls under it. */
              goal={
                <GoalBar
                threadId={chat.threadId}
                mode={String(open?.mode ?? 'build')}
                plan={open?.plan ?? null}
                todo={open?.todo ?? null}
                planPath={open?.plan_path ?? null}
                projectId={workspace?.id ?? null}
                items={chat.items}
                running={chat.turn !== 'idle'}
                failed={chat.error !== null}
                lastEventId={chat.lastEventId}
                onContinue={chat.continueTurn}
                onOpenPlan={() => {
                  showGoalBar();
                  void openPlanSurface(chat.threadId, setInspector);
                }}
                onOpenDoc={(path) => {
                  showGoalBar();
                  void openPlanSurface(chat.threadId, setInspector, path);
                }}
                onSay={(words) => void chat.send(words)}
                onDraft={(words) => setDraft(words)}
                onPlan={async (next) => {
                  if (chat.threadId === null) return;
                  await setThreadPlan(chat.threadId, next);
                  await threads.refresh();
                }}
                />
              }
              suggestions={chat.threadId === null ? <Suggestions onPrompt={setDraft} /> : null}
              queued={queue.waiting}
              onUnqueue={queue.drop}
            />
          </div>

          {/* Not merely hidden: rendered once or not at all. Leaving it in the DOM
              behind `display:none` duplicated every pane's rows and its landmark,
              so a screen reader met the Machine pane twice. */}
          {inspector.open ? (
            <Inspector
              state={inspector}
              setState={(next) => {
                /* Tab / + menu click pins so CS6 auto-focus does not yank Journey away. */
                try {
                  sessionStorage.setItem(INSPECTOR_PIN_KEY, '1');
                } catch {
                  /* ignore */
                }
                setInspector(next);
              }}
              onResizeStart={
                (wantsHalfWidth(inspector) ? stageDrag : paneDrag).onPointerDown
              }
              onResizeKey={(wantsHalfWidth(inspector) ? stageDrag : paneDrag).onKeyDown}
              snappedTo={(wantsHalfWidth(inspector) ? stageDrag : paneDrag).snapped}
              diagnosis={diagnosis}
              evidence={evidence}
              evals={evals}
              onControls={() => setDialog('controls')}
              workspace={workspace}
              stage={inspector.active === 'stage' ? stageAt('split') : null}
              liveRunId={longRun.live ? chat.threadId : null}
              sandboxId={
                spendingRows(chat.items).find((key) => key.startsWith('train')) ?? null
              }
              context={
                inspector.active === 'context' ? (
                  <ContextPane threadId={chat.threadId} tick={chat.lastEventId} />
                ) : null
              }
              plan={
                inspector.active === 'plan' ? (
                  <PlanPanel
                    threadId={chat.threadId}
                    plan={open?.plan ?? null}
                    onSaved={() => void threads.refresh()}
                  />
                ) : null
              }
              agents={
                inspector.active === 'agents' ? (
                  <AgentsPane
                    read={subAgents.read}
                    onOpen={(id) => chat.openThread(id)}
                    onStop={(id) => void subAgents.stop(id)}
                  />
                ) : null
              }
              journey={
                <JourneyPane
                  threadId={chat.threadId}
                  lastEventId={chat.lastEventId}
                  active={inspector.active === 'journey'}
                  onDoStep={(tool, prefill) => {
                    setControlsFocus(tool);
                    setControlsPrefill(prefill);
                    setDialog('controls');
                  }}
                  onChanged={() => void threads.refresh()}
                />
              }
              threadId={chat.threadId}
            />
          ) : null}
        </div>
      </main>

      {dialog === 'connect' ? (
        <ConnectModel
          providers={providers}
          onClose={() => setDialog(null)}
          onSettings={() => setDialog('settings')}
        />
      ) : null}
      {dialog === 'settings' ? (
        <Settings
          providers={providers}
          theme={theme}
          onTheme={setTheme}
          instructionSet={tools.instructionSet}
          projectId={open?.project_id ?? openProject ?? null}
          onConnect={() => setDialog('connect')}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === 'controls' ? (
        <Controls
          tools={tools}
          threadId={chat.threadId}
          storms={storms}
          denials={denials}
          onApprove={approve}
          focus={controlsFocus}
          prefill={controlsPrefill}
          onClose={() => {
            setDialog(null);
            setControlsFocus(null);
            setControlsPrefill(null);
          }}
        />
      ) : null}
    </div>
  );
}

/**
 * The connection to the event log, stated rather than hidden.
 *
 * The engine ends the response about every 25 seconds on purpose
 * (`event_stream(timeout: float = 25.0)`), so "connecting" flickers past
 * constantly and is not worth a badge; only a state that persists is. The
 * drop button is here because the claim this product makes about reconnection
 * is worth being able to test by hand: pull the connection mid-reply and watch
 * the transcript come back complete from `Last-Event-ID`.
 */
function StreamState({
  threadId,
  status,
  detail,
  lastEventId,
  onInterrupt,
}: {
  threadId: number | null;
  status: string;
  detail: string;
  lastEventId: number;
  onInterrupt: () => void;
}) {
  if (threadId === null) return null;
  /* THE HEALTHY STATE IS NOTHING AT ALL. First cut: "following · event 412 ·
     drop". Second: one quiet word, "live", with the drop button on hover.
     Third, 2026-09-12, the owner pointing at the roof beside the thread
     title: "I don't think we need this live / drop thing." A connection
     that works is not news, and the drop button was a test instrument for
     the replay claim - `tests/` holds that claim now, not the toolbar. What
     stays is the one state worth a chip: the stream is NOT healthy, said in
     its own word, with the event id in the hover for whoever verifies. */
  const healthy = status === 'open' || status === 'connecting';
  if (healthy) return null;
  void onInterrupt;
  return (
    <span
      className="streamstate"
      data-status={status}
      title={`${detail ? `${detail} · ` : ''}at event ${lastEventId}`}
    >
      <span className="streamstate__word">{status}</span>
    </span>
  );
}

/* ── Density, per thread ───────────────────────────────────────────────────── */

/* NORMAL, ALWAYS. The stored preference is deliberately not read: a thread
   last opened at Summary would otherwise come back at a level the product no
   longer offers and no control can leave. The key is left on disk rather than
   migrated - nothing reads it, and deleting somebody's browser storage to tidy
   up is a bigger act than ignoring a value. */
function useDensity(_threadId: number | null): Density {
  return 'normal';
}

/* ── Resizing ───────────────────────────────────────────────────────────────
   §4.1 gives min and max for both. The pointer handler clamps to them, so a
   drag cannot produce a width the design system does not allow. */

function useViewportWidth(): number {
  const [width, setWidth] = useState(() => window.innerWidth);
  useEffect(() => {
    const onResize = () => setWidth(window.innerWidth);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);
  return width;
}





function usePersistedWidth(
  key: string,
  fallback: number,
): [number, (next: number) => void] {
  const [width, setWidth] = useState<number>(() => {
    const stored = Number(localStorage.getItem(key));
    return Number.isFinite(stored) && stored > 0 ? stored : fallback;
  });
  const set = useCallback(
    (next: number) => {
      setWidth(next);
      localStorage.setItem(key, String(next));
    },
    [key],
  );
  return [width, set];
}

function useDrag(
  current: number,
  set: (next: number) => void,
  min: number,
  max: number,
  /* +1 when dragging right widens (the rail), -1 when it narrows (the stack) */
  sign: 1 | -1,
) {
  const start = useRef({ x: 0, width: 0 });

  return useCallback(
    (event: React.PointerEvent) => {
      event.preventDefault();
      start.current = { x: event.clientX, width: current };
      const move = (moveEvent: PointerEvent) => {
        const delta = (moveEvent.clientX - start.current.x) * sign;
        set(Math.min(max, Math.max(min, start.current.width + delta)));
      };
      const up = () => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    },
    [current, set, min, max, sign],
  );
}
