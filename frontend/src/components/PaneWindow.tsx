/**
 * EVERY PANE, IN ITS OWN WINDOW, BOUND TO ONE THREAD - WITH THE RAIL.
 *
 * Max, 2026-09-12: *"when you click a pop out, you expect to pop out that
 * certain page... I still want the sidebar though, because I want to interact
 * and work with the other things and the other features in our little pop
 * out sidebar section. This way you can navigate everything uniquely and
 * exclusively from this pop out. So you can have two windows open, one for
 * your tools - plan, machine, etcetera - and just your chat window... this
 * means everything should be able to come into a pop out. Literally every
 * single thing."*
 *
 * So this window IS the inspector, detached: the same pane rail, the same
 * header, the same `PaneBody`, opened on the pane the person popped and free
 * to move to any other. It follows one thread - the id comes from the query
 * string and is never re-pointed; a second thread's window is a second
 * window (`src-tauri/src/lib.rs::open_pane` puts the thread in the label).
 *
 * WHERE ITS FACTS COME FROM. The shell composes the panes from six hooks
 * over the open chat; this window has no chat box, so it follows the
 * thread's event stream directly (the way `StageWindow` does) and folds it
 * with the same `foldEvents` the transcript uses. The diagnosis and the eval
 * runs are read off that fold by `lib/theThreadRead.ts` - one reader for
 * both windows, so they cannot disagree about the same run. Evidence,
 * storms, denials, the stage and the journey are the same hooks the shell
 * calls, given this thread id. The Controls dialog opens here too, for the
 * Machine pane's "run it" buttons and the journey's "do this step".
 */

import { useCallback, useEffect, useMemo, useReducer, useState } from 'react';

import { getThread, listProjects } from '../lib/engine/client';
import { readCarve } from '../lib/engine/datawork';
import { openEventStream } from '../lib/engine/events';
import type { Prefilled } from '../lib/engine/journey';
import { readRecallReport } from '../lib/engine/retrieval';
import type { EngineEvent, Project, Thread } from '../lib/engine/types';
import { initialStage, stageReducer } from '../lib/stageState';
import { evalReportsIn, latestDiagnosis } from '../lib/theThreadRead';
import { foldEvents } from '../lib/transcript';
import { allReadsOf, latestReadOf } from '../lib/transcriptReads';
import { useDenials } from '../lib/useApprovals';
import { useEvidence } from '../lib/useEvidence';
import { useLocalSpecs } from '../lib/useLocalSpecs';
import { useStage } from '../lib/useStage';
import { useStorms } from '../lib/useStorms';
import { useTools } from '../lib/useTools';
import { ContextPane } from './ContextPane';
import { Controls } from './Controls';
import { Icon } from './Icon';
import { JourneyPane } from './JourneyPane';
import {
  PANE_ICON,
  PANE_ORDER,
  PANE_TITLE,
  PaneBody,
  paneProvenance,
  type PaneId,
} from './PaneStack';
import { PlanDocument } from './PlanDocument';
import { Stage } from './Stage';
import { StatusDot } from './primitives';
import { WindowControls } from './WindowControls';

/* The same sheets the shell loads, in the same order, for the same cascade
   reasons App.tsx gives at each import. `main.tsx` loads tokens and base. */
import '../styles/shell.css';
import '../styles/chat.css';
import '../styles/engine.css';
import '../styles/provenance.css';
import '../styles/plan.css';
import '../styles/evals.css';
import '../styles/retrieval.css';
import '../styles/datawork.css';

/** Every pane the inspector has can be a window now. The list is the
 *  inspector's own, so a pane added there is a pane that pops out. */
export const PANES_THAT_POP_OUT: readonly PaneId[] = PANE_ORDER;

export function canPopOut(pane: string): pane is PaneId {
  return (PANE_ORDER as readonly string[]).includes(pane);
}

