/**
 * The rail's contents: real projects off `GET /api/projects` and real threads
 * off `GET /api/threads`.
 *
 * THE FILE NAME STAYS `useThreads.ts` ON PURPOSE. `docs/ROADMAP.md` step 1.20
 * names it, and a path in a plan that no longer resolves costs more than a name
 * that is one word narrow. What changed is what it holds: the rail's top level
 * is the project list — `docs/ARCHITECTURE.md` §5.1 makes a project the root —
 * so this hook owns both lists and the grouping between them.
 *
 * WHY BOTH IN ONE HOOK, AND WHY ONE REQUEST FOR THE THREADS. `GET /api/threads`
 * takes an optional `project_id`, so a tree could be fetched folder by folder.
 * It is not: six projects would be seven requests, the folders would populate
 * at seven different moments, and a thread whose project was archived between
 * two of them would appear in none of the responses. One unfiltered read plus
 * one project read is two requests that describe one instant.
 *
 * `GET /api/runs` is still deliberately not called: it returns the legacy
 * run-tracker shape with no `kind`, no lifecycle `status` and no `archived_at`,
 * so a run row built from it would be a real row wearing a design it cannot
 * satisfy. That is also why no thread row carries a run-state dot.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  archiveProject,
  archiveThread,
  deleteProject,
  deleteThread,
  createProject,
  listProjects,
  listThreads,
  renameThread,
} from './engine/client';
import type { Project, Thread } from './engine/types';

/** One folder in the rail: a project and the threads that point at it. */
export interface RailGroup {
  project: Project | null;
  /** Present only on the unfiled group, which has no project row to name. */
  label: string;
  threads: Thread[];
}

