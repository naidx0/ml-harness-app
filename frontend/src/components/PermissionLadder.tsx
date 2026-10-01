/**
 * Permission ladder: ask / measure / write / full (CS1).
 *
 * Same Menu chip pattern as the old Ask/Autonomous toggle. Amber styling
 * when above `ask` — the person pre-approved something that would otherwise
 * stop. Hover lists what this mode covers, from the engine.
 */

import { useEffect, useState } from 'react';
import { setThreadPermission } from '../lib/engine/client';
import { Icon } from './Icon';
import { MenuButton, type MenuRow } from './Menu';

export type PermissionMode = 'ask' | 'measure' | 'write' | 'full';

const LABELS: Record<PermissionMode, string> = {
  ask: 'Ask me',
  measure: 'Measure',
  write: 'Write',
  full: 'Full — decide all',
};

export function PermissionLadder({
  threadId,
  mode,
  onChanged,
}: {
  threadId: number;
  mode: PermissionMode;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [covers, setCovers] = useState<Record<string, string> | null>(null);
  const [never, setNever] = useState<Record<string, string> | null>(null);

  useEffect(() => {
    setCovers(null);
    setNever(null);
  }, [threadId, mode]);

  async function set(next: PermissionMode) {
    if (busy || next === mode) return;
    setBusy(true);
    try {
      const answered = await setThreadPermission(threadId, next);
      setCovers(answered.covers ?? null);
      setNever(answered.never_covers ?? null);
      onChanged();
    } catch {
      /* stay put */
    } finally {
      setBusy(false);
    }
  }

  const title = [
    `Permissions: ${LABELS[mode]}`,
    mode === 'full'
      ? '\nZero-ask bypass: the model settles facts and tools. Only delete_sandbox still asks.'
      : '',
    covers && Object.keys(covers).length
      ? '\nPre-approved:\n' +
        Object.keys(covers)
          .map((name) => '  ' + name)
          .join('\n')
      : mode === 'ask'
        ? '\nEvery gated step still asks.'
        : '',
    never && Object.keys(never).length
      ? '\n\nStill asks:\n' +
        Object.keys(never)
          .map((name) => '  ' + name)
          .join('\n')
      : '',
  ].join('');

  const rows: MenuRow[] = (
    ['ask', 'measure', 'write', 'full'] as PermissionMode[]
  ).map((key) => ({
    id: key,
    label: LABELS[key],
    icon: key === 'ask' ? 'play' : 'run',
    current: mode === key,
    disabledReason: busy ? 'Switching…' : undefined,
  }));

  return (
    <span className="autotoggle" data-on={mode !== 'ask' || undefined}>
      <MenuButton
        className="modechip"
        label="Permissions"
        title={title}
        rows={rows}
        open={open}
        setOpen={setOpen}
        minWidth={168}
        onChoose={(id) => void set(id as PermissionMode)}
      >
        <Icon name={mode === 'ask' ? 'play' : 'run'} size={12} />
        <span className="modechip__word">{LABELS[mode]}</span>
        <Icon name="chevdown" size={11} />
      </MenuButton>
    </span>
  );
}
