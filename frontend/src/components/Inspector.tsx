/**
 * THE INSPECTOR — Cursor-style chrome tabs over a column split (CS14–CS19).
 *
 * One work column beside the chat, under the shared appbar. Open panes are a
 * square-chip strip (icon + short label; X on hover) above the panel body.
 * Close a subject on the chrome tab X; hide the whole column from the appbar
 * panel toggle — never a second X inside the card. Pop-out stays on the tools
 * head. Endpoint “from GET …” lines stay out of people’s faces (CS19).
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocalSpecs } from '../lib/useLocalSpecs';
import type { EvidenceState } from '../lib/useEvidence';
import type { DiagnosisPayload } from '../lib/engine/facts';
import type { EvalReport } from '../lib/engine/evals';
import {
  closeInspectorTab,
  focusInspectorTab,
  openInspectorTab,
  type InspectorState,
} from '../lib/inspectorTabs';
import { Icon } from './Icon';
import {
  currentEvalReport,
  PANE_ICON,
  PANE_ORDER,
  PANE_TITLE,
  PaneBody,
  paneProvenance,
  type PaneId,
} from './PaneStack';
import { FIVE_GATES } from '../data/sample';

export type { PaneId } from './PaneStack';
export type { InspectorState } from '../lib/inspectorTabs';
export { PANE_ORDER } from './PaneStack';
export { initialInspector, openInspectorTab } from '../lib/inspectorTabs';
import { canPopOut } from './PaneWindow';
import { nativeOpenPane } from '../lib/engine/shell';

/** CS14 — panes offered in the `+` menu (Data lives inside Stage). */
export const PANE_MENU: readonly PaneId[] = PANE_ORDER.filter((id) => id !== 'data');

/** Short labels for the tab strip — Context window → Context. */
export const TAB_LABEL: Record<PaneId, string> = {
  ...PANE_TITLE,
  context: 'Context',
};

