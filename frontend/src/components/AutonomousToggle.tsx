/**
 * ONE CHOICE: run the approved-in-advance steps without stopping to ask.
 *
 * Max asked for this by name, and set its limits in the same sentence: *"it
 * is opt-in per thread and never the default; every auto-approved call is
 * still recorded and visible in the transcript exactly as a manual one would
 * be; and it never covers a tool that spends money or writes outside the
 * sandbox."* All three are enforced on the engine - `app/autonomy.py` holds
 * the whitelist, migration v015 makes the column `NOT NULL DEFAULT 0`, and
 * `conductor._run_tool` writes `auto_approved` onto the same event it would
 * have written anyway. This is the control, and its whole job is to be
 * honest about what pressing it does.
 *
 * A DROPDOWN, LIKE THE MODE BESIDE IT. Max, 2026-09-11: *"re work the plan
 * and auto modes, more as drop downs or expandables maybe - and make sure they
 * follow our brand book."* Same `Menu`, same square chip, two rows: "Ask me"
 * and "Autonomous". The chip is amber when it is on - the tone the approval
 * card uses, since both mean a person agreed to something that would
 * otherwise stop - and never green, because autonomy is a trade a person
 * made rather than an improvement.
 *
 * WHY IT NAMES WHAT IT COVERS. A switch labelled "autonomous" that silently
 * pre-approves eleven tools is a switch nobody can consent to. The engine's
 * reply to the toggle carries the whitelist AND the reasons, so the hover
 * lists exactly what was pre-approved and what still stops - in the engine's
 * words, not this file's. Nothing here is a sentence about safety that the
 * engine does not also enforce.
 *
 * ONE CONTROL, NOT A SETTINGS PAGE. It sits under the chat box beside the
 * mode, because both are per-thread and neither is a preference about the
 * product. There is deliberately no global version: a machine-wide autonomy
 * setting is the shape that quietly becomes the default.
 */

import { useEffect, useState } from 'react';
import { setThreadAutonomous } from '../lib/engine/client';
import { Icon } from './Icon';
import { MenuButton, type MenuRow } from './Menu';

export function AutonomousToggle({
  threadId,
  on,
  onChanged,
}: {
  threadId: number;
  /** The thread's own column. Off unless a person turned it on. */
  on: boolean;
  onChanged: (next: boolean) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [covers, setCovers] = useState<Record<string, string> | null>(null);
  const [never, setNever] = useState<Record<string, string> | null>(null);

  /* The lists are the engine's and are fetched only when they are about to be
     shown, so a thread nobody switches costs no request. */
  useEffect(() => {
    setCovers(null);
    setNever(null);
  }, [threadId]);

  async function set(next: boolean) {
    if (busy || next === on) return;
    setBusy(true);
    try {
      const answered = await setThreadAutonomous(threadId, next);
      setCovers(answered.covers ?? null);
      setNever(answered.never_covers ?? null);
      onChanged(Boolean(answered.autonomous));
    } catch {
      /* The engine refused or is gone. The control stays where it was, which
         is the honest thing: a control that moved anyway would be claiming
         a state the engine does not hold. */
    } finally {
      setBusy(false);
    }
  }

  const title = on
    ? [
        'Autonomous: the steps below run without stopping to ask.',
        covers
          ? '\nPre-approved:\n' +
            Object.keys(covers)
              .map((name) => '  ' + name)
              .join('\n')
          : '',
        never
          ? '\n\nStill asks every time:\n' +
            Object.entries(never)
              .map(([name, why]) => '  ' + name + ' — ' + why)
              .join('\n')
          : '',
      ].join('')
    : 'Off. Every step that needs an approval stops and asks you.\n' +
      'Autonomous lets a journey run its safe steps unattended — never ' +
      'training, never a deletion, never a change to where the project ' +
      'writes.';

  const rows: MenuRow[] = [
    {
      id: 'ask',
      label: 'Ask me',
      icon: 'play',
      current: !on,
      disabledReason: busy ? 'Switching…' : undefined,
    },
    {
      id: 'auto',
      label: 'Autonomous',
      icon: 'run',
      current: on,
      disabledReason: busy ? 'Switching…' : undefined,
    },
  ];

  return (
    <span className="autotoggle" data-on={on || undefined}>
      <MenuButton
        className="modechip"
        label="Approvals"
        title={title}
        rows={rows}
        open={open}
        setOpen={setOpen}
        minWidth={168}
        onChoose={(id) => void set(id === 'auto')}
      >
        <Icon name={on ? 'run' : 'play'} size={12} />
        <span className="modechip__word">{on ? 'Autonomous' : 'Ask me'}</span>
        <Icon name="chevdown" size={11} />
      </MenuButton>
    </span>
  );
}
