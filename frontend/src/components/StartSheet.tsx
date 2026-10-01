/**
 * CS7 / CS18 — new-thread start sheet: model/Connect, Plan|Build, permission,
 * project folder. Starter prompts live above the composer (Suggestions), not
 * duplicated here — the blank chat stays one quiet decision strip.
 */

import { useEffect, useState } from 'react';

import { listProjects } from '../lib/engine/client';
import type { Project } from '../lib/engine/types';
import type { PermissionMode } from './PermissionLadder';
import { EmptyState } from './EmptyState';
import { Icon } from './Icon';

export interface StartSheetPrefs {
  mode: 'plan' | 'build';
  permission: PermissionMode;
  projectId: number | null;
}

/** The three rungs, the same ones `ModeSwitch` offers once a thread exists. */
const START_LADDER: {
  id: string;
  label: string;
  mode: 'plan' | 'build';
  permission: PermissionMode;
  title: string;
}[] = [
  {
    id: 'plan',
    label: 'Plan',
    mode: 'plan',
    permission: 'ask',
    title: 'Read-only. It looks things up and writes a plan; it changes nothing.',
  },
  {
    id: 'build',
    label: 'Build',
    mode: 'build',
    permission: 'ask',
    title: 'Works the plan. Anything that spends the card or writes a file asks you first.',
  },
  {
    id: 'full',
    label: 'Full',
    mode: 'build',
    permission: 'full',
    title: 'Works the plan and decides for itself. No approvals, no questions.',
  },
];

export function StartSheet({
  prefs,
  onPrefs,
  onConnect,
  onAssignFolder,
}: {
  prefs: StartSheetPrefs;
  onPrefs: (next: StartSheetPrefs) => void;
  onPrompt: (text: string) => void;
  onConnect: () => void;
  onAssignFolder: (projectId: number) => void;
}) {
  const [projects, setProjects] = useState<Project[]>([]);

  useEffect(() => {
    let live = true;
    listProjects()
      .then((rows) => {
        if (live) setProjects(rows);
      })
      .catch(() => {
        if (live) setProjects([]);
      });
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="empty start-sheet">
      <div className="empty__inner">
        <EmptyState />

        <div className="start-sheet__controls" aria-label="Start this conversation">
          {/* ONE LADDER, NOT TWO PICKERS. Max, 2026-09-19: "When I open a
              thread, I can't put it in full. I have to start in plan." He
              could press Full here, and it did nothing he could see, because
              Mode and Permissions were two controls for one decision and
              `workingModeOf` reads mode FIRST: plan + full is still plan, so
              the chip said Plan and the thread got the plan tool list. It
              only became visible the day the mode default moved to plan.
              `ModeSwitch` has modelled this correctly all along - Plan,
              Build, Full - and this is the same ladder, so the sheet and the
              chip cannot disagree about what was chosen. */}
          <div className="start-sheet__row">
            <span className="start-sheet__label">Mode</span>
            <div className="start-sheet__seg" role="group" aria-label="Mode">
              {START_LADDER.map((rung) => (
                <button
                  key={rung.id}
                  type="button"
                  className="start-sheet__chip"
                  title={rung.title}
                  aria-pressed={
                    prefs.mode === rung.mode && prefs.permission === rung.permission
                  }
                  onClick={() =>
                    onPrefs({ ...prefs, mode: rung.mode, permission: rung.permission })
                  }
                >
                  {rung.label}
                </button>
              ))}
            </div>
          </div>

          <div className="start-sheet__row">
            <span className="start-sheet__label">Project</span>
            <select
              className="start-sheet__select"
              value={prefs.projectId ?? ''}
              onChange={(event) => {
                const raw = event.target.value;
                onPrefs({
                  ...prefs,
                  projectId: raw === '' ? null : Number(raw),
                });
              }}
            >
              <option value="">Default project</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                  {project.root_path ? ` — ${project.root_path}` : ''}
                </option>
              ))}
            </select>
            {prefs.projectId !== null ? (
              <button
                type="button"
                className="start-sheet__folder"
                onClick={() => onAssignFolder(prefs.projectId as number)}
                title="Assign a folder on this machine"
              >
                <Icon name="folder" size={12} />
                Folder
              </button>
            ) : null}
          </div>

          <div className="start-sheet__row start-sheet__row--actions">
            <button type="button" className="start-sheet__connect" onClick={onConnect}>
              <Icon name="key" size={12} />
              Connect a model
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