export function Inspector({
  state,
  setState,
  onResizeStart,
  onResizeKey,
  snappedTo = null,
  diagnosis,
  evidence,
  evals,
  onControls,
  workspace,
  stage,
  journey,
  plan,
  context,
  agents,
  threadId = null,
  liveRunId = null,
  sandboxId = null,
}: {
  state: InspectorState;
  setState: (next: InspectorState) => void;
  onResizeStart: (event: React.PointerEvent) => void;
  /* Left and Right step the pane through the snap frames when the grabber has
     focus — the only way to reach them without a pointer. Optional so the
     component's own tests can render it without a shell. */
  onResizeKey?: (event: React.KeyboardEvent) => void;
  /* The frame the drag is currently held by, in px, or null when it is free.
     The grabber draws the accent while it is a number. */
  snappedTo?: number | null;
  diagnosis: DiagnosisPayload | null;
  evidence: EvidenceState;
  evals: EvalReport[];
  onControls: () => void;
  workspace?: { id: number; name: string; root: string | null } | null;
  stage?: React.ReactNode;
  journey?: React.ReactNode;
  plan?: React.ReactNode;
  context?: React.ReactNode;
  agents?: React.ReactNode;
  threadId?: number | null;
  liveRunId?: number | null;
  sandboxId?: string | null;
}) {
  const [pickedEval, setPickedEval] = useState<number | null>(null);
  const [plusOpen, setPlusOpen] = useState(false);
  const [plusQuery, setPlusQuery] = useState('');
  const [plusPos, setPlusPos] = useState<{ top: number; left: number } | null>(null);
  const plusWrap = useRef<HTMLSpanElement>(null);
  const plusMenu = useRef<HTMLDivElement>(null);
  const specs = useLocalSpecs();

  const subject = state.tabs.includes(state.active) ? state.active : 'machine';

  const provenance = paneProvenance(
    subject,
    specs.status === 'ok' ? specs.specs : null,
    { threadId },
  );
  const qualifier = paneQualifier(subject, diagnosis, evals, pickedEval);

  useLayoutEffect(() => {
    if (!plusOpen || !plusWrap.current) {
      setPlusPos(null);
      return;
    }
    const place = () => {
      const rect = plusWrap.current!.getBoundingClientRect();
      const width = 280;
      const left = Math.min(
        Math.max(8, rect.left),
        Math.max(8, window.innerWidth - width - 8),
      );
      setPlusPos({ top: rect.bottom + 4, left });
    };
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [plusOpen]);

  useEffect(() => {
    if (!plusOpen) return;
    const onDoc = (event: MouseEvent) => {
      const target = event.target as Node;
      if (plusWrap.current?.contains(target) || plusMenu.current?.contains(target)) return;
      setPlusOpen(false);
      setPlusQuery('');
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPlusOpen(false);
        setPlusQuery('');
      }
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [plusOpen]);

  const q = plusQuery.trim().toLowerCase();
  const menuRows = PANE_MENU.filter((pane) => {
    if (!q) return true;
    return (
      PANE_TITLE[pane].toLowerCase().includes(q) ||
      TAB_LABEL[pane].toLowerCase().includes(q) ||
      pane.includes(q)
    );
  });

  const plusMenuNode =
    plusOpen && plusPos
      ? createPortal(
          <div
            ref={plusMenu}
            className="inspector__plusmenu inspector__plusmenu--portal"
            role="listbox"
            aria-label="Panes"
            style={{ top: plusPos.top, left: plusPos.left }}
          >
            <input
              className="inspector__plussearch"
              type="search"
              value={plusQuery}
              onChange={(event) => setPlusQuery(event.target.value)}
              placeholder="Search panes…"
              aria-label="Search panes"
              autoFocus
            />
            {menuRows.map((pane) => (
              <button
                key={pane}
                type="button"
                className="inspector__plusrow"
                role="option"
                aria-selected={pane === subject}
                data-current={pane === subject || undefined}
                onClick={() => {
                  setPlusOpen(false);
                  setPlusQuery('');
                  setState(openInspectorTab(state, pane));
                }}
              >
                <Icon name={PANE_ICON[pane]} size={12} />
                <span>{PANE_TITLE[pane]}</span>
              </button>
            ))}
            {menuRows.length === 0 ? (
              <p className="inspector__plusempty">No pane matches</p>
            ) : null}
          </div>,
          document.body,
        )
      : null;

  return (
    <aside
      className="inspector"
      data-tabs={state.tabs.length > 1 ? 'many' : 'one'}
      aria-label={`Inspector — ${PANE_TITLE[subject]}`}
    >
      <button
        type="button"
        className="grabber grabber--stack"
        aria-label="Resize the inspector — Left and Right snap it to a quarter, a third or half the workspace"
        data-snapped={snappedTo !== null ? '' : undefined}
        onPointerDown={onResizeStart}
        onKeyDown={onResizeKey}
      />

      {/* CS19 — larger centered chrome chips; close lives here only. */}
      <div className="inspector__chrome" role="tablist" aria-label="Open panes">
        {state.tabs.map((pane) => (
          <div
            key={pane}
            className="inspector__toptab"
            data-active={pane === subject || undefined}
            role="presentation"
          >
            <button
              type="button"
              role="tab"
              aria-selected={pane === subject}
              className="inspector__toptab-btn"
              title={PANE_TITLE[pane]}
              onClick={() => setState(focusInspectorTab(state, pane))}
            >
              <Icon name={PANE_ICON[pane]} size={14} />
              <span>{TAB_LABEL[pane]}</span>
            </button>
            <button
              type="button"
              className="inspector__toptab-x"
              title={`Close ${PANE_TITLE[pane]}`}
              aria-label={`Close ${PANE_TITLE[pane]}`}
              onClick={() => setState(closeInspectorTab(state, pane))}
            >
              <Icon name="x" size={11} />
            </button>
          </div>
        ))}

        <span className="inspector__plus" ref={plusWrap}>
          <button
            type="button"
            className="inspector__plus-btn"
            aria-expanded={plusOpen}
            aria-label="Open a pane"
            title="Open a pane"
            onClick={() => setPlusOpen((was) => !was)}
          >
            <Icon name="plus" size={13} />
          </button>
        </span>
      </div>
      {plusMenuNode}

      <div className="inspector__card">
        {/* Pop-out + quiet qualifier only — no panel X, no from-GET strip (CS19). */}
        {(qualifier || (canPopOut(subject) && threadId !== null)) ? (
          <header
            className="inspector__head inspector__head--tools"
            title={provenance ?? undefined}
          >
            {canPopOut(subject) && threadId !== null ? (
              <button
                type="button"
                className="inspector__popout"
                title={`Open ${PANE_TITLE[subject]} in its own window, following this thread`}
                aria-label={`Open ${PANE_TITLE[subject]} in its own window`}
                onClick={() => {
                  void nativeOpenPane(subject, threadId).then((opened) => {
                    if (opened) return;
                    window.open(
                      `${window.location.pathname}?pane=${subject}&thread=${threadId}`,
                      `mlh-${subject}-${threadId}`,
                      'width=560,height=760',
                    );
                  });
                }}
              >
                <Icon name="open" size={13} />
              </button>
            ) : null}
            {qualifier ? <span className="inspector__qual">{qualifier}</span> : null}
            <span className="inspector__head-spacer" />
          </header>
        ) : null}

        <div className="inspector__body scroll-y" id={`pane-${subject}`}>
          <PaneBody
            id={subject}
            journey={journey}
            plan={plan}
            context={context}
            agents={agents}
            diagnosis={diagnosis}
            evidence={evidence}
            evals={evals}
            pickedEval={pickedEval}
            onPickEval={setPickedEval}
            onControls={onControls}
            workspace={workspace}
            projectId={workspace?.id ?? null}
            stage={stage}
            liveRunId={liveRunId}
            sandboxId={sandboxId}
          />
        </div>
      </div>
    </aside>
  );
}

function paneQualifier(
  pane: PaneId,
  diagnosis: DiagnosisPayload | null,
  evals: EvalReport[],
  pickedEval: number | null,
): string | null {
  if (pane === 'eval') {
    const shown = currentEvalReport(evals, pickedEval);
    if (!shown) return null;
    return `run ${shown.runId} · ${shown.graded} rows graded`;
  }
  if (pane !== 'evidence' || !diagnosis) return null;
  const passed = FIVE_GATES.filter(
    (gate) => diagnosis.gate_ledger[gate.id]?.status === 'PASSED',
  ).length;
  return `${passed} of ${FIVE_GATES.length} gates passed`;
}
