/**
 * The left rail, built to Graphite page 17.
 *
 * Page 17 is the one page in the book that draws its subject at forty rows,
 * "because a density claim that is only made in prose is not a claim". Five row
 * types and nothing else:
 *
 *   .railitem    30px   14px icon, one label. No count, no chevron.
 *   .railhead    24px   mono uppercase label, right-aligned 20px actions.
 *   .folder      30px   folder glyph, project name, collapse chevron.
 *   .thread      28px   optional state dot, title, relative timestamp.
 *   .emptyfolder 28px   one phrase in --ink-4. No button, no illustration.
 *   .acct        30px   18px avatar, account name. Pinned below the scroll.
 *
 * WHAT CHANGED, AND WHY EACH THING WAS WRONG BEFORE
 *
 * 1. **It is a tree now, because `projects` exists.** This file used to carry:
 *    "There are no folders, because the `threads` table has no folder column;
 *    the day buckets the engine's `updated_at` already supports stand in their
 *    place." Migration 3 added `projects`, migration 4 added
 *    `threads.project_id`, and `app/main.py` serves all four project routes.
 *    Verified against the running engine, not against `docs/ROADMAP.md`, which
 *    still says the rail is threads-only. Day buckets were a stand-in for a
 *    thing that had not shipped; it has, and they are gone.
 *
 * 2. **The timestamp is relative.** It printed a clock time — "07:14" — which
 *    answers "when". The rail's question is "how recently", and page 17 rules
 *    that "absolute dates belong in the thread, not the rail". The full stamp
 *    is still on the row's `title`, so nothing was taken away.
 *
 * 3. **The thread row lost its icon.** Page 17.2 enumerates what a `.thread` is
 *    allowed to hold — "optional state dot, title, relative timestamp" — and
 *    the specimen draws none. At 280px an icon costs two words of title on
 *    every row for no signal the shape of the row does not already carry.
 *
 * 4. **The section head's count became its two actions.** The count stood where
 *    the reference puts new-folder and filter "because neither of those exists
 *    behind the API yet, and an icon that does nothing is worse than an empty
 *    corner". New folder is `POST /api/projects` now. Filter is a search over
 *    rows this component already holds, which needs no route at all — and page
 *    18 forbids a search field in the top bar precisely because "search is a
 *    rail action".
 *
 * WHAT IS STILL NOT DRAWN, AND WHY. Page 17 shows Automations and Skills beside
 * New thread, and page 39 adds Recipes for enterprise. There is no automations
 * store, no skills registry and no recipe editor behind any of them, and a rail
 * row that looks like a product feature and does nothing is the fixture problem
 * in a different costume. Tools is real — it opens every registered tool as a
 * button — and it keeps the book's `ic-skill` glyph because that is the row it
 * stands in for. There are no run-state dots for the same reason: page 17 draws
 * six hues for six run states, and `GET /api/runs` cannot say which state a
 * thread is in, so every dot would be a colour we invented.
 *
 * SELECTION IS A SHAPE. A fully rounded lighter rectangle at --r-10 filled with
 * --state-selected. Never a left accent bar: it competed with the state dot for
 * the same edge of the same row, and "where I am" is not a claim about the
 * world, which is what the accent is reserved to mean.
 *
 * TWO THINGS MAX ADDED AFTER USING IT.
 *
 * 5. **Hover actions on the thread row**, and the row is a row of controls now
 *    rather than one control. See `ThreadRow` below for what the four are, why
 *    there is one button and not four, and why Delete is drawn and disabled.
 *
 * 6. **Air between groups, and only between groups.** "Make sure there's good
 *    spacing and it's easy to read." Every row height on this page is unchanged
 *    — 30 / 24 / 30 / 28 / 28 / 30, exactly as 17.2 rules — because the rows
 *    were never the problem. What was wrong is that the rail had one gap
 *    between everything: 10px above the section head, 0 below it, 0 between one
 *    project and the next. Three relationships, two values, so nothing grouped.
 *    It is a ladder off page 08's own scale now: --sp-8 between rows, --sp-12
 *    between groups, --sp-16 above a section head, 0 between a label and what
 *    it labels. Compact is not cramped, and nothing got taller.
 */

