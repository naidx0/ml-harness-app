/**
 * THE MACHINE, AS A FOLD IN THE RAIL.
 *
 * Max, 2026-09-11: *"remove the pc thing from bottom left it should be
 * setting as it used to be as well - and then the nvidia local lab thing /
 * gpu available / compute available, should be from the sidebar drop down
 * and expandable."* The day before he had moved the machine out of the top
 * bar and into the sidebar; the first cut put it in the rail's FOOT, which is
 * the settings door and always was (App.tsx: "the bottom-left row is the
 * settings door"). So the foot goes back to what it was, and the machine is a
 * group of its own above it, drawn exactly as a project folder is drawn: a
 * 30px line with a glyph, a name, and the collapse chevron at the end - page
 * 17.2's own row, so the rail has one rhythm and not two.
 *
 * Shut by default. The rail is for conversations; the machine is the same
 * whichever one is open, and a person who wants it opens it once. The body is
 * the Machine pane itself - the same rows, the same provenance tags, the same
 * "not detected yet" - because two renderings of one measurement would be two
 * places for them to disagree. The pop-out glyph opens the pane in its own
 * window, the way the pane's own header does.
 */

import { useState } from 'react';

import { useLocalSpecs } from '../lib/useLocalSpecs';
import { Icon } from './Icon';
import { MachinePane } from './PaneStack';

export function MachineFold({ onOpenPane }: { onOpenPane: (pane: string) => void }) {
  const [open, setOpen] = useState(false);
  const specs = useLocalSpecs();

  /* The line names the card and its memory when they are known, so a shut
     fold still answers the one question a glance asks. A failed detection
     never renders as a measurement. */
  const gpu =
    specs.status === 'ok'
      ? specs.specs.gpu_name ?? 'No graphics card detected'
      : specs.status === 'loading'
        ? 'Reading this machine…'
        : 'Could not read this machine';
  const vram =
    specs.status === 'ok' && specs.specs.vram_gb !== null ? `${specs.specs.vram_gb} GB` : null;

  return (
    <div className="rail__group machinefold" data-open={open || undefined}>
      <div className="folderline">
        <button
          type="button"
          className="folderrow"
          aria-expanded={open}
          onClick={() => setOpen((was) => !was)}
          title="What the harness measured about this machine"
        >
          <Icon name="gpu" />
          {/* Two spans, not one: the name never truncates and the card's
              name does, so the row reads "Machine · NVIDIA GeForce RT…"
              with the dot always present. One font size for both, so the
              baseline does not step between them - the owner's screenshot
              of 2026-09-12 showed exactly that step. */}
          <span className="machinefold__name">Machine</span>
          <span className="machinefold__gpu">
            <span className="machinefold__dot" aria-hidden="true">·</span>
            <span className="machinefold__card">{gpu}</span>
            {vram ? <span className="num machinefold__vram">{vram}</span> : null}
          </span>
        </button>
        <button
          type="button"
          className="folderline__cv"
          aria-label="Open the machine in its own window"
          title="Open the machine in its own window"
          onClick={() => onOpenPane('machine')}
        >
          <Icon name="open" size={12} />
        </button>
        <button
          type="button"
          className="folderline__cv"
          aria-expanded={open}
          aria-label={open ? 'Collapse the machine' : 'Expand the machine'}
          onClick={() => setOpen((was) => !was)}
        >
          <Icon name="chevright" size={12} rotate={open ? 90 : 0} />
        </button>
      </div>
      {open ? (
        <div className="machinefold__body">
          <MachinePane />
        </div>
      ) : null}
    </div>
  );
}