export function PaneWindow({ pane, threadId }: { pane: string; threadId: number }) {
  const [subject, setSubject] = useState<PaneId>(canPopOut(pane) ? pane : 'machine');

  /* THE THREAD'S EVENTS, FOLLOWED LIVE. Keyed by id because a reconnect
     replays from `Last-Event-ID` and may hand back a frame already held. */
  const [events, setEvents] = useState<Map<number, EngineEvent>>(new Map());
  const [lastEventId, setLastEventId] = useState(0);
  const [following, setFollowing] = useState(false);
  useEffect(() => {
    const handle = openEventStream(`thread:${threadId}`, {
      since: 0,
      onEvent: (event) => {
        setLastEventId(event.id);
        setEvents((held) => {
          if (held.has(event.id)) return held;
          const next = new Map(held);
          next.set(event.id, event);
          return next;
        });
      },
      onStatus: (status) => setFollowing(status === 'open'),
    });
    return () => handle.close();
  }, [threadId]);

  const items = useMemo(
    () => foldEvents([...events.values()].sort((a, b) => a.id - b.id)),
    [events],
  );
  const diagnosis = useMemo(() => latestDiagnosis(items), [items]);
  const evals = useMemo(() => evalReportsIn(items), [items]);
  const [pickedEval, setPickedEval] = useState<number | null>(null);
  const recalls = useMemo(() => allReadsOf(items, readRecallReport), [items]);
  const carve = useMemo(() => latestReadOf(items, readCarve), [items]);

  const evidence = useEvidence(threadId);
  const specs = useLocalSpecs();
  const tools = useTools();
  const storms = useStorms(threadId, lastEventId);
  const denials = useDenials(threadId);

  /* THE THREAD ROW - its title, its plan, its project. Re-read every few
     seconds and on focus: a Tauri window that is never focused never fires
     `focus`, which is why a pop-out opened before the plan landed used to
     stay on "No plan yet" (2026-09-12). One small GET. */
  const [thread, setThread] = useState<Thread | null>(null);
  const [failed, setFailed] = useState(false);
  const read = useCallback(async () => {
    try {
      const detail = await getThread(threadId);
      setThread(detail.thread);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [threadId]);
  useEffect(() => {
    void read();
    const again = () => void read();
    const tick = window.setInterval(again, 4000);
    window.addEventListener('focus', again);
    return () => {
      window.clearInterval(tick);
      window.removeEventListener('focus', again);
    };
  }, [read]);

  const [projects, setProjects] = useState<Project[]>([]);
  useEffect(() => {
    listProjects(true)
      .then(setProjects)
      .catch(() => {
        /* The Files and Memory panes then say they have no project, which is
           honest; nothing else here needs the folder. */
      });
  }, [threadId]);
  const workspace = useMemo(() => {
    const project = projects.find((each) => each.id === thread?.project_id) ?? null;
    return project ? { id: project.id, name: project.name, root: project.root_path ?? null } : null;
  }, [projects, thread]);

  /* THE STAGE AT ITS SPLIT SIZE. Its own state here, as `StageWindow` keeps
     one: this window is not the shell's inline row. */
  const [stage, dispatchStage] = useReducer(stageReducer, undefined, initialStage);
  useEffect(() => {
    dispatchStage({ type: 'open', size: 'split' });
  }, []);
  const stageData = useStage(threadId, lastEventId, subject === 'stage');

  /* CONTROLS, HERE TOO. The Machine pane's "run it" and the journey's "do
     this step" both open the dialog; a pop-out that sent the person back to
     the main window for it would not be the second window he asked for. */
  const [dialog, setDialog] = useState<'controls' | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [prefill, setPrefill] = useState<Record<string, Prefilled> | null>(null);
  const approve = useCallback(
    (fingerprint: string, proposalArgs: Record<string, unknown>, build: unknown) =>
      storms.approve(threadId, fingerprint, proposalArgs, build),
    [storms, threadId],
  );

  useEffect(() => {
    document.title = `${PANE_TITLE[subject]} · ${thread?.title ?? `thread ${threadId}`}`;
  }, [subject, thread, threadId]);

  const provenance = paneProvenance(
    subject,
    specs.status === 'ok' ? specs.specs : null,
    { threadId },
  );

  return (
    <div className="panewindow">
      <div className="panewindow__bar" data-tauri-drag-region>
        <Icon name={PANE_ICON[subject]} size={14} />
        <span className="panewindow__title">{PANE_TITLE[subject]}</span>
        <span className="panewindow__thread" title={`thread ${threadId}`}>
          {thread?.title ?? `thread ${threadId}`}
        </span>
        <span
          className="panewindow__following"
          title={following ? 'Following this thread live' : 'Reconnecting to the engine'}
        >
          <StatusDot role={following ? 'st-done' : 'st-neutral'} shape="filled" />
          {following ? 'following' : 'reconnecting'}
        </span>
        {/* NO NATIVE FRAME on this window either, so without these it could not
            be dismissed at all. Same argument as StageWindow. */}
        <WindowControls />
      </div>

      <div className="panewindow__body panewindow__body--rail">
        {/* THE PANE RAIL, the inspector's own: every pane is one icon, the
            current one carrying the selected inlay. Click one and this window
            becomes that pane for this thread. */}
        <nav className="inspector__rail" aria-label="Panes">
          {PANE_ORDER.map((each) => (
            <button
              key={each}
              type="button"
              className="inspector__tab"
              aria-current={each === subject || undefined}
              title={PANE_TITLE[each]}
              aria-label={PANE_TITLE[each]}
              onClick={() => setSubject(each)}
            >
              <Icon name={PANE_ICON[each]} />
            </button>
          ))}
        </nav>

        <div className="inspector__main">
          <header className="inspector__head">
            <Icon name={PANE_ICON[subject]} />
            <span className="inspector__subject">{PANE_TITLE[subject]}</span>
          </header>
          {provenance ? <div className="inspector__prov">{provenance}</div> : null}
          <div className="inspector__body scroll-y" id={`pane-${subject}`}>
            {subject === 'plan' && failed ? (
              <p className="panewindow__unknown">
                The engine did not answer when this window asked for the plan.
              </p>
            ) : (
              <PaneBody
                id={subject}
                journey={
                  <JourneyPane
                    threadId={threadId}
                    lastEventId={lastEventId}
                    active={subject === 'journey'}
                    onDoStep={(tool, offered) => {
                      setFocus(tool);
                      setPrefill(offered);
                      setDialog('controls');
                    }}
                    onChanged={() => void read()}
                  />
                }
                /* THE DOCUMENT, not the phase editor - the pop-out is where
                   the plan is READ (components/PlanDocument.tsx); Edit is one
                   click inside it. */
                context={
                  subject === 'context' ? (
                    <ContextPane threadId={threadId} tick={lastEventId} />
                  ) : null
                }
                plan={
                  subject === 'plan' ? (
                    <PlanDocument
                      threadId={threadId}
                      plan={thread?.plan ?? null}
                      planPath={thread?.plan_path ?? null}
                      onSaved={() => void read()}
                    />
                  ) : null
                }
                diagnosis={diagnosis}
                evidence={evidence}
                evals={evals}
                pickedEval={pickedEval}
                onPickEval={setPickedEval}
                onControls={() => setDialog('controls')}
                workspace={workspace}
                projectId={workspace?.id ?? thread?.project_id ?? null}
                stage={
                  subject === 'stage' ? (
                    <Stage
                      payload={stageData.payload}
                      state={stage}
                      dispatch={dispatchStage}
                      size="split"
                      recall={recalls}
                      carve={carve}
                      loading={stageData.loading}
                      error={stageData.error}
                    />
                  ) : null
                }
              />
            )}
          </div>
        </div>
      </div>

      {dialog === 'controls' ? (
        <Controls
          tools={tools}
          threadId={threadId}
          storms={storms}
          denials={denials}
          onApprove={approve}
          focus={focus}
          prefill={prefill}
          onClose={() => {
            setDialog(null);
            setFocus(null);
            setPrefill(null);
          }}
        />
      ) : null}
    </div>
  );
}