import { MachineFold } from './MachineFold';
import { useMemo, useRef, useState } from 'react';
import type { Provider, Thread } from '../lib/engine/types';
import type { ActivityRead, ActivityThread } from '../lib/engine/activity';
import type { RailGroup } from '../lib/useThreads';
import { absoluteTime, relativeAge } from '../lib/useThreads';
import { Icon } from './Icon';
import { ContextRing } from './Spinner';
import { MenuButton, type MenuRow } from './Menu';
import { ProvenanceTag } from './primitives';

export function Rail({
  groups,
  count,
  loading,
  error,
  selectedId,
  destinationId,
  provider,
  onSelect,
  onNew,
  onPickProject,
  activity,
  onDuplicateProject,
  onArchiveProject,
  onDeleteProject,
  onOpenPane,
  onAddProject,
  onControls,
  onConnect,
  onResizeStart,
  pinned,
  onTogglePin,
  onRename,
  onArchive,
  onDelete,
}: {
  groups: RailGroup[];
  /** Live threads across every project. Used only to tell "no threads yet"
   *  from "no project matches this filter". */
  count: number;
  loading: boolean;
  error: string | null;
  selectedId: number | null;
  /** Which project a new thread would land in right now. The rail shows it
   *  rather than leaving the user to find out after they have typed. */
  destinationId: number | null;
  provider: Provider | null;
  onSelect: (id: number) => void;
  onNew: () => void;
  /** Aim the composer at this project and start a new thread in it. This is
   *  the ONLY way a thread reaches a project the user made: `POST /api/threads`
   *  files a thread with no `project_id` in `db.default_project()`, so before
   *  this existed a project created in the rail stayed empty forever, however
   *  many threads the user started. */
  onPickProject: (projectId: number) => void;
  /** WHICH CONVERSATIONS ARE WORKING, from the engine (lib/useActivity.ts).
   *  Max, 2026-09-13: "if I have a session running now when I switch to
   *  another chat, I want to see a spinner or something... so you see which
   *  chats are working, their context windows." */
  activity: ActivityRead;
  onDuplicateProject: (projectId: number) => void;
  /** ARCHIVE A FOLDER. The engine has had `POST /api/projects/{id}/archive`
   *  and the client has had `archiveProject` for weeks; nothing called it.
   *  The owner, 2026-09-11: "add a way to remove or archive past
   *  conversations - the actual folders." Archiving, not deleting, for
   *  the same reason a thread archives: nothing is destroyed, it leaves
   *  the rail. */
  onArchiveProject: (projectId: number) => void;
  /** DELETE A FOLDER. The other door, 2026-09-12: "old projects that people
   *  really don't work with aren't just infinitely archived adding space,
   *  but they are deleted and removed." The engine removes the project, its
   *  threads, its memory and its ledger rows; the folder on disk is the
   *  person's and is not touched. 409 for the last live project. */
  onDeleteProject: (projectId: number) => Promise<void>;
  /** For the machine chip in the foot. */
  onOpenPane: (pane: string) => void;
  onAddProject: (name: string) => Promise<unknown>;
  onControls: () => void;
  onConnect: () => void;
  onResizeStart: (event: React.PointerEvent) => void;
  /** Thread ids pinned to the top of their folder. */
  pinned: ReadonlySet<number>;
  onTogglePin: (threadId: number) => void;
  onRename: (threadId: number, title: string) => Promise<void>;
  onArchive: (threadId: number) => Promise<void>;
  /** The other door. Removes the thread and every row keyed to it. */
  onDelete: (threadId: number) => Promise<void>;
}) {
  /* Collapse is per project and lives here. It is not persisted: a collapsed
     folder is a reading position, not a preference, and a rail that reopens
     tomorrow with yesterday's folders shut hides work rather than tidying it. */
  const [collapsed, setCollapsed] = useState<ReadonlySet<number>>(new Set());
  const [query, setQuery] = useState<string | null>(null);
  /* SELECT SEVERAL, DELETE ONCE. Max, 2026-09-12: "add a little thing on the
     left side rail so that you can select multiple chats at once and then
     click delete all, because right now it's really hard to do one by one."
     Selecting is a mode of the rail: rows become checkboxes, the menu
     buttons step aside, and one bar at the bottom names the count and the
     door. Not persisted - a selection is a moment, not a preference. */
  const [selecting, setSelecting] = useState(false);
  const [picked, setPicked] = useState<ReadonlySet<number>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const togglePicked = (threadId: number) =>
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(threadId)) next.delete(threadId);
      else next.add(threadId);
      return next;
    });
  const stopSelecting = () => {
    setSelecting(false);
    setPicked(new Set());
  };
  const deletePicked = async () => {
    const ids = [...picked];
    if (ids.length === 0 || deleting) return;
    if (
      !window.confirm(
        `Delete ${ids.length} thread${ids.length === 1 ? '' : 's'}? Every message, event and attachment record in them is removed for good. Files on disk are not touched.`,
      )
    ) {
      return;
    }
    setDeleting(true);
    try {
      for (const id of ids) {
        await onDelete(id);
      }
      stopSelecting();
    } catch (failure) {
      window.alert(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setDeleting(false);
    }
  };
  const [naming, setNaming] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);

  /* One clock reading per render, shared by every row, so a column of forty
     timestamps is forty readings of the same instant rather than forty
     instants a millisecond apart. */
  const now = new Date();

  const needle = (query ?? '').trim().toLowerCase();
  const shown = useMemo(() => {
    /* PINNED SORTS ABOVE, INSIDE ITS OWN FOLDER AND NOT ACROSS THEM. A global
       pinned section would take a thread out of the project that owns it, and
       the project is the root of this product's structure — a row that has
       left its folder can no longer be read as belonging to anything. The
       engine's order is preserved inside each half, so pinning reorders and
       never re-sorts. */
    const pin = (list: Thread[]) =>
      pinned.size === 0
        ? list
        : [
            ...list.filter((thread) => pinned.has(thread.id)),
            ...list.filter((thread) => !pinned.has(thread.id)),
          ];
    if (!needle) {
      return groups.map((group) => ({ ...group, threads: pin(group.threads) }));
    }
    return groups
      .map((group) => ({
        ...group,
        threads: pin(
          group.threads.filter((thread) =>
            thread.title.toLowerCase().includes(needle),
          ),
        ),
      }))
      /* While a filter is running an empty folder means "nothing here matched",
         which is not what page 17's "No threads" says. Hiding it is honest; the
         rule about an empty folder saying so in words governs a folder that is
         genuinely empty, and that case is untouched below. */
      .filter((group) => group.threads.length > 0);
  }, [groups, needle, pinned]);

  const matched = shown.reduce((total, group) => total + group.threads.length, 0);

  return (
    <nav className="rail" aria-label="Projects and threads">
      {/* The brand row the Letter book draws at the top of its rail (page 14):
          the solid H mark and the wordmark in the script face. The book's rail
          says "Harness", not "ML Harness" — the wordmark is a word. */}
      <div className="rail__top">
        <Icon name="mark" size={16} />
        <span className="wordmark">Harness</span>
      </div>

      <div className="rail__scroll">
        <button type="button" className="railitem railitem--strong" onClick={onNew}>
          <Icon name="newthread" />
          <span>New thread</span>
        </button>
        <button
          type="button"
          className="railitem"
          onClick={onControls}
          title="Every tool the harness has, as buttons"
        >
          <Icon name="skill" />
          <span>Tools</span>
        </button>

        <div className="railhead">
          <span>Threads</span>
          {/* 20px, and this is the only place in the product where a control is
              drawn below 26px. Page 17.2: they sit against a 10px uppercase
              label, and a 26px control beside it would out-weigh the thing it
              labels. */}
          <span className="railhead__acts">
            <button
              type="button"
              aria-label="New project"
              title="New project"
              aria-expanded={naming}
              onClick={() => {
                setNameError(null);
                setNaming((open) => !open);
              }}
            >
              <Icon name="folderplus" size={12} />
            </button>
            <button
              type="button"
              aria-label="Filter threads"
              title="Filter threads"
              aria-pressed={query !== null}
              onClick={() => setQuery((current) => (current === null ? '' : null))}
            >
              <Icon name="filter" size={12} />
            </button>
            <button
              type="button"
              aria-label="Select threads"
              title="Select several threads, then delete them at once"
              aria-pressed={selecting}
              onClick={() => (selecting ? stopSelecting() : setSelecting(true))}
            >
              <Icon name="check" size={12} />
            </button>
          </span>
        </div>

        {query !== null ? (
          <RailFilter
            value={query}
            onChange={setQuery}
            onClose={() => setQuery(null)}
          />
        ) : null}

        {naming ? (
          <NewProject
            onSubmit={async (name) => {
              try {
                await onAddProject(name);
                setNaming(false);
                setNameError(null);
              } catch (failure) {
                setNameError(
                  failure instanceof Error ? failure.message : String(failure),
                );
              }
            }}
            onCancel={() => {
              setNaming(false);
              setNameError(null);
            }}
            error={nameError}
          />
        ) : null}

        {error ? (
          <div className="rail__empty rail__empty--wrap">
            The rail could not read the engine: <span className="mono">{error}</span>
          </div>
        ) : null}

        {!error && loading ? <div className="rail__empty">Reading…</div> : null}

        {!error && !loading && groups.length === 0 ? (
          <div className="rail__empty">No projects yet — one starts when you send.</div>
        ) : null}

        {!error && !loading && needle && matched === 0 && count > 0 ? (
          <div className="rail__empty">
            Nothing in {count} thread{count === 1 ? '' : 's'} matches that.
          </div>
        ) : null}

        {shown.map((group) => {
          const id = group.project?.id ?? -1;
          const shut = collapsed.has(id);
          /* "A new thread starts here." Shown only while no thread is open,
             which is the only moment the destination is a live question — and
             it keeps the rail to one highlighted row. */
          const aimed =
            selectedId === null &&
            group.project != null &&
            group.project.id === destinationId;
          return (
            /* A project is a GROUP, and the class says so, because the air
               between one group and the next is now a real value rather than
               the zero that fell out of two divs touching. */
            <div className="rail__group" key={id}>
              <div className="folderline">
                <button
                  type="button"
                  className="folderrow"
                  aria-current={aimed}
                  disabled={group.project == null}
                  onClick={() => {
                    if (group.project) onPickProject(group.project.id);
                  }}
                  title={
                    group.project
                      ? `Start a thread in ${group.label} · ${group.threads.length} thread${
                          group.threads.length === 1 ? '' : 's'
                        }`
                      : 'Threads whose project is archived or missing'
                  }
                >
                  <Icon name="folder" />
                  <span className="folderrow__name">{group.label}</span>
                </button>
                {group.project ? (
                  <button
                    type="button"
                    className="folderline__cv"
                    aria-label={`Duplicate ${group.label}`}
                    title="Duplicate project - same folder, fresh thread history"
                    onClick={() => onDuplicateProject(group.project!.id)}
                  >
                    <Icon name="folderplus" size={12} />
                  </button>
                ) : null}
                {group.project ? (
                  <button
                    type="button"
                    className="folderline__cv"
                    aria-label={`Archive ${group.label}`}
                    title="Archive this folder - it leaves the rail; nothing is deleted"
                    onClick={() => {
                      if (window.confirm(`Archive ${group.label}? It leaves the rail. Nothing is deleted.`)) {
                        onArchiveProject(group.project!.id);
                      }
                    }}
                  >
                    <Icon name="download" size={12} />
                  </button>
                ) : null}
                {group.project ? (
                  <button
                    type="button"
                    className="folderline__cv folderline__cv--danger"
                    aria-label={`Delete ${group.label}`}
                    title="Delete this folder - every thread in it, its memory and its ledger rows are removed. The folder on disk is not touched."
                    onClick={() => {
                      if (
                        window.confirm(
                          `Delete ${group.label}? Every thread in it (${group.threads.length}), its memory and its ledger rows are removed for good. The folder on disk is not touched.`,
                        )
                      ) {
                        void onDeleteProject(group.project!.id).catch((failure: unknown) =>
                          window.alert(failure instanceof Error ? failure.message : String(failure)),
                        );
                      }
                    }}
                  >
                    <Icon name="x" size={12} />
                  </button>
                ) : null}
                {/* The chevron is the collapse control, which is what page 17.2
                    names it: ".folder — folder glyph, project name, collapse
                    chevron at .cv". It is its own 20px button rather than the
                    whole row, because the row now has a second thing to say and
                    a row cannot answer two questions with one click. */}
                <button
                  type="button"
                  className="folderline__cv"
                  aria-expanded={!shut}
                  aria-label={shut ? `Expand ${group.label}` : `Collapse ${group.label}`}
                  onClick={() =>
                    setCollapsed((current) => {
                      const next = new Set(current);
                      if (next.has(id)) next.delete(id);
                      else next.add(id);
                      return next;
                    })
                  }
                >
                  {/* One glyph pointed two ways rather than two glyphs that can
                      disagree about weight. */}
                  <Icon name="chevright" size={12} rotate={shut ? 0 : 90} />
                </button>
              </div>

              {shut ? null : group.threads.length === 0 ? (
                /* Page 17, rule 7: "A project with no threads renders one 28px
                   row reading 'No threads' — not a dashed box, not an
                   illustration, not a call to action. Inside a 280px rail it
                   would cost six threads to say nothing." */
                <div className="emptyfolder">No threads</div>
              ) : (
                <div className="threads">
                  {nested(group.threads).map((thread) => (
                    <ThreadRow
                      key={thread.id}
                      thread={thread}
                      now={now}
                      selected={thread.id === selectedId}
                      pinned={pinned.has(thread.id)}
                      onSelect={onSelect}
                      onTogglePin={onTogglePin}
                      onRename={onRename}
                      onArchive={onArchive}
                      onDelete={onDelete}
                      activity={activity.threads.find((each) => each.thread_id === thread.id) ?? null}
                      selecting={selecting}
                      picked={picked.has(thread.id)}
                      onPick={togglePicked}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* THE MACHINE, above the foot and never in it. Max, 2026-09-11: "remove
          the pc thing from bottom left it should be setting as it used to be
          as well - and then the nvidia local lab thing / gpu available /
          compute available, should be from the sidebar drop down and
          expandable." See components/MachineFold.tsx. */}
      {selecting ? (
        <div className="railselect">
          <span className="railselect__count num">
            {picked.size} selected
          </span>
          <button
            type="button"
            className="btn btn--sm btn--danger"
            disabled={picked.size === 0 || deleting}
            onClick={() => void deletePicked()}
          >
            {deleting ? 'Deleting…' : `Delete ${picked.size || ''}`.trim()}
          </button>
          <button type="button" className="btn btn--sm btn--ghost" onClick={stopSelecting}>
            Cancel
          </button>
        </div>
      ) : null}

      <MachineFold onOpenPane={onOpenPane} />

      {/* The foot, as page 17.4 draws its third variant: "the honest version of
          'bring your own model' — the thing you lent us is named in the same row
          as the account, tagged Declared because you told us what it is and we
          did not measure it." We ship no AI, so this is the closest thing this
          product has to an account row. It never scrolls, and it is the
          settings door (App.tsx, `onConnect`). */}
      <div className="rail__foot">
        <button type="button" className="acct" onClick={onConnect}>
          <span className="avatar">
            <Icon name="key" size={12} />
          </span>
          <span className="acct__name" data-mono={provider ? 'true' : undefined}>
            {provider ? provider.model : 'No model connected'}
          </span>
        </button>
        {provider ? <ProvenanceTag tag="DECLARED" /> : null}
      </div>

      <button
        type="button"
        className="grabber grabber--rail"
        aria-label="Resize the rail"
        onPointerDown={onResizeStart}
      />
    </nav>
  );
}

/* ── The thread row, and the four things you can do to one ────────────────
   MAX, AFTER USING IT: "it gets too much, sometimes people can get
   overwhelmed, so you should be able to edit when you hover. Usually just a
   codex: when you hover a chat session on the left sidebar, you can edit, you
   can delete" — plus pin and archive.

   ONE CONTROL ON HOVER, NOT FOUR. Four 26px buttons is 104px of a 280px rail,
   which is most of a thread title, on every row. Codex puts one overflow
   button where the timestamp is and opens a menu, and page 14.4 already has
   the menu: "a list of things you can do to one object... rows are the rail's
   own 30px icon-and-label row, because the rail is a menu."

   THE TIMESTAMP IS WHAT IT REPLACES. The two never both draw: page 17.3 gives
   the thread row three signals in three channels and adding a fourth object to
   the right edge would break the alignment of the mono age column, which is
   the thing that lets forty rows read as one axis.

   RENAME HAPPENS IN THE ROW. A dialog for a title is heavier than the title.
   The row becomes a field at the same 28px, so nothing under it moves.

   DELETE IS DRAWN AND DISABLED, WITH THE REASON. There is no delete route in
   this engine — `app/events.py archive_thread` says why in as many words:
   "Not deletion. The transcript is the artifact; archiving takes a thread out
   of the rail and leaves every message and every event exactly where they
   are." Page 14.5's Do/Don't rules that an unavailable action is shown
   disabled in place with its reason and never silently removed, "which is the
   only thing that lets them change it". So it is there, it is off, and it says
   what would have to exist. It is not wired to archive wearing another name. */

/** The group's threads with each sub-agent moved under the conversation that
 *  sent it out, in the order they were handed out.
 *
 *  Max, 2026-09-14: *"have the sub-agents pop up under and indented from the
 *  chat on the rail, so that if the chat moves up you can see on the side rail
 *  how many sub-agents are running."* They were already in the rail - a
 *  sub-agent IS a conversation - but as flat siblings sorted by recency, which
 *  puts them ABOVE the parent that made them and reads as three unrelated
 *  chats. Nesting is the whole difference between "what are these" and "that
 *  one sent these two out".
 *
 *  A child whose parent is in another project, or archived out of this group,
 *  stays where it is rather than disappearing: the rail's job is to show every
 *  thread, and a row that vanishes because its parent is filtered away is a
 *  conversation a person cannot reach.
 */
export function nested(threads: Thread[]): Thread[] {
  const here = new Set(threads.map((one) => one.id));
  const children = new Map<number, Thread[]>();
  for (const thread of threads) {
    const parent = thread.subagent_of ?? null;
    if (parent === null || !here.has(parent)) continue;
    const kin = children.get(parent) ?? [];
    kin.push(thread);
    children.set(parent, kin);
  }
  const out: Thread[] = [];
  for (const thread of threads) {
    const parent = thread.subagent_of ?? null;
    if (parent !== null && here.has(parent)) continue;
    out.push(thread);
    /* Oldest first under a parent: the phases were handed out in order and
       reading them newest-first tells the story backwards. */
    for (const child of (children.get(thread.id) ?? []).slice().reverse()) {
      out.push(child);
    }
  }
  return out;
}

function ThreadRow({
  thread,
  now,
  selected,
  pinned,
  onSelect,
  onTogglePin,
  onRename,
  onArchive,
  onDelete,
  activity,
  selecting,
  picked,
  onPick,
}: {
  thread: Thread;
  now: Date;
  selected: boolean;
  pinned: boolean;
  onSelect: (id: number) => void;
  onTogglePin: (id: number) => void;
  onRename: (id: number, title: string) => Promise<void>;
  onArchive: (id: number) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  /** This thread's work, when it has any: a turn in flight, a run taking
   *  turns, and what its last prompt cost. `null` when it is idle. */
  activity: ActivityThread | null;
  /** The rail's select mode: the row is a checkbox and its menu steps aside. */
  selecting: boolean;
  picked: boolean;
  onPick: (id: number) => void;
}) {
  const [menu, setMenu] = useState(false);
  const [mode, setMode] = useState<'row' | 'rename' | 'archive' | 'delete'>('row');
  const [draft, setDraft] = useState(thread.title);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fail = (failure: unknown) =>
    setError(failure instanceof Error ? failure.message : String(failure));

  const rows: MenuRow[] = [
    { id: 'rename', label: 'Rename', icon: 'newthread' },
    {
      id: 'pin',
      label: pinned ? 'Unpin' : 'Pin to the top',
      icon: 'pin',
    },
    /* `download` is the tray-and-arrow glyph. The Artifacts pane uses it too;
       both mean "into a store", they never appear on one surface, and page 09
       reserves drawing a fifty-ninth icon for a meaning the sheet does not
       already carry. */
    { id: 'archive', label: 'Archive', icon: 'download' },
    /* Live since 2026-09-12: `DELETE /api/threads/{id}`. The row used to be
       disabled in place with the engine's own reason; the engine has a
       position on it now, and so does the confirm below. */
    {
      id: 'delete',
      label: 'Delete this thread',
      icon: 'x',
      destructive: true,
    },
  ];

  if (mode === 'rename') {
    return (
      <>
        <div className="railfield railfield--inrow">
          <input
            autoFocus
            className="railfield__input"
            aria-label={`Rename ${thread.title}`}
            value={draft}
            disabled={busy}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={() => {
              if (!busy) setMode('row');
            }}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                setMode('row');
                setDraft(thread.title);
              }
              if (event.key === 'Enter') {
                event.preventDefault();
                if (!draft.trim() || busy) return;
                setBusy(true);
                onRename(thread.id, draft)
                  .then(() => setMode('row'))
                  .catch(fail)
                  .finally(() => setBusy(false));
              }
            }}
          />
        </div>
        {error ? <div className="rail__empty rail__empty--wrap">{error}</div> : null}
      </>
    );
  }

  return (
    <>
      <div
        className="threadrow"
        data-current={selected || undefined}
        data-open={menu || undefined}
        /* A SUB-AGENT IS INDENTED AND GOLD, the same two signals the strip
           above the chat box uses, so the two surfaces are describing one
           thing. `data-working` is the sub-agent's OWN state rather than the
           row's: a child that has finished keeps its indent and loses its
           colour, which is how a person sees at a glance how many are still
           out. */
        data-subagent={thread.subagent_of ? thread.subagent_state || 'done' : undefined}
        title={thread.subagent_phase ? `sub-agent working "${thread.subagent_phase}"` : undefined}
      >
        <button
          type="button"
          className="threadrow__open"
          aria-current={selected}
          role={selecting ? 'checkbox' : undefined}
          aria-checked={selecting ? picked : undefined}
          onClick={() => (selecting ? onPick(thread.id) : onSelect(thread.id))}
          title={`${thread.title}\nLast active ${absoluteTime(thread.updated_at)}`}
        >
          {selecting ? (
            <span className="threadrow__pick" data-on={picked || undefined} aria-hidden="true">
              {picked ? <Icon name="check" size={10} /> : null}
            </span>
          ) : null}
          {/* CS20 — rail keeps the context dial only; ASCII spin lives on
              Thinking + GoalBar. Working is the title's accent shimmer. */}
          {activity && !selecting && activity.tokens && activity.window ? (
            <span
              className="threadrow__working"
              title={
                (activity.run
                  ? `a run is working this plan - turn ${activity.run.turns} of ${activity.run.cap}`
                  : 'a turn is running in this conversation') +
                ` · last prompt ${activity.tokens.toLocaleString()} of ${activity.window.toLocaleString()} tokens`
              }
            >
              <ContextRing share={activity.tokens / activity.window} size={10} />
            </span>
          ) : null}
          {/* Pinned is a shape on the left, so it cannot be confused with the
              run-state dot the book reserves for that position. */}
          {pinned && !selecting && !activity ? <Icon name="pin" size={12} /> : null}
          {/* Titles truncate and never wrap: a wrapped title turns one 28px row
              into two and destroys the arithmetic the whole rail is built on. */}
          <span
            className="threadrow__title"
            data-working={activity && !selecting ? true : undefined}
          >
            {thread.title}
          </span>
        </button>
        {/* The timestamp is never truncated — a row that has lost its recency
            has lost the reason it is above another. */}
        <span className="threadrow__age">{relativeAge(thread.updated_at, now)}</span>
        {selecting ? null : (
        <MenuButton
          className="threadrow__more"
          label={`Actions for ${thread.title}`}
          align="end"
          minWidth={196}
          open={menu}
          setOpen={setMenu}
          rows={rows}
          onChoose={(id) => {
            if (id === 'rename') {
              setDraft(thread.title);
              setError(null);
              setMode('rename');
            } else if (id === 'pin') {
              onTogglePin(thread.id);
            } else if (id === 'archive') {
              setError(null);
              setMode('archive');
            } else if (id === 'delete') {
              setError(null);
              setMode('delete');
            }
          }}
        >
          <Icon name="more" size={14} />
        </MenuButton>
        )}
      </div>

      {/* ARCHIVE ASKS FIRST, AND THE ASKING IS WHERE THE HONESTY GOES. It is
          not destructive in the database and it IS destructive in this
          interface, because nothing here reads `include_archived` yet — so the
          sentence says both halves rather than the reassuring one. */}
      {mode === 'archive' ? (
        <div className="railconfirm">
          <p className="railconfirm__body">
            Archive this thread? It leaves the rail. Nothing is deleted — every
            message and event stays — but this interface has no way to bring it
            back yet.
          </p>
          <div className="railconfirm__acts">
            <button
              type="button"
              className="btn btn--sm"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                onArchive(thread.id)
                  .catch(fail)
                  .finally(() => {
                    setBusy(false);
                    setMode('row');
                  });
              }}
            >
              Archive
            </button>
            <button
              type="button"
              className="btn btn--sm btn--ghost"
              onClick={() => setMode('row')}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
      {/* DELETE ASKS TOO, AND SAYS THE OTHER HALF: this one IS destructive in
          the database. What survives is one line in the ledger. */}
      {mode === 'delete' ? (
        <div className="railconfirm">
          <p className="railconfirm__body">
            Delete this thread? Every message, event and attachment record in
            it is removed for good. Files on disk are not touched.
          </p>
          <div className="railconfirm__acts">
            <button
              type="button"
              className="btn btn--sm btn--danger"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                onDelete(thread.id)
                  .catch(fail)
                  .finally(() => {
                    setBusy(false);
                    setMode('row');
                  });
              }}
            >
              Delete
            </button>
            <button
              type="button"
              className="btn btn--sm btn--ghost"
              onClick={() => setMode('row')}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
      {error ? <div className="rail__empty rail__empty--wrap">{error}</div> : null}
    </>
  );
}

/* ── The two section-head actions, as rows ────────────────────────────────
   Both open into the scroll rather than into a popover. A popover over a 280px
   rail covers the thing it is filtering, and page 14 reserves popovers for
   content that has somewhere else to be. */

function RailFilter({
  value,
  onChange,
  onClose,
}: {
  value: string;
  onChange: (next: string) => void;
  onClose: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="railfield">
      <Icon name="search" size={12} />
      <input
        ref={input}
        autoFocus
        className="railfield__input"
        placeholder="Filter threads"
        aria-label="Filter threads by title"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape') onClose();
        }}
      />
      <button type="button" className="railfield__x" aria-label="Clear filter" onClick={onClose}>
        <Icon name="x" size={12} />
      </button>
    </div>
  );
}

function NewProject({
  onSubmit,
  onCancel,
  error,
}: {
  onSubmit: (name: string) => Promise<unknown>;
  onCancel: () => void;
  error: string | null;
}) {
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  const commit = async () => {
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      await onSubmit(name);
      setName('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="railfield">
        <Icon name="folder" size={12} />
        <input
          autoFocus
          className="railfield__input"
          placeholder="Project name"
          aria-label="New project name"
          value={name}
          disabled={busy}
          onChange={(event) => setName(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              void commit();
            }
            if (event.key === 'Escape') onCancel();
          }}
        />
        <button type="button" className="railfield__x" aria-label="Cancel" onClick={onCancel}>
          <Icon name="x" size={12} />
        </button>
      </div>
      {/* The engine's own words. `POST /api/projects` validates `portal`
          against db.PORTALS and archiving refuses the last live project with a
          sentence worth printing verbatim. */}
      {error ? <div className="rail__empty rail__empty--wrap">{error}</div> : null}
    </>
  );
}
