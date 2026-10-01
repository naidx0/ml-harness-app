/**
 * MEMORY, EDITABLE. Two texts: what this project already knows, and who the
 * person is - the two stores Hermes keeps as MEMORY.md and USER.md, here as
 * rows the model writes through `remember` and the person edits here.
 *
 * Max, 2026-09-11: "implement all 3 exact same systems in ours." Hermes has
 * no pane for this - its memory is a file the person opens in an editor.
 * This product's rule is that anything the model holds about the person is
 * something the person can read and change, so the two blocks are here,
 * beside the chat, in the form the model sees them: one entry per line,
 * separated by `§` - Hermes' own delimiter, kept so an export reads the same.
 *
 * Save refuses the whole text if any entry carries a number with no origin
 * word, and says which - the engine's rule (`app/memory.py`), not this
 * pane's, and the edit stays in the box either way.
 */

import { useEffect, useState } from 'react';

import { getMemory, saveMemory, type MemoryTarget } from '../lib/engine/client';
import { Icon } from './Icon';

const TITLE: Record<MemoryTarget, string> = {
  project: 'This project knows',
  user: 'About you',
};

const EMPTY: Record<MemoryTarget, string> = {
  project:
    'Nothing yet. The model writes here when it learns something durable about this project - a decision, a ruled-out option, where the data lives. You can too.',
  user: 'Nothing yet. How you like to work, what you already know, what to stop asking you.',
};

export function MemoryPane({ projectId }: { projectId: number | null }) {
  const [texts, setTexts] = useState<Record<MemoryTarget, string>>({ project: '', user: '' });
  const [limits, setLimits] = useState<Record<MemoryTarget, number>>({ project: 2200, user: 1375 });
  const [drafts, setDrafts] = useState<Partial<Record<MemoryTarget, string>>>({});
  const [busy, setBusy] = useState<MemoryTarget | null>(null);
  const [refused, setRefused] = useState<Partial<Record<MemoryTarget, string>>>({});

  async function read() {
    try {
      const got = await getMemory(projectId);
      setTexts({ project: got.project.text, user: got.user.text });
      setLimits({ project: got.project.limit, user: got.user.limit });
    } catch {
      /* The engine is gone; the pane keeps what it had. */
    }
  }

  useEffect(() => {
    void read();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function save(target: MemoryTarget) {
    const text = drafts[target];
    if (text === undefined) return;
    setBusy(target);
    try {
      const answer = await saveMemory(target, projectId, text);
      if (!answer.ok) {
        setRefused((was) => ({ ...was, [target]: answer.detail ?? 'not saved' }));
        return;
      }
      setRefused((was) => ({ ...was, [target]: undefined }));
      setDrafts((was) => ({ ...was, [target]: undefined }));
      await read();
    } catch {
      setRefused((was) => ({ ...was, [target]: 'not saved - the engine did not answer' }));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="memorypane">
      {(['project', 'user'] as MemoryTarget[]).map((target) => {
        const shown = drafts[target] ?? texts[target];
        const dirty = drafts[target] !== undefined && drafts[target] !== texts[target];
        const disabled = target === 'project' && projectId === null;
        return (
          <section className="memorypane__block" key={target}>
            <header className="memorypane__head">
              <span className="eyebrow">{TITLE[target]}</span>
              <span className="num memorypane__use">
                {shown.length.toLocaleString()} / {limits[target].toLocaleString()}
              </span>
            </header>
            <textarea
              className="planpane__edit memorypane__edit"
              value={shown}
              spellCheck={false}
              disabled={disabled}
              placeholder={disabled ? 'Open a thread in a project to see its memory.' : EMPTY[target]}
              aria-label={TITLE[target]}
              onChange={(event) => setDrafts((was) => ({ ...was, [target]: event.target.value }))}
            />
            <div className="planpane__bar">
              {refused[target] ? (
                <span className="planpane__failed">
                  <Icon name="alert" /> {refused[target]}
                </span>
              ) : (
                <span className="planpane__count">one entry per line, separated by §</span>
              )}
              <button
                type="button"
                className="planpane__revert"
                disabled={!dirty || busy !== null}
                onClick={() => setDrafts((was) => ({ ...was, [target]: undefined }))}
              >
                Revert
              </button>
              <button
                type="button"
                className="planpane__save"
                disabled={!dirty || busy !== null || disabled}
                onClick={() => void save(target)}
              >
                {busy === target ? 'Saving' : 'Save'}
              </button>
            </div>
          </section>
        );
      })}
    </div>
  );
}