export interface ThreadsState {
  projects: Project[];
  threads: Thread[];
  /** Projects in the engine's order, each with its threads in the engine's
   *  order, plus — only when it is non-empty — a group for threads whose
   *  project is not in the live list. */
  groups: RailGroup[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  /** `POST /api/projects`, then a refresh. Rejects with the engine's own
   *  message so the rail can print what it actually said. */
  /** Create a project and return it, so the caller can aim the composer at
   *  the thing the user just made rather than at the engine's default. */
  addProject: (name: string, rootPath?: string | null) => Promise<Project>;
  /** `POST /api/threads/{id}/rename`, then a refresh. The engine moves
   *  `updated_at` too, so the row it renames also moves to the top of its
   *  folder — which is `events.rename_thread`'s own documented behaviour and
   *  not something this hook re-sorts for. */
  rename: (threadId: number, title: string) => Promise<void>;
  /** `POST /api/threads/{id}/archive`, then a refresh. Not deletion:
   *  `GET /api/threads` stops returning the row and every message and event
   *  stays exactly where it was. */
  archive: (threadId: number) => Promise<void>;
  archiveProject: (projectId: number) => Promise<void>;
  /** The other door. Removes the rows; nothing on disk. */
  remove: (threadId: number) => Promise<void>;
  removeProject: (projectId: number) => Promise<void>;
  /** Thread ids the user has pinned to the top of their folder.
   *
   *  LOCAL, AND THAT IS A REPORTED GAP RATHER THAN A DESIGN. The `threads`
   *  table has no `pinned` column and no route sets one, so this is held in
   *  localStorage exactly as the transcript density is — a reading preference
   *  the engine does not know about. It follows the machine, not the thread,
   *  and a second machine will not see it. */
  pinned: ReadonlySet<number>;
  togglePin: (threadId: number) => void;
}

const PIN_KEY = 'mlh.pinnedThreads';

function readPins(): Set<number> {
  try {
    const raw = JSON.parse(localStorage.getItem(PIN_KEY) ?? '[]');
    return new Set(Array.isArray(raw) ? raw.filter((n) => typeof n === 'number') : []);
  } catch {
    return new Set();
  }
}

export function useThreads(): ThreadsState {
  const [projects, setProjects] = useState<Project[]>([]);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      /* Both, together. A tree drawn from a project list read at one moment and
         a thread list read at another can show a folder that has just been
         archived holding threads that have just moved out of it. */
      const [nextProjects, nextThreads] = await Promise.all([
        listProjects(),
        listThreads(),
      ]);
      setProjects(nextProjects);
      setThreads(nextThreads);
      setError(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const addProject = useCallback(
    async (name: string, rootPath?: string | null) => {
      const project = await createProject(
        name.trim(),
        rootPath ? { root_path: rootPath } : {},
      );
      await refresh();
      return project;
    },
    [refresh],
  );

  /* Memoised because the rail filters over it: `groupThreads` returns a fresh
     array every call, so an un-memoised value would defeat every `useMemo`
     downstream that lists it as a dependency. */
  const groups = useMemo(
    () => groupThreads(projects, threads),
    [projects, threads],
  );

  const rename = useCallback(
    async (threadId: number, title: string) => {
      await renameThread(threadId, title.trim());
      await refresh();
    },
    [refresh],
  );

  const archive = useCallback(
    async (threadId: number) => {
      await archiveThread(threadId);
      await refresh();
    },
    [refresh],
  );

  const archiveProjectNow = useCallback(
    async (projectId: number) => {
      await archiveProject(projectId);
      await refresh();
    },
    [refresh],
  );

  const remove = useCallback(
    async (threadId: number) => {
      await deleteThread(threadId);
      await refresh();
    },
    [refresh],
  );

  const removeProject = useCallback(
    async (projectId: number) => {
      await deleteProject(projectId);
      await refresh();
    },
    [refresh],
  );

  const [pinned, setPinned] = useState<ReadonlySet<number>>(readPins);
  const togglePin = useCallback((threadId: number) => {
    setPinned((current) => {
      const next = new Set(current);
      if (next.has(threadId)) next.delete(threadId);
      else next.add(threadId);
      localStorage.setItem(PIN_KEY, JSON.stringify([...next]));
      return next;
    });
  }, []);

  return {
    projects,
    threads,
    groups,
    loading,
    error,
    refresh,
    addProject,
    rename,
    archive,
    archiveProject: archiveProjectNow,
    remove,
    removeProject,
    pinned,
    togglePin,
  };
}

/**
 * Projects, each with its threads, in the order the engine returned both.
 *
 * A thread whose `project_id` matches no live project gets an **Unfiled** group
 * rather than being dropped. That is not defensive padding: archiving a project
 * leaves its threads pointing at it and `GET /api/projects` stops returning it,
 * so without this a user who archives a folder watches every conversation
 * inside it disappear from the rail while it is still in the database. The
 * group only exists when something is in it.
 */
export function groupThreads(
  projects: Project[],
  threads: Thread[],
): RailGroup[] {
  const byProject = new Map<number, Thread[]>();
  for (const project of projects) byProject.set(project.id, []);

  const unfiled: Thread[] = [];
  for (const thread of threads) {
    const bucket =
      thread.project_id === null ? undefined : byProject.get(thread.project_id);
    if (bucket) bucket.push(thread);
    else unfiled.push(thread);
  }

  const groups: RailGroup[] = projects.map((project) => ({
    project,
    label: project.name,
    threads: byProject.get(project.id) ?? [],
  }));
  if (unfiled.length > 0) {
    groups.push({ project: null, label: 'Unfiled', threads: unfiled });
  }
  return groups;
}

/**
 * `updated_at` as a **relative** age, which is what Graphite page 17 puts on
 * every thread row: "4h", "2h", "1d", "1w".
 *
 * This replaces the clock time the rail used to print. A clock time answers
 * "when" and the rail's question is "how recently" — and page 17 rules that
 * "absolute dates belong in the thread, not the rail". It is also the only
 * format that stays one column wide in mono, which is what lets a column of
 * forty of them read as one axis.
 *
 * SQLite writes `CURRENT_TIMESTAMP` as `YYYY-MM-DD HH:MM:SS` in **UTC** with no
 * zone marker, which `Date.parse` reads as local time — so a thread written
 * this morning can read as a day old on a machine west of Greenwich. The `Z` is
 * appended rather than assumed away.
 */
export function relativeAge(stamp: string, now: Date = new Date()): string {
  const parsed = parseStamp(stamp);
  if (parsed === null) return '';
  const seconds = Math.max(0, (now.getTime() - parsed.getTime()) / 1000);
  if (seconds < 60) return 'now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  const weeks = Math.floor(days / 7);
  if (weeks < 53) return `${weeks}w`;
  return `${Math.floor(days / 365)}y`;
}

/** The full timestamp, for the row's `title`. The rail shows the relative age;
 *  the absolute one is still reachable without opening the thread, which is
 *  what stops "2w" being the only thing a person can ever learn. */
export function absoluteTime(stamp: string): string {
  const parsed = parseStamp(stamp);
  return parsed === null ? '' : parsed.toLocaleString();
}

function parseStamp(stamp: string): Date | null {
  const parsed = new Date(`${stamp.replace(' ', 'T')}Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}
