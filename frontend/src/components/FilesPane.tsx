/**
 * THE FILES PANE — the project's folder, readable and editable where Machine is.
 *
 * CS19: listing stays beside the open file (mini VS Code). Pretty = rendered
 * Markdown (or JSON pretty); Source = editable mono. No from-GET status strip.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  listWorkspaceFiles,
  readWorkspaceFile,
  saveWorkspaceFile,
  type WorkspaceFile,
  type WorkspaceListing,
} from '../lib/engine/client';
import { Button, Strip } from './primitives';
import { Icon } from './Icon';
import { Markdown } from './Transcript';

export function FilesPane({
  workspace,
}: {
  workspace: { id: number; name: string; root: string | null } | null;
}) {
  const [listing, setListing] = useState<WorkspaceListing | null>(null);
  const [listingError, setListingError] = useState<string | null>(null);
  const [open, setOpen] = useState<WorkspaceFile | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);
  const [mode, setMode] = useState<'pretty' | 'source'>('pretty');
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveNote, setSaveNote] = useState<{ text: string; failed: boolean } | null>(null);

  const projectId = workspace?.id ?? null;
  const editing = mode === 'source';

  const refresh = useCallback(async () => {
    if (projectId === null) return;
    setListingError(null);
    try {
      setListing(await listWorkspaceFiles(projectId));
    } catch (failure) {
      setListing(null);
      setListingError(failure instanceof Error ? failure.message : String(failure));
    }
  }, [projectId]);

  useEffect(() => {
    setOpen(null);
    setMode('pretty');
    setSaveNote(null);
    void refresh();
  }, [refresh]);

  const openFile = async (path: string) => {
    if (
      open &&
      editing &&
      draft !== open.content &&
      !window.confirm('Discard the unsaved edit and open another file?')
    ) {
      return;
    }
    setOpenError(null);
    setSaveNote(null);
    setMode('pretty');
    try {
      const file = await readWorkspaceFile(projectId as number, path);
      setOpen(file);
      setDraft(file.content);
    } catch (failure) {
      setOpen(null);
      setOpenError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  const save = async () => {
    if (!open || projectId === null || saving) return;
    setSaving(true);
    setSaveNote(null);
    try {
      const wrote = await saveWorkspaceFile(projectId, open.path, draft, open.modified);
      setOpen({ ...open, content: draft, size: wrote.size, modified: wrote.modified });
      setSaveNote({ text: `Saved to ${open.path}.`, failed: false });
    } catch (failure) {
      setSaveNote({
        text: failure instanceof Error ? failure.message : String(failure),
        failed: true,
      });
    } finally {
      setSaving(false);
    }
  };

  if (!workspace) {
    return (
      <p className="filespane__empty">
        No project is open. Open a thread, or pick a project in the rail, and
        this pane shows its folder.
      </p>
    );
  }
  if (!workspace.root) {
    return (
      <p className="filespane__empty">
        <strong>{workspace.name}</strong> has no folder attached, so there are
        no files to show. The chip under the chat box attaches one.
      </p>
    );
  }

  const reports = (listing?.files ?? []).filter((row) =>
    row.path.startsWith('harness-reports/'),
  );
  const rest = (listing?.files ?? []).filter(
    (row) => !row.path.startsWith('harness-reports/'),
  );

  return (
    <div className="filespane" title={listing ? `read ${when(listing.read_at)}` : undefined}>
      {listingError ? (
        <Strip tone="wont" icon="alert">
          {listingError}
        </Strip>
      ) : null}
      {openError ? (
        <Strip tone="wont" icon="alert">
          {openError}
        </Strip>
      ) : null}

      <div className="filespane__split" data-open={open ? 'true' : undefined}>
        <div className="filespane__rail">
          {listing && listing.count === 0 ? (
            <p className="filespane__empty">The folder is empty.</p>
          ) : null}
          {reports.length > 0 ? (
            <FileGroup
              title="Journey reports"
              files={reports}
              active={open?.path ?? null}
              onOpen={(path) => void openFile(path)}
            />
          ) : null}
          {rest.length > 0 ? (
            <FileGroup
              title={reports.length > 0 ? 'Everything else' : 'Files'}
              files={rest}
              active={open?.path ?? null}
              onOpen={(path) => void openFile(path)}
            />
          ) : null}
          {listing && listing.left_unlisted > 0 ? (
            <p className="filespane__empty">
              {listing.left_unlisted} more not listed (first {listing.count} shown).
            </p>
          ) : null}
          {listing && (listing.skipped_outside_root ?? 0) > 0 ? (
            <p className="filespane__empty">
              {listing.skipped_outside_root} outside this folder, not followed.
            </p>
          ) : null}
          {listing && (listing.unreadable ?? 0) > 0 ? (
            <p className="filespane__empty">
              {listing.unreadable} unreadable, not listed.
            </p>
          ) : null}
        </div>

        {open ? (
          <div className="filespane__viewer">
            <div className="filespane__filehead">
              <span className="filespane__path mono" title={open.path}>
                {open.path}
              </span>
              <span className="filespane__modes" role="group" aria-label="View mode">
                <button
                  type="button"
                  className="filespane__mode"
                  aria-pressed={mode === 'pretty'}
                  onClick={() => {
                    if (
                      mode === 'source' &&
                      draft !== open.content &&
                      !window.confirm('Discard unsaved edits and switch to Pretty?')
                    ) {
                      return;
                    }
                    setDraft(open.content);
                    setMode('pretty');
                  }}
                >
                  Pretty
                </button>
                <button
                  type="button"
                  className="filespane__mode"
                  aria-pressed={mode === 'source'}
                  onClick={() => {
                    setDraft(open.content);
                    setMode('source');
                  }}
                >
                  Source
                </button>
              </span>
            </div>
            <p className="filespane__meta-line">
              {bytes(open.size)} · changed {when(open.modified)}
            </p>

            {mode === 'source' ? (
              <>
                <textarea
                  className="filespane__editor mono"
                  value={draft}
                  spellCheck={false}
                  disabled={saving}
                  onChange={(event) => setDraft(event.target.value)}
                  aria-label={`Edit ${open.path}`}
                />
                <div className="filespane__acts">
                  <Button
                    small
                    kind="primary"
                    icon="check"
                    onClick={() => void save()}
                    disabled={saving || draft === open.content}
                  >
                    {saving ? 'Saving…' : 'Save'}
                  </Button>
                  <Button
                    small
                    onClick={() => {
                      setDraft(open.content);
                      setMode('pretty');
                    }}
                    disabled={saving}
                  >
                    Cancel
                  </Button>
                </div>
              </>
            ) : (
              <div className="filespane__pretty">
                {open.path.endsWith('.md') ? (
                  <Markdown source={open.content} />
                ) : (
                  <pre className="filespane__content mono">{pretty(open)}</pre>
                )}
              </div>
            )}

            {saveNote ? (
              <div className="filespane__note">
                {saveNote.failed ? (
                  <Strip tone="wont" icon="alert">
                    {saveNote.text}{' '}
                    <button
                      type="button"
                      className="strip__action"
                      onClick={() => {
                        if (
                          editing &&
                          draft !== open.content &&
                          !window.confirm('Discard the unsaved edit and reopen the newer copy?')
                        ) {
                          return;
                        }
                        void openFile(open.path);
                      }}
                    >
                      reopen the newer copy
                    </button>
                  </Strip>
                ) : (
                  <Strip tone="fits" icon="check">
                    {saveNote.text}
                  </Strip>
                )}
              </div>
            ) : null}
          </div>
        ) : (
          <p className="filespane__empty filespane__empty--hint">
            Pick a file to read or edit.
          </p>
        )}
      </div>
    </div>
  );
}

function FileGroup({
  title,
  files,
  active,
  onOpen,
}: {
  title: string;
  files: { path: string; size: number; modified: number }[];
  active: string | null;
  onOpen: (path: string) => void;
}) {
  return (
    <section>
      <h3 className="filespane__group">{title}</h3>
      <ul className="filespane__list">
        {files.map((row) => (
          <li key={row.path}>
            <button
              type="button"
              className="filespane__row"
              data-active={row.path === active || undefined}
              onClick={() => onOpen(row.path)}
              title={`${row.path} · ${bytes(row.size)} · changed ${when(row.modified)}`}
            >
              <Icon name="file" size={12} />
              <span className="filespane__path mono">{baseName(row.path)}</span>
              <span className="filespane__meta mono">{bytes(row.size)}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function baseName(path: string): string {
  const norm = path.replace(/\\/g, '/');
  const parts = norm.split('/').filter(Boolean);
  return parts[parts.length - 1] || path;
}

function pretty(file: WorkspaceFile): string {
  if (file.path.endsWith('.json')) {
    try {
      return JSON.stringify(JSON.parse(file.content), null, 2);
    } catch {
      return file.content;
    }
  }
  return file.content;
}

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function when(epoch: number): string {
  try {
    return new Date(epoch * 1000).toLocaleString();
  } catch {
    return String(epoch);
  }
}
